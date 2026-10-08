"""The next tool call for one open draft.

The client searches open sources and writes the draft. This does not ask the
user when that step can be done from open sources or from sources already
given, and it does not release the book.
"""

import re
from pathlib import Path

from studium.authoring.audit import (
    audited_paragraph_ids,
    explicit_gap_ids,
    review_edition,
    review_is_current,
    scan_is_current,
    section_needs_more_prose,
    short_paragraph_id,
    writer_edition,
)
from studium.authoring.blueprint import current_sections
from studium.authoring.computation import list_computations
from studium.authoring.problems import REPRODUCIBILITY_TEXT, RUST_NOT_WORKED_PROBLEM
from studium.authoring.excerpts import excerpts_by_id
from studium.authoring.paragraphs import supported_paragraphs, supported_section_ids
from studium.authoring.section_blocks import blocked_ids, blocked_sections, mark_blocked, offers_for, remember_offer
from studium.authoring.support import draft_source_usable
from studium.domain.profiles import BOOK_TOPIC
from studium.research.course_documents import list_course_documents
from studium.research.public_sources import license_forbids_use
from studium.storage.init_project import book_kind, load_project_toml, load_state
from studium.storage.records import (
    BLUEPRINT,
    CLAIMS,
    COMPUTATIONS,
    EXCERPTS,
    AUDITS,
    CONTRADICTIONS,
    FIGURES,
    PARAGRAPHS,
    REVIEWS,
    PROBLEMS,
    PUBLIC_BIBLIOGRAPHY,
    SECTION_BLOCKS,
    SECTION_OFFERS,
    fold_by_id,
)

_ASK = "ask the user"
_FORMAT = "do not ask the user how to format the page."
_MIN_SECTIONS = 8
_MIN_SOURCES = 12
_MIN_EXPLANATION_WORDS = 400
_MIN_EXPLANATION_SECTIONS = 2
_LOCAL_REGISTRY = "sources/registry.jsonl"
_PIRATE_KINDS = frozenset({"pirate", "pirated", "unauthorized", "unauthorised"})
_TOO_SHORT = (
    "The study book is too short. Store at least 8 blueprint sections before writing or rendering."
)
_NEED_SOURCES = (
    "Search open sources and record another source. "
    "Fewer than 12 distinct sources are stored. "
    "User-provided local sources and open-web sources both count. "
    "Pirate copies and forbidden licenses do not. Do not write or render yet."
)
_RUST_PROBLEM = (
    f"{RUST_NOT_WORKED_PROBLEM} {REPRODUCIBILITY_TEXT} "
    "Record a replayed computation or a numeric result cited from two excerpts."
)
_RUST_REMOVE = (
    "A Rust test cannot be the worked problem of a book that is not COMPUTER_SCIENCE. "
    "Remove that stored problem before recording a new computation."
)
_UNWRITTEN = (
    "Write the next unwritten chapter: {title}. "
    "The book is incomplete while {title} has no paragraphs. "
    "Do not render it as finished."
)
_TWO_SECTIONS = (
    "This chapter needs at least two section blocks of explanation, not a single Explicación, "
    "plus the lead, one consejo, one worked problem, and one autoficha."
)
_CHAPTER = (
    "Write a full chapter in Spanish, several paragraphs of explanation as body text, not a summary and not a sentence. "
    "The explanation needs at least two section blocks and 400 words. "
    "Use the same shape every chapter: a short lead, the explanation, at most one consejo, "
    "definitions only for new terms, one worked problem with enunciado, resolución, and respuesta, "
    "and one autoficha. "
    "Boxes are only those four. Cite stored excerpts. "
    "A formula must be quoted in an excerpt or replayed. "
    "A worked problem in a book that is not COMPUTER_SCIENCE is a replayed computation or a numeric result cited from two excerpts. "
    "Code behavior needs two sources or a test that passed 3 times. "
    "Do not ask the user how to format the page. The renderer owns the boxes."
)
_ARITHMETIC = re.compile(r"^[0-9+\-*/×÷·().=]+$")
_BODY_SKIP = frozenset({"purpose", "consejo", "definition", "self_check"})
_CODE_OR_CALCULATION = frozenset({"COMPUTER_SCIENCE", "STEM"})
_DRAFT_INPUTS = (
    PARAGRAPHS,
    PROBLEMS,
    COMPUTATIONS,
    FIGURES,
    AUDITS,
    CONTRADICTIONS,
    REVIEWS,
    BLUEPRINT,
    CLAIMS,
    EXCERPTS,
    SECTION_BLOCKS,
    SECTION_OFFERS,
)
_NO_SECOND = "no second independent open excerpt"
_NO_REPLAY = "no replayed check"


