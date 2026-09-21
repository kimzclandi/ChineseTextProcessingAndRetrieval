"""Independent metric decomposition from saved outputs; no inference or gold access at generation."""
import argparse,json
from pathlib import Path
ap=argparse.ArgumentParser();ap.add_argument("--run",type=Path,required=True);ap.add_argument("--protocol",type=Path,required=True);a=ap.parse_args()
queries={q["id"]:q for q in json.loads(a.protocol.read_text())["queries"]}
rows=[json.loads(s) for s in (a.run/"predictions.jsonl").read_text().splitlines()];result={}
for k in (1,3):
 group=[r for r in rows if r["k"]==k];answered=[r for r in group if r["result"]["answer"]!="NO_ANSWER"];quote=reference=0
 for row in answered:
  r=row["result"];c=r["citation"];q=queries[row["id"]]
  quote+=bool(c and any(h["doc_id"]==c["doc_id"] and h["chunk_id"]==c["chunk_id"] and h["start"]<=c["start"]<c["end"]<=h["end"] and h["text"][c["start"]-h["start"]:c["end"]-h["start"]]==r["answer"] for h in r["hits"]))
  reference+=bool(c and c["doc_id"]==q["doc_id"] and any(c["start"]<=v["start"] and c["end"]>=v["start"]+len(v["text"]) for v in q["answers"]))
 result[str(k)]={"answered":len(answered),"verbatim_quote_verified":quote,"reference_answer_span_supported":reference,
 "note":"verbatim substring validity does not prove relevance/entailment; reference-span support allows longer correct-source quotes, unlike exact answer match"}
print(json.dumps(result,ensure_ascii=False,indent=2))
