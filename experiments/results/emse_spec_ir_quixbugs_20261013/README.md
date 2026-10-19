# SpecIR QuixBugs 输入批次（emse_spec_ir_quixbugs_20261013）

> **性质**：论文 Table 5（QuixBugs mutation 分数）复算链的**输入批次**——零 LLM
> 复算脚本 `experiments/emse_quixbugs_mutk_full.py` 的默认输入
> （`_INPUT_JSON`）。X 轮（2026-10-19）论文复现性闭环时入库：该脚本随论文
> Table 5 引用入库，但其默认输入此前不在工件包内，fresh clone 复算链断裂。

## 口径

- 数据集：QuixBugs Python 子集（`dataset=quixbugs`，50 程序）
- 跑批时间：2026-10-14 00:51（本地）；工作树与 provenance 见批次 JSON 内字段
- 消费方：`experiments/emse_quixbugs_mutk_full.py`（cosmic-ray 全变异体 Mut@k
  + 健全性前置门；输出 `experiments/results/emse_quixbugs_mutk_full_20261015/`）
- 复算（零 LLM，耗时以小时计——全变异体口径）：`python experiments/emse_quixbugs_mutk_full.py`

## 完整性

`SHA256SUMS` 覆盖本目录全部分发文件（批次 JSON + 逐任务 traces）；
`scripts/gates/checksum_results.py --verify --results-dir experiments/results/emse_spec_ir_quixbugs_20261013` 校验。
