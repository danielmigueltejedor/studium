"""Streamable HTTP transport for the same ``handle`` core. No second policy.

Protocol shape: MCP 2025-03-26. One endpoint, ``/mcp``, accepts POST and GET.
POST returns JSON or one SSE response. GET opens an SSE stream. ``--public``
publishes that endpoint with a Cloudflare quick tunnel, which does not need an
account.
"""

import hmac
import json
import os
import platform
import re
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
import traceback
from collections.abc import Mapping
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import BinaryIO
from urllib.parse import urlparse

from studium.mcp.server import (
    McpSession,
    acceptable_protocol_header,
    handle,
    open_workspace,
)

_MAX_BODY = 32 * 1024 * 1024
_TUNNEL_URL = re.compile(r"https://[A-Za-z0-9-]+\.trycloudflare\.com")
_ALLOWED_ORIGIN_SUFFIXES = (".chatgpt.com", ".openai.com")
_ALLOWED_ORIGIN_HOSTS = {"chatgpt.com", "openai.com", "chat.openai.com", "localhost", "127.0.0.1", "::1"}


@dataclass
class HttpState:
    session: McpSession
    token: str | None
    stop: threading.Event = field(default_factory=threading.Event)
    session_ids: set[str] = field(default_factory=set)
    events: int = 0


class HttpEndpoint:
    def __init__(self, httpd: ThreadingHTTPServer, thread: threading.Thread, state: HttpState) -> None:
        self.httpd = httpd
        self.thread = thread
        self.state = state
        self._closed = False

    @property
    def port(self) -> int:
        return int(self.httpd.server_address[1])

    @property
    def url(self) -> str:
        return local_mcp_url(self.port)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.state.stop.set()
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)


def local_mcp_url(port: int) -> str:
    return f"http://127.0.0.1:{port}/mcp"


def cloudflared_args(port: int) -> list[str]:
    # HTTP/2 is Cloudflare's fallback when UDP/QUIC to port 7844 is blocked.
    return [
        "tunnel",
        "--url",
        f"http://127.0.0.1:{port}",
        "--protocol",
        "http2",
        "--no-autoupdate",
    ]


def run_command(port: int) -> str:
    return "cloudflared " + " ".join(cloudflared_args(port))


def install_command() -> str:
    system = platform.system()
    machine = platform.machine().lower()
    if system == "Darwin":
        return "brew install cloudflared"
    if system == "Windows":
        return "winget install --id Cloudflare.cloudflared"
    asset = "cloudflared-linux-arm64" if machine in {"aarch64", "arm64"} else "cloudflared-linux-amd64"
    url = f"https://github.com/cloudflare/cloudflared/releases/latest/download/{asset}"
    return (
        f"curl -fsSL -o /tmp/cloudflared {url} && chmod +x /tmp/cloudflared && "
        "sudo install -m 755 /tmp/cloudflared /usr/local/bin/cloudflared"
    )


def missing_cloudflared_text(port: int) -> str:
    return "\n".join(
        [
            local_mcp_url(port),
            "cloudflared is not installed, so there is no public URL.",
            f"Install: {install_command()}",
            f"Run: {run_command(port)}",
        ]
    )


def public_mcp_url(log: str) -> str | None:
    match = _TUNNEL_URL.search(log)
    if match is None:
        return None
    return match.group(0) + "/mcp"


def start_http_server(
    *,
    workspace: str | None = None,
    default_project: str | None = None,
    port: int = 8765,
    token: str | None = None,
) -> HttpEndpoint | None:
    session = open_workspace(workspace, default_project)
    if session is None:
        return None
    state = HttpState(session=session, token=token or None)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), _handler(state))
    httpd.daemon_threads = True
    thread = threading.Thread(target=httpd.serve_forever, name="studium-mcp-http", daemon=True)
    thread.start()
    _wait_until_listening(int(httpd.server_address[1]))
    return HttpEndpoint(httpd, thread, state)


