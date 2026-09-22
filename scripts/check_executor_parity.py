"""Real public corpus executor parity and one worker retry; no speed claim."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import time
from engine.common import read_jsonl, sha
from engine.pipeline import run, registered_snapshot

ROOT = Path(__file__).resolve().parents[1]


def compare_snapshots(left, right):
    names = {p.name for p in left.iterdir()}
    if names != {p.name for p in right.iterdir()}:
        raise ValueError('Executor snapshot file sets differ')
    equality = {}
    for name in sorted(names):
        a, b = left / name, right / name
        if any(p.is_symlink() or not p.is_file() for p in (a, b)):
            raise ValueError('Executor snapshot contains non-regular files')
        equality[name] = sha(a) == sha(b)
    # This acceptance check must survive python -O.
    if not all(equality.values()):
        raise ValueError('Executor snapshot bytes differ: ' + repr(equality))
    return equality


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / 'work') or output == ROOT / 'work':
        parser.error('Use a new work/ child')
    output.mkdir(parents=True, exist_ok=False)
    source = ROOT / 'data/source-v1/source-records.jsonl'
    rows = read_jsonl(source)
    serial = run(rows, output / 'serial')
    serial_path = registered_snapshot(output / 'serial', serial['version'])
    import ray
    started = time.perf_counter()
    ray.init(num_cpus=2, include_dashboard=False, object_store_memory=100*1024*1024,
             _temp_dir=tempfile.mkdtemp(prefix='rp-', dir='/tmp'))
    startup = time.perf_counter() - started
    try:
        marker = output / 'worker-exit-once'
        parallel = run(rows, output / 'ray', executor='ray', fault_marker=marker)
        ray_path = registered_snapshot(output / 'ray', parallel['version'])
        equality = compare_snapshots(serial_path, ray_path)
        if not marker.is_file() or serial['reused_snapshot'] or parallel['reused_snapshot']:
            raise ValueError('Expected fresh executions with worker interruption marker')
        result = dict(created_utc=datetime.now(timezone.utc).isoformat(), input_rows=len(rows),
            input_sha256=sha(source),
            code_sha256={str(p.relative_to(ROOT)): sha(p) for p in
                         (Path(__file__), ROOT/'engine/pipeline.py', ROOT/'engine/common.py', ROOT/'engine/quality.py')},
            ray_cpus=2, ray_version=ray.__version__, ray_startup_seconds=startup,
            serial=serial, ray=parallel, byte_equality=equality, worker_interruption_marker=True,
            scope='real CMRC processing, one worker exit/retry; single-host correctness, not performance comparison')
        (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result, indent=2))
    finally:
        ray.shutdown()


if __name__ == '__main__':
    main()
