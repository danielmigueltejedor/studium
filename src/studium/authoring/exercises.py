"""Exercises that are not a number: the kinds a discipline actually asks for.

A history chapter is practised with a development question, a primary-source
commentary, a chronology or a cause-and-consequence analysis. A literature
chapter is practised with a text commentary. A biology chapter is practised
with an experimental design or a data interpretation next to its calculations.
None of these has one numeric answer, so the numeric and Rust paths of
:mod:`studium.authoring.problems` cannot hold them.

A discursive exercise stores a prompt, optionally a quoted source text and
guiding questions, and a model answer (a *pauta*). Every point of the model
answer cites stored excerpts, so the answer is grounded in the book's sources
and not in the model's memory. The checks here are mechanical and narrow:

* every cited excerpt exists and passes the same citation rules as a paragraph;
* a quoted source text is a verbatim passage of the excerpt it names;
* a chronology date appears in the text of an excerpt the event cites;
* the answer is ``two_witnesses`` only when its excerpts come from at least two
  different sources. That is agreement between sources, not proof that they are
  right, and it does not approve the exercise academically.
"""

import re
from pathlib import Path

from studium.authoring.excerpts import excerpts_by_id
from studium.authoring.support import corroboration_for_excerpts, paragraph_citation_blockers
from studium.policy.trust import directive_changes_policy

DEVELOPMENT_QUESTION = "DEVELOPMENT_QUESTION"
SOURCE_COMMENTARY = "SOURCE_COMMENTARY"
TEXT_COMMENTARY = "TEXT_COMMENTARY"
LITERARY_ANALYSIS = "LITERARY_ANALYSIS"
CHRONOLOGY = "CHRONOLOGY"
CAUSAL_ANALYSIS = "CAUSAL_ANALYSIS"
EXPERIMENT_DESIGN = "EXPERIMENT_DESIGN"
DATA_INTERPRETATION = "DATA_INTERPRETATION"
MECHANISM_EXPLANATION = "MECHANISM_EXPLANATION"
CASE_ANALYSIS = "CASE_ANALYSIS"

#: Types that have no single numeric answer. ``COMPARATIVE`` and ``CONCEPTUAL``
#: are shared with the numeric exercise types and may be either kind.
DISCURSIVE_TYPES = frozenset(
    {
        DEVELOPMENT_QUESTION,
        SOURCE_COMMENTARY,
        TEXT_COMMENTARY,
        LITERARY_ANALYSIS,
        CHRONOLOGY,
        CAUSAL_ANALYSIS,
        EXPERIMENT_DESIGN,
        DATA_INTERPRETATION,
        MECHANISM_EXPLANATION,
        CASE_ANALYSIS,
    }
)
#: A commentary quotes a passage the reader reads before answering.
COMMENTARY_TYPES = frozenset({SOURCE_COMMENTARY, TEXT_COMMENTARY, LITERARY_ANALYSIS})

_ALL = DISCURSIVE_TYPES | {"COMPARATIVE", "CONCEPTUAL"}
#: The discursive types each domain profile may record. A profile that is absent
#: records none (engineering and computer science keep their own exercise kinds).
PROFILE_DISCURSIVE_TYPES: dict[str, frozenset[str]] = {
    "HUMANITIES": frozenset(
        {
            DEVELOPMENT_QUESTION,
            SOURCE_COMMENTARY,
            TEXT_COMMENTARY,
            LITERARY_ANALYSIS,
            CHRONOLOGY,
            CAUSAL_ANALYSIS,
            "COMPARATIVE",
            "CONCEPTUAL",
        }
    ),
    "LAW": frozenset(
        {DEVELOPMENT_QUESTION, SOURCE_COMMENTARY, CASE_ANALYSIS, CAUSAL_ANALYSIS, "COMPARATIVE", "CONCEPTUAL"}
    ),
    "SOCIAL_SCIENCES": frozenset(
        {
            DEVELOPMENT_QUESTION,
            SOURCE_COMMENTARY,
            CASE_ANALYSIS,
            CAUSAL_ANALYSIS,
            DATA_INTERPRETATION,
            CHRONOLOGY,
            "COMPARATIVE",
            "CONCEPTUAL",
        }
    ),
    "LIFE_SCIENCES": frozenset(
        {
            DEVELOPMENT_QUESTION,
            EXPERIMENT_DESIGN,
            DATA_INTERPRETATION,
            MECHANISM_EXPLANATION,
            CAUSAL_ANALYSIS,
            "COMPARATIVE",
            "CONCEPTUAL",
        }
    ),
    "GENERAL": frozenset(_ALL),
}
#: Profiles whose exercises are never numeric. A numeric or Rust problem there
#: is refused with the discursive types the profile does accept.
NO_NUMERIC_PROFILES = frozenset({"HUMANITIES", "LAW"})

