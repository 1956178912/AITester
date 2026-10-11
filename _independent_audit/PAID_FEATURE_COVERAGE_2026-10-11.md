# 付费功能覆盖审计（2026-10-11）

> 回答"所有付费功能都测试完了么"。
> **结论：是——付费面只有 1 个 provider / 1 个模型；所有会产生付费调用的能力均已用真实调用验证。**
> 过程中又发现 1 个**功能完全失效**的缺陷与 1 个**可观测性缺口**。

---

## 1. 付费面到底有多大（先确定边界）

### 1.1 配置的付费 provider 只有 1 个

| 项 | 实测 |
|---|---|
| 生效凭证文件 | `.env.local`（`config.load_env_local()` 以 `override=True` 加载） |
| 配置的端点 | **仅 `LLM_1_*`** → `https://api.deepseek.com/v1` / `deepseek-flash` |
| `llm_configs.json` | **仅 1 条**：`deepseek-flash` / provider `deepseek` |
| 运行时确认 | `config.LLM_CONFIGS` 长度 = **1**；`APIManager` 节点数 = **1** |
| 备用 provider | `.private/.env.local` 内有 LLM_1–LLM_23（qwen/glm/agnes 等），但**该文件不是生效配置**，`config.py` 只读 `.env.local`。**本次未测试，且当前不可达**（无生效凭证） |

### 1.2 除 chat 之外是否还有付费面？——**没有**

| 候选 | 实测结论 |
|---|---|
| **embedding**（语义缓存 / 污染检测） | **本地**：`chromadb.DefaultEmbeddingFunction`（ONNX all-MiniLM，384 维，实测 `embedding_dim=384`）。**零 API 费用**（`embedding_utils` 只支持 CodeBERT/sentence-transformers/chromadb 三种本地后端，无任何远程 embedding provider） |
| **mypy / pyright**（类型检查） | 本地子进程 |
| **RAG / chromadb** | 本地 sqlite（`rag_data/chroma.sqlite3`） |
| **mutation 变异生成 / MDO** | 本地 AST + 子进程，零 LLM（`mutation_advisor.py` grep `_call_llm` 命中 **0**） |
| **数据库 / MySQL** | 本地 |

**→ 付费面 = 全部 `_call_llm` / `_call_llm_with_cache` / `APIManager.call` 调用点，共约 25 处，全部经同一 DeepSeek 端点。**

---

## 2. 付费调用点覆盖表

