"""Ask-once copy for local sources. This is not an autopilot pack."""

from studium.domain.languages import is_spanish_tag

QUESTION_EN = (
    "Do you have your own course materials? You can provide lecture notes, "
    "Moodle PDFs, slides, problem sheets, previous exams, formula sheets, "
    "lab material, recommended bibliography or your own notes. They are "
    "optional. If you do not have any, just say so."
)

QUESTION_ES = (
    "¿Tienes materiales propios de la asignatura? Puedes aportar apuntes, "
    "PDFs de Moodle, diapositivas, hojas de problemas, exámenes anteriores, "
    "formularios, material de laboratorio, bibliografía recomendada o tus "
    "propias notas. Son opcionales. Si no tienes, basta con decirlo."
)


def local_source_guidance(
    local: dict[str, object],
    sources: list[dict[str, object]],
    language: str | None,
) -> dict[str, object]:
    should_ask = local.get("status") == "UNKNOWN" and local.get("prompted") is not True
    question: str | None = None
    if should_ask:
        question = QUESTION_ES if is_spanish_tag(language) else QUESTION_EN
    visible: list[dict[str, object]] = []
    if local.get("status") == "IMPORTED":
        for source in sources:
            raw_roles = source.get("roles")
            roles = raw_roles if isinstance(raw_roles, list) else []
            visible.append(
                {
                    "id": source.get("id"),
                    "roles": list(roles),
                    "classification": source.get("classification"),
                }
            )
    return {
        "should_ask": should_ask,
        "do_not_ask": not should_ask,
        "question": question,
        "sources": visible,
    }
