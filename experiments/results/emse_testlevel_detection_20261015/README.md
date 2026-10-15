# QuixBugs 测试级检出画像（TESTLEVEL_DETECTION，2026-10-15 批次九）

> 零 LLM：只读归档 benchmark JSON + 本地 pytest 子进程；无网络/LLM 调用。
> 本目录三件套：`README.md`（方法学+表格+核验证据）、`TESTLEVEL_DETECTION.json`（机器可读）、
> `SHA256SUMS.txt`（`shasum -a 256` 前两件）。

## 0. 口径标签（全文一致）

| 标签 | 含义 |
|---|---|
| `measured` | 本次本地 pytest 运行直接观测到的计数/比率（可复算） |
| `computed` | 由 measured 计数经精确闭式公式推导（McNemar 精确 p、δ、贝叶斯因子） |
| `estimated` | 模型近似（MDE、功效：正态近似；BF 依赖 Jeffreys 先验模型） |
| `unmeasured` | 本次无法测量（超时/无 gold 材料/无逐测试数据），**不填 0** |

判定口径（逐测试，互斥）：`f2p` = buggy 侧失败 ∧ fixed 侧通过；`p2p` = 两侧通过；
`f2f` = 两侧失败；`p2f` = buggy 通过 ∧ fixed 失败；`other` = 单侧不可用
（收集错误 / 超时 / node id 缺失 / skipped）。
「失败」含 call 相位断言失败与 setup/teardown 异常（相位细分见 §3.6）。

## 1. 方法与命令

1. 任务集 = `src.datasets.dataset_realbugs.QuixBugsDataset()`（`/Users/wangchenyu/.cache/aitester/quixbugs`）；
   仅 `metadata.test_cases` ∧ `metadata.fixed` 均非空者进入口径：
   **41 / 50** 个任务
（排除 9 个无 gold 材料程序：`quixbugs__breadth_first_search_test`, `quixbugs__depth_first_search_test`, `quixbugs__detect_cycle_test` …）。
2. 材料派生复用单一事实源：模块名 ← `_m1_metrics._extract_gold_material`；gold 代码 ← `_gold_fixed_code`；
   缺陷代码 ← `task.instance_code`；生成套件 ← 归档行 `generated_test`。
3. 物化 = `_m1_metrics._prepare_packaged_test_tree`（packaged 分支，与 `_run_pytest_in_tmp` 判分链路逐字同口径：
   双布局模块 + `node.py`/`load_testdata.py`/`json_testcases` + `pytest.use_correct=False` prelude）。
4. 同一套件跑两次：`pytest <test> -v --tb=no -rA -p no:cacheprovider -p _dsh_outcomes`，
   一次对缺陷代码、一次对 gold 修复代码；`_dsh_outcomes` 是**只做记录**的插件（逐 phase 写 JSONL）。
   两路解析（插件 JSONL + `-v` 文本）交叉校验，不一致即暴露（见 §3.6）。
5. 每次运行上限 `30s`（与 `emse_test_sanity_audit.py` 同口径）；超时 = 不可测。

复现命令：

```bash
AITESTER_QUIXBUGS_DATA=~/.cache/aitester/quixbugs .venv/bin/python experiments/emse_testlevel_detection.py --out experiments/results/emse_testlevel_detection_20261015 --cap-seconds 30 --jobs 1
```

（脚本内部子进程命令行即上表第 4 步；逐套件哈希/计数见 JSON `tasks[].buggy.stdout_sha256`。）

本件为**分析重算**（`--reuse-json`：不重跑 pytest，只重算聚合/统计/渲染；
全部 measured 字段来自上面那条完整跑批命令的工件）：

```bash
AITESTER_QUIXBUGS_DATA=~/.cache/aitester/quixbugs .venv/bin/python experiments/emse_testlevel_detection.py --reuse-json experiments/results/emse_testlevel_detection_20261015/TESTLEVEL_DETECTION.json --independent-check --out experiments/results/emse_testlevel_detection_20261015 --cap-seconds 30 --jobs 1
```

### 1.1 来源工件（本次实际使用，含 sha256）

| 来源 | 角色 | 工件 | sha256（前 16） | cache_namespace | 归档行数 | gold 合资格 | 实跑套件 | 跳过(无 gold) |
|---|---|---|---|---|---|---|---|---|
| `quixbugs50_batch5` | batch5 | `benchmark_quixbugs_20261014_005101.json` | `4d2f37e86b10dcc6` | `-` | 50 | 41 | 41 | 9 |
| `arm_A_specir` | arm | `benchmark_quixbugs_20261014_212856.json` | `aac71d96a56a347d` | `emse_qbug_specir_expand_A_20261014` | 50 | 41 | 41 | 9 |
| `arm_B_nl` | arm | `benchmark_quixbugs_20261014_215650.json` | `8a2ab2dadc770bf8` | `emse_qbug_specir_expand_B_20261014` | 50 | 41 | 41 | 9 |
| `arm_C_specir_repeat` | arm | `benchmark_quixbugs_20261015_180316.json` | `7ab516d5a238882c` | `emse_qbug_specir_expand_C_20261014` | 50 | 41 | 41 | 9 |
| `arm_D_nl_repeat` | arm | `benchmark_quixbugs_20261015_183226.json` | `8db81c3dd34e88f1` | `emse_qbug_specir_expand_D_20261014` | 50 | 41 | 41 | 9 |

合计：**5 个来源 × 41 个 gold-eligible 任务 = 205 个套件 × 2 侧 = 410 次 pytest 运行**；总墙钟 1519.4s。

## 2. 执行总览（measured）

| 来源 | 套件 | detecting_clean | detecting_invalid | blind_clean | invalid_only | timeout | no_pertest_data | buggy 超时 | fixed 超时 | 无可解析逐测试数据的任务数 |
|---|---|---|---|---|---|---|---|---|---|---|
| `quixbugs50_batch5` | 41 | 30 | 4 | 2 | 1 | 4 | 0 | 4 | 3 | 0 |
| `arm_A_specir` | 41 | 24 | 8 | 3 | 1 | 5 | 0 | 5 | 3 | 0 |
| `arm_B_nl` | 41 | 26 | 8 | 1 | 1 | 5 | 0 | 5 | 4 | 0 |
| `arm_C_specir_repeat` | 41 | 22 | 10 | 2 | 2 | 5 | 0 | 5 | 4 | 0 |
| `arm_D_nl_repeat` | 41 | 25 | 9 | 1 | 1 | 5 | 0 | 5 | 4 | 0 |
| `pooled_all_sources` | 205 | 127 | 39 | 9 | 6 | 24 | 0 | 5 | 4 | 0 |

> 套件级标签（互斥，判定顺序：timeout → no_pertest_data → 四分类）：
> `detecting_clean` = f2p≥1 且 f2f=0；`detecting_invalid` = f2p≥1 且 f2f≥1；
> `blind_clean` = f2p=0 且 f2f=0（可能含 p2f/other）；`invalid_only` = f2p=0 且 f2f≥1；
> `timeout` = 任一侧 30s 未终结；`no_pertest_data` = 两侧都跑完但至少一侧无任何可解析 node id。
> **注意**：`detecting_clean` 只排除 f2f，**不等价于** task-level `detection_rate`=1.0——
> 后者还要求 fixed 侧 rc=0，因此 p2f>0（在修复代码上反而失败）的套件仍可能落进 `detecting_clean`。
> 反向成立：det=1.0 的套件必然是 `detecting_clean` 且 f2f=p2f=0（下表 §3.4 的 f2p=0 异常清单为空即此校验）。

## 3. Step 2 指标（显式分母）

### 3.1 测试级 F2P 率

| 来源 | f2p | 可分类测试 n（两侧都出现） | 池化 F2P 率（f2p/n） | 并集分母 n | 并集口径 F2P 率 | 单侧仅 buggy | 单侧仅 fixed |
|---|---|---|---|---|---|---|---|
| `quixbugs50_batch5` | 326 | 904 | 0.3606 | 991 | 0.329 | 0 | 74 |
| `arm_A_specir` | 299 | 920 | 0.325 | 1016 | 0.2943 | 0 | 51 |
| `arm_B_nl` | 292 | 795 | 0.3673 | 893 | 0.327 | 0 | 46 |
| `arm_C_specir_repeat` | 284 | 811 | 0.3502 | 948 | 0.2996 | 0 | 86 |
| `arm_D_nl_repeat` | 343 | 826 | 0.4153 | 916 | 0.3745 | 0 | 48 |
| `pooled_all_sources` | 1544 | 4256 | 0.3628 | 4764 | 0.3241 | 0 | 305 |

