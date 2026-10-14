"""On-demand latency benchmark for the quality-control calls of a real book.

Not part of the test suite. Point it at a COPY of a book workspace; the scan
and review calls append records to the project they run on.

    PYTHONPATH=src python benchmarks/qc_latency.py /path/to/copy/workspace slug [--repeat 3]

Prints the wall time of each call (median of the repeats) as JSON.
"""

import argparse
import json
import statistics
import time
from pathlib import Path

from studium.mcp.server import dispatch, open_workspace

CALLS = (
    "studium_project_status",
    "studium_book_next",
    "studium_contradiction_scan",
    "studium_book_review",
    "studium_quality_report",
    "studium_draft_completeness",
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("workspace", type=Path)
    parser.add_argument("slug")
    parser.add_argument("--repeat", type=int, default=3)
    args = parser.parse_args()
    project = args.workspace / args.slug
    session = open_workspace(str(args.workspace), default_project=str(project))
    if session is None:
        raise SystemExit(f"not a workspace: {args.workspace}")
    timings: dict[str, float] = {}
    for tool in CALLS:
        samples = []
        for _ in range(max(1, args.repeat)):
            start = time.perf_counter()
            dispatch(tool, {}, session=session)
            samples.append(time.perf_counter() - start)
        timings[tool] = round(statistics.median(samples), 3)
    print(json.dumps(timings, indent=1))


if __name__ == "__main__":
    main()
