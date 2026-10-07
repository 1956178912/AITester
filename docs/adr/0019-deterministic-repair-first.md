# ADR-0019: 确定性优先修复路由——syntax/import/name-error 类失败先走零 LLM 变换器

- 日期：2026-10-07（修复引擎批次 IV，第十六轮审查 R16-5 落地）
- 状态：已采纳（Accepted，`DETERMINISTIC_REPAIR_FIRST_ENABLE` 默认关、灰度 A/B 后转正）
- 关联：ADR-0017（修复引擎三阶段·合成段）、ADR-0018（编辑意图落盘）、ADR-0003（默认关惯例）、`src/tools/deterministic_repair.py`、`src/graph/nodes.py`

## 背景（Context）

1. 修复循环对所有失败类别整轮进 LLM，但其中一部分存在零 token 确定性修法（To Run or Not to Run，arXiv:2606.26978：执行/验证应按成本调度——"不必要的服务调用"是 token 浪费主源）。
2. PAGENT（ACM DL 2026）实证针对性确定性层可挽回 22.8% 的类型相关失败补丁；Syntax Repair as Language Intersection（arXiv:2507.11873）证明语法修复可确定性化。
3. E2 的 MAST 分布：assertion 23% / runtime 15.6% / type_error 11.3% / syntax 3.4%——runtime/syntax 中 NameError·ImportError·缩进混用三类有确定性通道。

## 决策（Decision）

1. **类别路由 + 三个保守变换器**（`src/tools/deterministic_repair.py`，全部零 LLM）：
   - `missing_import_inference`：`NameError: name 'X' is not defined` ∧ X ∈ 标准库白名单 ∧ 目标以词边界使用 X ∧ 顶层无 `import X` → 在最后一个顶层 import 后插入（无 import 时插到 docstring 后）；
   - `import_alias_backfill`：`cannot import name 'X'` ∧ 目标顶层**恰一个**同前缀重命名嫌疑符号 Y（多重嫌疑 → 保守放弃）→ 模块级追加 `X = Y`（P3 契约回填启发式复用）；
   - `tab_indent_normalize`："inconsistent use of tabs and spaces" ∧ 目标含制表符 → 全量归一 4 空格。
2. **统一验证门**：候选必须过 `ast.parse` 且 ≠ 原码，否则弃用（`attempted=True / patch_code=None / reason=validation_failed:*`）。
3. **接线（每任务至多一次）**：`DETERMINISTIC_REPAIR_FIRST_ENABLE`（默认关）开启时，`_debugger_node` 在调用 LLM 前先走本路由；产出候选则**跳过该轮 LLM 调用**（省 token），补丁照常进入既有 executor 回归验证；`state["deterministic_repair_status"]` 非 None 即不再进（哨兵语义，防同签名无限重试），确定性补丁无效后自然回落 LLM 路径。
4. **结果同构**：确定性结果经 `build_deterministic_debug_result` 构造，与 `debug()` 返回**键集合同构**（下游专家池/类型修复层等读取不缺键）；`deterministic_repair_status` 结果行透出（实验层统计接管率与省 token 量）。

## 后果（Consequences）

**正面**：命中类别零 token 修复；每任务一次哨兵防重试；失败原子回落（无半接管状态）；为 L2/L3 基准（BugsInPy/SWE Lite 的 import/syntax 类真实缺陷）预置通道。

**负面/风险**：白名单外的 NameError 不接管（刻意保守——不为任意未知名造补丁）；变换器命中面在 synthetic 上预计偏低（主类别 assertion/type 无确定性修法）——接管率指标若长期为 0，本层仅在 L2/L3 生效，属预期而非缺陷；与专家池/辩论叠加时确定性结果会被多采样覆盖（初始 A/B 不同时开启）。

## 验证

- 批次 IV 离线锁 18 项（三变换器命中/放弃/验证门、结果键集合同构、接线与哨兵存在性、开关缺省）；
- 全量回归 4502→4520 / 0 failed；接管率真实测量待 A/B 批次（synthetic + QuixBugs，同任务集 × {开, 关}）。

## 修订记录

1. 2026-10-07 首次落地（批次 IV）：`src/tools/deterministic_repair.py` + `_debugger_node` 确定性优先门 + `state["deterministic_repair_status"]`（哨兵语义）+ 结果行透出 + 18 项测试。
