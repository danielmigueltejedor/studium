"""Straight beams: structured model, exact solution, independent checks.

A beam is described by data, not by a picture::

    {
      "length": 8, "units": {"force": "kN", "length": "m"},
      "points": {"A": 0, "B": 2, "C": 6, "D": 8},
      "supports": [{"at": "A", "type": "fixed"}, {"at": "C", "type": "roller"}],
      "hinges": ["B"],
      "loads": [
        {"type": "point", "at": "B", "value": 2, "direction": "down"},
        {"type": "distributed", "from": "A", "to": "D", "start": 20, "end": 5, "direction": "up"},
        {"type": "couple", "at": 5, "value": 4, "sense": "ccw"}
      ],
      "EI": 1000, "convention": "ule-teoria-estructuras"
    }

Reactions, internal forces ``N, V, M`` and (with ``EI``) rotations and
deflections come from one linear system: global equilibrium, ``M = 0`` at each
internal hinge and, only when the beam is statically indeterminate or a
deflection is wanted, the support kinematics. All arithmetic is exact.

The checks in :func:`verify_beam` do not reuse the solver's formulas: global
equilibrium is summed directly from the loads about several points, internal
forces are recomputed from the right-hand part, the differential relations come
from the declared convention, and jumps are compared with the concentrated
actions at each point.
"""

from dataclasses import dataclass, field
from itertools import pairwise

import sympy

from studium.diagrams.evidence import Evidence
from studium.diagrams.piecewise import DataError, Piece, Piecewise, X, as_float, exact, sympify_text
from studium.engineering.structures.claims import compare
from studium.engineering.structures.convention import Convention, parse_convention

SUPPORT_TYPES = {"fixed": ("H", "R", "M"), "pin": ("H", "R"), "roller": ("R",)}
_DIRECTIONS = {"down": (0, -1), "up": (0, 1), "left": (-1, 0), "right": (1, 0)}
_MAX_ITEMS = 40
_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


@dataclass(frozen=True)
class PointForce:
    at: sympy.Expr
    fx: sympy.Expr
    fy: sympy.Expr
    label: str = ""


@dataclass(frozen=True)
class Couple:
    at: sympy.Expr
    ccw: sympy.Expr
    label: str = ""


@dataclass(frozen=True)
class Distributed:
    """Linear intensity from ``start`` to ``end`` along ``[a, b]``; ``axis`` y is transverse, x is axial."""

    a: sympy.Expr
    b: sympy.Expr
    start: sympy.Expr
    end: sympy.Expr
    sign: int
    axis: str
    label: str = ""

    def intensity(self, t: sympy.Expr) -> sympy.Expr:
        """Signed intensity: upward (axis y) or rightward (axis x) positive."""

        return self.sign * (self.start + (self.end - self.start) * (t - self.a) / (self.b - self.a))


@dataclass(frozen=True)
class Support:
    name: str
    at: sympy.Expr
    kind: str

    def unknowns(self) -> list[tuple[str, sympy.Symbol]]:
        return [(component, sympy.Symbol(f"{component}_{self.name}")) for component in SUPPORT_TYPES[self.kind]]


@dataclass
class BeamModel:
    length: sympy.Expr
    supports: list[Support]
    hinges: list[sympy.Expr]
    forces: list[PointForce]
    couples: list[Couple]
    distributed: list[Distributed]
    points: dict[str, sympy.Expr]
    units: dict[str, str]
    convention: Convention
    ei: list[tuple[sympy.Expr, sympy.Expr, sympy.Expr]] | None
    ea: sympy.Expr | None
    parameters: dict[str, sympy.Symbol]

    def breakpoints(self) -> list[sympy.Expr]:
        values = {sympy.Integer(0), self.length}
        values.update(support.at for support in self.supports)
        values.update(self.hinges)
        values.update(force.at for force in self.forces)
        values.update(couple.at for couple in self.couples)
        for load in self.distributed:
            values.update((load.a, load.b))
        if self.ei:
            for start, end, _ in self.ei:
                values.update((start, end))
        values.update(self.points.values())
        return sorted(values, key=as_float)

    def name_at(self, value: sympy.Expr) -> str:
        for name, position in self.points.items():
            if sympy.simplify(position - value) == 0:
                return name
        return ""


@dataclass(frozen=True)
class Extreme:
    x: sympy.Expr
    value: sympy.Expr


@dataclass
class BeamSolution:
    model: BeamModel
    reactions: dict[str, sympy.Expr]
    N: Piecewise
    V: Piecewise
    M: Piecewise
    theta: Piecewise | None = None
    v: Piecewise | None = None
    u: Piecewise | None = None
    degree: int = 0
    notes: list[str] = field(default_factory=list)

    def reaction_forces(self) -> tuple[list[PointForce], list[Couple]]:
        forces: list[PointForce] = []
        couples: list[Couple] = []
        for support in self.model.supports:
            for component, symbol in support.unknowns():
                value = self.reactions[str(symbol)]
                if component == "H":
                    forces.append(PointForce(support.at, value, sympy.Integer(0), str(symbol)))
                elif component == "R":
                    forces.append(PointForce(support.at, sympy.Integer(0), value, str(symbol)))
                else:
                    couples.append(Couple(support.at, value, str(symbol)))
        return forces, couples


# --------------------------------------------------------------------------- parsing


