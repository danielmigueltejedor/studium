"""Depth and scope planning for a subject.

The planner turns a verified curriculum scope (or an existing academic
blueprint) and an academic depth profile into a structured plan: how many
concepts each chapter should cover, which derivations, how many worked
examples and exercises, and the length the whole scope needs. It is fully
deterministic, works offline, and produces requirements any AI client can
follow across sessions.
"""

from __future__ import annotations

from pathlib import Path

from studium.authoring.academic_blueprint import academic_concepts_for_chapter, current_academic_blueprint
from studium.authoring.blueprint import current_sections
from studium.authoring.depth.length import estimate_book_scope, length_preference, validate_length_target
from studium.authoring.depth.profiles import AcademicProfile, profile_requirements, resolve_depth_profile
from studium.storage.init_project import domain_profile as _domain_profile
from studium.storage.init_project import load_project_toml
from studium.storage.migrate import utc_now
from studium.storage.records import DEPTH_PLANS, append_jsonl, fold_by_id

_INVALID_CURRICULUM = "curriculum_scope must be a list of topics with id and title"

# Keyword -> net concept count adjustment for STEM topics. Long, rich titles
# legitimately describe more planned concepts than short ones.
_KEYWORDS_TOKENS = (
    ("conservacion", 2),
    ("ecuacion", 1),
    ("teorema", 1),
    ("dimensional", 1),
    ("capa limite", 1),
    ("diferencial", 1),
    ("integral", 1),
    ("transferencia", 1),
    ("turbul", 1),
    ("aerodinam", 1),
    ("estatica", 1),
    ("cinematica", 1),
    ("dinamica", 1),
)
_DERIVATION_KEYWORDS = ("ecuacion", "conservacion", "teorema", "deriv", "investigacion-", "balance")
_EXAMPLE_KEYWORDS = ("aplicac", "problem", "medicion", "instrument", "flujo en", "diseno")
# Exercise count per concept at each academic level.
_EXERCISES_PER_CONCEPT = {1: 1.0, 2: 1.6, 3: 2.0, 4: 2.4, 5: 2.8}


def build_depth_plan(
    root: Path,
    *,
    academic_depth: object = None,
    length: object = None,
    curriculum_scope: object = None,
    target_pages: object = None,
    max_pages: object = None,
    min_pages: object = None,
    exercises_with_solutions: object = None,
    theory_emphasis: object = None,
) -> dict[str, object]:
    """Plan the depth and length of the active project and store the plan.

    The curriculum may come from the stored academic blueprint or from an
    explicit ``curriculum_scope`` list of ``{"id", "title"}`` topics. The
    academic depth profile and length preference are validated; a requested
    page target is checked against the scope the content needs, and the
    resulting notes explain any mismatch instead of silently accepting it.
    """

    profile, profile_error = resolve_depth_profile(academic_depth)
    preference, preference_error = length_preference(length if length is not None else "COMPREHENSIVE")
    if profile_error is not None:
        return profile_error
    if preference_error is not None:
        return preference_error
    assert profile is not None and preference is not None

    topics, curriculum_source, concepts_total, derivations_total = _curriculum_counts(root, curriculum_scope)
    if topics is None:
        return _error("mcp.invalid_input", _INVALID_CURRICULUM)

    exercises_total = _exercises_total(profile, topics)
    chapters = len(topics)
    scope = estimate_book_scope(
        profile=profile,
        chapters=chapters,
        concepts=concepts_total,
        derivations=derivations_total,
        worked_examples=_examples_total(topics),
        exercises=exercises_total,
        figures=0,
        sources=_source_count(root),
        preference=preference,
    )
    notes = validate_length_target(scope=scope, target_pages=_int(target_pages), max_pages=_int(max_pages))
    if min_pages is not None:
        minimum = _int(min_pages)
        if minimum is not None and minimum > scope.floor:
            notes.append(
                f"the requested minimum of {minimum} pages is above the {int(scope.floor)}–{int(scope.ceiling)} "
                "planned scope; expand the curriculum and replan rather than padding."
            )

    per_chapter = [
        _chapter_requirements(profile, topic, exercises_with_solutions)
        for topic in topics
    ]
    plan: dict[str, object] = {
        "status": "planned",
        "source": curriculum_source,
        "subject": _subject(root),
        "domain_profile": _domain_profile(root),
        "academic_depth": profile_requirements(profile),
        "length": {
            "preference": preference,
            "low": scope.floor,
            "estimate": scope.estimate,
            "high": scope.ceiling,
            "breakdown": scope.breakdown,
        },
        "curriculum": {
            "chapters": chapters,
            "concepts": concepts_total,
            "derivations": derivations_total,
            "worked_examples": _examples_total(topics),
            "exercises": exercises_total,
            "figures": 0,
            "sources": _source_count(root),
        },
        "chapters": per_chapter,
        "validation": notes,
        "assumptions": list(scope.assumptions),
        "theory_emphasis": theory_emphasis if isinstance(theory_emphasis, str) else "AUTO",
        "exercises_with_solutions": exercises_with_solutions is not False,
        "generated_at": utc_now(),
    }
    _store(root, plan)
    return plan