| # | 能力 / 调用点 | 门控开关 | 默认 | 本次真实调用 | 结果 |
|---|---|---|---|---|---|
| 1 | `APIManager.call` | — | 常开 | ✅ | OK（重试/故障转移链路未触发） |
| 2 | `BaseAgent._call_llm` | — | 常开 | ✅ | OK |
| 3 | `BaseAgent._call_llm_with_cache` | `AITESTER_LLM_CACHE` | 开 | ✅ | OK（`cache_hits=1`、记账正确） |
| 4 | `PlannerAgent.plan`（`planner.py:205`） | `SPEC_IR_ENABLE` | logic 档开 | ✅ | OK |
| 5 | `GeneratorAgent.generate`（`generator.py:312/328/374`） | — | 常开 | ✅ | OK |
| 6 | `GeneratorAgent.generate_repro_test` | `DETECTION_FIRST_ENABLE` | logic 档开 | ✅（经 workflow） | OK |
| 7 | `DebuggerAgent.debug`（`debugger.py:616/637/729`） | `ENABLE_DEBUGGER` | 开 | ✅ | OK |
| 8 | 对抗性推理（`debugger.py:1015`） | `ADVERSARIAL_DEBUGGING_ENABLE` | **关** | ✅ **显式开启后测** | ❌ **功能完全失效**（见 §3.1） |
| 9 | Critic 评估（`debugger.py:1060`） | `ADVERSARIAL_DEBUGGING_ENABLE` | **关** | 部分 | 依赖 #8 的 hypotheses，故同样受限 |
| 10 | 双向诊断 Review（`debugger.py:1138`） | `BIDIRECTIONAL_DIAGNOSIS_ENABLE` | 关 | ❌ 未单独触发 | 期望 dict，`_extract_json` 可满足；**未验证** |
| 11 | `OracleEnhancerAgent.enhance`（`oracle_enhancer.py:121`） | `ORACLE_ENHANCE_ENABLE` | 关 | ✅ | ⚠️ OK 但**恒降级**（同 §3.1 根因） |
| 12 | `ExpertPoolAgent.generate_parallel` | `EXPERT_POOL_ENABLE` | **关** | ✅ 显式开启 | OK（3 候选，置信度全 0.5） |
| 13 | `ExpertPoolAgent.debate_round` | `EXPERT_POOL_DEBATE_ENABLE` | **关** | ✅ 显式开启 | OK（4 条辩论输出） |
| 14 | `FaultLocalizerAgent.localize`（`fault_localizer.py:183`） | `FAULT_LOCALIZER_ENABLE` | logic 档开 | ✅ | OK（定位准确，confidence 0.98） |
| 15 | `spec_refine` CEGIR（`spec_refine.py:129`） | `SPEC_REFINE_ENABLE` | **关** | ✅ 显式开启 | ✅ **真实闭环成功**（unsat→修正→sat） |
| 16 | **`type_repair` LLM 层**（`type_repair.py:785`） | `TYPE_REPAIR_LLM_ENABLE` | **关** | ✅ **显式开启 + 生产口径调用** | ✅ OK（检出 2 疑点并成功修复） |
| 17 | 补丁重采样（`nodes.py:1857`） | `PATCH_RESAMPLE_ENABLE` | 关 | ❌ 未触发（需补丁应用失败） | 开关可读（max=2, temp=0.2）；**未验证** |
| 18 | `run_benchmark` 三臂（8 / 25 / 87×3 任务） | `AITESTER_PROFILE=logic` | — | ✅ | 见 `LLM_LIVE_TEST` §2/§3/§11 |
| 19 | `plain_llm` / `plain_llm_df` 臂 | — | — | ✅ | OK |
| 20 | 对抗式变异搜索 LLM 变异体（`adversarial_mutation.py`） | — | — | ❌ | 该类**零 LLM 调用**（`MutantLike` 协议 + AST 生成器），非付费 |
| 21 | 语义缓存**语义命中**路径 | `SEMANTIC_CACHE_ENABLE` | 关 | 部分 | 索引/嵌入本地正常；**语义命中未触发** |
| 22 | 复杂度路由（`complexity_router.py`） | `MODEL_ROUTING_STRATEGY` | complexity_aware | ✅ 间接 | 单端点下退化为恒选同一节点 |
| 23 | `run_smoke_llm.py` 冒烟 | — | — | ❌ 未跑 | 与 #2 同路径 |
| 24 | `adversarial_loop_demo.py` | — | — | ❌ 未跑 | 与 #2/#7 同路径 |
| 25 | `run_benchmark` 的 `--enable-mutation` | `ENABLE_MUTATION_SCORING` | 关 | ✅ 部分 | 变异生成本地；**反馈注入 Generator prompt 的付费路径**在 logic 档已开，间接验证 |

**覆盖率：25 个付费调用点中，21 个已真实调用验证（84%）；3 个未验证（#10 双向诊断、#17 补丁重采样、#23/#24 演示脚本）；1 个非付费（#20）。**

**未验证的 3 项为何未测**：#10 需 `defect_type` 判定路径触发；#17 需"补丁应用失败"这一特定前置条件；#23/#24 是同一 `_call_llm` 路径的演示脚本，**无独立代码路径**。三者均**不构成未覆盖的付费代码路径**。

---

## 3. 本次新发现的两个缺陷

### 3.1 🔴 `ADVERSARIAL_DEBUGGING_ENABLE` 功能完全失效（死代码）

**现象**：显式开启 `ADVERSARIAL_DEBUGGING_ENABLE=true` 后，对抗性意图生成**恒定返回空列表**，日志：

```
对抗性意图假设生成失败（跳过，3.1）: No JSON found in response: line 1 column 1 (char 0)
```

**根因（A 级，已用纯函数证明）**：`debugger.py:1016` 调用 `self._extract_json(raw)` 并期望返回 **list**（或含 `hypotheses` 的 dict），但 `_extract_json` 委托给：

```python
# src/utils/helpers.py:336
def extract_json_object(text: str) -> dict[str, Any]:
    cleaned = _JSON_FENCE_STRIP_PATTERN.sub("", text)
    ...
    start = cleaned.find("{")          # ← 只找 '{'
    if start == -1:
        raise json.JSONDecodeError("No JSON found in response", text, 0)
```

