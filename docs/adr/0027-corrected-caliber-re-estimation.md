# ADR-0027: 修正口径重估收口——false_fix/CPR/弃权精确率首次非平凡 + 归因解混杂检验

- 日期：2026-10-07（修复引擎批次 XIII，ADR-0021 勘误义务的执行收口）
- 状态：已采纳（Accepted——全部零 LLM 存量回放，`make corrected-metrics`）
- 关联：ADR-0021（伪影定案）、ADR-0024（归因首测）、ADR-0020（弃权阻断档判据）、`experiments/corrected_metrics.py`

## 背景（Context）

ADR-0021 修正 correct 口径后登记了连锁勘误义务：false_fix 分布（原值由受染 repair 推导）、CPR（correct=0 时诚实未定义）、弃权精确率（correct=0 按构造=1.0 平凡值）——三者都有真实数字后，弃权阻断档与四开关 A/B 的转正判据才具备预注册条件。同时 ADR-0024 的归因首测结论（FL 命中与修复成功负相关）存在缺陷难度混杂的替代解释，须层内检验。

## 决策（Decision）

1. **行级修正规则**（`correct_row`）：patch 空 → 原指标语义本就正确（repair=0 非伪影），保留原值；patch 非空 → `repair_replay.replay_row` 重放，correct/wrong_patch 改三键（patch_correct/repair_rate/false_fix_rate），diff 形态/无 gold 材料/异常 → 三键改 None（不可测诚实降级，原受染值 0/1.0 废弃）；纯函数（原行不修改）。
2. **总报告**（`experiments/corrected_metrics.py`，`make corrected-metrics`）四节：修正 repair 按实验代际 / 修正 false_fix 分布 / CPR·IDR·弃权修正视角（复用 cpr_idr 判定核喂修正行）/ ADR-0024 归因的 bug_type 分层（解混杂）。第五节为四开关转正判据重定**建议**（显式标注非预注册——正式判据须预注册文档修订）。

## 首测定案（2026-10-07，main_batch 10 批次，aitester 臂 669 行）

| 量 | 修正值 | 含义 |
|---|---|---|
| repair（R-P0-2 三种子，145 可重放） | **35.86%**（52/145） | 生死实验"repair=0"勘误为 35.9% |
| repair（E1/E2 logic 档，106 可重放） | **48.11%**（51/106） | 双门批次修复率最高 |
| repair（早期 10-01 批，15 可重放） | **0/15 真零** | 该批历史 repair=0 非伪影——README 引用的"false_fix=89.8% 假成功通道"证据**维持成立** |
| 修正 false_fix（passed 可测 436 行） | **87.16%**（380/436） | 非平凡：56 行 passed 且 gold 裁决通过 |
| **CPR**（correct∩plausible 70 行） | **84.29%**（59/70） | 首次可定义——correct 行 11/70（15.7%）会被当前信号集阻断（**阻断档潜在误伤率的存量代理**） |
| **弃权精确率**（passed 压制 392 行） | **85.97%** | 首次非平凡——被压制"成功"中 86% 确为 false_fix（判据 ① 实证基础） |
| IDR（修正 incorrect 74 行） | 34.33% | 较原 27.78% 上升：15 个负信号行修正后 correct=1（信号集对 correct 行的保守误报实证） |
| bug_type 分层（assertion/runtime） | 层内 P(corr\|hit) 15.4%/16.7% < P(corr\|miss) 50%/91.7% | **负相关在层内成立——ADR-0024"生成侧主导"非纯难度混杂**（可分解层仅 2 个，n=53，结论为方向性） |

## 后果（Consequences）

**正面**：弃权阻断档与四开关 A/B 的转正判据首次具备真实分母；README/prereg 的 repair=0 主张获得精确的修正数字支撑；ADR-0024 结论经解混杂检验加固。

**负面/风险**：可分解层仅 2 个 bug_type（其余类型 FL/重放不可测）；CPR 分母限定 plausible∩correct（口径自洽但与总 correct=103 不同——33 个 correct 行 plausible=0，属"补丁有效但未写盘成功"的独立观测，未展开）；阻断档若按当前信号集直接开启将误伤 15.7% 的 correct 行——**必须先预注册阈值再转正**。

## 验证

- 批次 XIII 测试锁 13 项（修正四态/纯函数性/汇总数学/CPR 可定义/分层/代际标签/报告关键行/CLI）；
- 存量首测即上表（`make corrected-metrics`）。

## 修订记录

1. 2026-10-07 首次落地（批次 XIII）：`correct_row` + `analyze_arm` + `build_report` + Makefile 目标 + 13 项测试；四组修正数字定案（R-P0-2 35.9% / E2 48.1% / 早期批真零 / false_fix 87.2% / CPR 84.3% / 弃权精确率 86.0%）。
