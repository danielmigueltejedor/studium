"""User-source service. The CLI and MCP call these functions and no others.

There is one ``SRC-`` registry. Origin is the channel; ``source_class`` is
the authority tier. ``local_sources`` is a project sub-object, not a state.
"""

import hashlib
import re
from pathlib import Path

from studium.domain.enums import (
    COURSE_AUTHORITY,
    LOCAL_SOURCE_STATUSES,
    SCIENTIFIC_AUTHORITY,
    SOURCE_ORIGINS,
    SOURCE_ROLES,
)
from studium.policy.authority import authority_assignment_error, source_class_error
from studium.policy.trust import contains_directive, directive_changes_policy
from studium.research.attachments import attachment_to_intake
from studium.research.formats import ACCEPTED_FORMATS, sniff
from studium.research.guidance import local_source_guidance
from studium.research.impact import apply_impact, impact_report, record_support
from studium.storage.init_project import load_project_toml, load_state, load_state_holding_lock, write_state
from studium.storage.locking import ProjectLocked, project_lock
from studium.storage.migrate import utc_now
from studium.storage.records import allocate_id, append_jsonl, fold_by_id
from studium.validation.hashutil import canonical_hash

_REGISTRY = "sources/registry.jsonl"
_AUDIT = "audit/audit.jsonl"
_ENTITY = re.compile(
    r"^(SRC|EVD|CLM|CON|SYM|TRM|EQ|DER|FIG|EX|CH|REV|TSK|TOP|OUT|SKL|CNF|WAV|CST)-[0-9]{4,}$"
)
_DECISIONS = {"none": "NONE", "skipped": "SKIPPED", "available": "AVAILABLE"}
_PROBABLE_KINDS = frozenset(
    {
        "official_course_guide",
        "official_standard",
        "peer_reviewed_paper",
        "textbook",
        "professor_notes",
        "exam",
        "student_notes",
        "problem_sheet",
        "slides",
        "lab_material",
        "bibliography",
        "wuolah",
        "other",
    }
)
_SENSITIVE_DIRS = frozenset({".ssh", ".aws", ".gnupg", ".kube"})
_SENSITIVE_NAMES = frozenset(
    {
        "id_rsa",
        "id_ed25519",
        "id_dsa",
        "credentials",
        "credentials.json",
        ".env",
        "passwd",
        "shadow",
        "known_hosts",
    }
)


def project_status(root: Path) -> dict[str, object]:
    state = load_state(root)
    document = load_project_toml(root)
    course = document.get("course")
    course_fields = course if isinstance(course, dict) else {}
    local = _local(state)
    sources = _live(root)
    language = course_fields.get("language")
    return {
        "schema_version": state.get("schema_version"),
        "state": state.get("state"),
        "edition": document.get("edition"),
        "edition_cycle": state.get("edition_cycle"),
        "local_sources": local,
        "history": state.get("history"),
        "course": course_fields,
        "guidance": local_source_guidance(
            local,
            sources,
            language if isinstance(language, str) else None,
        ),
    }


def source_capabilities(root: Path) -> dict[str, object]:
    local = _local(load_state(root))
    return {
        "local_sources_supported": True,
        "status": local["status"],
        "prompted": local["prompted"],
        "accepted_formats": list(ACCEPTED_FORMATS),
        "private_by_default": True,
        "auto_upload": False,
    }


def source_status(root: Path) -> dict[str, object]:
    state = load_state(root)
    document = load_project_toml(root)
    course = document.get("course")
    language = course.get("language") if isinstance(course, dict) else None
    local = _local(state)
    payload: dict[str, object] = dict(local)
    payload.update(
        local_source_guidance(local, _live(root), language if isinstance(language, str) else None)
    )
    payload["capabilities"] = source_capabilities(root)
    return payload


def source_list(root: Path) -> dict[str, object]:
    sources = _live(root)
    return {"status": "ok", "sources": [_present(source, _successors(sources)) for source in sources]}


def source_get(root: Path, source_id: str) -> dict[str, object]:
    sources = _live(root)
    found = next((source for source in sources if source.get("id") == source_id), None)
    if found is None:
        return _error("sources.not_found", f"no source {source_id}", source_id=source_id)
    return {"status": "ok", "source": _present(found, _successors(sources))}


