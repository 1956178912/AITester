# E2 / P0-3b：补丁未落盘零 LLM 诊断报告（"有补丁文本但 `patch_plausible=0`"）

生成时间：2026-10-10　生成者：patch-analyst（task-6）
数据来源：既有批次工件（只读）+ `review_2026/E2_fence_recompute.json`（重算）+ 一次零 LLM gold 重放（`experiments/repair_replay.py::replay_row`，ADR-0021 口径）
代码版本：重放期间 `src/tools/patch_applier.py` / `experiments/_m1_metrics.py` 哈希稳定（`9a9cba278f6d5e66` / `6333b0c8f72ca9bd`）

---

## 0. 结论摘要

1. **口径先纠正**：266 有补丁文本 → 144 plausible → "≈122 行未落盘"中的 **122 不成立**。
   144 是 **274**（全部带补丁行）口径的 plausible 数，而 266 是"有 gold 材料"口径。
   正确数字：**274 中 130 行未落盘；266 可重放口径内 129 行**（差 1 行 = 无 gold 材料的
   `synthetic__palindrome_case_sensitive_0000`）。
2. **主因不是围栏残留，而是证据门**：全三组 **402** 行"有补丁文本但未落盘"中，
   **394 行（98.0%）** 由 `PATCH_EVIDENCE_GATE_ENABLE`（默认开）在**写盘成功之后**
   回滚原文件所致；**7 行（1.7%）** 是类体全文件补丁的应用模式缺口（独立 bug）；
   **1 行（0.2%）** 是 2026-10-01 老代码的命名契约拒绝。
   main_batch 130 行的构成：**129 证据门 + 1 契约拒绝**。
3. **核心假设（"围栏残留导致 `safe_apply_patch` 判定非法"）＝ 否证**：代码层
   `normalize_patch_text` 在所有守卫之前执行（`src/tools/patch_applier.py:236`）；
   数据层 862/862 带补丁行清理后全部 wellformed、0 语法错误；且 394 行证据门拒绝的
   行**带有非空 `patch_evidence_level`**——该字段只在 `if written:` 分支写入
   （`src/graph/nodes.py:1841`），**证明补丁当时已成功应用到目标文件并通过全部静态守卫**，
   随后才被证据门回滚。围栏残留对"落盘"的量化影响 = **0 行**。
4. **但"补丁其实可用却被写盘层拒绝"这半个假设成立，且量级很大**：
   - main_batch 129 行未落盘中，**44 行（34.1%）经 gold 独立裁决为 correct**
     （本机重放：`written=1` 行 71/137=51.8% correct vs 未落盘 44/129=34.1%）；
   - 若旁路证据门，修正口径 repair = **115/266 (43.2%) → 159/266 (59.8%)，+16.5pp**；
   - 全三组的同类上界（工件自带 `patch_correct`）：**88 行**（r4 13 + e6 75），
     加上 main_batch 重放 44 行 → **全球上界 132 行**。
5. **误导性标签（本次诊断的第二个硬发现）**：129/130 行的 `error_category` 是
   `patch_validation_failed`，124 行 `stop_reason` 是 `skip_debugger_repair_invalid`
   （经 `src/observability/failure_taxonomy.py:75` 进一步映射为
   `GENERATION_CAPABILITY_FAILURE`=模型能力失败）。两者**都是从
   `repair_history[-1].patch_applied is False` 派生的后果标签**
   （`src/agents/error_classifier.py:1288`），而 `patch_applied=False` 的真实含义
   在 129 行里是"证据门回滚"，不是"补丁被安全守卫拒绝"。**按这两个字段做归因
   会把门禁策略问题系统性错判为模型能力问题。**

---

## 1. 口径与范围（数字从哪来）

