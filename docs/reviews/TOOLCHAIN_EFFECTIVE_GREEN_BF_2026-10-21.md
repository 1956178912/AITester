# BF 轮：脚本工具链的 rc==0 判绿收口（2026-10-21，零 LLM）

**范围**：`scripts/tools/self_mutation.py`（基线前置校验 + 变异体分类）与
`scripts/tools/verify_synthetic_templates.py`（buggy / fixed 两侧）。这是
F03 缺陷族（pytest 对全 skip / xfail / xpass / deselect 的套件同样返回
`rc==0` 且摘要 `passed==0`）在**脚本工具链**的剩余收口；BA / BB / BC /
BD 已收口 M1、experiments 侧消费点与 MDO，BE 已收口生产路径。

**结论**：两处判绿点全部接入共享有效通过证据。`self_mutation` 的基线
`green` 改为 `rc==0` 且含有效通过（全 skip 基线记
`baseline_no_effective_pass` 并阻断），变异体 `rc==0` 无有效通过记
`invalid` 并排除出 mutation score 分母（不再记 `survived` 压低分数）；
`verify_synthetic_templates` 的 buggy / fixed 两侧同样要求有效通过。
**20 例新锁 + 变异 8 锚点全红（2/2/5/1/1/1/2/42）+ 中性对照 0 红**；
登记前一跑 **11426 passed / 1 failed / 5 skipped、201.04s、collected
11432**（唯一失败 = 基线守卫）；刷新后确认跑 **11427 passed / 5 skipped
/ 0 failed、212.90s、collected 11432**；行覆盖 **19055/19581 =
97.3147%**、分支 **6982/7418 = 94.1224%**（`src/` 除共享谓词只读引用外
零改动，读数与 BE 逐位相同）。**未提交**（随收口提交一并入库）。

---

## 1. 两处判绿点

| # | 位置 | 旧判据 | 风险 |
|---|---|---|---|
| 1 | `self_mutation._run_preflight` | `green = rc==0 and not timed_out` | 全 skip 的基线被记成绿，其后的变异体不可能被真实杀死；分数无证据 |
| 2 | `self_mutation.classify_result` | `rc==0 ⇒ survived` | 全 skip / xfail / deselect 的变异体被记成"存活"，无证据地压低 mutation score |
| 3 | `verify_synthetic_templates` buggy 侧 | `rc==0 ⇒ "全绿"` | 全 skip 被记成"缺陷不可检出"（结论方向碰巧保守，但归因错误） |
| 4 | `verify_synthetic_templates` fixed 侧 | `rc!=0 ⇒ 不自洽`、`rc==0 ⇒ 自洽` | 全 skip 的 fixed 侧被记成 gold 自洽，模板会进入检测率分母 |

改后统一口径：**至少 1 个真实 `passed` 且 0 个 `failed`**；部分 skip
与真实 passed 并存仍算有效通过；摘要不可解析（空输出 / 自定义运行器）
不算有效通过（fail-closed）。`rc != 0`（含 `None`）与超时口径不变。

## 2. 逐点处置与行为差异

| # | 位置 | 改后行为 |
|---|---|---|
| 1 | 基线 | `green = run_has_effective_pass(rc, output) and not timed_out`；无有效通过 ⇒ `reason="baseline_no_effective_pass"`，默认阻断（`--allow-red-baseline` 才继续并标 `measurement_valid=false`）；错误文案点名"全 skip / xfail / deselect 同样返回 rc=0" |
| 2 | 变异体 | `classify_result(rc, timed_out, output)`：`rc==0` 且有效通过 ⇒ `survived`；`rc==0` 无有效通过 ⇒ `invalid` + `no_effective_pass:<counts>`（点名 `passed/failed/skipped/xfailed/xpassed/deselected/error` 计数；不可解析 → `unparseable_summary`），保留 `output_tail` 归因，不进分母 |
| 3 | 模板 buggy 侧 | `rc==0` 且有效通过 ⇒ "全绿（缺陷不可检出）"；`rc==0` 无有效通过 ⇒ "无有效通过（全 skip / xfail / deselect，缺陷不可检出）" |
| 4 | 模板 fixed 侧 | `rc!=0` ⇒ 既有"gold 材料不自洽＋尾行"；`rc==0` 无有效通过 ⇒ "无有效通过（gold 材料自洽未被证明）" |

