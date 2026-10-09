"""Academic depth profiles.

A profile is a deterministic description of how deep a subject must be
treated: the mathematical rigor, the expected prior knowledge, the level of
explanation, the complexity of derivations, the theory-to-practice emphasis,
and the mix of exercise difficulty. Profiles never fabricate content; they
only state requirements that an authoring client can follow without a
specific AI provider.
"""

from __future__ import annotations

from dataclasses import dataclass

PROFILE_KEYS = ("INTRODUCTORY", "UNDERGRADUATE", "ADVANCED_UNDERGRADUATE", "GRADUATE", "RESEARCH")


@dataclass(frozen=True)
class AcademicProfile:
    """One named academic depth profile with its planning requirements."""

    key: str
    label: str
    academic_level: int
    math_rigor: int
    explanation_depth: str
    derivation_complexity: str
    prerequisites: tuple[str, ...]
    prior_knowledge: tuple[str, ...]
    theory_weight: float
    exercise_mix: dict[str, int]
    guidelines: tuple[str, ...]
    pages_per_concept: float
    derivation_pages_per_item: float


PROFILES: dict[str, AcademicProfile] = {
    "INTRODUCTORY": AcademicProfile(
        key="INTRODUCTORY",
        label="Introductory",
        academic_level=1,
        math_rigor=1,
        explanation_depth=(
            "explain every concept from first principles with plain-language intuition "
            "before any formula, and keep notation minimal and consistent"
        ),
        derivation_complexity=(
            "present derivations as narrated arguments with one or two arithmetic steps; "
            "no calculus is assumed"
        ),
        prerequisites=("high-school algebra", "basic arithmetic"),
        prior_knowledge=(
            "high-school algebra",
            "ability to substitute numbers into a formula",
        ),
        theory_weight=0.45,
        exercise_mix={"FOUNDATIONAL": 60, "INTERMEDIATE": 30, "ADVANCED": 10, "EXAM_LEVEL": 0},
        guidelines=(
            "define every symbol the first time it appears",
            "give one intuitive interpretation before every equation",
            "use concrete numeric examples at every step",
            "do not assume calculus or vector notation",
        ),
        pages_per_concept=0.45,
        derivation_pages_per_item=0.35,
    ),
    "UNDERGRADUATE": AcademicProfile(
        key="UNDERGRADUATE",
        label="Undergraduate",
        academic_level=2,
        math_rigor=2,
        explanation_depth=(
            "explain concepts with both intuition and quantitative development; "
            "state assumptions and limits of each result"
        ),
        derivation_complexity=(
            "full derivations with single-variable calculus where the subject requires it; "
            "every step explained and every variable defined"
        ),
        prerequisites=("single-variable calculus", "elementary physics"),
        prior_knowledge=(
            "single-variable calculus",
            "elementary mechanics",
            "basic units and dimensional reasoning",
        ),
        theory_weight=0.5,
        exercise_mix={"FOUNDATIONAL": 40, "INTERMEDIATE": 40, "ADVANCED": 15, "EXAM_LEVEL": 5},
        guidelines=(
            "state the assumptions behind each governing equation",
            "derive important results, do not only state them",
            "include worked examples at intermediate difficulty",
            "verify every numeric result",
        ),
        pages_per_concept=0.7,
        derivation_pages_per_item=0.45,
    ),
    "ADVANCED_UNDERGRADUATE": AcademicProfile(
        key="ADVANCED_UNDERGRADUATE",
        label="Advanced Undergraduate",
        academic_level=3,
        math_rigor=3,
        explanation_depth=(
            "assume a working knowledge of vector calculus and ordinary differential "
            "equations; derive governing equations from conservation laws and give "
            "physical interpretations of every term"
        ),
        derivation_complexity=(
            "multivariable derivations (integral and differential forms of conservation "
            "laws) with stated assumptions, boundary conditions, and applicability limits"
        ),
        prerequisites=(
            "multivariable calculus",
            "ordinary differential equations",
            "elementary mechanics",
        ),
        prior_knowledge=(
            "multivariable calculus (gradient, divergence, surface and volume integrals)",
            "ordinary differential equations",
            "vector algebra",
            "introductory thermodynamics",
        ),
        theory_weight=0.55,
        exercise_mix={"FOUNDATIONAL": 25, "INTERMEDIATE": 40, "ADVANCED": 25, "EXAM_LEVEL": 10},
        guidelines=(
            "derive the governing equations from conservation laws",
            "state assumptions, boundary conditions, and limitations for every equation",
            "distinguish physical content from idealizations",
            "include advanced and exam-level problems",
            "verify derivations with deterministic checks where possible",
        ),
        pages_per_concept=1.0,
        derivation_pages_per_item=0.55,
    ),
    "GRADUATE": AcademicProfile(
        key="GRADUATE",
        label="Graduate",
        academic_level=4,
        math_rigor=4,
        explanation_depth=(
            "assume familiarity with partial differential equations and tensor notation; "
            "emphasize proofs, regimes of validity, and the difference between modeling "
            "assumptions and physical laws"
        ),
        derivation_complexity=(
            "complete derivations including partial differential equation statements, "
            "scaling arguments, and asymptotic limits"
        ),
        prerequisites=(
            "partial differential equations",
            "linear algebra",
            "vector and tensor analysis",
        ),
        prior_knowledge=(
            "partial differential equations",
            "linear algebra",
            "vector and tensor analysis",
            "advanced calculus",
        ),
        theory_weight=0.6,
        exercise_mix={"FOUNDATIONAL": 10, "INTERMEDIATE": 30, "ADVANCED": 40, "EXAM_LEVEL": 20},
        guidelines=(
            "present proofs and scaling arguments",
            "discuss regimes of validity and failure modes",
            "require the student to extend results, not only apply them",
            "include research-grade exercises that require synthesis",
        ),
        pages_per_concept=1.25,
        derivation_pages_per_item=0.7,
    ),
    "RESEARCH": AcademicProfile(
        key="RESEARCH",
        label="Research",
        academic_level=5,
        math_rigor=5,
        explanation_depth=(
            "assume mastery of the field's standard mathematics; emphasize open "
            "questions, current literature, and the boundary of established results"
        ),
        derivation_complexity=(
            "deep derivations with full detail, including references to the original "
            "scientific literature and discussion of approximation hierarchies"
        ),
        prerequisites=(
            "graduate-level mathematics of the field",
            "the standard textbook body of the discipline",
        ),
        prior_knowledge=(
            "graduate-level mathematics of the field",
            "standard body of the discipline",
            "ability to read primary literature",
        ),
        theory_weight=0.65,
        exercise_mix={"FOUNDATIONAL": 0, "INTERMEDIATE": 15, "ADVANCED": 45, "EXAM_LEVEL": 40},
        guidelines=(
            "cite the primary literature for every major result",
            "distinguish established results from open questions",
            "derive results from first principles with complete rigor",
            "design advanced exercises that require reading the literature",
        ),
        pages_per_concept=1.5,
        derivation_pages_per_item=0.85,
    ),
}


