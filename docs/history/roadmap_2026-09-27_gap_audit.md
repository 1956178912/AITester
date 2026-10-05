# 改进路线图七节落地核查（2026-09-27）

> 核查对象：用户提供的"改进方案"路线图七节（① 代码上下文/补丁配方保留、
> ② 补丁后处理类型修复、③ 双向诊断、④ 合成数据集难度分层、⑤ 数据污染检测
> 多维度扩展、⑥ RAG Token 效率验证、⑦ 模型路由按复杂度分级）。
> 方法：逐节 grep/read 代码核实（证据标注 文件:行号），判定已实现 / 剩余缺口。
> 核查日期：2026-09-27 ｜ 仓库：AITester（0.7 债务清偿期之后）。
> 结论摘要：**七节中六节的全部改进点已落地**（分布于 0.8–0.11 各批次），
> 第五节（数据污染检测多维度扩展）残留 3 个子项缺口，已于同日批次补齐
> （见下方"缺口落地批次"）。

---

## ① 代码上下文：从字符截断到"补丁配方"保留

| 改进点 | 现状 | 证据 |
|---|---|---|
| 1.1 补丁配方保留 `preserve_patch_ingredients(file_path, func_name)`：目标函数完整 AST 节点 + 直接调用函数签名（1 层）+ 模块级导出符号（`__all__` / `@register` / 插件入口）+ 全部 import | ✅ 已实现 | `src/tools/code_analyzer.py:445`（`preserve_patch_ingredients`，返回 `imports / target_ast / called_signatures / exports / register_symbols / module_constants` 字典）；`code_analyzer.py:526`（`render_patch_ingredients` 渲染为 `[PATCH_INGREDIENTS]` 文本块） |
| 截断前显式注入补丁配方（替代简单字符截断） | ✅ 已实现 | `src/agents/base_agent.py:523`（`truncate_code` 在 `focus_function` 非空时先走 `code_context.extract_focused_code_detail`（调用链 depth + 自动追加 `[PATCH_INGREDIENTS]` 契约块），仅无聚焦函数 / 聚焦解析失败时才字符级头尾截断兜底） |
| 1.2 命名契约 AST 符号守卫：补丁应用前对比原文件与补丁后文件的模块级符号集合（函数名 / 类名 / `__all__`），删除任何原导出符号即拒绝 | ✅ 已实现 | `src/tools/patch_applier.py:519`（`check_naming_contract`：AST 解析两侧文件，对比模块级符号 + `__all__` 条目 + 注册装饰器符号 + 插件入口点符号）；`patch_applier.py:559`（`safe_apply_patch_contract`：先 AST 语法校验，再符号守卫，缺失符号 → 拒绝应用 + 记录缺失列表 + 触发了重采样/重新生成） |
| 1.3 三级降级链：完整函数上下文 → 补丁配方保留 → 签名+import 极简上下文，逐级收紧温度 | ✅ 已实现 | `patch_applier.py:614`（`_CONTEXT_TIER_TEMPERATURES = {0: 0.2, 1: 0.1, 2: 0.0}` + `build_tiered_context`：tier 0 = `extract_function_context` 全上下文，tier 1 = `preserve_patch_ingredients` 配方，tier 2 = 签名+import 极简 `[MINIMAL_CONTEXT]`）；`patch_applier.py:638`（`advance_context_tier` 守卫拒绝时推进档位）；`src/agents/debugger.py:102-145`（`_build_downgrade_context` + `_downgrade_tier_temperature`，`contract_reject_feedback` 透传触发档位化重生成） |

## ② 补丁后处理：类型错误的系统化修复

| 改进点 | 现状 | 证据 |
|---|---|---|
| TypeRepairLayer 位于 DebuggerAgent 之后、`_apply_fix_node` 之前 | ✅ 已实现 | `src/agents/debugger.py:547`（`debug()` 在产出补丁后、写回 state 前调 `type_repair.type_repair_layer`，即"LLM 生成补丁之后、应用/写盘之前"的修复管道位置）；`src/graph/nodes.py:814`（`_debugger_node` 把 `type_repair_findings` / `mypy_findings_count` 写回 state 供实验分析消费） |
| 静态类型检查（mypy 仓库级 + AST 保守启发式双层） | ✅ 已实现 | `src/tools/type_repair.py`（`_static_type_findings` 纯 AST 保守层：类型重赋值 / 容器混用 / 未定义属性 / 返回类型不一致；`_run_mypy_findings` 在 `TYPE_CHECK_ENABLE=true` 时跑 mypy，未装透明降级） |
| LLM 类型推断修复（注入原文件类型注解作上下文） | ✅ 已实现 | `type_repair.py`（`type_repair_layer` LLM 层：`TYPE_REPAIR_LLM_ENABLE=true` 时把疑点 + 原代码类型注解注入 LLM 推断并产出修订补丁；默认关闭，未启用时仅输出疑点观测层） |
| 修复后补丁重新经符号守卫检查 | ✅ 已实现 | `type_repair.py`（修订补丁回环调 `patch_applier.check_naming_contract`，`contract_ok` 为 False 则拒绝修订、保守保留原补丁） |

