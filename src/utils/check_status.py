"""静态检查/预检的可测量性状态词汇与聚合（BI 轮，2026-10-22，单一事实源）。

背景（缺陷族 F03 的静态侧）：
    BG 轮的 ``type_repair`` 检查器、BH 轮的 ``testless_validation`` 四层、BI 轮
    的 ``patch_applier`` 命名契约 / 危险 API 预检，都在回答同一类问题——
    **"这个结论是测出来的，还是根本没测成"**。三处各自定义了同一套四值词表
    （``ok / disabled / unavailable / error``），本模块把它收敛为单一事实源，
    并锁住三处取值逐字相同（见 ``tests/test_bi_static_precheck_unmeasurable.py``）。

两种聚合方向（由"结果之间是什么关系"决定，不由词表决定）：
    - ``any_measurable_status``：**可替换后端**（同一检查的两个实现，BG 的
      pyright / mypy）——任一 ``ok`` ⇒ 整体可测量；
    - ``worst_check_status``：**相互独立的检查层**（BH 的四层、BI 的命名契约 +
      危险 API 预检）——任一层不可测量 ⇒ 整体不完整，故取最差者。

口径约定（下游消费时必须遵守）：
    ``status != "ok"`` 时，该检查给出的**空结果**（``missing=[]`` /
    ``dangerous_added=[]`` / ``findings=[]``）**不是**"没有缺陷"的证据；
    它只表示"没读出缺陷"或"按设计未检查"。

BK 轮（2026-10-22）补的第三类事实源——**捕获面与形态**：
    词表回答了"结论可不可信"，但没回答"守卫自己捕得住哪些读不懂"。本守卫
    （``scripts/gates/check_ast_parse_guards.py``）自测口径：``src/`` 78 个含
    ``ast.parse`` 的 ``try`` 站点里，未收敛前（HEAD 树）35 个只捕 ``SyntaxError``，
    BK 收敛 13 处（deterministic_repair / cross_file / expert_pool / patch_intent 共
    8 处 + multi_candidate 5 处；BJ 另收敛 2 处）⇒ 现存 20 处单腿守卫全部登记在
    19 条豁免额度内；``experiments/`` + ``scripts/`` 另有 45 站点 / 26 处未覆盖
    （仅报告，暂不阻断）。
    ``ValueError`` 族从这些单腿守卫里抛穿（实测 3.14.6：孤立代理位抛
    ``UnicodeEncodeError``；null 字节抛的是 ``SyntaxError`` 本体，不算新腿）。
    ``AST_UNREADABLE_ERRORS`` 收敛捕获面，``unparseable_shape`` 收敛"读不懂"的形态
    归因（围栏 / diff / 不可编码 / 语法），上面的门禁把两者锁成棘轮（新增单腿站点
    即阻断）。开工普查给出的"125 站点 / 60 单腿 / src 33"与本守卫不同口径且已不可
    复现，以守卫自测数为准（勘误见 BK 手册 §2）。
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterable
from typing import Any

#: 本层执行完成且报告可信 ⇒ 结果（含空结果）可作证据
CHECK_OK = "ok"
#: 按设计未检查（开关关 / 输入为空）⇒ 空结果不代表干净
CHECK_DISABLED = "disabled"
#: 依赖或工具缺席，预期降级 ⇒ 空结果不代表干净
CHECK_UNAVAILABLE = "unavailable"
#: 跑了但没产出可信结论（输入读不懂 / 崩溃 / rc 异常 / 报告损坏）⇒ 不可测量
CHECK_ERROR = "error"

#: 最差者优先（error > unavailable > disabled > ok）：独立检查层的聚合次序。
CHECK_STATUS_PRECEDENCE = (CHECK_ERROR, CHECK_UNAVAILABLE, CHECK_DISABLED, CHECK_OK)

#: 全部已知取值（供一致性锁与未知值判定）
CHECK_STATUS_VOCABULARY = frozenset(CHECK_STATUS_PRECEDENCE)

#: 静态预检的可解析性原因字面量（BH 的 testless 层与 BI 的两个守卫共用）
UNPARSEABLE_ORIGINAL = "unparseable_original"
UNPARSEABLE_PATCHED = "unparseable_patched"

#: ``ast.parse`` 的"读不懂"捕获面（BK 轮，2026-10-22，单一事实源）。
#: ``src/`` 78 个含 ``ast.parse`` 的 ``try`` 站点中，未收敛前 35 个只捕
#: ``SyntaxError``（BJ + BK 共收敛 15 处后仍有 20 个，登记在 19 条豁免额度内）；
#: ``ast.parse`` 还会抛 ``ValueError`` 族（实测 Python 3.14.6 对孤立代理位抛
#: ``UnicodeEncodeError``），单腿守卫会让它从"读不懂 ⇒ 降级"分支里抛穿。
#: 新增单腿站点由 ``scripts/gates/check_ast_parse_guards.py`` 阻断。
AST_UNREADABLE_ERRORS: tuple[type[BaseException], ...] = (SyntaxError, ValueError)

#: 读不懂文本的形态标签（BK 轮：``fenced_block`` / ``syntax`` 沿用 BJ 轮口径，
#: ``git_diff`` / ``undecodable`` 为本轮补入——统一差异不是"坏了的 Python"而是压根
#: 不该进 AST 门，孤立代理位是编码问题而不是语法问题）。
UNPARSEABLE_FENCED = "fenced_block"
UNPARSEABLE_GIT_DIFF = "git_diff"
UNPARSEABLE_UNDECODABLE = "undecodable"
UNPARSEABLE_SYNTAX = "syntax"
_CODE_FENCE_MARKER = "```"
_DIFF_HUNK_RE = re.compile(r"^@@ -\d+", re.MULTILINE)


def unparseable_shape(text: str) -> str:
    """把读不懂的代码文本按**形态**分类（只用于披露，不参与任何判定）。

    口径（四类判定值相同——都按"读不懂"降级，但归因不同）：
    - 剥掉前导空白后以 ````` ``` ````` 开头 ⇒ ``fenced_block``（整块 markdown 围栏被
      当作源码返回，属传输层伪影；围栏出现在正文中间按 ``syntax``——对 AST 而言
      它确实是语法错误，不自愈，与 BJ 轮 §3 口径逐字一致）；
    - ``diff --git`` 开头或含 ``@@ -<行号>`` hunk 头 ⇒ ``git_diff``（统一差异本就不是
      可解析的模块，实测归档 ``test_patch`` 257/257 属此类）；
    - 无法按 UTF-8 编码（含孤立代理位）⇒ ``undecodable``（``ast.parse`` 为此抛
      ``UnicodeEncodeError``——它不是 ``SyntaxError``，正是单腿守卫抛穿的那一类；
      把它报成 ``syntax`` 等于把编码问题记成代码质量）；
    - 其余 ⇒ ``syntax``（文本自身的语法缺陷）。
    """
    stripped = text.lstrip()
    if stripped.startswith(_CODE_FENCE_MARKER):
        return UNPARSEABLE_FENCED
    if stripped.startswith("diff --git") or _DIFF_HUNK_RE.search(text):
        return UNPARSEABLE_GIT_DIFF
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        return UNPARSEABLE_UNDECODABLE
    return UNPARSEABLE_SYNTAX


def parse_error_text(exc: BaseException) -> str:
    """把读不懂的异常折成稳定文本（``ValueError`` 族没有 ``.msg``，不能无条件取）。"""
    msg = getattr(exc, "msg", None)
    return str(msg) if msg else str(exc)


def parses_as_module(code: str) -> bool:
    """判定文本能否作为 Python 模块被 AST 读取。

    ``ValueError`` 同样按"读不懂"处理：``ast.parse`` 除 ``SyntaxError`` 外还会抛
    ``ValueError`` 子类——实测 Python 3.14.6 对含孤立代理位（lone surrogate，以
    surrogateescape 读非 UTF-8 文件所得）的源码抛 ``UnicodeEncodeError``，只捕
    ``SyntaxError`` 会让它从守卫里抛穿。口径与本模块的下游一致：
    ``patch_applier._collect_*`` 与 ``testless_validation._unparseable_side`` 均按
    ``AST_UNREADABLE_ERRORS`` 判定。注意空字节在 3.14.6 属 ``SyntaxError``
    （"source code string cannot contain null bytes"），不是 ``ValueError``。
    """
    try:
        ast.parse(code)
    except AST_UNREADABLE_ERRORS:
        return False
    return True


def unparseable_side(original_code: str, patched_code: str) -> str | None:
    """判定静态预检的两侧输入能否被 AST 读取（读不懂 ⇒ 未做任何比较）。

    Returns:
        ``UNPARSEABLE_ORIGINAL`` / ``UNPARSEABLE_PATCHED`` / ``None``（两侧均可
        解析）。原始侧优先：原文读不懂时不存在可比对的基准符号集。
    """
    if not parses_as_module(original_code):
        return UNPARSEABLE_ORIGINAL
    if not parses_as_module(patched_code):
        return UNPARSEABLE_PATCHED
    return None


def record_check_outcome(
    sink: list[dict[str, Any]] | None,
    check: str,
    status: str,
    reason: str = "",
) -> None:
    """向 outcome_sink 追加一条 ``{check, status, reason}``（sink 为 None 时零开销）。

    与 BG 轮 ``_record_static_check_outcome``（键名 ``backend``）同型：判定值
    仍走函数返回值，可测量性走 sink，从而不改任何既有调用点的返回契约。
    """
    if sink is not None:
        sink.append({"check": check, "status": status, "reason": reason})


def status_for_check(outcomes: Iterable[dict[str, Any]] | None, check: str) -> str | None:
    """从逐条 outcome 里挑出**指定检查腿**的最差 status；该腿没记录 ⇒ None。

    BL 轮消费侧双读的地基：``worst_check_status`` 把多道独立预检聚合成一个
    ``safety_check_status``，直接拿它给"命名契约缺失符号"定口径会把"危险 API 腿
    读不懂"错记到契约头上。本函数按 ``check`` 名挑该腿自己的可测量性——
    None 与 ``CHECK_OK`` 在消费侧是两种读法（前者"本轮没做这条腿"，后者
    "做了且可信，空结果可作证据"）。
    """
    leg = [
        str(outcome.get("status", ""))
        for outcome in (outcomes or [])
        if isinstance(outcome, dict) and outcome.get("check") == check
    ]
    if not leg:
        return None
    return worst_check_status(leg)


def worst_check_status(statuses: Iterable[str | None], default: str = CHECK_ERROR) -> str:
    """聚合**相互独立**的检查层：最差者优先，未知/缺失 status 按 error 保守处理。

    Args:
        statuses: 逐层 status（``None`` 视同未知）。
        default: statuses 为空时返回值。BH 的 testless 四层传默认 ``error``
            （"一层都没记录"不能读成"都验过了"）。

    Returns:
        已知取值中的最差者；无任何已知取值 ⇒ ``CHECK_ERROR``（fail-closed）。
    """
    values = [status or "" for status in statuses]
    if not values:
        return default
    for candidate in CHECK_STATUS_PRECEDENCE:
        if any(status == candidate for status in values):
            return candidate
    return CHECK_ERROR


def any_measurable_status(statuses: Iterable[str | None], default: str = CHECK_DISABLED) -> str:
    """聚合**同一检查的可替换后端**：任一 ``ok`` ⇒ 整体可测量，否则取最差者。

    保持 BG 轮历史口径（含"取值集合为空 ⇒ ``disabled``"与"未知 status 不升级
    为 error"两点），因此与 ``worst_check_status`` 的默认值与未知值处理不同——
    这不是疏漏：BG 的 outcomes 为空确实意味着"一次都没跑"（按设计未检查）。

    Args:
        statuses: 逐次尝试的 status。
        default: 空集合时返回值（BG 口径 ``disabled``）。

    Returns:
        ``CHECK_OK``（任一 ok）否则按 ``error > unavailable > disabled`` 取首个
        命中者；全不命中（含未知取值）⇒ ``default``。
    """
    values = [status or "" for status in statuses]
    if CHECK_OK in values:
        return CHECK_OK
    for candidate in (CHECK_ERROR, CHECK_UNAVAILABLE, CHECK_DISABLED):
        if candidate in values:
            return candidate
    return default
