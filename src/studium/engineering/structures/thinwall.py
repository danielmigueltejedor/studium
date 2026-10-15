"""Thin-walled sections: shear flow, shear centre and torsion of open, closed and multicell sections.

Data (section coordinates ``z``, ``y`` of the wall mid-lines; axis directions from
the declared convention)::

    {
      "nodes": {"A": [0, 0], "B": [100, 0], ...},
      "walls": [{"from": "A", "to": "B", "t": 2}, ...],
      "booms": [{"at": "A", "area": 400}],          # optional idealised stringers
      "direct_stress_walls": true,                  # false: idealised skin carries shear only
      "cells": [["A", "B", "C", "D"]],              # every closed cell, as a node loop
      "shear": {"Vy": 1000, "Vz": 0, "at": [50, 30]},  # or "at": "shear_centre"
      "torque": 0, "G": 27000,
      "units": {"length": "mm", "force": "N"},
      "convention": "ule-teoria-estructuras"
    }

The flow on each wall is ``q(s)``, positive from ``from`` to ``to``. On every wall
``dq/ds = -t (alpha y + beta z)`` (wall equilibrium with ``d sigma/dx = alpha y + beta z``);
at every node the flows balance, a boom adding ``-B (alpha y + beta z)``. ``alpha``
and ``beta`` are fixed by asking the flows to resolve into the applied shear
``(Vy, Vz)``. Closed cells add one constant flow each, found from moment
equilibrium and equal twist of all cells. The torque about the x axis of a force
``(Fy, Fz)`` at ``(z, y)`` is ``y Fz - z Fy``; a constant flow ``q`` round a cell
of area ``A`` traversed in the positive sense gives ``2 A q`` (Bredt).

Checks recompute the flow resultant and moment by direct integration, test
conservation at every node, the derivative of ``q`` on every wall, equal twist
of the cells and a length/force scaling.
"""

from dataclasses import dataclass, field

import sympy

from studium.diagrams.evidence import Evidence
from studium.diagrams.piecewise import DataError, as_float, exact
from studium.engineering.structures.claims import compare
from studium.engineering.structures.convention import Convention, parse_convention

S = sympy.Symbol("s", real=True)
_MAX = 60


@dataclass(frozen=True)
class Wall:
    name: str
    start: str
    end: str
    t: sympy.Expr
    t_direct: sympy.Expr


@dataclass
class ThinWallModel:
    nodes: dict[str, tuple[sympy.Expr, sympy.Expr]]
    walls: list[Wall]
    booms: dict[str, sympy.Expr]
    cells: list[list[str]]
    vy: sympy.Expr
    vz: sympy.Expr
    at: tuple[sympy.Expr, sympy.Expr] | str | None
    torque: sympy.Expr
    shear_modulus: sympy.Expr | None
    units: dict[str, str]
    convention: Convention


@dataclass
class ThinWallSolution:
    model: ThinWallModel
    area: sympy.Expr
    centroid: tuple[sympy.Expr, sympy.Expr]
    Iz: sympy.Expr
    Iy: sympy.Expr
    Iyz: sympy.Expr
    alpha: sympy.Expr
    beta: sympy.Expr
    flows: dict[str, sympy.Expr]  # wall name -> q(s), s from the wall start, centroidal data
    shear_centre: tuple[sympy.Expr, sympy.Expr]
    twist_rate: sympy.Expr | None  # theta' (or theta' * G when G is not given)
    cell_flows: list[sympy.Expr]
    open_torque: sympy.Expr  # torque left to St Venant torsion of the open walls
    j_open: sympy.Expr
    notes: list[str] = field(default_factory=list)


