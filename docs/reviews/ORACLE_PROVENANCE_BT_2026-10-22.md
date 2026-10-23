# BT 轮：验收 oracle 来源与可见性——写入端说反了，读端为 0（零 LLM，$0）

## 1. 发现

`oracle_type` / `test_visible_to_system` 是 R52（2026-09-30）加入的 APR 严谨性
检查点，用来回答两件事：**这批数字的验收信号是什么来源？系统是否看得见测试？**
归档实测（`experiments/results/` 全量）：

| 事实 | 数值 |
|---|---|
| 归档 JSON 总数 / 其中批次文件 | 1702 / **257**（其余 1445 份：108 份不可解析的 QuixBench 夹具 + 1337 份非批次形状，含 8 份顶层 list） |
| 结果行总数 | 11197 |
| 带 `oracle_type` / `test_visible_to_system` 的行 | **8012**（131 份文件） |
| 两个键的取值分布 | `generated_test` × **8012**、`True` × **8012**（无一例外；其余 3185 行两键均缺） |
| 两键的读端（`experiments/` + `scripts/` + `src/`） | **0** |
| 带 `repo_verification` 的行 | **50**，来自 **20 个唯一任务**跨 3 组同名孪生文件（`benchmark_*` 与 `full_stack_*` 每对任务集相同：17 个任务出现 2 份、1 个出现 4 份、2 个出现 6 份 ⇒ 34 + 4 + 12 = 50），全部 `aitester` 单臂、2026-09-29 g8 批次，早于 R52 |
| 其中带 oracle 键的行 | **0**（全部 `(None, None)`，即"未记录"） |

两处问题：

1. **写入端把仓库级验收说反了。** SWE-bench 的 `passed` 在
   `experiments/run_benchmark.py:2972`（`final_state["test_passed"] =
   repo_result["passed"]`；路由 `if` 起于 :2917，`executor_repo.verify` 在
   :2958）被 gold FAIL_TO_PASS /
   PASS_TO_PASS 覆盖；gold 测试由 harness 在仓库内执行，**不进入任何 agent
   prompt**。但两个键硬编码为 `oracle_type="generated_test"`、
   `test_visible_to_system=True`——任何新的 swe_bench 批次都会被标成
   "生成测试验收且系统可见"。
2. **读端为 0。** 8012 行写入了检查点，报告面从没读过；读者只能手动翻 JSON。

历史影响需要说清：**归档里没有"标错"的行**——所有 repo 行都早于 R52，字段
直接缺失（`None`），不是错标。本项修的是"下一次跑批会说错"，并把只写不读的
键接上读端。

## 2. 处置

**写入端（按基线真实路径取值，而非按状态猜）**

- 新增 `experiments/_oracle_provenance.py` 作为标签单一事实源：
  `generated_test` / `enhanced_generated_test` / **`gold_fail_to_pass`**；
- 新增 `run_benchmark._oracle_descriptor(task, baseline, final_state)`：
  `baseline == "aitester"` **且** `REPO_LEVEL_EXECUTION` 开启 **且** 任务带
  `source=swe_bench` + `fail_to_pass` + `repo_url` + `base_commit`
  → `("gold_fail_to_pass", False)`；否则回落到生成/增强测试 + `True`；
- `_build_task_result(..., oracle=...)` 增加显式参数，成功/限流重试/两类失败/
  harness_invalid **五个构造点**全部传入描述符——崩溃行也声明它**本该**使用的
  oracle，而不是把崩溃折成"生成测试验收"。

**读端（新增报告章节）**

- `statistical_analysis.oracle_provenance_stats(rows)`：按行统计词表内取值、
  `not_recorded`（键缺席/值为 null）、`other`（词表外，单列 `other_values`）、
  可见性三档；repo 行分**三档**——`repo_rows_unrecorded`（两键全缺，即早于 R52
  的历史批次）、`repo_rows_consistent`（`gold_fail_to_pass` + `False`）、
  `n_violations`（其余，含**只记录一个键**的不完整声明），恒等式
  `unrecorded + consistent + violations == repo_rows`；
- `analyze_results.build_analysis` 增 `per_baseline.oracle_provenance`，
  `render_markdown` 新增「验收 oracle 来源与可见性」章节：11 列表 + 不一致逐条点名 +
  两条口径脚注（"未记录 ≠ 生成测试验收"、"repo 缺声明 = 两键全缺，不计入不一致"）。
  **不进入任何判定**（不改 passed / repair / 分母）。

