# BQ 轮：报告读侧把四个 status 通道当作不存在——BN 落盘的结果行四键零读者（2026-10-22，零 LLM，$0）

> 语言：中文（本册）。系列位置：BH → BI → BJ → BK → BL → BM → BN → BO → BP → **BQ**（"读不懂 ⇒ 静默 / 写了没人读"缺陷族的第 10 面）。
> 本轮零 LLM 调用、$0 支出；全部读数为实测，未跑的事一律写"尚未执行"。

## 1. 缺陷：字节落盘了（BN），但报告面没有一个读者

BM 轮把 `contract_status` 接进实验侧最后一个"写了没人读"的消费点
（`run_benchmark._build_risk_summary_for_result` 的 kwarg 透传），登记册同时写明
`static_check_status` / `safety_check_status` / `oracle_check_status` / `check_status`
四处仍是「写了没人读」。BN 轮（同日）随后把 static/safety/oracle 三通道的
status+outcomes 写进**结果行两分支**与 **raw 白名单**——写侧闭合。

但**读侧仍为零**，而且比"没人读"更精确：`experiments/` + `scripts/` 共 184 个
`.py` 里，从 **details 行**读这四个键的消费者 = **0**
（探针 A 段实测，AST 按 `.get(key)` / 下标 / 比较分类，state 读与行读分开计数）：

| 通道 | 写点（dict-key） | state 读（持久化写路径） | **行读（报告面消费者）** |
|---|---|---|---|
| `contract_status` | 3（run_benchmark） | 3（`:936` / `:1893` / `:2434`） | **0** |
| `static_check_status` | 3（run_benchmark） | 2（`:937` / `:1900`） | **0** |
| `safety_check_status` | 3（run_benchmark） | 2（`:939` / `:1902`） | **0** |
| `oracle_check_status` | 3（run_benchmark） | 2（`:941` / `:1904`） | **0** |

BM 给 `contract_status` 接的 `:2434` 是 **state 读**（`final_state → 结果行` 的
生产侧透传），不是报告面行读者。对照组 `contract_missing_symbols` 反而有 1 个
真实行读者（`scripts/tools/refresh_patch_field.py:201` 的
`row.get("contract_missing_symbols") or []`——它把 null / 缺席折成空列表，
同族折叠，本轮只按名登记、不修，见 §7-3）。

后果：归档与新批次里「这条腿跑过且干净（ok）」与「崩了（error）/ 按设计没跑
（disabled）/ 材料缺失（unavailable）/ 没记录（null / absent）」在**所有报告面
同形**——`build_analysis` 的 30 个指标助手无一读这四个键，
`run_main_batch._print_r4_summary` 的摘要块不列它们，
`statistical_analysis.py` 不读它们。BG→BN 七轮把"读不懂 ⇒ 判优"收成四值
status 并在发布侧/判定侧接上双读，披露链在**实验侧断在最后一步**。

## 2. 处置：只补读侧披露，判定值与方向一处不动

| # | 站点 | 改法 | 判定影响 |
|---|---|---|---|
| ① | 新模块 `experiments/analysis_parts/check_leg_analysis.py` | `_check_leg_measurability(details)`：四通道 × 七档计数（ok / disabled / unavailable / error / null / absent / other）+ `recorded_rows` + `rows_any_unmeasurable` + `available` + `reason` | 纯函数，零判定 |
| ② | `experiments/analyze_results.py` | `build_analysis` 的 `per_baseline` 加平行键 `check_leg_measurability`；`render_markdown` 加新章节「检查腿可测量性（BQ：结果行四通道的读侧）」：长表（基线 × 通道 × 七档摘要）、词表外取值点名、口径注；`available=False` 的臂按名列入「本节未列出 N 个基线」并写明「**不是「四腿都干净」，也不是「没有任务」**」；全臂不可记录时节照常渲染（BP 的 P14 教训） | 既有键集只多一个新键（棘轮锁）；既有章节一行不改 |
| ③ | `experiments/run_main_batch.py::_print_r4_summary` | 同一助手的一行摘要（与 R4/N1 同块同风格）：`BQ 检查腿（记录 k/n 行，任一腿没测成 m 行）: 命名契约腿 ok=.. 没测成=.. 没跑=.. 未记录=..；…`；`recorded=0` 时明写「未记录（早于 BN 轮落盘，不可读作「干净」）」而非零表 | 只加一行，R4/N1 文案不动 |

