"""Canonical hashing — the basis of deterministic IDs and replay verification.

Values are converted with Pydantic's JSON encoder at every depth, so a model
hashes the same before and after a JSON round-trip (for example, after being
stored and loaded for replay). ``str()``/``repr()`` must never reach a hash:
they differ for equal values (e.g. ``timezone.utc`` vs Pydantic's ``TzInfo``).
"""

import hashlib
import json
from typing import Any

from pydantic_core import to_jsonable_python


def canonical_json(value: Any) -> str:
    return json.dumps(
        to_jsonable_python(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def sha256_of(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def short_id(prefix: str, value: Any, length: int = 12) -> str:
    return f"{prefix}-{sha256_of(value)[:length].upper()}"
