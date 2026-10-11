# T3 领域架构专项诊断（红队版）

> 审查对象：AITester @ `/Users/wangchenyu/Workspace/AITester`（工作树，2026-10-10）
> 审查立场：**红队式挑战框架本身**，而非在其自设框架内挑错。
> 约束遵守：只读；未修改任何仓库源文件；未运行任何调用 LLM 的脚本（本报告全部证据来自源码/文档/工件静态阅读）。
> 证据口径：每条结论给出 `file:line`；未能读到实现的位置一律标注"**需进一步核验** + 核验方法"，不做行为推测。

---

## 0. 事实底座校准（先纠正 3 处口径，再进入评审）

任务简报与仓库登记之间存在三处需要先对齐的数字/语义，否则后续全部论证会踩空：

| # | 简报写法 | 仓库实际 | 证据 |
|---|---------|---------|------|
| C1 | `spec_compile_rate 0.47–0.52` | 该值**不是对外登记的基线**，而是 S6 接线生效后的单批证据；对外登记的 `target_quality.spec_compile_rate` 仍是 **0.205–0.219**（E1/E2 logic 档四批次），条目自注目标 ≥0.55 未达 | `BASELINE.yaml:68-70`；`BASELINE.yaml:488-499`（"spec_compile_rate 由历史 0.205–0.219 升至 0.472–0.517"） |
| C2 | `spec_compile_rate` 的语义 | 它**不是**"规约被机器化的比例"，而是 expr 通道内**编译器接受率**（可解析 + 过白名单）；覆盖意愿由正交指标 `spec_expr_coverage`（0.723–0.741）承担 | `src/specs/spec_ir_v2.py:553-601`（rate 定义）、`:604-616`（coverage 定义）、`BASELINE.yaml:71-72` |
| C3 | "逻辑驱动 CEGIR 反例回灌闭环"（README"最新优化"行） | 该模块**明确声明不接入主链路**："本模块是**独立可调用能力**……不接入主链路（Planner/Generator 调用点的接入属后续批次）" | `src/specs/spec_refine.py:28-30` |

**红队基调**：本项目最稀缺的品质是"自我批判的记账纪律"（4 起测量伪影自曝、A1 假阴性自曝、负结果不筛选）。但**记账诚实 ≠ 框架正确**。以下 8 维评审的核心问法是：*如果把这些自我披露全部当真，它剩下的主张还站得住吗？*

---

## 1. 逻辑驱动：一个"表达式锚点"被写成了"逻辑驱动系统"

### 1.1 现状（file:line）

**规格语言的实际表达力**（`src/specs/spec_ir_v2.py`）：

- 允许的调用名闭集仅 12 个：`len/abs/min/max/round/float/int/str/sorted/any/all/isinstance`（`:63-65`）；属性仅 `value/real/imag`（`:69`）。
- 子句必须是**单条 Python 表达式**且整串落在 ASCII 字符白名单内（`:89` `_EXPR_TOKEN_RE`；`:92-124`）。
- 编译产物是逐条 `assert <expr>`（`:231`），绑定上下文为 `{r} ∪ 签名参数`（`:308-311`）。
- 不可编译子句降级为 `# NL provenance` 注释（`:324`、`:338`），不产占位 `assert True`（`:27-29`）。

**判定：这套"逻辑"是受限命题/单输入算术表达式层，缺四项"逻辑驱动"通常意味着的能力**：

1. **无量化**。匿名审查：`all()`/`any()` 虽在白名单（`:64`），但 `_compile_single_clause` 会把推导式绑定变量当未知标识符拒绝（`:227-230` `identifiers - base_known`；`base_known` 只含 `r` + 签名参数 + 白名单名，`:308-311`）。因此 `all(x > 0 for x in arr)` 除极偶然的同名参数外**必然降级**。
2. **无关系/无抽象数据类型语义**。无数组/映射/记录理论、无未解释函数——调用用户自定义函数直接不可编译（`BASELINE.yaml:543-544` 自注"剩余阻塞为调用未白名单用户函数"）。
3. **无时序/无状态机语义**。无 `always/eventually/until`，无 trace 级性质；`invariant` 被**语义弱化**为"给定边界输入时成立"的单点断言（`:329-330` 逐字注释："invariant = 任意输入下的性质，保守编译为'在边界输入下成立'——不臆测全输入域"）——这一弱化同时是**假阳性来源**：把 ∀ 性质的断言落到一个任意边界输入上，正确实现也可能被判红（见 §5.4）。
4. **无可判定性/复杂度论证**。仓库无任何关于该片段的判定过程、可满足性上界或复杂度说明；`SPEC_SMT_*` 只覆盖前件 SAT 与后件一致性（`src/specs/spec_smt.py:459-560`、`:654-711`），且在有限整数/实数排序上做（`:207` `_infer_sorts`、`:322-390` `_translate`），本质是**约束求解辅助**而非规格语义层。

**白名单实现的表述与实现不一致**（可被审稿人一句话击落的点）：模块 docstring 宣称"白名单 AST 节点子集（比较/布尔/算术/常量/函数白名单调用/容器下标·长度）"（`:11-13`），但 `_WhitelistVisitor` 只对 `Call`（`:146-156`）与 `Attribute`（`:158-162`）收集违例，其余全部走 `generic_visit`（`:168-170`）——**它是两个节点种类的黑名单，不是节点种类白名单**。`Lambda`/推导式/`IfExp` 等节点本身不被拒绝，只被后续的标识符集合间接拦下（`:227-230`）。结论：**安全边界依赖"未知标识符拒绝"这一条，而非文档宣称的节点白名单**（该结论可由 `tests/` 现有白名单用例反证核验：构造 `sorted(a)[0] if a else []` 观察 `_whitelist_check` 返回空列表）。

### 1.2 "逻辑驱动"主张与实测之间的差距

| 环节 | 实测 | 证据 |
|---|---|---|
| LLM 是否愿意产出表达式子句 | `spec_expr_coverage` 0.723–0.741 | `BASELINE.yaml:71-72` |
| 产出后被编译器接受 | `spec_compile_rate` 0.472–0.517（S6 后，单批证据）；登记口径仍 0.205–0.219 | `BASELINE.yaml:488-499`；`:68-70` |
| 编译器可否编译出非空 oracle | 真实 Planner 规约 427 条离线可达性：含 `*_expr` **28.8%**、子句过 AST 90.0%、过白名单 73.3%、**端到端非空 18.7%（上界）** | `BASELINE.yaml:502-506` |
| 真正注入到测试文件 | 合成集 **2–3/87 ≈2.3%**；真实 QuixBugs **20/50 = 40%** | `BASELINE.yaml:489`、`:500-501` |
| 注入后的检出贡献 | 合成集注入行 detection **全部为 0**；作者自注"**无暴露，非无效应**" | `BASELINE.yaml:492-493`、`:507` |

**两个结构性缺陷使上述数字无法支撑"逻辑驱动"之名**：

- **度量通道 ≠ 消费通道（历史已发生，且后果未清算）**：S6 修复前的实际状态是"编译器 10 批 1,997 行臂中可执行规约 oracle 注入 **0 行**（'逻辑驱动'从未真正运行）"（`src/specs/spec_ir_v2.py:284-291` 逐字）。也就是说，`spec_compile_rate` 曾被作为一个**没有任何消费端**的指标对外登记（`BASELINE.yaml:104-105`）。这是继 4 起测量伪影之后的**第 5 类系统性风险：指标—通道脱耦**，而项目尚未把它制度化（无"指标必须有消费点"门禁；S6 是靠人读代码发现的）。
- **注入后的检出贡献不可归因**：oracle 代码被**合并进** `generated_test`（`src/graph/nodes.py:847`），状态里只留一个布尔 `spec_oracle_injected`（`:864-865`、`src/graph/state.py:407`），而该键**不在** M1 `metrics_schema`（`BASELINE.yaml:141-151`）中，实验层也无消费者（`grep -rn spec_oracle_injected --include=*.py` 仅命中 `nodes.py` / `state.py`）。M1 的 F2P 判定对合并后的文件执行（`experiments/_m1_metrics.py:519-523`）——**注入 oracle 造成的红与 LLM 断言造成的红在结果行里逐位同构**。因此"逻辑驱动通道的确定性检出"这一主张目前**不可证伪也不可证实**：`SPEC_ORACLE_EXEC_ENABLE`（`BASELINE.yaml:110-112`）打开后系统会跑它，但没有任何一行指标能把它单独摘出来。

### 1.3 与 2025–2026 前沿的差距

- 前沿的"规约/契约驱动"路线（Design-by-Contract + 反例精化，如 icontract/CrossHair 生态；`src/specs/spec_refine.py:11-14` 自引 Balestra et al. ICST 2026、SpecPylot）要求：可编译契约→运行时监控→**反例回灌收敛**。本项目三环里**第三环未接线**（`:28-30`），第二环无独立可观测性（§1.2），只剩第一环的"接受率"数字。
- 前沿的 SMT 用法是**把程序语义编码进求解器**（bounded symbolic execution / path constraints）；本项目 z3 只用于**规约前件的模型生成**与后件一致性检查（`src/specs/spec_smt.py:459-560`、`:654-684`），并在见证生成后**用 Python 语义复核**（`:495-517`）——设计上诚实（避免 z3/Python 语义分歧造成假见证），但能力边界是"举例器"而非"验证器"。

### 1.4 具体可执行改进

| # | 动作 | 落点 | 验收度量 |
|---|---|---|---|
| L1 | **给注入 oracle 独立归因键**：结果行新增 `spec_oracle_f2p`（仅在只跑 oracle 文件时的三段判定），与 LLM 断言分离；或至少记录 oracle 断言行数/独立执行 rc | `experiments/run_benchmark.py`（结果行）、`experiments/_m1_metrics.py` | 合成集与 QuixBugs 上"oracle-only F2P 命中率"首次出数；若为 0，则"逻辑驱动"应降级为"规约锚点"表述 |
| L2 | **补"指标必须有消费点"门禁**：`scripts/gates/` 新增检查——`metrics_schema` 中每个键必须在 `experiments/` 或 `src/` 有非测试消费者（静态可达性扫描） | `scripts/gates/check_metric_consumers.py`（新建）+ `.github/workflows/ci.yml` | 该门禁能复现性拦住"S6 之前的 spec_compile_rate"这类孤儿指标 |
| L3 | **补节点种类白名单，或改写 docstring**：把 `_WhitelistVisitor` 改为正向节点白名单（`BoolOp/UnaryOp/Compare/BinOp/Constant/Name/Subscript/Call/Attribute` + 显式拒绝其余） | `src/specs/spec_ir_v2.py:133-181` | 新增测试：`Lambda`/`GeneratorExp`/`IfExp` 必须被拒 |
| L4 | **给 invariant 编译加"弱化披露"或收紧**：当前 ∀→单点弱化会产生假阳性红；建议 invariant 仅在 SMT 见证或参数化多输入下编译，否则降级为 NL provenance | `src/specs/spec_ir_v2.py:328-338` | 度量 `spec_oracle_false_red_rate`＝注入 oracle 在 gold fixed 上失败的比率（可零 LLM 回放） |
| L5 | **CEGIR 接线或降级叙事**：若无力接入，README/ MODEL_CARD 应把"逻辑驱动反例精化闭环"改为"可调用能力（未接线）" | `src/specs/spec_refine.py:28-30`、`README.md:45` | 叙事与代码一致；或接入 Planner 后以 `SPEC_REFINE_ENABLE` 消融给出 detection 增量 |
| L6 | **升一阶/关系文法的门槛化**：给出"路径 D2"的可证伪里程碑（`BASELINE.yaml:70` 自注目标 ≥0.55），并把"无量化"写进 limitation | `docs/design/`（规约语言 spec）+ prereg | 新版本规约语言须附：支持的量词片段、判定过程、复杂度上界 |

