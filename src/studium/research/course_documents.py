"""Official course documents the client already holds.

This is not local-source intake and it does not fetch, search, or read a disk.
The text is stored as data. It is not a source class, a verification, or a policy.
"""

import hashlib
from pathlib import Path

from studium.domain.enums import SourceOrigin
from studium.policy.trust import contains_directive, directive_changes_policy
from studium.storage.init_project import load_state_holding_lock
from studium.storage.locking import ProjectLocked, project_lock
from studium.storage.migrate import utc_now
from studium.storage.records import append_jsonl, fold_by_id

_CANDIDATES = "course/candidates.jsonl"
_AUDIT = "audit/audit.jsonl"
_MAX_TITLE = 500
_MAX_TEXT = 2_000_000


def record_course_document(
    root: Path,
    *,
    title: object,
    url: object,
    text: object = None,
    actor: dict[str, object] | None = None,
) -> dict[str, object]:
    cleaned_title = _title(title)
    if cleaned_title is None:
        return _error("mcp.invalid_input", "title is required")
    cleaned_url = _http_url(url)
    if cleaned_url is None:
        return _error("mcp.invalid_input", "url must be an http or https URL the client already has")
    body, text_error = _text(text)
    if text_error is not None:
        return _error("mcp.invalid_input", text_error)
    if isinstance(body, str) and directive_changes_policy(body):
        return _error("policy.overridden", "source text changed policy")
    digest = hashlib.sha256(cleaned_url.encode("utf-8")).hexdigest()
    ignored = isinstance(body, str) and contains_directive(body.encode("utf-8"))
    record: dict[str, object] = {
        "schema_version": "1.0.0",
        "id": digest,
        "title": cleaned_title,
        "url": cleaned_url,
        "origin": SourceOrigin.OFFICIAL_WEB.value,
        "state": "DISCOVERED",
        "classification": "PENDING",
        "source_class": None,
        "authority_status": None,
        "text_present": isinstance(body, str),
        "text_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest() if isinstance(body, str) else None,
        "content_directives_ignored": ignored,
        "recorded_at": utc_now(),
    }
    if isinstance(body, str):
        record["text"] = body
    try:
        with project_lock(root):
            state = load_state_holding_lock(root)
            local = _local(state)
            project_state = state.get("state")
            existing = fold_by_id(root / _CANDIDATES)
            prior = next((item for item in existing if item.get("id") == digest), None)
            if prior is not None:
                return {
                    "status": "already_recorded",
                    "candidate": _public(prior),
                    "local_sources": local,
                    "project_state": project_state,
                }
            append_jsonl(root / _CANDIDATES, record)
            append_jsonl(
                root / _AUDIT,
                {
                    "schema_version": "1.0.0",
                    "timestamp": utc_now(),
                    "source_id": None,
                    "operation": "record_candidate",
                    "origin": SourceOrigin.OFFICIAL_WEB.value,
                    "actor": _actor(actor),
                    "previous_hash": None,
                    "new_hash": record["text_sha256"],
                    "result": "recorded",
                    "tool": "course_document_record",
                },
            )
            fresh = load_state_holding_lock(root)
            return {
                "status": "recorded",
                "candidate": _public(record),
                "local_sources": _local(fresh),
                "project_state": fresh.get("state"),
            }
    except ProjectLocked:
        return _error("storage.locked", "project is locked")


def _title(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned or len(cleaned) > _MAX_TITLE:
        return None
    return cleaned


def _http_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned.startswith(("http://", "https://")):
        return None
    if any(character.isspace() for character in cleaned):
        return None
    return cleaned


def _text(value: object) -> tuple[str | None, str | None]:
    """Return ``(text or None, error)``. Blank text is treated as omitted."""

    if value is None:
        return None, None
    if not isinstance(value, str):
        return None, "text must be a string"
    if len(value) > _MAX_TEXT:
        return None, "text is too long to store"
    if not value.strip():
        return None, None
    return value, None


def _public(record: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in record.items() if key != "text"}


def _local(state: dict[str, object]) -> dict[str, object]:
    local = state.get("local_sources")
    if isinstance(local, dict):
        return dict(local)
    return {"status": "UNKNOWN", "prompted": False, "source_count": 0}


def _actor(actor: dict[str, object] | None) -> dict[str, object] | None:
    if not actor:
        return None
    safe: dict[str, object] = {}
    for key in ("kind", "name", "provider"):
        value = actor.get(key)
        if isinstance(value, str) and value and "/" not in value and "~" not in value and len(value) <= 80:
            safe[key] = value
    return safe or None


def _error(code: str, message: str) -> dict[str, object]:
    return {"status": code, "message": message}
