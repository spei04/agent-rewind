import hashlib
import http.client
import json
import threading
from contextlib import contextmanager

import pytest

from scripts import recorded_walkthrough as recorded

RUN = "a" * 32
FILE_ROUTE = f"/api/runs/{RUN}/files/3"


@pytest.fixture
def recording(tmp_path):
    data = {
        "schema": "agent-rewind-recorded-walkthrough-v1",
        "source_commit": recorded.SOURCE,
        "viewer_commit": "b" * 40,
        "assets": {
            name: hashlib.sha256((recorded.WEB / name).read_bytes()).hexdigest()
            for name in recorded.ASSETS
        },
        "responses": {
            "/api/me": recorded.IDENTITY,
            "/api/runs": [],
            "/api/studies": [],
            "/api/jobs": [],
            FILE_ROUTE: [{"path": "invoice.py"}],
            FILE_ROUTE + "?path=invoice.py": {"content": "reviewed fixture", "truncated": False},
        },
    }
    path = tmp_path / "recording.json"
    path.write_text(json.dumps(data))
    path.chmod(0o600)
    return path


@contextmanager
def running(recording, **kwargs):
    with recorded.make_server(recording, port=0, **kwargs) as server:
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            assert server.server_address[0] == "127.0.0.1"
            yield server.server_port
        finally:
            server.shutdown()
            thread.join(timeout=3)
            assert not thread.is_alive()


def request(port, method, path, *, host=None, origin=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        headers = {} if host is None else {"Host": host}
        if origin is not None:
            headers["Origin"] = origin
        connection.request(method, path, headers=headers)
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def test_recorded_view_preserves_assets_and_disables_live_authority(recording):
    with running(recording) as port:
        status, headers, body = request(port, "GET", "/")
        assert status == 200
        banner = recorded.historical_banner("b" * 40)
        assert body.replace(banner, b"", 1) == (recorded.WEB / "index.html").read_bytes()
        assert b"Recorded 6 Oct 2026" in body and b"Read-only" in body
        assert b"<details><summary>Recording details</summary>" in body
        assert b"Historical controlled fault injection" in body
        assert b"position:sticky" in banner and b"grid-template-columns:1fr auto" in banner
        assert b"height:" not in banner and b"padding-top:" not in banner
        assert b">LIVE<" not in body and b"available allowance unknown" in body
        assert b"$36.567974" in body and b"five jobs" in body and b"bill" in body
        assert b"New provider calls: 0" in body
        assert headers["Cache-Control"] == "no-store"
        assert "connect-src 'self'" in headers["Content-Security-Policy"]
        for name in ("app.js", "style.css"):
            status, _, content = request(port, "GET", "/static/" + name)
            assert status == 200 and content == (recorded.WEB / name).read_bytes()
        status, _, identity = request(port, "GET", "/api/me")
        assert status == 200 and json.loads(identity) == recorded.IDENTITY
        status, _, content = request(port, "GET", FILE_ROUTE + "?path=invoice.py")
        assert status == 200 and json.loads(content)["content"] == "reviewed fixture"


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD", "TRACE"])
def test_every_mutation_method_is_refused_including_auth(recording, method):
    with running(recording) as port:
        for path in ("/auth/logout", "/api/runs", f"/api/runs/{RUN}/branch"):
            status, _, _ = request(port, method, path)
            assert status == 405


@pytest.mark.parametrize(
    "path",
    [
        "/.env",
        "/../.env",
        "/static/../.env",
        "/static/%2e%2e/.env",
        "https://example.com/api/me",
        "/api/me?role=operator",
        "/api/runs/" + "c" * 32,
        FILE_ROUTE + "?path=../../.env",
        FILE_ROUTE + "?path=invoice.py&path=.env",
        FILE_ROUTE + "?path=file%3A%2F%2F%2Fetc%2Fpasswd",
    ],
)
def test_unknown_urls_and_files_never_resolve_outside_finite_map(recording, path):
    with running(recording) as port:
        status, _, _ = request(port, "GET", path, host=f"127.0.0.1:{port}")
        assert status == 404


@pytest.mark.parametrize("header", ["host", "origin"])
def test_foreign_host_or_origin_is_refused(recording, header):
    with running(recording) as port:
        status, _, _ = request(port, "GET", "/api/me", **{header: "http://attacker.example"})
        assert status == 403


@pytest.mark.parametrize(
    "change", ["permissions", "symlink", "operator", "asset", "secret", "route"]
)
def test_manifest_privacy_and_identity_are_checked_before_serving(recording, change):
    data = json.loads(recording.read_text())
    if change == "permissions":
        recording.chmod(0o644)
    elif change == "symlink":
        link = recording.with_name("link.json")
        link.symlink_to(recording)
        recording = link
    else:
        if change == "operator":
            data["responses"]["/api/me"]["role"] = "operator"
        elif change == "asset":
            data["assets"]["app.js"] = "0" * 64
        elif change == "secret":
            data["responses"]["/api/runs"] = [{"api_key": "synthetic-sensitive-value"}]
        else:
            data["responses"]["/.env"] = {"value": "never exposed"}
        recording.write_text(json.dumps(data))
    with pytest.raises((ValueError, OSError)):
        recorded.make_server(recording, port=0)


def test_duplicate_and_nonfinite_manifest_values_refuse(recording):
    for raw in ('{"schema":1,"schema":2}', '{"value":NaN}'):
        recording.write_text(raw)
        with pytest.raises(ValueError):
            recorded.load_recording(recording)


def test_explicit_ssh_forward_accepts_only_the_exact_loopback_origin(recording):
    with running(recording, browser_port=18081) as port:
        status, _, _ = request(
            port, "GET", "/api/me", host="127.0.0.1:18081", origin="http://127.0.0.1:18081"
        )
        assert status == 200
        status, _, _ = request(port, "GET", "/api/me", host="127.0.0.1:18082")
        assert status == 403
        status, _, _ = request(
            port, "GET", "/api/me", host="127.0.0.1:18081", origin="http://attacker.example"
        )
        assert status == 403
