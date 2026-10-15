# ULT 官方 gold 测试"全败"归因诊断（2026-10-15，零 LLM）

> 输入：`experiments/results/emse_test_sanity_20261015/SANITY_AUDIT.json`（71/71 gold 全败）
> + 上游 `datasets/ULT.jsonl` / `datasets/ULT_Lite.jsonl`（一手核验）。
> 判定：每个任务跑 6 种物化（P/P2/O/C/GP/GO，另按需 C+），pytest 30s 上限，本地执行，无 LLM/网络。

墙钟：506.2s；pytest 9.1.1；Python 3.14.6。

## 0. 结论摘要（先读这节）

- **任务级**：71 个任务中 **1 个**（`ult__fix_labels`）在**官方契约逐字物化（O）下 5/5 通过**——其 gold 失败的 100% 由项目 harness 造成（项目 mod 文件缺官方 `code_import` 前置块 → `re` 未定义）；其余 70 个在官方契约下同样失败。
- **断言级**：355 条 gold 断言中，项目物化口径通过 44 条、失败 311 条；把 harness 纠正到官方契约 + 显式符号绑定后通过 55 条 ⇒ **项目侧造成的断言失败 11/355 = 3.1%**，**上游断言内容不一致 300/355 = 84.5%**。
- **叠加效应**：28 个任务属 `mixed`——同时存在「项目侧造成的失败」与「上游不一致的失败」；`upstream_*` 全败任务的失败与项目物化无关。
- **对已发布生成测试数字的因果路径**：项目健全性门把 `ult__fix_labels` 误判为红灯（缺前置块），官方前置块下该任务生成套件转绿 ⇒ probe25 有效分母 5 → 6（实测；见 §2c），lite46 不变（9/46）。
- **第二处项目侧缺陷（独立于 gold 结论）**：4 个下划线函数名任务被 `src/datasets/dataset_ult.py:236` 的 `.strip('_')` 改名 ⇒ `ImportError`（= 归档审计里那 4 个 collection error）；官方 `from mod import *` 也不绑定下划线名，故这 4 个在官方契约下仍失败（签名不同）。
- **上游确实存在的缺陷**（同时与官方 README.md:30 "Self-contained functions" 冲突）：`time_in_swiss_german` 期望 `quartel` 而 code 只产出 `viertel`；`centre_on_peak`/`lflverify`/`num_agreeing_tuples` 分别依赖官方前置块也没有的 `sys`/`logging`/`itertools`（`lflverify` 补上 `logging` 后 5/5 通过——属自足性缺口而非断言不一致）。

## 1. 官方契约（Ray/main.py 逐字引用）

| 上游文件:行 | 内容 |
|---|---|
| `Ray/main.py:31-46` | `code_import` 前置块（os/re/math/numpy/pandas/pytest/random/string/warnings/datetime/traceback/np/pd/typing） |
| `Ray/main.py:140-145` | `mod.py = code_import + '\n\n' + instance['code'] + '\n\n'`（再 `rename_test_functions`） |
| `Ray/main.py:148-153` | `test.py = code_import + '\n\n' + 'from mod import *' + '\n\n' + tests[:k]` |
| `Ray/main.py:20-29` | `test-command = "pytest test.py"`，`timeout = {timeout}` |
| `Ray/main.py:159-174` | 官方一致性过滤 = cosmic-ray `baseline`（**作用于生成测试**，非 gold） |
| `Ray/main.py:192-198` | `correct_tasks_tc_{k}_{model}` = baseline 通过集合 |
| `Ray/leakage_free.py:66-74` | `correct_tasks ∩ leakage_free_tasks`（换一批任务，口径同） |
| `datasets/ULT.jsonl` | 3,909 条，字段 `tests`（list[str]，完整 `def test_*` 函数） |
| `datasets/ULT_Lite.jsonl` | 200 条，字段 `test_list`（list[str]，裸 `assert` 片段） |
| `README.md:150-152` | "we do **not** release the ground-truth tests"（与数据文件含 `tests`/`test_list` 矛盾） |

**结论**：`test_list` 在上游仓库**无任何消费者**（grep 全仓 0 命中）；ULT_Lite 的官方执行契约由
`ULT.jsonl` 的 `tests` 形态推定 —— 本脚本机械核验二者断言体逐条相同（见 `records[].upstream.official_tests_equal_lite_test_list`）。
官方契约的 `from mod import *` 还隐含一条：**下划线开头的顶层符号不会被导入**（Python `import *` 语义）。

