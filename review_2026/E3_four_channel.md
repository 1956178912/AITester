# E3 · 四通道检出协议：零 LLM 存量重算（P1-7）

> **任务**：task-7 必做 1。**方法**：只读既有入库工件，零 LLM、零 subprocess、零网络重算。
> **重算脚本**：[experiments/four_channel_recompute.py](../experiments/four_channel_recompute.py)
> **机器可读结果**：[review_2026/E3_four_channel.json](E3_four_channel.json)
> **数据源**：[e4_quixbugs_FIXED_harness/aitester.json](../experiments/results/e6_a1_batches/e4_quixbugs_FIXED_harness/aitester.json)
> （sha256 `2cbf4009…`）、[.../aitester.log](../experiments/results/e6_a1_batches/e4_quixbugs_FIXED_harness/aitester.log)（`b587a374…`）、
> [.../plain_llm_df.json](../experiments/results/e6_a1_batches/e4_quixbugs_FIXED_harness/plain_llm_df.json)（`d23402fb…`）、
> [.../plain_llm_df.log](../experiments/results/e6_a1_batches/e4_quixbugs_FIXED_harness/plain_llm_df.log)（`8a34acbd…`）。
> 四个文件均在 [e6_a1_batches/SHA256SUMS](../experiments/results/e6_a1_batches/SHA256SUMS) 覆盖内（已核）。

> **引用行号的基准代码态**（`git hash-object`，工作树内容）：`src/graph/nodes.py` `8adb660a`、
> `src/graph/state.py` `d50c2406`、`src/agents/generator.py` `3dcce87e`、`src/agents/planner.py` `8af37376`、
> `src/tools/logic_spec.py` `273f115a`、`src/tools/detection_gates.py` `14915626`、
> `experiments/run_benchmark.py` `9c9ca407`、`experiments/_m1_metrics.py` `27861829`。
> **注意**：本任务执行期间有其它成员在改 `src/`，`nodes.py` 的行号已实测发生漂移
> （`spec_oracle_injected` 写入点 865 → **967**）。**以 blob sha 为准复核后再引用。**

---

## 0. 结论速览

| # | 结论 | 证据强度 |
|---|---|---|
| **1** | **零 LLM 版已能分离 C1（执行）与 C2（挂起）在"环路内执行层"的信号** —— 挂起行与断言红行完全不相交 | **强**（两独立痕迹交叉一致） |
| **2** | **挂起通道救回 2 行**（aitester，41 口径 **+4.9pp**）/ **3 行**（df 臂，**+7.3pp**）。**全部落在"执行通道不可测"格，落在"执行通道=0"格的是 0 行** | **强**（计数精确） |
| **3** | **存量数据不足以在 M1 事后裁决层判定挂起通道** —— `rc_buggy`/`rc_fixed`/哪一侧超时**均未落盘**。C2 在判定层记 **`not_available`**，上表"救回"数只能算**环路内代理口径** | **这是本次最重要的诚实判定** |
| **4** | 项目自述"**`over_red` 里相当一部分是挂起**"→ **本批证否**：全 50 行中 `over_red` 30 行，仅 **1 行**（`sqrt`）有挂起痕迹（**3.3%**）；且该行 fixed 腿仍红，挂起通道同样救不回。**全库普查**（1157 行）进一步显示挂起仅 17 例且**全部在 QuixBugs**，合成批次 **957 行 0 例** | **强**（可反证） |
| **5** | **C3 逻辑通道 = `not_available`** —— src 层的 `spec_oracle_injected`（`:408`）与 `spec_oracle_verdict`（`:419`，六态）**均未透出到 `details[]`**；**C4 覆盖通道 = `auxiliary`**，4 个挂起行 `coverage` 全为 `0.0`，无独立信息 | 强 |

> **一句话**：挂起通道是真的，但它**很窄**（本批 ≤3/50），而且它救的是"**测不了**"的行，不是"**测出来是 0**"的行；要把它从**代理**升级为**可发表判定**，必须在 M1 裁决层补 4 个字段（§4）。

