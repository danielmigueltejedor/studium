# Publishing validation and artifact preservation

Audit started 21 October 2026 from `main` commit `b30934f`. This document records implemented behaviour and the limits of the evaluated cases. Compilation, structural completeness, source support and academic review remain separate states.

## Reproduced defects and corrections

| Finding | Severity / priority | Root cause and observed impact | Change | Status and regression risk |
|---|---|---|---|---|
| A missing compiler destroys the last PDF | HIGH / P0 | `render_draft` unlinked `latex/draft.pdf` before compiler discovery. A missing engine removed the previous edition. | Generate in a unique temporary sibling directory; retain the old source/PDF on missing engine or compilation failure. Failed attempts use `draft.failed.*` when a previous PDF exists. The result has `pdf: null` and an explicit `previous_pdf`; the old artifact is not reported as a successful new build. | **FIXED_AND_VERIFIED** for missing engine, compiler failure and compiler I/O exception. Consumers should use returned artifact paths rather than assume the attempt always writes `draft.tex`. |
| Concurrent renders compile another request's source | HIGH / P0 | Project locking ended before compilation; a second request could overwrite the shared TeX/PDF/log paths. The first test compiler observed the second request's source. | Keep the project lock through document generation, staged compilation and publication. A competing request returns `storage.locked`. | **FIXED_AND_VERIFIED** for cooperating concurrent render calls. Rendering now holds the project writer lock longer; callers must handle the existing busy response. |
| A missing figure still satisfies completeness | MEDIUM / P1 | Completeness counted `status == checked`; reference/usage views also trusted stored flags. The renderer correctly omitted a nonexistent output, leaving the views inconsistent. | Shared contained, nonempty artifact availability check for completeness, rendering, reference resolution and usage. A failed correctness flag, missing/empty output, unsafe path or final-file symlink does not count. | **FIXED_AND_VERIFIED** for these artifact-availability cases. Legacy output bytes without a stored hash are not authenticated. |

Tests cover previous source/PDF preservation, discarded partial compiler output, competing render calls, successful replacement with a recovery copy, compiler I/O exceptions, missing figure output, incorrect production flags, unsafe paths and figure references/usage. Existing tests continue to cover real compilation, final-pass diagnostics, source mapping, exercise output and native figure placement.

## Artifact publication and recovery contract

Compilation happens in a unique directory directly under the project root. This preserves existing `../figures` and `../editorial-config.tex` references. Compiler intermediates do not touch the current edition. Authoring JSONL records are not rewritten by rendering.

When replacing a previous PDF after a successful compilation, the renderer first copies the existing `latex/draft.*` files to `.studium/render-backups/<unique-id>/`. A successful result returns `previous_artifacts`. Compiler outputs are flushed and replaced individually; the PDF is published last. Failed attempts retain separate TeX, compiler diagnostics and editorial reports while leaving the old source and PDF in place.

This is **not an atomic multi-file transaction**. A hard process termination or storage failure during final publication can leave mixed artifact generations; the previous files remain in the recovery directory. There is no automatic recovery command, power-loss durability guarantee or backup retention policy in this change. Inspect the matching backup and restore its complete artifact set before using an interrupted edition. Full transactional publication/recovery is **PARTIALLY_FIXED**, not certified by the tests above. Raw TeX and external compilers also remain a trust boundary; staging and `-no-shell-escape` are not a security sandbox.

## Existing editorial pipeline

`publishing.py` maps generated source lines to record and chapter IDs. It reports compiler errors, undefined references/citations, font/package warnings, and overfull/underfull boxes from the final compiler pass. Reports contain a document hash and observed diagnostic methods. Earlier-pass reference warnings are not confused with final unresolved references.

The pipeline does not automatically detect all clipping, label collisions, misleading figures, empty pages or poor pedagogy. There are compilation/text regressions and figure-fit tests; a persistent raster-baseline suite and exhaustive visual analysis remain **NOT_IMPLEMENTED**. Manual review must identify the actual inspected pages and unresolved findings.

## Local validation environment

The local TeX Live 2026 basic installation initially lacked `accsupp.sty`, causing full-book compilation failures. This was reproduced in the compiler logs and corrected only in a task-local TEXMF tree using TeX Live's verified package repository. No system TeX package installation was changed. A matching environment can use:

