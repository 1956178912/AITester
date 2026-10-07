# 预注册：E1–E4 验证实验（检出优先协议 + 逻辑链 + 双门）

最后更新: 2026-10-07（AO 批：E6 matched 上限来源修订——改取 E2 实测
均值，R-P0-2 旧常数降为量级参照，修订早于任何 E6 数据；此前同日
AN2/AN5 呈现性增补入 E3 节——主终点/阈值/停止规则不变；2026-10-06
AM 批：E6 执行前置达成声明 + 执行记录表 E6/E7 行 + E6 就绪命令块）

## 目的与效力范围

本文档在 E1/E2 任一复跑**启动前**固化假设、主终点、预注册阈值、停止规则与
统计分析计划（第十一轮审查 N4；此前预注册内容散落于 ADR-0016 与
`statistical_report_3seed_pooled.md`，无独立可引用工件）。

效力范围：E1（契约冒烟）/ E2（双门复核）/ E3（全指标，并入 E2）/
E4（真实基准首跑）/ E6（预算匹配四臂）/ E7（修复上限分层抽样）。
E6/E7 由 AL 批次（2026-10-06）增补——增补时点早于任何 E6/E7 数据
产生（E7 抽样脚本尚未对真实工件运行、E6 无任何批次）。E5（模型
梯度）为**探索性**，不受本文档约束，结果呈现时须标注。

## 既有结果的诚实声明（防"事后预注册"质疑）

- R-P0-2 生死实验已于 2026-10-06 完成并入库：plain_llm_df +43pp vs
  plain_llm、aitester +14pp vs plain_llm、**aitester −28pp vs
  plain_llm_df**、repair 全线 0（`statistical_report_3seed_pooled.md`，
  261 对，聚类校正后全稳健）。
- AB1 12 任务验证批已完成于契约修复**之前**（spec_compile_rate 全 0）。
- 因此 E1/E2 属**复核（replication）性质**：判定阈值在本文件落盘时固定，
  但实验方向的先验知识已存在——任何解读不得声称双盲预测。
- 时间顺序审计：本文件的入库 commit 必须早于 E1/E2 复跑批次工件的入库
  commit（git 历史可核）。

## E1：规约契约修复冒烟（AC1 验收）

- **假设 H1**：`SPEC_EXPR_CONTRACT_SECTION` 注入后，Planner 按
  `{"desc": NL, "expr": DSL}` 双通道产出可过 spec_ir_v2 编译器的规约子句
  （修复前实测一切真实运行 spec_compile_rate = 0.0——prompt 中文 NL vs
  `_EXPR_TOKEN_RE` ASCII 白名单契约断裂）。
- **设计**：ab1_validation 同 12 任务（synthetic seed=42 前 12 任务），
  `AITESTER_PROFILE=logic`，`TEMPERATURE=0`，缓存命名空间 seed42。
- **主终点**：spec_compile_rate（expr 通道；行级字段 AB3 已透出）。
- **预注册判定**：
  - ≥ 0.3 → 契约修复有效，"逻辑驱动"主张保留，进入 E2；
  - < 0.2 → 按 ADR-0016 预写阈值**放弃逻辑驱动主张**（后续转向 LLM
    属性模板路线，另行立项，不在本文件范围）；
  - [0.2, 0.3) 灰区 → 允许**恰好一次** prompt 契约迭代后重跑一次
    （迭代前后工件均入库），仍 < 0.3 按放弃处理。
- **次要终点**：spec_expr_coverage 非空率 = 100%（透出通道健全性）。
- **预算**：≈ 0.1M token。

## E2：双门复核（AC2 验收，E3 并入同批）

- **假设**：
  - H2a：特异性门使"过红测试"通道（buggy 红 ∧ fixed 也红——非缺陷特异，
    空耗修复循环）行数归零；
  - H2b：红回归门使"抹红"通道（red_then_green 但最终测试在 buggy 上
    变绿——检出证据被修复循环销毁）行数归零；
  - H2c：双门后 aitester vs plain_llm_df 的 detection 配对差收敛
    （|δ| 后验 95% CI 含 0）或反超。
