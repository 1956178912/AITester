"""P0 2.3：SWE-bench 源码导出质量验证脚本。

背景：
    scripts/export_swe_bench_source.py 产出 SWE_BENCH_ENRICHMENT 格式的
    enrichment JSONL（instance_id + instance_code）。本脚本对已生成的
    enrichment 文件做质量验证，输出"成功数/失败数/缺失文件列表"的导出
    质量报告，供论文附录 / 复现步骤引用。

验证维度（每个 instance）：
    1. 非空检查：instance_code 非空且非纯 issue 文本（问题描述长度远超
       源码行数 → 疑似兜底）。
    2. 目标函数存在性：官方 patch 提取的 suggested_function 是否出现在
       instance_code 中（函数级定位依赖）。
    3. 目标文件路径匹配：官方 patch 的 "+++ b/<path>" 行是否对应
       instance_code 的模块结构（import 行检查）。
    4. 行数合理性：instance_code 行数 >= 最低阈值（默认 5 行，小于 5 行
       视为"非真实源码"兜底标记）。
    5. Python 语法合法：instance_code 可被 ast.parse（排除半 diff 文本混入）。

使用方式：
    # 验证 data/swe_bench_lite_enriched.jsonl（项目内已有 enrichment）
    python scripts/verify_swe_bench_export.py \
        --enrichment data/swe_bench_lite_enriched.jsonl \
        --instances ~/.cache/aitester/swe_bench/swe_bench_lite_instances.jsonl \
        --output experiments/results/enrichment_quality_report.json

    # 仅验证非空 + 行数（快速，不读官方 JSONL）
    python scripts/verify_swe_bench_export.py --enrichment data/swe_bench_lite_enriched.jsonl
"""

from __future__ import annotations

import ast
import json
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import click

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger(__name__)

# ─── 验证阈值常量 ──────────────────────────────────────────────────────────
_MIN_SOURCE_LINES = 5  # 低于此行数视为"非真实源码"兜底（issue 文本 / 空文件）
_MAX_ISSUE_LINE_RATIO = 10  # issue 文本通常 < 200 行，源码 > 100 行
_ISSUE_FALLBACK_HEURISTIC_CHARS = 500  # issue 兜底文本特征：纯自然语言无 def/class
_TARGET_FUNC_RE = re.compile(r"^\s*def\s+(\w+)\s*\(")
_PATCH_TARGET_RE = re.compile(r"^\+\+\+ (?:b/)?(\S+)")


@dataclass
class InstanceVerification:
    """单个 instance 的验证结果。"""

    instance_id: str
    # 各维度检查结果（True = 通过）
    non_empty: bool = True
    line_count: int = 0
    has_python_syntax: bool = False
    contains_target_func: bool | None = None  # None = 无法判断（suggested_function 缺失）
    target_file_path: str | None = None
    is_issue_fallback: bool = False  # 疑似 issue 文本兜底（非真实源码）
    error: str = ""  # 附加错误信息
    _min_lines: int = _MIN_SOURCE_LINES  # 行数阈值（verify_enrichment_file 注入）

    @property
    def passed(self) -> bool:
        """综合判定：非空 + 行数达标 + 语法合法 + 非 issue 兜底。

        P0 审查修正：用实例字段 _min_lines（CLI 可经 --min-lines 覆盖），
        而非模块级 _MIN_SOURCE_LINES（此前 verify_enrichment_file 通过
        `global` 语句改写模块全局，导致同一解释器内多次不同阈值调用
        互相污染）。
        """
        return (
            self.non_empty
            and self.line_count >= self._min_lines
            and self.has_python_syntax
            and not self.is_issue_fallback
        )

    @property
    def score_label(self) -> str:
        if self.passed:
            return "OK"
        if self.is_issue_fallback:
            return "ISSUE_FALLBACK"
        if not self.has_python_syntax:
            return "SYNTAX_INVALID"
        if self.line_count < self._min_lines:
            return "TOO_SHORT"
        if not self.non_empty:
            return "EMPTY"
        return "UNKNOWN"


