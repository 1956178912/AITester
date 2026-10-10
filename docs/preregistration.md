# 预注册：E1–E4 验证实验（检出优先协议 + 逻辑链 + 双门）

最后更新: 2026-10-07（**E2 迭代批**：用户批准动用"恰好一次"门参数/
路由修正迭代——迭代前置三缺陷修复：①fl_at_k 0/174 根因=实现背离
R8 docstring 设计（只认系统补丁 diff，而 synthetic patch 系整文件
替换文本恒解析为空，且 `_extract_diff_line_numbers` 单参调用两参
函数 TypeError 被吞、fallback 自诞生即死）——修复为 gold diff
优先（SequenceMatcher buggy 侧差异行，与 fl Top-k 行号同轴）+
修活的 patch diff fallback；②recursion_limit 8×MAX+8=32 仍触顶
16/174 → 16×MAX+8=56；③mutation 31/174 系**设计保守口径非缺陷**
（生成测试在 gold fixed 上不全绿 → None 不误报；即 82% 生成测试
在正确代码上不过——本身为主要科学发现）——修正均为 harness/测量
口径修复，不触碰主终点判定规则与统计协议；迭代重跑同命令同种子。
此前同日 E2 首跑判定：两通道降幅 67.0%/85.7% 过停止线落入本迭代
分支、H2c δ=−0.3673 显著为负结论升级；E1 已执行 0.367≥0.3 保留；
此前同日 AO 批：E6 matched 上限来源修订——改取 E2 实测均值，修订
早于任何 E6 数据；此前同日 AN2/AN5 呈现性增补入 E3 节；2026-10-06
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
  **修订注记（2026-10-07 批次 XIII，ADR-0021/0027）**：repair 全线 0
  系 patch 字段围栏残留测量伪影——修正口径存量重放 R-P0-2 = 35.9%
  （52/145 可重放行）。上述 detection 类结论与 H2 判定不受影响
  （detection 通道未受染）；引用 repair 数字处一律以修正口径为准。
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

### E4 污染防控（R4，2026-10-09 预注册增补，早于任何 E4 正式数据）

> 背景：SWE-bench 系基准存在已被 2024–2025 文献证实的系统性训练数据污染。
> 本增补把"污染防控"从隐性假设升级为预注册的**强制披露条款**，使 E4 的
> "真实基准"结论不被污染质疑连带推翻。增补时点早于任何 E4 正式三臂数据
> 产生（R4 阶段仅 R4 副产品单臂，非 E4），git 历史可核。

- **污染风险声明（引用证据，均须在 E4 报告引用章节原文标注 DOI/URL）**：
  ① Aleithan et al. 2024——原始 SWE-bench 94% 实例早于主流 LLM 训练截止，
  高分可能部分来自直接/间接记忆而非泛化能力；② Liang et al. 2025——SOTA
  LLM 仅凭 issue 描述猜中 buggy 文件路径达 76%（SWE-bench Verified）；
  ③ Wang et al. 2025（PatchDiff）——差分测试显示至多 6.4pp 表观增益为
  "幻影"（评估不健全所致）；④ Yu et al. 2025（UTBoost）——测试增强与更严
  解析修正了 24% 的 leaderboard 条目。QuixBugs 为经典教学基准（Derrick
  Lin 等），同样处于主流 LLM 训练语料覆盖范围，污染风险**不可假设为零**。
- **强制披露口径（E4 报告须含独立小节）**：
  1. **模型训练截止 vs 实例时间**：记录 E4 所用模型（deepseek-flash 等）的
     公开训练截止日期，与 QuixBugs 实例引入时间对照，标注"潜在重叠"实例占比；
  2. **靶点错位声明**：延续 SWE-bench Lite 0/20 的诚实披露口径——若 E4 为
     负结果，须区分"方法无效"与"靶点错位"（函数级单文件修复 vs 仓库级任务）
     两种解释，不得静默归因任一方向；
  3. **差分测试复核（PatchDiff 式）**：对 E4 中 detection/resolved 为正的
     行，抽样做"提示剔除定位线索后重跑"的差分检验——若剔除 issue/路径线索
     后正结果显著下降，须在报告标注污染成分区间；
  4. **可复现性**：污染披露不得依赖手工判断——以"模型截止日期 + 实例时间 +
     差分重跑"三个客观字段入结果行或报告附录。
