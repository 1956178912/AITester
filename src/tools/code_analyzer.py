"""
代码分析工具：AST 解析、圈复杂度计算、代码结构提取。

本模块使用 Python 标准库 ast（抽象语法树）对源码进行静态分析，
不依赖任何第三方库，确保兼容性和可移植性。

主要功能：
    - parse_function_nodes:       解析源码中所有函数/方法定义及其属性
    - extract_function_code:      按名称提取单个函数的完整代码块
    - compute_cyclomatic_complexity: 计算圈复杂度（McCabe 度量）
    - replace_function_code:      使用 AST 安全替换指定函数实现
    - extract_function_context:   按调用链 depth 提取最小上下文（P0 1.1 分层代码压缩）
    - preserve_patch_ingredients: 截断前显式保留补丁成分（P0 1.2 补丁配方保留）
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
        - args (list):     参数名列表（按源码顺序，方法含 self/cls；
          不额外剔除，因首个参数并不总是 self/cls，由调用方自行判断）
        - docstring (str): 函数文档字符串（无则 None）
    """
    # 将源码编译为 AST 对象，若语法错误则抛出 SyntaxError
    tree = ast.parse(source_code)
    functions = []
    # 遍历 AST 树中所有节点（广度优先）
    for node in ast.walk(tree):
        # 匹配普通函数定义和异步函数定义两种节点类型
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # 提取参数名列表：按源码顺序包含全部位置参数（方法含 self/cls）
            # 不在此处剔除首个参数——首个参数并不总是接收者（如回调、生成器函数）
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
        - 三目表达式 (IfExp):    a if b else c 增加一条路径
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
        # ast.IfExp: 三目表达式 a if b else c
        # ast.While: while 循环
        # ast.For:   for 循环
        # ast.ExceptHandler: try-except 中的 except 分支
        if isinstance(node, (ast.If, ast.IfExp, ast.While, ast.For, ast.ExceptHandler)):
            complexity += 1
        elif isinstance(node, ast.BoolOp):
            # BoolOp 表示 and/or 运算符
            # CPython 把同一运算符的链式（a and b and c）折叠为单个
            # BoolOp 节点（values 长度 = 操作数个数），而非二叉树嵌套，
            # 因此每个 BoolOp 增加 len(values) - 1 条额外路径
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
        # 匹配普通函数与异步函数定义，且函数名一致
        # （AsyncFunctionDef 不是 FunctionDef 子类，须显式列出，否则 async def 会被静默漏配）
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
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


def extract_function_context(
    source_code: str,
    func_name: str,
    depth: int = 2,
    max_chars: int = 3000,
) -> str | None:
    """按调用链 depth 提取目标函数的最小代码上下文（P0 1.1 分层代码压缩）。

    口径（用户需求 1.1）：只将"目标函数 + 其直接调用的辅助函数（depth 层）
    + 相关 import"注入 LLM prompt，而非整个文件。跨文件任务由调用方把多个
    模块的源码拼接成一段多段源码后调用，模块间的调用链由顶层 import 表达
    （被调函数若在同段源码中存在则随闭包保留）。

    实现委托给 src.tools.code_context.extract_focused_code_detail（AST 闭包，
    depth=1 等价于一层直接依赖，depth=2 再展开一层被调函数的依赖）。

    Args:
        source_code: Python 源码（可多文件拼接）。
        func_name: 目标函数名。
        depth: 调用链展开层数（1 = 直接调用的辅助函数；2 = 再展开一层）。
        max_chars: 输出字符预算（超出仍由 extract_focused_code_detail 逐层裁剪）。

    Returns:
        最小上下文字符串；源码无法解析或函数不存在时返回 None
        （调用方降级为全文件 + 字符级截断兜底）。
    """
    if not source_code or not source_code.strip():
        return None
    from src.tools.code_context import extract_focused_code_detail

    # 2026-09-26 全面审查（C-1 性能修复）：改用 extract_focused_code_detail
    # 拿 (code, focus_resolved) 二元组——旧版靠 "result == source_code" 反推
    # 原样返回场景后**再做一次 ast.parse + ast.walk** 确认函数是否存在
    # （extract_focused_code 内部已 parse 过，大文件 ~200ms 翻倍）。
    # 新口径：focus_resolved=False 即"AST 解析失败 / 无顶层函数 / 焦点不在
    # 源码中"，直接返回 None，零重复解析。
    focused, focus_resolved = extract_focused_code_detail(
        source_code,
        focus_function=func_name,
        max_chars=max_chars,
        depth=depth,
    )
    if not focus_resolved:
        return None
    return focused


# ─── P0 1.2 补丁配方保留（Patch Ingredient Retention）────────────────────────
# 参考 SWEZZE 的 Oracle-guided Code Distillation：压缩过程不得破坏语义完整性
# （定义-使用关系、类型约束）。本步骤在截断前显式识别"最小充分成分"——
# 目标函数完整 AST 节点、其调用函数的签名、模块级导出符号（__all__、注册
# 装饰器、插件入口点）及全部相关 import 语句——并返回"成分保留片段"，
# 供上游（BaseAgent.truncate_code / 各 Agent 的 prompt 构建）与 AST 截取结果
# 合并注入，确保 LLM 看到"最小充分子序列"而非字符级硬截断的残片。


