# AR 轮：OTel 导出标识先合法再谈稳定——单 trace、32/16 位 hex、确定性派生（2026-10-21，零 LLM）

**范围**：`src/observability/otel_export.py` 的 `_record_to_span` / `export_trace_jsonl`
（`trace.jsonl` → OTel GenAI 语义约定 span）。AQ 轮收口了数值值域；本轮收口
**标识与字符串值域**：`trace_id` / `span_id` 的 OTel 形态、一个文件一个 trace、
缺失 / 非法标识的确定性派生、同一 trace 内 `span_id` 冲突，以及 node 名称 /
`decision` / `decision_reason` / `strategy_selected` / `stop_reason` / `task`
的字符串门。

**结论**：导出器过去把 `run_id` **原样当 trace_id**、把 `span_id` **原样导出**。
真实语料里 `run_id` 是 16 位 hex、`span_id` 是 12 位 hex，都不符合 OTel
（trace_id 32 位、span_id 16 位）；`task_start` / `task_end` 没有显式标识时
**每次导出生成随机 uuid**，node 又拿 `run_id` 当 trace_id，于是同一个文件出现
**两个 trace**，root 与子 span 的 parent 引用**跨 trace**。真实语料实测：
**8002 个文件多 trace、61188 条 parent 断链、9086/9086 个文件重复导出标识不一致**。
处置后：标识规范化为 32/16 位小写 hex（短 hex 左补零、大小写归一），一个文件一个
trace_id，缺失 / 非法标识按 SHA-256 确定性派生，同 trace 内冲突改派生并披露；
字符串属性只导出 `str`。**48 例新锁 + 16/16 变异锚点转红 + 0 逃逸**；真实语料
9086 文件 / 129058 span 全部单 trace、标识合规、parent 全在文件内、零披露、
重复导出逐字相同。**未提交。**

---

## 1. 缺陷定义

改前核心读取（`src/observability/otel_export.py`，AR 前原文，HEAD 版本）：

```text
# 每文件 trace_id：取 task_start 的 run_id，缺失时随机
first = next((r for r in records if r.get("event") == "task_start"), None)
trace_id = (first.get("run_id") if first else None) or uuid.uuid4().hex[:32]
...

# 每条记录：run_id 原样覆盖 trace_id；span_id 原样或随机
trace_id_val = record.get("run_id") or trace_id
span_id = record.get("span_id") or uuid.uuid4().hex[:16]
name = record.get("node") if event == "node" else f"task_{record.get('event', 'unknown')}"
...
for src_key, dst_key in (...):
    if record.get(src_key) is not None:
        attributes[dst_key] = record[src_key]
if record.get("task") is not None:
    attributes["aitester.task_id"] = record["task"]
```

合成记录实测（`_record_to_span` / `export_trace_jsonl`，AR 前）：

| 观测（合成记录） | 改前读数 | 根因 |
|---|---|---|
| `run_id="ab"` | `trace_id="ab"`（2 位） | run_id 原样当 trace_id，无 32 位约束 |
| `span_id="cd"` | `span_id="cd"`（2 位） | span_id 原样导出，无 16 位约束 |
| `run_id="AB"` / `span_id="CD"` | 大写原样 | 无小写归一 |
| `run_id="not-hex"` | `trace_id="not-hex"` | 无 hex 门 |
| `span_id="0"*16` | 全零 span id 原样导出 | 无全零门（OTel 非法） |
| `task_start` / `task_end` 无 `span_id` | 每次导出新 `uuid4().hex[:16]` | 随机兜底 |
| node 有 `run_id="ab"`、root 无 `run_id` | node trace `"ab"` ≠ root 的 uuid32；parent 指向另一 trace 的 root | 文件级 trace 被记录级 run_id 覆盖 |
| `node=7` | span 名为整数 `7` | 名称无字符串门 |
| `decision=7` / `task=["a"]` | 属性为整数 / 列表 | 字符串属性无类型门 |
| `node=""` | span 名为空串 | 无空名回退 |

真实语料普查（只读，`/tmp/ar_probe.py`）：**9086 份 `.trace.jsonl` /
129058 个导出 span**（9085 `task_start` + 110926 `node` + 9046 `task_end` +
1 个合成 root）：

