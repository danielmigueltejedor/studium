"""F37: a figure that fits at natural size keeps its size instead of shrinking to zero width."""

import re
import shutil
import subprocess

import pytest

from studium.authoring.render import _fit_block

pytestmark = pytest.mark.skipif(shutil.which("pdflatex") is None, reason="needs pdflatex")


def _blank_pdf(path, width: float, height: float) -> None:
    """A one-page PDF of exactly width x height points (one stroked box, so it has content)."""

    content = f"0 0 0 RG 1 w 1 1 {width - 2:.2f} {height - 2:.2f} re S".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] /Contents 4 0 R /Resources << >> >>".encode(),
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(bytes(out))


# (name, width bp, height bp); TeX reports pt (1 bp = 72.27/72 pt). The book is A4 with 2.5 cm margins: \linewidth 455.24pt,
# 0.38 \textheight = 267.0pt.
_CASES = [
    ("small", 120.0, 80.0),  # natural size
    ("plot", 430.0, 250.0),  # book-01 Python plots: natural size, previously zero width
    ("wide", 900.0, 300.0),  # scaled down to \linewidth
    ("tall", 200.0, 900.0),  # scaled down to 0.38 \textheight
    ("letter", 612.0, 792.0),  # TikZ letter-size page: both limits
]


def _measure(tmp_path, consume_box: bool) -> dict[str, tuple[float, float]]:
    body: list[str] = [
        r"\documentclass{book}",
        r"\usepackage[a4paper,margin=2.5cm]{geometry}",
        r"\usepackage{graphicx}",
        r"\begin{document}",
        r"\typeout{LINEWIDTH:\the\linewidth}",
    ]
    for name, width, height in _CASES:
        _blank_pdf(tmp_path / f"{name}.pdf", width, height)
        graphic = r"\includegraphics{" + name + ".pdf}"
        block = _fit_block(graphic, consume_box=consume_box)
        body.append(r"\setbox1=\hbox{" + "\n".join(block) + "}")
        body.append(r"\typeout{FIT:" + name + r":\the\wd1:\the\ht1}")
        body.append(r"\noindent\box1\par")
    body.append(r"\end{document}")
    (tmp_path / "fit.tex").write_text("\n".join(body), encoding="utf-8")
    run = subprocess.run(
        ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "fit.tex"], cwd=tmp_path, capture_output=True, text=True
    )
    assert run.returncode == 0, run.stdout[-3000:]
    log = (tmp_path / "fit.log").read_text(encoding="latin-1")
    sizes = {}
    for name, width, height in re.findall(r"FIT:(\w+):([\d.]+)pt:([\d.]+)pt", log):
        sizes[name] = (float(width), float(height))
    return sizes


@pytest.mark.parametrize("consume_box", [True, False])
def test_fit_block_keeps_natural_size_and_scales_large_figures(tmp_path, consume_box):
    sizes = _measure(tmp_path, consume_box)
    linewidth = 455.24
    cap = 267.0
    for name, width, height in _CASES:
        got_width, got_height = sizes[name]
        assert got_width > 1.0, f"{name} rendered with zero width"
        assert got_width <= linewidth + 0.5, name
        assert got_height <= max(cap, 0) + 0.5, name
        # Aspect ratio preserved.
        assert abs(got_width / got_height - width / height) < 0.01 * width / height, name
    bp = 72.27 / 72
    assert sizes["small"] == pytest.approx((120.0 * bp, 80.0 * bp), abs=0.5)
    assert sizes["plot"] == pytest.approx((430.0 * bp, 250.0 * bp), abs=0.5)
    assert sizes["wide"][0] == pytest.approx(linewidth, abs=0.5)
    assert sizes["tall"][1] == pytest.approx(cap, abs=0.5)


def test_fit_block_never_reads_the_width_of_a_consumed_box():
    lines = "\n".join(_fit_block(r"\includegraphics{x.pdf}", consume_box=True))
    assert r"\resizebox{\wd0}" not in lines


def test_centered_figure_keeps_line_breaks_inside_unaligned_nodes(tmp_path):
    """A node with ``\\\\`` and no alignment compiles inside the centred figure box."""

    from studium.authoring.render import _TIKZ_LINEBREAK

    def compile_with(prefix: str) -> int:
        tex = tmp_path / "t.tex"
        tex.write_text(
            "\\documentclass{article}\\usepackage{tikz}\\begin{document}\n"
            "\\noindent\\begin{minipage}{\\linewidth}\\centering\n"
            + prefix
            + "\n\\begin{tikzpicture}\\node[draw] {uno\\\\ dos};\\end{tikzpicture}\n"
            "\\end{minipage}\\end{document}\n",
            encoding="utf-8",
        )
        done = subprocess.run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "t.tex"],
                              cwd=tmp_path, capture_output=True, check=False)
        return done.returncode

    assert compile_with("") != 0  # the failure this guards against
    assert compile_with(_TIKZ_LINEBREAK) == 0
