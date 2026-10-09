"""Notation and terminology registries.

One symbol keeps one meaning across the whole book. A term is defined once
and the same definition is reused. Conflicts are reported deterministically;
they are never silently merged.
"""

from __future__ import annotations

from pathlib import Path

from studium.authoring.blueprint import current_sections
from studium.policy.trust import contains_directive
from studium.storage.init_project import load_state_holding_lock
from studium.storage.locking import ProjectLocked, project_lock
from studium.storage.migrate import utc_now
from studium.storage.records import NOTATION, TERMINOLOGY, allocate_id, append_jsonl, fold_by_id

_MAX_SYMBOL = 40
_MAX_LINE = 500


def record_notation(
    root: Path,
    *,
    section: object,
    symbol: object,
    meaning: object,
    units: object = None,
) -> dict[str, object]:
    """Register one symbol with one meaning. Does not change project state."""

    section_id, section_error = _section(root, section)
    if section_error is not None:
        return section_error
    cleaned_symbol, symbol_error = _symbol(symbol)
    if symbol_error is not None:
        return symbol_error
    cleaned_meaning, meaning_error = _line(meaning, "meaning")
    if meaning_error is not None:
        return meaning_error
    cleaned_units, units_error = _line(units, "units") if units is not None else (None, None)
    if units_error is not None:
        return units_error
    if contains_directive(f"{cleaned_symbol} {cleaned_meaning}".encode()):
        return {"status": "policy.directive", "message": "the notation changed or requested policy"}
    assert section_id is not None and cleaned_symbol is not None and cleaned_meaning is not None
    try:
        with project_lock(root):
            rows = fold_by_id(root / NOTATION)
            for row in rows:
                if row.get("symbol") == cleaned_symbol and row.get("meaning") != cleaned_meaning:
                    return {
                        "status": "notation.conflict",
                        "message": "the same symbol already carries a different meaning in this book",
                        "existing": {"section": row.get("section"), "meaning": row.get("meaning")},
                    }
            for row in rows:
                if (
                    row.get("symbol") == cleaned_symbol
                    and row.get("meaning") == cleaned_meaning
                    and row.get("section") == section_id
                ):
                    return {"status": "already_recorded", "entry": _public(row)}
            record: dict[str, object] = {
                "schema_version": "1.0.0",
                "id": allocate_id(root, "SYM"),
                "section": section_id,
                "symbol": cleaned_symbol,
                "meaning": cleaned_meaning,
                "recorded_at": utc_now(),
            }
            if cleaned_units is not None:
                record["units"] = cleaned_units
            append_jsonl(root / NOTATION, record)
            fresh = load_state_holding_lock(root)
    except ProjectLocked:
        return {"status": "storage.locked", "message": "project is locked"}
    return {
        "status": "recorded",
        "entry": _public(record),
        "project_state": fresh.get("state"),
        "released": fresh.get("state") == "RELEASED",
    }


def record_terminology(
    root: Path,
    *,
    section: object,
    term: object,
    definition: object,
) -> dict[str, object]:
    """Register one term with its definition. Does not change project state."""

    section_id, section_error = _section(root, section)
    if section_error is not None:
        return section_error
    cleaned_term, term_error = _line(term, "term")
    if term_error is not None:
        return term_error
    cleaned_definition, definition_error = _line(definition, "definition")
    if definition_error is not None:
        return definition_error
    assert section_id is not None and cleaned_term is not None and cleaned_definition is not None
    if contains_directive(f"{cleaned_term} {cleaned_definition}".encode()):
        return {"status": "policy.directive", "message": "the definition changed or requested policy"}
    try:
        with project_lock(root):
            rows = fold_by_id(root / TERMINOLOGY)
            for row in rows:
                if row.get("term") == cleaned_term and row.get("definition") != cleaned_definition:
                    return {
                        "status": "terminology.conflict",
                        "message": "the same term already carries a different definition in this book",
                        "existing": {"section": row.get("section"), "definition": row.get("definition")},
                    }
            for row in rows:
                if row.get("term") == cleaned_term and row.get("section") == section_id:
                    return {"status": "already_recorded", "entry": _public(row)}
            record: dict[str, object] = {
                "schema_version": "1.0.0",
                "id": allocate_id(root, "TRM"),
                "section": section_id,
                "term": cleaned_term,
                "definition": cleaned_definition,
                "recorded_at": utc_now(),
            }
            append_jsonl(root / TERMINOLOGY, record)
            fresh = load_state_holding_lock(root)
    except ProjectLocked:
        return {"status": "storage.locked", "message": "project is locked"}
    return {
        "status": "recorded",
        "entry": _public(record),
        "project_state": fresh.get("state"),
        "released": fresh.get("state") == "RELEASED",
    }