---

## 1. 方法

### 1.1 四通道定义（与任务书一致）

| 通道 | 定义 | 本批取值来源 | 验证等级 |
|---|---|---|---|
| **C1 执行** | 断言失败红（F2P 三段判定：buggy 红 ∧ fixed 绿 ∧ 无收集错误） | `details[].detection_rate` | `measured` |
| **C2 挂起** | 测试在 **buggy** 上超时 ∧ 在 **gold fixed** 上有限时间通过 → 记检出 | **工件未落盘判定所需字段** | `not_available`（判定层）/ `proxy`（环路内层） |
| **C3 逻辑** | `spec_oracle` 注入后判定失败 | `details[]` **无** `spec_oracle_injected` / `spec_oracle_verdict` | `not_available` |
| **C4 覆盖** | 覆盖率增益，**仅辅助**，不得单独作为检出证据 | `details[].coverage` / `execution_trace[].coverage` | `auxiliary` |

### 1.2 判定"挂起"的证据阶梯（存量工件里实际存在的三条痕迹）

三条痕迹**全部只读**，无 LLM、无 subprocess：

| 代号 | 痕迹 | 落点 | 性质 |
|---|---|---|---|
| **R1** | `execution_trace[].elapsed_seconds` **触顶** `EXECUTION_TIMEOUT`（本批 = 30s，取自 `provenance.env_snapshot`） | `details[].execution_trace` | 环路内执行器的**耗时天花板**（超时被截断在 30.0s） |
| **R2** | 批次日志显式文本行 `测试执行超时（>30s）: … -k', '<program>'` | `aitester.log:35,77,90,129,149,196,450,500,504,507,511,514` | **唯一带程序名的直接超时证据** |
| **R3** | `specificity_gate_verdict == "specific_red"` = 特异性门在 **gold fixed** 上跑绿 | `details[].specificity_gate_verdict` | 挂起通道"fixed 腿有限时间通过"的**代理** |

R1 与 R2 在本批 **4 行上完全一致**（每行各 3 次，见 §2.3），构成交叉验证。
非挂起行的 `execution_trace` 最大耗时中位数仅 **1.92s**，与 30.0s 天花板分离度极高。

### 1.3 为什么 R1/R2 只能是 `proxy`

**超时预算三处不一致，这是本次判定的核心事实：**

| 执行面 | 位置 | 超时 |
|---|---|---|
| 环路内执行器 | `src/graph/nodes.py::_executor_node` 侧 | **30s**（`EXECUTION_TIMEOUT`） |
| 特异性门 | `src/tools/detection_gates.py:52` `_GATE_TIMEOUT_SECONDS = 60` | **60s** |
| M1 事后裁决 | `experiments/_m1_metrics.py:302` `_run_pytest_in_tmp(timeout=120)` | **120s** |

⇒ R1/R2 只证明"**环路内**挂起"，**不能**证明"**M1 裁决层**挂起"。一个耗时 45s 的测试会在环路内超时（R1/R2 命中）但在 M1 层正常返回红（C1 可测）——两者不是同一个命题。

### 1.4 复算命令

```bash
.venv/bin/python experiments/four_channel_recompute.py --json-out review_2026/E3_four_channel.json
```

---

## 2. 结果

### 2.1 逐通道数字（终结点 = BASELINE.yaml:291-298 预注册的 41 个有 gold 缺陷程序）

