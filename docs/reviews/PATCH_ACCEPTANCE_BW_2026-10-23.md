# BW 轮：补丁接收链的覆盖率与分母从未披露（零 LLM，$0）

登记日 2026-10-23；实测自 2026-10-23（本机 macOS，Python 3.14.6，pytest 9.1.1）。

## 1. 发现

补丁从「写盘成功」到「gold 判正确」是一条**多门链**。每一门都在结果行里留下判定值，
但报告面只读其中一部分；BW 收口的四族读取端改前**全部为零（或只有测试读者）**：

| 键 | 写入点 | 归档行 | 沉默形态 |
|---|---|---|---|
| `patch_precision` | R53（预注册 E3 指标） | 8012 | 报告面 **0 读者**；`None` 与 `0.0` 在读者侧同形 |
| `patch_plausible_evidence` / `patch_plausible_invariant_violation` | P0-2 | 4044 | 报告面 **0 读者**；plausible 的唯一可复核依据、`correct=1 ∧ plausible=0` 的显式观测都不见报 |
| `patch_abstain_signals` | 批次 V（ADR-0020） | 5935 | 报告面 **0 读者**；弃权由哪条不可信信号触发、弃权精确率都不见报 |
| `patch_validated` / `patch_validate_verdict` | 批次 XVI | 4044 | 只有测试读者；filtered success 的覆盖率不见报 |

归档实测（`experiments/results/`：257 份批次文件 / 11197 条结果行；全部读数见 §4 复现命令）：

| 事实 | 数值 |
|---|---|
| 接收链已记录（`plausible` + `correct` + `patch_precision` 三键齐备） | **8012** / 11197（其余 3185 行早于 R53） |
| 接受集（`plausible=1`） | **1331**（覆盖率 **16.61%**） |
| 接受集判对 / 判错 | **607** / **724** |
| 全部判对（`correct=1`） | **746** = 607（接受集内）+ **139**（`plausible=0`） |
| 精确率（存储口径，交 / plausible） | **45.6048%**（607/1331） |
| 并集精确率（correct / (plausible ∪ correct)） | **50.7483%**（746/1470） |
| gold 精确率（剔除 283 行无 gold 材料） | **57.9198%**（607/1048） |
| 选择性风险（接受集判错 / plausible） | **54.3952%**（724/1331）；gold 分母 **42.0802%**（441/1048） |
| `correct=0` 分档（`correct_status`，全 8012 行） | gold 判错 **6476** / 无 gold 材料 **790** |
| 证据档（4044 行已记录） | applied **614** / applied_then_rejected **32** / rejected **368** / no_patch **3030** / 其它 **0** / 未记录 **7153** |
| 隐含 plausible（applied 或 applied_then_rejected） | **646**；plausible 但证据档不支撑 **685**；不一致 **0** |
| 不变量 | 复算违反 **139**（布尔键为真 10 / 键缺席 129）；键未落盘历史行 **3968** |
| 弃权已记录（`patch_abstained` + `patch_abstain_signals`） | **5935**；abstained **3605** / not **2330** |
| 弃权四桶 | passed_with_patch 690 / passed_no_patch 2349 / failed_with_patch 1179 / failed_no_patch 1717 |
| 无可抑制对象（failed_no_patch） | **608**；可抑制 **2997** |
| 抑制 passed | **1960**；抑制精确率 **93.9753%**（1825/1942，gold 分母）/ **93.1122%**（1825/1960，全部分母） |
| 信号分布（可多选） | test_regenerated 1449 / detection_first 1719 / specificity 1224 / patch_evidence 747 / source_unverified 717；≥2 信号 **2042**；未知信号 **0** |
| 验证已记录（`patch_validated` + `patch_validate_verdict`） | **4044**；validated **594** / unvalidated **3450** |
| 验证输入 | 仅 `patch_evidence_level` **1007**；`repo_verification` / `deterministic_repair_status` **全归档可达域为空** |
| 验证输入取值 | sbfl **594** / null **3037** / none **387** / keyword **26** |
| 无可用输入 | **3037**；且这 3037 行全部 unvalidated ⇒ `unvalidated` ≠「验证过且失败」 |
| passed | **2116**（抑制中 1198 / 未抑制 918）；filtered success **329**（覆盖率 15.55% / 未抑制 35.84%） |
| 三处判定核重跑不一致 | precision **0** / correct-rate **0** / 弃权 **0** / 信号 **0** / 验证 **0** / validated **0** |

