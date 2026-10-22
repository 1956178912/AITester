# BP 轮：统计对照面把「这一行没记录污染级别」折成沉默（2026-10-22，零 LLM，$0）

> 语言：中文（本册）。系列位置：BH → BI → BJ → BK → BL → BM → BN → BO → **BP**（第 8 面）。
> 本轮零 LLM 调用、$0 支出；全部读数为实测，未跑的事一律写「尚未执行」。

## 1. 缺陷：同一个「行内没有级别」，两个消费者折成两种东西

`contamination_risk_level` 是污染检测写到结果行上的字段。BM 轮把「检测腿崩了」从
`low` 里摘出来归 `unknown`，但**「这一行根本没写这个字段」在下游仍然是沉默的**：

1. **`experiments/analysis_parts/cross_analysis.py:56`（改前 `:42`）的 `if not level: continue`**
   ——一条语句把「键不存在 / 值为 null / 精确空串 / 其他假值」四种形状一起丢掉：不进桶、
   不计数、输出里也没有「被丢了几行」的面。读者只看得到 `by_risk_level` 的合计比行数少；
   若**整臂**都没有该字段，则 `observed == 0` ⇒ `available=False` ⇒ 5.3 节在报告里**整节消失**，
   与「这一节没跑」同形。
2. **`experiments/statistical_analysis.py:1469` 的 `recorded or "unknown"`**（批次 IX 历史口径）
   ——同一批行被**并进 `unknown`**，与「检测跑了但判不了」同计数。
   于是 5.3 表的「未入对照任务」列（按①口径）与批次 IX 的 `unknown` 列（按②口径）
   之差正好是那批被丢掉的行数，而**没有任何一处能把它减出来**。
3. **渲染层 `experiments/analyze_results.py` 5.3 节**：`excluded` 只加三档合计，未记录行既不在
   表内也不在列里；脚注却按②口径把「未记录」写成 `unknown`（**本表实际并不这样计**）；
   `available=False` 的臂被 filter 直接丢弃，不点名。
4. **`high_vs_low_success_delta`**：docstring 声明 `float | None`，代码在两档不齐时是**键不存在**；
   消费方 `.get()` 到的 `None` 与「真值 None」同形，读者拿不到「缺的是哪一档」。
   更糟的是 5.3 的解读句写着「若差异 ≤0.2，说明污染效应不显著，**结果可信度较高**」——
   归档里这个差**从来没有数**（见 §3.3），`N/A` 被顺着那句读成了有利判定。

## 2. 处置：只把沉默换成分档披露，判定值与方向一处不动

| 站点 | 改后 | 判定影响 |
| --- | --- | --- |
| `_contamination_cross_analysis` | 缺席按四档计数 `unobserved{key_absent, value_null, value_blank, other_falsy}` + `unobserved_total` + `n_details`；`available=False` 时补 `reason`（`no_rows` / `no_level_recorded`）；两档不齐时把 `high_vs_low_success_delta` **落成显式 `None`** 并给 `delta_missing_buckets` 点名缺失档 | 桶的键集合与各桶数值、`available` 取值、可算时的 delta 数值**逐位不变**（锁里逐字重写改前算法做对比）；未记录行仍不进任何桶 |
| `contamination_view_summary` | `counts` 与两率一字不动，只加平行键 `unknown_of_which_absent`（`unknown` 里有多少行属于「根本没记录」） | 批次 IX 口径原样保留 ⇒ 与 5.3 表之差变成**可减出来的数** |
| 5.3 渲染 | `excluded` 再加 `unobserved_total`；`available=False` 且有行的臂按名列入「本节未列出 N 个基线：…」并写明「**不是「检测干净」，也不是「没有任务」**」；`N/A` 单元格写成 `N/A（high 档无行）` / `N/A（high、low 档无行）`；全表都算不出差时追加一句：≥0.2 / ≤0.2 判据在此**无从应用** | 表格数值不变；脚注保留 BM 锁要求的子串 `未入对照任务」= medium/unknown/not_applicable`，但不再把「未记录」说成 `unknown` |

两条口径约束（实测得出，不是设定）：

