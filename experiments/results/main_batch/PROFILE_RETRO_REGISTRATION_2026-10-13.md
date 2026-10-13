# AITESTER_PROFILE 存量三批次补登记说明（2026-10-13，T-05 收口）

> 对应独立评审 v2 §3.1 C-07 / §3.3 配置完整性缺口 / §10 T-05：
> R-P0-2 三种子主批次（git `b533cff1`，2026-10-06 14:09–16:43 实跑）
> 的 `provenance.env_snapshot` **无 `AITESTER_PROFILE` 键**、
> `provenance.profile` 字段为 None——统计报告自称"profile 生效证据在
> env_snapshot 内"与工件不符（该字段的写入逻辑于同日 AB2 批次才落地，
> 见 `experiments/run_benchmark.py:3510-3514` 与快照键白名单
> `:3322`）。本文件为存量三批次的补登记，使"主配置 = logic 档"这一
> 口径具备可审计的证据链。

## 1. 工件事实（2026-10-13 逐位核查）

| 批次文件 | git_sha | env_snapshot 键数 | AITESTER_PROFILE | provenance.profile |
|---|---|---|---|---|
| `benchmark_synthetic_20261006_140906.json` | b533cff1 | 32 | **缺失** | None |
| `benchmark_synthetic_20261006_151907.json` | b533cff1 | 32 | **缺失** | None |
| `benchmark_synthetic_20261006_164357.json` | b533cff1 | 32 | **缺失** | None |
| `benchmark_synthetic_20261007_161053.json`（对照） | d3c3cc4 | 33 | `logic` | `logic` |

## 2. 补登记证据链（三线独立）

**线 1 —— 工件内预设开关组合（直接证据，部分覆盖）**：
三批次 env_snapshot 中在场的 logic 档预设开关**全部为 true**：

| 键 | 值 | 所属预设 |
|---|---|---|
| `SPEC_IR_ENABLE` | true | scientific/logic |
| `LOGIC_SPEC_STRICT_ENABLE` | true | logic 独有 |
| `DETECTION_FIRST_ENABLE` | true | logic 独有 |
| `BRANCH_COVERAGE_INJECT_ENABLE` | true | logic 独有 |

其中 `LOGIC_SPEC_STRICT_ENABLE` / `DETECTION_FIRST_ENABLE` /
`BRANCH_COVERAGE_INJECT_ENABLE` 为 logic 档独有注入（safe 档不含），
三者同时为 true 与"logic 档生效"一致，且与任何其他档位（safe /
scientific / fast）的预设组合**不兼容**。

**线 2 —— 预注册与统计报告的配置声明（文档证据）**：
`docs/preregistration.md` 的跑批命令（E2/主批次口径）与
`experiments/results/main_batch/statistical_report_3seed_pooled.md:8`
均记载主配置为 `AITESTER_PROFILE=logic` × `TEMPERATURE=0.0` ×
`BENCHMARK_PARALLELISM=4`。

**线 3 —— 后续批次的正向对照（机制证据）**：同一跑批脚本在
`d3c3cc4` 起写出 `provenance.profile="logic"` 与
`env_snapshot["AITESTER_PROFILE"]="logic"`（2026-10-07 四批次、
E6/A1 全部批次逐位一致），证明"logic 档主批次"的配置声明与工件
记录在修复后完全对齐——存量三批次缺失的只是**记录**，不是**配置**。

## 3. 诚实边界（不可声明为工件完备证明）

- `b533cff1` 的快照白名单仅 32 键，logic 档 18 个预设开关中**14 个
  不在白名单**（`SPEC_IR_DSL_ENABLE` / `SPEC_SMT_ENABLE` /
  `SPEC_ORACLE_EXEC_ENABLE` / `ENABLE_MUTATION_SCORING` /
  `ORACLE_VALIDATE_ENABLE` / `PATCH_SNAPSHOT_ROLLBACK_ENABLE` /
  `PATCH_ROLLBACK_FAIL_CLOSED` / `DETERMINISTIC_GUARD_ENABLE` /
  `ROUTE_STRUCTURED_ENABLE` / `LOGIC_SPEC_STRICT_FALLBACK_ENABLE` /
  `DETECTION_SPECIFICITY_GATE_ENABLE` / `RED_REGRESSION_GATE_ENABLE` /
  `FL_SPECTRAL_ENABLE` / `MUTATION_ADVISOR_ENABLE`）——这些键的
  **缺失不等于关闭**（只是未登记），其实际值无法从存量工件恢复；
- 同理，safe 档判别键（`KERNEL_SANDBOX_ENABLE` 等）的缺失也不能
  反证"非 safe 档"；线 1 的排除力来自 **logic 独有键在场且为
  true**（正向命中），而非其他档键缺席；
- 因此本补登记的强度表述为：**"logic 档生效"获三线独立证据支持
  （含工件内 logic 独有开关组合），但不构成逐开关的工件完备
  证明**；EMSE 论文复现包中，该三批次应以"profile=logic
  （补登记，2026-10-13）"标注，并链接本文件。

## 4. 向前收口（防复发）

- `experiments/run_benchmark.py`：`provenance.profile = ACTIVE_PROFILE`
  （显式字段）+ `AITESTER_PROFILE` 入快照白名单——双重记录；
- 守卫测试：`tests/test_ab_batch.py::TestAB2ProvenanceProfile`
  （源文本契约断言，快照键必须含 profile 原文）；
- 复算验证（3-5 任务小批，确认新工件双字段在场）：待用户确认
  LLM 预算后执行（见 EMSE 优化报告 §7 待办）。