def parse_beam(spec: object) -> BeamModel:
    """Read and validate a beam description. Raises :class:`DataError` naming the field."""

    if not isinstance(spec, dict):
        raise DataError("a beam must be an object")
    parameters = _parameters(spec.get("parameters"))
    length = exact(spec.get("length"), "length", parameters)
    if length.is_number and not bool(length > 0):
        raise DataError("length must be positive")
    points_raw = spec.get("points") or {}
    if not isinstance(points_raw, dict) or len(points_raw) > _MAX_ITEMS:
        raise DataError("points must map names to positions")
    points: dict[str, sympy.Expr] = {}
    for name, value in points_raw.items():
        if not isinstance(name, str) or not name.strip() or len(name) > 12:
            raise DataError("a point name must be a short label such as A")
        points[name.strip()] = _inside(exact(value, f"points.{name}", parameters), length, f"points.{name}")

    def position(value: object, field_name: str) -> sympy.Expr:
        if isinstance(value, str) and value.strip() in points:
            return points[value.strip()]
        return _inside(exact(value, field_name, parameters), length, field_name)

    supports = _supports(spec.get("supports"), position, points)
    hinges = [position(item, "hinges") for item in _list(spec.get("hinges"), "hinges")]
    for hinge in hinges:
        if hinge.is_number and (hinge == 0 or sympy.simplify(hinge - length) == 0):
            raise DataError("an internal hinge must lie strictly inside the beam")
    forces: list[PointForce] = []
    couples: list[Couple] = []
    distributed: list[Distributed] = []
    for index, load in enumerate(_list(spec.get("loads"), "loads")):
        where = f"loads[{index}]"
        if not isinstance(load, dict):
            raise DataError(f"{where} must be an object")
        kind = load.get("type")
        label = str(load.get("label") or "")[:20]
        if kind == "point":
            at = position(load.get("at"), f"{where}.at")
            value = exact(load.get("value"), f"{where}.value", parameters)
            if "angle_deg" in load:
                angle = sympy.pi * exact(load.get("angle_deg"), f"{where}.angle_deg") / 180
                fx, fy = value * sympy.cos(angle), value * sympy.sin(angle)
            else:
                direction = load.get("direction")
                if direction not in _DIRECTIONS:
                    raise DataError(f"{where}.direction must be up, down, left or right (or give angle_deg)")
                dx, dy = _DIRECTIONS[str(direction)]
                fx, fy = value * dx, value * dy
            forces.append(PointForce(at, sympy.simplify(fx), sympy.simplify(fy), label))
        elif kind == "couple":
            at = position(load.get("at"), f"{where}.at")
            value = exact(load.get("value"), f"{where}.value", parameters)
            sense = load.get("sense")
            if sense not in ("ccw", "cw"):
                raise DataError(f"{where}.sense must be ccw or cw")
            if any(sympy.simplify(at - hinge) == 0 for hinge in hinges):
                raise DataError(f"{where}: a couple exactly at an internal hinge is ambiguous; put it on one side")
            couples.append(Couple(at, value if sense == "ccw" else -value, label))
        elif kind in ("distributed", "axial_distributed"):
            a = position(load.get("from"), f"{where}.from")
            b = position(load.get("to"), f"{where}.to")
            if a.is_number and b.is_number and not bool(b > a):
                raise DataError(f"{where}: 'to' must be beyond 'from'")
            start = exact(load.get("start"), f"{where}.start", parameters)
            end = exact(load.get("end", load.get("start")), f"{where}.end", parameters)
            direction = load.get("direction")
            if kind == "distributed":
                if direction not in ("up", "down"):
                    raise DataError(f"{where}.direction must be up or down")
                distributed.append(Distributed(a, b, start, end, 1 if direction == "up" else -1, "y", label))
            else:
                if direction not in ("left", "right"):
                    raise DataError(f"{where}.direction must be left or right")
                distributed.append(Distributed(a, b, start, end, 1 if direction == "right" else -1, "x", label))
        else:
            raise DataError(f"{where}.type must be point, couple, distributed or axial_distributed")
    units = _units(spec.get("units"))
    ei = _stiffness(spec.get("EI"), length, parameters, position)
    ea_value = spec.get("EA")
    ea = exact(ea_value, "EA", parameters) if ea_value is not None else None
    convention = parse_convention(spec.get("convention"))
    return BeamModel(length, supports, hinges, forces, couples, distributed, points, units, convention, ei, ea, parameters)


def _parameters(value: object) -> dict[str, sympy.Symbol]:
    if value is None:
        return {}
    if not isinstance(value, list) or len(value) > 20:
        raise DataError("parameters must be a short list of names")
    found: dict[str, sympy.Symbol] = {}
    for item in value:
        if not isinstance(item, str) or not item.isidentifier() or len(item) > 20:
            raise DataError("a parameter must be an identifier such as q or L")
        found[item] = sympy.Symbol(item, positive=True)
    return found


def _inside(value: sympy.Expr, length: sympy.Expr, name: str) -> sympy.Expr:
    if value.is_number and length.is_number and not bool(0 <= value <= length):
        raise DataError(f"{name} lies outside the beam")
    return value


def _list(value: object, name: str) -> list[object]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > _MAX_ITEMS:
        raise DataError(f"{name} must be a list")
    return value


def _supports(value: object, position, points: dict[str, sympy.Expr]) -> list[Support]:
    supports: list[Support] = []
    for index, item in enumerate(_list(value, "supports")):
        if not isinstance(item, dict) or item.get("type") not in SUPPORT_TYPES:
            raise DataError(f"supports[{index}] needs type fixed, pin or roller")
        at_value = item.get("at")
        at = position(at_value, f"supports[{index}].at")
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            name = at_value.strip() if isinstance(at_value, str) and at_value.strip() in points else ""
        if not name:
            name = next((label for label, place in points.items() if sympy.simplify(place - at) == 0), "")
        if not name:
            name = _LETTERS[index]
        if any(existing.name == name for existing in supports):
            raise DataError(f"two supports are called {name}")
        supports.append(Support(name.strip(), at, str(item["type"])))
    if not supports:
        raise DataError("a beam needs at least one support")
    return supports


def _units(value: object) -> dict[str, str]:
    units = {"force": "kN", "length": "m"}
    if value is None:
        return units
    if not isinstance(value, dict):
        raise DataError("units must map force and length to unit names")
    for key in ("force", "length"):
        item = value.get(key)
        if item is not None:
            if not isinstance(item, str) or not item.strip() or len(item) > 10:
                raise DataError(f"units.{key} must be a short unit name such as kN or m")
            units[key] = item.strip()
    return units


