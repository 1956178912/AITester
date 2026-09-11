"""
工具函数模块包。

提供代码分析、AST 操作、补丁应用等底层工具，
供上层智能体调用。

模块:
    - code_analyzer: AST 复杂度分析与函数体精确替换
    - code_context: 基于 AST 的智能代码截取（焦点函数及其直接依赖）
    - dependency: 第三方依赖检测与缓存 venv 管理（执行隔离）
    - multi_candidate: 多候选补丁生成与验证筛选（3.1，默认关闭）
    - patch_applier: 补丁应用（完整文件 / 单函数两种模式）
"""