逐任务 F2P 占比（`f2p / 可分类测试数`，pooled 全部 181 个套件中可分类者）：mean=0.3747，median=0.3，Q1=0.1538，Q3=0.5882，min=0.0，max=0.9333。

占比直方图（pooled，measured）：

| 区间 | 套件数 |
|---|---|
| 0 | 15 |
| (0,0.25] | 65 |
| (0.25,0.5] | 43 |
| (0.5,0.75] | 35 |
| (0.75,1] | 23 |

### 3.2 盲测质量（blind mass，measured）

| 来源 | p2p | f2p | p2p/可分类 | p2p/(p2p+f2p) |
|---|---|---|---|---|
| `quixbugs50_batch5` | 550 | 326 | 0.6084 | 0.6279 |
| `arm_A_specir` | 570 | 299 | 0.6196 | 0.6559 |
| `arm_B_nl` | 472 | 292 | 0.5937 | 0.6178 |
| `arm_C_specir_repeat` | 480 | 284 | 0.5919 | 0.6283 |
| `arm_D_nl_repeat` | 458 | 343 | 0.5545 | 0.5718 |
| `pooled_all_sources` | 2530 | 1544 | 0.5945 | 0.621 |

### 3.3 无效质量（invalid mass：在**正确代码**上失败的测试）

| 来源 | f2f | f2f/可分类 | f2f>0 的套件数 | 套件在 fixed 上 rc=0（绿） | 套件绿率(fixed) | 套件在 buggy 上 rc=0 | p2f（反向） | p2f>0 套件数 |
|---|---|---|---|---|---|---|---|---|
| `quixbugs50_batch5` | 22 | 0.0243 | 5 | 30 | 0.7317 | 2 | 6 | 4 |
| `arm_A_specir` | 30 | 0.0326 | 9 | 25 | 0.6098 | 3 | 21 | 6 |
| `arm_B_nl` | 22 | 0.0277 | 9 | 27 | 0.6585 | 1 | 9 | 4 |
| `arm_C_specir_repeat` | 36 | 0.0444 | 12 | 22 | 0.5366 | 2 | 11 | 7 |
| `arm_D_nl_repeat` | 20 | 0.0242 | 10 | 26 | 0.6341 | 1 | 5 | 4 |
| `pooled_all_sources` | 130 | 0.0305 | 45 | 130 | 0.6341 | 9 | 52 | 25 |

> 对照 `emse_test_sanity_20261015/SANITY_AUDIT.json`（**扁平物化**口径，仅 fixed 侧、30s）：
> batch5 生成套件 30 pass / 17 fail / 3 nonterminate。本件用 packaged 物化（detection_rate 的判分链路），
> 两者差异只可能来自物化口径与超时口径，逐任务对账见 §5。

### 3.4 任务级检出的测试级换算（headline，measured）

对**归档 `detection_rate` = 1.0** 的套件，统计其 f2p 测试函数个数分布：

| 来源 | det=1.0 套件数 | f2p=0 | **f2p=1（单测试扛下）** | f2p=2 | f2p≥3 | det1 内 f2p 合计 | det1 内可分类测试合计 | det1 内平均 f2p |
|---|---|---|---|---|---|---|---|---|
| `quixbugs50_batch5` | 28 | 0 | **0** | 3 | 25 | 307 | 723 | 10.9643 |
| `arm_A_specir` | 23 | 0 | **1** | 2 | 20 | 223 | 536 | 9.6957 |
| `arm_B_nl` | 26 | 0 | **2** | 2 | 22 | 261 | 617 | 10.0385 |
| `arm_C_specir_repeat` | 20 | 0 | **1** | 2 | 17 | 149 | 417 | 7.45 |
| `arm_D_nl_repeat` | 25 | 0 | **0** | 2 | 23 | 195 | 562 | 7.8 |
| `pooled_all_sources` | 122 | 0 | **4** | 11 | 107 | 1135 | 2855 | 9.3033 |

**headline：122 个任务级"检出"中，4 个（3.3%）由 1 个测试函数扛下，118 个由 ≥2 个测试函数支撑**（pooled，measured）。

- det=1.0 套件里 f2p=0 的异常情况：无（应为空——若非空即口径矛盾，需调查）。
- det=1.0 套件的 f2p 占其可分类测试总数：1135/2855 = 0.3975。

### 3.5 f2p 的相位细分（buggy 侧 call 相位 vs setup/teardown 相位，measured）

| 来源 | f2p（buggy 侧 call 相位失败：断言失败或测试体内未捕获异常） | f2p（buggy 侧 setup/teardown 异常） |
|---|---|---|
| `quixbugs50_batch5` | 326 | 0 |
| `arm_A_specir` | 299 | 0 |
| `arm_B_nl` | 292 | 0 |
| `arm_C_specir_repeat` | 284 | 0 |
| `arm_D_nl_repeat` | 343 | 0 |
| `pooled_all_sources` | 1544 | 0 |

> 「call 相位失败」= pytest 在测试函数体内记录 `failed`：既含 `assert` 失败，也含被测缺陷代码
> 直接抛出的未捕获异常（如 `IndexError`/`TypeError`）——两者都是真实的缺陷触发路径。
> setup/teardown 相位异常单列（夹具/清理阶段失败，与测试体断言无关）。
> 本件未保存失败消息 → 「纯断言失败」这一更细的子类**unmeasured**（不猜）。

### 3.6 解析与数据完整性（measured）

| 来源 | 插件/-v 双路一致条数 | 不一致条数 | -v 回退侧数 | 无解析器侧数 | 超时（任一侧） | 无可解析逐测试数据的任务 |
|---|---|---|---|---|---|---|
| `quixbugs50_batch5` | 1899 | 0 | 0 | 0 | 4 | 0 |
| `arm_A_specir` | 1973 | 0 | 0 | 0 | 5 | 0 |
| `arm_B_nl` | 1731 | 0 | 0 | 0 | 5 | 0 |
| `arm_C_specir_repeat` | 1801 | 0 | 0 | 0 | 5 | 0 |
| `arm_D_nl_repeat` | 1775 | 0 | 0 | 0 | 5 | 0 |
| `pooled_all_sources` | 9179 | 0 | 0 | 0 | 24 | 0 |

## 4. Step 3：任务级 vs 测试级配对功效

### 4.1 任务级（复现既有结论，computed）

复用 `experiments/emse_quixbugs_specir_expand.py::build_analysis`（同一实现，非另写）：

| 对比 | n | 仅 specir 检出 | 仅 NL 检出 | δ(pp) | McNemar 精确 p | BF10(Jeffreys) | MDE(pp, 两比例) | 判定 |
|---|---|---|---|---|---|---|---|---|
| task-level primary（A specir vs B NL） | 35 | 2 | 5 | -8.57 | 0.4531 | 0.5625 | 16.57 | `not_confirmed` |
| task-level repeat（C specir vs D NL） | 35 | 2 | 7 | -14.29 | 0.1797 | 1.1172 | 16.57 | `not_confirmed` |
| task-level merged（A∪C vs B∪D） | 70 | 4 | 12 | -11.43 | 0.0768 | 1.587 | 11.71 | `not_confirmed` |

### 4.2 测试级配对（按 node id 配对，computed）

| 对比 | 配对任务数 | 共享 node id | X 独有 | Y 独有 | 因 other 丢弃 | 配对数 n | 仅 X f2p | 仅 Y f2p | 双侧 f2p | 都不 f2p | δ(pp) | p(McNemar 精确) | BF10 | MDE(pp) | 判定 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A_specir vs B_nl | 41 | 68 | 948 | 825 | 9 | 59 | 0 | 1 | 13 | 45 | -1.69 | 1.0 | 0.9999999999999994 | 12.76 | `not_confirmed` |
| C_specir_repeat vs D_nl_repeat | 41 | 67 | 881 | 849 | 13 | 54 | 1 | 2 | 18 | 33 | -1.85 | 1.0 | 0.4999999999999997 | 13.34 | `not_confirmed` |
| test-level merged（A∪C vs B∪D，分层合并） | 82 | 135 | 1829 | 1674 | 22 | 113 | 1 | 3 | 31 | 78 | -1.77 | 0.625 | 0.6249999999999999 | 9.22 | `not_confirmed` |