- **设计**：synthetic n=87 × 3 臂 {aitester, plain_llm, plain_llm_df} ×
  2 种子 {42, 44} × `AITESTER_PROFILE=logic` × 双门开
  （`DETECTION_SPECIFICITY_GATE_ENABLE` / `RED_REGRESSION_GATE_ENABLE`，
  logic 档自动注入）× `ENABLE_MUTATION_SCORING=true`（E3 并入）×
  `TEMPERATURE=0` × `--max-pattern-repeat 2` × `--pool-seeds`。
  AI1（2026-10-06）补齐 logic 档 `FL_SPECTRAL_ENABLE` 注入——E2 批次
  将首次产出 fl_at_k 数据（此前全部 logic 档批次恒空，0/87 实证）。
- **主终点**：
  1. 过红/抹红通道行数（判定口径 = 合并报告"已知口径缺口"节实测方法：
     red_not_repaired ∧ detection=0 为过红候选；red_then_green ∧
     detection=0 为抹红候选）；
  2. aitester vs plain_llm_df 的 detection 配对差（McNemar + 贝叶斯）。
- **预注册判定**：
  - 两通道行数均 = 0 → H2a/H2b 成立；
  - aitester vs df：δ 后验 95% CI 含 0 或 δ > 0 → 编排净负贡献撤销
    （ADR-0016"负面/风险"条款解除）；仍显著为负 → "编排容器在检出
    口径下结构性劣后"结论升级（ADR-0016 预写，同样可发表）。
- **停止规则**：任一通道行数未归零但相对基线（88 行过红 / 28 行抹红）
  降幅 ≥ 50% → 允许**恰好一次**门参数/路由修正后重跑一次；降幅 < 50%
  → 直接接受结果，不再迭代（防门参数搜索过拟合基准）。
- **次要终点**：repair 是否破零；E3 全指标行级非空率（见下节）。
- **预算**：≈ 3–6M token（AD 批 `LLM_THINKING_MODE=disabled` 口径）。

## E3：全指标开启（并入 E2 同批）

- 要求：mutation_detection_rate / fl_at_k / patch_precision /
  spec_compile_rate / spec_expr_coverage 在全部可测行非空（None 仅允许
  "无 gold 材料"口径，且须在报告披露占比与根因——不得出现 schema
  在而运行时未开的情况）。
- AN2/AN5（2026-10-07）呈现性增补：E2 统计报告新增"测试套件可靠性"节
  （mutation_detection_rate 按臂聚合，SWE-Mutation 2026 口径对齐）与成本
  节 $/detection 推导列（$/task ÷ 检出率）——两者均为**呈现性增补**
  （已登记测量的聚合/商，非新测量），主终点、判定阈值与停止规则不变；
  增补时点早于 E2 数据产生（本文件改动的入库 commit 早于 E2 批次
  工件入库 commit，git 历史可核），防"事后呈现"质疑。

## E4：真实基准首跑（QuixBugs L1）

- **前置条件**：① QuixBugs 上游许可核实并记入 DATA_CARD（既有登记项）；
  ② 数据落 `data/`（gitignore 区，不入库）。
- **设计**：Python 子集 29 任务 × 3 臂 {aitester, plain_llm, plain_llm_df}
  × 1 种子（42）× logic 档 × 双门开。
- **主终点 / 验收线**（BASELINE 预注册口径）：任一臂 detection > 0 ∧
  resolved > 0。
- **判定**：达标 → 真实阶梯 L2（BugsInPy）立项；双方全 0 → 记阴性并
  **强制根因分析**（error_category × stop_reason 聚合）后才允许更换
  数据集——禁止静默换基准。
- **预算**：≈ 0.3M token。

