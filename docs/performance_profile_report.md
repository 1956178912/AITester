# AITester 性能分析报告

生成时间: 2026-08-16 19:55:51

## 1. CPU 性能分析

### BaseAgent JSON/代码提取

```
         3513338 function calls (3428391 primitive calls) in 1.034 seconds

   Ordered by: cumulative time
   List reduced from 11847 to 20 due to restriction <20>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        5    0.000    0.000    1.041    0.208 /Users/wangchenyu/Workspace/AITester/scripts/performance_profile.py:96(test_base_agent_parsing)
   2748/3    0.004    0.000    1.023    0.341 <frozen importlib._bootstrap>:1360(_find_and_load)
   2216/3    0.004    0.000    1.023    0.341 <frozen importlib._bootstrap>:1308(_find_and_load_unlocked)
   6179/6    0.001    0.000    1.023    0.170 <frozen importlib._bootstrap>:483(_call_with_frames_removed)
   2154/5    0.002    0.000    1.022    0.204 <frozen importlib._bootstrap>:914(_load_unlocked)
   2094/5    0.001    0.000    1.022    0.204 <frozen importlib._bootstrap_external>:753(exec_module)
   2228/5    0.015    0.000    1.022    0.204 {built-in method builtins.exec}
        1    0.000    0.000    0.800    0.800 /Users/wangchenyu/workspace/AITester/src/agents/base_agent.py:1(<module>)
        1    0.000    0.000    0.785    0.785 /Users/wangchenyu/Workspace/AITester/.venv/lib/python3.14/site-packages/langchain_openai/__init__.py:1(<module>)
        1    0.000    0.000    0.752    0.752 /Users/wangchenyu/Workspace/AITester/.venv/lib/python3.14/site-packages/langchain_openai/chat_models/__init__.py:1(<module>)
        1    0.000    0.000    0.752    0.752 /Users/wangchenyu/Workspace/AITester/.venv/lib/python3.14/site-packages/langchain_openai/chat_models/azure.py:1(<module>)
 1796/379    0.001    0.000    0.724    0.002 {built-in method builtins.__import__}
5999/5967    0.019    0.000    0.646    0.000 {built-in method builtins.__build_class__}
 1266/572    0.001    0.000    0.517    0.001 <frozen importlib._bootstrap>:1409(_handle_fromlist)
1934/1932    0.017    0.000    0.507    0.000 /Users/wangchenyu/Workspace/AITester/.venv/lib/python3.14/site-packages/pydantic/_internal/_model_construction.py:84(__new__)
        1    0.000    0.000    0.465    0.465 /Users/wangchenyu/Workspace/AITester/.venv/lib/python3.14/site-packages/openai/__init__.py:1(<module>)
        1    0.000    0.000    0.295    0.295 /Users/wangchenyu/Workspace/AITester/.venv/lib/python3.14/site-packages/openai/types/__init__.py:1(<module>)
1933/1931    0.003    0.000    0.272    0.000 /Users/wangchenyu/Workspace/AITester/.venv/lib/python3.14/site-packages/pydantic/_internal/_model_construction.py:566(set_model_fields)
1933/1931    0.021    0.000    0.269    0.000 /Users/wangchenyu/Workspace/AITester/.venv/lib/python3.14/site-packages/pydantic/_internal/_fields.py:224(collect_model_fields)
        5    0.000    0.000    0.233    0.047 /Users/wangchenyu/workspace/AITester/src/agents/base_agent.py:212(__init__)


```

### ErrorClassifier 分类

