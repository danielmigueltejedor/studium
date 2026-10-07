"""Entry gates for the project state machine.

``project.toml`` checks the course identity used to create a book.
``course_json`` checks that same identity plus one recorded official course
document. Every other gate fails closed with ``state.gate_not_implemented``.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from studium.domain.enums import SourceOrigin
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


def course_json_gate(
    course: Mapping[str, object] | None = None,
    documents: Sequence[Mapping[str, object]] | None = None,
) -> GateResult:
    """Pass only with stored course identity and one recorded official document.

    Document text is not read. A model summary is not a source and does not
    verify or authorize the record.
    """

    blockers: list[Blocker] = []
    missing = _missing_identity(course)
    if missing:
        joined = ", ".join(missing)
        blockers.append(
            Blocker(
                code="state.course_identity_missing",
                entity_id=None,
                message=f"{joined} must be non-empty",
            )
        )
    if not any(_official_document(document) for document in documents or ()):
        blockers.append(
            Blocker(
                code="state.course_document_missing",
                entity_id=None,
                message="an official course document must already be recorded",
            )
        )
    if blockers:
        return GateResult(name=COURSE_JSON, ok=False, blockers=tuple(blockers))
    return GateResult(name=COURSE_JSON, ok=True, blockers=())


def gate_for(
    name: str,
    course: Mapping[str, object] | None = None,
    documents: Sequence[Mapping[str, object]] | None = None,
) -> GateResult:
    if name == PROJECT_TOML:
        return project_toml_gate(course)
    if name == COURSE_JSON:
        return course_json_gate(course, documents)
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


def _missing_identity(course: Mapping[str, object] | None) -> list[str]:
    fields = {} if course is None else course
    return [
        f"course.{key}"
        for key in _REQUIRED_COURSE_FIELDS
        if not isinstance(fields.get(key), str) or not str(fields.get(key)).strip()
    ]


def _official_document(document: Mapping[str, object]) -> bool:
    if document.get("deleted") is True:
        return False
    if document.get("origin") != SourceOrigin.OFFICIAL_WEB.value:
        return False
    if document.get("state") != "DISCOVERED":
        return False
    title = document.get("title")
    url = document.get("url")
    if not isinstance(title, str) or not title.strip():
        return False
    if not isinstance(url, str):
        return False
    cleaned = url.strip()
    return cleaned.startswith(("http://", "https://")) and not any(character.isspace() for character in cleaned)