def _decorator_name(dec: ast.expr) -> str | None:
    """提取装饰器名称（@register_plugin / @sphinx.application ...）。"""
    if isinstance(dec, ast.Name):
        return dec.id
    if isinstance(dec, ast.Attribute):
        return dec.attr
    if isinstance(dec, ast.Call):
        inner = _decorator_name(dec.func)
        if inner:
            return inner
    return None


# 常见"注册 / 插件入口 / 导出"装饰器名（命中即视为模块级契约符号）
_REGISTER_DECORATOR_NAMES: frozenset[str] = frozenset(
    {
        "register",
        "register_plugin",
        "plugin",
        "entry_point",
        "component",
        "register_action",
        "app",
        "blueprint",
        "hook",
        "hookimpl",
        "hookwrapper",
        "fixture",
        "pytest",
    }
)


def _decorator_is_register_like(dec: ast.expr) -> bool:
    """装饰器名（或其调用形式）是否命中注册/插件入口模式。"""
    name = _decorator_name(dec)
    if not name:
        return False
    low = name.lower()
    return low in _REGISTER_DECORATOR_NAMES or any(p in low for p in ("register", "plugin", "entry", "hook"))


def _collect_ingredient_segments(
    source_code: str,
    target_func: str | None,
    _ast: ast.Module | None = None,
) -> dict[str, Any]:
    """识别补丁最小充分成分（P0 1.2）。

    遍历源码 AST，收集：
    - imports：全部模块级 import / from-import 语句（import 链完整性的前提）；
    - exports：__all__ 列表字面量内容（若存在）；
    - register_symbols：顶层带注册/插件入口装饰器（@register*、@plugin、
      @entry_point、@hook... 等）的函数/类名；
    - target_ast：目标函数的完整 AST 节点（未截断源码文本，供"定义-使用"
      关系保留）；
    - called_signatures：目标函数体内直接调用的同模块函数的签名行（仅
      def 行 + 装饰器，不展开函数体，控制 token 成本）；
    - module_constants：顶层赋值常量名（`NAME = ...` / `NAME: T = ...`）。

    解析失败或源码为空时返回各字段空值（不阻断调用方降级路径）。

    2026-09-26 性能优化：_ast 可选参数——调用方（code_context 的
    extract_focused_code_detail）已对同一 source 做过 ast.parse，可传入
    既有 tree 复用，消除 200ms 级重复解析；独立调用（无 _ast）时行为不变。
    """
    ingredients: dict[str, Any] = {
        "imports": "",
        "exports": [],
        "register_symbols": [],
        "target_ast": "",
        "called_signatures": [],
        "module_constants": [],
        "parsed": False,
        # 2026-09-26：暴露解析成功的 AST tree（供调用方复用做二次分析，
        # 避免重复 ast.parse；独立调用方未消费此键时不影响既有字段口径）
        "ast_tree": None,
    }
    if not source_code or not source_code.strip():
        return ingredients
    if _ast is not None:
        tree: ast.Module = _ast
    else:
        try:
            tree = ast.parse(source_code)
        except (SyntaxError, ValueError):
            return ingredients
    ingredients["parsed"] = True
    ingredients["ast_tree"] = tree

    lines = source_code.splitlines()

    # 1. import 语句（模块级）
    import_segments: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            start = getattr(node, "lineno", 1) or 1
            end = getattr(node, "end_lineno", start) or start
            import_segments.append("\n".join(lines[start - 1 : end]))
    ingredients["imports"] = "\n".join(import_segments)

    # 2. 顶层函数 / 类 / 常量 / 装饰器识别
    top_funcs: dict[str, ast.AST] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            top_funcs[node.name] = node
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    if target.id == "__all__":
                        # __all__ 字面量提取
                        value = node.value
                        if isinstance(value, (ast.List, ast.Tuple)):
                            for elt in value.elts:
                                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                    ingredients["exports"].append(elt.value)
                    elif not target.id.startswith("__"):
                        ingredients["module_constants"].append(target.id)
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and not node.target.id.startswith("__")
        ):
            ingredients["module_constants"].append(node.target.id)

    # 3. 注册 / 插件入口装饰器
    for name, top_node in top_funcs.items():
        for dec in getattr(top_node, "decorator_list", []) or []:
            if _decorator_is_register_like(dec):
                ingredients["register_symbols"].append(name)
                break

    # 4. 目标函数完整 AST + 调用签名
    if target_func and target_func in top_funcs:
        target_node = top_funcs[target_func]
        start = getattr(target_node, "lineno", 1) or 1
        end = getattr(target_node, "end_lineno", start) or start
        ingredients["target_ast"] = "\n".join(lines[start - 1 : end])
        # 目标函数体内直接调用的同模块函数 → 仅签名（def 行 + 装饰器）
        called_names: set[str] = set()
        for sub in ast.walk(target_node):
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name):
                called_names.add(sub.func.id)
        for called in sorted(called_names):
            if called in top_funcs and called != target_func:
                callee = top_funcs[called]
                callee_start = getattr(callee, "lineno", 1) or 1
                # 仅取装饰器行 + def 行本身，不展开函数体：
                # callee_start 为 1-based def 行号；0-based 切片
                # lines[dec_start-1 : callee_start] 的右端 callee_start 恰好切到
                # def 行结束（不含函数体首行）。无装饰器时 dec_start==callee_start，
                # 切片为单行 def；有装饰器时含全部装饰器行 + def 行。
                # （2026-09-26 round8 tools 审查核实：切片正确，与 docstring
                # "仅 def 行 + 装饰器"口径一致，无缺陷。）
                dec_start = callee_start
                for dec in getattr(callee, "decorator_list", []) or []:
                    dec_start = min(dec_start, getattr(dec, "lineno", dec_start) or dec_start)
                ingredients["called_signatures"].append(
                    "\n".join(lines[dec_start - 1 : callee_start])
                )

    return ingredients


