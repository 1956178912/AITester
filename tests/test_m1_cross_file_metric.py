"""M1 跨文件任务判分（R27，2026-10-08 R2 第三起测量伪影）单元测试。

背景：
    合成跨文件任务（Level 3 / 3.5）的 gold test_cases 直接 ``import
    module_a/module_b/module_c``（与 pattern 名无关，模块名中性化不重写）。
    历史"单文件判分口径"只物化 ``{task_id末段}.py``，伴生模块缺失 →
    gold 测试收集错误 rc=2 → 跨文件行 repair 被系统性判 0、false_fix 抬升。
    本测试锁定修复后的跨文件物化分支与三态判分（buggy/patched/fixed）。

先红后绿过程（R27 修复前）：
    - ``test_detection_cross_file_correct_gold_test``、
      ``test_repair_cross_file_correct_patch`` 在新口径前恒为 0.0；
    - ``test_legacy_without_metadata_rc2`` 记录的正是伪影现象（rc=2），
      修复后**仍应为 2**（历史子串分派回退不变——防止把回退路径一并
      误改成物化，破坏 detection_gates 委托的向后兼容）。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from experiments._m1_metrics import (
    _compute_detection_rate,
    _compute_false_fix_rate,
    _compute_repair_rate,
    _prepare_cross_file_test_tree,
    _run_pytest_in_tmp,
)

# ─── 跨文件任务 fixture（双模块 L3：module_a → module_b；缺陷在 module_b）───

_MODULE_A = "from module_b import process\n\n\ndef run_pipeline(items: list) -> list:\n    return process(items)\n"
_MODULE_B_BUGGY = "def process(items: list) -> list:\n    return [x + 1 for x in items]\n"
_MODULE_B_FIXED = "def process(items: list) -> list:\n    return [x + 2 for x in items]\n"
_GOLD_TEST = (
    "from module_a import run_pipeline\n"
    "from module_b import process\n"
    "\n"
    "\n"
    "def test_process_normal():\n"
    "    assert process([1, 2, 3]) == [3, 4, 5]\n"
    "\n"
    "\n"
    "def test_pipeline_normal():\n"
    "    assert run_pipeline([1, 2, 3]) == [3, 4, 5]\n"
)


def _cross_file_task() -> SimpleNamespace:
    md: dict[str, Any] = {
        "source": "synthetic",
        "is_cross_file": True,
        "num_files": 2,
        "target_module": "module_b",
        "module_a_name": "module_a",
        "module_a_code": _MODULE_A,
        "module_b_name": "module_b",
        "module_b_code": _MODULE_B_BUGGY,
        "module_c_name": "module_c",
        "module_c_code": "",
        "fixed_module_code": _MODULE_B_FIXED,
        "test_cases": _GOLD_TEST,
    }
    return SimpleNamespace(
        task_id="synthetic__task_0002",
        instance_code=_MODULE_B_BUGGY + "\n# noise_seed_b=123\n",
        metadata=md,
        test_code=_GOLD_TEST,
        expected_pass_count=2,
        total_test_count=2,
    )


# ─── 判分三态（修复前恒 0，修复后可达 1.0）───────────────────────────────


def test_detection_cross_file_correct_gold_test() -> None:
    """已知正确的 gold 测试（buggy 红 ∧ fixed 绿）经新口径应判 1.0。"""
    task = _cross_file_task()
    state = {"generated_test": _GOLD_TEST, "patch": "", "test_passed": False}
    assert _compute_detection_rate(task, state) == 1.0


def test_detection_cross_file_wrong_test_still_zero() -> None:
    """盲区测试（buggy 上也绿）仍应判 0.0（物化不改变判定语义）。"""
    task = _cross_file_task()
    blind_test = "def test_ok():\n    assert True\n"
    state = {"generated_test": blind_test, "patch": "", "test_passed": True}
    assert _compute_detection_rate(task, state) == 0.0


def test_repair_cross_file_correct_patch() -> None:
    """已知正确的补丁（gold fixed 全文）经新口径应判 repair=1.0。"""
    task = _cross_file_task()
    state = {"generated_test": _GOLD_TEST, "patch": _MODULE_B_FIXED, "test_passed": True}
    assert _compute_repair_rate(task, state) == 1.0


def test_repair_cross_file_wrong_patch_zero() -> None:
    """未修复的补丁（原缺陷码）应判 repair=0.0。"""
    task = _cross_file_task()
    state = {"generated_test": _GOLD_TEST, "patch": _MODULE_B_BUGGY, "test_passed": True}
    assert _compute_repair_rate(task, state) == 0.0


def test_false_fix_cross_file_after_fix() -> None:
    """正确补丁 + passed → 非假修复（false_fix=0.0）。"""
    task = _cross_file_task()
    state = {"generated_test": _GOLD_TEST, "patch": _MODULE_B_FIXED, "test_passed": True}
    assert _compute_false_fix_rate(task, state) == 0.0


def test_legacy_without_metadata_rc2() -> None:
    """向后兼容锁定：不传 task_metadata 时跨文件 gold 测试仍收集错误（rc=2）。

    这正是历史伪影现象本身；显式信号缺省（detection_gates 委托调用）
    时行为不变，说明修复未污染回退路径。
    """
    rc = _run_pytest_in_tmp(_GOLD_TEST, _MODULE_B_FIXED, "task_0002")
    assert rc is not None and rc[0] == 2


# ─── 物化不变量 ────────────────────────────────────────────────────────────


def test_materialize_tree_invariants(tmp_path) -> None:
    """伴生模块按 metadata 落盘；目标模块内容 = 传入 target_code；其余为缺陷原版。"""
    task = _cross_file_task()
    tmpdir = str(tmp_path / "run")
    Path(tmpdir).mkdir()
    test_path, pythonpath = _prepare_cross_file_test_tree(tmpdir, _MODULE_B_FIXED, _GOLD_TEST, task.metadata)
    root = Path(tmpdir)
    assert (root / "module_a.py").is_file()
    assert (root / "module_b.py").is_file()
    # 目标模块（module_b）= 传入 target_code（三态统一），非 metadata 缺陷原版
    assert (root / "module_b.py").read_text(encoding="utf-8") == _MODULE_B_FIXED
    # 伴生模块（module_a）= metadata 缺陷原版
    assert (root / "module_a.py").read_text(encoding="utf-8") == _MODULE_A
    # module_c 在双模块任务中代码为空 → 不落盘（与 _write_cross_file_modules 同口径）
    assert not (root / "module_c.py").exists()
    assert Path(test_path).is_file()
    assert pythonpath == tmpdir


def test_materialize_three_module_target_c(tmp_path) -> None:
    """三模块任务（L3.5）：target_module=module_c 时目标落点为 module_c。"""
    md: dict[str, Any] = {
        "source": "synthetic",
        "is_cross_file": True,
        "num_files": 3,
        "target_module": "module_c",
        "module_a_name": "module_a",
        "module_a_code": "from module_b import mid\n\n\ndef top():\n    return mid(1)\n",
        "module_b_name": "module_b",
        "module_b_code": "from module_c import leaf\n\n\ndef mid(x):\n    return leaf(x)\n",
        "module_c_name": "module_c",
        "module_c_code": "def leaf(x):\n    return x - 1\n",
        "fixed_module_code": "def leaf(x):\n    return x + 1\n",
        "test_cases": "from module_a import top\n\n\ndef test_top():\n    assert top() == 2\n",
    }
    tmpdir = str(tmp_path / "run")
    Path(tmpdir).mkdir()
    _prepare_cross_file_test_tree(tmpdir, md["fixed_module_code"], md["test_cases"], md)
    root = Path(tmpdir)
    assert (root / "module_a.py").is_file() and (root / "module_b.py").is_file()
    assert (root / "module_c.py").read_text(encoding="utf-8") == md["fixed_module_code"]


def test_run_pytest_cross_file_end_to_end() -> None:
    """端到端：跨文件物化后 gold 测试在 fixed 代码上全绿（修复前 rc=2）。"""
    task = _cross_file_task()
    rc = _run_pytest_in_tmp(_GOLD_TEST, _MODULE_B_FIXED, "task_0002", task_metadata=task.metadata)
    assert rc is not None and rc[0] == 0, f"跨文件 gold 测试应全绿，实际 rc={None if rc is None else rc[0]}"
