"""Discipline-aware agent planning and resumable, evidence-neutral coordination.

This module does not invoke an LLM or certify academic work. MCP clients execute
the tasks and use Studium's existing evidence, verification and publishing tools.
"""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path
from typing import TypedDict

from studium.storage.init_project import load_project_toml
from studium.storage.locking import ProjectLocked, project_lock
from studium.storage.migrate import utc_now
from studium.storage.records import atomic_write_text

_WORKFLOW = ".studium/agent-workflow.json"

# Domain-specific tasks are *not* interchangeable: e.g. history requires
# primary-source interpretation, not a numerical worked problem.
class DisciplineSpec(TypedDict):
    terms: tuple[str, ...]
    specialist: str
    activity: str
    checker: str


_DISCIPLINES: dict[str, DisciplineSpec] = {
    "history": {
        "terms": ("historia", "history", "historiografia", "medieval", "antigua", "modern history"),
        "specialist": "historiador del periodo",
        "activity": "comentario comparado de fuentes y análisis causal",
        "checker": "crítica documental e historiográfica; contrastar fuentes primarias",
    },
    "biology": {
        "terms": ("biologia", "biology", "genetica", "ecologia", "botanica", "bioquimica"),
        "specialist": "biólogo del campo de estudio",
        "activity": "interpretación de experimentos, procesos y estudios de caso",
        "checker": "contraste con evidencia experimental y métodos del estudio",
    },
    "politics": {
        "terms": ("politica", "politics", "political", "gobierno", "democracia", "politologia"),
        "specialist": "politólogo de la especialidad",
        "activity": "análisis de instituciones y comparación de políticas públicas",
        "checker": "contraste de datos, perspectivas y calidad metodológica",
    },
    "mathematics": {
        "terms": ("matematic", "mathemat", "algebra", "calculo", "calculus", "geometria"),
        "specialist": "matemático de la especialidad",
        "activity": "ejercicios graduados y demostraciones justificadas",
        "checker": "demostración independiente, contraejemplos y verificación simbólica",
    },
    "engineering": {
        "terms": ("ingenier", "engineering", "fisica", "physics", "fluid", "fluidos", "termodinamica"),
        "specialist": "ingeniero o físico de la especialidad",
        "activity": "problemas de modelado con hipótesis y unidades explícitas",
        "checker": "reproducción independiente, dimensiones, conservación y validación física",
    },
    "programming": {
        "terms": ("programac", "programming", "software", "informatica", "rust", "python", "algoritm"),
        "specialist": "ingeniero de software del área",
        "activity": "ejercicios de código, depuración y proyectos graduales",
        "checker": "revisión de código, pruebas reproducibles y seguridad",
    },
    "languages": {
        "terms": ("idioma", "language", "ingles", "english", "frances", "linguistic", "linguistica"),
        "specialist": "lingüista y docente de la lengua",
        "activity": "comprensión, conversación, escritura y corrección guiada",
        "checker": "rúbricas de competencia y retroalimentación lingüística",
    },
    "humanities": {
        "terms": ("filosofia", "philosophy", "literatura", "literature", "arte", "art history"),
        "specialist": "especialista de humanidades",
        "activity": "lectura crítica, análisis textual y argumentación",
        "checker": "crítica de fuentes e interpretaciones justificadas",
    },
    "general": {
        "terms": (),
        "specialist": "especialista en el tema específico",
        "activity": "actividades ajustadas a las competencias, sin exigir problemas numéricos",
        "checker": "contrastar las afirmaciones con fuentes y métodos pertinentes",
    },
}

_PROFILE_DEFAULT = {
    "STEM": "engineering",
    "LIFE_SCIENCES": "biology",
    "SOCIAL_SCIENCES": "politics",
    "HUMANITIES": "humanities",
    "LAW": "humanities",
    "COMPUTER_SCIENCE": "programming",
    "GENERAL": "general",
}
_OBJECTIVES = frozenset({"book", "chapter", "activity", "edition", "review"})