## E6：预算匹配四臂（编排 vs 算力归因；AL 批次预注册，执行待预算）

- **动机（R4/AL7）**：R-P0-2 中 aitester 26,115 tok/任务 vs
  plain_llm_df 4,223 tok/任务（8.1×），−28pp 的归因存在"编排结构"与
  "预算混杂"（长循环上下文膨胀/磨损）两种解释；2026 领域成本口径
  （$/resolved 展布 $0.46–$74，六前沿模型同分位）要求归因隔离后才可
  下结构性结论。
- **设计**：2×2 四臂 = {aitester, plain_llm_df} × {standard,
  budget-matched}；synthetic n=87 × 2 种子 {42, 44} × logic 档 ×
  双门开 × `TEMPERATURE=0` × `--max-pattern-repeat 2` × `--pool-seeds`。
  - budget-matched 定义（**AO 修订，2026-10-07，早于任何 E6 数据**）：
    matched 上限一律取 **E2 同种子 standard 批次实测的每任务总 token
    均值**（行级 `token_usage.total_tokens` 按臂聚合）——df(matched) =
    df 标准臂 + 每任务上限抬至 E2 aitester 标准臂实测均值（允许更多
    再生成轮次直至预算触顶）；aitester(matched) = aitester 标准臂 +
    每任务上限压至 E2 df 标准臂实测均值。R-P0-2 的 26,115/4,223 为
    **无门控口径**，仅作量级参照、不得直接用作 cap——双门会改变
    aitester 的 token 消耗曲线（门路由减少无效修复循环），若门控后
    均值低于旧 df 均值，硬编码 cap 将不绑定，aitester(matched) 退化为
    无约束对照，等预算对比失效。
  - **修订效力声明**：本修订（AO 批次，2026-10-07）为设计增补——主
    终点、判定规则与停止规则不变，仅"matched 上限的数值来源"从
    R-P0-2 常数改为 E2 实测均值；增补时点早于任何 E6 批次数据
    （E6 零批次），git 历史可核。
  - **执行前置（AM 批次已达成，2026-10-06）**：
    `run_main_batch/run_benchmark` 已实现 `--per-task-token-caps`
    （臂=上限映射，经 `set_task_token_cap` 写入任务预算实例，超限走既有
    budget 停止路径——stop_reason=budget_exceeded，结果行
    token_budget_capped=true，provenance.per_task_token_caps 留痕）。
    注：预注册原稿写 stop_reason 记 "budget_cap"，实现复用既有枚举值
    `budget_exceeded`（语义一致，判定读该字段即可）——本行为唯一
    勘误，判定规则未改。
- **主终点**：两条"等预算"对比的 detection 配对差 δ（McNemar + 贝叶斯
  + BH-FDR）——df(matched) vs aitester(standard)、aitester(matched) vs
  df(standard)。
- **预注册判定**（显著 = |δ| 95% CI 不含 0 且 ROPE ±5pp 外）：
  - 两对均 δ≈0 → 预算混杂不成立，−28pp 归因编排结构（ADR-0016
    结论加固）；
  - df(matched) 显著升 或 aitester(matched) 显著降 → 预算混杂显著，
    −28pp 须降格表述为"等预算下未验证"；
  - 混合结果 → 按主导通道如实报告，不做二次迭代。
- **停止规则**：一次性实验，无迭代条款。
- **预算**：≈ 4M token（thinking 关口径）。

## E7：修复上限分层抽样人工复核（AL 批次预注册）

- **动机（R9/AL10）**：repair=0 的漏斗（patch 产出 94.2% → plausible
  46.8% → correct 0，`repair_ceiling_report.md`）中 correct=0 由 gold
  全等裁决得出——须排除"gold 判定过严低估 repair"的可能，"上限卡在
  合理性与正确性"才可定案。
