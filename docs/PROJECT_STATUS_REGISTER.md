# 项目状态与决策登记册（Status & Decision Register）

- 最后更新：2026-10-17（df_spec 实验（P1 主实验）实跑 + 判定 `not_confirmed`（方向为负的显著证据）+ 判定契约 25 例入库；§1 快照随 `BASELINE.yaml` 同步至当日终态）
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

## 1. 现状快照（2026-10-16 I 轮实测，CI 同口径）

| 维度 | 数值 | 验证入口 |
|---|---|---|
| 全量测试 | **6784 passed / 5 skipped / 0 failed**（登记口径 = collected 6789 − skipped 5；2026-10-17 沙箱实跑 500.83s：6782 passed / 2 failed 全**非代码回归**——① BASELINE 自指（随本行刷新转绿）② ps 被禁（环境已知项）；本轮净增 25 例 = df_spec 判定契约） | `pytest tests/ -q -n 4 --dist loadfile` |
| 总行覆盖 | **92.96%**（15748/16941；**连跑两次逐行比对零漂移**，见 §4 已收口条目；ratchet 水位 92.90，余量 +0.06pp） | `make test-cov` + `scripts/gates/coverage_ratchet.py --check` |
| 总分支覆盖 | **87.62%**（5464/6236；**连跑两次逐分支比对零漂移**〔3118 个分支点全同〕；水位 87.50，余量 +0.12pp） | 同上（`--cov-branch`） |
| 静态硬下限覆盖 | 达标（行 ≥85% / 分支总 ≥77% / 核心路由 ≥85–90%） | `scripts/gates/check_branch_coverage.py coverage.xml` |
| 门禁总数 | **24 道全绿**（口径 = `ci.yml` 主工作流**逐提交阻断的门禁检查步骤**，不含测试执行本身；可枚举复算）【2026-10-16 勘误：原记"17 道（14 硬门禁 + 引用可追溯性 + 覆盖率棘轮 + 分支硬下限）"——"14"无出处、citations 在 CI 中实为非阻断周检、与独立评审/投稿骨架的"24"口径分裂；`scripts/gates/` 目录现为 25 脚本（CI 接入 23 项），主工作流阻断检查步骤实为 24，已按实测收口】 | `make gates`；逐项见 §3 |
| 静态检查 | ruff 全绿 / 702 文件已格式化 / mypy 0 错（133 源文件） | `ruff check .`、`ruff format --check .`、`mypy src/ config.py` |
| 构建基线 | `BASELINE.yaml` 与实测逐位对账（含守卫 `TestBaselineNumbersConsistency`） | `pytest tests/test_2026_10_10_optimization_batch.py -q` |

> 一致性提示：**任何一项数值漂移都会让对应门禁转红**。覆盖率余量仍属薄（行 +0.06pp、
> 分支 +0.12pp），因此本表不允许手工维护——它必须随 `BASELINE.yaml` 同步刷新。
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
| 覆盖率棘轮偏差"关闭记录"（16 批轨迹） | `docs/EMSE_COVERAGE_RATCHET_DEVIATION.md` | `coverage_ratchet --check` 全绿 |
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
| **df_spec 实验（P1 主实验，2026-10-17 凌晨实跑）**：预注册 + 判定口径**跑批前**锁定（`EMSE_DF_SPEC_PREREG_2026-10-16.md` sha256 `a19a6c29…` → 承诺于 `cd514d2`；分析脚本 25 例测试同批入库）→ QuixBugs 双臂同批实跑（50/50 锚命中 `attempted_replaced`、独立 namespace、logic 档 temp=0、双 provenance `git_dirty=false`）→ **`not_confirmed`（方向为负的显著证据）**：df_spec **54.3%（19/35）vs df 77.8%（28/36）**、配对 **1:10**、δ=**−25.7pp**、双向精确 p=**0.0117**、BF10=16.4；over_red 占比 **46.0% vs 22.5%**（预注册预期 −30%，实测反向上升 104%）；预注册三条件全未满足、失败线（<50%）未触发。机制假设（锚材料=对缺陷代码的再描述，非独立正确规格）标注"待检验"，见分层叙事 §9 | 工件 `experiments/results/emse_df_spec_20261016/`（两臂 JSON + `DF_SPEC_REPORT.json` + README + SHA256SUMS 104 项校验通过） | `python -m experiments.emse_df_spec_analysis --dfspec … --df …`；`pytest tests/test_emse_df_spec_analysis.py -q` |

