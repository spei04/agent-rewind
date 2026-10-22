"""Native boundaries for the complete inspector under its actual operator body."""

import hashlib
import json
import sqlite3
from uuid import uuid4

import pytest
import test_migrations_postgres as migration_tests
from ledger_operator_fixture import SQLiteTrace
from ledger_reader_fixture import (
    RowTransferWatch,
    complete_postgres_ar6,
    later_admitted_call,
    postgres_snapshot,
    seed_ar7,
    sqlite_snapshot,
)
from postgres_control import observe_exclusion_failure, wait_for_database_drain
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool
from test_ledger_operator_postgres import PostgresTrace
from test_ledger_reader_independent import COMPLETE_CASES, reader_case
from test_run_projection_postgres import drain, observed_reader

from agent_rewind.migrations import ledger_work, service
from agent_rewind.migrations.ledger_transaction import LedgerOutcome, ledger_transaction
from agent_rewind.migrations.ledger_work import LedgerWork
from agent_rewind.migrations.schema import MigrationRefused

__all__ = ["reader_case", "observed_reader"]
pg = migration_tests.pg
postgres_only = pytest.mark.skipif(
    not migration_tests.POSTGRES, reason="Opt-in independent PostgreSQL ledger reader"
)


@pytest.fixture
def reader_trace(monkeypatch, record_property):
    trace = SQLiteTrace()
    actions = []

    def connect(*args, **kwargs):
        raw = trace.connect(*args, **kwargs)

        def authorize(action, first, second, database, trigger):
            actions.append((trace.phase, action, first, second, database, trigger))
            return sqlite3.SQLITE_OK

        raw.set_authorizer(authorize)
        return raw

    trace.authorized_actions = actions
    monkeypatch.setattr(sqlite3, "connect", connect)
    yield trace
    record_property("reader_native_trace", json.dumps(trace.events))


@pytest.mark.parametrize("reader_case", COMPLETE_CASES, indirect=True)
def test_reader_uses_one_raw_connection_and_no_native_data_or_schema_writes(
    reader_case, reader_trace, record_property
):
    from agent_rewind.migrations.ledger_inspection import inspect_ledger_state

    case, trace = reader_case, reader_trace
    before = sqlite_snapshot(case.path)
    boundary = len(trace.events)
    engine = case.operator_engine()
    work, outcome = LedgerWork(), LedgerOutcome()
    try:
        with ledger_transaction(engine, outcome, work=work) as connection:
            trace.phase = "reader"
            raw = connection.connection.driver_connection
            assert raw.in_transaction
            result = inspect_ledger_state(connection)
            assert connection.connection.driver_connection is raw and raw.in_transaction
            assert result.model_dump(mode="json") == case.expected
            trace.phase = "cleanup"
        events = trace.events[boundary:]
        assert len([event for event in events if event[0] == "connect_return"]) == 1
        sql = [event[3] for event in events if event[0] == "sql"]
        assert "BEGIN EXCLUSIVE" in sql and "COMMIT" in sql
        reader_sql = [event[3] for event in events if event[:2] == ("sql", "reader")]
        assert reader_sql
        writes = {
            getattr(sqlite3, name)
            for name in (
                "SQLITE_INSERT",
                "SQLITE_UPDATE",
                "SQLITE_DELETE",
                "SQLITE_CREATE_INDEX",
                "SQLITE_CREATE_TABLE",
                "SQLITE_CREATE_TEMP_INDEX",
                "SQLITE_CREATE_TEMP_TABLE",
                "SQLITE_CREATE_TEMP_TRIGGER",
                "SQLITE_CREATE_TEMP_VIEW",
                "SQLITE_CREATE_TRIGGER",
                "SQLITE_CREATE_VIEW",
                "SQLITE_DROP_INDEX",
                "SQLITE_DROP_TABLE",
                "SQLITE_DROP_TEMP_INDEX",
                "SQLITE_DROP_TEMP_TABLE",
                "SQLITE_DROP_TEMP_TRIGGER",
                "SQLITE_DROP_TEMP_VIEW",
                "SQLITE_DROP_TRIGGER",
                "SQLITE_DROP_VIEW",
                "SQLITE_ALTER_TABLE",
                "SQLITE_REINDEX",
                "SQLITE_ANALYZE",
                "SQLITE_ATTACH",
                "SQLITE_DETACH",
            )
        }
        assert not [
            action
            for action in trace.authorized_actions
            if action[0] == "reader" and action[1] in writes
        ]
        assert work.prepaid_bootstrap == 12 and work.prepaid_cleanup == 8
        assert 0 < work.observed_ordinary <= 2028
        assert not outcome.cleanup_failed and outcome.commit_acknowledged
        assert engine.pool.checkedout() == 0
        record_property("reader_work", str(work.observed_ordinary))
    finally:
        engine.dispose()
    assert sqlite_snapshot(case.path) == before


