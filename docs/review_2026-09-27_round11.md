# 2026-09-27 第十一轮功能批次：错误分类 16→17 类 + 2.2 补丁重采样 + 1.3 降级链透传 + 五污染检测 + 2.1 mypy 静态层（默认行为不变）

> 范围：`src/agents/` + `src/graph/` + `src/tools/` + `experiments/` + `tests/`。
> 原则：**默认行为不变**（所有新能力均有独立环境变量开关，默认关闭；修复项仅修正
> 隐藏缺陷）；**保守可落地**（每项改动有最小回归测试锁定）；**全量回归零失守**
> （1937 测试全通过 / ruff 全绿 / mypy 全绿）。

---

## 一、基线（进入本轮前）

| 指标 | 数值 | 来源 |
|------|------|------|
| 全量测试 | **1920 passed / 0 failed** | 第十轮 `a1a06ec` 实测 |
| 静态检查 | ruff 全绿 / mypy 0 错误（62 源文件） | 第十轮基线 |
| 错误分类 | 16 类（10 文本类 + 2 状态细化 + 2 多候选/轨迹 + P0 4.1 子类 2） | `error_classifier.ErrorCategory` |

---

## 二、本轮改动清单（按方向）

| # | 方向 | 默认行为 | 开关 |
|---|------|----------|------|
| 1 | 5.2 错误分类 16 → 17 类（新增 `PATCH_SYNTAX_INVALID`） | 否（新类别） | 无（枚举扩展） |
| 2 | 2.2 补丁后处理重采样 | 否（历史单补丁口径） | `PATCH_RESAMPLE_ENABLE`（默认 false） |
| 3 | 1.3 分层压缩降级链透传 | 否（仅记录缺失符号） | `CONTEXT_TIER_DOWNGRADE_ENABLE`（默认 false） |
| 4 | 五、多维度污染检测 + Token 效率 | 否（保守 "low"） | 无（benchmark 结果字段扩展） |
| 5 | 2.1 mypy 静态层 | 否（仅 ast 静态层） | `TYPE_CHECK_ENABLE`（默认 false） |
| 6 | 修复 `on_resample` → `resample_fn` 关键参数名 | 否（修复隐藏缺陷） | 无 |
| 7 | `build_tiered_context` tier-0 `str\|None` → `str` | 否（行为等价） | 无 |
| 8 | `AITesterState` 声明 4 个新键 | 否 | 无 |

---

## 三、5.2 错误分类 16 → 17 类

- **新增类别 `PATCH_SYNTAX_INVALID`**（`src/agents/error_classifier.py`）：
  补丁经 2.2 重采样（最多 2 次）后仍语法不合法（AST 解析失败）时，由
  `apply_patch_with_resample` 统计经 `_patch_applier_node` 写入
  `state["error_category"]`，标识"补丁语法反复损坏"场景（与失败知识库
  同口径）。
- **`refine_failure_category` / `refine_final_error_category`** 新增
  `patch_syntax_invalid` 参数；判定优先级
  `patch_rejected > rag_empty > trace_missing > multi_rejected > patch_syntax_invalid`。
- **测试同步**：`tests/test_error_classifier.py` 的
  `test_seventeen_categories_total` 锁定 17 类总数 + `PATCH_SYNTAX_INVALID` 值。

---

## 四、2.2 补丁后处理重采样（`PATCH_RESAMPLE_ENABLE`）

- **`src/graph/nodes.py::_patch_applier_node`**：应用失败（定位不到目标函数 /
  AST 解析不通过）时，若 `PATCH_RESAMPLE_ENABLE=true` 则触发
  `apply_patch_with_resample`（最多 `PATCH_RESAMPLE_MAX` 次，默认 2，钳到 0-5）；
  仍失败则把该轮标记为 `patch_syntax_invalid`（`refine_failure_category`
  消费，归一为 `PATCH_SYNTAX_INVALID`），保留原代码。
- **`apply_patch_with_resample` 关键参数修复**（`src/tools/patch_applier.py`）：
  此前调用方误传 `on_resample` 参数名，导致 2.2 重采样**静默失效**
  （`apply_patch_with_resample` 签名实际为 `resample_fn`）。本批次修正为
  `resample_fn=_on_resample`，重采样路径真正接线。默认关闭不受影响。
- **重采样 LLM 温度**：`_patch_resample_temperature()` 读
  `patch_applier._current_context_tier()` 的档位温度（被符号守卫拒绝后自动
  降级到的档位 0.2/0.1/0.0），与 1.3 降级链"降级层用更严格采样"口径一致。
