# A-05 oracle 质量度量工件（emse_oracle_quality_20261017）

> **性质**：M 轮 T7-A（独立评审 §10 A-05 / G6 / D-4）零 LLM 重放的**描述性**
> 机制度量工件。oracle 质量反映确定性规约通道，**不是 LLM 生成能力指标**；
> 非预注册确认性证据，不做显著性推断。

## 1. 输入 sha256（只读消费）

| 输入 | sha256 |
|---|---|
| `experiments/results/emse_df_spec_20261016/benchmark_quixbugs_20261016_232138.json` | `813c437fc53a84c1517cce234b12184e5047bf483fb982cb9382d1c61307245a` |
| `experiments/results/emse_df_spec_20261016/benchmark_quixbugs_20261017_003023.json` | `536da803dbb290dab9dff26ae14302a8ce8d452e058b1d2c4c1705852900d0ec` |
| `experiments/results/emse_spec_anchor_20261016/SPEC_ANCHOR_TABLE.json` | `3e90b2ad5ed365ad5ee989c73c92b84956a83c0fa8cb51368d288ae3ea53bf22`（SHA256SUMS 校验：`experiments/results/emse_spec_anchor_20261016/SHA256SUMS`） |

> 以上输入工件哈希同时以 `../` 相对路径引用行记入同目录 `SHA256SUMS`（`scripts/gates/checksum_results.py --verify` 一并校验；文件内路径条目仅覆盖本目录工件）。

## 2. 复算命令

```bash
python -m experiments.oracle_quality_replay --out experiments/results/emse_oracle_instrument_hardening_20261017 --compare-report experiments/results/emse_oracle_quality_20261017/ORACLE_QUALITY_REPORT.json --jobs 4 --per-test-timeout 1 --file-timeout 240 --repeat 1
```

## 3. 覆盖与分母

- `plain_llm_df_spec`（treatment）：任务行 50，锚命中 50，注入成功 38，可测 oracle 任务 11，可分类 oracle 测试（分母）11，不可分类 27
- `plain_llm_df`（control）：任务行 50，锚命中 50，注入成功 38，可测 oracle 任务 11，可分类 oracle 测试（分母）11，不可分类 27

> 四分类占比分母 = 可分类 oracle 测试数（buggy/fixed 两侧均有 pass/fail）；
> timeout/collect/import/syntax/skipped/test_error/missing_side 单列、不进分母。

## 4. 核心数字（40 缺陷程序口径）

| 指标 | `plain_llm_df_spec` | `plain_llm_df` |
|---|---|---|
| `correct` 计数/占比 | 0 / 0.00% | 0 / 0.00% |
| `fp` 计数/占比 | 2 / 18.18% | 2 / 18.18% |
| `silent` 计数/占比 | 9 / 81.82% | 9 / 81.82% |
| `misguided` 计数/占比 | 0 / 0.00% | 0 / 0.00% |
| detection `archived` | 54.29% | 77.78% |
| detection `llm_only_replay` | 50.00% | 77.50% |
| detection `oracle_augmented_replay` | 44.74% | 71.05% |
| Δ augmented − llm_only（配对 pp） | -2.6316 | -5.2632 |

## 5. 交叉校验（0 mismatch 要求）

- `plain_llm_df_spec`：detection 对账 {'artifact_none': 6, 'both_none': 9, 'match': 35}（mismatch=0）；归档 oracle verdict 复现 {'match': 50}（mismatch=0）；归档字段自洽性违规 0；**all_ok=True**
- `plain_llm_df`：detection 对账 {'artifact_none': 5, 'both_none': 9, 'match': 36}（mismatch=0）；归档 oracle verdict 复现 {'match': 50}（mismatch=0）；归档字段自洽性违规 0；**all_ok=True**

## 6. 确定性 / 墙钟

- body digest：`cc1ab8e1ed4e0e527c82de2c46c98624a644d295b063e9b43a63a99c1b10f2b3`
- repeat=1；deterministic=True；各次 digest=['cc1ab8e1ed4e0e527c82de2c46c98624a644d295b063e9b43a63a99c1b10f2b3']
- 本次重放墙钟：279.862 s（只进 run_meta，不进 body digest）
- **确定性口径**：A-05 repeat=1（单测锁 body 结构；窗口结束后可选补 repeat=2）；A-11 repeat=2 逐位一致。

## 7. O-1 仪器加固前后对照（before/after）

> 对照基线：`experiments/results/emse_oracle_quality_20261017/ORACLE_QUALITY_REPORT.json`（sha256 `0657a81c34b34dc539425b7233c7cca8a9cdd21b8a96b5ba1eb5fc883108024d`）。**仪器治疗 ≠ 检出能力提升**：加固只改变崩溃的记账方式（fp → skipped/unavailable），oracle 断言语义与 correct 语义质量不变。

