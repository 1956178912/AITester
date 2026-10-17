"""P1（2026-10-17 独立评审 §6 P1 / A-02）：独立 docstring 规格锚表构建（零 LLM）。

背景：df_spec 臂（A-10）的锚材料 = Planner 对**缺陷代码**的再描述，机制上
仍可能把缺陷行为固化成预期（df_spec 实跑 54.3% vs df 77.8%，方向为负且
显著）。独立评审给出修复路径：改用**独立于缺陷实现的人类规格**作锚，按三
级回退：(a) 人类 docstring；(b) docstring + Planner SpecExpr 子句并集；
(c) 仅在 (a)(b) 均缺失时沿用 Planner 再描述（现口径）。

QuixBugs 缺陷程序**没有函数 docstring**，但 40/41 个程序在文件尾部有一个人
类书写的顶层字符串字面量（Input/Output/Examples 规格块，只有 ``node.py``
缺失）——这就是天然的独立规格锚。本脚本零 LLM 从 QuixBugs 数据目录物化锚表：

    key   = sha256(源码.strip())（**内容寻址**——同源码同锚，免受 task_id /
            种子 / 路径漂移影响；臂侧按同一口径查表）
    value = {function_name, human_spec, source_head, source_len, human_spec_len}

两种模式：
    - 默认（doc）：只含人类规格（P1 回退 (a) 档）；40/41 有 human_spec，
      ``node.py`` 保留空串条目（覆盖统计如实披露；臂侧渲染契约见
      ``src/tools/spec_first.py::build_spec_replace_section`` 的 human_spec
      键在场语义）。
    - ``--union``：读既有 Planner 锚表（A-10 的 SPEC_ANCHOR_TABLE.json，默认
      ``experiments/results/emse_spec_anchor_20261016/``），把命中条目的
      ``logic_analysis`` 并入输出（P1 回退 (b) 档）；未命中者只保留人类规格。

确定性纪律：两次运行输出**逐字节一致**（无时间戳；program 按文件名排序；
内置 key 排序；stats 覆盖数写入表头）。
缺少数据目录 / 程序数不符 → fail-fast 非零退出并给出清晰提示（不静默产出
残缺锚表——"锚缺失静默回退"是独立评审点名的 A1 假阴性类缺陷）。

用法：
    .venv/bin/python experiments/build_docstring_anchor_table.py
    .venv/bin/python experiments/build_docstring_anchor_table.py --union
    AITESTER_QUIXBUGS_DATA=/path/to/quixbugs \\
        .venv/bin/python experiments/build_docstring_anchor_table.py --data-dir /path/to/quixbugs
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.tools.spec_first import (  # noqa: E402
    module_spec_text,
    sole_top_level_function_name,
)
from src.utils.atomic_io import atomic_write_json  # noqa: E402

# 数据目录：显式 --data-dir > AITESTER_QUIXBUGS_DATA > 仓内 data/quixbugs
# （与 src/datasets/dataset_realbugs.py 的环境变量口径一致；仓内目录 gitignored）。
_DATA_DIR_ENV = "AITESTER_QUIXBUGS_DATA"
DEFAULT_DATA_DIR = _REPO_ROOT / "data" / "quixbugs"
_PROGRAMS_SUBDIR = "python_programs"
# QuixBugs 缺陷程序官方口径：41 个（另 9 个 *_test.py 属测试驱动任务，不在
# 主分析集 41 口径内；dataset loader 的 50 任务 = 41 + 9）。
EXPECTED_PROGRAMS = 41

DEFAULT_OUT_DIR = _REPO_ROOT / "experiments" / "results" / "emse_docstring_anchor_20261017"
DEFAULT_PLANNER_TABLE = _REPO_ROOT / "experiments" / "results" / "emse_spec_anchor_20261016" / "SPEC_ANCHOR_TABLE.json"
TABLE_NAME = "DOCSTRING_ANCHOR_TABLE.json"
UNION_TABLE_NAME = "DOCSTRING_ANCHOR_TABLE_UNION.json"


class AnchorTableError(Exception):
    """锚表构建前置条件不满足（数据目录/程序数/Planner 表缺失或损坏）。"""


# ─── 源码侧提取 ──────────────────────────────────────────────────────────────
def _first_top_level_function_name(source: str) -> str:
    """首个顶层函数名（多函数模块的保守回退；无 → 空串）。

    与 ``src/datasets/dataset_realbugs.py::_first_top_level_function``（数据
    加载器 ``metadata["suggested_function"]`` 的来源）同口径，仅补 async 与
    异常面——锚表 function_name 只用于渲染签名，签名缺失不会影响人类规格
    锚的注入（渲染器保守降级）。
    """
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, TypeError, MemoryError, RecursionError):
        return ""
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return node.name
    return ""


def anchor_function_name(source: str) -> str:
    """锚条目 function_name：优先无歧义的唯一顶层函数，否则回退首顶层函数。

    复用 ``sole_top_level_function_name``（2026-10-14 度量侧修正，与节点渲染
    侧的回退口径同源）；多函数模块（如 ``shortest_path_length.py``）用
    ``_first_top_level_function_name`` 给出与数据加载器一致的保守默认。
    """
    sole = sole_top_level_function_name(source)
    if sole:
        return sole
    return _first_top_level_function_name(source)


def source_digest(source: str) -> str:
    """锚表内容寻址键：sha256(源码.strip())（与臂侧查表口径逐字一致）。"""
    return hashlib.sha256(source.strip().encode("utf-8")).hexdigest()


def _source_head(source: str) -> str:
    """源码首行摘要（审计用；与 Planner 锚表同格式）。"""
    stripped = source.strip()
    return stripped.splitlines()[0][:120] if stripped else ""


def program_files(programs_dir: Path) -> list[Path]:
    """枚举 QuixBugs 缺陷程序文件（确定性排序；排除 *_test.py 测试驱动）。"""
    return [p for p in sorted(programs_dir.glob("*.py")) if not p.name.endswith("_test.py")]


# ─── 锚表构建 ────────────────────────────────────────────────────────────────
def _load_planner_anchors(planner_table: Path) -> dict[str, dict[str, Any]]:
    """读 Planner 锚表 anchors 映射（缺失/损坏/形状不符 → AnchorTableError）。"""
    if not planner_table.is_file():
        raise AnchorTableError(
            f"Planner 锚表缺失：{planner_table}\n"
            "请先运行 .venv/bin/python experiments/build_spec_anchor_table.py 生成，"
            "或用 --planner-table 指定路径"
        )
    try:
        data = json.loads(planner_table.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise AnchorTableError(f"Planner 锚表损坏：{planner_table}（{e}）") from e
    anchors = data.get("anchors") if isinstance(data, dict) else None
    if not isinstance(anchors, dict):
        raise AnchorTableError(f"Planner 锚表结构不符（缺少 anchors 映射）：{planner_table}")
    return anchors


def build_doc_anchor_table(
    data_dir: Path,
    *,
    planner_table: Path | None = None,
    expect_programs: int | None = EXPECTED_PROGRAMS,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """从 QuixBugs 数据目录构建 docstring 锚表（planner_table 非 None = union）。

    Args:
        data_dir: QuixBugs 根目录（其下须有 ``python_programs/``）。
        planner_table: union 模式下并入 ``logic_analysis`` 的 Planner 锚表；
            None = 纯人类规格锚（doc 模式）。
        expect_programs: 期望缺陷程序数（默认 41；None = 不校验，供小样本测试）。

    Returns:
        ``(table, stats)``——table 为完整产出结构（meta + anchors），stats 为
        透出计数字典（与 meta 同源，便于测试断言）。

    Raises:
        AnchorTableError: 数据目录缺失 / 程序数不符 / union 的 Planner 表不可用。
    """
    programs_dir = data_dir / _PROGRAMS_SUBDIR
    if not programs_dir.is_dir():
        raise AnchorTableError(
            f"QuixBugs 数据目录缺失：{programs_dir}\n"
            "请克隆 https://github.com/jkoppel/QuixBugs 到该位置，"
            f"或设 {_DATA_DIR_ENV} 指向已克隆目录（也可用 --data-dir 显式指定）"
        )
    files = program_files(programs_dir)
    if not files:
        raise AnchorTableError(f"QuixBugs python_programs 目录为空：{programs_dir}")
    if expect_programs is not None and len(files) != expect_programs:
        raise AnchorTableError(
            f"QuixBugs 缺陷程序数不符：期望 {expect_programs} 个，实得 {len(files)} 个"
            f"（python_programs 目录：{programs_dir}）；如确认数据完整可用 --expect-programs 覆盖"
        )

    planner_anchors = _load_planner_anchors(planner_table) if planner_table is not None else None
    stats: dict[str, Any] = {
        "programs": len(files),
        "human_spec_present": 0,
        "human_spec_missing": 0,
        "human_spec_missing_programs": [],
        "function_name_present": 0,
        "function_name_missing_programs": [],
        "table_entries": len(files),
        "union_matched": 0,
        "union_missing": 0,
        "union_missing_programs": [],
    }
    anchors: dict[str, dict[str, Any]] = {}
    for path in files:
        source = path.read_text(encoding="utf-8")
        digest = source_digest(source)
        human_spec = module_spec_text(source)
        function_name = anchor_function_name(source)
        entry: dict[str, Any] = {
            "function_name": function_name,
            "human_spec": human_spec,
            "source_head": _source_head(source),
            "source_len": len(source),
            "human_spec_len": len(human_spec),
        }
        if human_spec:
            stats["human_spec_present"] += 1
        else:
            stats["human_spec_missing"] += 1
            stats["human_spec_missing_programs"].append(path.stem)
        if function_name:
            stats["function_name_present"] += 1
        else:
            stats["function_name_missing_programs"].append(path.stem)
        if planner_anchors is not None:
            planner_entry = planner_anchors.get(digest)
            logic = planner_entry.get("logic_analysis") if isinstance(planner_entry, dict) else None
            if isinstance(logic, dict) and logic:
                # P1 回退 (b)：人类规格锚 + Planner SpecExpr 子句并集
                entry["logic_analysis"] = logic
                stats["union_matched"] += 1
            else:
                # 未命中只保留 human_spec（回退 (a) 档），不伪造形式化子句
                stats["union_missing"] += 1
                stats["union_missing_programs"].append(path.stem)
        anchors[digest] = entry

    meta: dict[str, Any] = {
        "schema": 1,
        "generated_by": "experiments/build_docstring_anchor_table.py",
        "mode": "union" if planner_anchors is not None else "doc",
        "data_dir": str(data_dir),
        "programs_dir": str(programs_dir),
        "expected_programs": expect_programs,
        **stats,
    }
    if planner_table is not None:
        meta["planner_table"] = str(planner_table)
        meta["planner_table_sha256"] = hashlib.sha256(planner_table.read_bytes()).hexdigest()
    table = {"meta": meta, "anchors": anchors}
    return table, stats


def default_data_dir() -> Path:
    """数据目录口径：AITESTER_QUIXBUGS_DATA > 仓内 data/quixbugs。"""
    env = (os.environ.get(_DATA_DIR_ENV) or "").strip()
    return Path(env) if env else DEFAULT_DATA_DIR


def output_name(union: bool) -> str:
    """输出文件名（doc / union 两套工件互不覆盖）。"""
    return UNION_TABLE_NAME if union else TABLE_NAME


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "--data-dir",
        default=None,
        help=f"QuixBugs 数据根目录（默认 {_DATA_DIR_ENV} 或仓内 data/quixbugs）",
    )
    ap.add_argument("--out", default=None, help=f"输出目录（默认 {DEFAULT_OUT_DIR}）")
    ap.add_argument("--union", action="store_true", help="并集模式：并入 Planner 锚表的 logic_analysis")
    ap.add_argument(
        "--planner-table",
        default=None,
        help=f"Planner 锚表路径（仅 --union 生效；默认 {DEFAULT_PLANNER_TABLE}）",
    )
    ap.add_argument(
        "--expect-programs",
        type=int,
        default=EXPECTED_PROGRAMS,
        help=f"期望缺陷程序数（默认 {EXPECTED_PROGRAMS}；数据不完整时 fail-fast）",
    )
    args = ap.parse_args(argv)

    if args.planner_table and not args.union:
        print("[build_docstring_anchor_table] ✗ --planner-table 仅与 --union 同用", file=sys.stderr)
        return 1
    data_dir = Path(args.data_dir) if args.data_dir else default_data_dir()
    out_dir = Path(args.out) if args.out else DEFAULT_OUT_DIR
    planner_table = None
    if args.union:
        planner_table = Path(args.planner_table) if args.planner_table else DEFAULT_PLANNER_TABLE

    try:
        table, stats = build_doc_anchor_table(
            data_dir,
            planner_table=planner_table,
            expect_programs=args.expect_programs,
        )
    except AnchorTableError as e:
        print(f"[build_docstring_anchor_table] ✗ {e}", file=sys.stderr)
        return 1

    out_path = out_dir / output_name(args.union)
    out_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(str(out_path), table, indent=2, mode=0o644)
    meta = table["meta"]
    union_note = ""
    if args.union:
        union_note = (
            f"；union 命中 {stats['union_matched']}/{stats['programs']}"
            f"（未命中 {stats['union_missing']}，仅保留 human_spec）"
        )
    print(
        f"[build_docstring_anchor_table] ✓ 写入 {out_path}\n"
        f"    模式 {meta['mode']} / 程序 {stats['programs']} / 锚 {meta['table_entries']} 条；"
        f"human_spec {stats['human_spec_present']}/{stats['programs']} 覆盖"
        f"（缺失：{stats['human_spec_missing_programs'] or '无'}）；"
        f"function_name {stats['function_name_present']}/{stats['programs']}{union_note}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
