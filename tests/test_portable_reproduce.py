from copy import deepcopy
import pytest
from scripts.reproduce_portable import compare_predictions


def prediction():
    return {'id': 'q1', 'hits': [{'chunk_id': 'c1', 'score': 1.0}],
            'span_hit': 1, 'document_hit': 1, 'returned_chars': 160,
            'latency_seconds': 0.001}


def test_rounding_and_runtime_do_not_change_reproduction():
    saved = prediction()
    actual = deepcopy(saved)
    actual['hits'][0]['score'] += 2e-15
    actual['latency_seconds'] = 0.123
    compare_predictions([actual], [saved])


@pytest.mark.parametrize('field,value', [('id', 'other'), ('span_hit', 0),
                                         ('document_hit', 0), ('returned_chars', 159)])
def test_identity_and_metrics_remain_exact(field, value):
    saved = prediction()
    actual = deepcopy(saved)
    actual[field] = value
    with pytest.raises(ValueError):
        compare_predictions([actual], [saved])


def test_missing_prediction_is_rejected():
    with pytest.raises(ValueError, match='coverage'):
        compare_predictions([], [prediction()])


@pytest.mark.parametrize('score', [float('nan'), float('inf'), 1.01])
def test_nonfinite_or_material_score_change_is_rejected(score):
    saved = prediction()
    actual = deepcopy(saved)
    actual['hits'][0]['score'] = score
    with pytest.raises(ValueError, match='scores'):
        compare_predictions([actual], [saved])


def test_ranking_change_is_rejected():
    saved = prediction()
    actual = deepcopy(saved)
    actual['hits'][0]['chunk_id'] = 'c2'
    with pytest.raises(ValueError, match='ordered'):
        compare_predictions([actual], [saved])
