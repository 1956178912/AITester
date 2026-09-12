# AITester 性能分析报告

生成时间: 2026-09-12 21:45:07

## 1. CPU 性能分析

### BaseAgent JSON/代码提取

```
         3542596 function calls (3457588 primitive calls) in 1.210 seconds

   Ordered by: cumulative time
   List reduced from 11903 to 20 due to restriction <20>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        5    0.000    0.000    1.219    0.244 /Users/wangchenyu/Workspace/AITester/scripts/performance_profile.py:94(test_base_agent_parsing)
   2753/3    0.004    0.000    1.206    0.402 <frozen importlib._bootstrap>:1360(_find_and_load)
   2221/3    0.005    0.000    1.206    0.402 <frozen importlib._bootstrap>:1308(_find_and_load_unlocked)
   6190/6    0.002    0.000    1.205    0.201 <frozen importlib._bootstrap>:483(_call_with_frames_removed)
   2159/5    0.002    0.000    1.205    0.241 <frozen importlib._bootstrap>:914(_load_unlocked)
   2098/5    0.002    0.000    1.205    0.241 <frozen importlib._bootstrap_external>:753(exec_module)
   2232/5    0.015    0.000    1.204    0.241 {built-in method builtins.exec}
        1    0.000    0.000    0.955    0.955 /Users/wangchenyu/Workspace/AITester/src/agents/base_agent.py:1(<module>)
        1    0.000    0.000    0.911    0.911 /Users/wangchenyu/Workspace/AITester/src/agents/llm_client.py:1(<module>)
        1    0.000    0.000    0.911    0.911 /Users/wangchenyu/Workspace/AITester/.venv/lib/python3.14/site-packages/langchain_openai/__init__.py:1(<module>)
        1    0.000    0.000    0.875    0.875 /Users/wangchenyu/Workspace/AITester/.venv/lib/python3.14/site-packages/langchain_openai/chat_models/__init__.py:1(<module>)
        1    0.000    0.000    0.874    0.874 /Users/wangchenyu/Workspace/AITester/.venv/lib/python3.14/site-packages/langchain_openai/chat_models/azure.py:1(<module>)
 1797/384    0.001    0.000    0.841    0.002 {built-in method builtins.__import__}
6037/6005    0.018    0.000    0.624    0.000 {built-in method builtins.__build_class__}
 1259/568    0.001    0.000    0.608    0.001 <frozen importlib._bootstrap>:1409(_handle_fromlist)
        1    0.000    0.000    0.555    0.555 /Users/wangchenyu/Workspace/AITester/.venv/lib/python3.14/site-packages/openai/__init__.py:1(<module>)
1934/1932    0.016    0.000    0.495    0.000 /Users/wangchenyu/Workspace/AITester/.venv/lib/python3.14/site-packages/pydantic/_internal/_model_construction.py:84(__new__)
        1    0.000    0.000    0.358    0.358 /Users/wangchenyu/Workspace/AITester/.venv/lib/python3.14/site-packages/openai/types/__init__.py:1(<module>)
     2098    0.005    0.000    0.302    0.000 <frozen importlib._bootstrap_external>:826(get_code)
1933/1931    0.002    0.000    0.260    0.000 /Users/wangchenyu/Workspace/AITester/.venv/lib/python3.14/site-packages/pydantic/_internal/_model_construction.py:566(set_model_fields)


```

### ErrorClassifier 分类