---

## 2. 多智能体：不是"叙事退守"，而是"退守后仍未完成归因"

### 2.1 现状（file:line）

**拓扑与调度**：LangGraph `StateGraph`，节点 `planner→generator→executor→(diagnosis)→debugger→patch_applier→executor`（`src/graph/workflow.py:434-561`）；`_should_debug` 条件路由（`:653-720`）；显式 `recursion_limit` 包装（`:889-914`，注释记录历史"Recursion limit of 10007 reached 事故" `:883-884`）。

**通信协议**：**共享 state 字段 + 自由文本**，无结构化消息 schema、无消息历史通道。状态是扁平 `TypedDict`（`src/graph/state.py:14-420`），跨 agent 传递的主力字段是 `diagnosis: str`（`:156`）、`patch: str`（`:158`）、`test_output: str`（`:152`）；Planner→Generator 的"契约"是 `json.dumps(test_plan)` 塞进 prompt（`src/agents/generator.py:408`）。唯一半结构化通道是专家池候选 dict `{dimension, patch, new_code, confidence, expert_failed}`（`src/graph/expert_pool.py:241-242`）。

**角色分化强度**：专家池的"维度专精"实现方式是**把维度提示词追加到 `target_code` 尾部**再走同一个 `DebuggerAgent.debug` 路径（`expert_pool.py:273-293`，逐字："仅把维度标签追加到 system prompt 尾部"/"在 prompt 构建路径的 target_code 参数里追加维度提示"）——即**同 prompt 同行数、多一次采样**，而非不同工具/不同上下文视图。

**共识/冲突解决**：`cross_validate` 对补丁做 AST 归一化后**文本两两一致/子串包含**投票，按 (被验证数, 置信度) 排序（`expert_pool.py:375-383`）；多候选补丁默认**只做静态筛选 + 最小改动优先**（`src/tools/multi_candidate.py:263-284`），执行验证 opt-in（`:286-299`）。

**奖励与策略**：`_compute_reward_signals` 产出 `correctness/efficiency/simplicity`（`src/graph/trace_reward.py:117-150`）并写入轨迹（`:89-113`），注释自述"供执行反馈 RL **备料**"（`:123`）——**无消费者**，不更新任何策略；唯一在环的策略调整是"覆盖率连降→降温度/停滞→换视角"的规则建议（`:153-188`）。

**预算/记账**：cost_budget / token_usage 为线程局部，专家池显式跨线程 attach（`expert_pool.py:258-272`）；**已知缺陷 D2**：缓存命中提前 return 绕过 `record_usage`（`src/agents/base_agent.py:397-407` LRU 快路径、`:452-454` 文件命中路径），导致 E6 matched 臂"两臂 token **0/87 行** → matched cap 无分母"，实验状态"受阻"（`BASELINE.yaml:208-211`）。

**可观测性/可解释性**：自定义 JSONL trace（`src/observability/trace.py:9-20`），字段级摘要截断（`:72-78`，全量 prompt 不入 trace）；`otel_export.py` 是**离线 JSONL→OTel span dict 转换器**，不依赖 SDK、不导出、无告警（`src/observability/otel_export.py:8-21`）；`grep Sentry|alert|webhook` 在 `src/observability/` 下**零命中**。

### 2.2 −28pp 是科学诚实，也是**未完成的归因**：机制假说排序

**既有证据链（全部来自项目自曝）**：

- 三种子主批次：detection `df 44.8% > aitester 15.8% > plain_llm 1.5%`，`aitester vs df δ=−0.279`（`BASELINE.yaml:165-169`）；E2 δ=−0.3673（`README.md:10`）；E6 第三次复现 δ=−25.3pp（`BASELINE.yaml:205-207`）。
- 机制归因（合并报告 + ADR-0016）：**88 行过红测试** + **28 行修复循环抹红**（`docs/adr/0016-orchestration-container-repositioning.md:20-24`）。
- 预算混杂已排除：E6 matched 实验"低预算下 aitester 更差（87/87 触顶）且 df 不受预算约束 → 差异不可由预算分配解释，源于编排结构"（`BASELINE.yaml:599-601`）。
- 采样次数已排除（针对提示协议效应）：RT1 关闭强化段只保留再生成路由 → RT1 11.5% vs plain_llm 10.3%（p=1.0，采样效应可忽略），df vs RT1 +19.5pp（p=0.0001）；结论"**+43pp 归因提示协议本身，非采样次数**"（`BASELINE.yaml:524-540`）。

**结构性根因假设（按可证伪性从高到低排序）**：

| 排序 | 假说 | 现有证据的方向 | 反证/证伪方式 | 成本 |
|---|---|---|---|---|
| **H1（最该先测）** | **Prompt 内容错配**：aitester 的 Generator 收到的是"计划 JSON（含 `expected_output`/`edge_cases`）+ 现有断言 + RAG + 变异反馈"，df 只收到代码 + 协议文本；错配的期望值直接把测试推向"过红" | A1（剥离 plan 的 `expected_output`）在 QuixBugs 上 detection 45.9%→51.4%（+5.5pp，p=0.72 不显著）、首轮 `specific_red 19→21`、`over_red 21→17`——**三项过程指标同向**（`BASELINE.yaml:403-419`）；这是全项目唯一在真实基准上方向为正的干预 | **上下文对齐消融**：保持全部节点/环路/调用次数不变，只把 Generator 的 prompt 载荷替换为 df 的等价载荷（代码+协议文本，去掉 plan JSON/RAG/断言/变异段）。主终点 QuixBugs 41 缺陷程序 detection；预注册判别：若 ≈df 83.8% → H1 成立；若 ≈46% → H1 否证，转 H2 | 中（同调用次数，QuixBugs 单臂约 20 分钟量级，`BASELINE.yaml:307`） |
| **H2** | **环路反噬**：修复循环在非特异红之后仍然消耗预算并产生"抹红/换测试"证据销毁（88+28 行） | 红回归门/特异性门已实现但**默认关**（`src/tools/detection_gates.py:55-66`）；`stop_reason=skip_debugger_repair_invalid` 占 50.0%、`patch_evidence_level=none` 占 48.1%（`docs/adr/0016-orchestration-container-repositioning.md:73-78`） | **拓扑消融**：aitester 只保留 `generator→executor→regenerate`（`allow_regeneration=True`，禁 debugger），与全拓扑对照；预测若 detection 回到 df 量级 → 环路有害；若不变 → 环路无关 | 中 |
| **H3** | **角色间信息损失**：Planner→Generator 的文本 JSON 中转丢失/污染语义（D1 实证：39% 任务 Planner 空计划、30.3% 缓存响应无法 `json.loads`） | `BASELINE.yaml:238-249`：D1 修复后空计划 39.1%→25.3%，但 detection 6.9%→8.0%（p=1.0）→**"空计划"不是 never-red 主因（假说已证否）** | 已部分证否；剩余变体（plan 有内容但语义错误）可由 H1 覆盖 | 低（已完成） |
| **H4** | **上下文膨胀/提示遮蔽**：6.2–8.4× token 使指令被稀释 | token 26.1k vs 4.2k（`docs/adr/0016-orchestration-container-repositioning.md:15-17`）；E6 matched 只封顶**迭代预算**（87/87 触顶），并未压缩**单次 prompt 上下文**（`BASELINE.yaml:590-602`） | 与 H1 同一次消融可分解：H1 的"载荷替换"若有效，则膨胀被证；若无效，进一步做"同载荷加长填充"对照 | 低（H1 的副产品） |
| **H5** | **过早收敛**：首轮全绿→再生成上限/首轮红→修复轮数不足 | `_MAX_REGENERATIONS` 上限保护（`src/graph/workflow.py:660-690`）；over_red 路径无强化段（`BASELINE.yaml:434`） | 已有 `OVER_RED_SECTION_ENABLE` 消融：21→18 过红、detection +5.5pp、p=0.72 → **未见效**（`BASELINE.yaml:438-447`） | 低（已完成） |
| **H6** | **预算被非关键节点消耗** | 已由 E6 matched 证否（`BASELINE.yaml:599-601`） | — | 已完成 |

**判定**：保留编排为"可消融容器"**是科学诚实**（负结果 + 转正判据写死在 ADR，`docs/adr/0016:32-36`），但**不是归因完成**——目前只把 −28pp 归到"编排结构"这一层抽象（`BASELINE.yaml:581`），而"结构"下至少还有 H1/H2/H4 三个可干预变量未分离。**把未分离的机制写成"结构性劣后"是叙事上的二次退守**：它把一个可实验回答的问题（哪一段 prompt/哪一个环）变成了一个不可反驳的结论。

### 2.3 与 2025–2026 前沿的差距

- 前沿共识（本项目自己也引用，`README.md:12-20`）：**手工编排弱于 one-shot 提示协议**（CANDOR [待核验]）；可超越的是**自动搜索编排**（BOAD [待核验]）。本项目的差距不是"没做多智能体"，而是**没有把编排当作搜索对象**：`docs/design/mas_compilation.md`（95 行）仍是 Proposed 探索文档（`BASELINE.yaml:14` 自注"探索性 Proposed"）。
- 通信层面：前沿已转向结构化 handoff（typed artifact / tool-call schema）；本项目仍是**自由文本 + JSON 字符串**（`src/graph/state.py:152-158`、`src/agents/generator.py:408`），这使得"角色间信息损失"无法被静态检测，也无法做 schema 级回归。

### 2.4 具体可执行改进