def _stiffness(value: object, length: sympy.Expr, parameters, position) -> list[tuple[sympy.Expr, sympy.Expr, sympy.Expr]] | None:
    if value is None:
        return None
    if isinstance(value, list):
        pieces = []
        for index, item in enumerate(value):
            if not isinstance(item, dict):
                raise DataError(f"EI[{index}] must be an object with from, to, value")
            pieces.append(
                (
                    position(item.get("from"), f"EI[{index}].from"),
                    position(item.get("to"), f"EI[{index}].to"),
                    exact(item.get("value"), f"EI[{index}].value", parameters),
                )
            )
        pieces.sort(key=lambda piece: as_float(piece[0]))
        cursor = sympy.Integer(0)
        for start, end, _ in pieces:
            if sympy.simplify(start - cursor) != 0:
                raise DataError("EI pieces must cover the beam without gaps")
            cursor = end
        if sympy.simplify(cursor - length) != 0:
            raise DataError("EI pieces must cover the beam without gaps")
        return pieces
    return [(sympy.Integer(0), length, exact(value, "EI", parameters))]


# --------------------------------------------------------------------------- solving


def _sums_left(
    forces: list[PointForce], couples: list[Couple], distributed: list[Distributed], a: sympy.Expr, x: sympy.Expr
) -> tuple[sympy.Expr, sympy.Expr, sympy.Expr]:
    """Upward force, rightward force and counter-clockwise moment about the cut at ``x``
    of every action on ``[0, x)`` for a cut inside the interval that starts at ``a``."""

    fy = sympy.Integer(0)
    fx = sympy.Integer(0)
    ccw = sympy.Integer(0)
    t = sympy.Symbol("t", real=True)
    for force in forces:
        if as_float(force.at) <= as_float(a):
            fy += force.fy
            fx += force.fx
            ccw += (force.at - x) * force.fy
    for couple in couples:
        if as_float(couple.at) <= as_float(a):
            ccw += couple.ccw
    for load in distributed:
        if as_float(load.a) > as_float(a):
            continue
        upper = load.b if as_float(load.b) <= as_float(a) else x
        intensity = load.intensity(t)
        if load.axis == "y":
            fy += sympy.integrate(intensity, (t, load.a, upper))
            ccw += sympy.integrate((t - x) * intensity, (t, load.a, upper))
        else:
            fx += sympy.integrate(intensity, (t, load.a, upper))
    return sympy.expand(fy), sympy.expand(fx), sympy.expand(ccw)


def _sums_right(
    forces: list[PointForce], couples: list[Couple], distributed: list[Distributed], b: sympy.Expr, x: sympy.Expr
) -> tuple[sympy.Expr, sympy.Expr, sympy.Expr]:
    """The same sums for every action on ``(x, L]`` for a cut inside the interval that ends at ``b``."""

    fy = sympy.Integer(0)
    fx = sympy.Integer(0)
    ccw = sympy.Integer(0)
    t = sympy.Symbol("t", real=True)
    for force in forces:
        if as_float(force.at) >= as_float(b):
            fy += force.fy
            fx += force.fx
            ccw += (force.at - x) * force.fy
    for couple in couples:
        if as_float(couple.at) >= as_float(b):
            ccw += couple.ccw
    for load in distributed:
        if as_float(load.b) < as_float(b):
            continue
        lower = load.a if as_float(load.a) >= as_float(b) else x
        intensity = load.intensity(t)
        if load.axis == "y":
            fy += sympy.integrate(intensity, (t, lower, load.b))
            ccw += sympy.integrate((t - x) * intensity, (t, lower, load.b))
        else:
            fx += sympy.integrate(intensity, (t, lower, load.b))
    return sympy.expand(fy), sympy.expand(fx), sympy.expand(ccw)


def solve_beam(model: BeamModel) -> BeamSolution:
    """Reactions and internal forces. Raises :class:`DataError` for a mechanism or a missing stiffness."""

    _require_numeric_order(model)
    rel = model.convention.relations()
    symbols: list[sympy.Symbol] = []
    unknown_forces: list[PointForce] = []
    unknown_couples: list[Couple] = []
    for support in model.supports:
        for component, symbol in support.unknowns():
            symbols.append(symbol)
            if component == "H":
                unknown_forces.append(PointForce(support.at, symbol, sympy.Integer(0), str(symbol)))
            elif component == "R":
                unknown_forces.append(PointForce(support.at, sympy.Integer(0), symbol, str(symbol)))
            else:
                unknown_couples.append(Couple(support.at, symbol, str(symbol)))
    forces = model.forces + unknown_forces
    couples = model.couples + unknown_couples
    breaks = model.breakpoints()
    intervals = list(pairwise(breaks))
    if not intervals:
        raise DataError("the beam has no length")
    # Internal forces from the left part, in terms of the unknown reactions.
    n_pieces, v_pieces, m_pieces = [], [], []
    for a, b in intervals:
        fy, fx, ccw = _sums_left(forces, couples, model.distributed, a, X)
        n_pieces.append(Piece(a, b, sympy.expand(rel.left_axial * fx)))
        v_pieces.append(Piece(a, b, sympy.expand(rel.left_shear * fy)))
        m_pieces.append(Piece(a, b, sympy.expand(rel.left_moment * ccw)))
    end = model.length
    fy_all, fx_all, ccw_all = _sums_left(forces, couples, model.distributed, end, end)
    vertical = [sympy.expand(fy_all), sympy.expand(ccw_all)]
    for hinge in model.hinges:
        left_piece = next(piece for piece in m_pieces if sympy.simplify(piece.end - hinge) == 0)
        vertical.append(sympy.expand(left_piece.expr.subs(X, hinge)))
    axial = [sympy.expand(fx_all)]
    v_unknowns = [s for s in symbols if not str(s).startswith("H_")]
    h_unknowns = [s for s in symbols if str(s).startswith("H_")]
    degree = len(v_unknowns) - len(vertical)
    degree_axial = len(h_unknowns) - 1
    notes: list[str] = []
    if degree < 0:
        raise DataError(f"the beam is a mechanism: {len(v_unknowns)} transverse reactions for {len(vertical)} equations")
    has_axial_load = any(sympy.simplify(f.fx) != 0 for f in model.forces) or any(
        load.axis == "x" for load in model.distributed
    )
    if not h_unknowns:
        if has_axial_load:
            raise DataError("the beam has axial load but no horizontal restraint")
        notes.append("no horizontal restraint; acceptable only because there is no axial load")
        axial = []
    want_kinematics = model.ei is not None
    if degree > 0 and not want_kinematics:
        raise DataError(f"the beam is statically indeterminate of degree {degree}; give EI to add compatibility")
    if degree_axial > 0 and model.ea is None:
        raise DataError(f"the beam is axially indeterminate of degree {degree_axial}; give EA")
    equations = vertical + axial
    unknowns: list[sympy.Symbol] = list(symbols)
    kin_symbols: list[sympy.Symbol] = []
    if want_kinematics:
        theta_pieces, v_pieces_k, kin_eqs, kin_symbols = _kinematics(model, m_pieces, rel_moment=model.convention.moment_sign)
        equations += kin_eqs
        unknowns += kin_symbols
    if degree_axial > 0:
        u_pieces, axial_eqs, u_symbols = _axial_kinematics(model, n_pieces)
        equations += axial_eqs
        unknowns += u_symbols
    solution = sympy.solve(equations, unknowns, dict=True)
    if len(solution) != 1 or any(symbol not in solution[0] for symbol in symbols):
        raise DataError("the support system does not determine the reactions (mechanism or redundant data)")
    values = solution[0]
    reactions: dict[str, sympy.Expr] = {
        str(symbol): sympy.simplify(values[symbol]) for symbol in symbols
    }

    def fill(pieces: list[Piece], name: str) -> Piecewise:
        return Piecewise(name, tuple(Piece(p.start, p.end, sympy.expand(p.expr.subs(values))) for p in pieces))

    result = BeamSolution(model, reactions, fill(n_pieces, "N"), fill(v_pieces, "V"), fill(m_pieces, "M"), degree=degree, notes=notes)
    if want_kinematics:
        if not all(symbol in values for symbol in kin_symbols):
            raise DataError("the supports do not fix the deflected shape")
        result.theta = fill(theta_pieces, "theta")
        result.v = fill(v_pieces_k, "v")
    if degree_axial > 0:
        result.u = fill(u_pieces, "u")
    return result