_MAX_PROMPT_POINT = 1_500
_MAX_QUOTE = 4_000
_MIN_QUOTE = 20
_MAX_QUESTIONS = 10
_MAX_SECTIONS = 12
_MAX_POINTS = 12
_MAX_EVENTS = 30
_MIN_EVENTS = 3
_MAX_LIST = 10
_MAX_LABEL = 80
_MAX_META = 300
_YEAR = re.compile(r"(?<!\d)(\d{3,4})(?!\d)")


def allowed_types(profile: str) -> frozenset[str]:
    """Discursive and shared types a domain profile may record."""

    return PROFILE_DISCURSIVE_TYPES.get(profile, frozenset())


def numeric_allowed(profile: str) -> bool:
    return profile not in NO_NUMERIC_PROFILES


def numeric_refusal(profile: str) -> str:
    kinds = ", ".join(sorted(allowed_types(profile) & DISCURSIVE_TYPES))
    return (
        f"A {profile} book does not ask numeric or Rust exercises. Record a discursive exercise "
        f"with problem_type and an answer: {kinds}."
    )


def norm(text: str) -> str:
    """Whitespace-normalised text, the form a quote is compared in."""

    return re.sub(r"\s+", " ", text).strip()


def validate_discursive(
    root: Path,
    *,
    profile: str,
    problem_type: str | None,
    answer: object,
    source: object,
    questions: object,
) -> tuple[dict[str, object] | None, str | None, str | None]:
    """The stored fields of a discursive exercise, or ``(None, code, message)``.

    The fields are ``answer``, ``questions``, ``source`` (commentary types) and
    ``excerpts``, the ordered ids the exercise cites.
    """

    if problem_type not in DISCURSIVE_TYPES:
        return None, "mcp.invalid_input", "problem_type must be a discursive exercise type"
    if problem_type not in allowed_types(profile):
        kinds = ", ".join(sorted(allowed_types(profile) & DISCURSIVE_TYPES)) or "none"
        return (
            None,
            "problem.type_not_for_discipline",
            f"{problem_type} is not an exercise type of a {profile} book. Allowed: {kinds}.",
        )
    if not isinstance(answer, dict) or not answer:
        return None, "mcp.invalid_input", "a discursive exercise needs an answer object"
    stored = excerpts_by_id(root)
    cited: list[str] = []

    def take(value: object, where: str) -> tuple[list[str] | None, str | None]:
        if not isinstance(value, list) or not 1 <= len(value) <= 4:
            return None, f"{where} needs one to four stored excerpt ids"
        identifiers: list[str] = []
        for item in value:
            if not isinstance(item, str) or not item.strip() or len(item.strip()) > 128:
                return None, f"{where} needs one to four stored excerpt ids"
            if item.strip() not in identifiers:
                identifiers.append(item.strip())
        for item in identifiers:
            if item not in cited:
                cited.append(item)
        return identifiers, None

    clean_answer: dict[str, object] = {}
    summary = answer.get("summary")
    if summary is not None:
        text, error = _text(summary, "summary", 2_500)
        if error:
            return None, "mcp.invalid_input", error
        clean_answer["summary"] = text
    sections = answer.get("sections")
    events = answer.get("events")
    if problem_type == CHRONOLOGY:
        if not isinstance(events, list) or not _MIN_EVENTS <= len(events) <= _MAX_EVENTS:
            return None, "mcp.invalid_input", f"a chronology needs {_MIN_EVENTS} to {_MAX_EVENTS} events"
        clean_events: list[dict[str, object]] = []
        for index, event in enumerate(events, 1):
            if not isinstance(event, dict):
                return None, "mcp.invalid_input", f"event {index} must be an object"
            date, date_error = _text(event.get("date"), f"event {index} date", 80)
            body, body_error = _text(event.get("text"), f"event {index} text", _MAX_PROMPT_POINT)
            ids, ids_error = take(event.get("excerpts"), f"event {index}")
            if date_error or body_error or ids_error:
                return None, "mcp.invalid_input", date_error or body_error or ids_error
            assert date and body and ids
            year = _year(event.get("year"), date)
            if year is None:
                return None, "mcp.invalid_input", f"event {index} needs a year of three or four digits"
            clean_events.append({"date": date, "year": year, "text": body, "excerpts": ids})
        clean_answer["events"] = clean_events
    elif events is not None:
        return None, "mcp.invalid_input", "events belong to a CHRONOLOGY exercise"
    if sections is not None or problem_type != CHRONOLOGY:
        if not isinstance(sections, list) or not 1 <= len(sections) <= _MAX_SECTIONS:
            return None, "mcp.invalid_input", f"answer.sections needs one to {_MAX_SECTIONS} labelled groups of points"
        clean_sections: list[dict[str, object]] = []
        total = 0
        for index, section in enumerate(sections, 1):
            if not isinstance(section, dict):
                return None, "mcp.invalid_input", f"section {index} must be an object"
            label, label_error = _text(section.get("label"), f"section {index} label", _MAX_LABEL)
            points = section.get("points")
            if label_error or not isinstance(points, list) or not 1 <= len(points) <= _MAX_POINTS:
                return None, "mcp.invalid_input", label_error or f"section {index} needs one to {_MAX_POINTS} points"
            clean_points: list[dict[str, object]] = []
            for position, point in enumerate(points, 1):
                if not isinstance(point, dict):
                    return None, "mcp.invalid_input", f"point {index}.{position} must be an object"
                body, body_error = _text(point.get("text"), f"point {index}.{position} text", _MAX_PROMPT_POINT)
                ids, ids_error = take(point.get("excerpts"), f"point {index}.{position}")
                if body_error or ids_error:
                    return None, "mcp.invalid_input", body_error or ids_error
                assert body and ids
                clean_points.append({"text": body, "excerpts": ids})
            total += len(clean_points)
            clean_sections.append({"label": label, "points": clean_points})
        if total < 2 and problem_type != CHRONOLOGY:
            return None, "mcp.invalid_input", "a model answer needs at least two points"
        clean_answer["sections"] = clean_sections
    for key in ("mistakes", "criteria"):
        items, error = _text_list(answer.get(key), f"answer.{key}")
        if error:
            return None, "mcp.invalid_input", error
        if items:
            clean_answer[key] = items
    clean_questions, question_error = _text_list(questions, "questions", _MAX_QUESTIONS)
    if question_error:
        return None, "mcp.invalid_input", question_error
    fields: dict[str, object] = {"answer": clean_answer}
    if clean_questions:
        fields["questions"] = clean_questions
    if problem_type in COMMENTARY_TYPES:
        clean_source, code, message = _source(source, stored, cited)
        if message:
            return None, code, message
        assert clean_source is not None
        fields["source"] = clean_source
    elif source is not None:
        return None, "mcp.invalid_input", "source belongs to a commentary exercise"
    for flat in _flat(clean_answer):
        if directive_changes_policy(flat):
            return None, "policy.overridden", "exercise text changed policy"
    blockers = paragraph_citation_blockers(root, list(cited))
    if blockers:
        first = blockers[0]
        return None, str(first.get("code") or "claim.excerpt_missing"), str(first.get("message") or "excerpt blocked")
    for event in clean_answer.get("events") or []:  # type: ignore[union-attr]
        assert isinstance(event, dict)
        ids = event["excerpts"]
        assert isinstance(ids, list)
        year = str(event["year"])
        if not any(year in norm(str(stored[item].get("text") or "")) for item in ids if item in stored):
            return (
                None,
                "problem.date_not_in_excerpt",
                f"the year {year} of an event does not appear in the excerpts that event cites",
            )
    fields["excerpts"] = list(cited)
    return fields, None, None


