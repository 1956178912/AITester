# misguided/effective 逐测试度量：df / df_spec 两臂零 LLM 重放工件（2026-10-17）

> **性质**：L 轮 T2 交付的**描述性机制度量**工件（ISSTA'26 操作化：misguided/effective
> 逐测试四分类），用于替代 `over_red` proxy。**不是**预注册确认性证据；不做
> 显著性/效应量推断。所有数字由 `experiments/misguided_metrics.py` 直出，可零 LLM/零网络复算。
>
> **口径设计文档**：`docs/design/misguided_effective_metric.md`
> **输入工件**：`experiments/results/emse_df_spec_20261016/` 两臂（df_spec 处理臂 / df 对照臂）
> **核心结论（一句话）**：按 ISSTA'26 严格操作化，df_spec 相对 df 的 **effective
> 逐测试占比下降 12.65pp**（44.72% → 32.07%），而 **misguided 占比并未上升**（1.29% →
> 0.74%）——df_spec 的 `over_red` 上升主要由 **both_fail**（两侧都失败的无效/过约束测试）
> 承担（1.29% → 12.04%，+10.75pp）。即"锚=缺陷再描述→误导固化"这一机制假设
> **在严格操作化下未获支持**；真实伤害形态更接近"契约/期望值失真导致正确实现也过不了"。

---

## 1. 输入工件（sha256 锁定）

| 臂 | 角色 | 工件 | sha256 |
|---|---|---|---|
| `plain_llm_df` | 对照 | `experiments/results/emse_df_spec_20261016/benchmark_quixbugs_20261017_003023.json` | `536da803dbb290dab9dff26ae14302a8ce8d452e058b1d2c4c1705852900d0ec` |
| `plain_llm_df_spec` | 处理 | `experiments/results/emse_df_spec_20261016/benchmark_quixbugs_20261016_232138.json` | `813c437fc53a84c1517cce234b12184e5047bf483fb982cb9382d1c61307245a` |

两臂工件来自 2026-10-16/17 的 df_spec 双臂实验（`git_sha=cd514d2…`，`git_dirty=false`；
预注册 `docs/emse/EMSE_DF_SPEC_PREREG_2026-10-16.md`）。本工件只读消费，不修改。

## 2. 复算命令（零 LLM / 零网络）

```bash
# 目标单测（<30s；微型 fixture，不依赖真实 QuixBugs/网络）
.venv/bin/python -m pytest tests/test_misguided_metrics.py -q    # 74 passed

# 两臂重放（产出本目录 MISGUIDED_REPORT.json / .md）
.venv/bin/python -m experiments.misguided_metrics \
  --artifact experiments/results/emse_df_spec_20261016/benchmark_quixbugs_20261017_003023.json \
  --artifact experiments/results/emse_df_spec_20261016/benchmark_quixbugs_20261016_232138.json \
  --out experiments/results/emse_misguided_20261017 \
  --jobs 4 --per-test-timeout 1 --file-timeout 240 --repeat 2
```

- 运行环境：Python 3.14.6 / pytest 9.1.1 / pytest-timeout 2.4.0 / macOS darwin；`nice -n 15` 下执行；
- 实测墙钟 **239.4s**（含 `--repeat 2` 确定性重放，2 次全量）；缺陷版源码解析自
  `~/.cache/aitester/quixbugs/python_programs/`（与工件 `task_metadata.fixed` 的
  同源校验逐任务通过）；
- `MISGUIDED_REPORT.json` 的 `schema = misguided_effective_metric/1`，报告内嵌输入 sha256、
  完整命令行、时间戳（`run_meta`）、body digest、确定性声明、逐任务逐测试明细。

## 3. 口径摘要（完整定义见设计文档）

对每条 pytest node id 在**缺陷版（buggy）**与**gold 修复版（fixed）**各跑一次：

| 分类 | 判据 |
|---|---|
| effective | buggy fail ∧ fixed pass（真正区分两版） |
| misguided | buggy pass ∧ fixed fail（把缺陷行为断言成期望行为） |
| both_pass | 两侧都 pass（零检出信号） |
| both_fail | 两侧都 fail（正确实现也过不了 → 测试无效/过约束） |

