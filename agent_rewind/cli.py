import argparse
import json
import os
import secrets
import tempfile
from pathlib import Path

import httpx
import uvicorn
from cryptography.fernet import Fernet

from .config import Settings
from .database import Database


def main() -> None:
    parser = argparse.ArgumentParser(description="Agent Rewind experiment service")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="Create local secret placeholders and initialize metadata")
    commands.add_parser("migrate", help="Initialize the database schema")
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
    settings = Settings()
    if args.command in {"init", "migrate"}:
        Database(settings).migrate()
        print("Metadata schema initialized.")
    elif args.command == "serve":
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
        assert store.get(store.put(b"health check")) == b"health check"
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
