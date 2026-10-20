"""Quiet ordinary autovacuum only in the pinned, disposable Actions test service.

This is CI setup, never an operator command for an arbitrary database. The product
still refuses every competing backend. PostgreSQL may launch anti-wraparound
workers even with autovacuum off; this fresh, short-lived cluster is not a
general guarantee of maintenance-free operation.
"""

import json
import os
import re
import subprocess
import time
from collections.abc import Mapping

IMAGE = "postgres:16-alpine@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea"
LABEL = "io.agent-rewind.ci-run"
MAX_SECONDS = 30.0
COMMAND_SECONDS = 5.0
OBSERVE = (
    "SELECT setting, source, pending_restart, "
    "(SELECT count(*) FROM pg_catalog.pg_stat_activity "
    "WHERE backend_type = 'autovacuum worker') "
    "FROM pg_catalog.pg_settings WHERE name = 'autovacuum'"
)


class SetupRefused(ValueError):
    """Fixed diagnostics only; subprocess output must not enter CI errors."""


def _run(arguments: list[str], deadline: float) -> str:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise SetupRefused("ci_postgres_setup_timeout")
    try:
        result = subprocess.run(  # noqa: S603 - fixed commands; validated container ID, no shell
            arguments,
            check=True,
            capture_output=True,
            text=True,
            timeout=min(COMMAND_SECONDS, remaining),
        )
    except (OSError, subprocess.SubprocessError):
        raise SetupRefused("ci_postgres_command_failed") from None
    if len(result.stdout) > 4096:
        raise SetupRefused("ci_postgres_response_invalid")
    return result.stdout.strip()


def configure(environment: Mapping[str, str]) -> None:
    """Require the current Actions service identity before any SQL mutation."""
    container = environment.get("REWIND_CI_POSTGRES_CONTAINER", "")
    run = environment.get("GITHUB_RUN_ID", "")
    attempt = environment.get("GITHUB_RUN_ATTEMPT", "")
    if (
        environment.get("GITHUB_ACTIONS") != "true"
        or re.fullmatch(r"[0-9a-f]{64}", container) is None
        or re.fullmatch(r"[1-9][0-9]{0,19}", run) is None
        or re.fullmatch(r"[1-9][0-9]{0,9}", attempt) is None
    ):
        raise SetupRefused("ci_postgres_identity_required")
    deadline = time.monotonic() + MAX_SECONDS
    template = (
        "{{json .Config.Image}}\n"
        '{{json (index .Config.Labels "' + LABEL + '")}}\n'
        "{{json .State.Running}}"
    )
    inspected = _run(["docker", "inspect", "--format", template, container], deadline)
    try:
        identity = [json.loads(line) for line in inspected.splitlines()]
    except (ValueError, RecursionError):
        raise SetupRefused("ci_postgres_identity_mismatch") from None
    if len(identity) != 3 or identity[:2] != [IMAGE, f"{run}-{attempt}"] or identity[2] is not True:
        raise SetupRefused("ci_postgres_identity_mismatch")
    # Unix socket inside the verified service; no externally supplied DSN,
    # inherited psql startup file or server is used.
    command = [
        "docker",
        "exec",
        container,
        "psql",
        "-X",
        "-w",
        "-h",
        "/var/run/postgresql",
        "-p",
        "5432",
        "-U",
        "postgres",
        "-d",
        "postgres",
        "-v",
        "ON_ERROR_STOP=1",
        "-A",
        "-t",
        "-F",
        "|",
        "-c",
    ]
    # Separate commands: ALTER SYSTEM is forbidden inside a transaction block.
    _run([*command, "ALTER SYSTEM SET autovacuum = off"], deadline)
    if _run([*command, "SELECT pg_catalog.pg_reload_conf()"], deadline) != "t":
        raise SetupRefused("ci_postgres_reload_failed")
    while True:
        observation = _run([*command, OBSERVE], deadline)
        if observation == "off|configuration file|f|0":
            return
        if re.fullmatch(r"(on|off)\|[^|\r\n]{1,64}\|(t|f)\|[0-9]{1,8}", observation) is None:
            raise SetupRefused("ci_postgres_observation_invalid")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise SetupRefused("ci_postgres_setup_timeout")
        # Wait for observed effective reload/ordinary worker exit, never retry a
        # migration or kill a backend. No fixture runs before this setup succeeds.
        time.sleep(min(0.1, remaining))


def main() -> int:
    try:
        configure(os.environ)
    except SetupRefused as error:
        print(str(error))
        return 1
    print("ci_postgres_ordinary_autovacuum_off_verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
