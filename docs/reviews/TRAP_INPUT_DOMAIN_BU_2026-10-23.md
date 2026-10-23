# BU 轮：Self-Repair Trap 判定核的输入可达域从未披露（零 LLM，$0）

登记日 2026-10-23；实测自 2026-10-22 23:32 起、跨零点于 2026-10-23 00:5x 完成——下面每个读数都带自己的时刻与口径。

## 1. 发现

`self_repair_trap_suspected` / `self_repair_trap_signals` 由**批次 XIV**（`docs/adr/0028-fl-constraint-gate-self-repair-trap.md`）
写入结果行。判定核是 `src/tools/self_repair_trap.py:81 detect_self_repair_trap`，三个信号各有一个
**最少点数门槛**：

| 信号 | 判据（源码位置） | 门槛 |
|---|---|---|
| `assert_count_declining` | `self_repair_trap.py:104`：`len(counts) >= 3` 且末两点连续下降 | ≥ **3** 个可解析断言计数点 |
| `assertion_collapse` | `self_repair_trap.py:106`：`len(counts) >= 2` 且末点为 0、存在前值 > 0 | ≥ **2** 个可解析点 |
| `mutation_score_declining` | `self_repair_trap.py:113`：`len(scores) >= 2` 且末点 < 首点 | ≥ **2** 个非 `None` 变异分数 |

归档实测（`experiments/results/`：257 份批次文件 / 11197 条结果行）：

| 事实 | 数值 |
|---|---|
| 带判定键的行 | **5935**（其余 **5262** 行早于批次 XIV，键缺席） |
| 判定值分布 | `False` × **5935**（无一例外）；`self_repair_trap_signals` 恒 `[]` |
| `oracle_quality_history` 键 | 在场 5935 / 缺失 **0** / 值非列表 **12**（12 行全为 `None`，来自 `benchmark_synthetic_20261009_191716.json`） |
| 历史长度分布 | `len=1` **3200** 行、`len=2` **2723** 行（3200 + 2723 + 12 = 5935） |
| 四档输入供给 | 未记录 **5262** / 形状不符 **12** / 欠最少点数 **3200** / 达最少点数 **2723** |
| 三信号输入可达域 | declining **0** 行 / collapse **2723** 行 / score **0** 行 |
| 域内结果 | collapse 域内可开火 **0**、判干净 **2723**；score 域内 **0** |
| 非 `None` 变异分数点数 | 0 点 **5692** 行（含 12 行形状不符，其分数序列为空）/ 1 点 **243** 行 ⇒ 没有任何一行给出 2 个分数 |
| 域外下降证据 | **531** 行历史确有连续下降，但点数 < 3 ⇒ 结构上进不了 declining 门 |
| 同进程重跑对账 | 判定不一致 **0**、信号不一致 **0**、重跑异常 **0**、读不懂 **0**（`reconciled=True`） |
| 两键的读端（改前） | `suspected` row_read 4（报告面 2）/ `signals` row_read 3（报告面 2）；state_read **0**；write 2 |
| 只写不读键池（§61① 读法口径） | 改前 **13** 键 / 76488 行 → 本两键接入读端后 **11** 键 / 64618 行（64618 + 2 × 5935 = 76488 ✓） |

两处问题，同一族（判据看不见输入 ⇒ 报告面同形）：

1. **门槛从不披露，于是三种事实共用一个读数。** 报告面上「0 例怀疑」同时兼容：
   5935 行里有 **3200** 行只有 1 个点、压根进不了任何门；**2723** 行进得了 collapse 门且确实判干净；
   而 declining 与 score 两个信号**在整个归档里从没拿到过输入**（各 0 行）。分档不写出来，
   读者无法区分「判定核说没有」与「判定核没被问」。531 行是第三种情形：**证据存在、判据看不见**。
2. **两键写了没人读。** 自批次 XIV 起 5935 行落盘，`experiments/analyze_results.py` 的报告面从没读过它们。

