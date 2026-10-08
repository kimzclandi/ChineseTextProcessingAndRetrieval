# 保持检索结果的 BM25 查询优化

2026-10-08，Codex 辅助实现、执行与分析。新增可选 `PreparedBM25`，历史 `BM25`、切块、索引、评测和所有负结果原样保留。

## 改了什么

1. 在构建索引时预计算每个词的 IDF 和每个 chunk 的长度归一化项，减少查询内重复计算。
2. 使用 `heapq.nsmallest(k)` 选取 top-k，保留 `(-score, chunk_id)` 的并列顺序。
3. 保留逐词、逐 posting 的遍历及浮点运算顺序。同一运行环境中，候选与基准分数及排序要求精确相等。

代价是额外 O(V+N) 的索引状态及构建工作（V 为词表大小，N 为 chunk 数）。未测峰值 RSS，不声称降低内存或加快建库。
索引是 build-once/query-many；与历史实现一样，构建后不得原地修改 rows、k1 或 b。

## 固定实验

[协议](../configs/bm25-exact-performance-v1.json)与实现先提交于 `abdf6c9`，再执行一次；没有结果后调参。
固定已有两套 chunk 索引及 dev/holdout 各160题，共 **640 个 query-index 对、1,920 个 top-3 分数**，结果精确一致。
既有 holdout 在此仅用于检验实现等价，不做切块选择、模型质量改进或外部确认。

| 索引 | 原实现中位数 | 新实现中位数 | 加速比 | 更快轮数 |
|---|---:|---:|---:|---:|
| baseline chunks | 6.507 ms | 3.473 ms | 1.874× | 5/5 |
| candidate chunks | 10.050 ms | 5.397 ms | 1.862× | 5/5 |

计时为 5 轮逐查询中位数的中位数，每轮随机臂顺序，两臂使用相同随机查询顺序，排除建库和正确性比较。
两套索引均通过预定 ≥1.05× 且 ≥4/5 轮更快的门槛。这是本机固定语料的查询优化，不代表端到端 QA 或线上吞吐。
不要用本轮的 5.397 ms 替换旧实验的 12.04 ms：环境、执行时点和计时协议不同；性能比较只能使用同轮两臂。
原来 span-hit 的收益、文档 recall 的退化、chunk 增长和 Ray 负结果均继续成立。

## 使用与证据

```python
from engine.common import read_jsonl
from engine.prepared_bm25 import PreparedBM25

index = PreparedBM25(read_jsonl('reports/retrieval-v1/candidate/chunks.jsonl'))
hits = index.search('查询文本', k=3)
```

- [实现](../engine/prepared_bm25.py)、[对照程序](../scripts/benchmark_prepared_bm25.py)、[随机语料及边界测试](../tests/test_prepared_bm25.py)。
- [逐次计时](../reports/bm25-exact-performance-v1/timings.json)、[逐题精确结果](../reports/bm25-exact-performance-v1/equivalence.json)、[汇总](../reports/bm25-exact-performance-v1/summary.json)、[来源与输入哈希](../reports/bm25-exact-performance-v1/run.json)。

```bash
python scripts/benchmark_prepared_bm25.py verify --output reports/bm25-exact-performance-v1
python -m pytest -q
```

验证会重新执行两种检索器并要求同机精确一致；与 macOS 归档分数跨平台比较时沿用仓库既有的 `1e-12` 浮点容差，chunk ID 与顺序仍精确一致。
离线验证不是重新计时。新的性能执行必须使用新目录。

## 配对顺序验收修复（2026-10-08）

旧验收只核对 timing cell、查询集合和中位数，未验证执行顺序。将一臂的查询顺序反转，或改写记录的臂顺序，仍会得到相同的合格结论；这不能支持协议要求的同轮配对随机顺序。回归检查先在旧实现复现了 8 种应拒绝却被接受的情况。

当前验收从冻结 seed 重放原执行程序的随机顺序，同时核验全部轮次的实际记录顺序、声明的臂顺序和两臂查询顺序，并拒绝重复查询身份及布尔／浮点轮次编号。[回归测试](../tests/test_bm25_performance_contract.py)包含未修改的原始归档及顺序、seed、身份异常；历史 timing、源代码快照和汇总不变，没有重新计时或修改门槛。

该检查证明归档记录符合冻结调度，不是对计时进程的独立追踪，也不能证明未记录的机器负载或消除共享硬件噪声。查询性能结论仍限于原来的一次固定实验。