def _require_numeric_order(model: BeamModel) -> None:
    for value in model.breakpoints():
        if not value.is_number:
            raise DataError("positions must be numbers; symbolic parameters are allowed in magnitudes only")


def _ei_at(model: BeamModel, a: sympy.Expr, b: sympy.Expr) -> sympy.Expr:
    assert model.ei is not None
    middle = (a + b) / 2
    for start, end, value in model.ei:
        if as_float(start) <= as_float(middle) <= as_float(end):
            return value
    raise DataError("EI does not cover the beam")


def _kinematics(model: BeamModel, m_pieces: list[Piece], rel_moment: int):
    """Rotation and deflection (upward positive) by integrating ``v'' = rel_moment * M / EI``."""

    theta0, v0 = sympy.symbols("theta_0 v_0")
    jumps = {hinge: sympy.Symbol(f"dtheta_{index}") for index, hinge in enumerate(model.hinges)}
    theta_pieces: list[Piece] = []
    v_pieces: list[Piece] = []
    theta_at = theta0
    v_at = v0
    t = sympy.Symbol("t", real=True)
    for piece in m_pieces:
        a, b = piece.start, piece.end
        for hinge, symbol in jumps.items():
            if sympy.simplify(hinge - a) == 0:
                theta_at = theta_at + symbol
        curvature = rel_moment * piece.expr / _ei_at(model, a, b)
        theta_expr = sympy.expand(theta_at + sympy.integrate(curvature.subs(X, t), (t, a, X)))
        v_expr = sympy.expand(v_at + sympy.integrate(theta_expr.subs(X, t), (t, a, X)))
        theta_pieces.append(Piece(a, b, theta_expr))
        v_pieces.append(Piece(a, b, v_expr))
        theta_at = theta_expr.subs(X, b)
        v_at = v_expr.subs(X, b)
    equations = []
    for support in model.supports:
        piece_index = _piece_index(v_pieces, support.at)
        equations.append(v_pieces[piece_index].expr.subs(X, support.at))
        if support.kind == "fixed":
            equations.append(theta_pieces[piece_index].expr.subs(X, support.at))
    return theta_pieces, v_pieces, equations, [theta0, v0, *jumps.values()]


def _axial_kinematics(model: BeamModel, n_pieces: list[Piece]):
    assert model.ea is not None
    u0 = sympy.Symbol("u_0")
    u_pieces: list[Piece] = []
    u_at = u0
    t = sympy.Symbol("t", real=True)
    for piece in n_pieces:
        expr = sympy.expand(u_at + sympy.integrate((model.convention.axial_sign * piece.expr / model.ea).subs(X, t), (t, piece.start, X)))
        u_pieces.append(Piece(piece.start, piece.end, expr))
        u_at = expr.subs(X, piece.end)
    equations = []
    for support in model.supports:
        if "H" in SUPPORT_TYPES[support.kind]:
            index = _piece_index(u_pieces, support.at)
            equations.append(u_pieces[index].expr.subs(X, support.at))
    return u_pieces, equations, [u0]


def _piece_index(pieces: list[Piece], at: sympy.Expr) -> int:
    for index, piece in enumerate(pieces):
        if as_float(piece.start) <= as_float(at) <= as_float(piece.end):
            return index
    raise DataError("a support lies outside the beam")


# --------------------------------------------------------------------------- key values


def key_points(solution: BeamSolution, function: str) -> list[dict[str, object]]:
    """Values a diagram must show: ends of every interval, jumps, interior extrema and zeros."""

    curve = {"N": solution.N, "V": solution.V, "M": solution.M}.get(function)
    if curve is None:
        curve = solution.v if function == "v" else solution.theta
    if curve is None:
        return []
    found: list[dict[str, object]] = []
    for piece in curve.pieces:
        for side, place in (("right", piece.start), ("left", piece.end)):
            found.append({"x": place, "side": side, "value": piece.at(place), "kind": "end"})
    for place in curve.critical_points():
        found.append({"x": place, "side": "both", "value": curve.piece_at(place).at(place), "kind": "extremum"})
    for place in curve.zeros():
        found.append({"x": place, "side": "both", "value": sympy.Integer(0), "kind": "zero"})
    return found


