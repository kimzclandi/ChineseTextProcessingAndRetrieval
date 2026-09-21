"""Freeze and run paired, source-withheld, locally generated QA diagnostics."""
import argparse
import hashlib
import json
import platform
import time
from pathlib import Path

from engine.answering import EvidenceQA, LocalGenerator
from engine.span_answering import SpanQA, EXTRACT_INSTRUCTION, VERIFY_INSTRUCTION
from engine.common import digest

ARMS = ("json", "span", "verified_span")

def read(path):
    return [json.loads(s) for s in Path(path).read_text().splitlines()]

def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")

def build_set(documents, questions, excluded, positive_n, negative_n, salt):
    # Evaluation-only construction: source removal is fixed before inference.
    ordered = sorted(questions, key=lambda q: digest([salt, q["id"]]))
    used_families = set()
    positive = []
    for q in ordered:
        if q["id"] in excluded or q["family_id"] in used_families:
            continue
        positive.append(dict(q, answerable=True))
        used_families.add(q["family_id"])
        if len(positive) == positive_n:
            break
    negatives = []
    for q in ordered:
        if q["id"] in excluded or q["family_id"] in used_families:
            continue
        answers = [a["text"] for a in q["answers"]]
        # Require all annotated exact answers to occur only in the withheld source.
        if not answers or min(map(len, answers)) < 4:
            continue
        if any(a in d["text"] for d in documents if d["doc_id"] != q["doc_id"] for a in answers):
            continue
        negatives.append(dict(q, answerable=False))
        used_families.add(q["family_id"])
        if len(negatives) == negative_n:
            break
    if len(positive) != positive_n or len(negatives) != negative_n:
        raise ValueError("not enough disjoint source-withheld cases")
    removed = {q["doc_id"] for q in negatives}
    corpus = [d for d in documents if d["doc_id"] not in removed]
    assert all(q["doc_id"] not in removed for q in positive)
    queries = sorted(positive + negatives, key=lambda q: digest([salt, "order", q["id"]]))
    return corpus, queries, sorted(removed)

def score(q, result):
    citation = result["citation"]
    answer = result["answer"]
    gold = [a["text"] for a in q["answers"]]
    def supports(c):
        return c["doc_id"] == q["doc_id"] and any(
            c["start"] <= a["start"] and c["end"] >= a["start"] + len(a["text"])
            for a in q["answers"])
    quote_valid = bool(citation and any(
        h["doc_id"] == citation["doc_id"] and h["chunk_id"] == citation["chunk_id"]
        and h["text"][citation["start"]-h["start"]:citation["end"]-h["start"]] == answer
        for h in result["hits"]))
    return {
        "correct": answer in gold if q["answerable"] else answer == "NO_ANSWER",
        "retrieval_hit": bool(q["answerable"] and any(supports(h) for h in result["hits"])),
        "quote_valid": quote_valid,
        "reference_supported": bool(q["answerable"] and citation and supports(citation)),
    }

