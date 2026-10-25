# 自身测试套件变异测试（self-mutation）设计说明

> 立项日期：2026-10-17（WP-A）
> 状态：**已实装**——`scripts/tools/self_mutation.py` + 3 模块基线实测 + 存活变异体击杀批次
> （2026-10-17）。本文写清"为什么这样测量"，实测数字见 §7/§8；机器可读事实源为
> `experiments/results/self_mutation_20261017/*.json`。
> 关联：`experiments/mutation_testing.py`（被复用的变异算子层）、
> `src/utils/process_utils.py`（`run_with_timeout` / `nested_pytest_env`）、
> `docs/design/` 不在双语门禁扫描面（本文件中文单语）。

## 1. 背景与问题

本仓的"测试质量"目前由两层门禁度量：

1. **覆盖率门禁**（`coverage_ratchet.py` / `check_branch_coverage.py`）：回答
   "源码行/分支**被执行**过吗"；
2. **既有变异层**（`experiments/mutation_testing.py`）：服务**LLM 生成的测试**
   打分（被测对象是任务代码，测试由模型产出）。

两层都没有回答本轮补的元问题：**项目自己的测试套件，对项目自己的源码，有多强的
检出能力？** 覆盖率是必要非充分条件——一行代码被"执行过"不等于其行为被断言；
一处 `>=` 写成 `>` 是否会被测试发现，覆盖率完全不回答。`mutation score`
（被变异体杀死比例）就是回答这个问题的标准工具。

**当前缺口**（本轮立项依据）：全仓 `mutation_score` 只出现在"LLM 测试 vs 任务
代码"的实验工件里，项目自身测试强度从未被量化；且既有 `_run_mutant_tests` 的
执行面是为模型测试设计的流水线（rc≠1 一律保守记"存活"），不能直接用来度量
自身套件——必须能区分"测试弱"与"测试没跑起来"。

## 2. 目标与非目标

**目标**

1. 提供零 LLM / 零网络的自身变异测试驱动器：任意 `src/` 文件 + 其专属测试 →
   逐变异体 killed/survived/invalid/timeout 计数 + mutation score 点估计；
2. 绝不污染工作树（临时副本隔离）、绝不因变异体死循环而挂死（killpg 超时）；
3. 产出可复算的 JSON + Markdown 报告（Python/主机/worker/样本量/测试命令/git
   sha 全记录）；支持 before/after 同一测试集合对比；
4. 用 3 个核心叶子工具模块跑出**真实基线**，并补测击杀可杀死的存活变异体；
5. 给出 Makefile / CI 接入片段（共享集成文件由 Lead 统一改）。

**非目标**

- 不替换覆盖率门禁：两者互补（覆盖率保"执行面"，变异测试保"断言面"）；
- 不做"全仓 × 全量变异体"的常跑：单变异体一次 pytest 启动 ~1.5–5s，全仓全量
  是小时级 CPU 成本，属于 nightly/季度审计而非每 PR 门禁（见 §10）；
- 不引入 mutmut 等外部依赖：复用仓内已有算子层，避免第二套变异语义口径。

## 3. 架构与数据流

```
CLI 参数
  │
  ├─ 生成：ExtendedMutationGenerator.generate(source)         （18 类 AST 单点算子）
  │     └─ 过滤生成器无效变异体（identity / syntax_error，§4.2）
  ├─ 抽样：按源码位置等距抽样（--max-mutants，§4.3）
  ├─ 测试集合：tests/test_<stem>*.py 自动发现 或 --test-map 冻结（§4.4）
  │
  ├─ 绿基线前置：每个模块先在副本上跑"未变异"测试，非绿默认阻断（§4.5）
  │
  └─ 并行执行（--workers N，默认 2）
       ├─ worker-0 独立 tempfile 副本 ──┐
       ├─ worker-1 独立 tempfile 副本 ──┤  每个变异体：
       └─ worker-k 独立 tempfile 副本 ──┘  写变异体 → pytest 子进程
                                            （nested_pytest_env 隔离宿主配置，
                                             run_with_timeout killpg 整树超时）
                                          → 还原原始字节
                                          → rc 分类（§4.6）
       │
       └─ 汇总：逐模块/逐类型计数 → JSON + Markdown 报告 → --fail-under 判定
```

