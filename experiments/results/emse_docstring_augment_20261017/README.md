# M-4 规格增广二臂正式批（df 对照 + augment 处理，真 LLM，2026-10-17）

> **性质**：预注册正式批执行工件（EMSE Registered Reports 口径）。
> **预注册**（结果产出前随切点提交）：`/Users/wangchenyu/Workspace/AITester-m-batch-fae8f45/docs/emse/EMSE_DOCSTRING_AUGMENT_PREREG_2026-10-17.md`
> sha256=`df2d3b9bc62bf9bb1e6e39d21e62b38d7bdd0f97dd24944dd11d1fd6e847e3ed`。
> **跑批切点（干净 worktree）**：`/Users/wangchenyu/Workspace/AITester-m-batch-fae8f45`，HEAD=`fae8f45844e986895b909cd59af60c1248b61343`，
> 跑前/跑后 `git status --porcelain` 0 行（每臂 log 头/尾记录）；两臂批次 provenance `git_dirty=false`。
> **判定与全部数字由脚本从批次 JSON / 分析报告 / 重放报告直出**（`run_augment_batch.sh`），本 README 不手写结果数字。
> 臂：df 对照 `plain_llm_df`（同批同日新跑） / aug 处理 `plain_llm_df_doc_augment`（代码保留 + 人类 docstring 规格并列增广）。
> 数据集：QuixBugs 50 行（41 缺陷程序 + 9 测试驱动；主分析集=41 口径）；模型：deepseek-flash。

## 1. 跑批协议（二臂并发、同批同日、逐臂独立 cache namespace）

| 项 | df（对照） | aug（处理） |
|---|---|---|
| baseline | `plain_llm_df` | `plain_llm_df_doc_augment` |
| cache namespace | `emse_docstring_augment_20261017_df` | `emse_docstring_augment_20261017_aug` |
| 批次工件 | `benchmark_quixbugs_20261017_221948.json` | `benchmark_quixbugs_20261017_221735.json` |
| 时间窗（UTC，start→end） | `2026-10-17T13:10:25Z` → `2026-10-17T14:20:00Z` | `2026-10-17T13:10:25Z` → `2026-10-17T14:20:00Z` |
| 墙钟 | **4175s** | **4175s** |
| parallelism | 4 | 4 |
| provenance git_sha / dirty | `fae8f45844e986895b909cd59af60c1248b61343` / **False** | `fae8f45844e986895b909cd59af60c1248b61343` / **False** |

共同协议（每臂实际命令，逐字见 `RUN_MANIFEST` 的 `arm_command_lines`）：

```bash
# 两臂各一条命令（并发执行；互异 namespace/log）
# df:  env -u DOC_ANCHOR_TABLE -u AITESTER_LLM_CACHE -u AITESTER_QUIXBUGS_DATA -u LLM_REASONING_EFFORT -u LLM_MAX_OUTPUT_TOKENS -u AITESTER_SMOKE_LLM AITESTER_PROFILE=logic TEMPERATURE=0.0 LLM_THINKING_MODE=disabled BENCHMARK_PARALLELISM=4 AITESTER_BATCH_MAX_CALLS=300 COST_BUDGET_ENABLE=true COST_BUDGET_USD=5 AITESTER_TRACE_DIR=/Users/wangchenyu/Workspace/AITester-m-batch-fae8f45/experiments/results/emse_docstring_augment_20261017/traces AITESTER_CACHE_NAMESPACE=emse_docstring_augment_20261017_df /User
# aug: env -u DOC_ANCHOR_TABLE -u AITESTER_LLM_CACHE -u AITESTER_QUIXBUGS_DATA -u LLM_REASONING_EFFORT -u LLM_MAX_OUTPUT_TOKENS -u AITESTER_SMOKE_LLM AITESTER_PROFILE=logic TEMPERATURE=0.0 LLM_THINKING_MODE=disabled BENCHMARK_PARALLELISM=4 AITESTER_BATCH_MAX_CALLS=300 COST_BUDGET_ENABLE=true COST_BUDGET_USD=5 AITESTER_TRACE_DIR=/Users/wangchenyu/Workspace/AITester-m-batch-fae8f45/experiments/results/emse_docstring_augment_20261017/traces AITESTER_CACHE_NAMESPACE=emse_docstring_augment_20261017_aug /Use
```

