"""Draft claims. Text is data. A claim is not verified or accepted."""

import hashlib
from pathlib import Path

from studium.authoring.blueprint import current_sections
from studium.authoring.support import support_blockers
from studium.policy.trust import contains_directive, directive_changes_policy
from studium.storage.init_project import load_state_holding_lock
from studium.storage.locking import ProjectLocked, project_lock
from studium.storage.migrate import utc_now
from studium.storage.records import CLAIMS, allocate_id, append_jsonl, fold_by_id

_AUDIT = "audit/audit.jsonl"
_MAX_TEXT = 20_000
_MAX_SOURCES = 40


def record_claim(
    root: Path,
    *,
    text: object,
    sources: object,
    section: object = None,
    actor: dict[str, object] | None = None,
) -> dict[str, object]:
    """Store one draft when every cited public source passes the support check."""

    cleaned_text, text_error = _text(text)
    if text_error is not None:
        return text_error
    source_ids, source_error = _sources(sources)
    if source_error is not None:
        return source_error
    section_id, section_error = _section(root, section)
    if section_error is not None:
        return section_error
    assert cleaned_text is not None and source_ids is not None
    if directive_changes_policy(cleaned_text):
        return _error("policy.overridden", "claim text changed policy")
    blockers = support_blockers(root, source_ids)
    if blockers:
        state = _read_state(root)
        return {
            "status": "rejected",
            "message": "a cited source cannot support a claim",
            "blockers": blockers,
            "local_sources": _local(state),
            "project_state": state.get("state"),
            "released": state.get("state") == "RELEASED",
        }
    try:
        with project_lock(root):
            state = load_state_holding_lock(root)
            fresh_blockers = support_blockers(root, source_ids)
            if fresh_blockers:
                return {
                    "status": "rejected",
                    "message": "a cited source cannot support a claim",
                    "blockers": fresh_blockers,
                    "local_sources": _local(state),
                    "project_state": state.get("state"),
                    "released": state.get("state") == "RELEASED",
                }
            identifier = allocate_id(root, "CLM")
            record: dict[str, object] = {
                "schema_version": "1.0.0",
                "id": identifier,
                "text": cleaned_text,
                "sources": source_ids,
                "status": "draft",
                "classification": "PENDING",
                "content_directives_ignored": contains_directive(cleaned_text.encode("utf-8")),
                "recorded_at": utc_now(),
            }
            if section_id is not None:
                record["section"] = section_id
            append_jsonl(root / CLAIMS, record)
            _audit(root, record=record, actor=actor)
            fresh = load_state_holding_lock(root)
            return {
                "status": "recorded",
                "claim": _public(record),
                "local_sources": _local(fresh),
                "project_state": fresh.get("state"),
                "released": fresh.get("state") == "RELEASED",
            }
    except ProjectLocked:
        return _error("storage.locked", "project is locked")


def list_claims(root: Path) -> dict[str, object]:
    """Read stored drafts. Does not verify them or fetch sources."""

    return {"status": "ok", "claims": [_public(record) for record in fold_by_id(root / CLAIMS)]}


def _public(record: dict[str, object]) -> dict[str, object]:
    visible = {
        "id": record.get("id"),
        "text": record.get("text"),
        "sources": record.get("sources"),
        "status": "draft",
        "classification": "PENDING",
    }
    if isinstance(record.get("section"), str):
        visible["section"] = record["section"]
    if record.get("content_directives_ignored") is True:
        visible["content_directives_ignored"] = True
    return visible


def _text(value: object) -> tuple[str | None, dict[str, object] | None]:
    if not isinstance(value, str):
        return None, _error("mcp.invalid_input", "text is required")
    cleaned = value.strip()
    if not cleaned or len(cleaned) > _MAX_TEXT:
        return None, _error("mcp.invalid_input", "text is required")
    return cleaned, None


def _sources(value: object) -> tuple[list[str] | None, dict[str, object] | None]:
    if not isinstance(value, list) or not value:
        return None, _error("mcp.invalid_input", "sources must list one or more public source ids")
    if len(value) > _MAX_SOURCES:
        return None, _error("mcp.invalid_input", "too many sources to store")
    identifiers: list[str] = []
    for item in value:
        if not isinstance(item, str):
            return None, _error("mcp.invalid_input", "sources must list one or more public source ids")
        cleaned = item.strip()
        if not cleaned or len(cleaned) > 128:
            return None, _error("mcp.invalid_input", "sources must list one or more public source ids")
        if cleaned in identifiers:
            return None, _error("mcp.invalid_input", "sources lists the same public source more than once")
        identifiers.append(cleaned)
    return identifiers, None


def _section(root: Path, value: object) -> tuple[str | None, dict[str, object] | None]:
    if value is None:
        return None, None
    if not isinstance(value, str) or not value.strip():
        return None, _error("mcp.invalid_input", "section must be a blueprint section id")
    identifier = value.strip()
    known = {section["id"] for section in current_sections(root)}
    if identifier not in known:
        return None, _error("claim.section_unknown", "section is not in the stored blueprint")
    return identifier, None


def _read_state(root: Path) -> dict[str, object]:
    try:
        with project_lock(root):
            return load_state_holding_lock(root)
    except ProjectLocked:
        return {}


def _audit(root: Path, *, record: dict[str, object], actor: dict[str, object] | None) -> None:
    text = record.get("text")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest() if isinstance(text, str) else None
    append_jsonl(
        root / _AUDIT,
        {
            "schema_version": "1.0.0",
            "timestamp": utc_now(),
            "source_id": record.get("id"),
            "operation": "record_claim",
            "origin": None,
            "actor": _actor(actor),
            "previous_hash": None,
            "new_hash": digest,
            "result": "draft",
            "tool": "claim_record",
        },
    )


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
