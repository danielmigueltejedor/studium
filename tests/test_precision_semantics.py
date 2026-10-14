"""Precision of claimed and replayed numbers (PR #42 review).

A claimed number is compared at the precision it is *written* with. That
representation must survive recording, storage and replay, the replayed value
must not be rounded before the comparison, and a claim whose precision cannot
be read from how it is written is reported as ambiguous instead of guessed.
"""

import json
from fractions import Fraction

import pytest

from studium.authoring.computation import ComputationError, agrees, evaluate_number, precision_verdict
from studium.mcp.server import dispatch, open_workspace
from studium.storage.records import COMPUTATIONS


def _book(tmp_path):
    session = open_workspace(str(tmp_path))
    created = dispatch(
        "studium_project_create",
        {"slug": "fluidos", "topic": "Mecánica de fluidos", "language": "es", "profile": "STEM"},
        session=session,
    )
    assert created["status"] == "created", created
    session = open_workspace(str(tmp_path), str(tmp_path / "fluidos"))
    dispatch("studium_blueprint_store", {"sections": [{"id": "s1", "title": "Sección"}]}, session=session)
    return session, tmp_path / "fluidos"


# --- Priority 1: the written claim survives recording, storage and replay -----------------


def test_trailing_zero_in_a_claimed_string_is_kept_by_computation_check(tmp_path):
    session, _root = _book(tmp_path)
    checked = dispatch(
        "studium_computation_check",
        {"section": "s1", "expression": "31.26 * 1", "result": "31.30"},
        session=session,
    )
    assert checked["status"] == "mismatch", checked
    assert checked["computation"]["claimed_text"] == "31.30"


def test_the_written_claim_is_reused_on_replay(tmp_path):
    session, _root = _book(tmp_path)
    first = dispatch(
        "studium_computation_check",
        {"section": "s1", "expression": "sqrt(2*600/1.225)", "result": "31.30"},
        session=session,
    )
    assert first["status"] == "replayed", first
    again = dispatch("studium_computation_check", {"id": first["computation"]["id"]}, session=session)
    assert again["status"] == "replayed", again
    assert again["computation"]["claimed_text"] == "31.30"


def test_a_legacy_record_without_the_written_claim_is_compared_exactly(tmp_path):
    session, root = _book(tmp_path)
    first = dispatch(
        "studium_computation_check",
        {"section": "s1", "expression": "sqrt(2*600/1.225)", "result": "31.30"},
        session=session,
    )
    path = root / COMPUTATIONS
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    for row in rows:
        row.pop("claimed_text", None)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    again = dispatch("studium_computation_check", {"id": first["computation"]["id"]}, session=session)
    # 313/10 does not say how many digits were written, so no rounding is inferred from it.
    assert again["status"] == "mismatch", again


def test_a_fraction_is_never_given_an_inferred_precision():
    assert not agrees(Fraction(313, 10), Fraction(3126, 100))
    assert agrees(Fraction(313, 10), Fraction(313, 10))


# --- Priority 2: the comparison uses the full replayed value ------------------------------


def _problem(session, final_expression, expected):
    excerpts = []
    for index in range(2):
        url = f"https://open.example/p{index}"
        source = dispatch("studium_public_source_record", {"title": f"Fuente {index}", "url": url}, session=session)
        excerpt = dispatch(
            "studium_excerpt_record",
            {"source_id": source["candidate"]["id"], "url": url, "text": f"Texto de la fuente {index} sobre el problema."},
            session=session,
        )
        excerpts.append(excerpt["excerpt"]["id"])
    recorded = dispatch(
        "studium_problem_record",
        {
            "section": "s1",
            "role": "worked",
            "prompt": "Calcule el valor.",
            "expected": expected,
            "excerpts": excerpts,
            "solution": {"steps": [{"text": "Resultado", "expression": final_expression, "expected": expected}]},
        },
        session=session,
    )
    assert recorded["status"] == "recorded", recorded
    return dispatch("studium_problem_check", {"id": recorded["problem"]["id"]}, session=session)


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("1 + 49/10000000", "1.000005"),  # 1.0000049 prints as 1.00000 at six significant figures
        ("1.2*250*5/1.8e-5", "83333333.3"),  # 83333333.33 prints as 8.33333e+07
    ],
)
def test_answer_check_uses_the_unrounded_replayed_value(tmp_path, expression, expected):
    session, _root = _book(tmp_path)
    checked = _problem(session, expression, expected)
    assert checked["step_checks"][-1]["reproduced"] is True, checked["step_checks"]
    assert checked["answer_check"]["result"] == "replayed", checked["answer_check"]


