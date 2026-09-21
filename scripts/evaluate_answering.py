"""Freeze a new diagnostic protocol, run paired real inference, or recompute metrics."""
import argparse, hashlib, json, platform, time
from pathlib import Path
from engine.answering import EvidenceQA, LocalGenerator
from engine.common import digest

def read(path): return [json.loads(s) for s in Path(path).read_text().splitlines()]
def write(path, value): Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n")
def metrics(rows):
    out = {}
    for k in (1,3):
        group=[r for r in rows if r["k"]==k]
        pos=[r for r in group if r["gold"]]; neg=[r for r in group if not r["gold"]]
        answered=[r for r in group if r["result"]["answer"]!="NO_ANSWER"]
        out[str(k)]={"n":len(group), "answerable_n":len(pos), "unanswerable_n":len(neg),
            "retrieval_span_coverage":sum(r["retrieval_hit"] for r in pos)/len(pos),
            "answerable_exact_match":sum(r["correct"] for r in pos)/len(pos),
            "overall_exact_match":sum(r["correct"] for r in group)/len(group),
            "false_refusal_rate":sum(r["result"]["answer"]=="NO_ANSWER" for r in pos)/len(pos),
            "correct_refusal_rate":sum(r["correct"] for r in neg)/len(neg),
            "answered_n":len(answered),
            "citation_gold_support_rate":sum(r["supported"] for r in answered)/len(answered) if answered else None,
            "mean_seconds":sum(r["seconds"] for r in group)/len(group),
            "failures":[r["id"] for r in group if not r["correct"]]}
    return out

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--out",type=Path,required=True)
    ap.add_argument("--snapshot");ap.add_argument("--recompute",action="store_true");a=ap.parse_args()
    if a.recompute:
        result=metrics(read(a.out/"predictions.jsonl"));assert result==json.loads((a.out/"metrics.json").read_text());print(json.dumps(result,indent=2));return
    a.out.mkdir(parents=True,exist_ok=False)
    docs=read("data/asset-v1/documents.jsonl")
    queries=sorted(read("data/source-v1/holdout.jsonl"),key=lambda q:digest(q["id"]))[:24]
    # Explicitly constructed missing-information probes; not CMRC negative labels.
    for i in range(8):
        queries.append({"id":f"missing-private-{i}","question":f"私有工单 CASE-20260921-{i} 的一次性验证码是什么？", "answers":[],"doc_id":None})
    protocol={"version":"rag-closed-loop-v1","dataset_sha256":digest(docs),"queries":queries,
        "model_snapshot":Path(a.snapshot).name,"arms":[1,3],"size":160,"stride":80,
        "hypothesis":"Top-3 improves answer EM over top-1 without increasing false refusal or unsupported citations.",
        "success":"higher answerable EM, no lower correct refusal or gold citation support; descriptive pilot only",
        "failure":"unchanged/worse EM or refusal tradeoff; preserve all outputs; no tuning on these questions",
        "scope":"24 hash-selected existing holdout questions + 8 authored missing-private-information probes; not a fresh blind holdout",
        "generation":{"max_new_tokens":80,"sample":False,"device":"cpu","dtype":"float32"},
        "frozen_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())}
    write(a.out/"protocol.json",protocol)
    write(a.out/"environment.json",{"python":platform.python_version(),"platform":platform.platform(),
        "model_files":{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in Path(a.snapshot).iterdir() if f.is_file()},
        "source_sha256":hashlib.sha256(Path("engine/answering.py").read_bytes()).hexdigest()})
    qa=EvidenceQA(docs,LocalGenerator(a.snapshot)); rows=[]
    with (a.out/"predictions.jsonl").open("w") as output:
        for q in queries:
            for k in (1,3):
                start=time.perf_counter(); r=qa.answer(q["question"],k); seconds=time.perf_counter()-start
                gold=[x["text"] for x in q["answers"]]
                def supports(c): return c["doc_id"]==q["doc_id"] and any(c["start"]<=x["start"] and c["end"]>=x["start"]+len(x["text"]) for x in q["answers"])
                correct=r["answer"] in gold if gold else r["answer"]=="NO_ANSWER"
                supported=bool(correct and r["citation"] and supports(r["citation"]))
                item={"id":q["id"],"k":k,"gold":gold,"result":r,"seconds":seconds,"correct":correct,
                      "retrieval_hit":any(supports(c) for c in r["hits"]),"supported":supported}
                rows.append(item); output.write(json.dumps(item,ensure_ascii=False)+"\n");output.flush()
                print(q["id"],k,flush=True)
    write(a.out/"metrics.json",metrics(rows))
if __name__=="__main__":main()
