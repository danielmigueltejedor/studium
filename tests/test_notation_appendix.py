"""F38: the notation appendix breaks across pages and loses no entry."""

import re
import shutil
import subprocess

import pytest
from test_render_regression import _full_setup

from studium.authoring.render import render_draft
from studium.mcp.server import dispatch

_GREEK = ["alpha", "beta", "gamma", "delta", "epsilon", "theta", "lambda", "mu", "nu", "rho", "sigma", "tau", "phi", "omega"]


def _notation_book(tmp_path, monkeypatch, count: int):
    session, root = _full_setup(tmp_path, monkeypatch)
    for index in range(count):
        base = _GREEK[index % len(_GREEK)]
        symbol = f"{base}_{index}"
        meaning = f"magnitud{index:04d} "
        if index % 7 == 0:
            meaning += "con una descripción larga que debe partirse en varias líneas dentro de la columna " * 2
        recorded = dispatch(
            "studium_notation_record",
            {"section": "presion", "symbol": symbol, "meaning": meaning.strip(), "units": "kg/m^3" if index % 3 else ""},
            session=session,
        )
        assert recorded["status"] == "recorded", recorded
    return session, root


def test_notation_appendix_is_a_breakable_longtable(tmp_path, monkeypatch):
    _session, root = _notation_book(tmp_path, monkeypatch, 40)
    render_draft(root)
    tex = (root / "latex" / "draft.tex").read_text(encoding="utf-8")
    appendix = tex[tex.index(r"\chapter{Notación}"):]
    appendix = appendix[: appendix.index(r"\end{longtable}")]
    assert r"\begin{longtable}" in appendix
    assert r"\begin{tabular}" not in appendix
    assert r"\endhead" in appendix and r"\endfirsthead" in appendix
    assert r"\usepackage{longtable}" in tex
    # 40 recorded here plus the one from the fixture.
    assert appendix.count(r"\\") >= 41


@pytest.mark.skipif(shutil.which("pdflatex") is None or shutil.which("pdftotext") is None, reason="needs pdflatex and pdftotext")
def test_three_hundred_notation_entries_are_all_visible_in_the_pdf(tmp_path, monkeypatch):
    _session, root = _notation_book(tmp_path, monkeypatch, 300)
    rendered = render_draft(root)
    pdf = root / "latex" / "draft.pdf"
    assert pdf.exists(), rendered
    log = (root / "latex" / "draft.log").read_text(encoding="latin-1")
    start = log.index("Notaci") if "Notaci" in log else 0
    assert not re.search(r"Overfull \\vbox", log[start:]), "the notation table overflows the page"
    text = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True, check=True).stdout
    flat = re.sub(r"\s+", " ", text)
    missing = [index for index in range(300) if f"magnitud{index:04d}" not in flat]
    assert missing == []
