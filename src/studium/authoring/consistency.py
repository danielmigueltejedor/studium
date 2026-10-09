"""Book-wide consistency report.

Combines the registries (notation, terminology, equations) with the stored
drafts: conflicting symbols, conflicting definitions, duplicate text,
duplicate equation identifiers with different equations, and open
contradictions. Every check is deterministic and labeled with what it can and
cannot detect. It reports; it never edits.
"""

from __future__ import annotations

from pathlib import Path

from studium.authoring.contradictions import open_contradictions
from studium.authoring.notation import notation_conflicts, terminology_conflicts
from studium.authoring.paragraphs import supported_paragraphs
from studium.storage.records import DERIVATIONS, fold_by_id


def consistency_report(root: Path) -> dict[str, object]:
    """One report over the stored registries and drafts."""

    duplicates = _duplicate_paragraphs(root)
    equations = equation_registry(root)
    equation_conflicts = [
        {
            "equation_id": identifier,
            "equations": sorted(values),
        }
        for identifier, values in sorted(equations.items())
        if len(values) > 1
    ]
    notation = notation_conflicts(root)
    terminology = terminology_conflicts(root)
    contradictions = open_contradictions(root)
    findings = (
        len(duplicates)
        + len(equation_conflicts)
        + len(notation)
        + len(terminology)
        + len(contradictions)
    )
    return {
        "status": "ok",
        "consistent": findings == 0,
        "findings": findings,
        "notation_conflicts": notation,
        "terminology_conflicts": terminology,
        "duplicate_paragraphs": duplicates,
        "equation_conflicts": equation_conflicts,
        "open_contradictions": [
            {"target": item.get("target"), "kind": item.get("kind"), "status": item.get("status")}
            for item in contradictions
        ],
        "limitations": (
            "duplicate detection compares full stored texts only",
            "equation conflicts compare identifiers and final equations, not derivation steps",
            "terminology conflicts compare recorded definitions, not synonyms or inflections",
        ),
    }


def equation_registry(root: Path) -> dict[str, set[str]]:
    """equation_id -> the set of final equations recorded under it."""

    registry: dict[str, set[str]] = {}
    for record in fold_by_id(root / DERIVATIONS):
        identifier = record.get("equation_id")
        equation = record.get("equation")
        if isinstance(identifier, str) and isinstance(equation, str):
            registry.setdefault(identifier, set()).add(equation)
    return registry


def _duplicate_paragraphs(root: Path) -> list[dict[str, object]]:
    seen: dict[str, list[dict[str, object]]] = {}
    for record in supported_paragraphs(root):
        digest = record.get("text_sha256")
        if isinstance(digest, str):
            seen.setdefault(digest, []).append(record)
    duplicates: list[dict[str, object]] = []
    for digest, records in sorted(seen.items()):
        if len(records) > 1:
            duplicates.append(
                {
                    "text_sha256": digest,
                    "sections": sorted({str(item.get("section")) for item in records}),
                    "paragraphs": [str(item.get("id")) for item in records],
                }
            )
    return duplicates
