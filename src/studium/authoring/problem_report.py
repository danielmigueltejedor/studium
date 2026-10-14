"""Unified scientific review of structured academic problems.

The report keeps mathematical, dimensional, numerical and editorial
checks separate. Passing those checks does not prove physical validity.
"""

from collections.abc import Mapping

from studium.authoring.problem_verification import (
    verify_problem_dimensions,
    verify_problem_numeric,
)
from studium.authoring.substitution_audit import audit_substitution
from studium.verification.model import VerificationResult, VerificationStatus


def verify_problem_report(
    solution: Mapping[str, object],
    *,
    expected_value: float | None = None,
    expected_unit: str | None = None,
) -> VerificationResult:
    """Produce a non-destructive scientific review of one problem.

    FAILED means a performed check found an inconsistency.

    UNVERIFIED means the available checks cannot establish complete
    scientific validity.

    Physical assumptions are recorded but never treated as verified
    merely because they appear in the solution.
    """

    dimensional = verify_problem_dimensions(
        solution,
        expected_unit=expected_unit,
    )

    if expected_value is not None and expected_unit is not None:
        numeric = verify_problem_numeric(
            solution,
            expected_value=expected_value,
            expected_unit=expected_unit,
        )
    else:
        numeric = VerificationResult(
            status=VerificationStatus.UNVERIFIED,
            method="problem_numeric_reproduction",
            detail="An expected numerical value and unit are required.",
        )

    substitution = audit_substitution(solution)

    raw_assumptions = solution.get("assumptions")

    declared_assumptions = (
        tuple(
            item.strip()
            for item in raw_assumptions
            if isinstance(item, str) and item.strip()
        )
        if isinstance(raw_assumptions, list)
        else ()
    )

    issues: list[str] = []

    failed_checks = [
        name
        for name, result in (
            ("dimensional", dimensional),
            ("numeric", numeric),
        )
        if result.status is VerificationStatus.FAILED
    ]

    if failed_checks:
        issues.append(
            "Failed checks: " + ", ".join(failed_checks)
        )

    if dimensional.status is VerificationStatus.UNVERIFIED:
        issues.append("Dimensional verification is incomplete.")

    if numeric.status is VerificationStatus.UNVERIFIED:
        issues.append("Numerical reproduction is incomplete.")

    substitution_status = substitution.get("status")

    if substitution_status == "different":
        issues.append(
            "The stored substitution differs from the current "
            "generator output. Mathematical inconsistency is not proven."
        )
    elif substitution_status == "missing":
        issues.append("No stored substitution is available.")
    elif substitution_status == "inconclusive":
        issues.append("The stored substitution could not be audited.")

    if declared_assumptions:
        issues.append(
            "Physical assumptions are declared but have not "
            "been independently verified."
        )
    else:
        issues.append(
            "Physical assumptions are missing or not structured."
        )

    status = (
        VerificationStatus.FAILED
        if failed_checks
        else VerificationStatus.UNVERIFIED
    )

    return VerificationResult(
        status=status,
        method="structured_problem_scientific_review",
        detail=(
            "One or more checks found an inconsistency."
            if failed_checks
            else "Scientific validity has not been fully established."
        ),
        inputs={
            "expected_value": expected_value,
            "expected_unit": expected_unit,
        },
        outputs={
            "checks": {
                "dimensional": dimensional.as_dict(),
                "numeric": numeric.as_dict(),
                "substitution": substitution,
            },
            "issues": issues,
            "human_review_required": True,
        },
        assumptions=declared_assumptions,
        limitations=(
            "Mathematical correctness does not establish physical validity.",
            "Declared physical assumptions have not been independently checked.",
            "LaTeX differences do not by themselves prove mathematical errors.",
            "This report does not authorize automatic modification or release.",
        ),
        methods_used=(
            dimensional.method,
            numeric.method,
            "substitution_audit",
        ),
    )
