#!/usr/bin/env python3
"""
性能基准测试脚本：测量 Executor 和 ErrorClassifier 的关键操作耗时。
用于对比优化前后的性能提升。
"""

import time
import sys
import os

# 确保项目根目录在路径中
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def benchmark_executor():
    """基准测试 Executor 性能"""
    from src.agents.executor import ExecutorAgent
    
    agent = ExecutorAgent(timeout=5)
    
    # 测试用例 1：简单的测试代码
    simple_test = """
import sys
sys.path.insert(0, '/tmp')

def test_add():
    assert 1 + 1 == 2
"""
    
    # 测试用例 2：带导入的测试代码
    import_test = """
import sys
sys.path.insert(0, '/tmp')

from calculator import add

def test_add():
    assert add(2, 3) == 5
"""
    
    # 测试用例 3：复杂导入路径
    complex_test = """
import sys
sys.path.insert(0, '/tmp')
sys.path.insert(0, '/tmp/src')

from utils.string_utils import is_palindrome
from utils.math_utils import compute_factorial

def test_palindrome():
    assert is_palindrome("racecar") == True

def test_factorial():
    assert compute_factorial(5) == 120
"""
    
    results = {}
    
    # 基准测试 _auto_fix_imports
    print("\n【Executor 性能测试】")
    print("-" * 40)
    
    for name, code in [("simple", simple_test), ("import", import_test), ("complex", complex_test)]:
        iterations = 100
        times = []
        for _ in range(iterations):
            start = time.perf_counter()
            result = agent._auto_fix_imports(code, "/tmp/test.py", PROJECT_ROOT)
            end = time.perf_counter()
            times.append(end - start)
        
        avg_ms = sum(times) / len(times) * 1000
        min_ms = min(times) * 1000
        max_ms = max(times) * 1000
        
        results[f"_auto_fix_imports_{name}"] = {
            "avg_ms": avg_ms,
            "min_ms": min_ms,
            "max_ms": max_ms,
            "iterations": iterations
        }
        
        print(f"  {name:10s}: avg={avg_ms:.2f}ms, min={min_ms:.2f}ms, max={max_ms:.2f}ms")
    
    return results


def benchmark_error_classifier():
    """基准测试 ErrorClassifier 性能"""
    from src.agents.error_classifier import ErrorClassifier, ErrorCategory
    
    classifier = ErrorClassifier()
    
    # 测试用例：各种错误类型
    test_cases = [
        ("syntax_import", "ModuleNotFoundError: No module named 'missing_module'", []),
        ("syntax_syntax", "SyntaxError: invalid syntax at line 10", []),
        ("runtime_type", "TypeError: unsupported operand type(s) for +: 'int' and 'str'", []),
        ("runtime_zero", "ZeroDivisionError: division by zero", []),
        ("assertion_fail", "AssertionError: expected 5, got 3", []),
        ("timeout", "Test ran for longer than 30 seconds", []),
        ("unknown", "Some unexpected error occurred", []),
    ]
    
    results = {}
    
    print("\n【ErrorClassifier 性能测试】")
    print("-" * 40)
    
    for name, output, cases in test_cases:
        iterations = 100
        times = []
        
        for _ in range(iterations):
            start = time.perf_counter()
            result = classifier.classify(output, cases)
            end = time.perf_counter()
            times.append(end - start)
        
        avg_ms = sum(times) / len(times) * 1000
        min_ms = min(times) * 1000
        max_ms = max(times) * 1000
        
        results[f"classify_{name}"] = {
            "avg_ms": avg_ms,
            "min_ms": min_ms,
            "max_ms": max_ms,
            "iterations": iterations
        }
        
        print(f"  {name:15s}: avg={avg_ms:.2f}ms, min={min_ms:.2f}ms, max={max_ms:.2f}ms")
    
    # 测试 extract_error_context
    print("\n【ErrorClassifier Context 提取性能】")
    print("-" * 40)
    
    test_output = "FAILED test_example.py::test_add - AssertionError: expected 5, got 3"
    failed_cases = [{"name": "test_add", "error": "AssertionError: expected 5, got 3"}]
    
    iterations = 100
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        result = classifier.extract_error_context(test_output, failed_cases)
        end = time.perf_counter()
        times.append(end - start)
    
    avg_ms = sum(times) / len(times) * 1000
    results["extract_context"] = {
        "avg_ms": avg_ms,
        "iterations": iterations
    }
    
    print(f"  extract_context   : avg={avg_ms:.2f}ms")
    
    return results


def benchmark_base_agent():
    """基准测试 BaseAgent 解析性能"""
    from src.agents.base_agent import BaseAgent
    
    agent = BaseAgent("test prompt")
    
    # JSON 提取测试
    json_text = '''
    Some text before
    ```json
    {"key": "value", "nested": {"a": 1, "b": 2}}
    ```
    Some text after
    '''
    
    # Python 代码提取测试
    code_text = '''
    Here is the code:
    ```python
    def add(a, b):
        return a + b
    ```
    '''
    
    results = {}
    
    print("\n【BaseAgent 解析性能测试】")
    print("-" * 40)
    
    # JSON 提取基准
    iterations = 100
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        result = agent._extract_json(json_text)
        end = time.perf_counter()
        times.append(end - start)
    
    avg_ms = sum(times) / len(times) * 1000
    results["extract_json"] = {"avg_ms": avg_ms, "iterations": iterations}
    print(f"  extract_json      : avg={avg_ms:.2f}ms")
    
    # Python 代码提取基准
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        result = agent._extract_python_code(code_text)
        end = time.perf_counter()
        times.append(end - start)
    
    avg_ms = sum(times) / len(times) * 1000
    results["extract_python_code"] = {"avg_ms": avg_ms, "iterations": iterations}
    print(f"  extract_python_code: avg={avg_ms:.2f}ms")
    
    return results


def main():
    print("=" * 60)
    print("AITester 性能基准测试")
    print("=" * 60)
    
    all_results = {}
    
    # 运行各项基准测试
    all_results["executor"] = benchmark_executor()
    all_results["error_classifier"] = benchmark_error_classifier()
    all_results["base_agent"] = benchmark_base_agent()
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("性能基准测试汇总")
    print("=" * 60)
    
    total_ops = 0
    total_time_ms = 0
    
    for category, metrics in all_results.items():
        print(f"\n[{category}]")
        for name, data in metrics.items():
            ops = data.get("iterations", 1)
            avg_ms = data.get("avg_ms", 0)
            total_ops += ops
            total_time_ms += avg_ms * ops / 1000
            print(f"  {name:20s}: {avg_ms:.2f}ms/op")
    
    print(f"\n总计: {total_ops} 次操作, 总耗时 {total_time_ms:.2f}s")
    print(f"平均每操作: {total_time_ms / total_ops * 1000:.3f}ms" if total_ops > 0 else "无操作")
    
    # 保存结果
    import json
    output_path = os.path.join(PROJECT_ROOT, "experiments", "results", "performance_benchmark.json")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    
    print(f"\n详细结果已保存至: {output_path}")
    
    return all_results


if __name__ == "__main__":
    main()
