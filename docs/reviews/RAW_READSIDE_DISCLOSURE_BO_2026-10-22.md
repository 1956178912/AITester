# BO 轮：raw 落盘面的读侧把三种缺席折成实测——开关态、依赖图边数、定位命中率（2026-10-22，零 LLM，$0）

> 系列位置：BH→BI→BJ→BK→BL→BM→BN→**BO**（"读不懂 / 没测 ⇒ 沉默或判优"缺陷族）。
> **序数口径先说清**：BM 分册自述"第 5 面"、BN 分册自述"第 6 面"（BN 枚举"前五轮"时跳过了 BK），
> 而按字母序数 BH=1 起算本轮是第 **8** 个字母轮。此处只登记该存量漂移，**不回改历史分册**。
> 本轮闭合的是 BN §7.1 与 `MEASUREMENT_INTEGRITY` §58⑥ 按名登记的那一条：
> **`--save-state` 决定 raw 存不存在，而 raw 读侧的一切折叠都以它为唯一前提，这个前提本身不可复核**。
> 判据范围 = 都做（普查给出的 5 处 raw 读侧折叠站点 + 1 处开关态落盘）。
> 口径：判定值与判定方向不变，归档工件一个字节不改；本轮 `src/` 零改动（写入面普查 9 个文件，见 §3.6）。

---

## 1. 缺陷：读侧把"没落盘 / 键不在 / 值是 null / 件读坏了"折成"测过了，而且测到了 0"

BN 把检查通道的四值 `status` 落到了盘上，但落盘只是**前提**。本轮量的是消费这些工件的
`experiments/` 读侧五处站点，它们共同的写法是 `x = state.get(key) or []` + `len(x) == 0` ——
"读到空"与"没读到"在同一个 `if` 里，于是缺席一路走到判据与读数，最后印成一个数。

### 1.1 开关态本身不落盘：三种事后解释压成同一个观察

`--save-state` 默认 `False`（`experiments/run_benchmark.py:2586` / `:4068`），`run_main_batch.py`
从不传 ⇒ 默认批次根本不写 `raw/<task_id>/<baseline>.json`。于是"raw 不在"有三种成因：
①跑批时没开；②开了但 raw 没随归档留存；③开了且留存（本轮看不见）。实测（探针 A 段）：

| 观察面 | 读数 |
| --- | --- |
| 批次 JSON（含 provenance） | **246 份**里出现 `save_state` 类键 **0 份** |
| provenance 键面 | 15 个键（`git_sha` / `profile` / `seed` / `temperature` / `cache_namespace` …），**无开关态** |
| 归档键名里含 `raw`/`save` 字样 | 只有 `gold_tests_raw`、`mdo_raw`——都不是落盘开关 |
| raw 留存 | 磁盘 **34** 个 `raw/` 目录 vs 入库 **88** 份 raw 文件、只覆盖 **6** 个批次目录 |
| 忽略规则 | `.gitignore:172` = `experiments/results/**` |

⇒ "raw 是否随归档留存"是**逐批次**事实，既不在 summary 里，也不能由忽略规则推出。
事后既不能证明"当初没落盘"，也不能证明"落盘了但没归档"——这是开关态的沉默面，
不是"默认关"这个口径本身的问题（本轮**不改默认值**，见 §7.1）。

### 1.2 根因归因：三种缺席折成"实测 0 条依赖边"

`experiments/cross_file_root_cause._classify_root_cause` 的第 3 步改前写作
`deps = state.get("cross_file_deps") or []` → `len(deps) == 0` ⇒ `DEP_GRAPH_INCOMPLETE`。
件不可用、键不存在（批次早于该键进白名单）、值为 null（BN 起白名单恒写键、null=该环节从未记录）
三种缺席因此全部折成**"依赖图不完整"这一条根因**。复放读数（探针 B 段，真实批次两臂对照）：

