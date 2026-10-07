"""Pure project state machine.

``apply`` does not read or write the filesystem. A transition that is not
in the table is ``state.illegal_transition``. A legal transition whose
entry gate is missing or not ok does not change the state.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone

from studium.domain.enums import STATE_ORDER, ProjectEvent, ProjectState
from studium.state.gates import (
    AUTHORING_COMPLETE,
    BLUEPRINT_ACCEPTED,
    COURSE_JSON,
    CORPUS_STARTED,
    CORPUS_SUFFICIENT,
    PROJECT_TOML,
    RELEASE,
    RELEASE_INTACT,
    REVIEWS_CURRENT,
    VERIFICATION_PASSED,
    Blocker,
    GateResult,
    gate_for,
)

ENTRY_GATE: dict[ProjectState, str] = {
    ProjectState.CREATED: PROJECT_TOML,
    ProjectState.COURSE_DISCOVERY: PROJECT_TOML,
    ProjectState.SOURCE_DISCOVERY: COURSE_JSON,
    ProjectState.CORPUS_BUILDING: CORPUS_STARTED,
    ProjectState.BLUEPRINT: CORPUS_SUFFICIENT,
    ProjectState.AUTHORING: BLUEPRINT_ACCEPTED,
    ProjectState.VERIFYING: AUTHORING_COMPLETE,
    ProjectState.REVIEWING: VERIFICATION_PASSED,
    ProjectState.RELEASE_CANDIDATE: REVIEWS_CURRENT,
    ProjectState.RELEASED: RELEASE,
}

_FORWARD: dict[tuple[ProjectState | None, str], tuple[ProjectState, str]] = {
    (None, ProjectEvent.PROJECT_CREATED.value): (ProjectState.CREATED, PROJECT_TOML),
    (ProjectState.CREATED, ProjectEvent.BEGIN_DISCOVERY.value): (
        ProjectState.COURSE_DISCOVERY,
        PROJECT_TOML,
    ),
    (ProjectState.COURSE_DISCOVERY, ProjectEvent.COURSE_RECORDED.value): (
        ProjectState.SOURCE_DISCOVERY,
        COURSE_JSON,
    ),
    (ProjectState.SOURCE_DISCOVERY, ProjectEvent.CORPUS_STARTED.value): (
        ProjectState.CORPUS_BUILDING,
        CORPUS_STARTED,
    ),
    (ProjectState.CORPUS_BUILDING, ProjectEvent.CORPUS_SUFFICIENT.value): (
        ProjectState.BLUEPRINT,
        CORPUS_SUFFICIENT,
    ),
    (ProjectState.BLUEPRINT, ProjectEvent.BLUEPRINT_ACCEPTED.value): (
        ProjectState.AUTHORING,
        BLUEPRINT_ACCEPTED,
    ),
    (ProjectState.AUTHORING, ProjectEvent.AUTHORING_COMPLETE.value): (
        ProjectState.VERIFYING,
        AUTHORING_COMPLETE,
    ),
    (ProjectState.VERIFYING, ProjectEvent.VERIFICATION_PASSED.value): (
        ProjectState.REVIEWING,
        VERIFICATION_PASSED,
    ),
    (ProjectState.REVIEWING, ProjectEvent.REVIEWS_CURRENT.value): (
        ProjectState.RELEASE_CANDIDATE,
        REVIEWS_CURRENT,
    ),
    (ProjectState.RELEASE_CANDIDATE, ProjectEvent.RELEASE.value): (
        ProjectState.RELEASED,
        RELEASE,
    ),
    (ProjectState.RELEASED, ProjectEvent.REFRESH_COURSE.value): (
        ProjectState.COURSE_DISCOVERY,
        RELEASE_INTACT,
    ),
}


@dataclass(frozen=True)
class HistoryEntry:
    from_state: ProjectState | None
    to: ProjectState
    event: str
    at: str


@dataclass(frozen=True)
class ApplyResult:
    applied: bool
    state: ProjectState | None
    entry: HistoryEntry | None
    blockers: tuple[Blocker, ...]


def required_gate(state: ProjectState | None, event: str) -> str | None:
    found = _FORWARD.get((state, event))
    if found is None:
        return None
    return found[1]


def earlier_gates_fail(state: ProjectState, gates: Mapping[str, GateResult]) -> bool:
    index = STATE_ORDER.index(state)
    return any(_gate_blockers(gates, ENTRY_GATE[candidate]) is not None for candidate in STATE_ORDER[:index])


def apply(
    state: ProjectState | None,
    event: str,
    gates: Mapping[str, GateResult],
) -> ApplyResult:
    if event == ProjectEvent.REGRESS.value:
        if not isinstance(state, ProjectState):
            return _refuse(state, "state.illegal_transition", "cannot regress without a project state")
        return _regress(state, gates)

    found = _FORWARD.get((state, event))
    if found is None:
        label = state.value if isinstance(state, ProjectState) else "none"
        return _refuse(state, "state.illegal_transition", f"cannot apply {event} from {label}")

    destination, gate_name = found
    blockers = _gate_blockers(gates, gate_name)
    if blockers is not None:
        return ApplyResult(applied=False, state=state, entry=None, blockers=blockers)

    entry = HistoryEntry(
        from_state=state if isinstance(state, ProjectState) else None,
        to=destination,
        event=event,
        at=_timestamp(),
    )
    return ApplyResult(applied=True, state=destination, entry=entry, blockers=())


def _regress(state: ProjectState, gates: Mapping[str, GateResult]) -> ApplyResult:
    index = STATE_ORDER.index(state)
    for candidate in reversed(STATE_ORDER[:index]):
        if _gate_blockers(gates, ENTRY_GATE[candidate]) is None:
            entry = HistoryEntry(
                from_state=state,
                to=candidate,
                event=ProjectEvent.REGRESS.value,
                at=_timestamp(),
            )
            return ApplyResult(applied=True, state=candidate, entry=entry, blockers=())
    return _refuse(
        state,
        "state.regress_target",
        "no earlier state has a passing entry gate",
    )


def _gate_blockers(gates: Mapping[str, GateResult], name: str) -> tuple[Blocker, ...] | None:
    result = gates.get(name)
    if result is None:
        return gate_for(name).blockers
    if result.ok:
        return None
    if result.blockers:
        return result.blockers
    return gate_for(name).blockers


def _refuse(state: ProjectState | None, code: str, message: str) -> ApplyResult:
    return ApplyResult(
        applied=False,
        state=state,
        entry=None,
        blockers=(Blocker(code=code, entity_id=None, message=message),),
    )


def _timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
