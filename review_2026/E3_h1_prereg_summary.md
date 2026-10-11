# E3 · H1 载荷等价实验：预注册要点摘要 + dry-run 实录（P1-5）

> **任务**：task-7 必做 2。**产物**：
> 预注册全文 [docs/design/payload_equivalence_prereg.md](../docs/design/payload_equivalence_prereg.md)（≈500 行）、
> 运行器骨架 [experiments/run_payload_ab.py](../experiments/run_payload_ab.py)。
> **本文件只做摘要与证据留档**；判定规则以预注册全文为准。

> **未执行任何 LLM 实验**：本轮只做只读检查 + `--dry-run` + 校验器夹具测试。
> 无 `--confirm-budget` 时运行器**默认拒绝执行**（安全默认）。

---

## 1. 预注册关键设计抉择（10 条）

| # | 抉择 | 取值 | 理由 / 代价 |
|---|---|---|---|
| **D1** | **执行顺序**（用户指令，硬性） | **先修围栏残留（P0-2）→ 再跑 H1 → 再开逻辑通道（C3）** | 三臂必须同代码态；C3 埋点会改 `run_benchmark.py` 的 details 组装路径，若先改则 `git_sha` 不同，破坏单变量比较 |
| **D2** | **臂数** | **三臂 + 存量 REF**（不跑第 4 臂） | ①`df_parity`+logic、②`df_parity`+单体、③`full`+logic；REF = 存量 `plain_llm_df` 工件 |
| **D3** | **为何不是 2×2 全因子** | 单体拓扑**没有 Planner** ⇒ 载荷的 `full` 水平在该拓扑下**不可构造** | 预先登记为设计限制，**不得**在报告中当作事后发现的缺陷 |
| **D4** | **主对比** | **① − ③**（编排固定 logic，只动载荷） | H1 的唯一干净检验；② vs REF 作 **assay sensitivity** 操纵检查（阈值 **+10pp**，先声明） |
| **D5** | **判定阈值** | δ ≥ **+20pp** ∧ `p_BH<0.05` → 成立；δ ≤ **+5pp** ∧ `P(\|δ\|≤5pp)≥0.90` → 否证；**中间区显式登记为 indeterminate** | 预先声明**第三态**，防止把"不显著"强行读成"否证"或反之；阈值不得事后改 |
| **D6** | **`structure` 水平** | **默认不跑**（预算保护） | 仅在 indeterminate 且扩样后仍不明时才补跑；禁止 HARKing |
| **D7** | **检验力诚实披露** | 存量观测不一致率 **14/41 = 34.1%** ⇒ n=41 对 +20pp 的检验力**仅约 0.5–0.6**（临界） | 预先登记三点应对：单侧精确 McNemar + 贝叶斯 ROPE 并列主判 + indeterminate 区扩样（**只加 seed**） |
| **D8** | **聚类单位** | QuixBugs **无模板** ⇒ 用**算法族**（附录 D，41 程序分 6 族，**本预注册时点按程序名冻结**） | `n_eff` 与族级符号检验**只作敏感性分析**，**不得**推翻 S1 的判定方向；划分主观性已声明 |
| **D9** | **缺失指标的处置** | `spec_oracle_injected` 在 H1 阶段**不可得**（C3 未打开）⇒ 报告须**明确标注该指标缺失** | 不得留空装作已测；这是 G1 门存在的理由 |
| **D10** | **口径订正（不沿用任务书失实字段名）** | plan JSON 实际字段：`test_cases[].expected_output` ✅、`logic_analysis.edge_cases` ✅（**非** `test_cases[].edge_cases`）、**`boundaries` 不是 plan JSON 字段** | `boundaries` 实为 SpecIR v2 规约字段（`spec_ir_v2.py:456`）与 CFG `loop_boundaries`；在 Generator 侧是**独立注入段**（`BOUNDARY_TRIPLETS_ENABLE`）。附录 A 按**实际代码**列 20 项字段 |

### 1.1 `GENERATOR_PAYLOAD ∈ {full, df_parity, structure}` 操作化（摘要）

- **`full`** = 现状，**逐字节不变**（ADR-0003 默认关）。
- **`df_parity`** = 仅 `target_code` + `module_name`/import 约束 + **检出优先协议文本**；
  **剥除** 20 项（附录 A）：整个 `plan_json`（含 `expected_output` / `logic_analysis.edge_cases`）、
  RAG 参考、断言增强、变异反馈、分支覆盖段、AST 边界三元组段、蜕变/差分段。
  后四段**复用既有** `ORACLE_CONTEXT_TIER=minimal` 机制（`src/tools/logic_spec.py:67-82`），
  **不再造一套**（避免口径分叉）。
