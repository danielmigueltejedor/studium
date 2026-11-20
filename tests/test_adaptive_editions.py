"""Regression tests for the first adaptive-agent and book-edition workflow."""

import json

from studium.mcp.server import dispatch, open_workspace, tool_names


def _topic(tmp_path, slug: str, topic: str):
    session = open_workspace(str(tmp_path))
    created = dispatch("studium_project_create", {"slug": slug, "topic": topic}, session=session)
    assert created["status"] == "created"
    return session, tmp_path / slug


def test_agents_select_different_disciplines_and_tasks(tmp_path):
    session, _ = _topic(tmp_path, "historia", "Historia medieval")
    history = dispatch("studium_agent_plan", {}, session=session)
    assert history["discipline"] == "history"
    assert "fuentes" in history["verification"]
    assert "numérico" not in history["activity"]
    biology = dispatch("studium_agent_plan", {"discipline": "biología molecular"}, session=session)
    assert biology["discipline"] == "biology"
    assert "experimentos" in biology["activity"]
    politics = dispatch("studium_agent_plan", {"discipline": "política comparada"}, session=session)
    assert politics["discipline"] == "politics"
    assert "instituciones" in politics["activity"]
    math = dispatch("studium_agent_plan", {"discipline": "matemáticas"}, session=session)
    assert math["discipline"] == "mathematics"
    assert "demostraciones" in math["activity"]
    unknown = dispatch("studium_agent_plan", {"discipline": "reparación de bicicletas"}, session=session)
    assert unknown["discipline"] == "general"
    assert "sin exigir problemas numéricos" in unknown["activity"]


def test_workflow_tracks_dependencies_without_pretending_to_verify(tmp_path):
    session, _ = _topic(tmp_path, "biologia", "Biología celular")
    started = dispatch("studium_agent_workflow_start", {}, session=session)
    assert started["status"] == "created"
    nxt = dispatch("studium_agent_workflow_next", {}, session=session)
    assert [task["id"] for task in nxt["ready"]] == ["research"]
    blocked = dispatch(
        "studium_agent_workflow_submit",
        {"task_id": "independent_review", "artifacts": ["AUD-1"]},
        session=session,
    )
    assert blocked["status"] == "workflow.blocked"
    no_artifact = dispatch(
        "studium_agent_workflow_submit",
        {"task_id": "research", "artifacts": []},
        session=session,
    )
    assert no_artifact["status"] == "mcp.invalid_input"
    submitted = dispatch(
        "studium_agent_workflow_submit",
        {"task_id": "research", "artifacts": ["SRC-1"]},
        session=session,
    )
    assert submitted["status"] == "recorded"
    assert submitted["verification"] == "not_established"
    nxt = dispatch("studium_agent_workflow_next", {}, session=session)
    assert [task["id"] for task in nxt["ready"]] == ["domain"]
    assert nxt["academic_review"] == "not_established"
    assert dispatch("studium_agent_workflow_start", {}, session=session)["status"] == "workflow.exists"


def test_new_edition_is_independent_and_invalidates_old_reviews(tmp_path):
    session, original = _topic(tmp_path, "historia", "Historia contemporánea")
    (original / "draft").mkdir()
    (original / "draft" / "paragraphs.jsonl").write_text('{"id":"P-1","text":"Example"}\n', encoding="utf-8")
    (original / "draft" / "audits.jsonl").write_text('{"id":"OLD"}\n', encoding="utf-8")
    (original / "draft" / "reviews.jsonl").write_text('{"id":"edition","audit_passed":true}\n', encoding="utf-8")
    (original / "latex").mkdir()
    (original / "latex" / "draft.pdf").write_bytes(b"%PDF-old")
    before = (original / "project.toml").read_bytes()

    new = dispatch(
        "studium_edition_create",
        {"request": "Mejora el rigor, añade fuentes y mejores ejercicios de análisis histórico."},
        session=session,
    )
    assert new["status"] == "created"
    assert new["version"] == "0.2.0"
    successor = tmp_path / "historia-edition-2"
    assert successor.is_dir()
    assert (successor / "draft" / "paragraphs.jsonl").exists()
    assert not (successor / "draft" / "audits.jsonl").exists()
    assert not (successor / "draft" / "reviews.jsonl").exists()
    assert not (successor / "latex" / "draft.pdf").exists()
    assert (original / "latex" / "draft.pdf").read_bytes() == b"%PDF-old"
    assert (original / "project.toml").read_bytes() == before
    assert session.active == successor
    metadata = json.loads((successor / ".studium" / "edition.json").read_text(encoding="utf-8"))
    assert metadata["source_project"] == "historia"
    assert metadata["publication"] == "draft"
    assert metadata["academic_review"] == "not_established"
    assert new["workflow"]["status"] == "created"
    workflow = dispatch("studium_agent_workflow_next", {}, session=session)
    assert workflow["discipline"] == "history"
    assert "fuentes" in workflow["edition_request"]
    assert workflow["source_project"] == "historia"
    assert workflow["target_version"] == "0.2.0"

    versions = dispatch("studium_edition_list", {}, session=session)
    assert [(v["index"], v["version"]) for v in versions["editions"]] == [(1, "0.1.0"), (2, "0.2.0")]


