"""Authored micro-KB regression, not the inaccessible private customer-service repo."""
import argparse,json,time,hashlib
from pathlib import Path
from engine.answering import EvidenceQA,LocalGenerator
ap=argparse.ArgumentParser();ap.add_argument("--snapshot",required=True);ap.add_argument("--out",type=Path,required=True);a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=False)
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+"\n")
old=[{"doc_id":"returns","text":"蓝杉商店的退货期限是七天。"},{"doc_id":"shipping","text":"蓝杉商店使用顺丰快递发货。"}]
new=[{"doc_id":"returns","text":"蓝杉商店的退货期限是十四天。"},old[1],{"doc_id":"hours","text":"蓝杉商店的人工客服营业时间是九点到十八点。"}]
queries=[{"id":"updated","question":"蓝杉商店的退货期限是多久？","before":"七天","after":"十四天"},
{"id":"stable","question":"蓝杉商店使用什么快递发货？","before":"顺丰快递","after":"顺丰快递"},
{"id":"new","question":"蓝杉商店的人工客服营业时间是什么？","before":"NO_ANSWER","after":"九点到十八点"},
{"id":"missing","question":"蓝杉商店的内部管理员密码是什么？","before":"NO_ANSWER","after":"NO_ANSWER"}]
write(a.out/"protocol.json",{"version":"authored-kb-update-v1","before":old,"after":new,"queries":queries,
"hypothesis":"fresh snapshot updates changed facts, retains stable answers, exposes new facts and refuses unknowns",
"success":"all eight expected outputs match; old source offsets never accepted in new snapshot",
"failure":"any stale or incorrect answer or false refusal; preserve it","scope":"self-authored 3-document diagnostic, not private service evidence",
"frozen_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())})
generator=LocalGenerator(a.snapshot);rows=[]
for version,docs in [("before",old),("after",new)]:
 qa=EvidenceQA(docs,generator)
 for q in queries:
  result=qa.answer(q["question"]);rows.append({"id":q["id"],"version":version,"expected":q[version],"correct":result["answer"]==q[version],"result":result})
  write(a.out/"results.json",rows)
print(json.dumps([{k:r[k] for k in ["id","version","correct"]} for r in rows],ensure_ascii=False))