@pytest.mark.parametrize("state", ["unbegun", "logical", "native-exclusive"])
@pytest.mark.parametrize("reader_case", [COMPLETE_CASES[0]], indirect=True)
def test_unissued_connection_refuses_before_any_reader_sql(reader_case, reader_trace, state):
    from agent_rewind.migrations.ledger_inspection import inspect_ledger_state

    engine = create_engine(str(reader_case.engine.url))
    try:
        with engine.connect() as connection:
            if state == "logical":
                connection.begin()
            elif state == "native-exclusive":
                connection.exec_driver_sql("BEGIN EXCLUSIVE")
            boundary = len(reader_trace.events)
            with pytest.raises(MigrationRefused, match="^transactional_connection_required$"):
                inspect_ledger_state(connection)
            assert reader_trace.events[boundary:] == []
    finally:
        engine.dispose()


@pytest.mark.parametrize("failure", ["deadline", "ordinary-budget"])
@pytest.mark.parametrize("reader_case", [COMPLETE_CASES[0]], indirect=True)
def test_reader_exhaustion_never_publishes_and_still_cleans_up(
    reader_case, reader_trace, monkeypatch, failure
):
    from agent_rewind.migrations.ledger_inspection import inspect_ledger_state

    now = [1000.0]
    monkeypatch.setattr(ledger_work, "monotonic", lambda: now[0])
    case, trace = reader_case, reader_trace
    before = sqlite_snapshot(case.path)
    engine = case.operator_engine()
    work, outcome, returned = LedgerWork(), LedgerOutcome(), []
    code = "migration_busy" if failure == "deadline" else "ledger_limit_exceeded"
    try:
        with (
            pytest.raises(MigrationRefused, match="^" + code + "$"),
            ledger_transaction(engine, outcome, work=work) as connection,
        ):
            if failure == "deadline":
                now[0] += 121
            else:
                # Spend real observed bundles, leaving insufficient work for a catalog.
                while work.observed_ordinary < 1950:
                    connection.exec_driver_sql("SELECT 1").scalar_one()
            trace.phase = "reader"
            returned.append(inspect_ledger_state(connection))
        assert returned == []
        assert outcome.rollback_acknowledged and not outcome.commit_attempted
        assert not outcome.cleanup_failed
        assert work.observed_ordinary <= 2028
        assert len(work.cleanup_observations) <= 8
        assert engine.pool.checkedout() == 0
        assert "ROLLBACK" in trace.sql()
    finally:
        engine.dispose()
    assert sqlite_snapshot(case.path) == before


@pytest.fixture
def postgres_reader_case(request, pg, observed_reader):
    legacy, ledger, empty = request.param
    case = complete_postgres_ar6(pg, legacy=legacy)
    if ledger:
        seed_ar7(case, empty_accounts=empty)
        drain(pg)
    yield case
    case.dispose()
    drain(pg)


@postgres_only
@pytest.mark.parametrize("postgres_reader_case", COMPLETE_CASES, indirect=True)
def test_postgres_fixture_has_complete_profile_history_and_opening(postgres_reader_case, pg):
    from agent_rewind.migrations.ledger_state import validate_ledger_chain, validate_progress_row
    from agent_rewind.migrations.schema import LEDGER

    case = postgres_reader_case
    with case.engine.connect() as connection:
        adoption = dict(
            connection.exec_driver_sql("SELECT * FROM installation_adoptions").mappings().one()
        )
        assert {
            key: value for key, value in adoption.items() if key != "installed_schema_fingerprint"
        } == {
            key: value
            for key, value in case.adoption.items()
            if key != "installed_schema_fingerprint"
        }
        if case.revision == LEDGER:
            rows = (
                connection.exec_driver_sql(
                    "SELECT revision,phase,source_digest,CAST(cursor AS TEXT) AS cursor,"
                    "rows_verified,status,updated_at FROM migration_progress "
                    "WHERE revision='ar_0007_ledger' "
                    "ORDER BY phase"
                )
                .mappings()
                .all()
            )
            values = [validate_progress_row(connection, dict(row)) for row in rows]
            receipt = validate_ledger_chain(
                [value for value in values if hasattr(value, "manifest")],
                next(value for value in values if hasattr(value, "jobs")),
            )
            assert receipt.model_dump(mode="json") == case.expected["head"]
    drain(pg)


@postgres_only
@pytest.mark.parametrize("postgres_reader_case", COMPLETE_CASES, indirect=True)
def test_postgres_complete_reader_identity_and_no_native_tuple_writes(
    postgres_reader_case, pg, monkeypatch, record_property
):
    _inspect_postgres_case(postgres_reader_case, pg, monkeypatch, record_property)


