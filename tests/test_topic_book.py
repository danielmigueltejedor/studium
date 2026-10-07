"""Course books keep their fields. Topic books name a subject and do not write yet."""

import json
import tomllib

from studium.cli.app import main
from studium.domain.profiles import EVIDENCE_RULE, TOPIC_BOOK_NEXT_ACTION, TOPIC_BOOK_STATUS, infer_topic_profile
from studium.mcp.server import dispatch, open_workspace
from studium.research.sources import project_status

_COURSE = {
    "course": "Mecánica de Fluidos",
    "university": "Universidad de León",
    "degree": "Grado en Ingeniería Aeroespacial",
}
_CLI_COURSE = [
    "--course",
    _COURSE["course"],
    "--university",
    _COURSE["university"],
    "--degree",
    _COURSE["degree"],
]


def test_programming_topics_use_computer_science():
    assert infer_topic_profile("Programación en C") == "COMPUTER_SCIENCE"
    assert infer_topic_profile("Rust") == "COMPUTER_SCIENCE"
    assert infer_topic_profile("TypeScript") == "COMPUTER_SCIENCE"
    assert infer_topic_profile("Cálculo") == "STEM"
    assert infer_topic_profile("Mecánica de Fluidos") == "STEM"
    assert infer_topic_profile("Ingeniería aeroespacial") == "STEM"
    assert infer_topic_profile("Historia medieval") is None


def test_topic_book_create_fields_and_status_text(tmp_path):
    session = open_workspace(str(tmp_path))
    created = dispatch(
        "studium_project_create",
        {"slug": "programacion-en-c", "topic": "Programación en C"},
        session=session,
    )
    assert created["status"] == "created"
    assert created["message"] == TOPIC_BOOK_STATUS
    assert created["writing_available"] is False
    project = created["project"]
    assert project["message"] == TOPIC_BOOK_STATUS
    assert project["writing_available"] is False
    assert project["course_guide_required"] is False
    assert project["book_kind"] == "topic"
    assert project["evidence"] == EVIDENCE_RULE
    assert project["course"]["kind"] == "topic"
    assert project["course"]["name"] == "Programación en C"
    assert project["course"]["domain_profile"] == "COMPUTER_SCIENCE"
    assert "university" not in project["course"]
    assert "degree" not in project["course"]

    status = dispatch("studium_project_status", {}, session=session)
    assert status["message"] == TOPIC_BOOK_STATUS
    assert status["writing_available"] is False
    assert status["evidence"] == EVIDENCE_RULE

    document = tomllib.loads((tmp_path / "programacion-en-c" / "project.toml").read_text(encoding="utf-8"))
    assert document["course"]["kind"] == "topic"
    assert "university" not in document["course"]
    assert "degree" not in document["course"]
    task = json.loads((tmp_path / "programacion-en-c" / "tasks" / "tasks.jsonl").read_text(encoding="utf-8"))
    assert task["type"] == "topic_book"
    assert task["status"] == "not_available"
    assert task["blocked_reason"] == "Writing is not available yet."


def test_rust_and_typescript_are_not_general(tmp_path):
    session = open_workspace(str(tmp_path))
    for slug, topic in (("rust", "Rust"), ("typescript", "TypeScript")):
        created = dispatch("studium_project_create", {"slug": slug, "topic": topic, "profile": "GENERAL"}, session=session)
        assert created["project"]["course"]["domain_profile"] == "COMPUTER_SCIENCE"
        assert created["message"] == TOPIC_BOOK_STATUS


def test_math_and_engineering_topics_use_stem(tmp_path):
    session = open_workspace(str(tmp_path))
    math_book = dispatch("studium_project_create", {"slug": "calculo", "topic": "Cálculo"}, session=session)
    fluids = dispatch(
        "studium_project_create",
        {"slug": "fluidos-tema", "topic": "Mecánica de Fluidos"},
        session=session,
    )
    assert math_book["project"]["course"]["domain_profile"] == "STEM"
    assert fluids["project"]["course"]["domain_profile"] == "STEM"
    assert math_book["project"]["evidence"] == EVIDENCE_RULE


