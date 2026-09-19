"""Rebuild serial assets and dev retrieval with portable BM25 score comparison.

The original reproduce.py remains frozen. IDs, metrics and asset bytes stay
exact; only finite BM25 scores use the existing 1e-12 rounding tolerance.
"""
import argparse
import json
from pathlib import Path
from engine.common import read_jsonl, sha, write_json, write_jsonl
from engine.pipeline import run, registered_snapshot
from engine.retrieval import BM25, chunks, evaluate
from scripts.verify_portable import compare_hits

ROOT = Path(__file__).resolve().parents[1]


def compare_predictions(actual, saved):
    if [row['id'] for row in actual] != [row['id'] for row in saved]:
        raise ValueError('Prediction IDs or coverage differ')
    for row, reference in zip(actual, saved):
        compare_hits(row['hits'], reference['hits'])
        # evaluate records query timing, which is expected to change on rerun.
        excluded = {'hits', 'latency_seconds'}
        if {k: v for k, v in row.items() if k not in excluded} != {
                k: v for k, v in reference.items() if k not in excluded}:
            raise ValueError('Retrieval metrics differ: ' + row['id'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--limit', type=int, default=8)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / 'work') or output == ROOT / 'work':
        parser.error('Use a new work/ subdirectory')
    if not 1 <= args.limit <= 160:
        parser.error('limit must be 1..160 dev queries')
    output.mkdir(parents=True, exist_ok=False)
    result = run(read_jsonl(ROOT / 'data/source-v1/source-records.jsonl'), output / 'lake')
    snapshot = registered_snapshot(output / 'lake', result['version'])
    equality = {name: sha(snapshot / name) == sha(ROOT / 'data/asset-v1' / name)
                for name in ('documents.jsonl', 'lineage.jsonl', 'quarantine.jsonl', 'documents.parquet')}
    if not all(equality.values()):
        raise ValueError('Rebuilt asset differs')
    docs = read_jsonl(snapshot / 'documents.jsonl')
    queries = read_jsonl(ROOT / 'data/source-v1/dev.jsonl')[:args.limit]
    protocol = json.loads((ROOT / 'configs/protocol.json').read_text())
    metrics = {}
    for variant in ('baseline', 'candidate'):
        generated = chunks(docs, **protocol['retrieval'][variant])
        frozen = read_jsonl(ROOT / f'reports/retrieval-v1/{variant}/chunks.jsonl')
        if generated != frozen:
            raise ValueError('Chunk rebuild differs')
        metrics[variant], predictions = evaluate(BM25(generated, **protocol['retrieval']['bm25']), queries)
        reference = read_jsonl(ROOT / f'reports/retrieval-v1/{variant}/dev.predictions.jsonl')[:args.limit]
        compare_predictions(predictions, reference)
        write_jsonl(output / f'{variant}.predictions.jsonl', predictions)
    write_json(output / 'result.json', {'pipeline': result, 'asset_byte_equality': equality,
               'dev_queries': args.limit, 'metrics': metrics,
               'scope': 'Actual serial asset rebuild and BM25 execution; no Ray or model inference',
               'score_rel_tol': 1e-12, 'score_abs_tol': 1e-12})
    print('Rebuilt all assets; dev IDs, rankings and metrics matched with portable BM25 score tolerance.')


if __name__ == '__main__':
    main()