| 记号 | 范围 | 行数 |
|---|---|---|
| S0 | `main_batch/*` × `aitester` 臂，全部结果行 | 669 |
| S1 | S0 中 `patch` 非空 | **274**（= ADR-0021 的 274/274 围栏行） |
| S2 | S1 ∩ `task_metadata.test_cases` 非空（可重放） | **266** |
| S3 | S1 中 `patch_plausible=1` | 144 |
| S4 | S2 中 `patch_plausible=1` | **137** |
| **未落盘（S1）** | S1 − S3 | **130** |
| **未落盘（S2）** | S2 − S4 = 129 | **129**（≈ 报告的 "122"） |
| S5 | 全三组（main_batch + r4_batches + e6_a1_batches）`patch` 非空 | 862 |
| **未落盘（S5）** | S5 中 `patch_plausible=0` | **402** |

122 的来历：`266 − 144 = 122` 把 274 口径的 plausible 数（144）减到 266 口径的
分母上；S3 中有 7 行（8 行无 gold 材料中的 7 行）本就在 S2 之外。正确值是 **129**。

复现：`.venv/bin/python scripts/tools/refresh_patch_field.py`（产物
`review_2026/E2_fence_recompute.{md,json}`，其中 `not_written_rows` 即 S5 逐行清单）。

## 2. 分类表（原因分布）

### 2.1 全三组 402 行

| 类别 | 计数 | 占比 | 机制（代码落点） |
|---|---|---|---|
| **C1 证据门回滚**（写盘成功 → 证据不足 → 恢复原文件） | **394** | 98.0% | `src/graph/nodes.py:1842`（`patch_evidence_gate_enabled() and not evidence_allows_write(level)`；行号基于 2026-10-10 17:0x 工作树，锚点为符号名）→ `_write_file_atomic(原文件)` + `written=False` + `source_patched_unverified=True` |
| **C2 类体全文件补丁无法应用** | **7** | 1.7% | `src/tools/patch_applier.py:116`（`_is_full_file_patch` 判据不含"仅类定义"形态）→ `:280` 取到类方法名 → `:148`（只查顶层 def）→ `applied=False` → `src/graph/patch_io.py:384` |
| **C3 命名契约拒绝**（2026-10-01 老代码，无证据门阻断语义） | **1** | 0.2% | `contract_missing_symbols=['LOWER_MAP']`，`applied=False` |
| 合计 | **402** | 100% | |

判据：
- C1 的识别键 = `patch_evidence_level ∈ {none, keyword}` ∧ `source_patched_unverified=True`
  ∧ 工件代码版本含"证据门真阻断"语义（30 个文件中 **27** 个如此；3 个 2026-10-01 文件
  的 `evidence_guard` 为 `if applied:` 标记制，已单独归入 C3）；
- C2 的识别键 = `patch_evidence_level is None` ∧ `applied` 失败（`if written:` 未进入）。
- **`patch_evidence_level` 非空 ⟹ 写盘曾成功**（该键仅在 `if written:` 分支写入）；
  C1 的 394 行因此是"补丁在运行时被成功应用并写盘"的直接证据。

### 2.2 main_batch 130 行（S1 口径，逐项分布）

| 维度 | 分布 |
|---|---|
| 类别 | C1 证据门 **129**、C3 契约拒绝 **1** |
| `patch_evidence_level` | `none` 107、`keyword` 23（C1 内：`none` 106 + `keyword` 23） |
| `source_patched_unverified` | `True` 130/130 |
| `stop_reason` | `skip_debugger_repair_invalid` 124、`max_iterations` 5、`test_passed` 1 |
| `error_category` | `patch_validation_failed` 129、`test_regenerated_pass_unverified` 1 |
| `iterations` | 2 → 124 行、3 → 5 行、1 → 1 行 |
| `patch` 形态 | `python\n` 前缀 130/130、markdown 围栏 0；清理后 `ast.parse` 全通过（130/130） |
| `patch` 字节长度 | min 84 / median 284 / max 1344（无空补丁、无 unified diff） |
| `contract_missing_symbols` | 非空 2 行（`LOWER_MAP`、`list`）——均为 C1（证据门先于契约判定生效） |
| `patch_resample_stats` | 全为 None（未走 2.2 重采样路径） |
| `detection_first_status` | `red_not_repaired` 128、`red_then_green` 1、`None` 1 |

