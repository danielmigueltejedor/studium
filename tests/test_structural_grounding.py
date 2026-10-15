"""F32: grounding compares complete relations, never fragments or substrings."""

from test_grounding import _book, _check_numeric, _excerpt, _explode, _two

from studium.authoring.grounding import GroundingContext, equation_evidence, formula_statuses, math_statements
from studium.mcp.server import dispatch


def _paragraph(session, text, excerpts):
    recorded = dispatch("studium_paragraph_record", {"section": "presion", "text": text, "excerpts": excerpts}, session=session)
    assert recorded["status"] == "recorded", recorded
    return recorded["paragraph"]


def _derivation_with_steps(session, equation, steps):
    recorded = dispatch(
        "studium_derivation_record",
        {"section": "presion", "name": "Presión", "equation": equation, "steps_latex": steps},
        session=session,
    )
    assert recorded["status"] == "recorded", recorded
    return str(recorded["derivation"]["id"])


def _statuses(root, paragraph):
    return [status for _text, status in formula_statuses(root, paragraph)]


def _audit(session, paragraph):
    return dispatch(
        "studium_audit_record",
        {"target": paragraph["id"], "kind": "formula", "excerpts": _two(session)},
        session=session,
    )


def test_math_statements_are_complete_relations_from_math_spans():
    text = (
        r"El balance da $\frac{dX}{dt} = -kX$ y además \(p = \rho g h\). "
        r"En cadena $a = b + c = d$; la viscosidad $\nu \equiv \mu/\rho$ y $g \approx 9{,}81$."
    )
    statements = math_statements(text)
    assert ("claim", r"\frac{dX}{dt} = -kX") in statements
    assert ("claim", r"p = \rho g h") in statements
    assert ("claim", "a = b + c") in statements and ("claim", "b + c = d") in statements
    assert ("definition", r"\nu \equiv \mu/\rho") in statements
    assert ("approximation", r"g \approx 9{,}81") in statements
    # No fragment such as "= -kX" or "dt =" is ever produced.
    assert all(not text.startswith("=") and not text.rstrip().endswith("=") for _kind, text in statements)


