"""The DRAFT is a book. Greek is escaped. Nothing here is RELEASED."""

import json
import re
import subprocess

from studium.authoring.render import emit_prose, find_engine, render_text_run
from studium.mcp.server import dispatch, open_workspace

_GREEK = "Density ρ₀ and viscosity μ meet length ℓ in the sum Σ × ρ."
_PLAIN = "The opened page is the support for a second explanatory paragraph."
_UNCHECKED = "An unchecked draft sentence stays in the draft."


def test_unicode_and_delimited_math_stay_in_math_mode():
    tex = render_text_run("Density ρ₀ and viscosity μ meet length ℓ in the sum Σ × ρ.")
    assert r"\(\rho_{0}\)" in tex
    assert r"\(\mu\)" in tex
    assert r"\(\ell\)" in tex
    assert r"\(\Sigma \times \rho\)" in tex
    assert "Density" in tex
    assert "and viscosity" in tex
    joined = "con ρ₀ ≤ μ y la relación"
    spanish = render_text_run(joined)
    assert r"\(\rho_{0} \leq \mu\)" in spanish
    assert " y la" in spanish
    pressure = render_text_run("La presión cumple p = ρ g h en el punto.")
    assert r"\(p = \rho g h\)" in pressure
    assert "cumple " in pressure
    assert " en el punto." in pressure
    explicit = render_text_run(r"La relación \(E = mc^{2}\) cierra el párrafo.")
    assert r"\(E = mc^{2}\)" in explicit
    assert r"\textbackslash" not in explicit
    dollar = render_text_run(r"la energía $E = mc^2$ basta")
    assert r"\(E = mc^2\)" in dollar
    assert "la energía " in dollar
    for raw in ("ρ", "₀", "μ", "ℓ", "Σ", "×", "≤"):
        assert raw not in tex + spanish + pressure