## 4. 关键口径决策（每条回答"为什么"）

### 4.1 复用 `ExtendedMutationGenerator` 而非自研算子

- 该生成器已有 18 类算子（比较翻转/边界替换/布尔取反/语句删除/返回替换/
  异常路径/常量置换/算术互换/下标取反等）与 476 变异体规模的真实产出记录，
  口径与项目论文实验一致，分数可与其他批次对齐；
- 自研算子会产生第二套"变异语义"，两处口径漂移正是本仓反复治理过的问题
  （参见 `src/utils/env_utils.py` 的"单一事实源"治理动机）；
- 本工具只替换**目标**（项目自身源码）与**执行面**（项目自己的测试），
  生成语义零改动——变异算子层的缺陷（§4.2）在工具侧过滤并披露，不改共享文件。

### 4.2 生成器无效变异体：过滤而不是"记 survived"

2026-10-17 实测发现 `experiments/mutation_testing.py` 的 2 类假变异体：

| 类别 | 根因 | 现象 | 处置 |
| --- | --- | --- | --- |
| identity（语义恒等） | `_generate_numeric_offset` 对 Compare 中**非数值**常量（`None`/字符串）登记 "const None → +1"，但 `_offset_numeric` 只处理 int/float，实际零改动；`ast.unparse` 重排版后与源码 AST 逐节点相同 | 每模块各 1 个；跑测试必然存活 | 抽样前剔除，不计入分母 |
| syntax_error（语法非法） | `_gen_subscript_negate` 在 `helpers.py:468` 附近产出 unparse 后语法非法的代码（`[-:m.start(1) - ...]`） | 5 个；不可执行 | 抽样前剔除，不占用样本额度 |

**为什么必须剔除**：identity 变异体若计入分母，会把"生成器没真正变异"记成
"项目测试弱"，系统性压低 mutation score——这是指标污染而非测试缺陷。报告单列
`generator_filtered{identity,syntax_error}` 与 `executable_pool`，抽样率按
可执行池披露，不静默丢弃。

**上游修复已同批落地（2026-10-17 17:18）**：`experiments/mutation_testing.py` 的 K 轮修复为 `_generate_numeric_offset` 增加"仅数值常量才登记"判据、为扩展算子 `_emit` 增加 `ast.parse(new_code)` 语法自检与 AST identity 判据（该文件属共享集成面，不在 WP-A 写范围，由 Lead 批次处理）。用修复后的生成器复跑（§7）实测 `generator_filtered=0/0`；本工具侧过滤逻辑**保留为回归防线**——上游若回退，报告会重新命中并显式计数（§10 第 2 条）。

### 4.3 抽样：等距、确定性、披露

- `--max-mutants` 默认 120/文件；按 (行号, 类型, 描述) 排序后**等距抽样**：
  保持源码空间分布与类型比例的近似无偏，且无随机种子（同一源码 + 同一上限
  必然同结果，before/after 可逐 ID 对账）；
- 不采用"类型轮转"取样：轮转会把大类型（如 `stmt_delete`）压到与稀有类型
  同等少量，分数方差更大；等距抽样更接近全量口径；
- 报告披露"生成数 / 剔除数 / 可执行池 / 抽样执行数"，**抽样分数不得写成
  全量 mutation score**（本次 helpers 模块为 120/468 ≈ 25.6% 抽样）。

### 4.4 临时副本隔离：绝不原地变异

- 每个 worker 持有一份独立副本（`src/` 全树 + `config.py` + `pyproject.toml` +
  `tests/conftest.py` + 目标测试文件），变异体只写副本；
- 每个变异体运行前写入、运行后立刻用内存中的原始字节还原；还原放在 `finally`，
  子进程异常/超时/中断都不会把变异体留在副本里；
- **为什么不"原地改再还原"**：任何崩溃/超时都会把变异体留在工作树，且并发
  worker 会互相看到对方的变异——副本隔离让测量污染在结构上不可能发生。
  `tests/test_self_mutation_tool.py` 用字节级断言锁定"工作树零改动"契约。

### 4.5 green baseline 前置校验

正式执行前，在副本上跑一遍**未变异**测试命令：

