"""Framework-neutral analytics identifier helpers."""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

from rentivo.settings import settings

HASH_LEN = 16


def analytics_hash(value: Any) -> str | None:
    """Return the app-secret keyed, truncated HMAC-SHA256 for ``value``.

    Returns ``None`` when ``value`` is ``None`` or an empty string.
    """
    if value is None or value == "":
        return None
    key = settings.get_secret_key().encode()
    return hmac.new(key, str(value).encode(), hashlib.sha256).hexdigest()[:HASH_LEN]
