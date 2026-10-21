# AE 轮（2026-10-20）：价目条目准入接共享谓词（run_b8 聚合器）+ 测试侧域收口 + 入库报告陈旧差值登记更新

最后更新：2026-10-20
范围：AB-17 §4/§5 登记的成本/价目残余准入候选 A–G 的前置普查与处置。零 LLM 调用、$0 配额。
前置阅读：`TABLE_ADMISSION_AB17_2026-10-20.md`（表级读侧准入）、`PRICE_ADMISSION_AB16_2026-10-20.md`
（条目级谓词 `entry_block_reason`）、`AD_ROUND_STAT_DISPLAY_2026-10-20.md`（本轮 F 项的成因来源）。
命名说明：本册的「AE 轮」指 2026-10-20 的迭代轮次（接 AD 轮）；与 2026-10-06 的旧「AE 批次」
（`tests/test_ae_batch.py` 所在批次）不是同一对象，勿混引。

## 0. 一句话结论

AB-16/AB-17 把"什么算一条合格价目"收进了 `src.budget.pricing.entry_block_reason`，但**分析层
还有一处没接过去**：`run_b8_injection.aggregate` 自持一套 `isinstance(..., (int, float))` 数字门，
`bool` / `nan` / `inf` / 负价全部收下计价、`currency=CNY` 被记成 USD、读不出的条目静默换成内置价
**且无任何披露**。本轮把该门接到共享谓词，拒绝一律"内置价兜底 + 机制码披露"；测试侧
`test_ae_batch.py` 的价目 schema 断言同样自持一套更宽的域（`currency` 缺席缺省 USD、`inf` 被
`value >= 0` 放行），一并收口；同时把 AB-15/AB-16 登记里"入库 e2 报告 86 / 88 行陈旧差值"的
**登记数字**按当前树重算并归因（现树 94 / 100 行，canonical 110 → 122；增量 100% 来自 AD-1 渲染，
受保护工件不重写）。真批次读数零改变由锁执行（重聚合产物 `price` / 成本逐位相等，
`README.md` / `ISOLATION.json` 逐字节相同）。

## 1. 前置普查（A–G 逐项判定，只读 + /tmp 探针）

| 候选 | 判定 | 真实工件命中 | 处置 |
|---|---|---|---|
| **A** `run_b8_injection.aggregate` 自持数字门 + 币种盲 | **真实缺陷**（bool/nan/inf/负价/CNY/字符串价/未登记模型七类构造全部坐实） | **0**（2 份聚合工件均真表 USD；1699 份 results JSON 的价目块 0 处异常） | **本轮处置**（§2） |
| **B** `emse_stats_extensions._cost_per_task` 未登记模型 → 0.0 部分和 + note | 真实缺陷，但**现行口径**已显式区分"未登记（诚实降级）"与"拒绝（不产生金额）"，且被旧锁锁定 | 0（三臂 by_model 仅 `deepseek-flash`，note 恒"未计价模型：无"） | 维持现行口径，见 §5.1 |
| **C** `statistical_analysis.cost_analysis` 的 `missing_models` 桶词汇 | **仅归因措辞**（不产生错误金额；`cost` 恒 None） | 0（真批次桶全空） | 维持，见 §5.2 |
| **D** `tests/test_ae_batch.py` 价目 schema 断言 | **真实缺陷（测试侧）**：`entry.get("currency","USD")` 缺省美元 + `isinstance + >=0` 放行 `inf` | 测试自身绿只因真表 3/3 合规 | **本轮处置**（§3） |
| **E** P-1 归档 README 非渲染器产物 | 设计性/受保护工件（251 vs 64 行，10 个手写章节） | — | 不重写（§5.3） |
| **F** 入库 e2 报告 86 / 88 行陈旧差值 | 已有登记，但**登记数字已被 AD-1 推翻** | 是（受 `SHA256SUMS` 保护） | **本轮更新登记**（§4） |
| **G** Y 轮登记的 `trace` A20 坏行守卫 9 行未覆盖 | **无实例**：`trace.py` 当前未覆盖 0 行（Y2 提交 `12dbff94` 已消化）；审计复跑剩 9 行是 Y 轮已登记"记录不补"项 | — | 维持，见 §5.4 |

**A 的实测量（前置普查，/tmp 副本上跑生产 `aggregate()`，真实 `s_round` 工件）**：

