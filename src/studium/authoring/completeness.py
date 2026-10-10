"""Pedagogical completeness per chapter.

The checklist states, for one section and for the book, which pedagogical
components are present, which are planned but missing, and which do not apply
to this discipline. It never marks a chapter complete because the headings
exist: a component counts only when the stored record that provides it is
current and, where required, checked.
"""

from __future__ import annotations

from pathlib import Path

from studium.authoring.academic_blueprint import academic_concepts_for_chapter
from studium.authoring.audit import audited_paragraph_ids
from studium.authoring.blueprint import current_sections
from studium.authoring.contradictions import open_contradictions
from studium.authoring.derivations import derivations_for_section
from studium.authoring.problems import problem_result_current
from studium.domain.profiles import depth_thresholds
from studium.storage.init_project import load_project_toml
from studium.storage.records import FIGURES, PROBLEMS, PUBLIC_BIBLIOGRAPHY, fold_by_id

_MIN_PARAGRAPHS = 2

_STEM_ONLY = ("derivation", "derivations_checked", "exercise_difficulties", "figures_checked", "notation")
_ALL_ITEMS = (
    "lead",
    "explanation_paragraphs",
    "explanation_depth",
    "definition",
    "self_check",
    "worked_problem",
    "computation",
    "derivation",
    "derivations_checked",
    "exercise_difficulties",
    "figures_checked",
    "notation",
    "sources",
    "audited",
    "contradictions_clear",
    "concepts_covered",
)


def chapter_completeness(root: Path, section: object = None) -> dict[str, object]:
    """The pedagogical checklist for one section, or for every section."""

    wanted = None
    if section is not None:
        if not isinstance(section, str) or not section.strip():
            return {"status": "mcp.invalid_input", "message": "section must be a blueprint section id"}
        wanted = section.strip()
        known = {item["id"] for item in current_sections(root)}
        if wanted not in known:
            return {"status": "completeness.section_unknown", "message": "section is not in the stored blueprint"}

    profile = _domain_profile(root)
    sections = [item for item in current_sections(root) if wanted is None or item["id"] == wanted]
    paragraphs = _paragraphs_by_section(root)
    audited = audited_paragraph_ids(root)
    contradictions = {item.get("target") for item in open_contradictions(root)}
    problems = fold_by_id(root / PROBLEMS)
    figures = fold_by_id(root / FIGURES)
    source_count = sum(1 for row in fold_by_id(root / PUBLIC_BIBLIOGRAPHY) if row.get("deleted") is not True)

    reports: list[dict[str, object]] = []
    for item in sections:
        report = _section_report(root, item["id"], {
            "profile": profile,
            "paragraphs": paragraphs,
            "audited": audited,
            "contradictions": contradictions,
            "problems": problems,
            "figures": figures,
            "source_count": source_count,
        })
        reports.append(report)

    complete = sum(1 for report in reports if report.get("complete") is True)
    return {
        "status": "ok",
        "section": wanted,
        "domain_profile": profile,
        "sections": reports,
        "summary": {"sections": len(reports), "complete": complete, "incomplete": len(reports) - complete},
    }