def extremes(curve: Piecewise) -> dict[str, Extreme]:
    """Largest and smallest values over the whole beam, from ends and interior critical points."""

    candidates: list[tuple[sympy.Expr, sympy.Expr]] = []
    for piece in curve.pieces:
        candidates.append((piece.start, piece.at(piece.start)))
        candidates.append((piece.end, piece.at(piece.end)))
    for place in curve.critical_points():
        candidates.append((place, curve.piece_at(place).at(place)))
    largest = max(candidates, key=lambda item: as_float(item[1]))
    smallest = min(candidates, key=lambda item: as_float(item[1]))
    return {
        "max": Extreme(largest[0], sympy.simplify(largest[1])),
        "min": Extreme(smallest[0], sympy.simplify(smallest[1])),
    }


# --------------------------------------------------------------------------- verification


def verify_beam(solution: BeamSolution, claims: object = None) -> Evidence:
    """Independent checks of a solved beam. A failed check means the data and the result disagree."""

    model = solution.model
    rel = model.convention.relations()
    evidence = Evidence()
    reaction_forces, reaction_couples = solution.reaction_forces()
    forces = model.forces + reaction_forces
    couples = model.couples + reaction_couples
    t = sympy.Symbol("t", real=True)
    # 1. Global equilibrium, summed directly from the actions about three points.
    total_fy = sum((f.fy for f in forces), sympy.Integer(0)) + sum(
        (sympy.integrate(load.intensity(t), (t, load.a, load.b)) for load in model.distributed if load.axis == "y"),
        sympy.Integer(0),
    )
    total_fx = sum((f.fx for f in forces), sympy.Integer(0)) + sum(
        (sympy.integrate(load.intensity(t), (t, load.a, load.b)) for load in model.distributed if load.axis == "x"),
        sympy.Integer(0),
    )
    evidence.add("global equilibrium, vertical forces", "symbolic", sympy.simplify(total_fy) == 0, residual=sympy.simplify(total_fy))
    if model.supports and any("H" in SUPPORT_TYPES[s.kind] for s in model.supports):
        evidence.add("global equilibrium, horizontal forces", "symbolic", sympy.simplify(total_fx) == 0, residual=sympy.simplify(total_fx))
    for label, pivot in (("left end", sympy.Integer(0)), ("right end", model.length), ("mid-span", model.length / 3)):
        moment = sum(((f.at - pivot) * f.fy for f in forces), sympy.Integer(0))
        moment += sum((c.ccw for c in couples), sympy.Integer(0))
        moment += sum(
            (sympy.integrate((t - pivot) * load.intensity(t), (t, load.a, load.b)) for load in model.distributed if load.axis == "y"),
            sympy.Integer(0),
        )
        evidence.add(f"global equilibrium, moments about {label}", "symbolic", sympy.simplify(moment) == 0, residual=sympy.simplify(moment))
    # 2. Internal forces recomputed from the right-hand part.
    agree = True
    worst = ""
    for v_piece, m_piece, n_piece in zip(solution.V.pieces, solution.M.pieces, solution.N.pieces, strict=True):
        fy, fx, ccw = _sums_right(forces, couples, model.distributed, v_piece.end, X)
        for name, left, right in (
            ("V", v_piece.expr, rel.right_shear * fy),
            ("M", m_piece.expr, rel.right_moment * ccw),
            ("N", n_piece.expr, rel.right_axial * fx),
        ):
            difference = sympy.simplify(sympy.expand(left - right))
            if difference != 0:
                agree = False
                worst = f"{name} on ({v_piece.start}, {v_piece.end}) differs by {difference}"
    evidence.add("left and right sections agree on every interval", "symbolic", agree, worst)
    # 3. Differential relations derived from the convention.
    ok = True
    detail = f"dV/dx = {rel.shear_load:+d} q_up, dM/dx = {rel.moment_shear:+d} V, dN/dx = {rel.axial_load:+d} p_right"
    for v_piece, m_piece, n_piece in zip(solution.V.pieces, solution.M.pieces, solution.N.pieces, strict=True):
        middle = (v_piece.start + v_piece.end) / 2
        q_up = sum((load.intensity(X) for load in model.distributed if load.axis == "y" and _covers(load, middle)), sympy.Integer(0))
        p_right = sum((load.intensity(X) for load in model.distributed if load.axis == "x" and _covers(load, middle)), sympy.Integer(0))
        checks = (
            sympy.diff(v_piece.expr, X) - rel.shear_load * q_up,
            sympy.diff(m_piece.expr, X) - rel.moment_shear * v_piece.expr,
            sympy.diff(n_piece.expr, X) - rel.axial_load * p_right,
        )
        if any(sympy.simplify(sympy.expand(item)) != 0 for item in checks):
            ok = False
            detail += f"; fails on ({v_piece.start}, {v_piece.end})"
    evidence.add("differential relations of the declared convention", "symbolic", ok, detail)
    # 4. Jumps at concentrated actions, and continuity elsewhere.
    jump_ok = True
    jump_detail = ""
    for place in model.breakpoints():
        point_fy = sum((f.fy for f in forces if sympy.simplify(f.at - place) == 0), sympy.Integer(0))
        point_fx = sum((f.fx for f in forces if sympy.simplify(f.at - place) == 0), sympy.Integer(0))
        point_ccw = sum((c.ccw for c in couples if sympy.simplify(c.at - place) == 0), sympy.Integer(0))
        expected = {
            "V": rel.left_shear * point_fy,
            "M": rel.left_moment * point_ccw,
            "N": rel.left_axial * point_fx,
        }
        for name, curve in (("V", solution.V), ("M", solution.M), ("N", solution.N)):
            before = curve.left(place) if as_float(place) > 0 else sympy.Integer(0)
            after = curve.right(place) if as_float(place) < as_float(model.length) else sympy.Integer(0)
            residual = sympy.simplify(after - before - expected[name])
            if residual != 0:
                jump_ok = False
                jump_detail = f"{name} jump at x = {place} is off by {residual}"
    evidence.add("jumps equal the concentrated actions; continuity elsewhere (ends included)", "symbolic", jump_ok, jump_detail)
    # 5. Internal hinges carry no moment.
    for hinge in model.hinges:
        residual = (sympy.simplify(solution.M.left(hinge)), sympy.simplify(solution.M.right(hinge)))
        evidence.add(f"M = 0 at the hinge x = {hinge}", "symbolic", residual == (0, 0), residual=residual)
    # 6. Support kinematics and the elastic line.
    if solution.v is not None and solution.theta is not None:
        evidence.extend(_verify_kinematics(solution))
    # 7. Extrema: analytic candidates against a dense numeric sweep.
    evidence.extend(_verify_extrema(solution))
    # 8. Dimensional homogeneity by scaling lengths and forces.
    evidence.extend(_verify_scaling(solution))
    if claims is not None:
        evidence.extend(check_claims(solution, claims))
    return evidence