def parse_thin_wall(spec: object) -> ThinWallModel:
    if not isinstance(spec, dict):
        raise DataError("a thin-walled section must be an object")
    raw_nodes = spec.get("nodes")
    if not isinstance(raw_nodes, dict) or not 2 <= len(raw_nodes) <= _MAX:
        raise DataError("nodes must map names to [z, y]")
    nodes: dict[str, tuple[sympy.Expr, sympy.Expr]] = {}
    for name, value in raw_nodes.items():
        if not isinstance(value, list) or len(value) != 2:
            raise DataError(f"node {name} must be [z, y]")
        nodes[str(name)] = (exact(value[0], f"nodes.{name}"), exact(value[1], f"nodes.{name}"))
    direct = spec.get("direct_stress_walls", True) is not False
    raw_walls = spec.get("walls")
    if not isinstance(raw_walls, list) or not raw_walls or len(raw_walls) > _MAX:
        raise DataError("walls must be a non-empty list")
    walls: list[Wall] = []
    for index, item in enumerate(raw_walls):
        if not isinstance(item, dict) or item.get("from") not in nodes or item.get("to") not in nodes or item.get("from") == item.get("to"):
            raise DataError(f"walls[{index}] needs from and to among the nodes")
        t = exact(item.get("t"), f"walls[{index}].t")
        if not bool(t > 0):
            raise DataError(f"walls[{index}].t must be positive")
        name = str(item.get("name") or f"{item['from']}{item['to']}")
        walls.append(Wall(name, str(item["from"]), str(item["to"]), t, t if direct else sympy.Integer(0)))
    if len({wall.name for wall in walls}) != len(walls):
        raise DataError("wall names must be unique")
    booms: dict[str, sympy.Expr] = {}
    for index, item in enumerate(spec.get("booms") or []):
        if not isinstance(item, dict) or item.get("at") not in nodes:
            raise DataError(f"booms[{index}] needs at (a node) and area")
        booms[str(item["at"])] = booms.get(str(item["at"]), sympy.Integer(0)) + exact(item.get("area"), f"booms[{index}].area")
    cells = []
    for index, loop in enumerate(spec.get("cells") or []):
        if not isinstance(loop, list) or len(loop) < 3 or any(node not in nodes for node in loop):
            raise DataError(f"cells[{index}] must be a loop of at least three nodes")
        cells.append([str(node) for node in loop])
    used = {wall.start for wall in walls} | {wall.end for wall in walls}
    if set(nodes) - used:
        raise DataError(f"nodes without walls: {', '.join(sorted(set(nodes) - used))}")
    independent = len(walls) - len(nodes) + 1
    if independent != len(cells):
        raise DataError(f"the walls form {independent} closed cells; list each one in cells")
    shear = spec.get("shear") or {}
    if not isinstance(shear, dict):
        raise DataError("shear must be an object with Vy, Vz and at")
    vy = exact(shear.get("Vy", 0), "shear.Vy")
    vz = exact(shear.get("Vz", 0), "shear.Vz")
    at_value = shear.get("at")
    at: tuple[sympy.Expr, sympy.Expr] | str | None
    if at_value is None or at_value == "shear_centre":
        at = "shear_centre"
    elif isinstance(at_value, str) and at_value in nodes:
        at = nodes[at_value]
    elif isinstance(at_value, list) and len(at_value) == 2:
        at = (exact(at_value[0], "shear.at"), exact(at_value[1], "shear.at"))
    else:
        raise DataError("shear.at must be [z, y], a node name or shear_centre")
    g_value = spec.get("G")
    units = {"length": "mm", "force": "N"}
    raw_units = spec.get("units")
    if isinstance(raw_units, dict):
        for key in ("length", "force"):
            if isinstance(raw_units.get(key), str) and raw_units[key].strip():
                units[key] = raw_units[key].strip()
    return ThinWallModel(
        nodes,
        walls,
        booms,
        cells,
        vy,
        vz,
        at,
        exact(spec.get("torque", 0), "torque"),
        exact(g_value, "G") if g_value is not None else None,
        units,
        parse_convention(spec.get("convention")),
    )


def _geometry(model: ThinWallModel, wall: Wall) -> tuple[sympy.Expr, sympy.Expr, sympy.Expr, sympy.Expr, sympy.Expr, sympy.Expr]:
    z0, y0 = model.nodes[wall.start]
    z1, y1 = model.nodes[wall.end]
    length = sympy.sqrt((z1 - z0) ** 2 + (y1 - y0) ** 2)
    return z0, y0, z1, y1, length, length


