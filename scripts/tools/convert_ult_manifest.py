"""ULT（UnLeakedTestbench）官方数据 → 本项目逐行 JSONL manifest 转换脚本。

背景（2026-10-12 ULT 接线批次）：
    官方仓库（github.com/huangd1999/UnLeakedTestBench）的 datasets/ 目录
    提供三个数据文件（文件名 .jsonl 但内容为 **JSON 数组**，非逐行 JSONL）：
      - ULT.jsonl        全量 3,909 函数（tests 字段：list[str]，每函数 5 条
                         官方测试函数）
      - ULT_Lite.jsonl   官方 200 任务子集（test_list 字段：list[str] 断言片段）
      - PLT.jsonl        Pass@k 对照集 18,310 函数（test_input 字段：输入样本）

    本项目加载器 src/datasets/dataset_ult.py 自 2026-10-12 起已**直接兼容**
    官方 JSON 数组格式（无需转换即可用：AITESTER_ULT_DATA 指向官方
    datasets/ 目录，subset="lite" 指定 ULT_Lite.jsonl）。本脚本是
    旧式逐行 JSONL manifest 的**备用生成路径**（如需自定义字段裁剪、
    过滤、或给不支持 JSON 数组的下游工具喂数据时使用），行为：
      官方记录 {func_name, code, prompt, task_id, tests/test_list,
                cyclomatic_complexity}
        → 逐行 JSONL {function_name, source_code, signature, prompt,
                      test_cases, cyclomatic_complexity}

用法：
    python scripts/tools/convert_ult_manifest.py \\
        --source ~/.cache/aitester/ult_repo/datasets/ULT_Lite.jsonl \\
        --output ~/.cache/aitester/ult/ult_manifest.jsonl

    产出后经 AITESTER_ULT_DATA=<output 所在目录> 使用。
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path


def _first_function_name(code: str) -> str | None:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            return node.name
    return None


def _normalize_tests(value: object) -> list[str]:
    """官方 tests / test_list / test_input 字段 → list[str]。"""
    if isinstance(value, str):
        text = value.strip()
        if not text or text in ("[]", "null"):
            return []
        try:
            parsed = json.loads(text)
            value = parsed if isinstance(parsed, list) else [str(parsed)]
        except json.JSONDecodeError:
            value = [text]
    if not isinstance(value, list):
        return []
    return [str(v) for v in value if str(v).strip()]


def convert(source: Path, output: Path) -> int:
    raw = source.read_text(encoding="utf-8")
    data = json.loads(raw)  # 官方文件为 JSON 数组
    if not isinstance(data, list):
        print(f"[FAIL] {source} 顶层非数组（实际 {type(data).__name__}），无法转换", file=sys.stderr)
        return 1

    written = skipped = 0
    with output.open("w", encoding="utf-8") as f:
        for row in data:
            if not isinstance(row, dict):
                skipped += 1
                continue
            code = str(row.get("code") or "")
            if not code.strip():
                skipped += 1
                continue
            func_name = str(row.get("func_name") or "").strip() or _first_function_name(code) or ""
            complexity = row.get("cyclomatic_complexity")
            complexity = complexity if isinstance(complexity, int) and complexity >= 0 else None
            out_row = {
                "function_name": func_name,
                "source_code": code,
                "signature": "",
                "prompt": str(row.get("prompt") or ""),
                "test_cases": _normalize_tests(row.get("tests", row.get("test_list", row.get("test_input", [])))),
                "cyclomatic_complexity": complexity,
            }
            f.write(json.dumps(out_row, ensure_ascii=False, allow_nan=False) + "\n")
            written += 1
    print(f"[OK] {source.name} → {output}（{written} 条，跳过 {skipped} 条无效记录）")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="ULT 官方 JSON 数组数据 → 逐行 JSONL manifest 转换")
    parser.add_argument("--source", required=True, help="官方 ULT.jsonl / ULT_Lite.jsonl / PLT.jsonl 路径")
    parser.add_argument("--output", required=True, help="输出逐行 JSONL manifest 路径")
    args = parser.parse_args()
    source = Path(args.source).expanduser()
    output = Path(args.output).expanduser()
    if not source.exists():
        print(f"[FAIL] 源文件不存在: {source}", file=sys.stderr)
        return 1
    output.parent.mkdir(parents=True, exist_ok=True)
    return convert(source, output)


if __name__ == "__main__":
    raise SystemExit(main())
