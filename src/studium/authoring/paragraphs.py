"""Draft paragraphs tied to an opened excerpt.

A paragraph is not verified or accepted. The model is not a source. Empty
blueprint sections stay empty.
"""

import hashlib
from pathlib import Path

from studium.authoring.blueprint import current_sections
from studium.authoring.support import paragraph_citation_blockers
from studium.policy.trust import contains_directive, directive_changes_policy
from studium.storage.init_project import load_state_holding_lock
from studium.storage.locking import ProjectLocked, project_lock
from studium.storage.migrate import utc_now
from studium.storage.records import PARAGRAPHS, allocate_id, append_jsonl, fold_by_id

_AUDIT = "audit/audit.jsonl"
_MAX_TEXT = 20_000
_MAX_EXCERPTS = 40
GAP_LABEL = "Gap: this section has no paragraph tied to an opened excerpt."


def record_paragraph(
    root: Path,
    *,
    section: object,
    text: object,
    excerpts: object,
    role: object = None,
    actor: dict[str, object] | None = None,
) -> dict[str, object]:
    """Store one draft paragraph for a blueprint section. Does not change state."""

    section_id, section_error = _section(root, section)
    if section_error is not None:
        return section_error
    cleaned_text, text_error = _text(text)
    if text_error is not None:
        return text_error
    excerpt_ids, excerpt_error = _excerpts(excerpts)
    if excerpt_error is not None:
        return excerpt_error
    paragraph_role, role_error = _role(role)
    if role_error is not None:
        return role_error
    assert section_id is not None and cleaned_text is not None and excerpt_ids is not None
    if directive_changes_policy(cleaned_text):
        return _error("policy.overridden", "paragraph text changed policy")
    blockers = paragraph_citation_blockers(root, excerpt_ids)
    if blockers:
        return _rejected(root, blockers)
    try:
        with project_lock(root):
            state = load_state_holding_lock(root)
            fresh_blockers = paragraph_citation_blockers(root, excerpt_ids)
            if fresh_blockers:
                return _rejected_state(state, fresh_blockers)
            digest = _digest(section_id, cleaned_text, excerpt_ids)
            prior = next((item for item in fold_by_id(root / PARAGRAPHS) if item.get("text_sha256") == digest), None)
            if prior is not None:
                return _body(state, prior, status="already_recorded")
            record: dict[str, object] = {
                "schema_version": "1.0.0",
                "id": allocate_id(root, "PAR"),
                "section": section_id,
                "text": cleaned_text,
                "excerpts": excerpt_ids,
                "status": "draft",
                "classification": "PENDING",
                "text_sha256": digest,
                "content_directives_ignored": contains_directive(cleaned_text.encode("utf-8")),
                "recorded_at": utc_now(),
            }
            if paragraph_role is not None:
                record["role"] = paragraph_role
            append_jsonl(root / PARAGRAPHS, record)
            _audit(root, record=record, actor=actor)
            fresh = load_state_holding_lock(root)
            return _body(fresh, record, status="recorded")
    except ProjectLocked:
        return _error("storage.locked", "project is locked")


def replace_paragraph(
    root: Path,
    *,
    paragraph_id: object,
    text: object,
    excerpts: object,
    role: object = None,
    actor: dict[str, object] | None = None,
) -> dict[str, object]:
    """Rewrite one stored paragraph in place. The new text still cites an excerpt.

    Conflicts and course sources the guide does not cite are rejected, the same
    as ``record_paragraph``. The id does not change. The result stays a draft.
    """

    identifier = _paragraph_id(paragraph_id)
    if identifier is None:
        return _error("mcp.invalid_input", "id is required")
    current = next((item for item in fold_by_id(root / PARAGRAPHS) if item.get("id") == identifier), None)
    if current is None:
        return _error("paragraph.not_found", "no stored paragraph with that id")
    cleaned_text, text_error = _text(text)
    if text_error is not None:
        return text_error
    excerpt_ids, excerpt_error = _excerpts(excerpts)
    if excerpt_error is not None:
        return excerpt_error
    paragraph_role, role_error = _role(role)
    if role_error is not None:
        return role_error
    assert cleaned_text is not None and excerpt_ids is not None
    if directive_changes_policy(cleaned_text):
        return _error("policy.overridden", "paragraph text changed policy")
    blockers = paragraph_citation_blockers(root, excerpt_ids)
    if blockers:
        return _rejected(root, blockers)
    section_id = current.get("section")
    if not isinstance(section_id, str):
        return _error("paragraph.section_unknown", "section is not in the stored blueprint")
    try:
        with project_lock(root):
            state = load_state_holding_lock(root)
            fresh_blockers = paragraph_citation_blockers(root, excerpt_ids)
            if fresh_blockers:
                return _rejected_state(state, fresh_blockers)
            digest = _digest(section_id, cleaned_text, excerpt_ids)
            record: dict[str, object] = {
                "schema_version": "1.0.0",
                "id": identifier,
                "section": section_id,
                "text": cleaned_text,
                "excerpts": excerpt_ids,
                "status": "draft",
                "classification": "PENDING",
                "text_sha256": digest,
                "content_directives_ignored": contains_directive(cleaned_text.encode("utf-8")),
                "recorded_at": utc_now(),
                "replaces": identifier,
            }
            if paragraph_role is not None:
                record["role"] = paragraph_role
            elif isinstance(current.get("role"), str):
                record["role"] = current["role"]
            append_jsonl(root / PARAGRAPHS, record)
            _audit(root, record=record, actor=actor, operation="replace_paragraph")
            fresh = load_state_holding_lock(root)
            return _body(fresh, record, status="replaced")
    except ProjectLocked:
        return _error("storage.locked", "project is locked")


