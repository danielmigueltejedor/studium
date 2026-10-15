"""TikZ drawings of a cross-section: geometry and centroidal axes, principal axes,
and the normal-stress field (neutral axis, tension and compression zones).

Drawn elements carry trace comments that :func:`verify_section_drawing`
compares with the data: vertices, centroid, principal direction, neutral axis
and printed values.
"""

import math
import re
from dataclasses import dataclass

import sympy

from studium.diagrams.evidence import Evidence
from studium.diagrams.piecewise import as_float, format_number
from studium.diagrams.tikz import fmt
from studium.engineering.structures.section import SectionSolution, Y, Z

_SIZE = 5.5
_COORD = re.compile(r"\((-?[0-9.]+),(-?[0-9.]+)\)")


@dataclass(frozen=True)
class Frame:
    """Section (z, y) to paper (X, Y) in cm. ``down`` when the section's y axis points down."""

    k: float
    z0: float
    y0: float
    down: bool

    def point(self, z: float, y: float) -> tuple[float, float]:
        return (z - self.z0) * self.k, (-(y - self.y0) if self.down else (y - self.y0)) * self.k

    def inverse(self, px: float, py: float) -> tuple[float, float]:
        return px / self.k + self.z0, (-py if self.down else py) / self.k + self.y0


def _frame(solution: SectionSolution) -> Frame:
    zs = [as_float(z) for part in solution.model.parts for z, _ in part.points]
    ys = [as_float(y) for part in solution.model.parts for _, y in part.points]
    span = max(max(zs) - min(zs), max(ys) - min(ys)) or 1.0
    down = solution.model.convention.get("section_y_axis") == "down"
    return Frame(_SIZE / span, min(zs), min(ys), down)


def _xy(point: tuple[float, float]) -> str:
    return f"({fmt(point[0])},{fmt(point[1])})"


def _number(value: object, comma: bool, decimals: int = 2) -> str:
    return format_number(value, decimals=decimals, comma=comma)


def _outline(solution: SectionSolution, frame: Frame, fill: str = "gray!18") -> list[str]:
    lines: list[str] = []
    for part in [p for p in solution.model.parts if not p.hole] + [p for p in solution.model.parts if p.hole]:
        lines.append(f"% studium:polygon {part.name}")
        color = "white" if part.hole else fill
        path = " -- ".join(_xy(frame.point(as_float(z), as_float(y))) for z, y in part.points)
        lines.append(f"\\filldraw[fill={color},draw=black,thick] {path} -- cycle;")
    return lines


def _dimensions(solution: SectionSolution, frame: Frame, comma: bool) -> list[str]:
    zs = [as_float(z) for part in solution.model.parts for z, _ in part.points]
    ys = [as_float(y) for part in solution.model.parts for _, y in part.points]
    unit = solution.model.units["length"]
    left, right = min(zs), max(zs)
    top_y = min(ys) if frame.down else max(ys)
    bottom_y = max(ys) if frame.down else min(ys)
    _, bottom = frame.point(left, bottom_y)
    lines = []
    y_dim = bottom - 0.9
    x0, _ = frame.point(left, bottom_y)
    x1, _ = frame.point(right, bottom_y)
    lines.append(f"\\draw[<->,gray] ({fmt(x0)},{fmt(y_dim)}) -- ({fmt(x1)},{fmt(y_dim)});")
    lines.append(
        f"\\node[font=\\small,anchor=north] at ({fmt((x0 + x1) / 2)},{fmt(y_dim)}) {{${_number(right - left, comma)}$~\\mbox{{{unit}}}}};"
    )
    xr = x1 + 0.45
    _, ya = frame.point(right, top_y)
    _, yb = frame.point(right, bottom_y)
    lines.append(f"\\draw[<->,gray] ({fmt(xr)},{fmt(ya)}) -- ({fmt(xr)},{fmt(yb)});")
    lines.append(
        f"\\node[font=\\small,anchor=west] at ({fmt(xr)},{fmt((ya + yb) / 2)}) {{${_number(max(ys) - min(ys), comma)}$~\\mbox{{{unit}}}}};"
    )
    return lines


