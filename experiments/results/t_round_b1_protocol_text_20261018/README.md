# T2/B1：RT1 协议文本消融的指纹级复现（3 格 × 2 seed，真 LLM）

> **性质**：预注册判定测量（`PREREG.md` 跑前冻结，判定规则不得事后改动）。本报告只按冻结规则给 `verdict`，并如披露成本/墙钟/指纹/旧批漂移与局限。

## 0. 摘要

**联合 verdict：`confirmed`**（H-text=`replicated_strong`，H-sampling=`sampling_effect_negligible`）。

- H-text: 2/2 seed 可判定；Δ_text_pp={42: 16.09, 44: 19.54}；McNemar p={42: 0.000519, 44: 1.5e-05}
- H-sampling: 2/2 seed 可判定；Δ_sampling_pp={42: 1.15, 44: -2.3}；McNemar p={42: 1.0, 44: 0.5}

- 证据质量：6 跑 `git_dirty` 全为 false 且 `git_sha` 全等于切点；`model_fingerprint` 块在场=True，**pinned 全为 true=True**（可称『指纹级（pinned）』）；指纹探针 sha 唯一值数=1、返回模型=['deepseek-flash']。
- 成本/墙钟：6 跑估算 **$0.8763**（价目表标准价上界口径，非账单）/ 批次墙钟 **1299s**（上限 $2.0 / 5400s）。
- 失败/缺失：无（6/6 跑批 ok）。
- **执行性修订（判据未改）**：首跑因批后 mutation/MDO 辅助测量墙钟超预期被中止（无主终点数据损失，日志归档 `_superseded_first_attempt/`）；六格统一以 `ENABLE_MUTATION_SCORING=false` 重跑（只关辅助测量字段；详见 `PREREG_CONTINUATION.md`，sha256 `4cb5218d158e80a7…`）。

## 1. 设计与切点

- 切点：`a93c1f60ee31b9582e0146f73e3038e6ce0f01a1`；跑批工作树：`/Users/wangchenyu/Workspace/AITester-t-b1-a93c1f6`（与切点一致、全程 clean；本批零代码修改）。
- 数据：`synthetic`，`--task-count 87 --max-pattern-repeat 2`；seeds = [42, 44]。
- 三格（每 seed 独立跑，同一运行协议，仅 `--baselines` 与一个 env 开关不同）：

| 格 | `--baselines` | 再生成路由 | 强化段落 | 语义 |
|---|---|---|---|---|
| C1 | `plain_llm` | 无 | 无 | plain_llm |
| C2 | `plain_llm_df` | 有 | 无 | rt1 |
| C3 | `plain_llm_df` | 有 | 有 | df_full |

- 共享 env：`AITESTER_PROFILE=logic`，`TEMPERATURE=0.0`，`LLM_THINKING_MODE=disabled`，`BENCHMARK_PARALLELISM=4`，`AITESTER_LLM_CACHE=0`，`COST_BUDGET_ENABLE=true`，`COST_BUDGET_TOKENS=200000`，`COST_BUDGET_USD=1.0`，`AITESTER_BATCH_MAX_CALLS=4000`，`AITESTER_BATCH_MAX_USD=2.0`，`ENABLE_MUTATION_SCORING=false`；每跑独立 `AITESTER_CACHE_NAMESPACE=t_b1_<cell>_<seed>`、独立 `AITESTER_TRACE_DIR`。
- 格间唯一 env 差异：C2 额外 `DETECTION_FIRST_SECTION_ENABLE=false`（只关强化段落、**不动路由**——PREFLIGHT 的干预探针已逐项验证：section_on→段落 196 字符、section_off→None、`regenerate_entry=True` 不变）。
- 主口径：行 detection_rate（>=1.0 记检出；None 不进分母）；并列 行 llm_suite_detection_rate（同口径并列，若存在）。配对按 `task_id`（同 seed 三格集合一致，GATES 硬检查）。

## 2. 逐 seed 三格主表（detection，行 `detection_rate`）

