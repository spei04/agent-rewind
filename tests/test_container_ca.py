"""Exercise the container-only trust repair without changing the host stores."""

import importlib.util
import ssl
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def module():
    spec = importlib.util.spec_from_file_location("container_ca", ROOT / "scripts/container_ca.py")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


@pytest.fixture
def stores(tmp_path, monkeypatch, module):
    ca = tmp_path / "etc/ssl/certs"
    sources = tmp_path / "usr/share/ca-certificates"
    local = tmp_path / "usr/local/share/ca-certificates"
    for path in (ca, sources, local):
        path.mkdir(parents=True)
    roots = module.certificates((ROOT / "tests/fixtures/container-ca.pem").read_bytes())
    subject_hashes = {body: f"{i:08x}" for i, body in enumerate(roots.values())}
    monkeypatch.setattr(module, "subject_hash", subject_hashes.__getitem__)
    good = {key: value for key, value in roots.items() if key != module.BAD_ROOT}
    source = sources / "emSign_ECC_Root_CA_-_G3.crt"
    source.write_bytes(roots[module.BAD_ROOT])
    bundle = ca / "ca-certificates.crt"
    pip = tmp_path / "base-pip.pem"
    config = tmp_path / "ca-certificates.conf"
    runtime = tmp_path / "runtime-certifi.pem"
    combined = b"\n".join(roots.values()) + b"\n"
    bundle.write_bytes(combined)
    pip.write_bytes(combined)
    config.write_text(module.CA_ENTRY + "\n")
    runtime.write_bytes(b"\n".join(good.values()) + b"\n")
    for i, (fingerprint, body) in enumerate(roots.items()):
        path = source if fingerprint == module.BAD_ROOT else sources / (fingerprint + ".crt")
        if not path.exists():
            path.write_bytes(body)
        (ca / f"{i:08x}.0").symlink_to(path)
    values = {
        "OS_BUNDLE": bundle,
        "CAPATH": ca,
        "CA_SOURCE": source,
        "CA_CONFIG": config,
        "PIP_BUNDLE": pip,
        "ALLOWED_ROOTS": (ca, sources, local),
        "EXPECTED": {
            "os_before": module.signature(set(roots)),
            "pip_before": module.signature(set(roots)),
            "os_after": module.signature(set(good)),
            "pip_after": module.signature(set(good)),
            "runtime_after": module.signature(set(good)),
        },
    }
    for name, value in values.items():
        monkeypatch.setattr(module, name, value)
    monkeypatch.setattr(
        module.ssl,
        "get_default_verify_paths",
        lambda: SimpleNamespace(cafile=str(bundle), capath=str(ca)),
    )
    pip_configs = {
        "global": tmp_path / "etc/pip.conf",
        "global_xdg": tmp_path / "etc/xdg/pip/pip.conf",
        "base_prefix": tmp_path / "base-prefix/pip.conf",
        "prefix": tmp_path / "prefix/pip.conf",
        "user": tmp_path / "home/.config/pip/pip.conf",
        "legacy_user": tmp_path / "home/.pip/pip.conf",
    }
    global_configs = {
        Path("/etc/pip.conf"): pip_configs["global"],
        Path("/etc/xdg/pip/pip.conf"): pip_configs["global_xdg"],
    }

    class FixturePaths:
        def __call__(self, *parts):
            path = Path(*parts)
            return global_configs.get(path, path)

        @staticmethod
        def home():
            return tmp_path / "home"

    # Only the two otherwise host-bound config paths need constructor redirection.
    monkeypatch.setattr(module, "Path", FixturePaths())
    monkeypatch.setattr(module.sys, "prefix", str(tmp_path / "prefix"))
    monkeypatch.setattr(module.sys, "base_prefix", str(tmp_path / "base-prefix"))
    for name in module.OVERRIDES:
        monkeypatch.delenv(name, raising=False)
    calls = []

    def regenerate(command, *, check):
        calls.append(command)
        assert command == ["/usr/sbin/update-ca-certificates", "--fresh"] and check is True
        assert not source.exists()
        for path in ca.iterdir():
            if path.is_symlink():
                path.unlink()
        for fingerprint in good:
            (ca / (subject_hashes[good[fingerprint]] + ".0")).symlink_to(
                sources / (fingerprint + ".crt")
            )
        bundle.write_bytes(b"\n".join(good.values()) + b"\n")

    monkeypatch.setattr(module.subprocess, "run", regenerate)
    # Refusal tests must start from a valid fixture, not an unrelated early failure.
    assert module.check_stores(before=True)["os"] == module.signature(set(roots))
    return SimpleNamespace(
        module=module,
        roots=roots,
        good=good,
        calls=calls,
        runtime=runtime,
        regenerate=regenerate,
        pip_configs=pip_configs,
    )


