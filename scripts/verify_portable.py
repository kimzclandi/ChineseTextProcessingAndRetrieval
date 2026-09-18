"""Cross-platform reranking; frozen evidence and ordered IDs remain exact.

Only numeric BM25 scores allow rel_tol=abs_tol=1e-12 for libm rounding.
The original pre-holdout checker is preserved and runs first, unchanged.
"""
import json
import math
from pathlib import Path
from engine.common import read_jsonl
from engine.retrieval import BM25
from scripts.verify import main as verify_evidence


def compare_hits(actual, saved):
    if [h['chunk_id'] for h in actual] != [h['chunk_id'] for h in saved]:
        raise ValueError('ordered chunk IDs differ')
    differences = []
    for a, b in zip(actual, saved):
        x, y = a['score'], b['score']
        if not (math.isfinite(x) and math.isfinite(y)
                and math.isclose(x, y, rel_tol=1e-12, abs_tol=1e-12)):
            raise ValueError(f'BM25 scores differ: {x!r} versus {y!r}')
        differences.append(abs(x-y))
    return differences


def main():
    verify_evidence()
    folder = Path('reports/retrieval-v1')
    protocol = json.loads(Path('configs/protocol.json').read_text())
    differences = []
    queries = 0
    for variant in ['baseline', 'candidate']:
        index = BM25(read_jsonl(folder/variant/'chunks.jsonl'), **protocol['retrieval']['bm25'])
        for split in ['dev', 'holdout']:
            path = folder/variant/'dev.predictions.jsonl' if split == 'dev' else folder/'holdout'/f'{variant}.predictions.jsonl'
            for q, row in zip(read_jsonl(f'data/source-v1/{split}.jsonl'), read_jsonl(path)):
                actual = [{'chunk_id': c['chunk_id'], 'score': s} for c, s in index.search(q['question'])]
                try:
                    differences.extend(compare_hits(actual, row['hits']))
                except ValueError as exc:
                    raise ValueError(f'{variant}/{split}/{q["id"]}: {exc}') from exc
                queries += 1
    print(json.dumps({'query_arm_count': queries, 'ordered_rankings': 'exact',
                      'scores_compared': len(differences),
                      'scores_with_rounding_difference': sum(d > 0 for d in differences),
                      'max_absolute_score_difference': max(differences, default=0),
                      'score_rel_tol': 1e-12, 'score_abs_tol': 1e-12}, sort_keys=True))


if __name__ == '__main__':
    main()
