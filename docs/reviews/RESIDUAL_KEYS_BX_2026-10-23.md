# BX 轮：写而不读键池最后两键的读侧从未披露（零 LLM，$0）

登记日 2026-10-23；实测自 2026-10-23（本机 macOS，Python 3.14.6，pytest 9.1.1）。

## 1. 发现

BU 普查量出的 13 键 / 76,488 行「只写不读」池，经 BV（41,545 行）、BW（22,035 行）
两轮收口后只剩最后两键：`risk_summary`（8,864 行）与 `mdo_crash_rate`（4,044 行），
合计 12,908 行。两者在报告面**零读者**，且各自把多种事实折叠成同一个值：

| 键 | 写入点 | 归档行 | 沉默形态 |
|---|---|---|---|
| `risk_summary` | 风险门（BM 起 `contract_status` 透传） | 8,864（另 2,333 行键缺席） | `enabled=False` 占位与「通道开着且全部低风险」同形；`risk_level=None` 与 `low` 同形；键缺席与低风险同形；`pause_requested=False` 在通道关闭时恒为 False |
| `mdo_crash_rate` | MDO 测量出口 | 4,044（另 7,153 行键缺席） | 五层输入域（未跑 / 材料缺 / 不可测 / 暂定池 / 实测）共用一个 `None`；`mdo_pool_floor_ok=False` 是两义键；暂定池原始值落在未读的 `mdo_raw` |

归档实测（`experiments/results/`：257 份批次文件 / 11,197 条结果行；全部读数见 §4）：

| 事实 | 数值 |
|---|---|
| `risk_summary` 在场 / 缺席 | **8,864** / 2,333（缺席行早于该键落盘） |
| `enabled` | `True` **0** / `False` **8,864** / 键缺席 0 ⇒ **全归档通道关闭** |
| 7 键形状 / 6 键形状 / 其它 | **8,012** / **852** / 0（差别只在 `pause_requested` 是否在场） |
| `risk_level` / `approval_action` / `risk_score` 非空 | **0** / 0 / 0（占位三字段） |
| `pause_requested` | `True` 0 / `False` **8,012** / 缺席 **852** / 非布尔 0 |
| `contract_status` 在场 | **0**（在 8,864 行在场记录里一次也没出现） |
| 占位失配（enabled 与三字段口径冲突） | **0** |
| `mdo_crash_rate` 五层 | 未跑 **2,312** / 材料缺 **122** / 不可测 **986** / 暂定池 **530** / 实测 **94**（合计 = 键在场 4,044） |
| 未给出规范值的成因 | `test_not_green_on_base(rc=1)` 947 / `no_gold_material` 116 / `no_gold_fixed_material` 6 / `baseline_timeout` 38 / `baseline_execution_error` 1 / 无 reason 2,312 |
| 规范值非空 | **94**（`0.0` **79** / ≠0 **15**，均值 **0.3978%**，最大 2.94%） |
| 池化 crash（反推分子） | **15 / 3,200 = 0.46875%**；歧义 0 / 失败 0 |
| 暂定池原始值（`mdo_raw`） | **530**（`0.0` 518 / ≠0 12），池化 **12 / 7,190 = 0.1669%** |
| `mdo_pool_floor_ok=False` | **1,516** = 暂定池 **530** + 不可测 **986**（后者是 `MDOResult` 默认值） |
| provisional 标记缺失 | **2,434** |
| 可评估计数五键在场 | **0**（`mdo_status` / `mdo_evaluable` / `mdo_non_terminating` / `mdo_probe_invalid` / `mdo_no_effective_pass`） |

四条事实值得单独点名：

1. **「通道没开」不是「全部低风险」。** 8,864 行 `risk_summary` 全部 `enabled=False`，
   `risk_level` 非空 0 行。`level=None` 若被读成 `low`，整份归档会得到「零高风险」的
   假读数；`pause_requested=False` 同理——通道关闭时它恒为 False，不构成「判定无需暂停」。