def _wall_moments(model: ThinWallModel, wall: Wall, t: sympy.Expr):
    z0, y0, z1, y1, length, _ = _geometry(model, wall)
    area = t * length
    sz = t * length * (z0 + z1) / 2
    sy = t * length * (y0 + y1) / 2
    zz = t * length * (z0**2 + z0 * z1 + z1**2) / 3
    yy = t * length * (y0**2 + y0 * y1 + y1**2) / 3
    yz = t * length * (2 * y0 * z0 + y0 * z1 + y1 * z0 + 2 * y1 * z1) / 6
    return area, sy, sz, yy, zz, yz


def _properties(model: ThinWallModel) -> tuple[sympy.Expr, tuple[sympy.Expr, sympy.Expr], sympy.Expr, sympy.Expr, sympy.Expr]:
    totals: list[sympy.Expr] = [sympy.Integer(0)] * 6
    for wall in model.walls:
        for index, value in enumerate(_wall_moments(model, wall, wall.t_direct)):
            totals[index] += value
    for node, area in model.booms.items():
        z, y = model.nodes[node]
        for index, value in enumerate((area, area * y, area * z, area * y * y, area * z * z, area * y * z)):
            totals[index] += value
    area, sy, sz, yy, zz, yz = (sympy.radsimp(sympy.expand(v)) for v in totals)
    if area == 0:
        raise DataError("no wall or boom carries direct stress; give booms or direct_stress_walls")
    zg, yg = sympy.radsimp(sz / area), sympy.radsimp(sy / area)
    iz = sympy.radsimp(sympy.expand(yy - area * yg**2))
    iy = sympy.radsimp(sympy.expand(zz - area * zg**2))
    iyz = sympy.radsimp(sympy.expand(yz - area * yg * zg))
    return area, (zg, yg), iz, iy, iyz


def _open_increment(model: ThinWallModel, wall: Wall, alpha: sympy.Expr, beta: sympy.Expr, centroid) -> sympy.Expr:
    """``-int_0^s t (alpha y + beta z) ds`` along the wall, in centroidal coordinates."""

    z0, y0, z1, y1, length, _ = _geometry(model, wall)
    zg, yg = centroid
    y = (y0 - yg) + (y1 - y0) * S / length
    z = (z0 - zg) + (z1 - z0) * S / length
    return sympy.expand(-wall.t_direct * sympy.integrate(alpha * y + beta * z, (S, 0, S)))


def _flow_moment(model: ThinWallModel, wall: Wall, q: sympy.Expr, about: tuple[sympy.Expr, sympy.Expr]) -> sympy.Expr:
    """Torque about the x axis through ``about`` of the flow ``q(s)`` on one straight wall."""

    z0, y0, z1, y1, length, _ = _geometry(model, wall)
    uz, uy = (z1 - z0) / length, (y1 - y0) / length
    arm = (y0 - about[1]) * uz - (z0 - about[0]) * uy
    return sympy.expand(arm * sympy.integrate(q, (S, 0, length)))


def _cell_orientation(model: ThinWallModel, loop: list[str]) -> tuple[list[tuple[Wall, int]], sympy.Expr]:
    """Walls of a cell with +1/-1 traversal signs in the positive (torque) sense, and its area."""

    pairs = list(zip(loop, loop[1:] + loop[:1], strict=True))
    signed: sympy.Expr = sympy.Add(*((model.nodes[a][0] * model.nodes[b][1] - model.nodes[b][0] * model.nodes[a][1]) / 2 for a, b in pairs))
    # A constant flow round the loop gives a torque -2 * signed_area * q; the positive sense needs signed < 0.
    if as_float(signed) > 0:
        loop = [loop[0], *reversed(loop[1:])]
        pairs = list(zip(loop, loop[1:] + loop[:1], strict=True))
        signed = -signed
    walls = []
    for a, b in pairs:
        wall = next((w for w in model.walls if (w.start, w.end) in ((a, b), (b, a))), None)
        if wall is None:
            raise DataError(f"no wall joins {a} and {b} in a cell")
        walls.append((wall, 1 if (wall.start, wall.end) == (a, b) else -1))
    return walls, -signed


