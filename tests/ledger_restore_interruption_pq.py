"""Bounded nonblocking libpq channel for the fixed interruption query set."""

import json
import time

from ledger_restore_interruption_contracts import (
    COMMANDS,
    FIELDS,
    MAX_CELL,
    MAX_RESULT,
    PARAMETERS,
    SQL,
)
from psycopg import pq

READ, WRITE = 1, 2


def check(deadline):
    if time.monotonic() >= deadline:
        raise TimeoutError("interrupted restore control deadline exceeded")


class Channel:
    def __init__(self, conninfo, *, deadline, record):
        self.deadline, self.record = deadline, record
        self.raw, self.polling = None, pq.PollingStatus.WRITING
        self.ready, self.closed, self.query = False, False, None
        self.rows, self.result_seen, self.complete = None, False, False
        self.write_pending, self.first_poll = False, True
        self.notice_error = None
        check(deadline)
        self.raw = pq.PGconn.connect_start(conninfo)
        self.raw.notice_handler = self.notice
        check(deadline)

    def notice(self, result):
        try:
            value = result.error_message
            assert len(value) <= MAX_CELL, "control notice bound exceeded"
            self.record({"notice": value.decode("utf-8", "strict")})
        except BaseException as error:
            # libpq notice callbacks may have their exceptions intercepted.
            self.notice_error = self.notice_error or error

    @property
    def fd(self):
        return self.raw.socket

    @property
    def interest(self):
        if self.closed:
            return 0
        if not self.ready:
            return READ if self.polling == pq.PollingStatus.READING else WRITE
        return (READ | WRITE) if self.write_pending else READ if self.query else 0

    def send(self, name, parameters, *, deadline):
        assert self.ready and not self.closed and self.query is None
        assert name in SQL and len(parameters) == PARAMETERS[name]
        assert all(
            type(value) is bytes and len(value) <= MAX_CELL and b"\0" not in value
            for value in parameters
        )
        check(deadline)
        self.deadline = deadline
        self.query, self.rows = name, None
        self.complete, self.result_seen = False, False
        self.record(
            {
                "query": name,
                "sql": SQL[name],
                "parameters": [value.decode("utf-8", "strict") for value in parameters],
            }
        )
        self.raw.send_query_params(SQL[name].encode(), parameters)
        self.write_pending = bool(self.raw.flush())
        check(deadline)

    def step(self, mask=0):
        if self.notice_error is not None:
            raise self.notice_error
        if self.closed or self.ready and self.query is None:
            return
        check(self.deadline)
        if not self.ready:
            if not self.first_poll and not mask:
                return
            self.first_poll = False
            self.polling = self.raw.connect_poll()
            assert self.polling in (
                pq.PollingStatus.READING,
                pq.PollingStatus.WRITING,
                pq.PollingStatus.OK,
            ), "control connection failed or returned unknown poll state"
            if self.polling == pq.PollingStatus.OK:
                self.raw.nonblocking = 1
                assert self.raw.status == pq.ConnStatus.OK
                self.ready = True
            check(self.deadline)
            return
        if self.write_pending and mask & WRITE:
            self.write_pending = bool(self.raw.flush())
        if mask & READ:
            self.raw.consume_input()
        if not self.write_pending and not self.raw.is_busy():
            result = self.raw.get_result()
            if result is None:
                assert self.result_seen, "control request ended without a result"
                expected = pq.TransactionStatus.INTRANS if self.query in {"begin", "lock"} else None
                if expected is not None:
                    assert self.raw.transaction_status == expected
                else:
                    assert self.raw.transaction_status == pq.TransactionStatus.IDLE
                self.complete = True
            else:
                try:
                    assert not self.result_seen, "additional control result"
                    self.rows = self.read_result(result)
                    self.result_seen = True
                finally:
                    result.clear()
        if self.notice_error is not None:
            raise self.notice_error
        check(self.deadline)

    def read_result(self, result):
        name = self.query
        message, tag = result.error_message, result.command_status
        assert type(message) is bytes and len(message) <= MAX_CELL
        assert type(tag) is bytes and len(tag) <= MAX_CELL
        self.record(
            {
                "result": name,
                "status": int(result.status),
                "command_tag": tag.decode("utf-8", "strict"),
                "error": message.decode("utf-8", "strict"),
            }
        )
        if name in COMMANDS:
            assert result.status == pq.ExecStatus.COMMAND_OK
            assert result.command_status == COMMANDS[name] and result.ntuples == result.nfields == 0
            return []
        assert result.status == pq.ExecStatus.TUPLES_OK, "control SQL did not complete"
        assert result.ntuples <= 2 and result.nfields == len(FIELDS[name]) <= 32
        assert tuple(result.fname(i).decode("ascii") for i in range(result.nfields)) == FIELDS[name]
        assert all(result.fformat(i) == 0 for i in range(result.nfields))
        # Bound the exact compact JSON row-list encoding, including labels,
        # escaping, nulls and separators, before retaining each decoded cell.
        total, rows = 2, []
        for row in range(result.ntuples):
            total += 2 + bool(rows)
            values = {}
            for field, key in enumerate(FIELDS[name]):
                value = result.get_value(row, field)
                assert value is None or type(value) is bytes and len(value) <= MAX_CELL
                decoded = None if value is None else value.decode("utf-8", "strict")
                field_json = json.dumps({key: decoded}, separators=(",", ":"), allow_nan=False)
                total += len(field_json.encode()) - 2 + bool(values)
                assert total <= MAX_RESULT, "control result byte bound exceeded"
                values[key] = value
            rows.append(values)
        return rows

    def take(self):
        assert self.complete
        value, name = self.rows, self.query
        self.record(
            {
                "returned": name,
                "rows": [
                    {
                        key: None if value is None else value.decode("utf-8", "strict")
                        for key, value in row.items()
                    }
                    for row in value
                ],
            }
        )
        self.query, self.complete = None, False
        return value

    def close(self):
        if self.raw is not None and not self.closed:
            self.raw.finish()
            self.closed = True
            self.record({"physical_close": True})
