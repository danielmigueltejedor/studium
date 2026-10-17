# Authoring regressions found while building a turbomachinery draft

These fixes start at `47c12a7` (main after #73). The evaluated book used
`08ef1f4`; its project and pinned engine are not migrated or modified here.
The tests use synthetic inputs and include no private course documents,
student solutions, source-page images or excerpts from the evaluation book.

## Units and dimensional powers

`unit_latex` now handles reciprocal units (`1/s`), exact decimal/rational
powers (`K^0.5`, `m^(1/3)`, `K**(-0.5)`), powers of grouped units and
cancellation to the identity, including Unicode powers such as `s⁻¹`.
The notation appendix and structured solutions share this unit formatter;
the appendix no longer applies a separate slash-splitting heuristic. Decimal powers are stored as exact fractions
for typesetting. The bounded parser does not evaluate Python or unit names.
Unknown names retain the existing upright display; this formatter does not
establish that a unit is recognised by Pint.

Malformed groups, missing factors, nonnumeric exponents and zero denominators
raise `MathError` instead of silently printing a partial interpretation or
leaking `ValueError`. Numeric scale factors other than literal `1` remain
unsupported. Inputs are bounded to 200 characters and 24 nested groups.

**Compatibility correction:** multiplication and division now associate left
to right, as in Pint: `kg/m*s` means `kg m^-1 s`. Write `kg/(m*s)` when both
factors belong in the denominator. The old renderer incorrectly kept every
subsequent factor in the denominator after the first slash. Stored strings
are not rewritten; existing ambiguous strings should be inspected when
regenerating a book.

A dimensionless base may now have a dimensionless symbolic exponent. For
example `Tin*(pout/pin)**((gamma-1)/(gamma*eta_p))` has temperature dimensions
when all units are declared consistently. This does not evaluate the model,
check the numeric domain or certify a thermodynamic law. A dimensionful or
undeclared exponent still fails; a dimensional base still needs a numeric
constant exponent. Literal exponent arithmetic keeps exact rational powers,
and literal zero denominators/nonfinite exponents are refused.

## Mathematical prose and exercise identity

A short first line ending in a comma, colon or semicolon, or containing math
delimiters, a relation or a LaTeX command, stays body prose. A lead-in such as
`Aplicando el balance:` no longer becomes an escaped section title. Existing
plain short titles and generic `Explicación` handling remain supported.
Explicit academic blueprint headings keep their existing rendering path.

Exercise statements and appendix solutions show the same stable `PRB-` ID
beside their chapter-local number. The appendix groups solutions in blueprint
chapter order; replayed calculations stay with their own chapter. Unknown
chapter IDs remain visible instead of being discarded. Stale/unchecked
solutions remain omitted and contribute to the unresolved count.

Difficulty and reasoning-type enums are displayed as readable Spanish or
English labels, using the existing English fallback for other box chrome.
Unknown future values remain visible. Persisted enum values, IDs, MCP/CLI
schemas and verification fingerprints are unchanged. Legacy worked-answer
summaries remain available in the appendix.

## Verification scope

Regression tests cover valid/failing unit syntax, structured substitutions,
thermodynamic variable exponents and invalid powers, ordinary titles versus
mathematical lead-ins, localized labels, duplicate chapter-local numbers,
stale solutions, chapter grouping of calculations and real PDF compilation.
Rendering is checked not to mutate existing JSONL records. Existing source
provenance, human-review requirements and draft/release gates are preserved.

An earlier missing-symbol error in a derivative/integral request was a caller
error: those symbols must be declared. No verification requirement is removed
to accommodate that request.