## 4. 遗留缺口（按"是否值得继续"分级）

| 分级 | 缺口 | 说明 |
|---|---|---|
| **建议做** | B5 文本目检（清单/哈希锁已就绪，2026-10-16 呈交） | B6 已执行（8c2b655）；A-10 df_spec 臂已落地（6ddd1ca）；A-11 冻结 ADR-0034 |
| **可做** | `graph/nodes.py` **155** 行、`agents/executor_repo.py` **118** 行、`graph/orchestration_search.py` **74** 行（未覆盖行数，I 轮按 `coverage.xml` 复核**三项均无变动**；nodes.py 分母由 697 增至 **701**——I2/I2b 新增 4 行全部被新测试覆盖，故未覆盖行数仍是 155、比率 0.7776→**0.7789**。nodes.py 此前给"149–155"区间**因测量非确定**，H1/H5/H6 收口后已确定为 155——上升的 6 行是"不再因 env 残留意外覆盖"，非覆盖退步。executor_repo 由 101 升至 118 系 G 轮新增守卫代码所致） | 均属"配置门控装配/长链"，单模块约 30–50 例的成本。⚠️ I 轮后覆盖率余量为 **行 +0.06pp / 分支 +0.12pp**（F 轮所记 +0.40/+0.37pp、H 轮所记 +0.04/+0.08pp 均已过期），补测的边际收益**上升**而非递减——水位只升不降，任何回退都会直接转红 |
| **低优先** | `agents/debugger.py` 76 行 | LLM 调用链，需 mock 编排，测试价值低于其维护成本 |
| **H 轮已收口** | ~~覆盖率测量非确定性~~ → **三处独立噪声源全部定位并消除**（§3.2 **H1 / H5 / H6**） | G 轮登记的"成因未定位"本轮完整收口。**排查顺序与结论**：先排除 xdist 分组、随机路径、并发超时（均非成因）；① **H1 主因**＝`config` 在 import 期用 `setdefault` 注入档位开关、既绕过 monkeypatch 也无 teardown，加上两处测试**手抄**的还原清单均已过期 → 6 个开关键跨测试残留 → `nodes.py` 在 0.7776/0.7862 间摆动（特异性门块内 6 行）。② 修掉①后逐行比对只剩 **2 行**（`spec_ir_v2.py` 晚期 parse 门），定位为**只有 hypothesis 模糊测试碰运气才命中**；补确定性用例时反被模糊测试抓出**真门漂移**（H5，反例 `"0,"`）。③ 再修后只剩 **1 个分支**（`api_manager.py:1068` 双重检查锁竞态弧），由既有 8 线程用例的调度运气决定，已钉成确定性（H6）。**终局证据**：连跑两次 CI 口径全量，`coverage.xml` 逐行 + 逐分支比对**零漂移**（16934 行 / 3116 分支点全同；行 15739/16934=92.9432%、分支 5458/6232=87.5802% 两次逐位相同）。**方法论教训**：噪声不是单一根因——修掉最大的一处只把不确定性从"6 行"降到"2 行"再降到"1 分支"，**必须逐层比对到零**才算收口 |
| **H 轮遗留（口径精修）** | G6 的 **±0.10pp** 对账容差现已偏宽 | 该容差是按"含噪声观测"的抖动上界（≈2×）定的；噪声源全部消除后，理论上可回到逐位相等口径。**本轮不收紧**：① 防回退不靠容差，靠 `coverage_ratchet.py` 的只升水位；② 收紧需要多轮干净复跑重测抖动上界（跨主机/跨 CI runner 仍可能有差异，见下条跨平台风险）；③ 收紧的收益只是口径更严，风险是把"常年假绿"换成"随机真红"（G6 勘误二的原教训）。处置建议：先在 CI 的 ubuntu 档观测数次，确认跨平台也零漂移后再收紧 |
| **H 轮新登记** | 装饰守卫审计的**残余 2 项** | 本轮按"有实现 + 有单测 + 有开关，但**零生产调用点**"口径全仓审计，命中 3 项、修 1 项（H3）。残余：① `src/agents/deterministic_guard.py::guard_generated_test` 生产调用 **0**（仅测试）——它只是 `scan_test_file` 的薄包装，后者已在 `nodes.py` 接线，故**不是防护缺口**，属死代码（与用户 F 轮排除的 ④ 同类，未获授权不动）；② `src/tools/patch_applier.py::safe_apply_patch_contract` 全仓 **0 调用 0 测试**——同为死代码，契约检查实际经 `check_naming_contract` 接线。两项都**不影响安全性**，处置需死代码清理授权 |
| **H 轮新登记** | 嵌套 pytest 环境隔离只修了 **2/7** 处 | H2 修的是 `src/` 与 M1 判分层（测量结论的直接来源）：`experiments/_m1_metrics.py`、`src/measurement/mdo.py`。按"子进程命令里确有 `-m pytest`"口径复核，剩余 **5 处 / 4 文件**仍用 `env={**os.environ, ...}`：`gold_consistency_pruning.py:116`、`mutation_testing.py:1602`、`suite_repair_pipeline.py:114`、`emse_testlevel_detection.py:382` 与 `:1282`（后两处还把自写插件物化进 tmpdir 并靠 `PYTHONPATH` 加载，与宿主 `PYTEST_PLUGINS` 叠加时同一机制）。另有 3 处 `**os.environ` 起的是**纯 python 探针**（`solver_directed_trigger.py:247`、`spec_ambiguity.py:280`、`mdo.py:298`），不受影响，不计入。这 4 个文件是批次驱动、已冻结用于既有发表数字，且干净环境下 `nested_pytest_env` 与旧写法逐位等价，故本轮不动（避免给已冻结工件加无关 diff）；后续统一收敛时直接换 `nested_pytest_env` 即可 |
| **I 轮已收口** | ~~`src/observability/failure_taxonomy.py` **无生产消费方**~~ → 已接批次落盘（§3.2 **I1**） | G 轮登记为"功能缺口而非缺陷"，本轮补齐末端：per-task 行 4 键 + 臂级 `failure_bucket_distribution` + 报告层分母披露。接线过程又暴露两处**读侧分支不可达**（I2b 标记被默认计划替换吞掉、I3 `unknown` 抢占弱信号），均已修 |
| **I 轮已收口** | ~~`m10_leaf_fallback` **只写不读**（1 写侧、0 读侧）~~ → 已抬顶层 + 落盘（§3.2 **I2 / I2b**） | ADR-0032 的可分离性现为**可机读**：两个顶层标记的组合直接区分"提取器误诊"与"LLM 真未输出"，且随批次工件落盘。无需再把 ADR-0032 降级为"设计意图" |
| **I 轮新登记** | 桶归因与交互边归因存在**有意的不对称** | `logic_degraded` 弱信号命中时 `failure_bucket=specification_failure`，但 `attribution_edge/fault_side` 仍为 `uncategorized`：弱信号只够判定"失效在规约层"，不足以钉出**哪条交互边**、更不足以判定故障侧——若强行归给 `planner_to_generator + model_side`，恰好会把 I2b 那类"提取器（harness 侧）误诊"记成模型侧问题，属编造归因。**后续可做**：`m10_leaf_fallback=True` 正是把这类行判为 `harness_side` 所需的那条证据（ADR-0032 的原意），但把它接进 `interaction_attribution` 是一条**新的归因规则**（新的科学主张），需独立论证与 A/B，不宜与本轮的"接线"混为一谈 |
| **I 轮新登记** | `run_benchmark()` 内三个既有聚合器仍是**嵌套函数**，口径无法被单测钉住 | `_aggregate_rag_metrics` / `_aggregate_token_metrics` / `_aggregate_failure_categories` 都定义在 `run_benchmark()` 内部，只能靠端到端跑批间接覆盖。I1 新增的 `_aggregate_failure_buckets` 因无闭包依赖已提到模块级（分母口径 `total` vs `total_rows` 是最容易读错的地方，必须可测）。三个既有聚合器同样可以外提，属纯结构调整，但会碰到已冻结实验文件的 diff 面，故本轮不动 |
| **G 轮已知代价** | C5 片段扫描的 fail-closed **保守假阳性** | 补丁片段加脚手架后仍解析不出 → 拒绝应用。方向是刻意的（G 轮决策：一律 fail-closed），代价是**可能拒掉良性补丁**，表现为 repair 成功率下界被压低。若后续观测到误拒率显著，处置是补脚手架形态而不是改回"读不懂即放行" |
| **G 轮已知风险** | G6 对账的**跨平台**余量 | 登记册 §1 声明的是 darwin 实测；ubuntu 档若与声明相差 >0.10pp，`Status register coverage reconciliation` 会转红。该红属**真阳性**（文档↔工件分裂），处置是按 CI 的 `coverage.xml` 刷新 §1，**不得**放宽容差或删步骤 |
| **可做** | 布尔口径残留分裂 **11 处**（G 轮全量复核；F 轮记的"10 处"漏了 2 处、又移出 1 处）：负集式 `not in ("false","0"[,"off"])` **5** 处（`CFG_ANALYSIS_ENABLE` / `PATCH_PROTECT_REPO_CORE` / `EVENT_BUS_ENABLE` / `DETECTION_FIRST_SECTION_ENABLE` / `P2P_GATE_ENABLE`）、单值否定式 `!= "false"` **1** 处（`EMPTY_PATCH_GUARD`）、opt-out 式 `!= "0"` / `== "0"` **4** 处（`AITESTER_AGENT_REUSE` / `AITESTER_EXECUTOR_AGENT_CACHE` / `AITESTER_LLM_CACHE` / **`AITESTER_CACHE_ISOLATE_MODEL`**〔F 轮漏记〕）、opt-in 单值式 `== "1"` **1** 处（**`EXECUTOR_RLIMIT_AS_FORCE`**〔F 轮漏记〕） | **G 轮已为守卫类开关定调**：安全守卫一律保留**负集口径**（垃圾值 → 守卫保持开启，天然 fail-closed；正集口径会把 `=ture` 拼错当成"关闭守卫"），参考实现 `src/tools/dependency.py::conftest_ast_scan_enabled`（含口径理由）；`CONTEST_AST_SCAN_ENABLE` 已据此从"待定调"移出。**剩余 11 处属非守卫开关**，合并到 `env_flag` 会改变垃圾值语义（判 True → 判 False，opt-in 式则是 `=true` 由 False 变 True），需按开关逐个定调后再动。复核命令：`rg -n "(os\.getenv|os\.environ\.get)\([^)]*\).*(not in|!=|==)" src/`（实测 12 行 = 上述 11 处 + 已定调的 `CONTEST_AST_SCAN_ENABLE`）。`config.py::_parse_int_env/_parse_float_env` 同理未并入 `env_int`（20+ 调用点、已锁测试，且并入会改 logger 名＝可观测行为变更） |
| **I 轮已收口** | ~~`CHANGELOG.md` 缺 **F / G / H / I 四轮**条目~~ → **已补写**（2026-10-16，按轮分节 + 逐条验证命令 + 未回填任何未实测数字） | 双语同步：`CHANGELOG.en.md` 对称补入四节（两文件各 107 个 `##` 节、日期行同步至 2026-10-16）；`check_bilingual_docs.py --strict` 零警告零失败 |
| **本轮范围外** | ④ 死代码（`event_bus.py::publish_workflow_completed`、`process_utils.py::_close_quietly`）⑤ `rag/retriever.py` 克隆合并 | 用户在 F 轮明确排除（④⑤不在批准范围内），G 轮沿用；如需处理请单独授权 |
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