def source_add(
    root: Path,
    paths: list[str],
    *,
    origin: str | None = None,
    logical_id: str | None = None,
    supersedes: str | None = None,
    supports: list[str] | None = None,
    provided_by: str | None = None,
    actor: dict[str, object] | None = None,
) -> dict[str, object]:
    if not paths:
        return _error("mcp.invalid_input", "a file path is required")
    if supersedes and len(paths) != 1:
        return _error("sources.supersedes_ambiguous", "supersedes accepts one file")
    prepared: list[dict[str, object]] = []
    for raw in paths:
        item = _prepare_path(raw)
        if item.get("status") != "ready":
            return item
        prepared.append(item)
    return _commit(
        root,
        prepared,
        origin=origin or "local_private",
        logical_id=logical_id,
        supersedes=supersedes,
        supports=supports or [],
        provided_by=provided_by or "user",
        actor=actor,
        tool="source_intake",
    )


def source_intake_attachment(
    root: Path,
    *,
    handle: str,
    filename: str,
    content: bytes,
    logical_id: str | None = None,
    supersedes: str | None = None,
    supports: list[str] | None = None,
    provided_by: str | None = None,
    actor: dict[str, object] | None = None,
) -> dict[str, object]:
    try:
        draft = attachment_to_intake(handle, filename, content)
    except ValueError as exc:
        return _error(str(exc), "attachment was not authorized")
    sniffed = sniff(str(draft["filename"]), content)
    if sniffed is None:
        return _error("sources.format_unsupported", "file format is not accepted")
    _extension, media_type = sniffed
    if directive_changes_policy(content.decode("utf-8", errors="ignore")):
        return _error("policy.overridden", "source text changed policy")
    prepared = [
        {
            "status": "ready",
            "filename": draft["filename"],
            "content": content,
            "media_type": media_type,
            "sha256": hashlib.sha256(content).hexdigest(),
            "directives": contains_directive(content),
        }
    ]
    return _commit(
        root,
        prepared,
        origin="user_uploaded",
        logical_id=logical_id,
        supersedes=supersedes,
        supports=supports or [],
        provided_by=provided_by or "attachment",
        actor=actor,
        tool="source_intake",
    )


def source_register(
    root: Path,
    *,
    decision: str | None = None,
    mark_prompted: bool = False,
    actor: dict[str, object] | None = None,
) -> dict[str, object]:
    if decision is not None and decision not in _DECISIONS:
        return _error("mcp.invalid_input", "decision must be none, skipped, or available")
    if decision is None and not mark_prompted:
        return _error("mcp.invalid_input", "a decision or mark_prompted is required")
    try:
        with project_lock(root):
            state = load_state_holding_lock(root)
            local = _local(state)
            count = len(_live(root))
            if decision is not None and count >= 1:
                return _error(
                    "sources.availability_conflict",
                    "imported sources cannot be cleared by a decision",
                    local_sources=local,
                )
            updated = dict(local)
            changed = False
            if mark_prompted and updated["prompted"] is not True:
                updated["prompted"] = True
                changed = True
            if decision is not None:
                status = _DECISIONS[decision]
                if updated["status"] != status or updated["prompted"] is not True:
                    updated["status"] = status
                    updated["prompted"] = True
                    updated["source_count"] = 0
                    changed = True
            if not changed:
                return {"status": "ok", "local_sources": updated, "project_state": state.get("state")}
            updated["last_updated"] = utc_now()
            state["local_sources"] = updated
            write_state(root, state)
            _audit(
                root,
                source_id=None,
                operation="register",
                origin=None,
                actor=actor,
                previous_hash=None,
                new_hash=None,
                result=str(updated["status"]),
                tool="source_register",
            )
            return {"status": "ok", "local_sources": updated, "project_state": state.get("state")}
    except ProjectLocked:
        return _error("storage.locked", "project is locked")


