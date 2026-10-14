"""Conservative classification of stored substitution differences."""

from studium.authoring.substitution_audit import (
    classify_substitution_difference,
)


def test_identical_substitutions():
    latex = r"\frac{2}{3}"
    assert classify_substitution_difference(latex, latex) == "identical"


def test_redundant_quantity_grouping_is_presentation_only():
    stored = r"1.2\,\mathrm{m}^{2} \cdot 3000\,\mathrm{Pa}"
    candidate = (
        r"\left(1.2\,\mathrm{m}^{2}\right) "
        r"\left(3000\,\mathrm{Pa}\right)"
    )
    assert (
        classify_substitution_difference(stored, candidate)
        == "presentation_only"
    )


def test_redundant_grouping_inside_fraction():
    stored = r"\frac{2\,\mathrm{m}}{2}"
    candidate = r"\frac{\left(2\,\mathrm{m}\right)}{2}"
    assert (
        classify_substitution_difference(stored, candidate)
        == "presentation_only"
    )


def test_exponent_moving_from_number_to_unit_requires_review():
    stored = (
        r"\frac{0.2\,\mathrm{m}^{2}}"
        r"{0.1\,\mathrm{m}^{2}}"
    )
    candidate = (
        r"\frac{\left(0.2\,\mathrm{m}\right)^{2}}"
        r"{\left(0.1\,\mathrm{m}\right)^{2}}"
    )
    assert (
        classify_substitution_difference(stored, candidate)
        == "requires_review"
    )


def test_changed_numerical_value_requires_review():
    assert (
        classify_substitution_difference(
            r"\left(2\,\mathrm{m}\right)",
            r"\left(3\,\mathrm{m}\right)",
        )
        == "requires_review"
    )


def test_changed_operation_requires_review():
    assert (
        classify_substitution_difference(
            r"2 + 3",
            r"2 - 3",
        )
        == "requires_review"
    )


def test_large_latex_requires_review():
    assert (
        classify_substitution_difference("a" * 5000, "b" * 5000)
        == "requires_review"
    )



def test_ambiguous_implicit_multiplication():
    stored = r"0.1\,\mathrm{m} 2\,\mathrm{m}\,\mathrm{s}^{-1}"

    candidate = (
        r"\left(0.1\,\mathrm{m}\right) "
        r"\left(2\,\mathrm{m}\,\mathrm{s}^{-1}\right)"
    )

    assert (
        classify_substitution_difference(stored, candidate)
        == "ambiguous_notation"
    )


def test_ambiguous_multiplication_in_hydrostatics():
    stored = (
        r"9.81\,\mathrm{m}\,\mathrm{s}^{-2} "
        r"\cdot 10\,\mathrm{m} 1000\,\mathrm{kg}\,\mathrm{m}^{-3}"
    )

    candidate = (
        r"\left(9.81\,\mathrm{m}\,\mathrm{s}^{-2}\right) "
        r"\left(10\,\mathrm{m}\right) "
        r"\left(1000\,\mathrm{kg}\,\mathrm{m}^{-3}\right)"
    )

    assert (
        classify_substitution_difference(stored, candidate)
        == "ambiguous_notation"
    )


def test_explicit_multiplication_remains_presentation_only():
    stored = r"2\,\mathrm{m} \cdot 3\,\mathrm{m}"

    candidate = (
        r"\left(2\,\mathrm{m}\right) "
        r"\left(3\,\mathrm{m}\right)"
    )

    assert (
        classify_substitution_difference(stored, candidate)
        == "presentation_only"
    )
