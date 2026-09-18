"""Source adapters and pre-split duplicate-family construction. No model feedback."""
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path
from .common import digest,sha,write_json,write_jsonl
from .quality import normalize_title,process_batch,consolidate


def shingles(text):
    return {text[i:i+5] for i in range(max(0,len(text)-4))}


def simhash(text):
    counts=[0]*64
    for token in shingles(text):
        h=int.from_bytes(hashlib.blake2b(token.encode(),digest_size=8).digest(),'big')
        for bit in range(64):counts[bit]+=1 if h&(1<<bit) else -1
    return sum(1<<i for i,n in enumerate(counts) if n>=0)


def families(docs, lineage):
    parent={r['doc_id']:r['doc_id'] for r in docs}
    def root(i):
        while parent[i]!=i:
            parent[i]=parent[parent[i]];i=parent[i]
        return i
    def union(a,b):
        a,b=root(a),root(b)
        parent[max(a,b)]=min(a,b)
    titles={}
    for row in lineage:
        title=row['title_key'];doc=row['doc_id']
        if title in titles:union(doc,titles[title])
        titles[title]=doc
    buckets=defaultdict(list);hashes={};grams={};pairs=[];candidates=0
    for row in sorted(docs,key=lambda x:x['doc_id']):
        doc=row['doc_id'];h=simhash(row['text']);g=shingles(row['text']);possible=set()
        for band in range(4):possible.update(buckets[(band,(h>>(16*band))&65535)])
        for other in sorted(possible):
            if (h^hashes[other]).bit_count()>3:continue
            candidates+=1
            og=grams[other];j=len(g&og)/len(g|og) if g|og else 1
            if j>=.85:union(doc,other);pairs.append({'a':doc,'b':other,'jaccard':j})
        for band in range(4):buckets[(band,(h>>(16*band))&65535)].append(doc)
        hashes[doc]=h;grams[doc]=g
    groups=defaultdict(list)
    for doc in parent:groups[root(doc)].append(doc)
    result={doc:digest(sorted(group)) for group in groups.values() for doc in group}
    return result,{'near_pairs':pairs,'simhash_candidates_checked':candidates,'families':len(groups),'heuristic':'Not exhaustive semantic near-duplicate detection.'}


def prepare(raw_path, old_dev_path, output):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    raw=json.loads(Path(raw_path).read_text());old=json.loads(Path(old_dev_path).read_text())
    old_text={p['context'] for a in old['data'] for p in a['paragraphs']}
    old_titles={normalize_title(a['title']) for a in old['data']}
    records=[];queries=[];counts=Counter();qaudit=[]
    for ai,article in enumerate(raw['data']):
        for pi,paragraph in enumerate(article['paragraphs']):
            text=paragraph['context'];title=article['title'];sid=f'cmrc-train:{ai}:{pi}'
            counts['raw_paragraphs']+=1
            if text in old_text or normalize_title(title) in old_titles:
                counts['excluded_old_dev_paragraphs']+=1;continue
            records.append({'source_id':sid,'title':title,'text':text})
            for q in paragraph['qas']:
                counts['candidate_questions']+=1
                refs=q['answers']
                valid=bool(refs) and all(isinstance(a.get('text'),str) and a['text'].strip() and isinstance(a.get('answer_start'),int) and a['answer_start']>=0 and text[a['answer_start']:a['answer_start']+len(a['text'])]==a['text'] for a in refs)
                if not valid:
                    counts['invalid_reference_questions']+=1;qaudit.append({'id':q['id'],'reason':'empty_or_offset_mismatch'});continue
                queries.append({'id':q['id'],'source_id':sid,'doc_id':digest(text),'question':q['question'],'answers':[{'text':a['text'],'start':a['answer_start']} for a in refs]})
    processed=process_batch(records);docs,quarantine,lineage=consolidate(processed)
    fmap,audit=families(docs,lineage)
    candidates=defaultdict(list)
    for q in queries:
        if q['doc_id'] in fmap:
            q['family_id']=fmap[q['doc_id']];candidates[q['family_id']].append(q)
    ordered=sorted(candidates,key=lambda f:digest('evidence-v1:'+f))
    if len(ordered)<320:raise ValueError('Insufficient independent families')
    chosen=[]
    for n,family in enumerate(ordered[:320]):
        q=min(candidates[family],key=lambda q:digest('question-v1:'+q['id'])).copy()
        q['split']='dev' if n<160 else 'holdout';chosen.append(q)
    write_jsonl(output/'source-records.jsonl',records)
    write_jsonl(output/'dev.jsonl',[q for q in chosen if q['split']=='dev'])
    write_jsonl(output/'holdout.jsonl',[q for q in chosen if q['split']=='holdout'])
    write_jsonl(output/'reference-quarantine.jsonl',qaudit)
    write_json(output/'families.json',fmap)
    manifest={'source_sha256':sha(raw_path),'excluded_old_dev_sha256':sha(old_dev_path),'counts':dict(counts),'corpus':{'documents':len(docs),'exact_duplicate_rows':len(records)-len(quarantine)-len(docs),'quarantined_rows':len(quarantine)},'family_audit':audit,'selection':'160 development +160 holdout, one question per family; no model outputs used','files':{p.name:sha(p) for p in output.iterdir() if p.is_file()}}
    write_json(output/'manifest.json',manifest)
    return manifest
