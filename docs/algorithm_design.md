> **语言 / Language**：[English](algorithm_design.en.md) | 简体中文（本文）

# 检出优先的测试生成与修复归因评估协议（算法设计文档）

最后更新：2026-10-19（Z 轮第三方审查 F15/F16：red_not_repaired 检出语义更正为"协议层机制状态、不构成有效检出充分条件"；标题与开篇按 ADR-0016 重定位为检出优先协议 + 可消融编排容器）

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
| 谱系故障定位（O2，默认开） | Ochiai Top-k 行级可疑度排序（零 LLM），Top-k 段落注入 Debugger prompt | [src/agents/fl_spectral.py](../src/agents/fl_spectral.py) | `measure_fl_spectral_focus()` / `compute_ochiai_scores()` / `rank_top_k()` / `build_fl_spectral_prompt_section()` | — |
| RGFL 推理故障定位（修复引擎一期，默认开） | 谱系 Top-k 佐证 + LLM 结构化定位〔函数/行区间/置信度〕，gold diff→AST 函数级命中判定 | [src/agents/fault_localizer.py](../src/agents/fault_localizer.py) | `FaultLocalizerAgent.localize()` / `gold_changed_functions()` / `localization_hit()` / `build_localization_prompt_section()` | 0017 |
| 嵌入后端（CodeBERT/sentence-transformers/词袋） | 按 `EMBEDDING_BACKEND` 选择后端，缺依赖时保守回退词袋余弦 | [src/utils/embedding_utils.py](../src/utils/embedding_utils.py) | `embed_text()` / `cosine_similarity()` / `backend_name()` | 0004 |
| 静态类型修复层（mypy/pyright） | `TYPE_CHECK_BACKEND` 切换后端，pyright 不可用时降级 ast 静态层 | [src/tools/type_repair.py](../src/tools/type_repair.py) | `_run_mypy_findings()` / `_run_pyright_findings()` / `type_repair_layer()` | 0004 |
| SWE-bench Pro 数据集 | `swe_bench_pro` / `swebench_pro` 注册，复用 `SWEBenchDataset`，数据目录经 `data_dir` 注入 | [src/datasets/dataset_loader.py](../src/datasets/dataset_loader.py) | `load_dataset()` / `get_available_datasets()` | — |
| RAG A/B 实验 | 自动跑 RAG ON vs OFF 两批，产出 token/成功率/迭代/耗时统计 + Welch t-test + Mann-Whitney U + Cohen's d | [experiments/rag_ab_experiment.py](../experiments/rag_ab_experiment.py) | `compare_ab()` / `token_saving.delta_pct` | 0003 |

---

## 1. 系统概述

AITester 是一个以检出优先（detection-first）协议为核心、把多智能体编排定位为可消融容器（ablatable container）的 Python 测试生成与自修复系统/评估协议（编排定位见 `docs/adr/0016-orchestration-container-repositioning.md`）。

系统由五个核心智能体构成，各自职责如下：

| 智能体 | 职责 | 是否调用 LLM |
|:------:|------|:------------:|
| **PlannerAgent** | 对目标函数进行逻辑分析，输出结构化测试计划 | ✅ 是 |
| **GeneratorAgent** | 根据测试计划生成可运行的 pytest 代码 | ✅ 是 |
| **ExecutorAgent** | 在隔离环境中执行测试，捕获输出与覆盖率 | ❌ 否 |
| **DebuggerAgent** | 分析失败原因，生成分层修复补丁 | ✅ 是 |
| **FaultLocalizerAgent** | RGFL 式 LLM 推理故障定位（只定位不修复，修复引擎第一阶段；由 `debugger` 节点内联调用，非独立图节点） | ✅ 是 |

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

### 2.5 规约 Oracle 编译与并列执行（2026-10-05 审查批次 R1）

逻辑分析（LA）的机器可执行化分两层（此前 LA 仅作为 prompt 注入材料，规约侧无可执行产物）：