**读法（关键）**：测试级「共享 node id」极少——两个臂是**独立生成**的测试套件，
函数名大多不同，因此按 node id 严格配对会丢掉绝大部分观测（配对 n 远小于双臂测试总数）。
这不是 bug，而是「测试级配对」这一口径的**固有代价**，也正是必须同时给任务聚类变体的原因。

### 4.3 任务聚类变体（每任务一个观测单位，防伪重复，computed）

| 对比 | 任务 n | Σf2p(X) | Σf2p(Y) | X 更多的任务 | Y 更多的任务 | 并列 | 平均 Δf2p(计数) | 平均 Δf2p(占比) | 符号检验(McNemar 精确) p | Wilcoxon 精确 p | Wilcoxon 正态近似 p |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A_specir vs B_nl | 41 | 299 | 292 | 16 | 15 | 10 | 0.1707 | -0.0289 | 1.0 | 0.5561 | 0.5548 |
| C_specir_repeat vs D_nl_repeat | 41 | 284 | 343 | 13 | 18 | 10 | -1.439 | -0.0496 | 0.4731 | 0.3139 | 0.3115 |
| task-clustered merged（A∪C vs B∪D） | 82 | 583 | 635 | 29 | 33 | 20 | -0.6341 | -0.0393 | 0.7035 | `unmeasured` | `unmeasured` |

### 4.4 MDE 对照（estimated：正态近似模型）

| 层级 | n | ψ（不一致率） | MDE 两比例(pp) | MDE 配对(pp) | 8pp 处功效 |
|---|---|---|---|---|---|
| 任务级（primary A vs B） | 35 | 0.2 | 16.57 | 10.59 | 0.5622 |
| 测试级（primary A vs B，按 node id） | 59 | 0.0169 | 12.76 | 2.37 | 1.0 |
| 测试级（任务聚类：n=任务数） | 41 | unmeasured（任务级计数非二值，ψ 无对应定义） | 15.31 | - | - |

### 4.5 替代口径敏感性：buggy 侧挂死算不算检出（computed，非主口径）

替代口径（敏感性）：buggy 侧 30s 挂死 ∧ fixed 侧 rc=0 且无执行错误 → 记检出 1.0；其余同主口径

| 对比（替代口径） | n | 仅 X 检出 | 仅 Y 检出 | δ(pp) | McNemar 精确 p | BF10 | MDE(pp) | 判定 |
|---|---|---|---|---|---|---|---|---|
| A_alt vs B_alt | 37 | 2 | 5 | -8.11 | 0.4531 | 0.5624999999999997 | 16.11 | `not_confirmed` |
| C_alt vs D_alt | 37 | 2 | 7 | -13.51 | 0.1797 | 1.1171875000000029 | 16.11 | `not_confirmed` |
| AC_alt vs BD_alt | 74 | 4 | 12 | -10.81 | 0.0768 | 1.5870056152343772 | 11.39 | `not_confirmed` |

被该口径翻转的任务（逐源，均为「buggy 侧 30s 挂死、fixed 侧全绿」）：

| 来源 | 数量 | task_id |
|---|---|---|
| `quixbugs50_batch5` | 1 | `quixbugs__find_first_in_sorted` |
| `arm_A_specir` | 2 | `quixbugs__bitcount`, `quixbugs__find_first_in_sorted` |
| `arm_B_nl` | 1 | `quixbugs__find_first_in_sorted` |
| `arm_C_specir_repeat` | 1 | `quixbugs__find_first_in_sorted` |
| `arm_D_nl_repeat` | 1 | `quixbugs__find_first_in_sorted` |

> 读法：主口径下这 1 个任务/源（`quixbugs__find_first_in_sorted`）因 buggy 侧挂死被判 `None`，
> 从而**整体退出配对样本**（n=35 而非 41）；若改判为检出，配对 n 与 δ/p 都会变化。
> 这说明任务级配对结论不仅样本小，而且**对「不可测」的记法敏感**；替代口径仅供敏感性披露，
> 不作为本件或论文的主口径。

### 4.6 任务聚类「计数 vs 占比」方向不一致的根因：**套件规模混淆**（measured）

§4.3 表中 primary 对比出现「计数方向为正（SpecExpr 多）vs 占比方向为负（NL 多）」
的不一致。本节由逐任务计数导出其根因：**套件规模（生成测试数量）差异造成的混淆**，
不是度量矛盾。

**arm_A_specir vs arm_B_nl**（共同 41 任务）

| 量 | arm_A_specir | arm_B_nl | 差 |
|---|---|---|---|
| 可分类测试总数 | **920** | **795** | +125（**+15.7%**） |
| 每任务平均可分类测试数 | **22.4** | **19.4** | +3.0 |
| Σf2p（计数尺度） | 299 | 292 | +7 |
| f2p 率（归一后） | **0.3250** | **0.3673** | **-4.23pp** |
| Δf2p 逐任务均值 | 计数 **+0.1944** | 占比 **-0.0289** | 占比口径下 NL 更多 18 : SpecExpr 更多 16 |

**arm_C_specir_repeat vs arm_D_nl_repeat**（共同 41 任务）

| 量 | arm_C_specir_repeat | arm_D_nl_repeat | 差 |
|---|---|---|---|
| 可分类测试总数 | **811** | **826** | -15（**-1.8%**） |
| 每任务平均可分类测试数 | **19.8** | **20.1** | -0.4 |
| Σf2p（计数尺度） | 284 | 343 | -59 |
| f2p 率（归一后） | **0.3502** | **0.4153** | **-6.51pp** |
| Δf2p 逐任务均值 | 计数 **-1.6389** | 占比 **-0.0496** | 占比口径下 NL 更多 20 : SpecExpr 更多 13 |


> 读法：计数尺度比较的是「两臂各自生成的测试数量」，而两臂**生成量本身不同**
> （primary 对 A 比 B 多 +15.7%；repeat 对 C 比 D 少 −1.8%）⇒ 计数口径被套件规模
> 混淆，**其方向可随生成量差异而翻转**（primary 对即由 +0.19 翻为 −0.03），不等于
> 检出能力差异；按规模归一后两对同向（均无正效应，NL 略高）。因此原「primary 任务
> 聚类方向反向」的表述**不成立**。

> **对论文的措辞要求**：跨臂比较**不得**使用「f2p 绝对计数」作因变量（未控生成量）；
> 若报告计数，必须同时给出可分类测试总数或改用占比/率。§4.3 的 Δf2p(计数) 列仅作
> 描述性补充，判定以占比与任务级二值口径为准。

### 4.7 结论（逐条标注支撑口径）

