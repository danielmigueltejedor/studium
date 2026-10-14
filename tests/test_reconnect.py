"""The server tells the agent when it is stale, and can reload in place.

A client holds the code the MCP server imported at startup. ``studium_server_info``
makes that state visible and ``studium_server_reload`` reloads the catalog and
the server module so a client that honours ``notifications/tools/list_changed``
sees new tools without a process restart.
"""

import io
import json

from studium.mcp import reconnect
from studium.mcp.server import handle, open_workspace, serve, tool_names


def _call(name, arguments=None, session=None):
    response = handle(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments or {}}},
        session=session,
    )
    return json.loads(response["result"]["content"][0]["text"])


def test_initialize_advertises_list_changed():
    response = handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}})
    capabilities = response["result"]["capabilities"]
    assert capabilities["tools"]["listChanged"] is True
    server_info = response["result"]["serverInfo"]
    assert server_info["schema_version"] == "1.0.0"
    assert "mcp_api_version" in server_info


def test_server_info_reports_matching_code(tmp_path):
    session = open_workspace(str(tmp_path))
    info = _call("studium_server_info", session=session)
    assert info["status"] == "ok"
    assert info["stale"] is False
    assert info["code_changed"] is False
    assert info["new_tools"] == []
    assert info["removed_tools"] == []
    assert set(info["loaded_tools"]) == set(tool_names())


def test_server_info_reports_a_new_tool_on_disk(tmp_path, monkeypatch):
    real = reconnect.tool_names_on_disk()
    monkeypatch.setattr(reconnect, "tool_names_on_disk", lambda: [*real, "studium_future_tool"])
    session = open_workspace(str(tmp_path))
    info = _call("studium_server_info", session=session)
    assert info["stale"] is True
    assert info["new_tools"] == ["studium_future_tool"]
    assert "reconnect" in info
    assert "studium_server_reload" in info["reconnect"]


def test_server_info_reports_changed_code(tmp_path, monkeypatch):
    monkeypatch.setattr(reconnect, "code_fingerprint", lambda: "0" * 64)
    session = open_workspace(str(tmp_path))
    info = _call("studium_server_info", session=session)
    assert info["stale"] is True
    assert info["code_changed"] is True
    assert "reload" in info["reconnect"].lower() or "restart" in info["reconnect"].lower()


def test_reload_keeps_the_tool_set_and_dispatch_working(tmp_path):
    session = open_workspace(str(tmp_path))
    before = list(tool_names())
    reloaded = _call("studium_server_reload", session=session)
    assert reloaded["status"] == "reloaded"
    assert reloaded["tool_count"] == len(before)
    assert set(reloaded["tools"]) == set(before)
    # The reloaded module still answers the ordinary tools.
    info = _call("studium_server_info", session=session)
    assert info["status"] == "ok"
    status = _call("studium_project_status", session=session)
    assert isinstance(status, dict) and "status" in status


def test_serve_loop_announces_a_reload(tmp_path):
    message = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {"name": "studium_server_reload", "arguments": {}},
        }
    )
    stdin = io.BytesIO(message.encode("utf-8") + b"\n")
    stdout = io.BytesIO()
    code = serve(stdin, stdout, workspace=str(tmp_path))
    assert code == 0
    lines = [line for line in stdout.getvalue().decode("utf-8").splitlines() if line.strip()]
    methods = [json.loads(line).get("method") for line in lines]
    assert "notifications/tools/list_changed" in methods


def test_unknown_tool_message_is_stable(tmp_path):
    session = open_workspace(str(tmp_path))
    response = handle(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "studium_nope", "arguments": {}}},
        session=session,
    )
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["status"] == "mcp.unknown_tool"


def test_cli_check_prints_the_installed_catalog(capsys):
    from studium.cli.app import main

    code = main(["mcp", "--check"])
    assert code == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["tool_count"] == len(tool_names())
    assert "studium_server_info" in printed["tools"]
    assert "studium_server_reload" in printed["tools"]
    assert "reconnect" in printed["how_to_reconnect"].lower()