口径来源：`src/utils/pytest_output.run_has_effective_pass`（BE 建立的执行级
唯一入口，BD 上移的单一事实源）。本轮**不复制**解析逻辑，工具链与生产
路径读取同一实现。

## 3. 真语料测量（改前 / 改后）

### 3.1 self-mutation CI 口径（env_utils + atomic_io）

改前 / 改后各跑一次 `make self-mutation-ci` 的等价命令（`--workers 2
--max-mutants 60 --fail-under 0.85` + 冻结 `--test-map`），报告落 `/tmp`
（不写归档）：

| 指标 | 改前 | 改后 |
|---|---:|---:|
| env_utils | 40 killed / 15 survived / 5 invalid（0.7273） | 同左 |
| atomic_io | 16 killed / 4 survived / 0 invalid（0.8000） | 同左 |
| 合计 | 56 / 19 / 5，score **0.7467** | 同左 |
| 逐变异体行 | 80 行 | 80 行，`(mutant_id → outcome, rc)` 逐行相等 |

零影响是**预期**而非巧合：真实测试套件的通过都带真实 `passed`，旧口径与
新口径在合法输入上必须给出同一读数——本轮修的是"空套件被记成存活/绿"的
假读数通道，不是重算真实分数。`--fail-under 0.85` 仍为 1（该门禁的 0.85
阈值是既有独立问题，与本轮无关；Makefile 注释已记录其成因是测试集合选择）。

### 3.2 模板验证器（全 8 池）

改前探针（monkeypatch `_run_pytest` 逐模板计数）：50 个模板 / 100 侧，
其中 **50 个 rc==0 侧全部为有效通过、0 个无有效通过**；改后真实子进程
全跑：**50/50 通过**（buggy 可检出 + fixed 自洽 + 口径无漂移）。同样零
读数变化：50 个模板的 gold 测试都真实执行断言。

### 3.3 影响面结论

两处工具的真实输入都不含"rc==0 但零断言"的样本 ⇒ 历史报告零影响、
零回填；本轮堵住的是未来把全 skip 套件接入这两条工具时的静默假绿。

## 4. 回归锁

`tests/test_bf_toolchain_effective_green.py`（**20 例**）：

- `TestClassifyResultEffectivePass`（8）：真实通过 → survived；部分 skip +
  真实通过 → survived；全 skip / xfail-only / 空输出 / deselected-only →
  invalid + `no_effective_pass`（全 skip 归因含 `skipped`）；rc==1 仍
  killed；超时优先于有效通过。
- `TestPreflightEffectivePass`（4）：全 skip 基线 → `green=False` +
  `baseline_no_effective_pass` + 输出尾部；默认阻断且错误文案含"有效通过"；
  真实通过 → 绿；rc==1 → 既有 `baseline_not_green`。
- `TestSingleMutantEffectivePass`（3）：全 skip 变异体 → invalid + 归因 +
  `output_tail`；真实通过 → survived；rc==1 → killed。
- `TestTemplateEffectivePass`（5）：buggy 红 + fixed 绿 → 无违规；fixed 全
  skip / buggy 全 skip → 各报"无有效通过"；buggy 真绿仍报"全绿"；fixed
  红仍报"gold 材料不自洽"。

既有 `tests/test_self_mutation_tool.py` 的 rc 分类矩阵按新签名改为
`(returncode, timed_out, output, expected)`（用例数不变）；沙箱端到端用例
把被杀死进程的真实 stdout 传入新签名。受影响面 8 个测试文件共 **169
passed**。

## 5. 变异验证

`scripts/tools/bf_mutation_verify.py`：8 锚点 + 1 中性对照。纪律：干净
副本先全绿（20 collected）、逐锚点 `compile()` + collected 数核对、跑完
按 sha256 原字节还原（不用 git checkout / stash）。

| 锚点 | 红数 | 被谁抓住 |
|---|---:|---|
| M1 基线退回 rc-only | 2 | 全 skip 基线不绿 + 默认阻断 |
| M2 基线归因退回 `baseline_not_green` | 2 | 归因断言 + 阻断文案 |
| M3 变异体退回 rc-only | 5 | 四种空套件分类 + 单变异体 |
| M4 归因丢掉摘要计数 | 1 | 全 skip 归因须含 `skipped` |
| M5 fixed 侧守卫关闭 | 1 | fixed 全 skip 必须被报 |
| M6 buggy 侧空套件并入"全绿" | 1 | buggy 全 skip 须报"无有效通过" |
| M7 模板判绿退回 rc-only | 2 | fixed + buggy 两个空套件用例 |
| M8 共享谓词恒真 | 42 | BF 20 + BA + BE（collected 95） |
| M9 中性对照（仅改措辞） | 0 | 必须存活 |

