"""tools/patch_applier 动态 bypass 构造 / 命名契约 / diff 分支补齐（2026-10-02 批次·九）。

锁定 patch_applier.py 低覆盖分支（纯静态，零 LLM / 零网络）：
- _collect_dynamic_bypass_constructions：getattr/importlib/ctypes/shutil/__import__
  危险 API 构造的 AST 守卫分支（危险模块限定 + 属性命中 + 别名兜底）
- _collect_dynamic_import_bypass：__import__().attr / 别名引用 / getattr(module, attr)
  三模式动态获取危险模块
- _collect_module_level_symbols：__all__ 提取 / 顶层 Assign / AnnAssign / dunder 跳过 /
  解析失败空集
- check_naming_contract：开关关闭 / 空代码 / 无原符号 / 删除符号 / 保留符号
- generate_diff：unified diff 输出 / 空变更 / 多行变更
- _patch_ast_valid：空代码 / 合法 / 非法语法
"""

from __future__ import annotations

# ─── _collect_dynamic_bypass_constructions 分支 ────────────────────────────


class TestCollectDynamicBypassConstructions:
    def _collect(self, code: str):
        from src.tools.patch_applier import _collect_dynamic_bypass_constructions

        return _collect_dynamic_bypass_constructions(code)

    def test_getattr_dangerous_module_name_hit(self):
        """getattr(os, "system")：基对象为已知危险模块名 → 拦截。"""
        out = self._collect('import os\ngetattr(os, "system")("rm -rf /")\n')
        assert any("system" in s for s in out)

    def test_getattr_dangerous_attr_unknown_base_hit(self):
        """getattr(unknown_obj, "system")：属性命中危险集 → 保守拦截。"""
        out = self._collect('getattr(some_obj, "popen")\n')
        assert any("popen" in s for s in out)

    def test_getattr_safe_attr_not_hit(self):
        """getattr(obj, "name")：属性非危险集 → 不拦截（防误报）。"""
        out = self._collect('getattr(config, "name")\n')
        assert out == set()

    def test_getattr_non_string_attr_not_hit(self):
        """getattr(obj, var)：属性参数非字符串常量 → 不命中（保守放行）。"""
        out = self._collect("def f(attr):\n    getattr(config, attr)\n")
        assert out == set()

    def test_importlib_dangerous_module_hit(self):
        """importlib.import_module("os") → 拦截。"""
        out = self._collect('import importlib\nimportlib.import_module("subprocess")\n')
        assert any("subprocess" in s for s in out)

    def test_importlib_safe_module_not_hit(self):
        """importlib.import_module("json")：模块非危险集 → 不拦截。"""
        out = self._collect('import importlib\nimportlib.import_module("json")\n')
        assert out == set()

    def test_importlib_non_constant_arg_not_hit(self):
        """importlib.import_module(mod_var)：参数非常量 → 不命中。"""
        out = self._collect("import importlib\ndef f(m):\n    importlib.import_module(m)\n")
        assert out == set()

    def test_ctypes_dangerous_hits(self):
        """ctypes.CDLL / create_string_buffer / memmove / windll / oledll 全命中。"""
        out = self._collect(
            "import ctypes\n"
            "ctypes.CDLL('libc.so')\n"
            "ctypes.create_string_buffer(b'x')\n"
            "ctypes.memmove(a, b, 4)\n"
            "ctypes.windll\n"
            "ctypes.oledll\n"
        )
        assert any("CDLL" in s for s in out)
        assert any("create_string_buffer" in s for s in out)
        assert any("memmove" in s for s in out)

    def test_ctypes_safe_attr_not_hit(self):
        """ctypes.c_int：属性非危险集 → 不拦截。"""
        out = self._collect("import ctypes\nx = ctypes.c_int(0)\n")
        assert out == set()

    def test_shutil_dangerous_hits(self):
        """shutil.rmtree / copy2 / move / unlink 全命中。"""
        out = self._collect(
            "import shutil\nshutil.rmtree('/tmp/x')\nshutil.copy2(a, b)\nshutil.move(a, b)\nshutil.unlink(f)\n"
        )
        assert any("rmtree" in s for s in out)
        assert any("copy2" in s for s in out)

    def test_shutil_safe_attr_not_hit(self):
        """shutil.disk_usage：属性非危险集 → 不拦截。"""
        out = self._collect("import shutil\nshutil.disk_usage('/')\n")
        assert out == set()

    def test_double_import_dangerous_hit(self):
        """__import__("os") → 拦截。"""
        out = self._collect('__import__("os").system("id")\n')
        assert any("__import__" in s for s in out)

    def test_double_import_safe_module_not_hit(self):
        """__import__("json")：模块非危险集 → 不拦截。"""
        out = self._collect('json_mod = __import__("json")\n')
        assert out == set()

    def test_syntax_error_returns_empty(self):
        """解析失败 → 保守返回空集（不阻断）。"""
        assert self._collect("def f(:\n") == set()

    def test_empty_code_returns_empty(self):
        assert self._collect("") == set()


