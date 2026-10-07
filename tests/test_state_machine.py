from studium.domain.enums import ProjectEvent, ProjectState
from studium.state.gates import PROJECT_TOML, GateResult, gate_for, project_toml_gate
from studium.state.machine import apply, required_gate

_COURSE = {"name": "Mecánica de Fluidos", "university": "Universidad de León", "degree": "Grado"}


def test_project_created_and_begin_discovery_reach_course_discovery():
    gate_name = required_gate(None, ProjectEvent.PROJECT_CREATED.value)
    assert gate_name == required_gate(ProjectState.CREATED, ProjectEvent.BEGIN_DISCOVERY.value)
    gates = {gate_name: gate_for(gate_name, _COURSE)}

    created = apply(None, ProjectEvent.PROJECT_CREATED.value, gates)
    assert created.applied is True
    assert created.state is ProjectState.CREATED
    assert created.entry is not None
    assert created.entry.from_state is None
    assert created.entry.to is ProjectState.CREATED
    assert created.entry.event == "project_created"

    discovered = apply(created.state, ProjectEvent.BEGIN_DISCOVERY.value, gates)
    assert discovered.applied is True
    assert discovered.state is ProjectState.COURSE_DISCOVERY
    assert discovered.entry is not None
    assert discovered.entry.from_state is ProjectState.CREATED
    assert discovered.entry.to is ProjectState.COURSE_DISCOVERY
    assert discovered.entry.event == "begin_discovery"


def test_release_from_course_discovery_is_illegal_and_keeps_state():
    green = GateResult(name="release", ok=True, blockers=())
    result = apply(ProjectState.COURSE_DISCOVERY, "release", {"release": green})
    assert result.applied is False
    assert result.state is ProjectState.COURSE_DISCOVERY
    assert result.entry is None
    assert result.blockers[0].code == "state.illegal_transition"


def test_unimplemented_gate_blocks_course_recorded():
    gate_name = required_gate(ProjectState.COURSE_DISCOVERY, "course_recorded")
    assert gate_name is not None
    blocked = gate_for(gate_name)
    assert blocked.ok is False
    assert blocked.blockers[0].code == "state.gate_not_implemented"

    result = apply(ProjectState.COURSE_DISCOVERY, "course_recorded", {gate_name: blocked})
    assert result.applied is False
    assert result.state is ProjectState.COURSE_DISCOVERY
    assert result.blockers[0].code == "state.gate_not_implemented"

    missing = apply(ProjectState.COURSE_DISCOVERY, "course_recorded", {})
    assert missing.applied is False
    assert missing.state is ProjectState.COURSE_DISCOVERY
    assert missing.blockers[0].code == "state.gate_not_implemented"


def test_project_toml_gate_requires_three_non_empty_fields():
    blocked = project_toml_gate({"name": " ", "university": "U", "degree": "D"})
    assert blocked.ok is False
    assert blocked.name == PROJECT_TOML
    assert blocked.blockers[0].code == "state.project_fields_missing"

    opened = project_toml_gate(_COURSE)
    assert opened.ok is True
    assert opened.blockers == ()


def test_topic_book_gate_requires_a_name_and_not_a_university():
    opened = project_toml_gate({"kind": "topic", "name": "Rust"})
    assert opened.ok is True
    assert opened.blockers == ()

    blocked = project_toml_gate({"kind": "topic", "name": " "})
    assert blocked.ok is False
    assert blocked.blockers[0].code == "state.project_fields_missing"
    assert "course.name" in blocked.blockers[0].message
    assert "university" not in blocked.blockers[0].message


def test_regress_stops_at_the_latest_green_earlier_state():
    gates = {PROJECT_TOML: project_toml_gate(_COURSE)}
    result = apply(ProjectState.COURSE_DISCOVERY, "regress", gates)
    assert result.applied is True
    assert result.state is ProjectState.CREATED
    assert result.entry is not None
    assert result.entry.event == "regress"
    assert result.entry.from_state is ProjectState.COURSE_DISCOVERY


def test_regress_without_a_green_target_does_not_move():
    result = apply(ProjectState.COURSE_DISCOVERY, "regress", {})
    assert result.applied is False
    assert result.state is ProjectState.COURSE_DISCOVERY
    assert result.blockers[0].code == "state.regress_target"


def test_refresh_course_is_blocked_while_its_gate_is_unimplemented():
    result = apply(ProjectState.RELEASED, "refresh_course", {})
    assert result.applied is False
    assert result.state is ProjectState.RELEASED
    assert result.blockers[0].code == "state.gate_not_implemented"