```
         142316 function calls (142111 primitive calls) in 0.025 seconds

   Ordered by: cumulative time
   List reduced from 239 to 20 due to restriction <20>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        5    0.000    0.000    0.025    0.005 /Users/wangchenyu/Workspace/AITester/scripts/performance_profile.py:123(test_error_classifier)
     2500    0.002    0.000    0.023    0.000 /Users/wangchenyu/Workspace/AITester/src/agents/error_classifier.py:203(classify)
    50000    0.010    0.000    0.010    0.000 {method 'search' of 're.Pattern' objects}
     2500    0.001    0.000    0.006    0.000 /Users/wangchenyu/Workspace/AITester/src/agents/error_classifier.py:394(_is_llm_format_error)
    17500    0.001    0.000    0.005    0.000 /Users/wangchenyu/Workspace/AITester/src/agents/error_classifier.py:401(<genexpr>)
     2500    0.002    0.000    0.005    0.000 /Users/wangchenyu/Workspace/AITester/src/agents/error_classifier.py:357(_is_syntax_error)
     1500    0.001    0.000    0.004    0.000 /Users/wangchenyu/Workspace/AITester/src/agents/error_classifier.py:433(_is_runtime_error)
    13500    0.001    0.000    0.003    0.000 /Users/wangchenyu/Workspace/AITester/src/agents/error_classifier.py:436(<genexpr>)
        1    0.000    0.000    0.002    0.002 <frozen importlib._bootstrap>:1360(_find_and_load)
        1    0.000    0.000    0.002    0.002 <frozen importlib._bootstrap>:1308(_find_and_load_unlocked)
        1    0.000    0.000    0.002    0.002 <frozen importlib._bootstrap>:914(_load_unlocked)
        1    0.000    0.000    0.002    0.002 <frozen importlib._bootstrap_external>:753(exec_module)
        2    0.000    0.000    0.002    0.001 <frozen importlib._bootstrap>:483(_call_with_frames_removed)
      2/1    0.000    0.000    0.002    0.002 {built-in method builtins.exec}
        1    0.000    0.000    0.002    0.002 /Users/wangchenyu/Workspace/AITester/src/agents/error_classifier.py:1(<module>)
       27    0.000    0.000    0.001    0.000 /Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14/re/__init__.py:287(compile)
       27    0.000    0.000    0.001    0.000 /Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14/re/__init__.py:330(_compile)
     1500    0.000    0.000    0.001    0.000 /Users/wangchenyu/Workspace/AITester/src/agents/error_classifier.py:438(_is_assertion_error)
       27    0.000    0.000    0.001    0.000 /Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14/re/_compiler.py:757(compile)
     2519    0.000    0.000    0.001    0.000 {method 'join' of 'str' objects}


```

### CodeAnalyzer 分析

```
         1092966 function calls (1092962 primitive calls) in 0.132 seconds

   Ordered by: cumulative time
   List reduced from 133 to 20 due to restriction <20>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        5    0.001    0.000    0.132    0.026 /Users/wangchenyu/Workspace/AITester/scripts/performance_profile.py:142(test_code_analyzer)
    78000    0.015    0.000    0.089    0.000 /Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14/ast.py:386(walk)
      500    0.007    0.000    0.085    0.000 /Users/wangchenyu/Workspace/AITester/src/tools/code_analyzer.py:20(parse_function_nodes)
    77250    0.011    0.000    0.071    0.000 {method 'extend' of 'collections.deque' objects}
   153750    0.030    0.000    0.060    0.000 /Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14/ast.py:280(iter_child_nodes)
      250    0.005    0.000    0.045    0.000 /Users/wangchenyu/Workspace/AITester/src/tools/code_analyzer.py:96(compute_cyclomatic_complexity)
      250    0.001    0.000    0.043    0.000 /Users/wangchenyu/Workspace/AITester/src/tools/code_analyzer.py:62(extract_function_code)
      750    0.000    0.000    0.021    0.000 /Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14/ast.py:26(parse)
      750    0.021    0.000    0.021    0.000 {built-in method builtins.compile}
   211500    0.015    0.000    0.021    0.000 /Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14/ast.py:268(iter_fields)
   350007    0.014    0.000    0.014    0.000 {built-in method builtins.isinstance}
   134264    0.006    0.000    0.006    0.000 {built-in method builtins.getattr}
    77250    0.003    0.000    0.003    0.000 {method 'popleft' of 'collections.deque' objects}
     1500    0.000    0.000    0.001    0.000 /Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14/ast.py:294(get_docstring)
      2/1    0.000    0.000    0.001    0.001 <frozen importlib._bootstrap>:1360(_find_and_load)
      2/1    0.000    0.000    0.001    0.001 <frozen importlib._bootstrap>:1308(_find_and_load_unlocked)
      500    0.000    0.000    0.000    0.000 /Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14/inspect.py:790(cleandoc)
        2    0.000    0.000    0.000    0.000 <frozen importlib._bootstrap>:914(_load_unlocked)
        2    0.000    0.000    0.000    0.000 <frozen importlib._bootstrap_external>:753(exec_module)
        2    0.000    0.000    0.000    0.000 <frozen importlib._bootstrap_external>:826(get_code)


```

