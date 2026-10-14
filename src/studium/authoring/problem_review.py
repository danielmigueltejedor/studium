"""Read-only scientific review of stored academic problems."""

import math
from pathlib import Path

from studium.authoring.problem_report import verify_problem_report
from studium.authoring.problems import list_problems


def review_stored_problem(
    root: Path,
    *,
    problem_id: object,
    expected_value: object = None,
    expected_unit: object = None,
) -> dict[str, object]:
    """Review one stored numerical problem without changing its status.

    The review is advisory. It does not persist verification results,
    update stored problems, or authorize publication.
    """

    if (
        not isinstance(problem_id, str)
        or not problem_id.strip()
        or len(problem_id) > 120
    ):
        return {
            "status": "mcp.invalid_input",
            "message": "A valid problem id is required.",
        }

    identifier = problem_id.strip()

    if (expected_value is None) != (expected_unit is None):
        return {
            "status": "mcp.invalid_input",
            "message": "expected_value and expected_unit must be provided together.",
        }

    numeric_value: float | None = None
    unit_value: str | None = None

    if expected_value is not None:
        if (
            isinstance(expected_value, bool)
            or not isinstance(expected_value, (int, float))
        ):
            return {
                "status": "mcp.invalid_input",
                "message": "expected_value must be a finite number.",
            }

        try:
            numeric_value = float(expected_value)
        except (ValueError, TypeError, OverflowError):
            return {
                "status": "mcp.invalid_input",
                "message": "expected_value could not be converted.",
            }

        if not math.isfinite(numeric_value):
            return {
                "status": "mcp.invalid_input",
                "message": "expected_value must be finite.",
            }

        if (
            not isinstance(expected_unit, str)
            or not expected_unit.strip()
            or len(expected_unit) > 100
        ):
            return {
                "status": "mcp.invalid_input",
                "message": "expected_unit must be a valid unit string.",
            }

        unit_value = expected_unit.strip()

    listed = list_problems(root)
    records = listed.get("problems")

    if not isinstance(records, list):
        return {
            "status": "problem.review_unavailable",
            "message": "The problem collection could not be read.",
        }

    problem = next(
        (
            item
            for item in records
            if isinstance(item, dict) and item.get("id") == identifier
        ),
        None,
    )

    if problem is None:
        return {
            "status": "problem.not_found",
            "message": "No stored problem has that id.",
        }

    if problem.get("kind") != "numeric":
        return {
            "status": "problem.unsupported_kind",
            "message": "Scientific problem review currently supports numeric problems.",
        }

    stored_solution = problem.get("solution")
    solution = stored_solution if isinstance(stored_solution, dict) else {}

    report = verify_problem_report(
        solution,
        expected_value=numeric_value,
        expected_unit=unit_value,
    )

    return {
        "status": "ok",
        "problem_id": identifier,
        "problem_status": problem.get("status"),
        "record_current": problem.get("current") is not False,
        "report": report.as_dict(),
        "advisory": True,
        "stored_content_modified": False,
    }
