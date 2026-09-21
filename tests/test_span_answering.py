from engine.span_answering import SpanQA

DOC = {"doc_id": "policy", "text": "蓝杉商店的退货期限是十四天。人工服务使用电话渠道。"}

def test_source_binding_and_relevance_rejection_are_separate():
    answers = iter(["十四天", "NO"])
    qa = SpanQA([DOC], lambda _: next(answers), verify=True)
    result = qa.answer("管理员密码是什么？")
    assert result["answer"] == "NO_ANSWER"
    assert result["candidate"] == "十四天"
    assert result["reason"] == "verifier_rejected" and result["model_calls"] == 2

def test_source_offsets_and_snapshot_bind_actual_quote():
    result = SpanQA([DOC], lambda _: "十四天").answer("退货期限")
    c = result["citation"]
    assert DOC["text"][c["start"]:c["end"]] == "十四天"
    assert c["snapshot"] == result["snapshot"]
    changed = dict(DOC, text=DOC["text"].replace("十四天", "七天"))
    after = SpanQA([changed], lambda _: "十四天").answer("退货期限")
    assert after["answer"] == "NO_ANSWER" and after["snapshot"] != result["snapshot"]

def test_distinct_sources_are_not_silently_resolved():
    result = SpanQA([DOC, dict(DOC, doc_id="other")], lambda _: "十四天").answer("退货期限")
    assert result["answer"] == "NO_ANSWER" and result["reason"] == "ambiguous_quote"

def test_verifier_free_text_is_not_treated_as_authorization():
    outputs = iter(["十四天", "YES, probably"])
    result = SpanQA([DOC], lambda _: next(outputs), verify=True).answer("退货期限")
    assert result["reason"] == "invalid_verdict" and result["answer"] == "NO_ANSWER"