| 价目构造（`deepseek-flash`） | 改前 `price_meta` | 改前 on/off 成本 | 改前读数问题 |
|---|---|---|---|
| 真表（0.3 / 1.2 USD） | 真表原样 | 0.046531 / 0.060761（total 0.107292） | 与受保护 `REPORT.json` 逐字段相等（基线） |
| `true` / `true` | 1.0 / 1.0 | **0.083246 / 0.113638** | bool 被当 1 收下计价 |
| `nan` / `nan` | NaN | NaN | **`REPORT.json` 写裸 `NaN`**（非 RFC-8259） |
| `inf` / `inf` | Infinity | Infinity | **写裸 `Infinity`**（非 RFC-8259） |
| `-0.3` / `-1.2` | 负 | **-0.046531 / -0.060761** | 负成本 |
| 0.3 / 1.2 + `currency=CNY` | CNY | 0.046531 / 0.060761 | **CNY 被当 USD** 记进 `cost_usd_standard_price`，README 无单位提醒 |
| `"0.3"` / `"1.2"`（字符串） | 静默退回内置价 | 0.046531 | 与"根本没给价目表"同形，**无机制披露** |
| 批次 `provenance.model_name=qwen-long`（真表 CNY 0.5 / 2.0） | CNY | **0.077551 / 0.101268（total 0.178819）** | 人民币价目被记成 `cost_usd` |
| `provenance.model_name=gpt-unknown` | 静默内置价 | 0.046531 | 与"真表读数"同形，**无披露** |

**影响范围实测**：真实聚合产物仅 2 份（`s_round_b8_injection_20261018/`、`t_round_a19_default_gate_20261018/`），
`price` 均 USD 真表；全仓 1,699 份 results JSON 中含 `cost_usd_standard_price` 的 35 份，
价目块与币种非 USD 异常 **0 处**；`experiments/price_table.json` git 历史只有 1 个版本、条目从未变坏。
⇒ A 是**理论可达、零实盘实例**：修复价值在"未来误配不再静默"，不纠历史读数。

## 2. A：`run_b8_injection.aggregate` 条目级准入接共享谓词

### 2.1 处置

- 新增 `_price_entry_reason(table, model)`（`experiments/run_b8_injection.py`）：`model not in table`
  → `model_unregistered`（"没登记"与"登记了但读不出"是两种事实，AB-11 判据，不共用码）；
  否则 `entry_block_reason(table[model])`（形状 / 空条目 / 币种不可判定或非 USD / 数字域，
  含 `bool`、字符串、`nan`/`inf`、负价、缺键）。
- `aggregate()` 删除自持的 `isinstance` 数字门改为调用该助手：
  - **接受路径**：`price_meta` 键集与改前**逐字节相同**（`source` / `currency` / `as_of` / `model` /
    `input_per_mtok` / `output_per_mtok`）——真表读数必须与受保护 `REPORT.json` 的 `price` 逐字段相等；
  - **拒绝路径**：保留内置 deepseek-flash 标准价（0.3 / 1.2）兜底，`logger.warning` 点名 model 与机制码，
    只在真拒绝时写 `price_meta["model"]` / `price_meta["entry_reason"]`，**不写** input/output 数字键
    （拒绝的价与 nan/inf 不进入工件）；
  - 表级失败（缺表 / 坏表）行为一律不变（只有 `table_reason`，不写 `entry_reason`）。
- `_write_readme()` 仅在表级或条目级不可用时追加一行
  `> **价目不可用**（<code>）：成本列按内置 deepseek-flash 标准价上界估算…`；
  真表路径输出空串 ⇒ 真工件 README 逐字节不变。

### 2.2 行为矩阵（改后实测，与 §1 改前逐行对照）

| 条目输入 | `price.entry_reason` | 成本 | 工件/披露 |
|---|---|---|---|
| 合法 USD 0.5 / 2.0 | （无键） | 0.0015 / total 0.003 | 接受，`price_meta` 六键原样 |
| 0.0 / 0.0 | （无键） | 0.0 / total 0.0 | **0.0 是合法价**，不被 falsy 误拒 |
| 币种缺席 / `null` / 空白 | `currency_absent` | 内置价 0.0009 / total 0.0018 | + logger + README 披露 |
| `CNY` | `currency_not_usd:CNY` | 内置价 | 拒绝的价不参与金额 |
| `null` 价 / 缺价键 | `price_null` | 内置价 | 同上 |
| `true` | `price_not_a_number:bool` | 内置价 | bool 不再当 1 |
| `"0.5"` | `price_not_a_number:str` | 内置价 | 字符串价不再静默兜底 |
| `nan` / `inf` | `price_not_finite:nan` / `:inf` | 内置价 | `REPORT.json` 无裸 `NaN`/`Infinity`（RFC-8259 严格） |
| 负价 | `price_negative` | 内置价 | 不再产生负成本 |
| `{}` | `entry_empty` | 内置价 | — |
| 非对象条目（如 `[0.5, 2.0]`） | `entry_not_object:list` | 内置价 | 不再崩在 `.get` |
| 模型未登记（`gpt-unknown`） | `model_unregistered` | 内置价 | 与"读不出"分开点名 |