- （measured）pooled 122 个任务级检出中 4 个（3.3%）由**单个**测试函数扛下；det1 套件平均 f2p = 9.3033（占其可分类测试 39.75%）。
- （measured）pooled 盲测质量 p2p=2530 vs f2p=1544：62.1% 的（p2p+f2p）测试不携带任何缺陷检出信号；f2f（在正确代码上失败）率 0.0305。
- （computed）任务级 primary 复现：2:5，n=35，δ=-8.57pp，p=0.4531，BF10=0.5625 → 判定 `not_confirmed`（与既有结论一致）。
- （computed）测试级 A_specir vs B_nl：共享 node id 68（X 独有 948、Y 独有 825），严格配对数 n=59，0:1，δ=-1.69pp，p=1.0，BF10=0.9999999999999994 → `not_confirmed`。
- （computed）测试级 C_specir_repeat vs D_nl_repeat：共享 node id 67（X 独有 881、Y 独有 849），严格配对数 n=54，1:2，δ=-1.85pp，p=1.0，BF10=0.4999999999999997 → `not_confirmed`。
- （computed）测试级 test-level merged（A∪C vs B∪D，分层合并）：共享 node id 135（X 独有 1829、Y 独有 1674），严格配对数 n=113，1:3，δ=-1.77pp，p=0.625，BF10=0.6249999999999999 → `not_confirmed`。
- （computed）任务聚类 A_specir vs B_nl：n=41 任务，X/Y 更多 f2p 的任务数 16/15（并列 10），符号检验 p=1.0，Wilcoxon 精确 p=0.5561，平均 Δf2p(计数)=0.1707。
- （computed）任务聚类 C_specir_repeat vs D_nl_repeat：n=41 任务，X/Y 更多 f2p 的任务数 13/18（并列 10），符号检验 p=0.4731，Wilcoxon 精确 p=0.3139，平均 Δf2p(计数)=-1.439。
- （computed）任务聚类 task-clustered merged（A∪C vs B∪D）：n=82 任务，X/Y 更多 f2p 的任务数 29/33（并列 20），符号检验 p=0.7035，Wilcoxon 精确 p=None，平均 Δf2p(计数)=-0.6341。
- （estimated）MDE 对照：任务级 n=35 → 16.57pp（配对近似 10.59pp）；测试级严格配对 n=59 → 12.76pp；任务聚类 n=41 → 15.31pp。
- （口径提示）测试级严格配对把「两臂各自生成的测试函数」按同名 node id 对齐，共享率极低，其 n 远小于测试总数；因此**任务聚类结论优先于测试级严格配对结论**，测试级配对只作为「同名测试函数在同任务上的行为差异」这一窄口径的补充证据。
- （computed·替代口径敏感性）把「buggy 侧挂死 ∧ fixed 侧全绿」也记为检出后，A_alt vs B_alt → 2:5（n=37，δ=-8.11pp，p=0.4531，`not_confirmed`）；C_alt vs D_alt → 2:7（n=37，δ=-13.51pp，p=0.1797，`not_confirmed`）；AC_alt vs BD_alt → 4:12（n=74，δ=-10.81pp，p=0.0768，`not_confirmed`）；此类任务逐源：{'quixbugs50_batch5': ['quixbugs__find_first_in_sorted'], 'arm_A_specir': ['quixbugs__bitcount', 'quixbugs__find_first_in_sorted'], 'arm_B_nl': ['quixbugs__find_first_in_sorted'], 'arm_C_specir_repeat': ['quixbugs__find_first_in_sorted'], 'arm_D_nl_repeat': ['quixbugs__find_first_in_sorted']}。

## 5. 任务级检测率复算对账（measured vs 归档）

三段判据（`_compute_detection_rate` 同规则）在本次运行上复算，与归档 `detection_rate` 逐任务对账：

| 来源 | 归档→复算（1.0→1.0） | (0.0→0.0) | (None→None) | 其他组合 | 不一致 |
|---|---|---|---|---|---|
| `quixbugs50_batch5` | 28 | 8 | 4 | 1 | 1 |
| `arm_A_specir` | 23 | 12 | 5 | 1 | 1 |
| `arm_B_nl` | 26 | 9 | 5 | 1 | 1 |
| `arm_C_specir_repeat` | 20 | 15 | 5 | 1 | 1 |
| `arm_D_nl_repeat` | 25 | 10 | 5 | 1 | 1 |

不一致逐条（若为空表则完全一致）：

| 来源 | task_id | 归档 | 复算 | buggy rc | fixed rc | buggy 超时 | fixed 超时 | f2p/p2p/f2f/p2f/other | 归档 stop_reason |
|---|---|---|---|---|---|---|---|---|---|
| `quixbugs50_batch5` | `quixbugs__node` | None | 0.0 | 0 | 0 | False | False | 0/8/0/0/0 | `test_passed` |
| `arm_A_specir` | `quixbugs__node` | None | 0.0 | 1 | 1 | False | False | 0/31/1/0/0 | `skip_debugger_repair_invalid` |
| `arm_B_nl` | `quixbugs__node` | None | 0.0 | 1 | 1 | False | False | 0/15/6/0/0 | `test_passed` |
| `arm_C_specir_repeat` | `quixbugs__node` | None | 0.0 | 1 | 1 | False | False | 0/8/3/0/0 | `skip_debugger_repair_invalid` |
| `arm_D_nl_repeat` | `quixbugs__node` | None | 0.0 | 1 | 1 | False | False | 0/16/3/0/0 | `test_passed` |

### 5.1 无逐测试数据的任务（不静默丢弃）

- `quixbugs50_batch5`：0 个 —— （无）
- `arm_A_specir`：0 个 —— （无）
- `arm_B_nl`：0 个 —— （无）
- `arm_C_specir_repeat`：0 个 —— （无）
- `arm_D_nl_repeat`：0 个 —— （无）

## 6. 手工核验证据（原始输出 ↔ 解析结果并排）

### quixbugs50_batch5 / `quixbugs__pascal`（选取规则：batch5 中 f2p 计数最大（并列取 task_id 最小））

- 归档 detection_rate = `1.0`；本次复算 = `1.0`；suite_class = `detecting_clean`
- buggy 侧：rc=1 timed_out=False node ids=46（-v 解析=46） 解析器=plugin+verbose
- fixed 侧：rc=0 timed_out=False node ids=46（-v 解析=46） 解析器=plugin+verbose

**原始 `pytest -v` 输出（buggy 侧，节选末尾 60 行）**：

```text
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_inner_elements_are_sum_of_above[2] PASSED                   [ 78%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_inner_elements_are_sum_of_above[3] FAILED                   [ 80%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_inner_elements_are_sum_of_above[4] FAILED                   [ 82%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_inner_elements_are_sum_of_above[5] FAILED                   [ 84%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_inner_elements_are_sum_of_above[6] FAILED                   [ 86%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_inner_elements_are_sum_of_above[7] FAILED                   [ 89%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_inner_elements_are_sum_of_above[8] FAILED                   [ 91%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_inner_elements_are_sum_of_above[9] FAILED                   [ 93%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_inner_elements_are_sum_of_above[10] FAILED                  [ 95%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_n0_behavior_under_precondition_violation PASSED             [ 97%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_negative_n_behavior_under_precondition_violation PASSED     [100%]

======================================================================================= short test summary info ========================================================================================
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_n1_returns_single_row
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_result_length_equals_n[1]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_result_length_equals_n[2]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_row_lengths_are_i_plus_one[1]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_row_edges_are_one[1]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_row_edges_are_one[2]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_inner_elements_are_sum_of_above[2]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_n0_behavior_under_precondition_violation
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_negative_n_behavior_under_precondition_violation
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_n2_returns_two_rows - AssertionError: assert [[1], [1]] =...
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_n3_returns_three_rows - IndexError: list index out of range
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_n5_returns_expected_triangle - IndexError: list index out...
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_n10_returns_expected_triangle - IndexError: list index ou...
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_result_length_equals_n[3] - IndexError: list index out of...
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_result_length_equals_n[4] - IndexError: list index out of...
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_result_length_equals_n[5] - IndexError: list index out of...
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_result_length_equals_n[6] - IndexError: list index out of...
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_result_length_equals_n[7] - IndexError: list index out of...
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_result_length_equals_n[8] - IndexError: list index out of...
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_result_length_equals_n[9] - IndexError: list index out of...
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_result_length_equals_n[10] - IndexError: list index out o...
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_row_lengths_are_i_plus_one[2] - assert False
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_row_lengths_are_i_plus_one[3] - IndexError: list index ou...
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_row_lengths_are_i_plus_one[4] - IndexError: list index ou...
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_row_lengths_are_i_plus_one[5] - IndexError: list index ou...
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_row_lengths_are_i_plus_one[6] - IndexError: list index ou...
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_row_lengths_are_i_plus_one[7] - IndexError: list index ou...
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_row_lengths_are_i_plus_one[8] - IndexError: list index ou...
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_row_lengths_are_i_plus_one[9] - IndexError: list index ou...
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_row_lengths_are_i_plus_one[10] - IndexError: list index o...
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_row_edges_are_one[3] - IndexError: list index out of range
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_row_edges_are_one[4] - IndexError: list index out of range
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_row_edges_are_one[5] - IndexError: list index out of range
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_row_edges_are_one[6] - IndexError: list index out of range
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_row_edges_are_one[7] - IndexError: list index out of range
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_row_edges_are_one[8] - IndexError: list index out of range
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_row_edges_are_one[9] - IndexError: list index out of range
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_row_edges_are_one[10] - IndexError: list index out of range
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_inner_elements_are_sum_of_above[3] - IndexError: list ind...
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_inner_elements_are_sum_of_above[4] - IndexError: list ind...
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_inner_elements_are_sum_of_above[5] - IndexError: list ind...
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_inner_elements_are_sum_of_above[6] - IndexError: list ind...
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_inner_elements_are_sum_of_above[7] - IndexError: list ind...
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_inner_elements_are_sum_of_above[8] - IndexError: list ind...
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_inner_elements_are_sum_of_above[9] - IndexError: list ind...
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_ngzjg8n2/python_testcases/test_pascal.py::test_pascal_inner_elements_are_sum_of_above[10] - IndexError: list in...
===================================================================================== 37 failed, 9 passed in 0.10s =====================================================================================
```