- 测试套件本身红着时，任何变异体的 rc=1 都可能是既有失败而非"被杀死"，
  分数会全部虚增；
- baseline 不绿 → 默认中止（退出码 2，打印失败输出尾部与处理建议）；
  确需在红基线上继续须显式 `--allow-red-baseline`，报告标记
  `measurement_valid=false`。

### 4.6 rc 分类：invalid 单列，不进分母

| 子进程结果 | 分类 | 理由 |
| --- | --- | --- |
| rc == 1（pytest TESTS_FAILED） | killed | 测试跑起来了且捕获了变异 |
| rc == 0（全部通过） | survived | 测试未能捕获 |
| rc == 2/3/4/5 | invalid | 收集中断/内部错误/用法错误/没收集到测试——套件没成功运行 |
| 超时（run_with_timeout timed_out） | timeout（invalid 子类） | 单独计数以暴露"测试会被变异体拖死"的风险面 |

**与 `experiments/mutation_testing._run_mutant_tests` 的保守口径刻意不同**：
那里为 LLM 测试打分，rc≠1 一律记存活（宁低估）；这里是度量项目自身测试强度，
必须显式区分"测试弱"与"测试没跑起来"——把收集错误算成存活会低估分数，算成
杀死会虚增分数，两种都会让指标失去鉴别力。

### 4.7 子进程超时：`run_with_timeout` 的 killpg 语义

变异体可能让测试陷入死循环。`subprocess.run(timeout=)` 只 kill **直接子进程**，
pytest 孙进程持有管道写端会让父进程在 `communicate()` 等 EOF 时**永久阻塞**
（根因与实跑复现记录见 `src/utils/process_utils.py` 模块 docstring 与
`experiments/mutation_testing._run_mutant_tests` 注释）。本工具统一用
`run_with_timeout`：`start_new_session` + `killpg(SIGKILL)` 整树终止 +
文件后端收口，保证函数一定返回；超时按上表记 invalid。

### 4.8 测试集合发现与冻结

- 默认发现规则：`tests/test_<module_stem>.py` 精确优先；否则
  `tests/test_<module_stem>_*.py` 全族（如 helpers 的 property/robustness/
  fence 三件套）；都没有则**报错要求 `--test-map`**——不把几十个文件拖进每个
  变异体，也不"瞎猜"；
- `--test-map MODULE=test1,test2`（可重复）用于**冻结**测试集合：
  before/after 必须同一集合，否则"分数提升"可能只是多挂了一个测试文件；
  击杀存活变异体时把新测试文件追加进映射（本批 `tests/test_self_mutation_targets.py`）；
- 报告记录测试文件路径 + sha256 快照，复跑时可核对集合是否漂移。

