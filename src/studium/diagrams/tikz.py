"""TikZ output for function plots, with a machine-readable trace.

Every plotted curve is preceded by a comment that names the series and the
affine map from data to paper::

    % studium:series V sx=1.5 sy=0.02 x0=0 y0=-3.2 sign=1
    \\draw[...] (0.0000,-3.2000) -- (0.3750,-3.1500) -- ...;

and every printed value by::

    % studium:label V x=2 side=left value=-24.35

:func:`verify_representation` reads those comments and coordinates back and
compares them with the stored functions. The plot sign is supplied by the
caller from the declared convention, not read from the drawing, so a drawing
that flips a diagram fails even if its own comment agrees with itself.
"""

import re
from dataclasses import dataclass
from itertools import pairwise
from typing import cast

import sympy

from studium.diagrams.evidence import Evidence
from studium.diagrams.piecewise import Piecewise, X, as_float, format_number

_SERIES = re.compile(
    r"^% studium:series (?P<name>[A-Za-z0-9_]+) sx=(?P<sx>[-0-9.eE]+) sy=(?P<sy>[-0-9.eE]+) "
    r"x0=(?P<x0>[-0-9.eE]+) y0=(?P<y0>[-0-9.eE]+) sign=(?P<sign>-?1)\s*$"
)
_LABEL = re.compile(
    r"^% studium:label (?P<name>[A-Za-z0-9_]+) x=(?P<x>\S+) side=(?P<side>left|right|both) value=(?P<value>\S+)\s*$"
)
_POINT = re.compile(r"\((-?[0-9.]+),(-?[0-9.]+)\)")
_DIGITS = 4


@dataclass(frozen=True)
class Frame:
    """Affine map from data ``(x, f)`` to paper ``(x0 + sx*x, y0 + sign*sy*f)`` in cm."""

    sx: float
    sy: float
    x0: float
    y0: float
    sign: int

    def point(self, x: float, value: float) -> tuple[float, float]:
        return self.x0 + self.sx * x, self.y0 + self.sign * self.sy * value


def fmt(value: float) -> str:
    text = f"{value:.{_DIGITS}f}"
    return "0.0000" if text in ("-0.0000",) else text


def sample(curve: Piecewise, per_piece: int = 32) -> list[list[tuple[sympy.Expr, float]]]:
    """Sample each piece: exact ends, interior critical points, and evenly spaced points."""

    runs: list[list[tuple[sympy.Expr, float]]] = []
    critical = curve.critical_points()
    for piece in curve.pieces:
        degree = sympy.Poly(piece.expr, X).degree() if piece.expr.free_symbols else 0
        count = 1 if degree <= 1 else per_piece
        places = [piece.start + (piece.end - piece.start) * sympy.Rational(k, count) for k in range(count + 1)]
        places += [place for place in critical if bool(piece.start < place < piece.end)]
        places = sorted(set(places), key=as_float)
        runs.append([(place, as_float(piece.expr.subs(X, place))) for place in places])
    return runs


def series(
    name: str,
    curve: Piecewise,
    frame: Frame,
    *,
    style: str = "thick",
    fill: str | None = None,
) -> list[str]:
    """Draw a piecewise curve, one path per piece, between ``studium:series`` and ``studium:end``.

    Fills and the vertical segments at jumps are drawn outside the traced block,
    so the trace holds only points that must lie on the function.
    """

    runs = sample(curve)
    lines: list[str] = []
    if fill:
        for run in runs:
            first = frame.point(as_float(run[0][0]), 0.0)
            last = frame.point(as_float(run[-1][0]), 0.0)
            body = " -- ".join(_xy(frame.point(as_float(place), value)) for place, value in run)
            lines.append(f"\\fill[{fill}] {_xy(first)} -- {body} -- {_xy(last)} -- cycle;")
    lines.append(
        f"% studium:series {name} sx={frame.sx!r} sy={frame.sy!r} x0={frame.x0!r} y0={frame.y0!r} sign={frame.sign}"
    )
    for run in runs:
        lines.append(f"\\draw[{style}] " + " -- ".join(_xy(frame.point(as_float(place), value)) for place, value in run) + ";")
    lines.append(f"% studium:end {name}")
    for left, right in pairwise(runs):
        top = frame.point(as_float(left[-1][0]), left[-1][1])
        bottom = frame.point(as_float(right[0][0]), right[0][1])
        if abs(top[1] - bottom[1]) > 1e-6:
            lines.append(f"\\draw[{style}] {_xy(top)} -- {_xy(bottom)};")
    return lines


def _xy(point: tuple[float, float]) -> str:
    return f"({fmt(point[0])},{fmt(point[1])})"


def label_comment(name: str, x: sympy.Expr, side: str, printed: str) -> str:
    """Trace of a printed number. ``printed`` is the text as typeset, with a point as decimal mark."""

    return f"% studium:label {name} x={x} side={side} value={printed.replace('{,}', '.')}"