def _covers(load: Distributed, place: sympy.Expr) -> bool:
    return as_float(load.a) < as_float(place) < as_float(load.b)


def _verify_kinematics(solution: BeamSolution) -> Evidence:
    model = solution.model
    evidence = Evidence()
    assert solution.v is not None and solution.theta is not None
    for support in model.supports:
        evidence.add(
            f"no deflection at support {support.name}",
            "symbolic",
            sympy.simplify(solution.v.left(support.at) if as_float(support.at) > 0 else solution.v.right(support.at)) == 0,
        )
        if support.kind == "fixed":
            evidence.add(
                f"no rotation at the fixed support {support.name}",
                "symbolic",
                sympy.simplify(solution.theta.right(support.at) if as_float(support.at) < as_float(model.length) else solution.theta.left(support.at)) == 0,
            )
    smooth = True
    for place in model.breakpoints()[1:-1]:
        if sympy.simplify(solution.v.jump(place)) != 0:
            smooth = False
        hinge = any(sympy.simplify(place - hinge) == 0 for hinge in model.hinges)
        if not hinge and sympy.simplify(solution.theta.jump(place)) != 0:
            smooth = False
    evidence.add("deflection continuous; rotation continuous except at hinges", "symbolic", smooth)
    curvature_ok = True
    for m_piece, v_piece in zip(solution.M.pieces, solution.v.pieces, strict=True):
        ei = _ei_at(model, m_piece.start, m_piece.end)
        if sympy.simplify(sympy.diff(v_piece.expr, X, 2) - model.convention.moment_sign * m_piece.expr / ei) != 0:
            curvature_ok = False
    evidence.add("elastic line: v'' equals the curvature M/EI of the declared moment sign", "symbolic", curvature_ok)
    return evidence


def _verify_extrema(solution: BeamSolution, samples: int = 1200) -> Evidence:
    evidence = Evidence()
    for name, curve in (("V", solution.V), ("M", solution.M)):
        if not curve.is_numeric():
            continue
        analytic = extremes(curve)
        sweep_max = -float("inf")
        sweep_min = float("inf")
        for piece in curve.pieces:
            a, b = as_float(piece.start), as_float(piece.end)
            coefficients = [as_float(c) for c in sympy.Poly(piece.expr, X).all_coeffs()]
            for k in range(samples + 1):
                place = a + (b - a) * k / samples
                value = 0.0
                for coefficient in coefficients:
                    value = value * place + coefficient
                sweep_max = max(sweep_max, value)
                sweep_min = min(sweep_min, value)
        scale = max(abs(sweep_max), abs(sweep_min), 1e-12)
        top = as_float(analytic["max"].value)
        bottom = as_float(analytic["min"].value)
        good = top >= sweep_max - 1e-9 * scale and bottom <= sweep_min + 1e-9 * scale and abs(top - sweep_max) < 1e-3 * scale and abs(bottom - sweep_min) < 1e-3 * scale
        evidence.add(
            f"{name} extrema agree with a {samples}-point sweep per interval",
            "numeric",
            good,
            f"analytic max {top:.6g}, min {bottom:.6g}; sweep max {sweep_max:.6g}, min {sweep_min:.6g}",
        )
    return evidence


def _verify_scaling(solution: BeamSolution) -> Evidence:
    """Scale lengths by 3 and forces by 7: V must scale by 7 and M by 21 at matching points."""

    model = solution.model
    lam, phi = sympy.Integer(3), sympy.Integer(7)
    scaled = BeamModel(
        model.length * lam,
        [Support(s.name, s.at * lam, s.kind) for s in model.supports],
        [h * lam for h in model.hinges],
        [PointForce(f.at * lam, f.fx * phi, f.fy * phi, f.label) for f in model.forces],
        [Couple(c.at * lam, c.ccw * phi * lam, c.label) for c in model.couples],
        [Distributed(d.a * lam, d.b * lam, d.start * phi / lam, d.end * phi / lam, d.sign, d.axis, d.label) for d in model.distributed],
        {k: v * lam for k, v in model.points.items()},
        model.units,
        model.convention,
        [(a * lam, b * lam, ei * phi * lam**2) for a, b, ei in model.ei] if model.ei else None,
        model.ea * phi if model.ea is not None else None,
        model.parameters,
    )
    try:
        other = solve_beam(scaled)
    except DataError as exc:
        return _single("dimensional scaling (lengths x3, forces x7)", False, str(exc))
    good = True
    for piece_v, piece_m, scaled_v, scaled_m in zip(solution.V.pieces, solution.M.pieces, other.V.pieces, other.M.pieces, strict=True):
        if sympy.simplify(sympy.expand(scaled_v.expr.subs(X, lam * X) - phi * piece_v.expr)) != 0:
            good = False
        if sympy.simplify(sympy.expand(scaled_m.expr.subs(X, lam * X) - phi * lam * piece_m.expr)) != 0:
            good = False
    if solution.v is not None and other.v is not None:
        for piece, scaled_piece in zip(solution.v.pieces, other.v.pieces, strict=True):
            if sympy.simplify(sympy.expand(scaled_piece.expr.subs(X, lam * X) - lam * piece.expr)) != 0:
                good = False
    return _single(
        "dimensional scaling (lengths x3, forces x7): V scales as force, M as force*length, v as length",
        good,
        "",
    )