- 5 个 cross_file 批次 × on/off = **9 臂**（1 臂零失败）、多文件失败 **29 例**；
- 改前 **14 例**的判定随"raw 目录给不给"翻转（同一行数据，带 raw 判 `LLM_CAPABILITY`/`DEP_INPUT_ABSENT`、不给判 `DEP_GRAPH_INCOMPLETE`）；
- `level1`（单文件）两臂恒 **0 例**翻转 ⇒ 折叠只在多文件腿上开；
- 键级普查（B2）：29 例里 `cross_file_deps` **键在场 14 / 键缺席 14 / 件缺席 1**；
- 逐件普查（5 臂 311 份 `aitester.json`）：键不存在 **216** / 非空列表 **95** / 值为 null **0** / 空列表 **0**
  ⇒ `DEP_INPUT_NULL` 这一腿在归档里 **0 实例**，它属于 BN 之后的新批次（白名单恒写键才会出现），按名登记不写成"已发生"。

### 1.3 分布读数：把"这一档没测"读成"没有这种根因"，且报告不自证覆盖度

改前 `analyze()` 只输出桶计数。读者看到分布里没有 `ROLLBACK_CONSERVATIVE`，只能读成"本批无此类根因"，
而真实原因是**该档的输入（`per_module_patches` / `applied_modules`）在 raw 工件里根本不存在**——按构造恒 0 例。
"恒 0"与"没测"在旧口径里同形，报告本身也不说这批到底用了多少 raw。

BN 之后又多一条陷阱：白名单**恒写**这些键 ⇒ "键在场"不再等于"记录过"。
所以自证面的可达性判据必须按**值非 null**，不能按键在场（变异锚点 R5/R6 锁的正是这两处）。

### 1.4 定位命中率：四条不可计算腿塌成 `0.0`，渲染成"定位正确率 0.0%"

`experiments/position_aware_ab._locate_accuracy` 改前把 raw 目录缺席、任务件缺席、`position_aware_focus`
键缺席、`details` 不可用四条腿一律返回 `0.0`，`_locate_text` 再印 `0.0%`。探针 C 段实测：
改前这四条腿与"实测定位全未命中"**数值同形 = True、文本同形 = True**——`0.0` 不是保守值，是用缺席造出来的读数。

另有一条更窄的折档：`focus is None` 且该行**确有**修复轮次或补丁时，改前会进分母并被计成一次实测未命中
（"定位环节没记录"压低命中率读数）。归档侧的形态普查（C2，8 臂 236 条 details）：
键在且为空 **156** / 键在且有内容 **80** / 键不存在 **0**——156 条空值行全部既无 `iterations` 也无 `patch`，
因此"未激活"口径下的跳过明细逐字节同形，新口径不动历史读数（C 段八臂现场复算与归档 21.43 / 0.0 / 0.0 / 0.0 /
25.0 / 0.0 / −1.0 / −1.0 逐位相同）。

### 1.5 失败对比报告：单臂缺席静默、损坏件抛穿整份报告、空产物 ≡ 无产物

`experiments/compare_failures.py` 改前只在**两臂都**读不到 raw 时写一行披露。D 段实测：

| 现场 | 改前 | 改后 |
| --- | --- | --- |
| 单臂（aitester 侧）缺席 | 报告里 `环节级工件不可用` **False**、`环节级产物缺失` **False**（静默） | `环节级工件不可用=True`，且点名是哪臂 |
| 两臂皆缺席 | 仅一行 | 保留该行 + 增"缺席形态"逐臂不同句 |
| 损坏 JSON | `json.JSONDecodeError` 抛穿整份报告 | `artifact=None`、`status=unreadable`，报告继续并披露 |
| 空产物 `{}` | 与"件不存在"同一句 | 渲染 `**aitester 环节产物**` 块（空 ≠ 缺席） |

### 1.6 A/B 脚本自己教的命令会把折叠再走一遍

