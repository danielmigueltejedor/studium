"""Cross-sections made of polygons: geometric properties, normal stresses, checks.

A section is a list of named parts in section coordinates ``(z, y)``; the
directions of the axes come from the declared convention (``section_y_axis``).
Parts are rectangles ``{"name": "ala", "z": [0, 120], "y": [0, 20]}`` or
polygons ``{"name": "lado", "polygon": [[z, y], ...]}``; ``"hole": true``
subtracts a part.

Area, first and second moments are exact (shoelace and Green's-theorem
formulas on rational vertices). They are computed twice: part by part with the
parallel-axis theorem (closed-form ``b h^3/12`` for rectangles), and directly
about the centroid from the vertex formulas. Normal stresses follow

    sigma = N/A + [(Mz Iy - My Iyz) y + (My Iz - Mz Iyz) z] / (Iy Iz - Iyz^2),

whose resultants are checked by integrating ``sigma`` over the polygons:
``int sigma dA = N``, ``int sigma y dA = Mz``, ``int sigma z dA = My``.
"""

import math
from dataclasses import dataclass

import sympy

from studium.diagrams.evidence import Evidence
from studium.diagrams.piecewise import DataError, as_float, exact
from studium.engineering.structures.claims import compare
from studium.engineering.structures.convention import Convention, parse_convention

Point = tuple[sympy.Expr, sympy.Expr]
_MAX_PARTS = 40
_MAX_VERTICES = 200


@dataclass(frozen=True)
class Part:
    name: str
    points: tuple[Point, ...]
    hole: bool = False
    rect: tuple[sympy.Expr, sympy.Expr, sympy.Expr, sympy.Expr] | None = None  # z0, z1, y0, y1


@dataclass(frozen=True)
class Moments:
    """Integrals over a region about the origin: A, int y, int z, int y^2, int z^2, int y z."""

    area: sympy.Expr
    sy: sympy.Expr
    sz: sympy.Expr
    yy: sympy.Expr
    zz: sympy.Expr
    yz: sympy.Expr

    def __add__(self, other: "Moments") -> "Moments":
        return Moments(*(a + b for a, b in zip(self.astuple(), other.astuple(), strict=True)))

    def __neg__(self) -> "Moments":
        return Moments(*(-a for a in self.astuple()))

    def astuple(self) -> tuple[sympy.Expr, ...]:
        return (self.area, self.sy, self.sz, self.yy, self.zz, self.yz)


@dataclass
class SectionModel:
    parts: list[Part]
    units: dict[str, str]
    convention: Convention
    loads: dict[str, sympy.Expr]


@dataclass
class SectionSolution:
    model: SectionModel
    area: sympy.Expr
    centroid: Point  # (z_G, y_G) in the given coordinates
    Iz: sympy.Expr
    Iy: sympy.Expr
    Iyz: sympy.Expr
    I1: sympy.Expr
    I2: sympy.Expr
    theta: sympy.Expr  # radians, from z towards y, of the axis of I1
    stress: sympy.Expr | None  # sigma(z, y) in centroidal coordinates, or None
    extremes: dict[str, tuple[sympy.Expr, Point]]


Z, Y = sympy.symbols("z y", real=True)