def test_removes_only_reviewed_root_and_checks_distinct_final_stores(stores):
    m = stores.module
    result = m.repair()
    assert result["os"] == result["hashed_capath"] == result["pip"] == m.signature(set(stores.good))
    assert len(stores.calls) == 1
    assert m.CA_CONFIG.read_text() == "!" + m.CA_ENTRY + "\n"
    assert set(m.certificates(m.PIP_BUNDLE.read_bytes())) == set(stores.good)
    final = m.check_stores(before=False, runtime=stores.runtime)
    assert final["runtime_certifi"] == m.signature(set(stores.good))
    assert final["removed_der_sha256"] == m.BAD_ROOT
    with pytest.raises(ValueError, match="os_before"):
        m.repair()


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "duplicate",
        "wrong_source",
        "config",
        "default",
        "escape",
        "broken",
        "loop",
        "gap",
        "wrong_hash",
    ],
)
def test_preflight_refuses_before_any_write(stores, monkeypatch, tmp_path, mutation):
    m = stores.module
    if mutation == "missing":
        m.PIP_BUNDLE.write_bytes(stores.runtime.read_bytes())
    elif mutation == "duplicate":
        m.PIP_BUNDLE.write_bytes(m.PIP_BUNDLE.read_bytes() + stores.roots[m.BAD_ROOT] + b"\n")
    elif mutation == "wrong_source":
        m.CA_SOURCE.write_bytes(next(iter(stores.good.values())))
    elif mutation == "config":
        m.CA_CONFIG.write_text("# disabled without review\n")
    elif mutation == "default":
        monkeypatch.setattr(
            m.ssl,
            "get_default_verify_paths",
            lambda: SimpleNamespace(cafile=str(m.PIP_BUNDLE), capath=str(m.CAPATH)),
        )
    else:
        alias = m.CAPATH / "00000000.0"
        alias.unlink()
        if mutation == "escape":
            outside = tmp_path / "outside.pem"
            outside.write_bytes(next(iter(stores.roots.values())))
            alias.symlink_to(outside)
        elif mutation == "broken":
            alias.symlink_to(m.CAPATH / "missing.pem")
        elif mutation == "loop":
            alias.symlink_to(alias)
        elif mutation == "wrong_hash":
            (m.CAPATH / "ffffffff.0").symlink_to(m.CA_SOURCE)
        else:
            (m.CAPATH / "00000000.1").symlink_to(m.CA_SOURCE)
    before = {
        path: path.read_bytes() for path in (m.OS_BUNDLE, m.PIP_BUNDLE, m.CA_CONFIG, m.CA_SOURCE)
    }
    with pytest.raises((ValueError, OSError, ssl.SSLError)):
        m.repair()
    assert not stores.calls
    assert {path: path.read_bytes() for path in before} == before


