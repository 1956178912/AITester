> **语言 / Language**：[English](algorithm_design.en.md) | 简体中文（本文）

# 多智能体协作测试生成与自修复协议（算法设计文档）

> 本文档描述 AITester 的核心算法设计与理论框架，供技术评审与代码审查参考。
> 附录提供算法到源码的精确映射表，便于快速定位实现细节。
>
> **基线数字**：本文档中引用的测试基线数字以仓库根 [BASELINE.yaml](../BASELINE.yaml)
> 为唯一事实来源（批次落地后同步刷新）；历史轨迹见 `CHANGELOG.md` 各条目，
> 本文件不再内嵌基线数字，避免随轮次推进产生过期快照。
>
> **位置感知迭代修复（3.3）实现口径说明**：`POSITION_AWARE_REPAIR_ENABLE`
> （默认 false）启用后，定位阶段由 `error_classifier` 提取 traceback 行号，
> 经 `_locate_repair_focus()` AST 定位"包围异常行的最短区间函数"，
> 再经 `_build_position_aware_prompt_section()` 注入位置感知修复指引；
> 无法定位时自动降级为常规全文件修复。该阶段为纯静态定位，不消耗 LLM token，
> 与 LoopRepair 式"先定位后补丁"口径一致，映射表附录已列出。

---

## 附录：算法 — 代码映射表

| 算法编号 | 算法名称 | 源码位置 | 关键函数/类 | 相关 ADR |
|:--------:|---------|---------|------------|---------|
| Algorithm 1 | 逻辑驱动测试规划 | [src/agents/planner.py](../src/agents/planner.py) | `PlannerAgent.plan()` | 0001 |
| Algorithm 2 | 错误分类（规则匹配 + 置信度分层） | [src/agents/error_classifier.py](../src/agents/error_classifier.py) | `ErrorClassifier.classify()` / `classify_with_confidence()` | 0002 |
| Algorithm 3 | 迭代修复循环 | [src/graph/workflow.py](../src/graph/workflow.py) | `_should_debug()` + 条件路由边 | 0001, 0005 |
| Patch 应用 | 补丁写入原文件 | [src/tools/patch_applier.py](../src/tools/patch_applier.py) | `apply_patch_to_code()` | 0003, 0005 |
| 跨文件修复（3.5，默认关） | 跨文件依赖分析 + 多文件补丁 | [src/tools/cross_file.py](../src/tools/cross_file.py) + [src/graph/workflow.py](../src/graph/workflow.py) `cross_file_analyzer` 节点（插在 executor→debugger 之间） | `analyze_cross_file_deps()` / `build_cross_file_repair_plan()` / `apply_multi_file_patch()` / `cross_file_fallback_single_file()` | 0003 |
| RAG 检索 | 向量相似检索 | [src/rag/retriever.py](../src/rag/retriever.py) | `TestCaseRetriever` | 0004 |
| 批量实验 | 基准测试执行 | [experiments/run_benchmark.py](../experiments/run_benchmark.py) | `run_benchmark()` | 0001 |
| 数据污染检测（2.1） | 生成补丁 vs 黄金补丁 token 级 Jaccard 重叠度 | [experiments/contamination_check.py](../experiments/contamination_check.py) | `patch_overlap_score()` / `detect_contamination()` / `render_contamination_section()` | — |
| 任务难度分层（2.2） | 按 code_size / dependency_count / complexity_proxy 分层 | [experiments/difficulty_stratification.py](../experiments/difficulty_stratification.py) | `stratify_by_dimension()` / `render_stratification_section()` | — |
| Docker 隔离执行（4.3） | docker CLI 容器内跑 pytest | [src/agents/executor.py](../src/agents/executor.py) | `ExecutorAgent._execute_docker()` | 0005 |
| 依赖缓存监控（4.4） | venv 缓存命中率统计 + 清理 | [src/tools/dependency.py](../src/tools/dependency.py) | `get_venv_cache_stats()` / `list_venv_cache()` / `clear_venv_cache()` | 0003 |
| 收敛失败模式归因（1.2） | 区分"无法定位根因" vs "无法生成有效补丁" | [experiments/analyze_results.py](../experiments/analyze_results.py) | `_convergence_failure_modes()` | — |
| 边界用例覆盖（1.3） | AST 保守判定 generated_test 边界条件覆盖 | [experiments/analyze_results.py](../experiments/analyze_results.py) | `_boundary_case_coverage()` | — |
| 变异得分（1.3） | 收集 details[].mutation_score（外部变异测试器产出） | [experiments/analyze_results.py](../experiments/analyze_results.py) | `_mutation_score_metrics()` | — |
| 执行反馈轨迹（3.2） | 每次执行追加 passed/coverage_delta/elapsed/reward_signals | [src/graph/state.py](../src/graph/state.py) + [src/graph/nodes.py](../src/graph/nodes.py) | `_record_execution_trace()` / `state.execution_trace` | 0001, 0005 |
| 位置感知迭代修复（3.3，默认关） | traceback 行号 + AST 定位"包围异常行的最短区间函数"，注入位置感知修复指引 | [src/agents/debugger.py](../src/agents/debugger.py) | `_position_aware_repair_enabled()` / `_locate_repair_focus()` / `_build_position_aware_prompt_section()` | 0003 |
| 嵌入后端（CodeBERT/sentence-transformers/词袋） | 按 `EMBEDDING_BACKEND` 选择后端，缺依赖时保守回退词袋余弦 | [src/utils/embedding_utils.py](../src/utils/embedding_utils.py) | `embed_text()` / `cosine_similarity()` / `backend_name()` | 0004 |
| 静态类型修复层（mypy/pyright） | `TYPE_CHECK_BACKEND` 切换后端，pyright 不可用时降级 ast 静态层 | [src/tools/type_repair.py](../src/tools/type_repair.py) | `_run_mypy_findings()` / `_run_pyright_findings()` / `type_repair_layer()` | 0004 |
| SWE-bench Pro 数据集 | `swe_bench_pro` / `swebench_pro` 注册，复用 `SWEBenchDataset`，数据目录经 `data_dir` 注入 | [src/datasets/dataset_loader.py](../src/datasets/dataset_loader.py) | `load_dataset()` / `get_available_datasets()` | — |
| RAG A/B 实验 | 自动跑 RAG ON vs OFF 两批，产出 token/成功率/迭代/耗时统计 + Welch t-test + Mann-Whitney U + Cohen's d | [experiments/rag_ab_experiment.py](../experiments/rag_ab_experiment.py) | `compare_ab()` / `token_saving.delta_pct` | 0003 |