- **设计**：抽样框 = repair_ceiling_report §1 的 patch_plausible=1 行
  （72/261）；分层键 = patch_evidence_level {none, sbfl, keyword}；每层
  抽 ceil(层行数 × 10%)（确定性 seed=42，脚本
  `experiments/repair_sample_selection.py`，输出候选行清单供人工比对）。
- **人工复核口径**：逐行将补丁与 gold diff 对照，判定 ∈ {equivalent
  （语义等价，应判 repair）, plausible_overfit, wrong_location,
  test_only, incomplete}。
- **预注册判定**：equivalent 占比 > 0 → repair 口径存在低估，
  BASELINE/pooled 报告须勘误并给出修正后 repair 上界；= 0 → "repair
  上限卡在合理性与 gold 正确性"结论定案（repair=0 为真零）。
- **成本**：人工约 1 天，零 LLM 成本（纯离线抽样 + 人工比对）。
- **候选清单（AO 批已生成，2026-10-07）**：
  `experiments/results/main_batch/e7_repair_sample_candidates.md`——
  抽样脚本已对真实工件运行（seed=42，确定性，可复算），人工复核自该
  清单逐行执行，复核完成后按上方判定规则回填执行记录表。
  **对照式复核工作表（AP 批已生成，2026-10-07）**：
  `experiments/results/main_batch/e7_review_worksheet.md`——每个候选节
  内嵌四段素材（生成补丁 / gold fixed / gold 官方测试 / 最终生成测试）
  与判定勾选栏；整文件替换口径下 patch 正文即补丁应用后完整文件，与
  gold fixed 逐行对照即可分类。复核结论仍以人工判定为准，工作表仅
  备料不裁决。

## 统计分析计划（全部实验通用）

- 检验族：McNemar（连续性校正）+ BH-FDR（α=0.05）+ 贝叶斯 Dirichlet
  配对（ROPE ±5pp，MC seed=42）+ 模板聚类 DEFF 敏感性 + 模板级符号
  检验（AC4 口径，`--cluster-by-template`）。
- 多种子拼接一律 `--pool-seeds`（AB4 口径）；分析口径以
  statistical_analysis.py 当前版本为准，分析代码与工件同批入库。
- 主终点优先呈现；次要终点标注"探索性"；**不得因结果切换主终点或
  事后增删检验**。
- 功效依据：`scripts/power_analysis.py`（基线检出 2%、检出差 10pp 需
  n≈87；E2 双门若为近确定性通道消除，复核定位以通道归零为主、效应量
  估计为辅）。

## 工件与可复现性

- 每个实验产出：批次 JSON + 全量 trace + 统计报告 + SHA256SUMS，全部
  入 git 白名单（experiments/results/main_batch/ 口径）；
- 跑批前验证 provenance `git_dirty=False`，不满足时中止并登记原因；复跑
  一律**不得**使用 `--allow-dirty`（AK 勘误补注，AL1 改写为禁止语境：
  R-P0-2 当时即在该旗标口径下跑批，provenance 瑕疵已在 pooled 报告
  "AK 勘误"节登记；报告引用工件的入库由
  `scripts/check_artifacts_tracked.py` CI 强制）；
- 复算命令逐份写进报告头（既有 R2 协议）；
- 成本口径：$/task 由 `experiments/price_table.json` 价目表驱动（AE2），
  E1/E2/E4 报告生成前补齐对应模型价目（含来源与生效日期）。AK 补注
  （2026-10-06）：deepseek-flash / qwen-long 已按官方页登记（$/task 可
  计，主模型 deepseek-flash 不受阻）；agnes-3.0-flash 无公开官方价维持
  null，使用该模型的批次须先补登记。

## 偏差控制与诚实条款

- passed 为自指指标，仅作诊断，不得作为结论依据；
- 无 gold 材料行不进分母（M1 口径）并在报告披露占比；
- 任务死亡/降级出口（error_category）计入披露，不得静默丢弃；
- 配额中断/预算超支 → 实验按"中止"记录，已完成部分可报告但不补跑凑数；
- 任何偏离本预注册的决定（含灰区迭代、停止规则触发）须在执行记录中
  留痕并追记全局决策日志。