- **判定增强**：原"任一臂 detection>0 ∧ resolved>0"维持不变；新增
  "污染披露小节缺失 → E4 报告视为不完整，不得用于对外引用"的硬约束。
- **预算影响**：污染防控为**离线字段记录 + 抽样差分重跑**，无额外 LLM 全量
  成本（差分重跑仅在正结果行抽样，≈ 0.01M token 量级），不改变 E4 预算口径。

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
  **修订注记（2026-10-07 批次 XIII，早于任何人脸复核数据）**：E7 的
  动机已被 ADR-0021 机制性回答——gold 裁决非"过严低估"，而是从未
  执行真实补丁（patch 字段围栏残留 → 100% NameError）；修正口径
  repair = 35.9%（52/145，`make corrected-metrics`）。原判定分支
  "= 0 → 真零"作废；人工复核仍有独立价值（检验修正口径下 61% 的
  wrong_patch 行是否存在语义等价被漏判），但性质从"口径低估检验"
  降级为"残余语义等价抽样审计"，预期占比大幅缩水。
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
- 功效依据：`scripts/tools/power_analysis.py`（基线检出 2%、检出差 10pp 需
  n≈87；E2 双门若为近确定性通道消除，复核定位以通道归零为主、效应量
  估计为辅）。

## 工件与可复现性

- 每个实验产出：批次 JSON + 全量 trace + 统计报告 + SHA256SUMS，全部
  入 git 白名单（experiments/results/main_batch/ 口径）；
