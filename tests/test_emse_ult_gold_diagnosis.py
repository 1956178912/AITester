"""ULT gold 归因诊断脚本的回归测试（2026-10-15）。

覆盖 experiments/emse_ult_gold_diagnosis.py 的纯函数纪律：
  - _assertion_words 对空字符串字面量的健壮性（曾触发 TypeError）；
  - classify_signature 的机械分桶（官方前置块符号缺失 / 断言词汇缺失 / 导入错误）；
  - attribute_task 的归因规则（project_only_defect / official_contract_defect /
    mixed / upstream_missing_module_dependency / upstream_assert_inconsistency）；
  - _top_level_names 含下划线符号（纠正 harness 的关键）；
  - _parse_pytest 对 -v 输出的解析（含收集期错误）。
"""

from __future__ import annotations

from experiments.emse_ult_gold_diagnosis import (
    CAP_SECONDS,
    CODE_IMPORT,
    PRELUDE_SYMBOLS,
    _assertion_words,
    _parse_pytest,
    _top_level_names,
    attribute_task,
    classify_signature,
    project_test_code,
)


def _run(status: str, n_passed: int = 0, n_failed: int = 0, buckets: dict | None = None) -> dict:
    return {
        "status": status,
        "n_passed": n_passed,
        "n_failed": n_failed,
        "n_error": 0,
        "bucket_by_test": buckets or {},
    }


def test_cap_seconds_matches_archive_caliber() -> None:
    """30s 界限与 emse_test_sanity_audit 同口径（测试锁定）。"""
    assert CAP_SECONDS == 30


def test_code_import_prelude_contains_key_symbols() -> None:
    """官方前置块（Ray/main.py:31-46 逐字）关键符号存在。"""
    for sym in ("import re", "import os", "import datetime", "import numpy as np"):
        assert sym in CODE_IMPORT
    assert {"re", "os", "datetime", "np", "pd"} <= PRELUDE_SYMBOLS


def test_assertion_words_handles_empty_literal() -> None:
    """空字符串字面量不得抛 TypeError（回归：`'' == []` 型断言消息）。"""
    assert _assertion_words("assert [] == []") == set()
    assert _assertion_words("assert f('') == ''") == set()
    assert "quartel" in _assertion_words("assert 'viertel' == 'quartel ab'")


def test_project_test_code_wraps_bare_asserts() -> None:
    """裸断言 → from <mod> import <fn> + test_gold_<i>（归档审计口径）。"""
    code = project_test_code(["assert f(1) == 2"], "f")
    assert code.startswith("from f import f")
    assert "def test_gold_0():" in code
    assert "    assert f(1) == 2" in code


def test_top_level_names_includes_underscore_symbols() -> None:
    """下划线开头顶层函数必须被收集（否则无法纠正 `from mod import *` 缺陷）。"""
    names = _top_level_names("def _normalized_vcf(a):\n    return a\n\n\ndef __transform_coors(a):\n    return a\n")
    assert names == ["_normalized_vcf", "__transform_coors"]


def test_classify_signature_official_prelude_symbol() -> None:
    """NameError 指向官方前置块符号 → fixture_or_harness_missing（项目物化缺前置块）。"""
    bucket, cause = classify_signature(
        "NameError", "name 're' is not defined. Did you forget to import 're'?",
        code="def fix_labels(h):\n    return h\n", fut_names={"fix_labels"},
    )
    assert bucket == "fixture_or_harness_missing"
    assert cause == "missing_official_prelude_symbol:re"


def test_classify_signature_upstream_vocabulary_absent() -> None:
    """期望词汇在 code 中完全不出现 → assert_failed_clearly_upstream_bug。"""
    bucket, cause = classify_signature(
        "AssertionError", "assert 'viertel vor 2 am namittag' == '1 vor quartel abig'",
        code="def f(h, m):\n    return 'viertel vor 2 am namittag'\n", fut_names={"f"},
    )
    assert bucket == "assert_failed_clearly_upstream_bug"
    assert "quartel" in cause


def test_classify_signature_import_error_and_type_error() -> None:
    """ImportError 与 TypeError 各归其桶。"""
    b1, _ = classify_signature(
        "ImportError", "cannot import name 'normalized_vcf' from 'normalized_vcf'",
        code="def _normalized_vcf(a):\n    return a\n", fut_names={"normalized_vcf"},
    )
    assert b1 == "import_or_symbol_error"
    b2, _ = classify_signature(
        "TypeError", "f() missing 1 required positional argument: 'b'",
        code="def f(a, b):\n    return a\n", fut_names={"f"},
    )
    assert b2 == "signature_or_api_mismatch"