**调度偏差披露（M-4 任务书要求二臂并发；务必与单臂口径分开阅读）**：

- ① **df 与 aug 两臂并发执行**（两个独立进程，各 P4、互异 cache namespace/log、同批同日启动）。
  单臂内部协议不变（temp=0.0 / logic / seed=42 / 判分口径 / 全量 50 行）。
- ② 并发带来的 CPU 争抢发生在**任务阶段与批后处理阶段的重叠窗口**；主指标 detection 在任务阶段采集，
  但次指标（mutation_score / MDO 等变异类测量）的时间窗含并发噪声，方向不系统性偏向任一臂。
- ③ 两臂均未中断、未重跑、未删除任何日志/工件；`--task-count 50` = QuixBugs 全量（L 轮修复后对真实数据集等价 `--task-limit`）。
- ④ 后处理阶段（变异得分/变异检出/MDO 逐任务串行 loop）耗时占比高，属既有管线口径；超时防御有界终止不挂死。

**每臂 env 级预算上限（不进入 env_snapshot 的开关由 RUN_MANIFEST 记录）**：`AITESTER_BATCH_MAX_CALLS=300`、`COST_BUDGET_ENABLE=true`、`COST_BUDGET_USD=5`。

> 预算 cap 口径披露：采用 M-4 派单值 `COST_BUDGET_USD=5`（预注册 §6 命令示例写 `3`；两者均远高于单任务实测成本，
> 不改变 detection 测量口径与判定，差异在此如实披露）。

## 2. 前置闸（preflight）与锚表

`python scripts/tools/run_preflight.py --expect-tasks 50 --parallelism 4`（worktree 内；输出见 `preflight.log`）。关键行：

```text
工作树：sha=fae8f45844e986895b909cd59af60c1248b61343  dirty=False
计划任务数=50  并行度=4  估算请求量上界=323
任务级预算：enabled=False tokens=None usd=None
批次级上限：AITESTER_BATCH_MAX_CALLS=None
近期批次指纹（近 5 个）：pinned=true 的有 0 个
孤儿进程巡检：扫描 735 个进程，泄漏的嵌套测试子进程 0 个
阻断/告警项：
  ✗ 任务级预算未启用（COST_BUDGET_ENABLE=false）——单任务失控无硬闸；启用：COST_BUDGET_ENABLE=true + COST_BUDGET_TOKENS=<上限>
```

锚表（预注册材料随切点提交；augment 臂使用 run_benchmark 默认路径，**不设 DOC_ANCHOR_TABLE**）：

| 文件 | sha256 |
|---|---|
| `DOCSTRING_ANCHOR_TABLE.json` | `2a650afdb181cc7035745d9f6c50b105317e5e1a5268fc309b24c52f3734272d` |

> 告警处理：preflight 无 strict（与 L 轮口径一致）；「任务级预算未启用」「批次级调用上限未配置」两项告警已用每臂 env cap（见 §1）显式覆盖；worktree 无历史批次指纹 → 本批工件自身指纹 `pinned=true`（见 §6）。

## 3. 结果（`DF_AUG_REPORT.json` / `.md` 直出）

### 3.1 检出（主分析集=41 缺陷程序；可判定子集口径，None 不进分母）

| 臂 | 可判定/41 行 | 检出 | detection | 41 口径 None | 全 50 行 None |
|---|---|---|---|---|---|
| `df` | 36/41 | 29 | **80.56%** | 5 | 14 |
| `augment` | 35/41 | 29 | **82.86%** | 6 | 15 |

### 3.2 配对对比（精确 McNemar；a=处理臂 vs b=df 对照）

| 对比 | 配对 n | a 独有 : b 独有 | δ | 单向 p | 双向 p | BF10 | MDE(80%) |
|---|---|---|---|---|---|---|---|
| `augment_vs_df` | 35 | 4:3 | **+2.86pp** | 0.5 | 1.0 | 0.3125 | 16.57pp |

### 3.3 预注册判定（direct-from-report）

**verdict = `not_confirmed`；fail_line_triggered = `False`**