- **`structure`** = 保结构骨架，仅剥三个 **oracle-来自-实现锚点**：
  `test_cases[].expected_output`、`logic_analysis.output_domain`、`logic_analysis.postconditions`。

> **与 A1 消融的区别**（关键）：A1 只剥 `expected_output` **一个键**且实测零效应，
> 但 A1 有已知**结构性空转**（34/87 任务 `test_cases=[]` 无键可剥）。
> ⇒ "剥一键无效" **推不出** "剥整个载荷无效"——这正是 H1 要检验的。

---

## 2. 前置门：dry-run 实测 **4 项全红**（**这是本次最重要的运行结论**）

运行器在 `--dry-run` 下**只读**检查了预注册 §0 / 附录 C 的全部门禁。**当前仓库状态 4 项均未通过**：

| 门 | 状态 | 一手证据 |
|---|---|---|
| **G0-a** 围栏回灌（P0-2） | ⛔ | 参考批次 **50/50** 行 `details[].patch` 以 `python\n` 开头 |
| **G0-b** 快照登记 | ⛔ | `_env_snapshot_keys`（39 键）**缺** `GENERATOR_PAYLOAD`、`ORACLE_CONTEXT_TIER` |
| **G0-c** CI 门禁覆盖 | ⛔ | `check_env_snapshot_keys.py` 的 `DEFAULT_SELECT='_ENABLE$'` **不匹配**上述两键（且不在白名单） |
| **P-1** 干预落地 | ⛔ | `src/` 下**无** `GENERATOR_PAYLOAD` 消费者 ⇒ 现在跑三臂 = 三臂跑同一个 `full` 载荷 |

> **诚实判定**：**H1 现在不可执行**，且**不是**因为预算，而是因为**干预尚未落地**（P-1）
> 与**审计链未闭合**（G0-b/c）。若此刻强行跑，将重演 A1 首跑的
> "开关未生效却被当成零效应"**假阴性**。
> `--confirm-budget` 在门未过时**硬拒绝**（实测 exit code **3**，未执行任何命令）。

---

## 3. 运行器骨架验证（零 LLM）

| # | 验证项 | 命令 | 结果 |
|---|---|---|---|
| V1 | `ruff check` | `.venv/bin/python -m ruff check experiments/run_payload_ab.py` | ✅ All checks passed |
| V2 | `--dry-run` 打印命令 + env，**不执行** | `… --dry-run` | ✅ exit 0，103 行，无 subprocess |
| V3 | 安全默认：无 `--confirm-budget` ⇒ 不跑 | `… `（不带 flag） | ✅ exit 0，仅 dry-run |
| V4 | 门未过时 `--confirm-budget` **拒绝执行** | `… --confirm-budget` | ✅ **exit 3**，逐条打印未通过门 |
| V5 | `--arms` 校验 | `… --arms nope` | ✅ exit 2 |
| V6 | `env_snapshot` 校验器（夹具） | 见 §3.2 | ✅ 3 例全对 |

### 3.1 dry-run 实录（完整，sha256 `bf5faf14…`）

