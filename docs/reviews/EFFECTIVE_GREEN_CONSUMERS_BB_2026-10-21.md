# BB 轮：rc==0 判绿消费点的剩余收口——experiments 侧 11 处（2026-10-21，零 LLM）

**范围**：BA 轮（`_suite_has_effective_pass` 四处消费点）之后，对
`experiments/` 全仓普查出的其余 **11 个 pytest 套件判绿点**逐一收口。
所有点共用同一缺陷族（F03 同型）：pytest 对"没有任何断言执行"的套件
同样返回 `rc==0`——全 skip / xfail / xpass / deselect 的摘要行里
`passed==0`，只看 `rc` 会把"没跑起来"计成"有效 green"。

**结论**：11 处全部接入 BA 轮建立的共享谓词
`experiments/_m1_metrics.py::_suite_has_effective_pass`（≥1 个真实
`passed` 且 0 个 `failed`；部分 skip 与真实 passed 并存仍有效；摘要
不可解析判 `False`），无有效通过一律 fail-closed。**60 例新锁 +
11 个变异锚点全红（2/2/2/1/2/2/2/2/2/2/1）+ 中性对照 0 红**；
受影响面子集 245 passed；确认跑 **11317 passed / 5 skipped /
0 failed、243.69s、rc=0**（collected **11322** = 11317 + 5 + 0；
沙箱复跑 11303 passed / 19 skipped / 0 failed，collected 一致）；
`make gates` 全链 rc=0（ruff 937 files formatted、mypy 135 源文件、
零断言 446 测试文件 0 违规、JSON strict 0 违规、双语文档 0 警告）。

---

## 1. 普查方法与判定

普查面：`experiments/` 与 `src/` 全部 `rc == 0` / `returncode == 0`
判绿点（Grep 枚举后逐点读上下文分类）：

| 类 | 判定 | 处置 |
|---|---|---|
| pytest 套件判绿（`rc==0 ⇒ 绿/通过/保留`） | F03 同型缺陷 | **本轮收口** |
| 非套件子进程成功（`git rev-parse` / pip / 补丁应用 / harness 退出码） | 与断言执行无关 | 不动 |
| `compile_exec_metrics` 的 `--collect-only`（`rc==0 ∧ n_nodes>0`） | 已有"收集到节点"证据 | 不动（登记） |
| `misguided_metrics` 三处（`replay_detection` / `replay_fixed_green` / `_verdict_agreement`） | 归档对账语义，BA §7.2 已登记 | **留待专门轮次**（对账标签语义变更需评估归档 mismatch 影响） |
| `src/` 生产路径（`detection_gates` / `executor*` / `testless_validation`） | 生产循环语义 | **留待专门轮次**（默认关或与主循环耦合，需单独回归面） |

## 2. 逐点处置（11 处）

| # | 位置 | 改前行为 | 改后行为 |
|---|---|---|---|
| 1 | `emse_gold_conformance_audit._audit_one` | gold 全 skip → `status="pass"`（"gold 自洽"假证据） | `status="unverifiable"` + reason（fail-closed） |
| 2 | `emse_optimization._rerun_on_fixed` | 全 skip → `passes_on_fixed=True` + `P4_passes_on_fixed` | `None` + `P5_no_effective_pass_on_fixed`（新模式，不折历史 P4） |
| 3 | `gold_consistency_pruning` 块保留 | 全 skip 块 `rc==0` → 保留为"与 gold 一致" | 剔除 + 原因「无有效通过」；整 suite 判据同样收紧 |
| 4 | `emse_testlevel_detection` 任务级判据 | fixed 全 skip → `reproduced=1.0`（注释声称"与 `_compute_detection_rate` 逐字同规则"，BA 后已漂移） | `None`（与 BA 后口径同步；`_fixed_side_effective_pass` 优先用逐测试 outcomes，回退摘要解析） |
| 5 | `emse_ult_gold_diagnosis._parse_pytest` | 全 skip → `status="pass"`，进而归因到具体缺陷类 | `status="unverifiable"`；`attribute_task` 早退 `undecidable_no_effective_pass`（不得把"没跑起来"归因成签名/断言不一致） |
| 6 | `suite_repair_pipeline._runs_green_on` | 全 skip → `True`（见证通过安全门被注入） | `False`（不可判定，不得作为注入依据） |
| 7 | `emse_ult_mutk_full._sanity_gate` | 全 skip → `"pass"` → 进入 Mut@k 测量 | `"unverifiable"` → `_skip("test_no_effective_pass_on_fixed")` |
| 8 | `emse_quixbugs_mutk_full._sanity_gate` | 同上 | 同上 |
| 9 | `emse_test_sanity_audit._run_one` | 全 skip → `pass`（计入 Mut@k 可测集） | `unverifiable`（汇总表新增列，不计入可测集） |
| 10 | `emse_ult_dfsmoke_accuracy._run_one` | 全 skip → `pass` → 抬高 green_on_fut accuracy 分子 | `unverifiable`：不进分子**也不进分母**（与 material_missing 同口径），单独计数披露 |
| 11 | `mutation_testing.compute_mutation_score` 基线 | 全 skip → `pre_existing_failures=1`（误诊"测试没检出缺陷"）+ 所有变异体"存活" → score=0.0 归因测试弱 | `baseline_no_effective_pass=True` 与 `pre_existing_failures` 互斥；score 保守口径不变（不夸大） |

