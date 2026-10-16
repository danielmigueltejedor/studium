"""Explicit scientific contracts over the existing bounded SymPy/Pint engine.

These checks concern author-declared mathematics and conditions. They cannot
establish that a predicate faithfully represents the world or the prose.
"""

from __future__ import annotations

import ast
import json
from typing import Any

import sympy

from studium.verification.engine import (
    _definitely_nonzero,
    _run_bounded,
    verify_dimensions,
)
from studium.verification.parser import parse_expression

MODEL_REQUIREMENTS = {
    "bernoulli_simple": (
        "steady",
        "incompressible",
        "inviscid",
        "same_streamline",
        "no_losses",
        "no_shaft_work",
    ),
    "steady_stokes": ("small_reynolds", "negligible_unsteady_inertia"),
}
_ROLES = {"theory", "derivation", "example", "self_check", "problem", "solution", "appendix"}
_FIELDS = {
    "identity": {"left", "right"},
    "dimensions": {"expression", "expected_unit"},
    "defined": {"expression"},
    "limit": {"expression", "variable", "point", "claimed"},
    "gradient": {"coordinates", "components"},
    "model": {"model"},
}
_CATEGORIES = {
    "identity": "symbolic",
    "dimensions": "dimensions",
    "defined": "domain",
    "limit": "symbolic",
    "gradient": "model",
    "model": "model",
}