**原始 `pytest -v` 输出（fixed 侧，节选末尾 60 行）**：

```text
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_inner_elements_are_sum_of_above[2] PASSED                   [ 78%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_inner_elements_are_sum_of_above[3] PASSED                   [ 80%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_inner_elements_are_sum_of_above[4] PASSED                   [ 82%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_inner_elements_are_sum_of_above[5] PASSED                   [ 84%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_inner_elements_are_sum_of_above[6] PASSED                   [ 86%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_inner_elements_are_sum_of_above[7] PASSED                   [ 89%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_inner_elements_are_sum_of_above[8] PASSED                   [ 91%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_inner_elements_are_sum_of_above[9] PASSED                   [ 93%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_inner_elements_are_sum_of_above[10] PASSED                  [ 95%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_n0_behavior_under_precondition_violation PASSED             [ 97%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_negative_n_behavior_under_precondition_violation PASSED     [100%]

======================================================================================= short test summary info ========================================================================================
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_n1_returns_single_row
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_n2_returns_two_rows
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_n3_returns_three_rows
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_n5_returns_expected_triangle
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_n10_returns_expected_triangle
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_result_length_equals_n[1]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_result_length_equals_n[2]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_result_length_equals_n[3]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_result_length_equals_n[4]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_result_length_equals_n[5]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_result_length_equals_n[6]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_result_length_equals_n[7]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_result_length_equals_n[8]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_result_length_equals_n[9]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_result_length_equals_n[10]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_row_lengths_are_i_plus_one[1]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_row_lengths_are_i_plus_one[2]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_row_lengths_are_i_plus_one[3]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_row_lengths_are_i_plus_one[4]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_row_lengths_are_i_plus_one[5]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_row_lengths_are_i_plus_one[6]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_row_lengths_are_i_plus_one[7]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_row_lengths_are_i_plus_one[8]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_row_lengths_are_i_plus_one[9]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_row_lengths_are_i_plus_one[10]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_row_edges_are_one[1]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_row_edges_are_one[2]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_row_edges_are_one[3]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_row_edges_are_one[4]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_row_edges_are_one[5]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_row_edges_are_one[6]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_row_edges_are_one[7]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_row_edges_are_one[8]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_row_edges_are_one[9]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_row_edges_are_one[10]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_inner_elements_are_sum_of_above[2]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_inner_elements_are_sum_of_above[3]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_inner_elements_are_sum_of_above[4]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_inner_elements_are_sum_of_above[5]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_inner_elements_are_sum_of_above[6]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_inner_elements_are_sum_of_above[7]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_inner_elements_are_sum_of_above[8]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_inner_elements_are_sum_of_above[9]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_inner_elements_are_sum_of_above[10]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_n0_behavior_under_precondition_violation
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_pascal_9msqpixh/python_testcases/test_pascal.py::test_pascal_negative_n_behavior_under_precondition_violation
========================================================================================== 46 passed in 0.09s ==========================================================================================
```

**解析后的逐测试分类（node id / buggy / fixed / class）**：

| node id | buggy | fixed | class |
|---|---|---|---|
| `test_pascal.py::test_pascal_inner_elements_are_sum_of_above[10]` | fail | pass | **f2p** |
| `test_pascal.py::test_pascal_inner_elements_are_sum_of_above[2]` | pass | pass | **p2p** |
| `test_pascal.py::test_pascal_inner_elements_are_sum_of_above[3]` | fail | pass | **f2p** |
| `test_pascal.py::test_pascal_inner_elements_are_sum_of_above[4]` | fail | pass | **f2p** |
| `test_pascal.py::test_pascal_inner_elements_are_sum_of_above[5]` | fail | pass | **f2p** |
| `test_pascal.py::test_pascal_inner_elements_are_sum_of_above[6]` | fail | pass | **f2p** |
| `test_pascal.py::test_pascal_inner_elements_are_sum_of_above[7]` | fail | pass | **f2p** |
| `test_pascal.py::test_pascal_inner_elements_are_sum_of_above[8]` | fail | pass | **f2p** |
| `test_pascal.py::test_pascal_inner_elements_are_sum_of_above[9]` | fail | pass | **f2p** |
| `test_pascal.py::test_pascal_n0_behavior_under_precondition_violation` | pass | pass | **p2p** |
| `test_pascal.py::test_pascal_n10_returns_expected_triangle` | fail | pass | **f2p** |
| `test_pascal.py::test_pascal_n1_returns_single_row` | pass | pass | **p2p** |
| `test_pascal.py::test_pascal_n2_returns_two_rows` | fail | pass | **f2p** |
| `test_pascal.py::test_pascal_n3_returns_three_rows` | fail | pass | **f2p** |
| `test_pascal.py::test_pascal_n5_returns_expected_triangle` | fail | pass | **f2p** |
| `test_pascal.py::test_pascal_negative_n_behavior_under_precondition_violation` | pass | pass | **p2p** |
| `test_pascal.py::test_pascal_result_length_equals_n[10]` | fail | pass | **f2p** |
| `test_pascal.py::test_pascal_result_length_equals_n[1]` | pass | pass | **p2p** |
| `test_pascal.py::test_pascal_result_length_equals_n[2]` | pass | pass | **p2p** |
| `test_pascal.py::test_pascal_result_length_equals_n[3]` | fail | pass | **f2p** |
| `test_pascal.py::test_pascal_result_length_equals_n[4]` | fail | pass | **f2p** |
| `test_pascal.py::test_pascal_result_length_equals_n[5]` | fail | pass | **f2p** |
| `test_pascal.py::test_pascal_result_length_equals_n[6]` | fail | pass | **f2p** |
| `test_pascal.py::test_pascal_result_length_equals_n[7]` | fail | pass | **f2p** |
| `test_pascal.py::test_pascal_result_length_equals_n[8]` | fail | pass | **f2p** |
| `test_pascal.py::test_pascal_result_length_equals_n[9]` | fail | pass | **f2p** |
| `test_pascal.py::test_pascal_row_edges_are_one[10]` | fail | pass | **f2p** |
| `test_pascal.py::test_pascal_row_edges_are_one[1]` | pass | pass | **p2p** |
| `test_pascal.py::test_pascal_row_edges_are_one[2]` | pass | pass | **p2p** |
| `test_pascal.py::test_pascal_row_edges_are_one[3]` | fail | pass | **f2p** |
| `test_pascal.py::test_pascal_row_edges_are_one[4]` | fail | pass | **f2p** |
| `test_pascal.py::test_pascal_row_edges_are_one[5]` | fail | pass | **f2p** |
| `test_pascal.py::test_pascal_row_edges_are_one[6]` | fail | pass | **f2p** |
| `test_pascal.py::test_pascal_row_edges_are_one[7]` | fail | pass | **f2p** |
| `test_pascal.py::test_pascal_row_edges_are_one[8]` | fail | pass | **f2p** |
| `test_pascal.py::test_pascal_row_edges_are_one[9]` | fail | pass | **f2p** |
| `test_pascal.py::test_pascal_row_lengths_are_i_plus_one[10]` | fail | pass | **f2p** |
| `test_pascal.py::test_pascal_row_lengths_are_i_plus_one[1]` | pass | pass | **p2p** |
| `test_pascal.py::test_pascal_row_lengths_are_i_plus_one[2]` | fail | pass | **f2p** |
| `test_pascal.py::test_pascal_row_lengths_are_i_plus_one[3]` | fail | pass | **f2p** |
| `test_pascal.py::test_pascal_row_lengths_are_i_plus_one[4]` | fail | pass | **f2p** |
| `test_pascal.py::test_pascal_row_lengths_are_i_plus_one[5]` | fail | pass | **f2p** |
| `test_pascal.py::test_pascal_row_lengths_are_i_plus_one[6]` | fail | pass | **f2p** |
| `test_pascal.py::test_pascal_row_lengths_are_i_plus_one[7]` | fail | pass | **f2p** |
| `test_pascal.py::test_pascal_row_lengths_are_i_plus_one[8]` | fail | pass | **f2p** |
| `test_pascal.py::test_pascal_row_lengths_are_i_plus_one[9]` | fail | pass | **f2p** |

