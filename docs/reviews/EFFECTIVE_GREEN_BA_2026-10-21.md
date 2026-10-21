# BA 轮：rc==0 不是有效通过——全 skip / xfail 的套件没有断言执行（2026-10-21，零 LLM）

**范围**：M1 指标与其同源消费者对"测试通过"的判定——

- `experiments/_m1_metrics.py::_compute_detection_rate`（F2P 第二段：fixed 侧）；
- `experiments/_m1_metrics.py::_compute_repair_rate`（gold 套件在补丁后代码上）；
- `experiments/repair_replay.py::replay_row`（重放裁决）；
- `experiments/mutation_detection.py::mutation_detection_rate`（基线段）。

**结论**：pytest 对"没有任何断言执行"的套件同样返回 `rc==0`。旧实现
只看 `rc`，于是全 skip / xfail / xpass / deselect 的摘要行（`passed==0`）
被计成有效 green：detection 的 fixed 侧与 repair 的 gold 侧各有一条
假阳性通道，重放工具给出 `correct`，变异检测则把"测试没跑"误报成
"测试没有检出力"（`rate=0.0`）。处置：新增共享谓词
`_suite_has_effective_pass`（至少 1 个 `passed` 且 0 个 `failed`；
部分 skip 与真实 passed 并存仍有效），四处消费点接入，无有效通过
一律 fail-closed（`None` / `unverifiable` / `skipped`）。
**35 例新锁 + 变异 6 锚点全红 / 中性对照全绿**；确认跑
**11257 passed / 5 skipped / 0 failed、204.07s、rc=0**。**未提交。**

---

## 1. 缺陷定义

### 1.1 最小复现（审计 F03 条件）

| 侧 | 测试代码 | pytest 结果 |
|---|---|---|
| buggy | `assert False` | `rc=1`，`1 failed` |
| fixed | `pytest.skip("instrument unavailable")` | `rc=0`，`1 skipped` |

改前 `_compute_detection_rate` 的判定链是：

```python
if buggy_rc == 0:
    return 0.0
if _looks_like_test_execution_error(...):
    return 0.0
if fixed_rc != 0:
    return 0.0
return 1.0
```

`fixed_rc == 0` 处没有"是否真的通过了一个断言"的证据检查，于是上表
返回 **1.0**——一次没有执行任何断言的运行被记成"真实 fail-to-pass 检出"。

同一通道在另外三个消费者上分别表现为：

| 消费者 | 改前行为 | 改后行为 |
|---|---|---|
| `_compute_repair_rate` | gold 全 skip + 有补丁 → **1.0**（"修好了"） | `None`（不可测） |
| `repair_replay.replay_row` | gold 全 skip → `correct` | `unverifiable` |
| `mutation_detection_rate` | 测试全 skip → 基线"全绿" → 所有变异体存活 → **rate=0.0** | `skipped=True`、`rate=None` |

### 1.2 为什么不是"保守即可"

三处都已有正确的 fail-closed 先例：`_suite_run_verdict` 对 oracle 套件
把 `skipped>0 且 failed==0` 判为 `unavailable`；`_compute_repair_rate`
对 `rc==5`（no tests collected）返回 `None`。F03 的问题不是不知道该
怎么办，而是该处理**没有传播到 M1 的 detection / repair 及其同源消费者**。

### 1.3 口径边界：部分 skip 仍可以是有效通过

审查报告明确警告"部分 skip 可以与有效断言通过并存"。因此不能直接把
`_suite_run_verdict`（任何 skip → unavailable）套到这三个消费点——那会
把"1 passed, 1 skipped"误判为不可测。新谓词只拒绝 `passed==0`：

```python
def _suite_has_effective_pass(output: str) -> bool:
    counts = pytest_summary_counts(output)
    return int(counts.get("passed", 0)) > 0 and int(counts.get("failed", 0)) == 0
```

摘要不可解析（空输出 / 自定义运行器）同样返回 `False`——fail-closed，
不把"读不到证据"当成"证据成立"。

## 2. 真语料测量（只读）

全部为静态扫描 + 只读解析，零 LLM、零网络、不重写任何归档：

| 口径 | 实测 |
|---|---|
| benchmark 归档（`**/benchmark_*.json`） | **246** 份 |
| 含生成测试的行 | **9358** 条 |
| 非 oracle 且含 skip/xfail 标记的生成测试 | **114** 条 |
| 其中 `detection_rate == 1.0` | **12** 条 |
| 唯一 gold 套件 | **736** 份 |
| gold 套件含 skip 标记 | **2** 份（**0** 份模块级全 skip） |
| gold 标记行 / 其中带补丁 | **92** / **55** 条 |
| 带 mutation 判定键的行 / 已测（rate 非 None） | **4895** / **1376** 条 |
| mutation 已测行中生成测试含标记 | **132** 条 |

**与审计数字的差异**：审计报告写"88 条非 oracle 生成测试含 skip/xfail
标记，其中 10 条 detection=1"；按本仓当前 246 份归档按上述口径复扫得到
**114 / 12**。审计未给出筛选条件的实现，差异无法逐位复现；本手册与
回归锁一律采用**本仓实测值**，不使用审计数字。