def parse_section(spec: object) -> SectionModel:
    if not isinstance(spec, dict):
        raise DataError("a section must be an object")
    raw_parts = spec.get("parts")
    if not isinstance(raw_parts, list) or not raw_parts or len(raw_parts) > _MAX_PARTS:
        raise DataError("parts must be a non-empty list")
    parts: list[Part] = []
    for index, item in enumerate(raw_parts):
        where = f"parts[{index}]"
        if not isinstance(item, dict):
            raise DataError(f"{where} must be an object")
        name = item.get("name")
        if not isinstance(name, str) or not name.strip() or len(name) > 30:
            raise DataError(f"{where}.name is required")
        hole = item.get("hole") is True
        if "polygon" in item:
            vertices = item.get("polygon")
            if not isinstance(vertices, list) or not 3 <= len(vertices) <= _MAX_VERTICES:
                raise DataError(f"{where}.polygon needs at least three [z, y] vertices")
            points = tuple((exact(v[0], f"{where}.z"), exact(v[1], f"{where}.y")) for v in vertices if isinstance(v, list) and len(v) == 2)
            if len(points) != len(vertices):
                raise DataError(f"{where}.polygon vertices must be [z, y] pairs")
            parts.append(Part(name.strip(), points, hole))
        else:
            zs, ys = item.get("z"), item.get("y")
            if not (isinstance(zs, list) and isinstance(ys, list) and len(zs) == 2 and len(ys) == 2):
                raise DataError(f"{where} needs z: [z0, z1] and y: [y0, y1], or a polygon")
            z0, z1 = sorted((exact(zs[0], f"{where}.z"), exact(zs[1], f"{where}.z")), key=as_float)
            y0, y1 = sorted((exact(ys[0], f"{where}.y"), exact(ys[1], f"{where}.y")), key=as_float)
            if z0 == z1 or y0 == y1:
                raise DataError(f"{where} has zero width or height")
            points = ((z0, y0), (z1, y0), (z1, y1), (z0, y1))
            parts.append(Part(name.strip(), points, hole, (z0, z1, y0, y1)))
    names = [part.name for part in parts]
    if len(set(names)) != len(names):
        raise DataError("part names must be unique")
    units = {"length": "mm", "force": "N"}
    raw_units = spec.get("units")
    if isinstance(raw_units, dict):
        for key in ("length", "force"):
            if isinstance(raw_units.get(key), str) and raw_units[key].strip():
                units[key] = raw_units[key].strip()
    loads: dict[str, sympy.Expr] = {}
    raw_loads = spec.get("loads")
    if raw_loads is not None:
        if not isinstance(raw_loads, dict):
            raise DataError("loads must map N, My, Mz to values")
        for key in ("N", "My", "Mz"):
            if raw_loads.get(key) is not None:
                loads[key] = exact(raw_loads[key], f"loads.{key}")
        unknown = set(raw_loads) - {"N", "My", "Mz"}
        if unknown:
            raise DataError(f"unknown load components: {', '.join(sorted(unknown))}")
    return SectionModel(parts, units, parse_convention(spec.get("convention")), loads)


def polygon_moments(points: tuple[Point, ...]) -> Moments:
    """Exact integrals over a simple polygon, made positive whatever the vertex order."""

    area = sy = sz = yy = zz = yz = sympy.Integer(0)
    count = len(points)
    for index in range(count):
        z0, y0 = points[index]
        z1, y1 = points[(index + 1) % count]
        cross = z0 * y1 - z1 * y0
        area += cross / 2
        sz += (z0 + z1) * cross / 6
        sy += (y0 + y1) * cross / 6
        zz += (z0**2 + z0 * z1 + z1**2) * cross / 12
        yy += (y0**2 + y0 * y1 + y1**2) * cross / 12
        yz += (z0 * y1 + 2 * z0 * y0 + 2 * z1 * y1 + z1 * y0) * cross / 24
    moments = Moments(*(sympy.expand(v) for v in (area, sy, sz, yy, zz, yz)))
    if as_float(moments.area) < 0:
        moments = -moments
    if moments.area == 0:
        raise DataError("a part has zero area")
    return moments


def _shift(points: tuple[Point, ...], dz: sympy.Expr, dy: sympy.Expr) -> tuple[Point, ...]:
    return tuple((z - dz, y - dy) for z, y in points)