第 1 条不是"判定核算错"：把判定核在同一进程重跑在归档历史上、与行内已写值逐值对照，
**0 处不一致**。所以本轮**不动判定核、不动任何行的值与方向**，只把输入供给接上读端。

## 2. 处置

**单一事实源**：新增 `experiments/_trap_input_domain.py`

- 键名常量 `TRAP_VERDICT_KEY` / `TRAP_SIGNALS_KEY` / `TRAP_HISTORY_KEY`（:19-21）；
- `SIGNAL_MIN_POINTS`（:26：declining 3 / collapse 2 / score 2）与 `GLOBAL_MIN_POINTS`（:39，取 `min`）——
  报告面的门槛文案一律读常量，不写死数字；
- 四档 `BUCKET_NOT_RECORDED` / `BUCKET_MALFORMED` / `BUCKET_BELOW_FLOOR` / `BUCKET_FLOOR_REACHED`（:33-36）；
- 取数助手 `assert_counts`（:48）/ `mutation_scores`（:56）与判定核**逐字同式**（`parse_ok` 才计点、
  `or 0` 折空、`bool` 不当变异分数）；另有 `signal_domains`（:66）、`input_bucket`（:77）、
  `two_point_decline_outside_domain`（:89）。

**读端**：`statistical_analysis.self_repair_trap_domain_stats(rows)`（:1520）+
`self_repair_trap_domain_summary(data)`（:1635）——四档计数、三域可达计数、域内可开火 / 判干净、
域外两点下降、同进程重跑对账（不一致行点名，**封顶单点在返回处**）、`reconciled` 声明。

**报告面**：`analyze_results.py` :112 以别名 `_trap_domain` 导入，:223 落
`per_baseline.self_repair_trap_domain`，:1166-1251 新增章节
「Self-Repair Trap 判定核的输入可达域（BU：`self_repair_trap_*` 的读侧）」——13 列表 + 每臂行 + `**合计**` 行、
沉默臂注（整臂两键都没落盘时点名）、空域注（declining 域为 0 时说明没有任何一行给出 ≥3 点）、
对账异常注（重跑判定核抛错时单列，不折成「一致」）、两条口径脚注
（`未记录` = 键缺席、早于批次 XIV；`域外下降` = 证据存在但点数低于门槛）。
**不进入任何判定，不改 passed / repair / 分母，也不给论文数字提供新出口。**

**棘轮**：BQ 的读者数棘轮键集新增 `self_repair_trap_domain`（只增不删）。

## 3. 验证

- 新增 **79 例锁**（`tests/test_trap_input_domain_bu.py`，逐类取自 `--collect-only` 实测）：
  `TestInputBucket` 16 / `TestJudgeParity` 14 / `TestSignalDomains` 7 / `TestTwoPointDeclineOutsideDomain` 7 /
  `TestDomainStats` 12 / `TestThresholdSourceLock` 5 / `TestReportSurface` 14 / `TestPinnedBatches` 4。
  含判定核取数同式对照（同一历史分别喂判定核与分档助手）、门槛常量与判定核字面量的 AST 结构锁、
  三域可达逐档参数化、报告 13 列表格逐格期望 + 单元格数一致性锁、三个具名冻结批次钉档。
- **变异 61 锚点全红 + 1 中性对照 0 红**（`scripts/tools/bu_mutation_verify.py`，630 行）：
  受影响面 8 个文件，逐文件 collected 79 + 65 + 40 + 29 + 35 + 31 + 43 + 17 = **339**；
  预检 62 个锚点（61 + 对照）在原文件中各唯一命中一次；终跑基线 **339 passed / 6.72s**
  （首轮基线 338 / 6.59s——那时锁面还差 §6③ 补的那一例）；
  每锚点变异前后 collected 恒 **339**；写盘前 `compile()`、sha256 校验后按原字节还原；
  终跑 **rc=0**（00:38:27 止；墙钟未做 `date +%s` 成对采集，故不登记墙钟）。
  五个被改文件 `# mutation: ` 残留各 **0**；`git status --porcelain src/` 命中 **0**。
