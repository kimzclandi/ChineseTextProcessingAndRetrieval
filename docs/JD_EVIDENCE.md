# 与岗位JD的对应关系

依据用户提供的两张招聘截图：阿里巴巴2027届AI数据工程师，北京/杭州，截图更新日期2026-08-24。这里只使用截图中的职责设计项目，不声明职位当前仍开放，也不把截图中的投递规则当作执行指令。

| JD要求 | 本项目实际交付 | 可检验位置 | 未覆盖边界 |
|---|---|---|---|
| 高性能、可复用处理算子与pipeline | 契约审查、原文offset保护、疑似联系方式隔离、精确去重、血缘、切块 | engine/quality.py、pipeline.py、retrieval.py | 本规模Ray不加速，无全模态算子 |
| Ray/Spark/Flink与调度/容错 | Ray Core本机4CPU、有界任务、worker退出重试、提交前进程中断恢复 | scripts/systems.py、reports/systems-v1 | 无Spark/Flink、跨机集群、流批一体 |
| 高质量数据/评测集建设 | 固定源hash、21道offset校验隔离、近重复家族、160/160划分 | data/source-v1、engine/dataset.py | 公共百科数据，无业务专家标签或全面语义去重 |
| 数据资产体系 | Parquet与JSONL、不可变快照、SQLite版本/血缘、增量缓存 | engine/pipeline.py、data/asset-v1 | 无权限治理平台、对象存储原子提交或EB规模 |
| 评测驱动数据优化 | 基线dev诊断→一次重叠切块→门槛冻结→holdout配对验证 | reports/retrieval-v1 | 指标为标注span检索覆盖，无模型训练收益 |
| Python与工程质量 | 31项测试、隔离复现、校验脚本、固定依赖、CI定义 | tests、scripts/reproduce.py、scripts/verify.py | 当前只有本机验证，线上CI未执行 |
| LLM、SFT、RAG等理解 | 解释数据加工对检索证据的影响；训练/量化经验由既有Domain QA Lab补充 | docs/INTERVIEW.md | 此项目没有生成器、embedding模型训练、RLHF/RLAIF |
| AI编程与完整交付 | AI辅助实现、运行、故障验证和审计，保留收益与负结果 | CONTRIBUTIONS.md、reports/RESULTS.md | 用户独立掌握尚未通过主动回忆验证 |

选择理由：继续做小规模LoRA调参会重复旧项目；这个项目增加的是“可恢复的数据资产生产 + 有质量门槛的数据迭代”。先做文本与结构化标注的可靠闭环，不把未做的视频、音频、3D数据宣称成全模态能力。