def _centroid(solution: SectionSolution, frame: Frame, comma: bool) -> list[str]:
    zg, yg = (as_float(v) for v in solution.centroid)
    gx, gy = frame.point(zg, yg)
    zs = [as_float(z) for part in solution.model.parts for z, _ in part.points]
    ys = [as_float(y) for part in solution.model.parts for _, y in part.points]
    reach_z = (max(zs) - zg) * frame.k + 0.6
    reach_y = ((max(ys) - yg) if frame.down else (yg - min(ys))) * frame.k + 0.4
    unit = solution.model.units["length"]
    top = min(ys) if frame.down else max(ys)
    _, py_top = frame.point(zg, top)
    left = frame.point(min(zs), yg)[0] - 0.9
    return [
        f"% studium:point G z={solution.centroid[0]} y={solution.centroid[1]}",
        f"\\fill[black] ({fmt(gx)},{fmt(gy)}) circle (0.06);",
        f"\\node[font=\\small,anchor=south west] at ({fmt(gx)},{fmt(gy)}) {{$G$}};",
        f"\\draw[-stealth,thin] ({fmt(gx)},{fmt(gy)}) -- ({fmt(gx + reach_z)},{fmt(gy)}) node[right,font=\\small] {{$z$}};",
        f"\\draw[-stealth,thin] ({fmt(gx)},{fmt(gy)}) -- ({fmt(gx)},{fmt(gy - reach_y if frame.down else gy + reach_y)}) node[{'below' if frame.down else 'above'},font=\\small] {{$y$}};",
        f"\\draw[<->,gray] ({fmt(left)},{fmt(py_top)}) -- ({fmt(left)},{fmt(gy)});",
        f"\\node[font=\\small,anchor=east,gray!30!black] at ({fmt(left)},{fmt((py_top + gy) / 2)}) {{$y_G = {_number(abs(yg - top), comma)}$~\\mbox{{{unit}}}}};",
    ]


def _principal(solution: SectionSolution, frame: Frame, comma: bool) -> list[str]:
    if solution.Iyz == 0:
        return []
    theta = as_float(solution.theta)
    zg, yg = (as_float(v) for v in solution.centroid)
    gx, gy = frame.point(zg, yg)
    length = 0.55 * _SIZE
    lines = [f"% studium:axis principal theta={theta!r}"]
    for name, angle in (("1", theta), ("2", theta + math.pi / 2)):
        dz, dy = math.cos(angle), math.sin(angle)
        end = frame.point(zg + dz * length / frame.k, yg + dy * length / frame.k)
        start = frame.point(zg - dz * length / frame.k, yg - dy * length / frame.k)
        lines.append(f"\\draw[densely dashed,violet] {_xy(start)} -- {_xy(end)} node[font=\\small,violet,anchor=south west] {{${name}$}};")
    degrees = _number(theta * 180 / math.pi, comma, 1)
    lines.append(f"\\node[font=\\scriptsize,violet,anchor=north west] at ({fmt(gx + 0.25)},{fmt(gy - 0.05)}) {{$\\theta_p = {degrees}^\\circ$}};")
    del gx
    return lines


def properties_figure(solution: SectionSolution, *, comma: bool = True) -> str:
    frame = _frame(solution)
    lines = _outline(solution, frame)
    lines += _dimensions(solution, frame, comma)
    lines += _centroid(solution, frame, comma)
    lines += _principal(solution, frame, comma)
    return "\n".join(lines)


def _clip(points: list[tuple[float, float]], sign: float, field) -> list[tuple[float, float]]:
    """Sutherland-Hodgman clip of a polygon to ``sign * field(z, y) >= 0``."""

    result: list[tuple[float, float]] = []
    count = len(points)
    for index in range(count):
        current, following = points[index], points[(index + 1) % count]
        a, b = sign * field(*current), sign * field(*following)
        if a >= 0:
            result.append(current)
        if (a >= 0) != (b >= 0):
            t = a / (a - b)
            result.append((current[0] + t * (following[0] - current[0]), current[1] + t * (following[1] - current[1])))
    return result


def stress_figure(solution: SectionSolution, *, comma: bool = True) -> str:
    if solution.stress is None:
        raise ValueError("the section has no loads; give N, My or Mz")
    frame = _frame(solution)
    zg, yg = (as_float(v) for v in solution.centroid)
    stress = sympy.lambdify((Z, Y), solution.stress, "math")

    def field(z: float, y: float) -> float:
        return float(stress(z - zg, y - yg))

    lines = _outline(solution, frame, fill="white")
    for part in solution.model.parts:
        if part.hole:
            continue
        polygon = [(as_float(z), as_float(y)) for z, y in part.points]
        for sign, color, name in ((1.0, "red!30", "tension"), (-1.0, "blue!25", "compression")):
            region = _clip(polygon, sign, field)
            if len(region) >= 3:
                lines.append(f"% studium:zone {name}")
                lines.append(f"\\fill[{color}] " + " -- ".join(_xy(frame.point(z, y)) for z, y in region) + " -- cycle;")
    lines += [line.replace("fill=white", "fill=none") for line in _outline(solution, frame, fill="white")]
    lines += _centroid(solution, frame, comma)[:3]
    lines += _neutral_axis(solution, frame, field)
    lines += _profile(solution, frame, field, comma)
    unit = f"{solution.model.units['force']}/{solution.model.units['length']}^2"
    if solution.model.units == {"length": "mm", "force": "N"}:
        unit = "MPa"
    for kind, (value, point) in solution.extremes.items():
        px, py = frame.point(as_float(point[0]), as_float(point[1]))
        printed = _number(value, comma)
        anchor = "south east" if kind == "max" else "north west"
        lines.append(f"% studium:value sigma_{kind} z={point[0]} y={point[1]} value={printed.replace('{,}', '.')}")
        lines.append(f"\\fill ({fmt(px)},{fmt(py)}) circle (0.05);")
        lines.append(
            f"\\node[font=\\scriptsize,anchor={anchor},fill=white,fill opacity=0.85,text opacity=1,inner sep=1pt] at ({fmt(px)},{fmt(py)}) "
            f"{{$\\sigma = {printed}$~\\mbox{{{unit}}}}};"
        )
    return "\n".join(lines)


