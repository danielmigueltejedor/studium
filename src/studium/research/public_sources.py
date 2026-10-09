"""Public bibliography the client supplies.

This is not the user-source registry and it is not an official course document.
The server does not fetch the URL, search the web, or read the home directory.
Stored text is untrusted data. A record stays an unverified candidate.
A check compares an opened page with the stored citation. It does not assign
scientific authority and it does not mark the source accepted or verified.
"""

import hashlib
import re
from pathlib import Path
from urllib.parse import urlparse

from studium.domain.enums import SourceOrigin
from studium.domain.profiles import BOOK_TOPIC, WRITING_STILL_UNAVAILABLE
from studium.policy.trust import contains_directive, directive_changes_policy
from studium.storage.init_project import book_kind, load_state_holding_lock
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
_MAX_ISBN = 32
BIBLIOGRAPHIC_IDENTITY = "bibliographic_identity"
YEAR_CONFLICT_STATUS = "The observed year conflicts with the stored citation. Classification stays PENDING."
_IDENTITY_ONLY = "Bibliographic identity only. This is not proof of the book's claims."
_STILL_PENDING = "The opened page does not conflict with the stored citation. Classification stays PENDING."


_UNAUTHORIZED_KINDS = frozenset({"pirate", "pirated", "unauthorized", "unauthorised"})


def unauthorized_copy(value: object) -> bool:
    """True when the client marks a copy as pirate or unauthorized."""

    return value is True or (isinstance(value, str) and value.strip().lower() in _UNAUTHORIZED_KINDS | {"true", "yes"})


def license_forbids_use(value: object) -> bool:
    """True when the client says the license forbids this use."""

    return value is True or (isinstance(value, str) and "forbid" in value.lower())


def openstax_host(url: object) -> bool:
    """True for an OpenStax host. Used by media and student-note intake."""

    if not isinstance(url, str):
        return False
    host = urlparse(url).hostname or ""
    return host.lower().endswith("openstax.org")


