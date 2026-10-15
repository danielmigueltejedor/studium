"""Sign conventions for internal forces, declared, never assumed.

A convention says which way a positive internal force acts on each face of a
slice and which side of the axis its diagram is drawn on. The differential
relations and the method-of-sections formulas are *derived* here from the
declared directions by writing the equilibrium of a slice ``[x, x + dx]``
with SymPy, so a book that declares a different convention gets the
relations that belong to it.

Physical loads are always described by direction words (``up``, ``down``,
``left``, ``right``, ``ccw``, ``cw``), independent of the convention.
"""

from dataclasses import dataclass
from functools import cache

import sympy

from studium.diagrams.piecewise import DataError

_CHOICES: dict[str, tuple[str, ...]] = {
    "axial_positive": ("tension", "compression"),
    "shear_positive": ("left_face_up", "left_face_down"),
    "moment_positive": ("compresses_top", "compresses_bottom"),
    "axial_diagram_positive": ("up", "down"),
    "shear_diagram_positive": ("up", "down"),
    "moment_diagram_positive": ("up", "down"),
    "torsion_positive": ("ccw_on_viewed_face", "cw_on_viewed_face"),
    "section_y_axis": ("down", "up"),
    "mohr_plot": ("x_point_minus_tau", "x_point_plus_tau"),
}

_TEXT_ES = {
    ("axial_positive", "tension"): "axil positivo de tracción",
    ("axial_positive", "compression"): "axil positivo de compresión",
    ("shear_positive", "left_face_up"): "cortante positivo si levanta la cara izquierda de la rebanada",
    ("shear_positive", "left_face_down"): "cortante positivo si baja la cara izquierda de la rebanada",
    ("moment_positive", "compresses_top"): "flector positivo si comprime la fibra superior",
    ("moment_positive", "compresses_bottom"): "flector positivo si comprime la fibra inferior",
    ("moment_diagram_positive", "down"): "flectores positivos dibujados hacia abajo",
    ("moment_diagram_positive", "up"): "flectores positivos dibujados hacia arriba",
    ("shear_diagram_positive", "up"): "cortantes positivos dibujados hacia arriba",
    ("shear_diagram_positive", "down"): "cortantes positivos dibujados hacia abajo",
}

_TEXT_EN = {
    ("axial_positive", "tension"): "axial force positive in tension",
    ("axial_positive", "compression"): "axial force positive in compression",
    ("shear_positive", "left_face_up"): "shear positive when it lifts the left face of the slice",
    ("shear_positive", "left_face_down"): "shear positive when it pushes the left face of the slice down",
    ("moment_positive", "compresses_top"): "bending moment positive when it compresses the top fibre",
    ("moment_positive", "compresses_bottom"): "bending moment positive when it compresses the bottom fibre",
    ("moment_diagram_positive", "down"): "positive moments drawn below the axis",
    ("moment_diagram_positive", "up"): "positive moments drawn above the axis",
    ("shear_diagram_positive", "up"): "positive shear drawn above the axis",
    ("shear_diagram_positive", "down"): "positive shear drawn below the axis",
}

PRESETS: dict[str, dict[str, str]] = {
    # Universidad de León, Teoría de Estructuras (0710321): course slides and
    # lecturer's exam corrections. Moment diagrams are drawn positive downward.
    "ule-teoria-estructuras": {
        "axial_positive": "tension",
        "shear_positive": "left_face_up",
        "moment_positive": "compresses_top",
        "axial_diagram_positive": "up",
        "shear_diagram_positive": "up",
        "moment_diagram_positive": "down",
        "torsion_positive": "ccw_on_viewed_face",
        "section_y_axis": "down",
        "mohr_plot": "x_point_minus_tau",
    },
    # Sagging-positive convention with every diagram drawn positive upward.
    "sagging-positive-up": {
        "axial_positive": "tension",
        "shear_positive": "left_face_up",
        "moment_positive": "compresses_top",
        "axial_diagram_positive": "up",
        "shear_diagram_positive": "up",
        "moment_diagram_positive": "up",
        "torsion_positive": "ccw_on_viewed_face",
        "section_y_axis": "up",
        "mohr_plot": "x_point_minus_tau",
    },
}


@dataclass(frozen=True)
class Relations:
    """Coefficients derived from slice equilibrium.

    ``dV/dx = shear_load * q_up``, ``dM/dx = moment_shear * V``,
    ``dN/dx = axial_load * p_right``. Method of sections from the left part:
    ``V = left_shear * sum(Fy_up)``, ``M = left_moment * sum(ccw moments about the cut)``,
    ``N = left_axial * sum(Fx_right)``. From the right part the factors are
    ``right_*``.
    """

    shear_load: int
    moment_shear: int
    axial_load: int
    left_shear: int
    left_moment: int
    left_axial: int
    right_shear: int
    right_moment: int
    right_axial: int