## 3. 验证

- 新增 **40 例锁**（`tests/test_oracle_provenance_bt.py`，逐类取自 `--collect-only`
  实测）：描述符 11 / 组装写端 3 / 统计分档 15 / 构造点接线 3 / 报告面 8。含
  仓库材料逐项参数化、崩溃行写 gold+隐藏、默认回落仍问标签助手、归档 50 条缺键
  repo 行钉成 `50/50/0/0`、AST 结构锁（描述符的条件项集合 = 真实路由 `if` 的
  条件项集合，各 6 项），以及报告 11 列表格的逐格期望串。
- 键集棘轮（BQ 的"恰好 +1 键"）改为显式登记两个新增键——键集只增不删。
- 变异 **48 锚点全红 + 中性对照 0 红**（见下节「变异验证」）。
- 预登记跑（`make test-cov`，含 `--cov`，xdist `-n 4 --dist loadfile`）collected
  **12110** = **12104 passed** + 5 skipped + **1 failed**、**215.61s / rc=2**——
  唯一红 = 基线数对账守卫（当时 BASELINE 仍写 12077，实收 − 声明 = 33 > 6 容差）。
- 刷新后确认跑（`make test`，无 `--cov`）collected **12110** =
  **12105 passed / 5 skipped / 0 failed、209.80s / rc=0**（37 warnings；墙钟
  **211s**，`date +%s` 成对采集 1792680497→1792680708）。事前预测为 collected
  12110 = 12105 + 5（BT 锁 12→40 例，+28；BQ 棘轮只改断言不改用例数），实测逐位命中。
- 覆盖率：行 **19526/20040 = 97.4351%** 与 BS 逐位相同；弧 **7150/7582 = 94.3023%**
  （BS 记 7148，**+2 在已登记的 ±2 抖动内**）。依据不是"读数相同"而是
  `git status --porcelain src/` 命中 **0**——本轮改动面在 `experiments/` + 测试 + 文档，
  覆盖率分母只测 `src/`。
- `make gates` 全链 **rc=0** 两跑（`date +%s` 成对采集）：首跑墙钟 **199s**（1792681705→1792681904；链内 **12105 passed / 5 skipped / 0 failed、193.44s、41 warnings**），跑在 §6⑦（BP 段落补回）之前；终跑墙钟 **200s**（1792682426→1792682626；链内 **193.76s、42 warnings**、collected **12110**、`4 workers [12110 items]`），跑在本轮全部登记文本完成、门禁句回填之前。链内 pytest 为 xdist `-n 4 --dist loadfile` 且不带 `--cov`（与 §3 确认跑同一采集面，用时不可与含 `--cov` 的预登记跑 215.61s 相减）。链首 `ruff check .` All checks passed、`ruff format --check .` **1010 files already formatted**、`mypy src/ config.py` **137** 源文件 0 错。链尾分步：`env-budget` 253/253、零断言门扫 **467** 个测试文件（零断言 0 / 豁免 0 / 违规 0）、`ast-guards` **136/79/20/0/20/19**、`status-persistence` 10 通道 / 3 落盘面全覆盖、报告→工件对账 1 文档 × 3 臂 × 11 列通过、状态登记册 §1 覆盖率对账在 ±0.20pp 容差内通过。**门禁读数里唯一变动的一格**：`ast.parse` 守卫站点 78→79——由 **BR** 在 `src/agents/executor_imports.py::_insert_sys_path_prefix` 新增的 `except AST_UNREADABLE_ERRORS` 守卫带来（BT `git status --porcelain src/` 命中 0），BK/BL 登记的「链内读数 136/78/20/0/20/19 逐位相同」就此过期，登记不追改。
- 回填只改文档：本条写完后重跑文档面锁 4 件（`test_markdown_table_integrity` / `test_ao_batch` / `test_2026_10_10_optimization_batch` / `test_prompt_artifacts_gate`）**87 passed / 0 failed**、`ruff format --check .` **1010 files already formatted**、`check_bilingual_docs.py --strict` 与 `check_doc_links.py --strict` 各 rc=0（重跑读数不再登记为链条读数）。