- **预登记跑 00:41:17→00:44:39**（墙钟 **202s**，`date +%s` 成对采集）：执行 `make test-cov` 体内的
  pytest 行（xdist `-n 4 --dist loadfile` + `--cov=src --cov-branch`），但**未设 `COVERAGE_FILE`**
  （数据落默认 `.coverage`）——口径差异如实登记，不冒充 `make` 读数（见 §6⑧）。
  collected **12189** = **12183 passed** + 5 skipped + **1 failed**、链内 **200.51s / 40 warnings**，
  唯一红 = 基线守卫 `tests/test_2026_10_10_optimization_batch.py::TestBaselineNumbersConsistency::test_tests_and_mypy_are_current`
  （实收 12189 − 声明 12105 = 84 > 容差 6）。
- 覆盖率：行 **19526/20040 = 97.4351%** 与 BT 逐位相同；弧 **7150/7582 = 94.3023%** 与 BT 逐位相同
  （分母 7582 取 `coverage json` 的 `num_branches`，分子由 `coverage.xml` root `branch-rate` = 0.9430 唯一确定：
  7149/7582 → 0.9429、7151/7582 → 0.9432）。依据不是"读数相同"而是 `git status --porcelain src/` 命中 **0**——
  本轮改动面在 `experiments/` + `tests/` + `docs/` + `scripts/tools/`，覆盖率分母只测 `src/`。
- **刷新后确认跑 00:49:08→00:52:24**（`make test` 同口径：xdist `-n 4 --dist loadfile`、**不带 `--cov`**）：
  **12184 passed / 5 skipped / 0 failed、194.81s / rc=0**、53 warnings、墙钟 **196s**（`date +%s` 成对采集）。
  事前预测 collected **12189** = 12184 + 5（BT 基线 12110 + BU 新锁 79），实测逐位命中。
- `make gates`：全链 **rc=0**，单独执行、不接管道、与其他 pytest 不重叠（`date +%s` 成对采集：墙钟 **199s**，1792689206→1792689405，链内 **19** 条目标回显）。链内 pytest 为 xdist `-n 4 --dist loadfile` 且**不带 `--cov`**：**12184 passed / 5 skipped / 0 failed、193.35s、53 warnings**，12184 + 5 = **12189** 与预登记 predicted collected 逐位相符；用时不可与含 `--cov` 的预登记跑（200.51s）相减。链首 `ruff check .` All checks passed、`ruff format --check .` **1015 files already formatted**、`mypy src/ config.py` **137** 源文件 0 错。链尾分步读数：双语 strict **0 失败 / 0 警告**、链接 strict **189 份文档 / 913 条链接（内部 904 / 外链 9）/ 0 错误**、env-budget **253/253** 无未登记新增、`check_baseline` 结构校验通过、基线数字检查报「当前基线块零硬编码」、状态契约 **136** 文件无未声明键读写、env-snapshot 快照 **115** 键 / 开关全集 **84** / 已覆盖 **84** / 缺失 **0**（另 31 个键不在扫描面，信息项不阻断）、model-fingerprint 无新批次可验（通过）、工具版本 mypy **1.15.0** / ruff **0.16.3** 一致、JSON 契约调用点口径 A **7** 处（期望 7）+ 文档数量表述 **9** 处全 OK、json-strict 工件 **7274 = 严格 7272 + 登记豁免 2 + 违规 0** / 源码 **335** 份写入点违规 **0**、报告→工件三臂对账 **0** 项不一致（T-10 严格 **29 行 / 25 可测**、宽松 **62 / 55**）且**状态登记册覆盖率对账 [OK]**（§1 声明 97.44% / 94.30% 与 `coverage.xml` 实测在 ±0.20pp 内）、零断言门扫 **468** 个测试文件 0 违规、`ast.parse` 守卫站点 **79** / 未覆盖 ValueError 族 **20** / 豁免命中 **20** / EXEMPT 条目 **19** / 违规 **0**、落盘可达性声明 **10** 个通道 / 落盘面 **3** 处全覆盖。口径注：本地链**不加 `--require-coverage`**，登记册那支读的是 **2026-10-23 00:44:37** 那份 `coverage.xml`（预登记跑的产物），不是本链生成。本条描述的是**回填之前**那一跑——回填后未再跑全链；若要让门禁再见这三处文本，须另起一跑并如实标成第二次读数。

