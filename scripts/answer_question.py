"""Single-question local demo. Inputs are documents, model snapshot and question."""
import argparse,json
from pathlib import Path
from engine.answering import EvidenceQA,LocalGenerator
p=argparse.ArgumentParser();p.add_argument("--documents",type=Path,default=Path("data/asset-v1/documents.jsonl"));p.add_argument("--snapshot",required=True);p.add_argument("--question",required=True);p.add_argument("--k",type=int,default=3);a=p.parse_args()
print(json.dumps(EvidenceQA([json.loads(s) for s in a.documents.read_text().splitlines()],LocalGenerator(a.snapshot)).answer(a.question,a.k),ensure_ascii=False,indent=2))
