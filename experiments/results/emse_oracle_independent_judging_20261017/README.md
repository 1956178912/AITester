# A-05 后续修复：独立判读零 LLM 重放验证（N-3）

> **性质**：N-3 任务的**零 LLM 验证工件**（验证性，不作能力证据/预注册证据）。
> 验证两处生产修复：① `nodes._append_spec_oracle_to_test_with_verdict` 的
> `spec_anchor` 接线（修复 df_spec/doc/union/augment 类臂永远 not_attempted 的缺口）；
> ② `_m1_metrics` 的 LLM-suite / oracle-suite **独立判读**（oracle 失败不再改写 LLM 检出）。
> 对账权威基线 = M-2 `emse_oracle_quality_20261017`（df_spec 50.00% / df 77.50%，40 口径）。

## 1. 输入 sha256（只读消费）

| 输入 | sha256 |
|---|---|
| `experiments/results/emse_df_spec_20261016/benchmark_quixbugs_20261016_232138.json` | `813c437fc53a84c1517cce234b12184e5047bf483fb982cb9382d1c61307245a` |
| `experiments/results/emse_df_spec_20261016/benchmark_quixbugs_20261017_003023.json` | `536da803dbb290dab9dff26ae14302a8ce8d452e058b1d2c4c1705852900d0ec` |
| `experiments/results/emse_spec_anchor_20261016/SPEC_ANCHOR_TABLE.json` | `3e90b2ad5ed365ad5ee989c73c92b84956a83c0fa8cb51368d288ae3ea53bf22` |
| `experiments/results/emse_oracle_quality_20261017/ORACLE_QUALITY_REPORT.json`（M-2 基线报告） | `0657a81c34b34dc539425b7233c7cca8a9cdd21b8a96b5ba1eb5fc883108024d` |

## 2. 复算命令

```bash
python -m experiments.oracle_quality_replay --independent-judging --out experiments/results/emse_oracle_independent_judging_20261017 --jobs 4 --repeat 1
```

## 3. 口径

- **state 形态**：只带 `spec_anchor`（复刻生产 df_spec/doc/union/augment 臂，无 `test_plan`）
  —— 注入成功本身即 N-3 接线修复的生产态证据。
- **LLM-suite detection**：`_m1_metrics._compute_llm_suite_detection_rate`
  （pytest `-k` 排除 `test_specir_v2_oracle` / `test_specir_v2_smt_witness`）。
- **oracle-suite verdict**：`_m1_metrics._compute_oracle_suite_verdict`
  （`-k` 只选 oracle 测试名，独立运行 buggy/fixed 两侧；取值域见报告 metric 段）。
- **M1 判分口径**：`M1_PER_TEST_TIMEOUT=1`s（与 M-2 重放对齐）。

## 4. 核心数字

| 指标 | `plain_llm_df_spec` | `plain_llm_df` |
|---|---|---|
| 锚命中 / 注入成功（anchor-only state） | 50 / 38 | 50 / 38 |
| LLM-suite detection（40 口径） | 20/40 = 50.00% | 31/40 = 77.50% |
| M-2 40 口径基线（对账） | 20/40 = 50.00% | 31/40 = 77.50% |
| 与 M-2 计数一致 | True | True |
| detection 对账 mismatch 数 | 0 | 0 |

oracle-suite 四分类（独立判读；40 口径）：

| 类别 | `plain_llm_df_spec` | `plain_llm_df` |
|---|---|---|
| `correct` | 0 | 0 |
| `fp` | 29 | 29 |
| `silent` | 9 | 9 |
| `misguided` | 0 | 0 |
| `unavailable` | 2 | 2 |

oracle 类别 vs M-2 逐测试分类对账（描述性）：

- `plain_llm_df_spec`：{'both_unavailable': 12, 'match': 38}
- `plain_llm_df`：{'both_unavailable': 12, 'match': 38}

注入 verdict 对账（anchor-only 接线 vs M-2 反事实）：

- `plain_llm_df_spec`：{'same_injected_flag_refined_verdict': 1, 'same_verdict': 49}
- `plain_llm_df`：{'same_injected_flag_refined_verdict': 1, 'same_verdict': 49}

## 5. 确定性 / 墙钟

