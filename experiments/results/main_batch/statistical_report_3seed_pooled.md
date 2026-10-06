# R-P0-2 生死实验：三种子合并统计报告（2026-10-06）

## 实验口径（预注册 R-P0-2）

- 强模型：`deepseek-flash @ api.deepseek.com`（`.env.local` LLM_1，配额探测 live）
- 数据集：synthetic n=87 × 3 种子 {42, 43, 44} × `--max-pattern-repeat 2`（R-P0-4）
- 三臂：`aitester` / `plain_llm` / `plain_llm_df`（检出优先协议归因基线，X1）
- 配置：`AITESTER_PROFILE=logic`（R-P0-3 主配置）× `TEMPERATURE=0.0`（确定性协议）× `BENCHMARK_PARALLELISM=4`
- 缓存：默认开 + 自动命名空间 `seed<N>`（跨种子隔离，首跑无命中）
- 工作树：b533cff，跑批时含未提交改动（三批次 provenance 实测
  `git_dirty=true`，`--allow-dirty` 口径；勘误见文末"AK 勘误"节）
- 总耗时 3.8h；总 tokens ≈ 8.76M

批次工件：
- `benchmark_synthetic_20261006_140906.json`（seed 42）
- `benchmark_synthetic_20261006_151907.json`（seed 43）
- `benchmark_synthetic_20261006_164357.json`（seed 44）

## 方法学说明（与 canonical `statistical_report.md` 的差异）

canonical R14 报告的 `_pair_by_task` 去重口径为"同 task_id 最新批次优先"
（为重复跑设计）。多种子实验中 task_id 跨种子同名是设计使然（中性化命名），
该去重会把 3 种子折叠为 1 种子（261 行进概览、配对只剩 seed 44 的 87 对）。
本报告按**种子分层拼接**（task_id 加 `s<seed>__` 前缀）后复用规范实现
（`mcnemar_test` / `bayesian_paired_analysis` / `bh_fdr_correct`），
261 对全量进入检验，单元格口径与规范逐位一致。

复算命令：`.venv/bin/python /tmp/pooled_3seed_analysis.py`
（拼接逻辑：`{**row, "task_id": f"s{seed}__{row['task_id']}"}` 后按对比调用规范函数）

## 数据概览（3 种子合计，n=261 任务/臂）

| 臂 | detection 阳性/可测 | detection 率 | passed | passed 率 | tokens/任务 | LLM 调用/任务 |
|----|----|----|----|----|----|----|
| aitester | 38/240 | 15.8% | 143 | 54.8% | 26,115 | 4.24 |
| plain_llm | 4/261 | 1.5% | 229 | 87.7% | 3,209 | 1.13 |
| plain_llm_df | 117/261 | 44.8% | 7 | 2.7% | 4,223 | 0.97 |

注：passed 为自指指标（自产测试在未修复缺陷代码上通过）——plain_llm 的
87.7% "通过率"与其 1.5% 检出率并存，再次实证自指口径的误导性。

## 首要结论：detection 配对差（F2P 检出，gold 独立裁决，McNemar + 贝叶斯 Dirichlet）

| 对比 | 不一致对（A检B未检 / 反向） | McNemar χ² | p | BH-FDR q | δ 后验均值 | 95% CI | P(δ>0) | 结论 |
|------|----|----|----|----|----|----|----|----|
| plain_llm_df vs plain_llm | 113 / 0 | 111.01 | ≈0 | 6.0e-08 | **+0.426** | [+0.367, +0.487] | 1.0000 | 检出优先提示协议 +43pp，决定性阳性 |
| aitester vs plain_llm | 37 / 3 | 27.23 | 1.8e-07 | 1.8e-07 | **+0.139** | [+0.092, +0.190] | 1.0000 | 完整系统优于裸 LLM +14pp |
| aitester vs plain_llm_df | 12 / 80 | 48.79 | 2.8e-12 | 1.2e-07 | **−0.279** | [−0.348, −0.209] | 0.0000 | **完整系统显著劣于纯提示协议 −28pp** |

