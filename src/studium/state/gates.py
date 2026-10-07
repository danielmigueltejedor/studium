"""Entry gates for the project state machine.

Only the ``project.toml`` gate has a predicate. Every other gate fails
closed with ``state.gate_not_implemented``.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from studium.domain.profiles import BOOK_TOPIC

PROJECT_TOML = "project_toml"
COURSE_JSON = "course_json"
CORPUS_STARTED = "corpus_started"
CORPUS_SUFFICIENT = "corpus_sufficient"
BLUEPRINT_ACCEPTED = "blueprint_accepted"
AUTHORING_COMPLETE = "authoring_complete"
VERIFICATION_PASSED = "verification_passed"
REVIEWS_CURRENT = "reviews_current"
RELEASE = "release"
RELEASE_INTACT = "release_intact"

_REQUIRED_COURSE_FIELDS = ("name", "university", "degree")
_REQUIRED_TOPIC_FIELDS = ("name",)


@dataclass(frozen=True)
class Blocker:
    code: str
    entity_id: str | None
    message: str


@dataclass(frozen=True)
class GateResult:
    name: str
    ok: bool
    blockers: tuple[Blocker, ...]


def project_toml_gate(course: Mapping[str, object] | None = None) -> GateResult:
    fields = {} if course is None else course
    required = _REQUIRED_TOPIC_FIELDS if fields.get("kind") == BOOK_TOPIC else _REQUIRED_COURSE_FIELDS
    missing = [
        f"course.{key}"
        for key in required
        if not isinstance(fields.get(key), str) or not str(fields.get(key)).strip()
    ]
    if missing:
        joined = ", ".join(missing)
        return GateResult(
            name=PROJECT_TOML,
            ok=False,
            blockers=(
                Blocker(
                    code="state.project_fields_missing",
                    entity_id=None,
                    message=f"{joined} must be non-empty",
                ),
            ),
        )
    return GateResult(name=PROJECT_TOML, ok=True, blockers=())


def gate_for(name: str, course: Mapping[str, object] | None = None) -> GateResult:
    if name == PROJECT_TOML:
        return project_toml_gate(course)
    return GateResult(
        name=name,
        ok=False,
        blockers=(
            Blocker(
                code="state.gate_not_implemented",
                entity_id=None,
                message=f"gate {name} is not implemented",
            ),
        ),
    )
