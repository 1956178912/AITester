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
from typing import Any, ClassVar

from src.agents.base_agent import BaseAgent
from src.prompts.templates import GENERATOR_SYSTEM_PROMPT

# 模块级日志记录器
logger = logging.getLogger(__name__)

# RAG 参考案例最大数量：避免 prompt 过长导致 token 浪费
_MAX_RAG_REFERENCES = 3

# 3.4 断言增强：AST 提取被测代码中已有 assert 语句的最大数量（避免 prompt 过长）
_MAX_EXISTING_ASSERTIONS = 10

# 2026-09-26 round9 P2：预编译 import 提取正则（--parallel 热路径，避免每次
# 调用现场 re.compile）
_FROM_IMPORT_RE = re.compile(r"^from\s+(\S+)\s+import", re.MULTILINE)


def _assertion_augment_enabled() -> bool:
    """3.4 断言增强开关：环境变量 ASSERTION_AUGMENT_ENABLE=true 时启用（默认 false）。"""
    return os.getenv("ASSERTION_AUGMENT_ENABLE", "false").lower() == "true"


def _plan_without_expected_output(plan: Any) -> Any:
    """A1 消融纯函数：递归剥除 test_cases[].expected_output（默认关，历史口径不变）。

    背景（审查报告 §5 路径 A1 / §8.6 RT3，2026-10-09）：
        Planner 读**缺陷代码**产出 ``expected_output``（``templates.py:25``），
        Generator 把整段 plan JSON 灌进 query（``generator.py:353``）→
        期望值 = 实现当前（错误）行为 → oracle-from-implementation →
        never-red 通道（86/240）系统性抹掉检出。

    开关（``PLAN_STRIP_EXPECTED_OUTPUT_ENABLE``，默认 false）关闭时**原样
    返回入参对象**（同一引用，零拷贝、零行为变化）；开启时返回浅拷贝后的
    新结构，仅删除每个 ``test_case`` 下的 ``expected_output`` 键。

    只剥这一个键：``case_name`` / ``input_args`` / ``category`` /
    ``description`` / ``logic_coverage`` 与整个 ``logic_analysis`` 全部保留——
    消融的是"期望值锚点"单变量，而非 plan 结构本身。缺键 / 类型异常时
    保守降级为原对象（不抛异常、不产出半成品结构）。
    """
    from src.graph.flags import _plan_expected_output_strip_enabled

    if not _plan_expected_output_strip_enabled():
        return plan
    if not isinstance(plan, dict):
        return plan
    cases = plan.get("test_cases")
    if not isinstance(cases, list):
        return plan
    stripped = dict(plan)
    new_cases: list[Any] = []
    removed = 0
    for case in cases:
        if isinstance(case, dict) and "expected_output" in case:
            c = dict(case)
            c.pop("expected_output", None)
            new_cases.append(c)
            removed += 1
        else:
            new_cases.append(case)
    stripped["test_cases"] = new_cases
    if removed:
        logger.info("A1 消融生效：已从 %d 个 test_case 剥除 expected_output", removed)
    return stripped