- 跑批前验证 provenance `git_dirty=False`，不满足时中止并登记原因；复跑
  一律**不得**使用 `--allow-dirty`（AK 勘误补注，AL1 改写为禁止语境：
  R-P0-2 当时即在该旗标口径下跑批，provenance 瑕疵已在 pooled 报告
  "AK 勘误"节登记；报告引用工件的入库由
  `scripts/gates/check_artifacts_tracked.py` CI 强制）；
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
| E1 | 已执行（12/12 有效，其中 2 任务 recursion_limit 触顶无终态，E1 后置修复，见文首注记） | `experiments/results/ab1_validation_e1/`（AITESTER_PROFILE=logic，seed 42，temp 0.0，git_dirty=False，deepseek-flash，87,495 tok） | spec_compile_rate 均值=0.367（n=10/12 可测）；伴随观测：detection=20.0%（2 例均 specific_red 门确认）、repair=0.0%、false_fix=80.0% | **保留**（≥0.3） | 2026-10-07 |
| E2+E3 | 已执行（首跑 + 迭代重跑各双种子 42/44 × 3 臂；迭代批逐位复现首跑主指标——temp 0.0 缓存命中确定性重放，本迭代为恰好一次，后续不再迭代） | 迭代批 `main_batch/benchmark_synthetic_20261007_181638.json` + `..._185941.json` + `statistical_report_e2_iter.md`；首跑 `..._161053.json` + `..._170147.json` + `statistical_report_e2.md` | 迭代终判：过红 88→31（降幅 64.8%）、抹红 28→2（降幅 92.9%）；aitester vs df δ=−0.3673 [−0.4552,−0.2785]（bayes_neg，与首跑逐位一致）；pooled detection：aitester 12.7% / plain_llm 1.7% / df 52.3%；repair 全线 0.0%；spec_compile_rate=0.212（灰区）；**FL@1 首度可测 19/53=35.8%**（gold diff 修复后）；mutation 可测 31/174 均值 0.767（保守口径）；触顶 16/174（56 上界下 df 臂失控回环仍在，如实披露） | H2a/H2b **不成立**（未归零；降幅均 ≥50% 但"恰好一次"迭代已用尽 → 按停止规则接受结果：门削减过红约 2/3、抹红约 93%）；H2c **"编排容器在检出口径下结构性劣后"结论最终确立**（ADR-0016 预写，可发表）；次要终点 repair 未破零；E3 非空率：fl 30% 可测（修复后）/mutation 18%（设计口径）/spec 91% | 2026-10-07 |
| R4 A/B + QuixBugs 单臂（**预注册外调试豁免**，非 E4） | 已执行（R4 通道原型验证的副产品；synthetic 两臂系 **dirty 树跑批**、QuixBugs 两臂系干净树跑批） | `experiments/results/r4_batches/{r4_ab_arm_a,r4_ab_arm_b,r4_synth_arm_b2,r4_qb_arm_a,r4_qb_arm_b,loc_test_quix}`（2026-10-08 R2 入库，含 SHA256SUMS/README） | synthetic repair 8/50；QuixBugs A/B repair M1 可测口径 **37/41、36/41**（all-task 37/50、36/50） | R4 局部化约束**阴性**（A/B 无增益）；QuixBugs 单臂仅验证管道，**不构成 E4 正式执行** | 2026-10-08 |
| E4 | **已执行（2026-10-09，双臂完整结算：`aitester` + `plain_llm_df`）** | `experiments/results/e6_a1_batches/e4_quixbugs_aitester/`（`benchmark_quixbugs_20261009_215514.json`） + `e4_quixbugs_plain_llm_df/`（`benchmark_quixbugs_20261009_223101.json`），各含 50 traces 与日志 | **41 缺陷程序口径：两臂 detection 均 0/41 = 0.0%**；aitester repair 35/40 = 87.5%、false_fix 2.5%、token/task 17,156、red_seen 40/41；df repair 0（无修复通道）、token/task 2,370、red_seen 41/41。**配对 McNemar（detection）：不一致对 = 0、p = 1.0000**（41/41 逐位一致）；贝叶斯 δ=+0.0000、95% CI [−0.0659, +0.0672]、P(\|δ\|≤ROPE)=0.8943 | **主终点失败**（双臂 `detection > 0` 均不成立）。**机制定案**：红测试普遍存在（red_seen 40–41/41）但**不特异**——F2P 三段判定第 2 段（fixed 上绿）不通过，故「0% 检出」的准确含义是**「红得不特异」**（断言错/过苛，或 30s 执行超时），与合成集 over-red 通道同源。**「修复依赖非 F2P 信号」假说被否证**：repair 由 gold 测试独立裁决，与生成测试通道不相交。**真实基准上编排 vs 纯提示 detection 无差异**（p=1.0）而编排贵 7.2× token。限定：两臂各自标准预算，非等预算对照 | 2026-10-09 |
| E6 | **已执行（2026-10-09，两阶段：冷缓存 standard + matched）** | `experiments/results/e6_a1_batches/e6_phase1_standard_coldcache/`（standard 三臂）+ `e6_phase2_matched_coldcache/`（matched 两臂），含 SHA256SUMS/README | 四臂 detection：aitester standard 6.9%（6/87, 8,857 tok）· aitester matched 2.3%（2/87, 87/87 触顶）· df standard 31.0%（27/87, 2,586 tok）· df matched 26.4%（23/87, 2,602 tok） | **预算混杂被证否**：df(matched) vs aitester(standard) χ²=13.474 p=0.0002（BH q=0.0002）显著；df 抬预算后**不消费增量**（2,586→2,602）且检出无显著变化（p=0.2888）→ **−28pp 归因编排结构，ADR-0016 结论加固**。限定：aitester(matched) 的 cap 低于其单任务需求（84/87 行触顶提前终止），该臂测的是「预算不足时编排的表现」，非严格等能量对比 | 2026-10-09 |
| E7 | 待人工复核（候选清单已生成，AO 批） | — | — | — | — |
| **A1 消融（预注册外，2026-10-09 审查报告 §5 路径 A1）** | **执行中（2026-10-09，见下方 A1 设计声明）** | 待落盘 | — | **先声明后取数** | — |

### E6 执行增补（2026-10-09，**数据产生前登记**）

**动因**：E6 预注册（AO 修订）要求 budget-matched 上限取"**E2 同种子 standard 批次
实测的每任务总 token 均值**"。执行前核查发现该前提**不成立**：E2 四个批次
（`..._161053/_170147/_181638/_185941`）结果行中**仅 aitester 臂有
`token_usage.total_tokens`**，`plain_llm_df` 与 `plain_llm` 两臂**无 token 行**
（df 在 R-P0-2 尚有 79/87 行、E2 批为 **0 行**）。故 **df 臂 matched cap 在现有
工件中不可推导**，E6 无法按原设计直接开跑。

**增补决策（不改主终点/判定/停止规则）**：先跑一批 **E6 control**（E2 协议同参：
seed 42、n=87、logic 档、双门、`TEMPERATURE=0`、`--max-pattern-repeat 2`、
**`LLM_THINKING_MODE=disabled`**——与 E2 及 E6 预注册预算口径一致，
见本文件 :96），用途：