def solve_section(model: SectionModel) -> SectionSolution:
    total = Moments(*([sympy.Integer(0)] * 6))
    for part in model.parts:
        moments = polygon_moments(part.points)
        total = total + (-moments if part.hole else moments)
    if as_float(total.area) <= 0:
        raise DataError("the holes remove all the area")
    zg = total.sz / total.area
    yg = total.sy / total.area
    centroidal = Moments(*([sympy.Integer(0)] * 6))
    for part in model.parts:
        moments = polygon_moments(_shift(part.points, zg, yg))
        centroidal = centroidal + (-moments if part.hole else moments)
    iz, iy, iyz = centroidal.yy, centroidal.zz, centroidal.yz
    mean = (iz + iy) / 2
    radius = sympy.sqrt(((iz - iy) / 2) ** 2 + iyz**2)
    theta = sympy.atan2(-2 * iyz, iz - iy) / 2 if (iyz != 0 or iz != iy) else sympy.Integer(0)
    stress = None
    extremes: dict[str, tuple[sympy.Expr, Point]] = {}
    if model.loads:
        normal = model.loads.get("N", sympy.Integer(0))
        my = model.loads.get("My", sympy.Integer(0))
        mz = model.loads.get("Mz", sympy.Integer(0))
        det = iy * iz - iyz**2
        stress = sympy.expand(normal / total.area + ((mz * iy - my * iyz) * Y + (my * iz - mz * iyz) * Z) / det)
        values = []
        for part in model.parts:
            if part.hole:
                continue
            for z, y in part.points:
                values.append((sympy.expand(stress.subs({Z: z - zg, Y: y - yg})), (z, y)))
        extremes["max"] = max(values, key=lambda item: as_float(item[0]))
        extremes["min"] = min(values, key=lambda item: as_float(item[0]))
    return SectionSolution(
        model,
        total.area,
        (zg, yg),
        iz,
        iy,
        iyz,
        sympy.radsimp(mean + radius),
        sympy.radsimp(mean - radius),
        theta,
        stress,
        extremes,
    )


def contains(points: tuple[Point, ...], point: Point) -> bool:
    """Point in polygon, boundary included (exact for rational data)."""

    z, y = point
    count = len(points)
    for index in range(count):
        (z0, y0), (z1, y1) = points[index], points[(index + 1) % count]
        cross = (z1 - z0) * (y - y0) - (y1 - y0) * (z - z0)
        if cross == 0 and min(as_float(z0), as_float(z1)) <= as_float(z) <= max(as_float(z0), as_float(z1)) and min(
            as_float(y0), as_float(y1)
        ) <= as_float(y) <= max(as_float(y0), as_float(y1)):
            return True
    inside = False
    for index in range(count):
        (z0, y0), (z1, y1) = points[index], points[(index + 1) % count]
        if (as_float(y0) > as_float(y)) != (as_float(y1) > as_float(y)):
            crossing = z0 + (y - y0) * (z1 - z0) / (y1 - y0)
            if as_float(z) < as_float(crossing):
                inside = not inside
    return inside


def parts_containing(solution: SectionSolution, point: Point) -> list[str]:
    holes = [part for part in solution.model.parts if part.hole and contains(part.points, point)]
    if holes:
        return []
    return [part.name for part in solution.model.parts if not part.hole and contains(part.points, point)]


