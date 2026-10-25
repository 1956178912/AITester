#!/usr/bin/env python3
"""CX（2026-10-26）：仓库卫生守卫——**构建/测试临时产物不得被 git 跟踪**。

起因（本轮实测）：CW 轮的一次 pytest 运行把 `--basetemp` 落在仓库内的
`.tmp_pytest/`，而 `.gitignore` 只登记了 `.pytest_tmp/` 与 `.pytest_tmp*/`
**没有**登记 `.tmp_pytest/` ⇒ 12 个 pytest 临时文件（含 `.lock` 与
`pytest-current` 符号链接）被**提交进仓库**，随 v1.0.0 一同发布。

为什么值得单独设门：这类文件
  - 每次跑测试都在变 ⇒ 永久制造无意义的 diff；
  - `.lock` 与 `pytest-current` 是**符号链接**⇒ 在不同机器/容器上解引用目标不同
    ⇒ 跨平台检出会炸；
  - 它们是**别人的产物**（pytest 的），进版本库等于把工具的内部布局固化成本项目的
    公开契约。

判定面：被 git 跟踪的路径里，不得出现「缓存/临时」形态。规则按**路径分量**判定
（不是后缀）——`.log` 在 `experiments/results/` 下是**故意的证据工件**，不在禁列。

口径：
  - 只看 `git ls-files`（已跟踪面），不看工作树（未跟踪文件由 .gitignore 管）；
  - 不设豁免表：缓存/临时文件进版本库没有正当理由；确有需要时应当**改名**成
    语义化的工件（如 `run_artifacts_<ts>/`）后再入库；
  - git 不可用 ⇒ 判红（无法验证 ≠ 通过）。

用法：
    python scripts/gates/check_repo_hygiene.py          # 审计，违规 exit 1
    python scripts/gates/check_repo_hygiene.py --list   # 打印命中的规则与路径

CI 接线：ci.yml test 作业（仅 3.14 档，纯 git 调用，与 Python 版本无关）。
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

#: (规则名, 命中说明, 判定函数)。判定函数收到「路径分量列表」。
#: 全部按**分量**判定：只有当某个分量整体等于（或匹配）该模式时才命中，
#: 避免 `foo/tmp_trace_notes.md` 这类正常文件名被误伤。
Rule = tuple[str, str, object]

#: 分量精确匹配（该分量整体等于此值即命中）。
_EXACT_COMPONENTS: tuple[tuple[str, str], ...] = (
    ("__pycache__", "Python 字节码缓存目录"),
    (".pytest_cache", "pytest 缓存目录"),
    (".tmp_pytest", "pytest --basetemp 落点（本轮实测被误提交 12 个文件）"),
    (".pytest_tmp", "pytest 专用 TMPDIR 沙箱"),
    (".tmp_run", "临时运行目录"),
    ("tmp_trace", "失败追踪残留（Makefile 有 clean-traces 目标）"),
    (".DS_Store", "macOS 目录元数据"),
    (".venv", "本地虚拟环境"),
    ("node_modules", "Node 依赖目录"),
)

#: 分量前缀匹配（该分量以此开头即命中）。
_PREFIX_COMPONENTS: tuple[tuple[str, str], ...] = (
    (".pytest_tmp", "pytest 专用 TMPDIR 沙箱（带后缀变体）"),
    (".coverage", "coverage 数据文件"),
)

#: 分量后缀匹配（**某个分量**以此结尾即命中）——如 `pkg.egg-info/` 这类目录分量。
_COMPONENT_SUFFIXES: tuple[tuple[str, str], ...] = ((".egg-info", "打包元数据目录"),)

#: 文件名后缀匹配（整条路径的最后一个分量以该后缀结尾即命中）。
_SUFFIX_COMPONENTS: tuple[tuple[str, str], ...] = (
    (".pyc", "Python 字节码"),
    (".pyo", "Python 优化字节码"),
)


def _hit_reason(parts: tuple[str, ...]) -> tuple[str, str] | None:
    """返回 (规则名, 命中说明)；未命中则 None。"""
    for name, why in _EXACT_COMPONENTS:
        if name in parts:
            return (name, why)
    for name, why in _PREFIX_COMPONENTS:
        if any(part.startswith(name) for part in parts):
            return (name, why)
    for name, why in _COMPONENT_SUFFIXES:
        if any(part.endswith(name) for part in parts):
            return (name, why)
    last = parts[-1] if parts else ""
    for name, why in _SUFFIX_COMPONENTS:
        if last.endswith(name):
            return (name, why)
    # 顶层 `venv/`（未带点的写法）也禁——避免与 `.venv` 规则重复登记。
    if parts and parts[0] == "venv":
        return ("venv", "本地虚拟环境（无点写法）")
    return None


def tracked_files(repo: Path) -> list[str]:
    """列出被 git 跟踪的文件（相对仓库根）。git 不可用时抛 RuntimeError。"""
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "ls-files", "-z"],
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as exc:  # pragma: no cover - 环境无 git
        raise RuntimeError("git 不可用——无法核验跟踪面") from exc
    if proc.returncode != 0:
        raise RuntimeError(f"`git ls-files` 退出码 {proc.returncode}：{proc.stderr.decode('utf-8', 'replace').strip()}")
    out = proc.stdout.decode("utf-8", "replace")
    return [p for p in out.split("\0") if p]


def find_offenders(repo: Path) -> list[tuple[str, str, str]]:
    """返回 [(相对路径, 规则名, 说明)]。"""
    offenders: list[tuple[str, str, str]] = []
    for path in tracked_files(repo):
        parts = tuple(path.split("/"))
        hit = _hit_reason(parts)
        if hit is not None:
            offenders.append((path, hit[0], hit[1]))
    return offenders


def rule_inventory() -> list[tuple[str, str, str]]:
    """列出全部规则：[(类别, 规则名, 说明)]。`--list` 打印它。"""
    rows: list[tuple[str, str, str]] = []
    for name, why in _EXACT_COMPONENTS:
        rows.append(("分量精确匹配", name, why))
    for name, why in _PREFIX_COMPONENTS:
        rows.append(("分量前缀匹配", name, why))
    for name, why in _COMPONENT_SUFFIXES:
        rows.append(("分量后缀匹配", name, why))
    for name, why in _SUFFIX_COMPONENTS:
        rows.append(("末段后缀匹配", name, why))
    rows.append(("顶层目录精确匹配", "venv", "本地虚拟环境（无点写法）"))
    return rows


#: `scripts/README.md` 里 gates 清单的小节标题形如 `## gates/（27 个）`。
_GATES_SECTION_RE = re.compile(r"^##\s+gates/（(\d+)\s*个）", re.M)
#: 清单里每一行形如 `| `check_xxx.py` | 说明 |`。
_GATES_ROW_RE = re.compile(r"^\|\s*`([^`]+)`\s*\|", re.M)


def check_gate_registry(repo: Path) -> list[str]:
    """判定面 B：`scripts/README.md` 的门禁清单必须**完整且与盘面一致**。

    起因（本轮实测）：`scripts/README.md` 的「## gates/（27 个）」与它自己的表格
    内部自洽（27 行），但**盘上已有 34 个门禁**——CF / CG / CH / BN / BK / CU 几轮
    新增的 7 道门从未登记进这张表。读者按文档找门禁，会漏掉其中 7 道；而**门禁
    数量本身**是文档里的一个手写数字，没有任何机制能发现它过期。

    三条判据：
      1. 盘上每个 `scripts/gates/*.py` 都必须出现在清单表格里；
      2. 小节标题里的个数必须等于盘上的实际个数；
      3. 表格行数必须等于标题里的个数（表与标题不能各说各话）。

    返回问题描述列表；空列表 = 通过。
    """
    problems: list[str] = []
    gates_dir = repo / "scripts" / "gates"
    actual = sorted(p.name for p in gates_dir.glob("*.py"))
    readme = repo / "scripts" / "README.md"
    if not readme.exists():
        return ["scripts/README.md 不在场——门禁清单无法对账"]
    text = readme.read_text(encoding="utf-8")

    header = _GATES_SECTION_RE.search(text)
    if not header:
        return ["scripts/README.md 里找不到「## gates/（N 个）」小节标题——门禁清单无法对账"]
    declared = int(header.group(1))

    # 只取 gates/ 小节**内部**的表格行：小节从标题行开始，到下一个 `## ` 为止。
    # （早先版本用全文正则，把 tools/ 等小节的表格行也算进来 ⇒ 行数虚高 35。）
    section_end = re.search(r"^##\s", text[header.end() :], re.M)
    section_text = text[header.end() : header.end() + section_end.start()] if section_end else text[header.end() :]
    rows = _GATES_ROW_RE.findall(section_text)
    registered = {name for name in rows if name.endswith(".py") and (gates_dir / name).exists()}

    missing = [name for name in actual if name not in registered]
    if missing:
        problems.append(f"scripts/README.md 的门禁清单漏登 {len(missing)} 道（盘上已存在）：{missing}")
    if declared != len(actual):
        problems.append(f"scripts/README.md 标题写「gates/（{declared} 个）」，盘上实有 {len(actual)} 个")
    if len(rows) != declared:
        problems.append(f"scripts/README.md 的门禁表有 {len(rows)} 行，标题写 {declared} 个——表与标题不一致")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="仓库卫生守卫：临时/缓存产物不得被 git 跟踪")
    parser.add_argument(
        "--list",
        action="store_true",
        help="打印规则清单（不改变判定与退出码）",
    )
    args = parser.parse_args(argv)

    if args.list:
        print("[repo-hygiene] 规则清单：")
        for kind, name, why in rule_inventory():
            print(f"  - [{kind}] {name}：{why}")

    failures: list[str] = []

    try:
        offenders = find_offenders(PROJECT_ROOT)
    except RuntimeError as exc:
        print(f"[repo-hygiene] ❌ {exc}")
        return 1

    if offenders:
        print(f"[repo-hygiene] ❌ 被 git 跟踪的临时/缓存产物 {len(offenders)} 个：")
        for path, rule, why in offenders:
            print(f"  - {path}  （规则「{rule}」：{why}）")
        print("[repo-hygiene] 处置：`git rm --cached <路径>` 移出索引 + 把该目录名登记进 .gitignore。")
        failures.append(f"跟踪面内含 {len(offenders)} 个临时/缓存产物")

    registry_problems = check_gate_registry(PROJECT_ROOT)
    for problem in registry_problems:
        print(f"[repo-hygiene] ❌ {problem}")
    failures.extend(registry_problems)

    if failures:
        return 1

    print("[repo-hygiene] ✅ 跟踪面内无临时/缓存产物；门禁清单与盘面一致。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