def _normal(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    return "".join(char for char in value if not unicodedata.combining(char))


def _discipline(root: Path, requested: object) -> tuple[str, str] | None:
    document = load_project_toml(root)
    course = document.get("course")
    course = course if isinstance(course, dict) else {}
    label = str(course.get("name") or "")
    if requested is not None and (not isinstance(requested, str) or not requested.strip() or len(requested) > 120):
        return None
    text = requested.strip() if isinstance(requested, str) else label
    normalized = _normal(text)
    for key, spec in _DISCIPLINES.items():
        if key != "general" and any(term in normalized for term in spec["terms"]):
            return key, text
    if requested is not None:
        return "general", text
    profile = str(course.get("domain_profile") or "GENERAL")
    return _PROFILE_DEFAULT.get(profile, "general"), text


def _depend(task: dict[str, object], dependency: str) -> None:
    """Add one DAG prerequisite to an existing planned task."""
    links = task.get("depends_on")
    if isinstance(links, list):
        links.append(dependency)


def agent_plan(
    root: Path, *, objective: object = "book", discipline: object = None, level: object = None
) -> dict[str, object]:
    """Return a plan, not a claim that agents have been executed."""
    if not isinstance(objective, str) or objective not in _OBJECTIVES:
        return {"status": "mcp.invalid_input", "message": "unsupported objective"}
    if level is not None and (not isinstance(level, str) or len(level) > 100 or not level.strip()):
        return {"status": "mcp.invalid_input", "message": "level must be non-empty text"}
    chosen = _discipline(root, discipline)
    if chosen is None:
        return {"status": "mcp.invalid_input", "message": "discipline must be non-empty text (max 120)"}
    key, topic = chosen
    spec = _DISCIPLINES[key]
    tasks: list[dict[str, object]] = [
        {"id": "research", "role": "investigador de fuentes", "depends_on": [],
         "deliverable": "fuentes abiertas y fragmentos verificables con procedencia"},
        {"id": "domain", "role": str(spec["specialist"]), "depends_on": ["research"],
         "deliverable": "alcance, conceptos y supuestos específicos del tema"},
        {"id": "theory", "role": "autor de teoría", "depends_on": ["domain"],
         "deliverable": "explicación progresiva basada en evidencia y objetivos"},
        {"id": "activities", "role": "diseñador de actividades", "depends_on": ["domain"],
         "deliverable": str(spec["activity"])},
        {"id": "independent_review", "role": "revisor independiente de la disciplina",
         "depends_on": ["theory", "activities"], "deliverable": str(spec["checker"])},
        {"id": "source_audit", "role": "contrastador de fuentes", "depends_on": ["theory"],
         "deliverable": "trazabilidad por afirmación, discrepancias y datos insuficientes"},
        {"id": "pedagogy", "role": "experto en didáctica", "depends_on": ["activities", "independent_review"],
         "deliverable": "progresión, claridad, objetivos y evaluación apropiada"},
        {"id": "final_review", "role": "editor y auditor final",
         "depends_on": ["independent_review", "source_audit", "pedagogy"],
         "deliverable": "informe de bloqueos y pasos pendientes en los quality gates de Studium"},
    ]
    # Optional specialist stages are selected by scope and discipline rather
    # than launching every available Claude agent for every request. The stable
    # base tasks above remain backward compatible with existing MCP clients.
    by_id = {str(item["id"]): item for item in tasks}
    extra: list[dict[str, object]] = []
    if objective in {"book", "edition"}:
        curriculum: dict[str, object] = {
            "id": "curriculum",
            "role": "arquitecto curricular",
            "recommended_agent": "curriculum-architect",
            "depends_on": ["domain"],
            "deliverable": "objetivos, prerrequisitos y progresión por capítulos",
        }
        extra.append(curriculum)
        for task_id in ("theory", "activities"):
            _depend(by_id[task_id], "curriculum")
        if objective == "edition":
            extra.append({
                "id": "edition_analysis",
                "role": "analista de evolución de ediciones",
                "recommended_agent": "edition-evolution-analyst",
                "depends_on": ["domain"],
                "deliverable": "cambios concretos que mejoran la edición sin sobrescribir la anterior",
            })
            _depend(curriculum, "edition_analysis")
    if objective in {"book", "chapter", "edition"}:
        extra.append({
            "id": "concept_map",
            "role": "revisor de conceptos y prerrequisitos",
            "recommended_agent": "concept-map-auditor",
            "depends_on": ["theory"],
            "deliverable": "mapa de conceptos, saltos y confusiones entre contenidos",
        })
        _depend(by_id["final_review"], "concept_map")
        if key in {"history", "biology", "mathematics", "engineering", "politics", "humanities"}:
            extra.append({
                "id": "figure_audit",
                "role": "revisor de figuras y visualizaciones",
                "recommended_agent": "figure-visualization-auditor",
                "depends_on": ["theory"],
                "deliverable": "revisar figuras necesarias, procedencia, legibilidad y datos",
            })
            _depend(by_id["final_review"], "figure_audit")
    if objective in {"book", "chapter", "edition", "activity"}:
        extra.append({
            "id": "assessment_review",
            "role": "arquitecto de evaluaciones",
            "recommended_agent": "assessment-architect",
            "depends_on": ["activities"],
            "deliverable": "alineación de objetivos, actividades y rúbricas",
        })
        _depend(by_id["pedagogy"], "assessment_review")
        if key in {"mathematics", "engineering", "programming"}:
            extra.append({
                "id": "independent_solution",
                "role": "resolutor independiente",
                "recommended_agent": "independent-solver",
                "depends_on": ["activities"],
                "deliverable": "solución independiente y discrepancias antes de leer la respuesta original",
            })
            _depend(by_id["independent_review"], "independent_solution")
    if objective in {"book", "edition"}:
        extra.append({
            "id": "cross_chapter_review",
            "role": "auditor de coherencia global",
            "recommended_agent": "cross-chapter-consistency",
            "depends_on": ["source_audit", "pedagogy", "concept_map"],
            "deliverable": "inconsistencias, duplicidades y contradicciones entre capítulos",
        })
        _depend(by_id["final_review"], "cross_chapter_review")
    if objective in {"book", "chapter", "edition"}:
        extra.append({
            "id": "accessibility_review",
            "role": "revisor de accesibilidad y localización",
            "recommended_agent": "accessibility-localization",
            "depends_on": ["pedagogy"],
            "deliverable": "estructura, textos alternativos, terminología e idioma accesibles",
        })
        _depend(by_id["final_review"], "accessibility_review")
    tasks = [*tasks[:-1], *extra, tasks[-1]]
    return {
        "status": "ok",
        "objective": objective,
        "discipline": key,
        "topic": topic,
        "level": level or "adaptar al proyecto y al estudiante",
        "activity": spec["activity"],
        "verification": spec["checker"],
        "tasks": tasks,
        "execution": "external_client_required",
        "academic_review": "not_established",
        "instructions": (
            "Los agentes redactan y contrastan; solo las herramientas deterministas y las revisiones "
            "humanas documentadas asignan estados de verificación. No inventar citas ni aprobar la propia salida."
        ),
    }


def workflow_start(root: Path, *, objective: object = "book", discipline: object = None,
                   level: object = None) -> dict[str, object]:
    plan = agent_plan(root, objective=objective, discipline=discipline, level=level)
    if plan["status"] != "ok":
        return plan
    target = root / _WORKFLOW
    try:
        with project_lock(root):
            if target.exists():
                return {"status": "workflow.exists", "message": "A workflow already exists. Resume it first."}
            document = {**plan, "created_at": utc_now(),
                        "tasks": [{**t, "status": "pending", "artifacts": []} for t in plan["tasks"]]}
            # Carry the original improvement request across MCP sessions. The
            # edition copy contains its own local metadata, not a shared queue.
            if objective == "edition":
                metadata_path = root / ".studium" / "edition.json"
                if metadata_path.is_file():
                    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                    document["edition_request"] = str(metadata.get("request") or "")
                    document["source_project"] = metadata.get("source_project")
                    document["target_version"] = metadata.get("version")
            atomic_write_text(target, json.dumps(document, ensure_ascii=False, indent=2) + "\n")
    except ProjectLocked:
        return {"status": "storage.locked", "message": "project is locked"}
    return {"status": "created", "workflow": document, "next_tool": "studium_agent_workflow_next"}


def workflow_next(root: Path) -> dict[str, object]:
    target = root / _WORKFLOW
    if not target.is_file():
        return {"status": "workflow.not_found", "message": "Start a workflow first."}
    data = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("tasks"), list):
        return {"status": "workflow.invalid", "message": "Malformed workflow record."}
    tasks = data["tasks"]
    completed = {str(t.get("id")) for t in tasks if isinstance(t, dict) and t.get("status") == "submitted"}
    ready = [t for t in tasks if isinstance(t, dict) and t.get("status") == "pending"
             and all(dep in completed for dep in t.get("depends_on", []))]
    pending = [t for t in tasks if isinstance(t, dict) and t.get("status") == "pending"]
    return {"status": "ok", "objective": data.get("objective"), "discipline": data.get("discipline"),
            "edition_request": data.get("edition_request"),
            "source_project": data.get("source_project"), "target_version": data.get("target_version"),
            "ready": ready, "pending_count": len(pending), "all_submitted": not pending,
            "academic_review": "not_established",
            "note": "Submitted tasks are reports, not verified facts. Apply existing Studium audits before rendering."}


