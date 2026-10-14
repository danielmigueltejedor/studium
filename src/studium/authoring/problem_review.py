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

    expected_text: str | None = None
    expected_source = "caller" if numeric_value is not None else None
    if numeric_value is None:
        # Without a caller-supplied value, review the problem's own stated answer in the
        # unit of its final step, read at the precision it is written with.
        stored_expected = problem.get("expected")
        stored_unit = _final_step_unit(solution)
        if isinstance(stored_expected, str) and stored_unit is not None:
            try:
                candidate = float(stored_expected)
            except ValueError:
                candidate = math.nan
            if math.isfinite(candidate):
                numeric_value, unit_value, expected_text = candidate, stored_unit, stored_expected
                expected_source = "stored"

    report = verify_problem_report(
        solution,
        expected_value=numeric_value,
        expected_unit=unit_value,
        expected_text=expected_text,
    )

    answer_check = problem.get("answer_check")
    return {
        "status": "ok",
        "problem_id": identifier,
        "problem_status": problem.get("status"),
        "record_current": problem.get("current") is not False,
        "expected_source": expected_source,
        "evidence": {
            # Three different questions. None of them is scientific validity.
            "source_independence": problem.get("status") == "two_witnesses",
            "answer_arithmetic": answer_check.get("result") if isinstance(answer_check, dict) else "not_checked",
            "model_reproduction": _numeric_status(report.as_dict()),
            "scientific_validity": "not_established",
        },
        "report": report.as_dict(),
        "advisory": True,
        "stored_content_modified": False,
    }


def _numeric_status(report: dict[str, object]) -> str:
    outputs = report.get("outputs")
    checks = outputs.get("checks") if isinstance(outputs, dict) else None
    numeric = checks.get("numeric") if isinstance(checks, dict) else None
    status = numeric.get("status") if isinstance(numeric, dict) else None
    return str(status) if status is not None else "UNVERIFIED"


def _final_step_unit(solution: dict[str, object]) -> str | None:
    steps = solution.get("steps")
    if not isinstance(steps, list):
        return None
    for step in reversed(steps):
        if isinstance(step, dict) and "expression" in step:
            unit = step.get("unit")
            return unit.strip() if isinstance(unit, str) and unit.strip() else None
    return None
