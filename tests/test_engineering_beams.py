"""Beams from structured data: exact solutions, independent checks, and drawings that match them."""

import re

import pytest
import sympy

from studium.diagrams.evidence import summarize
from studium.diagrams.piecewise import DataError, Piece, Piecewise, X
from studium.diagrams.tikz import verify_representation
from studium.engineering.structures import beam_draw
from studium.engineering.structures.beam import (
    check_claims,
    extremes,
    laws_latex,
    parse_beam,
    solve_beam,
    verify_beam,
)
from studium.engineering.structures.convention import parse_convention

ULE = "ule-teoria-estructuras"


def _beam(**overrides):
    spec = {"length": 6, "convention": ULE, "supports": [], "loads": []}
    spec.update(overrides)
    return solve_beam(parse_beam(spec))


def _status(solution, claims=None):
    return verify_beam(solution, claims).summary()


def _simply_supported_point_load():
    return _beam(
        points={"A": 0, "C": 2, "B": 6},
        supports=[{"at": "A", "type": "pin"}, {"at": "B", "type": "roller"}],
        loads=[{"type": "point", "at": "C", "value": 12, "direction": "down"}],
    )


# --------------------------------------------------------------------- conventions


def test_course_convention_derives_its_own_differential_relations():
    relations = parse_convention(ULE).relations()
    assert (relations.shear_load, relations.moment_shear, relations.axial_load) == (1, 1, -1)
    flipped_shear = parse_convention({"base": ULE, "shear_positive": "left_face_down"}).relations()
    assert flipped_shear.shear_load == -1
    assert flipped_shear.moment_shear == -1
    both = parse_convention({"base": ULE, "shear_positive": "left_face_down", "moment_positive": "compresses_bottom"})
    assert both.relations().moment_shear == 1


@pytest.mark.parametrize(
    "value",
    [None, "made-up-preset", {"base": ULE, "shear_positive": "sideways"}, {"base": ULE, "colour": "red"}, {"shear_positive": "left_face_up"}],
)
def test_invalid_or_missing_sign_conventions_are_rejected(value):
    with pytest.raises(DataError):
        parse_convention(value)


def test_a_beam_without_a_declared_convention_is_rejected():
    with pytest.raises(DataError, match="convention"):
        parse_beam({"length": 4, "supports": [{"at": 0, "type": "fixed"}], "loads": []})


# --------------------------------------------------------------------- statics


def test_simply_supported_point_load_reactions_jump_and_peak():
    solution = _simply_supported_point_load()
    assert solution.reactions["R_A"] == 8 and solution.reactions["R_B"] == 4
    assert solution.V.jump(sympy.Integer(2)) == -12
    peak = extremes(solution.M)["max"]
    assert peak.x == 2 and peak.value == 16
    assert len(solution.M.pieces) == 2
    assert _status(solution)["status"] == "mathematically_verified"


def test_cantilever_with_uniform_load_hogs_at_the_wall():
    solution = _beam(
        length=3,
        supports=[{"at": 0, "type": "fixed", "name": "A"}],
        loads=[{"type": "distributed", "from": 0, "to": 3, "start": 4, "direction": "down"}],
    )
    assert solution.M.right(sympy.Integer(0)) == -18
    assert solution.V.right(sympy.Integer(0)) == 12
    assert solution.M.left(sympy.Integer(3)) == 0
    assert solution.reactions["M_A"] == 18


def test_triangular_load_peak_moment_is_where_shear_vanishes():
    solution = _beam(
        length=6,
        supports=[{"at": 0, "type": "pin", "name": "A"}, {"at": 6, "type": "roller", "name": "B"}],
        loads=[{"type": "distributed", "from": 0, "to": 6, "start": 0, "end": 9, "direction": "down"}],
    )
    assert solution.reactions["R_B"] == 18
    peak = extremes(solution.M)["max"]
    assert sympy.simplify(peak.x - 6 / sympy.sqrt(3)) == 0
    assert sympy.simplify(peak.value - 9 * 36 / (9 * sympy.sqrt(3))) == 0
    assert _status(solution)["status"] == "mathematically_verified"