| seed | 格 | 检出/可测 | 检出率 | llm_suite 检出/可测 | passed | tokens | 估算$ | 墙钟s | 再生成行 | 0/1 regen 计数分布 |
|---|---|---|---|---|---|---|---|---|---|---|
| 42 | C1 | 9/87 (10.3%) | 10.34pp | 9/87 (10.3%) | 69/87 (79.3%) | 105689 | 0.0899 | 156 | 0 | {"0": 87} |
| 42 | C2 | 10/87 (11.5%) | 11.49pp | 10/87 (11.5%) | 67/87 (77.0%) | 199217 | 0.1689 | 227 | 79 | {"0": 8, "1": 79} |
| 42 | C3 | 24/87 (27.6%) | 27.59pp | 24/87 (27.6%) | 47/87 (54.0%) | 218779 | 0.1843 | 249 | 79 | {"0": 8, "1": 79} |
| 44 | C1 | 12/87 (13.8%) | 13.79pp | 12/87 (13.8%) | 65/87 (74.7%) | 102155 | 0.0856 | 149 | 0 | {"0": 87} |
| 44 | C2 | 10/87 (11.5%) | 11.49pp | 10/87 (11.5%) | 69/87 (79.3%) | 197865 | 0.1674 | 227 | 77 | {"0": 10, "1": 77} |
| 44 | C3 | 27/87 (31.0%) | 31.03pp | 27/87 (31.0%) | 41/87 (47.1%) | 215349 | 0.1801 | 273 | 77 | {"0": 10, "1": 77} |

## 3. 效应表（配对 + McNemar 精确双侧 + bootstrap CI）

### 3.1 文本净效应：C3 − C2（两者路由/再生成一致，唯一差别 = 强化段落文本）

| seed | C3 率 | C2 率 | Δ_text（臂率，pp） | 检出计数差 | 配对可测 | b (C3 only) | c (C2 only) | 不一致对 | Δ_paired（pp） | McNemar p（双侧） | bootstrap 95% CI（pp） |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 42 | 27.59pp | 11.49pp | **16.09** | +14 | 87 | 15 | 1 | 16 | 16.09 | 0.000519 | [8.05, 24.14] |
| 44 | 31.03pp | 11.49pp | **19.54** | +17 | 87 | 17 | 0 | 17 | 19.54 | 0.000015 | [11.49, 27.59] |

### 3.2 多一次采样效应：C2 − C1（C1 无再生成路由；C2 首轮全绿会再生成一次）

| seed | C2 率 | C1 率 | Δ_sampling（臂率，pp） | 配对可测 | b (C2 only) | c (C1 only) | 不一致对 | McNemar p（双侧） | bootstrap 95% CI（pp） |
|---|---|---|---|---|---|---|---|---|---|
| 42 | 11.49pp | 10.34pp | **1.15** | 87 | 1 | 0 | 1 | 1.000000 | [0.00, 3.45] |
| 44 | 11.49pp | 13.79pp | **-2.30** | 87 | 0 | 2 | 2 | 0.500000 | [-5.75, 0.00] |

## 4. 预注册判定（`PREREG.md` §5，冻结规则）

| 判据 | 规则（跑前冻结） | 结果 |
|---|---|---|
| H-text | 每 seed Δ_text_pp>0 且 2/2 方向一致 → replicated；≥1 seed McNemar p<0.05 → strong；任一 seed Δ≤0 → not_replicated | **`replicated_strong`**（显著 seeds=[42, 44]） |
| H-sampling | 每 seed |Δ_sampling_pp|≤5.0pp 且 McNemar p≥0.05；2/2 满足 → negligible | **`sampling_effect_negligible`** |
| 联合 | 见 PREREG §5 表 | **`confirmed`** |

## 5. 与 2026-10-09 旧批并排（描述性；旧批不构成本批判据）

