"""Compact context packets for long authoring sessions.

A packet is a deterministic summary the client can hand to a fresh session:
what is stored for one chapter, what is missing, and what the next concrete
step is. It stays compact: paragraph bodies are reduced to their opening
sentence, and every list is bounded.
"""

from __future__ import annotations

from pathlib import Path

from studium.authoring.academic_blueprint import academic_concepts_for_chapter
from studium.authoring.audit import audited_paragraph_ids
from studium.authoring.blueprint import current_sections
from studium.authoring.contradictions import open_contradictions
from studium.authoring.depth.planner import depth_plan_status
from studium.authoring.derivations import derivations_for_section
from studium.authoring.excerpts import excerpts_by_id
from studium.authoring.paragraphs import supported_paragraphs
from studium.authoring.problems import problem_result_current
from studium.storage.init_project import load_state_holding_lock
from studium.storage.records import (
    AUDITS,
    DERIVATIONS,
    EXCERPTS,
    NOTATION,
    PROBLEMS,
    PUBLIC_BIBLIOGRAPHY,
    REVIEWS,
    TERMINOLOGY,
    fold_by_id,
)

_MAX_PARAGRAPHS = 40
_MAX_ISSUES = 30


def chapter_context(root: Path, section: object) -> dict[str, object]:
    """The stored state for one chapter, reduced to what a session needs."""

    if not isinstance(section, str) or not section.strip():
        return {"status": "mcp.invalid_input", "message": "section must be a blueprint section id"}
    section_id = section.strip()
    known = {item["id"]: item["title"] for item in current_sections(root)}
    if section_id not in known:
        return {"status": "context.section_unknown", "message": "section is not in the stored blueprint"}

    stored = excerpts_by_id(root)
    audited = audited_paragraph_ids(root)
    paragraphs = [item for item in supported_paragraphs(root) if item.get("section") == section_id]
    excerpt_ids: set[str] = set()
    lines: list[dict[str, object]] = []
    for record in paragraphs[:_MAX_PARAGRAPHS]:
        text = str(record.get("text") or "")
        excerpts = record.get("excerpts")
        if isinstance(excerpts, list):
            excerpt_ids.update(str(item) for item in excerpts)
        lines.append(
            {
                "id": record.get("id"),
                "role": record.get("role"),
                "opening": text.split(". ")[0] + "." if text else "",
                "words": len(text.split()),
                "audited": record.get("id") in audited,
                "concepts": record.get("concepts") if isinstance(record.get("concepts"), list) else [],
            }
        )

    sources: set[str] = set()
    for identifier in excerpt_ids:
        excerpt = stored.get(identifier)
        if excerpt is not None and isinstance(excerpt.get("source_id"), str):
            sources.add(str(excerpt["source_id"]))

    problems = [item for item in fold_by_id(root / PROBLEMS) if item.get("section") == section_id]
    derivations = derivations_for_section(root, section_id)
    concepts = academic_concepts_for_chapter(root, section_id)
    covered = {str(name) for line in lines for name in line["concepts"]}  # type: ignore[union-attr]
    issues: list[str] = []
    if not paragraphs:
        issues.append("no supported paragraphs yet")
    if len(paragraphs) < 2:
        issues.append("fewer than two cited explanation paragraphs")
    for concept in concepts:
        if str(concept.get("id")) not in covered:
            issues.append(f"planned concept not taught yet: {concept.get('id')} ({concept.get('title')})")
    for record in problems:
        if not problem_result_current(root, record):
            issues.append(f"problem without a current checked result: {record.get('id')}")
    for record in derivations:
        verification = record.get("verification")
        status = str((verification or {}).get("status")) if isinstance(verification, dict) else "UNVERIFIED"
        if status in {"UNVERIFIED", "FAILED"}:
            issues.append(f"derivation not verified: {record.get('id')} is {status}")

    return {
        "status": "ok",
        "section": section_id,
        "title": known[section_id],
        "paragraphs": lines,
        "sources": len(sources),
        "derivations": [
            {"id": record.get("id"), "name": record.get("name"), "equation": record.get("equation")}
            for record in derivations
        ],
        "problems": [
            {"id": record.get("id"), "role": record.get("role"), "checked": problem_result_current(root, record)}
            for record in problems
        ],
        "concepts": [
            {"id": concept.get("id"), "title": concept.get("title"), "taught": str(concept.get("id")) in covered}
            for concept in concepts
        ],
        "issues": issues[:_MAX_ISSUES],
        "next_step": issues[0] if issues else "audit, contradiction scan, and review for this chapter",
    }


def resume_packet(root: Path) -> dict[str, object]:
    """Project-level packet: state, counts, and what remains open."""

    state = load_state_holding_lock(root)
    sections = current_sections(root)
    paragraphs = supported_paragraphs(root)
    written = {str(item.get("section")) for item in paragraphs if isinstance(item.get("section"), str)}
    audited = audited_paragraph_ids(root)
    contradictions = open_contradictions(root)
    derivations = fold_by_id(root / DERIVATIONS)
    unverified = [
        record
        for record in derivations
        if isinstance(record.get("verification"), dict) and str(record["verification"].get("status")) in {"UNVERIFIED", "FAILED"}  # type: ignore[index]
    ]
    problems = fold_by_id(root / PROBLEMS)
    checked = [record for record in problems if problem_result_current(root, record)]
    plan = depth_plan_status(root)
    missing_sections = [item["id"] for item in sections if item["id"] not in written]
    unreviewed = [item["id"] for item in sections if item["id"] in written and not _section_audited(root, item["id"], audited)]

    steps: list[str] = []
    if not sections:
        steps.append("store a blueprint outline with studium_blueprint_store")
    if missing_sections:
        steps.append(f"write the chapters with no supported paragraphs: {', '.join(missing_sections[:10])}")
    if unreviewed:
        steps.append(f"record audits for the unaudited chapters: {', '.join(unreviewed[:10])}")
    if unverified:
        steps.append(f"check the unverified derivations: {', '.join(str(r.get('id')) for r in unverified[:10])}")
    if contradictions:
        steps.append("resolve the open contradictions before review")
    if not steps:
        steps.append("run the contradiction scan, book review, and render")

    return {
        "status": "ok",
        "project_state": state.get("state"),
        "released": state.get("state") == "RELEASED",
        "counts": {
            "sections": len(sections),
            "sections_written": len(written),
            "paragraphs": len(paragraphs),
            "paragraphs_audited": len(audited),
            "sources": sum(1 for row in fold_by_id(root / PUBLIC_BIBLIOGRAPHY) if row.get("deleted") is not True),
            "excerpts": len(fold_by_id(root / EXCERPTS)),
            "problems": len(problems),
            "problems_checked": len(checked),
            "derivations": len(derivations),
            "derivations_unverified": len(unverified),
            "audits": len(fold_by_id(root / AUDITS)),
            "contradictions_open": len(contradictions),
            "reviews": len(fold_by_id(root / REVIEWS)),
            "notation": len(fold_by_id(root / NOTATION)),
            "terminology": len(fold_by_id(root / TERMINOLOGY)),
        },
        "missing_sections": missing_sections,
        "unreviewed_sections": unreviewed[:_MAX_ISSUES],
        "open_contradictions": len(contradictions),
        "depth_plan": plan.get("status"),
        "next_steps": steps[:_MAX_ISSUES],
    }


def _section_audited(root: Path, section_id: str, audited: set[str]) -> bool:
    paragraphs = [item for item in supported_paragraphs(root) if item.get("section") == section_id]
    return bool(paragraphs) and all(item.get("id") in audited for item in paragraphs)
