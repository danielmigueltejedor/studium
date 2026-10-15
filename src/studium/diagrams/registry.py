"""Registry of structured-data families and the diagram generators built on them.

A *family* is a kind of structured problem data (a beam, a cross-section, a
stress state). It knows how to validate the data, solve it and check it.
A *generator* draws one kind of figure from one family's data and returns the
TikZ body with the evidence for that drawing.

Extensions register here when imported. :func:`load_extensions` imports the
extensions that ship with Studium, so the generic code never names a subject.
"""

import importlib
from collections.abc import Callable
from dataclasses import dataclass, field

from studium.diagrams.evidence import Evidence
from studium.diagrams.piecewise import DataError

_EXTENSIONS = ("studium.engineering.structures.register",)


@dataclass(frozen=True)
class Options:
    """Presentation choices common to every generator."""

    language: str = "es"
    decimals: int = 2

    @property
    def comma(self) -> bool:
        return self.language.split("-")[0] in {"es", "fr", "de", "it", "pt", "ca", "gl", "eu", "nl"}


@dataclass
class Generated:
    tikz: str
    data: dict[str, object]
    evidence: Evidence
    #: Short derived text an author may cite (values, laws). Never a substitute for the checks.
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Family:
    name: str
    description: str
    #: Validate and solve; return (solution data, evidence). Raises DataError on bad data.
    check: Callable[[dict[str, object], object], tuple[dict[str, object], Evidence]]
    #: Optional: display-math lines with the solution's laws, for the worked solution.
    laws: Callable[[dict[str, object], Options], list[str]] | None = None


@dataclass(frozen=True)
class Generator:
    name: str
    family: str
    description: str
    stages: tuple[str, ...]
    build: Callable[[dict[str, object], dict[str, object], Options, object], Generated]
    version: str = "1"


_FAMILIES: dict[str, Family] = {}
_CONVENTIONS: dict[str, dict[str, str]] = {}
_GENERATORS: dict[str, Generator] = {}
_LOADED = False

#: Where a figure belongs inside a worked problem, in reading order.
STAGES = (
    "statement",
    "model",
    "free_body",
    "equilibrium",
    "solution",
    "graphical",
    "verification",
    "interpretation",
)


def register_family(family: Family) -> None:
    _FAMILIES[family.name] = family


def register_generator(generator: Generator) -> None:
    if generator.family not in _FAMILIES:
        raise ValueError(f"generator {generator.name} names an unknown family {generator.family}")
    _GENERATORS[generator.name] = generator


def register_conventions(presets: dict[str, dict[str, str]]) -> None:
    """Named sign-convention presets an extension offers (shown to authors, never assumed)."""

    _CONVENTIONS.update(presets)


def load_extensions() -> None:
    global _LOADED
    if _LOADED:
        return
    for module in _EXTENSIONS:
        importlib.import_module(module)
    _LOADED = True


def family(name: str) -> Family | None:
    load_extensions()
    return _FAMILIES.get(name)


def generator(name: str) -> Generator | None:
    load_extensions()
    return _GENERATORS.get(name)


def catalogue() -> dict[str, object]:
    load_extensions()
    return {
        "families": {name: item.description for name, item in sorted(_FAMILIES.items())},
        "generators": {
            name: {"family": item.family, "description": item.description, "stages": list(item.stages)}
            for name, item in sorted(_GENERATORS.items())
        },
        "stages": list(STAGES),
        "conventions": dict(_CONVENTIONS),
    }


def family_laws(family_name: object, spec: object, options: Options) -> list[str]:
    """Typeset laws of a solved structure, or nothing when the family has none or the data fail."""

    found = family(family_name) if isinstance(family_name, str) else None
    if found is None or found.laws is None or not isinstance(spec, dict):
        return []
    try:
        return found.laws(spec, options)
    except (DataError, ArithmeticError, LookupError, TypeError, ValueError):
        # Typesetting must never stop a render; the laws are an aid, the checks live elsewhere.
        return []


def verification_block(evidence: Evidence, summary: dict[str, object] | None = None) -> dict[str, object]:
    return {**(summary or evidence.summary()), "checks": [check.as_dict() for check in evidence.checks]}


def solve_structure(family_name: object, spec: object, claims: object = None) -> dict[str, object]:
    """Solve and check structured data of one family. Nothing is drawn or stored."""

    found = family(family_name) if isinstance(family_name, str) else None
    if found is None:
        return {"status": "diagram.family_unknown", "message": f"no family called {family_name!r}", "stored": False}
    if not isinstance(spec, dict) or not spec:
        return {"status": "mcp.invalid_input", "message": "spec must be an object with the structured data", "stored": False}
    try:
        data, evidence = found.check(spec, claims)
    except DataError as exc:
        return {"status": "diagram.data_invalid", "message": str(exc), "stored": False}
    except (ValueError, ZeroDivisionError, TypeError) as exc:
        return {"status": "diagram.data_invalid", "message": f"the data cannot be solved: {exc}", "stored": False}
    return {"status": "solved", "stored": False, "data": data, "verification": verification_block(evidence)}
