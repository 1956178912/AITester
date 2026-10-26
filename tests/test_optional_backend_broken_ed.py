"""ED（2026-10-27）：可选依赖「装上但坏了」——导入期非 ImportError 也须降级。

DG 修的是 embedding 后端**构造期**的兄弟分支不一致；本文件锁**导入期**：
模块级 `try: import X ... except ImportError` 只在"缺包"时降级，而
"`pip install` 成功、包内部损坏"（扩展 ABI 不匹配、传递依赖版本冲突、
本地共享库缺失）抛出的是 RuntimeError/OSError/ValueError——异常会击穿
文档承诺的降级路径。对 chromadb 尤其致命：retriever 导入失败会沿着
`src.cli.app → src.graph.workflow → src.graph.rag → src.rag.retriever`
一路冒泡，整个 CLI 无法启动（不是"RAG 增强不可用"，是命令行不可用）。

每例在子进程里替换 `builtins.__import__`，把目标包变成 RuntimeError，
断言公开入口仍返回文档承诺的降级值；`test_required_dependency_breakage_
still_propagates` 是负控制——必需依赖（click）损坏必须照常抛出，
防止修复退化成"吞掉一切导入错误"。

审计排除 `src/cli/output.py`（rich）：rich 是 httpx 的硬导入（`_main.py`
`import rich.console`），而 httpx 的 `__init__` 只对 `ImportError` 降级
（缺包可降级、坏包直接崩溃）；本包任何 `src.cli.*` 导入都会经
`src/cli/__init__ → app → langgraph → langchain → httpx` 先触发它，
我们这一层捕获 Exception 也无法把 CLI 救回来——修不改变可观测行为，
故不纳入本轮（在 MEASUREMENT_INTEGRITY 登记为排除项）。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]

_HOOK = """
import builtins

_real_import = builtins.__import__
_broken = {broken!r}


def _fake_import(name, *args, **kwargs):
    if name.split(".")[0] in _broken:
        raise RuntimeError("simulated broken install: " + name)
    return _real_import(name, *args, **kwargs)


builtins.__import__ = _fake_import
"""


def _run_broken(packages: tuple[str, ...], body: str, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    """在子进程里把 packages 变成"装了但导入即 RuntimeError"，再执行 body。"""
    code = _HOOK.format(broken=packages) + body + "\nprint('OK')\n"
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


class TestImportBoundaryDegradation:
    """每处可选导入边界：装上但坏了 ⇒ 与"没装"同样的降级值。"""

    def _assert_ok(self, proc: subprocess.CompletedProcess[str]) -> None:
        assert proc.returncode == 0, proc.stderr[-1200:]
        assert "OK" in proc.stdout

    def test_chromadb_broken_cli_starts_and_rag_degrades(self):
        """chromadb 损坏不得拖垮 CLI 启动；RAG 单例按既有失败短路返回 None。"""
        proc = _run_broken(
            ("chromadb",),
            """
import src.cli.app  # noqa: F401  整个 CLI 启动面必须可导入
import src.rag.retriever as retriever

assert retriever.CHROMA_AVAILABLE is False

from src.graph.rag import RAG_MODULE_AVAILABLE, get_rag_retriever

assert RAG_MODULE_AVAILABLE is True
assert get_rag_retriever() is None
""",
        )
        self._assert_ok(proc)

    def test_z3_broken_probe_reports_unavailable(self):
        proc = _run_broken(
            ("z3",),
            """
from src.specs.spec_smt import smt_available

assert smt_available() is False
""",
        )
        self._assert_ok(proc)

    def test_hypothesis_broken_probe_reports_unavailable(self):
        proc = _run_broken(
            ("hypothesis",),
            """
from src.specs.spec_ir import _hypothesis_available

assert _hypothesis_available() is False
""",
        )
        self._assert_ok(proc)

    def test_datasets_broken_loader_raises_import_error_with_cause(self):
        """下载入口仍抛文档承诺的 ImportError，但须把真实导入异常挂在 __cause__。"""
        proc = _run_broken(
            ("datasets",),
            """
import src.datasets.dataset_loader as loader

assert loader._datasets is None
try:
    loader.SWEBenchDataset.download_from_huggingface()
except ImportError as exc:
    assert "datasets" in str(exc)
    assert isinstance(exc.__cause__, RuntimeError), repr(exc.__cause__)
else:
    raise AssertionError("datasets 损坏时 download_from_huggingface 必须抛 ImportError")
