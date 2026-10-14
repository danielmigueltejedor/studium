"""F25: replacing a paragraph keeps its academic subsection unless the author moves it."""

from studium.authoring.render import render_draft
from studium.mcp.server import dispatch, open_workspace


def _explode(*_args, **_kwargs):
    raise RuntimeError("network access not allowed in tests")


def _concept(identifier: str) -> dict[str, object]:
    return {
        "id": identifier,
        "title": identifier.upper(),
        "learning_objectives": [f"learn {identifier}"],
        "depth": "ADVANCED_UNDERGRADUATE",
        "exercises": 1,
    }


def _book(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session = open_workspace(str(tmp_path))
    created = dispatch(
        "studium_project_create",
        {"slug": "book", "course": "Fluidos", "university": "ULE", "degree": "Aero", "language": "es", "profile": "STEM"},
        session=session,
    )
    assert created["status"] == "created", created
    assert dispatch("studium_blueprint_store", {"sections": [{"id": "ch1", "title": "Capítulo uno"}]}, session=session)[
        "status"
    ] == "recorded"
    stored = dispatch(
        "studium_academic_blueprint_store",
        {
            "profile_key": "ADVANCED_UNDERGRADUATE",
            "subject": "Fluidos",
            "parts": [
                {
                    "id": "p1",
                    "title": "Parte uno",
                    "chapters": [
                        {
                            "id": "ch1",
                            "title": "Capítulo uno",
                            "learning_objectives": ["learn ch1"],
                            "sections": [
                                {"id": "ch1.a", "title": "Sección Alfa", "concepts": [_concept("ca")]},
                                {
                                    "id": "ch1.b",
                                    "title": "Sección Beta",
                                    "concepts": [_concept("cb")],
                                    "subsections": [{"id": "ch1.b.1", "title": "Apartado Beta uno", "concepts": [_concept("cb1")]}],
                                },
                            ],
                        }
                    ],
                }
            ],
        },
        session=session,
    )
    assert stored["status"] == "recorded", stored
    excerpts = []
    for name, url, text in (
        ("Source A", "https://open.example/a", "Pressure increases with depth linearly in a fluid at rest."),
        ("Source B", "https://open.example/b", "The hydrostatic equation: p = rho * g * h."),
    ):
        source = dispatch("studium_public_source_record", {"title": name, "url": url, "text": text}, session=session)
        source_id = source["candidate"]["id"]
        dispatch(
            "studium_public_source_open_supplement",
            {"id": source_id, "open_supplement": True, "open_licensed": True},
            session=session,
        )
        excerpt = dispatch("studium_excerpt_record", {"source_id": source_id, "url": url, "text": text}, session=session)
        excerpts.append(excerpt["excerpt"]["id"])
    return session, tmp_path / "book", excerpts


def _record(session, excerpts, text, subsection=None, **extra):
    arguments = {"section": "ch1", "text": text, "excerpts": excerpts, **extra}
    if subsection is not None:
        arguments["subsection"] = subsection
    recorded = dispatch("studium_paragraph_record", arguments, session=session)
    assert recorded["status"] == "recorded", recorded
    return recorded["paragraph"]["id"]


def _stored(session, identifier):
    listed = dispatch("studium_paragraph_list", {}, session=session)
    matches = [item for item in listed["paragraphs"] if item["id"] == identifier]
    assert len(matches) == 1, "a replaced paragraph must not be duplicated"
    return matches[0]


def _tex(root):
    rendered = render_draft(root)
    assert rendered["status"] in ("rendered", "compiler_missing", "incomplete"), rendered
    return (root / "latex" / "draft.tex").read_text(encoding="utf-8")


def test_replace_keeps_the_subsection(tmp_path, monkeypatch):
    session, root, excerpts = _book(tmp_path, monkeypatch)
    intro = _record(session, excerpts, "Texto de la introducción del capítulo.")
    target = _record(session, excerpts, "Texto original de la sección beta.", "ch1.b", role="consejo", concepts=["cb"])
    replaced = dispatch(
        "studium_paragraph_replace",
        {"id": target, "text": "Texto corregido de la sección beta.", "excerpts": excerpts},
        session=session,
    )
    assert replaced["status"] == "replaced", replaced
    assert replaced["paragraph"]["subsection"] == "ch1.b"
    stored = _stored(session, target)
    assert stored["subsection"] == "ch1.b"
    assert stored["role"] == "consejo"
    assert stored["concepts"] == ["cb"]
    tex = _tex(root)
    assert tex.index(r"\section{Sección Beta}") < tex.index("Texto corregido de la sección beta")
    assert tex.index("Texto de la introducción") < tex.index(r"\section{Sección Beta}")
    assert "Texto original" not in tex
    assert intro != target


def test_replace_moves_to_an_explicit_subsection(tmp_path, monkeypatch):
    session, root, excerpts = _book(tmp_path, monkeypatch)
    target = _record(session, excerpts, "Párrafo que empieza en la sección alfa.", "ch1.a")
    _record(session, excerpts, "Otro párrafo de la sección alfa.", "ch1.a")
    replaced = dispatch(
        "studium_paragraph_replace",
        {"id": target, "text": "Párrafo trasladado al apartado beta uno.", "excerpts": excerpts, "subsection": "ch1.b.1"},
        session=session,
    )
    assert replaced["status"] == "replaced", replaced
    assert _stored(session, target)["subsection"] == "ch1.b.1"
    tex = _tex(root)
    assert tex.index(r"\subsection{Apartado Beta uno}") < tex.index("Párrafo trasladado al apartado beta uno")


def test_replace_rejects_a_subsection_outside_the_chapter(tmp_path, monkeypatch):
    session, _root, excerpts = _book(tmp_path, monkeypatch)
    target = _record(session, excerpts, "Párrafo de la sección alfa.", "ch1.a")
    rejected = dispatch(
        "studium_paragraph_replace",
        {"id": target, "text": "Párrafo corregido.", "excerpts": excerpts, "subsection": "ch9.x"},
        session=session,
    )
    assert rejected["status"] == "paragraph.subsection_unknown", rejected
    assert "ch1.a" in rejected["message"] and "ch1.b.1" in rejected["message"]
    assert _stored(session, target)["text"] == "Párrafo de la sección alfa."


def test_record_rejects_an_unknown_subsection(tmp_path, monkeypatch):
    session, _root, excerpts = _book(tmp_path, monkeypatch)
    rejected = dispatch(
        "studium_paragraph_record",
        {"section": "ch1", "subsection": "ch1.typo", "text": "Párrafo mal ubicado.", "excerpts": excerpts},
        session=session,
    )
    assert rejected["status"] == "paragraph.subsection_unknown", rejected


def test_replace_removes_the_subsection_when_asked(tmp_path, monkeypatch):
    session, root, excerpts = _book(tmp_path, monkeypatch)
    target = _record(session, excerpts, "Párrafo de la sección alfa.", "ch1.a")
    _record(session, excerpts, "Párrafo de la sección beta.", "ch1.b")
    replaced = dispatch(
        "studium_paragraph_replace",
        {"id": target, "text": "Ahora es la introducción del capítulo.", "excerpts": excerpts, "subsection": None},
        session=session,
    )
    assert replaced["status"] == "replaced", replaced
    assert "subsection" not in replaced["paragraph"]
    assert "subsection" not in _stored(session, target)
    tex = _tex(root)
    assert tex.index("Ahora es la introducción") < tex.index(r"\section{Sección Beta}")


def test_replaced_subsection_survives_a_server_restart(tmp_path, monkeypatch):
    session, _root, excerpts = _book(tmp_path, monkeypatch)
    target = _record(session, excerpts, "Párrafo del apartado beta uno.", "ch1.b.1")
    dispatch("studium_paragraph_replace", {"id": target, "text": "Párrafo corregido del apartado.", "excerpts": excerpts}, session=session)
    restarted = open_workspace(str(tmp_path))
    listed = dispatch("studium_paragraph_list", {"project": "book"}, session=restarted)
    stored = next(item for item in listed["paragraphs"] if item["id"] == target)
    assert stored["subsection"] == "ch1.b.1"
    assert stored["text"] == "Párrafo corregido del apartado."


def test_subsection_text_renders_when_its_section_has_no_direct_paragraph(tmp_path, monkeypatch):
    """Without a chapter introduction, a section holding only subsection text was skipped with its text."""

    session, root, excerpts = _book(tmp_path, monkeypatch)
    _record(session, excerpts, "Texto de la sección alfa.", "ch1.a")
    _record(session, excerpts, "Texto del apartado beta uno.", "ch1.b.1")
    tex = _tex(root)
    assert tex.index(r"\section{Sección Beta}") < tex.index(r"\subsection{Apartado Beta uno}") < tex.index("Texto del apartado beta uno")


def test_paragraph_tool_schemas_document_subsection():
    from studium.mcp.catalog import _TOOLS, _schema

    tools = {schema["name"]: schema for schema in (_schema(tool) for tool in _TOOLS)}
    for name in ("studium_paragraph_record", "studium_paragraph_replace"):
        properties = tools[name]["inputSchema"]["properties"]
        assert "subsection" in properties, name
        assert "academic" in properties["subsection"]["description"].lower()