---

## 1. 系统概述

AITester 是一个基于多智能体协作（Multi-Agent Collaboration）的 Python 自动化测试生成与自修复系统。

系统由四个核心智能体构成，各自职责如下：

| 智能体 | 职责 | 是否调用 LLM |
|:------:|------|:------------:|
| **PlannerAgent** | 对目标函数进行逻辑分析，输出结构化测试计划 | ✅ 是 |
| **GeneratorAgent** | 根据测试计划生成可运行的 pytest 代码 | ✅ 是 |
| **ExecutorAgent** | 在隔离环境中执行测试，捕获输出与覆盖率 | ❌ 否 |
| **DebuggerAgent** | 分析失败原因，生成分层修复补丁 | ✅ 是 |

系统整体工作流为有向图（由 LangGraph 编排），支持循环修复路径及消融实验开关。

---

## 2. 逻辑驱动思维链算法（Algorithm 1）

### 2.1 问题建模

设被测函数为 $f: D_{in} \rightarrow D_{out}$，其中 $D_{in}$ 为输入定义域，$D_{out}$ 为输出值域。

**目标**：生成测试集合 $\mathcal{T} = \{t_1, t_2, \ldots, t_n\}$，使得每个 $t_i$ 对应 $f$ 的一个逻辑分支或边界条件，且 $\bigcup_i \text{coverage}(t_i) \geq \theta$（覆盖率阈值，默认 80%）。

### 2.2 算法步骤