def test_unclassified_topic_can_stay_general(tmp_path):
    session = open_workspace(str(tmp_path))
    created = dispatch(
        "studium_project_create",
        {"slug": "historia", "topic": "Historia medieval"},
        session=session,
    )
    assert created["status"] == "created"
    assert created["project"]["course"]["domain_profile"] == "GENERAL"
    assert created["message"] == TOPIC_BOOK_STATUS


def test_topic_book_rejects_university_and_course_guide(tmp_path):
    session = open_workspace(str(tmp_path))
    rejected = dispatch(
        "studium_project_create",
        {"slug": "rust", "topic": "Rust", "university": "Universidad de León"},
        session=session,
    )
    assert rejected["status"] == "mcp.invalid_input"
    assert "university" in rejected["message"]
    assert not (tmp_path / "rust").exists()

    created = dispatch("studium_project_create", {"slug": "rust", "topic": "Rust"}, session=session)
    assert created["status"] == "created"
    recorded = dispatch(
        "studium_course_document_record",
        {"title": "Guía", "url": "https://example.edu/guia", "text": "temario"},
        session=session,
    )
    assert recorded["status"] == "topic_book.no_course_guide"
    attempted = dispatch("studium_course_recorded", {}, session=session)
    assert attempted["status"] == "topic_book.no_course_guide"
    state = json.loads((tmp_path / "rust" / ".studium" / "state.json").read_text(encoding="utf-8"))
    assert state["state"] == "COURSE_DISCOVERY"
    assert state["local_sources"]["status"] == "UNKNOWN"


def test_topic_book_keeps_local_source_decisions(tmp_path):
    session = open_workspace(str(tmp_path))
    assert dispatch("studium_project_create", {"slug": "rust", "topic": "Rust"}, session=session)["status"] == "created"
    before = dispatch("studium_project_status", {}, session=session)
    assert "next_action" not in before
    question = before["guidance"]["question"]
    assert isinstance(question, str)
    assert "course guide" not in question.casefold()
    assert "guía" not in question.casefold()
    registered = dispatch("studium_source_register", {"decision": "none"}, session=session)
    assert registered["local_sources"]["status"] == "NONE"
    status = dispatch("studium_project_status", {}, session=session)
    assert status["message"] == TOPIC_BOOK_STATUS
    assert status["local_sources"]["status"] == "NONE"
    assert status["course_guide_required"] is False
    assert status["guidance"]["question"] is None


def test_topic_book_decision_none_next_action_is_stop(tmp_path):
    session = open_workspace(str(tmp_path))
    created = dispatch("studium_project_create", {"slug": "rust", "topic": "Rust"}, session=session)
    assert created["status"] == "created"
    assert "next_action" not in created["project"]
    registered = dispatch("studium_source_register", {"decision": "none"}, session=session)
    assert registered["next_action"] == TOPIC_BOOK_NEXT_ACTION
    status = dispatch("studium_project_status", {}, session=session)
    assert status["local_sources"]["status"] == "NONE"
    assert status["next_action"] == TOPIC_BOOK_NEXT_ACTION
    assert status["writing_available"] is False
    assert status["message"] == TOPIC_BOOK_STATUS


def test_topic_book_skipped_and_available_also_stop(tmp_path):
    for decision, label in (("skipped", "SKIPPED"), ("available", "AVAILABLE")):
        workspace = tmp_path / decision
        workspace.mkdir()
        session = open_workspace(str(workspace))
        assert dispatch("studium_project_create", {"slug": "rust", "topic": "Rust"}, session=session)["status"] == "created"
        dispatch("studium_source_register", {"decision": decision}, session=session)
        status = dispatch("studium_project_status", {}, session=session)
        assert status["local_sources"]["status"] == label
        assert status["next_action"] == TOPIC_BOOK_NEXT_ACTION


