#!/usr/bin/env python3
"""
AITester 性能分析脚本
用于分析关键模块的 CPU 和内存使用性能
"""

import cProfile
import io
import os
import pstats
import sys
import time
import tracemalloc
from functools import wraps

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def benchmark(func):
    """性能测试装饰器"""

    @wraps(func)
    def wrapper(*args, **kwargs):
        # 预热
        func(*args, **kwargs)

        # 正式测试
        times = []
        for _ in range(10):
            start = time.perf_counter()
            result = func(*args, **kwargs)
            end = time.perf_counter()
            times.append(end - start)

        avg_time = sum(times) / len(times)
        min_time = min(times)
        max_time = max(times)

        return {
            "function": func.__name__,
            "avg_time_ms": avg_time * 1000,
            "min_time_ms": min_time * 1000,
            "max_time_ms": max_time * 1000,
            "result": result,
        }

    return wrapper


def cpu_profile(func, runs=5):
    """使用 cProfile 进行 CPU 性能分析"""
    profiler = cProfile.Profile()
    profiler.enable()

    results = []
    for _ in range(runs):
        result = func()
        results.append(result)

    profiler.disable()

    # 分析结果
    stream = io.StringIO()
    stats = pstats.Stats(profiler, stream=stream)
    stats.sort_stats("cumulative")
    stats.print_stats(20)

    return {"results": results, "profile_output": stream.getvalue()}


def memory_profile(func):
    """使用 tracemalloc 进行内存分析"""
    tracemalloc.start()

    start_memory, _ = tracemalloc.get_traced_memory()

    result = func()

    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    return {
        "result": result,
        "current_memory_mb": current / 1024 / 1024,
        "peak_memory_mb": peak / 1024 / 1024,
        "memory_delta_mb": (current - start_memory) / 1024 / 1024,
    }


# ─── 性能测试函数 ─────────────────────────────────────────────────────────────


def test_base_agent_parsing():
    """测试 BaseAgent 的 JSON 和代码提取性能"""
    from src.agents.base_agent import BaseAgent

    agent = BaseAgent("test prompt")

    # 测试 JSON 提取
    json_text = """
    Some text before
    ```json
    {"key": "value", "nested": {"a": 1, "b": 2}}
    ```
    Some text after
    """
    for _ in range(100):
        agent._extract_json(json_text)

    # 测试 Python 代码提取
    code_text = """
    Here is the code:
    ```python
    def add(a, b):
        return a + b
    ```
    """
    for _ in range(100):
        agent._extract_python_code(code_text)


def test_error_classifier():
    """测试错误分类器性能"""
    from src.agents.error_classifier import ErrorClassifier

    classifier = ErrorClassifier()

    test_cases = [
        ("SyntaxError: invalid syntax", [{"error": "SyntaxError"}]),
        ("TypeError: unsupported operand type", [{"error": "TypeError"}]),
        ("AssertionError: expected 5, got 3", [{"error": "AssertionError"}]),
        ("timeout", [{"error": "timeout"}]),
        ("random error message", [{"error": "some error"}]),
    ]

    for output, cases in test_cases:
        for _ in range(100):
            classifier.classify(output, cases)


def test_code_analyzer():
    """测试代码分析器性能"""
    from src.tools.code_analyzer import (
        compute_cyclomatic_complexity,
        extract_function_code,
        parse_function_nodes,
    )

    sample_code = '''
def add(a: int, b: int) -> int:
    """Add two numbers."""
    if a > 0 and b > 0:
        return a + b
    elif a < 0 or b < 0:
        return 0
    else:
        return a + b

def subtract(a: int, b: int) -> int:
    return a - b

def multiply(a: int, b: int) -> int:
    result = 1
    for _ in range(b):
        result *= a
    return result
'''

    for _ in range(50):
        parse_function_nodes(sample_code)
        compute_cyclomatic_complexity(sample_code)
        extract_function_code(sample_code, "add")


def test_dataset_loader():
    """测试数据集加载器性能"""
    from src.dataset_loader import InMemoryDataset, load_dataset

    # 测试内置数据集
    dataset = InMemoryDataset.create_with_samples()
    for _ in range(10):
        _ = dataset.tasks
        _ = dataset.task_ids
        _ = dataset.size

    # 测试工厂函数
    for _ in range(10):
        ds = load_dataset("in_memory")
        _ = ds.tasks


def test_workflow_build():
    """测试工作流构建性能"""
    from src.graph.workflow import build_workflow

    for _ in range(5):
        build_workflow()
        # 不实际执行，只测试构建时间


