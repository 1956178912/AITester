# 项目状态与决策登记册（Status & Decision Register）

- 最后更新：2026-10-16（W/C 批次合并收口；§1 快照随 `BASELINE.yaml` 同步至当日终态）
- **自我对账**：本册的覆盖率/测试数声明由 `scripts/gates/check_artifact_doc_consistency.py`
  的 `check_status_register()` 与 `coverage.xml` 实测**逐位对账**——数字过期即 CI 红，
  因此本册不允许手工美化。
- 用途：把多轮优化中的"**已完成 / 遗留 / 阻断**"三类状态收敛到一份可核验清单。
  每一项都给出**验证入口**（命令或门禁），使"文档说做了"必须能被复跑证实——
  本项目既往的失分形态正是"文档与工件静默分裂"，本册即是该纪律的交接面。
- 阅读顺序建议：§1 现状快照 → §2 阻断项与解锁路径 → §3 已完成事项（含验证入口）
  → §4 遗留缺口 → §5 口径与术语纪律。

## 1. 现状快照（2026-10-15 收尾批次实测，CI 同口径）

| 维度 | 数值 | 验证入口 |
|---|---|---|
| 全量测试 | **6612 passed / 5 skipped / 0 failed**（登记口径 = collected 6617 − skipped 5；全量实跑 534.61s） | `pytest tests/ -q -n 4 --dist loadfile` |
| 总行覆盖 | **92.78%**（ratchet 水位 92.40，余量 +0.38pp） | `make test-cov` + `scripts/gates/coverage_ratchet.py --check` |
| 总分支覆盖 | **87.29%**（水位 86.90，余量 +0.39pp） | 同上（`--cov-branch`） |
| 静态硬下限覆盖 | 达标（行 ≥85% / 分支总 ≥77% / 核心路由 ≥85–90%） | `scripts/gates/check_branch_coverage.py coverage.xml` |
| 门禁总数 | **17 道全绿**（14 硬门禁 + 引用可追溯性 + 覆盖率棘轮 + 分支硬下限） | `make gates`；逐项见 §3 |
| 静态检查 | ruff 全绿 / 695 文件已格式化 / mypy 0 错（133 源文件） | `ruff check .`、`ruff format --check .`、`mypy src/ config.py` |
| 构建基线 | `BASELINE.yaml` 与实测逐位对账（含守卫 `TestBaselineNumbersConsistency`） | `pytest tests/test_2026_10_10_optimization_batch.py -q` |

> 一致性提示：**任何一项数值漂移都会让对应门禁转红**（覆盖率零/小缓冲已被显式记录），
> 因此本表不允许手工维护——它必须随 `BASELINE.yaml` 同步刷新。

## 2. 阻断项与解锁路径（需要人决策/授权，代码侧已就绪）

| # | 阻断项 | 类型 | 解锁路径（已就绪的前置件） | 解锁后的收益 |
|---|---|---|---|---|
| B1 | 2×2 消融（协议文本开关 × 再生成预算） | **LLM 配额** | 双开关已具备、零新代码；跑前设 `COST_BUDGET_ENABLE=true`、`AITESTER_BATCH_MAX_CALLS≥1684`、`AITESTER_RUN_PREFLIGHT=true`，并在**干净树**上跑 | 把"+43pp 归因于 instruction artifact"从**协议包效应**钉成**文本效应**（PROMPT-SE 最想看的一张表） |
| B2 | 锁指纹重跑主批次（261 任务 × 3 臂） | **LLM 配额** | 同上；新批次须带 `model_fingerprint.pinned=true`（近 5 个批次已实测均为 true） | 关掉"头条批次 10/10 `git_dirty=true`、0/10 有指纹"这一复现性缺口 |
| B3 | SWE-bench Lite 重跑 | **LLM 配额** | 配额闸已补（`AITESTER_BATCH_MAX_CALLS`）；`make preflight --strict` 会阻断未配置状态 | 把 `not_evaluated` 变成有效能力结论（当前严禁引用其 `pass_rate`） |
| B4 | E7 人工复核 | **人力** | 协议已可执行（抽样框/五选一量表/双人独立/Cohen's κ）：`docs/HUMAN_ADJUDICATION_PROTOCOL.md`；**预注册口径 = `ceil(10%/层)` → 当前 72 行单层为 8 行**（"≥40 行"是优化记录里的建议口径，二者冲突已在协议文档登记） | 给 `detection_rate` 一个**人类外部校标**（构念效度从 `open` 转 `reduced`） |
| B5 | Prompt Card + 哈希锁 | **清单/哈希锁已就绪；文本已呈交目检（2026-10-16）** | detection-first 段落现内联于 `src/graph/nodes.py:540-547`、over-red 于 `:650-667`；7 个 JSON 契约调用点已由门禁固定（口径 A=7） | 满足 PROMPT-SE "instruction artifacts as first-class objects" 的复现要求 |
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

## 4. 遗留缺口（按"是否值得继续"分级）

| 分级 | 缺口 | 说明 |
|---|---|---|
| **建议做** | B5 文本目检（清单/哈希锁已就绪，2026-10-16 呈交） | B6 已执行（8c2b655）；A-10 df_spec 臂已落地（6ddd1ca）；A-11 冻结 ADR-0034 |
| **可做** | `graph/nodes.py` 155 行、`executor_repo.py` 101 行、`orchestration_search.py` 74 行 | 均属"配置门控装配/长链"，单模块约 30–50 例的成本；覆盖率已 +0.40/+0.37pp 余量，边际收益递减 |
| **低优先** | `agents/debugger.py` 76 行 | LLM 调用链，需 mock 编排，测试价值低于其维护成本 |
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