`cross_file_ab.py` 跑完打印的根因分析提示不带 `--raw-dir`，而该臂跑批时 `save_state=True`、
raw 就在 `on_dir/raw` 下 ⇒ **照抄一次提示就把 29 例失败里的 14 例折成 `DEP_GRAPH_INCOMPLETE`**。
提示文本本身成了折叠的入口（探针 B 段的"不带 raw"臂就是这个照抄现场）。

---

## 2. 处置：只补披露与分档，判定方向一处不动

| 站点 | 处置 | 判据是否改变 |
| --- | --- | --- |
| `run_benchmark` provenance | +1 键 `"save_state": bool(save_state)`（严格布尔，`experiments/run_benchmark.py:4697`）；只对新批次生效 | 否 |
| `cross_file_root_cause._load_state` | 返回 `(state, status)`，词表 `ok` / `no_raw_dir` / `file_absent` / `unreadable`；顶层非 dict 记 `unreadable`（`:102`） | 否 |
| `_classify_root_cause` | 三条缺席腿分档 `RAW_UNAVAILABLE` / `DEP_INPUT_ABSENT` / `DEP_INPUT_NULL`，且排在结构档之前（`:126`）；`dep_edges=None` 不再印 `len([])` | 否（只换归因名，不新增拒绝） |
| `analyze()` | 自证面 `raw_coverage` / `rule_evidence` / `unreachable_rules`；可达性按**值非 null**判（`:207`） | 否 |
| `position_aware_ab` | 新增 `_locate_stats`（`:153`）：分母 / 命中 / 逐原因跳过 + `grade`；`_locate_accuracy` 只透传 `grade`（`:267`）；`_GRADE_TEXT` 给九种不可计算档各一句（`:138`） | 否（`-1.0` 数值档是既有的"不可计算"，本轮由 grade 细分语义） |
| `compare_failures` | `load_state_artifact_status`（`:93`）不抛穿 + `_ABSENCE_TEXT` 逐形态不同句 + 报告头证据面 + 单臂缺席披露 | 否 |
| `cross_file_ab` | 后续提示命令补 `--raw-dir {on_dir}/raw`（`:275`） | 否（仅提示文本） |
| `tests/` | 净增 **70 例** + 按新口径改写既有 2 例（见 §4） | — |
| 门禁 | **本轮未新增门禁**：BN 的 `check_status_persistence.py` 管"声明面 ⊆ 落盘面"，读侧折叠由测试锁覆盖 | — |

缺席**只做披露，不做归因、不做拒绝**：`RAW_UNAVAILABLE` 不判任务失败，`grade != measured` 不产生断言，
`unreadable` 不抛穿。把"没测"翻成"有问题"是与折叠同样严重的错误。

---

## 3. 测量（全部实测；Python 3.14.6，零 LLM）

复算入口 `scripts/tools/bo_raw_readside_fold_probe.py`（只读；A/B/B2/C/C2/D 六段），改前改后各跑一次。

### 3.1 A 段：开关态与 raw 留存 ⇒ 见 §1.1 表（246 / 0 份、provenance 15 键、34 目录 vs 88 文件 / 6 目录）。

### 3.2 B / B2 段：根因折叠复放 ⇒ 9 臂 29 失败；**改后 18 例翻转**（改前 14），level1 两臂 0。
两口径的差要说清：改前有 4 例"件在但键不存在"的行，在带 raw / 不带 raw 两臂下**同折**成
`DEP_GRAPH_INCOMPLETE`，因此翻转不出来；本轮分档后这 4 例在带 raw 臂落 `DEP_INPUT_ABSENT`，
于是同一臂集翻转数 14 → 18（多出的正是那 4 例键级缺席）。另有 3 例 `level3` 键缺席行先落
`EMPTY_LLM_PATCH`，不经本档。键级普查 = 键在场 14 / 键缺席 14 / 件缺席 1；逐件普查 = 216 / 95 / 0 / 0。

### 3.3 自证面读数：样例臂 `by_status={'ok': 4}`，零证据档三个 =
`DEP_GRAPH_INCOMPLETE` / `ROLLBACK_CONSERVATIVE` / `TOPOLOGICAL_ORDER`，后两档由输入构造决定、报告直接点名。

