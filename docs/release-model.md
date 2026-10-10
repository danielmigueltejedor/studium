# Release model

Studium does not publish books. It produces drafts.

## Edition states

| State | Meaning |
|---|---|
| `DRAFT` | Work in progress. The `.tex` file is written; a PDF may exist if a compiler is available. |
| `AUTOMATICALLY_CHECKED` | All deterministic gates passed: paragraphs audited, computations reproduced, contradictions resolved, completeness satisfied. |
| `REVIEW_REQUIRED` | Automated checks passed but the edition has not been reviewed by a qualified human. |
| `ACADEMICALLY_REVIEWED` | A human reviewer recorded a review with scope and identity. Never assigned by the pipeline. |
| `RELEASED` | Not implemented. Reserved for a future publication gate. |

## What `audit_passed` means

`audit_passed = True` means this edition's audits still match the current paragraph and excerpt text and each audit cites a tool result the server already stored. It does not mean:

- The prose is mathematically verified.
- The content was academically reviewed.
- The book is published or endorsed.

A changed paragraph or excerpt makes that audit stale.

## Gates

The state machine defines forward gates. Each gate fails closed:

| Gate | Status |
|---|---|
| `project_toml` | Implemented. Checks course identity fields. |
| `course_json` | Implemented. Requires one recorded official document. |
| `corpus_started` | Implemented. Every blueprint section needs a supported paragraph. |
| `corpus_sufficient` | Not implemented. Fails closed. |
| `blueprint_accepted` | Not implemented. Fails closed. |
| `authoring_complete` | Not implemented. Fails closed. |
| `verification_passed` | Not implemented. Fails closed. |
| `reviews_current` | Not implemented. Fails closed. |
| `release` | Not implemented. Fails closed. |
| `release_intact` | Not implemented. Fails closed. |

An unimplemented gate returns `state.gate_not_implemented`. `studium verify` reports these as blockers. No unimplemented gate silently passes.

## Rendering vs releasing

`studium render` writes a draft PDF. It does not change the project state and does not claim the book is complete or reviewed. The draft is labeled with its status.

`studium verify` reports all blockers. It does not move the book to `RELEASED`.

## Honest labeling

A book produced by Studium is labeled as what it is:

- If no human reviewed it: draft, automatically checked.
- If a human reviewed it: the review record includes scope and reviewer.
- An institution is never claimed as endorser unless the institution actually reviewed the edition.
