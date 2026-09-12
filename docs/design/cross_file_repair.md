# 3.5 跨文件修复能力设计文档

> 立项日期：2026-09-14
> 状态：设计阶段（未实施）
> 关联清单：改进清单 3.5
> 前置依赖：3.1 多候选补丁（`multi_candidate.py` 已落地）

## 1. 背景与目标

### 1.1 现状

当前系统假设"修复只发生在 `target_file` 单文件内"：

- `patch_applier.py` 按单文件应用补丁（`apply_patch_to_code(original_code, patch)`）；
- `ExecutorAgent` 在沙箱内只运行 `target_file` 的 pytest；
- `multi_candidate.py` 候选筛选也是单文件范围；
- `dependency.py` 的 `extract_import_module_names` 已能识别跨文件 import（顶层模块名），但未用于修复规划。

### 1.2 问题

真实数据集（SWE-bench / Defects4J）中**约 40% 的任务需要多文件修改**（如：

- 修复 A 文件中的函数，需同步更新 B 文件中的调用方；
- 修改公共库接口，需更新 N 个调用方；
- 修复测试用例时，需同步修改被测代码的 mock 依赖。

单文件假设导致这类任务在当前架构下必然失败：Debugger 只能看到 `target_code`（单文件内容），无法诊断跨文件依赖。

### 1.3 目标

- 在 `patch_applier` 层支持"多文件补丁"（每个文件一个补丁片段）；
- 在 `workflow` 层新增 `CrossFileAnalyzer` 节点（可选，默认关），对被测代码做 AST 依赖分析，产出"跨文件修复计划"；
- 在 `DebuggerAgent` 提示词中注入跨文件上下文，让 LLM 感知"修改 X 函数会影响 Y 文件"；
- 在 `multi_candidate.py` 扩展候选筛选：静态校验每个文件的补丁，执行验证仍复用单文件（跨文件执行验证留作二期）。

成功标准（可测）：
- 在 `examples/` 构造 3 个含跨文件 bug 的合成任务（A 文件函数有 bug，B 文件调用 A，修复需改 A + 同步改 B）；
- 启用 `CROSS_FILE_ENABLE=true` 时，任务通过率显著高于启用前；
- 不改变 `CROSS_FILE_ENABLE` 默认值（false），历史实验口径不变。

## 2. 方案对比

### 方案 A：协调器-提议者架构（PhoenixRepair 思路）

- 一个"协调器"节点分析跨文件依赖，产出修复计划（哪些文件要改、每个文件改什么）；
- 多个"提议者"节点（每个文件一个）并行生成补丁；
- 协调器汇总后交给现有 `patch_applier` 应用。

优点：架构清晰，与现有 `planner → generator → executor → debugger → patch_applier` 五节点图易集成；可扩展到 N 个文件；提议者间并行省时间。

缺点：复杂度高，协调器需实现"跨文件依赖图 + 修复计划"的数据结构；提议者间补丁冲突需协调器仲裁。

### 方案 B：纯 LLM 端到端（把多文件内容全塞进 prompt）

- 在 Debugger 节点把"target_code + 所有相关文件内容"一起喂给 LLM；
- LLM 直接输出多文件 diff。

优点：实现简单（只需改 prompt）。

缺点：token 成本爆炸（大项目跨文件场景）；LLM 上下文窗口可能装不下；无法做静态筛选（多文件候选筛选成本高）。

### 最终选择：方案 A（协调器-提议者架构）

理由：

1. 跨文件依赖分析用 AST 做（确定性、低成本），比让 LLM 直接"猜"更可靠；
2. 提议者并行生成，token 成本可控；
3. 与现有 `multi_candidate.py` 的"候选筛选 + 执行验证"机制可复用；
4. 二期可扩展到"依赖图 + 拓扑排序 + 分批修复"。

## 3. 最终方案

### 3.1 数据结构

新增 `src/tools/cross_file.py`：

