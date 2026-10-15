"""Plane stress states: principal stresses, Mohr's circle, yield criteria, and their drawings.

Data::

    {"sigma_x": 90, "sigma_y": 30, "tau_xy": 70, "sigma_z": 0,
     "yield": 250, "rotation_deg": 30, "units": {"stress": "MPa"},
     "convention": "ule-teoria-estructuras"}

``tau_xy`` acts on the face of normal +x in the +y direction. ``sigma_z`` is a
principal stress normal to the plane (0 in plane stress). Angles are measured
from x towards y. Mohr points follow the declared ``mohr_plot`` convention:
``x_point_minus_tau`` draws ``P_x = (sigma_x, -tau_xy)`` and ``P_y = (sigma_y, tau_xy)``
with the tau axis upward.

The exact results use radicals only; the checks replace trigonometric
simplification by the algebraic values ``cos 2t = (sigma_x - sigma_y)/(2R)`` and
``sin 2t = tau_xy / R`` on the principal direction.
"""

import math
import re
from dataclasses import dataclass

import sympy

from studium.diagrams.evidence import Evidence
from studium.diagrams.piecewise import DataError, as_float, exact, format_number
from studium.diagrams.tikz import fmt
from studium.engineering.structures.claims import compare
from studium.engineering.structures.convention import Convention, parse_convention

_COORD = re.compile(r"\((-?[0-9.]+),(-?[0-9.]+)\)")


@dataclass
class StressState:
    sx: sympy.Expr
    sy: sympy.Expr
    txy: sympy.Expr
    sz: sympy.Expr
    yield_stress: sympy.Expr | None
    rotation: sympy.Expr | None  # degrees
    unit: str
    convention: Convention


@dataclass
class StressSolution:
    state: StressState
    centre: sympy.Expr
    radius: sympy.Expr
    s1: sympy.Expr  # in-plane major
    s2: sympy.Expr  # in-plane minor
    principal: tuple[sympy.Expr, sympy.Expr, sympy.Expr]  # sorted, all three
    theta: sympy.Expr  # radians, from x to the direction of s1
    tau_in_plane: sympy.Expr
    tau_absolute: sympy.Expr
    von_mises: sympy.Expr
    tresca: sympy.Expr
    rotated: tuple[sympy.Expr, sympy.Expr, sympy.Expr] | None  # sigma_x', sigma_y', tau_x'y'


def parse_stress(spec: object) -> StressState:
    if not isinstance(spec, dict):
        raise DataError("a stress state must be an object")
    unit = "MPa"
    units = spec.get("units")
    if isinstance(units, dict) and isinstance(units.get("stress"), str) and units["stress"].strip():
        unit = units["stress"].strip()
    unknown = set(spec) - {"sigma_x", "sigma_y", "tau_xy", "sigma_z", "yield", "rotation_deg", "units", "convention"}
    if unknown:
        raise DataError(f"unknown stress-state fields: {', '.join(sorted(unknown))}")
    return StressState(
        exact(spec.get("sigma_x", 0), "sigma_x"),
        exact(spec.get("sigma_y", 0), "sigma_y"),
        exact(spec.get("tau_xy", 0), "tau_xy"),
        exact(spec.get("sigma_z", 0), "sigma_z"),
        exact(spec["yield"], "yield") if spec.get("yield") is not None else None,
        exact(spec["rotation_deg"], "rotation_deg") if spec.get("rotation_deg") is not None else None,
        unit,
        parse_convention(spec.get("convention")),
    )


def solve_stress(state: StressState) -> StressSolution:
    centre = (state.sx + state.sy) / 2
    radius = sympy.sqrt(((state.sx - state.sy) / 2) ** 2 + state.txy**2)
    s1, s2 = sympy.radsimp(centre + radius), sympy.radsimp(centre - radius)
    principal = tuple(sorted((s1, s2, state.sz), key=as_float, reverse=True))
    theta = sympy.atan2(2 * state.txy, state.sx - state.sy) / 2 if radius != 0 else sympy.Integer(0)
    a, b, c = principal
    tau_absolute = sympy.radsimp((a - c) / 2)
    von_mises = sympy.radsimp(sympy.sqrt(((a - b) ** 2 + (b - c) ** 2 + (c - a) ** 2) / 2))
    tresca = sympy.radsimp(a - c)
    rotated = None
    if state.rotation is not None:
        beta = sympy.pi * state.rotation / 180
        half = (state.sx - state.sy) / 2
        sxr = centre + half * sympy.cos(2 * beta) + state.txy * sympy.sin(2 * beta)
        syr = centre - half * sympy.cos(2 * beta) - state.txy * sympy.sin(2 * beta)
        txyr = -half * sympy.sin(2 * beta) + state.txy * sympy.cos(2 * beta)
        rotated = (sympy.radsimp(sympy.expand(sxr)), sympy.radsimp(sympy.expand(syr)), sympy.radsimp(sympy.expand(txyr)))
    return StressSolution(state, centre, radius, s1, s2, principal, theta, radius, tau_absolute, von_mises, tresca, rotated)  # type: ignore[arg-type]


