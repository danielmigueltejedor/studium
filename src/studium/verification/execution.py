"""Local authorization for reviewed, author-owned host code; never a sandbox.

Documents and MCP arguments cannot grant this capability. Untrusted source needs
an externally isolated executor, which Studium does not currently provide.
"""

import hashlib
import json
from dataclasses import dataclass


def execution_input_sha256(source: str, invocation: list[str]) -> str:
    """Bind an authorization to exact source bytes and the requested operation."""

    payload = json.dumps([source, invocation], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ReviewedHostExecution:
    """Explicit local review of trusted author-owned code, not external code.

    Construct only after reviewing the exact source and invocation. This is a
    Python capability, deliberately absent from CLI/MCP input schemas. It does
    not isolate filesystem access, network access or child processes.
    """

    input_sha256: str
    reviewer: str
    reason: str

    def __post_init__(self) -> None:
        if len(self.input_sha256) != 64 or any(c not in "0123456789abcdef" for c in self.input_sha256):
            raise ValueError("input_sha256 must be a lowercase SHA-256 digest")
        if not self.reviewer.strip() or not self.reason.strip():
            raise ValueError("reviewer and reason are required")

    def audit_record(self) -> dict[str, object]:
        return {
            "kind": "reviewed_author_owned_host_execution",
            "input_sha256": self.input_sha256,
            "reviewer": self.reviewer,
            "reason": self.reason,
            "isolated": False,
        }


def host_execution_authorized(
    source: str, invocation: list[str], authorization: ReviewedHostExecution | None,
) -> bool:
    return (
        isinstance(authorization, ReviewedHostExecution)
        and authorization.input_sha256 == execution_input_sha256(source, invocation)
    )


def isolation_required(source: str) -> dict[str, object]:
    return {
        "status": "execution.isolation_required",
        "checked": False,
        "correct": False,
        "classification": "UNVERIFIED",
        "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "runs": [],
        "message": (
            "Untrusted code was not executed. No isolated executor is configured. "
            "MCP and CLI cannot authorize host execution. Only a local Python caller may "
            "explicitly authorize exact reviewed, author-owned source and invocation; "
            "resource limits and Python guards are not a security sandbox."
        ),
    }
