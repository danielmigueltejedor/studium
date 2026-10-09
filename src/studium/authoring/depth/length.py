"""Dynamic book length planning.

The final length of a book follows from its curriculum scope, academic level,
number of concepts, required derivations, examples, exercises, figures, and
references. There is no fixed page quota. A requested page target is checked
against the scope derived from the plan: a target below the floor would skip
planned content, and a target above the ceiling would require filler. When a
target is inappropriate, this module explains why and proposes the scope the
plan actually needs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from studium.authoring.depth.profiles import AcademicProfile

LENGTH_PREFERENCES = frozenset({"CONCISE", "STANDARD", "COMPREHENSIVE", "EXHAUSTIVE", "AUTO"})

_LENGTH_FACTORS = {
    "CONCISE": 0.5,
    "STANDARD": 0.75,
    "COMPREHENSIVE": 1.0,
    "EXHAUSTIVE": 1.5,
    "AUTO": 1.0,
}

_DIFFICULTY_MIX = ("FOUNDATIONAL", "INTERMEDIATE", "ADVANCED", "EXAM_LEVEL")


@dataclass(frozen=True)
class LengthScope:
    """A transparent page estimate with its breakdown and assumptions.

    ``floor`` and ``ceiling`` are the range the planned content needs at the
    chosen depth. ``estimate`` is the central value after applying the length
    preference.
    """

    estimate: float
    floor: float
    ceiling: float
    preference: str
    breakdown: dict[str, float]
    assumptions: tuple[str, ...] = field(default=())


def estimate_book_scope(
    *,
    profile: AcademicProfile,
    chapters: int,
    concepts: int,
    derivations: int,
    worked_examples: int,
    exercises: int,
    figures: int = 0,
    sources: int = 0,
    complexity: float = 1.0,
    preference: str = "COMPREHENSIVE",
) -> LengthScope:
    """Estimate the pages the planned scope needs at one academic depth.

    The estimate is a sum of independent contributions, each derived from a
    planned quantity, so a larger length always means more planned content,
    never padding. ``AUTO`` applies no preference factor and reports the scope
    the content itself requires.
    """

    if complexity <= 0:
        complexity = 1.0
    level = float(profile.academic_level)
    concept_pages = concepts * profile.pages_per_concept * complexity
    derivation_pages = derivations * profile.derivation_pages_per_item * complexity
    example_pages = worked_examples * (0.35 + 0.1 * level) * complexity
    exercise_pages = exercises * (0.06 + 0.015 * level)
    figure_pages = figures * 0.14
    reference_pages = sources * 0.03
    front_back = 6.0 + chapters * 1.2
    factor = _LENGTH_FACTORS.get(preference, 1.0)
    raw = (
        concept_pages
        + derivation_pages
        + example_pages
        + exercise_pages
        + figure_pages
        + reference_pages
        + front_back
    )
    estimate = raw * factor
    breakdown = {
        "concepts": round(concept_pages, 2),
        "derivations": round(derivation_pages, 2),
        "worked_examples": round(example_pages, 2),
        "exercises": round(exercise_pages, 2),
        "figures": round(figure_pages, 2),
        "references": round(reference_pages, 2),
        "front_and_back_matter": round(front_back, 2),
    }
    assumptions = (
        f"profile {profile.key} assigns {profile.pages_per_concept} pages per concept at "
        f"{profile.academic_level} of {profile.exercise_mix}",
        f"{derivations} planned derivations at {profile.derivation_pages_per_item} pages each with steps",
        f"length preference {preference} multiplies the basic scope by {factor}",
        "pages are A4 with the default layout; figures count only when actually drawn and checked",
    )
    return LengthScope(
        estimate=round(estimate, 1),
        floor=round(estimate * 0.75, 1),
        ceiling=round(estimate * 1.35, 1),
        preference=preference,
        breakdown=breakdown,
        assumptions=assumptions,
    )


def validate_length_target(
    *,
    scope: LengthScope,
    target_pages: int | None = None,
    max_pages: int | None = None,
) -> list[str]:
    """Explain whether a requested length is appropriate for the scope.

    Returns a list of human-readable notes. An empty list means the request is
    compatible with the planned scope. Every note states the reason and the
    proposed scope; a bad target is never silently accepted.
    """

    notes: list[str] = []
    if target_pages is not None and target_pages > 0:
        if target_pages < scope.floor:
            notes.append(
                f"the requested {target_pages} pages is below the {int(scope.floor)}–{int(scope.ceiling)} "
                "pages this scope needs; shrinking the book this way would drop planned concepts, "
                f"derivations, or exercises. Use the planned range, or reduce the curriculum scope "
                "first and replan."
            )
        elif target_pages > scope.ceiling:
            notes.append(
                f"the requested {target_pages} pages is above the {int(scope.floor)}–{int(scope.ceiling)} "
                "pages this scope supports; the extra pages would require filler or repetition. "
                "To get a genuinely longer book, expand the curriculum scope (more concepts, "
                "derivations, examples, or exercises) and replan."
            )
        else:
            notes.append(f"the requested {target_pages} pages fits the planned {int(scope.floor)}–{int(scope.ceiling)} page scope.")
    if max_pages is not None and max_pages > 0:
        if max_pages < scope.floor:
            notes.append(
                f"the maximum of {max_pages} pages is below the {int(scope.floor)}–{int(scope.ceiling)} "
                "pages this scope needs; either raise the limit or reduce and replan the scope."
            )
        else:
            notes.append(f"the maximum of {max_pages} pages fits the planned scope.")
    if not notes:
        notes.append(f"no page target was set; the plan needs {int(scope.floor)}–{int(scope.ceiling)} pages.")
    return notes


def length_preference(value: object) -> tuple[str | None, dict[str, object] | None]:
    """Validate a length preference value."""

    if not isinstance(value, str):
        return None, {
            "status": "mcp.invalid_input",
            "message": "length preference must be one of " + ", ".join(sorted(LENGTH_PREFERENCES)),
        }
    cleaned = value.strip().upper()
    if cleaned not in LENGTH_PREFERENCES:
        return None, {
            "status": "mcp.invalid_input",
            "message": "unknown length preference. Expected one of " + ", ".join(sorted(LENGTH_PREFERENCES)),
        }
    return cleaned, None
