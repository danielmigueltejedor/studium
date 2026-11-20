# Studium for Claude Code — full MCP parity with ChatGPT

Claude Code and ChatGPT connect to the **same Studium server/tool catalog**:
Claude uses the bundled **stdio** MCP connection, while ChatGPT uses the
authenticated **Streamable HTTP** MCP endpoint. Both routes dispatch through
`studium.mcp.server.handle` and return the **same tool names, descriptions and
JSON input schemas**; neither is a reduced or hardcoded tool list.

The plugin offers additional *Claude-native* specialist agents and skills,
but their existence does not remove any MCP tool. Skills/subagents have no
`tools` allowlist; the session's permissions and tool availability still apply.
Claude's tool-search/discovery feature may display only relevant tools at a
time when the catalog is large; that is not a server-side limitation.

## Install

1. Install the **same Studium version** used by your book workspace:
   `python -m pip install -e .` from the repo checkout (Python 3.11+).
2. Start Claude Code from the directory holding your Studium projects, or
   configure the server's `--workspace` argument if you use another directory.
3. Load the plugin:

```sh
claude --plugin-dir /absolute/path/to/studium/integrations/claude/plugin
```

Check plugin validity and MCP connectivity with:

```sh
claude plugin validate /absolute/path/to/studium/integrations/claude/plugin
```

In Claude Code, use `/mcp`, ask for `studium_server_info`, and inspect the
reported `tool_count`, `new_tools`, `removed_tools` and `stale`. If stale,
use `studium_server_reload` or restart Claude Code. The plugin's
`.mcp.json` invokes **`studium mcp` without tool filtering**. The underlying
binary must be installed and accessible on `PATH`.

> For *data parity*, ensure Claude and ChatGPT point to the **same workspace**
> and compatible Studium version. Otherwise each transport can have the same
> tools while displaying different books or revisions.

## Capabilities

| Invoke | Skill | Typical specialist agents |
| --- | --- | --- |
| `/studium:book` | Create or improve a research-grounded book | librarian, subject specialist, activity designer, independent critic, editor |
| `/studium:learn` | Teach any subject at an appropriate level | subject specialist, learning designer |
| `/studium:research` | Research claims and collect sources | bibliography researcher, domain evidence reviewer |
| `/studium:verify` | Check book, evidence and calculations | quantitative verifier, evidence reviewer, adversarial critic |
| `/studium:new-edition` | Request a successor edition without overwriting the old book | multidisciplinary reviewers and editor |

These workflows can use **all current and future Studium MCP tools**, including
source records, blueprint, authoring, math and verification, diagrams and
rendering, quality reports, and edition management. Each subagent receives
limited relevant context; project writes must be serialized. A reviewer
should not see an author's conclusions before independent checking.

## Verification and regression testing

The repo contains a transport parity test:

```sh
python -m pytest -q tests/test_claude_plugin_parity.py
```

It compares the **full tools/list response** from a local stdio MCP instance
(the Claude route) and Streamable HTTP (the ChatGPT route), plus the plugin
manifest and discoverability of agents/skills. The test is not a live Claude
or ChatGPT UI acceptance test; verify both actual client connections before
claiming installation on a machine.

## Safety

The plugin does not bypass client permission prompts, invent research sources,
run undocumented external services or grant `ACADEMICALLY_REVIEWED` status.
Creating a new edition means a new **draft project and improvement plan**,
not that an autonomous LLM has already rewritten, checked, and rendered it.
