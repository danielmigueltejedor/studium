"""Create the four files a new Studium project is allowed to contain."""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import tomllib

from studium.domain.enums import ProjectEvent, ProjectState
from studium.domain.ids import IdAllocator
from studium.state.gates import PROJECT_TOML, Blocker, gate_for
from studium.state.machine import HistoryEntry, apply
from studium.storage.locking import ProjectLocked, project_lock
from studium.storage.migrate import initial_local_sources, migrate_state, utc_now

_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_PROFILES = frozenset(
    {
        "GENERAL",
        "STEM",
        "HUMANITIES",
        "SOCIAL_SCIENCES",
        "COMPUTER_SCIENCE",
        "LAW",
    }
)
_TASK_STATUSES = frozenset({"open", "blocked_human"})


@dataclass(frozen=True)
class CreateRequest:
    slug: str
    parent: Path
    name: str
    university: str
    degree: str
    academic_year: str | None = None
    course_code: str | None = None
    semester: str | None = None
    language: str | None = None
    domain_profile: str = "GENERAL"
    local_sources: str | None = None
    sources_present: bool = False


@dataclass(frozen=True)
class CreateResult:
    root: Path | None
    failure: str | None = None
    blockers: tuple[Blocker, ...] = ()


def local_sources_label(raw: str) -> str:
    path = Path(raw)
    if path.is_absolute():
        return path.name or raw
    return path.as_posix()


