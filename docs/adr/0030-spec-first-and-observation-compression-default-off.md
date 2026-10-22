# ADR-0030: 规格优先与观测压缩的默认关口径（2026-10-12 独立评审优化批次）

- 日期：2026-10-12
- 状态：已采纳（Accepted）
- 关联：`src/tools/spec_first.py` / `src/tools/feedback_compression.py` /
  `src/graph/orchestration_search.py` / `experiments/run_orchestration_search.py` /
  `src/datasets/decontamination.py` / `src/measurement/recovery_latency.py` /
  `src/agents/generator.py` / `src/graph/nodes.py` / `config.py`（scientific /
  logic 档）
- 依据：`INDEPENDENT_REVIEW_2026-10-12.md` §6 超越前沿路径 P1–P5 与 §10 建议表
  S-05 / S-06 / S-08 / S-09 / S-10 / S-16

## 背景（Context）

`INDEPENDENT_REVIEW_2026-10-12.md` 的独立评审结论（§0 执行摘要 F1–F7）确立了
三条对本批次直接构成约束的事实：

1. **编排净负 −28pp 是项目自身 A 级阴性结果**（F1 / ADR-0016）：完整多智能体
   编排（aitester 臂）detection 15.8% vs 单提示检出优先协议（plain_llm_df）
   44.8%（**仓内工件口径**，可由 `make mutation-det-correlation` 零 LLM 复算）。
   评审另引入两项**外部**工作作为参考，2026-10-16 第十九轮已一手核验并内联编号：
   BOAD（*Discovering Hierarchical Software Engineering Agents via Bandit
   Optimization*，ICLR 2026，arXiv:2512.23631——SWE-bench-Verified 上自动发现的
   层级多 agent 胜单 agent 与手工多 agent）；ICST'26 复现研究（Konstantinou,
   Degiovanni, Papadakis，*How well LLM-based test generation techniques perform
   with newer LLM versions?*，ICST 2026，DOI 10.1109/ICST69053.2026.00040，
   arXiv:2601.09695v2——393 类 / 3,657 方法上 plain LLM(M) 的 line/branch/mutation
   总计 49.95/35.33/33.82，对比 HITS 42.43/29.49/27.97：**相对提升**
   17.72%/19.80%/20.92%，折合绝对差 +7.52/+5.84/+5.85pp。原文摘要写 "by X%"，
   是相对量而非百分点，引用时不得写成 "pp"（F09 更正，2026-10-22）。
   两条外部研究提供了与本项目阴性结果**同向**的参考，但各自只支持其设定的比较：
   BOAD 说明自动搜索的层级 agent 在 SWE-bench-Verified 上可胜手工多 agent；
   ICST'26 复现说明 plain LLM(M) 在该 Java 复现设定下可胜四个工程化工具。
   **不构成"手工编排已不被前沿视为价值来源"的领域级判断**（见
   `docs/EVALUATION_SCOPE.md` C10：证据只支持本系统设定下的编排净负）；
2. **"逻辑驱动"内核薄弱**（F3）：spec_compile_rate 仅 0.205–0.219，
   约 79% 的规约子句不可机器化，根因在**文法表达力**而非提示
   （§3.3 行 3）；
3. **观测通道信噪比低**：aitester 臂 token 26.1k/任务 vs df 臂 4.2k/任务
   （**6.2×** = 26,115/4,223；F15 更正：历史笔误写 8.1×，该倍数对应
   plain_llm 的 ≈3,209 tok/任务，不是 df），全量 trace 注入是主要低信噪比
   通道（§4.1 C11 / §6 P4）。

评审 §6 给出七条超越前沿路径（P1–P8）。本批次落地其中六条的
**第一阶段原语**（均遵循 ADR-0003 默认关口径，历史行为逐字节零变化）：

| 评审路径 | 本批次落地 | 模块 | 开关 |
|---|---|---|---|
| P1 规格优先生成 | P0-A-1 文法升阶 + P0-A-2 规约替换臂 | `spec_ir_v2.py` / `spec_first.py` | `DETECTION_SPEC_MODE` |
| P2 变异第一公民 | P0-B 算子 v3 + 环路内化 | `mutation_testing.py` / `config.py` | `MUTATION_ADVISOR_ENABLE` |
| P3 编排自动搜索 | P1-A UCB1 bandit 搜索原语 | `orchestration_search.py` / `run_orchestration_search.py` | `ORCHESTRATION_SEARCH_ENABLE` |
| P4 观测压缩（一期） | P2-A 行粒度压缩段落 | `feedback_compression.py` | `FEEDBACK_COMPRESSION_ENABLE` |
| P5 SRE 口径指标 | P1-B 认知恢复延迟纯函数 | `recovery_latency.py` | 无（纯测量模块，无路由开关） |
| P8 去污染协议 | P1-B 时间戳切片 + 审计报告 | `decontamination.py` | 无（纯函数层，调用方自管） |