def serve_http(
    *,
    workspace: str | None = None,
    default_project: str | None = None,
    port: int = 8765,
    token: str | None = None,
    public: bool = False,
) -> int:
    binary = shutil.which("cloudflared") if public else None
    if public and binary is None:
        print(missing_cloudflared_text(port), flush=True)
        return 1
    try:
        endpoint = start_http_server(
            workspace=workspace,
            default_project=default_project,
            port=port,
            token=token,
        )
    except OSError as exc:
        print(f"could not listen on 127.0.0.1:{port}: {exc}", file=sys.stderr)
        return 1
    if endpoint is None:
        print("workspace not found", file=sys.stderr)
        return 3
    proc: subprocess.Popen[bytes] | None = None
    try:
        if not public:
            print(endpoint.url, flush=True)
            return _wait(endpoint, None)
        assert binary is not None
        proc = subprocess.Popen(
            [binary, *cloudflared_args(endpoint.port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        url = _wait_for_public_url(proc, timeout=30)
        if url is None:
            print(missing_cloudflared_text(endpoint.port), flush=True)
            return 1
        print(url, flush=True)
        return _wait(endpoint, proc)
    except KeyboardInterrupt:
        return 0
    finally:
        _stop_process(proc)
        endpoint.close()


def _wait(endpoint: HttpEndpoint, proc: subprocess.Popen[bytes] | None) -> int:
    stopped = threading.Event()

    def _handle_signal(signum: int, frame: object) -> None:
        stopped.set()

    watched = (signal.SIGINT, signal.SIGTERM)
    previous = {sig: signal.getsignal(sig) for sig in watched}
    for sig in watched:
        signal.signal(sig, _handle_signal)
    try:
        while not stopped.is_set():
            if proc is not None:
                code = proc.poll()
                if code is not None:
                    return code
            if endpoint.state.stop.is_set():
                return 0
            stopped.wait(0.25)
        return 0
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def _wait_for_public_url(proc: subprocess.Popen[bytes], timeout: float) -> str | None:
    holder: list[str] = []
    found = threading.Event()

    def pump(stream: BinaryIO) -> None:
        carry = ""
        try:
            while True:
                line = stream.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace")
                sys.stderr.write(text)
                sys.stderr.flush()
                carry = (carry + text)[-4096:]
                if not holder:
                    url = public_mcp_url(carry)
                    if url is not None:
                        holder.append(url)
                        found.set()
        except OSError:
            return

    threads: list[threading.Thread] = []
    for stream in (proc.stdout, proc.stderr):
        if stream is None:
            continue
        thread = threading.Thread(target=pump, args=(stream,), daemon=True)
        thread.start()
        threads.append(thread)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if holder:
            return holder[0]
        if proc.poll() is not None:
            found.wait(0.2)
            return holder[0] if holder else None
        found.wait(0.2)
    return holder[0] if holder else None


def _stop_process(proc: subprocess.Popen[bytes] | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            proc.kill()
        proc.wait(timeout=5)


def _wait_until_listening(port: int) -> None:
    import socket

    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.02)
    raise OSError(f"127.0.0.1:{port} did not accept connections")


def _handler(state: HttpState) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: object) -> None:
            return

        def do_GET(self) -> None:
            _get(self, state)

        def do_POST(self) -> None:
            _post(self, state)

        def do_DELETE(self) -> None:
            _delete(self, state)

        def do_OPTIONS(self) -> None:
            if not _guard(self, state):
                return
            self.send_response(204)
            self.send_header("Allow", "GET, POST, DELETE, OPTIONS")
            self.send_header("Content-Length", "0")
            self.end_headers()

    return Handler


def _endpoint_path(raw: str) -> str:
    path = urlparse(raw).path
    if path == "/mcp/":
        return "/mcp"
    return path


def _guard(handler: BaseHTTPRequestHandler, state: HttpState) -> bool:
    if _endpoint_path(handler.path) != "/mcp":
        _send_json(handler, 404, {"jsonrpc": "2.0", "id": None, "error": {"code": -32601, "message": "not found"}})
        return False
    if not _origin_allowed(handler.headers.get("Origin")):
        _send_json(handler, 403, {"jsonrpc": "2.0", "id": None, "error": {"code": -32003, "message": "origin rejected"}})
        return False
    if not _bearer_ok(handler.headers.get("Authorization"), state.token):
        handler.send_response(401)
        handler.send_header("WWW-Authenticate", "Bearer")
        handler.send_header("Content-Type", "application/json")
        body = json.dumps(
            {"jsonrpc": "2.0", "id": None, "error": {"code": -32001, "message": "unauthorized"}}
        ).encode("utf-8")
        handler.send_header("Content-Length", str(len(body)))
        handler.send_header("Cache-Control", "no-store")
        handler.end_headers()
        handler.wfile.write(body)
        return False
    return True


def _origin_allowed(origin: str | None) -> bool:
    if origin is None or origin == "":
        return True
    if origin == "null":
        return False
    parsed = urlparse(origin)
    if parsed.scheme not in {"http", "https"}:
        return False
    host = (parsed.hostname or "").lower()
    if host in _ALLOWED_ORIGIN_HOSTS:
        return True
    return any(host.endswith(suffix) for suffix in _ALLOWED_ORIGIN_SUFFIXES)


def _bearer_ok(header: str | None, token: str | None) -> bool:
    if not token:
        return True
    if header is None:
        return False
    scheme, separator, rest = header.partition(" ")
    if scheme != "Bearer" or separator != " " or not rest or rest != rest.strip():
        return False
    return hmac.compare_digest(rest, token)


def _session_rejected(handler: BaseHTTPRequestHandler, state: HttpState) -> bool:
    raw = handler.headers.get("Mcp-Session-Id")
    if raw is None:
        return False
    if raw in state.session_ids:
        return False
    _send_json(handler, 404, {"jsonrpc": "2.0", "id": None, "error": {"code": -32004, "message": "session not found"}})
    return True


def _get(handler: BaseHTTPRequestHandler, state: HttpState) -> None:
    if not _guard(handler, state) or _session_rejected(handler, state):
        return
    accept = handler.headers.get("Accept", "")
    if "text/event-stream" not in accept.lower():
        _send_json(handler, 406, {"jsonrpc": "2.0", "id": None, "error": {"code": -32006, "message": "text/event-stream required"}})
        return
    version = handler.headers.get("MCP-Protocol-Version")
    if not acceptable_protocol_header(version):
        _send_json(handler, 400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "unsupported protocol version"}})
        return
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream")
    handler.send_header("Cache-Control", "no-cache")
    handler.end_headers()
    try:
        handler.wfile.write(b": connected\n\n")
        handler.wfile.flush()
        while not state.stop.wait(0.25):
            handler.wfile.write(b": ping\n\n")
            handler.wfile.flush()
    except (BrokenPipeError, ConnectionResetError, OSError):
        return