1. 补齐 **df 臂 token 实测**（原缺失项），使 matched cap 可推导；
2. 提供 A1 消融臂所需的**同批 aitester 对照**（同代码状态、同种子、同协议）；
3. 作为 E6 standard 臂的**当次复现基线**（代码状态已并入 R2–R5 落地改动，
   与 E2 的 git 状态不同，故不可直接沿用 E2 行作对照）。

**已知偏差（如实登记）**：control 批 `token_usage` 在 df 臂仍有**部分行为 0**
（小样本冒烟实测 3/5 行有值；0 值来自"截断后无测试入选"与"检出未触发再生成"
两类路径）——**故 df 的 matched cap 只能按"有值行均值"推导，分母非 87**，
引用须注明分母。此偏差不改 E6 主终点判定（detection 配对差不依赖 cap 精度），
但会影响 matched 臂是否**真正绑定**上限，须在结果报告中显式披露。

### A1 消融设计声明（2026-10-09，**预注册外实验；先声明后取数**）

**诚实前置**：A1 **不在**原 E1–E7 预注册内，系 2026-10-09 审查报告
（§5 路径 A1、§8.6 红队 RT3）新提假设的**探索性验证**。本节在设计执行前登记，
以保留"先声明后取数"的可审计性；**不得**据此声称与 E1–E7 同级证据强度。

**假设（H-A1）**：R-P0-2 中 aitester 显著劣于 `plain_llm_df`（δ=−0.279）的
主导机制**不是** ADR-0016 所述"编排结构性劣后"，而是 **oracle-from-
implementation**：Planner 读**缺陷代码**产出 `test_cases[].expected_output`
（`templates.py:25`）→ Generator 整段 plan JSON 入 prompt（`generator.py:353`）
→ 期望值 = 实现当前（错误）行为 → 断言在 buggy 上全绿（never-red 通道 86/240）。

**干预（单变量）**：`PLAN_STRIP_EXPECTED_OUTPUT_ENABLE=true` —— 仅从 Generator
prompt 中剥除 `test_cases[].expected_output`，**保留** `case_name` /
`input_args` / `category` / `description` / `logic_coverage` 与整个
`logic_analysis`。默认 false（历史口径零变化，ADR-0003）。

**设计**：2 臂 = {aitester(standard), aitester(strip)} × seed 42 × n=87 ×
E2 协议同参（logic 档 / 双门 / temp 0.0 / thinking disabled /
`--max-pattern-repeat 2`）；对照取上表 E6 control 批的 aitester 臂（同代码状态）。

**主终点**：detection 配对差 δ（McNemar + BH-FDR；并按 pooled 报告先例补
**模板级 DEFF 校正 + 符号检验**——n=87 名义样本下模板簇 k≈31，n_eff 远小于 87）。

**判定规则（先声明）**：
- strip 臂 detection 显著**高于** aitester(standard)（CI 不含 0 且 ROPE ±5pp 外）
  → **H-A1 成立**：−28pp 主导机制是 oracle-from-implementation，ADR-0016 的
  "编排结构性劣后"须**降格为"未与实现缺陷解耦"**；
- δ≈0 → H-A1 不成立，never-red 另有成因（转向 A2/A3 路径）；
- 混合/边缘 → 如实报告，不作二次迭代。

**停止规则**：一次性实验，无迭代条款。**预算**：≈1.2M token（thinking 关口径）。

### A1 执行结果（2026-10-09，**数据产生后追加，判定规则未改**）

| 项 | 结果 |
|---|---|
| detection（standard） | **8/87 = 9.2%** |
| detection（strip） | **8/87 = 9.2%** |
| 配对 McNemar | 不一致对 **2**，χ²=0.500，p=0.4795，**BH-FDR q=1.0000** |
| 贝叶斯配对 | δ=**+0.0000**，95% CI **[−0.0451, +0.0445]**，P(\|δ\|≤ROPE)=**0.9691** |
| 模板簇校正 | k=29，ICC=0.671，DEFF=4.356，n_eff=39.9/174；符号检验 1:1，p=1.0000 |
| **判定** | **H-A1 不成立**。95% CI **完全落在 ROPE ±5pp 内** → 按 equivalence 口径为**实际等价**（强于"不显著"）；本路径撤回 |