def _inspect_postgres_case(case, pg, monkeypatch, record_property):
    from agent_rewind.migrations.ledger_inspection import inspect_ledger_state

    before = postgres_snapshot(case.engine)
    drain(pg)
    trace = PostgresTrace(monkeypatch)
    engine = case.operator_engine()
    work, outcome = LedgerWork(), LedgerOutcome()
    try:
        with ledger_transaction(engine, outcome, work=work) as connection:
            trace.phase = "counter-observer"
            observer_start = work.observed_ordinary
            assert connection.exec_driver_sql("SHOW track_counts").scalar_one() == "on"
            counters_before = _transaction_write_counters(connection)
            before_units = work.observed_ordinary - observer_start
            trace.phase = "reader"
            raw = connection.connection.driver_connection
            reader_start = work.observed_ordinary
            state = inspect_ledger_state(connection)
            reader_units = work.observed_ordinary - reader_start
            assert connection.connection.driver_connection is raw
            assert state.model_dump(mode="json") == case.expected
            trace.phase = "counter-observer"
            observer_start = work.observed_ordinary
            counters_after = _transaction_write_counters(connection)
            after_units = work.observed_ordinary - observer_start
            assert _tuple_write_delta(counters_before, counters_after) == {}
            record_property("counter_observer_units", str(before_units + after_units))
            trace.phase = "ordinary"
        assert len(trace.handles) == 1
        assert raw.closed and outcome.commit_acknowledged and not outcome.cleanup_failed
        assert work.observed_ordinary <= 2028
        commands = [
            sql.strip().upper()
            for phase, kind, _, sql in trace.events
            if phase == "reader" and kind in {"sql-call", "command"} and sql
        ]
        assert commands
        # Hash the original spelling, before the separate prefix-only policy.
        _assert_reviewed_ctes(
            [
                sql
                for phase, kind, _, sql in trace.events
                if phase == "reader" and kind == "sql-call" and sql
            ]
        )
        assert all(sql.startswith(("SELECT", "WITH", "SET LOCAL", "SHOW")) for sql in commands)
        assert not any(
            sql.startswith(("DECLARE", "FETCH", "INSERT", "UPDATE", "DELETE")) for sql in commands
        )
        record_property("reader_work", str(reader_units))
        record_property("total_ordinary", str(work.observed_ordinary))
    finally:
        engine.dispose()
        trace.stop()
        record_property("reader_native_trace", json.dumps(trace.events))
    drain(pg)
    assert postgres_snapshot(case.engine) == before
    drain(pg)