| 读数 | 改前 |
|---|---|
| `trace_id` 长度 32 / 16 | **67870 / 61188** |
| `span_id` 长度 16 / 12 | **67870 / 61188** |
| 同一文件出现 >1 个 `trace_id` | **8002 个文件** |
| parent 引用不在同文件同 trace 的 span | **61188 条** |
| 两次导出标识不一致 | **9086 / 9086 个文件** |
| 带 `run_id` / `span_id` 的 node | 61188（其余 49738 个 node 两者皆无） |
| 多 run_id 文件 / run_id 冲突 | 0 / 0 |
| node 名与字符串属性非 `str` | 0（字符串门是潜在缺陷） |

要点：**标识缺陷是真实缺陷，字符串门是潜在缺陷**。真实 trace 的单文件里
`run_id` 只出现在部分 node（16 位），root / `task_end` / 其余 node 没有标识；
因此导出必然同时产生 32 位 uuid trace 与 16 位 run_id trace，parent 引用无法
落在同一 trace。

## 2. 处置

### 2.1 五个私有判定器 / 派生器

| 名称 | 位置 | 输入 | 接受 / 行为 |
|---|---|---|---|
| `_canonical_identifier` | `otel_export.py:131` | 任意值 + 宽度 + 字段名 | `None` 静默缺席；`str` 小写、hex、非空、≤宽度、非全零 ⇒ 左补零到宽度；否则机制名 |
| `_derived_span_id` | `otel_export.py:146` | `trace_id`、记录序号、尝试次数 | `SHA-256("aitester-span:{trace}:{index}:{attempt}")[:16]`，跳过全零 |
| `_file_trace_id` | `otel_export.py:155` | 全部记录 + 路径 | 首个可规范化 `run_id` → 首个非法非空字符串哈希 → `path:` 哈希；输出 32 位 hex |
| `_span_name` | `otel_export.py:171` | 记录 + event | 非 node ⇒ `task_<event>`；node 为 `str` 且非空 ⇒ 原名；非字符串 / 空串回退 `"node"` 并披露 |
| `_ensure_unique_span` | `otel_export.py:184` | span、trace、序号、已见集合 | 首次出现保留；冲突改派生 id 并追加 `span_id_duplicate` |

标识机制名：`run_id_not_string:<T>` / `run_id_invalid_format` /
`run_id_mismatch`；`span_id_not_string:<T>` / `span_id_invalid_format`；
`span_id_duplicate`；名称机制名 `node_not_string:<T>` / `node_empty`。

### 2.2 `_record_to_span` 的接线

| 记录形态 | 改后行为 | 披露 |
|---|---|---|
| `run_id` 可规范化且等于文件 trace | 使用文件 trace_id | 无 |
| `run_id` 可规范化但不同于文件 trace | 仍使用文件 trace_id（不拆 trace） | `run_id_mismatch` |
| `run_id` 非字符串 / 空串 / 非 hex / 超宽 / 全零 | 使用文件 trace_id | `run_id_*` |
| `span_id` 可规范化 | 左补零 / 小写后的 16 位 hex | 无 |
| `span_id` 缺失 | `_derived_span_id(trace, index)` | 无（缺席是常态） |
| `span_id` 非法 | 派生 16 位 hex | `span_id_*` |
| 同一 trace 内 `span_id` 冲突 | 保留首次；后者改派生 | `span_id_duplicate`（追加在既有披露之后） |
| `task_start` | root（`parent=None`），参与冲突检测 | — |
| `node` / `task_end` | 子 span，parent = 文件内的 root / 合成 root | — |
| 无 `task_start` | 合成 `task_root_synthetic`，`_derived_span_id(trace, -1)` | `aitester.synthetic_root=True`（既有） |

### 2.3 字符串值域