def solve_thin_wall(model: ThinWallModel) -> ThinWallSolution:
    area, centroid, iz, iy, iyz = _properties(model)
    det = iz * iy - iyz**2
    if det == 0:
        raise DataError("the section has no bending stiffness in some direction")
    alpha = sympy.radsimp((model.vy * iy - model.vz * iyz) / det)
    beta = sympy.radsimp((model.vz * iz - model.vy * iyz) / det)
    flows, twist = _flows(model, centroid, alpha, beta)
    # Shear centre: flows of unit shears through it carry no torque (open) or produce no twist (closed).
    centre = _shear_centre(model, centroid, iz, iy, iyz)
    j_open = sum((sympy.sqrt((model.nodes[w.end][0] - model.nodes[w.start][0]) ** 2 + (model.nodes[w.end][1] - model.nodes[w.start][1]) ** 2) * w.t**3 / 3 for w in model.walls), sympy.Integer(0))
    open_torque = sympy.Integer(0)
    if not model.cells:
        applied = _applied_moment(model, centroid, centre)
        carried = sum((_flow_moment(model, w, flows[w.name], centroid) for w in model.walls), sympy.Integer(0))
        open_torque = sympy.radsimp(sympy.expand(applied - carried))
    solution = ThinWallSolution(model, area, centroid, iz, iy, iyz, alpha, beta, flows, centre, twist, [], open_torque, sympy.radsimp(j_open))
    solution.cell_flows = cell_flow_values(solution)
    return solution


def _applied_moment(model: ThinWallModel, centroid, centre) -> sympy.Expr:
    point = centre if model.at == "shear_centre" else model.at
    assert isinstance(point, tuple)
    return (point[1] - centroid[1]) * model.vz - (point[0] - centroid[0]) * model.vy + model.torque


def _flows(model: ThinWallModel, centroid, alpha, beta, *, zero_twist: bool = False, applied: sympy.Expr | None = None):
    """Wall flows from conservation, moment equilibrium and equal twist."""

    constants = {wall.name: sympy.Symbol(f"q0_{index}") for index, wall in enumerate(model.walls)}
    flows = {wall.name: constants[wall.name] + _open_increment(model, wall, alpha, beta, centroid) for wall in model.walls}
    equations = []
    zg, yg = centroid
    for node, (z, y) in model.nodes.items():
        outgoing = sum((flows[w.name].subs(S, 0) for w in model.walls if w.start == node), sympy.Integer(0))
        incoming = sum((flows[w.name].subs(S, _geometry(model, w)[4]) for w in model.walls if w.end == node), sympy.Integer(0))
        boom = model.booms.get(node, sympy.Integer(0))
        equations.append(sympy.expand(outgoing - incoming + boom * (alpha * (y - yg) + beta * (z - zg))))
    equations = equations[:-1]  # one balance follows from the others
    twist = None
    unknowns = list(constants.values())
    if model.cells:
        twist_symbol = sympy.Symbol("twist")
        for loop in model.cells:
            walls, cell_area = _cell_orientation(model, loop)
            circulation = sum((sign * sympy.integrate(flows[w.name], (S, 0, _geometry(model, w)[4])) / w.t for w, sign in walls), sympy.Integer(0))
            g = model.shear_modulus if model.shear_modulus is not None else sympy.Integer(1)
            equations.append(sympy.expand(circulation / (2 * cell_area * g) - (0 if zero_twist else twist_symbol)))
        if not zero_twist:
            target = applied if applied is not None else _applied_moment(model, centroid, _shear_centre(model, centroid, *_properties(model)[2:]))
            moment = sum((_flow_moment(model, w, flows[w.name], centroid) for w in model.walls), sympy.Integer(0))
            equations.append(sympy.expand(moment - target))
            unknowns.append(twist_symbol)
    solution = sympy.solve(equations, unknowns, dict=True)
    if len(solution) != 1 or any(symbol not in solution[0] for symbol in constants.values()):
        raise DataError("the flows are not determined; check the walls and the cells")
    values = solution[0]
    solved = {name: sympy.radsimp(sympy.expand(expr.subs(values))) for name, expr in flows.items()}
    if model.cells:
        twist = sympy.radsimp(values.get(sympy.Symbol("twist"), sympy.Integer(0))) if not zero_twist else sympy.Integer(0)
    return solved, twist


