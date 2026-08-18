"""
代码分析工具：AST 解析、圈复杂度计算、代码结构提取。

本模块使用 Python 标准库 ast（抽象语法树）对源码进行静态分析，
不依赖任何第三方库，确保兼容性和可移植性。

主要功能：
    - parse_function_nodes:       解析源码中所有函数/方法定义及其属性
    - extract_function_code:      按名称提取单个函数的完整代码块
    - compute_cyclomatic_complexity: 计算圈复杂度（McCabe 度量）
    - replace_function_code:      使用 AST 安全替换指定函数实现
"""

from __future__ import annotations

import ast
from typing import Any


def parse_function_nodes(source_code: str) -> list[dict[str, Any]]:
    """
    解析 Python 源码中的所有函数/方法定义。

    使用 ast.walk 遍历整棵 AST 树，收集所有 FunctionDef 和 AsyncFunctionDef 节点。
    每个节点提取：函数名、起始/结束行号、参数列表、文档字符串。

    Args:
        source_code: Python 源代码字符串。

    Returns:
        函数节点列表，每个节点包含：
        - name (str):      函数名
        - lineno (int):    起始行号（1-based）
        - end_lineno (int): 结束行号（1-based，含函数体最后一行）
        - args (list):     参数名列表（不含 self/cls）
        - docstring (str): 函数文档字符串（无则 None）
    """
    # 将源码编译为 AST 对象，若语法错误则抛出 SyntaxError
    tree = ast.parse(source_code)
    functions = []
    # 遍历 AST 树中所有节点（广度优先）
    for node in ast.walk(tree):
        # 匹配普通函数定义和异步函数定义两种节点类型
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # 提取参数名列表：跳过 self/cls 等接收者参数（索引 0 通常为 self）
            args = [arg.arg for arg in node.args.args]
            functions.append(
                {
                    "name": node.name,
                    "lineno": node.lineno,
                    "end_lineno": node.end_lineno,
                    "args": args,
                    # ast.get_docstring 返回第一个 docstring 节点的内容，无则返回 None
                    "docstring": ast.get_docstring(node),
                }
            )
    return functions


def extract_function_code(source_code: str, function_name: str) -> str | None:
    """
    从源码中提取指定函数的完整代码块。

    流程：
        1. 调用 parse_function_nodes 获取所有函数节点
        2. 按函数名查找匹配节点
        3. 根据 lineno/end_lineno 截取对应行范围

    Args:
        source_code: Python 源代码字符串。
        function_name: 目标函数名（精确匹配）。

    Returns:
        函数代码字符串（含函数定义行到函数体最后一行），未找到时返回 None。
    """
    # 按行分割源码，便于后续按行号切片
    lines = source_code.splitlines()
    # 获取所有函数节点信息
    functions = parse_function_nodes(source_code)

    # 遍历节点列表，查找目标函数
    for func in functions:
        if func["name"] == function_name:
            # lineno 为 1-based，转为 0-based 索引
            start = func["lineno"] - 1
            # end_lineno 为 1-based 且包含结束行，切片时用 end_lineno（Python 切片右闭左开）
            end = func["end_lineno"]
            # 返回从 start 到 end 的行（不含 end）
            return "\n".join(lines[start:end])
    # 未找到匹配函数，返回 None
    return None


