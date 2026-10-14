"""Regression tests for grouped numerical substitutions."""

from studium.authoring.mathematics import substitution_latex


def test_squared_lengths_include_numerical_values():
    latex = substitution_latex(
        "V1*(D1*D1)/(D2*D2)",
        {
            "V1": ("1", "m/s"),
            "D1": ("0.2", "m"),
            "D2": ("0.1", "m"),
        },
    )

    assert r"\left(0.2\,\mathrm{m}\right)^{2}" in latex
    assert r"\left(0.1\,\mathrm{m}\right)^{2}" in latex
    assert r"0.2\,\mathrm{m}^{2}" not in latex


def test_squared_velocities_are_grouped():
    latex = substitution_latex(
        "rho*(V2*V2-V1*V1)/2",
        {
            "rho": ("1000", "kg/m^3"),
            "V1": ("1", "m/s"),
            "V2": ("4", "m/s"),
        },
    )

    compact = latex.replace(
        r"\left(\left(", r"\left("
    ).replace(
        r"\right)\right)", r"\right)"
    )

    assert r"\left(4\,\mathrm{m}\,\mathrm{s}^{-1}\right)^{2}" in compact
    assert r"\left(1\,\mathrm{m}\,\mathrm{s}^{-1}\right)^{2}" in compact
