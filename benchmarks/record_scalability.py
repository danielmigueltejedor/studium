"""Reproducible bounded JSONL load/fold probe, not a full scientific audit."""

import json
import platform
import statistics
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

from studium.storage.records import fold_by_id


def probe():
    rows = []
    with tempfile.TemporaryDirectory(prefix="studium-scalability-") as directory:
        root = Path(directory)
        for chapters in (10, 30, 60):
            paragraphs = chapters * 100
            records = []
            for index in range(paragraphs):
                record = {
                    "id": f"PAR-{index + 1:06d}",
                    "section": f"ch-{index // 100 + 1:02d}",
                    "revision": 1,
                    "text": ("Synthetic academic paragraph for storage measurement. " * 40).strip(),
                    "excerpts": [f"EXC-{index % 1000 + 1:06d}", f"EXC-{(index + 1) % 1000 + 1:06d}"],
                    "status": "draft",
                }
                records.append(record)
                if index % 5 == 0:
                    records.append({**record, "revision": 2, "text": record["text"] + " Revised."})
            path = root / f"chapters-{chapters}.jsonl"
            path.write_text("".join(json.dumps(row, separators=(",", ":")) + "\n" for row in records))
            samples = []
            for _ in range(5):
                start = time.perf_counter()
                folded = fold_by_id(path)
                samples.append(time.perf_counter() - start)
                assert len(folded) == paragraphs
            tracemalloc.start()
            folded = fold_by_id(path)
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            rows.append(
                {
                    "chapters": chapters,
                    "current_paragraphs": paragraphs,
                    "history_rows": len(records),
                    "evidence_links": paragraphs * 2,
                    "input_bytes": path.stat().st_size,
                    "load_fold_seconds_median": round(statistics.median(samples), 6),
                    "load_fold_seconds_samples": [round(x, 6) for x in samples],
                    "python_peak_bytes": peak,
                }
            )
    return {
        "scope": "JSONL paragraph read and fold only; no PDF page count, semantic audit, full-book benchmark or optimization claim. Files generated deterministically; warm OS cache; five samples; tracemalloc measured separately.",
        "python": sys.version,
        "platform": platform.platform(),
        "results": rows,
    }


if __name__ == "__main__":
    print(json.dumps(probe(), indent=2))