def _zero(expr: sympy.Expr) -> bool:
    return sympy.radsimp(sympy.together(sympy.expand(expr))) == 0


def verify_stress(solution: StressSolution, claims: object = None) -> Evidence:
    state = solution.state
    evidence = Evidence()
    evidence.add("invariant: s1 + s2 = sigma_x + sigma_y", "symbolic", _zero(solution.s1 + solution.s2 - state.sx - state.sy))
    evidence.add("invariant: s1 s2 = sigma_x sigma_y - tau_xy^2", "symbolic", _zero(solution.s1 * solution.s2 - state.sx * state.sy + state.txy**2))
    if solution.radius != 0:
        c2 = (state.sx - state.sy) / (2 * solution.radius)
        s2 = state.txy / solution.radius
        normal = (state.sx + state.sy) / 2 + (state.sx - state.sy) / 2 * c2 + state.txy * s2
        shear = -(state.sx - state.sy) / 2 * s2 + state.txy * c2
        evidence.add("on the principal direction the shear vanishes and the normal stress is s1", "symbolic", _zero(shear) and _zero(normal - solution.s1))
        angle = 2 * as_float(solution.theta)
        evidence.add(
            "stored principal angle matches that direction",
            "numeric",
            abs(math.cos(angle) - as_float(c2)) < 1e-12 and abs(math.sin(angle) - as_float(s2)) < 1e-12,
        )
    px = (state.sx - solution.centre) ** 2 + state.txy**2 - solution.radius**2
    evidence.add("both face points lie on the Mohr circle", "symbolic", _zero(px))
    components = sympy.sqrt(
        ((state.sx - state.sy) ** 2 + (state.sy - state.sz) ** 2 + (state.sz - state.sx) ** 2 + 6 * state.txy**2) / 2
    )
    evidence.add("von Mises from components equals von Mises from principal stresses", "symbolic", _zero(components**2 - solution.von_mises**2))
    if solution.rotated is not None:
        sxr, syr, txyr = solution.rotated
        evidence.add("a rotated element keeps the invariants", "symbolic", _zero(sxr + syr - state.sx - state.sy) and _zero(sxr * syr - txyr**2 - state.sx * state.sy + state.txy**2))
    lam = sympy.Integer(7)
    scaled = solve_stress(StressState(state.sx * lam, state.sy * lam, state.txy * lam, state.sz * lam, None, state.rotation, state.unit, state.convention))
    evidence.add(
        "dimensional scaling (stresses x7): principal stresses and von Mises scale, angles do not",
        "dimensional",
        _zero(scaled.s1 - lam * solution.s1) and _zero(scaled.von_mises - lam * solution.von_mises) and _zero(scaled.theta - solution.theta),
    )
    if claims is not None:
        evidence.extend(_claims(solution, claims))
    return evidence


def _claims(solution: StressSolution, claims: object) -> Evidence:
    evidence = Evidence()
    if not isinstance(claims, dict):
        evidence.add("claims are readable", "symbolic", False, "claims must be an object")
        return evidence
    values = {
        "sigma_1": solution.s1,
        "sigma_2": solution.s2,
        "theta_p_deg": solution.theta * 180 / sympy.pi,
        "tau_max_in_plane": solution.tau_in_plane,
        "tau_max_absolute": solution.tau_absolute,
        "von_mises": solution.von_mises,
        "tresca": solution.tresca,
        "centre": solution.centre,
        "radius": solution.radius,
    }
    if solution.rotated is not None:
        values.update(zip(("sigma_x_rot", "sigma_y_rot", "tau_xy_rot"), solution.rotated, strict=True))
    for key, actual in values.items():
        if key in claims:
            evidence.add(*compare(f"claimed {key}", claims[key], actual, {}))
    if "yields" in claims:
        if solution.state.yield_stress is None:
            evidence.add("claimed yield verdict", "symbolic", False, "no yield stress in the data")
        else:
            verdict = as_float(solution.von_mises) >= as_float(solution.state.yield_stress)
            evidence.add("claimed von Mises yield verdict", "symbolic", verdict == bool(claims["yields"]), f"von Mises {as_float(solution.von_mises):.4g} vs yield {as_float(solution.state.yield_stress):.4g}")
    return evidence