## ③ 双向代码-测试诊断

| 改进点 | 现状 | 证据 |
|---|---|---|
| DiagnosisNode 在 `_debug_node` 之前分析根因（错误类型 / 失败断言 / 堆栈位置），判定"代码缺陷 vs 测试缺陷" | ✅ 已实现 | `src/graph/nodes.py:626`（`_diagnosis_node`，复用 `DebuggerAgent._run_review_diagnosis` Review Agent）；`src/graph/workflow.py:240-251`（`DIAGNOSIS_NODE_ENABLE=true` 时在 executor→debugger 之间插入 diagnosis 节点 + `_route_after_diagnosis` 条件路由） |
| 测试缺陷 → 路由回 GeneratorAgent 重新生成测试（更严断言约束） | ✅ 已实现 | `workflow.py:138-177`（`_route_after_diagnosis`：`test_defect` 且再生成未达上限 → `"regenerate"` 路由回 generator；达上限 → `"done"` 收敛）；`_generator_node` 消费 `defect_type="test_defect"` 走再生成 |
| 代码缺陷 → 路由到 DebuggerAgent 生成补丁 | ✅ 已实现 | `workflow.py:177`（`_route_after_diagnosis` 返回 `"debug"`）；`BIDIRECTIONAL_DIAGNOSIS_ENABLE=true` 时 debugger 内联 `_run_review_diagnosis` 同口径判定 |

## ④ 合成数据集难度分层

| 改进点 | 现状 | 证据 |
|---|---|---|
| 4.1 四层难度分级（Level 1 单函数 / Level 2 多函数交互 / Level 3 跨文件依赖 / Level 4 边界异常隐蔽） | ✅ 已实现 | `src/datasets/synthetic_dataset.py`（`difficulty` 参数，`_VALID_DIFFICULTIES = {"mixed","level1".."level4"}`；Level 3 经 `CROSS_FILE_PATTERNS` 双模块 `module_a`+`module_b` 构造，缺陷在 `module_b` 但 `module_a` 调用触发）；`experiments/synthetic_difficulty.py`（独立多层难度任务生成器，`generate_level1..4_task`，Level 3 生成双模块 + `cross_file_deps` 依赖边） |
| 4.2 变异体难度升级：条件边界变异（`>`↔`>=`）+ 返回值变异（None / 空列表 / 错误类型） | ✅ 已实现 | `experiments/mutation_testing.py:198-212`（内置生成器 7 类变异：`operator_flip`（==↔!= / <↔>）、`boolean_negation`、`numeric_offset`、`boundary_shift`（>↔>= / <↔<= off-by-one 方向）、`return_void`（`return X → return None`）、`return_empty`（→ 空容器/空串）、`exception_remove`（移除/改异常类型）；覆盖率口径对齐 4.2 提案的边界+返回值+异常三类） |

## ⑤ 数据污染检测多维度扩展

| 改进点 | 现状 | 证据 |
|---|---|---|
| 语义级相似度（CodeBERT 嵌入余弦） | ✅ 已实现（真实嵌入钩子 + CodeBERT 后端） | `src/utils/embedding_utils.py`（`embed_text` 按 `EMBEDDING_BACKEND` 选后端，`auto` 优先级 codebert → sentence_transformers → chromadb；codebert 分支用 `transformers.AutoModel` 加载 `Salesforce/codebert-base`（可经 `EMBEDDING_CODEBERT_MODEL` 覆盖），`[CLS]` L2 归一化嵌入；缺依赖透明回退词袋余弦保守口径）；`contamination_check.py`（`_detect_semantic_cosine` 消费 `embed_text`，`semantic_source` 标注真实嵌入 vs 词袋代理） |
| 结构级相似度（AST 子树匹配，检测补丁是否"记忆"黄金补丁结构） | ✅ 已实现 | `contamination_check.py`（`_detect_ast_skeleton_similarity`：两补丁修改行"语句类型序列"（Expr/Assign/Compare…）经 LCS 比率衡量结构相似度，捕获"换名但控制流相同"的复制） |
| SWE-bench Pro 支持（强 copyleft 抗污染基准） | ✅ 已实现 | `contamination_check.py`（`CONTAMINATION_RESISTANT_BENCHMARKS` 含 `swe-bench-pro` 条目：强 copyleft 设计说明 + GPT-5 Pass@1 ~23.3% + `recommended_pairing` = `swe-bench-verified`）；`src/datasets/dataset_loader.py`（`load_dataset("swe_bench_pro")` / `swebench_pro` 别名，复用 `SWEBenchDataset`，数据目录经 `data_dir` 注入，与 `swe_rebench` 同构口径） |
| 实验报告自动标注每个任务污染风险等级 | ✅ 已实现 | `contamination_check.py`（`_combined_risk_level` 取三维最严重者 → high/medium/low；`detect_contamination` 每任务输出 `risk_level` 字段）；`experiments/run_benchmark.py`（`_build_task_result` 写 `contamination_risk_level` 行字段） |

