"""KB 覆盖率收口：压缩反馈 / 补丁后处理 / spec-first 的降级与失败分支。

动机：这三个模块的低覆盖行都是**观测/后处理层的保守降级**——探针快照帧损坏、
FL 候选行为非法、traceback 定位异常、压缩构建异常兜底、导入回填的"不可判定"
出口、契约别名回填的解析失败、签名/docstring 提取的语法失败。它们不影响默认
路径，但一旦触发就决定"安全跳过还是把坏数据注入 prompt / 补丁"。

纪律：零 LLM / 零网络；全部 monkeypatch 注入失败路径；纯字符串与 dict 输入。
"""

from __future__ import annotations

import pytest

from src.tools import feedback_compression as fc
from src.tools import patch_postprocess as pp
from src.tools import spec_first as sf


@pytest.mark.unit
class TestFeedbackCompressionSnapshotDegradation:
    """运行时探针 / 谱系候选行的输入形态校验（坏数据 → 安全返回空）。"""

    def test_probe_throw_line_rejects_bad_shapes(self):
        assert fc._probe_throw_line({"runtime_probe_snapshot": ["不是 dict"]}) is None
        assert fc._probe_throw_line({"runtime_probe_snapshot": {"frames": []}}) is None
        assert fc._probe_throw_line({"runtime_probe_snapshot": {"frames": ["不是帧"]}}) is None
        assert fc._probe_throw_line({"runtime_probe_snapshot": {"frames": [{"line": 0}]}}) is None
        assert fc._probe_throw_line({"runtime_probe_snapshot": {"frames": [{"line": 4}]}}) == 4

    def test_fl_candidate_lines_filters_invalid_entries(self):
        state = {"fl_spectral_focus": {"top_k": [{"line": 0}, {"line": "坏值"}, {"line": 7}, "不是 dict"]}}
        assert fc._fl_candidate_lines(state) == [7]

    def test_fl_candidate_lines_bad_top_k_type_returns_empty(self):
        assert fc._fl_candidate_lines({"fl_spectral_focus": {"top_k": "不是 list"}}) == []

    def test_traceback_locator_exception_degrades_to_none(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            "src.agents.error_classifier.ErrorClassifier.extract_error_context",
            lambda self, output, cases: (_ for _ in ()).throw(RuntimeError("分类器损坏（模拟）")),
        )
        state = {"test_output": "AssertionError", "failed_cases": [{"name": "t", "error": "e"}]}
        assert fc._traceback_candidate_line(state) is None  # type: ignore[arg-type]

    def test_build_compressed_feedback_exception_degrades_to_none(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            fc,
            "_build_compressed_feedback_inner",
            lambda state: (_ for _ in ()).throw(RuntimeError("压缩构建损坏（模拟）")),
        )
        assert fc.build_compressed_feedback({}) is None  # type: ignore[arg-type]


@pytest.mark.unit
class TestImportRepairGuards:
    """P2 导入断裂回填的四条"不可判定即跳过"出口。"""

    def test_no_original_imports_returns_none(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("IMPORT_REPAIR_ENABLE", "true")
        original = "def f():\n    return 1\n"
        patch = "import os\n\ndef f():\n    return 2\n"
        assert pp.repair_missing_imports(original, patch) is None

    def test_patch_without_top_import_returns_none(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("IMPORT_REPAIR_ENABLE", "true")
        original = "import os\n\ndef f():\n    return os.sep\n"
        patch = "def f():\n    return os.sep\n"
        assert pp.repair_missing_imports(original, patch) is None

    def test_patch_keeps_all_imports_returns_none(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("IMPORT_REPAIR_ENABLE", "true")
        original = "import os\n\ndef f():\n    return os.sep\n"
        patch = "import os\n\ndef f():\n    return os.curdir\n"
        assert pp.repair_missing_imports(original, patch) is None

    def test_unused_import_not_restored(self, monkeypatch: pytest.MonkeyPatch):
        """缺失 import 的模块名在正文中已无引用 → 不回填（允许废弃依赖消失）。"""
        monkeypatch.setenv("IMPORT_REPAIR_ENABLE", "true")
        original = "import json\nimport os\n\ndef f():\n    return os.sep\n"
        patch = "import os\n\ndef f():\n    return os.curdir\n"
        assert pp.repair_missing_imports(original, patch) is None

    def test_restores_missing_import_when_symbol_still_used(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("IMPORT_REPAIR_ENABLE", "true")
        original = "import json\n\ndef f():\n    return json.dumps({})\n"
        # 补丁本身是"完整文件形态"（带顶层 import，但漏了 json）
        patch = "import os\n\ndef f():\n    return json.dumps({'a': 1}) + os.sep\n"
        repaired = pp.repair_missing_imports(original, patch)
        assert repaired is not None
        assert repaired.startswith("import json")
        assert "def f():" in repaired


@pytest.mark.unit
class TestContractAliasGuards:
    """P3 契约符号别名回填的输入校验与符号收集口径。"""

    def test_empty_patch_returns_none(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("CONTRACT_ALIAS_ENABLE", "true")
        assert pp.repair_contract_aliases("X = 1\n", "") is None

    def test_unparsable_patch_returns_none(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("CONTRACT_ALIAS_ENABLE", "true")
        assert pp.repair_contract_aliases("X = 1\n", "def broken(:\n") is None

    def test_collects_assign_and_annotated_assign_symbols(self, monkeypatch: pytest.MonkeyPatch):
        """模块级赋值 / 带注解赋值均纳入契约符号集合（重命名检测的输入口径）。"""
        monkeypatch.setenv("CONTRACT_ALIAS_ENABLE", "true")
        original = "X = 1\nY: int = 2\n\ndef f():\n    return X + Y\n"
        patch = "def f():\n    return X + Y\n"
        # 无重命名嫌疑符号 → 不自动回填（None 表示交上游契约守卫处理）
        assert pp.repair_contract_aliases(original, patch) is None


@pytest.mark.unit
class TestSpecFirstExtraction:
    """spec-first 模式的签名行 / docstring 提取（语法失败 → 空串）。"""

    def test_invalid_source_returns_empty_signature(self):
        assert sf._extract_signature_line("def broken(:\n", "f") == ""

    def test_empty_source_returns_empty_docstring(self):
        assert sf._docstring_of("", "f") == ""

    def test_signature_of_top_level_function_keeps_annotations(self):
        source = "def f(a: int, b: str = 'x') -> int:\n    return a\n"
        assert sf._extract_signature_line(source, "f") == "def f(a: int, b: str='x') -> int"

    def test_signature_of_class_method(self):
        source = "class C:\n    def m(self, x: int) -> None:\n        return None\n"
        assert sf._extract_signature_line(source, "m") == "def m(self, x: int) -> None"

    def test_docstring_of_class_method(self):
        source = 'class C:\n    def m(self):\n        """方法契约说明。"""\n        return None\n'
        assert sf._docstring_of(source, "m") == "方法契约说明。"
