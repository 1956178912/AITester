# 工件数据许可证声明（Replication Artifacts License）

`experiments/results/` 目录下的**数据与结果工件**（批次 JSON、统计报告、
Mut@k 工件、SHA256SUMS 校验和等）以 **CC0 1.0 Universal（CC0-1.0）**
发布——作者在法律允许范围内放弃全部著作权与相关权利，便利第三方
复现、再分析与引用。

- 完整法律文本：https://creativecommons.org/publicdomain/zero/1.0/
- 本目录中的**代码文件**（如有）遵循仓库根目录 `LICENSE`（MIT）；
- 第三方基准数据（QuixBugs、ULT 子集、Defects4J、SWE-bench）的
  原始语料**不整体收录**在本包内，其许可证由上游项目规定；
- **例外（F14 更正，2026-10-22）**：benchmark JSON 的 `task_metadata` 字段内嵌
  上游 `fixed` 源码与 gold `test_cases` 原文（例：QuixBugs
  `breadth_first_search` 的 `fixed` 与上游固定提交逐字节一致，SHA256
  `dccde51d…a172cf7`）。这些字段**不是派生产出**，分发时按上游许可证处理；
  包内其余内容（LLM 生成测试、判分结果、统计量）才是派生产出。此前"仅收录
  派生产出"的整包声明不成立，已按字段改为本说明（不作侵权判定）；
- 引用本包时请同时引用论文与 Zenodo DOI（归档后见
  `REPLICATION_PACKAGE.md` §6）。

AITester Contributors, 2026-10-16
