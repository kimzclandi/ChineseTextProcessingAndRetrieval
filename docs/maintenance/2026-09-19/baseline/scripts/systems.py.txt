"""Run real fault injection and serial/Ray measurement. Synthetic fixtures are separate."""
import json
import os
from pathlib import Path
import shutil
import sqlite3
import statistics
import subprocess
import sys
import time
import ray
from engine.common import digest,read_jsonl,sha,write_json
from engine.pipeline import run,registered_snapshot,connect,verify_snapshot

ROOT=Path(__file__).resolve().parents[1]


def check(name,condition,details):
    if not condition:raise AssertionError(name)
    return {'name':name,'passed':True,'details':details}


def main():
    os.chdir(ROOT);out=ROOT/'reports/systems-v1';out.mkdir(exist_ok=False)
    work=ROOT/'work/systems-v1';work.mkdir(exist_ok=False)
    records=read_jsonl('data/source-v1/source-records.jsonl')
    # Fixtures use reserved example.invalid and fictional identifiers; not real PII.
    fixtures=[{'source_id':f'fixture:{i}','title':f'虚构文章{i}','text':f'虚构系统测试记录{i}。队列顺序为先进先出。'} for i in range(100)]
    fixtures += [dict(fixtures[0],source_id='fixture:duplicate'),{'source_id':'fixture:email','title':'虚构','text':'联系 test@example.invalid'}, {'source_id':'fixture:empty','title':'虚构','text':''}, {'source_id':'fixture:schema','title':'虚构','text':None}]
    checks=[]
    start=time.perf_counter();ray.init(num_cpus=4,include_dashboard=False,log_to_driver=False,_temp_dir='/tmp/ced-ray-systems');startup=time.perf_counter()-start
    try:
        marker=work/'worker-exited';fault=run(fixtures,work/'fault-lake','ray',fault_marker=marker)
        clean=run(fixtures,work/'clean-lake','serial')
        f=registered_snapshot(work/'fault-lake',fault['version']);c=registered_snapshot(work/'clean-lake',clean['version'])
        checks.append(check('real_worker_exit_retried',marker.exists() and sha(f/'documents.jsonl')==sha(c/'documents.jsonl'),{'exit_code':73,'fault_marker':marker.read_text(),'fault_version':fault['version'],'clean_version':clean['version'],'counts':verify_snapshot(f)['counts']}))
        before=sha(f/'manifest.json');again=run(fixtures,work/'fault-lake','ray')
        checks.append(check('duplicate_delivery_idempotent',again['reused_snapshot'] and sha(f/'manifest.json')==before,again))
        # Real subprocess exits after staged shard cache, before version visibility.
        from engine.common import write_jsonl
        write_jsonl(work/'fixtures.jsonl',fixtures)
        code='''import os\nfrom engine.common import read_jsonl\nfrom engine.pipeline import run\ntry: run(read_jsonl("work/systems-v1/fixtures.jsonl"),"work/systems-v1/resume-lake",fail_after=2)\nexcept RuntimeError: os._exit(74)\n'''
        child=subprocess.run([sys.executable,'-c',code],cwd=ROOT)
        lake=work/'resume-lake'
        visible_before=len(list((lake/'versions').glob('*'))) if (lake/'versions').exists() else 0
        recovered=run(fixtures,lake)
        recovered_path=registered_snapshot(lake,recovered['version'])
        checks.append(check('driver_exit_resume',child.returncode==74 and visible_before==0 and recovered['resumed_shards']>=2 and sha(recovered_path/'documents.jsonl')==sha(c/'documents.jsonl'),{'child_exit':child.returncode,'visible_before_resume':visible_before,'recovery':recovered}))
        more=fixtures+[{'source_id':'fixture:new','title':'新增虚构','text':'增量输入是一条新记录。'}]
        inc=run(more,lake,parent=recovered['version']);full=run(more,work/'full-append')
        ip=registered_snapshot(lake,inc['version']);fp=registered_snapshot(work/'full-append',full['version'])
        checks.append(check('incremental_equal_full_rebuild',inc['resumed_shards']>0 and sha(ip/'documents.jsonl')==sha(fp/'documents.jsonl'),{'incremental':inc,'full':full,'parent_preserved':sha(recovered_path/'documents.jsonl')==sha(c/'documents.jsonl')}))
        tamper=work/'tamper';shutil.copytree(c,tamper)
        with (tamper/'documents.jsonl').open('a') as h:h.write('{}\n')
        detected=False
        try:verify_snapshot(tamper)
        except ValueError:detected=True
        checks.append(check('tamper_rejected',detected,{'corruption':'append invalid row to copied snapshot'}))
        # A simulated post-rename/pre-catalog crash: remove registration only in dedicated fixture DB.
        with connect(work/'clean-lake') as con:con.execute('DELETE FROM versions');con.execute('DELETE FROM lineage')
        invisible=False
        try:registered_snapshot(work/'clean-lake',clean['version'])
        except KeyError:invisible=True
        registered=run(fixtures,work/'clean-lake')
        checks.append(check('orphan_publish_recovery',invisible and registered['reused_snapshot'],{'simulation':'catalog registration removed from fixture; not a hardware power-loss test'}))
        runs=[]
        for n,executor in enumerate(['serial','ray','ray','serial','serial','ray']):
            t=time.perf_counter();r=run(records,work/f'benchmark-{n}-{executor}',executor);wall=time.perf_counter()-t
            snapshot=registered_snapshot(work/f'benchmark-{n}-{executor}',r['version'])
            runs.append({'order':n+1,'executor':executor,'wall_seconds':wall,'rows_per_second':len(records)/wall,'documents_sha256':sha(snapshot/'documents.jsonl'),'pipeline':r})
        if len({r['documents_sha256'] for r in runs})!=1:raise ValueError('Benchmark output mismatch')
        write_json(out/'result.json',{'checks':checks,'ray_startup_seconds':startup,'benchmark':runs,'median_rows_per_second':{e:statistics.median(r['rows_per_second'] for r in runs if r['executor']==e) for e in ['serial','ray']},'scope':'single-host warm runtime, end-to-end local pipeline incl disk writes; Ray init separately reported. No multi-node, streaming, memory or model training benchmark.','synthetic_fixture_records':len(fixtures),'real_source_records':len(records),'ray_version':ray.__version__})
        print(json.dumps({'checks':[x['name'] for x in checks],'runs':len(runs)},indent=2))
    finally:ray.shutdown()

if __name__=='__main__':main()