def _single(name: str, passed: bool, detail: str) -> Evidence:
    evidence = Evidence()
    evidence.add(name, "dimensional", passed, detail)
    return evidence


# --------------------------------------------------------------------------- author claims


def check_claims(solution: BeamSolution, claims: object) -> Evidence:
    """Compare values an author states with the solution.

    ``claims`` may hold ``reactions`` (name to value), ``values`` (function, at,
    side, value), ``extrema`` (function, kind max/min, value, optional at) and
    ``pieces`` (function, from, to, expr). A decimal claim must equal the exact
    result rounded to the claim's own decimals; an exact claim must be equal.
    """

    evidence = Evidence()
    if not isinstance(claims, dict):
        evidence.add("claims are readable", "symbolic", False, "claims must be an object")
        return evidence
    model = solution.model

    def where(value: object) -> sympy.Expr:
        if isinstance(value, str) and value.strip() in model.points:
            return model.points[value.strip()]
        return exact(value, "claim position", model.parameters)

    curves = {"N": solution.N, "V": solution.V, "M": solution.M, "theta": solution.theta, "v": solution.v}
    for name, value in (claims.get("reactions") or {}).items():
        actual = solution.reactions.get(str(name))
        if actual is None:
            evidence.add(f"claimed reaction {name}", "symbolic", False, "no such reaction")
            continue
        evidence.add(*compare(f"claimed reaction {name}", value, actual, model.parameters))
    for item in claims.get("values") or []:
        if not isinstance(item, dict):
            continue
        curve = curves.get(str(item.get("function")))
        if curve is None:
            evidence.add("claimed value", "symbolic", False, f"unknown function {item.get('function')!r}")
            continue
        place = where(item.get("at"))
        side = item.get("side", "both")
        actual = curve.left(place) if side == "left" else curve.right(place)
        if side == "both" and sympy.simplify(curve.jump(place)) != 0:
            evidence.add(f"claimed {curve.name}({place})", "symbolic", False, "the function jumps there; say left or right")
            continue
        evidence.add(*compare(f"claimed {curve.name}({place}, {side})", item.get("value"), actual, model.parameters))
    for item in claims.get("extrema") or []:
        if not isinstance(item, dict):
            continue
        curve = curves.get(str(item.get("function")))
        if curve is None or not curve.is_numeric():
            evidence.add("claimed extremum", "symbolic", False, "unknown or non-numeric function")
            continue
        kind = "max" if item.get("kind") == "max" else "min"
        found = extremes(curve)[kind]
        evidence.add(*compare(f"claimed {kind} of {curve.name}", item.get("value"), found.value, model.parameters))
        if item.get("at") is not None:
            evidence.add(*compare(f"claimed position of the {kind} of {curve.name}", item.get("at"), found.x, model.parameters))
    for item in claims.get("pieces") or []:
        if not isinstance(item, dict):
            continue
        curve = curves.get(str(item.get("function")))
        if curve is None:
            evidence.add("claimed piece", "symbolic", False, "unknown function")
            continue
        start, end = where(item.get("from")), where(item.get("to"))
        middle = (start + end) / 2
        piece = curve.piece_at(middle)
        symbols = {"x": X, **model.parameters}
        try:
            claimed = sympify_text(str(item.get("expr")), locals=symbols, rational=True)
        except (sympy.SympifyError, SyntaxError, TypeError):
            evidence.add(f"claimed {curve.name} on ({start}, {end})", "symbolic", False, "the expression cannot be read")
            continue
        covered = as_float(piece.start) <= as_float(start) and as_float(end) <= as_float(piece.end)
        difference = sympy.simplify(sympy.expand(claimed - piece.expr))
        evidence.add(
            f"claimed {curve.name}(x) on ({start}, {end})",
            "symbolic",
            covered and difference == 0,
            "" if covered else "the interval crosses a breakpoint of the solution",
            residual=difference,
        )
    return evidence


# --------------------------------------------------------------------------- export


def solution_data(solution: BeamSolution, decimals: int = 6) -> dict[str, object]:
    """JSON-ready solution: exact values as text, decimals for reading."""

    def number(value: sympy.Expr) -> dict[str, object]:
        data: dict[str, object] = {"exact": str(value)}
        if value.is_number:
            data["decimal"] = round(as_float(value), decimals)
        return data

    data: dict[str, object] = {
        "reactions": {name: number(value) for name, value in solution.reactions.items()},
        "N": solution.N.as_dict(),
        "V": solution.V.as_dict(),
        "M": solution.M.as_dict(),
        "breakpoints": [str(value) for value in solution.model.breakpoints()],
        "degree_of_indeterminacy": solution.degree,
        "convention": solution.model.convention.as_dict(),
        "units": {
            "force": solution.model.units["force"],
            "length": solution.model.units["length"],
            "moment": f"{solution.model.units['force']}·{solution.model.units['length']}",
            "distributed": f"{solution.model.units['force']}/{solution.model.units['length']}",
        },
        "notes": list(solution.notes),
    }
    for name, curve in (("V", solution.V), ("M", solution.M)):
        if curve.is_numeric():
            found = extremes(curve)
            data[f"{name}_extremes"] = {
                kind: {"x": number(item.x), "value": number(item.value)} for kind, item in found.items()
            }
    if solution.theta is not None and solution.v is not None:
        data["theta"] = solution.theta.as_dict()
        data["v"] = solution.v.as_dict()
        if solution.v.is_numeric():
            found = extremes(solution.v)
            data["v_extremes"] = {kind: {"x": number(item.x), "value": number(item.value)} for kind, item in found.items()}
    return data


# --------------------------------------------------------------------------- typeset laws


