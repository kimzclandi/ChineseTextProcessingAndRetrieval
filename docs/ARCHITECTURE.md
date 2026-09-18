# 架构与工程边界

输入契约为JSONL记录：source_id、title、text均为字符串；原始公开问答另行保存，答案不进索引。输出为文档、隔离原因、血缘、Parquet资产、不可变manifest和SQLite版本目录。

```mermaid
flowchart LR
  A[固定公开来源与SHA256] --> B[记录契约与规则审查]
  B --> C[内容哈希分桶与可复用分片]
  C --> D[串行或Ray有界任务]
  D --> E[精确去重与完整血缘]
  E --> F[临时快照与文件校验]
  F --> G[原子rename]
  G --> H[SQLite事务登记]
  H --> I[检索语料切块]
  I --> J[开发集诊断]
  J --> K[冻结一次改进]
  K --> L[留出集与配对回归]
```

## 五个重要设计决定

1. **保持原文offset**：不对text做NFC或去空格。标题归一化只用于分组，检索分词只用于索引；块仍携带原文start/end。否则“清洗正确”可能让标签位置全部错位。
2. **输入与副作用分离**：worker只做纯数据算子，driver持有文件写锁并完成快照提交。worker可能重复执行，不能把Ray重试叫exactly-once；幂等的是最终可见快照。
3. **分片可复用**：记录内容hash的前两位给出256个桶，桶内稳定排序，最多64行再拆分；追加通常只改变对应桶的分片。桶内插入或超过64行仍可能使该桶多个分片失效，不能保证每次只处理一条。
4. **读者以catalog为准**：提交前中断无版本可见；rename后catalog前中断留下未登记目录，重跑先验hash再登记。SQLite事务同时登记版本和血缘。没有全局“最新”指针，使用明确version查询。
5. **验证与模型收益分开**：只读重算核验、全量资产重建、BM25实际执行、Ray进程故障、真实业务效果是不同证据层级。

## 一致性、容错与增量语义

单机文件系统上使用flock单写者锁；缓存文件临时写入、fsync并replace。快照写完各文件后rename到versions目录，再向SQLite提交。不承诺对象存储或跨主机原子事务，也未做磁盘断电/目录fsync持久性测试。os._exit测试是进程中断，不是电源故障模拟。

版本ID来源于排序后输入、算子源码hash、batch_size。执行器不进语义版本ID，故串行和Ray应相同。parent只作生成沿革，不改变内容身份；同一内容再次导入复用原版本，不创建多份版本描述。

source_id出现不同内容时拒绝整次提交，避免把更新混成重复。当前增量仅append-only：**没有更新、删除、CDC、watermark、乱序事件或真实消息队列**。分片cache被篡改会阻止恢复，已发布文件或catalog manifest不一致会阻止读取/复用。

隔离记录只保存source_id、记录hash和原因，不复制可疑联系方式文本。输入原始文件属于独立的源资产，敏感来源仍需访问控制；本项目没有生产敏感数据。

## 资源与规模

Ray Core使用4个本地CPU、max_retries=2、最多8个在途任务，实现有限提交压力；不是完整的流处理背压系统。当前records、consolidation、近重复特征及BM25索引在driver内存中，仍有单进程全量状态和全局精确去重瓶颈。原始2,403文段的小规模对照上Ray较慢，调度/序列化/写盘可解释成本，但没有通过独立profiling证明各自占比。

扩展设计只能作为未来方案：分区去重、外部shuffle、对象存储提交协议、分布式索引和资源调度。没有这些运行证据，不写“可扩展到万亿/EB”。

## 血缘查询

reproduce会在work/reproduce-01/lake生成catalog.sqlite。该库的versions保存版本、manifest校验与相对路径；lineage保存(version, doc_id, source_id)。可以通过标准库sqlite3查询；真实输出例子见reports/systems-v1/result.json与data/asset-v1/lineage.jsonl。Parquet保存全部文档内容，JSONL作为可审阅且确定性的对应格式。
