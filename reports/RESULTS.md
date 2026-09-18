# 真实运行结果：中文数据资产与一次检索数据改进

本轮没有训练或生成模型。指标是公共阅读理解语料上的标注证据检索覆盖，不是CMRC官方分数或业务QA准确率。所有质量结果来自实际执行BM25，保留逐题排名、评分、fix/regression。

## 预登记与冻结

- d1aed99：研究范围、唯一候选、系统故障检查与门槛预登记。
- 5ab8dbf：固定公开源hash、质量规则和源码实现；尚未检索评测。
- 9aa7cb1：真实数据资产及160/160家族查询已冻结。
- 80263ba：提交开发集结果和采用决定。
- c9f111c：保存freeze.json后才执行holdout；未据holdout追加调参。

## 质量与成本

| 集合/方案 | n | span-hit@3 | 文档recall@3 | MRR@3 | oracle coverage | 中位查询ms | p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| dev/baseline | 160 | 82.50% | 97.50% | 0.94896 | 90.62% | 6.65 | 13.52 |
| dev/candidate | 160 | 88.75% | 96.88% | 0.94896 | 99.38% | 10.67 | 20.55 |
| holdout/baseline | 160 | 81.25% | 95.62% | 0.93125 | 89.38% | 7.50 | 14.70 |
| holdout/candidate | 160 | 89.38% | 95.00% | 0.93125 | 100.00% | 12.04 | 22.54 |

top3、最多480原始字符，两方案共用相同语料和字符BM25。切块从8,775增至12,297（+40.14%），索引统计量也改变，因此结论归因于切块策略整体，不是仅边界一个变量的纯因果分离。

开发集门槛：span-hit至少+2个百分点、文档recall最多-1个百分点、块数比例<=1.8。实际检查{'doc_recall': True, 'index_cost': True, 'span_gain': True}，选择candidate。该研究门槛不代表业务SLA。

开发集修复13、回归3；holdout修复17、回归4，净增13题。没有显著性/统计等价或全业务泛化声明。

### 失败切片

| 集合/方案 | 成功 | 边界或答案太长导致oracle缺失 | 未取回原文档 | 取到错误块 |
|---|---:|---:|---:|---:|
| dev/baseline | 132 | 15 | 4 | 9 |
| dev/candidate | 142 | 1 | 5 | 12 |
| holdout/baseline | 130 | 17 | 7 | 6 |
| holdout/candidate | 143 | 0 | 8 | 9 |

切片是可计算症状，非唯一根因证明。oracle缺失优先归入边界/长答案，即使该题也没有检索到原文档；各类互斥、和为160。span命中也不保证语义蕴含或生成器答对。

## Ray/串行和工程故障

| 顺序 | 执行器 | wall秒 | 行/秒 |
|---|---|---:|---:|
| 1 | serial | 0.193036 | 12448.48 |
| 2 | ray | 0.197791 | 12149.16 |
| 3 | ray | 0.200782 | 11968.18 |
| 4 | serial | 0.183740 | 13078.28 |
| 5 | serial | 0.180940 | 13280.61 |
| 6 | ray | 0.218300 | 11007.81 |

中位吞吐：串行13078.28行/s，Ray11968.18行/s；本工作量没有Ray加速证据。系统实验Ray启动1.864秒单列，不计入表中温运行。包括本地写盘，只有单机三次/执行器，无并发服务、峰值内存或多机结论。

六个系统检查：
- real_worker_exit_retried: PASS；细节保存在systems-v1/result.json。
- duplicate_delivery_idempotent: PASS；细节保存在systems-v1/result.json。
- driver_exit_resume: PASS；细节保存在systems-v1/result.json。
- incremental_equal_full_rebuild: PASS；细节保存在systems-v1/result.json。
- tamper_rejected: PASS；细节保存在systems-v1/result.json。
- orphan_publish_recovery: PASS；细节保存在systems-v1/result.json。

worker退出和driver子进程退出是真实进程操作；rename后catalog缺失为隔离fixture中删除登记来模拟该窗口，并非断电。初始fixture104条：100个唯一文档、1个重复、3个隔离；增量追加1条后复用84分片、加工1分片。所有fixture只用于工程行为测试，没有参与检索质量报告。

## 证据索引

- data/source-v1/manifest.json：固定源、21道位置异常审计、2,402家族和确定性划分。
- data/asset-v1：冻结文档、Parquet、血缘、隔离记录与manifest。
- build-v1/result.json：真实Ray/串行五项字节一致。
- retrieval-v1/baseline-diagnosis.json：先保存基线dev症状，再执行预登记候选。
- retrieval-v1/{baseline,candidate}：完整块、dev排名/分数与索引大小。
- retrieval-v1/freeze.json：dev采用决定、源码/协议/holdout/块hash。
- retrieval-v1/holdout：两候选全部160题排名、分数和配对变化。
- systems-v1/result.json与execution/systems.log：实际worker重试、恢复、增量与六次性能。

## 结论与未完成项

项目证明了本机文本数据资产生产和恢复流程可运行，一次固定切块策略改善了此留出集的标注span覆盖。未证明神经模型能力提升、真实业务效果、完整PII检测、全模态、流批一体、对象存储一致性或多机扩展。后续如需业务结论，应取得业务材料、审查标签与SLA并另冻结协议；不继续用本holdout挑参数。
