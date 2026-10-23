# BY 轮：报告的「分析集流量」从未披露（零 LLM，$0）

登记日 2026-10-23；实测自 2026-10-23（本机 macOS，Python 3.14.6，pytest 9.1.1）。

## 1. 发现

报告 `## 数据来源` 只列**纳入**的批次文件。读者看到「110 个批次 / n=561」时，
看不到加载器在到达该清单之前已经做了四层剔除，也看不到载入之后配对之前
还折叠了一道去重：

1. 扫描面只认 `benchmark_*.json`（归档里另有非 benchmark 命名的结果文件）；
2. 数据集白名单 `synthetic` / `quixbugs` 之外整份丢弃；
3. schema 完备（默认口径）：`detection_rate` 全 None 的批次整份丢弃
   （`--allow-schema-mixed` 恢复）；
4. 基线白名单：未登记的臂整臂丢弃；
5. 行级去重：同一 `task_id` 只保留最新批次一行（`latest_rows_by_task`）；
6. 字段 None：去重后、配对前剔除该字段为 None 的任务（不是 0）。

归档实测（`experiments/results/`，加载器 glob 口径；全部读数见 §4）：

| 事实 | 数值 |
|---|---|
| 扫描面（`benchmark_*.json`） | **246 份 / 10,659 行** |
| 数据集白名单外 | **77 份 / 886 行**（`examples` 50 / `swe_bench` 11 / `ult` 6 / `swe_bench_pro` 6 / `o3_cross_file` 2 / `<缺失>` 2） |
| schema 不完备（默认剔除） | **59 份 / 2,463 行**（含 2 份 `.mdo.json` 旁车，0 行） |
| 读取 / 加载失败 | **0 份 / 0 行** |
| 未登记基线（行） | **300**（`plain_llm_df_spec` 150 / `plain_llm_df_doc` 50 / `plain_llm_df_doc_union` 50 / `plain_llm_df_doc_augment` 50） |
| 载入 | **110 份 / 7,310 行_all / 7,010 行_tracked** |
| 重复 `task_id` 折叠 | **6,449**（占载入行 **91.997%**） |
| 唯一 task 行 | **561** |
| 缺 `task_id` 行 | **0** |
| 字段 None / 可测 | `passed` 0 / 561；`detection_rate` **45 / 516**；`repair_rate` **52 / 509** |
| 扫描面之外（全归档带 `results`） | **257 份 / 11,197 行**；非 `benchmark_*` 命名 **13 份 / 538 行** |
| 混批口径（`--allow-schema-mixed`） | **169 份 / 9,473 行**；重复 **8,494**；唯一 **979**；`detection_rate` None **463 / 516**、`repair_rate` None **470 / 509** |

三层对账（报告面逐句写出，任一不闭合即直书「对账未闭合」）：

- `10,659 − 886 − 2,463 − 300 = 7,010`（扫描 − 三层剔除 = 载入 tracked 行）；
- `7,010 = 561 + 6,449`（载入 = 唯一行 + 重复折叠）；
- `9,473 − 7,010 = 2,463`（混批口径与默认口径之差恰为 schema 层）。

四条事实值得单独点名：

1. **「载入 7,010 行」不是 n。** 去重折叠了 **6,449 行（91.997%）**，配对单元
   只有 **561** 个唯一任务行；把载入行数当 n 会放大样本量 12.5 倍。外部口径
   （Hurlbert 1984 伪重复）要求 n 只数独立观测单元，折叠本身是对的，
   **折叠量必须披露**。
2. **整份剔除与行内折叠是两种剔除。** PRISMA 2020 流程图要求逐阶段记录数量
   与排除理由，且流程图与正文/结果表必须一致；本表把「整份文件剔除」
   （数据集 886 行 / schema 2,463 行）与「行级折叠」（未登记基线 300 行 /
   重复 6,449 行）分成两段，读者才能核对 `## 数据来源` 的 110 份清单之前
   丢了什么。
3. **扫描面之外还有结果文件。** 全归档带 `results` 的 JSON 有 257 份 / 11,197 行，
   其中 **13 份 / 538 行**不叫 `benchmark_*`，连扫描面都没进；报告首行必须
   写明本表扫描面是 246 份，而不是把 257 当成「全部」。
4. **字段 None 不是 0。** `detection_rate` 在 561 个唯一行里 45 行不可测、
   `repair_rate` 52 行不可测；它们不进配对分母，也不折成 0 参与均值。
   混批口径下不可测行升到 463 / 470，两个口径的读数不可混用。

## 2. 处置

**单一事实源**：新增 `experiments/_analysis_flow.py`