| 通道 | `aitester` | `plain_llm_df`（外部参照） |
|---|---|---|
| **C1 执行** 正 / 零 / 不可测 | **17 / 20 / 4** | **31 / 6 / 4** |
| C1 率（可测分母 37） | 17/37 = **45.9%** | 31/37 = **83.8%** |
| C1 率（全分母 41） | 17/41 = **41.5%** | 31/41 = **75.6%** |
| **C2 挂起** 挂起嫌疑行 | **4** | **4** |
| C2 fixed 腿绿 | **2** | **3** |
| **C2 判正（救回）** | **2** | **3** |
| C3 逻辑 | `not_available` | `not_available` |
| C4 覆盖 | `auxiliary` | `auxiliary` |
| **四通道合并** 正 | **19/41 = 46.3%** | **34/41 = 82.9%** |
| 合并 Δ vs C1 | **+2 行 / +4.88pp** | **+3 行 / +7.32pp** |
| 合并后仍不可测 | 2 | 1 |

> 注：`C1 不可测 = 4` 而非任务书背景所述"4 行"以外的数字——**全 50 行口径下 `detection=None` 共 13 行**，
> 其中 **9 行是测试驱动脚本**（`*_test`，`task_metadata.test_cases` 为空串 → `_extract_gold_material`
> 在 `_m1_metrics.py:434` 直接返回 `None`，M1 **结构性**不可测，与 BASELINE.yaml:291-298 预注册的
> "50 = 41 缺陷程序 + 9 测试驱动"完全对齐），**4 行才是挂起**（`bitcount` / `find_first_in_sorted` /
> `sqrt` / `wrap`，四者 `test_cases` 均非空）。两臂的 13 行集合**逐一致**。

**全 50 行口径**（供对照）：aitester C1 17/50 = 34.0% → 合并 19/50 = 38.0%；df 31/50 = 62.0% → 34/50 = 68.0%。

### 2.2 C1 × C2 2×2 交叉表

**`aitester`（41 行终结点）**

| C1 \ C2 | C2=1（挂起 ∧ fixed 绿） | C2=0 | 行计 |
|---|---|---|---|
| **C1=1** | 0 | 17 | 17 |
| **C1=0** | **0** | 20 | 20 |
| **C1 不可测** | **2** | 2 | 4 |
| 列计 | 2 | 39 | 41 |

**`plain_llm_df`（41 行终结点）**

| C1 \ C2 | C2=1 | C2=0 | 行计 |
|---|---|---|---|
| **C1=1** | 0 | 31 | 31 |
| **C1=0** | **0** | 6 | 6 |
| **C1 不可测** | **3** | 1 | 4 |
| 列计 | 3 | 38 | 41 |

> **"执行通道=0 但挂起通道=1"的格子 = 0（两臂同为 0）。**
> 挂起通道的全部产出都落在 **C1 不可测列**（2 行 / 3 行）。

### 2.3 关键问题：挂起通道能把多少行变成可判定？

**精确计数（aitester 臂，41 口径）：**

| 行 | gate 裁决 | C1 | R1 触顶次数 | R2 日志次数 | fixed 腿绿 | 挂起通道 | 四通道合并 |
|---|---|---|---|---|---|---|---|
| `quixbugs__bitcount` | `specific_red` | `None` | 3/3 | 3 | ✅ | **1** | **1.0** |
| `quixbugs__find_first_in_sorted` | `specific_red` | `None` | 3/3 | 3 | ✅ | **1** | **1.0** |
| `quixbugs__sqrt` | `over_red` | `None` | 3/3 | 3 | ❌（fixed 仍红） | 0 | `None` |
| `quixbugs__wrap` | `unavailable` | `None` | 3/3 | 3 | ❔（不可判定） | 0 | `None` |

- **从 `detection=None` 变为可判定：2 行**（`bitcount`、`find_first_in_sorted`）＝ 41 行终结点中的 **4.9%**，13 个 `None` 行中的 **2/13 = 15.4%**。
- **从 `over_red` 变为可判定：0 行。** `sqrt` 是唯一"`over_red` ∧ 挂起"的行，但它在 gold fixed 上仍然**红**（门裁决 `over_red` 的前提就是执行完成且 `rc != 0`），挂起通道的 fixed 腿不成立。
- `wrap` 在 fixed 侧连门都判不了（`unavailable`），两通道皆不可判定。
- **df 臂救回 3 行**（`bitcount` / `find_first_in_sorted` / `sqrt`）——同一批任务在 df 臂下 `sqrt` 的门裁决是 `specific_red`（不同臂生成不同测试，fixed 侧结果不同），故多救回 1 行。**同一任务在不同臂的通道取值可以不同**，这本身是四通道协议的必要性证据。

