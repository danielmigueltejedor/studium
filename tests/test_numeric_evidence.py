"""D2: numeric evidence is reported for what it is (PR #42 review, priority 5).

Source independence, arithmetic reproduction of the stated answer, and
reproduction of the answer from the stored model are three different things.
None of them is scientific validity, and the draft says so.
"""

from studium.mcp.server import _failed, dispatch, open_workspace


def _book(tmp_path):
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
    for index in range(2):
        url = f"https://open.example/pitot-{index}"
        source = dispatch("studium_public_source_record", {"title": f"Pitot {index}", "url": url}, session=session)
        excerpt = dispatch(
            "studium_excerpt_record",
            {"source_id": source["candidate"]["id"], "url": url, "text": f"Static plus dynamic pressure is total pressure ({index})."},
            session=session,
        )
        excerpts.append(excerpt["excerpt"]["id"])
    return session, tmp_path / "fluidos", excerpts


def _pitot(session, excerpts, *, symbolic="sqrt(2*dp/rho)", expected="31.30", final="sqrt(2*600/1.225)"):
    recorded = dispatch(
        "studium_problem_record",
        {
            "section": "bernoulli",
            "role": "worked",
            "prompt": "Un tubo de Pitot mide 600 Pa de presión dinámica en aire de 1,225 kg/m^3. Calcule la velocidad.",
            "expected": expected,
            "excerpts": excerpts,
            "solution": {
                "given": [{"symbol": "dp", "value": 600, "unit": "Pa"}, {"symbol": "rho", "value": 1.225, "unit": "kg/m^3"}],
                "model": [{"name": "Pitot", "latex": r"V = \sqrt{2\,\Delta p/\rho}", "symbolic": symbolic}],
                "assumptions": ["flujo estacionario, incompresible y no viscoso"],
                "steps": [{"text": "Velocidad", "expression": final, "expected": expected, "unit": "m/s"}],
                "result": r"V \approx 31{,}3\ \mathrm{m/s}",
            },
        },
        session=session,
    )
    assert recorded["status"] == "recorded", recorded
    identifier = recorded["problem"]["id"]
    dispatch("studium_problem_check", {"id": identifier}, session=session)
    return identifier


def test_review_uses_the_stored_answer_and_separates_the_evidence(tmp_path):
    session, _root, excerpts = _book(tmp_path)
    identifier = _pitot(session, excerpts)
    review = dispatch("studium_problem_scientific_review", {"id": identifier}, session=session)
    assert review["expected_source"] == "stored"
    assert review["evidence"] == {
        "source_independence": True,
        "answer_arithmetic": "replayed",
        "model_reproduction": "COMPUTATION_REPRODUCED",
        "scientific_validity": "not_established",
    }
    assert review["report"]["status"] != "INDEPENDENTLY_VERIFIED"


def test_review_finds_a_model_that_does_not_give_the_replayed_answer(tmp_path):
    session, _root, excerpts = _book(tmp_path)
    # The steps compute the right number, but the stored model forgot the factor 2.
    identifier = _pitot(session, excerpts, symbolic="sqrt(dp/rho)")
    review = dispatch("studium_problem_scientific_review", {"id": identifier}, session=session)
    assert review["evidence"]["answer_arithmetic"] == "replayed"
    assert review["evidence"]["model_reproduction"] == "FAILED"
    assert review["report"]["status"] == "FAILED"


def test_the_draft_says_what_the_answer_check_established(tmp_path):
    session, root, excerpts = _book(tmp_path)
    _pitot(session, excerpts)
    _pitot(session, excerpts, expected="35.0", final="sqrt(2*600/1.225)")
    for role in ("purpose", "explanation"):
        dispatch(
            "studium_paragraph_record",
            {"section": "bernoulli", "role": role, "excerpts": excerpts[:1],
             "text": "El tubo de Pitot compara la presión total con la estática para obtener la velocidad del aire."},
            session=session,
        )
    dispatch("studium_render", {}, session=session)
    tex = (root / "latex" / "draft.tex").read_text(encoding="utf-8")
    assert "Comprobación de la respuesta" in tex
    assert "no valida el modelo físico" in tex
    assert "no da la respuesta enunciada" in tex


def test_a_computation_verdict_is_a_result_not_a_tool_error(tmp_path):
    session, _root, _excerpts = _book(tmp_path)
    checked = dispatch(
        "studium_computation_check",
        {"section": "bernoulli", "expression": "sqrt(2*600/1.225)", "result": "35.0"},
        session=session,
    )
    assert checked["status"] == "mismatch"
    assert _failed(checked) is False
    assert _failed({"status": "mismatch"}) is True