def _section_report(root: Path, section_id: str, context: dict[str, object]) -> dict[str, object]:
    profile = str(context["profile"])
    raw_paragraphs = context["paragraphs"]
    raw_problems = context["problems"]
    raw_figures = context["figures"]
    raw_audited = context["audited"]
    raw_contradictions = context["contradictions"]
    source_total = context["source_count"]
    paragraphs = [item for item in raw_paragraphs if isinstance(item, dict) and item.get("section") == section_id]  # type: ignore[union-attr]
    audited = raw_audited if isinstance(raw_audited, set) else set()
    contradictions = raw_contradictions if isinstance(raw_contradictions, set) else set()
    problems = [item for item in raw_problems if isinstance(item, dict) and item.get("section") == section_id]  # type: ignore[union-attr]
    figures = [item for item in raw_figures if isinstance(item, dict) and item.get("section") == section_id]  # type: ignore[union-attr]
    sources_total = source_total if isinstance(source_total, int) else 0
    text_words = sum(len(str(item.get("text") or "").split()) for item in paragraphs)
    roles = {item.get("role") for item in paragraphs}
    derivations = derivations_for_section(root, section_id)
    problems_checked = [item for item in problems if problem_result_current(root, item)]
    practice = [item for item in problems if item.get("role") == "practice"]
    difficulties = {item.get("difficulty") for item in practice if isinstance(item.get("difficulty"), str)}
    sources_used = _sources_for_section(root, section_id)
    concepts = academic_concepts_for_chapter(root, section_id)
    concept_ids = {str(concept.get("id")) for concept in concepts}
    covered: set[str] = set()
    for item in paragraphs:
        names = item.get("concepts")
        if isinstance(names, list):
            covered.update(str(name) for name in names)
    notation_count = _notation_count(root, section_id)
    figures_checked = [item for item in figures if item.get("status") == "checked"]
    min_words = depth_thresholds(profile).min_explanation_words

    checks: list[dict[str, object]] = []

    def check(identifier: str, applies: bool, met: bool, detail: str) -> None:
        checks.append({"id": identifier, "applies": applies, "met": met if applies else None, "detail": detail})

    check("lead", bool(paragraphs), bool(paragraphs), f"{len(paragraphs)} cited paragraphs stored")
    check(
        "explanation_paragraphs",
        True,
        len(paragraphs) >= _MIN_PARAGRAPHS,
        f"{len(paragraphs)} of at least {_MIN_PARAGRAPHS} cited explanation paragraphs",
    )
    check(
        "explanation_depth",
        True,
        text_words >= min_words,
        f"{text_words} of about {min_words} words of explanation",
    )
    check("definition", bool(paragraphs), "definition" in roles, "a definition-role paragraph" if "definition" in roles else "no definition-role paragraph")
    check("self_check", bool(paragraphs), "self_check" in roles, "a self-check paragraph" if "self_check" in roles else "no self-check paragraph")
    worked = [item for item in problems if item.get("role") in (None, "worked") and problem_result_current(root, item)]
    check("worked_problem", True, bool(worked), f"{len(worked)} checked worked problems")
    check("computation", True, bool(problems_checked), f"{len(problems_checked)} checked problems with a current result")
    if profile == "STEM":
        check("derivation", True, bool(derivations), f"{len(derivations)} recorded derivations")
        unchecked = [
            item
            for item in derivations
            if isinstance(item.get("verification"), dict) and str(item["verification"].get("status")) in ("UNVERIFIED", "FAILED")  # type: ignore[index]
        ]
        check("derivations_checked", True, bool(derivations) and not unchecked, f"{len(unchecked)} derivations UNVERIFIED or FAILED")
        check("exercise_difficulties", True, len(difficulties) >= 2, f"{len(difficulties)} exercise difficulty levels recorded")
        check("figures_checked", not figures or profile == "STEM", not figures or len(figures_checked) == len(figures), f"{len(figures_checked)} of {len(figures)} figures checked")
        check("notation", True, notation_count > 0, f"{notation_count} notation entries registered")
    else:
        for identifier in _STEM_ONLY:
            check(identifier, False, False, "not applicable to this domain profile")
    check("sources", True, sources_total > 0 and bool(sources_used), f"{len(sources_used)} distinct sources cited by this section")
    section_audited = [item for item in paragraphs if item.get("id") in audited]
    check("audited", bool(paragraphs), len(section_audited) == len(paragraphs) and bool(paragraphs), f"{len(section_audited)} of {len(paragraphs)} paragraphs audited")
    section_contradictions = [target for target in contradictions if target == section_id]
    check("contradictions_clear", True, not section_contradictions, f"{len(section_contradictions)} open contradictions")
    if concepts:
        missing = concept_ids - covered
        check("concepts_covered", True, not missing, f"{len(concept_ids) - len(missing)} of {len(concept_ids)} planned concepts covered")
    else:
        check("concepts_covered", False, False, "no academic blueprint concepts planned for this section")

    complete = all(item["met"] is True for item in checks if item["applies"])
    missing = [item["id"] for item in checks if item["applies"] and item["met"] is not True]
    return {
        "section": section_id,
        "complete": complete,
        "missing": missing,
        "checks": checks,
    }


def _paragraphs_by_section(root: Path) -> list[dict[str, object]]:
    from studium.authoring.paragraphs import supported_paragraphs

    return supported_paragraphs(root)


def _sources_for_section(root: Path, section_id: str) -> set[str]:
    from studium.authoring.excerpts import excerpts_by_id
    from studium.authoring.paragraphs import supported_paragraphs

    stored = excerpts_by_id(root)
    found: set[str] = set()
    for record in supported_paragraphs(root):
        if record.get("section") != section_id:
            continue
        excerpts = record.get("excerpts")
        if not isinstance(excerpts, list):
            continue
        for identifier in excerpts:
            excerpt = stored.get(str(identifier))
            if excerpt is not None:
                source_id = excerpt.get("source_id")
                if isinstance(source_id, str):
                    found.add(source_id)
    return found


def _notation_count(root: Path, section_id: str) -> int:
    from studium.storage.records import NOTATION

    return sum(1 for row in fold_by_id(root / NOTATION) if row.get("section") == section_id)


def _domain_profile(root: Path) -> str:
    document = load_project_toml(root)
    course = document.get("course")
    if isinstance(course, dict) and isinstance(course.get("domain_profile"), str):
        return str(course["domain_profile"])
    return "GENERAL"
