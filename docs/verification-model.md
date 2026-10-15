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

A numeric problem reports three separate kinds of evidence, and none of them is scientific validity:

- **Source independence** (`two_witnesses`): the two cited excerpts come from different public sources. It does not mean they state the answer.
- **Answer arithmetic** (`answer_check`): the unrounded value of the final replayed step reproduces the stated answer at its written precision (`replayed`), does not (`mismatch`), only would with trailing zeros read as placeholders (`ambiguous_precision`), or cannot be replayed (`not_replayable`).
- **Model reproduction** (`studium_problem_scientific_review`): the stored model evaluated with the stored given values reproduces the stated answer in the unit of the final step. Without a caller-supplied value, the review uses the problem's own `expected`. A model that does not give the answer is `FAILED` even when the step arithmetic replays.

The review always reports `scientific_validity: not_established` and `human_review_required`. The draft prints the answer check under each solution and says that an arithmetic reproduction does not validate the physical model.

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

## Equations in prose

Grounding works on complete relations. Every `$…$`, `$$…$$`, `\(…\)` and `\[…\]` span is split at top-level separators (`\quad`, `, `, `;`, `\text{ … }`, `\\`) and relation operators, so `a = b = c` gives `a = b` and `b = c`; plain-text relations outside math spans are kept only when both sides are whole. A fragment such as `= -p` is never a statement, and a relation is never grounded because its text is a substring of a longer one. The statement is kept exactly as written.

Each equation claim gets the strongest status its stored evidence gives that exact statement:

| Status | Evidence | Blocks the evidence audit |
|---|---|---|
| `symbolically_verified` | final equation of a derivation whose check is symbolic or independent, or a passing `studium_math_verify` equation/equivalence | no |
| `dimensionally_verified` | final equation of a derivation with only a dimensional check | no |
| `numerically_reproduced` | a replayed computation, a derivation with only a numeric check, or numbers that hold at their written precision | no |
| `source_supported` | a cited excerpt states the whole relation (not a proof) | no |
| `follows_from_stated_premises` | a calculation (derivatives, integrals, matrix products, algebra) shows the relation follows from definitions stated earlier in the same paragraph; the definitions keep their own status | no — needs human review of the premises |
| `derived_steps_unchecked` | only an intermediate step of a checked derivation states it | no |
| `numerically_ambiguous` | numbers that hold only if trailing zeros are placeholders | no |
| `not_machine_checkable` | nothing backs it and the relation parser cannot read it | no — needs human review |
| `unsupported` | nothing backs it although the parser can read it | yes |
| `contradicted` | its own numbers do not hold | yes |
| `verification_failed` | a stored check of the same equation failed and nothing passing backs it | yes |

Definitions (`\equiv`, `:=`), approximations (`\approx`) and values or conditions (`x = 0`, `r = R`) are not claims. An unparseable equation can only be `source_supported` or `not_machine_checkable`; it is never verified by the parser. `studium_equation_report` lists every equation with its status, evidence ids, whether it is a display equation and whether a person must still review it. The source-audit appendix prints only per-paragraph counts, never a label after each equation.

Draft, evidence audit, scientific verification, human approval and publication readiness are separate stages (`stages` in `studium_quality_report` and `studium_book_review`). A draft renders with unverified mathematics; `audit_passed` is the evidence audit only; scientific verification is complete only when every equation claim is verified; no human approval is recorded by Studium yet.

### Derivatives, integrals and matrices

When the scalar parser refuses a relation, `latex_calculus` reads it as SymPy with its own recursive-descent parser (nothing is evaluated by name): `\frac{d^n f}{dx^n}`, `\frac{\partial f}{\partial x}`, `\frac{d}{dx}(...)`, `f'(x)`, `\int_a^b f\,dx`, `bmatrix` and `pmatrix` literals with sums, products, transposes and inverses, `\frac12`, roots, functions, `\log_{10}`, degrees, `\Delta p` as one quantity. It refuses what it cannot read faithfully: `\nabla`, `\sum`, `\oint`, indefinite integrals, vector or tensor products, the derivative of a bare symbol that is not a function (`d(mv)/dt` with nothing saying `m` depends on `t`).

A relation that is an identity is `symbolically_verified` (evidence `sympy`). A definition stated earlier in the same paragraph (`w(x) = ...`, `\mathbf{K} = ...`, a symbolic `name = expression`) is a premise: a later relation that is an identity once the premises are substituted is `follows_from_stated_premises` and lists them. A value or a condition (`x = 0`, `r = R`) is never a premise, because it holds at one place. A relation whose two exact sides differ by a nonzero constant is `contradicted`; a decimal literal never makes a contradiction, because it may be a rounded value. A relation that is not an identity stays `not_machine_checkable` or `unsupported`: failing to prove an equation is not a proof that it is wrong.