def source_audit(
    root: Path,
    source_id: str,
    *,
    roles: list[str] | None = None,
    source_class: str | None = None,
    origin: str | None = None,
    course_authority: str | None = None,
    scientific_authority: str | None = None,
    probable_kind: str | None = None,
    peer_reviewed: bool | None = None,
    supports: list[str] | None = None,
    notes: str | None = None,
    actor: dict[str, object] | None = None,
) -> dict[str, object]:
    if source_class is not None:
        class_problem = source_class_error(source_class)
        if class_problem is not None:
            return _error(class_problem, "source class was rejected")
    if origin is not None and origin not in SOURCE_ORIGINS:
        return _error("sources.origin_invalid", "origin is not a known channel")
    if roles is not None:
        unknown = [role for role in roles if role not in SOURCE_ROLES]
        if unknown:
            return _error("sources.role_invalid", "unknown role", roles=unknown)
        if len(roles) != len(set(roles)):
            return _error("sources.role_invalid", "roles are duplicated")
    if course_authority is not None and course_authority not in COURSE_AUTHORITY:
        return _error("sources.authority_invalid", "course authority is not a known axis")
    if scientific_authority is not None and scientific_authority not in SCIENTIFIC_AUTHORITY:
        return _error("sources.authority_invalid", "scientific authority is not a known axis")
    if probable_kind is not None and probable_kind not in _PROBABLE_KINDS:
        return _error("sources.kind_invalid", "probable kind is not known")
    entity_problem = _entity_error(supports or [])
    if entity_problem is not None:
        return entity_problem
    try:
        with project_lock(root):
            state = load_state_holding_lock(root)
            current = _find(_live(root), source_id)
            if current is None:
                return _error("sources.not_found", f"no source {source_id}", source_id=source_id)
            updated = dict(current)
            if source_class is not None:
                updated["source_class"] = source_class
                updated["authority_status"] = source_class
            if origin is not None:
                updated["origin"] = origin
            if roles is not None:
                updated["roles"] = list(roles)
            if course_authority is not None:
                updated["course_authority"] = course_authority
            if scientific_authority is not None:
                updated["scientific_authority"] = scientific_authority
            if peer_reviewed is not None:
                updated["peer_reviewed"] = peer_reviewed
            if probable_kind is not None:
                updated["probable_kind"] = probable_kind
            problem = authority_assignment_error(
                source_class=updated.get("source_class") if isinstance(updated.get("source_class"), str) else None,
                scientific_authority=(
                    updated.get("scientific_authority")
                    if isinstance(updated.get("scientific_authority"), str)
                    else None
                ),
                peer_reviewed=updated.get("peer_reviewed") if isinstance(updated.get("peer_reviewed"), bool) else None,
                probable_kind=updated.get("probable_kind") if isinstance(updated.get("probable_kind"), str) else None,
            )
            if problem is not None:
                return _error(problem, "authority assignment was rejected")
            hostile_notes = bool(notes) and contains_directive(notes.encode("utf-8"))
            if hostile_notes:
                updated["content_directives_ignored"] = True
                updated["notes"] = ""
            elif notes is not None:
                if len(notes) > 280:
                    return _error("sources.notes_rejected", "notes are too long to store")
                updated["notes"] = notes
            if directive_changes_policy(str(notes or "")):
                return _error("policy.overridden", "source text changed policy")
            structured = any(
                (
                    roles is not None,
                    source_class is not None,
                    origin is not None,
                    course_authority is not None,
                    scientific_authority is not None,
                    probable_kind is not None,
                    peer_reviewed is not None,
                    bool(supports),
                )
            )
            if structured:
                updated["classification"] = "AUDITED"
            if updated.get("state") == "ACCEPTED" or updated.get("classification") in {"VERIFIED", "verified"}:
                return _error("sources.acceptance_forbidden", "audit does not accept a source")
            updated["state"] = current.get("state") if current.get("state") == "REJECTED" else "DISCOVERED"
            previous = canonical_hash(_stored(current))
            append_jsonl(root / _REGISTRY, _stored(updated))
            if supports:
                record_support(root, source_id, supports)
                apply_impact(
                    root,
                    source_id,
                    project_state=str(state.get("state")),
                    now=utc_now(),
                    allocate=lambda prefix: allocate_id(root, prefix),
                )
            _audit(
                root,
                source_id=source_id,
                operation="audit",
                origin=updated.get("origin") if isinstance(updated.get("origin"), str) else None,
                actor=actor,
                previous_hash=previous,
                new_hash=canonical_hash(_stored(updated)),
                result="audited",
                tool="source_audit",
            )
            fresh = _live(root)
            found = _find(fresh, source_id)
            return {
                "status": "audited",
                "source": _present(found or updated, _successors(fresh)),
                "next_action": "SOURCE_DISCOVERY",
                "project_state": state.get("state"),
            }
    except ProjectLocked:
        return _error("storage.locked", "project is locked")