def test_fenced_code_becomes_a_listing_and_display_math_stays_display():
    src = "Usa el programa.\n\n```c\nint main(void) {\n    return 0;\n}\n```\n"
    tex = "\n".join(emit_prose(src))
    assert r"\begin{lstlisting}[" in tex
    assert "language={C}" in tex
    assert "int main(void)" in tex
    assert "    return 0;" in tex
    assert "```" not in tex
    assert "Usa el programa." in tex
    rust = "\n".join(emit_prose("```rust\nfn main() {}\n```"))
    assert "language={Rust}" in rust
    assert "fn main()" in rust
    inline = render_text_run("Llama a `printf` y sigue.")
    assert r"\texttt{printf}" in inline
    assert "`" not in inline
    displayed = "\n".join(emit_prose("Antes.\n\n\\begin{equation}\nE = mc^{2}\n\\end{equation}\n\nDespués."))
    assert r"\begin{equation}" in displayed
    assert r"\end{equation}" in displayed
    assert r"\textbackslash" not in displayed
    assert "Antes." in displayed
    assert "Después." in displayed
    standalone = "\n".join(emit_prose("ρ = m/V"))
    assert r"\[" in standalone
    assert r"\rho = m/V" in standalone
    assert "ρ" not in standalone


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
            "role": "consejo",
            "text": "Comprueba las unidades antes de sustituir los datos.",
            "excerpts": [excerpt_id],
        },
        session=session,
    )
    dispatch(
        "studium_paragraph_record",
        {
            "section": "tema-1",
            "role": "definition",
            "text": "Se llama densidad a la masa por unidad de volumen.",
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
    assert r"\chapter{Energía}" not in tex
    assert "Esta sección está vacía." not in tex
    assert "Energía: todavía no está escrito" in tex
    assert tex.index("Plan de estudio") < tex.index("Energía: todavía no está escrito")
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
        "Definition",
    ):
        assert english not in tex
    chapter, _separator, appendix = tex.partition(r"\chapter{Auditoría de fuentes}")
    assert "Estado de las fuentes:" not in chapter
    assert "Estado de las fuentes:" in appendix
    assert "PENDING" not in chapter
    assert "Los fluidos en conflicto definen esta sección." in chapter
    assert tex.count(r"\begin{tcolorbox}[title={Problema resuelto}") == 1
    assert tex.count(r"\begin{tcolorbox}[title={Consejo}") == 1
    assert "La definición permanece ligada a la página abierta." in _outside_boxes(tex)
    assert rendered["released"] is False
    assert rendered["project_state"] != "RELEASED"
    assert (root / ".studium" / "state.json").read_bytes() == state_before
    if find_engine() is not None:
        assert rendered["status"] == "incomplete"
        assert rendered["message"] == "The book is incomplete. Write the next unwritten chapter: Energía."
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


def test_spanish_prose_without_a_stored_language_uses_spanish_headings(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session = open_workspace(str(tmp_path))
    created = dispatch(
        "studium_project_create",
        {"slug": "fluidos", "topic": "Fluidos"},
        session=session,
    )
    assert created["status"] == "created"
    root = tmp_path / "fluidos"
    assert "language =" not in (root / "project.toml").read_text(encoding="utf-8")
    source_id = _source(session, "https://open.example/fluidos")
    excerpt_id = _excerpt(session, source_id, "https://open.example/fluidos", "La pagina abierta describe el fluido.")
    dispatch(
        "studium_blueprint_store",
        {"sections": [{"id": "continuidad", "title": "Continuidad"}]},
        session=session,
    )
    dispatch(
        "studium_paragraph_record",
        {
            "section": "continuidad",
            "text": "La densidad del fluido permanece constante en el volumen de control.",
            "excerpts": [excerpt_id],
        },
        session=session,
    )
    dispatch(
        "studium_paragraph_record",
        {
            "section": "continuidad",
            "role": "definition",
            "text": "Se llama densidad a la masa por unidad de volumen.",
            "excerpts": [excerpt_id],
        },
        session=session,
    )
    state_before = (root / ".studium" / "state.json").read_bytes()
    dispatch("studium_render", {}, session=session)
    toc = root / "latex" / "draft.toc"
    toc.parent.mkdir(parents=True, exist_ok=True)
    toc.write_text(
        "\\contentsline {part}{Problems}{2}{}\n\\contentsline {chapter}{Exam preparation}{4}{}\n",
        encoding="utf-8",
    )
    rendered = dispatch("studium_render", {}, session=session)
    tex = (root / "latex" / "draft.tex").read_text(encoding="utf-8")
    assert r"\begin{tcolorbox}[title={Definición}" in tex
    assert "Borrador" in tex
    assert r"\chapter{Prefacio}" in tex
    assert "Cómo usar este libro" in tex
    assert "Notación" in tex
    assert "Hoja de fórmulas" in tex
    assert "Auditoría de fuentes" in tex
    assert "Preface" not in tex
    assert "Definition" not in tex
    assert "DRAFT" not in tex
    assert "How to use this book" not in tex
    assert "Notation" not in tex
    assert "Formula sheet" not in tex
    assert "Source audit" not in tex
    assert "La densidad del fluido permanece constante en el volumen de control." in _outside_boxes(tex)
    assert rendered["released"] is False
    assert (root / ".studium" / "state.json").read_bytes() == state_before
    if find_engine() is not None:
        assert rendered["status"] == "rendered"
        rebuilt = toc.read_text(encoding="utf-8")
        assert "Problems" not in rebuilt
        assert "Exam preparation" not in rebuilt
        visible = subprocess.check_output(["pdftotext", str(root / "latex" / "draft.pdf"), "-"], text=True)
        assert "Definición" in visible
        assert "Borrador" in visible
        assert "Preface" not in visible
        assert "Definition" not in visible
        assert "Exam preparation" not in visible
        assert "Problems" not in visible
    else:
        assert rendered["status"] == "compiler_missing"
        assert not toc.exists()


def test_explanation_stays_outside_the_one_worked_problem_box(tmp_path, monkeypatch):
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
    excerpt_id = _excerpt(session, source_id, "https://open.example/fluidos", "La página abierta describe el balance.")
    dispatch(
        "studium_blueprint_store",
        {"sections": [{"id": "tema-1", "title": "Continuidad"}]},
        session=session,
    )
    explanation = "La explicación desarrolla el balance en varios párrafos y no cabe en una caja."
    dispatch(
        "studium_paragraph_record",
        {"section": "tema-1", "role": "explanation", "text": explanation, "excerpts": [excerpt_id]},
        session=session,
    )
    dispatch(
        "studium_paragraph_record",
        {
            "section": "tema-1",
            "role": "definition",
            "text": "Se llama densidad a la masa por unidad de volumen.",
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
    rendered = dispatch("studium_render", {}, session=session)
    tex = (root / "latex" / "draft.tex").read_text(encoding="utf-8")
    assert tex.count(r"\begin{tcolorbox}[title={Problema resuelto}") == 1
    assert "Enunciado" in tex
    assert "Resolución" in tex
    assert "Respuesta" in tex
    outside = _outside_boxes(tex)
    assert explanation in outside
    assert r"\section{Explicación}" in outside
    assert rendered["released"] is False
    assert rendered["project_state"] != "RELEASED"


def test_consejo_paragraph_becomes_a_tcolorbox_with_babel_spanish(tmp_path, monkeypatch):
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
    excerpt_id = _excerpt(session, source_id, "https://open.example/fluidos", "La página abierta describe el balance.")
    dispatch(
        "studium_blueprint_store",
        {"sections": [{"id": "tema-1", "title": "Continuidad"}]},
        session=session,
    )
    explanation = "La explicación desarrolla el balance en el cuerpo del capítulo."
    dispatch(
        "studium_paragraph_record",
        {"section": "tema-1", "role": "explanation", "text": explanation, "excerpts": [excerpt_id]},
        session=session,
    )
    dispatch(
        "studium_paragraph_record",
        {
            "section": "tema-1",
            "role": "consejo",
            "text": "Comprueba las unidades antes de sustituir los datos.",
            "excerpts": [excerpt_id],
        },
        session=session,
    )
    dispatch(
        "studium_paragraph_record",
        {
            "section": "tema-1",
            "text": "Consejo: No mezcles las unidades en el mismo término.",
            "excerpts": [excerpt_id],
        },
        session=session,
    )
    dispatch(
        "studium_paragraph_record",
        {
            "section": "tema-1",
            "text": "Definición: Se llama densidad a la masa por unidad de volumen.",
            "excerpts": [excerpt_id],
        },
        session=session,
    )
    dispatch(
        "studium_paragraph_record",
        {
            "section": "tema-1",
            "text": "Autoficha: Escribe la relación con tus palabras.",
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
    rendered = dispatch("studium_render", {}, session=session)
    tex = (root / "latex" / "draft.tex").read_text(encoding="utf-8")
    assert r"\usepackage[spanish]{babel}" in tex
    assert r"\usepackage[a4paper,margin=2.5cm]{geometry}" in tex
    assert r"\usepackage{titlesec}" in tex
    assert r"\let\cleardoublepage\clearpage" in tex
    assert r"\renewcommand{\contentsname}{Índice}" in tex
    assert "Contents" not in tex
    assert "Cada párrafo sustantivo cita un extracto almacenado." not in tex
    assert "Borrador" in tex
    assert tex.count(r"\begin{tcolorbox}[title={Consejo}") == 1
    assert tex.count(r"\begin{tcolorbox}[title={Definición}") == 1
    assert tex.count(r"\begin{tcolorbox}[title={Problema resuelto}") == 1
    assert tex.count(r"\begin{tcolorbox}[title={Autoficha}") == 1
    assert "Enunciado" in tex
    assert "Resolución" in tex
    assert "Respuesta" in tex
    assert "Consejo:" not in tex
    assert "Definición:" not in tex
    assert "Autoficha:" not in tex
    outside = _outside_boxes(tex)
    assert explanation in outside
    assert "No mezcles las unidades en el mismo término." not in outside
    assert "Se llama densidad a la masa por unidad de volumen." not in outside
    assert "Escribe la relación con tus palabras." not in outside
    assert r"\section{Explicación}" in outside
    assert rendered["released"] is False
    if find_engine() is not None:
        assert rendered["status"] == "rendered"
        visible = subprocess.check_output(["pdftotext", "-layout", str(root / "latex" / "draft.pdf"), "-"], text=True)
        pages = visible.split("\f")
        if pages and not pages[-1].strip():
            pages = pages[:-1]
        assert pages
        assert all(page.strip() not in {"", "Borrador"} for page in pages)
        assert "Índice" in visible
        assert "Contents" not in visible


def test_draft_cover_math_code_boxes_and_figure_caption(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session = open_workspace(str(tmp_path))
    created = dispatch(
        "studium_project_create",
        {"slug": "programacion", "topic": "Programación en C", "language": "es"},
        session=session,
    )
    assert created["status"] == "created"
    root = tmp_path / "programacion"
    source_id = _source(session, "https://open.example/c")
    excerpt_id = _excerpt(session, source_id, "https://open.example/c", "La página abierta describe el bucle.")
    dispatch(
        "studium_blueprint_store",
        {
            "sections": [
                {"id": "tema-1", "title": "Bucles"},
                {"id": "tema-2", "title": "Figuras"},
            ]
        },
        session=session,
    )
    explanation = (
        "La suma recorre los índices con ρ₀ ≤ μ y la relación \\(E = mc^{2}\\).\n\n"
        "ρ = m/V\n\n"
        "```c\n"
        "int main(void) {\n"
        "    return 0;\n"
        "}\n"
        "```"
    )
    dispatch(
        "studium_paragraph_record",
        {"section": "tema-1", "role": "explanation", "text": explanation, "excerpts": [excerpt_id]},
        session=session,
    )
    dispatch(
        "studium_paragraph_record",
        {
            "section": "tema-1",
            "role": "consejo",
            "text": "Comprueba el índice antes de leer el elemento.",
            "excerpts": [excerpt_id],
        },
        session=session,
    )
    dispatch(
        "studium_paragraph_record",
        {
            "section": "tema-1",
            "role": "definition",
            "text": "Se llama bucle a una repetición con una condición de salida.",
            "excerpts": [excerpt_id],
        },
        session=session,
    )
    dispatch(
        "studium_paragraph_record",
        {
            "section": "tema-1",
            "role": "self_check",
            "text": "Escribe el mismo bucle con tus palabras.",
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
    dispatch(
        "studium_paragraph_record",
        {
            "section": "tema-2",
            "role": "explanation",
            "text": "El dibujo acompaña la explicación y no sustituye la comprobación.",
            "excerpts": [excerpt_id],
        },
        session=session,
    )
    scheme = dispatch(
        "studium_figure_record",
        {
            "section": "tema-1",
            "caption": "Esquema del bucle.",
            "kind": "python",
            "source": _PLOT,
            "excerpts": [excerpt_id],
        },
        session=session,
    )
    measured = dispatch(
        "studium_figure_record",
        {
            "section": "tema-2",
            "caption": "La longitud dibujada es 2.",
            "kind": "python",
            "source": _PLOT,
            "excerpts": [excerpt_id],
        },
        session=session,
    )
    assert dispatch("studium_figure_check", {"id": scheme["figure"]["id"]}, session=session)["checked"] is True
    assert dispatch("studium_figure_check", {"id": measured["figure"]["id"]}, session=session)["checked"] is True
    rendered = dispatch("studium_render", {}, session=session)
    tex = (root / "latex" / "draft.tex").read_text(encoding="utf-8")
    cover = tex.split(r"\begin{document}", 1)[1].split(r"\clearpage", 1)[0]
    assert r"\maketitle" not in tex
    assert "Studium" in cover
    assert "Programación en C" in cover
    assert "Apuntes de trabajo" in cover
    assert "Borrador" in cover
    assert "No publicado" in cover
    assert "Edición 0.1.0" in cover
    assert r"\today" in cover
    assert r"\vspace*{0.08\textheight}" in cover
    assert r"\vfill" in cover
    assert cover.index("Studium") < cover.index("Programación en C") < cover.index("Apuntes de trabajo")
    assert cover.index("Apuntes de trabajo") < cover.index("Borrador") < cover.index("Edición 0.1.0")
    assert "DRAFT" not in tex
    assert "Not released" not in tex
    assert r"\(E = mc^{2}\)" in tex
    assert r"\(\rho_{0} \leq \mu\)" in tex
    assert r"\[" in tex
    assert r"\rho = m/V" in tex
    assert r"\textbackslash{}(" not in tex
    assert "ρ" not in tex
    assert "```" not in tex
    assert r"\begin{lstlisting}[" in tex
    assert "language={C}" in tex
    assert r"\ttfamily" in tex
    assert "int main(void) {" in tex
    assert "    return 0;" in tex
    assert "studiumtip" in tex
    assert "studiumdef" in tex
    assert "studiumworked" in tex
    assert "studiumcheck" in tex
    backs = [
        _color(tex, "studiumTipBack"),
        _color(tex, "studiumDefBack"),
        _color(tex, "studiumWorkedBack"),
        _color(tex, "studiumCheckBack"),
    ]
    frames = [
        _color(tex, "studiumTipFrame"),
        _color(tex, "studiumDefFrame"),
        _color(tex, "studiumWorkedFrame"),
        _color(tex, "studiumCheckFrame"),
    ]
    assert len(set(backs)) == 4
    assert len(set(frames)) == 4
    assert set(backs).isdisjoint(frames)
    outside = _outside_boxes(tex)
    assert "La suma recorre los índices" in outside
    assert "int main(void)" in outside
    assert "Comprueba el índice antes de leer el elemento." not in outside
    assert "Se llama bucle a una repetición con una condición de salida." not in outside
    chapter, _marker, appendix = tex.partition(r"\chapter{Auditoría de fuentes}")
    assert "Una figura no demuestra la ciencia." not in tex
    assert "A figure does not prove the science." not in tex
    assert "Esquema del bucle." in chapter
    assert r"\includegraphics" in chapter
    assert r"\textheight/100*38" in chapter
    assert r"\linewidth" in chapter
    assert "La cifra del pie sigue sin comprobar." not in chapter
    assert "La cifra del pie sigue sin comprobar." in appendix
    assert rendered["released"] is False
    assert rendered["project_state"] != "RELEASED"
    if find_engine() is not None:
        assert rendered["status"] == "rendered", rendered["message"]
        pdf = root / "latex" / "draft.pdf"
        assert pdf.read_bytes().startswith(b"%PDF-")
        visible = subprocess.check_output(["pdftotext", "-layout", str(pdf), "-"], text=True)
        assert "Programación en C" in visible
        assert "Borrador" in visible
        assert "int main" in visible
        assert "Una figura no demuestra la ciencia." not in visible
    else:
        assert rendered["status"] == "compiler_missing"
        assert not (root / "latex" / "draft.pdf").exists()


def _color(tex: str, name: str) -> str:
    match = re.search(r"\\definecolor\{" + name + r"\}\{RGB\}\{([^}]+)\}", tex)
    assert match is not None
    return match.group(1)


_PNG = (
    "89504e470d0a1a0a0000000d49484452000000010000000108000000003a7e9b55"
    "0000000a49444154789c63f80f0001010100b138f6140000000049454e44ae426082"
)
_PLOT = "import pathlib\n" f'pathlib.Path("figure.png").write_bytes(bytes.fromhex("{_PNG}"))\n'


def _outside_boxes(tex: str) -> str:
    return re.sub(r"\\begin\{tcolorbox\}.*?\\end\{tcolorbox\}", "", tex, flags=re.S)


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


def test_book_next_does_not_render_a_short_blocked_book(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _topic(tmp_path, "historia", "Historia medieval")
    _excerpt(session, _source(session, "https://open.example/one"), "https://open.example/one")
    dispatch(
        "studium_blueprint_store",
        {"sections": [{"id": "tema-1", "title": "Origenes"}]},
        session=session,
    )
    first = dispatch("studium_book_next", {}, session=session)
    assert first["tool"] == "studium_blueprint_store"
    assert first["tool"] != "studium_render"
    assert first["reason"] == (
        "The study book is too short. Store at least 8 blueprint sections before writing or rendering."
    )
    for _ in range(4):
        nxt = dispatch("studium_book_next", {}, session=session)
        assert nxt["tool"] != "studium_render"
        assert nxt["released"] is False
        assert "ask the user" not in json.dumps(nxt).lower().replace("do not ask the user how to format the page.", "")
    rendered = dispatch("studium_render", {}, session=session)
    tex = (root / "latex" / "draft.tex").read_text(encoding="utf-8")
    assert "Gap: this section has no paragraph tied to an opened excerpt." not in tex
    assert r"\chapter{Origenes}" not in tex
    assert "Origenes: not written yet" in tex
    assert tex.index("Study plan") < tex.index("Origenes: not written yet")
    assert rendered["status"] == "incomplete"
    assert rendered["message"] == "The book is incomplete. Write the next unwritten chapter: Origenes."
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