| 字段 | 属性 | 改后行为 | 披露 |
|---|---|---|---|
| `node`（仅 node） | span `name` + `gen_ai.operation.name` | `str` 非空 ⇒ 原名；`None` / 缺席 ⇒ `"node"`；非 `str` / 空串 ⇒ `"node"` | `node_not_string:<T>` / `node_empty` |
| `decision` | `aitester.decision` | 仅 `str`；空串照导出 | `decision_not_string:<T>` |
| `decision_reason` | `aitester.decision_reason` | 同上 | `decision_reason_not_string:<T>` |
| `strategy_selected` | `aitester.strategy` | 同上 | `strategy_selected_not_string:<T>` |
| `stop_reason` | `aitester.stop_reason` | 同上 | `stop_reason_not_string:<T>` |
| `task` | `aitester.task_id` | 仅 `str`；空串照导出 | `task_not_string:<T>` |

### 2.4 机制名顺序

`run_id → span_id → name → ts → duration → token（input/output/total）→
string attrs（decision / decision_reason / strategy_selected / stop_reason）→
budget_remaining → iteration → task`。

**注意**：本轮**故意改变干净记录的标识**——这正是缺陷修复本身；干净记录的
**属性**（数值与字符串）与改前逐字一致（AQ 数值语义未变），但 `trace_id` /
`span_id` / 合成 root 的 id 会按新规则规范化 / 派生。不得以"导出逐字不变"作为
本轮回归判据；回归判据是**同一文件重复导出逐字相同**。

## 3. 真工件证据

- **全量真实语料**：9086 份文件 → **129058 个 span**；每文件**恰好 1 个**
  `trace_id`；所有 `trace_id` 为 32 位小写 hex、所有 `span_id` 为 16 位小写 hex；
  所有非空 `parent_span_id` 都在**同文件**的 span id 集合内；同文件 `span_id`
  **无重复**；`aitester.export_value_reasons` **0 个实例**。
- **重复导出稳定**：同文件连续导出两次，`export_trace_jsonl` 返回值**逐字相等**
  ——9086/9086 全部通过（测试内锁）。
- **非法 / 缺失标识**：合成用例覆盖非字符串、空串、非 hex、超宽、全零、缺失、
  大小写、短 hex、冲突；非法值不导出原值，披露后改用派生 id。
- **无 `task_start` / 空文件**：合成 root 的 32 位 trace 与 16 位 span id 均由
  路径确定性派生，重复导出稳定（不再是 uuid）。
- **未改写任何归档或原始批次 JSON**；真实语料只读。

## 4. 回归锁

`tests/test_otel_export_identifier_domain_ar.py`：**48 例**（collected）。

| 组 | 例数 | 覆盖 |
|---|---|---|
| `TestIdentifierCanonicalization` | 10 | 缺席、满宽、大写、短 hex、非字符串、非法形态参数化、全零 |
| `TestRecordIdentifierMapping` | 11 | 短 id 规范化、大写端到端、坏 run_id、run_id 不一致、缺失 / 非法 / 全零 span_id 派生、node 名三种回退 |
| `TestFileTraceId` | 4 | 首個可规范化 run_id、路径种子、首个非法字符串哈希、非字符串 / 空串回落路径 |
| `TestDuplicateSpanIds` | 4 | 重复改派生、披露追加、root 冲突保持 parent、显式 id 撞派生 |
| `TestStringValueDomain` | 11 | 全部字符串属性、空串、四个字段非字符串参数化、task 非字符串参数化、缺席 |
| `TestReasonOrder` | 1 | 标识 → 名称 → 数值 → 字符串 → budget → iteration → task 的完整顺序 |
| `TestExportEndToEnd` | 5 | 单 trace / 合法形态 / parent 闭合、重复导出、合成 root、路径依赖、空文件 |
| `TestRealCorpus` | 2 | 9086 文件 / 129058 span 形态与零披露、全语料重复导出稳定 |

同时：

- `tests/test_p2_1_otel_export.py`：头部第 5 条改为 AR 口径；`test_trace_id_from_run_id`
  断言 16 位 run_id 左补零为 32 位 trace；`test_span_id_stable_for_same_file`
  断言短 hex 规范化为 16 位并稳定；`test_node_without_token_usage_omits_genai_usage`
  的 run_id 换成合法 hex。**用例数不变（7）**。