| 臂 | 旧批（2026-10-09，seed42） | 本批 seed42 | 本批 seed44 | 漂移说明 |
|---|---|---|---|---|
| C1/plain_llm | 9/87 (10.3%) | 9/87 (10.3%) | 12/87 (13.8%) | 旧批 git_dirty=True、无 model_fingerprint；绝对漂移只作描述 |
| C2/rt1 | 10/87 (11.5%) | 10/87 (11.5%) | 10/87 (11.5%) | 旧批 git_dirty=True、无 model_fingerprint；绝对漂移只作描述 |
| C3/df_full | 27/87 (31.0%) | 24/87 (27.6%) | 27/87 (31.0%) | 旧批 git_dirty=True、无 model_fingerprint；绝对漂移只作描述 |

旧批配对复算（从旧工件的行字段直接重算，供核对 BASELINE.yaml 已登记口径）：

| 对比 | b | c | 不一致对 | Δ（pp） | McNemar p |
|---|---|---|---|---|---|
| text_old_df_vs_rt1 | 17 | 0 | 17 | 19.54 | 0.000015 |
| sampling_old_rt1_vs_plain_llm | 1 | 0 | 1 | 1.15 | 1.000000 |

## 6. 成本、墙钟与预算护栏

| 项 | 值 |
|---|---|
| 6 跑估算费用（标准价上界口径） | **$0.8763** |
| 逐跑费用 | {"C1_seed42": 0.089914, "C2_seed42": 0.168927, "C3_seed42": 0.184313, "C1_seed44": 0.085611, "C2_seed44": 0.167431, "C3_seed44": 0.180143} |
| 价格口径 | experiments/price_table.json deepseek-flash input 0.3 / output 1.2 USD per Mtok（标准价，上界口径，非账单） |
| 逐跑墙钟之和 | 1281 s |
| 批次墙钟 | 1299 s（上限 5400 s / 90 min） |
| 预算 | $0.8763 ≤ $2.0 上限；`within_budget=True`，`within_wall=True` |

## 7. 证据质量（指纹 / 洁净树 / 门禁）

| 项 | 结果 |
|---|---|
| 切点 sha（6 跑 provenance 一致） | `a93c1f60ee31b9582e0146f73e3038e6ce0f01a1` |
| `git_dirty` | 全为 false（GATES：`provenance_clean_tree`） |
| `model_fingerprint` 块在场 | True |
| `model_fingerprint.pinned` | 全 true=True；返回模型=['deepseek-flash']；探针 sha 唯一值数=1（≤1 = 同快照） |
| GATES 状态 | `pass`；blocking=[]；warnings=[] |
| 数据质量：`detection_rate` vs `llm_suite_detection_rate` | 不一致 0 行（N-3 口径两键同值） |
| 执行性修订生效性（GATES `mutation_scoring_disabled_all_runs`） | 六跑 `env_snapshot.ENABLE_MUTATION_SCORING=false`（只关批后辅助测量；`PREREG_CONTINUATION.md`） |

## 8. 口径与局限（必须并列披露）

1. **样本小**：87 任务 × 2 seed；McNemar 只在不一致对上检验，功效有限。`direction_only` 不得读成「无效应」。
2. **旧批不可直接合并**：2026-10-09 旧批 `git_dirty=true`、`model_fingerprint` 缺失、单 seed；本批与其绝对值的差异混有代码状态与模型快照漂移，只作描述性并排。
3. **浮动别名**：`deepseek-flash` 为请求侧别名；本批以 `model_fingerprint`（returned_model / system_fingerprint / 探针 sha256）记录快照证据。本批 pinned=true，可称指纹级。
4. **`detection_rate` 是协议级信号**：不得当作测试质量通用代理（`docs/VALIDITY.md` §5.1）。
5. **C1→C2 的『多一次采样』是复合干预**：C2 相对 C1 同时打开了再生成路由与相应计数；本批把它整体作为『多一次采样/再生成效应』报告，不进一步拆分内部调用差异。
6. **不是假修复结论**：本批主终点只有 detection；false-fix/声明通过率只作并列读数，不支持「检出优先减少假修复」的因果主张（见 `docs/VALIDITY.md` §5.2）。
7. **B2 主批次并行运行**：CPU/API 争用可能抬高墙钟与重试，本批未因此降并行度或缩样本；实际墙钟见 §6。
8. **执行性修订（非判据修订）**：见 `PREREG_CONTINUATION.md`。首跑（C1_seed42，修订前）因 `ENABLE_MUTATION_SCORING=true` 的内联 mutation_score + MDO 批后辅助测量耗时 >10.5 min 未结束而被中止，未产出批次 JSON（日志归档 `_superseded_first_attempt/`）；六格最终统一以 `ENABLE_MUTATION_SCORING=false` 重跑。该开关只影响批后 `mutation_score`/`mdo_*` 辅助字段，**不影响** detection/生成/再生成/提示/预算，本批结论不引用任何 mutation/MDO 数值。