三条恒等式（锁里逐条钉）：每通道
`ok+disabled+unavailable+error+null+absent+other == n_rows`；
`recorded_rows == n_rows − 四键全缺席的行数`；
`0 ≤ rows_any_unmeasurable ≤ recorded_rows`。

分档口径（BP 式"缺席 ≠ 零"判据，四值词汇外加三档非词汇形状）：
`absent` = 行里没有这个键（批次早于 BN 落盘）；`null` = 键在场值为 None
（失败分支占位或腿未跑）；`other` = 词表外真值，自成一档并带
`other_values` 明细（防 `"OK"` / `1` 被静默算进 ok）。
**`status ≠ ok` 不表示"发现问题"，也不表示"没问题"**——四个键不进入任何
判定，本节只让"没测 / 没记录"在报告面可见。

## 3. 测量（全部实测；Python 3.14.6，零 LLM；探针 `scripts/tools/bq_check_leg_probe.py`）

### 3.1 A 段：读者普查（改前读数，只读）

扫描 `experiments/` + `scripts/`（排除 `results/` 与 `__pycache__`）共
**184** 个 `.py`。按 §1 表：三通道（含 contract）**行读 = 0**，写点各 3 处
（raw 白名单 `:936-945`、结果行成功分支 `:1893-1905`、失败分支 `:2214-2221`），
state 读 2–3 处（持久化路径）。`contract_missing_symbols` 行读 = 1
（`refresh_patch_field.py:201`）。接线普查（改前全 False）：助手模块不存在、
`analyze_results` 未 import、`build_analysis` 未调用、`render_markdown` 无章节、
`run_main_batch` 无摘要行。

### 3.2 B 段：归档取值分布（改前读数，只读）

`experiments/results/**/*.json` 递归扫描：文件 **1702**、可解析 **1594**、
解析失败 **108**（`JSONDecodeError`）。四键出现 = **0**
（BN 之后没有批次跑过）；`contract_missing_symbols` 出现 **8865**
（BL 之前的历史行：8853 None + 12 非平凡）。⇒ 本轮读者对历史工件只输出
「未记录」，真实读数待下一个批次。

### 3.3 C 段：合成七档栅格（改后复跑）

八行语料（五个词汇档各一行四键同值 + 全 absent 一行 + 词表外一行 + 混合行
`contract=ok / static=error / safety=disabled / oracle 缺席`）：

```
n_rows=8 recorded_rows=7 rows_any_unmeasurable=3 available=True
[contract_status] ok=3 disabled=1 unavailable=1 error=1 null=1 absent=1 other=0  合计=8
[static_check_status] ok=1 disabled=1 unavailable=1 error=2 null=1 absent=1 other=1  other_values=['OK']  合计=8
[safety_check_status] ok=2 disabled=2 unavailable=1 error=1 null=1 absent=1 other=0  合计=8
[oracle_check_status] ok=2 disabled=1 unavailable=1 error=1 null=1 absent=2 other=0  合计=8
```

三条恒等式全部成立（探针内断言 + 测试锁双重执行）。

### 3.4 全量回归、覆盖率与写入面

- **首跑（存量红修复前，顺序事故留档）**：collected **11992** → 11971 passed /
  19 skipped / **2 failed**、206.49s / rc=2、墙钟 **208s**（`date +%s` 成对采集
  1792662491→1792662699）。2 红 = 基线数对账守卫 + **`test_json_strict_af.py::
  TestStrictJsonGate::test_real_repo_passes`**（后者是存量缺陷，见 §6-1）。
- **预登记跑（`make test-cov` 等价命令，含 `--cov`，xdist `-n 4 --dist loadfile`）**：
  collected **11992** → 11972 passed / 19 skipped / 1 failed、29 warnings、
  **216.20s** / rc=2，墙钟 **218s**（1792663842→1792664060）；唯一红 = 基线
  数对账守卫（实收 11992 − 声明 11922 = **70 > 6** 容度，刷新后消失）。
