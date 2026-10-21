# Scientific verification coverage

Audit date: 2026-10-21. Base: `main` at `b30934f`. Automated checks concern
explicit inputs, never the scientific authority of the model, source or author.

## Reproduced domain and limit defects

| Finding | Severity / priority | Cause and impact | Correction and regression |
|---|---|---|---|
| MAT-001 | HIGH / P1 | `verification/engine.py` simplified `x/x` to `1`, or subtracted identical sides before substituting `x=0`. Equations and numeric checks could pass at an undefined point. | Inspect original syntax for zero divisors, negative powers and nonfinite subexpressions under simultaneous substitution. Tests: `tests/test_verification_domains.py`. |
| MAT-002 | HIGH / P1 | `_limit_point` implicitly used the right-hand direction for a finite point without a suffix. `abs(x)/x`, point `0`, claimed `1` passed although the two-sided limit does not exist. | Unsuffixed finite points use both directions; `0+` and `0-` remain explicit. An undecidable/nonexistent two-sided limit returns UNVERIFIED. Direction is included in successful outputs. |

These corrections retain finite complex algebraic solutions and symbolic
families conditional on the common domain. They do not impose real-only
physics rules on algebra. Removable singularities still permit limits; the
point guard is not applied to the limit's integration/approach expression.

The regression suite first reproduced the existing false successes. The new
point guards use the existing allowlisted parser and its 1000-character,
200-node, 24-level budgets. They inspect original arithmetic/function
subexpressions, so cancellation cannot erase a demonstrated singularity.
Unknown symbolic domains remain conditional and are explicitly described in
successful equation limitations. This is not an exhaustive branch/domain proof.

## Actual supported properties

| Capability | Scope established | Remaining limitations |
|---|---|---|
| Symbolic algebra | Simplified scalar identities under supplied symbol assumptions | Common-domain identity, not equality of domains or physical applicability |
| Equations | Proposed substitutions satisfy declared sides on their common domain; original point singularities guarded | Does not establish all roots, uniqueness or applicability |
| Differentiation | SymPy derivative agrees with supplied candidate | Global domains and all branch conditions not established; derivative assumption argument is not currently applied |
| Integration | Candidate antiderivative differentiates back; supported definite integrals agree | No general convergence/regularity certification |
| Limits | Supported finite two-sided/explicit one-sided and infinite-point symbolic limits | Infinity in a claimed result is outside the expression grammar; undecidable cases remain UNVERIFIED |
| Numerical substitution | Exact rational substitutions followed by numerical comparison | Reproduction, not independent proof; binary floating inputs may already have lost author precision |
| Numeric cross-check | SymPy and mpmath agree at supplied samples, with point singularities guarded | Finite samples do not prove an identity |
| Dimensions/conversions | Pint dimensional compatibility and supported unit conversions | Matching dimensions does not validate an equation or meaning of variables |
| Matrices/calculus in LaTeX | Restricted literals, operations and explicit paragraph premises | Unsupported vector/tensor notation remains for human review |
| Scientific contracts | Explicit identity, unit, domain-point, two-sided-limit, local gradient compatibility, declared predicate checks | Prose-to-contract mapping, physical applicability and expert review remain pending |
| Physical profiles | Declared sufficient predicates for `bernoulli_simple` and `steady_stokes` | No general mechanics, structures, flight, turbomachinery or thermodynamic certification |
| Source support | Stored excerpts, bibliographic provenance, live source checks and distinct source counts | Semantic support and true independent corroboration are not established automatically |

## Bounds and unfinished work

The symbolic timeout currently uses a worker **thread**, whose computation
cannot be killed by cancelling its future once running. Parsing also constructs
SymPy expressions before that timeout. Grammar budgets reduce exposure but are
not a hard CPU/memory isolation guarantee. A process-based bounded worker is
still required; no claim of complete resource isolation is made here.

General series convergence, ODE/PDE solvers, exhaustive singularity/domain
analysis, numerical convergence studies, true source-lineage independence and
reviewed semantic support are NOT_IMPLEMENTED as general verifiers. Existing
engineering calculators are scoped computations, not universal model checks.

Stored historical check outputs are not silently rewritten by these fixes.
Checks used in a new scientific review must be rerun under the current engine;
full engine-version migration/invalidation remains unfinished.