四条事实值得单独点名：

1. **三个「精确率」是三个分母，不是一个估计。** 存储口径 45.60%、并集口径 50.75%、
   gold 口径 57.92%。`correct=1 ∧ plausible=0` 的 **139** 行让两个集合不是包含关系；
   把「接受集精确率」写成 `correct / plausible` 会在归档上得到 **56.05%**，与存储值
   相差 10.4pp——这正是「同一个名字，三种算法」的典型分叉。
2. **`patch_precision=0.0` 在 283 行上不是「测了且错」。** 这些行 `plausible=1` 但
   `repair_rate` 缺席或 `None`，写侧在无 gold 时的保守取值被存成 0.0；
   `patch_precision=None` 则当且仅当 `plausible=0`（无分母）。两者都**不得读作 0 分**。
3. **弃权的分母有两层。** 3605 行 `abstained=True` 里 **608** 行是「失败且无补丁」——
   没有可抑制对象，与真正的抑制同记 `True`；可抑制只有 2997 行。抑制精确率按
   gold 分母是 93.98%，按全部被抑制行是 93.11%（18 行无 gold 材料被记为「非错误」）；
   两个数都要报，且 1960 行里还有 117 行是被抑制但**判对**的。
4. **验证层的最强证据在整个归档里一次也没出现。** `repo_verification` /
   `deterministic_repair_status` 的行内可达域为 **0**；594 行 `validated=True` 全部来自
   最弱的 `patch_evidence_level` 一档，其中实际只有 `sbfl`（594）。3037 行没有任何
   验证输入却落 `unvalidated=True`——「没验」与「验了失败」在结果行里同值。

只写不读键池（§61① 读法口径）：BV 收口后 **6 键 / 34943 行** → BW 接入四键
（`patch_precision` 8012 + `patch_abstain_signals` 5935 + `patch_plausible_evidence`
4044 + `patch_plausible_invariant_violation` 4044 = **22035** 行）后剩
**2 键 / 12908 行**（`risk_summary` 8864 + `mdo_crash_rate` 4044）；
12908 + 22035 = 34943 ✓（A 段复核）。

## 2. 处置

**单一事实源**：新增 `experiments/_patch_acceptance.py`

- 键名常量（12 个）与词表：`EVIDENCE_BASES`（六档 + 未记录）、`EVIDENCE_PLAUSIBLE_BASES`
  （applied / applied_then_rejected）、`CORRECT_VOCAB`（correct / gold_incorrect / no_gold /
  correct_unrecorded）、`ABSTAIN_BUCKETS`（四桶）、`VALIDATION_INPUTS`（三输入）。
  信号词表与验证词表从判定核同源导入（`src.tools.patch_abstain` / `patch_validate`），
  测试逐项对照。
- 读侧原语：`flag`（bool/int/字符串显式折叠，`bool("false")` 不生效）、`plausible` /
  `correct` / `correct_status`、`precision_stored` / `precision_expected` /
  `precision_mismatch`、`evidence_basis` / `evidence_plausible` / `evidence_mismatch`、
  `invariant_recomputed` / `invariant_flag`、`patch_present` / `abstain_bucket` /
  `abstain_applicable` / `abstain_signals` / `abstain_signal_names`、
  `recompute_abstention`、`validation_inputs` / `validation_verdict` / `validated` /
  `recompute_validation` / `filtered_success`。
- 缺席语义：缺键返回 `None`（不是 0）；`correct=0` 三分（gold 判错 / 无 gold / 未记录）；
  未知证据档落 `other:<值>` 而不是并入已知档；`patch_abstain_signals` 非列表不猜。

**读端**：`statistical_analysis.patch_acceptance_stats(rows)` + `patch_acceptance_summary(data)`——
接收集四格交叉 + 三个精确率分母 + 覆盖率 + 选择性风险 + 不变量四档；证据六档 + 未记录 +
「隐含 plausible / plausible 无证据」；弃权四桶 + 共抑制/无对象拆分 + 两分母抑制精确率 +
信号计数 + 信号域（记录 / null / 缺席，**null 与缺席分列**）；验证输入计数 + 取值域 +
判定不一致 + filtered success 两个覆盖率。