def witness_status(root: Path, excerpt_ids: list[str]) -> str | None:
    """``two_witnesses`` when the exercise cites two different public sources."""

    return corroboration_for_excerpts(root, excerpt_ids)


def _source(
    value: object, stored: dict[str, dict[str, object]], cited: list[str]
) -> tuple[dict[str, object] | None, str | None, str | None]:
    if not isinstance(value, dict):
        return None, "mcp.invalid_input", "a commentary exercise needs a source object with an excerpt id and a quote"
    excerpt_id = value.get("excerpt")
    if not isinstance(excerpt_id, str) or excerpt_id.strip() not in stored:
        return None, "claim.excerpt_missing", "source.excerpt is not a stored excerpt id"
    excerpt_id = excerpt_id.strip()
    quote = value.get("quote")
    if not isinstance(quote, str) or not _MIN_QUOTE <= len(norm(quote)) <= _MAX_QUOTE:
        return None, "mcp.invalid_input", f"source.quote must be {_MIN_QUOTE} to {_MAX_QUOTE} characters"
    if norm(quote) not in norm(str(stored[excerpt_id].get("text") or "")):
        return None, "problem.source_not_quoted", "source.quote is not a verbatim passage of the excerpt it names"
    clean: dict[str, object] = {"excerpt": excerpt_id, "quote": quote.strip()}
    for key in ("author", "work", "date", "note"):
        if value.get(key) is None:
            continue
        text, error = _text(value.get(key), f"source.{key}", _MAX_META)
        if error:
            return None, "mcp.invalid_input", error
        clean[key] = text
    if excerpt_id not in cited:
        cited.append(excerpt_id)
    return clean, None, None


