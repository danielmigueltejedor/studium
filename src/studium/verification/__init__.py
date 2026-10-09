"""Mathematical verification subsystem.

This package proves small mathematical claims using allowlisted syntax only.
It never executes arbitrary Python, never calls ``eval`` on untrusted input,
and never hands an untrusted string to ``sympy.sympify`` or ``parse_expr``.

The statuses are deliberately distinct:

- ``COMPUTATION_REPRODUCED``: the same expression was evaluated again and the
  number matched. This is a replay, not a proof.
- ``SYMBOLICALLY_VERIFIED``: a symbolic identity holds under the stated
  assumptions. It is not automatically physically valid.
- ``DIMENSIONALLY_VERIFIED``: the units are consistent. A dimensionally
  consistent equation can still be physically wrong.
- ``NUMERICALLY_CROSS_CHECKED``: two independent numeric methods agree on
  sampled points. Sampling is not a proof.
- ``INDEPENDENTLY_VERIFIED``: two or more distinct methods agree.
- ``UNVERIFIED``: the claim could not be decided within the limits.
- ``FAILED``: a counterexample or a mismatch was found.
"""

from studium.verification.dimensional import (
    DimensionCheck,
    DimensionError,
    check_dimensions,
    convert,
    parse_units,
)
from studium.verification.engine import (
    verify_algebraic_equivalence,
    verify_boundary_condition,
    verify_combined,
    verify_derivative,
    verify_dimensions,
    verify_equation,
    verify_integral,
    verify_limit,
    verify_numeric_cross_check,
    verify_substitution,
)
from studium.verification.model import (
    VerificationResult,
    VerificationStatus,
    combine,
)
from studium.verification.parser import (
    ExpressionError,
    ParsedExpression,
    parse_expression,
)

__all__ = [
    "DimensionCheck",
    "DimensionError",
    "ExpressionError",
    "ParsedExpression",
    "VerificationResult",
    "VerificationStatus",
    "check_dimensions",
    "combine",
    "convert",
    "parse_expression",
    "parse_units",
    "verify_algebraic_equivalence",
    "verify_boundary_condition",
    "verify_combined",
    "verify_derivative",
    "verify_dimensions",
    "verify_equation",
    "verify_integral",
    "verify_limit",
    "verify_numeric_cross_check",
    "verify_substitution",
]
