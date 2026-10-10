"""A book language is stored, loaded into babel, and used for framework chrome."""

import tomllib

import pytest

from studium.authoring.render import find_engine
from studium.cli.app import main
from studium.domain.languages import (
    SPANISH_CHAPTER,
    describe,
    messages,
)
from studium.mcp.server import dispatch, open_workspace

_PROSE = "Density stays constant in the control volume."
_INVALID = "language must be a BCP 47 tag or a TeX babel language name"
_CATALOG = (
    ("es", "spanish", "Enunciado", "Prefacio", "Índice"),
    ("en", "english", "Statement", "Preface", "Contents"),
    ("fr", "french", "Énoncé", "Préface", "Table des matières"),
    ("de", "ngerman", "Aufgabenstellung", "Vorwort", "Inhaltsverzeichnis"),
    ("pt", "portuguese", "Enunciado", "Prefácio", "Índice"),
    ("it", "italian", "Enunciato", "Prefazione", "Indice"),
    ("ca", "catalan", "Enunciat", "Prefaci", "Índex"),
    ("gl", "galician", "Resposta", "Auditoría de fontes", "Índice"),
)


def test_catalog_covers_the_eight_languages_and_galician_gap():
    for code, babel, *_rest in _CATALOG:
        language = describe(code)
        assert language is not None
        assert language.babel == babel
        assert language.loader == "babel"
        assert language.catalog == code
    galician = describe("gl")
    assert galician is not None
    assert messages(galician)["gap"] == "Esta sección está baleira."
    assert messages(galician)["footer"] == "Borrador"
    assert messages(galician)["status_head"] == "Estado das fontes: PENDING."


def test_spanish_book_emits_spanish_babel_and_labels(tmp_path, monkeypatch):
    tex, rendered = _chrome(tmp_path, monkeypatch, "es")
    assert r"\usepackage[spanish]{babel}" in tex
    assert r"\usepackage{polyglossia}" not in tex
    assert r"\AtBeginDocument{\spanishdeactivate{" in tex
    assert r"\renewcommand{\contentsname}{Índice}" in tex
    for label in (
        "Enunciado",
        "Resolución",
        "Respuesta",
        "Consejo",
        "Definición",
        "Problema resuelto",
        "Autoficha",
        "Prefacio",
        "Auditoría de fuentes",
        "Borrador",
        "Estado de las fuentes: PENDING.",
        "Extractos",
        "comprobación rehecha",
    ):
        assert label in tex
    assert "Preface" not in tex
    assert "DRAFT" not in tex
    assert "Statement" not in tex
    assert r"\usepackage[english]{babel}" not in tex
    assert rendered["released"] is False
    assert _PROSE in tex


def test_english_book_emits_english_babel_and_labels(tmp_path, monkeypatch):
    tex, rendered = _chrome(tmp_path, monkeypatch, "en")
    assert r"\usepackage[english]{babel}" in tex
    assert r"\usepackage{polyglossia}" not in tex
    assert "spanishdeactivate" not in tex
    assert r"\renewcommand{\contentsname}{Contents}" in tex
    for label in (
        "Statement",
        "Solution",
        "Answer",
        "Tip",
        "Definition",
        "Worked problem",
        "Self-check",
        "Preface",
        "Source audit",
        "DRAFT",
        "Source status: PENDING.",
        "Excerpts",
        "replayed check",
    ):
        assert label in tex
    assert "Prefacio" not in tex
    assert "Borrador" not in tex
    assert "Enunciado" not in tex
    assert r"\usepackage[spanish]{babel}" not in tex
    assert rendered["released"] is False
    assert _PROSE in tex


