"""A second pass over a draft. The auditor is not a source of truth.

An audit cites a tool result the server already stored. A note that the
auditor agrees is not evidence. The audit adds no prose. A review can record
``audit_passed`` for this edition and still does not release the book.
"""

import hashlib
import re
from pathlib import Path

from studium.authoring.blueprint import current_sections
from studium.authoring.computation import computation_fingerprint
from studium.authoring.excerpts import excerpts_by_id
from studium.authoring.paragraphs import supported_paragraphs
from studium.authoring.problems import problem_input_sha256, problem_result_current
from studium.authoring.section_blocks import blocked_ids
from studium.authoring.support import corroboration_for_excerpts, supported_drafts
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

_AUDIT_LOG = "audit/audit.jsonl"
_KINDS = frozenset({"formula", "comparison", "historical", "literary", "scientific", "code"})
_MIN_WORDS = 25
_QUANTITY = re.compile(
    r"\b([A-Za-z][A-Za-z0-9_-]{1,40})\s*(?:=|is|equals)\s*(-?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
_OPINION = "a second model opinion is not a source of truth"


def record_audit(
    root: Path,
    *,
    target: object,
    kind: object,
    excerpts: object = None,
    computation: object = None,
    problem: object = None,
    figure: object = None,
    note: object = None,
    actor: dict[str, object] | None = None,
) -> dict[str, object]:
    """Record an audit of a paragraph or problem. Does not add prose or release."""

    check_kind = _kind(kind)
    if check_kind is None:
        return _error("mcp.invalid_input", "kind must be formula, comparison, historical, literary, scientific, or code")
    found = _target(root, target)
    if found is None:
        return _error("mcp.invalid_input", "target must be a stored paragraph or problem id")
    target_id, target_kind = found
    evidence, evidence_error = _evidence(root, excerpts, computation, problem, figure)
    if evidence_error is not None:
        if isinstance(note, str) and note.strip():
            return _error("audit.opinion_rejected", _OPINION)
        return evidence_error
    assert evidence is not None
    conflict = _chapter_conflict(root, target_id, target_kind, evidence)
    if conflict is not None:
        return _error("audit.rejected", conflict)
    try:
        with project_lock(root):
            state = load_state_holding_lock(root)
            passage_ids = [passage_id for passage_id, _text in _chapter_passages(root, target_id, target_kind)]
            record: dict[str, object] = {
                "schema_version": "1.0.0",
                "id": allocate_id(root, "REV"),
                "target": target_id,
                "target_kind": target_kind,
                "kind": check_kind,
                "evidence": evidence,
                "passages": passage_ids,
                "binding": _binding(root, passage_ids, evidence),
                "prose_added": False,
                "status": "recorded",
                "classification": "PENDING",
                "recorded_at": utc_now(),
            }
            append_jsonl(root / AUDITS, record)
            _log(root, record=record, actor=actor, operation="record_audit")
            fresh = load_state_holding_lock(root)
            return _body(fresh, status="recorded", audit=_public_audit(record))
    except ProjectLocked:
        return _error("storage.locked", "project is locked")


def contradiction_scan(root: Path) -> dict[str, object]:
    """Compare accepted numeric passages. A disagreement is an open contradiction."""

    grouped: dict[str, dict[str, list[str]]] = {}
    for passage_id, text in _accepted_passages(root):
        for name, value in _quantities(text):
            grouped.setdefault(name, {}).setdefault(value, []).append(passage_id)
    try:
        with project_lock(root):
            state = load_state_holding_lock(root)
            open_items: list[dict[str, object]] = []
            for name, values in sorted(grouped.items()):
                existing = _contradiction_for(root, name)
                if len(values) < 2:
                    if existing is not None and existing.get("status") == "open":
                        resolved = dict(existing)
                        resolved["status"] = "resolved"
                        resolved["recorded_at"] = utc_now()
                        append_jsonl(root / CONTRADICTIONS, resolved)
                    continue
                passages = sorted({item for ids in values.values() for item in ids})
                recorded = {
                    "schema_version": "1.0.0",
                    "id": existing["id"] if existing is not None else allocate_id(root, "CON"),
                    "quantity": name,
                    "values": {value: ids for value, ids in sorted(values.items())},
                    "passages": passages,
                    "status": "open",
                    "recorded_at": utc_now(),
                }
                append_jsonl(root / CONTRADICTIONS, recorded)
                open_items.append(_public_contradiction(recorded))
            marker = {
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


def book_review(root: Path) -> dict[str, object]:
    """Review this edition. ``audit_passed`` does not move the book to RELEASED."""

    reasons = review_blockers(root)
    passed = not reasons
    try:
        with project_lock(root):
            state = load_state_holding_lock(root)
            record: dict[str, object] = {
                "schema_version": "1.0.0",
                "id": "edition",
                "edition": review_edition(root),
                "status": "audit_passed" if passed else "blocked",
                "audit_passed": passed,
                "reasons": reasons,
                "released": False,
                "recorded_at": utc_now(),
            }
            append_jsonl(root / REVIEWS, record)
            fresh = load_state_holding_lock(root)
    except ProjectLocked:
        return _error("storage.locked", "project is locked")
    return {
        "status": "audit_passed" if passed else "blocked",
        "audit_passed": passed,
        "reasons": reasons,
        "released": False,
        "applied": False,
        "project_state": fresh.get("state"),
        "local_sources": _local(fresh),
        "message": "audit_passed is for this edition only. The book is not RELEASED.",
    }


def review_blockers(root: Path) -> list[str]:
    """Why this edition cannot pass. Empty means the checks passed."""

    reasons: list[str] = []
    gaps = explicit_gap_ids(root)
    covered = audited_paragraph_ids(root)
    for section in current_sections(root):
        if section["id"] in gaps:
            continue
        if section_needs_more_prose(root, section["id"]):
            reasons.append(f"{section['id']} is too short to teach")
        for paragraph in _section_paragraphs(root, section["id"]):
            identifier = paragraph.get("id")
            if isinstance(identifier, str) and identifier not in covered:
                reasons.append(f"{identifier} has no audit record")
    if open_contradictions(root):
        names = ", ".join(str(item["quantity"]) for item in open_contradictions(root))
        reasons.append(f"open contradiction: {names}")
    for figure in fold_by_id(root / FIGURES):
        section = figure.get("section")
        if isinstance(section, str) and section in gaps:
            continue
        if not _figure_checked(root, figure):
            identifier = figure.get("id") if isinstance(figure.get("id"), str) else "figure"
            reasons.append(f"{identifier} is not a checked figure")
    return reasons


def explicit_gap_ids(root: Path) -> set[str]:
    """Sections left empty or blocked. They are gaps, not short chapters."""

    covered = {section for paragraph in supported_paragraphs(root) if isinstance((section := paragraph.get("section")), str)}
    return {section["id"] for section in current_sections(root) if section["id"] not in covered} | blocked_ids(root)


def section_needs_more_prose(root: Path, section_id: str) -> bool:
    """A taught section needs several explanatory paragraphs, not one short paragraph."""

    teaching = _teaching_paragraphs(root, section_id)
    if len(teaching) < 2:
        return True
    return any(_too_short(paragraph, root) for paragraph in teaching)


def short_paragraph_id(root: Path, section_id: str) -> str | None:
    """A teaching paragraph that is one sentence, too small, or only a restatement."""

    for paragraph in _teaching_paragraphs(root, section_id):
        if _too_short(paragraph, root) and isinstance(paragraph.get("id"), str):
            return str(paragraph["id"])
    return None


def audited_targets(root: Path) -> set[str]:
    found: set[str] = set()
    for record in fold_by_id(root / AUDITS):
        if record.get("status") != "recorded" or record.get("prose_added") is not False:
            continue
        target = record.get("target")
        if isinstance(target, str):
            found.add(target)
    return found


def audited_paragraph_ids(root: Path) -> set[str]:
    """Paragraphs whose audit still matches the current paragraph and excerpt text.

    A later paragraph, a rewritten paragraph, or a changed excerpt is not covered.
    """

    paragraphs = supported_paragraphs(root)
    excerpts = excerpts_by_id(root)
    covered: set[str] = set()
    for record in fold_by_id(root / AUDITS):
        for paragraph in paragraphs:
            identifier = paragraph.get("id")
            if isinstance(identifier, str) and _covers_paragraph(root, record, paragraph, excerpts):
                covered.add(identifier)
    return covered


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
    number = float(raw)
    if number == int(number):
        return str(int(number))
    return str(number)


def _too_short(paragraph: dict[str, object], root: Path) -> bool:
    text = paragraph.get("text") if isinstance(paragraph.get("text"), str) else ""
    sentences = [part.strip() for part in re.split(r"[.!?]+", text) if part.strip()]
    if len(sentences) < 2 or len(text.split()) < _MIN_WORDS:
        return True
    excerpts = excerpts_by_id(root)
    raw = paragraph.get("excerpts") if isinstance(paragraph.get("excerpts"), list) else []
    words = set(text.lower().split())
    for excerpt_id in raw:
        if not isinstance(excerpt_id, str):
            continue
        excerpt = excerpts.get(excerpt_id)
        body = excerpt.get("text") if isinstance(excerpt, dict) else None
        if not isinstance(body, str) or not body.strip():
            continue
        excerpt_words = set(body.lower().split())
        if words and excerpt_words and words <= excerpt_words:
            return True
    return False


def _section_paragraphs(root: Path, section_id: str) -> list[dict[str, object]]:
    return [record for record in supported_paragraphs(root) if record.get("section") == section_id]


def _target(root: Path, value: object) -> tuple[str, str] | None:
    if not isinstance(value, str) or not value.strip():
        return None
    identifier = value.strip()
    if any(record.get("id") == identifier for record in supported_paragraphs(root)):
        return identifier, "paragraph"
    for record in fold_by_id(root / PROBLEMS):
        if record.get("id") == identifier:
            return identifier, "problem"
    if any(section["id"] == identifier for section in current_sections(root)):
        return identifier, "section"
    return None


def _teaching_paragraphs(root: Path, section_id: str) -> list[dict[str, object]]:
    return [record for record in _section_paragraphs(root, section_id) if record.get("role") != "self_check"]


def _chapter_passages(root: Path, target_id: str, target_kind: str) -> list[tuple[str, str]]:
    """Paragraph and problem text. Stored CLM claims are not chapter sentences."""

    passages: list[tuple[str, str]] = []
    for record in _grounded_records(root, target_id, target_kind):
        identifier = record.get("id")
        text = record.get("text")
        if isinstance(identifier, str) and isinstance(text, str):
            passages.append((identifier, text))
    return passages


def _grounded_records(root: Path, target_id: str, target_kind: str) -> list[dict[str, object]]:
    if target_kind == "paragraph":
        found = next((record for record in supported_paragraphs(root) if record.get("id") == target_id), None)
        return [found] if isinstance(found, dict) else []
    if target_kind == "section":
        return _section_paragraphs(root, target_id)
    if target_kind == "problem":
        found = next((record for record in fold_by_id(root / PROBLEMS) if record.get("id") == target_id), None)
        records: list[dict[str, object]] = []
        if isinstance(found, dict):
            prompt = found.get("prompt") if isinstance(found.get("prompt"), str) else ""
            source = found.get("source_text") if isinstance(found.get("source_text"), str) else ""
            excerpts = found.get("excerpts") if isinstance(found.get("excerpts"), list) else []
            records.append({"id": target_id, "text": f"{prompt}\n{source}", "excerpts": excerpts})
            section = found.get("section")
            if isinstance(section, str):
                records.extend(_section_paragraphs(root, section))
        return records
    return []


def _chapter_conflict(root: Path, target_id: str, target_kind: str, evidence: dict[str, object]) -> str | None:
    """Reject a sentence whose formula or number is not quoted or replayed."""

    if target_kind == "section" and not _section_paragraphs(root, target_id):
        return "an empty section is a gap, not a written chapter"
    missing = _ungrounded_formulas(root, target_id, target_kind)
    if missing:
        return "the formula is not in the cited excerpts and was not replayed: " + "; ".join(missing)
    by_name, bare = _evidence_numbers(root, evidence)
    cited_numbers = _cited_numbers(root, target_id, target_kind)
    for name, values in by_name.items():
        if len(values) > 1:
            return f"the stored sources contradict each other on {name}"
    for _passage_id, text in _chapter_passages(root, target_id, target_kind):
        for name, value in _quantities(text):
            stored = by_name.get(name)
            if stored is not None and value not in stored:
                return (
                    f"the chapter contradicts a stored number: {name} is {value} in the chapter "
                    f"and {', '.join(sorted(stored))} in the stored sources"
                )
            if value not in bare and value not in cited_numbers:
                return f"the chapter states {name} is {value}, which the stored sources do not support"
    return None


def _ungrounded_formulas(root: Path, target_id: str, target_kind: str) -> list[str]:
    """Formulas the paragraph states that no cited excerpt quotes and no computation replayed."""

    expressions = [
        record.get("expression")
        for record in fold_by_id(root / COMPUTATIONS)
        if record.get("status") == "replayed" and record.get("correct") is True and isinstance(record.get("expression"), str)
    ]
    stored_excerpts = excerpts_by_id(root)
    missing: list[str] = []
    seen: set[str] = set()
    for record in _grounded_records(root, target_id, target_kind):
        bodies = _record_excerpt_texts(record, stored_excerpts)
        text = record.get("text") if isinstance(record.get("text"), str) else ""
        for sentence in _sentences(text):
            for formula in _formulas(sentence):
                if _formula_grounded(formula, bodies, expressions):
                    continue
                key = _normalize_formula(formula)
                if key in seen:
                    continue
                seen.add(key)
                missing.append(formula)
    return missing


def _cited_numbers(root: Path, target_id: str, target_kind: str) -> set[str]:
    found: set[str] = set()
    stored_excerpts = excerpts_by_id(root)
    for record in _grounded_records(root, target_id, target_kind):
        for body in _record_excerpt_texts(record, stored_excerpts):
            for match in re.finditer(r"-?\d+(?:\.\d+)?", body):
                found.add(_canon_number(match.group(0)))
    for record in fold_by_id(root / COMPUTATIONS):
        if record.get("status") != "replayed" or record.get("correct") is not True:
            continue
        result = record.get("server_result")
        expression = record.get("expression")
        if isinstance(result, str):
            found.add(_canon_number(result))
        if isinstance(expression, str):
            for match in re.finditer(r"-?\d+(?:\.\d+)?", expression):
                found.add(_canon_number(match.group(0)))
    return found


def _record_excerpt_texts(record: dict[str, object], stored: dict[str, dict[str, object]]) -> list[str]:
    raw = record.get("excerpts") if isinstance(record.get("excerpts"), list) else []
    bodies: list[str] = []
    for excerpt_id in raw:
        excerpt = stored.get(excerpt_id) if isinstance(excerpt_id, str) else None
        body = excerpt.get("text") if isinstance(excerpt, dict) else None
        if isinstance(body, str) and body.strip():
            bodies.append(body)
    return bodies


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"[.!?]+", text) if part.strip()]


