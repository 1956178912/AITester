# docstring 独立锚三臂实验判定报告（P1 / A-02）

> 预注册：`docs/study/DOCSTRING_ANCHOR_PREREG_2026-10-17.md`；本报告由 `experiments/emse_docstring_anchor_analysis.py` 直出（数字不得手写）。

## 1. 主判定（doc vs df）

**verdict：`not_confirmed`**

| 条件 | 结果 |
|---|---|
| 绝对线 doc detection ≥ 65% | 65.7%（met=True） |
| 单向 McNemar p < 0.05 | False |
| 方向 δ > 0 | False |

## 2. 检出率（41 缺陷程序口径，可判定子集）

| 臂 | detection | 可判定/41 行 |
|---|---|---|
| df（对照） | 80.6%（29/36） | 36/41 |
| doc（处理 A） | 65.7%（23/35） | 35/41 |
| union（处理 B） | 73.5%（25/34） | 34/41 |

## 3. 配对对比（精确 McNemar）

| 对比 | 配对 n | a 独有 : b 独有 | δ | 单向 p | 双向 p | BF10 | MDE |
|---|---|---|---|---|---|---|---|
| doc_vs_df（主） | 35 | 4:9 | -14.29pp | 0.9539 | 0.2668 | 0.5811 | 16.57pp |
| union_vs_df（次级） | 34 | 3:5 | -5.88pp | 0.8555 | 0.7266 | 0.3516 | 16.81pp |

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
