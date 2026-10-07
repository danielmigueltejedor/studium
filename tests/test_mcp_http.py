"""Streamable HTTP uses the same handle() core as stdio."""

import json
import subprocess
import sys
import urllib.error
import urllib.request
from io import BytesIO

from studium.cli.app import main
from studium.mcp.http_server import (
    cloudflared_args,
    missing_cloudflared_text,
    public_mcp_url,
    run_command,
    serve_http,
    start_http_server,
)
from studium.mcp.server import read_message, write_message

_COURSE = {
    "slug": "fluidos",
    "course": "Mecánica de Fluidos",
    "university": "Universidad de León",
    "degree": "Grado en Ingeniería Aeroespacial",
}


def test_http_initialize_tools_and_create(tmp_path):
    endpoint = start_http_server(workspace=str(tmp_path), port=0)
    assert endpoint is not None
    try:
        status, headers, initialized = _post(
            endpoint.url,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}},
            },
        )
        assert status == 200
        assert "text/event-stream" in headers.get("Content-Type", "")
        assert initialized["result"]["protocolVersion"] == "2025-03-26"
        assert initialized["result"]["serverInfo"]["name"] == "studium"
        session = headers.get("Mcp-Session-Id")
        assert session

        status, _headers, listed = _post(
            endpoint.url,
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            accept="application/json",
            session=session,
            protocol="2025-03-26",
        )
        assert status == 200
        assert "application/json" in _headers.get("Content-Type", "")
        names = {tool["name"] for tool in listed["result"]["tools"]}
        assert "studium_project_create" in names
        assert "studium_project_list" in names

        status, _headers, before = _post(
            endpoint.url,
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "studium_project_status", "arguments": {}}},
            session=session,
            protocol="2025-03-26",
        )
        assert before["result"]["isError"] is False
        assert before["result"]["structuredContent"]["next_action"] == "create"

        status, _headers, created = _post(
            endpoint.url,
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "studium_project_create", "arguments": _COURSE},
            },
            session=session,
            protocol="2025-03-26",
        )
        assert created["result"]["isError"] is False
        assert created["result"]["structuredContent"]["status"] == "created"
        assert (tmp_path / "fluidos" / "project.toml").is_file()

        status, _headers, after = _post(
            endpoint.url,
            {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "studium_project_status", "arguments": {}}},
            session=session,
            protocol="2025-03-26",
        )
        body = after["result"]["structuredContent"]
        assert body["state"] == "COURSE_DISCOVERY"
        assert body["course"]["name"] == _COURSE["course"]

        noted, _headers, empty = _post(
            endpoint.url,
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            session=session,
            protocol="2025-03-26",
        )
        assert noted == 202
        assert empty is None
    finally:
        endpoint.close()


def test_bearer_token_is_required_when_set(tmp_path):
    endpoint = start_http_server(workspace=str(tmp_path), port=0, token="secret-token")
    assert endpoint is not None
    message = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}}
    try:
        missing, _headers, _body = _post(endpoint.url, message)
        assert missing == 401
        wrong, _headers, _body = _post(endpoint.url, message, token="nope")
        assert wrong == 401
        ok, headers, initialized = _post(endpoint.url, message, token="secret-token")
        assert ok == 200
        assert initialized["result"]["protocolVersion"] == "2025-06-18"
        assert headers.get("Mcp-Session-Id")
    finally:
        endpoint.close()


def test_get_opens_an_sse_stream_and_bad_origin_is_rejected(tmp_path):
    endpoint = start_http_server(workspace=str(tmp_path), port=0)
    assert endpoint is not None
    try:
        import http.client

        connection = http.client.HTTPConnection("127.0.0.1", endpoint.port, timeout=2)
        connection.request("GET", "/mcp", headers={"Accept": "text/event-stream"})
        response = connection.getresponse()
        assert response.status == 200
        assert "text/event-stream" in response.getheader("Content-Type", "")
        chunk = response.read(20)
        assert b"connected" in chunk
        connection.close()

        rejected, _headers, _body = _post(
            endpoint.url,
            {"jsonrpc": "2.0", "id": 1, "method": "initialize"},
            origin="https://evil.example",
        )
        assert rejected == 403
    finally:
        endpoint.close()


def test_stdio_still_answers_initialize(tmp_path):
    incoming = BytesIO()
    write_message(incoming, {"jsonrpc": "2.0", "id": 7, "method": "initialize"})
    incoming.seek(0)
    completed = subprocess.run(
        [sys.executable, "-m", "studium", "mcp"],
        cwd=tmp_path,
        input=incoming.getvalue(),
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0
    parsed = read_message(BytesIO(completed.stdout))
    assert parsed["result"]["serverInfo"]["name"] == "studium"
    assert parsed["result"]["protocolVersion"] == "2024-11-05"


def test_public_without_cloudflared_exits_nonzero(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("studium.mcp.http_server.shutil.which", lambda _name: None)
    assert main(["mcp", "--public"]) == 1
    captured = capsys.readouterr()
    text = captured.out
    assert "http://127.0.0.1:8765/mcp" in text
    assert "cloudflared tunnel --url http://127.0.0.1:8765 --protocol http2 --no-autoupdate" in text
    assert "login" not in run_command(8765)
    assert cloudflared_args(8765) == [
        "tunnel",
        "--url",
        "http://127.0.0.1:8765",
        "--protocol",
        "http2",
        "--no-autoupdate",
    ]


def test_public_url_is_parsed_from_the_quick_tunnel_log():
    log = """
2026-01-01T00:00:00Z INF Requesting new quick Tunnel on trycloudflare.com...
2026-01-01T00:00:00Z INF |  https://orange-apple-1234.trycloudflare.com                         |
"""
    assert public_mcp_url(log) == "https://orange-apple-1234.trycloudflare.com/mcp"
    assert "http://127.0.0.1:9/mcp" in missing_cloudflared_text(9)
    assert "cloudflared tunnel --url http://127.0.0.1:9 --protocol http2 --no-autoupdate" in missing_cloudflared_text(9)


def test_public_prints_one_https_line(tmp_path, monkeypatch, capsys):
    binary = tmp_path / "cloudflared"
    binary.write_text("#!/bin/sh\necho 'https://demo-book.trycloudflare.com' >&2\n", encoding="utf-8")
    binary.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    code = serve_http(workspace=str(tmp_path), port=0, public=True)
    captured = capsys.readouterr()
    assert code == 0
    assert captured.out.strip() == "https://demo-book.trycloudflare.com/mcp"
    assert "\n" not in captured.out.strip()


def _post(url, payload, *, accept="application/json, text/event-stream", token=None, session=None, protocol=None, origin=None):
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": accept,
        "Content-Length": str(len(data)),
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if session:
        headers["Mcp-Session-Id"] = session
    if protocol:
        headers["MCP-Protocol-Version"] = protocol
    if origin:
        headers["Origin"] = origin
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            body = response.read()
            return response.status, response.headers, _decode(response.headers.get("Content-Type", ""), body)
    except urllib.error.HTTPError as exc:
        body = exc.read()
        content_type = exc.headers.get("Content-Type", "")
        decoded = _decode(content_type, body) if body else None
        return exc.code, exc.headers, decoded


def _decode(content_type, body):
    if not body:
        return None
    if "text/event-stream" in content_type:
        data = []
        for line in body.decode("utf-8").splitlines():
            if line.startswith("data:"):
                data.append(line[5:].lstrip())
        return json.loads("\n".join(data))
    return json.loads(body.decode("utf-8"))