def notation_registry(root: Path) -> dict[str, dict[str, object]]:
    """symbol -> canonical entry (the first recorded meaning wins in output)."""

    registry: dict[str, dict[str, object]] = {}
    for row in fold_by_id(root / NOTATION):
        symbol = row.get("symbol")
        if isinstance(symbol, str) and symbol not in registry:
            registry[symbol] = _public(row)
    return registry


def list_notation(root: Path) -> dict[str, object]:
    return {"status": "ok", "entries": [_public(row) for row in fold_by_id(root / NOTATION)]}


def list_terminology(root: Path) -> dict[str, object]:
    return {"status": "ok", "entries": [_public(row) for row in fold_by_id(root / TERMINOLOGY)]}


def notation_conflicts(root: Path) -> list[dict[str, object]]:
    """Symbols that carry more than one meaning anywhere in the book."""

    meanings: dict[str, list[dict[str, object]]] = {}
    for row in fold_by_id(root / NOTATION):
        symbol = row.get("symbol")
        if isinstance(symbol, str):
            meanings.setdefault(symbol, []).append(row)
    conflicts: list[dict[str, object]] = []
    for symbol, rows in sorted(meanings.items()):
        distinct = {str(row.get("meaning")) for row in rows}
        if len(distinct) > 1:
            conflicts.append(
                {
                    "symbol": symbol,
                    "meanings": [{"section": row.get("section"), "meaning": row.get("meaning")} for row in rows],
                }
            )
    return conflicts


def terminology_conflicts(root: Path) -> list[dict[str, object]]:
    definitions: dict[str, list[dict[str, object]]] = {}
    for row in fold_by_id(root / TERMINOLOGY):
        term = row.get("term")
        if isinstance(term, str):
            definitions.setdefault(term, []).append(row)
    conflicts: list[dict[str, object]] = []
    for term, rows in sorted(definitions.items()):
        distinct = {str(row.get("definition")) for row in rows}
        if len(distinct) > 1:
            conflicts.append(
                {
                    "term": term,
                    "definitions": [{"section": row.get("section"), "definition": row.get("definition")} for row in rows],
                }
            )
    return conflicts


def _public(record: dict[str, object]) -> dict[str, object]:
    visible: dict[str, object] = {
        "id": record.get("id"),
        "section": record.get("section"),
    }
    for key in ("symbol", "meaning", "units", "term", "definition"):
        if record.get(key) is not None:
            visible[key] = record.get(key)
    return visible


def _section(root: Path, value: object) -> tuple[str | None, dict[str, object] | None]:
    if not isinstance(value, str) or not value.strip():
        return None, {"status": "mcp.invalid_input", "message": "section must be a blueprint section id"}
    identifier = value.strip()
    known = {section["id"] for section in current_sections(root)}
    if identifier not in known:
        return None, {"status": "notation.section_unknown", "message": "section is not in the stored blueprint"}
    return identifier, None


def _symbol(value: object) -> tuple[str | None, dict[str, object] | None]:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > _MAX_SYMBOL:
        return None, {"status": "mcp.invalid_input", "message": "symbol is required and must be short"}
    return value.strip(), None


def _line(value: object, field: str) -> tuple[str | None, dict[str, object] | None]:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > _MAX_LINE:
        return None, {"status": "mcp.invalid_input", "message": f"{field} is required and must be short"}
    if "\n" in value or "\r" in value:
        return None, {"status": "mcp.invalid_input", "message": f"{field} must be one line"}
    return value.strip(), None
