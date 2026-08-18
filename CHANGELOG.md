# Changelog

所有重要变更将记录在此文件中。格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

## [Unreleased]

### 新增功能
- **API 管理器增强**：新增 `src/api_manager.py` 模块，支持多 Provider 轮询和高可用故障转移
  - 实现轮询、加权随机、健康感知、最快优先四种策略
  - 支持动态节点添加/移除
  - 自动健康检查与故障转移
  - 新增 31 个单元测试覆盖完整功能
- **LLM 缓存机制**：实现 `src/graph/llm_cache.py`，支持 LLM 调用结果缓存
  - 减少重复 API 调用，节省 token 消耗
  - 提供缓存统计接口
- **错误报告生成器**：新增 `src/reports/` 模块，支持将测试失败信息转化为结构化诊断报告
  - 支持文本、JSON、Markdown 三种输出格式
  - 自动分类错误类型（语法/运行时/断言/超时/未知）
  - 生成根本原因分析和修复建议
  - 集成 `ErrorClassifier` 进行错误分类
  - 新增 13 个单元测试覆盖完整功能
- **多 LLM 配置支持**：`LLM_CONFIGS` 列表支持 API Key 轮询和高可用
  - 配置格式：`LLM_N_API_KEY`, `LLM_N_BASE_URL`, `LLM_N_MODEL_NAME`
  - 向后兼容：保留 `MODEL_NAME`, `OPENAI_API_KEY` 等旧变量名

### 代码质量
- **Ruff 代码格式化**：修复 791 个代码风格问题（导入排序、空白行、过时类型注解等）
- **类型注解现代化**：将 `Optional[X]` 替换为 `X | None`，符合 Python 3.10+ 风格

### 工程化改进
- **Ruff Lint 配置**：新增 `pyproject.toml`，配置 ruff 进行代码检查和格式化（替代 flake8 + isort）
- **Pre-commit Hooks**：新增 `.pre-commit-config.yaml`，集成 ruff、mypy、trailing-whitespace 等检查
- **GitHub Actions CI**：新增 `.github/workflows/ci.yml`，支持多 Python 版本测试、lint 检查和安全扫描
- **pytest 配置**：在 `pyproject.toml` 中配置 pytest 参数（测试路径、标记、输出格式）

### 性能优化
- **RAG 检索器单例化**：将 ChromaDB 客户端改为懒加载单例模式（`src/graph/workflow.py`），节省每个任务 2-6 秒初始化时间
- **LLM_TIMEOUT 配置接入**：在 `src/agents/base_agent.py` 中接入 `LLM_TIMEOUT` 配置，防止 LLM 调用卡死
- **并发执行支持**：实现 `BENCHMARK_PARALLELISM` 环境变量驱动的多线程并行基准测试（`experiments/run_benchmark.py`）
- **Parametrize 重试逻辑优化**：修复 `src/agents/generator.py` 中 parametrize 校验失败时使用相同 query 重试的问题，改为追加负面反馈提示
- **Executor 导入路径搜索优化**：限制 `_auto_fix_imports` 的全量 rglob 遍历，优先检查常见路径（`src/`, `lib/`, 当前目录），提升 98.6%

### Bug 修复
- **指数退避重试逻辑**：修复 `src/agents/base_agent.py` 中的重试退避策略
- **路径安全检查**：增强 `src/tools/patch_applier.py` 的路径验证，防止路径遍历攻击
- **模块导入路径搜索优化**：限制 `_auto_fix_imports` 的全量 rglob 遍历，优先检查常见路径（`src/`, `lib/`, 当前目录）

### 文档更新
- **README.md**：添加性能优化说明章节，包括 RAG 单例化、LLM_TIMEOUT 配置、并发执行使用指南
- **README.md**：更新快速开始部分，新增并发执行命令示例
- **README.md**：更新配置说明表格，补充 LLM_TIMEOUT 和 LLM_RETRY_WAIT 配置项
- **README.md**：更新迭代优化记录，添加 v0.10 和 v0.9 变更记录
- **README.md**：更新测试状态表格，反映最新测试结果（696+ passed）
- **CHANGELOG.md**：添加多 LLM 配置支持说明
- **新增文档**：`docs/performance_optimization_report.md`、`docs/report_generator_guide.md`、`API_MANAGER_EXTENSION_GUIDE.md`
- **迭代报告**：`ITERATION_REPORT_20260818.md`、`FINAL_ITERATION_SUMMARY.md`、`ITERATION_REPORT_ROUND2.md`
- **架构文档**：更新 `docs/algorithm_design.md`，反映 RAG 单例化改动

## [0.2.0] - 2026-08-17

### 工程化改进
- **Ruff Lint 配置**：新增 `pyproject.toml`，配置 ruff 进行代码检查和格式化
- **Pre-commit Hooks**：新增 `.pre-commit-config.yaml`，集成 ruff、mypy、trailing-whitespace 等检查
- **GitHub Actions CI**：新增 `.github/workflows/ci.yml`，支持多 Python 版本测试、lint 检查和安全扫描
- **pytest 配置**：在 `pyproject.toml` 中配置 pytest 参数（测试路径、标记、输出格式）

### 文档更新
- **README.md**：更新测试状态表格，集成测试已标记为通过（52 passed）
- **README.md**：新增「开发工具」章节，包含 Ruff lint、Pre-commit hooks、CI/CD、测试命令说明
- **CHANGELOG.md**：按 Keep a Changelog 格式规范更新

### 测试状态
- 单元测试：215 passed（含集成测试）
- 无硬编码密钥
- 代码覆盖率 75%（目标 80%+）

---

## [0.1.0] - 2026-08-14

### 新增
- 初始版本发布
- 四智能体协作架构（Planner → Generator → Executor → Debugger）
- 支持 examples、synthetic、swe_bench 三种数据集
- Docker 一键复现支持
- 完整单元测试（185 个用例，17 个测试文件）

---

## 版本说明

- `Unreleased`: 当前开发中功能，尚未正式发布
- 版本号遵循 [语义化版本 2.0.0](https://semver.org/lang/zh-CN/)
