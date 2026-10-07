import random
import pytest
from engine.retrieval import BM25
from engine.prepared_bm25 import PreparedBM25


def test_exact_scores_order_and_ties_under_random_corpus():
    rng = random.Random(20261008)
    rows = [dict(chunk_id=f'{i:03}',text=''.join(rng.choice('中文ABC１２！') for _ in range(rng.randrange(25)))) for i in range(70)]
    rows += [dict(chunk_id='tie-z',text='相同'),dict(chunk_id='tie-a',text='相同')]
    for k1,b in [(1.2,.75),(.5,0),(2.,1.)]:
        ref, candidate = BM25(rows,k1,b), PreparedBM25(rows,k1,b)
        for query in ['', '！！', '相同', 'absent', 'ＡBC', '中中文'] + [''.join(rng.choice('中文ABC１２') for _ in range(8)) for _ in range(30)]:
            for k in [0,1,3,100]:
                assert candidate.search(query,k) == ref.search(query,k)


def test_empty_corpus_and_invalid_k():
    assert PreparedBM25([]).search('查询') == []
    for k in [True,-1,1.5]:
        with pytest.raises(ValueError): PreparedBM25([]).search('x',k)
