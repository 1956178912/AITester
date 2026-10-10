"""
11. 基线数字漂移守卫（scripts/gates/check_baseline_numbers.py）单元测试。

验证改进清单 #11（P0）：README / README.en 的"当前基线"块硬编码数字被
守卫捕获，历史叙事章节与指向 BASELINE.yaml 的合规写法不被误报。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from scripts.gates.check_baseline_numbers import _extract_section, check_baseline_numbers


class TestExtractSection:
    """测试 _extract_section 章节边界提取。"""

    def test_extracts_up_to_next_h2(self):
        text = "前导\n## 测试状态\n内容 A\n内容 B\n## 开发工具\n内容 C\n"
        section = _extract_section(text, __import__("re").compile(r"^##\s+测试状态\s*$"))
        assert "内容 A" in section
        assert "内容 B" in section
        assert "内容 C" not in section
        assert "开发工具" not in section

    def test_missing_heading_returns_empty(self):
        text = "## 其他章节\n内容\n"
        assert _extract_section(text, __import__("re").compile(r"^##\s+测试状态\s*$")) == ""


class TestBaselineNumbers:
    """测试当前基线块数字漂移检测。"""

    def test_current_repo_passes(self):
        """当前仓库 README / README.en 当前基线块应零硬编码（守卫自检）。"""
        failures = check_baseline_numbers()
        assert failures == [], failures

    def test_detects_passed_count(self, tmp_path, monkeypatch):
        """模拟残留 `1234 passed` 硬编码应被捕获。"""
        readme = tmp_path / "README.md"
        readme.write_text(
            "## 测试状态\n\n全量 1234 passed / 行覆盖 89%\n\n## 开发工具\n\nok\n",
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)
        import scripts.gates.check_baseline_numbers as mod

        mod._TARGETS = [("README.md", r"^##\s+测试状态\s*$")]
        failures = mod.check_baseline_numbers()
        assert any("passed" in f for f in failures)
        assert any("行覆盖" in f for f in failures)

    def test_detects_collected_count(self, tmp_path, monkeypatch):
        readme = tmp_path / "README.md"
        readme.write_text("## 测试状态\n\n全量 999 collected（历史数字）\n\n## 开发工具\n\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        import scripts.gates.check_baseline_numbers as mod

        mod._TARGETS = [("README.md", r"^##\s+测试状态\s*$")]
        failures = mod.check_baseline_numbers()
        assert any("collected" in f for f in failures)

    def test_historical_section_excluded(self, tmp_path, monkeypatch):
        """ "迭代优化记录" 等历史叙事章节不在检查范围。"""
        readme = tmp_path / "README.md"
        readme.write_text(
            "## 测试状态\n\n当前数值见 BASELINE.yaml tests 节。\n\n## 迭代优化记录\n\n"
            "全量 1937 passed / 0 failed（历史快照，允许保留）\n",
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)
        import scripts.gates.check_baseline_numbers as mod

        mod._TARGETS = [("README.md", r"^##\s+测试状态\s*$")]
        assert mod.check_baseline_numbers() == []

    def test_compliant_pointer_passes(self, tmp_path, monkeypatch):
        """指向 BASELINE.yaml 的合规写法不被误报。"""
        readme = tmp_path / "README.md"
        readme.write_text(
            "## 测试状态\n\n| 指标 | 状态 |\n|------|------|\n| 单元测试 | 全量通过，数值见 BASELINE.yaml tests 节 |\n",
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)
        import scripts.gates.check_baseline_numbers as mod

        mod._TARGETS = [("README.md", r"^##\s+测试状态\s*$")]
        assert mod.check_baseline_numbers() == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