| # | 动作 | 落点 | 验收度量 |
|---|---|---|---|
| M1 | **上下文对齐消融（H1）落地为预注册实验**，主终点 detection（QuixBugs 41 行口径），判别规则写死在 prereg | `docs/preregistration.md` 新节 + `experiments/run_main_batch.py`（新档位 `AITESTER_GENERATOR_PAYLOAD=df_parity`） | 二元判别结论（H1 成立/否证），无论方向均可发表 |
| M2 | **把 −28pp 的 88+28 行拆成可归因子类**：`specificity_gate_verdict` 增第 4/5 值（`over_red_hang`＝缺陷实现不终止/超时；`over_red_assert`＝断言过苛），零 LLM 可回放 | `src/tools/detection_gates.py:96-121`、`experiments/run_benchmark.py` | 60% 过红被拆开；`over_red_hang` 份额决定"测试侧超时语义"的优先级 |
| M3 | **结构化交接 schema**：Planner→Generator 的 plan 用 pydantic/TypedDict 校验（已有 `_validate_planner_output`，可升级为 schema+版本号），并把"计划字段被 prompt 消费"做成静态不变量测试（参照 AF-D 对 `problem_statement` 的做法） | `src/graph/state.py`、`src/agents/generator.py:394-450` | 新增字段必须先声明消费点；D1 类静默降级可被门禁拦住 |
| M4 | **奖励信号接线或删除**：`reward_signals` 要么用于候选排序（现已有 `predict_candidate_rewards`，`src/tools/multi_candidate.py:497-560`），要么在文档中明确"纯观测"，不再以"RL 备料"表述 | `src/graph/trace_reward.py:117-150` | 若接线：给出 `REWARD_PREDICTOR_ENABLE` 的 A/B 结果 |
| M5 | **token 记账修复（D2）**：缓存命中路径补记 `record_usage`，或把 `cache_avoided_tokens` 纳入预算口径并在 matched 实验中止损 | `src/agents/base_agent.py:397-407`、`:452-454` | E6 matched 臂可获得真实分母；否则等预算对照实验永久不可做 |
| M6 | **编排搜索最小版本**：不做完整 BOAD，先做"算子化编排搜索"（节点子集 × 环路开关 × 载荷档）的小网格，以 detection/成本双目标报告 | `docs/design/mas_compilation.md` → 实验 | 至少给出"自动搜索能否超过手工拓扑"的首个本地证据 |

**追加红队发现（M7，本节最重要）**：生死实验的 `logic` 档**根本没有打开任何"多智能体"组件**。`_PROFILE_PRESETS["logic"]`（`config.py:64-112`）逐项列出的是 SPEC_IR/DSL/SMT/oracle、mutation scoring、oracle 校验、回滚 + fail-closed、strict 校验、确定性守卫、分支覆盖、结构化路由、检出优先协议、双门、FL 谱定位——**不含 `EXPERT_POOL_ENABLE`、`EXPERT_POOL_DEBATE_ENABLE`、`ENABLE_RAG`、`RISK_APPROVAL_ENABLE`、`KERNEL_SANDBOX_ENABLE`**（`grep EXPERT_POOL|RISK_APPROVAL|KERNEL_SANDBOX config.py` 仅命中 `safe` 档的 `KERNEL_SANDBOX_ENABLE`，`config.py:45`）；专家池默认关（`src/graph/expert_pool.py:128-130`），辩论默认关（`:133-141`），RAG 默认关（`config.py:381`）。

因此 −28pp 的准确表述是"**带规划 + 修复环的单体流水线**在检出口径下劣于单提示协议"，**不是**"手工多智能体编排劣于 one-shot"——被文献批评的角色池/辩论/共识机制在这组决定性实验里是关闭的，从未被检验。README 由"多智能体系统"退守为"可消融容器"（`README.md:9-11`）是一步**过度收缩**：它用一个未检验多智能体组件的实验，给"多智能体"这个更大的标签判了负。**这是叙事退守与科学诚实之间的一处真实错位**（且方向与项目自述相反：它比证据更谦卑，但谦卑错了对象）。

---

## 3. 测试生成：工具链齐备，但四条关键能力"名存实亡"

### 3.1 现状（file:line）

- **生成主链路**：`GeneratorAgent.generate` 组装 prompt＝`json.dumps(test_plan)`（`src/agents/generator.py:408`）＋ RAG 参考（≤3 条，`:31`、`:426-429`）＋ 被测代码现存断言（≤10 条，`:34`、`:440-447`）＋ 检出优先强化段（`:281-282`）＋ 过红强化段（`src/graph/nodes.py:731`）。
- **断言质量检查（静态、3 类）**：恒真断言 / 魔数断言 / 类型不一致（`src/tools/oracle_validator.py:69-74`），仅**观测**写入 `state["oracle_findings"]`（`src/graph/nodes.py:782-796`），只有 `tautological` 一类触发一次强制重生成（`:815-819`）；开关默认关（`oracle_validator.py:60-62`），`logic` 档开（`config.py:72`）。
- **覆盖准则**：仅**分支覆盖**测量（`src/graph/nodes.py:1257-1274` → `src/tools/branch_coverage_inject.py`），Docker 链路不支持（`nodes.py:1263-1265`）。**无 MC/DC、无条件组合、无路径覆盖**。
- **变异测试**：`experiments/mutation_testing.py`（1186 行）算子族＝比较翻转（`:302`）、布尔否定（`:348`）、数值偏移（`:381`）、边界平移（`:433`）、异常移除（`:493`）、返回空/None（`:585`、`:640`）＋异常类型替换（`:814`）。**变异体由 gold fixed 代码生成**（`BASELINE.yaml:113-116` 口径）。合成集上得分接近饱和：aitester 0.818–0.976 vs plain_llm 0.951–0.992 vs df 0.986–0.997，**基线自注"合成集变异体过弱，该指标在此数据集上鉴别力有限"**（`BASELINE.yaml:63-67`）。
- **模糊/差分/符号执行**：无模糊测试（`grep atheris|fuzz` 在 `src/` 零命中）；差分测试仅存在于 `experiments/differential_test.py:2-6`（未接线）；无符号执行——z3 只服务规约前件见证与一致性检查（§1.1）。
- **最小化/去重/优先级**：原语在 `experiments/test_suite_minimize.py`（断言去重 / 失败优先排序 / delta-debugging 最小化，`:1-25`），但**只有 `dedup_assertions` 被接线**（`src/graph/nodes.py:834-839`，且开关 `TEST_SUITE_DEDUP_ENABLE` 默认 false）；`failure_first_order`、`minimize_suite` 全仓无消费者（`grep` 仅命中定义处）。
- **"属性测试"名不副实**：`compile_to_hypothesis`（`src/specs/spec_ir.py:216`）注释自述"R1a 后编译产物**不再依赖 hypothesis**，仅保留探测"（`:283-287`），实际产出**纯 pytest 参数化**代码（`:225`）；`_hypothesis_available` 只是一个探针（`:283-290`）。`.hypothesis/` 目录存在，但那是**本项目自身测试**用的，不是生成物（需进一步核验：`grep -rn "from hypothesis" src/` 仅 `src/tools/dependency.py:85` 的字符串清单）。

### 3.2 差距与红队判断

1. **"覆盖率"这个词在本项目有两套含义**，且对外最容易被误读：`coverage.line_total_pct=89` 是**项目自身源码**的元覆盖（`BASELINE.yaml:22-28` 已自曝 MET-01），被测代码覆盖在 `target_quality` 节（`:53-62`）。红队要点不是"混淆"（它已澄清），而是：**`target_quality` 的两条证据都不支持有效性**——`target_line_coverage` aitester 84.0–93.6% **系统性低于** plain_llm 86.0–97.2%（`:56-62`），mutation_score 在合成集饱和（`:63-67`）。也就是说，"测试生成质量"目前**没有任何一条独立指标显示该系统优于纯提示**。
2. **覆盖准则停留在分支层**：2025–2026 前沿（TestAgent/ULT/CoverUp 一类）已把"覆盖 + 变异 + 断言强度"作为联合目标；本项目的分支覆盖是**纯观测**（`nodes.py:1261` 逐字"纯观测层（不阻断主流程）"），不进入任何路由或门禁。
3. **变异测试的鉴别力问题被正确识别但未解决**：饱和意味着它无法区分 aitester 与 df 的测试质量——而它本应是"生成侧质量"的主裁判。要恢复鉴别力必须提高算子强度（下列 M8）。
4. **去重/最小化/优先级三件套只剩一件，且默认关**（`nodes.py:834`）：这直接影响 prompt 膨胀与执行成本，也直接影响 §2 的 H1/H4（上下文与预算）。
5. **断言类型的盲区**：三类检查全是"弱断言"检测，**没有"过强/过苛断言"检测**——而 over_red 正是过强断言的表现（§5）。这是测试生成与反馈闭环之间缺失的一环。

### 3.3 具体可执行改进

| # | 动作 | 落点 | 验收度量 |
|---|---|---|---|
| G1 | **加"断言强度"双向检查**：弱断言（已有）+ **过苛断言**（断言依赖 gold 未承诺的实现细节/对未定义输入断言异常类型/断言精确字符串），输出 `assertion_strength` 分布 | `src/tools/oracle_validator.py:65-127`（新增第 4 类 finding） | 与 `over_red` 的离线相关性（零 LLM 回放）；预期 over_red 行的过苛 finding 显著更高 |
| G2 | **提高变异算子强度**：补"参数交换/常量替换/语句删除/返回值替换/条件取反后的分支交换"，并在真实基准（QuixBugs）上重测鉴别力 | `experiments/mutation_testing.py` | aitester vs df 的 mutation_score 差距从"饱和无差"变为可分辨（给出效应量与 n） |
| G3 | **覆盖目标入环**：把"分支覆盖未达标"从纯观测升级为一次定向再生成（与检出优先协议同构的定向反馈门） | `src/graph/nodes.py:1257-1274`、`workflow.py` 路由 | 消融：开/关的 detection 与 target_line_coverage 双指标 |
| G4 | **最小化三件套全部接线并默认开（低成本项）**：失败优先排序 + delta-debugging 最小复现子集 | `src/graph/nodes.py`、`src/agents/executor*` | 单任务执行时间与 prompt token 的下降幅度；不得改变 detection |
| G5 | **属性测试要么真做要么改名**：引入 hypothesis 策略编译（`pyproject.toml` 已有 `[formal]` extras 双源，`BASELINE.yaml:14` AR 批次）或把 `compile_to_hypothesis` 更名 | `src/specs/spec_ir.py:216-290` | 若引入：给出"属性测试发现的缺陷数（在合成集植入的变异体上）"；若改名：消除对外误读 |
| G6 | **差分测试接线（低成本高价值）**：合成集已有 buggy/fixed 两版实现，可自动构造差分 oracle 用于验证生成测试的判别力 | `experiments/differential_test.py` → `src/tools/` | 差分命中率作为"测试判别力"的第三把尺子 |

---

## 4. 自修复：漏斗的每一步都在漏，但**漏的地方与项目叙事不同**

### 4.1 现状（file:line）

- **定位**：谱系 Ochiai（`src/agents/fl_spectral.py:295-352`，`compute_ochiai_scores_from_contexts` 为主口径 `:356-381`），Top-k 排序（`:385-403`），prompt 注入（`:405-420`）；LLM 推理定位在 `src/agents/fault_localizer.py`（466 行），结果行含 `localization_hit_function` / `_at_3` / `mrr`（`BASELINE.yaml:124-128`）。FL 默认开（`src/graph/flags.py:204-219`）。
- **补丁生成**：Debugger 整文件重写为主路径；多候选默认只做静态筛选 + 最小改动优先（`src/tools/multi_candidate.py:259-284`）；确定性优先路由 `src/tools/deterministic_repair.py:85-90`（ADR-0019）；编辑意图落盘 `src/tools/patch_intent.py`（ADR-0018）；应用层 `src/tools/patch_applier.py:212-336`（含 `safe_apply_patch:444`）。
- **验证/回滚**：快照 + P2P 全量回归 + 失败自动回滚（`src/tools/patch_rollback.py:240-...`），开关 `PATCH_SNAPSHOT_ROLLBACK_ENABLE` **默认 false**（`patch_rollback.py:81-89`），`logic` 档开（`config.py:73`）且 `PATCH_ROLLBACK_FAIL_CLOSED=true`（`config.py:76`）。
- **弃权**：五信号判定核（`src/tools/patch_abstain.py:40-46`：M5 假通过 / `all_green_unverified` / `over_red` / `patch_evidence_level=none` / `source_patched_unverified`），**仅观测层**，阻断档 Proposed 待 A/B（`patch_abstain.py:28-38`、ADR-0020）。
- **防 test-hacking**：AST 差集检测硬编码输入分支/断言删除/吞异常（`src/tools/patch_test_hacking.py:106-148`），结果行 `test_hacking_suspected`（`experiments/run_benchmark.py:645-668`），观测层。
- **人工门**：`RISK_APPROVAL_ENABLE` 默认 false（`src/graph/risk_approval.py:57-59`），不在 `logic` 档；开启时以 LangGraph `interrupt()` 暂停（`src/graph/debugger.py:839-854`），resume 值消费语义"其余值（False/"reject"）＝丢弃本轮补丁"（`:850-854`）。

