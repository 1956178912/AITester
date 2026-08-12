"""
代码分析工具模块：基于 AST 的函数解析、圈复杂度计算和精确代码替换。
所有函数替换均基于 ast 模块，避免正则表达式在嵌套/同名函数场景下的误匹配。
"""

from __future__ import annotations

import ast
from typing import Any, Dict, List, Optional, Tuple


def parse_function_nodes(source_code: str) -> List[Dict[str, Any]]:
    """
    解析 Python 源码中的所有函数/方法定义。
    使用 ast 模块而非正则，能够正确处理嵌套函数、装饰器、类方法等复杂场景。

    Args:
        source_code: Python 源代码字符串。

    Returns:
        函数节点列表，每个节点包含：
        - name: 函数名
        - lineno: 起始行号（1-based）
        - end_lineno: 结束行号（1-based）
        - args: 参数名列表
        - docstring: 函数文档字符串（如无则为 None）
    """
    # 解析源码为 AST 树
    tree = ast.parse(source_code)
    functions = []
    # 遍历所有节点，提取函数定义
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
    使用 ast 模块精确获取行号范围，比正则更可靠。

    Args:
        source_code: Python 源代码字符串。
        function_name: 目标函数名。

    Returns:
        函数代码字符串，未找到时返回 None。
    """
    lines = source_code.splitlines()
    # 先解析所有函数节点，找到目标函数的行号范围
    functions = parse_function_nodes(source_code)

    for func in functions:
        if func["name"] == function_name:
            # AST 行号为 1-based，列表索引为 0-based，需减 1
            start = func["lineno"] - 1
            end = func["end_lineno"]
            return "\n".join(lines[start:end])
    return None


def compute_cyclomatic_complexity(source_code: str) -> int:
    """
    计算代码的圈复杂度（Cyclomatic Complexity）。
    公式：M = 1 + 所有决策点数量
    决策点包括：if/elif/for/while/except 和 and/or 运算符。
    复杂度越高，说明代码路径越多，测试难度越大。

    Args:
        source_code: Python 源代码字符串。

    Returns:
        圈复杂度整数值。
    """
    tree = ast.parse(source_code)
    complexity = 1  # 基础复杂度（一条执行路径）

    for node in ast.walk(tree):
        # 每个控制流语句增加一个决策点
        if isinstance(node, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
            complexity += 1
        elif isinstance(node, ast.BoolOp):
            # and/or 各有 n 个操作数时，增加 n-1 个决策点
            complexity += len(node.values) - 1

    return complexity


def replace_function_code(source_code: str, function_name: str, new_code: str) -> Tuple[str, bool]:
    """
    使用 ast 模块精确定位并替换指定函数的代码体，
    避免因函数嵌套或同名函数导致的正则误替换问题。
    新代码必须是合法的 Python 函数定义（以 'def ' 开头）。

    Args:
        source_code: 原始 Python 源代码。
        function_name: 要替换的函数名。
        new_code: 新的函数定义代码字符串（需以 'def ' 开头）。

    Returns:
        (替换后的完整代码, 是否成功替换)。
        若函数不存在或新代码语法错误，返回原代码和 False。
    """
    try:
        # 解析原始代码为新 AST，用于定位目标函数
        tree = ast.parse(source_code)
        # 解析新函数代码为新 AST，确保新代码语法合法
        new_tree = ast.parse(new_code)
    except SyntaxError as e:
        # 新代码语法错误，回退到原代码，避免破坏项目
        return source_code, False

    # 在 AST 中查找目标函数节点
    target_node: Optional[ast.FunctionDef] = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            target_node = node
            break

    if target_node is None:
        # 函数不存在，不做替换
        return source_code, False

    # 从新 AST 中提取目标函数的 body（函数体列表）
    # 排除 def 声明行本身
    new_func_body = None
    for node in ast.walk(new_tree):
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            new_func_body = node.body
            break

    if new_func_body is None:
        return source_code, False

    # 用新函数体替换目标节点的 body
    # 注意：不改变函数签名（参数、返回类型注解），只替换函数体
    target_node.body = new_func_body

    # 将修改后的 AST 重新生成为代码字符串
    new_source = ast.unparse(tree)
    # 保留原代码的末尾换行，确保格式一致
    if source_code.endswith("\n") and not new_source.endswith("\n"):
        new_source += "\n"
    return new_source, True
