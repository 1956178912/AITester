# BC 轮：misguided_metrics 重放对账的 rc==0 判绿收口（2026-10-21，零 LLM）

**范围**：BA 轮 §7.2 登记的"保留原口径"项——`experiments/misguided_metrics.py`
三处任务级重放判绿点。这是 F03 缺陷族（pytest 对全 skip / xfail / deselect
的套件同样返回 `rc==0` 且摘要 `passed==0`）在**重放对账工具**中的收口。

**动机（内部不一致）**：本模块的**逐测试**四分类早已把 skip 单列为
"无 pass/fail 信号"（`UNCLASSIFIABLE_REASONS.skipped`），**任务级**重放
判绿却只看 `rc==0`——同一工具内两层口径不一致：一个全 skip 的套件在
逐测试层"不可分类"，在任务层却被记成"fixed 侧绿 / detection=1.0"。

**结论**：三处判绿点全部接入有效通过证据（BA 轮共享谓词同口径），
无有效通过一律 fail-closed；判据顺序与 `_m1_metrics._compute_detection_rate`
逐条对齐。**35 例新锁 + 变异 5 锚点全红（5/3/4/14/1）+ 中性对照 0 红**；
确认跑 **11352 passed / 5 skipped / 0 failed、195.47s、rc=0**
（collected **11357**）；`make gates` 全链 rc=0。**未提交**（随收口提交
一并入库）。

---

## 1. 为什么对账工具不能"保留原口径"

BA 轮把本工具登记为"保留原口径"，理由是：重放值要与**按旧口径计算**的
归档 detection 对账，改判据会让 match 变 mismatch。BC 轮的论证相反：

1. **对账工具的价值恰在于用当前口径复算**。归档值是历史快照；重放若
   沿用旧口径，对账永远 match，工具退化为"复读机"。判据修正后产生的
   mismatch 必须带**可解释归因**（新增"口径修正"分支），而不是被吞掉。
2. **归档侧根本没有命中**（见 §3）：350 任务行 / 700 侧中 rc==0 且无
   pass 的侧为 0——旧口径与新口径在已归档批次上**给出同一组值**，
   对账标签零变化。保留原口径在此语料上没有收益，却有机制风险。
3. **不冤枉归档**：`_verdict_agreement` 对"rc==0 但无有效通过"记
   `not_applicable`（不可判定）而非 `mismatch`——没有证据时不得指控
   归档错。

## 2. 逐点处置（3 处 + 2 项支撑）

| # | 位置 | 改前 | 改后 |
|---|---|---|---|
| 1 | `replay_detection` | fixed `rc==0` ⇒ 1.0 | fixed `rc==0 ∧ 有效通过` ⇒ 1.0；`rc==0 ∧ 无有效通过` ⇒ `None`；判据顺序与 `_m1_metrics` 对齐（buggy 侧 `rc==0` → 0.0 优先，fixed 仍红 → 0.0，最后才判有效通过） |
| 2 | `replay_fixed_green`（`analyze_task`） | `rc==0` ⇒ True | `rc==0 ∧ 有效通过` ⇒ True；无有效通过 ⇒ 字段保持 `None`（"未演示 green"——cross_check 表已有 `none` 桶，不是 False） |
| 3 | `_verdict_agreement` | `replay_green = rc==0` | 同样要求有效通过；无有效通过 ⇒ `not_applicable` + 原因（specific_red 与 over_red 两种期望都不得确认） |
| 4 | `_side_has_effective_pass`（新增） | — | 侧级证据谓词：优先逐测试 `outcomes`（junit/verbose，`run_side` 原生产物：≥1 `pass` 且无 `fail`）；outcomes 缺失回退 pytest 摘要行；两者皆无 ⇒ False（fail-closed） |
| 5 | `_pytest_summary_line` + `run_side` 保留摘要行（新增） | — | `run_side` 把 exec 输出的最后一条 pytest 摘要行存进 `exec_summary_line`——**仅内部判定用**，`_side_record` 不选该键，报告 body schema 不变 |
| 6 | `_skip` 归因保留（支撑） | 迟发跳过无条件覆盖 `detection_disagreement_reason` | 已写下更具体归因（口径修正/超时/收集失败）时不覆盖；早发跳过（语法错误等）行为不变 |

行为不变面（逐位保持）：

- 干净 F2P（buggy 红 + fixed 有真实 passed）⇒ detection 1.0 / green True / verdict match；
- **部分 skip + 真实 passed** ⇒ 仍算有效通过；
- buggy 侧 `rc==0`（含 all-skip）⇒ detection 仍 0.0（不是检出）；
- fixed 侧仍红 ⇒ 0.0；`rc==5` / 超时 / 收集失败 / exec_error ⇒ 原有分支不变；
- 报告 body schema、`_side_record` 键集、四分类与分母纪律零变化。

## 3. 真语料测量（只读静态扫描）

| 口径 | 实测 |
|---|---|
| 归档 MISGUIDED_REPORT（3 份：20261017 / augment / docstring_anchor） | **350** 任务行 |
| 侧结果总数（buggy + fixed） | **700** |
| `exec_rc==0` 的侧 | **568** |
| 其中 `outcome_counts.pass==0`（all-skip at runtime） | **0** |
| 归档侧出现过的 outcome 状态 | pass 567 / fail 356 / timeout 54 / skip 4 / error 2 |

**静态适用面为零**：已归档批次不存在"rc==0 但无有效通过"的侧——
本轮 fail-closed 分支对历史归档读数**零影响**（不重跑、不回填、不重生成
任何归档）。机制由第 4 节的合成最小复现与回归锁共同证明。

## 4. 回归锁

