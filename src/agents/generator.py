"""
测试代码生成器模块：根据测试计划生成可运行的 pytest 测试代码。

支持 RAG 检索增强：在生成前先检索相似历史测试用例作为参考，
提升生成测试的质量和风格一致性。

3.4 断言增强策略（Assertion Augmentation，默认关）：
    启用 ASSERTION_AUGMENT_ENABLE=true 时，Generator 在生成前先 AST 提取
    被测代码中已有的 assert 语句（开发者编写或测试用例中的现有断言），
    作为"锚点断言"注入 prompt，引导 LLM 生成更高质量的断言（避免断言弱化、
    恒真断言、魔数未命名等异味）。该策略不改变 LLM 调用主路径，仅在
    构造 prompt 时多一段"现有断言参考"注入。
"""

from __future__ import annotations

import ast
import json
import logging
import os
import re
from typing import Any

from src.agents.base_agent import BaseAgent
from src.prompts.templates import GENERATOR_SYSTEM_PROMPT

# 模块级日志记录器
logger = logging.getLogger(__name__)

# RAG 参考案例最大数量：避免 prompt 过长导致 token 浪费
_MAX_RAG_REFERENCES = 3

# 3.4 断言增强：AST 提取被测代码中已有 assert 语句的最大数量（避免 prompt 过长）
_MAX_EXISTING_ASSERTIONS = 10


def _assertion_augment_enabled() -> bool:
    """3.4 断言增强开关：环境变量 ASSERTION_AUGMENT_ENABLE=true 时启用（默认 false）。"""
    return os.getenv("ASSERTION_AUGMENT_ENABLE", "false").lower() == "true"


def _extract_existing_assertions(target_code: str) -> list[str]:
    """3.4 断言增强：AST 提取被测代码中已有的 assert 语句（开发者编写的锚点断言）。

    扫描 target_code 中所有 ast.Assert 节点，返回源文本列表（去重，保持顺序）。
    若被测代码本身无 assert（罕见），返回空列表。

    Args:
        target_code: 被测代码字符串。

    Returns:
        assert 语句源文本列表（最多 _MAX_EXISTING_ASSERTIONS 条，截断保留前 N）。
    """
    if not target_code:
        return []
    try:
        tree = ast.parse(target_code)
    except SyntaxError:
        # 被测代码语法错误时无法 AST 解析，保守返回空（不阻断主流程）
        return []
    assertions: list[str] = []
    seen: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            # 提取源文本（ast.get_source_segment 需要完整源码 + 行号上下文）
            try:
                seg = ast.get_source_segment(target_code, node)
            except (AttributeError, ValueError):
                seg = None
            if seg and seg.strip() and seg not in seen:
                seen.add(seg)
                assertions.append(seg)
            if len(assertions) >= _MAX_EXISTING_ASSERTIONS:
                break
    return assertions


