"""A derivation check must be about the stored derivation.

Regression for a verification bypass found in an MCP evaluation run: the
checks a client passed to ``studium_derivation_check`` were never related to
the stored equation, so ``a + b = b + a`` plus "p is in pascals" made a wrong
Bernoulli equation INDEPENDENTLY_VERIFIED, and that status then grounded prose.
"""

from studium.mcp.server import dispatch, open_workspace

_TOPIC = {"slug": "fluidos", "topic": "Mecánica de fluidos", "language": "es", "profile": "STEM"}


def _project(tmp_path):
    session = open_workspace(str(tmp_path))
    created = dispatch("studium_project_create", _TOPIC, session=session)
    assert created["status"] == "created", created
    session = open_workspace(str(tmp_path), str(tmp_path / "fluidos"))
    stored = dispatch(
        "studium_blueprint_store",
        {"sections": [{"id": "bernoulli", "title": "Ecuación de Bernoulli"}]},
        session=session,
    )
    assert stored["status"] == "recorded", stored
    return session


def _excerpt(session):
    url = "https://open.example/bernoulli"
    text = "The static pressure plus one half of the density times the velocity squared is the total pressure."
    record = dispatch("studium_public_source_record", {"title": "Bernoulli", "url": url, "text": text}, session=session)
    assert record["status"] == "recorded", record
    excerpt = dispatch(
        "studium_excerpt_record",
        {"source_id": record["candidate"]["id"], "url": url, "text": text},
        session=session,
    )
    assert excerpt["status"] == "recorded", excerpt
    return str(excerpt["excerpt"]["id"])


def _record(session, equation, symbolic=None, variables=None):
    arguments: dict[str, object] = {"section": "bernoulli", "name": "Bernoulli", "equation": equation}
    if symbolic is not None:
        arguments["symbolic"] = symbolic
    if variables is not None:
        arguments["variables"] = variables
    recorded = dispatch("studium_derivation_record", arguments, session=session)
    assert recorded["status"] == "recorded", recorded
    return str(recorded["derivation"]["id"])


def _check(session, derivation_id, **checks):
    checked = dispatch("studium_derivation_check", {"id": derivation_id, **checks}, session=session)
    assert checked["status"] == "checked", checked
    return checked


_UNITS = {"p": "Pa", "p_t": "Pa", "rho": "kg/m^3", "V": "m/s"}


def test_unrelated_checks_do_not_verify_a_wrong_equation(tmp_path):
    session = _project(tmp_path)
    excerpt = _excerpt(session)
    derivation = _record(session, r"p + \rho V^2 = p_t", symbolic="p + rho*V**2 = p_t")

    checked = _check(
        session,
        derivation,
        symbolic={"left": "a + b", "right": "b + a"},
        dimensions={"expression": "p", "symbol_units": {"p": "pascal"}, "expected_unit": "pascal"},
    )

    assert checked["verification_status"] == "UNVERIFIED", checked
    details = " ".join(str(item["detail"]) for item in checked["derivation"]["verification"]["checks"])
    assert "stored" in details

    paragraph = dispatch(
        "studium_paragraph_record",
        {
            "section": "bernoulli",
            "text": "En un flujo estacionario se cumple p + \\rho V^2 = p_t a lo largo de una línea de corriente.",
            "excerpts": [excerpt],
            "math": [{"statement": r"p + \rho V^2 = p_t", "kind": "derivation", "refs": [derivation]}],
        },
        session=session,
    )
    assert paragraph["status"] == "paragraph.math_ungrounded", paragraph


def test_a_premise_that_is_the_stored_equation_is_circular(tmp_path):
    session = _project(tmp_path)
    derivation = _record(session, r"p = p_0 + \rho g h", symbolic="p = p0 + rho*g*h")

    checked = _check(
        session,
        derivation,
        symbolic={"equation_left": "p", "equation_right": "p0 + rho*g*h", "solution": {"p": "p0 + rho*g*h"}},
    )

    assert checked["verification_status"] == "UNVERIFIED", checked
    (only,) = checked["derivation"]["verification"]["checks"]
    assert "circular" in str(only["detail"])


def test_a_premise_the_stored_equation_solves_verifies_it(tmp_path):
    session = _project(tmp_path)
    derivation = _record(session, r"V = \sqrt{2 g h}", symbolic="V = sqrt(2*g*h)")

    checked = _check(
        session,
        derivation,
        symbolic={"equation_left": "V^2", "equation_right": "2*g*h", "solution": {"V": "sqrt(2*g*h)"}},
        numeric={"expression": "sqrt(2*g*h)", "values": {"g": 9.81, "h": 4.905}, "claimed": 9.81},
    )

    assert checked["verification_status"] == "INDEPENDENTLY_VERIFIED", checked