def book_next(root: Path) -> dict[str, object]:
    """Return the next concrete tool call. Does not write and does not fetch."""

    state = load_state(root)
    if book_kind(root) != BOOK_TOPIC and not _course_documents(root):
        return _step(
            state,
            "studium_course_document_record",
            {},
            "Open the official course document and record its title and url.",
        )
    attached = _known_source_file(root, state)
    if attached is not None:
        return _step(
            state,
            "studium_source_intake",
            {"path": attached},
            "Import the source file the user already gave.",
        )
    if not _public_records(root):
        return _step(
            state,
            "studium_public_source_record",
            {},
            "Search open sources, open the page, and record the source you opened. Refuse pirate copies.",
        )
    missing = _source_without_excerpt(root)
    if missing is not None:
        arguments: dict[str, object] = {"source_id": missing["id"]}
        url = missing.get("url")
        if isinstance(url, str):
            arguments["url"] = url
        return _step(
            state,
            "studium_excerpt_record",
            arguments,
            "Open that page and store the excerpt you read. The server does not download it.",
        )
    sections = current_sections(root)
    if not sections:
        if book_kind(root) == BOOK_TOPIC or not _course_documents(root):
            return _step(
                state,
                "studium_blueprint_store",
                {"sections": _study_sections(root)},
                (
                    f"{_TOO_SHORT} No course guide is stored. Build the study book: roadmap, foundations, "
                    "the topic chapters, worked problems, self-check, a formula or concept sheet, "
                    "and the source audit. Do not invent a citation."
                ),
            )
        return _step(
            state,
            "studium_blueprint_store",
            {},
            "Store the section ids and titles from the stored course guide. Do not invent a citation.",
        )
    outline = _outline_gate(state, root, sections)
    if outline is not None:
        return outline
    quality = _chapter_gate(state, root, sections)
    if quality is not None:
        return quality
    if _profile(root) == "COMPUTER_SCIENCE" and _foreign_rust(root) is None:
        problem = _pending_problem(root, sections)
        if problem is not None and problem.get("tool") == "studium_problem_check":
            return _step(state, str(problem["tool"]), _arguments(problem.get("arguments")), str(problem["reason"]))
    pending = _pending_paragraph(root, sections)
    if pending is not None:
        section, excerpt_id = pending
        return _unwritten_step(state, root, section, excerpt_id)
    problem = _pending_problem(root, sections)
    if problem is not None:
        return _step(state, str(problem["tool"]), _arguments(problem.get("arguments")), str(problem["reason"]))
    longer = _pending_length(root, sections)
    if longer is not None:
        kind, section, excerpt_id, paragraph_id = longer
        if kind == "replace" and paragraph_id is not None:
            return _step(
                state,
                "studium_paragraph_replace",
                {"id": paragraph_id, "excerpts": [excerpt_id]},
                (
                    f"Rewrite {paragraph_id} in {section['id']} ({section['title']}) into teaching prose. "
                    "A section of one short paragraph does not count as written. "
                    "A one-sentence section is too short to teach. Attach the sources you used. "
                    + _CHAPTER
                ),
                blocked=blocked_sections(root),
            )
        return _step(
            state,
            "studium_paragraph_record",
            {"section": section["id"], "excerpts": [excerpt_id], "role": "explanation"},
            (
                f"Write another explanatory paragraph for {section['id']} ({section['title']}). "
                "A section of one short paragraph does not count as written. "
                "A one-sentence section is too short to teach. "
                + _CHAPTER
            ),
            blocked=blocked_sections(root),
        )
    self_check = _pending_self_check(root, sections)
    if self_check is not None:
        section, excerpt_id = self_check
        return _step(
            state,
            "studium_paragraph_record",
            {"section": section["id"], "excerpts": [excerpt_id], "role": "self_check"},
            (
                f"Add one autoficha for {section['id']} ({section['title']}). "
                "The explanation above must still teach from the excerpts. "
                + _CHAPTER
            ),
            blocked=blocked_sections(root),
        )
    for section in sections:
        if _paragraph_count(root, section["id"]) == 0:
            return _unwritten_step(state, root, section, _excerpt_for_section(root, section["id"]))
        if _explanation_words(root, section["id"]) < _MIN_EXPLANATION_WORDS:
            return _explanation_step(state, root, section)
    audit = _pending_audit(root)
    if audit is not None:
        return _step(
            state,
            "studium_audit_record",
            {"target": audit},
            (
                f"Audit {audit}. Cite a passed tool result: two excerpts from different sources, "
                "a replayed computation, a Rust test that passed 3 times, or a checked figure. "
                "The audit adds no new prose."
            ),
            blocked=blocked_sections(root),
        )
    if not scan_is_current(root) and not offers_for(root, writer_edition(root), "contradiction_scan"):
        remember_offer(root, section_id=writer_edition(root), kind="contradiction_scan")
        return _step(
            state,
            "studium_contradiction_scan",
            {},
            "Compare stored numeric results and claims. An open contradiction blocks review.",
            blocked=blocked_sections(root),
        )
    if not review_is_current(root) and not offers_for(root, review_edition(root), "book_review"):
        remember_offer(root, section_id=review_edition(root), kind="book_review")
        return _step(
            state,
            "studium_book_review",
            {},
            "Review this edition. audit_passed does not release the book.",
            blocked=blocked_sections(root),
        )
    outline = _outline_gate(state, root, sections)
    if outline is not None:
        return outline
    quality = _chapter_gate(state, root, sections)
    if quality is not None:
        return quality
    unwritten = _first_unwritten(root, sections)
    if unwritten is not None:
        return _unwritten_step(state, root, unwritten, _excerpt_for_section(root, unwritten["id"]))
    if not _draft_is_current(root):
        return _render_step(state, root, sections)
    return _step(state, None, {}, "The DRAFT is rendered. Do not request release.", blocked=blocked_sections(root))