### 4.2 "plausible 47% → correct 39%" 漏斗的**口径重算**（本报告的核心定量发现）

项目对外并列的三个数字（`README.md:42`："patch 产出 94%/plausible 47%/correct 39.31%"）**来自三套不同分母**，算术上不可串成一条漏斗：

| 步骤 | 数字 | 分母 | 证据 |
|---|---|---|---|
| 进入修复循环 | 154/261（59%） | R-P0-2 全部任务行 | `docs/adr/0016:73-78` |
| 产出补丁文本 | 145/154（94.2%） | **进入修复循环的行** | `experiments/results/main_batch/repair_ceiling_report.md:18`（表行"patch 产出（patch 非空）145 94.2%"） |
| `patch_plausible=1`（写盘成功） | 72/154（46.8%） | 同上 | 同表 `:19` |
| 离线重放判定 correct | 57/145（39.31%） | **可重放行（另一套口径）** | `docs/design/repair_caliber_matrix.md:20`（行⑤）、`experiments/results/main_batch/corrected_report_v2.md:11` |

在**单一 10 批次底座**（669 行，`aitester`）上重算，漏斗真实形状是（`corrected_report_v2.md:12-15`）：

```
669 行 ──8 无材料──▶ 661 ──395 无补丁──▶ 266 有补丁文本（39.8%）
                                            ├─ 115 correct（43.2% of 266）
                                            └─ 151 wrong_patch（56.8% of 266）
运行时落盘口径另计：plausible 144 行（`corrected_report_v2.md:32`）——与 266 不同源
（前者＝运行时 apply 成功，`experiments/run_benchmark.py:601-617`；后者＝离线重放同一 patch
文本，`experiments/corrected_metrics.py:64-95`）
```

**结论（三条，全部与项目叙事有出入）**：

1. **最大的漏点不在"验证"，而在"补丁根本没落盘"**：266 个可离线重放为 correct/wrong 的补丁文本中，运行时只有 144 行被记为 plausible（`corrected_report_v2.md:32`）——**约 4 成以上的补丁文本在应用/意图落盘阶段丢失**（与 ADR-0018/0019 的立项动机一致）。修正口径的 CPR=84.51%（60/71）说明"被接受的补丁里 84.5% 是正确补丁"（`:33`）——**接受侧已经是高精度的，丢的是落盘侧**。
2. **第二个漏点是"补丁语义错误"，且它与定位质量负相关**：ADR-0024 存量回放给出 P(correct | FL 命中)=**15.79%**（3/19）而 P(correct | FL 未命中)=**64.71%**（22/34）（`docs/adr/0024-counterfactual-fl-upper-bound.md:26-28`）——**定位越准修复越差**，作者正确诊断为难度混杂 + 整文件重写不消费定位信号（`:30-34`）。因此"提升 FL 精度"不是杠杆，**"让补丁生成消费定位"才是**。
3. **成功通道仍不可信**：修正口径 `false_fix = 87.16%`（380/436 passed 行，`corrected_report_v2.md:17-18`）。也就是**系统报告"通过"的 6/7 是假成功**。这意味着 repair 的 39.31% 完全是靠 gold 独立裁决救回来的数字，系统自身的成功信号在该口径下**不可用**。

### 4.3 每一步的改进点与所需机制

| 步骤 | 卡点（file:line） | 所需机制 | 验收 |
|---|---|---|---|
| 定位 | 负相关暴露"定位不被消费"（`docs/adr/0024:26-34`） | **局部编辑强制消费**：补丁必须以"改哪个函数/哪几行"为输出契约，整文件重写降级为兜底（ADR-0018 已有 `EDIT_INTENT_ENABLE`，需给出"接管率 >0 且 correct 不低于对照"的判定，见 `repair_caliber_matrix.md:53-54`） | 定位命中组的 correct 率**反超**未命中组（当前 15.79% vs 64.71%） |
| 补丁生成 | 整文件重写 + 最小改动启发（`multi_candidate.py:263-284`） | **验证导向的候选选择**：把 `use_execution_validation` 默认打开或在有 gold-like oracle 时启用（`:286-299`），并以"隐藏测试"近似（QuixBugs 有官方 gold 测试可用于离线评估，不可入环） | plausible 行中 correct 占比 ≥ 现状 CPR 84.5% 且总量上升 |
| 落盘/应用 | `safe_apply_patch` 失败即回落（`patch_applier.py:444`）；`patch_evidence_level=none` 占 48.1%（`docs/adr/0016:73-78`） | **失败分类学 + 重试**：把 apply 失败按"锚点未命中/语法/多函数冲突"分层，对可机械修复类走确定性通道（ADR-0019 已起步），其余记录为独立指标 | 新增 `patch_apply_failure_class` 行级字段；apply 成功率从 54%→≥75% |
| 验证 | gold 裁决仅存在于实验层（`experiments/_m1_metrics.py:577`）；仓内无 gold | **仓内验证信号**：变异体裁决（把补丁后的代码做变异，检查生成测试是否能杀掉）＋差分（buggy/fixed 双版） | `patch_verified_inrepo` 行级字段与 gold correct 的一致性（κ） |
| 回归/回滚 | 快照回滚默认 false（`patch_rollback.py:81-89`），仅 `logic` 档开 | **默认安全档**：把 `safe` 档设为含回滚 fail-closed + 内核沙箱的发布默认（`config.py:44-51` 已存在，只是不默认） | 发布默认下"坏补丁不得留在工作树" |
| 弃权 | 观测层（`patch_abstain.py:28-38`） | **转正判据落地**：弃权精确率 85.97%（`corrected_report_v2.md:35`）已高于 ADR-0020 门槛描述，可做 A/B 阻断档 | 阻断档下 false_fix 下降且不压制 correct（CPR 不变） |
| 人工门 | 默认关且不在 `logic` 档（`risk_approval.py:57-59`） | **分级默认**：对"跨文件/高风险/低置信"任务默认 `human_confirm`（而非全局默认关） | 默认档下高风险任务 100% 有 pause 记录 |

---

## 5. 反馈闭环：+43pp 是真的，但"先红后绿"的代价被低估了一半

### 5.1 现状（file:line）

- **协议实现**：首轮红灯观测（`src/graph/nodes.py:1210-1216`）、三值终态（`_derive_detection_first_status`，`:498-...`）、强化段（`_detection_first_section`，`:391-418`）、终态从全绿→regenerate 路由（`src/graph/workflow.py:660-690`）。
- **双门**：特异性门（首轮红在 gold fixed 上对照 → `specific_red`/`over_red`/`unavailable`，`src/tools/detection_gates.py:96-121`）与红回归门（恢复红证人，`:124-...`），默认关（`:55-66`），`logic` 档开（`config.py:104-105`）。
- **over_red 强化段**：`_over_red_section`（`src/graph/nodes.py:429-488`），开关默认 false（`BASELINE.yaml:436`）。
- **奖励**：`correctness/efficiency/simplicity` 纯观测（§2.1）。
- **停止条件**：`StopReason` 枚举 + 单点判定（`workflow.py:100-214`），并自曝过一个可观测性缺陷："条件边函数拿到的 state 是副本 → `final_state["stop_reason"]` 恒为初始值 None，结果行的 stop_reason 列全空"（`:191-198`），已用 `effective_stop_reason` 兜底（`:187-214`）。

### 5.2 直接回答："45.9% vs 83.8% 的根因是 over_red，还是协议本身激励苛刻断言？"

**证据链给出的答案是"两者都有，但都不是主因；主因在生成侧"**：

1. **协议本身确实激励苛刻断言**——项目自己在 ADR 里承认该风险（`docs/adr/0015-detection-first-protocol.md` 后果节"LLM 可能为'变红'而写过苛断言"），且 df 臂（同一协议文本、单提示）首轮 over_red 也有 30%（15/50）（`BASELINE.yaml:432-433`）。
2. **但协议不是 45.9% 的原因**：df 用**同一份协议**拿到 83.8%（`BASELINE.yaml:381-386`）。协议变量的效应是 +43pp 正效应（`BASELINE.yaml:524-540`，且 RT1 已排除"多一次采样"解释）。
3. **架构把 over_red 翻了一倍，而"红得是否特异"几乎完全决定检出**：首轮分组统计——aitester `over_red 30/50（60%）`／`specific_red 19/50（38%）`；df `over_red 15/50（30%）`／`specific_red 34/50（68%）`；**两个臂内部，over_red 组的 detection 均为 0%、specific_red 组的 detection 均为 100%**（`BASELINE.yaml:429-433`）。即"红得不特异"与"检不出"在当前测量下几乎同义，而多出来的那 30pp 过红归因于架构（planner 计划载荷 / 环路 / 绑定材料），不是协议文本。
4. **双门并未解决它**：E4 修正结算是**双门开启**口径（`BASELINE.yaml:300` "logic 档 / 双门"），aitester 仍 45.9% vs df 83.8%（p=0.0005，`BASELINE.yaml:381-386`）。因此"环路反噬"（H2）是次级机制，**主因必须在首轮生成**（H1）。
5. **还有一类 over_red 任何协议都救不回**：4 个 QuixBugs 任务（bitcount/find_first_in_sorted/sqrt/wrap）的缺陷实现**永不返回**，判分层 120s 超时 → detection=None（`BASELINE.yaml:462-473`，一手证据：bitcount 缺陷 `n ^= n - 1` 对任何 n 不终止）。作者已把结论收敛为"over_red 里相当一部分是缺陷实现不终止（挂起），再好的 prompt 也无法让挂起的测试变红；**需测试侧超时判定**"（`BASELINE.yaml:454`）。

### 5.3 与前沿的差距

- 前沿的"红-绿证据链"通常配套**测试侧超时语义**（per-test timeout → 判定 hang 而非 fail）与**断言强度度量**；本项目两者都缺：超时是**执行层**的统一 30s/120s（`BASELINE.yaml:271-273`），不区分"测试挂起"与"断言失败"；断言强度无指标（§3.2 第 5 点）。
- 收敛性理论层面：`over_red` 路径在修复环里**不可恢复**（首轮 over_red 无强化段，`BASELINE.yaml:434`；补丁后新增强化段实测 21→18、p=0.72，`BASELINE.yaml:443-445`）——项目自己给出了"两个 prompt 方向均停在 +5.5pp，未触及主因"的结论（`:454`）。这是一个**已证否的干预族**，值得在论文中作为负结果写入。