def _looks_like_issue_text(code: str) -> bool:
    """启发式判断 instance_code 是否为 issue 文本兜底（非真实源码）。

    特征（满足任一即判定）：
    - 无 def/class/import 关键字（纯自然语言）；
    - 长度 > 500 字符但无换行（issue 文本常为单段长字符串）；
    - 含典型 issue 标记（"Issue", "Bug", "Problem", 中文"问题"/"缺陷"）。
    """
    if not code or not code.strip():
        return True
    low = code.lower()
    has_python_marker = any(m in low for m in ("def ", "class ", "import ", "return ", "assert "))
    if not has_python_marker:
        return True  # 纯自然语言
    # 单段长字符串（无换行且 > 500 字符）→ 疑似 issue 兜底
    return "\n" not in code.strip() and len(code.strip()) > _ISSUE_FALLBACK_HEURISTIC_CHARS


def _check_python_syntax(code: str) -> bool:
    """instance_code 可被 ast.parse（排除半 diff 文本 / 乱码混入）。"""
    if not code:
        return False
    try:
        ast.parse(code)
        return True
    except (SyntaxError, ValueError):
        return False


def _check_target_function(code: str, suggested_function: str | None) -> bool | None:
    """suggested_function 是否出现在 instance_code 中。"""
    if not suggested_function:
        return None
    pattern = re.compile(rf"\bdef\s+{re.escape(suggested_function)}\s*\(")
    return bool(pattern.search(code))


def _check_target_file(code: str, patch_text: str) -> str | None:
    """从官方 patch 提取目标文件路径，验证 import 行是否匹配。"""
    if not patch_text:
        return None
    for line in patch_text.splitlines():
        m = _PATCH_TARGET_RE.match(line.strip())
        if not m:
            continue
        path = m.group(1)
        if path == "/dev/null":
            continue
        if "test_" in path or "tests/" in path or "_test" in path:
            continue
        return path
    return None