### 2.3 全三组 402 行的横向分布

| 维度 | 分布 |
|---|---|
| `stop_reason` | `skip_debugger_repair_invalid` 387、`max_iterations` 14、`test_passed` 1 |
| `iterations` | 2 → 387、3 → 14、1 → 1（**第 2 轮即早退是主导路径**） |
| `error_category` | `patch_validation_failed` 401、`test_regenerated_pass_unverified` 1 |
| `patch` 形态 | `python\n` 前缀 302、markdown 围栏 100；`ast.parse` 全通过 402/402 |
| `patch` 字节长度 | min 84 / median 517 / max 2712 |
| `patch_evidence_level` | `none` 366、`keyword` 29、`None` 7（= C2） |
| 跨文件任务占比 | 未落盘行中 32/129（main_batch）为 `is_cross_file`，而落盘行仅 14/137 → 跨文件行被拒率高 **2.4×**（假说：证据等级依赖本地化，跨文件定位更难拿到 sbfl/gold） |

## 3. 核心假设检验：围栏残留 → 写盘层拒绝？

**结论：否证（falsified）。** 三条独立证据：

1. **代码层（口径顺序）**：`src/tools/patch_applier.py:236` 在任何守卫之前执行
   `clean_patch = normalize_patch_text(patch)`；围栏/`python:` 前缀在进入
   `_is_full_file_patch`、`safe_apply_patch`、`_safe_write_patch` 之前已被剥离。
   围栏文本**不可能**成为写盘层拒绝的原因。
2. **数据层（文本形态）**：全部 862 带补丁行都是围栏形态，清理后 **862/862**
   wellformed（0 语法错误、0 空补丁、0 unified diff）；402 未落盘行的文本形态
   与 460 落盘行无任何形态学差异（同为围栏、同为 wellformed）。
3. **数据层（更强的反证）**：C1 的 394 行带非空 `patch_evidence_level`，而该字段
   只在 `if written:` 分支写入（`src/graph/nodes.py:1841`）——**说明这些补丁在运行时
   已经被成功应用到真实目标文件并通过了长度/函数定义/路径/契约等全部静态守卫**，
   随后才被证据门回滚。既然写盘曾成功，"写盘层拒绝"就不可能由文本形态造成。
4. **残余（C2，7 行）**：这 7 行确实在写盘前被拒，但原因是**应用模式选择**而非围栏：
   补丁是"仅类定义"的整文件（`class Node:` + 4 个方法、0 个顶层 def），
   `_is_full_file_patch` 返回 False → 单函数模式取到第一个 `def`（类方法）
   → `_find_function_range_ast` 只扫顶层 def → 定位失败 → `applied=False`。
   离线复现（以 `task_metadata.fixed` 为原码）：`apply_patch_to_code(fixed, normalize(patch))`
   → `ok=False`。**与围栏无关**。

**围栏残留的真实危害边界**：只在**测量层**（ADR-0021 已修）。证据：main_batch 工件
274 行的 `patch_correct` 全为 0（旧测量层在未清理文本上跑 gold 测试），而本机按
ADR-0021 口径重放得 **115/266 = 43.2%**。对本报告关心的"落盘"问题，围栏影响为 0。

## 4. 量化影响上界（证据门的修复损失）

### 4.1 main_batch（S2 = 266，本机 gold 重放，ADR-0021 口径）

| 分组 | 可重放行 | correct | wrong | correct 率 |
|---|---|---|---|---|
| `patch_plausible=1`（已落盘） | 137 | 71 | 66 | 51.8% |
| `patch_plausible=0`（**未落盘**） | 129 | **44** | 85 | **34.1%** |
| 合计 | 266 | 115 | 151 | 43.2% |