def _profile(solution: SectionSolution, frame: Frame, field, comma: bool) -> list[str]:
    """Linear stress profile beside the section when sigma depends on y only (horizontal neutral axis)."""

    zg, yg = (as_float(v) for v in solution.centroid)
    if abs(field(zg + 1, yg) - field(zg, yg)) > 1e-12 * max(1.0, abs(field(zg, yg + 1) - field(zg, yg))):
        return []
    zs = [as_float(z) for part in solution.model.parts for z, _ in part.points]
    ys = [as_float(y) for part in solution.model.parts for _, y in part.points]
    base = frame.point(max(zs), yg)[0] + 1.6
    top, bottom = min(ys), max(ys)
    largest = max(abs(field(zg, top)), abs(field(zg, bottom)), 1e-12)
    scale = 1.3 / largest
    unit = "MPa" if solution.model.units == {"length": "mm", "force": "N"} else f"{solution.model.units['force']}/{solution.model.units['length']}^2"
    lines = [f"% studium:profile base={base!r} scale={scale!r}"]
    py_top = frame.point(zg, top)[1]
    py_bottom = frame.point(zg, bottom)[1]
    lines.append(f"\\draw[thin] ({fmt(base)},{fmt(py_top)}) -- ({fmt(base)},{fmt(py_bottom)});")
    for y in (top, bottom):
        value = field(zg, y)
        py = frame.point(zg, y)[1]
        color = "red!30" if value > 0 else "blue!25"
        anchor = "west" if value >= 0 else "east"
        _, py_na = frame.point(zg, yg - field(zg, yg) / ((field(zg, yg + 1) - field(zg, yg)) or 1e-300))
        lines.append(f"\\fill[{color}] ({fmt(base)},{fmt(py_na)}) -- ({fmt(base + value * scale)},{fmt(py)}) -- ({fmt(base)},{fmt(py)}) -- cycle;")
        printed = _number(value, comma)
        lines.append(f"% studium:value profile y={y!r} value={printed.replace('{,}', '.')}")
        lines.append(f"\\node[font=\\scriptsize,anchor={anchor}] at ({fmt(base + value * scale)},{fmt(py)}) {{${printed}$~\\mbox{{{unit}}}}};")
    lines.append(f"\\draw[thick] ({fmt(base + field(zg, top) * scale)},{fmt(py_top)}) -- ({fmt(base + field(zg, bottom) * scale)},{fmt(py_bottom)});")
    lines.append(f"\\node[font=\\small,anchor=south] at ({fmt(base)},{fmt(max(py_top, py_bottom) + 0.1)}) {{$\\sigma_x$}};")
    return lines


def _neutral_axis(solution: SectionSolution, frame: Frame, field) -> list[str]:
    zs = [as_float(z) for part in solution.model.parts for z, _ in part.points]
    ys = [as_float(y) for part in solution.model.parts for _, y in part.points]
    zg, yg = (as_float(v) for v in solution.centroid)
    c0 = field(zg, yg)
    cz = field(zg + 1, yg) - c0
    cy = field(zg, yg + 1) - c0
    if abs(cz) < 1e-15 and abs(cy) < 1e-15:
        return []
    margin = 0.15 * max(max(zs) - min(zs), max(ys) - min(ys))
    points = []
    if abs(cy) >= abs(cz):
        for z in (min(zs) - margin, max(zs) + margin):
            points.append((z, yg - (c0 + cz * (z - zg)) / cy))
    else:
        for y in (min(ys) - margin, max(ys) + margin):
            points.append((zg - (c0 + cy * (y - yg)) / cz, y))
    (za, ya), (zb, yb) = points
    return [
        f"% studium:neutral-axis z1={za!r} y1={ya!r} z2={zb!r} y2={yb!r}",
        f"\\draw[very thick,green!45!black] {_xy(frame.point(za, ya))} -- {_xy(frame.point(zb, yb))} node[font=\\small,anchor=west,green!35!black] {{e.n.}};",
    ]