`tests/test_misguided_replay_effective_green_bc.py`：**35 例**
（纯函数 + `analyze_task` 真实重放，零 LLM）。

| 类 | 例数 | 覆盖 |
|---|---|---|
| `TestSideHasEffectivePass` | 8 | outcomes pass/部分 skip/全 skip/全 xfail(记 skip)/pass+fail；空 outcomes 摘要行回退（pass/skip）；无证据 fail-closed |
| `TestReplayDetectionEffectiveGreen` | 10 | fixed 全 skip/xfail ⇒ None；干净/部分 skip F2P ⇒ 1.0；buggy skip ⇒ 0.0；两侧 skip ⇒ 0.0；fixed 红 ⇒ 0.0；收集失败/超时不变；摘要行回退路径；口径修正归因文案 |
| `TestVerdictAgreementEffectiveGreen` | 6 | specific_red/over_red × 无有效通过 ⇒ not_applicable；干净 match；仍红 mismatch；unavailable/None ⇒ not_applicable |
| `TestAnalyzeTaskReplayFixedGreen` | 5 | 端到端（真实 pytest 子进程）：干净 F2P；fixed 全 skip ⇒ green None + detection None + replay_none + 口径归因；两侧 skip ⇒ 0.0；verdict 对账两路 |
| `TestArchivedCorpusApplicability` | 1 | 3 份归档 700 侧零 all-skip-at-runtime（静态面锁） |
| `TestWiringSourceLocks` | 5 | 三处判绿点过谓词、`run_side` 保留摘要行、`_side_record` 不含摘要行（schema 不变） |

最小复现（端到端夹具 `F2P_SKIP_ON_FIXED`）：生成测试在 buggy 上失败
（`a-b=0≠3` 断言红）、在 fixed 上 skip（`a+b=3` 命中条件分支）——
buggy `rc=1/1 failed` ∧ fixed `rc=0/1 skipped`。改前
`replay_detection` 返回 **1.0**（假检出）、`replay_fixed_green` 为
**True**；改后分别为 **None / None**。

## 5. 变异验证

6 个锚点（5 真实 + 1 中性对照）；逐锚点：读取原字节 → 写入变异 →
`compile()` → 跑受影响面（BC 锁 + 既有 misguided 契约测试）→ sha256
校验后按原字节还原（绝不用 `git checkout` / `git stash`；脚本
`scripts/tools/bc_mutation_verify.py`，带名字过滤参数）。
基线干净副本 **35 passed**；每个变异体运行后源文件 sha256 与原字节
一致（脚本内 assert）。

| 锚点 | 变异 | 红数 |
|---|---|---|
| M1-replay-detection-guard-off | 有效通过守卫改 `if False:` | **5** |
| M2-replay-fixed-green-guard-off | `replay_fixed_green` 判据去掉谓词 | **3** |
| M3-verdict-agreement-guard-off | verdict 对账去守卫 | **4** |
| M4-side-predicate-always-true | `_side_has_effective_pass` 恒真 | **14** |
| M5-skip-reason-preserve-off | `_skip` 恢复无条件覆盖归因 | **1** |
| M6-control-comment-wording | 仅改注释用词（行为不变） | **0（SURVIVED，112 passed）** |

## 6. 踩坑与自纠

1. **判据顺序 bug（自纠）**：初稿把 fixed 有效通过检查放在 buggy 侧
   判据之前，导致"两侧都 all-skip"（buggy `rc==0`）返回 None 而非
   0.0——与 BA 轮 `_m1_metrics` 的顺序（buggy `rc==0` → 0.0 优先）
   不一致，被自己的回归锁抓到。修正为同序后补测试锁定。
2. **端到端路径的结构跳过**：fixed 全 skip 的任务在逐测试分类后
   `n_classifiable==0` ⇒ 走 `no_classifiable_tests` 结构跳过——这是
   **既有**行为（skip 本来就不可分类）。判绿字段在跳过前落值；
   顺带修复 `_skip` 用通用文案覆盖更具体归因的问题（M5 锚点锁定）。
3. **中性对照选点**：与 BB 同型——注释用词变异（0 红）才是行为中性点。

## 7. 边界（不得引用为「全仓所有 rc==0 判定均已收口」）

1. **`src/` 生产路径仍未收口**：`detection_gates._run_test_against_code`
   的 `green` 判据、`executor_runtime`/`executor_modes`/`executor` 的
   `passed`、`testless_validation` 两处仍以裸 `rc==0` 判绿——**保留
   原口径**，属 BD 轮范围（生产语义，需单独回归面）。
2. **历史归档零回填**：§3 实测静态适用面为零，本轮不重跑任何 LLM
   批次、不改写任何归档工件（含 3 份 MISGUIDED_REPORT）。
3. **证据源口径差异（已知、零命中）**：`_side_has_effective_pass` 的
   outcomes 判据把 junit 中的 xpass 记为 `pass`（junit 对 xpassed
   不写子元素），而摘要行谓词不计 xpassed——语料中 xpass 零命中，
   差异登记不混用。
4. **报告 schema 不变**：`exec_summary_line` 只进内部判定，
   `_side_record` 键集与 body digest 口径零变化（既有契约测试锁定）。

## 8. 复算命令

```bash
# 目标锁（35 collected）
.venv/bin/python -m pytest tests/test_misguided_replay_effective_green_bc.py -q

# 受影响面（既有 misguided 契约测试）
.venv/bin/python -m pytest tests/test_misguided_replay_effective_green_bc.py \
  tests/test_misguided_metrics.py -q

# 变异验证（6 锚点；可传名字前缀过滤，如 M1 M4）
.venv/bin/python scripts/tools/bc_mutation_verify.py

# 全量 + 门禁（CI 同口径；不与 make gates 重叠）
make test
make gates
```
