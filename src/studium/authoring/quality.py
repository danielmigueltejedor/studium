"""Deterministic chapter-quality assessment with labeled checks.

Every check is a small, auditable rule over stored records. Each section gets
a list of labeled assessments (``PASS``, ``WARN``, ``FAIL``) plus a chapter
label. The labels are claims about the stored material, never about the
subject matter itself.

Labels:
- ``teachable``  every check passes.
- ``adequate``   no check fails; at least one check is a warning.
- ``needs_work`` at least one check fails.
"""

from __future__ import annotations

from pathlib import Path

from studium.authoring.audit import audited_paragraph_ids, open_contradictions
from studium.authoring.blueprint import current_sections
from studium.authoring.excerpts import excerpts_by_id
from studium.authoring.paragraphs import supported_paragraphs

PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"

_MIN_WORDS = 25
_MIN_SENTENCES = 2
_MIN_TEACHING_PARAGRAPHS = 2
_BODY_SKIP = frozenset({"self_check", "consejo"})


def assess_book(root: Path) -> list[dict[str, object]]:
    """Labeled assessments for every blueprint section."""

    assessments: list[dict[str, object]] = []
    for section in current_sections(root):
        assessment = assess_section(root, section["id"])
        if assessment is not None:
            assessments.append(assessment)
    return assessments


def assess_section(root: Path, section_id: str) -> dict[str, object] | None:
    """One labeled assessment for one section, or ``None`` when unknown."""

    sections = {section["id"] for section in current_sections(root)}
    if section_id not in sections:
        return None
    checks = _checks(root, section_id)
    levels = [str(check["label"]) for check in checks]
    if FAIL in levels:
        label = "needs_work"
    elif WARN in levels:
        label = "adequate"
    else:
        label = "teachable"
    return {
        "section": section_id,
        "label": label,
        "checks": checks,
        "passes": levels.count(PASS),
        "warnings": levels.count(WARN),
        "failures": levels.count(FAIL),
    }


def _checks(root: Path, section_id: str) -> list[dict[str, object]]:
    paragraphs = _section_paragraphs(root, section_id)
    teaching = [record for record in paragraphs if record.get("role") != "self_check"]
    audited = set(audited_paragraph_ids(root)) if teaching else set()

    def check(name: str, ok: bool, description: str, warn: bool = False) -> dict[str, object]:
        label = WARN if (warn and not ok) else (PASS if ok else FAIL)
        return {"check": name, "label": label, "description": description}

    return [
        check("lead", _has_role(paragraphs, "purpose"), "the section starts with a lead"),
        check("tip", _has_role(paragraphs, "consejo"), "the section has one advice box"),
        check(
            "coverage",
            len(teaching) >= _MIN_TEACHING_PARAGRAPHS,
            f"at least {_MIN_TEACHING_PARAGRAPHS} teaching paragraphs",
        ),
        check(
            "depth",
            bool(teaching) and all(_has_depth(paragraph) for paragraph in teaching),
            "every teaching paragraph has substance",
        ),
        check(
            "explanation_sections",
            _explanation_count(root, section_id) >= 2,
            "two explanation sections or more",
        ),
        check(
            "explanation_words",
            _explanation_words(root, section_id) >= 400,
            "400 words of explanation",
        ),
        check(
            "worked_problem",
            _worked_ok(root, section_id),
            "the section has a replayed or verified worked problem",
        ),
        check("self_check", _has_role(paragraphs, "self_check"), "the section has a self-check"),
        check(
            "citation_shadow",
            all(_cites(paragraph) for paragraph in paragraphs),
            "every paragraph cites an excerpt",
        ),
        check(
            "audit_coverage",
            all(identifier in audited for identifier in _identifiers(teaching)),
            "every teaching paragraph has a current audit",
        ),
        check(
            "source_diversity",
            _distinct_sources(root, paragraphs) >= 2,
            "the section cites at least two distinct sources",
            warn=True,
        ),
        check(
            "no_open_contradiction",
            not _contradicts_section(root, paragraphs),
            "no open contradiction involves this section",
        ),
    ]


def _section_paragraphs(root: Path, section_id: str) -> list[dict[str, object]]:
    return [record for record in supported_paragraphs(root) if record.get("section") == section_id]


def _identifiers(paragraphs: list[dict[str, object]]) -> list[str]:
    return [
        identifier
        for paragraph in paragraphs
        if isinstance((identifier := paragraph.get("id")), str)
    ]


def _has_role(paragraphs: list[dict[str, object]], role: str) -> bool:
    return any(paragraph.get("role") == role for paragraph in paragraphs)


def _has_depth(paragraph: dict[str, object]) -> bool:
    text = paragraph.get("text")
    if not isinstance(text, str):
        return False
    if len(text.split()) < _MIN_WORDS:
        return False
    sentences = [part.strip() for part in text.replace("?", ".").replace("!", ".").split(".") if part.strip()]
    return len(sentences) >= _MIN_SENTENCES


def _cites(paragraph: dict[str, object]) -> bool:
    excerpts = paragraph.get("excerpts")
    return isinstance(excerpts, list) and any(isinstance(item, str) and item.strip() for item in excerpts)


def _distinct_sources(root: Path, paragraphs: list[dict[str, object]]) -> int:
    excerpts = excerpts_by_id(root)
    source_ids: set[str] = set()
    for paragraph in paragraphs:
        raw = paragraph.get("excerpts")
        if not isinstance(raw, list):
            continue
        for excerpt_id in raw:
            if not isinstance(excerpt_id, str):
                continue
            excerpt = excerpts.get(excerpt_id)
            source_id = excerpt.get("source_id") if isinstance(excerpt, dict) else None
            if isinstance(source_id, str):
                source_ids.add(source_id)
    return len(source_ids)


def _contradicts_section(root: Path, paragraphs: list[dict[str, object]]) -> bool:
    passage_ids: set[str] = set()
    for record in open_contradictions(root):
        listed = record.get("passages")
        if isinstance(listed, list):
            passage_ids.update(passage for passage in listed if isinstance(passage, str))
    if not passage_ids:
        return False
    section_ids = set(_identifiers(paragraphs))
    return bool(passage_ids & section_ids)


def _explanation_count(root: Path, section_id: str) -> int:
    return len(_explanation_paragraphs(root, section_id))


def _explanation_paragraphs(root: Path, section_id: str) -> list[dict[str, object]]:
    found: list[dict[str, object]] = []
    for record in supported_paragraphs(root):
        if record.get("section") != section_id or record.get("role") in _BODY_SKIP:
            continue
        text = record.get("text")
        if isinstance(text, str) and text.strip():
            found.append(record)
    return found


def _explanation_words(root: Path, section_id: str) -> int:
    total = 0
    for record in supported_paragraphs(root):
        if record.get("section") != section_id or record.get("role") in _BODY_SKIP:
            continue
        text = record.get("text")
        if isinstance(text, str):
            total += len(text.split())
    return total


def _worked_ok(root: Path, section_id: str) -> bool:
    """A worked numerical problem exists: replayed, witnessed, or verified."""

    from studium.authoring.book_next import _worked_ok as contract_worked

    try:
        return bool(contract_worked(root, section_id))
    except Exception:
        return False


def chapter_quality(root: Path, section_id: str) -> dict[str, object]:
    """The MCP-facing quality tool body for one section."""

    assessment = assess_section(root, section_id)
    if assessment is None:
        return {"status": "section_unknown", "section": section_id}
    return {"status": "ok", "assessment": assessment}
