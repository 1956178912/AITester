# misguided/effective 逐测试度量：设计、口径与已知限制

> **性质**：机制度量（mechanism metric）的设计/口径文档，配套实现
> `experiments/misguided_metrics.py`、契约测试 `tests/test_misguided_metrics.py`、
> 首轮真实工件报告 `experiments/results/emse_misguided_20261017/`。
> **最后更新**：2026-10-17（L 轮 T2；首轮 df / df_spec 两臂零 LLM 重放）。
> **证据状态**：描述性度量，**非**预注册确认性证据；不含显著性推断。
> 单语文档（过程/口径记录类，非对外参考文档；与 `docs/design/` 下其他
> 单语设计文档同口径——`scripts/gates/check_bilingual_docs.py` 非递归扫描
> `docs/*.md`，不覆盖本目录）。

---

## 1. 动机：为什么需要它

独立评审（`docs/reviews/INDEPENDENT_SYSTEMATIC_REVIEW_2026-10-17.md`）§6 P1
与 §10 A-05 指出：df_spec 规格锚路线三连阴性（D1 / M4 / df_spec）后，机制
假设是"**锚材料 = 对缺陷代码的再描述，约一半概率把缺陷固化成预期行为**"。
但当时能支撑该假设的机制侧信号只有 **`over_red` proxy**：

- 它来自特异性门（`src/tools/detection_gates.py::specificity_verdict`）：生成
  测试整体在 gold 修复代码上是否仍红——**任务级、二值、且不区分**"红得是否
  针对缺陷"；
- `over_red` 上升不等价于"更多的测试在断言缺陷行为"：整套测试只要有一条在
  fixed 上失败，就整体判 `over_red`，其内部可能同时存在大量 effective 测试；
- 于是"锚使误导固化"这一机制主张，只能以 proxy 的形式披露（df_spec PRE-REG
  §3 明确标注 `as-proxy, 不作机制证明`）。

本度量把机制信号升级为**逐测试**、可复算、带分母披露的观测：

- 用归档的 `generated_test` 在**缺陷版**与**修复版**两侧各跑一次；
- 按 pytest node id 逐条判定 pass/fail，再按 ISSTA'26 的三分操作化归类；
- 得到"多少测试在断言缺陷行为（misguided）、多少测试真正区分两版
  （effective）"，以及它们相对**可分类测试数**的占比。

它替代 `over_red` 成为 P1 的机制指标（见
`docs/study/DF_SPEC_PREREG_2026-10-16.md` §3"机制侧信号"与独立评审
§6 P1"misguided 占比 −30%"），但**不改变任何主判定**（detection / McNemar /
BF10 仍由既有分析脚本直出）。

---

## 2. 定义与公式

### 2.1 逐测试真值表

对一条测试 $t$（pytest node id）与一对源码版本 $(B, F)$（缺陷版 / gold
修复版），记 $r_B(t), r_F(t) \in \{\text{pass}, \text{fail}\}$：

| $r_B(t)$ | $r_F(t)$ | 分类 | 含义 |
|---|---|---|---|
| fail | pass | **effective** | 测试真正区分缺陷版与修复版（正确测到缺陷） |
| pass | fail | **misguided** | 测试把缺陷行为当成期望行为（断言了 bug） |
| pass | pass | both_pass | 零检出信号（刻画性/盲测） |
| fail | fail | both_fail | 在正确代码上也失败 → 测试自身无效/恒红 |

前三列之外的任何情况（超时/收集失败/import 失败/语法错误/skip/单侧缺失）
**不进四分类**，按原因单列（见 §2.3）。

### 2.2 汇总公式

逐测试口径（pooled，主口径）：

