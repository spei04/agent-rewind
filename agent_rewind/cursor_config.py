"""Lazy LIST-only cursor secret validation, separate from application startup."""

from __future__ import annotations

import base64
import hmac
import re

from .config import Settings
from .errors import Fault
from .run_cursor import CursorCodec


def cursor_codec(settings: Settings) -> CursorCodec:
    """Call only after fresh LIST authority, never from detail/startup/health."""
    secret = settings.cursor_signing_key
    value = None if secret is None else secret.get_secret_value()
    if type(value) is not str or re.fullmatch(r"[A-Za-z0-9_-]{43}", value) is None:
        raise Fault("dependency_unavailable")
    try:
        key = base64.b64decode(value + "=", altchars=b"-_", validate=True)
        encryption = base64.b64decode(
            settings.encryption_key.get_secret_value(), altchars=b"-_", validate=True
        )
    except (ValueError, UnicodeError):
        raise Fault("dependency_unavailable") from None
    if (
        len(key) != 32
        or len(encryption) != 32
        or base64.urlsafe_b64encode(key).decode().rstrip("=") != value
        or hmac.compare_digest(key, encryption)
    ):
        raise Fault("dependency_unavailable")
    return CursorCodec(key)
