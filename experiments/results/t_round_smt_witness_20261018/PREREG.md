# T3b 预注册（跑批前冻结）：z3 SMT 见证层最小启用批次（A-18 / Q7，零 LLM）

- **冻结时间**：2026-10-18 09:05（+0800），在**任何求解器调用之前**落盘
  （此前的材料覆盖预检只用 `parse_logic_analysis` / `extract_signature_params`
  做材料统计，未调用 z3、未观察任何 `smt_status`）。
- **性质**：单臂观测批（**无对照臂**）；机制层为可判定判定，关联层为
  **探索性**（非 confirmatory）。
- **依据**：`docs/design/smt_witness_batch_plan.md`（全文）；任务书 T3b。
- **预算**：零 LLM（0 次 LLM 调用、0 USD、不联网）；算力 = z3 求解 + Python。
- **锚点**：git HEAD `a93c1f60ee31b9582e0146f73e3038e6ce0f01a1`。

## 1. 数据集与任务集（冻结）

| 项 | 冻结值 |
|---|---|
| 任务清单来源 | `experiments/results/emse_df_spec_20261016/benchmark_quixbugs_20261016_232138.json` → `results.plain_llm_df_spec.details`（50 行，与 df_spec 同集） |
| 输入工件 sha256 | 上述文件 `813c437fc53a84c1517cce234b12184e5047bf483fb982cb9382d1c61307245a` |
| **主判定集** | **41 个缺陷程序**（task 的 `task_metadata.program` 不以 `_test` 结尾）——与 df_spec 的 detection 41 口径同集 |
| 扩展披露集 | 全 50 任务（含 9 个 `*_test` 驱动任务）；**不参与机制层判定**，仅披露 |
| 缺陷源码根 | `--quixbugs-root` 覆盖 > `~/.cache/aitester/quixbugs` > 仓库 `data/quixbugs` > `AITESTER_QUIXBUGS_DATA`（与 `experiments/misguided_metrics.resolve_quixbugs_roots` 同序）；实际命中根与逐任务源码 sha256 写入 PREFLIGHT/TASK_LEVEL |

## 2. 材料（冻结）

| 项 | 冻结值 |
|---|---|
| 规格材料 | `experiments/results/emse_spec_anchor_20261016/SPEC_ANCHOR_TABLE.json`（Planner 缓存物化，零 LLM），**加载时强制按同目录 SHA256SUMS 校验**（fail-closed，复用 `experiments/oracle_quality_replay.py::load_anchor_table`） |
| 锚表 sha256 | `3e90b2ad5ed365ad5ee989c73c92b84956a83c0fa8cb51368d288ae3ea53bf22` |
| 内容寻址 | `key = sha256(buggy_source.strip())`；查表复用 `lookup_anchor`（与 df_spec 臂/生产同口径） |
| 缺口处理 | 锚表未命中 / 源码不可得 / `parse_logic_analysis` 为空 → 任务记 `spec_material_missing`（或 `spec_parse_failed`）并**从主判定均值中剔除**，缺口逐任务披露；**不得用 LLM 补跑** |
| 子句通道 | **SpecExpr 形式化通道**（`preconditions_expr` / `postconditions_expr` / `invariants_expr`），选择规则与 `spec_ir_v2._select_compile_channels` 同口径：三个 `*_expr` 字段任一含 str 子句 → 用 expr 通道；否则回退 NL 通道并标注。**与 SpecExpr 可编译率（0.7161）同材料通道/同非空子句分母口径** |
| 签名参数 | `extract_signature_params(buggy_source, anchor.function_name)`；若返回 `None` 且 `function_name` 含 `.`（如 `Node.__init__`），回退点分末段再解析一次并记 `signature_params_source="dotted_tail"`；仍 `None` → 该任务全部子句记 `error`（签名未解析），披露 |

## 3. 求解入口与参数（冻结）