- 词表与顺序：`BATCH_GLOB = "benchmark_*.json"`、`FLOW_FIELDS = ("passed",
  "detection_rate", "repair_rate")`、`LAYER_ORDER = ("included",
  "unsupported_dataset", "schema_incomplete", "read_error", "load_error")`。
- 文件级归层：`classify_document` 按 `_load_batch_file` 的判定顺序（数据集 →
  schema → `results` 形状 → 将被加载的基线块形状）逐层归因；任何会让加载器
  整份返回 False 的异常记 `load_error`，不猜成 schema 或数据集原因。
  `batch_is_m1_schema_complete` 与加载器引用同一判据，不各写一份。
- 流量账：`flow_stats`（glob / 白名单两种模式；白名单重复路径只算一次，
  解析失败记 `read_error`，不回退 glob）、`loaded_flow`（去重与 None 分成
  两步，去重原语与配对同为 `latest_rows_by_task`）、`archive_universe`
  （扫描面之外的结果文件盘点，只读、不做加载或判定）。
- 混批口径：`--allow-schema-mixed` 下 schema 层不剔除，但另记
  `schema_incomplete_if_default`（默认口径会剔除多少份/行），避免报告里
  该行显示 0 被读成「没有 schema 不完备批次」。

**读端**：`statistical_analysis.analysis_flow_stats(results, results_dir,
batch_files, allow_schema_mixed)`——在加载器产出 `results` **之后**读取同一
扫描面重新分类，再对 `results` 做行级流量账；三层对账（扫描 − 剔除 = 载入；
载入 tracked 行 = 实际 `results` 行；行 = 唯一 + 重复 + 缺 task_id）任一不闭合
时 `reconciles=False`。

**报告面**：`statistical_analysis` 生成的 `## 数据来源` 节新增子章节「分析集流量
（BY：逐层剔除与去重）」——一张 4 列表（层 / 文件 / 行 / 说明）、三层对账句、
扫描面之外脚注、混批口径脚注、外部口径两条脚注；`run_all_statistics` 构建报告时
按同一份流量账打印一行控制台读数（扫描 → 四层剔除 → 载入 → 折叠 → 唯一 + 字段
None），批次跑完即可见。**不进入任何判定，不改 passed / repair / 分母，也不回填
历史行。**

**口径分列**：报告渲染走 `load_experiment_results`（默认 glob 口径），§1 的
归档宇宙（257 / 11,197）走 `archive_universe` 的原始 `*` 扫描；两套口径都
登记，不混用。混批口径单列，不与默认口径相减。

## 3. 验证

### 3.1 测试

| 项 | 读数 |
|---|---|
| BY 新锁 | `tests/test_analysis_flow_by.py` **27 例**（分类顺序 5 / schema 与行数 3 / 文件级 4 / 行级 5 / 渲染与摘要 5 / 5 个具名冻结批次 5）全绿 |
| collected | **12,499** = 12,494 passed + 5 skipped（12,472 BX 基线 + 27 例） |
| 预登记全量跑 | **12,493 passed / 5 skipped / 1 failed、601.91s（0:10:01）、rc=1**（collected 12,499；单进程口径，与 xdist 读数不可互比）；唯一红 = 基线守卫：实收 12,499 − `total_passed` 12,467 = 32 > 6，恰为新增 27 例 + 5 skip；BASELINE 刷新后转绿 |
| 确认跑 | **12,494 passed / 5 skipped / 0 failed、40 warnings、217.79s / rc=0**（`make gates` 链内 pytest，xdist `-n 4 --dist loadfile`、不带 `--cov`；collected **12,499**；链墙钟 **224s**，`date +%s` 成对采集） |
| 旧契约 | 无既有断言改写；`BASELINE.yaml` 的 `tests.total_passed` 刷新为 12,494（由本轮新增 27 例决定，不是改测试） |
| 覆盖率 | 与 BX 逐位相同：行 **19538/20052 = 97.4367%**、弧 **7150/7584 = 94.2774%**（`git status --porcelain src/` 命中 0） |

### 3.2 变异

`scripts/tools/by_mutation_verify.py`：**46 个锚点（45 个变异 + 1 个中性对照 N01）**。
干净树先全绿且 collected 一致（恒 27）→ 逐锚点读原字节 → 写变异 → `compile()` →
收集数核对 → 跑受影响面 → **sha256 校验后按原字节还原**（不用 `git checkout` /
`git stash`）。锚点方向：每一处都是「把 BY 补的读侧退回沉默、退回并档、退回同形」——
分类顺序（数据集先于 schema / schema 先于形状 / 白名单先于 schema）、行数口径
（只数 tracked 行 / 把未登记基线并进 tracked / 重复数改成正数 / 缺 task_id 并进重复）、
混批口径（schema 层照剔 / 默认层不记）、报告披露（标题 / 表头 / 对账句 / 外部口径 /
扫描面之外 / 混批脚注 / None 行）、摘要接线与逐基线字段。结果：**45/45 变异转红，
对照 0 红，rc=0，`# mutation: ` 残留 0**。

