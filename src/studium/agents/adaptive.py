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
    tasks = [
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