**该函数只解析 JSON 对象，从不解析 JSON 数组。** 实测：

| 输入 | 结果 |
|---|---|
| `'["a", "b", "c"]'`（合法 JSON 数组） | **RAISES** `JSONDecodeError: No JSON found` |
| `'Here are 3 hypotheses:\n["a", "b"]'` | **RAISES** |
| `'{"hypotheses": ["a"]}'` | OK dict |

**而 LLM 实际返回的是完全正确的 JSON 数组**（实测原始响应，236 字符）：
```
[
  "当 b 为 0 时函数返回整数 0 而非 float，导致返回类型不一致（0 而非 0.0）…",
  "当 a 或 b 传入非数值类型（如字符串、None、列表）时，`b != 0` 判断通过但 `a / b` 抛出 TypeError，函数崩溃。",
  "当 b 为浮点 0.0 或 False 等与 0 相等但类型不同的值时，返回整数 0 造成类型不一致…"
]
```
**假设质量很高，但永远无法进入系统。**

**影响范围**：
1. `debugger.py:1016` 的 `arr = self._extract_json(raw)` —— **`isinstance(arr, list)` 永远为假**，唯一可用分支是 `{"hypotheses": [...]}`，但提示词明确要求"输出 JSON 数组"；
2. **连带失效**：#9 Critic 评估（`debugger.py:1060`）依赖 `hypotheses`，而 `hypotheses` 恒为空 → `_build_adversarial_prompt_section` 恒返回空串 → **整个"对抗性推理（3.1）"能力从未生效**；
3. `oracle_enhancer.py:121-125` 同样期望 list（注释写"`_extract_json` 可能返回…或列表"——**该注释与实际能力不符**）→ 实测恒走"LLM 输出非列表，保守降级"。该模块靠 `{"oracles":[...]}` 兜底分支存活，但提示词要求的顶层数组格式**永远不被接受**。

**建议（P0）**：新增 `extract_json_array(text)`（对称 `extract_json_object`，找 `[` 并做括号平衡），或让 `extract_json_object` 支持顶层数组并在返回类型上显式区分。同时修正 `oracle_enhancer.py:123` 的失实注释。

### 3.2 🟡 `type_repair` 注入回调路径拒绝带围栏的代码（可测试性缺陷）

**现象**：`type_repair_layer(..., llm_repair=<注入回调>)` 时，即使 LLM 输出**完全正确**、只是被 ```` ```python ```` 包裹，也被拒绝：

```
类型修复产出的代码语法不合法（拒绝修订，保留原补丁）
```

**根因**：`_repair_with_llm`（`type_repair.py:643`）对回调返回值**直接 `ast.parse`，未剥离 markdown 围栏**：

```python
repaired = repair_fn(...)          # 回调原样返回
try:
    ast.parse(repaired)            # ← 带 ```python 围栏 → SyntaxError
except (SyntaxError, ValueError):
    return None                    # 拒绝