## 执行记录（跑批后追加，不得改写判定规则）

| 实验 | 状态 | 批次工件 | 主终点结果 | 判定 | 日期 |
|------|------|----------|------------|------|------|
| E1 | 待执行 | — | — | — | — |
| E2+E3 | 待执行 | — | — | — | — |
| E4 | 待执行 | — | — | — | — |
| E6 | 待执行（前置旗标已实现，AM 批） | — | — | — | — |
| E7 | 待人工复核（候选清单已生成，AO 批） | — | — | — | — |

## 就绪命令（AH2 预置：预算批准且干净树后直接执行）

E1 契约冒烟（12 任务，≈0.1M token；`run_main_batch` 默认拒绝脏树——
干净树由工具强制，**不得**加 `--allow-dirty`，否则违反本预注册）：

```bash
AITESTER_PROFILE=logic .venv/bin/python experiments/run_main_batch.py \
  --task-count 12 --seed 42 --baselines aitester \
  --output-dir ab1_validation_e1 --skip-stats
```

结果验证（spec_compile_rate 均值对照预注册阈值：≥0.3 保留 / <0.2 放弃）：

```bash
.venv/bin/python -c "import json,glob; f=sorted(glob.glob('experiments/results/ab1_validation_e1/benchmark_*.json'))[-1]; rows=json.load(open(f))['results']['aitester']['details']; vals=[r['spec_compile_rate'] for r in rows if r.get('spec_compile_rate') is not None]; print(f, f'spec_compile_rate mean={sum(vals)/len(vals):.3f} (n={len(vals)}/{len(rows)})')"
```

E4 前置状态（AH1 更新）：QuixBugs 上游许可已核实为 MIT（GitHub API，
2026-10-06）——前置条件①解除；数据获取后随 E4 工件登记 commit。
BugsInPy（L2）无 SPDX 许可证，见 DATA_CARD §4 决策门槛，不在 E4 范围。

### E4 就绪命令（AJ 批补：数据已取，2026-10-06）

数据前置已完成：`data/quixbugs` 已克隆（**commit
`4257f44b0ff1181dedaedee6a447e133219fcebf`**，gitignore 区不入库，
溯源已登记 DATA_CARD §4）。零 LLM 加载器冒烟实测：50 程序加载、
41 个 gold 三件套齐全（buggy+fixed+官方测试；预注册设计节写"29 任务"
系估算值——判定规则"任一臂 detection>0 ∧ resolved>0"不依赖 n，其余
9 个无官方测试的任务按 M1 口径 detection=None 不进分母）。跑批命令：

```bash
AITESTER_QUIXBUGS_DATA=data/quixbugs AITESTER_PROFILE=logic \
  .venv/bin/python experiments/run_main_batch.py --dataset quixbugs \
  --seed 42 --baselines aitester,plain_llm,plain_llm_df --skip-stats
```

### E2 就绪命令（AJ 批补）

双种子跑批（每批 87 任务 × 3 臂；--max-pattern-repeat 2 与生死实验
同口径；同样**不得** --allow-dirty）：

```bash
for SEED in 42 44; do
  AITESTER_PROFILE=logic .venv/bin/python experiments/run_main_batch.py \
    --task-count 87 --seed "$SEED" \
    --baselines aitester,plain_llm,plain_llm_df \
    --max-pattern-repeat 2 --skip-stats
done
```

合并统计（**--batches 白名单必须只选 E2 新批次**：同种子重复跑会被
"最新批次优先"去重折叠，混入生死实验旧批次会把 gate 前/后口径错配）：

```bash
.venv/bin/python experiments/statistical_analysis.py --results-dir experiments/results \
  --batches main_batch/benchmark_synthetic_<E2_seed42 时间戳>.json,main_batch/benchmark_synthetic_<E2_seed44 时间戳>.json \
  --pool-seeds --output experiments/results/main_batch/statistical_report_e2.md
```

