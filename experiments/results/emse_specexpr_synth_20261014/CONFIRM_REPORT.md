# SpecExpr 确认性实验报告（synthetic seed 45/46，2026-10-14）

> 预注册：`docs/emse/SPECEXPR_SYNTH_CONFIRM_PREREG_2026-10-14.md`；复算：`experiments/emse_specexpr_confirm.py`（零 LLM）。

## 1. 主分析：2 种子合并 McNemar（specir vs replace）

| 指标 | 值 |
|---|---|
| 配对数 n | 174 |
| 不一致对（仅 specir / 仅 replace） | 1 / 2 |
| 双中 / 双未 | 4 / 167 |
| δ | -0.57pp |
| p（精确） | 1 |
| BF10（Jeffreys / Uniform） | 0.5 / 2 |
| BF 判读 | 1/3≤BF10≤3：数据不充分，不得作任一方向结论 |
| MDE(80%) | 1.39pp |
| 8pp 所需配对数 | 6 |
| 8pp 功效 | 1 |
| **判定（预注册规则）** | **not_confirmed** |

## 2. 单种子 McNemar

| 种子 | n | 仅specir | 仅replace | δ | p | 判定 |
|---|---|---|---|---|---|---|
| 45 | 87 | 0 | 1 | -1.15pp | 1 | not_confirmed |
| 46 | 87 | 1 | 1 | 0pp | 1 | not_confirmed |

## 3. 敏感性：双臀均应用 spec_replace 的纯处理子集

| 指标 | 值 |
|---|---|
| 配对数 n | 122 |
| δ | -1.64pp |
| p（精确） | 0.5 |
| 判定 | not_confirmed |

## 4. 机制观测与审计

| 种子·臂 | 行数 | spec_replace 应用分布 | 回退率 | expr覆盖 | 编译率 | detection可用/阳性 |
|---|---|---|---|---|---|---|
| 45·replace | 87 | {'attempted_fallback': 21, 'attempted_replaced': 66} | 0.2414 | —（n=0） | —（n=0） | 87/3 |
| 45·specir | 87 | {'attempted_fallback': 17, 'attempted_replaced': 70} | 0.1954 | 0.6928（n=70） | 0.3383（n=87） | 87/2 |
| 46·replace | 87 | {'attempted_replaced': 72, 'attempted_fallback': 15} | 0.1724 | —（n=0） | —（n=0） | 87/3 |
| 46·specir | 87 | {'attempted_replaced': 70, 'attempted_fallback': 17} | 0.1954 | 0.7477（n=70） | 0.282（n=87） | 87/3 |

- 不对称应用审计（两臂 spec_replace_applied 不一致的任务数）：**34**（理论预期 0）。双向分解：
  - seed45：forward（replace 应用/specir 回退）7，**reverse（replace 回退/specir 应用）11**——reverse 违反材料包含律（SpecExpr 材料 ⊇ NL 材料），根因为 temp=0 下 Planner 对 synthetic 任务的跨跑批非确定性（JSON 解析失败频发；实测 reverse 案例 iters=0/regen=0，排除再生成路径覆写）。属处理前噪声，两臂同型；对结论的影响由 §3 纯处理子集覆盖。
  - seed46：forward（replace 应用/specir 回退）9，**reverse（replace 回退/specir 应用）7**——reverse 违反材料包含律（SpecExpr 材料 ⊇ NL 材料），根因为 temp=0 下 Planner 对 synthetic 任务的跨跑批非确定性（JSON 解析失败频发；实测 reverse 案例 iters=0/regen=0，排除再生成路径覆写）。属处理前噪声，两臂同型；对结论的影响由 §3 纯处理子集覆盖。
- provenance 校验（干净口径 + SPEC_IR 臂标识）：通过

## 4b. 设计敏感性（区分真阴性与功效失败）

| 指标 | 值 |
|---|---|
| replace 臂 detection 边际率 | 0.0345（6/174） |
| specir 臂 detection 边际率 | 0.0287（5/174） |
| 若存在 +8pp 效应，预期不一致对数 | ≈24.5 |
| 若存在 +12pp 效应（QuixBugs 量级），预期不一致对数 | ≈31 |

实测不一致对仅 **3**（1:2）——远小于 QuixBugs 量级效应的预期产出，故本阴性为**信息性真阴性**而非功效失败（§1 表中 MDE 以实测近零不一致率为条件，会给出过于乐观的小数值，以本节无条件陈述为准）。

## 5. 跨数据集一致性（QuixBugs pilot，不合并检验）

| 数据集 | n | 仅specir | 仅replace | δ | p | 判定 |
|---|---|---|---|---|---|---|
| QuixBugs pilot（标准口径·双方非None） | 35 | 6 | 1 | 14.29pp | 0.125 | not_confirmed |
| QuixBugs pilot（RERUN_REPORT 口径·None记0，对账） | 50 | 7 | 1 | 12pp | 0.0703 | trend |
| synthetic 合并（本报告） | 174 | 1 | 2 | -0.57pp | 1 | not_confirmed |

**口径勘误**：RERUN_REPORT 与 EMSE 主报告 §6.7 引用的 pilot 值（7:1 / n=50 / δ=+12.00pp / p=0.0703）为 None-记-0 口径（分母含 15 个不可测任务）；项目标准口径（与 D1 n=36、scale87 n=35 同族）为 6:1 / n=35 / δ=14.29pp / p=0.125。两口径方向一致，标准口径效应量更大、显著性更弱——对外引用须以标准口径为准。

## 6. 成本

| 种子·臂 | tokens | 调用 | 缓存命中 |
|---|---|---|---|
| 45·replace | 386975 | 198 | 2 |
| 45·specir | 651821 | 236 | 5 |
| 46·replace | 361512 | 186 | 0 |
| 46·specir | 623616 | 220 | 3 |