# ─── _collect_dynamic_import_bypass 分支 ────────────────────────────────────


class TestCollectDynamicImportBypass:
    def _collect(self, code: str):
        from src.tools.patch_applier import _collect_dynamic_import_bypass

        return _collect_dynamic_import_bypass(code)

    def test_import_attr_pattern_hit(self):
        """__import__("os").system → 命中。"""
        out = self._collect('__import__("os").system("rm -rf /")\n')
        assert any("system" in s for s in out)

    def test_import_alias_pattern_hit(self):
        """m = __import__("subprocess"); m.run(...) → 别名命中。"""
        out = self._collect('m = __import__("subprocess")\nm.run(["ls"])\n')
        assert any("m.run" in s for s in out)

    def test_importlib_alias_pattern_hit(self):
        """m = importlib.import_module("os"); m.system → 别名命中。"""
        out = self._collect('import importlib\nm = importlib.import_module("os")\nm.system("id")\n')
        assert any("m.system" in s for s in out)

    def test_plain_import_alias_hit(self):
        """import socket as s; s.socket(...) → 裸 import 别名命中。"""
        out = self._collect("import socket as s\ns.socket()\n")
        assert any("s.socket" in s for s in out)

    def test_getattr_module_pattern_hit(self):
        """getattr(os, "system")：基为危险模块名 → 命中。"""
        out = self._collect('import os\ngetattr(os, "system")("id")\n')
        assert any("system" in s for s in out)

    def test_getattr_safe_attr_not_hit(self):
        """getattr(os, "name")：属性非危险集 → 不命中（防误报）。"""
        out = self._collect('import os\ngetattr(os, "name")\n')
        assert out == set()

    def test_safe_module_not_hit(self):
        """__import__("json") 非危险模块 → 不命中。"""
        out = self._collect('j = __import__("json")\nj.loads("{}")\n')
        assert out == set()

    def test_syntax_error_returns_empty(self):
        assert self._collect("def f(:\n") == set()

    def test_empty_code_returns_empty(self):
        assert self._collect("") == set()


# ─── C4 from-import 别名绕过守卫（2026-10-05 系统审查 P0）──────────────────