**报告面**：`analyze_results.py` 新增章节「补丁接收链的覆盖率与分母（BW：`patch_precision` /
证据 / 弃权 / 验证的读侧）」——四张表（14 / 12 / 13 / 14 列）+ 每臂行 + `**合计**` 行 +
口径脚注：三分母、`correct=0` 两档、不变量缺席不得读作「未违反」、legacy（早于 R53）不得
读作 plausible=0、ADR-0021 工件注记（本轮**未重跑**回放）、证据同一性、弃权两分母、信号
计数与信号域、`unvalidated` ≠「验证过且失败」、两个最强输入可达域为空、外部口径
（selective prediction 的风险–覆盖曲线；覆盖率为 0 时风险**未定义**）。
`run_main_batch._print_r4_summary` 增两行摘要（接收链 + 弃权/验证），批次跑完即可见。
**不进入任何判定，不改 passed / repair / 分母，也不回填历史行。**

**棘轮**：BQ 的 per-baseline 键集棘轮新增 `patch_acceptance`（只增不删）。

**口径分列**：报告渲染走 `load_experiment_results`（默认 7010 行 / `allow_schema_mixed=True`
9473 行），§1 与普查走**全 JSON 原始扫描**（257 文件 / 11197 行）。两套口径都登记，不混用；
本册所有归档读数均为后者。

## 3. 验证

### 3.1 测试

| 项 | 读数 |
|---|---|
| BW 新锁 | `tests/test_patch_acceptance_bw.py` **94 例**（含 5 个具名冻结批次逐档对账）全绿 |
| collected | **12370** = 12365 passed + 5 skipped（12276 BV 基线 + 94 例） |
| 预登记全量跑 | **12363 passed / 5 skipped / 2 failed、600.17s / rc=1**；两红均为本轮引入的旧契约：`total_passed` 仍为 12271、per-baseline 键集棘轮未登记 `patch_acceptance`。修复后两套件 **6 passed** |
| 确认跑 | 见 §3.3（`make gates`，唯一权威确认读数） |
| 旧契约 | 1 处扩展（键集棘轮 +1）；`BASELINE.yaml` 的 `tests.total_passed` 刷新为 12365（由本轮新增 94 例决定，不是改测试） |
| 覆盖率 | 与 BV 逐位相同：行 **19538/20052 = 97.4367%**、弧 **7150/7584 = 94.2774%**（`git status --porcelain src/` 命中 0；`coverage.xml` root 口径） |

### 3.2 变异

`scripts/tools/bw_mutation_verify.py`：**68 个锚点（67 个变异 + 1 个中性对照 N01）**。
干净树先全绿且 collected 一致（恒 94）→ 逐锚点读原字节 → 写变异 → `compile()` →
收集数核对 → 跑受影响面 → **sha256 校验后按原字节还原**（不用 `git checkout` / `git stash`）。
结果：**67/67 变异转红，对照 0 红，rc=0，`# mutation: ` 残留 0**。

首轮 **4 项存活**，全部就地处置（不是登记了事）：

| 存活锚点 | 存活原因 | 处置 |
|---|---|---|
| S19（选择性风险分母换成 gold） | 报告面从计数重算这一列，`selective_risk["value"]` 没有直接读者，改值不改变任何输出 | 在接收集恒等式测试里直接断言 `value` 与 `gold_value` 两个分母 |
| P13（弃权精确率口径消失） | 变异串落在**字符串字面量内部**，`# mutation:` 注释随字符串一起渲染，关键词仍在 md 里 | 锚点改为整行（含引号与逗号），注释移到字面量外；首个修法误加逗号让 `append` 收到两个参数（15 红崩溃），再改为纯拼接后精确 1 红 |
| P15（信号域少一项） | 报告先建 `signal_domain` 初值，统计侧 `setdefault` 又把全部名字补回 ⇒ 删初值是无操作 | 锚点改到真正控制输出的脚注 join（`list(sig_domain.items())[:-1]`），测试收窄为「信号域段落」内逐名断言 |
| M03（摘要 filtered 分母换成已验证行） | 夹具里 `n_recorded == n_passed == 2`，换分母是恒等操作 | **不对称夹具**：加入一条已记录但 `passed=False` 的行 ⇒ `1/2` vs 变异 `1/3` |