- `tests/test_otel_export_value_domain_aq.py`：只把夹具 `span_id` / `run_id` 换成
  合法 hex，保持 AQ 的数值机制断言纯净。**用例数不变（61）**。

## 5. 变异验证

基线目标集 **147 collected**（AR 48 + AQ 61 + p2_1 7 + small_gaps 31）。每个锚点：
精确一次替换 → `compile()` 预校验 → 跑四个文件 → **sha256 原字节还原**
（不用 `git checkout` / `git stash`）；每次 collected 恒为 **147**。

| 锚点 | 变异 | 结果 |
|---|---|---|
| M1 | 去掉 `.lower()` | 2 failed |
| M2 | 去掉 `zfill(width)` | 9 failed |
| M3 | 允许全零标识 | 2 failed |
| M4 | 放宽 hex / 超宽检查 | 7 failed |
| M5 | 非字符串标识放行 | 4 failed |
| M6 | trace 种子恒用路径 | 1 failed |
| M7 | 可规范化 run_id 不参与文件 trace | 31 failed |
| M8 | 用原始 run_id 当 span trace | 8 failed |
| M9 | 派生 id 忽略 trace_id | 1 failed |
| M10 | 非字符串 node 名原样返回 | 1 failed |
| M11 | 空 node 名原样返回 | 1 failed |
| M12 | 非字符串属性照导出 | 4 failed |
| M13 | 非字符串 task 照导出 | 4 failed |
| M14 | token 机制名提到队首 | 2 failed |
| M15 | 跳过重复 span_id 处置 | 4 failed |
| M16 | 冲突覆盖既有披露 | 1 failed |

合计 **16/16 转红、0 存活**；还原后目标集 **147 passed**、文件 sha256 与基线
逐字节相同（`2ae8fee09830c60594b17927480739224d548c6a756c63c27e5788f5e53d6de5`）。

## 6. 收口读数

- 登记前一跑（不带覆盖率）：**10950 passed / 1 failed / 5 skipped、176.83s**；
  collected **10956**；唯一失败 = `BASELINE.yaml` 守卫（仍写 10903，
  实收 − 声明 = 53 > 6 容差）。
- 带覆盖率一跑（`make test-cov`）：**10950 passed / 1 failed / 5 skipped、181.58s**。
- **覆盖自审**（`coverage.xml` root 口径）：**18898/19424 行 = 97.2912%**、
  **6902/7338 弧 = 94.0605%**。分母较 AQ **+81 行 / +42 弧**；覆盖 **+79 / +40**；
  未覆盖行 **526**（+2 = `_derived_span_id` / `_ensure_unique_span` 两处
  SHA-256 全零防御循环，结构性不可达）；缺弧 **436**（+2 同源）。
- `src/observability/otel_export.py`：**209/212 行 = 98.58%**；未覆盖行
  152、194（全零防御）、306（空行守卫）；偏弧 323→320 / 347→343 是
  "接受的 event 必有 span" 的结构性分支。
- 十项核心模块行覆盖与三项核心路由分支覆盖按同一份 `coverage.xml` 复算全部不变
  （base_agent 98.51 / api_manager 99.24 / dataset_loader 97.28 / graph_nodes 99.88 /
  code_analyzer 99.38 / planner 99.09 / dependency 96.26 / multi_candidate 98.67 /
  cross_file 92.98 / rag_retriever 98.10；routing 99.17 / 96.49 / 100.00）。
- 刷新 `BASELINE.yaml`（10951 / 18898·19424 / 6902·7338）后确认跑：
  **10951 passed / 5 skipped / 0 failed、177.27s、rc=0**；collected **10956**
  = passed 10951 + skipped 5（= AQ 的 10903 + AR 的 48）。