_MATH_OPS = set("+-×·*/^()=")


def _formulas(sentence: str) -> list[str]:
    found: list[str] = []
    start = 0
    while True:
        index = sentence.find("=", start)
        if index < 0:
            return found
        left = _expand_math(sentence, index, -1)
        right = _expand_math(sentence, index + 1, 1)
        raw = " ".join(sentence[left:right].split())
        if _looks_like_formula(raw):
            found.append(raw)
        start = index + 1


def _looks_like_formula(raw: str) -> bool:
    compact = _normalize_formula(raw)
    if "=" not in compact:
        return False
    if re.fullmatch(r"[a-z][a-z0-9_]{0,40}=-?\d+(?:\.\d+)?", compact):
        return False
    return bool(re.search(r"[+\-*/]", compact))


def _formula_grounded(formula: str, excerpts: list[str], expressions: list[object]) -> bool:
    needle = _normalize_formula(formula)
    if not needle or "=" not in needle:
        return False
    for text in excerpts:
        if needle in _normalize_formula(text):
            return True
    for expression in expressions:
        if isinstance(expression, str) and needle in _normalize_formula(expression):
            return True
    return False


def _normalize_formula(text: str) -> str:
    cleaned = text.casefold().replace("×", "*").replace("·", "*").replace("−", "-").replace("–", "-")
    return "".join(cleaned.split())


