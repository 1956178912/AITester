"""
experiments/analyze_failures.py 单元测试（5.3 失败根因分类 + 案例知识库）。

覆盖：
- root_cause_classification 三大根因归类（llm_capability / dependency / framework）
- failure_knowledge_base 结构化案例选取（按 error_category 多样性）
- generate_report 新增章节渲染（"失败根因分类" + "失败案例知识库"）
- CLI --knowledge-base 选项默认路径与显式路径
"""

from __future__ import annotations

import json

import pytest

from experiments.analyze_failures import (
    failure_knowledge_base,
    generate_report,
    root_cause_classification,
)


class TestRootCauseClassification:
    """5.3 失败根因分类：三大根因归类（保守启发式）"""

    def test_classify_all_three_causes(self):
        details = [
            {"task_id": "a", "passed": False, "error_category": "llm_format_error", "diagnosis": "JSON parse failed"},
            {"task_id": "b", "passed": False, "error_category": "import_error", "diagnosis": "ModuleNotFoundError"},
            {"task_id": "c", "passed": False, "error_category": "patch_validation_failed", "diagnosis": ""},
            {"task_id": "d", "passed": True, "error_category": "", "diagnosis": ""},
        ]
        rc = root_cause_classification(details)
        assert rc["total_failed"] == 3
        assert rc["root_causes"] == {"llm_capability": 1, "dependency": 1, "framework": 1}
        assert rc["distribution"]["llm_capability"] == pytest.approx(1 / 3, abs=1e-6)
        assert "a" in rc["representative_cases"]["llm_capability"]
        assert "b" in rc["representative_cases"]["dependency"]
        assert "c" in rc["representative_cases"]["framework"]

    def test_no_failed_tasks_returns_zero(self):
        rc = root_cause_classification([{"task_id": "x", "passed": True}])
        assert rc["total_failed"] == 0
        assert rc["root_causes"] == {"llm_capability": 0, "dependency": 0, "framework": 0}
        assert rc["distribution"]["llm_capability"] == 0.0

    def test_unknown_category_defaults_to_llm_capability(self):
        """未命中任何规则的失败任务归 LLM 能力边界（保守兜底）。"""
        rc = root_cause_classification([{"task_id": "z", "passed": False, "error_category": "weird", "diagnosis": ""}])
        assert rc["root_causes"]["llm_capability"] == 1
        assert "z" in rc["representative_cases"]["llm_capability"]

    def test_diagnosis_keywords_match_dependency(self):
        """diagnosis 文本含 'pip' / 'venv' 关键词时归 dependency（即使 error_category 为空）。"""
        rc = root_cause_classification(
            [{"task_id": "p", "passed": False, "error_category": "", "diagnosis": "pip install failed: venv"}]
        )
        assert rc["root_causes"]["dependency"] == 1


class TestFailureKnowledgeBase:
    """5.3 失败案例知识库：结构化案例选取"""

    def test_kb_by_category_diversity(self):
        """按 error_category 多样性优先选取（每类取前 2 个）。"""
        details = [
            {"task_id": "a", "passed": False, "error_category": "llm_format_error", "diagnosis": "x"},
            {"task_id": "b", "passed": False, "error_category": "llm_format_error", "diagnosis": "y"},
            {"task_id": "c", "passed": False, "error_category": "llm_format_error", "diagnosis": "z"},
            {"task_id": "d", "passed": False, "error_category": "import_error", "diagnosis": "w"},
        ]
        kb = failure_knowledge_base(details, top_n=10)
        cats = [k["error_category"] for k in kb]
        # 前 2 个 llm_format_error + 1 个 import_error
        assert cats.count("llm_format_error") == 2
        assert cats.count("import_error") == 1
        assert len(kb) == 3

    def test_kb_respects_top_n(self):
        details = [
            {"task_id": f"t{i}", "passed": False, "error_category": f"cat_{i % 3}", "diagnosis": ""} for i in range(20)
        ]
        kb = failure_knowledge_base(details, top_n=5)
        assert len(kb) == 5

    def test_kb_empty_when_no_failures(self):
        kb = failure_knowledge_base([{"task_id": "x", "passed": True}])
        assert kb == []

    def test_kb_case_structure(self):
        """每条案例含 task_id / root_cause / error_category / reproducible_steps / suggested_fix。"""
        details = [{"task_id": "k", "passed": False, "error_category": "import_error", "diagnosis": "mod missing"}]
        kb = failure_knowledge_base(details, top_n=1)
        case = kb[0]
        assert case["task_id"] == "k"
        assert case["root_cause"] == "dependency"
        assert "复现" in case["reproducible_steps"]
        assert case["suggested_fix"]["suggestion"]