def _tex_number(value: sympy.Expr, comma: bool, decimals: int = 4) -> str:
    number = sympy.sympify(value)
    if isinstance(number, sympy.Integer):
        text = str(number)
    else:
        text = f"{as_float(number):.{decimals}f}".rstrip("0").rstrip(".")
    if comma:
        text = text.replace(".", "{,}")
    return text


def _tex_poly(expr: sympy.Expr, comma: bool) -> str:
    """A polynomial in x with readable decimal coefficients, highest power first."""

    expanded = sympy.expand(expr)
    if expanded.free_symbols - {X} or not expanded.is_polynomial(X):
        return sympy.latex(expanded)
    terms = sympy.Poly(expanded, X).terms()
    if not terms:
        return "0"
    pieces: list[tuple[str, str]] = []
    for (power,), coefficient in terms:
        if coefficient == 0:
            continue
        negative = as_float(coefficient) < 0
        magnitude = -coefficient if negative else coefficient
        number = _tex_number(magnitude, comma)
        if power == 0:
            body = number
        else:
            variable = "x" if power == 1 else f"x^{{{power}}}"
            body = variable if number == "1" else f"{number}\\,{variable}"
        sign = "-" if negative else "+"
        pieces.append((sign, body))
    first_sign, first_body = pieces[0]
    text = ("-" if first_sign == "-" else "") + first_body
    for sign, body in pieces[1:]:
        text += f" {sign} {body}"
    return text


def laws_latex(solution: BeamSolution, *, comma: bool = True) -> list[str]:
    """Display-math blocks with the piecewise laws N, V, M (and v when solved)."""

    blocks: list[str] = []
    curves = [("N", solution.N), ("V", solution.V), ("M", solution.M)]
    for name, curve in curves:
        if name == "N" and all(sympy.simplify(piece.expr) == 0 for piece in curve.pieces):
            continue
        merged: list[list[sympy.Expr]] = []
        for piece in curve.pieces:
            # Neighbouring intervals with the same law are one interval of the law.
            if merged and sympy.expand(merged[-1][2] - piece.expr) == 0:
                merged[-1][1] = piece.end
            else:
                merged.append([piece.start, piece.end, piece.expr])
        rows = []
        for start, end, expr in merged:
            interval = f"{_tex_number(start, comma)} < x < {_tex_number(end, comma)}"
            rows.append(f"{_tex_poly(expr, comma)} & {interval}")
        blocks.append(f"{name}(x) = \\begin{{cases}} " + " \\\\ ".join(rows) + " \\end{cases}")
    return blocks


# --------------------------------------------------------------------------- virtual work


@dataclass
class VirtualWork:
    virtual: BeamSolution
    work: sympy.Expr  # int M m / EI dx
    elastic: sympy.Expr  # the same displacement read from the elastic line
    kind: str  # "deflection" or "rotation"
    at: sympy.Expr


def virtual_work(real: BeamSolution, unit: object) -> VirtualWork:
    """Displacement at a point by the unit-load method, and the same value from the elastic line.

    ``unit`` is ``{"type": "point", "at": ..., "direction": "down"}`` (a deflection in
    that direction) or ``{"type": "couple", "at": ..., "sense": "ccw"}`` (a rotation).
    """

    model = real.model
    if model.ei is None or real.v is None or real.theta is None:
        raise DataError("the unit-load method needs EI")
    if not isinstance(unit, dict) or unit.get("type") not in ("point", "couple"):
        raise DataError("virtual must be a unit point load or a unit couple")
    at_raw = unit.get("at")
    at = model.points[at_raw] if isinstance(at_raw, str) and at_raw in model.points else exact(at_raw, "virtual.at")
    forces: list[PointForce] = []
    couples: list[Couple] = []
    if unit["type"] == "point":
        direction = unit.get("direction", "down")
        if direction not in ("up", "down"):
            raise DataError("a virtual unit force must point up or down")
        forces.append(PointForce(at, sympy.Integer(0), sympy.Integer(1 if direction == "up" else -1), "1"))
        kind = "deflection"
    else:
        sense = unit.get("sense", "ccw")
        if sense not in ("ccw", "cw"):
            raise DataError("a virtual unit couple turns ccw or cw")
        couples.append(Couple(at, sympy.Integer(1 if sense == "ccw" else -1), "1"))
        kind = "rotation"
    virtual_model = BeamModel(
        model.length, model.supports, model.hinges, forces, couples, [], dict(model.points), model.units, model.convention, model.ei, model.ea, model.parameters
    )
    virtual = solve_beam(virtual_model)
    places = sorted({*model.breakpoints(), *virtual_model.breakpoints()}, key=as_float)
    work = sympy.Integer(0)
    for a, b in pairwise(places):
        middle = (a + b) / 2
        product = real.M.piece_at(middle).expr * virtual.M.piece_at(middle).expr / _ei_at(model, a, b)
        work += sympy.integrate(product, (X, a, b))
    work = sympy.simplify(work)
    if kind == "deflection":
        value = real.v.right(at) if as_float(at) < as_float(model.length) else real.v.left(at)
        elastic = -value if unit.get("direction", "down") == "down" else value
    else:
        if any(sympy.simplify(at - hinge) == 0 for hinge in model.hinges):
            raise DataError("a rotation exactly at a hinge has two values; put the unit couple beside it")
        value = real.theta.right(at) if as_float(at) < as_float(model.length) else real.theta.left(at)
        elastic = value if unit.get("sense", "ccw") == "ccw" else -value
    return VirtualWork(virtual, work, sympy.simplify(elastic), kind, at)


def verify_virtual_work(result: VirtualWork, claims: object = None) -> Evidence:
    evidence = verify_beam(result.virtual)
    difference = sympy.simplify(result.work - result.elastic)
    evidence.add(
        f"unit-load {result.kind} equals the elastic line at x = {result.at}",
        "symbolic",
        difference == 0,
        f"virtual work {result.work}, elastic line {result.elastic}",
        residual=difference,
    )
    if isinstance(claims, dict) and "displacement" in claims:
        evidence.add(*compare(f"claimed {result.kind}", claims["displacement"], result.work, result.virtual.model.parameters))
    return evidence