- **编译入口（复用 src 公开函数，不重实现）**：`src.specs.spec_ir.parse_logic_analysis`
  + `src.specs.spec_ir.extract_signature_params`；逐子句求解走
  `src.specs.spec_smt` 公开 API：
  - `preconditions_expr` / NL-precondition 子句 → `check_precondition_vacuity({"preconditions":[clause]}, params)`；
  - `postconditions_expr` + `invariants_expr`（同一任务后件组）→ `check_postcondition_consistency({"postconditions":[clause]}, params)`
    （与 `_collect_post_constraints` 把 post+inv 同 collect 的口径一致；inv 归入后件组）。
  - 单子句 spec 构造是**口径选择**（让公开 API 逐子句求解），不含任何 src 逻辑复制。
- **参数**：`SPEC_SMT_ENABLE=true`；`SPEC_SMT_TIMEOUT_MS=5000`（per-clause 5s，落在
  src 内 [100, 30000] 合法区间）；不设 `SPEC_SMT_MAX_WITNESSES`（本批不产见证测试）。
- **超时计法（冻结）**：`timeout` **不计 unsat、不计 unknown**。公开 API 只回
  `sat/unsat/unknown/skipped`；映射规则：
  1. `sat` → `sat`；`unsat` → `unsat`；
  2. `unknown` 且 `smt_solve_ms ≥ 0.9 × 5000ms` → `timeout`；否则 → `unknown`；
  3. `skipped`（未达求解器：形态门/白名单/排序推断/翻译任一保守拒绝）→ `error`，
     `error_kind="not_reached"`、`reached_solver=false`（**不并入 unsat/unknown**）；
  4. 公开 API 抛异常 → `error`，`error_kind="solver_exception"`。
- **确定性**（口径见文末「跑前修订记录 R1」）：同一输入**进程内两次独立求解**，
  剔除计时键（`smt_solve_ms` / `smt_solve_ms_total` / `wall_clock_seconds`）后的
  status/分类/计数/率字段逐字段一致；子句按材料内顺序、任务按 `task_id` 字典序；
  JSON 输出 `sort_keys=True`、`ensure_ascii=False`、固定缩进。计时键为求解器墙钟
  （本质非确定），允许运行间波动，不纳入幂等声明。z3 未设置随机参数（整数/布尔
  约束），同一输入返回同一 status 由双求解自检验证；若出现不一致将在报告披露。

## 4. 观测字段（冻结）

**逐子句（`PER_CLAUSE.jsonl`）**：`task_id`、`function_name`、`channel`
（`expr`|`nl`）、`channel_field`（`preconditions_expr` 等）、`kind`
（`precondition`|`postcondition`）、`clause_index`、`clause_text`、
`clause_sha256_16`（= 子句文本 sha256 前 16 位）、`smt_status ∈
{sat, unsat, unknown, timeout, error}`、`error_kind ∈ {null, not_reached,
solver_exception}`、`reached_solver`、`smt_solve_ms`、`timeout_ms`、
`raw_status`（公开 API 原值 sat/unsat/unknown/skipped）。

**任务级（`TASK_LEVEL.json`）**：`smt_clauses_nonempty`（D1 = 该任务评估子句非空数）、
`smt_clauses_reached`、`smt_status_counts{sat,unsat,unknown,timeout,error}`、
`smt_witness_rate = sat / D1`（D1=0 → null）、`smt_reach_rate = reached / D1`、
`smt_timeout_rate = timeout / reached`（reached=0 → null）、
`smt_timeout_share_nonempty = timeout / D1`、`smt_solve_ms_total`、
`material_status`、`signature_params_*`、`channel_used`、`in_primary`、
df_spec 同任务行 `dfspec_detection_rate` / `dfspec_detection_measurable` /
`dfspec_specificity_gate_verdict`（**同行落盘**）。

## 5. 判定规则（跑后不得改）

**机制层（可判定）**，在主判定集（41 缺陷程序，剔除材料缺口后）上：

- **通过（层在工作）**：
  1. `smt_witness_rate` 全任务均值 > 0；**且**
  2. `smt_timeout_rate` < 20%——判定值冻结为**合并口径**
     `timeout 子句数 / reached 子句数`（主判定集汇总；同时披露任务级均值）；**且**
  3. 每个 `smt_status` 桶（sat/unsat/unknown/timeout/error）可由 `PER_CLAUSE.jsonl`
     逐子句复算：从行重聚合的桶计数与 `TASK_LEVEL.json`/`ANALYSIS_REPORT.json`
     **逐项相等**（脚本内自检，0 mismatch 为要求）。