- **门禁实测（两次单独跑 `make gates`，均不与其他命令重叠）**：两次均 `rc=0`；
  墙钟 **184.59s / 183.66s**；链内 pytest（`-n 4 --dist loadfile`，**不带 `--cov`**，
  与带覆盖率读数不可互换）**10951 passed / 5 skipped / 0 failed、179.60s / 178.95s**
  （73 / 53 warnings；collected 10956）；`ruff check` All checks passed、
  `ruff format --check .` **916 files already formatted**、mypy
  `Success: no issues found in 135 source files`；双语文档 0 警告 / 0 失败；
  文档链接 strict **160 份文件 / 680 条链接 / 0 错误 / 0 警告**；env-budget
  253/253 登记；`check_baseline` 结构校验与 `check_baseline_numbers` 均通过；
  状态通道 134 文件通过；env-snapshot 84/84 覆盖、缺失 0；tool-versions OK；
  JSON 契约 7/7；JSON strict **7273 工件 = 7271 严格 + 2 路径豁免 + 0 违规、
  300 源文件 0 写入点违规**；报告↔工件对账 [OK]（不一致 0；T-10 严格 29 行 /
  25 可测，宽松 62 / 55；状态登记册覆盖率对账相符）；零断言 **436 测试文件 /
  0 违规**。**回填后验证跑**：`rc=0`、墙钟 **184.61s**、链内 **179.86s /
  41 warnings**（同一 collected 10956，各项计数不变）。
- **门禁首跑自纠（如实登记）**：第一次 `make gates` 在 `format` 门 `rc=2`——
  本手册 §1 的 `python` 围栏含占位 `...`，`ruff format` 要求改写为
  `for src_key, dst_key in ...:`；该代码块是"改前原文摘录 + 省略号"，不是可执行
  程序，故把围栏改为 `text` 而不是让格式化器改写原文。改后两次全链 `rc=0`；
  未改任何源码或断言。

## 7. 边界（不得引用为「OTel 导出标识已全仓闭合」）

1. **trace_id 是文件级而不是记录级**：一个文件一个 trace；`run_id` 不一致披露
   `run_id_mismatch` 但不会拆成多 trace。不要把 trace_id 当 run_id 的逐字编码
   （短 hex 被左补零、大小写归一）。
2. **确定性派生 ≠ 真实标识**：缺失 / 非法 `span_id` 由
   `SHA-256(trace_id,index)` 派生，可复现但不是生产者观测到的 id；派生值不携带
   写入端信息。
3. **全零 / 非 hex 不可导出**：这是 OTel 合法性拒绝，不是"补零后仍可用"；
   披露机制名后改用派生 id。
4. **重复 `span_id` 只改后者**：同 trace 内冲突时保留首次出现，后者改派生并追加
   `span_id_duplicate`；不保证冲突语义（可能是上游重复写入）。
5. **字符串只收 `str`**：空字符串仍是合法字符串（照导出）；`node` 空串例外
   回退 `"node"` 并披露 `node_empty`。
6. **无披露 ≠ 标识已核验**：无 `run_id` / `span_id` 的记录会静默派生确定性 id
   （缺失是常态），不披露；只有非法值披露。
7. **本轮改变干净导出的标识**：标识规范化 / 派生是有意行为；回归判据是
   "同一文件重复导出逐字相同"，不是"与 AR 前逐字相同"。
8. **AQ 数值域仍适用**：本轮不改时间戳 / token / budget / iteration 语义；
   数值坏值的 0 哨兵与 `export_value_reasons` 口径不变。
9. **覆盖口径**：登记值取 `coverage.xml` root（6902/7338）；`coverage report`
   偏弧是另一口径，不得混用。

## 8. 复算命令

```bash
# 目标集（48 collected）
.venv/bin/python -m pytest tests/test_otel_export_identifier_domain_ar.py -q

# 含受影响旧锁（147 collected）
.venv/bin/python -m pytest \
  tests/test_otel_export_identifier_domain_ar.py \
  tests/test_otel_export_value_domain_aq.py \
  tests/test_p2_1_otel_export.py \
  tests/test_small_gaps_closeout.py -q

# 变异验证（逐锚点回退 → compile → 跑锁 → sha256 原字节还原）
.venv/bin/python /tmp/ar_mutations.py

# 全量 + 覆盖率（CI 同口径；不与 make gates 重叠）
make test-cov
```

`/tmp/ar_mutations.py`、`/tmp/ar_probe.py` 是本次运行的临时脚本（不入库）；
复算时以本文件第 1、3、5、6 节的读数与锚点描述为准。
