"""Audit cites a tool result. A contradicted number is rejected. Review does not release."""

import json
import re

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
    excerpt_id = _excerpt(
        session,
        source_id,
        "https://open.example/calculus",
        text="A limit is tied to the opened page. The quantity is 2.",
    )
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
    evidence = audited["audit"]["evidence"]
    assert evidence["computation_result"] == "COMPUTATION_REPRODUCED"
    assert evidence["mathematically_verified"] is False
    assert evidence["academically_reviewed"] is False
    assert evidence["computation_result"] not in {"mathematically_verified", "academically_reviewed"}
    assert audited["released"] is False
    assert audited["applied"] is False
    assert '"mathematically_verified": true' not in json.dumps(audited)
    assert '"academically_reviewed": true' not in json.dumps(audited)
    assert text in (root / "draft" / "paragraphs.jsonl").read_text(encoding="utf-8")
    assert (root / ".studium" / "state.json").read_bytes() == state_before
    assert json.loads(state_before)["state"] != "RELEASED"


def test_changed_paragraph_or_excerpt_drops_the_audit(tmp_path, monkeypatch):
    import hashlib

    from studium.authoring.audit import audited_paragraph_ids
    from studium.storage.records import EXCERPTS, append_jsonl, read_jsonl

    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _topic(tmp_path, "historia", "Historia medieval")
    _section(session)
    left, right = _two_excerpts(session)
    first = f"The density is 2. {_TEACH}"
    second = f"The density equals 2. {_TEACH}"
    paragraph = _paragraph(session, "tema-1", first, [left, right])
    other = _paragraph(session, "tema-1", second, [left, right])
    audited = dispatch(
        "studium_audit_record",
        {"target": "tema-1", "kind": "scientific", "excerpts": [left, right]},
        session=session,
    )
    assert audited["status"] == "recorded"
    assert {paragraph, other} <= audited_paragraph_ids(root)
    state_before = (root / ".studium" / "state.json").read_bytes()
    replaced = dispatch(
        "studium_paragraph_replace",
        {
            "id": paragraph,
            "text": f"The density is 2. {_TEACH} The later sentence still uses the stored quantity.",
            "excerpts": [left, right],
        },
        session=session,
    )
    assert replaced["status"] == "replaced"
    assert replaced["paragraph"]["id"] == paragraph
    assert paragraph not in audited_paragraph_ids(root)
    assert other in audited_paragraph_ids(root)
    reviewed = dispatch("studium_book_review", {}, session=session)
    assert reviewed["audit_passed"] is False
    assert reviewed["released"] is False
    assert any(paragraph in reason for reason in reviewed["reasons"])
    assert (root / ".studium" / "state.json").read_bytes() == state_before
    assert json.loads(state_before)["state"] != "RELEASED"

    session_b, root_b = _topic(tmp_path, "historia-b", "Historia medieval")
    _section(session_b)
    left_b, right_b = _two_excerpts(session_b)
    kept = _paragraph(session_b, "tema-1", first, [left_b, right_b])
    _paragraph(session_b, "tema-1", second, [left_b, right_b])
    assert (
        dispatch(
            "studium_audit_record",
            {"target": "tema-1", "kind": "scientific", "excerpts": [left_b, right_b]},
            session=session_b,
        )["status"]
        == "recorded"
    )
    assert kept in audited_paragraph_ids(root_b)
    state_b = (root_b / ".studium" / "state.json").read_bytes()
    current = next(row for row in read_jsonl(root_b / EXCERPTS) if row.get("id") == left_b)
    changed = dict(current)
    changed["text"] = str(current.get("text")) + " The opened page now adds another sentence."
    changed["text_sha256"] = hashlib.sha256(b"excerpt-changed").hexdigest()
    append_jsonl(root_b / EXCERPTS, changed)
    assert kept not in audited_paragraph_ids(root_b)
    reviewed_b = dispatch("studium_book_review", {}, session=session_b)
    assert reviewed_b["audit_passed"] is False
    assert reviewed_b["released"] is False
    assert any(kept in reason for reason in reviewed_b["reasons"])
    assert (root_b / ".studium" / "state.json").read_bytes() == state_b
    assert json.loads(state_b)["state"] != "RELEASED"


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
    assert r"\usepackage[T1]{fontenc}" in tex
    assert r"\usepackage[utf8]{inputenc}" in tex
    assert "tcolorbox" in tex
    assert "PAR-" not in tex
    preface = tex.index("Preface")
    how_to = tex.index("How to use this book")
    contents = tex.index(r"\tableofcontents")
    chapter = tex.index(r"\chapter{Conservation of mass}")
    purpose = tex.index(r"\textit{" + first.split(".", 1)[0])
    explanation = tex.index(second)
    worked = tex.index(r"\begin{tcolorbox}[title={Worked problem}")
    self_check = tex.index(r"\begin{tcolorbox}[title={Self-check}")
    notation = tex.index("Notation")
    formula = tex.index("Formula sheet")
    solutions = tex.index("Solutions")
    source_audit = tex.index("Source audit")
    study = tex.index("Study plan")
    bibliography = tex.index("thebibliography")
    assert r"\section{Explanation}" not in tex
    assert preface < how_to < contents < chapter < purpose < explanation < worked < self_check
    assert self_check < notation < formula < solutions < source_audit < study < bibliography
    assert tex.count(r"\begin{tcolorbox}[title={Worked problem}") == 1
    outside = _outside_boxes(tex)
    assert first in outside
    assert second in outside
    assert "What is the stored density?" in tex
    assert "Restate the stored density" in tex
    assert audited["audit"]["id"] in tex
    assert "The density is 2." in tex
    assert r"\part{Problems}" not in tex
    assert "Problem solving" not in tex
    assert tex.index("Source status:") > source_audit
    assert rendered["released"] is False
    assert rendered["project_state"] != "RELEASED"
    assert (root / ".studium" / "state.json").read_bytes() == state_before