### 5.4 具体可执行改进

| # | 动作 | 落点 | 验收度量 |
|---|---|---|---|
| F1 | **拆 over_red 为三类**：`over_red_hang`（执行超时/不终止）、`over_red_assert`（真过苛）、`over_red_plan`（期望值来自错误计划） | `src/tools/detection_gates.py:96-121`、`experiments/_m1_metrics.py`（超时信号） | 60% 过红被拆开；`over_red_hang` 占比直接决定 F2 优先级 |
| F2 | **测试侧超时语义**：per-test timeout → 记 `test_hang`（不计入"红"，也不计入"绿"），并在判分层把 hang 作为独立终态而非 None | `src/agents/executor*`、`experiments/_m1_metrics.py` | 4 个恒不终止任务从 detection=None 变为可判定；`None` 行数下降 |
| F3 | **注入 oracle 的假红度量**（与 L1/L4 同一件事，闭环侧视角）：度量"规约 oracle 在 gold fixed 上失败"的比率 | `experiments/`（零 LLM 回放） | `spec_oracle_false_red_rate`；若 >0，它本身就是 over_red 的一个来源 |
| F4 | **奖励接线**：把 `reward_signals` 用于再生成/候选排序（现仅落轨迹） | `src/graph/trace_reward.py:117-150` | 开/关消融的 detection 与 token 双指标 |
| F5 | **把"已证否的干预族"固化**：`OVER_RED_SECTION_ENABLE`、A1 strip 两条负结果写进 prereg 的"不再重复"清单 | `docs/preregistration.md` | 防止后续批次重复烧预算（两次干预各 ≈0.7M token 量级，`BASELINE.yaml:307`） |

---

## 6. 评估与基准：方法学一流，**证据基础是最大单点风险**

### 6.1 基准构成（全部一手核验）

| 基准 | 规模 | 性质 | 主结果 | 证据 |
|---|---|---|---|---|
| 合成集 | 50 模板 / n=87 | **模板即分布**：每个模板把 buggy+fixed+gold 测试写在同一个 dict 里 | aitester 9.2% vs df 34.5%（E6） | `src/datasets/synthetic_dataset.py:32-54`；`BASELINE.yaml:88`；`:571-577` |
| QuixBugs | 50 文件（41 有 gold 的缺陷程序 + 9 个测试驱动） | 真实但极小；每个程序带 Input/Output/Examples docstring | aitester 45.9% vs df 83.8%（p=0.0005，成本 8.4×） | `src/datasets/dataset_realbugs.py:123-124`、`:150`；`BASELINE.yaml:286-298`、`:381-386` |
| SWE-bench Lite (sqlfluff-20) | 20 | 真实仓库；**0/20** | 负结果如实披露 | `README.md:42`；`experiments/results/experiment_report_20260925.md:142` |
| SWE-bench Pro | 0（probe 文档） | 仅探针 | 未跑 | `docs/design/swe_bench_probe.md` |

### 6.2 合成集是否构成自证循环？**是，且项目自己已经量化了它的后果**

三条独立证据链：

1. **缺陷、修复、oracle 三者同源**：`BUG_PATTERNS[*]` 的 `template`（缺陷版）、`fixed`（正确版）、`test_cases`（gold 测试）由同一作者在同一条目内共同设计（`src/datasets/synthetic_dataset.py:36-53`）。因此"检出"=能否猜中作者选定的语义差异，而该差异由**同一批人**在写 gold 测试时定义。
2. **任务在 prompt 侧是欠定的**：`problem_statement` 被写入 state 后**只被注入守卫扫描消费**（`src/graph/nodes.py:667-678`；`experiments/run_benchmark.py:1594-1595`），**从不进入任何 LLM prompt**；合成模板的 buggy 代码**没有 docstring**（`synthetic_dataset.py:36-37` 只有 `def divide(a,b): return a/b`）。即任务只给了实现、没给契约——"必须抛 ValueError"这类期望**不可从输入推断**。这不是"模型不会测"，而是**基准不给规格**。
3. **模板即分布 → 有效样本量崩塌**：基线自测 `cluster_k=29、ICC=0.671、DEFF=4.356、n_eff=39.9`（`BASELINE.yaml:219`）。n=261 的三种子实验，**有效独立样本只有 ~40**。项目已用聚类校正（`χ²_adj=6.60`、符号检验 p=0.0034，`:220-223`）——这是加分项，但也说明**合成集只能支撑"方向性"结论，不能支撑"量级"结论**。

**跨基准反差（本报告补充的一条关键证据）**：同一系统、同一 `logic` 档、同一协议，在**带 Input/Output/Examples docstring** 的 QuixBugs 上得 45.9%（`BASELINE.yaml:381-383`），在**无任何契约文本**的合成集上只得 9.2%（`:571-577`）；df 臂同向（83.8% vs 34.5%）。这条自然实验**不需要任何新预算**，却直接支持 §2 的 H1（载荷/规格决定检出），并与"基准更难"的常规解释相反——**更难的是"没有规格"，不是"代码更复杂"**。

### 6.3 测量伪影台账（4 起 + 1 起假阴性 + 3 项登记缺陷）

| # | 事件 | 影响 | 证据 |
|---|---|---|---|
| A1 | ADR-0021：patch 字段围栏残留 → repair 全线 0.0% | 使"修复能力不存在"的结论被写进多份报告 | `BASELINE.yaml:170-175` |
| A2 | ADR-0029/R27：跨文件任务伴生模块未物化 → 跨文件行 repair 恒 0 | 6 个批次受影响，v1→v2 修正 35.86%→39.31% | `docs/design/repair_caliber_matrix.md:30-40` |
| A3 | ADR-0029（同批）/ 第二起：跨文件 + 打包 import | 同上 | `BASELINE.yaml:21-27` |
| A4 | **第四起**：M1 判分树 import 布局不匹配 → **detection 构造性恒 0**（9/9 在 buggy 与 fixed 两侧 rc=2） | E4 首跑 0/41 系伪影；修正后 17/37=45.9%（n10=17、n01=0 的单向翻转是伪影特征） | `BASELINE.yaml:343-373` |
| A5 | **A1 消融假阴性**：`PLAN_STRIP_EXPECTED_OUTPUT_ENABLE=None`（开关未生效）、消融日志 0 行、detection 与对照逐点相同 → 原"H-A1 不成立"作废 | **一个"零效应"结论其实是"干预没跑"** | `BASELINE.yaml:389-402` |
| D1 | Planner 39% 空计划（LLM 输出 Python 语法而非 JSON，30.3% 无法 `json.loads`） | 生成侧三成任务无计划；修复后 detection 6.9%→8.0%（p=1.0） | `BASELINE.yaml:238-249` |
| D2 | 缓存命中不计 token → matched 臂无分母 | **等预算对照实验结构性受阻** | `BASELINE.yaml:208-211`；`src/agents/base_agent.py:397-407` |
| D3 | 消融开关未入 `env_snapshot` | A5 类假阴性无法被自动发现 | `BASELINE.yaml:455-461` |

**红队判断**：这 5 起非同质。A1–A4 是**测量管道缺陷**（可被"双向零 LLM 复现 + 判分树单变量"手法根治，项目已在做）；**A5 是治理缺陷**——它证明"负结果"也可能伪造，而当时的门禁（`env_snapshot`）不足以发现。项目对此的响应是把 `OVER_RED_SECTION_ENABLE` 加入快照（`BASELINE.yaml:459`），但**"新开关必须入快照"仍只是建议未成门禁**（`:461` 逐字"建议把'新开关必须出现在 `_env_snapshot_keys`'做成门禁（**未实施**）"）。这是当前**最高性价比的治理补丁**。

### 6.4 统计方法充分性

| 项 | 现状 | 评价 |
|---|---|---|
| McNemar（连续性校正） | `experiments/statistical_analysis.py:485` | 齐备 |
| BH-FDR | 同文件（`preregistration.md:236-240` 声明） | 齐备 |
| 贝叶斯配对 + ROPE ±5pp | 有多批次报告数值（`BASELINE.yaml:216-223`） | 齐备，且用于**等价性**判定（A1：CI 完全落在 ROPE 内，`p_rope=0.9691`） |
| 聚类校正（ICC/DEFF/符号检验） | `χ²_adj`、`cluster_k=29`（`BASELINE.yaml:219-223`） | 齐备，超多数同类工作 |
| 功效分析 | `scripts/tools/power_analysis.py`；预注册"基线检出 2%、检出差 10pp 需 n≈87"（`preregistration.md:241-243`） | 齐备，但**功效基线取自 2% 的合成集**——在 QuixBugs 这种 45–84% 检出率下，n=37 的双臂对比天然高功效；反之小效应（+5.5pp）在 n=37 上**永远不显著**，A1 的 p=0.72 属于设计性欠功效而非真零 |
| 预注册与偏差控制 | 主终点/停止规则/灰区/披露条款完整（`preregistration.md:234-271`）；A1 事后补登记且明确标注"预注册外实验、先声明后取数" | 齐备，属于**该仓库最强的方法学资产** |

### 6.5 LLM 缓存与对照污染

- 缓存键＝prompt＋system＋temperature（`src/agents/base_agent.py:360`）＋模型隔离（R13 默认开，`:370-378`）＋实验命名空间（`:388-393`）。
- **同臂重放**（同 namespace 复跑）是**可复现性特性**，且有 commit 全等校验（`BASELINE.yaml:14` Z 批次）；**跨臂复用**只有在 prompt 完全相同时才可能命中——df 与 aitester 的 prompt 不同，故主要风险不在"串味"，而在两处：
  1. **E4 修正结算刻意复用原 namespace**（`BASELINE.yaml:355-359` 单变量设计）——这是**正确的方法学选择**（唯一变量＝判分树），但也意味着修正后的 45.9% 与 83.8% 共享旧响应；若原响应本身受伪影影响（例如生成阶段依赖了错误的现场），复用得不出结论。作者已用 n10=17/n01=0 的单向翻转特征作为伪影指纹（`:357-358`），论证充分。
  2. **D2**：缓存命中不计 token（`:208-211`）——**污染的不是结果，而是预算口径**；后果是等预算对照实验永久不可做（除非修 D2）。
- **过红强化段首次运行不可验证**（`BASELINE.yaml:448-453`：开关未入快照 + 复用了标准臂缓存 namespace → 再生成响应被缓存短路，强化段未送到模型），与 A5 同类。**这是缓存复用与消融实验交互产生的新一类伪影**，值得在预注册里单列一节。

### 6.6 可推广性判断（红队结论）