def test_applied_couple_makes_a_moment_jump_and_no_shear_jump():
    solution = _beam(
        length=4,
        supports=[{"at": 0, "type": "pin", "name": "A"}, {"at": 4, "type": "roller", "name": "B"}],
        loads=[{"type": "couple", "at": 1, "value": 8, "sense": "cw"}],
    )
    # A clockwise couple on the left part adds to the sagging moment just to its right.
    assert solution.M.jump(sympy.Integer(1)) == 8
    assert solution.V.jump(sympy.Integer(1)) == 0
    assert _status(solution)["status"] == "mathematically_verified"


def test_internal_hinge_carries_no_moment():
    solution = _beam(
        length=7,
        points={"A": 0, "H": 3, "B": 5, "E": 7},
        supports=[{"at": "A", "type": "fixed"}, {"at": "B", "type": "roller"}],
        hinges=["H"],
        loads=[
            {"type": "distributed", "from": "A", "to": "E", "start": 2, "direction": "down"},
            {"type": "point", "at": "E", "value": 5, "direction": "down"},
        ],
    )
    assert solution.M.left(sympy.Integer(3)) == 0 and solution.M.right(sympy.Integer(3)) == 0
    summary = _status(solution)
    assert summary["status"] == "mathematically_verified"
    names = [check["name"] for check in verify_beam(solution).summary()["failed"]]
    assert names == []


def test_axial_load_gives_tension_positive_axial_force():
    solution = _beam(
        length=5,
        supports=[{"at": 0, "type": "pin", "name": "A"}, {"at": 5, "type": "roller", "name": "B"}],
        loads=[{"type": "point", "at": 5, "value": 30, "direction": "right"}],
    )
    assert solution.N.right(sympy.Integer(0)) == 30
    assert solution.reactions["H_A"] == -30


def test_symbolic_parameters_give_the_textbook_formula():
    q, length = sympy.symbols("q L", positive=True)
    solution = solve_beam(
        parse_beam(
            {
                "length": 4,
                "parameters": ["q"],
                "convention": ULE,
                "supports": [{"at": 0, "type": "pin", "name": "A"}, {"at": 4, "type": "roller", "name": "B"}],
                "loads": [{"type": "distributed", "from": 0, "to": 4, "start": "q", "direction": "down"}],
            }
        )
    )
    assert sympy.simplify(solution.reactions["R_A"] - 2 * q) == 0
    assert sympy.simplify(solution.M.right(sympy.Integer(2)) - 2 * q) == 0
    assert length not in solution.M.pieces[0].expr.free_symbols


# --------------------------------------------------------------------- determinacy


def test_mechanism_and_missing_stiffness_are_reported():
    with pytest.raises(DataError, match="mechanism"):
        _beam(supports=[{"at": 0, "type": "roller", "name": "A"}], loads=[{"type": "point", "at": 3, "value": 1, "direction": "down"}])
    with pytest.raises(DataError, match="indeterminate of degree 1"):
        _beam(
            supports=[{"at": 0, "type": "fixed", "name": "A"}, {"at": 6, "type": "roller", "name": "B"}],
            loads=[{"type": "distributed", "from": 0, "to": 6, "start": 2, "direction": "down"}],
        )


def test_propped_cantilever_uses_compatibility_when_stiffness_is_given():
    solution = _beam(
        EI=1000,
        supports=[{"at": 0, "type": "fixed", "name": "A"}, {"at": 6, "type": "roller", "name": "B"}],
        loads=[{"type": "distributed", "from": 0, "to": 6, "start": 2, "direction": "down"}],
    )
    assert solution.degree == 1
    assert solution.reactions["R_B"] == sympy.Rational(3, 8) * 2 * 6
    assert _status(solution)["status"] == "mathematically_verified"


