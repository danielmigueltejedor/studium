# Scientific quality and publishing: contracts and remaining work

Studium drafts evidence-grounded books with an AI client. The model is not a
source of truth. Compilation, arithmetic replay, source diversity, scientific
review and publication are different operations.

## Investigation baseline

This change starts at `963428f` on `main`, rather than the evaluation revision
`6877e35`. There were no open PRs at investigation time. The only open issue was
[#39](https://github.com/danielmigueltejedor/studium/issues/39), the planned app;
this PR does not implement that app or close its issue.

The current repository already has SymPy/Pint, structured solutions, dimensional
and numeric problem review, paragraph equation evidence, append-only records,
content-bound audits and staged engineering diagrams. These remain the core
contracts. No dependency or persisted-record migration is introduced.

The example driver `examples/build-fluid-mechanics-ule.py` explicitly deletes its
previous output by default and documents that `--keep` is not idempotent. It was
inspected, not executed. Its lifecycle cannot safely stand in for editorial
reconciliation; the replacement contract is a separately scoped next release.

The evaluation book was not provided or modified. Synthetic regressions reproduce
the identifier failure; the precise original cause at line 17361 of the amended
41,372-line evaluation document cannot be established without that document.
The `$$…$$` display-wrapper regression is a separate reproducible missing-math-
delimiter case, not a claim about that unavailable line. New structured solutions
already reject raw dollar delimiters at ingestion; the renderer also needs to
handle legacy/direct display inputs safely.

## Problem → cause → change → regression

| Problem | Current cause/status | Change | Test |
|---|---|---|---|
| Internal key produces Double subscript | `_tokenize` seeds math at every unbraced script | Block namespaced editorial keys and multi-underscore identifiers before math inference; preserve literal text | `test_internal_identifiers_are_literal`, real compiler fixture |
| Normalization changes code | Spelled-delta replacement precedes opaque-span recognition | Normalize prose outside code and explicit math | `test_code_is_opaque_to_math_normalization` |
| Legacy dollar display produces Missing $ | Display wrapper strips only one dollar on each side | Unwrap double dollars before emitting one display environment | `test_double_dollar_result_has_one_display_wrapper` |
| Numeric steps invisible | `_steps_lines` prints only equation/symbolic fields | Typeset the validated replay AST without discarding operands, order or precision | Numeric-step and multidisciplinary regressions |
| Solved figures appear in statements | Any global stage accepted; some generators advertise unsafe statement placement | Reject result-bearing generators in statements; relocate legacy drawings in the draft view, preserving records | Diagram placement regressions |
| Fatal message lacks record context | Only final 400 process-output characters returned | Preserve full process/log output; map paragraph, solution and figure ranges to records | Real double-script/undefined-command failures and source-map tests |
| First-pass references misinterpreted | No structured final-pass report | Run pdflatex at least twice, up to four on rerun requests; report only final-pass warnings | First-pass/reference regression |
| Long equality chains overflow | One display line | Align only complete top-level equality chains; leave a single long RHS intact | `test_long_chain_wraps_only_at_complete_top_level_equalities` |
| Arithmetic mistaken for science | Existing independent checks scattered across reports | Integrate checks with explicit ERROR / WARNING / REVIEW_REQUIRED / INFO findings | Replayed arithmetic with incorrect output dimensions; inapplicable-model review |
| Distinct documents mistaken for corroboration | Legacy `two_witnesses` means source diversity only | Explicit semantic-support review finding, never an automatic authority upgrade | Two unrelated synthetic excerpts |
| Editorial corrections lost during regeneration | No generic generation/reconciliation API with revision ownership | Existing append-only IDs retained; render/audit tested read-only; generator reconciliation deferred | Render twice after paragraph replacement, compare persisted bytes |

## Text and mathematical rendering

Unbraced identifiers with two or more underscores, such as
`w_perfil_u_abierto`, are literal outside explicit math. Namespaced keys such as
`[E2-C05:w_perfil_u_abierto]` also remain literal. They are not deleted.
Single-index notation (`p_man`) keeps its existing behavior. To express a
mathematical multi-index, write explicit, valid mathematics with braces, e.g.
`$w_{perfil,u,abierto}$`. Explicit math overrides identifier inference.

Inline code, fenced code, explicit math, ordinary prose and figure markers retain
their separate rendering paths. No global underscore deletion or equation
rewriting is used. A malformed explicit equation is retained and compilation
fails with a diagnostic; the renderer does not invent a corrected equation.

Numeric steps use the existing replay language and its AST, not unconstrained
LaTeX interpretation. Fractions, powers, roots, products and functions remain
visible. Printed operations do not imply that a claimed value agrees: the
existing step/answer checks still report mismatches separately. A numeric-only
step is not a substitute for the missing physical/symbolic model; the integrated
audit lists that incompleteness.

Long equality chains are wrapped at top-level equality signs only, when the
fragment exceeds 120 characters. This is a conservative presentation heuristic,
not a width measurement. Existing environments and paired `\\left/\\right`
delimiters are left alone. Single long expressions need author-supplied
`aligned`, `split` or `multline` structure; compiler overflow warnings remain
visible. Mathematical meaning takes precedence over automatic line breaking.

## Compiler diagnostics

Rendering still returns existing draft statuses. Additional response fields:

- `editorial_report`: `latex/draft.quality.json` (also `.md`).
- `editorial_counts`: ERROR, WARNING and INFO counts.
- `compiler_log`: full process output, when the engine ran.

The report includes the TeX SHA-256, compiler, compilation outcome, source-map
ranges and structured findings (file, line, record, chapter, type, evidence,
method, verification scope and suggested action). The `.tex` contains invisible
encoded record comments (the decoded map is in the JSON report). Context is exact for mapped paragraph/solution/figure ranges;
preamble and some back matter can have a null record. A box warning may name a
range rather than the exact offending token. Logs are diagnostic data, not
instructions to execute.

`draft.log`, `draft.compiler.log`, intermediate compiler files and the preceding
`draft.previous.log` are retained. pdflatex performs two to four passes, while
Tectonic handles its internal reruns and keeps logs/intermediates. Only the last
pass determines remaining undefined-reference warnings. Compilation can succeed
with warnings; a warning never becomes a demonstrated scientific error.
A missing compiler leaves `compiled: false` and no PDF. A fatal compiler error
retains the TeX/logs and removes an unusable partial PDF, as before.

## Statement and solution diagrams

The generator registry is the generic safety contract. A generator may be used
at `statement` only if it advertises that stage. This is not a beam-specific
rule. Section properties (centroid/principal axes), thin-wall geometry
(shear centre) and stress elements (principal stresses/direction) expose derived
results and no longer advertise statement safety. Their default placement moves
to model/solution; `beam.statement` remains statement-safe.

Legacy result-bearing figures stored as statements are reported as
`statement_diagram_leak`. The renderer uses an in-memory copy to place those
figures at `solution`, including practice solutions in the appendix. Original
IDs, captions, drawing source, geometry, signs, checks and JSONL bytes remain
unchanged. The report identifies the persisted placement needing correction.

This contract does not analyze arbitrary prose captions or certify custom
extensions. A third-party generator advertising statement safety must ensure its
drawing contains only supplied data. Generic semantic leakage detection and
new statement-only variants of the result-bearing generators remain future work.

## Integrated book audit

```bash
studium quality-audit --project /path/to/book > quality.json
studium quality-audit --project /path/to/book --format markdown > quality.md
```

MCP: `studium_book_quality_audit`, class READ, accepts the standard `project`.
It returns stable finding identifiers, severity, chapter, record, problem type,
evidence, detection method, recommended correction and verification scope.
The command returns success when the advisory report was produced, even if
findings include errors; inspect `counts`. It is not a publication gate.

Existing checks are reused for missing excerpts, citation policy blockers,
current paragraph audits, equation evidence, problem fingerprints, model/unit
consistency, numeric model reproduction, answer mismatch, diagram status,
statement placement, unresolved figures and open contradictions. The compiler
report is included only if its fingerprint matches the current TeX; it is not
proof that subsequently edited book records were rendered.

A solution completeness check measures fields, not length: knowns, unknown,
model, assumptions, development, symbolic steps, explanations, result, units
and interpretation. `dimensionless` explicitly supplies a unit. Missing fields
are warnings. Contradictory arbitrary interpretations need review, rather than
an unreliable keyword heuristic. All numeric problems receive a scientific
review finding; passing arithmetic/dimensions does not validate applicability,
physical assumptions or conclusions. Likewise, two source IDs do not establish
semantic support, authority or independent corroboration. Existing source and
excerpt PENDING states are preserved.

## Compatibility and limits

- Existing CLI/MCP operations and record schemas are retained; the audit is
  additive. No real project is migrated, overwritten or regenerated.
- Draft layout changes for numeric steps and legacy unsafe diagram placement.
  Literal identifier inference changes only outside explicit math.
- Additional compiler passes may increase render time. The full integrated
  audit can be expensive on large books; pagination/caching is future work.
- Compiler diagnostics cover common TeX errors and warnings, not every TeX
  dialect. Tectonic flags are implemented but must be exercised where installed.
- No automatic human-review, publication or scientific-certification state.

## Next releases, in priority order

1. Revision-aware generation/reconciliation: define generated versus editorial
   ownership, stable semantic keys, expected-input fingerprints and atomic
   conflict reporting. Then implement an opt-in overlay/rebuild API using the
   existing append-only records. Acceptance must cover adding a real academic
   source, editing paragraph/model steps, rebuilding twice without duplicates,
   preserving corrections and reporting generator/editor conflicts. The render
   immutability test here is **not** that reconstruction implementation.
2. Versioned scientific contracts: model domain, required assumptions, knowns /
   unknowns, physical constraints and sign conventions, with deterministic
   checks only for explicitly supported constraints. Preserve expert review for
   uncheckable applicability; no universal physics verifier.
3. Extend claim–excerpt relations beyond existing equation grounding to arbitrary
   paragraph claims; record relevance, contradictions and shared-source lineage
   separately from quote matching and authority. Never auto-upgrade PENDING.
4. Provide statement-only geometry/stress variants and explicit known/derived
   labels for extensible diagrams; visual regression fixtures for clipping and
   overlap, with captions requiring review.
5. Editorial profiles and measured equation/table widths, optional PDF page
   inspection for clipping and unexpected blank pages, font coverage and
   broader diagnostic source mapping. Do not suppress warnings to obtain green CI.
6. Difficulty/objective-sensitive pedagogical contracts, guided/proposed exercise
   modes and independent physical-model checks where a second method exists.
