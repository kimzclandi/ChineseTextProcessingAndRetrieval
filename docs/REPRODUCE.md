# 复现与验收边界

所有命令从源码根目录执行；Python3.12。项目是独立公开Git仓库，不与Extractive QA共享工作区。免费公开数据下载；没有模型下载或付费服务。

## 四种验证不能混淆

| 验证 | 命令/入口 | 实际做什么 |
|---|---|---|
| 保存证据核验 | scripts/verify.py | 重算指标/门槛、校验数据与源码，不启动模型或Ray |
| 实际检索重跑 | scripts/verify_portable.py | 重建BM25，重新执行640条query-arm检索并比较排名；不改参数 |
| 隔离资产复现 | scripts/reproduce_portable.py --output work/new-name | 串行重新处理全部2,403记录、写快照/Parquet/catalog，执行8道dev×两方案 |
| 从源重建 | scripts/fetch_prepare.py --output work/new-source | 实际下载固定train/dev、核对hash、重新审计和划分，比较六个产物 |

本轮已实际执行以上环节。隔离新环境仍在同一M4 Max上，不能称异机；Ray系统实验为原环境本机实测。发布时另外在GitHub Ubuntu runner上安装轻量CI锁定依赖，通过37项测试和640条query-arm重新检索。该范围属于异机检索核验，不是完整Ray流水线异机复现；未做Windows、跨机Ray、GPU、生成模型或训练。

```bash
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python -r requirements.lock.txt
.venv/bin/python -m pytest -q
PYTHONPATH=. .venv/bin/python scripts/verify_portable.py
PYTHONPATH=. .venv/bin/python scripts/reproduce_portable.py --output work/reproduce-01
PYTHONPATH=. .venv/bin/python scripts/fetch_prepare.py --output work/source-01
```

初版31项测试，首次发布后新增6项浮点比较边界测试；当前再补10项portable重建比较测试，共47项，覆盖真实数据证据、存储/增量/失败语义、检索边界、预测完整性及异常分数；合成fixture不混入正式检索指标。依赖锁为精确版本列表，不含wheel哈希；安装需要网络或预先缓存，不声称长期依赖可用或跨平台完全相同。

## 实际运行Ray加工

```bash
RAY_USAGE_STATS_ENABLED=0 .venv/bin/python -m engine.pipeline \
  --input data/source-v1/source-records.jsonl --lake work/ray-lake-01 --executor ray
```

使用本机4CPU；需要本地进程、端口权限，禁用Ray使用统计。SQLite版本在work/ray-lake-01/catalog.sqlite，产物在versions/<version>。相同输入重跑复用快照，已有快照被篡改会失败；这与scripts/reproduce对输出目录“必须新建”的规则不同：前者用于验证幂等，后者用于隔离实验。

## 冻结研究入口

scripts/study.py按build/dev/freeze/holdout阶段构建既有实验，正式路径已存在会拒绝覆盖。不要删除data或reports来执行这些入口。若未来开展新研究，先复制源码到独立目录、修改新协议并建立新版本目录，不重用本次holdout调参。历史协议提交与开发冻结提交见reports/RESULTS.md。

## 性能复现的可比性

保留Ray启动耗时与pipeline耗时的区别；串行/Ray各3次，顺序为S/R/R/S/S/R，输出hash相同。小于一秒的本地工作量容易受缓存和系统负载影响，报告中位数只是本轮描述，不是吞吐SLA。检索耗时从CPU查询开始，不含索引构建、网络或生成回答，首次用固定虚构查询预热一次。

## 跨平台浮点核验

推荐入口为scripts/verify_portable.py：先执行原冻结核验器，再重新检索。chunk ID及顺序必须完全一致；有限BM25分数使用相对/绝对容差各1e-12，任何排名变化或超差均失败。原scripts/verify.py --rerank保留逐浮点精确相等检查，Linux上可能因底层数学库舍入而失败。冻结源码、数据、配置、预测和指标没有修改。历史scripts/reproduce.py保留原精确比较语义；当前scripts/reproduce_portable.py采用同一分数容差，ID覆盖、排名、指标和资产字节仍要求完全相同。CI另执行完整串行资产重建及默认8道dev查询，不包括Ray执行。详见[发布记录](PUBLICATION.md)。