2. **键缺席与低风险是两件事。** 2,333 行早于该键落盘，报告面必须单列「键缺席」，
   不得并进 `enabled=False`。`contract_status` 在 8,864 行在场记录里 0 次出现
   ⇒「缺失符号为空可不可信」在归档上**没有证据**，不能写成已确认。
3. **`mdo_crash_rate` 的 `None` 有五层原因。** 未跑 2,312 / 材料缺 122 / 不可测 986 /
   暂定池 530 / 实测 94 共用一个空值；只有 94 行有规范值（79 行实测零崩溃，15 行非零）。
   把 `None` 读成 0，或把暂定池的 `mdo_raw` 与实测值合并，都会改写分母。
4. **`mdo_pool_floor_ok=False` 是两义键。** 1,516 行里 530 行是暂定池，986 行是
   `MDOResult` 的默认值（不可测），**不是池不足**；直接按该键筛「池不足」会多算 986 行。
   crash 分母是**全池 `n`**（含 `non_terminating` / `probe_invalid` / `no_effective_pass`），
   与 MTR/MDR 的**可评估**分母不同；可评估计数五键归档 0 行 ⇒ 可评估分母无法复算。

键池闭合（§61① 读法口径）：BU 池 13 键 / 76,488 行 = BV 41,545 + BW 22,035 +
BX 12,908；BX 接入后**全树零读者池为空**（A 段复核）。

## 2. 处置

**单一事实源**：新增 `experiments/_residual_keys.py`

- 键名常量与词表：`RISK_KEY` / `CRASH_KEY`、占位三字段、`CRASH_LAYERS`（五层）、
  `CRASH_UNMEASURED_LAYERS`（前三层）、`MDO_EVALUABILITY_KEYS`（五键）。
- 读侧原语：`crash_layer`（键缺席 → `None`；`mdo_available is None` 且无可用 reason →
  未跑；有 reason → 材料缺；`False` → 不可测；`mdo_provisional is True` → 暂定池；
  其余 → 实测）、`_value_summary`、`_reconstruct_count`（`round(c/n,4)==rate` 的唯一
  整数解；歧义 / 失败只计数、不猜）、`_pooled`（精确比值，不四舍五入）。
- 缺席与类型纪律：字符串布尔显式折叠；`pool_size` 为 bool / 非正整数、`rate` 为 bool /
  非数值一律返回 `None`；`pause_requested` 键在场但非布尔单列 `other`，不折进 `false`；
  只有 `enabled is True` 的行才计入「level 可读」，`enabled=False` 行的残留级别值
  只由占位失配计数，不读成可读级别。

**读端**：`statistical_analysis.residual_keys_stats(rows)`——risk 侧：在场 / 缺席 /
非字典、enabled 三态、7 键与 6 键形状、占位字段非空、占位失配、pause 四桶、
`contract_status` 在场；crash 侧：五层、未测三层的成因、值域四分（非空 / 0 / ≠0 / 空）、
池化（精确）、暂定池原始值（独立池化）、`floor_false` 两义分解、provisional 标记缺失、
可评估计数在场行数。

**报告面**：`analyze_results.py` 新增章节「写而不读键池的收口（BX：`risk_summary` 与
`mdo_crash_rate` 的读侧）」——两张表（13 / 14 列）+ 每臂行 + `**合计**` 行 + 脚注：
`level=None` 不是 `low`、`pause_requested=False` 不是判定、键缺席不等于低风险、
`contract_status` 无证据、五层输入域与成因、`floor_false` 两义键、全池分母 vs 可评估
分母、`None` 不是 0、行均值 vs 池化、暂定池原始值不与实测合并；外部口径（联网核对）：
NIST SP 800-30 的风险等级是半定量分箱的序数标签（不是概率），Google Play
`vitals.crashrate` 以去重用户数归一化且禁止再聚合、per-session 与 per-request 分母
不同 ⇒ crash 率必须带分母、两个分母的读数不得相减。
`run_main_batch._print_r4_summary` 增一行摘要（BX 残池），批次跑完即可见。
**不进入任何判定，不改 passed / repair / 分母，也不回填历史行。**

