"""Iterative chapter expansion against the planned teaching.

``expansion_plan`` compares the academic blueprint's planned concepts with
what the stored paragraphs actually teach (each paragraph may name the
concepts it covers). The output is a concrete expansion plan: which concept
needs which kind of content (definition, derivation, example, exercises) and
roughly how much, derived from the stored depth profile. It never pads: the
suggestions exist only for concepts the plan requires and the draft lacks.
"""

from __future__ import annotations

from pathlib import Path

from studium.authoring.academic_blueprint import academic_concepts, current_academic_blueprint
from studium.authoring.blueprint import current_sections
from studium.authoring.paragraphs import supported_paragraphs

_MIN_PARAGRAPHS_PER_SECTION = 2
_MIN_WORDS_PER_SECTION = 400


def expansion_plan(root: Path, section: object = None) -> dict[str, object]:
    """Concrete expansion suggestions for one section, or for the whole book."""

    wanted = None
    if section is not None:
        if not isinstance(section, str) or not section.strip():
            return {"status": "mcp.invalid_input", "message": "section must be a blueprint section id"}
        wanted = section.strip()
        known = {item["id"] for item in current_sections(root)}
        if wanted not in known:
            return {"status": "expansion.section_unknown", "message": "section is not in the stored blueprint"}

    paragraphs = supported_paragraphs(root)
    covered_ids: set[str] = set()
    per_section_words: dict[str, int] = {}
    per_section_count: dict[str, int] = {}
    for record in paragraphs:
        section_id = record.get("section")
        if not isinstance(section_id, str):
            continue
        if wanted is not None and section_id != wanted:
            continue
        per_section_count[section_id] = per_section_count.get(section_id, 0) + 1
        text = record.get("text")
        if isinstance(text, str):
            per_section_words[section_id] = per_section_words.get(section_id, 0) + len(text.split())
        concepts = record.get("concepts")
        if isinstance(concepts, list):
            for item in concepts:
                if isinstance(item, str):
                    covered_ids.add(item)

    blueprint = current_academic_blueprint(root)
    suggestions: list[dict[str, object]] = []
    concepts_planned = 0
    concepts_covered = 0
    if blueprint is not None:
        for concept in academic_concepts(root):
            concept_id = str(concept.get("id"))
            concept_section = concept.get("section")
            if wanted is not None and concept.get("chapter") != wanted and concept_section != wanted:
                continue
            concepts_planned += 1
            if concept_id in covered_ids:
                concepts_covered += 1
                continue
            suggestions.append(_concept_suggestion(concept, wanted))

    structural: list[dict[str, object]] = []
    sections = [item for item in current_sections(root) if wanted is None or item["id"] == wanted]
    for item in sections:
        section_id = item["id"]
        count = per_section_count.get(section_id, 0)
        words = per_section_words.get(section_id, 0)
        if count < _MIN_PARAGRAPHS_PER_SECTION:
            structural.append(
                {
                    "section": section_id,
                    "kind": "prose",
                    "needs": f"at least {_MIN_PARAGRAPHS_PER_SECTION} cited explanation paragraphs",
                    "have": {"paragraphs": count, "words": words},
                }
            )
        elif words < _MIN_WORDS_PER_SECTION:
            structural.append(
                {
                    "section": section_id,
                    "kind": "depth",
                    "needs": f"about {_MIN_WORDS_PER_SECTION} words of cited explanation",
                    "have": {"paragraphs": count, "words": words},
                }
            )

    return {
        "status": "ok",
        "section": wanted,
        "academic_blueprint": blueprint is not None,
        "concepts": {"planned": concepts_planned, "covered": concepts_covered},
        "concept_gaps": suggestions,
        "structural_gaps": structural,
        "next_step": _next_step(wanted, suggestions, structural),
    }


def _concept_suggestion(concept: dict[str, object], wanted: str | None) -> dict[str, object]:
    math_requirements = concept.get("math_requirements")
    needs = ["a cited explanation paragraph that names this concept"]
    derivations = 0
    if isinstance(math_requirements, list) and any("deriv" in str(item).casefold() for item in math_requirements):
        needs.append("a recorded derivation with assumptions, steps, and a checked status")
        derivations = 1
    examples = concept.get("examples")
    example_count = len(examples) if isinstance(examples, list) else 1
    if example_count:
        needs.append(f"about {example_count} worked or qualitative example")
    exercises = concept.get("exercises")
    if isinstance(exercises, int) and exercises > 0:
        needs.append(f"about {exercises} practice exercises with a solution appendix entry")
    return {
        "concept": concept.get("id"),
        "title": concept.get("title"),
        "chapter": concept.get("chapter"),
        "section": concept.get("section"),
        "needs": needs,
        "suggested_paragraphs": max(1, derivations + example_count // 2 + 1),
        "suggested_derivations": derivations,
        "suggested_exercises": exercises if isinstance(exercises, int) else 1,
    }


def _next_step(wanted: str | None, suggestions: list[dict[str, object]], structural: list[dict[str, object]]) -> str:
    if suggestions:
        concept = suggestions[0]
        return (
            f"write the missing content for concept {concept['concept']} "
            f"({concept['title']}) in section {concept['section'] or wanted or concept['chapter']}"
        )
    if structural:
        gap = structural[0]
        return f"expand section {gap['section']}: it needs {gap['needs']}"
    if wanted is None:
        return "the planned concepts are covered; continue with audit, contradiction scan, and review"
    return "this section covers the planned concepts; continue with audit, contradiction scan, and review"
