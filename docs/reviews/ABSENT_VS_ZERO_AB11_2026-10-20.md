# AB-11：「键缺席」不等于「值为 null」，也不等于「读不动」（2026-10-20）

> 零 LLM、$0、全部改动堆在既有未提交树上。本轮把 AB-10 收口时"**还剩 3 处登记**"的
> 三处全部处置完（`analyze_t1_b2_main_batch.py`、`emse_docstring_augment_analysis.py`、
> `mast_trace_analysis.py`）。判据仍是 AB-9 的分析层口径（宁可响亮崩溃，不要一个看起来
> 正常的错数字），但本轮把它推进一格：**"缺席"必须落到一个不与任何正面读数同形的桶，
> 而"无法核验"的原因本身也是一个读数——原因写错同样是错的读数**。

## 1. 为什么是这三处

AB-9 §2 表里三行标着"登记，下一轮"（`analyze_t1_b2_main_batch.py:48`、
`emse_docstring_augment_analysis.py:105`、`mast_trace_analysis.py:73`），AB-10 没动它们。
三处的共同形态不是"丢数据"，而是**归因塌缩**——读数本身看起来是有据可查的，但据是假的：

- **站点 a**：`_profile_presets` 把四种失败机制（`git show` 失败、`ast.parse` 失败、
  `ast.literal_eval` 失败、根本找不到 `_PROFILE_PRESETS` 赋值）一律折叠成同一个 `{}`，
  而调用方把原因**写死**成 `"git show config.py 失败（无法核验）"`。三种与 git 无关的故障
  被报成 git 故障——披露的形对了，内容是假的。更要紧的是 `_profile_drift` 只问"预设表
  空不空"，从不问"档名在不在"：`o = old.get(profile) or {}` 让"**档位不存在**"和
  "档位存在且两边逐键相同"在下游**逐字同形**，都渲染成"无漂移"。
- **站点 b**：`spec_augment_applied` 一个字段被三种事实共用——生产者显式写下的 `null`
  （真的没触发）、详情行根本没有这个键（上一代生产者没写）、第二遍原始读取失败（工件读不动）。
  三者都落进 `domain_stats` 的 `none` 桶，报告读作"增广从未触发"，而实际是"审计面读不动"。
  原写法还给兜底分支加了 `# pragma: no cover`，把这条兜底从覆盖率口径里藏掉——
  而它恰恰是唯一会说出真话的分支。
- **站点 c**：`parse_trace_file` 读到坏行返回 `None`，调用方 `arms["unknown"]["damaged"] += 1`
  后 `continue`。一个 `meta.baseline` 写着臂名、文件名也带臂名的损坏文件，被整体归到
  `unknown` 桶；而"坏行之前已经解析出 N 条、这 N 条被整份作废"这件事**一个字节都没留下**。

## 2. 实测读数（先读数，再定处置）

### 2.1 站点 a：真路径走哪条分支（本轮可以改它而不动入库读数的原因）

就地复算 `_profile_drift(b533cff…, a93c1f60…)` 与归档
`t_round_b2_main_batch_20261018/ANALYSIS_REPORT.json` 的 `profile_preset_drift`：
**逐字段相等**（`available: true`、`profile: logic`、`added` 5 个开关、`removed` 与
`changed` 为空）。两个切点的 `_PROFILE_PRESETS` 都读到非空表、原因码都是空串，档位集合均为
`fast / logic / safe / scientific`——因此 `available=False` 分支与新增的档名缺席分支
**在盘上真工件上都不会被走到**，改造不动任何入库读数；也正因为它只在读不动/档名缺席时出现，
它产出的才是那条最像结论的错读数（"无漂移"）。

新增档名分支的实测读数：`_profile_drift(…, profile="no_such_profile")` ⇒
`{"available": false, "reason": "档位 'no_such_profile' 在旧切点、新切点的 \`_PROFILE_PRESETS\` 里不存在（档名缺席不等于该档无漂移）"}`。

### 2.2 站点 b：真工件落在哪个桶

盘上 `experiments/results/emse_docstring_augment_20261017/` 两批次 JSON 的 df 臂 50 行详情，
`spec_augment_applied` **键存在且值为 `null` 的行 50/50**——即真路径全部落在"真的没触发"这一桶。
三态改造后 `domain_stats` 仍为 `{"none": 50}`，与入库 `DF_AUG_REPORT.json` 逐字相同；
`key_absent` 与 `audit_unreadable` 两桶在盘上真工件上 **0 实例**（这正是它们必须与 `none`
分开的理由：0 实例的时候谁都不看见它们，非 0 实例的时候它们会被看见成 0 命中）。

