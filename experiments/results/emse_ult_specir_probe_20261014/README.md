# EMSE ULT SpecExpr 探针（2026-10-14，25 任务）

> 目的：填补 BASELINE `spec_compile_rate.aitester.ult_post_grammar`（T-11 遗留
> "契约后 ULT 零实测"）。干净口径（`DETECTION_SPEC_MODE=replace +
> SPEC_IR_ENABLE + SPEC_IR_DSL_ENABLE`，无 profile），与 QuixBugs pilot /
> synthetic 确认性跑批同口径，跨数据集可此较。

## 结果

| 指标 | 值 |
|---|---|
| spec_compile_rate | **0.5626**（n=25；7/25 恒 0） |
| spec_expr_coverage | 0.6176（n=21） |
| spec_replace_applied | 21/25 replaced（回退率 0.16） |
| detection | 0/24 可测（延续 ult_lite46 的 0/45——ULT 生成测试不产红） |
| 成本 | 524,592 token / 141 调用 ≈ $0.15 |

**provenance**：profile=None、SPEC_IR_ENABLE=true、SPEC_IR_DSL_ENABLE=true、
DETECTION_SPEC_MODE=replace、cache_namespace=specexpr_ult_probe_v1（全新）、
指纹 aeb56401ca74e127… pinned、git_sha e7a0027 clean。

## 结论

ULT（真实基准）契约后 spec_compile_rate=0.5626 **≥0.35 阈值**——与 QuixBugs
0.6321（n=50）并列构成"逻辑驱动"可编译率主张的两个真实基准数据点；
synthetic 模板仅 0.3102（n=174）未达。可编译率呈**数据集分层**：受限表达式
DSL 对真实代码规约接受率良好，对合成模板子句（`unknown_name` 拒绝为主）
不足——下一优化方向 = 扩白名单/扩文法（优先 synthetic 模板场景），见 BASELINE
note 与 EMSE 报告 §6.5/§6.8。

注意：ULT 的 detection 对比仍不可用（生成测试在 ULT 上零检出，0 基线无
McNemar 判别力）——本探针只补 spec_compile_rate 机制观测，不作检测增益证据。

## 文件

- `benchmark_ult_*.json`：批次工件（25 任务 details + provenance）
- `raw/`、`traces/`：环节级状态与轨迹
- `chain.log`：跑批日志（含随后全量 pytest 尝试记录）
- `full_pytest_v2_summary.txt`：全量 pytest 复跑摘要（沙箱阻断模式复现，见下；完整 11MB 日志不留档）
- `SHA256SUMS`：完整性校验（`shasum -a 256 -c SHA256SUMS`）

## 附：全量 pytest 沙箱阻断复现

同链尾的全量 pytest（`--basetemp=.pytest_tmp_full_v2`）再次复现沙箱阻断
模式（4525 errors / 2 failed / 1309 passed）——单文件复跑全部通过
（test_z_batch.py 18/18、test_emse_specexpr_confirm.py 24/24、
test_2026_10_10_optimization_batch.py 26/26），确认错误为环境性
（sitecustomize bulk-delete 守卫 / pytest-of-root 争用），非代码回归。
BASELINE total_passed 维持推导值 5835（collected 5839），实测须提权前台。
