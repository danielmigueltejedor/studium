"""Mathematical derivation records and deterministic verification.

A derivation is stored as structured metadata: starting assumptions, governing
principles, intermediate steps, the final equation, variable definitions and
units, boundary conditions, applicability, limitations, and supporting
references. ``check_derivation`` runs the deterministic checks the recorded
metadata supports (symbolic identities, numeric substitution, dimensional
analysis) and preserves the Part 7 status distinction. A symbolic
simplification is never reported as a physical proof.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import NamedTuple

from studium.authoring.blueprint import current_sections
from studium.authoring.excerpts import excerpts_by_id
from studium.authoring.mathematics import MathError, symbol_names_of, validate_latex
from studium.policy.trust import directive_changes_policy
from studium.storage.init_project import load_state_holding_lock
from studium.storage.locking import ProjectLocked, project_lock
from studium.storage.migrate import utc_now
from studium.storage.records import DERIVATIONS, allocate_id, append_jsonl, fold_by_id
from studium.verification.engine import (
    proportional,
    verify_algebraic_equivalence,
    verify_dimensions,
    verify_equation,
    verify_substitution,
)
from studium.verification.model import VerificationResult, VerificationStatus, combine

_MAX_LINE = 500
_MAX_STEPS = 30
_MAX_ENTRIES = 30
_MAX_VARIABLES = 50
_AUDIT = "audit/audit.jsonl"

VERIFICATION_STATUSES = frozenset(
    {
        "COMPUTATION_REPRODUCED",
        "SYMBOLICALLY_VERIFIED",
        "DIMENSIONALLY_VERIFIED",
        "INDEPENDENTLY_VERIFIED",
        "ACADEMICALLY_REVIEWED",
        "UNVERIFIED",
        "FAILED",
    }
)

_HEAD = frozenset(
    {"assumptions", "governing_principles", "steps", "boundary_conditions", "applicability", "limitations"}
)
_REFERENCE_KINDS = frozenset({"excerpts", "sources"})


class _SymbolicIdentity(NamedTuple):
    left: str
    right: str
    solution: dict[str, str] | None


class _NumericCheck(NamedTuple):
    expression: str
    values: dict[str, float]
    claimed: float


class _DimensionalCheck(NamedTuple):
    expression: str
    symbol_units: dict[str, str]
    expected_unit: str | None


def record_derivation(
    root: Path,
    *,
    section: object,
    name: object,
    equation: object,
    equation_id: object = None,
    assumptions: object = None,
    governing_principles: object = None,
    steps: object = None,
    steps_latex: object = None,
    symbolic: object = None,
    variables: object = None,
    boundary_conditions: object = None,
    applicability: object = None,
    limitations: object = None,
    references: object = None,
    actor: dict[str, object] | None = None,
) -> dict[str, object]:
    """Store one structured derivation for a blueprint section."""

    section_id, section_error = _section(root, section)
    if section_error is not None:
        return section_error
    cleaned_name, name_error = _line(name, "name")
    if name_error is not None:
        return name_error
    cleaned_equation, equation_error = _line(equation, "equation")
    if equation_error is not None:
        return equation_error
    if directive_changes_policy(_safe_join([cleaned_name or "", cleaned_equation or ""])):
        return _error("policy.overridden", "derivation text changed policy")
    identifier, id_error = _optional_line(equation_id, "equation_id", 128)
    if id_error is not None:
        return id_error
    paragraphs: dict[str, list[str]] = {}
    assumptions_list, error = _lines(assumptions, "assumptions")
    if error is not None:
        return error
    if assumptions_list:
        paragraphs["assumptions"] = assumptions_list
    principles, error = _lines(governing_principles, "governing_principles")
    if error is not None:
        return error
    if principles:
        paragraphs["governing_principles"] = principles
    steps_list, error = _lines(steps, "steps")
    if error is not None:
        return error
    if steps_list:
        paragraphs["steps"] = steps_list
    steps_tex, error = _latex_lines(steps_latex, "steps_latex")
    if error is not None:
        return error
    symbolic_tex, error = _symbolic_line(symbolic, "symbolic")
    if error is not None:
        return error
    boundaries, error = _lines(boundary_conditions, "boundary_conditions")
    if error is not None:
        return error
    if boundaries:
        paragraphs["boundary_conditions"] = boundaries
    uses, error = _lines(applicability, "applicability")
    if error is not None:
        return error
    if uses:
        paragraphs["applicability"] = uses
    limits, error = _lines(limitations, "limitations")
    if error is not None:
        return error
    if limits:
        paragraphs["limitations"] = limits
    variables_map, error = _variables(variables)
    if error is not None:
        return error
    references_map, error = _references(root, references)
    if error is not None:
        return error
    try:
        with project_lock(root):
            record: dict[str, object] = {
                "schema_version": "1.0.0",
                "id": allocate_id(root, "DER"),
                "section": section_id,
                "name": cleaned_name,
                "equation": cleaned_equation,
                "status": "recorded",
                "verification": {"status": "UNVERIFIED", "checks": []},
                "recorded_at": utc_now(),
            }
            if identifier is not None:
                record["equation_id"] = identifier
            for key, values in paragraphs.items():
                record[key] = values
            if steps_tex:
                record["steps_latex"] = steps_tex
            if symbolic_tex is not None:
                record["symbolic"] = symbolic_tex
            if variables_map:
                record["variables"] = variables_map
            if references_map:
                record["references"] = references_map
            append_jsonl(root / DERIVATIONS, record)
            fresh = load_state_holding_lock(root)
            return _body(fresh, record, status="recorded")
    except ProjectLocked:
        return _error("storage.locked", "project is locked")


def remove_derivation(
    root: Path,
    derivation_id: object,
    *,
    actor: dict[str, object] | None = None,
) -> dict[str, object]:
    """Delete one stored derivation. Sources, paragraphs, and excerpts stay.

    A missing id is an error. This does not change project state and does not
    release the book.
    """

    identifier = _derivation_id(derivation_id)
    if identifier is None:
        return _error("mcp.invalid_input", "id is required")
    current = _find(root, identifier)
    if current is None:
        return _error("derivation.not_found", "no stored derivation with that id")
    try:
        with project_lock(root):
            again = _find(root, identifier)
            if again is None:
                return _error("derivation.not_found", "no stored derivation with that id")
            append_jsonl(
                root / DERIVATIONS,
                {
                    "schema_version": "1.0.0",
                    "id": identifier,
                    "deleted": True,
                    "recorded_at": utc_now(),
                },
            )
            _audit(root, record=again, actor=actor, operation="remove_derivation")
            fresh = load_state_holding_lock(root)
    except ProjectLocked:
        return _error("storage.locked", "project is locked")
    return {
        "status": "removed",
        "derivation_id": identifier,
        "message": "The derivation is removed from the book. Sources, paragraphs, and excerpts are unchanged.",
        "released": fresh.get("state") == "RELEASED",
        "applied": False,
        "project_state": fresh.get("state"),
        "local_sources": _local(fresh),
    }


def check_derivation(
    root: Path,
    derivation_id: object,
    *,
    symbolic: object = None,
    numeric: object = None,
    dimensions: object = None,
    actor: dict[str, object] | None = None,
) -> dict[str, object]:
    """Run the deterministic checks requested for one derivation.

    ``symbolic`` ``{"left", "right"}`` or ``{"equation_left", "equation_right",
    "solution"}``; ``numeric`` ``{"expression", "values", "claimed"}``;
    ``dimensions`` ``{"expression", "symbol_units", "expected_unit"}``. Each
    check keeps its own status; the derivation status is the strongest honest
    combination of the checks that actually ran.
    """

    identifier = _derivation_id(derivation_id)
    if identifier is None:
        return _error("mcp.invalid_input", "id is required")
    current = _find(root, identifier)
    if current is None:
        return _error("derivation.not_found", "no stored derivation with that id")
    results: list[dict[str, object]] = []
    failed = False
    symbolic_identity, identity_error = _symbolic(symbolic)
    if identity_error is not None:
        return identity_error
    numeric_check, numeric_error = _numeric(numeric)
    if numeric_error is not None:
        return numeric_error
    dimensional_check, dimensional_error = _dimensions(dimensions)
    if dimensional_error is not None:
        return dimensional_error

    stored = _stored_relation(current)
    if symbolic_identity is not None:
        results.append(_result_payload("symbolic", _symbolic_result(stored, symbolic_identity)))
    if numeric_check is not None:
        results.append(_result_payload("numeric_substitution", _numeric_result(stored, numeric_check)))
    if dimensional_check is not None:
        results.append(_result_payload("dimensional", _dimensional_result(stored, dimensional_check, current)))
    if not results:
        return _error("mcp.invalid_input", "at least one of symbolic, numeric, or dimensions is required")
    for item in results:
        if item.get("status") in {"FAILED", "UNVERIFIED"}:
            failed = failed or item.get("status") == "FAILED"
    overall = _overall(results)
    updated = dict(current)
    verification: dict[str, object] = {"status": overall, "checks": results, "checked_at": utc_now()}
    if stored is not None:
        # The checks above were bound to this exact stored form; a later change of ``symbolic`` makes them stale.
        verification["bound_to"] = current.get("symbolic")
    updated["verification"] = verification
    try:
        with project_lock(root):
            append_jsonl(root / DERIVATIONS, updated)
            fresh = load_state_holding_lock(root)
    except ProjectLocked:
        return _error("storage.locked", "project is locked")
    return {
        "status": "checked",
        "derivation": _public(updated),
        "verification_status": overall,
        "failed": failed,
        "project_state": fresh.get("state"),
        "released": fresh.get("state") == "RELEASED",
    }


def list_derivations(root: Path) -> dict[str, object]:
    return {"status": "ok", "derivations": [_public(record) for record in fold_by_id(root / DERIVATIONS)]}


def derivations_for_section(root: Path, section_id: str) -> list[dict[str, object]]:
    return [record for record in fold_by_id(root / DERIVATIONS) if record.get("section") == section_id]


def _overall(results: list[dict[str, object]]) -> str:
    """The combined status of the checks that ran.

    Delegates to :func:`studium.verification.model.combine` so the derivation
    layer cannot drift from the verification layer: numeric substitution and
    dimensional agreement alone are corroboration, not independent proof.
    """

    verification: list[VerificationResult] = []
    for item in results:
        status = str(item.get("status"))
        if status not in VerificationStatus.__members__:
            continue
        verification.append(
            VerificationResult(
                status=VerificationStatus[status],
                method=str(item.get("method") or ""),
            )
        )
    return combine(verification).status.value


def _free_symbols(*texts: str) -> set[str]:
    """Identifier names in the given expressions that are not constants or functions.

    Declaring them does not weaken the check: the parser still applies its own
    allowlist and limits; it only tells the equation verifier which single
    letters are variables of this derivation.
    """

    from studium.verification.parser import CONSTANTS, FUNCTIONS

    reserved = frozenset(CONSTANTS) | frozenset(FUNCTIONS)
    names = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", " ".join(texts)))
    return {name for name in names if name not in reserved and not name.startswith("_")}


_NO_STORED_EQUATION = (
    "the derivation stores no symbolic final equation, so this check cannot be tied to it; "
    "record the derivation again with symbolic written as 'lhs = rhs'"
)


class _Relation(NamedTuple):
    """The stored final equation, both sides as plain expressions."""

    left: str
    right: str

    @property
    def residual(self) -> str:
        return f"({self.left}) - ({self.right})"

    def sides(self) -> list[str]:
        return [side for side in (self.left, self.right) if side.strip() != "0"]


def _stored_relation(record: dict[str, object]) -> _Relation | None:
    """The stored ``symbolic`` final equation. Without ``=`` it is a residual equal to zero."""

    symbolic = record.get("symbolic")
    if not isinstance(symbolic, str) or not symbolic.strip():
        return None
    sides = [side.strip().replace("^", "**") for side in symbolic.split("=")]
    if len(sides) == 1:
        return _Relation(sides[0], "0")
    if len(sides) == 2 and all(sides):
        return _Relation(sides[0], sides[1])
    return None


def _unbound(method: str, detail: str, inputs: dict[str, object]) -> VerificationResult:
    return VerificationResult(status=VerificationStatus.UNVERIFIED, method=method, detail=detail, inputs=inputs)


def _is_side(expression: str, stored: _Relation, *, up_to_factor: bool = False) -> bool:
    """Whether ``expression`` is one side of the stored equation (or a constant multiple of one)."""

    candidate = expression.replace("^", "**")
    for side in stored.sides():
        if up_to_factor:
            if proportional(candidate, side):
                return True
        elif proportional(f"({candidate}) - ({side})", "0"):
            return True
    return False


def _symbolic_result(stored: _Relation | None, check: _SymbolicIdentity) -> VerificationResult:
    left = check.left.replace("^", "**")
    right = check.right.replace("^", "**")
    inputs: dict[str, object] = {"left": left, "right": right}
    if stored is None:
        return _unbound("symbolic", _NO_STORED_EQUATION, inputs)
    if check.solution is None:
        # An identity says something about the derivation only if it rewrites one of its sides.
        if not (_is_side(left, stored) or _is_side(right, stored)):
            return _unbound(
                "symbolic",
                "neither side of this identity is a side of the stored final equation; it says nothing about it",
                inputs,
            )
        return verify_algebraic_equivalence(left, right)
    solution = {name: value.replace("^", "**") for name, value in check.solution.items()}
    inputs["solution"] = solution
    stored_names = _free_symbols(stored.left, stored.right)
    if not stored_names & set(solution):
        return _unbound(
            "symbolic",
            "the solution substitutes no symbol of the stored final equation; it says nothing about it",
            inputs,
        )
    if proportional(f"({left}) - ({right})", stored.residual):
        return _unbound(
            "symbolic",
            "circular: the premise is the stored final equation itself; give the relation it was derived from",
            inputs,
        )
    premise = verify_equation(left, right, solution=solution, symbols=_free_symbols(left, right, *solution.values()))
    if premise.status is not VerificationStatus.SYMBOLICALLY_VERIFIED:
        return premise
    mentioned = _free_symbols(left, right, *solution.values()) | set(solution)
    unmentioned = sorted(stored_names - mentioned)
    if unmentioned:
        # A stored symbol the premise and the solution never mention is not constrained by them: the
        # substituted equation then cannot be falsified, only left undecided.
        return _unbound(
            "symbolic",
            "the stored final equation uses symbols the premise and solution never mention ("
            + ", ".join(unmentioned)
            + "); the check cannot decide it",
            inputs,
        )
    consequence = verify_equation(
        stored.left,
        stored.right,
        solution=solution,
        symbols=_free_symbols(stored.left, stored.right, *solution.values()),
    )
    if consequence.status is VerificationStatus.FAILED:
        return VerificationResult(
            status=VerificationStatus.FAILED,
            method="symbolic_equation",
            detail="the solution satisfies the premise but not the stored final equation: " + consequence.detail,
            inputs=inputs,
        )
    if consequence.status is not VerificationStatus.SYMBOLICALLY_VERIFIED:
        return consequence
    return VerificationResult(
        status=VerificationStatus.SYMBOLICALLY_VERIFIED,
        method="symbolic_equation",
        detail="the solution satisfies the premise and the stored final equation",
        inputs=inputs,
        limitations=(
            "the premise is the client's; the check shows the stored equation follows from it, not that it is physical",
        ),
    )


def _numeric_result(stored: _Relation | None, check: _NumericCheck) -> VerificationResult:
    inputs: dict[str, object] = {"expression": check.expression, "values": dict(check.values), "claimed": check.claimed}
    if stored is None:
        return _unbound("numeric_substitution", _NO_STORED_EQUATION, inputs)
    if not _is_side(check.expression, stored):
        return _unbound(
            "numeric_substitution",
            "the expression is not a side of the stored final equation; replaying it says nothing about it",
            inputs,
        )
    return verify_substitution(check.expression.replace("^", "**"), values=check.values, claimed=check.claimed)


def _variable_units(record: dict[str, object]) -> dict[str, str]:
    variables = record.get("variables")
    found: dict[str, str] = {}
    if isinstance(variables, dict):
        for name, entry in variables.items():
            if isinstance(name, str) and isinstance(entry, dict) and isinstance(entry.get("units"), str):
                found[name] = str(entry["units"])
    return found


def _dimensional_result(
    stored: _Relation | None,
    check: _DimensionalCheck,
    record: dict[str, object],
) -> VerificationResult:
    """Dimensional homogeneity of the stored final equation, every side and every term."""

    units = {**_variable_units(record), **check.symbol_units}
    inputs: dict[str, object] = {"expression": check.expression, "symbol_units": units, "expected_unit": check.expected_unit}
    if stored is None:
        return _unbound("dimensional", _NO_STORED_EQUATION, inputs)
    if check.expression.strip() and not _is_side(check.expression, stored, up_to_factor=True):
        return _unbound(
            "dimensional",
            "the expression is not a side of the stored final equation; its units say nothing about it",
            inputs,
        )
    missing = sorted(_free_symbols(stored.left, stored.right) - set(units))
    if missing:
        return _unbound("dimensional", "no units for " + ", ".join(missing) + " in symbol_units or the stored variables", inputs)
    sides = stored.sides()
    results = [verify_dimensions(side, units, expected_unit=check.expected_unit) for side in sides]
    failed = next((result for result in results if result.status is not VerificationStatus.DIMENSIONALLY_VERIFIED), None)
    if failed is not None:
        return failed
    reduced = {
        tuple(sorted(dict(result.outputs.get("dimensionality") or {}).items()))  # type: ignore[arg-type]
        for result in results
    }
    if len(reduced) > 1:
        return VerificationResult(
            status=VerificationStatus.FAILED,
            method="dimensional",
            detail="the two sides of the stored final equation have different dimensions",
            inputs=inputs,
        )
    return VerificationResult(
        status=VerificationStatus.DIMENSIONALLY_VERIFIED,
        method="dimensional",
        detail="every term of the stored final equation has the same dimensions: " + results[0].detail,
        inputs=inputs,
        limitations=("dimensionally consistent does not mean physically correct",),
    )


def _result_payload(method: str, result: object) -> dict[str, object]:
    status = str(getattr(result, "status", "UNVERIFIED"))
    detail = str(getattr(result, "detail", ""))
    return {
        "method": method,
        "status": status.split(".")[-1],
        "detail": detail,
        "inputs": getattr(result, "inputs", None),
    }


def _symbolic(value: object) -> tuple[_SymbolicIdentity | None, dict[str, object] | None]:
    if value is None:
        return None, None
    if not isinstance(value, dict):
        return None, _error("mcp.invalid_input", "symbolic must be an object with left/right or equation_left/equation_right/solution")
    if "left" in value and "right" in value:
        left, right = value.get("left"), value.get("right")
        if not isinstance(left, str) or not isinstance(right, str) or not left.strip() or not right.strip():
            return None, _error("mcp.invalid_input", "symbolic left and right must be expressions")
        return _SymbolicIdentity(left.strip(), right.strip(), None), None
    left = value.get("equation_left")
    right = value.get("equation_right")
    solution = value.get("solution")
    if not isinstance(left, str) or not isinstance(right, str) or not isinstance(solution, dict):
        return None, _error("mcp.invalid_input", "symbolic equation check needs equation_left, equation_right, and solution")
    cleaned_solution: dict[str, str] = {}
    for name, item in solution.items():
        if not isinstance(name, str) or not isinstance(item, str):
            return None, _error("mcp.invalid_input", "solution values must be strings")
        cleaned_solution[name] = item
    return _SymbolicIdentity(left, right, cleaned_solution), None


def _numeric(value: object) -> tuple[_NumericCheck | None, dict[str, object] | None]:
    if value is None:
        return None, None
    if not isinstance(value, dict):
        return None, _error("mcp.invalid_input", "numeric must be an object with expression, values, claimed")
    expression = value.get("expression")
    values = value.get("values")
    claimed = value.get("claimed")
    if not isinstance(expression, str) or not expression.strip() or not isinstance(values, dict):
        return None, _error("mcp.invalid_input", "numeric needs an expression and a substitution dict")
    try:
        claimed_number = float(str(claimed))
    except ValueError:
        return None, _error("mcp.invalid_input", "numeric claimed must be a number")
    cleaned_values: dict[str, float] = {}
    for name, item in values.items():
        try:
            cleaned_values[str(name)] = float(str(item))
        except ValueError:
            return None, _error("mcp.invalid_input", "numeric values must be numbers")
    return _NumericCheck(expression, cleaned_values, claimed_number), None


def _dimensions(value: object) -> tuple[_DimensionalCheck | None, dict[str, object] | None]:
    if value is None:
        return None, None
    if not isinstance(value, dict):
        return None, _error("mcp.invalid_input", "dimensions must be an object with expression and symbol_units")
    expression = value.get("expression", "")
    symbol_units = value.get("symbol_units", {})
    if not isinstance(expression, str) or not isinstance(symbol_units, dict):
        return None, _error("mcp.invalid_input", "dimensions needs symbol_units and an optional expression")
    cleaned: dict[str, str] = {}
    for name, item in symbol_units.items():
        if not isinstance(name, str) or not isinstance(item, str) or not item.strip():
            return None, _error("mcp.invalid_input", "symbol_units values must be unit strings")
        cleaned[name] = item
    expected = value.get("expected_unit")
    if expected is not None and not isinstance(expected, str):
        return None, _error("mcp.invalid_input", "expected_unit must be a unit string")
    return _DimensionalCheck(expression, cleaned, expected), None


def _section(root: Path, value: object) -> tuple[str | None, dict[str, object] | None]:
    if not isinstance(value, str) or not value.strip():
        return None, _error("mcp.invalid_input", "section must be a blueprint section id")
    identifier = value.strip()
    known = {section["id"] for section in current_sections(root)}
    if identifier not in known:
        return None, _error("derivation.section_unknown", "section is not in the stored blueprint")
    return identifier, None


def _line(value: object, field: str) -> tuple[str | None, dict[str, object] | None]:
    if not isinstance(value, str):
        return None, _error("mcp.invalid_input", f"{field} is required")
    cleaned = value.strip()
    if not cleaned or len(cleaned) > _MAX_LINE or "\n" in cleaned or "\r" in cleaned:
        return None, _error("mcp.invalid_input", f"{field} must be one line")
    return cleaned, None


def _optional_line(value: object, field: str, limit: int) -> tuple[str | None, dict[str, object] | None]:
    if value is None:
        return None, None
    if not isinstance(value, str):
        return None, _error("mcp.invalid_input", f"{field} must be one line")
    cleaned = value.strip()
    if not cleaned or len(cleaned) > limit or "\n" in cleaned or "\r" in cleaned:
        return None, _error("mcp.invalid_input", f"{field} must be one line")
    return cleaned, None


def _lines(value: object, field: str) -> tuple[list[str] | None, dict[str, object] | None]:
    if value is None:
        return [], None
    if not isinstance(value, list) or len(value) > _MAX_ENTRIES:
        return None, _error("mcp.invalid_input", f"{field} must be a list of short lines")
    cleaned: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip() or len(item) > _MAX_LINE:
            return None, _error("mcp.invalid_input", f"{field} entries must be short lines")
        cleaned.append(item.strip())
    return cleaned, None


def _latex_lines(value: object, field: str) -> tuple[list[str] | None, dict[str, object] | None]:
    if value is None:
        return [], None
    if not isinstance(value, list) or len(value) > _MAX_ENTRIES:
        return None, _error("mcp.invalid_input", f"{field} must be a list of short LaTeX lines")
    cleaned: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip() or len(item) > _MAX_LINE:
            return None, _error("mcp.invalid_input", f"{field} entries must be short LaTeX lines")
        stripped = item.strip()
        problems = validate_latex(stripped)
        if problems:
            return None, _error("mcp.invalid_input", f"{field} has invalid LaTeX: " + "; ".join(problems))
        cleaned.append(stripped)
    return cleaned, None


def _symbolic_line(value: object, field: str) -> tuple[str | None, dict[str, object] | None]:
    if value is None:
        return None, None
    if not isinstance(value, str) or not value.strip() or len(value) > _MAX_LINE:
        return None, _error("mcp.invalid_input", f"{field} must be one symbolic line")
    cleaned = value.strip()
    sides = cleaned.split("=")
    if len(sides) > 2:
        return None, _error("mcp.invalid_input", f"{field} may hold at most one '=': write the final equation as lhs = rhs")
    try:
        for side in sides:
            symbol_names_of(side)
    except MathError as exc:
        return None, _error("mcp.invalid_input", f"{field} is not a valid symbolic expression: {exc}")
    return " = ".join(side.strip() for side in sides), None


def _variables(value: object) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    if value is None:
        return None, None
    if not isinstance(value, dict) or not value or len(value) > _MAX_VARIABLES:
        return None, _error("mcp.invalid_input", "variables must be an object of symbol descriptions")
    cleaned: dict[str, object] = {}
    for name, description in value.items():
        if not isinstance(name, str) or not name or len(name) > 40:
            return None, _error("mcp.invalid_input", "variable names must be short strings")
        if isinstance(description, str):
            cleaned[name] = {"meaning": description.strip()}
            continue
        if not isinstance(description, dict):
            return None, _error("mcp.invalid_input", "variable descriptions need a meaning and optional units")
        meaning = description.get("meaning")
        units = description.get("units")
        if not isinstance(meaning, str) or not meaning.strip() or len(meaning) > _MAX_LINE:
            return None, _error("mcp.invalid_input", f"variable {name} needs a meaning line")
        entry: dict[str, object] = {"meaning": meaning.strip()}
        if isinstance(units, str) and units.strip():
            entry["units"] = units.strip()
        cleaned[name] = entry
    return cleaned, None


def _describe(value: object) -> str:
    """A short description of a value's type for a validation error."""

    if isinstance(value, list):
        return f"a list of {len(value)} item(s)"
    if isinstance(value, dict):
        return "an object"
    if value is None:
        return "null"
    return f"a {type(value).__name__}"


