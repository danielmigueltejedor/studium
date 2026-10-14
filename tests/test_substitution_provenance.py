"""Regression tests for automatic substitution provenance."""

from studium.authoring.problems import _solution


def _example():
    return {
        "given": [
            {"symbol": "V1", "value": "1", "unit": "m/s"},
            {"symbol": "D1", "value": "0.2", "unit": "m"},
            {"symbol": "D2", "value": "0.1", "unit": "m"},
        ],
        "model": [
            {
                "name": "Ecuación de continuidad",
                "latex": r"V_2 = V_1 \left(\frac{D_1}{D_2}\right)^2",
                "symbolic": "V1*(D1*D1)/(D2*D2)",
            },
        ],
    }


def test_generated_substitution_has_provenance():
    normalized, error = _solution(_example())

    assert error is None
    assert normalized is not None

    assert normalized["substitution_origin"] == "generated"
    assert isinstance(normalized["substitution"], str)
    assert normalized["substitution"]


def test_provided_substitution_is_preserved():
    solution = _example()
    manual = r"\frac{1}{2}"

    solution["substitution"] = manual

    normalized, error = _solution(solution)

    assert error is None
    assert normalized is not None

    assert normalized["substitution"] == manual

    # Explicitly provided content cannot be assumed auto-generated.
    assert "substitution_origin" not in normalized


def test_generated_substitution_does_not_change_result():
    normalized, error = _solution(_example())

    assert error is None
    assert normalized is not None

    substitution = normalized["substitution"]

    assert isinstance(substitution, str)

    # A squared quantity must retain the unit inside the grouping.
    assert r"\left(0.2\,\mathrm{m}\right)" in substitution
    assert r"\left(0.1\,\mathrm{m}\right)" in substitution


def test_generated_origin_survives_normalization():
    first, error = _solution(_example())

    assert error is None
    assert first is not None

    second, error = _solution(first)

    assert error is None
    assert second is not None
    assert second["substitution_origin"] == "generated"
    assert second["substitution"] == first["substitution"]


def test_legacy_substitution_keeps_unknown_origin():
    solution = _example()
    solution["substitution"] = r"\frac{1}{2}"

    normalized, error = _solution(solution)

    assert error is None
    assert normalized is not None
    assert "substitution_origin" not in normalized