- **回归守卫**：`tests/test_improvements_1_2_2_1_2_2_4_3.py` 锁定重采样路径。

---

## 五、1.3 分层压缩降级链透传（`CONTEXT_TIER_DOWNGRADE_ENABLE`）

- **`src/graph/state.py`**：`AITesterState` 声明 4 个新键（
  `create_initial_state` 同步补默认值 `None`）：
  - `contract_reject_feedback`（`dict[str, Any] | None`）：
    `_patch_applier_node` → `_debugger_node` 跨轮透传的档位反馈
  - `contract_missing_symbols`（`list[str] | None`）：本轮缺失的模块级符号列表
  - `patch_resample_stats`（`dict[str, Any] | None`）：2.2 重采样统计
  - `patch_syntax_invalid_flag`（`bool | None`）：2.2 重采样耗尽标记
- **`src/graph/nodes.py`**：
  - `_debugger_node` 透传 `contract_reject_feedback` 给 `debug()`
  （`cast` 收窄 TypedDict.get 的 `Any` 返回类型）
  - `_patch_applier_node` 符号守卫（`check_naming_contract`）拒绝补丁时，
    若 `CONTEXT_TIER_DOWNGRADE_ENABLE=true` 则调 `advance_context_tier()`
    推进档位，并把 `(tier_name, missing_symbols)` 写入
    `state["_1_3_contract_feedback"]`（节点函数内临时键，末尾经
    `state.pop` 取出合并进返回 dict，通道键为 `contract_reject_feedback`）；
    默认关闭时仅记录 `state["_1_3_contract_missing"]`（不动档位）。
- **`src/agents/debugger.py`**：
  - `debug()` 新增 `contract_reject_feedback` 参数
  - `_build_downgrade_context`：按被拒档位构建"更高约束"的代码上下文
    （`patch_ingredients` = 补丁配方保留片段；`minimal` = 签名+import 极简），
    替代"全文件截断"——被拒轮次的 prompt 不再携带已破坏契约的大段代码；
    构建失败（AST 解析失败等）时返回空串，调用方回退历史截断口径
  - `_downgrade_tier_temperature`：档位 → 温度映射（读
    `patch_applier._CONTEXT_TIER_TEMPERATURES`）
  - 观测字段 `mypy_findings_count` / `downgrade_triggered` / `downgrade_tier`
    （实验分析"降级链触发率"消费）

---

## 六、五、多维度污染检测 + Token 效率

- **`experiments/run_benchmark.py::_build_task_result`** 新增
  `contamination_risk_level` 字段（high/medium/low）：
  - 调 `patch_semantic_similarity`（`experiments/contamination_check.py`）
    多维度检测（token Jaccard + AST 语句骨架 LCS + 嵌入余弦/词袋余弦保守
    代理；`EMBEDDING_BACKEND` 接入真实嵌入库时自动升级为 CodeBERT 类
    语义余弦），综合得出 risk_level（取最严重维度）
  - 无 golden patch（纯合成数据集 / 无 ground truth 场景）→ 保守 "low"
    （无重叠证据，非"完全相同"）
  - 失败分支各键 None 兜底（键集合同构）
  - 供 `analyze_results` 的 `_contamination_cross_analysis` 消费
    （区分"含污染样本"与"不含污染样本"的结果）
- **`experiments/rag_ab_experiment.py::compare_ab`** 新增
  `token_saving.delta_pct`（RAG ON vs OFF token 消耗降低百分比；
  分母 `max(_mean(off_tokens), 1)` 防除零；ICSE 2025 知识增强修复
  工作基线 17.49%-34.24%，ContextSniper 进一步优化 -51.5%）。

---

## 七、2.1 mypy 静态类型检查层（`TYPE_CHECK_ENABLE`）

- **`src/tools/type_repair.py::_run_mypy_findings`**：`TYPE_CHECK_ENABLE=true`
  时对"补丁后代码"跑 mypy 仓库级静态类型分析（PAGENT 混合架构的
  "仓库级静态分析"部分），识别 PAGENT 研究中的"类型/数据结构管理错误"
  （占失败补丁 27.19%）：
  - 未定义名称（`name-defined`）
  - 参数类型不匹配（`arg-type`）
  - 返回值类型与声明不一致（`return-value`）
  - 容器类型混用（`dict-item` / `list-item`）