def source_remove(root: Path, source_id: str, *, actor: dict[str, object] | None = None) -> dict[str, object]:
    try:
        with project_lock(root):
            state = load_state_holding_lock(root)
            current = _find(_live(root), source_id)
            if current is None:
                return _error("sources.not_found", f"no source {source_id}", source_id=source_id)
            if current.get("state") == "ACCEPTED":
                return _error("source.remove_blocked", "an accepted source still supports evidence")
            append_jsonl(
                root / _REGISTRY,
                {"schema_version": "1.0.0", "id": source_id, "deleted": True},
            )
            local = _recount(state, len(_live(root)))
            state["local_sources"] = local
            write_state(root, state)
            _audit(
                root,
                source_id=source_id,
                operation="remove",
                origin=current.get("origin") if isinstance(current.get("origin"), str) else None,
                actor=actor,
                previous_hash=str(current.get("sha256")),
                new_hash=None,
                result="removed",
                tool="source_remove",
            )
            return {
                "status": "ok",
                "source_id": source_id,
                "local_sources": local,
                "project_state": state.get("state"),
            }
    except ProjectLocked:
        return _error("storage.locked", "project is locked")


def source_reject(
    root: Path,
    source_id: str,
    *,
    reason: str,
    actor: dict[str, object] | None = None,
) -> dict[str, object]:
    if not isinstance(reason, str) or not reason.strip():
        return _error("mcp.invalid_input", "rejection_reason is required")
    try:
        with project_lock(root):
            state = load_state_holding_lock(root)
            current = _find(_live(root), source_id)
            if current is None:
                return _error("sources.not_found", f"no source {source_id}", source_id=source_id)
            if current.get("state") == "ACCEPTED":
                return _error("sources.reject_blocked", "an accepted source is not rejected here")
            if current.get("state") == "REJECTED" and current.get("rejection_reason") == reason:
                return {"status": "ok", "source_id": source_id, "state": "REJECTED", "project_state": state.get("state")}
            updated = dict(current)
            updated["state"] = "REJECTED"
            updated["rejection_reason"] = reason.strip()
            updated["classification"] = current.get("classification")
            append_jsonl(root / _REGISTRY, _stored(updated))
            _audit(
                root,
                source_id=source_id,
                operation="reject",
                origin=current.get("origin") if isinstance(current.get("origin"), str) else None,
                actor=actor,
                previous_hash=str(current.get("sha256")),
                new_hash=str(current.get("sha256")),
                result="rejected",
                tool="source_reject",
            )
            return {
                "status": "ok",
                "source_id": source_id,
                "state": "REJECTED",
                "project_state": state.get("state"),
            }
    except ProjectLocked:
        return _error("storage.locked", "project is locked")


def source_impact(root: Path, source_id: str) -> dict[str, object]:
    state = load_state(root)
    return impact_report(root, source_id, str(state.get("state")))


def release_safe_metadata(root: Path) -> list[dict[str, object]]:
    """Source slice of a release manifest: no bytes and no personal paths."""

    safe: list[dict[str, object]] = []
    for source in _live(root):
        safe.append(
            {
                "id": source.get("id"),
                "title": source.get("filename"),
                "sha256": source.get("sha256"),
                "classification": source.get("classification"),
                "origin": source.get("origin"),
                "source_class": source.get("source_class"),
                "roles": list(source.get("roles") or []),
            }
        )
    return safe


