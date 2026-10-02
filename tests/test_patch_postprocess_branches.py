"""tools/patch_postprocess 补丁卫生化 P1/P2/P3 分支补齐（2026-10-02 批次·六）。

锁定 patch_postprocess.py 零 LLM / 零网络的纯静态分支：
- detect_empty_patch 空壳判定（None / 纯空白 / 短代码 / 有效代码 / 开关关）
- _effective_code_chars markdown 围栏 / 注释 / 空行剔除
- repair_missing_imports 导入回填（开关 / 非完整文件 / 缺失 import 存活）
- repair_contract_aliases 契约别名回填（重命名嫌疑前缀 / 纯删除无嫌疑）
- sanitize_patch P1→P2→P3 流水线 + None 短路
- _import_module_names import 形式模块名提取
- postprocess_enabled_flags 开关状态
"""

from __future__ import annotations


class TestDetectEmptyPatchBranches:
    def test_none_patch_empty(self, monkeypatch):
        from src.tools.patch_postprocess import detect_empty_patch

        monkeypatch.delenv("EMPTY_PATCH_GUARD", raising=False)  # 默认 true
        assert detect_empty_patch(None) is True

    def test_whitespace_only_empty(self, monkeypatch):
        from src.tools.patch_postprocess import detect_empty_patch

        monkeypatch.delenv("EMPTY_PATCH_GUARD", raising=False)
        assert detect_empty_patch("   \n  ") is True

    def test_short_code_empty(self, monkeypatch):
        from src.tools.patch_postprocess import detect_empty_patch

        monkeypatch.delenv("EMPTY_PATCH_GUARD", raising=False)
        # "def f(): pass" 有效代码 < 20 字符 → 空壳
        assert detect_empty_patch("def f(): pass\n") is True

    def test_valid_code_not_empty(self, monkeypatch):
        from src.tools.patch_postprocess import detect_empty_patch

        monkeypatch.delenv("EMPTY_PATCH_GUARD", raising=False)
        # 有效代码 >= 20 字符
        assert detect_empty_patch("def f():\n    return x + 1  # fix\n") is False

    def test_guard_disabled_always_false(self, monkeypatch):
        from src.tools.patch_postprocess import detect_empty_patch

        monkeypatch.setenv("EMPTY_PATCH_GUARD", "false")
        assert detect_empty_patch("") is False
        assert detect_empty_patch(None) is False


class TestEffectiveCodeCharsBranches:
    def test_empty_text_zero(self):
        from src.tools.patch_postprocess import _effective_code_chars

        assert _effective_code_chars("") == 0
        assert _effective_code_chars(None) == 0

    def test_markdown_fence_stripped(self):
        from src.tools.patch_postprocess import _effective_code_chars

        out = _effective_code_chars("```python\ndef f():\n    return 1\n```\n")
        # 去围栏后有效代码字符数
        assert out >= len("def f():")

    def test_comment_and_blank_skipped(self):
        from src.tools.patch_postprocess import _effective_code_chars

        text = "# only comment\n\n\n"
        assert _effective_code_chars(text) == 0


class TestExtractTopLevelImportsBranches:
    def test_extract_imports(self):
        from src.tools.patch_postprocess import _extract_top_level_imports

        code = "import os\nfrom collections import OrderedDict\n\ndef f():\n    import sys\n"
        out = _extract_top_level_imports(code)
        # 顶层 import 两行（函数体内局部 import 不取）
        assert any("os" in line for line in out)
        assert any("OrderedDict" in line for line in out)

    def test_invalid_code_returns_empty(self):
        from src.tools.patch_postprocess import _extract_top_level_imports

        assert _extract_top_level_imports("def f(:\n") == []


