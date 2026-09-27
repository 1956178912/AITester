"""
1.1 LLM 输出后处理层（patch_postprocess）单元测试。

覆盖：
- P1 空壳补丁检测（detect_empty_patch / sanitize_patch 标签）；
- P2 导入断裂修复（repair_missing_imports，默认关 + 开关切换）；
- P3 契约符号别名回填（repair_contract_aliases，默认关 + 开关切换）；
- 开关默认值与观测接口（postprocess_enabled_flags）。
"""

from __future__ import annotations

import pytest

from src.tools.patch_postprocess import (
    detect_empty_patch,
    postprocess_enabled_flags,
    repair_contract_aliases,
    repair_missing_imports,
    sanitize_patch,
)

_ORIG = """import os
import json
from mylib import helper


class Rule_L001:
    def run(self):
        return helper.check(self)


def run_all():
    return [Rule_L001().run()]
"""


@pytest.fixture(autouse=True)
def _default_flags(monkeypatch):
    """每个用例前重置三个开关到默认值（P1 on / P2 off / P3 off）。"""
    monkeypatch.setenv("EMPTY_PATCH_GUARD", "true")
    monkeypatch.setenv("IMPORT_REPAIR_ENABLE", "false")
    monkeypatch.setenv("CONTRACT_ALIAS_ENABLE", "false")
    yield


class TestEmptyPatchGuard:
    """P1 空壳补丁检测。"""

    def test_none_patch(self) -> None:
        assert detect_empty_patch(None) is True

    def test_blank_patch(self) -> None:
        assert detect_empty_patch("   \n\n  ") is True

    def test_markdown_fence_only(self) -> None:
        assert detect_empty_patch("```python\n```") is True

    def test_shell_function_only(self) -> None:
        # 纯壳函数（无行为改变）算空壳
        assert detect_empty_patch("def f():\n    pass\n") is True

    def test_effective_fix_not_empty(self) -> None:
        # 20 字符阈值：短修复（<20 有效字符）保守判定为空壳
        assert detect_empty_patch("def f():\n    return 42\n") is True
        assert detect_empty_patch("def f(a, b):\n    if a == 0:\n        raise ValueError\n    return a / b\n") is False

    def test_disabled_guard_returns_false(self, monkeypatch) -> None:
        monkeypatch.setenv("EMPTY_PATCH_GUARD", "false")
        assert detect_empty_patch("") is False

    def test_sanitize_returns_empty_label(self) -> None:
        out, labels = sanitize_patch(_ORIG, "")
        assert out == ""
        assert labels == ["empty_patch"]

    def test_sanitize_none_patch_label(self) -> None:
        out, labels = sanitize_patch(_ORIG, None)
        assert out == ""
        assert labels == ["empty_patch"]

    def test_sanitize_none_patch_guard_off(self, monkeypatch) -> None:
        monkeypatch.setenv("EMPTY_PATCH_GUARD", "false")
        out, labels = sanitize_patch(_ORIG, None)
        assert out == ""
        assert labels == []


class TestImportRepair:
    """P2 导入断裂修复。"""

    def test_disabled_by_default(self) -> None:
        patch = """import os

class Rule_L001:
    def run(self):
        return helper.check(self)
"""
        assert repair_missing_imports(_ORIG, patch) is None

    def test_missing_import_repaired_when_enabled(self, monkeypatch) -> None:
        monkeypatch.setenv("IMPORT_REPAIR_ENABLE", "true")
        # 补丁丢失 `from mylib import helper`，但正文仍引用 helper
        patch = """import os
import json

class Rule_L001:
    def run(self):
        return helper.check(self)

def run_all():
    return [Rule_L001().run()]
"""
        repaired = repair_missing_imports(_ORIG, patch)
        assert repaired is not None
        assert "from mylib import helper" in repaired
        # 回填位于补丁头部
        assert repaired.index("from mylib import helper") < repaired.index("import os")

    def test_unused_import_not_repaired(self, monkeypatch) -> None:
        """原代码未使用的 import 不回填（随 LLM 重写消失是合理行为）。"""
        monkeypatch.setenv("IMPORT_REPAIR_ENABLE", "true")
        orig_unused = "import unused_lib\n\n\ndef f():\n    return 1\n"
        patch = "def f():\n    return 1\n"
        # 无顶层 import 意图的补丁 → 不回填
        assert repair_missing_imports(orig_unused, patch) is None

    def test_no_missing_imports_returns_none(self, monkeypatch) -> None:
        monkeypatch.setenv("IMPORT_REPAIR_ENABLE", "true")
        patch = "import os\nimport json\nfrom mylib import helper\n"
        assert repair_missing_imports(_ORIG, patch) is None

    def test_unparseable_original_returns_none(self, monkeypatch) -> None:
        monkeypatch.setenv("IMPORT_REPAIR_ENABLE", "true")
        assert repair_missing_imports("def broken(:\n", "import os\n") is None