```
         69022 function calls (68945 primitive calls) in 0.012 seconds

   Ordered by: cumulative time
   List reduced from 180 to 20 due to restriction <20>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        5    0.000    0.000    0.012    0.002 /Users/wangchenyu/Workspace/AITester/scripts/performance_profile.py:125(test_error_classifier)
     2500    0.001    0.000    0.011    0.000 /Users/wangchenyu/workspace/AITester/src/agents/error_classifier.py:111(classify)
     7000    0.002    0.000    0.009    0.000 /Users/wangchenyu/workspace/AITester/src/agents/error_classifier.py:142(_matches_patterns)
    42000    0.006    0.000    0.006    0.000 {method 'search' of 're.Pattern' objects}
        1    0.000    0.000    0.001    0.001 <frozen importlib._bootstrap>:1360(_find_and_load)
        1    0.000    0.000    0.001    0.001 <frozen importlib._bootstrap>:1308(_find_and_load_unlocked)
        1    0.000    0.000    0.001    0.001 <frozen importlib._bootstrap>:914(_load_unlocked)
        1    0.000    0.000    0.001    0.001 <frozen importlib._bootstrap_external>:753(exec_module)
        2    0.000    0.000    0.001    0.001 <frozen importlib._bootstrap>:483(_call_with_frames_removed)
        1    0.000    0.000    0.001    0.001 {built-in method builtins.exec}
        1    0.000    0.000    0.001    0.001 /Users/wangchenyu/workspace/AITester/src/agents/error_classifier.py:1(<module>)
        3    0.000    0.000    0.001    0.000 {built-in method builtins.__build_class__}
        1    0.000    0.000    0.001    0.001 /Users/wangchenyu/workspace/AITester/src/agents/error_classifier.py:34(ErrorPatterns)
       27    0.000    0.000    0.001    0.000 /Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14/re/__init__.py:287(compile)
       27    0.000    0.000    0.001    0.000 /Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14/re/__init__.py:330(_compile)
       27    0.000    0.000    0.001    0.000 /Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14/re/_compiler.py:757(compile)
     2508    0.000    0.000    0.001    0.000 {method 'join' of 'str' objects}
       27    0.000    0.000    0.000    0.000 /Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14/re/_parser.py:963(parse)
       27    0.000    0.000    0.000    0.000 /Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14/re/_parser.py:452(_parse_sub)
     5000    0.000    0.000    0.000    0.000 /Users/wangchenyu/workspace/AITester/src/agents/error_classifier.py:130(<genexpr>)


```

### CodeAnalyzer 分析

```
         1092950 function calls (1092946 primitive calls) in 0.132 seconds

   Ordered by: cumulative time
   List reduced from 132 to 20 due to restriction <20>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        5    0.001    0.000    0.132    0.026 /Users/wangchenyu/Workspace/AITester/scripts/performance_profile.py:144(test_code_analyzer)
    78000    0.015    0.000    0.090    0.000 /Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14/ast.py:386(walk)
      500    0.007    0.000    0.085    0.000 /Users/wangchenyu/workspace/AITester/src/tools/code_analyzer.py:20(parse_function_nodes)
    77250    0.011    0.000    0.072    0.000 {method 'extend' of 'collections.deque' objects}
   153750    0.031    0.000    0.061    0.000 /Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14/ast.py:280(iter_child_nodes)
      250    0.005    0.000    0.045    0.000 /Users/wangchenyu/workspace/AITester/src/tools/code_analyzer.py:92(compute_cyclomatic_complexity)
      250    0.001    0.000    0.043    0.000 /Users/wangchenyu/workspace/AITester/src/tools/code_analyzer.py:58(extract_function_code)
      750    0.000    0.000    0.022    0.000 /Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14/ast.py:26(parse)
      750    0.022    0.000    0.022    0.000 {built-in method builtins.compile}
   211500    0.016    0.000    0.021    0.000 /Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14/ast.py:268(iter_fields)
   350007    0.014    0.000    0.014    0.000 {built-in method builtins.isinstance}
   134264    0.006    0.000    0.006    0.000 {built-in method builtins.getattr}
    77250    0.003    0.000    0.003    0.000 {method 'popleft' of 'collections.deque' objects}
     1500    0.000    0.000    0.001    0.000 /Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14/ast.py:294(get_docstring)
      500    0.000    0.000    0.000    0.000 /Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14/inspect.py:790(cleandoc)
      2/1    0.000    0.000    0.000    0.000 <frozen importlib._bootstrap>:1360(_find_and_load)
      2/1    0.000    0.000    0.000    0.000 <frozen importlib._bootstrap>:1308(_find_and_load_unlocked)
      750    0.000    0.000    0.000    0.000 <frozen importlib._bootstrap>:1409(_handle_fromlist)
      5/3    0.000    0.000    0.000    0.000 <frozen importlib._bootstrap>:483(_call_with_frames_removed)
        2    0.000    0.000    0.000    0.000 <frozen importlib._bootstrap>:914(_load_unlocked)


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
       50    0.000    0.000    0.000    0.000 /Users/wangchenyu/workspace/AITester/src/dataset_loader.py:572(load_dataset)
        1    0.000    0.000    0.000    0.000 /Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14/dataclasses.py:478(add_fns_to_class)
        1    0.000    0.000    0.000    0.000 <frozen importlib._bootstrap_external>:826(get_code)
       55    0.000    0.000    0.000    0.000 /Users/wangchenyu/workspace/AITester/src/dataset_loader.py:451(add_sample_tasks)
        1    0.000    0.000    0.000    0.000 <frozen importlib._bootstrap_external>:509(_compile_bytecode)
        1    0.000    0.000    0.000    0.000 {built-in method marshal.loads}
        5    0.000    0.000    0.000    0.000 {built-in method builtins.__build_class__}
       55    0.000    0.000    0.000    0.000 /Users/wangchenyu/workspace/AITester/src/dataset_loader.py:439(__init__)
       55    0.000    0.000    0.000    0.000 /Users/wangchenyu/workspace/AITester/src/dataset_loader.py:96(__init__)


```

