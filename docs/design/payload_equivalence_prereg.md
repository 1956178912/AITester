# H1 载荷等价实验 —— 预注册（先声明后取数）

| 项 | 值 |
|---|---|
| **文档状态** | **预注册（pre-data）**。截至本文件落盘，**H1 的任何一臂均未执行**，无 H1 数据被采集或查看。 |
| 登记日期 | 2026-10-10 |
| 关联任务 | task-7 必做 2（P1-5）；上游假说来自 `REVIEW_2026_FRONTIER.md` §H1 / `review_2026/T3_domain_audit.md:126,448` |
| 主终点定义者 | 本文件（不可在取数后修改，改动须走 §8 偏离登记表） |
| 运行器 | [experiments/run_payload_ab.py](../../experiments/run_payload_ab.py)（骨架；`--dry-run` 已验证） |
| 相关既有预注册 | [docs/preregistration.md](../preregistration.md)（E4 污染防控 :124-153；E6 预算匹配） |

> **诚实性声明**：本预注册撰写者在撰写前**已查看**非 H1 的存量批次工件
> （`experiments/results/e6_a1_batches/**`，含 E4 FIXED harness 两臂）。这些数据**不是** H1 数据，
> 但被用于 §2.6 的检验力估算（观测不一致率）与 §5 的预算估算。**该使用已在此处披露**，
> 且不构成对 H1 任何一臂的结果预判。§2.6 的检验力估算所依据的是"现有 −28pp 对照的不一致率"，
> 与 H1 的自变量（Generator 载荷）无关。

> **引用行号的基准代码态**（`git hash-object`，工作树内容）：`src/agents/generator.py` `3dcce87e`、
> `src/agents/planner.py` `8af37376`、`src/graph/nodes.py` `8adb660a`、`src/graph/state.py` `d50c2406`、
> `src/tools/logic_spec.py` `273f115a`、`src/tools/detection_gates.py` `14915626`、
> `experiments/run_benchmark.py` `9c9ca407`、`experiments/_m1_metrics.py` `27861829`。
> **注意**：本任务执行期间有其它成员在改 `src/`，`nodes.py` 行号已实测漂移
> （`spec_oracle_injected` 写入点 865 → **967**）。**落地 P-1 干预前须以 blob sha 复核。**

---

## 0. 前置依赖声明（**用户明确要求的执行顺序，硬性**）

> **执行顺序：先修围栏残留（P0-2）→ 再跑载荷等价（H1）→ 再打开逻辑通道（C3）。**

本顺序是**用户明确指令**，不是本预注册的建议。违反顺序即视为 H1 结果无效。

### G0 —— 围栏回灌门（P0-2），**H1 的强制前置**

