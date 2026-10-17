# Rocket textbook workflow regressions

## Conservative parsing of thermodynamic function values

While drafting a thermodynamics chapter, the equation report labelled

```tex
h(T)-h(T_r)=\int_{T_r}^{T}c_p(\vartheta)\,d\vartheta
```

as `contradicted`, with `sympy` evidence. The earlier paragraph included
`h=e+p/\rho` and `c_p=dh/dT`. This is the regression reported in #76.

The calculus reader interpreted the slash quotient `dh/dT` as the algebraic
product `h*T`, then stored it as a definition of `c_p`. It also treated a
parenthesized Greek or subscripted argument as multiplication, and expanded
scalar definitions in apparent function calls. Numeric sampling subsequently
rejected an expression different from the one the author had written.

The reader now refuses slash differential notation that it cannot interpret
faithfully. Explicit derivative fractions such as `\frac{dh}{dT}` retain their
existing support. A single symbolic or signed numeric argument, including a
Greek or subscripted name, remains an opaque function value. A scalar
definition alone does not authorize interpreting that call as multiplication
or establish its functional dependence; the relation is left for review.
Compound groups used in ordinary implicit products retain their existing
behavior, and explicitly defined functions still allow symbolic evaluation.
An intended scalar product with one atomic factor can be written explicitly,
for example `a\cdot(x)`, to avoid the function-call ambiguity.

The regression paragraph is `not_machine_checkable`, with human review
required and no fabricated symbolic evidence. This does not prove the
thermodynamic relation or parse the scope of conditional prose. It avoids a
false contradiction while preserving actual failures for explicit integral
computations and the existing evidence gates. Source authority, academic
review and publication state are unchanged.

The tests use synthetic prose and equations. No private book materials or
third-party pages are part of the fix.

## Numeric inline math

The native renderer treated every digit-leading dollar span without letters
or LaTeX commands as a currency amount. Consequently `$1.08$` was printed
literally, and its closing delimiter could start a spurious formula at the
next dollar. The book importer worked around this by converting every inline
math delimiter to `\(` and `\)`.

Tightly paired numeric literals, including decimal points and decimal commas,
are now explicit math. Unpaired prices and adjacent amounts such as
`$5, $10` or `$5 $10` retain their literal currency rendering. This changes the
previous heuristic for `$5$`: use escaped dollars for a literal currency sign.
The rest of the math and prose detection is unchanged.

## Other observations

The importing adapter's stripped `aligned` wrappers were corrected in that
adapter; they do not require a framework change. Public document intake does
not automatically establish source authority. Pending source audits, complete
physical review and experimental validation remain scientific review work,
not failures to hide by changing publication or evidence statuses.