def _delete(handler: BaseHTTPRequestHandler, state: HttpState) -> None:
    if not _guard(handler, state):
        return
    raw = handler.headers.get("Mcp-Session-Id")
    if raw is None:
        _send_json(handler, 400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "session id required"}})
        return
    if raw not in state.session_ids:
        _send_json(handler, 404, {"jsonrpc": "2.0", "id": None, "error": {"code": -32004, "message": "session not found"}})
        return
    state.session_ids.discard(raw)
    handler.send_response(204)
    handler.send_header("Content-Length", "0")
    handler.end_headers()


def _post(handler: BaseHTTPRequestHandler, state: HttpState) -> None:
    if not _guard(handler, state):
        return
    accept = handler.headers.get("Accept", "")
    if not _accept_ok(accept):
        _send_json(
            handler,
            406,
            {"jsonrpc": "2.0", "id": None, "error": {"code": -32006, "message": "accept application/json or text/event-stream"}},
        )
        return
    content_type = handler.headers.get("Content-Type", "")
    if content_type and "application/json" not in content_type.lower():
        _send_json(handler, 415, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "content type must be application/json"}})
        return
    length_header = handler.headers.get("Content-Length")
    if length_header is None:
        _send_json(handler, 411, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "content length required"}})
        return
    try:
        length = int(length_header)
    except ValueError:
        _send_json(handler, 400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "bad content length"}})
        return
    if length < 0 or length > _MAX_BODY:
        _send_json(handler, 413, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "body too large"}})
        return
    body = handler.rfile.read(length) if length else b""
    try:
        loaded = json.loads(body.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        _send_json(handler, 400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}})
        return
    messages = loaded if isinstance(loaded, list) else [loaded]
    if not messages or not all(isinstance(item, dict) for item in messages):
        _send_json(handler, 400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "invalid request"}})
        return
    requests = [item for item in messages if _is_request(item)]
    initialize_only = bool(messages) and all(
        _is_request(item) and item.get("method") == "initialize" for item in messages
    )
    if not initialize_only and _session_rejected(handler, state):
        return
    if any(item.get("method") != "initialize" for item in requests):
        version = handler.headers.get("MCP-Protocol-Version")
        if not acceptable_protocol_header(version):
            _send_json(handler, 400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "unsupported protocol version"}})
            return
    responses: list[dict[str, object]] = []
    new_session: str | None = None
    try:
        for message in messages:
            if not isinstance(message, dict):
                continue
            if _is_request(message):
                response = handle(message, session=state.session)
                if response is None:
                    response = {
                        "jsonrpc": "2.0",
                        "id": message.get("id"),
                        "error": {"code": -32603, "message": "empty response"},
                    }
                responses.append(response)
                if message.get("method") == "initialize":
                    new_session = secrets.token_hex(16)
                    state.session_ids.add(new_session)
            elif _is_notification(message):
                handle(message, session=state.session)
            elif not _is_client_response(message):
                _send_json(handler, 400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "invalid request"}})
                return
    except Exception:
        traceback.print_exc(file=sys.stderr)
        _send_json(handler, 500, {"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": "internal error"}})
        return
    extra: list[tuple[str, str]] = []
    if new_session is not None:
        extra.append(("Mcp-Session-Id", new_session))
    if not responses:
        handler.send_response(202)
        handler.send_header("Content-Length", "0")
        for key, value in extra:
            handler.send_header(key, value)
        handler.end_headers()
        return
    payload: object = responses[0] if len(responses) == 1 and not isinstance(loaded, list) else responses
    if _prefers_sse(accept):
        _send_sse(handler, payload, state, extra)
        return
    _send_json(handler, 200, payload, extra)


