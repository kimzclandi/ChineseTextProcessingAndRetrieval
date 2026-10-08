"""Reject protocol drift that leaves timing medians and coverage unchanged."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from scripts.benchmark_prepared_bm25 import load, summarize


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / 'reports/bm25-exact-performance-v1'


@pytest.fixture
def saved_run():
    spec = json.loads((ARCHIVE / 'protocol.json').read_text())
    records = json.loads((ARCHIVE / 'timings.json').read_text())
    query_ids = [q['id'] for split in spec['splits']
                 for q in load(ROOT / f'data/source-v1/{split}.jsonl')]
    return records, spec, query_ids


def test_original_archive_still_passes_without_changing_summary(saved_run):
    records, spec, query_ids = saved_run
    assert summarize(records, spec, query_ids) == json.loads(
        (ARCHIVE / 'summary.json').read_text())


@pytest.mark.parametrize('both_arms', [False, True])
def test_reordered_queries_cannot_claim_frozen_paired_schedule(saved_run, both_arms):
    records, spec, query_ids = saved_run
    records[0]['queries'].reverse()
    if both_arms:
        # Even matching query orders can violate the predeclared seeded order.
        records[1]['queries'].reverse()
    with pytest.raises(ValueError, match='query order'):
        summarize(records, spec, query_ids)


def test_declared_arm_order_must_match_execution_order(saved_run):
    records, spec, query_ids = saved_run
    records[0]['arm_order'].reverse()
    with pytest.raises(ValueError, match='arm order'):
        summarize(records, spec, query_ids)


def test_swapping_executed_arms_cannot_claim_same_protocol(saved_run):
    records, spec, query_ids = saved_run
    records[0], records[1] = records[1], records[0]
    with pytest.raises(ValueError, match='timing order'):
        summarize(records, spec, query_ids)


def test_changed_seed_is_detected_even_with_unchanged_timing_cells(saved_run):
    records, spec, query_ids = saved_run
    spec['seed'] += 1
    with pytest.raises(ValueError, match='order'):
        summarize(records, spec, query_ids)


@pytest.mark.parametrize('invalid_round', [False, 0.0])
def test_round_identifiers_are_integers_not_numeric_aliases(saved_run, invalid_round):
    records, spec, query_ids = saved_run
    records[0]['round'] = invalid_round
    with pytest.raises(ValueError, match='round'):
        summarize(records, spec, query_ids)


def test_duplicate_query_identity_is_not_a_valid_paired_population(saved_run):
    records, spec, query_ids = saved_run
    query_ids.append(query_ids[0])
    for row in records:
        duplicate = next(sample for sample in row['queries']
                         if sample['id'] == query_ids[0])
        row['queries'].append(deepcopy(duplicate))
    with pytest.raises(ValueError, match='Duplicate query'):
        summarize(records, spec, query_ids)