**静态适用≠已证实假阳性**：12 条 detection=1.0 的行经逐条检查均为
**条件性** skip/xfail（`pytest.skip` 在分支内、`@pytest.mark.skipif`），
没有模块级全 skip（`allow_module_level=True`），本轮不重跑 LLM、不回填
归档，因此不声称这 12 条在改前口径下必然是假阳性；机制由第 1 节的
最小复现与第 4 节的锁共同证明。

## 3. 处置

| 位置 | 判定 | 无有效通过时 |
|---|---|---|
| `_m1_metrics._compute_detection_rate` | fixed 侧 `rc==0` ∧ 无执行错误 ∧ `_suite_has_effective_pass` | `None`（不可测，不误报检出） |
| `_m1_metrics._compute_repair_rate` | gold 侧 `rc==0` ∧ `_suite_has_effective_pass` | `None`（与 `rc==5` 同口径） |
| `repair_replay.replay_row` | `rc==0` ∧ `_suite_has_effective_pass` | `status="unverifiable"` |
| `mutation_detection.mutation_detection_rate` | 基线 `rc==0` ∧ 无执行错误 ∧ `_suite_has_effective_pass` | `skipped=True`、`rate=None` |

行为不变面（逐位保持）：

- 干净 `rc==0`（至少 1 passed、0 failed）→ detection/repair 仍为 1.0；
- **部分 skip + 真实 passed** → 仍为有效通过（四条路径同口径）；
- buggy 侧 `rc==0`（含 all-skip）→ detection 仍为 0.0（不是检出）；
- gold 失败（`rc!=0`）→ repair 仍为 0.0、重放仍为 `wrong_patch`；
- `rc==5` / 超时 / 材料缺失 → 原有 fail-closed 分支不变。

## 4. 回归锁

`tests/test_effective_green_ba.py`：6 个测试类，**35 例**。

| 类 | 例数 | 覆盖 |
|---|---|---|
| `TestSuiteHasEffectivePass` | 10 | 干净 passed / 部分 skip / 全 skip / xfail / xpass / deselect / no tests ran / passed+failed / failed+skip / 空输出 |
| `TestDetectionRequiresEffectiveGreen` | 7 | fixed 侧 skip、xfail → None；干净 F2P、部分 skip F2P → 1.0；buggy skip → 0.0；fixed 失败 → 0.0；源码锁 |
| `TestRepairRequiresEffectiveGreen` | 6 | gold 全 skip、全 xfail → None；干净 / 部分 skip → 1.0；失败 → 0.0；源码锁 |
| `TestRepairReplayRequiresEffectiveGreen` | 5 | 全 skip → `unverifiable`（rc=0 仍记录）；干净 / 部分 skip → `correct`；失败 → `wrong_patch`；源码锁 |
| `TestMutationBaselineRequiresEffectiveGreen` | 4 | 全 skip 基线 → skipped/None；真实 passed + skip → 正常测量；弱但真实（`assert True`）→ 0.0；源码锁 |
| `TestRealCorpusApplicability` | 3 | 12 条 detection=1.0 行静态适用 + 非模块级全 skip + 全仓计数稳定（246 / 114 / 12） |

另有既有测试按新口径改写：`tests/test_oracle_independent_judging.py::
TestM1IndependentJudging::test_switch_off_zero_extra_subprocess` 的行内
替身原返回 `(0, "", "")`，新谓词正确地把它判为"无有效通过"；改为
`(0, "1 passed in 0.01s", "")`（用例数不变，断言对象仍为零子进程 /
零过滤）。

## 5. 变异验证

六个真实锚点 + 一个中性对照；逐锚点：写入变异 → `compile()` → 跑
受影响面（8 个测试文件）→ sha256 原字节还原（绝不用 `git checkout` /
`git stash`）。基线 **264 passed**，collected 恒 **264**；还原后源文件
sha256 与原字节一致。

| 锚点 | 变异 | 红数 |
|---|---|---|
| M1-helper-always-true | `_suite_has_effective_pass` 恒返回 `True` | **14** |
| M2-helper-drops-failed-clause | 谓词去掉 `failed == 0` 分支 | **1** |
| M3-detection-guard-off | detection 的 F03 守卫改 `if False:` | **3** |
| M4-repair-guard-off | repair 的 F03 守卫改 `if False:` | **3** |
| M5-repair-replay-guard-off | 重放的 F03 守卫改 `if False:` | **1** |
| M6-mutation-baseline-guard-off | 变异基线的 F03 守卫改 `if False:` | **2** |
| M7-control-docstring-wording | 仅改谓词 docstring 用词（行为不变） | **0（SURVIVED）** |

