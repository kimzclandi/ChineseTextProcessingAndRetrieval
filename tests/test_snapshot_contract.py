import json
import pytest
from engine.common import sha
from engine.pipeline import run,verify_snapshot,registered_snapshot,connect
from contextlib import closing

def snapshot(tmp_path):
    result=run([{'source_id':'a','title':'title','text':'test text'}],tmp_path)
    return registered_snapshot(tmp_path,result['version'])

@pytest.mark.parametrize('change',['missing_entry','extra_file','symlink','wrong_version'])
def test_incomplete_or_misdirected_snapshot_rejected(tmp_path,change):
    folder=snapshot(tmp_path);p=folder/'manifest.json';m=json.loads(p.read_text())
    if change=='missing_entry':del m['files']['documents.jsonl']
    if change=='extra_file':(folder/'unexpected.json').write_text('{}')
    if change=='symlink':
        target=tmp_path/'outside.jsonl';target.write_bytes((folder/'documents.jsonl').read_bytes());(folder/'documents.jsonl').unlink();(folder/'documents.jsonl').symlink_to(target)
    if change=='wrong_version':m['version']='0'*24
    p.write_text(json.dumps(m))
    with pytest.raises(ValueError):verify_snapshot(folder)

def test_corrupt_unregistered_snapshot_is_not_registered(tmp_path):
    folder=snapshot(tmp_path);version=folder.name
    with closing(connect(tmp_path)) as con,con:
        con.execute('DELETE FROM lineage WHERE version=?',(version,));con.execute('DELETE FROM versions WHERE version=?',(version,))
    (folder/'untracked.txt').write_text('incomplete recovered content')
    with pytest.raises(ValueError):run([{'source_id':'a','title':'title','text':'test text'}],tmp_path)
    with closing(connect(tmp_path)) as con:assert con.execute('SELECT count(*) FROM versions').fetchone()[0]==0
