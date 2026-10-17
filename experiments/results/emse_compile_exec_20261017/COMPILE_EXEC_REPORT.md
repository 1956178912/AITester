# A-11 编译率 / 执行率报告（零 LLM 重放）

> **性质**：描述性工程度量（指标 schema 缺口补齐），**非**预注册确认性证据。
> `exec_rate` 只衡量 pytest 可收集/可 import，不衡量测试执行通过率或检出能力。
> **生成时间**：2026-10-17T13:31:34+00:00　**body digest**：`2f6142757710dd8f86caa6a2e3b75ebefd031fd220fed76bce8dd8934bc34e20`
> **工具**：experiments.compile_exec_metrics v1.0.0　**schema**：`compile_exec_metric/1`

复算命令：

```bash
python -m experiments.compile_exec_metrics --out experiments/results/emse_compile_exec_20261017 --jobs 4 --repeat 2
```

## 1. 输入工件（只读）

| 批次 | 轮次 | 工件 | sha256 | 臂 |
|---|---|---|---|---|
| `emse_docstring_anchor_df` | `emse_docstring_anchor_20261017` | `experiments/results/emse_docstring_anchor_20261017/benchmark_quixbugs_20261017_194444.json` | `9405176136db2c2e4e7885ca4e6a7116d1647893c31ddd0b8e76b512f1239672` | `plain_llm_df` |
| `emse_docstring_anchor_doc` | `emse_docstring_anchor_20261017` | `experiments/results/emse_docstring_anchor_20261017/benchmark_quixbugs_20261017_193626.json` | `3e2a69896d308d389bdd35ed5ce38ae532b9accf89109b297391c265696f78b2` | `plain_llm_df_doc` |
| `emse_docstring_anchor_union` | `emse_docstring_anchor_20261017` | `experiments/results/emse_docstring_anchor_20261017/benchmark_quixbugs_20261017_201928.json` | `746090a277cc6a91fa12151aa1a01f4702efc5e4df1289ceb1afc18bf7e842b2` | `plain_llm_df_doc_union` |
| `emse_df_spec_treatment` | `emse_df_spec_20261016` | `experiments/results/emse_df_spec_20261016/benchmark_quixbugs_20261016_232138.json` | `813c437fc53a84c1517cce234b12184e5047bf483fb982cb9382d1c61307245a` | `plain_llm_df_spec` |
| `emse_df_spec_control` | `emse_df_spec_20261016` | `experiments/results/emse_df_spec_20261016/benchmark_quixbugs_20261017_003023.json` | `536da803dbb290dab9dff26ae14302a8ce8d452e058b1d2c4c1705852900d0ec` | `plain_llm_df` |
| `main_batch_seed42` | `main_batch` | `experiments/results/main_batch/benchmark_synthetic_20261006_140906.json` | `6e31c07dd76ce7c356a1f6bef9c011925b07dd653a09547f9a7ae2a2cbdf4aec` | `aitester`、`plain_llm`、`plain_llm_df` |
| `main_batch_seed43` | `main_batch` | `experiments/results/main_batch/benchmark_synthetic_20261006_151907.json` | `bb5fcfc8afebeb5a1859767257f7c7d4d20dd3449e395a489b688a527292f1ae` | `aitester`、`plain_llm`、`plain_llm_df` |
| `main_batch_seed44` | `main_batch` | `experiments/results/main_batch/benchmark_synthetic_20261006_164357.json` | `be6a42e5597a449b498caebd324f604d0beefa02eb8bfe21fda36926aed07e57` | `aitester`、`plain_llm`、`plain_llm_df` |

## 2. 口径定义

- **compile_rate**：ast.parse(generated_test) 成功的行占比；分母 = 全部行 − 空 generated_test（空产物单列，不算编译失败）
- **exec_rate**：物化执行树后 `pytest --collect-only` 可收集（rc==0 且 node>0）的行占比；分母 = 编译成功行 − 材料不可重建行（material_incomplete 单列，不算测试失败）；收集阶段超时（collect_timeout）单列、不进 exec_rate 分母（另给 excl_timeout 口径）
- **执行协议**：pytest --collect-only（仅收集，不执行测试用例：执行错误与失败不属本指标）
- **分母纪律**：每个比率均报分母；空产物 / 材料不完整 / 收集超时三类**不混入** exec_rate 分母，在 reason_counts 与 n_* 字段单列；跨 seed 合并按计数重新计算比率（不做比率平均）
- **外部可比性**：独立评审引 TestAgent 编译率 99.11% / 执行率 97.46%；本项目与其数据集（QuixBugs/synthetic vs 其基准）、语言/工具链、执行定义（collect-only vs 全量运行）均不同——**仅作方向参考，不横向断言优劣**

## 3. 主表（批次 × 臂）

