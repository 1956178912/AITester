# AB-12c：站点 c 的"可解析但不是对象"行不再充进有效分母（2026-10-20）

> 零 LLM、$0、全部改动堆在既有未提交树上。处置的是 AB-9 普查表行 44 原文登记、AB-11 §6③
> 明确"**未处置、继续登记**"的那一半：`experiments/mast_trace_analysis.py` 里
> `if isinstance(rec, dict)` 把可解析的非对象行**既不计数也不标损坏**。
> 判据仍是 AB-9/AB-10/AB-11 的分析层口径：**形状不合是一次读数，不是一次零命中**。

## 1. 先读数——包括测量工具自身的一次纠错

本轮第一个动作是只读普查，不改造。第一版探针（`/tmp/ab12c_nonobject_probe.py`）报
"扫描目录数=129 文件数=783 行总数=5964 非对象行=0"，据此就可以写下"0 实例"。
**但那个 0 是漏扫出来的**：探针写的是
`{p.parent for p in ROOT.glob("experiments/results/**/traces*") if p.is_dir()}`——
取的是 trace 目录的**父目录**，于是 `main_batch/traces`（单目录就 2007 个文件）一份都没被扫到。
第二版以目录本身为扫描根，并打印目录数与文件数自证覆盖面：

| 口径 | 第一版（漏扫） | 第二版（修正后） |
| --- | --- | --- |
| `traces*` 目录数 | 129（父目录） | 138 |
| `*.trace.jsonl` 文件数 | 783 | 8539 |
| 非空行数 | 5964 | 125270 |
| 可解析但非对象的行 | 0 | **0** |
| 整份都是非对象行的文件 | 未测 | **0** |
| 读不动的文件 | 0 | 0 |
| 坏行（JSONDecodeError） | 未计 | 5（走损坏通道，AB-11 已处置） |

默认目录 `main_batch/traces` 单独复核同口径：2007 个文件、19413 行、非对象行 0。
5 个坏行文件的行号与"坏行前已解析记录数"沿用 AB-11 §2.3 的登记，本轮未动。

**这条纠错本身是要登记的读数**：0 实例是"测量工具的产出"，工具坏了就会把"没看"报成"没有"。
`TestRealPathInvariants.test_repo_wide_non_object_census_is_zero_and_instrument_covered`
因此同时断言 `目录数 >= 138`、`文件数 >= 8539` 与 `非对象行 == 0`——覆盖面回落时先红，
不允许用漏扫的 0 顶替普查的 0。

## 2. 处置（三条通道各归各的，没有一处把崩溃换成静默）

| 机制 | 处置 | 真路径影响 |
| --- | --- | --- |
| 逐行非对象滤除无痕 | `parse_trace_file` 新增 `non_object_records`（行数）与 `non_object_shapes`（按类型名计数：list / str / int / float / bool / NoneType），坏行前的非对象行同样计数 | 0 实例 ⇒ 所有入库读数不变 |
| "整份形状不合"与"零事件"同形 | 新增 `non_object_only`（`damage is None` 且无对象记录且有非对象行）；**损坏优先**：同一份文件落损坏通道，不重复计形状不合 | 同上 |
| 形状不合的文件仍进 `files` 分母 | `analyze_traces` 为其单设 `non_object_only` 桶（按臂），**不再计入 `stats["files"]`**；全局新增 `non_object_only_files` / `files_with_non_object_lines` / `non_object_lines` / `non_object_shapes` / `non_object_files`（点名文件名） | 分母账变为 `files + damaged + non_object_only == total_files`，0 实例时与改前逐字段全等 |
| 报告只说"有效文件数 N" | `render_markdown` 仅在非对象行真的出现时插一条"非对象行留痕"披露行，并在该臂头行追加"非对象行独占 N 份不计入分母"；无新读数时两处文案与改前逐字相同 | 0 实例 ⇒ 报告逐字节不变 |

口径边界（本轮明确不变的部分）：**"能读、无事件"的空文件仍计入有效文件数**——AB-11 就写着
空文件不是 damaged，本轮只把"形状不合"挪出分母，不顺手缩"真的零事件"。这条由
`test_genuinely_empty_file_is_not_shape_only` 与 `test_ag_batch.py::test_empty_file_counted_with_zero_hits`
共同锁住（后者在 c3 锚点上转红，证明这条边界不是措辞承诺）。

## 3. 入库工件字节不变（硬约束，验过才算）

- 6 个入库 trace 目录（`main_batch/traces` + AB-11 的 5 个损坏目录）改前后 `analyze_traces`
  **旧字段逐字段全等**（把本轮新增键剔除后逐目录 `json.dumps(sort_keys=True)` 相等），
  新计数全为 0，各臂 `non_object_only` 合计全为 0；
