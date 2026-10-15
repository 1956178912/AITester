# EMSE 投稿优化记录（批次：审稿可判性收口，2026-10-15）

本文件记录本轮"根据 EMSE 诊断结论优化项目"的**已完成动作、验证口径、新增实证发现、
以及仍需人工/最新材料才能完成的项**。所有改动均在 HEAD=`53053d6` 基线上完成，
工作树改动范围见文末"改动清单"。

---

## 1. 本轮已完成的优化（代码 / 口径 / 文档）

### 1.1 测量口径与统计可判性

| 项 | 问题（优化前） | 改动 | 验证 |
|----|---------------|------|------|
| **首要结论口径缺多重比较校正** | `bh_fdr_correct` 仅作用于 `passed`（自指、已降级）口径的 McNemar p 值；报告声明为"首要结论口径"的 detection/repair 节**无 q 值**（审稿人一旦发现即为方法学硬伤） | `experiments/statistical_analysis.py`：`honest_comparisons` 按**指标族**独立做 BH-FDR（detection 族 / repair 族各自构成 FDR 分母，不跨指标混池），新增 `fdr_adjusted_p` / `fdr_rejected`；控制台与报告表新增 q 值列；节内新增"多重比较校正"口径说明 | 实跑三种子合并批次：detection 两比较 q=0.0000（FDR 后仍显著），repair 两比较 q=1.0000（零效应如实呈现） |
| **"独立裁决"术语歧义** | 全项目 "gold 独立裁决" 指**判据材料独立**（留出 gold 测试/补丁），但英文读者/审稿人易误读为**人工裁决**；仓库实际**无任何人工裁决**（全仓 `kappa` 0 命中；E7 预注册未执行） | 代码侧 20 处表述改为"gold 材料独立裁决（自动化 oracle，无人工参与）"；报告节新增口径说明段（明确"不含人工裁决"、E7 未执行）；`README.md` / `README.en.md` 基准指标节新增术语范围声明；`BASELINE.yaml` 新增 `terminology_scope` 机器可读节 | 双语门禁通过；`check_baseline.py` / `check_baseline_numbers.py` 通过 |
| **口径标签纪律（δ 与 repair 多值）** | 三种子合并 δ=−0.279（−28pp）与 E2 δ=−0.3673、repair v2 39.31%(57/145) 与 v1 35.86%(52/145) 并存，易被误读为"数字矛盾" | `BASELINE.yaml` 新增 `caliber_labels` 节，逐项声明每个数值的**实验代际**（E2 vs 三种子合并；v2 含 R27 跨文件物化 vs v1 伪影下界） | 结构门禁通过；README 同步指向 |

### 1.2 构念效度：mutation × detection 交叉验证（从"声称"变为"真算"）

- **问题**：`experiments/emse_optimization.py::mutation_correlation()` 的 docstring 声称计算
  Pearson/Spearman，**函数体实际只返回计数与检出=1 时的均值**——论文若据此声称"已与
  变异得分交叉验证"即为不实陈述。
- **改动**：补齐真实 `pearson` / `spearman` 系数、`mean_when_detection_0`、
  `mean_delta_det1_minus_det0`、退化原因 `spearman_reason`，以及机器可读的
  `interpretation_caveat`；新增 `mutation_correlation_report()` + CLI
  `--mutation-correlation` + `make mutation-det-correlation`。
- **诚实纪律内置**：变异得分饱和阈值 0.98（与 `experiments/target_quality_replay.py` 同口径）
  → 饱和即标 **无鉴别力**；报告固定包含"解读纪律"与"方向性发现"段。

### 1.3 真实基准失败的结构化披露

- **问题**：SWE-bench Lite 的"基础设施故障、无有效能力结论"仅存在于散文与一个**只被测试消费**
  的函数中；结果工件仍以 `pass_rate: "0/7 (0%)"` 为一等指标（=死端）。
- **改动**：`swebench_infra_facts()` 升级为结构化判据（限流信号优先取
  `results_summary.notes` 结构化字段；超时占比阈值 0.5），新增 `capability_conclusion`、
  `pass_rate_must_not_be_quoted`、`timeout_ratio`、`rate_limit_signals`；新增
  `swebench_disclosure_report()` + CLI `--swebench-disclosure` + `make swebench-disclosure`。