$$
\text{misguided\_share} = \frac{\#\text{misguided}}{\#\text{classifiable}},
\qquad
\text{effective\_share} = \frac{\#\text{effective}}{\#\text{classifiable}}
$$

其中 $\#\text{classifiable} = \#\text{effective} + \#\text{misguided} +
\#\text{both\_pass} + \#\text{both\_fail}$（四类计数之和恒等于分母）。

任务级口径（披露聚合方差，不做推断）：

- 每任务 misguided 占比 $= \text{misguided}_i / \text{classifiable}_i$，
  报告 `mean / median / min / max / q1 / q3`；
- 含 effective 测试的任务数、含 misguided 测试的任务数、两者皆无的任务数；
- 两臂对比只给**百分点差** $\Delta_{pp} = (\text{share}_B -
  \text{share}_A)\times 100$，标注描述性、无显著性推断。

### 2.3 不可分类原因（单列，不进分母）

| 原因 | 判据 |
|---|---|
| `timeout` | 该测试被 pytest-timeout 判超时（junit `<failure>` 含 `Timeout … from pytest-timeout`），或整文件墙钟超时导致该侧无逐测试结果 |
| `import_error` | 收集/模块导入期命中 `ModuleNotFoundError` / `No module named` / `attempted relative import` |
| `syntax_error` | 生成测试文件语法错误（`SyntaxError` / `invalid syntax`） |
| `collect_error` | pytest 收集/执行期 rc≥2 或 dump 出收集失败但无法归因到 import/语法 |
| `skipped` | `pytest.skip` / `xfail`（无 pass/fail 信号） |
| `test_error` | setup/teardown 或测试执行期 `error`（非断言失败） |
| `missing_side` | 该 node 只在一侧出现（另一侧无结果），且无法归因到超时/收集失败 |
| `unknown` | 其余不可判定（保守兜底） |

**纪律**：不可分类测试**绝不**并入 `both_fail` 或任何四分类的一类。超时
尤其不能当作"测试红"——那是 A-06 判分口径（超时记红用于 detection）的选择，
不是"测试相对缺陷有信号"的证据。

### 2.4 任务级结构跳过（structural skip，不静默）

若任务材料/执行不足以产出任何可分类测试，任务级记 `structural_skip` 并给
原因码，逐任务列入报告（不参与任务级可判定集合，不混入分母）：

`artifact_row_malformed` / `invalid_program_name` / `missing_buggy_source` /
`buggy_source_unparseable` / `buggy_source_validation_failed` /
`missing_fixed_material` / `fixed_material_unparseable` /
`empty_generated_test` / `generated_test_syntax_error` /
`no_tests_collected` / `import_error` / `syntax_error` / `collect_error` /
`file_timeout` / `exec_unknown` / `no_classifiable_tests` /
`materialize_failed` / `unknown`。

### 2.5 分母披露（强制项）

报告同时给出：`n_tasks`（行数）/ `n_tasks_ok` / 结构跳过原因分布 /
`n_tests_collected`（两侧 node id 并集，含跳过任务）/ `n_tests_classifiable`
（分母）/ `n_tests_unclassifiable`（按原因）/ `n_ast_test_defs`（生成测试
AST 的 `test_*` 定义数，用于核对"定义数 vs 收集数"）。任何比率必须能追溯
到这些计数。

主分析集（三层口径，报告 `aggregate` 逐层给出）：

- `all_tasks`：QuixBugs 50 行 = **41 缺陷程序行 + 9 个测试驱动（`*_test`）**；
- `defect_programs_41_convention`：与项目既有
  `experiments/emse_df_spec_analysis.py::defect_program_ids` 对齐的 41 口径
  （仅按 `task_id` 后缀排除 `*_test`），用于与历史材料对账；
- `defect_programs`：**机制度量主分析集 = 40 行**。在 41 口径基础上剔除
  `buggy == fixed`（无缺陷信号）的行——目前唯一命中的是 QuixBugs
  `node.py` 辅助模块：数据集加载器把它当作程序行加载，其
  `task_metadata.test_cases` 实为辅助类源码（无 `test_*` 定义）、
  `buggy` 与 `fixed` 逐字相同，因此 effective/misguided **结构上恒 0**；
  把它计入会稀释误导/有效占比。该行仍保留在 `all_tasks` 与逐任务明细中
  （`defect_signal=false`），不静默删除。

9 个驱动程序的源码使用**包相对 import**（`from .node import Node`）且无
官方 gold 测试；在"平铺执行"的生产口径下生成的 `from <driver> import ...`
无法解析 → 结构跳过（与归档 `detection=None` 同源）。

引用本度量的误导/有效占比时应使用 `aggregate.defect_programs`（40 口径），
并同时披露 41 口径与 `all_tasks` 的行数。

---

## 3. 分类树（实现口径）

```text
读取归档行（task_id / generated_test / task_metadata.fixed / program）
  ├─ 行缺字段 / program 非法标识符 / generated_test 空或语法错误 → structural_skip
  ├─ fixed 缺失或不可解析 → structural_skip
  ├─ 解析缺陷版源码（~/.cache/aitester/quixbugs → data/quixbugs → env）
  │    ├─ 缺失 / 不可解析 → structural_skip
  │    └─ 校验与工件一致：suggested_function ∈ buggy 顶层函数；
  │       若数据目录 correct_python_programs/<prog>.py 与工件 fixed 不一致
  │       → fail-closed structural_skip（无法确认同源）
  ├─ 物化两个版本目录（平铺 {prog}.py + python_programs/{prog}.py 双布局，
  │   同步复制同目录依赖如 node.py，写 test_generated.py 与 conftest.py）
  ├─ 每个版本：
  │    ├─ pytest --collect-only -q → node id 清单 / 收集错误归因
  │    │    （超时 → file_timeout；import/syntax/rc≥2 → 相应原因）
  │    ├─ pytest 整文件一次（-v --junitxml），可用时加
  │    │    --timeout/--timeout-method=signal（单测超时单列）
  │    │    外层 run_with_timeout + killpg 墙钟兜底
  │    └─ 解析 junit（主）+ -v 文本（交叉校验）；两者集合对齐，
  │         timeout 视为 fail 的子类（不误报解析不一致）
  ├─ 归并两侧 node id 并集 → 逐条 classify_outcomes（§2.1/§2.3）
  └─ 任务级复算 detection（M1 三段口径）与 strict 变体，与归档对账
```

---

## 4. 执行口径（可复算的关键决定）

1. **双布局物化 = 生产执行口径的忠实镜像**。生产执行沙箱把被测模块**平铺**
   写成 `{module}.py`，Generator 因此写 `from {module} import ...`；而
   QuixBugs 官方测试/包结构使用 `python_programs.{module}`。只物化一种布局会
   把合法 import 误判成"没跑起来"（ADR-0033 第四起测量伪影，`detection` 曾
   构造性恒 0）。故两个版本目录同时提供：根 `{prog}.py` + `python_programs/
   {prog}.py`（`__init__.py`）+ 同目录其它程序（如 `node.py`）+
   `conftest.py`（`pytest.use_correct=False / run_slow=False`）。
2. **每个版本只跑一次整文件**（效率优先），不使用"逐测试起进程"；逐测试结果
   由 `--junitxml` 取得，`-v` 文本解析用于交叉校验（集合不一致会披露）。
3. **两层超时**：
   - per-test：`pytest-timeout`（`--timeout=N --timeout-method=signal`）；
     插件不可用时静默回退（配置里记录 `pytest_timeout_plugin_available=false`），
     此时超时只可能整体出现（`timeout` 单列，不污染四分类）；
   - 整文件墙钟：`run_with_timeout`（`start_new_session` + `killpg` 整树终止，
     文件后端承接 stdout/stderr，结构上不会因孙进程持管道而永久阻塞）。
4. **嵌套 pytest 环境**：子进程 env 由 `src/utils/process_utils.nested_pytest_env`
   构造，剔除宿主 `PYTEST_PLUGINS` / `PYTEST_ADDOPTS`——否则宿主 pytest 配置
   能让结论与被测代码无关（H2 教训，`tests/test_misguided_metrics.py` 有
   行为级回归：宿主设 `PYTEST_PLUGINS=<不可导入>` 时重放仍必须成功）。
   另固定 `PYTHONHASHSEED=0`、`PYTHONDONTWRITEBYTECODE=1`、禁用
   `cacheprovider/randomly` 插件。
5. **确定性**：报告 body 不含时间戳/墙钟（只进 `run_meta`）；`--repeat N`
   重复整批重放并比较 body digest，差异路径如实披露（不静默平均）。生成测试
   若自身使用未播种随机源，重放可能漂移——这是被测产物的性质，不是工具平均
   掉的噪声。
6. **并行**：任务级 `ThreadPoolExecutor`（每任务内部串行两版本）；结果按
   `task_id` 排序后聚合，保证输出与并行度无关。

---

## 5. 与工件既有字段的交叉校验

报告逐任务给 3 组对账（`cross_check`）：

1. **`detection_rate`**（M1 任务级 F2P 三段判定）：
   本工具用同一批重放的 rc 复算 `replay_detection`（0/1/None）；另给
   `replay_detection_strict`——若任一侧出现单测 timeout 即记 None（模拟
   A-06 per-test 超时**落地前**的历史 M1 口径，用于与归档逐位对账）。
   对账标签：`match` / `mismatch` / `both_none` / `artifact_none` /
   `replay_none`；不一致处逐条给归因（如"per-test 超时改写整文件超时判定"）。
2. **`specificity_gate_verdict`**（specific_red / over_red / unavailable）：
   语义上 `specific_red` ⇔ 生成测试在 gold fixed 上转绿（整文件 rc==0），
   `over_red` ⇔ fixed 上仍红。用重放 fixed 侧绿/红做对账（`match` /
   `mismatch` / `not_applicable`），不一致逐条披露。
3. **`passed`**（归档布尔字段）：只做分布披露与"passed vs 重放 fixed 绿/红"
   交叉表，**不用它推导分类**（历史批次该字段语义与 M1 指标不同）。

**注意**：交叉校验是"同一批工件、同一条物化链路的独立复算"，用于暴露
测量层差异（环境/超时/随机性），不是对原批次判分的重判。

---

## 6. 已知限制（必须随数字一起引用）

### 6.1 生成测试的全局状态与跨测试污染

同一 `test_generated.py` 内的测试**共享进程级全局状态**（模块级变量、
`sys.modules`、被测模块的全局副作用、文件系统副作用）。本工具只做到
"每个版本一个独立临时目录"，**不做逐测试进程隔离**（那会改变 pytest 语义
并使成本不可接受）。因此分类结果是"该测试在本套件收集顺序下的行为"，与
"该测试单独运行的行为"可能不同。

### 6.2 pytest 收集顺序

node id 的收集顺序、参数化展开顺序由 pytest 决定，受生成测试文件内容与
插件影响。分类的**计数**对顺序不敏感（按 node id 归并），但**单条测试的
pass/fail** 可能因顺序/状态污染而变化。报告保留逐测试明细（node id +
两侧结果），使该限制可审计。

### 6.3 官方金测试与 generated_test 的交互

- 四分类**只**使用 `generated_test`；官方金测试 `task_metadata.test_cases`
  不参与分类。
- 官方金测试只在**交叉校验**中作为 M1 `detection_rate` 的既有口径参数
  （arc 归档 detection 由"generated_test 在 buggy 红 ∧ fixed 绿"定义，
  金测试在修复侧参与 repair/false_fix 等其他指标）。
- 两者覆盖的缺陷面可能不同：generated_test 可能只测到缺陷函数的子集，
  gold 测试覆盖全集。因此 `effective` 计数 > 0 不等于任务级 `detection=1`
  （任务级要求**整文件** buggy 红 ∧ fixed 绿，任一条测试在 fixed 上失败都会
  把 detection 打成 0）；反之 `detection=0` 也不等于没有 effective 测试。
  这正是本度量相对任务级二值口径的增益（可分解性），也是不能互相替代的
  原因。

### 6.4 超时口径（与 A-06 有意不同）

- 本度量：超时 = **不可分类**（单列 `timeout`），不并入 `both_fail`。
  理由：缺陷版不终止时，"测试挂死"与"测试断言失败"是不同证据形态；
  把挂死记红会混入"该测试是否真的断言了缺陷行为"的判断。
- A-06 判分口径：超时在执行判定层记 **fail→红**，使 4 个缺陷版不终止的
  QuixBugs 任务（bitcount / sqrt / wrap / find_first_in_sorted）由 None 变为
  可判定。
- 两者**不可混读**：任务级 detection 交叉校验提供 `strict`（历史口径）
  与 rc 两种复算，明确区分"超时改写判定"的影响；逐测试四分类的分母**不含**
  timeout。QuixBugs 上 4 个不终止缺陷任务的 buggy 侧挂死测试很多
  （单任务可收集 90+ 条），因此这些任务的可分类数会显著低于收集数——
  报告的分母披露与 `unclassifiable_counts.timeout` 必须一起读。

### 6.5 结构跳过（9 个驱动任务）与无缺陷信号行

`*_test` 驱动任务在平铺执行口径下无法 import（源码使用包相对 import、
无官方金测试），记 `structural_skip / import_error`。它们不属于 41 缺陷
程序主分析集；不得把跳过数当作"无法分类的失败"。

`node.py` 辅助模块行（buggy == fixed）不结构跳过、但 `defect_signal=false`：
它在 `all_tasks`/明细中可见，不计入 40 口径主分析集。任何"41 行"与
"40 行"的分母差异必须显式披露，不得混用。

### 6.6 单模型、单基准、批次随机性

- 首轮工件来自 QuixBugs × deepseek-flash × 单 seed=42 的单批 df / df_spec，
  描述性结论**不外推**到其他模型/基准/批次；
- 归档批次存在跨批次随机性（评审 §4.6：同臂 QuixBugs 6pp 波动），
  交叉校验差异表是披露该风险的一等工件，不得为了"对齐"而静默调参；
- 与 ISSTA'26 原文数字**不直接可比**：原研究是 Java Defects4J、按**测试条**
  计、不同的提示协议与模型集合。本工具只搬用其**操作化定义**，不搬用数字。

### 6.7 宿主环境与嵌套 pytest

若显式绕过 `nested_pytest_env`，宿主 `PYTEST_PLUGINS`/`PYTEST_ADDOPTS` 会
静默改写结果（H2 教训）。本工具已收口并有行为级回归测试；但**修改执行层
时必须保持该不变量**。

### 6.8 描述性、非预注册确认性

本度量进入报告的一律是描述性统计：计数、占比、百分点差、任务级分布。
**不做**显著性检验/置信区间/效应量推断；P1 预注册的主判定（detection ≥65%
∧ 单向 McNemar p<0.05 ∧ misguided 占比 −30%）中，前两项由既有分析脚本判定，
第三项（机制信号）以本度量的描述性占比变化披露，并标注 `as-descriptive`。

---

## 7. 引用与证据分级

| 项 | 内容 | 等级/说明 |
|---|---|---|
| 操作化定义来源 | Zhao, Zhou & Cohen, *…misguidance…*, ISSTA 2026, DOI **10.1145/3832204** | 引用**来自**独立评审 §4.5/§6 P1（评审已做一手核验，标 A 级）；本仓库未独立重读原文，故仅搬用定义、不引用其数字 |
| 机制假设来源 | 本项目 df_spec 阴性 + BASELINE `over_red` 60% / detection 0% 的历史定位；评审 §6 P1"锚=缺陷再描述" | 本项目 A/B 级工件 + 评审推导 |
| over_red proxy 的替代关系 | `docs/study/DF_SPEC_PREREG_2026-10-16.md` §3"机制侧信号（描述性，不参与主判定）" | 本度量升级该信号，不改变主判定 |
| 相邻需求 | 独立评审 §10 **A-05**（oracle 正确率未系统度量；oracle_correct/oracle_fp/oracle_silent 三指标） | 本度量中的 `misguided` 是"断言缺陷行为"的代理证据，与 A-05 的 oracle 质量指标互补但不相同；A-05 仍待独立落地 |

**红线**：本工具不复制、不复述 ISSTA'26 的效应量数字到本项目口径；凡报告
数字均由复算工件直出。

---

## 8. 复算入口

零 LLM / 零网络，本地 pytest 子进程：

```bash
# 目标单测（<30s，微型 fixture，无真实数据集依赖）
.venv/bin/python -m pytest tests/test_misguided_metrics.py -q

# df / df_spec 两臂重放（产出 MISGUIDED_REPORT.json/.md）
.venv/bin/python -m experiments.misguided_metrics \
  --artifact experiments/results/emse_df_spec_20261016/benchmark_quixbugs_20261017_003023.json \
  --artifact experiments/results/emse_df_spec_20261016/benchmark_quixbugs_20261016_232138.json \
  --out experiments/results/emse_misguided_20261017 \
  --jobs 4 --per-test-timeout 1 --file-timeout 240 --repeat 2
```

输入工件的 sha256、运行命令、时间戳、确定性声明、逐任务明细与分母披露
全部写入报告；`experiments/results/emse_misguided_20261017/README.md` 记录
本轮实跑口径、覆盖面与限制。
