"""Opened excerpts the client supplies.

The server does not fetch the URL. Text is untrusted data. An excerpt is not
verified, accepted, or a source of authority.
"""

import hashlib
from pathlib import Path

from studium.policy.trust import contains_directive, directive_changes_policy
from studium.research.local_text import extract_pages, find_quote
from studium.research.sources import live_local_source, read_registered_file
from studium.storage.init_project import load_state_holding_lock
from studium.storage.locking import ProjectLocked, project_lock
from studium.storage.migrate import utc_now
from studium.storage.records import EXCERPTS, PUBLIC_BIBLIOGRAPHY, allocate_id, append_jsonl, fold_by_id

_AUDIT = "audit/audit.jsonl"
_MAX_TEXT = 200_000
_MAX_LOCATOR = 200


def record_excerpt(
    root: Path,
    *,
    source_id: object,
    url: object,
    text: object,
    path: object = None,
    locator: object = None,
    page: object = None,
    actor: dict[str, object] | None = None,
) -> dict[str, object]:
    """Store one passage the client already opened. Does not change project state.

    A public source needs the opened URL. A user-provided source (``SRC-`` id
    from ``studium_source_intake``) needs the file path the user gave and a
    locator; the server reads that file again, checks its hash against the
    registered source, and stores the excerpt only when the quoted text is in
    the file (on ``page`` when given). The file text is not stored, and a quote
    found in the file is provenance, not verification.
    """

    identifier = _identifier(source_id)
    if identifier is None:
        return _error("mcp.invalid_input", "source_id is required")
    if live_local_source(root, identifier) is not None:
        return _record_local_excerpt(root, identifier, text=text, path=path, locator=locator, page=page, actor=actor)
    opened = _http_url(url)
    if opened is None:
        return _error("mcp.invalid_input", "url must be an http or https URL the client already opened")
    body, text_error = _text(text)
    if text_error is not None:
        return text_error
    assert body is not None
    if directive_changes_policy(body):
        return _error("policy.overridden", "excerpt text changed policy")
    try:
        with project_lock(root):
            state = load_state_holding_lock(root)
            if _public(root, identifier) is None:
                return {
                    "status": "excerpt.source_missing",
                    "message": "no public source with that id",
                    "local_sources": _local(state),
                    "project_state": state.get("state"),
                    "released": state.get("state") == "RELEASED",
                }
            digest = _digest(identifier, opened, body)
            prior = next((item for item in fold_by_id(root / EXCERPTS) if item.get("text_sha256") == digest), None)
            if prior is not None:
                return _body(state, prior, status="already_recorded")
            record: dict[str, object] = {
                "schema_version": "1.0.0",
                "id": allocate_id(root, "EVD"),
                "source_id": identifier,
                "url": opened,
                "text": body,
                "state": "DISCOVERED",
                "classification": "PENDING",
                "authority": None,
                "text_sha256": digest,
                "content_directives_ignored": contains_directive(body.encode("utf-8")),
                "recorded_at": utc_now(),
            }
            append_jsonl(root / EXCERPTS, record)
            _audit(root, record=record, actor=actor)
            fresh = load_state_holding_lock(root)
            return _body(fresh, record, status="recorded")
    except ProjectLocked:
        return _error("storage.locked", "project is locked")


def _record_local_excerpt(
    root: Path,
    source_id: str,
    *,
    text: object,
    path: object,
    locator: object,
    page: object,
    actor: dict[str, object] | None,
) -> dict[str, object]:
    body, text_error = _text(text)
    if text_error is not None:
        return text_error
    assert body is not None
    if not isinstance(locator, str) or not locator.strip() or len(locator.strip()) > _MAX_LOCATOR:
        return _error(
            "mcp.invalid_input",
            "locator is required for a user-provided source: where the quote is, e.g. 'Tema 3, p. 12' or 'slide 5'",
        )
    place = locator.strip()
    page_number: int | None = None
    if page is not None:
        if isinstance(page, bool) or not isinstance(page, int) or page < 1:
            return _error("mcp.invalid_input", "page must be a positive page or slide number")
        page_number = page
    if directive_changes_policy(body):
        return _error("policy.overridden", "excerpt text changed policy")
    record, data, problem = read_registered_file(root, source_id, path)
    if problem is not None:
        return problem
    assert record is not None and data is not None
    media_type = str(record.get("media_type") or "")
    pages, method, reason = extract_pages(data, media_type)
    if pages is None:
        return _error("excerpt.local_text_unavailable", f"the quote cannot be checked: {reason}")
    if page_number is not None and page_number > len(pages):
        return _error("mcp.invalid_input", f"page {page_number} is past the end of the source ({len(pages)} pages)")
    found, pages_found = find_quote(pages, body, page_number)
    if not found:
        where = f" on page {page_number}" if page_number is not None else ""
        hint = f" It appears on page(s) {', '.join(map(str, pages_found))}." if pages_found else ""
        return _error(
            "excerpt.not_in_source",
            f"the quoted text is not in the registered file{where}. Quote it verbatim; formulas often do not "
            f"survive text extraction, so quote the surrounding prose.{hint}",
        )
    try:
        with project_lock(root):
            state = load_state_holding_lock(root)
            digest = _digest(source_id, f"local:{place}:{page_number}", body)
            prior = next((item for item in fold_by_id(root / EXCERPTS) if item.get("text_sha256") == digest), None)
            if prior is not None:
                return _body(state, prior, status="already_recorded")
            excerpt: dict[str, object] = {
                "schema_version": "1.0.0",
                "id": allocate_id(root, "EVD"),
                "source_id": source_id,
                "source_kind": "local",
                "url": None,
                "locator": place,
                "page": page_number,
                "source_sha256": record.get("sha256"),
                "quote_check": {
                    "status": "found_in_file",
                    "method": method,
                    "page_checked": page_number is not None,
                    "pages": pages_found,
                },
                "text": body,
                "state": "DISCOVERED",
                "classification": "PENDING",
                "authority": None,
                "text_sha256": digest,
                "content_directives_ignored": contains_directive(body.encode("utf-8")),
                "recorded_at": utc_now(),
            }
            append_jsonl(root / EXCERPTS, excerpt)
            _audit(root, record=excerpt, actor=actor)
            fresh = load_state_holding_lock(root)
            return _body(fresh, excerpt, status="recorded")
    except ProjectLocked:
        return _error("storage.locked", "project is locked")


