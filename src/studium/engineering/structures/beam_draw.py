"""TikZ drawings of a beam problem, drawn from the model and its solution.

Four drawings share one horizontal scale so they can be read together:

* :func:`problem_figure` the statement: geometry, supports, loads, dimensions, axes;
* :func:`free_body_figure` the isolated beam with its reactions (symbols, or signed values);
* :func:`internal_forces_figure` the loaded beam above aligned N, V and M diagrams;
* :func:`deflection_figure` the elastic line, when ``EI`` was given.

Nothing here computes mechanics; it only draws what :mod:`beam` returned, and
the plotted curves carry a trace that :func:`studium.diagrams.tikz.verify_representation`
compares with the stored functions.
"""

import re
from dataclasses import dataclass
from itertools import pairwise

import sympy

from studium.diagrams.evidence import Evidence
from studium.diagrams.piecewise import Piecewise, X, as_float, format_number
from studium.diagrams.tikz import Frame, fmt, jump_side_values, label_comment, series
from studium.engineering.structures.beam import BeamModel, BeamSolution, extremes

_WIDTH = 12.0
_REACTION_RADIUS = 0.55
_AMPLITUDE = 1.15
_LOAD_HEIGHT = 0.85

_WORDS = {
    "es": {"x": "x", "free": "", "deflection": "deformada"},
    "en": {"x": "x", "free": "", "deflection": "deflected shape"},
}
_FILL = {"N": "green!14", "V": "blue!11", "M": "red!11", "m": "violet!12", "v": "gray!12"}
_STROKE = {"N": "green!45!black", "V": "blue!70!black", "M": "red!70!black", "m": "violet!70!black", "v": "black"}


@dataclass(frozen=True)
class Style:
    """Presentation choices: decimal comma, decimals in labels, drawing width in cm."""

    comma: bool = True
    decimals: int = 2
    width: float = _WIDTH

    def number(self, value: object) -> str:
        return format_number(value, decimals=self.decimals, comma=self.comma)


def _sx(model: BeamModel, style: Style) -> float:
    return style.width / as_float(model.length)


def _unit(model: BeamModel, kind: str) -> str:
    force, length = model.units["force"], model.units["length"]
    return {
        "force": force,
        "length": length,
        "moment": f"{force}\\,{length}",
        "distributed": f"{force}/{length}",
    }[kind]


def _qty(style: Style, value: object, unit: str) -> str:
    return f"${style.number(value)}$~\\mbox{{{unit}}}"


# --------------------------------------------------------------------------- elements


def _beam_line(model: BeamModel, style: Style, y: float) -> list[str]:
    return [f"\\draw[line width=1.6pt] (0,{fmt(y)}) -- ({fmt(style.width)},{fmt(y)});"]


def _supports(model: BeamModel, style: Style, y: float) -> list[str]:
    sx = _sx(model, style)
    lines: list[str] = []
    for support in model.supports:
        px = as_float(support.at) * sx
        lines.append(_mark("support", support.name, support.at))
        if support.kind == "fixed":
            side = -1 if px < style.width / 2 else 1
            lines.append(f"\\draw[thick] ({fmt(px)},{fmt(y - 0.5)}) -- ({fmt(px)},{fmt(y + 0.5)});")
            for k in range(6):
                yy = y - 0.5 + 0.2 * k
                lines.append(f"\\draw ({fmt(px)},{fmt(yy + 0.18)}) -- ({fmt(px + side * 0.18)},{fmt(yy)});")
        else:
            depth = 0.36 if support.kind == "pin" else 0.28
            lines.append(
                f"\\draw[thick,fill=white] ({fmt(px)},{fmt(y)}) -- ({fmt(px - 0.2)},{fmt(y - depth)}) -- ({fmt(px + 0.2)},{fmt(y - depth)}) -- cycle;"
            )
            base = y - depth
            if support.kind == "roller":
                lines.append(f"\\draw ({fmt(px - 0.1)},{fmt(base - 0.05)}) circle (0.05);")
                lines.append(f"\\draw ({fmt(px + 0.1)},{fmt(base - 0.05)}) circle (0.05);")
                base -= 0.1
            lines.append(f"\\draw ({fmt(px - 0.32)},{fmt(base)}) -- ({fmt(px + 0.32)},{fmt(base)});")
            for k in range(5):
                xx = px - 0.28 + 0.14 * k
                lines.append(f"\\draw ({fmt(xx)},{fmt(base)}) -- ({fmt(xx - 0.1)},{fmt(base - 0.1)});")
    return lines