**效力限定（必须并列）**：干预在 **34/87（39%）任务上结构性空转**——Planner 输出
结构不完整回退默认计划时 `test_cases = []`，**无 `expected_output` 可剥**
（`nodes.py:242-248` → `_get_default_test_plan`）。故效力范围为剩余 **61%** 任务；
在该范围内仍为零效应。**副产物**：该 39% 空计划率是 never-red 通道的**新候选真因**
（优先级高于原 A1/A2/A3）。

**工件**：`experiments/results/e6_a1_batches/a1_strip_seed42/`（含 SHA256SUMS/README）。

### E6 阶段 1 执行增补（2026-10-09，**数据产生前登记**）

**动因（承接上方「E6 执行增补」的已知偏差）**：control 批实测确认
`plain_llm`/`plain_llm_df` 两臂 token **0/87 行**、aitester 仅 37/87。根因定位：
`src/agents/base_agent.py:389/437` 缓存命中时提前 `return`，**绕过 `record_usage`**
——而该文件 `:339` 自述"缓存命中…不再消耗 token——历史口径保持。**正式实验须显式
`AITESTER_LLM_CACHE=0`**"。即：**热缓存跑批的 token 记账天然不完整**，这是既有
设计口径而非新缺陷；但 E6 的 matched cap 需要**完整**记账。

**增补决策（不改主终点/判定/停止规则）**：E6 分两阶段执行——

- **阶段 1（本次）**：standard 三臂 × **`AITESTER_LLM_CACHE=0`（冷缓存）**
  × seed 42 × n=87 × 其余协议同 control（logic 档 / 双门 / temp 0.0 /
  thinking disabled / `--max-pattern-repeat 2`）。用途：取得**完整**的每任务
  token 记账（三臂全覆盖），据此按 AO 修订推导 matched cap；
- **阶段 2（待阶段 1 出数）**：matched 两臂 `df(matched)`（cap 抬至 aitester 实测均值）
  与 `aitester(matched)`（cap 压至 df 实测均值），经 `--per-task-token-caps` 注入。

**已知代价（如实登记）**：冷缓存意味着**放弃缓存复用**，阶段 1 的 token/成本高于
热缓存批次，且阶段 1 的 aitester 与 control 批**不可直接配对**（缓存状态不同）——
阶段 1 仅用于**推导 cap**，E6 主终点对比在阶段 2 与阶段 1 的 standard 臂之间进行。

**停止规则**：阶段 2 一次性执行，无迭代条款。

**停止规则**：一次性实验，无迭代条款。

**v2 修正口径指针（2026-10-08 R2，R27/R13）**：上表 E2+E3 行"repair 全线 0.0%"
系 ADR-0021 围栏伪影 + **第三起伪影（跨文件任务未物化，R27）** 双重受染的原始值。
R27 修复后按修正口径重放（`experiments/results/main_batch/corrected_report_v2.md`）：
R-P0-2 修正 repair **39.31%（57/145）**（v1 35.86%，52/145）；E1/E2 **54.72%（58/106）**
（v1 48.11%，51/106）。对外引用一律以 v2 与
`docs/design/repair_caliber_matrix.md` 口径矩阵为准（引用须注明分子/分母/oracle/臂）。

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

### A1 假阴性更正与两个特异性修复的受控臂（2026-10-10）

**A1 假阴性**：原 A1 批次 `a1_strip_seed42` 的
`env_snapshot.PLAN_STRIP_EXPECTED_OUTPUT_ENABLE` 为 **`None`**（未设置）、
日志中零条“A1 消融生效”行、且两臂 detection 逐点相同（8/87）
—— 即 **消融从未生效**，原“零效应”是**假阴性**。
**结论：结果一的 H-A1 证否作废。**

**A1 首次真正生效的受控臂**（`PLAN_STRIP_EXPECTED_OUTPUT_ENABLE=true`，
判分树为修复后版本，QuixBugs 41 缺陷程序口径，生效性已验）：
detection **45.9% → 51.4%**（+5.5pp），首轮 `over_red` 21→17；
配对 McNemar **p=0.7237**（不显著）。

**over_red 强化段受控臂**（新增 `OVER_RED_SECTION_ENABLE`，**默认 false**）：
detection **45.9% → 51.4%**（+5.5pp），首轮 `over_red` 21→18；
配对 McNemar **p=0.7237**（不显著）。**两个方向数值完全一致且均不显著。**

**两个审计缺口（均已修复）**

