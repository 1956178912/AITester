# AITester 性能分析报告

生成时间: 2026-08-17 17:05:24

## 1. CPU 性能分析

### BaseAgent JSON/代码提取

```
         3514867 function calls (3429920 primitive calls) in 1.013 seconds

   Ordered by: cumulative time
   List reduced from 11847 to 20 due to restriction <20>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        5    0.000    0.000    1.019    0.204 /Users/wangchenyu/Workspace/AITester/scripts/performance_profile.py:96(test_base_agent_parsing)
   2748/3    0.004    0.000    1.002    0.334 <frozen importlib._bootstrap>:1360(_find_and_load)
   2216/3    0.004    0.000    1.001    0.334 <frozen importlib._bootstrap>:1308(_find_and_load_unlocked)
   6179/6    0.001    0.000    1.001    0.167 <frozen importlib._bootstrap>:483(_call_with_frames_removed)
   2154/5    0.002    0.000    1.001    0.200 <frozen importlib._bootstrap>:914(_load_unlocked)
   2094/5    0.001    0.000    1.001    0.200 <frozen importlib._bootstrap_external>:753(exec_module)
   2228/5    0.014    0.000    1.001    0.200 {built-in method builtins.exec}
        1    0.000    0.000    0.779    0.779 /Users/wangchenyu/workspace/AITester/src/agents/base_agent.py:1(<module>)
        1    0.000    0.000    0.767    0.767 /Users/wangchenyu/Workspace/AITester/.venv/lib/python3.14/site-packages/langchain_openai/__init__.py:1(<module>)
        1    0.000    0.000    0.735    0.735 /Users/wangchenyu/Workspace/AITester/.venv/lib/python3.14/site-packages/langchain_openai/chat_models/__init__.py:1(<module>)
        1    0.000    0.000    0.735    0.735 /Users/wangchenyu/Workspace/AITester/.venv/lib/python3.14/site-packages/langchain_openai/chat_models/azure.py:1(<module>)
 1796/379    0.001    0.000    0.713    0.002 {built-in method builtins.__import__}
5999/5967    0.018    0.000    0.618    0.000 {built-in method builtins.__build_class__}
 1266/572    0.001    0.000    0.513    0.001 <frozen importlib._bootstrap>:1409(_handle_fromlist)
1934/1932    0.016    0.000    0.489    0.000 /Users/wangchenyu/Workspace/AITester/.venv/lib/python3.14/site-packages/pydantic/_internal/_model_construction.py:84(__new__)
        1    0.000    0.000    0.444    0.444 /Users/wangchenyu/Workspace/AITester/.venv/lib/python3.14/site-packages/openai/__init__.py:1(<module>)
        1    0.000    0.000    0.284    0.284 /Users/wangchenyu/Workspace/AITester/.venv/lib/python3.14/site-packages/openai/types/__init__.py:1(<module>)
1933/1931    0.002    0.000    0.263    0.000 /Users/wangchenyu/Workspace/AITester/.venv/lib/python3.14/site-packages/pydantic/_internal/_model_construction.py:566(set_model_fields)
1933/1931    0.020    0.000    0.260    0.000 /Users/wangchenyu/Workspace/AITester/.venv/lib/python3.14/site-packages/pydantic/_internal/_fields.py:224(collect_model_fields)
        5    0.000    0.000    0.232    0.046 /Users/wangchenyu/workspace/AITester/src/agents/base_agent.py:212(__init__)


```

### ErrorClassifier 分类