## 5. CLI 参考

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--files` | 3 个核心模块 | 逗号分隔目标源码（仓库根相对） |
| `--max-mutants` | 120 | 每文件最多执行变异体数（等距抽样；0=全量） |
| `--workers` | 2 | 并行 worker 数（每个一份独立副本，1..8） |
| `--timeout-per-mutant` | 60.0 | 单变异体超时秒数（超时 killpg 整树终止） |
| `--test-command` | `{python} -m pytest {test_files} -q --tb=no -x -p no:cacheprovider -o addopts=` | 命令模板，必须含 `{test_files}` |
| `--test-map` | 空 | `MODULE=tests/a.py,...`，冻结测试集合（可重复） |
| `--json-out` / `--md-out` | `experiments/results/self_mutation_20261017/self_mutation_report.{json,md}` | 报告输出 |
| `--dry-run` | 关 | 只生成清单/报告，零子进程（与 `--fail-under` 互斥） |
| `--fail-under` | 无 | mutation score 低于阈值 → 退出码 1（CI 口径） |
| `--allow-red-baseline` | 关 | 红基线放行（报告标记 measurement_valid=false） |
| `-q/--quiet`、`-v/--verbose` | 互斥 | 输出粒度 |
| `--keep-sandbox` | 关 | 保留 tempfile 副本（调试用） |

退出码：0 正常；1 `--fail-under` 未达标；2 用法/环境错误（文件缺失、
baseline 非绿未放行、测试发现失败等）。

## 6. 报告 schema

JSON（机器可读事实源）顶层：`schema_version` / `tool` / `mode` /
`generated_at` / `duration_seconds` / `environment`（主机/Python/pytest）/
`git`（sha/dirty）/ `config`（worker/超时/样本上限/抽样方式/测试命令/复现命令）/
`summary`（总计数、有效分母、mutation score、generator_filtered、baseline_green、
measurement_valid）/ `modules[]`。

逐模块：`source_sha256` / `test_files` + `test_files_sha256` / `baseline` /
`total_generated_mutants` / `generator_filtered` / `executable_pool` /
`sampled_mutants` / `samples`（killed/survived/invalid/timeout）/ `mutation_score` /
`by_type` / `mutants[]`（逐变异体 ID、行号、类型、描述、code sha256、outcome、
rc、duration、invalid 归因）。

Markdown 是同一事实源的人读镜像：测量口径、运行环境、总览表（含过滤/可执行池/
抽样率）、逐模块明细（by-type 表 + 存活清单 + invalid/timeout 归因）、复现命令。

报告目录 `experiments/results/` 属"数据非代码"（ruff 排除、gitignore）；如要
入库需 `git add -f`，由 Lead 决定。

## 7. 实测基线（2026-10-17，命令见 §11）

### 7.1 方法与环境

- 命令：`.venv/bin/python scripts/tools/self_mutation.py --files src/utils/env_utils.py,src/utils/helpers.py,src/utils/atomic_io.py --workers 2 --max-mutants 120`
  （默认报告落点，报告 `generated_at=2026-10-17T17:30:33+0800`）；
- 环境：macOS-27.0.1 / arm64 / 10 核；CPython 3.14.6；pytest 9.1.1；git
  `362bf02`，`dirty=true`（工作树有 82 个并行批次的未提交变更；报告记录 sha 快照，
  分数只对应本次工作树状态）；
- 变异体：ExtendedMutationGenerator 生成 572 个；**工具侧生成器无效过滤命中 0**
  （§4.2 的两类假变异体已在同批上游修复，见 §4.2 末注）→ 可执行池 572；
- 抽样：env_utils 83/83（全量）、atomic_io 21/21（全量）、helpers 120/468
  （**25.6% 抽样，`--max-mutants 120` 等距抽样**）→ 共执行 224 个；
- 每变异体超时 60s；green baseline 三模块全绿；总耗时 315.5s（与另一
  agent 的全量覆盖率跑并行，CPU 竞争使耗时偏高，不影响计数口径）。

### 7.2 基线结果（报告 `self_mutation_report.json`）

| 模块 | 生成 | 剔除(恒等/语法) | 可执行池 | 抽样执行 | killed | survived | invalid | timeout | mutation score |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `src/utils/env_utils.py` | 83 | 0/0 | 83 | 83 | 67 | 8 | 8 | 0 | **0.8933** |
| `src/utils/helpers.py` | 468 | 0/0 | 468 | 120（25.6%） | 63 | 56 | 0 | 1 | **0.5294** |
| `src/utils/atomic_io.py` | 21 | 0/0 | 21 | 21 | 8 | 13 | 0 | 0 | **0.3810** |
| **合计** | 572 | 0/0 | 572 | 224 | 138 | 77 | 8 | 1 | **0.6419** |

有效分母 = killed + survived = 138 + 77 = **215**；`baseline_green=true`，
`measurement_valid=true`。

**invalid / timeout 归因（不进分母）**：

- env_utils 的 8 个 invalid 全部是 rc=4：变异体破坏 `env_flag`/`env_int` 后，
  `config.py` 在 **import 期**调用这些函数（`DOCKER_ENABLED = env_flag(...)` 等），
  而测试套件的 `tests/conftest.py` import `config` → 收集阶段直接崩溃。这是
  "套件根本没成功运行"，按 §4.6 口径记 invalid（既不算测试弱、也不算检测成功）。
- helpers 的 1 个 timeout（`aug_assign_swap`，line 512）让测试陷入 >60s 死循环，
  `run_with_timeout` killpg 整树终止后记 timeout——正是 §4.7 要防御的场景。

### 7.3 分数解读（避免误读）

- **atomic_io 0.3810 不是"测试差"的直接结论**：其测试锁定的是"写入完整性 /
  os.replace 原子性 / 并发不半写"三类**外部契约**，而存活变异体集中在临时文件
  命名、fd 初始值、死代码等内部面；其中 5 个后续被归因为实践等价（§8.3）。
- **helpers 0.5294 是抽样分数**（120/468，25.6%），不可写作全量 mutation score；
  该模块是 LLM 输出修复链，按设计包含大量"防御畸形输入"的冗余守卫，存活面多在
  这些守卫上（§8.3 的 3.3/3.4 类）。
- 总分数 0.6419 是**加权（按有效变异体数）点估计**，未给置信区间；由于抽样
  确定性（§4.3），同一工作树重跑应得到同一变异体集合与同一计数（测试确定性
  前提下）。

## 8. 击杀存活变异体（第 2 轮）

### 8.1 方法

- 从 §7 基线报告导出 77 个 survived，用"canonical AST diff + 100 组公开 API 差分探测"
  判断哪些存活变异体有**公开可观测差异**；对可杀者写行为契约测试到新文件
  `tests/test_self_mutation_targets.py`（不改任何既有测试）；
- 每个候选击杀先做"单变异体 × 目标测试集合"沙箱预验证（`rc==1`），再进入正式复跑；
- 复跑用 `--test-map` **冻结与基线相同的测试集合**并追加新文件（§11 命令 2），
  保证 before/after 只差一个测试文件、变异体 ID 集合逐项相同（224/224 对账一致）。
  注意：基线报告是在 after 复跑之后用**同一生成器快照**重跑的（报告 `generated_at`
  先后不代表语义顺序）；否则生成器修复前后的变异体池不同、分数不可比。

### 8.2 结果（报告 `self_mutation_after.json`）

| 模块 | before K/S | before score | after K/S | after score | Δ score |
| --- | ---: | ---: | ---: | ---: | ---: |
| `src/utils/env_utils.py` | 67/8 | 0.8933 | 71/4 | 0.9467 | +0.0534 |
| `src/utils/helpers.py` | 63/56 | 0.5294 | 77/42 | 0.6471 | +0.1177 |
| `src/utils/atomic_io.py` | 8/13 | 0.3810 | 17/4 | 0.8095 | +0.4285 |
| **合计** | 138/77 | **0.6419** | 165/50 | **0.7674** | **+0.1255** |

- 有效分母不变（215）；invalid 8 / timeout 1 不变（不进分母）；
- 共 **27 个 survived→killed**（无反向翻转），逐变异体到击杀测试的映射见
  `（工件已清除）` §2；
- 击杀测试文件 `tests/test_self_mutation_targets.py` 在**未变异代码**上全绿
  （与 `tests/test_self_mutation_tool.py` 合计 58 例，`-n 2` 通过），
  且全部 28 个候选击杀在预验证阶段实测 `rc==1`。

### 8.3 剩余 50 个存活变异体归因（详见 `survivor_attribution.md`）

| 类别 | 数量 | 说明 |
| --- | ---: | --- |
| 可证明等价（annotation-only） | 5 | 注解在 `from __future__ import annotations` 下从未求值 |
| 强证据实践等价 | 17 | 死代码/冗余防御/快路径兜底/表示层转义差异，机制可解释且差分探测零差异 |
| 公开契约外（内部异常/诊断） | 5 | 私有求值器异常类型/消息/诊断字段，公开契约只承诺 JSONDecodeError |
| 待补（未构造出可观测差异） | 23 | 防御性字符串感知/叶子回退/表达式求值守卫；**不声称等价**，后续可补 |

**结论**：本批把 3 模块合计 mutation score 从 **0.6419 提升到 0.7674**（+0.1255，
相对提升 19.6%）；剩余存活的 50 个中 22 个有等价性证据、5 个属公开契约外内部细节、
23 个是尚未构造出可杀输入的防御分支——不把等价变异体当测试缺陷，也不硬杀内部细节。

## 9. Makefile / CI 接入片段（共享文件由 Lead 统一修改）

```makefile
# 自身变异测试（WP-A，2026-10-17）：3 个核心工具模块的测试强度点估计。
# 默认抽样口径（每文件 120 个变异体、2 worker），完整报告落
# experiments/results/self_mutation_20261017/；本地跑约 6-10 分钟（CPU 相关）。
self-mutation:  ## 自身测试套件变异测试（默认 3 模块 × 每文件 120 变异体）
	$(PY) scripts/tools/self_mutation.py --workers 2