### quixbugs50_batch5 / `quixbugs__next_palindrome`（选取规则：batch5 中 task_id 最小的 f2f>0 套件）

- 归档 detection_rate = `0.0`；本次复算 = `0.0`；suite_class = `invalid_only`
- buggy 侧：rc=1 timed_out=False node ids=33（-v 解析=33） 解析器=plugin+verbose
- fixed 侧：rc=1 timed_out=False node ids=33（-v 解析=33） 解析器=plugin+verbose

**原始 `pytest -v` 输出（buggy 侧，节选末尾 60 行）**：

```text
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_postconditions[digit_list1] PASSED [ 30%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_postconditions[digit_list2] PASSED [ 33%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_postconditions[digit_list3] PASSED [ 36%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_postconditions[digit_list4] PASSED [ 39%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_postconditions[digit_list5] PASSED [ 42%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_postconditions[digit_list6] PASSED [ 45%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_postconditions[digit_list7] PASSED [ 48%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_postconditions[digit_list8] PASSED [ 51%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_postconditions[digit_list9] PASSED [ 54%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_postconditions[digit_list10] PASSED [ 57%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list0] FAILED [ 60%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list1] FAILED [ 63%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list2] FAILED [ 66%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list3] PASSED [ 69%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list4] FAILED [ 72%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list5] FAILED [ 75%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list6] FAILED [ 78%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list7] FAILED [ 81%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list8] PASSED [ 84%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list9] FAILED [ 87%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list10] FAILED [ 90%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_empty_list_precondition_violation PASSED [ 93%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_non_palindrome_precondition_violation PASSED [ 96%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_non_digit_element_precondition_violation PASSED [100%]

======================================================================================= short test summary info ========================================================================================
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_normal_cases[digit_list0-expected0]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_normal_cases[digit_list1-expected1]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_normal_cases[digit_list2-expected2]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_normal_cases[digit_list3-expected3]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_normal_cases[digit_list4-expected4]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_normal_cases[digit_list5-expected5]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_all_nines_expansion[digit_list0-expected0]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_all_nines_expansion[digit_list1-expected1]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_postconditions[digit_list0]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_postconditions[digit_list1]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_postconditions[digit_list2]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_postconditions[digit_list3]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_postconditions[digit_list4]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_postconditions[digit_list5]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_postconditions[digit_list6]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_postconditions[digit_list7]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_postconditions[digit_list8]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_postconditions[digit_list9]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_postconditions[digit_list10]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list3]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list8]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_empty_list_precondition_violation
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_non_palindrome_precondition_violation
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_non_digit_element_precondition_violation
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list0]
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list1]
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list2]
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list4]
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list5]
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list6]
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list7]
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list9]
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_1otk8cx8/python_testcases/test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list10]
===================================================================================== 9 failed, 24 passed in 0.10s =====================================================================================
```

**原始 `pytest -v` 输出（fixed 侧，节选末尾 60 行）**：

```text
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_postconditions[digit_list1] PASSED [ 30%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_postconditions[digit_list2] PASSED [ 33%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_postconditions[digit_list3] PASSED [ 36%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_postconditions[digit_list4] PASSED [ 39%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_postconditions[digit_list5] PASSED [ 42%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_postconditions[digit_list6] PASSED [ 45%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_postconditions[digit_list7] PASSED [ 48%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_postconditions[digit_list8] PASSED [ 51%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_postconditions[digit_list9] PASSED [ 54%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_postconditions[digit_list10] PASSED [ 57%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list0] FAILED [ 60%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list1] FAILED [ 63%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list2] FAILED [ 66%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list3] PASSED [ 69%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list4] FAILED [ 72%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list5] FAILED [ 75%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list6] FAILED [ 78%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list7] FAILED [ 81%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list8] PASSED [ 84%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list9] FAILED [ 87%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list10] FAILED [ 90%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_empty_list_precondition_violation PASSED [ 93%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_non_palindrome_precondition_violation PASSED [ 96%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_non_digit_element_precondition_violation PASSED [100%]

======================================================================================= short test summary info ========================================================================================
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_normal_cases[digit_list0-expected0]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_normal_cases[digit_list1-expected1]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_normal_cases[digit_list2-expected2]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_normal_cases[digit_list3-expected3]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_normal_cases[digit_list4-expected4]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_normal_cases[digit_list5-expected5]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_postconditions[digit_list0]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_postconditions[digit_list1]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_postconditions[digit_list2]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_postconditions[digit_list3]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_postconditions[digit_list4]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_postconditions[digit_list5]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_postconditions[digit_list6]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_postconditions[digit_list7]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_postconditions[digit_list8]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_postconditions[digit_list9]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_postconditions[digit_list10]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list3]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list8]
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_empty_list_precondition_violation
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_non_palindrome_precondition_violation
PASSED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_non_digit_element_precondition_violation
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_all_nines_expansion[digit_list0-expected0]
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_all_nines_expansion[digit_list1-expected1]
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list0]
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list1]
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list2]
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list4]
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list5]
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list6]
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list7]
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list9]
FAILED ../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_next_palindrome_qrlyv40r/python_testcases/test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list10]
==================================================================================== 11 failed, 22 passed in 0.08s =====================================================================================
```

**解析后的逐测试分类（node id / buggy / fixed / class）**：

| node id | buggy | fixed | class |
|---|---|---|---|
| `test_next_palindrome.py::test_next_palindrome_all_nines_expansion[digit_list0-expected0]` | pass | fail | **p2f** |
| `test_next_palindrome.py::test_next_palindrome_all_nines_expansion[digit_list1-expected1]` | pass | fail | **p2f** |
| `test_next_palindrome.py::test_next_palindrome_empty_list_precondition_violation` | pass | pass | **p2p** |
| `test_next_palindrome.py::test_next_palindrome_non_digit_element_precondition_violation` | pass | pass | **p2p** |
| `test_next_palindrome.py::test_next_palindrome_non_palindrome_precondition_violation` | pass | pass | **p2p** |
| `test_next_palindrome.py::test_next_palindrome_normal_cases[digit_list0-expected0]` | pass | pass | **p2p** |
| `test_next_palindrome.py::test_next_palindrome_normal_cases[digit_list1-expected1]` | pass | pass | **p2p** |
| `test_next_palindrome.py::test_next_palindrome_normal_cases[digit_list2-expected2]` | pass | pass | **p2p** |
| `test_next_palindrome.py::test_next_palindrome_normal_cases[digit_list3-expected3]` | pass | pass | **p2p** |
| `test_next_palindrome.py::test_next_palindrome_normal_cases[digit_list4-expected4]` | pass | pass | **p2p** |
| `test_next_palindrome.py::test_next_palindrome_normal_cases[digit_list5-expected5]` | pass | pass | **p2p** |
| `test_next_palindrome.py::test_next_palindrome_postconditions[digit_list0]` | pass | pass | **p2p** |
| `test_next_palindrome.py::test_next_palindrome_postconditions[digit_list10]` | pass | pass | **p2p** |
| `test_next_palindrome.py::test_next_palindrome_postconditions[digit_list1]` | pass | pass | **p2p** |
| `test_next_palindrome.py::test_next_palindrome_postconditions[digit_list2]` | pass | pass | **p2p** |
| `test_next_palindrome.py::test_next_palindrome_postconditions[digit_list3]` | pass | pass | **p2p** |
| `test_next_palindrome.py::test_next_palindrome_postconditions[digit_list4]` | pass | pass | **p2p** |
| `test_next_palindrome.py::test_next_palindrome_postconditions[digit_list5]` | pass | pass | **p2p** |
| `test_next_palindrome.py::test_next_palindrome_postconditions[digit_list6]` | pass | pass | **p2p** |
| `test_next_palindrome.py::test_next_palindrome_postconditions[digit_list7]` | pass | pass | **p2p** |
| `test_next_palindrome.py::test_next_palindrome_postconditions[digit_list8]` | pass | pass | **p2p** |
| `test_next_palindrome.py::test_next_palindrome_postconditions[digit_list9]` | pass | pass | **p2p** |
| `test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list0]` | fail | fail | **f2f** |
| `test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list10]` | fail | fail | **f2f** |
| `test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list1]` | fail | fail | **f2f** |
| `test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list2]` | fail | fail | **f2f** |
| `test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list3]` | pass | pass | **p2p** |
| `test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list4]` | fail | fail | **f2f** |
| `test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list5]` | fail | fail | **f2f** |
| `test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list6]` | fail | fail | **f2f** |
| `test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list7]` | fail | fail | **f2f** |
| `test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list8]` | pass | pass | **p2p** |
| `test_next_palindrome.py::test_next_palindrome_strictly_greater[digit_list9]` | fail | fail | **f2f** |

