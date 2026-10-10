# 测试套件索引（tests/）

> **本目录刻意保持平铺**（无子目录）。这是既有约定，不是遗漏：`pyproject.toml` 的
> `[tool.pytest.ini_options]` 用 `testpaths = ["tests"]` + `python_files = ["test_*.py"]`
> 直接收集顶层用例，`conftest.py` / `__init__.py` 亦在顶层。拆分子目录会同时牵动
> 收集口径、覆盖率棘轮（`docs/coverage_ratchet.yaml`）与多处文档引用，收益不抵风险。
>
> 本文档是**索引**：解决"253 个用例文件按引入批次命名、无法按能力检索"的问题。
> 配套：[../pyproject.toml](../pyproject.toml)（pytest 配置）、[../Makefile](../Makefile)（测试入口）。

## 一、运行方式

```bash
make test                 # 全量（xdist -n 4 loadfile，CI 同口径）
make test-cov             # 全量 + 覆盖率（CI 同口径）
pytest tests/test_spec_refine.py          # 单文件
pytest -k spec_refine                     # 按名称匹配
pytest -m unit                            # 按 marker 分层（slow / integration / unit）
```

约定（`pyproject.toml` 声明，改动前请先读）：

- `addopts = "-v --tb=short --timeout=1200 --strict-markers"` —— **`--strict-markers`
  生效**：使用未在 `markers` 中声明的 marker（如 `@pytest.mark.slowtest` 拼写错误）
  会直接报错，而不是被静默忽略；
- `timeout = 1200`（单用例 20 分钟上限）。

## 二、命名家族：为什么文件名看不出测什么

文件名按**引入时间/批次**命名，不按被测能力命名，因此分三个家族：

### 家族 A：批次字母（22 个）—— 历次审查/优化批次的回归锁定

| 文件 | 批次 |
|---|---|
| `test_w_batch.py` | W 批次（2026-10-05 审查优化落地）回归测试 |
| `test_x_batch.py` | X 批次（2026-10-05 第七轮审查落地）回归测试 |
| `test_y_batch.py` | Y 批次（2026-10-05 X 批次冒烟验证后的补遗）回归测试 |
| `test_z_batch.py` | Z 批次（2026-10-06 系统性审查落地）回归测试 |
| `test_aa_batch.py` | AA 批次（2026-10-06 代码优化落地）回归测试 |
| `test_ab_batch.py` | AB 批次（2026-10-06 生死实验根因修复）测试 |
| `test_ac_batch.py` | AC 批次（2026-10-06 第十轮审查落地） |
| `test_ad_batch.py` | AD 批次（2026-10-06 输出成本控制） |
| `test_ae_batch.py` | AE 批次（2026-10-06 第十一轮审查落地） |
| `test_af_batch.py` | AF 批次（2026-10-06 第十一轮审查第二轮自主收口） |
| `test_ag_batch.py` | AG 批次（2026-10-06 第十一轮第三轮自主收口） |
| `test_ai_batch.py` | AI 批次（2026-10-06 第十一轮审查漏配审计落地） |
| `test_aj_batch.py` | AJ 批次（2026-10-06 E4 数据前置 + 三实验就绪命令预置） |
| `test_ak_batch.py` | AK 批次（2026-10-06 第十二轮审查落地） |
| `test_al_batch.py` | AL 批次（2026-10-06 第十三轮审查落地） |
| `test_am_batch.py` | AM 批次（2026-10-06 第十三轮审查落地续） |
| `test_an_batch.py` | AN 批次（2026-10-07 第十四轮审查落地） |
| `test_ao_batch.py` | AO 批次（2026-10-07 第十五轮审查落地）锁定测试 |
| `test_ap_batch.py` | AP 批次（2026-10-07 第十五轮审查续）锁定测试 |
| `test_aq_batch.py` | AQ 批次（2026-10-07 第十五轮审查续二）锁定测试 |
| `test_ar_batch.py` | AR 批次（2026-10-07 第十五轮审查续三）锁定测试 |
| `test_as_batch.py` | AS 批次（2026-10-07 第十五轮审查续四）锁定测试 |

> 注：`test_ah_batch.py` 不存在（字母 AH 未使用）——批次字母非连续，不要据字母推断数量。

### 家族 B：日期/轮次编码（11 个）