def test_simply_supported_deflection_matches_five_over_384():
    solution = _beam(
        length=4,
        EI=500,
        supports=[{"at": 0, "type": "pin", "name": "A"}, {"at": 4, "type": "roller", "name": "B"}],
        loads=[{"type": "distributed", "from": 0, "to": 4, "start": 3, "direction": "down"}],
    )
    assert solution.v is not None
    assert solution.v.right(sympy.Integer(2)) == -sympy.Rational(5, 384) * 3 * 4**4 / 500
    assert _status(solution)["status"] == "mathematically_verified"


# --------------------------------------------------------------------- claims


def test_claims_agree_only_within_their_written_precision():
    solution = _beam(
        length=3,
        supports=[{"at": 0, "type": "pin", "name": "A"}, {"at": 3, "type": "roller", "name": "B"}],
        loads=[{"type": "point", "at": 1, "value": 10, "direction": "down"}],
    )
    good = {"reactions": {"R_A": "6.67", "R_B": "10/3"}, "extrema": [{"function": "M", "kind": "max", "value": "6.67", "at": 1}]}
    assert summarize([c.as_dict() for c in check_claims(solution, good).checks])["failed"] == []
    bad = {"reactions": {"R_A": "6.5"}}
    assert check_claims(solution, bad).failed
    wrong_law = {"pieces": [{"function": "V", "from": 0, "to": 1, "expr": "-20/3"}]}
    assert check_claims(solution, wrong_law).failed
    right_law = {"pieces": [{"function": "M", "from": 1, "to": 3, "expr": "-10*x/3 + 10"}]}
    assert not check_claims(solution, right_law).failed


def test_a_wrong_claim_makes_the_whole_verification_fail():
    solution = _simply_supported_point_load()
    summary = verify_beam(solution, {"reactions": {"R_A": 4}}).summary()
    assert summary["status"] == "verification_failed"


# --------------------------------------------------------------------- drawings


def _hinge_beam():
    return _beam(
        length=8,
        EI=20000,
        points={"A": 0, "B": 2, "C": 6, "D": 8},
        supports=[{"at": "A", "type": "fixed"}, {"at": "C", "type": "roller"}],
        hinges=["B"],
        loads=[
            {"type": "distributed", "from": "A", "to": "D", "start": 12, "end": 4, "direction": "up"},
            {"type": "point", "at": 4, "value": 10, "direction": "down"},
            {"type": "couple", "at": 5, "value": 8, "sense": "cw"},
            {"type": "point", "at": "D", "value": 6, "direction": "down"},
        ],
    )


def test_internal_force_diagrams_match_the_functions_and_the_convention():
    solution = _hinge_beam()
    tikz, curves, signs = beam_draw.internal_forces_figure(solution)
    assert signs == {"V": 1, "M": -1}
    evidence = verify_representation(tikz, curves, signs)
    assert evidence.failed == []
    assert "% studium:label M" in tikz


def test_a_flipped_moment_diagram_is_rejected():
    solution = _hinge_beam()
    tikz, curves, signs = beam_draw.internal_forces_figure(solution)
    flipped = tikz.replace("sign=-1", "sign=1")
    assert any("side the convention declares" in check.name for check in verify_representation(flipped, curves, signs).failed)


def test_a_moved_curve_point_is_rejected():
    solution = _hinge_beam()
    tikz, curves, signs = beam_draw.internal_forces_figure(solution)
    lines = tikz.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("% studium:series M"))
    target = start + 1
    lines[target] = re.sub(r"\((-?[0-9.]+),(-?[0-9.]+)\)", lambda m: f"({m.group(1)},{float(m.group(2)) + 0.3:.4f})", lines[target], count=1)
    failed = verify_representation("\n".join(lines), curves, signs).failed
    assert any("lies on the stored function" in check.name for check in failed)


