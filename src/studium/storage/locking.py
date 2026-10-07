"""Exclusive project write lock. One writer; a second request fails closed."""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class ProjectLocked(Exception):
    """Raised when ``.studium/write.lock`` is already held."""


@contextmanager
def project_lock(root: Path) -> Iterator[None]:
    lock = root / ".studium" / "write.lock"
    fd: int | None = None
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError as exc:
        raise ProjectLocked("storage.locked") from exc
    try:
        yield
    finally:
        if fd is not None:
            os.close(fd)
        lock.unlink(missing_ok=True)