### DatasetLoader 加载

```
         783077 function calls (764232 primitive calls) in 0.538 seconds

   Ordered by: cumulative time
   List reduced from 4650 to 20 due to restriction <20>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        5    0.000    0.000    0.539    0.108 /Users/wangchenyu/Workspace/AITester/scripts/performance_profile.py:176(test_dataset_loader)
    911/1    0.001    0.000    0.538    0.538 <frozen importlib._bootstrap>:1360(_find_and_load)
    849/1    0.002    0.000    0.538    0.538 <frozen importlib._bootstrap>:1308(_find_and_load_unlocked)
   2409/1    0.002    0.000    0.538    0.538 <frozen importlib._bootstrap>:483(_call_with_frames_removed)
    996/1    0.000    0.000    0.538    0.538 {built-in method builtins.__import__}
    821/1    0.001    0.000    0.538    0.538 <frozen importlib._bootstrap>:914(_load_unlocked)
    729/1    0.001    0.000    0.538    0.538 <frozen importlib._bootstrap_external>:753(exec_module)
    899/1    0.020    0.000    0.536    0.536 {built-in method builtins.exec}
        1    0.000    0.000    0.536    0.536 /Users/wangchenyu/Workspace/AITester/src/datasets/__init__.py:1(<module>)
        1    0.000    0.000    0.533    0.533 /Users/wangchenyu/Workspace/AITester/src/datasets/dataset_loader.py:1(<module>)
        1    0.000    0.000    0.532    0.532 /Users/wangchenyu/Workspace/AITester/.venv/lib/python3.14/site-packages/datasets/__init__.py:1(<module>)
        1    0.000    0.000    0.505    0.505 /Users/wangchenyu/Workspace/AITester/.venv/lib/python3.14/site-packages/datasets/arrow_dataset.py:1(<module>)
        1    0.000    0.000    0.249    0.249 /Users/wangchenyu/Workspace/AITester/.venv/lib/python3.14/site-packages/pandas/__init__.py:1(<module>)
 1113/591    0.001    0.000    0.235    0.000 <frozen importlib._bootstrap>:1409(_handle_fromlist)
      729    0.002    0.000    0.187    0.000 <frozen importlib._bootstrap_external>:826(get_code)
        1    0.000    0.000    0.147    0.147 /Users/wangchenyu/Workspace/AITester/.venv/lib/python3.14/site-packages/pandas/core/api.py:1(<module>)
      821    0.001    0.000    0.122    0.000 <frozen importlib._bootstrap>:809(module_from_spec)
       89    0.000    0.000    0.116    0.001 <frozen importlib._bootstrap_external>:1051(create_module)
       89    0.116    0.001    0.116    0.001 {built-in method _imp.create_dynamic}
      729    0.001    0.000    0.108    0.000 <frozen importlib._bootstrap_external>:947(get_data)


```

### Workflow 构建

