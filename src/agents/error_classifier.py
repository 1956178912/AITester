"""
错误分类器模块：将测试失败原因归类为十二类错误，并支持子类型识别。

文本分类优先级（classify() 路径，基于 pytest 输出正则）：LLM_FORMAT_ERROR > IMPORT_ERROR > SYNTAX > TYPE_ERROR
           > INDEX_ERROR > RUNTIME > ASSERTION/LOGIC_ERROR > TIMEOUT > UNKNOWN
状态细化类别（refine_failure_category() 路径，基于任务最终状态信号）：
    - PATCH_VALIDATION_FAILED：补丁被 PatchApplier 安全守卫拒绝
      （repair_history 中 patch_applied=False）；
    - RAG_RETRIEVAL_EMPTY：RAG 启用（rag_stats 非空）但任务内全部
      检索 results==0（检索库冷启动 / 查询与入库案例差异过大）。
使用正则规则匹配而非 LLM，确保分类速度快且结果稳定。
分类结果用于指导 Debugger 选择合适的修复策略。

细粒度说明（P2 优化）：
    - IMPORT_ERROR 从原 SYNTAX 中拆出：缺依赖/导入失败与"代码写错语法"
      的修复路径完全不同（装依赖 vs 重写文件），分开才能精准分诊；
    - TYPE_ERROR 从原 RUNTIME 中拆出：类型不匹配的修复方向是核对参数
      与返回类型，区别于除零/越界等其他运行时异常；
    - LOGIC_ERROR 是 ASSERTION 的子情形：断言失败且失败栈未触及被测
      模块时，更可能是测试用例自身预期值写错（测试逻辑错误），
      修复方向是改测试而非改代码（需 target_module 信息判定）；
    - LLM_FORMAT_ERROR（1.2 残余细化）：LLM 响应格式异常（JSON 解析
      失败 / 响应被截断 / 空响应），此前全部落入 UNKNOWN（占失败样本
      75%，见 docs/failure_analysis.md）。单列后 Debugger 走"重新生成
      响应/放宽 JSON 提取"策略而非通用的 LLM 兜底分析；
    - INDEX_ERROR（1.2 残余细化）：索引越界（IndexError / index out of
      range）从 RUNTIME 拆出。failure_analysis.md 案例 2 显示此类错误
      此前被归入 UNKNOWN，导致 Debugger 无法针对性修复（越界的修复
      方向是补边界判断，而非泛化的运行时异常排查）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol


class ErrorCategory(Enum):
    """
    错误类型枚举，用于分层错误修复策略。

    属性:
        LLM_FORMAT_ERROR: LLM 响应格式异常（JSON 解析失败、响应被
            截断、空响应）（1.2 残余细化：此前归入 UNKNOWN，占失败
            样本 75%，见 docs/failure_analysis.md）
        LLM_EMPTY_RESPONSE: P0 4.1 子类——LLM 返回空响应（空字符串 /
            纯空白），修复策略：用更严格 prompt 重新请求（响应格式
            重试），而非通用 LLM 兜底
        LLM_JSON_PARSE_FAILED: P0 4.1 子类——LLM 响应非空但 JSON
            解析失败（markdown 包裹 / 截断 / 格式错乱），修复策略：
            记录原始响应片段到 failure_knowledge_base.json，Debugger
            用更严格的 JSON 输出约束重新请求
        IMPORT_ERROR: 模块导入失败（ModuleNotFoundError/ImportError），
            通常缺第三方依赖或模块路径错误（P2 细化：从 SYNTAX 拆出）
        SYNTAX: 语法/编译错误，如 SyntaxError、IndentationError
        TYPE_ERROR: 类型不匹配（TypeError），修复方向是核对参数与
            返回类型（P2 细化：从 RUNTIME 拆出）
        INDEX_ERROR: 索引越界（IndexError / index out of range），
            修复方向是补边界判断（1.2 残余细化：从 RUNTIME 拆出，
            此前归入 UNKNOWN 导致 Debugger 无法针对性修复）
        ASSERTION: 断言失败，期望值与实际返回值不一致（失败栈触及被测代码）
        LOGIC_ERROR: 测试逻辑错误（如断言预期值写反），断言失败但失败
            栈未触及被测模块（P2 细化：从 ASSERTION 拆出）
        RUNTIME: 其他运行时异常，如除零、NameError
        TIMEOUT: 执行超时
        UNKNOWN: 无法识别的错误类型
        PATCH_VALIDATION_FAILED: 补丁被安全守卫拒绝（空/过短/无函数
            定义/路径不合法，repair_history 中 patch_applied=False），
            区别于"补丁应用了但测试仍失败"（1.1 状态细化）
        RAG_RETRIEVAL_EMPTY: RAG 启用但任务内全部检索命中为 0
            （rag_stats 非空且所有 results==0），标识 RAG 失效场景
            （1.1 状态细化）
        EXECUTION_TRACE_MISSING: 任务失败但 execution_trace 为空
            （执行器异常路径：executor 节点未正常写入轨迹，或被
            上游崩溃截断），标识"执行轨迹丢失"，便于排查执行器异常
            （5.2 持续细化）
        MULTI_CANDIDATE_ALL_REJECTED: 多候选补丁全部被静态筛选拒绝
            （ENABLE_MULTI_CANDIDATE_PATCH=true 但 N 个候选均未通过
            static_validate_patch），标识多候选策略失效场景（5.2 持续细化）
        PATCH_SYNTAX_INVALID: 补丁经 2.2 重采样（最多 2 次）后仍语法不合法
            （AST 解析失败），已记录到失败知识库（failure_knowledge_base.json
            同口径，由 _patch_applier_node 的重采样统计产出），标识"补丁语法
            反复损坏"场景（2.2 改进，重采样耗尽标记）
    TEST_REGENERATED_PASS_UNVERIFIED: M5（2026-09-29 审查 P0）——测试重生成
            后通过但源码未被修复（regenerate 路由不经过 debugger/patch_applier，
            源码一字未改而测试通过 = 经典 oracle-from-implementation 假成功通道）。
            由 _executor_node 在 regeneration_count>0 且 test_passed=True 时写入
            state["test_regenerated_pass_unverified"]=True；refine_failure_category
            在任务收尾时把该标记归为"不通过"，使假成功率可被实验层度量。
    """

    LLM_FORMAT_ERROR = "llm_format_error"
    # P0 4.1 子类（LLM_FORMAT_ERROR 的两个精确子类）
    LLM_EMPTY_RESPONSE = "llm_empty_response"
    LLM_JSON_PARSE_FAILED = "llm_json_parse_failed"
    IMPORT_ERROR = "import_error"
    SYNTAX = "syntax"
    TYPE_ERROR = "type_error"
    INDEX_ERROR = "index_error"
    ASSERTION = "assertion"
    LOGIC_ERROR = "logic_error"
    RUNTIME = "runtime"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"
    # 1.1 状态细化：两类"流程状态"类别，不走 classify() 文本正则，
    # 由 refine_failure_category() 在任务收尾时按状态信号判定
    PATCH_VALIDATION_FAILED = "patch_validation_failed"
    RAG_RETRIEVAL_EMPTY = "rag_retrieval_empty"
    # 5.2 持续细化：两类"多候选/轨迹"流程类别（refine_failure_category 判定）
    EXECUTION_TRACE_MISSING = "execution_trace_missing"
    MULTI_CANDIDATE_ALL_REJECTED = "multi_candidate_all_rejected"
    # 2.2 改进：重采样耗尽标记（patch_applier.apply_patch_with_resample 统计）
    PATCH_SYNTAX_INVALID = "patch_syntax_invalid"
    # M5（2026-09-29 审查 P0）：测试重生成后通过但源码未修复（regenerate 路由
    # 不经过 debugger/patch_applier，源码一字未改而测试通过 = 经典
    # oracle-from-implementation 假成功通道）。由 _executor_node 在
    # regeneration_count>0 且 test_passed=True 时写入
    # state["test_regenerated_pass_unverified"]=True；refine_failure_category
    # 在任务收尾时把该标记归为"不通过"，使假成功率可被实验层度量。
    TEST_REGENERATED_PASS_UNVERIFIED = "test_regenerated_pass_unverified"


class SyntaxSubtype(Enum):
    """
    Syntax 错误的子类型枚举，用于更精确的诊断和修复策略。

    属性:
        IMPORT_ERROR: 导入错误，如 ModuleNotFoundError、ImportError
        SYNTAX_ERROR: 语法错误，如 SyntaxError、IndentationError
        UNRECOGNIZED: 无法识别的子类型
    """

    IMPORT_ERROR = "import_error"
    SYNTAX_ERROR = "syntax_error"
    UNRECOGNIZED = "unrecognized"


@dataclass
class ErrorContext:
    """
    错误上下文数据结构，包含从错误信息中提取的关键信息。

    属性:
        filename: 出错的文件名（如 missing_module.py）
        line: 出错行号（如 42）
        column: 出错列号（如 10）
        module_name: 缺失的模块名（如 pandas）
        error_message: 完整的错误消息
        subtype: 错误子类型（仅 SYNTAX 类别有值）
    """

    filename: str | None = None
    line: int | None = None
    column: int | None = None
    module_name: str | None = None
    error_message: str = ""
    subtype: SyntaxSubtype | None = None


@dataclass(frozen=True)
class ClassificationResult:
    """
    1. 置信度分类（改进清单 P1）：分类结果 + 置信度 + 低置信度兜底策略。

    属性:
        category: 命中/判定出的错误类别（低置信度时为兜底类别）。
        confidence: 置信度（0.0-1.0）；规则层判定为确定性规则匹配，
            命中即高置信，未命中（UNKNOWN）置信度低。
        confidence_basis: 置信度口径说明（如 "regex_hit" / "fallback_unknown"）。
        fallback_used: 是否使用了低置信度兜底策略（低置信度 + 启用兜底时
            category 会被替换为 fallback_category）。
        fallback_category: 兜底类别（由低置信度兜底策略选出）；None 表示未启用。
        explanation: 可解释性字段（2026-09-29 批次，外部数据支撑："可解释性
            应被视为基础设计原则，而非可选功能"）：为什么选择这个修复策略
            ——命中哪条规则特征 / 被替代的候选类别（top-2 考虑过的类别）/
            兜底是否触发。纯数据口径（零 LLM 成本），供修复报告与 ADR-0013
            可追踪依赖链（错误分类 → 修复策略选择 → 补丁生成 → 验证结果）消费。

    设计（分层预留，见 ADR-0002"已知局限与演进方向"）：
        - L1 规则层：纯正则确定性匹配，零 LLM 成本，命中置信度高（0.9）；
        - L1 兜底层：UNKNOWN / 低命中特征 → confidence 低（0.2）+ 可选
          兜底策略（generic_analysis / 重新生成响应）；
        - L2 概率化 / ML 层：Protocol 预留（_ProbabilisticClassifier），
          高频类别（LLM_BREAKS_IMPORT / PATCH_SYNTAX_INVALID）后续接入
          轻量分类器（如逻辑回归 / 微调小模型）时，L2 输出 top-2 + 置信度，
          L1 低置信度样本可路由给 L2 精判（当前 L2 未实现，恒 None →
          走 L1 兜底，行为与历史一致；落地 L2 需独立 ADR + 回归守卫）。
    """

    category: ErrorCategory
    confidence: float
    confidence_basis: str
    fallback_used: bool = False
    fallback_category: ErrorCategory | None = None
    explanation: str = ""


class ProbabilisticClassifier(Protocol):
    """
    L2 概率化 / ML 分类层接口预留（改进清单 #1，分层架构 L2 层）。

    当前无默认实现（_default_probabilistic_classifier 恒返回 None），
    高频类别（LLM_BREAKS_IMPORT / PATCH_SYNTAX_INVALID）后续接入轻量
    ML 分类器（逻辑回归 / 微调小 BERT 等）时实现本协议，经
    classify_with_confidence(classifier=...) 注入 L1 低置信度样本精判。
    L1 规则层保持零 LLM 成本、确定性可复现（ADR-0002 口径不变）。
    """

    def predict(
        self,
        combined_text: str,
        target_module: str | None,
    ) -> tuple[ErrorCategory, float]:
        """返回 (类别, 置信度 0.0-1.0)。"""
        ...


def _default_probabilistic_classifier() -> ProbabilisticClassifier | None:
    """L2 分类层默认实现：当前未落地，恒返回 None（走 L1 兜底，历史行为不变）。"""
    return None


# ─── 预编译正则表达式（避免重复编译开销）─────────────────────────────────────
# Import Error 检测模式
_RE_MODULE_NOT_FOUND = re.compile(r"ModuleNotFoundError:\s*No module named\s+'(\w+)'", re.IGNORECASE)
_RE_IMPORT_ERROR = re.compile(r"ImportError:\s*cannot import name\s+'(\w+)'", re.IGNORECASE)
# Syntax Error 检测模式
_RE_SYNTAX_ERROR_FILE_LINE = re.compile(r"(\w+\.py):(\d+):(\d+):\s*(.+)")
_RE_PYTEST_SYNTAX = re.compile(r"E\s*\S+\.py:(\d+):(\d+)", re.IGNORECASE)
_RE_TRACEBACK = re.compile(r'File\s+"([^"]+)",\s*line\s+(\d+)')
# 2026-10 P0（A/B 阴性结果驱动）：pytest --tb=short 帧行模式。
# short 模式省略 "File "...", line N" 完整帧，改为紧凑行
# "path/to/module.py:6: in get_option"（被测模块帧），
# "test_file.py:8: in test_x"（测试帧），末尾 "E   异常类型: 消息"。
# 此前 _RE_TRACEBACK 只匹配完整帧形式 → --tb=short 下
# extract_error_context 提取不到 filename/line → _locate_repair_focus
# 的 context.line 恒 None → 定位阶段 0/30 命中（A/B 阴性根因）。
# 本模式捕获被测模块帧（排除 E 开头的异常消息行），供
# extract_error_context 在完整帧缺失时降级匹配。
# 口径注意：_RE_TRACEBACK 的 group(1) 是完整路径（"path/to/module.py"），
# 本模式 group(1) 是 basename（"module.py"）——消费方（_locate_repair_focus
# 的跨文件保护、_is_test_side_assertion 的 endswith 判定）均按 basename
# 口径工作，两者在下游可互换。
# 帧行在 pytest --tb=short 输出中按调用栈深度排序（外层/测试帧先出现，
# 最内层/被测模块帧最后出现），故消费方取 findall 的**最后一个**匹配
# 即被测模块帧；纯测试侧断言失败（无被测模块帧）时最后匹配是测试帧，
# 由 _locate_repair_focus 跨文件保护兜底（focused=False，不误定位）。
# 行首路径前缀用 (?:[\w\-\./]+/)* 匹配（目录段可含点/斜杠/下划线，
# 覆盖 macOS 临时目录 /var/folders/pj/x/.../T/tmpXXXX/ 的完整路径形态）；
# basename 帧行（行首无目录）时前缀组为空，捕获组 1 始终是 basename。
# 实测（L2.5 验证）：被测模块帧形如
# "/var/.../tmpXXXX/runtime_index_error_boundary_0002.py:5: in first_and_last"
# （行首完整路径），前缀组需能匹配整段路径，不能只吃字母数字段。
_RE_TRACEBACK_SHORT_FRAME = re.compile(r"^(?:[\w\-\./]+/)*([\w\.\-]+\.py):(\d+):\s+in\s+(\w+)", re.MULTILINE)


# Runtime Error 检测模式
_RE_RUNTIME_ERRORS = [
    re.compile(r"ZeroDivisionError", re.IGNORECASE),
    re.compile(r"TypeError", re.IGNORECASE),
    re.compile(r"ValueError", re.IGNORECASE),
    re.compile(r"KeyError", re.IGNORECASE),
    re.compile(r"IndexError", re.IGNORECASE),
    re.compile(r"AttributeError", re.IGNORECASE),
    re.compile(r"RecursionError", re.IGNORECASE),
    re.compile(r"NameError", re.IGNORECASE),
    # O35（2026-09-30 全面审查 P1）：JSONDecodeError 是被测代码极常见的运行时
    # 异常（解析外部输入必踩）。pytest 输出形态的样本在第 1 步被
    # _RE_PYTEST_OUTPUT 挡掉 LLM 格式分支后，此前会一路落到 UNKNOWN(0.2)
    # 触发通用兜底——现在归 RUNTIME(0.9)，走"分析异常栈定位 bug 函数"策略。
    # 非 pytest 形态的裸 "json.decoder.JSONDecodeError: …" 仍在第 1 步被
    # LLM 格式分支接走（历史口径不变，既有单测锁定）。
    re.compile(r"JSONDecodeError", re.IGNORECASE),
]
# Assertion Error 检测模式
_RE_ASSERTION_ERRORS = [
    re.compile(r"AssertionError", re.IGNORECASE),
    re.compile(r"assert\s+", re.IGNORECASE),
    re.compile(r"Expected.*but got", re.IGNORECASE),
]
# Timeout Error 检测模式
_RE_TIMEOUT_ERRORS = [
    re.compile(r"timeout", re.IGNORECASE),
    re.compile(r"TimedOut", re.IGNORECASE),
    re.compile(r"Test ran for longer than", re.IGNORECASE),
]
# Type Error 检测模式（从 RUNTIME 拆出的独立类别：类型不匹配）
_RE_TYPE_ERROR = re.compile(r"\bTypeError\b", re.IGNORECASE)
# Index Error 检测模式（从 RUNTIME 拆出的独立类别：索引越界，1.2 残余细化）
# IndexError / "index out of range" / 中文"下标越界"三类表述
_RE_INDEX_ERROR = re.compile(r"\bIndexError\b|index out of range|下标越界", re.IGNORECASE)
# LLM Format Error 检测模式（LLM 响应格式异常，1.2 残余细化）
# 覆盖 failure_analysis.md 记录的三类特征：JSON 解析失败（Could not find
# complete JSON / Expecting value / JSONDecodeError）、响应截断（incomplete/
# truncated）、空响应（empty response）
_RE_LLM_FORMAT_ERRORS = [
    re.compile(r"JSONDecodeError", re.IGNORECASE),
    re.compile(r"Expecting value", re.IGNORECASE),
    re.compile(r"Could not find complete JSON", re.IGNORECASE),
    re.compile(r"JSON.*解析失败|解析.*JSON.*失败", re.IGNORECASE),
    re.compile(r"empty response|响应为空|空响应", re.IGNORECASE),
    re.compile(r"incomplete response|truncated response|响应被截断|响应截断", re.IGNORECASE),
]
# O35（2026-09-30 全面审查 P1）：pytest 输出形态标记。
# _is_llm_format_error 的关键词（JSONDecodeError / Expecting value /
# empty response…）同时是**被测代码**最常见的运行时异常文本——
# `FAILED tests/test_parser.py::test_parse - json.decoder.JSONDecodeError:
# Expecting value…` 这类真实测试失败此前被 L1 链条第 1 优先级以 0.9 置信
# 判成 LLM_FORMAT_ERROR，修复 prompt 注入"请重新请求 LLM 生成合规响应"
# （对着被测代码毫无意义），失败统计也随之失真。
# LLM 响应格式异常本身**不会**出现在 pytest 输出里（它发生在 LLM 调用侧，
# 由 classify_llm_response 单独判定），故：命中下列任一 pytest 形态即
# 说明文本是测试输出 → 跳过 LLM 格式分支，让后续规则按真实异常判定。
#   - 测试节点 id（path.py::test_name）
#   - pytest 汇总头（FAILED/ERRORS 行、short test summary info、分隔线）
#   - traceback 帧（file.py:NN: in func）/ pytest 断言详情缩进（E 开头）
_RE_PYTEST_OUTPUT = re.compile(
    r"\.py::|^\s*(?:FAILED|ERROR)\s+\S+\.py|short test summary info|_{5,}\s*(?:FAILURES|ERRORS)"
    r"|\.py:\d+:\s*in\s+\S+|^\s*E\s{2,}\S",
    re.IGNORECASE | re.MULTILINE,
)
# 语法错误关键词（模块级常量，避免每次 _is_syntax_error 调用重复构建列表）
_SYNTAX_ERROR_KEYWORDS = (
    "SyntaxError",
    "ImportError",
    "ModuleNotFoundError",
    "IndentationError",
    "TabError",
    "IncompleteInput",
)
# ───────────────────────────────────────────────────────────────────────────


class ErrorClassifier:
    """
    测试失败原因分类器。

    根据 pytest 输出文本判断错误类别，为 Debugger 提供结构化输入。
    使用规则匹配而非 LLM，确保分类速度快且结果稳定。

    分类优先级（由高到低）：
    1. LLM_FORMAT_ERROR - LLM 响应格式异常：JSON 解析失败/截断/空响应，
        单列后 Debugger 走"重新生成响应/放宽 JSON 提取"策略
    2. IMPORT_ERROR - 导入错误：缺依赖/路径错误
    3. SYNTAX - 语法错误：无需语义分析，直接让 LLM 重写整个文件
    4. TYPE_ERROR - 类型不匹配：核对参数与返回类型
    5. INDEX_ERROR - 索引越界：补边界判断（此前落入 RUNTIME/UNKNOWN）
    6. RUNTIME - 其他运行时异常：需分析异常栈，定位 bug 所在函数
    7. ASSERTION/LOGIC_ERROR - 断言失败：判断是代码逻辑错误还是测试
        预期值错误
    8. TIMEOUT - 执行超时：通常说明被测函数存在死循环
    9. UNKNOWN - 无法识别：交由 LLM 自行分析
    """

    # 2026-09-26 优化：classify_with_context() 内部调用 classify() 时共享
    # 已构建的合并文本，避免对同一 test_output + failed_cases 做两次 O(n) 拼接。

    def classify(
        self,
        test_output: str,
        failed_cases: list[dict],
        target_module: str | None = None,
        _combined: str | None = None,
    ) -> ErrorCategory:
        """
        根据测试输出和失败用例分类错误类型。

        分类优先级：LLM_FORMAT_ERROR > IMPORT_ERROR > SYNTAX > TYPE_ERROR
                    > INDEX_ERROR > RUNTIME > ASSERTION/LOGIC_ERROR
                    > TIMEOUT > UNKNOWN
        规则匹配优先于 LLM 兜底分类。
        LLM_FORMAT_ERROR 置于最高优先级：JSON 解析失败文本中几乎不会
        出现 IndexError，但 IndexError 文本中可能出现 assert，顺序放反
        会误判。

        合并策略：将 test_output 和最多前 3 个 failed_cases 的 error 信息拼接后统一匹配，
        确保能从失败用例的详细错误信息中识别出错误类型。

        Args:
            test_output: pytest 完整输出文本。
            failed_cases: 失败用例列表，每项含 name 和 error 字段。
            target_module: 被测模块名（不含 .py）。提供时用于区分
                ASSERTION（代码 bug）与 LOGIC_ERROR（测试预期值写错）：
                断言失败且失败栈未触及被测模块时归类为 LOGIC_ERROR。
            _combined: 内部参数——已合并文本（classify_with_context 传入，
                避免重复拼接）。外部调用者无需传此参数。

        Returns:
            最匹配的 ErrorCategory 枚举值。
        """
        # 合并 test_output 和 failed_cases 的 error 信息用于分类
        # 最多取前 3 个失败用例的错误信息，避免过长
        if _combined is not None:
            combined = _combined
        else:
            combined = test_output + "\n" + "\n".join(case.get("error", "") for case in failed_cases[:3])

        # 委托给纯数据判定路径（与 classify_with_context 共享同一实现）
        return self._classify_combined(combined, target_module)

    # 1. 置信度分层（改进清单 P1）：L1 规则层命中即高置信；未命中（UNKNOWN）
    # 或"宽松弱匹配"（如 _is_syntax_error 仅靠通用 file.py:line:col 格式命中、
    # 无具体异常关键词）为低置信样本 → 触发低置信度兜底策略（generic_analysis），
    # 而非硬性路由。L2 概率化/ML 层经 ProbabilisticClassifier 协议预留
    # （当前 _default_probabilistic_classifier 恒 None，落地 L2 需独立 ADR）。
    _CONFIDENCE_RULE_HIT = 0.9
    _CONFIDENCE_RULE_WEAK = 0.5
    _CONFIDENCE_FALLBACK = 0.2
    # 置信度门槛：低于该值视为"低置信度"，触发兜底策略。
    # 注意：门槛取 0.5，使"弱命中"（confidence=0.5）同样触发兜底
    # （弱命中 = 仅通用格式命中、无具体异常特征，需 LLM 兜底确认而非硬性路由）。
    _LOW_CONFIDENCE_THRESHOLD = 0.5
    # 低置信度兜底策略：UNKNOWN → 通用 LLM 分析（generic_analysis）；
    # 弱命中的 SYNTAX → 走 LLM 兜底而非硬性"重写整文件"路由
    _FALLBACK_CATEGORY = ErrorCategory.UNKNOWN

    def _classify_combined(self, combined: str, target_module: str | None) -> ErrorCategory:
        """对已合并文本按优先级顺序做类别判定（纯数据路径，零正则重复）。

        2026-09-26 优化：classify() 与 classify_with_context() 共享此方法，
        避免对同一合并文本做两套独立判定逻辑（正则已预编译，判定本身为
        O(1) 查表 + 正则搜索，无重复编译开销）。
        1. 置信度分层（改进清单 P1）：经 classify_with_confidence 内核判定，
        历史 17 类口径逐样本等价（enable_fallback=False 时兜底不触发）。
        """
        return self.classify_with_confidence(combined, target_module, enable_fallback=False).category

    def classify_with_confidence(
        self,
        combined_or_test_output: str,
        target_module: str | None = None,
        failed_cases: list[dict] | None = None,
        *,
        _combined: str | None = None,
        classifier: ProbabilisticClassifier | None = None,
        enable_fallback: bool = True,
    ) -> ClassificationResult:
        """
        1. 置信度分层分类（改进清单 P1，L1 规则层 + L2 预留 + 低置信度兜底）。

        在 classify() 的优先级判定基础上输出置信度，并对低置信度样本触发
        兜底策略（而非硬性路由）：
        - L1 规则命中（具体异常关键词/模块名/行号）→ confidence=0.9（高）；
        - L1 弱命中（仅通用格式命中、无具体特征）→ confidence=0.5（低）；
        - L1 未命中（UNKNOWN）→ confidence=0.2（低）；
        - 低置信度 + enable_fallback=True → 触发兜底策略（generic_analysis），
          fallback_category=UNKNOWN，fallback_used=True；
        - 低置信度 + classifier（L2 概率化/ML 层）提供时，优先用 L2 精判
          （当前 L2 恒 None，走 L1 兜底，行为与历史一致）。

        与 classify() 的关系：分类结果（category 在不启用兜底时）与历史 17 类
        口径逐样本等价（enable_fallback=False / classifier=None 时兜底不触发）。

        Args:
            combined_or_test_output: 已合并文本（_combined 显式传入时忽略此参数；
                否则作为 test_output 与 failed_cases 拼接）。
            target_module: 被测模块名（见 classify() 说明）。
            failed_cases: 失败用例列表（拼接用，见 classify() 说明）。
            _combined: 内部参数——已合并文本（避免重复拼接）。
            classifier: L2 概率化/ML 分类器（Protocol）；None 时走 L1 兜底。
            enable_fallback: 是否对低置信度样本触发兜底策略（默认 True）。

        Returns:
            ClassificationResult（category / confidence / confidence_basis /
            fallback_used / fallback_category）。
        """
        # 合并文本（与 classify 同口径：_combined 优先，否则 test_output + 前3用例）
        if _combined is not None:
            combined = _combined
        else:
            cases = failed_cases or []
            combined = combined_or_test_output + "\n" + "\n".join(c.get("error", "") for c in cases[:3])

        # L1 规则层：判定类别 + 置信度
        category, confidence, basis = self._classify_confidence(combined, target_module)

        # L2 精判（预留）：低置信度样本且提供 L2 分类器时，用 L2 top-1 精判
        if confidence <= self._LOW_CONFIDENCE_THRESHOLD and classifier is not None:
            l2_cat, l2_conf = classifier.predict(combined, target_module)
            if l2_conf > self._LOW_CONFIDENCE_THRESHOLD:
                category, confidence, basis = l2_cat, l2_conf, "l2_probabilistic"

        # 低置信度兜底策略（改进清单 P1：低置信度触发兜底而非硬性路由）
        fallback_used = False
        fallback_category: ErrorCategory | None = None
        if enable_fallback and confidence <= self._LOW_CONFIDENCE_THRESHOLD:
            fallback_used = True
            fallback_category = self._FALLBACK_CATEGORY
            # 兜底不改变已判定类别（若已命中具体类），仅标记"该走通用兜底"；
            # 若类别为 UNKNOWN/弱命中 SYNTAX，则收敛到兜底类别（generic_analysis）
            if category in (ErrorCategory.UNKNOWN, ErrorCategory.SYNTAX):
                category = self._FALLBACK_CATEGORY
                basis = "fallback_unknown"

        # 可解释性字段（2026-09-29 批次）：说明"为什么选这个类别 + 替代
        # 候选被放弃的原因"，供修复报告 / ADR-0013 可追踪依赖链消费。
        explanation = self._build_explanation(category, confidence, basis, fallback_used, combined, target_module)

        return ClassificationResult(
            category=category,
            confidence=confidence,
            confidence_basis=basis,
            fallback_used=fallback_used,
            fallback_category=fallback_category,
            explanation=explanation,
        )

    def _build_explanation(
        self,
        category: ErrorCategory,
        confidence: float,
        basis: str,
        fallback_used: bool,
        combined: str,
        target_module: str | None,
    ) -> str:
        """构建可解释性说明（纯数据口径，零 LLM 成本；ADR-0013 追踪链第 1 环）。"""
        parts: list[str] = []
        # 命中的规则特征（为什么是这个类别）
        if category == ErrorCategory.LLM_FORMAT_ERROR:
            parts.append("命中 LLM 响应格式异常特征（JSON 解析失败/截断/空响应关键词）")
        elif category == ErrorCategory.IMPORT_ERROR:
            module = self._extract_import_module_name(combined)
            parts.append("命中导入错误特征" + (f"（缺失模块 {module}）" if module else ""))
        elif category == ErrorCategory.SYNTAX:
            parts.append(
                "命中语法错误特征"
                if self._has_concrete_syntax_feature(combined)
                else "仅通用 file.py:line:col 格式命中（弱命中）"
            )
        elif category == ErrorCategory.TYPE_ERROR:
            parts.append("命中 TypeError 异常关键词")
        elif category == ErrorCategory.INDEX_ERROR:
            parts.append("命中 IndexError / 越界表述")
        elif category == ErrorCategory.RUNTIME:
            parts.append("命中运行时异常关键词（ZeroDivision/Value/Key/Attribute/Recursion/Name 等）")
        elif category == ErrorCategory.ASSERTION:
            parts.append("命中断言失败特征（失败栈触及被测代码）")
        elif category == ErrorCategory.LOGIC_ERROR:
            parts.append(f"断言失败且失败栈未触及被测模块（{target_module or '未知模块'}），判定测试侧逻辑错误")
        elif category == ErrorCategory.TIMEOUT:
            parts.append("命中超时特征（死循环/无限递归嫌疑）")
        elif category == ErrorCategory.UNKNOWN:
            parts.append("未命中任何具体规则特征，落入通用兜底")
        else:
            parts.append(f"状态细化类别 {category.value}")
        # 置信度口径
        parts.append(f"置信度 {confidence:.2f}（{basis}）")
        # 兜底触发
        if fallback_used:
            parts.append("低置信度 → 触发兜底策略（generic_analysis），替代硬性路由")
        return "；".join(parts)

    def _classify_confidence(self, combined: str, target_module: str | None) -> tuple[ErrorCategory, float, str]:
        """L1 规则层置信度判定（classify_with_confidence 的内核，纯数据路径）。

        在 _classify_combined 的优先级链上叠加置信度口径：
        - 具体特征命中（模块名 / 行号 / 异常关键词）→ 0.9；
        - 仅通用格式命中（_is_syntax_error 靠 file.py:line:col 或 E 前缀，
          无具体异常关键词）→ 0.5；
        - 未命中（UNKNOWN）→ 0.2。

        Returns:
            (类别, 置信度, 置信度口径说明)。
        """
        # 1. LLM 响应格式异常（具体特征：JSON 解析失败 / 空响应关键词）→ 高置信
        # O35（2026-09-30 全面审查 P1）：仅当文本**不是** pytest 输出时才适用
        # ——否则被测代码自身的 JSONDecodeError / "empty response" 等会被误判
        # 成 LLM 格式异常（详见 _RE_PYTEST_OUTPUT 注释）。pytest 形态的样本
        # 落到下方规则链按真实异常类判定。
        if not _RE_PYTEST_OUTPUT.search(combined) and self._is_llm_format_error(combined):
            return ErrorCategory.LLM_FORMAT_ERROR, self._CONFIDENCE_RULE_HIT, "regex_hit"
        # 2. Import 错误（具体特征：缺失模块名可提取 → 高置信；否则中置信）
        if self._is_import_error(combined):
            conf = (
                self._CONFIDENCE_RULE_HIT if self._extract_import_module_name(combined) else self._CONFIDENCE_RULE_WEAK
            )
            return ErrorCategory.IMPORT_ERROR, conf, "regex_hit"
        # 3. Syntax 错误（细分子类型判定置信度：具体语法关键词 → 高；仅通用
        #    格式命中 → 低，触发兜底）
        if self._is_syntax_error(combined):
            conf = (
                self._CONFIDENCE_RULE_HIT if self._has_concrete_syntax_feature(combined) else self._CONFIDENCE_RULE_WEAK
            )
            return ErrorCategory.SYNTAX, conf, "regex_hit" if conf >= self._CONFIDENCE_RULE_HIT else "regex_weak"
        # 4. Type 错误 → 高置信
        if self._is_type_error(combined):
            return ErrorCategory.TYPE_ERROR, self._CONFIDENCE_RULE_HIT, "regex_hit"
        # 5. Index 越界 → 高置信
        if self._is_index_error(combined):
            return ErrorCategory.INDEX_ERROR, self._CONFIDENCE_RULE_HIT, "regex_hit"
        # 6. Runtime 错误 → 高置信
        if self._is_runtime_error(combined):
            return ErrorCategory.RUNTIME, self._CONFIDENCE_RULE_HIT, "regex_hit"
        # 7. Assertion 错误（测试侧逻辑 → LOGIC_ERROR；否则 ASSERTION）→ 高置信
        if self._is_assertion_error(combined):
            if target_module and self._is_test_side_assertion(combined, target_module):
                return ErrorCategory.LOGIC_ERROR, self._CONFIDENCE_RULE_HIT, "regex_hit"
            return ErrorCategory.ASSERTION, self._CONFIDENCE_RULE_HIT, "regex_hit"
        # 8. Timeout 错误 → 高置信
        if self._is_timeout_error(combined):
            return ErrorCategory.TIMEOUT, self._CONFIDENCE_RULE_HIT, "regex_hit"
        # 未命中 → UNKNOWN（低置信度，触发兜底）
        return ErrorCategory.UNKNOWN, self._CONFIDENCE_FALLBACK, "fallback_unknown"

    @staticmethod
    def _extract_import_module_name(text: str) -> str | None:
        """提取缺失模块名（ImportError/ModuleNotFoundError）；无则 None。"""
        m = _RE_MODULE_NOT_FOUND.search(text) or _RE_IMPORT_ERROR.search(text)
        return m.group(1) if m else None

    @staticmethod
    def _has_concrete_syntax_feature(text: str) -> bool:
        """是否存在具体语法错误特征（异常关键词或 file.py:line:col 定位）。

        具体特征 = 命中语法异常关键词（SyntaxError/IndentationError/TabError/
        IncompleteInput 等，**不含** 泛化的 ImportError/ModuleNotFoundError——
        那些已由 IMPORT_ERROR 分支先判定）。仅靠通用 file.py:line:col / E
        前缀定位而无上述关键词时视为"弱命中"（低置信样本，触发兜底）。
        """
        concrete_keywords = ("SyntaxError", "IndentationError", "TabError", "IncompleteInput")
        return any(kw in text for kw in concrete_keywords)

    def classify_with_context(
        self,
        test_output: str,
        failed_cases: list[dict[str, Any]],
        target_module: str | None = None,
    ) -> tuple[ErrorCategory, ErrorContext]:
        """
        分类错误类型并提取错误上下文。

        这是 classify() 的增强版本，额外返回 ErrorContext 对象，
        包含文件名、行号、列号、缺失模块名等详细信息。

        Args:
            test_output: pytest 完整输出文本。
            failed_cases: 失败用例列表，每项含 name 和 error 字段。
            target_module: 被测模块名（可选，见 classify() 说明）。

        Returns:
            (category, context) 元组，category 是 ErrorCategory，
            context 是 ErrorContext 对象。
        """
        # 2026-09-26 性能优化：一次构建合并文本供 classify() 与
        # extract_error_context() 共享（此前各自独立构建，对同一
        # test_output + failed_cases 做了两次 O(n) 拼接）。
        # 注意：classify() 默认路径只取前 3 个 failed_cases（避免过长文本），
        # 但 extract_error_context() 取全部 failed_cases（取最后的 traceback 帧）。
        # 此处统一取全部 failed_cases 构建 combined（与 extract 口径一致），
        # classify() 收到 _combined 后直接使用（不再截前 3），
        # 保证 classify_with_context() 的分类结果与 extract_error_context() 所用
        # 文本范围一致（否则 4+ 用例时分类与提取基于不同文本范围，
        # 导致同一任务在 reports/generator 与 debugger 中分类结果不一致）。
        # 默认路径 classify()（_combined=None）仍截前 3，历史口径不变。
        combined = test_output + "\n" + "\n".join(case.get("error", "") for case in failed_cases)
        category = self.classify(test_output, failed_cases, target_module=target_module, _combined=combined)
        context = self._extract_error_context_from_combined(combined)
        return category, context

    def extract_error_context(self, test_output: str, failed_cases: list[dict]) -> ErrorContext:
        """
        提取错误上下文信息，包括文件名、行号、列号、模块名等。

        分析错误输出文本，提取关键诊断信息，帮助 Debugger 精确定位问题。

        Args:
            test_output: pytest 完整输出文本。
            failed_cases: 失败用例列表。

        Returns:
            ErrorContext 对象，包含提取的上下文信息。
        """
        # 合并所有错误信息
        combined = test_output + "\n" + "\n".join(case.get("error", "") for case in failed_cases)
        return self._extract_error_context_from_combined(combined)

    def _extract_error_context_from_combined(self, combined: str) -> ErrorContext:
        """从已合并文本提取错误上下文（纯数据路径，零拼接开销）。

        2026-09-26 优化：extract_error_context() 与 classify_with_context()
        共享此方法，对同一合并文本只做一次 O(n) 正则扫描。
        """
        # 清理错误消息：去除首尾空白，避免空消息包含换行符
        cleaned_message = combined.strip()[:500]
        context = ErrorContext(error_message=cleaned_message)

        # 尝试提取模块名称（ImportError/ModuleNotFoundError）
        module_match = _RE_MODULE_NOT_FOUND.search(combined)
        if module_match:
            context.module_name = module_match.group(1)
            context.subtype = SyntaxSubtype.IMPORT_ERROR
            return context

        import_name_match = _RE_IMPORT_ERROR.search(combined)
        if import_name_match:
            context.module_name = import_name_match.group(1)
            context.subtype = SyntaxSubtype.IMPORT_ERROR
            return context

        # 尝试提取文件路径、行号、列号（SyntaxError/IndentationError 等）
        file_line_match = _RE_SYNTAX_ERROR_FILE_LINE.search(combined)
        if file_line_match:
            context.filename = file_line_match.group(1)
            context.line = int(file_line_match.group(2))
            context.column = int(file_line_match.group(3))
            context.subtype = SyntaxSubtype.SYNTAX_ERROR
            return context

        # pytest 格式：E   path/file.py:line:col
        pytest_match = _RE_PYTEST_SYNTAX.search(combined)
        if pytest_match:
            context.line = int(pytest_match.group(1))
            context.column = int(pytest_match.group(2))
            context.subtype = SyntaxSubtype.SYNTAX_ERROR
            return context

        # 尝试从 traceback 中提取文件名
        # 使用 findall 获取所有匹配，取最后一个（最深的调用栈）
        # 注意：任意 Python traceback（含纯运行时错误）都会命中该模式，
        # 因此这里不赋 subtype——subtype 仅由 import/语法错误分支设置，
        # 否则 RUNTIME 类错误会被误标为 syntax_error 子类型
        traceback_matches = _RE_TRACEBACK.findall(combined)
        if traceback_matches:
            # 取最后一个匹配（最深处的文件）
            context.filename = traceback_matches[-1][0]
            context.line = int(traceback_matches[-1][1])
            return context

        # 2026-10 P0（A/B 阴性结果驱动）：pytest --tb=short 帧行降级匹配。
        # --tb=short 省略 "File "...", line N" 完整帧，改为紧凑帧行
        # "module.py:6: in get_option"。完整帧缺失时按多行匹配捕获
        # "被测模块帧 + 测试帧"。
        # 关键口径：失败栈中**被测模块帧在文本上位于测试帧之后**
        # （pytest 帧行按调用栈深度排序：外层/测试帧先出现，最内层/
        # 被测模块帧最后出现），故取**最后一个**匹配帧行（即被测模块帧），
        # 而非"优先非 test 帧"（此前误判：测试帧总在前，非 test 帧
        # 后取会命中被测模块帧——但取"最后一个非 test 帧"在纯测试
        # 帧失败时回退到测试帧本身，定位到测试代码而非被测代码）。
        # 统一取最后一个匹配 + 由下游 _locate_repair_focus 的跨文件
        # 保护（context.filename 与 target_module 不符时 focused=False）
        # 兜底"测试侧断言失败"误定位场景。不赋 subtype（与完整帧
        # 分支同口径：仅定位，不改错误分类）。
        short_frames = _RE_TRACEBACK_SHORT_FRAME.findall(combined)
        if short_frames:
            # findall 返回 3 元组 [(file, line, func), ...]（basename 口径）；
            # 取最后一个匹配帧行（--tb=short 帧行按调用栈深度排序：外层/
            # 测试帧先出现，被测模块帧最后出现；纯测试帧失败时取到测试帧，
            # 由 _locate_repair_focus 跨文件保护兜底不误定位）
            picked = short_frames[-1]
            context.filename = picked[0]
            context.line = int(picked[1])
            return context

        return context

    @staticmethod
    def _is_syntax_error(text: str) -> bool:
        """检查是否为 Syntax 错误（导入错误或语法错误）。"""
        # 检查导入错误
        if _RE_MODULE_NOT_FOUND.search(text) or _RE_IMPORT_ERROR.search(text):
            return True
        # 检查语法错误关键词
        if any(kw in text for kw in _SYNTAX_ERROR_KEYWORDS):
            return True
        # 检查 pytest 冒号格式：file.py:line:col: error
        if _RE_SYNTAX_ERROR_FILE_LINE.search(text):
            return True
        # 检查 E prefix 格式：E   file.py:line:col
        return bool(_RE_PYTEST_SYNTAX.search(text))

    @staticmethod
    def _is_import_error(text: str) -> bool:
        """检查是否为 Import 错误（缺模块/缺依赖，从 SYNTAX 拆出的独立类别）。"""
        if _RE_MODULE_NOT_FOUND.search(text) or _RE_IMPORT_ERROR.search(text):
            return True
        return "ImportError:" in text

    @staticmethod
    def _is_type_error(text: str) -> bool:
        """检查是否为 Type 错误（TypeError，从 RUNTIME 拆出的独立类别）。"""
        return bool(_RE_TYPE_ERROR.search(text))

    @staticmethod
    def _is_index_error(text: str) -> bool:
        """检查是否为 Index 越界错误（1.2 残余细化：从 RUNTIME 拆出）。

        匹配 IndexError 异常名、"index out of range" 标准报错与中文"下标越界"。
        """
        return bool(_RE_INDEX_ERROR.search(text))

    # P0 4.1 子类拆分：LLM_FORMAT_ERROR 进一步细分为空响应 / JSON 解析失败
    _RE_LLM_EMPTY_RESPONSE = re.compile(
        r"empty response|响应为空|空响应|response.*empty|empty.*response", re.IGNORECASE
    )
    _RE_LLM_JSON_PARSE_FAILED = re.compile(
        r"JSONDecodeError|Expecting value|Could not find complete JSON|JSON.*解析失败|解析.*JSON.*失败|JSON.*parse.*fail",
        re.IGNORECASE,
    )

    @classmethod
    def classify_llm_response(cls, raw_response: str) -> ErrorCategory:
        """P0 4.1：将 LLM 原始响应直接分类为空响应 / JSON 解析失败 / 格式正常。

        与 classify()（基于 pytest 文本）不同，本方法在 Debugger 收到
        LLM 响应后、JSON 解析前调用，把"LLM 响应格式异常"从 UNKNOWN 拆
        为两个精确子类（占失败样本 75% 的 UNKNOWN 根因之一）：
        - 空响应（strip 后为空 / 纯空白）→ LLM_EMPTY_RESPONSE
        - 非空但 JSON 提取失败（_try_extract_json 抛异常）→ LLM_JSON_PARSE_FAILED
        - 正常解析成功 → LLM_FORMAT_ERROR（保留语义：格式异常大类）

        Args:
            raw_response: LLM 原始响应文本。

        Returns:
            对应的 ErrorCategory 枚举值。
        """
        # 空响应检测（P0 4.1 LLM_EMPTY_RESPONSE 子类）
        if not raw_response or not raw_response.strip():
            return ErrorCategory.LLM_EMPTY_RESPONSE
        # 非空响应：尝试 JSON 提取
        try:
            # 提取 JSON 对象（含 markdown 包裹 / 前后自然语言容忍）
            from src.utils.helpers import extract_json_object

            extracted = extract_json_object(raw_response)
            if extracted is None:
                # 非空但无法提取 JSON → JSON 解析失败
                return ErrorCategory.LLM_JSON_PARSE_FAILED
            # 提取成功但内容异常（空 dict）仍视为格式问题
            if isinstance(extracted, dict) and not extracted:
                return ErrorCategory.LLM_JSON_PARSE_FAILED
        except Exception:
            return ErrorCategory.LLM_JSON_PARSE_FAILED
        # 正常响应
        return ErrorCategory.LLM_FORMAT_ERROR

    @staticmethod
    def _is_llm_format_error(text: str) -> bool:
        """检查是否为 LLM 响应格式异常（1.2 残余细化）。

        匹配 JSON 解析失败（JSONDecodeError/Expecting value/Could not find
        complete JSON）、空响应、响应截断三类特征（见 _RE_LLM_FORMAT_ERRORS）。
        """
        return any(pattern.search(text) for pattern in _RE_LLM_FORMAT_ERRORS)

    @staticmethod
    def _is_test_side_assertion(text: str, target_module: str) -> bool:
        """判断断言失败是否发生在测试侧（而非被测代码）——LOGIC_ERROR 判定。

        依据：pytest --tb=short 输出的 traceback 帧（File "..." 行）。
        若失败栈存在、且没有任何一帧指向被测模块文件，则断言失败源于
        测试用例自身的逻辑（如预期值写反），而非被测代码 bug。
        无法提取到帧信息时保守判定为 False（归 ASSERTION，交给 LLM 分诊）。

        Args:
            text: 合并后的错误文本。
            target_module: 被测模块名（不含 .py）。

        Returns:
            True 表示断言失败发生在测试侧（LOGIC_ERROR）。
        """
        frames = _RE_TRACEBACK.findall(text)
        if not frames:
            return False
        # 任何一帧落在被测模块文件上即视为被测代码问题（非测试侧逻辑错误）。
        # 用 endswith 而非 basename 全等：pytest 帧为完整路径；旧版三个子句
        # （basename==file / basename==module / endswith）中前两个是 endswith
        # 的子集（帧几乎总带 .py 后缀，无后缀帧在 pytest traceback 中不出现），
        # 收敛为单一 endswith 判断（"mycalc.py" 误中 "calc.py" 的既有限制保留）
        target_file = f"{target_module}.py"
        return all(not frame_file.endswith(target_file) for frame_file, _line in frames)

    @staticmethod
    def _is_runtime_error(text: str) -> bool:
        """检查是否为 Runtime 错误。"""
        return any(pattern.search(text) for pattern in _RE_RUNTIME_ERRORS)

    @staticmethod
    def _is_assertion_error(text: str) -> bool:
        """检查是否为 Assertion 错误。"""
        return any(pattern.search(text) for pattern in _RE_ASSERTION_ERRORS)

    @staticmethod
    def _is_timeout_error(text: str) -> bool:
        """检查是否为 Timeout 错误。"""
        return any(pattern.search(text) for pattern in _RE_TIMEOUT_ERRORS)


def classify_with_confidence(
    test_output: str,
    failed_cases: list[dict] | None = None,
    target_module: str | None = None,
    *,
    enable_fallback: bool = True,
    classifier: ProbabilisticClassifier | None = None,
) -> ClassificationResult:
    """
    模块级便利函数：对 test_output + failed_cases 做置信度分层分类（改进清单 P1）。

    等价于 ErrorClassifier().classify_with_confidence(...)，供 Debugger /
    实验分析层直接调用（无需先实例化分类器）。L1 规则层零 LLM 成本、
    确定性可复现；低置信度样本触发兜底策略而非硬性路由；L2 概率化/ML
    层经 classifier 协议预留（当前恒 None，落地需独立 ADR）。

    Args:
        test_output: pytest 完整输出文本。
        failed_cases: 失败用例列表（每项含 name 和 error 字段）。
        target_module: 被测模块名（见 classify() 说明）。
        enable_fallback: 是否对低置信度样本触发兜底策略。
        classifier: L2 概率化/ML 分类器（None 时走 L1 兜底）。

    Returns:
        ClassificationResult（category / confidence / confidence_basis /
        fallback_used / fallback_category）。
    """
    return ErrorClassifier().classify_with_confidence(
        test_output,
        target_module,
        failed_cases=failed_cases or [],
        enable_fallback=enable_fallback,
        classifier=classifier,
    )


def get_fix_strategy(category: ErrorCategory, context: ErrorContext | None = None) -> str:
    """
    根据错误类型和上下文返回推荐修复策略描述。

    不同错误类型需要不同的修复策略：
    - LLM_FORMAT_ERROR：响应格式异常，需重新生成或放宽 JSON 提取
    - INDEX_ERROR：索引越界，需补边界判断
    - SYNTAX：代码无法编译，需重写整个文件
    - RUNTIME：需分析异常栈，定位 bug 所在函数
    - ASSERTION：需判断是代码错还是测试预期值错
    - TIMEOUT：需添加循环/递归终止条件
    - UNKNOWN：通用分析，由 LLM 自行判断

    对于 SYNTAX 类型，根据子类型提供更具针对性的策略：
    - IMPORT_ERROR：建议添加缺失依赖或修复导入路径
    - SYNTAX_ERROR：建议检查语法和缩进

    Args:
        category: 已分类的错误类型。
        context: 错误上下文对象（可选），用于细化策略。

    Returns:
        针对该错误类型的修复策略文字描述，供 Debugger prompt 使用。
    """
    # 带上下文细化的类别单独分支处理，其余走固定策略映射表（定义在下方）
    if category == ErrorCategory.IMPORT_ERROR:
        return _import_error_strategy(context)
    if category == ErrorCategory.SYNTAX:
        return _syntax_strategy(context)
    return _FIX_STRATEGIES.get(category, _FIX_STRATEGIES[ErrorCategory.UNKNOWN])


def _import_error_strategy(context: ErrorContext | None) -> str:
    """IMPORT_ERROR 的修复策略，按是否携带缺失模块名细化。"""
    if context and context.module_name:
        return (
            f"检测到导入错误：缺少模块 '{context.module_name}'。"
            f"请优先为该依赖配置安装方案（如在 requirements.txt 或 venv 中安装），"
            f"其次检查 import 语句的模块名/路径是否正确。"
            f"若模块应由被测项目提供，请修正导入路径，而不是删除 import。"
        )
    return (
        "检测到导入错误（ImportError/ModuleNotFoundError）。"
        "请判断缺失模块是第三方依赖还是项目内模块：第三方依赖需安装，"
        "项目内模块需修正导入路径。不要通过删除 import 语句来'修复'。"
    )


def _syntax_strategy(context: ErrorContext | None) -> str:
    """SYNTAX 的修复策略，按子类型（导入错误/语法错误）细化。"""
    if context and context.subtype == SyntaxSubtype.IMPORT_ERROR:
        if context.module_name:
            return (
                f"检测到导入错误：缺少模块 '{context.module_name}'。"
                f"请检查是否需要在 requirements.txt 中添加该依赖，"
                f"或确认模块名称是否正确。如果模块已安装，"
                f"请检查 Python 环境路径是否包含该模块。"
            )
        return (
            "检测到导入错误（ImportError/ModuleNotFoundError）。"
            "请检查是否需要安装缺失的依赖包，"
            "或确认模块名称是否正确。"
        )
    if context and context.subtype == SyntaxSubtype.SYNTAX_ERROR:
        location = ""
        if context.filename:
            location = f" 文件 '{context.filename}'"
        if context.line:
            location += f" 第 {context.line} 行"
        if context.column:
            location += f" 第 {context.column} 列"
        return (
            f"检测到语法错误{location}。"
            f"请检查该位置的语法是否正确，"
            f"特别关注括号匹配、缩进、逗号和冒号的使用。"
            f"重新生成完整的修复后代码文件，"
            f"确保语法符合 Python 规范。"
        )
    return (
        "检测到语法/编译错误（如 ImportError、SyntaxError）。"
        "请重新生成完整的修复后代码文件，确保所有 import 语句正确、"
        "缩进和语法符合 Python 规范。不要只修改单个函数，"
        "而是输出包含所有函数和 import 的完整文件代码。"
    )


# 固定修复策略映射表：无需上下文细化的错误类别直接查表返回。
# 带上下文细化的 IMPORT_ERROR / SYNTAX 由上方两个辅助函数处理。
_FIX_STRATEGIES: dict[ErrorCategory, str] = {
    # LLM_FORMAT_ERROR：LLM 响应格式异常（1.2 残余细化），策略针对"重生成/放宽提取"
    ErrorCategory.LLM_FORMAT_ERROR: (
        "检测到 LLM 响应格式异常（JSON 解析失败、响应被截断或空响应）。"
        "请重新请求 LLM 生成合规响应；若响应内含 JSON 但被 markdown 代码块"
        "包裹，先剥离代码块标记再解析；若响应被截断，降低单次输出长度或"
        "分段请求。不要将格式异常误判为代码逻辑 bug。"
    ),
    # P0 4.1 子类：LLM 空响应（占 UNKNOWN 75% 的根因之一）
    ErrorCategory.LLM_EMPTY_RESPONSE: (
        "检测到 LLM 空响应（返回内容为空字符串或纯空白）。"
        "可能原因：API 端点故障、prompt 超长被截断为空白、或模型拒绝响应。"
        "修复策略：用更严格的 prompt 重新请求（明确 JSON 输出格式约束），"
        "降低上下文长度，或在响应为空时自动重试一次。"
        "不要将空响应误判为代码逻辑 bug。"
    ),
    # P0 4.1 子类：LLM JSON 解析失败（占 UNKNOWN 75% 的根因之一）
    ErrorCategory.LLM_JSON_PARSE_FAILED: (
        "检测到 LLM 响应非空但 JSON 解析失败（markdown 包裹 / 截断 / 格式错乱）。"
        "修复策略：记录原始响应片段到 failure_knowledge_base.json，"
        "用更严格的 JSON 输出约束重新请求（'只输出 JSON，不要输出任何其他文本'），"
        "放宽 JSON 提取容忍度（剥离 markdown 代码块、截取首个 { 到最后一个 }）。"
        "不要将格式异常误判为代码逻辑 bug。"
    ),
    # INDEX_ERROR：索引越界的专属策略（1.2 残余细化：从 RUNTIME 拆出）
    ErrorCategory.INDEX_ERROR: (
        "检测到索引越界（IndexError / index out of range）。"
        "请检查引发异常的列表/字符串/数组访问位置，"
        "在循环边界、切片与默认值处理上补充分支判断；"
        "对空容器先判空再访问。不要用 try/except 静默吞掉越界。"
    ),
    # TYPE_ERROR：类型不匹配的专属策略（P2 细化）
    ErrorCategory.TYPE_ERROR: (
        "检测到类型错误（TypeError）。请核对引发异常的参数类型、函数签名与实际传入值："
        "常见根因是传入了 None/字符串/列表等不符预期的类型，或把对象当容器使用。"
        "修复时对齐参数与返回类型（必要时做输入校验与类型转换），"
        "不要用 try/except 吞掉异常来掩盖类型问题。"
    ),
    # LOGIC_ERROR：测试侧逻辑错误（P2 细化）
    ErrorCategory.LOGIC_ERROR: (
        "检测到疑似测试逻辑错误：断言失败且失败栈未触及被测模块，"
        "更可能是测试用例的预期值写错（如断言方向反了、期望值与文档不符）。"
        "请先根据函数签名/文档字符串核对测试预期值并修正测试用例；"
        "只有当被测代码行为确实与问题描述矛盾时才修改被测代码。"
    ),
    # 运行时异常：分析异常栈，定位到具体哪行代码引发问题
    ErrorCategory.RUNTIME: (
        "检测到运行时异常（如 ZeroDivisionError、TypeError 等）。"
        "请分析异常发生的具体位置和原因，修复有 bug 的代码函数，"
        "而不是修改测试用例来绕过问题。重点关注边界条件和异常处理。"
    ),
    # 断言失败：期望值计算错误或测试用例设计有问题
    ErrorCategory.ASSERTION: (
        "检测到断言失败（期望值与实际返回值不一致）。"
        "请先判断是代码逻辑错误还是测试用例的预期值错误。"
        "如果代码实现与函数签名/文档字符串描述不符，修复代码；"
        "如果测试用例的预期值不符合函数实际行为，修正测试用例的预期值。"
    ),
    # 超时：死循环或无限递归
    ErrorCategory.TIMEOUT: (
        "检测到执行超时，通常意味着存在死循环或无限递归。"
        "请检查函数中的循环条件和递归终止条件，添加适当的边界检查和退出条件。"
    ),
    # 未知类型：让 LLM 自行分析
    ErrorCategory.UNKNOWN: (
        "错误类型未能自动识别。请仔细分析测试输出，"
        "判断是代码逻辑错误、测试用例问题还是环境问题，"
        "然后给出相应的修复方案。"
    ),
    # 补丁被安全守卫拒绝（1.1 状态细化）：本轮补丁未生效，
    # 修复方向是重新生成更安全/完整的补丁而非调整测试
    ErrorCategory.PATCH_VALIDATION_FAILED: (
        "检测到上一轮补丁被安全守卫拒绝（补丁为空/过短/丢失函数定义"
        "或文件路径不合法），本轮修复未真正写入。"
        "请重新生成完整补丁：保留原代码全部函数与 import，"
        "输出完整文件而非片段，避免被安全守卫再次拒绝。"
    ),
    # RAG 检索全空（1.1 状态细化）：检索未提供参考案例，
    # 生成质量不受检索增强，按常规策略修复并考虑扩充检索库
    ErrorCategory.RAG_RETRIEVAL_EMPTY: (
        "检测到 RAG 检索未命中任何历史案例（检索库冷启动或"
        "当前任务与已入库案例差异过大）。本轮生成未获得检索增强，"
        "请按常规修复策略处理；若同类任务反复出现，"
        "考虑扩充检索库案例或降低相似度阈值。"
    ),
    # 执行轨迹丢失（5.2 持续细化）：任务失败但 execution_trace 为空，
    # 说明执行器异常路径（executor 节点未正常写入轨迹，或被上游崩溃截断）。
    # 修复方向是排查执行器/沙箱基础设施而非代码本身——轨迹缺失意味着
    # 无法定位"哪一轮执行失败"，需先恢复执行链路
    ErrorCategory.EXECUTION_TRACE_MISSING: (
        "检测到执行轨迹丢失：任务失败但 execution_trace 为空，"
        "执行器未正常记录执行结果（沙箱崩溃/超时/基础设施异常）。"
        "本轮修复无法基于逐轮执行反馈定位根因，请检查执行链路"
        "（venv/沙箱/超时配置）后重试；代码层面按常规策略谨慎修复。"
    ),
    # 多候选全拒绝（5.2 持续细化）：多候选补丁全部被静态筛选拒绝，
    # 说明 LLM 生成的 N 个候选均未通过语法/完整性/函数数检查。
    # 修复方向是回退到单补丁路径（更宽松的生成约束），而非继续扰动多候选
    ErrorCategory.MULTI_CANDIDATE_ALL_REJECTED: (
        "检测到多候选补丁策略失效：本轮生成的 N 个候选补丁全部被"
        "静态筛选拒绝（语法错误/函数定义丢失/代码过短），多候选策略"
        "未产出可用补丁。请回退到单补丁流程，并降低对 LLM 输出的"
        "扰动幅度（候选视角差异过大时 LLM 易输出残缺代码）。"
    ),
    # M5（2026-09-29 审查 P0）：测试重生成后通过但源码未被修复
    # （regenerate 路由不经过 debugger/patch_applier，源码一字未改而
    # 测试通过 = 经典 oracle-from-implementation 假成功通道）。
    # 这不是代码/测试 bug，而是实验口径问题——需人工/评估层介入，
    # 把该类任务归入"未验证假通过"而非"修复成功"。
    ErrorCategory.TEST_REGENERATED_PASS_UNVERIFIED: (
        "检测到测试重生成后通过但源码未被修复（oracle-from-implementation 假成功通道）。"
        "regenerate 路由不经过 debugger/patch_applier，源码一字未改而测试通过，"
        "说明测试断言被重写为恒真或与实现一致而非与规格一致。"
        "此任务应归入未验证假通过而非修复成功，需人工或评估层介入确认。"
    ),
}


def get_recommended_fix_strategy(
    category: ErrorCategory,
    context: ErrorContext | None = None,
) -> dict[str, str]:
    """P1 改进（2.1）：错误分类 → 修复策略的**显式结构化映射**。

    与 get_fix_strategy()（返回策略文字，供 Debugger prompt 注入）互补：
    本函数返回结构化策略记录，把"该走什么修复路径"从分散在 workflow/
    debugger 的隐式分支收敛为分类器输出的显式标签，供：
    - Debugger 选择修复 prompt 分支（而非整段文字解析）；
    - 实验分析按 strategy 标签统计"哪类错误走了哪条修复路径"；
    - 失败知识库按策略去重积累。

    Args:
        category: 已分类的错误类型。
        context: 错误上下文（可选），用于带上下文细化的类别。

    Returns:
        策略记录 dict：
        - "category": 错误类别字符串值
        - "strategy": 策略标签（snake_case，如 "regenerate_strict_json"）
        - "description": 策略文字（与 get_fix_strategy 同口径）
        - "repair_action": 推荐动作类别：
            "llm_resample"（重新生成 LLM 响应）/ "repair_code"（修代码）/
            "repair_test"（修测试预期）/ "investigate_infra"（查基础设施）/
            "no_action"（无操作）
    """
    description = get_fix_strategy(category, context=context)
    return {
        "category": category.value,
        "strategy": _STRATEGY_TAGS.get(category, "generic_analysis"),
        "description": description,
        "repair_action": _REPAIR_ACTIONS.get(category, "repair_code"),
    }


# 类别 → 策略标签（snake_case 短标签，供实验分析 / 失败知识库消费）
_STRATEGY_TAGS: dict[ErrorCategory, str] = {
    ErrorCategory.LLM_FORMAT_ERROR: "regenerate_loosen_json_extraction",
    ErrorCategory.LLM_EMPTY_RESPONSE: "regenerate_strict_json",
    ErrorCategory.LLM_JSON_PARSE_FAILED: "regenerate_strict_json",
    ErrorCategory.IMPORT_ERROR: "install_or_fix_import",
    ErrorCategory.SYNTAX: "regenerate_full_file",
    ErrorCategory.INDEX_ERROR: "add_boundary_check",
    ErrorCategory.TYPE_ERROR: "align_types",
    ErrorCategory.RUNTIME: "analyze_traceback_fix_code",
    ErrorCategory.ASSERTION: "judge_code_vs_test",
    ErrorCategory.LOGIC_ERROR: "fix_test_expectation",
    ErrorCategory.TIMEOUT: "add_termination_condition",
    ErrorCategory.UNKNOWN: "generic_analysis",
    ErrorCategory.PATCH_VALIDATION_FAILED: "regenerate_safe_patch",
    ErrorCategory.RAG_RETRIEVAL_EMPTY: "normal_repair_and_expand_rag",
    ErrorCategory.EXECUTION_TRACE_MISSING: "investigate_execution_infra",
    ErrorCategory.MULTI_CANDIDATE_ALL_REJECTED: "fallback_single_patch",
    ErrorCategory.PATCH_SYNTAX_INVALID: "resample_strict_patch",
    ErrorCategory.TEST_REGENERATED_PASS_UNVERIFIED: "investigate_oracle_from_implementation",
}

# 类别 → 推荐动作类别（coarse 四档，供修复路由分支选择）
_REPAIR_ACTIONS: dict[ErrorCategory, str] = {
    ErrorCategory.LLM_FORMAT_ERROR: "llm_resample",
    ErrorCategory.LLM_EMPTY_RESPONSE: "llm_resample",
    ErrorCategory.LLM_JSON_PARSE_FAILED: "llm_resample",
    ErrorCategory.IMPORT_ERROR: "repair_code",
    ErrorCategory.SYNTAX: "llm_resample",
    ErrorCategory.INDEX_ERROR: "repair_code",
    ErrorCategory.TYPE_ERROR: "repair_code",
    ErrorCategory.RUNTIME: "repair_code",
    ErrorCategory.ASSERTION: "repair_code",
    ErrorCategory.LOGIC_ERROR: "repair_test",
    ErrorCategory.TIMEOUT: "repair_code",
    ErrorCategory.UNKNOWN: "repair_code",
    ErrorCategory.PATCH_VALIDATION_FAILED: "llm_resample",
    ErrorCategory.RAG_RETRIEVAL_EMPTY: "repair_code",
    ErrorCategory.EXECUTION_TRACE_MISSING: "investigate_infra",
    ErrorCategory.MULTI_CANDIDATE_ALL_REJECTED: "llm_resample",
    ErrorCategory.PATCH_SYNTAX_INVALID: "llm_resample",
    # M5（2026-09-29 审查 P0）：假通过 = 测试重生成后通过但源码未修复
    # （regenerate 路由不经过 debugger/patch_applier）。修复方向是
    # "investigate_infra"——这不是代码/测试问题，而是实验口径问题
    # （oracle-from-implementation 假成功通道），需人工/评估层介入。
    ErrorCategory.TEST_REGENERATED_PASS_UNVERIFIED: "investigate_infra",
}


def refine_failure_category(
    error_category: str,
    test_passed: bool | None,
    repair_history: list[dict] | None = None,
    rag_stats: list[dict] | None = None,
    execution_trace: list[dict] | None = None,
    multi_candidate_stats: dict | None = None,
    patch_syntax_invalid: bool | None = None,
    test_regenerated_pass_unverified: bool | None = None,
) -> str:
    """任务收尾时按最终状态信号细化失败类别（1.1 状态细化 + 5.2 持续细化 + M5 假通过标记）。

    与 classify() 的文本正则分类互补：classify() 在测试输出上工作，
    本函数在任务最终状态（repair_history / rag_stats / execution_trace /
    multi_candidate_stats）上工作，把"修复失败"与"补丁不安全"、"RAG 失效"、
    "执行轨迹丢失"、"多候选全拒绝"单独标识出来，供失败分布统计与实验分析使用。

    M5（2026-09-29 审查 P0）：test_regenerated_pass_unverified 早退规则
    （优先于"成功任务原样返回"）——测试重生成后通过（regeneration_count>0
    且 test_passed=True）但源码未被修复（regenerate 路由不经过
    debugger/patch_applier）= 经典 oracle-from-implementation 假成功通道。
    此时把任务归为 TEST_REGENERATED_PASS_UNVERIFIED（不通过），使假
    成功率可被实验层度量（M5 验收指标：test_regenerated_pass 计数 = 0）。
    判定优先于其他规则：即使 test_passed=True，只要
    test_regenerated_pass_unverified=True 就归为假通过。

    判定规则（M5 假通过标记优先；其余仅对 test_passed 为 False 的任务生效）：
    0. TEST_REGENERATED_PASS_UNVERIFIED（M5）：test_regenerated_pass_unverified
       为 True（测试重生成后通过但源码未修复）——优先于"成功原样返回"；
    1. PATCH_VALIDATION_FAILED：repair_history 中任一轮 patch_applied
       为 False（补丁被安全守卫拒绝）——比 RAG 检索空更具体的失败原因，
       优先级更高；
    2. RAG_RETRIEVAL_EMPTY：rag_stats 非空（RAG 启用过）且全部记录
       results==0（任务内一次检索都未命中）；
    3. EXECUTION_TRACE_MISSING（5.2）：任务失败但 execution_trace 为空
       （执行器异常路径：executor 节点未正常写入轨迹，或被上游崩溃截断，
       无法基于逐轮执行反馈定位根因）；
    4. MULTI_CANDIDATE_ALL_REJECTED（5.2）：multi_candidate_stats 记录
       N 个候选全部被静态筛选拒绝（static_passed==0 且 candidates>0），
       标识多候选策略失效场景；
    5. 其余情况原样返回传入的 error_category。

    Args:
        error_category: classify() 得出的错误类别字符串（枚举 .value）。
        test_passed: 任务最终是否通过（None 表示中途崩溃，原样返回）。
        repair_history: PatchApplier 累计的修复历史（每轮 patch_applied 标志）。
        rag_stats: 任务内 RAG 检索指标记录（每记录 results 命中数）。
        execution_trace: 任务内 executor 执行轨迹（3.2 默认常开写入）。
        multi_candidate_stats: 多候选补丁统计 {"candidates": N, "static_passed": M}
            （可选；None 表示未启用多候选）。
        patch_syntax_invalid: 补丁经重采样后仍语法不合法（2.2 改进标记）。
        test_regenerated_pass_unverified: M5 标记——测试重生成后通过但
            源码未修复（可选；None/False = 未触发，历史口径不变）。

    Returns:
        细化后的错误类别字符串。
    """
    # M5（2026-09-29 审查 P0）：假通过早退——测试重生成后通过（regenerate
    # 路由不经过 debugger/patch_applier，源码未修复）优先归为
    # TEST_REGENERATED_PASS_UNVERIFIED（不通过），使假成功率可度量。
    # 判定优先于"成功任务原样返回"：即使 test_passed=True，只要
    # test_regenerated_pass_unverified=True 就归为假通过。
    if test_regenerated_pass_unverified:
        return ErrorCategory.TEST_REGENERATED_PASS_UNVERIFIED.value
    if test_passed is not False:
        return error_category
    history = repair_history or []
    # 补丁被安全守卫拒绝（显式 patch_applied=False 才命中；键缺失时
    # get() 缺省 True 不进入过滤，与原实现口径一致）
    patch_rejected = any(h.get("patch_applied") is False for h in history)
    if patch_rejected:
        return ErrorCategory.PATCH_VALIDATION_FAILED.value
    stats = rag_stats or []
    if stats and all(s.get("results", 0) == 0 for s in stats):
        return ErrorCategory.RAG_RETRIEVAL_EMPTY.value
    # 5.2 持续细化：执行轨迹丢失（任务失败但 execution_trace 为空）
    # 注意：execution_trace 为 None/空列表都视为"丢失"（3.2 默认常开，
    # 正常路径必写入至少 1 条；空值 = 执行器异常路径）
    if not execution_trace:
        return ErrorCategory.EXECUTION_TRACE_MISSING.value
    # 5.2 持续细化：多候选全拒绝（N 个候选均未通过静态筛选）。
    # L3 逻辑修复（2026-09-29 审查）：adaptive-skip 场景（单候选回退）下
    # multi_candidate_stats 被写成 {"candidates": 1, "static_passed": 0/1,
    # "adaptive_skipped": True}，若候选 1 应用失败会命中"多候选全拒绝"
    # 误判——该任务实际根本没走多候选（自适应策略主动跳过，L482-493）。
    # 守卫：adaptive_skipped=True 时跳过多候选全拒绝判定（真实原因已归一
    # 为单候选应用失败，不污染"多候选策略失效"实验口径）。
    if multi_candidate_stats and not multi_candidate_stats.get("adaptive_skipped"):
        candidates = multi_candidate_stats.get("candidates", 0)
        static_passed = multi_candidate_stats.get("static_passed", 0)
        if candidates > 0 and static_passed == 0:
            return ErrorCategory.MULTI_CANDIDATE_ALL_REJECTED.value
    # 2.2 改进：重采样耗尽标记（patch_applier.apply_patch_with_resample 统计
    # 经 _patch_applier_node 写入 state["error_category"]="patch_syntax_invalid"）
    if patch_syntax_invalid or error_category == ErrorCategory.PATCH_SYNTAX_INVALID.value:
        return ErrorCategory.PATCH_SYNTAX_INVALID.value
    return error_category


def refine_final_error_category(final_state: dict) -> str:
    """从工作流最终状态字典提取并细化失败类别（refine_failure_category 的接线封装）。

    cli/app.py 与 run_benchmark.py 各自重复"取 error_category/test_passed/
    repair_history/rag_stats/execution_trace/multi_candidate_stats →
    refine_failure_category"的同构代码，新增 state 字段时两处易漂移。
    此处收敛为单一接线点，两个调用方只需传 final_state。

    Args:
        final_state: 工作流最终状态字典（error_category/test_passed/
            repair_history/rag_stats/execution_trace/multi_candidate_stats 键，
            缺失时用安全默认）。

    Returns:
        细化后的错误类别字符串（判定规则见 refine_failure_category）。
    """
    return refine_failure_category(
        final_state.get("error_category", "") or "",
        final_state.get("test_passed", False),
        repair_history=final_state.get("repair_history"),
        rag_stats=final_state.get("rag_stats"),
        execution_trace=final_state.get("execution_trace"),
        multi_candidate_stats=final_state.get("multi_candidate_stats"),
        patch_syntax_invalid=bool(final_state.get("patch_syntax_invalid_flag", False)),
        # M5（2026-09-29 审查 P0）：测试重生成后通过但源码未修复（regenerate
        # 路由不经过 debugger/patch_applier）= 假成功通道。executor 节点在
        # regeneration_count>0 且 test_passed=True 时写入该标记；收尾时
        # refine_failure_category 把该标记归为 TEST_REGENERATED_PASS_UNVERIFIED
        # （不通过），使假成功率可被实验层度量。
        test_regenerated_pass_unverified=bool(final_state.get("test_regenerated_pass_unverified", False)),
    )
