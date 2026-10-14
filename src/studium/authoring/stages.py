"""The separate stages between a draft and a publishable book.

A draft that renders, an evidence audit that passed, scientific verification
of the mathematics, human academic approval, and publication readiness are
different facts. Each stage reports its own status; none implies the next.
"""

from pathlib import Path

from studium.storage.records import REVIEWS, fold_by_id


def verification_stages(root: Path, math_grounding: dict[str, object]) -> dict[str, object]:
    """Report the five stages from stored records and the equation evidence summary."""

    from studium.authoring.contradictions import review_is_current

    review = next((item for item in fold_by_id(root / REVIEWS) if item.get("id") == "edition"), None)
    if review is None:
        audit_status = "not_run"
    elif not review_is_current(root):
        audit_status = "stale"
    else:
        audit_status = "passed" if review.get("audit_passed") is True else "blocked"
    claims = _int(math_grounding.get("claims"))
    verified = _int(math_grounding.get("claims_verified"))
    by_status = math_grounding.get("by_status")
    counts = by_status if isinstance(by_status, dict) else {}
    unresolved = math_grounding.get("unresolved_important")
    important = len(unresolved) if isinstance(unresolved, list) else 0
    science_complete = claims == verified
    reasons: list[str] = []
    if audit_status != "passed":
        reasons.append(f"evidence audit is {audit_status}")
    if not science_complete:
        reasons.append(f"scientific verification is incomplete: {verified} of {claims} equation claims verified")
    reasons.append("no human academic approval is recorded")
    return {
        "draft": {"status": "renderable", "note": "a draft renders even with unverified mathematics"},
        "evidence_audit": {"status": audit_status},
        "scientific_verification": {
            "status": "complete" if science_complete else "incomplete",
            "claims": claims,
            "verified": verified,
            "not_machine_checkable": _int(counts.get("not_machine_checkable")),
            "unsupported": _int(counts.get("unsupported")),
            "contradicted_or_failed": _int(counts.get("contradicted")) + _int(counts.get("verification_failed")),
            "unresolved_important_equations": important,
        },
        "human_approval": {"status": "not_recorded"},
        "publication_ready": {"ready": False, "reasons": reasons},
    }


def _int(value: object) -> int:
    return value if isinstance(value, int) else 0