## 决策（Decision）

1. **默认关口径（ADR-0003 不变）**：`DETECTION_SPEC_MODE` 默认 `off`
   （Generator prompt 与历史逐字节一致）；`FEEDBACK_COMPRESSION_ENABLE`
   默认 `false`；`ORCHESTRATION_SEARCH_ENABLE` 默认 `false`（未开启时
   `orchestration_search.py` 与 `run_orchestration_search.py` 的全部公共
   入口立即拒绝执行，退出码 2，零 I/O）；去污染与恢复延迟为纯函数层，
   无默认行为路径。
2. **唯一默认开例外：P0-B 的 `MUTATION_ADVISOR_ENABLE`**——仅在
   `scientific` 与 `logic` 两个**科研评测档**默认注入 `true`
   （`config.py::_PROFILE_PRESETS`，setdefault 口径，显式 env 优先）；
   `safe` 与 `fast` 档（`{}`）保持关闭以控成本。理由：变异反馈是
   "变异引导测试增强"闭环的数据源，此前默认关、观测覆盖 0/154
   （评审 S-08）；科研档的口径是"完整链路可测可观测"，默认开不改变
   历史 fast 档行为。
3. **编排自动搜索不进任何 profile 档**：P1-A 的 7 项开关族
   （`ORCHESTRATION_SEARCH_*`）是**实验 harness 族**（与
   `ENABLE_MUTATION_SCORING` 同区），champion 配置晋升新档须待
   Stage-2 确认批（champion vs plain_llm_df，n=87×3，前置
   `collect_model_fingerprint` 版本钉住，S29）通过后另走 ADR。
4. **hindsight credit 不进臂选择**（防 reward hacking，ADR-0016 教训）：
   主奖励 = M1 detection（成本以硬顶约束进入，不做 λ 标量化）；
   hindsight credit（`ORCHESTRATION_SEARCH_HINDSIGHT_GAMMA`）只进
   归因报告，不进 UCB 臂选择。
5. **SpecExpr v3 文法升阶为纯扩展**：新增 `<quant>` 产生式（all/any
   推导式）+ 字符串纯方法白名单（15 个）+ 迭代域内建（range/enumerate），
   自由变量分析 `_free_names` 精确到 comprehension/lambda 作用域——
   越界引用循环变量仍按 `unknown_name` 拒绝（防 NameError 假红断言）。
   原 P2-L3 唯一 strict xfail（推导式变量被标识符门误杀）修复后转正，
   套件现 0 xfail。
6. **规约替换臂的保守口径**：`DETECTION_SPEC_MODE=replace` 时仅当规约
   材料非空才替换（无材料 → 空串 → 调用方保持历史口径，不产出"无代码
   无规约"的空洞提示）；与 `ORACLE_CONTEXT_MINIMAL` 消融档同口径
   （minimal 时不构建本段）。

## 后果（Consequences）

**正面**：

- 三条阴性结果（−28pp / spec_compile_rate 0.21 / token 8.1×）各有一条
  已落地的原语级对策，且全部可通过单一 env 开关消融（历史口径零变化
  逐字节可验证）；
- 测试 5485/5489 → 5689/5692（+204/+203，7 个新测试文件 + 语料库扩充），
  全量 0 failed / 0 xfailed；
- `BASELINE.yaml` 与 `docs/env_budget.yaml`（env_total 184 → 187）同步
  刷新；`docs/DATA_CARD.md` 泄漏通道节登记第二消费点
  （`orchestration_search.py` 的 `create_initial_state` 入参，守卫测试
  `tests/test_af_batch.py` 锁定唯一读取口径）。

**负面 / 待办**：

- 所有新原语目前为**桩评估器测试路径**——本批次不烧真实 LLM 预算，
  效果验证（McNemar p<0.01 且 δ≥+10pp，P0-A-2 判据）与 champion 晋升
  须在 Stage-2 确认批另走 ADR；
- P2-A 一期为行级压缩（≤4000 字符段落），KV-Cache 级通信（P4 二期）
  未落地；
- P1-B 去污染时间戳字段探测为数据集可扩展设计
  （`task_created_at` / `created_at` / `creation_date` 优先级），
  新数据集接入须同步登记；
- 变异算子 v3 的合成变异体仍为"项目自认过弱"口径（评审 C5），ULT /
  TestGenEval 外部变异体重测未落地（评审 S-07 / S-08 后续批次）。

**关联 ADR**：ADR-0003（默认关口径）、ADR-0015（检出优先协议）、
ADR-0016（编排降级为可消融容器）、ADR-0025（oracle 上下文消融档）。
