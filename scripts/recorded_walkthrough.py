"""Serve a reviewed, private recording with the existing workbench; never run agents."""

import argparse
import hashlib
import json
import os
import re
import stat
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit

MAX_BYTES = 8 * 1024 * 1024
MAX_ROUTES = 512
WEB = Path(__file__).resolve().parents[1] / "agent_rewind" / "web"
ASSETS = {"index.html": "text/html", "app.js": "text/javascript", "style.css": "text/css"}
IDENTITY = {"subject": "Historical recording · 2026-10-06", "role": "viewer", "csrf": ""}
SOURCE = "05fd44be4a0c8125c502baa73b9cc55b1bef394f"
FORBIDDEN_KEYS = {"api_key", "authorization", "password", "secret", "token", "proposed"}
ID = r"[0-9a-f]{32}"


def route_key(target):
    """Normalize only the two known query forms; never interpret a filesystem path."""
    if type(target) is not str or len(target) > 2048 or any(ord(c) < 32 for c in target):
        raise ValueError("invalid_recorded_route")
    value = urlsplit(target)
    if value.scheme or value.netloc or value.fragment:
        raise ValueError("invalid_recorded_route")
    pairs = parse_qsl(value.query, keep_blank_values=True, strict_parsing=True, max_num_fields=2)
    query = dict(pairs)
    if len(query) != len(pairs):
        raise ValueError("invalid_recorded_route")
    if value.path in {"/api/me", "/api/runs", "/api/studies", "/api/jobs"} and not query:
        return value.path
    if re.fullmatch(rf"/api/runs/{ID}", value.path) and not query:
        return value.path
    if re.fullmatch(rf"/api/runs/{ID}/files/[1-9][0-9]{{0,4}}", value.path):
        if not query:
            return value.path
        if set(query) == {"path"} and 0 < len(query["path"]) <= 256:
            return value.path + "?" + urlencode(query)
    if (
        value.path == "/api/compare"
        and set(query) == {"left", "right"}
        and all(re.fullmatch(ID, query[k]) for k in query)
    ):
        return value.path + "?" + urlencode(sorted(query.items()))
    raise ValueError("invalid_recorded_route")


