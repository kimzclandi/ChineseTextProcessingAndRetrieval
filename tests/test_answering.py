import json
from engine.answering import EvidenceQA
DOCS=[{"doc_id":"a","text":"实验客服的退货期限为七天。"}]
def test_source_citation_and_update():
    generator=lambda _:json.dumps({"answer":"七天","citation":1},ensure_ascii=False)
    old=EvidenceQA(DOCS,generator).answer("退货期限")
    assert old["answer"]=="七天" and old["citation"]["start"]==10
    new=EvidenceQA([{"doc_id":"a","text":"实验客服的退货期限为十四天。"}],generator).answer("退货期限")
    assert new["answer"]=="NO_ANSWER" and new["reason"]=="unsupported_quote" and new["snapshot"]!=old["snapshot"]
def test_fence_is_bounded_and_citation_is_not_inferred():
    for raw in ['说明：{"answer":"七天","citation":1}','{"answer":"七天"}','{"answer":"七天","citation":2}']:
        assert EvidenceQA(DOCS,lambda _:raw).answer("退货期限")["answer"]=="NO_ANSWER"
    raw='```json\n{"answer":"七天","citation":1}\n```'
    assert EvidenceQA(DOCS,lambda _:raw).answer("退货期限")["answer"]=="七天"