```
         5770824 function calls (5605151 primitive calls) in 0.993 seconds

   Ordered by: cumulative time
   List reduced from 3414 to 20 due to restriction <20>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        5    0.000    0.000    1.006    0.201 /Users/wangchenyu/Workspace/AITester/scripts/performance_profile.py:193(test_workflow_build)
    504/1    0.001    0.000    0.668    0.668 <frozen importlib._bootstrap>:1360(_find_and_load)
    484/1    0.001    0.000    0.668    0.668 <frozen importlib._bootstrap>:1308(_find_and_load_unlocked)
    452/2    0.001    0.000    0.668    0.334 <frozen importlib._bootstrap>:914(_load_unlocked)
    432/2    0.000    0.000    0.668    0.334 <frozen importlib._bootstrap_external>:753(exec_module)
   1255/3    0.000    0.000    0.668    0.223 <frozen importlib._bootstrap>:483(_call_with_frames_removed)
    553/2    0.011    0.000    0.668    0.334 {built-in method builtins.exec}
        1    0.000    0.000    0.668    0.668 /Users/wangchenyu/Workspace/AITester/src/graph/workflow.py:1(<module>)
        1    0.000    0.000    0.599    0.599 /Users/wangchenyu/Workspace/AITester/src/rag/retriever.py:1(<module>)
        1    0.000    0.000    0.599    0.599 /Users/wangchenyu/Workspace/AITester/.venv/lib/python3.14/site-packages/chromadb/__init__.py:1(<module>)
1133/1108    0.004    0.000    0.423    0.000 {built-in method builtins.__build_class__}
       25    0.000    0.000    0.338    0.014 /Users/wangchenyu/Workspace/AITester/src/graph/workflow.py:1053(build_workflow)
        7    0.000    0.000    0.287    0.041 /Users/wangchenyu/Workspace/AITester/.venv/lib/python3.14/site-packages/pydantic_settings/main.py:193(__init__)
       25    0.000    0.000    0.285    0.011 /Users/wangchenyu/Workspace/AITester/.venv/lib/python3.14/site-packages/langgraph/graph/state.py:1177(compile)
      150    0.001    0.000    0.279    0.002 /Users/wangchenyu/Workspace/AITester/.venv/lib/python3.14/site-packages/langgraph/graph/state.py:1444(attach_node)
      150    0.000    0.000    0.274    0.002 /Users/wangchenyu/Workspace/AITester/.venv/lib/python3.14/site-packages/langgraph/pregel/_read.py:153(__init__)
      125    0.002    0.000    0.274    0.002 /Users/wangchenyu/Workspace/AITester/.venv/lib/python3.14/site-packages/langgraph/pregel/_utils.py:47(find_subgraph_pregel)
      125    0.002    0.000    0.269    0.002 /Users/wangchenyu/Workspace/AITester/.venv/lib/python3.14/site-packages/langgraph/pregel/_utils.py:140(get_function_nonlocals)
        7    0.000    0.000    0.251    0.036 /Users/wangchenyu/Workspace/AITester/.venv/lib/python3.14/site-packages/pydantic_settings/main.py:484(_settings_build_values)
   341/50    0.000    0.000    0.243    0.005 {built-in method builtins.__import__}


```

### 完整流程（简化）