@pytest.fixture
def latin1_pg(monkeypatch):
    """Own a C-locale LATIN1 database and roles, independent of default-encoding cases."""
    admin = create_engine(
        migration_tests.POSTGRES, isolation_level="AUTOCOMMIT", poolclass=NullPool
    )
    token = "ar_reader_latin1_" + uuid4().hex
    owner, app, group = token + "_owner", token + "_app", token + "_group"
    password = "synthetic-test-only"
    roles, engines = [], []
    database_created = False
    exclusion = service._postgres_exclusion

    def observed_exclusion(connection, tables):
        observe_exclusion_failure(exclusion, connection, tables, control=admin, database=token)

    monkeypatch.setattr(service, "_postgres_exclusion", observed_exclusion)
    try:
        with admin.connect() as connection:
            assert (
                connection.exec_driver_sql("SHOW server_version_num").scalar_one().startswith("16")
            )
            for role, options in (
                (owner, f"LOGIN PASSWORD '{password}'"),
                (app, f"LOGIN NOINHERIT PASSWORD '{password}'"),
                (group, "NOLOGIN"),
            ):
                connection.exec_driver_sql(f"CREATE ROLE {role} {options}")
                roles.append(role)
            connection.exec_driver_sql(
                f"CREATE DATABASE {token} OWNER {owner} TEMPLATE template0 "
                "ENCODING 'LATIN1' LC_COLLATE 'C' LC_CTYPE 'C'"
            )
            database_created = True
        url = admin.url.set(database=token)
        for identity, secret in ((owner, password), (app, password), (url.username, url.password)):
            engines.append(
                create_engine(
                    url.set(username=identity, password=secret),
                    poolclass=NullPool,
                    connect_args={"client_encoding": "UTF8"},
                )
            )
        owner_engine, app_engine, privileged = engines
        with owner_engine.begin() as connection:
            connection.exec_driver_sql("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
            assert tuple(
                connection.exec_driver_sql(
                    "SELECT pg_encoding_to_char(encoding),datcollate,datctype "
                    "FROM pg_database WHERE datname=current_database()"
                ).one()
            ) == ("LATIN1", "C", "C")
            assert connection.exec_driver_sql("SHOW client_encoding").scalar_one() == "UTF8"
            assert tuple(
                connection.exec_driver_sql(
                    "SELECT rolsuper,rolcreaterole FROM pg_roles WHERE rolname=current_user"
                ).one()
            ) == (False, False)
        wait_for_database_drain(admin, token)
        yield {
            "owner": owner_engine,
            "app": app_engine,
            "admin": privileged,
            "control": admin,
            "owner_role": owner,
            "app_role": app,
            "group_role": group,
        }
    finally:
        for engine in engines:
            engine.dispose()
        with admin.connect() as connection:
            if database_created:
                connection.exec_driver_sql(f"DROP DATABASE {token} WITH (FORCE)")
            for role in reversed(roles):
                connection.exec_driver_sql(f"DROP ROLE {role}")
            assert (
                connection.execute(
                    text("SELECT count(*) FROM pg_database WHERE datname=:name"), {"name": token}
                ).scalar_one()
                == 0
            )
            assert (
                connection.execute(
                    text("SELECT count(*) FROM pg_roles WHERE rolname IN (:owner,:app,:group)"),
                    {"owner": owner, "app": app, "group": group},
                ).scalar_one()
                == 0
            )
        admin.dispose()


@postgres_only
def test_postgres_latin1_native_bytes_and_decoded_utf8_sizes_are_distinct(
    latin1_pg, observed_reader, monkeypatch, record_property
):
    from test_ownership import FRESH

    from agent_rewind.migrations.ledger_inspection import inspect_ledger_state

    case = complete_postgres_ar6(latin1_pg, legacy=False)
    try:
        with case.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO jobs(id,kind,created,payload,status,cancel,budget,reserved,actor) "
                    "VALUES(:id,'run',1700000000.125,:payload,'queued',false,1,0,:actor)"
                ),
                {
                    "id": "e" * 32,
                    "payload": "café",
                    "actor": FRESH["principal_grants"][0]["principal_id"],
                },
            )
            connection.execute(
                text("INSERT INTO resource_scopes VALUES('job',:id,:project)"),
                {"id": "e" * 32, "project": FRESH["project_id"]},
            )
            native, value = connection.exec_driver_sql(
                "SELECT octet_length(payload),payload FROM jobs"
            ).one()
            assert native == 4 and value == "café" and len(value.encode("utf-8")) == 5
        drain(latin1_pg)
        before = postgres_snapshot(case.engine)
        drain(latin1_pg)
        watch = RowTransferWatch(monkeypatch, {"latin1-financial-payload": "café"})
        engine, work, outcome = case.operator_engine(), LedgerWork(), LedgerOutcome()
        try:
            with ledger_transaction(engine, outcome, work=work) as connection:
                observer_start = work.observed_ordinary
                actual_server = connection.exec_driver_sql("SHOW server_encoding").scalar_one()
                actual_client = connection.exec_driver_sql("SHOW client_encoding").scalar_one()
                observer_units = work.observed_ordinary - observer_start
                assert actual_server == "LATIN1"
                reader_start = work.observed_ordinary
                state = inspect_ledger_state(connection)
                reader_units = work.observed_ordinary - reader_start
                assert state.model_dump(mode="json") == case.expected
            assert work.observed_ordinary <= 2028
            assert outcome.commit_acknowledged and not outcome.cleanup_failed
        finally:
            engine.dispose()
        # Size the decoded Python value as UTF-8, independently of native octets.
        # This is not a measurement of physical network packet bytes.
        assert watch.hits and all(hit["bytes"] == 5 for hit in watch.hits)
        record_property(
            "encoding_receipt",
            json.dumps(
                {
                    "server_encoding": actual_server,
                    "operator_client_encoding": actual_client,
                    "encoding_observer_units": observer_units,
                    "reader_work": reader_units,
                    "total_ordinary": work.observed_ordinary,
                    "native_bytes": native,
                    "decoded_utf8_bytes": 5,
                    "decoded_utf8_bound": 4 * native,
                    "observed_transfers": watch.hits,
                }
            ),
        )
        drain(latin1_pg)
        assert postgres_snapshot(case.engine) == before
        drain(latin1_pg)
    finally:
        case.dispose()


