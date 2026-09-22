"""Read-only artifact check; optionally recompute BM25 rankings with --rerank.

No model, Ray service, network or new writes. Metadata file hashes are audited
separately against reports/manifest.json, generated after all final reports.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path
from engine.common import read_jsonl,sha
from engine.pipeline import verify_snapshot
from engine.retrieval import BM25,chunks,score_query,summarize,paired

ROOT=Path(__file__).resolve().parents[1]


def historical_source(path):
    # These exact pre-maintenance bytes remain bound to the original freeze.
    if path in {'engine/pipeline.py', 'engine/quality.py', 'scripts/verify.py', 'scripts/systems.py'}:
        return ROOT/'docs/maintenance/2026-09-19/baseline'/f'{path}.txt'
    if path == 'engine/common.py':
        return ROOT/'docs/maintenance/2026-09-22-readiness/baseline/engine/common.py.txt'
    return ROOT/path


def main(rerank=False):
    import os
    os.chdir(ROOT)
    if not __debug__:raise SystemExit('Do not disable assertions')
    manifest=json.loads(Path('reports/manifest.json').read_text())
    for f,h in manifest['files'].items():assert sha(f)==h,f
    source=json.loads(Path('data/source-v1/manifest.json').read_text())
    for f,h in source['files'].items():assert sha(Path('data/source-v1')/f)==h,f
    asset=verify_snapshot('data/asset-v1');docs=read_jsonl('data/asset-v1/documents.jsonl');docmap={r['doc_id']:r for r in docs}
    protocol=json.loads(Path('configs/protocol.json').read_text());folder=Path('reports/retrieval-v1');freeze=json.loads((folder/'freeze.json').read_text())
    assert sha('configs/protocol.json')==freeze['protocol_sha256']
    for f,h in freeze['source_sha256'].items():assert sha(historical_source(f))==h,f
    assert sha(folder/'selection.json')==freeze['selection_sha256']
    assert sha('data/source-v1/holdout.jsonl')==freeze['holdout_sha256']
    qs={s:read_jsonl(f'data/source-v1/{s}.jsonl') for s in ['dev','holdout']}
    assert all(len(rows)==160 and len({r['family_id'] for r in rows})==160 for rows in qs.values())
    assert not {r['family_id'] for r in qs['dev']}&{r['family_id'] for r in qs['holdout']}
    for rows in qs.values():
        for q in rows:
            text=docmap[q['doc_id']]['text']
            assert all(text[a['start']:a['start']+len(a['text'])]==a['text'] for a in q['answers'])
    results={}
    for v in ['baseline','candidate']:
        saved=read_jsonl(folder/v/'chunks.jsonl');assert saved==chunks(docs,**protocol['retrieval'][v])
        assert sha(folder/v/'chunks.jsonl')==freeze['chunks_sha256'][v]
        cmap={c['chunk_id']:c for c in saved};bydoc=defaultdict(list)
        for c in saved:bydoc[c['doc_id']].append(c)
        index=BM25(saved,**protocol['retrieval']['bm25']) if rerank else None
        for split in ['dev','holdout']:
            p=folder/v/'dev.predictions.jsonl' if split=='dev' else folder/'holdout'/f'{v}.predictions.jsonl'
            metrics_path=folder/v/'dev.metrics.json' if split=='dev' else folder/'holdout'/f'{v}.metrics.json'
            predictions=read_jsonl(p);assert [r['id'] for r in predictions]==[q['id'] for q in qs[split]]
            for q,row in zip(qs[split],predictions):
                assert len(row['hits'])<=3 and len({h['chunk_id'] for h in row['hits']})==len(row['hits'])
                hits=[cmap[h['chunk_id']] for h in row['hits']]
                score=score_query(q,hits,bydoc[q['doc_id']]);assert all(row[k]==v for k,v in score.items())
                assert row['returned_chars']==sum(len(c['text']) for c in hits)<=480
                if index:
                    expected=[{'chunk_id':c['chunk_id'],'score':s} for c,s in index.search(q['question'])]
                    assert expected==row['hits'],q['id']
            assert summarize(predictions)==json.loads(metrics_path.read_text())
            results[v,split]=predictions
    selection=json.loads((folder/'selection.json').read_text());checks=selection['checks']
    a=summarize(results['baseline','dev']);b=summarize(results['candidate','dev']);g=protocol['gate']
    assert checks=={'span_gain':b['span_hit_at3']-a['span_hit_at3']>=g['dev_min_span_hit_gain']-1e-12,'doc_recall':b['document_recall_at3']+g['dev_max_doc_recall_drop']>=a['document_recall_at3']-1e-12,'index_cost':len(read_jsonl(folder/'candidate/chunks.jsonl'))/len(read_jsonl(folder/'baseline/chunks.jsonl'))<=g['max_index_chunk_ratio']}
    assert selection['candidate_adopted']==all(checks.values())
    assert selection['paired']==paired(results['baseline','dev'],results['candidate','dev'])
    final=json.loads((folder/'holdout/summary.json').read_text())
    assert final['paired']==paired(results['baseline','holdout'],results['candidate','holdout'])
    assert final['dev_selection']==selection['selected'] and final['holdout_does_not_reselect']
    systems=json.loads(Path('reports/systems-v1/result.json').read_text());assert all(c['passed'] for c in systems['checks'])
    assert len(systems['benchmark'])==6 and len({r['documents_sha256'] for r in systems['benchmark']})==1
    print('Verified source/asset hashes, split families, raw answer offsets, all640 query-arm records, chunk budgets, gates, paired regressions and system evidence.' + (' BM25 ranks recomputed.' if rerank else ' Saved rankings only; use --rerank to execute retrieval again.'))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--rerank',action='store_true');a=p.parse_args();main(a.rerank)
