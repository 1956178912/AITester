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

依赖纪律：仅导入 ``os``（零内部依赖），可被仓库根 ``config.py`` 与
``src/`` 任意模块安全导入，无循环导入风险。
"""

from __future__ import annotations

import os

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
