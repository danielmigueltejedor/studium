"""Open supplements and checked problems. Nothing here releases a book."""

import json

from studium.mcp.server import dispatch, handle, open_workspace

_COURSE = {
    "course": "Mecánica de Fluidos",
    "university": "Universidad de León",
    "degree": "Grado en Ingeniería Aeroespacial",
}
_PASS = "#[test]\nfn holds() {\n    assert_eq!(2 + 2, 4);\n}\n"
_FAIL = "#[test]\nfn drops() {\n    assert!(false);\n}\n"
_INVOCATION = ["rustc", "--test", "main.rs", "-o", "tester"]


def test_rust_test_is_checked_only_after_three_passes(tmp_path, monkeypatch):
    session, root = _rust_book(tmp_path)
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    recorded = _rust_problem(session, "ownership", "Show that a move ends the old owner.", _PASS)
    assert recorded["problem"]["status"] == "unchecked"
    assert recorded["problem"]["correct"] is False
    assert recorded["released"] is False
    for absent in ("verified", "accepted"):
        assert absent not in recorded["problem"]
    state_before = (root / ".studium" / "state.json").read_bytes()
    checked = dispatch("studium_problem_check", {"id": "PRB-0001"}, session=session)
    assert checked["status"] == "checked"
    assert checked["checked"] is True
    assert checked["released"] is False
    assert checked["project_state"] == "COURSE_DISCOVERY"
    assert [run["passed"] for run in checked["runs"]] == [True, True, True]
    assert checked["problem"]["correct"] is True
    assert "verified" not in checked["problem"]
    assert checked["problem"]["status"] == "checked"
    assert checked["message"] == (
        "Three identical rustc runs are a reproducibility check, not an independent proof."
    )
    assert checked["problem"]["status_text"] == checked["message"]
    assert checked["problem"]["check_kind"] == "reproducibility"
    assert "three methods" not in json.dumps(checked).lower()
    assert "methods" not in checked["problem"]
    assert (root / ".studium" / "state.json").read_bytes() == state_before
    verify = dispatch("studium_verify", {"mode": "full"}, session=session)
    assert verify["released"] is False
    assert verify["applied"] is False
    assert any(item["message"] == "gate release is not implemented" for item in verify["blockers"])
    assert json.loads(state_before)["state"] != "RELEASED"


def test_failing_rust_test_stays_unchecked(tmp_path, monkeypatch):
    session, root = _rust_book(tmp_path)
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    _rust_problem(session, "ownership", "This assertion does not hold.", _FAIL)
    state_before = (root / ".studium" / "state.json").read_bytes()
    checked = dispatch("studium_problem_check", {"id": "PRB-0001"}, session=session)
    assert checked["status"] == "unchecked"
    assert checked["checked"] is False
    assert checked["problem"]["correct"] is False
    assert checked["problem"]["status"] == "unchecked"
    assert checked["runs"]
    assert any(run["passed"] is False for run in checked["runs"])
    assert all(run["passed"] is not True or checked["checked"] is False for run in checked["runs"])
    assert "verified" not in checked["problem"]
    assert checked["released"] is False
    assert (root / ".studium" / "state.json").read_bytes() == state_before


def test_comment_only_rust_stays_unchecked_and_assert_eq_can_pass(tmp_path, monkeypatch):
    session, root = _rust_book(tmp_path)
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    comments = (
        "// The force is mass times acceleration.\n"
        "// fn main() { assert_eq!(1, 1); }\n"
        "/* #[test]\nfn hidden() { assert_ne!(1, 2); } */\n"
    )
    recorded = _rust_problem(session, "ownership", "Comments are not a calculation.", comments)
    assert recorded["problem"]["status"] == "unchecked"
    state_before = (root / ".studium" / "state.json").read_bytes()
    refused = dispatch("studium_problem_check", {"id": recorded["problem"]["id"]}, session=session)
    assert refused["status"] == "unchecked"
    assert refused["checked"] is False
    assert refused["problem"]["correct"] is False
    assert refused["problem"]["status"] == "unchecked"
    assert refused["runs"] == []
    assert "no test" in refused["message"]
    assert "only comments" in refused["message"]
    assert refused["released"] is False
    assert "verified" not in json.dumps(refused)
    stored = (root / "problems" / "problems.jsonl").read_text(encoding="utf-8")
    assert stored.count('"passed":true') == 0
    assert (root / ".studium" / "state.json").read_bytes() == state_before
    assert json.loads(state_before)["state"] != "RELEASED"

    passing = "#[test]\nfn holds() {\n    assert_eq!(2 + 2, 4);\n}\n"
    second = _rust_problem(session, "ownership", "One equality the server can run.", passing)
    checked = dispatch("studium_problem_check", {"id": second["problem"]["id"]}, session=session)
    assert checked["status"] == "checked"
    assert checked["checked"] is True
    assert checked["problem"]["correct"] is True
    assert [run["passed"] for run in checked["runs"]] == [True, True, True]
    assert checked["released"] is False
    assert checked["project_state"] != "RELEASED"
    assert "verified" not in json.dumps(checked)
    assert (root / ".studium" / "state.json").read_bytes() == state_before