def verify_section_drawing(tikz: str, solution: SectionSolution, *, tolerance: float = 2e-3) -> Evidence:
    """Vertices, centroid, principal direction, neutral axis, zones and printed values against the data."""

    evidence = Evidence()
    frame = _frame(solution)
    lines = tikz.splitlines()
    parts = {part.name: part for part in solution.model.parts}
    drawn: dict[str, bool] = {}
    for index, line in enumerate(lines):
        text = line.strip()
        if text.startswith("% studium:polygon "):
            name = text.split(" ", 2)[2]
            coords = [(float(a), float(b)) for a, b in _COORD.findall(lines[index + 1])]
            part = parts.get(name)
            if part is None or len(coords) != len(part.points):
                drawn[name] = False
                continue
            expected = [frame.point(as_float(z), as_float(y)) for z, y in part.points]
            drawn[name] = drawn.get(name, True) and all(
                abs(a[0] - b[0]) <= tolerance and abs(a[1] - b[1]) <= tolerance for a, b in zip(coords, expected, strict=True)
            )
    missing = [name for name in parts if name not in drawn]
    evidence.add("every part is drawn with the data's vertices", "representation", not missing and all(drawn.values()), ", ".join(missing))
    centroid_ok = False
    for index, line in enumerate(lines):
        if line.startswith("% studium:point G "):
            coords = [(float(a), float(b)) for a, b in _COORD.findall(lines[index + 1])]
            expected = frame.point(as_float(solution.centroid[0]), as_float(solution.centroid[1]))
            centroid_ok = bool(coords) and abs(coords[0][0] - expected[0]) <= tolerance and abs(coords[0][1] - expected[1]) <= tolerance
    evidence.add("the centroid is drawn at the computed point", "representation", centroid_ok)
    for line in lines:
        if line.startswith("% studium:axis principal "):
            drawn_theta = float(line.split("theta=", 1)[1])
            evidence.add(
                "principal axes are drawn at the computed angle",
                "representation",
                abs(drawn_theta - as_float(solution.theta)) < 1e-9,
            )
    if solution.stress is not None:
        zg, yg = (as_float(v) for v in solution.centroid)
        stress = sympy.lambdify((Z, Y), solution.stress, "math")
        scale = max(abs(as_float(solution.extremes["max"][0])), abs(as_float(solution.extremes["min"][0])), 1e-12)
        axis_ok = None
        for line in lines:
            if line.startswith("% studium:neutral-axis "):
                values = dict(item.split("=") for item in line.split()[2:])
                ends = ((float(values["z1"]), float(values["y1"])), (float(values["z2"]), float(values["y2"])))
                axis_ok = all(abs(float(stress(z - zg, y - yg))) <= 1e-9 * scale for z, y in ends)
        if axis_ok is not None:
            evidence.add("the neutral axis drawn is where sigma = 0", "representation", axis_ok)
        zones_ok = True
        for index, line in enumerate(lines):
            if line.startswith("% studium:zone "):
                kind = line.split()[-1]
                coords = [frame.inverse(float(a), float(b)) for a, b in _COORD.findall(lines[index + 1])]
                if not coords:
                    zones_ok = False
                    continue
                cz = sum(z for z, _ in coords) / len(coords)
                cy = sum(y for _, y in coords) / len(coords)
                value = float(stress(cz - zg, cy - yg))
                if (kind == "tension" and value < -1e-9 * scale) or (kind == "compression" and value > 1e-9 * scale):
                    zones_ok = False
        evidence.add("tension and compression zones are shaded on the right side of the neutral axis", "representation", zones_ok)
        printed_ok = True
        for line in lines:
            if line.startswith("% studium:value sigma_"):
                values = dict(item.split("=") for item in line.split()[3:])
                actual = float(stress(as_float(values["z"]) - zg, as_float(values["y"]) - yg))
                text = values["value"]
                decimals = len(text.split(".", 1)[1]) if "." in text else 0
                if abs(float(text) - actual) > 0.5 * 10 ** (-decimals) * (1 + 1e-9):
                    printed_ok = False
        for line in lines:
            if line.startswith("% studium:value profile "):
                values = dict(item.split("=") for item in line.split()[3:])
                actual = float(stress(0.0, float(values["y"]) - yg))
                text = values["value"]
                decimals = len(text.split(".", 1)[1]) if "." in text else 0
                if abs(float(text) - actual) > 0.5 * 10 ** (-decimals) * (1 + 1e-9):
                    printed_ok = False
        evidence.add("printed stresses equal the stress field at their points", "representation", printed_ok)
    return evidence
