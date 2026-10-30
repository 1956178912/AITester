# Q03/Q04/Q07 三组 A/B 预注册（2026-10-30，数据产生前冻结）

> 授权：用户 2026-10-30「需要 LLM 的也可以跑」+「优先把能跑的跑起来」。
> 本文件在**任何一臂启动前**落盘；判据冻结后取数，偏离须登记偏离表。
> 预算闸：任务级 COST_BUDGET_USD=1.0 / 批级 AITESTER_BATCH_MAX_USD=6.0，全程生效。

## 共同口径

- 数据集 synthetic 87 / seed 42（E8 同款语料，spec_compile 可测）；
  Q07 另跑 quixbugs 50（deterministic_repair 目标场景）；
- 臂配置：`AITESTER_PROFILE=logic TEMPERATURE=0.0 LLM_THINKING_MODE=disabled
  MAX_ITERATIONS=3 EXECUTION_TIMEOUT=30 ENABLE_RAG=false AITESTER_LLM_CACHE=0`
  （E8 current-off 同款；thinking 关为成本保护口径）；
- 每臂 `--baselines aitester` 单臂、`--skip-stats`，判定后置；
- 双开关均已在 `_env_snapshot_keys`（ORACLE_CONTEXT_TIER 在 logic_spec.py 扫描面；
  DETERMINISTIC_REPAIR_FIRST_ENABLE 为 `_ENABLE$` 形态被 CI 门禁覆盖）。

## Q04：oracle 生成上下文消融（ORACLE_CONTEXT_TIER）

- H（ASE 2025 方向复检）：minimal（剥四增强段）相对 full 的
  spec_compile_rate 差 ≥ −5pp（ROPE ±5pp 内视为等价）；若等价成立 ⇒
  支持降默认成本；若显著为负 ⇒ full 默认保留。
- 主终点：spec_compile_rate；次要：token 成本 / detection_rate。
- 判定：两臂 87 任务配对差 + bootstrap 95% CI（10,000 次）。

## Q07：确定性修复优先灰度（DETERMINISTIC_REPAIR_FIRST_ENABLE）

- H：on 相对 off 不劣于 −3pp（detection_rate）；token 成本显著下降
  则支持转正。零 LLM 确定性接管不消耗 token——预期 on 臂均成本下降。
- 主终点：detection_rate / false_fix_rate；次要：token 成本 / LLM 调用数。

## Q03：CF 运行时 gold 注入臂

- 开关与回放协议以 `src/agents/fault_localizer.py` 现场实装为准（启动前
  grep 确认开关名与默认值；若实装缺口无法在预算内闭合 ⇒ 披露放弃，不强跑）。

## 诚实条款

- 单 seed、单模型（deepseek-flash）、synthetic 语料饱和风险（G03 教训：
  合成语料两臂可能同满分）——若两臂同饱和，读数记「不可区分」而非 0 效应；
- 判读数前不得改判据；工作树 dirty 披露（results 写入）。