def _hinges(model: BeamModel, style: Style, y: float) -> list[str]:
    sx = _sx(model, style)
    lines: list[str] = []
    for index, hinge in enumerate(model.hinges):
        lines.append(_mark("hinge", str(index), hinge))
        lines.append(f"\\draw[thick,fill=white] ({fmt(as_float(hinge) * sx)},{fmt(y)}) circle (0.08);")
    return lines


def _point_names(model: BeamModel, style: Style, y: float) -> list[str]:
    sx = _sx(model, style)
    return [
        f"\\node[font=\\small\\bfseries,anchor=north west] at ({fmt(as_float(place) * sx + 0.05)},{fmt(y - 0.05)}) {{{name}}};"
        for name, place in model.points.items()
    ]


def _mark(kind: str, name: str, at: sympy.Expr, where: str = "first", to: sympy.Expr | None = None) -> str:
    """Trace a drawn element so :func:`verify_geometry` can compare the next drawn line with the data."""

    extra = f" to={to}" if to is not None else ""
    return f"% studium:at {kind} {name} x={at}{extra} check={where}"


_MARK = re.compile(r"^% studium:at (?P<kind>\w+) (?P<name>\S+) x=(?P<x>\S+)(?: to=(?P<to>\S+))? check=(?P<where>\w+)$")
_COORD = re.compile(r"\((-?[0-9.]+),(-?[0-9.]+)\)")


def verify_geometry(tikz: str, model: BeamModel, style: Style, *, free_body: bool = False) -> Evidence:
    """Every support (or, on a free-body diagram, every reaction), hinge, load and couple
    is drawn once, where the data put it."""

    evidence = Evidence()
    sx = _sx(model, style)
    lines = tikz.splitlines()
    seen: dict[tuple[str, str], bool] = {}
    for index, line in enumerate(lines):
        match = _MARK.match(line.strip())
        if not match:
            continue
        following = next((item for item in lines[index + 1 :] if _COORD.search(item)), "")
        coords = [(float(a), float(b)) for a, b in _COORD.findall(following)]
        expected = as_float(sympy.sympify(match.group("x"))) * sx
        where = match.group("where")
        if not coords:
            ok = False
        elif where == "span":
            end = as_float(sympy.sympify(match.group("to"))) * sx
            ok = abs(coords[0][0] - expected) < 2e-3 and abs(coords[-1][0] - end) < 2e-3
        elif where in ("tip",):
            ok = abs(coords[-1][0] - expected) < 2e-3
        elif where == "arc":
            ok = abs(coords[0][0] - _REACTION_RADIUS - expected) < 2e-3
        else:
            ok = abs(coords[0][0] - expected) < 2e-3
        seen[(match.group("kind"), match.group("name"))] = ok
    if free_body:
        wanted = [("reaction", str(symbol)) for s in model.supports for _, symbol in s.unknowns()]
    else:
        wanted = [("support", s.name) for s in model.supports]
    wanted += [("hinge", str(i)) for i in range(len(model.hinges))]
    wanted += [("force", str(i)) for i, f in enumerate(model.forces) if as_float(f.fx) or as_float(f.fy)]
    wanted += [("couple", str(i)) for i in range(len(model.couples))]
    wanted += [("distributed", str(i)) for i, d in enumerate(model.distributed) if d.axis == "y"]
    missing = [f"{kind} {name}" for kind, name in wanted if (kind, name) not in seen]
    misplaced = [f"{kind} {name}" for (kind, name), ok in seen.items() if not ok]
    evidence.add(
        "every support, hinge and load of the data is drawn",
        "representation",
        not missing,
        "missing: " + ", ".join(missing) if missing else f"{len(wanted)} elements",
    )
    evidence.add(
        "each drawn element sits at the position the data give",
        "representation",
        not misplaced,
        "misplaced: " + ", ".join(misplaced) if misplaced else "",
    )
    return evidence


