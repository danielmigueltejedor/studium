"""Compiler diagnostics and source mapping for draft documents.

Diagnostics describe observed TeX failures and layout warnings, never scientific
validity. Only the final compiler pass is used to judge unresolved references.
"""

import base64
import hashlib
import json
import re
from pathlib import Path

_MARKER = "% studium:record "
_ERROR_ADVICE = {
    "double_subscript": "Use braces for mathematical indices; put internal identifiers in code or literal text.",
    "double_superscript": "Group exponents explicitly; check mixed ASCII and Unicode powers.",
    "missing_math_delimiter": "Check math delimiters and text or unit commands inside this record.",
    "undefined_control_sequence": "Check the command spelling and required LaTeX package.",
    "latex_error": "Inspect the indicated record and the preserved compiler log.",
}


def record_lines(record: dict[str, object], lines: list[str]) -> list[str]:
    """Attach invisible, nested provenance comments without changing record text."""
    context = {key: record.get(key) for key in ("id", "section")}
    encoded = base64.urlsafe_b64encode(json.dumps(context, ensure_ascii=True).encode()).decode("ascii")
    return [_MARKER + encoded, *lines, "% studium:end-record " + encoded]


def source_map(document: str) -> list[dict[str, object]]:
    stack: list[tuple[int, dict[str, object], str]] = []
    ranges: list[dict[str, object]] = []
    for number, line in enumerate(document.splitlines(), 1):
        if line.startswith(_MARKER):
            try:
                context = json.loads(base64.urlsafe_b64decode(line[len(_MARKER) :]).decode())
            except (ValueError, UnicodeError):
                continue  # A literal example of the marker in a code listing.
            if isinstance(context, dict) and "id" in context and "section" in context:
                stack.append((number + 1, context, line[len(_MARKER):]))
        elif stack and line == "% studium:end-record " + stack[-1][2]:
            start, context, _ = stack.pop()
            ranges.append({"start": start, "end": number - 1, "record": context["id"], "chapter": context["section"]})
    return sorted(ranges, key=lambda item: int(str(item["start"])))


def _origin(line: int | None, ranges: list[dict[str, object]]) -> dict[str, object]:
    if line is None:
        return {"record": None, "chapter": None}
    matches = [item for item in ranges if int(str(item["start"])) <= line <= int(str(item["end"]))]
    if not matches:
        return {"record": None, "chapter": None}
    nearest = min(matches, key=lambda item: int(str(item["end"])) - int(str(item["start"])))
    return {key: nearest[key] for key in ("record", "chapter")}


def parse_log(log: str, *, filename: str, ranges: list[dict[str, object]]) -> list[dict[str, object]]:
    """Read fatal errors, final-pass references and TeX box warnings.

    Both traditional ``! ... / l.N`` and ``-file-line-error`` formats are
    accepted. Layout warnings remain warnings even when very wide.
    """
    issues: list[dict[str, object]] = []
    lines = log.splitlines()
    for index, text in enumerate(lines):
        file_error = re.match(r"^(.+\.tex):(\d+): (.+)$", text)
        if text.startswith("! ") or file_error:
            message = file_error.group(3) if file_error else text[2:]
            if "Fatal error occurred" in message:
                continue  # The preceding error is actionable; this is only TeX's summary.
            number = int(file_error.group(2)) if file_error else None
            if number is None:
                for following in lines[index + 1 : index + 14]:
                    location = re.match(r"l\.(\d+)\s", following)
                    if location:
                        number = int(location.group(1))
                        break
            kind = next(
                (
                    code
                    for phrase, code in (
                        ("Double subscript", "double_subscript"),
                        ("Double superscript", "double_superscript"),
                        ("Missing $ inserted", "missing_math_delimiter"),
                        ("Undefined control sequence", "undefined_control_sequence"),
                    )
                    if phrase in message
                ),
                "latex_error",
            )
            issues.append(
                {
                    "severity": "ERROR",
                    "type": kind,
                    "file": file_error.group(1) if file_error else filename,
                    "line": number,
                    **_origin(number, ranges),
                    "evidence": message,
                    "method": "latex_compiler",
                    "verification": "observed",
                    "suggestion": _ERROR_ADVICE[kind],
                }
            )
        if re.search(r"(?:Reference|Citation) .+ undefined", text):
            location = re.search(r"input line (\d+)", text)
            number = int(location.group(1)) if location else None
            issues.append(
                {
                    "severity": "WARNING",
                    "type": "undefined_reference",
                    "file": filename,
                    "line": number,
                    **_origin(number, ranges),
                    "evidence": text.strip(),
                    "method": "latex_final_pass",
                    "verification": "observed",
                    "suggestion": "Check the target label and whether its figure was rendered.",
                }
            )
        if re.search(r"(?:LaTeX(?: Font)?|Package \S+) Warning:|Missing character:", text) and not re.search(
            r"(?:Reference|Citation) .+ undefined", text
        ):
            issues.append(
                {
                    "severity": "WARNING",
                    "type": "latex_warning",
                    "file": filename,
                    "line": None,
                    "record": None,
                    "chapter": None,
                    "evidence": text.strip(),
                    "method": "latex_final_pass",
                    "verification": "observed",
                    "suggestion": "Inspect the full compiler log for missing symbols, font substitutions or rerun requests.",
                }
            )
        box = re.search(r"(Overfull|Underfull) \\([hv])box", text)
        if box:
            location = re.search(r"at lines? (\d+)", text)
            number = int(location.group(1)) if location else None
            amount = re.search(r"([\d.]+)pt too (?:wide|high)", text)
            issues.append(
                {
                    "severity": "WARNING" if box.group(1) == "Overfull" else "INFO",
                    "type": "overfull_box" if box.group(1) == "Overfull" else "underfull_box",
                    "file": filename,
                    "line": number,
                    **_origin(number, ranges),
                    "overflow_pt": float(amount.group(1)) if amount else None,
                    "evidence": text.strip(),
                    "method": "latex_final_pass",
                    "verification": "observed",
                    "suggestion": "Inspect the page; align long equations or revise table and figure width.",
                }
            )
    return issues


