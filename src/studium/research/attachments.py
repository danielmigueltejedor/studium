"""Turn an authorized host handle into intake input.

The handle is an opaque id from the client. This module does not open it,
and it does not import a ChatGPT or Claude SDK.
"""

from pathlib import Path


def attachment_to_intake(handle: str, filename: str, content: bytes) -> dict[str, object]:
    if not isinstance(handle, str) or not handle.strip():
        raise ValueError("sources.attachment_not_authorized")
    if not isinstance(content, (bytes, bytearray)):
        raise ValueError("sources.attachment_not_authorized")
    if not isinstance(filename, str) or not filename.strip():
        raise ValueError("mcp.invalid_input")
    safe_name = Path(filename).name
    if safe_name in {"", ".", ".."}:
        raise ValueError("mcp.invalid_input")
    return {
        "handle": handle.strip(),
        "filename": safe_name,
        "content": bytes(content),
        "origin": "user_uploaded",
    }