def _unwritten_reason(section: dict[str, str]) -> str:
    title = section["title"].strip() or section["id"]
    return _UNWRITTEN.format(title=title)


def _first_unwritten(root: Path, sections: list[dict[str, str]]) -> dict[str, str] | None:
    covered = supported_section_ids(root)
    return next((section for section in sections if section["id"] not in covered), None)


def _paragraph_count(root: Path, section_id: str) -> int:
    return sum(1 for record in supported_paragraphs(root) if record.get("section") == section_id)


def _unwritten_step(
    state: dict[str, object],
    root: Path,
    section: dict[str, str],
    excerpt_id: str | None,
) -> dict[str, object]:
    """An empty planned chapter is the next action, not a finished render."""

    if excerpt_id is None:
        return _step(state, "studium_public_source_record", {}, _NEED_SOURCES)
    return _step(
        state,
        "studium_paragraph_record",
        {"section": section["id"], "excerpts": [excerpt_id], "role": "explanation"},
        _unwritten_reason(section),
        blocked=blocked_sections(root),
    )


def _render_step(
    state: dict[str, object],
    root: Path,
    sections: list[dict[str, str]],
) -> dict[str, object]:
    empty = _empty_sections(sections, supported_section_ids(root))
    blocked = blocked_sections(root)
    parts: list[str] = []
    if blocked:
        names = ", ".join(f"{item['id']} ({item['title']})" if item["title"] else str(item["id"]) for item in blocked)
        parts.append(f"Blocked sections: {names}.")
    if empty:
        names = ", ".join(f"{section['id']} ({section['title']})" for section in empty)
        parts.append(f"Empty sections stay gaps: {names}.")
    parts.append("Render the DRAFT. Do not request release.")
    return _step(state, "studium_render", {}, " ".join(parts), blocked=blocked)