def _commit(
    root: Path,
    prepared: list[dict[str, object]],
    *,
    origin: str,
    logical_id: str | None,
    supersedes: str | None,
    supports: list[str],
    provided_by: str,
    actor: dict[str, object] | None,
    tool: str,
) -> dict[str, object]:
    if origin not in SOURCE_ORIGINS:
        return _error("sources.origin_invalid", "origin is not a known channel")
    if logical_id is not None and not _logical_ok(logical_id):
        return _error("sources.path_not_allowed", "logical identity cannot be a path")
    entity_problem = _entity_error(supports)
    if entity_problem is not None:
        return entity_problem
    try:
        with project_lock(root):
            state = load_state_holding_lock(root)
            project_state = state.get("state")
            existing = _live(root)
            planned: list[tuple[str, dict[str, object], dict[str, object] | None]] = []
            duplicates: list[dict[str, object]] = []
            for item in prepared:
                kind, prior = _classify(existing, str(item["sha256"]), logical_id, supersedes)
                if kind == "duplicate" and prior is not None:
                    duplicates.append(prior)
                    continue
                if kind == "conflict" and prior is not None:
                    return _error(
                        "sources.version_conflict",
                        "same logical source with a different hash",
                        source_id=prior.get("id"),
                        logical_id=logical_id,
                    )
                if kind == "missing_supersedes":
                    return _error("sources.supersedes_unknown", "supersedes does not name a source")
                planned.append((kind, item, prior))
            if not planned and len(duplicates) == 1:
                prior = duplicates[0]
                return {
                    "status": "already_registered",
                    "source_id": prior.get("id"),
                    "sha256": prior.get("sha256"),
                    "project_state": project_state,
                }
            if not planned:
                return {
                    "status": "already_registered",
                    "sources": [{"source_id": item.get("id"), "sha256": item.get("sha256")} for item in duplicates],
                    "project_state": project_state,
                }
            created: list[dict[str, object]] = []
            now = utc_now()
            for kind, item, prior in planned:
                source_id = allocate_id(root, "SRC")
                if not source_id.startswith("SRC-") or source_id.startswith("SRC-LOCAL-"):
                    return _error("id.unknown_prefix", "source ids stay on SRC-")
                previous_id = prior.get("id") if prior is not None else None
                record = _new_record(
                    source_id=source_id,
                    item=item,
                    origin=origin,
                    provided_by=provided_by,
                    now=now,
                    logical_id=logical_id or (prior.get("canonical_key") if prior else None),
                    supersedes=previous_id if kind == "version" else None,
                )
                append_jsonl(root / _REGISTRY, record)
                created.append(record)
                _audit(
                    root,
                    source_id=source_id,
                    operation="intake",
                    origin=origin,
                    actor=actor,
                    previous_hash=str(prior.get("sha256")) if prior is not None else None,
                    new_hash=str(item["sha256"]),
                    result="imported",
                    tool=tool,
                )
                if supports:
                    record_support(root, source_id, supports)
                if kind == "version":
                    apply_impact(
                        root,
                        source_id,
                        project_state=str(project_state),
                        now=now,
                        allocate=lambda prefix: allocate_id(root, prefix),
                    )
            local = _local(state)
            local["status"] = "IMPORTED"
            local["source_count"] = len(_live(root))
            local["last_updated"] = now
            state["local_sources"] = local
            write_state(root, state)
            fresh = _live(root)
            successors = _successors(fresh)
            body: dict[str, object] = {
                "status": "imported",
                "sources": [_present(_find(fresh, str(record["id"])) or record, successors) for record in created],
                "next_action": "SOURCE_AUDIT",
                "project_state": project_state,
            }
            if duplicates:
                body["already_registered"] = [
                    {"source_id": item.get("id"), "sha256": item.get("sha256")} for item in duplicates
                ]
            return body
    except ProjectLocked:
        return _error("storage.locked", "project is locked")


def _prepare_path(raw: str) -> dict[str, object]:
    candidate = Path(raw).expanduser()
    if _sensitive(candidate):
        return _error("security.credentials_forbidden", "refusing a credential path")
    if candidate.is_symlink():
        try:
            resolved = candidate.resolve()
        except OSError:
            return _error("security.symlink_escape", "symlink could not be resolved")
        if _sensitive(resolved):
            return _error("security.symlink_escape", "symlink leaves the authorized file")
    if not candidate.exists():
        return _error("sources.path_not_found", "file does not exist")
    if not candidate.is_file():
        return _error("sources.not_a_file", "intake accepts a file, not a directory scan")
    try:
        data = candidate.read_bytes()
    except OSError:
        return _error("sources.path_not_found", "file could not be read")
    filename = candidate.name
    sniffed = sniff(filename, data)
    if sniffed is None:
        return _error("sources.format_unsupported", "file format is not accepted")
    _extension, media_type = sniffed
    if directive_changes_policy(data.decode("utf-8", errors="ignore")):
        return _error("policy.overridden", "source text changed policy")
    return {
        "status": "ready",
        "filename": filename,
        "content": data,
        "media_type": media_type,
        "sha256": hashlib.sha256(data).hexdigest(),
        "directives": contains_directive(data),
    }


def _classify(
    existing: list[dict[str, object]],
    digest: str,
    logical_id: str | None,
    supersedes: str | None,
) -> tuple[str, dict[str, object] | None]:
    by_hash = next((source for source in existing if source.get("sha256") == digest), None)
    if by_hash is not None:
        return "duplicate", by_hash
    logical_match = None
    if logical_id:
        logical_match = next((source for source in existing if source.get("canonical_key") == logical_id), None)
    target = _find(existing, supersedes) if supersedes else None
    if supersedes and target is None:
        return "missing_supersedes", None
    if logical_match is not None and target is None:
        return "conflict", logical_match
    if target is not None:
        key = target.get("canonical_key")
        if logical_id and isinstance(key, str) and key and key != logical_id:
            return "conflict", target
        return "version", target
    return "new", None


