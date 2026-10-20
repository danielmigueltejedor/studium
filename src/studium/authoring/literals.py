"""Opaque Markdown code regions shared by rendering and scientific checks.

Offsets always refer to the original text. Unclosed fences consume the remainder;
no equation detector may reinterpret a broken code block as scientific evidence.
"""

import re
from dataclasses import dataclass

_OPEN = re.compile(r"^[ ]{0,3}(`{3,}|~{3,})[ \t]*([^\n]*)$", re.M)


@dataclass(frozen=True)
class CodeRegion:
    start: int
    end: int
    body: str
    language: str = ""
    block: bool = False
    closed: bool = True


def code_regions(text: str) -> list[CodeRegion]:
    regions: list[CodeRegion] = []
    cursor = 0
    while cursor < len(text):
        opening = _OPEN.match(text, cursor) if cursor == 0 or text[cursor - 1] == "\n" else None
        if opening is not None:
            marker, info = opening.groups()
            if marker[0] == "`" and "`" in info:
                cursor = opening.end()
                continue
            closing = re.compile(r"^[ ]{0,3}" + re.escape(marker[0]) + "{" + str(len(marker)) + r",}[ \t]*$", re.M)
            content_start = min(opening.end() + 1, len(text))
            end = closing.search(text, content_start)
            stop = end.end() if end is not None else len(text)
            regions.append(CodeRegion(cursor, stop, text[content_start:end.start() if end else stop],
                                      info.strip().split()[0] if info.strip() else "", True, end is not None))
            cursor = stop
            continue
        if text[cursor] == "`":
            run = re.match(r"`+", text[cursor:])
            assert run is not None
            marker = run.group()
            closing = re.search(r"(?<!`)" + re.escape(marker) + r"(?!`)", text[cursor + len(marker):])
            if closing is not None:
                stop = cursor + len(marker) + closing.end()
                body = text[cursor + len(marker):stop - len(marker)].replace("\n", " ")
                if body.startswith(" ") and body.endswith(" ") and body.strip():
                    body = body[1:-1]
                regions.append(CodeRegion(cursor, stop, body))
                cursor = stop
                continue
            cursor += len(marker)
            continue
        cursor += 1
    return regions


def mask_code(text: str) -> str:
    """Hide code from prose analyses, preserving newlines and original offsets."""
    chars = list(text)
    for region in code_regions(text):
        chars[region.start:region.end] = ["\n" if c == "\n" else " " for c in text[region.start:region.end]]
    return "".join(chars)
