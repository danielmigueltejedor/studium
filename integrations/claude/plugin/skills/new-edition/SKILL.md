---
name: new-edition
description: Create a new improved edition of an existing Studium book from one user request while preserving the original and redoing verification.
---

When the user asks for a new, corrected, expanded or improved edition, locate the existing book with `studium_project_list` or `studium_project_status`. Call `studium_edition_create` with the user's requested improvements as `request`. Do not invent extra constraints, and never rewrite the original project in place.

After requesting a new edition, use `edition-evolution-analyst` to compare inherited content with the user's actual instructions and prioritize evidence-backed changes. For comprehensive revisions, use `curriculum-architect` to inspect chapter progression; delegate changed assessments to `assessment-architect`, mathematical or coding problems to `independent-solver`, multi-chapter consistency to `cross-chapter-consistency`, and accessible final presentation to `accessibility-localization`. Run independent checks only where the new content requires them. Report what changed versus what was inherited; do not invent a diff or claim all requested improvements are already implemented.

The result includes a **new project** and an adaptive agent workflow. Inspect `studium_agent_workflow_next`, then use the book skill's evidence-first coordination to update the inherited draft, re-check old sources, incorporate relevant new ones and improve activities appropriate to the actual discipline. Use independent critical review, source auditing and deterministic checks where applicable. An old audit or PDF cannot certify the new edition; run the current Studium gates and render only after they permit it.

Tell the user the new project/version and whether it is *created only*, *revised but unverified*, or *rendered and audited*. Do not claim that `studium_edition_create` alone rewrites the content. Offer concrete blockers if the connected client cannot execute required tasks.