（aitester vs plain_llm_df 单元格以 δ 方向为准；aitester 的 None detection 行
（21/261，M10 强校验拒绝或无 gold 材料/补丁校验失败）按 M1 口径不进分母，
共同任务 240。）

## 逐种子一致性（aitester vs plain_llm，detection McNemar）

| seed | 共同任务 | 不一致对 | χ² | p |
|------|----|----|----|----|
| 42 | 81 | 13 | 7.69 | 0.0055 ** |
| 43 | 79 | 16 | 10.56 | 0.0012 ** |
| 44 | 80 | 11 | 5.82 | 0.0159 * |

三种子方向一致、逐一显著——编排效应（aitester > plain_llm）稳健。

## repair（gold 裁决修复）

三组对比不一致对均为 0（repair 全线 0.000）——修复主张继续无证据，
与历史口径一致。

## 状态分布（aitester，detection_first_status）

| seed | red_not_repaired | red_then_green | all_green_unverified | None |
|------|----|----|----|----|
| 42 | 40 | 18 | 23 | 6 |
| 43 | 27 | 22 | 30 | 8 |
| 44 | 30 | 17 | 33 | 7 |

## 结论与定位

1. **检出收益主要来自检出优先提示协议本身**（+43pp vs 裸 LLM），而非
   多智能体编排或规约链：完整系统不仅未在协议之上叠加增益，反而显著
   低于纯提示协议 28pp——强模型下编排管线对检出构成**净负贡献**
   （第九轮红队预警 H2"plain_llm 追平"的最强形式）。
2. 编排效应仍真实存在（+14pp，三种子一致显著）：aitester 优于裸 LLM，
   但其代价是 8.1× token（26.1k vs 3.2k/任务）。
3. 修复主张（repair）在强模型 + logic 档下仍为 0，"自修复"主张继续
   无实验支持。
4. 论文定位应按第九轮三点式框架的 B/C 轴落笔：归因方法学（配对基线 +
   诚实指标 + 贝叶斯配对）与本阴性/归因结果本身是可发表贡献；主张 A
   按当前证据应收缩为"检出优先提示协议 +43pp"（提示工程贡献），
   而非"多智能体/规约链贡献"。

## 已知口径缺口（遗留待办）

- `spec_compile_rate` 无行级字段（R-P0-5"全指标开启"待办）：logic 档
  开关注入已实证（env_snapshot SPEC_IR_ENABLE=true），但 spec 链指标
  未接线到结果行，本轮无法评估规约 oracle 的独立贡献。
- provenance 无 profile 字段（AITESTER_PROFILE 生效证据在 env_snapshot
  内，建议后续显式记录）。
- aitester 21/261 行 detection=None（根因已定位：21 行全部为 M10
  `LOGIC_SPEC_STRICT_ENABLE` 强校验拒绝——Planner 第 0 轮 raise，
  error_category='error'；AB 批次已加 `LOGIC_SPEC_STRICT_FALLBACK_ENABLE`
  降级出口，logic 档预设注入 true，后续批次不再整任务死亡）。
- 交叉分析补充：88 行 red_not_repaired 但 detection=0（过红测试——
  buggy 红 fixed 也红，F2P 三段判定不通过，非缺陷特异）；28 行
  red_then_green 但 detection=0（修复循环使最终测试在 buggy 上变绿，
  检出能力被抹掉）——完整系统 −28pp 的两条机制主通道。

## 模板聚类稳健敏感性分析（AC4，T-P0-5，2026-10-06 追加）

多种子拼接口径下同模板任务跨种子为相关观测（50 模板簇 vs 261 观测/臂），
逐对 McNemar 的独立性假设名义偏乐观。本节以设计效应校正（DEFF =
1+(m̄−1)·ICC，ICC 为按模板簇的单因素随机效应估计）+ 模板级配对符号
检验（每模板臂内 detection 均值逐一比较，精确二项 p）做敏感性检验：