1. **边界参数化层（v1，`src/specs/spec_ir.py::compile_to_hypothesis`）**：SpecIR 的 `boundaries`（确定性边界锚点，输入/期望值对）编译为 `@pytest.mark.parametrize` 断言；NL 前置/后置/不变量子句不产出测试（R1a 修复：历史版本对 invariants 产出 `assert True` 恒真断言——假通过通道，已封堵；无边界材料时保守返回空串）。
2. **受限表达式 DSL 层（v2，`src/specs/spec_ir_v2.py::compile_spec_oracle`）**：形如 `r == x * 2` 的表达式子句经白名单 AST 验证（11 个纯函数调用白名单 + 属性白名单 + 节点类型限制）编译为 `assert <expr>`；不可机器化子句降级为 NL 溯源注释。**签名感知绑定（R1b）**：`extract_signature_params` 从被测函数 AST 签名提取真实参数名（三态：None=未找到降级 / []=0 参 / 非空=按签名），绑定上下文从硬编码 `{r,x,a,b,y}` 扩展为真实参数集，调用元数按签名修正。**v3 文法升阶（P0-A-1，2026-10-12 独立评审优化批次）**：①有限域量化——`<quant>` 产生式（`all(...)` / `any(...)` 推导式形态）+ 自由变量分析 `_free_names`（comprehension/lambda 作用域精确版，循环变量只在推导式内绑定，越界引用按 `unknown_name` 拒绝）；②字符串纯方法白名单——15 个无副作用方法（`startswith/endswith/split/join/strip/lstrip/rstrip/lower/upper/isdigit/isalpha/isalnum/isspace/find/count/replace`）入 `<attr>` 白名单（`title/center/encode/format` 等刻意不收，作为反例教学形态）；③迭代域内建——`range` / `enumerate` 单独出现亦无害。提示契约（`src/agents/planner.py` BNF 段 + 7 正例 + 5 反例 + 自检）与编译器白名单经 `spec_expr_grammar_terminals()` 单一事实源同步（新增 `quantifiers` 键供 BNF `<quant>` 渲染）。原 P2-L3 已知假阴性（推导式变量被标识符门误杀，strict xfail）经 v3 自由变量分析修复后转正，套件现 0 xfail。
3. **并列执行接线（R1c，`SPEC_ORACLE_EXEC_ENABLE` 默认关）**：`_generator_node` 经 `_append_spec_oracle_to_test` 把 v2 编译产物追加到 LLM 生成测试尾部**并列**执行——LLM 测试通过 ≠ 规约 oracle 通过；oracle 在缺陷代码（buggy 侧）上的失败只是**单侧信号**，**不构成"确定性检出"判定**：检出须按双侧判据（buggy 红 ∧ gold fixed/修复后绿 ∧ 两侧无收集/语法错误，即 F2P 口径）由实验评估层独立裁决，单侧失败仅作机制观测与归因线索（评估层不得直接计为 detection；N-3 起 oracle 单独以 `oracle_suite_verdict` 判读）。观测字段 `state["spec_oracle_injected"]`。启用方式：单开关，或 `AITESTER_PROFILE=scientific` 一键。

**编译率观测**：`spec_compile_rate`（可编译子句数/非空子句总数）量化"逻辑驱动"的实际机器化程度（`SPEC_IR_DSL_ENABLE=true` 时由 Planner 节点写入 state）。

---

## 3. 分层错误修复协议（Algorithm 2 & 3）

> **修复引擎范式（2026-10-07 批次 I 范式转向）**：修复流程升格为"**局部化 → 合成 → 验证**"三段，局部化从"Debugger 的副产品"升格为可独立量化的第一阶段。局部化采用**双通道融合**：
> 1. **谱系通道**（零 LLM）：Ochiai 谱系 Top-k 行级可疑度排序（`FL_SPECTRAL_ENABLE`，默认 true），作为客观佐证注入 prompt；
> 2. **推理通道**（LLM）：RGFL 式结构化定位（`FAULT_LOCALIZER_ENABLE`，默认 true）——输入带行号源码 + 失败测试 + 错误输出 + 谱系 Top-k 佐证，输出 `{function_name, line_start, line_end, confidence, reasoning}`，**只定位不修复**；LLM 失败 / JSON 解析失败保守降级 None，不产出假定位、不阻断修复。
>
> 融合接线在 `_debugger_node`：定位结果写 `state["llm_localization"]`，经 `build_localization_prompt_section()` 与谱系段落并列注入 Debugger prompt。局部化质量由独立指标量化：`localization_hit_function`（LLM 定位函数 ∈ gold 变更函数集合，函数级）与 `fl_at_k`（谱系行级 Top-k 命中），与检出率 / 修复率并列输出。

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

> **协议说明（ADR-0015 / ADR-0016 现行口径，2026-10-18 同步更正）**：本算法按**检出优先（"先红后绿"）**协议重写。历史版本（每次迭代 `T ← Generator(S_current)`、`passed` 即成功）与现行实现和 ADR 不一致，已按 ADR-0015（检出优先协议）与 ADR-0016（编排为可消融容器 + **测试文件锁定原则**）更正。协议开关默认关（ADR-0003 默认行为不变原则）；`AITESTER_PROFILE=logic` 档注入 `DETECTION_FIRST_ENABLE=true` 与两道门开关，关闭时退回"首轮全绿即结束"的历史口径、终态字段为 `None`（键集合同构）。