### 3.4 C / C2 段：定位 ⇒ 八臂现场复算与归档**逐位相同**；四腿数值同形 True→**False**、文本同形 True→**False**；
236 details 形态 156（键在值为空）/ 80（有内容）/ 0（键不存在）。

### 3.5 D 段：`compare_failures` ⇒ 见 §1.5 表（四现场改前改后各一读数）。

### 3.6 全量回归、覆盖率与写入面

- **预登记跑**（`make test-cov`，含 `--cov`，xdist `-n 4 --dist loadfile`）：collected **11865** →
  **11859 passed / 1 failed / 5 skipped**、47 warnings、**198.68s**、rc=2，墙钟 **200s**
  （`date +%s` 成对采集 1792646884→1792647084）。唯一红 = 基线数对账守卫（`BASELINE.yaml` 当时仍写 11790，
  实收 11865 − 声明 = **75 > 6** 容差），刷新 BASELINE 后消失。
- 同轮的**不带 `--cov`** 跑（先于预登记跑执行）：collected **11865**、11859 / 1 / 5、29 warnings、195.26s、
  墙钟 197s（1792646642→1792646839）。两跑都不带 `rc=0`（守卫仍红），全绿读数见刷新后确认跑（§9）。
- 覆盖率：`coverage.xml`（mtime 1792647082 = 预登记跑工件）root **19393/19904 行 = 97.4327%**、
  **7105/7532 弧 = 94.3309%**，未覆盖 **511** 行、缺弧 **427**，与 BN/BM 登记逐位相同。
  ⚠️ 相同读数**不证明** `src/` 零改动——该主张的依据是下一条。
- 写入面普查：以 `st_mtime > 1792642989`（BN 链终跑之后的干净时刻）扫全仓 `.py`/`.md`/`.yaml`/`.yml`，
  命中 **9** 个文件 = `experiments/{compare_failures,cross_file_ab,cross_file_root_cause,position_aware_ab,run_benchmark}.py`
  + `scripts/tools/bo_{mutation_verify,raw_readside_fold_probe}.py` + `tests/test_bo_raw_readside_disclosure.py`
  + `tests/test_experiments_ab_scaffolds.py`；**`src/` 与 `config.py` 命中 0**。
  阈值本身踩过一次（初值取 BN 终跑结束时刻，把 BN 的 CHANGELOG 写入扫进本轮），见 §6.4。

---

## 4. 回归锁（`tests/test_bo_raw_readside_disclosure.py`，70 例；逐类计数取自 `--collect-only` 实测）

| 类 | 例数 | 断言的是什么 |
| --- | --- | --- |
| `TestSwitchStateProvenance` | 6 | `save_state` 入 provenance：默认档离线端到端跑批落 `false`（内存 + 磁盘两份工件）、ON 档落 `true`、非布尔入参被强转（`1`→`True` / `""`→`False` / `None`→`False`，参数化 3 例）、summary 顶层键面不因此漂移 |
| `TestStateReaderStatuses` | 5 | `_load_state` 四值词表逐值（`no_raw_dir` / `file_absent` / `unreadable` / `ok`）；顶层非 dict ⇒ `unreadable`；坏件不抛 |
| `TestRootCauseGrading` | 10 | 件不可用是披露不是归因；键缺席 ≠ 件缺席；键在值为 null 自成一腿；真记录过的空图 / 不完整图仍归因；完整图才进能力档；单文件任务不入结构档；结果行各腿优先于结构档（参数化） |
| `TestAnalyzeSelfCertification` | 7 | 无 raw 时不宣称覆盖度；键在值为 null 记「零证据」；真边才使该档可达；`ROLLBACK_CONSERVATIVE`/`TOPOLOGICAL_ORDER` 按构造零证据且该主张锚到 raw 白名单；多状态分开计数；`main()` 未给 `--raw-dir` 时告警 |
| `TestLocateGrades` | 17 | 十档词表（`measured` + 九种不可计算）两两不同文；null 腿与键缺席腿不互并；`_repaired` 双证据（轮次**或**补丁）；未修复行的 null 仍留既有「未激活」桶；实测未命中/命中才是测量；兼容层只回数值且 docstring 的档数与词表一致 |
| `TestLocateRendering` | 3 | 渲染文本点名不可计算原因；`measured` 才印百分数 |
| `TestArchivedReadingsDoNotDrift` | 4 | 八臂现场复算与归档逐位相同（历史读数零影响） |
| `TestArtifactStatusReader` | 7 | `load_state_artifact_status` 词表（参数化）；损坏件 `(None, "unreadable")` 不抛；旧包装函数在可读件上仍返回原字典 |
| `TestReportDisclosure` | 7 | 报告头先说证据面；单臂缺席逐臂点名；两臂缺席保留原句并加缺席形态行；「件坏了」与「件没了」不同句；空产物 ≠ 件不存在（两臂各一例）；批量损坏不掀报告 |
| `TestCrossFileAbCommandWiring` | 2 | 后续提示命令带 `--raw-dir`；根因脚本在未给 `--raw-dir` 时自我声明「不做依赖图归因」（源码文本锁） |
| `TestNoSilentCrashOnRealArchives` | 2 | 真实归档批量喂入不抛穿；`OSError` 归 `unreadable` |