def stress_data(solution: StressSolution, decimals: int = 6) -> dict[str, object]:
    def number(value: sympy.Expr) -> dict[str, object]:
        return {"exact": str(value), "decimal": round(as_float(value), decimals)}

    data: dict[str, object] = {
        "centre": number(solution.centre),
        "radius": number(solution.radius),
        "sigma_1": number(solution.s1),
        "sigma_2": number(solution.s2),
        "principal_sorted": [number(v) for v in solution.principal],
        "theta_p_deg": number(solution.theta * 180 / sympy.pi),
        "tau_max_in_plane": number(solution.tau_in_plane),
        "tau_max_absolute": number(solution.tau_absolute),
        "von_mises": number(solution.von_mises),
        "tresca": number(solution.tresca),
        "unit": solution.state.unit,
        "convention": solution.state.convention.as_dict(),
    }
    if solution.state.yield_stress is not None:
        data["yields_von_mises"] = as_float(solution.von_mises) >= as_float(solution.state.yield_stress)
        data["safety_factor_von_mises"] = number(solution.state.yield_stress / solution.von_mises)
    if solution.rotated is not None:
        data["rotated"] = {k: number(v) for k, v in zip(("sigma_x", "sigma_y", "tau_xy"), solution.rotated, strict=True)}
    return data


# --------------------------------------------------------------------------- drawings


def _n(value: object, comma: bool) -> str:
    return format_number(value, decimals=2, comma=comma)


def mohr_figure(solution: StressSolution, *, comma: bool = True) -> str:
    state = solution.state
    span = max(abs(as_float(v)) for v in (*solution.principal, solution.radius, 1e-12))
    k = 2.6 / max(span, as_float(solution.radius) * 1.2)
    sign = -1 if state.convention.get("mohr_plot") == "x_point_minus_tau" else 1
    lo = min(as_float(v) for v in solution.principal) - 0.15 * span
    hi = max(as_float(v) for v in solution.principal) + 0.15 * span
    r = as_float(solution.radius) * k
    lines = [
        f"\\draw[-stealth] ({fmt(min(lo, 0) * k)},0) -- ({fmt(max(hi, 0) * k + 0.4)},0) node[right,font=\\small] {{$\\sigma$}};",
        f"\\draw[-stealth] (0,{fmt(-r - 0.4)}) -- (0,{fmt(r + 0.5)}) node[above,font=\\small] {{$\\tau$}};",
    ]
    circles = [(solution.s1, solution.s2, "thick")]
    if all(as_float(state.sz) != as_float(v) for v in (solution.s1, solution.s2)):
        a, b, c = solution.principal
        circles += [(a, c, "densely dashed,gray"), (b, c, "densely dashed,gray"), (a, b, "densely dashed,gray")]
    seen = set()
    for top, bottom, style in circles:
        key = (round(as_float(top), 9), round(as_float(bottom), 9))
        if key in seen or as_float(top) == as_float(bottom):
            continue
        seen.add(key)
        cx = (as_float(top) + as_float(bottom)) / 2 * k
        radius = abs(as_float(top) - as_float(bottom)) / 2 * k
        lines.append(f"% studium:circle centre={(as_float(top) + as_float(bottom)) / 2!r} radius={abs(as_float(top) - as_float(bottom)) / 2!r} scale={k!r}")
        lines.append(f"\\draw[{style}] ({fmt(cx)},0) circle ({fmt(radius)});")
    px = (as_float(state.sx) * k, sign * as_float(state.txy) * k)
    py = (as_float(state.sy) * k, -sign * as_float(state.txy) * k)
    c = as_float(solution.centre) * k
    lines += [
        f"\\draw[red!70!black,thick] ({fmt(px[0])},{fmt(px[1])}) -- ({fmt(py[0])},{fmt(py[1])});",
        f"% studium:mohrpoint Px sigma={as_float(state.sx)!r} tau={sign * as_float(state.txy)!r} scale={k!r}",
        f"\\fill[red!70!black] ({fmt(px[0])},{fmt(px[1])}) circle (0.06) node[anchor={'north west' if px[1] < 0 else 'south west'},font=\\small] {{$P_x\\,({_n(state.sx, comma)};\\,{_n(sign * state.txy, comma)})$}};",
        f"% studium:mohrpoint Py sigma={as_float(state.sy)!r} tau={-sign * as_float(state.txy)!r} scale={k!r}",
        f"\\fill[red!70!black] ({fmt(py[0])},{fmt(py[1])}) circle (0.06) node[anchor={'north east' if py[1] < 0 else 'south east'},font=\\small] {{$P_y\\,({_n(state.sy, comma)};\\,{_n(-sign * state.txy, comma)})$}};",
        f"\\fill ({fmt(c)},0) circle (0.04) node[below,font=\\small] {{$C$}};",
        f"\\fill[blue!60!black] ({fmt(as_float(solution.s1) * k)},0) circle (0.05) node[anchor=south west,font=\\small,blue!60!black] {{$\\sigma_1 = {_n(solution.s1, comma)}$}};",
        f"\\fill[blue!60!black] ({fmt(as_float(solution.s2) * k)},0) circle (0.05) node[anchor=south east,font=\\small,blue!60!black] {{$\\sigma_2 = {_n(solution.s2, comma)}$}};",
        f"\\draw[densely dotted] ({fmt(c)},0) -- ({fmt(c)},{fmt(r)}) node[above right,font=\\small] {{$\\tau_{{\\max}} = {_n(solution.tau_in_plane, comma)}$}};",
    ]
    angle_px = math.degrees(math.atan2(px[1], px[0] - c)) if r > 0 else 0.0
    if r > 0:
        lines.append(
            f"\\draw[-stealth,violet] ({fmt(c + 0.45 * r * math.cos(math.radians(angle_px)))},{fmt(0.45 * r * math.sin(math.radians(angle_px)))}) arc ({angle_px:.3f}:0:{fmt(0.45 * r)});"
        )
        lines.append(
            f"\\node[font=\\small,violet,anchor=west] at ({fmt(c + 0.5 * r)},{fmt(0.18 * r * (1 if angle_px > 0 else -1))}) {{$2\\theta_p = {_n(abs(2 * solution.theta * 180 / sympy.pi), comma)}^\\circ$}};"
        )
    lines.append(f"\\node[font=\\small,anchor=north west] at ({fmt(min(lo, 0) * k)},{fmt(-r - 0.5)}) {{tensiones en {state.unit}}};")
    return "\n".join(lines)


