"""Audit cites a tool result. A contradicted number is rejected. Review does not release."""

import json

from studium.mcp.server import dispatch, open_workspace, tool_names

_PASSAGE = "The density is 2."
_TEACH = (
    "This explanation teaches the stored quantity so a reader can follow the derivation, "
    "the comparison, and the later problem without treating the model as a source of truth."
)


def test_audit_without_a_tool_result_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _topic(tmp_path, "historia", "Historia medieval")
    _section(session)
    source_id = _source(session, "https://open.example/one")
    excerpt_id = _excerpt(session, source_id, "https://open.example/one")
    paragraph = _paragraph(session, "tema-1", "Mass is conserved.", [excerpt_id])
    state_before = (root / ".studium" / "state.json").read_bytes()
    text_before = (root / "draft" / "paragraphs.jsonl").read_text(encoding="utf-8")
    refused = dispatch(
        "studium_audit_record",
        {"target": paragraph, "kind": "historical", "note": "the auditor agrees"},
        session=session,
    )
    assert refused["status"] == "audit.opinion_rejected"
    assert refused["message"] == "a second model opinion is not a source of truth"
    assert refused["prose_added"] is False
    assert refused["released"] is False
    assert "verified" not in json.dumps(refused)
    assert not (root / "draft" / "audits.jsonl").exists()
    assert (root / "draft" / "paragraphs.jsonl").read_text(encoding="utf-8") == text_before
    assert (root / ".studium" / "state.json").read_bytes() == state_before
    assert json.loads(state_before)["state"] != "RELEASED"
    assert {"studium_audit_record", "studium_contradiction_scan", "studium_book_review"} <= set(tool_names())