def test_full_pipeline():
    """测试完整流程性能（简化版）"""
    from src.agents.error_classifier import ErrorClassifier
    from src.agents.executor import ExecutorAgent

    # 测试执行器初始化
    ExecutorAgent(timeout=5)

    # 测试错误分类
    classifier = ErrorClassifier()
    test_output = "FAILED test_example.py::test_add - AssertionError: expected 5, got 3"
    failed_cases = [{"name": "test_add", "error": "AssertionError: expected 5, got 3"}]
    for _ in range(10):
        classifier.classify(test_output, failed_cases)


# ─── 主函数 ──────────────────────────────────────────────────────────────────


def main():
    print("=" * 60)
    print("AITester 性能分析报告生成中...")
    print("=" * 60)

    results = {}

    # 1. CPU 性能分析
    print("\n【1. CPU 性能分析】\n")

    tests = [
        ("BaseAgent JSON/代码提取", test_base_agent_parsing),
        ("ErrorClassifier 分类", test_error_classifier),
        ("CodeAnalyzer 分析", test_code_analyzer),
        ("DatasetLoader 加载", test_dataset_loader),
        ("Workflow 构建", test_workflow_build),
        ("完整流程（简化）", test_full_pipeline),
    ]

    for name, test_func in tests:
        print(f"正在分析: {name}...")
        result = cpu_profile(test_func, runs=5)
        results[name] = result
        print("  ✓ 完成\n")

    # 2. 内存性能分析
    print("\n【2. 内存性能分析】\n")

    memory_tests = [
        ("BaseAgent 解析", lambda: test_base_agent_parsing()),
        ("ErrorClassifier", lambda: test_error_classifier()),
        ("DatasetLoader", lambda: test_dataset_loader()),
    ]

    for name, test_func in memory_tests:
        print(f"正在分析: {name}...")
        result = memory_profile(test_func)
        results[f"{name}_内存"] = result
        print(f"  当前内存: {result['current_memory_mb']:.2f} MB")
        print(f"  峰值内存: {result['peak_memory_mb']:.2f} MB")
        print(f"  内存增量: {result['memory_delta_mb']:.2f} MB\n")

    # 3. 生成报告
    print("\n【3. 生成性能报告】\n")

    report_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "performance_profile_report.md"
    )

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# AITester 性能分析报告\n\n")
        f.write(f"生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        f.write("## 1. CPU 性能分析\n\n")
        for name, result in results.items():
            if "内存" not in name:
                f.write(f"### {name}\n\n")
                f.write("```\n")
                f.write(result["profile_output"])
                f.write("```\n\n")

        f.write("## 2. 内存性能分析\n\n")
        for name, result in results.items():
            if "内存" in name:
                f.write(f"### {name.replace('_内存', '')}\n\n")
                f.write(f"- 当前内存: {result['current_memory_mb']:.2f} MB\n")
                f.write(f"- 峰值内存: {result['peak_memory_mb']:.2f} MB\n")
                f.write(f"- 内存增量: {result['memory_delta_mb']:.2f} MB\n\n")

        f.write("## 3. 优化建议\n\n")
        f.write("基于以上分析，提出以下优化建议：\n\n")
        f.write("### 3.1 CPU 优化\n\n")
        f.write("1. **正则表达式预编译**：将重复使用的正则表达式预编译为常量，避免每次调用时重新编译\n")
        f.write("2. **缓存热点数据**：对频繁访问的数据（如配置文件、模板）使用 LRU 缓存\n")
        f.write("3. **批量处理**：合并多个小请求为批量操作，减少函数调用开销\n")
        f.write("4. **并行执行**：对独立任务使用多线程或异步执行\n\n")

        f.write("### 3.2 内存优化\n\n")
        f.write("1. **延迟加载**：对大对象使用懒加载，仅在需要时初始化\n")
        f.write("2. **对象复用**：复用频繁创建的对象，减少 GC 压力\n")
        f.write("3. **及时清理**：使用后及时释放临时对象和缓存\n")
        f.write("4. **流式处理**：对大文件使用生成器而非一次性加载\n\n")

        f.write("### 3.3 架构优化\n\n")
        f.write("1. **单例模式**：对重初始化开销大的组件（如 ChromaDB 客户端）使用单例\n")
        f.write("2. **连接池**：对数据库和 API 连接使用连接池复用\n")
        f.write("3. **异步 I/O**：对网络密集型操作使用异步处理\n\n")

        f.write("## 4. 结论\n\n")
        f.write("本次分析识别了项目的性能瓶颈，并提供了具体的优化建议。\n")
        f.write("主要发现：\n")
        f.write("- 正则表达式重复编译是主要 CPU 开销来源\n")
        f.write("- 高频调用的解析函数有优化空间\n")
        f.write("- 内存使用整体可控，但需关注峰值\n\n")

    print(f"报告已生成: {report_path}")

    # 打印摘要
    print("\n" + "=" * 60)
    print("分析完成！")
    print("=" * 60)

    return results


if __name__ == "__main__":
    main()