### 2.3 站点 c：损坏面的全仓普查（`tmp_path` 之外的一次性只读普查）

全仓 148 个 `*/traces` 目录、9086 个 `*.trace.jsonl`：**5 个损坏文件**，每目录恰好 1 个；
坏行之前已解析出的记录分别 5 / 9 / 16 / 9 / 5，合计 **44 条被无痕作废**；非对象行 **0 个**；
"能打开但零事件"的文本文件 **0 个**。`main_batch/traces` 当前 2007 个文件、0 损坏。

## 3. 处置（三处，全部"静默 → 留痕或换桶"，没有一处把崩溃换成静默）

| 站点 | 处置 | 真路径影响 |
| --- | --- | --- |
| `_profile_presets` / `_profile_drift` | 返回域改为 `(预设, 原因码)`，四种机制各给各的码（`git_show_failed:<异常>` / `ast_parse_failed:<异常>` / `literal_eval_failed:<异常>` / `assignment_not_found`，另加"预设表为空"）；`_profile_drift` 的不可核验原因**由机制拼**，不再写死 git；新增档名缺席分支，`available=False` 且点名是哪一侧切点缺该档 | §2.1：真路径两切点均可读且含 `logic` ⇒ 归档读数逐字段不变 |
| `render_readme` 两处不可核验表述 | §0.5.2 行与 §5 局限条目都改为打印**登记的原因**，原因缺失时明写"原因未记录"，不冒充核验过 | 只在 `available=False` 时改变文案，真路径 `available=True` ⇒ 0 字节变化 |
| `load_augment_rows` | 值域三态：显式 `null` 仍是 `None`（`none` 桶＝真的没触发）、键缺席 → `key_absent`、第二遍读不动或 `task_id` 对不上行集 → `audit_unreadable` 并向 stderr 打**命名 WARN**（点名文件、臂键、异常类型与受影响行数）；回填与行集对不上时按 `details 行数 / 回填数 / 行摘要数` 三个数披露，重复 `task_id` 导致行集缩分时单独成句；删掉 `# pragma: no cover` | §2.2：50/50 落 `none` ⇒ 报告 JSON 与 Markdown 逐字节不变、stderr 空 |
| `parse_trace_file` / `analyze_traces` / `render_markdown` | 损坏不再返回 `None` 而是返回带 `damaged` / `damage`（机制名）/ `records_before_damage` 的结构；归臂口径与完好文件一致（`meta.baseline` → 文件名 → `unknown`），损坏文件计入**所属臂**的 `damaged`；被作废的记录数汇总成 `damaged_files_with_records` 与 `damaged_records_before_damage`，报告里**仅在存在损坏文件时**插一条"损坏留痕"披露行；模块 docstring 的口径句同步改为与代码一致 | 判定分母不变（损坏文件仍不进 `files`）；5 个损坏目录跑"改前 vs 改后"复刻，逐臂 `files` / `pattern_files` / `category_files` 全等，只有 `damaged` 从 `unknown` 搬回自己的臂；`main_batch` 0 损坏 ⇒ 报告逐字节相同 |

## 4. 入库工件字节不变（硬约束，验过才算）

```
# 站点 b
PYTHONPATH=. .venv/bin/python experiments/emse_docstring_augment_analysis.py \
    --json <批次JSON> --arm plain_llm_df --out /tmp/x.json --markdown /tmp/x.md
# 站点 c
PYTHONPATH=. .venv/bin/python experiments/mast_trace_analysis.py \
    --traces experiments/results/main_batch/traces --output /tmp/mast_after.md
```

实测：站点 b 两批次 JSON 的 `stderr` 为空、`--out` JSON 除 `inputs.*.path` 记录的临时路径外
与入库 `DF_AUG_REPORT.json` 相等、`--markdown` 与入库 `DF_AUG_REPORT.md` **逐字节相同**
（1493 字符，本轮由 `test_committed_augment_report_is_reproducible` 逐字锁住）；
**站点 c 那句"`/tmp` 复算与入库 `mast_distribution_report.md` `cmp` 相同"是本轮写下的过度声明，
AB-12c 轮实测撤销**：同一条命令（`--traces-dir experiments/results/main_batch/traces --output /tmp/…`，
rc=0）与入库报告在第 3 行第 123 个字符处即不同（`963 个 trace 文件` vs 实跑 `2007 个`）——
本册 §5 登记的正是这条陈旧，§4 与 §5 自相矛盾时**以盘上为准、§4 作废**。
错漏没被锁抓到的原因很直白：站点 b 有逐字复算锁，站点 c 只有一条"目录数已超声明数"的
陈旧登记，`cmp` 那句话从来没有对应的断言。站点 a 无需复算写盘——§2.1 已证其真路径分支不变。
三处都只碰 `/tmp`，受 `SHA256SUMS` 保护的目录 `git status` 干净、逐条校验 0 处不符。