- **分母** = 可分类测试数 = 四类之和；`timeout / collect_error / import_error /
  syntax_error / skipped / test_error / missing_side / unknown` **单列**、不进分母；
- 超时**不**当"测试红"（与 A-06 判分口径有意不同，交叉校验表用 `strict` 口径单独对账）；
- 每版本只跑一次整文件 pytest（`--junitxml` 取逐测试结果），先 `--collect-only` 定位
  收集错误；pytest-timeout 1s/测 + 整文件墙钟 240s（`run_with_timeout` + killpg）；
- 子进程 env 经 `nested_pytest_env` 构造（剔除宿主 `PYTEST_PLUGINS`/`PYTEST_ADDOPTS`，H2 教训）；
- **主分析集 = 40 个有缺陷信号的缺陷程序**：QuixBugs 50 行 = 40 真实缺陷程序 + 9 个
  `*_test` 驱动（结构跳过）+ `node.py` 辅助模块（`buggy==fixed`，无缺陷信号，
  `defect_signal=false`；保留在 `all_tasks` 与逐任务明细，不计入 40 口径）。
  另给 `defect_programs_41_convention`（项目既有 41 口径，含 node）与 `all_tasks`（50 行）
  两套兼容口径，报告内三套并列、不混用。

## 4. 核心结果（40 口径主分析集；分母 = 可分类测试数）

| 指标 | `plain_llm_df`（对照） | `plain_llm_df_spec`（处理） | Δ (df_spec − df) |
|---|---|---|---|
| 分析任务数 / ok 任务数 | 40 / 40 | 40 / 40 | — |
| 总收集测试数（行内并集） | 834 | 1336 | +502 |
| **可分类测试数（分母）** | **776** | **1213** | +437 |
| 不可分类测试数 | 58（timeout 56、skipped 2） | 123（timeout 122、test_error 1） | — |
| effective 计数 / 占比 | **347 / 44.72%** | **389 / 32.07%** | **−12.65pp** |
| misguided 计数 / 占比 | **10 / 1.29%** | **9 / 0.74%** | **−0.55pp** |
| both_pass 计数 / 占比 | 409 / 52.71% | 669 / 55.15% | +2.45pp |
| both_fail 计数 / 占比 | 10 / 1.29% | 146 / 12.04% | **+10.75pp** |
| 含 effective 测试的任务数 | 37 / 40 | 37 / 40 | 0 |
| 含 misguided 测试的任务数 | 4 / 40 | 4 / 40 | 0 |
| 每任务 misguided 占比 mean / median | 1.57% / 0% | 0.78% / 0% | — |
| 每任务 effective 占比 mean / median | 42.41% / 40.06% | 33.27% / 23.82% | — |
| 每任务可分类数 mean / median | 19.4 / 17.5 | 30.3 / 23.0 | — |

> 兼容口径（同批归档、供与历史材料对账）：**41 口径（含 node）** df = 793 可分类
> （effective 43.76% / misguided 1.26% / both_pass 52.84% / both_fail 2.14%）、df_spec =
> 1230 可分类（31.63% / 0.73% / 55.04% / 12.60%）；`all_tasks`（50 行）数字见报告 §3。

**misguided 任务明细（40 口径）**：

- df（10 条）：`wrap` 6、`subsequences` 2、`bucketsort` 1、`hanoi` 1；
- df_spec（9 条）：`next_palindrome` 3、`subsequences` 3、`knapsack` 2、`possible_change` 1；
- 两臂 misguided **绝对计数几乎相同（10 vs 9）**，在 776 / 1213 的分母上占比差
  仅 −0.55pp；且集中在 4 个任务。**该差异量级不足以支撑"锚显著减少/增加误导"的强主张**，
  只能作描述性披露。

**df_spec 的 both_fail 高度集中**：146 条中 `shunting_yard` 47、`kheapsort` 40、
`next_palindrome` 27，前三任务占 **78.1%**——即"在正确实现上也失败"的测试并非均匀
出现，而集中在少数任务（与归档 `over_red` 任务数 9 → 17 的方向一致）。

