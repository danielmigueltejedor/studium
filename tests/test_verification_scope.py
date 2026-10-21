"""A check can only support its declared relation and conditional scope."""

from test_grounding import _book, _derivation, _excerpt

from studium.authoring.grounding import equation_evidence
from studium.mcp.server import dispatch


def _paragraph(session, excerpt, statement, **extra):
    return dispatch(
        "studium_paragraph_record",
        {"section": "presion", "text": f"La relación declarada es ${statement}$ en estas condiciones.", "excerpts": [excerpt], **extra},
        session=session,
    )


def test_unrelated_passing_check_does_not_verify_stored_final_equation(tmp_path):
    session, root = _book(tmp_path)
    excerpt = _excerpt(session, "La presión es fuerza por unidad de área.")
    derivation = _derivation(session, "p = F * A")
    checked = dispatch("studium_derivation_check", {"id": derivation, "symbolic": {"left": "x+x", "right": "2*x"}}, session=session)
    assert checked["verification_status"] == "SYMBOLICALLY_VERIFIED"  # the check itself passed
    recorded = _paragraph(session, excerpt, "p = F * A")
    equation = equation_evidence(root, recorded["paragraph"])[0]
    assert equation["status"] == "unsupported"
    assert equation["blocks_audit"] is True
    declared = _paragraph(session, excerpt, "p = F * A", math=[{"statement": "p = F * A", "kind": "derivation", "refs": [derivation]}])
    assert declared["status"] == "paragraph.math_ungrounded"


def test_unrelated_numeric_check_does_not_reproduce_final_equation(tmp_path):
    session, root = _book(tmp_path)
    excerpt = _excerpt(session, "La presión es fuerza por unidad de área.")
    derivation = _derivation(session, "p = F * A")
    dispatch("studium_derivation_check", {"id": derivation, "numeric": {"expression": "2+2", "values": {}, "claimed": 4}}, session=session)
    recorded = _paragraph(session, excerpt, "p = F * A")
    assert equation_evidence(root, recorded["paragraph"])[0]["status"] == "unsupported"


def test_unrelated_failed_check_does_not_disprove_final_equation(tmp_path):
    session, root = _book(tmp_path)
    excerpt = _excerpt(session, "La presión es fuerza por unidad de área.")
    derivation = _derivation(session, "p = F * A")
    dispatch("studium_derivation_check", {"id": derivation, "symbolic": {"left": "x+x", "right": "3*x"}}, session=session)
    recorded = _paragraph(session, excerpt, "p = F * A")
    assert equation_evidence(root, recorded["paragraph"])[0]["status"] == "unsupported"


def test_a_point_equation_check_is_reported_with_its_solution_premises(tmp_path):
    session, root = _book(tmp_path)
    excerpt = _excerpt(session, "La presión es fuerza por unidad de área.")
    result = dispatch("studium_math_verify", {"kind": "equation", "left": "p", "right": "F*A", "solution": {"p": "6", "F": "2", "A": "3"}}, session=session)
    assert result["verification_status"] == "SYMBOLICALLY_VERIFIED"
    recorded = _paragraph(session, excerpt, "p = F * A")
    equation = equation_evidence(root, recorded["paragraph"])[0]
    assert equation["status"] == "follows_from_stated_premises"
    assert equation["human_review"] == "required"
    assert equation["verification_scope"][0]["solution"] == {"p": "6", "F": "2", "A": "3"}


def test_conditional_equivalence_does_not_become_an_unrestricted_proof(tmp_path):
    session, root = _book(tmp_path)
    excerpt = _excerpt(session, "Se declara una variable real positiva.")
    result = dispatch("studium_math_verify", {"kind": "equivalence", "left": "sqrt(x**2)", "right": "x", "assumptions": {"x": ["positive"]}}, session=session)
    assert result["accepted"] is True
    recorded = _paragraph(session, excerpt, "sqrt(x**2) = x")
    equation = equation_evidence(root, recorded["paragraph"])[0]
    assert equation["status"] == "follows_from_stated_premises"
    assert equation["verification_scope"][0]["assumptions"] == {"x": ["positive"]}


def test_matched_numeric_check_is_retained_but_not_upgraded_by_unrelated_algebra(tmp_path):
    session, root = _book(tmp_path)
    excerpt = _excerpt(session, "La presión es fuerza por unidad de área.")
    derivation = _derivation(session, "p = F / A")
    dispatch("studium_derivation_check", {"id": derivation, "symbolic": {"left": "x+x", "right": "2*x"}, "numeric": {"expression": "F/A", "values": {"F": 100, "A": 2}, "claimed": 50}}, session=session)
    recorded = _paragraph(session, excerpt, r"p = \frac{F}{A}")
    assert equation_evidence(root, recorded["paragraph"])[0]["status"] == "numerically_reproduced"


def test_evaluating_only_output_variable_does_not_check_a_relation(tmp_path):
    session, root = _book(tmp_path)
    excerpt = _excerpt(session, "La presión es fuerza por unidad de área.")
    derivation = _derivation(session, "p = F / A")
    dispatch("studium_derivation_check", {"id": derivation, "numeric": {"expression": "p", "values": {"p": 50}, "claimed": 50}}, session=session)
    recorded = _paragraph(session, excerpt, "p = F / A")
    assert equation_evidence(root, recorded["paragraph"])[0]["status"] == "unsupported"


def test_zero_residual_checks_the_relation_at_the_declared_point(tmp_path):
    session, root = _book(tmp_path)
    excerpt = _excerpt(session, "La presión es fuerza por unidad de área.")
    derivation = _derivation(session, "p = F / A")
    dispatch("studium_derivation_check", {"id": derivation, "numeric": {"expression": "p-F/A", "values": {"p": 50, "F": 100, "A": 2}, "claimed": 0}}, session=session)
    recorded = _paragraph(session, excerpt, "p = F / A")
    assert equation_evidence(root, recorded["paragraph"])[0]["status"] == "numerically_reproduced"


def test_failed_scalar_check_does_not_become_unchecked_passing_chain(tmp_path):
    session, root = _book(tmp_path)
    excerpt = _excerpt(session, "La presión es fuerza por unidad de área.")
    derivation = _derivation(session, r"p = F / A, \qquad q = F / (2 A)")
    dispatch("studium_derivation_check", {"id": derivation, "numeric": {"expression": "F/A", "values": {"F": 100, "A": 2}, "claimed": 60}}, session=session)
    recorded = _paragraph(session, excerpt, "p = F / A")
    assert equation_evidence(root, recorded["paragraph"])[0]["status"] == "unsupported"
