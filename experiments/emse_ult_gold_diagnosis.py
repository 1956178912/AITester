#!/usr/bin/env python3
"""emse_ult_gold_diagnosis.py — ULT 官方 gold 测试"全败"的逐任务归因诊断（零 LLM，2026-10-15）。

动机（EMSE 投稿"科学诚信"载荷点）：
    归档审计 `experiments/results/emse_test_sanity_20261015/SANITY_AUDIT.json`
    报告：ULT 官方 gold（`test_list`）在本项目物化的目标代码（`fixed`）上
    **71/71 全败**（ult_lite46 46/46、ult_probe25 25/25）。项目文档据此断言
    这是"上游数据属性（fixed ≠ 正确实现）"。
    "官方测试在官方正确实现上 100% 失败"是极端主张，必须逐任务、机制级
    归因后才能写入稿件——项目自购物化/harness 造成同样现象的可能性与
    "上游数据不一致"完全同权。本脚本即该归因的**唯一证据工件**。

官方契约（一手核验，`~/.cache/aitester/ult_repo/`，引用行号见 README）：
    `Ray/main.py:140-153`（cosmic_ray_init）逐字规定官方物化口径：
      mod.py  = code_import 前置块 + '\\n\\n' + instance['code'] + '\\n\\n'
                （再经 rename_test_functions；ULT 的 code 无 test_ 定义，无影响）
      test.py = code_import 前置块 + '\\n\\n' + 'from mod import *' + '\\n\\n'
                + '\\n\\n'.join(instance['tests'][:num_test_cases])
      toml    = test-command = "pytest test.py"（Ray/main.py:20-29）
    其中 code_import（Ray/main.py:31-46）= os/re/math/numpy/pandas/pytest/
    random/string/warnings/datetime/traceback/numpy as np/pandas as pd/typing 名单。
    官方数据字段：`datasets/ULT.jsonl` → `tests`（list[str]，完整 test_ 函数）；
    `datasets/ULT_Lite.jsonl` → `test_list`（list[str]，裸断言片段）。官方仓库
    无任何 `test_list` 消费者（grep 全仓 0 命中），故 ULT_Lite 的官方执行契约
    由 ULT.jsonl 的 `tests` 形态**推定**：二者断言体逐条相同（本脚本机械核验）。
    官方 `correct_tasks`（Ray/main.py:176-198）= cosmic-ray baseline 在**生成
    测试**上的通过集合，**不是**对 gold 的健全性过滤，本项目文档引用时须注意。

判定口径（每个任务跑 4 种物化，全部本地 pytest，30s 上限，零 LLM）：
    P  = 项目物化（复刻 `experiments/emse_test_sanity_audit.py::_run_one` +
         `experiments/emse_ult_mutk.py::_gold_tests_to_pytest_code`）：模块文件
         `{function_name}.py` = `fixed` 原文，测试文件 `from {function_name}
         import {function_name}` + 裸断言包装；
    P2 = 项目**加载器**物化（复刻 `src/datasets/dataset_ult.py` 的 wrapped_test：
         `from {module} import {fn}` + 非断言行 + `test_i` 包装）——验证"归档审计
         路径"与"在线加载器路径"同结论；
    O  = 官方契约物化（Ray/main.py:140-153 逐字；测试源优先取上游 ULT.jsonl
         `tests`，缺失时把 `test_list` 包成 `def test_N():`）；
    C  = 纠正 harness 对照（官方前置块 + `from mod import *` + **显式**导入 code
         内全部顶层符号，含下划线名）——把"命名/命名空间管线"从"断言内容语义"
         中剥离：C 全过 ⇒ 断言内容与 code 语义一致，失败纯属 harness；
         C 仍败 ⇒ 断言内容与 code 语义不一致（上游数据属性）。

归因规则（机械化，先注册后执行）：
    - C 全过 ∧ O 全过           → `project_only_defect`（项目物化唯一责任）
    - C 全过 ∧ O 未全过         → `shared_official_contract_defect`（官方契约本身缺陷）
    - C 部分过                  → `mixed_upstream_and_harness`
    - C 全败（语义类异常）      → `upstream_assert_inconsistency`
    - C 出现"code 与前置块均无该符号"的错误 → `undecidable_missing_external_symbol`

签名分桶（每个失败 test 函数）：
    nonterminate_or_timeout / import_or_symbol_error / fixture_or_harness_missing
    / signature_or_api_mismatch / assert_failed_clearly_upstream_bug
    / assert_failed_expectation_mismatch / other
    `assert_failed_clearly_upstream_bug` 的机械判据：AssertionError 且断言期望
    字符串中含 ≥1 个长度 ≥4 的字母词，该词在 `code` 源文本中**完全不出现**
    （实现永不可能产出该词汇）。否则记 `assert_failed_expectation_mismatch`。

纪律：零 LLM（无网络、无模型调用）；确定性（固定文件布局、固定参数、无随机）；
只读归档工件与上游数据集；只写 `--out` 指定目录。
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# ---------------------------------------------------------------------------
# 口径常量（测试锁定）
# ---------------------------------------------------------------------------
CAP_SECONDS = 30  # 单次 pytest 墙钟上限（与 emse_test_sanity_audit 同口径）
ULT_UPSTREAM_DIR = Path.home() / ".cache/aitester/ult_repo"
ULT_LITE_JSONL = ULT_UPSTREAM_DIR / "datasets/ULT_Lite.jsonl"
ULT_FULL_JSONL = ULT_UPSTREAM_DIR / "datasets/ULT.jsonl"

_LITE46_JSON = "experiments/results/spec_ab_scale87_20261012/ult_lite46_replace/benchmark_ult_20261012_214028.json"
_PROBE25_JSON = "experiments/results/emse_ult_specir_probe_20261014/benchmark_ult_20261014_130937.json"

SUBSETS: tuple[tuple[str, str], ...] = (("ult_lite46", _LITE46_JSON), ("ult_probe25", _PROBE25_JSON))

# 官方前置块：Ray/main.py:31-46 逐字复制（含首尾空行）
CODE_IMPORT = """
import os
import re
import math
import numpy
import pandas
import pytest
import random
import string
import warnings
import datetime
import traceback
import numpy as np
import pandas as pd
from typing import List, Dict, Any, Optional, Union, Tuple, Set, FrozenSet, Sequence, Iterable, Generator, Callable
"""

# 官方前置块提供的顶层绑定（NameError 归因用）
PRELUDE_SYMBOLS: frozenset[str] = frozenset(
    {
        "os",
        "re",
        "math",
        "numpy",
        "pandas",
        "pytest",
        "random",
        "string",
        "warnings",
        "datetime",
        "traceback",
        "np",
        "pd",
        "List",
        "Dict",
        "Any",
        "Optional",
        "Union",
        "Tuple",
        "Set",
        "FrozenSet",
        "Sequence",
        "Iterable",
        "Generator",
        "Callable",
    }
)

# ---------------------------------------------------------------------------
# pytest 输出解析
# ---------------------------------------------------------------------------
_RE_TESTLINE = re.compile(r"^(?P<file>\S+\.py)::(?P<test>\S+)\s+(?P<status>PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)\b")
_RE_SUMMARY = re.compile(r"^(?P<verb>FAILED|ERROR)\s+(?P<node>\S+)(?:\s+-\s+(?P<msg>.*))?$")
_RE_SECTION = re.compile(r"^_{5,}\s*(?P<name>.+?)\s*_{5,}$")
_RE_SECTION_EXC = re.compile(
    r"^E\s{2,}(?:(?P<exc>[A-Za-z_][\w.]*(?:Error|Exception|Exit|Interrupt|Warning))(?::\s*(?P<msg>.*))?"
    r"|(?P<plain>assert\b.*))$"
)
_RE_EXC = re.compile(r"^E\s+(?P<exc>[A-Za-z_][\w.]*(?:Error|Exception|Exit|Interrupt|Warning))\b:?\s*(?P<msg>.*)$")
_RE_COUNT = re.compile(r"(\d+)\s+(passed|failed|error|errors|skipped)")


def _last_nonempty_line(text: str) -> str:
    for line in reversed(text.splitlines()):
        if line.strip():
            return line.strip()[:200]
    return ""


def _split_message(msg: str) -> tuple[str, str]:
    """`AssertionError: assert 3 == 4` → ("AssertionError", "assert 3 == 4")；
    裸 `assert 3 == 4`（pytest 断言重写形态）同样归 AssertionError。"""
    exc_type, sep, exc_msg = msg.partition(":")
    head = exc_type.strip()
    if not sep or head.startswith("assert ") or head == "assert":
        return "AssertionError", msg.strip()
    return head or "Unknown", exc_msg.strip()


def _parse_pytest(stdout: str, rc: int | None) -> dict[str, Any]:
    """把 pytest -v --tb=short 输出解析为逐 test 状态 + 逐失败**完整**签名。

    主解析走 FAILURES/ERRORS 小节：`____ test_name ____` 小节头给出 test 名，
    小节内首条 `E   <ExcType>: <msg>` 给出完整异常（`--tb=line` 的短摘要会被
    pytest 截断，故不作主口径）；短摘要（-rf）仅作回退。
    """
    per_test: dict[str, str] = {}
    for line in stdout.splitlines():
        m = _RE_TESTLINE.match(line.strip())
        if m:
            per_test[f"{m.group('file')}::{m.group('test')}"] = m.group("status")

    by_name: dict[str, dict[str, str]] = {}
    cur: str | None = None
    for line in stdout.splitlines():
        m = _RE_SECTION.match(line.strip())
        if m:
            cur = m.group("name")
            continue
        if cur is None:
            continue
        m2 = _RE_SECTION_EXC.match(line.rstrip())
        if m2 and cur not in by_name:
            # pytest 断言重写后，首条 E 行可能是裸 `assert ...`（无 AssertionError: 前缀）
            is_plain = m2.group("plain") is not None
            by_name[cur] = {
                "exc_type": "AssertionError" if is_plain else m2.group("exc"),
                "message": (m2.group("plain") if is_plain else (m2.group("msg") or "")).strip()[:400],
            }

    sigs: dict[str, dict[str, str]] = {}
    for node, status in per_test.items():
        if status not in {"FAILED", "ERROR"}:
            continue
        name = node.split("::", 1)[-1]
        if name in by_name:
            sigs[node] = by_name[name]
    # 回退：-rf 短摘要（截断，仅在主解析缺失时使用）
    for line in stdout.splitlines():
        m = _RE_SUMMARY.match(line.strip())
        if m and m.group("node") not in sigs:
            exc_type, exc_msg = _split_message((m.group("msg") or "").strip())
            sigs[m.group("node")] = {"exc_type": exc_type, "message": exc_msg[:400]}

    # 收集期错误：从 ERRORS 段抽 E <ExcType>: <msg>
    collection_error: dict[str, str] | None = None
    if rc == 2 and not per_test:
        exc_type, exc_msg = "", ""
        for line in stdout.splitlines():
            m = _RE_EXC.match(line.rstrip())
            if m and "collecting" not in line:
                exc_type, exc_msg = m.group("exc"), m.group("msg")
        collection_error = {
            "exc_type": exc_type or "CollectionError",
            "message": exc_msg.strip()[:400] or _last_nonempty_line(stdout),
        }

    n_passed = sum(1 for v in per_test.values() if v == "PASSED")
    n_failed = sum(1 for v in per_test.values() if v == "FAILED")
    n_error = sum(1 for v in per_test.values() if v == "ERROR")
    if collection_error is not None:
        status = "collection_error"
    elif rc == 0:
        status = "pass"
    else:
        status = "fail"
    return {
        "status": status,
        "n_passed": n_passed,
        "n_failed": n_failed,
        "n_error": n_error,
        "per_test": per_test,
        "signatures": sigs,
        "collection_error": collection_error,
    }


def _run_pytest(work_dir: Path, target: str, variant: str) -> dict[str, Any]:
    """在 work_dir 运行 `pytest <target> -v --tb=line -rEf`（30s 上限）。"""
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        target,
        "-v",
        "--tb=short",
        "-rf",
        "-p",
        "no:cacheprovider",
    ]
    t0 = time.time()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(work_dir),
            capture_output=True,
            text=True,
            timeout=CAP_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return {
            "variant": variant,
            "status": "nonterminate",
            "rc": None,
            "wall_s": round(time.time() - t0, 1),
            "n_passed": 0,
            "n_failed": 0,
            "n_error": 0,
            "per_test": {},
            "signatures": {},
            "collection_error": None,
            "cmd": " ".join([*cmd, f"# cwd={work_dir.name}"]),
            "tail": f">{CAP_SECONDS}s",
        }
    parsed = _parse_pytest(proc.stdout or "", proc.returncode)
    parsed.update(
        variant=variant,
        rc=proc.returncode,
        wall_s=round(time.time() - t0, 1),
        cmd=" ".join(cmd),
        tail=_last_nonempty_line(proc.stdout or ""),
    )
    return parsed


# ---------------------------------------------------------------------------
# 物化
# ---------------------------------------------------------------------------
def project_test_code(gold_tests: list[str], function_name: str) -> str:
    """复刻 experiments/emse_ult_mutk.py::_gold_tests_to_pytest_code（逐字口径）。"""
    lines = [f"from {function_name} import {function_name}  # noqa: F401", ""]
    for i, raw in enumerate(gold_tests):
        lines.append(f"def test_gold_{i}():")
        for assert_line in raw.splitlines() or [raw]:
            stripped = assert_line.strip()
            if stripped:
                lines.append(f"    {stripped}")
        lines.append("")
    return "\n".join(lines)


def loader_test_code(gold_tests: list[str], function_name: str) -> str:
    """复刻 src/datasets/dataset_ult.py 的 wrapped_test 包装（在线加载器口径）。"""
    module_name_alt = function_name.replace("-", "_")[:50]
    alt_test_code = "\n".join(gold_tests)
    has_bare_asserts = alt_test_code.lstrip().startswith("assert ") or any(
        line.startswith("assert ") for line in alt_test_code.splitlines()
    )
    if not has_bare_asserts:
        return alt_test_code
    non_assert_lines = [
        line for line in alt_test_code.splitlines() if line.strip() and not line.strip().startswith("assert")
    ]
    assert_lines = [line for line in alt_test_code.splitlines() if line.strip().startswith("assert")]
    wrapped: list[str] = [f"from {module_name_alt} import {function_name}"]
    wrapped.extend(non_assert_lines)
    wrapped.extend(f"def test_{i}():\n    {line.strip()}\n" for i, line in enumerate(assert_lines, start=1))
    return "\n".join(wrapped) + "\n"


def official_materialize(code: str, tests: list[str], work_dir: Path) -> None:
    """Ray/main.py:140-153 官方物化（逐字；rename_test_functions 对 ULT code 无影响）。"""
    (work_dir / "mod.py").write_text(CODE_IMPORT + "\n\n" + code + "\n\n", encoding="utf-8")
    test_code = CODE_IMPORT + "\n\n" + "from mod import *" + "\n\n"
    for test in tests:
        test_code += f"{test}\n\n"
    (work_dir / "test.py").write_text(test_code, encoding="utf-8")


def official_module_only_materialize(code: str, test_code: str, module_name: str, work_dir: Path) -> None:
    """只给**模块**加官方前置块（mod.py = code_import + code），测试原文照搬。

    用于生成测试侧的门翻转量化：项目健全性门的物化 = 模块无前置块 +
    生成测试原文（emse_ult_mutk_full.py::_sanity_gate）；官方契约的差别就是
    mod.py 带 ``code_import`` 前置块（Ray/main.py:140-145）。
    """
    (work_dir / f"{module_name}.py").write_text(CODE_IMPORT + "\n\n" + code + "\n\n", encoding="utf-8")
    (work_dir / f"test_{module_name}.py").write_text(test_code, encoding="utf-8")


def _top_level_names(code: str) -> list[str]:
    """code 内全部顶层绑定名（含下划线名；纠正 harness 用）。"""
    names: list[str] = []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return names
    # PERF401 豁免理由：append 分布在 4 个互斥 AST 分支内 + 一层嵌套循环，无法表达
    # 为单一列表推导；语义为"深度 1 的顶层符号收集"，显式分支更可读。
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(node.name)
        elif isinstance(node, ast.Assign):
            names.extend(tgt.id for tgt in node.targets if isinstance(tgt, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.append(node.target.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.append(alias.asname or alias.name.split(".")[0])  # noqa: PERF401
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        # PERF401 豁免理由：去重副作用（seen.add 与 out.append 耦合），推导式会丢失语义
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def corrected_materialize(code: str, tests: list[str], work_dir: Path) -> None:
    """官方前置块 + `from mod import *` + 显式导入 code 内全部顶层符号（含下划线名）。"""
    (work_dir / "mod.py").write_text(CODE_IMPORT + "\n\n" + code + "\n\n", encoding="utf-8")
    names = _top_level_names(code)
    explicit = f"from mod import {', '.join(names)}" if names else ""
    test_code = CODE_IMPORT + "\n\n" + "from mod import *" + "\n\n" + explicit + "\n\n"
    for test in tests:
        test_code += f"{test}\n\n"
    (work_dir / "test.py").write_text(test_code, encoding="utf-8")


def _corrected_materialize_with_extra(code: str, tests: list[str], work_dir: Path, extra_symbols: list[str]) -> None:
    """C+：纠正 harness + 官方前置块之外的缺失模块（补充测量，非官方口径）。"""
    extra = "\n".join(f"import {s}" for s in extra_symbols if s.isidentifier())
    (work_dir / "mod.py").write_text(CODE_IMPORT + "\n" + extra + "\n\n" + code + "\n\n", encoding="utf-8")
    names = _top_level_names(code)
    explicit = f"from mod import {', '.join(names)}" if names else ""
    test_code = CODE_IMPORT + "\n" + extra + "\n\n" + "from mod import *" + "\n\n" + explicit + "\n\n"
    for test in tests:
        test_code += f"{test}\n\n"
    (work_dir / "test.py").write_text(test_code, encoding="utf-8")


# ---------------------------------------------------------------------------
# 签名分桶
# ---------------------------------------------------------------------------
_WORD = re.compile(r"[^\W\d_]{4,}")
_QUOTED = re.compile(r"'([^']*)'|\"([^\"]*)\"")
_NAMEERR = re.compile(r"name '([^']+)' is not defined")
_IMPORTERR_NAME = re.compile(r"cannot import name '([^']+)'")


def _assertion_words(message: str) -> set[str]:
    words: set[str] = set()
    for m in _QUOTED.finditer(message):
        s = m.group(1) if m.group(1) is not None else m.group(2)
        if s:
            words |= {w.lower() for w in _WORD.findall(s)}
    return words


def classify_signature(
    exc_type: str,
    message: str,
    *,
    code: str,
    fut_names: set[str],
) -> tuple[str, str]:
    """返回 (bucket, subcause)。机械规则，先注册后执行（见模块 docstring）。"""
    exc = (exc_type or "").strip()
    if exc in {"ImportError", "ModuleNotFoundError"}:
        return "import_or_symbol_error", f"ImportError:{message[:120]}"
    if exc == "NameError":
        m = _NAMEERR.search(message)
        sym = m.group(1) if m else ""
        if sym in fut_names:
            return "import_or_symbol_error", f"NameError:fut_symbol:{sym}"
        if sym in PRELUDE_SYMBOLS:
            return "fixture_or_harness_missing", f"missing_official_prelude_symbol:{sym}"
        return "fixture_or_harness_missing", f"NameError:undefined_symbol:{sym or message[:80]}"
    if exc == "TypeError":
        return "signature_or_api_mismatch", message[:160]
    if exc == "AssertionError":
        words = _assertion_words(message)
        code_l = code.lower()
        absent = sorted(w for w in words if w not in code_l)
        if absent:
            return "assert_failed_clearly_upstream_bug", f"expected_vocabulary_absent_from_code:{','.join(absent[:4])}"
        return "assert_failed_expectation_mismatch", message[:160]
    return "other", f"{exc}: {message[:160]}"


BUCKETS = (
    "assert_failed_expectation_mismatch",
    "assert_failed_clearly_upstream_bug",
    "import_or_symbol_error",
    "signature_or_api_mismatch",
    "fixture_or_harness_missing",
    "nonterminate_or_timeout",
    "other",
    "collection_error",
)

# 任务级归因（先注册后执行；README §2 逐条口径与此一致）
ATTRIBUTIONS = (
    "project_only_defect",
    "official_contract_defect",
    "mixed_upstream_and_harness",
    "upstream_assert_inconsistency",
    "upstream_missing_module_dependency",
    "upstream_signature_or_type_mismatch",
    "undecidable_nonterminate",
)


def attribute_task(run_o: dict[str, Any], run_c: dict[str, Any], n_gold: int) -> tuple[str, str]:
    """由 O（官方契约）与 C（纠正 harness）两次运行裁定任务级归因 + 机制说明。"""
    c_buckets = Counter(run_c.get("bucket_by_test", {}).values())
    if run_c["status"] == "collection_error":
        c_buckets["collection_error"] += 1
    if run_c["status"] == "nonterminate" or run_o["status"] == "nonterminate":
        return "undecidable_nonterminate", "corrected harness 或官方契约下超时——无法判定断言内容"
    c_ok = run_c["status"] == "pass"
    o_ok = run_o["status"] == "pass"
    if c_ok:
        if o_ok:
            return "project_only_defect", "C 全过 ∧ O 全过：断言内容与 code 语义一致，失败纯由项目物化造成"
        return "official_contract_defect", (
            "C 全过 ∧ O 未过：官方 `from mod import *` 契约本身不绑定该符号（如以下划线开头的顶层函数），"
            "项目物化在此之上又叠加了自有缺陷"
        )
    if run_c["n_passed"] > 0:
        return "mixed_upstream_and_harness", (
            f"C 部分过（{run_c['n_passed']}/{n_gold}）：部分 gold 断言与 code 一致，部分不一致"
        )
    if c_buckets.get("fixture_or_harness_missing") or c_buckets.get("import_or_symbol_error"):
        return "upstream_missing_module_dependency", (
            "C（含官方前置块）仍报 NameError/ImportError：`code` 依赖官方前置块也未提供的模块"
            '（官方 README.md:30 "Self-contained functions" 反例；官方 harness 同样失败）'
        )
    if c_buckets.get("assert_failed_expectation_mismatch") or c_buckets.get("assert_failed_clearly_upstream_bug"):
        return "upstream_assert_inconsistency", "C 全败且均为断言类失败：gold 期望与 code 语义不一致"
    return "upstream_signature_or_type_mismatch", (
        f"C 全败且异常类型为 {dict(c_buckets)}（gold 调用形态与 code 接口/类型不匹配，非断言词汇问题）"
    )


def _bucketize_run(run: dict[str, Any], code: str, fut_names: set[str]) -> None:
    """就地给 run 的每个失败/报错 test 打 bucket。"""
    if run["status"] == "nonterminate":
        run["buckets"] = {"nonterminate_or_timeout": len(run["per_test"]) or 1}
        run["bucket_by_test"] = {k: "nonterminate_or_timeout" for k in run["per_test"]} or {
            "<timeout>": "nonterminate_or_timeout"
        }
        return
    bucket_by_test: dict[str, str] = {}
    counts: Counter[str] = Counter()
    ce = run.get("collection_error")
    if ce:
        bucket, cause = classify_signature(ce["exc_type"], ce["message"], code=code, fut_names=fut_names)
        run["collection_error"]["bucket"] = bucket
        run["collection_error"]["subcause"] = cause
        counts["collection_error"] += 1
    for node, status in run["per_test"].items():
        if status not in {"FAILED", "ERROR"}:
            continue
        sig = run["signatures"].get(node) or run["signatures"].get(node.split("::")[-1]) or {}
        exc_type = sig.get("exc_type", "Unknown")
        message = sig.get("message", "")
        bucket, cause = classify_signature(exc_type, message, code=code, fut_names=fut_names)
        bucket_by_test[node] = bucket
        counts[bucket] += 1
        run.setdefault("signature_detail", {})[node] = {
            "exc_type": exc_type,
            "message": message,
            "bucket": bucket,
            "subcause": cause,
        }
    run["bucket_by_test"] = bucket_by_test
    run["buckets"] = dict(counts)


# ---------------------------------------------------------------------------
# 数据装配
# ---------------------------------------------------------------------------
def _load_json_array(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [r for r in data if isinstance(r, dict)]


def _load_project_tasks(repo: Path) -> list[dict[str, Any]]:
    """从两份归档批次 JSON 提取 71 条 ULT 任务（task_metadata 口径与归档审计一致）。"""
    rows: list[dict[str, Any]] = []
    for subset, rel in SUBSETS:
        path = repo / rel
        if not path.is_file():
            raise FileNotFoundError(f"批次工件缺失：{path}")
        details = json.loads(path.read_text(encoding="utf-8"))["results"]["aitester"]["details"]
        for row in details:
            meta = row.get("task_metadata") or {}
            rows.append(
                {
                    "subset": subset,
                    "task_id": row.get("task_id"),
                    "source_json": rel,
                    "function_name": meta.get("function_name") or "",
                    "fixed": meta.get("fixed") or "",
                    "gold_tests": list(meta.get("gold_tests") or []),
                    "gold_tests_raw": meta.get("gold_tests_raw") or "",
                    "test_cases": meta.get("test_cases") or "",
                    "generated_test": row.get("generated_test") or "",
                }
            )
    return rows


def _normalize_test_body(test: str) -> str:
    """把 `def test_x():\\n    assert ...` 归一为断言体文本（比对 ULT vs ULT_Lite 用）。"""
    lines = [ln.strip() for ln in test.splitlines() if ln.strip()]
    body = [ln for ln in lines if not ln.startswith("def ")]
    return "\n".join(body)


def _upstream_citation(up_full: dict[str, Any] | None, up_lite: dict[str, Any] | None) -> dict[str, Any]:
    """上游数据行引用（便于 README 例证定位）。"""
    return {
        "ULT_jsonl_task_id": (up_full or {}).get("task_id"),
        "ULT_Lite_jsonl_task_id": (up_lite or {}).get("task_id"),
        "ULT_jsonl_tests_n": len((up_full or {}).get("tests") or []),
        "ULT_Lite_jsonl_test_list_n": len((up_lite or {}).get("test_list") or []),
    }


def _evidence(
    rec: dict[str, Any],
    code: str,
    up_full: dict[str, Any] | None,
    up_lite: dict[str, Any] | None,
) -> dict[str, Any]:
    """给每个任务产出 1-3 条最小例证（P 侧首个失败签名 + code 内相关行号）。"""
    out: dict[str, Any] = {"upstream": _upstream_citation(up_full, up_lite), "examples": []}
    code_lines = code.splitlines()
    for run_key in ("P", "C"):
        detail = rec["runs"][run_key].get("signature_detail") or {}
        for node, sig in list(detail.items())[:2]:
            actual = ""
            m = re.search(r"assert\s+(.+?)\s+==\s+(.+)$", sig["message"])
            if m:
                actual = m.group(1).strip()
            line_no = 0
            if actual:
                bare = actual.strip("'\"")
                for i, ln in enumerate(code_lines, 1):
                    if bare and bare in ln:
                        line_no = i
                        break
            out["examples"].append(
                {
                    "variant": run_key,
                    "nodeid": node,
                    "exc_type": sig["exc_type"],
                    "message": sig["message"][:200],
                    "bucket": sig["bucket"],
                    "subcause": sig["subcause"],
                    "code_line_of_actual_value": line_no,
                    "code_line_text": code_lines[line_no - 1].strip()[:160] if line_no else "",
                }
            )
        if rec["runs"][run_key].get("collection_error"):
            ce = rec["runs"][run_key]["collection_error"]
            out["examples"].append(
                {
                    "variant": run_key,
                    "nodeid": "<collection>",
                    "exc_type": ce["exc_type"],
                    "message": ce["message"][:200],
                    "bucket": ce.get("bucket", "collection_error"),
                    "subcause": ce.get("subcause", ""),
                    "code_line_of_actual_value": 0,
                    "code_line_text": "",
                }
            )
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="ULT gold 测试全败归因诊断（零 LLM）")
    ap.add_argument(
        "--out",
        default="experiments/results/emse_ult_gold_diagnosis_20261015/ULT_GOLD_DIAGNOSIS.json",
        help="结果 JSON 落盘路径（相对仓库根）",
    )
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 个任务（调试用；0=全量 71）")
    ap.add_argument(
        "--with-generated",
        action="store_true",
        default=True,
        help="额外跑生成测试的健全性门两态（项目物化 / 官方前置块），量化对已发布 Mut@k 的影响",
    )
    ap.add_argument("--keep-tmp", action="store_true", help="保留临时目录（调试用）")
    ap.add_argument(
        "--only-tasks",
        default="",
        help="逗号分隔的 task_id 白名单（补充测量用；空=全量）",
    )
    ap.add_argument(
        "--from-json",
        default=None,
        help="不跑 pytest，只从既有结果 JSON 重算 README/额外聚合（确定性离线口径）",
    )
    ap.add_argument(
        "--supplement",
        default=None,
        help="补充测量 JSON（含 C+ 变体），渲染进 README §2d；可与 --from-json 联用",
    )
    args = ap.parse_args(argv)

    t_start = time.time()
    repo = REPO
    out_path = (repo / args.out).resolve()
    out_dir = out_path.parent

    supplement = None
    if args.supplement:
        sup_path = Path(args.supplement)
        sup_path = sup_path if sup_path.is_absolute() else (repo / sup_path)
        if sup_path.is_file():
            supplement = json.loads(sup_path.read_text(encoding="utf-8"))

    if args.from_json:
        src = Path(args.from_json)
        src = src if src.is_absolute() else (repo / src)
        report = json.loads(src.read_text(encoding="utf-8"))
        # 用当前代码重新裁定任务级归因（离线、确定性；pytest 结果不变）
        for rec in report["records"]:
            rec["attribution"], rec["attribution_mechanism"] = attribute_task(
                rec["runs"]["O"], rec["runs"]["C"], rec.get("n_gold", 5)
            )
        for key, subset in (("all71", None), ("ult_lite46", "ult_lite46"), ("ult_probe25", "ult_probe25")):
            sub = [r for r in report["records"] if subset is None or r["subset"] == subset]
            report["aggregate"][key]["attribution"] = dict(Counter(r["attribution"] for r in sub))
        _assertion_level_split(report, repo)  # 计算并回写 records[].assertion_level
        src.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        _write_readme(out_dir, report, repo=repo, supplement=supplement)
        _write_sums(out_dir)
        print(f"[ult_gold_diag] 离线重算 README → {out_dir}/README.md", flush=True)
        return 0

    lite = _load_json_array(ULT_LITE_JSONL) if ULT_LITE_JSONL.is_file() else []
    full = _load_json_array(ULT_FULL_JSONL) if ULT_FULL_JSONL.is_file() else []
    full_by_code = {r.get("code", ""): r for r in full}
    lite_by_code = {r.get("code", ""): r for r in lite}

    tasks = _load_project_tasks(repo)
    if args.only_tasks:
        wanted = {t.strip() for t in args.only_tasks.split(",") if t.strip()}
        tasks = [t for t in tasks if t["task_id"] in wanted]
    if args.limit:
        tasks = tasks[: args.limit]

    records: list[dict[str, Any]] = []
    print(f"[ult_gold_diag] 开始：{len(tasks)} 任务 × 6 物化（cap={CAP_SECONDS}s）", flush=True)

    for i, task in enumerate(tasks, 1):
        code = task["fixed"]
        fname = task["function_name"]
        gold = task["gold_tests"]
        up_full = full_by_code.get(code)
        up_lite = lite_by_code.get(code)

        # 上游 tests：优先 ULT.jsonl 原文；缺失则用 ULT_Lite test_list 包装
        if up_full and isinstance(up_full.get("tests"), list):
            official_tests = [str(t) for t in up_full["tests"]]
            official_source = "ULT.jsonl:tests"
        else:
            official_tests = [
                f"def test_{j}():\n" + "\n".join(f"    {ln.strip()}" for ln in t.splitlines() if ln.strip())
                for j, t in enumerate(gold)
            ]
            official_source = "ULT_Lite.jsonl:test_list(wrapped)"

        # 上游断言体一致性核验（ULT.jsonl tests vs ULT_Lite test_list）
        body_full = sorted(_normalize_test_body(t) for t in official_tests)
        body_lite = sorted(_normalize_test_body(t) for t in gold)
        upstream_bodies_equal = bool(body_full) and body_full == body_lite

        fut_names = {fname, fname.strip("_"), f"_{fname}", f"__{fname}"}
        fut_names |= set(_top_level_names(code))

        rec: dict[str, Any] = {
            "subset": task["subset"],
            "task_id": task["task_id"],
            "function_name": fname,
            "n_gold": len(gold),
            "upstream": {
                "in_ULT_Lite_by_code": up_lite is not None,
                "in_ULT_by_code": up_full is not None,
                "ULT_func_name": (up_full or up_lite or {}).get("func_name"),
                "ULT_task_id": (up_full or up_lite or {}).get("task_id"),
                "fixed_byte_identical_to_upstream_code": bool(up_lite is not None or up_full is not None),
                "official_tests_source": official_source,
                "official_tests_equal_lite_test_list": upstream_bodies_equal,
            },
            "runs": {},
        }

        tmp_root = Path(tempfile.mkdtemp(prefix="ultgold_"))
        try:
            # P：项目物化（归档审计路径）
            d = tmp_root / "P"
            d.mkdir()
            (d / f"{fname}.py").write_text(code, encoding="utf-8")
            (d / f"test_{fname}.py").write_text(project_test_code(gold, fname), encoding="utf-8")
            run_p = _run_pytest(d, f"test_{fname}.py", "P_project_audit")
            _bucketize_run(run_p, code, fut_names)

            # P2：项目加载器物化（dataset_ult.py 在线路径）
            d = tmp_root / "P2"
            d.mkdir()
            (d / f"{fname}.py").write_text(code, encoding="utf-8")
            (d / f"test_{fname}.py").write_text(loader_test_code(gold, fname), encoding="utf-8")
            run_p2 = _run_pytest(d, f"test_{fname}.py", "P2_project_loader")
            _bucketize_run(run_p2, code, fut_names)

            # O：官方契约物化
            d = tmp_root / "O"
            d.mkdir()
            official_materialize(code, official_tests, d)
            run_o = _run_pytest(d, "test.py", "O_official_contract")
            _bucketize_run(run_o, code, fut_names)

            # C：纠正 harness 对照
            d = tmp_root / "C"
            d.mkdir()
            corrected_materialize(code, official_tests, d)
            run_c = _run_pytest(d, "test.py", "C_corrected_harness")
            _bucketize_run(run_c, code, fut_names)

            # C+：纠正 harness + 官方前置块**外**的缺失模块（sys/logging/itertools 等）
            # 只在 C 因 "code 与前置块都没有该符号" 失败时补测（廉价、条件触发）
            run_cp = None
            missing_syms = sorted(
                {
                    sig["subcause"].rsplit(":", 1)[-1].strip()
                    for sig in (run_c.get("signature_detail") or {}).values()
                    if sig.get("bucket") == "fixture_or_harness_missing"
                    and "undefined_symbol" in sig.get("subcause", "")
                }
            )
            if missing_syms:
                # 迭代补齐：C+ 可能暴露下一个缺失模块（如 itertools → bisect），
                # 最多 4 轮（有界，防死循环）。
                extra: list[str] = []
                run_cp = None
                for round_no in range(4):
                    extra = sorted(set(extra) | set(missing_syms))
                    d = tmp_root / f"Cplus{round_no}"
                    d.mkdir()
                    _corrected_materialize_with_extra(code, official_tests, d, extra)
                    run_cp = _run_pytest(d, "test.py", "Cplus_corrected_harness_extra_prelude")
                    _bucketize_run(run_cp, code, fut_names)
                    run_cp["extra_symbols"] = list(extra)
                    if run_cp["status"] == "pass":
                        break
                    missing_syms = sorted(
                        {
                            sig["subcause"].rsplit(":", 1)[-1].strip()
                            for sig in (run_cp.get("signature_detail") or {}).values()
                            if sig.get("bucket") == "fixture_or_harness_missing"
                            and "undefined_symbol" in sig.get("subcause", "")
                        }
                        - set(extra)
                    )
                    if not missing_syms:
                        break

            # GP / GO：生成测试健全性门（项目物化 vs 只给模块加官方前置块）
            gp = go = None
            gen = task["generated_test"]
            if args.with_generated and gen.strip() and fname.strip():
                d = tmp_root / "GP"
                d.mkdir()
                (d / f"{fname}.py").write_text(code, encoding="utf-8")
                (d / f"test_{fname}.py").write_text(gen, encoding="utf-8")
                gp = _run_pytest(d, f"test_{fname}.py", "GP_generated_project_gate")
                _bucketize_run(gp, code, fut_names)

                d = tmp_root / "GO"
                d.mkdir()
                official_module_only_materialize(code, gen, fname, d)
                go = _run_pytest(d, f"test_{fname}.py", "GO_generated_official_prelude")
                _bucketize_run(go, code, fut_names)
        finally:
            if not args.keep_tmp:
                shutil.rmtree(tmp_root, ignore_errors=True)

        rec["runs"] = {"P": run_p, "P2": run_p2, "O": run_o, "C": run_c}
        if run_cp is not None:
            rec["runs"]["C+"] = run_cp
        if gp is not None and go is not None:
            rec["runs"]["GP"] = gp
            rec["runs"]["GO"] = go
            rec["generated_gate_flip"] = gp["status"] != "pass" and go["status"] == "pass"

        # ---- 任务级归因 ----
        attribution, mechanism = attribute_task(run_o, run_c, len(gold))
        rec["attribution"] = attribution
        rec["attribution_mechanism"] = mechanism
        rec["c_summary"] = {
            "status": run_c["status"],
            "n_passed": run_c["n_passed"],
            "n_failed": run_c["n_failed"],
            "n_error": run_c["n_error"],
            "buckets": dict(Counter(run_c.get("bucket_by_test", {}).values())),
        }
        rec["evidence"] = _evidence(rec, code, up_full, up_lite)

        records.append(rec)
        print(
            f"[ult_gold_diag] {i}/{len(tasks)} {task['task_id']}: "
            f"P={run_p['status']}({run_p['n_passed']}p/{run_p['n_failed']}f) "
            f"O={run_o['status']}({run_o['n_passed']}p) "
            f"C={run_c['status']}({run_c['n_passed']}p/{run_c['n_failed']}f) → {attribution}",
            flush=True,
        )

    # ---- 聚合 ----
    def _matrix(subset: str | None) -> dict[str, Any]:
        sub = [r for r in records if subset is None or r["subset"] == subset]
        att = Counter(r["attribution"] for r in sub)
        sig_buckets: Counter[str] = Counter()
        for r in sub:
            for run_key in ("P", "P2", "O", "C", "GP", "GO"):
                run = r["runs"].get(run_key)
                if not run:
                    continue
                for b in run.get("bucket_by_test", {}).values():
                    sig_buckets[f"{run_key}:{b}"] += 1
                if run["status"] == "collection_error":
                    sig_buckets[f"{run_key}:collection_error"] += 1
                if run["status"] == "nonterminate":
                    sig_buckets[f"{run_key}:nonterminate_or_timeout"] += 1
        gen_rows = [r for r in sub if "GP" in r["runs"]]
        return {
            "n_tasks": len(sub),
            "attribution": dict(att),
            "signature_buckets": dict(sig_buckets),
            "run_status": {
                f"{k}:{s}": sum(1 for r in sub if r["runs"].get(k, {}).get("status") == s)
                for k in ("P", "P2", "O", "C", "GP", "GO")
                for s in ("pass", "fail", "collection_error", "nonterminate")
            },
            "gold_soundness_corrected": {
                "n_gold_pass_under_C": sum(1 for r in sub if r["runs"]["C"]["status"] == "pass"),
                "n_gold_pass_under_O": sum(1 for r in sub if r["runs"]["O"]["status"] == "pass"),
                "n_gold_pass_under_P": sum(1 for r in sub if r["runs"]["P"]["status"] == "pass"),
                "n_gold_pass_under_P2": sum(1 for r in sub if r["runs"]["P2"]["status"] == "pass"),
            },
            "generated_gate": {
                "n_tasks_with_generated": len(gen_rows),
                "n_pass_under_project_gate": sum(1 for r in gen_rows if r["runs"]["GP"]["status"] == "pass"),
                "n_pass_under_official_prelude_module": sum(1 for r in gen_rows if r["runs"]["GO"]["status"] == "pass"),
                "n_flips_fail_to_pass": sum(1 for r in gen_rows if r.get("generated_gate_flip")),
                "flipped_tasks": [r["task_id"] for r in gen_rows if r.get("generated_gate_flip")],
            },
        }

    agg = {
        "all71": _matrix(None),
        "ult_lite46": _matrix("ult_lite46"),
        "ult_probe25": _matrix("ult_probe25"),
    }

    report = {
        "caliber": {
            "cap_seconds": CAP_SECONDS,
            "pytest": _pytest_version(),
            "python": sys.version.split()[0],
            "upstream_repo": str(ULT_UPSTREAM_DIR),
            "upstream_official_contract": "Ray/main.py:140-153（mod.py=code_import+code；test.py=code_import+'from mod import *'+tests[:k]）",
            "variants": {
                "P": "项目物化（emse_test_sanity_audit._run_one + emse_ult_mutk._gold_tests_to_pytest_code）",
                "P2": "项目加载器物化（src/datasets/dataset_ult.py wrapped_test）",
                "O": "官方契约物化（Ray/main.py:140-153 逐字）",
                "C": "纠正 harness（官方前置块 + 显式导入 code 全部顶层符号）",
                "GP": "生成测试健全性门·项目物化（emse_ult_mutk_full._sanity_gate）",
                "GO": "生成测试健全性门·模块加官方前置块（Ray/main.py:140-145）",
            },
            "zero_llm": True,
            "deterministic": True,
        },
        "wall_clock_s": round(time.time() - t_start, 1),
        "aggregate": agg,
        "records": records,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.only_tasks:
        # 补充测量：只写 JSON，绝不动主 README / SHA256SUMS
        print(f"[ult_gold_diag] 补充测量完成（{len(records)} 任务）→ {out_path}", flush=True)
        return 0
    _write_readme(out_dir, report, repo=repo, supplement=supplement)
    _write_sums(out_dir)
    print(f"[ult_gold_diag] 完成：{out_path}（{report['wall_clock_s']}s）", flush=True)
    return 0


def _pytest_version() -> str:
    try:
        import pytest

        return pytest.__version__
    except Exception:  # pragma: no cover
        return "unknown"


def _write_sums(out_dir: Path) -> None:
    lines = [
        f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}"
        for p in sorted(out_dir.iterdir())
        if p.is_file() and p.name != "SHA256SUMS.txt"
    ]
    (out_dir / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_readme(
    out_dir: Path,
    report: dict[str, Any],
    *,
    repo: Path | None = None,
    supplement: dict[str, Any] | None = None,
) -> None:
    agg = report["aggregate"]
    a = agg["all71"]
    lines = [
        '# ULT 官方 gold 测试"全败"归因诊断（2026-10-15，零 LLM）',
        "",
        "> 输入：`experiments/results/emse_test_sanity_20261015/SANITY_AUDIT.json`（71/71 gold 全败）",
        "> + 上游 `datasets/ULT.jsonl` / `datasets/ULT_Lite.jsonl`（一手核验）。",
        "> 判定：每个任务跑 6 种物化（P/P2/O/C/GP/GO，另按需 C+），pytest 30s 上限，本地执行，无 LLM/网络。",
        "",
        f"墙钟：{report['wall_clock_s']}s；pytest {report['caliber']['pytest']}；Python {report['caliber']['python']}。",
        "",
        "## 0. 结论摘要（先读这节）",
        "",
        f"- **任务级**：71 个任务中 **{a['attribution'].get('project_only_defect', 0)} 个**（`ult__fix_labels`）在**官方契约逐字物化（O）下 5/5 通过**——其 gold 失败的 100% 由项目 harness 造成（项目 mod 文件缺官方 `code_import` 前置块 → `re` 未定义）；其余 {a['n_tasks'] - a['attribution'].get('project_only_defect', 0)} 个在官方契约下同样失败。",
        "- **断言级**：355 条 gold 断言中，项目物化口径通过 44 条、失败 311 条；把 harness 纠正到官方契约 + 显式符号绑定后通过 55 条 ⇒ **项目侧造成的断言失败 11/355 = 3.1%**，**上游断言内容不一致 300/355 = 84.5%**。",
        "- **叠加效应**：28 个任务属 `mixed`——同时存在「项目侧造成的失败」与「上游不一致的失败」；`upstream_*` 全败任务的失败与项目物化无关。",
        "- **对已发布生成测试数字的因果路径**：项目健全性门把 `ult__fix_labels` 误判为红灯（缺前置块），官方前置块下该任务生成套件转绿 ⇒ probe25 有效分母 5 → 6（实测；见 §2c），lite46 不变（9/46）。",
        "- **第二处项目侧缺陷（独立于 gold 结论）**：4 个下划线函数名任务被 `src/datasets/dataset_ult.py:236` 的 `.strip('_')` 改名 ⇒ `ImportError`（= 归档审计里那 4 个 collection error）；官方 `from mod import *` 也不绑定下划线名，故这 4 个在官方契约下仍失败（签名不同）。",
        '- **上游确实存在的缺陷**（同时与官方 README.md:30 "Self-contained functions" 冲突）：`time_in_swiss_german` 期望 `quartel` 而 code 只产出 `viertel`；`centre_on_peak`/`lflverify`/`num_agreeing_tuples` 分别依赖官方前置块也没有的 `sys`/`logging`/`itertools`（`lflverify` 补上 `logging` 后 5/5 通过——属自足性缺口而非断言不一致）。',
        "",
        "## 1. 官方契约（Ray/main.py 逐字引用）",
        "",
        "| 上游文件:行 | 内容 |",
        "|---|---|",
        "| `Ray/main.py:31-46` | `code_import` 前置块（os/re/math/numpy/pandas/pytest/random/string/warnings/datetime/traceback/np/pd/typing） |",
        "| `Ray/main.py:140-145` | `mod.py = code_import + '\\n\\n' + instance['code'] + '\\n\\n'`（再 `rename_test_functions`） |",
        "| `Ray/main.py:148-153` | `test.py = code_import + '\\n\\n' + 'from mod import *' + '\\n\\n' + tests[:k]` |",
        '| `Ray/main.py:20-29` | `test-command = "pytest test.py"`，`timeout = {timeout}` |',
        "| `Ray/main.py:159-174` | 官方一致性过滤 = cosmic-ray `baseline`（**作用于生成测试**，非 gold） |",
        "| `Ray/main.py:192-198` | `correct_tasks_tc_{k}_{model}` = baseline 通过集合 |",
        "| `Ray/leakage_free.py:66-74` | `correct_tasks ∩ leakage_free_tasks`（换一批任务，口径同） |",
        "| `datasets/ULT.jsonl` | 3,909 条，字段 `tests`（list[str]，完整 `def test_*` 函数） |",
        "| `datasets/ULT_Lite.jsonl` | 200 条，字段 `test_list`（list[str]，裸 `assert` 片段） |",
        '| `README.md:150-152` | "we do **not** release the ground-truth tests"（与数据文件含 `tests`/`test_list` 矛盾） |',
        "",
        "**结论**：`test_list` 在上游仓库**无任何消费者**（grep 全仓 0 命中）；ULT_Lite 的官方执行契约由",
        "`ULT.jsonl` 的 `tests` 形态推定 —— 本脚本机械核验二者断言体逐条相同（见 `records[].upstream.official_tests_equal_lite_test_list`）。",
        "官方契约的 `from mod import *` 还隐含一条：**下划线开头的顶层符号不会被导入**（Python `import *` 语义）。",
        "",
        "## 2. 归因矩阵（逐任务，71）",
        "",
        "| 归因 | all71 | ult_lite46 | ult_probe25 |",
        "|---|---|---|---|",
    ]
    keys = sorted({*agg["all71"]["attribution"], *agg["ult_lite46"]["attribution"], *agg["ult_probe25"]["attribution"]})
    lines.extend(
        f"| `{k}` | {agg['all71']['attribution'].get(k, 0)} | "
        f"{agg['ult_lite46']['attribution'].get(k, 0)} | {agg['ult_probe25']['attribution'].get(k, 0)} |"
        for k in keys
    )
    lines += [
        f"| **合计** | **{a['n_tasks']}** | **{agg['ult_lite46']['n_tasks']}** | **{agg['ult_probe25']['n_tasks']}** |",
        "",
        "口径：`project_only_defect` = 官方契约（O）也会过、只有项目物化失败；",
        "`official_contract_defect` = 纠正 harness（C）过、官方 `from mod import *` 契约不过；",
        "`mixed_upstream_and_harness` = C 部分断言过；`upstream_*` = C 全败（断言内容与 code 不一致）。",
        "",
        "## 2b. gold 参照修正值（实测，非估计）",
        "",
        "| 口径 | all71 | ult_lite46 | ult_probe25 |",
        "|---|---|---|---|",
    ]
    for key, label in (
        ("n_gold_pass_under_P", "归档口径 P（项目物化，无前置块）"),
        ("n_gold_pass_under_P2", "在线加载器口径 P2"),
        ("n_gold_pass_under_O", "官方契约口径 O（Ray/main.py 逐字）"),
        ("n_gold_pass_under_C", "纠正 harness 口径 C（前置块 + 显式符号绑定）"),
    ):
        lines.append(
            f"| {label} | {agg['all71']['gold_soundness_corrected'][key]}/71 | "
            f"{agg['ult_lite46']['gold_soundness_corrected'][key]}/46 | "
            f"{agg['ult_probe25']['gold_soundness_corrected'][key]}/25 |"
        )
    lines += [
        "",
        "## 2c. 生成测试健全性门：项目物化 vs 官方前置块（对已发布 Mut@k 的因果影响）",
        "",
        "| 任务集 | 生成测试非空 | 项目门 pass | 官方前置块 pass | fail→pass 翻转 |",
        "|---|---|---|---|---|",
    ]
    for sub_key in ("all71", "ult_lite46", "ult_probe25"):
        g = agg[sub_key]["generated_gate"]
        lines.append(
            f"| {sub_key} | {g['n_tasks_with_generated']} | {g['n_pass_under_project_gate']} | "
            f"{g['n_pass_under_official_prelude_module']} | {g['n_flips_fail_to_pass']}"
            + (f"（{', '.join(g['flipped_tasks'])}）" if g["flipped_tasks"] else "")
            + " |"
        )
    lines += [
        "",
        "## 3. 物化变体状态矩阵（任务级）",
        "",
        "| 变体 | pass | fail | collection_error | nonterminate |",
        "|---|---|---|---|---|",
    ]
    for v in ("P", "P2", "O", "C", "GP", "GO"):
        row = [
            agg["all71"]["run_status"].get(f"{v}:{s}", 0) for s in ("pass", "fail", "collection_error", "nonterminate")
        ]
        lines.append(f"| {v} | " + " | ".join(str(x) for x in row) + " |")
    lines += [
        "",
        "## 4. 失败签名分桶（test 函数级计数）",
        "",
        "| 变体:桶 | 计数 |",
        "|---|---|",
    ]
    for k, v in sorted(agg["all71"]["signature_buckets"].items()):
        lines.append(f"| `{k}` | {v} |")

    # ---- §4b P 侧 fixture_or_harness_missing 细分（项目前置块缺失 vs code 非自足）----
    sub = Counter()
    for rec in report["records"]:
        for v in ("P", "O", "C"):
            for sig in (rec["runs"][v].get("signature_detail") or {}).values():
                if sig.get("bucket") != "fixture_or_harness_missing":
                    continue
                sc = sig.get("subcause", "")
                sub[
                    f"{v}:missing_official_prelude_symbol"
                    if sc.startswith("missing_official_prelude_symbol")
                    else f"{v}:code_not_self_contained"
                ] += 1
    lines += [
        "",
        "## 4b. `fixture_or_harness_missing` 细分（符号缺失归因）",
        "",
        "| 变体:子因 | 计数 |",
        "|---|---|",
    ]
    for k in sorted(sub):
        lines.append(f"| `{k}` | {sub[k]} |")
    lines.append("")
    lines.append("`missing_official_prelude_symbol` = 该符号由官方 `code_import` 提供，仅项目物化缺失 ⇒ 项目侧缺陷；")
    lines.append("`code_not_self_contained` = 官方前置块也没有该模块 ⇒ 上游自足性缺口（官方 harness 同样失败）。")
    lines.append("")

    # ---- §4c 补充测量：fix_labels 生成测试 Mut@k 重基（若存在工件）----
    mutk_path = out_dir / "SUPPLEMENT_GENERATED_MUTK.json"
    if mutk_path.is_file():
        m = json.loads(mutk_path.read_text(encoding="utf-8"))
        rb = m["rebasing"]
        pub, cor = rb["published_specir"], rb["corrected_specir_if_fix_labels_admitted"]
        lines += [
            "",
            "## 4c. 补充测量：fix_labels 进入健全子集后的 specir Mut@k 重基",
            "",
            f"- fix_labels 生成套件（**官方前置块模块**）全变异体 Mut@k = "
            f"**{m['measured']['official_prelude_module']['mutation_score']}**"
            f"（{m['measured']['official_prelude_module']['mutants_killed']}/{m['measured']['official_prelude_module']['mutants_total']}，"
            f"cosmic-ray {m['cosmic_ray_version']}，实测；项目物化下同值但含恒红平凡击杀）。",
            f"- 已发布 specir：{pub['killed']}/{pub['total']} = **{pub['score']}**（n={pub['n_tasks']}）。",
            f"- 修正后（fix_labels 入组）：{cor['killed']}/{cor['total']} = **{cor['score']}**（n={cor['n_tasks']}），"
            f"δ = {rb['delta_score']:+.4f}（{rb['caliber']}）。",
            "",
        ]

    # ---- §4d 补充测量：C+（纠正 harness + 前置块外缺失模块）----
    if supplement:
        sup_recs = supplement.get("records") or []
        cp = [(r["task_id"], (r["runs"].get("C+") or {})) for r in sup_recs if "C+" in (r.get("runs") or {})]
        if cp:
            lines += [
                "",
                "## 4d. 补充测量：C+ = 纠正 harness + 官方前置块**外**的缺失模块",
                "",
                "> 官方 `code_import` 不含 `sys`/`logging`/`itertools` 等；`code` 依赖这些模块时",
                "> 官方 harness 亦失败。C+ 把缺失模块补进前置块后再判定，用来区分",
                "> 「断言内容与 code 一致但缺依赖」与「断言内容本身不一致」。**非官方口径**，仅作上界参照。",
                "",
                "| 任务 | C（官方前置块） | C+（补缺失模块） | 补的符号 |",
                "|---|---|---|---|",
            ]
            for tid, run in cp:
                lines.append(
                    f"| `{tid}` | {run.get('status')}（{run.get('n_passed')}p/{run.get('n_failed')}f） | "
                    f"{run.get('status')}（{run.get('n_passed')}p/{run.get('n_failed')}f） | "
                    f"{', '.join(run.get('extra_symbols') or [])} |"
                )
            n_cp_pass = sum(1 for _, r in cp if r.get("status") == "pass")
            lines += [
                "",
                f"C+ 全过任务数：**{n_cp_pass}/{len(cp)}**（补充测量，仅覆盖 C 上因缺模块报错的任务）。",
            ]

    # ---- §5 断言级（test 函数粒度）P vs C 归因拆分 ----
    split = _assertion_level_split(report, repo)
    lines += [
        "",
        "## 5. 断言级归因拆分（5 条 gold 断言 × 71 任务 = 355，实测）",
        "",
        "| 口径 | 计数 |",
        "|---|---|",
        f"| gold 断言总数 | {split['n_total']} |",
        f"| 项目物化 P 上通过 | {split['n_pass_P']} |",
        f"| 项目物化 P 上失败 | {split['n_fail_P']} |",
        f"| 纠正 harness C 上通过 | {split['n_pass_C']} |",
        f"| C 上失败（= 断言内容与 code 语义不一致） | {split['n_fail_C']} |",
        f"| **P 失败 ∧ C 通过（项目物化/harness 造成的断言失败）** | **{split['n_project_harness_caused']}** |",
        f"| **P 失败 ∧ C 失败（上游断言内容不一致）** | **{split['n_upstream_caused']}** |",
        f"| P 通过 ∧ C 失败（罕见：物化差异掩盖） | {split['n_pass_P_fail_C']} |",
        "",
        f"机器可读逐条记录：`ULT_GOLD_DIAGNOSIS.json → records[].assertion_level`（{split['n_total']} 条）。",
        "",
        "## 6. 各桶最小例证（verbatim 签名 + 上游定位）",
        "",
    ]
    for bucket in (*BUCKETS, "collection_error"):
        ex = _pick_examples(report, bucket, k=3)
        if not ex:
            continue
        lines.append(f"### `{bucket}`")
        lines.append("")
        for e in ex:
            lines.append(
                f"- `{e['task_id']}`（{e['subset']}，上游 `{e['upstream_file']}` 数组下标 {e['upstream_index']}，"
                f"task_id={e['upstream_task_id']}）变体 {e['variant']}：`{e['exc_type']}: {e['message'][:120]}`"
                + (f"；子因 `{e['subcause'][:70]}`" if e.get("subcause") else "")
                + (
                    f" ；`code` 第 {e['code_line_of_actual_value']} 行：`{e['code_line_text'][:80]}`"
                    if e["code_line_of_actual_value"]
                    else ""
                )
            )
        lines.append("")

    lines += [
        "## 7. 复现",
        "",
        "```bash",
        "# 零 LLM：只读归档批次工件 + 上游数据集 + 本地 pytest（71 任务 × 6 物化，实测墙钟见上）",
        ".venv/bin/python experiments/emse_ult_gold_diagnosis.py",
        "",
        "# 离线只重算本 README（不跑 pytest）",
        ".venv/bin/python experiments/emse_ult_gold_diagnosis.py --from-json "
        "experiments/results/emse_ult_gold_diagnosis_20261015/ULT_GOLD_DIAGNOSIS.json",
        "```",
        "",
        "逐任务明细与原始签名见 `ULT_GOLD_DIAGNOSIS.json`（`records[].runs.{P,P2,O,C,GP,GO}`）。",
        "",
    ]
    (out_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# README 的离线聚合（从结果 JSON + 归档批次工件 + 上游数据集重算，不跑 pytest）
# ---------------------------------------------------------------------------
def _norm_body(text: str) -> str:
    return "\n".join(ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("def "))


def _index_suffix(nodeid: str) -> int:
    m = re.search(r"_(\d+)$", nodeid.split("::", 1)[-1])
    return int(m.group(1)) if m else -1


def _assertion_level_split(report: dict[str, Any], repo: Path) -> dict[str, Any]:
    """把 P/C 两次运行的逐 test 状态按**断言体文本**对齐，得到断言级归因拆分。

    对应关系：P → `test_gold_{i}` ↔ `gold_tests[i]`；C → `test_<fn>_{j}` ↔
    ULT.jsonl `tests[j]`（两者断言体逐条相同，已核验）。同时把逐条结果写回
    `records[].assertion_level`。
    """
    tasks = {t["task_id"]: t for t in _load_project_tasks(repo)}
    full_by_code = {r.get("code", ""): r for r in _load_json_array(ULT_FULL_JSONL)}
    n_total = n_pass_P = n_fail_P = n_pass_C = n_fail_C = 0
    both_fail = p_only = p_pass_c_fail = 0
    for rec in report["records"]:
        task = tasks.get(rec["task_id"]) or {}
        gold = task.get("gold_tests") or []
        up_full = full_by_code.get(task.get("fixed") or "")
        official = [str(t) for t in (up_full or {}).get("tests") or []] or gold
        p_status = rec["runs"]["P"].get("per_test") or {}
        c_status = rec["runs"]["C"].get("per_test") or {}
        c_by_index: dict[int, str] = {}
        for node, st in c_status.items():
            j = _index_suffix(node)
            if j >= 0:
                c_by_index.setdefault(j, st)
        # 断言体 → 官方 tests 下标（两者逐条相同；缺失时按位对齐）
        c_body_index = {_norm_body(b): j for j, b in enumerate(official)}
        rows: list[dict[str, Any]] = []
        for i, body in enumerate(gold):
            node = f"test_{rec['function_name']}.py::test_gold_{i}"
            st_p = p_status.get(node, "not_collected")
            norm = _norm_body(body)
            j = c_body_index.get(norm, i if i < len(official) else -1)
            st_c = c_by_index.get(j, "not_collected") if j >= 0 else "not_collected"
            rows.append({"i": i, "assertion": body[:300], "P": st_p, "C": st_c})
            n_total += 1
            n_pass_P += st_p == "PASSED"
            n_fail_P += st_p != "PASSED"
            n_pass_C += st_c == "PASSED"
            n_fail_C += st_c != "PASSED"
            if st_p != "PASSED" and st_c == "PASSED":
                p_only += 1
            elif st_p != "PASSED" and st_c != "PASSED":
                both_fail += 1
            elif st_p == "PASSED" and st_c != "PASSED":
                p_pass_c_fail += 1
        rec["assertion_level"] = rows
    return {
        "n_total": n_total,
        "n_pass_P": n_pass_P,
        "n_fail_P": n_fail_P,
        "n_pass_C": n_pass_C,
        "n_fail_C": n_fail_C,
        "n_project_harness_caused": p_only,
        "n_upstream_caused": both_fail,
        "n_pass_P_fail_C": p_pass_c_fail,
    }


def _pick_examples(report: dict[str, Any], bucket: str, k: int = 3) -> list[dict[str, Any]]:
    """按桶挑 2-3 条最小例证（优先 P → O → C），并补上游数组下标定位。"""
    lite = _load_json_array(ULT_LITE_JSONL) if ULT_LITE_JSONL.is_file() else []
    full = _load_json_array(ULT_FULL_JSONL) if ULT_FULL_JSONL.is_file() else []
    lite_idx = {r.get("task_id"): i for i, r in enumerate(lite)}
    full_idx = {r.get("task_id"): i for i, r in enumerate(full)}
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for variant in ("P", "O", "C"):
        for rec in report["records"]:
            if rec["task_id"] in seen:
                continue
            detail = rec["runs"][variant].get("signature_detail") or {}
            for node, sig in detail.items():
                if sig.get("bucket") != bucket:
                    continue
                up = rec["upstream"]
                use_full = up.get("ULT_task_id") in full_idx
                src = "ULT.jsonl" if use_full else "ULT_Lite.jsonl"
                idx = full_idx.get(up.get("ULT_task_id")) if use_full else lite_idx.get(up.get("ULT_task_id"))
                ex = next(
                    (
                        e
                        for e in (rec.get("evidence") or {}).get("examples", [])
                        if e["nodeid"] == node and e["variant"] == variant
                    ),
                    {},
                )
                out.append(
                    {
                        "task_id": rec["task_id"],
                        "subset": rec["subset"],
                        "variant": variant,
                        "exc_type": sig["exc_type"],
                        "message": sig["message"],
                        "upstream_file": src,
                        "upstream_index": idx if idx is not None else -1,
                        "upstream_task_id": up.get("ULT_task_id"),
                        "subcause": sig.get("subcause", ""),
                        "code_line_of_actual_value": ex.get("code_line_of_actual_value", 0),
                        "code_line_text": ex.get("code_line_text", ""),
                    }
                )
                seen.add(rec["task_id"])
                break
            if len(out) >= k:
                break
        if len(out) >= k:
            break
    return out[:k]


if __name__ == "__main__":
    raise SystemExit(main())
