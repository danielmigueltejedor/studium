"""Offline workflow for a Spanish fluid-mechanics course book.

The fixture states its own provenance. It is not an official university document,
and the test does not call a network or an external model.
"""

import json
from fractions import Fraction
from pathlib import Path

from studium.authoring.audit import audited_paragraph_ids
from studium.authoring.computation import evaluate
from studium.authoring.render import _compile, find_engine, render_draft
from studium.cli.app import main
from studium.mcp.server import dispatch, open_workspace
from studium.storage.records import RecordCorruption, read_jsonl

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "mecanica_fluidos"
_COURSE = {
    "course": "Mecánica de Fluidos",
    "university": "Universidad de León",
    "degree": "Grado en Ingeniería Aeroespacial",
}
_EXPRESSION = "1000 * 981 * 2 / 100"
_EXPECTED = Fraction(1000) * Fraction(981) * Fraction(2) / Fraction(100)
_PROSE_A = (
    "The fixture derivation starts from dp = rho * g * h and keeps every factor visible to the reader. "
    "A student can replay 1000 * 981 * 2 / 100 without treating the model as a source of truth."
)
_PROSE_B = (
    "The worked example uses the stored depth and the stored gravity fraction from the opened fixture. "
    "The exercise asks for that same replayed difference and does not invent a second value."
)