_REACTION = re.compile(r"^% studium:reaction (?P<name>\S+) value=(?P<value>\S+)$")


def verify_reaction_labels(tikz: str, solution: BeamSolution) -> Evidence:
    """Printed reaction values equal the solved reactions to the precision printed."""

    evidence = Evidence()
    found = [match for match in (_REACTION.match(line.strip()) for line in tikz.splitlines()) if match]
    if not found:
        return evidence
    bad = []
    for match in found:
        name, text = match.group("name"), match.group("value")
        actual = solution.reactions.get(name)
        decimals = len(text.split(".", 1)[1]) if "." in text else 0
        if actual is None or abs(float(text) - as_float(actual)) > 0.5 * 10 ** (-decimals) * (1 + 1e-9):
            bad.append(f"{name} = {text}")
    printed = {match.group("name") for match in found}
    missing = sorted(set(solution.reactions) - printed)
    evidence.add(
        "printed reactions equal the solved reactions",
        "representation",
        not bad and not missing,
        ("wrong: " + ", ".join(bad) if bad else "") + (" missing: " + ", ".join(missing) if missing else ""),
    )
    return evidence


def _arrow(tail: tuple[float, float], tip: tuple[float, float], color: str = "black") -> str:
    return f"\\draw[-stealth,thick,{color}] ({fmt(tail[0])},{fmt(tail[1])}) -- ({fmt(tip[0])},{fmt(tip[1])});"


def _forces(model: BeamModel, style: Style, y: float) -> list[str]:
    sx = _sx(model, style)
    lines: list[str] = []
    for index, force in enumerate(model.forces):
        px = as_float(force.at) * sx
        fx, fy = as_float(force.fx), as_float(force.fy)
        size = (fx * fx + fy * fy) ** 0.5
        if size == 0:
            continue
        ux, uy = fx / size, fy / size
        text = _qty(style, sympy.sqrt(force.fx**2 + force.fy**2), _unit(model, "force"))
        if abs(uy) > 1e-9:
            offset = 0.06 if uy < 0 else -0.06
            tip = (px, y + offset)
            tail = (px - 1.05 * ux, y + offset - 1.05 * uy)
            anchor = "south" if uy < 0 else "north"
            lines.append(_mark("force", str(index), force.at, "tip"))
            lines.append(_arrow(tail, tip))
            lines.append(f"\\node[font=\\small,anchor={anchor}] at ({fmt(tail[0])},{fmt(tail[1])}) {{{text}}};")
        else:
            at_right_end = px > style.width - 1e-6
            at_left_end = px < 1e-6
            if (at_right_end and ux > 0) or (at_left_end and ux < 0):
                tail, tip = (px, y), (px + 1.0 * ux, y)
            else:
                tail, tip = (px - 1.0 * ux, y + 0.14), (px, y + 0.14)
            lines.append(_mark("force", str(index), force.at, "tail" if tail[0] == px else "tip"))
            lines.append(_arrow(tail, tip))
            lines.append(f"\\node[font=\\small,anchor=south] at ({fmt((tail[0] + tip[0]) / 2)},{fmt(max(tail[1], tip[1]) + 0.05)}) {{{text}}};")
    for index, couple in enumerate(model.couples):
        lines.append(_mark("couple", str(index), couple.at))
        lines.extend(_couple(as_float(couple.at) * sx, y, as_float(couple.ccw), _qty(style, abs(couple.ccw), _unit(model, "moment")), "black"))
    return lines