- 一手外部基准只有两个：**QuixBugs（50 个玩具程序，41 可用）** 与 **SWE-bench Lite sqlfluff-20（0/20）**。前者代码规模是个位数到几十行、缺陷是"单行 seeded bug"（`src/datasets/dataset_realbugs.py:149` 的 `problem_statement` 自述）；后者 0/20 的成因**部分是测量管道**（模块命名与 sqlfluff 插件契约，见 `experiments/results/experiment_report_20260925.md:178-180`），不能全部归因于能力。
- 因此对外可写的结论上限是：**"在带契约 docstring 的小程序基准上，检出优先提示协议显著优于完整流水线；在无契约的合成基准上，两者都显著低于可用水平"**。任何"通用测试生成系统 / SOTA / 工业可用"的措辞都会在这一节被击落。
- 建议把 **external validity** 当作一等限制写进 README 顶部与论文 limitation，而不是散落在各批次注记里。

### 6.7 具体可执行改进

| # | 动作 | 落点 | 验收 |
|---|---|---|---|
| E1 | **规格可获得性作为一等自变量**：正式登记"合成集无契约 vs QuixBugs 有契约"的自然实验（零 LLM 复算），并在预注册中把它写成假设而非脚注 | `docs/preregistration.md`、`docs/design/real_benchmark_upgrade.md` | 报告含"契约存在性 → 检出率"的分层表 |
| E2 | **"新开关必须入 env_snapshot"门禁化**（A5/A6 类假阴性的根因治理） | `scripts/gates/check_env_budget.py` 升级 或新增 `check_env_snapshot_coverage.py` + `ci.yml` | 任一 `os.getenv` 新键若为消融开关且未入快照 → CI 红 |
| E3 | **预注册里单列"缓存×消融"交互节**：规定消融实验必须使用独立 namespace，并在报告中声明缓存状态 | `docs/preregistration.md` | 消除 A6 类"强化段未送达"的不可验证结果 |
| E4 | **修 D2 token 记账**（与 M5 同一件事，此处是评估侧动机） | `src/agents/base_agent.py:397-407`、`:452-454` | matched 实验可重跑 |
| E5 | **合成集加契约（docstring/规格）版本**：保留旧版作对照，新增"带契约版"合成集 | `src/datasets/synthetic_dataset.py` | detection 若从 9.2% 显著抬升 → 证明旧基准的欠定性，而非系统能力不足 |
| E6 | **小效应实验的样本量纪律**：凡预期效应 <10pp 的实验，必须先用 `power_analysis.py` 报 n 需求，否则标"探索性" | `docs/preregistration.md` | A1（+5.5pp, n=37, p=0.72）类结果不再被当作"无效"或"有效" |

---

## 7. 安全与合规：工程很扎实，**默认姿态与 2025–2026 合规视角不匹配**

### 7.1 现状（file:line）

- **执行沙箱三档**：本地（`src/agents/executor.py:55-58` 默认）、venv 沙箱（`config.py:488` **默认 true**）、Docker（`config.py:497` **默认 false**）；内核级沙箱（Seatbelt/bwrap）**默认 false**（`src/agents/kernel_sandbox.py:16`、`:69-70`），且不可用时 **fail-closed 抛 `SandboxUnavailable`**（`:58-60`），bwrap 档含 `--ro-bind / /` + `--unshare-net`（`:145-177`），macOS 用 sandbox-exec profile（`:103`）。
- **Docker 档加固**（启用时）：`--cap-drop=ALL`、`no-new-privileges`、`--read-only` + tmpfs、内存/pids 上限、**默认 `--network=none`**（`src/agents/executor_modes.py:430-440`，且注释明确"allowlist 模式若无宿主防火墙则等价于全放 → 保守回落 `--network=none`"，`:409-410`）。这一处的安全推理质量高于多数生产项目。
- **凭证**：三条执行链路统一剔除 LLM 凭证，白名单模式默认开（`src/utils/credential_scrub.py:200-213`）；日志三层脱敏 + CI 门禁（`.github/workflows/ci.yml:323`、`:331`；`.pre-commit-config.yaml:48`）。
- **威胁模型**：`docs/threat_model.md`（攻击面 A1–A6 + Fail-Closed 原则 + 已知可接受风险 + 缺口表，`:1`、`:21`、`:35`、`:45`、`:54`）；披露流程 `SECURITY.md:1-5`。
- **供应链**：bandit / gitleaks（二进制 SHA256 校验）/ pip-audit（顶层 + lock 传递依赖）**全部阻断**（`ci.yml:422`、`:431`、`:448`、`:460`、`:490`）；5 条 chromadb 豁免**登记在册且有复审触发条件与期限**（`ci.yml:477-481`、`docs/dependency_exemptions.md` 当前豁免表），并有 `check_dependency_exemptions.py` 对照门禁（`ci.yml:554`）；GitHub Actions **全部 SHA 钉版**（`ci.yml:63`、`:68` 等）；发布链有"CI 全绿 + SBOM"前置（`release.yml:35-58`、`:60-114`）。
- **监管**：`MODEL_CARD.md:17` 声明"参考 NIST AI RMF 与模型卡通行条目"；`:107` 声明"按 EU AI Act 口径本系统属软件开发工具（非 GPAI 提供商/部署者义务主体）"。
- **人工门**：`RISK_APPROVAL_ENABLE` 默认 false（`src/graph/risk_approval.py:57-59`），不在 `logic` 档；开启时经 LangGraph `interrupt()` 真实暂停并消费 resume 值（`src/graph/debugger.py:839-854`）。

### 7.2 缺口清单（红队视角：**默认配置就是风险面**）

| # | 缺口 | 证据 | 2025–2026 对标 | 应补什么 / 补在哪 |
|---|---|---|---|---|
| S1 | **默认执行姿态是"宿主用户 + 无内核隔离"**：Docker 关、内核沙箱关、venv 只是隔离依赖而非隔离权限；LLM 生成的任意代码在宿主 uid 下运行 | `config.py:497`、`src/agents/kernel_sandbox.py:69-70`、`src/agents/executor.py:55-58` | NIST AI RMF 的 MANAGE 职能、EU AI Act 高风险系统的"技术稳健性"要求 | **把 `safe` 档设为发行/CLI 默认**（`config.py:44-51` 已存在）；无沙箱可用时要求显式 `--allow-unsandboxed` 并留审计记录（`ALLOW_UNSANDBOXED` 语义已在 `kernel_sandbox.py:58-60`，只差默认值） |
| S2 | **自动打补丁到工作树**：`patch_applier` 直接写被测文件；回滚开关默认 false（仅 `logic` 档开） | `src/tools/patch_applier.py:212-336`、`src/tools/patch_rollback.py:81-89`、`config.py:73` | SLSA 来源/完整性思路；APR 领域的"补丁必须经独立验证"共识 | 默认开启快照回滚 + fail-closed（`config.py:44-51` 已有组合）；补丁写入前记录 `before/after` 哈希到不可变审计日志 |
| S3 | **无人类审核门（默认）**：risk_approval 默认关且不在主档；自动生成的补丁可直接落盘 | `risk_approval.py:57-59`、`docs/adr/0016` 决策 4 | EU AI Act 对高风险用途的人类监督（human oversight）要求；NIST AI RMF GOVERN | 分级默认：跨文件 / 低置信 / 高风险任务默认 `human_confirm`；对"自动合并/自动提交"能力要求显式 opt-in |
| S4 | **审计面不足**：有 trace JSONL，但**无防篡改**、无补丁级 provenance、无签名 | `src/observability/trace.py:9-20`（追加式，无完整性保护）；`ci.yml:574` SBOM 作业自述 **info-only** | **SLSA 全链（provenance / attestation）在本仓库零命中**（`grep -li "SLSA\|cosign\|sigstore\|attestation\|ISO 42001"` 于文档/代码 → 无结果） | 至少：SBOM 从 info-only 升为阻断或发布附属产物 + 生成 `build provenance`；补丁事件写 append-only 审计（哈希链） |
| S5 | **供应链豁免依赖单一上游**：5 条 chromadb 豁免（PYSEC-2026-311/3813/3814/3815），RAG 是**可选依赖**但默认安装路径包含它 | `docs/dependency_exemptions.md`、`requirements.txt:65` | SLSA/供应链最小化 | 把 chromadb 移出默认安装（`pyproject.toml:75` 已有 `rag` extra），使默认发行物不含带豁免漏洞的依赖 |
| S6 | **监管映射只有一句话**：EU AI Act 归类断言、NIST AI RMF 仅"参考"，无控制项对照表 | `MODEL_CARD.md:17`、`:107` | EU AI Act 第 6/9–15 条（风险管理系统、数据治理、技术文档、日志、人类监督…） | 在 `MODEL_CARD.md` 增一节"控制项 → 实现证据（file:line）"表；声明本系统的**用途分级**（研究工具 vs 生产 CI 门禁） |
| S7 | **提示注入与"流氓测试"防线默认关**：`INJECTION_GUARD_ENABLE`/`ROGUE_MONITOR_ENABLE` 仅在 `safe` 档 | `config.py:48-49`；`src/agents/injection_guard.py`、`src/agents/rogue_monitor.py` | ADR-0012 自设目标 | 与 S1 同批：默认档开启（成本为零的静态扫描） |
| S8 | **滥用面**：本系统可被直接用于"对任意仓库自动生成并执行代码 + 自动改源码"，且无速率/范围限制条款 | 全仓无 use-policy / acceptable-use 章节（`grep -i "acceptable use\|abuse"` → 需进一步核验，本次未命中） | EU AI Act 透明度义务；研究伦理 | 在 `README.md`/`SECURITY.md` 增"用途边界与禁止用途"节；对自动打补丁增加"仅限显式授权仓库"的运行前置 |

---

## 8. 工程化与运维：**该项目的真正护城河**（也是最容易低估的一项）

### 8.1 CI 门禁清单（`.github/workflows/ci.yml`）

| 作业 | 门禁 | 失败行为 | 行号 |
|---|---|---|---|
| `smoke-llm` | 真实 LLM 最小连通性 + JSON 校验（默认关，需 `AITESTER_SMOKE_LLM=true`） | 可选 | `:45`、`:83` |
| `test`（3.12/3.13/3.14 矩阵） | mypy 硬门禁 / lock 同步 / **z3 求解器 fail-closed**（防 SMT 层静默降级） / llm_configs schema / 工具版本 / LangGraph state 契约 / 工件 checksum / 引用链入库 / 零断言测试守卫 / env 开关预算 / 基线数字漂移 / BASELINE 结构 / 双语文档配对 | **全部阻断** | `:175`–`:270` |
| `test` 续 | ruff / 全量 pytest + 覆盖率 / 日志脱敏审计 / 凭证剔除同步 / 分支覆盖（核心路由 85%）/ 覆盖率 ratchet | **全部阻断** | `:305`–`:379` |
| `security`（blocking） | bandit / gitleaks 工作树（SHA256 校验二进制）/ pip-audit 顶层 / pip-audit lock 传递依赖 | **全部阻断** | `:395`–`:490` |
| `security` 非阻断 | gitleaks 全历史（周检，唯一 `continue-on-error: true`）/ 引用链接检查 / docs 历史漂移 warning | 非阻断 | `:529`、`:549`、`:542`、`:560` |
| `supply-chain` | CycloneDX SBOM 生成 + 归档（自述 info-only） | 非阻断 | `:573`、`:592` |

