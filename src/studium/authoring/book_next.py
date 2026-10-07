"""The next tool call for one open draft.

The client searches open sources and writes the draft. This does not ask the
user when that step can be done from open sources or from sources already
given, and it does not release the book.
"""

from pathlib import Path

from studium.authoring.blueprint import current_sections
from studium.authoring.computation import list_computations
from studium.authoring.excerpts import excerpts_by_id
from studium.authoring.paragraphs import supported_paragraphs, supported_section_ids
from studium.authoring.section_blocks import blocked_ids, blocked_sections, mark_blocked, offers_for, remember_offer
from studium.authoring.support import draft_source_usable
from studium.domain.profiles import BOOK_TOPIC
from studium.research.course_documents import list_course_documents
from studium.storage.init_project import book_kind, load_project_toml, load_state
from studium.storage.records import (
    BLUEPRINT,
    CLAIMS,
    COMPUTATIONS,
    EXCERPTS,
    PARAGRAPHS,
    PROBLEMS,
    PUBLIC_BIBLIOGRAPHY,
    SECTION_BLOCKS,
    SECTION_OFFERS,
    fold_by_id,
)

_ASK = "ask the user"
_CODE_OR_CALCULATION = frozenset({"COMPUTER_SCIENCE", "STEM"})
_DRAFT_INPUTS = (
    PARAGRAPHS,
    PROBLEMS,
    COMPUTATIONS,
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
        return _step(
            state,
            "studium_blueprint_store",
            {},
            "Store the section ids and titles. Do not invent a citation.",
        )
    pending = _pending_paragraph(root, sections)
    if pending is not None:
        section, excerpt_id = pending
        return _step(
            state,
            "studium_paragraph_record",
            {"section": section["id"], "excerpts": [excerpt_id]},
            (
                f"Write the missing section paragraph for {section['id']} ({section['title']}) "
                "from the stored excerpt."
            ),
        )
    problem = _pending_problem(root, sections)
    if problem is not None:
        return _step(state, str(problem["tool"]), _arguments(problem.get("arguments")), str(problem["reason"]))
    if not _draft_is_current(root):
        return _render_step(state, root, sections)
    return _step(state, None, {}, "The DRAFT is rendered. Do not request release.")


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
                "reason": "Run studium_problem_check. A Rust test is checked only after three passing runs.",
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


def _step(
    state: dict[str, object],
    tool: str | None,
    arguments: dict[str, object],
    reason: str,
    blocked: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    if _ASK in reason.lower():
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
