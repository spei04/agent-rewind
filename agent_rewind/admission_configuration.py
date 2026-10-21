"""Pure, injected native-v1 configuration; no registry service or credential lookup.

The endpoint profile and revision name an immutable server-owned mapping. A later
worker must verify that mapping and all installed component/image identities;
this module does not resolve a URL, load credentials, or prove deployment state.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, NoReturn

from .admission_request import (
    MAX_CONFIG_BYTES,
    AdmissionPreparationError,
    bounded_canonical,
    decode_object,
)

MAX_IMAGE_ALIASES = 128
MAX_ALIAS_BYTES = 64 * 1024
_OPAQUE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
_DIGEST = re.compile(r"[0-9a-f]{64}")
_FIELDS = frozenset(
    {
        "schema",
        "kind",
        "image_identity",
        "endpoint_profile",
        "endpoint_revision",
        "model_revision",
        "adapter_digest",
        "prompt_digest",
        "tool_policy_digest",
        "configuration_digest",
        "processor_profile",
        "max_input_tokens",
        "max_output_tokens",
        "reasoning_effort",
        "seed_supported",
        "seed_strategy",
        "price_version",
        "input_microusd_per_million_tokens",
        "output_microusd_per_million_tokens",
    }
)
_DIGEST_FIELDS = ("adapter_digest", "prompt_digest", "tool_policy_digest", "configuration_digest")
_PROFILE_FIELDS = (
    "endpoint_profile",
    "endpoint_revision",
    "model_revision",
    "processor_profile",
    "price_version",
)
_REASONING = frozenset({"", "none", "minimal", "low", "medium", "high", "xhigh", "max"})
SEED_STRATEGY = "trial-plus-step-mod-2147483647"


def _invalid() -> NoReturn:
    raise AdmissionPreparationError("admission_configuration_invalid") from None


def _opaque(value: Any) -> bool:
    return type(value) is str and _OPAQUE.fullmatch(value) is not None


def _integer(value: Any, lower: int, upper: int) -> bool:
    return type(value) is int and lower <= value <= upper


@dataclass(frozen=True, init=False)
class NativeConfiguration:
    """Validated canonical schema-1 bytes and their externally supplied digest.

    Canonical bytes are the import format, bounded at 64 KiB before parsing.
    The configuration_digest member identifies a component/configuration input;
    it is distinct from the SHA256 of this whole object and is not a self-hash.
    All fields are required. No deployment defaults are filled from Settings.
    """

    canonical_bytes: bytes
    digest: str
    image_identity: str
    processor_profile: str

    def __init__(self, canonical_bytes: bytes, *, expected_digest: str):
        try:
            value = decode_object(
                canonical_bytes,
                limit=MAX_CONFIG_BYTES,
                limit_code="admission_configuration_limit",
            )
        except AdmissionPreparationError as error:
            if error.code == "admission_configuration_limit":
                raise
            _invalid()
        if (
            set(value) != _FIELDS
            or type(value["schema"]) is not int
            or value["schema"] != 1
            or value["kind"] != "native-v1"
            or type(value["image_identity"]) is not str
            or re.fullmatch(r"sha256:[0-9a-f]{64}", value["image_identity"]) is None
            or any(
                type(value[key]) is not str or _DIGEST.fullmatch(value[key]) is None
                for key in _DIGEST_FIELDS
            )
            or any(not _opaque(value[key]) for key in _PROFILE_FIELDS)
            or not _integer(value["max_input_tokens"], 1000, 1_000_000)
            or not _integer(value["max_output_tokens"], 1, 128_000)
            or type(value["reasoning_effort"]) is not str
            or value["reasoning_effort"] not in _REASONING
            or type(value["seed_supported"]) is not bool
            or value["seed_strategy"] != SEED_STRATEGY
            or not _integer(value["input_microusd_per_million_tokens"], 1, 2**63 - 1)
            or not _integer(value["output_microusd_per_million_tokens"], 1, 2**63 - 1)
            or type(expected_digest) is not str
            or _DIGEST.fullmatch(expected_digest) is None
        ):
            _invalid()
        encoded = bounded_canonical(
            value, limit=MAX_CONFIG_BYTES, limit_code="admission_configuration_limit"
        )
        if encoded != canonical_bytes or hashlib.sha256(encoded).hexdigest() != expected_digest:
            _invalid()
        object.__setattr__(self, "canonical_bytes", encoded)
        object.__setattr__(self, "digest", expected_digest)
        object.__setattr__(self, "image_identity", value["image_identity"])
        object.__setattr__(self, "processor_profile", value["processor_profile"])


@dataclass(frozen=True, init=False)
class NativeRegistry:
    """One optional immutable entry with exact administrator-approved image aliases.

    Construction/replacement is explicit server composition, not a deployed
    registry, endpoint, or reload mechanism. The entry is <=64 KiB; at most 128
    aliases consume <=64 KiB canonical bytes in total. No mutable collections
    escape. Matching an alias never changes the client's original TaskSpec bytes.
    """

    entry: NativeConfiguration | None
    image_aliases: tuple[str, ...]

    def __init__(
        self, entry: NativeConfiguration | None, image_aliases: list[str] | tuple[str, ...]
    ):
        if (
            entry is not None
            and type(entry) is not NativeConfiguration
            or type(image_aliases) not in (list, tuple)
            or len(image_aliases) > MAX_IMAGE_ALIASES
            or (entry is None and len(image_aliases) != 0)
            or (entry is not None and len(image_aliases) == 0)
        ):
            _invalid()
        # Copy and validate each primitive before set/hash/encoding operations.
        aliases = tuple(image_aliases)
        for alias in aliases:
            if type(alias) is not str or not 1 <= len(alias) <= 300 or "\x00" in alias:
                _invalid()
            try:
                alias.encode("utf-8")
            except UnicodeError:
                _invalid()
        if len(set(aliases)) != len(aliases):
            _invalid()
        try:
            bounded_canonical(
                list(aliases), limit=MAX_ALIAS_BYTES, limit_code="admission_configuration_limit"
            )
        except AdmissionPreparationError as error:
            if error.code == "admission_configuration_limit":
                raise
            _invalid()
        object.__setattr__(self, "entry", entry)
        object.__setattr__(self, "image_aliases", aliases)

    def resolve_new(
        self, adapter_config_id: str, task_image: str, *, permitted_processor_profile: str | None
    ) -> NativeConfiguration:
        """Pure preparation after P3 checks BOTH existing operation identities.

        The permission input is trusted internal policy data, not proof of SQL
        authority. P3 must verify actual caller/corpus permission before invoking
        this method and freshly recheck it at publication. A configuration cannot
        add a processor permission. Existing accepted operations bypass lookup
        and keep their originally stored bytes/digests.
        """
        if (
            adapter_config_id != "native-v1"
            or type(task_image) is not str
            or self.entry is None
            or task_image not in self.image_aliases
            or not _opaque(permitted_processor_profile)
            or permitted_processor_profile != self.entry.processor_profile
        ):
            raise AdmissionPreparationError("admission_configuration_unavailable")
        return self.entry
