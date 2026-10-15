"""Equation labels: a derivation box must not redefine a label the prose already set.

Found in the second edition of the ULE Fluid Mechanics book: every equation stated both in a paragraph
(``\\begin{equation} ... \\label{eq:x}``) and as a stored derivation with ``equation_id`` ``x`` produced a
second ``\\label{eq:x}`` after the unnumbered display of the derivation box. pdfLaTeX reported 46
"multiply defined" labels, and a derivation-only label pointed at the section counter instead of an
equation number.
"""

import re

from test_render_regression import _excerpts, _project

from studium.authoring.render import render_draft
from studium.mcp.server import dispatch


def _book(tmp_path, monkeypatch, prose_label: bool):
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    session, root = _project(tmp_path)
    dispatch("studium_blueprint_store", {"sections": [{"id": "presion", "title": "Presión hidrostática"}]}, session=session)
    excerpts = _excerpts(session)
    labelled = (
        "La presión de un fluido en reposo crece con la profundidad. Integrando la hidrostática,\n"
        "\\begin{equation}\np = \\rho g h \\label{eq:hidro}\n\\end{equation}\n"
        "y la ecuación \\eqref{eq:hidro} da la presión manométrica."
    )
    plain = "La presión de un fluido en reposo crece con la profundidad y se mide con manómetros de columna."
    dispatch(
        "studium_paragraph_record",
        {"section": "presion", "text": labelled if prose_label else plain, "excerpts": excerpts},
        session=session,
    )
    dispatch(
        "studium_derivation_record",
        {
            "section": "presion",
            "name": "Ecuación hidrostática",
            "equation": r"p = \rho g h",
            "equation_id": "hidro",
            "steps": ["Start from dp/dz = -rho*g", "Integrate"],
        },
        session=session,
    )
    render_draft(root)
    return root, (root / "latex" / "draft.tex").read_text(encoding="utf-8")


def test_prose_label_is_not_repeated_by_the_derivation_box(tmp_path, monkeypatch):
    _root, tex = _book(tmp_path, monkeypatch, prose_label=True)
    assert tex.count(r"\label{eq:hidro}") == 1
    # The surviving label is the prose one, inside a numbered equation environment.
    prose = tex.index(r"\label{eq:hidro}")
    assert tex.rfind(r"\begin{equation}", 0, prose) > tex.rfind(r"\end{equation}", 0, prose)


def test_derivation_only_equation_is_numbered_and_labelled_inside_the_environment(tmp_path, monkeypatch):
    _root, tex = _book(tmp_path, monkeypatch, prose_label=False)
    assert tex.count(r"\label{eq:hidro}") == 1
    match = re.search(r"\\begin\{equation\}\s*p = \\rho g h\s*\\label\{eq:hidro\}\s*\\end\{equation\}", tex)
    assert match, "the derivation equation must be numbered so \\eqref resolves to an equation number"
    # Never a label right after an unnumbered display, which would capture the section counter.
    assert not re.search(r"\\\]\s*\\label\{eq:", tex)
