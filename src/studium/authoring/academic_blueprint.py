"""Hierarchical academic blueprint.

The flat outline stores section ids and titles only. The academic blueprint
adds the planned teaching: a tree of parts, chapters, sections, subsections,
and concepts, where every concept carries learning objectives, prerequisites,
required theoretical coverage, academic depth, sources, mathematical
requirements, recommended examples, and verification criteria.

The blueprint describes what must be taught, not only the headings. It is
stored next to the flat outline, which the writing pipeline continues to use.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from studium.policy.trust import contains_directive
from studium.storage.init_project import load_state_holding_lock
from studium.storage.locking import ProjectLocked, project_lock
from studium.storage.migrate import utc_now
from studium.storage.records import ACADEMIC_BLUEPRINT, append_jsonl, fold_by_id

_AUDIT = "audit/audit.jsonl"
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$")
_MAX_TITLE = 500
_MAX_CONCEPTS = 3000
_MAX_ITEMS = 40  # parts, chapters, sections, subsections each
_MAX_FIELD = 400  # objectives, prerequisites, sources, math requirements entries
_PART_KEYS = frozenset({"id", "title", "chapters", "learning_objectives"})
_CHAPTER_KEYS = frozenset({"id", "title", "learning_objectives", "prerequisites", "sections"})
_SECTION_KEYS = frozenset({"id", "title", "subsections", "concepts", "depth"})
_SUBSECTION_KEYS = frozenset({"id", "title", "concepts", "depth"})
_CONCEPT_KEYS = frozenset(
    {
        "id",
        "title",
        "learning_objectives",
        "prerequisites",
        "sources",
        "math_requirements",
        "verification_criteria",
        "depth",
        "examples",
        "exercises",
    }
)


def scaffold_academic_blueprint(
    root: Path,
    *,
    subject: object = None,
    profile_key: object = None,
    chapters_per_part: object = None,
    actor: dict[str, object] | None = None,
) -> dict[str, object]:
    """Generate an academic blueprint scaffold from the flat outline.

    Reads the stored flat blueprint sections, groups them into parts, and
    creates a minimal academic blueprint where each flat section becomes a
    chapter with one section and one concept. The AI agent can then refine
    this scaffold by calling store_academic_blueprint with an expanded version.

    Does not fabricate content — titles come from the flat outline.
    """

    from studium.authoring.blueprint import current_sections
    from studium.authoring.depth.profiles import resolve_depth_profile

    sections = current_sections(root)
    if not sections:
        return _error("mcp.invalid_input", "store a flat blueprint first")

    existing = current_academic_blueprint(root)
    if existing is not None:
        return _error(
            "mcp.invalid_input",
            "an academic blueprint already exists; use studium_academic_blueprint_store to replace it",
        )

    profile = None
    if profile_key is not None:
        profile, depth_error = resolve_depth_profile(profile_key)
        if depth_error is not None:
            return depth_error

    depth_label = profile.key if profile is not None else None

    cpp = 5
    if isinstance(chapters_per_part, int) and 2 <= chapters_per_part <= 20:
        cpp = chapters_per_part

    parts = _scaffold_parts(sections, depth_label, cpp)
    return store_academic_blueprint(
        root,
        parts=parts,
        subject=subject,
        profile_key=profile_key,
        actor=actor,
    )


def _scaffold_parts(
    sections: list[dict[str, str]],
    depth: str | None,
    chapters_per_part: int,
) -> list[dict[str, object]]:
    """Group flat sections into parts, each with chapters, sections, concepts."""

    parts: list[dict[str, object]] = []
    chunk_start = 0
    part_number = 0

    while chunk_start < len(sections):
        part_number += 1
        chunk_end = min(chunk_start + chapters_per_part, len(sections))
        chunk = sections[chunk_start:chunk_end]

        chapters: list[dict[str, object]] = []
        for sec in chunk:
            sec_id = f"{sec['id']}.s1"
            concept_id = f"{sec['id']}.c1"
            concept: dict[str, object] = {
                "id": concept_id,
                "title": sec["title"],
            }
            if depth is not None:
                concept["depth"] = depth
            section: dict[str, object] = {
                "id": sec_id,
                "title": sec["title"],
                "concepts": [concept],
            }
            if depth is not None:
                section["depth"] = depth
            chapter: dict[str, object] = {
                "id": sec["id"],
                "title": sec["title"],
                "sections": [section],
            }
            chapters.append(chapter)

        part: dict[str, object] = {
            "id": f"part-{part_number}",
            "title": f"Part {part_number}",
            "chapters": chapters,
        }
        parts.append(part)
        chunk_start = chunk_end

    return parts


def store_academic_blueprint(
    root: Path,
    *,
    parts: object,
    subject: object = None,
    profile_key: object = None,
    actor: dict[str, object] | None = None,
) -> dict[str, object]:
    """Replace the planned teaching hierarchy. Does not change project state."""

    cleaned, error = _parts(parts)
    if error is not None:
        return error
    subject_text = subject.strip() if isinstance(subject, str) and subject.strip() else None
    depth_error = None
    if profile_key is not None:
        from studium.authoring.depth.profiles import resolve_depth_profile

        _profile, depth_error = resolve_depth_profile(profile_key)
    if depth_error is not None:
        return depth_error
    try:
        with project_lock(root):
            record: dict[str, object] = {
                "schema_version": "1.0.0",
                "id": "academic",
                "subject": subject_text,
                "profile_key": profile_key if isinstance(profile_key, str) else None,
                "parts": cleaned,
                "recorded_at": utc_now(),
            }
            append_jsonl(root / ACADEMIC_BLUEPRINT, record)
            _audit(root, record=record, actor=actor)
            fresh = load_state_holding_lock(root)
            return {
                "status": "recorded",
                "blueprint": _public(record),
                "concepts": _concept_count(record),
                "local_sources": _local(fresh),
                "project_state": fresh.get("state"),
                "released": fresh.get("state") == "RELEASED",
            }
    except ProjectLocked:
        return _error("storage.locked", "project is locked")


def get_academic_blueprint(root: Path) -> dict[str, object]:
    """Return the stored hierarchy, or null when none is stored."""

    current = current_academic_blueprint(root)
    if current is None:
        return {"status": "ok", "blueprint": None}
    return {"status": "ok", "blueprint": _public(current)}


def current_academic_blueprint(root: Path) -> dict[str, object] | None:
    rows = fold_by_id(root / ACADEMIC_BLUEPRINT)
    for row in reversed(rows):
        if row.get("id") == "academic":
            return row
    return None


def academic_concepts(root: Path) -> list[dict[str, object]]:
    """All planned concepts flattened, each carrying its chapter and part id."""

    blueprint = current_academic_blueprint(root)
    if blueprint is None:
        return []
    found: list[dict[str, object]] = []
    for part in _iter(blueprint.get("parts")):
        for chapter in _iter(part.get("chapters")):
            for section in _iter(chapter.get("sections")):
                for concept in _iter(section.get("concepts")):
                    found.append(_with_ancestors(concept, part, chapter, section, None))
                for subsection in _iter(section.get("subsections")):
                    for concept in _iter(subsection.get("concepts")):
                        found.append(_with_ancestors(concept, part, chapter, section, subsection))
    return found


def academic_concepts_for_chapter(root: Path, chapter_id: str) -> list[dict[str, object]]:
    return [concept for concept in academic_concepts(root) if concept.get("chapter") == chapter_id]


def academic_concept_ids(root: Path) -> set[str]:
    return {str(concept["id"]) for concept in academic_concepts(root) if isinstance(concept.get("id"), str)}


def academic_chapter_ids(root: Path) -> list[str]:
    blueprint = current_academic_blueprint(root)
    identifiers: list[str] = []
    if blueprint is None:
        return identifiers
    for part in _iter(blueprint.get("parts")):
        for chapter in _iter(part.get("chapters")):
            identifier = chapter.get("id")
            if isinstance(identifier, str):
                identifiers.append(identifier)
    return identifiers


def academic_concept_coverage(root: Path, covered_ids: set[str]) -> dict[str, object]:
    """Planned concepts versus concepts the stored paragraphs explicitly claim."""

    all_concepts = academic_concepts(root)
    planned = len(all_concepts)
    covered = [concept for concept in all_concepts if str(concept.get("id")) in covered_ids]
    return {
        "planned": planned,
        "covered": len(covered),
        "uncovered": planned - len(covered),
        "gaps": [str(concept.get("id")) for concept in all_concepts if str(concept.get("id")) not in covered_ids],
    }


def _with_ancestors(
    concept: dict[str, object],
    part: dict[str, object],
    chapter: dict[str, object],
    section: dict[str, object],
    subsection: dict[str, object] | None,
) -> dict[str, object]:
    visible = dict(concept)
    visible["part"] = part.get("id")
    visible["chapter"] = chapter.get("id")
    visible["section"] = section.get("id")
    if subsection is not None:
        visible["subsection"] = subsection.get("id")
    return visible


def _parts(value: object) -> tuple[list[dict[str, object]] | None, dict[str, object] | None]:
    if not isinstance(value, list) or not value or len(value) > _MAX_ITEMS:
        return None, _error("mcp.invalid_input", "an academic blueprint needs at least one part")
    cleaned: list[dict[str, object]] = []
    seen: set[str] = set()
    total_concepts = 0
    for item in value:
        if not isinstance(item, dict):
            return None, _error("mcp.invalid_input", "each part needs an id, title, and chapters")
        if set(item) - _PART_KEYS:
            return None, _error("mcp.invalid_input", "parts may only carry id, title, learning_objectives, chapters")
        identifier, title, error = _ident(item)
        if error is not None:
            return None, error
        assert identifier is not None and title is not None
        if identifier in seen:
            return None, _error("mcp.invalid_input", "ids must be unique across the whole blueprint")
        seen.add(identifier)
        part: dict[str, object] = {"id": identifier, "title": title}
        objectives, error = _strings(item.get("learning_objectives"), "learning_objectives")
        if error is not None:
            return None, error
        if objectives:
            part["learning_objectives"] = objectives
        chapters, count, error = _chapters(item.get("chapters"), seen)
        if error is not None:
            return None, error
        total_concepts += count
        if total_concepts > _MAX_CONCEPTS:
            return None, _error("mcp.invalid_input", "too many planned concepts")
        part["chapters"] = chapters
        cleaned.append(part)
    return cleaned, None


def _chapters(
    value: object,
    seen: set[str],
) -> tuple[list[dict[str, object]], int, dict[str, object] | None]:
    if not isinstance(value, list) or not value or len(value) > _MAX_ITEMS:
        return [], 0, _error("mcp.invalid_input", "each part needs at least one chapter")
    cleaned: list[dict[str, object]] = []
    total = 0
    for item in value:
        if not isinstance(item, dict):
            return [], 0, _error("mcp.invalid_input", "each chapter needs an id, title, and sections")
        if set(item) - _CHAPTER_KEYS:
            return [], 0, _error("mcp.invalid_input", "chapters may only carry id, title, objectives, prerequisites, sections")
        identifier, title, error = _ident(item)
        if error is not None:
            return [], 0, error
        assert identifier is not None and title is not None
        if identifier in seen:
            return [], 0, _error("mcp.invalid_input", "ids must be unique across the whole blueprint")
        seen.add(identifier)
        chapter: dict[str, object] = {"id": identifier, "title": title}
        objectives, error = _strings(item.get("learning_objectives"), "learning_objectives")
        if error is not None:
            return [], 0, error
        if objectives:
            chapter["learning_objectives"] = objectives
        prerequisites, error = _strings(item.get("prerequisites"), "prerequisites")
        if error is not None:
            return [], 0, error
        if prerequisites:
            chapter["prerequisites"] = prerequisites
        sections, count, error = _sections(item.get("sections"), seen)
        if error is not None:
            return [], 0, error
        total += count
        chapter["sections"] = sections
        cleaned.append(chapter)
    return cleaned, total, None


def _sections(
    value: object,
    seen: set[str],
) -> tuple[list[dict[str, object]], int, dict[str, object] | None]:
    if not isinstance(value, list) or not value or len(value) > _MAX_ITEMS:
        return [], 0, _error("mcp.invalid_input", "each chapter needs at least one section")
    cleaned: list[dict[str, object]] = []
    total = 0
    for item in value:
        if not isinstance(item, dict):
            return [], 0, _error("mcp.invalid_input", "each section needs an id, title, and concepts")
        if set(item) - _SECTION_KEYS:
            return [], 0, _error("mcp.invalid_input", "sections may only carry id, title, subsections, concepts, depth")
        identifier, title, error = _ident(item)
        if error is not None:
            return [], 0, error
        assert identifier is not None and title is not None
        if identifier in seen:
            return [], 0, _error("mcp.invalid_input", "ids must be unique across the whole blueprint")
        seen.add(identifier)
        section: dict[str, object] = {"id": identifier, "title": title}
        depth, error = _depth(item.get("depth"))
        if error is not None:
            return [], 0, error
        if depth is not None:
            section["depth"] = depth
        concepts, count, error = _concepts(item.get("concepts"), seen)
        if error is not None:
            return [], 0, error
        total += count
        section["concepts"] = concepts
        subsections, count2, error = _subsections(item.get("subsections"), seen)
        if error is not None:
            return [], 0, error
        total += count2
        if subsections:
            section["subsections"] = subsections
        cleaned.append(section)
    return cleaned, total, None


def _subsections(
    value: object,
    seen: set[str],
) -> tuple[list[dict[str, object]], int, dict[str, object] | None]:
    if value is None:
        return [], 0, None
    if not isinstance(value, list) or len(value) > _MAX_ITEMS:
        return [], 0, _error("mcp.invalid_input", "subsections must be a list of items with id, title, concepts")
    cleaned: list[dict[str, object]] = []
    total = 0
    for item in value:
        if not isinstance(item, dict):
            return [], 0, _error("mcp.invalid_input", "each subsection needs an id, title, and concepts")
        if set(item) - _SUBSECTION_KEYS:
            return [], 0, _error("mcp.invalid_input", "subsections may only carry id, title, concepts, depth")
        identifier, title, error = _ident(item)
        if error is not None:
            return [], 0, error
        assert identifier is not None and title is not None
        if identifier in seen:
            return [], 0, _error("mcp.invalid_input", "ids must be unique across the whole blueprint")
        seen.add(identifier)
        subsection: dict[str, object] = {"id": identifier, "title": title}
        depth, error = _depth(item.get("depth"))
        if error is not None:
            return [], 0, error
        if depth is not None:
            subsection["depth"] = depth
        concepts, count, error = _concepts(item.get("concepts"), seen)
        if error is not None:
            return [], 0, error
        total += count
        subsection["concepts"] = concepts
        cleaned.append(subsection)
    return cleaned, total, None


def _concepts(
    value: object,
    seen: set[str],
) -> tuple[list[dict[str, object]], int, dict[str, object] | None]:
    if not isinstance(value, list) or not value or len(value) > _MAX_ITEMS:
        return [], 0, _error("mcp.invalid_input", "each section needs at least one concept")
    cleaned: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            return [], 0, _error("mcp.invalid_input", "each concept needs an id and title")
        if set(item) - _CONCEPT_KEYS:
            return [], 0, _error(
                "mcp.invalid_input",
                "concepts may only carry id, title, learning_objectives, prerequisites, sources, "
                "math_requirements, verification_criteria, depth, examples, exercises",
            )
        identifier, title, error = _ident(item)
        if error is not None:
            return [], 0, error
        assert identifier is not None and title is not None
        if identifier in seen:
            return [], 0, _error("mcp.invalid_input", "ids must be unique across the whole blueprint")
        seen.add(identifier)
        concept: dict[str, object] = {"id": identifier, "title": title}
        for key, message in (
            ("learning_objectives", "learning_objectives"),
            ("prerequisites", "prerequisites"),
            ("sources", "sources"),
            ("math_requirements", "math_requirements"),
            ("verification_criteria", "verification_criteria"),
        ):
            values, error = _strings(item.get(key), message)
            if error is not None:
                return [], 0, error
            if values:
                concept[key] = values
        depth, error = _depth(item.get("depth"))
        if error is not None:
            return [], 0, error
        if depth is not None:
            concept["depth"] = depth
        examples, error = _strings(item.get("examples"), "examples")
        if error is not None:
            return [], 0, error
        if examples:
            concept["examples"] = examples
        exercises = item.get("exercises")
        if exercises is not None:
            if isinstance(exercises, bool) or not isinstance(exercises, int) or exercises < 1 or exercises > 30:
                return [], 0, _error("mcp.invalid_input", "exercises must be an integer between 1 and 30")
            concept["exercises"] = exercises
        cleaned.append(concept)
    return cleaned, len(cleaned), None


def _ident(item: dict[str, object]) -> tuple[str | None, str | None, dict[str, object] | None]:
    identifier = item.get("id")
    title = item.get("title")
    if not isinstance(identifier, str) or _ID.fullmatch(identifier.strip()) is None:
        return None, None, _error("mcp.invalid_input", "id is invalid")
    if not isinstance(title, str) or not title.strip() or len(title.strip()) > _MAX_TITLE:
        return None, None, _error("mcp.invalid_input", "title is required")
    if contains_directive(title.encode("utf-8")):
        return None, None, _error("policy.directive", "the title changed or requested policy")
    return identifier.strip(), title.strip(), None


def _strings(value: object, field: str) -> tuple[list[str] | None, dict[str, object] | None]:
    if value is None:
        return [], None
    if not isinstance(value, list) or len(value) > _MAX_ITEMS:
        return None, _error("mcp.invalid_input", f"{field} must be a list of short strings")
    cleaned: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip() or len(item) > _MAX_FIELD:
            return None, _error("mcp.invalid_input", f"{field} entries must be short strings")
        cleaned.append(item.strip())
    return cleaned, None


def _depth(value: object) -> tuple[str | None, dict[str, object] | None]:
    if value is None:
        return None, None
    from studium.authoring.depth.profiles import PROFILE_KEYS

    if not isinstance(value, str) or value.strip().upper() not in PROFILE_KEYS:
        return None, _error("mcp.invalid_input", "depth must be a known academic depth profile")
    return value.strip().upper(), None


def _concept_count(record: dict[str, object]) -> int:
    return len(academic_concepts_from_record(record))


def academic_concepts_from_record(record: dict[str, object]) -> list[dict[str, object]]:
    """Flatten concepts from a stored record, without touching the project."""

    found: list[dict[str, object]] = []
    for part in _iter(record.get("parts")):
        for chapter in _iter(part.get("chapters")):
            for section in _iter(chapter.get("sections")):
                for concept in _iter(section.get("concepts")):
                    found.append(concept)
                for subsection in _iter(section.get("subsections")):
                    for concept in _iter(subsection.get("concepts")):
                        found.append(concept)
    return found


def _public(record: dict[str, object]) -> dict[str, object]:
    return {
        "id": record.get("id"),
        "subject": record.get("subject"),
        "profile_key": record.get("profile_key"),
        "parts": record.get("parts"),
    }


def _iter(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _audit(root: Path, *, record: dict[str, object], actor: dict[str, object] | None) -> None:
    digest = hashlib.sha256(repr(record.get("parts")).encode("utf-8")).hexdigest()
    append_jsonl(
        root / _AUDIT,
        {
            "schema_version": "1.0.0",
            "timestamp": utc_now(),
            "source_id": "academic",
            "operation": "store_academic_blueprint",
            "origin": None,
            "actor": _actor(actor),
            "previous_hash": None,
            "new_hash": digest,
            "result": "planned",
            "tool": "academic_blueprint_store",
            "content_directives_ignored": False,
        },
    )


def _actor(actor: dict[str, object] | None) -> dict[str, object] | None:
    if not actor:
        return None
    safe: dict[str, object] = {}
    for key in ("kind", "name", "provider"):
        value = actor.get(key)
        if isinstance(value, str) and value and "/" not in value and "~" not in value and len(value) <= 80:
            safe[key] = value
    return safe or None


def _local(state: dict[str, object]) -> dict[str, object]:
    local = state.get("local_sources")
    if isinstance(local, dict):
        return dict(local)
    return {"status": "UNKNOWN", "prompted": False, "source_count": 0}


def _error(code: str, message: str) -> dict[str, object]:
    return {"status": code, "message": message}