def verify_section(solution: SectionSolution, claims: object = None) -> Evidence:
    model = solution.model
    evidence = Evidence()
    zg, yg = solution.centroid
    # 1. Parallel-axis route, part by part, closed form for rectangles.
    area = iz = iy = iyz = sympy.Integer(0)
    for part in model.parts:
        sign = -1 if part.hole else 1
        if part.rect is not None:
            z0, z1, y0, y1 = part.rect
            b, h = z1 - z0, y1 - y0
            a = b * h
            cz, cy = (z0 + z1) / 2, (y0 + y1) / 2
            own_iz, own_iy, own_iyz = b * h**3 / 12, h * b**3 / 12, sympy.Integer(0)
        else:
            m = polygon_moments(part.points)
            a = m.area
            cz, cy = m.sz / a, m.sy / a
            own = polygon_moments(_shift(part.points, cz, cy))
            own_iz, own_iy, own_iyz = own.yy, own.zz, own.yz
        area += sign * a
        iz += sign * (own_iz + a * (cy - yg) ** 2)
        iy += sign * (own_iy + a * (cz - zg) ** 2)
        iyz += sign * (own_iyz + a * (cy - yg) * (cz - zg))
    for name, first, second in (
        ("area", area, solution.area),
        ("Iz", iz, solution.Iz),
        ("Iy", iy, solution.Iy),
        ("Iyz", iyz, solution.Iyz),
    ):
        difference = sympy.simplify(first - second)
        evidence.add(f"{name}: parallel-axis sum equals the direct centroidal integral", "symbolic", difference == 0, residual=difference)
    # 2. The first moment about the centroid vanishes.
    first = Moments(*([sympy.Integer(0)] * 6))
    for part in model.parts:
        moments = polygon_moments(_shift(part.points, zg, yg))
        first = first + (-moments if part.hole else moments)
    evidence.add("first moments about the centroid are zero", "symbolic", first.sy == 0 and first.sz == 0)
    # 3. Principal values: invariants and zero product of inertia on the principal axes.
    invariant_sum = _zero(solution.I1 + solution.I2 - solution.Iz - solution.Iy)
    invariant_product = _zero(solution.I1 * solution.I2 - (solution.Iz * solution.Iy - solution.Iyz**2))
    evidence.add("principal moments keep the trace and the determinant", "symbolic", invariant_sum and invariant_product)
    # On the axis of I1: cos 2t = (Iz - Iy) / (I1 - I2) and sin 2t = -2 Iyz / (I1 - I2), with I1 - I2 taken
    # from the principal values themselves. Exact algebra, then the stored angle is compared with them.
    half_gap = (solution.I1 - solution.I2) / 2
    if half_gap == 0:
        evidence.add("product of inertia vanishes on the principal axes; I1 lies on the first axis", "symbolic", solution.Iyz == 0)
    else:
        c2 = (solution.Iz - solution.Iy) / (2 * half_gap)
        s2 = -solution.Iyz / half_gap
        product = _zero((solution.Iz - solution.Iy) / 2 * s2 + solution.Iyz * c2)
        rotated = _zero((solution.Iz + solution.Iy) / 2 + (solution.Iz - solution.Iy) / 2 * c2 - solution.Iyz * s2 - solution.I1)
        evidence.add("product of inertia vanishes on the principal axes; I1 lies on the first axis", "symbolic", product and rotated)
        angle = 2 * as_float(solution.theta)
        evidence.add(
            "stored principal angle matches the principal direction",
            "numeric",
            abs(math.cos(angle) - as_float(c2)) < 1e-12 and abs(math.sin(angle) - as_float(s2)) < 1e-12,
        )
    evidence.add("I1 >= I2 > 0", "symbolic", as_float(solution.I1) >= as_float(solution.I2) > 0)
    # 4. Centroid lies in the section's bounding box (a necessary geometric condition).
    zs = [as_float(z) for part in model.parts for z, _ in part.points]
    ys = [as_float(y) for part in model.parts for _, y in part.points]
    evidence.add(
        "centroid lies inside the section's bounding box",
        "symbolic",
        min(zs) <= as_float(zg) <= max(zs) and min(ys) <= as_float(yg) <= max(ys),
    )
    # 5. Stress resultants.
    if solution.stress is not None:
        resultants = Moments(*([sympy.Integer(0)] * 6))
        for part in model.parts:
            moments = polygon_moments(_shift(part.points, zg, yg))
            resultants = resultants + (-moments if part.hole else moments)
        coefficients = sympy.Poly(solution.stress, Y, Z)
        c0 = coefficients.coeff_monomial(1)
        cy = coefficients.coeff_monomial(Y)
        cz = coefficients.coeff_monomial(Z)
        n_check = sympy.simplify(c0 * resultants.area + cy * resultants.sy + cz * resultants.sz - model.loads.get("N", 0))
        mz_check = sympy.simplify(c0 * resultants.sy + cy * resultants.yy + cz * resultants.yz - model.loads.get("Mz", 0))
        my_check = sympy.simplify(c0 * resultants.sz + cy * resultants.yz + cz * resultants.zz - model.loads.get("My", 0))
        evidence.add("stress resultants: int sigma dA = N", "symbolic", n_check == 0, residual=n_check)
        evidence.add("stress resultants: int sigma y dA = Mz", "symbolic", mz_check == 0, residual=mz_check)
        evidence.add("stress resultants: int sigma z dA = My", "symbolic", my_check == 0, residual=my_check)
    # 6. Scaling: lengths x3 must scale A by 9 and inertias by 81.
    lam = sympy.Integer(3)
    scaled = SectionModel(
        [Part(p.name, tuple((z * lam, y * lam) for z, y in p.points), p.hole, tuple(v * lam for v in p.rect) if p.rect else None) for p in model.parts],  # type: ignore[arg-type]
        model.units,
        model.convention,
        {},
    )
    other = solve_section(scaled)
    good = (
        sympy.simplify(other.area - lam**2 * solution.area) == 0
        and sympy.simplify(other.Iz - lam**4 * solution.Iz) == 0
        and sympy.simplify(other.Iyz - lam**4 * solution.Iyz) == 0
    )
    evidence.add("dimensional scaling (lengths x3): area as length^2, inertias as length^4", "dimensional", good)
    if claims is not None:
        evidence.extend(check_section_claims(solution, claims))
    return evidence