## 变异验证（61 锚点 + 1 中性对照）

锚点方向：每一处都是「把 BU 补的分档 / 可达域 / 对账披露退回沉默、退回并档、退回同形」。
判定核 `src/tools/self_repair_trap.py` 的三处门槛字面量是 BU 阈值同源锁的靶子——变异只在
harness 运行期写盘，终态一律按原字节还原（绝不用 `git checkout` / `git stash`：工作树有 21 处未提交改动）。

| 锚点块 | 钉住的守卫 | 结果 |
|---|---|---|
| U01–U04 | 三个门槛常量与全局下界（改值即红） | 全红 |
| U05–U08 | 四档划分与并档（`False` 折成未记录 / 形状不符折成欠点 / 欠点与达界互并） | 全红 |
| U09–U12 | 与判定核同式的取数（末点不可解析豁免、`parse_ok` 参与、`bool` 当分数、不可读折成 0） | 全红 |
| U13–U17 | 可达域宽窄与类型、平坦序列读成下降、两点下界删除 | 全红 |
| U19–U22 | 判定核三处门槛字面量 + 门槛读取对象换名（`len(counts)` → `len(parsed)`） | 全红 |
| U23–U24 | 写侧把判定值 / 信号写死 | 全红 |
| U25–U38 | 分母与并档、域预置、点名与封顶、重跑异常 / 读不懂 / `reconciled` 的沉默化、臂排序 | 全红 |
| U39–U48 | 接线（算了不喂 / 键丢掉 / 章节不读键）、零行臂、沉默臂注、空域注、对账异常注的常开与常闭 | 全红 |
| U49–U62 | 报告表格逐格（可达域 / 不一致 / 开火 / 表头列数 / 四条口径 / 三处门槛文案 / 空域注门槛） | 全红 |
| U63（对照） | 仅改 docstring 强调星号、不动任何判据 | **0 红** |

逐锚点红数（终跑，顺序即执行顺序，U01…U17 与 U19…U63）：
11、10、3、10、27、10、8、11、2、1、1、2、9、9、1、4、1、17、3、2、1、2、2、4、5、2、3、1、1、3、1、1、3、1、9、6、1、9、10、8、1、1、1、2、1、1、1、2、2、1、1、1、1、1、1、1、1、1、1、1、1。

首轮（止于 00:21:18，`rc=2`，基线 collected 338）**不登记为读数**，其未杀活清单 6 项与处置：

| 项 | 现象 | 处置 |
|---|---|---|
| U18-outside-domain-ignores-bucket | **存活** | 撤锚点，代码保留——见 §6① |
| U30-mismatch-detail-uncapped | **存活** | 双重封顶使返回切片成恒等操作——见 §6② |
| U49 / U50 / U53 | **SYNTAX-ERROR（红数 −1）** | 锚点文本非法、变异根本没写进去——见 §6④ |
| U54-table-header-drops-a-column | **存活** | 没有任何锁消费列数——见 §6③ |

## 4. 复现

