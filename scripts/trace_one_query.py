"""Read-only trace of one frozen CMRC query through source, asset and retrieval.

The default is a pre-existing holdout repair. This script does not select a new
parameter, write research evidence or make a claim about generated answers.
"""
import argparse
from collections import defaultdict
import json
import math
from pathlib import Path

from engine.common import digest, read_jsonl, sha
from engine.retrieval import BM25, score_query
from engine.pipeline import verify_snapshot


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUERY = "TRAIN_3041_QUERY_1"


def one(rows, field, value):
    found = [row for row in rows if row[field] == value]
    if len(found) != 1:
        raise ValueError(f"Expected one {field}={value}, got {len(found)}")
    return found[0]


def trace(query_id):
    source_dir = ROOT / "data/source-v1"
    source_manifest = json.loads((source_dir / "manifest.json").read_text())
    for name, expected in source_manifest["files"].items():
        if sha(source_dir / name) != expected:
            raise ValueError(f"Source checksum mismatch: {name}")
    verify_snapshot(ROOT / "data/asset-v1")
    q = one(read_jsonl(source_dir / "holdout.jsonl"), "id", query_id)
    source = one(read_jsonl(source_dir / "source-records.jsonl"), "source_id", q["source_id"])
    doc = one(read_jsonl(ROOT / "data/asset-v1/documents.jsonl"), "doc_id", q["doc_id"])
    if source["text"] != doc["text"] or digest(source["text"]) != q["doc_id"]:
        raise ValueError("Source-to-document text identity mismatch")
    lineage = [r for r in read_jsonl(ROOT / "data/asset-v1/lineage.jsonl")
               if r["doc_id"] == q["doc_id"] and r["source_id"] == q["source_id"]]
    if len(lineage) != 1:
        raise ValueError("Source-to-document lineage mismatch")
    for answer in q["answers"]:
        start = answer["start"]
        if doc["text"][start:start + len(answer["text"])] != answer["text"]:
            raise ValueError("Reference answer offset mismatch")

    protocol = json.loads((ROOT / "configs/protocol.json").read_text())
    folder = ROOT / "reports/retrieval-v1"
    freeze = json.loads((folder / "freeze.json").read_text())
    if sha(ROOT / "configs/protocol.json") != freeze["protocol_sha256"]:
        raise ValueError("Protocol checksum mismatch")
    result = {"query": q, "source": source, "document": doc, "lineage": lineage[0], "arms": {}}
    for variant in ("baseline", "candidate"):
        chunk_path = folder / variant / "chunks.jsonl"
        if sha(chunk_path) != freeze["chunks_sha256"][variant]:
            raise ValueError(f"Frozen chunk checksum mismatch: {variant}")
        chunks = read_jsonl(chunk_path)
        by_id = {row["chunk_id"]: row for row in chunks}
        if len(by_id) != len(chunks):
            raise ValueError("Duplicate chunk IDs")
        prediction = one(read_jsonl(folder / "holdout" / f"{variant}.predictions.jsonl"), "id", query_id)
        fresh = BM25(chunks, **protocol["retrieval"]["bm25"]).search(q["question"])
        if [row["chunk_id"] for row, _ in fresh] != [hit["chunk_id"] for hit in prediction["hits"]]:
            raise ValueError(f"Fresh BM25 ranking differs: {variant}")
        if not all(math.isclose(score, saved["score"], rel_tol=1e-12, abs_tol=1e-12)
                   for (_, score), saved in zip(fresh, prediction["hits"])):
            raise ValueError(f"Fresh BM25 scores differ: {variant}")
        hits = [by_id[hit["chunk_id"]] for hit in prediction["hits"]]
        if sum(len(row["text"]) for row in hits) != prediction["returned_chars"]:
            raise ValueError("Returned character budget differs")
        doc_chunks = [row for row in chunks if row["doc_id"] == q["doc_id"]]
        scored = score_query(q, hits, doc_chunks)
        if any(scored[key] != prediction[key] for key in scored):
            raise ValueError(f"Frozen score fields differ: {variant}")
        result["arms"][variant] = {"prediction": prediction, "hits": hits,
                                    "source_chunks": doc_chunks}
    return result


def render(result):
    q, doc = result["query"], result["document"]
    answer = q["answers"][0]
    start, end = answer["start"], answer["start"] + len(answer["text"])
    lines = ["# 单条查询的证据链（只读重算）", "",
             f"- 留出集问题：`{q['id']}`；问题：{q['question']}",
             f"- 原始记录：`{q['source_id']}`；资产文档：`{q['doc_id']}`。已核对原文哈希、文本一致和血缘行。",
             f"- 标注答案：`{answer['text']}`；原文字符偏移：`[{start}, {end})`。",
             f"- 原文局部：…{doc['text'][max(0,start-22):min(len(doc['text']),end+22)]}…", "",
             "| 方案 | 原文档是否命中@3 | 完整答案跨度是否命中@3 | 原文档是否有可覆盖块 | 失败类型 |",
             "|---|---:|---:|---:|---|"]
    for variant in ("baseline", "candidate"):
        arm = result["arms"][variant]
        p = arm["prediction"]
        lines.append(f"| {variant} | {p['document_hit']} | {p['span_hit']} | {p['oracle_span']} | {p['failure']} |")
    for variant in ("baseline", "candidate"):
        arm = result["arms"][variant]
        lines += ["", f"## {variant}：重新执行 BM25 后的前三块"]
        for rank, (saved, chunk) in enumerate(zip(arm["prediction"]["hits"], arm["hits"]), 1):
            covers = chunk["doc_id"] == q["doc_id"] and chunk["start"] <= start and chunk["end"] >= end
            lines.append(f"{rank}. `chunk_id={chunk['chunk_id']}`，score={saved['score']:.5f}，"
                         f"原文档={'是' if chunk['doc_id']==q['doc_id'] else '否'}，"
                         f"区间=[{chunk['start']},{chunk['end']})，完整覆盖答案={'是' if covers else '否'}。")
        source_ranges = [(c["start"], c["end"]) for c in arm["source_chunks"]
                         if c["start"] <= start and c["end"] >= end]
        lines.append(f"原文档中完整覆盖答案的块区间：{source_ranges or '无'}。")
    lines += ["", "结论：本例是既有留出集中的一条修复案例；块覆盖改变了解析到标注答案的能力，"
             "但不能证明生成式回答正确，也不能代表所有问题都改善。完整总体与代价见 reports/RESULTS.md。"]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--query-id", default=DEFAULT_QUERY)
    args = parser.parse_args()
    print(render(trace(args.query_id)), end="")


if __name__ == "__main__":
    main()
