"""Opened excerpts can support a draft claim. Verify still does not release."""

from studium.cli.app import main
from studium.mcp.server import dispatch, open_workspace
from studium.research.public_sources import EXCERPT_BEFORE_DRAFT

_COURSE = {
    "course": "Mecánica de Fluidos",
    "university": "Universidad de León",
    "degree": "Grado en Ingeniería Aeroespacial",
}
_SENTENCE = "Mass is conserved when a steady flow crosses a fixed control surface."
_PASSAGE = "For steady flow the mass entering a fixed control volume equals the mass leaving it."
_GATES = (
    "corpus_sufficient",
    "blueprint_accepted",
    "authoring_complete",
    "verification_passed",
    "reviews_current",
    "release",
)


def test_supported_excerpt_claim_renders_into_the_draft(tmp_path, monkeypatch):
    session, root, cited = _fluidos(tmp_path)
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    state_before = (root / ".studium" / "state.json").read_bytes()
    opened = dispatch(
        "studium_excerpt_record",
        {
            "source_id": cited,
            "url": "https://publisher.example/white",
            "text": _PASSAGE,
        },
        session=session,
    )
    assert opened["status"] == "recorded"
    assert opened["released"] is False
    assert opened["project_state"] == "SOURCE_DISCOVERY"
    assert opened["local_sources"]["status"] == "NONE"
    excerpt = opened["excerpt"]
    assert excerpt["id"] == "EVD-0001"
    assert excerpt["source_id"] == cited
    assert excerpt["state"] == "DISCOVERED"
    assert excerpt["classification"] == "PENDING"
    assert excerpt["authority"] is None
    for absent in ("verified", "accepted", "text"):
        assert absent not in excerpt
    stored = (root / "bibliography" / "excerpts.jsonl").read_text(encoding="utf-8")
    assert _PASSAGE in stored
    fetched = dispatch("studium_excerpt_get", {"id": "EVD-0001"}, session=session)
    assert fetched["excerpt"]["text"] == _PASSAGE
    assert "verified" not in fetched["excerpt"]
    listed = dispatch("studium_excerpt_list", {}, session=session)
    assert _PASSAGE not in str(listed["excerpts"])
    claim = dispatch(
        "studium_claim_record",
        {"text": _SENTENCE, "excerpts": ["EVD-0001"]},
        session=session,
    )
    assert claim["status"] == "recorded"
    assert claim["claim"]["status"] == "draft"
    assert claim["claim"]["excerpts"] == ["EVD-0001"]
    assert claim["released"] is False
    for absent in ("verified", "accepted", "authority"):
        assert absent not in claim["claim"]
    rendered = dispatch("studium_render", {}, session=session)
    tex = (root / "latex" / "draft.tex").read_text(encoding="utf-8")
    assert _SENTENCE in tex
    assert "EVD-0001" in tex
    assert "DRAFT" in tex
    assert "PENDING" in tex
    assert rendered["released"] is False
    assert rendered["project_state"] == "SOURCE_DISCOVERY"
    if rendered["status"] == "rendered":
        assert (root / "latex" / "draft.pdf").read_bytes().startswith(b"%PDF-")
    else:
        assert rendered["status"] == "compiler_missing"
        assert rendered["pdf"] is None
        assert not (root / "latex" / "draft.pdf").exists()
    status = dispatch("studium_project_status", {}, session=session)
    assert EXCERPT_BEFORE_DRAFT in status["next_action"]
    assert status["state"] == "SOURCE_DISCOVERY"
    assert status["local_sources"]["status"] == "NONE"
    assert (root / ".studium" / "state.json").read_bytes() == state_before


def test_conflict_excerpt_cannot_support_a_claim(tmp_path, monkeypatch):
    session, root, _cited = _fluidos(tmp_path)
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    conflict = _record(session, title="Physical Fluid Dynamics", url="https://example.edu/tritton", year=1988)
    checked = dispatch(
        "studium_public_source_check",
        {
            "id": conflict,
            "url": "https://publisher.example/tritton",
            "title": "Physical Fluid Dynamics",
            "year": 1977,
        },
        session=session,
    )
    assert checked["status"] == "bibliographic_conflict"
    dispatch(
        "studium_public_source_guide_citation",
        {"id": conflict, "course_guide_cited": True},
        session=session,
    )
    opened = dispatch(
        "studium_excerpt_record",
        {
            "source_id": conflict,
            "url": "https://publisher.example/tritton",
            "text": "The observed year on this page is 1977.",
        },
        session=session,
    )
    assert opened["status"] == "recorded"
    state_before = (root / ".studium" / "state.json").read_bytes()
    refused = dispatch(
        "studium_claim_record",
        {"text": "A conflicting year still describes transition.", "excerpts": [opened["excerpt"]["id"]]},
        session=session,
    )
    assert refused["status"] == "rejected"
    assert refused["released"] is False
    assert refused["project_state"] == "SOURCE_DISCOVERY"
    assert any(item["code"] == "claim.conflict" and item["entity_id"] == conflict for item in refused["blockers"])
    assert "year" in next(item["message"] for item in refused["blockers"] if item["code"] == "claim.conflict")
    assert not (root / "claims").exists()
    assert (root / ".studium" / "state.json").read_bytes() == state_before
    assert json_state(root)["state"] != "RELEASED"
    assert json_state(root)["local_sources"]["status"] == "NONE"


