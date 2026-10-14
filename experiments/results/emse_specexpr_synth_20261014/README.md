# EMSE SpecExpr 确认性实验批次（synthetic seed 45/46，2026-10-14）

> 预注册：`docs/study/SPECEXPR_SYNTH_CONFIRM_PREREG_2026-10-14.md`（结果产出前落盘，commit `61a7e04`）
> 复算：`experiments/emse_specexpr_confirm.py`（零 LLM；24 例回归测试 `tests/test_emse_specexpr_confirm.py`）
> 主报告：`CONFIRM_REPORT.md` / `CONFIRM_REPORT.json`（同目录）

## 0. 结论先行

**SpecExpr 通道增益在 synthetic 上未复现（信息性真阴性）**：2 种子合并配对
McNemar n=174，仅 specir 检出 1 / 仅 replace 检出 2，δ=**−0.57pp**，p=1.0，
BF10=0.5（数据不充分）→ 预注册判定 **not_confirmed**。设计敏感性：若存在
QuixBugs 量级（+12pp）效应，预期不一致对 ≈25（实测 3）——阴性非功效失败。

机制归因（三条）：① synthetic 上干净口径 detection 基线仅 ~3%（6/174 vs
5/174），天花板远低于 QuixBugs（~63-66%）；② SpecExpr 子句在 synthetic 上的
可编译率仅 **0.3102**（n=174，42% 恒 0，unknown_name 拒绝为主）vs QuixBugs
0.6321——形式化通道在该数据集上显著减弱；③ 回退率 ~20%（无规约材料任务
两臂同回历史口径，无偏稀释）。

## 1. 实验设计（预注册冻结）

| 要素 | 值 |
|---|---|
| 数据集 | synthetic，seed 45 / 46（全新种子；当前生成器，与存量 42/43/44 不可逐位比照） |
| 任务数 | 87/种子（`--task-count 87`） |
| 臂 A（对照） | `DETECTION_SPEC_MODE=replace`（纯 NL 规格优先） |
| 臂 B（处理） | `+ SPEC_IR_ENABLE=true SPEC_IR_DSL_ENABLE=true`（完整规格优先） |
| 干净口径 | 无 profile（fast）；无门/mutation/RAG；planner+debugger 开；temp=0（R11） |
| 缓存 | 每臂独立新 namespace（`specexpr_s{45,46}_{replace,specir}_v1`） |
| 并行 | 2 |
| 模型 | deepseek-flash，指纹 aeb56401ca74e127…（pinned，四臂一致） |

**为什么用新种子**：temp=0 下同任务重跑为零信息重放；QuixBugs 本地集
（50 程序）已耗尽；ULT-lite detection 0/45 无 McNemar 判别力。

## 2. 结果

| 对比 | n | 仅specir | 仅replace | δ | p | 判定 |
|---|---|---|---|---|---|---|
| seed45 | 87 | 0 | 1 | −1.15pp | 1.0 | not_confirmed |
| seed46 | 87 | 1 | 1 | 0pp | 1.0 | not_confirmed |
| **合并（主分析）** | **174** | **1** | **2** | **−0.57pp** | **1.0** | **not_confirmed** |
| 纯处理子集（两臂均 applied） | 122 | — | — | −1.64pp | 0.5 | not_confirmed |

臂级边际 detection：replace 6/174（3.4%）vs specir 5/174（2.9%）。
spec_compile_rate（specir 臂）：seed45 0.3383 / seed46 0.2820，池化
**0.3102**（n=174；QuixBugs pilot 同口径 0.6321）。

## 3. 审计与披露

- **provenance 四臂全部通过**：profile=None、SPEC_IR 臂标识正确、
  DETECTION_SPEC_MODE=replace、缓存 namespace 独立、指纹钉锁一致；
  run1（s45_replace）git_dirty=true（当时分析脚本未提交，src/ 管线未动），
  run2-4 git_sha=7a91f83 clean。
- **不对称应用 34/174（双向）**：seed45 7 forward / 11 reverse；seed46
  9 forward / 7 reverse。reverse 违反材料包含律（SpecExpr ⊇ NL），
  根因 = temp=0 下 Planner 对 synthetic 任务的跨跑批非确定性
  （JSON 解析失败频发；reverse 案例 iters=0/regen=0 排除再生成覆写）。
  处理前噪声、两臂同型；纯处理子集敏感性结论不变。
- **pilot 口径勘误**：RERUN_REPORT / EMSE 主报告 §6.7 引用的 pilot 值
  （7:1/n=50/δ=+12.00pp/p=0.0703）为 None-记-0 口径；项目标准口径
  （双方非 None）为 6:1/n=35/δ=+14.29pp/p=0.125。方向一致，标准口径
  效应量更大、显著性更弱——对外引用以标准口径为准。
- **fallback 率**：replace 臂 0.2414/0.1724，specir 臂 0.1954/0.1954
  （无规约材料 → 两臂同回历史口径，一致对稀释，无偏）。

## 4. 成本

| 臂 | tokens | 调用 | 缓存命中 |
|---|---|---|---|
| s45_replace | 386,975 | 198 | 2 |
| s45_specir | 651,821 | 236 | 5 |
| s46_replace | 361,512 | 186 | 0 |
| s46_specir | 623,616 | 220 | 3 |
| **合计** | **2,023,924** | **840** | **10** |

墙钟 46m45s（串行链，并行度 2）。按 deepseek-flash 计价 ≈ $0.6。

## 5. 文件清单

- `chain.log`：四臂串行跑批完整日志
- `s45_replace/`、`s45_specir/`、`s46_replace/`、`s46_specir/`：批次工件
  （benchmark_synthetic_*.json + raw/ + traces/）
- `CONFIRM_REPORT.md` / `CONFIRM_REPORT.json`：预注册分析报告
- `SHA256SUMS`：工件完整性校验（`shasum -a 256 -c SHA256SUMS`）