def verify_enrichment_file(
    enrichment_path: str | Path,
    instances_path: str | Path | None = None,
    min_lines: int = _MIN_SOURCE_LINES,
) -> list[InstanceVerification]:
    """验证 enrichment 文件中每个 instance 的源码导出质量。

    Args:
        enrichment_path: SWE_BENCH_ENRICHMENT 格式 JSONL 路径。
        instances_path: 官方 SWE-bench JSONL 路径（含 patch/suggested_function，
            提供时做目标函数 / 目标文件交叉验证）；None 时仅做非空/行数/语法检查。
        min_lines: 最低行数阈值。

    Returns:
        InstanceVerification 列表（按 instance_id 排序）。
    """
    # 读取 enrichment
    enriched: dict[str, str] = {}
    with open(enrichment_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                iid = row.get("instance_id", "")
                code = row.get("instance_code", "")
                if iid:
                    enriched[iid] = code
            except json.JSONDecodeError:
                continue

    # 读取官方 instances（可选，含 patch 字段）
    instance_patches: dict[str, str] = {}
    if instances_path:
        with open(instances_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    iid = row.get("instance_id", "")
                    patch = row.get("patch", "")
                    if iid:
                        instance_patches[iid] = patch
                except json.JSONDecodeError:
                    continue

    results: list[InstanceVerification] = []
    for iid in sorted(enriched.keys()):
        code = enriched[iid]
        v = InstanceVerification(instance_id=iid, _min_lines=min_lines)

        v.non_empty = bool(code and code.strip())
        v.line_count = len(code.splitlines()) if code else 0
        v.has_python_syntax = _check_python_syntax(code)
        v.is_issue_fallback = _looks_like_issue_text(code)

        # 目标文件路径
        patch = instance_patches.get(iid, "")
        v.target_file_path = _check_target_file(code, patch)

        # 目标函数交叉验证
        suggested_func = _extract_suggested_func_from_patch(patch)
        if suggested_func:
            v.contains_target_func = _check_target_function(code, suggested_func)
        else:
            v.contains_target_func = None

        if not v.passed:
            if v.is_issue_fallback:
                v.error = "疑似 issue 文本兜底（无 def/class/import 标记或纯自然语言）"
            elif not v.has_python_syntax:
                v.error = "Python 语法不合法（可能混入 diff 文本）"
            elif v.line_count < min_lines:
                v.error = f"行数 {v.line_count} < 最低阈值 {min_lines}"
            elif not v.non_empty:
                v.error = "instance_code 为空"

        results.append(v)

    return results


def _extract_suggested_func_from_patch(patch_text: str) -> str | None:
    """从官方 patch 提取目标函数名（hunk 头 @@ 行的上下文，保守匹配）。"""
    if not patch_text:
        return None
    for line in patch_text.splitlines():
        # 2026-09-26 全面审查（P2 正确性）：此前 `startswith("@@") or
        # startswith("@")` 与下方 `re.search("@@...")` 语义矛盾——
        # startswith("@") 会命中 diff 删除行里的装饰器（`-@decorator`
        # 行以 `@` 开头但非 hunk 头），产生误匹配。收紧为仅 hunk 头
        # `@@` 行，并统一用 split("@@", 2)[2] 提取尾部上下文
        # （与 dataset_loader._extract_suggested_function 同口径）。
        if line.startswith("@@"):
            parts = line.split("@@", 2)
            if len(parts) < 3:
                continue
            tail = parts[2].strip()
            if tail:
                fm = _TARGET_FUNC_RE.match(tail)
                if fm:
                    return fm.group(1)
    return None


def build_quality_report(verifications: list[InstanceVerification]) -> dict:
    """汇总验证结果为结构化质量报告。

    Returns:
        {"total": int, "passed": int, "failed": int, "pass_rate": float,
         "by_label": dict[str, int], "failed_instances": list[dict],
         "avg_line_count": float}
    """
    total = len(verifications)
    passed = sum(1 for v in verifications if v.passed)
    by_label: dict[str, int] = {}
    failed_instances: list[dict] = []
    for v in verifications:
        label = v.score_label
        by_label[label] = by_label.get(label, 0) + 1
        if not v.passed:
            failed_instances.append(
                {
                    "instance_id": v.instance_id,
                    "label": label,
                    "line_count": v.line_count,
                    "has_python_syntax": v.has_python_syntax,
                    "target_file_path": v.target_file_path,
                    "error": v.error,
                }
            )
    avg_lines = round(sum(v.line_count for v in verifications) / total, 1) if total else 0.0
    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": round(passed / total, 4) if total else 0.0,
        "by_label": by_label,
        "failed_instances": failed_instances,
        "avg_line_count": avg_lines,
    }


@click.command()
@click.option(
    "--enrichment",
    "-e",
    required=True,
    help="SWE_BENCH_ENRICHMENT 格式 JSONL 文件路径（必填）",
)
@click.option(
    "--instances",
    "-i",
    default=None,
    help="官方 SWE-bench JSONL 路径（含 patch 字段，可选，用于目标函数/文件交叉验证）",
)
@click.option(
    "--output",
    "-o",
    default=None,
    help="质量报告输出路径（JSON）；默认打印到 stdout",
)
@click.option(
    "--min-lines",
    default=5,
    type=int,
    help=f"最低行数阈值（默认 {_MIN_SOURCE_LINES}，低于此值判为'非真实源码'）",
)
def cli(
    enrichment: str,
    instances: str | None,
    output: str | None,
    min_lines: int,
) -> None:
    """P0 2.3：验证 SWE-bench 源码导出质量（成功数/失败数/缺失文件列表）。"""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    enrichment_path = Path(enrichment).expanduser()
    if not enrichment_path.exists():
        click.echo(f"错误: enrichment 文件不存在: {enrichment_path}", err=True)
        sys.exit(1)

    instances_path = Path(instances).expanduser() if instances else None

    logger.info("验证 enrichment: %s（%d 条 instance）", enrichment_path, min_lines)
    verifications = verify_enrichment_file(enrichment_path, instances_path, min_lines)
    report = build_quality_report(verifications)

    # 打印质量报告
    print("\n导出质量报告：")
    print(f"  总 instance 数: {report['total']}")
    print(f"  通过: {report['passed']}  失败: {report['failed']}  通过率: {report['pass_rate'] * 100:.1f}%")
    print(f"  平均行数: {report['avg_line_count']}")
    if report["by_label"]:
        print(f"  按标签: {json.dumps(report['by_label'], ensure_ascii=False)}")
    if report["failed_instances"]:
        print(f"  失败 instance（{len(report['failed_instances'])} 条）:")
        for fi in report["failed_instances"][:20]:
            print(
                f"    [{fi['label']}] {fi['instance_id']}  "
                f"lines={fi['line_count']}  syntax={fi['has_python_syntax']}  "
                f"path={fi['target_file_path'] or '-'}  {fi['error']}"
            )

    # 写报告
    if output:
        out_path = Path(output).expanduser()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\n质量报告已写入: {out_path}")
    else:
        print(f"\n{json.dumps(report, ensure_ascii=False, indent=2)}")


if __name__ == "__main__":
    cli()
