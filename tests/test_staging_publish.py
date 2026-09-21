"""Synthetic interrupted-stage faults must never become registered snapshots."""
from contextlib import closing
import pytest
from engine.pipeline import run, connect, registered_snapshot

ROWS = [{'source_id': 'a', 'title': 'fixture', 'text': 'synthetic text'}]

@pytest.mark.parametrize('fault', ['extra_file', 'symlink', 'directory'])
def test_staging_fault_is_rejected_before_publish(tmp_path, fault):
    with pytest.raises(RuntimeError):
        run(ROWS, tmp_path, fail_after=1)
    stage = next((tmp_path / 'staging').iterdir())
    outside = tmp_path / 'outside.txt'
    outside.write_text('must remain unchanged')
    if fault == 'extra_file':
        (stage / 'unexpected.txt').write_text('unexpected')
    elif fault == 'symlink':
        (stage / 'documents.jsonl').symlink_to(outside)
    else:
        (stage / 'documents.jsonl').mkdir()
    with pytest.raises(ValueError, match='Staging'):
        run(ROWS, tmp_path)
    assert outside.read_text() == 'must remain unchanged'
    with closing(connect(tmp_path)) as con:
        assert con.execute('SELECT count(*) FROM versions').fetchone()[0] == 0
    assert not (tmp_path / 'versions').exists()
    for path in stage.iterdir():
        if path.is_dir(): path.rmdir()
        else: path.unlink()
    result = run(ROWS, tmp_path)
    assert result['resumed_shards'] == 1
    assert registered_snapshot(tmp_path, result['version']).is_dir()