- **空白串 `" "` 不算缺席**。它在②侧是真值、自成一档，改前①侧同样把它记作观测到，
  若划进缺席则两消费者恒等式在遇到一个空格字符时破。故 `value_blank` 只收**精确空串**。
- **`n_details == 0` 的臂不进「未列出」披露**——「没有行」与「有行但全没记录」是两件事，
  前者仍维持原状（本节不渲染）。

## 3. 测量（全部实测；Python 3.14.6，零 LLM；探针 `scripts/tools/bp_contamination_bucket_probe.py`）

### 3.1 A 段：取值形态普查

含该键的批次文件 **159** 份、参与对账的 (文件, 臂) **320** 个；行形态 =
`vocab:not_applicable` **7580** / `key_absent` **2093** / `vocab:low` **986**（合计 10 659 行）。
缺席合计（键不存在 + null + 精确空串）= **2093**，其中 **null 0 行、空串 0 行**
⇒ `value_null` / `value_blank` / `other_falsy` 三档在归档 0 实例，是为新批次与外部工件准备的腿。
词表内**没有** `high` / `medium` / `unknown` 三档的归档行 ⇒ 高 vs 低对照在本库从来没有输入。

### 3.2 B 段：两消费者对账（改后复跑）

有未进桶行的臂 **122**、未进桶行数合计 **2093**；两条恒等式在**全部 320 臂**成立、
不成立 0：`view.counts["unknown"] == 真 unknown 行数 + cross.unobserved_total`、
`view.unknown_of_which_absent == cross.unobserved_total`。
样例：`benchmark_synthetic_20260816_180235.json [aitester]` n=30 ⇒ cross 进桶 0 / 未进桶 30，
view 侧 30 行全记进 `unknown`（改前两数差 30 且无处可减）。

### 3.3 C 段：渲染层对账

`available=True` 的臂 **198**；`available=False` 的臂 **122**，其中「确有行但全部行无该字段」**122**
（⇒ 归档里不存在「空臂被误报成未记录」的实例，但锁把它当口径边界钉住）。
`high_vs_low_success_delta` **键缺席的臂 = 0**（改后 `None` 已落到位）、**显式为 None 的臂 = 198**，
缺失桶分布 = `{"['high', 'low']": 157, "['high']": 41}` ⇒ **198 个可对照臂里 0 个产出差值**。
「表内合计 ≠ 行数」的臂 = **0**，且**改前公式**（三档合计）的差额分布也是 `{}`
⇒ `excluded += unobserved_total` 这一处在归档 0 实例（198 个可对照臂的未记录行数都是 0，
2093 行全部落在 122 个整臂沉默的臂里），它的意义在改后新批次与外部工件。

### 3.4 全量回归、覆盖率与写入面

- 预登记跑（`make test-cov`，含 `--cov`）collected **11927** → 11921 passed / 1 failed / 5 skipped、
  10 warnings、**204.54s** / rc=2，墙钟 **206s**（`date +%s` 成对采集 1792650424→1792650630）；
  唯一红 = 基线数对账守卫（`tests/test_2026_10_10_optimization_batch.py:172`，
  「实收 11927 − passed 11860 = 67 > 6」），随 `BASELINE.yaml` 刷新消失。
- 另有一次**先于 BASELINE 刷新执行**的不带 `--cov` 全量跑（本轮顺序失误：应先刷新再跑确认跑）：
  collected 11927 → 11921 passed / 1 failed / 5 skipped、33 warnings、201.21s / rc=2，墙钟 203s
  （1792650718→1792650921）。登记为「刷新前跑」，不作为确认跑读数。
- 刷新后确认跑（`make test`，**不带 `--cov`**）：collected **11927** → **11922 passed / 5 skipped / 0 failed、
  195.48s / rc=0**（22 warnings；与预登记跑同一采集面；墙钟 **197s** 由 `date +%s` 成对采集
  1792651405→1792651602）；登记口径 = collected **11927** − skipped 5 = **11922**（预登记跑的 11921 是
  「11922 − 基线守卫那一红」，刷新后该例转绿，故两跑 passed 差 1、collected 相同）。
