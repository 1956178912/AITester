# AB-10：分析侧「缺席 / 读不动」不得报成「零命中 / 一致 / 未要求」（2026-10-20）

> 零 LLM、$0、全部改动堆在既有未提交树上。本轮处置 AB-9 普查 §2 里登记为"下一轮"的
> 5 处静默点中的 **2 处**（`emse_ult_gold_diagnosis.py:556` 与 `:697`，含与 `:697` 同形的
> `:1143` 一处），其余 **3 处按机制登记**；判据直接沿用 AB-9 的分析层口径，不新设。

## 1. 为什么是这一层、这一处

AB-9 把 `experiments/` 层 68 处 `json.loads` 按解析器返回域分类为 42 响亮崩溃 /
9 已 fail-closed / 5 崩溃被吞但留痕 / **12 静默**，并明确判据：**分析层宁可非零退出，
也不要一个看起来正常的错数字**。本轮从 12 处里挑出"错数字会被当成科学结论"的两处动手，
标准是 AB-9 §2 用的同一排序——数字是否正在被引用、错的形式是否影响结论方向。

挑中的两处都属于同一个更窄的缺陷族，比"静默丢行"更糟：**缺席被翻译成了一个正面的读数**。

- `:556`（`_load_json_array`）：上游数组工件读不出对象行时返回 `[]`，调用方把 `[]`
  同时当作"上游没有这一行"和"上游工件不可用"——于是 `official_tests` 退化成
  **本地归档 gold 的包装**，紧接着的一致性核验变成"拿本地 gold 和它自己比"。
- `:697`（`--supplement` 读取）：显式给了路径而文件不存在，`if sup_path.is_file()`
  让 `supplement` 保持 `None`，README 的 4d 节整段消失且没有任何痕迹；这与 AB-8 产品侧
  "配了但整份零生效、日志照写已加载 N 条"同形，只是发生在分析侧。

## 2. 实测读数（先读数，再定处置）

### 2.1 `_load_json_array` 的返回域（`tmp_path` 合成文件，函数级直调）

| 输入 | 处置前实测 | 处置后实测 |
| --- | --- | --- |
| `[{"code": "c1"}]` | `[{'code': 'c1'}]` | 同左（逐字不变） |
| `[]` | `[]`，无痕迹 | `[]`，无痕迹（真零行，与"读不动"不同形） |
| `"abc"` | **`[]`**（逐字符迭代后没有一个是 dict） | `TypeError：顶层不是列表（实测类型 str）` |
| `3` / `true` / `null` | `TypeError: 'int'/'bool'/'NoneType' object is not iterable` | `TypeError`（同一守卫，消息点名路径与类型） |
| `[1, "x", null, {"code": "keep"}]` | `[{'code': 'keep'}]`，**丢弃 3 行无痕迹** | 返回值同左，另向 stderr 打 `[WARN] …：3 行不是对象已跳过，仅使用余下 1 行` |
| `[1, 2, 3]` | `[]`，与空数组同形 | `[]` + `[WARN] …：3 行不是对象已跳过，仅使用余下 0 行`；经 `_load_upstream_array` 则 `ValueError：属读不动，不是零命中` |

### 2.2 「自己和自己比」不是推断，是实测

按 `main()` 里的原表达式（`:783` 一带）就地复算：把 `up_full` 置为 `None`、
`gold` 取盘上第一条真实任务的 5 条 gold 断言，则

```
official_tests = [f"def test_{j}():\n" + 缩进(gold[j]) ...]        # 本地 gold 的包装
body_full = sorted(_normalize_test_body(t) for t in official_tests)
body_lite = sorted(_normalize_test_body(t) for t in gold)
upstream_bodies_equal = bool(body_full) and body_full == body_lite   # 实测 True
```

**实测读数 `True`，且此时一份上游数据都没读到**——`_normalize_test_body` 把 `def` 行剥掉、
其余逐行 strip，包装与原文在这一步是同构的，所以该比对恒真。AB-9 §2 把它写成
"拿本地 gold 和自己比并报一致性"，本轮由复算确认，不是路径推断。

### 2.3 真数据实际走哪条分支（本轮的关键前置量）

