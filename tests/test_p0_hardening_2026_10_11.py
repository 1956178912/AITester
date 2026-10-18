"""P0 止血批次（2026-10-11 外部评审 §10）回归守卫。

覆盖两条硬伤修复：
1. **P0-4 进程泄漏**：M1 判分路径从裸 ``subprocess.run(timeout=)`` 改为
   ``run_with_timeout``（start_new_session + killpg 整树终止 + 文件后端）。
   超时后**不得残留孤儿进程**（实测修复前遗留 3 个进程运行 16.5 小时）。
2. **P0-2 记账不可复核**：``repair_history`` 落盘 + ``patch_plausible`` 判据
   证据 + ``correct ∧ ¬plausible`` 不变量观测（存量工件 129 行违反）。

纪律：本文件不调用任何 LLM；超时用例使用 ``sleep`` 构造真实挂起子进程。
"""

from __future__ import annotations

import subprocess
import sys
import time
from typing import Any

import pytest

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from experiments.run_benchmark import (
    _patch_correct as patch_correct,
)
from experiments.run_benchmark import (
    _patch_plausible as patch_plausible,
)
from experiments.run_benchmark import (
    _patch_plausible_evidence as patch_plausible_evidence,
)
from experiments.run_benchmark import (
    _patch_plausible_invariant_violation as patch_plausible_invariant_violation,
)
from experiments.run_benchmark import (
    _repair_history_public as repair_history_public,
)


def _orphans(pattern: str) -> list[str]:
    """返回 ppid==1（已被 init 收养 = 孤儿）且命令行含 pattern 的进程。"""
    out = subprocess.run(
        ["ps", "-eo", "pid,ppid,command"],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    ).stdout
    hits: list[str] = []
    for line in out.splitlines()[1:]:
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        pid, ppid, cmd = parts
        if ppid == "1" and pattern in cmd:
            hits.append(f"{pid}: {cmd[:90]}")
    return hits


