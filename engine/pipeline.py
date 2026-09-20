"""Single-host resumable batch asset commits using immutable snapshots + SQLite catalog.

Local shared filesystem and exclusive writer lock are required. Not a streaming
exactly-once claim, multi-host transaction, or object-store commit protocol.
"""
import argparse
from collections import Counter
from contextlib import closing
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import time
from .common import atomic_json, digest, read_jsonl, sha, write_json, write_jsonl
from .quality import consolidate, process_batch


def operator_hash():
    return digest({name:sha(Path(__file__).parent/name) for name in ('common.py','quality.py','pipeline.py')})


def worker(batch, fault_marker=None):
    if fault_marker:
        try:
            fd=os.open(fault_marker, os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        except FileExistsError:
            pass
        else:
            os.write(fd,b'worker intentionally exited once\n');os.close(fd)
            os._exit(73)
    return process_batch(batch)


def connect(lake):
    con=sqlite3.connect(lake/'catalog.sqlite')
    con.execute('PRAGMA journal_mode=WAL')
    con.execute('CREATE TABLE IF NOT EXISTS versions (version TEXT PRIMARY KEY, manifest_sha TEXT NOT NULL, path TEXT NOT NULL)')
    con.execute('CREATE TABLE IF NOT EXISTS lineage (version TEXT, doc_id TEXT, source_id TEXT, PRIMARY KEY(version,doc_id,source_id))')
    return con


def verify_snapshot(folder):
    folder=Path(folder)
    if (folder/'manifest.json').is_symlink():raise ValueError('Snapshot manifest must be a regular file')
    manifest=json.loads((folder/'manifest.json').read_text())
    files=manifest.get('files')
    required={'documents.jsonl','documents.parquet','quarantine.jsonl','lineage.jsonl'}
    allowed=required|{'input-record-hashes.json'}
    if not isinstance(files,dict) or not required<=set(files)<=allowed:
        raise ValueError('Snapshot file contract mismatch')
    actual={p.name for p in folder.iterdir() if p.name!='manifest.json'}
    if actual!=set(files):raise ValueError('Snapshot file set mismatch')
    if not isinstance(manifest.get('identity'),dict) or manifest.get('version')!=digest(manifest['identity'])[:24]:
        raise ValueError('Snapshot version identity mismatch')
    for name,h in files.items():
        path=folder/name
        if Path(name).name!=name or path.is_symlink() or not path.is_file() or sha(path)!=h:
            raise ValueError('Snapshot checksum mismatch: '+name)
    return manifest


def registered_snapshot(lake, version):
    with closing(connect(Path(lake))) as con:
        row=con.execute('SELECT manifest_sha,path FROM versions WHERE version=?',(version,)).fetchone()
    if row is None:raise KeyError('Version not published')
    path=Path(lake)/row[1]
    if sha(path/'manifest.json')!=row[0]:raise ValueError('Catalog manifest hash mismatch')
    verify_snapshot(path)
    return path


def run(records, lake, executor='serial', batch_size=64, fail_after=None, fault_marker=None, parent=None):
    import pyarrow as pa
    import pyarrow.parquet as pq
    lake=Path(lake).resolve();lake.mkdir(parents=True,exist_ok=True)
    if executor not in ('serial','ray') or batch_size<1:raise ValueError('Invalid executor/batch size')
    # Reject ambiguous updates; incremental mode is append-only, not silent replacement.
    seen={}
    for row in records:
        sid=row.get('source_id') if isinstance(row,dict) else None
        if isinstance(sid,str) and sid:
            h=digest(row)
            if sid in seen and seen[sid]!=h:raise ValueError('Conflicting source_id: '+sid)
            seen[sid]=h
    records=sorted(records,key=digest)
    op=operator_hash();identity={'input_hash':digest(records),'operator_hash':op,'batch_size':batch_size,'parent':parent}
    version=digest(identity)[:24]
    destination=lake/'versions'/version;stage=lake/'staging'/version
    t0=time.perf_counter()
    lock=(lake/'writer.lock').open('a')
    try:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if parent is not None:
            parent_path=registered_snapshot(lake,parent)
            hashes_path=parent_path/'input-record-hashes.json'
            if not hashes_path.exists():
                raise ValueError('Parent lacks input identity index; rebuild as a new root snapshot')
            previous=Counter(json.loads(hashes_path.read_text()))
            if previous-Counter(digest(row) for row in records):
                raise ValueError('Incremental input must be append-only: parent records removed or changed')
        if destination.exists():
            manifest=verify_snapshot(destination)
            if manifest['identity']!=identity:raise ValueError('Version identity mismatch')
            with closing(connect(lake)) as con, con:
                old=con.execute('SELECT manifest_sha FROM versions WHERE version=?',(version,)).fetchone()
                if old and old[0]!=sha(destination/'manifest.json'):raise ValueError('Catalog manifest mismatch')
                con.execute('INSERT OR IGNORE INTO versions VALUES (?,?,?)',(version,sha(destination/'manifest.json'),str(destination.relative_to(lake))))
                for row in read_jsonl(destination/'lineage.jsonl'):
                    con.execute('INSERT OR IGNORE INTO lineage VALUES (?,?,?)',(version,row['doc_id'],row['source_id']))
            return {'version':version,'reused_snapshot':True,'resumed_shards':0,'processed_shards':0,'wall_seconds':time.perf_counter()-t0}
        stage.mkdir(parents=True,exist_ok=True)
        (lake/'shard-cache').mkdir(exist_ok=True)
        buckets={}
        for record in records:buckets.setdefault(digest(record)[:2],[]).append(record)
        batches=[bucket[i:i+batch_size] for _,bucket in sorted(buckets.items()) for i in range(0,len(bucket),batch_size)]
        outputs={};pending=[];cached=0;processed=0
        # Cache by exact shard input + operator; hash each cached payload before reuse.
        for index,batch in enumerate(batches):
            key=digest({'batch':batch,'operator':op});path=lake/'shard-cache'/f'{key}.json'
            if path.exists():
                saved=json.loads(path.read_text())
                if saved['key']!=key or saved['rows_hash']!=digest(saved['rows']):raise ValueError('Shard checksum mismatch')
                outputs[index]=saved['rows'];cached+=1
            else:pending.append((index,batch,key,path))
        def save(item, rows):
            nonlocal processed
            index,batch,key,path=item
            atomic_json(path,{'key':key,'rows_hash':digest(rows),'rows':rows})
            outputs[index]=rows;processed+=1
            if fail_after is not None and processed>=fail_after:
                raise RuntimeError('Injected driver interruption before publish')
        if executor=='serial':
            for item in pending:save(item,worker(item[1]))
        else:
            import ray
            if not ray.is_initialized():raise RuntimeError('Call ray.init before Ray pipeline')
            remote=ray.remote(num_cpus=1,max_retries=2)(worker)
            queue=list(pending);active={}
            try:
                while queue or active:
                    while queue and len(active)<8:
                        item=queue.pop(0)
                        marker=str(fault_marker) if fault_marker and item[0]==0 else None
                        active[remote.remote(item[1],marker)]=item
                    ready,_=ray.wait(list(active),num_returns=1)
                    for ref in ready:
                        item=active.pop(ref);save(item,ray.get(ref))
            finally:
                for ref in active:ray.cancel(ref,force=True)
        rows=[r for i in range(len(batches)) for r in outputs[i]]
        docs,quarantine,lineage=consolidate(rows)
        write_jsonl(stage/'documents.jsonl',docs);write_jsonl(stage/'quarantine.jsonl',quarantine);write_jsonl(stage/'lineage.jsonl',lineage)
        # Hash every original record, including quarantined and duplicate inputs.
        # Parent validation must not infer source identity from deduplicated documents.
        write_json(stage/'input-record-hashes.json',sorted(digest(row) for row in records))
        schema=pa.schema([(k,pa.string()) for k in ('doc_id','title','title_key','text')])
        pq.write_table(pa.Table.from_pylist(docs,schema=schema),stage/'documents.parquet',compression='zstd')
        manifest={'version':version,'identity':identity,'parent':parent,'counts':{'input':len(records),'accepted_rows':len(rows)-len(quarantine),'documents':len(docs),'quarantined':len(quarantine),'duplicate_rows':len(rows)-len(quarantine)-len(docs)},'files':{p.name:sha(p) for p in sorted(stage.iterdir()) if p.is_file() and p.name!='manifest.json'},'scope':'local filesystem atomic rename + SQLite registration; at-least-once work, idempotent snapshot visibility'}
        write_json(stage/'manifest.json',manifest)
        for p in stage.iterdir():
            if p.is_file():
                with p.open('rb') as f:os.fsync(f.fileno())
        destination.parent.mkdir(exist_ok=True)
        os.rename(stage,destination)
        # A crash after rename can leave an unregistered directory; rerun verifies and registers it.
        with closing(connect(lake)) as con, con:
            con.execute('INSERT INTO versions VALUES (?,?,?)',(version,sha(destination/'manifest.json'),str(destination.relative_to(lake))))
            for row in lineage:
                con.execute('INSERT OR IGNORE INTO lineage VALUES (?,?,?)',(version,row['doc_id'],row['source_id']))
        return {'version':version,'reused_snapshot':False,'resumed_shards':cached,'processed_shards':processed,'wall_seconds':time.perf_counter()-t0}
    finally:
        fcntl.flock(lock,fcntl.LOCK_UN);lock.close()


def main():
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--lake',type=Path,required=True);p.add_argument('--executor',choices=['serial','ray'],default='serial');a=p.parse_args()
    if a.executor=='ray':
        import ray
        ray.init(num_cpus=4,include_dashboard=False)
    try:print(json.dumps(run(read_jsonl(a.input),a.lake,a.executor),indent=2))
    finally:
        if a.executor=='ray':ray.shutdown()

if __name__=='__main__':main()