| 批次 | 轮次 | 臂 | n | compile 分母 | compile_rate | exec 分母 | exec_rate | exec_rate(excl. timeout) |
|---|---|---|---|---|---|---|---|---|
| `emse_docstring_anchor_df` | `emse_docstring_anchor_20261017` | `plain_llm_df` | 50 | 50 | 100.00%（50/50） | 50 | 82.00%（41/50） | 82.00%（41/50） |
| `emse_docstring_anchor_doc` | `emse_docstring_anchor_20261017` | `plain_llm_df_doc` | 50 | 50 | 100.00%（50/50） | 50 | 82.00%（41/50） | 82.00%（41/50） |
| `emse_docstring_anchor_union` | `emse_docstring_anchor_20261017` | `plain_llm_df_doc_union` | 50 | 50 | 98.00%（49/50） | 49 | 81.63%（40/49） | 81.63%（40/49） |
| `emse_df_spec_treatment` | `emse_df_spec_20261016` | `plain_llm_df_spec` | 50 | 50 | 100.00%（50/50） | 50 | 82.00%（41/50） | 82.00%（41/50） |
| `emse_df_spec_control` | `emse_df_spec_20261016` | `plain_llm_df` | 50 | 50 | 100.00%（50/50） | 50 | 82.00%（41/50） | 82.00%（41/50） |
| `main_batch_seed42` | `main_batch` | `aitester` | 87 | 81 | 100.00%（81/81） | 65 | 100.00%（65/65） | 100.00%（65/65） |
| `main_batch_seed42` | `main_batch` | `plain_llm` | 87 | 87 | 100.00%（87/87） | 68 | 100.00%（68/68） | 100.00%（68/68） |
| `main_batch_seed42` | `main_batch` | `plain_llm_df` | 87 | 87 | 100.00%（87/87） | 68 | 100.00%（68/68） | 100.00%（68/68） |
| `main_batch_seed43` | `main_batch` | `aitester` | 87 | 79 | 98.73%（78/79） | 67 | 98.51%（66/67） | 98.51%（66/67） |
| `main_batch_seed43` | `main_batch` | `plain_llm` | 87 | 87 | 100.00%（87/87） | 72 | 100.00%（72/72） | 100.00%（72/72） |
| `main_batch_seed43` | `main_batch` | `plain_llm_df` | 87 | 87 | 100.00%（87/87） | 72 | 98.61%（71/72） | 98.61%（71/72） |
| `main_batch_seed44` | `main_batch` | `aitester` | 87 | 80 | 100.00%（80/80） | 63 | 100.00%（63/63） | 100.00%（63/63） |
| `main_batch_seed44` | `main_batch` | `plain_llm` | 87 | 87 | 100.00%（87/87） | 68 | 100.00%（68/68） | 100.00%（68/68） |
| `main_batch_seed44` | `main_batch` | `plain_llm_df` | 87 | 87 | 100.00%（87/87） | 68 | 100.00%（68/68） | 100.00%（68/68） |

说明：compile 分母 = 全部行 − 空 generated_test；exec 分母 = 编译成功行 − 材料不可重建行。

### 3.1 敏感性：排除 QuixBugs *_test 驱动任务（结构性不可收集）

QuixBugs 的 9 个 `*_test` 驱动任务在平铺执行口径下因相对 import 结构性不可收集（与归档 detection=None 同源），主口径计入 exec_rate；下表给出排除后的敏感性（synthetic 批次无 `*_test` 任务，两口径相同）：

| 批次 | 臂 | 驱动任务行数 | compile_rate(excl.) | exec_rate(excl.) |
|---|---|---|---|---|
| `emse_docstring_anchor_df` | `plain_llm_df` | 9 | 100.00%（41/41） | 100.00%（41/41） |
| `emse_docstring_anchor_doc` | `plain_llm_df_doc` | 9 | 100.00%（41/41） | 100.00%（41/41） |
| `emse_docstring_anchor_union` | `plain_llm_df_doc_union` | 9 | 97.56%（40/41） | 100.00%（40/40） |
| `emse_df_spec_treatment` | `plain_llm_df_spec` | 9 | 100.00%（41/41） | 100.00%（41/41） |
| `emse_df_spec_control` | `plain_llm_df` | 9 | 100.00%（41/41） | 100.00%（41/41） |
| `main_batch_seed42` | `aitester` | 0 | 100.00%（81/81） | 100.00%（65/65） |
| `main_batch_seed42` | `plain_llm` | 0 | 100.00%（87/87） | 100.00%（68/68） |
| `main_batch_seed42` | `plain_llm_df` | 0 | 100.00%（87/87） | 100.00%（68/68） |
| `main_batch_seed43` | `aitester` | 0 | 98.73%（78/79） | 98.51%（66/67） |
| `main_batch_seed43` | `plain_llm` | 0 | 100.00%（87/87） | 100.00%（72/72） |
| `main_batch_seed43` | `plain_llm_df` | 0 | 100.00%（87/87） | 98.61%（71/72） |
| `main_batch_seed44` | `aitester` | 0 | 100.00%（80/80） | 100.00%（63/63） |
| `main_batch_seed44` | `plain_llm` | 0 | 100.00%（87/87） | 100.00%（68/68） |
| `main_batch_seed44` | `plain_llm_df` | 0 | 100.00%（87/87） | 100.00%（68/68） |

