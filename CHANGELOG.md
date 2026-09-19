> **语言 / Language**：[English](CHANGELOG.en.md) | 简体中文（本文）

# Changelog

所有重要变更将记录在此文件中。格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

## [0.2] - 2026-09-19 代码质量与可靠性优化轮次

两个原子提交（`9f83197` + `d5f21f6`），零功能破坏，全量测试 1459→1460（净增 1 用例），Ruff 全绿。

### 重构与修复
- **RAG 降级守卫抽取**（`graph/rag.py` 新增 `rag_guarded`，依赖注入式设计）：
  统一 `graph/nodes.py` 中 4 处同构的「ENABLE_RAG 前置判断 + 取检索器单例 +
  try/except 降级」模板（generator 检索 / executor 入库 / debugger 检索 /
  debugger 入库）。依赖以参数注入而非模块内直读全局，历史 patch 路径
  （`src.graph.nodes.ENABLE_RAG` / `get_rag_retriever` 等 8 个测试用例）继续有效。
- **多函数补丁排序性能优化**（`tools/patch_applier.py`）：
  `apply_multi_function_patch` 排序 key 由「每个 patch 各自 split 一遍代码行」
  （O(n·m)）改为「预切分行复用」（O(n+m)），多文件大补丁场景直接受益。
- **实验排名绑定修复**（`experiments/analysis.py`）：`_rank_by_metric` 改为
  (name, value) 元组绑定排序，消除按 `zip` 位置错配排名的结构隐患；
  新增乱序插入回归测试 1 条（全量测试 1459→1460）。
- **数据库库名白名单**（`init_db.py`）：`MYSQL_DATABASE` 拼入
  `CREATE DATABASE` 前做 `[A-Za-z0-9_]+` 白名单校验，堵环境变量注入多语句
  SQL 的向量；import 顺序合规化。
- **懒导入消除**（`agents/base_agent.py`）：`_find_balanced_json` 与
  `extract_focused_code` 的函数内惰性导入提到模块顶层（两模块均无循环依赖），
  消除每次调用的 import 机制开销与别名噪音。
- **脱敏双实现收敛**（`agents/llm_client.py` + `api/api_manager.py`）：
  `_redact` / `_redact_log_text` 两套近似实现收敛为委托 `logging_utils.
  mask_sensitive_info` 的同一套逻辑，注释标明单一实现入口防漂移。
- **原子写盘异常收窄**（`graph/nodes.py`）：临时文件清理的
  `except BaseException` 改 `except Exception`（PEP 8：
  KeyboardInterrupt/SystemExit 不应插入清理路径，临时文件由进程退出兜底）。
- **API 管理器性能与可配置性**（`api/api_manager.py` + `api/api_health.py`）：
  `get_status` 中 `get_healthy_nodes()` 由连调两次改为结果复用（全节点池
  遍历减半）；批量健康检查节点间隔由硬编码 0.1s 提为可配置项
  `APIManagerConfig.batch_health_check_interval`（默认 0.1s 保持历史行为，
  100+ 节点池场景可设 0 或配合并发探测上调）。

### 测试清理
- 修复 1 处恒真断言（`tests/test_weak_coverage_modules.py` 的
  `assert ... or True`，此前该用例永远通过、形同虚设）。
- Ruff 自动 + 手动清理 tests/ 存量告警 24 条（未用变量 / 未用导入 /
  隐式 Optional / 裸 open / 冗余 monkeypatch 别名等）。

### 工程化基线
- 全量测试 **1460 passed / 0 failed**（约 30s）；`ruff check src/ tests/` 全绿
- 静态分析完整报告归档于 `docs/code_analysis_report.md`（30 条发现 +
  「值得做 / 不建议做」清单，本轮落地 6 条高价值项）

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

当前版本为 0.2。历史内部迭代版本（0.9.x / 0.10 等）不再单独记录，全部功能已并入 0.1 版本；0.2 为其上的代码质量优化轮次（无新功能，仅重构/修复/测试清理，零功能破坏）。