## 2. 归因矩阵（逐任务，71）

| 归因 | all71 | ult_lite46 | ult_probe25 |
|---|---|---|---|
| `mixed_upstream_and_harness` | 28 | 19 | 9 |
| `project_only_defect` | 1 | 0 | 1 |
| `upstream_assert_inconsistency` | 36 | 24 | 12 |
| `upstream_missing_module_dependency` | 3 | 2 | 1 |
| `upstream_signature_or_type_mismatch` | 3 | 1 | 2 |
| **合计** | **71** | **46** | **25** |

口径：`project_only_defect` = 官方契约（O）也会过、只有项目物化失败；
`official_contract_defect` = 纠正 harness（C）过、官方 `from mod import *` 契约不过；
`mixed_upstream_and_harness` = C 部分断言过；`upstream_*` = C 全败（断言内容与 code 不一致）。

## 2b. gold 参照修正值（实测，非估计）

| 口径 | all71 | ult_lite46 | ult_probe25 |
|---|---|---|---|
| 归档口径 P（项目物化，无前置块） | 0/71 | 0/46 | 0/25 |
| 在线加载器口径 P2 | 0/71 | 0/46 | 0/25 |
| 官方契约口径 O（Ray/main.py 逐字） | 1/71 | 0/46 | 1/25 |
| 纠正 harness 口径 C（前置块 + 显式符号绑定） | 1/71 | 0/46 | 1/25 |

## 2c. 生成测试健全性门：项目物化 vs 官方前置块（对已发布 Mut@k 的因果影响）

| 任务集 | 生成测试非空 | 项目门 pass | 官方前置块 pass | fail→pass 翻转 |
|---|---|---|---|---|
| all71 | 71 | 14 | 15 | 1（ult__fix_labels） |
| ult_lite46 | 46 | 9 | 9 | 0 |
| ult_probe25 | 25 | 5 | 6 | 1（ult__fix_labels） |

## 3. 物化变体状态矩阵（任务级）

| 变体 | pass | fail | collection_error | nonterminate |
|---|---|---|---|---|
| P | 0 | 67 | 4 | 0 |
| P2 | 0 | 67 | 4 | 0 |
| O | 1 | 70 | 0 | 0 |
| C | 1 | 70 | 0 | 0 |
| GP | 14 | 51 | 4 | 2 |
| GO | 15 | 50 | 4 | 2 |

## 4. 失败签名分桶（test 函数级计数）

| 变体:桶 | 计数 |
|---|---|
| `C:assert_failed_clearly_upstream_bug` | 54 |
| `C:assert_failed_expectation_mismatch` | 213 |
| `C:fixture_or_harness_missing` | 15 |
| `C:other` | 2 |
| `C:signature_or_api_mismatch` | 16 |
| `GO:assert_failed_clearly_upstream_bug` | 28 |
| `GO:assert_failed_expectation_mismatch` | 142 |
| `GO:collection_error` | 4 |
| `GO:fixture_or_harness_missing` | 60 |
| `GO:nonterminate_or_timeout` | 4 |
| `GO:other` | 17 |
| `GO:signature_or_api_mismatch` | 25 |
| `GP:assert_failed_clearly_upstream_bug` | 25 |
| `GP:assert_failed_expectation_mismatch` | 136 |
| `GP:collection_error` | 4 |
| `GP:fixture_or_harness_missing` | 150 |
| `GP:nonterminate_or_timeout` | 4 |
| `GP:other` | 17 |
| `GP:signature_or_api_mismatch` | 25 |
| `O:assert_failed_clearly_upstream_bug` | 52 |
| `O:assert_failed_expectation_mismatch` | 195 |
| `O:fixture_or_harness_missing` | 15 |
| `O:import_or_symbol_error` | 20 |
| `O:other` | 2 |
| `O:signature_or_api_mismatch` | 16 |
| `P2:assert_failed_clearly_upstream_bug` | 47 |
| `P2:assert_failed_expectation_mismatch` | 184 |
| `P2:collection_error` | 4 |
| `P2:fixture_or_harness_missing` | 37 |
| `P2:import_or_symbol_error` | 5 |
| `P2:other` | 2 |
| `P2:signature_or_api_mismatch` | 16 |
| `P:assert_failed_clearly_upstream_bug` | 47 |
| `P:assert_failed_expectation_mismatch` | 184 |
| `P:collection_error` | 4 |
| `P:fixture_or_harness_missing` | 37 |
| `P:import_or_symbol_error` | 5 |
| `P:other` | 2 |
| `P:signature_or_api_mismatch` | 16 |

