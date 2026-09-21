# Extractive answer modes and selective refusal

`engine/span_answering.py` adds `span` and `verified_span` modes to `scripts/answer_question.py`. The model produces a short verbatim span; deterministic code binds it to one unique document/offset and the corpus snapshot. Overlapping chunks at the same occurrence are deduplicated. Distinct occurrences refuse as ambiguous. The optional second local-model call sees the question and candidate quote, accepting only exact YES; it is a fallible relevance check, not full-context entailment proof. Default remains `json` because the new modes did not meet the quality success criteria.

## Frozen comparison

Hypothesis: removing JSON/index generation reduces format failures; an additional relevance decision reduces unsupported answers. Success was fixed as at least three additional positive exact matches out of 32 versus JSON, without increasing negative answers; the verifier must reduce negative errors without losing positive EM. Failure of either condition is retained, with no holdout-driven tuning.

Two development runs used 8 positives and 4 withheld-source probes each. The first extraction prompt over-refused; the second uses three authored examples and places the question after context. The first implementation is archived exactly in `reports/span-qa-dev-v1/span_answering_at_run.py.txt`. Only development results informed that prompt change. The holdout then used 32 positive questions and 12 source-withheld probes, one question per family, disjoint from the earlier 24 QA-generation questions. Historical retrieval evaluation has already used the source holdout: this is not wholly unseen benchmark data. A negative probe removes its sole source document; every annotated reference answer is at least four characters and absent from other documents. This tests closed-corpus refusal, not universal unanswerability.

All arms use identical top-3 BM25 evidence, size 160/stride 80, Qwen2.5-1.5B, CPU float32, four threads, greedy, 80 tokens per call. Arm order rotates by question. Frozen prompts, query IDs, removed documents, data hashes, weights hash, code hashes and raw model responses are saved in `reports/span-qa-holdout-v2`.

| Metric | JSON baseline | Span | Verified span |
|---|---:|---:|---:|
| Positive exact matches /32 | 5 | 4 | 3 |
| Retrieval coverage /32 | 27 | 27 | 27 |
| False refusals /32 | 17 | 17 | 25 |
| Answers on withheld-source probes /12 | 3 | 1 | 0 |
| Verbatim-valid quotes / answered | 18/18 | 16/16 | 7/7 |
| Quotes covering annotated answer at correct source | 7 | 6 | 5 |
| Model calls /44 questions | 44 | 44 | 60 |
| Observed mean seconds/question | 1.464 | 0.940 | 1.012 |

Both success criteria fail. Verified extraction reduces negative mistakes but discards more answerable cases, including a correct span on `TRAIN_2047_QUERY_1`. `TRAIN_2679_QUERY_1` fails unique-occurrence binding. `TRAIN_2071_QUERY_4` illustrates invalid JSON versus unsupported generated span. All outputs remain available, including failures and initial development negatives. Quote validity proves source presence, not answer correctness; annotated-span support is also only a proxy for semantic support. Single-run local timings describe this run, not statistically established speed gains or throughput.

## Run and recompute

```sh
PYTHONPATH=. python scripts/answer_question.py --snapshot "$QWEN_1_5B_SNAPSHOT" --mode verified_span --question '曹霸是哪个时期的画家？'
# New output directory; the saved protocol/results must stay unchanged:
PYTHONPATH=. python scripts/evaluate_span_qa.py --snapshot "$QWEN_1_5B_SNAPSHOT" --split holdout --out reports/span-new
PYTHONPATH=. python scripts/evaluate_span_qa.py --out reports/span-qa-holdout-v2 --recompute
python -m pytest -q
```

64 tests passed locally, including snapshot/offset binding, ambiguity and verifier rejection. These establish implemented contracts, not model quality. Stored predictions recompute to the saved metrics. No private customer-service code or knowledge base is used by this experiment.