### quixbugs50_batch5 / `quixbugs__bitcount`（选取规则：batch5 中 task_id 最小的超时套件）

- 归档 detection_rate = `None`；本次复算 = `None`；suite_class = `timeout`
- buggy 侧：rc=None timed_out=True node ids=1（-v 解析=0） 解析器=plugin
- fixed 侧：rc=None timed_out=True node ids=41（-v 解析=40） 解析器=plugin+verbose

**原始 `pytest -v` 输出（buggy 侧，节选末尾 60 行）**：

```text
========================================================================================= test session starts ==========================================================================================
collecting ... collected 41 items

../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_bitcount_9clnyy3d/python_testcases/test_bitcount.py::test_bitcount_127
```

**原始 `pytest -v` 输出（fixed 侧，节选末尾 60 行）**：

```text
========================================================================================= test session starts ==========================================================================================
collecting ... collected 41 items

../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_bitcount_0mo_lskv/python_testcases/test_bitcount.py::test_bitcount_127 PASSED                                            [  2%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_bitcount_0mo_lskv/python_testcases/test_bitcount.py::test_bitcount_128 PASSED                                            [  4%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_bitcount_0mo_lskv/python_testcases/test_bitcount.py::test_bitcount_5 PASSED                                              [  7%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_bitcount_0mo_lskv/python_testcases/test_bitcount.py::test_bitcount_zero PASSED                                           [  9%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_bitcount_0mo_lskv/python_testcases/test_bitcount.py::test_bitcount_one PASSED                                            [ 12%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_bitcount_0mo_lskv/python_testcases/test_bitcount.py::test_bitcount_power_of_two PASSED                                   [ 14%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_bitcount_0mo_lskv/python_testcases/test_bitcount.py::test_bitcount_all_ones PASSED                                       [ 17%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_bitcount_0mo_lskv/python_testcases/test_bitcount.py::test_bitcount_large PASSED                                          [ 19%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_bitcount_0mo_lskv/python_testcases/test_bitcount.py::test_bitcount_postcondition_nonnegative_int[0] PASSED               [ 21%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_bitcount_0mo_lskv/python_testcases/test_bitcount.py::test_bitcount_postcondition_nonnegative_int[1] PASSED               [ 24%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_bitcount_0mo_lskv/python_testcases/test_bitcount.py::test_bitcount_postcondition_nonnegative_int[2] PASSED               [ 26%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_bitcount_0mo_lskv/python_testcases/test_bitcount.py::test_bitcount_postcondition_nonnegative_int[3] PASSED               [ 29%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_bitcount_0mo_lskv/python_testcases/test_bitcount.py::test_bitcount_postcondition_nonnegative_int[5] PASSED               [ 31%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_bitcount_0mo_lskv/python_testcases/test_bitcount.py::test_bitcount_postcondition_nonnegative_int[7] PASSED               [ 34%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_bitcount_0mo_lskv/python_testcases/test_bitcount.py::test_bitcount_postcondition_nonnegative_int[8] PASSED               [ 36%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_bitcount_0mo_lskv/python_testcases/test_bitcount.py::test_bitcount_postcondition_nonnegative_int[127] PASSED             [ 39%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_bitcount_0mo_lskv/python_testcases/test_bitcount.py::test_bitcount_postcondition_nonnegative_int[128] PASSED             [ 41%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_bitcount_0mo_lskv/python_testcases/test_bitcount.py::test_bitcount_postcondition_nonnegative_int[255] PASSED             [ 43%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_bitcount_0mo_lskv/python_testcases/test_bitcount.py::test_bitcount_postcondition_nonnegative_int[1024] PASSED            [ 46%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_bitcount_0mo_lskv/python_testcases/test_bitcount.py::test_bitcount_postcondition_nonnegative_int[18446744073709551615] PASSED [ 48%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_bitcount_0mo_lskv/python_testcases/test_bitcount.py::test_bitcount_matches_bin_count[0] PASSED                           [ 51%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_bitcount_0mo_lskv/python_testcases/test_bitcount.py::test_bitcount_matches_bin_count[1] PASSED                           [ 53%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_bitcount_0mo_lskv/python_testcases/test_bitcount.py::test_bitcount_matches_bin_count[2] PASSED                           [ 56%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_bitcount_0mo_lskv/python_testcases/test_bitcount.py::test_bitcount_matches_bin_count[3] PASSED                           [ 58%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_bitcount_0mo_lskv/python_testcases/test_bitcount.py::test_bitcount_matches_bin_count[4] PASSED                           [ 60%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_bitcount_0mo_lskv/python_testcases/test_bitcount.py::test_bitcount_matches_bin_count[5] PASSED                           [ 63%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_bitcount_0mo_lskv/python_testcases/test_bitcount.py::test_bitcount_matches_bin_count[6] PASSED                           [ 65%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_bitcount_0mo_lskv/python_testcases/test_bitcount.py::test_bitcount_matches_bin_count[7] PASSED                           [ 68%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_bitcount_0mo_lskv/python_testcases/test_bitcount.py::test_bitcount_matches_bin_count[8] PASSED                           [ 70%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_bitcount_0mo_lskv/python_testcases/test_bitcount.py::test_bitcount_matches_bin_count[15] PASSED                          [ 73%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_bitcount_0mo_lskv/python_testcases/test_bitcount.py::test_bitcount_matches_bin_count[16] PASSED                          [ 75%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_bitcount_0mo_lskv/python_testcases/test_bitcount.py::test_bitcount_matches_bin_count[31] PASSED                          [ 78%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_bitcount_0mo_lskv/python_testcases/test_bitcount.py::test_bitcount_matches_bin_count[32] PASSED                          [ 80%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_bitcount_0mo_lskv/python_testcases/test_bitcount.py::test_bitcount_matches_bin_count[63] PASSED                          [ 82%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_bitcount_0mo_lskv/python_testcases/test_bitcount.py::test_bitcount_matches_bin_count[64] PASSED                          [ 85%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_bitcount_0mo_lskv/python_testcases/test_bitcount.py::test_bitcount_matches_bin_count[127] PASSED                         [ 87%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_bitcount_0mo_lskv/python_testcases/test_bitcount.py::test_bitcount_matches_bin_count[128] PASSED                         [ 90%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_bitcount_0mo_lskv/python_testcases/test_bitcount.py::test_bitcount_matches_bin_count[255] PASSED                         [ 92%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_bitcount_0mo_lskv/python_testcases/test_bitcount.py::test_bitcount_matches_bin_count[256] PASSED                         [ 95%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_bitcount_0mo_lskv/python_testcases/test_bitcount.py::test_bitcount_matches_bin_count[1024] PASSED                        [ 97%]
../../../../../../../var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tl_bitcount_0mo_lskv/python_testcases/test_bitcount.py::test_bitcount_negative_undefined_behavior
```

**解析后的逐测试分类（node id / buggy / fixed / class）**：