def _private_json(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as handle:
        info = os.fstat(handle.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_uid != os.getuid()
            or info.st_size > MAX_BYTES
        ):
            raise ValueError("recording_must_be_owner_private")
        raw = handle.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("recording_too_large")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate_recording_key")
            result[key] = value
        return result

    def nonfinite(_value):
        raise ValueError("nonfinite_recording")

    return json.loads(raw, object_pairs_hook=unique, parse_constant=nonfinite)


def _public_fields(value):
    if isinstance(value, dict):
        if any(key.lower() in FORBIDDEN_KEYS for key in value):
            raise ValueError("sensitive_recording_field")
        for child in value.values():
            _public_fields(child)
    elif isinstance(value, list):
        for child in value:
            _public_fields(child)


def load_recording(path):
    value = _private_json(path)
    if (
        type(value) is not dict
        or set(value) != {"schema", "source_commit", "viewer_commit", "assets", "responses"}
        or value["schema"] != "agent-rewind-recorded-walkthrough-v1"
        or value["source_commit"] != SOURCE
        or type(value["viewer_commit"]) is not str
        or not re.fullmatch(r"[0-9a-f]{40}", value["viewer_commit"])
        or type(value["assets"]) is not dict
        or set(value["assets"]) != set(ASSETS)
        or type(value["responses"]) is not dict
        or not 4 <= len(value["responses"]) <= MAX_ROUTES
    ):
        raise ValueError("invalid_recording_manifest")
    assets = {}
    for name, content_type in ASSETS.items():
        raw = (WEB / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != value["assets"][name]:
            raise ValueError("viewer_asset_mismatch")
        assets[name] = (content_type, raw)
    responses = value["responses"]
    if responses.get("/api/me") != IDENTITY:
        raise ValueError("recording_must_be_viewer_only")
    if any(
        type(responses.get(key)) is not list for key in ("/api/runs", "/api/studies", "/api/jobs")
    ):
        raise ValueError("missing_recording_lists")
    frozen = {}
    for key, payload in responses.items():
        if route_key(key) != key:
            raise ValueError("noncanonical_recorded_route")
        _public_fields(payload)
        frozen[key] = json.dumps(payload, allow_nan=False, separators=(",", ":")).encode()
    return value["viewer_commit"], assets, frozen


def historical_banner(viewer_commit):
    # This is an overlay on unchanged checked-in assets, not a product readiness flag.
    return (
        "<style>body{padding-top:220px!important}body>aside{top:220px!important}"
        "#recording-notice{position:fixed;display:block;top:0;left:0;right:0;"
        "width:100%;height:220px;overflow:auto;z-index:10000;padding:14px 24px;"
        "box-sizing:border-box;background:#17213a;color:#fff;font:14px/1.4 sans-serif}"
        "#recording-notice p{margin:3px 0}"
        "@media(max-width:800px){body>aside{top:auto!important}}</style>"
        '<div id="recording-notice" role="note">'
        "<strong>Historical controlled fault injection · 2026-10-06 · READ ONLY</strong>"
        "<p>No live execution or new provider calls. "
        "Branch, investigate and all writes are disabled."
        " “Fresh trial effect” below describes the eight confirmation pairs "
        "executed in October.</p>"
        "<p>8 confirmation pairs: controls 0/8, treatment 8/8; 95% interval 15.65–100 percentage "
        "points. This is not a natural-failure benchmark or a current-source execution.</p>"
        "<p>$36.567974 historically held/reserved across five jobs; "
        "bill, invoice, other exposure and available allowance unknown."
        " Usage-derived ceiling: $1.668527 for 67 recorded calls, "
        "excluding three proposal calls. This is not an invoice."
        " New provider calls: 0.</p>"
        f"<p>Recorded execution source: {SOURCE[:8]}; current viewer assets: {viewer_commit[:8]}."
        " Private review only; no public sharing.</p></div>"
    ).encode()


def make_server(recording, *, port=8081, browser_port=None):
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError("invalid_loopback_port")
    if browser_port is not None and (
        type(browser_port) is not int or not 1 <= browser_port <= 65535
    ):
        raise ValueError("invalid_browser_port")
    viewer_commit, assets, responses = load_recording(recording)
    html = assets["index.html"][1]
    live_badge = b'<span class="mono">LIVE</span>'
    if html.count(b"<body>") != 1 or html.count(live_badge) != 1:
        raise ValueError("unsupported_viewer_document")
    html = html.replace(live_badge, b'<span class="mono">RECORDED</span>', 1)
    html = html.replace(b"<body>", b"<body>" + historical_banner(viewer_commit), 1)
    static = {
        "/": ("text/html; charset=utf-8", html),
        "/static/app.js": ("text/javascript; charset=utf-8", assets["app.js"][1]),
        "/static/style.css": ("text/css; charset=utf-8", assets["style.css"][1]),
    }

    class RecordedHandler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(2)

        def log_message(self, _format, *_args):
            # Request URLs and recorded identifiers stay out of console/access logs.
            pass

        def send_payload(self, status, content_type, body):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
            )
            self.send_header("Connection", "close")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
            self.close_connection = True

        def do_GET(self):
            allowed_hosts = {
                f"127.0.0.1:{self.server.server_port}",
                f"localhost:{self.server.server_port}",
            }
            if browser_port is not None:
                allowed_hosts.update({f"127.0.0.1:{browser_port}", f"localhost:{browser_port}"})
            origins = {f"http://{host}" for host in allowed_hosts}
            if (
                self.headers.get_all("Host", []) != [self.headers.get("Host")]
                or self.headers.get("Host") not in allowed_hosts
                or self.headers.get("Origin") not in {None, *origins}
            ):
                self.send_payload(403, "application/json", b'{"detail":"Loopback host required"}')
                return
            if self.path in static:
                content_type, body = static[self.path]
                self.send_payload(200, content_type, body)
                return
            try:
                key = route_key(self.path)
            except ValueError:
                key = None
            body = responses.get(key)
            if body is None:
                self.send_payload(404, "application/json", b'{"detail":"Not in this recording"}')
            else:
                self.send_payload(200, "application/json", body)

        def refuse_write(self):
            self.send_payload(
                405, "application/json", b'{"detail":"Historical recording is read-only"}'
            )

        do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = do_HEAD = do_TRACE = refuse_write

    # No host option: this helper cannot expose the private recording on a public bind.
    return HTTPServer(("127.0.0.1", port), RecordedHandler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recording", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8081)
    parser.add_argument("--browser-port", type=int, help="Exact local SSH-forward port")
    args = parser.parse_args()
    with make_server(args.recording, port=args.port, browser_port=args.browser_port) as server:
        print(f"Private historical recording: http://127.0.0.1:{server.server_port}/", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