| 判据 | 值 |
|---|---|
| absolute_line | threshold=0.88，rate=0.8286，met=False |
| one_sided_p_lt_0.05 | False |
| direction_positive | True |
| non_inferiority.margin_pp | -5.0 |
| non_inferiority.delta_pp | 2.86 |
| non_inferiority.met | True |
| non_inferiority.role | independent_marker |
| non_inferiority.note | 非劣标记独立于三态判定，不改变 verdict；用于保留'代码保留假设'方向证据 |

预注册常量（分析脚本锁定）：`success_line=0.88`，`fail_line=0.78`，`confirm_p=0.05`，`trend_p=0.1`，`non_inferiority_margin_pp=-5.0`，`mde_reference_n=35`，`primary_contrast=augment_vs_df`

MDE 披露：observed n_pairs=35，observed MDE(80%)=16.57pp；reference n=35 时 16.57pp。小效应不可判（预注册已披露）。

> 完整判定证据（三态条件、失败线、非劣标记、MDE 披露）以 `DF_AUG_REPORT.json` 为准。

## 4. 审计面（机制/仪器侧，描述性）

| 项（41 缺陷程序口径） | df | aug |
|---|---|---|
| `spec_augment_applied`（全 50 行） | `{}` | `{"attempted_augmented": 40, "attempted_fallback": 10}` |
| `spec_augment_applied`（41 口径） | `{}` | `{"attempted_augmented": 40, "attempted_fallback": 1}` |
| `spec_replace_applied`（全 50 行；非该臂应全 None） | `{}` | `{}` |
| specificity verdict（41 口径） | `{"over_red": 8, "specific_red": 31, "unavailable": 2}` | `{"over_red": 7, "specific_red": 31, "unavailable": 3}` |
| over_red 占比（over/(spec+over)，41 口径） | 20.51% | 18.42% |

> 预期（预注册 §4/§6）：aug 臂 `attempted_augmented` = 40/41 缺陷程序（`node.py` human_spec 为空串 →
> `attempted_fallback`），9 个测试驱动任务无锚条目同样回落 → 全 50 行 `attempted_fallback` = 10；
> df 对照臂该字段应全 None。
> over_red 为既有 proxy，**不作机制证明**；严格版机制度量见 §8。

## 5. 成本（真实 token 记账 × deepseek-flash 标准价目表，保守上界）

| 臂 | input tok | output tok | total tok | LLM calls | cache hits | cache-avoided tok | 墙钟(s) | **成本（USD）** |
|---|---|---|---|---|---|---|---|---|
| `df` | 34,232 | 53,380 | 87,612 | 54 | 7 | 11,675 | 4175 | **$0.0743** |
| `aug` | 48,561 | 58,281 | 106,842 | 54 | 7 | 14,974 | 4175 | **$0.0845** |
| **合计** | | | | | | | **4489** | **≈$0.1588** |

- 价目表：`experiments/price_table.json`（deepseek-flash：$0.3/M in、$1.2/M out，as_of 2026-10-06，标准/峰时价 → **上界**）。
- 两臂均为全新 cache namespace：批内 cache hits 为同批同 prompt 命中（不影响独立样本主张）；跨臂/跨批无共享响应。

## 6. provenance / 完整性

| 项 | 值（两臂一致项；cache namespace 按臂单列） |
|---|---|
| `git_sha` | `fae8f45844e986895b909cd59af60c1248b61343` |
| `git_dirty` / `dirty_reason` | **False** / None |
| `model_name` / fingerprint | deepseek-flash / **pinned=True**、returned_model=deepseek-flash、missing=[] |
| `temperature` / `profile` / `seed` | 0.0 / logic / 42 |
| `cache_enabled` / `cache_namespace` | True / df: `emse_docstring_augment_20261017_df`；aug: `emse_docstring_augment_20261017_aug` |
| `env_snapshot` | 111 键；含 `AITESTER_CACHE_NAMESPACE`、`AITESTER_PROFILE`、`TEMPERATURE`、`LLM_THINKING_MODE` 等 |
| 顶层 `total_tasks` / `parallelism` | 50 / 4 |

- 跑前/跑后 worktree `git status --porcelain` 均 0 行（每臂 log 头/尾记录；结果目录在 gitignore 内不产生变更）。
  注：每臂 log 原始尾部 `GIT_STATUS_AFTER=<not-collected>` 系 runner 展示缺陷（空值被 `${VAR:-默认串}` 误判为未采集），
  跑后实测为 0 行（`RUN_MANIFEST.repo.git_dirty_after=false`、两臂 `provenance.git_dirty=false`、跑后 HEAD 未变）；
  原日志行未修改，已另以 `POST-RUN AUDIT ADDENDUM` 追加注记（runner 展示缺陷已修复，不影响本批任何数字/判定）。