### 3.3 门禁

- `make gates` 全链 **rc=0**（干净树；逐项读数如下）。

<!-- BY-GATES:BEGIN -->
- `make gates` 全链 **rc=0**（干净树；墙钟 **224s**，`date +%s` 成对采集）；链内 pytest
  xdist `-n 4 --dist loadfile`、**不带 `--cov`**：**12,494 passed / 5 skipped / 0 failed、
  40 warnings、217.79s**、collected **12,499**；`ruff check` 全通过、`ruff format --check .`
  **1035 文件已格式化**、mypy **137 源文件 0 错**；双语文档 **0 警告 / 0 失败**；文档链接
  **193 份 / 851 条 / 0 错误 / 0 警告**（内部 842 / 外链 9；文件 810 / 目录 4 / 锚点 28；
  较 §3.3 首登记的 849 条 / 文件 808 多出的 2 条，全部来自 §6⑨ 收口修复在两个 README
  轮换行里各新增的一处 `[BASELINE.yaml](BASELINE.yaml)` 链接，非新增文档）；
  env-budget **253/253**；BASELINE 结构与数字通过（当前基线块零硬编码）；状态通道
  **136 文件**；env-snapshot **84/84**、缺失 0（快照 115 键）；tool-versions OK；JSON 契约
  **7/7**（9 处文档数量表述 [OK]）；JSON strict **7274 工件 = 7272 严格 + 2 登记豁免 +
  0 违规**、**343 源文件 0 写入点违规**；报告→工件对账 **[OK]**（1 份文档 × 3 臂 ×
  11 列，容差 0.0005；T-10 严格 29 行 / 25 可测、宽松 62 / 55；登记册覆盖率对账相符）；
  零断言 **472 测试文件 0 违规**；ast-guards **136 文件 / 79 站点 / 未覆盖 20 / 违规 0 /
  豁免命中 20 / EXEMPT 19**；状态落盘 **10 通道 / 3 面全覆盖**。
- **预跑失败不计通过**：`make gates` 之前的非 pytest 预跑在 `ruff format --check .` 以
  rc=1 终止——`scripts/tools/by_mutation_verify.py` 的变异锚点用单引号包裹含双引号的
  字符串，格式化器要求改写为双引号。`ruff format scripts/tools/by_mutation_verify.py`
  后重跑整条变异链 **45/45 变异转红 / 对照 0 红**（baseline 干净、collected 恒 27、
  无 COLLECTED DRIFT / ANCHOR-ERROR / SYNTAX-ERROR、`# mutation: ` 残留 0、rc=0），
  再跑全部门禁 rc=0。本册只登记修好后的确认读数。
<!-- BY-GATES:END -->

### 3.4 只读普查三段

`scripts/tools/by_analysis_flow_census.py`（默认跑 A/B/C；`--segment a|b|c` 单段）：

- **A 段**（AST 读者普查 + 接线）：`analysis_flow_stats` / `flow_console_line` /
  `render_analysis_flow_lines` 的调用点与定义一致；`src/` 命中 0。
- **B 段**（全归档读数）：§1 表逐项一致；三层对账成立
  （`10,659 − 886 − 2,463 − 300 = 7,010`、`7,010 = 561 + 6,449`、
  `9,473 − 7,010 = 2,463`）。
- **C 段**（五个具名冻结批次逐档核对）：**5/5 OK**，零 DRIFT；读数与测试里的
  `PINNED_BATCHES` 同源，C 段从测试文件 `ast.literal_eval` 读取期望值，不手抄。

## 4. 复现

```bash
# A/B/C. 三段只读普查（全 JSON 扫描，含混批口径）
.venv/bin/python scripts/tools/by_analysis_flow_census.py
# 实测：扫描 246 份 / 10,659 行
#   数据集外 77 份 / 886 行；schema 59 份 / 2,463 行；失败 0 / 0；未登记基线 300 行
#   载入 110 份 / 7,310 行_all / 7,010 行_tracked
#   重复 6,449（91.997%）；唯一 561；缺 task_id 0
#   字段 None：passed 0 / detection_rate 45 / repair_rate 52
#   归档宇宙 257 份 / 11,197 行；非 benchmark 13 份 / 538 行
#   混批 169 份 / 9,473 行；重复 8,494；唯一 979

# B. 报告章节（`## 数据来源` 内的流量表 + 对账句 + 脚注）
.venv/bin/python experiments/statistical_analysis.py \
  --results-dir experiments/results --output /tmp/statistical_report.md