- **上界 A（按 M1 修正口径）**：旁路证据门（或把 `PATCH_EVIDENCE_GATE_ENABLE=false` 重跑）
  可回收 **44 行 correct**，repair 43.2% → **59.8%（+16.5pp）**。
- 证据门仍有选择性（34.1% vs 51.8%）——它压制的行确实质量更差，但绝对损失很大。
- **不是**"全部 129 行都可回收"：85 行（65.9%）即使落盘也是错的。

### 4.2 全三组（上界 B）

| 来源 | 计数 |
|---|---|
| r4_batches + e6_a1_batches：`patch_plausible=0 ∧ patch_correct=1`（工件自带测量层口径） | **88** |
| main_batch：本机重放的 44 行 | **44** |
| **全球上界（不重叠）** | **132 行** |

口径边界（诚实声明）：
- `patch_correct=1` 是 **M1 gold 独立裁决**（repair 度量），**不等于**任务级 `passed`；
  132 行是"修复度量可回收行数"上界，不是"端到端成功率可回收行数"上界；
- 旁路证据门会同时放行"错误但 plausible"的补丁（main_batch 85 行、全球比例更高），
  其 **false_fix / IDR / 回归** 代价本报告未量化（需 A/B 重跑，属实验设计范围）；
- 因此本报告的定位是"**证据门当前代价的量化上界**"，而非"应当关掉证据门"的建议。

## 5. 与预期不符的发现（7 条）

1. **122 → 129/130**：原数字混用了 274 与 266 两个分母（详见 §1）。
2. **主因是证据门而不是围栏**：任务书的核心假设指向围栏残留，实测 98.0% 是
   `PATCH_EVIDENCE_GATE_ENABLE` 的回滚（该开关 2026-10-05 起由"标记制"改为"真阻断"，
   恰好在 main_batch 后 7 个批次（10-06/10-07）生效 → 未落盘行集中在这些批次）。
3. **`error_category=patch_validation_failed` 是误导标签**（129/130 行）：派生自
   `patch_applied is False`（`src/agents/error_classifier.py:1288`），而其中 129 行的
   真实原因是证据门回滚。任何用该字段做"补丁质量"归因的分析都会错。
4. **`stop_reason=skip_debugger_repair_invalid` 是后果不是原因**（124 行）：
   证据门把 `written` 置 False → `repair_history[-1].patch_applied=False`
   → `src/graph/workflow.py:734` 的 `_recent_repairs_invalid` 在第 2 轮早退。
   经 `src/observability/failure_taxonomy.py:75` 该 reason 被映射为
   `GENERATION_CAPABILITY_FAILURE`（模型能力失败）——**门禁策略问题被归因成模型能力问题**。
5. **多出一个独立 bug（C2，7 行）**："仅类定义"的整文件补丁永远无法应用
   （`quixbugs__node` × 7 个批次各 1 行）。这是一个与围栏/证据门无关的修复引擎缺口。
6. **ADR-0021 的 103/266 与本次复算 115/266 有 12 行差异**：ADR-0021 之后落地的
   R27 跨文件物化修复（`experiments/repair_replay.py` 注释所述"第三起测量伪影"）
   把跨文件行从系统性 0 分纠正回来——266 行中 46 行为跨文件，其中 17 行 correct。
   若按修复前口径把这些行记 0，则约 98/266，量级与 103 吻合。**引用 ADR-0021 的
   38.7% 时应同时给出本机 43.2% 并标注代码版本。**
7. **工件内 `patch_correct` 仍是旧口径**：main_batch 274 行全为 0，任何直接消费
   工件 `patch_correct` 的分析都会重演"repair=0"的错误结论（这正是本 task 要修的
   回灌问题的另一半）。

## 6. 可执行的修复建议（含 file:line 落点；均属其他成员/lead 收口范围）