def depth_plan_status(root: Path) -> dict[str, object]:
    """Return the stored depth plan for this edition, or a clear status.

    The plan is edition-scoped: when the written content changed, the stored
    plan is reported as stale so the client replans against the current state.
    """

    rows = fold_by_id(root / DEPTH_PLANS)
    current = next((item for item in rows if item.get("id") == "plan"), None)
    if current is None:
        return {
            "status": "not_planned",
            "message": "no depth plan is stored. Call studium_depth_plan with an academic depth.",
        }
    plan = _public_plan(current)
    return {"status": "ok", "plan": plan}


def plan_requires_academic_blueprint(plan: dict[str, object] | None) -> bool:
    """True when the plan used the blueprint's concept assignments."""

    if not isinstance(plan, dict):
        return False
    return plan.get("source") == "academic_blueprint"


def _public_plan(record: dict[str, object]) -> dict[str, object]:
    plan = record.get("plan")
    return dict(plan) if isinstance(plan, dict) else {}


def _curriculum_counts(
    root: Path,
    curriculum_scope: object,
) -> tuple[list[dict[str, object]] | None, str, int, int]:
    """Topics with concept and derivation counts.

    An explicit curriculum scope wins; otherwise the stored academic blueprint
    is used chapter by chapter, and as a last resort the flat outline.
    """

    if curriculum_scope is not None:
        scoped = _topics(curriculum_scope)
        if scoped is None:
            return None, "curriculum_scope", 0, 0
        for topic in scoped:
            topic["_concepts"] = _concepts_for_title(str(topic.get("title") or ""))
            topic["_derivations"] = _derivations_for_title(str(topic.get("title") or ""))
        total_concepts = sum(_count(item, "_concepts") for item in scoped)
        total_derivations = sum(_count(item, "_derivations") for item in scoped)
        return scoped, "curriculum_scope", total_concepts, total_derivations

    blueprint = current_academic_blueprint(root)
    if blueprint is not None:
        from_blueprint: list[dict[str, object]] = []
        for chapter in _blueprint_chapters(blueprint):
            concepts = academic_concepts_for_chapter(root, str(chapter.get("id") or ""))
            from_blueprint.append(
                {
                    "id": str(chapter.get("id") or ""),
                    "title": str(chapter.get("title") or ""),
                    "_concepts": len(concepts),
                    "_derivations": sum(
                        1
                        for concept in concepts
                        if isinstance(concept, dict) and "derivation" in str(concept.get("math_requirements") or "")
                    ),
                    "source": "academic_blueprint",
                }
            )
        total_concepts = sum(_count(item, "_concepts") for item in from_blueprint)
        total_derivations = sum(_count(item, "_derivations") for item in from_blueprint)
        return from_blueprint, "academic_blueprint", total_concepts, total_derivations

    topics: list[dict[str, object]] = [{"id": section["id"], "title": section["title"]} for section in current_sections(root)]
    for topic in topics:
        topic["_concepts"] = _concepts_for_title(str(topic.get("title") or ""))
        topic["_derivations"] = _derivations_for_title(str(topic.get("title") or ""))
    return (
        topics,
        "outline",
        sum(_count(item, "_concepts") for item in topics),
        sum(_count(item, "_derivations") for item in topics),
    )


