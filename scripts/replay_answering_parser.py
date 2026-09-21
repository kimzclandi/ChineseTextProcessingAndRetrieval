"""Post-hoc paired parser ablation on unchanged real model generations.
This is an engineering recovery analysis, not new independent model evidence.
"""
import argparse,json,hashlib
from pathlib import Path
from engine.answering import EvidenceQA
from evaluate_answering import read,write,metrics
ap=argparse.ArgumentParser();ap.add_argument("--source",type=Path,required=True);ap.add_argument("--out",type=Path,required=True);a=ap.parse_args()
a.out.mkdir(parents=True,exist_ok=False)
old=read(a.source/"predictions.jsonl");docs=read("data/asset-v1/documents.jsonl")
protocol=json.loads((a.source/"protocol.json").read_text());questions={q["id"]:q for q in protocol["queries"]}
write(a.out/"protocol.json",{"version":"rag-parser-replay-v2","kind":"post-hoc same-output parser comparison; no new model calls; not blind evaluation",
    "source_predictions_sha256":hashlib.sha256((a.source/"predictions.jsonl").read_bytes()).hexdigest(),
    "hypothesis":"bounded code-fence handling recovers valid citations without allowing uncited prose",
    "source_sha256":hashlib.sha256(Path("engine/answering.py").read_bytes()).hexdigest()})
rows=[]
qa=EvidenceQA(docs,lambda prompt: "")
for item in old:
    q=questions[item["id"]];raw=item["result"]["raw_output"]
    qa.generator=lambda prompt:raw
    r=qa.answer(q["question"],item["k"])
    assert r["hits"]==item["result"]["hits"] and r["raw_output"]==raw
    row=dict(item,result=r)
    row["correct"]=r["answer"] in row["gold"] if row["gold"] else r["answer"]=="NO_ANSWER"
    c=r["citation"]
    row["supported"]=bool(row["correct"] and c and c["doc_id"]==q["doc_id"] and any(c["start"]<=x["start"] and c["end"]>=x["start"]+len(x["text"]) for x in q["answers"]))
    rows.append(row)
(a.out/"predictions.jsonl").write_text("".join(json.dumps(r,ensure_ascii=False)+"\n" for r in rows))
write(a.out/"metrics.json",metrics(rows))
print(json.dumps(metrics(rows),ensure_ascii=False,indent=2))