def workflow_submit(root: Path, *, task_id: object, artifacts: object) -> dict[str, object]:
    if not isinstance(task_id, str) or not task_id:
        return {"status": "mcp.invalid_input", "message": "task_id required"}
    if (not isinstance(artifacts, list) or not artifacts or len(artifacts) > 50
            or not all(isinstance(a, str) and a.strip() and len(a) <= 250 for a in artifacts)):
        return {"status": "mcp.invalid_input", "message": "artifact IDs required (non-empty list)"}
    target = root / _WORKFLOW
    try:
        with project_lock(root):
            if not target.is_file():
                return {"status": "workflow.not_found", "message": "Start a workflow first."}
            data = json.loads(target.read_text(encoding="utf-8"))
            tasks = data.get("tasks", [])
            found = next((t for t in tasks if isinstance(t, dict) and t.get("id") == task_id), None)
            if found is None or found.get("status") != "pending":
                return {"status": "workflow.invalid_task", "message": "Task unavailable or already submitted."}
            completed = {str(t.get("id")) for t in tasks if t.get("status") == "submitted"}
            if not all(dep in completed for dep in found.get("depends_on", [])):
                return {"status": "workflow.blocked", "message": "Prerequisite tasks are not submitted."}
            found["status"] = "submitted"
            found["artifacts"] = list(artifacts)
            found["submitted_at"] = utc_now()
            atomic_write_text(target, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    except ProjectLocked:
        return {"status": "storage.locked", "message": "project is locked"}
    return {"status": "recorded", "task": task_id, "verification": "not_established",
            "next_tool": "studium_agent_workflow_next"}
