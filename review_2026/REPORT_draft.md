# AITester 系统性审查与 2025–2026 前沿对标报告（工作稿）

> 审查对象：`/Users/wangchenyu/Workspace/AITester`（Python，456 commits，2026-08-11 ~ 2026-10-10）
> 审查者：跨学科科研评审 + 技术战略顾问 + Python 架构师/代码审查（多智能体协作审查）
> 审查日期：2026-10-10
> 口径纪律：本报告所有项目侧数字均标注**来源工件路径 + JSON key + 分母**；
> 凡未能独立复现的，标注「未独立核验」。外部数字标注可信度等级 A/B/C。

---

## 0. 执行摘要（待最终整合）

（占位：最终版在此汇总一句话定位、5 个核心结论、3 个 P0 行动。）

---

## 1. 工作目录与文件清单

（由 task-1 / T1_inventory.md 汇入。）

---

## 2. 项目理解与边界

### 2.1 项目真实定位（与任务描述存在偏差，必须先澄清）

任务描述把本项目称为「逻辑驱动的多智能体测试生成与自修复系统」。
但仓库自身的第一手表述不同，且这个差异是**审查中最重要的事实**：

| 来源 | 表述 |
|---|---|
| `README.md:3` | "AITester：检出优先的测试生成与修复评估（**归因**）系统" |
| `README.md:5-9` | 核心创新 = **检出优先思维链**（先红后绿）+ 分层错误修复 + Oracle 闭环；"**多智能体编排**在本系统中定位为**可消融容器**（非主断言）" |
| `docs/adr/0016-orchestration-container-repositioning.md` | 编排净负贡献 δ=−0.3673，标题与开篇不再以"多智能体"为主表述 |
| 代码 | `src/graph/workflow.py` 确实用 LangGraph 编排 5 个角色节点（planner/generator/executor/debugger/patch_applier） |

即：**项目已经把"逻辑驱动"与"多智能体"从主卖点降级**，转而在"检出优先协议 + 修复引擎"
上重建叙事。因此本审查的任务不是"评估它的多智能体做得好不好"，
而是回答一个更尖锐的问题：

> **在它自己诚实披露的 −28pp 面前，这个系统的存在理由是什么？**
> 是（a）承认编排为负贡献后转型为"提示协议 + 修复引擎"，
> 还是（b）用"逻辑驱动"这一尚未兑现的通道重新建立不可替代性？

本报告按（b）给出超越路径，并给出（a）的诚实底线方案作为 Plan B。

### 2.2 关键假设（红队视角）

| # | 项目持有的假设 | 审查判断 | 证据 |
|---|---|---|---|
| A1 | 多智能体编排能带来检测增益 | **已被项目自身三次独立证否** | δ=−0.279（R-P0-2）/ −0.3673（E2）/ −0.253（E6）；`BASELINE.yaml:200-236` |
| A2 | 逻辑驱动（规约 DSL + SMT）能提升检出 | **尚未被验证**（关键批次通道关闭） | QuixBugs 修正结算批 `oracle_type` 50/50 = `generated_test`，无一行注入规约 oracle（见 F6） |
| A3 | 覆盖率是有效性的代理指标 | **已被自身数据证否** | aitester 覆盖 84–94% 而检出仅 13–16%（`BASELINE.yaml:56-62`） |
| A4 | repair 能力是真实存在的（39.31%） | **成立，但口径可被误读** | `corrected_report_v2.md:12`（57/145）+ 本审查发现的 plausible/correct 不一致（F2） |
| A5 | 合成基准结论可外推到真实代码 | **不成立** | 合成集 = 自生成模板库（29 个 pattern 覆盖 87 任务，F8）；真实基准仅 QuixBugs 50 个玩具程序 |

---

## 3. 2025–2026 前沿基线表

（由 R1/R2/R3 研究报告汇入；每个数据点标注来源/年份/venue/可信度。）

---

## 4. 项目与前沿量化对比矩阵

（待前沿数据到位后整合。）

---