| 指标 | before | after |
|---|---|---|
| `plain_llm_df_spec` 可分类 oracle 测试数 | 38 | 11 |
| `plain_llm_df_spec` `correct` | 0 | 0 |
| `plain_llm_df_spec` `fp` | 29 | 2 |
| `plain_llm_df_spec` `silent` | 9 | 9 |
| `plain_llm_df_spec` `misguided` | 0 | 0 |
| `plain_llm_df_spec` `fp_assertion_fail`（断言型假阳，保留） | 2 | 2 |
| `plain_llm_df_spec` `instrument_error`（崩溃型假阳，拆出） | 27 | 0 |
| `plain_llm_df_spec` `skipped`（仪器不可用单列，不进分母） | 0 | 27 |
| `plain_llm_df` 可分类 oracle 测试数 | 38 | 11 |
| `plain_llm_df` `correct` | 0 | 0 |
| `plain_llm_df` `fp` | 29 | 2 |
| `plain_llm_df` `silent` | 9 | 9 |
| `plain_llm_df` `misguided` | 0 | 0 |
| `plain_llm_df` `fp_assertion_fail`（断言型假阳，保留） | 2 | 2 |
| `plain_llm_df` `instrument_error`（崩溃型假阳，拆出） | 27 | 0 |
| `plain_llm_df` `skipped`（仪器不可用单列，不进分母） | 0 | 27 |

> before 的 fp = fp_assertion_fail（断言型，保留）+ instrument_error（崩溃型；加固后应转为 skipped/unavailable，由 unclassifiable_counts.skipped 与 skip_reason_counts 观测）

## 8. 已知限制


- 反事实注入口径：锚表材料直接重建 test_plan（无 Planner 现场 spec_ir / boundary_triplets），不声称等同完整 logic 链路生产注入质量
- 归档批次（plain_llm_df*，Planner 关闭）生产注入口未实际尝试注入；本报告质量数字来自零 LLM 重放
- oracle 与 LLM 测试同文件、同 pytest session 执行（生产口径），全局状态污染与收集顺序照旧
- 官方金测试 test_cases 不参与本分类，仅用于任务级 detection 交叉校验口径说明
- 9 个 QuixBugs *_test 驱动任务（相对 import、无金测试）与辅助模块 node 在平铺执行口径下结构性不可 replay → 结构跳过单列；41 口径兼容行（node，buggy==fixed）无缺陷信号，主分析集为 40 口径
- per-test timeout 把挂死 oracle 测试记为不可分类 timeout（不并入四分类），与 M1 判分口径有意不同
- oracle 假阳/误导若因编译器提供的 0 字面量绑定导致（如 TypeError），属确定性通道自身缺陷，由 failure_stats.fixed_side_exception_types 逐类披露，不在本工具内修复
- 描述性对比，不提供显著性推断；两臂差异仅作机制侧方向参考

## 9. 生产独立判读验证（`independent_judging/`，N-3 判分链）

> 用途：验证加固后的 **生产 `_m1_metrics` 独立判读链**（非本工具的混判复算）
> 同样把"崩溃 → skip"记为 unavailable，且 LLM-suite detection 不被仪器加固
> 影响。命令：`--independent-judging --out <本目录>/independent_judging
> --jobs 4 --repeat 1`；墙钟 146.0s，digest `7fcd4dcc…`。

| 指标 | plain_llm_df_spec | plain_llm_df |
|---|---|---|
| LLM-suite detection（40 口径） | **20/40 = 50.00%** | **31/40 = 77.50%** |
| 与 M-2 基线逐位一致（`m2_rates_match`/`all_ok`） | True / True | True / True |
| 逐任务 detection 对账（match/both_none/replay_none/**mismatch**） | 40/9/1/**0** | 40/9/1/**0** |
| `oracle_suite_verdict`（40 口径） | unavailable **29** / fp **2** / silent **9** / correct **0** | 同左 |

- 29 = 27 个崩溃 skip + 2 个未注入任务（flatten / max_sublist_sum 编译为空）；
  fp 仅剩断言型 2 例（与 mixed 重放一致）——生产判分同样**不把 skip 混入
  fp/silent**，N-3 的 `oracle_suite_verdict` 语义在加固后成立。
- **重要修正**：M-2 记录"混判抹掉 14/22 检出"主要成分是**崩溃型 oracle 在
  fixed 侧恒红**（仪器伪影）：加固后混判 lost 降至 **1/2**、augmented 40 口径
  detection 10.53%/18.42% → **44.74%/71.05%**；LLM-suite detection 不变
  （50.00%/77.50%）、correct 仍 0——不是检出提升，是原"净损伤"量级被仪器
  缺陷放大。剩余 lost 1/2 为断言型 fp（语义质量）。
- **仪器治疗 ≠ 检出能力提升**：correct 0→0；可分类分母 38→11（mixed 口径），
  引用占比必须同时给 skipped 数；历史批次（开关默认关）数字不变。

## 10. 残余风险

- harness 只捕获 `Exception` 子类：段错误 / SIGSEGV / BaseException 类故障仍会
  崩（由外层 subprocess 超时与执行错误单列兜底）；
- skip 只把"仪器失效"暴露出来，**不修复**编译器绑定/输入选择缺陷（correct
  仍 0，语义质量治理另立项）；
- 前件校验只覆盖**可机检表达式**前件；NL 前件不可机检（保持注释），候选
  筛选可能因此宽松；
- `src/graph/nodes.py::_spec_oracle_verdict_after_run` 对"oracle 全 skip"轮次仍
  可能记 `injected_and_passed`（nodes 写域归 O-3，本任务未改）——行级
  verdict 与 `oracle_suite_verdict` 冲突时以后者为准（风险登记）；
- before 侧 fp 细分由 M-2 报告 `failure_stats` 推导（该工件无 per-test
  fp_kind 字段），推导规则见报告 `instrument_hardening_comparison`。