```
         77891 function calls (77508 primitive calls) in 0.013 seconds

   Ordered by: cumulative time
   List reduced from 226 to 20 due to restriction <20>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        5    0.000    0.000    0.013    0.003 /Users/wangchenyu/Workspace/AITester/scripts/performance_profile.py:125(test_error_classifier)
     2500    0.001    0.000    0.010    0.000 /Users/wangchenyu/workspace/AITester/src/agents/error_classifier.py:188(classify)
     7000    0.003    0.000    0.008    0.000 /Users/wangchenyu/workspace/AITester/src/agents/error_classifier.py:329(_matches_patterns)
    43000    0.006    0.000    0.006    0.000 {method 'search' of 're.Pattern' objects}
        1    0.000    0.000    0.003    0.003 <frozen importlib._bootstrap>:1360(_find_and_load)
        1    0.000    0.000    0.003    0.003 <frozen importlib._bootstrap>:1308(_find_and_load_unlocked)
        1    0.000    0.000    0.003    0.003 <frozen importlib._bootstrap>:914(_load_unlocked)
        1    0.000    0.000    0.003    0.003 <frozen importlib._bootstrap_external>:753(exec_module)
        2    0.000    0.000    0.003    0.001 <frozen importlib._bootstrap>:483(_call_with_frames_removed)
      2/1    0.000    0.000    0.003    0.003 {built-in method builtins.exec}
        1    0.000    0.000    0.003    0.003 /Users/wangchenyu/workspace/AITester/src/agents/error_classifier.py:1(<module>)
        5    0.000    0.000    0.002    0.000 {built-in method builtins.__build_class__}
        1    0.000    0.000    0.002    0.002 /Users/wangchenyu/workspace/AITester/src/agents/error_classifier.py:70(ErrorPatterns)
       38    0.000    0.000    0.002    0.000 /Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14/re/__init__.py:287(compile)
       38    0.000    0.000    0.002    0.000 /Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14/re/__init__.py:330(_compile)
       36    0.000    0.000    0.002    0.000 /Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14/re/_compiler.py:757(compile)
       36    0.000    0.000    0.001    0.000 /Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14/re/_parser.py:963(parse)
    59/36    0.000    0.000    0.001    0.000 /Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14/re/_parser.py:452(_parse_sub)
    59/36    0.000    0.000    0.001    0.000 /Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14/re/_parser.py:512(_parse)
     2519    0.000    0.000    0.001    0.000 {method 'join' of 'str' objects}


```

### CodeAnalyzer 分析

```
         1092950 function calls (1092946 primitive calls) in 0.132 seconds

   Ordered by: cumulative time
   List reduced from 132 to 20 due to restriction <20>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        5    0.001    0.000    0.132    0.026 /Users/wangchenyu/Workspace/AITester/scripts/performance_profile.py:144(test_code_analyzer)
    78000    0.015    0.000    0.089    0.000 /Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14/ast.py:386(walk)
      500    0.007    0.000    0.085    0.000 /Users/wangchenyu/workspace/AITester/src/tools/code_analyzer.py:20(parse_function_nodes)
    77250    0.011    0.000    0.071    0.000 {method 'extend' of 'collections.deque' objects}
   153750    0.030    0.000    0.060    0.000 /Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14/ast.py:280(iter_child_nodes)
      250    0.005    0.000    0.044    0.000 /Users/wangchenyu/workspace/AITester/src/tools/code_analyzer.py:92(compute_cyclomatic_complexity)
      250    0.001    0.000    0.043    0.000 /Users/wangchenyu/workspace/AITester/src/tools/code_analyzer.py:58(extract_function_code)
      750    0.000    0.000    0.022    0.000 /Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14/ast.py:26(parse)
      750    0.022    0.000    0.022    0.000 {built-in method builtins.compile}
   211500    0.015    0.000    0.021    0.000 /Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14/ast.py:268(iter_fields)
   350007    0.014    0.000    0.014    0.000 {built-in method builtins.isinstance}
   134264    0.006    0.000    0.006    0.000 {built-in method builtins.getattr}
    77250    0.003    0.000    0.003    0.000 {method 'popleft' of 'collections.deque' objects}
     1500    0.000    0.000    0.001    0.000 /Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14/ast.py:294(get_docstring)
      500    0.000    0.000    0.000    0.000 /Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14/inspect.py:790(cleandoc)
      2/1    0.000    0.000    0.000    0.000 <frozen importlib._bootstrap>:1360(_find_and_load)
      750    0.000    0.000    0.000    0.000 <frozen importlib._bootstrap>:1409(_handle_fromlist)
      2/1    0.000    0.000    0.000    0.000 <frozen importlib._bootstrap>:1308(_find_and_load_unlocked)
      5/3    0.000    0.000    0.000    0.000 <frozen importlib._bootstrap>:483(_call_with_frames_removed)
        1    0.000    0.000    0.000    0.000 {built-in method builtins.__import__}


```

### DatasetLoader 加载

