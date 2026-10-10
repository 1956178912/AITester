"""
5a. 静态检查快照生成器：把 ruff / mypy 实测输出归档到 docs/history/。

背景（改进清单 #5，P0）：
    docs/code_analysis_report.md 为 2026-09 静态快照（内容已全面过期），但仓库
    缺乏"每批次落地后自动刷新静态检查结论"的机制——快照靠人肉维护，长期漂移。
    本脚本把当前 `ruff check .` / `ruff format --check .` / `mypy src/ config.py`
    的实测输出生成为带时间戳的 Markdown 快照，追加归档到 docs/history/，
    使"最新静态检查结论"始终有一份可追溯的实测记录（与 BASELINE.yaml 同口径，
    批次落地后运行本脚本 + 刷新 BASELINE.yaml）。

    用法：
        python scripts/tools/generate_static_report.py            # 生成快照（追加归档）
        python scripts/tools/generate_static_report.py --check    # 只打印摘要，不写盘
                                                         # （CI 预检 / 快速查看）

    生成物：docs/history/static_report_<UTC 日期>.md（同日多次运行覆盖同名文件）。
    快照内容：各工具退出码 + 告警/错误统计 + 告警明细（截取上限 200 行，防膨胀）。
"""

from __future__ import annotations

import argparse
import datetime
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
HISTORY_DIR = PROJECT_ROOT / "docs" / "history"
_MAX_DETAIL_LINES = 200


def _run(cmd: list[str]) -> tuple[int, str]:
    """执行命令，返回 (退出码, 合并输出)。"""
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=PROJECT_ROOT)
    return result.returncode, (result.stdout + ("\n" + result.stderr if result.stderr else "")).strip()


def collect_snapshot() -> dict[str, object]:
    """运行 ruff / mypy 实测，收集快照数据（不写盘）。"""
    snapshot: dict[str, object] = {}
    snapshot["generated_at"] = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M UTC")
    snapshot["python"] = sys.version.split()[0]

    # ruff check（全仓）
    rc, out = _run([sys.executable, "-m", "ruff", "check", "."])
    snapshot["ruff_check"] = {"exit_code": rc, "output": out}
    # ruff format --check（全仓）
    rc, out = _run([sys.executable, "-m", "ruff", "format", "--check", "."])
    snapshot["ruff_format"] = {"exit_code": rc, "output": out}
    # mypy（与 BASELINE.yaml 同口径：src/ + config.py）
    rc, out = _run([sys.executable, "-m", "mypy", "src/", "config.py"])
    snapshot["mypy"] = {"exit_code": rc, "output": out}
    return snapshot


def _summarize(name: str, block: dict[str, object]) -> list[str]:
    """单工具摘要行：退出码 + 告警计数 + 明细（截断）。"""
    out = str(block["output"])
    lines = out.splitlines()
    total = len(lines)
    detail = lines[:_MAX_DETAIL_LINES]
    header = [f"### {name}（退出码 {block['exit_code']}，输出 {total} 行）", ""]
    if total > _MAX_DETAIL_LINES:
        detail.append(f"……（截断，完整输出共 {total} 行）")
    return [*header, "```", *detail, "```", ""]


def render_markdown(snapshot: dict[str, object]) -> str:
    """把快照渲染为 Markdown 文本。"""
    parts: list[str] = [
        f"# 静态检查快照（{snapshot['generated_at']}）",
        "",
        f"> 本文件由 `scripts/tools/generate_static_report.py` 自动生成（Python {snapshot['python']}）。",
        "> 各批次落地后运行脚本刷新；与 BASELINE.yaml `static_checks` 节同口径。",
        "> 前序快照保留在同目录（按日期命名），历史结论以对应快照为准。",
        "",
        "## 工具",
        "",
    ]
    for key, label in (
        ("ruff_check", "ruff check ."),
        ("ruff_format", "ruff format --check ."),
        ("mypy", "mypy src/ config.py"),
    ):
        parts.extend(_summarize(label, snapshot[key] if isinstance(snapshot[key], dict) else {}))
    return "\n".join(parts) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="生成静态检查快照并归档到 docs/history/")
    parser.add_argument("--check", action="store_true", help="只打印摘要，不写盘")
    args = parser.parse_args()

    snapshot = collect_snapshot()

    if args.check:
        print(render_markdown(snapshot))
        return 0

    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    day = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d")
    target = HISTORY_DIR / f"static_report_{day}.md"
    target.write_text(render_markdown(snapshot), encoding="utf-8")
    for key, label in (("ruff_check", "ruff check"), ("ruff_format", "ruff format"), ("mypy", "mypy")):
        block = snapshot[key]
        assert isinstance(block, dict)
        print(f"  {label}: 退出码 {block['exit_code']}")
    print(f"快照已写入 {target.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