# Exact compiled PostgreSQL WITH queries from the independently reviewed packets.
# These digests are fixed test inputs; they are never derived from runtime SQL.
_PG_REVIEWED_CTES = frozenset(
    {
        "024954d3816b259ebbb730306d820ee544483dd57985ce280c6c33821f706082",
        "048a738ffe573b39761b2c3b796c2dcab0c1917c423080e55a0e73a7c2e0dadf",
        "04a6ecc08f204b8de307841b490d7f665ab582c6f60a45f99da044fe9bd6bc9c",
        "04d0fc26d0163f2e2a554ccd96e6b698e2b794e6f970e99953fee10eefb88905",
        "05a93e12f6928096606e618fd47e4122593693f3a3fc2cf03a0bf3d75d043c5d",
        "11c9b46d16957de029b731072904c1a00a7a690cb93d800e16da5728212271d1",
        "12d6f884a520068b019979a881787565441818c7866f8bace81bb792a2dead79",
        "180d03b404731aaba6b5f4b9c2270a35207729f2b82e390683d88c1e26900ff3",
        "1d49c2d60b3582225286be1d47a5dedd1f1fe219c5317676b6e7b7f3d4e008c7",
        "2041d64b8a3949997fc81abae6d74d4cf5caf83d770c7cb85134df6ff858c2d2",
        "2b8ea987b8e021cb6530393d5a88b73635d927123c2b4c0f91f675c3119cf93e",
        "33108604b30c8978b1c892b1227557f27355a62ad8c190ddc238b0d375b4e430",
        "33f9e7fae65b34f03e930e523a3c552f8a87cc9c7fc40848838d2fc5a313e95d",
        "354643457bf63cced95acfdb0c18dd5610a2d73538d3721799da099335bdb4a1",
        "3753ba645b44255586b9b45081ec666d68cd1656fb26c5bccdb16f6edf56f3ca",
        "376dd01c9259384340dff553e12cdb0c7088bcfef7394a027580f12f427a8f45",
        "3c3639fff942b91476617cbe97cbb3244bf60184ebe880df1265f2ba50226ee9",
        "426742b6d39c258506a22383a86760491bb178ca45ee84726ef5eb87df14c2a5",
        "42a98d7f4165ffe7cb694d62f40e39ef88d161f4adf2ca89ac384226fbc2f6ce",
        "45ee7f22603222b55c2b5789f2f4093c539f24b321c5f25daac452bc83f10cac",
        "48cbfbb9cc01afb0638073d0d37584a1b34566e0d0b2328792a4c45ef32f518d",
        "4a091239e57afc43ba8f9b3ac3a24ea492682ffaffe1704f9251d709e426371c",
        "4bbcd2675d84581bc2206d8749e5986291fe3c021eb45dc54c5a6d6657b7752d",
        "4c0c2191a208c52071d53c8fb28140efe6394e9136289d300d6c429192210c36",
        "58975cfbe6a4e76416eba03eb80927fc579283648ddba3641de522628eda4c9c",
        "5f896d5b85b1295c6b38c7b14c0837e2b6d378e7caa1fa15bb54ae89714838f6",
        "6481b101af2a4453d14eeeab7e206bff2ee7985ea652ac77f01a1e0fbba6041a",
        "6cf594b7742018edb45395ec73439cf03b1d856ca7390c91c1950756a19996ca",
        "77eba7246c117b680723ce8c35431596ad35acaef64c57d9405d2bba85fe037f",
        "78b2550c0c5e377c82320f47e5a81365401fbc1260b9d043abdbebd41298c3e9",
        "78d562179a3dd6743c943aadf31afeb6c2cdb13184438bdb90bdfbc451d661aa",
        "7f891ebba26424c1744f2796c9d5fab49cba1dbdde34371f1c05201e714ee224",
        "80213b479f3384489b73dedfff0c3e2fd7441fa11f7868be3d4c1cab21d6b473",
        "8023d6f593097fe49befe2985234acb6b43bea818e520be8cf12fcd7f5341603",
        "80e55b6ac13f91382daa482bb166b5e0f4285edb7d6168878b26e9fe1e2e6c16",
        "824ebb2b09e333a8ddb652d486d72a94493ee012b58fbe4252764f4904adb46c",
        "8ed1aa2368ae394afed3fdc2cf33856b6636f21a346be0df0a4ec83c32356a44",
        "97e94fbc25accb62fef3c6686706e1e2f3a08f0324f8d9d853b576f143c04890",
        "9e7e36c9851830f15c4f21bf750fe0e51aad47048741fc23f520808c31b92ef8",
        "9ea00b808d6058cc0efcf8f82d8cb295b9c2e64bd52d1cd18e691f9b8921ea9d",
        "9ed24896996cf130b62881c234b314f473d326cba4c05f9634befba29966a097",
        "a27ef80849003736c8fad0102f33c98cbc23239e919253d0d80646cf3a5e0af5",
        "a4c696fdf29d34141764955db8d2c5370857f3e1b7d81844dccd291feaed4251",
        "a64e98af4dadf05a6cf9b1d77942cdf1318d683fd8f7c71faeb2f901afaed996",
        "abcec159db836de20424480e6d24b1dff59bb0aee4a522cf3c6392362870d60d",
        "ad82b369be58a085c257e8a3e4af4cc744fa9fddf6e6a11d871dc22cbb9852af",
        "b22921b6c4bf38237e8043a52529e56ecbd5065d6965e879583f28cbd52d1f5a",
        "b2d3c967bd1af7a3e3bc91e3772c722768fabd80d4b5e9bcf15e4d1a4de6df82",
        "b351f4f09fe9aec1f5d6655b8b0e3c7ce5d44c36b134326b988259a25caefc8f",
        "b42d30e722223b278bcf296df964a829f2727f8de8a3042ee6b857a7216210e6",
        "b59628f2d94e265b83bc372b386c703b3bee5e26537ebb28c4947b6058e5b296",
        "cca01c6dbb7c33d5301d48350ab292d39129e2a86bd2e7d03b84a93172ba6105",
        "cd78f3fffe20a1a5b241e1a3b588b3667d580842b312dfaba48da7df5519854e",
        "ceebdb6518cdea9ba113f4cf3be1643973a139c5155ebd52539a7367d7628522",
        "d8f7de1efde8f8b9bda0ac665fd7c54325d4ac504217f0a2282fd30019749d37",
        "db4468d31f5d5e52ad9c5b866e52febfb9444aedbf1e9046ab7f734fa416772a",
        "db7874588382edb8c41714b1cd1148514ffddb27b2575a543efefdc5d48dd460",
        "e1b81e7bac6282f92a4a74172634263525ad08cc56890c5c7567565e62c67786",
        "e663d46b8979f19684df0be1714950b6ad8f8f3daf8b229d2d82f4309a7c470e",
        "e719b90f108c5b470e236afb1d6227b2dbba47eebd94a5afe8657a532527531d",
        "e87d655df9c62eca019759ff5d83dd484c8f7948686d8ad720a419c935aa6f65",
        "ea9c12b61abc44c764f4214c7ab5edbef040d098e9dae46032dba8577718f8b1",
        "ee75b988bdaf066d4a5199aaece1c2dd255d7d9b338a37c64694752e8c647d18",
        "f1b1ee5489902b1ebf17937b2a28d3fd93d2b5617c053cef37ab5dc89b654626",
        "f4b315e6f37857bd3090c6f2cdfa4c1d765cdcda0592bbd2e82241b544cd9949",
    }
)


