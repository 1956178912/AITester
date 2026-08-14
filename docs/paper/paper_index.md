# AITester 论文文件索引

> 生成时间: 2026-08-14
> 论文标题（暂定）：AITester: 基于多智能体协作的逻辑驱动测试生成与自动修复框架

## 论文结构

```
docs/paper/
├── paper_index.md          ← 本文档（论文导航）
├── 01_introduction.md      ← 第1章 引言
├── 02_related_work.md      ← 第2章 相关工作
├── 03_methodology.md       ← 第3章 方法论
├── 04_experimental_setup.md ← 第4章 实验设置
├── 05_results.md           ← 第5章 实验结果
├── 06_discussion.md        ← 第6章 讨论
├── 07_conclusion.md        ← 第7章 结论
├── 08_appendix.md          ← 附录
└── failure_analysis.md     ← 失败案例分析报告
```

## 核心数据摘要

| 基线 | 任务数 | 成功率 | 平均覆盖率 | 平均迭代 | 平均耗时 |
|-----|:------:|:-----:|:---------:|:-------:|:-------:|
| AITester | 132 | 37.1% | 45.0% | 1.18 | 43.4s |
| plain_llm | 29 | 13.8% | 10.3% | 2.17 | 32.7s |
| single_agent | 26 | 11.5% | 7.7% | 0.19 | 11.6s |

**相对提升**：AITester vs plain_llm = +169%，AITester vs single_agent = +223%

## 待补充项（标记为"待填充"的段落）

1. Section 5.3：配对 t 检验完整结果（需重新运行实验统一任务 ID 后补充）
2. Section 5.4：消融实验具体数据（需运行 `ENABLE_PLANNER=false` 和 `ENABLE_DEBUGGER=false`）
3. Section 5.5：RAG 独立评估（需运行 `ENABLE_RAG=true` 对比实验）
4. Section 5.6：SWE-bench 真实数据集实验结果（需下载数据集后执行）

## 下一步行动

1. **网络恢复后**：运行 `python experiments/run_large_scale.py --task-count 100` 收集更多数据
2. **SWE-bench 准备**：运行 `python scripts/download_swe_bench.py --subset lite` 下载真实数据集
3. **消融实验**：分别运行 `ENABLE_PLANNER=false` 和 `ENABLE_DEBUGGER=false` 配置
4. **统计检验**：统一任务 ID 后运行完整配对 t 检验
5. **论文整合**：将各章节合并为最终 LaTeX/PDF 版本
