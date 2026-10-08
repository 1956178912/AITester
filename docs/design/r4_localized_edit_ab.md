# R4 A/B 预注册：定位锚定的局部编辑通道（LOCALIZED_EDIT_ENABLE）

- 日期：2026-10-08
- 状态：预注册（跑批前固化；判定规则与阈值在本文件落盘后不因结果而改）
- 关联：`src/tools/patch_localized.py`、ADR-0024（反事实 FL 上界）、ADR-0028（FL 约束观测门）、ADR-0018（编辑意图确定性落盘）

## 目的

验证"定位锚定的局部编辑约束"（`LOCALIZED_EDIT_ENABLE`）对修复质量的增量贡献。
ADR-0024 反事实指出 `P(correct | FL 命中)=15.8%` < `P(correct | FL 未命中)=64.7%`，
根因是补丁生成走整文件重写、不消费定位信号。本实验在"编辑意图通道
（`EDIT_INTENT_ENABLE`）"之上叠加定位锚定约束，隔离后者的净贡献。

## 臂

| 臂 | 环境变量 | 含义 |
|----|----------|------|
| A（对照） | `EDIT_INTENT_ENABLE=true` | 编辑意图通道，**无**定位约束（历史口径） |
| B（处理） | `EDIT_INTENT_ENABLE=true` + `LOCALIZED_EDIT_ENABLE=true` | 编辑意图 + 定位锚定约束（R4） |

两臂均为 `aitester` 完整管线；差异仅 `LOCALIZED_EDIT_ENABLE` 一个开关。
`AITESTER_PROFILE=logic` 已注入 `FAULT_LOCALIZER_ENABLE=true` +
`FL_SPECTRAL_ENABLE=true`，故定位信号在两臂均产出（A 臂仅"告知"、B 臂升级为"约束"）。

## 设计

- 数据集：synthetic，n=50，seed=42
- 模型：deepseek-flash（`.env.local` LLM_1）
- `AITESTER_PROFILE=logic`、`TEMPERATURE=0`（确定性采样）、`--max-pattern-repeat 2`
- 基线：`aitester` 单臂（两批各一臂，`--skip-stats` 后手工对比）
- LLM 缓存：两臂 Debugger prompt 不同（B 多局部化约束段），缓存 key 天然隔离；
  Planner / FaultLocalizer prompt 相同可命中缓存（保证定位一致 + 省 token）。

## 主终点

1. `repair_rate`（gold 独立裁决，修正口径——见 ADR-0021/0027）
2. `patch_correct` 行数

## 机制终点

1. `edit_localization.localized_ratio`（仅 B 臂非 None；衡量约束被 LLM 遵循程度）
2. `edit_localization.violations`（锚点越界诊断分布）
3. `fl_constraint_verdict`（hit / miss 占比——补丁实际修改位置与定位候选的求交）

## 判定规则

- H1（主）：B 臂 `repair_rate` ≥ A 臂，且 `patch_correct` 不下降；
- H2（机制）：B 臂 `localized_ratio` > 0（约束被遵循，非空转）；
- H3（机制）：B 臂 `fl_constraint_verdict=hit` 占比 ≥ A 臂。

结果如实记录，不因方向不理想而筛选或改判。若 H1 不成立（局部化约束未提升修复率），
记为阴性（与 ADR-0024"生成侧主导"结论一致：约束落点可能仍未触及整文件重写的根因）；
若 H2 不成立（`localized_ratio`≈0），说明 LLM 未遵循约束或锚点过严，需回查 prompt 契约。

## 就绪命令

```bash
# A 臂（对照）
AITESTER_PROFILE=logic EDIT_INTENT_ENABLE=true \
  .venv/bin/python experiments/run_main_batch.py \
  --task-count 50 --seed 42 --baselines aitester --max-pattern-repeat 2 --skip-stats

# B 臂（处理）
AITESTER_PROFILE=logic EDIT_INTENT_ENABLE=true LOCALIZED_EDIT_ENABLE=true \
  .venv/bin/python experiments/run_main_batch.py \
  --task-count 50 --seed 42 --baselines aitester --max-pattern-repeat 2 --skip-stats
```