def compute_cyclomatic_complexity(source_code: str) -> int:
    """
    计算代码的圈复杂度（Cyclomatic Complexity）。

    圈复杂度是 McCabe 提出的软件复杂度度量指标，定义为：
        M = 1 + 所有独立路径数（决策点数量）

    在本实现中，决策点包括：
        - if / elif / else if:  每个控制流分支增加一条独立路径
        - while / for:          循环结构本身引入一条路径
        - except:               异常处理分支
        - and / or:             布尔运算符增加组合路径

    圈复杂度越高，说明分支越多、测试难度越大。
    通常建议单函数圈复杂度 <= 10，超过则考虑重构。

    Args:
        source_code: Python 源代码字符串。

    Returns:
        圈复杂度整数值（>= 1，值越大越复杂）。
    """
    # 将源码编译为 AST 对象
    tree = ast.parse(source_code)
    # 基础复杂度为 1（无分支的线性代码）
    complexity = 1

    # 遍历所有 AST 节点，统计决策点
    for node in ast.walk(tree):
        # 每个控制流节点增加一条独立路径
        # ast.If:  if/elif 语句（注意：else 不单独计数，已包含在 if 分支中）
        # ast.While: while 循环
        # ast.For:   for 循环
        # ast.ExceptHandler: try-except 中的 except 分支
        if isinstance(node, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
            complexity += 1
        elif isinstance(node, ast.BoolOp):
            # BoolOp 表示 and/or 运算符
            # a and b and c 生成 2 个 BoolOp 节点（二叉树结构）
            # 每个 BoolOp 增加 len(values) - 1 条额外路径
            # 例如 a and b: 2 个值 → 增加 1 条路径（共 2 条：a真b真 / a假）
            complexity += len(node.values) - 1

    return complexity


def replace_function_code(
    source_code: str,
    function_name: str,
    new_function_code: str,
) -> tuple[str, bool]:
    """
    使用 AST 将源码中指定函数的实现替换为新代码。

    相比正则替换，AST 方式的优势：
        - 精确匹配函数定义边界，不受缩进/空格影响
        - 避免误匹配同名函数或嵌套函数
        - 自动验证替换后代码的语法合法性

    流程：
        1. 验证新函数代码的语法合法性（避免后续解析失败）
        2. 解析原始源码的 AST 树
        3. 遍历 AST 找到目标函数节点
        4. 按行范围替换函数体
        5. 验证替换后代码的语法合法性

    Args:
        source_code:       原始 Python 源代码字符串。
        function_name:     需要被替换的函数名。
        new_function_code: 新的函数定义代码字符串（需是合法 Python 语法）。

    Returns:
        包含两个元素的元组：
        - str:  替换后的完整代码字符串（失败时返回原代码）
        - bool: 是否成功替换（True=成功，False=失败）
    """
    # 第一步：预验证新函数代码的语法合法性
    # 若不在此处验证，后续 ast.parse 可能因语法错误而崩溃
    try:
        ast.parse(new_function_code)
    except SyntaxError:
        # 新代码有语法错误，无法安全替换，返回原代码并标记失败
        return source_code, False

    # 第二步：解析原始源码的 AST 树
    tree = ast.parse(source_code)

    # 第三步：遍历 AST 节点，查找目标函数定义
    for node in ast.walk(tree):
        # 匹配 FunctionDef 节点且函数名一致
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            # 找到目标函数，提取其行范围（转为 0-based 索引）
            # lineno: 函数定义行（def xxx(...):）
            # end_lineno: 函数体最后一行
            start_line = node.lineno - 1  # 0-based 起始行索引
            end_line = node.end_lineno  # 0-based 结束行索引（包含）

            # 将新函数代码按行分割为列表
            new_lines = new_function_code.splitlines()
            # 获取原始代码的所有行
            lines = source_code.splitlines()

            # 第四步：按行范围替换（切片拼接）
            # lines[:start_line] 保留函数之前的行
            # new_lines           插入新函数代码
            # lines[end_line:]    保留函数之后的行
            new_code_lines = lines[:start_line] + new_lines + lines[end_line:]

            # 重新拼接为完整代码字符串
            new_code = "\n".join(new_code_lines)

            # 第五步：验证替换后代码的语法合法性
            # 防止新函数与原有代码产生冲突（如重复定义、缩进错误等）
            try:
                ast.parse(new_code)
                # 语法合法，返回替换后的代码
                return new_code, True
            except SyntaxError:
                # 替换后代码有语法错误，回滚到原代码
                return source_code, False

    # 第六步：未找到目标函数，返回原代码
    return source_code, False
