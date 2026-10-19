# 修复覆盖率缺口审计·第二轮（2026-10-19，零 LLM）

> **性质**：Y 轮审计的收口与扩展——补齐 `src/` 剩余缺口中的 A20 守卫，并把同一方法
> 首次应用到 `experiments/`（Y 轮明确披露未覆盖的领域）。
> **花费**：真实 LLM **$0**。
> **结论**：新增 3 组 P1/P2 契约缺口共 8 例回归锁（全部变异验证）；
> `experiments/` 核心库模块已充分锁定，未覆盖集中在 CLI 入口脚本（正常）；
> 另发现 2 个无调用点的死函数。
> **测试基线**：审计前后全量绿（详见 §7）。

## 1. 本轮范围

| 范围 | 依据 | 结果 |
|---|---|---|
| `src/` 剩余缺口 | Y 轮报告 §5「建议下轮补」 | A20 三处守卫补口（3 例） |
| `experiments/` 首次审计 | Y 轮报告 §6「未做的事」第 4 条 | 核心库模块已锁定；发现 A06/A16 三处接线/分支缺口（5 例） |

## 2. 方法扩展

审计工具新增 `--pathspec`，可对任意目录重跑（`src/` 或 `experiments/`）：

```bash
make test-cov                                                    # src 口径
python scripts/tools/audit_fix_coverage.py                       # 默认 src/

COVERAGE_FILE=.coverage.exp python -m pytest tests/ -n 4 \
    --dist loadfile --cov=experiments --cov-report=xml:coverage_exp.xml
python scripts/tools/audit_fix_coverage.py \
    --pathspec experiments/ --coverage-xml coverage_exp.xml
```

注意 `coverage.xml` 的 `filename` 相对 `--cov` 的 source，故 `--pathspec` 同时
用于还原路径前缀——两者必须一致，否则全部行会被判为"未被测量"。

## 3. experiments/ 审计结果

```
基线 ff15a2f → HEAD；experiments/ 修复新增且被 coverage 测量的行 992，
其中未执行 550（55.44%）
```

**55.44% 不是缺陷信号**：该目录包含 6 个 X 轮入库的零 LLM 复算入口脚本
（`emse_dsl_diag3` / `emse_dsl_extend_recheck` / `emse_quixbugs_mutk_full` /
`emse_ult_mutk_full` / `emse_test_sanity_audit` / `emse_ult_dfsmoke_accuracy`），
共 739 行新增、531 行未执行——它们的 `argparse` + `main()` 是薄壳，由
`test_emse_recompute_entrypoints.py` 以**函数级**调用验证，CLI 外壳本就不该被单测覆盖。

真正的库模块全部干净：

| 模块 | 新增 | 未覆盖 | 说明 |
|---|---|---|---|
| `_m1_metrics.py` | 19 | **0** | A08/A16 |
| `_row_pairing.py` | 20 | **0** | A07 单一事实源，三入口共用 |
| `bayesian_paired.py` | 3 | **0** | A07 |
| `spec_examples_generator.py` | 4 | **0** | W 轮 env 泄漏 |
| `solver_directed_trigger.py` / `spec_ambiguity.py` | 1 / 1 | **0** | A08 调用点 |
| `statistical_analysis.py` | 109 | 4 | A06 + A07 |
| `run_benchmark.py` | 73 | 13 | A03 + A16 |

## 4. 已补的三组缺口

### 4.1 A20 三级降级链（`trace.py:147-149 / 260-262 / 469-471`）

A20 的契约是"宁可少一条观测记录，也不写坏行污染整份轨迹"，由三级降级实现：

| 级 | 位置 | 行为 | 原覆盖 |
|---|---|---|---|
| 1 | `_redact_record` | 结构脱敏抛异常 → 原样返回（不阻断写入） | ❌ |
| 2 | `_append` | `json.dumps` 成功但 `json.loads` 失败 → 丢弃该行 | ❌ |
| 3 | `dump_recent_to` | 序列化失败（如 `__str__` 抛异常）→ 跳过该行 | ❌ |

**既有测试名不副实**：`test_dump_with_unserializable_object_does_not_emit_bad_line`
的 `_Weird.__str__` 正常返回字符串，走的是"成功序列化"路径，从未触发丢弃分支。
真正的触发条件是 `__str__` 自己抛异常。

**变异证据**（逐项单独注入，每次仅目标用例变红、其余 17 例全绿）：

