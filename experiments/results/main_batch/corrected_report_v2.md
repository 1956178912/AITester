# 修正口径重估总报告 v2（ADR-0029 / R27 跨文件测量修复后重生成，零 LLM 存量回放）

> 本文件 = ADR-0027 报告（`experiments/corrected_metrics.py`）在 **R27 跨文件任务
> 测量修复**（2026-10-08 R2）后的**重生成版本**。与 v1 的差异：跨文件任务
> （synthetic Level 3/3.5）的伴生模块 module_a/b/c 现按 metadata 物化，
> gold 测试不再收集错误 → 跨文件行的 correct 由系统性 0 抬升为可测。
> 关键 v2 数字：R-P0-2 修正 repair **39.31%（57/145）**（v1：35.86%，52/145）；
> E1/E2 修正 repair **54.72%（58/106）**（v1：48.11%，51/106）。
> 口径矩阵与引用纪律见 `docs/design/repair_caliber_matrix.md`。



- 目录：`experiments/results/main_batch`（10 批次）；臂：`aitester`；行数：669
- 口径：ADR-0021 修正（normalize_patch_text 清理后 gold 裁决）；无补丁行的原指标语义正确（repair=0 非伪影），保留原值。
- 行级裁决分布：{'skipped_no_material': 8, 'no_patch': 395, 'wrong_patch': 151, 'correct': 115}

## 1. 修正 repair_rate（按实验代际）

| 代际 | 行数 | 带补丁 | 可重放 | 修正 correct | 修正 repair_rate |
|---|---|---|---|---|---|
| E1/E2 logic 档（10-07） | 348 | 106 | 106 | 58 | 0.5472 |
| R-P0-2（10-06 三种子） | 261 | 145 | 145 | 57 | 0.3931 |
| 早期批次 | 60 | 15 | 15 | 0 | 0.0000 |

## 2. 修正 false_fix 分布（passed 行）

- passed 可测行：436（不可测 7 行不计入分母）；
- **修正 false_fix 率：0.8716**（380/436）——历史口径（受染 repair 推导）下 passed 行恒 false_fix=1.0；

## 3. CPR / IDR / 弃权视角（修正 correct 口径）

- plausible 行：144；IDR（错误补丁带负信号比例）：0.3485
- **CPR（正确补丁保留率，correct>0 后首次可定义）：0.8451**（60/71）——弃权阻断档转正判据 ② 的分母
- 弃权视角：plausible 拦截面 0.7847；passed 压制 392/443
- **弃权精确率（修正，非平凡）：0.8597**——阻断档转正判据 ①（历史口径 correct=0 按构造=1.0 无信息量）

## 4. ADR-0024 归因的 bug_type 分层（解混杂检验）

谱系 FL 命中与修复成功的负相关是否为缺陷难度混杂——层内检验：

| bug_type | FL命中(对/总) | P(corr\|hit) | FL未命中(对/总) | P(corr\|miss) |
|---|---|---|---|---|
| assertion | 2/13 | 0.1538 | 11/22 | 0.5000 |
| runtime | 5/6 | 0.8333 | 11/12 | 0.9167 |

> 解读：若负相关在多数层内仍成立（P(corr|hit) < P(corr|miss)），
「ADR-0024 的生成侧主导结论非纯难度混杂；若层内消失，则 FL 命中率
本身是难度代理，归因须回到运行时反事实臂。」

## 5. 四开关转正判据重定建议（**建议非预注册**——正式判据须预注册文档修订）

修正基线（repair 38.7% 而非 0）下，既有转正判据须重定后才能跑 A/B：
- EDIT_INTENT_ENABLE / DETERMINISTIC_REPAIR_FIRST_ENABLE（ADR-0018/0019 判据「接管率>0 且 intent/确定性臂 patch_correct 不低于对照」）：
  修正口径下 patch_correct 非平凡——判据结构保留，分母口径改修正 correct；
- 弃权阻断档（ADR-0020）：转正判据 ①② 现有真实分母（本报告 §3），阈值取值待预注册；
- ORACLE_CONTEXT_TIER（ADR-0025）：不受伪影影响（spec_compile_rate 通道未受染），判据原样有效。

---
*报告生成：experiments/corrected_metrics.py（批次 XIII，ADR-0027）*