def test_attribute_task_project_only_defect() -> None:
    """C 过 ∧ O 过 → project_only_defect。"""
    att, _ = attribute_task(_run("pass", n_passed=5), _run("pass", n_passed=5), 5)
    assert att == "project_only_defect"


def test_attribute_task_official_contract_defect() -> None:
    """C 过 ∧ O 不过 → official_contract_defect（官方 import * 不绑定下划线名）。"""
    att, _ = attribute_task(_run("fail"), _run("pass", n_passed=5), 5)
    assert att == "official_contract_defect"


def test_attribute_task_mixed_and_upstream() -> None:
    """部分过 → mixed；全败且断言类 → upstream_assert_inconsistency。"""
    att_mixed, _ = attribute_task(
        _run("fail"), _run("fail", n_passed=1, n_failed=4, buckets={"t": "assert_failed_expectation_mismatch"}), 5
    )
    assert att_mixed == "mixed_upstream_and_harness"
    att_up, _ = attribute_task(
        _run("fail"), _run("fail", n_passed=0, n_failed=5, buckets={"t": "assert_failed_expectation_mismatch"}), 5
    )
    assert att_up == "upstream_assert_inconsistency"


def test_attribute_task_missing_module_dependency() -> None:
    """C 全败于 NameError（官方前置块也没有该模块）→ upstream_missing_module_dependency。"""
    att, _ = attribute_task(
        _run("fail"), _run("fail", n_passed=0, n_failed=5, buckets={"t": "fixture_or_harness_missing"}), 5
    )
    assert att == "upstream_missing_module_dependency"


def test_parse_pytest_collection_error() -> None:
    """收集期错误（rc=2、无逐 test 行）→ collection_error + ImportError 签名。"""
    out = (
        "collecting ... collected 0 items / 1 error\n"
        "==================================== ERRORS ====================================\n"
        "test_x.py:1: in <module>\n"
        "    from normalized_vcf import normalized_vcf\n"
        "E   ImportError: cannot import name 'normalized_vcf' from 'normalized_vcf'\n"
        "=============================== 1 error in 0.12s ===============================\n"
    )
    parsed = _parse_pytest(out, 2)
    assert parsed["status"] == "collection_error"
    assert parsed["collection_error"]["exc_type"] == "ImportError"


def test_parse_pytest_verbose_lines_and_signatures() -> None:
    """-v 逐 test 行 + -rf 短摘要解析。"""
    out = (
        "test.py::test_gold_0 FAILED                                   [ 50%]\n"
        "test.py::test_gold_1 PASSED                                   [100%]\n"
        "=========================== short test summary info ============================\n"
        "FAILED test.py::test_gold_0 - AssertionError: assert 3 == 4\n"
        "========================= 1 failed, 1 passed in 0.06s =========================\n"
    )
    parsed = _parse_pytest(out, 1)
    assert parsed["status"] == "fail"
    assert parsed["n_passed"] == 1 and parsed["n_failed"] == 1
    assert parsed["signatures"]["test.py::test_gold_0"]["exc_type"] == "AssertionError"


def test_parse_pytest_bare_assert_line() -> None:
    """pytest 断言重写形态：首条 E 行是裸 `assert ...`（无 AssertionError: 前缀）。"""
    out = (
        "test.py::test_gold_0 FAILED                                   [100%]\n"
        "=================================== FAILURES ===================================\n"
        "_________________________________ test_gold_0 __________________________________\n"
        "test.py:4: in test_gold_0\n"
        "    assert f() == 256\n"
        "E   assert 244 == 256\n"
        "E    +  where 244 = f()\n"
        "========================= 1 failed in 0.06s =========================\n"
    )
    parsed = _parse_pytest(out, 1)
    sig = parsed["signatures"]["test.py::test_gold_0"]
    assert sig["exc_type"] == "AssertionError"
    assert sig["message"] == "assert 244 == 256"


def test_split_message_bare_assert() -> None:
    """裸 assert 与带前缀 assert 都归 AssertionError。"""
    from experiments.emse_ult_gold_diagnosis import _split_message

    assert _split_message("assert 3 == 9") == ("AssertionError", "assert 3 == 9")
    assert _split_message("AssertionError: assert 3 == 4") == ("AssertionError", "assert 3 == 4")
    assert _split_message("NameError: name 're' is not defined")[0] == "NameError"
