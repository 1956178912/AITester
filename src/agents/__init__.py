"""
多智能体模块包。

包含四个核心智能体：
    - PlannerAgent: 测试规划师，输出逻辑驱动的结构化测试计划
    - GeneratorAgent: 测试生成器，根据计划生成测试代码
    - ExecutorAgent: 执行器，运行测试并收集覆盖率与结果
    - DebuggerAgent: 调试器，对失败测试进行根因分析与修复

另有 ErrorClassifier: 错误分类器，将失败原因分为五类以便分层修复。
"""
