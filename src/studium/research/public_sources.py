"""Public bibliography the client supplies.

This is not the user-source registry and it is not an official course document.
The server does not fetch the URL, search the web, or read the home directory.
Stored text is untrusted data. A record stays an unverified candidate.
"""

import hashlib
from pathlib import Path

from studium.domain.enums import SourceOrigin
from studium.policy.trust import contains_directive, directive_changes_policy
from studium.storage.init_project import load_state_holding_lock
from studium.storage.locking import ProjectLocked, project_lock
from studium.storage.migrate import utc_now
from studium.storage.records import PUBLIC_BIBLIOGRAPHY, append_jsonl, fold_by_id

_AUDIT = "audit/audit.jsonl"
_MAX_TITLE = 500
_MAX_TEXT = 2_000_000
_MAX_KIND = 80
_MAX_AUTHOR = 200
_MAX_AUTHORS = 40
_ORIGIN = SourceOrigin.ACADEMIC_EXTERNAL.value


def record_public_source(
    root: Path,
    *,
    title: object,
    url: object,
    authors: object = None,
    year: object = None,
    kind: object = None,
    text: object = None,
    actor: dict[str, object] | None = None,
) -> dict[str, object]:
    """Store one client-supplied candidate. Does not change ``local_sources`` or project state."""

    cleaned_title = _title(title)
    if cleaned_title is None:
        return _error("mcp.invalid_input", "title is required")
    cleaned_url = _http_url(url)
    if cleaned_url is None:
        return _error("mcp.invalid_input", "url must be an http or https URL the client already opened")
    names, author_error = _authors(authors)
    if author_error is not None:
        return _error("mcp.invalid_input", author_error)
    publication_year, year_error = _year(year)
    if year_error is not None:
        return _error("mcp.invalid_input", year_error)
    source_kind, kind_error = _kind(kind)
    if kind_error is not None:
        return _error("mcp.invalid_input", kind_error)
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
        "origin": _ORIGIN,
        "state": "DISCOVERED",
        "classification": "PENDING",
        "source_class": None,
        "authority_status": None,
        "authority": None,
        "text_present": isinstance(body, str),
        "text_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest() if isinstance(body, str) else None,
        "content_directives_ignored": ignored,
        "recorded_at": utc_now(),
    }
    if names is not None:
        record["authors"] = names
    if publication_year is not None:
        record["year"] = publication_year
    if source_kind is not None:
        record["kind"] = source_kind
    if isinstance(body, str):
        record["text"] = body
    try:
        with project_lock(root):
            state = load_state_holding_lock(root)
            local = _local(state)
            project_state = state.get("state")
            existing = fold_by_id(root / PUBLIC_BIBLIOGRAPHY)
            prior = next((item for item in existing if item.get("url") == cleaned_url), None)
            if prior is not None:
                return {
                    "status": "already_recorded",
                    "candidate": _public(prior),
                    "local_sources": local,
                    "project_state": project_state,
                }
            append_jsonl(root / PUBLIC_BIBLIOGRAPHY, record)
            append_jsonl(
                root / _AUDIT,
                {
                    "schema_version": "1.0.0",
                    "timestamp": utc_now(),
                    "source_id": None,
                    "operation": "record_candidate",
                    "origin": _ORIGIN,
                    "actor": _actor(actor),
                    "previous_hash": None,
                    "new_hash": record["text_sha256"],
                    "result": "recorded",
                    "tool": "public_source_record",
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


def list_public_sources(root: Path) -> dict[str, object]:
    """Read stored public candidates. Does not fetch, scan, verify, or assign authority."""

    records = [_listed(record) for record in fold_by_id(root / PUBLIC_BIBLIOGRAPHY)]
    return {"status": "ok", "records": records}


def public_source_count(root: Path) -> int:
    return len(fold_by_id(root / PUBLIC_BIBLIOGRAPHY))


def _listed(record: dict[str, object]) -> dict[str, object]:
    return {
        "title": record.get("title"),
        "url": record.get("url"),
        "state": "DISCOVERED",
        "classification": "PENDING",
        "authority": None,
    }


def _public(record: dict[str, object]) -> dict[str, object]:
    visible = {key: value for key, value in record.items() if key != "text"}
    visible["state"] = "DISCOVERED"
    visible["classification"] = "PENDING"
    visible["source_class"] = None
    visible["authority_status"] = None
    visible["authority"] = None
    return visible


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


def _authors(value: object) -> tuple[list[str] | None, str | None]:
    if value is None:
        return None, None
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return None, None
        if len(cleaned) > _MAX_AUTHOR:
            return None, "authors is too long to store"
        return [cleaned], None
    if not isinstance(value, list):
        return None, "authors must be a string or a list of strings"
    if len(value) > _MAX_AUTHORS:
        return None, "authors is too long to store"
    names: list[str] = []
    for item in value:
        if not isinstance(item, str):
            return None, "authors must be a string or a list of strings"
        cleaned = item.strip()
        if not cleaned:
            continue
        if len(cleaned) > _MAX_AUTHOR:
            return None, "authors is too long to store"
        names.append(cleaned)
    return (names or None), None


def _year(value: object) -> tuple[int | None, str | None]:
    if value is None:
        return None, None
    if isinstance(value, bool):
        return None, "year must be a number"
    if isinstance(value, int):
        number = value
    elif isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return None, None
        if not cleaned.isdigit():
            return None, "year must be a number"
        number = int(cleaned)
    else:
        return None, "year must be a number"
    if number < 1 or number > 9999:
        return None, "year must be a number"
    return number, None


def _kind(value: object) -> tuple[str | None, str | None]:
    if value is None:
        return None, None
    if not isinstance(value, str):
        return None, "kind must be a string"
    cleaned = value.strip()
    if not cleaned:
        return None, None
    if len(cleaned) > _MAX_KIND:
        return None, "kind is too long to store"
    return cleaned, None


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
