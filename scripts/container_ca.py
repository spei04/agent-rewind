"""Remove one distrusted root from the pinned container's trust stores.

Container build helper only. Expected set hashes are SHA-256 of sorted unique
lowercase DER-SHA256 hex strings joined by ASCII LF, without a terminal LF.
Remove this workaround when a reviewed upstream image fixes OS and pip trust.
"""

import argparse
import base64
import hashlib
import json
import os
import re
import ssl
import subprocess
import sys
from pathlib import Path

BAD_ROOT = "86a1ecba089c4a8d3bbe2734c612ba341d813e043cf9e8a862cd5c57a36bbe6b"
OS_BUNDLE = Path("/etc/ssl/certs/ca-certificates.crt")
CAPATH = Path("/etc/ssl/certs")
CA_SOURCE = Path("/usr/share/ca-certificates/mozilla/emSign_ECC_Root_CA_-_G3.crt")
CA_CONFIG = Path("/etc/ca-certificates.conf")
CA_ENTRY = "mozilla/emSign_ECC_Root_CA_-_G3.crt"
PIP_BUNDLE = Path("/usr/local/lib/python3.12/site-packages/pip/_vendor/certifi/cacert.pem")
ALLOWED_ROOTS = (
    Path("/etc/ssl/certs"),
    Path("/usr/share/ca-certificates"),
    Path("/usr/local/share/ca-certificates"),
)
EXPECTED = {
    "os_before": (150, "846514b720e6d4693c774f3705e46ceca836c6f9f04054c666eae8e1985d791f"),
    "os_after": (149, "f52462a29f992c63bad914e1941b5b7b5383af4cdc8d6d2f2adfcc7dd6a2f73a"),
    "pip_before": (151, "47692c1a950213bac0f52ee3e9aa4f77136f6ce7223b14babf558367b2669414"),
    "pip_after": (150, "4c673de4b3bb55be8f51941ac29bfcdf5c05cc51ad1e4fae07803cef28a6134b"),
    "runtime_after": (120, "9df06827e3a3807387370c033a9ae583eb6b42136b6ede8eb306a63a4d84dbfc"),
}
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_CERTIFICATES = 256
MAX_DIRECTORY_ENTRIES = 1024
OVERRIDES = (
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "OPENSSL_CONF",
    "OPENSSL_CONF_INCLUDE",
    "OPENSSL_MODULES",
    "OPENSSL_ENGINES",
    "XDG_CONFIG_HOME",
    "XDG_CONFIG_DIRS",
    "PIP_CERT",
    "PIP_TRUSTED_HOST",
    "PIP_CONFIG_FILE",
    "REQUESTS_CA_BUNDLE",
    "CURL_CA_BUNDLE",
    "AWS_CA_BUNDLE",
    "UV_SYSTEM_CERTS",
    "UV_NATIVE_TLS",
    "UV_INSECURE_HOST",
    "UV_NO_VERIFY",
    "PYTHONHTTPSVERIFY",
    "NODE_TLS_REJECT_UNAUTHORIZED",
)
PEM = re.compile(
    rb"(?m)^-----BEGIN CERTIFICATE-----\r?\n"
    rb"(?:[A-Za-z0-9+/=]+\r?\n)+-----END CERTIFICATE-----\r?$"
)


def read_file(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("Unexpected trust file type or size")
    with path.open("rb") as stream:
        body = stream.read(MAX_FILE_BYTES + 1)
    if len(body) > MAX_FILE_BYTES:
        raise ValueError("Trust file exceeds bounds")
    return body


def certificates(body: bytes) -> dict[str, bytes]:
    if len(body) > MAX_FILE_BYTES:
        raise ValueError("Trust file exceeds bounds")
    result = {}
    end = 0
    for match in PEM.finditer(body):
        if len(result) >= MAX_CERTIFICATES:
            raise ValueError("Too many certificates")
        if any(
            line.strip() and not line.startswith(b"#")
            for line in body[end : match.start()].splitlines()
        ):
            raise ValueError("Malformed certificate bundle")
        block = match.group()
        der = base64.b64decode(b"".join(block.splitlines()[1:-1]), validate=True)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cadata=block.decode("ascii"))
        fingerprint = hashlib.sha256(der).hexdigest()
        if fingerprint in result:
            raise ValueError("Duplicate certificate")
        result[fingerprint] = block
        end = match.end()
    if not result or any(
        line.strip() and not line.startswith(b"#") for line in body[end:].splitlines()
    ):
        raise ValueError("Malformed certificate bundle")
    return result


def signature(fingerprints: set[str]) -> tuple[int, str]:
    return len(fingerprints), hashlib.sha256(
        "\n".join(sorted(fingerprints)).encode("ascii")
    ).hexdigest()


def require_set(fingerprints: set[str], expected: str) -> None:
    if signature(fingerprints) != EXPECTED[expected]:
        raise ValueError(f"Unexpected {expected} trust set")


def defaults() -> dict[str, str]:
    if any(os.environ.get(name) for name in OVERRIDES):
        raise ValueError("Trust overrides are not permitted")
    configs = (
        Path("/etc/pip.conf"),
        Path("/etc/xdg/pip/pip.conf"),
        Path(sys.base_prefix) / "pip.conf",
        Path(sys.prefix) / "pip.conf",
        Path.home() / ".config/pip/pip.conf",
        Path.home() / ".pip/pip.conf",
    )
    if any(path.exists() for path in configs):
        raise ValueError("Unreviewed pip configuration")
    paths = ssl.get_default_verify_paths()
    if not paths.cafile or not paths.capath:
        raise ValueError("Missing OpenSSL default trust paths")
    if Path(paths.cafile).resolve(strict=True) != OS_BUNDLE:
        raise ValueError("Unexpected OpenSSL default cafile")
    if Path(paths.capath).resolve(strict=True) != CAPATH:
        raise ValueError("Unexpected OpenSSL default capath")
    return {"cafile": str(OS_BUNDLE), "capath": str(CAPATH)}


