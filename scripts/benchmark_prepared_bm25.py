"""Predeclared exact-output BM25 implementation comparison; never rewrites old reports."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import platform
import random
import statistics
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from engine.retrieval import BM25
from engine.prepared_bm25 import PreparedBM25

SPEC=ROOT/'configs/bm25-exact-performance-v1.json'


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]
def save(p,value):p.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def validate_timing_schedule(records, spec, query_ids):
    """Replay the frozen runner's seeded schedule, without executing searches.

    Coverage and medians alone cannot establish a paired comparison: reversing
    one arm's queries leaves both unchanged. Check recorded execution order as
    well as each row's declared arm order. This audits records, not wall-clock
    provenance or whether the measured process actually followed the schedule.
    """
    if len(set(query_ids)) != len(query_ids):
        raise ValueError('Duplicate query identities')
    expected_count = len(spec['indexes']) * spec['rounds'] * len(spec['arms'])
    if len(records) != expected_count:
        raise ValueError('Timing cell count differs from protocol')
    rng = random.Random(spec['seed'])
    position = 0
    for index in spec['indexes']:
        for round_id in range(spec['rounds']):
            arm_order = list(spec['arms'])
            rng.shuffle(arm_order)
            query_order = list(query_ids)
            rng.shuffle(query_order)
            for arm in arm_order:
                row = records[position]
                position += 1
                if type(row['round']) is not int:
                    raise ValueError('Timing round must be an integer')
                if (row['index'], row['round'], row['arm']) != (index, round_id, arm):
                    raise ValueError('Recorded timing order differs from frozen schedule')
                if row.get('arm_order') != arm_order:
                    raise ValueError('Recorded arm order differs from frozen schedule')
                if [sample['id'] for sample in row['queries']] != query_order:
                    raise ValueError('Recorded query order differs from frozen paired schedule')


def summarize(records,spec,query_ids):
    validate_timing_schedule(records, spec, query_ids)
    expected={(i,r,a) for i in spec['indexes'] for r in range(spec['rounds']) for a in spec['arms']}
    cells={}
    for row in records:
        key=(row['index'],row['round'],row['arm'])
        if key not in expected or key in cells:raise ValueError('Unexpected timing cell')
        samples=row['queries']
        if len(samples)!=len(query_ids) or {s['id'] for s in samples}!=set(query_ids):raise ValueError('Query coverage differs')
        if any(not isinstance(s['seconds'],(int,float)) or isinstance(s['seconds'],bool) or not math.isfinite(s['seconds']) or s['seconds']<=0 for s in samples):raise ValueError('Invalid timing')
        cells[key]=statistics.median(s['seconds'] for s in samples)
    if set(cells)!=expected:raise ValueError('Missing timing cells')
    result={}
    for index in spec['indexes']:
        medians={a:statistics.median(cells[index,r,a] for r in range(spec['rounds'])) for a in spec['arms']}
        speedup=medians['reference']/medians['prepared']
        faster=sum(cells[index,r,'prepared']<cells[index,r,'reference'] for r in range(spec['rounds']))
        result[index]=dict(median_of_round_query_medians_seconds=medians,speedup=speedup,
            faster_rounds=faster,passed=speedup>=spec['minimum_speedup'] and faster>=spec['minimum_faster_rounds'])
    return result


def run(output):
    if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip():raise ValueError('Require clean committed protocol')
    spec=json.loads(SPEC.read_text());output.mkdir(parents=True,exist_ok=False)
    query_files=[ROOT/f'data/source-v1/{s}.jsonl' for s in spec['splits']]
    queries=[q for p in query_files for q in load(p)]
    if len({q['id'] for q in queries})!=len(queries):raise ValueError('Duplicate query IDs')
    inputs={str(p.relative_to(ROOT)):sha(p) for p in query_files}
    files=['engine/retrieval.py','engine/prepared_bm25.py','scripts/benchmark_prepared_bm25.py',str(SPEC.relative_to(ROOT))]
    sources={}
    for path in files:
        dest=output/'source'/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes((ROOT/path).read_bytes());sources[path]=sha(ROOT/path)
    save(output/'protocol.json',spec)
    run=dict(status='running',git_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),python=sys.version,platform=platform.platform(),source_sha256=sources,input_sha256=inputs)
    save(output/'run.json',run)
    try:
        records=[];equal=[];rng=random.Random(spec['seed']);builds={}
        for index in spec['indexes']:
            path=ROOT/f'reports/retrieval-v1/{index}/chunks.jsonl';inputs[str(path.relative_to(ROOT))]=sha(path)
            chunks=load(path);arms={};builds[index]={}
            for name,cls in [('reference',BM25),('prepared',PreparedBM25)]:
                start=time.perf_counter();arms[name]=cls(chunks);builds[index][name]=time.perf_counter()-start
            for q in queries:
                a=arms['reference'].search(q['question'],spec['k']);b=arms['prepared'].search(q['question'],spec['k'])
                if a!=b:raise ValueError('Score or order differs')
                equal.append(dict(index=index,id=q['id'],hits=[dict(chunk_id=c['chunk_id'],score=s) for c,s in a]))
            # Full equality pass also warms both implementations.
            for r in range(spec['rounds']):
                order=list(spec['arms']);rng.shuffle(order);qorder=list(queries);rng.shuffle(qorder)
                for arm in order:
                    samples=[]
                    for q in qorder:
                        start=time.perf_counter();arms[arm].search(q['question'],spec['k']);elapsed=time.perf_counter()-start
                        samples.append(dict(id=q['id'],seconds=elapsed))
                    records.append(dict(index=index,round=r,arm=arm,arm_order=order,queries=samples))
                    save(output/'timings.json',records)
            print(index,'complete',flush=True)
        save(output/'equivalence.json',equal);save(output/'build-seconds.json',builds)
        save(output/'summary.json',summarize(records,spec,[q['id'] for q in queries]));run['status']='complete'
    except Exception as exc:run.update(status='failed',error=repr(exc));raise
    finally:
        save(output/'run.json',run)
        save(output/'checksums.json',{str(p.relative_to(output)):sha(p) for p in sorted(output.rglob('*')) if p.is_file() and p.name!='checksums.json'})


def verify(output):
    if {str(p.relative_to(output)):sha(p) for p in output.rglob('*') if p.is_file() and p.name!='checksums.json'}!=json.loads((output/'checksums.json').read_text()):raise ValueError('Evidence changed')
    run=json.loads((output/'run.json').read_text());spec=json.loads((output/'protocol.json').read_text())
    if run['status']!='complete' or spec!=json.loads(SPEC.read_text()):raise ValueError('Incomplete or changed protocol')
    for path,value in run['input_sha256'].items():
        if sha(ROOT/path)!=value:raise ValueError('Frozen input changed')
    for path,value in run['source_sha256'].items():
        if sha(output/'source'/path)!=value:raise ValueError('Source archive changed')
    queries=[q for s in spec['splits'] for q in load(ROOT/f'data/source-v1/{s}.jsonl')]
    evidence=[]
    for index in spec['indexes']:
        chunks=load(ROOT/f'reports/retrieval-v1/{index}/chunks.jsonl');a=BM25(chunks);b=PreparedBM25(chunks)
        for q in queries:
            x=a.search(q['question'],spec['k']);y=b.search(q['question'],spec['k'])
            if x!=y:raise ValueError('Current code output differs')
            evidence.append(dict(index=index,id=q['id'],hits=[dict(chunk_id=c['chunk_id'],score=s) for c,s in x]))
    # Same-runtime reference/candidate above remain bit-exact. Across libm
    # implementations use the repository's existing 1e-12 archive tolerance.
    from scripts.verify_portable import compare_hits
    saved=json.loads((output/'equivalence.json').read_text())
    if len(saved)!=len(evidence):raise ValueError('Archived query coverage differs')
    for a,b in zip(evidence,saved):
        if (a['index'],a['id'])!=(b['index'],b['id']):raise ValueError('Archived query order differs')
        compare_hits(a['hits'],b['hits'])
    result=summarize(json.loads((output/'timings.json').read_text()),spec,[q['id'] for q in queries])
    if result!=json.loads((output/'summary.json').read_text()):raise ValueError('Timing summary differs')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['run','verify']);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    if args.action=='run':run(args.output)
    else:print(json.dumps(verify(args.output),indent=2))