```
Algorithm 3: Detection-First Iterative Repair Loop（先红后绿）
Input:  原始缺陷代码 S₀；最大迭代次数 K；再生成预算 R（_MAX_REGENERATIONS）
Output: 修复后代码 S'；是否检出 detection；是否修复 repair；
        终态标注 status ∈ {red_then_green, all_green_unverified, red_not_repaired}

1:  S_current ← S₀ ; red_seen ← false ; status ← None
2:  T ← Generator(S₀)                     // 测试在修复循环前生成，循环内锁定
3:  (passed, output, failed_cases) ← Executor(T, S₀)   // 首轮基线执行（代码未修复）
4:  if passed then                         // 首轮全绿 = 未检出缺陷，不视为成功
5:      T ← RegenerateStrengthened(T, ≤R)  // 先红后绿强化提示；受 R 上限保护
6:      若仍全绿 then return (S₀, detection=false, repair=false, all_green_unverified)
7:  if 首轮红 then
8:      red_seen ← true ; T* ← T            // 红证人快照（锁定测试）
9:      if 特异性门开启 then
10:         v ← ExecuteOnGoldFixed(T)       // 在环双侧对照：gold fixed 侧须转绿
11:         if v == over_red then T ← Regenerate(T, ≤R) ; goto 3  // 过红 → 换缺陷特异测试，不进修复循环
12: for i ← 1 to K do
13:     e ← Classifier(output, failed_cases)          // ErrorClassifier（Algorithm 2）
14:     patch ← Debugger(S_current, output, e)        // 只生成源码修复补丁
15:     S_current ← ApplyPatch(S_current, patch)      // PatchApplier；失败回滚
16:     (passed, output, failed_cases) ← Executor(T, S_current)
17:     if passed then
18:         红回归门（若开启）：T 曾被再生成替换且 S_current 未修补 → T ← T*，置失败，continue
19:         status ← red_seen ? red_then_green : all_green_unverified
20:         return (S_current, detection=red_seen, repair=red_seen, status)
21: end for
22: status ← red_seen ? red_not_repaired : all_green_unverified
23: return (S_current, detection=red_seen, repair=false, status)
```

**判定口径（"passed"本身不是成功）**：

- **检出（detection）双侧判据**：F2P = 生成测试在 buggy 原始代码上红 **∧** 在 gold fixed（或修补后）代码上绿 **∧** 两侧均无收集/语法/执行错误；仅 buggy 侧红（单侧）只作机制信号，不判检出。
- **修复（repair）双侧判据**：逻辑闭环要求"先有红证人（曾检出）**∧** 修补后绿"；评估层 `repair_rate` 另以 **gold 材料独立裁决**——gold 测试在**补丁已写盘的最终代码**上全绿才计修复成功（无补丁写盘记 0.0，不可测记 None）。`all_green_unverified`（从未红即全绿 = 弱测试假成功）**评估层不得计为检出/修复成功**；`red_not_repaired`（曾观测红且未修复）只是**协议层机制状态**（算法伪码中的 `detection=red_seen` 同为协议层信号），**不构成有效检出的充分条件**——有效检出始终由评估层独立 F2P 三段判据（buggy 红 **∧** fixed 绿 **∧** 无执行错误）裁决；主批 88 行 `red_not_repaired` 属 buggy/fixed 皆红（过红，不满足 F2P），其 `detection=0` 即反例，不得为迎合文字把这 88 行改计检出。
- **测试锁定 / 不得靠换测试达成绿灯**：修复循环内测试 `T` 锁定；再生成仅允许经三类受 `R` 上限保护的专用路由（首轮全绿、特异性门 `over_red`、诊断判为测试缺陷）。红回归门检测"曾见红 + 测试被再生成 + 源码未修补"时恢复红证人测试并交回修源码通道——这是 ADR-0016 决策 4"修复循环内不得以换测试方式达成绿灯"的机制保证。
- **开关与默认**：`DETECTION_FIRST_ENABLE` / `DETECTION_SPECIFICITY_GATE_ENABLE` / `RED_REGRESSION_GATE_ENABLE` 均默认关（ADR-0003）；logic 档与显式实验批次开启。关闭时历史口径逐字节不变。

