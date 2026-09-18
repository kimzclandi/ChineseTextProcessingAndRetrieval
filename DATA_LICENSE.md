# 数据许可与来源归属

数据与报告中的原文、问题、答案来自CMRC2018，按 **Creative Commons Attribution-ShareAlike 4.0 International（CC BY-SA4.0）** 提供，不适用代码MIT许可。

作者：Yiming Cui、Ting Liu、Wanxiang Che、Li Xiao、Zhipeng Chen、Wentao Ma、Shijin Wang、Guoping Hu。基础百科材料的上游贡献者归属按原数据来源保留。

- 官方仓库：https://github.com/ymcui/cmrc2018
- 固定源版本：c0eb1b6ba219847457e6af3180da722bbeb656af
- 许可原文：https://raw.githubusercontent.com/ymcui/cmrc2018/c0eb1b6ba219847457e6af3180da722bbeb656af/LICENCE
- 本地完整许可：[data/SOURCE_LICENSE.txt](data/SOURCE_LICENSE.txt)
- 论文：Cui et al. (2019), A Span-Extraction Dataset for Chinese Machine Reading Comprehension, https://aclanthology.org/D19-1600/

本地改动：从官方train抽取文段、保留原问题ID及原文offset；增加内容hash/血缘/本地split，精确重复合并与近重复家族标识，构建160/160评测子集，生成重叠/非重叠切块及Parquet格式。原文与所选问题/答案文字未手工改写。21题在抽样前未通过参考答案校验，排除清单可审阅。

以上许可同样覆盖data/source-v1、data/asset-v1、reports/retrieval-v1中的来源内容及其加工形式。再分发须保留归属、来源、修改说明及相同许可。系统故障fixture为程序生成的虚构内容，联系方式使用example.invalid，不是业务数据。

新仓库尚未公开；当前授权仅为本地构建、验证。公开上传另需用户授权。