def _expand_math(sentence: str, pos: int, direction: int) -> int:
    i = pos
    limit = len(sentence)
    while True:
        if direction < 0:
            while i > 0 and sentence[i - 1].isspace():
                i -= 1
            if i == 0:
                return 0
            if sentence[i - 1] in _MATH_OPS:
                i -= 1
                continue
            token_end = i
            while i > 0 and (sentence[i - 1].isalnum() or sentence[i - 1] == "_"):
                i -= 1
            token = sentence[i:token_end]
            if token and (_is_math_token(token) or token.isdigit()):
                toward = _nearest_nonspace(sentence, token_end, 1)
                if toward is not None and sentence[toward] in _MATH_OPS:
                    continue
            return token_end
        while i < limit and sentence[i].isspace():
            i += 1
        if i >= limit:
            return limit
        if sentence[i] in _MATH_OPS:
            i += 1
            continue
        token_start = i
        while i < limit and (sentence[i].isalnum() or sentence[i] == "_"):
            i += 1
        token = sentence[token_start:i]
        if token and (_is_math_token(token) or token.isdigit()):
            toward = _nearest_nonspace(sentence, token_start - 1, -1)
            if toward is not None and sentence[toward] in _MATH_OPS:
                continue
        return token_start


def _nearest_nonspace(sentence: str, pos: int, direction: int) -> int | None:
    i = pos
    while 0 <= i < len(sentence):
        if not sentence[i].isspace():
            return i
        i += direction
    return None


