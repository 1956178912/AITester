# misguided/effective 逐测试度量：docstring 锚三臂（df / doc / union）零 LLM 重放工件（2026-10-17）

> **性质**：L 轮 T2 机制指标在 P1 正式批工件上的**描述性重放**（ISSTA'26 操作化：
> effective / misguided / both_pass / both_fail 逐测试四分类）。**不是**预注册确认性
> 证据；不做显著性/效应量推断。主判定（detection / McNemar / 三态 verdict）由
> `experiments/emse_docstring_anchor_analysis.py` 直出（见批次目录
> `DF_DOC_REPORT.json`，本轮结论 `not_confirmed`）；本工件只提供机制侧分解，
> 与 detection **分开报告、不互相顶替**。
>
> **口径文档**：`docs/design/misguided_effective_metric.md`
> **工具**：`experiments/misguided_metrics.py`（零 LLM/零网络，本地 pytest 子进程）
> **输入**（只读，不修改）：`experiments/results/emse_docstring_anchor_20261017/`
> 三件批次工件（同批同日、worktree 干净树 `git_sha=61493ce`、`git_dirty=false`）
> **一页结论**：三臂的机制签名一致——处理臂（doc / union）的 effective 逐测试占比
> 相对 df 对照下降 8.5–9.3pp，**misguided 占比下降**（相对降幅 −83% / −54%，但绝对
> 计数仅 9→2 / 9→7），**both_fail 上升**（+6.94pp / +1.38pp）；即独立锚**没有**把
> 缺陷行为固化为期望（misguided 未升），其检出损失主要来自"正确实现也失败"的
> 过约束/期望值失真测试。该分解细化了 `over_red` proxy 无法区分的两种失败形态。

---

## 1. 输入工件（sha256 锁定）

| 臂 | 角色 | 工件 | sha256 | 归档 detection |
|---|---|---|---|---|
| `plain_llm_df` | 对照 | `benchmark_quixbugs_20261017_194444.json` | `9405176136db2c2e4e7885ca4e6a7116d1647893c31ddd0b8e76b512f1239672` | 31/36 = 86.1% |
| `plain_llm_df_doc` | 处理 A（人类 docstring 锚） | `benchmark_quixbugs_20261017_193626.json` | `3e2a69896d308d389bdd35ed5ce38ae532b9accf89109b297391c265696f78b2` | 21/35 = 60.0% |
| `plain_llm_df_doc_union` | 处理 B（docstring ∪ Planner SpecExpr） | `benchmark_quixbugs_20261017_201928.json` | `746090a277cc6a91fa12151aa1a01f4702efc5e4df1289ceb1afc18bf7e842b2` | 21/34 = 61.76% |

三件工件均由 `run_main_batch.py --dataset quixbugs --task-count 50 --seed 42`
在预注册协议（`docs/study/DOCSTRING_ANCHOR_PREREG_2026-10-17.md`）下产出，
provenance `git_sha=61493ce…`、`git_dirty=false`；本工件只读消费。

## 2. 复算命令（零 LLM / 零网络）

```bash
# 目标单测（<10s；微型 fixture，不依赖真实 QuixBugs/网络）
.venv/bin/python -m pytest tests/test_misguided_metrics.py -q    # 77 passed

# 三臂重放（产出本目录 MISGUIDED_REPORT.json / .md）
.venv/bin/python -m experiments.misguided_metrics \
  --artifact experiments/results/emse_docstring_anchor_20261017/benchmark_quixbugs_20261017_194444.json \
  --artifact experiments/results/emse_docstring_anchor_20261017/benchmark_quixbugs_20261017_193626.json \
  --artifact experiments/results/emse_docstring_anchor_20261017/benchmark_quixbugs_20261017_201928.json \
  --out experiments/results/emse_misguided_docstring_anchor_20261017 \
  --jobs 4 --per-test-timeout 1 --file-timeout 240 --repeat 2
```

