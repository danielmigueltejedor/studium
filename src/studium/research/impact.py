"""Source impact. One walk, shared by intake and ``studium_source_impact``.

Marks are not project states. ``STALE`` is calculated from the binding hash.
``new_version_of`` is not stored; callers derive it from ``supersedes``.
"""

from pathlib import Path

from studium.storage.records import append_jsonl, fold_by_id, read_jsonl
from studium.validation.hashutil import canonical_hash

_EDGES = "graph/edges.jsonl"
_FRESHNESS = "sources/freshness.jsonl"
_REVIEWS = "reviews/reviews.jsonl"
_RESULTS = "verification/results.jsonl"
_EVIDENCE = "evidence/evidence.jsonl"


def entity_binding_hash(entity_id: str, links: list[tuple[str, str]]) -> str:
    payload = {"entity_id": entity_id, "sources": sorted(links)}
    return canonical_hash(payload)


def superseded_ids(sources: list[dict[str, object]]) -> set[str]:
    found: set[str] = set()
    for source in sources:
        previous = source.get("supersedes")
        if isinstance(previous, str) and previous:
            found.add(previous)
    return found


def support_links(
    entity_id: str,
    sources: list[dict[str, object]],
    edges: list[dict[str, object]],
) -> list[tuple[str, str]]:
    by_id = {str(source["id"]): source for source in sources}
    retired = superseded_ids(sources)
    links: list[tuple[str, str]] = []
    for edge in edges:
        if edge.get("type") != "supports" or edge.get("to") != entity_id:
            continue
        source_id = edge.get("from")
        if not isinstance(source_id, str) or source_id in retired:
            continue
        source = by_id.get(source_id)
        if source is None:
            continue
        links.append((source_id, str(source.get("sha256"))))
    return links


def affected_entity_ids(
    source_id: str,
    sources: list[dict[str, object]],
    edges: list[dict[str, object]],
) -> list[str]:
    by_id = {str(source["id"]): source for source in sources}
    focus = by_id.get(source_id)
    if focus is None:
        return []
    watched = {source_id}
    previous = focus.get("supersedes")
    if isinstance(previous, str) and previous:
        watched.add(previous)
    ordered: list[str] = []
    seen: set[str] = set()
    for edge in edges:
        if edge.get("type") != "supports" or edge.get("from") not in watched:
            continue
        entity = edge.get("to")
        if isinstance(entity, str) and entity not in seen:
            seen.add(entity)
            ordered.append(entity)
    return ordered


def current_binding_hash(root: Path, entity_id: str) -> str:
    sources = fold_by_id(root / "sources" / "registry.jsonl")
    edges = read_jsonl(root / _EDGES)
    return entity_binding_hash(entity_id, support_links(entity_id, sources, edges))


def review_mark(review: dict[str, object] | None, current_hash: str) -> str | None:
    if review is None:
        return None
    stored = review.get("entity_binding_hash")
    if stored != current_hash:
        return "STALE"
    verdict = review.get("verdict")
    if not isinstance(verdict, str):
        verdict = review.get("status")
    return str(verdict) if isinstance(verdict, str) else None


def record_support(root: Path, source_id: str, entity_ids: list[str]) -> None:
    existing = {
        (edge.get("from"), edge.get("to"))
        for edge in read_jsonl(root / _EDGES)
        if edge.get("type") == "supports"
    }
    for entity_id in entity_ids:
        if (source_id, entity_id) in existing:
            continue
        append_jsonl(
            root / _EDGES,
            {
                "schema_version": "1.0.0",
                "type": "supports",
                "from": source_id,
                "to": entity_id,
            },
        )


