"""TikZ drawings of thin-walled sections: geometry, and the shear-flow distribution.

The flow ``q(s)`` of each wall is drawn as a band on the outer side of the
wall, its width proportional to ``|q|``, with arrows along the wall in the
direction the flow actually runs. Each band is traced so :func:`verify_flow_drawing` can recover
``q(s)`` from the drawn points and compare it with the solution.
"""

import math
import re

import sympy

from studium.diagrams.evidence import Evidence
from studium.diagrams.piecewise import as_float, format_number
from studium.diagrams.tikz import fmt
from studium.engineering.structures.thinwall import S, ThinWallSolution, wall_length

_SIZE = 6.0
_BAND = 0.9
_COORD = re.compile(r"\((-?[0-9.]+),(-?[0-9.]+)\)")


class _Frame:
    def __init__(self, solution: ThinWallSolution):
        model = solution.model
        zs = [as_float(z) for z, _ in model.nodes.values()]
        ys = [as_float(y) for _, y in model.nodes.values()]
        span = max(max(zs) - min(zs), max(ys) - min(ys)) or 1.0
        self.k = _SIZE / span
        self.z0 = min(zs)
        self.y0 = min(ys)
        self.down = model.convention.get("section_y_axis") == "down"

    def point(self, z: float, y: float) -> tuple[float, float]:
        return (z - self.z0) * self.k, (-(y - self.y0) if self.down else (y - self.y0)) * self.k


def _xy(point: tuple[float, float]) -> str:
    return f"({fmt(point[0])},{fmt(point[1])})"


def _number(value: object, comma: bool) -> str:
    return format_number(value, decimals=2, comma=comma)


def _walls(solution: ThinWallSolution, frame: _Frame, comma: bool, labels: bool = True) -> list[str]:
    model = solution.model
    thickest = max(as_float(w.t) for w in model.walls)
    lines = []
    for wall in model.walls:
        width = 0.6 + 1.6 * as_float(wall.t) / thickest
        a = frame.point(*(as_float(v) for v in model.nodes[wall.start]))
        b = frame.point(*(as_float(v) for v in model.nodes[wall.end]))
        lines.append(f"\\draw[line width={width:.2f}pt,line cap=round] {_xy(a)} -- {_xy(b)};")
        if labels:
            middle = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            lines.append(f"\\node[font=\\scriptsize,gray!40!black,fill=white,inner sep=0.5pt] at {_xy(middle)} {{$t={_number(wall.t, comma)}$}};")
    for name, (z, y) in model.nodes.items():
        p = frame.point(as_float(z), as_float(y))
        lines.append(f"\\node[font=\\small\\bfseries,anchor=south east,inner sep=1pt] at {_xy(p)} {{{name}}};")
    for node, area in model.booms.items():
        p = frame.point(*(as_float(v) for v in model.nodes[node]))
        radius = 0.08 + 0.1 * math.sqrt(as_float(area) / max(as_float(a) for a in model.booms.values()))
        lines.append(f"\\fill {_xy(p)} circle ({radius:.3f});")
    return lines


def _markers(solution: ThinWallSolution, frame: _Frame, comma: bool) -> list[str]:
    model = solution.model
    g = frame.point(*(as_float(v) for v in solution.centroid))
    c = frame.point(*(as_float(v) for v in solution.shear_centre))
    lines = [
        f"% studium:point G z={solution.centroid[0]} y={solution.centroid[1]}",
        f"\\draw {_xy(g)} circle (0.07); \\node[font=\\small,anchor=north west] at {_xy(g)} {{$G$}};",
        f"% studium:point C z={solution.shear_centre[0]} y={solution.shear_centre[1]}",
        f"\\fill[violet] {_xy(c)} circle (0.07); \\node[font=\\small,anchor=south west,violet] at {_xy(c)} {{$C$}};",
    ]
    if model.vy != 0 or model.vz != 0:
        point = solution.shear_centre if model.at == "shear_centre" else model.at
        assert isinstance(point, tuple)
        p = frame.point(as_float(point[0]), as_float(point[1]))
        size = math.hypot(as_float(model.vy), as_float(model.vz))
        dz, dy = as_float(model.vz) / size, as_float(model.vy) / size
        direction = (dz, -dy if frame.down else dy)
        tail = (p[0] - 1.1 * direction[0], p[1] - 1.1 * direction[1])
        text = []
        if model.vy != 0:
            text.append(f"V_y = {_number(model.vy, comma)}")
        if model.vz != 0:
            text.append(f"V_z = {_number(model.vz, comma)}")
        lines.append(f"\\draw[-stealth,very thick,red!75!black] {_xy(tail)} -- {_xy(p)};")
        lines.append(f"\\node[font=\\small,red!75!black,anchor=south] at {_xy(tail)} {{${', '.join(text)}$~\\mbox{{{model.units['force']}}}}};")
    return lines


