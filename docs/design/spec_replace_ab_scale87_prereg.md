# spec_replace A/B 扩样实跑预注册（87 gold 任务）

日期：2026-10-12
模型：deepseek-flash（.env.local LLM_1_API_KEY / LLM_1_BASE_URL）
口径：单种子 42，parallel=4，deterministic 未开启（TEMP 默认），
DETECTION_SPEC_MODE 进程级（off / replace），--save-state 全环节落盘

## 1. 背景

首跑（SPEC_REPLACE_AB_REPORT_2026-10-12.md）在 QuixBugs 41 gold 任务上
做了三臂探索性筛查：B vs A δ=+8.1pp / p=0.7500 不显著。报告 §5 建议
"扩样前应先修复 spec_oracle_injected provenance 字段回填，使 replace 臂
'是否真正注入了规约文档'可逐任务审计"。

本批次已落地前置动作：
- P0-A-2 增设独立观测字段 `spec_replace_applied`（commit e1ee10c）：
  - `attempted_replaced` = 规约材料非空，规约文档实际替换了目标代码块注入
  - `attempted_fallback` = 规约材料为空，渲染返回空串，prompt 保持历史口径
  - `None` = DETECTION_SPEC_MODE=off / minimal 消融档 / 节点未运行
- ULT M1 判分归一化（本批次 dataset_ult.py 改动）：ULT 官方测试材料
  （裸断言片段 test_list）包装为 pytest 函数（`from <mod> import <fn>` +
  `test_<i>`），_m1_metrics 可直接判分；fixed = 被测函数全文（ULT 无缺陷
  基线，三段判定 fixed 侧 = 原码）。

## 2. 实验设计

### 2.1 数据集

- **QuixBugs 41 gold 任务**（有 buggy/fixed/gold test 三段材料，
  detection/repair/false_fix 可测）；
- **ULT_Lite 46 任务**（官方 200 任务子集，固定 seed=42 随机抽 46 个；
  每个任务携带 5 条官方断言 → total_test_count=5，gold 材料齐备）；
- **合计 87 任务**。

注：ULT_Lite 46 任务的"gold"指官方测试材料齐备（no_gold_tests=False），
但 ULT 无 buggy 版本（被测函数即"无缺陷"基线），detection_rate 恒 0.0
（无缺陷可检出，对应 ULT 官方"green_on_fut"辅助口径；mutation score
仍为主指标，见 metadata["mutation_primary_metric"]）。ULT 任务的主要
观测价值是：
1. `spec_replace_applied` 在真实复杂函数上的逐任务可审计性
   （首跑 0/50 为 None，因 spec_oracle_injected 从未在 replace 臂回填）；
2. 三臂间 detection_rate 行为差异（QuixBugs 可配对，ULT 仅描述性）。

### 2.2 臂

- **A** = aitester（vanilla），DETECTION_SPEC_MODE=off
- **B** = aitester + 规格替换，DETECTION_SPEC_MODE=replace
- **C** = plain_llm_df（检出优先提示协议，纯净 vanilla 模式）

### 2.3 判据（预注册）

1. **QuixBugs 41 gold 配对检验**（主判据）：
   - McNemar / binom 精确检验 B vs A、C vs A、C vs B；
   - 显著判据：p<0.05 且 δ≥+8pp；
   - 功效预警：n=41 可检出 δ≈15pp（80% 功效）——同首跑口径，
     本批次 QuixBugs 仍为**探索性/阴性筛查**，非确认性。
2. **ULT_Lite 46 任务描述性观测**：
   - 三臂 `spec_replace_applied` 分布（B 臂应 100% attempted_replaced
     或 attempted_fallback，A/C 臂应 100% None）；
   - B 臂 vs A 臂 detection_rate（恒 0.0 基线，仅观测 harness 健康度：
     M1 三段判定是否因 replace 改变生成测试结构而产生 None/异常）；
   - 无统计检验（detection 不可测，仅描述性）。
3. **总任务数 87 的统计意义**：
   - 87 是"总可测任务数"（41 QuixBugs F2P 可配对 + 46 ULT 描述性）；
   - **确认性 87 对功效要求**（δ≥+8pp @ 80% 功效）仍需 n≥87 对 F2P
     可配对任务——本批次 QuixBugs 仅 41 对，**未达到 87 对**，
     确认性结论仍需后续补样（如扩充 QuixBugs/BugsInPy gold 任务）。
   - 本批次的"87"意义：扩大机制观测面 + 覆盖真实复杂函数分布，
     而非 87 对 F2P 配对功效。

## 3. 成本估算

参考首跑（QuixBugs 50 任务 × 3 臂，aitester per_task≈11.7K token，
plain_llm_df≈1.9K token，总耗时≈24 分钟/臂）：

- QuixBugs 41 任务：aitester 臂 ≈41×11.7K×2（buggy+fixed 侧）≈958K token；
  plain_llm_df 臂 ≈41×1.9K≈78K；replace 臂与 off 臂 token 同量级；
- ULT_Lite 46 任务：ULT 函数代码更长（均值 ~793 字符），aitester 臂
  per_task 估≈15K token（复杂度高），46×15K≈690K；plain_llm_df 臂
  ≈46×2.5K≈115K；
- 总 token ≈ 3×(958+78+690+115)K ≈ 4.7M token（三臂合计）；
- 按 price_table.json deepseek-flash 峰时价（$0.3/M input，$1.2/M output，
  保守按 output 全计）：≈$5.6–$9.0（上界）；
- 耗时：三臂并行=4，估≈60–90 分钟。

## 4. 工件

- 实跑脚本：`experiments/run_spec_replace_ab_scale87.sh`（本批次新增）
- 输出目录：`/tmp/spec_ab_scale87/{quixbugs_off,quixbugs_replace}/`
  （QuixBugs 臂）+ `/tmp/spec_ab_scale87_ultfix/{ult_lite46_off,
  ult_lite46_replace}/`（ULT_Lite 46 臂，首轮 int(None) 崩溃后重跑，
  缓存命名空间 `scale87_seed42_ultfix`）
- 配对检验：内联于实跑脚本（scipy.stats.binomtest 回退口径）
- 结果报告：`SPEC_REPLACE_AB_SCALE87_REPORT_2026-10-12.md`（已产出，
  2026-10-12 实跑完成）
- 实跑结果登记（post-run）：
  - QuixBugs A(off) 65.7% / B(replace) 62.9% / C(df) 75.0%；
  - B vs A δ=−2.9pp / p=1.00（不显著，共同可测 35）；
  - C vs A δ=+8.6pp / p=0.58（不显著）；
  - C vs B δ=−11.4pp / p=0.39（不显著）；
  - ULT_Lite 46：detection 恒 0.0 基线（45/46 可测），
    B 臂 spec_replace_applied 43 replaced + 3 fallback（机制在
    cyclomatic 均值 14.87 真实函数上不变形）；
  - 首轮 ULT 46/46 全崩（int(None) TypeError）→ run_benchmark.py
    4 处防御性 `or` 兜底修复 + manifest 自检（详见报告 §4.1）；
  - 成本 ≈$7.2（低于预注册 $9.0 上界），耗时 ≈47 min（低于
    60–90 min 估算）。

## 5. 边界

- 本批次为**探索性扩样**（非确认性 87 对）；
- ULT_Lite 46 任务仅描述性观测（detection 不可测）；
- 若需确认性结论，须后续补 87 对 F2P 可配对 gold 任务（QuixBugs/BugsInPy）；
- 成本上界 $9.0，若触发 LLM 限流/超时，脚本自动降级为已采数据 + 登记缺口。