def _references(root: Path, value: object) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    if value is None:
        return None, None
    if not isinstance(value, dict):
        return None, _error(
            "mcp.invalid_input",
            'references must be an object like {"excerpts": ["EVD-0001"], "sources": ["SRC-0001"]}; '
            f"received {_describe(value)}",
        )
    unknown = set(value) - _REFERENCE_KINDS
    if unknown:
        allowed = ", ".join(sorted(_REFERENCE_KINDS))
        return None, _error(
            "mcp.invalid_input",
            f"references may only carry {allowed}; unknown key(s): {', '.join(sorted(str(key) for key in unknown))}",
        )
    stored = excerpts_by_id(root)
    cleaned: dict[str, object] = {}
    excerpts_value = value.get("excerpts")
    if excerpts_value is not None:
        ids, error = _references_ids(excerpts_value, "excerpts")
        if error is not None:
            return None, error
        for excerpt_id in ids:
            if excerpt_id not in stored:
                return None, _error(
                    "derivation.excerpt_unknown",
                    f"excerpt id {excerpt_id!r} is not stored; record it with studium_excerpt_record first",
                )
        if ids:
            cleaned["excerpts"] = ids
    sources_value = value.get("sources")
    if sources_value is not None:
        ids, error = _references_ids(sources_value, "sources")
        if error is not None:
            return None, error
        if ids:
            cleaned["sources"] = ids
    return cleaned or None, None


