# 项目状态与决策登记册（Status & Decision Register）

- 最后更新：2026-10-17（K 轮全面优化：JSON 围栏内容篡改修复〔P0〕/ 覆盖率收口 96.47% 行 + 92.57% 分支 / 自身测试套件变异测试基线（0.6419→0.7674）/ 变异生成器无效变异体修复〔测量伪影第⑤起〕/ G16 文档链接门禁 + INDEX / 孤儿进程巡检 / 性能基准扩展 / 本地 gates 补口；J 轮收口（J-1b/J-2/J-3/J-4/A-19）与 df_spec 实验判定 `not_confirmed` 同日落地；§1 快照随 `BASELINE.yaml` 同步至当日终态）
- **自我对账**：本册的覆盖率声明由 `scripts/gates/check_artifact_doc_consistency.py`
  的 `check_status_register()` 与 `coverage.xml` 实测对账——数字实质性错报即 CI 红，
  因此本册不允许手工美化。对账口径 = **锚定 §1 声明行 + ±0.10pp 容差**（见下）。
  > G6（2026-10-16）勘误一：上述"CI 红"在本轮之前**并不成立**——该步骤排在 CI 里
  > 生成 `coverage.xml` 的测试步骤之前约 90 行，产物必然缺席，函数返回空清单后
  > 调用方打印 `[OK] …（无 coverage.xml 时跳过）`，即"从未对过账"被读作"对账通过"。
  > 现已把强制支路移入覆盖率集群（`Status register coverage reconciliation` 步骤，
  > 3.14 档，`--require-coverage`：产物缺席即失败），缺席与通过不再同形。
  > G6（2026-10-16）勘误二：原口径"实测值的两位小数字符串出现在全文任意位置"
  > **既漏又不可满足**——漏：正文任何角落（历史勘误、别的指标）凑巧出现该数字就算
  > 通过；不可满足：**本仓库的覆盖率测量自带非确定性**，同一份源码连跑多次全量，
  > 分支覆盖分别是 5460/6236=87.56% 与 5459/6236=87.54%（单分支 0.016pp），
  > `graph/nodes.py` 行覆盖分别是 0.7776 与 0.7862（约 6 行 → 总行覆盖 0.035pp）。
  > 逐位相等只会把"常年假绿"换成"随机真红"。故改为锚定 `| 总行覆盖 | **NN.NN%** |` /
  > `| 总分支覆盖 | **NN.NN%** |` 两行 + **±0.10pp** 容差（≈观测抖动上界的 2 倍），
  > 声明行缺失按**不通过**处置。
  > 容差不是放松：**防回退由 `coverage_ratchet.py` 的只升水位独立把守**，本检查的
  > 职责是"文档不得实质性错报工件"；要骗过 ±0.10pp，谎报幅度必须小于测量噪声
  > （声称 95% 而实测 92.9% 依然立刻转红），那种谎报既不划算也改变不了任何结论。
  > **H 轮（2026-10-16）追加：勘误二的前提已失效，但结论仍成立。** 上述"覆盖率测量
  > 自带非确定性"已被三处修复完全消除（见 §3.2 H1/H5/H6 与 §4 已收口条目）——连跑
  > 两次全量的 `coverage.xml` 逐行逐分支比对**零漂移**。所以 ±0.10pp 现在**偏宽**；
  > 本轮**不收紧**（防回退不靠容差；且 ubuntu 档尚未观测，贸然收紧有把"常年假绿"
  > 换成"随机真红"的风险），登记为口径精修项（§4）。注意本检查的**判据本身不受影响**：
  > 锚定声明行 + 容差 + 声明行缺失即不通过，三条都仍然生效。
- 用途：把多轮优化中的"**已完成 / 遗留 / 阻断**"三类状态收敛到一份可核验清单。
  每一项都给出**验证入口**（命令或门禁），使"文档说做了"必须能被复跑证实——
  本项目既往的失分形态正是"文档与工件静默分裂"，本册即是该纪律的交接面。
- 阅读顺序建议：§1 现状快照 → §2 阻断项与解锁路径 → §3 已完成事项（含验证入口）
  → §4 遗留缺口 → §5 口径与术语纪律。

## 1. 现状快照（2026-10-17 K 轮全面优化批次实测，CI 同口径）

| 维度 | 数值 | 验证入口 |
|---|---|---|
| 全量测试 | **7530 passed / 5 skipped / 0 failed**（登记口径 = collected 7535 − skipped 5；2026-10-17 本机实跑 162.60s：7527 passed / 5 skipped / 3 failed，3 failed 全为**文档对账门禁自指**——① `TestBaselineNumbersConsistency`（随 BASELINE 刷新转绿）② `artifact_doc_consistency` 端到端 ×2（随本 §1 刷新转绿）；本轮净增 **358** 例 = 覆盖率收口 155 + self-mutation 58 + 文档链接门禁 47 + 生成器有效性 16 + 孤儿进程巡检 32 + preflight 6 + 性能基准扩展 10 + 反引号内容回归 29 + A-19 臂 5，零代码回归） | `pytest tests/ -q -n 4 --dist loadfile` |
| 总行覆盖 | **96.47%**（16369/16968；K 轮 10 个 `test_closeout_k_*.py`（155 例）补口 18 个文件：debugger 76 / base_agent 40 / api_manager 29 / llm_client 23 / multi_candidate 21 / cli-app 18 / workflow 16 / error_classifier 16 等；ratchet 水位 94.60 → **96.4**，余量 +0.07pp） | `make test-cov` + `scripts/gates/coverage_ratchet.py --check` |
| 总分支覆盖 | **92.57%**（5782/6246；+149 弧来自 18 个文件缺失分支补口：debugger 42→8 / api_manager 22→5 / llm_client 10→1 / error_classifier 10→4 / fault_localizer 6→0 等；水位 90.30 → **92.5**，余量 +0.07pp） | 同上（`--cov-branch`） |
| 静态硬下限覆盖 | 达标（行 ≥85% / 分支总 ≥77% / 核心路由 ≥85–90%） | `scripts/gates/check_branch_coverage.py coverage.xml` |
| 门禁总数 | **25 道全绿**（口径 = `ci.yml` 主工作流**逐提交阻断的门禁检查步骤**，不含测试执行本身；可枚举复算）【K 轮 2026-10-17：① 新增 G16 文档链接完整性门禁（24→25，109 文件/528 链接/0 错误）；② 实测发现 U3 零断言门禁**长期只在 CI、不在本地 `make gates` 链**——HEAD（fde68ae）实际带 1 例零断言违规（`test_class_method_not_confused_with_top_level`，`if ok:` 分支从不执行），即"本地全绿≠CI 绿"再次复现，已把该门补入本地 gates 并修复违规（现 0 违规）；`scripts/gates/` 目录现为 26 脚本（CI 接入 24 项），主工作流阻断检查步骤实为 25】 | `make gates`；逐项见 §3 |
| 静态检查 | ruff 全绿 / **744** 文件已格式化 / mypy 0 错（133 源文件） | `ruff check .`、`ruff format --check .`、`mypy src/ config.py` |
| 构建基线 | `BASELINE.yaml` 与实测逐位对账（含守卫 `TestBaselineNumbersConsistency`） | `pytest tests/test_2026_10_10_optimization_batch.py -q` |