def preserve_patch_ingredients(
    source_code: str, target_func: str | None = None, _ast: ast.Module | None = None
) -> dict[str, Any]:
    """P0 1.2 补丁配方保留：截断前显式保留最小充分成分（SWEZZE 式）。

    在代码上下文压缩（P0 1.1 分层截取）之前调用，返回"成分保留片段"——
    目标函数完整 AST 节点文本、其直接调用函数的签名、模块级导出符号
    （__all__ / 注册装饰器 / 插件入口点 / 模块级常量）与全部 import 语句。

    上游可将返回值中的各片段拼接到 LLM prompt，与 AST 截取结果合并，
    使 LLM 即便在字符级截断的残片场景下仍能看到"补丁必须保留的契约成分"，
    避免压缩破坏定义-使用关系与命名契约（sqlfluff 插件 5/7 失败根因）。

    Args:
        source_code: 原始 Python 源码（可多文件拼接，按拼接文本 AST 解析）。
        target_func: 目标函数名（可选）。提供时提取其完整 AST + 调用签名；
            None 时仅保留模块级契约成分（import / 导出 / 注册符号 / 常量）。
        _ast: 内部参数——调用方已解析的 AST tree（复用，避免重复解析）；
            外部调用者无需传此参数。

    Returns:
        成分字典，键：
        - imports (str): 全部模块级 import 语句（换行拼接）。
        - exports (list[str]): __all__ 列出的符号。
        - register_symbols (list[str]): 带注册/插件入口装饰器的顶层符号。
        - target_ast (str): 目标函数完整源码文本（None/未提供/未找到时 ""）。
        - called_signatures (list[str]): 目标函数直接调用的同模块函数签名
          （仅 def 行 + 装饰器，不含函数体）。
        - module_constants (list[str]): 顶层赋值常量名。
        - parsed (bool): 源码是否成功 AST 解析（失败时各字段为空，
          调用方降级为全文件 + 字符级截断兜底）。

    设计约束（与 contamination_check / embedding_utils 同口径）：
    - 纯标准库 ast，零外部依赖，可复算；
    - 解析失败保守返回空值，不抛出、不阻断主流程；
    - 调用签名仅取 def 行（token 成本 O(1)/函数），函数体由 P0 1.1 的
      调用链闭包（extract_function_context）按 depth 预算控制，两者正交。
    """
    return _collect_ingredient_segments(source_code, target_func, _ast=_ast)


def render_patch_ingredient_context(ingredients: dict[str, Any]) -> str:
    """把 preserve_patch_ingredients 的成分字典渲染为可注入 prompt 的文本块。

    输出格式（各段双换行分隔，空段跳过）：
    [PATCH_INGREDIENTS]
    imports:
    <import 语句>
    exports: __all__ = [...]
    register_symbols: register_plugin, ...
    target_ast:
    <目标函数完整源码>
    called_signatures:
    def helper_a(...)
    module_constants: NAME1, NAME2

    无任何成分（parsed=False 或全空）时返回空串（调用方不注入）。
    """
    if not ingredients:
        return ""
    parts: list[str] = []
    imports = ingredients.get("imports") or ""
    if imports:
        parts.append(f"imports:\n{imports}")
    exports = ingredients.get("exports") or []
    if exports:
        parts.append(f"exports: {', '.join(exports)}")
    reg = ingredients.get("register_symbols") or []
    if reg:
        parts.append(f"register_symbols: {', '.join(reg)}")
    target_ast = ingredients.get("target_ast") or ""
    if target_ast:
        parts.append(f"target_ast:\n{target_ast}")
    sigs = ingredients.get("called_signatures") or []
    if sigs:
        parts.append("called_signatures:\n" + "\n".join(sigs))
    consts = ingredients.get("module_constants") or []
    if consts:
        parts.append(f"module_constants: {', '.join(consts)}")
    if not parts:
        return ""
    return "[PATCH_INGREDIENTS]\n" + "\n\n".join(parts)