def element_figure(solution: StressSolution, *, comma: bool = True) -> str:
    """The stress element on x, y faces and the principal element rotated by theta_p."""

    state = solution.state
    lines: list[str] = []

    def square(cx: float, cy: float, angle: float, normal_x: float, normal_y: float, tau: float, texts: tuple[str, str, str | None]) -> None:
        a = math.radians(angle)
        ux, uy = math.cos(a), math.sin(a)
        vx, vy = -uy, ux
        h = 0.7
        corners = [(cx + (i * ux + j * vx) * h, cy + (i * uy + j * vy) * h) for i, j in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        lines.append("\\filldraw[fill=gray!12,thick] " + " -- ".join(f"({fmt(x)},{fmt(y)})" for x, y in corners) + " -- cycle;")
        for (nx, ny), value, text, anchor in (((ux, uy), normal_x, texts[0], "west"), ((vx, vy), normal_y, texts[1], "south")):
            if abs(value) < 1e-12:
                continue
            for face in (1, -1):
                base = (cx + face * nx * h, cy + face * ny * h)
                outward = 1 if value > 0 else -1  # tension pulls away from the face, compression pushes on it
                start = base if outward > 0 else (base[0] + face * nx * 0.6, base[1] + face * ny * 0.6)
                end = (base[0] + face * nx * 0.6, base[1] + face * ny * 0.6) if outward > 0 else base
                lines.append(f"\\draw[-stealth,thick,blue!60!black] ({fmt(start[0])},{fmt(start[1])}) -- ({fmt(end[0])},{fmt(end[1])});")
                if face == 1:
                    label = (base[0] + nx * 0.62, base[1] + ny * 0.62)
                    lines.append(f"\\node[font=\\scriptsize,anchor={anchor}] at ({fmt(label[0])},{fmt(label[1])}) {{{text}}};")
        if abs(tau) > 1e-12 and texts[2]:
            sense = 1 if tau > 0 else -1
            # Face +x: shear along +y; face -x along -y; face +y along +x; face -y along -x (for tau > 0).
            for (nx, ny), (tx, ty), face in (((ux, uy), (vx, vy), 1), ((ux, uy), (vx, vy), -1), ((vx, vy), (ux, uy), 1), ((vx, vy), (ux, uy), -1)):
                centre = (cx + face * nx * (h + 0.1), cy + face * ny * (h + 0.1))
                start = (centre[0] - face * sense * tx * 0.4, centre[1] - face * sense * ty * 0.4)
                end = (centre[0] + face * sense * tx * 0.4, centre[1] + face * sense * ty * 0.4)
                lines.append(f"\\draw[-stealth,red!70!black] ({fmt(start[0])},{fmt(start[1])}) -- ({fmt(end[0])},{fmt(end[1])});")
            lines.append(f"\\node[font=\\scriptsize,red!70!black,anchor=north west] at ({fmt(cx + 0.9)},{fmt(cy - 0.85)}) {{{texts[2]}}};")

    square(
        0, 0, 0, as_float(state.sx), as_float(state.sy), as_float(state.txy),
        (f"$\\sigma_x = {_n(state.sx, comma)}$", f"$\\sigma_y = {_n(state.sy, comma)}$", f"$\\tau_{{xy}} = {_n(state.txy, comma)}$"),
    )
    degrees = as_float(solution.theta) * 180 / math.pi
    square(
        5.2, 0, degrees, as_float(solution.s1), as_float(solution.s2), 0.0,
        (f"$\\sigma_1 = {_n(solution.s1, comma)}$", f"$\\sigma_2 = {_n(solution.s2, comma)}$", None),
    )
    lines.append("\\draw[-stealth] (-1.6,-1.6) -- (-0.9,-1.6) node[right,font=\\small] {$x$};")
    lines.append("\\draw[-stealth] (-1.6,-1.6) -- (-1.6,-0.9) node[above,font=\\small] {$y$};")
    lines.append(f"\\draw[densely dashed,violet] (5.2,0) -- ({fmt(5.2 + 1.5 * math.cos(math.radians(degrees)))},{fmt(1.5 * math.sin(math.radians(degrees)))});")
    lines.append(f"\\node[font=\\small,violet,anchor=north] at (5.2,-1.5) {{$\\theta_p = {_n(degrees, comma)}^\\circ$ desde $x$}};")
    lines.append(f"\\node[font=\\small,anchor=north] at (2.6,-2.1) {{tensiones en {state.unit}}};")
    return "\n".join(lines)


def verify_mohr_drawing(tikz: str, solution: StressSolution, *, tolerance: float = 2e-3) -> Evidence:
    evidence = Evidence()
    lines = tikz.splitlines()
    main_ok = False
    for index, line in enumerate(lines):
        if line.startswith("% studium:circle "):
            values = dict(item.split("=") for item in line.split()[2:])
            k = float(values["scale"])
            match = re.search(r"\((-?[0-9.]+),(-?[0-9.]+)\) circle \((-?[0-9.]+)\)", lines[index + 1])
            if match is None:
                continue
            drawn_ok = abs(float(match.group(1)) - float(values["centre"]) * k) <= tolerance and abs(float(match.group(3)) - float(values["radius"]) * k) <= tolerance
            if abs(float(values["centre"]) - as_float(solution.centre)) < 1e-9 and abs(float(values["radius"]) - as_float(solution.radius)) < 1e-9:
                main_ok = drawn_ok
    evidence.add("the main Mohr circle is drawn with the computed centre and radius", "representation", main_ok)
    sign = -1 if solution.state.convention.get("mohr_plot") == "x_point_minus_tau" else 1
    points_ok = True
    for index, line in enumerate(lines):
        if line.startswith("% studium:mohrpoint "):
            parts = line.split()
            values = dict(item.split("=") for item in parts[3:])
            name = parts[2]
            expected = (solution.state.sx, sign * solution.state.txy) if name == "Px" else (solution.state.sy, -sign * solution.state.txy)
            if abs(float(values["sigma"]) - as_float(expected[0])) > 1e-9 or abs(float(values["tau"]) - as_float(expected[1])) > 1e-9:
                points_ok = False
            coords = _COORD.findall(lines[index + 1])
            k = float(values["scale"])
            if not coords or abs(float(coords[0][0]) - as_float(expected[0]) * k) > tolerance or abs(float(coords[0][1]) - as_float(expected[1]) * k) > tolerance:
                points_ok = False
    evidence.add("face points are drawn where the declared Mohr convention puts them", "representation", points_ok)
    return evidence