```text
==============================================================================
H1 载荷等价实验 —— DRY RUN（不会执行任何命令，不会调用任何 LLM）
==============================================================================
runner      : main_batch → experiments/run_main_batch.py
out-dir     : /Users/wangchenyu/Workspace/AITester/experiments/results/e3_h1_payload
dataset     : quixbugs  task-count=50  seed=42
三臂        : ['p_df_parity__o_logic', 'p_df_parity__o_mono', 'p_full__o_logic']
外部参照REF : df_stored = experiments/results/e6_a1_batches/e4_quixbugs_FIXED_harness/plain_llm_df.json（存量，不重跑）

------------------------------------------------------------------------------
前置门（预注册 §0 / 附录 C）
------------------------------------------------------------------------------
⛔ [G0-b] `_env_snapshot_keys` 缺 ['GENERATOR_PAYLOAD', 'ORACLE_CONTEXT_TIER']（当前共 39 键）——缺口未补则干预**不可从工件证明**（A1/D3/RT1 同类事故）
⛔ [G0-c] check_env_snapshot_keys.py 的 DEFAULT_SELECT='_ENABLE$' 不匹配 ['GENERATOR_PAYLOAD', 'ORACLE_CONTEXT_TIER'] 且不在白名单 ⇒ CI 门禁不覆盖载荷开关（须加白名单或扩正则）
⛔ [P-1] src/ 下**无** GENERATOR_PAYLOAD 消费者 ⇒ 载荷干预未落地，现在跑三臂等于跑同一个 full 载荷（A1 首跑同类假阴性）
⛔ [G0-a] 参考批次 50/50 行 patch 仍以 'python\n' 开头（围栏残留未回灌）

⛔ 4 项前置门未通过 —— 真跑前必须补齐（见预注册 §2.5 P-1 / §0 G0）。

------------------------------------------------------------------------------
臂 p_df_parity__o_logic   （H1 主检验臂（①））
------------------------------------------------------------------------------
  注入的环境变量（COMMON_ENV + 自变量）：
    GENERATOR_PAYLOAD='df_parity'
    AITESTER_PROFILE='logic'
    TEMPERATURE='0.0'
    LLM_THINKING_MODE='disabled'
    AITESTER_LLM_CACHE='0'
    AITESTER_CACHE_NAMESPACE='e3_h1_seed42'
    MAX_ITERATIONS='3'
    EXECUTION_TIMEOUT='30'
    DETECTION_SPECIFICITY_GATE_ENABLE='true'
    RED_REGRESSION_GATE_ENABLE='true'
    DETECTION_FIRST_ENABLE='true'
    BENCHMARK_PARALLELISM='4'
    ENABLE_RAG='false'

  命令：
    /Users/wangchenyu/Workspace/AITester/.venv/bin/python experiments/run_main_batch.py --dataset quixbugs --task-count 50 --seed 42 --baselines aitester --output-dir /Users/wangchenyu/Workspace/AITester/experiments/results/e3_h1_payload/p_df_parity__o_logic --skip-stats --allow-dirty --dirty-reason E3 H1 payload-equivalence arm=p_df_parity__o_logic
  等价的直接 runner 命令（--runner benchmark）：
    /Users/wangchenyu/Workspace/AITester/.venv/bin/python experiments/run_benchmark.py --dataset quixbugs --task-count 50 --seed 42 --baselines aitester --output-dir /Users/wangchenyu/Workspace/AITester/experiments/results/e3_h1_payload/p_df_parity__o_logic

------------------------------------------------------------------------------
臂 p_df_parity__o_mono   （同载荷编排对照（②））
------------------------------------------------------------------------------
  注入的环境变量（COMMON_ENV + 自变量）：
    GENERATOR_PAYLOAD='df_parity'
    AITESTER_PROFILE='logic'
    TEMPERATURE='0.0'
    LLM_THINKING_MODE='disabled'
    AITESTER_LLM_CACHE='0'
    AITESTER_CACHE_NAMESPACE='e3_h1_seed42'
    MAX_ITERATIONS='3'
    EXECUTION_TIMEOUT='30'
    DETECTION_SPECIFICITY_GATE_ENABLE='true'
    RED_REGRESSION_GATE_ENABLE='true'
    DETECTION_FIRST_ENABLE='true'
    BENCHMARK_PARALLELISM='4'
    ENABLE_RAG='false'

  命令：
    /Users/wangchenyu/Workspace/AITester/.venv/bin/python experiments/run_main_batch.py --dataset quixbugs --task-count 50 --seed 42 --baselines plain_llm_df --output-dir /Users/wangchenyu/Workspace/AITester/experiments/results/e3_h1_payload/p_df_parity__o_mono --skip-stats --allow-dirty --dirty-reason E3 H1 payload-equivalence arm=p_df_parity__o_mono
  等价的直接 runner 命令（--runner benchmark）：
    /Users/wangchenyu/Workspace/AITester/.venv/bin/python experiments/run_benchmark.py --dataset quixbugs --task-count 50 --seed 42 --baselines plain_llm_df --output-dir /Users/wangchenyu/Workspace/AITester/experiments/results/e3_h1_payload/p_df_parity__o_mono

------------------------------------------------------------------------------
臂 p_full__o_logic   （H1 对照臂（③））
------------------------------------------------------------------------------
  注入的环境变量（COMMON_ENV + 自变量）：
    GENERATOR_PAYLOAD='full'
    AITESTER_PROFILE='logic'
    TEMPERATURE='0.0'
    LLM_THINKING_MODE='disabled'
    AITESTER_LLM_CACHE='0'
    AITESTER_CACHE_NAMESPACE='e3_h1_seed42'
    MAX_ITERATIONS='3'
    EXECUTION_TIMEOUT='30'
    DETECTION_SPECIFICITY_GATE_ENABLE='true'
    RED_REGRESSION_GATE_ENABLE='true'
    DETECTION_FIRST_ENABLE='true'
    BENCHMARK_PARALLELISM='4'
    ENABLE_RAG='false'

  命令：
    /Users/wangchenyu/Workspace/AITester/.venv/bin/python experiments/run_main_batch.py --dataset quixbugs --task-count 50 --seed 42 --baselines aitester --output-dir /Users/wangchenyu/Workspace/AITester/experiments/results/e3_h1_payload/p_full__o_logic --skip-stats --allow-dirty --dirty-reason E3 H1 payload-equivalence arm=p_full__o_logic
  等价的直接 runner 命令（--runner benchmark）：
    /Users/wangchenyu/Workspace/AITester/.venv/bin/python experiments/run_benchmark.py --dataset quixbugs --task-count 50 --seed 42 --baselines aitester --output-dir /Users/wangchenyu/Workspace/AITester/experiments/results/e3_h1_payload/p_full__o_logic

------------------------------------------------------------------------------
单变量纪律自检（预注册 §2.3）
------------------------------------------------------------------------------
  p_df_parity__o_logic vs p_df_parity__o_mono: 允许差异=[] 违规差异=无
  p_df_parity__o_logic vs p_full__o_logic: 允许差异=['GENERATOR_PAYLOAD'] 违规差异=无

------------------------------------------------------------------------------
落盘与校验计划
------------------------------------------------------------------------------
  1) 每臂输出 → /Users/wangchenyu/Workspace/AITester/experiments/results/e3_h1_payload/<arm>/
  2) 逐臂核 provenance.env_snapshot['GENERATOR_PAYLOAD'] == 该臂声明值
  3) 跨臂逐键 diff（除 GENERATOR_PAYLOAD 外必须完全相同）
  4) 生成 /Users/wangchenyu/Workspace/AITester/experiments/results/e3_h1_payload/SHA256SUMS（递归覆盖全部工件）

提示：未传 --confirm-budget ⇒ 只做 dry-run，未执行任何实验（安全默认）。
```