## 4b. `fixture_or_harness_missing` 细分（符号缺失归因）

| 变体:子因 | 计数 |
|---|---|
| `C:code_not_self_contained` | 15 |
| `O:code_not_self_contained` | 15 |
| `P:code_not_self_contained` | 15 |
| `P:missing_official_prelude_symbol` | 22 |

`missing_official_prelude_symbol` = 该符号由官方 `code_import` 提供，仅项目物化缺失 ⇒ 项目侧缺陷；
`code_not_self_contained` = 官方前置块也没有该模块 ⇒ 上游自足性缺口（官方 harness 同样失败）。


## 4c. 补充测量：fix_labels 进入健全子集后的 specir Mut@k 重基

- fix_labels 生成套件（**官方前置块模块**）全变异体 Mut@k = **1.0**（17/17，cosmic-ray 8.7.0，实测；项目物化下同值但含恒红平凡击杀）。
- 已发布 specir：847/1927 = **0.439543**（n=5）。
- 修正后（fix_labels 入组）：864/1944 = **0.444444**（n=6），δ = +0.0049（measured（fix_labels 单任务 Mut@k 为本脚本实测；池化重基为算术合成，非重跑全组））。


## 4d. 补充测量：C+ = 纠正 harness + 官方前置块**外**的缺失模块

> 官方 `code_import` 不含 `sys`/`logging`/`itertools` 等；`code` 依赖这些模块时
> 官方 harness 亦失败。C+ 把缺失模块补进前置块后再判定，用来区分
> 「断言内容与 code 一致但缺依赖」与「断言内容本身不一致」。**非官方口径**，仅作上界参照。

| 任务 | C（官方前置块） | C+（补缺失模块） | 补的符号 |
|---|---|---|---|
| `ult__num_agreeing_tuples` | fail（0p/5f） | fail（0p/5f） | bisect, itertools |
| `ult__centre_on_peak` | fail（0p/5f） | fail（0p/5f） | sys |
| `ult__lflverify` | pass（5p/0f） | pass（5p/0f） | logging |

C+ 全过任务数：**1/3**（补充测量，仅覆盖 C 上因缺模块报错的任务）。

## 5. 断言级归因拆分（5 条 gold 断言 × 71 任务 = 355，实测）

| 口径 | 计数 |
|---|---|
| gold 断言总数 | 355 |
| 项目物化 P 上通过 | 44 |
| 项目物化 P 上失败 | 311 |
| 纠正 harness C 上通过 | 55 |
| C 上失败（= 断言内容与 code 语义不一致） | 300 |
| **P 失败 ∧ C 通过（项目物化/harness 造成的断言失败）** | **11** |
| **P 失败 ∧ C 失败（上游断言内容不一致）** | **300** |
| P 通过 ∧ C 失败（罕见：物化差异掩盖） | 0 |

机器可读逐条记录：`ULT_GOLD_DIAGNOSIS.json → records[].assertion_level`（355 条）。

## 6. 各桶最小例证（verbatim 签名 + 上游定位）

### `assert_failed_expectation_mismatch`

- `ult__levenshtein_shortcircuit_dist`（ult_lite46，上游 `ULT.jsonl` 数组下标 2404，task_id=10807）变体 P：`AssertionError: assert (True, 1) == (True, 3)`；子因 `assert (True, 1) == (True, 3)`
- `ult__movement_of_standard_element`（ult_lite46，上游 `ULT.jsonl` 数组下标 2836，task_id=12803）变体 P：`AssertionError: assert 'ssu' == 'aa'`；子因 `assert 'ssu' == 'aa'`
- `ult__time_in_swiss_german`（ult_lite46，上游 `ULT.jsonl` 数组下标 284，task_id=1159）变体 P：`AssertionError: assert 'halbi 10i am abig' == '9 ab halbi znacht'`；子因 `assert 'halbi 10i am abig' == '9 ab halbi znacht'`

### `assert_failed_clearly_upstream_bug`