## 变异验证（48 锚点 + 1 中性对照）

`scripts/tools/bt_mutation_verify.py`：受影响面 = BT 新锁 + BQ/BP/BM 既有锁 +
两个分析套件，合跑 collected **165**；预检 49 个锚点在原文件中各唯一命中一次。

| 锚点块 | 钉住的守卫 | 结果 |
|---|---|---|
| T01–T19 | 写入端 `_oracle_descriptor` 的六个条件项、五个构造点接线、默认回落形状、路由同式 | 全红 |
| T20–T35 | 标签词表、七档分档、可见性真值判定、repo 行三档（缺声明 / 一致 / 不一致）、三档恒等式、违规明细封顶 | 全红 |
| T36–T48 | 渲染层零行臂、违规点名、词表外脚注、缺声明口径脚注、11 列表格逐格 | 全红 |
| T49（对照） | 仅改 docstring 措辞、不动任何判据 | **0 红** |

`rc=0`、墙钟 **385s**、基线 collected 165 绿、每锚点变异前后 collected 恒 165、
sha256 逐锚点原字节还原、残留扫描 `# mutation:` **0** 命中。逐锚点红数：
1/1/2/2/2/2/2/2/1/1/2/2/2/2/2/1/2/1/1/2/4/2/3/2/1/2/1/4/3/2/2/2/1/1/1/1/2/1/2/1/1/1/1/1/1/1/5/1。

两次跑不登记为读数：**结构改版前的 40 锚点跑**（锚点表已随 repo 分档重写而过时）与
**修 T44 前的 48 锚点跑**（`rc=2`，T44 存活）。按纪律改完判据面就重跑整链，
故唯一读数是上面这次 48/48。

## 4. 复现

```bash
# 归档分布（必须按形状过滤：1702 份 JSON 里只有 257 份是批次文件）
python3 - <<'PY'
import json
import collections
import pathlib

rows = keyed = batch = skip_parse = skip_shape = repo_rows = 0
typ = collections.Counter()
repo_shape = collections.Counter()
for p in pathlib.Path("experiments/results").rglob("*.json"):
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        skip_parse += 1
        continue
    if not isinstance(d, dict) or not isinstance(d.get("results"), dict):
        skip_shape += 1
        continue
    batch += 1
    for block in d["results"].values():
        for r in (block or {}).get("details") or []:
            if not isinstance(r, dict):
                continue
            rows += 1
            keyed += "oracle_type" in r
            typ[str(r.get("oracle_type"))] += 1
            rv = r.get("repo_verification")
            if isinstance(rv, dict) and rv:
                repo_rows += 1
                key = (r.get("oracle_type"), r.get("test_visible_to_system"))
                repo_shape[key] += 1
print(f"批次文件 {batch}（跳过不可解析 {skip_parse} / 非批次形状 {skip_shape}）")
print(f"结果行 {rows}｜带 oracle 键 {keyed}｜取值 {dict(typ)}")
print(f"repo 行 {repo_rows}｜两键形状 {dict(repo_shape)}")
PY
# 实测：批次文件 257（跳过 108 / 1337）｜行 11197｜带键 8012
#       {'None': 3185, 'generated_test': 8012}｜repo 行 50｜{(None, None): 50}

# 报告章节
python3 experiments/analyze_results.py --input <batch.json>   # 见 "验收 oracle 来源与可见性"
```

## 5. 未做 / 边界

- **历史工件不重写**：归档 8012 行仍是 `generated_test/True`（R52 之后的本地批
  本就是这个事实）；50 行 repo 记录仍是 `(None, None)`，报告面显示"未记录"。
- **未跑真实 swe_bench 批次**：修复的验收点是 `_oracle_descriptor` 的静态条件与
  五个构造点的接线，端到端需一次仓库级跑批（成本远高于本轮零 LLM 预算）。
- **论文数字不受影响**：两键从未进入判定或统计分母；本轮只纠正声明并新增读端。

## 6. 本轮自纠（同一族缺陷在 BT 自己的读端复现）

