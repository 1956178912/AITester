"""H1 载荷等价（GENERATOR_PAYLOAD）单元锁。

预注册：``docs/design/payload_equivalence_prereg.md`` §2.2（自变量操作化）、
§0 G0-b/G0-c（快照可审计）、§2.5 P-1（干预落地）。

本文件锁四件事：

1. **默认 full = 历史口径逐字节不变**（ADR-0003：新功能默认关）；
2. **df_parity**：prompt 只含被测代码 + ``module_name``/import 约束，
   plan JSON、RAG 参考、断言增强、变异反馈全部不进 prompt；
3. **structure**：保留 plan 骨架，只剥 ``test_cases[].expected_output``、
   ``logic_analysis.output_domain``、``logic_analysis.postconditions`` 三个
   oracle-来自-实现的锚点，其余字段与增强段不变；
4. **自变量可审计**：``GENERATOR_PAYLOAD`` 已入 ``_env_snapshot_keys``，
   且 CI 门禁的选择器覆盖该命名形态（否则干预测不出现在工件里）。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

CODE = "def initials(name):\n    return ''.join(p[0] for p in name.split()).upper()\n"

PLAN = {
    "function_name": "initials",
    "description": "取姓名首字母",
    "logic_analysis": {
        "input_domain": "非空字符串",
        "output_domain": "大写首字母串",
        "preconditions": ["name 非空"],
        "postconditions": ["返回大写"],
        "edge_cases": ["None 输入"],
    },
    "test_cases": [
        {
            "case_name": "normal_two_words",
            "input_args": {"name": "ada lovelace"},
            "expected_output": "AL",
            "category": "normal",
            "description": "两词姓名",
            "logic_coverage": "C1",
        }
    ],
}


def _mk() -> object:
    """构造 GeneratorAgent（__init__ 零 LLM / 零网络）。"""
    from src.agents.generator import GeneratorAgent

    return GeneratorAgent()


def _plan_from_query(query: str) -> dict:
    """从 prompt 里把 plan JSON 段解析回来（结构化断言，不用裸子串判真）。"""
    marker = "测试计划（JSON）：\n"
    assert query.startswith(marker), "full/structure 的 prompt 必须以 plan JSON 段开头"
    body, _, _ = query[len(marker) :].partition("\n\n目标代码")
    return json.loads(body)


class TestFullIsDefault:
    """默认值与显式 full 必须同一条路径（历史口径零变化）。"""

    def test_default_env_yields_full(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.agents.generator import generator_payload

        monkeypatch.delenv("GENERATOR_PAYLOAD", raising=False)
        assert generator_payload() == "full"

    def test_default_keeps_plan_and_oracle_anchors(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GENERATOR_PAYLOAD", raising=False)
        query = _mk()._build_query(PLAN, CODE, "mod_initials", None)
        plan = _plan_from_query(query)
        assert plan["test_cases"][0]["expected_output"] == "AL"
        assert plan["logic_analysis"]["output_domain"] == "大写首字母串"

    def test_explicit_full_is_byte_identical(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GENERATOR_PAYLOAD", raising=False)
        baseline = _mk()._build_query(PLAN, CODE, "mod_initials", None)
        monkeypatch.setenv("GENERATOR_PAYLOAD", "full")
        assert _mk()._build_query(PLAN, CODE, "mod_initials", None) == baseline


class TestDfParity:
    """df_parity：与 plain_llm_df 同载荷——只有代码 + import 约束。"""

    def test_prompt_is_code_and_import_constraint_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GENERATOR_PAYLOAD", "df_parity")
        query = _mk()._build_query(PLAN, CODE, "mod_initials", None)
        expected = (
            f"目标代码：\n```\n{CODE}\n```"
            "\n\n被测模块名：mod_initials"
            "\n\n【重要约束】import 语句必须使用以下模块名：`mod_initials`，"
            "即 `from mod_initials import ...`"
        )
        assert query == expected

    def test_enhancements_do_not_leak(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """RAG / 断言增强 / 变异反馈即使被传入也不得进入 df_parity prompt。"""
        monkeypatch.setenv("GENERATOR_PAYLOAD", "df_parity")
        monkeypatch.setenv("ASSERTION_AUGMENT_ENABLE", "true")
        query = _mk()._build_query(
            PLAN,
            CODE,
            "mod_initials",
            [{"test_code": "def test_x():\n    assert True"}],
            mutation_feedback={"survived_mutants": ["return_void"], "mutation_score": 0.2},
        )
        assert "测试计划" not in query
        assert "参考案例" not in query
        assert "断言增强" not in query
        assert "变异反馈" not in query
        assert "expected_output" not in query

    def test_empty_module_name_keeps_only_code(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GENERATOR_PAYLOAD", "df_parity")
        assert _mk()._build_query(PLAN, CODE, "", None) == f"目标代码：\n```\n{CODE}\n```"


class TestStructure:
    """structure：plan 骨架 + 其余增强段，剥三个 oracle-来自-实现锚点。"""

    def test_strips_three_anchors_keeps_skeleton(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GENERATOR_PAYLOAD", "structure")
        query = _mk()._build_query(PLAN, CODE, "mod_initials", None)
        plan = _plan_from_query(query)
        assert "expected_output" not in plan["test_cases"][0]
        assert "output_domain" not in plan["logic_analysis"]
        assert "postconditions" not in plan["logic_analysis"]
        # 骨架与其余 analysis 字段必须保留
        assert plan["function_name"] == "initials"
        assert plan["test_cases"][0]["case_name"] == "normal_two_words"
        assert plan["test_cases"][0]["input_args"] == {"name": "ada lovelace"}
        assert plan["test_cases"][0]["logic_coverage"] == "C1"
        assert plan["logic_analysis"]["input_domain"] == "非空字符串"
        assert plan["logic_analysis"]["edge_cases"] == ["None 输入"]

    def test_input_plan_not_mutated(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GENERATOR_PAYLOAD", "structure")
        before = json.dumps(PLAN, ensure_ascii=False, sort_keys=True)
        _mk()._build_query(PLAN, CODE, "mod_initials", None)
        assert json.dumps(PLAN, ensure_ascii=False, sort_keys=True) == before


class TestInvalidValue:
    """非法取值回退 full 并告警（与 ORACLE_CONTEXT_TIER 同口径）。"""

    def test_falls_back_to_full_and_warns(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        from src.agents.generator import generator_payload

        monkeypatch.setenv("GENERATOR_PAYLOAD", "no_such_level")
        with caplog.at_level("WARNING", logger="src.agents.generator"):
            assert generator_payload() == "full"
        assert any("GENERATOR_PAYLOAD" in rec.message for rec in caplog.records)


class TestEnvSnapshotContract:
    """G0-b / G0-c：自变量必须能从工件审计，且 CI 门禁必须覆盖该命名形态。"""

    def test_key_present_in_snapshot_list(self) -> None:
        text = (ROOT / "experiments" / "run_benchmark.py").read_text(encoding="utf-8")
        marker = "_env_snapshot_keys = ["
        start = text.index(marker)
        end = text.index("]", start)
        block = text[start:end]
        assert '"GENERATOR_PAYLOAD"' in block, "GENERATOR_PAYLOAD 必须登记进 _env_snapshot_keys"

    def test_gate_passes_with_new_selector(self) -> None:
        proc = subprocess.run(
            [sys.executable, "scripts/gates/check_env_snapshot_keys.py"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert proc.returncode == 0, f"快照键门禁应 exit 0\n{proc.stdout}\n{proc.stderr}"

    def test_selector_covers_payload_form(self) -> None:
        """选择器若退回只认 `_ENABLE$`，GENERATOR_PAYLOAD 就落在判据之外。"""
        import re

        text = (ROOT / "scripts" / "gates" / "check_env_snapshot_keys.py").read_text(encoding="utf-8")
        match = re.search(r"^DEFAULT_SELECT\s*=\s*r?[\"'](.+?)[\"']", text, re.M)
        assert match, "必须保留 DEFAULT_SELECT 常量以便臂级门禁解析"
        pattern = match.group(1)
        assert re.search(pattern, "GENERATOR_PAYLOAD"), f"选择器 {pattern!r} 未覆盖载荷开关"
        assert re.search(pattern, "ORACLE_CONTEXT_TIER"), f"选择器 {pattern!r} 未覆盖档位开关"