self-mutation-ci:  ## 自身变异测试 CI 口径（阈值门禁 + 只跑稳定模块）
	$(PY) scripts/tools/self_mutation.py --files src/utils/env_utils.py,src/utils/atomic_io.py \
		--workers 2 --max-mutants 60 --fail-under 0.85 \
		--json-out experiments/results/self_mutation_ci.json \
		--md-out experiments/results/self_mutation_ci.md
```

CI 建议（`.github/workflows/ci.yml`，放在 3.14 档 matrix 的独立 step 或
独立 job，**不与覆盖率全量跑重叠**）：

```yaml
      - name: Self-mutation (test strength, WP-A)
        # 只跑轻依赖叶子模块：单变异体 pytest 启动 ~1-3s，2 worker 约 2-4 分钟。
        # 阈值 0.85 基于 2026-10-17 实测基线（env_utils 0.89、atomic_io 0.37→期望
        # 击杀后 >=0.60；实际门禁见下），不达标阻断并输出报告工件。
        run: |
          python scripts/tools/self_mutation.py \
            --files src/utils/env_utils.py,src/utils/atomic_io.py \
            --workers 2 --max-mutants 60 --fail-under 0.85 \
            --json-out experiments/results/self_mutation_ci.json \
            --md-out experiments/results/self_mutation_ci.md
      - name: Upload self-mutation report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: self-mutation-report
          path: experiments/results/self_mutation_ci.*