```
Algorithm 1: Logic-Driven Test Planning
Input:  源代码 S，目标函数 f（可选，None 表示分析全部函数）
Output: 测试计划 P = (LA, TC)，其中 LA 为逻辑分析，TC 为测试用例列表

1:  LA ← LLM_Analyze(S, f)          // 逻辑分析：输入域、输出域、前置/后置条件、边界情况
2:  TC ← []                          // 初始化空测试用例列表
3:  for each pre-condition pc in LA.preconditions do
4:      TC.append(TestCase(pc, category="normal"))   // 前置条件 → 正常输入用例
5:  end for
6:  for each post-condition pc in LA.postconditions do
7:      TC.append(TestCase(pc, category="normal"))   // 后置条件 → 正常输入用例
8:  end for
9:  for each edge-case ec in LA.edge_cases do
10:     cat ← "boundary" if ec 涉及边界值 else "error"  // 边界 or 异常
11:     TC.append(TestCase(ec, category=cat))
12: end for
13: return P = (LA, TC)
```

### 2.3 复杂度分析

- **时间复杂度**：$O(k \cdot C_{LLM})$，其中 $k=5$ 为逻辑分析维度数，$C_{LLM}$ 为单次 LLM 调用成本。
- **空间复杂度**：$O(|S| + |P|)$，存储源代码和结构化测试计划。

### 2.4 实现说明

- 代码位置：[src/agents/planner.py](../src/agents/planner.py)
- System Prompt 定义于 [src/prompts/templates.py](../src/prompts/templates.py) 的 `PLANNER_SYSTEM_PROMPT`
- 若 LLM 未返回 `logic_analysis` 字段（兼容性兜底），自动填充空值避免下游崩溃

---

## 3. 分层错误修复协议（Algorithm 2 & 3）

### 3.1 错误分类器（Algorithm 2）

定义错误类型枚举 $\mathcal{E} = \{\text{SYNTAX}, \text{RUNTIME}, \text{ASSERTION}, \text{TIMEOUT}, \text{UNKNOWN}\}$。

分类函数 $C: \text{TestOutput} \rightarrow \mathcal{E}$ 采用**规则匹配**（正则表达式），确保 $O(1)$ 分类时间且无需消耗 LLM token。

```
Algorithm 2: Error Classification（规则匹配）
Input:  测试输出文本 O，失败用例列表 F
Output: 错误类别 e ∈ E

1:  combined ← O ⊕ concat(F[*].error)    // 拼接输出文本与失败用例错误信息
2:  if matches(combined, SYNTAX_PATTERNS) then return SYNTAX
3:  if matches(combined, RUNTIME_PATTERNS) then return RUNTIME
4:  if matches(combined, ASSERTION_PATTERNS) then return ASSERTION
5:  if matches(combined, TIMEOUT_PATTERNS) then return TIMEOUT
6:  return UNKNOWN                        // 兜底类别
```

**正则模式定义**（见 [src/agents/error_classifier.py](../src/agents/error_classifier.py)）：
- `SYNTAX_PATTERNS`：SyntaxError、ImportError、ModuleNotFoundError 等编译期错误
- `RUNTIME_PATTERNS`：ZeroDivisionError、TypeError、KeyError、IndexError 等运行时异常
- `ASSERTION_PATTERNS`：AssertionError、assert 语句、Expected...but got 等
- `TIMEOUT_PATTERNS`：timeout、TimedOut、Test ran for longer than 等

**已知局限与演进方向（2026-09-28 补充）**：当前分类器为纯规则匹配，
$O(1)$ 且零 LLM token 消耗，但难以覆盖复杂错误模式（正则未命中的新
异常组合会落入 `UNKNOWN`，见 `docs/failure_analysis.md` 历史快照：
UNKNOWN 曾占失败样本 75%）。演进路径建议（按成本递增）：

1. **轻量语义分类兜底层**：在 `refine_failure_category` 判定为
   `UNKNOWN` 时，调用一个轻量嵌入模型（复用 5.1 `semantic_cache`
   的嵌入后端，如 CodeBERT / sentence-transformers，均已在依赖中）
   对拼接文本做语义相似度匹配到 17 类已知类别中相似度最高的
   类别，相似度 ≥ 阈值（建议 0.6，低于 5.1 缓存的 0.92 保守口径）
   才采纳，否则仍返回 `UNKNOWN`。该层仅对规则未命中的少量样本
   生效，额外 LLM/嵌入调用量可控；可通过独立环境变量
   `SEMANTIC_CLASSIFY_ENABLE`（默认 false，保持历史行为）开关。