def value_text(value: object, *, decimals: int = 2, comma: bool = False) -> str:
    return "$" + format_number(value, decimals=decimals, comma=comma) + "$"


def verify_representation(
    tikz: str,
    curves: dict[str, Piecewise],
    signs: dict[str, int],
    *,
    tolerance: float = 2e-3,
) -> Evidence:
    """Parse the drawing and compare it with the stored functions.

    Checks, per series: the declared sign equals the convention's sign; every
    drawn point lies on the function (within ``tolerance`` cm); the drawn
    abscissae span the function's whole domain. Per label: the printed value
    equals the function at that point to the precision it is printed with.
    """

    evidence = Evidence()
    found = _parse(tikz)
    for name, curve in curves.items():
        entry = found.get(name)
        if entry is None:
            evidence.add(f"{name} diagram is drawn", "representation", False, "no studium:series trace in the drawing")
            continue
        frame, paths = entry
        expected_sign = signs.get(name, 1)
        evidence.add(
            f"{name} diagram drawn on the side the convention declares",
            "representation",
            frame.sign == expected_sign,
            f"drawn sign {frame.sign}, convention sign {expected_sign}",
        )
        worst = 0.0
        count = 0
        outside = False
        xs: list[float] = []
        for path in paths:
            if not path:
                continue
            abscissae = [(px - frame.x0) / frame.sx for px, _ in path]
            xs.extend(abscissae)
            middle = (min(abscissae) + max(abscissae)) / 2
            piece = next(
                (p for p in curve.pieces if as_float(p.start) - 1e-9 <= middle <= as_float(p.end) + 1e-9), None
            )
            if piece is None:
                outside = True
                continue
            for (_, py), x_value in zip(path, abscissae, strict=True):
                if not as_float(piece.start) - 1e-3 <= x_value <= as_float(piece.end) + 1e-3:
                    outside = True
                value = as_float(piece.expr.subs(X, sympy.Rational(repr(round(x_value, 9)))))
                expected_y = frame.y0 + expected_sign * frame.sy * value
                worst = max(worst, abs(expected_y - py))
                count += 1
        evidence.add(
            f"every drawn point of {name} lies on the stored function",
            "representation",
            count > 0 and worst <= tolerance and not outside,
            f"{count} points in {len(paths)} paths, largest deviation {worst:.2e} cm" + ("; a path leaves its interval" if outside else ""),
            residual=f"{worst:.3e}",
        )
        span_ok = bool(xs) and abs(min(xs) - as_float(curve.start)) < 1e-3 and abs(max(xs) - as_float(curve.end)) < 1e-3
        evidence.add(f"{name} is drawn over its whole domain", "representation", span_ok)
    labels_ok = True
    detail = ""
    count = 0
    for name, x_text, side, value_text_ in _labels(tikz):
        curve = curves.get(name)
        if curve is None:
            continue
        count += 1
        place = cast(sympy.Expr, sympy.sympify(x_text))
        actual = curve.left(place) if side == "left" else curve.right(place)
        decimals = len(value_text_.split(".", 1)[1]) if "." in value_text_ else 0
        if abs(float(value_text_) - as_float(actual)) > 0.5 * 10 ** (-decimals) * (1 + 1e-9):
            labels_ok = False
            detail = f"label {name}({x_text}, {side}) = {value_text_} but the function gives {as_float(actual):.6g}"
    if count:
        evidence.add("printed values equal the functions at their points", "representation", labels_ok, detail or f"{count} labels")
    return evidence


def _parse(tikz: str) -> dict[str, tuple[Frame, list[list[tuple[float, float]]]]]:
    found: dict[str, tuple[Frame, list[list[tuple[float, float]]]]] = {}
    current: str | None = None
    frame: Frame | None = None
    paths: list[list[tuple[float, float]]] = []
    for line in tikz.splitlines():
        stripped = line.strip()
        match = _SERIES.match(stripped)
        if match:
            current = match.group("name")
            frame = Frame(
                float(match.group("sx")),
                float(match.group("sy")),
                float(match.group("x0")),
                float(match.group("y0")),
                int(match.group("sign")),
            )
            paths = []
            continue
        if current is not None and stripped == f"% studium:end {current}":
            assert frame is not None
            found[current] = (frame, paths)
            current = None
            continue
        if current is not None and stripped.startswith("\\draw"):
            paths.append([(float(a), float(b)) for a, b in _POINT.findall(stripped)])
    return found


def _labels(tikz: str) -> list[tuple[str, str, str, str]]:
    labels = []
    for line in tikz.splitlines():
        match = _LABEL.match(line.strip())
        if match:
            labels.append((match.group("name"), match.group("x"), match.group("side"), match.group("value")))
    return labels


def jump_side_values(curve: Piecewise, place: sympy.Expr) -> list[tuple[str, sympy.Expr]]:
    """``[("left", value), ("right", value)]`` at a jump, or one ``("both", value)``."""

    left = curve.left(place)
    right = curve.right(place)
    if sympy.simplify(right - left) == 0:
        return [("both", left)]
    return [("left", left), ("right", right)]

