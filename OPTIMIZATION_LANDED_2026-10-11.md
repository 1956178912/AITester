# AITester 优化落地报告（2026-10-11）

> **依据**：三份独立评审 —— [`INDEPENDENT_AUDIT_2026-10-11.md`](INDEPENDENT_AUDIT_2026-10-11.md) / [`EXTERNAL_REVIEW_PACKAGE_AITester.md`](EXTERNAL_REVIEW_PACKAGE_AITester.md) / [`CONSOLIDATED_REVIEW_AND_PLAN.md`](CONSOLIDATED_REVIEW_AND_PLAN.md)
> **执行范围**：P0 门槛条件 + P0 补充 + P1 中的高杠杆项
> **最终状态**：**5487 passed / 3 skipped / 1 xfailed / 0 failed**（203s）· **18/19 门禁绿** · ruff 全绿 · mypy 0 错误

---

## 0. 一句话结论

**本批次没有提升任何指标——它做的是让指标变得可信。** 交付 17 项修复（5 项为新发现），其中最高优先级是**模型版本锁定**：在它完成前，项目其余全部 P0 项的验证结果在逻辑上都不可采信。

---

## 1. 交付清单

### 1.1 门槛条件（**最高优先级**）

| 项 | 交付 | 状态 |
|---|---|---|
| **S29 模型版本锁定** | `provenance.model_fingerprint`（9 字段）+ 新门禁 `scripts/gates/check_model_fingerprint.py` | ✅ 真实 API 验证 `pinned=true` |

**真实 API 验证结果**：
```json
{
  "requested_alias": "deepseek-flash",
  "returned_model": "deepseek-flash",
  "system_fingerprint": "aeb56401ca74e127821c4f9126dcb669",
  "probe_sha256": "fc3d915941b87e39064ba2075b6e2b29fc0de33bd9fd2b046f6857036edefda3",
  "pinned": true, "missing": [], "error": null
}
```
**三次独立调用 `probe_sha256` 逐位一致** → 该哈希可作为可比对性证据。

**过程中发现并修复一个真实缺陷**：探针原 `max_tokens=16` 被模型思维链 token 全部占用（实测 reasoning 56–65 tokens），正文被截断为 `'PRO'` 且 `finish_reason='length'`——**探针恒失败、`pinned` 恒 False、S29 形同虚设**。这是**只有真实调用才能发现**的缺陷（W1 受纪律所限无法发真实请求，故未能自验）。改为 64 后通过。

### 1.2 前提工程

| 项 | 交付 | 关键设计 |
|---|---|---|
| **S2 SWE-bench 管道 fail-fast** | `AITESTER_DATASET_STRICT_INSTANCE_CODE`；true 时剔除兜底任务并记 `strict_skipped_task_ids` | 默认 false **保持历史口径零变化** |

**动机量化**：我扫出 **389 行**（77 个工件文件）**同时缺 `instance_code` 与 `detection_rate`**——该项目从未产出过一行可用的真实仓库检出数据。

### 1.3 死代码与根因修复

| 项 | 交付 | 验证 |
|---|---|---|
| **T2 顶层 JSON 数组解析** | 新增 `extract_json_array()`，接入对抗性推理（3.1）与原子化预言 | **n_intents: 0 → 3**；`oracle_enhanced: False → True` |
| **T1 逻辑驱动文法契约** | planner 提示新增 BNF + 5 正例 + 5 反例 + 输出前自检；`spec_ir_v2` 新增 8 类拒绝原因 + `spec_reject_reasons()`，全链透出到结果行 | 提示与编译器**单一事实源**（白名单由 `spec_expr_grammar_terminals()` 渲染） |
| **T7 type_repair 注入路径** | 仅在确实存在围栏时剥离 markdown | fenced → 成功；unfenced → 原样透传（契约不变） |

**T2 的份量**：真实 LLM 输出的假设质量很高——
> `"当 b 为 0 时函数返回整数 0 而非 float，导致返回类型不一致…"`

但被解析器**全部丢弃**。修复前这两处功能**从设计上永不生效**。

### 1.4 统计口径与出口诚实性

| 项 | 交付 |
|---|---|
| **S13 聚类稳健统计** | `build_cluster_map()` / `cluster_robust_paired_test()` / `--cluster-robust`（默认关） |
| **S11 token 记账健全性** | ≥50% 行无记账 → 成本列 `NOT_COMPUTABLE`（此前静默输出数字） |
| **T6 MDO 池饱和出口拦截** | `status="provisional_pool"`；`as_dict()` 关数字出口 + `mdo_raw` 审计字段 |
| **S7 门禁收紧** | 基线余量 `+5` → `skipped+xfailed+1` |

**S13 的独立验证**：`build_cluster_map(87, 42)` = **26 簇**，规模分布 `1×5 / 2×7 / 3×4 / 4×5 / 5×1 / 6×1 / 7×1 / 9×2` —— 与我审查阶段的独立计算**逐位一致**。真实工件复算：δ=−0.2605、95% CI [−0.3745,−0.1465]、符号 p=0.0003、Cliff's δ=−0.6923，与评审的 −24.6pp / [−33.7,−15.6] 同向同量级。