- **保守降级**：mypy 未安装时透明降级为空列表（不阻断 ast 静态层）；
  仅消费高置信度错误类别，过滤"推断失败 / 类型不完整"类低置信度告警。
- **`src/agents/debugger.py::debug()`** 新增观测字段
  `mypy_findings_count`（未启用 / 未安装时 0）。
- 与 `TYPE_REPAIR_LLM_ENABLE`（LLM 层）独立开关，可同时启用。

---

## 八、修复 + 类型清零

- **`src/tools/patch_applier.py::build_tiered_context`**：tier-0 分支
  返回 `str | None` → `str`（`extract_function_context(...) or ""`，
  保守降级口径，行为等价）。
- **`src/agents/debugger.py` / `src/graph/nodes.py`**：`cast` 收窄
  `dict[str, Any] | None` union-attr（mypy 全绿，零行为变化）。
- **全仓 ruff 8 lint 问题清零 + mypy 12 类型错误清零**（64 源文件）。
  - `ruff --fix` 自动修 4 个 import 排序（`I001`）+ 1 个未使用 import
    （`F401`）
  - 手动修 3 个：`noqa: BLE001` 残留（`debugger.py`）/ `contextlib.suppress`
    替代 `try/except OSError: pass`（`type_repair.py`）/ 强化
    `assert ... or True` 空操作断言为真实负向断言
    （`tests/test_roadmap_13_22_21_mypy_5.py`）

---

## 九、测试与验证

| 指标 | 数值 |
|------|------|
| 全量测试 | **1937 passed / 0 failed**（基线 1920 + 17 新增） |
| ruff | 全绿（0 告警） |
| mypy | 0 错误（64 源文件） |
| 日志脱敏审计 | 96 文件 / 313 logger 调用点，0 可疑点 |
| lock 同步 | requirements.txt ↔ lock 一致（2 个传递依赖 advisory） |

**验证命令**：
```bash
.venv/bin/pytest tests -q
.venv/bin/ruff check src tests config.py main.py init_db.py
.venv/bin/mypy src config.py main.py
.venv/bin/python scripts/audit_log_redaction.py
.venv/bin/python scripts/check_lock_sync.py
```

---

## 十、新增回归守卫

- `tests/test_roadmap_13_22_21_mypy_5.py`（新增，17 用例）：
  - tier 推进 / 封顶 / 环境变量同步
  - 2.2 重采样接线（`_patch_resample_enabled` / `_patch_resample_max`）
  - 2.1 mypy 静态层（`TYPE_CHECK_ENABLE` 开关 + mypy 未安装降级）
  - 1.3 降级链透传（`_build_downgrade_context` + `_downgrade_tier_temperature`）
- `tests/test_error_classifier.py`：`test_seventeen_categories_total`
  锁定 17 类总数 + `PATCH_SYNTAX_INVALID` 值
- `tests/test_round8_contract_ref_findings.py`：新增
  `mypy_findings_count` / `downgrade_triggered` / `downgrade_tier`
  观测字段断言
- `tests/test_run_benchmark.py`：`_build_task_result` 新增
  `contamination_risk_level` 字段断言（成功 / 失败分支）

---

## 十一、核实后无需修改项

- `extract_function_context` 的 `str | None` 返回类型（函数签名本身
  设计为"无法解析时返回 None"，调用方 `build_tiered_context` 已
  `... or ""` 兜底，无需改函数签名）
- `_1_3_contract_feedback` / `_1_3_contract_missing` /
  `_2_2_patch_syntax_invalid` 临时键（节点函数内先写入、末尾经
  `state.pop` 取出合并进返回 dict，通道键已声明于 TypedDict，
  临时键不入 LangGraph 通道，`cast` 收窄即可）
- `apply_patch_with_resample` 的 `resample_fn: Any` 参数类型
  （设计为零硬依赖、可测试，`Any` 口径保留）

---

## 十二、延期项（下轮处理或需决策）

- `PATCH_RESAMPLE_ENABLE=true` 路径下 LLM 重采样调用量未做成本
  消融（需 `PATCH_RESAMPLE_MAX` 梯度实验验证 token 消耗 vs 修复率）
- `TYPE_CHECK_ENABLE=true` 的 mypy 静态层与 `TYPE_REPAIR_LLM_ENABLE`
  联动的修复成功率未做 A/B 对比（需 SWE-bench 子集实测）
- `contamination_risk_level` 的 "high" 档阈值未做样本校准
  （`_combined_risk_level` 默认阈值，需大样本验证误报率）