# --- Priority 3: trailing zeros of an integer are ambiguous, not silently placeholders ---


@pytest.mark.parametrize(
    ("claimed", "actual", "verdict"),
    [
        ("3924", Fraction(3924), "agrees"),
        ("3920", Fraction(3924), "ambiguous"),
        ("30", Fraction(313, 10), "ambiguous"),
        ("30", Fraction(36), "disagrees"),
        ("83300000", Fraction(833333333, 10), "ambiguous"),
        ("8.33e7", Fraction(833333333, 10), "agrees"),
        ("83300000", Fraction(83300000), "agrees"),
        ("83300000", Fraction(90000000), "disagrees"),
        ("31.30", Fraction(3126, 100), "disagrees"),
        ("31.30", Fraction(312984, 10000), "agrees"),
    ],
)
def test_precision_verdict(claimed, actual, verdict):
    assert precision_verdict(claimed, actual) == verdict
    assert agrees(claimed, actual) is (verdict == "agrees")


def test_an_ambiguous_answer_is_reported_as_such(tmp_path):
    session, _root = _book(tmp_path)
    checked = _problem(session, "1.2*250*5/1.8e-5", "83300000")
    assert checked["answer_check"]["result"] == "ambiguous_precision", checked["answer_check"]
    assert "8.33e7" in checked["answer_check"]["reason"] or "scientific" in checked["answer_check"]["reason"]


def test_an_ambiguous_computation_claim_is_not_accepted(tmp_path):
    session, _root = _book(tmp_path)
    checked = dispatch(
        "studium_computation_check",
        {"section": "s1", "expression": "1.2*250*5/1.8e-5", "result": "83300000"},
        session=session,
    )
    assert checked["status"] == "ambiguous_precision", checked
    assert checked["accepted"] is False


# --- Priority 4: documented evaluator bounds ---------------------------------------------


@pytest.mark.parametrize(
    "expression",
    [
        "6.022e23 * 2",  # Avogadro-scale constants are in range
        "6.626e-34 * 3e8",
        "2**64",  # an integer power above the old exponent limit stays exact
        "10**-30",
    ],
)
def test_physical_magnitudes_are_in_range(expression):
    evaluate_number(expression)


def test_integer_powers_stay_exact_within_the_limit():
    value, exact = evaluate_number("2**64")
    assert exact is True
    assert value == 2**64


@pytest.mark.parametrize(
    ("expression", "fragment"),
    [
        ("10**101", "magnitude"),
        ("1e400", "magnitude"),
        ("exp(1000)", "magnitude"),
        ("exp(-1000)", "underflow"),
        ("10**-101", "magnitude"),
        ("2**1001", "exponent"),
        ("sqrt(-1)", "domain"),
        ("log(0)", "domain"),
        ("asin(2)", "domain"),
        ("(-8)**(1/3)", "domain"),
        ("0**-1", "divides by zero"),
    ],
)
def test_out_of_range_input_is_refused_with_its_reason(expression, fragment):
    with pytest.raises(ComputationError) as raised:
        evaluate_number(expression)
    assert fragment in str(raised.value)


def test_public_record_gives_readable_value_for_huge_fraction():
    from studium.authoring.computation import _approximate

    assert _approximate("11723035734742750928125/140737488355328") == "83297178.8238"
    assert _approximate("6125/4") is None
    assert _approximate("42") is None
