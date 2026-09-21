# Local cited-answer pipeline

The previous pipeline stopped at evidence retrieval. `engine/answering.py` now exposes `EvidenceQA.answer(question, k)` and a CPU Transformers adapter. Inputs are versioned documents and a question. Outputs include retrieval hits, raw generation, an answer or `NO_ANSWER`, a reason, and source offsets bound to a document snapshot. Gold answers are only passed to the evaluator.

A returned quote must exactly match its cited chunk. A bounded whole-output JSON code fence is accepted. Prose surrounding JSON, absent citation numbers, out-of-range citations and altered quotes are rejected. **A genuine quote can still be irrelevant or wrong for the question.** This guard is not a semantic entailment checker.

## Run

Use the repository dependencies plus the tested CPU inference environment: torch 2.8.0, transformers 4.56.2. Obtain a licensed local Qwen2.5 snapshot separately; weights are not distributed.

```sh
PYTHONPATH=. python scripts/answer_question.py --snapshot "$QWEN_SNAPSHOT" --question '曹霸是哪个时期的画家？'
PYTHONPATH=. python scripts/evaluate_answering.py --snapshot "$QWEN_SNAPSHOT" --out reports/my-new-run
PYTHONPATH=. python scripts/evaluate_answering.py --out reports/answering-1_5b-v3 --recompute
python scripts/score_answering_detailed.py --run reports/answering-1_5b-v3 --protocol reports/answering-1_5b-v3/protocol.json
PYTHONPATH=. python scripts/evaluate_knowledge_update.py --snapshot "$QWEN_SNAPSHOT" --out reports/my-kb-update
```

All inference output directories must be new. Recompute needs no model inference. A previous code snapshot is archived and hash-checked for the initial strict-parser experiment.

## Fixed diagnostic and results

24 hash-selected questions from the existing CMRC holdout plus 8 explicitly authored missing-private-information probes; not a new independent benchmark. Fixed 160-character chunks, stride 80, Top-1 versus Top-3, greedy decoding, 80 generated tokens, CPU float32, 4 threads. The first hypothesis was that Top-3 would improve answer exact match without a refusal/support tradeoff.

| Model / parser | Top-1 answerable EM | Top-3 answerable EM | Top-1 false refusal | Top-3 false refusal | Missing-information correct refusal Top-1 / Top-3 |
|---|---:|---:|---:|---:|---:|
| 0.5B / strict JSON, original run | 0/24 | 0/24 | 23/24 | 24/24 | 8/8 / 8/8 |
| 0.5B / bounded-fence replay | 1/24 | 1/24 | 16/24 | 20/24 | 8/8 / 8/8 |
| 1.5B / bounded-fence, fresh inference | 4/24 | 4/24 | 11/24 | 17/24 | 8/8 / 7/8 |

Retrieval span coverage is 18/24 versus 22/24 for every model. It does not translate into an EM gain from Top-3. The parser comparison reuses identical saved generations and is a post-hoc engineering ablation, not fresh inference. The 1.5B comparison is exploratory after inspecting 0.5B failures. No blind generalization claim is made.

For 1.5B, 13 Top-1 and 8 Top-3 answers pass exact quote validation; only 4 in each arm cover the reference answer span in the correct document. The `citation_gold_support_rate` in the original metrics is the stricter joint exact-answer-and-citation metric; use `citation_decomposition.json` for independent quote validity and reference-span support. Neither metric establishes unrestricted semantic entailment. Mean generation/answer times were approximately 1.00s and 1.44s; these are local descriptive timings, not a throughput benchmark.

## Knowledge update and failures

The self-authored micro-KB changes a return period, preserves a shipping policy and adds service hours. It is separate from any private service project. `reports/knowledge-update-v1` preserves the 0.5B failures: converting 七天 to 7天 fails exact quote matching; after update, an administrator-password question receives a real but irrelevant return-policy quote. The 1.5B repetition is in `knowledge-update-1_5b-v2`: 6/8 exact outcomes, still below the predeclared all-eight threshold. One updated answer is refused; this is not a successful service-quality regression pass.

The pipeline is executable but answer quality is insufficient for unattended service. More retrieved context is not adopted as a quality improvement. An always-refuse comparator scores 8/32 overall and 0/24 answerable; the 1.5B Top-1 result is 12/32, still poor. Future improvements require separate development data and a fresh held-out evaluation, rather than repeatedly tuning these questions.