- **同执行集抖动核查复跑**：11972 passed / 19 skipped / 1 failed、208.06s / rc=2、
  墙钟 **209s**（1792663341→1792663550）；`coverage.xml` 根读数与预登记跑
  **逐位相同**（行 19393/19904、弧 7103/7532）。
- **归因实验（`--ignore` BQ 锁文件，同会话同 skip 集）**：11907 passed /
  19 skipped / 1 failed、209.78s / rc=2、墙钟 **212s**（1792663589→1792663801）；
  行 **19394/19904**、弧 **7104/7532**。
- **刷新后确认跑（`make test` 等价命令、不带 `--cov`）**：collected **11992** →
  **11973 passed / 19 skipped / 0 failed、198.25s / rc=0**（47 warnings；墙钟
  **199s** 由 `date +%s` 成对采集 1792664556→1792664755）。**本会话沙箱口径**：
  19 skipped = 正常口径 5 + 14 项环境能力缺失 skip（ps/broker/嵌套沙箱）；
  正常环境读数 11987 passed / 5 skipped 由该差导出、非本会话实测。
- **覆盖率**（预登记跑工件 `coverage.xml`，root 口径）：行
  **19393/19904 = 97.4327%**、未覆盖 **511**——与 BP **逐位相同**（13 项逐模块
  读数逐项相同：base_agent 98.53 / api_manager 99.24 / dataset_loader 97.28 /
  graph_nodes 99.88 / code_analyzer 99.38 / planner 99.09 / dependency 96.26 /
  multi_candidate 99.36 / cross_file 94.82 / rag/retriever 98.10 /
  graph_workflow 99.72 / error_classifier 100.00 / graph_state 100.00）；
  弧 **7103/7532 = 94.3043%**、缺弧 **429**（BP 为 7105 / 427，**−2 已三路归因**，
  见 §6-6）。棘轮水位（行 ≥96.4 / 弧 ≥92.5）与登记册 ±0.20pp 容差均通过
  （94.3043% vs 声明 94.33% 差 0.03pp）。
- **写入面普查**（阈值 `st_mtime >` BP 链终跑之后的明确时刻，扫
  `git ls-files` + `--others --exclude-standard` 的 `.py`/`.md`/`.yaml`/`.yml`）：
  命中 **10** 个文件 = `experiments/analyze_results.py` +
  `experiments/run_main_batch.py` + `experiments/analysis_parts/check_leg_analysis.py` +
  `scripts/tools/bq_check_leg_probe.py` + `scripts/tools/bq_mutation_verify.py` +
  `tests/test_bq_check_leg_readers.py` + `scripts/tools/bo_raw_readside_fold_probe.py` +
  `docs/reviews/CHECK_LEG_READERS_BQ_2026-10-22.md` + 登记面 `BASELINE.yaml` 与
  `docs/PROJECT_STATUS_REGISTER.md`；**`src/` 与 `config.py` 命中 0** ⇒ 行覆盖与
  BP 逐位相同的主张以本条普查为据（相同读数本身不证明 `src/` 零改动）。
- 格式化面：本轮 7 个改动文件 `ruff format --check` 全过、`ruff check` 全过
  （全仓读数以门禁链终跑为准）。

## 4. 回归锁（`tests/test_bq_check_leg_readers.py`，65 例；逐类计数取自 `--collect-only` 实测）

| 组 | 例 | 钉住什么 |
|---|---|---|
| `TestIdentitiesHold` | 25 | 8 份语料 × 三条恒等式（每通道分档合计 == n_rows；recorded_rows == n_rows − 全缺席行；unmeasurable ≤ recorded）+ available 与 recorded_rows 同义 |
| `TestGradesCountEveryShape` | 14 | 词汇四值各落本档（参数化 4）；null 不是 absent 也不是 ok；absent 不是 null；词表外六种形状（`"OK"` / `1` / `[]` / `{}` / `True` / `"ok "`）各进 other 档并带明细；明细按通道去重；混合行逐通道独立计数 |
| `TestSectionDiscloses` | 9 | 表格七档数值；词表外取值点名行（干净批次不打印）；沉默臂按名列出 + 「不是四腿都干净」；零行臂不进「未列出」（no_rows 与 no_channel_recorded 两件事）；全臂未记录时节照常渲染且无表格（P14 同型教训）；无任何行时节不渲染；混合臂 absent 列；口径注「四个键不进入任何判定」 |
| `TestDisclosureAnchorsInSource` | 5 | 助手七档语句在场；`build_analysis` 接线与章节标题锚；`run_main_batch` 接线与「未记录」文案锚；四通道键名与 run_benchmark 结果行逐字对应（防键名漂移）；标签字典与通道集合一致 |
| `TestRowsAnyUnmeasurable` | 4 | 多腿坏只计一次；disabled 不算没测成；null/absent 不算；ok 不算 |
| `TestReasonTwoGrades` | 3 | no_rows / no_channel_recorded / 已记录无 reason |
| `TestJudgmentValuesDidNotMove` | 3 | `per_baseline` 键集棘轮（既有 30 键 + 新键一个不多一个不少）；既有数值（success_rate / token / M1 分母口径 / 5.3 的 n_details）逐位不变；既有章节标题与 BP 披露文案仍在 |
| `TestBatchSummaryLineDiscloses` | 2 | 记录批次的四腿分档摘要行 + R4/N1 同块文案不动；未记录批次明写「未记录」且不出现零表 |