def _new_record(
    *,
    source_id: str,
    item: dict[str, object],
    origin: str,
    provided_by: str,
    now: str,
    logical_id: object,
    supersedes: object,
) -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "id": source_id,
        "state": "DISCOVERED",
        "filename": item["filename"],
        "media_type": item["media_type"],
        "size_bytes": len(item["content"]) if isinstance(item["content"], bytes) else 0,
        "sha256": item["sha256"],
        "origin": origin,
        "source_class": None,
        "provided_by": provided_by,
        "ingested_at": now,
        "privacy": "PRIVATE",
        "rights_status": "unknown",
        "authority_status": None,
        "access_status": "LOCAL",
        "classification": "PENDING",
        "notes": "",
        "roles": [],
        "course_authority": None,
        "scientific_authority": None,
        "peer_reviewed": None,
        "probable_kind": None,
        "canonical_key": logical_id if isinstance(logical_id, str) and logical_id else None,
        "supersedes": supersedes if isinstance(supersedes, str) and supersedes else None,
        "content_directives_ignored": item.get("directives") is True,
        "rejection_reason": None,
    }


def _stored(record: dict[str, object]) -> dict[str, object]:
    stored = dict(record)
    stored.pop("new_version_of", None)
    stored.pop("content", None)
    return stored


def _present(record: dict[str, object], successors: dict[str, list[str]]) -> dict[str, object]:
    view = _stored(record)
    view.pop("content_directives_ignored", None)
    view["content_directives_ignored"] = record.get("content_directives_ignored") is True
    view["new_version_of"] = list(successors.get(str(record.get("id")), []))
    return view


def _successors(sources: list[dict[str, object]]) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for source in sources:
        previous = source.get("supersedes")
        identifier = source.get("id")
        if isinstance(previous, str) and previous and isinstance(identifier, str):
            found.setdefault(previous, []).append(identifier)
    return found


def _live(root: Path) -> list[dict[str, object]]:
    return fold_by_id(root / _REGISTRY)


def _find(sources: list[dict[str, object]], source_id: str | None) -> dict[str, object] | None:
    if not source_id:
        return None
    return next((source for source in sources if source.get("id") == source_id), None)


def _local(state: dict[str, object]) -> dict[str, object]:
    local = state.get("local_sources")
    if not isinstance(local, dict):
        return {"status": "UNKNOWN", "prompted": False, "source_count": 0, "last_updated": utc_now()}
    status = local.get("status")
    if status not in LOCAL_SOURCE_STATUSES:
        status = "UNKNOWN"
    count = local.get("source_count")
    if isinstance(count, bool) or not isinstance(count, int):
        count = 0
    return {
        "status": status,
        "prompted": local.get("prompted") is True,
        "source_count": count,
        "last_updated": local.get("last_updated"),
    }


def _recount(state: dict[str, object], count: int) -> dict[str, object]:
    local = _local(state)
    if count >= 1:
        local["status"] = "IMPORTED"
        local["source_count"] = count
    else:
        local["status"] = "AVAILABLE"
        local["source_count"] = 0
    local["last_updated"] = utc_now()
    return local


def _logical_ok(value: str) -> bool:
    if not value or len(value) > 200:
        return False
    return "/" not in value and "\\" not in value and not value.startswith("~")


def _entity_error(entity_ids: list[str]) -> dict[str, object] | None:
    for entity_id in entity_ids:
        if _ENTITY.fullmatch(entity_id) is None:
            return _error("mcp.invalid_input", "support target is not an entity id", entity_id=entity_id)
    return None


def _sensitive(path: Path) -> bool:
    if path.name in _SENSITIVE_NAMES:
        return True
    return bool(set(path.parts) & _SENSITIVE_DIRS)


def _audit(
    root: Path,
    *,
    source_id: str | None,
    operation: str,
    origin: str | None,
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
            "origin": origin,
            "actor": _safe_actor(actor),
            "previous_hash": previous_hash,
            "new_hash": new_hash,
            "result": result,
            "tool": tool,
        },
    )


def _safe_actor(actor: dict[str, object] | None) -> dict[str, object] | None:
    if not actor:
        return None
    safe: dict[str, object] = {}
    for key in ("kind", "name", "provider"):
        value = actor.get(key)
        if isinstance(value, str) and value and "/" not in value and "~" not in value and len(value) <= 80:
            safe[key] = value
    return safe or None


def _error(code: str, message: str, **extra: object) -> dict[str, object]:
    payload: dict[str, object] = {"status": code, "message": message}
    payload.update(extra)
    return payload