> 一致性提示：**任何一项数值漂移都会让对应门禁转红**。K 轮收口后覆盖率余量仍薄（行 +0.07pp、
> 分支 +0.07pp），因此本表不允许手工维护——它必须随 `BASELINE.yaml` 同步刷新。
> **K 轮新增元层指标**：`BASELINE.yaml` 新增 `self_mutation` 节（项目自身测试套件变异强度），
> 与 `target_quality.mutation_score`（LLM 测试 × 任务代码）**口径不同、禁止混引**。
> **G 轮登记的"覆盖率测量非确定性"已在 H 轮完全收口，I 轮复核仍成立**：三处独立噪声源
> 逐个定位并消除（H1 `config` import 期 env 注入 + 测试侧还原清单过期 / H5 SpecExpr 晚期
> parse 门只有模糊测试碰运气才命中 / H6 `get_manager` 双重检查锁的竞态弧），I 轮改动落地后
> 再连跑两次 CI 口径全量，`coverage.xml` **逐行逐分支比对零漂移**（16941 行 + 3118 分支点
> 全同；行 15748/16941=92.9579%、分支 5464/6236=87.6203% 两次逐位相同）。
> 因此 G6 为"含噪声观测"定的 **±0.10pp** 对账容差现已**偏宽**——I 轮**仍不收紧**：容差
> 不是防回退机制（那由 `coverage_ratchet.py` 的只升水位独立把守），且收紧需要多轮干净
> 复跑重测抖动上界（ubuntu 档尚未观测），收益仅为口径精修。登记为下轮可做项（见 §4）。
> ⚠️ 覆盖率**数值变动不等于能力变动**：H 轮的 `nodes.py` 未覆盖 +6 行、总分支 5459→5458，
> 成因是"测试不再因 env 残留而**意外**走进档位开启分支"，即测量变准（详见 §4）。I 轮的
> 行 +9 / 分支 +6 已**逐文件完整归因**（`nodes.py` +4/+4、`failure_taxonomy.py` +2/+2、
> `state.py` +1/+1、`planner.py` +0/+2——最后一项是**存量漏测被新测试收复**，见 §3.2 I2）。

## 2. 阻断项与解锁路径（需要人决策/授权，代码侧已就绪）

| # | 阻断项 | 类型 | 解锁路径（已就绪的前置件） | 解锁后的收益 |
|---|---|---|---|---|
| B1 | 2×2 消融（协议文本开关 × 再生成预算） | **LLM 配额** | 双开关已具备、零新代码；跑前设 `COST_BUDGET_ENABLE=true`、`AITESTER_BATCH_MAX_CALLS≥1684`、`AITESTER_RUN_PREFLIGHT=true`，并在**干净树**上跑 | 把"+43pp 归因于 instruction artifact"从**协议包效应**钉成**文本效应**（PROMPT-SE 最想看的一张表） |
| B2 | 锁指纹重跑主批次（261 任务 × 3 臂） | **LLM 配额** | 同上；新批次须带 `model_fingerprint.pinned=true`（近 5 个批次已实测均为 true） | 关掉"头条批次 10/10 `git_dirty=true`、0/10 有指纹"这一复现性缺口 |
| B3 | SWE-bench Lite 重跑 | **LLM 配额** | 配额闸已补（`AITESTER_BATCH_MAX_CALLS`）；`make preflight --strict` 会阻断未配置状态 | 把 `not_evaluated` 变成有效能力结论（当前严禁引用其 `pass_rate`） |
| B4 | E7 人工复核 | **人力** | 协议已可执行（抽样框/五选一量表/双人独立/Cohen's κ）：`docs/HUMAN_ADJUDICATION_PROTOCOL.md`；**预注册口径 = `ceil(10%/层)` → 当前 72 行单层为 8 行**（"≥40 行"是优化记录里的建议口径，二者冲突已在协议文档登记） | 给 `detection_rate` 一个**人类外部校标**（构念效度从 `open` 转 `reduced`） |
| B5 | Prompt Card + 哈希锁 | **清单/哈希锁已就绪；文本已呈交目检（2026-10-16）** | detection-first 段落现内联于 `src/graph/nodes.py:549-556`、over-red 于 `:660-676`（G 轮 `nodes.py` 插入 G3 抬升块后行号整体下移，已按实测校正；**行号非哈希锁口径**——`PROMPT_ARTIFACTS.json` 只锁 id/sha256/行数，故文本改动会被门禁抓住，行号漂移不会）；7 个 JSON 契约调用点已由门禁固定（口径 A=7） | 满足 PROMPT-SE "instruction artifacts as first-class objects" 的复现要求 |
| B6 | `success` 呈现层降级 | ✅ **已执行（2026-10-16，8c2b655）** | 三指标落图表/表格/显著性基口径：主图四联（检出/假修复/成功率*/覆盖率）；表列 Detection/False-Fix/Repair 前置；显著性基口径 detection（旧批次回退 passed 并标注） | "三指标并列"从文字落到图表，图表与声明一致 |
| B7 | 原始 LLM 响应归档 | **存储/合规决策** | 现状：`traces/*.trace.jsonl` 只存结构化事件，**不含原始响应**（故无法量化单引号 JSON 发生率，也无法完整离线重放生成） | 提升 Open Science 的 Complete/Exercisable 等级 |
| B8 | A-19 覆盖率停滞检测**开/关消融批次** | **LLM 配额** | 臂已就绪（`experiments/run_benchmark.py --enable-stagnation / --no-stagnation`，写 `COVERAGE_STALL_DETECT_ENABLE` 即全链路生效、provenance 可复核；两臂互斥 fail fast，5 例映射测试）。跑批前置同 B1/B2（干净树 + 批次配额 + 指纹） | 把"停滞检测是否真提升收敛"从组件在场变成**消融证据**（A-19 出口判据） |

## 3. 已完成事项（按主题，含验证入口）

### 3.1 论文/投稿材料侧

| 事项 | 交付物 | 验证入口 |
|---|---|---|
| 声明→证据→范围对账表（11 条声明含 2 条 `contradicted`） | `docs/EVALUATION_SCOPE.md` | 人工阅读；数字可用 `make mutation-det-correlation` 等复算 |
| 结构化效度威胁专章（四类 × open/reduced/mitigated + 5 个 OPEN 项处置） | `docs/VALIDITY.md` + `.en.md` | `scripts/gates/check_bilingual_docs.py --strict` |
| 四起测量伪影方法学章（口径分叉审计） | `docs/MEASUREMENT_INTEGRITY.md` | 各 ADR + `make repair-replay` / `make corrected-metrics` |
| E7 人工裁决可执行协议 | `docs/HUMAN_ADJUDICATION_PROTOCOL.md` | 与 `docs/preregistration.md` E7 节比对 |
| 复现包说明（环境/模型设置/数据/零 LLM 复算/含 LLM 路径/已知偏差） | `REPLICATION.md` | 按其 §4 逐条执行零 LLM 目标 |
| 数据可用性声明 | `docs/DATA_CARD.md` §6 + `.en.md` | `check_bilingual_docs` + `check_baseline_numbers` |
| 覆盖率棘轮偏差"关闭记录"（16 批轨迹） | `docs/COVERAGE_RATCHET_DEVIATION.md` | `coverage_ratchet --check` 全绿 |
| 通过率混淆敏感性分析（成功声明率 + 条件口径 + 模板匹配子集） | `experiments/pass_matched_sensitivity.py`；工件 `PASS_MATCHED.{md,json}` | `make pass-matched` |
| MDE/功效 + 比例型端点 bootstrap CI + 成本分布 | `experiments/emse_stats_report.py`；工件 `emse_stats_report.{md,json}` | `make emse-stats` |

### 3.2 代码/实验/工程侧

