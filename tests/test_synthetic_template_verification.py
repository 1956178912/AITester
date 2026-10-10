"""P0-5（2026-10-05 独立审查）：合成模板自验证器测试。

锁定 verify_template 的三类判定语义（不可检出 / fixed 不自洽 / 口径漂移）
与跨文件落盘的 target-module 覆盖修复（companion buggy 版不得覆盖 target
的 fixed 版——首版验证器的真实 bug）。全库 50 模板的完整子进程验证由
scripts/tools/verify_synthetic_templates.py 承担（发布前手动跑，CI 不进——
50×2 子进程 pytest 约 2 分钟，属重工具）。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.tools.verify_synthetic_templates import verify_template

_GOOD_SINGLE = {
    "name": "v_probe_good",
    "description": "良好模板",
    "template": "def f(x):\n    return x + 1\n",
    "fixed": "def f(x):\n    return x - 1 if x > 100 else x + 1\n",
    "test_cases": "from v_probe_good import f\n\ndef test_a():\n    assert f(1) == 2\n\ndef test_b():\n    assert f(200) == 199\n",
    "bug_type": "assertion",
    "expected_pass": 1,
    "total_tests": 2,
}


class TestVerifyTemplateSemantics:
    def test_good_template_passes(self):
        # buggy 侧 test_b 红（f(200)=201≠199）+ fixed 全绿 + 口径自洽
        assert verify_template(_GOOD_SINGLE) == []

    def test_undetectable_bug_flagged(self):
        t = dict(_GOOD_SINGLE)
        t["template"] = t["fixed"]  # buggy 与 fixed 等价 → 不可检出
        problems = verify_template(t)
        assert any("不可检出" in p for p in problems)

    def test_inconsistent_fixed_flagged(self):
        t = dict(_GOOD_SINGLE)
        t["fixed"] = "def f(x):\n    return x * 100\n"  # fixed 也错
        problems = verify_template(t)
        assert any("不自洽" in p for p in problems)

    def test_count_drift_flagged(self):
        t = dict(_GOOD_SINGLE)
        t["total_tests"] = 3  # 实际 2 个 def test_
        problems = verify_template(t)
        assert any("口径漂移" in p for p in problems)

    def test_cross_file_companion_does_not_override_fixed(self):
        # 回归锁：target=module_b 的 fixed 落盘后，companion 循环里的
        # module_b_code（buggy 版）不得覆盖（首版验证器的真实 bug，
        # 曾把 type_mismatch / three_module 误报为 fixed 红）
        t = {
            "name": "v_probe_cross",
            "description": "跨文件探针",
            "module_a_code": "from module_b import lookup\n\ndef display(k):\n    return lookup(k).strip()\n",
            "module_b_code": '_TABLE = {"k": 1}\n\ndef lookup(key):\n    return _TABLE.get(key, 0)\n',
            "fixed_module_b_code": '_TABLE = {"k": "ok"}\n\ndef lookup(key):\n    return _TABLE.get(key, "?")\n',
            "test_cases": (
                "from module_b import lookup\nfrom module_a import display\n\n"
                "def test_lookup_str():\n    assert lookup('k') == 'ok'\n\ndef test_display():\n    assert display('k') == 'ok'\n"
            ),
            "bug_type": "runtime",
            "expected_pass": 0,
            "total_tests": 2,
            "target_module": "module_b",
            "num_files": 2,
        }
        # buggy 侧：lookup 返回 int → 两个断言红（可检出）；
        # fixed 侧：module_b 被 fixed 版占据（不被 companion 覆盖）→ 全绿
        assert verify_template(t, is_cross_pool=True) == []