### 2.3 回归锁与真工件不变量

- 新文件 `tests/test_experiments_cost_admission_ae.py` **21 例**：13 变体矩阵（每例断言
  `entry_reason` / `source` / 不写数字键 / 成本按内置价复算 / logger 点名，nan/inf 两例另断言
  `REPORT.json` 无裸 `NaN`/`Infinity`）+ 2 反例（合法条目接受、0.0 接受）+ 1 真工件重聚合 +
  2 表级失败不回归 + 2 README 披露 + 1 词汇判据；全部 `tmp_path`，缺工件 `pytest.fail` 不 skip。
- **真工件回归**（整目录副本、真表重聚合）：`price` 逐字段相等、
  `cost_total_usd` 0.107292、两臂 0.046531 / 0.060761 逐位相等且可由 token 复算；
  `README.md`（9773 B）/ `ISOLATION.json`（2220 B）重生成后与受保护文件**逐字节相同**；
  受保护目录树 sha256 前后一致、`SHA256SUMS` 58/58 OK。

## 3. D：测试侧价目 schema 也要接生产谓词

`tests/test_ae_batch.py` 的 `TestPriceTable.test_repo_price_table_schema` 改前自持一套**比生产更宽**
的域：`entry.get("currency", "USD")` 给币种缺席的条目造了一个缺省美元（生产 `currency_status`
读 `absent`）；`isinstance(value, (int, float)) and value >= 0` 放行 `inf`（生产
`price_block_reason` 读 `price_not_finite:inf`）。实测：删掉真表 `deepseek-flash` 条目的
`currency` 键后，旧断言仍绿而生产主批 `priced` 由 3/4 降到 0/4——测试防护力与实际口径脱节。

处置：抽模块级 `_validate_price_table(models)` 用生产谓词校验（`currency` 必须显式登记为字符串、
数字域 `price_block_reason(inp, outp) ∈ {None, "price_null"}`），schema 用例与两条负控共用：
① 缺 `currency` 键 → 校验失败；② `inf` 价 → 校验失败（两条在旧断言下都会绿）。

## 4. F：入库 e2 报告陈旧差值——数字重算与归因

**口径**（沿用 AB-15 §4.4）：用当前代码把报告重新生成到 `/tmp`，与 `experiments/results/main_batch/`
归档报告做行级比对；把**生成时间行**与**复算命令行**（含 `--results-dir` 绝对/相对路径，随调用方式变化）
归一后，统计 diff 的删除 + 新增行数。

| 报告 | 归档行数 | 现码行数 | 删除+新增（现树） | 同上（把 `_fmt_stat_num` 回退为旧渲染） |
|---|---|---|---|---|
| `statistical_report_e2.md` | 193 | 227 | **94** | **86**（= AB-15 登记值） |
| `statistical_report_e2_iter.md` | 192 | 228 | **100** | **88**（= AB-15 登记值） |
| `statistical_report.md`（canonical） | 157 | 223 | **122** | **110** |

**归因对拍**：仅把 `_fmt_stat_num` 回退为 AD-1 之前的渲染、其它代码不动，三份报告的差值**逐位回到
86 / 88 / 110**（AB-15 登记值）；差异块数同步 9 → 6 / 9 → 6 / 7 → 4。⇒ AB-15/AB-16 登记的
"86 / 88 行"在**旧渲染口径**下仍然精确成立，AD-1 把 5 / 7 个 p/q 单元格从 "0.0000" 改科学计数法后，
差异行数变大为 94 / 100（canonical 110 → 122）——**差值本身未消除、也不可能靠改渲染消除**
（归档报告是生成于 S11 / BH-FDR 等节之前的旧版本）。处置：不重写受 `SHA256SUMS` 保护的归档报告，
只更新登记数字与成因（§5.5），并把"差值随渲染口径变化"登记为可复算事实。

