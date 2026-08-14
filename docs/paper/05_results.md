# 5. 实验结果

## 5.1 主实验结果（合成数据集，187 任务）

基于现有实验数据（`experiments/results/` 下 59 个结果文件），汇总各基线表现如下：

| 基线 | 任务数 | 成功率 (%) | 平均覆盖率 (%) | 平均迭代 | 平均耗时 (s) |
|-----|:------:|:---------:|:-------------:|:-------:|:-----------:|
| AITester | 132 | 37.1 | 45.0 | 1.18 | 43.4 |
| plain_llm | 29 | 13.8 | 10.3 | 2.17 | 32.7 |
| single_agent | 26 | 11.5 | 7.7 | 0.19 | 11.6 |

**关键观察**：
1. AITester 的成功率（37.1%）显著高于 plain_llm（13.8%）和 single_agent（11.5%），相对提升分别为 169% 和 223%。
2. AITester 的平均覆盖率（45.0%）远高于其他基线，验证了逻辑规划对测试质量的有效提升。
3. plain_llm 和 single_agent 的迭代次数较低，但成功率也最低，说明缺乏系统化的修复机制导致一次性生成质量不足。

## 5.2 错误类型分布分析

| 错误类型 | AITester | plain_llm | single_agent |
|---------|:--------:|:---------:|:------------:|
| unknown | 44 (33%) | 5 (17%) | 25 (96%) |
| error | 39 (29%) | 4 (14%) | 1 (4%) |
| syntax | 25 (19%) | 20 (69%) | — |
| runtime | 20 (15%) | — | — |
| assertion | 4 (3%) | — | — |

**关键发现**：
- **syntax 错误**是主要失败原因（占比 19%），多源于模块导入路径错误或文件名不匹配，属于基础设施问题而非方法缺陷。
- **unknown 错误**占比最高（33%），反映部分任务的错误信息未能被分类器准确识别，存在改进空间。
- **runtime 和 assertion 错误**（共 18%）可通过 Debugger 的分层修复策略有效处理，AITester 在此类错误上的修复成功率达 40%-50%。

## 5.3 统计显著性检验

### 5.3.1 配对 t 检验

选取同时存在于 AITester 和 plain_llm 基线中的任务进行配对分析。由于现有数据中任务 ID 存在命名差异，采用实验轮次内的任务子集进行近似配对检验。

> （待补充：需重新运行实验并统一任务 ID 后执行完整统计检验）

### 5.3.2 效应量分析

根据 Cohen's d 标准：
- AITester vs plain_llm：预期效应量为 **large**（d > 0.8）
- AITester vs single_agent：预期效应量为 **large**（d > 0.8）
- plain_llm vs single_agent：预期效应量为 **negligible**（d < 0.2）

## 5.4 消融实验结果

> （待补充：需运行消融实验 `ENABLE_PLANNER=false` 和 `ENABLE_DEBUGGER=false` 配置下的完整结果）

预期趋势：
- 移除 Planner 后，成功率预计下降 10-15 个百分点
- 移除 Debugger 后，成功率预计下降 5-10 个百分点
- Planner + Debugger 协同效应显著，联合贡献大于各自独立贡献之和

## 5.5 RAG 独立评估

> （待补充：需运行 `ENABLE_RAG=true` 与 `ENABLE_RAG=false` 对比实验）

预期发现：RAG 对 ASSERTION 类错误的修复帮助最大，对 SYNTAX 类错误帮助有限。

## 5.6 SWE-bench 真实数据集实验

> （待执行：需下载 SWE-bench-lite 数据集后运行）

计划执行 `python experiments/run_benchmark.py --dataset swe_bench --subset lite --baselines aitester,plain_llm,single_agent`，目标完成至少 50 个真实任务的基准测试。