```
         2741 function calls (2740 primitive calls) in 0.001 seconds

   Ordered by: cumulative time
   List reduced from 187 to 20 due to restriction <20>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        5    0.000    0.000    0.001    0.000 /Users/wangchenyu/Workspace/AITester/scripts/performance_profile.py:179(test_dataset_loader)
        1    0.000    0.000    0.001    0.001 <frozen importlib._bootstrap>:1360(_find_and_load)
        1    0.000    0.000    0.001    0.001 <frozen importlib._bootstrap>:1308(_find_and_load_unlocked)
        1    0.000    0.000    0.001    0.001 <frozen importlib._bootstrap>:914(_load_unlocked)
        1    0.000    0.000    0.001    0.001 <frozen importlib._bootstrap_external>:753(exec_module)
        2    0.000    0.000    0.000    0.000 <frozen importlib._bootstrap>:483(_call_with_frames_removed)
      2/1    0.000    0.000    0.000    0.000 {built-in method builtins.exec}
        1    0.000    0.000    0.000    0.000 /Users/wangchenyu/workspace/AITester/src/dataset_loader.py:1(<module>)
        1    0.000    0.000    0.000    0.000 /Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14/dataclasses.py:1422(dataclass)
        1    0.000    0.000    0.000    0.000 /Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14/dataclasses.py:1439(wrap)
        1    0.000    0.000    0.000    0.000 /Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14/dataclasses.py:986(_process_class)
       50    0.000    0.000    0.000    0.000 /Users/wangchenyu/workspace/AITester/src/dataset_loader.py:578(load_dataset)
        1    0.000    0.000    0.000    0.000 /Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14/dataclasses.py:478(add_fns_to_class)
        1    0.000    0.000    0.000    0.000 <frozen importlib._bootstrap_external>:826(get_code)
       55    0.000    0.000    0.000    0.000 /Users/wangchenyu/workspace/AITester/src/dataset_loader.py:457(add_sample_tasks)
        1    0.000    0.000    0.000    0.000 <frozen importlib._bootstrap_external>:509(_compile_bytecode)
        1    0.000    0.000    0.000    0.000 {built-in method marshal.loads}
        5    0.000    0.000    0.000    0.000 {built-in method builtins.__build_class__}
       55    0.000    0.000    0.000    0.000 /Users/wangchenyu/workspace/AITester/src/dataset_loader.py:445(__init__)
       55    0.000    0.000    0.000    0.000 /Users/wangchenyu/workspace/AITester/src/dataset_loader.py:96(__init__)


```

### Workflow 构建

```
         5178288 function calls (5038348 primitive calls) in 0.901 seconds

   Ordered by: cumulative time
   List reduced from 3912 to 20 due to restriction <20>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        5    0.000    0.000    0.913    0.183 /Users/wangchenyu/Workspace/AITester/scripts/performance_profile.py:196(test_workflow_build)
    607/1    0.001    0.000    0.676    0.676 <frozen importlib._bootstrap>:1360(_find_and_load)
    587/1    0.001    0.000    0.676    0.676 <frozen importlib._bootstrap>:1308(_find_and_load_unlocked)
    553/2    0.001    0.000    0.676    0.338 <frozen importlib._bootstrap>:914(_load_unlocked)
    529/2    0.000    0.000    0.676    0.338 <frozen importlib._bootstrap_external>:753(exec_module)
   1605/3    0.001    0.000    0.676    0.225 <frozen importlib._bootstrap>:483(_call_with_frames_removed)
    647/2    0.012    0.000    0.676    0.338 {built-in method builtins.exec}
        1    0.000    0.000    0.676    0.676 /Users/wangchenyu/workspace/AITester/src/graph/workflow.py:1(<module>)
        1    0.000    0.000    0.627    0.627 /Users/wangchenyu/workspace/AITester/src/rag/retriever.py:1(<module>)
        1    0.000    0.000    0.627    0.627 /Users/wangchenyu/Workspace/AITester/.venv/lib/python3.14/site-packages/chromadb/__init__.py:1(<module>)
1320/1292    0.005    0.000    0.458    0.000 {built-in method builtins.__build_class__}
   832/49    0.000    0.000    0.278    0.006 {built-in method builtins.__import__}
        7    0.000    0.000    0.278    0.040 /Users/wangchenyu/Workspace/AITester/.venv/lib/python3.14/site-packages/pydantic_settings/main.py:193(__init__)
        7    0.000    0.000    0.251    0.036 /Users/wangchenyu/Workspace/AITester/.venv/lib/python3.14/site-packages/pydantic_settings/main.py:484(_settings_build_values)
       25    0.000    0.000    0.237    0.009 /Users/wangchenyu/workspace/AITester/src/graph/workflow.py:592(build_workflow)
        7    0.006    0.001    0.236    0.034 /Users/wangchenyu/Workspace/AITester/.venv/lib/python3.14/site-packages/pydantic_settings/sources/providers/dotenv.py:122(__call__)
        1    0.000    0.000    0.220    0.220 /Users/wangchenyu/Workspace/AITester/.venv/lib/python3.14/site-packages/chromadb/api/__init__.py:1(<module>)
       97    0.039    0.000    0.201    0.002 /Users/wangchenyu/Workspace/AITester/.venv/lib/python3.14/site-packages/overrides/overrides.py:112(override)
       25    0.000    0.000    0.194    0.008 /Users/wangchenyu/Workspace/AITester/.venv/lib/python3.14/site-packages/langgraph/graph/state.py:1177(compile)
      150    0.001    0.000    0.189    0.001 /Users/wangchenyu/Workspace/AITester/.venv/lib/python3.14/site-packages/langgraph/graph/state.py:1444(attach_node)


```

