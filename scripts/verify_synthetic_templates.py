#!/usr/bin/env python
"""P0-5（2026-10-05 独立审查）：合成模板库批量自验证。

每个模板的三重不变量（子进程真实执行，零 LLM）：
1. gold 测试在 **buggy** 代码上至少一红（缺陷可检出——否则模板无信息量，
   会把"恒绿任务"混入 detection_rate 分母，稀释指标）；
2. gold 测试在 **fixed** 代码上全绿（gold 材料自洽——fixed 侧红则 M1 的
   F2P 第二段判据恒假，detection 恒 0）；
3. test_cases 的 def test_ 计数 == total_tests（口径自洽）。

背景：2026-10-05 独立审查 P0-5 扩容 20 模板时的验证发现 6/20 首版模板
存在"buggy 不红 / fixed 不红 / 测试数漂移"问题（banker's rounding 临界、
小整数缓存 is 判定、同秒 .pyc 陈旧字节码等陷阱）——模板正确性需要机制
化守卫而非人肉评审。

用法：
    python scripts/verify_synthetic_templates.py           # 全库验证
    python scripts/verify_synthetic_templates.py --pool BUG_PATTERNS
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

_POOLS = (
    "BUG_PATTERNS",
    "BUG_PATTERNS_LEVEL2",
    "BUG_PATTERNS_LEVEL25",
    "BUG_PATTERNS_LEVEL25HARD",
    "BUG_PATTERNS_LEVEL4",
    "BUG_PATTERNS_LEVEL45",
    "CROSS_FILE_PATTERNS",
    "CROSS_FILE_DEEP_PATTERNS",
)

# 跨文件模板的 test_cases import 的是 module_a/b/c 而非 pattern 名，
# fixed 判定需落盘伴生模块（与 run_benchmark._write_cross_file_modules 同构）
_CROSS_FILE_POOLS = ("CROSS_FILE_PATTERNS", "CROSS_FILE_DEEP_PATTERNS")


def _run_pytest(cwd: Path) -> tuple[int, str]:
    """在 cwd 下跑 pytest，返回 (returncode, 输出摘要)。"""
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "test_gold.py",
            "-q",
            "--no-header",
            "-p",
            "no:cacheprovider",
        ],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=180,
    )
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def verify_template(template: dict, *, is_cross_pool: bool = False) -> list[str]:
    """验证单模板，返回违规信息列表（空 = 通过）。

    跨文件池（CROSS_FILE_*）无 "template" 键——缺陷在被调方模块
    （num_files≥3 取 module_c_code，否则 module_b_code），fixed 侧取
    fixed_module_c_code / fixed_module_b_code，落盘为 target_module 名
    （与 synthetic_dataset._load_raw_data 的构造同构）。
    """
    problems: list[str] = []
    name = template["name"]
    test_text = template["test_cases"]
    n_tests = test_text.count("def test_")
    if n_tests != template.get("total_tests"):
        problems.append(f"测试数口径漂移：def test_ 计 {n_tests} vs total_tests={template.get('total_tests')}")

    if is_cross_pool:
        num_files = int(template.get("num_files", 2))
        target_module = template.get("target_module", "module_b")
        def_key = "module_c_code" if num_files >= 3 else "module_b_code"
        fixed_key = "fixed_module_c_code" if num_files >= 3 else "fixed_module_b_code"
        sides = (("buggy", template.get(def_key, "")), ("fixed", template.get(fixed_key, "")))
        companion_keys = ("module_a_code", "module_b_code", "module_c_code")
        main_name = target_module
    else:
        sides = (("buggy", template["template"]), ("fixed", template["fixed"]))
        companion_keys = ()
        main_name = name

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        for side, code in sides:
            (td_path / f"{main_name}.py").write_text(code, encoding="utf-8")
            for mk in companion_keys:
                # companion 落盘跳过 main_name：target 模块以 side 专属代码
                # 为准（companion 的 buggy 版会覆盖 fixed 版——首版验证器的
                # 落盘顺序 bug，曾把 type_mismatch/three_module 误报为 fixed 红）
                if mk.replace("_code", "") == main_name:
                    continue
                mc = template.get(mk)
                if mc:
                    (td_path / f"{mk.replace('_code', '')}.py").write_text(mc, encoding="utf-8")
            (td_path / "test_gold.py").write_text(test_text, encoding="utf-8")
            rc, out = _run_pytest(td_path)
            if side == "buggy" and rc == 0:
                problems.append("gold 测试在 buggy 代码上全绿（缺陷不可检出，模板无信息量）")
            if side == "fixed" and rc != 0:
                tail = out.strip().splitlines()[-1] if out.strip() else "no output"
                problems.append(f"gold 测试在 fixed 代码上失败（gold 材料不自洽）：{tail}")
            # 同秒覆盖源文件时清 __pycache__（mtime 粒度会让 fixed 侧复用 buggy 字节码）
            shutil.rmtree(td_path / "__pycache__", ignore_errors=True)
    return problems


def main() -> None:
    parser = argparse.ArgumentParser(description="合成模板库批量自验证（P0-5）")
    parser.add_argument("--pool", choices=_POOLS, default=None, help="仅验证指定池（默认全部）")
    args = parser.parse_args()

    import src.datasets.synthetic_dataset as ds

    pools = [args.pool] if args.pool else list(_POOLS)
    failed = 0
    total = 0
    for pool_name in pools:
        templates = getattr(ds, pool_name, [])
        for t in templates:
            total += 1
            problems = verify_template(t, is_cross_pool=pool_name in _CROSS_FILE_POOLS)
            if problems:
                failed += 1
                print(f"[BAD] {pool_name}/{t['name']}")
                for p in problems:
                    print(f"      - {p}")

    if failed:
        print(f"\n模板自验证失败：{failed}/{total} 个模板违规")
        raise SystemExit(1)
    print(f"模板自验证通过：{total}/{total}（buggy 可检出 + fixed 自洽 + 口径无漂移）")


if __name__ == "__main__":
    main()