- **当前实测输出**：`capability_conclusion = none_valid_infrastructure_failure`，
  `pass_rate_must_not_be_quoted = true`（20 次尝试：7 完成 / 3 失败 / 10 超时，7/7 完成者均因 429 失败）。

### 1.4 文档一致性门禁（防"6 vs 7"复发）

- **问题**：同一事实（JSON 契约调用点数）在中英文文档中分裂为 **6（2 处）与 7（3 处）**，
  且**同一文件内自相矛盾**（`README.md:264` vs `:1385`；`MODEL_CARD.md:3` vs `:37`）。
- **改动**：
  1. 权威计数用 **AST** 固定为 **口径 A = 7 处显式 `json_mode=True` 实参调用点**
     （planner:337；debugger:622/643/735/1078/1157；fault_localizer:186）；
  2. 5 份文档 9 处表述全部对齐为 7（中英各 2 处原为 6）；
  3. 新增门禁 `scripts/gates/check_json_contract_sites.py`（`--report` 可打印口径 B 候选），
     接入 `make gates` 与 `make json-contract-sites`。
- **门禁设计要点**：AST 计数避免把文档字符串里的 `json_mode=True` 计入；文档声明解析
  **保留完整行**（早期版本截断 200 字符曾导致 `MODEL_CARD.en.md:3` 误报）。

---

## 2. 本轮新增的实证发现（由 1.2 的交叉验证首次产出）

`make mutation-det-correlation`（R-P0-2 三种子，n=261/臂；零 LLM）：

| 臂 | 配对 n | detection 率 | mean(MS\|det=1) | mean(MS\|det=0) | Δ均值 | Pearson | Spearman | 饱和判定 |
|----|--------|--------------|------------------|------------------|--------|---------|----------|----------|
| aitester | 240 | 15.83% | 0.9934 | 0.9478 | **+0.0456** | +0.0995 | +0.1029 | 近饱和，谨慎解读 |
| plain_llm | 261 | 1.53% | 1.0000 | 0.9710 | +0.0290 | +0.0267 | +0.0369 | 近饱和，谨慎解读 |
| plain_llm_df | 261 | 44.83% | 0.9872 | 0.9907 | **−0.0036** | −0.0193 | −0.0420 | **无鉴别力（饱和）** |

**可写进论文的结论（须带上述局限）**：

1. 变异得分在合成主批次**近乎饱和**（均值 0.95–1.00）——**该指标在本数据集上没有鉴别力**，
   不能用来支持"生成测试质量高"。
2. detection 与 mutation score 的相关性**弱且不一致**：aitester 弱正相关（+0.10），
   而**最强基线 plain_llm_df 为弱负相关（−0.02 ~ −0.04）**——"检出更多"并未伴随"变异得分更高"。
3. 因此 **detection_rate 不能被视为"测试质量"的通用代理**；论文必须把它定位为
   **特定于本基准的检出信号（protocol-level signal）**，并把这些数字作为**构念效度的
   反证证据**如实披露（这是审稿人 1/3 最可能追问的点，现在有据可答）。

> 注：本表同时暴露一个可深挖的方向——plain_llm_df 的 44.83% 检出伴随 0.9872 的变异均值，
> 而 aitester 的 15.83% 检出伴随 0.9934；即"检出率"与"变异覆盖"在高饱和区**并不同向**。

---

## 3. 仍未完成（阻塞项与需人工决策项）