| 事项 | 交付物 | 验证入口 |
|---|---|---|
| SWE-bench 限流信号计数口径修复（旧口径漏计 `issues`） | `experiments/emse_optimization.py::swebench_infra_facts` + `signal_breakdown` | `pytest tests/test_emse_optimization.py -q`；`make swebench-disclosure` |
| false-fix 复算分支可达性修复（stale 日期过滤导致永不触发） | `experiments/emse_optimization.py::_load_main_batch_rows` | 同上（`source` 断言为 `main_batch_artifact`） |
| false-fix 边际分母语义修复（改为"被度量指标可测"） | `experiments/emse_optimization.py::false_fix_caliber` | 同上（59.58% / 100% 逐位复算） |
| `parse_coverage` 两处缺陷修复（小写 `total` 回退失效、`TOTAL 85%` 截断为 5.0） | `src/agents/executor_output.py` | `pytest tests/test_small_gaps_closeout.py -q` |
| 一致性门禁"静默零"守卫（解析出 0 行不得当事实） | `scripts/gates/check_artifact_doc_consistency.py` | `make artifact-doc-consistency` |
| 批次跑批前置闸（配额/指纹/工作树，未配置 ≠ 无限） | `src/budget/batch_quota.py` + `scripts/tools/run_preflight.py` | `make preflight`（strict 语义） |
| T-10 声明对账（严格口径 29 行/25 可测 必须显式声明） | 同上门禁的 `check_t10_docs` | `make artifact-doc-consistency` |
| 引用可追溯性清零（3 处仓外数字改显式未核验 + allowlist 登记） | `docs/citation_allowlist.txt` §5 | `scripts/gates/check_citations.py --traceability` |
| 覆盖率收口（92.07%→92.78% / 86.21%→87.29%，约 +340 例） | 19 个新测试文件 | `make test-cov` + ratchet |
| **Instruction artifact 清单 + 哈希锁**（Prompt Card 的可验证底座） | `experiments/prompt_artifacts.py`；清单 `PROMPT_ARTIFACTS.{md,json}` + **投稿用 `PROMPT_CARD.md`**（全文/哈希/注入口径/调用点数/复现步骤） | `make prompt-artifacts-check`（strict）；CI 已接入 |
| **F 轮**：env 预算门禁盲区修复（后缀式 `_X_ENV` 常量 + `env_flag/env_int` 调用形态此前不可见，`--check` 报 "194/194 通过" 属**假绿**；现 194 → 219 个开关全部在册） | `scripts/gates/check_env_budget.py::_PATTERNS` + `docs/env_budget.yaml`（+25 名，逐个核实有实际取用点） | `make env-budget`；`pytest tests/test_x_batch.py -q -k EnvBudget` |
| **F 轮**：布尔开关口径统一（**60 处**窄口径 `.lower()=="true"` → `env_flag` 单一事实源，跨 27 文件）。修复 fail-open 缺陷：`PATCH_DANGEROUS_API_GUARD=1` / `PATCH_CONTRACT_CHECK=1` 此前被判 False——**想开安全守卫反而关掉**且无告警 | `src/utils/env_utils.py`（真值集 true/1/on，`yes` 需显式声明）+ 27 个调用文件 | `pytest tests/test_env_utils.py tests/test_patch_applier.py -q -k "EnvFlag or TruthyCaliber"` |
| **F 轮**：模块级裸 `int(os.getenv())` 加固（3 处坏值于 **import 期**抛 ValueError → `env_int` 容错回退 + WARNING） | `src/utils/env_utils.py::env_int`；`graph/nodes.py::CODE_FOCUS_DEPTH`、`tools/control_flow.py::_CFG_SUMMARY_MAX_CHARS`/`_PATH_MAX_DEFAULT` | `pytest tests/test_env_utils.py -q -k ModuleLevelNumeric`（子进程带坏值导入） |
| **F 轮**：`cache_stats.json` 原子落盘（此前直写，进程被 kill / 磁盘满留半写 JSON，而读侧对损坏文件**静默回零**——已累计计数无声丢失） | `src/tools/dependency.py::_persist_cache_stats` 改走 `src/utils/atomic_io.py::atomic_write_json`（同目录 tmp + `os.replace`，权限 0600） | `pytest tests/test_venv_cache_monitoring.py -q -k AtomicPersist` |
| **G 轮 A**：C5 危险 API 守卫**实效化**（repo 链路）。X 批次把 `+` 行原样拼接后交给 AST 扫描，跨 hunk 的调用被切碎 → 解析失败即"看不见"＝放行；现逐 hunk 三口径合并（差集 ∪ `+`-only ∪ 保留上下文行），且**读不懂即拒绝**（fail-closed） | `src/agents/executor_repo.py::_split_diff_hunks` / `_llm_patch_dangerous_calls` | `pytest tests/test_x_batch.py -q` |
| **G 轮 A′**：补丁**片段** AST 扫描。diff hunk 切片常是某个更大语法结构的中段，裸解析必然失败 → 加片段脚手架；仍解析不出则拒绝应用（安全守卫读不懂输入时不得判"安全"） | `src/tools/patch_applier.py`（片段扫描 + 拒绝口径） | `pytest tests/test_patch_applier.py -q` |
| **G 轮 B**：conftest 危险调用守卫**接线到生产路径**。此前该守卫只有测试调用、**零生产调用点**（开关形同装饰），而 repo 执行链正是在宿主上执行第三方仓库自带的 `conftest.py`；现按分层裁决接入 pytest 执行前。实测口径：本机 37 个真实 conftest.py → Tier-1 命中 **0/37**、Tier-2 **3/37**（分层是为压误报，不是为放行） | `src/agents/executor_repo.py::_scan_repo_conftests` + `src/tools/dependency.py`（S6 分层 / getattr 收紧 / 负集口径开关） | `pytest tests/test_x_batch.py tests/test_venv_cache_monitoring.py -q` |
| **G 轮 C**：`COST_BUDGET` 坏值不再等同"未配置"。三项数值配置写成非数值此前**静默按不限放行**（预算守卫形同不存在）；现三态区分（合法/非法/缺省），非法 → 拒绝后续 LLM 调用 + ERROR 日志 + 独立事件计数（与真实超限分开） | `src/budget/cost_budget.py::_read_budget_number` | `pytest tests/test_cost_budget_matrix.py -q` |
| **G 轮 D**：`strategy_bank` 结构损坏不再覆写主数据。顶层非 dict 此前静默降级为空库并**照写盘**，等于清空既有 `strategies` 表；现降级留 WARNING 且不覆写（观测层追加无权销毁主数据） | `src/tools/strategy_bank.py::_load_bank` / 写回路径 | `pytest tests/test_strategy_bank_branches.py -q -k Corruption` |
| **G1+G2**：两处门禁假绿。① `check_llm_configs_schema.py` 把"文件读不懂"（JSON 损坏 / 顶层非数组）与"目录为空"同形判绿；② `coverage_ratchet.py` 在**状态文件缺失**时回退初始水位判绿——"水位只升不降"被一次误删文件绕过。现均 fail-closed（棘轮 exit 2，首次落盘须显式 `--init`） | 两个门禁脚本 + `Makefile` | `pytest tests/test_w_batch.py tests/test_x_batch.py -q` |
| **G3**：`logic_degraded` 归因链断裂修复 + 状态契约门禁扩容。三个写侧只写进 `test_plan` 内部，唯一读侧 `failure_taxonomy` 读**顶层**键 → 恒 `None`，"规约降级弱信号"分支**从未 fire**（既有单测手工构造顶层键，恰好掩盖断链）；现由 `_planner_node` 抬升为顶层通道（`state.py` 声明 + 默认 `False`，纯观测不参与路由）。门禁扫描面从 2 个硬编码文件扩到 **`src/` 全树 132 文件**（0.15s、零存量违规） | `src/graph/state.py` + `src/graph/nodes.py::_planner_node` + `src/observability/failure_taxonomy.py` + `scripts/gates/check_state_contract.py` | `make state-contract`；`pytest tests/test_nodes_batch11_pure_logic.py tests/test_state_contract_guard.py -q` |
| **G6**：登记册↔`coverage.xml` 对账**常年假绿**（CI 步骤排在产物生成之前约 90 行，缺席被判 `[OK]`）+ 原口径**不可满足**（逐位相等 vs 单分支 0.016pp 抖动）。现强制支路移入覆盖率集群（`--require-coverage`：缺席即红），口径改为锚定 §1 声明行 + ±0.10pp 容差、声明行缺失按不通过处置 | `scripts/gates/check_artifact_doc_consistency.py::check_status_register` + `.github/workflows/ci.yml` | CI 步骤 `Status register coverage reconciliation`；`pytest tests/test_artifact_doc_consistency_gate.py -q` |
| **H1**：**覆盖率测量非确定性根因定位并修复**（G 轮登记为"成因未定位"，本轮收口）。`config._apply_profile_presets()` 在 **import 期**用 `os.environ.setdefault` 注入档位开关、既绕过 monkeypatch 追踪也无 teardown；两处测试各自**手抄**还原清单且均已过期（漏 AA/AB1/AC2/AI1/P0-B 五批新增键）→ 6 个开关键跨测试残留 → 后续测试走进"档位开启"分支。G 轮观测到的 `nodes.py` 0.7776/0.7862 摆动正是特异性门块内 6 行。**A/B 实测**：三文件回退 HEAD → 残留 `{SPEC_SMT_ENABLE, LOGIC_SPEC_STRICT_FALLBACK_ENABLE, DETECTION_SPECIFICITY_GATE_ENABLE, RED_REGRESSION_GATE_ENABLE, FL_SPECTRAL_ENABLE, MUTATION_ADVISOR_ENABLE}` 全为 `"true"`；修复后残留 **0** | `tests/conftest.py::_isolate_profile_presets`（全局兜底，键集**从 `_PROFILE_PRESETS` 派生**，新增档位开关自动纳入）+ 两处手抄清单改派生 + `_INJECTED` 补 6 键并加漂移锁 | `pytest tests/test_conftest_env_isolation.py -q`（含"兜底集缩小即红"负控） |
| **H2**：嵌套 pytest 子进程**剔除宿主 pytest 配置**（测量完整性）。`_run_pytest_in_tmp` 用 `env={**os.environ}` 却把 `PYTHONPATH` 覆盖成 tmpdir → 宿主 `PYTEST_PLUGINS` 在嵌套运行里不可导入 → pytest **在收集前** rc=1 → `detection_gates` 把"根本没跑起来"读成"测试红"→ `specificity_verdict` 误判 `over_red`（正确结论应为 `unavailable`）。**已实测复现**（最小 tmp 目录 rc=1 + ImportError）。即宿主的 pytest 配置能让 M1 检出裁决与 AC2 双门得出**与被测代码无关**的结论，且日志无异常 | `src/utils/process_utils.py::nested_pytest_env`；接线 `experiments/_m1_metrics.py` + `src/measurement/mdo.py` | `pytest tests/test_process_utils.py -q -k NestedPytestEnv`（端到端：旧口径 rc≠0 / 新口径 rc=0） |
| **H3**：`verify_redaction_consistency` **接线** + 运行期盲区检查（安全）。该守卫 docstring 自称"CI / 安全测试可调用"，H 轮前**全仓零调用点**（有实现、有单测、有开关语义，就是不跑 ＝ 装饰守卫）。接进脱敏审计门禁后**首次执行即抓出 3 个运行期盲区**：`api key:` / `private key:` / `refresh token:` **空格分隔变体**——静态扫描器（O33）早已按 `api[-_ ]?key` 口径拦"调用点原样打印"，运行期 `_SENSITIVE_PATTERNS` 却只认 `[_-]?`，导致 SensitiveFormatter、trace JSONL 落盘、`exc_info` 堆栈这些**全局兜底路径**对空格变体完全不设防。现两侧口径对齐，13 条规范探针**零盲区、零分叉**（944 文件 / 594 logger 调用点，静态半区仍 0 finding） | `scripts/gates/audit_log_redaction.py::audit_runtime_redaction`（一致性 + 盲区双检查，导入失败/异常/未执行一律 fail-closed）+ `src/utils/logging_utils.py`（字段名分隔符放宽 + 规范探针语料单一事实源） | `python scripts/gates/audit_log_redaction.py`（rc=0）；`pytest tests/test_audit_log_redaction.py -q` |
| **H4**：两个"只写不读"观测信号**补落盘**。`state["testless_validation"]`（补丁后四层静态验证）与 `state["deterministic_guard_report"]`（生成测试非确定性扫描）在全仓 **0 消费方**，且不在 `_dump_state_artifacts` 白名单 → LangGraph 直接丢弃，节点注释承诺的用途（"供 G2 风险分级放大风险分" / "供实验层决定是否入库确定性套件"）**静默落空**。与本白名单前两次扩容（`position_aware_focus` / `cross_file_deps`）同一缺陷形态。两开关默认关 → 默认档批次这两键恒 null，历史工件语义零变化 | `experiments/run_benchmark.py::_dump_state_artifacts` | `pytest tests/test_run_benchmark.py -q -k ObservationKeys`（含工件键集合钉死） |
| **H5**：**A-14 property 模糊测试第二起反例——晚期 parse 门归因漂移**（真缺陷，非测试问题）。`_clause_reject_reason_for_known` 在形态门、白名单门、`mode="eval"` 解析**全部通过**之后，还要把子句拼成 `assert <expr>` 再解析一次；该门失败时此前返回 `parse_error`——而 `parse_error` 是**形态门家族**标签（`_FORM_GATE_REASONS`），于是"`is_expression_clause` 为 True ⇒ 归因不含形态门家族"这条不变式被打破。反例 `"0,"`：尾随逗号让子句成为 1-元组，`assert (0,)` 恒真且缺 msg → SyntaxError。按模块**自身**的 `SPEC_REJECT_REASONS` 文档（`unsupported_syntax` = 可解析为表达式但**编译产物是恒真断言**，与 lambda / 海象同族；`parse_error` = 语法错）改判 `unsupported_syntax`——**只换标签，不放宽任何拒绝面**。归因错则"修提示 vs 扩文法"的取舍依据错，与 A-14 首起反例 `"0\x1f"` 同一缺陷形态。**发现路径值得记录**：该反例由 H1/H5 之外的第三个目的（消除覆盖率漂移）触发的双跑中，第 **2** 次运行才被 hypothesis 命中并写入 `.hypothesis/` 例库，此后确定性回放失败——单次全量绿并不代表不变式成立。**对入库工件零影响**（已核验）：全仓 36 个含 `parse_error` 字串的工件里，只有 `emse_dsl_diag3_20261015/DIAG3_REPORT.json` 用的是规约归因命名空间（其余为 SWE-bench 的 `error_category`），而它的 `parse_error` 样本桶为 **0 条**（`unsupported_syntax` 5 条）→ 同语料重生成逐格相同；文档侧亦无任何报告引用该归因分布 | `src/specs/spec_ir_v2.py::_clause_reject_reason_for_known`（晚期 parse 门 + `SPEC_REJECT_REASONS` 归因文档同步） | `pytest tests/test_spec_expr_property.py tests/test_spec_ir_guards_matrix.py -q`（含 `TestLateParseGateDriftRegression` 6 例确定性反例锁 + 合法逗号形态不误伤） |
| **H6**：**双重检查锁的竞态分支钉成确定性**。`get_manager()` 内层 `if _manager is None` 的 False 弧只在"另一线程于两次检查之间完成初始化"时走到，既有 8 线程并发用例能否命中**取决于调度**：H 轮连跑两次 CI 口径全量，`api/api_manager.py:1068` 一次 `100% (2/2)`、一次 `50% (1/2)`——这是修掉 H1（env 泄漏）与 H5（晚期 parse 门）之后**全仓最后一处**覆盖率漂移（1 个分支 = 0.016pp）。新增用例用假锁在 `__enter__` 注入"已被抢先初始化"的单例，把交错钉死；并首次断言**构造函数未被二次调用**——这才是双重检查锁真正要保证的性质，原并发用例只验证了"实例唯一"（该结论在无 DCL 时也可能碰巧成立） | `tests/test_api_manager_extended.py::TestSingletonThreadHygiene::test_double_checked_lock_skips_second_construction` | `pytest tests/test_api_manager_extended.py -q -k SingletonThreadHygiene --cov=src.api.api_manager --cov-branch`（1068 恒 `2/2`） |
| **I1**：**归因链末端接线**——`failure_taxonomy.annotate_final_state` 接进批次落盘。该框架自 U11（2026-10-05）落地以来**零生产调用点**：五桶终局分类 + 批次 XII 的 edge × fault_side 增补维度只在单测里被断言，批次工件与报表一处不落，"失败发生在哪个环节、故障侧指向 model 还是 harness"无法从工件复算。现 per-task 行新增 4 键（`failure_bucket` / `failure_bucket_detail` / `attribution_edge` / `attribution_fault_side`），臂级 summary 新增 `failure_bucket_distribution`（与 `summarize_batch` 同构，`render_markdown` 可直接消费）。**喂入口径是接线的一半**：`annotate_final_state` 读状态通道顶层键，而结果行是投影，且 `stop_reason` 必须经 `effective_stop_reason` 兜底（O35：路由层写入被 LangGraph 丢弃）——实测直喂 `final_state` 会把"迭代耗尽"这类最常见的生成能力失效**误判成 UNCATEGORIZED**（`generation_capability_failure` → `uncategorized`），即"归因没接对"伪装成"系统失效无法分类"。分母口径：运行异常行（无工作流终局状态）单列 `unclassified_rows`，**不**折进兜底桶；`render_markdown` 相应披露分母，否则报表把批次规模读小 | `experiments/run_benchmark.py::_failure_attribution_for_result` / `_aggregate_failure_buckets` | `pytest tests/test_run_benchmark.py -q -k "FailureAttributionWiring or FailureBucketAggregation"`（13 例） |
| **I2**：**`m10_leaf_fallback` 抬到状态顶层 + 落盘**（ADR-0032 可分离性变可机读）。此前 1 个写侧、0 个读侧：`PlannerAgent.plan` 的 M10 兜底分支把标记写进 `result`（即 `test_plan` **内部**），该键又从未在 `AITesterState` 声明 → LangGraph 直接丢弃、投影行也读不到，ADR-0032 声称的"`logic_degraded=True ∧ m10_leaf_fallback=True` ⇒ 提取器误诊（非 LLM 真未输出）"无法从任何工件验证。现三处补齐：`state.py` 声明 + `create_initial_state` 默认 False、`_planner_node` 无条件抬升（与 G3 的 `logic_degraded` 同构，False 同样有意义）、批次工件白名单与 per-task 行各加一键 | `src/graph/state.py`、`src/graph/nodes.py::_planner_node`、`experiments/run_benchmark.py` | `pytest tests/test_nodes_batch11_pure_logic.py -q -k M10LeafFallback`（6 例）+ `scripts/gates/check_state_contract.py` |
| **I2b**：**修 ADR-0032 标记在默认计划替换时被吞**（接线过程中实测发现，非登记项）。`extract_json_object` 的叶子降级档返回**最内层片段**（如 `{"k": 42}`），片段通常连 `function_name` 都没有 → `_validate_planner_output` 判 False → `_planner_node` 用默认计划**整份替换** `test_plan`，planner 刚写下的 `m10_leaf_fallback` 随之丢弃 → 顶层只能抬到 False，"提取器误诊"被记成"LLM 真未输出"，**归因反向错误**。即 ADR-0032 的可分离性恰好在它最该生效的场景下失效。实测日志链：`helpers.py:735`（叶子回退）→ `planner.py:380`（写标记）→ `nodes.py:2324`（缺 function_name）→ `nodes.py:337`（默认计划，标记消失）。修为替换前先摘出该标记再回填 | `src/graph/nodes.py::_planner_node` 结构校验失败分支 | `pytest tests/test_nodes_batch11_pure_logic.py -q -k test_marker_survives_default_plan_replacement`（真 PlannerAgent + 真节点，端到端） |
| **I3**：**`stop_reason="unknown"` 不再抢占 `logic_degraded` 弱信号**。I1 接线时按 G3 文档口径必须经 `effective_stop_reason` 取终止原因，而其兜底返回值是 `"unknown"`——**非空字符串**，于是旧实现 `if stop_reason:` 把它当作有信息的归因证据走查表 → UNCATEGORIZED，**永远走不到**弱信号分支：G3 抬升键路径修好了，读侧分支在唯一的生产路径上依然不可达。既有单测只构造"stop_reason 缺失"的输入（`test_logic_degraded_weak_signal`），因此一直是绿的——与 G3 同一失效形态（单测手工构造理想输入，掩盖生产路径不可达）。`"unknown"` 是 `determine_stop_reason` 第 8 优先级的保守兜底，语义等于"无信息"，而弱信号本就是为"stop_reason 不可用"设计的。映射表仍保留 `unknown → UNCATEGORIZED` 条目（保证对 `StopReason` 全域封闭，`test_mapping_covers_all_workflow_stop_reasons` 依赖它），只是不再让它抢占有真实弱信号的行 | `src/observability/failure_taxonomy.py::annotate_final_state` | `pytest tests/test_failure_taxonomy.py -q -k UnknownStopReason`（6 例，含经 `effective_stop_reason` 的端到端一例） |
| **df_spec 实验（P1 主实验，2026-10-17 凌晨实跑）**：预注册 + 判定口径**跑批前**锁定（`DF_SPEC_PREREG_2026-10-16.md` sha256 `a19a6c29…` → 承诺于 `cd514d2`；分析脚本 25 例测试同批入库）→ QuixBugs 双臂同批实跑（50/50 锚命中 `attempted_replaced`、独立 namespace、logic 档 temp=0、双 provenance `git_dirty=false`）→ **`not_confirmed`（方向为负的显著证据）**：df_spec **54.3%（19/35）vs df 77.8%（28/36）**、配对 **1:10**、δ=**−25.7pp**、双向精确 p=**0.0117**、BF10=16.4；over_red 占比 **46.0% vs 22.5%**（预注册预期 −30%，实测反向上升 104%）；预注册三条件全未满足、失败线（<50%）未触发。机制假设（锚材料=对缺陷代码的再描述，非独立正确规格）标注"待检验"，见分层叙事 §9 | 工件 `experiments/results/emse_df_spec_20261016/`（两臂 JSON + `DF_SPEC_REPORT.json` + README + SHA256SUMS 104 项校验通过） | `python -m experiments.emse_df_spec_analysis --dfspec … --df …`；`pytest tests/test_emse_df_spec_analysis.py -q` |
| **J-4 覆盖率收口批次（2026-10-17，零 LLM）** | 三件事一并落地：① **补口**——五个 `test_nodes_j4_*` + `test_executor_repo_j4_coverage.py`（193 例）把 `graph/nodes.py`（155 未覆盖行）与 `agents/executor_repo.py`（118 未覆盖行）补至 **100.00%（行 + 分支）**；② **死代码清理**——删除 `deterministic_guard.guard_generated_test` / `patch_applier.safe_apply_patch_contract` / `event_bus.publish_workflow_completed` / `process_utils._close_quietly`（四处零生产调用点，`nodes.py:2041` 保留历史注释）；③ **开关口径**——新增 `env_flag_opt_out`（负集口径，接管原手抄 10 处）与 `env_float`（含 NaN/±inf 回退）。总行覆盖 92.96→**94.68**、分支 87.62→**90.30**，`coverage_ratchet.yaml` 水位 92.90→94.60 / 87.50→90.30 | `pytest tests/test_nodes_j4_*.py tests/test_executor_repo_j4_coverage.py tests/test_env_utils.py -q`；`make env-budget`；`scripts/gates/coverage_ratchet.py --check` |
| **K-1：JSON 提取围栏内容篡改修复（P0，2026-10-17）** | `extract_json_object/array` 的历史清洗链用 `re.compile(r"```")` **无条件删除全文任意位置三连反引号**——合法 JSON 字符串值里出现反引号（LLM 输出补丁/命令/代码片段时极常见）会被静默改写：`{"cmd": "```bash"}` → `{"cmd": "bash"}`、`{"```": null}` → `{"": null}`。解析"成功"但内容错误，比解析失败更危险。修复：① 原始文本先行快路径（合法 JSON 未清洗即解析，内容零改写）；② 围栏只在行首剥离。**发现路径**：A-13 property 测试（300 例）随机命中反例 → 确定性回归锁 29 例（`tests/test_helpers_json_fence_content.py`）。验证：`pytest tests/test_helpers_json_fence_content.py tests/test_helpers_json_property.py -q` | `src/utils/helpers.py::_try_parse_raw_json` / `_JSON_FENCE_STRIP_PATTERN` |
| **K-2：G16 文档链接完整性门禁 + 文档 INDEX（2026-10-17）** | 109 份 markdown（根 15 / docs 90 / examples 4）的**相对链接 / 行锚目标 / 标题锚点**静态校验（零网络；外链只统计不 fetch；fenced/inline code 忽略；大小写逐级精确校验；github-slugger v2 近似，CJK 未命中降级 warning 当前 0 条）；排除 CHANGELOG*/docs/history（历史快照不可回写，作为链接目标仍校验）。基线 107 文件/351 链接/**1 错误** → 终态 109 文件/**528 链接/0 错误**；新增 `docs/INDEX.md` + `.en.md`（4 角色阅读路径）+ README 导航块 + `docs/link_check_allowlist.txt`（当前 0 条，无理由豁免本身判 error）。验证：`make docs-check`；`pytest tests/test_check_doc_links.py -q`（47 例）；CI 步骤 `Documentation link integrity (G16)` |
| **K-3：自身测试套件变异测试能力（meta 层，2026-10-17）** | 新增 `scripts/tools/self_mutation.py`（零 LLM：复用 18 类 AST 算子 + 每 worker 临时副本 + `nested_pytest_env` + killpg 超时 + rc 分类 + 绿基线前置 + JSON/MD 报告 + `--test-map/--fail-under`）。**首次量化项目自身测试强度**：基线 **0.6419**（138/215）→ 击杀批次后 **0.7674**（165/215，**+19.6% 相对**，27 survived→killed、0 反向翻转）；3 模块分列 env_utils 0.8933→0.9467 / helpers 0.5294→0.6471（25.6% 抽样点估计）/ atomic_io 0.3810→0.8095。剩余 50 存活逐条归因（可证明等价 5 / 强证据实践等价 17 / 公开契约外 5 / **待补 23 不声称等价**）。CI：weekly `mutation.yml`（gate 口径 env+atomic 阈值 0.85，实测 **0.9067**）；`make self-mutation` / `make self-mutation-ci`。验证：`pytest tests/test_self_mutation_tool.py tests/test_self_mutation_targets.py -q`（58 例） |
| **K-4：覆盖率收口 94.65% → 96.47%（2026-10-17）** | 10 个 `test_closeout_k_*.py`（155 例，全部确定性/零 LLM/零等待）：debugger 76 / base_agent 40 / api_manager 29 / llm_client 23 / multi_candidate 21 / cli-app 18 / workflow 16 / error_classifier 16 等 18 个文件改善、**0 回退**。行 16061/16968=94.65% → **16369/16968=96.47%**（+308 行）；分支 5638/6246=90.27% → **5782/6246=92.57%**（+144 弧）。未覆盖剩余逐条归因（import 期坏 env 回退为避免 `importlib.reload` 污染共享进程而刻意不覆盖 / 静态不可达 / `__main__` 自检块）。验证：`make test-cov` + `coverage_ratchet.py --check` |
| **K-5：变异生成器无效变异体修复（测量伪影第⑤起，2026-10-17）** | `experiments/mutation_testing.py` 两类假变异体：① identity——`_generate_numeric_offset` 对任意 Constant 登记偏移但只偏移 int/float（`x is None` / `s == "abc"` 零改动），字符串置换对原文 `'x'` 置换值仍为 `'x'`；② 语法非法——`_gen_subscript_negate` 对 Slice 下标产出 `x[-(a:b) - 1]`（实测单文件 5 个）。两者都会在执行期"恒存活"（后者 rc=2 被保守记存活）→ **mutation_score 系统性偏低**。修复：类型守卫 + AST 级变化校验 + Slice 跳过 + `_emit` 通用语法守卫。语料验证：30 文件 4603 变异体 **0 invalid / 0 identity**；新增 `tests/test_mutation_generator_validity.py`（16 例）。披露：`docs/MEASUREMENT_INTEGRITY.md` 第⑤起（存量工件该指标一律标"旧口径下界"；cosmic-ray 口径 QuixBugs Mut@k 0.9396 **不受影响**） |
| **K-6：孤儿嵌套测试进程巡检（运行期卫生，2026-10-17）** | 实测发现两个 PPID=1 的变异体 pytest 进程各空转 **~7 小时**、各占 ~97% CPU（合计浪费约 14 CPU·小时，期间全量测试被拖慢一倍）。成因：父进程被外部 SIGKILL 时 `run_with_timeout` 的 killpg 分支永不执行（macOS 无 `PR_SET_PDEATHSIG` 等价物）。新增 `scripts/tools/detect_orphan_procs.py`（四条件交集识别：沙箱标记 + pytest 调用 + PPID=1 + 龄期≥600s；只读默认，`--kill` 先 SIGTERM 后 SIGKILL；ps 不可用**不当零泄漏**）；接入 `make proc-hygiene` 与 preflight（泄漏计入阻断项——CPU 饥饿会制造超时=不可判定任务=污染批次结论）。验证：`pytest tests/test_detect_orphan_procs.py tests/test_batch_quota_preflight.py -q`（38 例） |
| **K-7：性能基准扩展（JSON 提取家族，2026-10-17）** | `scripts/tools/performance_benchmark.py` 新增 `json_extraction` 类别（4 条真实路径：典型围栏/2KB 大计划/截断修复档/数组契约）——每条 LLM 响应都走该解析入口，此前无回归面。基线 `docs/performance_baseline.json` 增补该类别（键值在 0.05ms 绝对下限之下，仅作趋势参考）；`make perf-bench` / `make perf-check`。验证：`pytest tests/test_perf_benchmark_k_round.py -q`（10 例，含基线漂移守卫） |
| **K-8：本地 gates 与 CI 对等补口（2026-10-17）** | 实测发现 U3 零断言门禁**长期只在 CI、不在本地 `make gates` 链**：HEAD（fde68ae）实际带 1 例零断言违规（`test_class_method_not_confused_with_top_level` 的 `if ok:` 分支从不执行）＝"本地全绿≠CI 绿"。处置：① 把 `zero-assert` 补入 `make gates`；② 把该用例改成双路径硬断言（拒绝路径逐字节回滚 + 类内方法定义仍在）。验证：`make zero-assert`（违规 0） |
| **K-9：CI 工作流新增（2026-10-17）** | ① `ci.yml` 新增 `Documentation link integrity (G16)` 阻断步骤（24→**25** 道阻断门禁）；② 新增 `mutation.yml`（每周一 07:00 UTC + 手动）：自身变异测试 gate（env+atomic，阈值 0.85，实测 0.9067）+ 3 模块全量巡检报告归档 90 天 + Step Summary。两者均固定 action SHA（与 ci.yml 同源）。验证：`.github/workflows/mutation.yml` YAML 解析通过；`make self-mutation-ci` 实测 exit 0（score 0.9067） |
| **J-1b：三个聚合器外提为模块级（2026-10-17，零 LLM）** | `_aggregate_rag_metrics` / `_aggregate_token_metrics` / `_aggregate_failure_categories` 由 `run_benchmark()` 嵌套函数外提（行为逐字节不变），10 例口径锁定测试钉住三个分母（检索次数 / 行数 / 调用数）与零除守卫 | `pytest tests/test_run_benchmark.py -q -k ModuleLevelAggregators` |
| **J-2：开关口径二次复现收口（2026-10-17，零 LLM）** | ① `env_flag_opt_out` 负集口径（10 处手抄收敛，补大小写/空白/关闭字面量集）+ `env_float`（NaN/±inf 回退）；② **env 预算门禁第二次同族盲区**：`env_flag_opt_out` 与 `config.py::_parse_int_env/_parse_float_env` 两式不可见 → 24 个真实旋钮（TEMPERATURE/MAX_ITERATIONS/MYSQL_PORT/EXECUTION_TIMEOUT…）从未入登记表；登记表 219→**248**，逐个核实有实际取用点 | `pytest tests/test_env_utils.py -q`；`make env-budget` |
| **J-3：可选插件类型面（2026-10-17，零 LLM）** | `pytest-timeout`（A-06 判分 per-test 超时的可选插件）加入 mypy `ignore_missing_imports` override；否则经 `detection_gates` 运行时 import 跟进后 `make typecheck` 报红 | `make typecheck` |
| **A-19：停滞检测消融臂 CLI（2026-10-17，零 LLM）** | `--enable-stagnation` / `--no-stagnation` 映射到 `COVERAGE_STALL_DETECT_ENABLE`（workflow 现读 env，provenance 清单已含该键）；两臂互斥 fail fast；5 例映射/互斥/读侧回读测试。**消融批次待 LLM 配额**（§2 B8） | `pytest tests/test_run_benchmark.py -q -k StagnationArm` |

## 4. 遗留缺口（按"是否值得继续"分级）

### 4.1 开放问题登记（独立评审 A-16，2026-10-17）

> 来源：`docs/reviews/INDEPENDENT_SYSTEMATIC_REVIEW_2026-10-17.md` §15（Q1-Q12）。已收口项（Q1 工件入 git / Q2 DOI 定位 / Q4 口径桥接 / Q9 全量测试实跑）不重复登记；下表为**仍未决**项，每项含责任建议人、截止建议与"未澄清时的降级处理"（降级纪律：不可验证项不得用于支撑任何结论）。

| # | 问题 | 建议责任方 | 截止建议 | 未澄清时的降级处理 |
|---|---|---|---|---|
| Q3 | QuixBugs repair 92.5%（37/40）分母定义（40 = 41−1 的哪一口径）与 9 个测试驱动任务的影响 | 实验负责人 | 2026-10-31 | 该指标对外引用一律带"分母口径待澄清"标签；不进任何横向对比 |
| Q5 | plain_llm_df 臂跨批 83.8%（10-09）→77.8%（10-16）6pp 波动的归因（服务端非确定性 / 缓存 / 物化差异） | 实验负责人 | 2026-11-07 | 所有单批 QuixBugs detection 结论附"跨批波动 6pp"披露；功效解读以 MDE 16.1pp 为准 |
| Q6 | `graph/orchestration_search.py` 16 臂 bandit 状态（ADR-0034 冻结中 vs 已废弃） | 项目负责人 | 2026-10-31 | 论文不提及该组件；README 标注"未实跑" |
| Q7 | `SPEC_SMT_ENABLE`（z3 SMT 见证层）是否有任何启用批次记录 | 实验负责人 | 2026-11-07 | z3 层仅作"实现在场未评估"的能力陈述，不进任何结果（启用批次设计见 `docs/design/smt_witness_batch_plan.md`） |
| Q8 | ULT 官方 `test_list` 71/71 在 fixed 上失败（gold 参照作废）是否已反馈上游；协议适配细节 | 实验负责人 | 2026-11-07 | ULT 相关结论带"官方 gold 在本管线不可用"标签；ULT 对标仅作方向性陈述 |
| Q10 | plain_llm 臂 false_fix 229/229=100% 的口径语义（IR §15.6 遗留） | 实验负责人 | 2026-10-31 | 该数字不单独引用；false_fix 一律以五口径矩阵标签呈现 |
| Q11 | `paper/draft.typ` 数字与工件一致性（评审仅抽查 3 处 SRC 注释） | 论文执笔人 | 投稿前 | 补审计划见评审报告 §1.3；重点核验百分比/DOI/成本数字的 SRC 完整性 |
| Q12 | `~/.cache/aitester/ult_repo` MIT 许可核实的证据链归档（项目自报 2026-10-12 实测） | 项目负责人 | 2026-10-31 | 论文 Data Availability 不引用该缓存路径，仅引用官方仓库地址 |

| 分级 | 缺口 | 说明 |
|---|---|---|
| **建议做** | B5 文本目检（清单/哈希锁已就绪，2026-10-16 呈交） | B6 已执行（8c2b655）；A-10 df_spec 臂已落地（6ddd1ca）；A-11 冻结 ADR-0034 |
| **J-4 已收口** | ~~`graph/nodes.py` **155** 行 + `agents/executor_repo.py` **118** 行未覆盖~~ → 均补至 **100.00%**（行 + 分支）；仅 `graph/orchestration_search.py` **74** 行仍"可做" | J-4 五个 `test_nodes_j4_*` + `test_executor_repo_j4_coverage.py`（193 例）收复 §4 这两处最大空洞，直接把总行覆盖 92.96→**94.68**、分支 87.62→**90.30**，并令 ratchet 水位上调（92.90→94.60 / 87.50→90.30）。orchestration_search 属 ADR-0034 冻结的 16 臂 bandit，Q6 未澄清前不投入。验证：`pytest tests/test_nodes_j4_*.py tests/test_executor_repo_j4_coverage.py -q` |
| **K 轮已收口** | ~~`agents/debugger.py` 76 行（低优先）~~ → **100.00%**（340/340） | K-4 的 `tests/test_closeout_k_debugger.py`（20 例）覆盖默认关开关的主流程/探针/跨文件预算 break/降级链温度/严格 prompt 重试/KB 闭环/RAG/对抗 critic/编辑意图/类型修复层；同理 base_agent 99% / api_manager 100% / llm_client 100% / error_classifier 100% / fault_localizer 100% |
| **H 轮已收口** | ~~覆盖率测量非确定性~~ → **三处独立噪声源全部定位并消除**（§3.2 **H1 / H5 / H6**） | G 轮登记的"成因未定位"本轮完整收口。**排查顺序与结论**：先排除 xdist 分组、随机路径、并发超时（均非成因）；① **H1 主因**＝`config` 在 import 期用 `setdefault` 注入档位开关、既绕过 monkeypatch 也无 teardown，加上两处测试**手抄**的还原清单均已过期 → 6 个开关键跨测试残留 → `nodes.py` 在 0.7776/0.7862 间摆动（特异性门块内 6 行）。② 修掉①后逐行比对只剩 **2 行**（`spec_ir_v2.py` 晚期 parse 门），定位为**只有 hypothesis 模糊测试碰运气才命中**；补确定性用例时反被模糊测试抓出**真门漂移**（H5，反例 `"0,"`）。③ 再修后只剩 **1 个分支**（`api_manager.py:1068` 双重检查锁竞态弧），由既有 8 线程用例的调度运气决定，已钉成确定性（H6）。**终局证据**：连跑两次 CI 口径全量，`coverage.xml` 逐行 + 逐分支比对**零漂移**（16934 行 / 3116 分支点全同；行 15739/16934=92.9432%、分支 5458/6232=87.5802% 两次逐位相同）。**方法论教训**：噪声不是单一根因——修掉最大的一处只把不确定性从"6 行"降到"2 行"再降到"1 分支"，**必须逐层比对到零**才算收口 |
| **H 轮遗留（口径精修）** | G6 的 **±0.10pp** 对账容差现已偏宽 | 该容差是按"含噪声观测"的抖动上界（≈2×）定的；噪声源全部消除后，理论上可回到逐位相等口径。**本轮不收紧**：① 防回退不靠容差，靠 `coverage_ratchet.py` 的只升水位；② 收紧需要多轮干净复跑重测抖动上界（跨主机/跨 CI runner 仍可能有差异，见下条跨平台风险）；③ 收紧的收益只是口径更严，风险是把"常年假绿"换成"随机真红"（G6 勘误二的原教训）。处置建议：先在 CI 的 ubuntu 档观测数次，确认跨平台也零漂移后再收紧 |
| **J-4 已收口** | ~~装饰守卫审计残余 2 项~~（`deterministic_guard.py::guard_generated_test`、`patch_applier.py::safe_apply_patch_contract`）→ 死代码已删 | J-4 按死代码清理授权删除两处零生产调用点的薄包装（前者包 `scan_test_file`、已在 `nodes.py` 接线；后者契约检查实经 `check_naming_contract` 接线）。删除后 `nodes.py:2041` 保留一条历史注释说明该包装器为何不再存在；全量 + 门禁零回归（`grep` 确认全仓无残留调用） |
| **H 轮新登记** | 嵌套 pytest 环境隔离只修了 **2/7** 处 | H2 修的是 `src/` 与 M1 判分层（测量结论的直接来源）：`experiments/_m1_metrics.py`、`src/measurement/mdo.py`。按"子进程命令里确有 `-m pytest`"口径复核，剩余 **5 处 / 4 文件**仍用 `env={**os.environ, ...}`：`gold_consistency_pruning.py:116`、`mutation_testing.py:1602`、`suite_repair_pipeline.py:114`、`emse_testlevel_detection.py:382` 与 `:1282`（后两处还把自写插件物化进 tmpdir 并靠 `PYTHONPATH` 加载，与宿主 `PYTEST_PLUGINS` 叠加时同一机制）。另有 3 处 `**os.environ` 起的是**纯 python 探针**（`solver_directed_trigger.py:247`、`spec_ambiguity.py:280`、`mdo.py:298`），不受影响，不计入。这 4 个文件是批次驱动、已冻结用于既有发表数字，且干净环境下 `nested_pytest_env` 与旧写法逐位等价，故本轮不动（避免给已冻结工件加无关 diff）；后续统一收敛时直接换 `nested_pytest_env` 即可 |
| **I 轮已收口** | ~~`src/observability/failure_taxonomy.py` **无生产消费方**~~ → 已接批次落盘（§3.2 **I1**） | G 轮登记为"功能缺口而非缺陷"，本轮补齐末端：per-task 行 4 键 + 臂级 `failure_bucket_distribution` + 报告层分母披露。接线过程又暴露两处**读侧分支不可达**（I2b 标记被默认计划替换吞掉、I3 `unknown` 抢占弱信号），均已修 |
| **I 轮已收口** | ~~`m10_leaf_fallback` **只写不读**（1 写侧、0 读侧）~~ → 已抬顶层 + 落盘（§3.2 **I2 / I2b**） | ADR-0032 的可分离性现为**可机读**：两个顶层标记的组合直接区分"提取器误诊"与"LLM 真未输出"，且随批次工件落盘。无需再把 ADR-0032 降级为"设计意图" |
| **I 轮新登记** | 桶归因与交互边归因存在**有意的不对称** | `logic_degraded` 弱信号命中时 `failure_bucket=specification_failure`，但 `attribution_edge/fault_side` 仍为 `uncategorized`：弱信号只够判定"失效在规约层"，不足以钉出**哪条交互边**、更不足以判定故障侧——若强行归给 `planner_to_generator + model_side`，恰好会把 I2b 那类"提取器（harness 侧）误诊"记成模型侧问题，属编造归因。**后续可做**：`m10_leaf_fallback=True` 正是把这类行判为 `harness_side` 所需的那条证据（ADR-0032 的原意），但把它接进 `interaction_attribution` 是一条**新的归因规则**（新的科学主张），需独立论证与 A/B，不宜与本轮的"接线"混为一谈 |
| **J-1b 已收口** | ~~`run_benchmark()` 内三个既有聚合器仍是**嵌套函数**，口径无法被单测钉住~~ → 已外提为模块级（10 例口径锁定） | `_aggregate_rag_metrics` / `_aggregate_token_metrics` / `_aggregate_failure_categories` 都定义在 `run_benchmark()` 内部，只能靠端到端跑批间接覆盖。I1 新增的 `_aggregate_failure_buckets` 因无闭包依赖已提到模块级（分母口径 `total` vs `total_rows` 是最容易读错的地方，必须可测）。三个既有聚合器同样可以外提，属纯结构调整，但会碰到已冻结实验文件的 diff 面，故本轮不动 |
| **G 轮已知代价** | C5 片段扫描的 fail-closed **保守假阳性** | 补丁片段加脚手架后仍解析不出 → 拒绝应用。方向是刻意的（G 轮决策：一律 fail-closed），代价是**可能拒掉良性补丁**，表现为 repair 成功率下界被压低。若后续观测到误拒率显著，处置是补脚手架形态而不是改回"读不懂即放行" |
| **G 轮已知风险** | G6 对账的**跨平台**余量 | 登记册 §1 声明的是 darwin 实测；ubuntu 档若与声明相差 >0.10pp，`Status register coverage reconciliation` 会转红。该红属**真阳性**（文档↔工件分裂），处置是按 CI 的 `coverage.xml` 刷新 §1，**不得**放宽容差或删步骤 |
| **J-4 已收口** | ~~布尔口径残留分裂 **11 处**~~ → 10 处收敛入 `env_flag_opt_out`（"显式关闭才算关"负集口径），残留 **1** 处 `EXECUTOR_RLIMIT_AS_FORCE`（opt-in 单值式 `== "1"`，刻意保留） | 新增 `src/utils/env_utils.py::env_flag_opt_out`（与 `env_flag` 正集口径对偶），11 调用点接管原手抄负集式 5 处（`CFG_ANALYSIS_ENABLE`/`PATCH_PROTECT_REPO_CORE`/`EVENT_BUS_ENABLE`/`DETECTION_FIRST_SECTION_ENABLE`/`P2P_GATE_ENABLE`）+ 单值否定式 1 处（`EMPTY_PATCH_GUARD`，补 `=0` 关闭字面量）+ opt-out 式 4 处（`AITESTER_AGENT_REUSE`/`AITESTER_EXECUTOR_AGENT_CACHE`/`AITESTER_LLM_CACHE`/`AITESTER_CACHE_ISOLATE_MODEL`）+ 守卫参考实现 `conftest_ast_scan_enabled`。垃圾值方向与 G 轮守卫定调一致（fail-closed）。`EXECUTOR_RLIMIT_AS_FORCE` 并入负集会翻转其垃圾值语义（`=""` 由 False→True），故不并。同批新增 `env_float`（供 `risk_approval`/`executor_modes`/`executor_repo` 收编手写 float 解析，含 NaN/±inf 回退）。复核：`rg -n "(os\\.getenv|os\\.environ\\.get)\\([^)]*\\).*(not in|!=|==)" src/` 现仅 1 行（该 opt-in） |
| **I 轮已收口** | ~~`CHANGELOG.md` 缺 **F / G / H / I 四轮**条目~~ → **已补写**（2026-10-16，按轮分节 + 逐条验证命令 + 未回填任何未实测数字） | 双语同步：`CHANGELOG.en.md` 对称补入四节（两文件各 107 个 `##` 节、日期行同步至 2026-10-16）；`check_bilingual_docs.py --strict` 零警告零失败 |
| **部分收口** | ④ 死代码（`event_bus.py::publish_workflow_completed`、`process_utils.py::_close_quietly`）→ **J-4 已删**；⑤ `rag/retriever.py` 克隆合并 → 仍范围外 | ④ 经 J-4 死代码清理授权删除（两处零调用，`grep` 确认无残留）；⑤ 用户 F 轮明确排除、J-4 未触及（retriever 行覆盖仍 98.10），如需处理单独授权 |
| **K 轮新登记** | 自身测试套件剩余 **23 个待补存活变异体**（不声称等价） | 3 模块击杀后仍存活 50：可证明等价 5（annotation-only，`from __future__ import annotations`下运行期不求值）+ 强证据实践等价 17（死代码/冗余防御/JSON 转义表示差异，100 组公开 API 差分输入零差异）+ 公开契约外 5（内部异常类型/诊断字段）+ **待补 23**（防御性字符串感知/叶子回退守卫分支，公开 API 差分探测未命中差异）。逐条见 `experiments/results/self_mutation_20261017/survivor_attribution.md`；23 个记为测试强度提升空间，**不得对外表述为"已知等价"** |
| **K 轮已收口** | ~~变异生成器无效变异体（identity/语法非法）~~ → 已修（K-5） | 修复前语料每模块 1 个 identity + 单文件最多 5 个语法非法；修复后 30 文件 4603 变异体 0 invalid/0 identity。存量工件 `mutation_score`/MDO 指标为**旧口径下界**（本轮未重算，已在 `docs/MEASUREMENT_INTEGRITY.md` 第⑤起登记）；cosmic-ray 口径 QuixBugs Mut@k 0.9396 不受影响 |
| **K 轮新登记** | 覆盖率对账容差 ±0.10pp 仍偏宽 | K 轮干净全量：登记 96.47/92.57 与实测逐位一致（16369/16968、5782/6246）；killed 后仍不收紧——理由同 H 轮（防回退由 ratchet 独立把守；跨 CI runner 抖动上界未观测足够样本）。收紧动作留待 ubuntu 档连续零漂移观测后执行 |
| **K 轮已收口** | ~~文档链接无任何检查~~ → G16 门禁（K-2） | 109 文件/528 链接/0 错误；allowlist 0 条；CI 阻断步骤 + `make docs-check` 双入口 |
| **K 轮已收口** | ~~孤儿嵌套测试进程泄漏（实测 2 进程 × ~7h CPU）~~ → 巡检器 + preflight 阻断项（K-6） | `detect_orphan_procs.py` 四条件识别（宁可漏报不误杀）；`--kill` 两阶段终止；ps 不可用显式"不判定"而非"零泄漏" |
| **需外部输入** | Scholarship 对话表（5–8 篇 anchor 文献） | 需一手核验的书目/DOI；未核验不得写入参考文献 |

## 5. 口径与术语纪律（对外引用强制）

| 纪律 | 权威落点 |
|---|---|
| δ 多代际：`−0.3673`（E2，n=174）/ `−0.279`（三种子合并，n=261、配对 240）/ `−0.253`（E6）**禁止混引** | `BASELINE.yaml caliber_labels` |
| repair 修正口径 = **39.31%（v2）**；35.86%/48.11% 为伪影下界，不得单独引用 | `docs/design/repair_caliber_matrix.md` |
| false_fix 双口径（边际 59.58% = 143/240 / 条件 100% = 143/143），引用必须带口径标签 | 同上 + 锁定测试 |
| "gold 独立裁决" = **判据材料独立**（自动化 oracle），**无人工裁决**（全仓无 Kappa） | `BASELINE.yaml terminology_scope` |
| `success`（自指通过率）**不得单独引用**，必须与三指标并列 | `README.md` 基准指标节 |
| SWE-bench Lite 的 `pass_rate` **不得引用**；该数据集只能出现在 Limitations 与复跑清单 | `experiments/results/emse_swebench_disclosure.md` |
| 匹配子集两种口径：**严格**（pattern×seed，29 行/25 可测）与宽松（仅 pattern，62/55）——引用必须标明 | `docs/VALIDITY.md` + 门禁 `check_t10_docs` |
