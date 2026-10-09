"""Report blockers. Do not apply a transition and do not move the book to RELEASED."""

from pathlib import Path

from studium.authoring.paragraphs import corpus_started_blockers
from studium.authoring.support import evidence_blockers, excluded_drafts, supported_drafts
from studium.domain.enums import STATE_ORDER, ProjectState
from studium.domain.profiles import BOOK_COURSE, BOOK_TOPIC
from studium.research.course_documents import list_course_documents
from studium.state.gates import CORPUS_STARTED, COURSE_JSON, gate_for
from studium.state.machine import ENTRY_GATE
from studium.storage.init_project import book_kind, load_project_toml, load_state
from studium.storage.records import COURSE_CANDIDATES, fold_by_id


def verify_book(root: Path, *, mode: str = "full", entity: str | None = None) -> dict[str, object]:
    """Return blockers for every unpassed forward gate plus the bibliography.

    ``fast`` and ``full`` both refuse to release. Neither mode calls ``apply``.
    """

    if mode not in {"fast", "full"}:
        return {"status": "mcp.invalid_input", "message": "mode must be fast or full"}
    state = load_state(root)
    current = _state(state.get("state"))
    kind = book_kind(root)
    blockers: list[dict[str, object]] = []
    if current is None:
        blockers.append(
            {
                "code": "state.illegal_transition",
                "entity_id": None,
                "message": "project state is not recognized",
            }
        )
    else:
        blockers.extend(_forward_gates(root, current, kind))
    if kind == BOOK_COURSE and _guide_is_unverified(root):
        blockers.append(
            {
                "code": "verify.guide_unverified",
                "entity_id": None,
                "message": "the stored course guide is an unverified course document",
            }
        )
    blockers.extend(evidence_blockers(root))
    if entity is not None:
        blockers = [item for item in blockers if item.get("entity_id") in {None, entity}]
    drafts = [str(claim["id"]) for claim in supported_drafts(root) if isinstance(claim.get("id"), str)]
    excluded = [str(claim["id"]) for claim in excluded_drafts(root) if isinstance(claim.get("id"), str)]
    project_state = current.value if current is not None else state.get("state")
    return {
        "status": "gate",
        "message": "verification did not pass",
        "mode": mode,
        "applied": False,
        "released": project_state == ProjectState.RELEASED.value,
        "project_state": project_state,
        "local_sources": _local(state),
        "blockers": blockers,
        "draft_claims": drafts,
        "excluded_claims": excluded,
        "draft_writing": "allowed only for claims that passed the support check",
    }


def _forward_gates(root: Path, current: ProjectState, kind: str) -> list[dict[str, object]]:
    """Entry gates of later states. Passing a gate here does not change state."""

    index = STATE_ORDER.index(current)
    course = _course(root)
    documents = fold_by_id(root / COURSE_CANDIDATES)
    blockers: list[dict[str, object]] = []
    for later in STATE_ORDER[index + 1 :]:
        gate_name = ENTRY_GATE[later]
        if kind == BOOK_TOPIC and gate_name == COURSE_JSON:
            continue
        if gate_name == CORPUS_STARTED:
            blockers.extend(corpus_started_blockers(root))
            continue
        result = gate_for(gate_name, course, documents) if gate_name == COURSE_JSON else gate_for(gate_name)
        if result.ok:
            continue
        for blocker in result.blockers:
            blockers.append(
                {"code": blocker.code, "entity_id": blocker.entity_id, "message": blocker.message}
            )
    return blockers


def _guide_is_unverified(root: Path) -> bool:
    listed = list_course_documents(root)
    documents = listed.get("documents")
    if not isinstance(documents, list) or not documents:
        return False
    return any(
        isinstance(document, dict)
        and (document.get("classification") == "PENDING" or document.get("authority") is None)
        for document in documents
    )


def _course(root: Path) -> dict[str, object] | None:
    loaded = load_project_toml(root).get("course")
    if isinstance(loaded, dict):
        return loaded
    return None


def _state(value: object) -> ProjectState | None:
    if not isinstance(value, str):
        return None
    try:
        return ProjectState(value)
    except ValueError:
        return None


def _local(state: dict[str, object]) -> dict[str, object]:
    local = state.get("local_sources")
    if isinstance(local, dict):
        return dict(local)
    return {"status": "UNKNOWN", "prompted": False, "source_count": 0}