def _shear_centre(model: ThinWallModel, centroid, iz, iy, iyz) -> tuple[sympy.Expr, sympy.Expr]:
    det = iz * iy - iyz**2
    results = []
    for vy, vz in ((1, 0), (0, 1)):
        alpha = sympy.radsimp((vy * iy - vz * iyz) / det)
        beta = sympy.radsimp((vz * iz - vy * iyz) / det)
        flows, _ = _flows(model, centroid, alpha, beta, zero_twist=True)
        results.append(sum((_flow_moment(model, w, flows[w.name], centroid) for w in model.walls), sympy.Integer(0)))
    # Unit Vy at (z_sc, y_sc): torque -(z_sc - zg); unit Vz: (y_sc - yg).
    z_sc = sympy.radsimp(centroid[0] - results[0])
    y_sc = sympy.radsimp(centroid[1] + results[1])
    return z_sc, y_sc


def wall_length(model: ThinWallModel, wall: Wall) -> sympy.Expr:
    return _geometry(model, wall)[4]


def cell_flow_values(solution: ThinWallSolution) -> list[sympy.Expr]:
    """For pure torsion of closed cells: the circulating flow of each cell (from a wall it owns alone)."""

    values = []
    oriented = [_cell_orientation(solution.model, loop)[0] for loop in solution.model.cells]
    for walls in oriented:
        owned = [(w, sign) for w, sign in walls if sum(1 for other in oriented if any(x is w for x, _ in other)) == 1]
        if owned:
            wall, sign = owned[0]
            values.append(sympy.radsimp(sign * solution.flows[wall.name].subs(S, 0)))
        else:
            values.append(sympy.nan)
    return values