> 环路内超时次数：aitester 每行 **3 次**（`MAX_ITERATIONS=3`，三次执行全部触顶），df 每行 **1 次**（单体臂只执行一次）。`aitester.log:35,90,149` = bitcount；`:77,129,196` = find_first_in_sorted；`:450,500,507` = sqrt；`:504,511,514` = wrap。

### 2.4 结构性结论：C1=0 ⇒ C2=0（不是巧合，是可证的）

`detection_rate` 取 `0.0`（`_m1_metrics.py:529-538`）只有三条路径，**每一条都与挂起通道的两条腿互斥**：

| C1=0 的成因 | 与挂起通道的关系 |
|---|---|
| `buggy_rc == 0`（测试在 buggy 上全过） | 测试**没有挂** → 挂起腿 (a) 不成立 |
| buggy 侧是收集/语法错误（`_looks_like_test_execution_error`） | 测试**报错**而非挂起 → 腿 (a) 不成立 |
| `fixed_rc != 0`（gold fixed 上仍红） | fixed 腿 (b)"有限时间通过"不成立 |

⇒ **挂起通道在结构上无法救回任何"执行通道=0"的行；它的全部价值局限于"执行通道不可测"格。**
这正是 §2.2 两个 0 格子的原因，也是把"挂起通道能改善检出"讲成"能救回一大片 `over_red`"属于**口径错误**的原因。

### 2.5 对"`over_red` 里相当一部分是挂起"的裁定

| 口径 | `over_red` 行数 | 其中有挂起痕迹 | 占比 |
|---|---|---|---|
| aitester，41 终结点 | 21 | **1**（`sqrt`） | **4.8%** |
| aitester，全 50 | 30 | **1** | **3.3%** |
| plain_llm_df，全 50 | 15 | **0** | **0.0%** |

**裁定：证否。** 该自述的机制前提也不成立——`specificity_verdict`（`src/tools/detection_gates.py:96-121`）
判定 `over_red` 的**前提是执行完成且 `rc != 0`**；测试若在 gold fixed 上**挂起**，
`_run_test_against_code` 返回 `None` → 裁决为 **`unavailable`**（`:91`, `:119`），**不会**落进 `over_red`。
本批 `unavailable` 恰好 1 行（`wrap`），与"挂起在 fixed 侧"的预期一致。
⇒ **`over_red` 与"挂起"在门的口径下是互斥集合**，把二者混为一谈是本次审查发现的一处**机制误述**。

> **附带发现（口径可审计性）**：产生 `specificity_gate_verdict` 的开关
> `DETECTION_SPECIFICITY_GATE_ENABLE` **不在** `_env_snapshot_keys`（`experiments/run_benchmark.py:2712-2771`，
> 共 39 键，实测缺失）——即**无法从工件证明门当时是开的**，只能从"裁决字段非空"反推。
> 同类缺失还有 `RED_REGRESSION_GATE_ENABLE`、`SPEC_ORACLE_EXEC_ENABLE`、`SPEC_IR_DSL_ENABLE`、
> `ASSERTION_AUGMENT_ENABLE`。与 D3/A1/RT1 三起事故同一机制（代码新增开关，快照清单未同步）；
> 另一成员已落地 `scripts/gates/check_env_snapshot_keys.py` 把该动作 CI 化，但其 `--select` 默认为
> `_ENABLE$`，**不覆盖** `GENERATOR_PAYLOAD` 这类非 `_ENABLE` 形态的开关（见 H1 预注册 G0 门）。

### 2.6 跨批次复现：挂起现象是 **QuixBugs 特有**，且**稳定复现**

