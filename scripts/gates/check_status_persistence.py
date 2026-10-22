#!/usr/bin/env python
"""状态通道落盘可达性棘轮（BN 轮，2026-10-22；CI 阻断项）。

背景（BH→BM 系列折叠面的第六面）：
    BH/BI/BJ/BG 四轮把"读不懂 ⇒ 判优"收成四值 status 词汇（`src/utils/check_status.py`），
    BL 补消费侧双读、BM 补实验/报告读侧——**判定侧和消费侧都读得到 status 了，
    落盘边界却一个都没登记**。本轮实测（`scripts/tools/bn_dump_boundary_probe.py`）：
    static / safety / oracle 三条检查通道的 `*_status` + `*_outcomes` 在
    `experiments/run_benchmark.py` 的两道落盘边界都是"5 种运行时态 → 1 种落盘形状"
    （ok / error / unavailable / disabled / 键不存在逐字节同形）；
    `contract_status` 进了结果行、仍不在 raw 白名单。归档普查
    （`scripts/tools/bn_archive_status_census.py`：1700 个 JSON + 9096 条 JSONL 轨迹行）
    给出这些键 **0 次出现**——披露只活在内存里，事后无法复核"检查完成且零疑点"
    与"检查崩了 / 按设计没跑"的区别。

本守卫（纯 stdlib AST 扫描 + 与 state-contract 同源的运行时声明面，零新依赖）：
    1. 声明面：`src/graph/state.py::AITesterState` 注解里以 `_status` / `_outcomes`
       结尾的通道（新增通道自动纳管，无需改本文件）；
    2. 落盘面：`_dump_state_artifacts` 里赋给 `artifact` 的 dict 字面量常量键，
       以及 `_build_task_result` **每一个** return dict 的常量键（两分支各自算，
       避免"只在一支登记"的漂移）；`**helper(...)` 展开的键按 helper 返回字典的
       常量键并集计入，展开不可静态判定时**不计入**（宁可假红，不可假绿）；
    3. 声明面 ⊄ 落盘面 ⇒ 违规，exit 1 阻断。豁免清单为空：本轮起 10 个声明通道
       全部登记，任何新通道不落盘就直接红。

CLI：
    python scripts/gates/check_status_persistence.py          # 审计，违规 exit 1
    python scripts/gates/check_status_persistence.py --list   # 只打印声明面与两个落盘面，exit 0
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

RUN_BENCHMARK = PROJECT_ROOT / "experiments" / "run_benchmark.py"
#: 通道后缀名：与 `src/observability/agent_telemetry.py` 的 status 词汇同族
CHANNEL_SUFFIXES: tuple[str, ...] = ("_status", "_outcomes")


def _rel(p: Path) -> str:
    return str(p.relative_to(PROJECT_ROOT))


def declared_channels() -> list[str]:
    """声明面 = AITesterState 注解里的 status/outcomes 通道（运行时导入，与门禁同源）。"""
    from src.graph.state import AITesterState

    return sorted(k for k in AITesterState.__annotations__ if k.endswith(CHANNEL_SUFFIXES))


def _constant_keys(node: ast.Dict) -> set[str]:
    return {k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}


def _returned_keys(fn: ast.FunctionDef) -> set[str]:
    """函数所有 return 字典字面量的常量键并集（用于解析 `**helper(...)` 展开）。"""
    keys: set[str] = set()
    for n in ast.walk(fn):
        if isinstance(n, ast.Return) and isinstance(n.value, ast.Dict):
            keys |= _constant_keys(n.value)
    return keys


def _dict_keys(node: ast.Dict, module_fns: dict[str, set[str]]) -> set[str]:
    """一个 dict 字面量的键集：常量键 + 可静态判定的 `**helper` 展开键。"""
    keys = _constant_keys(node)
    for k, v in zip(node.keys, node.values, strict=True):
        if k is not None or not isinstance(v, ast.Call):
            continue
        callee = v.func
        name = callee.id if isinstance(callee, ast.Name) else ""
        if name in module_fns:
            keys |= module_fns[name]
    return keys


def persisted_keys(path: Path) -> dict[str, set[str]]:
    """落盘面：返回 边界名 → 键集。

    - `raw_artifact`：`_dump_state_artifacts` 里 `artifact = {...}` 的键；
    - `result_row@<行号>`：`_build_task_result` 里每个 return 字典的键。
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    fns = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    module_keys = {name: _returned_keys(fn) for name, fn in fns.items()}

    surfaces: dict[str, set[str]] = {}
    dump = fns.get("_dump_state_artifacts")
    if dump is None:
        raise SystemExit(f"❌ {_rel(path)} 里找不到 _dump_state_artifacts（落盘边界改名需同步本守卫）")
    for n in ast.walk(dump):
        if (
            isinstance(n, ast.Assign)
            and isinstance(n.value, ast.Dict)
            and any(isinstance(t, ast.Name) and t.id == "artifact" for t in n.targets)
        ):
            surfaces["raw_artifact"] = _dict_keys(n.value, module_keys)
    if "raw_artifact" not in surfaces:
        raise SystemExit(f"❌ {_rel(path)}::_dump_state_artifacts 里找不到 artifact 字典字面量")
    row = fns.get("_build_task_result")
    if row is None:
        raise SystemExit(f"❌ {_rel(path)} 里找不到 _build_task_result（落盘边界改名需同步本守卫）")
    for n in ast.walk(row):
        if isinstance(n, ast.Return) and isinstance(n.value, ast.Dict):
            surfaces[f"result_row@{n.lineno}"] = _dict_keys(n.value, module_keys)
    return surfaces


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="只打印声明面与落盘面键集，不判定")
    args = parser.parse_args()

    channels = declared_channels()
    surfaces = persisted_keys(RUN_BENCHMARK)
    if args.list:
        print(f"声明面（AITesterState 的 status/outcomes 通道）{len(channels)} 个：")
        for c in channels:
            print(f"  {c}")
        for name, keys in sorted(surfaces.items()):
            print(f"落盘面 {name}：{len(keys)} 键，其中通道 {sorted(k for k in keys if k.endswith(CHANNEL_SUFFIXES))}")
        return

    missing = [(c, name) for c in channels for name, keys in sorted(surfaces.items()) if c not in keys]
    if not missing:
        row_surfaces = [n for n in surfaces if n.startswith("result_row@")]
        print(
            f"状态通道落盘可达性审计通过：声明 {len(channels)} 个通道，"
            f"落盘面 {len(surfaces)} 处（raw 白名单 + 结果行 {len(row_surfaces)} 个分支）全覆盖"
        )
        return

    print(f"❌ 状态通道在落盘边界被丢弃 {len(missing)} 处（声明了却归档不到 ⇒ 事后不可复核）：")
    for channel, surface in missing:
        print(f'  "{channel}" 未在 {_rel(RUN_BENCHMARK)}::{surface} 登记')
    print(
        "\n修复口径：在 experiments/run_benchmark.py 的 _dump_state_artifacts 白名单与"
        "\n_build_task_result 的**每个** return 分支登记该通道（成功分支取 final_state.get(...)，"
        "\n失败分支以 None 占位保持键集合同构）；纯观测字段不得参与判定，判定方向逐字节不变。"
    )
    raise SystemExit(1)


if __name__ == "__main__":
    main()