## 5. 超越前沿方法设计

（待前沿数据到位后整合。）

---

## 6. Lead 独立复核发现（一手证据，先于对外声明）

> 本节全部为本审查者**直接读取入库工件**所得，未调用任何 LLM，
> 可与 `review_2026/T4_claims_audit.md` 交叉验证。
> 详细原始记录见 `review_2026/LEAD_findings.md`。

### 6.1 ✅ 复现成功的口径（项目自述可信）

复核工件：`experiments/results/e6_a1_batches/e4_quixbugs_FIXED_harness/aitester.json`
（QuixBugs，logic 档，seed 42，2026-10-10）。

| 指标 | 本审查复算值 | BASELINE 声明 | 结论 |
|---|---|---|---|
| detection | 17/37 = 45.9% | 17/37 = 45.9% | 一致 |
| repair | 37/40 = 92.5% | 37/40 = 92.5% | 一致 |
| token/task | 16,038 | 16,038 | 一致 |
| 对照臂 plain_llm_df detection | 31/37 = 83.8% | 31/37 = 83.8% | 一致 |
| coverage 均值 | **69.12%** | 未登记 | 新增数据点（显著低于合成集 84–94%） |
| mutation_score 均值 | **0.721** | 未登记（合成集 0.818–0.976） | 真实基准显著低于合成集 |
| **有变异体的任务数** | **仅 17/50**，平均 4.76 个/任务 | 未登记 | 见 6.5，变异指标统计功效严重受限 |

结论：项目的核心数字**确实能在入库工件里逐位复现**。这是本项目最值得肯定的部分，
也是它区别于绝大多数"论文式仓库"的地方。

### 6.2 🔴 P0 新发现 1：`patch_plausible` 与 `patch_correct` 在同批工件内自相矛盾（13/50）

同一工件按 `(stop_reason, patch_plausible, patch_correct)` 交叉：

| stop_reason | plausible | correct | 行数 |
|---|---|---|---|
| `test_passed` | 1 | 1 | 13 |
| `skip_debugger_repair_invalid` | **0** | **1** | **13** ← 矛盾 |
| `skip_debugger_repair_invalid` | 0 | 0 | 11 |
| `max_iterations` | 1 | 1 | 11 |
| `max_iterations` | 1 | 0 | 2 |

- 13 行的 `patch` 字段全部以字面 `python\n` 开头（围栏残留形态，与
  `src/tools/patch_applier.py:58 normalize_patch_text` 描述的形态一致）。
- `patch_plausible` 定义在 `experiments/run_benchmark.py:601-617`，判据是
  `repair_history[-1]["patch_applied"]`（**写盘是否成功**）；
  `patch_correct` 定义在同文件 `620-634`，判据是 gold 独立裁决。
- 二者**不同源**：写盘层拒绝（`patch_applied=False`）→ plausible=0；
  测量层清理围栏后重放 → correct=1。

**跨全部主批次量化**（本审查直接统计）：`experiments/results/main_batch/` 与
`e6_a1_batches/` 的**全部**带补丁行，`patch` 字段 100% 以 `python\n` 或围栏开头
（10 个主批次依次为 4/4、4/4、15/15、54/54、46/46、45/45、27/27、26/26、27/27、26/26）。

影响面：
- `patch_precision` 在本批只有 26 行非空，而 `patch_correct=1` 有 37 行 → 精确率分母错误；
- `REPAIR_CEILING` 漏斗（`experiments/repair_ceiling_analysis.py:74,100,191`）
  以 `patch_plausible=1` 为闸口 → **漏斗各层分母与 repair 主指标分子不同源**；
- CPR/IDR 报表（`experiments/cpr_idr_report.py:118`）直接跳过 `patch_plausible != 1` 的行；
- E7 分层抽样框（`experiments/repair_sample_selection.py:57-62`）同样以 plausible 为框。

