#!/usr/bin/env python3
"""严格 JSON 门禁（AF 轮，2026-10-20）。

背景（AE 轮 §5.6 / §5.7 遗留）：
    Python `json.dumps` 默认 `allow_nan=True`，会把 NaN / ±Infinity 写成裸
    `NaN` / `Infinity`。Python 自己能读回，但这不是 RFC 8259 合法 JSON——
    jq / Go / Rust serde / JavaScript `JSON.parse` 会直接拒绝。AE 轮只保证
    `run_b8` 的价目路径不再新增；本门禁把"严格"变成全仓可执行契约。

三类检查：
    1. **工件**：受版本控制的 `.json` 必须可被严格解析；`.jsonl` 逐行同口径。
    2. **豁免**：确认为历史/上游非 JSON 工件必须在 `_ALLOWLIST` 中逐路径登记，
       且"豁免仍在、仍非严格"——档内文件消失或已变严格都算漂移（防静默扩大）。
    3. **源码**：`src/`、`experiments/*.py`、`scripts/` 中的 JSON 文件写入点
       （`json.dump` / 写入调用内的 `json.dumps`）必须显式 `allow_nan=False`。
       `tests/` 与 `experiments/results/` 不在口径内（前者需构造坏输入，
       后者是历史工件树，不重写）。

非 git 目录（单测 fixture）回退为扫描 root 下全部文件；根目录无任何工件或
源码文件时判失败，避免"扫了个空集合"被当成通过。

用法：
    python scripts/gates/check_json_strict.py
    python scripts/gates/check_json_strict.py --root /tmp/fixture

退出码：0 = 全部通过；1 = 存在非严格工件 / 源码写入点 / 豁免漂移。
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# 逐路径豁免：历史截断行（A20 已修复根因；受保护工件不重写）。
# BZ 轮（2026-10-23）追加 3 条：AB-11/AB-12「损坏通道」语料——测试契约
# 锁定的"含损坏 trace"目录（每目录 1 个坏行文件，损坏留痕通道的观测对象），
# 归档工件不重写；随契约工件入库（见 .gitignore BZ 块）。
# 2026-10-23 provider 清理：cross_file_off 与 rag_lvl25h_n40_g8batch 两个坏行
# 文件本身引用非 DeepSeek provider，已随清理删除，对应豁免同步移除。
_ALLOWLIST: dict[str, str] = {
    # CI 轮第三批（2026-10-24）：三条历史 trace 豁免随 experiments/results/
    # 全量数据清除一并删除（「文件消失 ⇒ 删登记」）；重跑生成新工件后按需重建。
}

_EXCLUDE_PARTS = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".hypothesis",
}
_SOURCE_EXCLUDE_PREFIXES = ("tests/", "experiments/results/")
_WRITE_SINKS = {"write", "writelines", "write_text", "atomic_write_text"}


class _NonFinite(Exception):
    pass


def _reject_constant(token: str) -> None:
    raise _NonFinite(token)


def _check_json_text(text: str) -> str | None:
    try:
        json.loads(text, parse_constant=_reject_constant)
    except _NonFinite as exc:
        return f"含裸 {exc} token（非 RFC 8259；严格解析器会拒绝）"
    except json.JSONDecodeError as exc:
        return f"不是合法 JSON：{exc.msg}（line {exc.lineno} col {exc.colno}）"
    return None


def _check_jsonl_text(text: str) -> list[str]:
    problems: list[str] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            json.loads(line, parse_constant=_reject_constant)
        except _NonFinite as exc:
            problems.append(f"line {lineno}: 含裸 {exc} token")
        except json.JSONDecodeError as exc:
            problems.append(f"line {lineno}: {exc.msg}（col {exc.colno}）")
    return problems


def _fallback_files(root: Path, suffixes: set[str]) -> list[Path]:
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in suffixes:
            continue
        rel = path.relative_to(root)
        if any(part in _EXCLUDE_PARTS for part in rel.parts):
            continue
        files.append(path)
    return files


def _tracked_files(root: Path, patterns: list[str]) -> list[Path] | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", "--", *patterns],
            capture_output=True,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    rels = [rel for rel in proc.stdout.decode("utf-8", errors="replace").split("\0") if rel]
    return [root / rel for rel in rels]


def _repo_files(root: Path, suffixes: set[str], patterns: list[str]) -> list[Path]:
    tracked = _tracked_files(root, patterns)
    return tracked if tracked is not None else _fallback_files(root, suffixes)


def _is_json_dump(node: ast.Call) -> bool:
    func = node.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "dump"
        and isinstance(func.value, ast.Name)
        and func.value.id == "json"
    )


def _is_json_dumps(node: ast.Call) -> bool:
    func = node.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "dumps"
        and isinstance(func.value, ast.Name)
        and func.value.id == "json"
    )


def _has_allow_nan_false(node: ast.Call) -> bool:
    for keyword in node.keywords:
        if keyword.arg == "allow_nan" and isinstance(keyword.value, ast.Constant) and keyword.value.value is False:
            return True
    return False


def _is_write_sink(node: ast.Call) -> bool:
    func = node.func
    if not isinstance(func, ast.Attribute):
        return False
    if func.attr in _WRITE_SINKS:
        return True
    return func.attr == "write" and isinstance(func.value, ast.Attribute) and func.value.attr == "stdout"


def _scan_source(path: Path) -> list[tuple[int, str]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, SyntaxError) as exc:
        return [(0, f"源码不可解析：{type(exc).__name__}: {exc}")]
    problems: list[tuple[int, str]] = []

    def walk(node: ast.AST, ancestors: list[ast.AST]) -> None:
        if isinstance(node, ast.Call):
            if _is_json_dump(node) and not _has_allow_nan_false(node):
                problems.append((node.lineno, "json.dump 文件写入未显式 allow_nan=False"))
            if _is_json_dumps(node) and not _has_allow_nan_false(node):
                for ancestor in reversed(ancestors):
                    if isinstance(ancestor, ast.Call) and _is_write_sink(ancestor):
                        problems.append((node.lineno, "json.dumps 写入文件未显式 allow_nan=False"))
                        break
        for child in ast.iter_child_nodes(node):
            walk(child, [*ancestors, node])

    walk(tree, [])
    return sorted(set(problems))


def _rel(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(REPO_ROOT), help="仓库根（默认本脚本所在仓库）")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()

    failures: list[str] = []

    # ── 1. 工件严格解析 ─────────────────────────────────────────────────────
    artifact_files = _repo_files(root, {".json", ".jsonl"}, ["*.json", "*.jsonl"])
    if not artifact_files:
        failures.append("未扫描到任何 .json/.jsonl 工件（拒绝空集合通过）")
    allowed_seen: dict[str, str | None] = {rel: None for rel in _ALLOWLIST}
    checked = 0
    strict_ok = 0
    allowlisted = 0
    for path in artifact_files:
        rel = _rel(root, path)
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            problems = [f"读取失败：{type(exc).__name__}: {exc}"]
        else:
            problems = _check_jsonl_text(text) if path.suffix == ".jsonl" else []
            if path.suffix == ".json":
                problem = _check_json_text(text)
                problems = [problem] if problem else []
        checked += 1
        if not problems:
            strict_ok += 1
            if rel in _ALLOWLIST:
                allowed_seen[rel] = "已可严格解析（豁免过期，应删除）"
            continue
        if rel in _ALLOWLIST:
            allowlisted += 1
            allowed_seen[rel] = "ok"
            continue
        detail = "；".join(problems[:3])
        failures.append(f"非严格 JSON 工件 {rel}：{detail}")

    for rel, status in allowed_seen.items():
        if status is None:
            failures.append(f"豁免失效：{rel} 不在受扫描工件中（删除该条豁免）")
        elif status != "ok":
            failures.append(f"豁免漂移：{rel} {status}")

    # ── 2. 源码写入点 ───────────────────────────────────────────────────────
    source_files = _repo_files(root, {".py"}, ["*.py"])
    source_files = [p for p in source_files if not _rel(root, p).startswith(_SOURCE_EXCLUDE_PREFIXES)]
    if not source_files:
        failures.append("未扫描到任何源码文件（拒绝空集合通过）")
    sink_problems = 0
    for path in source_files:
        for lineno, problem in _scan_source(path):
            failures.append(f"非严格 JSON 写入点 {_rel(root, path)}:{lineno}：{problem}")
            sink_problems += 1

    print(
        f"工件 {checked} 份（json/jsonl）= 严格 {strict_ok} + 登记豁免 {allowlisted}"
        f" + 违规 {checked - strict_ok - allowlisted}；"
        f"源码 {len(source_files)} 份，写入点违规 {sink_problems} 处"
    )
    for rel, reason in _ALLOWLIST.items():
        print(f"  豁免：{rel}（{reason}）")

    if failures:
        print("\n严格 JSON 门禁失败：")
        for failure in failures:
            print(f"  ✗ {failure}")
        return 1
    print("\n严格 JSON 门禁通过（工件严格可解析 + 源码写入点 allow_nan=False）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