| 对比 | 逐对 χ²（discordant） | 模板簇结构 | 保守 χ²_adj | 模板级胜负 | 符号检验 p |
|------|------|------|------|------|------|
| plain_llm_df vs plain_llm | 113.00（113:0） | k=31，m̄=16.84，ICC=0.153，DEFF=3.42，n_eff=152.7/522 | **33.06** | 22:0（平 9） | **4.8e-07** |
| aitester vs plain_llm | 28.90（37:3） | k=31，m̄=16.16，ICC=0.230，DEFF=4.49，n_eff=111.6/501 | **6.44** | 13:1（平 17） | **0.0018** |
| aitester vs plain_llm_df | 50.26（12:80） | k=31，m̄=16.16，ICC=0.299，DEFF=5.53，n_eff=90.5/501 | **9.08** | 5:17（平 9） | **0.0169** |

**结论：三组对比在聚类校正后方向与显著性全部保持**（df +43pp 协议效应
最稳健；aitester −28pp 劣势在模板级 5:17 仍显著 p=0.017；aitester +14pp
编排效应校正后最弱 χ²_adj=6.44/p≈0.011、符号检验 13:1 仍显著）——正文
三项结论对观测相关性稳健。复算命令：

```bash
.venv/bin/python experiments/statistical_analysis.py \
  --results-dir experiments/results/main_batch --cluster-by-template \
  --batches benchmark_synthetic_20261006_140906.json,benchmark_synthetic_20261006_151907.json,benchmark_synthetic_20261006_164357.json
```

（附注：canonical `statistical_report.md` 自 AC4 起 plain_llm_df 升为
统计加载一等基线，三臂对比不再依赖本文件的仓外拼接脚本；aitester vs
plain_llm_df χ²=48.7935 与本文件第三节逐位一致。）

## AK 勘误与敏感性双界（2026-10-06 追加，离线零 LLM 成本）

**勘误 1（provenance 表述错误）**：本文"实验口径"节原表述"工作树：
干净 @ b533cff（provenance git_dirty=False 三文件一致）"**与工件不符**——
三个批次 JSON 的 provenance 字段实测均为 `git_dirty: true`（跑批时
工作树含未提交改动，`--allow-dirty` 口径；sha 一致但代码态不可由
sha 单独复现）。已就地更正；审计链以批次 JSON provenance 字段为准。
本文及三批次工件此前未入 git（preregistration.md 时间顺序审计条款
的执行前提），AK 批次起随 `scripts/check_artifacts_tracked.py`
CI 守卫强制入库。

**勘误 2（21 行 detection=None 差异性缺失双界）**：正文第三节按 M1
口径剔除 aitester 的 21 行 None（共同任务 240）。最好/最坏双界填充
（None→1 / None→0）后重算配对差与 McNemar（同加载器、同检验实现）：

| 对比 | 情形 | 共同任务 | 配对差 | McNemar χ² | p |
|------|------|----|----|----|----|
| aitester vs plain_llm | 原口径（None 跳过） | 240 | +0.142 | 27.23 | 1.8e-07 |
| aitester vs plain_llm | 最坏（None→0） | 261 | +0.130 | 27.23 | 1.8e-07 |
| aitester vs plain_llm | 最好（None→1） | 261 | +0.211 | 47.80 | 4.7e-12 |
| aitester vs plain_llm_df | 原口径（None 跳过） | 240 | −0.329 | 48.79 | 2.8e-12 |
| aitester vs plain_llm_df | 最坏（None→0） | 261 | −0.303 | 59.07 | 1.5e-14 |
| aitester vs plain_llm_df | 最好（None→1） | 261 | −0.222 | 31.85 | 1.7e-08 |

**双界下两条定性结论均保持**：+14pp 编排正向效应最坏仍 +13.0pp
且显著；−28pp 协议劣势最好仍 −22.2pp 且显著（p=1.7e-08）。差异性
缺失（恰为第 0 轮 M10 死亡任务，方向不可知）不改变任何正文结论。

**补充（修复上限归因）**：`repair_ceiling_report.md`（AK1，同参口径）
分解 repair=0 漏斗：修复循环进入 154/261 → patch 产出 145（94.2%）
→ plausible 72（46.8%）→ correct 0——修复上限受制于补丁合理性/
证据门与 gold 正确性，而非补丁未产出；patch_evidence_level=none
占 48.1%、stop_reason=skip_debugger_repair_invalid 占 50.0%。该表
为 E7（修复上限诊断）的分层抽样框。
