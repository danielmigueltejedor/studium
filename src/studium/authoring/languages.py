"""Project language: a missing field stays Spanish. An invalid field does not."""

from pathlib import Path

from studium.domain.languages import (
    INVALID_LANGUAGE,
    SPANISH_CHAPTER,
    SPANISH_TWO_SECTIONS,
    BookLanguage,
    canonical_language,
    chapter_contract,
    describe,
    generic_section_titles,
    is_spanish_book,
    is_spanish_tag,
    messages,
    resolution_labels,
    self_check_word,
    status_line,
    tip_word,
    two_sections_line,
    writing_name,
)
from studium.storage.init_project import load_project_toml

__all__ = [
    "INVALID_LANGUAGE",
    "SPANISH_CHAPTER",
    "SPANISH_TWO_SECTIONS",
    "BookLanguage",
    "active_language",
    "book_language",
    "canonical_language",
    "chapter_contract",
    "describe",
    "generic_section_titles",
    "is_spanish_book",
    "is_spanish_tag",
    "messages",
    "resolution_labels",
    "self_check_word",
    "status_line",
    "tip_word",
    "two_sections_line",
    "writing_name",
]


def book_language(root: Path) -> BookLanguage | None:
    """Language of a project. A missing field stays Spanish. An invalid field is None."""

    course = load_project_toml(root).get("course")
    raw = course.get("language") if isinstance(course, dict) else None
    if not isinstance(raw, str) or not raw.strip():
        legacy = describe("es", legacy=True)
        assert legacy is not None
        return legacy
    return describe(raw)


def active_language(root: Path) -> BookLanguage:
    """Language for authoring guidance. An invalid stored code uses English chrome."""

    found = book_language(root)
    if found is not None:
        return found
    english = describe("en")
    assert english is not None
    return english
