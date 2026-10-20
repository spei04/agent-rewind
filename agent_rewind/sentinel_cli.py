"""Explicit doctor sentinel provisioning, independent from migrations."""


def provision_sentinel() -> None:
    from .sentinel import SentinelSettings, provision

    try:
        provision(SentinelSettings())
    except Exception:
        raise SystemExit("sentinel_install_failed") from None
    print('{"sentinel": "verified"}')
