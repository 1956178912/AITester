# Changelog

所有重要变更将记录在此文件中。格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

## [Unreleased]

### 新增
- 逻辑驱动思维链（PlannerAgent）
- 分层错误修复机制（DebuggerAgent + ErrorClassifier）
- AST 精确代码替换（替代正则匹配）
- RAG 检索增强生成（可选开关）
- 多基线对比与消融实验框架
- 合成数据集生成器（无需外部下载）
- 统计显著性检验（配对 t 检验 + Mann-Whitney U + Cohen's d）
- 完整中文注释：examples/、main.py、config.py、init_db.py、setup.py 逐行注释
- 完整单元测试：17 个测试文件共 185 个用例，覆盖全部核心模块

### 改进
- 优化 parametrize 校验逻辑，避免 LLM 反复生成错误参数
- 修复模块导入路径问题，增加 `_fix_import_module` 自动修正
- 补丁应用增加安全守卫（非空、≥10% 长度、含函数定义）

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
