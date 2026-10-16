"""A-10（2026-10-16）：df_spec 臂规格锚表预计算（零 LLM，只读 Planner LLM 缓存）。

背景：`plain_llm_df_spec` 臂（独立评审 P0 / P1 超越路径核心对照臂）需要在
**无 Planner** 的纯提示流程里注入"规格锚文档"——材料 = Planner 计划的
``{function_name, logic_analysis}`` 子集。本脚本把既有批次已跑过的 Planner
响应从 LLM 缓存（默认 ``~/.cache/aitester/llm/*.json``，``AITESTER_LLM_CACHE_DIR``
可覆盖）**零 LLM** 物化为锚表：

    key   = sha256(源码.strip())（**内容寻址**——同源码同锚，免受
            task_id / 种子 / 路径漂移影响；臂侧按同一口径查表）
    value = {function_name, logic_analysis, source_head, source_len,
             chosen_from（缓存条目文件名）, n_candidates, timestamp}

选择纪律（确定性，可复跑逐位一致）：
    - 同一源码多候选：优先 logic_analysis 含 ``*_expr`` 形式化子句者
      （材料更富），再按 (timestamp, 文件名) 确定性 tie-break；
    - 可用性以**真实渲染器**为准：``build_spec_replace_section`` 渲染为
      空串的条目弃用并计数（stats 披露）——校验口径与臂侧运行口径完全
      同一函数，防"表里有、跑起来空"的分裂。

产出：``--out`` 目录（默认 ``experiments/results/emse_spec_anchor_20261016/``，
与 run_benchmark._DF_SPEC_ANCHOR_TABLE_DEFAULT 同路径）下
``SPEC_ANCHOR_TABLE.json``。

用法：
    .venv/bin/python -m experiments.build_spec_anchor_table            # 默认路径
    .venv/bin/python -m experiments.build_spec_anchor_table --cache-dir /path/to/cache
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.tools.spec_first import build_spec_replace_section  # noqa: E402
from src.utils.atomic_io import atomic_write_json  # noqa: E402

DEFAULT_OUT_DIR = _REPO_ROOT / "experiments" / "results" / "emse_spec_anchor_20261016"
DEFAULT_CACHE_DIR = Path.home() / ".cache" / "aitester" / "llm"

# Planner 条目标识：system 提示词的稳定前缀（"你是一名软件测试规划师"）
_PLANNER_SYSTEM_MARKER = "软件测试规划师"
# prompt 中的源码栅栏块（"请分析以下代码并制定测试计划：\n\n```\n<source>\n```"）
_SOURCE_BLOCK_RE = re.compile(r"```(?:python)?[ \t]*\n(.*?)\n```", re.DOTALL)
# response 可能被 markdown 栅栏包裹（历史批次风格差异），解析前剥离
_RESPONSE_FENCE_RE = re.compile(r"^```(?:json)?[ \t]*\n(.*?)\n```[ \t]*$", re.DOTALL)


def _parse_response(response: str) -> tuple[dict[str, Any] | None, str]:
    """解析 Planner 响应（容错两级），返回 ``(obj | None, via)``。

    历史缓存（LLM_JSON_MODE 默认开启之前）存在 **Python 字面量风格**
    响应（单引号 / None / True，如 ``[1,'a',None]``）——严格 json.loads
    拒收。回退 ``ast.literal_eval``（安全，无代码执行）提取；两法均败 →
    ``(None, "rejected")``。via ∈ {"json", "python_literal", "rejected"}
    逐条计数进 stats（表来源口径可审计）。
    """
    text = (response or "").strip()
    m = _RESPONSE_FENCE_RE.match(text)
    if m:
        text = m.group(1).strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data, "json"
    except (ValueError, TypeError):
        pass
    try:
        obj = ast.literal_eval(text)
        if isinstance(obj, dict):
            return obj, "python_literal"
    except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):
        pass
    return None, "rejected"


def _extract_source_block(prompt: str) -> str | None:
    """从 Planner prompt 提取源码栅栏块（首个）；无 → None。"""
    m = _SOURCE_BLOCK_RE.search(prompt or "")
    if not m:
        return None
    source = m.group(1)
    return source if source.strip() else None


def _material_has_expr(material: dict[str, Any]) -> bool:
    """材料是否含 *_expr 形式化子句（候选优选判据）。"""
    logic = material.get("logic_analysis")
    if not isinstance(logic, dict):
        return False
    for key in ("preconditions_expr", "postconditions_expr", "invariants_expr"):
        value = logic.get(key)
        if isinstance(value, list) and any(str(c).strip() for c in value):
            return True
    return False


def _load_entry(path: Path) -> dict[str, Any] | None:
    """读取单个缓存条目；非 JSON / 非 dict → None。"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def build_anchor_table(cache_dir: Path) -> tuple[dict[str, Any], dict[str, int]]:
    """扫描缓存目录构建锚表。

    Args:
        cache_dir: LLM 缓存目录（``*.json`` 文件集合）。

    Returns:
        ``(table, stats)``——table 为完整产出结构（meta + anchors），
        stats 为透出计数字典（与 meta 同源，便于测试断言）。
    """
    stats = {
        "scanned_files": 0,
        "planner_entries": 0,
        "parsed_json": 0,
        "parsed_python_literal": 0,
        "rejected_json": 0,
        "rejected_no_source": 0,
        "rejected_no_function_name": 0,
        "rejected_empty_render": 0,
    }
    # 候选收集：source_hash → 候选列表（先收集后确定性优选，与文件遍历序解耦）
    candidates: dict[str, list[dict[str, Any]]] = {}

    for path in sorted(cache_dir.glob("*.json")):
        stats["scanned_files"] += 1
        entry = _load_entry(path)
        if entry is None:
            continue
        if _PLANNER_SYSTEM_MARKER not in str(entry.get("system") or ""):
            continue
        stats["planner_entries"] += 1
        source = _extract_source_block(str(entry.get("prompt") or ""))
        if source is None:
            stats["rejected_no_source"] += 1
            continue
        plan, via = _parse_response(str(entry.get("response") or ""))
        if plan is None:
            stats["rejected_json"] += 1
            continue
        stats["parsed_json" if via == "json" else "parsed_python_literal"] += 1
        fn = str(plan.get("function_name") or "").strip()
        logic = plan.get("logic_analysis")
        if not fn or not isinstance(logic, dict):
            stats["rejected_no_function_name"] += 1
            continue
        digest = hashlib.sha256(source.strip().encode("utf-8")).hexdigest()
        try:
            timestamp = float(entry.get("timestamp") or 0.0)
        except (TypeError, ValueError):
            timestamp = 0.0
        candidates.setdefault(digest, []).append(
            {
                "source": source,
                "material": {"function_name": fn, "logic_analysis": logic},
                "file": path.name,
                "timestamp": timestamp,
            }
        )

    anchors: dict[str, dict[str, Any]] = {}
    for digest in sorted(candidates):
        group = candidates[digest]
        # 确定性优选：含 *_expr 优先 → timestamp 大者优先 → 文件名小者优先
        group_sorted = sorted(
            group,
            key=lambda c: (not _material_has_expr(c["material"]), -c["timestamp"], c["file"]),
        )
        chosen = group_sorted[0]
        source = chosen["source"]
        material = chosen["material"]
        # 可用性以真实渲染器为准（与臂侧运行口径同一函数）
        rendered = build_spec_replace_section(
            material,
            source,
            module_name="",
            target_function=str(material.get("function_name") or ""),
        )
        if not rendered:
            stats["rejected_empty_render"] += 1
            continue
        anchors[digest] = {
            "function_name": material["function_name"],
            "logic_analysis": material["logic_analysis"],
            "source_head": source.strip().splitlines()[0][:120] if source.strip() else "",
            "source_len": len(source),
            "chosen_from": chosen["file"],
            "n_candidates": len(group),
            "timestamp": chosen["timestamp"],
        }

    table = {
        "meta": {
            "schema": 1,
            "generated_by": "experiments/build_spec_anchor_table.py",
            "cache_dir": str(cache_dir),
            **stats,
            "table_entries": len(anchors),
        },
        "anchors": anchors,
    }
    return table, stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache-dir", default=None, help="LLM 缓存目录（默认 ~/.cache/aitester/llm）")
    ap.add_argument("--out", default=None, help="输出目录（默认 experiments/results/emse_spec_anchor_20261016）")
    args = ap.parse_args(argv)

    cache_dir = Path(args.cache_dir) if args.cache_dir else DEFAULT_CACHE_DIR
    out_dir = Path(args.out) if args.out else DEFAULT_OUT_DIR
    if not cache_dir.is_dir():
        print(f"[build_spec_anchor_table] ✗ 缓存目录不存在：{cache_dir}")
        return 1

    table, stats = build_anchor_table(cache_dir)
    out_path = out_dir / "SPEC_ANCHOR_TABLE.json"
    out_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(out_path, table, indent=2, mode=0o644)
    meta = table["meta"]
    print(
        f"[build_spec_anchor_table] ✓ 写入 {out_path}\n"
        f"    扫描 {stats['scanned_files']} 文件 / Planner 条目 {stats['planner_entries']} / "
        f"锚 {meta['table_entries']} 条；解析：JSON {stats['parsed_json']} / "
        f"Python 字面量 {stats['parsed_python_literal']} / 失败 {stats['rejected_json']}；"
        f"弃用：无源码块 {stats['rejected_no_source']} / 缺函数名 {stats['rejected_no_function_name']} / "
        f"渲染为空 {stats['rejected_empty_render']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