def _ps_works() -> bool:
    """ps 不仅存在，而且当前进程真的能读进程表（A-09，2026-10-18 独立评审）。

    某些沙箱/容器宿主 `ps` 二进制存在但执行即 `PermissionError: Operation not
    permitted`；此时"无孤儿残留"断言无法判定——环境能力缺失而非代码缺陷，
    按项目既有 skipif 降级惯例显式 skip。
    """
    try:
        proc = subprocess.run(
            ["ps", "-eo", "pid,ppid,command"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0 and bool(proc.stdout.strip())


_PS_OK = _ps_works()


class TestProcessGroupTimeout:
    """P0-4：超时路径必须整树终止且不残留孤儿。"""

    @pytest.mark.skipif(
        not _PS_OK, reason="宿主环境禁止 ps 读取进程表（沙箱/容器限制），孤儿断言无法判定——非代码缺陷（A-09）"
    )
    def test_timeout_returns_none_and_leaves_no_orphan(self) -> None:
        """挂起测试（子进程 sleep 300）在 timeout 后返回 None，且无孤儿残留。"""
        from experiments._m1_metrics import _run_pytest_in_tmp

        marker = f"aitester_p0_orphan_probe_{int(time.time())}"
        slow_test = (
            "import subprocess\n"
            "\n"
            "def test_hang():\n"
            f"    subprocess.run(['sleep', '300'])  # {marker}\n"
            "    assert True\n"
        )
        target = "def f():\n    return 1\n"

        started = time.time()
        result = _run_pytest_in_tmp(slow_test, target, "m", timeout=3)
        elapsed = time.time() - started

        # 超时 = 不可测（None），不得记为 0（不误报）
        assert result is None, f"超时应返回 None（不可测），实际 {result!r}"
        # 必须真的超时而非立即返回；且不得远超预算（整树终止生效）
        assert 2.5 <= elapsed <= 25, f"耗时异常：{elapsed:.1f}s"

        # 等一个调度周期后检查孤儿（killpg 生效时子进程立即消失）
        deadline = time.time() + 5
        leftovers: list[str] = []
        while time.time() < deadline:
            leftovers = _orphans(marker)
            if not leftovers:
                break
            time.sleep(0.5)
        assert not leftovers, f"超时后残留孤儿进程（killpg 未生效）：{leftovers}"


class _FakeTask:
    """最小任务替身：提供 gold 材料（test_cases + fixed）使 M1 可裁决。"""

    def __init__(self, *, test_cases: str, fixed: str, code: str) -> None:
        self.task_id = "fixture__t"
        self.instance_code = code
        self.metadata: dict[str, Any] = {
            "source": "synthetic",
            "test_cases": test_cases,
            "fixed": fixed,
        }


_TC = "from t import f\n\ndef test_f():\n    assert f(3) == 2\n"
_BUGGY = "def f(x):\n    return x - 1\n"
_EQUIV_FIX = "def f(x):\n    return 1 + (x - 2)\n"  # 语义等价 → gold 裁决通过


class TestRepairHistoryPersistence:
    """P0-2：repair_history 投影与 patch_plausible 判据证据。"""

    def test_projection_keeps_scalars_and_truncates_containers(self) -> None:
        state = {
            "repair_history": [
                {
                    "iteration": 1,
                    "patch_applied": True,
                    "diagnosis": "x",
                    "blob": {"k": [1, 2]},  # 非标量 → 丢弃
                    "lines": ["a" * 500],  # 容器 → 截断
                }
            ]
        }
        rows = repair_history_public(state)
        assert len(rows) == 1
        assert rows[0]["iteration"] == 1
        assert rows[0]["patch_applied"] is True
        assert "blob" not in rows[0], "非标量字段必须丢弃（可序列化投影）"
        assert len(rows[0]["lines"][0]) <= 200, "容器元素必须截断"

    @pytest.mark.parametrize(
        ("state", "expected_basis", "expected_plausible"),
        [
            ({"patch": "", "repair_history": []}, "no_patch", 0),
            ({"patch": "x=1", "repair_history": []}, "no_history", 0),
            (
                {"patch": "x=1", "repair_history": [{"patch_applied": True}]},
                "applied",
                1,
            ),
            (
                {"patch": "x=1", "repair_history": [{"patch_applied": False}]},
                "rejected",
                0,
            ),
            (None, "no_state", 0),
        ],
    )
    def test_evidence_basis_matrix(
        self, state: dict[str, Any] | None, expected_basis: str, expected_plausible: int
    ) -> None:
        ev = patch_plausible_evidence(state)
        assert ev["basis"] == expected_basis
        assert patch_plausible(state) == expected_plausible

    def test_empty_repair_history_key_is_always_present(self) -> None:
        """键集合同构：无状态时也返回空列表而非崩溃。"""
        assert repair_history_public(None) == []
        assert repair_history_public({}) == []


class TestPatchPlausibleInvariant:
    """P0-2：correct ∧ ¬plausible 不变量观测（存量 129 行违反）。"""

    def test_violation_reproduced_when_history_missing(self) -> None:
        """正确补丁 + repair_history 缺失 → 复现存量的矛盾形态。"""
        task = _FakeTask(test_cases=_TC, fixed=_EQUIV_FIX, code=_BUGGY)
        state = {"patch": _EQUIV_FIX, "repair_history": []}
        assert patch_correct(task, state) == 1, "语义等价补丁应被 gold 裁决通过"
        assert patch_plausible(state) == 0, "无写盘记录 → plausible 保守为 0"
        assert patch_plausible_invariant_violation(task, state) is True, "correct=1 ∧ plausible=0 必须被不变量守卫捕获"

    def test_no_violation_when_history_recorded(self) -> None:
        """正确补丁 + 写盘记录 → 不变量成立（无违反）。"""
        task = _FakeTask(test_cases=_TC, fixed=_EQUIV_FIX, code=_BUGGY)
        state = {"patch": _EQUIV_FIX, "repair_history": [{"iteration": 1, "patch_applied": True}]}
        assert patch_correct(task, state) == 1
        assert patch_plausible(state) == 1
        assert patch_plausible_invariant_violation(task, state) is False

    def test_wrong_patch_is_not_correct(self) -> None:
        """错误补丁（gold 裁决失败）→ correct=0，不构成违反。"""
        task = _FakeTask(test_cases=_TC, fixed=_EQUIV_FIX, code=_BUGGY)
        state = {"patch": "def f(x):\n    return x - 2\n", "repair_history": []}
        assert patch_correct(task, state) == 0
        assert patch_plausible_invariant_violation(task, state) is False


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))