**历史可比性硬证据**：开关开/关两份报告剥掉新增节 + 复算行 + 时间戳后 **227 vs 227 逐行完全相同**。

### 1.5 撤回错误归因（**T5**）

`BASELINE.yaml` 的"过红是 −28pp 主机制"**已撤回**，替换为双重复核证据：

1. **门与检出同源**：450 个非 None verdict 上 `specific_red→det=1` **206/206**、`over_red→det=0` **244/244**，**真实分歧 0**（确定性互补——用检出解释检出）；
2. **比例随子集不稳**：10 文件全量 0.61/1.16 ↔ 前 7 文件 0.50/1.00，且 84–93% 行无 verdict。

**真实主机制**：测试生成侧不产红 —— aitester **296/609 = 48.6%** 行全绿未检出（每行含均值 **15.3** 条 assert，**不是没写断言，是断言全过**），df 仅 2.5%。

### 1.6 基线刷新（**F12 勘误**）

| 字段 | 旧值 | 新值 |
|---|---|---|
| `tests.total_passed` | 5389（注释写 5323，实测 5390 —— **三值互斥**） | **5487** |
| `suite_seconds` | 35 | 203 |
| `last_verified` | 2026-10-09 | 2026-10-11 |

新增测试 **94 例**（`test_model_fingerprint` 27 + `test_spec_contract_grammar` 31 + `test_cluster_robust_stats` 37），**全部零真实 LLM 调用**。

---

## 2. 执行纪律

| 纪律 | 落实 |
|---|---|
| 写权限隔离 | 3 个并行工程师 + Lead，**文件级不重叠**；禁改清单显式下发 |
| 零真实 LLM 调用（teammate） | 全部用 mock/stub；真实调用仅由 Lead 执行并计费 |
| 每步验证 | 每个改动后跑定向测试 + ruff + mypy；收尾跑全量 |
| 不覆盖他人改动 | 显式禁止回滚他人文件；冲突升级到 Lead 裁决 |
| 两次真实发现的缺陷 | S29 探针 `max_tokens`（Lead 真实调用发现）+ `check_model_fingerprint` 范围错误（Lead 门禁全跑发现） |

**Lead 的三次裁决**（均有据）：
1. **MDO 饱和拦截放哪**：W3 报告"严格执行 C 会让 5 个既有测试红"。裁定 → **拦截放在 `as_dict()` 序列化边界**，属性层不变（5 处断言继续绿、判别逻辑测试零改动），而非改测试。后续 W3 又发现第 6 处（池仅 2 的 fixture），追加四条并列断言既守原意图又守新语义。
2. **`mdo_raw` 能否穿过工件**：核实 `_compute_mdo_for_baseline` 是**逐键显式复制**，`as_dict()` 新键不会自动进 payload → 指派 W1 补三处键集合同构。
3. **门禁永久红灯**：`check_model_fingerprint` 默认扫描面把派生分析产物判红、"无新批次"也阻断 → 裁定收窄扫描面 + 空扫描面放行（S29 只要求**新批次**已锁定，对指纹功能上线前的历史批次要求 `pinned=true` 是范畴错误）。

---

## 3. 最终验证

### 3.1 测试

```
$ .venv/bin/python -m pytest tests/ -q
====== 5487 passed, 3 skipped, 1 xfailed, 4 warnings in 203.22s ======
```
（`--collect-only` 收集 5491；5491 − 3 skipped − 1 xfailed = 5487 ✅ 恒等式成立）

### 3.2 门禁 18/19 绿

```
OK  check_artifacts_tracked      OK  check_baseline               OK  check_baseline_numbers
OK  check_bilingual_docs         OK  check_branch_coverage        OK  check_citations
OK  check_credential_scrub       OK  check_dependency_exemptions  OK  check_docs_history_drift
OK  check_env_budget             OK  check_env_snapshot_keys      OK  check_llm_configs_schema
OK  check_lock_sync              OK  check_model_fingerprint      OK  check_perf_regression
OK  check_state_contract         OK  check_tool_versions          OK  check_zero_assert_tests
FAIL check_swe_bench_pro_ready  ← 数据前置校验（设计即如此）
```

**关于那 1 个未绿**：`check_swe_bench_pro_ready` 的 docstring 自述是"**独立入口**（供实验流程在执行前确认数据就绪）"，即**数据前置校验**而非代码门禁；本地无 SWE-bench Pro 数据集，且**未接入 CI**。这属**范围正确**而非故障。

### 3.3 静态检查

```
ruff check src/ config.py experiments/ tests/ scripts/   → All checks passed!
ruff format --check (491 files)                          → 491 files already formatted
mypy src/ config.py                                      → Success: no issues found in 125 source files
```

---

## 4. 本轮修复的审查发现（对照表）

