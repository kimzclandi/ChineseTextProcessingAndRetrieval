# Chinese Text Processing and Retrieval Evaluation

[简体中文](README.md) | **English**

![Project wordmark](.github/project-header.svg)

[![offline-evidence](https://github.com/kimzclandi/ChineseTextProcessingAndRetrieval/actions/workflows/offline.yml/badge.svg)](https://github.com/kimzclandi/ChineseTextProcessingAndRetrieval/actions/workflows/offline.yml)
[![Stars](https://img.shields.io/github/stars/kimzclandi/ChineseTextProcessingAndRetrieval?style=flat)](https://github.com/kimzclandi/ChineseTextProcessingAndRetrieval/stargazers) [![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A recoverable, traceable Chinese evidence pipeline: fixed public sources → quality and duplicate auditing → local Ray processing → Parquet/JSONL assets and SQLite lineage → retrieval failure analysis → one chunking revision → frozen holdout evaluation.

The focus is data operators, immutable snapshots, lineage and evaluation-driven iteration. There are no paid APIs, cloud GPUs, model training or generated answers. Metrics measure retrieved evidence coverage, **not language-model answer accuracy, official CMRC scores or business gains**.

## Features

- Chinese text quality checks, deduplication and source lineage.
- Ray/serial processing and immutable snapshots.
- Retrieval coverage and failure analysis on fixed splits.

## Components and data flow

| Layer | Input → output | Design tradeoff |
|---|---|---|
| Quality | Source records → accepted documents, quarantine reasons and lineage | Preserve original offsets; near-duplicates merge evaluation families, not source texts |
| Execution/publication | Stable content shards → immutable snapshots and version registration | Retryable workers, idempotent final publication; local filesystem |
| Retrieval | Text chunks and questions → rankings, span coverage and failure slices | Fixed BM25 and character budget; answers never enter the index |
| Iteration | Development failures → frozen candidate and holdout results | Report fixes, regressions, index size and latency together |

## Reading and verification

The [experiment guide](docs/EXPERIMENT_GUIDE.md) explains inputs/outputs, controls, metric denominators, code/evidence paths, saved-result verification and actual reruns. Start with results and limitations below, then trace individual records. Read environment and output-protection instructions before running commands. Linked technical documents retain their original language.

## Project history (added 2026-09-20)

According to the maintainer, related early work began locally around April 2026 before consolidation and upload to GitHub. This approximate starting point does not date every current feature or experiment. Later implementations, experiments and maintenance retain their actual version and run dates.

## Measured results

The fixed public CMRC2018 train source contains 2,403 passages and 10,142 candidate questions. Before evaluation sampling, 21 questions failed nonempty/original-offset checks and were excluded; their passages were retained. One highly similar passage pair was merged into an evaluation family, leaving 2,402 families. Development and holdout each contain 160 questions, at most one per family. CMRC dev used by the earlier QA project serves only as a source-exclusion list, not scoring or parameter selection here.

| Metric | Non-overlapping 160-character chunks | 160-character chunks, stride 96 |
|---|---:|---:|
| Development span-hit@3 | 132/160 = 82.50% | 142/160 = 88.75% |
| Holdout span-hit@3 | 130/160 = 81.25% | 143/160 = 89.38% |
| Holdout source-document recall@3 | 153/160 = 95.625% | 152/160 = 95.00% |
| Holdout oracle span coverage | 89.38% | 100.00% |
| Chunk count | 8,775 | 12,297 |
| Median holdout query latency | 7.50ms | 12.04ms |

Both arms use the same character BM25, corpus, top-3 and maximum 480 original characters; overlapping text still consumes budget. A span hit requires a retrieved chunk from the annotated source document that fully covers an original reference-answer offset. **This means annotated evidence can be retrieved, not that it is sufficient to infer an answer or that a generator answers correctly.**

The holdout gains 13 net questions (+8.125 percentage points): 17 fixes and 4 regressions. Document recall loses one question. The index has 40.14% more chunks and queries are slower. Development gates were passed before freezing and checking holdout; holdout was not used for further parameter selection. [Results and per-question evidence](reports/RESULTS.md).

## Measured system behavior

- **Actual Ray Core tasks:** one machine, 4 CPUs, at most 8 in-flight tasks; pure operators, 256 stable content-hash buckets and at most 64 rows per shard. No Ray Data streaming, Spark/Flink or multi-machine cluster.
- **Determinism:** Ray and serial outputs on the actual corpus match byte-for-byte for documents, quarantines, lineage, Parquet and manifests.
- **Versioning/recovery:** content/operator-addressed shard caches; complete snapshots built in temporary directories then atomically renamed; SQLite transactions register versions and lineage. Readers accept only registered, hash-verified snapshots; retries are idempotent.
- **Failure injection:** actual worker `os._exit(73)` and retry, subprocess exit before commit and recovery, duplicate delivery, incremental append, tampering detection, and recovery of a simulated rename-before-registration gap all passed.
- **Incremental fixture:** appending one record reused 84 shards and processed one; document bytes matched a full rebuild. This is an explicitly synthetic engineering fixture, not business data.
- **Negative performance result:** 2,403 actual records, three runs per executor; median serial throughput about 13,078 rows/s versus Ray 11,968 rows/s. **No speedup was demonstrated at this scale.** Ray initialization is separate; timings include local writes and are not cluster throughput.

The actual corpus had no exact-duplicate or contact-information rule hits, so no model gain from a cleaning removal rate is claimed. Near-duplicates merge evaluation families without blindly deleting original texts or offsets. See the [data card](docs/DATA_CARD.md) for PII-rule boundaries.

## Quick start

Python 3.12; the full lock was tested on macOS arm64. No model, API key or GPU is required. Initial dependency installation needs network access. Allow about 1GB of disk space; minimum hardware was not measured. Run from the repository root without `python -O`.

### Installation

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) first.

```bash
git clone https://github.com/kimzclandi/ChineseTextProcessingAndRetrieval.git
cd ChineseTextProcessingAndRetrieval
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python -r requirements.lock.txt
```

### Usage

```bash
.venv/bin/python -m pytest -q
PYTHONPATH=. .venv/bin/python scripts/verify.py
# Execute BM25 retrieval and compare saved rankings; no tuning or report overwrite
PYTHONPATH=. .venv/bin/python scripts/verify_portable.py
# Reprocess all source documents and run 8 dev queries in a new, protected directory
PYTHONPATH=. .venv/bin/python scripts/reproduce_portable.py --output work/reproduce-01
```

Evidence verification is read-only; reproduction executes processing. They are different operations. Ray failure experiments were actually run; rerunning requires local process/port permissions. Lightweight CI uses `requirements-ci.lock.txt`, tests frozen evidence, reruns 640 query-arm retrieval records and performs a portable serial asset rebuild. It does not establish cross-machine Ray, model inference or independent-machine end-to-end reproduction. [Publication and compatibility](docs/PUBLICATION.md).

To actually download again from the fixed official source and rebuild the sample:

```bash
PYTHONPATH=. .venv/bin/python scripts/fetch_prepare.py --output work/fresh-source-01
```

A source-hash mismatch fails rather than silently changing source. Published `data/` and `reports/` are frozen evidence; batch study scripts refuse to overwrite existing rounds. Do not delete old results to rerun. Use `work/` subdirectories for new work. [Full reproduction guide](docs/REPRODUCE.md).

## Implementation and documentation

| Implementation | Responsibility | Documentation/evidence |
|---|---|---|
| `engine/quality.py`, `engine/dataset.py` | Quarantine, exact deduplication, lineage, near-duplicate families and splits | [Data card](docs/DATA_CARD.md) |
| `engine/pipeline.py` | Ray/serial execution, shard cache, immutable snapshots, SQLite registration/recovery | [Architecture](docs/ARCHITECTURE.md) |
| `engine/retrieval.py` | Character BM25, original-offset coverage and paired fixes/regressions | [Results](reports/RESULTS.md) |
| `scripts/reproduce_portable.py`, `scripts/verify_portable.py` | Isolated rebuilding and portable ranking checks | [Reproduction](docs/REPRODUCE.md) |

[AI assistance and contributions](CONTRIBUTIONS.md) · [Data licensing](DATA_LICENSE.md) · [Sources](docs/SOURCES.md) · [Publication](docs/PUBLICATION.md)

This project produces data assets and retrieval evidence. [Small-model QA finetuning and quantization](https://github.com/kimzclandi/SmallModelQAFinetuningAndQuantization) independently studies LoRA, response distillation and quantization. Retrieval coverage gains are not model-training gains. Implementation is limited to single-machine batch processing; multi-machine execution, unified streaming/batch processing, image/audio operators and production deployment are unverified.

[2026-09-19 maintenance](docs/maintenance/2026-09-19/README.md) · [2026-09-21 maintenance](docs/maintenance/2026-09-21/README.md)

## Contributing

[Guide](CONTRIBUTING.md) · [Code of conduct](CODE_OF_CONDUCT.md) · [Maintenance](docs/MAINTAINING.md)

[Report a bug](https://github.com/kimzclandi/ChineseTextProcessingAndRetrieval/issues/new?template=bug_report.yml) · [Request a feature](https://github.com/kimzclandi/ChineseTextProcessingAndRetrieval/issues/new?template=feature_request.yml)

## License

Code: [MIT](LICENSE). Data and derived assets: [licensing and attribution](DATA_LICENSE.md).

[Naming and compatibility](docs/NAMING.md)