2. **根因定位精度提升**：`POSITION_AWARE_REPAIR_ENABLE`（3.3
   位置感知迭代修复）当前默认关闭。针对 MAX_ITERATIONS 收敛失败
   中"无法定位根因"子类（`docs/failure_analysis.md` 记录），
   建议在 50 任务合成集上开启对比实验验证修复率增益后再评估
   默认启用；"无法生成有效补丁"子类（补丁语法反复损坏，
   对应 `PATCH_SYNTAX_INVALID`）建议叠加 2.2 重采样（
   `PATCH_RESAMPLE_ENABLE`）已验证的收敛路径。
3. **跨文件修复价值边界验证**（3.5 `CROSS_FILE_ENABLE`）：
   当前默认关闭且缺乏正向实证（ON/OFF 均 0/N，见
   `docs/failure_analysis.md`）。建议设计细粒度验证实验：
   以"跨文件 import 依赖深度"为分层维度（depth=1 直接调用 /
   depth≥2 传递调用），配合更强模型（GPT-4 级别）+ 仓库全量
   源码上下文，测量各深度档位的 ON/OFF 修复率差，确认
   能力边界后再决定默认值。
4. **对抗性推理 × 变异测试闭环**（3.1 `ADVERSARIAL_DEBUGGING_ENABLE`
   + 1.2 内置变异测试生成器）：当前两者独立默认关闭。建议将
   `mutation_score_from_details` 产出的变异得分作为对抗性推理
   的输入信号——低得分（测试薄弱）时提高对抗性假设强度与
   采样数量，高得分时缩减额外 LLM 调用，形成"变异 → 发现
   薄弱点 → 对抗性生成 → 验证"闭环；可通过独立开关
   `MUTATION_FEEDBACK_ENABLE`（默认 false）实现，避免默认行为变化。

### 3.2 分层修复策略

每种错误类型 $e \in \mathcal{E}$ 对应唯一的差异化修复策略 $Strat(e)$：

| 错误类型 | 修复策略 | LLM 调用方式 |
|:--------:|---------|:------------:|
| SYNTAX | 重写完整文件（语法/导入修复） | 直接输出完整文件 |
| RUNTIME | 定位异常栈，修复具体函数逻辑 | 输出修复后的完整文件 |
| ASSERTION | 判断是代码逻辑错误还是测试预期值错误 | 分情况输出修复补丁 |
| TIMEOUT | 检查循环/递归条件，添加退出逻辑 | 输出修复后的完整文件 |
| UNKNOWN | 通用分析后自主判断 | 输出修复补丁 |

### 3.3 迭代修复循环（Algorithm 3）

```
Algorithm 3: Iterative Repair Loop
Input:  原始源代码 S，最大迭代次数 K
Output: 修复后的源代码 S'，测试是否通过 bool

1:  S_current ← S                          // 从原始代码开始
2:  for i ← 1 to K do
3:      T ← Generator(S_current)           // GeneratorAgent 生成测试代码
4:      (passed, output, failed_cases) ← Executor(T, S_current)
5:      if passed then return (S_current, true)   // 测试通过，提前终止
6:      e ← Classifier(output, failed_cases)   // ErrorClassifier 分类错误
7:      patch ← Debugger(S_current, output, e)  // DebuggerAgent 生成修复补丁
8:      S_current ← ApplyPatch(S_current, patch) // PatchApplier 应用补丁
9:  end for
10: return (S_current, false)               // 达到最大迭代仍未通过
```

**实现位置**：[src/graph/workflow.py](../src/graph/workflow.py) 中的 `_should_debug()` 控制路由条件。

> **3.5 跨文件扩展路径**（`CROSS_FILE_ENABLE=true` 时启用，默认关）：在 `executor` 与 `debugger` 之间插入 `cross_file_analyzer` 节点（`_cross_file_analyzer_node`），做 AST 跨文件 import 依赖分析并把依赖边写入 `state["cross_file_deps"]`；`_patch_applier_node` 在跨文件分支按拓扑序对多模块应用补丁（被调用方先改、调用方后改），任一文件失败经 `cross_file_fallback_single_file()` 降级为仅入口模块应用（与单文件 `safe_apply_patch` 同口径）。详见 [docs/design/cross_file_repair.md](design/cross_file_repair.md)。

---

## 4. 多智能体协作协议

### 4.1 状态转移图

