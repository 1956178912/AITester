# 目标质量存量重放报告（零 LLM，只读工件）

> 生成：`python -m experiments.target_quality_replay experiments/results/main_batch`　口径：只读存量批次 JSON，不补值、不外推、不调用 LLM。
> 用途：把**已采集但未登记**的被测代码覆盖率 / 变异得分 / 规约可编译率固化为可引用数字，供 BASELINE.yaml 登记与对外对标。

## 被测代码覆盖率（`coverage`）

| 批次 | aitester | plain_llm | plain_llm_df |
|------|------|------|------|
| benchmark_synthetic_20261001_112528.json | 89.6（n=5） | 70.4（n=5） | — |
| benchmark_synthetic_20261001_112801.json | 91.6（n=5） | 70.4（n=5） | — |
| benchmark_synthetic_20261001_121523.json | 93.6（n=50） | 86.0（n=50） | — |
| benchmark_synthetic_20261006_140906.json | 88.2（n=87） | 94.9（n=87） | 90.0（n=87） |
| benchmark_synthetic_20261006_151907.json | 84.0（n=87） | 97.2（n=87） | 92.8（n=87） |
| benchmark_synthetic_20261006_164357.json | 84.8（n=87） | 97.1（n=87） | 93.6（n=87） |
| benchmark_synthetic_20261007_161053.json | 86.4（n=87） | 94.9（n=87） | 83.2（n=87） |
| benchmark_synthetic_20261007_170147.json | 90.6（n=87） | 97.1（n=87） | 81.5（n=87） |
| benchmark_synthetic_20261007_181638.json | 86.4（n=87） | 94.9（n=87） | 83.2（n=87） |
| benchmark_synthetic_20261007_185941.json | 90.6（n=87） | 97.1（n=87） | 81.5（n=87） |

## 变异得分（`mutation_score`）

| 批次 | aitester | plain_llm | plain_llm_df |
|------|------|------|------|
| benchmark_synthetic_20261001_112528.json | n/a（n=0） | n/a（n=0） | — |
| benchmark_synthetic_20261001_112801.json | n/a（n=0） | n/a（n=0） | — |
| benchmark_synthetic_20261001_121523.json | n/a（n=0） | n/a（n=0） | — |
| benchmark_synthetic_20261006_140906.json | 0.976（n=81） | 0.971（n=87） | 0.986（n=87） |
| benchmark_synthetic_20261006_151907.json | 0.930（n=79） | 0.951（n=87） | 0.993（n=87） |
| benchmark_synthetic_20261006_164357.json | 0.958（n=80） | 0.992（n=87） | 0.989（n=87） |
| benchmark_synthetic_20261007_161053.json | 0.859（n=77） | 0.971（n=87） | 0.997（n=79） |
| benchmark_synthetic_20261007_170147.json | 0.818（n=81） | 0.992（n=87） | 0.987（n=76） |
| benchmark_synthetic_20261007_181638.json | 0.859（n=77） | 0.971（n=87） | 0.997（n=79） |
| benchmark_synthetic_20261007_185941.json | 0.818（n=81） | 0.992（n=87） | 0.987（n=76） |

## 变异体检出率（`mutation_detection_rate`）

| 批次 | aitester | plain_llm | plain_llm_df |
|------|------|------|------|
| benchmark_synthetic_20261001_112528.json | n/a（n=0） | n/a（n=0） | — |
| benchmark_synthetic_20261001_112801.json | n/a（n=0） | n/a（n=0） | — |
| benchmark_synthetic_20261001_121523.json | n/a（n=0） | n/a（n=0） | — |
| benchmark_synthetic_20261006_140906.json | 0.886（n=13） | 0.699（n=7） | 0.929（n=38） |
| benchmark_synthetic_20261006_151907.json | 0.871（n=15） | 0.900（n=3） | 0.930（n=36） |
| benchmark_synthetic_20261006_164357.json | 0.795（n=13） | 0.833（n=6） | 0.923（n=43） |
| benchmark_synthetic_20261007_161053.json | 0.763（n=14） | 0.699（n=7） | 0.929（n=38） |
| benchmark_synthetic_20261007_170147.json | 0.770（n=17） | 0.833（n=6） | 0.923（n=43） |
| benchmark_synthetic_20261007_181638.json | 0.763（n=14） | 0.699（n=7） | 0.929（n=38） |
| benchmark_synthetic_20261007_185941.json | 0.770（n=17） | 0.833（n=6） | 0.923（n=43） |

