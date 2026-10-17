"""环境开关读取的单一事实源（2026-10-16 C 轮去重）。

背景：全仓曾有 **55 处**重复的布尔环境变量解析惯用法——
``os.getenv(NAME, "false").lower() in ("true", "1", "on")``（部分带
``.strip()``，两处扩展 ``"yes"``）。逐点手抄带来三类隐患：

1. **口径漂移**：strip / "yes" 的有无逐步分化，审计难以穷尽；
2. **复制粘贴错误**：新增开关时默认值或变量名抄错，review 难以发现；
3. **语义变更成本**：若要接受新真值字面量（如 "enabled"），需逐点修改。

本模块收敛为 :func:`env_flag`：

- 默认接受集 = 项目既有主流口径（``"true"/"1"/"on"``，大小写不敏感，
  空白容忍）；
- 扩展集（如 ``"yes"``）必须由调用方**显式**经 ``extra_true`` 声明——
  默认不收，防"某处放宽、某处严"的隐式分裂；
- 未设置 → ``default``；已设置 → 按接受集判定（空字符串不在接受集，
  与历史惯用法逐字节一致：历史上显式空值的解析结果就是 False）。

2026-10-16 F 轮补充 :func:`env_int`：仓内仍有 **3 处模块级**裸
``int(os.getenv(NAME, "default"))``（``src/graph/nodes.py`` 的
``CODE_FOCUS_DEPTH``、``src/tools/control_flow.py`` 的
``_CFG_SUMMARY_MAX_CHARS`` / ``_PATH_MAX_DEFAULT``）——坏值（如
``CFG_SUMMARY_MAX_CHARS=abc``）会在 **import 期**抛 ``ValueError``，
即"一个拼错的环境变量让整个模块不可导入"，比运行期降级严重得多；而
``config.py::_parse_int_env`` 早已确立"坏值记 WARNING 回退默认值"的
项目口径，只是该 helper 位于重依赖的根 config 模块，轻依赖叶子模块
无法复用。:func:`env_int` 即其 ``src/`` 侧同语义落点（口径逐条对齐，
含越界回退）。

**已知未合并项（显式披露）**：``config.py::_parse_int_env`` /
``_parse_float_env`` 与本模块 :func:`env_int` / :func:`env_float` 语义重叠，
本轮**刻意不做**合并——前者有 20+ 调用点与锁定测试（``tests/test_config.py``），
且合并会改变日志的 logger 名（``config`` → ``src.utils.env_utils``），属可观测
行为变化，须单独一批处置。

2026-10-17 J 轮补充两个同族入口：

- :func:`env_float`——与 :func:`env_int` 对称（此前只有 int 版，浮点散点只能继续
  手写）。口径逐条对齐 ``config._parse_float_env``，**含非有限值（NaN/±inf）回退**：
  ``nan`` 参与任何 ``<`` / ``>`` 比较恒为 False，只做范围检查会让坏阈值静默穿透。
- :func:`env_flag_opt_out`——"显式关闭才算关"的负集口径，与 :func:`env_flag` 的
  正集口径对偶，收敛全仓 10 处手抄负集表达式（各站点的关闭字面量集原本互不相同）。
  垃圾值方向为 **fail-closed**（保持启用），沿用 G 轮对守卫类开关的定调。

**刻意未合并的两处本地解析器（显式披露）**：
``src/tools/feedback_compression.py::_clamp_env_int`` 与
``src/graph/risk_approval.py::_env_float`` 是**钳制**口径（越界取边界值，如
``FEEDBACK_COMPRESSION_MAX_LINES=999`` → 50），与本模块 :func:`env_int` /
:func:`env_float` 的"越界回退默认值"口径不同，且该钳制行为有锁定测试
（``tests/test_feedback_compression.py::test_clamped_high/low``，注释明示"防只传
一个行号的信息损失"）。合并会把"配置写大了"变成"静默降回默认参数"，属行为退化，
故保留各自口径。

依赖纪律：仅导入标准库 ``os`` / ``logging`` / ``math``（零内部依赖），可被仓库根
``config.py`` 与 ``src/`` 任意模块（含刻意保持轻依赖的叶子模块，如
``src/tools/control_flow.py`` 只有 ast/logging/typing）安全导入，
无循环导入风险。
"""