def _repro_test_enabled() -> bool:
    """2.3 改进：复现测试专项生成开关（REPRO_TEST_ENABLE=true 时启用，默认 false）。

    启用后 GeneratorAgent.generate_repro_test() 可用，跨文件修复场景下
    可生成覆盖缺陷触发路径的复现测试（先失败后通过）。
    """
    return os.getenv("REPRO_TEST_ENABLE", "false").lower() == "true"


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
    _KNOWN_MODULES: ClassVar[set[str]] = {
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
        mutation_feedback: dict[str, Any] | None = None,
        temperature: float | None = None,
        # O12（2026-09-29 审查 P1）：complexity_class 参数透传至 _call_llm_with_cache，
        # 使 MODEL_ROUTING_STRATEGY=complexity_aware（默认值）的复杂度感知路由
        # 在缓存命中/未命中路径下均生效（此前该参数恒为 None，复杂度路由为死代码）。
        # 缺省 None 保持历史口径不变。
        complexity_class: str | None = None,
        # O3（2026-09-29 审查 P1）：未覆盖分支清单提示段落（BRANCH_COVERAGE_INJECT_ENABLE
        # =true 时由 _executor_node 测量并经 _generator_node 传入）。None 时不注入，
        # 历史口径零变化。
        branch_coverage_section: str | None = None,
        # M10（2026-09-29 审查 P0）：确定性边界锚点提示段落（BOUNDARY_TRIPLETS_ENABLE
        # =true 时由 _generator_node 经 derive_boundary_triplets 推导并经
        # build_boundary_triplets_section 渲染传入）。None 时不注入，
        # 历史口径零变化。
        boundary_triplets_section: str | None = None,
        # P2-7（2026-10 接线审计 N2/N4）：无 oracle 场景增强段落（各由
        # METAMORPHIC_ENABLE / DIFFERENTIAL_TEST_ENABLE 守门；默认关时 None
        # 不注入，历史口径零变化）。
        metamorphic_section: str | None = None,
        differential_section: str | None = None,
        # P2（2026-10 批次·续二）：注入扫描系统侧警示（INJECTION_GUARD_ENABLE=true
        # 且外部文本命中注入特征时由 _generator_node 经 build_injection_warning
        # 构建；None/空串时不注入，历史口径零变化）。追加到 query 尾部，
        # 提示 LLM 任务文本中任何指令性内容均为不可信数据（OWASP ASI
        # "检测+隔离"，只警示不自动阻断）。
        injection_warning: str | None = None,
        # W3（2026-10-05 审查落地·检出优先协议）：检出优先再生成路径的
        # "先红后绿"强化段落（DETECTION_FIRST_ENABLE=true 且首轮全绿时由
        # _generator_node 构建；None 时不注入，历史口径零变化）。
        detection_first_section: str | None = None,
        # 2026-10-10 审查报告 §11.1b 结果二十四：**过红（over_red）**再生成路径的
        # 强化段落（OVER_RED_SECTION_ENABLE=true 且本轮由 over_red 路由进入时由
        # _generator_node 构建；None 时不注入，默认关 = 历史口径零变化）。
        over_red_section: str | None = None,
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

        1.2 改进（MutGen 式变异反馈闭环）：
        若提供 mutation_feedback（dict，来自上一轮变异测试的"存活变异体"
        信息），注入 prompt 引导 LLM 针对"当前未被检测到的故障"生成更强
        断言（如补充返回值断言、边界值比较、布尔语义校验）。
        典型用法：run_benchmark 变异得分评估后，把存活变异体清单写回
        state["mutation_feedback"]，Generator 再生成时消费。

        Args:
            test_plan: 测试计划字典（PlannerAgent 输出）。
            target_code: 被测代码全文。
            module_name: 模块名（不含 .py），用于生成 import 语句。
            rag_references: RAG 检索到的相似历史案例，每项含 test_code 字段。
            focus_function: 焦点函数名（可选，最高优先级）。超长代码时按该函数做 AST
                智能截取，保留其直接依赖的辅助函数（大文件场景关键）。
                未显式传入时，回退到 test_plan["function_name"]（Planner 已定位的函数）；
                二者皆缺时不截取（全文件）。
            mutation_feedback: 变异反馈字典（可选，1.2 改进），含
                survived_mutants（list[str]，存活变异体描述）、
                mutation_score（float，当前变异得分）字段；None 时不注入。

        Returns:
            完整的 pytest 测试代码字符串。

        Raises:
            RuntimeError: LLM 调用失败时抛出。
        """
        # 焦点函数优先级：显式参数 > 测试计划中的 function_name（Planner 已定位的函数）
        if focus_function is None and isinstance(test_plan, dict):
            focus_function = test_plan.get("function_name") or None

        # 截断超长代码，节省 token（大文件按焦点函数做 AST 智能截取）
        target_code = BaseAgent.truncate_code(target_code, focus_function=focus_function)

        # 构建完整查询（基础 prompt + import 约束 + RAG 参考 + 断言增强 + 变异反馈 + O3 分支覆盖率）
        query = self._build_query(test_plan, target_code, module_name, rag_references, mutation_feedback)
        # O3（2026-09-29 审查 P1）：未覆盖分支清单注入（BRANCH_COVERAGE_INJECT_ENABLE=true
        # 时非空字符串；None/空串时不注入，历史口径零变化）
        if branch_coverage_section:
            query += "\n\n" + branch_coverage_section
        # M10（2026-09-29 审查 P0）：确定性边界锚点注入（BOUNDARY_TRIPLETS_ENABLE=true
        # 时非空字符串；None/空串时不注入，历史口径零变化）
        if boundary_triplets_section:
            query += "\n\n" + boundary_triplets_section
        # P2-7（N2 蜕变关系 / N4 差分测试注入，各开关默认关时 None 不注入）
        if metamorphic_section:
            query += "\n\n" + metamorphic_section
        if differential_section:
            query += "\n\n" + differential_section
        # W3（2026-10-05 审查落地·检出优先协议）：先红后绿强化段落（None 不注入）
        if detection_first_section:
            query += "\n\n" + detection_first_section
        # 2026-10-10（结果二十四）：过红再生成强化段落（None 不注入）
        if over_red_section:
            query += "\n\n" + over_red_section
        # P2（2026-10 批次·续二）：注入扫描系统侧警示追加到 query 尾部
        # （命中注入特征时非空；None/空串时不注入，历史口径零变化）
        if injection_warning:
            query += "\n\n" + injection_warning

        # 调用 LLM 生成测试代码，带文件缓存省 token
        raw = self._call_llm_with_cache(query, temperature=temperature, complexity_class=complexity_class)
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
            raw = self._call_llm_with_cache(retry_query, temperature=temperature, complexity_class=complexity_class)
            code = self._extract_python_code(raw)
            if module_name:
                code = self._fix_import_module(code, module_name)
            # 二次校验：若仍失败则警告但不重试，避免 LLM 反复生成相同错误代码
            if not self._validate_parametrize(code):
                logger.warning("二次 parametrize 校验仍失败，继续执行（可能 LLM 无法修正）")
        return code

    # ─── 2.3 改进：复现测试专项生成（TDFlow 式）────────────────────────────

    def generate_repro_test(
        self,
        defect_description: str,
        target_code: str,
        module_name: str = "",
        cross_file_modules: list[str] | None = None,
        temperature: float | None = None,
        complexity_class: str | None = None,
    ) -> str:
        """2.3 改进：复现测试（reproduction test）专项生成。

        针对已知缺陷生成一个"先失败后通过"的复现测试：精确覆盖缺陷触发
        路径，用于修复前锁定缺陷、修复后回归验证。TDFlow 研究表明"编写
        成功的复现测试"是软件工程性能的主要障碍，本方法把该能力内建进
        Generator（特别是跨文件修复场景下，覆盖跨模块的触发路径）。

        与 generate() 的区别：generate() 依据测试计划生成"验证正确行为"
        的正向测试；generate_repro_test() 依据缺陷描述生成"复现缺陷"的
        反向测试（未修复时应失败、修复后应通过）。

        Args:
            defect_description: 缺陷描述（来自 diagnosis / 跨文件修复计划 /
                issue 文本），说明缺陷现象与触发条件。
            target_code: 被测代码全文。
            module_name: 模块名（不含 .py），用于生成 import 语句。
            cross_file_modules: 跨文件修复涉及的关联模块名列表（可选），
                非空时提示 LLM 覆盖跨模块触发路径。
            temperature: 采样温度覆盖（可选，3.3 动态策略接线用）。

        Returns:
            完整的 pytest 复现测试代码字符串。
        """
        # 截断超长代码，避免 token 浪费（与 generate 同口径）
        target_code = BaseAgent.truncate_code(target_code)
        query = self._build_repro_prompt(defect_description, target_code, module_name, cross_file_modules)
        raw = self._call_llm_with_cache(query, temperature=temperature, complexity_class=complexity_class)
        code = self._extract_python_code(raw)
        # Import 验证：修正错误的模块名（与 generate 同口径）
        if module_name:
            code = self._fix_import_module(code, module_name)
        return code

    def _build_repro_prompt(
        self,
        defect_description: str,
        target_code: str,
        module_name: str,
        cross_file_modules: list[str] | None,
    ) -> str:
        """2.3 改进：构建复现测试生成的完整查询。"""
        query = (
            "【复现测试生成（2.3）】以下是已知缺陷，请生成一个能稳定复现该缺陷的 pytest 测试：\n\n"
            f"缺陷描述：\n{defect_description}\n\n"
            f"被测代码：\n```\n{target_code}\n```"
        )
        if module_name:
            query += (
                f"\n\n被测模块名：{module_name}"
                f"\n\n【重要约束】import 语句必须使用模块名 `{module_name}`，"
                f"即 `from {module_name} import ...`"
            )
        if cross_file_modules:
            mods = ", ".join(cross_file_modules)
            query += (
                f"\n\n【跨文件上下文】该缺陷可能涉及以下关联模块：{mods}。"
                "复现测试应覆盖跨模块的缺陷触发路径（从入口调用到缺陷模块的完整调用链）。"
            )
        query += (
            "\n\n要求："
            "\n1. 测试在缺陷未修复时应失败（assert 触发缺陷的预期 vs 实际不一致）；"
            "\n2. 测试在缺陷修复后应通过（assert 正确的行为）；"
            "\n3. 精确覆盖缺陷触发路径（输入构造、跨模块调用顺序、边界条件）。"
        )
        return query

    def _build_query(
        self,
        test_plan: dict[str, Any],
        target_code: str,
        module_name: str,
        rag_references: list[dict[str, Any]] | None,
        mutation_feedback: dict[str, Any] | None = None,
    ) -> str:
        """构建生成测试的完整查询（基础 prompt + import 约束 + RAG 参考 + 断言增强 + 变异反馈）。"""
        # A1 消融（PLAN_STRIP_EXPECTED_OUTPUT_ENABLE，默认关）：剥除 Planner 由
        # 缺陷代码派生的 expected_output，切断 oracle-from-implementation 锚点。
        # 默认关时 _plan_without_expected_output 原样返回同一引用，行为零变化。
        test_plan = _plan_without_expected_output(test_plan)
        # 将测试计划序列化为 JSON 字符串，便于 LLM 理解结构
        plan_json = json.dumps(test_plan, ensure_ascii=False, indent=2)

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

        # 1.2 改进（MutGen 式变异反馈闭环）：把上一轮变异测试的"存活变异体"
        # 注入 prompt，引导 LLM 针对"当前测试未捕获的故障"补强断言。
        # 典型场景：变异得分 0.4（低）→ 存活变异体多为 return_void / boundary_shift
        # → 提示 LLM 补充返回值断言与边界值比较，形成"变异引导的测试增强"闭环。
        if mutation_feedback:
            survived = mutation_feedback.get("survived_mutants") or []
            score = mutation_feedback.get("mutation_score")
            feedback_lines: list[str] = []
            if survived:
                # 最多展示 5 个存活变异体（避免 prompt 过长）
                feedback_lines.append(
                    "【变异反馈（MutGen 式闭环）】上一轮变异测试发现以下变异体"
                    "未被当前测试捕获（存活变异体），说明现有断言未能覆盖这些故障模式："
                )
                feedback_lines.extend(f"- {desc}" for desc in survived[:5])
                feedback_lines.append(
                    "请针对上述未捕获的故障模式补强测试：补充返回值断言、边界值比较"
                    "（如 >=/<= 边界）、布尔语义校验，使新测试能杀死这些变异体。"
                )
            if score is not None:
                feedback_lines.append(f"当前变异得分 {score}（越高说明测试越强）；请在新测试中显著提升变异检测能力。")
            if feedback_lines:
                query += "\n\n" + "\n".join(feedback_lines)
                logger.info(
                    "Generator 变异反馈注入：%d 个存活变异体，score=%s",
                    len(survived),
                    score,
                )

        return query

    @staticmethod
    def _check_parametrize_decorator(decorator: ast.AST) -> tuple[list[str], ast.List] | None:
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
    def _validate_case_tuple(elt: ast.expr, param_names: list[str]) -> bool:
        """
        校验单个用例元组的长度是否与参数名数量匹配。

        Args:
            elt: AST 元组/列表节点。
            param_names: 参数名列表。

        Returns:
            True 表示匹配，False 表示不匹配。
        """
        if isinstance(elt, (ast.Tuple, ast.List)) and len(elt.elts) != len(param_names):
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
        # 直接导入底层纯函数（is_similar_module_name 实现于 executor_imports，
        # 经 ExecutorAgent 类属性绑定仅为兼容历史 patch 路径）；避免运行期
        # 依赖类属性挂载，同时消除 mypy attr-defined 误报
        from src.agents.executor_imports import is_similar_module_name

        # 2026-09-26 round9 P2：正则预编译为模块级常量（避免每次调用现场
        # re.compile，--parallel 热路径）。
        matches = _FROM_IMPORT_RE.findall(code)
        for wm in matches:
            # 若已是期望模块名，无需修改
            if wm == expected_module:
                continue
            # 跳过已知的外部包（标准库和测试框架）
            if wm in GeneratorAgent._KNOWN_MODULES:
                continue
            # 相似度门控：仅替换被测模块名的"笔误"变体，保留不相似的第三方库
            if not is_similar_module_name(wm, expected_module):
                continue
            # 2026-09-26 round10 P2：wm 为带点路径（pkg.mod）且代码里
            # 同时存在包形式 `from pkg import mod` 时，裸子串
            # code.replace("from pkg import", ...) 会把包形式行也误改
            # （`from pkg import mod` → `from targetmod import mod`，残留
            # 损坏的 `mod` 导入）。改用按模块名锚定的正则（与
            # executor_imports.apply_import_replacements 同口径），
            # 仅替换精确匹配的 `from {wm} import` 行首。
            # （re.escape 处理带点/带特殊字符的模块名；逐模块现场编译，
            # 数量少且 re 内部 LRU 命中，开销可忽略）
            pattern = re.compile(rf"^from\s+{re.escape(wm)}\s+import\b", re.MULTILINE)
            new_code, n = pattern.subn(f"from {expected_module} import", code)
            if n > 0:
                code = new_code
                logger.warning("Generator 修正了错误模块名：%s → %s", wm, expected_module)
        return code