- 覆盖率：`coverage.xml`（预登记跑工件，mtime 1792650628）root **19393/19904 行 = 97.4327%**、
  **7105/7532 弧 = 94.3309%**，未覆盖 **511**、缺弧 **427**；13 项逐模块行覆盖按本工件复算
  **逐项与 BO/BN/BM 相同**（base_agent 98.53 / api_manager 99.24 / dataset_loader 97.28 /
  graph_nodes 99.88 / code_analyzer 99.38 / planner 99.09 / dependency 96.26 / multi_candidate 99.36 /
  cross_file 94.82 / rag/retriever 98.10 / graph_workflow 99.72 / error_classifier 100.00 / graph_state 100.00）。
- 写入面普查（阈值 `st_mtime > 1792649000`，即 BO 链终跑之后）：仓库内可编辑文件命中
  **6** 个 = `experiments/statistical_analysis.py`、`experiments/analyze_results.py`、
  `experiments/analysis_parts/cross_analysis.py`、`scripts/tools/bp_contamination_bucket_probe.py`、
  `scripts/tools/bp_mutation_verify.py`、`tests/test_bp_contamination_bucket_disclosure.py`；
  **`src/` 命中 0、`config.py` 命中 0**（其余命中为 `.mypy_cache` / `.ruff_cache` / `.hypothesis` 等工件）。
- 同一阈值在登记批次后复算：命中 **6 → 9**，新增三项为本分册、`BASELINE.yaml`、
  `docs/PROJECT_STATUS_REGISTER.md`（后两者属登记面，非执行侧改动；`src/` 与 `config.py` 仍 **0**）。
  BASELINE 里登记的是这份 9 项清单，两处不是互相矛盾的读数，是**同一普查的两个时刻**。
- 格式化面：`ruff format --check .` = **994 files already formatted**（BO 的 990 + BP 新增 4 =
  2 个 `scripts/tools/bp_*` + 1 份测试锁 + 1 份中文分册；口径含 `.md`），与门禁链内读数同值。

## 4. 回归锁（`tests/test_bp_contamination_bucket_disclosure.py`，62 例；逐类计数取自 `--collect-only` 实测）

| 组 | 例 | 钉住什么 |
| --- | --- | --- |
| `TestAbsentShapesGetTheirOwnGrades` | 10 | 六种假值形状各自进本档（参数化 6）；四档各 1 时 `reason=no_level_recorded`；`" "` 记为观测到并自成一档；`no_rows` vs `no_level_recorded` 两种不可用分得开 |
| `TestJudgmentValuesDidNotMove` | 21 | 7 份语料 × 3 条：**逐字重写改前算法**后对比 `available` / `by_risk_level` / 可算时的 delta，与批次 IX 的 `counts`、两率对比；披露键在参照实现里不存在；`Σ桶 + unobserved_total == n_details` 且分档键与桶键互斥 |
| `TestDeltaIsAnExplicitNone` | 3 | 双缺时 `delta_missing_buckets == ["high","low"]` 且**键在场**；只缺 high 时 `["high"]`；可算时不挂 `delta_missing_buckets` |
| `TestTwoConsumersReconcile` | 15 | 7 份语料 × 两条恒等式 + `unknown` 与缺席构成的自证 |
| `TestSectionFiveThreeDiscloses` | 9 | 沉默臂点名 + 「不是检测干净」；`n_details=0` 臂不进「未列出」；**全部臂不可对照时本节仍要出现**；`excluded` 含未记录行；`N/A（high 档无行）` 落进单元格；全表 N/A 时追加「判据无从应用」句且可算时不追加；BM 脚注子串存活 + 新口径句；真「没有行」仍不渲染本节；`unknown` 列构成披露的有/无两支 |
| `TestDisclosureAnchorsInSource` | 3 | 三处实现的关键语句在场（防披露被整段删） |
| 模块级真归档复算 | 1 | 前 **8** 份批次文件逐臂复算两条恒等式与「桶 + 缺席 = 行数」，并要求可比对臂数 > 0（防空跑） |

既有断言**无需改写**：`tests/test_bm_experiments_readside.py` / `tests/test_experiments_analysis.py` /
`tests/test_batch_ix.py` 共 92 例在改后原样通过（含 BM 的 `| b | 1 | 1.0 | 1 | 0.0 | 1.0000 | 3 |`
与脚注子串锁）；四个受影响套件合跑 **1415 passed / 3 skipped / 0 failed**。