def _references_ids(value: object, field: str) -> tuple[list[str], dict[str, object] | None]:
    if not isinstance(value, list) or len(value) > _MAX_ENTRIES:
        return [], _error(
            "mcp.invalid_input",
            f"{field} must be a list of at most {_MAX_ENTRIES} stored id strings; received {_describe(value)}",
        )
    identifiers: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip() or len(item.strip()) > 128:
            return [], _error(
                "mcp.invalid_input",
                f"each {field} id must be a non-empty string of at most 128 characters",
            )
        cleaned = item.strip()
        if cleaned not in identifiers:
            identifiers.append(cleaned)
    return identifiers, None


def _public(record: dict[str, object]) -> dict[str, object]:
    visible: dict[str, object] = {
        "id": record.get("id"),
        "section": record.get("section"),
        "name": record.get("name"),
        "equation": record.get("equation"),
        "status": record.get("status"),
    }
    for key in (
        "equation_id",
        "assumptions",
        "governing_principles",
        "steps",
        "steps_latex",
        "symbolic",
        "boundary_conditions",
        "applicability",
        "limitations",
        "references",
    ):
        if record.get(key) is not None:
            visible[key] = record.get(key)
    if isinstance(record.get("variables"), dict):
        visible["variables"] = record["variables"]
    verification = record.get("verification")
    if isinstance(verification, dict):
        visible["verification"] = verification
    return visible


