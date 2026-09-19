# Chinese Evidence Data Engine

可恢复、可追溯的中文证据数据流水线：公开中文数据寻源 → 质量与重复审计 → Ray本地加工 → Parquet/JSONL数据资产与SQLite血缘 → 检索失败分析 → 一次切块改进 → 冻结后留出集评测。

核心是数据算子、不可变快照、血缘与评测驱动迭代（Evaluation-Driven Development）。无付费API、云GPU、模型训练或生成式回答；指标是检索证据覆盖，**不是大模型回答准确率、CMRC官方成绩或业务收益**。

## 已运行结果

输入为固定版本CMRC2018公开train，2,403篇文段、10,142道候选问题。21道问题未通过非空/原文offset校验，在评测抽样前排除；不删除对应文段。检测到一对高相似文段并合并评测家族，最终2,402个家族。开发/留出各160题、每家族最多一题。原Domain QA Lab使用的CMRC dev只作旧来源排除，不用于本项目评分或选参。

| 指标 | 不重叠160字符切块 | 160字符、步长96的重叠切块 |
|---|---:|---:|
| 开发集 span-hit@3 | 132/160 = 82.50% | 142/160 = 88.75% |
| 留出集 span-hit@3 | 130/160 = 81.25% | 143/160 = 89.38% |
| 留出集原文档 recall@3 | 153/160 = 95.625% | 152/160 = 95.00% |
| 留出集 oracle span coverage | 89.38% | 100.00% |
| 切块数 | 8,775 | 12,297 |
| 留出集查询中位耗时 | 7.50ms | 12.04ms |

两组相同字符BM25、同语料、top3、最多480个原始字符；重叠内容重复占用预算。span-hit要求返回块来自标注原文档且完整覆盖某个参考答案的原始offset。它只表明标注证据可被取回，**并不证明返回内容足以推导答案或生成器能答对**。

留出集净增加13题（+8.125个百分点），其中修复17题、回归4题；文档召回少1题。索引块数增加40.14%，查询变慢。开发集预登记门槛通过后才冻结并检查留出集，不依据留出集继续挑参数。[完整结果与逐题证据](reports/RESULTS.md)。

## 数据系统实测

- **真实Ray Core任务**：单机4CPU、最多8个在途任务；纯函数算子、256个稳定内容哈希桶、每分片最多64行。未使用Ray Data流式执行、Spark/Flink或多机集群。
- **确定性**：真实语料的Ray/串行文档、隔离记录、血缘、Parquet与manifest逐字节相同。
- **版本与恢复**：内容/算子哈希寻址分片缓存，临时目录生成完整快照后原子rename，SQLite事务登记版本与血缘。读者只认已登记且hash通过的快照；重试幂等。
- **故障注入**：真实worker执行`os._exit(73)`后重试成功；子进程提交前退出后恢复；重复投递；增量追加；篡改检测；模拟rename后未登记窗口的恢复，六项均通过。
- **增量fixture**：追加1条后复用84个分片，只加工1个分片，与全量重建文档字节相同。该结果来自明确标注的合成工程fixture，不是业务样本。
- **性能负结果**：真实2,403行、每种执行器3次，串行中位约13,078行/s，Ray约11,968行/s；**本规模没有加速证据**。Ray初始化单列，测量包含本地写盘，不是集群吞吐。

真实语料没有精确重复或联系方式规则命中，因此不宣称清洗删除率带来模型收益。近重复只合并评测家族，不盲删不同原文及其offset。规则隔离的PII边界见[数据卡](docs/DATA_CARD.md)。

## 快速开始

Python3.12，完整锁在macOS arm64实测。无模型、API key或GPU要求；首次安装依赖需要网络。建议预留1GB磁盘；未测最低硬件配置。必须在源码根目录运行，不用`python -O`。

```bash
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python -r requirements.lock.txt
.venv/bin/python -m pytest -q
PYTHONPATH=. .venv/bin/python scripts/verify.py
# 真正重新执行BM25检索，再与保存排名比较；不调参、不写旧报告
PYTHONPATH=. .venv/bin/python scripts/verify_portable.py
# 重新加工全部语料并执行8道dev查询，输出隔离且拒绝覆盖
PYTHONPATH=. .venv/bin/python scripts/reproduce_portable.py --output work/reproduce-01
```

证据核验只读；reproduce是实际运行，二者不能混称。Ray故障实验已真实运行，重跑需要本机进程/端口权限。轻量CI使用requirements-ci.lock.txt，检查测试、冻结证据与640条query-arm重新检索，并运行portable串行资产重建；这不代表Ray跨机、模型推理或全流程异机复现。[发布与兼容性记录](docs/PUBLICATION.md)。

实际从固定官方源重新下载并重建抽样：

```bash
PYTHONPATH=. .venv/bin/python scripts/fetch_prepare.py --output work/fresh-source-01
```

下载hash不匹配会失败，不能静默换源。正式data/reports是冻结证据，批量study脚本拒绝覆写既有轮次；不要删除旧结果来重跑。任意新工作使用work子目录。[完整复现说明](docs/REPRODUCE.md)。

## 代码与文档

| 实现 | 内容 | 文档与证据 |
|---|---|---|
| `engine/quality.py`、`engine/dataset.py` | 质量隔离、精确去重、来源血缘、近重复家族与切分 | [数据卡](docs/DATA_CARD.md) |
| `engine/pipeline.py` | Ray/串行执行、分片缓存、不可变快照、SQLite登记与恢复 | [架构](docs/ARCHITECTURE.md) |
| `engine/retrieval.py` | 字符BM25、原始offset证据覆盖、配对修复/回归 | [完整结果](reports/RESULTS.md) |
| `scripts/reproduce_portable.py`、`scripts/verify_portable.py` | 隔离重建与跨平台排名核验 | [复现指南](docs/REPRODUCE.md) |

[AI辅助与贡献](CONTRIBUTIONS.md) · [数据许可](DATA_LICENSE.md) · [上游来源](docs/SOURCES.md) · [发布记录](docs/PUBLICATION.md)

本项目关注数据资产与检索证据生产；[Domain QA Lab](https://github.com/kimzclandi/domain-qa-lab)独立研究LoRA、响应蒸馏和量化。这里的检索覆盖收益不等于大模型训练提升。实现限于单机批处理，尚未验证多机、流批一体、图像音频算子或生产部署。

[2026-09-19 工程维护与验证边界](docs/maintenance/2026-09-19/README.md)