class TestFromImportAliasBypassGuard:
    """`from os import system; system(...)` 类别名调用必须按限定名命中守卫。

    C4 背景：此前 _qualify_call_node 对裸 Name 只回原名，from-import
    别名调用的限定名（"system"/"run"）不在 _DANGEROUS_CALL_TARGETS 内，
    差集守卫整体被绕过——补丁可注入任意 shell/网络后落盘执行。
    """

    def _added(self, original: str, patched: str):
        from src.tools.patch_applier import dangerous_api_added

        return dangerous_api_added(original, patched)

    def test_from_os_import_system_bypass_blocked(self):
        """from os import system + 调用 → 新增 "os.system" 必须命中。"""
        patched = 'from os import system\n\ndef f():\n    system("id")\n'
        added = self._added("def f():\n    pass\n", patched)
        assert "os.system" in added, f"from-import 别名绕过未拦截：{added}"

    def test_from_subprocess_import_run_bypass_blocked(self):
        """from subprocess import run → 新增 "subprocess.run" 命中。"""
        patched = 'from subprocess import run\n\ndef f():\n    run(["ls"])\n'
        added = self._added("def f():\n    pass\n", patched)
        assert "subprocess.run" in added

    def test_from_import_with_as_alias_bypass_blocked(self):
        """from subprocess import Popen as P → 新增 "subprocess.Popen" 命中。"""
        patched = 'from subprocess import Popen as P\n\ndef f():\n    P("ls")\n'
        added = self._added("def f():\n    pass\n", patched)
        assert "subprocess.Popen" in added

    def test_from_urllib_import_urlopen_bypass_blocked(self):
        """from urllib.request import urlopen → 新增限定名命中。"""
        patched = 'from urllib.request import urlopen\n\ndef f():\n    urlopen("http://x")\n'
        added = self._added("def f():\n    pass\n", patched)
        assert "urllib.request.urlopen" in added

    def test_import_dotted_as_alias_qualified(self):
        """import urllib.request as ur; ur.urlopen(...) → 限定名命中。"""
        patched = 'import urllib.request as ur\n\ndef f():\n    ur.urlopen("http://x")\n'
        added = self._added("def f():\n    pass\n", patched)
        assert "urllib.request.urlopen" in added

    def test_preexisting_from_import_call_not_flagged_as_new(self):
        """差集口径不回归：原代码已有的 from-import 调用不算新增。"""
        original = 'from os import system\n\ndef f():\n    system("id")\n'
        patched = 'from os import system\n\ndef f():\n    system("id")\n\n\ndef g():\n    pass\n'
        assert self._added(original, patched) == []

    def test_from_import_safe_symbol_not_flagged(self):
        """from math import sqrt 等安全导入 → 不拦截（防误报）。"""
        patched = "from math import sqrt\n\ndef f():\n    return sqrt(4)\n"
        assert self._added("def f():\n    pass\n", patched) == []

    def test_local_name_shadowing_safe_import_still_resolves(self):
        """同文件 import os + from os import system 混用均可命中。"""
        patched = 'import os\nfrom subprocess import call\n\ndef f():\n    os.system("id")\n    call(["ls"])\n'
        added = self._added("def f():\n    pass\n", patched)
        assert "os.system" in added
        assert "subprocess.call" in added


# ─── _collect_module_level_symbols 分支 ─────────────────────────────────────


class TestCollectModuleLevelSymbols:
    def _collect(self, code: str):
        from src.tools.patch_applier import _collect_module_level_symbols

        return _collect_module_level_symbols(code)

    def test_top_level_functions_and_classes(self):
        out = self._collect("def f():\n    pass\n\nclass C:\n    pass\n")
        assert "f" in out and "C" in out

    def test_async_function_included(self):
        out = self._collect("async def a():\n    pass\n")
        assert "a" in out

    def test_dunder_assign_not_included(self):
        """__all__ 本身不作为常量符号（startswith dunder 跳过），但其内容提取。"""
        out = self._collect("__all__ = ['f', 'g']\ndef f():\n    pass\n")
        assert "__all__" not in out
        assert "f" in out and "g" in out  # __all__ 内符号被提取

    def test_all_tuple_extracted(self):
        """__all__ 为 Tuple 字面量时也提取。"""
        out = self._collect("__all__ = ('f', 'g')\n")
        assert "f" in out and "g" in out

    def test_all_non_string_elt_not_extracted(self):
        """__all__ 元素非字符串常量 → 不提取（保守）。"""
        out = self._collect("__all__ = [x, 42]\n")
        assert "x" not in out and "42" not in out

    def test_top_level_constant_assign_included(self):
        out = self._collect("MAX = 100\nCONST = 'x'\n")
        assert "MAX" in out and "CONST" in out

    def test_dunder_constant_not_included(self):
        out = self._collect("__version__ = '1.0'\n__doc__ = 'd'\n")
        assert "__version__" not in out and "__doc__" not in out

    def test_ann_assign_constant_included(self):
        """顶层 AnnAssign（X: int = 5）纳入符号。"""
        out = self._collect("X: int = 5\n")
        assert "X" in out

    def test_ann_assign_dunder_not_included(self):
        out = self._collect("__x__: int = 5\n")
        assert "__x__" not in out

    def test_syntax_error_returns_empty(self):
        assert self._collect("def f(:\n") == set()

    def test_empty_code_returns_empty(self):
        assert self._collect("") == set()


