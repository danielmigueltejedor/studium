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