既有断言只按新口径改写两处、**用例数不变**（`tests/test_experiments_ab_scaffolds.py`）：
`test_position_aware_ab_locate_accuracy_no_raw_dir` 与 `..._details_not_list` 原断言"保守 `0.0`"，
锁的正是本轮收口的伪测量；改为 `-1.0` + `grade` 点名，并在 docstring 写明 0.0 是"用缺席造读数"。

---

## 5. 变异验证（`scripts/tools/bo_mutation_verify.py`：23 锚点 + 1 中性对照）

基线先全绿（rc=0、collected=70），逐锚点改写 → `compile()` → 采集面核对 → 跑受影响面 → `finally` 按 sha256 还原。
红数为该锚点块里 `FAILED tests/…` 行的实测计数（最大 6，未触及 12 行尾部截断）。

| 组 | 锚点 → 红数 |
| --- | --- |
| S 开关态 | S1 删 provenance 键 → 6；S2 去掉 `bool()` 强转 → 3 |
| R 根因 | R1 件缺席折回 `DEP_GRAPH_INCOMPLETE` → 4；R2 键缺席折回 → 2；R3 null 折回 → 2；R4 `dep_edges` 印 0 → 3；R5 `recorded` 按键在场计数 → 1；R6 `reachable` 读键在场 → 1；R7 顶层非 dict 冒充 ok → 6 |
| P 定位 | P1 null focus 进分母 → 5；P2 键缺席腿并入 null 腿 → 4；P3 `_repaired` 丢掉补丁证据 → 1；P4 零分母优先级颠倒 → 2；P5 null 档文本删除 → 2 |
| C 对比报告 | C1/C2 单臂披露删除 → 各 1；C3/C4 真值折叠（`is not None`→真值）→ 各 1；C5 报告头证据面 → 1；C6 缺席形态行 → 4；C7 损坏件抛穿 → 5；C8 两种缺席共用一句 → 2 |
| W 接线 | W1 提示命令摘掉 `--raw-dir` → 1 |
| 对照 | M-control 只改注释措辞 → **0 红（SURVIVED，要求 0 红）** |

复跑读数：**击杀 23 / 23，采集面逐锚点恒 collected=70，中性对照 0 红，`# mutation:` 残留 0，墙钟 117s**
（`date +%s` 成对采集 1792647336→1792647453，rc=0）。

---

## 6. 踩坑与自纠（本轮实测发生的）

1. **整串搜 `"0.0%"` 被 `"100.0%"` 子串命中**——渲染层锁初版在报告全文里搜 `"0.0%"` 判"未命中档已印出"，
   ON 臂的 `100.0%` 让断言恒真。改成**逐行判**（`on_line.endswith(": 100.0%")`、OFF 行不含 `%`）。锁缺陷，不是实现缺陷。