class TestRepairMissingImportsBranches:
    def test_disabled_returns_none(self, monkeypatch):
        from src.tools.patch_postprocess import repair_missing_imports

        monkeypatch.delenv("IMPORT_REPAIR_ENABLE", raising=False)
        out = repair_missing_imports(
            "import os\n\ndef f():\n    return os.getcwd()\n", "def f():\n    return os.getcwd()\n"
        )
        assert out is None

    def test_enabled_repair_backfills_missing_import(self, monkeypatch):
        from src.tools.patch_postprocess import repair_missing_imports

        monkeypatch.setenv("IMPORT_REPAIR_ENABLE", "true")
        original = "import os\n\ndef f():\n    return os.getcwd()\n"
        # 补丁（完整文件形态，带顶层 import 意图）丢失了 import os
        patch = "import sys\n\ndef f():\n    return os.getcwd()\n"
        out = repair_missing_imports(original, patch)
        assert out is not None
        assert "import os" in out


class TestRepairContractAliasesBranches:
    def test_disabled_returns_none(self, monkeypatch):
        from src.tools.patch_postprocess import repair_contract_aliases

        monkeypatch.delenv("CONTRACT_ALIAS_ENABLE", raising=False)
        out = repair_contract_aliases("class Rule_L001:\n    pass\n", "class RuleL001:\n    pass\n")
        assert out is None

    def test_enabled_rename_suspect_backfills_alias(self, monkeypatch):
        from src.tools.patch_postprocess import repair_contract_aliases

        monkeypatch.setenv("CONTRACT_ALIAS_ENABLE", "true")
        # 原符号 Rule_L001 在补丁中缺失，补丁新增 RuleL001（前缀相关）→ 回填别名
        original = "class Rule_L001:\n    pass\n"
        patch = "class RuleL001:\n    pass\n"
        out = repair_contract_aliases(original, patch)
        assert out is not None
        assert "Rule_L001" in out

    def test_enabled_pure_delete_no_suspect_returns_none(self, monkeypatch):
        from src.tools.patch_postprocess import repair_contract_aliases

        monkeypatch.setenv("CONTRACT_ALIAS_ENABLE", "true")
        # 原符号被纯删除，补丁无重命名嫌疑 → None
        original = "def Rule_L001():\n    pass\n"
        patch = "def other_func():\n    pass\n"
        out = repair_contract_aliases(original, patch)
        assert out is None


class TestSanitizePatchBranches:
    def test_none_patch_short_circuit(self, monkeypatch):
        from src.tools.patch_postprocess import sanitize_patch

        monkeypatch.delenv("EMPTY_PATCH_GUARD", raising=False)
        out, labels = sanitize_patch("x", None)
        assert out == ""
        assert "empty_patch" in labels

    def test_empty_patch_label(self, monkeypatch):
        from src.tools.patch_postprocess import sanitize_patch

        monkeypatch.delenv("EMPTY_PATCH_GUARD", raising=False)
        _out, labels = sanitize_patch("x", "   ")
        assert "empty_patch" in labels

    def test_clean_patch_no_labels(self, monkeypatch):
        from src.tools.patch_postprocess import sanitize_patch

        monkeypatch.delenv("EMPTY_PATCH_GUARD", raising=False)
        out, labels = sanitize_patch("def f():\n    return 1\n", "def f():\n    return 1 + 1\n")
        assert labels == []
        assert out == "def f():\n    return 1 + 1\n"


class TestImportModuleNamesBranches:
    def test_import_as_alias(self):
        from src.tools.patch_postprocess import _import_module_names

        # import a.b as c → 别名 c（import 形式取 asname，无 asname 时取模块首段）
        out = _import_module_names("import a.b as c")
        assert "c" in out
        # 无 asname 形式 → 顶层模块名
        out2 = _import_module_names("import collections")
        assert "collections" in out2

    def test_from_import(self):
        from src.tools.patch_postprocess import _import_module_names

        out = _import_module_names("from x.y import m1, m2")
        assert "x.y" in out
        assert "m1" in out
        assert "m2" in out

    def test_invalid_line_empty(self):
        from src.tools.patch_postprocess import _import_module_names

        assert _import_module_names("not valid python") == []


class TestPostprocessFlagsBranches:
    def test_flags_structure(self):
        from src.tools.patch_postprocess import postprocess_enabled_flags

        out = postprocess_enabled_flags()
        assert set(out.keys()) == {"empty_patch_guard", "import_repair", "contract_alias"}
        assert all(isinstance(v, bool) for v in out.values())
