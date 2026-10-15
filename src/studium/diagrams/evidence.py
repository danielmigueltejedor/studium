"""Verification evidence for a diagram, kept apart from the drawing.

Each check names one category. The categories are not interchangeable:

* ``symbolic``: exact algebra (rational arithmetic or SymPy identities).
* ``numeric``: an independent numeric computation agreed within a tolerance.
* ``dimensional``: units or a scaling test agree.
* ``representation``: the drawn coordinates and labels match the stored data.
* ``visual``: a person or an agent looked at the rendered picture. This is an
  attestation, not a proof.
* ``not_machine_checkable``: the author declared that no machine check exists.

The headline status is derived from the checks, never stored by hand.
"""

from dataclasses import dataclass, field

CATEGORIES = ("symbolic", "numeric", "dimensional", "representation", "visual", "not_machine_checkable")

#: Headline statuses, most severe first.
STATUSES = (
    "verification_failed",
    "stale",
    "mathematically_verified",
    "numerically_checked",
    "dimensionally_consistent",
    "visually_inspected",
    "not_machine_checkable",
    "unverified",
)

STATUS_TEXT = {
    "verification_failed": "At least one check failed. The diagram does not represent consistent mathematics.",
    "stale": "The data the diagram was drawn from changed. Regenerate and check it again.",
    "mathematically_verified": "Exact checks passed and the drawing matches the stored functions.",
    "numerically_checked": "Independent numeric checks passed; no exact proof was run.",
    "dimensionally_consistent": "Only units or scaling were checked.",
    "visually_inspected": "Only a visual inspection was recorded. That is not a mathematical check.",
    "not_machine_checkable": "The author declared that no machine check applies.",
    "unverified": "Nothing was checked.",
}


@dataclass(frozen=True)
class Check:
    """One verification step. ``residual`` is the measured disagreement, if any."""

    name: str
    category: str
    passed: bool
    detail: str = ""
    residual: str | None = None

    def __post_init__(self) -> None:
        if self.category not in CATEGORIES:
            raise ValueError(f"unknown check category {self.category!r}")

    def as_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "name": self.name,
            "category": self.category,
            "passed": self.passed,
            "detail": self.detail,
        }
        if self.residual is not None:
            data["residual"] = self.residual
        return data


@dataclass
class Evidence:
    """Ordered checks for one diagram or one structural solution."""

    checks: list[Check] = field(default_factory=list)

    def add(self, name: str, category: str, passed: bool, detail: str = "", residual: object = None) -> bool:
        self.checks.append(
            Check(name, category, bool(passed), detail, None if residual is None else str(residual))
        )
        return bool(passed)

    def extend(self, other: "Evidence") -> None:
        self.checks.extend(other.checks)

    @property
    def failed(self) -> list[Check]:
        return [check for check in self.checks if not check.passed]

    def summary(self, *, stale: bool = False) -> dict[str, object]:
        return summarize([check.as_dict() for check in self.checks], stale=stale)


def summarize(checks: list[dict[str, object]], *, stale: bool = False) -> dict[str, object]:
    """Headline status plus one flag per category.

    ``mathematically_verified`` needs at least one passed symbolic check, no
    failure, and, when a drawing exists (any representation check), a passed
    representation check. A visual attestation never raises the status above
    ``visually_inspected``.
    """

    passed = dict.fromkeys(CATEGORIES, False)
    failed: list[str] = []
    counts = dict.fromkeys(CATEGORIES, 0)
    has_representation = False
    for item in checks:
        category = str(item.get("category"))
        if category not in counts:
            continue
        counts[category] += 1
        if category == "representation":
            has_representation = True
        if item.get("passed") is True:
            passed[category] = True
        else:
            failed.append(str(item.get("name")))
    if stale:
        status = "stale"
    elif failed:
        status = "verification_failed"
    elif passed["symbolic"] and (passed["representation"] or not has_representation):
        status = "mathematically_verified"
    elif passed["numeric"]:
        status = "numerically_checked"
    elif passed["dimensional"]:
        status = "dimensionally_consistent"
    elif passed["visual"]:
        status = "visually_inspected"
    elif passed["not_machine_checkable"]:
        status = "not_machine_checkable"
    else:
        status = "unverified"
    flags = {
        "mathematically_verified": status == "mathematically_verified",
        "numerically_checked": passed["numeric"] and not failed,
        "dimensionally_consistent": passed["dimensional"] and not failed,
        "representation_matches_data": passed["representation"] and not failed,
        "visually_inspected": passed["visual"],
    }
    return {
        "status": status,
        "text": STATUS_TEXT[status],
        "flags": flags,
        "failed": failed,
        "counts": counts,
    }