def verify_thin_wall(solution: ThinWallSolution, claims: object = None) -> Evidence:
    model = solution.model
    evidence = Evidence()
    zg, yg = solution.centroid
    # 1. Resultant of the flows equals the applied shear.
    fy = fz = sympy.Integer(0)
    for wall in model.walls:
        z0, y0, z1, y1, length, _ = _geometry(model, wall)
        total = sympy.integrate(solution.flows[wall.name], (S, 0, length))
        fy += total * (y1 - y0) / length
        fz += total * (z1 - z0) / length
    evidence.add("flow resultant equals Vy", "symbolic", sympy.radsimp(sympy.expand(fy - model.vy)) == 0, residual=sympy.N(fy - model.vy, 6))
    evidence.add("flow resultant equals Vz", "symbolic", sympy.radsimp(sympy.expand(fz - model.vz)) == 0, residual=sympy.N(fz - model.vz, 6))
    # 2. Balance at every node.
    balanced = True
    for node, (z, y) in model.nodes.items():
        outgoing = sum((solution.flows[w.name].subs(S, 0) for w in model.walls if w.start == node), sympy.Integer(0))
        incoming = sum((solution.flows[w.name].subs(S, wall_length(model, w)) for w in model.walls if w.end == node), sympy.Integer(0))
        boom = model.booms.get(node, sympy.Integer(0))
        if sympy.radsimp(sympy.expand(outgoing - incoming + boom * (solution.alpha * (y - yg) + solution.beta * (z - zg)))) != 0:
            balanced = False
    evidence.add("flows balance at every node (free edges carry no flow)", "symbolic", balanced)
    # 3. Wall equilibrium dq/ds = -t (alpha y + beta z).
    derivative_ok = True
    for wall in model.walls:
        z0, y0, z1, y1, length, _ = _geometry(model, wall)
        y = (y0 - yg) + (y1 - y0) * S / length
        z = (z0 - zg) + (z1 - z0) * S / length
        if sympy.radsimp(sympy.expand(sympy.diff(solution.flows[wall.name], S) + wall.t_direct * (solution.alpha * y + solution.beta * z))) != 0:
            derivative_ok = False
    evidence.add("dq/ds = -t (alpha y + beta z) on every wall", "symbolic", derivative_ok)
    # 4. Moment: closed sections carry the applied torque; open sections leave the rest to St Venant torsion.
    moment = sum((_flow_moment(model, w, solution.flows[w.name], solution.centroid) for w in model.walls), sympy.Integer(0))
    applied = _applied_moment(model, solution.centroid, solution.shear_centre)
    evidence.add(
        "flow torque plus open-wall St Venant torque equals the applied torque",
        "symbolic",
        sympy.radsimp(sympy.expand(moment + solution.open_torque - applied)) == 0,
    )
    # 5. Equal twist of all cells.
    if model.cells:
        rates = []
        for loop in model.cells:
            walls, cell_area = _cell_orientation(model, loop)
            circulation = sum((sign * sympy.integrate(solution.flows[w.name], (S, 0, wall_length(model, w))) / w.t for w, sign in walls), sympy.Integer(0))
            g = model.shear_modulus if model.shear_modulus is not None else sympy.Integer(1)
            rates.append(sympy.radsimp(sympy.expand(circulation / (2 * cell_area * g))))
        same = all(sympy.radsimp(sympy.expand(rate - rates[0])) == 0 for rate in rates)
        evidence.add("all cells twist at the same rate", "symbolic", same and sympy.radsimp(sympy.expand(rates[0] - (solution.twist_rate or 0))) == 0)
    # 6. Shear centre: a shear through it, alone, needs no torque.
    centre_check = _shear_centre(model, solution.centroid, solution.Iz, solution.Iy, solution.Iyz)
    evidence.add(
        "shear centre recomputed from unit shears agrees",
        "symbolic",
        all(sympy.radsimp(sympy.expand(a - b)) == 0 for a, b in zip(centre_check, solution.shear_centre, strict=True)),
    )
    # 7. Scaling: lengths x3, forces x7 -> q scales by 7/3, the shear centre by 3.
    evidence.extend(_scaling(solution))
    if claims is not None:
        evidence.extend(check_thin_wall_claims(solution, claims))
    return evidence


def _scaling(solution: ThinWallSolution) -> Evidence:
    model = solution.model
    lam, phi = sympy.Integer(3), sympy.Integer(7)
    scaled = ThinWallModel(
        {k: (v[0] * lam, v[1] * lam) for k, v in model.nodes.items()},
        [Wall(w.name, w.start, w.end, w.t * lam, w.t_direct * lam) for w in model.walls],
        {k: v * lam**2 for k, v in model.booms.items()},
        model.cells,
        model.vy * phi,
        model.vz * phi,
        model.at if isinstance(model.at, str) or model.at is None else (model.at[0] * lam, model.at[1] * lam),
        model.torque * phi * lam,
        model.shear_modulus * phi / lam**2 if model.shear_modulus is not None else None,
        model.units,
        model.convention,
    )
    evidence = Evidence()
    try:
        other = solve_thin_wall(scaled)
    except DataError as exc:
        evidence.add("dimensional scaling", "dimensional", False, str(exc))
        return evidence
    good = all(
        sympy.radsimp(sympy.expand(other.flows[name].subs(S, lam * S) - phi / lam * solution.flows[name])) == 0 for name in solution.flows
    ) and all(sympy.radsimp(a - lam * b) == 0 for a, b in zip(other.shear_centre, solution.shear_centre, strict=True))
    evidence.add("dimensional scaling (lengths x3, forces x7): q as force/length, shear centre as length", "dimensional", good)
    return evidence