def editorial_report(
    document: str, log: str, *, filename: str, compiled: bool, compiler: str | None
) -> dict[str, object]:
    ranges = source_map(document)
    issues = parse_log(log, filename=filename, ranges=ranges)
    if compiler and not compiled and not any(item["severity"] == "ERROR" for item in issues):
        issues.append(
            {
                "severity": "ERROR",
                "type": "compiler_failed",
                "file": filename,
                "line": None,
                "record": None,
                "chapter": None,
                "evidence": log[-1000:] or "No successful PDF compilation.",
                "method": "compiler_process",
                "verification": "observed",
                "suggestion": "Inspect the preserved process output for timeout, missing packages or engine errors.",
            }
        )
    for index, issue in enumerate(issues, 1):
        issue["id"] = f"PUB-{index:04d}"
    return {
        "schema_version": "1.0",
        "compiled": compiled,
        "compiler": compiler,
        "document_sha256": hashlib.sha256(document.encode()).hexdigest(),
        "source_map": ranges,
        "counts": {level: sum(item["severity"] == level for item in issues) for level in ("ERROR", "WARNING", "INFO")},
        "issues": issues,
        "limitations": [
            "Compiler diagnostics do not establish scientific validity.",
            "Blank pages, clipped equations and label collisions need visual inspection.",
        ],
    }


def report_markdown(report: dict[str, object]) -> str:
    issues = report.get("issues")
    lines = ["# Studium quality report", "", "Automated observations; expert scientific review remains required.", ""]
    lines.extend([f"Counts: {report.get('counts', {})}", ""])
    for issue in issues if isinstance(issues, list) else []:
        if not isinstance(issue, dict):
            continue
        lines.extend(
            [
                f"## {issue.get('id')} — {issue.get('severity')}: {issue.get('type')}",
                "",
                f"Record: {issue.get('record')}; chapter: {issue.get('chapter')}; line: {issue.get('line')}",
                "",
                str(issue.get("evidence")),
                "",
                str(issue.get("suggestion")),
                "",
            ]
        )
    limitations = report.get("limitations")
    lines.extend(
        ["## Limitations", "", *[str(item) for item in limitations if isinstance(item, str)], ""]
        if isinstance(limitations, list)
        else []
    )
    return "\n".join(lines)


def write_report(path: Path, report: dict[str, object]) -> None:
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path.with_suffix(".md").write_text(report_markdown(report), encoding="utf-8")


def align_long_chain(tex: str, *, threshold: int = 120) -> str:
    """Wrap a long equality chain at top-level equals signs only.

    A single long RHS and existing environments are left intact for editorial
    review. No term, fraction, delimiter pair or mathematical relation is split.
    """
    if len(tex) <= threshold or any(token in tex for token in (r"\begin", r"\left", r"\right", r"\\")):
        return tex
    depth = 0
    boundaries: list[int] = []
    for index, char in enumerate(tex):
        if char in "{([" and (index == 0 or tex[index - 1] != "\\"):
            depth += 1
        elif char in "})]" and (index == 0 or tex[index - 1] != "\\"):
            depth -= 1
            if depth < 0:
                return tex
        elif char == "=" and depth == 0:
            if index > 0 and tex[index - 1] in "<>!:":
                return tex
            boundaries.append(index)
    if depth or len(boundaries) < 2:
        return tex
    pieces: list[str] = []
    start = 0
    for boundary in boundaries:
        pieces.append(tex[start:boundary].strip())
        start = boundary + 1
    pieces.append(tex[start:].strip())
    if any(not piece for piece in pieces):
        return tex
    return (
        r"\begin{aligned}"
        + "\n"
        + pieces[0]
        + " &= "
        + pieces[1]
        + "".join(r" \\" + "\n&= " + piece for piece in pieces[2:])
        + "\n"
        + r"\end{aligned}"
    )
