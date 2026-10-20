"""C05 identity and role decision contract; not a request authorization boundary."""

from types import MappingProxyType

from .migrations.schema import checksum

_READ = frozenset({"read", "list", "compare"})
_OPERATE = _READ | {"record", "branch", "study", "investigate", "cancel"}
ROLE_ACTIONS = MappingProxyType(
    {
        "viewer": _READ,
        "operator": _OPERATE,
        "maintainer": _OPERATE | {"create_key", "revoke_key"},
    }
)


def allows_project_action(role: str, action: str) -> bool:
    """Unknown/admin roles deny; callers must still verify current scope/membership."""
    return action in ROLE_ACTIONS.get(role, frozenset())


def oidc_principal_id(verified_issuer: str, verified_subject: str) -> str:
    """Call only after issuer/audience/signature/nonce/expiry verification."""
    if any(
        not isinstance(value, str) or not 1 <= len(value) <= 4096
        for value in (verified_issuer, verified_subject)
    ):
        raise ValueError("invalid_verified_identity")
    return "oidc:" + checksum({"issuer": verified_issuer, "subject": verified_subject})
