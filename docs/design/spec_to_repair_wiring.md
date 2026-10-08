# 规约 → 修复定向通道（R22）设计说明

- **日期**：2026-10-08
- **状态**：**待架构师设计**（本轮侦查判定"信号不足"，未落地实现）
- **关联**：`src/graph/nodes.py`（`_spec_oracle_exec_enabled` / `_append_spec_oracle_to_test` /
  `_debugger_node`）、`src/specs/spec_ir_v2.py`（`compile_spec_oracle`）、
  `src/agents/executor.py`（`failed_cases`）、`src/graph/state.py`、
  R2 §6.1（逻辑驱动缺口）、H3（"逻辑驱动"与"自修复"是否同一闭环）

## 1. 现状侦查（本轮实录）

| 环节 | 现状 | 结论 |
|------|------|------|
| 规约 oracle 执行 | `SPEC_ORACLE_EXEC_ENABLE=true` 时，`compile_spec_oracle` 产物被**追加到 `generated_test` 尾部**并列执行 | 违例以**普通测试失败**形式进入执行循环（间接接通） |
| oracle 产物形态 | **单一**测试函数 `test_specir_v2_oracle`，全部可编译子句合并在内；子句文本仅作**注释**（`# pre: <clause>` / `# post: <clause>`） | 无"每子句一个测试"的粒度 |
| 执行输出 | `executor.parse_failed_cases` 产出 `failed_cases=[{"name": "test_specir_v2_oracle", "error": <traceback>}]`；该列表**已进入** `state["failed_cases"]`，`_debugger_node` 已消费它（FL 谱系定位、RAG 检索） | 有"哪个测试失败"的粒度，**无"哪个子句违例"**的粒度 |
| 违例字段 | `state` 仅有 `spec_oracle_injected: bool`；无 per-clause 违例字段；结果行无 spec 违例键 | **缺口：无 `spec_violation_clauses` 结构化信号** |
| 子句文本可达性 | pytest traceback 只回显**编译后的断言表达式**（如 `assert not (r < 0)`），不回显相邻注释里的 NL 子句文本 | 从错误文本**无法**还原违例子句 |

**判定**：R22 目标"违例子句摘要注入 Debugger prompt"所需的**子句级结构化信号当前不存在**。
失败案例粒度（`test_specir_v2_oracle` 整体失败 + 编译断言文本）虽存在，但不构成
"违例子句摘要"。**按任务约定不硬做**，交付本设计说明，标记"待架构师设计"。

## 2. 缺口清单（实现前必须补齐）

1. **子句级归属**：oracle 产物需把每个可编译子句**与其文本绑定**，使其在失败时可被判出。
2. **结构化透出**：执行侧需把"违例子句文本"提取为 `state` 观测键（如
   `spec_violation_clauses: list[str] | None`），与结果行键集合同构。
3. **定向通道**：Debugger prompt 需一个**默认关**的专项段，仅在开关打开且有违例时注入。

## 3. 推荐方案（A：assert 消息注入子句文本）

**最小侵入点 = `compile_spec_oracle` 的断言生成**：把子句文本写进断言的失败消息，
使 pytest 输出天然携带子句文本，执行侧零解析歧义：

```python
# spec_ir_v2._compile_single_clause 产物（示意）
assert not (r < 0), "[SPEC-VIOLATION][precondition] assert r >= 0"
```

- **执行侧**：`executor.parse_failed_cases` 已解析 `{name, error}`；在 `_executor_node`
  追加一次轻量扫描（正则 `\[SPEC-VIOLATION\]\[(?P<kind>\w+)\]\s*(?P<clause>.+)`），
  产出 `spec_violation_clauses`（去重，仅当 `test_specir_v2_oracle` 失败时非空；
  无违例/未启用 → None，键集合同构，零默认行为变化）。
- **state 键**：`spec_violation_clauses: list[str] | None`（`create_initial_state` 默认 None）。
- **修复通道**：`SPEC_REPAIR_CHANNEL_ENABLE`（默认 false）——`_debugger_node` 读取该键，
  非空且开关开时，构造"确定性规约违例"专项 prompt 段（子句列表 + 提示"修复须使规约
  oracle 通过"，与既有 FL 先验段并列、不替换）。config.py 注册 + `make env-budget` 预算内。
- **本地化锚点（可选增强）**：`_compile_single_clause` 同时把子句所属函数/行范围写入消息，
  供 `patch_localized` 复用（与 R4 通道协同，但 R4 已阴性归档，非必须）。

**优点**：改动集中在编译层 1 处 + 执行层 1 次扫描 + state/config/debugger 各 1 处；
失败消息即信号，无需脆弱源码行映射；零默认行为变化（默认关 + 键 None）。
**成本**：0.5–1 天 + 测试（oracle 产物文本断言、违例提取、开关注入、零回归）。
**风险**：oracle 产物文本变化会触及既有 `test_spec_ir_v2.py` 的产物断言 → 需同步更新测试；
断言消息含子句文本，须确认无 prompt 注入面（子句来自 SpecIR 白名单，非外部自由文本，
但仍应与注入防护一致处理）。

## 4. 备选方案（B：源码行映射，不推荐）

用 `compile_spec_oracle` 产物的行号 ↔ 子句注释映射，从 traceback 行号反查子句。
**不推荐**：依赖 pytest traceback 行号稳定性、`-q --no-header` 输出格式、多平台差异，
脆弱且难测；且一旦断言被 `patch_test_hacking`/格式化改写即失效。

## 5. 交付判定

- 本轮：**未落地实现**（信号不足，遵循"不要硬做"）；本文件为设计输入。
- 下一步（建议）：由架构师评审方案 A 后，按"观测层先行"（ADR-0020/0028 先例）落地
  ——先只透出 `spec_violation_clauses` 观测键（零行为变化），A/B 确认无害后再开
  `SPEC_REPAIR_CHANNEL_ENABLE` 转正通道。
- 与预注册的关系：任何"修复率提升"主张须走 E9 类预注册实验，不得由本观测通道直接宣称。
