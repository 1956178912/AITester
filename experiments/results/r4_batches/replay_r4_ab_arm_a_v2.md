# repair=0 围栏伪影存量重放报告（ADR-0021，批次 VII）

- 重放目录：`experiments/results/r4_batches/r4_ab_arm_a`（1 个批次文件）
- 臂：`aitester`
- 修正口径：normalize_patch_text 清理后整文件补丁 × gold test_cases（pytest rc==0 → correct）；
  原口径：结果行 patch_correct（历史伪影数字，未经清理执行）。

| 批次文件 | 带补丁行 | 可重放 | 修正 correct | 修正 repair_rate | 原 correct（伪影） |
|---|---|---|---|---|---|
| benchmark_synthetic_20261008_133303.json | 50 | 18 | 10 | 0.5556 | 8 |

**合计**：可重放 18 行，修正 correct = 10（修正 repair_rate = 0.5556）；原口径 correct = 8（伪影归零）；diff 形态不可重放 0 行、无 gold 材料 32 行、执行异常 0 行（不计入分母）。

> 解读：原口径 repair=0 由 patch 字段围栏残留（'python\n' 前缀）的测量伪影贡献；修正口径 = 与写盘链路同口径清理后的 gold 独立裁决。历史批次的repair / false_fix / CPR 分母应按本报告重估（ADR-0021 勘误注记）。