本地侧：`.pre-commit-config.yaml:12,14,22`（ruff/ruff-format/mypy）+ `:48`（日志脱敏）+ `:60`（密钥泄露守卫）；`scripts/gates/` 下 **20 个门禁脚本**（含 `check_baseline_numbers.py`、`coverage_ratchet.py`、`check_artifacts_tracked.py`、`check_state_contract.py`、`check_env_budget.py`、`checksum_results.py`）。

### 8.2 放水点与运维债务（红队核对）

1. **SBOM 自述 info-only**（`ci.yml:574`）→ 供应链证据链的最后一环不闭（见 S4）。
2. **孤儿进程只修了一环**：`run_with_timeout`（进程组 + `killpg` + 有界收口）只接线到 `branch_coverage_inject`（`BASELINE.yaml:279-285`），项目自注"另 9 文件 20 处 `subprocess.run`（`fl_spectral` 风险最高）"。**本次独立核对**：`src/` 内非注释 `subprocess.run(` 调用点 **14 处 / 10 个文件**（`executor_repo 3、testless_validation 2、dependency 2，其余 7 文件各 1`）；与 BASELINE 的"20 处"存在口径差（该项计数疑含注释/文档字符串）→ **需进一步核验**，核验方法：`grep -rn --include=*.py "subprocess.run(" src/ | grep -vE ':[0-9]+:[[:space:]]*#'`。
3. **`git_dirty=true` 历史**：三批次以 `--allow-dirty` 跑批（`BASELINE.yaml:181-183`），预注册已把该旗标改为禁止语境（`preregistration.md:250-259`）。这是"先跑批后补纪律"的典型，已收口。
4. **无告警链路**：`src/observability/` 无 Sentry/webhook/alert 命中（本次 grep），OTel 导出为离线转换器（`otel_export.py:8-21`）→ 长跑批次失败只能靠人看日志。
5. **测试规模与耗时**：5015 用例 / ~35s（`BASELINE.yaml:17-20`），ratchet 水位 89.5%（`:28`）——门禁密度与维护成本匹配良好，是本项目可持续性的核心。

### 8.3 具体可执行改进

| # | 动作 | 落点 | 验收 |
|---|---|---|---|
| O1 | **SBOM + provenance 升级**：SBOM 由 info-only 转为发布阻断或发布附属；生成 build provenance（SLSA L1–L2 语义） | `ci.yml:573-605`、`release.yml` | 发布物带可验证 provenance 文件 |
| O2 | **`run_with_timeout` 全量接线**：按风险排序（fl_spectral → executor_repo → testless_validation → dependency → type_repair → runtime_probe） | `src/utils/process_utils.py` + 各调用点 | 新增门禁：`src/` 内直接 `subprocess.run(` 计数不得超过登记值（棘轮式，`check_subprocess_ratchet.py`） |
| O3 | **告警最小闭环**：批次级失败/超时/预算触顶 → 结构化事件（webhook 或 GitHub Actions annotation）；不引入外部 SaaS | `src/observability/trace.py`、`experiments/run_main_batch.py` | 长跑批次失败 5 分钟内可见 |
| O4 | **默认安全档发布化**（与 S1/S3 同一动作）：CLI 默认 `safe`，`--profile logic` 需显式指定 | `config.py:43-51`、`src/cli/` | README 快速入门体现默认安全档 |
| O5 | **孤儿进程第 1 环**：病态任务资源上限 + 快速失败标记（`BASELINE.yaml:485` 自注"未修"） | `src/agents/executor*` | QuixBugs 4 个恒不终止任务不再产生 100% CPU 孤儿 |

---

## 9. 必做表 A：领域维度 → 现状评分（1–5）→ 依据 → 最短板

> 评分锚点：**1**＝概念/文档层面；**2**＝有实现但主张与证据脱节；**3**＝实现完整、工程可复现、但与前沿有明确差距；**4**＝局部达到或超过前沿；**5**＝该维度可作领域标杆。

| 维度 | 评分 | 依据（关键 file:line） | 最短板 |
|---|---|---|---|
| 1. 逻辑驱动 | **2** | 受限 DSL 与保守降级真实（`spec_ir_v2.py:63-124`、`:316-345`）；但无量化/无关系/无时序（`:227-230`、`:329-330`）、无可判定性论证、规约 oracle 检出贡献不可归因（`nodes.py:847`、`:864-865` 无结果行键）、CEGIR 未接线（`spec_refine.py:28-30`） | **"逻辑驱动"名不副实 + 贡献不可测**：端到端非空 18.7%、注入率合成 2.3%（`BASELINE.yaml:500-506`） |
| 2. 多智能体 | **2** | 工程完整（并发/超时/记账/降级，`expert_pool.py:321-373`）；但通信为自由文本（`state.py:152-158`）、共识为文本投票（`expert_pool.py:375-383`）、决定性实验根本没开多智能体组件（`config.py:64-112`）、−28pp 机制未分离（`BASELINE.yaml:581`） | **标签与实验对象错位 + 机制归因停在"结构"这一层** |
| 3. 测试生成 | **3** | 覆盖/变异/flaky/断言校验齐备（`nodes.py:1257-1274`、`mutation_testing.py:302-640`、`flaky_gate.py:45-58`）；无 MC/DC、无模糊/符号执行、最小化三件套只接线一件（`nodes.py:834-839`）、属性测试名不副实（`spec_ir.py:283-290`） | **缺"断言强度/过苛断言"度量**，导致 over_red 无生成侧解释力 |
| 4. 自修复 | **3** | 定位+补丁+回滚+弃权+防 hacking 链路罕见（`fl_spectral.py:295-352`、`patch_abstain.py:40-46`、`patch_test_hacking.py:106-148`）；correct 39.31%（`repair_caliber_matrix.md:20`）低于前沿；**落盘丢失 + 生成错误**双漏（`corrected_report_v2.md:12-32`） | **定位与修复负相关（15.79% vs 64.71%，`docs/adr/0024:26-28`）**：定位精度不是杠杆 |
| 5. 反馈闭环 | **3** | 协议 +43pp 且已排除采样效应（`BASELINE.yaml:524-540`）、三值终态、双门、聚类校正都扎实；但 over_red 不可恢复（`:429-454`）、无测试侧超时语义、奖励信号无消费者（`trace_reward.py:117-150`） | **"红得不特异"没有分类学**：60% 过红被当成一个同质现象处理 |
| 6. 评估与基准 | **3**（方法学 4.5／证据基础 1.5） | 统计/预注册/伪影自曝/双界披露达前沿水准（`preregistration.md:234-271`、`BASELINE.yaml:343-402`）；但 n_eff≈40 的合成集 + 50 玩具程序 + 0/20（`BASELINE.yaml:219`、`README.md:42`） | **外部有效性**：所有对外量级结论缺一手真实基准支撑 |
| 7. 安全与合规 | **3** | 沙箱三档 + fail-closed + Docker 强加固 + 凭证剔除 + 豁免登记 + SHA 钉版（`kernel_sandbox.py:58-60`、`executor_modes.py:430-440`、`credential_scrub.py:200-213`、`ci.yml:477-481`）；但默认姿态不安全（`config.py:497`、`kernel_sandbox.py:69`、`patch_rollback.py:81`、`risk_approval.py:57`）、无 SLSA/provenance（grep 零命中）、监管映射仅一句（`MODEL_CARD.md:107`） | **默认配置 + 自动打补丁 + 无人类门** 的组合 |
| 8. 工程化与运维 | **4** | 20 个门禁脚本 + 3.12–3.14 矩阵 + mypy/覆盖率硬门 + ratchet + 工件 checksum/入库守卫 + SHA 钉版（`ci.yml` 全篇、`scripts/gates/`） | 无告警链路；SBOM info-only；孤儿进程只修一环 |

**综合均分 ≈ 2.9/5**。若只看**方法学诚实度**，该项目处于同规模研究代码的前 5%；若看**主张的可支撑度**，则落在"有真实负结果、但正主张证据不足"的一档。

---

## 10. 必做表 B：红队反例（可能推翻本项目的竞争路线）

| # | 竞争路线 | 为什么可能推翻它 | 已有的脆弱证据 | 本项目最小防御动作 |
|---|---|---|---|---|
| R1 | **更强基座 + one-shot 协议** | 若前沿模型在单提示 + 检出优先协议下于 QuixBugs 达 ≥90% 检出，则完整流水线的**全部增量归零**，项目只剩"协议文本 + 归因方法学" | 项目**已自我收缩**主张 A 为提示协议（`docs/adr/0016:38-40`）；df 臂在 deepseek-flash 上已 83.8%（`BASELINE.yaml:383`） | 把"协议 × 模型能力"做成 2×2 网格；在论文中显式声明模型档位依赖 |
| R2 | **自动搜索编排（BOAD 类）** | 若自动搜索能找到优于 one-shot 的拓扑，则"手工编排净负"的结论被解释为"手工"而非"编排"；`mas_compilation.md` 已承认此路径 | 项目只有设计文档（Proposed，`BASELINE.yaml:14`），无任何本地证据 | 做"算子化编排小网格搜索"（M6），给出本地首个正/负证据 |
| R3 | **微调/蒸馏小模型做测试生成** | 若 1–2B 微调模型在同样基准上逼近或超过流水线，则"提示协议 + 编排"都被商品化；且成本低 1–2 个数量级 | 项目零训练能力与零训练数据管线（`MODEL_CARD.md:20-21` 自述不自研模型） | 至少给出"零样本 vs 少样本 vs 微调"的可行性讨论与成本对比表（诚实声明为未做） |
| R4 | **现成契约/属性测试工具链**（icontract + CrossHair + hypothesis） | 若这些工具在合成集/QuixBugs 上直接检出大部分缺陷，则"逻辑驱动"被现成工具支配，项目的 DSL 层无独立价值 | 本项目的"逻辑驱动"端到端非空仅 18.7%（`BASELINE.yaml:506`），且 oracle 检出贡献为 0/未知（`:507`） | **先做基线对照**：CrossHair/hypothesis 在这些任务上的检出率（零边际成本，见 E1/B 表配套实验） |
| R5 | **简洁三阶段 APR 流水线 + 前沿模型**（Agentless 式：定位→最小编辑→验证） | 若它在 QuixBugs/真实仓库上 >39.31% 且成本远低，则本项目"分层修复引擎"的复杂结构无优势 | 项目自己的 ADR-0024 已把杠杆指向"让补丁生成消费定位"（`docs/adr/0024:30-34`），这正是 Agentless 的核心 | 把"局部化编辑"做成默认路径并对照（ADR-0018 接管率判据） |
| R6 | **基准效度质疑**（无需竞争路线即可推翻） | 若审稿人认定合成集自证、QuixBugs 过小、SWE-bench Lite 0/20 系管道问题，则**全部主批次结论失去载体** | `BASELINE.yaml:219`（n_eff≈40）、`README.md:42`（0/20） | 一手基准扩容（TestGenEval 候补已登记但许可非清洁，`BASELINE.yaml:14` AN 批次）；预注册"外部基准升级"路径 |

---

## 11. 三个最致命短板（按"被审稿人一问击落"的概率排序）