```

> 注：阈值/模块清单需按 §7 实测分数与 CI 机器负载校准；`--max-mutants 60`
> 是本批成本-收益折中（2 worker 约 2-4 分钟），追求更低方差可在 nightly 用
> `--max-mutants 0` 全量跑 helpers。

### 9.1 2026-10-25（CQ 轮）：weekly 作业"上线即红"的归因与口径修正

- **现象**：`mutation.yml` 自 2026-10-19 首次运行即失败，此后每周红（阈值步 rc=1），
  full patrol（report-only）全绿——**红的是阈值步，不是工具本身**。
- **本地按作业原样复现**：env_utils **40/55 = 0.7273**、atomic_io **16/20 = 0.8000**，
  合计 **0.7467 < 0.85**（与 CI 同一命令、同一 test-map）。
- **根因**：`postprocess_warn_seconds`（2026-10-18 Q-3 新增）**没有任何测试落在
  `--test-map` 的映射面里**——自动发现只匹配 `test_<stem>.py`，新函数的测试若放在
  别的文件名下，门禁永远看不见。env 的 15 个存活体里 10 个落在该函数（含它读取的
  env 名常量）。
- **处置**：`tests/test_env_utils.py` 补 12 例口径表（未设置 / 空串 / 全空白 / 非数值 /
  NaN / ±inf / ≤0 / 合法值含亚秒 / 调用方 `default` / env 名字面量），
  `tests/test_atomic_io.py` 补 3 例（相对路径回落 cwd / `fd == 0` 关闭边界 /
  mkstemp 失败不关哨兵 fd）。复测：env **50/55 = 0.9091**、atomic **18/20 = 0.9000**，
  合计 **68/75 = 0.9067**，gate rc=0。**阈值未动**。
- **剩余 7 个存活体**：3 个可证明等价（`os.path.dirname(os.path.abspath(...)) or "."`
  的 `"."` 在 abspath 语义下不可达；对已存在的 fd 而言 `os.fdopen(fd, "x")` 与 `"w"`
  语义相同——本机实测写出成功，故这两个常量变异不可杀）；其余 4 个是 tuple 字面量
  上的索引类变异，报告已披露、**未声称等价**。
- **两条教训**：① **"上线即红"的定时作业最容易被当成噪声**——`perf.yml`（连续三次）
  与 `mutation.yml`（首次即红）是同一形状，判据是"有没有人看过红的原因"；
  ② **固定阈值下的红，先归因到"哪个函数的测试没进门禁的映射面"，再谈阈值**——
  直接调低阈值会把"新函数没有测试"永久合法化。

## 10. 已知局限与后续

1. **抽样分数非常量口径**：`--max-mutants` 小于可执行池时报告的是抽样点估计，
   不是全量 mutation score；报告已披露生成/过滤/可执行池/抽样数与抽样方式。
2. **生成器缺陷：已上游修复，工具过滤器保留为回归防线**（§4.2）：identity 与
   syntax_error 变异体问题由 K 轮修复在 `experiments/mutation_testing.py` 同批修掉
   （`_generate_numeric_offset` 仅数值常量才登记 + `_emit` 增加 `ast.parse` 语法自检
   与 AST identity 判据）；本批复跑过滤计数为 0。若未来上游回退，本工具会重新命中
   并在报告 `generator_filtered` 中显式计数（不静默丢弃）。
3. **等价变异体不可杀**：annotation-only（`from __future__ import annotations`
   下注解除引用）等变异体行为恒等，硬杀只会写入无意义断言污染测试套件；本批
   逐个归因、数量单独披露（§8）。
4. **invalid 需持续监控**：env_utils 的 8 个 invalid 来自"变异体破坏
   `config.py` import 期 `env_flag` 调用 → conftest 导入链崩溃 rc=4"。这是
   副本隔离真实存在的结构效应（测试套件依赖 `config.py` 在 import 期调用工具
   函数）；invalid 比例上升意味着评测环境/依赖链变化，需重新审视口径。
5. **单变异体 pytest 启动成本高**：每个变异体至少一次解释器+pytest 启动
   （~1.5–5s），无法像覆盖率一样每 PR 全仓跑；建议 CI 只跑轻量叶子模块、
   全量放 nightly/季度审计，并关注 `--workers` 与共享 CPU 的竞争（CPU 竞争
   可能把"应被杀死"拖成 timeout → 记 invalid，不虚报分数但降低有效样本）。
6. **测试发现启发式**：只按命名约定发现专属测试；跨模块契约（如
   `tests/test_venv_cache_monitoring.py` 依赖 atomic_io 临时命名）需 `--test-map`
   显式纳入，否则该契约不在观测面内。

## 11. 复现命令与工件清单

```bash
# 1) 基线（默认 3 模块 / 2 worker / 每文件 120 上限；报告落默认路径）
.venv/bin/python scripts/tools/self_mutation.py \
  --files src/utils/env_utils.py,src/utils/helpers.py,src/utils/atomic_io.py --workers 2