把环路内挂起代理口径铺到**全部**存量批次（`--census`，覆盖 15 个批次/臂、1157 行）：

| 批次 / 臂 | 行数 | 挂起嫌疑 |
|---|---|---|
| `e4_quixbugs_FIXED_harness/aitester` | 50 | **4** |
| `e4_quixbugs_FIXED_harness/plain_llm_df` | 50 | **4** |
| `e4_quixbugs_aitester/aitester`（**更早的独立跑批**） | 50 | **4** |
| `e4_quixbugs_plain_llm_df/plain_llm_df`（独立跑批） | 50 | **5** |
| 其余 11 个**合成**批次/臂 | **957** | **0** |
| **合计** | **1157** | **17** |

**三条结论：**

1. **挂起是 QuixBugs 特有，合成基准 0 例**（957 行 / 0 例）。
   ⇒ 挂起通道的收益（§2.3 的 2–3 行）**不可外推**到合成集；
   任何"挂起通道能改善检出"的主张必须带"QuixBugs 口径"限定词。
2. **挂起集合跨独立跑批稳定复现**：
   `{bitcount, find_first_in_sorted, sqrt, wrap}` 在 **4 次独立跑批 / 4 个臂**中重复出现
   （仅 `e4_quixbugs_plain_llm_df` 多出 `to_base` 一行）。
   ⇒ 挂起是**程序（buggy 实现）的属性**，不是某次运行的偶然 ——
   这同时**反证**了"挂起是 LLM 生成质量导致的普遍现象"这一解读。
3. 与 §2.5 呼应：`over_red` 与挂起在门的口径下互斥，且挂起总量（17/1157）**远小于**
   `over_red`（本批 30/50）——"`over_red` 里相当一部分是挂起"在全库口径下同样**不成立**。

> 复现命令：`.venv/bin/python experiments/four_channel_recompute.py --census --json-out review_2026/E3_four_channel_census.json`

---

## 3. 存量数据充分性判定

### 3.1 充分性矩阵

| 通道 | 判定层是否可算 | 等级 | 缺什么 |
|---|---|---|---|
| C1 执行 | ✅ 可算 | `measured` | — |
| C2 挂起 | ❌ **不可算**（只能算环路内代理） | `proxy` | M1 裁决层 `rc_buggy` / `rc_fixed` / 超时侧别 / 不可判定原因 |
| C3 逻辑 | ❌ **不可算** | `not_available` | `details[].spec_oracle_injected` / `spec_oracle_verdict`（src 层已有，实验层未透出） |
| C4 覆盖 | ✅ 可算（但仅辅助） | `auxiliary` | — |

### 3.2 C2 为什么不足：`None` 是**五义**的

`_run_pytest_in_tmp`（`_m1_metrics.py:298-385`）把**五种完全不同的情况**折叠成同一个裸 `None`：

1. `subprocess.TimeoutExpired`（`:380-381`）—— **超时**（正是挂起通道要的）
2. `except Exception`（`:382-383`）—— IO 异常
3. QuixBugs 辅助材料缺失的 fail-closed（`:339-346`）
4. `module_name` 非法（`detection_gates.py:82`）
5. 门侧超时（60s）与 M1 侧超时（120s）**预算不同**

`_compute_detection_rate`（`:520-525`）拿到 `None` 后**立刻 `return None`**，`rc_buggy` / `rc_fixed` / `stdout` / `stderr` **全部被丢弃**，只有最终 float 透出到 `details[]`。
⇒ 从存量工件**无法**区分"`bitcount` 的 buggy 侧超时"和"材料读取失败"——只能靠 R1/R2 的环路内痕迹**旁证**。

### 3.3 C3 为什么不足

`src/` 侧的**协议层已就绪**，缺的是**实验层透出**：