## 5. 变异验证（`scripts/tools/bp_mutation_verify.py`：18 锚点 + 1 中性对照）

每个变异都写成「把 BP 补的披露退回沉默 / 退回有利判定」的方向；逐锚点：读原字节 → 写变异 →
`compile()` → 采集面核对 → 跑受影响面 → `finally` 按 sha256 还原（不使用 `git checkout` / `git stash`）。
基线 rc=0 / red=0 / **collected=154**（62 新锁 + 92 既有），逐锚点采集面恒 154，无 COLLECTED-DRIFT。

| 锚点 → 红 | 锚点 → 红 | 锚点 → 红 |
| --- | --- | --- |
| 键缺席并入 null 档 → 4；键在场判据摘掉 → 4；null 不记缺席 → 2；空串不记缺席 → 2 | `reason` 塌成一档 → 5；`n_details`/`unobserved_total` 抹平 → 26；delta 的 `None` 写成 `0.0` → 4；缺失档不点名 → 3 | `unknown_of_which_absent` 写 0 → 8；缺席行不计数 → 7；构成披露整块删 → 1；`or "unknown"` 折叠改写 → 12 |
| `excluded` 不加未记录行 → 2；沉默臂仍整节消失 → 1；没有行也说成没记录 → 3；单元格不点名缺失档 → 2 | 全表 N/A 的「判据无从应用」句删 → 1；`delta_computable` 恒 False → 1 | **对照**（只改 docstring 措辞）→ **0 红（要求 SURVIVED）** |

**击杀 18 / 18，中性对照 0 红，采集面逐锚点恒 collected=154，`# mutation:` 在 `experiments/`+`src/`+`tests/`
残留 0**；复跑墙钟 **141s**（`date +%s` 成对采集 1792650952→1792651093）。

首轮有一处**存活**：`if contam_cross_rows or silent_cross_arms:` 改成 `if contam_cross_rows:` 时 0 红
（锁里所有渲染用例都至少有一个可对照臂，节标题照样出现）。这是覆盖不足，不是锚点冗余——
补 `test_section_survives_when_no_arm_is_comparable` 后复跑击杀（红=1）。

## 6. 踩坑与自纠（本轮实测发生的）

**① 「0 红」有两种成因，必须分开。** 上一句里 P14 的存活第一眼看像「锚点已被别的锁间接覆盖」，
但把该锚点的语义写成一例（全部臂都不可对照）就红了。红数不能反推覆盖面，覆盖面只能靠
「这条披露在什么输入下才可见」逐条问出来。

**② 恒等式的成立条件写在实现里、没写在断言里 ⇒ 会假绿。** `value_blank` 初版按
`not level.strip()` 划档，本地跑全绿；但它把 `" "` 也算缺席，而批次 IX 侧 `" "` 是真值自成一档，
两数在含空白串的语料上就差 1——归档恰好 0 行空白串，**探针和真归档都测不出来**。
改判据（只收精确空串）后恒等式变成无条件成立，并单独钉一例。

**③ 顺序失误：确认跑早于 BASELINE 刷新执行**，带着基线守卫那一红跑完了 203s。
登记为「刷新前跑」并补跑确认跑——同一批读数不能因为「跑过」就当成契约里的确认跑。

**④ zsh 的 glob 又咬了一口**：`grep -rn "x" --include=*.py .` 在未匹配时整行中止
（`no matches found`），本轮第二次踩中，改用 Grep 工具或加引号。

**⑤ 粗体奇偶是个「口径未定义」的检查，两边都会咬人。** 本轮靠 `line.count("**") % 2` 抓到并修好了
`README.en.md:3` / `docs/INDEX.en.md:3`（插入文本带了奇数个 `**`，打乱了 EN 惯例的「轮次名加粗不闭合」）；
但同一个朴素计数在 `docs/PROJECT_STATUS_REGISTER.md:3` 上是 **假阳性**：原值 785（奇）里有一对 `**`
写在行内代码中，剔除 `` `…` `` 后是 784（偶），该行本来就没有未闭合粗体。反过来，整文件逐行数奇偶
也不是可用信号——CHANGELOG 与廉洁分册有几百行是奇数，因为粗体**跨行延续**（同一段落内 GFM 允许）。
可用口径只有一种：**单逻辑行**（这些巨型 head 行）+ **先剔除行内代码与转义** 后再看奇偶。


