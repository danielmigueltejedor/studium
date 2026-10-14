"""The replay engine covers the arithmetic of ordinary engineering problems.

Regression for an MCP evaluation run in which ``studium_problem_record`` rejected
a Pitot-tube worked problem (``sqrt(2*600/1.225)``) and a Torricelli exercise,
because the replay engine accepted only integer powers and no functions.
"""

import pytest

from studium.authoring.computation import ComputationError, agrees, evaluate_number
from studium.mcp.server import dispatch, open_workspace


@pytest.mark.parametrize(
    ("expression", "value"),
    [
        ("sqrt(2*600/1.225)", 31.29843),
        ("(2*600/1.225)**0.5", 31.29843),
        ("(2*600/1.225)**(1/2)", 31.29843),
        ("10**-5", 1e-5),
        ("2*pi*0.5", 3.14159),
        ("exp(-9.81*1000/(287*288.15))", 0.888143),
        ("log(2)", 0.693147),
        ("sin(pi/6)", 0.5),
        ("abs(-3.5)", 3.5),
    ],
)
def test_roots_powers_and_functions_replay(expression, value):
    actual, _exact = evaluate_number(expression)
    assert float(actual) == pytest.approx(value, rel=1e-5)


def test_integer_arithmetic_stays_exact():
    actual, exact = evaluate_number("13600*9.81*0.25 - 1000*9.81*0.40")
    assert exact is True
    assert str(actual) == "29430"


def test_an_inexact_result_matches_a_claim_to_its_stated_precision():
    actual, exact = evaluate_number("sqrt(2*600/1.225)")
    assert exact is False
    assert agrees("31.30", actual)
    assert agrees("31.3", actual)
    assert not agrees("31.4", actual)
    assert not agrees("30", actual)


def test_a_claim_is_read_as_rounded_to_its_last_written_digit():
    actual, _exact = evaluate_number("1000*9.81*0.40")
    assert agrees("3924", actual)
    assert not agrees("3920", actual)
    assert agrees("979.59", evaluate_number("2*600/1.225")[0])


@pytest.mark.parametrize(
    ("expression", "fragment"),
    [
        ("open('x')", "supported"),
        ("sqrt(-1)", "outside"),
        ("log(0)", "outside"),
        ("__import__('os')", "supported"),
        ("x + 1", "supported"),
    ],
)
def test_unsupported_input_gets_an_actionable_error(expression, fragment):
    with pytest.raises(ComputationError) as raised:
        evaluate_number(expression)
    assert fragment in str(raised.value)


def test_a_pitot_worked_problem_can_be_recorded_and_its_steps_replay(tmp_path):
    session = open_workspace(str(tmp_path))
    created = dispatch(
        "studium_project_create",
        {"slug": "fluidos", "topic": "Mecánica de fluidos", "language": "es", "profile": "STEM"},
        session=session,
    )
    assert created["status"] == "created", created
    session = open_workspace(str(tmp_path), str(tmp_path / "fluidos"))
    dispatch("studium_blueprint_store", {"sections": [{"id": "bernoulli", "title": "Bernoulli"}]}, session=session)
    excerpts = []
    for index, text in enumerate(
        (
            "Bernoulli's equation states that the static pressure plus one half the density times the velocity squared is equal to the total pressure.",
            "The static pressure plus the dynamic pressure is equal to a constant throughout the flow.",
        )
    ):
        url = f"https://open.example/pitot-{index}"
        source = dispatch("studium_public_source_record", {"title": f"Pitot {index}", "url": url}, session=session)
        excerpt = dispatch(
            "studium_excerpt_record",
            {"source_id": source["candidate"]["id"], "url": url, "text": text},
            session=session,
        )
        excerpts.append(excerpt["excerpt"]["id"])

    recorded = dispatch(
        "studium_problem_record",
        {
            "section": "bernoulli",
            "role": "worked",
            "prompt": "Un tubo de Pitot mide 600 Pa de presión dinámica en aire de 1,225 kg/m^3. Calcule la velocidad.",
            "expected": "31.30",
            "excerpts": excerpts,
            "solution": {
                "given": [{"symbol": "dp", "value": 600, "unit": "Pa"}, {"symbol": "rho", "value": 1.225, "unit": "kg/m^3"}],
                "model": [{"name": "Pitot", "latex": r"V = \sqrt{2\,\Delta p/\rho}", "symbolic": "sqrt(2*dp/rho)"}],
                "steps": [
                    {"text": "V al cuadrado", "expression": "2*600/1.225", "expected": 979.59, "unit": "m^2/s^2"},
                    {"text": "Velocidad", "expression": "sqrt(2*600/1.225)", "expected": 31.30, "unit": "m/s"},
                ],
                "result": r"V \approx 31{,}3\ \mathrm{m/s}",
            },
        },
        session=session,
    )
    assert recorded["status"] == "recorded", recorded
    checked = dispatch("studium_problem_check", {"id": recorded["problem"]["id"]}, session=session)
    assert checked["steps_reproduced"] is True, checked["step_checks"]


def test_trailing_zero_integer_is_ambiguous_not_a_match():
    # Reviewed in PR #42: trailing zeros of an integer are not assumed to be placeholders.
    from fractions import Fraction

    from studium.authoring.computation import agrees, precision_verdict

    assert not agrees("83300000", Fraction(833333333, 10))
    assert precision_verdict("83300000", Fraction(833333333, 10)) == "ambiguous"
    assert not agrees("83300000", Fraction(90000000))
    assert not agrees("3924", Fraction(3930))
    assert agrees("3924", Fraction(39241, 10))
