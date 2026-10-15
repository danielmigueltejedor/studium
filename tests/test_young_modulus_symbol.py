"""Capital E is Young's modulus in a structures book: a check on a formula with E must not read it as 2.718."""

from studium.mcp.server import dispatch, open_workspace


def _derivation(tmp_path, equation, symbolic):
    session = open_workspace(str(tmp_path))
    assert dispatch("studium_project_create", {"slug": "g", "topic": "Estructuras", "language": "es"}, session=session)["status"] == "created"
    assert dispatch("studium_blueprint_store", {"sections": [{"id": "t", "title": "Tensión"}]}, session=session)["status"] == "recorded"
    recorded = dispatch(
        "studium_derivation_record", {"section": "t", "name": "Hooke", "equation": equation, "symbolic": symbolic}, session=session
    )
    assert recorded["status"] == "recorded", recorded
    return session, str(recorded["derivation"]["id"])


def test_young_modulus_can_be_the_solved_symbol(tmp_path):
    session, identifier = _derivation(tmp_path, r"\sigma = E\,\varepsilon", "sigma - E*epsilon")
    checked = dispatch(
        "studium_derivation_check",
        {"id": identifier, "symbolic": {"equation_left": "E*epsilon", "equation_right": "sigma", "solution": {"E": "sigma/epsilon"}}},
        session=session,
    )
    assert checked["verification_status"] in {"SYMBOLICALLY_VERIFIED", "INDEPENDENTLY_VERIFIED"}, checked


def test_a_wrong_relation_with_e_is_not_vacuously_verified(tmp_path):
    session, identifier = _derivation(tmp_path, r"m = 2\,\rho\,k\,L^{2}/E", "m - 2*rho*k*L**2/E")
    checked = dispatch(
        "studium_derivation_check",
        {"id": identifier, "symbolic": {"equation_left": "rho*A*L", "equation_right": "m", "solution": {"A": "k*L/E", "m": "2*rho*k*L**2/E"}}},
        session=session,
    )
    assert checked["verification_status"] == "FAILED", checked


def test_pi_needs_no_declared_dimension(tmp_path):
    session, identifier = _derivation(tmp_path, r"I_{z} = \frac{\pi\,d^{4}}{64}", "I_z - pi*d**4/64")
    checked = dispatch(
        "studium_derivation_check",
        {
            "id": identifier,
            "dimensions": {"expression": "pi*d**4/64", "symbol_units": {"d": "m"}, "expected_unit": "m^4"},
        },
        session=session,
    )
    assert checked["verification_status"] == "DIMENSIONALLY_VERIFIED", checked
