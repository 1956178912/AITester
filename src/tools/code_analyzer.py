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
    圈复杂度越高，说明分支越多、测试难度越大，通常 > 10 需要重构。

    Args:
        source_code: Python 源代码字符串。

    Returns:
        圈复杂度整数值（越高越复杂）。
    """
    tree = ast.parse(source_code)
    complexity = 1  # 基础复杂度（无分支时的最小值）

    for node in ast.walk(tree):
        # 每个控制流节点（if/while/for/except）增加一条独立路径
        if isinstance(node, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
            complexity += 1
        elif isinstance(node, ast.BoolOp):
            # and/or 各增加一个决策点（a and b and c 有 2 个 BoolOp 节点）
            complexity += len(node.values) - 1

    return complexity


def replace_function_code(source_code: str, function_name: str, new_function_code: str) -> tuple[str, bool]:
    """
    使用 AST 将源码中指定函数的实现替换为新代码。

    Args:
        source_code: 原始 Python 源代码字符串。
        function_name: 需要被替换的函数名。
        new_function_code: 新的函数定义代码字符串（需是合法 Python 语法）。

    Returns:
        包含两个元素的元组：
        - 替换后的完整代码字符串
        - 是否成功替换（布尔值）
    """
    # 先验证新函数代码的语法合法性，避免后续解析失败
    try:
        ast.parse(new_function_code)
    except SyntaxError:
        # 新代码有语法错误，直接返回原代码并标记失败
        return source_code, False

    # 解析原始源码的 AST 树
    tree = ast.parse(source_code)

    # 遍历 AST 节点，查找目标函数定义
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            # 找到目标函数，提取其行范围
            start_line = node.lineno - 1  # 转换为 0-based 索引
            end_line = node.end_lineno  # 包含结束行

            # 将新函数代码按行分割
            new_lines = new_function_code.splitlines()

            # 获取原始代码的所有行
            lines = source_code.splitlines()

            # 替换对应区间的行
            new_code_lines = lines[:start_line] + new_lines + lines[end_line:]

            # 重新拼接为完整代码字符串
            new_code = "\n".join(new_code_lines)

            # 验证替换后的代码语法合法性
            try:
                ast.parse(new_code)
                return new_code, True
            except SyntaxError:
                # 替换后代码不合法，返回原代码
                return source_code, False

    # 未找到目标函数，返回原代码
    return source_code, False