class GeneratorAgent(BaseAgent):
    """
    测试生成师：根据测试计划生成可运行的 pytest 代码。
    可选地接收 RAG 检索到的历史相似案例，增强生成质量。

    输入:
        test_plan: PlannerAgent 输出的测试计划字典。
        target_code: 被测代码全文（用于 import 引用）。
        rag_references: RAG 检索到的相似历史测试用例列表（可选）。

    输出:
        完整的 pytest 测试代码字符串。
    """

    # 已知合法的外部包，不应被替换为被测模块名
    # 这些是 Python 标准库和常用测试框架，import 它们属于正常行为
    _KNOWN_MODULES = {
        "pytest",
        "unittest",
        "typing",
        "re",
        "os",
        "sys",
        "json",
        "collections",
        "itertools",
        "functools",
        "abc",
        "dataclasses",
        "enum",
        "pathlib",
        "math",
        "datetime",
        "string",
        "random",
        "hashlib",
        "logging",
    }

    def __init__(self) -> None:
        # 使用生成器专用 system prompt
        super().__init__(GENERATOR_SYSTEM_PROMPT)

    def generate(
        self,
        test_plan: dict[str, Any],
        target_code: str,
        module_name: str = "",
        rag_references: list[dict[str, Any]] | None = None,
        focus_function: str | None = None,
    ) -> str:
        """
        生成 pytest 测试代码。
        若提供 rag_references，将其作为参考注入 prompt。

        处理流程：
        1. 将测试计划和目标代码拼接到 prompt 中
        2. 若有 RAG 参考，取前 _MAX_RAG_REFERENCES 个注入 prompt
        3. 调用 LLM 生成代码
        4. 修正错误的 import 模块名（_fix_import_module）
        5. 校验 parametrize 格式，失败则追加修正提示重试一次（仍失败仅告警，避免 LLM 反复生成相同错误）

        Args:
            test_plan: 测试计划字典（PlannerAgent 输出）。
            target_code: 被测代码全文。
            module_name: 模块名（不含 .py），用于生成 import 语句。
            rag_references: RAG 检索到的相似历史案例，每项含 test_code 字段。
            focus_function: 焦点函数名（可选）。超长代码时按该函数做 AST
                智能截取，保留其直接依赖的辅助函数（大文件场景关键）。

        Returns:
            完整的 pytest 测试代码字符串。

        Raises:
            RuntimeError: LLM 调用失败时抛出。
        """
        # 将测试计划序列化为 JSON 字符串，便于 LLM 理解结构
        plan_json = json.dumps(test_plan, ensure_ascii=False, indent=2)

        # 焦点函数优先级：显式参数 > 测试计划中的 function_name（Planner 已定位的函数）
        if focus_function is None and isinstance(test_plan, dict):
            focus_function = test_plan.get("function_name") or None

        # 截断超长代码，节省 token（大文件按焦点函数做 AST 智能截取）
        target_code = BaseAgent.truncate_code(target_code, focus_function=focus_function)

        # 构建基础查询，包含测试计划和目标代码
        query = (
            f"测试计划（JSON）：\n{plan_json}\n\n"
            f"目标代码：\n```\n{target_code}\n```"
            f"\n\n被测模块名：{module_name}"
            f"\n\n请根据以上计划生成完整的 pytest 测试代码。"
        )

        # 强约束：必须使用给定的 module_name 作为 import 来源
        # 避免 LLM 随意猜测模块名导致 ModuleNotFoundError
        if module_name:
            query += (
                f"\n\n【重要约束】import 语句必须使用以下模块名：`{module_name}`，即 `from {module_name} import ...`"
            )

        # RAG 增强：若检索到相似案例，注入参考代码
        # 最多取前 _MAX_RAG_REFERENCES 个案例，避免 prompt 过长导致 token 浪费
        if rag_references:
            refs_text = []
            for i, ref in enumerate(rag_references[:_MAX_RAG_REFERENCES], start=1):
                # 取 test_code 字段作为参考
                test_code = ref.get("test_code", "")
                if test_code:
                    refs_text.append(f"【参考案例 {i}】\n```python\n{test_code}\n```")
            if refs_text:
                query += "\n\n以下历史测试用例可作为参考风格：\n" + "\n\n".join(refs_text)
                logger.info("Generator 使用了 %d 个 RAG 参考案例", len(refs_text))

        # 3.4 断言增强（默认关）：提取被测代码中已有 assert 作为"锚点断言"注入 prompt
        if _assertion_augment_enabled():
            existing_assertions = _extract_existing_assertions(target_code)
            if existing_assertions:
                query += (
                    "\n\n【断言增强】被测代码中已存在以下断言，请在新测试中复用或扩展这些"
                    "断言模式，避免生成恒真断言 / 魔数未命名 / 断言弱化等异味：\n"
                    + "\n".join(f"- {a}" for a in existing_assertions)
                )
                logger.info("Generator 断言增强注入了 %d 条现有断言", len(existing_assertions))
            else:
                logger.debug("Generator 断言增强启用但被测代码无现有 assert，跳过注入")

        # 调用 LLM 生成测试代码，带文件缓存省 token
        raw = self._call_llm_with_cache(query)
        # 从响应中提取 Python 代码块（去除 markdown 包裹）
        code = self._extract_python_code(raw)
        # Import 验证：修正错误的模块名
        if module_name:
            code = self._fix_import_module(code, module_name)
        # Parametrize 格式校验：LLM 有时会在 parametrize 中混入 case_name 导致参数不匹配
        if not self._validate_parametrize(code):
            logger.warning("Generator 检测到 parametrize 格式错误，触发重试")
            # 重试时追加负面反馈提示，避免 LLM 用相同 query 生成相同错误
            retry_query = query + (
                "\n\n【修正要求】上次生成的测试代码中，"
                "pytest.mark.parametrize 的参数定义与用例元组长度不匹配。"
                "请确保每个用例元组的元素数量与参数名列表完全一致，"
                "不要混入 case_name 等额外字段。"
            )
            raw = self._call_llm_with_cache(retry_query)
            code = self._extract_python_code(raw)
            if module_name:
                code = self._fix_import_module(code, module_name)
            # 二次校验：若仍失败则警告但不重试，避免 LLM 反复生成相同错误代码
            if not self._validate_parametrize(code):
                logger.warning("二次 parametrize 校验仍失败，继续执行（可能 LLM 无法修正）")
        return code

    @staticmethod
    def _check_parametrize_decorator(decorator) -> tuple | None:
        """
        检查装饰器是否为 @pytest.mark.parametrize，若是则返回参数信息。

        Args:
            decorator: AST 装饰器节点。

        Returns:
            (param_names, cases_arg) 元组，否则返回 None。
        """
        if not (
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr == "parametrize"
        ):
            return None
        if not decorator.args:
            return None
        arg_expr = decorator.args[0]
        if not isinstance(arg_expr, ast.Constant) or not isinstance(arg_expr.value, str):
            return None
        param_names = [n.strip() for n in arg_expr.value.split(",")]
        if len(decorator.args) < 2:
            return None
        cases_arg = decorator.args[1]
        if not isinstance(cases_arg, ast.List):
            return None
        return param_names, cases_arg

    @staticmethod
    def _validate_case_tuple(elt, param_names: list[str]) -> bool:
        """
        校验单个用例元组的长度是否与参数名数量匹配。

        Args:
            elt: AST 元组/列表节点。
            param_names: 参数名列表。

        Returns:
            True 表示匹配，False 表示不匹配。
        """
        if isinstance(elt, (ast.Tuple, ast.List)):
            if len(elt.elts) != len(param_names):
                logger.warning(
                    "Parametrize 参数不匹配：声明 %d 个，实际 %d 个 → 需要重试",
                    len(param_names),
                    len(elt.elts),
                )
                return False
        return True

    @staticmethod
    def _validate_parametrize(code: str) -> bool:
        """
        校验 pytest.mark.parametrize 的参数定义与用例元组是否匹配。
        使用 ast 解析确保语法合法，再校验 parametrize 参数数量是否匹配。

        Returns:
            True 表示格式正确，False 表示需要重试。
        """
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            logger.warning("测试代码语法错误: %s → 需要重试", e.msg)
            return False
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for decorator in node.decorator_list:
                result = GeneratorAgent._check_parametrize_decorator(decorator)
                if result is None:
                    continue
                param_names, cases_arg = result
                for elt in cases_arg.elts:
                    if not GeneratorAgent._validate_case_tuple(elt, param_names):
                        return False
        return True

    @staticmethod
    def _fix_import_module(code: str, expected_module: str) -> str:
        """
        验证并修正测试代码中的 import 模块名。
        将"被测模块名的笔误变体"替换为期望的模块名，避免 ModuleNotFoundError。
        跳过已知的外部包（pytest、unittest 等）以及与被测模块名不相似的
        第三方库（如 numpy/requests），不做无差别改写。

        相似度门控（与 executor._is_similar_module_name 同源，阈值 0.6）：
        仅当导入名与被测模块名足够相似（视为笔误/缩写）时才替换，
        否则保留原样——避免把被测代码依赖的第三方库导入错误改写为被测模块名
        （如 `from numpy import array` 被改成 `from calculator import array`）。

        正则说明：
        - ``^from\\s+(\\S+)\\s+import`` 匹配行首的 "from X import ..." 语句
        - re.MULTILINE 使 ^ 匹配每行的开头

        Args:
            code: 待校验的测试代码字符串。
            expected_module: 期望的模块名（不含 .py）。

        Returns:
            修正后的代码字符串。
        """
        from src.agents.executor import ExecutorAgent

        # 匹配所有 "from X import ..." 语句（X 为模块名）
        pattern = re.compile(r"^from\s+(\S+)\s+import", re.MULTILINE)
        matches = pattern.findall(code)
        for wm in matches:
            # 若已是期望模块名，无需修改
            if wm == expected_module:
                continue
            # 跳过已知的外部包（标准库和测试框架）
            if wm in GeneratorAgent._KNOWN_MODULES:
                continue
            # 相似度门控：仅替换被测模块名的"笔误"变体，保留不相似的第三方库
            if not ExecutorAgent._is_similar_module_name(wm, expected_module):
                continue
            # 将错误的模块名替换为期望模块名
            code = code.replace(f"from {wm} import", f"from {expected_module} import")
            logger.warning("Generator 修正了错误模块名：%s → %s", wm, expected_module)
        return code