# C. 变异验证（46 锚点 = 45 变异 + 1 对照）
.venv/bin/python scripts/tools/by_mutation_verify.py
```

## 5. 未做 / 边界

- **不回填历史行**：所有剔除层只记账，归档行一个字节不改；历史报告重跑后
  数值逐位相同。
- **不动判定值与方向**：`_load_batch_file` / `_pair_by_task` / 任何指标一处不动；
  本轮 `src/` 零改动（`git status --porcelain src/` 命中 0）。
- **n 不是载入行数**：唯一 task 行 561 才是配对单元；报告同时给出 7,010 / 6,449 /
  561 三个数，禁止把 7,010 当 n 引用。
- **两个扫描面不混用**：`benchmark_*.json` 扫描面 246 份，全归档带 `results` 的
  JSON 257 份；13 份非 benchmark 命名的文件不在加载器扫描面内，报告点名而不并入。
- **混批口径单列**：`--allow-schema-mixed` 的 169 份 / 9,473 行只作对照，
  与默认口径的 110 份 / 7,010 行不相减、不相加。
- **字段 None 不折成 0**：45 / 52 个不可测任务不进配对分母，也不参与均值。
- **英文索引/README 同步**：本轮八处日期行、README 双语、CHANGELOG 双语、INDEX 双语、
  测量廉洁 §69、状态登记册与 AO3 锁全部前滚；英文索引补 BY 行，不代补更早的历史漂移。

## 6. 本轮自纠

| # | 自纠项 | 说明 |
|---|---|---|
| ① | **`{"results": []}` 的归层期望写错** | 初版期望 `schema_incomplete`，实际加载器在 schema 检查之前就会因 `results` 形状不合法返回 False ⇒ `load_error`；修法：期望改为 `load_error`，并在 `classify_document` 的判定顺序上锁。 |
| ② | **`ast.literal_eval` 读不了 `UNTRACKED`** | C 段从测试文件读 `PINNED_BATCHES` 时，夹具里引用模块常量 `UNTRACKED`，`ast.literal_eval` 直接抛错；修法：夹具写字符串字面量 `"plain_llm_df_spec"`，C 段只读字面量，不 import 被测模块。 |
| ③ | **A 段把局部变量当成模块级读者** | 初版 AST 普查把 `results = doc.get("results")` 里的局部名计成对 `results` 的读者；修法：只认 `_analysis_flow` 符号的调用/属性访问，局部赋值不计。 |
| ④ | **B 段把 4 键归档视图与 2 键期望相比** | 归档盘点返回 4 键（files / rows / non_benchmark_files / non_benchmark_rows），初版期望只写 2 键 ⇒ 恒 DRIFT；修法：按实际返回的键集比较，多出的键单列断言。 |
| ⑤ | **C 段给非纳入批次留了期望键** | 初版 `PINNED_BATCHES` 里两个被剔除的批次也带 `included` 字段；修法：剔除批次只留层名与行数，纳入批次才要求 `included`。 |
| ⑥ | **F26 存活：逐基线字段没断言** | 变异把 `per_baseline[baseline]["fields"]` 换成空字典，测试仍全绿；修法：补每基线 `fields` 的逐键断言，并新增 F41 锚点（把 `passed` 桶的 None 计数写死 0）。 |
| ⑦ | **F33 锚点在 `ruff format` 后失配** | 多行 f-string 被格式化器折叠成单行，锚点按原字节找不到；修法：锚点改为格式化后的精确子串，**锚点必须是原字节的精确子串，格式化也是锚点的一部分**。 |
| ⑧ | **`archive_universe` 触发 ruff S112** | `except Exception: continue` 被判为静默吞异常；修法：加 `# noqa: S112 — 解析不了的 JSON 不是盘点对象`，并在报告脚注写明盘点只数可解析文件。 |
| ⑨ | **文档收口漏掉 README「最新优化」行与登记册头行的轮换**（提交前复核抓到） | BY 轮当时只把 README 双语**头部引用**推进到 `**BY round:` / `**BY 轮：`（AO3 锁只锁头部，自然转绿），但「最新优化 / Latest Optimization」行与登记册头行仍停在 BX——与 BV 轮收口态（头部与行同轮）不符，且无任何门禁覆盖该行。修法：提交前按 BV 轮模板把两行轮换到 BY（BX 退居「此前」链），轮换后两行粗体配对为偶（中文 64 / 英文 60）。教训：**行锁覆盖的面不等于收口面**——AO3 锁绿只证明头部同步，表格行与登记册头行要按上一轮收口态逐面对账。 |