def test_missing_compiler_does_not_pretend_the_test_passed(tmp_path, monkeypatch):
    session, root = _rust_book(tmp_path)
    _rust_problem(session, "ownership", "Compile nothing.", _PASS)
    monkeypatch.setattr("studium.authoring.problems.shutil.which", lambda _name: None)
    monkeypatch.setattr("studium.authoring.problems._execute", _explode)
    checked = dispatch("studium_problem_check", {"id": "PRB-0001"}, session=session)
    assert checked["status"] == "compiler_missing"
    assert checked["checked"] is False
    assert checked["runs"] == []
    assert checked["problem"]["status"] == "unchecked"
    assert checked["problem"]["correct"] is False
    assert checked["released"] is False
    assert "verified" not in json.dumps(checked)
    stored = json.loads((root / "problems" / "problems.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert stored["status"] == "unchecked"
    assert stored["correct"] is False


def test_course_paragraph_can_cite_an_open_supplement(tmp_path, monkeypatch):
    session, root, source_id = _fluidos(tmp_path)
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    dispatch(
        "studium_blueprint_store",
        {"sections": [{"id": "viscosity", "title": "Viscosity"}]},
        session=session,
    )
    flagged = dispatch(
        "studium_public_source_open_supplement",
        {"id": source_id, "open_supplement": True, "open_licensed": True},
        session=session,
    )
    assert flagged["status"] == "ok"
    assert flagged["open_supplement"] is True
    assert flagged["guide_bibliography"] is False
    assert flagged["authority"] is None
    assert "verified" not in flagged["candidate"]
    excerpt = dispatch(
        "studium_excerpt_record",
        {
            "source_id": source_id,
            "url": "https://openstax.org/books/university-physics-volume-1/pages/14-3-viscosity",
            "text": "Viscosity measures resistance to flow in a fluid.",
        },
        session=session,
    )
    assert excerpt["status"] == "recorded"
    state_before = (root / ".studium" / "state.json").read_bytes()
    paragraph = dispatch(
        "studium_paragraph_record",
        {
            "section": "viscosity",
            "text": "Viscosity is the resistance a fluid offers to flow.",
            "excerpts": [excerpt["excerpt"]["id"]],
        },
        session=session,
    )
    assert paragraph["status"] == "recorded"
    assert paragraph["paragraph"]["status"] == "draft"
    assert paragraph["released"] is False
    rendered = dispatch("studium_render", {}, session=session)
    tex = (root / "latex" / "draft.tex").read_text(encoding="utf-8")
    assert "Open supplement:" in tex
    assert "Not the guide bibliography." in tex
    assert "Viscosity is the resistance a fluid offers to flow." in tex
    assert rendered["released"] is False
    report = dispatch("studium_draft_completeness", {}, session=session)
    assert report["empty_sections"] == []
    assert report["supported_section_count"] == 1
    status = dispatch("studium_project_status", {}, session=session)
    assert "Add checked problems." in status["next_action"]
    verify = dispatch("studium_verify", {"mode": "full"}, session=session)
    assert verify["released"] is False
    assert verify["applied"] is False
    assert any(item["message"] == "gate release is not implemented" for item in verify["blockers"])
    assert (root / ".studium" / "state.json").read_bytes() == state_before


def test_conflicting_source_is_still_rejected(tmp_path, monkeypatch):
    session, root, _cited = _fluidos(tmp_path)
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    dispatch(
        "studium_blueprint_store",
        {"sections": [{"id": "viscosity", "title": "Viscosity"}]},
        session=session,
    )
    conflict = dispatch(
        "studium_public_source_record",
        {"title": "Physical Fluid Dynamics", "url": "https://example.edu/tritton", "year": 1988},
        session=session,
    )["candidate"]["id"]
    assert (
        dispatch(
            "studium_public_source_check",
            {
                "id": conflict,
                "url": "https://publisher.example/tritton",
                "title": "Physical Fluid Dynamics",
                "year": 1977,
            },
            session=session,
        )["status"]
        == "bibliographic_conflict"
    )
    assert (
        dispatch(
            "studium_public_source_open_supplement",
            {"id": conflict, "open_supplement": True, "open_licensed": True},
            session=session,
        )["open_supplement"]
        is True
    )
    excerpt = dispatch(
        "studium_excerpt_record",
        {
            "source_id": conflict,
            "url": "https://publisher.example/tritton",
            "text": "The page says 1977.",
        },
        session=session,
    )
    refused = dispatch(
        "studium_paragraph_record",
        {
            "section": "viscosity",
            "text": "A conflicting year still describes transition.",
            "excerpts": [excerpt["excerpt"]["id"]],
        },
        session=session,
    )
    assert refused["status"] == "rejected"
    assert refused["released"] is False
    assert any(item["code"] == "claim.conflict" for item in refused["blockers"])
    pirate = dispatch(
        "studium_public_source_record",
        {
            "title": "Closed textbook scan",
            "url": "https://example.edu/closed-scan",
            "unauthorized": True,
        },
        session=session,
    )
    assert pirate["status"] == "source.unauthorized"
    stored = (root / "bibliography" / "public.jsonl").read_text(encoding="utf-8")
    assert "Closed textbook scan" not in stored
    instructions = handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})["result"]["instructions"]
    assert "Do not download pages." in instructions
    assert "Do not record pirate or unauthorized copies." in instructions
    assert json.loads((root / ".studium" / "state.json").read_text(encoding="utf-8"))["state"] != "RELEASED"


