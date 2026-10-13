"""Non-destructive audit of stored numerical substitutions."""

from collections.abc import Mapping
from typing import cast

from studium.authoring.problems import _auto_substitution, _solution


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
        "origin": origin,
        "stored": stored,
        "candidate": candidate,
    }
