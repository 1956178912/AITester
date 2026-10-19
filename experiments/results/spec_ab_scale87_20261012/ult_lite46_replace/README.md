# ULT lite46 replace 输入批次（spec_ab_scale87_20261012/ult_lite46_replace）

> **性质**：论文 Table 5（ULT gold 参照"不可用"结论）复算链的**输入批次**——
> 零 LLM 复算脚本 `experiments/emse_ult_gold_diagnosis.py` 的默认输入
> （`_LITE46_JSON`）。X 轮（2026-10-19）论文复现性闭环时入库：该脚本（含测试
> 契约）此前已在库，但其默认输入不在工件包内，fresh clone 复算链断裂。

## 口径

- 数据集：ULT-lite46（`spec_ab_scale87` 系列的 replace 臂，46 任务）
- 跑批时间：2026-10-12 21:40（本地）； provenance 见批次 JSON 内字段
- 消费方：`experiments/emse_ult_gold_diagnosis.py`（gold 材料在 fixed 修订上
  的可执行性诊断；论文 Table 5 题注"gold material fails on the fixed revision
  in 71/71 tasks"的复算依据）
- 复算（零 LLM）：`python experiments/emse_ult_gold_diagnosis.py`

## 完整性

`SHA256SUMS` 覆盖本目录全部分发文件（批次 JSON + raw + 逐任务 traces）；
`scripts/gates/checksum_results.py --verify --results-dir experiments/results/spec_ab_scale87_20261012/ult_lite46_replace` 校验。