def _assert_reviewed_ctes(commands):
    for command in commands:
        if command.lstrip().upper().startswith("WITH"):
            assert hashlib.sha256(command.encode()).hexdigest() in _PG_REVIEWED_CTES


def _transaction_write_counters(connection):
    """Backend-local before/after deltas; never assume a zero initial counter."""
    return {
        (row[0], row[1], row[2]): tuple(row[3:])
        for row in connection.exec_driver_sql(
            "SELECT relid,schemaname,relname,n_tup_ins,n_tup_upd,n_tup_del "
            "FROM pg_stat_xact_all_tables ORDER BY relid"
        )
    }


def _tuple_write_delta(before, after):
    return {
        key: tuple(
            end - start
            for start, end in zip(
                before.get(key, (0, 0, 0)), after.get(key, (0, 0, 0)), strict=True
            )
        )
        for key in before.keys() | after.keys()
        if before.get(key, (0, 0, 0)) != after.get(key, (0, 0, 0))
    }


def test_native_cte_policy_binds_reviewed_sql_and_rejects_hidden_dml():
    from sqlalchemy.dialects.postgresql.psycopg import PGDialect_psycopg

    from agent_rewind.migrations import (
        ledger_catalog_sql,
        ledger_financial_sql,
        ledger_graph_sql,
        ledger_history_sql,
    )

    actual = set()
    for module in (ledger_catalog_sql, ledger_financial_sql, ledger_graph_sql, ledger_history_sql):
        for key, query in module.SQL.items():
            if key[1] == "postgresql" and query.lstrip().upper().startswith("WITH"):
                command = str(text(query).compile(dialect=PGDialect_psycopg()))
                _assert_reviewed_ctes([command])
                actual.add(hashlib.sha256(command.encode()).hexdigest())
    assert actual == _PG_REVIEWED_CTES
    for predicate in ("true", "false"):
        command = (
            "WITH changed AS (UPDATE jobs SET reserved=reserved WHERE "
            + predicate
            + " RETURNING id) SELECT count(*) FROM changed"
        )
        with pytest.raises(AssertionError):
            _assert_reviewed_ctes([command])