def test_repeated_edition_requests_create_separate_versions(tmp_path):
    session, _ = _topic(tmp_path, "math", "Matemáticas")
    edition_two = dispatch("studium_edition_create", {"request": "Revisar y ampliar"}, session=session)
    assert edition_two["status"] == "created"
    edition_three = dispatch("studium_edition_create", {"request": "Profundizar en demostraciones"}, session=session)
    assert edition_three["status"] == "created"
    assert edition_three["version"] == "0.3.0"
    assert edition_three["project"] == "math-edition-3"
    assert (tmp_path / "math-edition-2").exists()
    assert (tmp_path / "math").exists()


def test_invalid_inputs_and_symlinks_fail_closed(tmp_path):
    session, root = _topic(tmp_path, "politica", "Política internacional")
    invalid = dispatch("studium_edition_create", {"request": ""}, session=session)
    assert invalid["status"] == "mcp.invalid_input"
    backwards = dispatch("studium_edition_create", {"request": "Revisar", "version": "0.1.0"}, session=session)
    assert backwards["status"] == "edition.invalid_version"
    assert not (tmp_path / "politica-edition-2").exists()
    (root / "outside").symlink_to(tmp_path, target_is_directory=True)
    unsafe = dispatch("studium_edition_create", {"request": "Mejora la edición"}, session=session)
    assert unsafe["status"] == "edition.unsafe_source"
    assert not (tmp_path / "politica-edition-2").exists()


def test_new_tools_are_visible_to_mcp_clients():
    names = set(tool_names())
    assert {"studium_agent_plan", "studium_agent_workflow_start",
            "studium_agent_workflow_next", "studium_agent_workflow_submit",
            "studium_edition_create", "studium_edition_list"} <= names


def test_extended_agents_are_selected_by_goal_and_subject(tmp_path):
    session, _ = _topic(tmp_path, "historia-extendida", "Historia contemporánea")
    history = dispatch("studium_agent_plan", {"objective": "book"}, session=session)
    history_tasks = {item["id"]: item for item in history["tasks"]}
    assert {"curriculum", "concept_map", "assessment_review", "figure_audit",
            "cross_chapter_review", "accessibility_review"} <= set(history_tasks)
    assert "independent_solution" not in history_tasks
    assert "edition_analysis" not in history_tasks
    assert "curriculum" in history_tasks["theory"]["depends_on"]
    assert "cross_chapter_review" in history_tasks["final_review"]["depends_on"]

    edition = dispatch("studium_agent_plan", {"objective": "edition"}, session=session)
    edition_tasks = {item["id"]: item for item in edition["tasks"]}
    assert edition_tasks["edition_analysis"]["recommended_agent"] == "edition-evolution-analyst"
    assert "edition_analysis" in edition_tasks["curriculum"]["depends_on"]

    math = dispatch("studium_agent_plan", {"objective": "book", "discipline": "matemáticas"}, session=session)
    math_tasks = {item["id"]: item for item in math["tasks"]}
    assert "independent_solution" in math_tasks
    assert "independent_solution" in math_tasks["independent_review"]["depends_on"]

    quick = dispatch("studium_agent_plan", {"objective": "review", "discipline": "historia"}, session=session)
    quick_ids = {item["id"] for item in quick["tasks"]}
    assert not {"curriculum", "edition_analysis", "figure_audit", "cross_chapter_review",
                "assessment_review", "independent_solution"} & quick_ids


def test_extended_plan_has_no_broken_or_cyclic_dependencies(tmp_path):
    session, _ = _topic(tmp_path, "biologia-extendida", "Biología molecular")
    for objective in ("book", "chapter", "activity", "edition", "review"):
        plan = dispatch("studium_agent_plan", {"objective": objective}, session=session)
        all_ids = {task["id"] for task in plan["tasks"]}
        done = set()
        while len(done) < len(all_ids):
            ready = [task["id"] for task in plan["tasks"]
                     if task["id"] not in done and set(task["depends_on"]) <= done]
            assert ready, f"cycle or unknown dependency in {objective}"
            done.update(ready)
        assert done == all_ids