def apply_impact(
    root: Path,
    source_id: str,
    *,
    project_state: str,
    now: str,
    allocate,
) -> list[str]:
    """Mark affected entities DIRTY and open review tasks. Returns task ids."""

    sources = fold_by_id(root / "sources" / "registry.jsonl")
    edges = read_jsonl(root / _EDGES)
    entities = affected_entity_ids(source_id, sources, edges)
    opened: list[str] = []
    for entity_id in entities:
        append_jsonl(
            root / _FRESHNESS,
            {
                "schema_version": "1.0.0",
                "entity_id": entity_id,
                "mark": "DIRTY",
                "review_required": True,
                "source_id": source_id,
                "at": now,
            },
        )
        opened.extend(_ensure_task(root, entity_id, "review_entity", project_state, now, allocate))
        if _has_verification(root, entity_id):
            opened.extend(
                _ensure_task(root, entity_id, "verify_entity", project_state, now, allocate)
            )
    return opened


def impact_report(root: Path, source_id: str, project_state: str) -> dict[str, object]:
    sources = fold_by_id(root / "sources" / "registry.jsonl")
    if not any(source.get("id") == source_id for source in sources):
        return {"status": "sources.not_found", "message": f"no source {source_id}", "source_id": source_id}
    edges = read_jsonl(root / _EDGES)
    entities = affected_entity_ids(source_id, sources, edges)
    reviews = _latest_by_entity(root / _REVIEWS)
    verifications = _latest_by_entity(root / _RESULTS)
    affected: list[dict[str, object]] = []
    for entity_id in entities:
        current = entity_binding_hash(entity_id, support_links(entity_id, sources, edges))
        affected.append(
            {
                "entity_id": entity_id,
                "mark": "DIRTY",
                "review": review_mark(reviews.get(entity_id), current),
                "verification": review_mark(verifications.get(entity_id), current),
            }
        )
    return {
        "status": "ok",
        "source_id": source_id,
        "project_state": project_state,
        "affected": affected,
        "blockers": _superseded_evidence(root, sources),
        "tasks": _open_tasks(root, set(entities)),
    }


def _has_verification(root: Path, entity_id: str) -> bool:
    return entity_id in _latest_by_entity(root / _RESULTS)


def _latest_by_entity(path: Path) -> dict[str, dict[str, object]]:
    found: dict[str, dict[str, object]] = {}
    for record in read_jsonl(path):
        entity = record.get("entity_id")
        if isinstance(entity, str):
            found[entity] = record
    return found


def _superseded_evidence(root: Path, sources: list[dict[str, object]]) -> list[dict[str, object]]:
    retired = superseded_ids(sources)
    blockers: list[dict[str, object]] = []
    for record in read_jsonl(root / _EVIDENCE):
        source_id = record.get("source_id")
        if source_id not in retired:
            continue
        entailment = record.get("entailment")
        if entailment not in {"DIRECT_SUPPORT", "PARTIAL_SUPPORT"}:
            continue
        blockers.append(
            {
                "code": "evidence.superseded_source",
                "entity_id": record.get("claim_id"),
                "source_id": source_id,
            }
        )
    return blockers


def _open_tasks(root: Path, entities: set[str]) -> list[dict[str, object]]:
    tasks: list[dict[str, object]] = []
    for record in fold_by_id(root / "tasks" / "tasks.jsonl"):
        if record.get("entity_id") not in entities:
            continue
        if record.get("status") != "open":
            continue
        if record.get("type") not in {"review_entity", "verify_entity"}:
            continue
        tasks.append({"id": record.get("id"), "type": record.get("type"), "entity_id": record.get("entity_id")})
    return tasks


def _ensure_task(root, entity_id, task_type, project_state, now, allocate) -> list[str]:
    for record in fold_by_id(root / "tasks" / "tasks.jsonl"):
        if (
            record.get("entity_id") == entity_id
            and record.get("type") == task_type
            and record.get("status") == "open"
        ):
            return []
    task_id = allocate("TSK")
    append_jsonl(
        root / "tasks" / "tasks.jsonl",
        {
            "schema_version": "1.0.0",
            "id": task_id,
            "type": task_type,
            "project_state": project_state,
            "entity_id": entity_id,
            "status": "open",
            "dependencies": [],
            "blocked_reason": None,
            "created_at": now,
            "updated_at": now,
        },
    )
    return [task_id]
