"""修复引擎批次 VII（2026-10-07）：repair=0 围栏伪影修复测试锁（ADR-0021）。

锁定四组行为：
1. normalize_patch_text（写盘口径函数化）：围栏 / python 前缀剥离、
   纯代码与 unified diff 幂等、python_x 标识符不误剥（负向后瞻）；
2. _target_code_after_patch 测量口径修复：带残留前缀的整文件补丁
   清理后可解析（repair_rate 伪影根因封堵）；
3. apply_patch_to_code 重构后行为不变（带围栏补丁应用成功——历史锁）；
4. repair_replay 存量重放：correct / wrong_patch / skipped 三态判定、
   汇总数学、报告关键行。

背景（ADR-0021）：E2 存量 274/274 带补丁行 patch 字段以 "python\n"
围栏残留开头，M1 独立裁决在未清理文本上执行 gold 测试 100% 失败 →
"repair 全线 0"系测量伪影；修正重放 266 可重放行 correct=103
（38.7%），E2 双种子批稳定 44-48%。
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments._m1_metrics import _target_code_after_patch
from experiments.repair_replay import build_report, replay_batch, replay_row
from src.tools.patch_applier import apply_patch_to_code, normalize_patch_text


class TestNormalizePatchText:
    def test_strips_markdown_fence(self) -> None:
        assert normalize_patch_text("```python\nx = 1\n```") == "x = 1"

    def test_strips_bare_python_prefix_newline(self) -> None:
        # 实测残留形态（E2 存量 274/274）：围栏剥离后 "python\n" 标签残留
        assert normalize_patch_text("python\n_STOCK = {}\n") == "_STOCK = {}"

    def test_strips_python_colon_prefix(self) -> None:
        assert normalize_patch_text("python:\nx = 1\n") == "x = 1"

    def test_plain_code_idempotent(self) -> None:
        # extract_code_block 既有口径：结果 .strip()（首尾空白剥除），
        # 尾换行丢失是写盘链路历史行为（apply 后补 "\n"），幂等指 f(f(x))==f(x)
        code = "def add(a, b):\n    return a + b\n"
        cleaned = normalize_patch_text(code)
        assert cleaned == "def add(a, b):\n    return a + b"
        assert normalize_patch_text(cleaned) == cleaned

    def test_unified_diff_untouched(self) -> None:
        diff = "diff --git a/m.py b/m.py\n--- a/m.py\n+++ b/m.py\n@@ -1 +1 @@\n-x\n+y\n"
        # 尾换行经 strip 剥除（extract_code_block 既有口径），diff 语义行不受影响
        assert normalize_patch_text(diff) == diff.rstrip("\n")

    def test_none_and_empty_return_empty(self) -> None:
        assert normalize_patch_text(None) == ""
        assert normalize_patch_text("") == ""

    def test_double_application_idempotent(self) -> None:
        raw = "```python\ndef f():\n    return 1\n```"
        once = normalize_patch_text(raw)
        assert normalize_patch_text(once) == once

    def test_python_identifier_prefix_not_stripped(self) -> None:
        # 负向后瞻锁：首行是 "python_x = 1" 这类合法标识符时不得剥出 "_x = 1"
        code = "python_path = 3\nother = 4\n"
        assert normalize_patch_text(code) == code.rstrip("\n")


class TestTargetCodeAfterPatch:
    def test_full_file_patch_with_residual_prefix_parses(self) -> None:
        # 伪影根因封堵：带 "python\n" 残留的整文件补丁，清理后必须可解析
        patched = _target_code_after_patch("old = 1\n", "python\ndef f():\n    return 42\n")
        assert patched.startswith("def f()")
        ast.parse(patched)  # 不抛 SyntaxError

    def test_clean_full_file_patch_unchanged(self) -> None:
        # 干净补丁仅尾空白差异（strip 既有口径），语义零变化
        code = "def f():\n    return 7\n"
        assert _target_code_after_patch("old = 1\n", code) == "def f():\n    return 7"

    def test_empty_patch_returns_original(self) -> None:
        assert _target_code_after_patch("x = 1\n", "") == "x = 1\n"


class TestApplyPatchToCodeRefactor:
    def test_fenced_patch_still_applies(self) -> None:
        # 历史行为锁：Step1/2 函数化为 normalize_patch_text 后带围栏补丁照常应用
        original = "def f():\n    return 0\n"
        new_code, ok = apply_patch_to_code(original, "```python\ndef f():\n    return 1\n```")
        assert ok is True
        assert "return 1" in new_code

    def test_python_prefix_patch_still_applies(self) -> None:
        original = "def f():\n    return 0\n"
        new_code, ok = apply_patch_to_code(original, "python\ndef f():\n    return 2\n")
        assert ok is True
        assert new_code.startswith("def f()")


class TestRepairReplay:
    @staticmethod
    def _make_row(patch: str, module: str, correct_code: str) -> dict:
        """构造重放行：gold 测试断言 add(1,2)==3（correct_code 满足）。"""
        return {
            "task_id": f"synthetic__{module}",
            "patch": patch,
            "patch_correct": 0,  # 历史伪影口径：未经清理执行 → 恒 0
            "task_metadata": {
                "source": "synthetic",
                "test_cases": f"from {module} import add\n\ndef test_add():\n    assert add(1, 2) == 3\n",
                "fixed": "",
            },
        }

    def test_correct_row_after_cleanup(self, tmp_path) -> None:
        row = self._make_row("python\ndef add(a, b):\n    return a + b\n", "replay_ok", "")
        verdict = replay_row(row, timeout=60)
        assert verdict["status"] == "correct"
        assert verdict["old_patch_correct"] == 0  # 原口径伪影 vs 修正口径 correct

    def test_wrong_patch_row(self, tmp_path) -> None:
        row = self._make_row("def add(a, b):\n    return a - b\n", "replay_bad", "")
        verdict = replay_row(row, timeout=60)
        assert verdict["status"] == "wrong_patch"

    def test_empty_patch_skipped(self) -> None:
        row = self._make_row("", "replay_skip", "")
        verdict = replay_row(row, timeout=60)
        assert verdict["status"] == "skipped_no_material"

    def test_diff_form_not_replayable(self) -> None:
        row = self._make_row("diff --git a/m.py b/m.py\n--- a/m.py\n+++ b/m.py\n", "replay_diff", "")
        verdict = replay_row(row, timeout=60)
        assert verdict["status"] == "not_replayable_diff"

    def test_batch_summary_and_report(self, tmp_path) -> None:
        details = [self._make_row("python\ndef add(a, b):\n    return a + b\n", f"mod_{i}", "") for i in range(3)] + [
            self._make_row("def add(a, b):\n    return 9\n", "mod_bad", ""),
            self._make_row("", "mod_skip", ""),
        ]
        batch = {
            "results": {
                "aitester": {
                    "details": details,
                }
            }
        }
        batch_path = tmp_path / "benchmark_synthetic_test.json"
        batch_path.write_text(json.dumps(batch), encoding="utf-8")
        summary = replay_batch(batch_path, "aitester", timeout=60)
        assert summary["replayed"] == 4
        assert summary["counts"]["correct"] == 3
        assert summary["counts"]["wrong_patch"] == 1
        assert summary["counts"]["skipped_no_material"] == 1
        assert summary["replay_repair_rate"] == 0.75
        assert summary["old_patch_correct_total"] == 0
        report = build_report(tmp_path, "aitester", timeout=60)
        assert "修正 repair_rate = 0.75" in report
        assert "原口径 correct = 0（伪影归零）" in report

    def test_main_writes_report_file(self, tmp_path, capsys) -> None:
        from experiments.repair_replay import main as replay_main

        batch = {
            "results": {"aitester": {"details": [self._make_row("def add(a, b):\n    return a + b\n", "main_mod", "")]}}
        }
        batch_path = tmp_path / "benchmark_synthetic_cli.json"
        batch_path.write_text(json.dumps(batch), encoding="utf-8")
        out_path = tmp_path / "report.md"
        rc = replay_main([str(tmp_path), "--arm", "aitester", "--out", str(out_path)])
        assert rc == 0
        assert out_path.exists()
        assert "ADR-0021" in out_path.read_text(encoding="utf-8")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