| node id | buggy | fixed | class |
|---|---|---|---|
| `test_bitcount.py::test_bitcount_127` | error | pass | **other** |
| `test_bitcount.py::test_bitcount_128` | unavailable | pass | **other** |
| `test_bitcount.py::test_bitcount_5` | unavailable | pass | **other** |
| `test_bitcount.py::test_bitcount_all_ones` | unavailable | pass | **other** |
| `test_bitcount.py::test_bitcount_large` | unavailable | pass | **other** |
| `test_bitcount.py::test_bitcount_matches_bin_count[0]` | unavailable | pass | **other** |
| `test_bitcount.py::test_bitcount_matches_bin_count[1024]` | unavailable | pass | **other** |
| `test_bitcount.py::test_bitcount_matches_bin_count[127]` | unavailable | pass | **other** |
| `test_bitcount.py::test_bitcount_matches_bin_count[128]` | unavailable | pass | **other** |
| `test_bitcount.py::test_bitcount_matches_bin_count[15]` | unavailable | pass | **other** |
| `test_bitcount.py::test_bitcount_matches_bin_count[16]` | unavailable | pass | **other** |
| `test_bitcount.py::test_bitcount_matches_bin_count[1]` | unavailable | pass | **other** |
| `test_bitcount.py::test_bitcount_matches_bin_count[255]` | unavailable | pass | **other** |
| `test_bitcount.py::test_bitcount_matches_bin_count[256]` | unavailable | pass | **other** |
| `test_bitcount.py::test_bitcount_matches_bin_count[2]` | unavailable | pass | **other** |
| `test_bitcount.py::test_bitcount_matches_bin_count[31]` | unavailable | pass | **other** |
| `test_bitcount.py::test_bitcount_matches_bin_count[32]` | unavailable | pass | **other** |
| `test_bitcount.py::test_bitcount_matches_bin_count[3]` | unavailable | pass | **other** |
| `test_bitcount.py::test_bitcount_matches_bin_count[4]` | unavailable | pass | **other** |
| `test_bitcount.py::test_bitcount_matches_bin_count[5]` | unavailable | pass | **other** |
| `test_bitcount.py::test_bitcount_matches_bin_count[63]` | unavailable | pass | **other** |
| `test_bitcount.py::test_bitcount_matches_bin_count[64]` | unavailable | pass | **other** |
| `test_bitcount.py::test_bitcount_matches_bin_count[6]` | unavailable | pass | **other** |
| `test_bitcount.py::test_bitcount_matches_bin_count[7]` | unavailable | pass | **other** |
| `test_bitcount.py::test_bitcount_matches_bin_count[8]` | unavailable | pass | **other** |
| `test_bitcount.py::test_bitcount_negative_undefined_behavior` | unavailable | error | **other** |
| `test_bitcount.py::test_bitcount_one` | unavailable | pass | **other** |
| `test_bitcount.py::test_bitcount_postcondition_nonnegative_int[0]` | unavailable | pass | **other** |
| `test_bitcount.py::test_bitcount_postcondition_nonnegative_int[1024]` | unavailable | pass | **other** |
| `test_bitcount.py::test_bitcount_postcondition_nonnegative_int[127]` | unavailable | pass | **other** |
| `test_bitcount.py::test_bitcount_postcondition_nonnegative_int[128]` | unavailable | pass | **other** |
| `test_bitcount.py::test_bitcount_postcondition_nonnegative_int[18446744073709551615]` | unavailable | pass | **other** |
| `test_bitcount.py::test_bitcount_postcondition_nonnegative_int[1]` | unavailable | pass | **other** |
| `test_bitcount.py::test_bitcount_postcondition_nonnegative_int[255]` | unavailable | pass | **other** |
| `test_bitcount.py::test_bitcount_postcondition_nonnegative_int[2]` | unavailable | pass | **other** |
| `test_bitcount.py::test_bitcount_postcondition_nonnegative_int[3]` | unavailable | pass | **other** |
| `test_bitcount.py::test_bitcount_postcondition_nonnegative_int[5]` | unavailable | pass | **other** |
| `test_bitcount.py::test_bitcount_postcondition_nonnegative_int[7]` | unavailable | pass | **other** |
| `test_bitcount.py::test_bitcount_postcondition_nonnegative_int[8]` | unavailable | pass | **other** |
| `test_bitcount.py::test_bitcount_power_of_two` | unavailable | pass | **other** |
| `test_bitcount.py::test_bitcount_zero` | unavailable | pass | **other** |

### 6.1 独立复核（重跑 + 读 pytest 自身汇总行，不走本脚本解析器）

| 任务 | buggy rc | buggy pytest 汇总行 | 工件 buggy(pass/fail) | fixed rc | fixed pytest 汇总行 | 工件 fixed(pass/fail) | 判定 |
|---|---|---|---|---|---|---|---|
| `quixbugs50_batch5/quixbugs__pascal` | 1 | `===================================================================================== 37 failed, 9 passed in <t>s ==============================================` | 9/37 | 0 | `========================================================================================== 46 passed in <t>s ===================================================` | 46/0 | **match** |
| `quixbugs50_batch5/quixbugs__next_palindrome` | 1 | `===================================================================================== 9 failed, 24 passed in <t>s ==============================================` | 24/9 | 1 | `==================================================================================== 11 failed, 22 passed in <t>s ==============================================` | 22/11 | **match** |
| `quixbugs50_batch5/quixbugs__bitcount` | `unmeasured` | `(超时终止，无 pytest 汇总行)` | `unmeasured`/`unmeasured` | `unmeasured` | `(超时终止，无 pytest 汇总行)` | `unmeasured`/`unmeasured` | **reproduced_timeout** |

> `match` = pytest 自身汇总行计数与工件逐测试表推出的该侧 (pass, fail+error) 逐位相等；
> `reproduced_timeout` = 两侧再次在 30s 上限超时（超时套件在工件中一律记 `other`，不产生 f2p）。

## 7. 局限与未测量项（诚实清单）

- 30s 上限口径（与 emse_test_sanity_audit.py 同）：任一侧超时 → 该套件记 `other`/`timeout`，**不**计入 f2p（超时套件清单见 JSON `aggregates`）。pooled buggy 侧超时 5 个任务（quixbugs__bitcount, quixbugs__find_first_in_sorted, quixbugs__sqrt, quixbugs__to_base, quixbugs__wrap）；fixed 侧超时 4 个（quixbugs__bitcount, quixbugs__sqrt, quixbugs__to_base, quixbugs__wrap）。buggy 侧挂死是「套件在缺陷代码上不终止」——是否算检出取决于口径选择，本件保守记 other 并单列。
- 归档 `detection_rate` 的判分链路用 120s 上限（`_run_pytest_in_tmp` 默认），本件用 30s；因此本件复算的 `task_level_reproduced` 与归档值在**慢任务**上可能不同，差异逐条列于 README §5，不静默。
- `test_level` 三种口径互不替代：(a) 测试级严格配对（按 node id，n 小）；(b) 任务聚类（n=任务数，防伪重复）；(c) 各臂边际 f2p 率（不配对）。三者的 p/δ 不可混引。
- 逐测试分类的「失败」含 call 相位断言失败与 setup/teardown 异常；相位细分见 §3.5，§3.5 的「call 相位失败」含断言失败**与**测试体内未捕获异常（被测缺陷代码直接抛出的 IndexError/TypeError 等）——两者都是真实的缺陷触发路径；setup/teardown 异常单列。若审稿人只想看断言失败，需按失败消息二次过滤（本件 JSON 只存相位级，不存失败消息 → 该细分 unmeasured）。
- 两路解析交叉校验：插件 JSONL 为主，`-v` 文本为辅；两侧不一致条数 0（0 = 完全一致）。
- 9 个 `quixbugs__*_test` 伪程序（QuixBugs `python_programs/*_test.py`）无官方 gold 材料，逐源排除（每源 9 个），不计入任何分母。
- QuixBugs 辅助模块（node.py / load_testdata.py / json_testcases）就绪=True；依赖辅助模块的套件数见 JSON `tasks[].needs_quixbugs_support`。
- 未测量项（`unmeasured`）：无 gold 材料任务的测试级分类、超时套件内部的逐测试结果、以及各臂「未归档套件」（归档工件只含每任务最终套件——迭代中间产物不在口径内）。
- 本件只覆盖 QuixBugs（唯一同时具备 defect 版 / gold 修复版 / 官方测试的基准）；ULT 生成套件无 buggy 侧（replace 口径）故**不可**做双侧测试级分类——明确记为 unmeasured，不猜。

## 8. 机器可读字段

`TESTLEVEL_DETECTION.json`：`meta`（来源/sha256/口径/墙钟）、`aggregates.per_source`、`aggregates.pooled`、
`tasks`（逐套件逐测试分类 + 双路解析计数 + stdout 哈希）、`testlevel_stats`、`handcheck`（含原始 -v 输出）。

