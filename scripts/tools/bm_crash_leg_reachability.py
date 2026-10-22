"""BM 轮（2026-10-22）只读复算：污染等级崩溃腿的真实可达性与取值域。

不改任何仓库文件；只在进程内调用函数并捕获异常（导入腿为 sys.modules 投毒，人工构造）。
用法：.venv/bin/python scripts/tools/bm_crash_leg_reachability.py
"""

import collections
import logging
import os
import pathlib
import sys
import traceback

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
logging.disable(logging.DEBUG)

from experiments.contamination_check import _combined_risk_level, patch_semantic_similarity  # noqa: E402
from experiments.run_benchmark import _compute_contamination_risk_level  # noqa: E402

GOLD = "+def f(x):\n+    return x + 1\n"
GRID = [
    ("str 普通等价", GOLD, GOLD),
    ("str 单落单 surrogate", "+x = '\ud800'\n", GOLD),
    ("str NUL 字节", "+x = \x00\n", GOLD),
    ("str fenced 代码块", "```python\n+def f(): pass\n```", GOLD),
    ("str 真 git diff", "diff --git a/b.py b/b.py\nindex 1..2\n@@ -1 +1 @@\n-a\n+b\n", GOLD),
    ("str 深嵌套括号", "+foo(" + "(" * 200000 + ")" * 200000 + ")\n", GOLD),
    ("str 超长单 token", "+" + "a" * 200000 + "\n", GOLD),
    ("str 巨量行", "\n".join(f"+tok{i} = {i}" for i in range(20000)) + "\n", GOLD),
    ("str 前导零数字", "+x = 0755\n", GOLD),
    ("str 全非修改行", " context only\n another\n", GOLD),
    ("bytes 补丁", b"+def f(x):\n+    return x\n", GOLD),
    ("list 补丁", ["+def f(): pass"], GOLD),
    ("dict 补丁", {"patch": "+x"}, GOLD),
    ("int 补丁", 123, GOLD),
    ("str 黄金 + 非 str 生成（反向）", "+x = 1\n", ["+x = 1\n"]),
]


def grid(caliber: str) -> None:
    if caliber == "none":
        os.environ["EMBEDDING_BACKEND"] = "none"
    else:
        os.environ.pop("EMBEDDING_BACKEND", None)
    print(f"\n== 栅格（语义腿口径 = {caliber}）：包装器实算 vs try 体内联复算 ==")
    rows = []
    for name, gen, gold in GRID:
        got = _compute_contamination_risk_level({"task_id": "t", "patch": gen}, {"t": gold})
        exc = None
        where = ""
        try:
            _combined_risk_level(patch_semantic_similarity(gen, gold))
        except BaseException as e:
            exc = f"{type(e).__name__}: {str(e)[:70]}"
            tb = traceback.extract_tb(sys.exc_info()[2])
            where = f"{os.path.basename(tb[-1].filename)}:{tb[-1].lineno} {tb[-1].name}"
        rows.append((name, got, exc, where))
        print(f"  [{name}] 包装器→{got!r} | 体内联→{exc or 'no-raise'} | {'崩溃腿' if exc else '正常腿'} {where}")
    print("\n== 统计 ==")
    print("  包装器返回分布:", dict(collections.Counter(r[1] for r in rows)))
    print("  崩溃腿触发条数:", sum(1 for r in rows if r[2]), "/", len(rows))
    print("  崩溃腿触发输入:", [r[0] for r in rows if r[2]])
    print("  判优(low) 且来自崩溃腿:", [r[0] for r in rows if r[2] and r[1] == "low"])


def domain() -> None:
    print("\n== 取值域 ==")
    print("  _combined_risk_level({}) →", _combined_risk_level({}))
    print("  patch_semantic_similarity 键:", sorted(patch_semantic_similarity("+a\n", "+a\n")))
    print("  该返回值里 jaccard 类型:", type(patch_semantic_similarity("+a\n", "+a\n")["jaccard"]).__name__)


def import_leg() -> None:
    print("\n== 导入腿（sys.modules 投毒，人工构造）==")
    key = "experiments.contamination_check"
    sys.modules[key] = None
    try:
        got = _compute_contamination_risk_level({"task_id": "t", "patch": "+a\n"}, {"t": "+a\n"})
        print("  投毒后包装器返回:", repr(got))
    except BaseException as e:
        print("  投毒后包装器抛出:", type(e).__name__)
    del sys.modules[key]


grid("none")
grid("embedding")
domain()
import_leg()
print("\n  归档普查不在本脚本：行级档位 × patch 形状由 bm_archive_level_patch_census.py 独占（同一读数只留一处口径）。")
