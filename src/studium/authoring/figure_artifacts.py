"""Shared availability check for a previously produced figure artifact.

This checks the stored production result and a contained nonempty output. It
does not verify the figure's scientific meaning or detect arbitrary edits to
legacy outputs that have no stored output hash.
"""

from pathlib import Path


def checked_figure_output(root: Path, record: dict[str, object]) -> str | None:
    if record.get("status") != "checked" or record.get("correct") is not True:
        return None
    output = record.get("output")
    if not isinstance(output, str) or not output.startswith("figures/FIG-") or ".." in Path(output).parts:
        return None
    if not output.endswith(("/figure.png", "/figure.pdf", "/figure.jpg")):
        return None
    original = root / output
    try:
        path = original.resolve()
        path.relative_to(root.resolve())
        if original.is_symlink() or not path.is_file() or path.stat().st_size <= 0:
            return None
    except (OSError, ValueError):
        return None
    return output