- `ult__movement_of_standard_element`（ult_lite46，上游 `ULT.jsonl` 数组下标 2836，task_id=12803）变体 P：`AssertionError: assert 'sddlu' == 'dadao'`；子因 `expected_vocabulary_absent_from_code:dadao,sddlu`
- `ult__time_in_swiss_german`（ult_lite46，上游 `ULT.jsonl` 数组下标 284，task_id=1159）变体 P：`AssertionError: assert 'viertel ab 6i am abig' == '6 ab quartel abig'`；子因 `expected_vocabulary_absent_from_code:quartel`
- `ult__fileNamer`（ult_lite46，上游 `ULT.jsonl` 数组下标 687，task_id=2798）变体 P：`AssertionError: assert 'val_mnist_cn...patience5best' == 'mnist_cnn_3L...ienceKvalbest'`；子因 `expected_vocabulary_absent_from_code:best,iencekvalbest,mnist`

### `import_or_symbol_error`

- `ult__cal_overlap_neg_strand`（ult_lite46，上游 `ULT.jsonl` 数组下标 577，task_id=2261）变体 P：`NameError: name 'COMP_OVL' is not defined`；子因 `NameError:fut_symbol:COMP_OVL`
- `ult__normalized_vcf`（ult_lite46，上游 `ULT.jsonl` 数组下标 375，task_id=1475）变体 O：`NameError: name '_normalized_vcf' is not defined`；子因 `NameError:fut_symbol:_normalized_vcf`
- `ult__lcsmatrix`（ult_lite46，上游 `ULT.jsonl` 数组下标 2289，task_id=10159）变体 O：`NameError: name '_lcsmatrix' is not defined`；子因 `NameError:fut_symbol:_lcsmatrix`

### `signature_or_api_mismatch`

- `ult__unmet_compare`（ult_lite46，上游 `ULT.jsonl` 数组下标 1525，task_id=6496）变体 P：`TypeError: sequence item 0: expected str instance, dict found`；子因 `sequence item 0: expected str instance, dict found`
- `ult__can_blas`（ult_probe25，上游 `ULT.jsonl` 数组下标 81，task_id=287）变体 P：`TypeError: unsupported operand type(s) for -: 'set' and 'list'`；子因 `unsupported operand type(s) for -: 'set' and 'list'`
- `ult__uoc_railfence_encrypt`（ult_probe25，上游 `ULT.jsonl` 数组下标 111，task_id=412）变体 P：`TypeError: object of type 'int' has no len()`；子因 `object of type 'int' has no len()`

### `fixture_or_harness_missing`

- `ult__num_agreeing_tuples`（ult_lite46，上游 `ULT.jsonl` 数组下标 1925，task_id=8461）变体 P：`NameError: name 'itertools' is not defined. Did you forget to import 'itertools'?`；子因 `NameError:undefined_symbol:itertools`
- `ult__processQuery`（ult_lite46，上游 `ULT.jsonl` 数组下标 1702，task_id=7454）变体 P：`NameError: name 're' is not defined. Did you forget to import 're'?`；子因 `missing_official_prelude_symbol:re`
- `ult__centre_on_peak`（ult_lite46，上游 `ULT.jsonl` 数组下标 937，task_id=3934）变体 P：`NameError: name 'sys' is not defined. Did you forget to import 'sys'?`；子因 `NameError:undefined_symbol:sys`

### `other`

- `ult__match_diagonal_right_left`（ult_lite46，上游 `ULT.jsonl` 数组下标 2841，task_id=12824）变体 P：`IndexError: string index out of range`；子因 `IndexError: string index out of range`
- `ult__longestNonWildcardSubsequence`（ult_probe25，上游 `ULT.jsonl` 数组下标 208，task_id=787）变体 P：`IndexError: string index out of range`；子因 `IndexError: string index out of range`

## 7. 复现

```bash
# 零 LLM：只读归档批次工件 + 上游数据集 + 本地 pytest（71 任务 × 6 物化，实测墙钟见上）
.venv/bin/python experiments/emse_ult_gold_diagnosis.py

# 离线只重算本 README（不跑 pytest）
.venv/bin/python experiments/emse_ult_gold_diagnosis.py --from-json experiments/results/emse_ult_gold_diagnosis_20261015/ULT_GOLD_DIAGNOSIS.json
```

逐任务明细与原始签名见 `ULT_GOLD_DIAGNOSIS.json`（`records[].runs.{P,P2,O,C,GP,GO}`）。