## 5. 登记未修 / 口径边界

1. **B：`emse_stats_extensions._cost_per_task` 的未登记模型仍是"部分和 + note"**。
   前置实测：真批次三臂 by_model 仅 `deepseek-flash`、note 恒"未计价模型：无"，`$/task` 与归档
   `STATS_EXTENSIONS.json` 逐位相等（0 实例）。构造输入下"全部未登记"会得到 `$0.0000`、混合臂得部分和；
   但这是 AB-15/AB-16 **已裁决的现行口径**：拒绝（币种/域/形状/空条目）不产生金额，
   "价目表没登记这个模型"属覆盖缺口、按诚实降级披露（note 点名未计价模型）。
   本轮**不重开该口径**，只登记它与 AB-15 判据的边界；若要改成"未登记也不产生金额"需单独一轮并
   改写 `tests/test_experiments_cost_rejection_ab15.py:519`。
   **AH（2026-10-20）即为该单独一轮且已处置**：未登记 / 无归因 / 归因不闭合 / 零任务分母一律
   `usd_per_task=None` 并在 note 点名机制，`tests/test_experiments_cost_rejection_ab15.py:519`
   旧锁按新口径改写；真批次三臂读数 0 行改变
   （`docs/reviews/COST_COMPLETENESS_AH_2026-10-20.md`）。
2. **C：`cost_analysis` 的 `missing_models` 桶不区分"未登记 / 域不合格 / 形状坏"**。
   真批次 0 实例；构造矩阵下域坏（`inf`/负/`bool`/缺键）与"未登记"同桶、形状码反而落进名为
   `unpriced_currency_models` 的桶（名不副实），全未计价早退分支的归因统一教读者"补价目字段"。
   仅归因措辞、不产生错误金额，登记待后续轮次。
   **AG（2026-10-20）已处置**：三桶互斥 + 行级归因 + 按码族渲染建议，真批次 522 行读数 0 行改变
   （`docs/reviews/COST_ATTRIBUTION_AG_2026-10-20.md`）。
3. **E：P-1 归档 README 不是渲染器产物**（归档 251 行 vs 当前渲染器 64 行、10 个手写独有章节，含
   `$0.006195`）；受 `SHA256SUMS` 保护，本轮只锁"未重写"，不当作可再生成工件。
4. **G：`trace` A20 坏行守卫**——Y2 已消化，当前 `trace.py` 未覆盖 0 行；`scripts/tools/audit_fix_coverage.py`
   复跑剩 9 行是 Y 轮报告 §5 已登记"记录不补"行（行号随代码漂移）。
5. **F 的登记数字更新**（`docs/PROJECT_STATUS_REGISTER.md` §4 的 AB-16 行 ⑪ 与 AB-15 §5.8 处）：
   86 / 88 → **94 / 100**（canonical 110 → **122**），成因 = AD-1 渲染，见 §4。
6. **本轮新发现、只登记不修：仓内工件含裸 `NaN`/`Infinity` token**。前置普查顺带统计：`experiments/results/`
   下 **68 份 JSON** 在文本中含裸 `NaN` / `Nan` / `Infinity` token（历史遗留、非本轮造成），
   说明"非 RFC-8259 JSON 工件"全仓无门禁；本轮只保证 `run_b8` 聚合路径不再新增（拒绝路径不写入非有限数），
   全仓严格 JSON 校验门禁留给后续轮次（需先清点历史工件豁免面）。
7. **`_write_json` 仍用 `json.dumps` 默认 `allow_nan=True`**：本轮只保证价目/成本路径不产生非有限数；
   其它非有限来源（如 token_metrics 被外力改坏）仍可写出裸 `NaN`。登记。
8. **`run_b8` 的"内置价兜底"语义**：拒绝路径仍产出**成本数字**（按内置 deepseek-flash 标准价上界），
   不是 `None`。这是该脚本既有"成本（标准价上界）"口径（表级失败同款行为，AB-17 锁定），
   拒绝的事实由 `entry_reason` 与 README 披露行承担；不得把该数字引用为"该模型的实际价目"。

## 6. 独立验证（ae-verifier，只读，2026-10-20）

全部证据在 `/tmp/ae_verify/REPORT.md` 与 `logs/`、`out/`；工作树验证前后不变（`git status` 恒 4 项、
4 文件 `shasum -c` OK、`experiments/results/` 与 docs/BASELINE 零触碰）。

