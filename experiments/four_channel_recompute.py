"""四通道检出协议 —— 零 LLM 存量重算（P1-7 / E-C 任务）。

背景
----
项目自述"`over_red` 里相当一部分是挂起，再好的 prompt 也无法让挂起的测试
变红；需测试侧超时判定"。本脚本**只读**既有入库工件，在存量数据上重算四个
检出通道是否可分离，回答：**挂起通道能把多少行从 `detection=None` /
`over_red` 变成可判定？**

四通道定义（与任务书一致）
--------------------------
1. **执行通道 C1**：断言失败红 —— 现有 ``detection_rate``（F2P 三段判定）。
2. **挂起通道 C2**：测试在 buggy 上超时 ∧ 在 gold fixed 上有限时间通过。
3. **逻辑通道 C3**：``spec_oracle`` 注入后判定失败（无数据 → ``not_available``）。
4. **覆盖通道 C4**：覆盖率增益，**仅辅助**，不得单独作为检出证据。

诚实性约束（**本脚本最重要的设计原则**）
--------------------------------------
判定"挂起"所需的字段若在存量工件中**没有记录**，必须报
``not_available`` 并给出埋点方案，**绝不编造数字**。本脚本对每个通道都输出
``verification_level``：

- ``measured``     —— 直接读工件中已记录的判定字段；
- ``proxy``        —— 用**同期、同批次**的间接痕迹推断，且明确标注推断链；
- ``not_available``—— 工件中无任何可判定字段。

存量工件实测可得的三条"挂起"痕迹（全部只读，无 LLM、无 subprocess）
------------------------------------------------------------------
R1. ``details[].execution_trace[].elapsed_seconds``：环路内执行器的**每次**
    执行耗时。超时被截断在 ``EXECUTION_TIMEOUT``（本批 = 30）→ 出现
    30.0x 的"天花板值"即为环路内超时嫌疑。
R2. 批次日志 ``<batch-dir>/<arm>.log`` 的显式文本行
    ``测试执行超时（>30s）: ... -k', '<program>'``（**唯一带程序名的直接证据**）。
R3. ``details[].specificity_gate_verdict == "specific_red"`` —— 特异性门在
    **gold fixed** 上跑绿 = 挂起通道所需的"fixed 侧有限时间通过"那一腿。

**R1/R2 都是环路内执行器（``EXECUTION_TIMEOUT=30``）的痕迹，而挂起通道的
判定层是 M1 事后裁决（``_m1_metrics._run_pytest_in_tmp``, ``timeout=120``）。
两者超时预算不同 ⇒ R1/R2 只能证明"环路内挂起"，不能证明"M1 侧挂起"。**
M1 侧的 ``rc_buggy`` / ``rc_fixed`` / 哪一侧超时**均未落盘**（``_run_pytest_in_tmp``
把 超时 / IO 异常 / 材料缺失 一律折叠成裸 ``None``，``_compute_detection_rate``
只把最终 float 透出）⇒ C2 在 M1 判定层记为 ``not_available``，另给
``C2_inloop`` 作为 ``proxy``。

用法
----
    .venv/bin/python experiments/four_channel_recompute.py            # 默认批
    .venv/bin/python experiments/four_channel_recompute.py --json-out review_2026/E3_four_channel.json
    .venv/bin/python experiments/four_channel_recompute.py --endpoint all --arms aitester plain_llm_df
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.utils.atomic_io import atomic_write_json

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_BATCH_DIR = "experiments/results/e6_a1_batches/e4_quixbugs_FIXED_harness"
DEFAULT_ARMS = ("aitester", "plain_llm_df")
DEFAULT_EXEC_TIMEOUT = 30.0

#: 环路内执行器的超时日志格式（src/graph/nodes.py::_executor_node 侧打印）。
#: 形如：``测试执行超时（>30s）: Command '[... '-k', 'bitcount']' timed out after 30 seconds``
_TIMEOUT_LOG_RE = re.compile(r"测试执行超时（>(\d+)s）")

#: 从超时日志的命令行里抽出被测 program（``-k', '<program>'``）。
_K_FLAG_RE = re.compile(r"-k',\s*'([A-Za-z0-9_]+)'")

#: QuixBugs 测试驱动脚本后缀（BASELINE.yaml:291-298 预注册口径：50 = 41 缺陷程序 + 9 测试驱动）。
_DRIVER_SUFFIX = "_test"

VERIFICATION_LEVELS = ("measured", "proxy", "not_available", "auxiliary")


# --------------------------------------------------------------------------- #
# 数据加载（只读）
# --------------------------------------------------------------------------- #
@dataclass
class Row:
    """单任务的四通道重算结果。"""

    task_id: str
    program: str
    # C1 执行通道
    c1_execution: float | None = None
    # C2 挂起通道
    c2_inloop: int = 0
    c2_m1: str = "not_available"
    c2_hang_evidence: list[str] = field(default_factory=list)
    fixed_leg_green_proxy: bool | None = None
    # C3 逻辑通道
    c3_logic: str = "not_available"
    # C4 覆盖通道（辅助）
    c4_coverage_final: float | None = None
    c4_coverage_max: float | None = None
    # 诊断元数据
    gate_verdict: str | None = None
    stop_reason: str | None = None
    error_category: str | None = None
    iterations: int | None = None
    trace_max_elapsed: float | None = None
    trace_iters_at_ceiling: int = 0
    log_timeout_hits: int = 0
    is_gold_program: bool = True

    @property
    def c1_measured(self) -> bool:
        return self.c1_execution is not None

    @property
    def c2_positive(self) -> bool:
        """挂起通道（环路内代理口径）判正：挂起痕迹 ∧ fixed 腿有限时间绿。"""
        return bool(self.c2_hang_evidence) and self.fixed_leg_green_proxy is True

    @property
    def detection_four_channel(self) -> float | None:
        """四通道合并判定（C4 仅辅助，**不**进入合并）。

        C1 可测 → 以 C1 为准（C1=1 已蕴含检出）。
        C1 不可测 → C2 判正则记 1；否则 None（逻辑通道存量不可用）。
        """
        if self.c1_execution is not None:
            return self.c1_execution
        if self.c2_positive:
            return 1.0
        return None


def _load_batch(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SystemExit(f"[four_channel] 批次工件不存在：{path}")
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def resolve_batch_file(batch_dir: Path, arm: str) -> tuple[Path, str]:
    """定位承载某臂的批次 JSON，返回 ``(路径, results 键)``。

    支持两种既有归档布局（均为只读）：
    1. **单臂一文件**（E4 归档）：``<batch-dir>/<arm>.json``，``results`` 键可能即 arm；
    2. **多臂一文件**（E6 / main_batch）：``<batch-dir>/benchmark_*.json``，
       ``results`` 下同时含多臂；取**最新**一个含该臂的文件。
    """
    direct = batch_dir / f"{arm}.json"
    candidates: list[Path] = [direct] if direct.is_file() else []
    candidates += sorted(batch_dir.glob("benchmark_*.json"), reverse=True)
    if not candidates:
        raise SystemExit(f"[four_channel] {batch_dir} 下既无 {arm}.json 也无 benchmark_*.json")
    errors: list[str] = []
    for path in candidates:
        try:
            with path.open(encoding="utf-8") as fh:
                keys = list((json.load(fh).get("results") or {}).keys())
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{path.name}: {exc}")
            continue
        if arm in keys:
            return path, arm
        if path is direct and len(keys) == 1:
            # 单臂文件但 results 键名与文件名不一致（历史命名差异）→ 退化为唯一键
            return path, keys[0]
    raise SystemExit(f"[four_channel] 未在候选文件中找到臂 {arm!r}；扫描错误={errors}")


def _exec_timeout(batch: dict[str, Any], fallback: float = DEFAULT_EXEC_TIMEOUT) -> float:
    snap = (batch.get("provenance") or {}).get("env_snapshot") or {}
    raw = snap.get("EXECUTION_TIMEOUT")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return fallback


def parse_log_hangs(log_path: Path) -> dict[str, int]:
    """从批次日志抽 ``{program: 超时次数}``（只读文本，不执行任何东西）。

    无日志文件 → 空字典（R2 证据缺失，R1 仍可用）。
    """
    hits: dict[str, int] = {}
    if not log_path.is_file():
        return hits
    with log_path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if not _TIMEOUT_LOG_RE.search(line):
                continue
            m = _K_FLAG_RE.search(line)
            if m:
                hits[m.group(1)] = hits.get(m.group(1), 0) + 1
    return hits


def build_rows(
    details: list[dict[str, Any]],
    log_hits: dict[str, int],
    exec_timeout: float,
    ceiling_tol: float = 0.6,
) -> list[Row]:
    """把 details 行重算成四通道行（纯函数，无副作用）。"""
    lo, hi = exec_timeout - ceiling_tol, exec_timeout + 0.5
    rows: list[Row] = []
    for d in details:
        task_id = str(d.get("task_id") or "")
        program = task_id.split("__")[-1] if "__" in task_id else task_id
        md = d.get("task_metadata") or {}
        trace = d.get("execution_trace") or []
        elapsed = [float(t.get("elapsed_seconds") or 0.0) for t in trace]
        at_ceiling = sum(1 for e in elapsed if lo <= e <= hi)

        row = Row(
            task_id=task_id,
            program=program,
            c1_execution=d.get("detection_rate"),
            gate_verdict=d.get("specificity_gate_verdict"),
            stop_reason=d.get("stop_reason"),
            error_category=d.get("error_category"),
            iterations=d.get("iterations"),
            trace_max_elapsed=max(elapsed) if elapsed else None,
            trace_iters_at_ceiling=at_ceiling,
            log_timeout_hits=int(log_hits.get(program, 0)),
            is_gold_program=bool((md.get("test_cases") or "").strip()) and not program.endswith(_DRIVER_SUFFIX),
        )
        # R1：环路内执行耗时触顶。
        if at_ceiling:
            row.c2_hang_evidence.append("r1_inloop_elapsed_ceiling")
        # R2：批次日志显式超时行（带程序名）。
        if row.log_timeout_hits:
            row.c2_hang_evidence.append("r2_batch_log_timeout")
        # R3：fixed 腿代理 —— 特异性门在 gold fixed 上转绿。
        if row.gate_verdict in ("specific_red", "over_red", "unavailable"):
            row.fixed_leg_green_proxy = row.gate_verdict == "specific_red"
        # 环路内代理口径的 C2。
        row.c2_inloop = int(row.c2_positive)
        # C4 覆盖（辅助）：最终覆盖 + 轨迹内最大覆盖。
        row.c4_coverage_final = d.get("coverage")
        row.c4_coverage_max = max((float(t.get("coverage") or 0.0) for t in trace), default=None)

        rows.append(row)
    return rows


# --------------------------------------------------------------------------- #
# 统计
# --------------------------------------------------------------------------- #
def _pct(num: int, den: int) -> str:
    return f"{num}/{den} = {100.0 * num / den:.1f}%" if den else "0/0 = n/a"


def _crosstab(rows: list[Row]) -> dict[str, Any]:
    """C1 × C2（环路内代理口径）2×2 交叉表。"""
    cells = {"c1_1_c2_1": 0, "c1_1_c2_0": 0, "c1_0_c2_1": 0, "c1_0_c2_0": 0, "c1_na_c2_1": 0, "c1_na_c2_0": 0}
    rescued: list[str] = []
    for r in rows:
        c2 = 1 if r.c2_positive else 0
        if r.c1_execution == 1.0:
            cells[f"c1_1_c2_{c2}"] += 1
        elif r.c1_execution == 0.0:
            cells[f"c1_0_c2_{c2}"] += 1
        else:
            cells[f"c1_na_c2_{c2}"] += 1
            if c2:
                rescued.append(r.task_id)
    return {"cells": cells, "rescued_by_hang_channel": rescued}


def _channel_separation(rows: list[Row]) -> dict[str, Any]:
    """挂起嫌疑行与 over_red 的重叠（用于检验"over_red 相当一部分是挂起"）。"""
    hang = [r for r in rows if r.c2_hang_evidence]
    over_red = [r for r in rows if r.gate_verdict == "over_red"]
    over_red_and_hang = [r for r in over_red if r.c2_hang_evidence]
    return {
        "n_rows": len(rows),
        "hang_suspect": [r.task_id for r in hang],
        "n_hang_suspect": len(hang),
        "n_over_red": len(over_red),
        "n_over_red_and_hang": len(over_red_and_hang),
        "over_red_and_hang": [r.task_id for r in over_red_and_hang],
        "hang_suspect_fixed_leg_green": [r.task_id for r in hang if r.fixed_leg_green_proxy is True],
        "hang_suspect_fixed_leg_red": [r.task_id for r in hang if r.fixed_leg_green_proxy is False],
        "hang_suspect_fixed_leg_unknown": [r.task_id for r in hang if r.fixed_leg_green_proxy is None],
    }


def _endpoint(rows: list[Row], endpoint: str) -> list[Row]:
    if endpoint == "all":
        return rows
    return [r for r in rows if r.is_gold_program]


def summarize_arm(rows: list[Row], endpoint: str, exec_timeout: float) -> dict[str, Any]:
    sel = _endpoint(rows, endpoint)
    n = len(sel)
    c1_pos = sum(1 for r in sel if r.c1_execution == 1.0)
    c1_zero = sum(1 for r in sel if r.c1_execution == 0.0)
    c1_na = sum(1 for r in sel if r.c1_execution is None)
    four_pos = sum(1 for r in sel if r.detection_four_channel == 1.0)
    four_na = sum(1 for r in sel if r.detection_four_channel is None)

    tabs = _crosstab(sel)
    sep = _channel_separation(sel)

    # 判定"over_red 里相当一部分是挂起"这一自述。
    if sep["n_over_red"] == 0:
        over_red_verdict = "n/a（本臂无 over_red 行）"
    else:
        share = 100.0 * sep["n_over_red_and_hang"] / sep["n_over_red"]
        over_red_verdict = (
            f"证否：over_red {sep['n_over_red']} 行中仅 {sep['n_over_red_and_hang']} 行有挂起痕迹"
            f"（{share:.1f}%）；「相当一部分」不成立"
            if share < 25.0
            else f"部分成立：{share:.1f}% 的 over_red 行有挂起痕迹"
        )

    return {
        "endpoint": endpoint,
        "n_rows": n,
        "execution_timeout_seconds": exec_timeout,
        "channel_1_execution": {
            "verification_level": "measured",
            "positive": c1_pos,
            "zero": c1_zero,
            "not_available": c1_na,
            "rate_denominator_measured": _pct(c1_pos, c1_pos + c1_zero),
            "rate_denominator_all": _pct(c1_pos, n),
        },
        "channel_2_hang": {
            "verification_level_m1_decision_layer": "not_available",
            "verification_level_inloop_proxy": "proxy",
            "not_available_reason": (
                "M1 事后裁决层未落盘 rc_buggy / rc_fixed / 哪一侧超时；"
                "_run_pytest_in_tmp 把 超时/IO异常/材料缺失 折叠为裸 None，"
                "_compute_detection_rate 仅透出最终 float"
            ),
            "inloop_hang_suspect": sep["n_hang_suspect"],
            "inloop_positive_fixed_leg_green": len(sep["hang_suspect_fixed_leg_green"]),
            "inloop_fixed_leg_green_ids": sep["hang_suspect_fixed_leg_green"],
            "inloop_fixed_leg_red_ids": sep["hang_suspect_fixed_leg_red"],
            "inloop_fixed_leg_unknown_ids": sep["hang_suspect_fixed_leg_unknown"],
        },
        "channel_3_logic": {
            "verification_level": "not_available",
            "not_available_reason": (
                "details[] 未透出 spec_oracle_injected（state 层已置位：src/graph/nodes.py:865）"
                "与 spec_oracle_verdict（六态行级判定：src/graph/state.py:419 / nodes.py:263-284）；"
                "experiments/run_benchmark.py 的 details 键集合未收录任一字段"
            ),
            "precursor_fields_present": ["spec_compile_rate", "spec_expr_coverage"],
        },
        "channel_4_coverage": {
            "verification_level": "auxiliary",
            "note": "仅辅助信号；不进入 detection 合并判定（与任务书定义一致）",
        },
        "crosstab_c1_x_c2_inloop": tabs,
        "rescued_by_hang_channel": tabs["rescued_by_hang_channel"],
        "n_rescued": len(tabs["rescued_by_hang_channel"]),
        "four_channel_merged": {
            "positive": four_pos,
            "not_available": four_na,
            "rate_denominator_all": _pct(four_pos, n),
            "delta_positive_rows_vs_c1": four_pos - c1_pos,
            "delta_pp_denominator_all": round(100.0 * (four_pos - c1_pos) / n, 2) if n else None,
        },
        "over_red_hang_claim": {
            "verdict": over_red_verdict,
            "n_over_red": sep["n_over_red"],
            "n_over_red_and_hang": sep["n_over_red_and_hang"],
        },
        "hang_suspect_ids": sep["hang_suspect"],
    }


def data_sufficiency() -> dict[str, Any]:
    """存量数据充分性判定（**结论性小节**，供报告直接引用）。"""
    return {
        "C1_execution": {
            "level": "measured",
            "sufficient": True,
            "note": "detection_rate 已落盘（F2P 三段判定），可直接用。",
        },
        "C2_hang": {
            "level": "proxy",
            "sufficient": False,
            "what_is_available": [
                "details[].execution_trace[].elapsed_seconds 触顶 EXECUTION_TIMEOUT（R1）",
                "批次日志 '测试执行超时（>Ns）' + '-k <program>' 显式行（R2）",
                "specificity_gate_verdict == specific_red（fixed 腿代理，R3）",
            ],
            "what_is_missing": [
                "M1 裁决层 rc_buggy（_m1_metrics.py:519）",
                "M1 裁决层 rc_fixed（_m1_metrics.py:523）",
                "两侧各自的超时/IO异常/材料缺失区分（_run_pytest_in_tmp 折叠为 None，:380-383）",
                "环路内执行器的显式 timed_out 布尔（现只能靠 elapsed≈EXECUTION_TIMEOUT 反推）",
            ],
            "why_it_matters": (
                "环路内执行器超时预算 EXECUTION_TIMEOUT=30s，M1 裁决层 timeout=120s，"
                "特异性门 timeout=60s（detection_gates.py:_GATE_TIMEOUT_SECONDS）。"
                "三者不同 ⇒ R1/R2 只证明『环路内挂起』，不能证明『M1 侧挂起』，"
                "更不能证明『挂起通道在 M1 判定标准下成立』。"
            ),
            "instrumentation_plan": [
                {
                    "file": "experiments/_m1_metrics.py",
                    "anchor": "_run_pytest_in_tmp（:298-385）",
                    "change": (
                        "新增 **平行** 函数（或 return_reason=False 的可选参数）返回"
                        "{rc, stdout, stderr, unavailable_reason ∈ timeout|io_error|support_missing|invalid_module}，"
                        "裸 None 语义保持不变（detection_gates.py:85 的委托调用零回归）"
                    ),
                },
                {
                    "file": "experiments/_m1_metrics.py",
                    "anchor": "_compute_detection_rate（:473-540）",
                    "change": (
                        "在返回值旁透出 detection_channels 子字典："
                        "{rc_buggy, rc_buggy_kind, rc_fixed, rc_fixed_kind, timeout_seconds_used}；"
                        "rc_buggy_kind/rc_fixed_kind ∈ {ok, timeout, io_error, support_missing}"
                    ),
                },
                {
                    "file": "experiments/run_benchmark.py",
                    "anchor": "details 行装配处（:1078 detection_rate 相邻）",
                    "change": "把 detection_channels 原样并入 details[]，作为 _m1_metrics 的透出字段",
                },
                {
                    "file": "experiments/run_benchmark.py",
                    "anchor": "_env_snapshot_keys（:2712-2771）",
                    "change": "登记 EXECUTION_TIMEOUT 已有；补 LLM 侧无关，但需登记新增开关（见 H1 预注册 G0 门）",
                },
            ],
        },
        "C3_logic": {
            "level": "not_available",
            "sufficient": False,
            "what_is_missing": [
                "details[].spec_oracle_injected（state 层已置位，未透出）",
                "details[].spec_oracle_verdict（六态行级判定，src 层已有，未透出）",
            ],
            "instrumentation_plan": [
                {
                    "file": "experiments/run_benchmark.py",
                    "anchor": "details 键集合（:1057-1061 spec_compile_rate / spec_expr_coverage 相邻）",
                    "change": (
                        '增 "spec_oracle_injected" 与 "spec_oracle_verdict" 两键'
                        "（后者才是可判定的六态字段：not_attempted/compiled_empty/"
                        "injected/injected_and_passed/injected_and_failed）"
                    ),
                },
                {
                    "file": "experiments/run_benchmark.py",
                    "anchor": "失败分支占位（:1226-1228）",
                    "change": '同步补 "spec_oracle_injected": None 与 "spec_oracle_verdict": None，保持键集合同构（该文件既有约定）',
                },
                {
                    "file": "experiments/run_benchmark.py",
                    "anchor": "_env_snapshot_keys（:2712-2771）",
                    "change": "登记 SPEC_ORACLE_EXEC_ENABLE——否则无法从工件证明逻辑通道是否开启",
                },
            ],
        },
        "C4_coverage": {
            "level": "auxiliary",
            "sufficient": True,
            "note": "coverage 已落盘；按定义不得单独作为检出证据。",
        },
    }


# --------------------------------------------------------------------------- #
# 报告
# --------------------------------------------------------------------------- #
def render_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = ["# 四通道重算（机器生成的数字小节）", ""]
    for arm, arm_sum in report["arms"].items():
        lines.append(f"## 臂 `{arm}`")
        lines.append("")
        c1 = arm_sum["channel_1_execution"]
        c2 = arm_sum["channel_2_hang"]
        merged = arm_sum["four_channel_merged"]
        cells = arm_sum["crosstab_c1_x_c2_inloop"]["cells"]
        lines += [
            f"- 终结点口径 `{arm_sum['endpoint']}`，n = {arm_sum['n_rows']}；"
            f"`EXECUTION_TIMEOUT` = {arm_sum['execution_timeout_seconds']:g}s",
            f"- **C1 执行通道**（measured）：正 {c1['positive']}，零 {c1['zero']}，"
            f"不可测 {c1['not_available']}；可测分母 {c1['rate_denominator_measured']}，"
            f"全分母 {c1['rate_denominator_all']}",
            f"- **C2 挂起通道**：M1 判定层 = `{c2['verification_level_m1_decision_layer']}`"
            f"（{c2['not_available_reason']}）",
            f"  - 环路内挂起嫌疑 {c2['inloop_hang_suspect']} 行；其中 fixed 腿绿 "
            f"{c2['inloop_positive_fixed_leg_green']} 行 → **挂起通道救回 "
            f"{arm_sum['n_rescued']} 行**：{arm_sum['rescued_by_hang_channel']}",
            f"- **C3 逻辑通道** = `{arm_sum['channel_3_logic']['verification_level']}`；"
            f"**C4 覆盖通道** = `{arm_sum['channel_4_coverage']['verification_level']}`（不进合并）",
            f"- **四通道合并**：正 {merged['positive']}（Δ vs C1 = {merged['delta_positive_rows_vs_c1']:+d} 行，"
            f"{merged['delta_pp_denominator_all']:+} pp），不可测 {merged['not_available']}",
            "",
            "### C1 × C2（环路内代理）2×2 交叉表",
            "",
            "| C1 \\ C2 | C2=1（挂起 ∧ fixed 绿） | C2=0 |",
            "|---|---|---|",
            f"| C1=1 | {cells['c1_1_c2_1']} | {cells['c1_1_c2_0']} |",
            f"| C1=0 | {cells['c1_0_c2_1']} | {cells['c1_0_c2_0']} |",
            f"| C1=不可测 | {cells['c1_na_c2_1']} | {cells['c1_na_c2_0']} |",
            "",
            f"- **『执行通道=0 但挂起通道=1』格子**（C1=0 且 C2=1）："
            f"{cells['c1_0_c2_1']}；**『执行通道不可测 但挂起通道=1』格子**：{cells['c1_na_c2_1']}",
            f"- over_red×挂起自述裁定：{arm_sum['over_red_hang_claim']['verdict']}",
            "",
        ]
    return "\n".join(lines)


def run_census(
    root: Path, skip_names: frozenset[str] = frozenset({"diagnostic_12task_prerepair.json"})
) -> dict[str, Any]:
    """**全库挂起普查**（只读）：扫描 root 下所有批次工件，统计挂起嫌疑行分布。

    目的：回答"挂起通道的收益是否外推"——把 C2 的环路内代理口径铺到**全部**
    存量批次上，看挂起现象是否只出现在某一基准。
    """
    entries: list[dict[str, Any]] = []
    total = hang_total = 0
    for batch_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        files: list[Path] = sorted(batch_dir.glob("benchmark_*.json"))
        files += [p for name in ("aitester.json", "plain_llm_df.json") if (p := batch_dir / name).is_file()]
        for batch_file in files:
            if batch_file.name in skip_names:
                continue
            batch = _load_batch(batch_file)
            exec_timeout = _exec_timeout(batch)
            log_hits = parse_log_hangs(batch_file.with_suffix(".log"))
            dataset = str(batch.get("dataset") or "?")
            for arm, payload in (batch.get("results") or {}).items():
                details = payload.get("details") or []
                if not details:
                    continue
                rows = build_rows(details, log_hits, exec_timeout)
                hang_ids = [r.task_id.split("__")[-1] for r in rows if r.c2_hang_evidence]
                total += len(rows)
                hang_total += len(hang_ids)
                entries.append(
                    {
                        "batch_dir": batch_dir.name,
                        "batch_file": batch_file.name,
                        "dataset": dataset,
                        "arm": arm,
                        "n_rows": len(rows),
                        "n_hang_suspect": len(hang_ids),
                        "hang_ids": hang_ids,
                    }
                )
    quix = [e for e in entries if "quixbugs" in str(e["dataset"]).lower() or "quixbugs" in str(e["batch_dir"]).lower()]
    other = [e for e in entries if e not in quix]
    return {
        "root": str(root),
        "total_rows": total,
        "total_hang_suspect": hang_total,
        "quixbugs_rows": sum(e["n_rows"] for e in quix),
        "quixbugs_hang_suspect": sum(e["n_hang_suspect"] for e in quix),
        "non_quixbugs_rows": sum(e["n_rows"] for e in other),
        "non_quixbugs_hang_suspect": sum(e["n_hang_suspect"] for e in other),
        "entries": entries,
    }


def render_census(census: dict[str, Any]) -> str:
    lines = ["# 全库挂起普查（环路内代理口径）", ""]
    lines.append(f"扫描根：`{census['root']}`")
    lines.append("")
    lines.append(f"| {'批次/臂':68} | {'行数':>5} | {'挂起嫌疑':>8} |")
    lines.append(f"|{'-' * 70}|{'-' * 7}|{'-' * 10}|")
    for e in census["entries"]:
        tag = f"{e['batch_dir']}/{e['arm']}"
        lines.append(f"| {tag:68} | {e['n_rows']:5d} | {e['n_hang_suspect']:8d} |")
    lines.append("")
    lines.append(
        f"- **合计** {census['total_rows']} 行，挂起嫌疑 {census['total_hang_suspect']} 行；"
        f"其中 QuixBugs 批次 {census['quixbugs_rows']} 行 / {census['quixbugs_hang_suspect']} 行，"
        f"**非 QuixBugs（合成）批次 {census['non_quixbugs_rows']} 行 / {census['non_quixbugs_hang_suspect']} 行**"
    )
    lines.append("")
    if census["non_quixbugs_hang_suspect"] == 0 and census["quixbugs_hang_suspect"] > 0:
        lines.append("⇒ **挂起现象为 QuixBugs 特有，合成基准 0 例**；挂起通道的收益**不可外推**到合成集。")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="四通道检出协议零 LLM 存量重算（只读）")
    ap.add_argument("--batch-dir", default=DEFAULT_BATCH_DIR, help=f"批次目录（默认 {DEFAULT_BATCH_DIR}）")
    ap.add_argument("--arms", nargs="+", default=list(DEFAULT_ARMS), help="臂名（对应 <arm>.json）")
    ap.add_argument("--endpoint", choices=("gold_only", "all"), default="gold_only", help="终结点口径")
    ap.add_argument(
        "--census",
        nargs="?",
        const="experiments/results/e6_a1_batches",
        default=None,
        help="全库挂起普查模式：扫描该根目录下全部批次工件（默认 e6_a1_batches）",
    )
    ap.add_argument("--json-out", default=None, help="把完整报告写为 JSON（建议落 review_2026/E3_*）")
    ap.add_argument("--md-out", default=None, help="把数字小节写为 Markdown")
    args = ap.parse_args(argv)

    if args.census:
        root = Path(args.census)
        if not root.is_absolute():
            root = PROJECT_ROOT / root
        census = run_census(root)
        print(render_census(census))
        if args.json_out:
            out = Path(args.json_out)
            if not out.is_absolute():
                out = PROJECT_ROOT / out
            out.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(out, census, indent=2, mode=0o644)
            print(f"[four_channel] 普查 JSON → {out}")
        return 0

    batch_dir = PROJECT_ROOT / args.batch_dir if not Path(args.batch_dir).is_absolute() else Path(args.batch_dir)
    report: dict[str, Any] = {
        "batch_dir": str(batch_dir),
        "endpoint_default": args.endpoint,
        "arms": {},
        "data_sufficiency": data_sufficiency(),
    }

    for arm in args.arms:
        batch_file, results_key = resolve_batch_file(batch_dir, arm)
        batch = _load_batch(batch_file)
        details = (batch.get("results") or {}).get(results_key, {}).get("details") or []
        exec_timeout = _exec_timeout(batch)
        # 环路内超时日志：优先同名 .log；多臂一文件布局下回退到与批次文件同名的 .log。
        log_path = batch_dir / f"{arm}.log"
        if not log_path.is_file():
            log_path = batch_file.with_suffix(".log")
        log_hits = parse_log_hangs(log_path)
        rows = build_rows(details, log_hits, exec_timeout)
        report["arms"][arm] = summarize_arm(rows, args.endpoint, exec_timeout)
        report["arms"][arm]["source_file"] = str(batch_file.relative_to(PROJECT_ROOT))
        report["arms"][arm]["log_file"] = str(log_path.relative_to(PROJECT_ROOT)) if log_path.is_file() else None
        report["arms"][arm]["log_hang_hits"] = log_hits
        report["arms"][arm]["rows"] = [
            {
                "task_id": r.task_id,
                "program": r.program,
                "is_gold_program": r.is_gold_program,
                "c1_execution": r.c1_execution,
                "c2_inloop": r.c2_inloop,
                "c2_m1": r.c2_m1,
                "c2_hang_evidence": r.c2_hang_evidence,
                "fixed_leg_green_proxy": r.fixed_leg_green_proxy,
                "c3_logic": r.c3_logic,
                "c4_coverage_final": r.c4_coverage_final,
                "c4_coverage_max": r.c4_coverage_max,
                "gate_verdict": r.gate_verdict,
                "stop_reason": r.stop_reason,
                "trace_max_elapsed": r.trace_max_elapsed,
                "trace_iters_at_ceiling": r.trace_iters_at_ceiling,
                "log_timeout_hits": r.log_timeout_hits,
                "detection_four_channel": r.detection_four_channel,
            }
            for r in rows
        ]

    md = render_markdown(report)
    sys.stdout.write(md + "\n")
    sys.stdout.write("数据充分性：\n")
    for ch, info in report["data_sufficiency"].items():
        sys.stdout.write(f"  {ch}: level={info['level']} sufficient={info['sufficient']}\n")
    sys.stdout.write(
        "\n⚠️  C2（挂起通道）在 M1 判定层 = not_available：存量工件未落盘 rc_buggy/rc_fixed。\n"
        "    上表 'inloop' 列是**代理口径**，见 --json-out 的 data_sufficiency.C2_hang.instrumentation_plan。\n"
    )

    if args.json_out:
        out = PROJECT_ROOT / args.json_out if not Path(args.json_out).is_absolute() else Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
        print(f"[four_channel] JSON 报告 → {out}")
    if args.md_out:
        out = PROJECT_ROOT / args.md_out if not Path(args.md_out).is_absolute() else Path(args.md_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(md, encoding="utf-8")
        print(f"[four_channel] Markdown → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