def resolve_alias(path: Path) -> Path:
    seen = set()
    for _ in range(16):
        path = Path(os.path.normpath(path))
        if not any(path.is_relative_to(root) for root in ALLOWED_ROOTS):
            raise ValueError("Certificate alias escapes trusted directories")
        if path in seen:
            raise ValueError("Certificate alias loop")
        seen.add(path)
        if not path.is_symlink():
            resolved = path.resolve(strict=True)
            if not any(resolved.is_relative_to(root) for root in ALLOWED_ROOTS):
                raise ValueError("Certificate alias escapes trusted directories")
            return resolved
        target = path.readlink()
        path = target if target.is_absolute() else path.parent / target
    raise ValueError("Certificate alias exceeds hop bound")


def subject_hash(body: bytes) -> str:
    # OpenSSL's lazy capath lookup requires the subject hash, not arbitrary aliases.
    result = subprocess.run(  # noqa: S603
        ["/usr/bin/openssl", "x509", "-subject_hash", "-noout"],
        input=body,
        capture_output=True,
        check=True,
        timeout=5,
    )
    value = result.stdout.decode("ascii")
    if not re.fullmatch(r"[0-9a-f]{8}\n", value):
        raise ValueError("Unexpected OpenSSL subject hash")
    return value.rstrip("\n")


def capath_roots(expected: str) -> set[str]:
    entries = []
    for path in CAPATH.iterdir():
        entries.append(path)
        if len(entries) > MAX_DIRECTORY_ENTRIES:
            raise ValueError("Certificate directory exceeds bounds")
    roots = set()
    slots: dict[str, list[int]] = {}
    for path in entries:
        match = re.fullmatch(r"([0-9a-f]{8})\.(\d+)", path.name)
        if not match:
            continue
        if not re.fullmatch(r"0|[1-9][0-9]*", match[2]):
            raise ValueError("Noncanonical certificate hash slot")
        values = certificates(read_file(resolve_alias(path)))
        if len(values) != 1 or roots.intersection(values):
            raise ValueError("Unexpected hashed certificate alias")
        if subject_hash(next(iter(values.values()))) != match[1]:
            raise ValueError("Incorrect certificate subject hash alias")
        roots.update(values)
        slots.setdefault(match[1], []).append(int(match[2]))
    if any(sorted(values) != list(range(len(values))) for values in slots.values()):
        raise ValueError("Gapped certificate hash aliases")
    require_set(roots, expected)
    return roots


def check_stores(*, before: bool, runtime: Path | None = None) -> dict[str, object]:
    paths = defaults()
    phase = "before" if before else "after"
    os_roots = set(certificates(read_file(OS_BUNDLE)))
    pip_roots = set(certificates(read_file(PIP_BUNDLE)))
    require_set(os_roots, "os_" + phase)
    require_set(pip_roots, "pip_" + phase)
    hashed = capath_roots("os_" + phase)
    result: dict[str, object] = {
        "removed_der_sha256": BAD_ROOT,
        "defaults": paths,
        "os": signature(os_roots),
        "hashed_capath": signature(hashed),
        "pip": signature(pip_roots),
        "pip_bundle": str(PIP_BUNDLE),
    }
    if runtime is not None:
        runtime_roots = set(certificates(read_file(runtime)))
        require_set(runtime_roots, "runtime_after")
        result["runtime_certifi"] = signature(runtime_roots)
        result["runtime_certifi_bundle"] = str(runtime)
    return result


def repair() -> dict[str, object]:
    # Complete preflight before the first write; a missing root is never a replay.
    check_stores(before=True)
    source = certificates(read_file(CA_SOURCE))
    if set(source) != {BAD_ROOT}:
        raise ValueError("Unexpected distrusted source certificate")
    config = read_file(CA_CONFIG)
    entry = CA_ENTRY.encode("ascii")
    if config.splitlines().count(entry) != 1 or (b"!" + entry) in config.splitlines():
        raise ValueError("Unexpected distrusted source configuration")
    pip = read_file(PIP_BUNDLE)
    pip_certificates = certificates(pip)
    if BAD_ROOT not in pip_certificates:
        raise ValueError("Distrusted pip root is absent")
    config = b"".join(
        (b"!" + line if line.rstrip(b"\r\n") == entry else line)
        for line in config.splitlines(keepends=True)
    )
    CA_CONFIG.write_bytes(config)
    CA_SOURCE.unlink()
    subprocess.run(["/usr/sbin/update-ca-certificates", "--fresh"], check=True)  # noqa: S603
    PIP_BUNDLE.write_bytes(pip.replace(pip_certificates[BAD_ROOT], b"", 1))
    return check_stores(before=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--repair", action="store_true")
    modes.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.repair:
        result = repair()
        result["event"] = "container_base_ca_repair_verified"
    else:
        # The final check runs with the installed application interpreter.
        import certifi

        result = check_stores(before=False, runtime=Path(certifi.where()))
        result["event"] = "container_final_ca_trust_verified"
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