def list_paragraphs(root: Path) -> dict[str, object]:
    """List stored draft paragraphs. Text is untrusted data."""

    return {"status": "ok", "paragraphs": [_public(record) for record in fold_by_id(root / PARAGRAPHS)]}


def draft_completeness(root: Path) -> dict[str, object]:
    """How many blueprint sections have a supported paragraph, and which are empty."""

    sections = current_sections(root)
    covered = supported_section_ids(root)
    empty = [section for section in sections if section["id"] not in covered]
    filled = [section for section in sections if section["id"] in covered]
    state = _read_state(root)
    return {
        "status": "ok",
        "section_count": len(sections),
        "supported_section_count": len(filled),
        "empty_sections": empty,
        "covered_sections": filled,
        "project_state": state.get("state"),
        "released": state.get("state") == "RELEASED",
        "local_sources": _local(state),
    }


def supported_paragraphs(root: Path) -> list[dict[str, object]]:
    """Stored drafts whose excerpts still pass the support check."""

    kept: list[dict[str, object]] = []
    for record in fold_by_id(root / PARAGRAPHS):
        if record.get("status") != "draft":
            continue
        excerpts = record.get("excerpts")
        if not isinstance(excerpts, list) or not excerpts or not all(isinstance(item, str) for item in excerpts):
            continue
        if paragraph_citation_blockers(root, list(excerpts)):
            continue
        kept.append(record)
    return kept


def supported_section_ids(root: Path) -> set[str]:
    found: set[str] = set()
    for record in supported_paragraphs(root):
        section = record.get("section")
        if isinstance(section, str):
            found.add(section)
    return found


def corpus_started_blockers(root: Path) -> list[dict[str, object]]:
    """corpus_started passes only when every blueprint section has a supported paragraph.

    An empty list means the check passes. This does not change project state.
    """

    sections = current_sections(root)
    if not sections:
        return [
            {
                "code": "state.corpus_incomplete",
                "entity_id": None,
                "message": "corpus_started requires every blueprint section to have a supported paragraph",
            }
        ]
    empty = [section for section in sections if section["id"] not in supported_section_ids(root)]
    return [
        {
            "code": "state.corpus_incomplete",
            "entity_id": section["id"],
            "message": f"{section['id']} ({section['title']}) has no supported paragraph",
        }
        for section in empty
    ]


def annotate_next_action(root: Path, payload: dict[str, object]) -> dict[str, object]:
    """Name empty blueprint sections on an existing next_action. Does not write."""

    action = payload.get("next_action")
    if not isinstance(action, str) or not current_sections(root):
        return payload
    empty = [section for section in current_sections(root) if section["id"] not in supported_section_ids(root)]
    if empty:
        names = ", ".join(f"{section['id']} ({section['title']})" for section in empty)
        suffix = (
            f" Empty sections: {names}. "
            "Fill them from opened open-licensed text and add checked problems."
        )
    else:
        suffix = (
            " Every blueprint section has a supported paragraph. "
            "Add checked problems. Do not mark the book released."
        )
    from studium.authoring.book_next import unfinished_chapter

    unfinished = unfinished_chapter(root)
    if unfinished is not None:
        section, missing = unfinished
        title = section["title"].strip() or section["id"]
        suffix += (
            f" Write the next unfinished chapter: {title}. "
            f"Missing contract pieces: {', '.join(missing)}. "
            "Do not render. Do not hand the draft over. "
            "A partial PDF is not a reason to stop."
        )
    else:
        suffix += (
            " Then studium_audit_record, studium_contradiction_scan, and studium_book_review, "
            "then render once. Do not stop mid-book for a preview. "
            "Do not mark the book released."
        )
    if suffix.strip() in action:
        return payload
    updated = dict(payload)
    updated["next_action"] = action + suffix
    return updated


