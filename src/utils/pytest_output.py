"""pytest 摘要行的共享解析与「有效通过」谓词（F03）。

事实源：BA 轮在 ``experiments/_m1_metrics.py`` 建立，BD 轮上移到 ``src/``
——M1 消费点与 MDO 的基线/变异体判定必须用同一份实现，不能各写一套。

F03：pytest 对"没有任何断言执行"的套件同样返回 rc==0（全 skip / xfail /
xpass / deselect）。``suite_has_effective_pass`` 要求至少 1 个真实
``passed`` 且 0 个 ``failed``；部分 skip 与真实 passed 并存仍算有效通过。
摘要不可解析（空输出 / 自定义运行器）同样不算有效通过——fail-closed。

R04（2026-10-23 全量集中复审 P1）：计数只从 **权威摘要行** 解析。pytest
标准输出含 warnings summary 与源代码原文，warning 正文（如
``UserWarning: 1 passed``）不属于测试结果；旧实现对整个输出取首个计数
匹配，反例 A（warning 正文 "1 passed" + 真实全 skip）被判有效通过（假绿
重新开放），反例 B（warning 正文 "1 failed validation" + 真实 1 passed）
被判失败（假红）。权威摘要行的判据：一行内除计数 token 外只含
分隔符（等号 / 逗号 / 空白）与 ``in <时长>s``——多条命中取最后一条
（pytest 终末摘要），一条都没有时返回空 dict（fail-closed 契约不变）。
"""

from __future__ import annotations

import re

# 测试结果计数词（不含 warning——它不是测试结果，仅参与行结构剥离）
_PYTEST_SUMMARY_COUNT_RE = re.compile(r"(\d+) (passed|failed|skipped|errors?|deselected|xfailed|xpassed)")
# 行结构校验用：额外剥离 warning 计数（摘要行可带 ", N warning(s)" 尾巴）
_SUMMARY_LINE_TOKEN_RE = re.compile(r"(\d+) (passed|failed|skipped|errors?|deselected|xfailed|xpassed|warnings?)")
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")
# 摘要行尾的会话时长（"in 0.01s" / "in 1:03.45s"）；剥离后便于统一做残留校验
_SUMMARY_DURATION_RE = re.compile(r"\bin\s+[\d:.]+s\b")


def _authoritative_summary_lines(output: str) -> list[str]:
    """从输出中筛出权威摘要行（结构校验通过、按出现顺序）。

    判据：一行（剥 ANSI 后）剥掉所有计数 token 与会话时长片段后，只剩
    分隔符（等号 / 逗号 / 空白）且至少含一个计数 token——warning 正文行
    （如 "UserWarning: 1 passed"）、会话头、coverage 行（"TOTAL 100%"）
    都有其他文字，不满足；默认模式等号包围 / -q 裸摘要 / 无时长后缀的
    拼接输出（pytest 摘要 + coverage）均可通过。
    """
    lines: list[str] = []
    for raw in str(output or "").splitlines():
        line = _ANSI_ESCAPE_RE.sub("", raw).strip()
        if not line:
            continue
        if not _SUMMARY_LINE_TOKEN_RE.search(line):
            continue
        residue = _SUMMARY_LINE_TOKEN_RE.sub("", _SUMMARY_DURATION_RE.sub("", line)).strip(" =,")
        if residue:
            continue
        lines.append(line)
    return lines


def pytest_summary_counts(output: str) -> dict[str, int]:
    """从 pytest 摘要行解析结果计数（O-1：skip/unavailable 识别用）。

    R04 后只解析**权威摘要行**（判据见 ``_authoritative_summary_lines``）：
    多条命中取最后一条（pytest 终末摘要反映真实最终状态）；无权威摘要行
    → 空 dict（调用方保守处理，fail-closed 契约不变）。行内每个结果 kind
    只出现一次，``setdefault`` 保留首个即唯一值。
    """
    counts: dict[str, int] = {}
    summary_lines = _authoritative_summary_lines(output)
    if not summary_lines:
        return counts
    for token in _PYTEST_SUMMARY_COUNT_RE.finditer(summary_lines[-1]):
        kind = "error" if token.group(2).startswith("error") else token.group(2)
        counts.setdefault(kind, int(token.group(1)))
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
