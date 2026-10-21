# Scientific verification coverage

Audit started: 2026-10-21; verification continued on 2026-10-22. Base: `main`
at `b30934f`. Automated checks concern
explicit inputs, never the scientific authority of the model, source or author.

## Reproduced domain and limit defects

| Finding | Severity / priority | Cause and impact | Correction and regression |
|---|---|---|---|
| MAT-001 | HIGH / P1 | `verification/engine.py` simplified `x/x` to `1`, or subtracted identical sides before substituting `x=0`. Equations and numeric checks could pass at an undefined point. | FIXED_AND_VERIFIED: inspect original syntax for zero divisors, negative powers and nonfinite subexpressions under simultaneous substitution. Tests: `tests/test_verification_domains.py`. |
| MAT-002 | HIGH / P1 | `_limit_point` implicitly used the right-hand direction for a finite point without a suffix. `abs(x)/x`, point `0`, claimed `1` passed although the two-sided limit does not exist. | FIXED_AND_VERIFIED: unsuffixed finite points use both directions; `0+` and `0-` remain explicit. An undecidable/nonexistent two-sided limit returns UNVERIFIED. Direction is included in successful outputs. |
| MAT-003 | HIGH / P1 | `authoring/grounding.py` promoted the entire final derivation equation using its aggregate check status. Checking `x+x = 2*x` could mark unrelated stored `p = F*A` as symbolically verified; an unrelated failing check could mark it failed. | FIXED_AND_VERIFIED in equation evidence/declarations: bind each reported relation to individual stored check inputs. Unmatched checks cannot certify or disprove it; unrelated symbolic success cannot upgrade a matched numeric replay. Tests: `tests/test_verification_scope.py`. |
| MAT-004 | HIGH / P1 | A `studium_math_verify` equation checked at `p=6,F=2,A=3` promoted unrestricted prose `p=F*A` to symbolically verified. Conditional equivalences similarly lost their assumptions. | FIXED_AND_VERIFIED in equation evidence: solution/assumption checks yield `follows_from_stated_premises`, explicit `verification_scope`, and required human review. The raw mathematical check still describes its actual successful substitution. |

These corrections retain finite complex algebraic solutions and symbolic
families conditional on the common domain. They do not impose real-only
physics rules on algebra. Removable singularities still permit limits; the
point guard is not applied to the limit's approach expression.

The regression suite first reproduced the existing false successes. The new
point guards use the existing allowlisted parser and its 1000-character,
200-node, 24-level budgets. They inspect original arithmetic/function
subexpressions, so cancellation cannot erase a demonstrated singularity.
Unknown symbolic domains remain conditional and are explicitly described in
successful equation limitations. This is not an exhaustive branch/domain proof.
Cross-bound or cyclic solution mappings (for example `x=y, y=0`) require an
independent parameterization and remain UNVERIFIED. Simultaneous substitution
must not leave a mapped symbol behind and certify an undefined point as a family.

## Check binding and compatibility

Derivation records retain the aggregate outcome of their requested mathematical
checks, along with each check's explicit input and method. The aggregate is not
a proof of every final equation or intermediate line. The verification metadata
now says this directly. Equation evidence uses individual matching checks:

- A checked left/right relation may support that relation, including existing
  notation normalization through the stored declared relation.
- A symbolic solution or supplied assumption remains a recorded premise.
  Prose is labelled conditional and requires human review, even when the
  algebraic substitution succeeds.
- A replay of a matching computed side with an output variable, or of a zero
  residual, is scoped numerical evidence. Merely evaluating an output variable
  does not reproduce the equation defining it.
- A check of one scalar expression in a final equation containing several
  relations retains `derived_steps_unchecked`; it does not silently identify
  the expression's output among those relations.
- Legacy records lacking check inputs are retained without inventing a binding.
  Rerun the check to make the correspondence explicit. Declarations of an
  unbound final relation return `paragraph.math_ungrounded` with the relation
  and derivation id; the stored mathematics is not deleted or rewritten.

The existing Torricelli regression now expects a conditional result from its
declared solution `V=sqrt(2*g*h)`, with that premise and required review exposed.
It no longer expects a universal identity among independent `V`, `g` and `h`.
Genuine matched arithmetic, explicit symbolic identities and failed checks of
the same relation retain their distinct statuses. No academic approval is added.

Focused validation on the final binding and substitution changes: 148 tests passed covering
scope, grounding, structural grounding, Young's modulus, persisted mathematical
verification, domain guards, scientific contracts and academic-depth integration,
including LaTeX compilation with the task's local TEXMF dependencies. Full regression results belong in the
comprehensive audit report; these focused counts are not a full-suite claim.

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
This limitation was reproduced safely with an event-waiting callable: the
caller received `VerificationTimeout`, while the worker remained active until
explicitly released. Status: NOT_IMPLEMENTED, HIGH/P1 resource-control work.

General series convergence, ODE/PDE solvers, exhaustive singularity/domain
analysis, numerical convergence studies, true source-lineage independence and
reviewed semantic support are NOT_IMPLEMENTED as general verifiers. Existing
engineering calculators are scoped computations, not universal model checks.

Stored historical check outputs are not silently rewritten by these fixes.
Checks used in a new scientific review must be rerun under the current engine;
full engine-version migration/invalidation remains unfinished.
The existing `authoring/math_verify.py::_fingerprint` also omits mathematical
inputs: two different accepted equivalence inputs with the same check, method
and status produce the same `input_sha256`. This is reproduced independently
of any book data; it weakens audit provenance. Status: NOT_IMPLEMENTED,
MEDIUM/P1. No cryptographic collision or data mutation is needed to reproduce it.
