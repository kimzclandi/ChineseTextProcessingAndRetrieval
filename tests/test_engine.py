import json
from pathlib import Path
import pytest
from engine.common import digest,read_jsonl,sha
from engine.quality import process_batch,consolidate
from engine.pipeline import run,registered_snapshot,verify_snapshot,connect
from engine.dataset import families
from engine.retrieval import chunks,BM25,score_query,paired,summarize


def record(i=0,text='甲乙丙丁戊己庚辛壬癸'):
    return {'source_id':str(i),'title':'文章'+str(i),'text':text}


@pytest.mark.parametrize('bad',[None,{}, {'source_id':'a','title':'t','text':None},record(text=''),record(text=' '),record(text='邮箱test@example.invalid'),record(text='虚构手机号13800000000')])
def test_quarantine_without_raw_contact(bad):
    result=process_batch([bad])[0]
    assert result['status']=='quarantine' and 'text' not in result
    assert 'example.invalid' not in json.dumps(result)


def test_offsets_are_preserved():
    text='  ＡＢＣ\n中文 e\u0301  '
    result=process_batch([record(text=text)])[0]
    assert result['text']==text


def test_dedup_keeps_lineage():
    docs,rejected,lineage=consolidate(process_batch([record(0),record(1)]))
    assert len(docs)==1 and len(lineage)==2 and not rejected


def test_source_conflict_blocks_publish(tmp_path):
    with pytest.raises(ValueError,match='Conflicting'):
        run([record(0),record(0,'另一个文本')],tmp_path)
    assert not (tmp_path/'versions').exists()


def test_idempotent_order_invariant(tmp_path):
    rows=[record(i,str(i)+'文本') for i in range(8)]
    a=run(rows,tmp_path);b=run(rows[::-1],tmp_path)
    assert a['version']==b['version'] and b['reused_snapshot']
    with connect(tmp_path) as con:assert con.execute('SELECT count(*) FROM versions').fetchone()[0]==1


def test_interrupted_not_visible_and_resume(tmp_path):
    rows=[record(i,str(i)+'文本') for i in range(8)]
    with pytest.raises(RuntimeError):run(rows,tmp_path,fail_after=2)
    assert not (tmp_path/'versions').exists()
    result=run(rows,tmp_path)
    assert result['resumed_shards']>=2
    assert verify_snapshot(registered_snapshot(tmp_path,result['version']))['counts']['documents']==8


def test_corrupt_checkpoint_blocks_resume(tmp_path):
    rows=[record(i,str(i)+'文本') for i in range(8)]
    with pytest.raises(RuntimeError):run(rows,tmp_path,fail_after=1)
    f=next((tmp_path/'shard-cache').glob('*.json'));d=json.loads(f.read_text());d['rows'][0]['text']='tampered';f.write_text(json.dumps(d))
    with pytest.raises(ValueError,match='Shard checksum'):run(rows,tmp_path)


def test_corrupt_published_data_blocks_reuse(tmp_path):
    rows=[record()];r=run(rows,tmp_path);p=registered_snapshot(tmp_path,r['version'])
    (p/'documents.jsonl').write_text('{}\n')
    with pytest.raises(ValueError,match='checksum'):run(rows,tmp_path)


def test_catalog_manifest_tampering_detected(tmp_path):
    r=run([record()],tmp_path);p=registered_snapshot(tmp_path,r['version'])
    manifest=json.loads((p/'manifest.json').read_text());manifest['counts']['documents']=100
    (p/'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='manifest hash'):registered_snapshot(tmp_path,r['version'])


def test_append_reuses_and_preserves_parent(tmp_path):
    rows=[record(i,str(i)+'文本') for i in range(40)]
    a=run(rows,tmp_path);ap=registered_snapshot(tmp_path,a['version']);h=sha(ap/'documents.jsonl')
    b=run(rows+[record(100,'新增记录')],tmp_path,parent=a['version'])
    assert b['resumed_shards']>0 and sha(ap/'documents.jsonl')==h and b['version']!=a['version']


def test_short_unrelated_not_near():
    docs,_,lin=consolidate(process_batch([record(0,'甲'),record(1,'乙')]))
    f,a=families(docs,lin)
    assert len(set(f.values()))==2


def test_same_title_grouped_before_split():
    rows=[record(0,'甲乙丙丁戊己'),dict(record(1,'完全不同的内容'),title='文章0')]
    docs,_,lin=consolidate(process_batch(rows));f,_=families(docs,lin)
    assert len(set(f.values()))==1


def test_chunk_boundary_failure_and_repair():
    docs=[{'doc_id':'d','text':'0123456789abcdefghij'}]
    q={'id':'q','doc_id':'d','answers':[{'text':'89ab','start':8}]}
    base=chunks(docs,10,10);candidate=chunks(docs,10,6)
    assert not score_query(q,base,base)['oracle_span']
    assert score_query(q,candidate,candidate)['span_hit']


def test_answer_in_wrong_source_is_not_support():
    c=[{'doc_id':'other','start':0,'end':10,'text':'abcdefghij'}]
    q={'id':'q','doc_id':'correct','answers':[{'text':'ab','start':0}]}
    assert score_query(q,c,c)['span_hit']==0


def test_long_answer_stays_failure():
    docs=[{'doc_id':'d','text':'a'*400}];c=chunks(docs,160,96)
    q={'id':'q','doc_id':'d','answers':[{'text':'a'*200,'start':0}]}
    assert not score_query(q,c,c)['oracle_span']


def test_empty_query_no_fabricated_hit():
    c=chunks([{'doc_id':'d','text':'测试文本'}]);assert BM25(c).search('！？')==[]


def test_bm25_query_and_document_only():
    rows=chunks([{'doc_id':'a','text':'苹果 水果'},{'doc_id':'b','text':'星球 宇宙'}])
    assert BM25(rows).search('苹果')[0][0]['doc_id']=='a'


def test_paired_rejects_missing_ids():
    with pytest.raises(ValueError):paired([{'id':'a','span_hit':0}],[{'id':'b','span_hit':1}])


def test_paired_keeps_regression():
    a=[{'id':'a','span_hit':0},{'id':'b','span_hit':1}];b=[{'id':'a','span_hit':1},{'id':'b','span_hit':0}]
    assert paired(a,b)=={'fixes':['a'],'regressions':['b']}


def test_empty_input_snapshot(tmp_path):
    r=run([],tmp_path);p=registered_snapshot(tmp_path,r['version'])
    assert read_jsonl(p/'documents.jsonl')==[]