# ─── check_naming_contract 分支 ────────────────────────────────────────────


class TestCheckNamingContractBranches:
    def _check(self, original: str, patched: str, monkeypatch):
        from src.tools.patch_applier import check_naming_contract

        monkeypatch.delenv("PATCH_CONTRACT_CHECK", raising=False)
        return check_naming_contract(original, patched)

    def test_switch_disabled_returns_pass(self, monkeypatch):
        """PATCH_CONTRACT_CHECK=false 时恒放行。"""
        from src.tools.patch_applier import check_naming_contract

        monkeypatch.setenv("PATCH_CONTRACT_CHECK", "false")
        ok, missing = check_naming_contract("def f():\n    pass\n", "def g():\n    pass\n")
        assert ok is True and missing == []

    def test_empty_code_returns_pass(self, monkeypatch):
        ok, missing = self._check("def f():\n    pass\n", "", monkeypatch)
        assert ok is True and missing == []

    def test_no_original_symbols_returns_pass(self, monkeypatch):
        """原代码无模块级符号（如仅表达式）→ 放行。"""
        ok, missing = self._check("1 + 1\n", "def new_fn():\n    pass\n", monkeypatch)
        assert ok is True and missing == []

    def test_removed_symbol_detected(self, monkeypatch):
        """删除原符号 → 拒绝（返回缺失列表）。"""
        original = "def f():\n    pass\n\nCONST = 1\n"
        patched = "def f():\n    pass\n"  # 删了 CONST
        ok, missing = self._check(original, patched, monkeypatch)
        assert ok is False
        assert "CONST" in missing

    def test_kept_symbols_pass(self, monkeypatch):
        """保留全部原符号 + 新增符号 → 放行。"""
        original = "def f():\n    pass\nCONST = 1\n"
        patched = "def f():\n    pass\n\nCONST = 1\n\ndef g():\n    pass\n"
        ok, missing = self._check(original, patched, monkeypatch)
        assert ok is True and missing == []

    def test_renamed_symbol_detected(self, monkeypatch):
        """重命名（f → g）等价于删除 f + 新增 g → 拒绝。"""
        ok, missing = self._check("def f():\n    pass\n", "def g():\n    pass\n", monkeypatch)
        assert ok is False
        assert "f" in missing

    def test_patch_parse_failure_still_checks(self, monkeypatch):
        """补丁解析失败 → 补丁符号空集 → 原符号全缺失 → 拒绝（保守）。"""
        ok, _missing = self._check("def f():\n    pass\n", "def f(:\n", monkeypatch)
        assert ok is False


# ─── generate_diff 分支 ────────────────────────────────────────────────────


class TestGenerateDiffBranches:
    def _diff(self, old: str, new: str):
        from src.tools.patch_applier import generate_diff

        return generate_diff(old, new)

    def test_no_change_returns_empty(self):
        assert self._diff("def f():\n    return 1\n", "def f():\n    return 1\n") == ""

    def test_simple_change_produces_diff(self):
        out = self._diff("return 1\n", "return 2\n")
        assert "-" in out and "+" in out

    def test_multiline_change(self):
        out = self._diff("def f():\n    return 1\n", "def f():\n    return 1\n    return 2\n")
        assert out.startswith("---")
        assert "original" in out and "modified" in out

    def test_all_lines_replaced(self):
        out = self._diff("a\n", "b\nc\n")
        assert "-a" in out and "+b" in out and "+c" in out


# ─── _patch_ast_valid 分支 ────────────────────────────────────────────────


class TestPatchAstValidBranches:
    def _valid(self, code: str):
        from src.tools.patch_applier import _patch_ast_valid

        return _patch_ast_valid(code)

    def test_empty_code_invalid(self):
        assert self._valid("") is False

    def test_whitespace_only_invalid(self):
        assert self._valid("   \n  ") is False

    def test_valid_python(self):
        assert self._valid("def f():\n    return 1\n") is True

    def test_invalid_syntax(self):
        assert self._valid("def f(:\n") is False

    def test_valid_empty_block(self):
        """合法但空块（pass）→ True。"""
        assert self._valid("if x:\n    pass\n") is True
