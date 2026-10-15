"""Cross-sections, thin-walled sections, stress states and the unit-load method from structured data."""

import re

import pytest
import sympy

from studium.diagrams.piecewise import DataError, as_float
from studium.diagrams.registry import Options, catalogue, generator, solve_structure
from studium.engineering.structures import section_draw, stress, thinwall_draw
from studium.engineering.structures.section import parse_section, solve_section, verify_section
from studium.engineering.structures.thinwall import parse_thin_wall, solve_thin_wall, verify_thin_wall

ULE = "ule-teoria-estructuras"
T_SECTION = {
    "parts": [{"name": "ala", "z": [0, 120], "y": [0, 20]}, {"name": "alma", "z": [50, 70], "y": [20, 120]}],
    "convention": ULE,
}


def _section(spec):
    return solve_section(parse_section(spec))


# --------------------------------------------------------------------- sections


def test_t_section_centroid_and_inertia_are_exact():
    solution = _section(T_SECTION)
    assert solution.centroid == (60, sympy.Rational(410, 11))
    assert solution.Iz == sympy.Rational(187240000, 33)
    assert verify_section(solution).failed == []


def test_t_section_centroid_is_in_the_web_not_the_flange():
    """Regression: book 1 computed y_G = 37.27 mm correctly but said it lay in the 20 mm flange."""

    solution = _section(T_SECTION)
    wrong = verify_section(solution, {"centroid_in": "ala"})
    assert [check.name for check in wrong.failed] == ["centroid lies in part ala"]
    assert "it lies in alma" in wrong.failed[0].detail
    right = verify_section(solution, {"centroid_in": "alma", "centroid_not_in": "ala", "centroid": {"y": "37.27"}})
    assert right.failed == []


def test_problem_with_the_wrong_geometric_interpretation_is_rejected():
    result = solve_structure("section", T_SECTION, {"centroid_in": "ala"})
    assert result["verification"]["status"] == "verification_failed"
    assert result["data"]["centroid_lies_in"] == ["alma"]


def test_unsymmetric_section_keeps_exact_rational_products():
    """Regression: an inexact simplification once replaced a rational inertia by a surd."""

    z_like = {
        "parts": [
            {"name": "ala sup", "z": [0, 80], "y": [0, 10]},
            {"name": "alma", "z": [0, 10], "y": [10, 110]},
            {"name": "ala inf", "z": [0, 60], "y": [110, 120]},
        ],
        "convention": ULE,
        "loads": {"Mz": "5e6", "My": "1e6"},
    }
    solution = _section(z_like)
    assert solution.Iy.is_Rational and solution.Iz.is_Rational and solution.Iyz.is_Rational
    assert solution.Iyz != 0
    assert verify_section(solution).failed == []


def test_hollow_section_with_axial_force_and_bending():
    box = {
        "parts": [{"name": "ext", "z": [0, 100], "y": [0, 60]}, {"name": "hueco", "z": [10, 90], "y": [10, 50], "hole": True}],
        "convention": ULE,
        "loads": {"N": "-20000", "Mz": "3e6"},
    }
    solution = _section(box)
    assert solution.area == 6000 - 3200
    assert verify_section(solution).failed == []


def test_bad_section_data_is_rejected():
    with pytest.raises(DataError):
        parse_section({"parts": [{"name": "a", "z": [0, 0], "y": [0, 1]}], "convention": ULE})
    with pytest.raises(DataError):
        parse_section({"parts": [{"name": "a", "z": [0, 1], "y": [0, 1]}]})


def test_section_drawings_match_the_data():
    solution = _section({**T_SECTION, "loads": {"Mz": "10e6"}})
    for figure in (section_draw.properties_figure(solution), section_draw.stress_figure(solution)):
        assert section_draw.verify_section_drawing(figure, solution).failed == []
    tampered = section_draw.stress_figure(solution).replace("% studium:zone tension", "% studium:zone compression", 1)
    assert section_draw.verify_section_drawing(tampered, solution).failed


# --------------------------------------------------------------------- thin walls


CHANNEL = {
    "nodes": {"A": [50, 0], "B": [0, 0], "C": [0, 100], "D": [50, 100]},
    "walls": [{"from": "A", "to": "B", "t": 2}, {"from": "B", "to": "C", "t": 2}, {"from": "C", "to": "D", "t": 2}],
    "shear": {"Vy": 1000, "at": "shear_centre"},
    "convention": ULE,
}


def test_channel_shear_centre_matches_the_closed_form():
    solution = solve_thin_wall(parse_thin_wall(CHANNEL))
    b, h = 50, 100
    assert solution.shear_centre[0] == -sympy.Rational(3 * b**2, h + 6 * b)
    assert solution.shear_centre[1] == 50
    assert verify_thin_wall(solution).failed == []


def test_single_cell_torsion_is_bredt():
    box = {
        "nodes": {"A": [0, 0], "B": [200, 0], "C": [200, 100], "D": [0, 100]},
        "walls": [{"from": "A", "to": "B", "t": 2}, {"from": "B", "to": "C", "t": 2}, {"from": "C", "to": "D", "t": 2}, {"from": "D", "to": "A", "t": 2}],
        "cells": [["A", "B", "C", "D"]],
        "torque": 40000,
        "G": 27000,
        "convention": ULE,
    }
    solution = solve_thin_wall(parse_thin_wall(box))
    assert solution.cell_flows == [1]
    assert solution.twist_rate == sympy.Rational(1, 40000) * 300 / 27000
    assert verify_thin_wall(solution).failed == []