def geometry_figure(solution: ThinWallSolution, *, comma: bool = True) -> str:
    frame = _Frame(solution)
    lines = _walls(solution, frame, comma)
    lines += _markers(solution, frame, comma)
    model = solution.model
    for index, loop in enumerate(model.cells, 1):
        zs = [as_float(model.nodes[n][0]) for n in loop]
        ys = [as_float(model.nodes[n][1]) for n in loop]
        corner = frame.point(min(zs) + 0.22 * (max(zs) - min(zs)), max(ys) - 0.2 * (max(ys) - min(ys)) if frame.down else min(ys) + 0.2 * (max(ys) - min(ys)))
        lines.append(f"\\node[font=\\small,gray!50!black] at {_xy(corner)} {{célula {index}}};")
    return "\n".join(lines)


def _scale(solution: ThinWallSolution) -> float:
    largest = 0.0
    for wall in solution.model.walls:
        length = wall_length(solution.model, wall)
        q = solution.flows[wall.name]
        for k in range(21):
            largest = max(largest, abs(as_float(q.subs(S, length * k / 20))))
    return _BAND / largest if largest > 0 else 1.0


def flow_figure(solution: ThinWallSolution, *, comma: bool = True) -> str:
    frame = _Frame(solution)
    model = solution.model
    scale = _scale(solution)
    zs = [as_float(z) for z, _ in model.nodes.values()]
    ys = [as_float(y) for _, y in model.nodes.values()]
    middle_section = frame.point(sum(zs) / len(zs), sum(ys) / len(ys))
    lines: list[str] = []
    for wall in model.walls:
        length = wall_length(solution.model, wall)
        q = solution.flows[wall.name]
        a = frame.point(*(as_float(v) for v in model.nodes[wall.start]))
        b = frame.point(*(as_float(v) for v in model.nodes[wall.end]))
        paper_length = math.hypot(b[0] - a[0], b[1] - a[1])
        ux, uy = (b[0] - a[0]) / paper_length, (b[1] - a[1]) / paper_length
        nx, ny = -uy, ux  # left of the wall direction on paper
        centre = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        # Bands go outside the section so they do not hide one another.
        side = 1 if (centre[0] - middle_section[0]) * nx + (centre[1] - middle_section[1]) * ny >= 0 else -1
        places = [length * sympy.Rational(k, 24) for k in range(25)] if sympy.Poly(q, S).degree() > 1 else [sympy.Integer(0), length]
        points = []
        for s_value in places:
            value = abs(as_float(q.subs(S, s_value)))
            fraction = as_float(s_value / length)
            base = (a[0] + fraction * (b[0] - a[0]), a[1] + fraction * (b[1] - a[1]))
            points.append((base[0] + side * nx * value * scale, base[1] + side * ny * value * scale))
        lines.append("\\fill[orange!25] " + _xy(a) + " -- " + " -- ".join(_xy(p) for p in points) + " -- " + _xy(b) + " -- cycle;")
        lines.append(
            f"% studium:flow {wall.name} ax={a[0]!r} ay={a[1]!r} ux={ux!r} uy={uy!r} plen={paper_length!r} scale={scale!r} side={side}"
        )
        lines.append("\\draw[orange!70!black] " + " -- ".join(_xy(p) for p in points) + ";")
        labelled = [sympy.Integer(0), length]
        slope = sympy.diff(q, S)
        if slope.free_symbols:
            labelled += [r for r in sympy.solve(sympy.Eq(slope, 0), S) if r.is_real and 0 < as_float(r) < as_float(length)]
        for s_value in labelled:
            value = q.subs(S, s_value)
            if abs(as_float(value)) < 1e-9:
                continue
            fraction = as_float(s_value / length)
            base = (a[0] + fraction * (b[0] - a[0]), a[1] + fraction * (b[1] - a[1]))
            tip = (base[0] + side * nx * (abs(as_float(value)) * scale + 0.18), base[1] + side * ny * (abs(as_float(value)) * scale + 0.18))
            printed = _number(abs(as_float(value)), comma)
            lines.append(f"% studium:qlabel {wall.name} s={s_value} value={printed.replace('{,}', '.')}")
            lines.append(f"\\node[font=\\scriptsize,inner sep=0.5pt] at {_xy(tip)} {{${printed}$}};")
        for fraction in (0.3, 0.7):
            value = as_float(q.subs(S, length * sympy.Rational(int(fraction * 10), 10)))
            if abs(value) < 1e-9:
                continue
            direction = 1 if value > 0 else -1
            base = (a[0] + fraction * (b[0] - a[0]) - side * nx * 0.12, a[1] + fraction * (b[1] - a[1]) - side * ny * 0.12)
            tail = (base[0] - direction * ux * 0.22, base[1] - direction * uy * 0.22)
            head = (base[0] + direction * ux * 0.22, base[1] + direction * uy * 0.22)
            lines.append(f"\\draw[-stealth,thick,orange!40!black] {_xy(tail)} -- {_xy(head)};")
    lines += _walls(solution, frame, comma, labels=False)
    lines += _markers(solution, frame, comma)
    unit = f"{model.units['force']}/{model.units['length']}"
    lowest = min(frame.point(as_float(z), as_float(y))[1] for z, y in model.nodes.values())
    lines.append(f"\\node[font=\\small,anchor=north west] at (0,{fmt(lowest - _BAND - 0.4)}) {{valores de $|q|$ en {unit}; las flechas indican el sentido}};")
    return "\n".join(lines)