def _pending_problem(root: Path, sections: list[dict[str, str]]) -> dict[str, object] | None:
    profile = _profile(root)
    if profile not in _CODE_OR_CALCULATION or not sections:
        return None
    section = sections[0]
    section_id = section["id"]
    if section_id in blocked_ids(root):
        return None
    if profile == "COMPUTER_SCIENCE":
        rust = [record for record in fold_by_id(root / PROBLEMS) if record.get("kind") == "rust"]
        if any(record.get("status") == "checked" and record.get("correct") is True for record in rust):
            return None
        unchecked = next((record for record in rust if isinstance(record.get("id"), str)), None)
        if unchecked is not None:
            runs = unchecked.get("runs")
            failed = isinstance(runs, list) and any(isinstance(run, dict) and run.get("passed") is False for run in runs)
            offered = offers_for(root, section_id, "problem_check")
            if failed or offered:
                mark_blocked(root, section_id=section_id, title=section["title"], reason=_NO_REPLAY)
                return None
            remember_offer(root, section_id=section_id, kind="problem_check")
            return {
                "tool": "studium_problem_check",
                "arguments": {"id": unchecked["id"]},
                "reason": f"Run studium_problem_check. {REPRODUCIBILITY_TEXT}",
            }
        if offers_for(root, section_id, "problem_record"):
            mark_blocked(root, section_id=section_id, title=section["title"], reason=_NO_REPLAY)
            return None
        remember_offer(root, section_id=section_id, kind="problem_record")
        return {
            "tool": "studium_problem_record",
            "arguments": {"section": section_id},
            "reason": "Record a Rust test for this code section. The server reruns it before it is checked.",
        }
    if any(item.get("status") == "replayed" and item.get("correct") is True for item in list_computations(root)):
        return None
    if offers_for(root, section_id, "computation"):
        mark_blocked(root, section_id=section_id, title=section["title"], reason=_NO_REPLAY)
        return None
    remember_offer(root, section_id=section_id, kind="computation")
    return {
        "tool": "studium_computation_check",
        "arguments": {"section": section_id},
        "reason": (
            "Store the expression and the result for this calculation. "
            "It is accepted only when the server evaluates the same expression again."
        ),
    }


def _pending_paragraph(
    root: Path,
    sections: list[dict[str, str]],
) -> tuple[dict[str, str], str] | None:
    empty = [section for section in _empty_sections(sections, supported_section_ids(root)) if section["id"] not in blocked_ids(root)]
    if not empty:
        return None
    unused = _unused_excerpts(root)
    can_second = len({source_id for _excerpt_id, source_id in unused}) >= 2 or _independent_source_count(root) >= 2
    for section in empty:
        excerpt_id = _unoffered_excerpt(root, section["id"], unused)
        if excerpt_id is not None and not offers_for(root, section["id"], "paragraph"):
            remember_offer(root, section_id=section["id"], kind="paragraph", excerpt_id=excerpt_id)
            return section, excerpt_id
        if can_second and excerpt_id is not None:
            remember_offer(root, section_id=section["id"], kind="paragraph", excerpt_id=excerpt_id)
            return section, excerpt_id
        mark_blocked(root, section_id=section["id"], title=section["title"], reason=_NO_SECOND)
    return None


def _unoffered_excerpt(root: Path, section_id: str, unused: list[tuple[str, str]]) -> str | None:
    offered = {
        record.get("excerpt")
        for record in offers_for(root, section_id, "paragraph")
        if isinstance(record.get("excerpt"), str)
    }
    for excerpt_id, _source_id in unused:
        if excerpt_id not in offered:
            return excerpt_id
    return None


def _unused_excerpts(root: Path) -> list[tuple[str, str]]:
    used: set[str] = set()
    for paragraph in supported_paragraphs(root):
        excerpts = paragraph.get("excerpts")
        if isinstance(excerpts, list):
            used.update(item for item in excerpts if isinstance(item, str))
    sources = _source_by_id(root)
    found: list[tuple[str, str]] = []
    for record in excerpts_by_id(root).values():
        identifier = record.get("id")
        source_id = record.get("source_id")
        if not isinstance(identifier, str) or identifier in used or not isinstance(source_id, str):
            continue
        source = sources.get(source_id)
        if source is None or not draft_source_usable(root, source):
            continue
        found.append((identifier, source_id))
    return found


def _independent_source_count(root: Path) -> int:
    return len({source_id for _excerpt_id, source_id in _all_usable_excerpts(root)})


def _all_usable_excerpts(root: Path) -> list[tuple[str, str]]:
    sources = _source_by_id(root)
    found: list[tuple[str, str]] = []
    for record in excerpts_by_id(root).values():
        identifier = record.get("id")
        source_id = record.get("source_id")
        if not isinstance(identifier, str) or not isinstance(source_id, str):
            continue
        source = sources.get(source_id)
        if source is None or not draft_source_usable(root, source):
            continue
        found.append((identifier, source_id))
    return found