""",
        )
        self._assert_ok(proc)

    def test_scipy_broken_significance_reports_unavailable(self):
        proc = _run_broken(
            ("scipy",),
            """
from src.experiments.analysis import analyze_experiment_results

out = analyze_experiment_results({"aitester": {"success_rate": 1.0}})
assert out["significance"]["status"] == "unavailable"
""",
        )
        self._assert_ok(proc)

    def test_tree_sitter_broken_probe_reports_unavailable(self):
        proc = _run_broken(
            ("tree_sitter",),
            """
import src.tools.tree_sitter_backend as backend

assert backend.is_tree_sitter_available() is False
assert backend.tree_sitter is None
""",
        )
        self._assert_ok(proc)

    def test_coverage_broken_fl_spectral_returns_none(self):
        """O2 谱系定位测量：coverage 损坏 ⇒ 与"不可用"一致的 None。"""
        proc = _run_broken(
            ("coverage",),
            r"""
import os
import tempfile

import src.agents.fl_spectral as fl

fd, target = tempfile.mkstemp(suffix=".py")
os.write(fd, b"def f():\n    return 1\n")
os.close(fd)

assert fl._measure_per_test_lines(target, "def test_f():\n    assert True\n") is None
""",
        )
        self._assert_ok(proc)

    def test_coverage_broken_branch_inject_returns_none(self):
        """O3 branch 测量：与 O2 同一条 coverage 依赖，必须同样降级。"""
        proc = _run_broken(
            ("coverage",),
            r"""
import os
import tempfile

import src.tools.branch_coverage_inject as branch

fd, target = tempfile.mkstemp(suffix=".py")
os.write(fd, b"def f():\n    return 1\n")
os.close(fd)

assert branch.measure_branch_coverage(target, "def test_f():\n    assert True\n") is None
""",
        )
        self._assert_ok(proc)

    def test_mypy_broken_testless_layer_unavailable(self):
        """testless 的 mypy 层：损坏 ⇒ 结构化 unavailable（不是崩溃/假通过）。"""
        proc = _run_broken(
            ("mypy",),
            """
from src.tools.testless_validation import VALIDATION_UNAVAILABLE, _run_mypy_layer

out = _run_mypy_layer("x = 1", "mod")
assert out["status"] == VALIDATION_UNAVAILABLE, out
assert out["infra_degraded"] is True
""",
        )
        self._assert_ok(proc)

    def test_mypy_broken_type_repair_layer_unavailable(self):
        """type_repair 的 mypy 层：损坏 ⇒ [] + outcome=unavailable（BH 三态口径）。"""
        proc = _run_broken(
            ("mypy",),
            """
import os

os.environ["TYPE_CHECK_ENABLE"] = "true"

from src.tools.type_repair import STATIC_CHECK_UNAVAILABLE, _run_mypy_findings

sink = []
assert _run_mypy_findings("x = 1", "x = 1", outcome_sink=sink) == []
assert sink[0]["status"] == STATIC_CHECK_UNAVAILABLE, sink
""",
        )
        self._assert_ok(proc)

    def test_pyright_broken_type_repair_layer_unavailable(self):
        """type_repair 的 pyright 层（cli 缺席、包损坏）：同为 unavailable。"""
        proc = _run_broken(
            ("pyright",),
            """
import os
import shutil

os.environ["TYPE_CHECK_ENABLE"] = "true"
os.environ["TYPE_CHECK_BACKEND"] = "pyright"
shutil.which = lambda *args, **kwargs: None

from src.tools.type_repair import STATIC_CHECK_UNAVAILABLE, _run_pyright_findings

sink = []
assert _run_pyright_findings("x = 1", "x = 1", outcome_sink=sink) == []
assert sink[0]["status"] == STATIC_CHECK_UNAVAILABLE, sink
""",
        )
        self._assert_ok(proc)

    def test_numpy_broken_cosine_falls_back_to_pure_python(self):
        """余弦相似度的纯 Python 回退：numpy 损坏也与"缺失"同一条路径。"""
        proc = _run_broken(
            ("numpy",),
            """
from src.utils.embedding_utils import cosine_similarity

assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0
assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0
""",
        )
        self._assert_ok(proc)


def test_required_dependency_breakage_still_propagates():
    """负控制：必需依赖（click）损坏必须照常抛出，不得被降级逻辑吞掉。"""
    proc = _run_broken(("click",), "import src.cli.output  # noqa: F401\n")
    assert proc.returncode != 0
    assert "RuntimeError" in proc.stderr
    assert "simulated broken install: click" in proc.stderr