主终点 1 通道计数（过红/抹红行数，期望 → 0；文件名同上白名单）：

```bash
.venv/bin/python -c "
import json, sys
rows = [r for f in sys.argv[1:] for r in json.load(open(f))['results']['aitester']['details']]
over = sum(1 for r in rows if r.get('detection_first_status')=='red_not_repaired' and r.get('detection_rate')==0)
erase = sum(1 for r in rows if r.get('detection_first_status')=='red_then_green' and r.get('detection_rate')==0)
print(f'过红(over-red)={over}  抹红(erase-red)={erase}  (n={len(rows)})')"
```

### E6 就绪命令（AM 批补：前置旗标 --per-task-token-caps 已实现；AO 批修订：cap 改取 E2 实测均值）

E6 四臂 = {aitester, plain_llm_df} × {standard, budget-matched}；
standard 口径直接复用 E2 双门批次（同 seed 42/44、同 gate/档位），
只需新跑两个 matched 臂批次。**matched 上限不得使用 R-P0-2 旧常数
（26,115/4,223）**——按 AO 修订从 E2 standard 批次实测提取。

第 1 步：从 E2 双种子 standard 批次提取各臂每任务 token 均值：

```bash
.venv/bin/python -c "
import json, sys
for f in sys.argv[1:]:
    d = json.load(open(f))
    for arm in sorted(d['results']):
        toks = [r['token_usage']['total_tokens'] for r in d['results'][arm]['details'] if r.get('token_usage')]
        if toks:
            print(f.rsplit('/',1)[-1], arm, f'mean_total_tokens_per_task={sum(toks)/len(toks):.0f}')
" experiments/results/main_batch/benchmark_synthetic_<E2_seed42 时间戳>.json \
  experiments/results/main_batch/benchmark_synthetic_<E2_seed44 时间戳>.json
```

第 2 步：以上一步打印的 aitester / plain_llm_df 均值分别替换
`AITESTER_MEAN` / `DF_MEAN` 后执行（df(matched) 抬至 aitester 均值，
对 df 实际近似无约束，作对称对照留档）。同样**不得** --allow-dirty：

```bash
AITESTER_MEAN=<E2 aitester 实测均值> DF_MEAN=<E2 df 实测均值>
for SEED in 42 44; do
  AITESTER_PROFILE=logic .venv/bin/python experiments/run_main_batch.py \
    --task-count 87 --seed "$SEED" \
    --baselines aitester --per-task-token-caps "aitester=${DF_MEAN}" \
    --max-pattern-repeat 2 --skip-stats
  AITESTER_PROFILE=logic .venv/bin/python experiments/run_main_batch.py \
    --task-count 87 --seed "$SEED" \
    --baselines plain_llm_df --per-task-token-caps "plain_llm_df=${AITESTER_MEAN}" \
    --max-pattern-repeat 2 --skip-stats
done
```

配对分析：matched 批次与 E2 同种子 standard 批次按 `--pool-seeds`
拼接（task_id 加 s<seed>__ 前缀后同任务配对），--batches 白名单 =
两个 matched 批次 + E2 同种子批次；判定读 aitester(matched) vs
df(standard)、df(matched) vs aitester(standard) 两组 detection 配对差。
护栏核对（token_budget_capped=True 行数应集中于 aitester(matched) 臂）：

```bash
.venv/bin/python -c "
import json, glob
for f in sorted(glob.glob('experiments/results/main_batch/benchmark_synthetic_*.json')):
    d = json.load(open(f)); caps = d.get('provenance', {}).get('per_task_token_caps')
    if not caps:
        continue
    for arm, rows in d['results'].items():
        n = sum(1 for r in rows['details'] if r.get('token_budget_capped'))
        print(f, arm, f'capped={n}/{len(rows[\"details\"])}', caps)"
```