def _source_without_excerpt(root: Path) -> dict[str, object] | None:
    opened = {
        record.get("source_id")
        for record in excerpts_by_id(root).values()
        if isinstance(record.get("source_id"), str)
    }
    for source in _usable_sources(root):
        if not _source_counts(source):
            continue
        if source.get("id") not in opened:
            return source
    return None


def _usable_sources(root: Path) -> list[dict[str, object]]:
    return [record for record in _public_records(root) if draft_source_usable(root, record)]


def _public_records(root: Path) -> list[dict[str, object]]:
    return fold_by_id(root / PUBLIC_BIBLIOGRAPHY)


def _source_by_id(root: Path) -> dict[str, dict[str, object]]:
    found: dict[str, dict[str, object]] = {}
    for record in _public_records(root):
        identifier = record.get("id")
        if isinstance(identifier, str):
            found[identifier] = record
    return found


def _empty_sections(
    sections: list[dict[str, str]],
    covered: set[str],
) -> list[dict[str, str]]:
    return [section for section in sections if section["id"] not in covered]


def _course_documents(root: Path) -> bool:
    listed = list_course_documents(root)
    documents = listed.get("documents")
    return isinstance(documents, list) and len(documents) > 0


def _known_source_file(root: Path, state: dict[str, object]) -> str | None:
    local = state.get("local_sources")
    if not isinstance(local, dict) or local.get("status") != "AVAILABLE" or local.get("source_count") not in {0, None}:
        return None
    document = load_project_toml(root)
    course = document.get("course")
    if not isinstance(course, dict):
        return None
    label = course.get("local_sources")
    if not isinstance(label, str) or not label.strip() or ".." in Path(label).parts:
        return None
    raw = Path(label.strip())
    candidates = [raw] if raw.is_absolute() else [root / raw, Path.cwd() / raw]
    for candidate in candidates:
        try:
            if candidate.is_file() and not candidate.is_symlink():
                return str(candidate)
        except OSError:
            continue
    return None


def _profile(root: Path) -> str:
    document = load_project_toml(root)
    course = document.get("course")
    if isinstance(course, dict) and isinstance(course.get("domain_profile"), str):
        return str(course["domain_profile"])
    return "GENERAL"


def _draft_is_current(root: Path) -> bool:
    tex = root / "latex" / "draft.tex"
    try:
        if not tex.is_file():
            return False
        tex_mtime = tex.stat().st_mtime
    except OSError:
        return False
    for relative in _DRAFT_INPUTS:
        path = root / relative
        try:
            if path.is_file() and path.stat().st_mtime > tex_mtime:
                return False
        except OSError:
            return False
    return True