- `--traces-dir experiments/results/main_batch/traces --output /tmp/…`（rc=0）改前与改后
  两次复算产物 **`cmp` 相同**；入库 `mast_distribution_report.md` 未被写过；
- `experiments/results/main_batch/SHA256SUMS` 逐条校验 **2040 条全部 OK、0 处不符**。

## 4. 验证层级

- **回归锁**：新文件 `tests/test_experiments_mast_nonobject_ab12.py` **32 例**
  （解析层 11 含 6 种非对象形状参数化、分母与归臂 8、渲染 3、真路径与全仓普查 10 含 5 目录参数化）。
  除真路径组读取**入库工件**外全部用 `tmp_path` 合成输入，缺工件即 `pytest.fail`（不静默 skip）；
  入库报告的"未重写"改按 `SHA256SUMS` 条目逐位比对，而不是只看有没有某个字符串。
- **变异验证 14 处锚点 + 1 处行为中性对照**（`/tmp/ab12c_mutate.py`，rc=0）：逐处删除的变红例数
  18 / 7 / 3 / 1 / 6 / 6 / 1 / 1 / 2 / 4 / 2 / 2 / 1 / 2，对照锚（只改 docstring 措辞）**0 红**；
  15 次运行的**收集数恒为 77**、每处先过 `compile()` 前置校验、逐处打印变红用例名、
  按 sha256 断言字节还原（源文件 `c10b9709fb627714…`，改前 `b130c77827f9ff18…`）。
- **两条本轮才出现的教训**（与"有红不等于有锁"同族，详见 `docs/MEASUREMENT_INTEGRITY.md` §15）：
  ① c4 锚点（撤销"损坏优先于形状不合"的判定）第一次跑出 **0 红**——不是守卫多余，
  而是我的测试输入里放了一条 `task_start`，`not records` 先为假，把被测守卫遮住了。
  换成"整份都是非对象行 + 一个坏行"后该锚点 1 红。**变异验证会反过来检测试的假阳性覆盖**。
  ② 首轮 7 处 `[MISS]` 全部是**预期红数订高了**（把真路径组也算进候选），逐处下调后每处仍 ≥1 红且点名；
  收集数与用例名都核对过，没有一处是"锚点写坏"冒充"守卫变红"。

## 5. 不得据本册引用的主张

1. **"MAST 报告的分母风险已消除"**——本轮在盘上**没有任何生效实例**（0 非对象行）。
   改造做到的是"下一次出现时会被看见并被计数"，不是"曾经有问题现已修好"；
2. **"全仓 trace 干净"**——普查面是 `experiments/results/**/traces*` 目录里的 `*.trace.jsonl`
   （138 目录 / 8539 文件），不是全部 JSONL；且该读数只覆盖形状与可读性，不覆盖语义正确性；
3. **"`mast_distribution_report.md` 可逐位复算"**——AB-11 §5 的陈旧声明**继续有效**，
   本轮未改写生成器里的"逐位复算"措辞（改它会让所有已落盘报告不可复算），
   入库快照仍是 963 文件时点、实跑 2007；
4. **"AB-9 行 44 已全量处置"**——该行登记的两半（损坏整份作废无痕 / 非对象行进分母）现均已处置，
   但同表刻意静默且已留痕的 6 处仍按原判据不改；AB-9 表行 43（站点 a）之外，
   站点 d（重复 `task_id` 缩分母）本册写作时未处置。
   **本册下一段更新**：站点 d 已由 AB-12d 轮处置（`ARM_ROW_COLLAPSE_AB12D_2026-10-20.md`）；
   本册原文把该 loader 的定义处写成 `emse_docstring_anchor_analysis.load_arm_rows`，实测定义在
   `emse_df_spec_analysis.py:49`，anchor 与 augment 两侧都只是 `import`。

## 6. 复算命令

```
.venv/bin/python /tmp/ab12c_nonobject_probe.py            # 只读普查（零 LLM）
.venv/bin/python -m pytest tests/test_experiments_mast_nonobject_ab12.py \
    tests/test_experiments_absent_vs_zero_ab11.py tests/test_ag_batch.py -q --no-cov
.venv/bin/python /tmp/ab12c_mutate.py                     # 变异验证（临时件，不入库）
cd experiments/results/main_batch && shasum -a 256 -c SHA256SUMS | grep -vc ': OK$'
```

关联登记：`docs/PROJECT_STATUS_REGISTER.md` §3.2 / §4 的 AB-12 行、
`CHANGELOG.md` / `CHANGELOG.en.md` 同名节、`docs/INDEX.md` 与 `docs/INDEX.en.md`；
上游判据出处：`docs/reviews/EXPERIMENTS_JSON_DOMAIN_AB9_2026-10-20.md` §2 行 44、
`docs/reviews/ABSENT_VS_ZERO_AB11_2026-10-20.md` §2.3 与 §6③。