既有断言**无需改写**：BQ + BP + BM + analysis + batch_ix 五套件合跑
**219 passed / 0 failed**（含 BP 的 62 例、BM 的 21 例与 §4 表格里的全部旧值）。

## 5. 变异验证（`scripts/tools/bq_mutation_verify.py`：16 锚点 + 1 中性对照）

每个变异都写成「把 BQ 补的读侧披露退回沉默 / 退回同形 / 退回最有利读数」的方向；
逐锚点：读原字节 → 写变异 → `compile()` → 采集面核对 → 跑受影响面 →
`finally` 按 sha256 还原（不使用 `git checkout` / `git stash`）。
基线 rc=0 / red=0 / **collected=219**（65 新锁 + 154 既有），逐锚点采集面恒 219，
无 COLLECTED-DRIFT。两次实跑红数逐位相同（墙钟 146s / 144s，
`date +%s` 成对采集 1792664397→1792664541 为第二次）。

| 锚点 → 红 | 锚点 → 红 | 锚点 → 红 |
|---|---|---|
| 键缺席并入 null → 4；null 不记档 → 3；词表外值不计数 → 9；词表外明细不记录 → 8 | recorded_rows 含未记录行 → 10；没测成集扩到词汇 → 4；reason 塌成一档 → 3；available 翻错 → 6 | 沉默臂整节消失 → 1；零行臂说成没记录 → 3；「不是干净」句删 → 1；词表外不点名 → 1 |
| 表格没测成列抹零 → 1；null/absent 合并 → 1 | 摘要行未记录也打零表 → 1；摘要行没测成抹零 → 1 | **对照**（只删 docstring 一对强调星号）→ **0 红（要求 SURVIVED）** |

**击杀 16 / 16，中性对照 0 红，采集面逐锚点恒 collected=219，`# mutation:` 残留 0。**
三次实跑（锚点更新前后各一轮 + format 后一轮）红数逐位相同、聚合结论一致
（`rc=0`；墙钟 146s / 144s / 147s，`date +%s` 成对采集，第三次为
1792665212→1792665359）。

## 6. 踩坑与自纠（本轮实测发生的）

**① 存量红：BP 收口的「门禁全绿」声明与实际工件分裂。** 首跑意外抓到
`test_json_strict_af.py::test_real_repo_passes` 红。根因不是本轮：BD→BP 批次
（b44a1aad）入库的 `scripts/tools/bo_raw_readside_fold_probe.py` 带两个宽松
`json.dumps` 写点（`:198` / `:308`），而 AF 轮的严格 JSON 门禁按
`git ls-files` 只扫**已跟踪**文件——**入库前的门禁跑看不到未跟踪的新文件**。
干净 worktree（`git worktree add /tmp/bq_head_check HEAD`）实测 HEAD 即红，
证明与 BQ 改动无关。处置：两处补 `allow_nan=False`（载荷是合成字典，零行为
变化；BO 探针复跑通过），门禁转绿。**教训**：门禁跑在脏树上 ≠ 门禁跑在入库后
的树上；本轮的提交纪律因此改为「先提交代码批次、再在干净树上跑链」。
门禁盲区本身（`--others` 不在扫描面）本轮不修，登记为下一轮候选（§7-6）。

