# docstring 独立锚三臂实验判定报告（P1 / A-02）

> 预注册：`docs/study/DOCSTRING_ANCHOR_PREREG_2026-10-17.md`；本报告由 `experiments/emse_docstring_anchor_analysis.py` 直出（数字不得手写）。

## 1. 主判定（doc vs df）

**verdict：`not_confirmed`**

| 条件 | 结果 |
|---|---|
| 绝对线 doc detection ≥ 65% | 60.0%（met=False） |
| 单向 McNemar p < 0.05 | False |
| 方向 δ > 0 | False |

## 2. 检出率（41 缺陷程序口径，可判定子集）

| 臂 | detection | 可判定/41 行 |
|---|---|---|
| df（对照） | 86.1%（31/36） | 36/41 |
| doc（处理 A） | 60.0%（21/35） | 35/41 |
| union（处理 B） | 61.8%（21/34） | 34/41 |

## 3. 配对对比（精确 McNemar）

| 对比 | 配对 n | a 独有 : b 独有 | δ | 单向 p | 双向 p | BF10 | MDE |
|---|---|---|---|---|---|---|---|
| doc_vs_df（主） | 35 | 3:12 | -25.71pp | 0.9963 | 0.0352 | 3.6274 | 16.57pp |
| union_vs_df（次级） | 34 | 1:9 | -23.53pp | 0.999 | 0.0215 | 9.4961 | 16.81pp |

## 4. 审计面

- `spec_replace_applied` df：{"none": 50}
- `spec_replace_applied` doc：{"attempted_fallback": 9, "attempted_replaced": 41}
- `spec_replace_applied` union：{"attempted_fallback": 9, "attempted_replaced": 41}
- 分母：臂行 50 / 41 口径任务 41 / doc-vs-df 可判定配对 35
- 机制指标（次级，描述性）：由 `experiments/misguided_metrics.py` 产出（口径见 `docs/design/misguided_effective_metric.md`；目标 misguided 占比降幅 ≥30%）——与 detection 分开报告。

## 5. 披露

- MDE（n=可判定配对、80% power、α=0.05 近似）：见上表；设计敏感性与失败线见预注册 §3/§4。
- 单模型（deepseek-flash）/ QuixBugs 单数据集；跨批波动与 MDE 解读见预注册 §4。
- 数字由脚本从输入 JSON 复算，输入 sha256 见 JSON 报告 `inputs` 块。