M1 的 14 红按用例名实测覆盖：纯谓词全 skip / xfail / xpass /
deselect / no tests ran / passed+failed / failed+skip / 空输出 **8**
例，detection 的 fixed skip / xfail **2** 例，repair 的 gold skip /
xfail **2** 例，重放 all-skip **1** 例，变异基线 all-skip **1** 例
（`-rf` 逐名捕获，与上表逐项对齐）。M2 的 1 红 =
`test_pass_with_failure_is_not_effective`——证明 `failed==0` 分支不是
死代码。M3/M4 各 3 红 = 该消费点的 skip / xfail / 源码锁三类守卫；
M5 的 1 红 = 重放 all-skip；M6 的 2 红 = 基线 all-skip + 源码锁。
中性对照仅改 docstring 用词，264 例全绿，证明红数来自行为变异而非
文本差异。

## 6. 收口读数

| 项 | 实测 |
|---|---|
| 登记前全量（`make test-cov`） | **11256 passed / 1 failed / 5 skipped、201.48s、rc=2**；collected **11262** |
| 唯一失败 | 基线守卫自身（BASELINE 仍写 11222，实收 − 声明 = 34 > 6 容差） |
| 覆盖率（`coverage.xml` root） | **19002/19528 行 = 97.3064%**、**6960/7396 弧 = 94.1049%**（与 AZ 逐位相同；`src/` 零改动） |
| 十项核心模块 | 逐项复算与 AZ 逐位相同（98.53 / 99.24 / 97.28 / 99.88 / 99.38 / 99.09 / 96.26 / 98.67 / 92.98 / 98.10） |
| 确认跑（`make test`，BASELINE 刷新后） | **11257 passed / 5 skipped / 0 failed、204.07s、rc=0**（collected 11262） |
| 门禁（`make gates` 最后单独跑，不与其他命令重叠） | **rc=0**；链内 **11257 passed / 5 skipped / 0 failed、201.90s**（45 warnings；同一 collected **11262**）；`ruff check` All checks passed、`ruff format --check .` **934 files already formatted**、mypy `Success: no issues found in 135 source files`；双语文档 0 警告 / 0 失败；文档链接 strict **169 份文件 / 716 条链接 / 0 错误 / 0 警告**；env-budget 253/253；状态通道 134 文件；JSON 契约 7/7；JSON strict **7274 工件 = 7272 严格 + 2 路径豁免 + 0 违规**、300 源文件 0 写入点违规；报告↔工件对账 [OK]；零断言 **445 测试文件 / 0 违规**；回填后验证跑（再次单独 `make gates`）**rc=0**、链内 **11257 passed / 5 skipped / 0 failed、206.09s**（35 warnings；同一 collected 11262，各项计数不变） |

**变异验证**：6 个真实锚点全部 KILLED（红数 14 / 1 / 3 / 3 / 1 / 2），
中性对照 SURVIVED（264 passed）；每个变异体写入前 `compile()`、运行后
sha256 原字节还原并复验，受影响面 collected 恒 **264**。

## 7. 边界（不得引用为「全仓所有 rc==0 判定均已收口」）

1. **只改四个消费点**：M1 detection、M1 repair、`repair_replay` 重放裁决、
   `mutation_detection` 基线段。oracle 判读 `_suite_run_verdict` 本就
   区分 skip，未改。
2. **重放对账工具保留原口径**：`experiments/misguided_metrics.py` 的
   `replay_detection` / `replay_fixed_green` / `_verdict_agreement` 仍以
   原始 `exec_rc == 0` 判绿，同一 all-skip 通道在这些工具中**保留**；
   本轮未改、未重新生成任何重放归档。引用其 detection 对账结果时不得
   假定已收口。
3. **gold 自洽性审计保留原口径**：`experiments/emse_gold_conformance_audit.py::_audit_one`
   的 `status="pass"` 仍只判 `rc==0`；审计工件零重写。
4. **历史归档零回填**：12 条静态适用行的 `detection_rate` 仍是旧值；
   本轮零 LLM，不重跑、不改写，不声称历史批次读数已自动修正。
5. **摘要行是判据**：若运行器不输出 pytest 摘要（空输出 / 自定义
   reporter），谓词判 `False` → 不可测。需要测量时必须保留摘要行。
6. **部分 skip 的边界**：只要至少 1 个真实 passed 且 0 failed，即算有效
   通过；不要求"所有测试都通过"，也不把"跳过大多数"伪装成"全部通过"。

## 8. 复算命令

```bash
# 目标锁（35 collected）
.venv/bin/python -m pytest tests/test_effective_green_ba.py -q

# 受影响面（M1 语义 / 变异 / oracle 判读 / 测量复核）
.venv/bin/python -m pytest tests/test_effective_green_ba.py \
  tests/test_m1_metric_semantics.py tests/test_r5_mutation_detection.py \
  tests/test_batch_vii.py tests/test_oracle_instrument_safety.py \
  tests/test_oracle_independent_judging.py \
  tests/test_review_20261019_measurement.py \
  tests/test_detection_gates_matrix.py -q

# 全量 + 覆盖率（CI 同口径；不与 make gates 重叠）
make test-cov

# 确认跑（BASELINE 刷新后）
make test

# 门禁（最后单独跑，绝不与其他命令重叠）
make gates
```
