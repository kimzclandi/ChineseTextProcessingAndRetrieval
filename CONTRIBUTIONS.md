# 贡献与 AI 辅助开发

项目使用 Codex 辅助设计实验协议、编写代码与文档、安装依赖、执行数据处理和故障注入、核验检索结果及维护发布流程。AI 辅助参与实现与执行；本项目不声称独立研发基础框架或原创检索算法。

CMRC2018 作者提供数据；Ray 提供任务执行与重试；PyArrow 提供 Parquet；Python/SQLite 提供运行与资产目录；pytest 提供测试。BM25、SimHash、Jaccard 与内容寻址均采用已有方法。上游来源见 [SOURCES](docs/SOURCES.md)，数据归属与再分发条件见 [DATA_LICENSE](DATA_LICENSE.md)。

可检查的项目工作包括数据算子、单机快照与恢复协议、检索对照实验和跨平台核验。实现和实验范围以 [README](README.md)、[架构](docs/ARCHITECTURE.md)及冻结结果为准。保留性能负结果、检索回归和原始证据；CI 核验不等于重新运行 Ray 故障实验或验证生产规模。
