"""Explicit phase gates: build -> dev -> freeze-dev commit -> holdout."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from engine.common import digest,read_jsonl,sha,write_json,write_jsonl
from engine.pipeline import run,verify_snapshot,registered_snapshot
from engine.retrieval import BM25,chunks,evaluate,paired

ROOT=Path(__file__).resolve().parents[1]


def provenance():
    return {'commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'source_sha256':{str(p.relative_to(ROOT)):sha(p) for parent in ('engine','scripts') for p in sorted((ROOT/parent).glob('*.py'))},'protocol_sha256':sha(ROOT/'configs/protocol.json')}


def start(folder):
    folder.mkdir(parents=True,exist_ok=False)
    write_json(folder/'provenance.json',provenance())


def build():
    import ray
    folder=ROOT/'reports/build-v1';start(folder)
    records=read_jsonl(ROOT/'data/source-v1/source-records.jsonl')
    startup=time.perf_counter()
    ray.init(num_cpus=4,include_dashboard=False,log_to_driver=False,_temp_dir='/tmp/ced-ray-build')
    started=time.perf_counter()-startup
    try:
        result=run(records,ROOT/'work/lake-main','ray')
    finally:ray.shutdown()
    snapshot=registered_snapshot(ROOT/'work/lake-main',result['version'])
    reference=run(records,ROOT/'work/lake-serial','serial')
    baseline=registered_snapshot(ROOT/'work/lake-serial',reference['version'])
    comparison={name:sha(snapshot/name)==sha(baseline/name) for name in ('documents.jsonl','quarantine.jsonl','lineage.jsonl','documents.parquet','manifest.json')}
    if not all(comparison.values()):raise ValueError('Serial/Ray mismatch')
    shutil.copytree(snapshot,ROOT/'data/asset-v1')
    write_json(folder/'result.json',{'ray':result,'ray_startup_seconds':started,'serial':reference,'byte_equality':comparison,'ray_version':ray.__version__,'scope':'real single-host Ray Core tasks,4CPUs; not Ray Data streaming or a multi-node cluster'})


def dev():
    folder=ROOT/'reports/retrieval-v1';start(folder)
    protocol=json.loads((ROOT/'configs/protocol.json').read_text())
    docs=read_jsonl(ROOT/'data/asset-v1/documents.jsonl');queries=read_jsonl(ROOT/'data/source-v1/dev.jsonl')
    results={};preds={};sizes={}
    for variant in ('baseline','candidate'):
        arm=folder/variant;arm.mkdir()
        cfg=protocol['retrieval'][variant]
        rows=chunks(docs,**cfg);write_jsonl(arm/'chunks.jsonl',rows)
        t=time.perf_counter();index=BM25(rows,**protocol['retrieval']['bm25']);build_seconds=time.perf_counter()-t
        metrics,pred=evaluate(index,queries)
        write_jsonl(arm/'dev.predictions.jsonl',pred);write_json(arm/'dev.metrics.json',metrics)
        results[variant]=metrics;preds[variant]=pred;sizes[variant]=len(rows)
        write_json(arm/'index.json',{'chunk_count':len(rows),'total_characters':sum(len(r['text']) for r in rows),'index_build_seconds':build_seconds,'chunks_sha256':sha(arm/'chunks.jsonl'),'input_docs_sha256':sha(ROOT/'data/asset-v1/documents.jsonl')})
        if variant=='baseline':
            # Freeze observed baseline dev symptoms before candidate execution.
            write_json(folder/'baseline-diagnosis.json',{'metrics':metrics,'hypothesis':'Overlap may recover reference spans cut by fixed boundaries; cannot fix lexical mismatch, and may crowd top3 with duplicates.','candidate':'Only preregistered160/96; no parameter search.'})
    a,b=results['baseline'],results['candidate'];gate=protocol['gate']
    checks={'span_gain':b['span_hit_at3']-a['span_hit_at3']>=gate['dev_min_span_hit_gain']-1e-12,'doc_recall':b['document_recall_at3']+gate['dev_max_doc_recall_drop']>=a['document_recall_at3']-1e-12,'index_cost':sizes['candidate']/sizes['baseline']<=gate['max_index_chunk_ratio']}
    write_json(folder/'selection.json',{'phase':'dev_only','checks':checks,'candidate_adopted':all(checks.values()),'selected':'candidate' if all(checks.values()) else 'baseline','metrics':results,'paired':paired(preds['baseline'],preds['candidate']),'chunk_counts':sizes,'holdout_queries_sha256':sha(ROOT/'data/source-v1/holdout.jsonl')})


def freeze():
    folder=ROOT/'reports/retrieval-v1';path=folder/'freeze.json'
    if path.exists():raise FileExistsError(path)
    status=subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True)
    if status:raise RuntimeError('Commit dev decision and code before freeze: '+status)
    write_json(path,dict(provenance(),selection_sha256=sha(folder/'selection.json'),holdout_sha256=sha(ROOT/'data/source-v1/holdout.jsonl'),chunks_sha256={v:sha(folder/v/'chunks.jsonl') for v in ('baseline','candidate')}))


def holdout():
    folder=ROOT/'reports/retrieval-v1';f=json.loads((folder/'freeze.json').read_text());current=provenance()
    if current['source_sha256']!=f['source_sha256'] or current['protocol_sha256']!=f['protocol_sha256']:raise ValueError('Code/protocol changed since dev freeze')
    if sha(folder/'selection.json')!=f['selection_sha256'] or sha(ROOT/'data/source-v1/holdout.jsonl')!=f['holdout_sha256']:raise ValueError('Selection/data changed')
    out=folder/'holdout';start(out)
    protocol=json.loads((ROOT/'configs/protocol.json').read_text());queries=read_jsonl(ROOT/'data/source-v1/holdout.jsonl');metrics={};preds={}
    for v in ('baseline','candidate'):
        if sha(folder/v/'chunks.jsonl')!=f['chunks_sha256'][v]:raise ValueError('Chunks changed')
        index=BM25(read_jsonl(folder/v/'chunks.jsonl'),**protocol['retrieval']['bm25'])
        metrics[v],preds[v]=evaluate(index,queries)
        write_jsonl(out/f'{v}.predictions.jsonl',preds[v]);write_json(out/f'{v}.metrics.json',metrics[v])
    write_json(out/'summary.json',{'metrics':metrics,'paired':paired(preds['baseline'],preds['candidate']),'dev_selection':json.loads((folder/'selection.json').read_text())['selected'],'holdout_does_not_reselect':True})

if __name__=='__main__':
    os.chdir(ROOT)
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['build','dev','freeze','holdout']);a=p.parse_args()
    globals()[a.phase]()
