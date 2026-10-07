"""Blueprint sections render as excerpt-backed paragraphs or as visible gaps."""

import json

from studium.authoring.paragraphs import GAP_LABEL
from studium.cli.app import main
from studium.mcp.server import dispatch, open_workspace

_COURSE = {
    "course": "Mecánica de Fluidos",
    "university": "Universidad de León",
    "degree": "Grado en Ingeniería Aeroespacial",
}
_SECTIONS = [
    {"id": "mass", "title": "Conservation of mass"},
    {"id": "momentum", "title": "Momentum"},
    {"id": "energy", "title": "Energy"},
]
_MASS_A = "Mass entering a fixed control volume equals mass leaving it in steady flow."
_MASS_B = "The continuity statement follows from that balance on the same opened page."
_ENERGY = "The energy crossing the surface is the work and heat recorded on the opened page."


def test_full_outline_renders_in_order_and_labels_a_gap(tmp_path, monkeypatch):
    session, root, cited = _fluidos(tmp_path)
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    dispatch("studium_blueprint_store", {"sections": _SECTIONS}, session=session)
    state_before = (root / ".studium" / "state.json").read_bytes()
    excerpt = _excerpt(session, cited, "https://publisher.example/white", "Steady flow conserves mass.")
    first = dispatch(
        "studium_paragraph_record",
        {"section": "mass", "text": _MASS_A, "excerpts": [excerpt]},
        session=session,
    )
    second = dispatch(
        "studium_paragraph_record",
        {"section": "mass", "text": _MASS_B, "excerpts": [excerpt]},
        session=session,
    )
    energy = dispatch(
        "studium_paragraph_record",
        {"section": "energy", "text": _ENERGY, "excerpts": [excerpt]},
        session=session,
    )
    assert first["status"] == "recorded"
    assert first["paragraph"]["status"] == "draft"
    assert first["paragraph"]["id"] == "PAR-0001"
    assert first["released"] is False
    for absent in ("verified", "accepted", "authority"):
        assert absent not in first["paragraph"]
    assert second["paragraph"]["id"] == "PAR-0002"
    assert energy["paragraph"]["id"] == "PAR-0003"
    missing = dispatch(
        "studium_paragraph_record",
        {"section": "momentum", "text": "This sentence has no opened excerpt."},
        session=session,
    )
    assert missing["status"] == "mcp.invalid_input"
    report = dispatch("studium_draft_completeness", {}, session=session)
    assert report["section_count"] == 3
    assert report["supported_section_count"] == 2
    assert report["empty_sections"] == [{"id": "momentum", "title": "Momentum"}]
    assert report["released"] is False
    status = dispatch("studium_project_status", {}, session=session)
    assert "Empty sections: momentum (Momentum)." in status["next_action"]
    assert "Open source text before writing them." in status["next_action"]
    assert status["state"] == "SOURCE_DISCOVERY"
    rendered = dispatch("studium_render", {}, session=session)
    tex = (root / "latex" / "draft.tex").read_text(encoding="utf-8")
    mass_at = tex.index("Conservation of mass")
    first_at = tex.index(_MASS_A)
    second_at = tex.index(_MASS_B)
    momentum_at = tex.index("Momentum")
    gap_at = tex.index(GAP_LABEL)
    energy_at = tex.index("Energy")
    energy_text = tex.index(_ENERGY)
    assert mass_at < first_at < second_at < momentum_at < gap_at < energy_at < energy_text
    assert "This sentence has no opened excerpt." not in tex
    assert rendered["released"] is False
    assert rendered["project_state"] == "SOURCE_DISCOVERY"
    assert rendered["draft_paragraphs"] == ["PAR-0001", "PAR-0002", "PAR-0003"]
    if rendered["status"] == "rendered":
        assert (root / "latex" / "draft.pdf").read_bytes().startswith(b"%PDF-")
    else:
        assert rendered["status"] == "compiler_missing"
        assert not (root / "latex" / "draft.pdf").exists()
    assert (root / ".studium" / "state.json").read_bytes() == state_before
    assert json.loads(state_before)["state"] != "RELEASED"


