"""Read a CLI path only when it stays inside the project."""

from pathlib import Path

_SENSITIVE_DIRS = frozenset({".ssh", ".aws", ".gnupg", ".kube"})
_SENSITIVE_NAMES = frozenset(
    {
        ".env",
        "id_rsa",
        "id_ed25519",
        "id_dsa",
        "credentials",
        "credentials.json",
        "passwd",
        "shadow",
        "known_hosts",
    }
)


class OutsideProjectError(ValueError):
    """The path is empty, sensitive, a symlink, or outside the project."""


def resolve_inside_project(root: Path, raw: str) -> Path:
    """Absolute path of a regular file under ``root``.

    Relative paths are resolved from the project, not the process working
    directory. A symlink is refused so the resolved path cannot leave ``root``.
    """

    if not isinstance(raw, str) or not raw.strip() or "\x00" in raw:
        raise OutsideProjectError("path is empty")
    base = root.resolve()
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = base / candidate
    if candidate.is_symlink():
        raise OutsideProjectError("refusing a symlink")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise OutsideProjectError("file could not be read") from exc
    if not resolved.is_relative_to(base):
        raise OutsideProjectError("path escapes the project")
    if resolved.name in _SENSITIVE_NAMES or set(resolved.parts) & _SENSITIVE_DIRS:
        raise OutsideProjectError("refusing a credential path")
    if not resolved.is_file():
        raise OutsideProjectError("path is not a file")
    return resolved