def test_replayed_computation_can_be_audited(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _topic(tmp_path, "calculo", "Cálculo")
    _section(session, section_id="limits", title="Limits")
    source_id = _source(session, "https://open.example/calculus")
    excerpt_id = _excerpt(session, source_id, "https://open.example/calculus", text="A limit is tied to the opened page.")
    text = "A replayed sum is the server value. The explanation stays tied to that check and adds no second opinion."
    paragraph = _paragraph(session, "limits", text, [excerpt_id])
    state_before = (root / ".studium" / "state.json").read_bytes()
    computed = dispatch(
        "studium_computation_check",
        {"expression": "2 + 2", "result": 4, "section": "limits"},
        session=session,
    )
    assert computed["status"] == "replayed"
    assert computed["correct"] is True
    audited = dispatch(
        "studium_audit_record",
        {"target": paragraph, "kind": "formula", "computation": computed["computation"]["id"]},
        session=session,
    )
    assert audited["status"] == "recorded"
    assert audited["prose_added"] is False
    assert audited["audit"]["prose_added"] is False
    assert audited["audit"]["evidence"]["computation_result"] == "replayed"
    assert audited["released"] is False
    assert audited["applied"] is False
    assert "verified" not in json.dumps(audited)
    assert text in (root / "draft" / "paragraphs.jsonl").read_text(encoding="utf-8")
    assert (root / ".studium" / "state.json").read_bytes() == state_before
    assert json.loads(state_before)["state"] != "RELEASED"


def test_chapter_that_contradicts_a_stored_number_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _topic(tmp_path, "historia", "Historia medieval")
    _section(session)
    left, right = _two_excerpts(session)
    text = f"The density is 9. {_TEACH}"
    paragraph = _paragraph(session, "tema-1", text, [left, right])
    state_before = (root / ".studium" / "state.json").read_bytes()
    refused = dispatch(
        "studium_audit_record",
        {"target": "tema-1", "kind": "scientific", "excerpts": [left, right]},
        session=session,
    )
    assert refused["status"] == "audit.rejected"
    assert "contradicts a stored number" in refused["message"]
    assert "density" in refused["message"]
    assert refused["prose_added"] is False
    assert refused["released"] is False
    assert "verified" not in json.dumps(refused)
    assert not (root / "draft" / "audits.jsonl").exists()
    stored = (root / "draft" / "paragraphs.jsonl").read_text(encoding="utf-8")
    assert paragraph in stored
    assert "The density is 9." in stored
    assert (root / ".studium" / "state.json").read_bytes() == state_before
    assert json.loads(state_before)["state"] != "RELEASED"


def test_contradiction_blocks_review(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _topic(tmp_path, "historia", "Historia medieval")
    _section(session)
    left, right = _two_excerpts(session)
    _paragraph(session, "tema-1", f"The density is 2. {_TEACH}", [left])
    _paragraph(session, "tema-1", f"The density is 9. {_TEACH}", [right])
    state_before = (root / ".studium" / "state.json").read_bytes()
    scanned = dispatch("studium_contradiction_scan", {}, session=session)
    assert scanned["status"] == "ok"
    assert scanned["open_count"] >= 1
    assert scanned["released"] is False
    assert any(item["quantity"] == "density" and set(item["values"]) >= {"2", "9"} for item in scanned["contradictions"])
    reviewed = dispatch("studium_book_review", {}, session=session)
    assert reviewed["status"] == "blocked"
    assert reviewed["audit_passed"] is False
    assert reviewed["released"] is False
    assert reviewed["applied"] is False
    assert any("contradiction" in reason for reason in reviewed["reasons"])
    assert (root / ".studium" / "state.json").read_bytes() == state_before
    assert json.loads(state_before)["state"] != "RELEASED"


def test_one_sentence_chapter_is_too_short(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _topic(tmp_path, "historia", "Historia medieval")
    _section(session)
    source_id = _source(session, "https://open.example/one")
    excerpt_id = _excerpt(session, source_id, "https://open.example/one")
    _paragraph(session, "tema-1", "Mass is conserved.", [excerpt_id])
    state_before = (root / ".studium" / "state.json").read_bytes()
    reviewed = dispatch("studium_book_review", {}, session=session)
    assert reviewed["audit_passed"] is False
    assert reviewed["released"] is False
    assert reviewed["applied"] is False
    assert any("too short" in reason for reason in reviewed["reasons"])
    assert reviewed["project_state"] != "RELEASED"
    assert (root / ".studium" / "state.json").read_bytes() == state_before


def test_multiparagraph_chapter_renders_in_book_shape(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _topic(tmp_path, "historia", "Historia medieval")
    dispatch(
        "studium_blueprint_store",
        {"sections": [{"id": "tema-1", "title": "Conservation of mass"}]},
        session=session,
    )
    left, right = _two_excerpts(session)
    first = f"The density is 2. {_TEACH}"
    second = f"The density equals 2. {_TEACH}"
    _paragraph(session, "tema-1", first, [left, right], role="purpose")
    _paragraph(session, "tema-1", second, [left, right], role="explanation")
    _paragraph(session, "tema-1", "Restate the stored density in your own words.", [left], role="self_check")
    claim = dispatch(
        "studium_claim_record",
        {"text": "The density is 2.", "excerpts": [left, right], "section": "tema-1"},
        session=session,
    )
    assert claim["claim"]["corroboration"] == "two_witnesses"
    problem = dispatch(
        "studium_problem_record",
        {
            "section": "tema-1",
            "prompt": "What is the stored density?",
            "expected": "2",
            "excerpts": [left, right],
        },
        session=session,
    )
    assert problem["problem"]["status"] == "two_witnesses"
    audited = dispatch(
        "studium_audit_record",
        {"target": "tema-1", "kind": "scientific", "excerpts": [left, right]},
        session=session,
    )
    assert audited["status"] == "recorded"
    assert audited["prose_added"] is False
    state_before = (root / ".studium" / "state.json").read_bytes()
    scanned = dispatch("studium_contradiction_scan", {}, session=session)
    assert scanned["open_count"] == 0
    reviewed = dispatch("studium_book_review", {}, session=session)
    assert reviewed["status"] == "audit_passed"
    assert reviewed["audit_passed"] is True
    assert reviewed["released"] is False
    assert reviewed["applied"] is False
    assert "not RELEASED" in reviewed["message"]
    rendered = dispatch("studium_render", {}, session=session)
    tex = (root / "latex" / "draft.tex").read_text(encoding="utf-8")
    assert r"\documentclass{book}" in tex
    preface = tex.index("Preface")
    how_to = tex.index("How to use this book")
    contents = tex.index(r"\tableofcontents")
    chapter = tex.index(r"\chapter{Conservation of mass}")
    purpose = tex.index(r"\section{What this section is for}")
    explanation = tex.index(r"\section{Explanation}")
    worked = tex.index(r"\section{Worked problem}")
    self_check = tex.index(r"\section{Self-check}")
    audited_line = tex.index("What was audited:")
    problems = tex.index("Worked problems")
    notation = tex.index("Notation")
    formula = tex.index("Formula sheet")
    solutions = tex.index("Solutions")
    source_audit = tex.index("Source audit")
    study = tex.index("Study plan")
    bibliography = tex.index("thebibliography")
    assert preface < how_to < contents < chapter < purpose < explanation < worked < self_check < audited_line
    assert audited_line < problems < notation < formula < solutions < source_audit < study < bibliography
    assert explanation < tex.index(second) < worked
    assert purpose < tex.index(first) < explanation
    assert "What is the stored density?" in tex
    assert "Restate the stored density" in tex
    assert audited["audit"]["id"] in tex
    assert "The density is 2." in tex
    assert r"\part{Problems}" in tex
    assert rendered["released"] is False
    assert rendered["project_state"] != "RELEASED"
    assert (root / ".studium" / "state.json").read_bytes() == state_before


def test_topic_book_without_a_guide_builds_a_study_outline(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, _root = _topic(tmp_path, "historia", "Historia medieval")
    source_id = _source(session, "https://open.example/one")
    _excerpt(session, source_id, "https://open.example/one")
    nxt = dispatch("studium_book_next", {}, session=session)
    assert nxt["tool"] == "studium_blueprint_store"
    identifiers = [item["id"] for item in nxt["arguments"]["sections"]]
    for required in ("roadmap", "foundations", "topic", "worked-problems", "self-check", "formula-sheet"):
        assert required in identifiers
    assert "source audit" in nxt["reason"]
    assert nxt["ask_user"] is False
    assert nxt["released"] is False
    assert "ask the user" not in json.dumps(nxt).lower()


def _topic(tmp_path, slug: str, topic: str):
    session = open_workspace(str(tmp_path))
    assert dispatch("studium_project_create", {"slug": slug, "topic": topic}, session=session)["status"] == "created"
    return session, tmp_path / slug


def _section(session, section_id: str = "tema-1", title: str = "Origenes") -> None:
    assert (
        dispatch(
            "studium_blueprint_store",
            {"sections": [{"id": section_id, "title": title}]},
            session=session,
        )["status"]
        == "recorded"
    )


def _source(session, url: str) -> str:
    recorded = dispatch("studium_public_source_record", {"title": "Open page", "url": url}, session=session)
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


def _two_excerpts(session) -> tuple[str, str]:
    left_source = _source(session, "https://open.example/one")
    right_source = _source(session, "https://open.example/two")
    return (
        _excerpt(session, left_source, "https://open.example/one"),
        _excerpt(session, right_source, "https://open.example/two"),
    )


def _paragraph(session, section: str, text: str, excerpts: list[str], role: str | None = None) -> str:
    arguments: dict[str, object] = {"section": section, "text": text, "excerpts": excerpts}
    if role is not None:
        arguments["role"] = role
    recorded = dispatch("studium_paragraph_record", arguments, session=session)
    assert recorded["status"] == "recorded"
    return str(recorded["paragraph"]["id"])


def _explode(*_args, **_kwargs):
    raise AssertionError("must not fetch")
