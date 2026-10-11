"""规格欠定度（Specification Ambiguity Index, SAI）——把"规格歧义"变成可测量的量。

## 研究问题（本模块要回答的那一个）

> **一个测试生成基准的 gold 实现，在多大程度上"任意地"固定了自然语言规格未决定的语义？**

## 动机：实测到的现象（2026-10-11，真实 LLM）

对 QuixBugs 4 个任务各独立生成 5 份实现（只给函数名 + "按通用语义正确实现"）：

| 任务 | 探针 | LLM 内部一致 | 多数 = gold |
|---|---|---|---|
| `gcd` | 4 | 4/4 | 4/4 |
| **`get_factors`** | 3 | 3/3 | **0/3** |
| `max_sublist_sum` | 2 | 2/2 | 1/2 |
| `levenshtein` | 2 | 2/2 | 2/2 |
| **合计** | **11** | **11/11 = 100%** | **7/11 = 64%** |

`get_factors(12)`：gold 给 `[2,2,3]`（**质因数**），5/5 独立实现一致给 `[1,2,3,4,6,12]`（**全部因子**）。
`gcd(-1,-3)`：gold 给 `-1`（保留符号），一致给 `1`（同 `math.gcd`）。

**结论**：这些不一致**不是模型错误**——是**规格欠定**（underspecification）。
基准用**单参考实现**单方面固定了欠定点。

## 定义（本模块采用的、可操作的定义）

给定函数 `f`、探针输入集合 `I`、以及 `n` 份**相互独立**的正确实现
`P = {p₁..pₙ}`（由独立 LLM 生成，不含参考实现）：

- **确定点**（determined）：`|{behavior(pᵢ, x)}| = 1`（全部实现行为一致）
- **欠定点**（ambiguous）：`|{behavior(pᵢ, x)}| ≥ 2`（出现分歧）
- **SAI（规格欠定度）** `= |{x ∈ I : x 欠定}| / |I|`

**补充指标**：
- **gold 偏离率**（gold deviation）：在**确定点**上，`behavior(gold, x) ≠ behavior(pᵢ, x)` 的比例
  ——这是最关键的指标：**若规格在 x 上是确定的（所有人一致），而 gold 不同于所有人，
  则说明 gold 选择了"违反常规"的那一支**；
- **欠定点清单**：逐点给出"gold 取值 vs 各实现取值分布"，供人工与论文直接引用。

## 为什么这是可发表的方法学贡献

一手依据：
- [arXiv:2608.19626]（2026-08）证明"执行反馈 + 单参考 oracle"会制造**表面进化增益**
  （单参考膨胀 9.46–14.85 pp，审计后等预算独立重采样反优 6.01–18.83 pp）；
- [arXiv:2609.09315] 把失效定位到 **oracle**；
- 本模块把"oracle 不可信"从**定性**推进到**可量化的基准属性**：
  **SAI 与 gold 偏离率是基准的元指标，与任何被测模型无关。**

## 用法

    from experiments.spec_ambiguity import (
        build_probe_inputs, collect_implementations, compute_sai, render_report,
    )

    probes = build_probe_inputs(sample_code, fn_name, limit=40)      # 自动生成探针输入
    impls = collect_implementations(fn_name, n=5, agent=...)          # LLM 独立实现
    sai = compute_sai(impls=impls, gold_code=gold, module=fn_name, probes=probes)
    print(render_report(sai))

零 LLM 复算：`collect_implementations` 只在生成阶段调用 LLM；`compute_sai` 及其之后**零 LLM**。
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# 行为归一化后的探针源码（复用 SDTS 的安全阀：1s 软超时 + 归一化）
_PROBE_TMPL = """
import json, signal, inspect, collections.abc as _abc

class _TO(Exception):
    pass

def _h(s, f):
    raise _TO()

def _norm(v):
    if isinstance(v, (str, bytes, int, float, bool)) or v is None:
        return v
    if isinstance(v, dict):
        return {{str(k): _norm(x) for k, x in sorted(v.items(), key=lambda kv: str(kv[0]))}}
    if isinstance(v, (set, frozenset)):
        return sorted((_norm(x) for x in v), key=repr)
    if isinstance(v, (list, tuple)):
        return [_norm(x) for x in v]
    if isinstance(v, _abc.Iterator) or (hasattr(v, "__next__") and not hasattr(v, "__len__")):
        try:
            return [_norm(x) for x in list(v)[:200]]
        except Exception as e:
            return "<iter-error:%s>" % type(e).__name__
    import re as _re
    return _re.sub(r"0x[0-9a-fA-F]+", "0xADDR", repr(v))[:200]

signal.signal(signal.SIGALRM, _h)
signal.setitimer(signal.ITIMER_REAL, 1.0)
try:
    import {module} as _m
    _fn = getattr(_m, "{fn}")
    _args = {args}
    try:
        _out = _fn(*_args)
        _r = {{"kind": "ok", "value": _norm(_out)}}
    except _TO:
        _r = {{"kind": "timeout"}}
    except Exception as e:
        _r = {{"kind": "exc", "value": type(e).__name__}}