def test_formula_missing_from_the_excerpt_and_not_replayed_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _topic(tmp_path, "fluidos", "Mecánica de fluidos")
    _section(session, section_id="tema-1", title="Temperatura")
    source_id = _source(session, "https://open.example/density")
    excerpt_id = _excerpt(session, source_id, "https://open.example/density", text="The density is 2.")
    text = "The conversion is F = C × 9/5 + 32. Continuity reduces to du/dx + dv/dy + dw/dz = 0."
    paragraph = _paragraph(session, "tema-1", text, [excerpt_id])
    computed = dispatch(
        "studium_computation_check",
        {"expression": "2 + 2", "result": 4, "section": "tema-1"},
        session=session,
    )
    assert computed["status"] == "replayed"
    state_before = (root / ".studium" / "state.json").read_bytes()
    refused = dispatch(
        "studium_audit_record",
        {"target": paragraph, "kind": "formula", "computation": computed["computation"]["id"]},
        session=session,
    )
    assert refused["status"] == "audit.rejected"
    assert refused["message"].startswith("the formula is not in the cited excerpts and was not replayed: ")
    assert "F = C × 9/5 + 32" in refused["message"]
    assert "du/dx + dv/dy + dw/dz = 0" in refused["message"]
    assert refused["prose_added"] is False
    assert refused["released"] is False
    assert "verified" not in json.dumps(refused)
    assert not (root / "draft" / "audits.jsonl").exists()
    assert text in (root / "draft" / "paragraphs.jsonl").read_text(encoding="utf-8")
    assert (root / ".studium" / "state.json").read_bytes() == state_before
    assert json.loads(state_before)["state"] != "RELEASED"


def test_quoted_formula_can_be_audited(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _topic(tmp_path, "fluidos", "Mecánica de fluidos")
    _section(session, section_id="tema-1", title="Temperatura")
    quoted = "The conversion is F = C × 9/5 + 32. Continuity reduces to du/dx + dv/dy + dw/dz = 0."
    source_id = _source(session, "https://open.example/quoted")
    excerpt_id = _excerpt(
        session,
        source_id,
        "https://open.example/quoted",
        text=quoted + " The stored quantity is 2.",
    )
    paragraph = _paragraph(session, "tema-1", quoted, [excerpt_id])
    computed = dispatch(
        "studium_computation_check",
        {"expression": "2 + 2", "result": 4, "section": "tema-1"},
        session=session,
    )
    state_before = (root / ".studium" / "state.json").read_bytes()
    recorded = dispatch(
        "studium_audit_record",
        {"target": paragraph, "kind": "formula", "computation": computed["computation"]["id"]},
        session=session,
    )
    assert recorded["status"] == "recorded"
    assert recorded["prose_added"] is False
    assert recorded["released"] is False
    assert recorded["applied"] is False
    assert (root / "draft" / "audits.jsonl").is_file()
    assert (root / ".studium" / "state.json").read_bytes() == state_before
    assert json.loads(state_before)["state"] != "RELEASED"


def test_claim_lines_stay_out_of_the_chapter_body(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _topic(tmp_path, "historia", "Historia medieval")
    _section(session, title="Conservation of mass")
    source_id = _source(session, "https://open.example/one")
    excerpt_id = _excerpt(session, source_id, "https://open.example/one", text="The opened page carries the chapter sentence.")
    chapter_text = "The opened page carries the chapter sentence for this section."
    _paragraph(session, "tema-1", chapter_text, [excerpt_id])
    claim_text = "Old draft line about ownership at compile time."
    claim = dispatch(
        "studium_claim_record",
        {"text": claim_text, "sources": [source_id], "section": "tema-1"},
        session=session,
    )
    assert claim["status"] == "recorded"
    state_before = (root / ".studium" / "state.json").read_bytes()
    rendered = dispatch("studium_render", {}, session=session)
    tex = (root / "latex" / "draft.tex").read_text(encoding="utf-8")
    chapter, _separator, appendix = tex.partition(r"\chapter{Source audit}")
    assert claim_text not in chapter
    assert claim_text in appendix
    assert "Leftover draft." in appendix
    assert chapter_text in chapter
    assert "PAR-" not in tex
    listed = dispatch("studium_claim_list", {}, session=session)
    assert any(item["id"] == claim["claim"]["id"] and item["text"] == claim_text for item in listed["claims"])
    assert rendered["released"] is False
    assert (root / ".studium" / "state.json").read_bytes() == state_before
    assert json.loads(state_before)["state"] != "RELEASED"


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
    assert "ask the user" not in json.dumps(nxt).lower().replace("do not ask the user how to format the page.", "")


def _topic(tmp_path, slug: str, topic: str):
    session = open_workspace(str(tmp_path))
    assert (
        dispatch("studium_project_create", {"slug": slug, "topic": topic, "language": "en"}, session=session)["status"]
        == "created"
    )
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


def _outside_boxes(tex: str) -> str:
    return re.sub(r"\\begin\{tcolorbox\}.*?\\end\{tcolorbox\}", "", tex, flags=re.S)


def _explode(*_args, **_kwargs):
    raise AssertionError("must not fetch")