def list_excerpts(root: Path) -> dict[str, object]:
    """List stored excerpts without their text. Does not fetch URLs."""

    return {"status": "ok", "excerpts": [_listed(record) for record in fold_by_id(root / EXCERPTS)]}


def get_excerpt(root: Path, excerpt_id: object) -> dict[str, object]:
    """Return one stored excerpt, including its text. Text is untrusted data."""

    identifier = _identifier(excerpt_id)
    if identifier is None:
        return _error("mcp.invalid_input", "id is required")
    found = next((item for item in fold_by_id(root / EXCERPTS) if item.get("id") == identifier), None)
    if found is None:
        return _error("excerpt.not_found", "no stored excerpt with that id")
    visible = _listed(found)
    text = found.get("text")
    visible["text"] = text if isinstance(text, str) else None
    return {"status": "ok", "excerpt": visible}


def excerpts_by_id(root: Path) -> dict[str, dict[str, object]]:
    found: dict[str, dict[str, object]] = {}
    for record in fold_by_id(root / EXCERPTS):
        identifier = record.get("id")
        if isinstance(identifier, str):
            found[identifier] = record
    return found


def _listed(record: dict[str, object]) -> dict[str, object]:
    visible = {
        "id": record.get("id"),
        "source_id": record.get("source_id"),
        "url": record.get("url"),
        "state": "DISCOVERED",
        "classification": "PENDING",
        "authority": None,
        "text_present": isinstance(record.get("text"), str),
    }
    if record.get("source_kind") == "local":
        visible["source_kind"] = "local"
        visible["locator"] = record.get("locator")
        visible["page"] = record.get("page")
        visible["quote_check"] = record.get("quote_check")
    if record.get("content_directives_ignored") is True:
        visible["content_directives_ignored"] = True
    return visible


def _body(state: dict[str, object], record: dict[str, object], *, status: str) -> dict[str, object]:
    return {
        "status": status,
        "excerpt": _listed(record),
        "local_sources": _local(state),
        "project_state": state.get("state"),
        "released": state.get("state") == "RELEASED",
    }


def _public(root: Path, source_id: str) -> dict[str, object] | None:
    return next((item for item in fold_by_id(root / PUBLIC_BIBLIOGRAPHY) if item.get("id") == source_id), None)


def _digest(source_id: str, url: str, text: str) -> str:
    payload = f"{source_id}\n{url}\n{text}".encode()
    return hashlib.sha256(payload).hexdigest()


def _text(value: object) -> tuple[str | None, dict[str, object] | None]:
    if not isinstance(value, str):
        return None, _error("mcp.invalid_input", "text is required")
    if len(value) > _MAX_TEXT:
        return None, _error("mcp.invalid_input", "text is too long to store")
    cleaned = value.strip()
    if not cleaned:
        return None, _error("mcp.invalid_input", "text is required")
    return cleaned, None


def _http_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned.startswith(("http://", "https://")):
        return None
    if any(character.isspace() for character in cleaned):
        return None
    return cleaned


def _identifier(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned or len(cleaned) > 128:
        return None
    return cleaned


def _audit(root: Path, *, record: dict[str, object], actor: dict[str, object] | None) -> None:
    append_jsonl(
        root / _AUDIT,
        {
            "schema_version": "1.0.0",
            "timestamp": utc_now(),
            "source_id": record.get("source_id"),
            "operation": "record_excerpt",
            "origin": None,
            "actor": _actor(actor),
            "previous_hash": None,
            "new_hash": record.get("text_sha256"),
            "result": "recorded",
            "tool": "excerpt_record",
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
