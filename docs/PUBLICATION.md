# 公开发布与线上验证

项目公开至[GitHub](https://github.com/kimzclandi/ChineseTextProcessingAndRetrieval)。发布记录日期为2026-09-19（Asia/Singapore；Actions日志为UTC前一日）。

## 实际验证

- 初次发布提交：f41a1ebbe68ce062b698270ca73de60b03fc8acf。
- [首次CI失败记录](https://github.com/kimzclandi/ChineseTextProcessingAndRetrieval/actions/runs/35373687737)：冻结核验器使用浮点精确相等，Linux重算在TRAIN_2286_QUERY_1报错。
- 修复提交：bddc8512a27853eb1cbfd797251dfef3d264ecd6。
- [修复后CI通过记录](https://github.com/kimzclandi/ChineseTextProcessingAndRetrieval/actions/runs/35374050968)：Ubuntu 24.04、CPython 3.12.14，轻量锁定依赖安装成功，37项测试通过。
- 640条query-arm实际重新检索，所有有序chunk ID完全一致；1,920个分数中42个存在舍入差异，最大绝对差2.842170943040401e-14。本机同样通过37项测试与640条重算，分数差为0。

新增scripts/verify_portable.py保留原核验器，先审计全部冻结哈希、数据划分、指标和门槛，再重算检索。仅有限浮点分数允许rel_tol=abs_tol=1e-12；排名改变、明显分数改变、NaN或无穷均拒绝，新增测试覆盖这些失败条件。底层libm跨平台舍入是对该现象的解释，未将容差用于指标或排名。

## 证据边界

原data/、reports/、configs/与冻结源码未改写。旧报告中的“未公开”“31项测试”等为发布前快照；当前状态以README、本页和对应提交的Actions记录为准。原v1 ZIP保留其提交和哈希，不冒充新版发布包。

线上执行范围为依赖安装、37项测试、保存证据核验及BM25重算。没有在线重跑Ray故障注入、全量源下载与加工，也没有训练或生成模型。因此可称“Linux异机检索验证”，不能称完整流水线异机复现、生产部署或业务效果验证。

## 当前复现入口

`scripts/reproduce_portable.py`在独立`work/`目录重新生成完整串行资产并执行默认8道dev查询。它复用已有有限分数容差，严格比较预测ID覆盖、排名、非计时指标及JSONL/Parquet资产字节。原`scripts/reproduce.py`仍保留冻结的精确浮点比较语义。当前CI增加portable重建；本地47项测试、640条query-arm重新检索及串行重建通过，远端状态以当前提交的Actions为准。此入口不运行Ray。