def test_a_wrong_printed_value_is_rejected():
    solution = _hinge_beam()
    tikz, curves, signs = beam_draw.internal_forces_figure(solution)
    label = next(line for line in tikz.splitlines() if line.startswith("% studium:label M"))
    tampered = tikz.replace(label, re.sub(r"value=\S+", "value=123.45", label))
    assert verify_representation(tampered, curves, signs).failed


def test_a_plausible_but_wrong_diagram_is_rejected():
    """A curve with the right shape and the wrong values (a sign slip in the reaction) fails."""

    solution = _simply_supported_point_load()
    wrong = Piecewise("M", (Piece(sympy.Integer(0), sympy.Integer(2), 4 * X), Piece(sympy.Integer(2), sympy.Integer(6), 8 - 0 * X)))
    tikz, _, signs = beam_draw.internal_forces_figure(solve_beam(parse_beam({
        "length": 6, "convention": ULE,
        "supports": [{"at": 0, "type": "pin", "name": "A"}, {"at": 6, "type": "roller", "name": "B"}],
        "loads": [{"type": "point", "at": 2, "value": 6, "direction": "down"}],
    })))
    evidence = verify_representation(tikz, {"M": solution.M}, signs)
    assert evidence.failed
    assert wrong.pieces[0].expr != solution.M.pieces[0].expr


def test_geometry_trace_catches_a_misplaced_load():
    solution = _hinge_beam()
    model = solution.model
    style = beam_draw.Style()
    tikz = beam_draw.problem_figure(model, style)
    assert beam_draw.verify_geometry(tikz, model, style).failed == []
    lines = tikz.splitlines()
    index = next(i for i, line in enumerate(lines) if line.startswith("% studium:at force 0"))
    lines[index + 1] = lines[index + 1].replace("(6.0000,", "(6.5000,")
    assert beam_draw.verify_geometry("\n".join(lines), model, style).failed


def test_free_body_reactions_print_the_solved_values():
    solution = _hinge_beam()
    tikz = beam_draw.free_body_figure(solution.model, solution)
    assert beam_draw.verify_reaction_labels(tikz, solution).failed == []
    tampered = re.sub(r"% studium:reaction R_C value=\S+", "% studium:reaction R_C value=99", tikz)
    assert beam_draw.verify_reaction_labels(tampered, solution).failed


def test_deflection_figure_matches_the_elastic_line():
    solution = _hinge_beam()
    tikz, curves, signs = beam_draw.deflection_figure(solution)
    assert verify_representation(tikz, curves, signs).failed == []


def test_laws_are_typeset_per_interval_with_decimal_comma():
    blocks = laws_latex(_simply_supported_point_load(), comma=True)
    assert blocks[0].startswith("V(x) = \\begin{cases}")
    assert "0 < x < 2" in blocks[0] and "2 < x < 6" in blocks[0]
    assert blocks[1].startswith("M(x)")


def test_scaling_check_is_reported_as_dimensional():
    evidence = verify_beam(_simply_supported_point_load())
    dimensional = [check for check in evidence.checks if check.category == "dimensional"]
    assert dimensional and all(check.passed for check in dimensional)


def test_alternative_convention_keeps_values_and_flips_only_the_plot():
    spec = {
        "length": 6,
        "points": {"A": 0, "C": 2, "B": 6},
        "supports": [{"at": "A", "type": "pin"}, {"at": "B", "type": "roller"}],
        "loads": [{"type": "point", "at": "C", "value": 12, "direction": "down"}],
    }
    course = solve_beam(parse_beam({**spec, "convention": ULE}))
    other = solve_beam(parse_beam({**spec, "convention": "sagging-positive-up"}))
    assert course.M.right(sympy.Integer(2)) == other.M.right(sympy.Integer(2))
    assert course.model.convention.plot_sign("M") == -1
    assert other.model.convention.plot_sign("M") == 1