def record_public_source(
    root: Path,
    *,
    title: object,
    url: object,
    authors: object = None,
    year: object = None,
    kind: object = None,
    isbn: object = None,
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
    if isinstance(source_kind, str) and source_kind.lower() in _UNAUTHORIZED_KINDS:
        return _error("source.unauthorized", "pirate or unauthorized copies are not recorded")
    publication_isbn, isbn_error = _isbn(isbn)
    if isbn_error is not None:
        return _error("mcp.invalid_input", isbn_error)
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
    if publication_isbn is not None:
        record["isbn"] = publication_isbn
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


def bibliography_counts(root: Path) -> dict[str, int]:
    """Pending, conflicting, and not-cited counts. Does not infer guide citation."""

    records = fold_by_id(root / PUBLIC_BIBLIOGRAPHY)
    return {
        "pending": sum(1 for record in records if record.get("classification") == "PENDING"),
        "conflicting": sum(1 for record in records if _has_conflicts(record)),
        "not_cited": sum(1 for record in records if record.get("course_guide_cited") is False),
    }


EXCERPT_BEFORE_DRAFT = (
    "Store an opened excerpt with studium_excerpt_record before writing a longer draft sentence."
)


def public_bibliography_next_action(root: Path) -> str:
    """Status text once public sources exist. A release stays unavailable.

    The next draft step is an excerpt the client opened. This does not fetch a URL.
    """

    counts = bibliography_counts(root)
    text = (
        f"{counts['pending']} pending, {counts['conflicting']} conflicting, "
        f"{counts['not_cited']} not cited by the stored course guide. "
        "Writing is still not available."
    )
    if book_kind(root) == BOOK_TOPIC:
        text += " Do not look for a university course guide. Do not call studium_course_recorded."
    return text + " " + EXCERPT_BEFORE_DRAFT


def check_public_source(
    root: Path,
    *,
    source_id: object,
    url: object,
    title: object,
    year: object = None,
    isbn: object = None,
    authors: object = None,
    actor: dict[str, object] | None = None,
) -> dict[str, object]:
    """Compare one opened page with the stored citation. Does not fetch the URL."""

    identifier = _identifier(source_id)
    if identifier is None:
        return _error("mcp.invalid_input", "id is required")
    opened = _http_url(url)
    if opened is None:
        return _error("mcp.invalid_input", "url must be an http or https URL the client already opened")
    observed_title = _title(title)
    if observed_title is None:
        return _error("mcp.invalid_input", "title is required")
    observed_year, year_error = _year(year)
    if year_error is not None:
        return _error("mcp.invalid_input", year_error)
    if observed_year is None:
        return _error("mcp.invalid_input", "year is required")
    observed_isbn, isbn_error = _isbn(isbn)
    if isbn_error is not None:
        return _error("mcp.invalid_input", isbn_error)
    observed_authors, author_error = _authors(authors)
    if author_error is not None:
        return _error("mcp.invalid_input", author_error)
    try:
        with project_lock(root):
            state = load_state_holding_lock(root)
            prior = _find(root, identifier)
            if prior is None:
                return _error("public_source.not_found", "no public source with that id")
            updated = _checked(
                prior,
                url=opened,
                title=observed_title,
                year=observed_year,
                isbn=observed_isbn,
                authors=observed_authors,
            )
            fresh_conflicts = _page_conflicts(updated, opened)
            if _unchanged_check(prior, updated):
                stored = prior
            else:
                append_jsonl(root / PUBLIC_BIBLIOGRAPHY, updated)
                _audit_public(
                    root,
                    source_id=identifier,
                    operation="check_bibliographic_identity",
                    actor=actor,
                    previous_hash=_text_hash(prior),
                    new_hash=_text_hash(updated),
                    result=_check_result(updated, fresh_conflicts),
                    tool="public_source_check",
                )
                stored = updated
            return _check_result_body(root, state, stored, fresh_conflicts)
    except ProjectLocked:
        return _error("storage.locked", "project is locked")


def mark_course_guide_citation(
    root: Path,
    *,
    source_id: object,
    cited: object,
    actor: dict[str, object] | None = None,
) -> dict[str, object]:
    """Record whether the client says the stored course guide cites this source.

    The server does not read the guide and does not infer the flag. ``False`` keeps the record.
    """

    identifier = _identifier(source_id)
    if identifier is None:
        return _error("mcp.invalid_input", "id is required")
    if not isinstance(cited, bool):
        return _error("mcp.invalid_input", "course_guide_cited must be true or false")
    try:
        with project_lock(root):
            state = load_state_holding_lock(root)
            prior = _find(root, identifier)
            if prior is None:
                return _error("public_source.not_found", "no public source with that id")
            if prior.get("course_guide_cited") is cited:
                stored = prior
            else:
                stored = _with_citation_flag(prior, cited)
                append_jsonl(root / PUBLIC_BIBLIOGRAPHY, stored)
                _audit_public(
                    root,
                    source_id=identifier,
                    operation="mark_course_guide_citation",
                    actor=actor,
                    previous_hash=_text_hash(prior),
                    new_hash=_text_hash(stored),
                    result="cited" if cited else "not_cited",
                    tool="public_source_guide_citation",
                )
            return _guide_result_body(root, state, stored, cited)
    except ProjectLocked:
        return _error("storage.locked", "project is locked")


def mark_open_supplement(
    root: Path,
    *,
    source_id: object,
    open_supplement: object,
    open_licensed: object = None,
    actor: dict[str, object] | None = None,
) -> dict[str, object]:
    """Flag a source the client opened as an open supplement.

    This does not fetch the URL and does not make the source part of the guide
    bibliography. A pirate or unauthorized copy is rejected.
    """

    identifier = _identifier(source_id)
    if identifier is None:
        return _error("mcp.invalid_input", "id is required")
    if not isinstance(open_supplement, bool):
        return _error("mcp.invalid_input", "open_supplement must be true or false")
    if open_supplement and open_licensed is not True:
        return _error(
            "source.unauthorized",
            "an open supplement must be open-licensed text you opened, not a pirate or unauthorized copy",
        )
    try:
        with project_lock(root):
            state = load_state_holding_lock(root)
            prior = _find(root, identifier)
            if prior is None:
                return _error("public_source.not_found", "no public source with that id")
            if prior.get("open_supplement") is open_supplement:
                stored = prior
            else:
                stored = _with_open_supplement(prior, open_supplement)
                append_jsonl(root / PUBLIC_BIBLIOGRAPHY, stored)
                _audit_public(
                    root,
                    source_id=identifier,
                    operation="mark_open_supplement",
                    actor=actor,
                    previous_hash=_text_hash(prior),
                    new_hash=_text_hash(stored),
                    result="open_supplement" if open_supplement else "not_open_supplement",
                    tool="public_source_open_supplement",
                )
            return _supplement_result_body(root, state, stored, open_supplement)
    except ProjectLocked:
        return _error("storage.locked", "project is locked")


def _listed(record: dict[str, object]) -> dict[str, object]:
    listed = {
        "id": record.get("id"),
        "title": record.get("title"),
        "url": record.get("url"),
        "state": "DISCOVERED",
        "classification": "PENDING",
        "authority": None,
    }
    if _has_conflicts(record):
        listed["conflicts"] = record.get("conflicts")
    if isinstance(record.get("course_guide_cited"), bool):
        listed["course_guide_cited"] = record.get("course_guide_cited")
    if record.get("open_supplement") is True:
        listed["open_supplement"] = True
        listed["guide_bibliography"] = False
    if record.get("origin") == SourceOrigin.STUDENT_NOTES.value:
        listed["origin"] = SourceOrigin.STUDENT_NOTES.value
        listed["guide_bibliography"] = False
        if isinstance(record.get("kind"), str):
            listed["kind"] = record["kind"]
    if record.get("identity") == BIBLIOGRAPHIC_IDENTITY:
        listed["identity"] = BIBLIOGRAPHIC_IDENTITY
    return listed


def _public(record: dict[str, object]) -> dict[str, object]:
    visible = {key: value for key, value in record.items() if key != "text"}
    visible["state"] = "DISCOVERED"
    visible["classification"] = "PENDING"
    visible["source_class"] = None
    visible["authority_status"] = None
    visible["authority"] = None
    if visible.get("identity") != BIBLIOGRAPHIC_IDENTITY:
        visible.pop("identity", None)
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


def _identifier(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned or len(cleaned) > 128:
        return None
    return cleaned


def _isbn(value: object) -> tuple[str | None, str | None]:
    if value is None:
        return None, None
    if not isinstance(value, str):
        return None, "isbn must be a string"
    cleaned = value.strip()
    if not cleaned:
        return None, None
    if len(cleaned) > _MAX_ISBN:
        return None, "isbn is too long to store"
    normalized = _norm_isbn(cleaned)
    if len(normalized) not in (10, 13):
        return None, "isbn must be an ISBN-10 or ISBN-13"
    if any(character == "X" for character in normalized[:-1]) or not all(
        character.isdigit() or character == "X" for character in normalized
    ):
        return None, "isbn must be an ISBN-10 or ISBN-13"
    return cleaned, None


def _find(root: Path, identifier: str) -> dict[str, object] | None:
    return next((item for item in fold_by_id(root / PUBLIC_BIBLIOGRAPHY) if item.get("id") == identifier), None)


def _has_conflicts(record: dict[str, object]) -> bool:
    conflicts = record.get("conflicts")
    return isinstance(conflicts, list) and len(conflicts) > 0


def _text_hash(record: dict[str, object]) -> str | None:
    value = record.get("text_sha256")
    return value if isinstance(value, str) else None


def _norm_title(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


def _norm_isbn(value: str) -> str:
    return "".join(character for character in value.upper() if character.isalnum())


def _author_key(names: list[str]) -> tuple[str, ...]:
    cleaned = [re.sub(r"\s+", " ", name.strip()).casefold() for name in names]
    return tuple(sorted(name for name in cleaned if name))


def _checked(
    prior: dict[str, object],
    *,
    url: str,
    title: str,
    year: int,
    isbn: str | None,
    authors: list[str] | None,
) -> dict[str, object]:
    updated = dict(prior)
    updated["state"] = "DISCOVERED"
    updated["classification"] = "PENDING"
    updated["source_class"] = None
    updated["authority_status"] = None
    updated["authority"] = None
    corroborations = _corroborations(prior)
    entry: dict[str, object] = {"url": url, "title": title, "year": year}
    if authors is not None:
        entry["authors"] = authors
    if isbn is not None:
        entry["isbn"] = isbn
    replaced = False
    refreshed: list[dict[str, object]] = []
    for item in corroborations:
        if item.get("url") == url:
            refreshed.append(entry)
            replaced = True
        else:
            refreshed.append(item)
    if not replaced:
        refreshed.append(entry)
    updated["corroborations"] = refreshed
    conflicts = [item for item in _conflict_list(prior) if item.get("url") != url]
    conflicts.extend(_citation_conflicts(prior, title=title, year=year, isbn=isbn, url=url))
    if conflicts:
        updated["conflicts"] = conflicts
    else:
        updated.pop("conflicts", None)
    if conflicts or not _identity_established(refreshed, prior):
        updated.pop("identity", None)
    else:
        updated["identity"] = BIBLIOGRAPHIC_IDENTITY
    return updated


def _corroborations(record: dict[str, object]) -> list[dict[str, object]]:
    value = record.get("corroborations")
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _conflict_list(record: dict[str, object]) -> list[dict[str, object]]:
    value = record.get("conflicts")
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _citation_conflicts(
    stored: dict[str, object],
    *,
    title: str,
    year: int,
    isbn: str | None,
    url: str,
) -> list[dict[str, object]]:
    found: list[dict[str, object]] = []
    stored_year = stored.get("year")
    if isinstance(stored_year, int) and not isinstance(stored_year, bool) and stored_year != year:
        found.append({"field": "year", "stored": stored_year, "observed": year, "url": url})
    stored_title = stored.get("title")
    if isinstance(stored_title, str) and _norm_title(stored_title) != _norm_title(title):
        found.append({"field": "title", "stored": stored_title, "observed": title, "url": url})
    stored_isbn = stored.get("isbn")
    if isinstance(stored_isbn, str) and isbn is not None and _norm_isbn(stored_isbn) != _norm_isbn(isbn):
        found.append({"field": "isbn", "stored": stored_isbn, "observed": isbn, "url": url})
    return found


def _identity_established(corroborations: list[dict[str, object]], stored: dict[str, object]) -> bool:
    agreeing: list[dict[str, object]] = []
    seen: set[str] = set()
    for entry in corroborations:
        url = entry.get("url")
        authors = entry.get("authors")
        if not isinstance(url, str) or url in seen:
            continue
        if not isinstance(authors, list) or not _agrees_with_citation(entry, stored):
            continue
        seen.add(url)
        agreeing.append(entry)
    if len(agreeing) < 2:
        return False
    keys: list[tuple[str, ...]] = []
    for entry in agreeing:
        raw_authors = entry.get("authors")
        if isinstance(raw_authors, list):
            keys.append(_author_key(raw_authors))
    if len(keys) != len(agreeing) or any(not key for key in keys) or len(set(keys)) != 1:
        return False
    stored_authors = stored.get("authors")
    if isinstance(stored_authors, list) and stored_authors:
        return keys[0] == _author_key(stored_authors)
    return True


def _agrees_with_citation(entry: dict[str, object], stored: dict[str, object]) -> bool:
    stored_title = stored.get("title")
    observed_title = entry.get("title")
    if not isinstance(stored_title, str) or not isinstance(observed_title, str):
        return False
    if _norm_title(stored_title) != _norm_title(observed_title):
        return False
    stored_year = stored.get("year")
    observed_year = entry.get("year")
    if not isinstance(stored_year, int) or isinstance(stored_year, bool):
        return False
    if stored_year != observed_year:
        return False
    stored_isbn = stored.get("isbn")
    observed_isbn = entry.get("isbn")
    if isinstance(stored_isbn, str) and isinstance(observed_isbn, str):
        return _norm_isbn(stored_isbn) == _norm_isbn(observed_isbn)
    return True


def _page_conflicts(record: dict[str, object], url: str) -> list[dict[str, object]]:
    return [item for item in _conflict_list(record) if item.get("url") == url]


def _unchanged_check(prior: dict[str, object], updated: dict[str, object]) -> bool:
    return (
        prior.get("corroborations") == updated.get("corroborations")
        and prior.get("conflicts") == updated.get("conflicts")
        and prior.get("identity") == updated.get("identity")
    )


def _check_result(record: dict[str, object], fresh_conflicts: list[dict[str, object]]) -> str:
    if fresh_conflicts or _has_conflicts(record):
        return "bibliographic_conflict"
    if record.get("identity") == BIBLIOGRAPHIC_IDENTITY:
        return BIBLIOGRAPHIC_IDENTITY
    return "checked"


def _conflict_message(conflicts: list[dict[str, object]]) -> str:
    fields: list[str] = []
    for item in conflicts:
        field = item.get("field")
        if isinstance(field, str) and field in {"year", "title", "isbn"} and field not in fields:
            fields.append(field)
    if fields == ["year"]:
        return YEAR_CONFLICT_STATUS
    labels = {"year": "year", "title": "title", "isbn": "ISBN"}
    sentences = [f"The observed {labels[field]} conflicts with the stored citation." for field in fields]
    if not sentences:
        return "The opened page conflicts with the stored citation. Classification stays PENDING."
    return " ".join(sentences) + " Classification stays PENDING."


def _check_result_body(
    root: Path,
    state: dict[str, object],
    record: dict[str, object],
    fresh_conflicts: list[dict[str, object]],
) -> dict[str, object]:
    identity = record.get("identity") if record.get("identity") == BIBLIOGRAPHIC_IDENTITY else None
    if fresh_conflicts:
        status = "bibliographic_conflict"
        message = _conflict_message(fresh_conflicts)
    elif _has_conflicts(record):
        status = "bibliographic_conflict"
        message = "A stored citation conflict remains. Classification stays PENDING."
    elif identity == BIBLIOGRAPHIC_IDENTITY:
        status = BIBLIOGRAPHIC_IDENTITY
        message = _IDENTITY_ONLY
    else:
        status = "ok"
        message = _STILL_PENDING
    return {
        "status": status,
        "message": message,
        "classification": "PENDING",
        "state": "DISCOVERED",
        "authority": None,
        "source_class": None,
        "authority_status": None,
        "identity": identity,
        "candidate": _public(record),
        "local_sources": _local(state),
        "project_state": state.get("state"),
        "next_action": public_bibliography_next_action(root),
        "writing_available": False,
        "writing_status": WRITING_STILL_UNAVAILABLE,
    }


def _with_open_supplement(prior: dict[str, object], open_supplement: bool) -> dict[str, object]:
    updated = dict(prior)
    updated["state"] = "DISCOVERED"
    updated["classification"] = "PENDING"
    updated["source_class"] = None
    updated["authority_status"] = None
    updated["authority"] = None
    updated["open_supplement"] = open_supplement
    updated["guide_bibliography"] = False
    if updated.get("identity") != BIBLIOGRAPHIC_IDENTITY:
        updated.pop("identity", None)
    return updated


def _supplement_result_body(
    root: Path,
    state: dict[str, object],
    record: dict[str, object],
    open_supplement: bool,
) -> dict[str, object]:
    return {
        "status": "ok",
        "open_supplement": open_supplement,
        "guide_bibliography": False,
        "classification": "PENDING",
        "state": "DISCOVERED",
        "authority": None,
        "candidate": _public(record),
        "local_sources": _local(state),
        "project_state": state.get("state"),
        "next_action": public_bibliography_next_action(root),
        "writing_available": False,
        "writing_status": WRITING_STILL_UNAVAILABLE,
    }


def _with_citation_flag(prior: dict[str, object], cited: bool) -> dict[str, object]:
    updated = dict(prior)
    updated["state"] = "DISCOVERED"
    updated["classification"] = "PENDING"
    updated["source_class"] = None
    updated["authority_status"] = None
    updated["authority"] = None
    updated["course_guide_cited"] = cited
    if updated.get("identity") != BIBLIOGRAPHIC_IDENTITY:
        updated.pop("identity", None)
    return updated


def _guide_result_body(
    root: Path,
    state: dict[str, object],
    record: dict[str, object],
    cited: bool,
) -> dict[str, object]:
    return {
        "status": "ok",
        "course_guide_cited": cited,
        "classification": "PENDING",
        "state": "DISCOVERED",
        "authority": None,
        "candidate": _public(record),
        "local_sources": _local(state),
        "project_state": state.get("state"),
        "next_action": public_bibliography_next_action(root),
        "writing_available": False,
        "writing_status": WRITING_STILL_UNAVAILABLE,
    }


def _audit_public(
    root: Path,
    *,
    source_id: str,
    operation: str,
    actor: dict[str, object] | None,
    previous_hash: str | None,
    new_hash: str | None,
    result: str,
    tool: str,
) -> None:
    append_jsonl(
        root / _AUDIT,
        {
            "schema_version": "1.0.0",
            "timestamp": utc_now(),
            "source_id": source_id,
            "operation": operation,
            "origin": _ORIGIN,
            "actor": _actor(actor),
            "previous_hash": previous_hash,
            "new_hash": new_hash,
            "result": result,
            "tool": tool,
        },
    )
