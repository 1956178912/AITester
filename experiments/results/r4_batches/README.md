# R4 / QuixBugs 批次工件入库（R14，2026-10-08 R2）

> 本目录为 2026-10-08（及 10-07 晚）R4 局部编辑通道 A/B 与 QuixBugs 并行复跑的
> **存量工件入库**。入库前的原始工件位于 `/tmp`（易失、未入库、无 SHA256SUMS），
> 违反预注册"全部工件入 git 白名单"条款（R2 §1.3 / §6.6 治理缺口）。本目录为其
> 归档副本，SHA256SUMS 覆盖全部 306 个文件（6 批次 JSON + 300 逐任务 trace）。

## 批次清单与 provenance

| 目录 | 批次 JSON | 数据集 | 臂 | seed | profile | git_sha | git_dirty | 模型 |
|------|-----------|--------|----|------|---------|---------|-----------|------|
| `r4_ab_arm_a/` | `benchmark_synthetic_20261008_133303.json` | synthetic | aitester | 42 | logic | `9823be5f` | **True** | deepseek-flash |
| `r4_ab_arm_b/` | `benchmark_synthetic_20261008_134156.json` | synthetic | aitester | 42 | logic | `9823be5f` | **True** | deepseek-flash |
| `r4_synth_arm_b2/` | `benchmark_synthetic_20261008_161508.json` | synthetic | aitester | 42 | logic | `8c1ce276` | False | deepseek-flash |
| `r4_qb_arm_a/` | `benchmark_quixbugs_20261008_165558.json` | quixbugs | aitester | 42 | logic | `8c1ce276` | False | deepseek-flash |
| `r4_qb_arm_b/` | `benchmark_quixbugs_20261008_165603.json` | quixbugs | aitester | 42 | logic | `8c1ce276` | False | deepseek-flash |
| `loc_test_quix/` | `benchmark_quixbugs_20261007_195728.json` | quixbugs | aitester | 42 | （默认档） | `0355f514` | **True** | deepseek-flash |

**约束与来源说明（诚实披露）**

1. **synthetic 两臂（r4_ab_arm_a / r4_ab_arm_b / loc_test_quix）系 dirty 树跑批**：
   provenance `git_dirty=True`，属"预注册外"的调试/迭代跑批（R4 通道原型验证
   阶段），**非**预注册正式执行批次——不得作为对外主结论证据，仅作通道机制
   与测量层诊断的观测依据。r4_ab_arm_a/b 的 `--allow-dirty` 豁免当时未登记
   原因（`dirty_reason` 字段为 R15 新增，此前不存在）；此处归档时如实标注。
2. **QuixBugs 两臂（r4_qb_arm_a / r4_qb_arm_b）为干净树跑批**（`git_dirty=False`，
   `git_sha=8c1ce276`），是 R4 局部编辑通道在真实多函数基准上的 A/B 复跑。
   二者系 **R4 A/B 的并行副产品**，为单臂 aitester、n=50、无统计报告——
   **不构成"E4 正式执行"**（E4 预注册设计为 3 臂 × logic 档；见
   `docs/preregistration.md` 执行记录表）。
3. 全部批次为单臂（仅 `aitester`）；`r4_synth_arm_b2` 为行级约束 B2 臂，
   `r4_ab_arm_a` 为函数级对照 A 臂，`r4_ab_arm_b` 为函数级处理 B 臂。
4. 数据集：synthetic（50 模板 seed=42）/ QuixBugs（n=50，其中 41 有官方 gold
   测试、9 无——按 M1 口径不进分母）；模型 deepseek-flash；
   `TEMPERATURE=0`、`--max-pattern-repeat 2`。

## 复算命令（零 LLM，存量为准）

```bash
# QuixBugs 两臂 repair 重放（包结构口径，_m1_metrics 修复后）
.venv/bin/python -m experiments.repair_replay \
  experiments/results/r4_batches/r4_qb_arm_a --arm aitester
.venv/bin/python -m experiments.repair_replay \
  experiments/results/r4_batches/r4_qb_arm_b --arm aitester

# 跨文件任务口径修正后的存量重放（R27；含跨文件伴生模块物化）
.venv/bin/python -m experiments.corrected_metrics \
  experiments/results/r4_batches/r4_ab_arm_a --arm aitester
```

## 完整性校验

```bash
cd experiments/results/r4_batches && shasum -a 256 -c SHA256SUMS
```

## 引用纪律

对外引用本目录任意数字时，**必须同时注明口径**（分子/分母/oracle/数据集/臂/
种子/开关/工件路径）——见 `docs/design/repair_caliber_matrix.md`。