### 3.2 `env_snapshot` 校验器夹具测试（`/tmp` 合成工件，非 LLM）

预注册 §6.2 的三条断言已用合成批次 JSON 逐条验证（夹具已删除）：

| 夹具 | 注入的缺陷 | 期望 | 实测 |
|---|---|---|---|
| A 干净 | 三臂 payload 正确、其余键一致 | exit 0 | ✅ 三臂全 ✅ |
| B 值错 | ② 声明 `df_parity` 实为 `full` | exit 1 | ✅ 报 `GENERATOR_PAYLOAD='full' ≠ 声明值 'df_parity'` |
| C 缺键 | ② 的 `TEMPERATURE` 整键缺失 | exit 1 | ✅ 报 `跨臂键集合不一致：TEMPERATURE 出现于 [...]` |

> 夹具测试**暴露并修复了一个真实缺陷**：初版校验器只做跨臂 `common` 键取值 diff，
> **既不校验"该臂 payload == 声明值"，也漏掉"某臂整键缺失"**（缺失键不在交集内 → 静默跳过）。
> 已改为"逐臂声明值断言 + 跨臂键集合断言 + 逐键取值断言"三重。

---

## 4. 预算（按预注册 §5.1，基于存量 token 实测）

| 臂 | token/task | ×41 | 小计 |
|---|---|---|---|
| ① `p_df_parity__o_logic` | ≈15,253 | 41 | ≈0.63M |
| ③ `p_full__o_logic` | ≈15,253 | 41 | ≈0.63M |
| ② `p_df_parity__o_mono` | ≈2,309 | 41 | ≈0.09M |
| REF `df_stored` | — | — | 0（存量） |
| **合计** | | | **≈1.35M token** |

与 `REVIEW_2026_FRONTIER.md` EXP-1 的"≈1.4M"一致。
**`--per-task-token-caps` 不设**（H1 是载荷实验，设 cap 会引入第二个自变量）。

---

## 5. 交接清单（谁需要做什么，才能让 H1 可执行）

| 门 | 需要改动 | 归属 |
|---|---|---|
| **G0-a** | 写盘链路接入 `normalize_patch_text`，使 `details[].patch` 不再以 `python\n` 开头 | P0-2 负责方 |
| **P-1** | `src/agents/generator.py::_build_query`（`:394-480`）新增 `GENERATOR_PAYLOAD` 分派（附录 A 的 20 项） | 干预实现方 |
| **G0-b** | `experiments/run_benchmark.py:2712-2771` 的 `_env_snapshot_keys` 增补两键 | 快照清单负责方 |
| **G0-c** | `scripts/gates/check_env_snapshot_keys.py` 白名单或 `--select` 扩正则覆盖非 `_ENABLE$` 键 | 门禁负责方 |
| **G1** | C3 埋点（`spec_oracle_injected` / `spec_oracle_verdict` 透出）—— **排在 H1 之后** | 见 [E3_four_channel.md](E3_four_channel.md) §4.2 |

> 上述任一未完成 ⇒ `run_payload_ab.py --confirm-budget` **仍会拒绝执行**（exit 3）。
> 这是设计意图：**把"科学前提未满足"从人肉纪律变成机器门禁。**
