import pytest
from scripts.verify_portable import compare_hits


def hits(score=1.0, chunk='a'):
    return [{'chunk_id': chunk, 'score': score}]


def test_libm_rounding_only():
    assert compare_hits(hits(1.0 + 2e-15), hits())[0] > 0


def test_different_rank_rejected():
    with pytest.raises(ValueError, match='ordered'):
        compare_hits(hits(chunk='b'), hits())


def test_material_score_change_rejected():
    with pytest.raises(ValueError, match='scores'):
        compare_hits(hits(1.001), hits())


@pytest.mark.parametrize('score', [float('nan'), float('inf'), -float('inf')])
def test_nonfinite_rejected(score):
    with pytest.raises(ValueError, match='scores'):
        compare_hits(hits(score), hits(score))
