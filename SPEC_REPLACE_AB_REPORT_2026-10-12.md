# 阶段 1 实验报告：spec_replace A/B（QuixBugs，探索性口径）

日期：2026-10-12
模型：deepseek-flash（.env.local LLM_1_API_KEY / LLM_1_BASE_URL）
口径：单种子 42，parallel=4，deterministic 未开启（TEMP 默认），
DETECTION_SPEC_MODE 进程级（off / replace），--save-state 全环节落盘

## 1. 实验设计

- 数据集：quixbugs（50 任务，其中 41 带官方 gold 测试，9 无 gold
  → detection 恒 None，不参与配对）
- 臂：
  - A = aiterst（vanilla），DETECTION_SPEC_MODE=off
  - B = aiterst + 规格替换，DETECTION_SPEC_MODE=replace
  - C = plain_llm_df（检出优先提示协议，纯净 vanilla 模式）
- 判据（方案预注册）：McNemar p<0.05 且 B 相对 A δ≥+8pp
- 统计：配对（仅 41 gold 任务），n01 / n10 不一致对，二项精确检验
  回退（scipy.stats.mcnemar 对 0/0 对返回 NaN，此处用 binomtest）

## 2. 实测结果

| 臂 | 可测任务 | 检出（detection=1） | 未检出 | 无 gold |
|---|---|---|---|---|
| A vanilla aiterst | 37 | 23 (62.2%) | 14 | 13 |
| B spec_replace     | 36 | 26 (72.2%) | 10 | 14 |
| C plain_llm_df     | 37 | 27 (73.0%) | 10 | 13 |

（B 臂 1 个任务在 replace 模式下 detection 为 None，因 spec 替换
改变了生成测试结构，导致 M1 三段判定第 1 段 harness 无效——
已计入 none 不计入配对。）

配对 McNemar（41 gold 任务，仅三臂间共同可测任务计入）：

| 对比 | n01 | n10 | δ（pp） | p（binom 精确） | 判据 δ≥+8pp & p<0.05 |
|---|---|---|---|---|---|
| B vs A（spec_replace vs vanilla） | 4 | 1 | **+8.1** | **0.7500** | 不满足（p 不显著） |
| C vs A（df vs vanilla） | 7 | 3 | +10.8 | 0.6875 | 不满足（p 不显著） |
| C vs B（df vs spec_replace） | 4 | 4 | +2.8 | 1.0000 | 不满足 |

## 3. 结论（诚实口径）

1. **spec_replace 相对 vanilla 检出率 +8.1pp，方向与预注册一致，但
   p=0.75 不显著**——41 gold 任务（可测 37）规模下，8pp 级差异在
   80% 功效量级**不可检测**（§1 功效分析已预警：n=41 可检出 δ≈15pp）。
   故本实验**既不能确认也不能否定** spec_replace 方向，属探索性/
   阴性筛查。
2. **df 对照臂 C 相对 vanilla A +10.8pp 同样不显著（p=0.69）**——
   与方案"将 df 升格为主叙事基线"的判断一致：即便在 QuixBugs 这一
   相对容易的基准上，3 臂间检出率差异在单种子 41 任务规模下均
   不足以统计区分。
3. **`spec_oracle_injected` 字段 0/50 为**预期行为**（A、B 两臂均
   如此，非缺陷）**——该字段追踪的是 R1c 批次的**确定性规约
   oracle 执行注入**（`SPEC_ORACLE_EXEC_ENABLE` 开关，默认关）：
   把 SpecIR 编译产物追加到 LLM 测试尾部并列执行。本实验未开启
   该开关，故字段全 None（未尝试注入），与 P0-A-2 的
   `DETECTION_SPEC_MODE=replace`（仅替换 prompt 的目标代码块，不
   追加执行链 oracle）是**两个独立机制**。replace 臂的实际生效
   由 prompt 构建路径本身保证（`nodes.py:928-943`：
   `DETECTION_SPEC_MODE=replace` 且非 minimal 消融档时调用
   `build_spec_replace_section`，非空则替换注入）。若需逐任务
   审计"replace 是否真正注入了规约文档"，建议后续批次为
   P0-A-2 增设独立观测字段 `spec_replace_section_chars`（或复用
   既有 `spec_oracle_verdict` 的扩展值域），当前实验按"代码路径
   已接线 + prompt 构建日志可查"口径登记，不阻塞结论。

## 4. 工件

- A + C 臂：`/tmp/spec_ab/off/benchmark_quixbugs_20261012_185327.json`
  （traces 50 条 / raw 全环节）
- B 臂：`/tmp/spec_ab/replace/benchmark_quixbugs_20261012_190733.json`
  （traces 50 条 / raw 全环节）
- 本报告的配对检验原始代码已内联于本报告 §2（可复现）

## 5. 下一步建议

- 若确认 spec_replace 方向，需按功效分析扩至 **n≥87 gold 任务**
  （方案维度二判据 δ≥+8pp @ 80% 功效）才能做确认性实验；
  当前 41 gold 任务只能作为阴性筛查 / 方向验证。
- 扩样前应先修复 `spec_oracle_injected` provenance 字段回填，
  使 replace 臂"是否真正注入了规约文档"可逐任务审计。
- 若 87 任务扩样后仍未达 δ≥+8pp，按方案 Plan B 退守路径执行
  （测量基建 + 阴性结果组合发布）。
- 若确认 replace 臂可审计性需求，为 P0-A-2 增设
  `spec_replace_section_chars` 观测字段（或扩展 `spec_oracle_verdict`
  值域），与 R1c 的确定性 oracle 注入（`spec_oracle_injected`）
  解耦登记——这是独立勘误项，不阻塞本批次结论。