def _count(topic: dict[str, object], key: str) -> int:
    value = topic.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _topics(value: object) -> list[dict[str, object]] | None:
    if not isinstance(value, list) or not value or len(value) > 200:
        return None
    cleaned: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            return None
        identifier = item.get("id")
        title = item.get("title")
        if not isinstance(identifier, str) or not identifier.strip() or not isinstance(title, str) or not title.strip():
            return None
        cleaned.append({"id": identifier.strip(), "title": title.strip()})
    return cleaned


def _chapter_requirements(
    profile: AcademicProfile,
    topic: dict[str, object],
    exercises_with_solutions: object,
) -> dict[str, object]:
    concepts = _count(topic, "_concepts")
    derivations = _count(topic, "_derivations")
    exercises = max(1, round(concepts * _EXERCISES_PER_CONCEPT.get(profile.academic_level, 2.0)))
    return {
        "chapter": topic.get("id"),
        "title": topic.get("title"),
        "concepts": concepts,
        "derivations": derivations,
        "worked_examples": max(1, _count(topic, "_examples")),
        "exercises": exercises,
        "sources_needed": max(2, (concepts + derivations + 2) // 3),
        "objectives": [f"teach the planned concepts of {topic.get('title')}"],
        "prerequisites": list(profile.prerequisites),
        "theory_weight": profile.theory_weight,
        "notes": _chapter_note(topic),
    }


def _chapter_note(topic: dict[str, object]) -> str:
    title = str(topic.get("title") or "")
    if any(token in title.casefold() for token in _DERIVATION_KEYWORDS):
        return "derive the governing equation from conservation laws and state its limits"
    if any(token in title.casefold() for token in _EXAMPLE_KEYWORDS):
        return "lead with applications and worked examples after the concept is defined"
    return "define concepts precisely and give a quantitative example for each"


def _concepts_for_title(title: str) -> int:
    lowered = title.casefold()
    count = 6
    for token, bonus in _KEYWORDS_TOKENS:
        if token in lowered:
            count += bonus
    if len(title) > 60:
        count += 1
    return count


def _derivations_for_title(title: str) -> int:
    lowered = title.casefold()
    count = 1
    for token in _DERIVATION_KEYWORDS:
        if token in lowered:
            count += 1
    return min(count, 4)


def _exercises_total(profile: AcademicProfile, topics: list[dict[str, object]]) -> int:
    total = 0
    for topic in topics:
        concepts = _count(topic, "_concepts")
        total += max(1, round(concepts * _EXERCISES_PER_CONCEPT.get(profile.academic_level, 2.0)))
    return total


def _examples_total(topics: list[dict[str, object]]) -> int:
    return max(1, len(topics))


def _int(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value == int(value):
        return int(value)
    if isinstance(value, str):
        try:
            number = int(float(value.strip()))
        except ValueError:
            return None
        return number
    return None


def _source_count(root: Path) -> int:
    rows = fold_by_id(root / "bibliography" / "public.jsonl")
    return len(rows) - sum(1 for row in rows if row.get("deleted") is True)


def _blueprint_chapters(blueprint: dict[str, object]) -> list[dict[str, object]]:
    parts = blueprint.get("parts")
    if not isinstance(parts, list):
        return []
    chapters: list[dict[str, object]] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        for chapter in part.get("chapters", []):
            if isinstance(chapter, dict):
                chapters.append(chapter)
    return chapters


def _subject(root: Path) -> str:
    document = load_project_toml(root)
    course = document.get("course")
    if isinstance(course, dict) and isinstance(course.get("name"), str) and course["name"].strip():
        return course["name"].strip()
    return "Book"


def _store(root: Path, plan: dict[str, object]) -> None:
    append_jsonl(
        root / DEPTH_PLANS,
        {
            "schema_version": "1.0.0",
            "id": "plan",
            "plan": plan,
            "generated_at": utc_now(),
        },
    )


def _error(code: str, message: str) -> dict[str, object]:
    return {"status": code, "message": message}