def test_catalog_languages_load_their_babel_option_and_chrome(tmp_path, monkeypatch):
    for code, babel, statement, preface, contents in _CATALOG:
        if code in {"es", "en"}:
            continue
        tex, rendered = _chrome(tmp_path, monkeypatch, code, slug=code)
        assert r"\usepackage[" + babel + "]{babel}" in tex
        assert r"\usepackage{polyglossia}" not in tex
        assert r"\renewcommand{\contentsname}{" + contents + "}" in tex
        assert statement in tex
        assert preface in tex
        if code == "gl":
            assert "Folla de fórmulas" in tex
            assert "está vacía" not in tex
        assert rendered["released"] is False
        assert _PROSE in tex


def test_dutch_uses_english_chrome_and_still_renders(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _topic(tmp_path, "dutch", "Dutch", "dutch")
    toml = tomllib.loads((root / "project.toml").read_text(encoding="utf-8"))
    assert toml["course"]["language"] == "dutch"
    _fill(session)
    rendered = dispatch("studium_render", {}, session=session)
    tex = (root / "latex" / "draft.tex").read_text(encoding="utf-8")
    assert r"\usepackage[dutch]{babel}" in tex
    assert r"\usepackage{polyglossia}" not in tex
    assert r"\renewcommand{\contentsname}{Contents}" in tex
    assert "Statement" in tex
    assert "Preface" in tex
    assert "Source audit" in tex
    assert "DRAFT" in tex
    assert "Source status: PENDING." in tex
    assert "Prefacio" not in tex
    assert "Enunciado" not in tex
    assert r"\usepackage[spanish]{babel}" not in tex
    assert _PROSE in tex
    assert rendered["released"] is False
    assert rendered["project_state"] != "RELEASED"
    if find_engine() is not None:
        assert rendered["status"] == "rendered"
        assert (root / "latex" / "draft.pdf").read_bytes().startswith(b"%PDF-")
    else:
        assert rendered["status"] == "compiler_missing"


_COMPILE_LANGS = [lang for lang in _CATALOG if lang[0] not in {"es", "en"}]


@pytest.mark.parametrize("code,babel,statement,preface,contents", _COMPILE_LANGS, ids=[lang[0] for lang in _COMPILE_LANGS])
def test_catalog_language_compiles_to_pdf(tmp_path, monkeypatch, code, babel, statement, preface, contents):
    import subprocess

    engine = find_engine()
    if engine is None:
        pytest.skip("no LaTeX engine")
    ldf = subprocess.run(["kpsewhich", f"{babel}.ldf"], capture_output=True, text=True)
    if ldf.returncode != 0:
        pytest.skip(f"{babel}.ldf not installed")
    _tex, rendered = _chrome(tmp_path, monkeypatch, code, slug=f"compile-{code}")
    assert rendered["status"] == "rendered", f"{code}: {rendered.get('message', rendered.get('status'))}"


def test_missing_language_stays_spanish_even_when_the_prose_is_english(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _topic(tmp_path, "old", "Old book", None)
    assert "language =" not in (root / "project.toml").read_text(encoding="utf-8")
    _fill(session)
    rendered = dispatch("studium_render", {}, session=session)
    tex = (root / "latex" / "draft.tex").read_text(encoding="utf-8")
    assert r"\usepackage[spanish]{babel}" in tex
    assert "Borrador" in tex
    assert r"\chapter{Prefacio}" in tex
    assert "Enunciado" in tex
    assert "Auditoría de fuentes" in tex
    assert _PROSE in tex
    assert "Preface" not in tex
    assert "DRAFT" not in tex
    assert r"\usepackage[english]{babel}" not in tex
    assert rendered["released"] is False


def test_empty_and_nonsense_languages_are_rejected(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    for code in ("", " ", "nope", "not-a-language"):
        rc = main(["create", "rejected", "--topic", "Rejected", "--language", code])
        captured = capsys.readouterr()
        assert rc == 3
        assert _INVALID in captured.err
        assert not (tmp_path / "rejected").exists()

    monkeypatch.chdir(tmp_path)
    rc = main(
        [
            "create",
            "course",
            "--course",
            "Fluids",
            "--university",
            "Test",
            "--degree",
            "Test",
            "--language",
            "nope",
        ]
    )
    captured = capsys.readouterr()
    assert rc == 3
    assert _INVALID in captured.err
    assert not (tmp_path / "course").exists()

    session = open_workspace(str(tmp_path))
    for arguments in (
        {"slug": "mcp-topic", "topic": "Topic", "language": ""},
        {"slug": "mcp-topic", "topic": "Topic", "language": " "},
        {"slug": "mcp-topic", "topic": "Topic", "language": "nope"},
        {
            "slug": "mcp-course",
            "course": "Fluids",
            "university": "Test",
            "degree": "Test",
            "language": "nope",
        },
    ):
        rejected = dispatch("studium_project_create", arguments, session=session)
        assert rejected["status"] == "invalid_language"
        assert rejected["message"] == _INVALID
        assert not (tmp_path / str(arguments["slug"])).exists()


def test_course_and_topic_books_persist_a_normalized_language(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert (
        main(
            [
                "create",
                "curso",
                "--course",
                "Fluids",
                "--university",
                "Test",
                "--degree",
                "Test",
                "--language",
                "DE",
            ]
        )
        == 0
    )
    capsys.readouterr()
    course = tomllib.loads((tmp_path / "curso" / "project.toml").read_text(encoding="utf-8"))
    assert course["course"]["language"] == "de"

    assert main(["create", "tema", "--topic", "Fluids", "--language", "EN"]) == 0
    capsys.readouterr()
    topic = tomllib.loads((tmp_path / "tema" / "project.toml").read_text(encoding="utf-8"))
    assert topic["course"]["language"] == "en"

    session = open_workspace(str(tmp_path))
    french = dispatch(
        "studium_project_create",
        {
            "slug": "francais",
            "course": "Fluides",
            "university": "Test",
            "degree": "Test",
            "language": "fr",
        },
        session=session,
    )
    assert french["status"] == "created"
    stored = tomllib.loads((tmp_path / "francais" / "project.toml").read_text(encoding="utf-8"))
    assert stored["course"]["language"] == "fr"
    brazilian = dispatch(
        "studium_project_create",
        {"slug": "brasil", "topic": "Fluidos", "language": "pt_BR"},
        session=session,
    )
    assert brazilian["status"] == "created"
    brazil = tomllib.loads((tmp_path / "brasil" / "project.toml").read_text(encoding="utf-8"))
    assert brazil["course"]["language"] == "pt-br"
    described = describe("pt-br")
    assert described is not None
    assert described.babel == "brazilian"
    assert described.catalog == "pt"


def test_a_hand_edited_invalid_language_does_not_render_as_spanish(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _topic(tmp_path, "broken", "Broken", "en")
    toml = (root / "project.toml").read_text(encoding="utf-8")
    (root / "project.toml").write_text(
        toml.replace('language = "en"', 'language = "nope"'),
        encoding="utf-8",
    )
    rendered = dispatch("studium_render", {}, session=session)
    assert rendered["status"] == "render.invalid_language"
    assert rendered["message"] == _INVALID
    assert rendered["released"] is False
    assert rendered["pdf"] is None
    assert not (root / "latex" / "draft.tex").exists()


def test_book_next_names_the_book_language(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    english, _root = _topic(tmp_path, "english", "English", "en")
    _contract_ready(english)
    nxt = dispatch("studium_book_next", {}, session=english)
    assert nxt["language"] == "en"
    assert nxt["write_in"] == "English"
    assert "Write a full chapter in English" in nxt["reason"]
    assert "Statement" in nxt["reason"]
    assert "Solution" in nxt["reason"]
    assert "Answer" in nxt["reason"]
    assert "Self-check" in nxt["reason"]
    assert "Tip" in nxt["reason"]
    lowered = nxt["reason"]
    assert "Explicación" not in lowered
    assert "enunciado" not in lowered
    assert "autoficha" not in lowered
    assert "consejo" not in lowered
    assert "in Spanish" not in lowered
    assert nxt["released"] is False

    legacy, _legacy_root = _topic(tmp_path, "legacy", "Legacy", None)
    first = dispatch("studium_book_next", {}, session=legacy)
    assert first["language"] == "es"
    assert first["write_in"] == "Spanish"
    _contract_ready(legacy)
    spanish = dispatch("studium_book_next", {}, session=legacy)
    assert spanish["language"] == "es"
    assert spanish["write_in"] == "Spanish"
    assert SPANISH_CHAPTER in spanish["reason"]
    assert "Explicación" in spanish["reason"]
    assert "consejo" in spanish["reason"]
    assert "autoficha" in spanish["reason"]
    assert spanish["released"] is False


def _chrome(tmp_path, monkeypatch, language: str, slug: str | None = None):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    name = slug or language
    session, root = _topic(tmp_path, name, name, language)
    _fill(session)
    rendered = dispatch("studium_render", {}, session=session)
    tex = (root / "latex" / "draft.tex").read_text(encoding="utf-8")
    return tex, rendered


def _topic(tmp_path, slug: str, topic: str, language: str | None):
    session = open_workspace(str(tmp_path))
    payload: dict[str, object] = {"slug": slug, "topic": topic}
    if language is not None:
        payload["language"] = language
    assert dispatch("studium_project_create", payload, session=session)["status"] == "created"
    return session, tmp_path / slug


def _fill(session) -> None:
    source_id = _source(session, "https://open.example/lang")
    excerpt_id = _excerpt(session, source_id, "https://open.example/lang", text="The opened page states 2.")
    dispatch(
        "studium_blueprint_store",
        {"sections": [{"id": "tema-1", "title": "Continuity"}]},
        session=session,
    )
    dispatch(
        "studium_paragraph_record",
        {"section": "tema-1", "text": _PROSE, "excerpts": [excerpt_id]},
        session=session,
    )
    dispatch(
        "studium_paragraph_record",
        {"section": "tema-1", "role": "consejo", "text": "Keep the units together.", "excerpts": [excerpt_id]},
        session=session,
    )
    dispatch(
        "studium_paragraph_record",
        {
            "section": "tema-1",
            "role": "definition",
            "text": "Density is mass divided by volume.",
            "excerpts": [excerpt_id],
        },
        session=session,
    )
    dispatch(
        "studium_paragraph_record",
        {"section": "tema-1", "role": "self_check", "text": "State the relation.", "excerpts": [excerpt_id]},
        session=session,
    )
    computed = dispatch(
        "studium_computation_check",
        {"expression": "2 + 2", "result": 4, "section": "tema-1"},
        session=session,
    )
    assert computed["status"] == "replayed"


def _contract_ready(session) -> None:
    excerpts = []
    for index in range(12):
        url = f"https://open.example/page-{index}"
        source_id = _source(session, url)
        excerpts.append(_excerpt(session, source_id, url, text=f"Opened page {index} states a stored fact."))
    dispatch(
        "studium_blueprint_store",
        {"sections": [{"id": f"tema-{index}", "title": f"Tema {index}"} for index in range(1, 9)]},
        session=session,
    )
    dispatch(
        "studium_paragraph_record",
        {
            "section": "tema-1",
            "role": "explanation",
            "text": "The explanation develops the balance in the body of the chapter.",
            "excerpts": [excerpts[0]],
        },
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


def _excerpt(session, source_id: str, url: str, text: str = "The opened page states the stored fact.") -> str:
    recorded = dispatch(
        "studium_excerpt_record",
        {"source_id": source_id, "url": url, "text": text},
        session=session,
    )
    assert recorded["status"] == "recorded"
    return str(recorded["excerpt"]["id"])


def _explode(*_args, **_kwargs):
    raise AssertionError("must not fetch")
