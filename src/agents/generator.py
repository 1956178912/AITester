"""
测试代码生成器模块：根据测试计划生成可运行的 pytest 测试代码。

支持 RAG 检索增强：在生成前先检索相似历史测试用例作为参考，
提升生成测试的质量和风格一致性。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from src.agents.base_agent import BaseAgent
from src.prompts.templates import GENERATOR_SYSTEM_PROMPT
from src.graph.llm_cache import cached_llm_call, get_cache_stats
from src.exceptions import SyntaxParseError

# 模块级日志记录器
logger = logging.getLogger(__name__)

# RAG 参考案例最大数量：避免 prompt 过长导致 token 浪费
_MAX_RAG_REFERENCES = 3
# import 修正重试次数上限：防止 LLM 反复生成相同错误
_MAX_PARAMETIZE_RETRIES = 2


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
    _KNOWN_MODULES = {'pytest', 'unittest', 'typing', 're', 'os', 'sys',
                      'json', 'collections', 'itertools', 'functools',
                      'abc', 'dataclasses', 'enum', 'pathlib', 'math',
                      'datetime', 'string', 'random', 'hashlib', 'logging'}

    def __init__(self) -> None:
        # 使用生成器专用 system prompt
        super().__init__(GENERATOR_SYSTEM_PROMPT)

    def generate(
        self,
        test_plan: Dict[str, Any],
        target_code: str,
        module_name: str = "",
        rag_references: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """
        生成 pytest 测试代码。
        若提供 rag_references，将其作为参考注入 prompt。

        处理流程：
        1. 将测试计划和目标代码拼接到 prompt 中
        2. 若有 RAG 参考，取前 _MAX_RAG_REFERENCES 个注入 prompt
        3. 调用 LLM 生成代码
        4. 修正错误的 import 模块名（_fix_import_module）
        5. 校验 parametrize 格式，失败则最多重试 _MAX_PARAMETIZE_RETRIES 次

        Args:
            test_plan: 测试计划字典（PlannerAgent 输出）。
            target_code: 被测代码全文。
            module_name: 模块名（不含 .py），用于生成 import 语句。
            rag_references: RAG 检索到的相似历史案例，每项含 test_code 字段。

        Returns:
            完整的 pytest 测试代码字符串。

        Raises:
            RuntimeError: LLM 调用失败时抛出。
        """
        # 将测试计划序列化为 JSON 字符串，便于 LLM 理解结构
        plan_json = json.dumps(test_plan, ensure_ascii=False, indent=2)

        # 截断超长代码，节省 token
        target_code = BaseAgent.truncate_code(target_code)

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
            query += f"\n\n【重要约束】import 语句必须使用以下模块名：`{module_name}`，即 `from {module_name} import ...`"

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

        # 调用 LLM 生成测试代码
        raw = self._call_llm(query)
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
            raw = self._call_llm(retry_query)
            code = self._extract_python_code(raw)
            if module_name:
                code = self._fix_import_module(code, module_name)
            # 二次校验：若仍失败则警告但不重试，避免 LLM 反复生成相同错误代码
            if not self._validate_parametrize(code):
                logger.warning("二次 parametrize 校验仍失败，继续执行（可能 LLM 无法修正）")
        return code

    @staticmethod
    def _validate_parametrize(code: str) -> bool:
        """
        校验 pytest.mark.parametrize 的参数定义与用例元组是否匹配。
        使用 ast 解析确保语法合法，再校验 parametrize 参数数量是否匹配。

        校验逻辑：
        1. ast.parse 检查整体语法合法性（语法错误直接返回 False）
        2. 遍历所有函数定义，查找 @pytest.mark.parametrize 装饰器
        3. 对每个 parametrize，提取参数名列表，逐一比对用例元组的长度

        Returns:
            True 表示格式正确，False 表示需要重试。
        """
        import ast
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            # 语法错误说明 LLM 输出了非法代码，需要重试
            error_msg = f"测试代码语法错误: {e.msg}"
            context = {
                "lineno": e.lineno or 0,
                "offset": e.offset or 0,
                "text": e.text[:100] if e.text else "",
            }
            logger.warning("%s → 需要重试", error_msg)
            return False
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for decorator in node.decorator_list:
                # 检查装饰器是否为 @pytest.mark.parametrize(...)
                if not (isinstance(decorator, ast.Call)
                        and isinstance(decorator.func, ast.Attribute)
                        and decorator.func.attr == "parametrize"):
                    continue
                if not decorator.args:
                    continue
                arg_expr = decorator.args[0]
                # 第一个参数应是参数名字符串（如 "x,y"）
                if not isinstance(arg_expr, ast.Constant) or not isinstance(arg_expr.value, str):
                    continue
                # 解析参数名字符串，去除多余空格
                param_names = [n.strip() for n in arg_expr.value.split(",")]
                # 第二个参数应是用例列表
                if len(decorator.args) < 2:
                    continue
                cases_arg = decorator.args[1]
                if not isinstance(cases_arg, ast.List):
                    continue
                # 逐一校验每个用例元组的长度是否与参数名数量一致
                for elt in cases_arg.elts:
                    if isinstance(elt, (ast.Tuple, ast.List)):
                        if len(elt.elts) != len(param_names):
                            logger.warning(
                                "Parametrize 参数不匹配：声明 %d 个，实际 %d 个 → 需要重试",
                                len(param_names), len(elt.elts),
                            )
                            return False
        return True

    @staticmethod
    def _fix_import_module(code: str, expected_module: str) -> str:
        """
        验证并修正测试代码中的 import 模块名。
        将错误的模块名替换为期望的模块名，避免 ModuleNotFoundError。
        跳过已知的外部包（pytest、unittest 等），不修改其 import 语句。

        正则说明：
        - ``^from\\s+(\\S+)\\s+import`` 匹配行首的 "from X import ..." 语句
        - re.MULTILINE 使 ^ 匹配每行的开头

        Args:
            code: 待校验的测试代码字符串。
            expected_module: 期望的模块名（不含 .py）。

        Returns:
            修正后的代码字符串。
        """
        # 匹配所有 "from X import ..." 语句（X 为模块名）
        pattern = re.compile(r'^from\s+(\S+)\s+import', re.MULTILINE)
        matches = pattern.findall(code)
        changed = False
        for wm in matches:
            # 若已是期望模块名，无需修改
            if wm == expected_module:
                continue
            # 跳过已知的外部包（标准库和测试框架）
            if wm in GeneratorAgent._KNOWN_MODULES:
                continue
            # 将错误的模块名替换为期望模块名
            code = code.replace(f'from {wm} import', f'from {expected_module} import')
            logger.warning('Generator 修正了错误模块名：%s → %s', wm, expected_module)
            changed = True
        return code