@dataclass(frozen=True)
class Convention:
    name: str
    choices: tuple[tuple[str, str], ...]

    def get(self, key: str) -> str:
        return dict(self.choices)[key]

    @property
    def shear_sign(self) -> int:
        return 1 if self.get("shear_positive") == "left_face_up" else -1

    @property
    def moment_sign(self) -> int:
        return 1 if self.get("moment_positive") == "compresses_top" else -1

    @property
    def axial_sign(self) -> int:
        return 1 if self.get("axial_positive") == "tension" else -1

    def plot_sign(self, function: str) -> int:
        key = {"N": "axial_diagram_positive", "V": "shear_diagram_positive", "M": "moment_diagram_positive"}[function]
        return 1 if self.get(key) == "up" else -1

    def relations(self) -> Relations:
        return _derive(self.shear_sign, self.moment_sign, self.axial_sign)

    def as_dict(self) -> dict[str, object]:
        rel = self.relations()
        return {
            "name": self.name,
            **dict(self.choices),
            "derived": {
                "dV_dx": f"{_coef(rel.shear_load)}q_up",
                "dM_dx": f"{_coef(rel.moment_shear)}V",
                "d2M_dx2": f"{_coef(rel.shear_load * rel.moment_shear)}q_up",
                "dN_dx": f"{_coef(rel.axial_load)}p_right",
            },
        }

    def describe(self, language: str = "es") -> list[str]:
        table = _TEXT_ES if language.startswith("es") else _TEXT_EN
        keys = ("axial_positive", "shear_positive", "moment_positive", "shear_diagram_positive", "moment_diagram_positive")
        return [table[(key, self.get(key))] for key in keys if (key, self.get(key)) in table]


def _coef(value: int) -> str:
    return "" if value == 1 else "-"


def parse_convention(value: object) -> Convention:
    """A preset name, or a full mapping of every key. Unknown keys or values are rejected."""

    if value is None:
        raise DataError("a sign convention is required; give a preset name or every key")
    if isinstance(value, str):
        preset = PRESETS.get(value.strip())
        if preset is None:
            raise DataError(f"unknown sign convention preset {value!r}; known: {', '.join(sorted(PRESETS))}")
        return Convention(value.strip(), tuple(sorted(preset.items())))
    if not isinstance(value, dict):
        raise DataError("convention must be a preset name or a mapping")
    data = dict(value)
    name = data.pop("name", "custom")
    base_name = data.pop("base", None)
    merged: dict[str, str] = {}
    if base_name is not None:
        if not isinstance(base_name, str) or base_name not in PRESETS:
            raise DataError(f"unknown base convention {base_name!r}")
        merged.update(PRESETS[base_name])
    for key, choice in data.items():
        if key not in _CHOICES:
            raise DataError(f"unknown convention key {key!r}")
        if choice not in _CHOICES[key]:
            raise DataError(f"convention {key} must be one of {', '.join(_CHOICES[key])}")
        merged[str(key)] = str(choice)
    missing = [key for key in _CHOICES if key not in merged]
    if missing:
        raise DataError(f"convention is missing {', '.join(missing)}")
    return Convention(str(name), tuple(sorted(merged.items())))


@cache
def _derive(shear_sign: int, moment_sign: int, axial_sign: int) -> Relations:
    """Equilibrium of a slice ``[x, x + dx]`` and of the two parts of a cut beam.

    On the slice's left face (outward normal -x) a positive shear acts upward
    when ``shear_sign`` is 1; a positive moment that compresses the top fibre
    acts clockwise on that face. Faces with normal +x carry the opposite
    actions. Second-order terms in ``dx`` vanish in the limit.
    """

    s, m, a = sympy.Integer(shear_sign), sympy.Integer(moment_sign), sympy.Integer(axial_sign)
    v, dv, mm, dm, n, dn, q, p, dx = sympy.symbols("V dV M dM N dN q p dx")
    # Slice: forces upward, moments counter-clockwise about the left face.
    fy = s * v - s * (v + dv) + q * dx
    mz = -m * mm + m * (mm + dm) + dx * (-s * (v + dv)) + q * dx * dx / 2
    fx = -a * n + a * (n + dn) + p * dx
    dv_dx = sympy.limit(sympy.solve(fy, dv)[0] / dx, dx, 0)
    dm_dx = sympy.limit(sympy.solve(mz.subs(dv, 0), dm)[0] / dx, dx, 0)
    dn_dx = sympy.limit(sympy.solve(fx, dn)[0] / dx, dx, 0)
    shear_load = sympy.simplify(dv_dx / q)
    moment_shear = sympy.simplify(dm_dx / v)
    axial_load = sympy.simplify(dn_dx / p)
    # Left part: its cut face has normal +x and carries -s V, +m M, +a N.
    fy_left, ccw_left, fx_left = sympy.symbols("Fy_left C_left Fx_left")
    left_v = sympy.solve(fy_left - s * v, v)[0] / fy_left
    left_m = sympy.solve(ccw_left + m * mm, mm)[0] / ccw_left
    left_n = sympy.solve(fx_left + a * n, n)[0] / fx_left
    # Right part: its cut face has normal -x and carries +s V, -m M, -a N.
    fy_right, ccw_right, fx_right = sympy.symbols("Fy_right C_right Fx_right")
    right_v = sympy.solve(fy_right + s * v, v)[0] / fy_right
    right_m = sympy.solve(ccw_right - m * mm, mm)[0] / ccw_right
    right_n = sympy.solve(fx_right - a * n, n)[0] / fx_right
    values = [shear_load, moment_shear, axial_load, left_v, left_m, left_n, right_v, right_m, right_n]
    return Relations(*(int(sympy.simplify(value)) for value in values))
