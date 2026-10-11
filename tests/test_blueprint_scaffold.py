"""Blueprint scaffold: flat outline → academic blueprint."""

from studium.mcp.server import dispatch, open_workspace

_COURSE = {
    "course": "Mecánica de Fluidos",
    "university": "Universidad de León",
    "degree": "Grado en Ingeniería Aeroespacial",
    "language": "es",
    "profile": "STEM",
}


def _project(tmp_path, slug="fluidos"):
    session = open_workspace(str(tmp_path))
    created = dispatch("studium_project_create", {"slug": slug, **_COURSE}, session=session)
    assert created["status"] == "created", created
    return session


def _flat_blueprint(session, n=8):
    sections = [{"id": f"ch-{i}", "title": f"Chapter {i}"} for i in range(1, n + 1)]
    stored = dispatch("studium_blueprint_store", {"sections": sections}, session=session)
    assert stored["status"] == "recorded", stored
    return stored


def _explode(*_a, **_kw):
    raise RuntimeError("no network")


def test_scaffold_creates_academic_blueprint(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session = _project(tmp_path)
    _flat_blueprint(session, n=8)

    result = dispatch(
        "studium_academic_blueprint_scaffold",
        {"profile_key": "UNDERGRADUATE", "subject": "Fluid Mechanics"},
        session=session,
    )
    assert result["status"] == "recorded", result
    parts = result["blueprint"]["parts"]
    assert len(parts) == 2
    assert parts[0]["id"] == "part-1"
    assert parts[1]["id"] == "part-2"
    assert len(parts[0]["chapters"]) == 5
    assert len(parts[1]["chapters"]) == 3


def test_scaffold_chapters_have_sections_and_concepts(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session = _project(tmp_path)
    _flat_blueprint(session, n=3)

    result = dispatch(
        "studium_academic_blueprint_scaffold",
        {"profile_key": "GRADUATE", "subject": "Thermodynamics"},
        session=session,
    )
    assert result["status"] == "recorded"
    chapter = result["blueprint"]["parts"][0]["chapters"][0]
    assert chapter["id"] == "ch-1"
    assert chapter["title"] == "Chapter 1"
    sections = chapter["sections"]
    assert len(sections) == 1
    assert sections[0]["id"] == "ch-1.s1"
    concepts = sections[0]["concepts"]
    assert len(concepts) == 1
    assert concepts[0]["id"] == "ch-1.c1"
    assert concepts[0]["depth"] == "GRADUATE"


def test_scaffold_custom_chapters_per_part(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session = _project(tmp_path)
    _flat_blueprint(session, n=9)

    result = dispatch(
        "studium_academic_blueprint_scaffold",
        {"chapters_per_part": 3},
        session=session,
    )
    assert result["status"] == "recorded"
    assert len(result["blueprint"]["parts"]) == 3
    for part in result["blueprint"]["parts"]:
        assert len(part["chapters"]) == 3


def test_scaffold_refuses_without_flat_blueprint(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session = _project(tmp_path)

    result = dispatch("studium_academic_blueprint_scaffold", {}, session=session)
    assert result["status"] == "mcp.invalid_input"
    assert "flat blueprint" in result["message"]


def test_scaffold_refuses_when_academic_already_exists(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session = _project(tmp_path)
    _flat_blueprint(session, n=4)

    first = dispatch("studium_academic_blueprint_scaffold", {}, session=session)
    assert first["status"] == "recorded"

    second = dispatch("studium_academic_blueprint_scaffold", {}, session=session)
    assert second["status"] == "mcp.invalid_input"
    assert "already exists" in second["message"]


def test_scaffold_no_depth_when_no_profile(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session = _project(tmp_path)
    _flat_blueprint(session, n=2)

    result = dispatch("studium_academic_blueprint_scaffold", {}, session=session)
    assert result["status"] == "recorded"
    concept = result["blueprint"]["parts"][0]["chapters"][0]["sections"][0]["concepts"][0]
    assert "depth" not in concept


def test_scaffold_subject_stored(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session = _project(tmp_path)
    _flat_blueprint(session, n=2)

    result = dispatch(
        "studium_academic_blueprint_scaffold",
        {"subject": "Quantum Mechanics"},
        session=session,
    )
    assert result["status"] == "recorded"
    assert result["blueprint"]["subject"] == "Quantum Mechanics"


def test_scaffold_concept_count(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session = _project(tmp_path)
    _flat_blueprint(session, n=10)

    result = dispatch("studium_academic_blueprint_scaffold", {}, session=session)
    assert result["status"] == "recorded"
    assert result["concepts"] == 10