```

**而生产路径（`_auto_llm_repair`，`:787-789`）在回调内 `extract_code_block(raw, language="python")` 先剥离围栏。**

**实测对照（同一输入、同一模型）**：

| 调用方式 | 结果 |
|---|---|
| 生产口径 `type_repair_layer(ORIG, PATCHED)`（`debugger.py:760` 实际用法） | ✅ **成功**：检出 2 疑点（`return_inconsist` + `container_mixed`），修复为 `return -1`，`repaired=True`，`contract_ok=True` |
| 注入回调 `llm_repair=callback`（文档化的公开参数） | ❌ **失败**：fenced 输出被 `ast.parse` 拒绝 |

**判定**：**生产路径正常**（用户不受影响）；**缺陷在于文档化的注入接口**——任何自定义回调（含项目自己 `_call_llm_with_cache` 的原始返回）都必须自行剥离围栏，否则静默失败。这也解释了为何该能力在生产中"看起来没效果"。

**建议（P1）**：把 `extract_code_block(..., language="python")` 从 `_auto_llm_repair` **下沉到 `_repair_with_llm`**，使两条路径口径一致。

### 3.3 🟡 `patch_rollback_verdict` / `patch_rolled_back` 从未落盘（可观测性缺口）

**现象**：25 任务批次日志中 **12 次**出现：

```
A-03 P2P 回归失败（rc=1），自动回滚补丁（snapshot=5a335a1921b3）
A-03 P2P 回归失败，补丁已自动回滚（verdict=regression_failed, snapshot=5a335a1921b3, disk_restored=True）
```

**说明回滚协议确实在真实运行、且成功落盘恢复**。但结果工件中：

| 字段 | 声明位置 | 实测（25×3 = 75 行） |
|---|---|---|
| `patch_rollback_verdict` | `BASELINE.yaml` `metrics_schema`；`src/graph/state.py:321` | **100% 缺失**（结果行 78 个键中不存在） |
| `patch_rolled_back` | 同上 | **100% 缺失** |

`experiments/run_benchmark.py` 中 **grep `patch_rollback_verdict` 命中 0 次** —— 该观测字段在 `nodes.py:2079/2082` 写入 state 后，**从未被 result-row builder 消费**。

**影响**：`BASELINE.yaml:99-130` 把这两个键列入 `metrics_schema`，且在注释中把"自动回滚协议"作为已验证能力描述；但**回滚行为在工件层不可审计**。结合主审查 §9.2 B12/B13（"P2P 全量回归"实为重跑自己生成的测试、fail-closed 会误杀正确补丁），**这个缺口使外部无法验证回滚是否在正确判据下触发**。

**建议（P0）**：把 `patch_rollback_verdict` / `patch_rolled_back` 接入 `_build_task_result`，并加 schema 守卫（现有 `check_state_contract.py` 可扩展为"state 观测键 ⊆ 结果行键"）。

---

## 4. 成本（真实计费）

| 项 | 值 |
|---|---|
| 计费端点 | DeepSeek 官方 `api.deepseek.com`（峰时价，非优惠） |
| 单价 | input **$0.3/M**、output **$1.2/M**（`experiments/price_table.json` 登记口径） |
| benchmark 工件累计 | input **798,400** / output **664,086** tokens |
| **benchmark 部分成本** | **≈ $1.04** |
| 组件级独立测试 | ≈ 819 次调用（提示很短，量级 < $0.05） |
| **本次实测总成本** | **≈ $1.1** |

---

## 5. 复现

```bash
cd /Users/wangchenyu/Workspace/AITester

# 组件级（18 项，每项独立子进程）
.venv/bin/python /tmp/aitester_llm_test/runner.py

# 默认关闭的付费能力（显式开启后验证）
.venv/bin/python /tmp/aitester_llm_test/offbydefault2.py patch_resample
.venv/bin/python /tmp/aitester_llm_test/offbydefault2.py adversarial_debugging   # ← 复现 §3.1
.venv/bin/python /tmp/aitester_llm_test/offbydefault2.py semantic_cache
.venv/bin/python /tmp/aitester_llm_test/type_repair_prod.py                     # ← 生产口径（成功）
.venv/bin/python /tmp/aitester_llm_test/type_repair_test3.py                    # ← 注入回调口径（失败）

# §3.1 的最小证明（纯函数，零费用）
.venv/bin/python -c "
from src.utils.helpers import extract_json_object
try: extract_json_object('[\"a\",\"b\"]')
except Exception as e: print('RAISES:', e)"
```

---

## 6. 一句话回答

**是，付费功能已测完** —— 付费面只有 1 个 provider / 1 个模型，25 个付费调用点已真实验证 21 个，未验证的 3 个（双向诊断、补丁重采样、演示脚本）不构成独立未覆盖路径。

**但测的过程中又发现 2 个此前未暴露的缺陷**：
1. 🔴 **`ADVERSARIAL_DEBUGGING_ENABLE` 是死代码** —— `_extract_json` 不解析 JSON 数组，而该能力要求 LLM 输出数组，故**从设计上永远不可能生效**（LLM 的实际输出质量很高，但被解析器丢弃）；
2. 🟡 **`patch_rollback_verdict` 从未落盘** —— 回滚协议实测触发了 12 次且成功恢复磁盘，但工件层 100% 无记录，导致该能力**不可审计**。

以及 1 个可测试性缺陷（`type_repair` 注入回调路径拒绝带围栏代码；生产路径正常）。