**② zsh 的 glob 第三次咬人。** `rm -f .coverage.ci .coverage.ci.*` 在无匹配时
整行中止（`no matches found`），第一次预登记跑因此没执行（墙钟 0s）。改用
显式列文件或先探测再删。

**③ `ruff format` 会重排变异锚点的字面。** 本轮先写锚点后跑 format，三处锚点
（Q5/Q6/Q10）因换行重排失配（BF 轮同型：M5 旧字符串失配）。precheck 的
「锚点唯一性」当场抓住（count=0），按格式化后文本更新锚点并复跑全绿。
**顺序教训：锚点必须在 format 之后写，或 format 后必须复跑 precheck。**

**④ 探针分类器双重计数。** A 段首版把「写点 / state 读 / 行读」分类器的子节点
循环写在 `if/elif` 链外，对 `.get(key)` 的 Call 节点重复进入同一分支，同一行
被记两次 state 读。改为单次分发（Constant → Dict → Compare → Call → 递归）后
读数与 AST 实际出现次数逐位一致。

**⑤ 两个章节同句式，测试抓错行。** BP 的 5.3 章节与 BQ 的新章节都渲染
「> 本节未列出 N 个基线：…」。首版锁抓到了 BP 章节的行（`no_level_recorded`），
按「四通道全部未记录」内容 disambiguate 后命中 BQ 章节。

**⑥ 弧覆盖 −2 不能一句"src/ 零改动"带过。** 见 §3.4 三跑分解：BP 会话 7105 →
本会话排除 BQ 锁文件 7104（−1：沙箱 skip 19 vs BP 的 5，能力探测用例未执行）
→ 本会话含 BQ 锁文件 7103（−1：`--dist loadfile` 分组变化对顺序相关分支的
影响）。同执行集两次复跑逐位相同（7103/7103）。两项均非 `src/` 改动
（写入面普查为据），但"同值不证明没动、差值必须归因"的纪律照办。

## 7. 边界与未收口部分（按名登记，不写成"已排除"）

1. **四键在归档 0 出现**（BN 之后没有批次跑过）：本轮读者对历史工件只输出
   「未记录」，真实分档读数待下一个批次落盘后重跑 B 段普查。恒等式锁对任何
   归档成立，不依赖"0 出现"。
2. **raw 侧三键仍无读者**：`detection_first_status` / `edit_intent_status` /
   `deterministic_repair_status` 在 raw 白名单而不在结果行，本轮报告面读者
   读不到它们；其中 debugger 腿级的 `check_status` 嵌套在 `edit_intent_status`
   里，既无 state 声明也不进结果行（BK/BL 登记项延续）。
3. **`refresh_patch_field.py:201` 的 `or []` 折叠未修**：
   `contract_missing_symbols` 的 null / 缺席被折成空列表（与"比过了、零缺失"
   同形）。它是脚本工具链的既有口径，改动面涉及其下游 funnel 计数，单独轮次。
4. **判定不变的具体含义**：四个键不进入任何判定（通过 / 拒绝 / 分母都不读
   它们）；`rows_any_unmeasurable` 与章节全部数值都是披露，不是门禁。
5. **本轮未新增门禁**：读侧披露由 65 例锁 + 16 锚点覆盖。
6. **门禁对未跟踪文件盲扫（根因未修）**：`check_json_strict.py` 等按
   `git ls-files` 扫描的源码写入点门禁看不到未提交文件。本轮只修了违规点；
   把 `git ls-files --others --exclude-standard` 纳入扫描面（含夹具豁免与
   对应锁）是下一轮候选。
7. **报告章节对新批次的真实行为未经生产验证**：合成栅格 + 单测证明分档与
   恒等式；真批次（含失败分支 None 占位行）落盘后需重跑 B 段与 §3.3。
8. **BP 收口声明与实际门禁状态的分裂只登记不追改**：BP 手册 §9 的"门禁链
   rc=0"两跑声明与 HEAD 实测（json-strict 红）不符，根因是 §6-1 的盲区；
   历史声明不改写，以本轮实测与修复为准。
9. 历史批次工件与 `SHA256SUMS` 覆盖的产物**不改写**；新章节只出现在改后新产出
   的分析报告里。