def _arguments(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _study_sections(root: Path) -> list[dict[str, str]]:
    name = "Topic"
    document = load_project_toml(root)
    course = document.get("course")
    if isinstance(course, dict) and isinstance(course.get("name"), str) and course["name"].strip():
        name = course["name"].strip()
    return [
        {"id": "roadmap", "title": "Roadmap"},
        {"id": "foundations", "title": "Foundations"},
        {"id": "topic", "title": name},
        {"id": "topic-2", "title": f"{name}, continued"},
        {"id": "worked-problems", "title": "Worked problems"},
        {"id": "self-check", "title": "Self-check"},
        {"id": "formula-sheet", "title": "Formula or concept sheet"},
        {"id": "source-audit", "title": "Source audit"},
    ]


def _outline_gate(
    state: dict[str, object],
    root: Path,
    sections: list[dict[str, str]],
) -> dict[str, object] | None:
    """The first failure that blocks writing and render: outline, then sources."""

    if len(sections) < _MIN_SECTIONS:
        if book_kind(root) == BOOK_TOPIC or not _course_documents(root):
            return _step(state, "studium_blueprint_store", {"sections": _study_sections(root)}, _TOO_SHORT)
        return _step(
            state,
            "studium_blueprint_store",
            {},
            f"{_TOO_SHORT} Chapters follow the stored course guide.",
        )
    if _usable_source_count(root) < _MIN_SOURCES:
        return _step(state, "studium_public_source_record", {}, _NEED_SOURCES)
    return None


def _chapter_gate(
    state: dict[str, object],
    root: Path,
    sections: list[dict[str, str]],
) -> dict[str, object] | None:
    """Rust misuse, then two explanation sections, then the rest of the chapter."""

    rust = _foreign_rust(root)
    if rust is not None:
        identifier = rust.get("id") if isinstance(rust.get("id"), str) else ""
        return _step(
            state,
            "studium_problem_remove",
            {"id": identifier},
            _RUST_REMOVE,
            blocked=blocked_sections(root),
        )
    for section in sections:
        if not _is_written(root, section["id"]):
            continue
        if _explanation_count(root, section["id"]) < _MIN_EXPLANATION_SECTIONS:
            return _explanation_step(state, root, section, two_sections=True)
    for section in sections:
        if not _is_written(root, section["id"]):
            continue
        if _explanation_words(root, section["id"]) < _MIN_EXPLANATION_WORDS:
            return _explanation_step(state, root, section)
    for section in sections:
        if not _is_written(root, section["id"]):
            continue
        if _explanation_words(root, section["id"]) < _MIN_EXPLANATION_WORDS:
            continue
        shown = _arithmetic_resolution(root, section["id"])
        if shown is None:
            continue
        return _step(
            state,
            "studium_problem_record",
            {"section": section["id"]},
            (
                f"The worked problem for {section['id']} ({section['title']}) is only an arithmetic expression "
                f"({shown}). Record a resolution with enunciado, resolución, and respuesta. "
                "An arithmetic expression is not that resolution."
            ),
            blocked=blocked_sections(root),
        )
    for section in sections:
        if not _is_written(root, section["id"]):
            continue
        if _explanation_words(root, section["id"]) < _MIN_EXPLANATION_WORDS or _explanation_count(root, section["id"]) < _MIN_EXPLANATION_SECTIONS:
            continue
        gap = _shape_gap(state, root, section)
        if gap is not None:
            return gap
    return None


def _explanation_step(
    state: dict[str, object],
    root: Path,
    section: dict[str, str],
    *,
    two_sections: bool = False,
) -> dict[str, object]:
    excerpt_id = _excerpt_for_section(root, section["id"])
    if excerpt_id is None:
        return _step(state, "studium_public_source_record", {}, _NEED_SOURCES)
    if two_sections:
        reason = (
            f"Write another explanation section for {section['id']} ({section['title']}). "
            + _TWO_SECTIONS
            + " "
            + _CHAPTER
        )
    else:
        reason = (
            f"Write the explanation for {section['id']} ({section['title']}) as body text. "
            "This chapter is too short. It needs at least 400 words of explanation. "
            "Search open sources before writing. Cite a stored excerpt. "
            + _CHAPTER
        )
    return _step(
        state,
        "studium_paragraph_record",
        {"section": section["id"], "excerpts": [excerpt_id], "role": "explanation"},
        reason,
        blocked=blocked_sections(root),
    )


def _shape_gap(
    state: dict[str, object],
    root: Path,
    section: dict[str, str],
) -> dict[str, object] | None:
    if not _has_role(root, section["id"], "purpose"):
        return _role_step(state, root, section, "purpose", f"Write the lead for {section['id']} ({section['title']}). {_TWO_SECTIONS}")
    if not _has_role(root, section["id"], "consejo"):
        return _role_step(state, root, section, "consejo", f"Add one consejo for {section['id']} ({section['title']}). {_TWO_SECTIONS}")
    if _profile(root) != "COMPUTER_SCIENCE" and not _worked_ok(root, section["id"]):
        return _step(
            state,
            "studium_computation_check",
            {"section": section["id"]},
            (
                f"Record a worked problem for {section['id']} ({section['title']}): "
                "a replayed computation or a numeric result cited from two excerpts. "
                + _RUST_PROBLEM
            ),
            blocked=blocked_sections(root),
        )
    if not _has_autoficha(root, section["id"]):
        return _role_step(
            state,
            root,
            section,
            "self_check",
            (
                f"Add one autoficha for {section['id']} ({section['title']}). "
                "The explanation above must still teach from the excerpts. "
                + _CHAPTER
            ),
        )
    return None


def _role_step(
    state: dict[str, object],
    root: Path,
    section: dict[str, str],
    role: str,
    reason: str,
) -> dict[str, object]:
    excerpt_id = _excerpt_for_section(root, section["id"])
    if excerpt_id is None:
        return _step(state, "studium_public_source_record", {}, _NEED_SOURCES)
    return _step(
        state,
        "studium_paragraph_record",
        {"section": section["id"], "excerpts": [excerpt_id], "role": role},
        reason,
        blocked=blocked_sections(root),
    )


def _is_written(root: Path, section_id: str) -> bool:
    return any(record.get("section") == section_id for record in supported_paragraphs(root))


def _explanation_count(root: Path, section_id: str) -> int:
    return len(_explanation_paragraphs(root, section_id))


def _explanation_paragraphs(root: Path, section_id: str) -> list[dict[str, object]]:
    found: list[dict[str, object]] = []
    for record in supported_paragraphs(root):
        if record.get("section") != section_id or record.get("role") in _BODY_SKIP:
            continue
        text = record.get("text") if isinstance(record.get("text"), str) else ""
        if text.strip():
            found.append(record)
    return found


def _explanation_words(root: Path, section_id: str) -> int:
    total = 0
    for record in supported_paragraphs(root):
        if record.get("section") != section_id or record.get("role") in _BODY_SKIP:
            continue
        text = record.get("text") if isinstance(record.get("text"), str) else ""
        total += len(text.split())
    return total


def _excerpt_for_section(root: Path, section_id: str) -> str | None:
    for record in supported_paragraphs(root):
        if record.get("section") != section_id:
            continue
        excerpt_id = _excerpt_on(record)
        if excerpt_id is not None:
            return excerpt_id
    usable = _all_usable_excerpts(root)
    if not usable:
        return None
    return usable[0][0]


def _arithmetic_resolution(root: Path, section_id: str) -> str | None:
    texts = _resolution_texts(root, section_id)
    if not texts or any(not _arithmetic_only(text) for text in texts):
        return None
    return texts[0]


def _resolution_texts(root: Path, section_id: str) -> list[str]:
    found: list[str] = []
    for record in fold_by_id(root / PROBLEMS):
        if record.get("section") != section_id:
            continue
        source = record.get("source_text") if isinstance(record.get("source_text"), str) else ""
        prompt = record.get("prompt") if isinstance(record.get("prompt"), str) else ""
        text = source.strip() or prompt.strip()
        if text:
            found.append(text)
    for record in fold_by_id(root / COMPUTATIONS):
        if record.get("section") != section_id:
            continue
        expression = record.get("expression") if isinstance(record.get("expression"), str) else ""
        if expression.strip():
            found.append(expression.strip())
    return found


def _arithmetic_only(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    if not compact or not any(operator in compact for operator in "+-*/×÷·"):
        return False
    return _ARITHMETIC.fullmatch(compact) is not None


def _usable_source_count(root: Path) -> int:
    found: set[str] = set()
    for record in _public_records(root):
        identifier = record.get("id")
        if isinstance(identifier, str) and _source_counts(record):
            found.add("public:" + identifier)
    for record in fold_by_id(root / _LOCAL_REGISTRY):
        identifier = record.get("id")
        if isinstance(identifier, str) and _source_counts(record):
            found.add("local:" + identifier)
    return len(found)


def _source_counts(record: dict[str, object]) -> bool:
    for key in ("kind", "probable_kind"):
        kind = record.get(key)
        if isinstance(kind, str) and kind.strip().lower() in _PIRATE_KINDS:
            return False
    if license_forbids_use(record.get("license_forbids")) or license_forbids_use(record.get("rights_status")):
        return False
    if record.get("rejection_reason"):
        return False
    classification = record.get("classification")
    if isinstance(classification, str) and classification.strip().lower() in {"rejected", "unauthorized"}:
        return False
    return True


def _foreign_rust(root: Path) -> dict[str, object] | None:
    if _profile(root) == "COMPUTER_SCIENCE":
        return None
    for record in fold_by_id(root / PROBLEMS):
        if record.get("kind") == "rust":
            return record
    return None


def _has_role(root: Path, section_id: str, role: str) -> bool:
    return any(record.get("section") == section_id and record.get("role") == role for record in supported_paragraphs(root))


def _worked_ok(root: Path, section_id: str) -> bool:
    if _profile(root) == "COMPUTER_SCIENCE":
        return any(
            record.get("section") == section_id and record.get("kind") == "rust"
            for record in fold_by_id(root / PROBLEMS)
        )
    if _arithmetic_resolution(root, section_id) is not None:
        return False
    for record in fold_by_id(root / COMPUTATIONS):
        if record.get("section") != section_id or record.get("status") != "replayed" or record.get("correct") is not True:
            continue
        expression = record.get("expression") if isinstance(record.get("expression"), str) else ""
        if expression.strip() and not _arithmetic_only(expression):
            return True
    for record in fold_by_id(root / PROBLEMS):
        if record.get("section") != section_id or record.get("kind") != "numeric":
            continue
        if record.get("corroboration") == "two_witnesses" or record.get("status") == "two_witnesses":
            return True
    return False


def _has_autoficha(root: Path, section_id: str) -> bool:
    for record in supported_paragraphs(root):
        if record.get("section") != section_id:
            continue
        if record.get("role") == "self_check":
            return True
        text = record.get("text") if isinstance(record.get("text"), str) else ""
        if text.strip().startswith("Autoficha"):
            return True
    return False


def _pending_length(
    root: Path,
    sections: list[dict[str, str]],
) -> tuple[str, dict[str, str], str, str | None] | None:
    blocked = blocked_ids(root)
    for section in sections:
        if section["id"] in blocked:
            continue
        paragraphs = [
            record
            for record in supported_paragraphs(root)
            if record.get("section") == section["id"] and record.get("role") != "self_check"
        ]
        if not paragraphs:
            continue
        excerpt_id = _excerpt_on(paragraphs[0])
        if excerpt_id is None:
            continue
        short_id = short_paragraph_id(root, section["id"])
        if short_id is not None and not offers_for(root, short_id, "rewrite"):
            remember_offer(root, section_id=short_id, kind="rewrite")
            return "replace", section, excerpt_id, short_id
        if section_needs_more_prose(root, section["id"]) and not offers_for(root, section["id"], "paragraph_more"):
            remember_offer(root, section_id=section["id"], kind="paragraph_more")
            return "more", section, excerpt_id, None
    return None


def _pending_self_check(
    root: Path,
    sections: list[dict[str, str]],
) -> tuple[dict[str, str], str] | None:
    blocked = blocked_ids(root)
    for section in sections:
        if section["id"] in blocked:
            continue
        paragraphs = [record for record in supported_paragraphs(root) if record.get("section") == section["id"]]
        if not paragraphs or any(record.get("role") == "self_check" for record in paragraphs):
            continue
        if offers_for(root, section["id"], "self_check"):
            continue
        excerpt_id = _excerpt_on(paragraphs[0])
        if excerpt_id is None:
            continue
        remember_offer(root, section_id=section["id"], kind="self_check")
        return section, excerpt_id
    return None


def _pending_audit(root: Path) -> str | None:
    covered = audited_paragraph_ids(root)
    gaps = explicit_gap_ids(root)
    for section in current_sections(root):
        if section["id"] in gaps:
            continue
        paragraphs = [record for record in supported_paragraphs(root) if record.get("section") == section["id"]]
        identifiers = [record.get("id") for record in paragraphs if isinstance(record.get("id"), str)]
        if not identifiers or all(identifier in covered for identifier in identifiers):
            continue
        if offers_for(root, section["id"], "audit"):
            continue
        remember_offer(root, section_id=section["id"], kind="audit")
        return section["id"]
    return None


def _excerpt_on(paragraph: dict[str, object]) -> str | None:
    excerpts = paragraph.get("excerpts")
    if not isinstance(excerpts, list):
        return None
    for excerpt_id in excerpts:
        if isinstance(excerpt_id, str) and excerpt_id.strip():
            return excerpt_id
    return None


def _step(
    state: dict[str, object],
    tool: str | None,
    arguments: dict[str, object],
    reason: str,
    blocked: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    if _ASK in reason.lower().replace(_FORMAT, ""):
        raise ValueError("book_next reason asked the user")
    local = state.get("local_sources")
    return {
        "status": "ok",
        "tool": tool,
        "arguments": arguments,
        "reason": reason,
        "ask_user": False,
        "released": state.get("state") == "RELEASED",
        "project_state": state.get("state"),
        "blocked_sections": [] if blocked is None else blocked,
        "local_sources": dict(local) if isinstance(local, dict) else {"status": "UNKNOWN", "prompted": False, "source_count": 0},
    }
