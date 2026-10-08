"""A removed problem stays out of the draft, and toy arithmetic needs a cited excerpt."""

import json

from studium.mcp.server import dispatch, open_workspace, tool_names

_RUST_SOURCE = "#[test]\nfn holds() {\n    assert_eq!(2 + 2, 4);\n}\n"
_RUST_INVOCATION = ["rustc", "--test", "main.rs", "-o", "tester"]
_PROMPT = "Compute the mass from the stored density."


def test_problem_remove_drops_the_problem_and_leaves_sources(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _topic(tmp_path, "programacion", "Programación")
    source_id = _source(session, "https://open.example/fluidos")
    excerpt_id = _excerpt(session, source_id, "https://open.example/fluidos", "La página abierta describe la masa.")
    dispatch(
        "studium_blueprint_store",
        {"sections": [{"id": "tema-1", "title": "Conservación"}]},
        session=session,
    )
    dispatch(
        "studium_paragraph_record",
        {
            "section": "tema-1",
            "text": "La masa del volumen de control sigue la página abierta.",
            "excerpts": [excerpt_id],
        },
        session=session,
    )
    first = _rust(session, "tema-1", _PROMPT)
    second = _rust(session, "tema-1", "A second Rust test stays until it is removed.")
    rendered = dispatch("studium_render", {}, session=session)
    tex = (root / "latex" / "draft.tex").read_text(encoding="utf-8")
    assert _PROMPT in tex
    assert rendered["released"] is False
    sources_before = (root / "bibliography" / "public.jsonl").read_bytes()
    paragraphs_before = (root / "draft" / "paragraphs.jsonl").read_bytes()
    excerpts_before = (root / "bibliography" / "excerpts.jsonl").read_bytes()
    state_before = (root / ".studium" / "state.json").read_bytes()
    removed = dispatch("studium_problem_remove", {"id": first}, session=session)
    assert removed["status"] == "removed"
    assert removed["problem_id"] == first
    assert removed["released"] is False
    assert removed["applied"] is False
    assert removed["project_state"] != "RELEASED"
    listed = dispatch("studium_problem_list", {}, session=session)
    assert first not in [item["id"] for item in listed["problems"]]
    assert second in [item["id"] for item in listed["problems"]]
    again = dispatch("studium_render", {}, session=session)
    tex_after = (root / "latex" / "draft.tex").read_text(encoding="utf-8")
    assert _PROMPT not in tex_after
    assert "A second Rust test stays until it is removed." in tex_after
    assert again["released"] is False
    assert (root / "bibliography" / "public.jsonl").read_bytes() == sources_before
    assert (root / "draft" / "paragraphs.jsonl").read_bytes() == paragraphs_before
    assert (root / "bibliography" / "excerpts.jsonl").read_bytes() == excerpts_before
    assert (root / ".studium" / "state.json").read_bytes() == state_before
    problems_after = (root / "problems" / "problems.jsonl").read_text(encoding="utf-8")
    missing = dispatch("studium_problem_remove", {"id": first}, session=session)
    assert missing["status"] == "problem.not_found"
    blank = dispatch("studium_problem_remove", {"id": "  "}, session=session)
    assert blank["status"] == "mcp.invalid_input"
    absent = dispatch("studium_problem_remove", {"id": "PRB-9999"}, session=session)
    assert absent["status"] == "problem.not_found"
    assert (root / "problems" / "problems.jsonl").read_text(encoding="utf-8") == problems_after
    assert "studium_problem_remove" in tool_names()
    assert json.loads(state_before)["state"] != "RELEASED"


def test_book_next_removes_each_rust_problem_before_a_computation(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, _root = _topic(tmp_path, "fluidos", "Mecánica de fluidos")
    for index in range(12):
        _opened(session, index)
    dispatch(
        "studium_blueprint_store",
        {"sections": [{"id": f"tema-{index}", "title": f"Tema {index}"} for index in range(1, 9)]},
        session=session,
    )
    first = _rust(session, "tema-1", "First leftover Rust test.")
    second = _rust(session, "tema-2", "Second leftover Rust test.")
    nxt = dispatch("studium_book_next", {}, session=session)
    assert nxt["tool"] == "studium_problem_remove"
    assert nxt["tool"] != "studium_computation_check"
    assert nxt["arguments"]["id"] == first
    assert nxt["released"] is False
    assert dispatch("studium_problem_remove", {"id": first}, session=session)["status"] == "removed"
    following = dispatch("studium_book_next", {}, session=session)
    assert following["tool"] == "studium_problem_remove"
    assert following["arguments"]["id"] == second
    assert following["tool"] != "studium_computation_check"
    assert dispatch("studium_problem_remove", {"id": second}, session=session)["status"] == "removed"
    after = dispatch("studium_book_next", {}, session=session)
    assert after["tool"] != "studium_problem_remove"
    assert after["tool"] != "studium_computation_check"
    assert after["released"] is False


def test_small_integer_arithmetic_needs_every_number_in_one_excerpt(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _topic(tmp_path, "fluidos", "Mecánica de fluidos")
    dispatch(
        "studium_blueprint_store",
        {"sections": [{"id": "tema-1", "title": "Fuerza"}, {"id": "tema-2", "title": "Otro"}]},
        session=session,
    )
    bare = _excerpt(session, _source(session, "https://open.example/bare"), "https://open.example/bare", "La página no trae esas cifras.")
    only_thousand = _excerpt(
        session,
        _source(session, "https://open.example/thousand"),
        "https://open.example/thousand",
        "La masa almacenada es 1000.",
    )
    split_rest = _excerpt(
        session,
        _source(session, "https://open.example/rest"),
        "https://open.example/rest",
        "El intervalo es 2 y el conteo es 1.",
    )
    grounded = _excerpt(
        session,
        _source(session, "https://open.example/grounded"),
        "https://open.example/grounded",
        "La masa es 1000, el intervalo es 2 y el conteo es 1.",
    )
    force = _excerpt(
        session,
        _source(session, "https://open.example/force"),
        "https://open.example/force",
        "Los datos citados son 2, 7 y 3.",
    )
    dispatch(
        "studium_paragraph_record",
        {
            "section": "tema-1",
            "text": "El texto del párrafo nombra 2, 7 y 3, pero el extracto no.",
            "excerpts": [bare],
        },
        session=session,
    )
    state_before = (root / ".studium" / "state.json").read_bytes()
    toy = dispatch(
        "studium_computation_check",
        {"expression": "2 * (7 - 3) / 2", "result": 4, "section": "tema-1"},
        session=session,
    )
    assert toy["status"] == "computation.ungrounded"
    assert toy["status"] != "replayed"
    assert toy["accepted"] is False
    assert toy["correct"] is False
    assert toy["released"] is False
    assert "verified" not in json.dumps(toy)
    assert not (root / "problems" / "computations.jsonl").exists()
    dispatch(
        "studium_paragraph_record",
        {"section": "tema-1", "text": "Solo aparece mil.", "excerpts": [only_thousand]},
        session=session,
    )
    partial = dispatch(
        "studium_computation_check",
        {"expression": "1000 * 2 * 1", "result": 2000, "section": "tema-1"},
        session=session,
    )
    assert partial["status"] == "computation.ungrounded"
    assert not (root / "problems" / "computations.jsonl").exists()
    dispatch(
        "studium_paragraph_record",
        {"section": "tema-1", "text": "El resto está en otro extracto.", "excerpts": [split_rest]},
        session=session,
    )
    split = dispatch(
        "studium_computation_check",
        {"expression": "1000 * 2 * 1", "result": 2000, "section": "tema-1"},
        session=session,
    )
    assert split["status"] == "computation.ungrounded"
    assert not (root / "problems" / "computations.jsonl").exists()
    dispatch(
        "studium_paragraph_record",
        {"section": "tema-2", "text": "Otro capítulo cita las tres cifras.", "excerpts": [grounded]},
        session=session,
    )
    other_section = dispatch(
        "studium_computation_check",
        {"expression": "1000 * 2 * 1", "result": 2000, "section": "tema-1"},
        session=session,
    )
    assert other_section["status"] == "computation.ungrounded"
    dispatch(
        "studium_paragraph_record",
        {"section": "tema-1", "text": "Ahora el mismo extracto cita las tres cifras.", "excerpts": [grounded]},
        session=session,
    )
    accepted = dispatch(
        "studium_computation_check",
        {"expression": "1000 * 2 * 1", "result": 2000, "section": "tema-1"},
        session=session,
    )
    assert accepted["status"] == "replayed"
    assert accepted["correct"] is True
    assert accepted["accepted"] is True
    assert accepted["released"] is False
    assert "verified" not in json.dumps(accepted)
    dispatch(
        "studium_paragraph_record",
        {"section": "tema-1", "text": "La fuerza usa los datos del extracto.", "excerpts": [force]},
        session=session,
    )
    replayed = dispatch(
        "studium_computation_check",
        {"expression": "2 * (7 - 3) / 2", "result": 4, "section": "tema-1"},
        session=session,
    )
    assert replayed["status"] == "replayed"
    assert replayed["server_result"] == "4"
    assert replayed["released"] is False
    decimal = dispatch(
        "studium_computation_check",
        {"expression": "2.5 * 4", "result": 10, "section": "tema-1"},
        session=session,
    )
    assert decimal["status"] == "replayed"
    assert (root / ".studium" / "state.json").read_bytes() == state_before
    assert json.loads(state_before)["state"] != "RELEASED"


def _topic(tmp_path, slug: str, topic: str):
    session = open_workspace(str(tmp_path))
    assert dispatch("studium_project_create", {"slug": slug, "topic": topic}, session=session)["status"] == "created"
    return session, tmp_path / slug


def _source(session, url: str) -> str:
    recorded = dispatch("studium_public_source_record", {"title": "Open page", "url": url}, session=session)
    assert recorded["status"] == "recorded"
    return str(recorded["candidate"]["id"])


def _excerpt(session, source_id: str, url: str, text: str) -> str:
    recorded = dispatch(
        "studium_excerpt_record",
        {"source_id": source_id, "url": url, "text": text},
        session=session,
    )
    assert recorded["status"] == "recorded"
    return str(recorded["excerpt"]["id"])


def _opened(session, index: int) -> str:
    url = f"https://open.example/page-{index}"
    return _excerpt(session, _source(session, url), url, f"Opened page {index} states a stored fact.")


def _rust(session, section: str, prompt: str) -> str:
    recorded = dispatch(
        "studium_problem_record",
        {
            "section": section,
            "prompt": prompt,
            "source_text": _RUST_SOURCE,
            "invocation": _RUST_INVOCATION,
        },
        session=session,
    )
    assert recorded["status"] == "recorded"
    return str(recorded["problem"]["id"])


def _explode(*_args, **_kwargs):
    raise AssertionError("must not fetch")