@pytest.mark.parametrize(
    "variable",
    [
        "SSL_CERT_FILE",
        "PIP_TRUSTED_HOST",
        "UV_INSECURE_HOST",
        "PYTHONHTTPSVERIFY",
        "OPENSSL_CONF",
        "OPENSSL_CONF_INCLUDE",
        "OPENSSL_MODULES",
        "OPENSSL_ENGINES",
        "XDG_CONFIG_HOME",
        "XDG_CONFIG_DIRS",
    ],
)
def test_active_trust_override_refuses_before_writes(stores, monkeypatch, variable):
    monkeypatch.setenv(variable, "1")
    with pytest.raises(ValueError, match="overrides"):
        stores.module.repair()
    assert not stores.calls and stores.module.CA_SOURCE.exists()


@pytest.mark.parametrize("failure", ["command", "retained_root", "lost_root", "extra_alias"])
def test_regeneration_failure_never_reports_success(stores, monkeypatch, failure):
    m = stores.module

    def regenerate(command, *, check):
        if failure == "command":
            raise subprocess.CalledProcessError(1, command)
        stores.regenerate(command, check=check)
        if failure == "retained_root":
            m.OS_BUNDLE.write_bytes(m.OS_BUNDLE.read_bytes() + stores.roots[m.BAD_ROOT] + b"\n")
        elif failure == "lost_root":
            m.OS_BUNDLE.write_bytes(next(iter(stores.good.values())) + b"\n")
        else:
            (m.CAPATH / "ffffffff.0").symlink_to(
                next(path for path in m.ALLOWED_ROOTS[1].iterdir())
            )

    monkeypatch.setattr(m.subprocess, "run", regenerate)
    with pytest.raises((ValueError, subprocess.CalledProcessError)):
        m.repair()


def test_final_check_does_not_substitute_runtime_for_base_pip(stores):
    m = stores.module
    m.repair()
    m.PIP_BUNDLE.write_bytes(b"\n".join(stores.roots.values()) + b"\n")
    with pytest.raises(ValueError, match="pip_after"):
        m.check_stores(before=False, runtime=stores.runtime)


@pytest.mark.parametrize(
    "body",
    [
        b"junk",
        b"-----BEGIN CERTIFICATE-----\nYQ==\n-----END CERTIFICATE-----\n",
        b"-----BEGIN CERTIFICATE-----\n***\n-----END CERTIFICATE-----\n",
    ],
)
def test_malformed_or_non_x509_material_is_rejected(module, body):
    with pytest.raises((ValueError, ssl.SSLError)):
        module.certificates(body)


def test_input_bounds_reject_before_unbounded_parse(module, monkeypatch):
    with pytest.raises(ValueError, match="bounds"):
        module.certificates(b"x" * (module.MAX_FILE_BYTES + 1))
    monkeypatch.setattr(module, "MAX_CERTIFICATES", 1)
    with pytest.raises(ValueError, match="Too many"):
        module.certificates((ROOT / "tests/fixtures/container-ca.pem").read_bytes())


def test_optimized_python_cannot_bypass_validation():
    code = (
        "import runpy; m=runpy.run_path(" + repr(str(ROOT / "scripts/container_ca.py")) + ");"
        "m['certificates'](b'not a certificate')"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-O", "-c", code], capture_output=True, text=True, timeout=10
    )
    assert result.returncode != 0 and "Malformed certificate bundle" in result.stderr


def test_actual_openssl_subject_hash_matches_pinned_root(module):
    roots = module.certificates((ROOT / "tests/fixtures/container-ca.pem").read_bytes())
    assert module.subject_hash(roots[module.BAD_ROOT]) == "14bc7599"


@pytest.mark.parametrize("output", [b"14BC7599\n", b"14bc7599\nextra\n", b"14bc7599", b"bad\n"])
def test_subject_hash_rejects_unexpected_utility_output(module, monkeypatch, output):
    def command(argv, **kwargs):
        assert argv == ["/usr/bin/openssl", "x509", "-subject_hash", "-noout"]
        assert kwargs == dict(input=b"reviewed", capture_output=True, check=True, timeout=5)
        return SimpleNamespace(stdout=output)

    monkeypatch.setattr(module.subprocess, "run", command)
    with pytest.raises(ValueError, match="subject hash"):
        module.subject_hash(b"reviewed")


