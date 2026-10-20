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

#: A number as a book writes it: ``9.81``, the typeset decimal comma ``9{,}81`` and, in Spanish prose, ``9,81``
#: (a comma followed by one or two digits, or four or more, is a decimal; ``1,000`` stays a thousands group).
_NUMBER = r"-?\d+(?:(?:\{,\}|\.)\d+|,\d{1,2}(?!\d)|,\d{4,})?"

_QUANTITY = re.compile(
    rf"\b([A-Za-z][A-Za-z0-9_-]{{1,40}})\s*(?:=|is|equals)\s*({_NUMBER})",
    re.IGNORECASE,
)

_CODE_SPAN = re.compile(r"```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`\n]+`")


def _strip_code_spans(text: str) -> str:
    """Remove Markdown fenced code blocks and inline code spans before scanning prose."""

    return _CODE_SPAN.sub(" ", text)


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

    Every scan re-evaluates every stored open record against the current text.
    An open record is resolved only by a scan: when its quantity is no longer
    detected (``no_longer_detected``) or is now a non-blocking finding
    (``reclassified``). The resolution names the passages whose text changed
    since the record was opened; the open record stays in the append-only
    history. A scan of unchanged text appends nothing new for a finding.
    """

    findings = _academic_findings(root)
    texts = _passage_hashes(root)
    try:
        with project_lock(root):
            edition = writer_edition(root)
            stored = _stored_by_key(root)
            open_items: list[dict[str, object]] = []
            resolved_items: list[dict[str, object]] = []
            detected: set[tuple[str, str]] = set()
            for finding in sorted(findings, key=lambda item: (item["quantity"], item["category"])):
                key = (str(finding["quantity"]), str(finding["category"]))
                detected.add(key)
                records = stored.get(key, [])
                opened = [record for record in records if record.get("status") == "open"]
                blocking = str(finding["verdict"]) in _BLOCKING_VERDICTS
                if blocking:
                    keep = opened[0] if opened else (records[-1] if records else None)
                    recorded = _finding_record(finding, keep, "open", texts, root)
                    if keep is None or _changed(keep, recorded):
                        append_jsonl(root / CONTRADICTIONS, recorded)
                    open_items.append(_public_contradiction(recorded))
                    for extra in opened[1:]:
                        resolved_items.append(_resolve(root, extra, "duplicate", finding, texts, edition, keep))
                    continue
                for record in opened:
                    resolved_items.append(_resolve(root, record, "reclassified", finding, texts, edition, None))
                keep = next((record for record in reversed(records) if record.get("status") == "not_open"), None)
                recorded = _finding_record(finding, keep, "not_open", texts, root)
                if keep is None or _changed(keep, recorded):
                    append_jsonl(root / CONTRADICTIONS, recorded)
            for key, records in sorted(stored.items()):
                if key in detected:
                    continue
                for record in records:
                    if record.get("status") == "open":
                        resolved_items.append(_resolve(root, record, "no_longer_detected", None, texts, edition, None))
            marker: dict[str, object] = {
                "schema_version": "1.0.0",
                "id": "scan",
                "edition": edition,
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
        "resolved": resolved_items,
        "resolved_count": len(resolved_items),
        "released": fresh.get("state") == "RELEASED",
        "project_state": fresh.get("state"),
        "local_sources": _local(fresh),
        "applied": False,
    }


_FINDING_FIELDS = ("quantity", "values", "passages", "status", "verdict", "category", "detail", "sources", "cross_chapter")


def _finding_record(
    finding: dict[str, object],
    keep: dict[str, object] | None,
    status: str,
    texts: dict[str, str],
    root: Path,
) -> dict[str, object]:
    passages = _finding_strings(finding, "passages")
    return {
        "schema_version": "1.0.0",
        "id": keep["id"] if keep is not None else allocate_id(root, "CON"),
        "quantity": finding["quantity"],
        "values": finding["values"],
        "passages": passages,
        "passage_sha256": {passage: texts[passage] for passage in passages if passage in texts},
        "status": status,
        "verdict": finding["verdict"],
        "category": finding["category"],
        "detail": finding["detail"],
        "sources": _finding_strings(finding, "sources"),
        "cross_chapter": finding["cross_chapter"],
        "recorded_at": utc_now(),
    }


def _changed(stored: dict[str, object], recorded: dict[str, object]) -> bool:
    fields = (*_FINDING_FIELDS, "passage_sha256")
    return any(stored.get(field) != recorded.get(field) for field in fields)


def _resolve(
    root: Path,
    record: dict[str, object],
    reason: str,
    finding: dict[str, object] | None,
    texts: dict[str, str],
    edition: str,
    kept: dict[str, object] | None,
) -> dict[str, object]:
    """Close an open record on the evidence of this scan. The open row stays in history."""

    passages = _finding_strings(record, "passages")
    hashes = record.get("passage_sha256")
    known = hashes if isinstance(hashes, dict) else {}
    removed = [passage for passage in passages if passage not in texts]
    if known:
        changed = [passage for passage in passages if passage not in texts or known.get(passage) != texts[passage]]
        unknown: list[str] = []
    else:
        changed = removed
        unknown = [passage for passage in passages if passage in texts]
    resolution: dict[str, object] = {
        "reason": reason,
        "scan_edition": edition,
        "previous_verdict": record.get("verdict"),
        "previous_values": record.get("values"),
        "passages_changed": changed,
        "passages_removed": removed,
        "passages_unknown": unknown,
        "passage_evidence": "sha256" if known else "unrecorded: the open record predates passage hashes",
    }
    if finding is not None:
        resolution["verdict"] = finding["verdict"]
        resolution["values"] = finding["values"]
        resolution["detail"] = finding["detail"]
    if kept is not None:
        resolution["kept"] = kept.get("id")
    resolved = dict(record)
    resolved["status"] = "resolved"
    resolved["resolution"] = resolution
    resolved["recorded_at"] = utc_now()
    append_jsonl(root / CONTRADICTIONS, resolved)
    visible = _public_contradiction(resolved)
    visible["resolution"] = resolution
    return visible


def _stored_by_key(root: Path) -> dict[tuple[str, str], list[dict[str, object]]]:
    """Current stored records per (quantity, category), oldest first. Legacy rows default to numeric."""

    grouped: dict[tuple[str, str], list[dict[str, object]]] = {}
    for record in fold_by_id(root / CONTRADICTIONS):
        quantity = record.get("quantity")
        if record.get("id") == "scan" or not isinstance(quantity, str):
            continue
        category = record.get("category") if isinstance(record.get("category"), str) else "numeric"
        grouped.setdefault((quantity, str(category)), []).append(record)
    return grouped


def _passage_hashes(root: Path) -> dict[str, str]:
    return {
        identifier: hashlib.sha256(text.encode("utf-8")).hexdigest()
        for identifier, text in _accepted_passages(root)
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
    fingerprints = source_fingerprints(root)
    for record in excerpts_by_id(root).values():
        source_id = record.get("source_id")
        if isinstance(source_id, str) and source_id not in seen_sources:
            seen_sources.add(source_id)
            lines.append(f"source:{source_id}:{fingerprints.get(source_id)}")
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
    prose = _strip_code_spans(text)
    found: list[tuple[str, str]] = []
    for match in _QUANTITY.finditer(prose):
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
    number = float(raw.replace("{,}", ".").replace(",", "."))
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
    prose = _strip_code_spans(text)
    found: list[tuple[str, str, str | None, str | None]] = []
    for match in _QUANTITY.finditer(prose):
        name = match.group(1).lower()
        if name in _STOP_NAMES:
            continue
        tail = _sentence_tail(prose, match.end())
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



def source_fingerprints(root: Path) -> dict[str, str]:
    """``_source_fingerprint`` for every source, reading each registry once."""

    found: dict[str, str] = {}
    for record in fold_by_id(root / "sources" / "registry.jsonl"):
        identifier = record.get("id")
        if isinstance(identifier, str):
            payload = f"local:{identifier}:{record.get('sha256')}"
            found[identifier] = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    for record in fold_by_id(root / PUBLIC_BIBLIOGRAPHY):
        identifier = record.get("id")
        if isinstance(identifier, str):
            payload = f"public:{identifier}:{record.get('text_sha256')}:{record.get('url')}"
            found[identifier] = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return found


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
