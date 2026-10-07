"""Real public corpus executor parity and one worker retry; no speed claim."""
import json,sys,time
from pathlib import Path
import ray
from engine.common import read_jsonl,sha
from engine.pipeline import run,registered_snapshot
import argparse,tempfile
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
out=a.output.resolve();root=Path.cwd().resolve()
if not out.is_relative_to(root/'work') or out==root/'work':raise ValueError('Use a new work/ child')
out.mkdir(parents=True,exist_ok=False)
rows=read_jsonl('data/source-v1/source-records.jsonl')
serial=run(rows,out/'serial'); sp=registered_snapshot(out/'serial',serial['version'])
started=time.perf_counter()
ray.init(num_cpus=2,include_dashboard=False,object_store_memory=100*1024*1024,_temp_dir=tempfile.mkdtemp(prefix='rp-',dir='/tmp'))
startup=time.perf_counter()-started
try:
 parallel=run(rows,out/'ray',executor='ray',fault_marker=(out/'worker-exit-once').resolve())
 rp=registered_snapshot(out/'ray',parallel['version'])
 equality={p.name:sha(p)==sha(rp/p.name) for p in sp.iterdir()}
 assert all(equality.values()),equality
 result=dict(input_rows=len(rows),ray_cpus=2,ray_version=ray.__version__,ray_startup_seconds=startup,serial=serial,ray=parallel,byte_equality=equality,scope='real CMRC processing, one worker exit/retry; single-host correctness, not performance comparison')
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
finally:ray.shutdown()