系统状态空间 $\mathcal{S}$ 由 TypedDict `AITesterState` 定义（见 [src/graph/state.py](../src/graph/state.py)），包含以下关键字段：

```
task_uuid ─▶ target_file ─▶ target_code
                    │
                    ▼
              test_plan ─▶ generated_test ─▶ test_passed
                                          │
                              ┌───────────┼───────────┐
                              │           │           │
                           passed?      failed     max_iter?
                              │           │           │
                              ▼           ▼           ▼
                             END     Debugger ─▶ PatchApplier ─┘
```

### 4.2 消融实验配置矩阵

通过布尔开关控制节点启用/禁用，形成 4 种实验变体（配置见 [config.py](../config.py)）：

| 变体 | ENABLE_PLANNER | ENABLE_DEBUGGER | ENABLE_RAG | 对应基线 |
|:----:|:--------------:|:---------------:|:----------:|---------|
| 完整系统 | true | true | false | AITester |
| 无 Planner | false | true | false | 无规划基线 |
| 无 Debugger | true | false | false | 无修复基线 |
| 纯 LLM | false | false | false | plain_llm |
| 单智能体 | — | — | — | single_agent |

---

## 5. 理论正确性说明

### 定理 1（完整性）

若被测函数 $f$ 存在可修复的 bug，且 LLM 具备足够能力，则算法在 $K$ 次迭代内收敛到通过所有测试的状态的概率为 $p > 0$。

**证明**：每次 Debugger 调用根据错误分类提供针对性修复策略，覆盖 SYNTAX/RUNTIME/ASSERTION/TIMEOUT 四类已知模式。对于 UNKNOWN 类别，LLM 进行通用分析。由于 LLM 输出空间包含正确修复方案（假设模型能力足够），存在一条从初始状态到成功状态的路径。∎

### 定理 2（终止性）

算法保证在 $K$ 次迭代后终止，不会无限循环。

**证明**：循环上界由 `MAX_ITERATIONS`（默认 3）控制，每次迭代执行固定节点序列（Generator → Executor → Debugger → PatchApplier），不存在递归调用自身的情况。∎

---

## 6. 与现有方法的对比

| 方法 | 逻辑规划 | 分层修复 | RAG 增强 | 消融实验 |
|:---:|:-------:|:-------:|:-------:|:-------:|
| Pynguin（传统工具） | ✗ | ✗ | ✗ | ✗ |
| 直接 LLM 单次调用 | ✗ | ✗ | ✗ | ✗ |
| 单智能体系统 | ✗ | 部分 | ✗ | ✗ |
| **AITester（本系统）** | ✅ | ✅ | ✅（可选） | ✅ |

---

## 7. 数据集加载架构

```
load_dataset(name, data_dir=None)
├── "examples" / "in_memory"   → InMemoryDataset（3 个预定义 bug 任务，无需下载）
├── "swe_bench" / "swebench"   → SWEBenchDataset（从 ~/.cache/aitester/swe_bench/ 读取，
│                                支持从 HuggingFace 自动下载：download_from_huggingface()）
├── "swe_rebench" / "swebench_rebench" → SWEBenchDataset（2.1 抗污染基准，
│                                data_dir 指向 SWE-rebench 数据目录，字段与 SWE-bench 同构）
├── "defects4j_python" / "d4j_py" → Defects4JPYDataset（从本地目录解析）
├── "synthetic" / "synth"      → SyntheticDataset（本地生成，支持自定义规模）
└── 其他名称                   → InMemoryDataset（graceful degrade，不崩溃）
```

每个任务统一为 `BenchmarkTask` 数据结构（定义于 [src/datasets/dataset_loader.py](../src/datasets/dataset_loader.py)）：

| 字段 | 类型 | 说明 |
|-----|------|------|
| `task_id` | str | 唯一标识，如 `examples__calculator_divide` |
| `repo_name` | str | 所属仓库/模块名 |
| `problem_statement` | str | Bug 描述 |
| `instance_code` | str | 有缺陷的原始代码 |
| `test_code` | str | 参考测试代码 |
| `expected_pass_count` | int | 期望通过的最小测试数 |
| `total_test_count` | int | 总测试用例数 |
| `metadata` | dict | 附加元数据（来源、bug 类型等） |