| 字段 | state 层落点 | 是否透出到 `details[]` |
|---|---|---|
| `spec_oracle_injected`（三态：True/False/None） | `src/graph/state.py:408`，写入 `src/graph/nodes.py:967` | ❌ **未收录** |
| `spec_oracle_verdict`（六态：`not_attempted` / `compiled_empty` / `injected` / `injected_and_passed` / `injected_and_failed` / None） | `src/graph/state.py:419`，取值域常量 `src/graph/nodes.py:159-166`，升级 `:263-284`，写入 `:968`（P0-4，**2026-10-10 当日新增，尚未提交**） | ❌ **未收录** |

`experiments/run_benchmark.py` 的 `details` 键集合（`:1057-1061`，含 `spec_compile_rate` / `spec_expr_coverage`）
**没有收录任一字段**，失败分支占位表（`:1226-1228`）同样没有。已 `grep` 全文件确认 **`spec_oracle_verdict` 0 处命中**。
⇒ **逻辑通道的"行级判定结果"在 src 层已经能区分"注入 oracle 造成的红"与"LLM 断言造成的红"，
但该信息在写工件时被丢弃**——这正是 C3 记为 `not_available` 的唯一原因。

---

## 4. 一手核验方案（精确埋点清单）

> 本节是 §3 的必要配套：**不补齐这些埋点，C2/C3 就不能升级为可发表判定。**
> 本任务**不修改** `src/` 与既有 `experiments/*.py`，以下为交接给实现方的规格。

### 4.1 C2 挂起通道（4 处）

| # | 文件 | 锚点 | 改法 | 验收判据 |
|---|---|---|---|---|
| 1 | `experiments/_m1_metrics.py` | `_run_pytest_in_tmp`（`:298-385`） | 新增**平行**函数（或 `return_reason=False` 的可选参数）返回 `{rc, stdout, stderr, unavailable_reason}`，`unavailable_reason ∈ {timeout, io_error, support_missing, invalid_module}`。**裸 `None` 语义必须保持不变**（`detection_gates.py:85` 的委托调用零回归） | 现有 `tests/test_m1_metric_semantics.py` 全绿；新函数对 4 类原因各产 1 条用例 |
| 2 | `experiments/_m1_metrics.py` | `_compute_detection_rate`（`:473-540`） | 返回值旁透出 `detection_channels` 子字典：`{rc_buggy, rc_buggy_kind, rc_fixed, rc_fixed_kind, timeout_seconds_used}`；`*_kind ∈ {ok, timeout, io_error, support_missing}` | 对 `bitcount` 存量测试（`generated_test` + `data/quixbugs/python_programs/bitcount.py`）重跑须得 `rc_buggy_kind == "timeout"` |
| 3 | `experiments/run_benchmark.py` | `details` 行装配处（`:1078` `detection_rate` 相邻） | 把 `detection_channels` 原样并入 `details[]` | 新批次工件 `details[0]` 含该键 |
| 4 | `experiments/run_benchmark.py` | `_env_snapshot_keys`（`:2712-2771`） | `EXECUTION_TIMEOUT` 已在册；**补登记新增的任何开关**（消融类开关不入册 = 无法从工件证明干预生效，D3/A1 同一审计缺口） | `scripts/gates/check_env_snapshot_keys.py` 通过 |

**关键语义修复（`src/tools/detection_gates.py`）**：`specificity_verdict`（`:96-121`）
把 **`unavailable` 坍塌成三义**：① 无 gold 材料（`:116`）② `module_name` 非法（`:82`）
③ 执行超时/IO 异常（`:91` → `res is None`）。
建议拆出第四个裁决值 **`fixed_timeout`**（或让 `unavailable` 携带 `reason`），
否则"挂起在 fixed 侧"与"根本没有 gold"永远无法区分——而这正是 `wrap` 行不可判定的原因。

> **不新增第二套执行面**：`detection_gates.py` 的门①已明确委托 `_m1_metrics._run_pytest_in_tmp`
> （见该文件模块 docstring），上述改动**同源扩展**，不引入口径分叉。

### 4.2 C3 逻辑通道（3 处）

