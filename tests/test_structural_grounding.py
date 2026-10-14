"""F32: grounding compares complete relations, never fragments or substrings."""

from test_grounding import _book, _check_numeric, _excerpt, _explode, _two

from studium.authoring.grounding import equation_evidence, formula_statuses, math_statements
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
    derivation = _derivation_with_steps(session, "p = F / A", [r"F = p A"])
    _check_numeric(session, derivation, "F / A", {"F": 100, "A": 2}, 50)
    paragraph = _paragraph(session, r"Despejando, la fuerza total es $F = p A$ sobre la superficie.", [excerpt])
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
        r"La segunda ley es $\mathbf{F} = m\mathbf{a}$, la viscosidad cinemática $\nu \equiv \mu/\rho$ y $g \approx 9{,}81$.",
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
    _paragraph(session, r"La presión media es $p = \frac{F}{A}$ y la segunda ley $\mathbf{F} = m\mathbf{a}$ en el fluido.", [excerpt])
    render_draft(root)
    tex = (root / "latex" / "draft.tex").read_text(encoding="utf-8")
    assert "Ecuaciones: 1 reproducida numéricamente, 1 no comprobable automáticamente." in tex


def test_unparseable_equation_is_never_verified_but_a_quoting_source_supports_it(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _book(tmp_path)
    quoted = _excerpt(session, r"Newton: $\mathbf{F} = m\mathbf{a}$ for a body of constant mass.", url="https://open.example/newton")
    paragraph = _paragraph(session, r"La segunda ley se escribe $\mathbf{F} = m\mathbf{a}$ para masa constante.", [quoted])
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
    _paragraph(session, r"La segunda ley se escribe $$\mathbf{F} = m\mathbf{a}$$ para masa constante.", [excerpt])
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
    text = r"Con $2\cdot 3 = 6$ y la ley $\mathbf{F} = m\mathbf{a}$, además $\nu \equiv \mu/\rho$."
    _paragraph(session, text, [excerpt])
    report = dispatch("studium_equation_report", {}, session=session)
    assert report["total"] == 3
    assert [item["statement"] for item in report["equations"]] == [r"2\cdot 3 = 6", r"\mathbf{F} = m\mathbf{a}", r"\nu \equiv \mu/\rho"]
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