def test_conflict_paragraph_is_rejected(tmp_path, monkeypatch):
    session, root, _cited = _fluidos(tmp_path)
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    dispatch(
        "studium_blueprint_store",
        {"sections": [{"id": "mass", "title": "Conservation of mass"}]},
        session=session,
    )
    conflict = _record(session, title="Physical Fluid Dynamics", url="https://example.edu/tritton", year=1988)
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
    dispatch(
        "studium_public_source_guide_citation",
        {"id": conflict, "course_guide_cited": True},
        session=session,
    )
    excerpt = _excerpt(session, conflict, "https://publisher.example/tritton", "The page says 1977.")
    state_before = (root / ".studium" / "state.json").read_bytes()
    refused = dispatch(
        "studium_paragraph_record",
        {"section": "mass", "text": "A conflicting year still describes transition.", "excerpts": [excerpt]},
        session=session,
    )
    assert refused["status"] == "rejected"
    assert refused["released"] is False
    assert refused["project_state"] == "SOURCE_DISCOVERY"
    assert any(item["code"] == "claim.conflict" and item["entity_id"] == conflict for item in refused["blockers"])
    assert not (root / "draft").exists()
    assert (root / ".studium" / "state.json").read_bytes() == state_before


def test_verify_still_blocks_release(tmp_path, monkeypatch):
    session, root, cited = _fluidos(tmp_path)
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    dispatch("studium_blueprint_store", {"sections": _SECTIONS}, session=session)
    excerpt = _excerpt(session, cited, "https://publisher.example/white", "Opened page.")
    for section_id, text in (
        ("mass", _MASS_A),
        ("momentum", "Momentum flux across the surface is the force named on the opened page."),
        ("energy", _ENERGY),
    ):
        assert (
            dispatch(
                "studium_paragraph_record",
                {"section": section_id, "text": text, "excerpts": [excerpt]},
                session=session,
            )["status"]
            == "recorded"
        )
    state_before = (root / ".studium" / "state.json").read_bytes()
    monkeypatch.setattr("studium.state.machine.apply", _explode)
    checked = dispatch("studium_verify", {"mode": "full"}, session=session)
    assert checked["status"] == "gate"
    assert checked["applied"] is False
    assert checked["released"] is False
    assert checked["project_state"] == "SOURCE_DISCOVERY"
    codes = {item["code"] for item in checked["blockers"]}
    messages = [item["message"] for item in checked["blockers"]]
    assert "state.corpus_incomplete" not in codes
    assert "gate release is not implemented" in messages
    assert "gate verification_passed is not implemented" in messages
    assert "gate reviews_current is not implemented" in messages
    assert (root / ".studium" / "state.json").read_bytes() == state_before
    assert main(["verify", "--full", "--project", str(root)]) == 2
    status = dispatch("studium_project_status", {}, session=session)
    assert "Every blueprint section has a supported paragraph." in status["next_action"]
    assert "Do not mark the book released." in status["next_action"]
    assert json.loads((root / ".studium" / "state.json").read_text(encoding="utf-8"))["state"] != "RELEASED"


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
    cited = _record(
        session,
        title="Fluid Mechanics",
        url="https://example.edu/white",
        authors=["Frank M. White"],
        year=2021,
    )
    assert (
        dispatch(
            "studium_public_source_guide_citation",
            {"id": cited, "course_guide_cited": True},
            session=session,
        )["course_guide_cited"]
        is True
    )
    return session, tmp_path / "fluidos", cited


def _record(session, **fields) -> str:
    recorded = dispatch("studium_public_source_record", fields, session=session)
    assert recorded["status"] == "recorded"
    return str(recorded["candidate"]["id"])


def _excerpt(session, source_id: str, url: str, text: str) -> str:
    opened = dispatch(
        "studium_excerpt_record",
        {"source_id": source_id, "url": url, "text": text},
        session=session,
    )
    assert opened["status"] == "recorded"
    return str(opened["excerpt"]["id"])


def _explode(*_args, **_kwargs):
    raise AssertionError("must not fetch or apply a transition")