## 5. 一条本轮才登记的陈旧声明（只登记，不改写）

入库 `main_batch/mast_distribution_report.md` 第 3 行写"963 个 trace 文件"、各臂"有效文件数 326"，
并声明"本报告为衍生工件，可用本脚本从入库 trace 逐位复算"。同一脚本对同一目录当前实跑给出
**2007 个文件**、aitester/plain_llm 各 **674**、plain_llm_df **609**、single_agent **50**。
差值是报告落盘后陆续补写进该目录的 trace——**"逐位复算"这条声明因输入增长而失效**，
不是脚本算错。本轮**不改写入库报告**（它受 `SHA256SUMS` 保护，且改动脚本措辞会连带破坏
§4 的逐字节复算），改为在 `tests/test_experiments_absent_vs_zero_ab11.py`
`test_committed_mast_report_census_is_stale_and_registered` 里把这个 staleness 锁住：
一旦有人把该行读成"复算成立"，锁会指出目录数已超声明数。

## 6. 验证层级与不得引用项

- **回归锁**：新文件 `tests/test_experiments_absent_vs_zero_ab11.py` **31 例**
  （站点 a 返回域与机制归因 9 + 渲染 4 + 站点 b 值域三态 5 + 站点 c 损坏留痕与归臂 6 +
  真路径不变量 7 含 5 目录参数化）；另按新口径改写 2 例既有断言
  （`test_ag_batch.py` 的"损坏返回 None"→"损坏留痕"、
  `test_emse_docstring_augment_analysis.py` 的"缺字段默认 None"→"键缺席不与 null 混同"），
  净增 **33 例**：collected 9655 → **9688**（全量实测）。除真路径不变量组读取**入库工件**外
  全部用 `tmp_path` 合成输入，缺工件即 `pytest.fail`（不许静默 skip）。
- **变异验证 18 处锚点逐处删除全部转红**（变红例数 2 / 1 / 1 / 1 / 1 / 2 / 2 / 2 / 1 / 2 /
  2 / 1 / 11 / 2 / 9 / 7 / 7 / 6），比对变异前后**收集数保持 86**、逐处打印变红用例名、
  按 sha256 断言字节还原（本树大量未提交，绝不用 `git checkout` 回滚）。
  **顺带登记一条脚本自身的教训**：c4 锚点第一版把 `continue` 插进原 `if` 块，留下孤儿缩进，
  导致整文件 `ImportError`、收集数 86→41——那不是"守卫变红"而是"锚点写坏"，
  只靠 collected-equality 这条前置检查才没被误记成锁；第二版改为单行归臂反转并加 `compile()`
  前置校验后，c4 用 7 例转红通过。