class TestPatchPlausibleAnyIterationSemantics:
    """`patch_plausible` 必须采用**任一迭代成功**口径（2026-10-11 修正）。

    原口径只看 `repair_history[-1]`（末条）→ 假阴性源：早期迭代成功写盘、
    后续迭代被 P0 证据门拒绝时，补丁仍在文件中（gold 裁决可通过），
    但末条为 False → plausible 被误记 0。

    实测证据（2026-10-11 真实 LLM 批次，QuixBugs n=10）：
    `quixbugs__bitcount` / `quixbugs__find_first_in_sorted` 两行出现
    `correct=1 ∧ plausible=0`，证据 basis='rejected'、history_len=2。
    """

    def test_early_applied_then_rejected_is_plausible(self) -> None:
        """早期成功 + 末条被拒 → 必须判 plausible=1（本次修复的核心场景）。"""
        state = {
            "patch": "def f():\n    return 1\n",
            "repair_history": [
                {"iteration": 1, "patch_applied": True},
                {"iteration": 2, "patch_applied": False},
            ],
        }
        assert patch_plausible(state) == 1, "早期迭代已写盘成功，plausible 不得为 0"
        ev = patch_plausible_evidence(state)
        assert ev["basis"] == "applied_then_rejected"
        assert ev["ever_patch_applied"] is True
        assert ev["last_patch_applied"] is False

    def test_all_rejected_is_not_plausible(self) -> None:
        state = {
            "patch": "x = 1",
            "repair_history": [{"patch_applied": False}, {"patch_applied": False}],
        }
        assert patch_plausible(state) == 0
        assert patch_plausible_evidence(state)["basis"] == "rejected"

    def test_rejected_then_applied_is_plausible(self) -> None:
        state = {
            "patch": "x = 1",
            "repair_history": [{"patch_applied": False}, {"patch_applied": True}],
        }
        assert patch_plausible(state) == 1
        assert patch_plausible_evidence(state)["basis"] == "applied"

    def test_invariant_holds_after_fix(self) -> None:
        """修正后：正确补丁 + 早期成功记录 → 不变量不再被违反。"""
        task = _FakeTask(test_cases=_TC, fixed=_EQUIV_FIX, code=_BUGGY)
        state = {
            "patch": _EQUIV_FIX,
            "repair_history": [
                {"iteration": 1, "patch_applied": True},
                {"iteration": 2, "patch_applied": False},
            ],
        }
        assert patch_correct(task, state) == 1
        assert patch_plausible(state) == 1
        assert patch_plausible_invariant_violation(task, state) is False


class TestRepairRateRequiresPatchLanded:
    """`repair_rate` 必须要求**补丁真的落地**（2026-10-11 真实批次发现）。

    R28 只堵住了"空补丁"路径。非空补丁**全部被证据门拒绝**
    （`repair_history` 全为 `patch_applied=False`）时，`_target_code_after_patch`
    返回的仍是原始缺陷代码，gold 测试在它上面通过 → 误判 `repair=1.0`。

    实测（2026-10-11 真实 LLM 批次 QuixBugs n=50）：**8/50 行（16%）**呈现
    `patch_applied 全 False ∧ repair_rate=1.0 ∧ source_patched_unverified=True`。
    """

    def test_not_landed_patch_scores_zero(self) -> None:
        from experiments._m1_metrics import _compute_repair_rate

        # gold 测试在**缺陷原码**上就通过（该基准的已知属性）
        task = _FakeTask(test_cases=_TC, fixed=_EQUIV_FIX, code="def f(x):\n    return 1 + (x - 2)\n")
        # 补丁文本非空但未写盘（两轮均被证据门拒绝）
        state = {
            "patch": "def f(x):\n    return 1 + (x - 2)\n",
            "repair_history": [{"patch_applied": False}, {"patch_applied": False}],
        }
        assert _compute_repair_rate(task, state) == 0.0, "补丁未落地时不得记 repair=1.0（否则是纯假阳性）"

    def test_landed_patch_still_scores_one(self) -> None:
        from experiments._m1_metrics import _compute_repair_rate

        task = _FakeTask(test_cases=_TC, fixed=_EQUIV_FIX, code=_BUGGY)
        state = {
            "patch": _EQUIV_FIX,
            "repair_history": [{"patch_applied": True}],
        }
        assert _compute_repair_rate(task, state) == 1.0

    def test_empty_history_keeps_legacy_behaviour(self) -> None:
        """无 repair_history（历史工件）时保持原口径，不引入回归。"""
        from experiments._m1_metrics import _compute_repair_rate

        task = _FakeTask(test_cases=_TC, fixed=_EQUIV_FIX, code=_BUGGY)
        state = {"patch": _EQUIV_FIX, "repair_history": []}
        assert _compute_repair_rate(task, state) == 1.0, "缺 repair_history 的历史工件应维持原判（向下兼容）"
