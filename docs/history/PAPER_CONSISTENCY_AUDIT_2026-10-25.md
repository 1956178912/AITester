# 论文数字-SRC 一致性审计（Q11，2026-10-17 独立评审）

> 工具：`scripts/tools/audit_paper_numbers.py`（本地工具，paper/ 不入库）
> 输入：`/Users/wangchenyu/Workspace/AITester/paper/tex/manuscript.tex` / `/Users/wangchenyu/Workspace/AITester/paper/tex/refs.bib`；SRC 窗口 ±12 行

## 1. 数字声明覆盖率（块级近似）

| 指标 | 数值 |
|---|---|
| 识别到的数字声明 | 278 |
| SRC 窗口覆盖（内部工件数字） | 265 |
| 正文引文覆盖（外部文献数字） | 13 |
| **综合可追溯率** | **100.0%** |
| 仅 SRC 覆盖率 | 95.3% |
| `// SRC:` 注释数 | 160 |

### 逐节覆盖率

| 章节 | 起始行 | 声明数 | SRC 覆盖 | 引文覆盖 | 综合可追溯率 |
|---|---|---|---|---|---|

### 未覆盖的数字声明（待对账清单）

（无）

## 2. SRC 引用有效性

- ✅ 全部 SRC 引用（路径 / ADR / BASELINE 键）可解析

## 2b. 数字存在性（读侧：声明数字是否真在所指工件里）

- 进入判据的高精度数字声明：37 条
- 在工件内核实：21 条
- 工件内**查无此数**（揭露，非阻断）：13 条
- 无可判定工件（披露）：3 条
- `// SRC-CHECK: strict` 声明块失败（**阻断**）：0 条

| 行 | 缺失数字 | 片段 | 所指工件 |
|---|---|---|---|
| 1200 | `['0.426']` | `all 113 favor the protocol (paired difference $\delta = +0.426$, 95\% CI` | docs/emse/WITHDRAWN_ARTIFACTS_2026-10-24.md |
| 1236 | `['0.25']` | `C3: deployed protocol & yes & yes & 80.6\% (29/36) & $+$3 tasks, $p=0.25$ \\` | docs/emse/WITHDRAWN_ARTIFACTS_2026-10-24.md |
| 1334 | `['1.53', '11.88']` | `arm, whose generation path no profile switch touches, moved 1.53\% $\to$` | docs/emse/WITHDRAWN_ARTIFACTS_2026-10-24.md |
| 1350 | `['0.8763']` | `independently (\$0.8763 estimated ceiling for the batch), and its detection` | docs/emse/WITHDRAWN_ARTIFACTS_2026-10-24.md |
| 1604 | `['0.9610', '0.9323', '0.9396', '0.9543', '0.7444', '0.6749', '0.928', '0.64', '0.4395']` | `QuixBugs generated suites & 0.9610 & 0.9323 & 0.9396 (1182/1258), 29/50 suites \\` | experiments/results/emse_quixbugs_mutk_20261014/MUTK_QUXBUGS_RECOMPUTE.json |
| 1658 | `['0.125', '0.45', '0.18', '0.077']` | `underpowered trend (+14.3 pp, $p = 0.125$). We pre-registered an expansion to` | docs/emse/WITHDRAWN_ARTIFACTS_2026-10-24.md |
| 1698 | `['41.32', '40.21']` | `outcome, not a post-hoc excuse. The published 12-model accuracy mean is 41.32\%` | docs/emse/WITHDRAWN_ARTIFACTS_2026-10-24.md |
| 1743 | `['0.0352', '0.0215']` | `two-sided exact $p = 0.0352$---and the union variant reaches 61.8\% (21/34,` | experiments/results/emse_docstring_anchor_20261017/benchmark_quixbugs_20261024_212034.json |
| 1885 | `['8.85', '12.51']` | `rate 8.85\% $\to$ 12.51\%, tasks carrying at least one witness 13/41` | docs/emse/WITHDRAWN_ARTIFACTS_2026-10-24.md |
| 1966 | `['0.001']` | `on the withdrawn generation it was significant at $p < 0.001$ on two seeds).` | docs/emse/WITHDRAWN_ARTIFACTS_2026-10-24.md |
| 2379 | `['0.25', '0.001']` | `positive on the regenerated corpus (+3 tasks, single seed, $p = 0.25$;` | docs/emse/WITHDRAWN_ARTIFACTS_2026-10-24.md |
| 2877 | `['1.959963985', '10,000']` | `Wilson score interval & centre and half-width over the usual $1 + z^2 / n$ denominator, clipped to the unit interval & $` | docs/emse/WITHDRAWN_ARTIFACTS_2026-10-24.md |
| 3064 | `['28.33', '48.79', '1.72', '23.50', '33.33', '1.69', '43.30', '111.01', '1.93', '39.83', '92.01', '1.01', '14.17', '27.23', '1.95', '15.67', '27.23', '1.95']` | `Orchestrated vs detection-first & published, all rows & 240 & 12:80 & $-$28.33 & 48.79 & $p = 1.72 \times 10^{-13}$ \\` | docs/emse/WITHDRAWN_ARTIFACTS_2026-10-24.md |

## 3. 引文卫生

- 正文引用 key：72 个
- bib 条目：72 个
- 缺失条目（正文引用但 bib 没有）：无
- 缺 DOI/arXiv 的条目（含 TODO 挂起）：['aitester2026artifact']
- 重复 DOI：无
- 未被正文引用的条目（warning）：无

## 4. TODO（投稿前清零）

- manuscript.tex:2360 — `DOI is to be assigned at Zenodo [TODO(submit): insert DOI and anonymized URL`
- manuscript.tex:2414 — `\textbf{Funding.} [TODO(confirm): if a grant supported this work, name it with its number`
- manuscript.tex:2419 — `[TODO(confirm): EMSE asks for this as an explicit statement rather than silence.]`
- manuscript.tex:2421 — `\textbf{Author contributions (CRediT).} [TODO(confirm): the assignment below is our`
- manuscript.tex:2430 — `[TODO(confirm): no ethics approval was sought, on that basis.]`
- manuscript.tex:2447 — `[TODO(submit): archival DOI and anonymized review URL].`
- manuscript.tex:2450 — `recomputation chain are released under MIT at [TODO(submit): repository URL and`
- manuscript.tex:2453 — `\textbf{Acknowledgements.} [TODO(submit): optional; leave absent if none.]`
- manuscript.tex:2455 — `\textbf{Preprint and concurrent submission.} [TODO(confirm): declare any preprint posted`
- refs.bib:320 — `note         = {DOI pending deposit; TODO(ref): to be filled in after Zenodo archiving}`

## 5. 边界

- 数字识别为启发式（漏报/误报均可能），未覆盖清单须人工复核；
- 覆盖率为块级近似，不等于逐条数字均已逐项追溯；
- 数字存在性判据只覆盖**高精度**数字（≥2 位小数或千分位整数）且 SRC 指向可判定工件（JSON / 撤回索引）；`unchecked` 是披露不是通过，低精度数字仍靠人工逐条核对；
- 本报告为本地审计工件（paper/ 不入库），不接入 CI。