```bash
# A. 归档输入可达域普查（只读 experiments/results）
#    口径要点：先按"批次形状"过滤（1702 份 JSON 里只有 257 份是批次文件），
#    再按"键在场"分档——`oracle_quality_history` 可能是 None，`results` 可能是 list。
.venv/bin/python - <<'PY'
import collections
import json
import pathlib
import sys

sys.path.insert(0, ".")
from experiments._trap_input_domain import (  # noqa: E402
    SIGNAL_MIN_POINTS,
    TRAP_HISTORY_KEY,
    TRAP_VERDICT_KEY,
    input_bucket,
    mutation_scores,
    signal_domains,
    two_point_decline_outside_domain,
)

rows = keyed = batch = skip_parse = skip_shape = 0
bucket = collections.Counter()
domain = collections.Counter()
lens = collections.Counter()
scores = collections.Counter()
outside = 0
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
        if not isinstance(block, dict):
            continue
        for r in block.get("details") or []:
            if not isinstance(r, dict):
                continue
            rows += 1
            if TRAP_VERDICT_KEY not in r:
                bucket["not_recorded"] += 1
                continue
            keyed += 1
            bucket[input_bucket(r)] += 1
            hist = r.get(TRAP_HISTORY_KEY)
            lens[len(hist) if isinstance(hist, list) else "not_list"] += 1
            for sig, hit in signal_domains(hist).items():
                domain[sig] += hit
            scores[len(mutation_scores(hist))] += 1
            outside += two_point_decline_outside_domain(r)
print(f"批次文件 {batch}（跳过不可解析 {skip_parse} / 非批次形状 {skip_shape}）｜行 {rows}｜有判定 {keyed}")
print(f"四档 {dict(bucket)}")
print(f"长度分布 {dict(lens)}")
print(f"三域可达 {dict(domain)}｜门槛 {dict(SIGNAL_MIN_POINTS)}")
print(f"分数点数分布 {dict(scores)}｜域外两点下降 {outside}")
PY
# 实测：批次文件 257（跳过 108 / 1337）｜行 11197｜有判定 5935
#       四档 {not_recorded: 5262, below_min_floor: 3200, min_floor_reached: 2723, history_malformed: 12}
#       长度分布 {1: 3200, 2: 2723, not_list: 12}
#       三域可达 {assert_count_declining: 0, assertion_collapse: 2723, mutation_score_declining: 0}｜门槛 {3, 2, 2}
#       分数点数分布 {0: 5692, 1: 243}｜域外两点下降 531

# B. 报告章节（13 列表 + 沉默臂 / 空域 / 对账异常注 + 两条口径脚注）
.venv/bin/python experiments/analyze_results.py --input <batch.json>   # 见 "Self-Repair Trap 判定核的输入可达域"
```

## 5. 未做 / 边界

- **不动判定核**：三个门槛是判据本身，改门槛 = 改判据（另一族）。本轮只披露"谁进了域、域里发生了什么"。
- **历史工件不重写**：5935 行仍是 `False` / `[]`，12 行 `oracle_quality_history` 仍是 `None`；报告面把
  缺键的 5262 行显示为「未记录」、把 12 行显示为「形状不符」，不折成"判干净"。
- **不进入任何判定**：分档、可达域、对账都不改 passed / repair / 分母。
- **键池其余 11 项未动**（复跑 A 段普查可点清，合计 64618 行）：`risk_summary`（8864 行）、`patch_precision`（8012）、
  `patch_abstain_signals` / `test_hacking_suspected` / `test_hacking_signals` / `fl_constraint_verdict` /
  `fl_constraint_hit_rank` / `fl_constraint_changed_functions`（各 5935）、`patch_plausible_evidence` /
  `patch_plausible_invariant_violation` / `mdo_crash_rate`（各 4044）
  仍是只写不读——它们是 BV 轮的候选池。
- **英文索引只补本轮条目**：`docs/INDEX.en.md` 从没收到 BR / BS / BT 三份分册的行（本轮补 BU 一行 +
  滚动日期行，不代其余三轮补写）——同族漂移一并留给 BV。
- **未跑真实批次**：本轮零 LLM、$0；"让判定核真的拿到 3 个点"需要新的跑批，不在本轮验收点内。

## 6. 本轮自纠