```
         3016 function calls in 0.001 seconds

   Ordered by: cumulative time

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        5    0.000    0.000    0.001    0.000 /Users/wangchenyu/Workspace/AITester/scripts/performance_profile.py:202(test_full_pipeline)
       50    0.000    0.000    0.001    0.000 /Users/wangchenyu/Workspace/AITester/src/agents/error_classifier.py:203(classify)
     1150    0.001    0.000    0.001    0.000 {method 'search' of 're.Pattern' objects}
       50    0.000    0.000    0.000    0.000 /Users/wangchenyu/Workspace/AITester/src/agents/error_classifier.py:394(_is_llm_format_error)
      350    0.000    0.000    0.000    0.000 /Users/wangchenyu/Workspace/AITester/src/agents/error_classifier.py:401(<genexpr>)
       50    0.000    0.000    0.000    0.000 /Users/wangchenyu/Workspace/AITester/src/agents/error_classifier.py:357(_is_syntax_error)
       50    0.000    0.000    0.000    0.000 /Users/wangchenyu/Workspace/AITester/src/agents/error_classifier.py:433(_is_runtime_error)
      450    0.000    0.000    0.000    0.000 /Users/wangchenyu/Workspace/AITester/src/agents/error_classifier.py:436(<genexpr>)
       50    0.000    0.000    0.000    0.000 /Users/wangchenyu/Workspace/AITester/src/agents/error_classifier.py:386(_is_index_error)
       50    0.000    0.000    0.000    0.000 /Users/wangchenyu/Workspace/AITester/src/agents/error_classifier.py:374(_is_import_error)
       50    0.000    0.000    0.000    0.000 /Users/wangchenyu/Workspace/AITester/src/agents/error_classifier.py:438(_is_assertion_error)
       50    0.000    0.000    0.000    0.000 /Users/wangchenyu/Workspace/AITester/src/agents/error_classifier.py:381(_is_type_error)
      100    0.000    0.000    0.000    0.000 /Users/wangchenyu/Workspace/AITester/src/agents/error_classifier.py:441(<genexpr>)
       50    0.000    0.000    0.000    0.000 {method 'join' of 'str' objects}
      350    0.000    0.000    0.000    0.000 /Users/wangchenyu/Workspace/AITester/src/agents/error_classifier.py:364(<genexpr>)
      100    0.000    0.000    0.000    0.000 /Users/wangchenyu/Workspace/AITester/src/agents/error_classifier.py:235(<genexpr>)
        1    0.000    0.000    0.000    0.000 {method 'disable' of '_lsprof.Profiler' objects}
       50    0.000    0.000    0.000    0.000 {method 'get' of 'dict' objects}
        5    0.000    0.000    0.000    0.000 /Users/wangchenyu/Workspace/AITester/src/agents/executor.py:143(__init__)
        5    0.000    0.000    0.000    0.000 {method 'append' of 'list' objects}


```

## 2. 内存性能分析

### BaseAgent 解析

- 当前内存: 0.00 MB
- 峰值内存: 0.00 MB
- 内存增量: 0.00 MB

### ErrorClassifier

- 当前内存: 0.00 MB
- 峰值内存: 0.00 MB
- 内存增量: 0.00 MB

### DatasetLoader

- 当前内存: 0.00 MB
- 峰值内存: 0.00 MB
- 内存增量: 0.00 MB

## 3. 性能分析结论（基于实测数据）

> 本节依据上方 cProfile 实测数据归纳，取代脚本原先的模板化结论。

### 3.1 运行时逻辑高效，无 CPU 热点

- ErrorClassifier 分类：2500 次调用仅 0.025s（单次约 10μs），正则已预编译
  （`re.Pattern.search` 而非每次 `re.compile`），不存在"重复编译"开销
- CodeAnalyzer AST 分析：50 次循环 0.132s，`ast.walk`/`iter_child_nodes`
  属 AST 遍历的正常开销，无优化空间
- BaseAgent JSON/代码提取：解析逻辑近乎零开销，耗时全部来自模块首次 import

### 3.2 主要开销是第三方库 import（固有成本）

| 库 | 耗时 | 触发链 |
|----|------|--------|
| chromadb | ~0.6s | import workflow → retriever → chromadb |
| pandas + datasets | ~0.53s | import dataset_loader → datasets → pandas |
| openai + pydantic | ~0.9s | import base_agent/llm_client → langchain_openai → openai |

这些库均为项目核心依赖（RAG / 数据集 / LLM 调用），import 成本属固有开销，
无法通过代码重构消除。

### 3.3 可优化点评估（收益/风险）

- **延迟导入 chromadb**：仅对"未启用 RAG 的场景"省 ~0.6s 启动。但需改动
  workflow 多个节点函数的 RAG 可用性检查，风险高、收益有限，本轮评估后
  不实施（见 OPTIMIZATION_REPORT）。
- **延迟导入 datasets/pandas**：同理，仅对"不加载数据集"的路径有效。

### 3.4 内存

实测 tracemalloc 显示三个被测模块的内存增量均 < 0.01 MB，
内存使用无异常，无需专项优化。

## 4. 结论

本次分析（2026-09-12 实测）确认：

- 运行时逻辑高效，**无 CPU 热点、无内存泄漏**
- 主要耗时来自第三方库 import（chromadb / pandas / openai），属固有成本
- 结论：项目当前**无低垂果实式的性能优化点**，性能方向以保持现状为主