- 输入工件 sha256 已写入 `DF_AUG_REPORT.json.inputs` 与本目录 `SHA256SUMS`。

**工件 sha256（本批关键文件；完整清单见 `SHA256SUMS`）**：

| 文件 | sha256 |
|---|---|
| `benchmark_quixbugs_20261017_221735.json` | `b6303604bfb640ec20083b7384525e255461ba0f52e91a7439281f6d58128be7` |
| `benchmark_quixbugs_20261017_221948.json` | `80f8a54f097b65b53b57621ffbb5826fdb7784c436752e1304fc328919a09c2b` |
| `DF_AUG_REPORT.json` | `b399bdaa38c454a82db227f9ed34f16f242300e2dbea5ffe1eabf1eb6d049467` |
| `DF_AUG_REPORT.md` | `eaed2163fee455a28bdd0591ed23e06cf1668b4b9e4ba165829904021ef1cd1e` |
| `PROMPT_EVIDENCE.json` | `0967cd474605ce5e8e0b377a443938ee7d6179b22aa218def2bb198b166087fc` |

## 7. Prompt 增广核验（一等证据：代码块 + 规格锚同时在场）

数据来源：`~/.cache/aitester/llm/*.json` 中批次时间窗内的 generator 调用缓存（本次两臂均为全新 namespace →
缓存条目全部来自本批）。

**判据澄清（重要）**：QuixBugs 的人类规格文本就是缺陷源码文件尾部的模块级 docstring，因此
「规格文本出现」**不能**单独证明增广注入（df 对照臂代码块内也含该文本）。本证据以 **M-1 augment
framing 段**为决定性判据：代码标记（锚表 `source_head`）< augment framing 标记 < 规格锚末次出现，
并记录规格锚文本出现次数（源码内嵌一次 vs 增广段重复注入）；同 generator 条目含代码但无 framing 段 =
df 对照臂（负向对照）。

| 计数（时间窗内） | 值 |
|---|---|
| generator 缓存条目 | 108 |
| augment framing 命中（aug 臂） | **43** |
| 含代码块但无 framing 段（df 对照） | 42 |
| 负向对照在场 | True |
| 证据状态 | **ok** |

**例 1：`minimum_spanning_tree`**（缓存 `099e0d7fcfc6436d.json`，sha256 `09f41270ad0e8c27…`；prompt_len=2223；代码 offset=29 < framing offset=1027 < 规格锚末次出现=1588；规格锚出现 2 次；增广小节标题在场=True）

```text
): 10,
    ...     (1, 4): 10
    ... })
    {(1, 2), (3, 4), (1, 4)}
"""

```

【规格增广模式（Spec-Augment）：规格锚与目标代码并列】
上方已完整给出目标代码；以下并列追加同一函数的人类独立规格锚（独立于缺陷实现书写）。
请结合两者：当实现与规格不一致时，按规格构造期望值（这是检出缺陷的关键）。
不得仅凭当前实现的实际行为推断期望值——那会把缺陷固化成预期（oracle-from-implementation），系统性抹掉检出。

函数签名：def minimum_spanning_tree(weight_by_edge)
被测模块名：minimum_spanning_tree（import 必须 `from minimum_spanning_tree import ...`）

【独立于实现的规格锚（人类 docstring）】
Minimum Spanning Tree


Kruskal's algorithm implementation.

Input:
    weight_by_edge: A dict of the form {(u, v): weight} for every undirected graph edge {u, v}

Precondition:
    The input graph is connected

Output:
    A set of edges that connects all the vertices of the input graph and has the least possible total weight.

Example:
    >>> minimum_spanning_tree({
    ...     (1, 2): 10,
    ...     (2, 3): 15,
    ...     (3, 4): 10,
    ...     (1, 4): 10
    ... })
    {(1, 2), (3, 4), (1, 4)}