def test_a_solution_that_does_not_satisfy_the_stored_equation_fails(tmp_path):
    session = _project(tmp_path)
    # Stored equation is wrong (missing the factor 2); the premise is right.
    derivation = _record(session, r"V = \sqrt{g h}", symbolic="V = sqrt(g*h)")

    checked = _check(
        session,
        derivation,
        symbolic={"equation_left": "V^2", "equation_right": "2*g*h", "solution": {"V": "sqrt(2*g*h)"}},
    )

    assert checked["verification_status"] == "FAILED", checked


def test_the_dimensional_check_covers_the_whole_stored_equation(tmp_path):
    session = _project(tmp_path)
    # Dimensionally inconsistent: rho*V has units of kg/(m^2 s), not Pa.
    derivation = _record(session, r"p + \rho V = p_t", symbolic="p + rho*V = p_t")

    checked = _check(
        session,
        derivation,
        dimensions={"expression": "p_t", "symbol_units": _UNITS, "expected_unit": "Pa"},
    )

    assert checked["verification_status"] == "FAILED", checked


def test_the_dimensional_check_passes_a_homogeneous_stored_equation(tmp_path):
    session = _project(tmp_path)
    derivation = _record(session, r"p + \tfrac12 \rho V^2 = p_t", symbolic="p + rho*V**2/2 = p_t")

    checked = _check(session, derivation, dimensions={"symbol_units": _UNITS, "expected_unit": "Pa"})

    assert checked["verification_status"] == "DIMENSIONALLY_VERIFIED", checked


def test_dimensional_units_fall_back_to_the_stored_variables(tmp_path):
    session = _project(tmp_path)
    variables = {name: {"meaning": name, "units": unit} for name, unit in _UNITS.items()}
    derivation = _record(session, r"p + \tfrac12 \rho V^2 = p_t", symbolic="p + rho*V**2/2 = p_t", variables=variables)

    checked = _check(session, derivation, dimensions={"symbol_units": {}})

    assert checked["verification_status"] == "DIMENSIONALLY_VERIFIED", checked


def test_a_numeric_check_must_evaluate_a_side_of_the_stored_equation(tmp_path):
    session = _project(tmp_path)
    derivation = _record(session, r"V = \sqrt{2 g h}", symbolic="V = sqrt(2*g*h)")

    checked = _check(session, derivation, numeric={"expression": "2 + 2", "values": {}, "claimed": 4})

    assert checked["verification_status"] == "UNVERIFIED", checked


def test_a_derivation_without_a_machine_readable_equation_cannot_be_verified(tmp_path):
    session = _project(tmp_path)
    derivation = _record(session, r"V = \sqrt{2 g h}")

    checked = _check(
        session,
        derivation,
        symbolic={"equation_left": "V^2", "equation_right": "2*g*h", "solution": {"V": "sqrt(2*g*h)"}},
    )

    assert checked["verification_status"] == "UNVERIFIED", checked
    (only,) = checked["derivation"]["verification"]["checks"]
    assert "symbolic" in str(only["detail"])


def test_a_residual_symbolic_form_still_binds(tmp_path):
    session = _project(tmp_path)
    derivation = _record(session, r"V = \sqrt{2 g h}", symbolic="V - sqrt(2*g*h)")

    checked = _check(
        session,
        derivation,
        symbolic={"equation_left": "V^2", "equation_right": "2*g*h", "solution": {"V": "sqrt(2*g*h)"}},
    )

    assert checked["verification_status"] == "SYMBOLICALLY_VERIFIED", checked


def test_a_stored_symbol_the_premise_never_mentions_leaves_the_check_undecided(tmp_path):
    """A case computation (hc, Ixc, A for a rectangle) does not falsify a general stored equation for hcp."""

    session = _project(tmp_path)
    derivation = _record(session, r"h_{cp} = h_c + I_{xc}/(h_c A)", symbolic="hcp = hc + Ixc/(hc*A)")

    checked = _check(
        session,
        derivation,
        symbolic={
            "equation_left": "hc + Ixc/(hc*A)",
            "equation_right": "2*H/3",
            "solution": {"hc": "H/2", "Ixc": "b*H**3/12", "A": "b*H"},
        },
    )

    assert checked["verification_status"] == "UNVERIFIED", checked
    (only,) = checked["derivation"]["verification"]["checks"]
    assert "hcp" in str(only["detail"]) and "never mention" in str(only["detail"])