**实现位置**：路由在 [src/graph/workflow.py](../src/graph/workflow.py) 的 `_should_debug()`；首轮红灯/终态标注在 [src/graph/nodes.py](../src/graph/nodes.py) 的 `_executor_node`（`_derive_detection_first_status` 由 `(passed, red_seen)` 推导三值）；双门判定在 [src/tools/detection_gates.py](../src/tools/detection_gates.py)。

> **路由信号优先级（2026-10-05 审查批次 R17）**：`ROUTE_STRUCTURED_ENABLE=true`（默认关）时，"测试生成错误"路由信号采用**结构化优先、关键词兜底**口径——`error_category=logic_error`（错误分类器从失败栈判定：断言失败但栈未触及被测模块，即测试自身逻辑错误）优先于中文诊断关键词匹配（`_test_gen_signal_hit`）；信号来源（`structured_error_category` / `diagnosis_keyword`）写入 trace，可度量关键词兜底触发率。动机：关键词匹配依赖 LLM 诊断文本，曾在 M5 事故中被源码异常签名（AttributeError/NameError/SyntaxError）误判触发假通过。开关关时与历史关键词口径逐字节一致。

> **3.5 跨文件扩展路径**（`CROSS_FILE_ENABLE=true` 时启用，默认关）：在 `executor` 与 `debugger` 之间插入 `cross_file_analyzer` 节点（`_cross_file_analyzer_node`），做 AST 跨文件 import 依赖分析并把依赖边写入 `state["cross_file_deps"]`；`_patch_applier_node` 在跨文件分支按拓扑序对多模块应用补丁（被调用方先改、调用方后改），任一文件失败经 `cross_file_fallback_single_file()` 降级为仅入口模块应用（与单文件 `safe_apply_patch` 同口径）。详见 [docs/design/cross_file_repair.md](design/cross_file_repair.md)。

---

## 4. 多智能体编排协议（可消融容器，ADR-0016）

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

> **修复引擎批次 I 新增状态键**：`llm_localization`（RGFL 推理定位结果，`_debugger_node` 写入，`{function_name, line_start, line_end, confidence, reasoning}` 或 None）；既有键 `fl_spectral_focus`（谱系 Top-k，O2）承担谱系通道。两者共同供实验层局部化指标消费。

### 4.2 消融实验配置矩阵

通过布尔开关控制节点启用/禁用，形成 4 种实验变体（配置见 [config.py](../config.py)）：

| 变体 | ENABLE_PLANNER | ENABLE_DEBUGGER | ENABLE_RAG | 对应基线 |
|:----:|:--------------:|:---------------:|:----------:|---------|
| 完整系统 | true | true | false | AITester |
| 无 Planner | false | true | false | 无规划基线 |
| 无 Debugger | true | false | false | 无修复基线 |
| 纯 LLM | false | false | false | plain_llm |
| 单智能体 | — | — | — | single_agent |

> **定位通道消融（修复引擎批次 I 起）**：`FAULT_LOCALIZER_ENABLE`（默认 true，false=纯谱系消融口径）与 `FL_SPECTRAL_ENABLE`（默认 true）独立于上述四变体，可叠加出"双通道完整 / 仅谱系 / 仅推理 / 无定位"四档定位消融，用于隔离两条局部化通道各自的贡献。

---

## 5. 理论正确性说明

### 命题 1（修复可收敛性，可证伪经验命题）

**陈述**：给定迭代预算 $K$ 与 LLM 温度 $T$，算法的修复成功率 $p$ 是一个**可测量**的经验量——随缺陷类别（SYNTAX/RUNTIME/ASSERTION/TIMEOUT/UNKNOWN）、错误分类粒度与定位通道精度而变化，**不由任何模型能力假设先验保证**。

**证伪方式**：$p$ 以 `repair_rate` 与 `false_fix_rate` 双口径在 gold 独立裁决下于每一批次实测；若某缺陷类别在固定 $K$ 下 $p$ 持续为 0 或接近 0，则该类别"可修复"的主张被证伪。本系统主批次实测原始口径 repair=0、修正口径 39.31%（57/145 可重放），说明"存在成功路径"的保证在实际中很弱，修复成功率必须以实测为准。

> **勘误（2026-10-13 独立评审 S-01 / T-04）**：原"定理 1（完整性）"以"LLM 具备足够能力"为前提，而其结论（存在成功路径）已蕴含于该假设（"LLM 输出空间包含正确修复方案"），属同义反复。本版本改写为上述可证伪经验命题。原"定理 2（终止性）"为结构性保证（由 `MAX_ITERATIONS` 上界给出），不依赖模型能力假设，予以保留。

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
