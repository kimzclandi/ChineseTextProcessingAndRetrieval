# 2026-09-22 follow-up: Atomic JSON publication

This is a post-submission improvement. Earlier records and dates are unchanged.

Five synthetic filesystem failures reproduced linked-file overwrite, leftover partial temporary files and concurrent writer collisions. Publication now uses exclusively created unique same-directory files, serializes before creation, fsyncs content, replaces the destination, and removes only its own temporary file. The exact old common.py is archived for frozen source hashes.

## Reproduce

Python 3.12; install requirements-ci.lock.txt for the Python data repositories. Agent export tests use the standard library. Use a new output directory each time.

```sh
python -m pytest tests/test_atomic_json.py -q
PYTHONPATH=. python scripts/verify_portable.py
PYTHONPATH=. python scripts/reproduce_portable.py --output work/new-reproduce
```

Expected: tests exit 0; replay and rebuild pass historical contracts. Baseline failure logs and current validation logs are in evidence/. Fresh local clones/environments remain same-host replication, not independent hardware replication.

## Limits

Last successful writer wins. This is one-file atomic publication, not a multi-file transaction or power-loss durability guarantee for the directory. No retrieval gain is claimed.

No new training, human semantic annotation, model-quality uplift or deployment is claimed. For resume mapping and interview questions, see the existing 2026-09-22 maintenance handoff; this addendum changes reliability evidence only.