行为不变面（逐位保持）：

- 干净 `rc==0`（≥1 passed、0 failed）→ 全部 11 处原行为不变；
- **部分 skip + 真实 passed** → 仍算有效通过（pruning 的 already_green、
  各门的 pass、P4 的 True 均不变）；
- buggy 侧 rc==0、gold 失败、rc==5 / 超时 / 材料缺失 → 原有 fail-closed
  分支不变；
- 汇总口径（Counter / 分母 / skip_reason 映射）只新增 unverifiable 桶，
  不重排既有桶。

## 3. 真语料测量（只读静态扫描）

| 口径 | 实测 |
|---|---|
| benchmark 归档（`**/benchmark_*.json`） | **246** 份（与 BA 轮同口径） |
| 归档生成测试含**模块级** skip 标记（`allow_module_level=True` / 首块 `@pytest.mark.skip`） | **0** 条 |
| 唯一 gold 套件含模块级 skip 标记 | **0** 份 |

**静态适用面为零**：已归档批次不存在模块级全 skip 套件，因此本轮
fail-closed 分支对**历史归档读数零影响**（不重跑、不回填任何归档）。
机制由第 4 节的合成最小复现与回归锁共同证明；条件性 skip（分支内
`pytest.skip` / `skipif`）不在此列（BA 轮已登记 114/12 条）。

## 4. 回归锁

`tests/test_effective_green_consumers_bb.py`：**60 例**（真实子进程
pytest，零 LLM；与项目既有测试同口径）。

| 类 | 例数 | 覆盖 |
|---|---|---|
| `TestGoldConformanceAudit` | 6 | 干净/部分 skip pass；全 skip/xfail unverifiable；fail 不变；材料缺失不变 |
| `TestOptimizationRerunOnFixed` | 6 | 干净/部分 skip True+P4；全 skip/xfail None+P5；fail False+P1；既有入口 smoke |
| `TestGoldConsistencyPruning` | 5 | already_green 干净/部分 skip；全 skip 不进 already_green；混合块剪枝（rc=1 + 无有效通过两类原因）；全 skip 块不可用 |
| `TestTestlevelEffectivePass` | 5 | outcomes 判据 4 例 + `run_source` 接线源码锁 |
| `TestGoldDiagnosisStatus` | 7 | `_parse_pytest` 5 例（pass/unverifiable×2/fail/collection_error）+ 归因早退 + 既有归因不变 |
| `TestSuiteRepairGreen` | 3 | 干净 True；全 skip/xfail False；fail False |
| `TestSanityGates` | 14 | 四门 ×（pass/unverifiable×2/fail）+ 两处 measure_task skip 映射 + fail 理由不被吞并 |
| `TestMutationTestingBaseline` | 6 | detail 三态 + score 三基线（pre_existing / no_effective_pass / clean） |
| `TestRealCorpusApplicability` | 2 | 归档零模块级 skip（生成测试 + gold 两口径） |

## 5. 变异验证

12 个锚点（11 真实 + 1 中性对照）；逐锚点：读取原字节 → 写入变异 →
`compile()` → 跑受影响面 → sha256 校验后按原字节还原（绝不用
`git checkout` / `git stash`；脚本
`scripts/tools/bb_mutation_verify.py`，带名字过滤参数）。
基线干净副本 **60 passed**；每个变异体运行后源文件 sha256 与原字节
一致（脚本内 assert）。