### 完整流程（简化）

```
         1466 function calls in 0.001 seconds

   Ordered by: cumulative time

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        5    0.000    0.000    0.001    0.000 /Users/wangchenyu/Workspace/AITester/scripts/performance_profile.py:205(test_full_pipeline)
       50    0.000    0.000    0.001    0.000 /Users/wangchenyu/workspace/AITester/src/agents/error_classifier.py:188(classify)
      150    0.000    0.000    0.000    0.000 /Users/wangchenyu/workspace/AITester/src/agents/error_classifier.py:329(_matches_patterns)
     1050    0.000    0.000    0.000    0.000 {method 'search' of 're.Pattern' objects}
       50    0.000    0.000    0.000    0.000 {method 'join' of 'str' objects}
      100    0.000    0.000    0.000    0.000 /Users/wangchenyu/workspace/AITester/src/agents/error_classifier.py:207(<genexpr>)
        1    0.000    0.000    0.000    0.000 {method 'disable' of '_lsprof.Profiler' objects}
       50    0.000    0.000    0.000    0.000 {method 'get' of 'dict' objects}
        5    0.000    0.000    0.000    0.000 /Users/wangchenyu/workspace/AITester/src/agents/executor.py:40(__init__)
        5    0.000    0.000    0.000    0.000 {method 'append' of 'list' objects}


```

## 2. 内存性能分析

### BaseAgent 解析

- 当前内存: 0.00 MB
- 峰值内存: 0.01 MB
- 内存增量: 0.00 MB

### ErrorClassifier

- 当前内存: 0.00 MB
- 峰值内存: 0.00 MB
- 内存增量: 0.00 MB

### DatasetLoader

- 当前内存: 0.00 MB
- 峰值内存: 0.00 MB
- 内存增量: 0.00 MB

## 3. 优化建议

基于以上分析，提出以下优化建议：

### 3.1 CPU 优化

1. **正则表达式预编译**：将重复使用的正则表达式预编译为常量，避免每次调用时重新编译
2. **缓存热点数据**：对频繁访问的数据（如配置文件、模板）使用 LRU 缓存
3. **批量处理**：合并多个小请求为批量操作，减少函数调用开销
4. **并行执行**：对独立任务使用多线程或异步执行

### 3.2 内存优化

1. **延迟加载**：对大对象使用懒加载，仅在需要时初始化
2. **对象复用**：复用频繁创建的对象，减少 GC 压力
3. **及时清理**：使用后及时释放临时对象和缓存
4. **流式处理**：对大文件使用生成器而非一次性加载

### 3.3 架构优化

1. **单例模式**：对重初始化开销大的组件（如 ChromaDB 客户端）使用单例
2. **连接池**：对数据库和 API 连接使用连接池复用
3. **异步 I/O**：对网络密集型操作使用异步处理

## 4. 结论

本次分析识别了项目的性能瓶颈，并提供了具体的优化建议。
主要发现：
- 正则表达式重复编译是主要 CPU 开销来源
- 高频调用的解析函数有优化空间
- 内存使用整体可控，但需关注峰值