## 5. 与工件既有字段的交叉校验（测量链忠实性证据）

| 对账项 | `plain_llm_df` | `plain_llm_df_spec` |
|---|---|---|
| `detection_rate` 一致（match） | **36 / 41 可判任务** | **35 / 41** |
| `detection_rate` 不一致（mismatch） | **0** | **0** |
| 归档 None ↔ 重放 None（both_none） | 9（= 9 个驱动任务结构跳过） | 9 |
| 归档 None、重放可判（artifact_none） | 5 | 6 |
| `specificity_gate_verdict` 一致 | 40 / 41（match） | 37 / 41 |
| `specificity_gate_verdict` 不一致 | **0** | **0** |
| verdict 不可判（n/a） | 10（9 驱动 + 1 归档 unavailable） | 13（9 驱动 + 4 归档 unavailable） |

- **零 mismatch**：凡归档有判定（detection / verdict）的任务，本次重放用**完全独立**的
  物化+执行链路逐位复现——说明 df_spec 负结果不是重放/测量链路的伪影，而是被测生成
  测试的真实行为；
- `artifact_none` 的 5/6 行可由 **per-test 超时口径**完整解释：`bitcount` /
  `find_first_in_sorted` / `sqrt` / `wrap`（df_spec 另加 `to_base`）在归档批次里因整套
  挂死被 M1 记 None，本次重放启用 per-test 超时后变为可判（逐条归因见报告 §5 差异表；
  报告的 `replay_detection_strict` 模拟 A-06 落地前口径，对这些任务同样给 None，与归档逐位一致）；
- 唯一需要人工核对的是 `node`：其归档 `task_metadata.test_cases` 实为辅助类源码（无
  `test_*` 定义），M1 不可判；重放可算 0.0。该行已标 `defect_signal=false` 并从 40 口径
  主分析集剔除，**不静默使用**。
- 归档 `passed` 全为 false（50/50），只做披露：`passed=False` 且重放 fixed 侧绿/红 =
  31/10（df）、20/21（df_spec）——历史 `passed` 字段与本度量不构成可互推关系。

## 6. 结论与解读（**描述性**，非预注册确认性）

1. **与 df_spec 负结果一致**：归档任务级 detection 为 df 77.8%（28/36）vs df_spec
   54.3%（19/35）（预注册分析脚本直出）。本度量给出同方向的逐测试分解：effective
   占比 −12.65pp、每任务 effective 占比 mean −9.1pp；且两臂"含 effective 测试的任务数"
   相同（37/40）——**df_spec 并非"写不出有效测试"，而是每个套件里混入大量在 fixed 上
   也失败的测试，拖垮了"整文件 fixed 绿"的任务级三段判定**。这解释了任务级二值指标
   为何对机制变化不敏感/不可分解，也是本度量要解决的问题。
2. **对 P1 机制假设的修正（重要）**：预注册/评审的机制假设是"df_spec 锚 = 对缺陷代码
   的再描述 → 把缺陷行为固化为期望 → **misguided 上升**"。严格 ISSTA 操作化下**未观察
   到该方向**：df_spec 的 misguided 占比反而略低（0.74% vs 1.29%，绝对数 9 vs 10）。
   与此同时 `over_red` 上升被 **both_fail（+10.75pp）** 接管——即更常见的失败形态是
   "测试在缺陷版与修复版上**都**失败"（期望值/契约错误、过约束），而不是"断言缺陷行为"。
   → 后续 P1 docstring 独立锚正式批（新批次工件）应使用本工具同口径拆分误导/有效/
   both_fail 占比，作为**描述性机制信号**；不得把 `over_red` 上升直接读作"misguidance 上升"。
3. **与文献数字不可比**：ISSTA'26 的操作化定义被搬用，但其效应量数字（Java/Defects4J/
   不同提示协议与模型）**不进入**本项目口径；本报告任何数字均来自上述两件工件的本地复算。