def _text(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 1000:
        raise ValueError("expected a nonempty bounded string")
    return value.strip()


def _list(value: object) -> list[Any]:
    if not isinstance(value, list) or len(value) > 60:
        raise ValueError("expected a list with at most 60 entries")
    return value


def validate_contract(value: object) -> dict[str, Any]:
    """Reject unknown fields, unsafe expressions and cyclic definitions upfront."""
    if not isinstance(value, dict) or len(json.dumps(value)) > 100_000:
        raise ValueError("contract must be an object of at most 100000 characters")
    if set(value) - {"variables", "bindings", "assumptions", "equations", "derivations", "representations"}:
        raise ValueError("unknown contract field")
    data = json.loads(json.dumps(value))
    variables = data.get("variables")
    if not isinstance(variables, dict) or not variables or len(variables) > 40:
        raise ValueError("variables must declare 1 to 40 symbol units")
    for name, unit in variables.items():
        parse_expression(name, symbols=set(variables))
        _text(unit)
    names = set(variables)

    def expression(item: object) -> None:
        parse_expression(_text(item), symbols=names)

    bindings = data.setdefault("bindings", {})
    if not isinstance(bindings, dict) or set(bindings) - names:
        raise ValueError("bindings must map declared symbols to expressions")
    for item in bindings.values():
        expression(item)
    _bindings(data)
    assumptions = _list(data.setdefault("assumptions", []))
    identifiers = []
    for assumption in assumptions:
        if not isinstance(assumption, dict) or set(assumption) != {"id", "left", "relation", "right"}:
            raise ValueError("assumption needs id, left, relation, right")
        identifiers.append(_text(assumption["id"]))
        if assumption["relation"] not in ("eq", "ne", "gt", "ge", "lt", "le"):
            raise ValueError("unknown assumption relation")
        expression(assumption["left"])
        expression(assumption["right"])
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("duplicate assumption id")
    equations = _list(data.setdefault("equations", []))
    equation_ids = []
    for equation in equations:
        if not isinstance(equation, dict) or set(equation) != {"id", "left", "right"}:
            raise ValueError("equation needs id, left, right")
        equation_ids.append(_text(equation["id"]))
        expression(equation["left"])
        expression(equation["right"])
    if len(set(equation_ids)) != len(equation_ids):
        raise ValueError("duplicate equation id")
    for identifier in _list(data.setdefault("derivations", [])):
        _text(identifier)
    representations = _list(data.get("representations"))
    if not representations:
        raise ValueError("at least one representation is required")
    count = 0
    for representation in representations:
        if not isinstance(representation, dict) or set(representation) - {"record", "role", "requires", "checks"}:
            raise ValueError("unknown representation field")
        _text(representation.get("record"))
        if representation.get("role") not in _ROLES:
            raise ValueError("unknown representation role")
        for identifier in _list(representation.setdefault("requires", [])):
            _text(identifier)  # Unknown assumptions remain visible as missing hypotheses.
        checks = _list(representation.get("checks"))
        if not checks:
            raise ValueError("each representation needs checks")
        count += len(checks)
        for check in checks:
            if not isinstance(check, dict):
                raise ValueError("check must be an object")
            if set(check) == {"kind", "equation"} and check.get("kind") == "identity":
                equation = next((eq for eq in equations if eq["id"] == check["equation"]), None)
                if equation is None:
                    raise ValueError("unknown equation id")
                continue
            kind = check.get("kind")
            if not isinstance(kind, str) or kind not in _FIELDS or set(check) != {"kind", *_FIELDS[kind]}:
                raise ValueError("check fields do not match a supported kind")
            if kind == "gradient":
                coords, components = check["coordinates"], check["components"]
                if (
                    not isinstance(coords, list)
                    or len(coords) != 3
                    or len(set(coords)) != 3
                    or any(coord not in names for coord in coords)
                    or not isinstance(components, list)
                    or len(components) != 3
                ):
                    raise ValueError("gradient needs three distinct coordinates and components")
                if set(coords) & set(bindings):
                    raise ValueError("gradient coordinates cannot be bound before differentiation")
                for item in components:
                    expression(item)
            elif kind == "model":
                if check["model"] not in MODEL_REQUIREMENTS:
                    raise ValueError("unknown model profile")
            else:
                for field in _FIELDS[kind] - {"expected_unit", "variable"}:
                    expression(check[field])
                if kind == "dimensions":
                    _text(check["expected_unit"])
                if kind == "limit" and check["variable"] not in names:
                    raise ValueError("limit variable must be declared")
    if count > 60:
        raise ValueError("at most 60 checks per contract")
    return data


def _expanded(text: str, definitions: dict[str, str]) -> str:
    """Expand syntax under the existing parser's budgets, before evaluation."""

    class Substitute(ast.NodeTransformer):
        def visit_Name(self, node: ast.Name) -> ast.AST:
            return ast.parse(definitions[node.id].strip(), mode="eval").body if node.id in definitions else node

    tree = Substitute().visit(ast.parse(text.strip(), mode="eval"))
    expanded = ast.unparse(tree)
    parse_expression(expanded)  # Enforce size, depth and numeric-power budgets.
    return expanded


def _bindings(data: dict[str, Any]) -> dict[str, str]:
    pending = dict(data.get("bindings", {}))
    resolved: dict[str, str] = {}
    while pending:
        ready = [name for name, value in pending.items() if not (parse_expression(value).symbols & pending.keys())]
        if not ready:
            raise ValueError("cyclic bindings are not allowed")
        for name in ready:
            resolved[name] = _expanded(pending.pop(name), resolved)
    return resolved


def _expr(text: str, bindings: dict[str, str]) -> sympy.Expr:
    return parse_expression(_expanded(text, bindings)).expr


def _identity(left: sympy.Expr, right: sympy.Expr) -> tuple[str, str]:
    # Keep parsed objects: serializing Euler's constant as 'E' and reparsing
    # would confuse it with Young's modulus, which is a legitimate symbol.
    difference = _run_bounded(lambda: sympy.simplify(left - right), 5.0)
    if difference == 0:
        return (
            "SYMBOLICALLY_VERIFIED",
            "The difference simplifies to zero on the common domain of the declared expressions.",
        )
    if _run_bounded(lambda: _definitely_nonzero(difference), 5.0) is True:
        return "FAILED", f"The declared equality is not an identity; residual: {str(difference)[:1000]}"
    return "UNVERIFIED", f"The identity could not be decided; residual: {str(difference)[:1000]}"


def _point_status(text: str, bindings: dict[str, str], definitions: dict[str, str]) -> tuple[str, str]:
    """Check the original divisions before SymPy can cancel x/x to 1."""
    visited: set[str] = set()
    undecided = False

    def guards(source: str) -> str | None:
        nonlocal undecided
        source = source.strip()
        tree = ast.parse(source, mode="eval")
        for node in reversed(list(ast.walk(tree))):
            denominator = None
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
                denominator = node.right
            elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
                power = _expr(ast.unparse(node.right), bindings)
                if power.is_negative is True:
                    denominator = node.left
            if denominator is not None:
                value = _expr(ast.unparse(denominator), bindings)
                if value == 0:
                    return "The original expression has a zero divisor at the declared point."
                if value.is_zero is not False:
                    undecided = True
            if isinstance(node, (ast.BinOp, ast.UnaryOp, ast.Call)):
                intermediate = _expr(ast.unparse(node), bindings)
                if (
                    intermediate.is_finite is False
                    or intermediate.is_real is False
                    or intermediate.has(sympy.zoo, sympy.nan, sympy.oo, -sympy.oo)
                ):
                    return "An original subexpression has no finite real value at the declared point."
                if intermediate.is_finite is not True or intermediate.is_real is not True:
                    undecided = True
            if isinstance(node, ast.Name) and node.id in definitions and node.id not in visited:
                visited.add(node.id)
                issue = guards(definitions[node.id])
                if issue:
                    return issue
        return None

    issue = guards(text)
    if issue:
        return "FAILED", issue
    value = _expr(text, bindings)
    if value.is_finite is False or value.is_real is False or value.has(sympy.zoo, sympy.nan, sympy.oo, -sympy.oo):
        return "FAILED", f"The original expression has no finite real point value: {value}"
    if value.is_finite is True and value.is_real is True and not undecided:
        return "DOMAIN_POINT_CHECKED", f"Finite real value at the declared point: {value}"
    return "UNVERIFIED", "The declared point does not determine a finite real value."


def _assumption(assumption: dict[str, Any], bindings: dict[str, str], definitions: dict[str, str]) -> str:
    for key in ("left", "right"):
        if _point_status(assumption[key], bindings, definitions)[0] == "FAILED":
            return "FAILED"
    left, right = (_expr(assumption[key], bindings) for key in ("left", "right"))
    operations = {"eq": sympy.Eq, "ne": sympy.Ne, "gt": sympy.Gt, "ge": sympy.Ge, "lt": sympy.Lt, "le": sympy.Le}
    result = _run_bounded(lambda: operations[assumption["relation"]](sympy.simplify(left), sympy.simplify(right)), 5.0)
    if result is sympy.true:
        return "ASSUMPTIONS_CHECKED"
    if result is sympy.false:
        return "FAILED"
    return "UNVERIFIED"


def _check(check: dict[str, Any], data: dict[str, Any], bindings: dict[str, str]) -> tuple[str, str]:
    kind = check["kind"]
    if kind == "identity":
        if "equation" in check:
            check = next(eq for eq in data["equations"] if eq["id"] == check["equation"])
        for side in ("left", "right"):
            status, detail = _point_status(check[side], bindings, data["bindings"])
            if status == "FAILED":
                return status, detail
        return _identity(_expr(check["left"], bindings), _expr(check["right"], bindings))
    if kind == "dimensions":
        # Units apply to the stated equation, before substituting numeric data.
        result = verify_dimensions(check["expression"], data["variables"], expected_unit=check["expected_unit"])
        return result.status.value, result.detail
    if kind == "defined":
        return _point_status(check["expression"], bindings, data["bindings"])
    if kind == "limit":
        # The limiting variable must remain free, even when the point value is supplied.
        variable = sympy.Symbol(check["variable"])
        definitions = {key: value for key, value in data["bindings"].items() if key != str(variable)}
        reduced = _bindings(
            {"bindings": definitions}
        )
        for key in ("expression", "point", "claimed"):
            status, detail = _point_status(check[key], reduced, definitions)
            if status == "FAILED":
                return status, detail
        expression = _expr(check["expression"], reduced)
        point = _expr(check["point"], reduced)
        if variable in point.free_symbols:
            return "UNVERIFIED", "The limit point depends on the limiting variable."
        computed = _run_bounded(lambda: sympy.limit(expression, variable, point, dir="+-"), 5.0)
        status, detail = _identity(computed, _expr(check["claimed"], reduced))
        return status, "Two-sided limit: " + detail
    if kind == "gradient":
        coords = [sympy.Symbol(name) for name in check["coordinates"]]
        for value in check["components"]:
            status, detail = _point_status(value, bindings, data["bindings"])
            if status == "FAILED":
                return status, detail
        components = [_expr(value, bindings) for value in check["components"]]
        for i, j in ((0, 1), (0, 2), (1, 2)):
            residual = _run_bounded(
                lambda i=i, j=j: sympy.diff(components[i], coords[j]) - sympy.diff(components[j], coords[i]), 5.0
            )
            status, detail = _identity(residual, sympy.Integer(0))
            if status != "SYMBOLICALLY_VERIFIED":
                return status, f"Mixed partials ({i},{j}): {detail}"
        return (
            "MODEL_CONSISTENT_UNDER_ASSUMPTIONS",
            "Pressure-gradient mixed partials agree locally; global existence, domain regularity and physical applicability require review.",
        )
    return (
        "MODEL_CONSISTENT_UNDER_ASSUMPTIONS",
        "The model profile's declared predicates hold under the supplied bindings; applicability requires expert review.",
    )


def assess_contract(value: object) -> dict[str, Any]:
    """Return a verification vector, never an aggregate VERIFIED flag."""
    data = validate_contract(value)
    bindings = _bindings(data)
    assumptions: dict[str, str] = {}
    for item in data["assumptions"]:
        try:
            assumptions[item["id"]] = _assumption(item, bindings, data["bindings"])
        except Exception:
            assumptions[item["id"]] = "UNVERIFIED"
    checks = []
    for representation in data["representations"]:
        for index, check in enumerate(representation["checks"]):
            required = list(representation["requires"])
            if check["kind"] == "model":
                required.extend(MODEL_REQUIREMENTS[check["model"]])
            missing = [name for name in required if assumptions.get(name) != "ASSUMPTIONS_CHECKED"]
            if missing:
                failed = any(assumptions.get(name) == "FAILED" for name in missing)
                status, detail = (
                    ("FAILED" if failed else "UNVERIFIED"),
                    "Unsatisfied or missing hypotheses: " + ", ".join(missing),
                )
            else:
                try:
                    status, detail = _check(check, data, bindings)
                except Exception as exc:
                    status, detail = "UNVERIFIED", f"The check could not decide: {type(exc).__name__}"
            checks.append(
                {
                    "record": representation["record"],
                    "role": representation["role"],
                    "index": index,
                    "kind": check["kind"],
                    "category": _CATEGORIES[check["kind"]],
                    "status": status,
                    "detail": detail,
                    "inputs": check,
                    "requires": required,
                    "scope": "Declared expressions and bindings only; correspondence to prose and physical conditions requires review.",
                }
            )
    verification: dict[str, str] = dict.fromkeys(
        (
            "arithmetic",
            "symbolic",
            "dimensions",
            "domain",
            "assumptions",
            "model",
            "numerical_convergence",
            "documentary",
        ),
        "NOT_CHECKED",
    )
    for category in ("symbolic", "dimensions", "domain", "model"):
        states = [check["status"] for check in checks if check["category"] == category]
        verification[category] = _combine_scope(states)
    verification["assumptions"] = _combine_scope(list(assumptions.values()))
    verification["expert_review"] = "PENDING"
    return {
        "checks": checks,
        "assumptions": assumptions,
        "verification": verification,
        "scientific_validity": "not_established",
    }


def _combine_scope(states: list[str]) -> str:
    if "FAILED" in states:
        return "FAILED"
    if "UNVERIFIED" in states:
        return "UNVERIFIED"
    unique = set(states)
    return next(iter(unique)) if len(unique) == 1 else ("MIXED_CHECKS" if unique else "NOT_CHECKED")