| 锚点 | 变异 | 红数 |
|---|---|---|
| M1-gold-conformance-guard-off | 守卫改 `if False:` | **2** |
| M2-optimization-p5-off | P5 守卫改 `if False:` | **2** |
| M3-pruning-block-guard-off | 块保留去掉谓词 | **2** |
| M4-testlevel-reproduced-off | 判据改 `elif False:` | **1**（接线源码锁） |
| M5-gold-diagnosis-status-off | status 恒 `"pass"` | **2** |
| M6-suite-repair-green-off | 返回裸 `rc==0` | **2** |
| M7-mutk-sanity-guard-off | 健全性门去谓词 | **2** |
| M8-quixbugs-sanity-guard-off | 同上（QuixBugs 门） | **2** |
| M9-sanity-audit-guard-off | status 恒 `"pass"` | **2** |
| M10-dfsmoke-guard-off | 同上（dfs moke 门） | **2** |
| M11-mutation-baseline-diagnosis-off | 基线诊断改 `if False:` | **1** |
| M12-control-comment-wording | 仅改注释用词（行为不变） | **0（SURVIVED，60 passed）** |

## 6. 边界（不得引用为「全仓所有 rc==0 判定均已收口」）

1. **本轮只收口 experiments 侧 11 处套件判绿点**。`misguided_metrics`
   三处重放对账与 `src/` 生产路径（`detection_gates._run_test_against_code`
   的 `green`、`executor_runtime`/`executor_modes`/`executor` 的
   `passed`、`testless_validation` 两处）仍以裸 `rc==0` 判绿——
   **保留原口径**，需专门轮次评估（对账标签语义 / 生产循环回归面）。
2. **历史归档零回填**：第 3 节实测静态适用面为零，本轮不重跑任何
   LLM 批次、不改写任何归档工件。
3. **`mutation_testing` 的 score 保守口径不变**：all-skip 基线仍得
   0.0（不夸大），只是诊断标签从"测试弱"改为"没跑起来"。
4. **摘要行是判据**：自定义运行器不输出 pytest 摘要时谓词判 `False`
   （fail-closed）——需要测量时必须保留摘要行。
5. **部分 skip 边界**：≥1 真实 passed 且 0 failed 即有效通过；不要求
   "所有测试都通过"，也不把"跳过大多数"伪装成"全部通过"。

## 7. 踩坑与自纠

1. **`_run_suite` 返回类型变更漏掉测试消费点**：为让剪枝判据拿到输出，
   `_run_suite` 从返回 `int`（rc）改为 `(rc, output)` 元组。全量登记前
   一跑因此多红一例——`test_nested_pytest_env_convergence.py::
   test_real_gold_pruning_site_survives_poisoned_host_env` 断言
   `rc == 0`（int）。修正为解包 `(rc, output)` 并补 `"1 passed" in
   output` 断言。**教训（"A06/A07 同型复发）**：改内部函数返回形状时，
   消费点普查必须含 `tests/`——第一轮普查只扫了 `experiments/`+`src/`。
2. **中性对照选择**：M12 初稿改 `rec["reason"]` 文案（中文→英文），
   被 `test_all_skip_gold_suite_unverifiable` 的
   `assert "无有效通过" in rec["reason"]` 抓到——机制名文案是披露
   的一部分、被测试锁定，不是行为中性点。改用**注释用词**变异
   （60 passed，SURVIVED），证明红数来自行为变异而非文本差异。
3. **变异锚点与 `ruff format` 漂移**：M7–M10 首跑锚点失配
   （ANCHOR NOT UNIQUE）——插入的多行条件表达式被 `ruff format`
   重新折行。按折行后实际文本更新锚点后全部转红。
4. **`_sanity_gate` 与 `_run_one` 签名序不同**（前者
   `(fixed, test, module)`、后者 `(module, fixed, test)`），测试侧
   经 lambda 归一，勿在参数序上想当然。

## 8. 复算命令

```bash
# 目标锁（60 collected）
.venv/bin/python -m pytest tests/test_effective_green_consumers_bb.py -q

# 受影响面（含三个有既有测试的模块 + BA 轮同族锁）
.venv/bin/python -m pytest tests/test_effective_green_consumers_bb.py \
  tests/test_emse_optimization.py tests/test_emse_testlevel_detection.py \
  tests/test_emse_ult_gold_diagnosis.py tests/test_mutation_operators_v3.py \
  tests/test_mutation_generator_validity.py tests/test_mutation_advisor.py \
  tests/test_path_c_trigger.py tests/test_effective_green_ba.py -q

# 变异验证（12 锚点；可传名字前缀过滤，如 M1 M7）
.venv/bin/python scripts/tools/bb_mutation_verify.py

# 全量 + 门禁（CI 同口径；不与 make gates 重叠）
make test
make gates
```
