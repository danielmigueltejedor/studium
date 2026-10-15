"""Dimensional consistency of prose equations from the book's own notation units.

The notation registry gives each symbol one unit string. For an equation whose
symbols all have a unit (or are declared dimensionless by their meaning), both
sides are walked over the Pint base dimensions and compared. This is a
*probe*, not a verification status: a book may reuse a letter for two
quantities (``D`` for a diameter and for a drag force), so a mismatch means
"look at this equation", and a match shows only that the equation is
dimensionally plausible under the registered units.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from studium.authoring.notation import notation_registry
from studium.verification.dimensional import DimensionError, check_dimensions

_DIMENSIONLESS_MEANING = re.compile(
    r"n[uú]mero|coeficiente|adimensional|factor|raz[oó]n|relaci[oó]n|cociente|dimensionless|ratio|coefficient|number",
    re.IGNORECASE,
)
_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_']*")
_RESERVED = frozenset({"sqrt", "sin", "cos", "tan", "exp", "ln", "log", "sinh", "cosh", "tanh", "pi"})


class EquationUnits:
    """Symbol name (as the relation parser spells it) -> unit string, from the notation registry."""

    def __init__(self, root: Path) -> None:
        from studium.authoring.grounding import _sympy_text

        self.units: dict[str, str] = {}
        for symbol, entry in notation_registry(root).items():
            unit = entry.get("units")
            meaning = str(entry.get("meaning") or "")
            if isinstance(unit, str) and unit.strip():
                chosen = unit.strip()
            elif _DIMENSIONLESS_MEANING.search(meaning):
                chosen = "dimensionless"
            else:
                continue
            for part in (item.strip() for item in symbol.split(",")):
                text = _sympy_text(f"{part} = 0")
                if text is None:
                    continue
                name = text.partition("=")[0].strip()
                if _NAME.fullmatch(name) and name not in self.units:
                    self.units[name] = chosen

    def probe(self, statement: str) -> dict[str, object]:
        return dict(_probe(self, statement))


@lru_cache(maxsize=8192)
def _probe_cached(key: tuple[tuple[str, str], ...], statement: str) -> tuple[tuple[str, object], ...]:
    from studium.authoring.grounding import _sympy_text

    units = dict(key)
    text = _sympy_text(statement)
    if text is None or text.count("=") != 1:
        return (("status", "unavailable"), ("detail", "the relation parser cannot read it"))
    left, right = (side.strip() for side in text.split("=", 1))
    if _numeric_side(left) or _numeric_side(right):
        return (("status", "unavailable"), ("detail", "a numeric side carries an implicit unit"))
    names = {name for name in _NAME.findall(left + " " + right) if name not in _RESERVED}
    names.discard("pi")
    for name in sorted(names):
        # \Delta p is a difference of p: it has the unit of p.
        if name not in units and name.startswith("Delta_") and name[6:] in units:
            units = {**units, name: units[name[6:]]}
    missing = sorted(name for name in names if name not in units)
    if missing:
        return (("status", "unavailable"), ("detail", "no registered unit for: " + ", ".join(missing[:6])))
    scope = {name: units[name] for name in names}
    scope = {name: ("1" if unit == "dimensionless" else unit) for name, unit in scope.items()}
    # pi is a dimensionless constant, never a quantity that needs a registered unit (F20).
    scope["pi"] = "1"
    try:
        first = check_dimensions(_python(left), scope)
        second = check_dimensions(_python(right), scope)
    except DimensionError as error:
        return (("status", "inconsistent"), ("detail", str(error)))
    if first.dims == second.dims:
        return (("status", "consistent"), ("detail", first.detail))
    return (("status", "inconsistent"), ("detail", f"left side: {first.detail}; right side: {second.detail}"))


def _probe(units: EquationUnits, statement: str) -> tuple[tuple[str, object], ...]:
    return _probe_cached(tuple(sorted(units.units.items())), statement)


def _numeric_side(side: str) -> bool:
    """A side made only of numbers, pi and functions of numbers: its unit is implicit in the prose."""

    return not [name for name in _NAME.findall(side) if name not in _RESERVED] and bool(re.search(r"\d|pi", side))


def _python(text: str) -> str:
    return text.replace("'", "_prime")