def test_offline_fluidos_workflow_renders_real_artifacts(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    monkeypatch.chdir(tmp_path)
    assert (
        main(
            [
                "create",
                "fluidos",
                "--course",
                _COURSE["course"],
                "--university",
                _COURSE["university"],
                "--degree",
                _COURSE["degree"],
                "--language",
                "es",
                "--profile",
                "STEM",
                "--project-dir",
                str(tmp_path),
            ]
        )
        == 0
    )
    session = open_workspace(str(tmp_path))
    root = tmp_path / "fluidos"
    assert session is not None
    session.active = root
    provenance = (_FIXTURE / "provenance.md").read_text(encoding="utf-8")
    assert "not an official document" in provenance
    excerpts = json.loads((_FIXTURE / "excerpts.json").read_text(encoding="utf-8"))
    dispatch(
        "studium_blueprint_store",
        {"sections": [{"id": "hidrostatica", "title": "Presión hidrostática"}]},
        session=session,
    )
    left = _source_and_excerpt(session, excerpts["left"])
    right = _source_and_excerpt(session, excerpts["right"])
    first = _paragraph(session, _PROSE_A, [left, right])
    second = _paragraph(session, _PROSE_B, [left, right])
    computed = dispatch(
        "studium_computation_check",
        {"expression": _EXPRESSION, "result": str(_EXPECTED), "section": "hidrostatica"},
        session=session,
    )
    assert computed["status"] == "replayed"
    assert computed["correct"] is True
    assert computed["server_result"] == str(evaluate(_EXPRESSION))
    assert evaluate(_EXPRESSION) == _EXPECTED
    problem = dispatch(
        "studium_problem_record",
        {
            "section": "hidrostatica",
            "prompt": "Replay the stored hydrostatic difference.",
            "expected": str(_EXPECTED),
            "excerpts": [left, right],
        },
        session=session,
    )
    assert problem["problem"]["status"] == "two_witnesses"
    audited = dispatch(
        "studium_audit_record",
        {
            "target": "hidrostatica",
            "kind": "scientific",
            "excerpts": [left, right],
            "computation": computed["computation"]["id"],
            "problem": problem["problem"]["id"],
        },
        session=session,
    )
    assert audited["status"] == "recorded"
    assert audited["audit"]["evidence"]["computation_result"] == "COMPUTATION_REPRODUCED"
    assert audited["audit"]["evidence"]["mathematically_verified"] is False
    assert {first, second} <= audited_paragraph_ids(root)
    scanned = dispatch("studium_contradiction_scan", {}, session=session)
    assert scanned["open_count"] == 0
    reviewed = dispatch("studium_book_review", {}, session=session)
    assert reviewed["audit_passed"] is True
    assert reviewed["released"] is False
    rendered = render_draft(root)
    tex_path = root / "latex" / "draft.tex"
    tex = tex_path.read_text(encoding="utf-8")
    assert r"\chapter{Presión hidrostática}" in tex
    assert "dp = rho * g * h" in tex or "dp = rho * g * h".replace(" ", "") in tex.replace(" ", "")
    assert "19620" in tex or str(_EXPECTED) in tex
    assert "RELEASED" not in tex
    state = json.loads((root / ".studium" / "state.json").read_text(encoding="utf-8"))
    assert state["state"] != "RELEASED"
    if find_engine() is None:
        assert rendered["status"] == "compiler_missing"
        assert not (root / "latex" / "draft.pdf").exists()
    else:
        assert rendered["status"] == "rendered", rendered.get("message")
        pdf = (root / "latex" / "draft.pdf").read_bytes()
        assert pdf.startswith(b"%PDF-")
        assert b"obj" in pdf

    reopened = open_workspace(str(tmp_path))
    status = dispatch("studium_project_status", {"project": "fluidos"}, session=reopened)
    assert status["course"]["name"] == _COURSE["course"]
    assert status["course"]["university"] == _COURSE["university"]
    assert status["state"] != "RELEASED"
    capsys.readouterr()


def test_malformed_records_fail_closed(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    root = _course(tmp_path)
    path = root / "draft" / "paragraphs.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"id":"PAR-0001","text":"kept"}\n{broken\n{"id":"PAR-0002"}\n', encoding="utf-8")
    try:
        read_jsonl(path)
    except RecordCorruption as exc:
        assert 2 in exc.lines
    else:
        raise AssertionError("malformed record was accepted")
    state = json.loads((root / ".studium" / "state.json").read_text(encoding="utf-8"))
    assert state["state"] != "RELEASED"


def test_missing_compiler_does_not_invent_a_pdf(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    root = _course(tmp_path)
    monkeypatch.setattr("studium.authoring.render.find_engine", lambda: None)
    rendered = render_draft(root)
    assert rendered["status"] == "compiler_missing"
    assert rendered["pdf"] is None
    assert (root / "latex" / "draft.tex").is_file()
    assert not (root / "latex" / "draft.pdf").exists()


def test_real_compiler_rejects_invalid_tex(tmp_path):
    engine = find_engine()
    if engine is None:
        import pytest

        pytest.skip("no LaTeX engine on PATH")
    tex = tmp_path / "bad.tex"
    tex.write_text(r"\documentclass{article}\begin{document}\notacommand\end{document}" + "\n", encoding="utf-8")
    compiled, detail = _compile(engine, tex, tmp_path)
    assert compiled is False
    assert detail
    assert not (tmp_path / "bad.pdf").is_file() or (tmp_path / "bad.pdf").stat().st_size == 0


def test_invalid_math_and_unsupported_claim_are_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _session(tmp_path)
    _section(session)
    excerpts = json.loads((_FIXTURE / "excerpts.json").read_text(encoding="utf-8"))
    left = _source_and_excerpt(session, excerpts["left"])
    right = _source_and_excerpt(session, excerpts["right"])
    invalid = dispatch(
        "studium_computation_check",
        {"expression": "1 / 0", "result": "0", "section": "hidrostatica"},
        session=session,
    )
    assert invalid["accepted"] is False
    assert invalid["correct"] is False
    assert invalid["status"] != "replayed"
    _paragraph(session, _PROSE_A, [left, right])
    _paragraph(session, "The density is 9. " + _PROSE_B, [left, right])
    refused = dispatch(
        "studium_audit_record",
        {"target": "hidrostatica", "kind": "scientific", "excerpts": [left, right]},
        session=session,
    )
    assert refused["status"] == "audit.rejected"
    assert refused["released"] is False
    assert not (root / "draft" / "audits.jsonl").exists()


def test_stale_audit_and_unresolved_contradiction_block_review(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _session(tmp_path)
    _section(session)
    excerpts = json.loads((_FIXTURE / "excerpts.json").read_text(encoding="utf-8"))
    left = _source_and_excerpt(session, excerpts["left"])
    right = _source_and_excerpt(session, excerpts["right"])
    first = _paragraph(session, _PROSE_A, [left])
    _paragraph(session, _PROSE_B, [right])
    assert dispatch(
        "studium_audit_record",
        {"target": "hidrostatica", "kind": "scientific", "excerpts": [left, right]},
        session=session,
    )["status"] == "recorded"
    dispatch(
        "studium_paragraph_replace",
        {"id": first, "text": _PROSE_A + " The later sentence changes the audited paragraph.", "excerpts": [left]},
        session=session,
    )
    assert first not in audited_paragraph_ids(root)
    contradicted = dispatch(
        "studium_paragraph_record",
        {
            "section": "hidrostatica",
            "text": "The density is 9. " + _PROSE_B,
            "excerpts": [right],
        },
        session=session,
    )
    assert contradicted["status"] == "recorded"
    # The first prose does not name density. Add an opposing value in a second paragraph pair.
    dispatch(
        "studium_paragraph_record",
        {"section": "hidrostatica", "text": "The density is 2. " + _PROSE_A, "excerpts": [left]},
        session=session,
    )
    scanned = dispatch("studium_contradiction_scan", {}, session=session)
    assert scanned["open_count"] >= 1
    assert any(item["quantity"] == "density" for item in scanned["contradictions"])
    reviewed = dispatch("studium_book_review", {}, session=session)
    assert reviewed["audit_passed"] is False
    assert reviewed["released"] is False
    assert any("contradiction" in reason or first in reason for reason in reviewed["reasons"])


def test_incomplete_book_is_not_finished(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _session(tmp_path)
    dispatch(
        "studium_blueprint_store",
        {
            "sections": [
                {"id": "hidrostatica", "title": "Presión hidrostática"},
                {"id": "continuidad", "title": "Continuidad"},
            ]
        },
        session=session,
    )
    excerpts = json.loads((_FIXTURE / "excerpts.json").read_text(encoding="utf-8"))
    left = _source_and_excerpt(session, excerpts["left"])
    _paragraph(session, _PROSE_A, [left])
    nxt = dispatch("studium_book_next", {}, session=session)
    assert nxt["released"] is False
    blob = json.dumps(nxt)
    assert "Continuidad" in blob or "incomplete" in blob.lower() or nxt["tool"] != "studium_render"
    rendered = render_draft(root)
    assert rendered["released"] is False
    state = json.loads((root / ".studium" / "state.json").read_text(encoding="utf-8"))
    assert state["state"] != "RELEASED"


def _course(tmp_path: Path) -> Path:
    session, root = _session(tmp_path)
    del session
    return root


def _session(tmp_path: Path):
    session = open_workspace(str(tmp_path))
    created = dispatch(
        "studium_project_create",
        {"slug": "fluidos", **_COURSE, "language": "es", "profile": "STEM"},
        session=session,
    )
    assert created["status"] == "created"
    return session, tmp_path / "fluidos"


def _section(session) -> None:
    assert (
        dispatch(
            "studium_blueprint_store",
            {"sections": [{"id": "hidrostatica", "title": "Presión hidrostática"}]},
            session=session,
        )["status"]
        == "recorded"
    )


def _source_and_excerpt(session, item: dict[str, str]) -> str:
    source = dispatch(
        "studium_public_source_record",
        {"title": item["title"], "url": item["url"], "text": item["text"]},
        session=session,
    )
    assert source["status"] == "recorded"
    opened = dispatch(
        "studium_public_source_open_supplement",
        {"id": source["candidate"]["id"], "open_supplement": True, "open_licensed": True},
        session=session,
    )
    assert opened["status"] in {"recorded", "ok", "unchanged", "already_recorded"} or opened.get("open_supplement") is True, opened
    excerpt = dispatch(
        "studium_excerpt_record",
        {"source_id": source["candidate"]["id"], "url": item["url"], "text": item["text"]},
        session=session,
    )
    assert excerpt["status"] == "recorded"
    return str(excerpt["excerpt"]["id"])


def _paragraph(session, text: str, excerpts: list[str]) -> str:
    recorded = dispatch(
        "studium_paragraph_record",
        {"section": "hidrostatica", "text": text, "excerpts": excerpts, "role": "explanation"},
        session=session,
    )
    assert recorded["status"] == "recorded", recorded
    return str(recorded["paragraph"]["id"])


def _explode(*_args, **_kwargs):
    raise AssertionError("must not fetch")
