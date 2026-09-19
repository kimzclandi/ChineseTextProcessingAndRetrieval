import json
import pytest
from engine.pipeline import run, registered_snapshot


def record(i, text=None):
    return {'source_id': str(i), 'title': 'title', 'text': text or f'text {i}'}


def test_parent_must_exist(tmp_path):
    with pytest.raises((KeyError, ValueError), match='parent|Parent|published'):
        run([record(1)], tmp_path, parent='missing')


@pytest.mark.parametrize('child', [[record(2)], [record(1, 'changed')]])
def test_parent_prevents_removal_or_replacement(tmp_path, child):
    first = run([record(1)], tmp_path)
    with pytest.raises(ValueError, match='append-only'):
        run(child, tmp_path, parent=first['version'])
    assert registered_snapshot(tmp_path, first['version']).exists()


def test_parent_is_part_of_snapshot_identity(tmp_path):
    first = run([record(1)], tmp_path)
    independent = run([record(1), record(2)], tmp_path)
    child = run([record(1), record(2)], tmp_path, parent=first['version'])
    assert child['version'] != independent['version']
    path = registered_snapshot(tmp_path, child['version'])
    assert json.loads((path / 'manifest.json').read_text())['parent'] == first['version']
    assert run([record(2), record(1)], tmp_path, parent=first['version'])['reused_snapshot']


def test_quarantined_and_duplicate_inputs_are_also_append_only(tmp_path):
    rows = [record(1), record(1), {'source_id': 'bad', 'title': '', 'text': ''}]
    parent = run(rows, tmp_path)['version']
    for child in (rows[:-1], rows[1:]):
        with pytest.raises(ValueError, match='append-only'):
            run(child, tmp_path, parent=parent)


def test_repeated_source_has_one_lineage_edge_in_both_stores(tmp_path):
    from contextlib import closing
    from engine.common import read_jsonl
    from engine.pipeline import connect

    result = run([record(1), record(1)], tmp_path)
    snapshot = registered_snapshot(tmp_path, result['version'])
    lineage = read_jsonl(snapshot / 'lineage.jsonl')
    with closing(connect(tmp_path)) as con:
        count = con.execute('SELECT count(*) FROM lineage WHERE version=?', (result['version'],)).fetchone()[0]
    assert len(lineage) == count == 1
    assert json.loads((snapshot / 'manifest.json').read_text())['counts']['duplicate_rows'] == 1