def _couple(px: float, y: float, ccw: float, text: str, color: str) -> list[str]:
    radius = 0.42
    label = f"\\node[font=\\small,anchor=south,{color}] at ({fmt(px)},{fmt(y + radius + 0.02)}) {{{text}}};"
    if ccw >= 0:
        arc = f"\\draw[-stealth,thick,{color}] ({fmt(px + radius)},{fmt(y)}) arc (0:250:{radius});"
    else:
        arc = f"\\draw[-stealth,thick,{color}] ({fmt(px - radius)},{fmt(y)}) arc (180:-70:{radius});"
    return [label, arc]


def _distributed(model: BeamModel, style: Style, y: float) -> list[str]:
    sx = _sx(model, style)
    lines: list[str] = []
    transverse = [load for load in model.distributed if load.axis == "y"]
    peak = max((max(abs(as_float(load.start)), abs(as_float(load.end))) for load in transverse), default=0.0)
    for load in transverse:
        a, b = as_float(load.a), as_float(load.b)
        count = max(3, int((b - a) * sx / 0.45) + 1)
        tops = []
        for k in range(count + 1):
            t = a + (b - a) * k / count
            q_up = as_float(load.intensity(sympy.Rational(repr(t))))
            height = 0.12 + (_LOAD_HEIGHT * abs(q_up) / peak if peak else 0)
            side = -1 if q_up > 0 else 1
            base = (t * sx, y + side * 0.1)
            top = (t * sx, y + side * (0.1 + height))
            tops.append(top)
            if abs(q_up) > 1e-12:
                lines.append(f"\\draw[-stealth,blue!60!black] ({fmt(top[0])},{fmt(top[1])}) -- ({fmt(base[0])},{fmt(base[1])});")
        lines.append(_mark("distributed", str(model.distributed.index(load)), load.a, "span", load.b))
        lines.append("\\draw[blue!60!black] " + " -- ".join(f"({fmt(px)},{fmt(py)})" for px, py in tops) + ";")
        unit = _unit(model, "distributed")
        start_text = _qty(style, abs(load.start), unit)
        end_text = _qty(style, abs(load.end), unit)
        first, last = tops[0], tops[-1]
        anchor = "south" if first[1] > y else "north"
        if sympy.simplify(load.start - load.end) == 0:
            middle = tops[len(tops) // 2]
            lines.append(f"\\node[font=\\small,anchor={anchor},blue!60!black] at ({fmt(middle[0])},{fmt(middle[1])}) {{{start_text}}};")
        else:
            if abs(as_float(load.start)) > 0:
                lines.append(f"\\node[font=\\small,anchor={anchor} west,blue!60!black] at ({fmt(first[0])},{fmt(first[1])}) {{{start_text}}};")
            if abs(as_float(load.end)) > 0:
                lines.append(f"\\node[font=\\small,anchor={anchor} east,blue!60!black] at ({fmt(last[0])},{fmt(last[1])}) {{{end_text}}};")
    for load in model.distributed:
        if load.axis != "x":
            continue
        a, b = as_float(load.a) * sx, as_float(load.b) * sx
        count = max(2, int((b - a) / 0.6))
        for k in range(count):
            start = a + (b - a) * (k + 0.2) / count
            length = 0.35 * (1 if load.sign > 0 else -1)
            lines.append(f"\\draw[-stealth,blue!60!black] ({fmt(start)},{fmt(y + 0.2)}) -- ({fmt(start + length)},{fmt(y + 0.2)});")
        lines.append(f"\\node[font=\\small,anchor=south,blue!60!black] at ({fmt((a + b) / 2)},{fmt(y + 0.25)}) {{{_qty(style, abs(load.start), _unit(model, 'distributed'))}}};")
    return lines


def _dimensions(model: BeamModel, style: Style, y: float) -> list[str]:
    sx = _sx(model, style)
    marks = sorted({as_float(p) for p in model.breakpoints()})
    lines = [f"\\draw[gray] (0,{fmt(y)}) -- ({fmt(style.width)},{fmt(y)});"]
    for mark in marks:
        lines.append(f"\\draw[gray] ({fmt(mark * sx)},{fmt(y - 0.1)}) -- ({fmt(mark * sx)},{fmt(y + 0.1)});")
    exact_marks = sorted(set(model.breakpoints()), key=as_float)
    for left, right in pairwise(exact_marks):
        middle = (as_float(left) + as_float(right)) / 2 * sx
        lines.append(
            f"\\node[font=\\small,anchor=north] at ({fmt(middle)},{fmt(y - 0.05)}) {{{_qty(style, right - left, _unit(model, 'length'))}}};"
        )
    return lines


def _axes(model: BeamModel, y: float) -> list[str]:
    down = model.convention.get("section_y_axis") == "down"
    tip = y - 0.7 if down else y + 0.7
    return [
        f"\\draw[-stealth] (-1.1,{fmt(y)}) -- (-0.4,{fmt(y)}) node[right,font=\\small] {{$x$}};",
        f"\\draw[-stealth] (-1.1,{fmt(y)}) -- (-1.1,{fmt(tip)}) node[{'below' if down else 'above'},font=\\small] {{$y$}};",
    ]


def _below_depth(model: BeamModel) -> float:
    """How far below the beam the drawing already reaches (supports, upward loads)."""

    depth = 0.55
    for load in model.distributed:
        if load.axis == "y" and (as_float(load.start) * load.sign > 0 or as_float(load.end) * load.sign > 0):
            depth = max(depth, 0.1 + 0.12 + _LOAD_HEIGHT + 0.35)
    return depth


# --------------------------------------------------------------------------- figures


def problem_figure(model: BeamModel, style: Style | None = None) -> str:
    style = style or Style()
    lines = []
    lines += _distributed(model, style, 0.0)
    lines += _beam_line(model, style, 0.0)
    lines += _supports(model, style, 0.0)
    lines += _hinges(model, style, 0.0)
    lines += _forces(model, style, 0.0)
    lines += _point_names(model, style, 0.0)
    lines += _dimensions(model, style, -_below_depth(model) - 0.45)
    lines += _axes(model, 0.0)
    return "\n".join(lines)


def _reactions(model: BeamModel, solution: BeamSolution | None, style: Style, y: float) -> list[str]:
    sx = _sx(model, style)
    lines: list[str] = []
    tail = y - _below_depth(model) - 0.55
    for support in model.supports:
        px = as_float(support.at) * sx
        for component, symbol in support.unknowns():
            name = str(symbol)
            letter, _, label = name.partition("_")
            symbol_tex = f"{letter}_{{{label}}}"
            text = f"${symbol_tex}$"
            if solution is not None:
                value = solution.reactions[name]
                unit = _unit(model, "moment" if component == "M" else "force")
                printed = style.number(value)
                lines.append(f"% studium:reaction {name} value={printed.replace('{,}', '.')}")
                text = f"${symbol_tex} = {printed}$~\\mbox{{{unit}}}"
            if component == "R":
                lines.append(_mark("reaction", name, support.at, "tip"))
                lines.append(_arrow((px, tail), (px, y - 0.06), "red!75!black"))
                lines.append(f"\\node[font=\\small,anchor=north,red!75!black] at ({fmt(px)},{fmt(tail - 0.02)}) {{{text}}};")
            elif component == "H":
                if px < style.width / 2:
                    lines.append(_mark("reaction", name, support.at, "tip"))
                    lines.append(_arrow((px - 1.0, y), (px, y), "red!75!black"))
                    lines.append(f"\\node[font=\\small,anchor=east,red!75!black] at ({fmt(px - 1.02)},{fmt(y)}) {{{text}}};")
                else:
                    lines.append(_mark("reaction", name, support.at, "first"))
                    lines.append(_arrow((px, y), (px + 1.0, y), "red!75!black"))
                    lines.append(f"\\node[font=\\small,anchor=west,red!75!black] at ({fmt(px + 1.02)},{fmt(y)}) {{{text}}};")
            else:
                radius = _REACTION_RADIUS
                lines.append(_mark("reaction", name, support.at, "arc"))
                lines.append(f"\\draw[-stealth,thick,red!75!black] ({fmt(px + radius)},{fmt(y)}) arc (0:250:{radius});")
                lines.append(f"\\node[font=\\small,anchor=south,red!75!black] at ({fmt(px + 0.15)},{fmt(y + radius + 0.02)}) {{{text}}};")
    return lines


def free_body_figure(model: BeamModel, solution: BeamSolution | None = None, style: Style | None = None) -> str:
    """The beam cut free from its supports. Reactions are drawn in their assumed positive sense:
    up, to the right and counter-clockwise. A negative value acts the other way."""

    style = style or Style()
    lines = []
    lines += _distributed(model, style, 0.0)
    lines += _beam_line(model, style, 0.0)
    lines += _hinges(model, style, 0.0)
    lines += _forces(model, style, 0.0)
    lines += _reactions(model, solution, style, 0.0)
    lines += _point_names(model, style, 0.0)
    lines += _dimensions(model, style, -_below_depth(model) - 1.15)
    return "\n".join(lines)


def _panel(
    name: str,
    curve: Piecewise,
    sign: int,
    y0: float,
    model: BeamModel,
    style: Style,
    unit: str,
) -> list[str]:
    sx = _sx(model, style)
    largest = max((abs(as_float(p.at(e))) for p in curve.pieces for e in (p.start, p.end)), default=0.0)
    for place in curve.critical_points():
        largest = max(largest, abs(as_float(curve.piece_at(place).at(place))))
    sy = _AMPLITUDE / largest if largest > 0 else 1.0
    frame = Frame(sx, sy, 0.0, y0, sign)
    lines = [f"\\draw[gray!70] (0,{fmt(y0)}) -- ({fmt(style.width + 0.3)},{fmt(y0)});"]
    lines += series(name, curve, frame, style=f"thick,{_STROKE[name]}", fill=_FILL[name])
    shown = model.symbols.get(name, name) if name in ("N", "V", "M") else name
    lines.append(f"\\node[font=\\small,anchor=east] at (-0.15,{fmt(y0)}) {{${shown}$ ({unit})}};")
    lines.append(f"\\node[font=\\small,anchor=west] at ({fmt(style.width + 0.3)},{fmt(y0)}) {{$x$}};")
    lines += _value_labels(name, curve, frame, model, style)
    lines += _sign_marks(curve, frame)
    return lines


def _value_labels(name: str, curve: Piecewise, frame: Frame, model: BeamModel, style: Style) -> list[str]:
    lines: list[str] = []
    shown: set[tuple[float, float]] = set()
    places = sorted({*(p.start for p in curve.pieces), curve.end}, key=as_float)
    for place in places:
        values = jump_side_values(curve, place)
        if place == curve.start:
            values = [("right", curve.right(place))]
        elif place == curve.end:
            values = [("left", curve.left(place))]
        for side, value in values:
            number = as_float(value)
            key = (round(as_float(place), 6), round(number, 6))
            if abs(number) < 1e-12 or key in shown:
                continue
            shown.add(key)
            px, py = frame.point(as_float(place), number)
            above = py >= frame.y0
            vertical = "south" if above else "north"
            horizontal = {"left": " east", "right": " west", "both": ""}[side]
            printed = style.number(value)
            lines.append(label_comment(name, place, side, printed))
            lines.append(f"\\fill ({fmt(px)},{fmt(py)}) circle (0.03);")
            lines.append(f"\\node[font=\\scriptsize,anchor={vertical}{horizontal},inner sep=1.5pt] at ({fmt(px)},{fmt(py)}) {{${printed}$}};")
    for place in curve.critical_points():
        value = curve.piece_at(place).at(place)
        px, py = frame.point(as_float(place), as_float(value))
        upward = py >= frame.y0
        vertical = "south" if upward else "north"
        ly = py + (0.38 if upward else -0.38)
        lines.append(label_comment(name, place, "both", style.number(value)))
        lines.append(f"\\fill ({fmt(px)},{fmt(py)}) circle (0.04);")
        lines.append(f"\\draw[densely dotted] ({fmt(px)},{fmt(frame.y0)}) -- ({fmt(px)},{fmt(py)});")
        lines.append(f"\\draw[gray] ({fmt(px)},{fmt(py)}) -- ({fmt(px)},{fmt(ly)});")
        lines.append(
            f"\\node[font=\\scriptsize,anchor={vertical},inner sep=1pt,align=center,fill=white,fill opacity=0.8,text opacity=1] at ({fmt(px)},{fmt(ly)}) "
            f"{{${style.number(value)}$\\\\[-1pt]$(x = {style.number(place)})$}};"
        )
    for place in curve.zeros():
        px, _ = frame.point(as_float(place), 0.0)
        lines.append(f"\\draw ({fmt(px)},{fmt(frame.y0)}) circle (0.045);")
    return lines


def _sign_marks(curve: Piecewise, frame: Frame) -> list[str]:
    lines: list[str] = []
    for piece in curve.pieces:
        cuts = sorted([piece.start, piece.end, *[z for z in curve.zeros() if bool(piece.start < z < piece.end)]], key=as_float)
        for left, right in pairwise(cuts):
            if as_float(right) - as_float(left) < 0.08 * as_float(curve.end - curve.start):
                continue
            middle = (left + right) / 2
            value = as_float(piece.expr.subs(X, middle))
            if abs(value) < 1e-12:
                continue
            px, py = frame.point(as_float(middle), value * 0.45)
            mark = "\\oplus" if value > 0 else "\\ominus"
            lines.append(f"\\node[font=\\footnotesize,gray!60!black] at ({fmt(px)},{fmt(py)}) {{${mark}$}};")
    return lines


def _nonzero(curve: Piecewise) -> bool:
    return any(sympy.simplify(piece.expr) != 0 for piece in curve.pieces)


def internal_forces_figure(
    solution: BeamSolution,
    style: Style | None = None,
    functions: tuple[str, ...] = ("N", "V", "M"),
    include_load: bool = True,
) -> tuple[str, dict[str, Piecewise], dict[str, int]]:
    """Loaded beam (with reaction values) above aligned diagrams.

    ``N`` is drawn only when it is not zero everywhere. Returns the TikZ body,
    the drawn curves and the plot sign of each, for the representation check.
    """

    style = style or Style()
    model = solution.model
    curves = {"N": solution.N, "V": solution.V, "M": solution.M}
    chosen = [name for name in functions if name in curves and (name != "N" or _nonzero(curves["N"]))]
    lines: list[str] = []
    top = 0.0
    if include_load:
        lines += _distributed(model, style, 0.0)
        lines += _beam_line(model, style, 0.0)
        lines += _hinges(model, style, 0.0)
        lines += _forces(model, style, 0.0)
        lines += _reactions(model, solution, style, 0.0)
        lines += _point_names(model, style, 0.0)
        top = -_below_depth(model) - 0.95
    units = {"N": _unit(model, "force"), "V": _unit(model, "force"), "M": _unit(model, "moment")}
    signs = {name: model.convention.plot_sign(name) for name in chosen}
    y0 = top - 1.5
    bottom = y0
    for name in chosen:
        lines += _panel(name, curves[name], signs[name], y0, model, style, units[name])
        bottom = y0 - 1.4
        y0 -= 3.3
    sx = _sx(model, style)
    for place in model.breakpoints():
        px = as_float(place) * sx
        lines.insert(0, f"\\draw[densely dashed,gray!55] ({fmt(px)},{fmt(top + (1.0 if include_load else 0))}) -- ({fmt(px)},{fmt(bottom)});")
    return "\n".join(lines), {name: curves[name] for name in chosen}, signs


def virtual_work_figure(
    real: BeamSolution, virtual: BeamSolution, style: Style | None = None
) -> tuple[str, dict[str, Piecewise], dict[str, int]]:
    """Real loading and its M diagram above the unit virtual loading and its m diagram."""

    style = style or Style()
    model = real.model
    lines: list[str] = []
    lines += _distributed(model, style, 0.0)
    lines += _beam_line(model, style, 0.0)
    lines += _supports(model, style, 0.0)
    lines += _hinges(model, style, 0.0)
    lines += _forces(model, style, 0.0)
    lines += _point_names(model, style, 0.0)
    sign = model.convention.plot_sign("M")
    top = -_below_depth(model) - 0.6
    lines += _panel("M", real.M, sign, top - 1.5, model, style, _unit(model, "moment"))
    virtual_y = top - 4.6
    vmodel = virtual.model
    lines += _beam_line(vmodel, style, virtual_y)
    lines += _supports(vmodel, style, virtual_y)
    lines += _hinges(vmodel, style, virtual_y)
    sx = _sx(model, style)
    for force in vmodel.forces:
        px = as_float(force.at) * sx
        up = as_float(force.fy) > 0
        tail = (px, virtual_y - 1.0) if up else (px, virtual_y + 1.0)
        tip = (px, virtual_y - 0.06) if up else (px, virtual_y + 0.06)
        lines.append(_arrow(tail, tip, "violet!70!black"))
        lines.append(f"\\node[font=\\small,violet!70!black,anchor={'north' if up else 'south'}] at ({fmt(tail[0])},{fmt(tail[1])}) {{$1$}};")
    for couple in vmodel.couples:
        lines.extend(_couple(as_float(couple.at) * sx, virtual_y, as_float(couple.ccw), "$1$", "violet!70!black"))
    unit_m = _unit(model, "length")
    lines += _panel("m", virtual.M, sign, virtual_y - _below_depth(vmodel) - 1.9, vmodel, style, unit_m)
    return "\n".join(lines), {"M": real.M, "m": virtual.M}, {"M": sign, "m": sign}


def deflection_figure(solution: BeamSolution, style: Style | None = None) -> tuple[str, dict[str, Piecewise], dict[str, int]]:
    """The deflected shape (upward positive), exaggerated, above the supports."""

    if solution.v is None:
        raise ValueError("the solution has no elastic line; give EI")
    style = style or Style()
    model = solution.model
    sx = _sx(model, style)
    curve = solution.v
    found = extremes(curve)
    largest = max(abs(as_float(found["max"].value)), abs(as_float(found["min"].value)))
    sy = 1.0 / largest if largest > 0 else 1.0
    frame = Frame(sx, sy, 0.0, 0.0, 1)
    lines = [f"\\draw[gray,dashed,line width=1pt] (0,0) -- ({fmt(style.width)},0);"]
    lines += _supports(model, style, 0.0)
    lines += _hinges(model, style, 0.0)
    lines += series("v", curve, frame, style="very thick")
    for kind in ("max", "min"):
        item = found[kind]
        value = item.value
        if abs(as_float(value)) < 1e-15:
            continue
        place = item.x
        px, py = frame.point(as_float(place), as_float(value))
        lines.append(label_comment("v", place, "both", style.number(value)))
        lines.append(f"\\fill ({fmt(px)},{fmt(py)}) circle (0.045);")
        anchor = "south" if py >= 0 else "north"
        lines.append(
            f"\\node[font=\\scriptsize,anchor={anchor},align=center] at ({fmt(px)},{fmt(py)}) "
            f"{{$v = {style.number(value)}$~\\mbox{{{_unit(model, 'length')}}}\\\\[-1pt]$(x = {style.number(place)})$}};"
        )
    lines += _point_names(model, style, -0.5)
    return "\n".join(lines), {"v": curve}, {"v": 1}