@pytest.mark.parametrize(
    "location", ["global", "global_xdg", "base_prefix", "prefix", "user", "legacy_user"]
)
def test_unreviewed_pip_configuration_refuses_before_writes(stores, location):
    m = stores.module
    config = stores.pip_configs[location]
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text("[global]\ntrusted-host = example.invalid\n")
    before = {
        path: path.read_bytes() for path in (m.OS_BUNDLE, m.PIP_BUNDLE, m.CA_CONFIG, m.CA_SOURCE)
    }
    with pytest.raises(ValueError, match="Unreviewed pip configuration"):
        m.repair()
    assert not stores.calls
    assert {path: path.read_bytes() for path in before} == before


@pytest.mark.parametrize("host_config", ["/etc/pip.conf", "/etc/xdg/pip/pip.conf"])
def test_fixture_repair_ignores_host_global_pip_configuration(stores, monkeypatch, host_config):
    original_exists = Path.exists
    host_probes = []

    def exists(path):
        if path == Path(host_config):
            host_probes.append(path)
            return True
        return original_exists(path)

    monkeypatch.setattr(Path, "exists", exists)
    m = stores.module
    assert m.repair()["os"] == m.signature(set(stores.good))
    assert len(stores.calls) == 1
    assert not host_probes


def test_capath_directory_bound_refuses_before_writes(stores, monkeypatch):
    monkeypatch.setattr(stores.module, "MAX_DIRECTORY_ENTRIES", 1)
    with pytest.raises(ValueError, match="directory exceeds bounds"):
        stores.module.repair()
    assert not stores.calls and stores.module.CA_SOURCE.exists()


@pytest.mark.parametrize("slot", ["00", "01"])
def test_noncanonical_hash_slot_refuses_before_writes(stores, slot):
    m = stores.module
    alias = m.CAPATH / "00000000.0"
    target = alias.readlink()
    alias.unlink()
    (m.CAPATH / ("00000000." + slot)).symlink_to(target)
    with pytest.raises(ValueError, match="Noncanonical"):
        m.repair()
    assert not stores.calls and m.CA_SOURCE.exists()


def test_canonical_collision_slots_preserve_every_root(stores, monkeypatch):
    m = stores.module
    monkeypatch.setattr(m, "subject_hash", lambda body: "00000000")
    for number in (1, 2):
        (m.CAPATH / f"{number:08x}.0").rename(m.CAPATH / f"00000000.{number}")
    assert m.capath_roots("os_before") == set(stores.roots)


def test_pinned_non_ascii_config_preserves_every_unrelated_byte(stores):
    m = stores.module
    original = (ROOT / "tests/fixtures/container-ca.conf").read_bytes()
    assert any(value > 127 for value in original)
    m.CA_CONFIG.write_bytes(original)
    m.repair()
    entry = m.CA_ENTRY.encode("ascii") + b"\n"
    assert original.count(entry) == 1
    assert m.CA_CONFIG.read_bytes() == original.replace(entry, b"!" + entry, 1)


@pytest.mark.parametrize("mutation", ["duplicate", "disabled"])
def test_non_ascii_config_identity_failure_precedes_every_write(stores, mutation):
    m = stores.module
    original = (ROOT / "tests/fixtures/container-ca.conf").read_bytes()
    entry = m.CA_ENTRY.encode("ascii") + b"\n"
    if mutation == "duplicate":
        original += entry
    else:
        original = original.replace(entry, b"!" + entry, 1)
    m.CA_CONFIG.write_bytes(original)
    before = {
        path: path.read_bytes() for path in (m.OS_BUNDLE, m.PIP_BUNDLE, m.CA_CONFIG, m.CA_SOURCE)
    }
    with pytest.raises(ValueError, match="source configuration"):
        m.repair()
    assert not stores.calls
    assert {path: path.read_bytes() for path in before} == before