def verify_flow_drawing(tikz: str, solution: ThinWallSolution, *, tolerance: float = 2e-3) -> Evidence:
    """Recover |q(s)| from each drawn band and compare it with the solution; check printed values."""

    evidence = Evidence()
    model = solution.model
    lines = tikz.splitlines()
    walls = {w.name: w for w in model.walls}
    drawn: dict[str, bool] = {}
    for index, line in enumerate(lines):
        if not line.startswith("% studium:flow "):
            continue
        parts = line.split()
        name = parts[2]
        values = dict(item.split("=") for item in parts[3:])
        wall = walls.get(name)
        coords = [(float(a), float(b)) for a, b in _COORD.findall(lines[index + 1])]
        if wall is None or not coords:
            drawn[name] = False
            continue
        ax, ay, ux, uy = (float(values[key]) for key in ("ax", "ay", "ux", "uy"))
        paper_length, scale, side = float(values["plen"]), float(values["scale"]), int(values["side"])
        length = wall_length(model, wall)
        ok = True
        for px, py in coords:
            along = (px - ax) * ux + (py - ay) * uy
            offset = -(px - ax) * uy + (py - ay) * ux
            s_value = along / paper_length * as_float(length)
            expected = side * abs(as_float(solution.flows[name].subs(S, sympy.Float(s_value, 20)))) * scale
            if abs(offset - expected) > tolerance:
                ok = False
        drawn[name] = ok
    missing = [name for name in walls if name not in drawn]
    evidence.add("every wall's flow band is drawn", "representation", not missing, ", ".join(missing))
    evidence.add("each drawn band follows q(s) of its wall", "representation", all(drawn.values()))
    printed_ok = True
    for line in lines:
        if line.startswith("% studium:qlabel "):
            parts = line.split()
            name = parts[2]
            values = dict(item.split("=") for item in parts[3:])
            actual = abs(as_float(solution.flows[name].subs(S, sympy.sympify(values["s"]))))
            text = values["value"]
            decimals = len(text.split(".", 1)[1]) if "." in text else 0
            if abs(float(text) - actual) > 0.5 * 10 ** (-decimals) * (1 + 1e-9):
                printed_ok = False
    evidence.add("printed flows equal q at their points", "representation", printed_ok)
    centre_ok = True
    frame = _Frame(solution)
    for index, line in enumerate(lines):
        if line.startswith("% studium:point C "):
            coords = [(float(a), float(b)) for a, b in _COORD.findall(lines[index + 1])]
            expected = frame.point(*(as_float(v) for v in solution.shear_centre))
            centre_ok = bool(coords) and abs(coords[0][0] - expected[0]) <= tolerance and abs(coords[0][1] - expected[1]) <= tolerance
    evidence.add("the shear centre is drawn at the computed point", "representation", centre_ok)
    return evidence
