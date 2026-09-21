"""Low-format-burden extraction with deterministic source binding.

Optional local relevance verification is a fallible model decision, not proof of
entailment. This module receives no gold answers, labels or evaluation identities.
"""
from .answering import EvidenceQA

EXTRACT_INSTRUCTION = (
    "完成阅读理解，从参考材料中提取问题的答案。答案使用材料原文，尽量简短。"
    "有答案时必须回答；确实没有答案时回答 NO_ANSWER。只写答案，不写解释。\n"
    "示例一\n材料：青松站于1998年开放。\n问题：青松站何时开放？\n答案：1998年\n"
    "示例二\n材料：紫桥位于海州市。\n问题：紫桥位于哪里？\n答案：海州市\n"
    "示例三\n材料：紫桥位于海州市。\n问题：紫桥有多长？\n答案：NO_ANSWER\n"
)
VERIFY_INSTRUCTION = (
    "判断引文是否直接回答问题。仅有相同主题或词语不算支持。"
    "答案必须回答问题所问的具体属性，不能依赖外部知识。"
    "支持只输出 YES；不支持、信息不完整或不能确定只输出 NO。\n"
)

class SpanQA(EvidenceQA):
    def __init__(self, documents, generator, verify=False, **kwargs):
        super().__init__(documents, generator, **kwargs)
        self.verify = verify

    def answer(self, question, k=3):
        if k not in (1, 3):
            raise ValueError("k must be 1 or 3")
        hits = [dict(c, score=s) for c, s in self.index.search(question, k)]
        prompt = EXTRACT_INSTRUCTION + "参考材料：\n"
        prompt += "\n---\n".join(c["text"] for c in hits) + "\n问题：" + question + "\n答案："
        raw = self.generator(prompt)
        result = {
            "question": question, "snapshot": self.version, "hits": hits,
            "raw_output": raw, "answer": "NO_ANSWER", "citation": None,
            "reason": "model_abstained", "model_calls": 1,
        }
        candidate = raw.strip()
        if candidate == "NO_ANSWER":
            return result
        if not candidate:
            result["reason"] = "empty_answer"
            return result
        # Deduplicate the same occurrence present in overlapping chunks. Distinct
        # document/offset occurrences are ambiguous and are not silently selected.
        occurrences = {}
        for chunk in hits:
            start = 0
            while (offset := chunk["text"].find(candidate, start)) >= 0:
                absolute = chunk["start"] + offset
                occurrences[(chunk["doc_id"], absolute)] = (chunk, absolute)
                start = offset + 1
        result["candidate"] = candidate
        if not occurrences:
            result["reason"] = "unsupported_quote"
            return result
        if len(occurrences) != 1:
            result["reason"] = "ambiguous_quote"
            return result
        chunk, offset = next(iter(occurrences.values()))
        if self.verify:
            check = VERIFY_INSTRUCTION + "问题：" + question + "\n引文：" + candidate
            verdict = self.generator(check).strip()
            result.update(verifier_raw=verdict, model_calls=2)
            if verdict != "YES":
                result["reason"] = "verifier_rejected" if verdict == "NO" else "invalid_verdict"
                return result
        result.update(
            answer=candidate, reason="quoted",
            citation={"doc_id": chunk["doc_id"], "chunk_id": chunk["chunk_id"],
                      "start": offset, "end": offset + len(candidate), "snapshot": self.version},
        )
        return result