**棘轮**：BQ 的 per-baseline 键集棘轮新增 `residual_keys`（只增不删）。

**口径分列**：报告渲染走 `load_experiment_results`（默认口径），§1 与普查走**全 JSON
原始扫描**（257 文件 / 11,197 行）。两套口径都登记，不混用；本册所有归档读数均为后者。

## 3. 验证

### 3.1 测试

| 项 | 读数 |
|---|---|
| BX 新锁 | `tests/test_residual_keys_bx.py` **102 例**（含 3 个具名冻结批次逐档对账）全绿 |
| collected | **12,472** = 12,467 passed + 5 skipped（12,370 BW 基线 + 102 例） |
| 预登记全量跑 | **12,465 passed / 5 skipped / 2 failed、250.80s / rc=1**；两红均为本轮引入的旧契约：`total_passed` 仍为 12,365、per-baseline 键集棘轮未登记 `residual_keys`。修复后两套件 **2 passed** |
| 确认跑 | **12,467 passed / 5 skipped / 0 failed、102 warnings、221.53s / rc=0**（`make gates` 链内 pytest，collected 12,472；逐项见 §3.3） |
| 旧契约 | 1 处扩展（键集棘轮 +1）；`BASELINE.yaml` 的 `tests.total_passed` 刷新为 12,467（由本轮新增 102 例决定，不是改测试） |
| 覆盖率 | 与 BW 逐位相同：行 **19538/20052 = 97.4367%**、弧 **7150/7584 = 94.2774%**（`git status --porcelain src/` 命中 0） |

### 3.2 变异

`scripts/tools/bx_mutation_verify.py`：**44 个锚点（43 个变异 + 1 个中性对照 N01）**。
干净树先全绿且 collected 一致（恒 102）→ 逐锚点读原字节 → 写变异 → `compile()` →
收集数核对 → 跑受影响面 → **sha256 校验后按原字节还原**（不用 `git checkout` / `git stash`）。
锚点方向：每一处都是「把 BX 补的读侧退回沉默、退回并档、退回同形」——判定原语
（键缺席读成未跑 / 不可测并进未跑 / 暂定池并进实测 / 字符串真值 / bool 守卫 / 歧义取首解 /
失败读成零 / 实测零被丢弃 / null 计入零 / 空值摘要写成 0 / 均值精度 / floor 两义擦除 /
两处不一致 / 占位失读 / 形状合并）、报告披露（标题 / 表头 / 三处口径句 / 外部口径 /
两义键 / 分母句 / 原始值 / 比率精度 / 无行渲染 / contract 硬编码）与摘要接线。
结果：**43/43 变异转红，对照 0 红，rc=0，`# mutation: ` 残留 0**。

### 3.3 门禁

- `make gates` 全链 **rc=0**（干净树；链内 pytest、ruff、mypy、双语文档、文档链接、
  env-budget、BASELINE、状态通道、env-snapshot、JSON 契约、JSON strict、报告对账、
  零断言、ast-guards、状态落盘全部通过；逐项读数如下）。