1. **消融开关未入 provenance 快照**：over_red 首跑的 `env_snapshot`
   不含该键 → **无法从工件证明干预生效**（与 A1 假阴性同类）；
   已将 `OVER_RED_SECTION_ENABLE` 加入 `_env_snapshot_keys`，并加回归测试锁定。
2. **会改变 prompt 的消融必须用独立 cache namespace**：
   over_red 首跑复用了标准臂 namespace，而强化段恰好**只在再生成时注入**
   → 已缓存的再生成响应被直接复用，**干预文本根本未送到模型**；
   首跑的 59.5% 不作结论依据。

**瓶颈重定位**：两个 prompt 方向均停在 +5.5pp，说明它们**未触及主因**——
`over_red` 任务中相当一部分是**缺陷实现不终止**（挂起）：
4 个 `detection=None` 任务（`bitcount`/`find_first_in_sorted`/`sqrt`/`wrap`）
全属此类（`bitcount` 缺陷 `n ^= n - 1` 应为 `n &= n - 1`，对任何 n 不终止）。
**再好的 prompt 也无法让一个挂起的测试“变红”**，需的是
**测试侧超时判定**（将“挂起”记为检出），已列为后续独立设计任务。

### 第四起测量伪影修正与 E4 重结算（2026-10-10）

**伪影（已修）**：M1 判分树 `_prepare_packaged_test_tree` 仅提供 QuixBugs
包结构 `python_programs/{module}.py`，而被测模块名取 `task_id` 末段、
生产执行沙箱把模块**平铺**写成 `{module}.py`，故 Generator
写出的**扁平 import**（如 `from bitcount import bitcount`，在其生成环境里
是正确的）在判分树里一律 `ModuleNotFoundError` → pytest `rc=2`
（收集中断）→ `detection` **构造性恒为 0**。

**修复**：双布局（tmpdir 根同时写一份 `{module}.py`）。
**三段判定逐字未改、口径未放松**（恒失败测试在新布局下同样得 0，
已加回归测试）。

**零 LLM 验证**：12 任务子集 9 个缺陷程序，修复前 **9/9 在 buggy 与
fixed 两侧均 rc=2**；同一批工件仅改判分树 → F2P 检出 **0/7 → 6/7**。

**E4 重结算（单变量：同协议、同 cache namespace 复用原响应）**

| 臂 | detection（41 缺陷程序口径） | token/task |
|---|---|---|
| `aitester` | **17/37 = 45.9%**（修正前 0/41 = 0.0%） | 16,038 |
| `plain_llm_df` | **31/37 = 83.8%** | **1,905** |

配对 McNemar（修正前 vs 修正后，aitester）：不一致对 17、
χ²=15.059、**p=1.042e-04**；2×2：**n10=17、n01=0**（单向翻转）。
配对 McNemar（两臂）：不一致对14、χ²=12.071、**p=0.0005**。

**结论（取代本预注册此前的 E4 行文）**：
真实基准上完整编排的检出率显著低于纯提示
（45.9% vs 83.8%）且成本高 8.4×；两臂能力互补
（df 擅长检出、aitester 擅长修复 92.5%）。

### E4 数据集口径增补（2026-10-09，**数据产生前登记**）

**发现（零 LLM 成本，逐任务核对）**：`data/quixbugs` 复取成功
（commit `4257f44b0ff1181dedaedee6a447e133219fcebf`，与上方登记一致），
但加载器给出的 **50 个任务中 9 个是 QuixBugs 的"测试驱动脚本"**（`program`
以 `_test` 结尾，如 `breadth_first_search_test`），**无 gold `test_cases`**，
M1 判定必然 `detection=None` / `repair=None`。

**决策（不改主终点定义，只改分母口径）**：
- **E4 主终点 `detection>0 ∧ resolved>0` 只在 41 个有 gold 的缺陷程序上计算**；
- 9 个测试驱动任务**从任务集剔除**（或单列为"非缺陷样本"，不计入分母）；
- 理由：这 9 个任务**结构上不可能被"解决"**（它们本身就是测试脚本），
  计入分母等于对系统无条件扣分，会使 E4 结果偏向假阴性。

**时点声明**：本增补登记于**任何 E4 正式数据产生之前**（E4 执行记录仍为"待执行"），
符合"修订效力声明早于数据产生"条款。

**同时更正**：此前"QuixBugs 50 程序 / 41 gold"的表述应读作
"**50 个 Python 文件 = 41 个缺陷程序 + 9 个测试驱动**"。

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