def test_a_relation_that_is_only_a_substring_of_a_derivation_is_not_grounded(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _book(tmp_path)
    excerpt = _excerpt(session, "La presión es fuerza por unidad de área.")
    derivation = _derivation_with_steps(session, "p = F / A + B", [])
    _check_numeric(session, derivation, "F / A + B", {"F": 100, "A": 2, "B": 1}, 51)
    # "p = F / A" is a prefix of "p = F / A + B": the substring rule grounded it as that derivation.
    paragraph = _paragraph(session, "Un error afirma que p = F / A en todo punto del fluido.", [excerpt])
    assert _statuses(root, paragraph) == ["unsupported"]
    audit = _audit(session, paragraph)
    assert audit["status"] == "audit.rejected", audit


def test_latex_relation_matching_the_checked_derivation_is_grounded(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _book(tmp_path)
    excerpt = _excerpt(session, "La presión es fuerza por unidad de área.")
    derivation = _derivation_with_steps(session, "p = F / A", [])
    _check_numeric(session, derivation, "F / A", {"F": 100, "A": 2}, 50)
    paragraph = _paragraph(session, r"La presión media sobre una superficie es $p = \frac{F}{A}$, en pascales.", [excerpt])
    # The derivation carries only a numeric check, so the equation is numerically reproduced, not symbolic.
    assert _statuses(root, paragraph) == ["numerically_reproduced"]
    report = dispatch("studium_quality_report", {}, session=session)["math_grounding"]
    assert report["formulas"] == 1 and report["formulas_ungrounded"] == 0
    assert report["by_status"]["numerically_reproduced"] == 1


def test_an_unchecked_derivation_step_is_labelled_not_counted_as_checked(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _book(tmp_path)
    excerpt = _excerpt(session, "La presión es fuerza por unidad de área.")
    derivation = _derivation_with_steps(session, "p = F / A", [r"dF = p\,dA"])
    _check_numeric(session, derivation, "F / A", {"F": 100, "A": 2}, 50)
    paragraph = _paragraph(session, r"Sobre un elemento de área, $dF = p\,dA$ en la superficie.", [excerpt])
    assert _statuses(root, paragraph) == ["derived_steps_unchecked"]
    report = dispatch("studium_quality_report", {}, session=session)["math_grounding"]
    assert report["by_kind"]["derivation"] == 0
    assert report["by_status"]["derived_steps_unchecked"] == 1


def test_arithmetic_in_prose_is_checked_at_its_written_precision(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _book(tmp_path)
    excerpt = _excerpt(session, "La presión es fuerza por unidad de área.")
    good = _paragraph(session, r"Con los datos, $1{,}8\cdot 80/0{,}002 = 72\,000$ pascales de diferencia.", [excerpt])
    assert _statuses(root, good) == ["numerically_reproduced"]
    bad = _paragraph(session, r"Con otros datos, $2\cdot 3{,}5 = 8$ pascales de diferencia.", [excerpt])
    assert _statuses(root, bad) == ["contradicted"]
    assert _audit(session, bad)["status"] == "audit.rejected"


def test_unparseable_definitions_and_approximations_are_labelled_not_blocking(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _book(tmp_path)
    excerpt = _excerpt(session, "La presión es fuerza por unidad de área.")
    paragraph = _paragraph(
        session,
        r"La continuidad es $\nabla\cdot\mathbf{u} = 0$, la viscosidad cinemática $\nu \equiv \mu/\rho$ y $g \approx 9{,}81$.",
        [excerpt],
    )
    assert _statuses(root, paragraph) == ["not_machine_checkable", "definition", "approximation"]
    report = dispatch("studium_quality_report", {}, session=session)["math_grounding"]
    assert report["formulas_ungrounded"] == 0
    assert report["by_status"]["not_machine_checkable"] == 1


def test_values_and_conditions_are_labelled_not_grounded_as_formulas(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _book(tmp_path)
    excerpt = _excerpt(session, "La presión es fuerza por unidad de área.")
    paragraph = _paragraph(session, r"Tomamos $r = 3$, en la pared $u = 0$ y en el borde $r = R$; además $p_0 = 101\,325$.", [excerpt])
    assert _statuses(root, paragraph) == ["value_or_condition"] * 4


def test_typeset_scientific_notation_is_one_number(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _book(tmp_path)
    excerpt = _excerpt(session, "La presión es fuerza por unidad de área.")
    paragraph = _paragraph(
        session, r"El cociente es $6{,}63\times 10^{-8}/1{,}0\times 10^{-5} = 6{,}63\times 10^{-3}$ en este caso.", [excerpt]
    )
    assert _statuses(root, paragraph) == ["numerically_reproduced"]


def test_elided_or_dangling_sides_are_not_statements():
    assert math_statements(r"$n + \ldots + b + c = 0$ y $= -kX$") == []


def test_source_audit_labels_each_paragraphs_equations(tmp_path, monkeypatch):
    from studium.authoring.render import render_draft

    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _book(tmp_path)
    excerpt = _excerpt(session, "La presión es fuerza por unidad de área.")
    derivation = _derivation_with_steps(session, "p = F / A", [])
    _check_numeric(session, derivation, "F / A", {"F": 100, "A": 2}, 50)
    _paragraph(session, r"La presión media es $p = \frac{F}{A}$ y la continuidad $\nabla\cdot\mathbf{u} = 0$ en el fluido.", [excerpt])
    render_draft(root)
    tex = (root / "latex" / "draft.tex").read_text(encoding="utf-8")
    assert "Ecuaciones: 1 reproducida numéricamente, 1 no comprobable automáticamente." in tex


def test_unparseable_equation_is_never_verified_but_a_quoting_source_supports_it(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _book(tmp_path)
    quoted = _excerpt(session, r"Gauss: $\oint_S \mathbf{E}\cdot d\mathbf{A} = Q/\varepsilon_0$ for any closed surface.", url="https://open.example/gauss")
    paragraph = _paragraph(session, r"La ley de Gauss es $\oint_S \mathbf{E}\cdot d\mathbf{A} = Q/\varepsilon_0$ para toda superficie cerrada.", [quoted])
    items = equation_evidence(root, paragraph)
    assert [(item["status"], item["evidence"], item["machine_parseable"], item["human_review"]) for item in items] == [
        ("source_supported", [quoted], False, "recommended")
    ]


def test_a_failed_check_of_the_same_equation_is_reported_and_blocks(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _book(tmp_path)
    excerpt = _excerpt(session, "La presión es fuerza por unidad de área.")
    derivation = _derivation_with_steps(session, "p = F * A", [])
    failed = dispatch(
        "studium_derivation_check",
        {"id": derivation, "numeric": {"expression": "F * A", "values": {"F": 100, "A": 2}, "claimed": 50}},
        session=session,
    )
    assert failed["status"] == "checked"
    paragraph = _paragraph(session, "Por error se escribe p = F * A en el texto.", [excerpt])
    items = equation_evidence(root, paragraph)
    assert [(item["status"], item["evidence"], item["blocks_audit"]) for item in items] == [("verification_failed", [derivation], True)]


def test_review_and_quality_report_separate_the_five_stages(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, _root = _book(tmp_path)
    excerpt = _excerpt(session, "La presión es fuerza por unidad de área.")
    _paragraph(session, r"La continuidad se escribe $$\nabla\cdot\mathbf{u} = 0$$ en un fluido incompresible.", [excerpt])
    review = dispatch("studium_book_review", {}, session=session)
    assert review["scientific_verification"]["status"] == "incomplete"
    assert review["scientific_verification"]["unresolved_important_equations"] == 1
    assert "not scientific verification" in review["message"]
    stages = dispatch("studium_quality_report", {}, session=session)["stages"]
    assert set(stages) == {"draft", "evidence_audit", "scientific_verification", "human_approval", "publication_ready"}
    assert stages["draft"]["status"] == "renderable"
    assert stages["human_approval"]["status"] == "not_recorded"
    assert stages["publication_ready"]["ready"] is False


def test_equation_report_lists_statements_as_written_with_filters(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, _root = _book(tmp_path)
    excerpt = _excerpt(session, "La presión es fuerza por unidad de área.")
    text = r"Con $2\cdot 3 = 6$ y la ley $\nabla\cdot\mathbf{u} = 0$, además $\nu \equiv \mu/\rho$."
    _paragraph(session, text, [excerpt])
    report = dispatch("studium_equation_report", {}, session=session)
    assert report["total"] == 3
    assert [item["statement"] for item in report["equations"]] == [r"2\cdot 3 = 6", r"\nabla\cdot\mathbf{u} = 0", r"\nu \equiv \mu/\rho"]
    only = dispatch("studium_equation_report", {"status": "not_machine_checkable"}, session=session)
    assert only["total"] == 1 and only["equations"][0]["human_review"] == "required"
    bad = dispatch("studium_equation_report", {"status": "verified"}, session=session)
    assert bad["status"] == "mcp.invalid_input"


def test_equation_of_an_independently_verified_derivation_is_symbolically_verified(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _book(tmp_path)
    excerpt = _excerpt(session, "La presión es fuerza por unidad de área.")
    derivation = _derivation_with_steps(session, "V^2 = 2 g h", [])
    checked = dispatch(
        "studium_derivation_check",
        {
            "id": derivation,
            "symbolic": {"equation_left": "V^2", "equation_right": "2*g*h", "solution": {"V": "sqrt(2*g*h)"}},
            "numeric": {"expression": "sqrt(2*g*h)", "values": {"g": 9.81, "h": 4.905}, "claimed": 9.81},
        },
        session=session,
    )
    assert checked["verification_status"] == "INDEPENDENTLY_VERIFIED", checked
    paragraph = _paragraph(session, r"Torricelli da $V^{2} = 2gh$ para la descarga libre.", [excerpt])
    items = equation_evidence(root, paragraph)
    assert [(item["status"], item["evidence"]) for item in items] == [("symbolically_verified", [derivation])]


def test_parser_reads_scalar_notation_and_refuses_vector_operators():
    from studium.authoring.grounding import _relation, equivalent_math

    assert equivalent_math(r"E = \tfrac12 m v^{2}", "E = m*v**2/2")
    assert equivalent_math(r"x = A\cos\omega t + B\sin\omega t", "x = A*cos(omega*t) + B*sin(omega*t)")
    assert equivalent_math(r"\omega_d = \omega_0\sqrt{1 - \zeta^{2}}", "omega_d**2 = omega_0**2*(1 - zeta**2)") is False
    assert _relation(r"x(t) = x_0 e^{kt}") is not None
    assert _relation(r"V_t = (\rho_p - \rho_f)\,g\,d^{2}/(18\mu)") is not None
    assert _relation(r"\mathbf{p} = m\mathbf{v}") is not None
    # Cross products, divergence, integrals and norms are not guessed as scalars.
    assert _relation(r"\mathbf{L}_O = \mathbf{r}\times m\mathbf{v}") is None
    assert _relation(r"\nabla\cdot\mathbf{u} = 0") is None
    assert _relation(r"Q = \int_0^{R} u\,2\pi r\,dr") is None
    assert _relation(r"|\mathbf{u}| = U") is None


def test_numeric_matrix_relations_are_checked(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _book(tmp_path)
    excerpt = _excerpt(session, "La presión es fuerza por unidad de área.")
    good = _paragraph(
        session,
        r"La rigidez da $\begin{bmatrix} 2 & -1 \\ -1 & 2 \end{bmatrix}\begin{bmatrix} 1 \\ 1 \end{bmatrix} = \begin{bmatrix} 1 \\ 1 \end{bmatrix}$ en kN.",
        [excerpt],
    )
    assert _statuses(root, good) == ["numerically_reproduced"]
    bad = _paragraph(
        session,
        r"Con otra carga, $\begin{bmatrix} 2 & -1 \\ -1 & 2 \end{bmatrix}\begin{bmatrix} 1 \\ 0 \end{bmatrix} = \begin{bmatrix} 2 \\ 1 \end{bmatrix}$ en kN.",
        [excerpt],
    )
    assert _statuses(root, bad) == ["contradicted"]
    symbolic = _paragraph(
        session, r"La matriz de rigidez del muelle es $\mathbf{K} = \begin{bmatrix} k & -k \\ -k & k \end{bmatrix}$ en general.", [excerpt]
    )
    assert _statuses(root, symbolic) == ["not_machine_checkable"]


def test_equivalence_check_is_bounded_on_large_numeric_and_transcendental_relations():
    """Found on book-01: simplify() on a relation with large powers and logs ran for minutes."""

    import time

    from studium.authoring.grounding import equivalent_math

    started = time.perf_counter()
    # ln 25 / 2 is ln 5: SymPy rewrites the integer logarithm itself, so this is a genuine match.
    assert equivalent_math(r"\Delta v = 3000\ln 5", r"\Delta v = 3000\ln(25)/2") is True
    assert equivalent_math(r"\Delta v = 3000\ln 5", r"\Delta v = 3000\ln 7") is False
    assert equivalent_math(r"v = \sqrt{2\cdot 9{,}81\cdot 1000^{7}}", r"v = \sqrt{2 g h}") is False
    assert equivalent_math(r"y = e^{x}\ln(x)^{9}(x+1)^{8}", r"y = e^{x}\ln(x)^{9}(x+1)^{8}") is True
    # Different symbols are never the same relation.
    assert equivalent_math("p = F/A", "q = F/A") is False
    assert time.perf_counter() - started < 5


def test_tensor_double_dot_is_not_a_separator_and_inequalities_end_a_chain():
    statements = math_statements(r"$\Phi_v = 2\mu\,\mathbf{E}:\mathbf{E} = 2\mu\,E_{ij}E_{ij} \ge 0$")
    assert statements == [
        ("claim", r"\Phi_v = 2\mu\,\mathbf{E}:\mathbf{E}"),
        ("claim", r"2\mu\,\mathbf{E}:\mathbf{E} = 2\mu\,E_{ij}E_{ij}"),
        ("condition", r"2\mu\,E_{ij}E_{ij} \ge 0"),
    ]
    assert math_statements(r"$G = 0:\quad u = Uy/h$ con $x<L$") == [
        ("claim", "G = 0"),
        ("claim", "u = Uy/h"),
        ("condition", "x < L"),
    ]


def test_differentials_are_never_read_as_products():
    from studium.authoring.grounding import _relation, equivalent_math

    # Read as a product, du/dy and u/y would be the same relation.
    assert _relation(r"\tau = \mu\,du/dy") is None
    assert _relation(r"\mathbf{F} = \frac{d\mathbf{p}}{dt}") is None
    assert _relation(r"dx/dt = kx") is None
    assert equivalent_math(r"\tau = \mu\,du/dy", r"\tau = \mu\,u/y") is False
    # A diameter d is still a symbol.
    assert _relation(r"V_t = (\rho_p - \rho_f)\,g\,d^{2}/(18\mu)") is not None
    # The same differential text still matches itself (text path, no parsing).
    assert equivalent_math(r"\tau = \mu\,du/dy", r"\tau = \mu\, du/dy") is True


def test_dimension_probe_uses_the_notation_units_and_flags_symbol_reuse(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _book(tmp_path)
    excerpt = _excerpt(session, "La presión es fuerza por unidad de área.")
    for symbol, meaning, units in (
        ("p", "presión", "Pa"),
        ("\\rho", "densidad", "kg/m^3"),
        ("V", "velocidad", "m/s"),
        ("D", "diámetro", "m"),
        ("C_D", "coeficiente de resistencia", ""),
        ("S", "superficie", "m^2"),
        ("g", "gravedad", "m/s^2"),
        ("h", "altura", "m"),
    ):
        recorded = dispatch(
            "studium_notation_record",
            {"section": "presion", "symbol": symbol, "meaning": meaning, **({"units": units} if units else {})},
            session=session,
        )
        assert recorded["status"] == "recorded", recorded
    good = _paragraph(session, r"La presión es $p = \rho g h$ y la dinámica $q = \tfrac12\rho V^{2}$ en pascales.", [excerpt])
    clash = _paragraph(session, r"Con la resistencia $D = C_D\,\tfrac12\rho V^{2} S$ en newtons.", [excerpt])
    context = GroundingContext(root)
    by_statement = {item["statement"]: item for rec in (good, clash) for item in equation_evidence(root, rec, context)}
    assert by_statement[r"p = \rho g h"]["dimensions"]["status"] == "consistent"
    # q has no registered unit: the probe says so instead of guessing.
    assert by_statement[r"q = \tfrac12\rho V^{2}"]["dimensions"]["status"] == "unavailable"
    # D was registered as a diameter, so the drag equation looks inconsistent: a notation clash to review.
    assert by_statement[r"D = C_D\,\tfrac12\rho V^{2} S"]["dimensions"]["status"] == "inconsistent"
    # The probe never changes the evidence status.
    assert by_statement[r"p = \rho g h"]["status"] == "unsupported"
    summary = dispatch("studium_quality_report", {}, session=session)["math_grounding"]
    assert summary["dimension_probe"]["inconsistent"] == 1
    assert summary["dimension_conflicts"][0]["statement"] == r"D = C_D\,\tfrac12\rho V^{2} S"


def test_left_and_right_delimiters_are_not_relation_operators():
    """\\left starts with \\le: it once cut 'y = a/2 \\left(...\\right)' into a fragment that matched a derivation."""

    text = (
        r"\begin{equation} y = \frac{a}{2}\left(\frac{2 t x}{u_0} - \frac{x^{2}}{u_0^{2}}\right), "
        r"\qquad 0 \le x \le u_0 t \end{equation}"
    )
    assert math_statements(text) == [
        ("claim", r"y = \frac{a}{2}\left(\frac{2 t x}{u_0} - \frac{x^{2}}{u_0^{2}}\right)"),
        ("condition", r"0 \le x"),
        ("condition", r"x \le u_0 t"),
    ]
    assert math_statements(r"$a \leftarrow b$ y $c \nearrow d$") == []


def test_a_relation_chained_in_a_derivation_equation_is_not_individually_verified(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _book(tmp_path)
    excerpt = _excerpt(session, "La presión es fuerza por unidad de área.")
    derivation = _derivation_with_steps(session, "p = F / A, \\qquad q = F / (2 A)", [])
    _check_numeric(session, derivation, "F / A", {"F": 100, "A": 2}, 50)
    paragraph = _paragraph(session, r"Se tiene $q = F / (2 A)$ en la sección y $p = F / A$ en general.", [excerpt])
    statuses = dict(formula_statuses(root, paragraph))
    # The check ran on one expression; neither relation of the two-relation equation is individually covered.
    assert set(statuses.values()) == {"derived_steps_unchecked"}