def test_course_book_decision_none_does_not_stop(tmp_path):
    session = open_workspace(str(tmp_path))
    assert dispatch("studium_project_create", {"slug": "fluidos", **_COURSE}, session=session)["status"] == "created"
    registered = dispatch("studium_source_register", {"decision": "none"}, session=session)
    assert "next_action" not in registered
    status = dispatch("studium_project_status", {}, session=session)
    assert status["local_sources"]["status"] == "NONE"
    assert "next_action" not in status
    assert "message" not in status


def test_course_book_still_requires_university_and_degree(tmp_path):
    session = open_workspace(str(tmp_path))
    missing = dispatch(
        "studium_project_create",
        {"slug": "fluidos", "course": "Mecánica de Fluidos", "degree": "Grado"},
        session=session,
    )
    assert missing["status"] == "mcp.invalid_input"
    assert missing["message"] == "university is required"
    assert not (tmp_path / "fluidos").exists()

    created = dispatch("studium_project_create", {"slug": "fluidos", **_COURSE}, session=session)
    assert created["status"] == "created"
    assert "message" not in created
    assert created["project"]["book_kind"] == "course"
    assert created["project"]["evidence"] == EVIDENCE_RULE
    assert "writing_available" not in created["project"]
    assert created["project"]["course"]["university"] == _COURSE["university"]
    assert created["project"]["course"]["degree"] == _COURSE["degree"]
    assert created["project"]["course"]["domain_profile"] == "GENERAL"
    task = json.loads((tmp_path / "fluidos" / "tasks" / "tasks.jsonl").read_text(encoding="utf-8"))
    assert task["type"] == "course_discovery"
    assert task["status"] == "open"


def test_course_book_named_like_a_programming_topic_stays_general(tmp_path):
    session = open_workspace(str(tmp_path))
    created = dispatch(
        "studium_project_create",
        {
            "slug": "programacion",
            "course": "Programación en C",
            "university": "Universidad de León",
            "degree": "Grado en Ingeniería Informática",
        },
        session=session,
    )
    assert created["project"]["course"]["domain_profile"] == "GENERAL"
    assert created["project"]["book_kind"] == "course"


def test_cli_topic_book_prints_the_status_text(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    rc = main(["create", "typescript", "--topic", "TypeScript"])
    captured = capsys.readouterr()
    assert rc == 0
    assert captured.out == f"{TOPIC_BOOK_STATUS}\n"
    assert captured.err == ""
    document = tomllib.loads((tmp_path / "typescript" / "project.toml").read_text(encoding="utf-8"))
    assert document["course"]["domain_profile"] == "COMPUTER_SCIENCE"
    assert "university" not in document["course"]

    rc = main(["status", "--project", str(tmp_path / "typescript")])
    text = capsys.readouterr().out
    assert rc == 0
    assert TOPIC_BOOK_STATUS in text
    assert "course.domain_profile: COMPUTER_SCIENCE" in text
    assert "course.university:" not in text

    rc = main(["next", "--project", str(tmp_path / "typescript")])
    nxt = capsys.readouterr().out
    assert rc == 0
    assert "task: none" in nxt
    assert "course_discovery" not in nxt


def test_cli_course_book_output_is_unchanged(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    rc = main(["create", "fluidos", *_CLI_COURSE])
    captured = capsys.readouterr()
    assert rc == 0
    assert captured.out == (
        "Studium project created.\n"
        "Next: COURSE_DISCOVERY\n"
        "Run: studium agent-pack\n"
    )
    status = project_status(tmp_path / "fluidos")
    topic = dispatch(
        "studium_project_create",
        {"slug": "rust", "topic": "Rust"},
        session=open_workspace(str(tmp_path)),
    )
    assert status["evidence"] == topic["project"]["evidence"]


def test_cli_topic_book_rejects_a_degree(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    rc = main(["create", "rust", "--topic", "Rust", "--degree", "Grado"])
    captured = capsys.readouterr()
    assert rc == 3
    assert captured.out == ""
    assert "degree" in captured.err
    assert not (tmp_path / "rust").exists()