① **缺键折成不一致**。第一版 `oracle_provenance_stats` 对 repo 行只问「是不是
gold + 不可见」，于是归档 50 条**两键全缺**的 g8 记录被折成 50 条不一致——正是
本轮 §1 自己声明的「缺键 ≠ 错标」的反面，且方向是**加重指控**（把没说过话的行
判成说了假话）。改为三档 `repo_rows_unrecorded` / `repo_rows_consistent` /
`n_violations`，恒等式三档相加 = `repo_rows`；表格加 `repo 缺声明` 列 + 脚注；
锁面加归档实钉（6 份 g8 文件 → `50/50/0/0`）。只记录一个键属**不完整声明**，
仍计入不一致——缺两键是"没声明"，缺一键是"声明错了"。

② **T44 存活暴露「未被断言的单元格」**。`repo 缺声明` 格的抹零锚点首轮存活，
根因是夹具里该格真为 0（只放一致 + 违规两行），把渲染改成常量 `0` 是恒等操作。
补第三类输入（两键全缺的 repo 行）后期望行变为
`| aitester | 1 | 0 | 1 | 1 | 0 | 3 | 3 | 1 | 1 | 1 |`，锚点转红 `red=1`。
教训：N−1/N 的"全红"里藏着**没有断言消费的那一格**。

③ **§4 复现命令在真归档上会崩**。原片段直接 `d.get("results")`，而 1702 份 JSON
里只有 **257** 份是批次形状（108 份不可解析、1337 份非批次，含 8 份顶层 list）。
手册里写的复现命令必须先在真语料上跑一遍再说"可复现"。

④ **§1 唯一任务数登记错误**。原文写「25 个唯一任务 × 2」；实测 50 条 repo 行来自
**20 个唯一任务**跨 3 组同名孪生文件（17 个任务出现 2 份、1 个 4 份、2 个 6 份
= 34 + 4 + 12）。带日期的更正就地写在这里，不改 §1 已修正后的表。

⑤ **引用行号更正**。gold 覆盖判定在 `experiments/run_benchmark.py:2972`
（`final_state["test_passed"] = repo_result["passed"]`；路由 `if` 起于 :2917、
`executor_repo.verify` 在 :2958），原文写的 `:2920` 落在路由体内部而非覆盖点。

⑥ **AO3 行锁落后两轮**（顺带收口的存量面）。
`tests/test_ao_batch.py` 在 BR、BS 两轮都没推进，仍断言 `"**BQ round:"`，而该字面
此时只在 `README.en.md` 头部的历史链 `Previously **BQ round:` 命中——即 BC 轮
docstring 自己记过的**误绿**形态（头部再怎么往回退也不会转红）。BT 推进至
`"**BT round:"`（头部唯一命中，历史链首项 `Previously **BS round:`；
单逻辑行剔除行内代码后 `**` = 476 为偶）。

⑦ **CHANGELOG 的 BP 段落是一个空标题**（回填门禁读数时顺手量到的文档面存量缺陷）。
`CHANGELOG.md` / `CHANGELOG.en.md` 里 `## [Unreleased] — 2026-10-22 BP 轮/round` 之后
**直接跟着下一个 `## [Unreleased]`**——正文一个字都没有，而且这个标题卡在"最新段之上"
的位置（时序上 BP 早于 BQ）。`git log -S` 定位：`b44a1aad`（BD→BP 批次）根本没写过 BP
段，标题是 `c236cada`（BQ 轮收口）插入的，自那次提交起就是空的，并已随 BS 入库。
处置：按 `docs/reviews/CONTAMINATION_ABSENT_BUCKET_DISCLOSURE_BP_2026-10-22.md` 的实测段
把正文补回（159 份 / 320 臂、`key_absent` 2093、122 个沉默臂、198 个可对照臂 0 个差值、
62 例锁、变异 18/18 collected 恒 154、确认跑 11922 / 5 / 0、195.48s / rc=0），
并把段落移到 BQ 与 BO 之间恢复 newest-first。双语同改（H2 骨架对账要求两侧标题序列一致：
`check_bilingual_docs.py --strict` rc=0）。
教训：**登记册与 CHANGELOG 的"条目存在"不等于"条目有内容"**——本轮的键集棘轮讲的是
"写了没人读"，这里是另一个方向：**读得到标题、读不到正文**，而门禁只数标题序列，
所以空标题一路绿灯。判据：滚动式文档收口时，除断言"标题在场"外还要断言"该标题到下一个
标题之间存在正文"。
