"""Client-supplied outline. Structure only: section ids and titles.

The server does not read the course guide, does not check headings against it,
and does not store factual claims.
"""

import hashlib
import re
from pathlib import Path

from studium.policy.trust import contains_directive
from studium.storage.init_project import load_state_holding_lock
from studium.storage.locking import ProjectLocked, project_lock
from studium.storage.migrate import utc_now
from studium.storage.records import BLUEPRINT, allocate_id, append_jsonl, fold_by_id

_AUDIT = "audit/audit.jsonl"
_SECTION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$")
_MAX_TITLE = 500
_MAX_SECTIONS = 200
_SECTION_KEYS = frozenset({"id", "title"})


def store_blueprint(
    root: Path,
    sections: object,
    *,
    actor: dict[str, object] | None = None,
) -> dict[str, object]:
    """Replace the stored outline. Does not change project state or local_sources."""

    cleaned, error = _sections(sections)
    if error is not None or cleaned is None:
        return error if error is not None else _error("mcp.invalid_input", "sections are required")
    try:
        with project_lock(root):
            prior = _current(root)
            identifier = str(prior["id"]) if prior is not None else allocate_id(root, "OUT")
            record: dict[str, object] = {
                "schema_version": "1.0.0",
                "id": identifier,
                "sections": cleaned,
                "recorded_at": utc_now(),
            }
            append_jsonl(root / BLUEPRINT, record)
            _audit(root, identifier=identifier, actor=actor, sections=cleaned)
            fresh = load_state_holding_lock(root)
            return _body(fresh, record)
    except ProjectLocked:
        return _error("storage.locked", "project is locked")


def get_blueprint(root: Path) -> dict[str, object]:
    """Return the stored outline, or null when none is stored. Does not write."""

    current = _current(root)
    if current is None:
        return {"status": "ok", "blueprint": None}
    return {"status": "ok", "blueprint": _public(current)}


def current_sections(root: Path) -> list[dict[str, str]]:
    current = _current(root)
    if current is None:
        return []
    sections = current.get("sections")
    if not isinstance(sections, list):
        return []
    visible: list[dict[str, str]] = []
    for item in sections:
        if isinstance(item, dict) and isinstance(item.get("id"), str) and isinstance(item.get("title"), str):
            visible.append({"id": item["id"], "title": item["title"]})
    return visible


def _sections(value: object) -> tuple[list[dict[str, str]] | None, dict[str, object] | None]:
    if not isinstance(value, list) or not value:
        return None, _error("mcp.invalid_input", "at least one section is required")
    if len(value) > _MAX_SECTIONS:
        return None, _error("mcp.invalid_input", "too many sections to store")
    cleaned: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            return None, _error("mcp.invalid_input", "each section needs an id and a title")
        if set(item) - _SECTION_KEYS:
            return None, {
                "status": "blueprint.structure_only",
                "message": "blueprint stores section ids and titles only",
            }
        identifier = item.get("id")
        title = item.get("title")
        if not isinstance(identifier, str) or _SECTION_ID.fullmatch(identifier.strip()) is None:
            return None, _error("mcp.invalid_input", "section id is invalid")
        if not isinstance(title, str):
            return None, _error("mcp.invalid_input", "section title is required")
        cleaned_title = title.strip()
        if not cleaned_title or len(cleaned_title) > _MAX_TITLE or "\n" in cleaned_title or "\r" in cleaned_title:
            return None, _error("mcp.invalid_input", "section title is required")
        section_id = identifier.strip()
        if section_id in seen:
            return None, _error("mcp.invalid_input", "section ids must be unique")
        seen.add(section_id)
        cleaned.append({"id": section_id, "title": cleaned_title})
    return cleaned, None


def _current(root: Path) -> dict[str, object] | None:
    rows = fold_by_id(root / BLUEPRINT)
    if not rows:
        return None
    return rows[-1]


def _public(record: dict[str, object]) -> dict[str, object]:
    sections = record.get("sections")
    visible = sections if isinstance(sections, list) else []
    return {"id": record.get("id"), "sections": visible}


def _body(state: dict[str, object], record: dict[str, object]) -> dict[str, object]:
    return {
        "status": "recorded",
        "blueprint": _public(record),
        "local_sources": _local(state),
        "project_state": state.get("state"),
        "released": state.get("state") == "RELEASED",
    }


def _local(state: dict[str, object]) -> dict[str, object]:
    local = state.get("local_sources")
    if isinstance(local, dict):
        return dict(local)
    return {"status": "UNKNOWN", "prompted": False, "source_count": 0}


def _audit(root: Path, *, identifier: str, actor: dict[str, object] | None, sections: list[dict[str, str]]) -> None:
    digest = hashlib.sha256(repr(sections).encode("utf-8")).hexdigest()
    ignored = any(contains_directive(section["title"].encode("utf-8")) for section in sections)
    append_jsonl(
        root / _AUDIT,
        {
            "schema_version": "1.0.0",
            "timestamp": utc_now(),
            "source_id": identifier,
            "operation": "store_blueprint",
            "origin": None,
            "actor": _actor(actor),
            "previous_hash": None,
            "new_hash": digest,
            "result": "structure_only",
            "tool": "blueprint_store",
            "content_directives_ignored": ignored,
        },
    )


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
