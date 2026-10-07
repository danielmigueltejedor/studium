"""Stage 0 boolean projects still open, and new projects store local_sources."""

import json

from studium.domain.enums import ProjectState
from studium.storage.init_project import load_state

_HISTORY = [
    {"from": None, "to": "CREATED", "event": "project_created"},
    {"from": "CREATED", "to": "COURSE_DISCOVERY", "event": "begin_discovery"},
]


def _stage0(root, *, missing: bool) -> None:
    state = {
        "schema_version": "1.0.0",
        "state": "COURSE_DISCOVERY",
        "edition_cycle": 1,
        "local_sources_missing": missing,
        "history": _HISTORY,
    }
    path = root / ".studium" / "state.json"
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def test_local_sources_are_not_a_project_state():
    assert "LOCAL_SOURCE_DECISION" not in {item.value for item in ProjectState}
    assert ProjectState.COURSE_DISCOVERY.value == "COURSE_DISCOVERY"


def test_boolean_true_migrates_to_unknown_even_when_labeled(tmp_path):
    root = tmp_path / "fluidos"
    root.mkdir()
    (root / ".studium").mkdir()
    (root / "project.toml").write_text(
        '[course]\nname = "C"\nuniversity = "U"\ndegree = "D"\nlocal_sources = "private-notes"\n',
        encoding="utf-8",
    )
    _stage0(root, missing=True)

    state = load_state(root)

    assert state["schema_version"] == "1.0.0"
    assert state["state"] == "COURSE_DISCOVERY"
    assert state["history"] == _HISTORY
    assert "local_sources_missing" not in state
    local = state["local_sources"]
    assert local["status"] == "UNKNOWN"
    assert local["prompted"] is False
    assert local["source_count"] == 0
    assert local["status"] != "NONE"
    stored = json.loads((root / ".studium" / "state.json").read_text(encoding="utf-8"))
    assert "local_sources_missing" not in stored
    assert stored["local_sources"]["status"] == "UNKNOWN"


def test_boolean_false_without_label_migrates_to_unknown(tmp_path):
    root = tmp_path / "fluidos"
    root.mkdir()
    (root / ".studium").mkdir()
    (root / "project.toml").write_text(
        '[course]\nname = "C"\nuniversity = "U"\ndegree = "D"\n',
        encoding="utf-8",
    )
    _stage0(root, missing=False)

    local = load_state(root)["local_sources"]
    assert local["status"] == "UNKNOWN"
    assert local["prompted"] is False
    assert local["source_count"] == 0


def test_boolean_false_with_label_migrates_to_available(tmp_path):
    root = tmp_path / "fluidos"
    root.mkdir()
    (root / ".studium").mkdir()
    (root / "project.toml").write_text(
        '[course]\nname = "C"\nuniversity = "U"\ndegree = "D"\nlocal_sources = "notes"\n',
        encoding="utf-8",
    )
    _stage0(root, missing=False)

    local = load_state(root)["local_sources"]
    assert local["status"] == "AVAILABLE"
    assert local["prompted"] is False
    assert local["source_count"] == 0
    assert local["status"] != "IMPORTED"


def test_object_wins_when_the_boolean_is_also_present(tmp_path):
    root = tmp_path / "fluidos"
    root.mkdir()
    (root / ".studium").mkdir()
    (root / "project.toml").write_text(
        '[course]\nname = "C"\nuniversity = "U"\ndegree = "D"\n',
        encoding="utf-8",
    )
    state = {
        "schema_version": "1.0.0",
        "state": "COURSE_DISCOVERY",
        "edition_cycle": 1,
        "local_sources_missing": True,
        "local_sources": {
            "status": "SKIPPED",
            "prompted": True,
            "source_count": 0,
            "last_updated": "2026-10-07T00:00:00Z",
        },
        "history": _HISTORY,
    }
    (root / ".studium" / "state.json").write_text(json.dumps(state) + "\n", encoding="utf-8")

    loaded = load_state(root)
    assert loaded["local_sources"]["status"] == "SKIPPED"
    assert loaded["local_sources"]["prompted"] is True
    assert "local_sources_missing" not in loaded
    stored = json.loads((root / ".studium" / "state.json").read_text(encoding="utf-8"))
    assert "local_sources_missing" not in stored