def _zero(expr: sympy.Expr) -> bool:
    """Exact zero test for rational expressions with square roots (no trigonometric simplification)."""

    return sympy.radsimp(sympy.together(sympy.expand(expr))) == 0


def check_section_claims(solution: SectionSolution, claims: object) -> Evidence:
    """``centroid`` {z, y}; ``centroid_in`` / ``centroid_not_in`` (part names);
    values ``A``, ``Iz``, ``Iy``, ``Iyz``, ``I1``, ``I2``, ``theta_deg``, ``sigma_max``, ``sigma_min``."""

    evidence = Evidence()
    if not isinstance(claims, dict):
        evidence.add("claims are readable", "symbolic", False, "claims must be an object")
        return evidence
    zg, yg = solution.centroid
    centroid = claims.get("centroid")
    if isinstance(centroid, dict):
        for axis, actual in (("z", zg), ("y", yg)):
            if axis in centroid:
                evidence.add(*compare(f"claimed centroid {axis}", centroid[axis], actual, {}))
    inside = parts_containing(solution, (zg, yg))
    for key, expect in (("centroid_in", True), ("centroid_not_in", False)):
        names = claims.get(key)
        if names is None:
            continue
        for name in [names] if isinstance(names, str) else list(names) if isinstance(names, list) else []:
            if all(part.name != name for part in solution.model.parts):
                evidence.add(f"claimed centroid position relative to {name}", "symbolic", False, "no such part")
                continue
            holds = (name in inside) == expect
            evidence.add(
                f"centroid {'lies in' if expect else 'lies outside'} part {name}",
                "symbolic",
                holds,
                f"centroid at (z, y) = ({as_float(zg):.6g}, {as_float(yg):.6g}); it lies in {', '.join(inside) or 'no part'}",
            )
    values = {
        "A": solution.area,
        "Iz": solution.Iz,
        "Iy": solution.Iy,
        "Iyz": solution.Iyz,
        "I1": solution.I1,
        "I2": solution.I2,
        "theta_deg": solution.theta * 180 / sympy.pi,
    }
    if solution.extremes:
        values["sigma_max"] = solution.extremes["max"][0]
        values["sigma_min"] = solution.extremes["min"][0]
    for key, actual in values.items():
        if key in claims:
            evidence.add(*compare(f"claimed {key}", claims[key], actual, {}))
    return evidence


def section_data(solution: SectionSolution, decimals: int = 6) -> dict[str, object]:
    def number(value: sympy.Expr) -> dict[str, object]:
        data: dict[str, object] = {"exact": str(value)}
        data["decimal"] = round(as_float(value), decimals)
        return data

    zg, yg = solution.centroid
    data: dict[str, object] = {
        "area": number(solution.area),
        "centroid": {"z": number(zg), "y": number(yg)},
        "centroid_lies_in": parts_containing(solution, (zg, yg)),
        "Iz": number(solution.Iz),
        "Iy": number(solution.Iy),
        "Iyz": number(solution.Iyz),
        "I1": number(solution.I1),
        "I2": number(solution.I2),
        "theta_deg": number(solution.theta * 180 / sympy.pi),
        "units": {"length": solution.model.units["length"], "stress": f"{solution.model.units['force']}/{solution.model.units['length']}^2"},
        "axes": {"y": solution.model.convention.get("section_y_axis"), "origin": "the coordinates of the data"},
        "convention": solution.model.convention.as_dict(),
    }
    if solution.stress is not None:
        data["stress"] = str(solution.stress)
        data["stress_note"] = "sigma(z, y) with z, y measured from the centroid; Mz = int sigma y dA, My = int sigma z dA"
        data["extremes"] = {
            kind: {"value": number(value), "at": {"z": number(point[0]), "y": number(point[1])}}
            for kind, (value, point) in solution.extremes.items()
        }
    return data
