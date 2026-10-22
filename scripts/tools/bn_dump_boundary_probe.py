"""BN 轮（2026-10-22）只读可达性探针：逐通道测量 status 在两道落盘边界上的可判别度。

两道边界都在 `experiments/run_benchmark.py`：
① `_dump_state_artifacts` 按**白名单**把环节级状态写进 `<output>/raw/<task_id>/<baseline>.json`；
② `_build_task_result` 的**结果行**（成功/失败两分支单一构造点）。

口径：对每个检查通道，只让该通道的取值在四值词汇（ok / error / unavailable / disabled）
之间变化、其余全部固定，比较落盘字节与行 `repr`。**几种运行时态折成几种形状**
就是该通道在该边界上的可判别度：1 种 ⇒ "检查完成且零疑点"与"检查崩了 / 没跑"事后不可区分。

①只写 `tempfile.mkdtemp()`，运行结束即删除；②全程内存。仓库零写入。
用法：.venv/bin/python scripts/tools/bn_dump_boundary_probe.py
"""

import pathlib
import shutil
import sys
import tempfile
from types import SimpleNamespace

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "experiments"))

import run_benchmark  # noqa: E402

from src.datasets.dataset_loader import BenchmarkTask  # noqa: E402

#: 通道名 → 该通道在 state 里的键（status 与明细 outcomes 成对发布）
CHANNELS: dict[str, tuple[str, ...]] = {
    "static_check": ("static_check_status", "static_check_outcomes"),
    "safety_check": ("safety_check_status", "safety_check_outcomes"),
    "oracle_check": ("oracle_check_status", "oracle_check_outcomes"),
    "contract": ("contract_status",),
}
STATUSES: tuple[str, ...] = ("ok", "error", "unavailable", "disabled")
ABSENT = "键不存在"

BASE_STATE: dict = {
    "test_plan": "plan",
    "generated_test": "def test_x():\n    assert 1\n",
    "diagnosis": "",
    "error_category": "",
    "patch": "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-old\n+new\n",
    "test_passed": True,
    "iteration": 1,
    "coverage_report": 0.5,
    "rag_stats": None,
    "position_aware_focus": None,
    "repo_verification": None,
    "cross_file_deps": None,
    "testless_validation": None,
    "deterministic_guard_report": None,
    "m10_leaf_fallback": None,
}


def outcomes(status: str) -> list[dict]:
    return [{"backend": "mypy", "status": status, "reason": "unrecognized arguments" if status == "error" else ""}]


def variant(keys: tuple[str, ...], status: str | None) -> dict:
    """同一份运行结果，只让 keys 通道携带 status；status=None 表示这些键根本不存在。"""
    state = dict(BASE_STATE)
    if status is None:
        return state
    for key in keys:
        state[key] = outcomes(status) if key.endswith("_outcomes") else status
    return state


def variant_all(status: str | None) -> dict:
    keys = tuple(k for channel in CHANNELS.values() for k in channel)
    return variant(keys, status)


def row_task() -> BenchmarkTask:
    return BenchmarkTask(
        task_id="probe__task",
        repo_name="probe/task",
        problem_statement="fix a bug",
        instance_code="def f():\n    return 1\n",
        test_code="def test_f():\n    assert f() == 1\n",
        expected_pass_count=0,
        total_test_count=1,
        metadata={"source": "bn-probe"},
    )


def dump(state: dict, out_dir: pathlib.Path) -> bytes:
    task = SimpleNamespace(task_id="probe__task", metadata={"difficulty": "easy"})
    run_benchmark._dump_state_artifacts(str(out_dir), task, "aitester", state)
    return (out_dir / "raw" / "probe__task" / "aitester.json").read_bytes()


def group(blobs: dict[str, object]) -> dict[object, list[str]]:
    out: dict[object, list[str]] = {}
    for label, blob in blobs.items():
        out.setdefault(blob, []).append(label)
    return out


def main() -> None:
    out_dir = pathlib.Path(tempfile.mkdtemp(prefix="bn_dump_boundary_"))
    try:
        states = {s: variant_all(s) for s in STATUSES}
        states[ABSENT] = variant_all(None)

        print("① 归档边界（`_dump_state_artifacts` 白名单 → raw/<task_id>/<baseline>.json）")
        blobs = {label: dump(state, out_dir) for label, state in states.items()}
        shapes = group(blobs)
        print(f"  全通道合测：运行时 {len(states)} 态 → 归档 {len(shapes)} 形状")
        for i, (blob, labels) in enumerate(shapes.items(), 1):
            print(f"    形状{i}（{len(blob)} 字节）← {labels}")
        text = blobs["ok"].decode()
        present = [k for ch in CHANNELS.values() for k in ch if f'"{k}"' in text]
        print(f"  工件中出现的通道键：{present or '无（全部不在白名单内）'}")

        print("\n② 结果行边界（`_build_task_result` 成功分支，全程内存）")
        rows = {
            label: repr(run_benchmark._build_task_result(row_task(), 1.0, final_state=state))
            for label, state in states.items()
        }
        row_shapes = group(rows)
        print(f"  全通道合测：运行时 {len(states)} 态 → 行 {len(row_shapes)} 形状")
        for i, (blob, labels) in enumerate(row_shapes.items(), 1):
            print(f"    行形状{i}（{len(blob)} 字符）← {labels}")
        row_text = rows["ok"]
        row_present = [k for ch in CHANNELS.values() for k in ch if k in row_text]
        print(f"  结果行中出现的通道键：{row_present or '无（两分支均未透出）'}")

        print("\n③ 逐通道可判别度（只让该通道变化，其余固定）")
        print(f"  {'通道':<14}{'工件形状':>10}{'行形状':>10}  通道键落盘情况")
        for channel, keys in CHANNELS.items():
            per_blobs = {s: dump(variant(keys, s), out_dir) for s in STATUSES}
            per_blobs[ABSENT] = dump(variant(keys, None), out_dir)
            per_rows = {
                s: repr(run_benchmark._build_task_result(row_task(), 1.0, final_state=variant(keys, s)))
                for s in STATUSES
            }
            per_rows[ABSENT] = repr(run_benchmark._build_task_result(row_task(), 1.0, final_state=variant(keys, None)))
            in_artifact = [k for k in keys if f'"{k}"' in per_blobs["ok"].decode()]
            in_row = [k for k in keys if k in per_rows["ok"]]
            reach = f"工件{in_artifact or '无'} / 行{in_row or '无'}"
            print(f"  {channel:<14}{len(group(per_blobs)):>12}{len(group(per_rows)):>10}  {reach}")

        print("\n④ 失败分支对照（final_state=None）")
        fail_row = repr(run_benchmark._build_task_result(row_task(), 1.0, diagnosis="执行异常", error_category="error"))
        fail_present = [k for ch in CHANNELS.values() for k in ch if k in fail_row]
        print(f"  失败行字符数 {len(fail_row)}，其中通道键出现：{fail_present or '无'}")
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)
        print("\n临时目录已删除，仓库零写入")


if __name__ == "__main__":
    main()
