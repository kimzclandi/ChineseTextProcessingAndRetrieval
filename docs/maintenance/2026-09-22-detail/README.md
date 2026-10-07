# Hardlink-safe staging and reliable parity acceptance — 2026-09-22 follow-up

## Failure-first findings

The earlier staging checks rejected symlinks but allowed hardlinks. A regular-looking `documents.jsonl` sharing an inode with another file could overwrite that file during retry. The added hardlink regression failed before repair; the original three staging cases continued to pass.

The parity runner also used an assertion for byte equality. A minimal probe executing that exact assertion under `python -O` with a false equality value exited successfully. This probe did not run Ray or measure model/data performance.

## Changes

Staging entries must additionally have link count one before output writes. A hardlinked entry is rejected before publication, leaving the other file untouched and shard cache reusable. This protects stale staging under the trusted single-writer contract; it does not claim resistance to an adversary racing filesystem changes.

The parity runner is now import-safe, imports Ray only when executing, compares complete file sets and bytes with explicit exceptions, checks the interruption marker and fresh-execution flags, and records input/code hashes. Output confinement uses the repository root, not a caller-supplied current working directory. Historical runner and pipeline source bytes are preserved under `baseline/`.

## Verification

Python 3.12.13, pyarrow 23.0.1, Ray 2.54.0. From repository root:

```sh
python -m pytest -q
PYTHONPATH=. python scripts/reproduce_portable.py --output work/detail-rebuild-new
PYTHONPATH=. python scripts/verify_portable.py
PYTHONPATH=. python scripts/check_executor_parity.py --output work/detail-parity-new
```

All 70 tests passed, including hardlink recovery and byte-mismatch detection in an optimized Python subprocess. Rebuilt all 2,403 public corpus rows and executed 8 development queries; assets/rankings matched. All 640 historical query-arm records were re-ranked consistently. A new 2-CPU Ray execution with one worker exit/retry matched all six serial snapshot files byte for byte.

This is same-host correctness/recovery evidence, not a controlled speed benchmark. No new model-quality result, new holdout selection or independent-hardware claim. Old source/data/configuration/report and first-round maintenance evidence remain unchanged.
