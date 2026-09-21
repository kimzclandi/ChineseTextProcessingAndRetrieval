"""Single-question local demo; baseline remains explicit and available."""
import argparse
import json
from pathlib import Path
from engine.answering import EvidenceQA, LocalGenerator
from engine.span_answering import SpanQA

p = argparse.ArgumentParser()
p.add_argument("--documents", type=Path, default=Path("data/asset-v1/documents.jsonl"))
p.add_argument("--snapshot", required=True)
p.add_argument("--question", required=True)
p.add_argument("--k", type=int, default=3)
p.add_argument("--mode", choices=("json", "span", "verified_span"), default="json")
a = p.parse_args()
documents = [json.loads(s) for s in a.documents.read_text().splitlines()]
generator = LocalGenerator(a.snapshot)
qa = EvidenceQA(documents, generator) if a.mode == "json" else SpanQA(documents, generator, verify=a.mode == "verified_span")
print(json.dumps(qa.answer(a.question, a.k), ensure_ascii=False, indent=2))
