# df_spec 臂 QuixBugs 双臂实验工件（2026-10-16/17 实跑，零 LLM 可复算）

> **性质**：独立评审 §6 P1 / 投稿骨架 §8 T-6 主实验执行工件。
> **预注册**（结果产出前落盘）：`docs/study/DF_SPEC_PREREG_2026-10-16.md`
> sha256=`a19a6c297fa4580b1767fc7f55f4f5b35807752c98a42cef902d4fe710716d80`
> （承诺哈希记录于跑批前入库提交 `cd514d2`；判定常量由 `experiments/emse_df_spec_analysis.py`
> 在结果产出前入库锁定）。
>
> **隔离链（单变量）**：plain_llm_df（对照）→ **+规格锚** → plain_llm_df_spec（处理）。
> 唯一变量 = prompt 中的"目标代码块"替换为预计算规格锚文档（内容寻址；
> QuixBugs 覆盖 50/50；锚表 `emse_spec_anchor_20261016/`，SHA256SUMS 锁定）。

## 1. 跑批协议（两臂同批同日、逐臂独立 cache namespace）

| 项 | 值 |
|---|---|
| 数据集 | QuixBugs，`--task-count 50 --seed 42`（= 41 缺陷程序 + 9 测试驱动） |
| 臂 A（处理） | `plain_llm_df_spec`，namespace `emse_df_spec_20261016_dfspec`，工件 `benchmark_quixbugs_20261016_232138.json` |
| 臂 B（对照） | `plain_llm_df`，namespace `emse_df_spec_20261016_df`，工件 `benchmark_quixbugs_20261017_003023.json` |
| 协议 | `AITESTER_PROFILE=logic` / `TEMPERATURE=0.0` / `LLM_THINKING_MODE=disabled` / `BENCHMARK_PARALLELISM=4` |
| 模型 | deepseek-flash（两臂同批指纹） |
| provenance | 两臂 `git_dirty=false`（干净树）；namespace 互异（本目录 `DF_SPEC_REPORT.json` 可校验） |
| 墙钟 | 臂 A 1h04m / 臂 B 1h08m（含变异后处理；沙箱 I/O 减速环境） |

复现（消耗 LLM 配额 ~$0.5 量级）：

```bash
AITESTER_PROFILE=logic TEMPERATURE=0.0 LLM_THINKING_MODE=disabled BENCHMARK_PARALLELISM=4 \
AITESTER_CACHE_NAMESPACE=<new-ns> .venv/bin/python experiments/run_main_batch.py \
  --dataset quixbugs --task-count 50 --seed 42 --baselines <arm> \
  --output-dir experiments/results/emse_df_spec_20261016 --skip-stats
```

零 LLM 复算判定：

```bash
.venv/bin/python -m experiments.emse_df_spec_analysis \
  --dfspec experiments/results/emse_df_spec_20261016/benchmark_quixbugs_20261016_232138.json \
  --df      experiments/results/emse_df_spec_20261016/benchmark_quixbugs_20261017_003023.json
```

## 2. 结果（41 缺陷程序口径；可判定子集）

| 指标 | df_spec（处理） | df（对照） |
|---|---|---|
| detection | **19/35 = 54.3%** | **28/36 = 77.8%** |
| 配对（n=35） | 仅 df_spec 检出 **1** | 仅 df 检出 **10**；共同 24 |
| δ（配对差） | **−25.7pp** | — |
| McNemar 精确 | 双向 p = **0.0117**（单向 0.9995，方向为负） | — |
| BF10 | **16.40**（支持"存在差异"、方向与 H1 相反） | — |
| MDE（80% power） | 16.57pp | — |

**预注册判定（`experiments/emse_df_spec_analysis.py` 直出，见 `DF_SPEC_REPORT.json`）**：

- C1（detection ≥ 60%）：**未达**（54.3%）；
- C2（单向 McNemar p<0.05，df_spec > df）：**未达**（方向为负，p_one=0.9995）；
- **verdict = `not_confirmed`**；失败线（<50%）未触发；
- **附带发现（双向口径）**：负方向在双向精确检验下**显著**（p=0.0117，
  1:10 全不对称），即"完全替换代码为规格锚"相对现行检出优先协议
  **显著损失检出 25.7pp**。

**机制侧信号（描述性）**：

| 项 | df_spec | df | 备注 |
|---|---|---|---|
| over_red / specific_red（41 口径） | 17 / 20 | 9 / 31 | — |
| over_red 占比 | **46.0%** | **22.5%** | 预注册预期"下降 ≥30%"；**实测上升 104%（方向相反）** |
| `spec_replace_applied` | **50/50 `attempted_replaced`** | 50/50 null（非该臂） | 锚命中率 100%，仪器无故障 |

**结果解读（基于证据的机制假设，供后续预注册检验，不作定论）**：
锚材料由 Planner 对**目标代码（缺陷版）**的历史分析物化（`build_spec_anchor_table`
从既有 Planner 缓存提取 `logic_analysis`）——它描述的是**含缺陷行为**
的逻辑，而非独立的正確规格。据此类"缺陷派生描述"生成测试，预测会产生
更多"断言缺陷行为"的过红（over_red↑）与更少特异检出（detection↓）——
与实测方向一致。**因此本负结果不应读作对 Zhao et al. (ISSTA 2026)
"spec-based prompting 缓解误导航"的反证**（其设定使用独立 spec docstring），
而应读作对"**锚材料来源必须是独立正确规格、而非对缺陷代码的再描述**"
这一操作条件的警示。此为基于本实验的假设生成，须独立预注册检验。

**评审判据对照（独立评审 §6 P1）**：成功判定（detection ≥60% ∧ p<0.05 ∧
误导率 −30%）**全未满足**；失败判定（detection <50% 或 p≥0.10 或误导率无下降）
中"误导率无下降"命中（上升）——本方按预注册三态输出 `not_confirmed`。

## 3. 数据质量披露（如实）

- **沙箱 I/O 减速环境**：变异后处理（mutation_score / mutation_detection / MDO）
  出现大量 30s 超时防御（有界终止，不挂死）；`mutation_detection_rate`
  非空 19/50（臂 A）/ 30/50（臂 B）；MDO available 20/50（臂 A）/ 31/50（臂 B）——
  **主指标 detection 不受影响**（在任务阶段完成）；
- 41 口径 None：臂 A 6 任务（bitcount / find_first_in_sorted / sqrt / wrap
  （= 已知"缺陷实现不终止"家族）+ node / to_base）；臂 B 5 任务（同族前四 + node）；
- 与 E4 历史 df 数据（31/37=83.8%）的参照对比：**检出集合基本为子集关系**
  （df_spec vs E4 df：35 共同可判定中 df_spec 独有 0、E4 df 独有 11）；
  同批 df 对照（本目录）为**主配对**，E4 仅参照（模型版本/环境隔离考虑）。

## 4. 文件

| 文件 | 说明 |
|---|---|
| `benchmark_quixbugs_20261016_232138.json` | 臂 A（df_spec）批次（50 任务逐行 details） |
| `benchmark_quixbugs_20261017_003023.json` | 臂 B（df）批次 |
| `DF_SPEC_REPORT.json` | 预注册判定输出（分析脚本直出） |
| `traces/` | 逐任务 trace（臂 A/B 追加式） |
| `SHA256SUMS` | 完整性校验 |