def _is_math_token(token: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z]{1,3}", token))


def _evidence_numbers(root: Path, evidence: dict[str, object]) -> tuple[dict[str, set[str]], set[str]]:
    by_name: dict[str, set[str]] = {}
    bare: set[str] = set()

    def absorb(text: str) -> None:
        for name, value in _quantities(text):
            by_name.setdefault(name, set()).add(value)
            bare.add(value)
        for match in re.finditer(r"-?\d+(?:\.\d+)?", text):
            bare.add(_canon_number(match.group(0)))

    raw_excerpts = evidence.get("excerpts")
    if isinstance(raw_excerpts, list):
        stored = excerpts_by_id(root)
        for excerpt_id in raw_excerpts:
            excerpt = stored.get(excerpt_id) if isinstance(excerpt_id, str) else None
            body = excerpt.get("text") if isinstance(excerpt, dict) else None
            if isinstance(body, str):
                absorb(body)
    computation = evidence.get("computation")
    if isinstance(computation, str):
        for record in fold_by_id(root / COMPUTATIONS):
            if record.get("id") != computation:
                continue
            expression = record.get("expression") if isinstance(record.get("expression"), str) else ""
            result = record.get("server_result") if isinstance(record.get("server_result"), str) else ""
            absorb(f"{expression}\n{result}")
    problem = evidence.get("problem")
    if isinstance(problem, str):
        for record in fold_by_id(root / PROBLEMS):
            if record.get("id") != problem:
                continue
            prompt = record.get("prompt") if isinstance(record.get("prompt"), str) else ""
            source = record.get("source_text") if isinstance(record.get("source_text"), str) else ""
            expected = record.get("expected") if isinstance(record.get("expected"), str) else ""
            absorb(f"{prompt}\n{source}\n{expected}")
    figure = evidence.get("figure")
    if isinstance(figure, str):
        stored_figure = _figure(root, figure)
        caption = stored_figure.get("caption") if isinstance(stored_figure, dict) else None
        if isinstance(caption, str):
            absorb(caption)
    return by_name, bare