def resolve_depth_profile(value: object) -> tuple[AcademicProfile | None, dict[str, object] | None]:
    """Return the profile named by ``value``, or a deterministic error.

    Accepts canonical keys in any case. Whitespace is stripped. An unknown
    value tells the client the full list of valid keys.
    """

    if not isinstance(value, str):
        return None, {
            "status": "mcp.invalid_input",
            "message": "academic depth must be one of " + ", ".join(PROFILE_KEYS),
        }
    key = value.strip().upper()
    profile = PROFILES.get(key)
    if profile is None:
        return None, {
            "status": "mcp.invalid_input",
            "message": "unknown academic depth. Expected one of " + ", ".join(PROFILE_KEYS),
        }
    return profile, None


def profile_requirements(profile: AcademicProfile) -> dict[str, object]:
    """Structured, provider-agnostic requirements for one profile."""

    return {
        "profile": profile.key,
        "label": profile.label,
        "academic_level": profile.academic_level,
        "math_rigor": profile.math_rigor,
        "explanation_depth": profile.explanation_depth,
        "derivation_complexity": profile.derivation_complexity,
        "prerequisites": list(profile.prerequisites),
        "prior_knowledge": list(profile.prior_knowledge),
        "theory_weight": profile.theory_weight,
        "practice_weight": round(1.0 - profile.theory_weight, 2),
        "exercise_mix": dict(profile.exercise_mix),
        "guidelines": list(profile.guidelines),
    }
