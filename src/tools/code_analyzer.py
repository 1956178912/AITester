"""
代码分析工具：AST 解析、圈复杂度计算、代码结构提取。
"""

from __future__ import annotations

import ast
from typing import Any, Dict, List


def parse_function_nodes(source_code: str) -> List[Dict[str, Any]]:
    """
    解析 Python 源码中的所有函数/方法定义。

    Args:
        source_code: Python 源代码字符串。

    Returns:
        函数节点列表，每个节点包含：
        - name: 函数名
        - lineno: 起始行号
        - end_lineno: 结束行号
        - args: 参数列表
    """
    tree = ast.parse(source_code)
    functions = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append({
                "name": node.name,
                "lineno": node.lineno,
                "end_lineno": node.end_lineno,
                "args": [arg.arg for arg in node.args.args],
                "docstring": ast.get_docstring(node),
            })
    return functions


def extract_function_code(source_code: str, function_name: str) -> str | None:
    """
    从源码中提取指定函数的完整代码块。

    Args:
        source_code: Python 源代码字符串。
        function_name: 目标函数名。

    Returns:
        函数代码字符串，未找到时返回 None。
    """
    lines = source_code.splitlines()
    functions = parse_function_nodes(source_code)

    for func in functions:
        if func["name"] == function_name:
            start = func["lineno"] - 1
            end = func["end_lineno"]
            return "\n".join(lines[start:end])
    return None


def compute_cyclomatic_complexity(source_code: str) -> int:
    """
    计算代码的圈复杂度（Cyclomatic Complexity）。
    复杂度 = 1 + 所有决策点（if/elif/for/while/except/and/or）数量。

    Args:
        source_code: Python 源代码字符串。

    Returns:
        圈复杂度整数值。
    """
    tree = ast.parse(source_code)
    complexity = 1  # 基础复杂度

    for node in ast.walk(tree):
        if isinstance(node, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
            complexity += 1
        elif isinstance(node, ast.BoolOp):
            # and/or 各增加一个决策点
            complexity += len(node.values) - 1

    return complexity
