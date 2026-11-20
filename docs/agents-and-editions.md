# Adaptive agents and improved book editions (MVP)

Studium can organize work for any subject without pretending that all subjects
need numerical exercises. It also lets a user request an improved edition of an
existing book **in one tool call**. The original edition and its outputs remain
unchanged.

These are *provider-neutral* features exposed through the existing CLI and MCP
server. They do **not** start Claude/ChatGPT subagents themselves or publish
academic work automatically.

## Discipline-adaptive planning

Ask the connected client:

> Use Studium to plan a chapter on the French Revolution, including primary
> source analysis and an independent historiographic review.

The client calls `studium_agent_plan` with the project and, optionally,
`objective`, `discipline`, and `level`. The response contains a dependency
graph, roles, suggested educational activities and verification criteria.

The planner distinguishes history, biology, politics, mathematics, engineering,
programming, languages, humanities, and generic subjects. The generic route does
**not** require an equation or numerical problem. New subjects work through a
topic-specific specialist and methods appropriate to the learning goals; an
explicit discipline overrides the automatic choice.

The workflow engine stores tasks per project and their submitted artifacts:

1. `studium_agent_workflow_start` saves the selected roles and dependencies.
2. `studium_agent_workflow_next` gives the ready tasks (independent tasks can run
   concurrently if the client supports it).
3. The client does real work using existing Studium MCP authoring/research tools.
4. `studium_agent_workflow_submit` records the produced artifact IDs and opens
   dependent tasks.

**Submitted is not verified.** A text an agent considers correct has no higher
authority than any other model output. Use Studium source audits, mathematical
and domain-appropriate checks, contradiction scan and book review. Unverified,
incomplete or disputed claims must remain clearly identified.

The CLI can inspect a proposed plan:

```bash
studium agent-plan --project ./history --objective book --discipline "Historia medieval"
```

The orchestration contract is a first step toward Claude Code agent packages,
a ChatGPT integration and provider-specific parallel execution; those adapters
are not yet implemented. The existing `studium mcp` is the integration point.

## Requesting a new and improved edition

From Claude/ChatGPT, a user can ask:

> Crea una nueva edición de mi libro de historia, con bibliografía más actual,
> mejores explicaciones y más análisis de fuentes primarias.

The client uses:

```json
{
  "name": "studium_edition_create",
  "arguments": {
    "project": "historia",
    "request": "Revisar fuentes, actualizar bibliografía y mejorar las actividades de análisis histórico"
  }
}
```

Or from a terminal:

```bash
studium edition --project ./historia \
  --request "Revisar bibliografía, mejorar los capítulos y los ejercicios"
studium editions --project ./historia
```

Studium creates `historia-edition-2` (then `-3`, etc.), increments the version
(`0.1.0` → `0.2.0` unless a newer version is specified), and inherits the
source records, current structure and authoring work. It clears edition-specific
audits, reviews, contradiction scans, workflow records and generated draft
outputs, then starts a discipline-specific **revision workflow**. The original
directory, generated PDF and metadata are not overwritten. An edition stores
its parent, version, requested improvements and creation timestamp in
`.studium/edition.json`.

**A request starts the improvement process; it does not mean that an AI has
already rewritten, verified or exported the book.** The client must process the
workflow and run Studium's quality checks before rendering the new draft. Source
URLs and external local file references may become stale; the agents must
revalidate them and bring in new evidence where appropriate.

### Safety and compatibility

- No mandatory AI subscription. Studium stays usable with supported MCP
  clients and the CLI; the execution client decides its model costs.
- Submissions do not change academic verification statuses or bypass quality
  gates. `ACADEMICALLY_REVIEWED` remains human-only.
- Edition creation refuses projects containing symbolic links and never writes
  outside the current project workspace. Each edition has its own files.
- All editions are **drafts** unless separate review and publication workflows
  explicitly establish something more.
- The first version of this feature intentionally does **not** implement
  autonomous research, multi-provider inference, new ChatGPT/Claude extension
  installation, or continuously scheduled improvement.

## Future integration work

Add provider-specific skill bundles, true concurrent execution when available,
reconciliation of independently authored revisions, trusted audit evidence
rather than unverified submission IDs, and user-facing edition diff/release
management. Validate cross-domain quality on mathematics, biology, history
and political science rather than counting agent messages.