- **失败**：均值 `smt_witness_rate` = 0（层未接线/材料未达求解器）**或**
  `smt_timeout_rate ≥ 20%`（参数需重标，**不得解读关联层结果**）。
- **材料缺口**：剔除后若有材料任务 < 30 → 如实报告缺口统计与缺口任务清单，
  不补跑、不解读关联层。

## 6. 关联层（探索性，冻结分桶）

- 分桶：主判定集按任务 `smt_witness_rate` 中位数二分（`≥ median` vs `< median`，
  median 由 `statistics.median` 计算）；若两桶任一为空（全等/无对照）→
  只报告「无对照，不做 detection 比较」。
- 对比量：df_spec 归档 `detection_rate`（`detection_rate is not None` 为
  measurable；`>0` 为 positive），逐桶 `positive / measurable / rate`。
- **预设披露**：n=41、可判定子集 35 对的 df_spec 同口径 **MDE ≈ 16.57pp**
  （来源 `emse_df_spec_20261016/DF_SPEC_REPORT.json::contrast_41.mde_pp`）；
  任何差异 < MDE 只能写「方向性描述」；**禁止**「提升 / 显著 / 证明」措辞；
  不做 p 值/检验；不引为确认性结论；不服务「规格锚增益」主张。

## 7. 产物与校验（冻结）

`experiments/results/t_round_smt_witness_20261018/` 下：
`PREREG.md`（本文件）、`PREFLIGHT.json`、`PER_CLAUSE.jsonl`、`TASK_LEVEL.json`、
`ANALYSIS_REPORT.json`、`README.md`、`RUN_SUMMARY.log`、`SHA256SUMS`（由
`scripts/gates/checksum_results.py --write` 生成并 `--verify`）。

## 8. 范围边界（预注册披露）

- 本批测的是「**形式化子句在 5s 有界求解下的可解性**」，与 SpecExpr 可编译率
  同通道；**不测**生产 `spec_smt` 从 NL 通道取子句的实际到达率——README 报告
  将披露：生产 `_collect_pre_constraints` 消费 `spec['preconditions']`（NL 通道），
  而本批主材为 `*_expr` 形式化通道（以单子句 spec 喂入同一公开入口）。该路径差
  作为限制披露，不在判定范围。
- 本批不修改 src/、docs/、BASELINE、其他 tests；不 git commit；零 LLM。

## 9. 材料覆盖预检（跑前，仅材料统计，未触求解器）

- 锚表命中：**50/50** 任务（41/41 缺陷程序），两个候选源码根
  （`~/.cache/aitester/quixbugs`、`data/quixbugs`）逐任务 sha256 同值。
- 主判定集（41）expr 通道非空子句预检：pre 67 / post 84 / inv 28 = **179**；
  `max_sublist_sum` 无 `*_expr`（按通道规则回退 NL，2 pre + 3 post）→
  预计 **D1 ≈ 184**。
- 签名参数：41 个缺陷程序中 1 个（`node`，锚函数名 `Node.__init__`）需点分末段
  回退；回退失败则其子句全部计 `error`。
- df_spec detection 可判定 35 / positive 19（与 `DF_SPEC_REPORT.json` 一致）。

## 修订记录（跑前，求解器未调用）

- **R1（2026-10-18 09:2x，首次求解器调用之前）**：原判据「同输入两次运行
  `PER_CLAUSE.jsonl`/`TASK_LEVEL.json` 逐字节一致」不可满足——逐子句观测字段
  `smt_solve_ms` 是求解器墙钟，两次运行必然波动。修订为：**进程内第二次独立完整
  求解**后，剔除计时键再比较 status/分类/计数/率字段（逐字段一致为要求）；
  计时键单独列为 volatile。该修订发生在任何求解调用与结果观察之前，不涉及
  判定阈值、材料口径、参数与关联层规则。