# 2) 击杀存活变异体后的 after 复跑（冻结 before 同一测试集合 + 追加击杀测试文件）
.venv/bin/python scripts/tools/self_mutation.py \
  --files src/utils/env_utils.py,src/utils/helpers.py,src/utils/atomic_io.py --workers 2 \
  --test-map src/utils/env_utils.py=tests/test_env_utils.py,tests/test_self_mutation_targets.py \
  --test-map src/utils/helpers.py=tests/test_helpers_json_property.py,tests/test_helpers_json_robustness.py,tests/test_helpers_json_fence_content.py,tests/test_self_mutation_targets.py \
  --test-map src/utils/atomic_io.py=tests/test_atomic_io.py,tests/test_self_mutation_targets.py \
  --json-out experiments/results/self_mutation_20261017/self_mutation_after.json \
  --md-out experiments/results/self_mutation_20261017/self_mutation_after.md

# 3) 工具自身单测 + 击杀测试单测（pristine 代码上必须全绿）
.venv/bin/python -m pytest tests/test_self_mutation_tool.py tests/test_self_mutation_targets.py -q
```

工件清单（`（工件已清除）`，gitignore 数据目录）：

| 文件 | 内容 |
| --- | --- |
| `self_mutation_report.json` / `.md` | 击杀前基线（默认命令产物；与 after 同生成器快照，224/224 ID 对账一致） |
| `self_mutation_after.json` / `.md` | 击杀后复跑（同一 target 集合 + 新测试） |
| `survivor_attribution.md` | 未击杀存活变异体逐条归因（等价/不可杀） |