```python
@dataclass
class CrossFileDependency:
    """跨文件依赖边：module_a 调用了 module_b 中的 symbol_b。"""
    source_module: str   # 调用方模块名（不含 .py）
    target_module: str   # 被调用方模块名
    symbol: str          # 被调用的函数/类名
    call_line: int       # 调用方源码行号
    context: str         # 调用行上下文（供 LLM 理解）


@dataclass
class CrossFileRepairPlan:
    """跨文件修复计划。"""
    plan_id: str
    target_modules: list[str]  # 需要修改的模块列表
    per_module_patches: dict[str, str]  # 模块名 → 补丁文本
    dependency_edges: list[CrossFileDependency]  # 依赖关系
    estimated_token_cost: int  # 预估 token 成本


def analyze_cross_file_deps(
    entry_module: str,
    source_files: dict[str, str],
) -> list[CrossFileDependency]:
    """AST 分析入口模块与其他模块的依赖关系。"""


def build_cross_file_repair_plan(
    deps: list[CrossFileDependency],
    debugger: "DebuggerAgent",
) -> CrossFileRepairPlan:
    """基于依赖图 + LLM 生成多文件修复计划。"""
```

### 3.2 工作流集成点

在 `workflow.py` 中，`_debugger_node` 之前插入可选的 `_cross_file_analyzer_node`（`CROSS_FILE_ENABLE=true` 时启用）：

```
... executor → (cross_file_analyzer →) debugger → patch_applier ...
```

- `cross_file_analyzer` 节点：调用 `analyze_cross_file_deps`，把结果写入 `state["cross_file_deps"]`；
- `_debugger_node` 在跨文件模式启用时，提示词追加"以下文件可能需要同步修改"；
- `_patch_applier_node` 在跨文件模式启用时，走"多文件补丁应用"分支（调用 `apply_multi_file_patch`，新增）。

### 3.3 多文件补丁应用

`patch_applier.py` 新增：

```python
def apply_multi_file_patch(
    original_files: dict[str, str],  # 模块名 → 原始代码
    patches: dict[str, str],          # 模块名 → 补丁
    entry_module: str,
) -> tuple[dict[str, str], bool]:
    """对多个文件同时应用补丁。

    策略：按依赖图拓扑序应用（被调用方先改，调用方后改），
    任一文件应用失败则回滚到原始代码（与单文件 safe_apply_patch 同口径）。
    """
```

### 3.4 配置开关

`config.py` 新增：

```python
# 3.5 跨文件修复：默认关闭，保持历史单文件口径
CROSS_FILE_ENABLE: bool = os.getenv("CROSS_FILE_ENABLE", "false").lower() == "true"
# 跨文件依赖分析的最大模块数（防止 LLM 上下文爆炸，默认 5）
CROSS_FILE_MAX_MODULES: int = int(os.getenv("CROSS_FILE_MAX_MODULES", "5"))
```

### 3.5 兼容性影响

- `CROSS_FILE_ENABLE=false`（默认）：所有路径行为不变；
- `CROSS_FILE_ENABLE=true`：需要 `target_file` 所在项目有可解析的多文件源码；单文件项目自动降级为单文件模式；
- `repair_history` 追加字段 `cross_file_files: list[str]`（记录本轮修复涉及的模块名）。

## 4. 测试策略

### 4.1 单元测试

`tests/test_cross_file.py`（新增）：

| 用例组 | 覆盖点 |
|--------|--------|
| `test_analyze_deps` | 跨文件 import / 调用识别正确 |
| `test_build_plan` | 修复计划结构完整，token 成本估算合理 |
| `test_apply_multi_file_patch` | 多文件补丁应用成功 / 部分失败回滚 |
| `test_topological_order` | 被调用方先改，调用方后改 |
| `test_single_file_fallback` | `CROSS_FILE_ENABLE=true` 但只有单文件时降级 |
| `test_workflow_integration` | 端到端：跨文件 bug 在 `CROSS_FILE_ENABLE=true` 时通过 |

### 4.2 集成测试

`experiments/results/` 构造 3 个合成任务：
- `task_1.py` + `task_2.py`：A 有 bug，B 调用 A（修复需同步 B）；
- `task_3.py` + `task_4.py` + `task_5.py`：三文件依赖链；
- 验证启用 `CROSS_FILE_ENABLE` 前后通过率差异。

## 5. 回滚计划

- 默认关（`CROSS_FILE_ENABLE=false`），不启用则零行为变化；
- 启用后若修复成功率下降，`git revert` 撤销跨文件节点接线即可（节点代码保留，开关关闭即不执行）。

## 6. 二期扩展（不在本次范围）

- 跨文件执行验证（当前只支持单文件候选执行验证）；
- 依赖图可视化（`dot` 输出）；
- 修复计划缓存（相同依赖图复用 LLM 生成结果）；
- 与 RAG 集成（跨文件修复案例入库）。