| 变异 | 变红用例 |
|---|---|
| `except Exception` → `except ZeroDivisionError` | `test_redact_record_degrades_to_raw_when_masking_raises` |
| 同上（`_append` 处） | `test_append_drops_line_failing_structure_guard` |
| 同上（`dump_recent_to` 处） | `test_dump_skips_record_whose_str_raises` |

### 4.2 A06 生产入口的元数据接线（`statistical_analysis.py:2749-2750`）

A06 的层 1 是"归档 `task_metadata.pattern_name` 程序身份优先于 task_id 查表"。
该逻辑本身有 8 个 `build_cluster_map` 用例覆盖，**但没有任何用例经过生产入口
`cluster_robust_analysis`**——入口里"从行内收集 metadata"的分支零执行。

**后果**：若该收集被破坏，层 1 永不触发，簇统计静默退回 task_id 查表——
正是 A06 修掉的跨 seed 错映射（223/261 行、26 簇、p≈6.6e-05 夸大的显著性），
而全部既有测试仍然全绿。

**变异证据**：把 `if isinstance(metadata, Mapping): task_metadata[str(tid)] = metadata`
改为恒假后，**仅新增 2 例变红，46 个既有用例（含 8 个层 1 逻辑测试）全绿**。

### 4.3 A16 的 flaky 证据消费（`run_benchmark.py:281-287`）

`_apply_execution_flaky_evidence` 在 `flaky_fail_then_pass=True` 时保守记
`test_passed=False` 并写真实 pass/total 计数；非 flaky 时只写 `test_passed`。
既有测试只覆盖了后者（快速返回路径），flaky 分支零执行。

**后果**：single_agent 基线会把"同测试首败次过"记成成功，把执行不稳定抹成
成功证据——A16 要消除的判分偏差原样复活。

**变异证据**：让函数永不进入 flaky 分支后，新增 2 例变红（第 3 例"非 flaky 路径
零变化"仍绿，符合预期——它锁的是另一侧契约）。

## 5. 发现的死代码（记录，未删）

两个函数在**全仓（含测试）无任何调用点**：

| 函数 | 位置 | 推断来源 |
|---|---|---|
| `_strip_seed_prefix` | `statistical_analysis.py:2290-2292` | A06 重构时被 `_split_seed_prefix` 取代 |
| `_rebuilt_task_fingerprints` | `statistical_analysis.py:2327-2333` | A06 重构时被 `_rebuilt_task_table` 取代 |

二者都是无副作用纯函数，删除安全。**本轮未删**（最小改动原则：审计轮不改生产
代码，避免审查面扩散）；建议下轮连同调用点确认后清理。保留的副作用是它们计入
覆盖分母且恒为未覆盖，会让"本次缺口数"虚高 2 行。

## 6. 剩余缺口

| 位置 | 行数 | 性质 | 处置 |
|---|---|---|---|
| `statistical_analysis.py:2747` | 1 | 重复/空 task_id 的 `continue` | 防御分支；如需可构造重复行锁定 |
| `run_benchmark.py:3818-3820` | 3 | provenance marker 读取失败（OSError/UnicodeDecodeError） | 错误处理；建议下轮补（可用不可读文件触发） |
| `run_benchmark.py:3824` | 1 | marker 行不含 `=` 或 key 非 GIT_SHA | 同上 |
| `run_benchmark.py:3862-3863` | 2 | git 调用异常降级 | 同上 |
| CLI 入口脚本 531 行 | — | `argparse` + `main()` 薄壳 | 不补（设计如此） |

## 7. 验证

- 新版回归锁：`tests/test_trace_jsonl_integrity.py`（+3）、
  `tests/test_cluster_robust_stats.py`（+2）、`tests/test_run_benchmark.py`（+3）；
- 每例均经"抹掉目标分支必红"变异验证（见 §4 各表）；
- 全量：见 BASELINE `tests` 节（本轮净增 8 例）；
- 门禁：双语 / 链接 / 零断言 / 工件追踪 / 基线数字 全绿；ruff + mypy 新代码 0 错。

## 8. 结论

1. `experiments/` 侧的**核心库模块已被充分锁定**（`_row_pairing` 20/0 是对 A07
   单一事实源的直接背书），未覆盖集中在 CLI 薄壳，属正常形态。
2. 但**接线点**是系统性的盲区：A06 的层 1、A16 的 flaky 分支都属于"逻辑有测试、
   接线无测试"。这与 A07/A09/A10 的复发模式同源，值得作为下一轮评审的固定检查项。
3. 审计工具已支持双目录，建议每轮修复后对 `src/` 与 `experiments/` 各跑一次。
