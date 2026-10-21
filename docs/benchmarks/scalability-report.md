# Storage scalability measurements

Measured on 21 October 2026 against base `b30934f` and this render-integrity change, using Python 3.12.15 on macOS 27.2 ARM64. Status: **IMPLEMENTED_NEEDS_REVIEW** for the benchmark; the broader scalability programme remains **NOT_IMPLEMENTED**.

## Reproduction and scope

```bash
PYTHONPATH=src python benchmarks/record_scalability.py > record-scalability.json
```

The script creates deterministic temporary JSONL corpora for 10, 30 and 60 chapters, with 100 current paragraphs per chapter, two excerpt links per paragraph, and one historical revision for every five paragraphs. It verifies the folded record count, measures five complete file-read/fold operations with `perf_counter`, then separately measures Python allocations with `tracemalloc`. Temporary corpora are removed after the run. Paragraphs contain 240 synthetic words; no source material is copied.

These are paragraph storage measurements with warm operating-system caches. Excerpt identifiers are links only; the benchmark does not resolve a source graph. The allocation figures cover traced allocations for reading/folding, not total process RSS. JSONL input bytes are measured, not operating-system I/O operations. No benchmark claims PDF page count, scientific audit throughput, MCP throughput, partial-regeneration throughput or representative performance for a 500-page book.

## Observations

| Chapters | Current paragraphs / history rows | Evidence links | JSONL bytes | Before median (s) | After median (s) | Traced peak (bytes), both runs |
|---|---:|---:|---:|---:|---:|---:|
| 10 | 1,000 / 1,200 | 2,000 | 2,733,000 | 0.005818 | 0.006608 | 11,964,152 |
| 30 | 3,000 / 3,600 | 6,000 | 8,199,000 | 0.016769 | 0.018024 | 35,906,808 |
| 60 | 6,000 / 7,200 | 12,000 | 16,398,000 | 0.046466 | 0.037158 | 71,823,632 |

Raw samples, interpreter and platform details are preserved in [before data](data/record-scalability-before.json) and [after data](data/record-scalability-after.json). The storage implementation is unchanged in this PR. Differences are observations across runs, not an optimization or a statistically established improvement. The samples are too small to infer tail latency or cold-disk performance.

The load/fold operation scales approximately with input size in these cases; its traced peak is roughly 4.4 times the input file size. This supports measuring repeated full-file reads in higher-level workflows before choosing an index or cache. It does not justify a cache that bypasses revision checks.

## Real-book context

A copied programming volume with 48 current paragraphs and eight blueprint sections was inspected. Single calls took 0.0262 s for project status, 0.0003 s for the next action, 0.0975 s for section completeness and 0.0018 s for the scientific-contract report. These are single diagnostic observations, not repeated comparative benchmarks. The scientific-contract report contained zero contracts, so its latency says nothing about large contract sets. Rendering and observations are documented in [publishing validation](../quality/publishing-validation.md).

## Remaining measurements

The existing `benchmarks/qc_latency.py` supports repeated quality-control calls on a **copy** of a real project; contradiction scan and review append records. Future work must measure a populated evidence graph, hundreds of exercises, full audit and dependency invalidation, 500+ compiled pages, RSS, read amplification, concurrent MCP requests, and interruption/retry costs. No optimization, cache or readiness claim is made for those unmeasured cases.
