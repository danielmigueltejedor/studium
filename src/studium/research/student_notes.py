"""A Wuolah page or file the user already opened or attached.

The record is an unverified candidate. Origin is student_notes. It is not
authority and it is not the guide bibliography. The server does not log in,
does not bypass access, and does not download a catalog.
"""

import hashlib
from pathlib import Path
from urllib.parse import urlparse

from studium.domain.enums import SourceOrigin
from studium.policy.trust import contains_directive, directive_changes_policy
from studium.research.public_sources import license_forbids_use, openstax_host, unauthorized_copy
from studium.storage.init_project import load_state_holding_lock
from studium.storage.locking import ProjectLocked, project_lock
from studium.storage.migrate import utc_now
from studium.storage.records import PUBLIC_BIBLIOGRAPHY, append_jsonl, fold_by_id

_AUDIT = "audit/audit.jsonl"
_MAX_TEXT = 200_000
_MAX_TITLE = 500
_LICENSE = "a source whose license forbids this use is not recorded, as with OpenStax"
_BULK_PARTS = ("/search", "/catalog", "/explore", "/users", "/download-all")


def record_student_notes(
    root: Path,
    *,
    title: object,
    url: object = None,
    path: object = None,
    text: object = None,
    license_forbids: object = None,
    unauthorized: object = None,
    actor: dict[str, object] | None = None,
) -> dict[str, object]:
    """Store one opened note. Does not fetch the URL or scan a directory."""

    if unauthorized_copy(unauthorized):
        return _error("source.unauthorized", "pirate or unauthorized copies are not recorded")
    if license_forbids_use(license_forbids):
        return _error("source.license_forbidden", _LICENSE)
    cleaned_title = _title(title)
    if cleaned_title is None:
        return _error("mcp.invalid_input", "title is required")
    opened = _http_url(url) if url is not None else None
    if url is not None and opened is None:
        return _error("mcp.invalid_input", "url must be an http or https URL the user already opened")
    if opened is not None and openstax_host(opened):
        return _error("source.license_forbidden", _LICENSE)
    if opened is not None and _bulk(opened):
        return _error("source.catalog_refused", "do not bulk-download the catalog")
    if opened is not None and _login(opened):
        return _error("source.login_refused", "do not log in and do not bypass access")
    file_name, file_error = _file(path)
    if file_error is not None:
        return file_error
    if opened is None and file_name is None:
        return _error("mcp.invalid_input", "a page url or an attached file is required")
    body, text_error = _text(text)
    if text_error is not None:
        return _error("mcp.invalid_input", text_error)
    if isinstance(body, str) and directive_changes_policy(body):
        return _error("policy.overridden", "note text changed policy")
    identity = opened or file_name or cleaned_title
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    host = (urlparse(opened).hostname or "").lower() if opened is not None else ""
    kind = "wuolah" if "wuolah" in host else "student_notes"
    record: dict[str, object] = {
        "schema_version": "1.0.0",
        "id": digest,
        "title": cleaned_title,
        "origin": SourceOrigin.STUDENT_NOTES.value,
        "kind": kind,
        "state": "DISCOVERED",
        "classification": "PENDING",
        "source_class": None,
        "authority_status": None,
        "authority": None,
        "guide_bibliography": False,
        "course_guide_cited": False,
        "open_supplement": False,
        "text_present": isinstance(body, str),
        "content_directives_ignored": isinstance(body, str) and contains_directive(body.encode("utf-8")),
        "recorded_at": utc_now(),
    }
    if opened is not None:
        record["url"] = opened
    if file_name is not None:
        record["filename"] = file_name
    if isinstance(body, str):
        record["text"] = body
        record["text_sha256"] = hashlib.sha256(body.encode("utf-8")).hexdigest()
    try:
        with project_lock(root):
            state = load_state_holding_lock(root)
            prior = next((item for item in fold_by_id(root / PUBLIC_BIBLIOGRAPHY) if item.get("id") == digest), None)
            if prior is not None:
                return _body(state, prior, status="already_recorded")
            append_jsonl(root / PUBLIC_BIBLIOGRAPHY, record)
            append_jsonl(
                root / _AUDIT,
                {
                    "schema_version": "1.0.0",
                    "timestamp": utc_now(),
                    "source_id": digest,
                    "operation": "record_student_notes",
                    "origin": SourceOrigin.STUDENT_NOTES.value,
                    "actor": {"kind": actor.get("kind")} if isinstance(actor, dict) and isinstance(actor.get("kind"), str) else None,
                    "previous_hash": None,
                    "new_hash": record.get("text_sha256"),
                    "result": "recorded",
                    "tool": "student_notes_record",
                },
            )
            fresh = load_state_holding_lock(root)
            return _body(fresh, record, status="recorded")
    except ProjectLocked:
        return _error("storage.locked", "project is locked")


def _bulk(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    if path in {"", "/"}:
        return True
    lowered = path.lower()
    if any(part in lowered for part in _BULK_PARTS):
        return True
    return "bulk" in parsed.query.lower()


def _login(url: str) -> bool:
    lowered = url.lower()
    return any(part in lowered for part in ("login", "signin", "sign-in", "wp-login", "password="))


def _file(value: object) -> tuple[str | None, dict[str, object] | None]:
    if value is None:
        return None, None
    if not isinstance(value, str) or not value.strip():
        return None, _error("mcp.invalid_input", "path must be one file the user attached")
    candidate = Path(value.strip()).expanduser()
    if ".." in candidate.parts:
        return None, _error("mcp.invalid_input", "path must be one file the user attached")
    try:
        if candidate.is_symlink() or not candidate.is_file():
            return None, _error("mcp.invalid_input", "path must be one file the user attached, not a directory")
    except OSError:
        return None, _error("mcp.invalid_input", "path must be one file the user attached")
    return candidate.name, None


def _body(state: dict[str, object], record: dict[str, object], *, status: str) -> dict[str, object]:
    visible = {
        "id": record.get("id"),
        "title": record.get("title"),
        "url": record.get("url"),
        "filename": record.get("filename"),
        "origin": SourceOrigin.STUDENT_NOTES.value,
        "kind": record.get("kind"),
        "state": "DISCOVERED",
        "classification": "PENDING",
        "authority": None,
        "guide_bibliography": False,
        "course_guide_cited": False,
    }
    return {
        "status": status,
        "candidate": {
            key: value for key, value in visible.items() if value is not None or key == "authority"
        },
        "local_sources": _local(state),
        "project_state": state.get("state"),
        "released": state.get("state") == "RELEASED",
    }


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
    parsed = urlparse(cleaned)
    host = parsed.hostname or ""
    if parsed.scheme not in {"http", "https"} or not host or any(character.isspace() for character in cleaned):
        return None
    return cleaned


def _text(value: object) -> tuple[str | None, str | None]:
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


def _error(code: str, message: str) -> dict[str, object]:
    return {"status": code, "message": message}
