"""Native contention protocol and cleanup confined to one command's resources."""

from contextlib import contextmanager
from types import SimpleNamespace

import ledger_recovery_postgres_fixture as recovery
from ledger_competing_process import CommandGroup, Conversation


class NativeConversation(Conversation):
    def __init__(self, identity):
        super().__init__(identity)
        if identity["role"] == "loser":
            self.state = "held"

    def accept(self, message):
        attestation = self.identity["role"] == "loser" and self.sequence == 1
        super().accept(message)
        if attestation:
            self.state = "continue"


class NativeCommandGroup(CommandGroup):
    message_limit = 12
    conversation_type = NativeConversation


def close_owned(engine, handles, record):
    """Always dispose only supplied owned resources; any rescue fails the case."""
    rescued, errors = [], []
    try:
        for raw in handles:
            if not raw.closed:
                rescued.append(id(raw))
                try:
                    raw.close()
                    assert raw.closed
                except BaseException as error:
                    errors.append(error)
    finally:
        try:
            engine.dispose()
        except BaseException as error:
            errors.append(error)
        record(
            "scoped_cleanup",
            {
                "raw_ids": [id(raw) for raw in handles],
                "closed": [raw.closed for raw in handles],
                "rescued_raw_ids": rescued,
                "errors": [type(error).__name__ for error in errors],
                "engine_id": id(engine),
            },
        )
    if errors:
        raise BaseExceptionGroup("owned native cleanup failed", errors)
    assert rescued == [], "service left an owned raw handle requiring harness rescue"


@contextmanager
def observe_owned(fixture, patch, record_property, *, observe_writes=False):
    """Reuse native physical tracing without its target-wide drain finalizer."""
    engine = fixture.case.operator_engine()
    captured = []
    sentinel = object()

    def cleanup(actual):
        assert actual is sentinel
        handles = captured[0].trace.handles if captured else []
        close_owned(engine, handles, record_property)

    fixed = SimpleNamespace(case=SimpleNamespace(operator_engine=lambda: engine))
    with patch.context() as scoped:
        # This fresh child observes exactly one engine and has no administrative
        # control engine. Even failure cleanup cannot touch the held winner.
        scoped.setattr(recovery, "drain", cleanup)
        with recovery.observe_command(
            fixed,
            sentinel,
            scoped,
            record_property,
            label="command",
            observe_writes=observe_writes,
        ) as watch:
            captured.append(watch)
            yield watch