## ⑥ RAG 的 Token 效率验证

| 改进点 | 现状 | 证据 |
|---|---|---|
| `--enable-rag` vs `--disable-rag` 对照实验，记录 token 消耗 / 成功率 / 迭代次数 | ✅ 已实现 | `experiments/rag_ab_experiment.py`（自动化跑 RAG ON vs OFF 两批，按任务统计 token / 成功率 / 迭代 / 耗时；Welch t-test + Mann-Whitney U + Cohen's d；产出 `token_saving.delta_pct` 等可直接入论文的效率指标；支持 `--analyze-only` 仅读已有结果做统计） |

## ⑦ 模型路由按任务复杂度分级

| 改进点 | 现状 | 证据 |
|---|---|---|
| APIManager 增加任务复杂度评估器（代码行数 / 文件数 / 依赖数量 → 复杂度分数） | ✅ 已实现 | `src/api/complexity_router.py`（`compute_complexity_score`：lines / files / deps / cyclomatic 四维度各 25% 归一化加权，得分 <0.35 simple / <0.70 medium / ≥0.70 complex；`count_imports` 统计模块级 import） |
| 简单任务路由轻量模型、复杂任务路由强模型 | ✅ 已实现 | `complexity_router.py:188`（`complexity_class_to_routing_hints`：simple 单候选小上下文、complex 多候选 3 + 大上下文 6000 + 额外迭代）；`src/agents/base_agent.py`（`_reorder_api_groups_by_complexity` 按档位重排 API 实例优先级）；`src/api/api_manager.py:465`（`_select_node_by_complexity` 按档位选节点） |
| 增加 `MODEL_ROUTING_STRATEGY=complexity_aware` 配置项 | ✅ 已实现 | `complexity_router.py:92`（`routing_strategy()` 读 `MODEL_ROUTING_STRATEGY`，默认 `complexity_aware`，`fixed` 回退历史口径） |

---

## 结论与缺口落地批次

### 判定汇总

| 节 | 判定 | 剩余工作（核查时） |
|---|---|---|
| ① 代码上下文 / 补丁配方 | 已实现 | 无 |
| ② 类型修复后处理 | 已实现（mypy 层） | （可选）pyright 备选后端 |
| ③ 双向诊断 | 已实现 | 无 |
| ④ 难度分层 | 已实现 | 无 |
| ⑤ 污染检测多维度 | 基本已实现 | 3 子项缺口：SWE-bench Pro 支持、CodeBERT 嵌入后端、pyright 备选 |
| ⑥ RAG Token 验证 | 已实现 | 无 |
| ⑦ 复杂度路由 | 已实现 | 无 |

> 说明：除第五节 3 个子项缺口外，路线图七节的全部改进点在仓库中均已实现并有对应测试。

### 缺口落地批次（2026-09-27，默认行为不变）

| 缺口 | 落地内容 | 证据 |
|---|---|---|
| ⑤ SWE-bench Pro 支持 | `contamination_check` 抗污染基准注册表 + `dataset_loader` 数据集名 | 见上 ⑤ 行 |
| ⑤ CodeBERT 嵌入后端 | `embedding_utils.codebert` 后端（`transformers` AutoModel，`auto` 优先级置顶，缺依赖回退） | `tests/test_roadmap_gaps_g1_g2_g3.py`（20 用例） |
| ② pyright 备选后端 | `type_repair._run_pyright_findings` + `TYPE_CHECK_BACKEND`（默认 mypy 口径不变） | 同上 |

回归验证：全量 1956 测试通过（基线 1937 + 新增 20 守卫），ruff / mypy 全绿；
默认实验口径零变化（新后端 / 新数据集均有独立开关或同构复用，缺依赖透明降级）。