- body digest：`22ae5d649bdc1692dab767515dbca53625a3a4110d5bcc1bf2ca01e798d40789`（不含时间戳/墙钟）
- repeat=1；deterministic=True；各次 digest=['22ae5d649bdc1692dab767515dbca53625a3a4110d5bcc1bf2ca01e798d40789']
- 本次重放墙钟：167.359 s（只进 run_meta）

## 6. 已知限制

- 反事实注入口径：锚表材料直接重建 test_plan（无 Planner 现场 spec_ir / boundary_triplets），不声称等同完整 logic 链路生产注入质量
- 归档批次（plain_llm_df*，Planner 关闭）生产注入口未实际尝试注入；本报告质量数字来自零 LLM 重放
- oracle 与 LLM 测试同文件、同 pytest session 执行（生产口径），全局状态污染与收集顺序照旧
- 官方金测试 test_cases 不参与本分类，仅用于任务级 detection 交叉校验口径说明
- 9 个 QuixBugs *_test 驱动任务（相对 import、无金测试）与辅助模块 node 在平铺执行口径下结构性不可 replay → 结构跳过单列；41 口径兼容行（node，buggy==fixed）无缺陷信号，主分析集为 40 口径
- per-test timeout 把挂死 oracle 测试记为不可分类 timeout（不并入四分类），与 M1 判分口径有意不同
- oracle 假阳/误导若因编译器提供的 0 字面量绑定导致（如 TypeError），属确定性通道自身缺陷，由 failure_stats.fixed_side_exception_types 逐类披露，不在本工具内修复
- 描述性对比，不提供显著性推断；两臂差异仅作机制侧方向参考
- 独立判读模式的 M1 判分使用生产 _m1_metrics（M1_PER_TEST_TIMEOUT=1s 对齐 M-2 重放）；与 M-2 基线差异逐条归因，未静默平均
- oracle-suite verdict 每任务单值（correct/fp/silent/misguided/unavailable），与 M-2 逐测试四分类的类别差异属预期可比对项（描述性）


## 7. 真 LLM 冒烟（`smoke/`，验证性，**不作证据**）

> 任务书 N-3 §4：df_spec 臂 + `SPEC_ORACLE_EXEC_ENABLE=true` 跑 1 个 QuixBugs
> 任务，验证注入发生、LLM-suite detection 不被 oracle 失败改写、trace/结果行
> 字段齐全。真实 LLM 调用 **1 次**（`token_usage.llm_calls=1`；input 921 /
> output 1502 tokens），模型 deepseek-flash，env：`AITESTER_PROFILE=logic`、
> `TEMPERATURE=0.0`、`LLM_THINKING_MODE=disabled`、
> `AITESTER_CACHE_NAMESPACE=n3_smoke_20261017_2`、`M1_PER_TEST_TIMEOUT=1`；
> API key/base_url **不落盘、不打印**（`grep sk-` = 0 命中）。

| 项 | 结果 |
|---|---|
| task | `quixbugs__find_in_sorted`（df_spec 臂入口 `run_plain_llm_df_spec_baseline` 直接调用，等价 run_benchmark 该臂路径） |
| 注入 | `spec_oracle_injected=true`、`spec_oracle_verdict=injected`；`spec_anchor` 有 `logic_analysis`、`spec_replace_applied=attempted_replaced` |
| oracle 独立判定 | `oracle_suite_verdict=fp`（可测量，非 unavailable） |
| **独立性演示** | 同一生成测试：**LLM-suite detection=1.0，legacy 混判 detection=0.0**（oracle fp 在旧口径下抹掉了 LLM 检出） |
| 结果行字段 | `detection_rate` / `llm_suite_detection_rate` / `oracle_suite_verdict` / `spec_oracle_verdict` 齐全 |
| trace | `execution_trace` 2 条 |
| 检查汇总 | **9/9 通过**（`SMOKE_REPORT.json.checks`，`all_checks_pass=true`） |
| 墙钟 | 13.97s |

产物：`smoke/SMOKE_REPORT.json`（环境白名单/检查项/独立性探针）、
`smoke/ROW.json`（完整结果行）、`smoke/smoke.log`（stdout）、
`smoke/smoke_run.py`（可复现命令的完整源）。
