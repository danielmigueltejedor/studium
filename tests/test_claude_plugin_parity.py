"""Guard parity between the Claude plugin (stdio MCP) and ChatGPT (HTTP MCP)."""

import json
import urllib.request
from io import BytesIO
from pathlib import Path

from studium.mcp.catalog import tool_names
from studium.mcp.http_server import start_http_server
from studium.mcp.server import read_message, serve, write_message

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "integrations" / "claude" / "plugin"


def _stdio_list(workspace):
    incoming, outgoing = BytesIO(), BytesIO()
    write_message(incoming, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    incoming.seek(0)
    assert serve(incoming, outgoing, workspace=str(workspace)) == 0
    outgoing.seek(0)
    return read_message(outgoing)["result"]["tools"]


def _http_request(url, message, *, session=None):
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if session:
        headers["Mcp-Session-Id"] = session
        headers["MCP-Protocol-Version"] = "2025-03-26"
    request = urllib.request.Request(
        url, data=json.dumps(message).encode("utf-8"), headers=headers, method="POST"
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        data = response.read().decode("utf-8")
        if response.headers.get("Content-Type", "").startswith("text/event-stream"):
            fragments = [line[5:].strip() for line in data.splitlines() if line.startswith("data:")]
            body = json.loads("\n".join(fragments))
        else:
            body = json.loads(data)
        return body, response.headers


def test_claude_plugin_starts_the_same_unfiltered_studium_mcp():
    config = json.loads((PLUGIN / ".mcp.json").read_text(encoding="utf-8"))
    servers = config["mcpServers"]
    assert list(servers) == ["studium"]
    assert servers["studium"]["command"] == "studium"
    assert servers["studium"]["args"] == ["mcp"]
    assert "tools" not in servers["studium"]
    assert "disabledTools" not in servers["studium"]
    manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "studium"


def test_stdio_claude_and_http_chatgpt_expose_identical_schemas(tmp_path):
    claude_tools = _stdio_list(tmp_path)
    endpoint = start_http_server(workspace=str(tmp_path), port=0)
    assert endpoint is not None
    try:
        initialized, headers = _http_request(
            endpoint.url,
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                        "clientInfo": {"name": "chatgpt-parity-test", "version": "1"}}},
        )
        assert initialized["result"]["serverInfo"]["name"] == "studium"
        session = headers["Mcp-Session-Id"]
        listed, _headers = _http_request(
            endpoint.url, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, session=session
        )
        chatgpt_tools = listed["result"]["tools"]
        assert claude_tools == chatgpt_tools
        assert {item["name"] for item in claude_tools} == set(tool_names())
        for item in claude_tools:
            assert item["inputSchema"]["type"] == "object"
            assert item["description"]
        for name in (
            "studium_source_intake",
            "studium_math_verify",
            "studium_book_next",
            "studium_book_review",
            "studium_edition_create",
            "studium_agent_workflow_next",
        ):
            assert name in {item["name"] for item in claude_tools}
    finally:
        endpoint.close()


def test_all_claude_agents_and_skills_are_discoverable_without_tool_restrictions():
    agents = sorted((PLUGIN / "agents").glob("*.md"))
    skills = sorted((PLUGIN / "skills").glob("*/SKILL.md"))
    assert len(agents) >= 16
    names = {path.stem for path in agents}
    assert {
        "curriculum-architect", "concept-map-auditor", "assessment-architect",
        "independent-solver", "figure-visualization-auditor",
        "cross-chapter-consistency", "edition-evolution-analyst",
        "accessibility-localization",
    } <= names
    assert len(skills) >= 5
    for path in [*agents, *skills]:
        content = path.read_text(encoding="utf-8")
        assert content.startswith("---\n")
        assert "description:" in content.split("---", 2)[1]
        assert "\ntools:" not in content.split("---", 2)[1]