盘上 `~/.cache/aitester/ult_repo/datasets/` 的两份上游数组实测
`ULT_Lite.jsonl` 顶层 `list` 长 200、`ULT.jsonl` 顶层 `list` 长 3909，`_load_json_array`
逐行 `isinstance(dict)` 后 **200 / 3909 全部保留（丢 0 行）**；`_load_project_tasks`
给出 71 条任务，按 `code` 对齐后 **71/71 命中 `ULT.jsonl:tests` 分支，0 条走包装分支**。
因此 §2.2 那条恒真路径**在盘上真工件上不会被走到**——这正是本轮可以改它而不动入库工件的前提，
也是它值得改的原因：它只在缓存缺失/形状坏掉时才出现，而那时它恰好产出最像结论的错读数。

## 3. 处置（四处，全部"静默 → 披露或 fail-closed"，没有一处把崩溃换成静默）

| 站点 | 处置 | 真路径影响 |
| --- | --- | --- |
| `_load_json_array` | 顶层非 `list` 抛 `TypeError`（点名路径与实测类型）；数组里非对象行**照旧跳过但向 stderr 报数**（丢弃数与余下数都写） | 实测丢 0 行 ⇒ 无新输出 |
| 新增 `_load_upstream_array` | 4 处上游读取（`main` 两处、`_assertion_level_split`、`_pick_examples`）改用它：文件缺失 ⇒ `FileNotFoundError`（"缺席不等于上游无该行"）；一个对象行都没有 ⇒ `ValueError`（"属读不动，不是零命中"）。口径对齐同文件 `_load_project_tasks` 既有的 `FileNotFoundError("批次工件缺失…")` **先例**，不是新设计 | 两份工件都在且非空 ⇒ 行为不变 |
| 新增 `_official_tests_for`（从 `main` 循环里提出的纯函数） | `up_full` 没有 `tests` 列表时返回 `(包装, "…test_list(wrapped)", **None**)`：一致性既不报 True（一致）也不报 False（不一致），而是"无法核验" | 真数据 0 条走该分支 ⇒ 入库 JSON 的 71 条 `upstream_bodies_equal` 全不变 |
| 新增 `_load_supplement`；`_render_section_4c/_4d`（从 `_write_readme` 提出） | 给了 `--supplement` 而文件不存在 ⇒ 抛错；文件在但顶层非对象 ⇒ 抛错；顶层是对象却无 `records` ⇒ stderr `[WARN]` 后按"无补充测量"继续（退出码不变）。README 侧：4c 工件不在输出目录、或 4d 读到记录但没有 C+ 变体时，**在原地写明"本节未渲染 = 工件缺席 / 这批记录不含该测量"**，不再静默省节 | 两份补充工件都在且可用 ⇒ 渲染逐字不变（见 §4） |

顺带如实登记一处**没改**的表述问题：包装分支的标签 `ULT_Lite.jsonl:test_list(wrapped)`
里的数据来源其实是本地归档 gold（`task_metadata.gold_tests`），`ULT_Lite` 只是这批 gold
的上游出处。改名在真路径上不产生任何字节变化（0 条任务走该分支），但它纯属措辞、
不影响任何读数，故本轮只在代码注释里写清，不动标签字符串。

## 4. 入库工件字节不变（这是硬约束，验过才算）

`experiments/results/emse_ult_gold_diagnosis_20261015/` 受 `SHA256SUMS.txt` 保护，
且本轮改动全在渲染与读取路径上，所以判据是**逐字节复现**：

```
cp experiments/results/emse_ult_gold_diagnosis_20261015/SUPPLEMENT_GENERATED_MUTK.json <tmp_out>/
PYTHONPATH=. .venv/bin/python experiments/emse_ult_gold_diagnosis.py \
    --from-json <tmp_copy>/ULT_GOLD_DIAGNOSIS.json --out <tmp_out>/REPORT.json \
    --supplement experiments/results/emse_ult_gold_diagnosis_20261015/SUPPLEMENT_CORRECTED_PRELUDE.json
cmp experiments/results/emse_ult_gold_diagnosis_20261015/README.md <tmp_out>/README.md
```

