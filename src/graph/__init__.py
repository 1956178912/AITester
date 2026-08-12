"""
工作流图模块包。

基于 LangGraph 的状态机定义，编排多智能体协作流程：
    Planner -> Generator -> Executor -> (Debugger -> Generator) * N -> END
"""
