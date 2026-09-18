> **语言 / Language**：[English](CHANGELOG.en.md) | 简体中文（本文）

# Changelog

所有重要变更将记录在此文件中。格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

## [0.1] - 2026-09-18 首个正式版本（功能全集）

### 多智能体架构
- 四智能体协作：Planner（逻辑驱动思维链）/ Generator（RAG 增强）/ Executor（本地/venv/Docker 三模式）/ Debugger（分层错误修复）
- 十二类错误分类：LLM 格式 / 导入 / 语法 / 类型 / 索引 / 断言 / 逻辑 / 运行时 / 超时 / 未知 / 补丁被安全守卫拒绝 / RAG 全空
- AST 精确代码替换（`code_analyzer.py` / `patch_applier.py`），避免正则误匹配
- 检索增强生成（ChromaDB，默认关闭；`ENABLE_RAG=true` 启用，持久化至 `rag_data/`）

### 实验与评估
- 多基线对比（aitester / plain_llm / single_agent）+ 消融实验（Planner / Debugger 开关）
- SWE-bench / Defects4J-Python / 合成数据集 / 内置示例 四数据集支持
- SWE-bench 源码导出自动化（`scripts/export_swe_bench_source.py`）+ 数据污染检测（token 级 Jaccard）
- 统计检验（配对 t 检验 / Mann-Whitney U / Cohen's d）
- 结果分析层（`experiments/analyze_results.py`）：成功率 / 覆盖率 / 迭代分布 / Token 效率 / 失败原因分布 / RAG 检索质量 / 修复收敛 / 边界用例覆盖 / 变异得分 / 断言强度 / 执行反馈轨迹
- 内置变异测试生成器（`experiments/mutation_testing.py`，AST 级三类变异体，每任务 ≤20 个）
- 测试异味检测（Assertion Roulette / Magic Number / 断言弱化 / 平凡测试 / Eager Test / Lack of Cohesion）

### 可观测性与可靠性
- 结构化 JSONL 追踪层（4.1，默认关闭；`AITESTER_TRACE_DIR` 启用）
- 多候选补丁生成与验证筛选（3.1，默认关闭）
- 成本感知路由 + 熔断冷却期 + 半开探测（3.4 + 4.1 + 4.2）
- 跨文件修复（协调器-提议者架构，3.5，默认关闭）
- 断言增强策略（AST 提取现有 assert，3.4，默认关闭）
- Docker 隔离执行（`EXECUTOR_USE_DOCKER`，4.3）
- 依赖缓存监控（venv 命中率可观测 + `clean-venv-cache` CLI）

### 工程化
- Ruff lint + pre-commit + GitHub Actions CI
- 全量 **1459 个测试用例** / 覆盖率 **96%** / Ruff 全绿
- 日志脱敏三层防线（Handler 层 / 入口接线 / trace JSONL 旁路脱敏）

### 基准测试（合成数据集 50 任务，3 基线对比）

| 基线方法 | 成功率 (%) | 平均覆盖率 (%) | 平均迭代次数 | 平均耗时 (s) |
|---------|-----------|---------------|-------------|-------------|
| **AITester** | **88.0** | **97.8** | 0.64 | 45.33 |
| Plain LLM | 68.0 | 98.0 | 0.0 | 16.6 |
| Single Agent | 4.0 | 0.0 | 0.24 | 26.85 |

关键发现：
- AITester 成功率显著高于 Plain LLM（88.0% vs 68.0%），覆盖率持平（97.8% vs 98.0%）
- Single Agent 基线成功率仅 4.0%（50 任务仅 2 个通过），验证多智能体架构的必要性
- 统计检验：AITester vs Single Agent 差异极显著（p < 0.001）

## 版本说明

当前版本为 0.1，是项目首个正式版本。历史内部迭代版本（0.9.x / 0.10 等）不再单独记录，全部功能已并入 0.1 版本。