- **① 行为矩阵对拍**：独立自建最小批次直调生产 `b8.aggregate`，**21/21 符合预期**——
  15 个坏条目变体（币种 absent/null/blank、CNY、not_string、价 null/bool/str/nan/inf/负、
  `entry_empty`、`entry_not_object`、`model_unregistered`、空表未登记）机制码逐码正确、
  source 回退内置、无数字价键/无 `table_reason`、成本按内置 0.3/1.2 逐位复算
  （1.288888/臂、合计 2.577776）、logger 点名机制码、README 恰 1 行「价目不可用」；
  nan/inf 的 `REPORT.json` 严格 JSON 无裸 `NaN`/`Infinity`；负价无负成本。正例 4/4
  （合法 USD、0.0、`usd` 小写、真表）接受，真表 `price` 与受保护逐字段相等。
- **② 真工件回归**：`s_round` / `t_round` 两份聚合产物副本重聚合，`price`、两臂成本、
  `cost_total_usd` 与受保护逐字段相等并按真表价逐位复算（20/20）；`s_round`
  的 `README.md` / `ISOLATION.json` 逐字节相同；**HEAD 旧实现 vs 现实现 A/B** 两工件
  README 逐字节相同（16/16）；仓库工件整树 sha256 前后不变。
- **③ 变异验证 10/10 全红**（/tmp 全树副本、带 `.env`、`compile()` 前置、基线 501 全绿、
  变异前后 collected 恒 69、sha256 还原、收尾复跑全绿）：M1 旧 `isinstance` 13 红；M2 去
  `entry_reason` 15；M3 未登记并入 `entry_block_reason` 3；M4 放行 `bool` 1；M5 去 README
  披露 1；M6 收非 USD 2；M7 0.0 当 falsy 拒 3；M8 拒绝路径写数字键 14；M9 披露行位置 2；
  M10 表级混入 `entry_reason` 3。
- **④ 反向验证（测试有效性）**：换回 HEAD 实现 → 目标集 17 红；旧 schema 口径 →
  `test_ae_batch` 两条负控红 ⇒ 新测试非空转。
- **⑤ 回归面**：3 个改动测试文件 + AB-13/14/15/16/17 + AB-12e 共 **527 passed**；
  ruff check / format 4 文件全过；collected 增量独立核对 **+23** 与声称一致。
- **⑥ 低严重度建议（已采纳）**：为 AB-17 空表用例补回 `as_of` 与"无数字价键"断言、
  为新矩阵补 `price` 精确键集断言（不放宽语义，只补回被改口径挤掉的观测面）。

## 7. 基线

- collected **10328** = passed **10323** + skipped 5 + failed 0（正常环境登记口径；
  净增 **23 例** = 新文件 21 + `test_ae_batch.py` 负控 2）；
- 本轮改动面为 2 个 `experiments/` 脚本（`run_b8_injection.py`；`tests/` 3 文件）+ 文档，
  **`src/` + `config.py` 零改动**；`experiments/` 不在 `--cov=src` 口径内，覆盖率读数
  **预期不变**（实测与抖动见收口跑）；
- 收口确认跑：`make gates` 全链 **rc=0**（链内 pytest **10323 passed / 5 skipped / 0 failed、
  180.35s**；该链**不带 `--cov`**，与带覆盖率口径的 187.39s 不可互换引用）。首跑曾在零断言门禁
  抓到 `test_repo_price_table_schema` 把断言抽进助手函数后**测试体内无断言信号**（违规 1）——
  补测试体内显式断言后复跑全链转绿，如实登记为方法学自纠；
- 本轮 `src/` + `config.py` 零改动（佐证 = 改动面清单）；`coverage.xml` 实测
  **18439/18963 行 = 97.2367%**、**6653/7090 弧 = 93.8364%**，与 AD 两次读数各差 1 行 / 1 弧，
  落在 AB-11 已登记的 `process_utils.py` 竞态分支抖动域内（±2 行 / ±1 弧），
  按 `docs/MEASUREMENT_INTEGRITY.md` §14 只作观测、不作零改动的佐证；
- ruff / mypy / 全部门禁绿；受保护工件一份未重写（重聚合逐字节相同由锁执行）。

## 8. 不得据本册引用

