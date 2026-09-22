# Validate staging before snapshot publication — 2026-09-22

## Reproduced failure

After an interrupted driver created staging and cached one shard, a retry trusted the directory contents. An extra file was included in the new manifest and registered even though the snapshot reader later rejected it. A symlink at `documents.jsonl` could be followed during overwrite; an unexpected directory produced an incidental I/O error. Existing tests covered corrupt published snapshots, not these pre-publication staging states.

## Repair

`engine/pipeline.py` now checks the resumed staging directory before any output write. Only the six known regular filenames are permitted; symlinks, directories and extra names are rejected without registration. `verify_snapshot(stage)` also runs before rename. Valid cached shards survive the failure, and removing the identified invalid entry permits normal recovery. The operator must inspect the invalid entry; the implementation does not silently delete evidence of corruption.

This protects against stale or accidentally malformed staging within the single trusted writer model. It is not a hostile concurrent-filesystem defense or a multi-host transaction. Existing flock, atomic rename, SQLite registration and hashes remain the publication mechanism.

## Reproduce

Python 3.12, `requirements-ci.lock.txt` for serial checks; full `requirements.lock.txt` including Ray for parallel checks. Run from repository root:

```sh
python -m pytest -q tests/test_staging_publish.py
python -m pytest -q
PYTHONPATH=. python scripts/verify_portable.py
PYTHONPATH=. python scripts/reproduce_portable.py --output work/rebuild-demo
PYTHONPATH=. python scripts/check_executor_parity.py --output work/parity-demo
```

Parity requires local Ray process/socket permissions. It uses 2 local CPUs, a short temporary socket path, separate cold serial/Ray lakes and one deliberately killed worker. Output directories must be new. No new dependencies were added. Ray initialization is recorded separately; the single diagnostic execution is not a performance benchmark.

## Executed evidence

Before: 64 existing tests passed, then all three new staging cases failed. After: 67 tests passed. All 640 historical query-arm rankings were recomputed identically. Current-code reconstruction of all 2,403 public corpus rows and 8 development queries matched saved assets/rankings. A real Ray run with worker exit/retry matched serial bytes for documents, Parquet, quarantine, lineage, input identities and manifest. Results/logs are in `evidence/`.

The first Ray attempt was blocked by sandbox process inspection; the next hit macOS socket path length. The successful command used approved local process access and a short `/tmp` path. These were environment failures and were not counted as successful data runs. No independent hardware or fresh network source download was tested.

## Unchanged interpretation

Historical holdout span-hit@3 is 130/160→143/160, with 17 fixes and 4 regressions, index size 8,775→12,297, and higher query latency. It is labeled-span evidence coverage, not final answer accuracy. Historical Ray timings did not show acceleration; this maintenance adds no speed or model-effect claim. Source, split, protocol, frozen reports and old source snapshots are unchanged. This dated follow-up used AI-assisted implementation and verification.
