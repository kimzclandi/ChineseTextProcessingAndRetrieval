"""Integration assertions over measured evidence; no Ray service or external access."""
import json
from pathlib import Path
import statistics
from engine.common import read_jsonl

ROOT=Path(__file__).resolve().parents[1]


def systems():
    return json.loads((ROOT/'reports/systems-v1/result.json').read_text())


def test_saved_benchmark_arithmetic_and_outputs():
    result=systems();runs=result['benchmark']
    assert [r['executor'] for r in runs]==['serial','ray','ray','serial','serial','ray']
    assert len({r['documents_sha256'] for r in runs})==1
    for r in runs:
        assert r['rows_per_second']==result['real_source_records']/r['wall_seconds']
        assert r['pipeline']['processed_shards']==256 and not r['pipeline']['reused_snapshot']
    for e in ['serial','ray']:
        assert statistics.median(r['rows_per_second'] for r in runs if r['executor']==e)==result['median_rows_per_second'][e]


def test_saved_fault_trace_has_exits_and_resume():
    checks={c['name']:c['details'] for c in systems()['checks']}
    fault=checks['real_worker_exit_retried']
    assert fault['exit_code']==73 and fault['fault_version']==fault['clean_version']
    assert fault['counts']=={'input':104,'accepted_rows':101,'documents':100,'quarantined':3,'duplicate_rows':1}
    recovery=checks['driver_exit_resume']
    assert recovery['child_exit']==74 and recovery['visible_before_resume']==0
    assert recovery['recovery']['resumed_shards']==2
    log=(ROOT/'reports/execution/systems.log').read_text()
    assert 'task will be retried' in log and 'worker died' in log.lower()


def test_incremental_evidence_preserves_parent_and_reuses_shards():
    case=next(c['details'] for c in systems()['checks'] if c['name']=='incremental_equal_full_rebuild')
    assert case['parent_preserved']
    assert case['incremental']['version']==case['full']['version']
    assert case['incremental']['processed_shards']==1 and case['incremental']['resumed_shards']==84
    assert case['full']['processed_shards']==85


def test_real_lineage_covers_every_input():
    records=read_jsonl(ROOT/'data/source-v1/source-records.jsonl')
    lineage=read_jsonl(ROOT/'data/asset-v1/lineage.jsonl')
    docs=read_jsonl(ROOT/'data/asset-v1/documents.jsonl')
    assert {r['source_id'] for r in records}=={r['source_id'] for r in lineage}
    assert {r['doc_id'] for r in docs}=={r['doc_id'] for r in lineage}
    assert len(records)==len(docs)==len(lineage)==2403


def test_holdout_report_uses_frozen_dev_choice():
    f=ROOT/'reports/retrieval-v1'
    selection=json.loads((f/'selection.json').read_text());holdout=json.loads((f/'holdout/summary.json').read_text())
    assert holdout['dev_selection']==selection['selected']
    assert holdout['holdout_does_not_reselect'] is True
    for v in ['baseline','candidate']:
        assert holdout['metrics'][v]==json.loads((f/f'holdout/{v}.metrics.json').read_text())
