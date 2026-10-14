# Verification model

Studium uses deterministic tools to verify mathematical claims. A model opinion is not verification.

## Verification statuses

Each status describes *how* a claim was checked, not that the result is physical truth.

| Status | Meaning |
|---|---|
| `UNVERIFIED` | No check was run or no method could decide. |
| `FAILED` | A check produced a counterexample or mismatch. |
| `COMPUTATION_REPRODUCED` | The server re-evaluated the same arithmetic expression and got the same number. This is a replay, not an independent proof. |
| `NUMERICALLY_CROSS_CHECKED` | A numeric substitution agreed with the claimed value within tolerance. |
| `SYMBOLICALLY_VERIFIED` | A symbolic algebra check (SymPy) confirmed an algebraic identity. |
| `DIMENSIONALLY_VERIFIED` | A dimensional analysis (Pint) confirmed unit consistency. |
| `INDEPENDENTLY_VERIFIED` | Two or more distinct passing methods agreed. |
| `ACADEMICALLY_REVIEWED` | Reserved for human academic review. Never assigned automatically. |

## Combining statuses

When multiple checks run on the same derivation:

- **Any `FAILED` dominates.** The combined status is `FAILED`.
- **`UNVERIFIED` results are ignored** for combination purposes.
- **Two or more distinct passing methods** produce `INDEPENDENTLY_VERIFIED`.
- **A single passing method** keeps its own status.
- **No passing methods** produce `UNVERIFIED`.

`SYMBOLICALLY_VERIFIED` + `UNVERIFIED` is `SYMBOLICALLY_VERIFIED`, not `INDEPENDENTLY_VERIFIED`. A method that could not decide does not count as agreement.

## What verification does not establish

- Physical correctness of assumptions.
- Applicability of a model to a specific problem.
- That the derivation is a valid proof.
- Academic review or endorsement.
- Correctness of the prose explanation.

Verification checks that the stored mathematics is internally consistent using deterministic tools. It does not replace expert review.

## Derivation checks

`studium_derivation_check` accepts three optional check types:

- **symbolic**: algebraic equivalence or equation solving via SymPy.
- **numeric**: substitution of values into an expression and comparison with a claimed result.
- **dimensional**: unit consistency via Pint.

At least one must be provided. Each produces its own status. The overall status is computed by the combination rules above.

## Problem checks

`studium_problem_check` replays a computation or compares with stored excerpts:

- **`two_witnesses`**: two stored excerpts from different sources agree on the answer.
- **`COMPUTATION_REPRODUCED`**: the server re-evaluated the expression and matched.

Neither is mathematical proof. Both are recorded honestly.

## Structured solutions

A worked problem may include a structured solution with given values, unknowns, governing equations, assumptions, intermediate steps, and a final result. Each step that includes an expression and expected value is replayed independently. A step that does not reproduce is reported, not hidden.

The replay engine evaluates numbers, `+ - * / **`, parentheses, `pi`, `e`, and `sqrt`, `cbrt`, `exp`, `log`/`ln`, `log10`, the trigonometric and hyperbolic functions and their inverses, and `abs`. Rational arithmetic with integer powers stays exact; roots, non-integer powers and functions are evaluated in floating point.

### Precision of a stated result

A stated result is read as rounded to its last written digit: `31.30` reproduces `sqrt(2*600/1.225) = 31.298…` but not `31.26`, and `3924` reproduces only values that round to `3924`.

- Precision is read only from the text the client wrote. A computation stores that text as `claimed_text` and replays against it; send the result as a string to keep trailing zeros (a JSON number `31.30` arrives as `31.3`). A record written before `claimed_text` existed is compared exactly, without inferring precision from its stored fraction.
- Comparisons use the unrounded replayed value. The `value` shown in `step_checks` is rounded for display only.
- An integer written with trailing zeros does not say whether they are significant. If it fails the strict reading but would agree with the zeros taken as placeholders (`83300000` for `83333333.3`), the outcome is `ambiguous_precision`, which is not acceptance. Write `8.33e7` or use a decimal point.

### Replay limits

Every intermediate and final value must be zero or have a magnitude between `1e-100` and `1e100`. Integer exponents up to `|1000|` are exact when the result stays in range; non-integer exponents and functions are floating point. A negative base with a non-integer exponent, `sqrt`/`log` of an out-of-domain argument, overflow and underflow are refused with a message naming the cause. `answer_check` values: `replayed`, `ambiguous_precision`, `mismatch`, `not_replayable`.
