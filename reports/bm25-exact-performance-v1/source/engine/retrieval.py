"""Transparent character BM25, with raw offsets retained for span verification."""
from collections import Counter,defaultdict
import math
import statistics
import time
import unicodedata
from .common import digest


def tokens(text):
    s=''.join(c.casefold() for c in unicodedata.normalize('NFC',text) if c.isalnum())
    return list(s)+[s[i:i+2] for i in range(len(s)-1)]


def chunks(documents,size=160,stride=160):
    if not 0<stride<=size:raise ValueError('Require 0 < stride <= size')
    result=[]
    for d in sorted(documents,key=lambda d:d['doc_id']):
        for start in range(0,len(d['text']),stride):
            end=min(start+size,len(d['text']))
            result.append({'chunk_id':digest([d['doc_id'],start,end]),'doc_id':d['doc_id'],'start':start,'end':end,'text':d['text'][start:end]})
            if end==len(d['text']):break
    return result


class BM25:
    def __init__(self,rows,k1=1.2,b=.75):
        self.rows=rows;self.k1=k1;self.b=b;self.postings=defaultdict(list);self.lengths=[]
        for i,row in enumerate(rows):
            words=tokens(row['text']);self.lengths.append(len(words))
            for word,count in Counter(words).items():self.postings[word].append((i,count))
        self.avg=sum(self.lengths)/max(len(rows),1)
    def search(self,query,k=3):
        scores=defaultdict(float);n=len(self.rows)
        for word,qtf in sorted(Counter(tokens(query)).items()):
            posting=self.postings.get(word,[]);df=len(posting)
            idf=math.log1p((n-df+.5)/(df+.5))
            for i,tf in posting:
                scores[i]+=qtf*idf*tf*(self.k1+1)/(tf+self.k1*(1-self.b+self.b*self.lengths[i]/max(self.avg,1)))
        ranked=sorted(scores,key=lambda i:(-scores[i],self.rows[i]['chunk_id']))[:k]
        return [(self.rows[i],scores[i]) for i in ranked]


def score_query(q,hits,all_chunks):
    doc_hit=any(c['doc_id']==q['doc_id'] for c in hits)
    def supports(c):
        return c['doc_id']==q['doc_id'] and any(c['start']<=a['start'] and c['end']>=a['start']+len(a['text']) for a in q['answers'])
    span=any(supports(c) for c in hits)
    oracle=any(supports(c) for c in all_chunks)
    rr=next((1/(i+1) for i,c in enumerate(hits) if c['doc_id']==q['doc_id']),0)
    reason='success' if span else ('chunk_boundary_or_answer_too_long' if not oracle else ('source_not_retrieved' if not doc_hit else 'wrong_chunk_from_source'))
    return {'id':q['id'],'document_hit':int(doc_hit),'span_hit':int(span),'reciprocal_rank':rr,'oracle_span':int(oracle),'failure':reason}


def evaluate(index,queries):
    # Fixed artificial warmup independent of evaluation questions.
    index.search('这是一个用于检索预热的问题')
    bydoc=defaultdict(list)
    for c in index.rows:bydoc[c['doc_id']].append(c)
    predictions=[]
    for q in queries:
        t=time.perf_counter();ranked=index.search(q['question']);elapsed=time.perf_counter()-t
        hits=[c for c,_ in ranked]
        if sum(len(c['text']) for c in hits)>480:raise ValueError('Retrieval character budget exceeded')
        score=score_query(q,hits,bydoc[q['doc_id']])
        predictions.append(dict(score,latency_seconds=elapsed,hits=[{'chunk_id':c['chunk_id'],'score':value} for c,value in ranked],returned_chars=sum(len(c['text']) for c in hits)))
    return summarize(predictions),predictions


def summarize(predictions):
    if not predictions:raise ValueError('Empty evaluation')
    n=len(predictions);latencies=sorted(p['latency_seconds'] for p in predictions)
    return {'n':n,'document_recall_at3':sum(p['document_hit'] for p in predictions)/n,'span_hit_at3':sum(p['span_hit'] for p in predictions)/n,'mrr_at3':sum(p['reciprocal_rank'] for p in predictions)/n,'oracle_span_coverage':sum(p['oracle_span'] for p in predictions)/n,'latency_median_ms':statistics.median(latencies)*1000,'latency_p95_ms':latencies[math.ceil(.95*n)-1]*1000,'failures':dict(Counter(p['failure'] for p in predictions))}


def paired(before,after):
    a={r['id']:r for r in before};b={r['id']:r for r in after}
    if len(a)!=len(before) or len(b)!=len(after) or set(a)!=set(b):raise ValueError('ID coverage mismatch')
    return {'fixes':[i for i in a if not a[i]['span_hit'] and b[i]['span_hit']],'regressions':[i for i in a if a[i]['span_hit'] and not b[i]['span_hit']]}