| # | 优先级 | 建议 | 落点 |
|---|---|---|---|
| R1 | P0 | 把"证据门回滚"与"补丁不可用"拆成两个可观测键（如 `patch_write_blocked_reason ∈ {evidence_gate, static_guard, apply_failed}`），当前两者共用 `patch_applied=False`，是 122/129 行只能反推的根因 | `src/graph/nodes.py:1822`（写盘）、`:1842`（证据门分支）、`:1881`（repair_history 追加） |
| R2 | P0 → **已落地** | `PATCH_EVIDENCE_GATE_ENABLE` 本身必须入 `_env_snapshot_keys`——它正是决定 129 行是否落盘的开关。**该建议已被其他成员在本次审查中采纳**（快照 39→50 键，见 `review_2026/E2_env_snapshot_report.md` §9） | `experiments/run_benchmark.py:2731`（快照清单）+ `src/tools/patch_evidence.py:58` |
| R3 | P0 | `patch_plausible` 语义分裂：应同时透出"写盘成功"（现状）与"文本合法可应用"（本工具的 `patch_wellformed`），避免 266/144/122 这类分母混用 | `experiments/run_benchmark.py:601 _patch_plausible` |
| R4 | P1 | `error_category` 派生规则细化：证据门回滚不应落到 `PATCH_VALIDATION_FAILED`（该枚举文案为"补丁被安全守卫拒绝"） | `src/agents/error_classifier.py:1288`、枚举文案 `:69-70`、`:1087` |
| R5 | P1 | 修复 C2：`_is_full_file_patch` 增加"补丁含 class 定义 ∧ 原代码含同名 class"判据；`_find_function_range_ast` 旁增 `_find_class_range_ast`（类体整文件替换） | `src/tools/patch_applier.py:116`、`:148`、`:280-285` |
| R6 | P1 | 证据门策略分档（需 A/B 信号支持）：对"应用成功 + 未改动函数签名/契约"的补丁保留写盘并标记 unverified，而不是直接回滚 | `src/graph/nodes.py:1842`、`src/tools/patch_evidence.py:191` |
| R7 | P2 | 跨文件行被拒率 2.4× —— 排查证据等级（sbfl/gold）在跨文件任务的可得性 | `src/tools/patch_evidence.py`（等级判定） |

## 7. 复现命令

```bash
# 1) 未落盘逐行清单 + 形态分布（只读，产物 review_2026/E2_fence_recompute.json 的 not_written_rows）
.venv/bin/python scripts/tools/refresh_patch_field.py

# 2) main_batch gold 重放（零 LLM，ADR-0021 口径；本次 274 行 ≈ 2.5 分钟）
.venv/bin/python -m experiments.repair_replay experiments/results/main_batch/ --arm aitester --out /tmp/replay.md

# 3) 关键事实核查（只读）
grep -n "if written:" -A 5 src/graph/nodes.py            # 证据门在写盘成功分支内
grep -n "return level in" src/tools/patch_evidence.py     # 仅 gold/sbfl 放行
grep -n "patch_rejected = any" src/agents/error_classifier.py  # 派生标签
```

## 8. 边界与已知不确定

1. `repair_history` 未透出结果行，C1/C2 的归因靠 `patch_evidence_level` +
   代码版本 + 写盘分支位置**反推**；R1 落地后可直接用显式键验证；
2. 402 行中 76 行（含 main_batch 的 1 行）无 gold 材料，无法裁决 correct；
3. e6/r4 的 88 行上界依赖工件自带的 `patch_correct`（测量层已按 ADR-0021 修正），
   未逐行重放；
4. 本报告**未**修改任何 `src/`、`experiments/`、`tests/` 文件；批次工件字节未变
   （`review_2026/E2_fence_recompute.md` §4 的 SHA256SUMS 对账：**全部 30 个批次文件
   逐个 ✅ 与登记值一致**，含 `r4_batches` / `e6_a1_batches` 分组清单）。