| 文件 | 覆盖主题 |
|---|---|
| `test_2026_09_26_review_optimizations.py` | 2026-09-26 全面审查与保守优化轮（默认行为不变） |
| `test_2026_09_26_review_round8.py` | 2026-09-26 第八轮全面审查与保守优化 |
| `test_2026_09_26_review_round9.py` | 第 9 轮全面审查与保守优化 |
| `test_2026_09_27_review_round10.py` | 第 10 轮全面审查与保守优化 |
| `test_2026_09_28_agent_reuse_optimizations.py` | Agent 实例复用缓存 + llm_client 开关/目录记忆 |
| `test_new_modules_2026_09_28.py` | CFG 静态分析 + 事件总线 + trace 可视化 |
| `test_round8_contract_ref_findings.py` | 第八轮契约/引用类修复的行为口径锁定 |
| `test_2026_10_05_review_batch.py` | 2026-10-05 审查优化批次（R1a/R1b/R1c/R4b/R11/R15/R16/R17） |
| `test_2026_10_05_review_fixes_batch.py` | 2026-10-05 系统审查修复批次（C6 / W12） |
| `test_2026_10_05_n_batch.py` | 2026-10-05 复审批次 N 系列 |
| `test_2026_10_05_v_batch.py` | 2026-10-05 独立审查优化批次 V 系列 |

### 家族 C：能力语义命名（220 个）

其余用例以被测对象命名（如 `test_spec_refine.py`、`test_process_utils.py`、
`test_temp_dir_hygiene.py`），可直接按文件名检索——**新增用例请沿用本口径**。

## 三、按能力反查测试（推荐做法）

家族 A/B 的文件名不含能力信息，反查请用符号名而非文件名：

```bash
# 改了 src/specs/spec_refine.py 的某个函数，反查谁在锁定它
grep -rl "refine_spec" tests/

# 只知道领域关键词
grep -rl "semantic_cache" tests/
```

## 四、改动 tests/ 前请注意的门禁

| 门禁 | 对 tests/ 的约束 |
|---|---|
| `scripts/gates/check_zero_assert_tests.py` | 禁止**零断言**测试函数（无 `assert`/`assert_*`/`pytest.raises` 等信号）——会让行覆盖率虚高 |
| `scripts/gates/coverage_ratchet.py` + `check_branch_coverage.py` | 覆盖率棘轮与核心模块分支门槛（79% 总 / 85% 核心），删减用例会触发 |
| `scripts/gates/check_state_contract.py` | 状态通道键读写契约（涉及 tests/ 的替换实现） |
| `scripts/gates/audit_log_redaction.py` | 日志脱敏审计 |
| `scripts/gates/check_docs_history_drift.py` | `docs/history/*.md` 中 "N passed" 声明与 `BASELINE.yaml` 的 `tests.total_passed` 对比 |
| `BASELINE.yaml`（`tests:` 节） | 记录 `total_passed` / `total_failed` / `suite_seconds`；增删用例后需刷新，`check_baseline.py --verify` 按 ±2% 容差比对实测 |

## 五、为什么不做文件重命名（2026-10-10 目录治理决议）

曾评估把 253 个用例文件按能力重命名并分目录，**决议不做**，理由：

1. **波及面远超测试本身**（2026-10-10 实测的引用方，非推测）：用例文件名出现在
   `CHANGELOG{,.en}.md`、`README{,.en}.md`、`docs/adr/0015-detection-first-protocol.md`、
   `docs/adr/0016-orchestration-container-repositioning.md`、`docs/DATA_CARD{,.en}.md`、
   `docs/api_reference{,.en}.md`、`.github/workflows/ci.yml`、
   `scripts/gates/check_zero_assert_tests.py`，**甚至 `src/api/api_manager.py` 与
   `src/api/api_health.py` 的注释里**。改名 = 同时改动文档、CI、门禁与源码注释。
2. **证据链风险**：部分批次用例是审查/实验批次的回归锁定入口，被 ADR 与数据卡
   指名引用；改名会让"结论 → 用例"的引用链断裂（与 `check_artifacts_tracked.py`
   所守护的引用链口径同类问题）。
3. **收益可由索引替代**：本文档 + `grep` 符号反查已能解决检索需求，且零引用破坏。

因此本索引是重命名的**替代方案**。若后续确有重命名需求，请单独开批次，并按上文
第 1 条的清单逐项同步引用后再动文件名。