① **U18 存活 = 「没有断言消费的那一格」第三次复现**（BT §6②、BH 系列同族）。锚点想把
`two_point_decline_outside_domain` 里的 `input_bucket(row) != BUCKET_FLOOR_REACHED` 门去掉，
但该谓词已含 `2 <= len(counts)` 下界，而 `BUCKET_FLOOR_REACHED` 恰好就是 `len >= GLOBAL_MIN_POINTS = 2`
——去掉它得到的仍是同一集合，**任何测试都无法区分**。处置：撤锚点、留代码（这句仍是可读的分档表述），
并登记这条判据：N−1/N 的"全红"里掩盖的是恒等替换，不是弱锁。

② **双重封顶让返回切片变成恒等操作**。`mismatches` 同时在循环内 `len(mismatches) < 20` 与返回处
`[:20]` 封顶，于是 U30（删返回处封顶）无人可杀。改为**封顶单点在返回处**，
「只点名漂移行」（U29）与「封顶 20」（U30）两条行为各自可杀。

③ **表头掉一列没有任何锁消费**。U54 首轮存活：行仍按旧列数产出，Markdown 看起来照样成形。
补 `test_bu_table_rows_share_one_cell_count`（4 行 × 13 列单元格数一致）后终跑 `red=1`。

④ **三处 SYNTAX-ERROR 不是"存活"，是"变异没写进去"**。U49/U50/U53 的替换文本用 `\"""` 收尾
（五引号）在 f-string 里非法，harness 在 `compile()` 前就失败、红数记 **−1**。harness 把它们列入
未杀活清单方向保守、是对的，但登记时必须区分"判据没被断言"与"锚点是坏字符串"：合法写法是
`"""...\"""`（四引号）或改用三单引号字面量。

⑤ **harness 号段跳号须自带说明**：U17 → U19 之间缺 U18（见 ①），数锚点的人会以为丢了一条。
撤回理由就地写在锚点表里（`scripts/tools/bu_mutation_verify.py:172-174`），不靠读者翻手册。

⑥ **mypy `call-overload`**：`_points(history: object)` 需显式 `from typing import Any` 并标注返回
`list[dict[str, Any]]`，否则 :51 的 `int(h.get("assert_count") or 0)` 落在 `int()` 重载的不确定上。
标注与判定核同款，语义不动。

⑦ **本轮新写锁自带两处 lint**：SIM300（可翻转的比较）、RUF005（`xs + [x]` 改 `[*xs, x]`）。

⑧ **口径不冒充**：预登记跑执行的是 `make test-cov` 的 pytest 行但未带 `COVERAGE_FILE`
（该隔离是为防探针子进程把非分支数据写进同一 `.coverage`）。本轮实测分母 20040 / 7582 与 BT 逐位相同、
无 coverage INTERNALERROR，说明这次未受影响；但读数仍按"实际跑的命令"登记。

⑨ **§4 复现命令首版在真语料上崩**——BT §6③ 同族第二次复现。首版直接对 `d.get("results")` 取
`.values()`，而归档里存在 `results` 为 **list** 的文件，`AttributeError` 当场中断。改为
先按批次形状过滤（`isinstance(d, dict) and isinstance(d.get("results"), dict)`）并逐层验形，
才得到上面 257 / 108 / 1337 与四档读数。判据不变：**手册里的复现命令必须先在真语料上跑通一遍**
才能写"实测"。

⑩ **同一普查在两处给出不同的"0 点行数"**（5680 vs 5692）：早先的探针把 12 行形状不符排除在
分数统计之外，§4 的复现命令按「键在场即计入」处理，`mutation_scores(None)` 返回空序列 ⇒ 0 点 5692。
本轮以复现命令口径为准（5692 + 243 = 5935 与"有判定行数"自洽），并在 §1 括注了 12 行的去向。

⑪ **登记稿里的键池项数写错（"9 项"，且漏列 `patch_abstain_signals`）**：§1 的表已经把改后池写成
11 键 / 64618 行，而 §5 的候选清单是人手抄的——复跑 A 段普查才露出差集。这是本册 §65⑥ 的镜像
（同一读数在两处不同口径下打架）：**候选清单必须与计数同源生成**，不得"记得哪些就写哪些"。
已按 11 项改正并补上 `patch_abstain_signals`（5935 行）。