```bash
tlmgr --usermode --usertree /path/to/task-texmf init-usertree
tlmgr --usermode --usertree /path/to/task-texmf install accsupp
TEXMFHOME=/path/to/task-texmf PYTHONPATH=src python -m pytest -q \
  tests/test_render_integrity.py tests/test_figure_artifact_integrity.py \
  tests/test_draft_book.py tests/test_draft_path.py \
  tests/test_publishing_quality.py tests/test_academic_depth.py tests/test_figures.py
```

The targeted regression set passed 97 tests, including 14 artifact-integrity cases. Pyright reported zero errors with the task Python environment selected. Ruff passes for the modified source/test files. These results are scoped to this change, not the overall mission.

## Copied real-book evaluation

The local `librosaeroespacial` repository was located under the user-authorized Developer directory. Originals were not edited. Its fluid mechanics, structures, flight mechanics and turbomachinery books are LaTeX imports without a native `project.toml` at the inspected book roots. They were inventoried, not represented as directly audited native Studium projects. Materials and engine maintenance also has a native project under its `project/` directory, but it was not evaluated in this slice.

Two programming projects, `vol00-enciclopedia-maestra-integral` and `vol05-monografias-python-js-ts`, were copied to the task's work directory. The former was inventoried (24 current paragraphs); the latter was evaluated (48 current paragraphs, eight blueprint sections). No authored Python, Rust or other exercise program was executed. Generated TeX was inspected for file-access/execution primitives before compilation; this is a bounded review, not a security proof.

### Python/JavaScript/TypeScript volume

The explicit review rendering mode (`include_unsupported=True`) compiled the copy to **45 pages**, the same count as the prior copied PDF. It retained draft/review warnings and did not promote evidence or release state. Diagnostics: **0 errors, 50 warnings and 13 informational findings**. Of the warnings, 48 were general LaTeX warnings and two overfull boxes; the maximum reported overflow was **19.37466 pt**. These remaining diagnostics prevent a claim of defect-free layout.

Visual sampling used Poppler PNG renders of pages **1, 14 and 45** of the rebuilt copy, plus page **14** of the prior copy. The sampled title, exercise box and bibliography were readable, without visible clipping in those sampled regions. This artifact-preservation change does not claim a new visual correction. No whole-book visual approval was performed. The sample still exposes editorial issues: a programming exercise uses the generic “Modelo físico” label and gives calculated timings in the statement; those content/domain issues remain pending.

Page 45 also exposed two recorded references, `https://doc.rust-lang.org/reference/src-python-ref.html` and `https://doc.rust-lang.org/reference/src-unicode-15.html`. Both returned **HTTP 404** during this audit. Their stored text was only a generic sentence naming the purported specification; their bibliographic/scientific authority was not established. This is evidence of a legacy content problem, not a claim that the renderer invented references. Originals were left intact and no replacement source was fabricated.

Read-only copied-project observations:

- Section completeness reported **8/8 structurally complete**.
- The scientific-contract report contained **zero claims, zero annotated claims and zero current contracts**, with `scientific_validity: not_established`.
- `book_next` remained in `COURSE_DISCOVERY`, requesting `studium_course_document_record`; the existence of the compiled PDF did not finish the workflow.
- Hashes of project settings, paragraph/problem records, public sources and excerpts matched the original copy inputs after evaluation. The prior-PDF recovery copy exactly matched the original PDF bytes.

Thus a complete structural checklist is not evidence coverage or academic readiness. Source repair, semantic review, exercise review, domain wording and remaining layout diagnostics are **NOT_IMPLEMENTED** in this slice. Screenshots, raw reports and preservation hashes are retained in the task's evaluation directory and are not committed as book/source fixtures.

### Repository fluid-mechanics example

A separate copy of `examples/fluid-mechanics-ule` compiled through the current renderer to **40 pages**, with **0 compiler errors, 5 warnings and 3 informational findings**. No figure/program source was executed. Page **10** was rendered with Poppler and visually inspected: derivation, worked-problem and practice boxes fit the sampled page. This is not a whole-book approval. The legacy example still prints one result as `1,002e − 06`, and exercise `PRB-0008` describes dynamic viscosity in “pascales por segundo”; the dimensional relation stress divided by velocity gradient requires Pa·s. These notation/content findings remain pending and are not fixed by artifact preservation.
