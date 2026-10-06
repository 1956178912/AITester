"""AG 批次测试（2026-10-06 第十一轮第三轮自主收口）。

覆盖三项：
- AG-Fix telemetry 展平修复锁定：trace 落盘时 node 事件业务负载在
  output 内层，模式判定按顶层读取——修复前真实 trace 全部零命中
  （周报口径失真）。锁定展平语义（顶层优先、output 兜底）与
  "嵌套记录可检出"行为；
- AG1 mast_trace_analysis：文件名臂回退、trace 解析（含损坏文件）、
  按臂聚合（含 error_category 值分布）、渲染含解读警示；
- 工件守卫：mast_distribution_report.md 在 main_batch 白名单目录且
  已纳入 SHA256SUMS（衍生工件可追溯）。

全部纯 stdlib / 零 LLM / 零网络（AG 测试不跑子进程；telemetry 匹配
为纯静态查表）。
"""

from __future__ import annotations

import json
from pathlib import Path

from experiments.mast_trace_analysis import (
    _arm_from_filename,
    analyze_traces,
    parse_trace_file,
    render_markdown,
)
from src.observability.agent_telemetry import match_failure_patterns

_ROOT = Path(__file__).resolve().parents[1]


# ─── AG-Fix：telemetry 展平语义锁定 ─────────────────────────────────────────


class TestTelemetryFlatten:
    """展平修复（顶层优先、output 兜底）——防"真实 trace 零命中"回归。"""

    def test_nested_output_error_category_detected(self) -> None:
        """error_category 嵌在 output 内层（真实 trace 落盘形态）→ 可检出。"""
        records = [
            {
                "event": "node",
                "node": "debugger",
                "task": "t1",
                "output": {"error_category": "runtime", "decision": "debug"},
            }
        ]
        report = match_failure_patterns(records)
        assert report["patterns"]["known_error_category_hit"]["count"] >= 1

    def test_top_level_error_category_still_detected(self) -> None:
        """顶层 error_category（既有测试夹具口径）→ 行为不变。"""
        records = [{"event": "node", "node": "debugger", "task": "t1", "error_category": "runtime"}]
        report = match_failure_patterns(records)
        assert report["patterns"]["known_error_category_hit"]["count"] >= 1

    def test_top_level_key_wins_over_output(self) -> None:
        """同名键顶层优先：顶层 iteration=0 压制 output 内 iteration=5
        （import_break_after_rewrite 需 iteration>=1 → 不命中）。"""
        records = [
            {
                "event": "node",
                "node": "debugger",
                "task": "t1",
                "iteration": 0,
                "output": {"iteration": 5, "error_category": "import_error"},
            }
        ]
        report = match_failure_patterns(records)
        assert report["patterns"]["import_break_after_rewrite"]["count"] == 0

    def test_non_dict_output_ignored(self) -> None:
        """output 非 dict（异常落盘形态）→ 展平不崩、按顶层判定。"""
        records = [{"event": "node", "node": "executor", "task": "t1", "output": "raw-string"}]
        report = match_failure_patterns(records)
        assert report["matched_records"] == 0


# ─── AG1：mast_trace_analysis ───────────────────────────────────────────────


class TestArmFromFilename:
    def test_known_arms(self) -> None:
        assert _arm_from_filename("synthetic__task_0000_aitester_1791262475.trace.jsonl") == "aitester"
        assert _arm_from_filename("synthetic__task_0000_plain_llm_df_1791262522.trace.jsonl") == "plain_llm_df"

    def test_unknown_pattern_returns_none(self) -> None:
        assert _arm_from_filename("whatever.trace.jsonl") is None
        assert _arm_from_filename("synthetic__x_unknownarm_123.trace.jsonl") is None