def max_shear_stress(solution: ThinWallSolution) -> tuple[sympy.Expr, str, sympy.Expr]:
    """Largest |q/t| over all walls: (value, wall, s)."""

    best = (sympy.Integer(0), "", sympy.Integer(0))
    for wall in solution.model.walls:
        length = wall_length(solution.model, wall)
        q = solution.flows[wall.name]
        places = [sympy.Integer(0), length]
        slope = sympy.diff(q, S)
        if slope.free_symbols:
            places += [root for root in sympy.solve(sympy.Eq(slope, 0), S) if root.is_real and 0 < as_float(root) < as_float(length)]
        for place in places:
            value = sympy.radsimp(q.subs(S, place) / wall.t)
            if abs(as_float(value)) > abs(as_float(best[0])):
                best = (value, wall.name, place)
    return best


def check_thin_wall_claims(solution: ThinWallSolution, claims: object) -> Evidence:
    evidence = Evidence()
    if not isinstance(claims, dict):
        evidence.add("claims are readable", "symbolic", False, "claims must be an object")
        return evidence
    centre = claims.get("shear_centre")
    if isinstance(centre, dict):
        for index, axis in enumerate(("z", "y")):
            if axis in centre:
                evidence.add(*compare(f"claimed shear centre {axis}", centre[axis], solution.shear_centre[index], {}))
    for item in claims.get("flows") or []:
        if not isinstance(item, dict) or item.get("wall") not in solution.flows:
            evidence.add("claimed flow", "symbolic", False, "unknown wall")
            continue
        wall = next(w for w in solution.model.walls if w.name == item["wall"])
        place = exact(item.get("s", 0), "claimed s") if item.get("s") != "end" else wall_length(solution.model, wall)
        evidence.add(*compare(f"claimed q on {wall.name} at s = {place}", item.get("value"), solution.flows[wall.name].subs(S, place), {}))
    if "tau_max" in claims:
        evidence.add(*compare("claimed maximum shear stress", claims["tau_max"], abs(max_shear_stress(solution)[0]), {}))
    if "twist_rate" in claims and solution.twist_rate is not None:
        evidence.add(*compare("claimed twist rate", claims["twist_rate"], solution.twist_rate, {}))
    for key, value in (("Iz", solution.Iz), ("Iy", solution.Iy), ("Iyz", solution.Iyz)):
        if key in claims:
            evidence.add(*compare(f"claimed {key}", claims[key], value, {}))
    return evidence


def thin_wall_data(solution: ThinWallSolution, decimals: int = 6) -> dict[str, object]:
    def number(value: sympy.Expr) -> dict[str, object]:
        return {"exact": str(value), "decimal": round(as_float(value), decimals)}

    tau = max_shear_stress(solution)
    model = solution.model
    data: dict[str, object] = {
        "area_direct": number(solution.area),
        "centroid": {"z": number(solution.centroid[0]), "y": number(solution.centroid[1])},
        "Iz": number(solution.Iz),
        "Iy": number(solution.Iy),
        "Iyz": number(solution.Iyz),
        "shear_centre": {"z": number(solution.shear_centre[0]), "y": number(solution.shear_centre[1])},
        "flows": {
            name: {
                "q(s)": str(expr),
                "start": number(expr.subs(S, 0)),
                "end": number(expr.subs(S, wall_length(model, next(w for w in model.walls if w.name == name)))),
                "length": number(wall_length(model, next(w for w in model.walls if w.name == name))),
            }
            for name, expr in solution.flows.items()
        },
        "tau_max": {"value": number(abs(tau[0])), "wall": tau[1], "s": number(tau[2])},
        "sign_note": "q(s) is positive from the wall's 'from' node to its 'to' node; torque about x is y*Fz - z*Fy",
        "convention": model.convention.as_dict(),
    }
    if solution.twist_rate is not None:
        key = "twist_rate" if model.shear_modulus is not None else "twist_rate_times_G"
        data[key] = number(solution.twist_rate)
    if not model.cells:
        data["open_wall_torque"] = number(solution.open_torque)
        data["J_open"] = number(solution.j_open)
    return data