## 7. 边界与未收口部分（按名登记，不写成「已排除」）

1. **高 vs 低污染对照在本库仍无数**：归档 0 行 `high`/`medium`/`unknown`，本轮只让「没数」可见，
   不制造样本。要真跑对照需要带黄金补丁重叠的批次（消耗 LLM，不在本轮）。
2. 未记录行**仍不进任何桶**（判定不变）；②侧继续按批次 IX 口径把未记录行并计 `unknown`，
   两表口径差**保留但可减**——统一两口径会改写历史读数，本轮不做。
3. 词表外真值（如 `" "`、`"off_vocab"`）在②侧会**自创新计数键**（`counts` 键集不定长），
   在①侧自成一桶；两侧一致所以恒等式成立，但这类值既不进对照也不进 `unknown`，
   本轮未给它单独的「词表外」披露档。
4. `value_null` / `value_blank` / `other_falsy` 三档归档 0 实例，为新批次与外部工件而准备。
5. **本轮未新增门禁**：读侧折叠由 62 例锁覆盖；把「缺席必须分档」做成棘轮需要一个可机读的
   声明源（哪些字段允许缺席、缺席须披露到哪一格），目前没有。
6. 历史批次工件与 `SHA256SUMS` 覆盖的产物**不改写**；`reason` / `unobserved` / `delta_missing_buckets`
   只出现在改后新产出的分析字典与报告里。
7. **文档渲染面（粗体未闭合）无人守**：本轮只跑过 `test_markdown_table_integrity.py`（钉列数与行尾 `|`），
   没有任何锁读「一行内 `**` 配对」。按上面⑤的口径实测 6 份登记面文件的 head 行（剔除行内代码后）：
   `README.md` 396 / `README.en.md` 422 / `docs/INDEX.md` 302 / `docs/INDEX.en.md` 276 /
   `docs/PROJECT_STATUS_REGISTER.md` 784 / `docs/MEASUREMENT_INTEGRITY.md` 56 —— **全部为偶，当前零缺陷**；
   6 份文件的 HEAD 读数同为偶（HEAD：74 / 132 / 38 / 26 / 570 / 22）⇒ 未闭合粗体只在 **BP 登记批内部**短暂出现过：
   批前备份 `README.en.md` 374、`docs/INDEX.en.md` 228（皆偶），批中插入文本后转为奇，补 `**` 闭合后复归偶，
   历史各轮不受牵连。未收口的是：这类缺陷要靠人肉检查才会被发现，
   做成门禁需要先定义可机读的口径（哪些行算「单逻辑行」、行内代码/转义/跨行延续怎么剔除），本轮未做。
8. 候选池剩余项按名登记（本轮未做）：`EXEMPT` 里 20 处 `ast.parse` 站点与 `experiments/`+`scripts/`
   报告面；`outcome_sink=None` 的调用方；额度里「collapse shape」仍是文本；D/D2 类普查缺 BL 之前的
   历史读数，差值不可减。

## 8. 复算命令（零 LLM、只读或可自还原、可逐条重跑）

