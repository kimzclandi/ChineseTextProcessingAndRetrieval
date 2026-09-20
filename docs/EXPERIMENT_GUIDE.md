# 数据与检索结果复核指南

## 输入、输出与问题边界

输入记录包含字符串 `source_id`、`title` 和 `text`。问答及答案位置另行保存，答案不进入检索索引。输出包括合格文档、隔离原因、来源血缘、Parquet/JSONL、快照 manifest 和 SQLite 版本目录。本项目回答两类问题：加工结果能否可靠恢复和追溯，以及切块策略是否影响标注答案片段的取回。

```mermaid
flowchart LR
  A[固定来源与校验和] --> B[质量算子与稳定分片]
  B --> C[串行 / Ray 执行]
  C --> D[快照校验与 SQLite 登记]
  D --> E[保持原始 offset 的切块]
  E --> F[字符 BM25 检索]
  F --> G[开发集诊断与冻结]
  G --> H[一次留出评估: 修复 / 回归 / 成本]
```

## 指标该如何理解

| 指标 | 判断对象 | 不能替代的结论 |
|---|---|---|
| 文档 recall@3 | 是否取回标注原文档 | 不保证答案片段完整 |
| span-hit@3 | 返回块来自原文档且完整覆盖参考答案 offset | 不等于答案可推导或生成回答正确 |
| oracle span coverage | 切块本身是否保留完整参考答案 | 不代表实际检索器一定取回 |
| 查询耗时与块数 | 当前索引布局的成本 | 不代表生产并发吞吐 |

两种切块共用字符 BM25、同一语料和 top-3 预算；返回块最多含 480 个原始字符，重叠部分也占预算。留出集从 130/160 到 143/160，是修复 17 题并回归 4 题的净结果；同时文档召回少一题、索引变大、查询变慢。不能只保留正向覆盖率。

## 从结果追到实现

1. [数据卡](DATA_CARD.md)：核查来源、21 道问题的排除规则和家族隔离。
2. [完整结果](../reports/RESULTS.md)：核查开发/留出分母、配对回归和成本。
3. [检索实现](../engine/retrieval.py)：核对 offset 与 BM25 排名计算。
4. [流水线实现](../engine/pipeline.py)：核对缓存、快照提交和版本登记。
5. [架构说明](ARCHITECTURE.md)：区分 worker 重试、最终快照幂等和真正的多机执行。

## 按目的选择运行方式

| 入口（仓库根目录，已安装依赖） | 执行内容 | 写入与限制 |
|---|---|---|
| `PYTHONPATH=. .venv/bin/python scripts/verify.py` | 保存证据核验 | 只读，不是完整重跑 |
| `PYTHONPATH=. .venv/bin/python scripts/verify_portable.py` | 实际重算 BM25 排名并与保存值比较 | 不训练、不调参 |
| `PYTHONPATH=. .venv/bin/python scripts/reproduce_portable.py --output work/reproduce-02` | 串行重建全部语料并执行 8 道 dev 查询 | 新输出目录；不是完整留出评测 |
| `PYTHONPATH=. .venv/bin/python scripts/fetch_prepare.py --output work/fresh-source-02` | 固定官方源下载与抽样重建 | 需要网络；hash 不符必须失败 |

完整环境、Ray 和故障实验入口见[复现说明](REPRODUCE.md)。portable CI 不等于重新执行 Ray 进程故障实验。

## 关键约束与排障

- 不规范化原文空格或 Unicode 后继续沿用旧 offset；清洗可能破坏标注位置。
- 缓存或快照校验失败时，先保存错误和来源；不要重签 manifest 使检查通过。
- 同一 `source_id` 出现不同内容会拒绝提交，当前增量是 append-only，不支持更新或删除。
- 本地 Ray 较串行慢是已保留结果；当前规模没有并行加速证据。
- 留出集已用于一次最终检查，不再用它选切块参数。新迭代需要新的评估设计。
