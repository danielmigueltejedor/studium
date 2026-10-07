"""The next draft step, replayed calculations, and a verify that still refuses release."""

import json
from fractions import Fraction

from studium.mcp.server import dispatch, handle, open_workspace, tool_names

_PASSAGE = "A stored excerpt is data, not a source of authority."


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
    assert "ask the user" not in json.dumps(nxt).lower()
    assert "studium_book_next" in tool_names()
    assert "studium_computation_check" in tool_names()


def test_book_next_moves_on_when_a_section_is_filled(tmp_path, monkeypatch):
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
    nxt = dispatch("studium_book_next", {}, session=session)
    assert nxt["tool"] == "studium_paragraph_record"
    assert nxt["arguments"]["section"] == "tema-1"
    assert nxt["arguments"]["excerpts"] == [excerpt_id]
    assert nxt["ask_user"] is False
    assert "ask the user" not in json.dumps(nxt).lower()
    recorded = dispatch(
        "studium_paragraph_record",
        {
            "section": "tema-1",
            "text": "The opened excerpt is the only support for this draft paragraph.",
            "excerpts": [excerpt_id],
        },
        session=session,
    )
    assert recorded["status"] == "recorded"
    assert recorded["paragraph"]["status"] == "draft"
    nxt = dispatch("studium_book_next", {}, session=session)
    assert nxt["tool"] == "studium_paragraph_replace"
    assert nxt["arguments"]["id"] == recorded["paragraph"]["id"]
    assert "too short" in nxt["reason"]
    assert nxt["ask_user"] is False
    assert nxt["released"] is False
    assert "ask the user" not in json.dumps(nxt).lower()
    rendered = _until_tool(session, "studium_render")
    assert rendered["arguments"].get("section") != "tema-1"
    assert "tema-2" in rendered["reason"]
    assert "tema-1" not in rendered["reason"]
    assert rendered["released"] is False
    assert "ask the user" not in json.dumps(rendered).lower()


def test_computation_is_accepted_only_when_replayed(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _topic(tmp_path, "calculo", "Cálculo")
    dispatch(
        "studium_blueprint_store",
        {"sections": [{"id": "limits", "title": "Limits"}]},
        session=session,
    )
    source_id = _source(session, "https://open.example/calculus")
    excerpt_id = _excerpt(session, source_id, "https://open.example/calculus")
    dispatch(
        "studium_paragraph_record",
        {"section": "limits", "text": "A limit is a draft tied to the opened page.", "excerpts": [excerpt_id]},
        session=session,
    )
    nxt = dispatch("studium_book_next", {}, session=session)
    assert nxt["tool"] == "studium_computation_check"
    assert nxt["arguments"]["section"] == "limits"
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
    done = _until_tool(session, None)
    assert done["tool"] is None
    assert done["ask_user"] is False
    assert done["released"] is False
    assert "Do not request release." in done["reason"]
    assert "ask the user" not in json.dumps(done).lower()
    assert json.loads(state_before)["state"] != "RELEASED"
    assert (root / ".studium" / "state.json").read_bytes() == state_before


def test_client_instructions_draft_without_asking_or_releasing():
    instructions = handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})["result"]["instructions"]
    assert "Call studium_book_next and perform that tool call." in instructions
    assert "or leave the gap." in instructions
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


def _topic(tmp_path, slug: str, topic: str):
    session = open_workspace(str(tmp_path))
    assert dispatch("studium_project_create", {"slug": slug, "topic": topic}, session=session)["status"] == "created"
    return session, tmp_path / slug


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


def _until_tool(session, tool: str | None) -> dict[str, object]:
    last: dict[str, object] = {}
    for _ in range(12):
        nxt = dispatch("studium_book_next", {}, session=session)
        assert nxt["ask_user"] is False
        assert nxt["released"] is False
        assert "ask the user" not in json.dumps(nxt).lower()
        last = nxt
        if nxt["tool"] == "studium_render" and tool != "studium_render":
            assert dispatch("studium_render", {}, session=session)["released"] is False
            continue
        if nxt["tool"] == tool:
            return nxt
    raise AssertionError(f"book_next did not reach {tool}: {last.get('tool')}")


def _explode(*_args, **_kwargs):
    raise AssertionError("must not fetch")