```bash
# 1) 本轮 62 例新锁（先看 collected=62，再看 rc）
.venv/bin/python -m pytest tests/test_bp_contamination_bucket_disclosure.py -q -p no:cacheprovider

# 2) 四个受影响套件合跑（应 0 红，含 BM 的既有 92 例）
.venv/bin/python -m pytest tests/test_bp_contamination_bucket_disclosure.py \
  tests/test_bm_experiments_readside.py tests/test_experiments_analysis.py tests/test_batch_ix.py -q

# 3) 三面只读探针（A 形态普查 / B 两消费者对账 / C 渲染层对账）
.venv/bin/python scripts/tools/bp_contamination_bucket_probe.py

# 4) 变异验证：18 锚点 + 1 对照（临时改写三个 experiments/ 文件，finally 按 sha256 还原；
#    中止过必须扫残留并复跑第 1 条）
.venv/bin/python scripts/tools/bp_mutation_verify.py

# 5) 写入面普查（只读；阈值须取上一轮链终跑之后的明确时刻）
.venv/bin/python - <<'PY'
import pathlib
cut, hits = 1792649000, []
for p in pathlib.Path(".").rglob("*"):
    if p.is_file() and not any(x in str(p) for x in (".venv/", "__pycache__", ".git/", ".mypy_cache", ".ruff_cache", ".hypothesis", "experiments/results/")) and p.stat().st_mtime > cut:
        hits.append(str(p))
print([h for h in hits if h.endswith((".py", ".md", ".yaml"))], "src/ 命中 =", sum(1 for h in hits if h.startswith("src/")))
PY

# 6) 粗体配对面（只读；§7-7 的六个数字由这条复算。口径 = 只看单逻辑行 head + 先剔除行内代码，
#    朴素逐行 count("**") % 2 在两个方向上都会误判，见 §6⑤）
.venv/bin/python - <<'PY'
import pathlib, re
files = ["README.md", "README.en.md", "docs/INDEX.md", "docs/INDEX.en.md",
         "docs/PROJECT_STATUS_REGISTER.md", "docs/MEASUREMENT_INTEGRITY.md"]
code = re.compile(r"``[^`]*``|`[^`\n]*`")
for f in files:
    head = pathlib.Path(f).read_text(encoding="utf-8").splitlines()[2]
    n = code.sub("", head).count("**")
    print(f, "raw", head.count("**"), "stripped", n, "ODD" if n % 2 else "even")
PY

# 7) 全量回归（先 test-cov 预登记，刷新 BASELINE 后再 test 确认跑）与门禁链（最后、单独、不接管道）
make test-cov && make test && make gates
```

## 9. 收口批注

- 预登记跑（`make test-cov`）：见 §3.4，collected **11927** → 11921 / 1 / 5、204.54s / rc=2、墙钟 206s。
- 刷新前的一次不带 `--cov` 跑（顺序失误，非确认跑）：11921 / 1 / 5、201.21s / rc=2、墙钟 203s（1792650718→1792650921）。
- 刷新后确认跑（`make test`，**不带 `--cov`**）：**11922 passed / 5 skipped / 0 failed、195.48s / rc=0**
  （22 warnings；collected **11927** 与预登记跑同一采集面；墙钟 197s，1792651405→1792651602）。
- 门禁链 `make gates`：首跑 **rc=0、墙钟 203s**（`date +%s` 成对采集 1792652359→1792652562；链内全量
  **11922 passed / 5 skipped / 65 warnings in 197.00s**、`994 files already formatted`、
  mypy `Success: no issues found in 137 source files`；与双语登记回填不重叠执行）。
  回填后终跑 **rc=0、墙钟 203s**（1792652635→1792652838；链内全量 **11922 passed / 5 skipped /
  51 warnings in 197.48s**，`994 files already formatted` 与 mypy `137 source files` 两跑同值）。
  两跑之后只回填门禁读数，未跑第三链。
- 回填后**链外复验**（终跑之后又改过 `BASELINE.yaml` 与本分册的注释文本，故只复跑文档锁，**不叠第三链**）：
  文档锁子集 7 份（`test_check_baseline_numbers` / `test_ao_batch` / `test_markdown_table_integrity` /
  `test_check_doc_links` / `test_al_batch` / `test_ar_batch` / `test_artifact_doc_consistency_gate`）
  **154 passed / 0 failed、5.33s**（墙钟 1792652963→1792652969）；此后每一处纯文本回填（本条、§6⑤、§7-7、§8 第 6 条、登记册 §4 的 BP 边界行）之后各重跑同一子集，
  **每一跑都是 154 passed / 0 failed**（首跑 5.33s 有墙钟成对采集，其余各跑 3.85–5.12s 属同一棵树上的重复跑抖动，不作结论）；
  `994 files already formatted` 各跑同值，`check_bilingual_docs.py --strict` 亦 0 警告 / 0 失败；`ruff check .` **All checks passed**；
  `ruff format --check .` **994 files already formatted**（与链内两跑同值）。
  文档锁子集的 154 例只覆盖"文档改动是否破坏基线数字/链接/表格/AO3 头行"，不覆盖 `src/` 与 `experiments/`
  执行侧——执行侧结论仍以确认跑 **11922 / 5 / 0** 为准。