def _kind(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip().lower()
    if cleaned not in _KINDS:
        return None
    return cleaned


def _evidence(
    root: Path,
    excerpts: object,
    computation: object,
    problem: object,
    figure: object,
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    evidence: dict[str, object] = {}
    if excerpts is not None:
        checked, error = _two_excerpts(root, excerpts)
        if error is not None and computation is None and problem is None and figure is None:
            return None, error
        if checked is not None:
            evidence["excerpts"] = checked
            evidence["excerpts_result"] = "two_witnesses"
    if isinstance(computation, str) and computation.strip():
        if _computation_passed(root, computation.strip()):
            evidence["computation"] = computation.strip()
            evidence["computation_result"] = "COMPUTATION_REPRODUCED"
            evidence["mathematically_verified"] = False
            evidence["academically_reviewed"] = False
        elif "excerpts" not in evidence and problem is None and figure is None:
            return None, _error("audit.tool_result_missing", "the computation was not replayed by the server")
    if isinstance(problem, str) and problem.strip():
        if _rust_passed(root, problem.strip()):
            evidence["problem"] = problem.strip()
            evidence["problem_result"] = "reproducibility_check"
            evidence["independent_proof"] = False
        elif "excerpts" not in evidence and "computation" not in evidence and figure is None:
            return None, _error("audit.tool_result_missing", "the Rust test has not passed 3 times")
    if isinstance(figure, str) and figure.strip():
        stored = _figure(root, figure.strip())
        if stored is not None and _figure_checked(root, stored):
            evidence["figure"] = figure.strip()
            evidence["figure_result"] = "checked"
        elif "excerpts" not in evidence and "computation" not in evidence and "problem" not in evidence:
            return None, _error("audit.tool_result_missing", "the figure program has not been rerun")
    if not evidence:
        return None, _error(
            "audit.tool_result_missing",
            "an audit needs a passed tool result already stored",
        )
    return evidence, None


def _two_excerpts(root: Path, value: object) -> tuple[list[str] | None, dict[str, object] | None]:
    if not isinstance(value, list) or len(value) < 2:
        return None, _error("audit.tool_result_missing", "two excerpts from different sources are required")
    identifiers = [item.strip() for item in value if isinstance(item, str) and item.strip()]
    if len(identifiers) < 2:
        return None, _error("audit.tool_result_missing", "two excerpts from different sources are required")
    if corroboration_for_excerpts(root, identifiers) != "two_witnesses":
        return None, _error("audit.tool_result_missing", "the excerpts are not from different stored sources")
    return identifiers, None


def _computation_passed(root: Path, identifier: str) -> bool:
    for record in fold_by_id(root / COMPUTATIONS):
        if record.get("id") != identifier:
            continue
        return record.get("status") == "replayed" and record.get("correct") is True
    return False


def _rust_passed(root: Path, identifier: str) -> bool:
    for record in fold_by_id(root / PROBLEMS):
        if record.get("id") != identifier or record.get("kind") != "rust":
            continue
        runs = record.get("runs")
        if not problem_result_current(root, record):
            return False
        if record.get("status") != "checked" or record.get("correct") is not True or not isinstance(runs, list):
            return False
        passed = [run for run in runs if isinstance(run, dict) and run.get("passed") is True]
        return len(runs) >= 3 and len(passed) >= 3 and all(isinstance(run, dict) and run.get("passed") is True for run in runs)
    return False


def _figure(root: Path, identifier: str) -> dict[str, object] | None:
    return next((record for record in fold_by_id(root / FIGURES) if record.get("id") == identifier), None)


def _figure_checked(root: Path, record: dict[str, object]) -> bool:
    if record.get("status") != "checked" or record.get("correct") is not True:
        return False
    output = record.get("output")
    if not isinstance(output, str) or ".." in Path(output).parts or output.startswith("/"):
        return False
    path = (root / output).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError:
        return False
    try:
        return path.is_file() and not path.is_symlink() and path.stat().st_size > 0
    except OSError:
        return False


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


def _dependency_entries(
    root: Path,
    evidence: dict[str, object],
    excerpt_hashes: dict[str, str],
) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add(kind: str, identifier: str, digest: str | None) -> None:
        if digest is None or (kind, identifier) in seen:
            return
        seen.add((kind, identifier))
        entries.append({"kind": kind, "id": identifier, "sha256": digest})

    computation = evidence.get("computation")
    if isinstance(computation, str):
        record = next((item for item in fold_by_id(root / COMPUTATIONS) if item.get("id") == computation), None)
        if isinstance(record, dict):
            add("computation", computation, computation_fingerprint(record))
    problem = evidence.get("problem")
    if isinstance(problem, str):
        record = next((item for item in fold_by_id(root / PROBLEMS) if item.get("id") == problem), None)
        if isinstance(record, dict):
            add("problem", problem, problem_input_sha256(root, record))
    figure = evidence.get("figure")
    if isinstance(figure, str):
        record = next((item for item in fold_by_id(root / FIGURES) if item.get("id") == figure), None)
        if isinstance(record, dict):
            payload = f"{record.get('source_sha256')}:{record.get('status')}:{record.get('correct')}"
            add("figure", figure, hashlib.sha256(payload.encode("utf-8")).hexdigest())
    excerpts = excerpts_by_id(root)
    for excerpt_id in excerpt_hashes:
        excerpt = excerpts.get(excerpt_id)
        source_id = excerpt.get("source_id") if isinstance(excerpt, dict) else None
        if isinstance(source_id, str):
            add("source", source_id, _source_fingerprint(root, source_id))
    return entries


def _dependencies_current(root: Path, entries: list[object]) -> bool:
    for entry in entries:
        if not isinstance(entry, dict):
            return False
        kind = entry.get("kind")
        identifier = entry.get("id")
        digest = entry.get("sha256")
        if not isinstance(kind, str) or not isinstance(identifier, str) or not isinstance(digest, str):
            return False
        if _current_dependency(root, kind, identifier) != digest:
            return False
    return True


def _current_dependency(root: Path, kind: str, identifier: str) -> str | None:
    if kind == "computation":
        record = next((item for item in fold_by_id(root / COMPUTATIONS) if item.get("id") == identifier), None)
        return computation_fingerprint(record) if isinstance(record, dict) else None
    if kind == "problem":
        record = next((item for item in fold_by_id(root / PROBLEMS) if item.get("id") == identifier), None)
        return problem_input_sha256(root, record) if isinstance(record, dict) else None
    if kind == "figure":
        record = next((item for item in fold_by_id(root / FIGURES) if item.get("id") == identifier), None)
        if not isinstance(record, dict):
            return None
        payload = f"{record.get('source_sha256')}:{record.get('status')}:{record.get('correct')}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
    if kind == "source":
        return _source_fingerprint(root, identifier)
    return None


def _binding(root: Path, passage_ids: list[str], evidence: dict[str, object]) -> dict[str, object]:
    """Hashes the audit was allowed to cite. A later change makes the audit stale."""

    paragraphs = {record.get("id"): record for record in supported_paragraphs(root)}
    excerpts = excerpts_by_id(root)
    passage_hashes: dict[str, str] = {}
    excerpt_hashes: dict[str, str] = {}
    for passage_id in passage_ids:
        paragraph = paragraphs.get(passage_id)
        if isinstance(paragraph, dict):
            _bind_paragraph(paragraph, excerpts, passage_hashes, excerpt_hashes)
    _bind_excerpt_ids(evidence.get("excerpts"), excerpts, excerpt_hashes)
    return {
        "passages": passage_hashes,
        "excerpts": excerpt_hashes,
        "dependencies": _dependency_entries(root, evidence, excerpt_hashes),
    }


def _bind_paragraph(
    paragraph: dict[str, object],
    excerpts: dict[str, dict[str, object]],
    passage_hashes: dict[str, str],
    excerpt_hashes: dict[str, str],
) -> None:
    identifier = paragraph.get("id")
    digest = paragraph.get("text_sha256")
    if isinstance(identifier, str) and isinstance(digest, str):
        passage_hashes[identifier] = digest
    _bind_excerpt_ids(paragraph.get("excerpts"), excerpts, excerpt_hashes)


def _bind_excerpt_ids(
    raw: object,
    excerpts: dict[str, dict[str, object]],
    excerpt_hashes: dict[str, str],
) -> None:
    if not isinstance(raw, list):
        return
    for excerpt_id in raw:
        if not isinstance(excerpt_id, str):
            continue
        excerpt = excerpts.get(excerpt_id)
        digest = excerpt.get("text_sha256") if isinstance(excerpt, dict) else None
        if isinstance(digest, str):
            excerpt_hashes[excerpt_id] = digest


def _covers_paragraph(
    root: Path,
    record: dict[str, object],
    paragraph: dict[str, object],
    excerpts: dict[str, dict[str, object]],
) -> bool:
    if record.get("status") != "recorded" or record.get("prose_added") is not False:
        return False
    binding = record.get("binding")
    if not isinstance(binding, dict):
        return False
    passage_hashes = binding.get("passages")
    excerpt_hashes = binding.get("excerpts")
    if not isinstance(passage_hashes, dict) or not isinstance(excerpt_hashes, dict):
        return False
    identifier = paragraph.get("id")
    if not isinstance(identifier, str) or passage_hashes.get(identifier) != paragraph.get("text_sha256"):
        return False
    for excerpt_id, digest in excerpt_hashes.items():
        current = excerpts.get(str(excerpt_id))
        current_digest = current.get("text_sha256") if isinstance(current, dict) else None
        if current_digest != digest:
            return False
    raw = paragraph.get("excerpts")
    cited = [item for item in raw if isinstance(item, str)] if isinstance(raw, list) else []
    for excerpt_id in cited:
        current = excerpts.get(excerpt_id)
        current_digest = current.get("text_sha256") if isinstance(current, dict) else None
        if excerpt_hashes.get(excerpt_id) != current_digest:
            return False
    dependencies = binding.get("dependencies")
    if isinstance(dependencies, list) and not _dependencies_current(root, dependencies):
        return False
    return True


def _public_audit(record: dict[str, object]) -> dict[str, object]:
    return {
        "id": record.get("id"),
        "target": record.get("target"),
        "target_kind": record.get("target_kind"),
        "kind": record.get("kind"),
        "evidence": record.get("evidence"),
        "prose_added": False,
        "status": "recorded",
        "classification": "PENDING",
    }


def _public_contradiction(record: dict[str, object]) -> dict[str, object]:
    return {
        "id": record.get("id"),
        "quantity": record.get("quantity"),
        "values": record.get("values"),
        "passages": record.get("passages"),
        "status": record.get("status"),
    }


def _body(state: dict[str, object], *, status: str, audit: dict[str, object]) -> dict[str, object]:
    return {
        "status": status,
        "audit": audit,
        "prose_added": False,
        "message": "The audit adds no new prose. " + _OPINION,
        "released": state.get("state") == "RELEASED",
        "applied": False,
        "project_state": state.get("state"),
        "local_sources": _local(state),
    }


def _log(root: Path, *, record: dict[str, object], actor: dict[str, object] | None, operation: str) -> None:
    append_jsonl(
        root / _AUDIT_LOG,
        {
            "schema_version": "1.0.0",
            "timestamp": utc_now(),
            "source_id": record.get("id"),
            "operation": operation,
            "origin": None,
            "actor": {"kind": actor.get("kind")} if isinstance(actor, dict) and isinstance(actor.get("kind"), str) else None,
            "previous_hash": None,
            "new_hash": None,
            "result": record.get("status"),
            "tool": operation,
        },
    )


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
