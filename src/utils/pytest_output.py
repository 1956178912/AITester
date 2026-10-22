"""pytest 摘要行的共享解析与「有效通过」谓词（F03）。

事实源：BA 轮在 ``experiments/_m1_metrics.py`` 建立，BD 轮上移到 ``src/``
——M1 消费点与 MDO 的基线/变异体判定必须用同一份实现，不能各写一套。

F03：pytest 对"没有任何断言执行"的套件同样返回 rc==0（全 skip / xfail /
xpass / deselect）。``suite_has_effective_pass`` 要求至少 1 个真实
``passed`` 且 0 个 ``failed``；部分 skip 与真实 passed 并存仍算有效通过。
摘要不可解析（空输出 / 自定义运行器）同样不算有效通过——fail-closed。
"""

from __future__ import annotations

import re

_PYTEST_SUMMARY_COUNT_RE = re.compile(r"(\d+) (passed|failed|skipped|errors?|deselected|xfailed|xpassed)")


def pytest_summary_counts(output: str) -> dict[str, int]:
    """从 pytest 摘要行解析结果计数（O-1：skip/unavailable 识别用）。

    只解析标准摘要片段（``N passed`` / ``N skipped`` / ...）；重复出现取首个
    出现值（pytest 摘要行只出现一次）。解析失败 → 空 dict（调用方保守处理）。
    """
    counts: dict[str, int] = {}
    for match in _PYTEST_SUMMARY_COUNT_RE.finditer(str(output or "")):
        kind = "error" if match.group(2).startswith("error") else match.group(2)
        counts.setdefault(kind, int(match.group(1)))
    return counts


def suite_has_effective_pass(output: str) -> bool:
    """rc==0 的输出是否含有效通过证据：至少 1 个 ``passed`` 且无 ``failed``。

    F03（2026-10-21 第三方审查 P1）：pytest 对"没有任何断言执行"的套件同样
    返回 rc==0——全 skip / xfail / xpass / deselect 的摘要行里 ``passed==0``。
    只看 rc 会把"没跑起来"计成有效 green，使 detection 的 fixed 侧与
    repair 的 gold 侧各有一条假阳性通道（审计最小条件：buggy 红 + fixed
    "1 skipped" → 旧实现返回 1.0）。

    口径边界：**部分 skip 与真实 passed 并存仍算有效通过**（审查报告明确
    警告"部分 skip 可以与有效断言通过并存"）；只拒绝 ``passed==0``。
    """
    counts = pytest_summary_counts(output)
    return int(counts.get("passed", 0)) > 0 and int(counts.get("failed", 0)) == 0


def run_has_effective_pass(returncode: int | None, output: str) -> bool:
    """执行级判绿：``rc==0`` 且摘要含有效通过（F03 生产路径统一入口）。

    BE（2026-10-21 生产路径收口）：executor / 沙箱 / Docker / 仓库节点 /
    P2P 回归此前只看 ``returncode == 0``——全 skip 的套件 rc 同样是 0，
    会被记成"修复正确 / 补丁安全"。本函数是这些消费点唯一允许的判绿入口；
    ``rc != 0``（含 None）恒 False，不改变既有失败口径。
    """
    return returncode == 0 and suite_has_effective_pass(output)