def _year(value: object, date: str) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if 100 <= value <= 2999 else None
    if isinstance(value, str) and value.strip().isdigit() and 3 <= len(value.strip()) <= 4:
        return int(value.strip())
    match = _YEAR.search(date)
    return int(match.group(1)) if match else None


def _text(value: object, name: str, limit: int) -> tuple[str | None, str | None]:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
        return None, f"{name} must be text of at most {limit} characters"
    return value.strip(), None


def _text_list(value: object, name: str, limit: int = _MAX_LIST) -> tuple[list[str] | None, str | None]:
    if value is None:
        return [], None
    if not isinstance(value, list) or len(value) > limit:
        return None, f"{name} must be a list of at most {limit} texts"
    items: list[str] = []
    for item in value:
        text, error = _text(item, name, _MAX_PROMPT_POINT)
        if error:
            return None, error
        assert text is not None
        items.append(text)
    return items, None


def _flat(answer: dict[str, object]) -> list[str]:
    found: list[str] = []
    summary = answer.get("summary")
    if isinstance(summary, str):
        found.append(summary)
    for section in answer.get("sections") or []:  # type: ignore[union-attr]
        if isinstance(section, dict):
            found.extend(str(point.get("text")) for point in section.get("points") or [] if isinstance(point, dict))
    for event in answer.get("events") or []:  # type: ignore[union-attr]
        if isinstance(event, dict):
            found.append(str(event.get("text")))
    for key in ("mistakes", "criteria"):
        value = answer.get(key)
        if isinstance(value, list):
            found.extend(str(item) for item in value)
    return found