## 9. 文件清单

| 文件 | 说明 |
|---|---|
| `PREREG.md` | 跑前冻结预注册（判定/停止规则/预算/产物） |
| `PREFLIGHT.json` | 工作树/预注册/导入源/CLI/干预开关/旧批复算/预算估算 + dry-run 记录 |
| `staging/<cell>_seed<seed>/benchmark_synthetic_<ts>.json` | 6 份原始批次工件 |
| `logs/<cell>_seed<seed>.log` | 6 份运行日志（起止/命令/env/退出码/墙钟） |
| `traces/<cell>_seed<seed>/` | `AITESTER_TRACE_DIR` 追踪产物 |
| `seed42/`、`seed44/` | 每 seed 三格抽取元数据 `meta_<cell>.json` |
| `RUN_SUMMARY.log` | 逐跑摘要 + 批次汇总（token/费用/墙钟/再生成行） |
| `GATES.json` | 硬门禁（行数/task 集合/洁净树/指纹/开关/预算） |
| `ANALYSIS_REPORT.json` | 本报告机器可读版（含逐任务配对表、旧批并排、逐跑 fingerprint） |
| `README.md` | 本中文报告 |
| `PREREG_CONTINUATION.md` | 跑中执行性修订（判据未改；辅助测量关闭 + 续跑规则）与首跑中止记录 |
| `_superseded_first_attempt/` | 修订前首跑日志归档（无主终点数据；不参与分析） |
| `DOC_RECONCILIATION.md` | 陈旧文档声明核对清单（Lead 采纳修正） |
| `SHA256SUMS` | checksum_results.py --write 生成、--verify 通过 |
| `_helpers/` | 零 LLM 可复算脚本（preflight/extract/gates/analyze/limited_run） |

## 10. 复现命令

```bash
# 1) 建 worktree（切点）并复制敏感配置（不打印/不提交）
git -C /Users/wangchenyu/Workspace/AITester worktree add --detach /Users/wangchenyu/Workspace/AITester-t-b1-a93c1f6 a93c1f60ee31b9582e0146f73e3038e6ce0f01a1
cp /Users/wangchenyu/Workspace/AITester/.env /Users/wangchenyu/Workspace/AITester/.env.local /Users/wangchenyu/Workspace/AITester-t-b1-a93c1f6/

# 2) 跑前自测（零 LLM）→ 真实跑批
cd /Users/wangchenyu/Workspace/AITester && bash experiments/run_t2_b1_protocol_text.sh --dry-run
cd /Users/wangchenyu/Workspace/AITester && nohup bash experiments/run_t2_b1_protocol_text.sh > /tmp/t2_b1_runner.log 2>&1 &

# 3) 分析 + 门禁 + 校验（零 LLM）
/Users/wangchenyu/Workspace/AITester/.venv/bin/python experiments/results/t_round_b1_protocol_text_20261018/_helpers/gates.py --out experiments/results/t_round_b1_protocol_text_20261018 --expect-sha a93c1f60ee31b9582e0146f73e3038e6ce0f01a1
/Users/wangchenyu/Workspace/AITester/.venv/bin/python experiments/results/t_round_b1_protocol_text_20261018/_helpers/analyze.py --out experiments/results/t_round_b1_protocol_text_20261018 --write
/Users/wangchenyu/Workspace/AITester/.venv/bin/python /Users/wangchenyu/Workspace/AITester/scripts/gates/checksum_results.py --write --results-dir experiments/results/t_round_b1_protocol_text_20261018
```

