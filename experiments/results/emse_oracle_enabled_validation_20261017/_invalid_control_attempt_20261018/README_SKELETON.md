# O-2 oracle-enabled 二臂验证批（20 任务）— README 骨架（真跑前生成，1425ee74490b）

> 本文件是零 LLM 骨架；真实跑批完成后由 `run_oracle_validation_batch.sh` 生成正式 `README.md`（数字全部来自两臂批次 JSON）。

## 1. 协议（固定，验证性非 confirmatory）

- 切点 worktree：`/Users/wangchenyu/Workspace/AITester`，HEAD=`1425ee74490ba6e2be15fd0feb87fc6f07ea856e`，跑前/跑后 `git status --porcelain` 0 行。
- 臂 A（control）：`--baselines plain_llm_df_spec`（oracle 关闭）；臂 B（oracle）：同一 baseline + `SPEC_ORACLE_EXEC_ENABLE=true`；两臂不设 `DETECTION_SPEC_MODE`。
- `--dataset quixbugs --task-limit 20 --seed 42`；`AITESTER_PROFILE=logic TEMPERATURE=0.0 LLM_THINKING_MODE=disabled BENCHMARK_PARALLELISM=4`。
- `AITESTER_BATCH_MAX_CALLS=100 COST_BUDGET_ENABLE=true COST_BUDGET_USD=1 AITESTER_LLM_CACHE=0`；两臂独立 `AITESTER_CACHE_NAMESPACE`（`..._control` / `..._oracle`）。
- 零 LLM 材料可行性探测：arm_can_inject_oracle=**True**。

**验证性协议修正（Lead 批准 2026-10-17，方案 a）**：任务书默认 baseline `plain_llm_df` 修正为 `plain_llm_df_spec`。
原因：oracle 材料优先级 = `spec_ir` → `test_plan.logic_analysis` → `spec_anchor.logic_analysis/human_spec`；
`plain_llm_df` 无 planner/无锚表 → 材料为空 → `SPEC_ORACLE_EXEC_ENABLE=true` 只会 `not_attempted`，无法验证注入；
`plain_llm_df_spec` 的 `spec_anchor.logic_analysis`（SPEC_ANCHOR_TABLE）为可编译锚材料。该修正不改任何判定规则/判分口径。

## 2. 两臂结果（真跑后填）

| 项 | A（control） | B（oracle） |
|---|---|---|
| baseline / namespace | | |
| 批次工件 / sha256 | | |
| 墙钟(s) / tokens / 成本($) | | |
| LLM-suite detection（41 口径） | | |
| `spec_oracle_injected` 分布 | | |
| `spec_oracle_verdict` 分布 | | |
| `oracle_suite_verdict` 分布 | | |
| 行字段完整率 | | |

## 3. LLM-suite 一致性（逐任务两臂对比）

（真跑后填：detection_rate / llm_suite_detection_rate 逐任务是否一致 + 不一致清单）

## 4. 成本与墙钟

（真跑后填）

## 5. 异常/局限/披露

- 验证性测量：不作为 confirmatory 判定；预算 ≤$0.2、墙钟 ≤60min。
- 并发调度（两臂并发、各自 P4）；次指标含 CPU 争抢噪声，LLM-suite detection 主指标在任务阶段采集。
- 若协议修正（如 arm baseline 改为 plain_llm_df_spec）已获 Lead 批准，须在此披露。

## 6. 复现

```bash
bash experiments/run_oracle_validation_batch.sh --root <clean-worktree> --require-clean-root \
  --arm-baseline plain_llm_df_spec
```