def metrics(rows):
    result = {}
    for arm in ARMS:
        group = [r for r in rows if r["arm"] == arm]
        pos = [r for r in group if r["answerable"]]
        neg = [r for r in group if not r["answerable"]]
        answered = [r for r in group if r["result"]["answer"] != "NO_ANSWER"]
        result[arm] = {
            "n": len(group), "positive_n": len(pos), "negative_n": len(neg),
            "answerable_exact_matches": sum(r["correct"] for r in pos),
            "retrieval_hits": sum(r["retrieval_hit"] for r in pos),
            "false_refusals": sum(r["result"]["answer"] == "NO_ANSWER" for r in pos),
            "negative_false_answers": sum(not r["correct"] for r in neg),
            "answered": len(answered), "valid_quotes": sum(r["quote_valid"] for r in answered),
            "reference_supported": sum(r["reference_supported"] for r in answered),
            "model_calls": sum(r["result"].get("model_calls", 1) for r in group),
            "mean_seconds": sum(r["seconds"] for r in group) / len(group),
            "failures": [{"id": r["id"], "reason": r["result"]["reason"]} for r in group if not r["correct"]],
        }
    return result

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--snapshot", type=Path)
    ap.add_argument("--split", choices=("dev", "holdout"), default="dev")
    ap.add_argument("--recompute", action="store_true")
    a = ap.parse_args()
    if a.recompute:
        rows = read(a.out / "predictions.jsonl")
        protocol = json.loads((a.out / "protocol.json").read_text())
        queries = {q["id"]: q for q in protocol["queries"]}
        for row in rows:
            assert all(row[k] == v for k, v in score(queries[row["id"]], row["result"]).items())
        assert metrics(rows) == json.loads((a.out / "metrics.json").read_text())
        print(json.dumps(metrics(rows), ensure_ascii=False, indent=2))
        return
    a.out.mkdir(parents=True, exist_ok=False)
    documents = read("data/asset-v1/documents.jsonl")
    previous = json.loads(Path("reports/answering-v1/protocol.json").read_text())
    excluded = {q["id"] for q in previous["queries"]}
    counts = (8, 4) if a.split == "dev" else (32, 12)
    corpus, queries, removed = build_set(documents, read(f"data/source-v1/{a.split}.jsonl"), excluded, *counts, "span-qa-v1")
    protocol = {
        "version": "span-qa-v1", "split": a.split, "queries": queries,
        "corpus_sha256": digest(corpus), "withheld_document_ids": removed,
        "source_documents_sha256": digest(documents), "arms": ARMS, "k": 3,
        "size": 160, "stride": 80, "extract_prompt": EXTRACT_INSTRUCTION,
        "verify_prompt": VERIFY_INSTRUCTION, "snapshot_revision": a.snapshot.name,
        "generation": {"max_new_tokens_per_call": 80, "do_sample": False, "device": "cpu", "dtype": "float32", "threads": 4},
        "hypothesis": "Deterministic citation binding reduces format loss; a separate relevance decision reduces source-withheld false answers.",
        "success": "Holdout span arm improves answerable exact matches by >=3/32 over JSON and does not increase false answers on 12 withheld-source probes; verifier must improve negative errors without losing positive EM.",
        "failure": "Any unmet condition retained; no holdout-driven prompt revision or reroll.",
        "scope": "QA-generation-disjoint from prior 24 questions, one question per family; historical retrieval holdout has been evaluated before. Negative labels mean withholding the sole exact-reference source, not universal world-knowledge absence.",
        "frozen_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    write(a.out / "protocol.json", protocol)
    write(a.out / "environment.json", {
        "python": platform.python_version(), "platform": platform.platform(),
        "source_sha256": {str(f): hashlib.sha256(f.read_bytes()).hexdigest() for f in (Path("engine/answering.py"), Path("engine/span_answering.py"), Path(__file__))},
        "weights_sha256": hashlib.sha256((a.snapshot/"model.safetensors").read_bytes()).hexdigest(),
    })
    generator = LocalGenerator(a.snapshot)
    systems = {"json": EvidenceQA(corpus, generator), "span": SpanQA(corpus, generator), "verified_span": SpanQA(corpus, generator, verify=True)}
    rows = []
    with (a.out/"predictions.jsonl").open("w") as output:
        for i, q in enumerate(queries):
            # Rotate execution order, while every arm receives identical retrieved text.
            for arm in ARMS[i % 3:] + ARMS[:i % 3]:
                start = time.perf_counter()
                result = systems[arm].answer(q["question"], 3)
                row = {"id": q["id"], "answerable": q["answerable"], "arm": arm, "result": result,
                       "seconds": time.perf_counter()-start, **score(q, result)}
                rows.append(row)
                output.write(json.dumps(row, ensure_ascii=False)+"\n"); output.flush()
                print(q["id"], arm, flush=True)
    write(a.out / "metrics.json", metrics(rows))

if __name__ == "__main__":
    main()