def _accept_ok(accept: str) -> bool:
    if not accept.strip():
        return True
    lowered = accept.lower()
    return "application/json" in lowered or "text/event-stream" in lowered


def _prefers_sse(accept: str) -> bool:
    """SSE when the client accepts an event stream, including when JSON is also listed."""

    return "text/event-stream" in accept.lower()


def _is_request(message: Mapping[str, object]) -> bool:
    return isinstance(message.get("method"), str) and "id" in message and message.get("id") is not None


def _is_notification(message: Mapping[str, object]) -> bool:
    return isinstance(message.get("method"), str) and ("id" not in message or message.get("id") is None)


def _is_client_response(message: Mapping[str, object]) -> bool:
    return "method" not in message and ("result" in message or "error" in message)


def _send_json(
    handler: BaseHTTPRequestHandler,
    status: int,
    payload: object,
    extra: list[tuple[str, str]] | None = None,
) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    for key, value in extra or []:
        handler.send_header(key, value)
    handler.end_headers()
    handler.wfile.write(body)


def _send_sse(
    handler: BaseHTTPRequestHandler,
    payload: object,
    state: HttpState,
    extra: list[tuple[str, str]],
) -> None:
    messages = payload if isinstance(payload, list) else [payload]
    chunks: list[bytes] = []
    for message in messages:
        state.events += 1
        encoded = json.dumps(message, ensure_ascii=False)
        lines = [f"id: {state.events}", "event: message"]
        lines.extend(f"data: {line}" for line in encoded.split("\n"))
        lines.append("")
        lines.append("")
        chunks.append("\n".join(lines).encode("utf-8"))
    body = b"".join(chunks)
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream")
    handler.send_header("Cache-Control", "no-cache")
    handler.send_header("Content-Length", str(len(body)))
    for key, value in extra:
        handler.send_header(key, value)
    handler.end_headers()
    handler.wfile.write(body)

