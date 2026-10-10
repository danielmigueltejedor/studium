"""Quality report from stored records only.

Every number here is counted from the project's own JSONL records or from a
deterministic check. The report states what was measured, how, and what was
not measured. It never claims review by a human instructor: that status does
not exist in this pipeline.
"""

from __future__ import annotations

from pathlib import Path

from studium.authoring.audit import audited_paragraph_ids
from studium.authoring.blueprint import current_sections
from studium.authoring.completeness import chapter_completeness
from studium.authoring.consistency import consistency_report
from studium.authoring.contradictions import open_contradictions
from studium.authoring.coverage import source_coverage
from studium.authoring.depth.planner import depth_plan_status
from studium.authoring.excerpts import excerpts_by_id
from studium.authoring.notation import notation_registry
from studium.authoring.paragraphs import supported_paragraphs
from studium.authoring.problems import problem_result_current
from studium.domain.profiles import depth_thresholds
from studium.storage.init_project import load_project_toml, load_state_holding_lock
from studium.storage.records import (
    AUDITS,
    COMPUTATIONS,
    DERIVATIONS,
    FIGURES,
    NOTATION,
    PROBLEMS,
    PUBLIC_BIBLIOGRAPHY,
    REVIEWS,
    TERMINOLOGY,
    fold_by_id,
)


def quality_report(root: Path) -> dict[str, object]:
    """Metrics, statuses, and honest limitations for the active edition."""

    state = load_state_holding_lock(root)
    profile = _domain_profile(root)
    thresholds = depth_thresholds(profile)
    sections = current_sections(root)
    paragraphs = supported_paragraphs(root)
    stored_excerpts = excerpts_by_id(root)
    sources = [row for row in fold_by_id(root / PUBLIC_BIBLIOGRAPHY) if row.get("deleted") is not True]
    audited = audited_paragraph_ids(root)
    contradictions = open_contradictions(root)
    problems = fold_by_id(root / PROBLEMS)
    checked_problems = [row for row in problems if problem_result_current(root, row)]
    computations = fold_by_id(root / COMPUTATIONS)
    replayed = [row for row in computations if row.get("status") == "replayed" and row.get("correct") is True]
    derivations = fold_by_id(root / DERIVATIONS)
    derivation_statuses: dict[str, int] = {}
    for row in derivations:
        verification = row.get("verification")
        status = str((verification or {}).get("status")) if isinstance(verification, dict) else "UNVERIFIED"
        derivation_statuses[status] = derivation_statuses.get(status, 0) + 1
    figures = fold_by_id(root / FIGURES)
    figures_checked = [row for row in figures if row.get("status") == "checked"]
    words = sum(len(str(row.get("text") or "").split()) for row in paragraphs)
    completeness = chapter_completeness(root)
    coverage = source_coverage(root)
    consistency = consistency_report(root)
    plan = depth_plan_status(root)

    limitations: list[str] = []
    limitations.append(
        "no human instructor has reviewed this edition; ACADEMICALLY_REVIEWED is not claimed by this pipeline"
    )
    if isinstance(plan.get("plan"), dict):
        length = plan["plan"].get("length")  # type: ignore[union-attr]
        if isinstance(length, dict):
            limitations.append(
                f"page targets are estimates ({length.get('low')}–{length.get('high')}); "
                "only the compiled PDF's page count is a measured fact"
            )
    thin = [str(item) for item in coverage.get("thin_sections", [])]  # type: ignore[union-attr]
    if thin:
        limitations.append(f"sections with too few distinct sources: {', '.join(thin[:10])}")
    unverified = [
        row
        for row in derivations
        if isinstance(row.get("verification"), dict) and str(row["verification"].get("status")) == "UNVERIFIED"  # type: ignore[index]
    ]
    if unverified:
        limitations.append(f"{len(unverified)} derivations carry no deterministic check result")

    return {
        "status": "ok",
        "project_state": state.get("state"),
        "released": state.get("state") == "RELEASED",
        "domain_profile": profile,
        "thresholds": {
            "min_sections": thresholds.min_sections,
            "min_sources": thresholds.min_sources,
            "min_explanation_words": thresholds.min_explanation_words,
            "min_explanation_sections": thresholds.min_explanation_sections,
        },
        "counts": {
            "sections": len(sections),
            "sections_with_prose": len({str(row.get("section")) for row in paragraphs}),
            "paragraphs": len(paragraphs),
            "paragraphs_audited": len([row for row in paragraphs if row.get("id") in audited]),
            "words": words,
            "sources": len(sources),
            "excerpts_used": len({str(identifier) for row in paragraphs for identifier in row.get("excerpts", [])}),  # type: ignore[union-attr]
            "excerpts_stored": len(stored_excerpts),
            "problems": len(problems),
            "problems_checked": len(checked_problems),
            "computations_replayed": len(replayed),
            "derivations": len(derivations),
            "figures": len(figures),
            "figures_checked": len(figures_checked),
            "notation_entries": len(fold_by_id(root / NOTATION)),
            "notation_symbols": len(notation_registry(root)),
            "terminology_entries": len(fold_by_id(root / TERMINOLOGY)),
            "audits": len(fold_by_id(root / AUDITS)),
            "reviews": len(fold_by_id(root / REVIEWS)),
            "open_contradictions": len(contradictions),
        },
        "derivation_statuses": derivation_statuses,
        "completeness": completeness.get("summary"),
        "coverage": coverage.get("totals"),
        "consistent": consistency.get("consistent"),
        "depth_plan": plan.get("status"),
        "verification_statuses_present": _statuses(derivations, computations, checked_problems),
        "limitations": limitations,
    }


def _domain_profile(root: Path) -> str:
    document = load_project_toml(root)
    course = document.get("course")
    if isinstance(course, dict) and isinstance(course.get("domain_profile"), str):
        return str(course["domain_profile"])
    return "GENERAL"


def _statuses(derivations: list[dict[str, object]], computations: list[dict[str, object]], problems: list[dict[str, object]]) -> list[str]:
    """The verification vocabulary actually used by stored records."""

    present = {"COMPUTATION_REPRODUCED"}
    for row in derivations:
        verification = row.get("verification")
        if isinstance(verification, dict):
            for check in verification.get("checks", []):
                if isinstance(check, dict) and isinstance(check.get("status"), str):
                    present.add(str(check["status"]))
    if problems:
        present.add("TWO_WITNESSES")
    if derivations:
        present.add("DIMENSIONALLY_VERIFIED")
    return sorted(present)