class TestContractAlias:
    """P3 契约符号别名回填。"""

    def test_disabled_by_default(self) -> None:
        patch = """import os

class RuleL001:
    def run(self):
        return 1
"""
        assert repair_contract_aliases(_ORIG, patch) is None

    def test_rename_suspect_repaired(self, monkeypatch) -> None:
        monkeypatch.setenv("CONTRACT_ALIAS_ENABLE", "true")
        # LLM 把 Rule_L001 重命名为 RuleL001（前缀嫌疑命中）
        patch = """import os
import json
from mylib import helper

class RuleL001:
    def run(self):
        return helper.check(self)

def run_all():
    return [RuleL001().run()]
"""
        repaired = repair_contract_aliases(_ORIG, patch)
        assert repaired is not None
        assert "Rule_L001 = RuleL001" in repaired
        # 别名行位于补丁尾部
        assert repaired.rstrip().endswith("Rule_L001 = RuleL001  # alias restored by patch postprocess (P3)")

    def test_pure_deletion_returns_none(self, monkeypatch) -> None:
        """无重命名嫌疑的纯删除 → 不自动回填（交 1.3 契约守卫拒绝）。"""
        monkeypatch.setenv("CONTRACT_ALIAS_ENABLE", "true")
        patch = """import os

def run_all():
    return 1
"""
        assert repair_contract_aliases(_ORIG, patch) is None

    def test_no_missing_symbols_returns_none(self, monkeypatch) -> None:
        monkeypatch.setenv("CONTRACT_ALIAS_ENABLE", "true")
        assert repair_contract_aliases(_ORIG, _ORIG) is None

    def test_unparseable_patch_returns_none(self, monkeypatch) -> None:
        monkeypatch.setenv("CONTRACT_ALIAS_ENABLE", "true")
        assert repair_contract_aliases(_ORIG, "def broken(:") is None


class TestSanitizePipeline:
    """sanitize_patch 组合行为。"""

    def test_p2_p3_chain(self, monkeypatch) -> None:
        monkeypatch.setenv("IMPORT_REPAIR_ENABLE", "true")
        monkeypatch.setenv("CONTRACT_ALIAS_ENABLE", "true")
        # 补丁带顶层 import（P2 的前置条件）且重命名 Rule_L001 → RuleL001
        patch = """import os

class RuleL001:
    def run(self):
        return helper.check(self)

def run_all():
    return [RuleL001().run()]
"""
        out, labels = sanitize_patch(_ORIG, patch)
        assert "imports_repaired" in labels
        assert "contract_aliases_restored" in labels
        assert "from mylib import helper" in out
        assert "Rule_L001 = RuleL001" in out

    def test_clean_patch_no_labels(self) -> None:
        out, labels = sanitize_patch(_ORIG, _ORIG)
        assert out == _ORIG
        assert labels == []


class TestFlags:
    """postprocess_enabled_flags 观测接口。"""

    def test_defaults(self) -> None:
        flags = postprocess_enabled_flags()
        assert flags == {"empty_patch_guard": True, "import_repair": False, "contract_alias": False}

    def test_env_switching(self, monkeypatch) -> None:
        monkeypatch.setenv("IMPORT_REPAIR_ENABLE", "true")
        monkeypatch.setenv("CONTRACT_ALIAS_ENABLE", "true")
        monkeypatch.setenv("EMPTY_PATCH_GUARD", "false")
        flags = postprocess_enabled_flags()
        assert flags == {"empty_patch_guard": False, "import_repair": True, "contract_alias": True}
