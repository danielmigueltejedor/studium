"""Canonical SHA-256 of a JSON value. No trailing newline."""

import hashlib
import json


def canonical_hash(document: object) -> str:
    raw = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