from __future__ import annotations

import logging
import math
import os

logger = logging.getLogger(__name__)

#: 项目主流真值口径（orchestration_search 臂登记注释同款）
_DEFAULT_TRUE: tuple[str, ...] = ("true", "1", "on")

#: 项目主流"关闭"口径（:func:`env_flag_opt_out` 用；与 :data:`_DEFAULT_TRUE` 逐项对偶：
#: true↔false、1↔0、on↔off。守卫类开关的 fail-closed 方向由此保证）
_DEFAULT_OFF: tuple[str, ...] = ("false", "0", "off")


def env_flag(name: str, default: bool = False, *, extra_true: tuple[str, ...] = ()) -> bool:
    """读取布尔型环境开关（项目统一口径）。

    Args:
        name: 环境变量名。
        default: 变量**未设置**时的默认值。
        extra_true: 额外接受的真值字面量（如 ``("yes",)``）。默认空——
            扩展集必须显式声明，防口径隐式分裂。

    Returns:
        归一化后的布尔值。

    Note:
        行为与历史惯用法逐字节一致：未设置 → default；已设置（含空串）
        → 按接受集判定，空串不在接受集故为 False（``.strip()`` 后判定，
        容忍 "TRUE" / " True " 等形态）。
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    accepted = _DEFAULT_TRUE if not extra_true else _DEFAULT_TRUE + tuple(extra_true)
    return raw.strip().lower() in accepted


def env_flag_opt_out(name: str, *, off_values: tuple[str, ...] | None = None) -> bool:
    """读取**opt-out 型**布尔开关（"显式关闭才算关"，与 :func:`env_flag` 对偶）。

    J-2（2026-10-17）新增。背景：全仓有 11 处"默认开、显式关"的开关各自手抄
    负集表达式，接受的关闭字面量互不相同（``("false","0")`` / ``("0","false")`` /
    ``("false","0","off")`` / 单值 ``"false"`` / 单值 ``"0"``，且 4 处漏了
    ``.lower()``）。手抄负集的代价不是"不统一"本身，而是**同一句意图在不同开关上
    结果不同**：``AITESTER_LLM_CACHE=false`` 今天仍判"开"（只认 ``"0"``），
    而 ``EMPTY_PATCH_GUARD=0`` 今天也判"开"（只认 ``"false"``）——两处都是用户的
    显式关闭意图被静默忽略。

    口径（与 :func:`env_flag` 的唯一区别在**垃圾值的方向**）：

    - 未设置 → ``True``（本类开关的惯例即"默认开"；故不提供 default 参数——
      默认关的开关应当用 :func:`env_flag`，否则等于没有开关）；
    - 值落在关闭集内（大小写不敏感、空白容忍）→ ``False``；
    - **其余一切值**（含 ``"ture"`` 拼错、``"no"``、空串）→ 保持 ``True``。
      这是守卫类开关必需的 fail-closed 方向：正集口径会把 ``=ture`` 读成
      "关闭守卫"，2026-10-16 G 轮已为守卫类开关定调保留负集。

    Args:
        name: 环境变量名。
        off_values: 关闭字面量集合；``None`` = 项目主流口径 ``("false", "0", "off")``
            （与 :data:`_DEFAULT_TRUE` 逐项对偶）。仅当某开关的历史接受集与主流
            不同时才**显式**传入，防隐式分裂。

    Returns:
        开关是否保持启用。

    Note:
        J-2 收敛的 11 处站点上，逐项核对后的**实际**行为差异只有一类方向——
        "用户的显式关闭意图开始生效"，且**从不**让守卫在垃圾值下被关闭：

        - 补大小写：``AITESTER_AGENT_REUSE=FALSE`` / ``AITESTER_EXECUTOR_AGENT_CACHE=OFF``
          / ``AITESTER_LLM_CACHE=False`` / ``AITESTER_CACHE_ISOLATE_MODEL=FALSE`` 此前
          因未 ``.lower()`` 判"仍启用"，现判关闭（4 处，即上述"漏 lower"名单）；
        - 补集合：单值口径把另一种常见写法当垃圾——``EMPTY_PATCH_GUARD=0``（原只认
          ``"false"``）、``CFG_ANALYSIS_ENABLE=off`` / ``P2P_GATE_ENABLE=false`` 类
          三值口径之外的站点同理；
        - 补空白：仅 ``AITESTER_CACHE_ISOLATE_MODEL`` 原有 ``.strip()``，其余 10 处
          ``" false "`` 这类带空白的关闭值此前判"启用"，现判关闭。

        未改变的方向：未设置仍为启用；垃圾值（``ture`` / ``no`` / 空串）仍**保持启用**
        （fail-closed，与原手写口径同结果）。
    """
    raw = os.getenv(name)
    if raw is None:
        return True
    off = _DEFAULT_OFF if off_values is None else tuple(off_values)
    return raw.strip().lower() not in off


def env_int(name: str, default: int, *, lo: int | None = None, hi: int | None = None) -> int:
    """容错读取整型环境变量（坏值/越界一律回退默认值，**绝不抛异常**）。

    口径与 ``config.py::_parse_int_env`` 逐条对齐：未设置或空串 → ``default``；
    非整数 → 记 WARNING 并回退；超出 ``[lo, hi]``（None 侧不限制）→ 记 WARNING
    并回退。设计目的是让模块级常量（import 期求值）不会因一个拼错的环境变量
    而让整个模块不可导入。

    Args:
        name: 环境变量名。
        default: 未设置/非法时的回退值。
        lo: 允许的最小值（None 表示不限制）。
        hi: 允许的最大值（None 表示不限制）。

    Returns:
        合法的环境变量值；未设置或非法时返回 ``default``。
    """
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw.strip())
    except ValueError:
        logger.warning("环境变量 %s=%r 不是合法整数，回退默认值 %d", name, raw, default)
        return default
    if (lo is not None and value < lo) or (hi is not None and value > hi):
        logger.warning("环境变量 %s=%d 超出范围 [%s, %s]，回退默认值 %d", name, value, lo, hi, default)
        return default
    return value


def env_float(name: str, default: float, *, lo: float | None = None, hi: float | None = None) -> float:
    """容错读取浮点环境变量（坏值/非有限值/越界一律回退默认值，**绝不抛异常**）。

    口径与 ``config.py::_parse_float_env`` 逐条对齐：未设置或空串 → ``default``；
    非数字 → 记 WARNING 并回退；**非有限值**（NaN / ±inf）→ 记 WARNING 并回退；
    超出 ``[lo, hi]``（None 侧不限制）→ 记 WARNING 并回退。

    非有限值判定不是冗余防御：``nan`` 与任何数的 ``<`` / ``>`` 比较都返回 False，
    只做范围检查会让 ``SEMANTIC_CACHE_THRESHOLD=nan`` 这类坏阈值**静默穿透**
    （阈值比较恒 False，功能恒开或恒关，日志里看不出任何异常）。

    Args:
        name: 环境变量名。
        default: 未设置/非法时的回退值。
        lo: 允许的最小值（None 表示不限制）。
        hi: 允许的最大值（None 表示不限制）。

    Returns:
        合法的环境变量值；未设置或非法时返回 ``default``。
    """
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw.strip())
    except ValueError:
        logger.warning("环境变量 %s=%r 不是合法浮点数，回退默认值 %g", name, raw, default)
        return default
    if not math.isfinite(value):
        logger.warning("环境变量 %s=%r 非有限值（NaN/inf），回退默认值 %g", name, raw.strip(), default)
        return default
    if (lo is not None and value < lo) or (hi is not None and value > hi):
        logger.warning("环境变量 %s=%g 超出范围 [%s, %s]，回退默认值 %g", name, value, lo, hi, default)
        return default
    return value