**问题（已一手核验）**：`e4_quixbugs_FIXED_harness/aitester.json` 全部 **50/50** 行的
`details[].patch` 字段**以 `python\n` 开头**——即 ` ```python ` 围栏标记被剥离后**语言标签残留**。
`normalize_patch_text`（`src/tools/patch_applier.py:58`）已实现"围栏 + python 前缀"清理，
M1 裁决层（`experiments/_m1_metrics.py:395-397`，批次 VII / ADR-0021）**已消费**它；
但**写盘链路与结果行透出仍暴露原始值**。ADR-0021 记录该伪影曾导致
"repair 全线 0"（E2 存量实测 **274/274** 行受影响，清理后重放 51/106 通过）。

**为什么它必须先修**：H1 的主终点是 `detection_rate`，而 `detection_rate` 与 `repair_rate`
共用 `_target_code_after_patch` 这一"把补丁文本变成新代码"的原语。围栏残留未修时，
**补丁文本 → 代码**的转换在不同链路（写盘 vs 裁决）上口径不一致 ⇒ H1 的"载荷"操纵
会与"补丁文本伪影"混杂，无法归因。且 `PLAN_STRIP_EXPECTED_OUTPUT_ENABLE`（A1 消融）
已有一次"干预未生效却被当成零效应"的先例，H1 **不得**重蹈。

**G0 验收判据（三条全绿才允许启动 H1）**

| # | 判据 | 验证方式 |
|---|---|---|
| G0-a | 一次冒烟跑（n≤3、`--dry-run` 之后的真实小跑允许）的 `details[].patch` **不再**以 `python\n` 开头 | `.venv/bin/python -c "import json;…"` 逐行断言 |
| G0-b | `GENERATOR_PAYLOAD`（见 §2.2）与 `ORACLE_CONTEXT_TIER` **已登记**进 `_env_snapshot_keys`（`experiments/run_benchmark.py:2712-2771`，实测当前 **39 键，二者均缺失**） | `python scripts/gates/check_env_snapshot_keys.py --all-keys` 退出码 0 |
| G0-c | 上条的门禁 `--select` 默认为 `_ENABLE$`，**不覆盖** `GENERATOR_PAYLOAD`/`ORACLE_CONTEXT_TIER` 这类非 `_ENABLE` 形态的键 ⇒ 须显式加入白名单或扩正则 | 同上 + 人工复核 |

> **G0-b/c 的理由**：`env_snapshot` 是"从工件证明干预是否生效"的**唯一**通道。
> 已发生三起同类事故（`PLAN_STRIP_EXPECTED_OUTPUT_ENABLE` A1 首跑 / `OVER_RED_SECTION_ENABLE` D3 /
> `DETECTION_FIRST_SECTION_ENABLE` RT1 首跑），机制完全一致：**代码新增开关，快照清单未同步**。
> H1 的自变量就是一个新开关 ⇒ G0-b 不通过则 H1 的干预**不可从工件证明**，实验无意义。

### G1 —— 逻辑通道门（C3），**在 H1 之后**

C3（逻辑通道）的开启排在 H1 之后，理由：C3 需要实验层新增字段透出
（`spec_oracle_injected` / `spec_oracle_verdict`，见 E3 报告 §4.2），
会同时改动 `run_benchmark.py` 的 details 组装路径。若在 H1 前改动，
H1 三期臂的**代码态不同**（provenance `git_sha` 不同），破坏单变量比较。
⇒ **H1 三臂必须在同一代码态下跑完，C3 埋点在 H1 落盘后再合并。**

---

## 1. 背景与假说

### 1.1 待解释的现象

项目 −28pp 的**三次复现**（δ = −0.279 / −0.3673 / −0.253），全部测的是 **`logic` 档**（多智能体编排）。
现有归因（ADR-0016）落在"编排结构净负"，但**预算混杂假说已被 E6 phase2 证否**
（df 抬预算不消费、aitester 压预算更差）。⇒ 剩余的候选解释中，**载荷（payload）**未被直接检验过。

**现有最接近的证据是间接的**：A1 消融（`PLAN_STRIP_EXPECTED_OUTPUT_ENABLE=true`，
仅剥 `test_cases[].expected_output` **一个**键）实测**零效应**（8/87 vs 8/87，δ=+0.0pp）。
但 A1 有**已知的结构性空转**：34/87（39%）任务触发"Planner 输出结构不完整，使用默认计划"，
此时 `test_cases = []`，**无 `expected_output` 可剥** ⇒ 该实验的效力范围仅剩 61% 任务。
⇒ **"剥一个键无效"不能推出"剥整个载荷无效"**。H1 要检验的正是后者。

### 1.2 H1 的精确表述

> **H1（载荷错配假说）**：在 `logic` 档多智能体编排**保持完全不变**（节点集合、拓扑、
> 调用次数上限、再生成上限、双门开关全部不动）的前提下，把 Generator 收到的**载荷**
> 从 `full` 降到 `df_parity`（仅被测代码 + 检出优先协议文本，逐字段清单见附录 A），
> 其 `detection_rate` 相对 `full` 载荷**提升 ≥ +20pp**（QuixBugs 41 个有 gold 缺陷程序的配对差）。
>
> **机制主张**：−28pp 的损失来自 Generator 收到的**载荷内容**（plan JSON 含
> `expected_output`/`logic_analysis.edge_cases` + RAG 参考 + 现存断言 + CFG/边界段 + 变异反馈），
> **而非**节点数量、拓扑或预算。

### 1.3 否证条件（**先声明**）

| 观测 | 判定 | 解释 |
|---|---|---|
| δ = ①−③ **≥ +20pp** 且 McNemar `p_adj < 0.05`（BH-FDR 校正后） | **H1 成立** | 载荷是主因；编排净负结论须收窄为"编排 + full 载荷"的联合效应 |
| δ = ①−③ **≤ +5pp**（落在 ROPE ±5pp 内） | **H1 否证** | 载荷不是主因；ADR-0016"编排结构净负"结论**加固** |
| +5pp < δ < +20pp | **不确定（indeterminate）** | **不得**按任一方向解读；须按 §5.3 扩样或登记为未决 |
| ①−③ 为**负**（① 比 ③ 更差） | **H1 反向证否** | 载荷减少反而有害；须登记并追查机制 |

> **"否证"必须是可接受的结局**：本实验的价值在于**二元可判定**，不在于 H1 成立。
> **禁止**在取数后修改 ±20pp / ±5pp 阈值（改动须走 §8 偏离登记表，且该偏离本身会成为报告的一节）。

### 1.4 与既有结论的关系（预先声明，防止事后叙事）

- 若 H1 成立 ⇒ `REVIEW_2026_FRONTIER.md` 的"编排净负"表述须改为
  "**`full` 载荷下**编排净负"；§1.1 的 −28pp 三次复现须加"载荷未对齐"限定词。
- 若 H1 否证 ⇒ ADR-0016 加固，但**仍不得**声称"载荷无关"——否证的是
  `df_parity` 这一个**极端**载荷水平（下界），不是载荷的连续效应（见 §7 局限）。

---

## 2. 实验设计

### 2.1 臂设计（**按用户指令：三臂 + df 外部参照**）

| 臂 | 载荷 `GENERATOR_PAYLOAD` | 编排 | 基线名 | 角色 |
|---|---|---|---|---|
| **① `p_df_parity__o_logic`** | `df_parity` | logic 档多智能体 | `aitester` | **H1 主检验臂** |
| **② `p_df_parity__o_mono`** | `df_parity` | 单体流水线（无 Planner、无修复循环） | `plain_llm_df` | 同载荷下的编排对照 |
| **③ `p_full__o_logic`** | `full`（现状 = 历史口径） | logic 档多智能体 | `aitester` | **H1 对照臂**（= 三次复现所测的臂） |
| **REF `df_stored`** | `df_parity` | 单体流水线 | 复用**存量工件** | **外部参照（不重跑）** |

**核心对比**：**① − ③**（编排固定为 logic，载荷变化）＝ H1 的**主终点**。
② 与 REF 的对比＝**操纵检查（manipulation check）**：若 ② 不能复现存量 df 工件，
说明环境不可复现，**H1 主终点不可解释**（§3.4 的 assay-sensitivity 前置判据）。

> **为什么不是 2×2 全因子**：单体流水线**没有 Planner**，`_build_query` 的
> `test_plan` 参数在该拓扑下不存在 ⇒ 载荷因子的 `full` 水平在单体拓扑下**不可构造**
> （不是"没跑"，是"不存在"）。故本设计是 **2 载荷 × 1 有效编排（logic）+ 单体作外部参照**，
> 而非完整 2×2。这一限制**预先登记**，不得在报告中当作设计缺陷被事后发现。

### 2.2 自变量操作化：`GENERATOR_PAYLOAD ∈ {full, df_parity, structure}`

**环境变量**：`GENERATOR_PAYLOAD`（新开关，**当前代码库不存在**，须先落地——见 §2.5 G0-b）。
默认 `full` = 历史口径**逐字节不变**（ADR-0003：新功能默认关）。

| 水平 | 定义 | 用途 |
|---|---|---|
| **`full`** | 现状（`logic` 档一切增强段按各自开关注入） | ③ 对照臂 |
| **`df_parity`** | **仅**被测代码 + `module_name`/import 约束 + 检出优先协议文本；**剥除**附录 A 列出的全部字段 | ① ② 主检验臂 |
| **`structure`** | 保留 plan JSON 的**结构骨架**（`function_name` / `description` / `test_cases[]{case_name, input_args, category, description, logic_coverage}`），但**剥除** oracle-来自-实现的三个锚点：`test_cases[].expected_output`、`logic_analysis.output_domain`、`logic_analysis.postconditions`；其余增强段同 `full` | **次要/探索性**，**不参与主终点**（见 §2.7） |

**`df_parity` 精确定义**（落点 `src/agents/generator.py::_build_query`，函数体 `:394-480`）：

> Generator 收到的 prompt **只含**三段：
> (1) `target_code`（经 `BaseAgent.truncate_code`）—— 对应 `:413`；
> (2) `module_name` + import 强约束 —— 对应 `:414`, `:420-423`；
> (3) **检出优先协议文本** —— 即 df 臂实际注入的强化段
> （`src/graph/nodes.py:490/511-517` `_detection_first_section` 与 `:530` `_over_red_section`）。
>
> **不再包含**：整个 `plan_json`、RAG 参考案例、现存断言注入、变异反馈、
> 分支覆盖段、AST 边界三元组段、蜕变/差分段。**逐字段清单见附录 A。**

**逐字段剥离清单（附录 A 摘要）**——`df_parity` **剥除**：

- 全部 `plan_json`（`:408`, `:411-416`）：`function_name`、`description`、
  `logic_analysis{input_domain, output_domain, preconditions, postconditions, edge_cases}`、
  `test_cases[]{case_name, input_args, category, description, logic_coverage, expected_output}`
- RAG 参考案例（`:427-436`，`_MAX_RAG_REFERENCES` 上限内）
- 断言增强 / 现存 assert 注入（`generator.py:439-449`，`ASSERTION_AUGMENT_ENABLE`）
- 变异反馈（`:455-478`：`survived_mutants` 前 5 个 + `mutation_score`）
- 分支覆盖段（`BRANCH_COVERAGE_INJECT_ENABLE`）、AST 边界三元组段
  （`boundary_triplets_section`，`BOUNDARY_TRIPLETS_ENABLE`）、蜕变/差分段（`MR_*` / `DIFF_*`）
- **不再额外新增**：`ORACLE_CONTEXT_TIER=minimal` 已剥离后四段（`src/tools/logic_spec.py:67-82`，env `ORACLE_CONTEXT_TIER`），
  `df_parity` **复用**该机制而非再造一套（避免口径分叉）

> **一个必须预先声明的口径订正**：任务书/H1 背景把 plan JSON 描述为含
> `expected_output` / `edge_cases` / `boundaries` 三字段。一手核验结果：
> - `test_cases[].expected_output` **存在**（`src/graph/flags.py:263`、`generator.py:46-80`）；
> - `edge_cases` **存在**，但位于 **`logic_analysis.edge_cases`**（`src/agents/planner.py:118,165,224`）
>   —— **不是** `test_cases[].edge_cases`；
> - **`boundaries` 不是 plan JSON 字段**：全 `src/` 检索，`boundaries` 仅出现在
>   **SpecIR v2 规约**（`src/specs/spec_ir_v2.py:456`）与 CFG 的 `loop_boundaries`
>   （`src/tools/control_flow.py:75`）中，是**独立注入段**（`logic_spec.derive_boundary_triplets`
>   → `boundary_triplets_section`，`src/graph/nodes.py:707-714`），**不随 plan JSON 序列化**。
> ⇒ 附录 A 按**实际代码**列字段，**不沿用**背景描述中的失实字段名。

### 2.3 常量控制（三臂必须**完全相同**，逐项可审计）

| 维度 | 值 | 说明 |
|---|---|---|
| profile | `AITESTER_PROFILE=logic` | 三臂一致；排除"档位差异"这一竞争解释 |
| 温度 | `TEMPERATURE=0.0` | 确定性采样（R11 三处级联） |
| thinking | `LLM_THINKING_MODE=disabled` | 与 E2/E6 预算口径一致（`docs/preregistration.md:96`） |
| 缓存 | **`AITESTER_LLM_CACHE=0`（cold cache）** | 硬性：热缓存命中不计 token 且**观测非独立样本**（`base_agent.py:339` 自述） |
| 缓存命名空间 | `AITESTER_CACHE_NAMESPACE=e3_h1_seed42` | 即便冷缓存也留痕（多 seed 独立性口径） |
| seed | `--seed 42` | |
| 迭代上限 | `MAX_ITERATIONS=3` | 与历史 −28pp 臂同口径 |
| 执行超时 | `EXECUTION_TIMEOUT=30` | 与历史口径一致；**不得**为提高检出而调整（会污染 C2 挂起通道） |
| 双门 | `DETECTION_SPECIFICITY_GATE_ENABLE=true`、`RED_REGRESSION_GATE_ENABLE=true` | **保持不变**（H1 只动载荷） |
| 检出优先 | `DETECTION_FIRST_ENABLE=true`、`DETECTION_FIRST_SECTION_ENABLE` 不设（默认 true） | 协议文本必须**在**三臂中一致存在 |
| 过红强化 | `OVER_RED_SECTION_ENABLE` 不设（默认 false） | 保持历史口径；若令其 =true 则不再是单变量 |
| 并行度 | `BENCHMARK_PARALLELISM=4` | 与 E6 一致 |
| 代码态 | 三臂**同一 `git_sha` + 同一 dirty 状态** | G0 完成后冻结；`--allow-dirty` 须带 `--dirty-reason` |
| RAG | `ENABLE_RAG=false`（基线默认） | 三臂一致 |

> **单变量纪律**：① 与 ③ 的 `os.environ` 差异**只允许** `GENERATOR_PAYLOAD` 一项。
> `run_payload_ab.py` 的 `env_snapshot` 校验会**逐键 diff** 并拒绝任何多余差异。

### 2.4 基准与协议

- **主终点数据集**：**QuixBugs 41 个有 gold 的缺陷程序**
  （口径见 `BASELINE.yaml:291-298`：50 任务 = **41 缺陷程序 + 9 测试驱动脚本**；
  9 个 `*_test` 驱动脚本 `task_metadata.test_cases` 为空串，M1 结构性不可测，**剔除或单列**）。
  `primary_endpoint_denominator: 41`，该口径**预注册于数据产生前**。
- **n = 41**，seed 42，cold cache，`--task-count 50`（跑满 50，按 id 过滤出 41 计算终点）。
- **本预注册不覆盖**：synthetic 批次、SWE-bench、真实仓库任务（无 gold ⇒ 特异性门 `unavailable`）。

### 2.5 两阶段执行（**先落地干预，再取数**）

| 阶段 | 内容 | 门 |
|---|---|---|
| **P-1 干预落地** | 在 `src/agents/generator.py::_build_query` 新增 `GENERATOR_PAYLOAD` 分派；登记 `_env_snapshot_keys` | G0-b/G0-c |
| **P0 冒烟** | n=3、`AITESTER_LLM_CACHE=0`，验证 `env_snapshot.GENERATOR_PAYLOAD` 三臂取值正确、prompt token 量级符合 §3.3 预期 | 冒烟通过 |
| **P1 主跑** | 三臂各 1 次，n=50（终点 41） | — |
| **P2 分析** | 按 §3/§4 判定 | — |

> **P0 冒烟是硬性前置**：若冒烟显示 ① 的 prompt token 较 ③ **未显著下降**，
> 说明载荷干预**未生效**（A1 首跑同类事故）⇒ **中止**，先修干预。

### 2.6 样本量与检验力（基于**存量非 H1 数据**的不一致率）

**观测（E4 FIXED harness，gold n=41，aitester vs plain_llm_df；已披露见文首）**：

| | df 检出 | df 未检出 |
|---|---|---|
| **aitester 检出** | 17 | 0 |
| **aitester 未检出** | **14** | 10 |

- 不一致对 **b+c = 14（34.1%）**，其中 `c = 0`（**零反向**），δ = 14/41 = **+34.1pp**，
  精确 McNemar 双尾 `p = 1.22e-4`。
- 该不一致率是"载荷/编排合并效应"的上界观测，用于**检验力下界估算**：
  在 14 个不一致对的规模下，精确 McNemar 双尾 `p<0.05` 需 **≥12 个单向对**（86%）。
- **MDES 推算**：+20pp ≈ 8.2/41 行净增。若 H1 效应为 +20pp 且不一致率与存量同量级（~14 对），
  则需 `b−c ≈ 8`、`b+c ≈ 14` ⇒ `b=11, c=3` ⇒ 精确双尾 `p ≈ 0.057`（**临界**）。
  ⇒ **n=41 对 +20pp 阈值的检验力偏低（约 0.5–0.6）**。
- **预先登记的应对**（不得事后追加）：
  1. **配对设计 + 单侧方向的精确 McNemar**（H1 有方向性预测：① > ③）⇒ 检验力提升；
  2. **贝叶斯 ROPE** 作为**主判定**的并列证据（不依赖 p 阈值，直接给 `P(|δ| ≤ 5pp)`）；
  3. 若落在 §1.3 的 **indeterminate 区**，按 §5.3 扩样（**只允许增加 seed，不允许更换数据集**）。

### 2.7 `structure` 水平的处置（**预算保护**）

`structure` 是**探索性次要水平**，**默认不跑**。仅当主终点落在 indeterminate 区（+5pp < δ < +20pp）
且 §5.3 的扩样仍不确定时，才按预注册顺序补跑 `structure` 单臂。
**禁止**在看到 ① − ③ 结果后临时改跑 `structure` 并把它当主终点（HARKing）。

---

## 3. 终点与判定

### 3.1 主终点

**`detection_rate` 的配对差** δ = `detection_rate(①)` − `detection_rate(③)`，
在 QuixBugs 41 个有 gold 缺陷程序上，**配对**（同一 task_id）。

- `detection_rate` 口径：**F2P 三段判定**（`experiments/_m1_metrics.py:473-540`）：
  buggy 红 ∧ gold fixed 绿 ∧ 两侧无收集/语法错误；超时/无材料 → `None`（不可测）。
- **`None` 的处置（预先声明）**：不可测行从**配对分母**中剔除，但**必须并列报告剔除数**
  （基线预期：41 行中 4 行为 `None`——9 个驱动脚本不在此 41 内）。
  **禁止**把 `None` 记为 0（会把挂起行算作未检出，见 E3 报告 §2.4）。

### 3.2 判定规则（**先声明**）

| 条件 | 判定 |
|---|---|
| δ ≥ **+20pp** ∧ `p_BH < 0.05`（单侧精确 McNemar，H1 方向） | **H1 成立** |
| δ ≤ **+5pp** ∧ 贝叶斯 `P(\|δ\| ≤ 5pp) ≥ 0.90` | **H1 否证**（ROPE ±5pp） |
| 其余 | **indeterminate** → §5.3 |

> 双侧报告纪律：主判定用**单侧**（H1 有方向）；但**必须并列报告双尾 p**，
> 以防读者误以为做了双侧检验。

### 3.3 过程指标（**必须报告，不参与主判定**）

| 指标 | 来源 | 用途 |
|---|---|---|
| **首轮 `specific_red` / `over_red` 拆分** | `details[].specificity_gate_verdict` | 检验"载荷减少 → 过红比例下降"这一机制路径 |
| **每任务 prompt token 分解** | `token_usage.input_tokens` + P-1 新增的分段计数 | **干预生效的直接证据**（① 的 prompt token 应显著低于 ③） |
| **`spec_oracle_injected`** | ⚠️ **H1 阶段尚不可得**（C3 未打开，见 G1） | H1 报告须**明确标注该指标缺失**，不得留空装作已测 |
| `regeneration_count` / `stop_reason` | `details[]` | 排除"再生成次数差异"这一竞争解释 |
| `plan_degraded` 比例 | `details[]`（若可得） | 排除 A1 式结构性空转 |
| 每任务 token 总量 | `details[].token_usage` | 预算可比性证明 |

### 3.4 Assay-sensitivity 前置判据（**先声明**）

若 ② 与存量 `df_stored`（REF）的 `detection_rate` 差异 **> 10pp**（即 ② 无法复现存量 df 臂），
则：**环境不可复现 ⇒ H1 主终点不得解释为载荷效应**，报告须标注
"assay sensitivity 未建立"，并把 H1 结论降级为"不可判定"。

> **阈值 +10pp 与 REF 的选择均在取数前固定**。REF 取
> `（工件已清除）`
> （sha256 `d23402fb…`，gold 口径 31/41 = 75.6%）。

---

## 4. 统计协议（**取数前固定**）

| # | 方法 | 规格 |
|---|---|---|
| S1 | **McNemar 精确检验** | 配对 2×2（b/c 不一致对）；主判定用单侧（H1 方向），并列双尾；`b+c < 25` 时用精确二项，≥25 时并列 χ²（连续性校正） |
| S2 | **BH-FDR 校正** | 对**全部预注册对比**（①−③ 主、②−REF 操纵检查、structure 探索）统一校正，`q = 0.05`；报告原始 p 与 `p_BH` |
| S3 | **贝叶斯 ROPE** | Beta-Binomial 配对模型（复用 `experiments/bayesian_paired.py` 的既有口径）；ROPE = **±5pp**；报告 `P(δ > 20pp)`、`P(\|δ\| ≤ 5pp)`、`P(δ < 0)` 与 95% 最高密度区间 |
| S4 | **模板级聚类校正（附 `n_eff`）** | QuixBugs **无模板** ⇒ 聚类单位**预先固定**为 §附录 D 的**算法族**划分（按程序名于本预注册时点冻结，未看任何 H1 结果）。报告设计效应 `DE = 1 + (m̄−1)·ICC`（ICC 由族内/族间配对差方差估计），`n_eff = n / DE`；主终点的 CI 用聚类稳健方差 |
| S5 | **模板级（族级）符号检验** | 对每个算法族计算族内配对差的符号，做精确符号检验（`H0: p=0.5`）；报告族级方向一致率 |
| S6 | **多重比较与文件抽屉** | 三臂 + REF 全部工件入盘（§6），**禁止**只报显著项；所有配对表原文附录 |

> **`n_eff` 的诚实边界**：附录 D 的族划分是本预注册撰写者按**程序名语义**作出的，
> 具有主观性。⇒ S4 的结果**只作敏感性分析**，**不得**用于推翻 S1 的判定方向；
> 若 S4 与 S1 结论方向冲突，须**两者并列披露**并标注为未决。

---

## 5. 预算与停止规则

### 5.1 预算（基于存量 token 实测，已披露见文首）

| 臂 | token/task（存量实测） | × 41 | 小计 |
|---|---|---|---|
| ① `p_df_parity__o_logic` | ≈ 15,253（aitester 口径） | 41 | ≈ **0.63M** |
| ③ `p_full__o_logic` | ≈ 15,253 | 41 | ≈ **0.63M** |
| ② `p_df_parity__o_mono` | ≈ 2,309（df 口径） | 41 | ≈ **0.09M** |
| REF `df_stored` | — | — | **0**（复用存量） |
| **合计** | | | **≈ 1.35M token** |

与 `REVIEW_2026_FRONTIER.md` EXP-1 的"≈1.4M token"估算一致。
**`--per-task-token-caps` 不设**（H1 是**载荷**实验，不是预算匹配实验；设 cap 会引入第二个自变量）。
**`AITESTER_LLM_CACHE=0`** ⇒ 该估算即实际上限。

### 5.2 停止规则（硬性）

1. **任一臂运行中出现 `budget_exceeded` 行 > 0** ⇒ **中止**该臂，登记并复核（不得静默继续）。
2. **单任务 token > 3× 存量 95 分位**（≈ 45k）⇒ 记录异常行，**不**剔除，纳入敏感性分析。
3. **三臂 `git_sha` 不一致** ⇒ 全部作废重跑。
4. **冒烟阶段 prompt token 未按预期下降** ⇒ 中止（§2.5）。

### 5.3 扩样规则（**只在 indeterminate 时触发，预先声明**）

- 触发条件：§3.2 判为 indeterminate **且** S3 的 `P(|δ| ≤ 5pp) < 0.90`。
- 允许动作：**仅**增加 seed（43、44），**不**更换数据集、**不**改阈值、**不**改臂定义。
- 扩样后判定：对 3 个 seed 的配对差做**随机效应 meta 分析**（seed 为随机效应），
  报告合并 δ 与预测区间；若仍 indeterminate ⇒ **登记为未决结论**，不得强行二值化。
- 扩样预算上限：**+2.7M token**（2 个 seed × ≈1.35M）；超出须重新预注册。

---

## 6. 工件与可复现性

### 6.1 落盘

- **独立目录**（不得与既有批次混放）：
  `experiments/results/e3_h1_payload/<arm>/`，每臂一个目录。
- 每臂产物：批次 JSON、逐任务 trace、运行日志、`env_snapshot.json`、
  本次运行的 `code_state.txt`（`git rev-parse HEAD` + `git status --short` 全文）。
- **`SHA256SUMS`**：每臂目录一份，覆盖该目录**全部**文件（含日志与 trace）；
  顶层 `（工件已清除）` 覆盖各臂 SHA256SUMS。
  校验：`shasum -a 256 -c SHA256SUMS`。
- **入库白名单**：三臂工件全部入 git 白名单目录；`/tmp` 产物**不构成证据**。

### 6.2 `env_snapshot` 校验（**运行器强制**）

`run_payload_ab.py` 在每臂跑完后：

1. 读取新产物的 `provenance.env_snapshot`；
2. 断言 `GENERATOR_PAYLOAD` == 该臂声明值；
3. 断言三臂的**其余所有键逐键相同**（`GENERATOR_PAYLOAD` 除外）；
4. 任一条不满足 ⇒ **非零退出 + 该臂工件标记不可用**。

> 该断言是 G0-b 的运行时兜底：即便 CI 门禁漏过，运行器仍会拒绝产出无 provenance 的臂。

### 6.3 复现命令

```bash
# 三臂（dry-run 先验证）
.venv/bin/python experiments/run_payload_ab.py --dry-run --out-dir experiments/results/e3_h1_payload
.venv/bin/python experiments/run_payload_ab.py --out-dir experiments/results/e3_h1_payload
```

---

## 7. 强制披露条款

> 参照 `docs/preregistration.md:124-153` 的 **E4 污染防控**（R4，2026-10-09 预注册增补，早于任何 E4 正式数据）。

1. **污染风险声明（须引用证据，报告章节原文标注 DOI/URL）**：
   ① Aleithan et al. 2024 —— 原始 SWE-bench 94% 实例早于主流 LLM 训练截止；
   ② Liang et al. 2025 —— SOTA LLM 仅凭 issue 描述猜中 buggy 文件路径达 76%；
   ③ Wang et al. 2025（PatchDiff）—— 至多 6.4pp 表观增益为"幻影"；
   ④ Yu et al. 2025（UTBoost）—— 测试增强与更严解析修正 24% 的 leaderboard 条目。
   **QuixBugs 为经典教学基准，处于主流 LLM 训练语料覆盖范围，污染风险不可假设为零。**
2. **模型训练截止 vs 实例时间**：记录所用模型（deepseek-flash 等）的公开训练截止日期，
   与 QuixBugs 实例引入时间对照，标注"潜在重叠"占比。
3. **差分测试复核（PatchDiff 式）**：对 H1 中 `detection=1` 的行**抽样**做
   "移除定位线索后重跑"的差分检验；若正结果显著下降，须标注污染成分区间。
4. **靶点错位声明**：若 H1 为负结果，须区分"载荷无关"与"靶点错位"
   （函数级单文件 vs 仓库级任务），**不得**静默归因任一方向。
5. **可复现性**：污染披露**不得**依赖手工判断——"模型截止日期 + 实例时间 + 差分重跑"
   三个客观字段入结果行或报告附录。
6. **硬约束**：**污染披露小节缺失 ⇒ H1 报告视为不完整，不得用于对外引用。**

> 预算影响：污染防控为**离线字段记录 + 抽样差分重跑**，仅在正结果行抽样（≈0.01M token 量级），
> 不改变 §5.1 的预算口径。

---

## 8. 偏离登记表（**取数后任何改动必须登记于此**）

| # | 日期 | 偏离内容 | 原因 | 对结论的影响 |
|---|---|---|---|---|
| — | — | **（预注册时点：无偏离）** | — | — |

> 纪律：**先声明后取数**。任何在数据产生后修改的阈值、臂定义、终点口径
> 都必须登记在本表，并在报告正文**并列披露**其"事后性"。
> 未登记的事后改动 ⇒ 该结论不得以 H1 名义对外引用。

---

## 附录 A：`df_parity` 逐字段剥离清单（落点 `src/agents/generator.py::_build_query` :394-480）

| # | payload 段 | 代码落点 | `full` | `df_parity` | `structure` |
|---|---|---|---|---|---|
| A1 | `plan_json` 整块（JSON 序列化） | `:408`（`json.dumps`）、`:411-416` | 注入 | **剥除** | 注入（骨架） |
| A1.1 | `└ function_name` | plan schema | 注入 | 剥除 | **保留** |
| A1.2 | `└ description` | plan schema | 注入 | 剥除 | **保留** |
| A1.3 | `└ logic_analysis.input_domain` | `planner.py:96-118` | 注入 | 剥除 | 保留 |
| A1.4 | `└ logic_analysis.output_domain` | `planner.py:96-118` | 注入 | 剥除 | **剥除**（oracle 锚点） |
| A1.5 | `└ logic_analysis.preconditions` | `planner.py:96-118` | 注入 | 剥除 | 保留 |
| A1.6 | `└ logic_analysis.postconditions` | `planner.py:96-118` | 注入 | 剥除 | **剥除**（oracle 锚点） |
| A1.7 | `└ logic_analysis.edge_cases` | `planner.py:118,165,224`（`logic_analysis` schema） | 注入 | 剥除 | 保留 |
| A1.8 | `└ test_cases[].case_name` | plan schema | 注入 | 剥除 | **保留** |
| A1.9 | `└ test_cases[].input_args` | plan schema | 注入 | 剥除 | **保留** |
| A1.10 | `└ test_cases[].category` | plan schema | 注入 | 剥除 | **保留** |
| A1.11 | `└ test_cases[].description` | plan schema | 注入 | 剥除 | **保留** |
| A1.12 | `└ test_cases[].logic_coverage` | `planner.py:257-265` | 注入 | 剥除 | **保留** |
| A1.13 | `└ test_cases[].expected_output` | `flags.py:263`、`generator.py:46-88` | 注入 | 剥除 | **剥除**（oracle 锚点） |
| A2 | `target_code` 块 | `:413` | 注入 | **保留** | 保留 |
| A3 | `module_name` + import 强约束 | `:414`, `:420-423` | 注入 | **保留** | 保留 |
| A4 | RAG 参考案例（`_MAX_RAG_REFERENCES` 上限内） | `:427-436` | 注入 | **剥除** | 保留 |
| A5 | 断言增强 / 现存 assert 注入 | `:439-449`（`ASSERTION_AUGMENT_ENABLE`） | 开关控 | **剥除** | 保留 |
| A6 | 变异反馈（存活变异体 + `mutation_score`） | `:455-478` | 注入 | **剥除** | 保留 |
| A7 | 分支覆盖段 | `nodes.py:709-713`（`BRANCH_COVERAGE_INJECT_ENABLE`） | 开关控 | **剥除**（经 `ORACLE_CONTEXT_TIER=minimal`） | 保留 |
| A8 | AST 边界三元组段 | `nodes.py:719-724` / `logic_spec.build_boundary_triplets_section` | 开关控 | **剥除**（同上） | 保留 |
| A9 | 蜕变 / 差分段 | `nodes.py:748,759`（`MR_*` / `DIFF_*`） | 开关控 | **剥除**（同上） | 保留 |
| A10 | 检出优先协议文本（强化段） | `nodes.py:511-517` / `_over_red_section`（`:530`） | 再生成轮注入 | **保留并前置到首轮** | 保留 |
| A11 | CFG 段 | `planner.py:187-193`（`CFG_ANALYSIS_ENABLE`，注入 **Planner** prompt） | 经 plan 间接 | **随 plan 剥除** | 随 plan 保留 |

> **`boundaries` 的处置**：见 §2.2 的口径订正——它不是 plan JSON 字段，
> 而是 A8 的独立注入段（`BOUNDARY_TRIPLETS_ENABLE`），在 `df_parity` 下随之剥除。

## 附录 B：臂 × env 矩阵（`run_payload_ab.py` 据此构造）

| env 键 | ① `p_df_parity__o_logic` | ② `p_df_parity__o_mono` | ③ `p_full__o_logic` |
|---|---|---|---|
| `GENERATOR_PAYLOAD` | **`df_parity`** | **`df_parity`** | **`full`** |
| `AITESTER_PROFILE` | `logic` | `logic` | `logic` |
| `baselines` | `aitester` | `plain_llm_df` | `aitester` |
| `TEMPERATURE` | `0.0` | `0.0` | `0.0` |
| `LLM_THINKING_MODE` | `disabled` | `disabled` | `disabled` |
| `AITESTER_LLM_CACHE` | `0` | `0` | `0` |
| `AITESTER_CACHE_NAMESPACE` | `e3_h1_seed42` | `e3_h1_seed42` | `e3_h1_seed42` |
| `MAX_ITERATIONS` | `3` | `3` | `3` |
| `EXECUTION_TIMEOUT` | `30` | `30` | `30` |
| `DETECTION_SPECIFICITY_GATE_ENABLE` | `true` | `true` | `true` |
| `RED_REGRESSION_GATE_ENABLE` | `true` | `true` | `true` |
| `DETECTION_FIRST_ENABLE` | `true` | `true` | `true` |
| `BENCHMARK_PARALLELISM` | `4` | `4` | `4` |
| `--seed` | `42` | `42` | `42` |
| `--task-count` | `50` | `50` | `50` |

> ② 的 `GENERATOR_PAYLOAD=df_parity` 在单体拓扑下**结构性冗余**（无 Planner ⇒ 无 plan 载荷）。
> 仍显式设置的原因：让 `env_snapshot` 忠实反映**声明的干预意图**，并作为
> §3.4 操纵检查的一部分。**不得**据此声称 ② 是对载荷因子的独立操纵。

## 附录 C：判据速查

| 判据 | 阈值 | 触发动作 |
|---|---|---|
| G0-a 围栏残留 | `details[].patch` 以 `python\n` 开头 | 阻断 H1 |
| G0-b/c 快照登记 | `GENERATOR_PAYLOAD`/`ORACLE_CONTEXT_TIER` 在 `_env_snapshot_keys` | 阻断 H1 |
| P0 冒烟 | ① 的 prompt token 未显著低于 ③ | 阻断 H1（干预未生效） |
| 主终点 | δ ≥ +20pp ∧ `p_BH < 0.05` | H1 成立 |
| ROPE | δ ≤ +5pp ∧ `P(\|δ\|≤5pp) ≥ 0.90` | H1 否证 |
| Assay sensitivity | ② − REF > 10pp | H1 降级为不可判定 |
| 停止 | 任一臂 `budget_exceeded > 0` | 中止并复核 |

## 附录 D：算法族划分（S4/S5 的聚类单位，**本预注册时点冻结**）

> 依据：**仅程序名语义**（未查看任何 H1 结果）。41 个有 gold 缺陷程序按 QuixBugs 主题归族：

| 族 | 程序 |
|---|---|
| F1 排序 | `bucketsort` `kheapsort` `mergesort` `quicksort` `hanoi` |
| F2 查找 | `find_in_sorted` `find_first_in_sorted` `kth` |
| F3 图/树 | `breadth_first_search` `depth_first_search` `detect_cycle` `minimum_spanning_tree` `shortest_path_length` `shortest_path_lengths` `shortest_paths` `topological_ordering` `reverse_linked_list` `node` |
| F4 动态规划 | `knapsack` `lcs_length` `levenshtein` `longest_common_subsequence` `max_sublist_sum` `possible_change` `lis` |
| F5 字符串 | `flatten` `is_valid_parenthesization` `next_palindrome` `pascal` `rpn_eval` `shunting_yard` `wrap` `to_base` |
| F6 数值/位 | `bitcount` `gcd` `get_factors` `sqrt` `subsequences` `powerset` `next_permutation` `sieve` |

> **`n_eff` 与族级符号检验据此计算**；族划分的主观性已在 §4 S4 的诚实边界中声明。
> 若实现时发现某程序不在 41 个有 gold 集合内（例如 `node` 实为辅助模块），
> **须在报告附录如实列出实际参与聚类的程序清单**，不得静默丢弃。