| 项 | 状态 | 阻塞原因 |
|----|------|----------|
| **E7 人工复核（唯一能建立 detection 外部校标的动作）** | 未执行 | 需**人力投入**：工作表已备料（`experiments/results/main_batch/e7_review_worksheet.md`，判定列空），预注册口径已定义（五选一）。**建议优先做**：≥40 行分层样本、双人独立、报 Kappa |
| Prompt Card + 哈希锁 | 未执行 | 需**你提供最新 prompt 全文**（detection-first 段落现内联于 `src/graph/nodes.py:540-547`，over-red 于 `:651-667`）；内容需逐字，不能由我改写 |
| QuixBugs 真实缺陷阶梯进正文 | 未执行 | 需确认最新批次口径与授权 |
| 2×2 消融（协议文本 vs 多一次采样） | 未执行 | 双开关已具备（`DETECTION_FIRST_ENABLE` / `DETECTION_FIRST_SECTION_ENABLE`），零新代码；**需 LLM 配额** |
| success 呈现层降级（报告首表/CLI/可视化） | 未执行 | 改报告结构与可视化属于口径变更，需你确认后再动（避免影响已归档报告的既有叙事） |
| regression_rate 未进 M1 聚合 | 未执行 | 第四指标未并列，需确认是否纳入论文主表 |
| 复现包钉 seed/model/temperature/dataset-version | 未执行 | 需确认"三种子"的**实际执行语义**（seed 不传 LLM API，非确定性由缓存命名空间控制） |
| SWE-bench Lite 重跑 | 未执行 | 需配额；且下载器/跑批入口**无配额预算控制**，重跑前建议先补配额闸 |

---

## 4. 验证口径（本轮）

| 检查 | 结果 |
|------|------|
| `ruff check .` | All checks passed |
| `ruff format --check .` | 651 files already formatted |
| `mypy src/ config.py` | Success: no issues found in 131 source files |
| 受影响模块测试（6 个文件） | 132 passed |
| 全量测试（`pytest -n 4 --dist loadfile`） | **6021 passed / 4 skipped / 0 failed**（85.3s，CI 同口径） |
| `check_bilingual_docs.py --strict` | 通过（0 警告 / 0 失败） |
| `check_baseline.py` + `check_baseline_numbers.py` | 通过 |
| `check_json_contract_sites.py`（新增） | 通过（口径 A=7，9 处文档表述一致） |
| `make mutation-det-correlation` | 产出 `experiments/results/main_batch/mutation_detection_correlation.md` |
| `make swebench-disclosure` | 产出 `experiments/results/emse_swebench_disclosure.md` |
| 首要口径 FDR 端到端 | detection q=0.0000 显著；repair q=1.0000（如实） |

---

## 5. 改动清单（18 文件 + 2 新增）

**新增**
- `scripts/gates/check_json_contract_sites.py`（门禁，接入 `make gates`）
- `docs/emse/EMSE_OPTIMIZATION_2026-10-15.md`（本文件，优化记录）

**机器生成的报告（有意不纳入版本控制）**
- `experiments/results/main_batch/mutation_detection_correlation.md`（`make mutation-det-correlation` 再生）
- `experiments/results/emse_swebench_disclosure.md`（`make swebench-disclosure` 再生）

理由：二者均可由已入库的源工件（三种子批次 JSON + `experiments/results/swebench_20_summary.json`）
零 LLM 一键再生，属**派生物**而非一次性的实验证据；证据链仍指向源 JSON，
`scripts/gates/check_artifacts_tracked.py` 的 MANIFEST 无需变更（该项新增登记会
反向要求把派生物入库，与"可再生产物不入库"的既有口径冲突）。

**修改**
- `experiments/statistical_analysis.py`（首要口径 BH-FDR + q 列 + 口径说明段 + 术语精度）
- `experiments/emse_optimization.py`（mutation 相关性真算 + 交叉验证报告 + SWE-bench 结构化披露 + 两个 CLI 入口）
- `experiments/_m1_metrics.py`、`experiments/run_benchmark.py`、`experiments/repair_replay.py`、
  `experiments/repair_ceiling_analysis.py`、`experiments/run_orchestration_search.py`、
  `experiments/trusted_verification.py`、`src/tools/patch_applier.py`（术语精度）
- `tests/test_emse_optimization.py`（3 个新回归：系数真算 / 负方向如实呈现 / 退化 reason）
- `Makefile`（`mutation-det-correlation`、`swebench-disclosure`、`json-contract-sites`，并入 `gates`）
- `README.md` / `README.en.md` / `MODEL_CARD.md` / `MODEL_CARD.en.md`（术语范围 + 6→7 对齐）
- `BASELINE.yaml`（`terminology_scope` + `caliber_labels`）

**未改动（有意）**：`docs/adr/0021|0027|0029|0015|0016`、`docs/design/*caliber_matrix*` 等
历史决策/口径记录——历史文档不得改写；术语权威定义改由 `README` + `BASELINE.yaml` 承载，
历史文档的表述由该定义统一解释。