class TestGenerateReportNewSections:
    """5.3 generate_report 新增章节渲染"""

    def test_report_contains_root_cause_section(self, tmp_path):
        details = [
            {
                "task_id": "a",
                "passed": False,
                "error_category": "llm_format_error",
                "diagnosis": "json",
                "baseline": "aitester",
            },
            {
                "task_id": "b",
                "passed": False,
                "error_category": "import_error",
                "diagnosis": "mod",
                "baseline": "aitester",
            },
            {"task_id": "c", "passed": True, "error_category": "", "diagnosis": "", "baseline": "aitester"},
        ]
        out = tmp_path / "report.md"
        generate_report(details, str(out))
        content = out.read_text(encoding="utf-8")
        assert "失败根因分类（5.3）" in content
        assert "llm_capability" in content
        assert "dependency" in content

    def test_report_contains_kb_section(self, tmp_path):
        details = [
            {
                "task_id": "k1",
                "passed": False,
                "error_category": "llm_format_error",
                "diagnosis": "x",
                "baseline": "aitester",
            },
        ]
        out = tmp_path / "report.md"
        generate_report(details, str(out))
        content = out.read_text(encoding="utf-8")
        assert "失败案例知识库（5.3，结构化）" in content
        assert "k1" in content

    def test_report_no_kb_when_no_failures(self, tmp_path):
        details = [{"task_id": "ok", "passed": True, "baseline": "aitester"}]
        out = tmp_path / "report.md"
        generate_report(details, str(out))
        content = out.read_text(encoding="utf-8")
        assert "无失败任务，知识库为空" in content


class TestCliKnowledgeBaseOption:
    """5.3 CLI --knowledge-base 选项"""

    def test_cli_default_kb_path(self, tmp_path, monkeypatch):
        """未传 --knowledge-base 时默认写入 <results-dir>/failure_knowledge_base.json。"""
        from experiments import analyze_failures as af

        results_dir = tmp_path / "results"
        results_dir.mkdir()
        (results_dir / "benchmark_x.json").write_text(
            json.dumps(
                {
                    "results": {
                        "aitester": {
                            "details": [
                                {
                                    "task_id": "k",
                                    "passed": False,
                                    "error_category": "llm_format_error",
                                    "diagnosis": "x",
                                    "baseline": "aitester",
                                },
                            ]
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        captured: dict[str, str] = {}

        def fake_generate_report(tasks, output_path):
            captured["report"] = output_path

        monkeypatch.setattr(af, "generate_report", fake_generate_report)

        # 直接调用 cli（绕过 click 命令解析，用 CliRunner 模拟）
        from click.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(af.cli, ["-r", str(results_dir), "-o", str(tmp_path / "r.md")])
        assert result.exit_code == 0, result.output
        default_kb = results_dir / "failure_knowledge_base.json"
        assert default_kb.exists()
        cases = json.loads(default_kb.read_text(encoding="utf-8"))
        assert len(cases) == 1 and cases[0]["task_id"] == "k"

    def test_cli_explicit_kb_path(self, tmp_path, monkeypatch):
        """显式 --knowledge-base 时写入指定路径。"""
        from click.testing import CliRunner

        from experiments import analyze_failures as af

        results_dir = tmp_path / "results"
        results_dir.mkdir()
        (results_dir / "benchmark_x.json").write_text(
            json.dumps(
                {
                    "results": {
                        "aitester": {
                            "details": [
                                {
                                    "task_id": "k",
                                    "passed": False,
                                    "error_category": "import_error",
                                    "diagnosis": "x",
                                    "baseline": "aitester",
                                },
                            ]
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

        def fake_generate_report(tasks, output_path):
            pass

        monkeypatch.setattr(af, "generate_report", fake_generate_report)
        runner = CliRunner()
        explicit_kb = tmp_path / "my_kb.json"
        result = runner.invoke(af.cli, ["-r", str(results_dir), "-o", str(tmp_path / "r.md"), "-k", str(explicit_kb)])
        assert result.exit_code == 0, result.output
        assert explicit_kb.exists()
        cases = json.loads(explicit_kb.read_text(encoding="utf-8"))
        assert len(cases) == 1
