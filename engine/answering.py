"""Retrieval -> local extractive generation -> source-bound citation or abstention.
Gold answers are not an input to this module. Quote validation is NOT entailment.
"""
import json
import re
from .common import digest
from .retrieval import BM25, chunks

class EvidenceQA:
    def __init__(self, documents, generator, size=160, stride=80):
        self.version = digest(documents)
        self.index = BM25(chunks(documents, size, stride))
        self.generator = generator

    def answer(self, question, k=3):
        if k not in (1, 3):
            raise ValueError("k must be 1 or 3")
        hits = [dict(c, score=s) for c, s in self.index.search(question, k)]
        evidence = [{"citation": i+1, "text": c["text"]} for i,c in enumerate(hits)]
        prompt = ("仅根据证据回答问题。答案必须是证据中的最短连续原文片段。"
                  "找不到答案则输出 NO_ANSWER。只输出 JSON："
                  '{"answer":"原文片段或NO_ANSWER","citation":1}。拒答时citation为0。\n'
                  + json.dumps({"question": question, "evidence": evidence}, ensure_ascii=False))
        raw = self.generator(prompt)
        result = {"question": question, "snapshot": self.version, "hits": hits,
                  "raw_output": raw, "answer": "NO_ANSWER", "citation": None,
                  "reason": "invalid_json"}
        try:
            # Accept only a whole-output JSON fence, never extract a substring from prose.
            fenced = re.fullmatch(r"```(?:json)?\s*\n(.*?)\n```", raw.strip(), re.S)
            value = json.loads(fenced.group(1) if fenced else raw)
            answer, number = value["answer"], value["citation"]
            if not isinstance(answer, str) or type(number) is not int:
                return result
        except (ValueError, TypeError, KeyError):
            return result
        result["candidate"] = value
        if answer == "NO_ANSWER":
            result["reason"] = "model_abstained"
        elif not answer.strip() or not 1 <= number <= len(hits):
            result["reason"] = "invalid_citation"
        else:
            c = hits[number-1]
            offset = c["text"].find(answer)
            if offset < 0:
                result["reason"] = "unsupported_quote"
            else:
                result.update(answer=answer, reason="quoted", citation={
                    "doc_id": c["doc_id"], "chunk_id": c["chunk_id"],
                    "start": c["start"]+offset, "end": c["start"]+offset+len(answer),
                    "snapshot": self.version})
        return result

class LocalGenerator:
    def __init__(self, snapshot):
        import torch
        from transformers import AutoTokenizer, AutoModelForCausalLM
        torch.set_num_threads(4)
        self.torch = torch
        self.tokenizer = AutoTokenizer.from_pretrained(snapshot, local_files_only=True)
        self.model = AutoModelForCausalLM.from_pretrained(snapshot, local_files_only=True,
            torch_dtype=torch.float32, attn_implementation="eager").eval()
    def __call__(self, prompt):
        text = self.tokenizer.apply_chat_template([{"role":"user", "content":prompt}],
            tokenize=False, add_generation_prompt=True)
        inputs = self.tokenizer(text, return_tensors="pt")
        with self.torch.inference_mode():
            out = self.model.generate(**inputs, do_sample=False, max_new_tokens=80)
        return self.tokenizer.decode(out[0, inputs["input_ids"].shape[1]:], skip_special_tokens=True).strip()
