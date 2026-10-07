# ADR-0020: 补丁弃权门——验证段"低置信不产补丁"（观测层先行，阻断档待 A/B 转正）

- 日期：2026-10-07（修复引擎批次 V，第十六轮审查 R16-4 落地）
- 状态：已采纳（Accepted——观测层；阻断档为 Proposed，A/B 后转正）
- 关联：ADR-0017（修复引擎三阶段·验证段）、`src/tools/patch_abstain.py`、`experiments/cpr_idr_report.py`、`experiments/run_benchmark.py`

## 背景（Context）

1. **IDR 首测定量化缺口**（批次 II）：错误补丁检测率 27.78%（40/144）——72% 的 plausible-but-wrong 补丁零负信号通过验证。
2. **弃权的实证收益**：Abstain and Validate（Google，ICSE-SEIP 2026，arXiv:2510.03217）——低置信弃权 + 补丁验证在 174 个真实 bug 上合计提升最多 39pp；Passerine（arXiv:2501.07531）"合理 73% vs 语义等价 43%"同指验证缺口。
3. **存量回放验证信号集有效**（本批首测，10 批次主工件）：would-be abstention 命中 passed 443 中的 392（88.5%），弃权精确率 1.0（correct=0 按构造）——信号集在**无 gold** 条件下于运行时几乎完整重构 false-fix 类（与历史 false_fix 89.8% 吻合）。

## 决策（Decision）

1. **判定核**（`src/tools/patch_abstain.py::evaluate_patch_abstention`，纯函数零 LLM）：五信号任一命中 → abstain——`test_regenerated_pass_unverified`（M5 假通过）/ `detection_first_status == "all_green_unverified"`（Y1 全程全绿）/ `specificity_gate_verdict == "over_red"`（终审过红）/ `patch_evidence_level == "none"`（证据零背书）/ `source_patched_unverified`（写盘未验证）。与 CPR/IDR 负信号同源（IDR 另含 rolled_back 等已拦截类信号，弃权门只看"接受时刻仍带病通过"）。
2. **观测层（本批）**：结果行新增 `patch_abstained` / `patch_abstain_signals`（失败分支 False/[] 占位，键集合同构）；`passed` 与主终点**历史口径零变化**（AN2 呈现性增补先例）；CPR/IDR 报告新增"弃权视角"节（存量工件即可回放 would-be abstention——拦截面 / passed 压制数 / 弃权精确率）。
3. **阻断档（Proposed，转正判据预注册后再接线）**：命中即回滚补丁 + 终态 `abstained`；转正判据 = ①弃权精确率（被压制"成功"中 false_fix 占比）≥ 预注册阈值，②不压制 gold 正确补丁（CPR ≥ 阈值），③A/B 批次（弃权门开/关 × 同任务集）确认调整后修复质量不降。

## 后果（Consequences）

**正面**：假成功通道首次获得**运行时**（非 gold 事后）识别器；弃权视角零成本回放存量工件；为阻断档提供精确率/误伤率的量化路径。

**负面/风险**：五信号中 `patch_evidence_level=="none"` 拦截面大（plausible 命中 78.5%）——阻断档若按当前信号集直接开启将压制 88.5% 的 passed（correct=0 时全部正确，但修复率破零后需 CPR 防误伤）；观测层语义与 IDR 部分重叠（刻意：同一信号族的两视角）。

## 验证

- 批次 V 离线锁（test_batch_v.py：五信号命中/可信值不触发/组合/None 保守/CPR 弃权数学/接线双分支）+ CPR/IDR 旧测试回归；
- 全量回归 4520→4530 / 0 failed。

## 修订记录

1. 2026-10-07 首次落地（批次 V 观测层）：`src/tools/patch_abstain.py` + 结果行 `patch_abstained`/`patch_abstain_signals` + CPR/IDR 弃权视角节 + 存量回放首测（passed 压制 392/443、精确率 1.0）。
