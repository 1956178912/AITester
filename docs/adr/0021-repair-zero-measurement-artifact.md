# ADR-0021: repair=0 围栏伪影定案——patch 透出口径与执行口径的清理分叉修复

- 日期：2026-10-07（修复引擎批次 VII）
- 状态：已采纳（Accepted——测量口径修复 + 存量重放工具）
- 关联：ADR-0017（修复引擎范式转向——动机勘误见本文末节）、ADR-0018（编辑意图最小 diff 口径）、`src/tools/patch_applier.py`、`experiments/_m1_metrics.py`、`experiments/repair_replay.py`

## 背景（Context）

第十七轮审查（2026-10-07，前沿对标报告）落地侦察中的一个**偶然发现**，经决定性重放实验定案：

1. **约定与分叉**：debugger 的 `state["patch"]` 保存 LLM JSON 原始值，项目约定该字段可含 ````` ```python ```` 围栏 / `python:` 前缀（类型修复层与编辑意图通道替换补丁时甚至**主动构造围栏形态**，debugger.py L655/L725）；写盘执行链路（`apply_patch_to_code` Step 1/2）负责清理。但 M1 独立裁决（`_target_code_after_patch`）与结果行透出**直接消费原始值，未经清理**。
2. **实测受染面**：10 个主批次工件 **274/274（100%）带补丁行的 patch 字段以 `"python\n"` 围栏残留开头**（`generated_test` 字段 974/974 全干净——仅 debugger 的 patch 通道受染）。
3. **决定性重放**（2026-10-07，本地 pytest，零 LLM）：
   - 原样执行（= 历史 repair_rate 口径）：**0/106 通过**——`python\n` 首行 NameError 击落全部补丁；
   - 与写盘同口径清理后执行：**51/106 通过**。
4. **全量重放**（`experiments/repair_replay.py`，10 批次 × aitester 臂）：可重放 266 行（= patch ∧ gold test_cases 双非空），**修正 correct = 103，修正 repair_rate = 38.7%**；E2 双种子批（161053/170147/181638/185941）稳定 **44.4%–53.8%**。plain_llm / plain_llm_df 两臂 patch 全空（不产补丁），其 repair=0 为真值，不受染。

即：**"repair 全线 0"的最大单一成分是测量层伪影，真实修复率在主批次存量上约 38.7%（E2 批次 44–48%）**。

## 决策（Decision）

1. **清理口径函数化为单一权威**：`patch_applier.normalize_patch_text()`（= 原 Step 1/2：`extract_code_block` + python 前缀剥离，幂等）；`apply_patch_to_code` 改为调用它（行为等价重构）。
2. **测量层修复**：`_m1_metrics._target_code_after_patch` 的完整文件分支经 `normalize_patch_text` 清理后返回——`detection_rate` / `repair_rate` / `false_fix_rate` / `regression_rate` 四指标的补丁应用口径与写盘链路对齐（干净补丁幂等，历史行为仅在受染输入上改变）。
3. **顺带加固**：`_PYTHON_PREFIX_RE` 补 `(?!\w)` 负向后瞻（与 helpers 既有正则对齐）——旧正则会把首行 `python_x = 1` 剥成 `_x = 1` 产出损坏代码；带后瞻后仅剥离独立 `python` / `python:` 前缀标签，严格减少误伤。
4. **存量重放工具**：`experiments/repair_replay.py`（零 LLM）——按修正口径重放存量批次工件，产出"原口径（伪影）vs 修正口径"对比报告；diff 形态补丁因存量行缺 instance_code 记 `not_replayable_diff`（诚实降级）；`Makefile` 增 `repair-replay` 入口。

## 后果（Consequences）

**正面**：

- "repair 全线 0"伪影定案并修复——修复引擎的优化目标从"0 → 破零"修正为"38.7% → 前沿水平"，基线重置；
- `state["patch"]` 的围栏约定保持不变（历史工件/写盘链路零破坏），仅测量口径对齐；
- 历史定案无需重跑即可勘误（重放工具读存量 JSON）。

**负面/风险**：

- **历史结论的连锁勘误**（须逐一登记）：E2 定案"次要终点 repair 全线 0 未破零"→ 修正为 44–48%（E2 双种子）；生死实验 R-P0-2 的 aitester 臂 repair=0 同受染（工件不在 main_batch 目录，待对其实际目录重放）；`false_fix_rate` 分布、IDR/CPR 的 correct 分母（correct>0 后 CPR 首次可定义）、弃权精确率"correct=0 按构造"的表述均需按修正口径重述；
- `detection_rate` 的 fixed 材料应用同经清理函数（干净材料幂等，理论无影响，但口径上多了一层转换）。

## 验证

- 批次 VII 测试锁 19 项（清理函数八态 / 测量口径修复 / apply 行为不变回归锁 / 重放工具五态 + 汇总数学 + CLI）；
- 受染面既有测试回归：M1 指标 / patch_applier / benchmark 相关 369 passed / 0 failed；
- 全量重放报告：`python -m experiments.repair_replay experiments/results/main_batch --arm aitester`（266 可重放 / 103 correct / 38.7%）。

## ADR-0017 动机勘误（承接"落地后须回收"纪律）

ADR-0017 背景 1"repair 全线 0"实为**伪影主导**（真实 38.7% 存量口径）。**范式转向不因此撤销**，理由：① 转向的其余动机（FL@1 35.8% 短板、H2c 结构性劣后、前沿共识范式）未受影响；② 修复引擎的落地资产（独立 FL / Top-3 排序 / 编辑意图 / 确定性路由 / 弃权门）对 38.7% 基线上的继续优化同样必要；③ **但第二阶段的优先级排序改变**：repair 已非"从零破冰"而是"38.7% → 提升"，反事实 FL 上界（若给对位置能否修好）与弃权门阻断档（压制错误补丁）的相对价值上升，"四子智能体重构"的紧迫性下降——重构前应先用修正口径重估漏斗。

## 修订记录

1. 2026-10-07 首次落地（批次 VII）：`normalize_patch_text()`（含负向后瞻加固）+ `_target_code_after_patch` 清理 + `experiments/repair_replay.py` + `Makefile::repair-replay` + 19 项测试；全量重放定案修正 repair_rate=38.7%（E2 双种子 44–48%）。