【生成纪律（增广模式）】
1. 人类规格 / docstring 明确覆盖的行为，必须按规格断言——不得以当前实现的实际行为作为期望值；
2. 规格与实现不一致处即为嫌疑缺陷：按规格推导正确结果并断言（这是检出缺陷的关键）；
3. 输入构造必须满足前置条件（不满足前件的输入应走 pytest.raises 路径或排除）；
4. 可以阅读上方目标代码理解调用方式，但不得访问规约与签名之外的属性 / 符号。

被测模块名：minimum_spanning_tree

请根据以上计划生成完整的 pytest 测
```

**例 2：`subsequences`**（缓存 `2862c16a50ed6835.json`，sha256 `bdbae64c7ef009c6…`；prompt_len=1385；代码 offset=28 < framing offset=511 < 规格锚末次出现=899；规格锚出现 2 次；增广小节标题在场=True）

```text
ces(a=1, b=5, k=3)
    [[1, 2, 3], [1, 2, 4], [1, 3, 4], [2, 3, 4]]
"""



```

【规格增广模式（Spec-Augment）：规格锚与目标代码并列】
上方已完整给出目标代码；以下并列追加同一函数的人类独立规格锚（独立于缺陷实现书写）。
请结合两者：当实现与规格不一致时，按规格构造期望值（这是检出缺陷的关键）。
不得仅凭当前实现的实际行为推断期望值——那会把缺陷固化成预期（oracle-from-implementation），系统性抹掉检出。

函数签名：def subsequences(a, b, k)
被测模块名：subsequences（import 必须 `from subsequences import ...`）

【独立于实现的规格锚（人类 docstring）】
Subsequences


Input:
    a: An int
    b: An int
    k: A positive int

Output:
    A list of all length-k ascending sequences of ints in range(a, b)

Example:
    >>> subsequences(a=1, b=5, k=3)
    [[1, 2, 3], [1, 2, 4], [1, 3, 4], [2, 3, 4]]

【生成纪律（增广模式）】
1. 人类规格 / docstring 明确覆盖的行为，必须按规格断言——不得以当前实现的实际行为作为期望值；
2. 规格与实现不一致处即为嫌疑缺陷：按规格推导正确结果并断言（这是检出缺陷的关键）；
3. 输入构造必须满足前置条件（不满足前件的输入应走 pytest.raises 路径或排除）；
4. 可以阅读上方目标代码理解调用方式，但不得访问规约与签名之外的属性 / 符号。

被测模块名：subsequences

请根据以上计划生成完整的 pytest 测试代码。

【重要约束】import 语句必须使用以下模块名：`subsequences`，即 `from subsequences import ...`
```

> 节选展示 augment framing 段与人类规格锚段落；完整证据与 1–5 条 aug 臂记录见 `PROMPT_EVIDENCE.json`。

## 8. 机制重放（misguided/effective 逐测试，零 LLM）

产物目录：`/Users/wangchenyu/Workspace/AITester-m-batch-fae8f45/experiments/results/emse_misguided_augment_20261017/MISGUIDED_REPORT.json` / `.md`（工具：`experiments/misguided_metrics.py`；**不参与主判定**）。

| 臂 | 可分析任务 | 可分类测试 | effective | misguided | both_pass | both_fail | effective 占比 | misguided 占比 |
|---|---|---|---|---|---|---|---|---|
| `plain_llm_df` | 39/50 | 849 | 400 | 11 | 424 | 14 | 47.11% | 1.30% |
| `plain_llm_df_doc_augment` | 39/50 | 970 | 543 | 3 | 413 | 11 | 55.98% | 0.31% |

> misguided/effective 为机制侧描述性信号（ISSTA'26 口径），与 detection 分开报告，不得互相顶替；
> 分母/不可分类原因（timeout、collect_error 等）见 `MISGUIDED_REPORT.json`。

## 9. 异常与限制（如实披露）

1. **调度偏差（并发）**：二臂并发（M-4 任务书要求，Lead 批准）——主指标 detection 在任务阶段采集，
   但次指标（变异类测量）时间窗含 CPU 争抢噪声；方向不系统性偏向任一臂。
2. **QuixBugs 已知「缺陷实现不终止」家族**（bitcount/find_first_in_sorted/sqrt/wrap 等）会令 M1 口径
   detection=None；None 按 fail-closed **不进入分母**（与预注册口径一致），分母已在 §3.1 如实披露。
3. **后处理耗时占比高**：变异得分/变异检出/MDO 逐任务串行 loop 占墙钟大头，超时防御有界终止；
   不影响任务阶段采集的 detection 主指标，但会抬高墙钟与部分次指标 None 率。
4. **单模型/单数据集/单 seed**：deepseek-flash + QuixBugs（41 缺陷程序可判定子集）+ seed=42；
   跨模型/跨数据集不可外推；小效应不可判（MDE≈16.6pp，见 §3.2）。
5. **cache 开启但 namespace 独立**：两臂为全新 namespace，无跨批/跨臂响应复用；批内同一 prompt
   可能命中（如重采样），cache hits 已在 §5 单列。
6. **审计字段口径**：`AITESTER_BATCH_MAX_CALLS`/`COST_BUDGET_*` 不在批次 `env_snapshot` 键集内，
   由 `RUN_MANIFEST.protocol.env_caps` + 每臂命令日志记录（可审计）。
7. **prompt 证据来自 LLM 缓存**（非 trace）：缓存条目含 prompt/system 全文、不含密钥；若证据状态非 ok 见 §7 说明。
8. 跑批过程**未中断、未重跑、未删除/手改任何日志与工件**；无 API key 泄露（日志脱敏机制在岗）。

## 10. 复现与判定命令（零 LLM 复算）

```bash
# 一键入口（本批实际执行；需干净 worktree + M-1 切点）
# bash experiments/run_augment_batch.sh --worktree <clean-worktree> --expect-sha <sha>

# 判定（零 LLM；本批实际命令，参数为两臂批次 JSON）
python -m experiments.emse_docstring_augment_analysis \
  --df /Users/wangchenyu/Workspace/AITester-m-batch-fae8f45/experiments/results/emse_docstring_augment_20261017/benchmark_quixbugs_20261017_221948.json \
  --augment /Users/wangchenyu/Workspace/AITester-m-batch-fae8f45/experiments/results/emse_docstring_augment_20261017/benchmark_quixbugs_20261017_221735.json \
  --out experiments/results/emse_docstring_augment_20261017/DF_AUG_REPORT.json \
  --markdown experiments/results/emse_docstring_augment_20261017/DF_AUG_REPORT.md

# 机制重放（零 LLM）
python -m experiments.misguided_metrics \
  --artifact /Users/wangchenyu/Workspace/AITester-m-batch-fae8f45/experiments/results/emse_docstring_augment_20261017/benchmark_quixbugs_20261017_221948.json \
  --artifact /Users/wangchenyu/Workspace/AITester-m-batch-fae8f45/experiments/results/emse_docstring_augment_20261017/benchmark_quixbugs_20261017_221735.json \
  --out experiments/results/emse_misguided_augment_20261017 --jobs 8

# 完整性
cd experiments/results/emse_docstring_augment_20261017 && shasum -a 256 -c SHA256SUMS
```

## 11. 文件与运行清单

| 文件 | 说明 |
|---|---|
| `run_augment_batch.sh` | 本次运行的跑批脚本副本（自归档；sha256 见 `SHA256SUMS`/`RUN_MANIFEST`） |
| `RUN_MANIFEST_20261017T131022Z.json` | 运行总清单（命令/env/工件/成本/token/墙钟/审计） |
| `preflight.log` | 前置闸输出 |
| `proc_hygiene.log` | 跑批期每 5min 只读孤儿巡检记录 |
| `log_df.log` / `log_aug.log` | 每臂完整日志（命令/env 白名单/GIT 前后状态） |
| `arm_df.meta.json` / `arm_aug.meta.json` | 每臂结构化元数据（provenance/token/成本/判分/审计/逐任务） |
| `DF_AUG_REPORT.json` / `.md` | 预注册判定（M-1 分析脚本直出） |
| `PROMPT_EVIDENCE.json` / `.md` | prompt 增广核验证据（缓存抽取） |
| `analysis_stdout.log` / `misguided_stdout.log` | 分析/重放完整输出 |
| `traces/` | 逐任务 trace（审计用） |
| `SHA256SUMS` | 本目录全部工件 sha256（`shasum -a 256 -c` 验证） |

> 交接：本批两份批次 JSON 即 M-1 机制指标的输入（路径/sha256 见 §6/`DF_AUG_REPORT.json.inputs`）；
> 重放报告在 `experiments/results/emse_misguided_augment_20261017/`。