def test_two_cell_torsion_balances_the_torque_and_twists_equally():
    spec = {
        "nodes": {"A": [0, 0], "B": [200, 0], "C": [500, 0], "D": [500, 200], "E": [200, 200], "F": [0, 200]},
        "walls": [
            {"from": "A", "to": "B", "t": 2}, {"from": "B", "to": "C", "t": 2}, {"from": "C", "to": "D", "t": 2},
            {"from": "D", "to": "E", "t": 2}, {"from": "E", "to": "F", "t": 2}, {"from": "F", "to": "A", "t": 2},
            {"from": "B", "to": "E", "t": 3},
        ],
        "cells": [["A", "B", "E", "F"], ["B", "C", "D", "E"]],
        "torque": 1000000,
        "convention": ULE,
    }
    solution = solve_thin_wall(parse_thin_wall(spec))
    q1, q2 = solution.cell_flows
    assert 2 * 40000 * q1 + 2 * 60000 * q2 == 1000000
    assert verify_thin_wall(solution).failed == []


def test_idealised_box_carries_shear_in_the_webs():
    spec = {
        "nodes": {"A": [0, 0], "B": [300, 0], "C": [300, 200], "D": [0, 200]},
        "walls": [{"from": "A", "to": "B", "t": 1}, {"from": "B", "to": "C", "t": 1}, {"from": "C", "to": "D", "t": 1}, {"from": "D", "to": "A", "t": 1}],
        "cells": [["A", "B", "C", "D"]],
        "booms": [{"at": node, "area": 400} for node in "ABCD"],
        "direct_stress_walls": False,
        "shear": {"Vy": 10000, "at": "shear_centre"},
        "convention": ULE,
    }
    solution = solve_thin_wall(parse_thin_wall(spec))
    assert abs(solution.flows["BC"]) == 25 and solution.flows["AB"] == 0
    assert verify_thin_wall(solution).failed == []


def test_open_section_with_off_centre_shear_reports_st_venant_torque():
    spec = {**CHANNEL, "shear": {"Vy": 1000, "at": [0, 50]}}
    solution = solve_thin_wall(parse_thin_wall(spec))
    assert solution.open_torque == 1000 * sympy.Rational(-75, 4)
    assert verify_thin_wall(solution).failed == []


def test_cells_must_be_declared():
    spec = {
        "nodes": {"A": [0, 0], "B": [1, 0], "C": [1, 1]},
        "walls": [{"from": "A", "to": "B", "t": 1}, {"from": "B", "to": "C", "t": 1}, {"from": "C", "to": "A", "t": 1}],
        "convention": ULE,
    }
    with pytest.raises(DataError, match="cells"):
        parse_thin_wall(spec)


def test_shear_flow_drawing_follows_the_flows_and_rejects_a_wrong_label():
    solution = solve_thin_wall(parse_thin_wall(CHANNEL))
    figure = thinwall_draw.flow_figure(solution)
    assert thinwall_draw.verify_flow_drawing(figure, solution).failed == []
    label = next(line for line in figure.splitlines() if line.startswith("% studium:qlabel"))
    tampered = figure.replace(label, re.sub(r"value=\S+", "value=99.99", label))
    assert thinwall_draw.verify_flow_drawing(tampered, solution).failed


# --------------------------------------------------------------------- stress states


def test_plane_stress_principal_values_and_yield():
    result = solve_structure(
        "stress_state",
        {"sigma_x": 90, "sigma_y": 30, "tau_xy": 70, "yield": 250, "convention": ULE},
        {"sigma_1": "136.16", "yields": False},
    )
    assert result["verification"]["status"] == "mathematically_verified"
    assert result["data"]["yields_von_mises"] is False
    wrong = solve_structure("stress_state", {"sigma_x": 90, "sigma_y": 30, "tau_xy": 70, "convention": ULE}, {"sigma_2": "16.16"})
    assert wrong["verification"]["status"] == "verification_failed"


def test_mohr_circle_drawing_uses_the_declared_convention():
    solution = stress.solve_stress(stress.parse_stress({"sigma_x": 90, "sigma_y": 30, "tau_xy": 70, "convention": ULE}))
    figure = stress.mohr_figure(solution)
    assert stress.verify_mohr_drawing(figure, solution).failed == []
    flipped = figure.replace("tau=-70.0", "tau=70.0", 1)
    assert stress.verify_mohr_drawing(flipped, solution).failed


def test_rotated_element_keeps_the_invariants():
    solution = stress.solve_stress(stress.parse_stress({"sigma_x": -40, "sigma_y": 80, "tau_xy": -35, "rotation_deg": 30, "convention": ULE}))
    assert stress.verify_stress(solution).failed == []
    sxr, syr, _ = solution.rotated
    assert sympy.simplify(sxr + syr - 40) == 0


# --------------------------------------------------------------------- unit-load method


def test_unit_load_deflection_equals_the_elastic_line():
    spec = {
        "length": 4,
        "EI": 500,
        "supports": [{"at": 0, "type": "pin", "name": "A"}, {"at": 4, "type": "roller", "name": "B"}],
        "loads": [{"type": "distributed", "from": 0, "to": 4, "start": 3, "direction": "down"}],
        "convention": ULE,
    }
    built = generator("beam.virtual_work").build(spec, {"virtual": {"type": "point", "at": 2, "direction": "down"}}, Options(), None)
    assert built.evidence.summary()["status"] == "mathematically_verified"
    assert built.data["virtual_work"]["value"]["exact"] == "1/50"
    rotation = generator("beam.virtual_work").build(spec, {"virtual": {"type": "couple", "at": 0, "sense": "cw"}}, Options(), {"displacement": "0.015"})
    assert rotation.evidence.summary()["status"] == "verification_failed"


def test_catalogue_lists_every_family():
    families = catalogue()["families"]
    assert {"beam", "section", "thin_wall", "stress_state"} <= set(families)
    assert as_float(sympy.Integer(1)) == 1.0