## 6. 踩坑与自纠

- **变异锚点必须被现有锁抓住。** 初版候选锚点 `_run_single_mutant` 把
  output 传成 `""`：全 skip 仍会落 invalid（归因变 `unparseable_summary`），
  而锁只断言 `no_effective_pass` 与 `output_tail` 含 `skipped`，锚点会
  存活。改用"丢掉摘要计数"锚点（M4）并让锁断言归因里必须有 `skipped`，
  红/绿两侧都成立后才登记。
- **既有矩阵测试的签名迁移是必要的口径变更，不是新锁。** rc==0 的
  `survived` 行必须补真实摘要，否则测试自己就在验证旧缺陷；其余行传入
  空输出即可保持原判据。
- **基线的超时优先于有效通过。** `run_has_effective_pass(rc, output)` 只看
  rc 与摘要，不含超时标记；两处调用都显式 `and not timed_out`，否则
  "超时但已打印 passed"会被记成绿。
- **文档收口前的 `ruff format` 会让字符串锚点失效。** 收口时
  `tests/test_bf_toolchain_effective_green.py` 与模板验证器被格式化，
  M5 锚点的旧字符串不再存在，变异脚本报 `ANCHOR-ERROR`（不是"红"）。
  按新字节更新锚点文本后重跑，8 锚点全部转红（M8 42 红）、中性对照
  存活、基线 20 collected 全绿。判据：**"锚点报错"必须与"锚点转红"
  分开；格式化改的是字节，锚点必须跟着字节走，重跑后才算数。**

## 7. 边界（不得引用为「脚本工具链所有 rc==0 均已收口」）

- `scripts/benchmarks/run_standardized_experiments.py` 与
  `experiments/model_gradient.py` 的 `rc==0` 是**批次驱动**控制流（决定是否
  继续下一步/汇总），不是"测试套件判绿"；不接谓词。
- `scripts/tools/verify_instance_solvable.py` 的执行面继承 BE 已收口的
  `RepoExecutor`，不重复接线。
- `experiments/spec_ambiguity.py` 的 `rc` 是探针命令返回码，非 pytest 套件。
- 自定义 `--test-command` 若抑制 pytest 摘要行，本工具按 fail-closed 记
  invalid / 基线非绿；这是有意语义，不是回归。

## 8. 复算命令

```bash
.venv/bin/python -m pytest tests/test_bf_toolchain_effective_green.py -q
.venv/bin/python scripts/tools/bf_mutation_verify.py
.venv/bin/python scripts/tools/self_mutation.py \
  --files src/utils/env_utils.py,src/utils/atomic_io.py --workers 2 \
  --max-mutants 60 --fail-under 0.85 \
  --test-map src/utils/env_utils.py=tests/test_env_utils.py,tests/test_self_mutation_targets.py \
  --test-map src/utils/atomic_io.py=tests/test_atomic_io.py,tests/test_self_mutation_targets.py \
  --json-out /tmp/bf_ci_after.json --md-out /tmp/bf_ci_after.md
.venv/bin/python scripts/tools/verify_synthetic_templates.py
```

## 9. 收口批注（2026-10-21）

- 确认跑（无 `--cov`）：**11427 passed / 5 skipped / 0 failed、212.90s、
  rc=0**（collected **11432** = 11427 + 5 + 0）。
- `make gates` 全链 **rc=0**（单独执行、不与其他 pytest 重叠；链内
  pytest **11427 passed / 5 skipped / 0 failed、212.47s**、46 warnings；
  双语文档 0 警告 / 文档链接 0 错误 / 基线守卫通过 / 零断言违规 0 /
  严格 JSON 违规 0）。
- 文档收口触发的 `ruff format` 改动了测试与模板验证器的字节，变异
  脚本已按新字节重跑：8 锚点全红、M9 存活、基线 20 collected 全绿
  （M5 旧字符串失配的 `ANCHOR-ERROR` 已在 §6 登记）。
- 本轮改动全部未提交，未推送（工作区 37 项，随收口提交一并入库）。