2. **不可击杀的锚点要先补锁再跑**——`P5`（删 `_GRADE_TEXT["focus_not_recorded"]`）第一轮 SURVIVED：
   渲染层用 `.get(grade, …)` 兜底，删条目仍渲染出唯一文本。补「措辞点名 null + 九档两两不同」两条锁后转红。
   判据：**锚点可击杀性是锁的属性，跑验证器之前先证明"改坏了会红"**。
3. **变异锚点非唯一**——`return None, "unreadable"` 在 `compare_failures` 里命中 2 次（两臂同函数），
   预计数发现后改成两行锚点（把 `isinstance` 行一起带上）。本轮因此 **0 次 `ANCHOR-ERROR`**：
   与 BN §6.2 同族教训，这次是**事前计数**而不是事后修。
4. **mtime 普查阈值取错**——初值取 BN `make gates` 终跑的结束时刻，秒级过冲把 BN 回填的 CHANGELOG/README
   写入扫进"本轮写入面"，得出 12 文件含历史轮文本。换成 BN 终跑之后一个明确时刻重跑，得 9 文件、`src/` 0 命中。
5. **`ruff format` 咬 Markdown 与 docstring 起手引号**——新测试里一段 docstring 以引号开头
   （`""""null = 没记录"…"""`）被格式检查拒绝，改写措辞后 `989 files already formatted`。
6. **重定向到文件 = 块缓冲**——把变异 harness 输出重定向到日志时，运行中 `wc -c` 恒 0，
   只在进程退出时一次性落盘（BJ 的管道事故同族，这次是文件重定向）。判据：长 harness 的中间进度不能靠
   `wc -c` 判断，只能等退出码；因此**不要在 harness 运行期间编辑它正在 sha256 核对的文件**。

---

## 7. 边界与未收口部分（按名登记，不写成"已排除"）

1. **`save_state` 默认仍为 `False`**（`:2586` / `:4068`），`run_main_batch.py` 从不传 ⇒ 默认批次继续只有
   结果行一个可复核面。本轮登记的是**开关态**，不是把开关打开——按口径不做，不是遗漏（BN §58⑥）。
2. **历史批次不回填**：246 份批次 JSON 里 `save_state` 仍 0 出现；"当初开没开"对历史批次永久不可复核。
3. **provenance 只证明开关态，不证明留存**：raw 是否随归档留存仍是逐批次事实（34 目录 vs 88 入库文件 / 6 目录）。
4. **`-1.0` 沿用既有数值档**，没有新增取值域；`grade` 只在渲染与 `_locate_stats` 里出现，
   既有消费方（表格、JSON）拿到的仍是同一个数——历史读数因此逐位不变（§3.4 实测）。
5. **`DEP_INPUT_NULL` 归档 0 实例**（216 键不存在 / 95 非空列表 / 0 null / 0 空列表）：该腿为 BN 之后的
   新批次而准备，本轮不主张它在历史里发生过。
6. **B 段 18 例翻转只在"带 raw vs 不带 raw"两臂复放口径下成立**，历史批次的根因报告文本未重写。
7. **本轮未新增门禁**：读侧折叠靠 70 例锁覆盖；若后续要把"缺席必须分档"变成棘轮，需要一个新的
   声明面（哪些 key 的缺席必须点名），当前没有可机读的声明源。
8. **BK→BN 候选池剩余项本轮未做**（仍按名登记）：`cross_analysis._contamination_cross_analysis` 的
   `if not level: continue`（把缺席折进"未观测"）与 `statistical_analysis` 的 `unknown` 桶口径不一致；
   `EXEMPT` 额度里剩余 20 处 `ast.parse` 站点与 `experiments/`+`scripts/` 的报告面；`outcome_sink=None` 的调用方；
   额度里"collapse shape"仍是文本而非机检；D/D2 类普查口径缺 BL 之前的历史读数，其差值不可减。