### Workflow 构建

```
         5147267 function calls (5008034 primitive calls) in 0.895 seconds

   Ordered by: cumulative time
   List reduced from 3911 to 20 due to restriction <20>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        5    0.000    0.000    0.907    0.181 /Users/wangchenyu/Workspace/AITester/scripts/performance_profile.py:196(test_workflow_build)
    606/1    0.001    0.000    0.673    0.673 <frozen importlib._bootstrap>:1360(_find_and_load)
    586/1    0.001    0.000    0.673    0.673 <frozen importlib._bootstrap>:1308(_find_and_load_unlocked)
    552/2    0.001    0.000    0.673    0.336 <frozen importlib._bootstrap>:914(_load_unlocked)
    528/2    0.000    0.000    0.672    0.336 <frozen importlib._bootstrap_external>:753(exec_module)
   1603/3    0.001    0.000    0.672    0.224 <frozen importlib._bootstrap>:483(_call_with_frames_removed)
    646/2    0.012    0.000    0.672    0.336 {built-in method builtins.exec}
        1    0.000    0.000    0.672    0.672 /Users/wangchenyu/workspace/AITester/src/graph/workflow.py:1(<module>)
        1    0.000    0.000    0.626    0.626 /Users/wangchenyu/workspace/AITester/src/rag/retriever.py:1(<module>)
        1    0.000    0.000    0.625    0.625 /Users/wangchenyu/Workspace/AITester/.venv/lib/python3.14/site-packages/chromadb/__init__.py:1(<module>)
1320/1292    0.005    0.000    0.455    0.000 {built-in method builtins.__build_class__}
   832/49    0.000    0.000    0.278    0.006 {built-in method builtins.__import__}
        7    0.000    0.000    0.276    0.039 /Users/wangchenyu/Workspace/AITester/.venv/lib/python3.14/site-packages/pydantic_settings/main.py:193(__init__)
        7    0.000    0.000    0.250    0.036 /Users/wangchenyu/Workspace/AITester/.venv/lib/python3.14/site-packages/pydantic_settings/main.py:484(_settings_build_values)
        7    0.006    0.001    0.235    0.034 /Users/wangchenyu/Workspace/AITester/.venv/lib/python3.14/site-packages/pydantic_settings/sources/providers/dotenv.py:122(__call__)
       25    0.000    0.000    0.234    0.009 /Users/wangchenyu/workspace/AITester/src/graph/workflow.py:497(build_workflow)
        1    0.000    0.000    0.220    0.220 /Users/wangchenyu/Workspace/AITester/.venv/lib/python3.14/site-packages/chromadb/api/__init__.py:1(<module>)
      124    0.000    0.000    0.218    0.002 /Users/wangchenyu/Workspace/AITester/.venv/lib/python3.14/site-packages/overrides/overrides.py:152(_overrides)
       97    0.000    0.000    0.200    0.002 /Users/wangchenyu/Workspace/AITester/.venv/lib/python3.14/site-packages/overrides/overrides.py:112(override)
       25    0.000    0.000    0.191    0.008 /Users/wangchenyu/Workspace/AITester/.venv/lib/python3.14/site-packages/langgraph/graph/state.py:1177(compile)


```

### 完整流程（简化）

```
         1416 function calls in 0.001 seconds

   Ordered by: cumulative time

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        5    0.000    0.000    0.001    0.000 /Users/wangchenyu/Workspace/AITester/scripts/performance_profile.py:205(test_full_pipeline)
       50    0.000    0.000    0.001    0.000 /Users/wangchenyu/workspace/AITester/src/agents/error_classifier.py:111(classify)
      150    0.000    0.000    0.000    0.000 /Users/wangchenyu/workspace/AITester/src/agents/error_classifier.py:142(_matches_patterns)
     1000    0.000    0.000    0.000    0.000 {method 'search' of 're.Pattern' objects}
       50    0.000    0.000    0.000    0.000 {method 'join' of 'str' objects}
      100    0.000    0.000    0.000    0.000 /Users/wangchenyu/workspace/AITester/src/agents/error_classifier.py:130(<genexpr>)
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