实测两次都为 `BYTE_IDENTICAL`：改动完成后一次、`ruff format` 之后再一次。
两条踩到的口径（都是先知道才能写对的）：

- 复现 README **必须同时提供 `--supplement` 并把 `SUPPLEMENT_GENERATED_MUTK.json` 放进输出目录**——
  第一轮只给 `--supplement` 时 4c 节整段缺失（21 行差异），补上文件后才逐字节对上。
  4c 节的开关是"该工件在不在 `out_dir`"，不是命令行参数。
- `--from-json` 会**就地重写**它读的那份 JSON，所以复算必须先把它复制出去（本轮全程只碰
  `/tmp`，入库目录 `git status` 干净、`SHA256SUMS.txt` 逐条校验 0 处不符）。

## 5. 验证层级与不得引用项

- **回归锁**：`tests/test_experiments_absent_vs_zero_ab10.py` **35 例**——返回域 10
  （含 4 种非列表顶层参数化）、上游缺席 4、自比 5（含"包装体归一后与本地 gold 逐字相同"
  这条恒真事实本身）、补充工件读取 8（含 5 种非对象顶层参数化）、节省略披露 6、
  入库真路径 2。全部用 `tmp_path` 合成输入，**不读 `~/.cache/aitester`**，
  所以 CI 与本机同口径、无新增 skip。
- **变异验证 10 处锚点逐处删除全部转红**（变红例数 5 / 2 / 1 / 1 / 2 / 1 / 5 / 3 / 1 / 1），
  脚本要求基线全绿、比对变异前后**收集数不变**（防空转）、逐处打印变红用例名、
  按 sha256 断言字节还原（本树大量未提交，绝不用 `git checkout` 回滚）。
- **不得据本册引用的主张**：① "`experiments/` 层 JSON 返回域已收口"——12 处静默点里
  AB-9 处置 1 处、本轮处置 2 处、刻意静默 6 处不改、**还剩 3 处登记**；
  **（AB-11 后续：那 3 处已全部处置，本册 §5 ① 的"还剩 3 处"自此失效；但 AB-11 对其中两行
  只各处置了原文所列机制的一件，`(x or {})` 降空对象、`GATES.json` 缺席报 `FAIL`、
  "非对象行仍计入分母"三项继续登记（实测均 0 实例），且刻意静默的 6 处一处未动。
  引用本册该句时应带此后缀。）**
  ② "上游工件缺失
  时本轮改造后的脚本一定会失败"——只核了 `_load_upstream_array` 的 4 个调用点，
  其余文件的上游读取不在本轮范围；③ "`official_tests_equal` 从未被误报"——真数据 0 条走
  包装分支，但这条结论来自本轮一次实测普查（71/71 命中上游），不是长期性质。
- **本轮 `src/` 零改动（已实测）**：改动面是 `experiments/emse_ult_gold_diagnosis.py` +
  1 个新测试文件 + 文档，`experiments/` 不在 `--cov=src` 口径内，故 `coverage.xml` 读数应与
  AB-8/AB-9 逐位相同。收口实测核对：登记前一跑 **9649 passed / 1 failed / 5 skipped**
  （collected 9655，168.76s 带 `--cov`，唯一失败 = 基线一致性守卫自身），刷新后的收口确认跑
  **9650 passed / 5 skipped / 0 failed，168.83s，rc=0**，其 `coverage.xml` 复算 **18371/18896 行
  （97.2216%）、6606/7044 弧（93.7819%）**，与 AB-8/AB-9 登记逐位相同。

## 6. 复算命令

```
.venv/bin/python -m pytest tests/test_experiments_absent_vs_zero_ab10.py -q --no-cov
.venv/bin/python /tmp/ab10_mutate.py            # 变异验证（临时件，不入库）
make gates
```

关联登记：`docs/PROJECT_STATUS_REGISTER.md` §3.2 AB-10 行与 §4 AB-10 行、
`CHANGELOG.md` / `CHANGELOG.en.md` 同名节、`BASELINE.yaml` `tests` 节；
上游普查与判据出处：`docs/reviews/EXPERIMENTS_JSON_DOMAIN_AB9_2026-10-20.md` §1–§2；
教训入 `docs/MEASUREMENT_INTEGRITY.md` §12。