def create_project(request: CreateRequest) -> CreateResult:
    if _SLUG.fullmatch(request.slug) is None:
        return CreateResult(root=None, failure="invalid_slug")
    if request.domain_profile not in _PROFILES:
        return CreateResult(root=None, failure="invalid_profile")

    course = {
        "name": request.name,
        "university": request.university,
        "degree": request.degree,
    }
    gates = {PROJECT_TOML: gate_for(PROJECT_TOML, course)}
    opened = apply(None, ProjectEvent.PROJECT_CREATED.value, gates)
    if not opened.applied or opened.entry is None or opened.state is None:
        return CreateResult(root=None, failure="gate", blockers=opened.blockers)
    discovered = apply(opened.state, ProjectEvent.BEGIN_DISCOVERY.value, gates)
    if not discovered.applied or discovered.entry is None or discovered.state is not ProjectState.COURSE_DISCOVERY:
        return CreateResult(root=None, failure="gate", blockers=discovered.blockers)

    root = request.parent / request.slug
    if root.exists():
        return CreateResult(root=None, failure="already_exists")

    allocator = IdAllocator()
    task_id, allocator = allocator.allocate("TSK")
    now = utc_now()
    availability = "AVAILABLE" if request.sources_present else "UNKNOWN"
    state_document = _state_document(
        discovered.state,
        (opened.entry, discovered.entry),
        initial_local_sources(availability, now),
    )
    task = {
        "schema_version": "1.0.0",
        "id": task_id,
        "type": "course_discovery",
        "project_state": discovered.state.value,
        "entity_id": None,
        "status": "open",
        "dependencies": [],
        "blocked_reason": None,
        "created_at": now,
        "updated_at": now,
    }
    ids_document = {"schema_version": "1.0.0", "counters": dict(allocator.counters)}

    root.mkdir(parents=False)
    (root / ".studium").mkdir()
    (root / "tasks").mkdir()
    (root / "project.toml").write_text(render_project_toml(request), encoding="utf-8")
    (root / ".studium" / "state.json").write_text(_dump(state_document), encoding="utf-8")
    (root / ".studium" / "ids.json").write_text(_dump(ids_document), encoding="utf-8")
    (root / "tasks" / "tasks.jsonl").write_text(
        json.dumps(task, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return CreateResult(root=root)


def render_project_toml(request: CreateRequest) -> str:
    course_lines = [
        f"name = {_quote(request.name)}",
        f"university = {_quote(request.university)}",
        f"degree = {_quote(request.degree)}",
    ]
    optional = (
        ("academic_year", request.academic_year),
        ("course_code", request.course_code),
        ("semester", request.semester),
        ("language", request.language),
        ("domain_profile", request.domain_profile),
        ("local_sources", request.local_sources),
    )
    for key, value in optional:
        if value is not None:
            course_lines.append(f"{key} = {_quote(value)}")
    lines = [
        'schema_version = "1.0.0"',
        'edition = "0.1.0"',
        "",
        "[course]",
        *course_lines,
        "",
        "[overrides]",
        "",
    ]
    return "\n".join(lines)


def load_state(root: Path) -> dict[str, object]:
    """Load ``state.json``, migrating a stage 0 boolean in place when needed."""

    document = _read_state(root)
    migrated, changed = migrate_state(document, labeled=_sources_labeled(root))
    if not changed:
        return migrated
    try:
        with project_lock(root):
            current = _read_state(root)
            migrated, changed = migrate_state(current, labeled=_sources_labeled(root))
            if changed:
                _write_state(root, migrated)
    except ProjectLocked:
        return migrated
    return migrated


def load_state_holding_lock(root: Path) -> dict[str, object]:
    """Migrate and return state. The caller already holds ``project_lock``."""

    migrated, changed = migrate_state(_read_state(root), labeled=_sources_labeled(root))
    if changed:
        _write_state(root, migrated)
    return migrated


def read_state_unmigrated(root: Path) -> dict[str, object]:
    return _read_state(root)


def write_state(root: Path, document: dict[str, object]) -> None:
    _write_state(root, document)


def _read_state(root: Path) -> dict[str, object]:
    loaded = json.loads((root / ".studium" / "state.json").read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise TypeError("state document must be an object")
    return loaded


def _write_state(root: Path, document: dict[str, object]) -> None:
    (root / ".studium" / "state.json").write_text(_dump(document), encoding="utf-8")


def _sources_labeled(root: Path) -> bool:
    try:
        document = load_project_toml(root)
    except (OSError, tomllib.TOMLDecodeError):
        return False
    course = document.get("course")
    if not isinstance(course, dict):
        return False
    label = course.get("local_sources")
    return isinstance(label, str) and bool(label.strip())


def load_project_toml(root: Path) -> dict[str, object]:
    return tomllib.loads((root / "project.toml").read_text(encoding="utf-8"))


def load_tasks(root: Path) -> list[dict[str, object]]:
    path = root / "tasks" / "tasks.jsonl"
    if not path.is_file():
        return []
    folded: dict[str, dict[str, object]] = {}
    order: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if not isinstance(record, dict) or "id" not in record:
            continue
        identifier = str(record["id"])
        if identifier not in folded:
            order.append(identifier)
        folded[identifier] = record
    visible: list[dict[str, object]] = []
    for identifier in order:
        record = folded[identifier]
        if record.get("deleted") is True:
            continue
        visible.append(record)
    return visible


def select_next_task(tasks: list[dict[str, object]], state: str) -> dict[str, object] | None:
    done = {str(task["id"]) for task in tasks if task.get("status") == "done"}
    candidates: list[dict[str, object]] = []
    for task in tasks:
        if task.get("project_state") != state:
            continue
        if task.get("status") not in _TASK_STATUSES:
            continue
        dependencies = task.get("dependencies") or []
        if not isinstance(dependencies, list):
            continue
        if all(str(dependency) in done for dependency in dependencies):
            candidates.append(task)
    if not candidates:
        return None
    return min(candidates, key=_task_sort_key)


def _task_sort_key(task: Mapping[str, object]) -> tuple[int, str]:
    identifier = str(task["id"])
    number = identifier.split("-", 1)[1]
    return (int(number), identifier)


def _state_document(
    state: ProjectState,
    history: tuple[HistoryEntry, ...],
    local_sources: dict[str, object],
) -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "state": state.value,
        "edition_cycle": 1,
        "local_sources": local_sources,
        "history": [
            {
                "from": None if entry.from_state is None else entry.from_state.value,
                "to": entry.to.value,
                "event": entry.event,
            }
            for entry in history
        ],
    }


def _quote(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def _dump(document: object) -> str:
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


def _timestamp() -> str:
    return utc_now()