- **不得据本册引用的主张**：① "`experiments/` 层静默点已清零"——本轮处置完 AB-9 表里
  标"下一轮"的 3 行，但同表**刻意静默且已留痕**的 6 处仍按机制登记为不改；
  ② "站点 a 那行 AB-9 登记已全部处置"——该行原文列了**三项**机制，本轮 **0 项处置**：`(x or {})` 把 `null`/`[]`/`0`
  降成空对象、`GATES.json` 缺席时渲染成 `gates_all_pass: FAIL`（**缺失被当成不通过**，
  方向保守但仍是把缺席读成一个数）、宽 `except Exception: continue` 把一对种子从配对比较里
  静默摘掉。本轮真正处置的 profile 预设是**同一文件里的另一站点**，该行原文从未列过它，
  所以把 profile 预设记成本行的部分处置是**归因错位**，已在 AB-9 那一行就地撤销。三件收口后
  逐个实测均 0 实例：该目录 11 份 JSON 0 份读不动；3 份种子批次顶层均为对象、`results` 为
  非空对象且三臂全在场（`or {}` 不改变其中任何一个）；`GATES.json` 实为对象且 `all_pass=true`；
  原批次目录 glob 命中 10 份、解析成功 10 份、被 except 摘掉 0 份、三 seed 配对无缺席——
  故不改不影响任何入库读数；
  ③ "站点 c 的 AB-9 登记口径已收口"——该行原文指的是**非对象行仍计入分母**，本轮实测
  该形态盘上 0 实例（9086 文件里非对象行 0、零事件可读文本文件 0），**未处置、继续登记**；
  本轮处置的是同一站点上更严重的另一半（unknown 归臂 + 44 条作废记录无痕）。
  **该项已由 AB-12c 轮处置**（`docs/reviews/SITE_C_MAST_NONOBJECT_AB12C_2026-10-20.md`）；
  本轮"0 实例"的普查数同时被 AB-12c 查出是**测量工具漏扫**所致覆盖面低估——修正后为
  138 目录 / 8539 文件 / 125270 行，非对象行仍为 0。
  ④ "`mast_distribution_report.md` 可逐位复算"——见 §5，输入已增长，声明失效；
  ⑤ "重复 `task_id` 缩分母已修"——折叠发生在**共享 loader** `emse_docstring_anchor_analysis.load_arm_rows`
  里，本轮只在 augment 侧加了命名 WARN 与三数披露，没有改共享 loader（其爆炸半径覆盖 anchor
  分析侧多个调用方），该缺口继续登记。
  **该项已由 AB-12d 轮处置**（`docs/reviews/ARM_ROW_COLLAPSE_AB12D_2026-10-20.md`）。
  本行原文把定义处写错了：`load_arm_rows` **定义**在 `emse_df_spec_analysis.py:49`，
  `emse_docstring_anchor_analysis.py:49` 与 `emse_docstring_augment_analysis.py:50` 都只是
  `import`——所以"爆炸半径覆盖 anchor 侧多个调用方"这句是对的（三个分析共用一条 loader），
  但按本行原文去 anchor 文件里找不到那个函数。`emse_docstring_augment_analysis.py:99` 的文档串
  同样把定义处写成了 anchor，已随 AB-12d 一并更正。
- **本轮 `src/` 零改动（以改动面清单为证，不以覆盖率同值为证）**：改动面是 3 个 `experiments/`
  脚本 + 3 个测试文件 + 文档，`experiments/` 不在 `--cov=src` 口径内。收口实测核对：登记前一跑
  **9682 passed / 1 failed / 5 skipped**（collected 9688，170.11s 带 `--cov`，唯一失败 = 基线一致性
  守卫自身），刷新后的**收口确认跑实测 9683 passed / 5 skipped / 0 failed、169.63s、rc=0**（登记见
  `docs/PROJECT_STATUS_REGISTER.md` §1 与 `BASELINE.yaml`）；`coverage.xml` 复算 **18371/18896 行
  （97.2216%）、6606/7044 弧（93.7819%）**。**但"与前几轮逐位相同"不得当佐证用**：`make gates` 的
  `format` 门抓到本轮新增的 reason 字符串写成两段隐式拼接，`ruff format` 后对**同一条 `src/` 树**
  又连跑两次全量口径，得到 **18371 → 18369 → 18371 行 / 6606 → 6605 → 6606 弧**（171.14s、170.46s，
  两次均 9683 passed / 5 skipped / 0 failed、rc=0），逐行比对 term-missing 表唯一变动的是
  `src/utils/process_utils.py`（641-642 未命中），根因是 638-642 那条 `killpg(SIGKILL)` 失败后回退
  `proc.kill()` 的负载相关竞态分支没有确定性锁——详见 `docs/MEASUREMENT_INTEGRITY.md` §14。格式化还
  使 18 处变异锚点全部**重跑**（a5 锚点改指合并后的单行，逐处仍转红、收集数 86 保持、sha256 断言
  字节还原）。

## 7. 复算命令

```
.venv/bin/python -m pytest tests/test_experiments_absent_vs_zero_ab11.py \
    tests/test_ag_batch.py tests/test_emse_docstring_augment_analysis.py -q --no-cov
.venv/bin/python /tmp/ab11_mutate.py            # 变异验证（临时件，不入库）
make gates
```

关联登记：`docs/PROJECT_STATUS_REGISTER.md` §3.2 AB-11 行与 §4 AB-11 行、
`CHANGELOG.md` / `CHANGELOG.en.md` 同名节、`BASELINE.yaml` `tests` 节；
三处站点的上游登记与判据出处：`docs/reviews/EXPERIMENTS_JSON_DOMAIN_AB9_2026-10-20.md` §2
（行 43 / 44 / 47）与 `docs/reviews/ABSENT_VS_ZERO_AB10_2026-10-20.md` §5 ①；
教训入 `docs/MEASUREMENT_INTEGRITY.md` §13。
