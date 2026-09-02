"""Canonical argument serialization shared by the policy gate and storage.

Authorization compares model-proposed tool arguments against arguments that were
persisted in an earlier request. Both sides must agree byte-for-byte, so the
canonical form has exactly one spelling in the codebase.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def args_hash(value: Any) -> str:
    """Stable digest of canonical arguments, used as the tamper-evident key."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