- 环境：Python 3.14.6 / pytest 9.1.1 / pytest-timeout 2.4.0 / macOS darwin；
  `nice -n 15`、`--jobs 4`（与其它长任务并行时的 CPU 协调口径）；
- 实测墙钟 **275.3s**（含 2 次全量确定性重放）；缺陷版源码解析自
  `~/.cache/aitester/quixbugs/python_programs/`，逐任务通过"与工件 fixed 同源"
  fail-closed 校验。

## 3. 口径摘要（完整定义见设计文档）

逐测试在 buggy / fixed 两版各跑一次（整文件 pytest + `--junitxml`，双布局物化，
`nested_pytest_env`，pytest-timeout 1s + 整文件墙钟 240s）：

| 分类 | 判据 |
|---|---|
| effective | buggy fail ∧ fixed pass |
| misguided | buggy pass ∧ fixed fail |
| both_pass | 两侧都 pass |
| both_fail | 两侧都 fail（正确实现也过不了） |

- **分母** = 可分类测试数 = 四类之和；`timeout / collect_error / import_error /
  syntax_error / skipped / test_error / missing_side / unknown` **单列、不进分母**；
  超时**不**当"测试红"（与 A-06 判分口径有意不同，交叉校验用 `strict` 口径单独对账）。
- **三档任务口径**（报告 `aggregate` 逐档给出）：
  - `defect_programs`（主分析集）：非 `*_test` 驱动且 `buggy != fixed`，**df/doc=40、
    union=39**（union 的 `powerset` 行因 `generated_test` 语法错误结构跳过，见 §6）；
  - `defect_programs_41_convention`：项目既有 41 口径（仅排除 `*_test`），三臂均 41 行；
  - `all_tasks`：全部 50 归档行（含 9 个 `*_test` 驱动结构跳过；union 另加 powerset → skip 10）。
- **9 个 `*_test` 驱动任务**：源码包相对 import（`from .node import …`），平铺执行口径
  下无法 import → 结构跳过 `import_error`（三臂一致，与归档 `detection=None` 同源）。

## 4. 核心结果（`defect_programs` 主分析集；分母 = 可分类测试数）

| 指标 | `plain_llm_df`（对照） | `plain_llm_df_doc`（A） | `plain_llm_df_doc_union`（B） |
|---|---|---|---|
| 任务行数（ok / 结构跳过） | 40（40/0） | 40（40/0） | **39**（39/0；另 1 行 powerset 语法错误跳过） |
| 总收集测试数 | 832 | 1148 | 1409 |
| **可分类测试数（分母）** | **764** | **1007** | **1264** |
| 不可分类（timeout / 其它） | 67 / 1（skipped） | 141 / 0 | 145 / 0 |
| effective 计数 / 占比 | **379 / 49.61%** | **406 / 40.32%** | **519 / 41.06%** |
| misguided 计数 / 占比 | **9 / 1.18%** | **2 / 0.20%** | **7 / 0.55%** |
| both_pass 计数 / 占比 | 363 / 47.51% | 512 / 50.84% | 699 / 55.30% |
| both_fail 计数 / 占比 | 13 / 1.70% | 87 / 8.64% | 39 / 3.09% |
| 含 effective / misguided 测试的任务数 | 37 / 2 | 35 / 2 | 37 / 4 |
| 每任务 misguided 占比 mean / median | 1.22% / 0% | 0.19% / 0% | 0.58% / 0% |
| 每任务 effective 占比 mean / median | 45.72% / 45.64% | 39.89% / 29.79% | 38.74% / 34.78% |

**两两描述性对比（40 口径；`delta_pp` = B − A，百分点）**

| 对比 | effective | misguided | both_pass | both_fail |
|---|---|---|---|---|
| df → doc | 49.61% → 40.32%（**−9.29**） | 1.18% → 0.20%（**−0.98**） | +3.33 | **+6.94** |
| df → union | 49.61% → 41.06%（**−8.55**） | 1.18% → 0.55%（**−0.62**） | +7.79 | **+1.38** |
| doc → union | 40.32% → 41.06%（+0.74） | 0.20% → 0.55%（+0.36） | +4.46 | −5.55 |

