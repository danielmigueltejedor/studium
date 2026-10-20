# Programming books: measured verification and literal regions

Programming and mathematical evidence have separate scopes. `ExerciseContract`
(`studium.authoring.programming`) distinguishes conceptual, implementation,
debugging, architecture and project work. Implementation, debugging and project
contracts require tests; conceptual and architecture contracts require a rubric.
These are structural requirements, not approval. Mathematical exercises continue
to use the existing symbolic, numerical and dimensional contracts unchanged.
The new contract is an additive Python API; legacy persisted problem records and
CLI/MCP schemas are unchanged. Migration of those interfaces remains pending.

`CodeArtifact` and `verify_program` in `studium.verification.programs` expose
language adapters for Python, Rust, C, C++, JavaScript, TypeScript and Bash, plus
JSON/TOML parsers. Unsupported modes remain unverified. Each result records the
full SHA-256 of source bytes, requested mode, commands, observed output, installed
tool version and limitations. Declared language versions are metadata; callers
must check the recorded installed version against their supported environment.
Rust currently uses edition 2024; C uses C17 and C++ uses C++20.

| Result | Established property |
| --- | --- |
| SYNTAX_VALIDATED | A parser/tool accepted syntax; no behavioral claim |
| COMPILED | Compilation succeeded; program not run |
| EXECUTED | Exit succeeded without a supplied output oracle; `passed=null` |
| OUTPUT_MATCHED | Exact stdout matched a caller-supplied expectation |
| TESTS_PASSED | A supported runner reported at least one passing test |
| INTENTIONAL_PARTIAL | Explicitly incomplete; `passed=null` |
| UNVERIFIED / PENDING_TOOLCHAIN / ISOLATION_REQUIRED | Required evidence absent |
| FAILED / TIMEOUT | Check failed or exceeded a limit |

Nonzero passing tests are recognized for Rust, Python unittest and Node's test
runner. C/C++ test suites require a project-specific oracle and remain unverified
by this single-file test API. The TypeScript adapter uses `tsc` for syntax/type checks and compilation; runtime/test mode requires a reviewed project adapter. Node test execution alone does not typecheck TypeScript.
SQL, HTML, YAML and arbitrary frameworks have no behavioral adapter here.

## Execution boundary

No command from a source, excerpt or manifest is executed. Commands come from
fixed adapters. By default no external tool runs: `trusted=False` returns
`ISOLATION_REQUIRED` (Python/JSON/TOML in-process parsing is the exception).
Reviewed author-owned programs can opt in with `trusted=True`. The caller must
review the exact source hash. For untrusted programs use an externally provisioned
container/VM with network, filesystem and process isolation, then call this API
inside that boundary. Do not automatically expose trusted execution through MCP.

Trusted tool runs use a disposable directory, a reduced environment (compiler configuration homes retained), closed
stdin, a new process group, a wall-clock timeout, bounded captured output and
POSIX CPU/file/core limits. The entire process group is killed after each run.
These limits are **not a security sandbox** and do not prevent filesystem/network
access. Resource enforcement on Windows is limited to time/output/process exit.

## Literal rendering and scientific checks

The shared code-region parser handles backtick/tilde fences, longer closing
fences, multi-backtick inline spans and unclosed fences. Mathematics and quantity
extraction mask those regions. The integrated quality audit reports unclosed
fences and missing language tags. Listing escape delimiters are chosen to avoid
collisions with the original code. Terminal, output and diagnostic fences have
distinct presentation. Unsupported Unicode glyphs in the legacy pdfLaTeX backend
still need a Unicode-capable backend; this change does not claim full Unicode
fidelity or syntax highlighting for every language.

## Optional editorial hook and evidence review copies

A project-owned `editorial-config.tex` is loaded after the standard preamble.
It may define `\studiumcustomtitle` to replace the draft title page. Without that
file/default macro all existing books retain their rendering. Treat this file
like other trusted LaTeX source, not downloaded source material.

`render_draft(root, include_unsupported=True)` explicitly creates a review copy
that includes stored draft paragraphs whose evidence is blocked. It also retains original TikZ figures with visible pending-evidence captions. It prints an
Spanish warning for Spanish books (English otherwise) and reports `includes_unsupported_drafts=true`; it never repairs
citations, bypasses audits or changes persisted approval. The default remains
`False`. This opt-in is useful when removing fabricated evidence without losing
the manuscript being reviewed. It is intentionally not a release option.

Explanatory solution results are kept in prose instead of sending entire sentences to math mode. Paragraph boundaries and Markdown emphasis survive rendering. Long inline code can wrap at separators without inserting hyphens, percent units are escaped, and Spanish TOC reads keep angle brackets inactive. Figures first cited in a chapter purpose/box are placed once, including when the main explanation never cites them.

Review copies also retain stored proposed answers/solutions, visibly marked as
pending, even when their evidence no longer supports normal publication.
Stored verification fields are not promoted; stale check summaries are omitted
from the proposed solution. Worked developments already printed in the chapter
are not duplicated in full in the solutions appendix. Default rendering still
filters unchecked solutions.


Reader editions may explicitly choose generated sections in `project.toml`:

```toml
[render]
frontmatter = []
appendices = ["solutions"]
```

The default frontmatter is `["preface", "reader_guide"]`; the default appendices
are `["notation", "formulas", "solutions", "diagram_report", "audit", "study"]`.
Unknown or repeated names fail explicitly. Bibliography, chapters and exercises
remain. These settings change presentation only: journals and evidence are not
deleted, review metadata and the unsupported-draft warning remain. A reader
edition can thus omit an irrelevant formula sheet and internal audit/work plans
while keeping them available to editorial tools. Unconfigured STEM books retain
their existing sections.
