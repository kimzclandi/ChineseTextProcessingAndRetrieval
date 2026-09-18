# 官方来源与实际版本

核对日期2026-09-18。安装版本由requirements.lock.txt固定；官方latest文档可能比实际依赖新，不用其版本号冒充已安装版本。

- CMRC2018：[官方仓库](https://github.com/ymcui/cmrc2018)与[固定许可](https://raw.githubusercontent.com/ymcui/cmrc2018/c0eb1b6ba219847457e6af3180da722bbeb656af/LICENCE)。数据为公开阅读理解材料，非本项目企业数据；许可及改动见DATA_LICENSE.md。
- Ray：实测2.54.0，[官方任务容错说明](https://docs.ray.io/en/latest/ray-core/fault_tolerance/tasks.html)。本项目明确设max_retries=2，并实际验证worker进程退出后的重试，不依赖文档来替代实测。
- PyArrow：实测23.0.1，[官方Parquet读写说明](https://arrow.apache.org/docs/python/parquet.html)。用显式字符串schema与Zstd写出，实际检查串行/Ray相同字节。
- SQLite：Python3.12标准库提供，[官方原子提交说明](https://www.sqlite.org/atomiccommit.html)。本项目SQLite事务仅覆盖catalog内的版本与血缘；不能扩张为文件系统和数据库整体原子事务。

Ray/PyArrow为Apache-2.0开源组件；Python、SQLite和pytest按各自上游许可使用。项目不分发运行环境或上游二进制，源码包内只有自身代码与按CC BY-SA标明的衍生数据。