def test_verify_still_does_not_release(tmp_path, monkeypatch):
    session, root, cited = _fluidos(tmp_path)
    dispatch(
        "studium_excerpt_record",
        {"source_id": cited, "url": "https://publisher.example/white", "text": _PASSAGE},
        session=session,
    )
    dispatch(
        "studium_claim_record",
        {"text": _SENTENCE, "excerpts": ["EVD-0001"]},
        session=session,
    )
    state_before = (root / ".studium" / "state.json").read_bytes()
    monkeypatch.setattr("studium.state.machine.apply", _explode)
    checked = dispatch("studium_verify", {"mode": "full"}, session=session)
    assert checked["status"] == "gate"
    assert checked["applied"] is False
    assert checked["released"] is False
    assert checked["project_state"] == "SOURCE_DISCOVERY"
    assert checked["local_sources"]["status"] == "NONE"
    assert checked["draft_claims"] == ["CLM-0001"]
    messages = [item["message"] for item in checked["blockers"]]
    assert any(item["code"] == "state.corpus_incomplete" for item in checked["blockers"])
    for gate in _GATES:
        assert f"gate {gate} is not implemented" in messages
    assert (root / ".studium" / "state.json").read_bytes() == state_before
    assert main(["verify", "--full", "--project", str(root)]) == 2
    assert json_state(root)["state"] != "RELEASED"


def test_topic_book_excerpt_does_not_need_a_guide(tmp_path):
    session = open_workspace(str(tmp_path))
    dispatch("studium_project_create", {"slug": "rust", "topic": "Rust"}, session=session)
    dispatch("studium_source_register", {"decision": "none"}, session=session)
    recorded = dispatch(
        "studium_public_source_record",
        {"title": "The Rust Programming Language", "url": "https://doc.rust-lang.org/book/", "year": 2024},
        session=session,
    )
    source_id = recorded["candidate"]["id"]
    opened = dispatch(
        "studium_excerpt_record",
        {
            "source_id": source_id,
            "url": "https://doc.rust-lang.org/book/ch04-01-what-is-ownership.html",
            "text": "Each value in Rust has an owner.",
        },
        session=session,
    )
    assert opened["status"] == "recorded"
    claim = dispatch(
        "studium_claim_record",
        {
            "text": "A value has one owner, and assignment moves that ownership.",
            "excerpts": [opened["excerpt"]["id"]],
        },
        session=session,
    )
    assert claim["status"] == "recorded"
    assert claim["claim"]["status"] == "draft"
    assert claim["project_state"] == "COURSE_DISCOVERY"
    assert claim["released"] is False
    assert "claim.not_cited" not in str(claim)
    assert json_state(tmp_path / "rust")["state"] != "RELEASED"
    assert json_state(tmp_path / "rust")["local_sources"]["status"] == "NONE"


def _fluidos(tmp_path):
    session = open_workspace(str(tmp_path))
    assert dispatch("studium_project_create", {"slug": "fluidos", **_COURSE, "language": "en"}, session=session)["status"] == "created"
    assert dispatch("studium_source_register", {"decision": "none"}, session=session)["local_sources"]["status"] == "NONE"
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
    cited = _record(
        session,
        title="Fluid Mechanics",
        url="https://example.edu/white",
        authors=["Frank M. White"],
        year=2021,
    )
    assert dispatch(
        "studium_public_source_guide_citation",
        {"id": cited, "course_guide_cited": True},
        session=session,
    )["course_guide_cited"] is True
    return session, tmp_path / "fluidos", cited


def _record(session, **fields) -> str:
    recorded = dispatch("studium_public_source_record", fields, session=session)
    assert recorded["status"] == "recorded"
    return str(recorded["candidate"]["id"])


def json_state(root):
    import json

    return json.loads((root / ".studium" / "state.json").read_text(encoding="utf-8"))


def _explode(*_args, **_kwargs):
    raise AssertionError("must not fetch")
