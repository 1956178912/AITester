"""
P2 确定性守卫（2026-09-29 批次，外部参照：AltTester 确定性工作流——
"生成时用 LLM 写测试，保留确定性测试套件，运行时无模型、无 token、
每次结果相同"；以及 2026 年研究指出的 LLM 引入的非确定性风险）。

设计目标：LLM 生成的测试代码在"生成"与"执行"间解耦——本模块对 LLM
输出的测试文件做静态扫描，标记含非确定性操作的文件（time.sleep 长等待、
随机数、外部网络、墙钟时间），供调用方决定"存为确定性套件"还是
"需人工确认"。纯标准库 AST 扫描，零 LLM 成本，默认关闭（
DETERMINISTIC_GUARD_ENABLE=false 时恒放行，历史口径）。

扫描口径（保守，高召回优先误伤可控）：
- random / numpy.random 的调用 → "随机数生成"；
- time.sleep(>阈值) → "长等待"（默认 0.5s，短 sleep 常见于测试重试
  容忍，不计入）；
- datetime.now / time.time 直接读墙钟 → "墙钟依赖"（测试时间敏感）；
- requests / urllib / httpx / socket / subprocess 的网络与子进程调用
  → "外部副作用"（CI 沙箱内不可复现）；
- 未命中的测试文件 = 可入库为确定性套件（调用方决定存储路径）。
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

from src.utils.env_utils import env_flag, env_float

_GUARD_ENV = "DETERMINISTIC_GUARD_ENABLE"
_SLEEP_ENV = "DETERMINISTIC_GUARD_SLEEP_THRESHOLD"


def deterministic_guard_enabled() -> bool:
    """确定性守卫开关（DETERMINISTIC_GUARD_ENABLE，默认 false 历史口径）。"""
    return env_flag(_GUARD_ENV)


def _sleep_threshold() -> float:
    """time.sleep 计入"长等待"的秒数阈值（默认 0.5s，测试重试短 sleep 豁免）。

    EF（2026-10-27）：非有限值（NaN/±inf）由 ``env_float`` 告警后回退默认值。
    `float("nan")` 不抛 ValueError，而 `arg_val > nan` 恒 False——历史实现会
    让 long_sleep 规则静默失效。
    """
    return env_float(_SLEEP_ENV, 0.5)


@dataclass
class GuardFinding:
    """确定性守卫 finding。"""

    rule: str  # "random_usage" / "long_sleep" / "wall_clock" / "external_side_effect"
    detail: str
    line: int = 0


@dataclass
class GuardReport:
    """对单个测试文件内容的扫描结果。"""

    filename: str
    findings: list[GuardFinding] = field(default_factory=list)

    @property
    def is_deterministic(self) -> bool:
        """无 finding（或开关关闭）时视为可入库的确定性测试文件。"""
        return not self.findings


# 危险/非确定性调用模式（AST 级判定，保守口径）
# 2026-10-01 全面审查 P2 修复：此前 set 含 "urllib.request" 但匹配用
# qual.split(".")[0]（仅顶层模块名）——urllib 家族（urllib.request.urlopen /
# urllib.parse.urlencode / urllib.error.HTTPError）全部漏检。现改为顶层模块
# 前缀匹配（qual.split(".")[0] in 顶层名集合 + urllib 子模块白名单），
# 并把 set 统一为顶层模块名集合（与 Import/ImportFrom 分支同口径）。
_EXTERNAL_MODULE_TOPLEVEL = {
    "requests",
    "urllib",
    "httpx",
    "socket",
    "subprocess",
}


def _is_external_call(qual: str) -> bool:
    """判定调用限定名 qual（如 "urllib.request.urlopen"）是否属于
    外部副作用模块家族（保守：按顶层模块名匹配，urllib 含全部子模块）。"""
    top = qual.split(".", maxsplit=1)[0]
    return top in _EXTERNAL_MODULE_TOPLEVEL


_WALL_CLOCK_ATTRS = {
    "datetime.now",
    "datetime.utcnow",
    "time.time",
    "time.clock",
}
_RANDOM_ATTRS = {
    "random",
    "numpy.random",
}
_SLEEP_CALL = "time.sleep"


def _is_random_qual(qual: str) -> bool:
    """限定名是否属**随机数家族**（`random.*` / `numpy.random.*`）。

    GJ 轮（2026-10-28）修复：此前判定写成 `qual.split(".")[0] in _RANDOM_ATTRS`
    ——而 `_RANDOM_ATTRS` 里存的是 `"numpy.random"`（**两段**），
    `split(".")[0]` 永远只给出**一段**的顶层名 ⇒ `numpy.random.seed` 判不出、
    `import numpy`（无别名）写法**完全漏检**（模块 docstring 第 13 行明示
    numpy.random 纳入检测）。实测：`np.random.seed(1)` 被标成 `random.numpy`
    （别名展开写错了位置，见 `_qualified_attr`），`import numpy` 一条 finding 都没有。

    现按**前缀**判定：`qual` 等于族名或以 `族名.` 开头 ⇒ 命中。
    「`numpy` 本身」不算（`numpy.array` 不是随机数）。
    """
    return any(qual == attr or qual.startswith(f"{attr}.") for attr in _RANDOM_ATTRS)


def _qualified_attr(node: ast.AST) -> str | None:
    """把 Attribute 链展开为模块限定名（a.b.c）；`import numpy as np` 的
    别名展开为 "numpy.random" 等真实模块名（测试可拦截 numpy.random）。"""
    parts: list[str] = []
    cur: ast.AST = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        alias = cur.id
        # 模块别名展开：import numpy as np → np.random ≡ numpy.random
        #
        # GJ 轮（2026-10-28）修复：此前写 `parts[0] = _IMPORT_ALIASES[alias]`
        # ——`parts` 是**逆序**累积的（`np.random.seed` ⇒ ["seed","random"]），
        # `parts[0]` 是**最外层属性名**（"seed"）而不是基名 ⇒ 展开结果变成
        # "random.numpy"（限定名被打乱，族判定随之失效）。
        # 正确写法：**追加**展开后的真实模块名（基名本来就不在 parts 里）。
        parts.append(_IMPORT_ALIASES.get(alias, alias))
        return ".".join(reversed(parts))
    return None


# 常见测试依赖的模块别名映射（保守白名单：仅展开已知的"顶层真实模块"）
_IMPORT_ALIASES = {
    "np": "numpy",
}


def _arg_is_numeric_const(node: ast.AST) -> float | None:
    """实参是数字常量时返回其值（time.sleep(0.1) 判定豁免用）。"""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    return None


def scan_test_file(source: str, filename: str = "<memory>") -> GuardReport:
    """对 LLM 生成的测试文件内容做非确定性扫描（AST 级，零 LLM 成本）。

    开关关闭（默认）时返回空 findings（is_deterministic 恒 True，历史
    口径零变化）；开启时按模块文档的规则集扫描。

    Args:
        source: 测试文件全文。
        filename: 文件名（仅用于报告展示）。

    Returns:
        GuardReport（findings 可能为空）。
    """
    report = GuardReport(filename=filename)
    if not deterministic_guard_enabled():
        return report
    try:
        tree = ast.parse(source)
    except SyntaxError:
        # 语法不合法的文件本就进不了执行路径（2.2 重采样口径），
        # 此处不追加 finding（避免与补丁守卫职责混叠）
        return report

    for node in ast.walk(tree):
        # 1. 随机数调用（random.xxx / numpy.random.xxx）
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            qual = _qualified_attr(node.func)
            if qual:
                if _is_random_qual(qual):
                    report.findings.append(
                        GuardFinding("random_usage", f"随机数调用 {qual}（测试不可复现）", node.lineno)
                    )
                    continue
                if qual == _SLEEP_CALL:
                    threshold = _sleep_threshold()
                    arg_val = _arg_is_numeric_const(node.args[0]) if node.args else None
                    if arg_val is None or arg_val > threshold:
                        report.findings.append(
                            GuardFinding(
                                "long_sleep",
                                f"长等待 time.sleep({arg_val if arg_val is not None else '…'}s) > {threshold}s",
                                node.lineno,
                            )
                        )
                    continue
                if qual in _WALL_CLOCK_ATTRS:
                    report.findings.append(
                        GuardFinding("wall_clock", f"墙钟时间依赖 {qual}（结果随时间漂移）", node.lineno)
                    )
                    continue
                if _is_external_call(qual):
                    report.findings.append(
                        GuardFinding(
                            "external_side_effect",
                            f"外部副作用调用 {qual}（CI 沙箱内不可复现）",
                            node.lineno,
                        )
                    )
        # 2. 模块级 import（import subprocess / from socket import …）
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in _EXTERNAL_MODULE_TOPLEVEL:
                    report.findings.append(
                        GuardFinding("external_side_effect", f"外部模块导入 {alias.name}", node.lineno)
                    )
        if isinstance(node, ast.ImportFrom):
            top = (node.module or "").split(".")[0]
            if top in _EXTERNAL_MODULE_TOPLEVEL:
                report.findings.append(GuardFinding("external_side_effect", f"外部模块导入 {node.module}", node.lineno))
    return report


__all__ = [
    "GuardFinding",
    "GuardReport",
    "deterministic_guard_enabled",
    "scan_test_file",
]
