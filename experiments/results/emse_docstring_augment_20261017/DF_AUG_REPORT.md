# 规格增广双臂实验判定报告（M-1，2026-10-17）

> 预注册：`docs/emse/EMSE_DOCSTRING_AUGMENT_PREREG_2026-10-17.md`；本报告由 `experiments/emse_docstring_augment_analysis.py` 直出（数字不得手写）。

## 1. 主判定（augment vs df）

**verdict：`not_confirmed`**

| 条件 | 结果 |
|---|---|
| 绝对线 augment detection ≥ 88% | 82.9%（met=False） |
| 单向 McNemar p < 0.05 | False |
| 方向 δ > 0 | True |
| 失败线（独立标记）augment detection < 78% | 未触发 |

## 2. non-inferiority（独立标记，不参与 verdict）

- 边界：配对 δ ≥ **-5.0pp**；实测 δ = **+2.86pp**；met = **True**

## 3. 检出率（41 缺陷程序口径，可判定子集）

| 臂 | detection | 可判定/41 行 |
|---|---|---|
| df（对照） | 80.6%（29/36） | 36/41 |
| augment（处理） | 82.9%（29/35） | 35/41 |

## 4. 配对对比（精确 McNemar）

| 对比 | 配对 n | a 独有 : b 独有 | δ | 单向 p | 双向 p | BF10 | MDE |
|---|---|---|---|---|---|---|---|
| augment_vs_df（主） | 35 | 4:3 | +2.86pp | 0.5 | 1.0 | 0.3125 | 16.57pp |

## 5. 审计面

- `spec_augment_applied` df：{"none": 50}
- `spec_augment_applied` augment：{"attempted_augmented": 40, "attempted_fallback": 10}
- `spec_replace_applied`（互斥核验，应全为 none）：{"augment": {"none": 50}, "df": {"none": 50}}
- 分母：臂行 50 / 41 口径任务 41 / augment-vs-df 可判定配对 35
- 机制指标（次级，描述性）：由 `experiments/misguided_metrics.py` 产出（口径见 `docs/design/misguided_effective_metric.md`）——与 detection 分开报告。

## 6. 披露

- MDE：n≈35（L 轮可判定配对先例）时 80% power / α=0.05 的双比例 MDE≈16.6pp；本设计属边缘功效——小于 MDE 的效应不可判定，阴性结果不得读作'无效应'；本批配对 n=35，MDE=16.57pp（reference n=35 时 16.57pp）。
- 单模型（deepseek-flash）/ QuixBugs 单数据集 / 单 seed；跨批波动与 MDE 解读见预注册 §4。
- 数字由脚本从输入 JSON 复算，输入 sha256 见 JSON 报告 `inputs` 块。
