"""Isolated serial rebuild of all assets plus eight development-query checks by default."""
import argparse
import json
from pathlib import Path
from engine.common import read_jsonl,sha,write_json,write_jsonl
from engine.pipeline import run,registered_snapshot
from engine.retrieval import BM25,chunks,evaluate

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--limit',type=int,default=8);a=p.parse_args()
    output=a.output.resolve()
    if not output.is_relative_to(ROOT/'work') or output==ROOT/'work':p.error('Use a new work/ subdirectory')
    if not 1<=a.limit<=160:p.error('limit must be1..160 dev queries')
    output.mkdir(parents=True,exist_ok=False)
    result=run(read_jsonl(ROOT/'data/source-v1/source-records.jsonl'),output/'lake')
    snapshot=registered_snapshot(output/'lake',result['version'])
    equality={name:sha(snapshot/name)==sha(ROOT/'data/asset-v1'/name) for name in ('documents.jsonl','lineage.jsonl','quarantine.jsonl','documents.parquet')}
    if not all(equality.values()):raise ValueError('Rebuilt asset differs')
    docs=read_jsonl(snapshot/'documents.jsonl');queries=read_jsonl(ROOT/'data/source-v1/dev.jsonl')[:a.limit]
    protocol=json.loads((ROOT/'configs/protocol.json').read_text());metrics={}
    for v in ['baseline','candidate']:
        generated=chunks(docs,**protocol['retrieval'][v]);frozen=read_jsonl(ROOT/f'reports/retrieval-v1/{v}/chunks.jsonl')
        if generated!=frozen:raise ValueError('Chunk rebuild differs')
        metrics[v],predictions=evaluate(BM25(generated,**protocol['retrieval']['bm25']),queries)
        reference=read_jsonl(ROOT/f'reports/retrieval-v1/{v}/dev.predictions.jsonl')[:a.limit]
        if any(a['hits']!=b['hits'] or a['span_hit']!=b['span_hit'] for a,b in zip(predictions,reference)):raise ValueError('Retrieval rerun differs')
        write_jsonl(output/f'{v}.predictions.jsonl',predictions)
    write_json(output/'result.json',{'pipeline':result,'asset_byte_equality':equality,'dev_queries':a.limit,'metrics':metrics,'scope':'Actual serial rebuild and BM25 execution, not model inference; no holdout tuning'})
    print('Rebuilt all assets; both variants matched saved development rankings.')

if __name__=='__main__':main()
