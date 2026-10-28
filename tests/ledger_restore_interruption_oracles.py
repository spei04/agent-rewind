"""Independent native failure and unchanged-archive gates for the COPY component."""

import hashlib
import json
import re

from ledger_restore_interruption_contracts import COPY, PROFILE
from ledger_restore_interruption_raw import TABLES
from ledger_restore_tools import MAX_ARCHIVE


def archive_witness(path, source):
    with path.open("rb") as handle:
        data = handle.read(MAX_ARCHIVE + 1)
    assert 5 < len(data) <= MAX_ARCHIVE and data.startswith(b"PGDMP")
    observed = re.findall(rb"COPY public\.[a-z_]+ \([^\x00]{1,2048}?\) FROM stdin;\n", data)
    expected = []
    for table in TABLES:
        columns = [
            row["name"] for row in source["inventory"]["columns"] if row["relation"] == table
        ]
        assert columns and all(re.fullmatch(r"[a-z_]+", column) for column in columns)
        expected.append(
            ("COPY public." + table + " (" + ", ".join(columns) + ") FROM stdin;\n").encode()
        )
    assert observed == expected and observed[1] == COPY
    return {
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "copy_literals": [value.decode() for value in observed],
    }


def assert_cancelled_restore(error, directory, command, control, owner_role):
    assert type(error) is RuntimeError and str(error) == "restore tool failed"
    record = json.loads((directory / "data-restore.json").read_text())
    assert record["argv"] == command and record["returncode"] == 1
    assert record["first_error"] == "RuntimeError" and record.get("control_error") is None
    assert record["signals"] == record["cleanup_errors"] == [] and record["reaped"] is True
    assert control.completed and not control.uncertain
    assert control.cancel_attempted and control.cancel_ack and control.restore_absent
    assert record["control"] == control.report()
    for name in ("stdout", "stderr"):
        path = directory / ("data-restore." + name)
        value = path.read_bytes()
        assert record["files"][path.name] == {
            "bytes": len(value),
            "sha256": hashlib.sha256(value).hexdigest(),
        }
    assert (directory / "data-restore.stdout").read_bytes() == b""
    diagnostic = (directory / "data-restore.stderr").read_bytes()
    message = (
        b"pg_restore: error: could not execute query: ERROR:  "
        b"canceling statement due to user request\nCommand was: " + COPY
    )
    # pg_restore's pinned archiver may emit its fixed TOC context before the error.
    context = (
        rb"pg_restore: while PROCESSING TOC:\n"
        rb"pg_restore: from TOC entry [1-9][0-9]{0,9}; [0-9]{1,10} [0-9]{1,10} "
        rb"TABLE DATA api_keys " + re.escape(owner_role.encode()) + rb"\n"
    )
    assert re.fullmatch(rb"(?:" + context + rb")?" + re.escape(message), diagnostic)
    report = control.owner.report()
    assert report["resolved"] and report["profile"] == list(PROFILE)
    assert [row["label"] for row in report["steps"]] == list(PROFILE)
    assert [row["returncode"] for row in report["children"]] == [0, 0, 0, 0, 1]
    assert len(report["children"]) == 5
    return record