def _rust_book(tmp_path):
    session = open_workspace(str(tmp_path))
    assert dispatch("studium_project_create", {"slug": "rust", "topic": "Rust"}, session=session)["status"] == "created"
    dispatch("studium_source_register", {"decision": "none"}, session=session)
    dispatch(
        "studium_blueprint_store",
        {"sections": [{"id": "ownership", "title": "Ownership"}]},
        session=session,
    )
    return session, tmp_path / "rust"


def _rust_problem(session, section: str, prompt: str, source: str) -> dict:
    recorded = dispatch(
        "studium_problem_record",
        {"section": section, "prompt": prompt, "source_text": source, "invocation": _INVOCATION},
        session=session,
    )
    assert recorded["status"] == "recorded"
    return recorded


def _fluidos(tmp_path):
    session = open_workspace(str(tmp_path))
    assert dispatch("studium_project_create", {"slug": "fluidos", **_COURSE}, session=session)["status"] == "created"
    dispatch("studium_source_register", {"decision": "none"}, session=session)
    assert (
        dispatch(
            "studium_course_document_record",
            {
                "title": "Guía docente",
                "url": "https://www.unileon.es/guia-fluidos",
                "text": "Bibliografía: Frank M. White, Fluid Mechanics.",
            },
            session=session,
        )["status"]
        == "recorded"
    )
    assert dispatch("studium_course_recorded", {}, session=session)["state"] == "SOURCE_DISCOVERY"
    recorded = dispatch(
        "studium_public_source_record",
        {
            "title": "University Physics",
            "url": "https://openstax.org/books/university-physics-volume-1",
            "year": 2021,
        },
        session=session,
    )
    assert recorded["status"] == "recorded"
    assert recorded["candidate"].get("course_guide_cited") is not True
    return session, tmp_path / "fluidos", recorded["candidate"]["id"]


def _explode(*_args, **_kwargs):
    raise AssertionError("must not fetch or run")
