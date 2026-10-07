"""Apply ``course_recorded`` only when the existing ``course_json`` gate passes."""

from pathlib import Path

from studium.domain.enums import ProjectEvent, ProjectState
from studium.state.gates import COURSE_JSON, gate_for
from studium.state.machine import apply
from studium.storage.init_project import load_state_holding_lock, write_state
from studium.storage.locking import ProjectLocked, project_lock


def attempt_course_recorded(root: Path) -> dict[str, object]:
    """Transition only when ``course_json`` passes. A failed gate leaves state untouched."""

    try:
        with project_lock(root):
            document = load_state_holding_lock(root)
            current = _state(document.get("state"))
            if current is None:
                return _blocked(document.get("state"), "state.illegal_transition", "project state is not recognized")
            result = apply(
                current,
                ProjectEvent.COURSE_RECORDED.value,
                {COURSE_JSON: gate_for(COURSE_JSON)},
            )
            if not result.applied or result.entry is None or result.state is None:
                return {
                    "status": "gate",
                    "message": "gate",
                    "state": current.value,
                    "blockers": [
                        {"code": blocker.code, "entity_id": blocker.entity_id, "message": blocker.message}
                        for blocker in result.blockers
                    ],
                }
            history = document.get("history")
            entries = list(history) if isinstance(history, list) else []
            entries.append(
                {
                    "from": None if result.entry.from_state is None else result.entry.from_state.value,
                    "to": result.entry.to.value,
                    "event": result.entry.event,
                }
            )
            document["state"] = result.state.value
            document["history"] = entries
            write_state(root, document)
            return {"status": "ok", "state": result.state.value, "event": result.entry.event}
    except ProjectLocked:
        return {"status": "storage.locked", "message": "project is locked"}


def _state(value: object) -> ProjectState | None:
    if not isinstance(value, str):
        return None
    try:
        return ProjectState(value)
    except ValueError:
        return None


def _blocked(state: object, code: str, message: str) -> dict[str, object]:
    return {
        "status": "gate",
        "message": message,
        "state": state if isinstance(state, str) else None,
        "blockers": [{"code": code, "entity_id": None, "message": message}],
    }
