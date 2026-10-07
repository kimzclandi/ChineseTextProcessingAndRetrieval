# 中文文本数据处理与检索评测：证据索引

规范仓库：[ChineseTextProcessingAndRetrieval](https://github.com/kimzclandi/ChineseTextProcessingAndRetrieval)。旧名chinese-evidence-data-engine在冻结报告、历史提交与兼容记录中保留，不重写历史。

| 表述 | 代码 | 报告／原始记录 |
|---|---|---|
| 2,403文段、10,142候选问题、21条偏移异常 | [数据准备](../engine/dataset.py)、[质量检查](../engine/quality.py) | [固定来源清单](../data/source-v1/manifest.json)、[数据卡](DATA_CARD.md) |
| span-hit@3 81.25%→89.38%；文档recall@3 95.625%→95.00% | [BM25及切块](../engine/retrieval.py) | [完整报告](../reports/RESULTS.md)、[160题两臂原始预测](../reports/retrieval-v1/holdout/) |
| 块数+40.14%；查询中位7.50→12.04 ms | [检索实现](../engine/retrieval.py) | [块与索引记录](../reports/retrieval-v1/)、[质量与成本](../reports/RESULTS.md#质量与成本) |
| 内容哈希、不可变快照、SQLite血缘、幂等与恢复 | [pipeline](../engine/pipeline.py)、[原子JSON](../engine/common.py) | [历史系统原始记录](../reports/systems-v1/result.json)、[初始构建一致性](../reports/build-v1/result.json) |
| 后续2-CPU Ray、256分片、worker退出重试、六项字节一致 | [独立执行器核对](../scripts/check_executor_parity.py) | [逐项结果](maintenance/2026-09-22-readiness/evidence/readiness-parity-result.json)、[执行日志](maintenance/2026-09-22-readiness/evidence/engine-ray.log)、[哈希清单](maintenance/2026-09-22-readiness/evidence/manifest.json) |
| staging链接拒绝、原子写入故障回归 | [staging测试](../tests/test_staging_publish.py)、[原子写入测试](../tests/test_atomic_json.py) | [失败与修复记录](maintenance/2026-09-22-detail/README.md)、[后续记录](maintenance/2026-09-22-readiness/README.md) |

2-CPU结果的JSONL、Parquet、输入哈希、血缘、manifest与隔离记录逐字节一致；worker退出/重试发生在该轮真实语料检查。driver resume、重复投递、篡改拒绝、孤儿快照恢复属于另列的历史系统实验，不把全部故障说成同一轮2-CPU实测。孤儿恢复是模拟rename后catalog登记缺失，不是断电测试。

Ray在原固定小规模实验慢于serial，初始化另计；后续带故障注入的2-CPU核对不是性能对照。span-hit是标注证据覆盖，不是答案正确率；切块数、索引统计也发生变化，不能只归因于边界覆盖。个人项目与AI辅助范围见[贡献说明](../CONTRIBUTIONS.md)。

## 验收范围

```sh
python -m pytest -q
PYTHONPATH=. python scripts/verify_portable.py
python .github/scripts/test_doc_links.py
python .github/scripts/check_docs.py
git diff --check
```

[原CI定义](../.github/workflows/offline.yml)还执行隔离的portable串行重建；它不重写冻结输出，不运行新的Ray性能实验。轻量CI未安装Ray，不能称为2-CPU故障实验的新一次执行。历史2-CPU证据以源hash、清单和原始日志核验。