_KEPT_ROLES = {"purpose", "self_check", "consejo", "definition"}


def _role(value: object) -> tuple[str | None, dict[str, object] | None]:
    if value is None:
        return None, None
    if not isinstance(value, str):
        return None, _error("mcp.invalid_input", "role must be purpose, explanation, consejo, definition, or self_check")
    cleaned = value.strip().lower()
    if cleaned in {"definicion", "definición"}:
        cleaned = "definition"
    if cleaned == "explanation":
        return None, None
    if cleaned not in _KEPT_ROLES:
        return None, _error("mcp.invalid_input", "role must be purpose, explanation, consejo, definition, or self_check")
    return cleaned, None


def _section(root: Path, value: object) -> tuple[str | None, dict[str, object] | None]:
    if not isinstance(value, str) or not value.strip():
        return None, _error("mcp.invalid_input", "section must be a blueprint section id")
    identifier = value.strip()
    known = {section["id"] for section in current_sections(root)}
    if identifier not in known:
        return None, _error("paragraph.section_unknown", "section is not in the stored blueprint")
    return identifier, None


def _text(value: object) -> tuple[str | None, dict[str, object] | None]:
    if not isinstance(value, str):
        return None, _error("mcp.invalid_input", "text is required")
    cleaned = value.strip()
    if not cleaned or len(cleaned) > _MAX_TEXT:
        return None, _error("mcp.invalid_input", "text is required")
    return cleaned, None


def _excerpts(value: object) -> tuple[list[str] | None, dict[str, object] | None]:
    if not isinstance(value, list) or not value:
        return None, _error("mcp.invalid_input", "a paragraph needs a stored excerpt id")
    if len(value) > _MAX_EXCERPTS:
        return None, _error("mcp.invalid_input", "too many excerpts to store")
    identifiers: list[str] = []
    for item in value:
        if not isinstance(item, str):
            return None, _error("mcp.invalid_input", "a paragraph needs a stored excerpt id")
        cleaned = item.strip()
        if not cleaned or len(cleaned) > 128:
            return None, _error("mcp.invalid_input", "a paragraph needs a stored excerpt id")
        if cleaned in identifiers:
            return None, _error("mcp.invalid_input", "excerpts lists the same id more than once")
        identifiers.append(cleaned)
    return identifiers, None


def _public(record: dict[str, object]) -> dict[str, object]:
    visible = {
        "id": record.get("id"),
        "section": record.get("section"),
        "text": record.get("text"),
        "excerpts": record.get("excerpts"),
        "status": "draft",
        "classification": "PENDING",
    }
    if record.get("role") in _KEPT_ROLES:
        visible["role"] = record["role"]
    if record.get("content_directives_ignored") is True:
        visible["content_directives_ignored"] = True
    return visible


def _body(state: dict[str, object], record: dict[str, object], *, status: str) -> dict[str, object]:
    return {
        "status": status,
        "paragraph": _public(record),
        "local_sources": _local(state),
        "project_state": state.get("state"),
        "released": state.get("state") == "RELEASED",
    }


def _rejected(root: Path, blockers: list[dict[str, object]]) -> dict[str, object]:
    return _rejected_state(_read_state(root), blockers)


def _rejected_state(state: dict[str, object], blockers: list[dict[str, object]]) -> dict[str, object]:
    return {
        "status": "rejected",
        "message": "a paragraph needs a stored excerpt whose public source can support a draft",
        "blockers": blockers,
        "local_sources": _local(state),
        "project_state": state.get("state"),
        "released": state.get("state") == "RELEASED",
    }


def _digest(section_id: str, text: str, excerpts: list[str]) -> str:
    payload = section_id + "\n" + text + "\n" + "\n".join(excerpts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _read_state(root: Path) -> dict[str, object]:
    try:
        with project_lock(root):
            return load_state_holding_lock(root)
    except ProjectLocked:
        return {}


def _paragraph_id(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned or len(cleaned) > 128:
        return None
    return cleaned


def _audit(
    root: Path,
    *,
    record: dict[str, object],
    actor: dict[str, object] | None,
    operation: str = "record_paragraph",
) -> None:
    append_jsonl(
        root / _AUDIT,
        {
            "schema_version": "1.0.0",
            "timestamp": utc_now(),
            "source_id": record.get("id"),
            "operation": operation,
            "origin": None,
            "actor": _actor(actor),
            "previous_hash": None,
            "new_hash": record.get("text_sha256"),
            "result": "draft",
            "tool": operation,
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