def _body(state: dict[str, object], record: dict[str, object], *, status: str) -> dict[str, object]:
    return {
        "status": status,
        "derivation": _public(record),
        "local_sources": _local(state),
        "project_state": state.get("state"),
        "released": state.get("state") == "RELEASED",
    }


def _derivation_id(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned or len(cleaned) > 128:
        return None
    return cleaned


def _audit(
    root: Path,
    *,
    record: dict[str, object],
    actor: dict[str, object] | None,
    operation: str,
) -> None:
    digest = hashlib.sha256(str(record.get("equation", "")).encode("utf-8")).hexdigest()
    append_jsonl(
        root / _AUDIT,
        {
            "schema_version": "1.0.0",
            "timestamp": utc_now(),
            "source_id": record.get("id"),
            "operation": operation,
            "origin": None,
            "actor": {"kind": actor.get("kind")} if isinstance(actor, dict) and isinstance(actor.get("kind"), str) else None,
            "previous_hash": None,
            "new_hash": digest,
            "result": record.get("status"),
            "tool": operation,
        },
    )


def _find(root: Path, identifier: str) -> dict[str, object] | None:
    return next((record for record in fold_by_id(root / DERIVATIONS) if record.get("id") == identifier), None)


def _safe_join(lines: list[str]) -> str:
    return "\n".join(lines)


def _local(state: dict[str, object]) -> dict[str, object]:
    local = state.get("local_sources")
    if isinstance(local, dict):
        return dict(local)
    return {"status": "UNKNOWN", "prompted": False, "source_count": 0}


def _error(code: str, message: str) -> dict[str, object]:
    return {"status": code, "message": message}