- 不得引用"成本/价目准入已全仓统一"：B 处按现行口径保留（§5.1）；C 处已由
  **AG 轮（2026-10-20）处置**，见 §11（本条为日期化补记，不改写原判据），
  `_write_json` 的 `allow_nan` 与 68 份历史非严格 JSON 工件未处置（§5.6 / §5.7）。
- 不得引用"入库 e2 报告可逐位复现"：陈旧差值仍在（现树 94 / 100 / canonical 122 行），
  本轮只更新登记数字与成因。
- 不得引用"`run_b8` 拒绝时没有成本数字"：拒绝路径按内置标准价上界兜底并披露，不是 `None`（§5.8）。

## 9. 复算命令

```bash
# 目标回归锁（69 passed：新 21 + AB-17 26 + ae_batch 22）
.venv/bin/python -m pytest tests/test_experiments_cost_admission_ae.py \
  tests/test_experiments_table_admission_ab17.py tests/test_ae_batch.py -q --basetemp=/tmp/pt_ae

# 价目链回归面
.venv/bin/python -m pytest tests/test_emse_stats_report.py \
  tests/test_experiments_price_table_ab13.py tests/test_experiments_currency_caliber_ab14.py \
  tests/test_experiments_cost_rejection_ab15.py tests/test_experiments_price_admission_ab16.py \
  tests/test_experiments_table_admission_ab17.py -q --basetemp=/tmp/pt_ae_chain

# 全量（CI 同口径）
COVERAGE_FILE=.coverage.ci .venv/bin/python -m pytest tests/ -n 4 --dist loadfile \
  --cov=src --cov-branch --cov-report=term-missing --cov-report=xml
```

## 10. AF 轮日期化勘误（2026-10-20，只追加、不改写上文）

**勘误对象：§5.6 第 6 条「仓内 68 份 JSON 含裸 `NaN`/`Nan`/`Infinity` token」。**

该计数来自**文本 grep**，把字符串值内部的同名字样也计入了。AF 轮以
`json.loads(parse_constant=拒绝)` 对 `git ls-files` 的 7273 份 `.json`/`.jsonl` 逐份严格解析：
**违规 0 份**；`experiments/results/` 下确有 69 份文件（worktree；42 份 tracked）在字符串内
出现这些字样（如测试名 `test_sqrt_positive_infinity`、诊断文本 "x 为 NaN"），它们在 RFC 8259
下**合法**，严格解析器接受。因此 §5.6 的"68 份非严格工件"不成立，应读作
"68 份文件文本中出现该字样"；真正的缺口是 §5.7 的写入路径。

**§5.7 已由 AF 轮处置**：`run_b8._write_json` 与 `_Injection._record`、`atomic_write_json`、
`trace` 三处写盘全部改走 `src/utils/json_strict.strict_json_dumps`（fail-closed，带 JSON 路径），
另为 39 份源码的 41 个直写点补 `allow_nan=False`，并新增门禁
`scripts/gates/check_json_strict.py`（工件 7273 份 = 严格 7271 + 2 份 A20 历史截断行登记豁免
+ 违规 0；源码 300 份写入点违规 0）。详见 `docs/reviews/JSON_STRICT_AF_2026-10-20.md`。


## 11. AG 轮日期化补记（2026-10-20）：候选 C 已处置

**补记对象：§5 第 2 条（C）「`cost_analysis` 的 `missing_models` 桶不区分未登记 / 域不合格 / 形状坏」。**

AG 轮已按该条登记的方向处置，**不改写上文**：

- `missing_models` 现**只含真键缺席**（`model_unregistered`）；
- 价格域坏值（`price_null` / `price_not_a_number:*` / `price_negative` /
  `price_not_finite:*`）与形状码（`entry_not_object:*` / `entry_empty`）不再冒充未登记，
  也不再落进名为「币种」的桶；
- 新增 `unpriced_model_reasons` 完整机制图与 `unpriced_row_reason`
  （`mixed_currencies:*` / `mixed_price_pairs`）；三个条目桶互斥，行级是另一种事实；
- 全未计价早退分支按机制给建议，不再统一教读者补价目字段；
- **真批次 0 行改变**：522 行、模型集 `{"deepseek-flash"}`、成本单元格与未计价注逐字节相同。

判据 = 删掉 15 处行为锚点中任一处必红（red 1–25，collected 恒 365，中性对照 0 红）。
详见 `docs/reviews/COST_ATTRIBUTION_AG_2026-10-20.md`。**B（`emse_stats_extensions` 的
未登记部分和口径）仍按 §5 第 1 条保留**；本条只关闭 C。
