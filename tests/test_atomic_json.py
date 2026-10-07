"""Fault injection uses synthetic files, not CMRC benchmark samples."""
import json
from concurrent.futures import ThreadPoolExecutor
import pytest
from engine.common import atomic_json

@pytest.mark.parametrize('kind',['symlink','hardlink'])
def test_stale_temp_cannot_overwrite_another_file(tmp_path,kind):
    victim=tmp_path/'victim';victim.write_text('keep')
    stale=tmp_path/'state.json.tmp'
    if kind=='symlink':stale.symlink_to(victim)
    else:stale.hardlink_to(victim)
    atomic_json(tmp_path/'state.json',{'ok':True})
    assert victim.read_text()=='keep'
    assert json.loads((tmp_path/'state.json').read_text())=={'ok':True}

@pytest.mark.parametrize('failure',['serialize','replace'])
def test_failure_preserves_target_and_removes_own_temp(tmp_path,monkeypatch,failure):
    import engine.common as common
    target=tmp_path/'state.json';target.write_text('{"old":true}')
    if failure=='replace':
        def fail(*args):raise OSError('injected replace failure')
        monkeypatch.setattr(common.os,'replace',fail)
    with pytest.raises((TypeError,OSError)):
        atomic_json(target,object() if failure=='serialize' else {'new':True})
    assert json.loads(target.read_text())=={'old':True}
    assert sorted(p.name for p in tmp_path.iterdir())==['state.json']

def test_concurrent_writers_publish_one_complete_value(tmp_path):
    target=tmp_path/'state.json'
    values=[{'writer':i,'body':str(i)*1000} for i in range(20)]
    with ThreadPoolExecutor(max_workers=8) as pool:list(pool.map(lambda v:atomic_json(target,v),values))
    assert json.loads(target.read_text()) in values
    assert len(list(tmp_path.iterdir()))==1
