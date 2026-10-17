# Aerospace drafting workflow regressions

This change follows a complete drafting exercise with chapters, structured
problems, Python figures, scientific contracts and an independent editorial
LaTeX layer. Regression fixtures are synthetic: no private teaching PDFs,
exam statements or third-party figures are committed.

| Observed issue | Disposition |
|---|---|
| Unit powers, symbolic dimensionless exponents, multi-chapter exercise ids | Already fixed by #74; this branch starts from that merged change. |
| JSON/Matplotlib imports and embedded TrueType PDF fonts fail in figure runner | Trusted dependency bootstrap, guarded font-table evaluation, explicit plotting extra, and server-interpreter selection; submitted code keeps its restrictions. |
| Paragraph accepts a supplemental/local excerpt but its claim/contract anchor is rejected | Shared draft citation eligibility, including source conflicts, live local version checks and contract revision dependencies. |
| Original integer-only exercise steps rejected for lack of numbers in a source quotation | Explicit `problem_id` binding to an exact stored solution step; source text is not fabricated to include generated values. |
| Linked exercise changes after a computation was replayed | Current evidence views invalidate the old binding for audits, grounding, rendering, captions and quality counts while retaining history. |
| Two tests assume repository-root working directory | Resolve their source inspection paths from the test file. |
| External manuscript adapter stripped alignment wrappers | Caller defect, already repaired in that adapter; no framework change required. |
| Angular model returns radians while caller expects degrees | Caller model/unit defect, corrected by a separate conversion; no gate bypass. |
| Incomplete source audits, short chapters, pending equations, no human approval | Expected review findings. They remain blocking; this change does not release a book or claim scientific correctness. |
| Book-specific visual identity | Kept in the editable editorial layer; no global template change imposed on unrelated books. |

See the evidence and verification models for the new citation and generated
exercise contracts. Python plotting setup and limits are in the research
model. A `checked` figure, arithmetic replay, or accepted draft citation is
still not academic approval.