### 3.3 门禁

- `make gates` 全链 **rc=0**（干净树、墙钟 **245s**〔`date +%s` 成对采集〕；链内 pytest xdist `-n 4 --dist loadfile` 且**不带 `--cov`**：**12365 passed / 5 skipped / 0 failed、238.80s**、55 warnings、collected **12370**；ruff **1025 文件已格式化**、mypy **137 源文件 0 错**；双语文档 0 警告 / 0 失败；文档链接 **191 份 / 841 条 / 0 错误**；env-budget **253/253**；BASELINE 结构与数字通过；状态通道 **136 文件**；env-snapshot **84/84**、缺失 0；JSON 契约 **7/7**；JSON strict **7274 工件 0 违规** + **343 源文件 0 写入点违规**；报告→工件对账 [OK]；零断言 **470 测试文件 0 违规**；ast-guards **136/79/20/0/20/19**；状态落盘 **10 通道 / 3 面全覆盖**）

### 3.4 只读普查三段

`scripts/tools/bw_patch_acceptance_census.py`（默认跑 A/B/C；`--segment a|b|c` 单段）：

- **A 段**（AST 读者普查 + 键池）：全树零读者 **2 键 / 12908 行**；四键读侧命中去向单列
  （`patch_precision` row_read 1 / 报告面 1；`patch_plausible_evidence` 2 / 2；
  `patch_plausible_invariant_violation` 3 / 3；`patch_abstain_signals` 1 / 1；
  `patch_validated` 5 / 4；`patch_validate_verdict` 4 / 2）；恒等式
  **12908 + 22035 = 34943** 成立。
- **B 段**（全归档 257 文件 / 11197 行）：§1 表逐项一致；分档恒等式
  607 + 724 + 139 + 6542 = 8012、证据六档 + 未记录 = 11197、弃权四桶和 = 5935、
  验证 594 + 3450 = 4044 全部成立；判定核重跑（precision / correct-rate / 弃权 /
  信号 / 验证 / validated）不一致均为 **0**。
- **C 段**（五个具名冻结批次逐档核对）：**5/5 OK**，零 DRIFT；读数与测试里的
  `PINNED_BATCHES` 同源，C 段从测试文件 `ast.literal_eval` 读取期望值，不手抄。

## 4. 复现

```bash
# A/B/C. 三段只读普查（全 JSON 扫描，含 schema 混批）
.venv/bin/python scripts/tools/bw_patch_acceptance_census.py
# 实测：批次 257 / 行 11197
#   接收链 已记录 8012 | plausible 1331 | correct 746 | 交 607 | 接受集判错 724 | 排除集判对 139 | 无 gold 283
#   精确率 0.456048 / 并集 0.507483 / gold 0.579198；覆盖率 0.166126
#   不变量 {flag_unrecorded: 3968, violation: 139, flag_missing: 129, flag_true: 10}
#   证据 已记录 4044 / 未记录 7153 | applied 614 / no_patch 3030 / rejected 368 / applied_then_rejected 32
#   弃权 已记录 5935 | abstained 3605 | 无可抑制对象 608 | 可抑制 2997
#        抑制 passed 1960 | 抑制精确率 0.939753（1825/1942）| 全部分母 0.931122
#   验证 已记录 4044 | validated 594 | unvalidated 3450 | 无输入 3037
#        passed 2116（抑制 1198 / 未抑制 918）| filtered success 329
#   键池 2 键 / 12908 行；12908 + 22035 = 34943

# B. 报告章节（四张表 + 脚注）
.venv/bin/python experiments/analyze_results.py --input <batch.json>

# C. 变异验证（68 锚点 = 67 变异 + 1 对照）
.venv/bin/python scripts/tools/bw_mutation_verify.py
```

## 5. 未做 / 边界