1. **外部有效性（证据基础）**：合成集自证 + n_eff≈40 + 唯一大规模真实基准 0/20。所有"系统级"主张都建在这三块地基上；即便方法学无可指摘，结论也只能覆盖"带契约的小程序"。**这不是写作问题，是证据问题。**
2. **归因缺口**：三处未闭合——(a) "逻辑驱动"的检出贡献**没有任何一行指标**能单独观测（`nodes.py:847`、`:864-865` 与 `BASELINE.yaml:141-151` 键集缺失）；(b) −28pp 停在"编排结构"这一层，H1（载荷错配）从未被单变量检验（而 A1 的 +5.5pp 方向为正、三项过程指标同向，正好指向 H1）；(c) "多智能体"标签被判负，但决定性实验**没开任何多智能体组件**（`config.py:64-112`）。
3. **默认不安全 + 供应链证据链不闭**：默认在宿主 uid 下执行 LLM 生成的代码（`config.py:497`、`kernel_sandbox.py:69`）、默认自动把补丁写进工作树（`patch_applier.py:212`、`patch_rollback.py:81`）、默认无人类门（`risk_approval.py:57`）、无 SLSA/provenance（grep 零命中）、SBOM info-only（`ci.yml:574`）。在 2025–2026 的合规视角下，这套组合需要一个"默认安全档 + 人类监督门 + 审计链"的最小闭环。

---

## 12. 最可证伪的机制假说与首测设计（预注册级建议）

**H1（首选）：Prompt 载荷错配假说**

> aitester 的检出损失主要来自 Generator 收到的**载荷**（plan JSON 含 `expected_output`/`edge_cases`/`boundaries` + 现存断言 + RAG + CFG + 变异反馈），而不是来自节点数量、环路拓扑或调用预算。

**判别实验（单变量、可预注册）**：

| 项 | 设定 |
|---|---|
| 自变量 | `GENERATOR_PAYLOAD` ∈ {`full`（现状）, `df_parity`（仅被测代码 + 检出优先协议文本）}；**节点集合、调用次数上限、再生成上限、双门开关全部保持不变** |
| 数据 | QuixBugs 41 个有 gold 的缺陷程序（`BASELINE.yaml:291-298` 口径），seed 42，cold cache，`TEMPERATURE=0`，`LLM_THINKING_MODE=disabled` |
| 主终点 | detection（M1 三段判定 F2P，`experiments/_m1_metrics.py:473-523`） |
| 判别规则 | 若 `df_parity` − `full` ≥ +20pp 且与 df 臂 83.8% 的差不再显著 → **H1 成立**；若差异 ≤5pp（ROPE 内）→ **H1 否证**，转向 H2（环路反噬：禁 debugger 的拓扑消融） |
| 过程指标 | 首轮 `specific_red/over_red` 拆分（配合 F1 的五值分类）、每任务 prompt token 分解、`spec_oracle_injected` |
| 成本量级 | 单臂约 20 分钟 / ≈0.7M token（参照 E4 首跑，`BASELINE.yaml:307`）；可先做 12 任务子集做功效预判 |

**为什么它最该先测**：①单变量、判别规则二元、任何结果都可发表；②已有旁证（A1 +5.5pp 方向为正且三项过程指标同向，`BASELINE.yaml:403-419`；跨基准反差：有契约 45.9% vs 无契约 9.2%）；③能一次分解 H1/H4（载荷内容 vs 载荷长度）；④若 H1 成立，**修复动作是"减上下文"而非"加编排"**——与 ADR-0016"不做编排加码"的决策方向一致。

**零 LLM 前置步骤（先做，0 预算）**：利用 LLM 缓存条目中保存的 `prompt` 字段（`src/agents/base_agent.py:442`），或对现存 trace 做字段分解，统计每任务各节点的 prompt 规模与 `over_red`/`specific_red` 的关联；若关联显著，H1 的可信度在跑批前即可提升。**需先核验**：本机缓存目录是否保留对应 namespace 的条目（`_llm_cache_dir()`），以及 trace 是否保存了足够字段（`src/observability/trace.py:72-78` 会截断）。

---

## 13. 不确定项与核验方法（不编造、可复核）

| # | 不确定项 | 为什么不确定 | 核验方法 |
|---|---|---|---|
| U1 | trace 是否保存完整 prompt | `trace.py:72-78` 明确对字段做摘要与截断 | `grep -l "prompt" experiments/results/**/*.trace.jsonl` 后抽样读取一行；或读 `src/observability/trace.py:250-310` 的写入键集合 |
| U2 | LLM 缓存是否可用于 H1 的零 LLM 前置分析 | 缓存为本地可信域、不进 git，且 namespace 按 seed 隔离 | 检查 `_llm_cache_dir()` 指向目录中是否存在 `seed42`/`e4_quixbugs` 命名空间的条目（条目 JSON 含 `prompt`/`response`/`tokens`） |
| U3 | `subprocess.run` 真实计数（14 vs BASELINE 的 20） | 两者口径可能不同（本次仅计非注释行） | `grep -rn --include=*.py "subprocess.run(" src/ \| grep -vE ':[0-9]+:[[:space:]]*#'`（本次输出：14 处 / 10 文件） |
| U4 | 注入 spec oracle 是否真的从未被单独度量 | 本次 grep 只覆盖 `spec_oracle_injected` 键；可能以其他键名或报告形式存在 | `grep -rn "spec_oracle\|SPEC_ORACLE" experiments/ src/reports/`；并检查 `experiments/results/**` 是否含该字段 |
| U5 | SWE-bench Lite 0/20 中"管道问题"与"能力问题"的占比 | 现有证据是 2026-09-25 的报告（`experiments/results/experiment_report_20260925.md:142`、`:178-180`），此后有多批修复（模块命名/插件契约/P2P 门禁） | 用修复后的 loader 重跑 sqlfluff 子集（零 LLM 的"能否收集/执行"预检可先做：只验 gold 测试能否跑起来） |
| U6 | `spec_compile_rate 0.472–0.517` 是否已在登记口径中生效 | `BASELINE.yaml:68-70` 仍是 0.205–0.219，而 `:488-499` 给 S6 后数值；两者未同步 | 由维护流程刷新 `target_quality.spec_compile_rate` 并注明批次；或确认 0.472–0.517 属"单批证据、未登记" |
| U7 | 是否存在 use-policy / 滥用条款 | 本次未命中相关关键词 | `grep -rni "acceptable use\|abuse\|misuse\|用途边界" README.md SECURITY.md MODEL_CARD.md docs/` |
| U8 | `EXPERT_POOL`/辩论在**非** `logic` 档批次（历史批次）是否开过 | `logic` 档不含这些开关，但历史批次可能用显式 env | 检查历史批次 provenance `env_snapshot` 中 `EXPERT_POOL_ENABLE` 的取值分布（`experiments/results/**/*.json`） |
| U9 | 合成集"无契约"结论是否对所有模板成立 | 本次抽检了 `divide`/`bitcount` 等模板，未逐条核对 50 个模板是否全部无 docstring | 对 `BUG_PATTERNS*` 全量做 AST 检查：`ast.get_docstring(module)` 是否为 None 的比例 |
| U10 | A1（`PLAN_STRIP`）在 QuixBugs 上的 +5.5pp 是否受缓存复用影响 | 该批次 `dir: /tmp/a1_fixed（待归档）`（`BASELINE.yaml:410`），未归档则不可复核 | 要求归档 + SHA256SUMS；否则该结论只能作"待复核"引用 |

---

## 14. 附：证据索引（本报告引用的关键锚点）

**规格/逻辑**：`src/specs/spec_ir_v2.py:63-69,89,92-124,133-181,227-230,240-345,553-616`；`src/specs/spec_smt.py:406-456,459-560,654-711`；`src/specs/spec_refine.py:28-30,134-218`；`src/specs/spec_ir.py:216-290`；`src/prompts/templates.py:39-58`；`src/agents/planner.py:202`；`src/graph/nodes.py:158-208,847,864-865`。

**编排/状态/预算**：`src/graph/workflow.py:434-561,653-720,889-914`；`src/graph/state.py:14-420`；`src/graph/expert_pool.py:128-170,240-293,321-383`；`src/tools/multi_candidate.py:225-299,497-560`；`src/graph/trace_reward.py:89-150,153-188`；`src/agents/base_agent.py:360-393,397-407,442,452-454`；`config.py:43-112,365,380-382,488,497`；`src/agents/generator.py:31-46,215,266-282,394-450`。

**检出/修复**：`src/graph/nodes.py:391-488,498-...，1180-1298`；`src/tools/detection_gates.py:55-121`；`src/tools/patch_abstain.py:28-63`；`src/tools/patch_rollback.py:72-89,240-...`；`src/tools/patch_applier.py:212-336,444`；`src/tools/patch_test_hacking.py:106-148`；`src/agents/fl_spectral.py:295-420`；`src/agents/fault_localizer.py`；`src/graph/debugger.py:787-854`；`src/graph/risk_approval.py:57-59`。

**评估/基准**：`experiments/_m1_metrics.py:58-84,125-210,298-386,473-523,577`；`experiments/run_benchmark.py:544-668,1572,1591-1595,2712-2790`；`experiments/corrected_metrics.py:64-175`；`experiments/statistical_analysis.py:73-104,485`；`experiments/repair_ceiling_analysis.py:74-103`；`src/datasets/synthetic_dataset.py:32-54,2309-2390`；`src/datasets/dataset_realbugs.py:115-164`；`experiments/results/main_batch/{repair_ceiling_report.md:18-20, corrected_report_v2.md:11-35}`；`docs/design/repair_caliber_matrix.md:9-44`。

**安全/运维**：`src/agents/kernel_sandbox.py:16,58-60,69-70,79-177,226-232`；`src/agents/executor_modes.py:377-440`；`src/utils/credential_scrub.py:197-213`；`src/utils/process_utils.py`；`src/observability/{trace.py:9-20,72-78, otel_export.py:8-21}`；`.github/workflows/ci.yml`（门禁行号见 §8.1）、`release.yml:35-114`；`.pre-commit-config.yaml:12-60`；`scripts/gates/*`（20 个）；`docs/threat_model.md`；`SECURITY.md:1-30`；`MODEL_CARD.md:17,105-108`；`docs/dependency_exemptions.md`。

**基线/预注册/ADR**：`BASELINE.yaml:62-76,141-151,159-213,238-298,299-402,403-508,509-602`；`docs/preregistration.md:20-47,234-271,415-500`；`docs/adr/0015`、`0016`、`0018`、`0019`、`0020`、`0021`、`0022`、`0024`、`0027`、`0028`、`0029`。

---

> **审查者结论一句话**：这是一份罕见地"把自己的失败写清楚"的工作，因此它的**负结果（−28pp、45.9% vs 83.8%、0/20、mutation 饱和）比它的正主张更可信**；但它的三个正主张——"逻辑驱动"、"多智能体可消融容器"、"自修复 39.31%"——目前分别缺少**可归因指标**、**正确的实验对象**与**落盘侧机制**，且全部建在一个有效样本量 ≈40 的合成地基上。下一步最高价值的动作不是加功能，而是：**做一次载荷对齐消融（H1）**、**给逻辑 oracle 一行独立指标**、**把默认档改成安全档**。
