"""The DRAFT is a book. Greek is escaped. Nothing here is RELEASED."""

import json
import subprocess

from studium.authoring.render import find_engine
from studium.mcp.server import dispatch, open_workspace

_GREEK = "Density ρ₀ and viscosity μ meet length ℓ in the sum Σ × ρ."
_PLAIN = "The opened page is the support for a second explanatory paragraph."
_UNCHECKED = "An unchecked draft sentence stays in the draft."


def test_draft_tex_has_the_book_skeleton_and_escapes_greek(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _topic(tmp_path, "historia", "Historia medieval")
    source_id = _source(session, "https://open.example/historia")
    excerpt_id = _excerpt(session, source_id, "https://open.example/historia")
    dispatch(
        "studium_blueprint_store",
        {"sections": [{"id": "tema-1", "title": "Conservation of mass"}]},
        session=session,
    )
    greek = dispatch(
        "studium_paragraph_record",
        {"section": "tema-1", "text": _GREEK, "excerpts": [excerpt_id]},
        session=session,
    )
    plain = dispatch(
        "studium_paragraph_record",
        {"section": "tema-1", "text": _PLAIN, "excerpts": [excerpt_id]},
        session=session,
    )
    claim = dispatch(
        "studium_claim_record",
        {"text": _UNCHECKED, "sources": [source_id]},
        session=session,
    )
    assert greek["status"] == "recorded"
    assert plain["paragraph"]["id"] == "PAR-0002"
    assert claim["claim"]["status"] == "draft"
    state_before = (root / ".studium" / "state.json").read_bytes()
    rendered = dispatch("studium_render", {}, session=session)
    tex = (root / "latex" / "draft.tex").read_text(encoding="utf-8")
    assert r"\documentclass{book}" in tex
    preface = tex.index("Preface")
    how_to = tex.index("How to use this book")
    contents = tex.index(r"\tableofcontents")
    chapter = tex.index(r"\chapter{Conservation of mass}")
    audit = tex.index("Source audit")
    bibliography = tex.index("thebibliography")
    assert preface < how_to < contents < chapter < audit < bibliography
    assert r"\part{Problems}" not in tex
    assert "Problem solving" not in tex
    assert "PAR-" not in tex
    assert "tcolorbox" in tex
    assert r"\usepackage[T1]{fontenc}" in tex
    for title in (
        "Notation",
        "Formula sheet",
        "Solutions",
        "Study plan",
    ):
        assert title in tex
    assert _PLAIN in tex
    assert chapter < tex.index(r"\Sigma")
    assert r"\Sigma" in tex
    assert r"\rho" in tex
    assert r"\ell" in tex
    assert r"\mu" in tex
    assert r"\times" in tex
    assert r"_{0}" in tex
    for raw in ("Σ", "ρ", "ℓ", "μ", "×", "₀"):
        assert raw not in tex
    assert "single excerpt" in tex
    assert f"{claim['claim']['id']}: unchecked" in tex
    assert _UNCHECKED in tex
    assert "DRAFT" in tex
    assert rendered["released"] is False
    assert rendered["project_state"] != "RELEASED"
    assert (root / ".studium" / "state.json").read_bytes() == state_before
    if find_engine() is not None:
        assert rendered["status"] == "rendered"
        assert rendered["pdf"] == "latex/draft.pdf"
        assert (root / "latex" / "draft.pdf").read_bytes().startswith(b"%PDF-")
    else:
        assert rendered["status"] == "compiler_missing"
        assert rendered["pdf"] is None
        assert not (root / "latex" / "draft.pdf").exists()


def test_spanish_draft_uses_boxes_without_internal_ids(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session = open_workspace(str(tmp_path))
    created = dispatch(
        "studium_project_create",
        {"slug": "fluidos", "topic": "Mecánica de fluidos", "language": "es"},
        session=session,
    )
    assert created["status"] == "created"
    root = tmp_path / "fluidos"
    source_id = _source(session, "https://open.example/fluidos")
    excerpt_id = _excerpt(session, source_id, "https://open.example/fluidos", "La página abierta describe los fluidos.")
    dispatch(
        "studium_blueprint_store",
        {
            "sections": [
                {"id": "tema-1", "title": "Tema 1: Tema 1: Conservación"},
                {"id": "tema-2", "title": "Tema 2: Energía"},
            ]
        },
        session=session,
    )
    dispatch(
        "studium_paragraph_record",
        {
            "section": "tema-1",
            "role": "purpose",
            "text": "Los fluidos en conflicto definen esta sección.",
            "excerpts": [excerpt_id],
        },
        session=session,
    )
    dispatch(
        "studium_paragraph_record",
        {
            "section": "tema-1",
            "role": "explanation",
            "text": "La definición permanece ligada a la página abierta.",
            "excerpts": [excerpt_id],
        },
        session=session,
    )
    dispatch(
        "studium_paragraph_record",
        {
            "section": "tema-1",
            "role": "self_check",
            "text": "Escribe la definición con tus palabras.",
            "excerpts": [excerpt_id],
        },
        session=session,
    )
    computed = dispatch(
        "studium_computation_check",
        {"expression": "2 + 2", "result": 4, "section": "tema-1"},
        session=session,
    )
    assert computed["status"] == "replayed"
    state_before = (root / ".studium" / "state.json").read_bytes()
    rendered = dispatch("studium_render", {}, session=session)
    tex = (root / "latex" / "draft.tex").read_text(encoding="utf-8")
    assert "tcolorbox" in tex
    assert "PAR-" not in tex
    assert r"\usepackage[T1]{fontenc}" in tex
    assert r"\usepackage[utf8]{inputenc}" in tex
    assert r"\chapter{Conservación}" in tex
    assert "Tema 1:" not in tex
    assert "Tema 2:" not in tex
    assert r"\chapter{Energía}" in tex
    assert "Esta sección está vacía." in tex
    for heading in (
        "Prefacio",
        "Cómo usar este libro",
        "Auditoría de fuentes",
        "Plan de estudio",
        "Notación",
        "Hoja de fórmulas",
        "Soluciones",
        "Borrador",
        "Consejo",
        "Definición",
        "Problema resuelto",
        "Autoficha",
    ):
        assert heading in tex
    for english in (
        "Preface",
        "How to use this book",
        "Problems",
        "Problem solving",
        "Worked problems",
        "Exam preparation",
        r"\part{Problems}",
        "Gap:",
        "Source status:",
    ):
        assert english not in tex
    chapter, _separator, appendix = tex.partition(r"\chapter{Auditoría de fuentes}")
    assert "Estado de las fuentes:" not in chapter
    assert "Estado de las fuentes:" in appendix
    assert "PENDING" not in chapter
    assert "Los fluidos en conflicto definen esta sección." in chapter
    assert rendered["released"] is False
    assert rendered["project_state"] != "RELEASED"
    assert (root / ".studium" / "state.json").read_bytes() == state_before
    if find_engine() is not None:
        assert rendered["status"] == "rendered"
        pdf = root / "latex" / "draft.pdf"
        assert pdf.read_bytes().startswith(b"%PDF-")
        visible = subprocess.check_output(["pdftotext", str(pdf), "-"], text=True)
        assert "fluidos" in visible
        assert "conflicto" in visible
        assert "Borrador" in visible
        assert "Definición" in visible
        assert "PAR-" not in visible
        assert "con icto" not in visible
    else:
        assert rendered["status"] == "compiler_missing"
        assert rendered["pdf"] is None


def test_paragraph_replace_keeps_the_id_and_rejects_bad_citations(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root, cited = _fluidos(tmp_path)
    dispatch(
        "studium_blueprint_store",
        {"sections": [{"id": "mass", "title": "Conservation of mass"}]},
        session=session,
    )
    excerpt_id = _excerpt(session, cited, "https://example.edu/white", "Steady flow conserves mass.")
    recorded = dispatch(
        "studium_paragraph_record",
        {"section": "mass", "text": "The first draft sentence cites the opened page.", "excerpts": [excerpt_id]},
        session=session,
    )
    state_before = (root / ".studium" / "state.json").read_bytes()
    replaced = dispatch(
        "studium_paragraph_replace",
        {
            "id": "PAR-0001",
            "text": "The rewritten paragraph still teaches from the opened page.",
            "excerpts": [excerpt_id],
        },
        session=session,
    )
    assert replaced["status"] == "replaced"
    assert replaced["paragraph"]["id"] == "PAR-0001"
    assert replaced["paragraph"]["status"] == "draft"
    assert replaced["paragraph"]["classification"] == "PENDING"
    assert replaced["released"] is False
    for absent in ("verified", "accepted", "authority"):
        assert absent not in replaced["paragraph"]
    listed = dispatch("studium_paragraph_list", {}, session=session)
    texts = [item["text"] for item in listed["paragraphs"]]
    assert texts == ["The rewritten paragraph still teaches from the opened page."]
    assert recorded["paragraph"]["text"] not in texts
    assert (root / ".studium" / "state.json").read_bytes() == state_before
    missing = dispatch(
        "studium_paragraph_replace",
        {"id": "PAR-0001", "text": "No excerpt is attached.", "excerpts": ["EVD-9999"]},
        session=session,
    )
    assert missing["status"] != "replaced"
    conflict = _record(session, title="Physical Fluid Dynamics", url="https://example.edu/tritton", year=1988)
    dispatch(
        "studium_public_source_check",
        {"id": conflict, "url": "https://publisher.example/tritton", "title": "Physical Fluid Dynamics", "year": 1977},
        session=session,
    )
    dispatch("studium_public_source_guide_citation", {"id": conflict, "course_guide_cited": True}, session=session)
    conflict_excerpt = _excerpt(session, conflict, "https://publisher.example/tritton", "The page says 1977.")
    refused = dispatch(
        "studium_paragraph_replace",
        {"id": "PAR-0001", "text": "A conflict still cannot support this sentence.", "excerpts": [conflict_excerpt]},
        session=session,
    )
    assert refused["status"] == "rejected"
    uncited = _record(session, title="Wing Theory", url="https://example.edu/wing", year=1990)
    uncited_excerpt = _excerpt(session, uncited, "https://example.edu/wing", "The guide does not cite this page.")
    uncited_refused = dispatch(
        "studium_paragraph_replace",
        {"id": "PAR-0001", "text": "An uncited course source stays out.", "excerpts": [uncited_excerpt]},
        session=session,
    )
    assert uncited_refused["status"] == "rejected"
    assert dispatch("studium_paragraph_list", {}, session=session)["paragraphs"][0]["text"].startswith("The rewritten")
    assert json.loads((root / ".studium" / "state.json").read_text(encoding="utf-8"))["state"] != "RELEASED"


def test_book_next_renders_when_a_section_is_blocked(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _topic(tmp_path, "historia", "Historia medieval")
    source_id = _source(session, "https://open.example/one")
    excerpt_id = _excerpt(session, source_id, "https://open.example/one")
    dispatch(
        "studium_blueprint_store",
        {"sections": [{"id": "tema-1", "title": "Origenes"}]},
        session=session,
    )
    first = dispatch("studium_book_next", {}, session=session)
    assert first["tool"] == "studium_paragraph_record"
    assert first["arguments"]["section"] == "tema-1"
    assert first["arguments"]["excerpts"] == [excerpt_id]
    second = None
    for _ in range(12):
        nxt = dispatch("studium_book_next", {}, session=session)
        assert nxt["ask_user"] is False
        assert nxt["released"] is False
        assert "ask the user" not in json.dumps(nxt).lower()
        if nxt["tool"] == "studium_render":
            second = nxt
            break
    assert second is not None
    assert second["tool"] == "studium_render"
    assert any(item["id"] == "tema-1" for item in second["blocked_sections"])
    rendered = dispatch("studium_render", {}, session=session)
    tex = (root / "latex" / "draft.tex").read_text(encoding="utf-8")
    assert "Gap: this section has no paragraph tied to an opened excerpt." in tex
    assert rendered["released"] is False
    assert json.loads((root / ".studium" / "state.json").read_text(encoding="utf-8"))["state"] != "RELEASED"


def test_youtube_transcript_is_stored_unverified(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    monkeypatch.setattr("urllib.request.OpenerDirector.open", _explode)
    session, root = _topic(tmp_path, "historia", "Historia medieval")
    recorded = dispatch(
        "studium_media_record",
        {
            "url": "https://www.youtube.com/watch?v=dQw4w9wgxcq",
            "title": "Opened lecture",
            "transcript": "The client extracted this caption. It is not a source of truth.",
        },
        session=session,
    )
    assert recorded["status"] == "recorded"
    assert recorded["downloaded"] is False
    assert recorded["released"] is False
    media = recorded["media"]
    assert media["classification"] == "PENDING"
    assert media["authority"] is None
    assert media["transcript_origin"] == "client"
    assert "The client extracted this caption." in media["transcript"]
    assert "verified" not in json.dumps(recorded)
    monkeypatch.setattr("studium.research.media.fetch_public_captions", lambda _video_id: None)
    missing = dispatch(
        "studium_media_record",
        {"url": "https://www.youtube.com/watch?v=abcdefghijk"},
        session=session,
    )
    assert missing["status"] == "captions_missing"
    assert "invented" in missing["message"].lower()
    stored = (root / "media" / "media.jsonl").read_text(encoding="utf-8")
    assert "abcdefghijk" not in stored
    assert "invented transcript" not in stored.lower()


def test_wuolah_note_and_forbidden_license(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    monkeypatch.setattr("urllib.request.OpenerDirector.open", _explode)
    session, _root = _topic(tmp_path, "historia", "Historia medieval")
    note = dispatch(
        "studium_student_notes_record",
        {
            "title": "Apuntes de tema 1",
            "url": "https://www.wuolah.com/documents/tema-1.pdf",
        },
        session=session,
    )
    assert note["status"] == "recorded"
    assert note["released"] is False
    candidate = note["candidate"]
    assert candidate["origin"] == "student_notes"
    assert candidate["kind"] == "wuolah"
    assert candidate["guide_bibliography"] is False
    assert candidate["authority"] is None
    assert candidate["classification"] == "PENDING"
    assert "verified" not in json.dumps(note)
    catalog = dispatch(
        "studium_student_notes_record",
        {"title": "Catalog", "url": "https://wuolah.com/catalog"},
        session=session,
    )
    assert catalog["status"] == "source.catalog_refused"
    forbidden_note = dispatch(
        "studium_student_notes_record",
        {"title": "OpenStax copy", "url": "https://openstax.org/books/university-physics"},
        session=session,
    )
    assert forbidden_note["status"] == "source.license_forbidden"
    assert "OpenStax" in forbidden_note["message"]
    forbidden = dispatch(
        "studium_public_source_record",
        {
            "title": "University Physics",
            "url": "https://openstax.org/books/university-physics-volume-1",
            "license_forbids": True,
        },
        session=session,
    )
    assert forbidden["status"] == "source.license_forbidden"
    allowed = dispatch(
        "studium_public_source_record",
        {"title": "University Physics", "url": "https://openstax.org/books/university-physics-volume-1"},
        session=session,
    )
    assert allowed["status"] == "recorded"
    video = dispatch(
        "studium_media_record",
        {"url": "https://www.youtube.com/videoplayback?id=1", "transcript": "no"},
        session=session,
    )
    assert video["status"] != "recorded"


def _topic(tmp_path, slug: str, topic: str):
    session = open_workspace(str(tmp_path))
    assert dispatch("studium_project_create", {"slug": slug, "topic": topic}, session=session)["status"] == "created"
    return session, tmp_path / slug


def _fluidos(tmp_path):
    session = open_workspace(str(tmp_path))
    assert (
        dispatch(
            "studium_project_create",
            {
                "slug": "fluidos",
                "course": "Mecánica de Fluidos",
                "university": "Universidad de León",
                "degree": "Grado en Ingeniería Aeroespacial",
            },
            session=session,
        )["status"]
        == "created"
    )
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
    cited = _record(session, title="Fluid Mechanics", url="https://example.edu/white", authors=["Frank M. White"], year=2021)
    assert (
        dispatch("studium_public_source_guide_citation", {"id": cited, "course_guide_cited": True}, session=session)[
            "course_guide_cited"
        ]
        is True
    )
    return session, tmp_path / "fluidos", cited


def _source(session, url: str) -> str:
    return _record(session, title="Open page", url=url)


def _record(session, **fields) -> str:
    recorded = dispatch("studium_public_source_record", fields, session=session)
    assert recorded["status"] == "recorded"
    return str(recorded["candidate"]["id"])


def _excerpt(session, source_id: str, url: str, text: str = "A stored excerpt is data, not a source of authority.") -> str:
    opened = dispatch(
        "studium_excerpt_record",
        {"source_id": source_id, "url": url, "text": text},
        session=session,
    )
    assert opened["status"] == "recorded"
    return str(opened["excerpt"]["id"])


def _explode(*_args, **_kwargs):
    raise AssertionError("must not fetch")
