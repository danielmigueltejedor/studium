# Studium plugin for Claude Code

This plugin bundles the existing local Studium MCP server, a book-authoring
skill, an improved-edition skill, and specialist/review subagents. It does
not install Python automatically.

Install Studium first (`pip install -e .` from the repository). From a
directory containing your Studium books, run:

```sh
claude --plugin-dir /absolute/path/to/studium/integrations/claude/plugin
```

Validate locally with:

```sh
claude plugin validate /absolute/path/to/studium/integrations/claude/plugin
```

Then call `/studium:book` or `/studium:new-edition`, or ask naturally
to create/improve a book. The plugin launches `studium mcp`, which must
be on `PATH`. Check `/mcp` for its connection status.

The workflow coordinator chooses discipline-specific tasks using the
Studium server. Claude may use its subagents for independent context, but
Studium's deterministic evidence and quality gates remain authoritative.
Neither this plugin nor an edition request guarantees an academically
verified or automatically completed manuscript.
