"""Deterministic contradiction scanning across accepted passages.

A structured disagreement about a numeric value, definition, or term is
recorded as an open contradiction. ``CONFIRMED_CONTRADICTION`` and
``POSSIBLE_CONTRADICTION`` block review. Measurements taken under different
stated conditions are ``CONTEXT_DEPENDENT``, not automatically contradictory.
"""

import hashlib
import re
from fractions import Fraction
from pathlib import Path

from studium.authoring.blueprint import current_sections
from studium.authoring.computation import computation_fingerprint
from studium.authoring.excerpts import excerpts_by_id
from studium.authoring.paragraphs import supported_paragraphs
from studium.authoring.problems import problem_input_sha256, problem_result_current
from studium.authoring.support import supported_drafts
from studium.storage.init_project import load_state_holding_lock
from studium.storage.locking import ProjectLocked, project_lock
from studium.storage.migrate import utc_now
from studium.storage.records import (
    AUDITS,
    COMPUTATIONS,
    CONTRADICTIONS,
    FIGURES,
    PROBLEMS,
    PUBLIC_BIBLIOGRAPHY,
    REVIEWS,
    allocate_id,
    append_jsonl,
    fold_by_id,
)

_QUANTITY = re.compile(
    r"\b([A-Za-z][A-Za-z0-9_-]{1,40})\s*(?:=|is|equals)\s*(-?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)


def _finding_strings(finding: dict[str, object], key: str) -> list[str]:
    value = finding.get(key)
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def contradiction_scan(root: Path) -> dict[str, object]:
    """Compare accepted passages. A structured disagreement is an open contradiction.

    Deterministic categories: numeric values with or without a stated condition,
    units, definitions, and terminology. ``CONFIRMED_CONTRADICTION`` and
    ``POSSIBLE_CONTRADICTION`` block review. Measurements taken under different
    stated conditions are ``CONTEXT_DEPENDENT``, not automatically contradictory.
    """

    findings = _academic_findings(root)
    try:
        with project_lock(root):
            open_items: list[dict[str, object]] = []
            for finding in sorted(findings, key=lambda item: (item["quantity"], item["category"])):
                existing = _contradiction_for(root, str(finding["quantity"]))
                blocking = str(finding["verdict"]) in _BLOCKING_VERDICTS
                if blocking:
                    recorded = {
                        "schema_version": "1.0.0",
                        "id": existing["id"] if existing is not None else allocate_id(root, "CON"),
                        "quantity": finding["quantity"],
                        "values": finding["values"],
                        "passages": _finding_strings(finding, "passages"),
                        "status": "open",
                        "verdict": finding["verdict"],
                        "category": finding["category"],
                        "detail": finding["detail"],
                        "sources": _finding_strings(finding, "sources"),
                        "cross_chapter": finding["cross_chapter"],
                        "recorded_at": utc_now(),
                    }
                    append_jsonl(root / CONTRADICTIONS, recorded)
                    open_items.append(_public_contradiction(recorded))
                else:
                    if existing is not None and existing.get("status") == "open":
                        resolved = dict(existing)
                        resolved["status"] = "resolved"
                        resolved["verdict"] = finding["verdict"]
                        resolved["detail"] = finding["detail"]
                        resolved["recorded_at"] = utc_now()
                        append_jsonl(root / CONTRADICTIONS, resolved)
                    recorded = {
                        "schema_version": "1.0.0",
                        "id": allocate_id(root, "CON"),
                        "quantity": finding["quantity"],
                        "values": finding["values"],
                        "passages": _finding_strings(finding, "passages"),
                        "status": "not_open",
                        "verdict": finding["verdict"],
                        "category": finding["category"],
                        "detail": finding["detail"],
                        "sources": _finding_strings(finding, "sources"),
                        "cross_chapter": finding["cross_chapter"],
                        "recorded_at": utc_now(),
                    }
                    append_jsonl(root / CONTRADICTIONS, recorded)
            marker: dict[str, object] = {
                "schema_version": "1.0.0",
                "id": "scan",
                "edition": writer_edition(root),
                "status": "scanned",
                "recorded_at": utc_now(),
            }
            append_jsonl(root / CONTRADICTIONS, marker)
            fresh = load_state_holding_lock(root)
    except ProjectLocked:
        return _error("storage.locked", "project is locked")
    return {
        "status": "ok",
        "contradictions": open_items,
        "open_count": len(open_items),
        "released": fresh.get("state") == "RELEASED",
        "project_state": fresh.get("state"),
        "local_sources": _local(fresh),
        "applied": False,
    }


def open_contradictions(root: Path) -> list[dict[str, object]]:
    return [
        _public_contradiction(record)
        for record in fold_by_id(root / CONTRADICTIONS)
        if record.get("status") == "open" and isinstance(record.get("quantity"), str)
    ]


def writer_edition(root: Path) -> str:
    return _digest(_writer_material(root))


def review_edition(root: Path) -> str:
    material = _writer_material(root)
    for item in open_contradictions(root):
        material.append(f"contradiction:{item.get('quantity')}:{item.get('values')}")
    return _digest(material)


def scan_is_current(root: Path) -> bool:
    marker = next((item for item in fold_by_id(root / CONTRADICTIONS) if item.get("id") == "scan"), None)
    return isinstance(marker, dict) and marker.get("edition") == writer_edition(root)


def review_is_current(root: Path) -> bool:
    marker = next((item for item in fold_by_id(root / REVIEWS) if item.get("id") == "edition"), None)
    return isinstance(marker, dict) and marker.get("edition") == review_edition(root)


def _writer_material(root: Path) -> list[str]:
    lines = [f"section:{section['id']}" for section in current_sections(root)]
    for record in supported_paragraphs(root):
        lines.append(f"paragraph:{record.get('id')}:{record.get('text_sha256')}")
    for record in excerpts_by_id(root).values():
        lines.append(f"excerpt:{record.get('id')}:{record.get('text_sha256')}")
    for record in supported_drafts(root):
        lines.append(f"claim:{record.get('id')}:{record.get('text')}")
    seen_sources: set[str] = set()
    for record in excerpts_by_id(root).values():
        source_id = record.get("source_id")
        if isinstance(source_id, str) and source_id not in seen_sources:
            seen_sources.add(source_id)
            lines.append(f"source:{source_id}:{_source_fingerprint(root, source_id)}")
    for record in fold_by_id(root / PROBLEMS):
        lines.append(
            f"problem:{record.get('id')}:{record.get('status')}:{record.get('correct')}:"
            f"{problem_input_sha256(root, record)}:{problem_result_current(root, record)}"
        )
    for record in fold_by_id(root / COMPUTATIONS):
        lines.append(
            f"computation:{record.get('id')}:{record.get('status')}:{record.get('server_result')}:"
            f"{record.get('expression')}:{computation_fingerprint(record)}"
        )
    for record in fold_by_id(root / FIGURES):
        lines.append(f"figure:{record.get('id')}:{record.get('status')}:{record.get('correct')}")
    for record in fold_by_id(root / AUDITS):
        if record.get("status") != "recorded":
            continue
        lines.append(f"audit:{record.get('id')}:{record.get('target')}:{record.get('evidence')}")
    return lines


def _digest(lines: list[str]) -> str:
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()[:16]


def _accepted_passages(root: Path) -> list[tuple[str, str]]:
    passages: list[tuple[str, str]] = []
    for record in supported_paragraphs(root):
        identifier = record.get("id")
        text = record.get("text")
        if isinstance(identifier, str) and isinstance(text, str):
            passages.append((identifier, text))
    for record in supported_drafts(root):
        identifier = record.get("id")
        text = record.get("text")
        if isinstance(identifier, str) and isinstance(text, str):
            passages.append((identifier, text))
    return passages


def _quantities(text: str) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for match in _QUANTITY.finditer(text):
        name = match.group(1).lower()
        if name in {"the", "a", "an", "this", "that", "it", "is"}:
            continue
        found.append((name, _canon_number(match.group(2))))
    return found


def _canon_number(raw: str) -> str:
    """Canonical comparison form for a stored or quoted number.

    Plain digit strings keep the historic float normalisation (so ``2300`` and
    ``2300.0`` compare equal). A fraction string such as the canonical form of
    a computation result (``489519/5``) is parsed exactly and kept as the
    reduced fraction so that integer results still normalise and genuine
    fractions lose no precision.
    """

    if "/" in raw:
        try:
            number = Fraction(raw)
        except (ValueError, ZeroDivisionError, TypeError):
            return raw
        if number.denominator == 1:
            return str(number.numerator)
        return f"{number.numerator}/{number.denominator}"
    number = float(raw)
    if number == int(number):
        return str(int(number))
    return str(number)


_BLOCKING_VERDICTS = frozenset(
    {"CONFIRMED_CONTRADICTION", "POSSIBLE_CONTRADICTION"}
)


_VERDICT_CONTEXT = "CONTEXT_DEPENDENT"


_VERDICT_NONE = "NO_CONTRADICTION"


_VERDICT_INSUFFICIENT = "INSUFFICIENT_EVIDENCE"


_STOP_NAMES = frozenset(
    {"the", "a", "an", "this", "that", "it", "is", "are", "was", "were", "its", "their", "and", "or"}
)


_QUALIFIER_MARKERS = ("at ", "when ", "for ", "if ", "under ", "measured at ", "during ", "near ")


_CONDITION_UNITS = frozenset(
    {
        "kg/m3",
        "kg/m³",
        "g/cm3",
        "g/cm³",
        "kg/m^3",
        "g/cm^3",
        "m/s",
        "m/s2",
        "m/s²",
        "pa·s",
        "pa s",
        "mpa·s",
        "cP",
        "cp",
        "kpa",
        "mpa",
        "pa",
        "bar",
        "atm",
        "n/m2",
        "n/m²",
        "°c",
        "°f",
        "c",
        "f",
        "k",
        "kg",
        "g",
        "mg",
        "m",
        "cm",
        "mm",
        "km",
        "s",
        "min",
        "h",
        "n",
        "kn",
        "m3",
        "m³",
        "cm3",
        "cm³",
        "l",
        "ml",
    }
)


def _academic_findings(root: Path) -> list[dict[str, object]]:
    """Deterministic structured disagreements across accepted passages.

    Categories: ``numeric`` (values, conditions, units), ``definition``,
    ``terminology``. Every finding carries a verdict from the five-status
    vocabulary and the passages and sources behind it.
    """

    passages = sorted(_accepted_passages(root))
    findings: list[dict[str, object]] = []
    numeric: dict[str, dict[str, set[str]]] = {}
    qualifiers: dict[str, dict[str, set[str]]] = {}
    units: dict[str, dict[str, set[str]]] = {}
    for passage_id, text in passages:
        for name, value, qualifier, unit in _numeric_matches(text):
            numeric.setdefault(name, {}).setdefault(value, set()).add(passage_id)
            if qualifier:
                qualifiers.setdefault(name, {}).setdefault(qualifier, set()).add(passage_id)
            if unit:
                units.setdefault(name, {}).setdefault(unit, set()).add(passage_id)
    sections = _passage_sections(root)
    sources = _passage_sources(root)
    for name in sorted(numeric):
        values = numeric[name]
        if len(values) < 2:
            continue
        unit_groups = units.get(name, {})
        verdict: str
        category = "numeric"
        if len(unit_groups) >= 2:
            verdict = _VERDICT_CONTEXT
            detail = "the passages assign different values in different units; a unit conversion may reconcile them"
        else:
            qualifier_groups = qualifiers.get(name, {})
            if len(qualifier_groups) >= 2:
                verdict = _VERDICT_CONTEXT
                detail = "the passages give different values under different stated conditions"
            elif len(qualifier_groups) == 1:
                passage_ids = sorted({item for ids in values.values() for item in ids})
                single = next(iter(qualifier_groups.values()))
                if set(passage_ids) <= set(single):
                    verdict = "CONFIRMED_CONTRADICTION"
                    detail = "the passages give different values under the same stated condition"
                else:
                    verdict = "POSSIBLE_CONTRADICTION"
                    detail = "only one passage states a condition for its value"
            else:
                verdict = "CONFIRMED_CONTRADICTION"
                detail = "the passages assign different values to the same quantity"
        passage_ids = sorted({item for ids in values.values() for item in ids})
        findings.append(
            _finding(
                name,
                {value: sorted(ids) for value, ids in sorted(values.items())},
                passage_ids,
                category,
                verdict,
                detail,
                sections,
                sources,
            )
        )
    definitions: dict[str, dict[str, set[str]]] = {}
    for passage_id, text in passages:
        for subject, object_phrase in _definition_pairs(text):
            definitions.setdefault(subject, {}).setdefault(object_phrase, set()).add(passage_id)
    for subject in sorted(definitions):
        objects = definitions[subject]
        if len(objects) < 2:
            continue
        passage_ids = sorted({item for ids in objects.values() for item in ids})
        findings.append(
            _finding(
                subject,
                {term: sorted(ids) for term, ids in sorted(objects.items())},
                passage_ids,
                "definition",
                "CONFIRMED_CONTRADICTION",
                "the passages define the same term differently",
                sections,
                sources,
            )
        )
    terminology: dict[str, dict[str, set[str]]] = {}
    for passage_id, text in passages:
        for subject, term in _terminology_pairs(text):
            terminology.setdefault(subject, {}).setdefault(term, set()).add(passage_id)
    for subject in sorted(terminology):
        terms = terminology[subject]
        if len(terms) < 2:
            continue
        passage_ids = sorted({item for ids in terms.values() for item in ids})
        findings.append(
            _finding(
                subject,
                {term: sorted(ids) for term, ids in sorted(terms.items())},
                passage_ids,
                "terminology",
                "CONFIRMED_CONTRADICTION",
                "the passages call the same thing by different names",
                sections,
                sources,
            )
        )
    return findings


def _finding(
    name: str,
    values: dict[str, list[str]],
    passage_ids: list[str],
    category: str,
    verdict: str,
    detail: str,
    sections: dict[str, str],
    sources: dict[str, list[str]],
) -> dict[str, object]:
    cross_chapter = len({sections.get(passage_id, "") for passage_id in passage_ids if sections.get(passage_id)}) > 1
    source_ids = sorted({item for passage_id in passage_ids for item in sources.get(passage_id, [])})
    return {
        "quantity": name,
        "values": values,
        "passages": passage_ids,
        "category": category,
        "verdict": verdict,
        "detail": detail,
        "cross_chapter": cross_chapter,
        "sources": source_ids,
    }


def _numeric_matches(text: str) -> list[tuple[str, str, str | None, str | None]]:
    found: list[tuple[str, str, str | None, str | None]] = []
    for match in _QUANTITY.finditer(text):
        name = match.group(1).lower()
        if name in _STOP_NAMES:
            continue
        tail = _sentence_tail(text, match.end())
        found.append(
            (
                name,
                _canon_number(match.group(2)),
                _qualifier_in(tail),
                _unit_in(tail),
            )
        )
    return found


def _sentence_tail(text: str, start: int) -> str:
    tail = text[start:]
    tail = re.split(r"[.!?;]", tail, maxsplit=1)[0]
    return tail[:80]


def _qualifier_in(tail: str) -> str | None:
    lowered = tail.casefold()
    for marker in _QUALIFIER_MARKERS:
        index = lowered.find(marker)
        if index >= 0:
            rest = tail[index + len(marker):]
            rest = re.split(r"[,;.]", rest, maxsplit=1)[0].strip()
            if rest:
                return rest[:40]
    return None


def _unit_in(tail: str) -> str | None:
    lowered = tail.casefold()
    for unit in sorted(_CONDITION_UNITS, key=len, reverse=True):
        if lowered.startswith(unit):
            return unit
        token = " " + unit
        if token in lowered[:40]:
            return unit
    return None


def _definition_pairs(text: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for match in re.finditer(
        r"\b([A-Za-z][A-Za-z0-9 _-]{0,40})\s+(?:is|are|was)\s+defined\s+as\s+([^.;!?]{3,80})",
        text,
        re.IGNORECASE,
    ):
        subject = _normalise_phrase(match.group(1))
        object_phrase = _normalise_phrase(match.group(2))
        if subject and object_phrase:
            pairs.append((subject, object_phrase))
    return pairs


def _terminology_pairs(text: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for match in re.finditer(
        r"\b([A-Za-z][A-Za-z0-9 _-]{0,40})\s+(?:is|are)\s+also\s+called\s+([^.;!?]{2,60})",
        text,
        re.IGNORECASE,
    ):
        subject = _normalise_phrase(match.group(1))
        term = _normalise_phrase(match.group(2))
        if subject and term:
            pairs.append((subject, term))
    return pairs


def _normalise_phrase(raw: str) -> str:
    cleaned = re.sub(r"\s+", " ", raw).strip().lower()
    if len(cleaned) > 60 or not cleaned:
        return ""
    return cleaned


def _passage_sections(root: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for record in supported_paragraphs(root):
        identifier = record.get("id")
        section = record.get("section")
        if isinstance(identifier, str) and isinstance(section, str):
            mapping[identifier] = section
    for record in supported_drafts(root):
        identifier = record.get("id")
        section = record.get("section")
        if isinstance(identifier, str) and isinstance(section, str):
            mapping[identifier] = section
    return mapping


def _passage_sources(root: Path) -> dict[str, list[str]]:
    excerpts = excerpts_by_id(root)
    mapping: dict[str, list[str]] = {}
    for record in [*supported_paragraphs(root), *supported_drafts(root)]:
        identifier = record.get("id")
        if not isinstance(identifier, str):
            continue
        source_ids: list[str] = []
        raw_value = record.get("excerpts")
        raw = raw_value if isinstance(raw_value, list) else []
        for excerpt_id in raw:
            if not isinstance(excerpt_id, str):
                continue
            excerpt = excerpts.get(excerpt_id)
            source_id = excerpt.get("source_id") if isinstance(excerpt, dict) else None
            if isinstance(source_id, str) and source_id not in source_ids:
                source_ids.append(source_id)
        mapping[identifier] = source_ids
    return mapping


def _contradiction_for(root: Path, quantity: str) -> dict[str, object] | None:
    found = [record for record in fold_by_id(root / CONTRADICTIONS) if record.get("quantity") == quantity]
    if not found:
        return None
    return found[-1]


def _source_fingerprint(root: Path, source_id: str) -> str | None:
    for record in fold_by_id(root / PUBLIC_BIBLIOGRAPHY):
        if record.get("id") != source_id:
            continue
        payload = f"public:{source_id}:{record.get('text_sha256')}:{record.get('url')}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
    for record in fold_by_id(root / "sources" / "registry.jsonl"):
        if record.get("id") != source_id:
            continue
        payload = f"local:{source_id}:{record.get('sha256')}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return None


def _public_contradiction(record: dict[str, object]) -> dict[str, object]:
    visible = {
        "id": record.get("id"),
        "quantity": record.get("quantity"),
        "values": record.get("values"),
        "passages": record.get("passages"),
        "status": record.get("status"),
    }
    for key in ("verdict", "category", "detail", "sources", "cross_chapter"):
        if record.get(key) is not None:
            visible[key] = record.get(key)
    return visible
def _local(state: dict[str, object]) -> dict[str, object]:
    local = state.get("local_sources")
    if isinstance(local, dict):
        return dict(local)
    return {"status": "UNKNOWN", "prompted": False, "source_count": 0}


def _error(code: str, message: str) -> dict[str, object]:
    return {
        "status": code,
        "message": message,
        "prose_added": False,
        "released": False,
        "applied": False,
    }