finally:
    signal.setitimer(signal.ITIMER_REAL, 0)
print(json.dumps(_r, sort_keys=True, default=str))
"""


@dataclass
class ProbePoint:
    """单个探针输入上的跨实现观测。"""

    args: list[Any]
    behaviors: list[str] = field(default_factory=list)  # 各实现的归一化行为
    gold_behavior: str = ""
    implementations_used: int = 0

    @property
    def distinct(self) -> int:
        return len(set(self.behaviors))

    @property
    def is_ambiguous(self) -> bool:
        return self.distinct >= 2

    @property
    def majority(self) -> str | None:
        if not self.behaviors:
            return None
        return max(set(self.behaviors), key=self.behaviors.count)

    @property
    def gold_deviates(self) -> bool:
        """在**确定点**上 gold 是否偏离全体一致取值。"""
        return (not self.is_ambiguous) and bool(self.gold_behavior) and self.gold_behavior != self.majority

    def render(self) -> str:
        dist: dict[str, int] = {}
        for b in self.behaviors:
            dist[b] = dist.get(b, 0) + 1
        return (
            f"输入 {json.dumps(self.args, ensure_ascii=False)}："
            f"gold={self.gold_behavior or '?'}；实现分布={json.dumps(dist, ensure_ascii=False)}"
        )


@dataclass
class SAIResult:
    """规格欠定度结果（全部可复算）。"""

    fn: str = ""
    points: list[ProbePoint] = field(default_factory=list)
    n_implementations: int = 0
    available: bool = False
    not_available_reason: str = ""

    @property
    def n_probes(self) -> int:
        return len(self.points)

    @property
    def n_ambiguous(self) -> int:
        return sum(1 for p in self.points if p.is_ambiguous)

    @property
    def sai(self) -> float | None:
        """规格欠定度 = 欠定点 / 全部点。"""
        if not self.points:
            return None
        return round(self.n_ambiguous / len(self.points), 4)

    @property
    def n_determined(self) -> int:
        return self.n_probes - self.n_ambiguous

    @property
    def gold_deviation_rate(self) -> float | None:
        """gold 偏离率 = 在确定点上 gold ≠ 全体一致取值的比例。"""
        det = [p for p in self.points if not p.is_ambiguous and p.gold_behavior]
        if not det:
            return None
        return round(sum(1 for p in det if p.gold_deviates) / len(det), 4)

    def ambiguous_points(self) -> list[ProbePoint]:
        return [p for p in self.points if p.is_ambiguous]

    def gold_deviation_points(self) -> list[ProbePoint]:
        return [p for p in self.points if p.gold_deviates]

    def as_dict(self) -> dict[str, Any]:
        return {
            "fn": self.fn,
            "available": self.available,
            "not_available_reason": self.not_available_reason,
            "n_implementations": self.n_implementations,
            "n_probes": self.n_probes,
            "n_ambiguous": self.n_ambiguous,
            "n_determined": self.n_determined,
            "sai": self.sai,
            "gold_deviation_rate": self.gold_deviation_rate,
            "ambiguous_points": [p.render() for p in self.ambiguous_points()[:20]],
            "gold_deviation_points": [p.render() for p in self.gold_deviation_points()[:20]],
        }


def build_probe_inputs(fn_name: str, sample_code: str, *, limit: int = 40, seed: int = 42) -> list[list[Any]]:
    """按参数族自动生成探针输入（复用 SDTS 的名称启发式 + hypothesis 策略）。"""
    import ast

    from experiments.solver_directed_trigger import _strategy_for, infer_param_family

    try:
        tree = ast.parse(sample_code)
    except SyntaxError:
        return []
    node = next((n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == fn_name), None)
    if node is None:
        return []
    params = [a.arg for a in node.args.args if a.arg not in ("self", "cls")]
    defaults = len(node.args.defaults)
    required = params[: len(params) - defaults] if defaults else params
    fams = [infer_param_family(p, sample_code) for p in required]
    if not fams:
        return []

    from hypothesis import HealthCheck, given, settings
    from hypothesis import strategies as st

    seen: list[list[Any]] = []
    strat = (
        st.tuples(*[_strategy_for(f) for f in fams]) if len(fams) > 1 else _strategy_for(fams[0]).map(lambda v: (v,))
    )

    @settings(max_examples=limit, deadline=None, suppress_health_check=list(HealthCheck), derandomize=True)
    @given(strat)
    def _collect(case: Any) -> None:
        args = list(case) if isinstance(case, tuple) else [case]
        if args not in seen:
            seen.append(args)

    try:
        _collect()
    except Exception:
        logger.warning("探针生成异常（已收集 %d 个）", len(seen), exc_info=True)
    return seen[:limit]


def _behavior(code: str, fn_name: str, module: str, args: list[Any], timeout: int) -> str | None:
    """在隔离环境取一次行为摘要（归一化 + 1s 软超时）。"""
    tmp = tempfile.mkdtemp(prefix="aitester_sai_")
    try:
        with open(os.path.join(tmp, f"{module}.py"), "w", encoding="utf-8") as f:
            f.write(code)
        probe = os.path.join(tmp, "_sai_probe.py")
        with open(probe, "w", encoding="utf-8") as f:
            f.write(_PROBE_TMPL.format(module=module, fn=fn_name, args=repr(args)))
        try:
            res = subprocess.run(
                [sys.executable, probe],
                cwd=tmp,
                capture_output=True,
                text=True,
                timeout=timeout,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": tmp},
                check=False,
            )
        except subprocess.TimeoutExpired:
            return "timeout"
        if res.returncode != 0:
            return None
        payload = json.loads((res.stdout or "").strip() or "{}")
        kind = payload.get("kind")
        if kind == "ok":
            return f"ok:{json.dumps(payload.get('value'), sort_keys=True, default=str)}"
        if kind == "exc":
            return f"exc:{payload.get('value')}"
        return "timeout" if kind == "timeout" else None
    except Exception:
        logger.debug("SAI 探针失败", exc_info=True)
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def compute_sai(
    *,
    implementations: list[str],
    gold_code: str,
    fn_name: str,
    probes: list[list[Any]],
    module_name: str | None = None,
    timeout: int = 20,
    workers: int = 8,
) -> SAIResult:
    """计算 SAI 与 gold 偏离率。

    Args:
        implementations: 相互独立的正确实现（**不得包含 gold**）。
        gold_code: 基准参考实现（仅用于对比，不参与"确定/欠定"判定）。
        fn_name: 函数名。
        probes: 探针输入列表。
        module_name: 落盘模块名（默认 = fn_name）。
        timeout: 单次探针超时。
        workers: 并行度（每次探针是独立子进程）。

    Returns:
        `SAIResult`。`available=False` 当且仅当实现数不足 2 或探针为空。
    """
    from concurrent.futures import ThreadPoolExecutor

    out = SAIResult(fn=fn_name)
    impls = [c for c in implementations if (c or "").strip()]
    if len(impls) < 2:
        out.not_available_reason = "need_at_least_2_implementations"
        return out
    if not probes:
        out.not_available_reason = "no_probes"
        return out
    out.n_implementations = len(impls)
    module = module_name or fn_name

    def _one(args: list[Any]) -> ProbePoint:
        pp = ProbePoint(args=args)
        pp.behaviors = [b for b in (_behavior(c, fn_name, module, args, timeout) for c in impls) if b is not None]
        pp.implementations_used = len(pp.behaviors)
        pp.gold_behavior = _behavior(gold_code, fn_name, module, args, timeout) or ""
        return pp

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        out.points = list(pool.map(_one, probes))
    # 只保留至少 2 份实现成功观测的点（否则无法判定分歧）
    out.points = [p for p in out.points if p.implementations_used >= 2]
    out.available = bool(out.points)
    if not out.available:
        out.not_available_reason = "no_usable_probe_points"
    return out


def render_report(results: list[SAIResult], *, title: str = "规格欠定度（SAI）报告") -> str:
    """渲染人读报告（论文可直接引用的表格 + 欠定点清单）。"""
    lines = [f"# {title}\n"]
    lines.append("| 函数 | 实现数 | 探针数 | **欠定点** | **SAI** | 确定点 | **gold 偏离率** |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in results:
        if not r.available:
            lines.append(f"| `{r.fn}` | {r.n_implementations} | — | — | — | — | — |")
            continue
        lines.append(
            f"| `{r.fn}` | {r.n_implementations} | {r.n_probes} | **{r.n_ambiguous}** | "
            f"**{r.sai}** | {r.n_determined} | **{r.gold_deviation_rate}** |"
        )
    ok = [r for r in results if r.available]
    if ok:
        tot_p = sum(r.n_probes for r in ok)
        tot_a = sum(r.n_ambiguous for r in ok)
        det = sum(r.n_determined for r in ok)
        dev = sum(len(r.gold_deviation_points()) for r in ok)
        lines.append("")
        lines.append(
            f"**汇总**：{len(ok)} 个函数、{tot_p} 个探针点；"
            f"欠定 {tot_a}（**池级 SAI = {tot_a / max(tot_p, 1):.3f}**）；"
            f"确定 {det}，其中 gold 偏离 {dev}（**池级偏离率 = {dev / max(det, 1):.3f}**）"
        )
    lines.append("\n## 欠定点清单（论文引用用）\n")
    for r in ok:
        pts = r.ambiguous_points()
        if not pts:
            continue
        lines.append(f"### `{r.fn}`（{len(pts)} 个欠定点）")
        lines.extend(f"- {p.render()}" for p in pts[:10])
        lines.append("")
    lines.append("## gold 偏离点清单（规格已确定但参考实现另选一支）\n")
    for r in ok:
        pts = r.gold_deviation_points()
        if not pts:
            continue
        lines.append(f"### `{r.fn}`（{len(pts)} 个偏离点）")
        lines.extend(f"- {p.render()}" for p in pts[:10])
        lines.append("")
    return "\n".join(lines)
