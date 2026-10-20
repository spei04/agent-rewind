import argparse
import json
import os
import secrets
import tempfile
from pathlib import Path

import httpx
import uvicorn
from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from .config import MigrationSettings, Settings
from .database import Database


def _migrate(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    from .migrations.inputs import read_mapping
    from .migrations.schema import HEAD, MigrationRefused
    from .migrations.service import adopt, install, schema_status, upgrade

    settings = MigrationSettings()
    action = "install" if args.command == "init" else (args.migration_action or "upgrade")
    selected = (
        (settings.database_url or settings.migration_database_url)
        if action == "status"
        else (settings.migration_database_url or settings.database_url)
    )
    if selected is None:
        parser.error("migration_database_url_required")
    try:
        url = make_url(selected.get_secret_value())
        if (
            url.get_backend_name() == "postgresql"
            and action != "status"
            and (settings.migration_database_url is None)
        ):
            parser.error("dedicated_migration_database_url_required")
        if url.get_backend_name() not in {"sqlite", "postgresql"}:
            parser.error("unsupported_database")
        if (
            url.get_backend_name() == "sqlite"
            and url.database
            and action == "install"
            and url.database != ":memory:"
        ):
            Path(url.database).parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        engine = create_engine(url, pool_pre_ping=True)
    except (ArgumentError, ImportError, ValueError, OSError):
        parser.error("invalid_migration_database_url")
    try:
        timeout = getattr(args, "lock_timeout", 5)
        if action == "status":
            result = schema_status(engine, include_source_digest=args.source_digest)
        elif action == "install":
            result = install(engine, args.installation_key, timeout_seconds=timeout)
        elif action == "adopt":
            result = adopt(
                engine,
                read_mapping(args.mapping),
                args.backup_evidence,
                args.drain_evidence,
                timeout_seconds=timeout,
            )
        else:
            result = upgrade(engine, getattr(args, "target", HEAD), timeout_seconds=timeout)
        print(json.dumps(result, sort_keys=True))
    except MigrationRefused as error:
        parser.error(error.code)
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Agent Rewind experiment service")
    commands = parser.add_subparsers(dest="command", required=True)
    initialize = commands.add_parser("init", help="Create local secret placeholders")
    initialize.add_argument("--installation-key")
    migrate = commands.add_parser("migrate", help="Explicit versioned metadata migration")
    migration_commands = migrate.add_subparsers(dest="migration_action")
    status = migration_commands.add_parser("status", help="Read revision and adoption state")
    status.add_argument("--source-digest", action="store_true")
    install_parser = migration_commands.add_parser("install", help="Install an empty database")
    install_parser.add_argument("--installation-key", required=True)
    adopt_parser = migration_commands.add_parser("adopt", help="Adopt the exact known baseline")
    adopt_parser.add_argument("--mapping", type=Path, required=True)
    adopt_parser.add_argument("--backup-evidence", required=True)
    adopt_parser.add_argument("--drain-evidence", required=True)
    upgrade_parser = migration_commands.add_parser("upgrade", help="Upgrade known versioned state")
    upgrade_parser.add_argument("--target", default="ar_0002_adoption")
    for migration_parser in (install_parser, adopt_parser, upgrade_parser):
        migration_parser.add_argument("--lock-timeout", type=int, default=5)
    serve = commands.add_parser("serve", help="Start the API and debugger")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8080)
    commands.add_parser("worker", help="Execute queued jobs")
    commands.add_parser("doctor", help="Check the database, artifact store, and sandbox runtime")
    submit = commands.add_parser("submit", help="Submit a task manifest")
    submit.add_argument("path", type=Path)
    submit.add_argument("--url", default="http://127.0.0.1:8080")
    args = parser.parse_args()
    if args.command == "init":
        path = Path(".env")
        existing = path.read_text() if path.exists() else ""
        lines = existing.splitlines()
        for name, value in {
            "REWIND_ENCRYPTION_KEY": Fernet.generate_key().decode(),
            "REWIND_BOOTSTRAP_KEY": "rw_" + secrets.token_urlsafe(32),
        }.items():
            matches = [i for i, line in enumerate(lines) if line.startswith(name + "=")]
            if not matches:
                lines.append(f"{name}={value}")
            elif not lines[matches[-1]].split("=", 1)[1].strip():
                lines[matches[-1]] = f"{name}={value}"
        fd, temporary = tempfile.mkstemp(prefix=".env.", dir=path.parent)
        try:
            with os.fdopen(fd, "w") as handle:
                handle.write("\n".join(lines) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
        path.chmod(0o600)
        print("Local secrets saved in .env. Keep this file private and back up the encryption key.")
    if args.command == "init" and not args.installation_key:
        print("Run rewind migrate install --installation-key <key> to install metadata explicitly.")
        return
    if args.command in {"init", "migrate"}:
        _migrate(parser, args)
        return
    settings = Settings()
    if args.command == "serve":
        from .api import create_app

        uvicorn.run(create_app(settings), host=args.host, port=args.port, access_log=False)
    elif args.command == "worker":
        from .worker import serve_worker

        serve_worker(settings)
    elif args.command == "doctor":
        from .artifacts import Artifacts
        from .runner import DockerRunner

        db = Database(settings)
        with db.engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")
        store = Artifacts(settings)
        if store.get(store.put(b"health check")) != b"health check":
            raise ValueError("Artifact store health check failed.")
        runner = DockerRunner(settings)
        print(
            json.dumps(
                {
                    "database": "ok",
                    "artifacts": "ok",
                    "sandbox": settings.sandbox_runtime,
                    "images": [
                        runner.resolve_image(s.strip())
                        for s in settings.allowed_images.split(",")
                        if s.strip()
                    ],
                    "model_configured": bool(settings.model_api_key and settings.model_name),
                }
            )
        )
    elif args.command == "submit":
        token = os.environ.get("REWIND_API_TOKEN", "")
        if not token:
            parser.error("Set REWIND_API_TOKEN to a scoped service API key.")
        response = httpx.post(
            args.url.rstrip("/") + "/api/runs",
            json=json.loads(args.path.read_text()),
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        response.raise_for_status()
        print(json.dumps(response.json()))
