# Programming practice and literal fidelity

`studium_problem_record` accepts `programming` as an alternative to the existing
numeric and Rust modes. It creates an unchecked practice record and never runs
client code during authoring:

```json
{
  "section": "collections",
  "prompt": "Return the first matching index, or None if absent.",
  "programming": {
    "kind": "implementation",
    "language": "python",
    "solution": "Explain the loop and include the reference implementation.",
    "tests": ["empty input -> None", "first position -> 0"]
  }
}
```

Implementation, debugging and project contracts need test cases. Conceptual and
architecture contracts need a rubric. Language and reference solution are
required. Numeric/Rust fields cannot be mixed with this mode. The contract,
solution and test/rubric metadata participate in the input fingerprint; changing
them invalidates stored evidence. `studium_problem_check` returns `unchecked`
for these records; a declared test case is not an observed passing test.

Use `studium.verification.programs.verify_program` with the appropriate mode and
explicit trust opt-in for reviewed source, or execute within external isolation.
Record exact source hashes, compiler/interpreter versions, commands, outputs and
oracles. Finite test cases do not establish correctness for all inputs or
academic approval. Legacy Rust checks now return `execution.isolation_required` through CLI/MCP.
Trusted author-owned single-file Rust fixtures can run only through an explicit
local Python capability bound to source and invocation. Cargo remains blocked
because a single-file hash cannot cover its build scripts and dependencies.
Neither runner is a security sandbox; see [Security](security.md).

The ordinary renderer retains the evidence policy. An explicit review copy can
show provisional reference solutions and their status. Programming practice
banks and reference listings flow across pages. Code on the first line of a
paragraph remains code; it cannot be consumed as an implicit section heading.

Literal code uses straight quotes and exact Unicode `ActualText` for supported
accented/math glyphs. TeX Live needs `upquote` and `accsupp` (both are included in
the usual latex-extra installation). Unsupported literal characters produce
`render.unsupported_literal_character`; they are never silently rewritten as
`U+...`. The previous TeX/PDF stays intact on that diagnostic. Use a valid
language escape that preserves the intended runtime value or provide font
support. PDF layout may change whitespace on copying; distribute editable
source files when exact indentation matters.