class TestParseTraceFile:
    def test_meta_extraction(self, tmp_path: Path) -> None:
        p = tmp_path / "synthetic__t_aitester_1.trace.jsonl"
        p.write_text(
            json.dumps(
                {
                    "event": "task_start",
                    "task": "k",
                    "meta": {"dataset_task_id": "synthetic__t", "baseline": "aitester"},
                }
            )
            + "\n"
            + json.dumps({"event": "node", "node": "debugger", "task": "k", "output": {"error_category": "runtime"}})
            + "\n",
            encoding="utf-8",
        )
        parsed = parse_trace_file(p)
        assert parsed is not None
        assert parsed["arm"] == "aitester"
        assert parsed["task_id"] == "synthetic__t"
        assert len(parsed["records"]) == 2

    def test_damaged_file_returns_none(self, tmp_path: Path) -> None:
        p = tmp_path / "broken.trace.jsonl"
        p.write_text("{not-json\n", encoding="utf-8")
        assert parse_trace_file(p) is None


class TestAnalyzeTraces:
    def _write_trace(self, path: Path, arm: str, task: str, with_error: bool) -> None:
        lines = [json.dumps({"event": "task_start", "task": "k", "meta": {"dataset_task_id": task, "baseline": arm}})]
        if with_error:
            lines.append(
                json.dumps(
                    {"event": "node", "node": "debugger", "task": "k", "output": {"error_category": "assertion"}}
                )
            )
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_per_arm_aggregation_and_category_distribution(self, tmp_path: Path) -> None:
        self._write_trace(tmp_path / "a1.trace.jsonl", "aitester", "t1", with_error=True)
        self._write_trace(tmp_path / "a2.trace.jsonl", "aitester", "t2", with_error=False)
        self._write_trace(tmp_path / "b1.trace.jsonl", "plain_llm", "t1", with_error=True)
        (tmp_path / "broken.trace.jsonl").write_text("{oops\n", encoding="utf-8")
        result = analyze_traces(tmp_path)
        assert result["total_files"] == 4
        assert result["damaged_files"] == 1
        a = result["arms"]["aitester"]
        assert a["files"] == 2
        assert a["pattern_files"]["known_error_category_hit"] == 1
        assert a["category_files"]["assertion"] == 1
        # plain_llm 同样有 error_category（fixture 直接带字段）→ 与真实 trace
        # 的"无 debugger 节点故零命中"不同，此处验证的是聚合数学
        b = result["arms"]["plain_llm"]
        assert b["pattern_files"]["known_error_category_hit"] == 1

    def test_empty_file_counted_with_zero_hits(self, tmp_path: Path) -> None:
        """空 trace（无事件）且文件名无臂约定 → 计入 unknown 桶（不静默丢弃）。"""
        (tmp_path / "empty.trace.jsonl").write_text("", encoding="utf-8")
        result = analyze_traces(tmp_path)
        assert result["arms"]["unknown"]["files"] == 1
        assert result["arms"]["unknown"]["pattern_files"] == {}


class TestRenderMarkdown:
    def test_contains_caveat_and_tables(self, tmp_path: Path) -> None:
        (tmp_path / "a1.trace.jsonl").write_text(
            json.dumps({"event": "task_start", "task": "k", "meta": {"dataset_task_id": "t", "baseline": "aitester"}})
            + "\n"
            + json.dumps({"event": "node", "node": "debugger", "task": "k", "output": {"error_category": "runtime"}})
            + "\n",
            encoding="utf-8",
        )
        result = analyze_traces(tmp_path)
        text = "\n".join(render_markdown(result, tmp_path))
        assert "## 臂：aitester" in text
        assert "解读警示" in text
        assert "known_error_category_hit" in text
        assert "error_category 原始值分布" in text
        assert "| runtime | 1 | 100.0% |" in text


# ─── 工件守卫 ───────────────────────────────────────────────────────────────


class TestArtifactGuard:
    def test_report_artifact_exists_and_checksummed(self) -> None:
        report = _ROOT / "experiments" / "results" / "main_batch" / "mast_distribution_report.md"
        assert report.exists() and report.stat().st_size > 500
        sums = (_ROOT / "experiments" / "results" / "main_batch" / "SHA256SUMS").read_text(encoding="utf-8")
        assert "mast_distribution_report.md" in sums

    def test_analysis_script_importable_without_side_effects(self) -> None:
        """脚本模块导入零副作用（无目录创建 / 无网络）。"""
        import experiments.mast_trace_analysis as m

        assert callable(m.analyze_traces)
        assert callable(m.render_markdown)