## 4. 不可执行原因分布

| 批次 | 臂 | `collect_error` | `compile_syntax_error` | `empty_generated_test` | `import_error` | `material_incomplete` |
|---|---|---|---|---|---|---|
| `emse_docstring_anchor_df` | `plain_llm_df` | 0 | 0 | 0 | 9 | 0 |
| `emse_docstring_anchor_doc` | `plain_llm_df_doc` | 0 | 0 | 0 | 9 | 0 |
| `emse_docstring_anchor_union` | `plain_llm_df_doc_union` | 0 | 1 | 0 | 9 | 0 |
| `emse_df_spec_treatment` | `plain_llm_df_spec` | 0 | 0 | 0 | 9 | 0 |
| `emse_df_spec_control` | `plain_llm_df` | 0 | 0 | 0 | 9 | 0 |
| `main_batch_seed42` | `aitester` | 0 | 0 | 6 | 0 | 16 |
| `main_batch_seed42` | `plain_llm` | 0 | 0 | 0 | 0 | 19 |
| `main_batch_seed42` | `plain_llm_df` | 0 | 0 | 0 | 0 | 19 |
| `main_batch_seed43` | `aitester` | 1 | 0 | 8 | 0 | 12 |
| `main_batch_seed43` | `plain_llm` | 0 | 0 | 0 | 0 | 15 |
| `main_batch_seed43` | `plain_llm_df` | 1 | 0 | 0 | 0 | 15 |
| `main_batch_seed44` | `aitester` | 0 | 0 | 7 | 0 | 17 |
| `main_batch_seed44` | `plain_llm` | 0 | 0 | 0 | 0 | 19 |
| `main_batch_seed44` | `plain_llm_df` | 0 | 0 | 0 | 0 | 19 |

## 5. 合并表（轮次 × 臂；跨 seed 按计数重算，不做比率平均）

| 轮次 | 臂 | 批次数 | n | compile_rate | exec_rate | exec_rate(excl. timeout) |
|---|---|---|---|---|---|---|
| `emse_df_spec_20261016` | `plain_llm_df` | 1 | 50 | 100.00%（50/50） | 82.00%（41/50） | 82.00% |
| `emse_df_spec_20261016` | `plain_llm_df_spec` | 1 | 50 | 100.00%（50/50） | 82.00%（41/50） | 82.00% |
| `emse_docstring_anchor_20261017` | `plain_llm_df` | 1 | 50 | 100.00%（50/50） | 82.00%（41/50） | 82.00% |
| `emse_docstring_anchor_20261017` | `plain_llm_df_doc` | 1 | 50 | 100.00%（50/50） | 82.00%（41/50） | 82.00% |
| `emse_docstring_anchor_20261017` | `plain_llm_df_doc_union` | 1 | 50 | 98.00%（49/50） | 81.63%（40/49） | 81.63% |
| `main_batch` | `aitester` | 3 | 261 | 99.58%（239/240） | 99.49%（194/195） | 99.49% |
| `main_batch` | `plain_llm` | 3 | 261 | 100.00%（261/261） | 100.00%（208/208） | 100.00% |
| `main_batch` | `plain_llm_df` | 3 | 261 | 100.00%（261/261） | 99.52%（207/208） | 99.52% |

## 6. 确定性 / 墙钟

- body digest：`2f6142757710dd8f86caa6a2e3b75ebefd031fd220fed76bce8dd8934bc34e20`（不含时间戳/墙钟）
- repeat=2；deterministic=True；各次 digest=['2f6142757710dd8f86caa6a2e3b75ebefd031fd220fed76bce8dd8934bc34e20', '2f6142757710dd8f86caa6a2e3b75ebefd031fd220fed76bce8dd8934bc34e20']
- 本次重放墙钟：184.302 s（只进 run_meta）

## 7. 已知限制

- exec_rate 仅衡量 pytest 可收集/可 import，不衡量测试执行通过率或检出能力（后者见 M1/机制指标）
- main_batch 跨文件 synthetic 行缺伴生模块与目标源码材料（归档 metadata 无 module_*_code、fixed 为空；合成发生器历史缓存漂移不可靠重建）→ material_incomplete 单列、排除 exec 分母，覆盖缺口如实披露
- 单文件 synthetic 行归档无缺陷版源码，目标模块用 gold fixed 代码物化（仅影响 import 解析，不参与判定）
- QuixBugs 9 个 *_test 驱动任务在平铺执行口径下因相对 import 结构性不可收集（与归档 detection=None 同源），作为真实不可执行计入 exec_rate；排除后的敏感性口径见报告 §3.1（四臂均 100%）
- 收集重放失败/超时按原因单列，不并入成功；分类定义不因失败而调整
- 不同批次/臂的生成测试可能依赖宿主 pytest 插件行为；已用 nested_pytest_env 剔除宿主 PYTEST_PLUGINS/PYTEST_ADDOPTS
- 与 TestAgent 数字仅方向参考（数据集/语言/执行定义不同），不做横向断言