---

## 8. 复算命令（零 LLM、零写入、可逐条重跑）

```bash
# 1) 本轮 70 例新锁（先看 collected=70，再看 rc）
.venv/bin/python -m pytest tests/test_bo_raw_readside_disclosure.py -q

# 2) 被口径改写的既有两条（用例数不变）
.venv/bin/python -m pytest tests/test_experiments_ab_scaffolds.py -q

# 3) 六段只读探针（A 开关态 / B+B2 根因折叠 / C+C2 定位 / D 对比报告）
.venv/bin/python scripts/tools/bo_raw_readside_fold_probe.py

# 4) 变异验证：23 锚点 + 1 中性对照（会临时改写 experiments/*.py，finally 按 sha256 还原）
#    中止过就必须扫残留，并复跑 §1 的 70 例：
.venv/bin/python scripts/tools/bo_mutation_verify.py
grep -rn "# mutation:" experiments/ scripts/ || echo "残留 0"

# 5) 写入面普查（只读；阈值必须是上一轮链终跑之后的明确时刻）
.venv/bin/python - <<'PY'
import pathlib
CUT = 1792642989
hits = [str(p) for p in pathlib.Path(".").rglob("*")
        if p.is_file() and p.suffix in (".py", ".md", ".yaml", ".yml")
        and not {".venv", ".git", "__pycache__"} & set(p.parts) and p.stat().st_mtime > CUT]
print(len(hits), *sorted(hits), sep="\n")
PY

# 6) 文档锁子集 + 门禁链（最后、单独跑，不接管道）
.venv/bin/python -m pytest -q tests/test_markdown_table_integrity.py tests/test_ao_batch.py
make gates
```

---

## 9. 收口批注

**刷新后确认跑（登记 `BASELINE.yaml` 与双语文档之后、门禁链之前，单独执行）**：`make test`（xdist `-n 4 --dist
loadfile`、**不带 `--cov`**）→ collected **11865** 面 **11860 passed / 5 skipped / 0 failed**，pytest 自计 **197.69s**，
**rc=0**、**36 warnings**；墙钟 **199s**（`date +%s` 成对采集 `start=1792647821` → `end=1792648020`）。与预登记跑
（11859 passed / 1 failed / 5 skipped、rc=2）同一采集面，唯一红 = 基线数对账守卫，随 `BASELINE.yaml` 刷新消失；
本轮净增 70 例 + 2 例口径改写（用例数不变）已全部落在绿侧。36 条告警按展示条目可拆尽：**30** 条来自
`test_spec_expr_property`（hypothesis 生成的 `SyntaxWarning`：一条聚合 29 + 一条散项）、**5** 条来自同一
`.venv/…/chromadb/telemetry/opentelemetry/__init__.py:128`（`asyncio.iscoroutinefunction` 弃用）、**1** 条来自
`test_branch_coverage_fill`（U10 的 `entry_ocurrence_stat` 旧名，v0.8.0 移除档）；聚合展示 **8** 条。

**首跑（回填前、单独执行、不接管道）**：`rc=0`，墙钟 **207s**（`date +%s` 成对采集 `start=1792648363` →
`end=1792648570`）。链组成**实测**：**19 步命令 / 17 个 make 目标**（`gates` 的 prerequisites 数出 17，日志里被 make
回显的命令行经精确前缀匹配数出 19，两条独立计数）——与 BN 逐字相同，因为本轮**未新增门禁**。

链内 pytest（`-n 4 --dist loadfile`、不带 `--cov`）：`4 workers [11865 items]` → **11860 passed / 5 skipped / 0 failed
in 200.83s**，**40 warnings**。采集面与确认跑（11865）同一、判绿方向同一。两跑告警可逐条对上：非 hypothesis 部分
两边都是 **6** 条（同一 `chromadb/…/__init__.py:128` 5 条 + `test_branch_coverage_fill` 的 `entry_ocurrence_stat`
弃用别名 1 条），差额 **40 − 36 = 4** 全部落在 `test_spec_expr_property` 的 hypothesis `SyntaxWarning` 聚合组
（确认跑 29 + 1 条散项 = **30** ↔ 首跑单条聚合 **34**）；聚合展示条目数 8 ↔ 7 的差即该组在首跑被并成一条。

