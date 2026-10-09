"""Source coverage per section and per planned concept.

Counts, for each blueprint section, how many distinct sources the cited
excerpts come from, and how many planned concepts those paragraphs claim to
teach. Low source counts are reported; they are never hidden behind totals.
"""

from __future__ import annotations

from pathlib import Path

from studium.authoring.academic_blueprint import academic_concepts
from studium.authoring.blueprint import current_sections
from studium.authoring.excerpts import excerpts_by_id
from studium.authoring.paragraphs import supported_paragraphs
from studium.storage.init_project import load_project_toml
from studium.storage.records import PUBLIC_BIBLIOGRAPHY, fold_by_id

_MIN_SOURCES_PER_SECTION = 1


def source_coverage(root: Path, section: object = None) -> dict[str, object]:
    """Distinct sources and concept coverage per section, or one section."""

    wanted = None
    if section is not None:
        if not isinstance(section, str) or not section.strip():
            return {"status": "mcp.invalid_input", "message": "section must be a blueprint section id"}
        wanted = section.strip()
        known = {item["id"] for item in current_sections(root)}
        if wanted not in known:
            return {"status": "coverage.section_unknown", "message": "section is not in the stored blueprint"}

    stored = excerpts_by_id(root)
    paragraphs = supported_paragraphs(root)
    sections = [item for item in current_sections(root) if wanted is None or item["id"] == wanted]

    concepts_by_chapter: dict[str, set[str]] = {}
    for concept in academic_concepts(root):
        chapter = concept.get("chapter")
        if isinstance(chapter, str):
            concepts_by_chapter.setdefault(chapter, set()).add(str(concept.get("id")))

    per_section: list[dict[str, object]] = []
    used_sources: set[str] = set()
    covered_concepts: set[str] = set()
    for item in sections:
        section_id = item["id"]
        sources: set[str] = set()
        concepts: set[str] = set()
        count = 0
        for record in paragraphs:
            if record.get("section") != section_id:
                continue
            count += 1
            excerpts = record.get("excerpts")
            if isinstance(excerpts, list):
                for identifier in excerpts:
                    excerpt = stored.get(str(identifier))
                    if excerpt is not None and isinstance(excerpt.get("source_id"), str):
                        sources.add(str(excerpt["source_id"]))
            names = record.get("concepts")
            if isinstance(names, list):
                concepts.update(str(name) for name in names)
        planned = concepts_by_chapter.get(section_id, set())
        per_section.append(
            {
                "section": section_id,
                "paragraphs": count,
                "sources": len(sources),
                "sources_ok": len(sources) >= _MIN_SOURCES_PER_SECTION,
                "concepts_planned": len(planned),
                "concepts_covered": len(planned & concepts),
                "concept_gaps": sorted(planned - concepts),
            }
        )
        used_sources.update(sources)
        covered_concepts.update(concepts)

    total_sources = sum(1 for row in fold_by_id(root / PUBLIC_BIBLIOGRAPHY) if row.get("deleted") is not True)
    thin = [item for item in per_section if item["sources_ok"] is False]
    planned_total = sum(int(value) for item in per_section if isinstance((value := item["concepts_planned"]), int))
    covered_total = sum(int(value) for item in per_section if isinstance((value := item["concepts_covered"]), int))
    return {
        "status": "ok",
        "section": wanted,
        "sections": per_section,
        "totals": {
            "sections": len(per_section),
            "sources_recorded": total_sources,
            "sources_used": len(used_sources),
            "sources_unused": max(0, total_sources - len(used_sources)),
            "concepts_planned": planned_total,
            "concepts_covered": covered_total,
            "concept_coverage": round(covered_total / planned_total, 3) if planned_total else None,
        },
        "thin_sections": [str(item["section"]) for item in thin],
        "domain_profile": _domain_profile(root),
    }


def _domain_profile(root: Path) -> str:
    document = load_project_toml(root)
    course = document.get("course")
    if isinstance(course, dict) and isinstance(course.get("domain_profile"), str):
        return str(course["domain_profile"])
    return "GENERAL"
