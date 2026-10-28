# 更新日志归档（2026-10-28 GJ 轮搬出的旧条目）

> 本文件由 `CHANGELOG.md` 门面搬迁而来：**原文逐字保留，未删改**（FC 轮同型处置）。
> 门面只保留指针行，见 `CHANGELOG.md` 的 `[Unreleased]` 节。

- CI 作业预算补齐（DH 轮）：`ci.yml` 的 `smoke-llm` 是唯一没有 `timeout-minutes`
  的作业——LLM 端点挂起时会被平台默认的 360 分钟兜底回收；补 15 分钟预算，并新增
  `tests/test_ci_job_timeouts.py` 锁全部 workflow 作业的预算声明与 (0,60] 值域
  （3 例，先红后绿）。
- 引用键快照生成器漏计多键引用（DG 轮）：`render_snapshot` 按单键正则统计
  `\citep` / `\citet` 形态，正文 `\citep{a,b}` 组内的键被漏计（真实稿件 4 个多键组、9 个键位，
  低估 `konstantinou2026icst` 等 6 个受管键）；改为按组拆分计数，1 例测试锁先红后绿。
- 可选嵌入后端加载失败必须降级（DG 轮）：`sentence-transformers` 分支只捕 `ImportError`，模型下载失败 / 缓存损坏会击穿「不可用即 None」契约；现补同形降级并在显式选择该后端时告警，3 例测试锁先红后绿。
- 注释语义按文件类型分治（DE 轮）：TeX `%` 按反斜杠奇偶、Typst `//` 与可嵌套块注释、BibTeX 按括号深度且 `\"` 不切换字符串态；修复 `refs.bib` 注释被误算进上一条目字段值造成的假 CJK 红。
- 论文构建脚本前置判据改为 `--pre-build`：只跳过产物页数对账，源侧判据照常阻断，避免「编辑源文件后无法重建」的自锁。
- 外部读数登记册更正 `wang2026harnessreeval` 为 arXiv v4 并补齐 v1–v4 版本史；两处强否定改为「所核摘要与正文未见」。