| # | 文件 | 锚点 | 改法 |
|---|---|---|---|
| 1 | `experiments/run_benchmark.py` | `details` 键集合（`:1057-1061`） | 增 `"spec_oracle_injected"` 与 **`"spec_oracle_verdict"`**（后者才是可判定的六态字段） |
| 2 | `experiments/run_benchmark.py` | 失败分支占位（`:1226-1228`） | 同步补两键 `None`，保持键集合同构（该文件既有约定） |
| 3 | `experiments/run_benchmark.py` | `_env_snapshot_keys`（`:2712-2771`） | 登记 `SPEC_ORACLE_EXEC_ENABLE`（实测缺失） |

**验收判据**：新批次 `details[]` 中 `spec_oracle_verdict` 的取值域覆盖
`{not_attempted, compiled_empty, injected, injected_and_passed, injected_and_failed}`
（当前 logic 档 `SPEC_ORACLE_EXEC_ENABLE=true`，非 `fast` 档应出现 `injected*` 取值）；
`injected_and_failed` 的行即为**逻辑通道判正**，且必须能与 C1 交叉列表（不应与 C1=1 完全同构——
若同构则该通道与 M1 判定同义反复，须引入独立第二裁决）。

### 4.3 C4 覆盖通道（无需埋点）

`coverage` 已落盘。但本批 4 个挂起行 `coverage` 与 `execution_trace[].coverage` **全为 `0.0`**
（挂起 = 测试没跑完 = 覆盖率天然为 0）。⇒ 覆盖通道对挂起行**零信息量**，
在四通道协议中只能保持 `auxiliary`，**不得**用它给挂起行背书。

---

## 5. 局限与不得外推的边界

1. **主数字来自单批次**：§2.1–§2.5 的交叉表来自 `e4_quixbugs_FIXED_harness`（QuixBugs FIXED 口径、seed 42、logic 档、双门开、n=50）。§2.6 的普查把**挂起分布**扩到全库 15 个批次/臂（1157 行），但不改变主交叉表的批次归属。**不得**把 FIXED harness 的检出率外推到 synthetic 批次、SWE-bench 或其它 profile。
2. **"救回 2/3 行"是环路内代理口径**，不是 M1 判定口径。§4.1 落地前，**该数字不得作为检出率改进的正式证据**引用；引用时须并列"代理口径"限定词。
3. **R1 的 30.0s 天花板依赖 `provenance.env_snapshot.EXECUTION_TIMEOUT`**。若某批工件该键缺失（D3 类缺口），脚本退化为默认 30 并**不报错**——建议后续把该键列为强制入册项。
4. **`sqrt` 与 `wrap` 的不可判定不是数据缺失，而是事实**：前者 fixed 侧真红（过红），后者 fixed 侧不可判定。四通道协议**不应**把它们计入检出。
5. 本次**未修改任何入库工件**；`git status --short experiments/results` 为空可证（§6）。
6. **挂起通道的收益不可外推**：全库普查（§2.6）显示 957 行合成批次挂起 **0 例**，17 例挂起**全部**落在 QuixBugs（4 个稳定复现的程序）。任何"挂起通道改善检出 +Npp"的数字**必须**标注"QuixBugs 41 口径"，**不得**作为通用增益引用。

## 6. 可复现性

```bash
cd /Users/wangchenyu/Workspace/AITester
# 1) 工件未被改动
git status --short experiments/results      # 应为空
# 2) 重算（零 LLM、零 subprocess）
.venv/bin/python -m ruff check experiments/four_channel_recompute.py
.venv/bin/python experiments/four_channel_recompute.py --json-out review_2026/E3_four_channel.json
# 3) 全库挂起普查（§2.6）
.venv/bin/python experiments/four_channel_recompute.py --census --json-out review_2026/E3_four_channel_census.json
# 4) 核查证据文件哈希与 SHA256SUMS 一致
cd experiments/results/e6_a1_batches && shasum -a 256 -c SHA256SUMS 2>/dev/null | grep -c OK
```