**39 任务匹配子集敏感性**（剔除 union 无法分类的 `powerset`，三臂同任务集；后验披露，
非报告内直出）：df = 749 可分类（effective 49.40% / misguided 1.20% / both_fail 1.74%）、
doc = 982（39.92% / 0.20% / 8.86%）、union = 1264（41.06% / 0.55% / 3.09%）——
与主分析集数字差 <0.25pp，结论不依赖该单行。

**41 口径兼容档**（含 node，项目既有 `defect_program_ids` 口径）：
df = 777 可分类（48.78% / 1.16% / 47.49% / 2.57%）、
doc = 1034（39.27% / 0.19% / 49.81% / 10.73%）、
union = 1276（40.67% / 0.55% / 55.25% / 3.53%）。
`all_tasks`（50 行）同数字，见报告 §3。

**misguided 任务明细**：df = `subsequences` 2 + `wrap` 7；doc = `gcd` 1 + `max_sublist_sum` 1；
union = `subsequences` 4 + `knapsack` 1 + `next_palindrome` 1 + `possible_change` 1。

**both_fail 集中度**：doc 的 87 条中 `detect_cycle` 20 + `shortest_path_length` 12 +
`reverse_linked_list` 12 + `hanoi` 9 + `topological_ordering` 8（前五 70%）；union 的 39 条中
`shunting_yard` 18 + `next_palindrome` 6 + `pascal` 4（前三 72%）；df 仅 13 条（`hanoi` 7、
`wrap` 3）。→ both_fail 不是均匀噪声，集中在少数任务（与各臂 `over_red` 任务数
df 6 / doc 15 / union 13 同向）。

## 5. 与工件既有字段的交叉校验（测量链忠实性）

| 对账项 | df | doc | union |
|---|---|---|---|
| `detection_rate` match | **36** | **35** | **33** |
| mismatch | **0** | **0** | **0** |
| artifact_none（归档 None、重放可判） | 5 | 6 | 7 |
| replay_none（归档有判定、重放不可判） | 0 | 0 | **1**（powerset 语法错误） |
| both_none | 9 | 9 | 9 |
| `specificity_gate_verdict` match / mismatch | 39 / **0** | 37 / **0** | 35 / **0** |
| verdict 不可判（n-a） | 11 | 13 | 15 |

- 三臂 **0 mismatch**：凡归档有 detection/verdict 判定的任务，本次独立重放逐位复现；
- `artifact_none` 全部是不终止任务（bitcount / find_first_in_sorted / sqrt / wrap，
  doc 另含 to_base，union 另含 longest_common_subsequence/knapsack 等），归档因整套
  挂死记 None；`replay_detection_strict`（模拟 A-06 per-test 超时落地前口径）对这些
  任务同样给 None，与归档一致；
- node（辅助模块行，`buggy==fixed`）归档 None、重放可判 0.0，已标 `defect_signal=false`
  并排除出 40 口径主分析集（41/50 行披露中保留）；
- **powerset（union）**：归档 `detection=0.0`（M1 把语法错误执行视为执行错误→0），
  重放无法分类 → `replay_none`，逐条列在报告 §5 差异表。

## 6. 数据质量发现（与机制无关，但必须披露）

