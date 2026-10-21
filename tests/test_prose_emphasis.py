"""Prose styling must span opaque literals without interpreting their contents."""

import pytest

from studium.authoring.render import render_text_run


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("**Rust (`vol03`)**: *data races*.", r"\textbf{Rust (\texttt{vol03})}: \emph{data races}."),
        (r"**$2\text{ KiB}$**", r"\textbf{\(2\text{ KiB}\)}"),
        ("**`0` significa éxito**", r"\textbf{\texttt{0} significa éxito}"),
        ("**relanza `CancellationException`**", r"\textbf{relanza \texttt{CancellationException}}"),
        ("**un *actor* seguro**", r"\textbf{un \emph{actor} seguro}"),
        ("***texto***", r"\textbf{\emph{texto}}"),
        ("*usa `x` o $y$*", r"\emph{usa \texttt{x} o \(y\)}"),
        ("**línea uno\nlínea dos**", "\\textbf{línea uno\nlínea dos}"),
        ("**ρ = m/V**", r"\textbf{\(\rho = m/V\)}"),
        ("**x²**", r"\textbf{\(x^{2}\)}"),
        ("*x²*", r"\emph{\(x^{2}\)}"),
        ("**snake_case_name**", r"\textbf{snake\_case\_name}"),
    ],
)
def test_emphasis_includes_literals_and_math(source, expected):
    assert render_text_run(source) == expected


@pytest.mark.parametrize("source", ["`2**3`", "`**kwargs`", r"$a*b*c$", "x * y * z", "x*y*z", "a**b**c"])
def test_literal_operators_never_become_prose_emphasis(source):
    result = render_text_run(source)
    assert r"\emph" not in result
    assert r"\textbf" not in result


def test_marker_inside_code_cannot_close_outer_emphasis():
    result = render_text_run('**lee `"**"` antes de continuar**')
    assert result.startswith(r"\textbf{lee ")
    assert result.endswith(" antes de continuar}")
    assert "**" in result  # This is a literal string, not an unrendered marker.
