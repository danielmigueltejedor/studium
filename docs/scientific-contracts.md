# Explicit scientific claim contracts

A reproduced operation does not establish a physical conclusion. This extension
attaches scientific metadata to **existing** `CLM-` claims and their existing book
records. It uses the existing allowlisted expression parser, bounded SymPy
operations, Pint, citation policies, project lock and append-only storage. No new
dependency or migration is required.

## Investigation and scope

Baseline: `main` at `08ef1f4` (merged PR #72). No PR was open at investigation.
PRs #57/#58 already distinguish equation evidence and bind checks to the stored
equation; #65 supplies calculus/premise grounding; #70 supplies staged diagrams;
#71/#72 improve replay, rendering and integrated audits. Those implementations
are retained. `authoring/claims.py` records draft scientific text and citations;
`derivations.py` stores assumptions, mathematics, units and check records;
`problem_review.py` replays the explicit model. Their evidence does not establish
agreement between distant explanations of one conclusion.

The bibliography separates origin, authority and PENDING classification. No new
code writes those records. The renderer and LaTeX controls are unchanged. The
example book generator has a destructive recreation lifecycle; it was inspected,
not run. No existing academic project was regenerated or overwritten.

This is a vertical implementation of explicit claim–equation–assumption checks,
not a universal prose/physics verifier or the complete overhaul. Its contract
reconciliation is **not chapter regeneration**.

## Representation

| Scientific object | Representation |
|---|---|
| CLAIM | Existing claim id, text, chapter and citations |
| EQUATION | Named `equations` with exact left/right expressions |
| ASSUMPTIONS | Named predicates and the representations requiring them |
| DERIVATION | Existing `DER-` ids in `derivations`, bound to their current record bytes |
| RESULT | Each check's `right`, `claimed`, expected unit or required predicate outcome |
| EVIDENCE | Existing claim/representation excerpts and source ids, fingerprints and current citation blockers |
| VERIFICATION | Per-check method, inputs, result, scope and a separate verification vector |

A claim contract can link theory, derivation, example, self-check, problem,
solution and appendix occurrences anywhere in the book. `record` is an existing
claim, paragraph, problem or derivation id. A role is an author's declaration of
where the statement occurs, not a certification of its pedagogical placement.
Mapping the prose to its explicit expression requires expert review. Equations
in the table are definitions of what to check: they do not pass simply because
they were stored. A check references an equation id or supplies its own sides.

## Contract schema (version 1.0)

All fields except `variables` and `representations` default to empty collections.
Unknown fields are rejected, including caller-supplied verification results.
Expressions use Studium's existing safe Python mathematics grammar, **not
LaTeX**; declarations use at most 40 symbols. `e` is Euler's number; `E` remains
a symbol suitable for Young's modulus. Units use Pint syntax; dimensionless
quantities must explicitly use `dimensionless` or `1`.

```json
{
  "variables": {"K": "dimensionless", "CL2": "dimensionless", "CD0": "dimensionless", "ei": "dimensionless", "AR": "dimensionless", "cd2": "dimensionless"},
  "bindings": {"K": "1/(pi*ei*AR)+cd2", "CL2": "CD0/K"},
  "assumptions": [],
  "equations": [{"id": "optimum_balance", "left": "K*CL2", "right": "CD0"}],
  "derivations": [],
  "representations": [
    {"record": "PAR-THEORY", "role": "theory", "requires": [],
     "checks": [{"kind": "identity", "equation": "optimum_balance"}]},
    {"record": "PAR-SELF-CHECK", "role": "self_check", "requires": [],
     "checks": [{"kind": "identity", "left": "CL2/(pi*ei*AR)", "right": "CD0"}]}
  ]
}
```

Replace the two illustrative record ids with ids in the actual book. This
example encodes the extremum condition as a declared premise, rather than
proving existence or global optimality of the aerodynamic maximum. Positivity,
model applicability and correspondence of the definitions to the book remain
expert questions.

The first identity passes on its common domain. The second is not an identity:
its residual is `-AR*CD0*cd2*ei*pi/(AR*cd2*ei*pi + 1)`. The equality concerns the
**total quadratic drag**. Setting `cd2 = 0` makes the isolated-induced-drag
identity pass too; special cases such as zero lift are not excluded by this
algebraic counterexample. A FAILED identity means that an unrestricted identity
under the declared bindings is disproved, not that the equation is false at
every point.

`bindings` define symbols by exact expressions and may depend on other bindings.
Cycles, including syntactically self-referential `x = x/x`, are rejected.
Expansion is checked against the original parser's expression/node/depth/numeric
power budgets before evaluation. An oversized check stays unverified rather
than being presented as a scientific contradiction.

A predicate is `{ "id": "no_losses", "left": "h_loss", "relation": "eq", "right": "0" }`.
Relations: `eq`, `ne`, `gt`, `ge`, `lt`, `le`. Predicates are evaluated under the
bindings. A symbolic undecidable predicate remains UNVERIFIED. Missing required
predicates are review findings; a false required predicate is a demonstrated
failure **of the declared scenario**. Hypotheses are not silently inferred from
successful algebra or units, and their truth in nature is not established.

## Check kinds

| Kind | Fields besides `kind` | Scope |
|---|---|---|
| `identity` | `left`, `right`, or just `equation` | Algebraic identity under the bindings on a common domain; a disproved rational identity is FAILED, undecidable expressions are UNVERIFIED |
| `dimensions` | `expression`, `expected_unit` | Pint check using declared units, before numerical substitution |
| `defined` | `expression` | Finite real value at the declared point; original divisors and negative powers are inspected before cancellation |
| `limit` | `expression`, `variable`, `point`, `claimed` | Finite-point **two-sided** symbolic limit; the limiting variable stays free even inside definitions |
| `gradient` | Three `coordinates`, three `components` | Mixed-partial compatibility of a supplied pressure-gradient field; success is local and conditional, not proof of global pressure existence |
| `model` | `model` | Required predicate checks for a supported model profile |

Each representation's `requires` applies to all its checks. Gradient coordinates
cannot be bound to points before differentiation. Components expand their
parameter definitions before differentiation; boundaries, topology, regularity,
body-force assumptions and the derivation of that gradient require review.

Model profiles are deliberately conservative, sufficient conditions for their
simple form; they are not exhaustive statements of all valid variants:

- `bernoulli_simple`: `steady`, `incompressible`, `inviscid`, `same_streamline`,
  `no_losses`, `no_shaft_work`.
- `steady_stokes`: `small_reynolds`, `negligible_unsteady_inertia`.

The author supplies predicates for these names. For example the Stokes
hypotheses should check separate convective and temporal inertia scales. A small
Reynolds predicate alone leaves the temporal hypothesis missing. The profile
does not choose universal Reynolds/Mach/acceleration thresholds, derive a force
balance or validate a supplied predicate's physical meaning.

## Verification states and reporting

Results remain separate for `arithmetic`, `symbolic`, `dimensions`, `domain`,
`assumptions`, `model`, `numerical_convergence`, `documentary`, `expert_review`.
This vector concerns the contract's own checks; legacy computations and
derivation checks retain their existing records and reports. No composite
VERIFIED state or academic approval is assigned.

- Symbolic and dimensional successes retain existing `SYMBOLICALLY_VERIFIED`
  and `DIMENSIONALLY_VERIFIED` vocabulary.
- `DOMAIN_POINT_CHECKED` describes a finite point, not a neighborhood or limit.
- `ASSUMPTIONS_CHECKED` describes the supplied predicates under the supplied
  bindings, not an observation that the real experiment meets them.
- `MODEL_CONSISTENT_UNDER_ASSUMPTIONS` concerns only the stated profile predicates
  or local pressure-gradient compatibility.
- `EVIDENCE_LOCATED` means stored excerpts exist and pass citation policy;
  `semantic_support` stays `not_established`. Source diversity is not corroboration.
- `NOT_CHECKED`, `UNVERIFIED`, `FAILED` and `MIXED_CHECKS` preserve absence,
  uncertainty, demonstrated failure and mixed scopes. Expert review stays PENDING.
- No external notebook executor or convergence checker is added. Arithmetic and
  convergence are `NOT_CHECKED` here; Mathematica code is never executed or
  labelled verified by these tools.

`studium quality-audit` includes these results in JSON and Markdown, with stable
finding ids, the affected record/chapter and the common claim id. Every contract
also produces a review finding explaining its limits. Stale contracts contribute
no passing or failed scientific checks until explicitly reconciled; invalid
stored schemas are warnings. Coverage counts existing claims, annotated claims
and current contracts. An empty report does not clear unannotated prose.

## CLI and MCP

```bash
studium scientific-contract record --project BOOK --claim CLM-000001 --file contract.json --origin generator --json
studium scientific-contract report --project BOOK --json
studium quality-audit --project BOOK > quality.json
studium quality-audit --project BOOK --format markdown > quality.md
```

MCP: `studium_scientific_contract_record` (WRITE) accepts `claim_id`, `contract`,
optional `expected_revision`, and `origin`. `studium_scientific_contract_report`
(READ) recomputes the assessments. The existing integrated audit remains READ
and advisory. Successful report production does not mean zero findings.

## Safe reconciliation and compatibility

Contracts are stored in `claims/scientific-contracts.jsonl`, keyed by the existing
claim id. This sidecar keeps academic text, source evidence and existing
validated results in their original records. Each revision retains its inputs,
dependency fingerprints, origin, prior revision and revision hash. A single
append under the existing project lock is the commit boundary; existing records
and histories are not rewritten.

For an update, pass the current `revision_sha256` as `expected_revision`.
An obsolete writer receives `scientific.revision_conflict` with the current
revision. Identical retries return `already_recorded` without changing bytes,
including when the writer did not receive the first response. A generator can
update its own revision with the expected revision. After a human correction,
a different generated proposal returns `scientific.editorial_conflict` even with
the latest revision. No timestamps, source states, metadata, validated result
records or ids are reset by retrying or rejecting a proposal.

`origin` records caller intent, not authentication. Automated generators must
use `generator`. Explicit editorial corrections use `human`. The API/MCP default
is `generator`; the manual CLI default is `human`. Read the current report or
record response before submitting an editorial update.

Dependencies bind full claim/paragraph/problem/derivation/excerpt/public-source
records conservatively, including check and provenance changes. Local-source
liveness is checked by the existing citation policy. Any changed linked record
invalidates the contract; an identical-contract reconciliation explicitly binds
the new revision. An audit recomputes results without modifying records or
promoting PENDING evidence. Broader book audit reads retain the existing
read-only snapshot/concurrent-writer limitations.

This mechanism protects the **contract** from regeneration. It deliberately
does not patch arbitrary chapter text, merge edited solution trees, preserve
edits through the old example driver's deletion, or make that driver safe.
A full generator/editorial reconciliation API needs per-field ownership and a
transaction boundary spanning all chapter records. Do not use the example
driver to rebuild an existing edited project.

## Regression coverage and remaining acceptance work

A second before/after comparison used the same explicitly annotated two-chapter
fixture with the integrated audit function from baseline `main` and the new
audit. Baseline reported zero scientific identity failures; the new audit
reported six, locating the incorrect induced-drag equality in derivation,
example, self-check, problem, solution and appendix representations. This checks
explicit annotations, not automatic understanding of arbitrary prose.

The synthetic regression suite first failed with the missing contract feature
(14 failures); it is not represented as 14 existing engine arithmetic bugs.
It tests total/isolated drag across seven book roles, the `cd2=0` restricted
case, zero-velocity power division, cancelled singularities, viscosity ratios,
inclined depths, local pressure integrability, Bernoulli/Stokes hypothesis
omissions, indeterminate point versus limit, wrong dimensions, E/e preservation,
unsafe input, expansion budgets, fingerprints, read-only JSON/Markdown reports,
concurrent/stale writers and two idempotent rebuild proposals after human edits.

Remaining work, in priority order:

1. Full chapter reconstruction with stable semantic keys and per-field editorial
   ownership; acceptance must add a real academic source, edit text/model steps,
   rebuild twice and preserve all evidence/history with explicit conflicts.
2. More physical models and derivation of pressure gradients from momentum
   equations; current `gradient` checks a supplied gradient, not an arbitrary
   velocity field. Add topology and domain-aware reasoning where defensible.
3. Independent source–claim semantic support, source lineage and reviewed
   prose-to-contract mappings. Unannotated text has no automatic protection.
4. Ambiguous academic problem data/reference frames and semantic unit matching
   beyond the existing structured solution gaps and dimensional checker.
5. Executed notebook provenance and separate spatial/temporal convergence
   studies versus independent analytic comparisons. Never count stored code as
   an execution. No fake `NUMERICALLY_CONVERGED` state is emitted meanwhile.
6. Broader diagram/caption leakage and measured equation/PDF layout checks; #72's
   existing compiler diagnostics and generator-stage tests remain authoritative.

The existing evidence/publication gates are unchanged. A contract audit is an
advisory report, and passing any subset of its checks cannot release a book.