@postgres_only
@pytest.mark.parametrize("postgres_reader_case", [COMPLETE_CASES[1]], indirect=True)
@pytest.mark.parametrize("matches", [True, False], ids=["same-value-update", "zero-row-update"])
def test_postgres_native_write_witness_detects_cte_and_exposes_zero_row_limit(
    postgres_reader_case, pg, matches, record_property
):
    case = postgres_reader_case
    snapshot = postgres_snapshot(case.engine)
    drain(pg)
    engine, work, outcome = case.operator_engine(), LedgerWork(), LedgerOutcome()

    class RollbackWitness(BaseException):
        pass

    try:
        with (
            pytest.raises(RollbackWitness),
            ledger_transaction(engine, outcome, work=work) as connection,
        ):
            assert connection.exec_driver_sql("SHOW track_counts").scalar_one() == "on"
            before = _transaction_write_counters(connection)
            predicate = "true" if matches else "false"
            command = (
                "WITH changed AS (UPDATE jobs SET reserved=reserved WHERE "
                + predicate
                + " RETURNING id) SELECT count(*) FROM changed"
            )
            assert connection.exec_driver_sql(command).scalar_one() == (3 if matches else 0)
            after = _transaction_write_counters(connection)
            delta = _tuple_write_delta(before, after)
            job_changes = [value for key, value in delta.items() if key[1:] == ("public", "jobs")]
            assert job_changes == ([(0, 3, 0)] if matches else [])
            if not matches:
                assert delta == {}
            with pytest.raises(AssertionError):
                _assert_reviewed_ctes([command])
            record_property("tuple_write_delta", repr(delta))
            raise RollbackWitness()
        assert outcome.rollback_acknowledged and not outcome.commit_attempted
        assert not outcome.cleanup_failed
    finally:
        engine.dispose()
    drain(pg)
    assert postgres_snapshot(case.engine) == snapshot
    drain(pg)


@postgres_only
@pytest.mark.parametrize(
    ("effect", "future_zero_period"),
    [("reserved", False), ("settled", False), ("released", False), ("reserved", True)],
    ids=["reserved", "settled", "released", "later-reservation-after-future-period"],
)
def test_postgres_complete_evolving_financial_state(
    pg, observed_reader, effect, future_zero_period, monkeypatch, record_property
):
    case = complete_postgres_ar6(pg, legacy=False)
    try:
        seed_ar7(case)
        ids = later_admitted_call(case, effect=effect, future_zero_period=future_zero_period)
        if future_zero_period:
            with case.engine.connect() as connection:
                future = connection.execute(
                    text(
                        "SELECT limit_microusd,held_microusd,accounted_microusd "
                        "FROM budget_accounts "
                        "WHERE id IN (:organization,:project) ORDER BY id"
                    ),
                    {
                        "organization": ids["future_accounts"][0],
                        "project": ids["future_accounts"][1],
                    },
                ).all()
                assert future == [(0, 0, 0), (0, 0, 0)]
        drain(pg)
        _inspect_postgres_case(case, pg, monkeypatch, record_property)
    finally:
        case.dispose()
        drain(pg)


@postgres_only
@pytest.mark.parametrize("postgres_reader_case", [COMPLETE_CASES[0]], indirect=True)
@pytest.mark.parametrize("extra_whitespace", [0, 1], ids=["unchanged-control", "receipt-mismatch"])
def test_postgres_adoption_utf8_receipt_before_json_semantics(
    postgres_reader_case, pg, extra_whitespace, monkeypatch, record_property
):
    from agent_rewind.migrations.ledger_inspection import inspect_ledger_state

    case = postgres_reader_case
    before = postgres_snapshot(case.engine)
    with case.engine.connect() as connection:
        mapping = connection.exec_driver_sql(
            "SELECT CAST(mapping AS TEXT) FROM installation_adoptions"
        ).scalar_one()
    drain(pg)
    replacement = mapping + " " * extra_whitespace
    assert json.loads(mapping) == json.loads(replacement)
    watch = RowTransferWatch(
        monkeypatch,
        {"adoption-mapping": mapping},
        replacements={"adoption-mapping": replacement},
    )
    engine, outcome, returned = case.operator_engine(), LedgerOutcome(), []
    try:
        if extra_whitespace:
            with (
                pytest.raises(MigrationRefused, match="^adoption_metadata_drift$"),
                ledger_transaction(engine, outcome, work=LedgerWork()) as connection,
            ):
                returned.append(inspect_ledger_state(connection))
            assert returned == [] and outcome.rollback_acknowledged
        else:
            with ledger_transaction(engine, outcome, work=LedgerWork()) as connection:
                returned.append(inspect_ledger_state(connection))
            assert returned[0].model_dump(mode="json") == case.expected
            assert outcome.commit_acknowledged
        assert not outcome.cleanup_failed
        assert watch.hits
        record_property("mapping_transport_delta", str(extra_whitespace))
    finally:
        engine.dispose()
    drain(pg)
    assert postgres_snapshot(case.engine) == before
    drain(pg)


