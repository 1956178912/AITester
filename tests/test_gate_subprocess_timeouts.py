"""DI 轮（2026-10-26）：门禁链子进程超时预算的回归锁。

## 为什么

门禁脚本里的 `subprocess` 调用若不带 `timeout`，一次挂起（git 锁、ruff/mypy 卡死、
pytest 收集死锁）就会让 `make gates` / CI **无限挂起**——比红更糟：没有读数、没有
失败行，只有被平台作业上限杀掉的整条流水线。本轮把「门禁链每个 spawn 都带预算」
变成结构判据，并把**超时后的语义**逐点锁死：

- 登记面对账：超时 **必须判红**（`RuntimeError`）——该门 `_run` 返回 `None` 会被读成
  `[SKIP]` 静默放行（`check_registration_consistency.py` 的两处 `if res is None`），
  超时走那条路等于把「挂死」洗成「通过」；
- 基线门：超时 → `None`，调用方已有「全量 pytest 收集失败」红；
- 仓库卫生门：超时 → `RuntimeError`（与该函数「git 不可用」同口径）；
- 引用工件门：超时 → 合成 `rc=124` 的 `CompletedProcess`，四处既有失败文案统一收口；
- 静态快照工具：超时 → `(124, 命令超时…)` 落进报告，不炸掉整份快照。

## 分母

AST 扫描面 = `scripts/gates/*.py`（全部门禁）+ 两个被 Makefile / CI 直接调用的工具
脚本。第二例保证扫描面非空（防路径漂移后「零调用点 ⇒ 全绿」）。
"""

from __future__ import annotations

import ast
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_GATES_DIR = PROJECT_ROOT / "scripts" / "gates"
_TOOLS_DIR = PROJECT_ROOT / "scripts" / "tools"
_EXTRA_SCOPE = (_TOOLS_DIR / "generate_static_report.py", _TOOLS_DIR / "e2e_probes_logic.py")
_SPAWN_FUNCS = frozenset({"run", "Popen", "call", "check_call", "check_output"})


def _load(rel: str, name: str):
    path = PROJECT_ROOT / rel
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def registration():
    return _load("scripts/gates/check_registration_consistency.py", "_di_registration")


@pytest.fixture(scope="module")
def baseline():
    return _load("scripts/gates/check_baseline.py", "_di_baseline")


@pytest.fixture(scope="module")
def hygiene():
    return _load("scripts/gates/check_repo_hygiene.py", "_di_hygiene")


@pytest.fixture(scope="module")
def artifacts():
    return _load("scripts/gates/check_artifacts_tracked.py", "_di_artifacts")


@pytest.fixture(scope="module")
def static_report():
    return _load("scripts/tools/generate_static_report.py", "_di_static_report")


def _scope_files() -> list[Path]:
    return sorted(_GATES_DIR.glob("*.py")) + [p for p in _EXTRA_SCOPE if p.exists()]


def _spawn_calls(path: Path) -> list[tuple[int, bool]]:
    """[(行号, 是否带 timeout)]：只认 `subprocess.run/Popen/...` 这类真 spawn 调用。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    calls: list[tuple[int, bool]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        owner = node.func.value
        if not (isinstance(owner, ast.Name) and owner.id == "subprocess"):
            continue
        if node.func.attr not in _SPAWN_FUNCS:
            continue
        calls.append((node.lineno, any(kw.arg == "timeout" for kw in node.keywords)))
    return calls


def _timeout_run(cmd, *args, **kwargs):
    raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs.get("timeout", 1))


# ══ 结构锁：扫描面内每个 spawn 都带预算 ═══════════════════════════════════
def test_every_scope_spawn_declares_a_timeout():
    offenders = [
        f"{path.relative_to(PROJECT_ROOT)}:{lineno}"
        for path in _scope_files()
        for lineno, has_timeout in _spawn_calls(path)
        if not has_timeout
    ]
    assert offenders == [], "门禁链的 subprocess 调用缺 timeout——端点挂起会吃满作业上限：" + ", ".join(offenders)


def test_scan_surface_is_not_empty():
    """分母守卫：门禁目录不许扫空；已知带 spawn 的文件必须在场。"""
    files = _scope_files()
    names = {path.name for path in files}
    assert {
        "check_scheduled_workflows.py",
        "check_dependency_audit.py",
        "check_bibtex_compilability.py",
        "generate_static_report.py",
        "e2e_probes_logic.py",
    } <= names
    total = sum(len(_spawn_calls(path)) for path in files)
    assert total >= 15, f"扫描面只剩 {total} 个 spawn 调用点——AST 判据已失真"
    probes = _spawn_calls(_TOOLS_DIR / "e2e_probes_logic.py")
    assert len(probes) >= 4, "e2e_probes_logic 的 4 个外部命令入口不应消失"


# ══ 行为锁：超时后的语义逐点钉死 ═════════════════════════════════════════
def test_registration_run_turns_timeout_into_runtime_error(registration):
    """超时不得返回 None——那条路会被主流程读成 [SKIP] 静默放行。"""
    with pytest.raises(RuntimeError, match="超时"):
        registration._run(
            [sys.executable, "-c", "import time; time.sleep(5)"],
            PROJECT_ROOT,
            timeout=0.3,
        )


def test_baseline_collection_timeout_degrades_to_none(baseline, monkeypatch):
    monkeypatch.setattr(baseline.subprocess, "run", _timeout_run)
    assert baseline.measure_full_suite() is None


def test_repo_hygiene_timeout_raises_runtime_error(hygiene, monkeypatch):
    monkeypatch.setattr(hygiene.subprocess, "run", _timeout_run)
    with pytest.raises(RuntimeError, match="超时"):
        hygiene.tracked_files(PROJECT_ROOT)


def test_artifacts_tracked_timeout_is_a_readable_failure(artifacts, tmp_path, monkeypatch):
    artifact = tmp_path / "results.json"
    artifact.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(artifacts, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(artifacts.subprocess, "run", _timeout_run)
    tracked, why = artifacts._is_tracked(artifact)
    assert tracked is False
    assert "超时" in why


def test_static_report_timeout_is_recorded_instead_of_raised(static_report, monkeypatch):
    monkeypatch.setattr(static_report.subprocess, "run", _timeout_run)
    rc, out = static_report._run(["ruff", "check", "."])
    assert rc == 124
    assert "超时" in out
