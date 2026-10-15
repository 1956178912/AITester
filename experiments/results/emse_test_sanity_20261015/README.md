# 生成测试 / 官方测试健全性审计（2026-10-15 批次八）

> **用途**：全量 Mut@k 跑批的健全性前置门依据 + 稿件披露节证据。
> 判定：测试在**正确代码**（task_metadata.fixed）上 30s 内运行，
> rc=0 → pass；rc≠0 → fail；超时 → nonterminate。
> 口径：pass 集合 = Mut@k 可测任务（fail/nonterminate 的击杀为
> 恒红/超时驱动的平凡信号，不可归因于变异敏感性）。

| 任务集 | 测试 | pass | fail | nonterminate | material_missing | 合计 |
|---|---|---|---|---|---|---|
| quixbugs50 | generated | 30 | 17 | 3 | 0 | 50 |
| ult_lite46 | generated | 9 | 36 | 1 | 0 | 46 |
| ult_lite46 | gold | 0 | 46 | 0 | 0 | 46 |
| ult_probe25 | generated | 5 | 19 | 1 | 0 | 25 |
| ult_probe25 | gold | 0 | 25 | 0 | 0 | 25 |

## 明细

见 `SANITY_AUDIT.json`（逐任务 status/rc/wall_s/失败摘要 tail）。

## 附注（批次八）

1. **gold 失败为上游数据属性**：ULT 两个子集的官方 `test_list` 在
   `fixed` 上 100% 失败（71/71），已排除包装/物化因素（官方物化风格
   复测抽样仍全败；`fixed` 与上游 `ULT_Lite.jsonl` 的 `code` 逐字节一致）
   ⇒ 归档"gold 上界 1.0"系恒红套件的平凡击杀伪影。
2. **官方前置块影响已量化**：以官方 `code_import` 前置块复测 77 个
   gen-fail 案例，仅 1 例翻转（`ult_probe25 ult__fix_labels`，1.3%）
   ——主表口径（无前置块）保持有效。明细：
   `PRELUDE_IMPACT_20261015.json`。
3. 非终止判定用 30s 界限（保守）；`windows_k_distinct`（k=-1 死循环）、
   `bitcount`/`sqrt`/`wrap` 为真死循环样本。

## 复现

```bash
# 零 LLM：只读归档批次工件 + 本地 pytest 判定
python experiments/emse_test_sanity_audit.py
```