4. **超时口径影响必须一起读**：QuixBugs 4 个"缺陷实现不终止"任务（bitcount / sqrt /
   wrap / find_first_in_sorted；df_spec 另含 to_base/knapsack 边缘任务）产生大量挂死测试：
   56（df）/ 122（df_spec）条单列 timeout、不进分母。若把它们当作"测试红"，both_fail/
   effective 都会被高估——报告选择单列并披露，未为凑数字调整分类定义。

## 7. 覆盖面与限制（完整版见设计文档 §6）

- **覆盖**：两臂各 40/40 缺陷程序可分类（无主分析集结构跳过）；逐测试可分类 776 / 1213；
  逐任务明细含每条测试的 buggy/fixed 结果与分类（报告 §7）；9 个 `*_test` 驱动任务因
  包相对 import 在平铺执行口径下无法 import → 结构跳过（`import_error`），与归档
  `detection=None` 同源；`node.py` 辅助模块 `buggy==fixed` → 无缺陷信号、不入 40 口径。
- **不可分类单列**：timeout 56/122、skipped 2/0、test_error 0/1，逐任务在报告 §3.2/§7 披露。
- **已知限制**：①生成测试全局状态与收集顺序照旧（仅按版本隔离临时目录，不逐测试隔离
  进程）；②官方金测试不参与四分类，只用于 detection 口径对账；③超时单列口径与 A-06
  "超时记红"有意不同；④单模型（deepseek-flash）/单基准/单批次，描述性结论不外推；
  ⑤生成测试若含未播种随机源，重放可能漂移（本批 `--repeat 2` 实测逐位一致，见 §8）。
- **不修改实验冻结工件**：本次只读两件输入 JSON；输出全部落本目录。

## 8. 确定性声明

`--repeat 2` 全量重复重放两次：**body digest 两次相同**
（`c3e2db3745b7376d5469c173a2f0d4252945681a618e4f4d086e914b5b2bad83`），
`difference_paths=[]`（除时间戳/墙钟等易变字段外逐位一致；这些字段只进
`run_meta`，不参与 digest）。确定性口径由 `tests/test_misguided_metrics.py`
（`TestReportDeterminism`）锁定。

## 9. 工件清单

| 文件 | sha256 | 说明 |
|---|---|---|
| `MISGUIDED_REPORT.json` | `6d4e1fd7ba866cbe74bf0e82b9102617de3002c48de567dab68b3bfd831b03e7` | 全量报告（含逐任务逐测试明细、交叉校验、分母披露、run_meta） |
| `MISGUIDED_REPORT.md` | `215385200a0a5b56bc643a6111675f72ed5494908e0583b38972d06dab99475d` | 人读版报告（表格直出） |
| `README.md` | 本文件 | 口径/输入 sha256/复算命令/结论/限制 |

工具与测试（随 L 轮提交入库，供 Lead 统一 commit；本工件为未提交工作树生成）。
说明：`MISGUIDED_REPORT.json` 的 body 由 `2f9a2716…` 版本生成；其后仅 Markdown
渲染函数有改动（body 与 digest 不变），`MISGUIDED_REPORT.md` 由 `22cd1041…`
版本从同一 JSON 重渲染，下表为当前工作树 sha256：

| 文件 | sha256（生成本工件时） |
|---|---|
| `experiments/misguided_metrics.py` | `22cd104196283326f8364e20905e6ce4b7b8955d80ee48351368cf91f3bf19d6` |
| `tests/test_misguided_metrics.py` | `5c5561b0e3da834b9015bb33f8be6e8306cb525887f4785073da096f7ccedaa4` |
| `docs/design/misguided_effective_metric.md` | `4239821427ac46deee36033ec79f341483c40c76f2344e2719193ffafe88a696` |

环境：Python 3.14.6 / pytest 9.1.1 / pytest-timeout 2.4.0 / macOS darwin / `--jobs 4`
`--per-test-timeout 1 --file-timeout 240 --repeat 2`；`nice -n 15`（exp-runner 跑批窗口协调）。
