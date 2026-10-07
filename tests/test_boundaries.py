"""Import direction: dependencies point toward the domain."""

import ast
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"

_ALLOWED = {
    "studium": set(),
    "studium.__main__": {"studium", "studium.cli"},
    "studium.domain": set(),
    "studium.policy": {"studium.domain", "studium.policy"},
    "studium.validation": set(),
    "studium.state": {"studium.domain", "studium.state"},
    "studium.config": set(),
    "studium.storage": {"studium.domain", "studium.state", "studium.storage"},
    "studium.research": {
        "studium.domain",
        "studium.policy",
        "studium.validation",
        "studium.storage",
        "studium.research",
    },
    "studium.cli": {
        "studium",
        "studium.domain",
        "studium.state",
        "studium.storage",
        "studium.config",
        "studium.research",
        "studium.mcp",
        "studium.cli",
    },
    "studium.mcp": {
        "studium",
        "studium.domain",
        "studium.config",
        "studium.research",
        "studium.storage",
        "studium.mcp",
    },
}


def _package_of(path: Path) -> str:
    parts = list(path.relative_to(_SRC).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    if parts[-1] == "__main__":
        return "studium.__main__"
    if len(parts) == 1:
        return "studium"
    return ".".join(parts[:2])


def _imported_layers(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    layers: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level:
            raise AssertionError(f"relative import in {path}")
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        for name in names:
            if name == "studium" or name.startswith("studium."):
                parts = name.split(".")
                layers.add("studium" if len(parts) == 1 else ".".join(parts[:2]))
    return layers


def test_layers_do_not_import_upward():
    files = sorted(_SRC.rglob("*.py"))
    assert files
    for path in files:
        owner = _package_of(path)
        assert owner in _ALLOWED, owner
        illegal = _imported_layers(path) - _ALLOWED[owner]
        assert not illegal, f"{path} imports {sorted(illegal)}"
