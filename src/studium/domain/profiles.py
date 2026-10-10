"""Create-time domain profiles. Topic books reuse this enum."""

import re
import unicodedata
from typing import NamedTuple

BOOK_COURSE = "course"
BOOK_TOPIC = "topic"
BOOK_KINDS = frozenset({BOOK_COURSE, BOOK_TOPIC})

PROFILES: tuple[str, ...] = (
    "GENERAL",
    "STEM",
    "HUMANITIES",
    "SOCIAL_SCIENCES",
    "COMPUTER_SCIENCE",
    "LAW",
)
PROFILE_CHOICES: tuple[str, ...] = tuple(profile for profile in PROFILES if profile != "GENERAL")

class DepthThresholds(NamedTuple):
    min_sections: int
    min_sources: int
    min_explanation_words: int
    min_explanation_sections: int


_DEPTH: dict[str, DepthThresholds] = {
    "STEM": DepthThresholds(min_sections=8, min_sources=12, min_explanation_words=400, min_explanation_sections=2),
    "COMPUTER_SCIENCE": DepthThresholds(min_sections=8, min_sources=12, min_explanation_words=400, min_explanation_sections=2),
    "HUMANITIES": DepthThresholds(min_sections=6, min_sources=10, min_explanation_words=500, min_explanation_sections=2),
    "SOCIAL_SCIENCES": DepthThresholds(min_sections=6, min_sources=10, min_explanation_words=400, min_explanation_sections=2),
    "LAW": DepthThresholds(min_sections=6, min_sources=10, min_explanation_words=500, min_explanation_sections=2),
    "GENERAL": DepthThresholds(min_sections=8, min_sources=12, min_explanation_words=400, min_explanation_sections=2),
}


def depth_thresholds(profile: str) -> DepthThresholds:
    return _DEPTH.get(profile, _DEPTH["GENERAL"])


TOPIC_BOOK_STATUS = "Topic book exists. Writing is not available yet."
TOPIC_BOOK_LOCAL_DECISIONS = frozenset({"NONE", "SKIPPED", "AVAILABLE"})
COURSE_PUBLIC_SOURCE_NEXT_ACTION = (
    "Record public sources with studium_public_source_record. "
    "You may browse the web. "
    "Record only a source whose URL you actually opened."
)
TOPIC_BOOK_NEXT_ACTION = (
    "Record public sources with studium_public_source_record. "
    "You may browse the web. "
    "Record only a source whose URL you actually opened. "
    "Do not look for a university course guide. "
    "Do not call studium_course_recorded. "
    "Writing is not available."
)
WRITING_STILL_UNAVAILABLE = "Writing is still not available."
EVIDENCE_RULE = (
    "The model is not a source. Claims need corroborated public sources. Verification is not skipped."
)
TOPIC_NO_COURSE_GUIDE = "A topic book does not ask for an official university course guide."

_COMPUTER_SCIENCE = (
    "computer science",
    "ciencias de la computacion",
    "ciencia de la computacion",
    "lenguajes de programacion",
    "programming languages",
    "programacion en c",
    "lenguaje c",
    "language c",
    "ansi c",
    "c programming",
    "c language",
    "programacion",
    "programming",
    "informatica",
    "computacion",
    "algoritmos",
    "algorithms",
    "algorithm",
    "estructura de datos",
    "estructuras de datos",
    "data structures",
    "data structure",
    "software",
    "compiladores",
    "compiler",
    "sistemas operativos",
    "sistema operativo",
    "operating systems",
    "operating system",
    "machine learning",
    "aprendizaje automatico",
    "inteligencia artificial",
    "artificial intelligence",
    "bases de datos",
    "base de datos",
    "databases",
    "database",
    "ciberseguridad",
    "cybersecurity",
    "desarrollo web",
    "web development",
    "sistemas distribuidos",
    "distributed systems",
    "redes de computadores",
    "computer networks",
    "typescript",
    "javascript",
    "python",
    "kotlin",
    "swift",
    "haskell",
    "scala",
    "golang",
    "rust",
    "java",
    "ruby",
    "perl",
    "lua",
    "dart",
    "php",
    "sql",
    "csharp",
    "c++",
    "c#",
    "cpp",
)

_STEM = (
    "matematicas",
    "mathematics",
    "matematica",
    "calculo",
    "calculus",
    "algebra lineal",
    "linear algebra",
    "algebra",
    "geometria",
    "geometry",
    "estadistica",
    "statistics",
    "probabilidad",
    "probability",
    "ecuaciones diferenciales",
    "differential equations",
    "topologia",
    "topology",
    "trigonometria",
    "trigonometry",
    "analisis matematico",
    "mathematical analysis",
    "matematica discreta",
    "discrete mathematics",
    "ingenieria",
    "engineering",
    "mecanica de fluidos",
    "fluid mechanics",
    "fluidos",
    "termodinamica",
    "thermodynamics",
    "resistencia de materiales",
    "electronica",
    "electronics",
    "aerodinamica",
    "aerodynamics",
    "aeroespacial",
    "aerospace",
    "mecanica",
    "fisica",
    "physics",
    "mecanica cuantica",
    "quantum",
    "electromagnetismo",
    "electromagnetism",
)


def infer_topic_profile(topic: str) -> str | None:
    """Map a computing, math, or engineering subject onto the profile enum."""

    text = _fold(topic)
    if _matches_any(text, _COMPUTER_SCIENCE):
        return "COMPUTER_SCIENCE"
    if _matches_any(text, _STEM):
        return "STEM"
    return None


def resolve_topic_profile(topic: str, requested: str | None) -> str:
    """A detected computing, math, or engineering topic is never stored as GENERAL."""

    inferred = infer_topic_profile(topic)
    if inferred is not None:
        return inferred
    if requested is None or requested == "GENERAL":
        return "GENERAL"
    return requested


def _fold(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text.casefold())
    stripped = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", stripped).strip()


def _matches_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(_contains_phrase(text, phrase) for phrase in phrases)


def _contains_phrase(text: str, phrase: str) -> bool:
    parts = [re.escape(part) for part in phrase.split()]
    pattern = r"(?<![a-z0-9])" + r"\s+".join(parts) + r"(?![a-z0-9])"
    return re.search(pattern, text) is not None
