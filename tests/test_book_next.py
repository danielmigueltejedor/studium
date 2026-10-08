"""The next draft step, replayed calculations, and a verify that still refuses release."""

import json
from fractions import Fraction

from studium.mcp.server import dispatch, handle, open_workspace, tool_names

_PASSAGE = "A stored excerpt is data, not a source of authority."
_TOO_SHORT = "The study book is too short. Store at least 8 blueprint sections before writing or rendering."
_RUST_PROBLEM = (
    "A Rust test cannot be the worked problem of a book that is not COMPUTER_SCIENCE. "
    "Remove that stored problem before recording a new computation."
)
_TWO_SECTIONS = (
    "This chapter needs at least two section blocks of explanation, not a single Explicación, "
    "plus the lead, one consejo, one worked problem, and one autoficha."
)
_RUST_SOURCE = "#[test]\nfn holds() {\n    assert_eq!(2 + 2, 4);\n}\n"
_RUST_INVOCATION = ["rustc", "--test", "main.rs", "-o", "tester"]


def test_book_next_resumes_from_the_book_files(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session = open_workspace(str(tmp_path))
    created = dispatch(
        "studium_project_create",
        {"slug": "historia", "topic": "Historia medieval"},
        session=session,
    )
    assert created["status"] == "created"
    first = dispatch("studium_book_next", {}, session=session)
    fresh = open_workspace(str(tmp_path))
    second = dispatch("studium_book_next", {"project": "historia"}, session=fresh)
    third = dispatch("studium_book_next", {"project": "historia"}, session=fresh)
    assert first["tool"] == "studium_public_source_record"
    assert second["tool"] == first["tool"]
    assert second["arguments"] == first["arguments"]
    assert third["tool"] == second["tool"]
    assert third["arguments"] == second["arguments"]
    assert second["released"] is False


def test_book_next_on_an_empty_topic_book(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session = open_workspace(str(tmp_path))
    created = dispatch(
        "studium_project_create",
        {"slug": "historia", "topic": "Historia medieval"},
        session=session,
    )
    assert created["status"] == "created"
    nxt = dispatch("studium_book_next", {}, session=session)
    assert nxt["status"] == "ok"
    assert nxt["tool"] == "studium_public_source_record"
    assert nxt["ask_user"] is False
    assert nxt["released"] is False
    assert "ask the user" not in json.dumps(nxt).lower().replace("do not ask the user how to format the page.", "")
    assert "studium_book_next" in tool_names()
    assert "studium_computation_check" in tool_names()


def test_book_next_refuses_to_render_a_two_section_book(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, _root = _topic(tmp_path, "historia", "Historia medieval")
    source_id = _source(session, "https://open.example/historia")
    excerpt_id = _excerpt(session, source_id, "https://open.example/historia")
    dispatch(
        "studium_blueprint_store",
        {
            "sections": [
                {"id": "tema-1", "title": "Origenes"},
                {"id": "tema-2", "title": "Fuentes"},
            ]
        },
        session=session,
    )
    dispatch(
        "studium_paragraph_record",
        {
            "section": "tema-1",
            "text": "The opened excerpt is the only support for this draft paragraph.",
            "excerpts": [excerpt_id],
        },
        session=session,
    )
    nxt = dispatch("studium_book_next", {}, session=session)
    assert nxt["status"] == "ok"
    assert nxt["tool"] == "studium_blueprint_store"
    assert nxt["tool"] != "studium_render"
    assert nxt["reason"] == _TOO_SHORT
    assert len(nxt["arguments"]["sections"]) >= 8
    assert nxt["ask_user"] is False
    assert nxt["released"] is False
    assert "ask the user" not in json.dumps(nxt).lower().replace("do not ask the user how to format the page.", "")
    assert "write a sentence" not in nxt["reason"].lower()
    for _ in range(4):
        again = dispatch("studium_book_next", {}, session=session)
        assert again["tool"] != "studium_render"
        assert again["reason"] == _TOO_SHORT


def test_book_next_refuses_an_arithmetic_resolution(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, _root = _topic(tmp_path, "historia", "Historia medieval")
    excerpt_ids = [_opened_source(session, index) for index in range(12)]
    dispatch("studium_blueprint_store", {"sections": _eight_sections()}, session=session)
    half = " ".join(["densidad"] * 200)
    quantities = _excerpt(
        session,
        _source(session, "https://open.example/quantities"),
        "https://open.example/quantities",
        text="The stored quantities are 2 and 3.",
    )
    dispatch(
        "studium_paragraph_record",
        {"section": "tema-1", "role": "explanation", "text": half, "excerpts": [excerpt_ids[0], quantities]},
        session=session,
    )
    dispatch(
        "studium_paragraph_record",
        {"section": "tema-1", "role": "explanation", "text": half + " masa", "excerpts": [excerpt_ids[1]]},
        session=session,
    )
    computed = dispatch(
        "studium_computation_check",
        {"expression": "2+3", "result": 5, "section": "tema-1"},
        session=session,
    )
    assert computed["status"] == "replayed"
    nxt = dispatch("studium_book_next", {}, session=session)
    assert nxt["tool"] == "studium_problem_record"
    assert nxt["tool"] != "studium_render"
    assert nxt["arguments"]["section"] == "tema-1"
    assert "2+3" in nxt["reason"]
    assert nxt["ask_user"] is False
    assert nxt["released"] is False
    assert "ask the user" not in json.dumps(nxt).lower().replace("do not ask the user how to format the page.", "")


def test_book_next_asks_for_twelve_sources(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _topic(tmp_path, "historia", "Historia medieval")
    for index in range(11):
        _opened_source(session, index)
    dispatch("studium_blueprint_store", {"sections": _eight_sections()}, session=session)
    nxt = dispatch("studium_book_next", {}, session=session)
    assert nxt["tool"] == "studium_public_source_record"
    assert nxt["tool"] != "studium_render"
    assert "12" in nxt["reason"]
    assert nxt["ask_user"] is False
    assert nxt["released"] is False
    forbidden = root / "bibliography" / "public.jsonl"
    with forbidden.open("a", encoding="utf-8") as handle:
        handle.write(
            '{"id":"pirate-1","title":"Scan","url":"https://evil.example/book","kind":"pirate","license_forbids":true}\n'
        )
    still = dispatch("studium_book_next", {}, session=session)
    assert still["tool"] == "studium_public_source_record"
    assert "12" in still["reason"]
    local = tmp_path / "notes.pdf"
    local.write_bytes(b"%PDF-1.4\nnotes")
    imported = dispatch(
        "studium_source_intake",
        {"path": str(local), "origin": "user_uploaded"},
        session=session,
    )
    assert imported["status"] == "imported"
    ready = dispatch("studium_book_next", {}, session=session)
    assert ready["tool"] != "studium_public_source_record"
    assert ready["tool"] != "studium_render"
    assert ready["released"] is False
    assert "ask the user" not in json.dumps(ready).lower().replace("do not ask the user how to format the page.", "")


def test_book_next_rejects_a_rust_problem_outside_computer_science(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    fluids = _profiled_topic(tmp_path, "fluidos", "Mecánica de fluidos")
    _ready_outline(fluids)
    recorded = dispatch(
        "studium_problem_record",
        {
            "section": "tema-1",
            "prompt": "Compute the mass from the stored density.",
            "source_text": _RUST_SOURCE,
            "invocation": _RUST_INVOCATION,
        },
        session=fluids,
    )
    assert recorded["status"] == "recorded"
    assert recorded["problem"]["kind"] == "rust"
    assert recorded["problem"]["status_text"] == (
        "A Rust test cannot be the worked problem of a book that is not COMPUTER_SCIENCE. "
        "Three identical rustc runs are a reproducibility check, not an independent proof."
    )
    assert "three methods" not in json.dumps(recorded).lower()
    rendered = dispatch("studium_render", {}, session=fluids)
    tex = (tmp_path / "fluidos" / "latex" / "draft.tex").read_text(encoding="utf-8")
    assert "assert_eq!" not in tex
    assert "Compute the mass from the stored density." not in tex
    assert rendered["released"] is False
    nxt = dispatch("studium_book_next", {}, session=fluids)
    assert nxt["tool"] == "studium_problem_remove"
    assert nxt["tool"] != "studium_computation_check"
    assert nxt["tool"] != "studium_problem_check"
    assert nxt["tool"] != "studium_render"
    assert nxt["reason"] == _RUST_PROBLEM
    assert nxt["arguments"]["id"] == recorded["problem"]["id"]
    assert nxt["ask_user"] is False
    assert nxt["released"] is False

    code = _profiled_topic(tmp_path, "rust", "Rust")
    _ready_chapter(code)
    dispatch(
        "studium_problem_record",
        {
            "section": "tema-1",
            "prompt": "Show that a move ends the old owner.",
            "source_text": _RUST_SOURCE,
            "invocation": _RUST_INVOCATION,
        },
        session=code,
    )
    code_next = dispatch("studium_book_next", {}, session=code)
    assert code_next["tool"] == "studium_problem_check"
    assert code_next["reason"] != _RUST_PROBLEM
    assert "reproducibility check" in code_next["reason"]
    assert "not an independent proof" in code_next["reason"]
    assert "three methods" not in code_next["reason"].lower()
    assert code_next["tool"] != "studium_render"
    assert code_next["released"] is False


def test_book_next_refuses_a_chapter_with_one_explanation_section(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _topic(tmp_path, "fluidos", "Mecánica de fluidos", language="es")
    excerpts = [_opened_source(session, index) for index in range(12)]
    dispatch("studium_blueprint_store", {"sections": _eight_sections()}, session=session)
    explanation = "La explicación desarrolla el balance en el cuerpo del capítulo."
    dispatch(
        "studium_paragraph_record",
        {"section": "tema-1", "role": "explanation", "text": explanation, "excerpts": [excerpts[0]]},
        session=session,
    )
    nxt = dispatch("studium_book_next", {}, session=session)
    assert nxt["tool"] == "studium_paragraph_record"
    assert nxt["tool"] != "studium_render"
    assert nxt["arguments"]["role"] == "explanation"
    assert _TWO_SECTIONS in nxt["reason"]
    assert nxt["released"] is False
    dispatch(
        "studium_paragraph_record",
        {
            "section": "tema-1",
            "role": "explanation",
            "text": "La segunda explicación sigue el balance con otro desarrollo.",
            "excerpts": [excerpts[1]],
        },
        session=session,
    )
    rendered = dispatch("studium_render", {}, session=session)
    tex = (root / "latex" / "draft.tex").read_text(encoding="utf-8")
    assert r"\section{Explicación}" not in tex
    assert explanation in tex
    assert "La segunda explicación sigue el balance con otro desarrollo." in tex
    assert rendered["released"] is False
    still = dispatch("studium_book_next", {}, session=session)
    assert still["tool"] != "studium_render"


def test_computation_is_accepted_only_when_replayed(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _topic(tmp_path, "calculo", "Cálculo")
    dispatch(
        "studium_blueprint_store",
        {"sections": [{"id": "limits", "title": "Limits"}]},
        session=session,
    )
    source_id = _source(session, "https://open.example/calculus")
    excerpt_id = _excerpt(
        session,
        source_id,
        "https://open.example/calculus",
        text="A stored excerpt is data, not a source of authority. The quantity is 2.",
    )
    dispatch(
        "studium_paragraph_record",
        {"section": "limits", "text": "A limit is a draft tied to the opened page.", "excerpts": [excerpt_id]},
        session=session,
    )
    nxt = dispatch("studium_book_next", {}, session=session)
    assert nxt["tool"] == "studium_blueprint_store"
    assert nxt["tool"] != "studium_render"
    assert nxt["reason"] == _TOO_SHORT
    assert nxt["ask_user"] is False
    state_before = (root / ".studium" / "state.json").read_bytes()
    wrong = dispatch(
        "studium_computation_check",
        {"expression": "2 + 2", "result": 5, "section": "limits"},
        session=session,
    )
    assert wrong["accepted"] is False
    assert wrong["correct"] is False
    assert wrong["status"] == "mismatch"
    assert wrong["server_result"] == "4"
    assert wrong["claimed_result"] == "5"
    assert wrong["computation"]["expression"] == "2 + 2"
    assert wrong["released"] is False
    assert "verified" not in wrong["computation"]
    stored = (root / "problems" / "computations.jsonl").read_text(encoding="utf-8")
    assert '"expression":"2 + 2"' in stored or '"expression": "2 + 2"' in stored
    assert "5" in stored and "4" in stored
    rejected = dispatch(
        "studium_computation_check",
        {"expression": "__import__('os').system('echo no')", "result": 0},
        session=session,
    )
    assert rejected["accepted"] is False
    assert rejected["status"] != "replayed"
    right = dispatch(
        "studium_computation_check",
        {"expression": "2 + 2", "result": 4, "section": "limits"},
        session=session,
    )
    assert right["status"] == "replayed"
    assert right["accepted"] is True
    assert right["correct"] is True
    assert right["server_result"] == "4"
    assert right["computation"]["corroboration"] == "replayed"
    assert right["computation"]["classification"] == "PENDING"
    assert right["computation"]["status"] == "replayed"
    assert "verified" not in json.dumps(right)
    assert right["released"] is False
    monkeypatch.setattr("studium.authoring.computation.evaluate", lambda _expression: Fraction(9))
    replayed = dispatch("studium_computation_check", {"id": right["computation"]["id"]}, session=session)
    assert replayed["accepted"] is False
    assert replayed["correct"] is False
    assert replayed["server_result"] == "9"
    assert replayed["status"] == "mismatch"
    assert "verified" not in json.dumps(replayed)
    assert (root / ".studium" / "state.json").read_bytes() == state_before


def test_two_independent_excerpts_are_two_witnesses(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, _root = _topic(tmp_path, "historia", "Historia medieval")
    dispatch(
        "studium_blueprint_store",
        {"sections": [{"id": "tema-1", "title": "Origenes"}]},
        session=session,
    )
    first = _source(session, "https://open.example/one")
    second = _source(session, "https://open.example/two")
    left = _excerpt(session, first, "https://open.example/one")
    right = _excerpt(session, second, "https://open.example/two")
    same = _excerpt(session, first, "https://open.example/one-again", text="A second passage from the same source.")
    claim = dispatch(
        "studium_claim_record",
        {"text": "Two opened pages agree on this draft sentence.", "excerpts": [left, right]},
        session=session,
    )
    assert claim["claim"]["status"] == "draft"
    assert claim["claim"]["corroboration"] == "two_witnesses"
    assert "verified" not in claim["claim"]
    alone = dispatch(
        "studium_claim_record",
        {"text": "One source repeated is still a draft.", "excerpts": [left, same]},
        session=session,
    )
    assert alone["claim"]["status"] == "draft"
    assert "corroboration" not in alone["claim"]
    assert "verified" not in alone["claim"]
    witnessed = dispatch(
        "studium_problem_record",
        {
            "section": "tema-1",
            "prompt": "What do the two pages report?",
            "expected": "4",
            "excerpts": [left, right],
        },
        session=session,
    )
    assert witnessed["problem"]["status"] == "two_witnesses"
    assert witnessed["problem"]["corroboration"] == "two_witnesses"
    assert witnessed["problem"]["correct"] is False
    assert "verified" not in witnessed["problem"]
    repeated = dispatch(
        "studium_problem_record",
        {
            "section": "tema-1",
            "prompt": "What does the same page report twice?",
            "expected": "4",
            "excerpts": [left, same],
        },
        session=session,
    )
    assert repeated["problem"]["status"] == "unchecked"
    assert "corroboration" not in repeated["problem"]
    checked = dispatch("studium_problem_check", {"id": witnessed["problem"]["id"]}, session=session)
    assert checked["status"] == "two_witnesses"
    assert checked["checked"] is False
    assert checked["problem"]["correct"] is False
    assert checked["released"] is False


def test_verify_still_refuses_release(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _topic(tmp_path, "historia", "Historia medieval")
    source_id = _source(session, "https://open.example/historia")
    excerpt_id = _excerpt(session, source_id, "https://open.example/historia")
    dispatch(
        "studium_blueprint_store",
        {"sections": [{"id": "tema-1", "title": "Origenes"}]},
        session=session,
    )
    dispatch(
        "studium_paragraph_record",
        {"section": "tema-1", "text": "A draft paragraph is not a release.", "excerpts": [excerpt_id]},
        session=session,
    )
    state_before = (root / ".studium" / "state.json").read_bytes()
    verify = dispatch("studium_verify", {"mode": "full"}, session=session)
    assert verify["applied"] is False
    assert verify["released"] is False
    assert verify["project_state"] != "RELEASED"
    assert any(item["message"] == "gate release is not implemented" for item in verify["blockers"])
    assert (root / ".studium" / "state.json").read_bytes() == state_before
    rendered = dispatch("studium_render", {}, session=session)
    assert rendered["released"] is False
    done = dispatch("studium_book_next", {}, session=session)
    assert done["tool"] == "studium_blueprint_store"
    assert done["tool"] != "studium_render"
    assert done["reason"] == _TOO_SHORT
    assert done["ask_user"] is False
    assert done["released"] is False
    assert "ask the user" not in json.dumps(done).lower().replace("do not ask the user how to format the page.", "")
    assert json.loads(state_before)["state"] != "RELEASED"
    assert (root / ".studium" / "state.json").read_bytes() == state_before


def test_one_written_chapter_and_one_empty_chapter_is_not_render(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _topic(tmp_path, "historia", "Historia medieval")
    excerpts = [_opened_source(session, index) for index in range(12)]
    sections = [
        {"id": "historia", "title": "Historia"},
        {"id": "sql", "title": "SQL"},
        *[{"id": f"tema-{index}", "title": f"Tema {index}"} for index in range(3, 9)],
    ]
    dispatch("studium_blueprint_store", {"sections": sections}, session=session)
    half = " ".join(["density"] * 200)
    dispatch(
        "studium_paragraph_record",
        {"section": "historia", "role": "purpose", "text": "This chapter opens the history.", "excerpts": [excerpts[0]]},
        session=session,
    )
    dispatch(
        "studium_paragraph_record",
        {"section": "historia", "role": "explanation", "text": half, "excerpts": [excerpts[0]]},
        session=session,
    )
    dispatch(
        "studium_paragraph_record",
        {"section": "historia", "role": "explanation", "text": half + " continued", "excerpts": [excerpts[1]]},
        session=session,
    )
    dispatch(
        "studium_paragraph_record",
        {"section": "historia", "role": "consejo", "text": "Keep the later chapters in the plan.", "excerpts": [excerpts[0]]},
        session=session,
    )
    dispatch(
        "studium_paragraph_record",
        {"section": "historia", "role": "self_check", "text": "Name the next unwritten chapter.", "excerpts": [excerpts[0]]},
        session=session,
    )
    witnessed = dispatch(
        "studium_problem_record",
        {
            "section": "historia",
            "prompt": "What do the two pages report?",
            "expected": "4",
            "excerpts": [excerpts[2], excerpts[3]],
        },
        session=session,
    )
    assert witnessed["problem"]["status"] == "two_witnesses"
    nxt = dispatch("studium_book_next", {}, session=session)
    assert nxt["tool"] == "studium_paragraph_record"
    assert nxt["tool"] != "studium_render"
    assert nxt["arguments"]["section"] == "sql"
    assert nxt["reason"] == (
        "Write the next unwritten chapter: SQL. "
        "The book is incomplete while SQL has no paragraphs. "
        "Do not render it as finished. "
        "Missing contract pieces: paragraphs, two explanation sections, 400 words of explanation, "
        "lead, consejo, worked problem, autoficha. "
        "Do not render. Do not hand the draft over. "
        "A partial PDF is not a reason to stop."
    )
    assert nxt["released"] is False
    rendered = dispatch("studium_render", {}, session=session)
    tex = (root / "latex" / "draft.tex").read_text(encoding="utf-8")
    body = tex.split(r"\appendix", 1)[0]
    assert r"\chapter{SQL}" not in tex
    assert "SQL" not in body
    assert "SQL: not written yet" in tex
    assert tex.index("Study plan") < tex.index("SQL: not written yet")
    assert rendered["status"] == "incomplete"
    assert rendered["message"] == "The book is incomplete. Write the next unwritten chapter: SQL."
    assert rendered["released"] is False
    assert rendered["project_state"] != "RELEASED"
    again = dispatch("studium_book_next", {}, session=session)
    assert again["tool"] != "studium_render"
    assert again["reason"] == nxt["reason"]


def test_unwritten_section_does_not_get_a_render_or_a_stop(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, _root = _topic(tmp_path, "historia", "Historia medieval")
    for index in range(12):
        _opened_source(session, index)
    dispatch(
        "studium_blueprint_store",
        {
            "sections": [
                {"id": "historia", "title": "Historia"},
                {"id": "sql", "title": "SQL"},
                *[{"id": f"tema-{index}", "title": f"Tema {index}"} for index in range(3, 9)],
            ]
        },
        session=session,
    )
    pieces = (
        "paragraphs",
        "two explanation sections",
        "400 words of explanation",
        "lead",
        "consejo",
        "worked problem",
        "autoficha",
    )
    for _ in range(6):
        nxt = dispatch("studium_book_next", {}, session=session)
        _assert_writes_the_chapter(nxt, "Historia")
        assert nxt["arguments"]["section"] == "historia"
        for piece in pieces:
            assert piece in nxt["reason"]
    rendered = dispatch("studium_render", {}, session=session)
    assert rendered["released"] is False
    assert rendered["status"] == "incomplete"
    after = dispatch("studium_book_next", {}, session=session)
    _assert_writes_the_chapter(after, "Historia")
    assert after["arguments"]["section"] == "historia"
    status = dispatch("studium_project_status", {}, session=session)
    action = str(status["next_action"])
    assert "Write the next unfinished chapter: Historia." in action
    assert "Missing contract pieces:" in action
    assert "then render" not in action
    assert "Do not render." in action
    assert "Do not hand the draft over." in action
    assert "A partial PDF is not a reason to stop." in action
    assert status["state"] != "RELEASED"


def test_contract_complete_book_may_render_once_and_stays_unreleased(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _topic(tmp_path, "historia", "Historia medieval")
    excerpts = [_opened_source(session, index) for index in range(12)]
    dispatch("studium_blueprint_store", {"sections": _eight_sections()}, session=session)
    _fill_contract(session, excerpts)
    seen: list[str | None] = []
    rendered_step: dict[str, object] | None = None
    last: dict[str, object] = {}
    for _ in range(24):
        nxt = dispatch("studium_book_next", {}, session=session)
        last = nxt
        assert nxt["released"] is False
        assert nxt["ask_user"] is False
        seen.append(nxt["tool"] if isinstance(nxt["tool"], str) else None)
        if nxt["tool"] is None:
            raise AssertionError(f"stopped before render: {nxt['reason']}")
        if nxt["tool"] == "studium_render":
            rendered_step = nxt
            break
        result = _perform_next(session, nxt, excerpts)
        assert result.get("released") is False
        if nxt["tool"] == "studium_book_review":
            assert result["audit_passed"] is True, result.get("reasons")
    assert rendered_step is not None, f"book_next did not reach render: {last.get('tool')} {last.get('reason')}"
    assert seen[:8] == ["studium_audit_record"] * 8
    assert seen[8:11] == ["studium_contradiction_scan", "studium_book_review", "studium_render"]
    reason = str(rendered_step["reason"])
    assert reason == (
        "Render the DRAFT once. Do not stop mid-book for a preview. Do not request release."
    )
    assert "hand" not in reason.lower()
    rendered = dispatch("studium_render", {}, session=session)
    assert rendered["released"] is False
    assert rendered["project_state"] != "RELEASED"
    assert json.loads((root / ".studium" / "state.json").read_text(encoding="utf-8"))["state"] != "RELEASED"
    done = dispatch("studium_book_next", {}, session=session)
    assert done["tool"] is None
    assert done["released"] is False
    assert done["reason"] == "The DRAFT was rendered once. Do not request release."
    assert "preview" not in str(done["reason"]).lower()
    assert "hand" not in str(done["reason"]).lower()
    status = dispatch("studium_project_status", {}, session=session)
    assert "render once" in str(status["next_action"])
    assert "Do not stop mid-book for a preview." in str(status["next_action"])
    assert status["state"] != "RELEASED"


def _assert_writes_the_chapter(nxt: dict[str, object], title: str) -> None:
    assert nxt["tool"] == "studium_paragraph_record"
    assert nxt["tool"] != "studium_render"
    assert nxt["released"] is False
    reason = str(nxt["reason"])
    assert title in reason
    assert "Render the DRAFT" not in reason
    assert "can be handed" not in reason.lower()
    assert "leave the gap" not in reason.lower()
    assert "preview" not in reason.lower()
    assert "Empty sections stay gaps" not in reason
    assert "you can stop" not in reason.lower()
    blob = json.dumps(nxt).lower().replace("do not ask the user how to format the page.", "")
    assert "ask the user" not in blob


def _fill_contract(session, excerpts: list[str]) -> None:
    sentence = "The chapter teaches this point from the opened page in the writer's own words."
    explanation = " ".join([sentence] * 16)
    lead = " ".join([sentence] * 4)
    advice = " ".join(["Keep the later point tied to the opened page and write it in the chapter's own sentences."] * 3)
    for index in range(1, 9):
        section = f"tema-{index}"
        dispatch(
            "studium_paragraph_record",
            {"section": section, "role": "purpose", "text": lead, "excerpts": [excerpts[0]]},
            session=session,
        )
        dispatch(
            "studium_paragraph_record",
            {"section": section, "role": "explanation", "text": explanation, "excerpts": [excerpts[0]]},
            session=session,
        )
        dispatch(
            "studium_paragraph_record",
            {"section": section, "role": "explanation", "text": explanation + " The next point follows.", "excerpts": [excerpts[1]]},
            session=session,
        )
        dispatch(
            "studium_paragraph_record",
            {"section": section, "role": "consejo", "text": advice, "excerpts": [excerpts[0]]},
            session=session,
        )
        dispatch(
            "studium_paragraph_record",
            {"section": section, "role": "self_check", "text": "Name the point the opened page supports in your own words.", "excerpts": [excerpts[0]]},
            session=session,
        )
        witnessed = dispatch(
            "studium_problem_record",
            {
                "section": section,
                "prompt": "What do the two pages report?",
                "expected": "4",
                "excerpts": [excerpts[0], excerpts[1]],
            },
            session=session,
        )
        assert witnessed["problem"]["status"] == "two_witnesses"


def _perform_next(session, nxt: dict[str, object], excerpts: list[str]) -> dict[str, object]:
    tool = str(nxt["tool"])
    arguments = dict(nxt["arguments"]) if isinstance(nxt["arguments"], dict) else {}
    if tool == "studium_audit_record":
        arguments["kind"] = "historical"
        arguments["excerpts"] = excerpts[:2]
    result = dispatch(tool, arguments, session=session)
    if tool == "studium_audit_record":
        assert result["status"] == "recorded", result
    return result


def test_client_instructions_draft_without_asking_or_releasing():
    instructions = handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})["result"]["instructions"]
    assert "Call studium_book_next and perform that tool call." in instructions
    assert "Do not leave a gap." in instructions
    assert "or leave the gap." not in instructions
    assert "do not block render" not in instructions.lower()
    assert "studium_computation_check" in instructions
    assert "Do not request release." in instructions
    assert "Refuse pirate copies and conflicting citations." in instructions
    assert "Do not ask the user what to do next." in instructions
    assert "two_witnesses, not verified and not absolute truth." in instructions
    assert "Writing is still not available." in instructions
    assert "Do not advance into authoring." in instructions
    assert "Record only a source whose URL you actually opened." in instructions
    assert "must not browse the web" not in instructions
    assert "This version has no tool for that." not in instructions


def _topic(tmp_path, slug: str, topic: str, language: str | None = None):
    session = open_workspace(str(tmp_path))
    payload: dict[str, object] = {"slug": slug, "topic": topic}
    if language is not None:
        payload["language"] = language
    assert dispatch("studium_project_create", payload, session=session)["status"] == "created"
    return session, tmp_path / slug


def _profiled_topic(tmp_path, slug: str, topic: str):
    session, _root = _topic(tmp_path, slug, topic)
    return session


def _ready_outline(session) -> None:
    for index in range(12):
        _opened_source(session, index)
    dispatch("studium_blueprint_store", {"sections": _eight_sections()}, session=session)


def _ready_chapter(session) -> None:
    excerpts = []
    for index in range(12):
        excerpts.append(_opened_source(session, index))
    dispatch("studium_blueprint_store", {"sections": _eight_sections()}, session=session)
    half = " ".join(["owner"] * 200)
    dispatch(
        "studium_paragraph_record",
        {"section": "tema-1", "role": "purpose", "text": "This section shows ownership.", "excerpts": [excerpts[0]]},
        session=session,
    )
    dispatch(
        "studium_paragraph_record",
        {"section": "tema-1", "role": "explanation", "text": half, "excerpts": [excerpts[0]]},
        session=session,
    )
    dispatch(
        "studium_paragraph_record",
        {"section": "tema-1", "role": "explanation", "text": half + " move", "excerpts": [excerpts[1]]},
        session=session,
    )
    dispatch(
        "studium_paragraph_record",
        {"section": "tema-1", "role": "consejo", "text": "Name the owner before the move.", "excerpts": [excerpts[0]]},
        session=session,
    )
    dispatch(
        "studium_paragraph_record",
        {"section": "tema-1", "role": "self_check", "text": "State who owns the value.", "excerpts": [excerpts[0]]},
        session=session,
    )


def _source(session, url: str) -> str:
    recorded = dispatch(
        "studium_public_source_record",
        {"title": "Open page", "url": url},
        session=session,
    )
    assert recorded["status"] == "recorded"
    return str(recorded["candidate"]["id"])


def _excerpt(session, source_id: str, url: str, text: str = _PASSAGE) -> str:
    recorded = dispatch(
        "studium_excerpt_record",
        {"source_id": source_id, "url": url, "text": text},
        session=session,
    )
    assert recorded["status"] == "recorded"
    return str(recorded["excerpt"]["id"])


def _eight_sections() -> list[dict[str, str]]:
    return [{"id": f"tema-{index}", "title": f"Tema {index}"} for index in range(1, 9)]


def _opened_source(session, index: int) -> str:
    url = f"https://open.example/page-{index}"
    source_id = _source(session, url)
    return _excerpt(session, source_id, url, text=f"Opened page {index} states a stored fact about the topic.")


def _until_tool(session, tool: str | None) -> dict[str, object]:
    last: dict[str, object] = {}
    for _ in range(12):
        nxt = dispatch("studium_book_next", {}, session=session)
        assert nxt["ask_user"] is False
        assert nxt["released"] is False
        assert "ask the user" not in json.dumps(nxt).lower().replace("do not ask the user how to format the page.", "")
        last = nxt
        if nxt["tool"] == "studium_render" and tool != "studium_render":
            assert dispatch("studium_render", {}, session=session)["released"] is False
            continue
        if nxt["tool"] == tool:
            return nxt
    raise AssertionError(f"book_next did not reach {tool}: {last.get('tool')}")


def _explode(*_args, **_kwargs):
    raise AssertionError("must not fetch")