- **不回填历史行**：3185 行接收链未记录、7153 行证据键缺席、3968 行不变量键缺席、
  3037 行无验证输入——报告面显示为「未记录 / 无输入」，不折成任何一档。
- **不动判定值与方向**：`patch_precision` / `patch_plausible*` / `patch_abstained*` /
  `patch_validated*` 的写侧与任何行的值一处不动；本轮 `src/` 零改动。
- **不进入任何判定**：分档、精确率、覆盖率、选择性风险都不改 passed / repair / 分母。
- **证据不是回放**：ADR-0021 的工件注记保留——本轮**未重跑** replay，`patch_plausible_evidence`
  是**归档登记值**，不是「重放后确认」的证据链。
- **`n_plausible_without_evidence` = 685 不是「错」**：它只表示 `plausible=1` 而证据档不在
  applied / applied_then_rejected 两档；后者是 `plausible` 的唯一可复核依据，缺失即
  「无法从行内材料复核」，不是「判错」。
- **两个最强验证输入的可达域为空**是归档事实，不是「没有这两条通道」：新批次一旦写入
  `repo_verification` / `deterministic_repair_status`，读侧会自动分档；本轮零 LLM、$0，
  未跑真实批次。
- **键池其余 2 项未动**：`risk_summary`（8864 行）、`mdo_crash_rate`（4044 行）仍是
  只写不读，留待后续轮次。
- **`patch_precision` 的存储口径不修正**：`plausible=1 ∧ repair_rate=None` 的 283 行存
  0.0，这是写侧既有语义；读侧只把它单列为「无 gold 材料」，不改存储值。
- **英文索引/README 同步**：本轮七处日期行、README 双语、CHANGELOG 双语、INDEX 双语与
  AO3 锁全部前滚；英文索引补 BW 行，不代补更早的历史漂移。

## 6. 本轮自纠

| # | 自纠项 | 说明 |
|---|---|---|
| ① | **报告脚注把「gold 判错」算成了 plausible 子集** | `correct=0` 分档最初用 `n_gold_incorrect`（plausible 子集，归档 441），而非 `correct_status`（全 8012 行，归档 6476）；归档上会把 **6476 行金标判错**误标成「无 gold 材料」。修法：改用 `correct_status` 的两个计数，并补**不对称夹具**（`plausible=0 ∧ correct=0 ∧ repair_rate=0`）锁住 2:1 与 6:1 的差异。 |
| ② | **变异串落进字符串字面量 ⇒ 假存活** | P13 的替换把 `# mutation:` 注释写进了 md 会渲染的字符串，关键词仍出现，测试自然绿。修法：锚点扩到整行，注释放到引号外；**变异体本身必须是语义上被改掉的代码**，注释位置也是锚点的一部分。 |
| ③ | **修变异时引入语法上合法、语义上崩坏的替换** | P13 第二版在 f-string 拼接中多写一个逗号，`append` 收到两个参数，15 个报告测试全红——那是崩溃，不是「精确杀」。修法：恢复纯字符串拼接，复跑得到精确 1 红。**红数不是越多越好，杀点必须可归因。** |
| ④ | **报告侧初值被统计侧 `setdefault` 自愈** | P15 删掉 `signal_domain` 初值后，统计结果又把全部信号名补回，变异无操作。修法：把锚点移到真正决定输出的 `join`，并把测试断言收窄到「信号域」段落。 |
| ⑤ | **对称夹具让分母变异成为恒等操作** | M03 的两条 passed 行使 `n_recorded == n_passed`，换分母无差别。修法：新增「已记录但未 passed」行，让两个分母在输出上分开。 |
| ⑥ | **预登记全量跑的两红都是本轮自己造成的** | `total_passed` 仍是 12271（新增 94 例未计数）、per-baseline 键集棘轮未登记 `patch_acceptance`。两处都在本轮收口：前者刷新 BASELINE，后者在棘轮里显式 +1；**不得把这两红登记成「环境问题」**。 |
| ⑦ | **墙钟口径不可跨轮比较** | 本轮全量 600.17s 是**单进程**口径；BV 的 218.94s 是 `-n 4 --dist loadfile` 沙箱口径。登记只写本轮口径，不做「变慢」结论。 |