## 8. 复算命令（零 LLM、只读或可自还原、可逐条重跑）

```bash
# 1) 本轮 65 例新锁（先看 collected=65，再看 rc）
.venv/bin/python -m pytest tests/test_bq_check_leg_readers.py -q -p no:cacheprovider

# 2) 五个受影响套件合跑（应 0 红；变异验证的采集面基线）
.venv/bin/python -m pytest tests/test_bq_check_leg_readers.py \
  tests/test_bp_contamination_bucket_disclosure.py tests/test_bm_experiments_readside.py \
  tests/test_experiments_analysis.py tests/test_batch_ix.py -q

# 3) 三面只读探针（A 读者普查 / B 归档分布 / C 合成栅格）
.venv/bin/python scripts/tools/bq_check_leg_probe.py

# 4) 变异验证：16 锚点 + 1 对照（临时改写三个 experiments/ 文件与助手模块，
#    finally 按 sha256 还原；中止过必须扫残留并复跑第 1 条）
.venv/bin/python scripts/tools/bq_mutation_verify.py

# 5) 存量红复现（只读）：干净 worktree 上跑严格 JSON 门禁
git worktree add /tmp/bq_head_check HEAD
.venv/bin/python scripts/gates/check_json_strict.py --root /tmp/bq_head_check
git worktree remove /tmp/bq_head_check --force

# 6) 全量回归（先 test-cov 预登记，刷新 BASELINE.yaml 后再 test 确认跑）
#    与门禁链（最后、单独、不接管道；make 在沙箱内被拦截时逐项目标等价执行）
make test-cov && make test && make gates
```

## 9. 收口批注

- **门禁链第一跑**（代码批次提交前、脏树；`make gates` 等价命令，19 步逐项记录 rc
  与墙钟，链内全量与文档编辑不重叠）：**全 19 步 rc=0、总墙钟 233s**。链内全量
  （`pytest tests/ -n 4 --dist loadfile`、不带 `--cov`）**11973 passed /
  19 skipped / 0 failed in 199.20s**（48 warnings）；`ruff check .` All checks
  passed；`ruff format --check .` = **999 files already formatted**（BP 994，净增
  5 = 4 个新可格式化文件 + 1 份中文手册）；mypy **Success: no issues found in
  137 source files**；双语文档 0 警告 / 0 失败；文档链接 185 文件 / 897 链接 /
  0 错误；env-budget 253 个唯一环境变量与登记表一致；`check_baseline.py` 结构
  校验通过、`check_baseline_numbers.py` 零硬编码通过；state-contract 136 文件
  无未声明键读写；env-snapshot 已覆盖 84 缺失 0；tool-versions OK；
  json-contract-sites 口径 A 通过；**json-strict 由存量红转绿**（§6-1 修复后
  首次链内通过）；artifact-doc-consistency 1 份文档 × 3 臂 × 11 列通过；
  零断言扫描 **461** 个测试文件 0 违规（BP 458）；ast-guards 136 文件 78 站点
  未覆盖 20 违规 0 豁免命中 20；status-persistence 声明 10 通道、落盘面 3 处
  全覆盖。
- **门禁链第二跑**（代码批次提交后、干净树；`git status` 干净、全部新文件已跟踪；
  `make gates` 等价命令，19 步逐项记录 rc 与墙钟）：**全 19 步 rc=0、总墙钟
  233s**，与第一跑逐项同值（链内全量 **11973 passed / 19 skipped / 0 failed in
  199.02s**、34 warnings；`999 files already formatted`；mypy 137；双语文档
  0 警告；文档链接 897 链接 0 错误；env-budget 253；baseline 双检通过；
  state-contract 136；env-snapshot 84；json-contract-sites 口径 A；
  **json-strict 通过**——§6-1 的盲区在干净树上不再成立：修复随代码批次入库后，
  扫描面看得到它；artifact-doc-consistency 通过；零断言 461 文件 0 违规；
  ast-guards 136/78/20/0/20/19；status-persistence 10 通道 3 处全覆盖）。
  **第二跑存在的理由**：脏树上看不到未跟踪文件，干净树才是入库后的真实门禁
  状态——BP 轮漏掉的正是这一遍。
- 回填后**链外复验**（文档锁子集 + json-strict 单跑）：读数回填于此。
