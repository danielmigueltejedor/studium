"""Structured verification results.

A status is a claim about *how* something was checked, not a claim that the
result is physical truth. Callers must not collapse the statuses into a single
boolean.
"""

from dataclasses import dataclass, field
from enum import StrEnum


class VerificationStatus(StrEnum):
    """How a mathematical claim was checked.

    The ordering is deliberate. Weakest first. Tests and reports may sort on
    ``strength`` but a stronger status must never be inferred from a weaker one.
    """

    UNVERIFIED = "UNVERIFIED"
    FAILED = "FAILED"
    COMPUTATION_REPRODUCED = "COMPUTATION_REPRODUCED"
    NUMERICALLY_CROSS_CHECKED = "NUMERICALLY_CROSS_CHECKED"
    SYMBOLICALLY_VERIFIED = "SYMBOLICALLY_VERIFIED"
    DIMENSIONALLY_VERIFIED = "DIMENSIONALLY_VERIFIED"
    INDEPENDENTLY_VERIFIED = "INDEPENDENTLY_VERIFIED"


#: Statuses that count as a positive result. ``FAILED`` and ``UNVERIFIED`` do not.
PASSING_STATUSES: frozenset[VerificationStatus] = frozenset(
    {
        VerificationStatus.COMPUTATION_REPRODUCED,
        VerificationStatus.NUMERICALLY_CROSS_CHECKED,
        VerificationStatus.SYMBOLICALLY_VERIFIED,
        VerificationStatus.DIMENSIONALLY_VERIFIED,
        VerificationStatus.INDEPENDENTLY_VERIFIED,
    }
)

#: Statuses that required at least two distinct methods to agree.
INDEPENDENT_STATUSES: frozenset[VerificationStatus] = frozenset(
    {VerificationStatus.INDEPENDENTLY_VERIFIED}
)

#: Statuses strong enough to stand in for a worked numerical problem.
WORKED_STATUSES: frozenset[VerificationStatus] = frozenset(
    {
        VerificationStatus.NUMERICALLY_CROSS_CHECKED,
        VerificationStatus.SYMBOLICALLY_VERIFIED,
        VerificationStatus.DIMENSIONALLY_VERIFIED,
        VerificationStatus.INDEPENDENTLY_VERIFIED,
    }
)


@dataclass(frozen=True)
class VerificationResult:
    """One verification attempt with full provenance and its limits."""

    status: VerificationStatus
    method: str
    detail: str = ""
    inputs: dict[str, object] = field(default_factory=dict)
    outputs: dict[str, object] = field(default_factory=dict)
    assumptions: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    methods_used: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.status in PASSING_STATUSES

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "method": self.method,
            "detail": self.detail,
            "inputs": dict(self.inputs),
            "outputs": dict(self.outputs),
            "assumptions": list(self.assumptions),
            "limitations": list(self.limitations),
            "methods_used": list(self.methods_used),
            "ok": self.ok,
        }


def combine(method_results: list[VerificationResult]) -> VerificationResult:
    """Combine several methods over the same claim into one status.

    Two or more distinct passing methods become ``INDEPENDENTLY_VERIFIED``. A
    single passing method keeps its own status. Any failure dominates: if one
    method finds a counterexample, the combined result is ``FAILED``.
    """

    if not method_results:
        return VerificationResult(
            status=VerificationStatus.UNVERIFIED,
            method="combine",
            detail="no method was run",
        )
    failed = [result for result in method_results if result.status is VerificationStatus.FAILED]
    if failed:
        return VerificationResult(
            status=VerificationStatus.FAILED,
            method="combine",
            detail="; ".join(result.detail for result in failed if result.detail) or "a method failed",
            methods_used=tuple(result.method for result in method_results),
            limitations=tuple(
                limitation for result in method_results for limitation in result.limitations
            ),
        )
    passing = [result for result in method_results if result.ok]
    distinct = {result.method for result in passing}
    if len(distinct) >= 2:
        strongest = max(passing, key=lambda result: _RANK[result.status])
        return VerificationResult(
            status=VerificationStatus.INDEPENDENTLY_VERIFIED,
            method="combine",
            detail=f"independent methods agree: {', '.join(sorted(distinct))}",
            outputs=dict(strongest.outputs),
            assumptions=tuple(dict.fromkeys(a for r in passing for a in r.assumptions)),
            limitations=tuple(dict.fromkeys(x for r in passing for x in r.limitations)),
            methods_used=tuple(sorted(distinct)),
        )
    if passing:
        return passing[0]
    return VerificationResult(
        status=VerificationStatus.UNVERIFIED,
        method="combine",
        detail="no method could decide the claim",
        methods_used=tuple(result.method for result in method_results),
    )


_RANK: dict[VerificationStatus, int] = {
    VerificationStatus.UNVERIFIED: 0,
    VerificationStatus.COMPUTATION_REPRODUCED: 1,
    VerificationStatus.NUMERICALLY_CROSS_CHECKED: 2,
    VerificationStatus.SYMBOLICALLY_VERIFIED: 3,
    VerificationStatus.DIMENSIONALLY_VERIFIED: 4,
    VerificationStatus.INDEPENDENTLY_VERIFIED: 5,
    VerificationStatus.FAILED: -1,
}
