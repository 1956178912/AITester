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
``_parse_float_env`` 与本模块 :func:`env_int` 语义重叠，本轮**刻意不做**
合并——前者有 20+ 调用点与锁定测试（``tests/test_config.py``），且合并
会改变日志的 logger 名（``config`` → ``src.utils.env_utils``），属可观测
行为变化，须单独一批处置。

依赖纪律：仅导入标准库 ``os`` / ``logging``（零内部依赖），可被仓库根
``config.py`` 与 ``src/`` 任意模块（含刻意保持轻依赖的叶子模块，如
``src/tools/control_flow.py`` 只有 ast/logging/os/typing）安全导入，
无循环导入风险。
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

#: 项目主流真值口径（orchestration_search 臂登记注释同款）
_DEFAULT_TRUE: tuple[str, ...] = ("true", "1", "on")


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