<!-- BX-GATES:BEGIN -->
- `make gates` 全链 **rc=0**（干净树；墙钟 **229s**，`date +%s` 成对采集）；链内 pytest
  xdist `-n 4 --dist loadfile`、**不带 `--cov`**：**12,467 passed / 5 skipped / 0 failed、
  221.53s**、102 warnings、collected **12,472**；`ruff check` 全通过、`ruff format --check .`
  **1030 文件已格式化**、mypy **137 源文件 0 错**；双语文档 **0 警告 / 0 失败**；文档链接
  **192 份 / 846 条 / 0 错误 / 0 警告**；env-budget **253/253**；BASELINE 结构与数字通过
  （当前基线块零硬编码）；状态通道 **136 文件**；env-snapshot **84/84**、缺失 0；tool-versions
  OK；JSON 契约 **7/7**（9 处文档数量表述 [OK]）；JSON strict **7274 工件 = 7272 严格 + 2 登记
  豁免 + 0 违规**、**343 源文件 0 写入点违规**；报告→工件对账 **[OK]**（1 份文档 × 3 臂 ×
  11 列，容差 0.0005；T-10 严格 29 行 / 25 可测、宽松 62 / 55；登记册覆盖率对账相符）；
  零断言 **471 测试文件 0 违规**；ast-guards **136 文件 / 79 站点 / 未覆盖 20 / 违规 0 /
  豁免命中 20 / EXEMPT 19**；状态落盘 **10 通道 / 3 面全覆盖**。
- **首跑失败不计通过**：第一次 `make gates` 在 `ruff format --check .` 以 rc=2 终止
  （0s）——`scripts/tools/bx_mutation_verify.py` 的变异锚点用单引号包裹含双引号的字符串，
  格式化器要求改写为双引号。`ruff format scripts/tools/bx_mutation_verify.py` 后重跑变异
  **43/43 变异转红 / 对照 0 红**（collected 恒 102、`# mutation: ` 残留 0），再跑门禁
  rc=0。本册只登记修好后的确认读数。
<!-- BX-GATES:END -->

### 3.4 只读普查三段

`scripts/tools/bx_residual_keys_census.py`（默认跑 A/B/C；`--segment a|b|c` 单段）：

- **A 段**（AST 读者普查 + 键池）：全树零读者 **0 键 / 0 行**；
  `risk_summary` row_read 4（报告面 4）、`mdo_crash_rate` row_read 5（报告面 5）；
  闭合恒等式 **41,545 + 22,035 + 12,908 = 76,488** 成立。
- **B 段**（全归档 257 文件 / 11,197 行）：§1 表逐项一致；风险形状 8,012 + 852 = 8,864、
  crash 五层 2,312 + 122 + 986 + 530 + 94 = 4,044、`floor_false` 1,516 = 530 + 986 全部成立；
  两处不一致计数（占位失配 0、反推歧义 0 / 失败 0）成立。
- **C 段**（三个具名冻结批次逐档核对）：**3/3 OK**，零 DRIFT；读数与测试里的
  `PINNED_BATCHES` 同源，C 段从测试文件 `ast.literal_eval` 读取期望值，不手抄。

## 4. 复现

```bash
# A/B/C. 三段只读普查（全 JSON 扫描，含 schema 混批）
.venv/bin/python scripts/tools/bx_residual_keys_census.py
# 实测：批次 257 / 行 11197；零读者池 0 键 / 0 行
#   risk_summary 在场 8864 / 缺席 2333；enabled_true 0 / enabled_false 8864
#     形状 7 键 8012 + 6 键 852；level 非空 0；pause false 8012 / absent 852；contract 0
#   mdo_crash_rate 五层 2312 / 122 / 986 / 530 / 94
#     值 94（0 79 / ≠0 15，均值 0.003978）；池化 15/3200 = 0.0046875
#     暂定原始值 530（0 518 / ≠0 12，池化 12/7190 = 0.00166898...）
#     floor=False 1516 = 530 + 986；可评估计数在场 0 行
#   键池闭合 41545 + 22035 + 12908 = 76488

# B. 报告章节（两张表 + 脚注）
.venv/bin/python experiments/analyze_results.py --input <batch.json>

# C. 变异验证（44 锚点 = 43 变异 + 1 对照）
.venv/bin/python scripts/tools/bx_mutation_verify.py
```

## 5. 未做 / 边界

- **不回填历史行**：2,333 行 `risk_summary` 键缺席、7,153 行 `mdo_crash_rate` 键缺席——
  报告面显示为「键缺席」，不折成低风险 / 零崩溃。