| 审查编号 | 问题 | 状态 |
|---|---|---|
| **F13 / S29** ⭐ | 模型版本未锁定（同别名 12.5 倍漂移） | ✅ 修复 + 真实 API 验证 |
| **F4 / S2 / K6** | SWE-bench 389/389 行无 `instance_code` | ✅ fail-fast 闸门（数据补齐仍需人工） |
| **F12 / S7** | 基线三值互斥 + 守卫放行 | ✅ 刷新 + 守卫收紧 |
| **F14 / T1** | 逻辑驱动失效根因（提示-文法契约） | ✅ 文法契约 + 归因透出 |
| **F15 / T2** | 对抗性调试死代码（数组永不解析） | ✅ 修复 + 回归锁 |
| **F2 / S13** | 聚类口径缺失（精确度高估 3.35×） | ✅ 聚类稳健统计 |
| **F9 / S11** | token 记账整臂为零仍输出成本 | ✅ `NOT_COMPUTABLE` |
| **F16** | 主机制误归因（过红） | ✅ 撤回 + BASELINE 更正 |
| **F11 / S8** | 零断言门禁红 | ✅ 2 例补断言 |
| T6 | MDO 池未达下限仍给数字 | ✅ 出口拦截 |
| T7 | type_repair 注入路径拒绝带围栏代码 | ✅ 修复 |
| — | 门禁范围错误（永久红灯） | ✅ 收窄（Lead 发现） |
| — | 探针 `max_tokens` 过小（S29 形同虚设） | ✅ 修复（Lead 真实调用发现） |

---

## 5. 未完成项（**明确边界**）

| # | 项 | 为何未做 | 需要什么 |
|---|---|---|---|
| 1 | **SWE-bench 端到端复跑**（S2 后半） | 需 enrichment JSONL + 仓库克隆；`swe_bench_lite_instances.jsonl` 仍 **0 字节** | 用户提供 `~/swe_repos` 或授权拉取 |
| 2 | **ULT 标定集跑批**（路径 A1，唯一有前沿对话资格的资产） | 需 ULT 数据（许可未澄清，上游 The Stack v2 gated） | 许可决策 |
| 3 | **S3 验证 oracle 独立化** | 需仓库级既有测试套件回归能力，依赖 #1 | #1 完成 |
| 4 | **S4 test-hacking 扩展测试侧** | 本轮 P0 已达容量上限；未动 `patch_test_hacking.py` | 下一批 |
| 5 | **S23 对外定位重构** | 属决策项（`ADR-0016` 已做一半），需项目方拍板 Q1 | 用户决策 |
| 6 | **历史批次回填指纹** | 不可能——历史批次跑在指纹功能之前 | 无（已在门禁中显式区分新/旧） |
| 7 | **`_independent_audit/` 的 ruff 噪音** | 审查资产含独立脚本，`ruff check .` 报 418 错**全部来自未跟踪的审查目录** | 提交前把审查目录加入 `extend-exclude` 或移出仓库 |

---

## 6. 下一步建议（严格顺序）

```
① 用户决策 Q1（对外定位）→ 决定 S23 口径
        ↓
② 提供 SWE-bench enrichment 数据 → 跑通 S2 后半 → 才能做 S3
        ↓
③ ULT 许可决策 → 路径 A1（MDO 在真实 Python 函数上落数）
        ↓
④ 用已接线的 spec_reject_reasons 跑一轮真实批次
   → 首次把"47.6% 为 0"拆成 natural_language / unknown_name / unsupported_operator
   → 据此决定"修提示 vs 扩文法"（T1 的下一步）
        ↓
⑤ 下一批 P0：S4 test-hacking 测试侧 + S17 文件拆分 + S16 mypy 严格化
```

**关于 ④ 的说明**：本轮已把归因通道**全链打通**（planner → spec_ir_v2 → state → 结果行），但**尚未用真实批次产出分布**——这需要一次真实跑批（约 $1 量级）。**这是当前投入产出比最高的一次实验**：它能把"逻辑驱动为何失效"从定性根因变成定量分布，直接指导下一步该修提示还是扩文法。

---

## 7. 交付物索引

| 文件 | 内容 |
|---|---|
| [`INDEPENDENT_AUDIT_2026-10-11.md`](INDEPENDENT_AUDIT_2026-10-11.md) | 独立审查主报告（1246 行，15 条关键发现） |
| [`EXTERNAL_REVIEW_PACKAGE_AITester.md`](EXTERNAL_REVIEW_PACKAGE_AITester.md) | 外部评审自包含版（901 行） |
| [`CONSOLIDATED_REVIEW_AND_PLAN.md`](CONSOLIDATED_REVIEW_AND_PLAN.md) | 三份评审整合 + 改进方案（420 行） |
| [`_independent_audit/`](_independent_audit/) | 前沿一手来源重建 / 指标重算 / 代码审计 / 真实 LLM 测试 / 付费覆盖审计 |
| `CHANGELOG.md` + `CHANGELOG.en.md` | 本批次条目（双语） |
| `BASELINE.yaml` | 已刷新（5487 / 203s / 2026-10-11） |