## 规约可编译率（`spec_compile_rate`）

| 批次 | aitester | plain_llm | plain_llm_df |
|------|------|------|------|
| benchmark_synthetic_20261001_112528.json | n/a（n=0） | n/a（n=0） | — |
| benchmark_synthetic_20261001_112801.json | n/a（n=0） | n/a（n=0） | — |
| benchmark_synthetic_20261001_121523.json | n/a（n=0） | n/a（n=0） | — |
| benchmark_synthetic_20261006_140906.json | n/a（n=0） | n/a（n=0） | n/a（n=0） |
| benchmark_synthetic_20261006_151907.json | n/a（n=0） | n/a（n=0） | n/a（n=0） |
| benchmark_synthetic_20261006_164357.json | n/a（n=0） | n/a（n=0） | n/a（n=0） |
| benchmark_synthetic_20261007_161053.json | 0.205（n=77） | n/a（n=0） | n/a（n=0） |
| benchmark_synthetic_20261007_170147.json | 0.219（n=81） | n/a（n=0） | n/a（n=0） |
| benchmark_synthetic_20261007_181638.json | 0.205（n=77） | n/a（n=0） | n/a（n=0） |
| benchmark_synthetic_20261007_185941.json | 0.219（n=81） | n/a（n=0） | n/a（n=0） |

## 表达式通道覆盖率（`spec_expr_coverage`）

| 批次 | aitester | plain_llm | plain_llm_df |
|------|------|------|------|
| benchmark_synthetic_20261001_112528.json | n/a（n=0） | n/a（n=0） | — |
| benchmark_synthetic_20261001_112801.json | n/a（n=0） | n/a（n=0） | — |
| benchmark_synthetic_20261001_121523.json | n/a（n=0） | n/a（n=0） | — |
| benchmark_synthetic_20261006_140906.json | n/a（n=0） | n/a（n=0） | n/a（n=0） |
| benchmark_synthetic_20261006_151907.json | n/a（n=0） | n/a（n=0） | n/a（n=0） |
| benchmark_synthetic_20261006_164357.json | n/a（n=0） | n/a（n=0） | n/a（n=0） |
| benchmark_synthetic_20261007_161053.json | 0.741（n=45） | n/a（n=0） | n/a（n=0） |
| benchmark_synthetic_20261007_170147.json | 0.723（n=51） | n/a（n=0） | n/a（n=0） |
| benchmark_synthetic_20261007_181638.json | 0.741（n=45） | n/a（n=0） | n/a（n=0） |
| benchmark_synthetic_20261007_185941.json | 0.723（n=51） | n/a（n=0） | n/a（n=0） |

## 天花板饱和告警

- 未发现饱和指标。

## 检出与特异性门（跨批次合计）

| 臂 | 检出阳性/可测 | 检出率 | 特异性门分布 |
|----|--------------|--------|--------------|
| aitester | 79/605 | 13.1% | over_red=66、specific_red=40 |
| plain_llm | 11/658 | 1.7% | over_red=38、specific_red=4 |
| plain_llm_df | 279/571 | 48.9% | over_red=140、specific_red=162 |

> 读法：`specific_red` = 测试在 buggy 上红且在 fixed 上绿（缺陷特异）；`over_red` = 过红（buggy/fixed 均红，非特异）。两者之比是检出质量的核心观测。

> **口径警告**：上表跨全部批次**跨代际**合计（含早期 10-01 批次与 E1/E2 logic 档），仅作**描述性概览**，**不是当前对外口径**。对外引用 detection 一律以 `docs/design/repair_caliber_matrix.md` 与 `statistical_report_3seed_pooled.md` 的口径编号为准（aitester 15.8% / plain_llm_df 44.8%，n=261/臂）。遵守该矩阵 §3 引用纪律。

- 各臂累计任务行数：aitester=669、plain_llm=669、plain_llm_df=609

*报告生成：experiments/target_quality_replay.py（R5 审查批次，零 LLM）*