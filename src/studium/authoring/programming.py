"""Non-physical exercise contracts and read-only programming quality checks."""

from dataclasses import dataclass
from typing import Literal

from studium.authoring.literals import code_regions

ExerciseKind = Literal["conceptual", "implementation", "debugging", "architecture", "project", "mathematical"]


@dataclass(frozen=True)
class ExerciseContract:
    kind: ExerciseKind
    prompt: str
    solution: str = ""
    tests: tuple[str, ...] = ()
    rubric: tuple[str, ...] = ()

    def gaps(self) -> list[str]:
        if self.kind not in {"conceptual", "implementation", "debugging", "architecture", "project", "mathematical"}:
            raise ValueError("unsupported exercise kind")
        missing = []
        if not self.prompt.strip():
            missing.append("prompt")
        if not self.solution.strip():
            missing.append("solution")
        if self.kind in {"implementation", "debugging", "project"} and not any(t.strip() for t in self.tests):
            missing.append("tests")
        if self.kind in {"conceptual", "architecture"} and not any(r.strip() for r in self.rubric):
            missing.append("rubric")
        if self.kind == "mathematical":
            missing.append("use_existing_mathematical_contract")
        return missing


def listing_findings(text: str) -> list[dict[str, object]]:
    findings = []
    for index, region in enumerate(code_regions(text), 1):
        if not region.block:
            continue
        if not region.closed:
            findings.append({"type": "unclosed_code_fence", "severity": "ERROR", "listing": index})
        non_ascii = sorted({f"U+{ord(c):04X}" for c in region.body if ord(c) > 127})
        if non_ascii:
            findings.append({"type": "unicode_listing_requires_pdf_review", "severity": "REVIEW_REQUIRED",
                             "listing": index, "codepoints": non_ascii})
        if not region.language:
            findings.append({"type": "code_language_missing", "severity": "WARNING", "listing": index})
    return findings
