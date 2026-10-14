"""Read-only inventory of substitutions across a Studium book.

This audits mathematical presentation, not global scientific validity.
"""

from collections import Counter
from pathlib import Path

from studium.authoring.problems import list_problems
from studium.authoring.substitution_audit import audit_substitution

MAX_PAGE_SIZE = 50
_REVIEW_CATEGORIES = frozenset({
    "ambiguous_notation",
    "requires_review",
})


def audit_book_substitutions(
    root: Path,
    *,
    offset: object = 0,
    limit: object = 30,
) -> dict[str, object]:
    """Audit one bounded page of stored problems without modifying them."""

    if (
        isinstance(offset, bool)
        or not isinstance(offset, int)
        or offset < 0
    ):
        return {
            "status": "mcp.invalid_input",
            "message": "offset must be a non-negative integer.",
        }

    if (
        isinstance(limit, bool)
        or not isinstance(limit, int)
        or not 1 <= limit <= MAX_PAGE_SIZE
    ):
        return {
            "status": "mcp.invalid_input",
            "message": "limit must be an integer between 1 and 50.",
        }

    listed = list_problems(root)

    if listed.get("status") != "ok":
        return listed

    problems = listed.get("problems")

    if not isinstance(problems, list):
        return {
            "status": "problem.audit_unavailable",
            "message": "The stored problem inventory is unavailable.",
        }

    total = len(problems)
    selected = problems[offset:offset + limit]
    counts: Counter[str] = Counter()
    items: list[dict[str, object]] = []

    for problem in selected:
        if not isinstance(problem, dict):
            category = "invalid_record"
            item: dict[str, object] = {
                "id": None,
                "classification": category,
            }
        else:
            identifier = problem.get("id")
            solution = problem.get("solution")

            if not isinstance(solution, dict):
                category = "no_structured_solution"
                item = {
                    "id": identifier,
                    "classification": category,
                }
            else:
                audit = audit_substitution(solution)
                status = str(audit.get("status", "inconclusive"))

                category = (
                    str(audit.get("difference_kind", "requires_review"))
                    if status == "different"
                    else status
                )

                item = {
                    "id": identifier,
                    "substitution_status": status,
                    "classification": category,
                    "origin": audit.get("origin", "unknown"),
                }

                if category in _REVIEW_CATEGORIES:
                    item["stored"] = audit.get("stored")
                    item["candidate"] = audit.get("candidate")

                if "reason" in audit:
                    item["reason"] = audit["reason"]

        counts[category] += 1
        items.append(item)

    next_offset = offset + len(items)

    return {
        "status": "ok",
        "scope": "substitution_presentation_audit",
        "total_problems": total,
        "offset": offset,
        "examined": len(items),
        "next_offset": next_offset if next_offset < total else None,
        "summary": dict(sorted(counts.items())),
        "items": items,
        "advisory": True,
        "stored_content_modified": False,
        "limitations": [
            "Counts describe only this page, not necessarily the entire book.",
            "Presentation equivalence does not establish physical validity.",
            "Unknown substitution provenance cannot be inferred.",
            "No stored substitution is regenerated or overwritten.",
            "Pagination limits result size, not symbolic execution time.",
        ],
    }