**这是第五起测量伪影**（前四起见 `BASELINE.yaml:367-373` 等），
性质是**记账层**而非判分层：ADR-0021 修的是**测量层**（`_m1_metrics` 调
`normalize_patch_text`），但**透出层没有回灌** —— `state["patch"]` 里的围栏残留
一直留在工件里，导致任何以"透出字段"为输入的指标（plausible / precision / funnel）
都建立在未清理文本上。

**零 LLM 修复路径**（建议 P0-1）：
1. 在 debugger / patch 节点**写盘处**（而不是测量处）调用 `normalize_patch_text`，
   使 `state["patch"]` 从源头就是干净文本；
2. 加回归测试：任何结果行的 `patch` 字段不得以 `python\n` / ```` ``` ```` 开头；
3. 用零 LLM 重放重算 `patch_plausible`（判据改为"清理后文本非空且 `ast.parse` 通过"），
   重生成 `repair_ceiling_report.md` 与 CPR/IDR 报表。

### 6.3 🔴 P0 新发现 2：SWE-bench（Lite/Pro）工件是"失败分支"行，不是有效基准结果

复核 `experiments/results/swe_bench_lite_20/benchmark_swe_bench_20260818_113525.json`
与 `experiments/results/g8_lite_retest{,2,3,4}/*.json`、`full_stack_swe_bench_pro_*.json`：

- 结果行只有 **9–19 个键**，**完全没有** `detection_rate` / `repair_rate` /
  `oracle_type` / `stop_reason`；而有效批次行有 **65 个键**。
  对应 `experiments/run_benchmark.py:1225-1244` 的**失败分支**行字典。
- `task_metadata.instance_code` 长度 = **0**（SWE-bench Lite 20/20），`coverage` 全 0.0。
- `error_category`：syntax 19 / timeout 1；诊断文本形如
  "被测代码中存在未闭合的字符串字面量" → 喂进去的是**占位/损坏文本**，不是真实仓库源码。
- `provenance` = `{}`（无模型/温度/种子/开关快照）。

**结论**：`README.md` 中"SWE-bench Lite（sqlfluff-20）真实基准 **0/20 负结果**与统计检验
同样如实披露"这句话，把「评测无法执行（输入物化失败）」表述成了「负结果」。
两者证据强度完全不同：前者是**管道缺陷**，后者是**方法学发现**。
对外不可引用为负结果；`docs/design/swe_bench_probe.md` 与
`docs/design/real_benchmark_upgrade.md` 需要按此改写。

**推论**：项目目前**唯一有效的真实基准是 QuixBugs**（50 个玩具程序，41 个有 gold）。
所有"真实基准"层面的外部有效性主张，目前只由一个 41 任务的玩具基准支撑。

### 6.4 🟠 P1 新发现 3：48% 任务的修复循环被"连续修复无效"提前掐断

同批 50 任务的 `stop_reason` 分布：`skip_debugger_repair_invalid` **24** /
`test_passed` 13 / `max_iterations` 13。

- 24 行**全部** `iterations=2`、`passed=False`、20 行未检出；
- 但其中 **13 行最终仍被 gold 判定修复正确**（`patch_correct=1`）。

代码定位：`src/graph/workflow.py:727-734` ——
`if iteration < max_iterations and _recent_repairs_invalid(state): → done`。

含义：**修复能力存在，但循环被路由层提前终止**。而项目对修复天花板的官方归因是
"卡点在生成侧合成质量"（ADR-0024）。本审查认为这两个归因**至少同等重要**，
且后者是零 LLM 成本、可立即 A/B 的工程修复：
把 `_recent_repairs_invalid` 的早退从"连续 2 轮写盘失败"改为
"连续 2 轮**且**补丁经清理后仍不可解析/空"，或直接提高早退门槛做 A/B。

### 6.5 🟠 P1 新发现 4：谱系定位（`fl_at_k`）在真实基准上全线 0，与 LLM 定位形成强反差

同批 50 任务：

| 指标 | 值 |
|---|---|
| `localization_hit_function`（LLM 推理定位，元素级 Hit@1） | **29/50 = 58%**（13 行 None，8 行 False） |
| `localization_hit_function_at_3` | **30/50 = 60%** |
| `localization_mrr` | 均值 **0.797**（n=37） |
| `fl_at_k`（Ochiai 谱系定位） | **`{'fl_at_1': 0.0, 'fl_at_3': 0.0, 'fl_at_5': 0.0}`（全 0）** |

含义：项目的「FaultLocalizer 范式转向」（ADR-0017）在真实基准上是
**LLM 定位可用、谱系通道无效**。而 ADR-0028 的"FL Top-k 约束门"
（补丁变更函数集合 ∩ 定位 Top-3）依赖 `fl_at_k` 通道，
在 QuixBugs 上等于**恒空 → 该门在真实基准上不可评估**。
建议：把 FL 约束门的取数通道改为 LLM 定位（`localization_*`），
或明确声明该门**仅适用于有谱系可观测性的合成任务**。

### 6.6 🟡 P1 新发现 5：变异指标的统计功效严重受限，且未用标准变异工具

同批 50 任务中，**只有 17 个任务**产生了变异体（`mutants_total > 0`），
平均 **4.76 个/任务**，合计 81 个变异体（68 个被杀死）。

- `mutation_score` 在 48 行非空（33 行无变异体时记 0.0 参与均值）→
  均值 0.721 的语义是"含 0 的结构"，**不是标准 mutation score**；
- 变异算子来自自研 AST 变换（`experiments/mutation_testing.py`：比较翻转 /
  布尔取反 / return 改写 / raise 删除 / 异常类型替换），**每任务仅 ~5 个**，
  远低于标准变异测试的几十~几百个量级。

这正是项目自述"合成集变异体过弱、该指标鉴别力有限"（`BASELINE.yaml:67`）的
**量化根因**。修复方向明确：接入标准 Python 变异工具
（`cosmic-ray` / `mutmut`）或扩大算子集并保证每任务 ≥ 30 个变异体，
再重测 `mutation_score`。

### 6.7 🟡 P1 新发现 6：合成集"模板重复"造成的聚类效应未进入主表口径

主批次 `experiments/results/main_batch/benchmark_synthetic_20261006_140906.json`（n=87）：

- `task_metadata.pattern_name` 去重后**只有 29 个不同模板**，最高重复 8 次
  （`import_chain_type_contract`）；
- `bug_type` = assertion 46 / runtime 41；`difficulty` = 1:22 / 2:20 / 3:19 / 4:11 / 5:15。

项目已在 A1 分析中登记 `cluster_k=29 / ICC=0.671 / DEFF=4.356 / n_eff=39.9`
（`BASELINE.yaml:219-223`），方法正确；但**主表（detection 44.8% vs 15.8%）
未附 `n_eff`**，存在把 n=261 当作独立样本量对外引用的风险。
建议：`BASELINE.yaml` 主表每个比例后强制附 `n_eff`。

### 6.8 🟡 P2 观察：真实基准批次的"逻辑通道"实际关闭

同批 50 行 `oracle_type` **全部** = `generated_test`，`spec_oracle_injected`
无一行产出；而 `BASELINE.yaml:489` 自述"真实 QuixBugs 注入 20/50 = 40%"。

这不必然是矛盾（可能是批次/开关差异，或"注入尝试"与"实际注入"两种口径），
但必须对齐：**如果检测主指标所在的那一批逻辑通道没开，
那么该批的 45.9% 完全不能作为"逻辑驱动"有效性的证据**。

---

## 7. Python 专项诊断表

（由 T2_python_audit.md 汇入。）

---

## 8. 领域专项诊断表

（由 T3_domain_audit.md 汇入。）

---

## 9. 改进/优化/新增建议表

（整合 T1–T4 + 前沿对标后产出。）

---

## 10. 优化后的项目方案与路线图

（待整合。）

---

## 11. 实验、验证与评估计划

（待整合。）

---

## 12. 风险、伦理与合规

（待整合。）

---

## 13. 待澄清问题

（待整合。）

---

## 14. 参考来源

（待整合。）
