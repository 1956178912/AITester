"""FB 轮：`python -O` 不得移除防 reward-hacking 的策略守卫。"""

from __future__ import annotations

import ast
import inspect
import os
import subprocess
import sys
from pathlib import Path

import pytest

from src.graph import orchestration_search

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_policy_guard_does_not_use_removable_assert():
    """运行期策略判据必须是显式分支，不能依赖会被优化器删除的 Assert 节点。"""
    tree = ast.parse(inspect.getsource(orchestration_search.assert_no_credit_coupling))
    assert not any(isinstance(node, ast.Assert) for node in ast.walk(tree))


def test_forbidden_credit_reference_is_rejected(monkeypatch: pytest.MonkeyPatch):
    """负向对照：主循环一旦引用信用函数，必须点名该符号并拒绝通过。"""
    monkeypatch.setattr(
        orchestration_search.inspect,
        "getsource",
        lambda _obj: "class OrchestrationSearch:\n    def choose(self): return hindsight_credits\n",
    )
    with pytest.raises(AssertionError, match="hindsight"):
        orchestration_search.assert_no_credit_coupling()


def test_policy_guard_survives_python_optimized_mode():
    """真实 `python -O` 子进程：同一个禁用引用在优化模式下同样必须被拒绝。"""
    probe = r"""
import src.graph.orchestration_search as module

module.inspect.getsource = lambda _obj: (
    "class OrchestrationSearch:\n"
    "    def choose(self):\n"
    "        return hindsight_credits\n"
)
try:
    module.assert_no_credit_coupling()
except AssertionError as exc:
    assert "hindsight" in str(exc)
    print("optimized guard rejected forbidden coupling")
else:
    raise SystemExit("optimized guard accepted forbidden credit coupling")
"""
    env = dict(os.environ)
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(REPO_ROOT) + (os.pathsep + existing_pythonpath if existing_pythonpath else "")
    completed = subprocess.run(
        [sys.executable, "-O", "-c", probe],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "optimized guard rejected forbidden coupling" in completed.stdout