@pytest.mark.parametrize("reader_case", [COMPLETE_CASES[1]], indirect=True)
@pytest.mark.parametrize("expire", [False, True], ids=["unexpired-control", "pure-loop-expiry"])
def test_complete_reader_stops_expired_pure_reducer_and_cleans_up(
    reader_case, reader_trace, monkeypatch, record_property, expire
):
    from agent_rewind.migrations import ownership_lineage
    from agent_rewind.migrations.ledger_inspection import inspect_ledger_state

    case, trace = reader_case, reader_trace
    study_job, study = "e" * 32, "f" * 32
    source_run = "1" * 32
    metadata = {
        "job_id": study_job,
        "source_run": source_run,
        "request": {"run_id": source_run},
        "candidates": [{"pairs": [{} for _ in range(64)]}],
        "confirmation": None,
    }
    with case.engine.begin() as connection:
        project = connection.execute(
            text(
                "SELECT project_id FROM resource_scopes "
                "WHERE resource_kind='run' AND resource_id=:source"
            ),
            {"source": source_run},
        ).scalar_one()
        connection.execute(
            text(
                "INSERT INTO jobs (id,kind,created,payload,status,cancel,budget,reserved,"
                "payload_version) VALUES (:id,'study',1.0,'opaque','succeeded',false,1,0,1)"
            ),
            {"id": study_job},
        )
        connection.execute(
            text("INSERT INTO records (id,kind,created,data) VALUES (:id,'study',1.0,:data)"),
            {"id": study, "data": json.dumps(metadata)},
        )
        for kind, identifier in (("job", study_job), ("study", study)):
            connection.execute(
                text(
                    "INSERT INTO resource_scopes (resource_kind,resource_id,project_id) "
                    "VALUES (:kind,:identifier,:project)"
                ),
                {"kind": kind, "identifier": identifier, "project": project},
            )
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    before = sqlite_snapshot(case.path)
    clock, probes = [0.0], []
    original = ownership_lineage._unique_object

    class ObservedPair(dict):
        def __contains__(self, key):
            if key in ("control_run", "treatment_run"):
                probes.append(key)
                trace.phase = "pure-reducer"
                if expire:
                    clock[0] = 121.0
            return super().__contains__(key)

    def observed_object(items):
        value = original(items)
        return ObservedPair(value) if value == {} else value

    # Preserve parsing and values; observe actual arm membership checks only.
    # The clock expires after the first valid pair starts, not before inspection.
    monkeypatch.setattr(ownership_lineage, "_unique_object", observed_object)
    monkeypatch.setattr(ledger_work, "monotonic", lambda: clock[0])
    engine, work, outcome = case.operator_engine(), LedgerWork(), LedgerOutcome()
    returned = []
    raw = None
    try:
        if expire:
            with (
                pytest.raises(MigrationRefused, match="^migration_busy$"),
                ledger_transaction(engine, outcome, work=work) as connection,
            ):
                trace.phase = "reader"
                raw = connection.connection.driver_connection
                returned.append(inspect_ledger_state(connection))
            assert returned == [] and probes == ["control_run", "treatment_run"]
            assert outcome.rollback_acknowledged and not outcome.commit_attempted
        else:
            with ledger_transaction(engine, outcome, work=work) as connection:
                trace.phase = "reader"
                raw = connection.connection.driver_connection
                returned.append(inspect_ledger_state(connection))
            assert returned[0].model_dump(mode="json") == case.expected
            assert probes == ["control_run", "treatment_run"] * 64
            assert outcome.commit_acknowledged
        assert not outcome.cleanup_failed
        assert work.observed_ordinary <= 2028 and len(work.cleanup_observations) <= 8
        assert engine.pool.checkedout() == 0 and raw is not None
        assert not raw.in_transaction
        cursor = raw.execute("PRAGMA busy_timeout")
        try:
            assert cursor.fetchone() == (work.previous_timeout,)
        finally:
            cursor.close()
        assert sqlite_snapshot(case.path) == before
        record_property(
            "pure_reducer_boundary",
            json.dumps(
                {
                    "expired": expire,
                    "actual_arm_probes": len(probes),
                    "returned_states": len(returned),
                    "total_ordinary": work.observed_ordinary,
                    "cleanup_observations": work.cleanup_observations,
                }
            ),
        )
    finally:
        engine.dispose()
    with pytest.raises(sqlite3.ProgrammingError):
        raw.execute("SELECT 1")
