"""Non-destructive audit of stored numerical substitutions."""

import re
from collections.abc import Mapping
from typing import cast

from studium.authoring.problems import _auto_substitution, _solution

# The classifier recognises only a narrow subset of generated LaTeX.
# It is not a general LaTeX parser or a mathematical proof.
_NUMBER = r"-?(?:\d+(?:\.\d+)?|\.\d+)"
_UNIT = r"(?:\\,\\mathrm\{[A-Za-z]+\}(?:\^\{[-+]?\d+\})?)*"
_ATOM = _NUMBER + _UNIT

_ATOM_WRAPPER = re.compile(
    r"\\left\((" + _ATOM + r")\\right\)(?!\s*\^)"
)

_DOUBLE_POWER_WRAPPER = re.compile(
    r"\\left\(\\left\(("
    + _ATOM
    + r")\\right\)\\right\)(?=\s*\^)"
)


def _presentation_form(latex: str) -> str:
    """Remove only recognised redundant wrappers and multiplication spacing."""
    cleaned = latex.strip()

    cleaned = _DOUBLE_POWER_WRAPPER.sub(
        lambda match: r"\left(" + match.group(1) + r"\right)",
        cleaned,
    )

    cleaned = _ATOM_WRAPPER.sub(
        lambda match: match.group(1),
        cleaned,
    )

    cleaned = cleaned.replace(r"\cdot", " ")

    return " ".join(cleaned.split())


# Detect implicit multiplication between a unit-bearing quantity
# and a following numerical quantity. Such notation needs review.
_AMBIGUOUS_QUANTITY_PRODUCT = re.compile(
    r"\\mathrm\{[A-Za-z]+\}(?:\^\{[-+]?\d+\})?"
    r"(?:\\,\\mathrm\{[A-Za-z]+\}(?:\^\{[-+]?\d+\})?)*"
    r"[ \t]+(?=-?(?:\d+(?:\.\d+)?|\.\d+)(?:\\,|[ \t]))"
)


def classify_substitution_difference(
    stored: str,
    candidate: str,
) -> str:
    """Conservatively classify two LaTeX substitution representations.

    Unrecognised transformations always require review. This function
    never asserts that an underlying physical model is correct.
    """
    if stored.strip() == candidate.strip():
        return "identical"

    if len(stored) > 4096 or len(candidate) > 4096:
        return "requires_review"

    if _presentation_form(stored) == _presentation_form(candidate):
        if _AMBIGUOUS_QUANTITY_PRODUCT.search(stored):
            return "ambiguous_notation"
        return "presentation_only"

    return "requires_review"


def audit_substitution(solution: Mapping[str, object]) -> dict[str, object]:
    """Compare stored substitution LaTeX with the current generator.

    This operation never modifies the supplied solution or its storage.

    A textual difference does not, by itself, establish mathematical
    inconsistency. Existing unmarked substitutions have unknown provenance.
    """
    stored = solution.get("substitution")

    origin = (
        "generated"
        if solution.get("substitution_origin") == "generated"
        else "unknown"
    )

    if not isinstance(stored, str) or not stored.strip():
        return {
            "status": "missing",
            "origin": origin,
            "reason": "No stored substitution is available.",
        }

    normalized, error = _solution(dict(solution))

    if error is not None or normalized is None:
        return {
            "status": "inconclusive",
            "origin": origin,
            "reason": "The structured solution could not be normalized.",
        }

    model = normalized.get("model")
    given = normalized.get("given")

    if not isinstance(model, list) or not isinstance(given, list):
        return {
            "status": "inconclusive",
            "origin": origin,
            "reason": "The symbolic model or numerical data are missing.",
        }

    candidate = _auto_substitution(
        cast("list[dict[str, str]]", model),
        cast("list[dict[str, str]]", given),
    )

    if candidate is None:
        return {
            "status": "inconclusive",
            "origin": origin,
            "reason": "The current generator cannot reproduce a substitution.",
        }

    status = "match" if stored.strip() == candidate.strip() else "different"

    return {
        "status": status,
        "difference_kind": classify_substitution_difference(
            stored,
            candidate,
        ),
        "origin": origin,
        "stored": stored,
        "candidate": candidate,
    }