union 臂 `powerset` 的 `generated_test` 是**被围栏与 DSML 残留污染的非法 Python**
（首行 ```` ```python ````，尾部含 `</｜｜DSML｜｜ parameter>` 等标记）→ 无法
`ast.parse`。本工具按 `generated_test_syntax_error` 结构跳过（不猜、不修），
不计入任何分母；该行归档 `detection=0.0`、`verdict=unavailable`。
扫描三件工件：**union 1/50 行含此类围栏/DSML 残留，df 0/50、doc 0/50**。
这是生成层/采集层的工件质量问题（历史 `generated_test` 通道曾 974/974 干净），
建议登记为测量完整性观察项（本工件不修改任何冻结输入）。它使 union 的
`defect_programs` 主分析集为 39 行而非 40 行，所有 union 比率均注明了该分母。

## 7. 机制侧解读（**描述性**，非预注册确认性）

1. **与主判定一致**：官方判定 `not_confirmed`（doc vs df δ = −25.71pp，双向 p=0.0352；
   union vs df δ = −23.53pp，p=0.0215；见批次 `DF_DOC_REPORT.json`）。本重放给出同方向的
   逐测试分解：处理臂 effective 占比 −9.29 / −8.55pp。
2. **misguided 方向**：两处理臂 misguided 占比相对 df **下降**（1.18%→0.20% / 0.55%；
   相对降幅 −83% / −54%，数值上超过预注册机制目标"降幅 ≥30%"），但**绝对计数极小**
   （9→2 / 9→7），逐任务 mean 由 1.22% 降至 0.19% / 0.58%。只能作描述性机制信号，
   不能据此作显著性/因果推断；且主判定仍未确认（锚路线不因该方向性信号而保留）。
3. **伤害形态**：处理臂的检出损失**不由 misguided 承担**（misguided 反而更低），而由
   **both_fail** 承担——测试在缺陷版与修复版上**都失败**（期望值/契约失真、过约束），
   把"整文件 fixed 绿"的任务级 detection 拖垮（doc 的 both_fail +6.94pp 且分布集中）。
   这解释了 `over_red` proxy（任务级"fixed 上仍红"）为何会把 independent anchor 的
   效应读成"misguidance"：proxy 把 both_fail 与 misguided 混为一谈。**独立锚并没有把
   缺陷行为固化成期望；它带来的是"正确实现也过不了"的测试。**
4. **doc vs union**：union 的 both_fail 显著低于 doc（3.09% vs 8.64%）、effective 略高
   （41.06% vs 40.32%）——但两者任务级 detection 几乎相同（61.76% vs 60.0%），说明
   union 的 SpecExpr 并集未改变任务级结论，机制差异只在测试单位上可见（描述性）。

## 8. 确定性声明

`--repeat 2` 全量重复重放两次：body digest 两次相同 =
`678463c84c4d9b8ac79d4ecd9a627ec20b54046bfd364b4c5bff91397ee10625`，
`difference_paths=[]`（除时间戳/墙钟等易变字段外逐位一致；易变字段只进 `run_meta`，
不参与 digest）。确定性口径由 `tests/test_misguided_metrics.py::TestReportDeterminism`
锁定。

## 9. 工件清单

| 文件 | sha256 | 说明 |
|---|---|---|
| `MISGUIDED_REPORT.json` | 见下方命令直出 | 三臂全量报告（逐任务逐测试明细、交叉校验、三档分母、run_meta） |
| `MISGUIDED_REPORT.md` | 见下方命令直出 | 人读版（三臂表 + 两两对比 + 差异表直出） |
| `README.md` | 本文件 | 口径/输入 sha256/复算命令/结论/限制 |

工具与测试（未提交工作树；随 L 轮由 Lead 统一 commit）：

| 文件 | 说明 |
|---|---|
| `experiments/misguided_metrics.py` | 零 LLM 重放工具（本轮新增 3 臂两两对比 + 结构跳过 detection 对账修正） |
| `tests/test_misguided_metrics.py` | 77 passed（微型 fixture；`TestComparison`/`TestAnalyzeTaskSkips` 覆盖本轮新增分支） |
| `docs/design/misguided_effective_metric.md` | 口径设计文档 |

> sha256 以本目录内报告 JSON 的 `inputs[].sha256` 与 `run_meta.body_digest` 为准；
> 工具/测试 sha256 由 Lead 入库提交记录，不在此手写以免漂移。

环境：Python 3.14.6 / pytest 9.1.1 / pytest-timeout 2.4.0 / macOS darwin /
`nice -n 15`、`--jobs 4 --per-test-timeout 1 --file-timeout 240 --repeat 2`。