链尾分步读数（首跑）：

| 步骤 | 读数 |
| --- | --- |
| `ruff check .` | All checks passed! |
| `ruff format --check .` | **990 files already formatted**（BN 链内 986，+4 = 本轮新增 2 个 `scripts/tools/bo_*` + 1 份测试锁 + 1 份分册，逐文件可点） |
| `mypy src/ config.py` | **Success: no issues found in 137 source files** |
| 双语配对 / 文档链接 | 0 警告 0 失败 / **183** 份文件、**882** 条链接（内部 873 / 外链 9）、0 错误 0 警告；BN 为 182 / 869，差值未逐项拆解归因 |
| 环境开关 / 状态契约 / env-snapshot | 253 唯一 253 已登记 / 136 文件无未声明键 / 84 开关全覆、缺失 0（快照 115 键、其中 31 键不在扫描面 = 信息项） |
| 指纹 / 工具版本 / JSON 调用点 | 无结果 JSON 可验（近期无新批次，S29 只要求新批次已锁定）/ mypy 1.15.0、ruff 0.16.3 一致 OK / 口径 A `json_mode=True` 调用点 **7** 处（期望 7） |
| 严格 JSON | 工件 **7274** 份 = 严格 7272 + 登记豁免 2 + 违规 0；源码 304 份写入点违规 0 |
| 报告→工件对账 | 1 份文档 × 3 臂 × 11 列 不一致 0 项；T-10 严格 29 行 / 25 可测、宽松 62 / 55；登记册覆盖率对账与 `coverage.xml` 相符（±0.20pp） |
| 零断言 | 扫描 **459** 个测试文件，0 例（BN 458，+1 = 本轮测试锁文件） |
| `ast-guards` | 136 文件 / 78 站点 / 未覆盖 20 / 违规 0 / 豁免命中 20 / EXEMPT 19（与 BK 轮起逐位相同——BO 未在 `src/` 动守卫面） |
| `status-persistence` | 声明 **10** 个通道，落盘面 **3** 处全覆盖（BN 的门，本轮读侧折叠不进此门） |

**终跑（回填首跑读数后、单独执行、不接管道）**：`rc=0`，墙钟 **206s**（`date +%s` 成对采集 `start=1792648723` →
`end=1792648929`）；同为 **19 步命令 / 17 个 make 目标**；链内 `4 workers [11865 items]` → **11860 passed / 5 skipped /
0 failed in 200.55s**、**29 warnings**。

**两跑对账**：滤去 xdist 逐例进度行后 `diff` 只剩 **4 行（2 对）**——`test_spec_expr_property.py` 的 hypothesis 聚合组
（**34** ↔ **23**）与 pytest 自身汇总计时行（`40 warnings in 200.83s` ↔ `29 warnings in 200.55s`）；链尾 19 步分步读数
**逐字节相同**，即回填文本既没把任何门禁推到红，也没让任何读数移动。三次全量跑（确认 36 / 首跑 40 / 终跑 29）里
非 hypothesis 部分恒为 **6** 条（同一 `chromadb/…__init__.py:128` 5 条 + `entry_ocurrence_stat` 弃用别名 1 条），
差额全部由 hypothesis 生成的 `invalid decimal literal` 组承担（30 / 34 / 23）——这条等式是三次现值相减核对出来的，
不是把差值推给"抖动"。

**未跑第三链**：终跑之后只回填门禁读数（本手册、`BASELINE.yaml` 的 `local_gates_target` 行、登记册 §1 门禁总数行），
最终树与终跑之间的差异面仅是这些文本，不含 `src/` / `tests/` / `scripts/` / `experiments/` 一行。