- **不动判定值与方向**：两键的写侧与任何行的值一处不动；本轮 `src/` 零改动
  （`git status --porcelain src/` 命中 0）。
- **不进入任何判定**：五层分档、池化、均值与 `floor_false` 分解都不改 passed / repair / 分母。
- **`level=None` 不是 `low`**：全归档 `enabled=True` 0 行，没有开启记录就没有可读级别；
  NIST SP 800-30 的序数标签语义不提供「空 = 最低档」的读法。
- **crash 分母不可替换**：全池 `n` 与 MTR/MDR 的可评估分母不同；可评估计数五键归档 0 行
  ⇒ 可评估分母**无法从归档复算**，crash 率不得与 MDR 相除或相减。
- **暂定池原始值不合并**：`mdo_raw` 的 530 行（12/7,190）与规范值 94 行（15/3,200）
  是两个口径，报告分列，不求和、不求平均。
- **两义键不重定义**：`mdo_pool_floor_ok=False` 的 986 行不可测是 `MDOResult` 默认值，
  读侧只分解、不改写该键，也不把它读成「池不足」。
- **英文索引/README 同步**：本轮八处日期行、README 双语、CHANGELOG 双语、INDEX 双语、
  测量廉洁 §68、状态登记册与 AO3 锁全部前滚；英文索引补 BX 行，不代补更早的历史漂移。

## 6. 本轮自纠

| # | 自纠项 | 说明 |
|---|---|---|
| ① | **`level_nonnull` 把 disabled 行的残留值算成「可读级别」** | 初版对全部行取 `risk_level is not None`，夹具里一条 `enabled=False` 但残留 `level="low"` 的行让计数变成 2；归档上这会把写侧缺陷读成「有级别」。修法：只统计 `enabled is True` 的行，残留值交给 `placeholder_mismatch` 单列（与报告脚注「没有开启记录就没有可读级别」对齐）。 |
| ② | **`contract_status` 夹具期望少算一行** | 期望写成 `present=1`，实际第 3 行夹具也带该键 ⇒ 2；修法改期望为 `{"present": 2, "absent": 7}`，并保留「整份归档 present=0」的结论——夹具与归档不混用。 |
| ③ | **pause 桶与表列数的期望先于实跑手算错** | `pause=False` 期望 4（实际 3：四条缺席 + 一条非布尔 `other`）；表行数期望 3（实际 4：表头 + 分隔 + 单臂 + 合计）。两处在跑之前按夹具重算纠正，**不以测试输出反推期望**。 |
| ④ | **`ast.literal_eval` 容不下 `2 / 192`** | 具名批次的 `rate` 初写成表达式 `2 / 192`，C 段与 `PINNED_BATCHES` 都要求字面量；改为 `0.010416666666666666`，并在测试里按精确比值断言。 |
| ⑤ | **变异锚点缩进与源码不匹配** | F05 锚点用了 8 空格，源码是 4 空格，precheck 命中 0；改为源码缩进后 44/44 通过。**锚点必须是原字节的精确子串，缩进也是锚点的一部分。** |
| ⑥ | **新增工具与测试未过 ruff format** | `scripts/tools/bx_residual_keys_census.py` 与 `tests/test_residual_keys_bx.py` 首轮 `ruff format` 需重排；格式化后重跑普查与 102 例，读数不变。 |
| ⑦ | **预登记全量跑的两红都是本轮自己造成的** | `total_passed` 仍是 12,365（新增 102 例未计数）、per-baseline 键集棘轮未登记 `residual_keys`。两处都在本轮收口：前者刷新 BASELINE，后者在棘轮里显式 +1；**不得把这两红登记成「环境问题」**。 |
| ⑧ | **用时要先证同并行度** | 本轮预登记跑 250.80s 与 BW 的 600.17s（单进程）不可直接互比；登记只写本轮口径，确认跑以 `make gates` 链内 xdist 读数为准。 |
