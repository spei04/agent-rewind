"""Require every job and the exact bounded current-attempt core coverage union."""

import hashlib
import http.client
import json
import os
import re
import signal
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from scripts.ci_receipts import (
    MAX_API_BYTES,
    MAX_ARCHIVE_BYTES,
    load_json,
    observe_identity,
    require,
    tracked_tests,
    unpack_receipt,
    validate_artifacts,
    validate_campaign,
    validate_expectations,
)

REQUIRED_JOBS = frozenset({"core", "isolation", "security", "package"})
API_ROOT = "https://api.github.com"
TRANSPORT_SECONDS = 120


def check_results(results: object) -> None:
    if not isinstance(results, dict) or set(results) != REQUIRED_JOBS:
        raise ValueError("CI gate received an unexpected required-job set")
    for name, result in results.items():
        if not isinstance(result, dict) or result.get("result") != "success":
            raise ValueError(f"Required job did not succeed: {name}")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class ArtifactReader:
    def __init__(self, token, *, clock=time.monotonic, opener=None):
        require(type(token) is str and bool(token), "Missing read token")
        self.token = token
        self.clock = clock
        self.deadline = clock() + TRANSPORT_SECONDS
        self.opener = opener or urllib.request.build_opener(NoRedirect())

    def __enter__(self):
        self.previous_handler = signal.getsignal(signal.SIGALRM)
        require(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), "Existing transport alarm")

        def expired(_signal, _frame):
            raise TimeoutError("Artifact transport deadline exceeded")

        signal.signal(signal.SIGALRM, expired)
        signal.setitimer(signal.ITIMER_REAL, self.deadline - self.clock())
        return self

    def __exit__(self, _kind, _value, _traceback):
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, self.previous_handler)

    def remaining(self):
        left = self.deadline - self.clock()
        require(left > 0, "Artifact transport deadline exceeded")
        return min(10, left)

    def read(self, response, bound):
        require(
            response.headers.get("Content-Encoding", "identity") == "identity",
            "Unexpected transport encoding",
        )
        declared = response.headers.get("Content-Length")
        if declared is not None:
            require(
                declared.isdecimal() and int(declared) <= bound, "Transport length exceeds bound"
            )
        chunks, size = [], 0
        while True:
            self.remaining()
            chunk = response.read1(min(65536, bound + 1 - size))
            if not chunk:
                break
            size += len(chunk)
            require(size <= bound, "Transport bytes exceed bound")
            chunks.append(chunk)
        self.remaining()
        return b"".join(chunks)

    def api_request(self, path):
        # The token is never attached to an artifact storage redirect.
        endpoint = (
            r"/repos/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/actions/"
            r"(?:runs/[1-9][0-9]*/artifacts\?per_page=100|artifacts/[1-9][0-9]*/zip)"
        )
        require(type(path) is str and re.fullmatch(endpoint, path), "Invalid API path")
        # Fixed HTTPS API host plus the exact endpoint grammar above.
        return urllib.request.Request(  # noqa: S310
            API_ROOT + path,
            headers={
                "Accept": "application/vnd.github+json",
                "Accept-Encoding": "identity",
                "Authorization": "Bearer " + self.token,
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )

    def list_artifacts(self, identity):
        path = (
            f"/repos/{identity['repository']}/actions/runs/{identity['run_id']}"
            "/artifacts?per_page=100"
        )
        try:
            with self.opener.open(self.api_request(path), timeout=self.remaining()) as response:
                require(response.status == 200, "Unexpected artifact listing status")
                return load_json(self.read(response, MAX_API_BYTES), MAX_API_BYTES)
        except (urllib.error.URLError, OSError) as error:
            raise ValueError("Artifact listing transport failed") from error

    def download(self, repository, artifact):
        path = f"/repos/{repository}/actions/artifacts/{artifact['id']}/zip"
        location = None
        try:
            with self.opener.open(self.api_request(path), timeout=self.remaining()):
                raise ValueError("Artifact API did not return a redirect")
        except urllib.error.HTTPError as error:
            try:
                require(error.code == 302, "Unexpected artifact download status")
                location = error.headers.get("Location")
            finally:
                error.close()
        except (urllib.error.URLError, OSError):
            raise ValueError("Artifact download request failed") from None
        require(type(location) is str and len(location) <= 8192, "Missing bounded redirect")
        require(
            all(33 <= ord(character) <= 126 for character in location),
            "Unsafe artifact redirect text",
        )
        try:
            parsed = urllib.parse.urlsplit(location)
            safe = (
                parsed.scheme == "https"
                and parsed.hostname is not None
                and parsed.port in (None, 443)
                and parsed.username is None
                and parsed.password is None
            )
        except ValueError:
            raise ValueError("Unsafe artifact redirect") from None
        require(safe, "Unsafe artifact redirect")
        require(
            parsed.hostname.endswith((".blob.core.windows.net", ".githubusercontent.com")),
            "Unexpected artifact storage host",
        )
        # HTTPS scheme/host/port and absence of credentials were checked above.
        request = urllib.request.Request(  # noqa: S310
            location, headers={"Accept-Encoding": "identity"}
        )
        try:
            # NoRedirect also rejects a second storage hop; no Authorization header is present.
            with self.opener.open(request, timeout=self.remaining()) as response:
                require(response.status == 200, "Unexpected artifact storage status")
                data = self.read(response, MAX_ARCHIVE_BYTES)
        except (urllib.error.URLError, OSError, http.client.HTTPException):
            # Signed URLs never appear in diagnostic exception chains.
            raise ValueError("Artifact storage transport failed") from None
        require(
            "sha256:" + hashlib.sha256(data).hexdigest() == artifact["digest"],
            "Artifact archive digest differs",
        )
        return data


def main():
    check_results(load_json(os.environ["CI_JOB_RESULTS"].encode("utf-8"), MAX_API_BYTES))
    root = Path(__file__).resolve().parents[1]
    identity = observe_identity(root, os.environ)
    tracked = tracked_tests(root)
    expectations = load_json(
        (root / "scripts/ci_core_expectations.json").read_bytes(), MAX_API_BYTES
    )
    validate_expectations(expectations, tracked)
    with ArtifactReader(os.environ["GITHUB_TOKEN"]) as reader:
        artifacts, ignored = validate_artifacts(reader.list_artifacts(identity), identity)
        receipts = [
            unpack_receipt(reader.download(identity["repository"], item)) for item in artifacts
        ]
    validate_campaign(receipts, identity, expectations, tracked)
    print(json.dumps({"ignored_prior_attempt_artifacts": ignored}, separators=(",", ":")))
    print("Every required job and all three exact core coverage receipts succeeded.")


if __name__ == "__main__":
    main()
