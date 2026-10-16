"""Synthetic publishing regressions; no evaluation-book data are modified."""

import shutil
import subprocess

import pytest

from studium.authoring.render import _display_math, emit_prose, render_text_run


@pytest.mark.parametrize("identifier", ["[E2-C05:w_perfil_u_abierto]", "w_perfil_u_abierto", "result_value_final"])
def test_internal_identifiers_are_literal(identifier):
    rendered = render_text_run(identifier + " y σ = F/A")
    assert identifier.replace("_", r"\_") in rendered
    assert r"\(\sigma = F/A\)" in rendered
    assert identifier not in rendered


def test_code_is_opaque_to_math_normalization():
    assert "delta U" in render_text_run("`delta U = x_perfil_abierto`")


def test_double_dollar_result_has_one_display_wrapper():
    tex = "\n".join(_display_math("$$x = 2$$"))
    assert "$" not in tex
    assert tex.count(r"\[") == tex.count(r"\]") == 1


@pytest.mark.skipif(shutil.which("pdflatex") is None, reason="pdflatex unavailable")
def test_identifiers_and_display_results_compile(tmp_path):
    body = "\n".join(emit_prose("[E2-C05:w_perfil_u_abierto] y σ = F/A"))
    body += "\n" + "\n".join(_display_math("$$x = 2$$"))
    source = r"\documentclass{article}\usepackage{amsmath}\begin{document}" + body + r"\end{document}"
    (tmp_path / "regression.tex").write_text(source)
    result = subprocess.run(
        ["pdflatex", "-halt-on-error", "-interaction=nonstopmode", "regression.tex"],
        cwd=tmp_path,
        capture_output=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout.decode(errors="replace")


@pytest.mark.parametrize(
    "expression, operands",
    [
        ("1800000/(2*6000)", ["1800000", "2", "6000"]),
        ("998*9.81*10", ["998", "9.81", "10"]),
        ("sqrt(2*9.81*5)", ["2", "9.81", "5"]),
        ("(1+2)**2/3", ["1", "2", "3"]),
        ("1.20e3/2", ["1.20", "10^{3}", "2"]),
    ],
)
def test_numeric_steps_preserve_the_calculation(expression, operands):
    from studium.authoring.mathematics import numeric_latex

    tex = numeric_latex(expression)
    assert all(operand in tex for operand in operands)
    assert "**" not in tex
    assert "$" not in tex


def test_step_without_symbolic_equation_still_displays_its_operation():
    from studium.authoring.languages import BookLanguage
    from studium.authoring.render import _steps_lines

    # Use the same language object the renderer resolves from a book.
    from studium.domain.languages import describe

    language = describe("en")
    assert isinstance(language, BookLanguage)
    tex = "\n".join(
        _steps_lines(
            [
                {
                    "text": "Substitute the supplied values.",
                    "expression": "1800000/(2*6000)",
                    "expected": "150",
                    "unit": "N/mm",
                }
            ],
            language,
        )
    )
    assert r"\frac{1800000}" in tex
    assert "6000" in tex and r"\mathrm{N}" in tex


def test_nested_record_map_and_compiler_error_location():
    from studium.authoring.publishing import editorial_report, record_lines

    document = "\n".join(
        record_lines({"id": "PRB-1", "section": "ch"}, record_lines({"id": "FIG-1", "section": "ch"}, ["bad equation"]))
    )
    report = editorial_report(
        document, "! Double subscript.\nl.3 bad equation", filename="draft.tex", compiled=False, compiler="pdflatex"
    )
    issue = report["issues"][0]
    assert issue["type"] == "double_subscript"
    assert issue["record"] == "FIG-1"
    assert issue["chapter"] == "ch" and issue["line"] == 3
    assert issue["suggestion"]


@pytest.mark.parametrize(
    "message,kind",
    [
        ("Missing $ inserted.", "missing_math_delimiter"),
        ("Double superscript.", "double_superscript"),
        ("Undefined control sequence.", "undefined_control_sequence"),
    ],
)
def test_file_line_compiler_errors(message, kind):
    from studium.authoring.publishing import parse_log

    issue = parse_log("draft.tex:18: " + message, filename="draft.tex", ranges=[])[0]
    assert issue["type"] == kind and issue["line"] == 18
    assert issue["severity"] == "ERROR"


def test_layout_and_references_are_distinct_from_fatal_errors():
    from studium.authoring.publishing import editorial_report

    log = "Overfull \\hbox (307.9pt too wide) in paragraph at lines 20--22\n"
    log += "LaTeX Warning: Reference `fig:absent' on page 1 undefined on input line 30.\n"
    log += "Underfull \\vbox (badness 10000) has occurred while \\output is active"
    report = editorial_report("", log, filename="draft.tex", compiled=True, compiler="pdflatex")
    assert report["counts"] == {"ERROR": 0, "WARNING": 2, "INFO": 1}
    assert report["issues"][0]["overflow_pt"] == 307.9


@pytest.mark.skipif(shutil.which("pdflatex") is None, reason="pdflatex unavailable")
@pytest.mark.parametrize(
    "equation,kind",
    [
        (r"x_i_j", "double_subscript"),
        (r"x^2^3", "double_superscript"),
        (r"\notACommand{x}", "undefined_control_sequence"),
    ],
)
def test_bad_explicit_math_is_reported_without_removing_it(tmp_path, equation, kind):
    from studium.authoring.publishing import editorial_report, record_lines
    from studium.authoring.render import _compile

    document = "\n".join(
        [
            r"\documentclass{article}\begin{document}",
            *record_lines({"id": "PAR-9", "section": "test"}, [r"\(" + equation + r"\)"]),
            r"\end{document}",
        ]
    )
    path = tmp_path / "draft.tex"
    path.write_text(document)
    compiled, _ = _compile(shutil.which("pdflatex"), path, tmp_path)
    assert not compiled
    log = path.with_suffix(".log").read_text()
    report = editorial_report(document, log, filename="draft.tex", compiled=compiled, compiler="pdflatex")
    issue = next(issue for issue in report["issues"] if issue["type"] == kind)
    assert issue["record"] == "PAR-9"
    assert path.read_text() == document
    assert path.with_suffix(".compiler.log").stat().st_size > 0


def test_long_chain_wraps_only_at_complete_top_level_equalities():
    from studium.authoring.publishing import align_long_chain

    chain = "q = " + "a+b+c+d+" * 15 + "z = 150"
    tex = align_long_chain(chain)
    assert r"\begin{aligned}" in tex and "\n&= 150" in tex
    assert "a+b+c+d+" * 15 in tex
    assert align_long_chain("x = " + "a+" * 100 + "b") == "x = " + "a+" * 100 + "b"
    assert align_long_chain(r"\frac{a=b}{c=d} = x", threshold=1) == r"\frac{a=b}{c=d} = x"


def test_first_pass_undefined_references_do_not_leak_into_final_report(tmp_path, monkeypatch):
    from studium.authoring import render
    from studium.authoring.publishing import editorial_report

    path = tmp_path / "draft.tex"
    path.write_text("")
    calls = []

    def run(_engine, tex_path, _out):
        calls.append(1)
        text = "LaTeX Warning: Reference `fig:x' undefined on input line 4." if len(calls) == 1 else ""
        tex_path.with_suffix(".log").write_text(text)
        return True, ""

    monkeypatch.setattr(render, "_run_latex", run)
    assert render._compile("pdflatex", path, tmp_path)[0]
    assert len(calls) == 2
    report = editorial_report(
        "", path.with_suffix(".log").read_text(), filename="draft.tex", compiled=True, compiler="pdflatex"
    )
    assert report["counts"]["WARNING"] == 0


def test_provenance_comments_do_not_reintroduce_visible_internal_identifiers():
    from studium.authoring.publishing import record_lines, source_map

    document = "\n".join(record_lines({"id": "PAR-42", "section": "ch"}, ["content"]))
    assert "PAR-" not in document
    assert source_map(document)[0]["record"] == "PAR-42"
    assert source_map("% studium:record malformed") == []


@pytest.mark.parametrize("raw, expected", [("abs(-2)", r"\left|"), ("factorial(5)", "!")])
def test_numeric_replay_tokens_are_valid_math(raw, expected):
    from studium.authoring.mathematics import numeric_latex

    assert expected in numeric_latex(raw)
    assert "_" not in numeric_latex(raw)


@pytest.mark.parametrize("raw", ["1_000_000/2", "0x10+1", "__import__('os')", "x+1"])
def test_numeric_formatter_refuses_expressions_outside_replay_language(raw):
    from studium.authoring.mathematics import MathError, numeric_latex

    with pytest.raises(MathError):
        numeric_latex(raw)


@pytest.mark.skipif(shutil.which("pdflatex") is None, reason="pdflatex unavailable")
def test_four_disciplines_keep_symbolic_and_numeric_steps_in_compilable_document(tmp_path):
    from studium.authoring.render import _steps_lines
    from studium.domain.languages import describe

    cases = [
        ("Structural engineering", r"q = \frac{M}{2A}", "1800000/(2*6000)", "N/mm"),
        ("Fluid mechanics", r"p = \rho g h", "998*9.81*10", "Pa"),
        ("Physics", r"F = m a", "2*3", "N"),
        ("Mathematics", r"c = \sqrt{a^2+b^2}", "sqrt(3**2+4**2)", "dimensionless"),
    ]
    body = []
    for discipline, equation, expression, unit in cases:
        body.extend(
            _steps_lines(
                [
                    {"text": discipline + ": state the model.", "equation": equation},
                    {"text": "Substitute the given values.", "expression": expression, "unit": unit},
                ],
                describe("en"),
            )
        )
    source = r"\documentclass{article}\usepackage{amsmath}\begin{document}" + "\n".join(body) + r"\end{document}"
    path = tmp_path / "disciplines.tex"
    path.write_text(source)
    result = subprocess.run(
        ["pdflatex", "-halt-on-error", "-interaction=nonstopmode", path.name],
        cwd=tmp_path,
        capture_output=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout.decode(errors="replace")
    assert all(equation in source for _, equation, _, _ in cases)
    assert r"\frac{1800000}" in source and "9.81" in source and "4" in source


def test_literal_end_record_in_code_does_not_truncate_the_source_map():
    from studium.authoring.publishing import record_lines, source_map

    document = '\n'.join(record_lines({'id': 'PAR-1', 'section': 'ch'},
                                      ['% studium:end-record', 'still in this record']))
    assert source_map(document)[0]['end'] == 3
