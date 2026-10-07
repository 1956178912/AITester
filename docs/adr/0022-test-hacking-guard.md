# ADR-0022: test-hacking 确定性守卫（观测层）——硬编码分支/断言弱化/吞异常三信号

- 日期：2026-10-07（修复引擎批次 VIII，第十七轮审查建议 6）
- 状态：已采纳（Accepted——观测层；阻断档 Proposed，A/B 后转正）
- 关联：ADR-0020（弃权门——同族"假成功识别器"）、ADR-0021（修正口径后的 patch 后代码）、`src/tools/patch_test_hacking.py`、`experiments/run_benchmark.py`

## 背景（Context）

1. **验证缺口的作弊子类**：IDR 27.78%（批次 II）量化了"plausible-but-wrong 补丁零负信号通过"，其中一类是**test hacking**——为通过测试而作弊（硬编码特定输入的输出、删除/弱化断言、吞异常），在自生成测试验收口径下零负信号。TDFlow（EACL 2026）将 test hacking 计为失败（其 800 次运行 7 例的数字**未经本仓一手核验**，仅作方向锚点）。
2. **既有防线不覆盖**：危险 API 守卫（安全向）、命名契约守卫（签名向）、弃权门（验证证据向）均不识别"补丁语义上是在绕过测试"的形态。
3. **确定性可行性**：三类作弊形态均为可静态判定的 AST 结构（差集口径与危险 API 守卫同模式——只看补丁新引入的结构，原有结构不误报）。

## 决策（Decision）

1. **检测核**（`src/tools/patch_test_hacking.py::detect_test_hacking`，纯 AST 差集、零 LLM）三信号：
   - `hardcoded_input_branch`：新增 if 分支，条件为「表达式 == 常量」或「表达式 in 全常量元组」，体为单一 return 常量（else 臂存在时须同为常量 return）——特定输入→固定输出后门；泛化解（改表达式/走通用逻辑）不命中；
   - `assert_weakened`：原码 assert 计数 > 补丁后（删除即弱化）；
   - `exception_swallow_added`：新增 except 且体为 pass / 单一常量 return（记日志/重抛/走逻辑的有意义处理不命中）。
2. **保守降级**：无补丁 / 无原码 / 任一侧解析失败 → `{"suspected": False, "signals": []}`（与弃权门口径一致）。
3. **观测层接线**：结果行新增 `test_hacking_suspected` / `test_hacking_signals`（失败分支 False/[] 占位，键集合同构）；补丁后代码经 `_target_code_after_patch`（批次 VII 修正口径）取得；`passed` 历史口径零变化（AN2 呈现性增补先例，纯检测零行为影响不设开关）。
4. **阻断档（Proposed）**：命中即拒绝补丁——转正判据 = 观测层出数后「误伤率（gold correct 补丁被标记占比）≤ 预注册阈值 ∧ 命中行 false_fix 富集度显著」。

## 后果（Consequences）

**正面**：作弊补丁首次获得确定性识别器；三信号零成本零 LLM；差集口径保证"原有结构零误报"。

**负面/风险**：
- `if x == 0: return 0` 型**合法边界处理**理论上可命中 hardcoded_input_branch（条件是常量等值且体是常量返回）——误伤率正是阻断档 A/B 的核心判据，观测层数据决定转正与否；
- **存量不可回放**：存量结果行不含 `instance_code` 原码，差集无法计算（与 repair_replay 的只需补丁后代码不同）——观测数据从下一跑批起累积；
- 跨文件任务只检测被调方模块补丁（当前管线单文件口径）。

## 验证

- 批次 VIII 测试锁 18 项（三信号命中/差集不误报/合法修复不命中/降级四态/组合信号/接线双分支契约）；
- 观测层首测待下一跑批（存量不可回放已披露）。

## 修订记录

1. 2026-10-07 首次落地（批次 VIII 观测层）：`src/tools/patch_test_hacking.py` + `run_benchmark` 结果行接线（成功实算/失败占位）+ 18 项测试。
