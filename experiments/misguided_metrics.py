#!/usr/bin/env python3
"""misguided/effective 逐测试三分度量（ISSTA'26 操作化，零 LLM 重放）。

动机（独立评审 §6 P1 / §10 A-05，2026-10-17 L 轮 T2）
========================================================
项目此前的机制侧信号只有 ``over_red`` **proxy**（特异性门 verdict：生成测试
在 gold 修复代码上仍红 = 过红）。它是任务级、二值、且与"红得是否针对缺陷"
不区分——无法回答"生成测试里有多少条在断言**缺陷行为**（misguided），
多少条真正**区分缺陷版与修复版**（effective）"。

Zhao, Zhou & Cohen（ISSTA 2026，DOI 10.1145/3832204；引用口径取自
``docs/reviews/INDEPENDENT_SYSTEMATIC_REVIEW_2026-10-17.md`` §4.5/§6 P1，
本工具不复制其任何数字到本项目口径）把测试相对缺陷的行为二分为：

    effective = 在缺陷版（buggy）上失败 ∧ 在修复版（fixed）上通过
                 —— 真正"抓住"了缺陷
    misguided = 在缺陷版上通过 ∧ 在修复版上失败
                 —— 把缺陷行为当成期望行为（测试把 bug 固化成了规格）
    其余两类（both_pass / both_fail）不是缺陷信号（刻画性 / 无效测试）。

本工具把该定义落地为**可复算的零 LLM 重放**：读 ``run_benchmark`` /
``run_main_batch`` 的批次 JSON 工件，用其中归档的 ``generated_test``（LLM
生成的 pytest 文件全文）与 ``task_metadata.fixed``（gold 修复版源码），
配合数据目录里的缺陷版源码，对每个任务**各跑一次** buggy / fixed 两侧的
完整 pytest 文件（``--junitxml`` 取逐测试结果），再按 pytest node id 做
四分类。**不调用任何 LLM、不联网**，只跑本地 pytest 子进程。

口径纪律（必须与实现逐条对齐，详见 docs/design/misguided_effective_metric.md）
--------------------------------------------------------------------------
1. **执行布局 = 生产执行口径的忠实镜像（双布局）**：每次运行把目标模块同时
   写成根目录 ``{module}.py``（生产执行沙箱的平铺口径，Generator 的生成测试
   按此写 ``from {module} import ...``）与 ``python_programs/{module}.py``
   （QuixBugs 官方包结构口径），并复制同目录其它程序（如 ``node.py``）——
   与 ``experiments/_m1_metrics.py::_prepare_packaged_test_tree`` 的双布局
   历史修复同源（ADR-0033 第四起测量伪影：只物化一种布局会让合法 import
   被误判成"没跑起来"）。
2. **两侧各一次整文件 pytest**（效率优先）：先用 ``--collect-only`` 取 node id
   清单并定位收集错误，再跑一次整文件 ``--junitxml`` 取逐测试结果；不做
   "逐测试起进程"。
3. **超时与红区分**：可用 pytest-timeout 时追加 ``--timeout=N
   --timeout-method=signal``（单条挂死测试被单独判失败并**标记为 timeout，
   不进入可分类分母**）；另设整文件墙钟上限（``run_with_timeout`` +
   ``start_new_session``/killpg，防"超时后孙进程持管道导致永久阻塞"）。
   收集失败 / import 失败 / 语法错误 / 超时 / skipped 一律单列
   （不可分类原因计数），**不得**并进 both_fail 冒充"测试红"。
4. **嵌套 pytest 环境**：子进程 env 经
   ``src/utils/process_utils.nested_pytest_env`` 构造（剔除宿主
   ``PYTEST_PLUGINS``/``PYTEST_ADDOPTS``）——H2 教训：否则宿主 pytest 配置
   能让结论与被测代码无关。另固定 ``PYTHONHASHSEED=0`` 抑制哈希随机化。
5. **确定性**：报告 body 不含时间戳/墙钟耗时（这些只进 ``run_meta``），
   ``--repeat`` 重复重放并比较 body digest；同一输入工件在无外部随机源时
   逐位一致。若某生成测试自身使用未播种随机源，重放差异会**如实列进
   ``run_meta.determinism``**，不做静默平均。
6. **分母披露（强制）**：报告同时给出 总收集测试数 / 可分类测试数 /
   任务数（含结构跳过任务的原因分布），以及"每任务可分类数"的分布；
   任何比率都标注其分母。

输出
----
``--out`` 目录下写 ``MISGUIDED_REPORT.json`` + ``MISGUIDED_REPORT.md``；
报告含输入工件 sha256、运行命令、时间戳、
逐任务明细（含每条测试的 buggy/fixed 结果与分类）、臂级汇总、与归档
``detection_rate`` / ``specificity_gate_verdict`` / ``passed`` 的交叉校验表。

用法示例::

    .venv/bin/python -m experiments.misguided_metrics \\
        --artifact experiments/results/emse_df_spec_20261016/benchmark_quixbugs_20261017_003023.json \\
        --artifact experiments/results/emse_df_spec_20261016/benchmark_quixbugs_20261016_232138.json \\
        --out experiments/results/emse_misguided_20261017 \\
        --jobs 8 --repeat 2

已知限制（报告与设计文档同步披露）
----------------------------------
- 生成测试之间的**全局状态污染**照旧存在（同一文件内按 pytest 收集顺序执行，
  顺序本身是测量对象的一部分）；只做隔离到"每个版本一个临时目录"。
- 官方金测试（``task_metadata.test_cases``）**不参与**本分类；仅用于交叉
  校验任务级 ``detection_rate``（M1 口径）。两者交互见设计文档。
- 9 个 QuixBugs ``*_test`` 驱动任务（相对 import、无官方金测试）在平铺
  执行口径下无法 import → 结构跳过（与归档 ``detection=None`` 同源）。
- 描述性度量：本报告**不是**预注册确认性证据；不提供显著性推断。
"""

from __future__ import annotations

import argparse
import ast
import concurrent.futures
import hashlib
import json
import math
import os
import re
import shutil
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.utils.atomic_io import atomic_write_json, atomic_write_text  # noqa: E402
from src.utils.process_utils import nested_pytest_env, run_with_timeout  # noqa: E402

SCHEMA_VERSION = "misguided_effective_metric/1"
TOOL_NAME = "experiments.misguided_metrics"
TOOL_VERSION = "1.0.0"

# 四分类（ISSTA'26 操作化；覆盖全部可分类测试）
CLASSES: tuple[str, ...] = ("effective", "misguided", "both_pass", "both_fail")
CLASS_DEFINITIONS: dict[str, str] = {
    "effective": "buggy 失败 ∧ fixed 通过（真正区分缺陷版与修复版）",
    "misguided": "buggy 通过 ∧ fixed 失败（把缺陷行为断言成期望行为）",
    "both_pass": "两侧都通过（零检出信号的刻画性测试）",
    "both_fail": "两侧都失败（在正确代码上即失败 → 测试自身无效/恒红）",
}
# 不可分类原因（单列；绝不并入四分类分母之外的任何一类）
UNCLASSIFIABLE_REASONS: tuple[str, ...] = (
    "timeout",  # 单测/整文件超时（pytest-timeout 或墙钟）
    "collect_error",  # pytest 收集中断（rc>=2，非 import/语法可归因）
    "import_error",  # 收集期 ModuleNotFoundError / ImportError（含相对 import 失败）
    "syntax_error",  # 生成测试文件语法错误
    "skipped",  # pytest.skip / xfail：无 pass/fail 信号
    "test_error",  # setup/teardown 或测试执行期 error（非断言失败）
    "missing_side",  # 该 node 只在一侧出现（另一侧无结果）
    "unknown",  # 其余不可判定（保守）
)
# 任务级结构跳过原因（不可产出可分类测试）
STRUCTURAL_REASONS: tuple[str, ...] = (
    "artifact_row_malformed",
    "invalid_program_name",
    "missing_buggy_source",
    "buggy_source_unparseable",
    "buggy_source_validation_failed",
    "missing_fixed_material",
    "fixed_material_unparseable",
    "empty_generated_test",
    "generated_test_syntax_error",
    "no_tests_collected",
    "import_error",
    "syntax_error",
    "collect_error",
    "file_timeout",
    "exec_unknown",
    "no_classifiable_tests",
    "materialize_failed",
    "unknown",
)

TEST_FILENAME = "test_generated.py"
# 与 _m1_metrics 同源探针：pytest-timeout 是否可被当前解释器加载
_TIMEOUT_FAILURE_RE = re.compile(r"from pytest-timeout|Timeout \(>")
_MISSING_MODULE_RE = re.compile(r"ModuleNotFoundError|No module named")
_RELATIVE_IMPORT_RE = re.compile(r"attempted relative import")
_IMPORT_ERROR_RE = re.compile(
    r"ModuleNotFoundError|ImportError|No module named|attempted relative import|"
    r"cannot import name|ImportError while importing test module",
)
_SYNTAX_ERROR_RE = re.compile(r"SyntaxError|invalid syntax")
_VERBOSE_RE = re.compile(r"^(?P<node>\S+?::\S+?)\s+(?P<out>PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)\b")
_VERBOSE_OUTCOMES: dict[str, str] = {
    "PASSED": "pass",
    "FAILED": "fail",
    "ERROR": "error",
    "SKIPPED": "skip",
    "XFAIL": "skip",
    "XPASS": "pass",
}
# 报告 digest/重复运行比较时剔除的易变键（时间戳/墙钟；不含任何计数/分类）
_VOLATILE_KEYS: frozenset[str] = frozenset(
    {
        "generated_at",
        "started_at",
        "finished_at",
        "wall_s",
        "total_wall_s",
        "duration_s",
        "elapsed_s",
        "timing",
    }
)
_PY_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


# ─── 基础工具 ──────────────────────────────────────────────────────────────
def _now_iso() -> str:
    """当前 UTC 时间戳（ISO 8601，秒级；报告时间戳口径）。"""
    return datetime.now(UTC).isoformat(timespec="seconds")


def sha256_bytes(data: bytes) -> str:
    """bytes 的 sha256 十六进制摘要。"""
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    """文本（UTF-8）的 sha256 十六进制摘要。"""
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: str | os.PathLike[str]) -> str:
    """文件的 sha256 十六进制摘要（流式读取，大工件友好）。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_json(obj: Any) -> str:
    """规范化 JSON 文本（键排序 + 紧凑分隔符；digest/逐位比较口径）。"""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def strip_volatile(obj: Any) -> Any:
    """递归剔除易变键（时间戳/墙钟），用于确定性 digest 与重复运行比较。"""
    if isinstance(obj, dict):
        return {k: strip_volatile(v) for k, v in obj.items() if k not in _VOLATILE_KEYS}
    if isinstance(obj, list):
        return [strip_volatile(v) for v in obj]
    return obj


def body_digest(body: dict[str, Any]) -> str:
    """报告 body 的确定性摘要（剔除易变字段后规范化 JSON 的 sha256）。"""
    return sha256_text(canonical_json(strip_volatile(body)))


def _diff_paths(a: Any, b: Any, *, path: str = "", limit: int = 40) -> list[str]:
    """比较两个 JSON 结构，返回差异路径列表（最多 limit 条，深度优先）。"""
    diffs: list[str] = []

    def walk(x: Any, y: Any, cur: str) -> None:
        if len(diffs) >= limit:
            return
        if type(x) is not type(y):
            diffs.append(f"{cur}: type {type(x).__name__} != {type(y).__name__}")
            return
        if isinstance(x, dict):
            for key in sorted(set(x) | set(y)):
                if key not in x:
                    diffs.append(f"{cur}/{key}: 仅第二次运行存在")
                elif key not in y:
                    diffs.append(f"{cur}/{key}: 仅第一次运行存在")
                else:
                    walk(x[key], y[key], f"{cur}/{key}")
            return
        if isinstance(x, list):
            if len(x) != len(y):
                diffs.append(f"{cur}: 长度 {len(x)} != {len(y)}")
                return
            for i, (xi, yi) in enumerate(zip(x, y, strict=False)):
                walk(xi, yi, f"{cur}[{i}]")
            return
        if x != y:
            diffs.append(f"{cur}: {x!r} != {y!r}")

    walk(a, b, path or "$")
    return diffs


def _quantile(sorted_vals: list[float], q: float) -> float | None:
    """线性插值分位数（numpy 默认口径；空列表 → None）。"""
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return round(float(sorted_vals[0]), 6)
    pos = q * (len(sorted_vals) - 1)
    lo = math.floor(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = pos - lo
    return round(float(sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac), 6)


def _summary(vals: list[float]) -> dict[str, Any]:
    """数值分布摘要（mean/median/min/max/q1/q3；空 → n=0 + None）。"""
    if not vals:
        return {"n": 0, "mean": None, "median": None, "min": None, "max": None, "q1": None, "q3": None}
    s = sorted(vals)
    return {
        "n": len(s),
        "mean": round(float(sum(s)) / len(s), 6),
        "median": _quantile(s, 0.5),
        "min": round(float(s[0]), 6),
        "max": round(float(s[-1]), 6),
        "q1": _quantile(s, 0.25),
        "q3": _quantile(s, 0.75),
    }


def _display_path(path: Path) -> str:
    """展示用路径：仓库内文件用相对路径（报告可移植），否则绝对路径。"""
    try:
        return str(path.resolve().relative_to(REPO))
    except (ValueError, OSError):
        return str(path.resolve())


def _truncate(text: str, limit: int = 500) -> str:
    """截断错误详情（报告不贴全量 traceback，仅留可定位尾部）。"""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return "…" + text[-limit:]


# ─── 异常 ────────────────────────────────────────────────────────────────
class MisguidedMetricsError(Exception):
    """本工具的可预期错误（CLI 捕获后以非零码退出，不打印 traceback）。"""


class ArtifactError(MisguidedMetricsError):
    """批次工件 JSON 结构/字段不合法。"""


class MaterialError(MisguidedMetricsError):
    """任务材料不可用（缺失/校验失败）；带原因码。"""

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


# ─── 批次工件读取 ──────────────────────────────────────────────────────────
def load_artifact(path: Path) -> dict[str, Any]:
    """读取批次 JSON 工件并做最小结构校验。

    Args:
        path: benchmark JSON 路径。

    Returns:
        顶层 dict（含 ``results`` 字段）。

    Raises:
        ArtifactError: 文件不存在/非 JSON/顶层缺 ``results`` dict。
    """
    if not path.is_file():
        raise ArtifactError(f"工件不存在: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise ArtifactError(f"工件无法解析为 JSON: {path}: {e}") from e
    if not isinstance(data, dict):
        raise ArtifactError(f"工件顶层不是 JSON 对象: {path}")
    results = data.get("results")
    if not isinstance(results, dict) or not results:
        raise ArtifactError(f"工件缺 results.<arm>.details 结构: {path}")
    return data


def list_artifact_arms(artifact: dict[str, Any]) -> list[str]:
    """列出工件内的臂名（按名称排序，确定性）。"""
    results = artifact.get("results") or {}
    return sorted(str(k) for k in results)


def select_rows(artifact: dict[str, Any], arm: str) -> list[dict[str, Any]]:
    """取某臂的 details 行（保持归档顺序；调用方可再排序）。

    Raises:
        ArtifactError: 臂不存在或 details 不是 list。
    """
    results = artifact.get("results") or {}
    if arm not in results:
        raise ArtifactError(f"工件内不存在臂 {arm!r}（可用: {list_artifact_arms(artifact)}）")
    arm_obj = results[arm]
    if not isinstance(arm_obj, dict):
        raise ArtifactError(f"results.{arm} 不是对象")
    details = arm_obj.get("details")
    if not isinstance(details, list):
        raise ArtifactError(f"results.{arm}.details 不是数组")
    return [row for row in details if isinstance(row, dict)]


def _as_float_or_none(value: Any) -> float | None:
    """把工件的 detection_rate 等字段安全归一为 float/None（"None"/缺失/NaN → None）。"""
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        v = float(value)
        return None if math.isnan(v) else v
    text = str(value).strip()
    if not text or text.lower() in {"none", "null", "nan"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _as_bool_or_none(value: Any) -> bool | None:
    """把工件的 passed 等字段安全归一为 bool/None。"""
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None


# ─── QuixBugs 缺陷版源码解析与校验 ─────────────────────────────────────────
def resolve_quixbugs_roots(explicit: str | None = None) -> list[Path]:
    """缺陷版源码候选根目录（按优先级）。

    顺序（与任务书口径一致）：``--quixbugs-root`` 显式覆盖 →
    项目默认缓存 ``~/.cache/aitester/quixbugs`` → 仓库内 ``data/quixbugs`` →
    环境变量 ``AITESTER_QUIXBUGS_DATA``。每个根目录下按 ``python_programs/``
    子目录查找；根目录本身名为 ``python_programs`` 时直接使用。
    """
    roots: list[Path] = []
    if explicit:
        roots.append(Path(explicit).expanduser())
    roots.append(Path.home() / ".cache" / "aitester" / "quixbugs")
    roots.append(REPO / "data" / "quixbugs")
    env_root = os.environ.get("AITESTER_QUIXBUGS_DATA", "").strip()
    if env_root:
        roots.append(Path(env_root).expanduser())
    # 去重（保持顺序）
    seen: set[str] = set()
    out: list[Path] = []
    for root in roots:
        key = str(root)
        if key in seen:
            continue
        seen.add(key)
        out.append(root)
    return out


def _python_programs_dir(root: Path) -> Path:
    """根目录 → 承载 ``*.py`` 程序的目录（兼容根目录即 python_programs）。"""
    if root.name == "python_programs":
        return root
    return root / "python_programs"


def resolve_buggy_source(program: str, roots: list[Path]) -> tuple[str, Path]:
    """按优先级解析缺陷版源码文件（``python_programs/<program>.py``）。

    Args:
        program: 程序名（模块名）。
        roots: ``resolve_quixbugs_roots`` 返回的候选根目录。

    Returns:
        (源码全文, 命中的文件路径)。

    Raises:
        MaterialError: ``missing_buggy_source``（列出已查路径）。
    """
    checked: list[str] = []
    for root in roots:
        candidate = _python_programs_dir(root) / f"{program}.py"
        checked.append(str(candidate))
        if candidate.is_file():
            try:
                code = candidate.read_text(encoding="utf-8")
            except OSError as e:
                raise MaterialError("missing_buggy_source", f"读取失败 {candidate}: {e}") from e
            return code, candidate
    raise MaterialError(
        "missing_buggy_source",
        f"未找到 python_programs/{program}.py；已查: {checked[:6]}",
    )


def validate_buggy_source(
    buggy_code: str,
    program: str,
    task_metadata: dict[str, Any],
    dataset_fixed: str | None,
) -> dict[str, Any]:
    """校验缺陷版源码与工件任务一致（失败即 raise，不静默）。

    校验项（全部为可复算的硬条件）：
    1. 文件非空且可 ``ast.parse``；
    2. 若工件 ``task_metadata.suggested_function`` 在场：该名字必须是缺陷版
       顶层函数（工件由同一缺陷版派生）；
    3. 若数据目录存在 ``correct_python_programs/<program>.py`` 且工件
       ``task_metadata.fixed`` 非空：二者（strip 后）必须一致——证明本机
       checkout 与工件材料同源，buggy/fixed 配对可信（不一致 → fail-closed）。

    Returns:
        校验旁证 dict（含 ``fixed_material_matches_dataset`` 三态）。

    Raises:
        MaterialError: ``buggy_source_unparseable`` /
            ``buggy_source_validation_failed``。
    """
    if not buggy_code.strip():
        raise MaterialError("buggy_source_unparseable", "缺陷版源码为空")
    try:
        tree = ast.parse(buggy_code)
    except SyntaxError as e:
        raise MaterialError("buggy_source_unparseable", f"缺陷版源码语法错误: {e}") from e
    top_funcs = {node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    suggested = str(task_metadata.get("suggested_function") or "").strip()
    if suggested and suggested not in top_funcs:
        raise MaterialError(
            "buggy_source_validation_failed",
            f"工件 suggested_function={suggested!r} 不在缺陷版顶层函数中"
            f"（前缀: {sorted(top_funcs)[:5]}）——缺陷版源码与工件任务不匹配",
        )
    fixed_material = str(task_metadata.get("fixed") or "")
    flags: dict[str, Any] = {
        "suggested_function": suggested or None,
        "suggested_function_found": bool(suggested) and suggested in top_funcs,
        "fixed_material_matches_dataset": None,
    }
    if dataset_fixed is not None and fixed_material.strip():
        flags["fixed_material_matches_dataset"] = dataset_fixed.strip() == fixed_material.strip()
        if not flags["fixed_material_matches_dataset"]:
            raise MaterialError(
                "buggy_source_validation_failed",
                f"工件 task_metadata.fixed 与数据目录 correct_python_programs/{program}.py 不一致"
                "——无法确认缺陷版源码与工件同源（fail-closed）",
            )
    return flags


def dataset_fixed_source(program: str, roots: list[Path]) -> str | None:
    """数据目录中的修复版源码（用于同源校验；缺失 → None，不阻断）。"""
    for root in roots:
        candidate = root / "correct_python_programs" / f"{program}.py"
        if candidate.is_file():
            try:
                return candidate.read_text(encoding="utf-8")
            except OSError:
                return None
    return None


def collect_siblings(buggy_path: Path) -> dict[str, str]:
    """收集缺陷版同目录全部 Python 程序（用于物化依赖，如 ``node.py``）。"""
    siblings: dict[str, str] = {}
    directory = buggy_path.parent
    try:
        entries = sorted(directory.glob("*.py"))
    except OSError:
        return siblings
    for entry in entries:
        if entry.name == buggy_path.name:
            continue
        try:
            siblings[entry.name] = entry.read_text(encoding="utf-8")
        except OSError:
            continue
    return siblings


# ─── 物化（双布局）与 pytest 子进程执行 ────────────────────────────────────
def materialize_version(
    version_dir: Path,
    program: str,
    target_code: str,
    generated_test: str,
    siblings: dict[str, str],
) -> None:
    """物化一个被测版本目录（平铺 + 包结构双布局，生产/官方 import 均可解析）。

    目录形态::

        version_dir/
          conftest.py                     # pytest.use_correct=False / run_slow=False
          {program}.py                    # 平铺口径（生产执行沙箱）：本版本源码
          {其它程序}.py                   # 依赖（如 node.py）
          python_programs/__init__.py
          python_programs/{program}.py    # QuixBugs 官方包结构口径：本版本源码
          python_programs/{其它程序}.py
          test_generated.py               # 归档 generated_test 原文

    只写临时目录，不触碰数据目录与工件；失败抛 OSError 由调用方归因为
    ``materialize_failed``。
    """
    version_dir.mkdir(parents=True, exist_ok=True)
    package_dir = version_dir / "python_programs"
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "__init__.py").write_text("", encoding="utf-8")
    (version_dir / "conftest.py").write_text(
        "import pytest\n\npytest.use_correct = False\npytest.run_slow = False\n",
        encoding="utf-8",
    )
    for name, code in sorted(siblings.items()):
        if name == "__init__.py":
            continue
        (version_dir / name).write_text(code, encoding="utf-8")
        (package_dir / name).write_text(code, encoding="utf-8")
    (version_dir / f"{program}.py").write_text(target_code, encoding="utf-8")
    (package_dir / f"{program}.py").write_text(target_code, encoding="utf-8")
    (version_dir / TEST_FILENAME).write_text(generated_test, encoding="utf-8")


def pytest_timeout_available() -> bool:
    """pytest-timeout 是否可被当前解释器加载（不可用 → 仅整文件墙钟兜底）。"""
    try:
        import pytest_timeout  # noqa: F401

        return True
    except Exception:
        return False


def _pytest_version() -> str:
    """pytest 版本字符串（报告 provenance；探测失败 → "unknown"）。"""
    try:
        import pytest

        return str(pytest.__version__)
    except Exception:
        return "unknown"


def _normalize_node_list(output: str) -> list[str]:
    """从 ``pytest --collect-only -q`` 输出提取 node id（``file::test`` 行）。"""
    nodes: list[str] = []
    for line in (output or "").splitlines():
        line = line.strip()
        if "::" not in line:
            continue
        if line.startswith(("=", "-", "_")) or " " in line:
            continue
        nodes.append(line)
    return nodes


def _junit_node_key(classname: str, name: str) -> str | None:
    """JUnit ``classname``/``name`` → 与 collect 一致的规范 node key。

    ``classname="test_generated"`` → ``test_generated.py::<name>``；
    ``classname="test_generated.TestX"`` → ``test_generated.py::TestX::<name>``。
    收集失败行（classname 为空）→ None（单独归因，不计测试）。
    """
    cls = (classname or "").strip()
    nm = (name or "").strip()
    if not cls or not nm:
        return None
    marker = "test_generated"
    if cls == marker:
        classes: list[str] = []
    elif cls.startswith(marker + "."):
        classes = cls[len(marker) + 1 :].split(".")
    else:
        idx = cls.rfind(marker)
        if idx < 0:
            return None
        rest = cls[idx + len(marker) :].lstrip(".")
        classes = rest.split(".") if rest else []
    return "::".join(["test_generated.py", *classes, nm])


def _testcase_status(case: ET.Element) -> tuple[str, str]:
    """JUnit ``<testcase>`` → (status, detail)；status ∈ pass/fail/skip/error/timeout。"""
    for child in case:
        tag = child.tag
        if tag == "failure":
            message = f"{child.get('message') or ''}\n{child.text or ''}"
            if _TIMEOUT_FAILURE_RE.search(message):
                return "timeout", "pytest-timeout 判失败"
            return "fail", _truncate(message, 200)
        if tag == "error":
            message = f"{child.get('message') or ''}\n{child.text or ''}"
            if (child.get("message") or "") == "collection failure":
                return "error", "collection failure"
            return "error", _truncate(message, 200)
        if tag == "skipped":
            return "skip", _truncate(str(child.get("type") or child.get("message") or ""), 120)
    return "pass", ""


def parse_junit_xml(path: Path) -> dict[str, Any]:
    """解析 pytest ``--junitxml`` 产物。

    Returns:
        {``outcomes``: {node_key: status}, ``collection_failures``: [...],
         ``parse_error``: str|None, ``n_testcases``: int}
    """
    result: dict[str, Any] = {"outcomes": {}, "collection_failures": [], "parse_error": None, "n_testcases": 0}
    if not path.is_file():
        result["parse_error"] = "junitxml 不存在"
        return result
    try:
        tree = ET.parse(str(path))
    except (ET.ParseError, OSError) as e:
        result["parse_error"] = f"junitxml 解析失败: {e}"
        return result
    root = tree.getroot()
    for case in root.iter("testcase"):
        result["n_testcases"] += 1
        classname = case.get("classname") or ""
        name = case.get("name") or ""
        status, detail = _testcase_status(case)
        if status == "error" and detail == "collection failure":
            result["collection_failures"].append(
                {"classname": classname, "name": name, "detail": _truncate(case.text or "", 300)}
            )
            continue
        node = _junit_node_key(classname, name)
        if node is None:
            result["collection_failures"].append(
                {"classname": classname, "name": name, "detail": _truncate(case.text or "", 300)}
            )
            continue
        result["outcomes"][node] = status
    return result


def _outcomes_agree(junit_status: str, verbose_status: str) -> bool:
    """两路解析是否一致（timeout 视为 fail 的子类，不误报 mismatch）。"""
    if junit_status == verbose_status:
        return True
    return {junit_status, verbose_status} <= {"fail", "timeout"}


def parse_verbose_outcomes(output: str) -> dict[str, str]:
    """解析 ``pytest -v`` 正文行 → {node: pass/fail/error/skip}（junit 交叉校验用）。"""
    outcomes: dict[str, str] = {}
    for raw in (output or "").splitlines():
        line = raw.strip()
        match = _VERBOSE_RE.match(line)
        if not match:
            continue
        outcomes[match.group("node")] = _VERBOSE_OUTCOMES.get(match.group("out"), "error")
    return outcomes


def _first_matching_line(output: str, pattern: re.Pattern[str]) -> str:
    """从 pytest 输出中取首条命中 pattern 的行（错误归因的可读摘要）。"""
    for line in (output or "").splitlines():
        if pattern.search(line):
            return line.strip()
    return ""


def _classify_collection_failure(rc: int | None, output: str, timed_out: bool) -> tuple[str, str]:
    """收集/执行失败 → (不可分类原因, 详情)。"""
    if timed_out:
        return "file_timeout", "整文件墙钟超时（收集或执行阶段）"
    # 归因优先级：缺模块/相对 import 的具体行，最后才回退通用 ImportError 行
    import_line = (
        _first_matching_line(output, _MISSING_MODULE_RE)
        or _first_matching_line(output, _RELATIVE_IMPORT_RE)
        or _first_matching_line(output, _IMPORT_ERROR_RE)
    )
    if import_line:
        return "import_error", _truncate(import_line, 400)
    syntax_line = _first_matching_line(output, _SYNTAX_ERROR_RE)
    if syntax_line:
        return "syntax_error", _truncate(syntax_line, 400)
    if rc is not None and rc >= 2:
        return "collect_error", f"pytest rc={rc}（收集中断）: {_truncate(output, 400)}"
    return "collect_error", f"pytest rc={rc}: {_truncate(output, 400)}"


def run_side(
    *,
    version_dir: Path,
    pytest_timeout_s: float,
    collect_timeout_s: float,
    file_timeout_s: float,
    python_exe: str | None = None,
) -> dict[str, Any]:
    """在一个已物化版本目录里跑「收集 + 整文件执行」并解析逐测试结果。

    返回 dict 中 ``ok`` 表示两侧结果足以做逐测试分类（收集成功且执行可解析）；
    ``missing_reason`` 是该侧测试在逐测试分类中缺失时的归因原因。
    """
    python_exe = python_exe or sys.executable
    base_env = nested_pytest_env(
        PYTHONPATH=str(version_dir),
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONHASHSEED="0",
        PYTHONUNBUFFERED="1",
        COLUMNS="200",
    )
    common = ["-p", "no:cacheprovider", "-p", "no:randomly", "--no-header", "--color=no"]
    rec: dict[str, Any] = {
        "ok": False,
        "collect_ok": False,
        "collect_reason": None,
        "collect_rc": None,
        "collect_timed_out": False,
        "collected": [],
        "n_collected": 0,
        "exec_ok": False,
        "exec_rc": None,
        "exec_timed_out": False,
        "exec_error": False,
        "outcomes": {},
        "n_outcomes": 0,
        "parser": "none",
        "parse_agreement": 0,
        "parse_mismatch": [],
        "missing_reason": "unknown",
        "outcome_counts": {},
        "detail": "",
        "timing": {"collect_wall_s": 0.0, "exec_wall_s": 0.0, "total_wall_s": 0.0},
    }
    t_total = time.time()

    # ① 收集：先取 node id 清单，并在执行前定位收集/import/语法错误
    collect_cmd = [python_exe, "-m", "pytest", TEST_FILENAME, "--collect-only", "-q", *common]
    t0 = time.time()
    collect_res = run_with_timeout(
        collect_cmd,
        timeout=collect_timeout_s,
        cwd=str(version_dir),
        text=True,
        logger_name="misguided_collect",
        env=base_env,
    )
    rec["timing"]["collect_wall_s"] = round(time.time() - t0, 3)
    collect_out = (collect_res.stdout or "") + "\n" + (collect_res.stderr or "")
    rec["collect_timed_out"] = bool(getattr(collect_res, "timed_out", False))
    rec["collect_rc"] = None if rec["collect_timed_out"] else collect_res.returncode
    if rec["collect_timed_out"] or collect_res.returncode != 0:
        reason, detail = _classify_collection_failure(rec["collect_rc"], collect_out, rec["collect_timed_out"])
        rec["collect_reason"] = reason
        rec["missing_reason"] = reason
        rec["detail"] = detail
        rec["timing"]["total_wall_s"] = round(time.time() - t_total, 3)
        return rec
    nodes = _normalize_node_list(collect_res.stdout or "")
    rec["collect_ok"] = True
    rec["collected"] = nodes
    rec["n_collected"] = len(nodes)
    if not nodes:
        rec["collect_reason"] = "no_tests_collected"
        rec["missing_reason"] = "no_tests_collected"
        rec["detail"] = "pytest 收集到 0 条测试（生成测试文件无 test_* / 全被跳过）"
        rec["timing"]["total_wall_s"] = round(time.time() - t_total, 3)
        return rec

    # ② 执行：整文件一次，--junitxml 取逐测试结果；可用时加 pytest-timeout
    xml_path = version_dir / "junit.xml"
    exec_cmd = [
        python_exe,
        "-m",
        "pytest",
        TEST_FILENAME,
        "-v",
        "--tb=short",
        f"--junitxml={xml_path}",
        *common,
    ]
    if pytest_timeout_s > 0:
        exec_cmd += [f"--timeout={pytest_timeout_s:g}", "--timeout-method=signal"]
    t1 = time.time()
    exec_res = run_with_timeout(
        exec_cmd,
        timeout=file_timeout_s,
        cwd=str(version_dir),
        text=True,
        logger_name="misguided_exec",
        env=base_env,
    )
    rec["timing"]["exec_wall_s"] = round(time.time() - t1, 3)
    rec["timing"]["total_wall_s"] = round(time.time() - t_total, 3)
    stdout = exec_res.stdout or ""
    stderr = exec_res.stderr or ""
    combined = stdout + "\n" + stderr
    rec["exec_timed_out"] = bool(getattr(exec_res, "timed_out", False))
    rec["exec_rc"] = None if rec["exec_timed_out"] else exec_res.returncode
    # M1 同源执行错误判据（rc>=2 或显式收集/语法标记；超时按 -9 走同一判据）
    try:
        from experiments._m1_metrics import _looks_like_test_execution_error

        rec["exec_error"] = bool(
            _looks_like_test_execution_error(
                -9 if rec["exec_timed_out"] else int(rec["exec_rc"] if rec["exec_rc"] is not None else 0),
                combined,
            )
        )
    except Exception:  # pragma: no cover - 单一事实源不可用时保守回退
        rec["exec_error"] = bool(rec["exec_timed_out"] or (rec["exec_rc"] or 0) >= 2)

    junit = parse_junit_xml(xml_path)
    verbose = parse_verbose_outcomes(stdout)
    if rec["exec_timed_out"]:
        rec["outcomes"] = {}
        rec["missing_reason"] = "timeout"
        rec["detail"] = "整文件墙钟超时，逐测试结果不可判（保守全部记 timeout）"
        rec["timing"]["total_wall_s"] = round(time.time() - t_total, 3)
        return rec
    if junit["outcomes"]:
        rec["outcomes"] = junit["outcomes"]
        rec["parser"] = "junit"
        if verbose:
            shared = set(junit["outcomes"]) & set(verbose)
            rec["parse_agreement"] = len(shared)
            rec["parse_mismatch"] = sorted(
                node for node in shared if not _outcomes_agree(junit["outcomes"][node], verbose[node])
            )
            rec["parser"] = "junit+verbose"
    elif verbose:
        rec["outcomes"] = verbose
        rec["parser"] = "verbose_fallback"
    rec["n_outcomes"] = len(rec["outcomes"])
    rec["outcome_counts"] = dict(sorted(Counter(rec["outcomes"].values()).items()))
    if not rec["outcomes"]:
        reason, detail = _classify_collection_failure(rec["exec_rc"], combined, False)
        rec["missing_reason"] = reason
        rec["detail"] = detail
        rec["timing"]["total_wall_s"] = round(time.time() - t_total, 3)
        return rec
    if junit["collection_failures"]:
        rec["missing_reason"] = "collect_error"
        rec["detail"] = (
            f"执行期收集失败 {len(junit['collection_failures'])} 处: {junit['collection_failures'][0]['detail'][:200]}"
        )
    elif rec["exec_error"]:
        rec["missing_reason"] = "collect_error"
        rec["detail"] = f"pytest 执行错误（rc={rec['exec_rc']}）: {_truncate(combined, 300)}"
    rec["exec_ok"] = True
    rec["ok"] = True
    return rec


# ─── 逐测试四分类 ──────────────────────────────────────────────────────────
def classify_outcomes(
    nodes: list[str],
    buggy_outcomes: dict[str, str],
    fixed_outcomes: dict[str, str],
    *,
    buggy_missing_reason: str = "unknown",
    fixed_missing_reason: str = "unknown",
) -> tuple[list[dict[str, Any]], dict[str, int], dict[str, int]]:
    """按 node id 对两侧逐测试结果做四分类。

    Args:
        nodes: 待分类 node id 列表（应为两侧收集结果的并集）。
        buggy_outcomes / fixed_outcomes: {node: pass|fail|error|skip|timeout}。
        buggy_missing_reason / fixed_missing_reason: 某侧无该 node 时的归因原因
            （如整文件 timeout / 收集失败原因）。

    Returns:
        (rows, counts, unclassifiable_counts)：
        - rows: 按 node 排序的逐测试记录（cls 为 None 时 reason 归因）；
        - counts: 四分类计数（仅可分类）；
        - unclassifiable_counts: 不可分类原因计数。
    """
    rows: list[dict[str, Any]] = []
    counts: dict[str, int] = dict.fromkeys(CLASSES, 0)
    unclassifiable: dict[str, int] = dict.fromkeys(UNCLASSIFIABLE_REASONS, 0)
    for node in sorted(nodes):
        b = buggy_outcomes.get(node)
        f = fixed_outcomes.get(node)
        reason: str | None = None
        cls: str | None = None
        if b is None or f is None:
            reason = "missing_side"
            if b is None and f is None:
                reason = "unknown"
            elif b is None:
                reason = buggy_missing_reason or "missing_side"
            else:
                reason = fixed_missing_reason or "missing_side"
        elif "timeout" in (b, f):
            reason = "timeout"
        elif "skip" in (b, f):
            reason = "skipped"
        elif "error" in (b, f):
            reason = "test_error"
        elif b in ("pass", "fail") and f in ("pass", "fail"):
            if b == "fail" and f == "pass":
                cls = "effective"
            elif b == "pass" and f == "fail":
                cls = "misguided"
            elif b == "pass" and f == "pass":
                cls = "both_pass"
            else:
                cls = "both_fail"
        else:
            reason = "unknown"
        if cls is not None:
            counts[cls] += 1
        else:
            unclassifiable[reason or "unknown"] += 1
        rows.append(
            {
                "node": node,
                "buggy": b if b is not None else "unavailable",
                "fixed": f if f is not None else "unavailable",
                "cls": cls,
                "reason": reason,
            }
        )
    return rows, counts, unclassifiable


def _union_nodes(*node_lists: list[str]) -> list[str]:
    """多来源 node id 并集（排序去重，确定性）。"""
    return sorted({node for nodes in node_lists for node in nodes})


def _count_ast_test_defs(code: str) -> int:
    """AST 统计 test_* 函数定义数（含类内方法；语法错误 → -1）。"""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return -1
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
    )


def replay_detection(
    buggy_side: dict[str, Any],
    fixed_side: dict[str, Any],
    *,
    strict: bool = False,
) -> float | None:
    """用本次重放复算 M1 任务级 detection_rate（0.0/1.0/None）。

    规则与 ``_m1_metrics._compute_detection_rate`` 同口径：
    buggy rc!=0 ∧ fixed rc==0 ∧ 两侧无收集/语法错误；超时/材料缺失 → None。

    ``strict=True`` 时若任一侧出现单测 timeout，也记 None——用于**模拟
    A-06 per-test 超时功能落地前**的历史 M1 口径（整套超时不可判），
    以便与归档 detection 逐位对账。
    """
    if not (buggy_side.get("collect_ok") and fixed_side.get("collect_ok")):
        return None
    if buggy_side.get("exec_timed_out") or fixed_side.get("exec_timed_out"):
        return None
    if strict and any(outcome == "timeout" for outcome in (buggy_side.get("outcomes") or {}).values()):
        return None
    b_rc = buggy_side.get("exec_rc")
    f_rc = fixed_side.get("exec_rc")
    if b_rc is None or f_rc is None:
        return None
    if buggy_side.get("exec_error") or fixed_side.get("exec_error"):
        return 0.0
    return 1.0 if (b_rc != 0 and f_rc == 0) else 0.0


def _detection_agreement(artifact_value: float | None, replay_value: float | None) -> str:
    """归档 detection 与重放 detection 的对账标签。"""
    if artifact_value is None and replay_value is None:
        return "both_none"
    if artifact_value is None:
        return "artifact_none"
    if replay_value is None:
        return "replay_none"
    if abs(float(artifact_value) - float(replay_value)) < 1e-9:
        return "match"
    return "mismatch"


def _detection_disagreement_reason(
    artifact_value: float | None,
    replay_value: float | None,
    strict_value: float | None,
    buggy_side: dict[str, Any],
    fixed_side: dict[str, Any],
) -> str:
    """给 detection 不一致的任务生成可解释归因（用于交叉校验表）。"""
    tag = _detection_agreement(artifact_value, replay_value)
    if tag in {"match", "both_none"}:
        return ""
    if tag == "replay_none":
        if buggy_side.get("exec_timed_out") or fixed_side.get("exec_timed_out"):
            return "重放整文件超时 → None（归档非 None）"
        if not (buggy_side.get("collect_ok") and fixed_side.get("collect_ok")):
            return "重放收集失败 → None（归档非 None）"
        return "重放不可判 → None（归档非 None）"
    if tag == "artifact_none" and strict_value is not None:
        return "归档 None 但历史口径重放可判——需人工核对（可能为跨批次随机性）"
    buggy_timeouts = sum(1 for o in (buggy_side.get("outcomes") or {}).values() if o == "timeout")
    fixed_timeouts = sum(1 for o in (fixed_side.get("outcomes") or {}).values() if o == "timeout")
    if artifact_value is None and replay_value is not None:
        if buggy_timeouts or fixed_timeouts:
            return (
                f"per-test 超时改写整文件超时判定（buggy timeout={buggy_timeouts}、"
                f"fixed timeout={fixed_timeouts}）→ 归档 None 变为可判 {replay_value}"
            )
        return "归档 None、重放可判（材料/执行环境差异，需人工核对）"
    if replay_value is None:
        return "重放可判性低于归档（环境差异）"
    return "两侧可判但结果不同（跨批次随机性/超时口径差异，描述性披露）"


# ─── 单任务分析 ────────────────────────────────────────────────────────────
def _task_program(task_id: str, task_metadata: dict[str, Any]) -> str:
    """解析任务被测程序名：优先 ``task_metadata.program``，回退 task_id 末段。"""
    program = str(task_metadata.get("program") or "").strip()
    if not program:
        program = str(task_id).rsplit("__", 1)[-1].strip()
    return program


def _side_record(side: dict[str, Any]) -> dict[str, Any]:
    """侧结果中进报告 body 的稳定字段（墙钟耗时只进 timing，digest 剔除）。"""
    return {
        "collect_ok": side.get("collect_ok"),
        "collect_rc": side.get("collect_rc"),
        "collect_timed_out": side.get("collect_timed_out"),
        "collect_reason": side.get("collect_reason"),
        "n_collected": side.get("n_collected"),
        "exec_ok": side.get("exec_ok"),
        "exec_rc": side.get("exec_rc"),
        "exec_timed_out": side.get("exec_timed_out"),
        "exec_error": side.get("exec_error"),
        "n_outcomes": side.get("n_outcomes"),
        "outcome_counts": side.get("outcome_counts"),
        "parser": side.get("parser"),
        "parse_agreement": side.get("parse_agreement"),
        "parse_mismatch": side.get("parse_mismatch"),
        "detail": _truncate(str(side.get("detail") or ""), 500),
        "missing_reason": side.get("missing_reason"),
    }


def analyze_task(
    row: dict[str, Any],
    *,
    roots: list[Path],
    pytest_timeout_s: float,
    collect_timeout_s: float,
    file_timeout_s: float,
    siblings_cache: dict[str, dict[str, str]],
) -> dict[str, Any]:
    """分析一个归档任务行：材料校验 → 物化两侧 → 重放 → 四分类。

    任何材料/执行不可用都记 ``status="structural_skip"`` + 原因码，
    **不静默跳过**；可用的逐测试结果照常单列不可分类原因。
    """
    task_id = str(row.get("task_id") or "")
    raw_meta = row.get("task_metadata")
    task_metadata: dict[str, Any] = raw_meta if isinstance(raw_meta, dict) else {}
    generated_test = str(row.get("generated_test") or "")
    program = _task_program(task_id, task_metadata)
    record: dict[str, Any] = {
        "task_id": task_id or "(缺失 task_id)",
        "program": program or None,
        "analysis_set": "defect_program" if program and not program.endswith("_test") else "driver_or_unknown",
        "defect_signal": None,
        "artifact_verdict": row.get("specificity_gate_verdict"),
        "artifact_detection_rate": _as_float_or_none(row.get("detection_rate")),
        "artifact_passed": _as_bool_or_none(row.get("passed")),
        "status": "ok",
        "skip_reason": None,
        "skip_detail": "",
        "buggy_source_path": None,
        "buggy_source_sha256": None,
        "fixed_source_sha256": None,
        "generated_test_sha256": None,
        "validation": {},
        "n_ast_test_defs": 0,
        "n_collected": 0,
        "n_classifiable": 0,
        "counts": dict.fromkeys(CLASSES, 0),
        "unclassifiable": dict.fromkeys(UNCLASSIFIABLE_REASONS, 0),
        "tests": [],
        "buggy_side": {},
        "fixed_side": {},
        "replay_detection": None,
        "replay_detection_strict": None,
        "replay_fixed_green": None,
        "detection_agreement": "both_none",
        "detection_disagreement_reason": "",
        "verdict_agreement": "not_applicable",
        "verdict_disagreement_reason": "",
        "timing": {"total_wall_s": 0.0},
    }
    t_total = time.time()

    def _skip(reason: str, detail: str) -> dict[str, Any]:
        record["status"] = "structural_skip"
        record["skip_reason"] = reason
        record["skip_detail"] = _truncate(detail, 600)
        # 结构跳过 ⇒ 重放不可判（replay None）；仍要与归档 detection 对账，
        # 避免把"归档有判定、重放不可判"静默吞成 both_none。
        record["detection_agreement"] = _detection_agreement(record["artifact_detection_rate"], None)
        if record["detection_agreement"] == "replay_none":
            record["detection_disagreement_reason"] = (
                f"结构跳过（{reason}）→ 无法重放；归档 detection={record['artifact_detection_rate']}"
            )
        record["timing"]["total_wall_s"] = round(time.time() - t_total, 3)
        return record

    if not task_id or not task_metadata:
        return _skip("artifact_row_malformed", "归档行缺 task_id 或 task_metadata")
    if not generated_test.strip():
        return _skip("empty_generated_test", "归档 generated_test 为空")
    if not _PY_IDENT_RE.match(program or ""):
        return _skip("invalid_program_name", f"程序名不是合法 Python 标识符: {program!r}")
    gen_ast = _count_ast_test_defs(generated_test)
    record["n_ast_test_defs"] = gen_ast
    if gen_ast < 0:
        return _skip("generated_test_syntax_error", "generated_test 无法通过 ast.parse（语法错误）")
    fixed_code = str(task_metadata.get("fixed") or "")
    if not fixed_code.strip():
        return _skip("missing_fixed_material", "task_metadata.fixed 为空（无 gold 修复版材料）")
    try:
        ast.parse(fixed_code)
    except SyntaxError as e:
        return _skip("fixed_material_unparseable", f"task_metadata.fixed 语法错误: {e}")
    record["fixed_source_sha256"] = sha256_text(fixed_code)
    record["generated_test_sha256"] = sha256_text(generated_test)
    try:
        buggy_code, buggy_path = resolve_buggy_source(program, roots)
        dataset_fixed = dataset_fixed_source(program, roots)
        record["validation"] = validate_buggy_source(buggy_code, program, task_metadata, dataset_fixed)
        record["buggy_source_path"] = _display_path(buggy_path)
        record["buggy_source_sha256"] = sha256_text(buggy_code)
        # 缺陷信号：buggy 与 fixed 源码相同 → effective/misguided 结构上恒 0
        # （如 QuixBugs 的 node.py 辅助模块被数据集加载器当作程序行）；不进
        # 机制度量主分析集，但仍保留其逐测试分类（all_tasks 口径可见）。
        record["defect_signal"] = buggy_code.strip() != fixed_code.strip()
    except MaterialError as e:
        return _skip(e.reason, e.detail)
    if program not in siblings_cache:
        siblings_cache[program] = collect_siblings(buggy_path)
    siblings = siblings_cache[program]

    tmpdir = Path(tempfile.mkdtemp(prefix=f"misguided_{program}_"))
    try:
        buggy_dir = tmpdir / "buggy"
        fixed_dir = tmpdir / "fixed"
        try:
            materialize_version(buggy_dir, program, buggy_code, generated_test, siblings)
            materialize_version(fixed_dir, program, fixed_code, generated_test, siblings)
        except OSError as e:
            return _skip("materialize_failed", f"物化版本目录失败: {e}")
        buggy_side = run_side(
            version_dir=buggy_dir,
            pytest_timeout_s=pytest_timeout_s,
            collect_timeout_s=collect_timeout_s,
            file_timeout_s=file_timeout_s,
        )
        fixed_side = run_side(
            version_dir=fixed_dir,
            pytest_timeout_s=pytest_timeout_s,
            collect_timeout_s=collect_timeout_s,
            file_timeout_s=file_timeout_s,
        )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    record["buggy_side"] = _side_record(buggy_side)
    record["fixed_side"] = _side_record(fixed_side)
    nodes = _union_nodes(
        buggy_side.get("collected") or [],
        fixed_side.get("collected") or [],
        list((buggy_side.get("outcomes") or {}).keys()),
        list((fixed_side.get("outcomes") or {}).keys()),
    )
    rows, counts, unclassifiable = classify_outcomes(
        nodes,
        buggy_side.get("outcomes") or {},
        fixed_side.get("outcomes") or {},
        buggy_missing_reason=buggy_side.get("missing_reason") or "missing_side",
        fixed_missing_reason=fixed_side.get("missing_reason") or "missing_side",
    )
    record["tests"] = rows
    record["counts"] = counts
    record["unclassifiable"] = unclassifiable
    record["n_collected"] = len(nodes)
    record["n_classifiable"] = sum(counts.values())
    record["replay_detection"] = replay_detection(buggy_side, fixed_side)
    record["replay_detection_strict"] = replay_detection(buggy_side, fixed_side, strict=True)
    if fixed_side.get("collect_ok") and not fixed_side.get("exec_timed_out") and fixed_side.get("exec_rc") is not None:
        record["replay_fixed_green"] = int(fixed_side["exec_rc"]) == 0
    record["detection_agreement"] = _detection_agreement(record["artifact_detection_rate"], record["replay_detection"])
    record["detection_disagreement_reason"] = _detection_disagreement_reason(
        record["artifact_detection_rate"],
        record["replay_detection"],
        record["replay_detection_strict"],
        buggy_side,
        fixed_side,
    )
    record["verdict_agreement"], record["verdict_disagreement_reason"] = _verdict_agreement(
        record["artifact_verdict"], fixed_side
    )
    # 执行不可用 → 任务级结构跳过（逐测试已按不可分类原因单列，不进可分类分母）
    side_failure = _side_failure_reason(buggy_side, fixed_side)
    if side_failure is not None:
        return _skip(*side_failure)
    if not rows:
        return _skip("no_tests_collected", "两侧均未收集到可分类测试 node")
    if record["n_classifiable"] == 0:
        return _skip("no_classifiable_tests", "两侧结果存在但全部不可分类（见 unclassifiable 计数）")
    record["timing"]["total_wall_s"] = round(time.time() - t_total, 3)
    return record


def _side_failure_reason(buggy_side: dict[str, Any], fixed_side: dict[str, Any]) -> tuple[str, str] | None:
    """双侧结果是否足以分类；不可用 → (结构跳过原因, 详情)。"""
    for label, side in (("buggy", buggy_side), ("fixed", fixed_side)):
        if side.get("collect_timed_out"):
            return "file_timeout", f"{label} 侧收集超时"
        if not side.get("collect_ok"):
            reason = str(side.get("collect_reason") or "collect_error")
            if reason == "no_tests_collected":
                return "no_tests_collected", f"{label} 侧收集到 0 条测试"
            return reason, f"{label} 侧收集失败: {_truncate(str(side.get('detail') or ''), 400)}"
        if side.get("exec_timed_out"):
            return "file_timeout", f"{label} 侧整文件执行超时（{_truncate(str(side.get('detail') or ''), 300)}）"
        if not side.get("outcomes"):
            reason = str(side.get("missing_reason") or "exec_unknown")
            if reason == "collect_error":
                reason = "collect_error"
            return reason, f"{label} 侧执行无逐测试结果: {_truncate(str(side.get('detail') or ''), 400)}"
    return None


def _verdict_agreement(artifact_verdict: Any, fixed_side: dict[str, Any]) -> tuple[str, str]:
    """归档特异性门 verdict 与重放 fixed 侧绿/红的对账。

    ``specific_red`` 的语义 = 生成测试在 gold fixed 上转绿 ⇒ 重放 fixed 侧
    应 rc==0；``over_red`` = gold fixed 上仍红 ⇒ 重放 fixed 侧应 rc!=0。
    不可判定（收集失败/超时/无材料）→ ``not_applicable``。
    """
    verdict = str(artifact_verdict or "")
    if verdict not in {"specific_red", "over_red"}:
        return "not_applicable", ""
    if not fixed_side.get("collect_ok") or fixed_side.get("exec_timed_out") or fixed_side.get("exec_rc") is None:
        return "not_applicable", "重放 fixed 侧不可判定"
    if fixed_side.get("exec_error"):
        return "not_applicable", "重放 fixed 侧执行错误（rc>=2/收集标记）"
    replay_green = int(fixed_side["exec_rc"]) == 0
    expected_green = verdict == "specific_red"
    if replay_green == expected_green:
        return "match", ""
    return (
        "mismatch",
        f"归档 verdict={verdict}（期望 fixed {'绿' if expected_green else '红'}），"
        f"重放 fixed rc={fixed_side['exec_rc']}（{'绿' if replay_green else '红'}）",
    )


# ─── 聚合与交叉校验 ────────────────────────────────────────────────────────
def _aggregate_subset(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    """聚合一个任务子集：总数、四分类、不可分类、任务级分布、分母披露。"""
    counts: dict[str, int] = dict.fromkeys(CLASSES, 0)
    unclassifiable: dict[str, int] = dict.fromkeys(UNCLASSIFIABLE_REASONS, 0)
    n_collected = 0
    n_classifiable = 0
    n_ast_defs = 0
    per_task_misguided: list[float] = []
    per_task_effective: list[float] = []
    misguided_tasks: list[str] = []
    effective_tasks: list[str] = []
    both_fail_only_tasks: list[str] = []
    for task in tasks:
        n_collected += int(task.get("n_collected") or 0)
        n_classifiable += int(task.get("n_classifiable") or 0)
        n_ast_defs += max(0, int(task.get("n_ast_test_defs") or 0))
        for cls in CLASSES:
            counts[cls] += int((task.get("counts") or {}).get(cls) or 0)
        for reason, value in (task.get("unclassifiable") or {}).items():
            if value:
                unclassifiable[reason] = unclassifiable.get(reason, 0) + int(value)
        task_classifiable = int(task.get("n_classifiable") or 0)
        if task_classifiable:
            mis = int((task.get("counts") or {}).get("misguided") or 0)
            eff = int((task.get("counts") or {}).get("effective") or 0)
            per_task_misguided.append(mis / task_classifiable)
            per_task_effective.append(eff / task_classifiable)
            if mis > 0:
                misguided_tasks.append(str(task.get("task_id")))
            if eff > 0:
                effective_tasks.append(str(task.get("task_id")))
            if mis == 0 and eff == 0:
                both_fail_only_tasks.append(str(task.get("task_id")))
    n_tasks_ok = sum(1 for t in tasks if t.get("status") == "ok")
    rates: dict[str, float | None] = {}
    for cls in CLASSES:
        rates[f"{cls}_share"] = round(counts[cls] / n_classifiable, 6) if n_classifiable else None
    return {
        "n_tasks": len(tasks),
        "n_tasks_ok": n_tasks_ok,
        "n_tasks_structural_skip": len(tasks) - n_tasks_ok,
        "n_ast_test_defs": n_ast_defs,
        "n_tests_collected": n_collected,
        "n_tests_classifiable": n_classifiable,
        "n_tests_unclassifiable": sum(unclassifiable.values()),
        "counts": counts,
        "rates": rates,
        "unclassifiable_counts": unclassifiable,
        "task_level": {
            "n_tasks_with_effective": len(effective_tasks),
            "n_tasks_with_misguided": len(misguided_tasks),
            "n_tasks_with_neither": len(both_fail_only_tasks),
            "misguided_task_ids": sorted(misguided_tasks),
            "effective_task_ids": sorted(effective_tasks),
            "per_task_misguided_fraction": _summary(per_task_misguided),
            "per_task_effective_fraction": _summary(per_task_effective),
            "per_task_classifiable_count": _summary(
                [float(t.get("n_classifiable") or 0) for t in tasks if t.get("status") == "ok"]
            ),
        },
    }


def aggregate_tasks(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    """臂级聚合：三套口径。

    - ``all_tasks``：全部归档行（含结构跳过任务，用于总量披露）；
    - ``defect_programs``：**主分析机制度量集** = 非 ``*_test`` 驱动 且
      ``buggy != fixed``（有缺陷信号）的任务；
    - ``defect_programs_41_convention``：与项目既有
      ``emse_df_spec_analysis.defect_program_ids`` 对齐的 41 口径行
      （仅按 task_id 后缀排除 ``*_test``；其中可能含无缺陷信号的辅助模块行，
      如 QuixBugs node——其 buggy==fixed，effective/misguided 结构上恒 0）。

    主分析集用 40 口径：既保持"任务行数"与 project 41 口径的差异可见，
    又避免无缺陷任务稀释误导/有效占比。
    """
    defect_41 = [t for t in tasks if t.get("analysis_set") == "defect_program"]
    defect_primary = [t for t in defect_41 if t.get("defect_signal") is True]
    return {
        "all_tasks": _aggregate_subset(tasks),
        "defect_programs": _aggregate_subset(defect_primary),
        "defect_programs_41_convention": _aggregate_subset(defect_41),
    }


def build_cross_check(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    """与工件既有字段（detection_rate / specificity_gate_verdict / passed）的对账。"""
    detection: Counter[str] = Counter()
    verdict: Counter[str] = Counter()
    disagreements: list[dict[str, Any]] = []
    verdict_disagreements: list[dict[str, Any]] = []
    verdict_crosstab: dict[str, dict[str, int]] = {}
    passed_counts: Counter[str] = Counter()
    passed_vs_fixed_green: Counter[str] = Counter()
    for task in tasks:
        passed_value = task.get("artifact_passed")
        passed_counts["true" if passed_value is True else "false" if passed_value is False else "none"] += 1
        fixed_green = task.get("replay_fixed_green")
        green_tag = "none" if fixed_green is None else ("green" if fixed_green else "red")
        passed_vs_fixed_green[f"passed={passed_value}/{green_tag}"] += 1

        tag = str(task.get("detection_agreement") or "both_none")
        detection[tag] += 1
        if tag in {"mismatch", "artifact_none", "replay_none"}:
            disagreements.append(
                {
                    "task_id": task.get("task_id"),
                    "artifact_detection_rate": task.get("artifact_detection_rate"),
                    "replay_detection": task.get("replay_detection"),
                    "replay_detection_strict": task.get("replay_detection_strict"),
                    "agreement": tag,
                    "reason": task.get("detection_disagreement_reason"),
                    "buggy_exec_rc": (task.get("buggy_side") or {}).get("exec_rc"),
                    "fixed_exec_rc": (task.get("fixed_side") or {}).get("exec_rc"),
                    "counts": task.get("counts"),
                    "status": task.get("status"),
                }
            )
        v_tag = str(task.get("verdict_agreement") or "not_applicable")
        verdict[v_tag] += 1
        if v_tag == "mismatch":
            verdict_disagreements.append(
                {
                    "task_id": task.get("task_id"),
                    "artifact_verdict": task.get("artifact_verdict"),
                    "reason": task.get("verdict_disagreement_reason"),
                }
            )
        if task.get("status") == "ok":
            row = verdict_crosstab.setdefault(
                str(task.get("artifact_verdict")), {"n_tasks": 0, "effective": 0, "misguided": 0}
            )
            row["n_tasks"] += 1
            row["effective"] += int((task.get("counts") or {}).get("effective") or 0)
            row["misguided"] += int((task.get("counts") or {}).get("misguided") or 0)
    return {
        "detection_agreement_counts": dict(sorted(detection.items())),
        "detection_disagreements": disagreements,
        "verdict_agreement_counts": dict(sorted(verdict.items())),
        "verdict_disagreements": verdict_disagreements,
        "verdict_x_replay_counts": dict(sorted(verdict_crosstab.items())),
        "artifact_passed_counts": dict(sorted(passed_counts.items())),
        "passed_vs_replay_fixed_green": dict(sorted(passed_vs_fixed_green.items())),
        "replay_detection_strict_note": (
            "replay_detection_strict 模拟 A-06 per-test 超时落地前的历史 M1 口径"
            "（任一侧出现单测 timeout 即 None），用于与归档 detection 逐位对账"
        ),
    }


def build_arm_result(
    *,
    artifact_path: Path,
    artifact_sha256: str,
    artifact_label: str,
    arm: str,
    rows: list[dict[str, Any]],
    roots: list[Path],
    pytest_timeout_s: float,
    collect_timeout_s: float,
    file_timeout_s: float,
    jobs: int,
    limit: int,
    progress: bool = True,
) -> dict[str, Any]:
    """跑一个（工件, 臂）的全部任务并返回臂级结果（并行执行、确定性排序）。"""
    work_rows = sorted(rows, key=lambda r: str(r.get("task_id") or ""))
    if limit > 0:
        work_rows = work_rows[:limit]
    siblings_cache: dict[str, dict[str, str]] = {}
    tasks: list[dict[str, Any]] = []
    total = len(work_rows)
    done = 0
    started = time.time()

    def _one(row: dict[str, Any]) -> dict[str, Any]:
        return analyze_task(
            row,
            roots=roots,
            pytest_timeout_s=pytest_timeout_s,
            collect_timeout_s=collect_timeout_s,
            file_timeout_s=file_timeout_s,
            siblings_cache=siblings_cache,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        futures = {pool.submit(_one, row): row for row in work_rows}
        for future in concurrent.futures.as_completed(futures):
            task = future.result()
            tasks.append(task)
            done += 1
            if progress:
                side = "ok" if task.get("status") == "ok" else "skip"
                counts = task.get("counts") or {}
                print(
                    f"[misguided] {arm} {done}/{total} {task.get('task_id')}: {side} "
                    f"eff={counts.get('effective', 0)} mis={counts.get('misguided', 0)} "
                    f"bp={counts.get('both_pass', 0)} bf={counts.get('both_fail', 0)}"
                    + (f" reason={task.get('skip_reason')}" if side == "skip" else ""),
                    flush=True,
                )
    tasks.sort(key=lambda t: str(t.get("task_id") or ""))
    aggregate = aggregate_tasks(tasks)
    cross_check = build_cross_check(tasks)
    structural_skips: Counter[str] = Counter(str(t.get("skip_reason")) for t in tasks if t.get("status") != "ok")
    return {
        "artifact": artifact_label,
        "artifact_sha256": artifact_sha256,
        "arm": arm,
        "n_rows": len(rows),
        "n_tasks": len(tasks),
        "n_tasks_ok": aggregate["all_tasks"]["n_tasks_ok"],
        "n_tasks_structural_skip": aggregate["all_tasks"]["n_tasks_structural_skip"],
        "structural_skip_reasons": dict(sorted(structural_skips.items())),
        "structural_skips": [
            {
                "task_id": t.get("task_id"),
                "program": t.get("program"),
                "analysis_set": t.get("analysis_set"),
                "reason": t.get("skip_reason"),
                "detail": t.get("skip_detail"),
            }
            for t in tasks
            if t.get("status") != "ok"
        ],
        "aggregate": aggregate,
        "cross_check": cross_check,
        "tasks": tasks,
        "timing": {"wall_s": round(time.time() - started, 3)},
    }


# ─── 对比与报告 ────────────────────────────────────────────────────────────
def _rate_pair(arm_a: dict[str, Any], arm_b: dict[str, Any], key: str, subset: str = "all_tasks") -> dict[str, Any]:
    """两臂某个比率的对比（含 pp 差；描述性，无显著性推断）。"""
    agg_a = arm_a["aggregate"][subset]
    agg_b = arm_b["aggregate"][subset]
    va = agg_a["rates"].get(key)
    vb = agg_b["rates"].get(key)
    delta = None
    if va is not None and vb is not None:
        delta = round((float(vb) - float(va)) * 100.0, 4)
    return {"arm_a": va, "arm_b": vb, "delta_pp_b_minus_a": delta}


def _build_pairwise(arm_a: dict[str, Any], arm_b: dict[str, Any]) -> dict[str, Any]:
    """两臂（任意两臂）的描述性对比条目（百分比差 + 任务级计数）。"""
    per_test: dict[str, Any] = {}
    for cls in CLASSES:
        per_test[f"{cls}_share"] = _rate_pair(arm_a, arm_b, f"{cls}_share")
    per_test["n_tests_classifiable"] = {
        "arm_a": arm_a["aggregate"]["all_tasks"]["n_tests_classifiable"],
        "arm_b": arm_b["aggregate"]["all_tasks"]["n_tests_classifiable"],
    }
    task_level = {
        "n_tasks_with_effective": {
            "arm_a": arm_a["aggregate"]["defect_programs"]["task_level"]["n_tasks_with_effective"],
            "arm_b": arm_b["aggregate"]["defect_programs"]["task_level"]["n_tasks_with_effective"],
        },
        "n_tasks_with_misguided": {
            "arm_a": arm_a["aggregate"]["defect_programs"]["task_level"]["n_tasks_with_misguided"],
            "arm_b": arm_b["aggregate"]["defect_programs"]["task_level"]["n_tasks_with_misguided"],
        },
        "per_task_misguided_fraction": {
            "arm_a": arm_a["aggregate"]["defect_programs"]["task_level"]["per_task_misguided_fraction"],
            "arm_b": arm_b["aggregate"]["defect_programs"]["task_level"]["per_task_misguided_fraction"],
        },
    }
    defect = {cls: _rate_pair(arm_a, arm_b, f"{cls}_share", subset="defect_programs") for cls in CLASSES}
    return {
        "arm_a": {"label": arm_a["arm"], "artifact": arm_a["artifact"]},
        "arm_b": {"label": arm_b["arm"], "artifact": arm_b["artifact"]},
        "per_test_all_tasks": per_test,
        "per_test_defect_programs": defect,
        "task_level_all_tasks": task_level,
    }


def build_comparison(arms: list[dict[str, Any]]) -> dict[str, Any] | None:
    """描述性两两对比（N≥2 臂的全部无序臂对；N<2 → None；不做显著性推断）。

    3 臂正式批（df / doc / union）需要三组两两对比；结构保持
    ``pairs[]`` 列表（每条 = 一组 arm_a/arm_b 的百分点差），
    便于报告表格直出与确定性 digest。
    """
    if len(arms) < 2:
        return None
    pairs = [_build_pairwise(arms[i], arms[j]) for i in range(len(arms)) for j in range(i + 1, len(arms))]
    return {
        "kind": "descriptive_pairwise",
        "arms": [{"label": arm["arm"], "artifact": arm["artifact"], "sha256": arm["artifact_sha256"]} for arm in arms],
        "pairs": pairs,
        "interpretation_disclaimer": (
            "描述性对比：delta_pp = 臂 B − 臂 A（百分点），不构成预注册确认性证据，"
            "不含显著性/效应量推断；数值解读必须结合分母披露与交叉校验表。"
        ),
    }


def build_report(
    *,
    artifact_entries: list[dict[str, Any]],
    arms: list[dict[str, Any]],
    config: dict[str, Any],
    command: list[str],
) -> dict[str, Any]:
    """组装确定性报告 body（不含时间戳/墙钟；这些只进 run_meta）。"""
    comparison = build_comparison(arms)
    return {
        "schema_version": SCHEMA_VERSION,
        "tool": {"name": TOOL_NAME, "version": TOOL_VERSION},
        "metric_definition": {
            "name": "misguided/effective 逐测试四分类（ISSTA'26 操作化）",
            "classes": dict(CLASS_DEFINITIONS),
            "unclassifiable_reasons": list(UNCLASSIFIABLE_REASONS),
            "denominator": (
                "所有比率的分母 = 可分类测试数（两侧均有 pass/fail 结果的测试）；"
                "超时/收集失败/import 失败/语法错误/skipped/test_error/missing_side/unknown 单列，"
                "不进分母；任务级结构跳过单独计数，不混入任务级可判定集合"
            ),
            "citation": (
                "Zhao, Zhou & Cohen, ISSTA 2026, DOI 10.1145/3832204"
                "（引用来源：docs/reviews/INDEPENDENT_SYSTEMATIC_REVIEW_2026-10-17.md §4.5/§6 P1；"
                "本工具不把该文数字复用到本项目口径）"
            ),
            "evidence_status": "描述性机制度量；非预注册确认性证据，无显著性推断",
        },
        "config": config,
        "command": command,
        "inputs": artifact_entries,
        "arms": arms,
        "comparison": comparison,
        "limitations": [
            "生成测试之间的全局状态污染与收集顺序照旧存在（仅按版本隔离临时目录）",
            "官方金测试 test_cases 不参与四分类，仅用于 detection_rate 交叉校验口径说明",
            "9 个 QuixBugs *_test 驱动任务（相对 import、无官方金测试）在平铺口径下无法 import → 结构跳过；"
            "项目既有 41 口径（defect_program_ids，仅排除 *_test）中的 node 辅助模块任务 buggy==fixed"
            "（无缺陷信号），主分析集取 40 个有缺陷信号任务，41 口径兼容聚合单列可见",
            "per-test timeout 把挂死测试记为不可分类 timeout（不并入 both_fail），与 A-06 '超时记红' 的判分口径有意不同",
            "两臂对比为描述性（非预注册确认性），不做显著性推断；跨批次随机性见交叉校验表",
            "生成测试若使用未播种随机源，重复重放可能出现分类漂移（run_meta.determinism 如实披露）",
        ],
    }


def _fmt(value: Any) -> str:
    """Markdown 单元格格式化（None → "—"）。"""
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _fmt_rate(value: Any) -> str:
    """比率 → 百分比字符串（None → "—"）。"""
    if value is None:
        return "—"
    return f"{float(value) * 100:.2f}%"


def render_markdown(report: dict[str, Any], run_meta: dict[str, Any]) -> str:
    """渲染 Markdown 报告（确定性；时间戳取自 run_meta，不进 body digest）。"""
    lines: list[str] = []
    add = lines.append
    add("# misguided/effective 逐测试三分度量报告（零 LLM 重放）")
    add("")
    add("> **性质**：描述性机制度量（ISSTA'26 操作化），**非**预注册确认性证据；")
    add("> 不做显著性推断。所有比率的分母为可分类测试数，不可分类原因单列。")
    add(f"> **生成时间**：{run_meta.get('generated_at')}　**body digest**：`{run_meta.get('body_digest')}`")
    add(f"> **工具**：{report['tool']['name']} v{report['tool']['version']}　**schema**：`{report['schema_version']}`")
    add("")
    add("复算命令：")
    add("")
    add("```bash")
    add(" ".join(str(x) for x in report.get("command") or []))
    add("```")
    add("")
    add("## 1. 输入工件")
    add("")
    add("| 工件 | sha256 | 臂 | 行数 |")
    add("|---|---|---|---|")
    for entry in report.get("inputs") or []:
        for arm in entry.get("arms") or []:
            add(f"| `{entry['path']}` | `{entry['sha256']}` | `{arm['arm']}` | {arm['n_rows']} |")
    add("")
    add("## 2. 口径定义")
    add("")
    add("| 类别 | 定义 |")
    add("|---|---|")
    for cls, definition in (report["metric_definition"]["classes"] or {}).items():
        add(f"| `{cls}` | {definition} |")
    add("")
    add("可分类测试 = 两侧均有 pass/fail 结果；以下原因**单列**、不进分母：")
    add("`" + "`、`".join(report["metric_definition"]["unclassifiable_reasons"]) + "`。")
    add("")
    add("> 分母纪律：" + report["metric_definition"]["denominator"])
    add("")
    add("## 3. 臂级汇总")
    add("")
    add("| 指标 | " + " | ".join(f"`{arm['arm']}`" for arm in report["arms"]) + " |")
    add("|---|" + "---|" * len(report["arms"]))
    agg_rows = [
        ("工件行数 / 分析任务数", lambda a: f"{a['n_rows']} / {a['n_tasks']}"),
        ("可分类任务数（ok）", lambda a: a["aggregate"]["all_tasks"]["n_tasks_ok"]),
        ("结构跳过任务数", lambda a: a["aggregate"]["all_tasks"]["n_tasks_structural_skip"]),
        ("总收集测试数（并集，含跳过任务）", lambda a: a["aggregate"]["all_tasks"]["n_tests_collected"]),
        ("可分类测试数（分母）", lambda a: a["aggregate"]["all_tasks"]["n_tests_classifiable"]),
        ("不可分类测试数", lambda a: a["aggregate"]["all_tasks"]["n_tests_unclassifiable"]),
        ("AST test_* 定义数（披露）", lambda a: a["aggregate"]["all_tasks"]["n_ast_test_defs"]),
    ]
    for label, getter in agg_rows:
        add(f"| {label} | " + " | ".join(_fmt(getter(arm)) for arm in report["arms"]) + " |")
    for cls in CLASSES:
        add(
            f"| `{cls}` 计数 / 占比 | "
            + " | ".join(
                f"{arm['aggregate']['all_tasks']['counts'][cls]} / "
                f"{_fmt_rate(arm['aggregate']['all_tasks']['rates'][f'{cls}_share'])}"
                for arm in report["arms"]
            )
            + " |"
        )
    add("")
    add("任务级汇总（同一分母披露）：")
    add("")
    add("| 指标 | " + " | ".join(f"`{arm['arm']}`" for arm in report["arms"]) + " |")
    add("|---|" + "---|" * len(report["arms"]))
    task_rows = [
        ("含 effective 测试的任务数", lambda a: a["aggregate"]["all_tasks"]["task_level"]["n_tasks_with_effective"]),
        ("含 misguided 测试的任务数", lambda a: a["aggregate"]["all_tasks"]["task_level"]["n_tasks_with_misguided"]),
        (
            "每任务 misguided 占比（mean/median）",
            lambda a: " / ".join(
                _fmt(x)
                for x in (
                    a["aggregate"]["all_tasks"]["task_level"]["per_task_misguided_fraction"]["mean"],
                    a["aggregate"]["all_tasks"]["task_level"]["per_task_misguided_fraction"]["median"],
                )
            ),
        ),
    ]
    for label, getter in task_rows:
        add(f"| {label} | " + " | ".join(str(getter(arm)) for arm in report["arms"]) + " |")
    add("")
    add("### 3.1 主分析集（40 缺陷程序：非 *_test 且 buggy≠fixed；41 口径兼容行见末行）")
    add("")
    add("| 指标 | " + " | ".join(f"`{arm['arm']}`" for arm in report["arms"]) + " |")
    add("|---|" + "---|" * len(report["arms"]))
    defect_rows = [
        (
            "任务行数（主分析集 / 41 口径）",
            lambda a: (
                f"{a['aggregate']['defect_programs']['n_tasks']} / "
                f"{a['aggregate']['defect_programs_41_convention']['n_tasks']}"
            ),
        ),
        ("ok 任务数", lambda a: a["aggregate"]["defect_programs"]["n_tasks_ok"]),
        ("可分类测试数（分母）", lambda a: a["aggregate"]["defect_programs"]["n_tests_classifiable"]),
        ("effective 占比", lambda a: _fmt_rate(a["aggregate"]["defect_programs"]["rates"]["effective_share"])),
        ("misguided 占比", lambda a: _fmt_rate(a["aggregate"]["defect_programs"]["rates"]["misguided_share"])),
        ("both_pass 占比", lambda a: _fmt_rate(a["aggregate"]["defect_programs"]["rates"]["both_pass_share"])),
        ("both_fail 占比", lambda a: _fmt_rate(a["aggregate"]["defect_programs"]["rates"]["both_fail_share"])),
    ]
    for label, getter in defect_rows:
        add(f"| {label} | " + " | ".join(str(getter(arm)) for arm in report["arms"]) + " |")
    add("")
    add("### 3.2 不可分类原因计数")
    add("")
    add("| 原因 | " + " | ".join(f"`{arm['arm']}`" for arm in report["arms"]) + " |")
    add("|---|" + "---|" * len(report["arms"]))
    for reason in UNCLASSIFIABLE_REASONS:
        add(
            f"| `{reason}` | "
            + " | ".join(
                str(arm["aggregate"]["all_tasks"]["unclassifiable_counts"].get(reason, 0)) for arm in report["arms"]
            )
            + " |"
        )
    add("")
    add("### 3.3 结构跳过原因分布")
    add("")
    add("| 原因 | " + " | ".join(f"`{arm['arm']}`" for arm in report["arms"]) + " |")
    add("|---|" + "---|" * len(report["arms"]))
    skip_reasons = sorted({r for arm in report["arms"] for r in (arm.get("structural_skip_reasons") or {})})
    for reason in skip_reasons:
        add(
            f"| `{reason}` | "
            + " | ".join(str((arm.get("structural_skip_reasons") or {}).get(reason, 0)) for arm in report["arms"])
            + " |"
        )
    add("")
    comparison = report.get("comparison")
    if comparison:
        add("## 4. 臂间描述性对比")
        add("")
        add("臂：" + "；".join(f"`{a['label']}`（`{a['artifact']}`）" for a in (comparison.get("arms") or [])))
        add("")
        for pair in comparison.get("pairs") or []:
            label_a = pair["arm_a"]["label"]
            label_b = pair["arm_b"]["label"]
            add(f"**{label_a} → {label_b}**（`delta_pp` = B − A，百分点；缺陷程序主分析集口径，行数见 §3.1）：")
            add("")
            add(f"| 指标 | `{label_a}` | `{label_b}` | delta_pp |")
            add("|---|---|---|---|")
            defect_cmp = pair.get("per_test_defect_programs") or {}
            for cls in CLASSES:
                entry = defect_cmp.get(cls) or {}
                add(
                    f"| `{cls}_share` | {_fmt_rate(entry.get('arm_a'))} | {_fmt_rate(entry.get('arm_b'))} | "
                    f"{_fmt(entry.get('delta_pp_b_minus_a'))} |"
                )
            add(
                f"| 可分类测试数 | {pair['per_test_all_tasks']['n_tests_classifiable']['arm_a']} | "
                f"{pair['per_test_all_tasks']['n_tests_classifiable']['arm_b']} | — |"
            )
            tl = pair["task_level_all_tasks"]
            add(
                f"| 含 effective 测试的任务数 | {tl['n_tasks_with_effective']['arm_a']} | "
                f"{tl['n_tasks_with_effective']['arm_b']} | — |"
            )
            add(
                f"| 含 misguided 测试的任务数 | {tl['n_tasks_with_misguided']['arm_a']} | "
                f"{tl['n_tasks_with_misguided']['arm_b']} | — |"
            )
            add("")
        add("> " + comparison["interpretation_disclaimer"])
        add("")
    add("## 5. 与工件既有字段的交叉校验")
    add("")
    add("| 对账项 | " + " | ".join(f"`{arm['arm']}`" for arm in report["arms"]) + " |")
    add("|---|" + "---|" * len(report["arms"]))
    keys = sorted({k for arm in report["arms"] for k in (arm["cross_check"]["detection_agreement_counts"] or {})})
    for key in keys:
        add(
            f"| detection 对账 `{key}` | "
            + " | ".join(
                str((arm["cross_check"]["detection_agreement_counts"] or {}).get(key, 0)) for arm in report["arms"]
            )
            + " |"
        )
    add("")
    add("`specificity_gate_verdict` 对账（归档 verdict 与重放 fixed 侧绿/红是否一致）：")
    add("")
    add("| 对账标签 | " + " | ".join(f"`{arm['arm']}`" for arm in report["arms"]) + " |")
    add("|---|" + "---|" * len(report["arms"]))
    vkeys = sorted({k for arm in report["arms"] for k in (arm["cross_check"]["verdict_agreement_counts"] or {})})
    for key in vkeys:
        add(
            f"| `{key}` | "
            + " | ".join(
                str((arm["cross_check"]["verdict_agreement_counts"] or {}).get(key, 0)) for arm in report["arms"]
            )
            + " |"
        )
    add("")
    add("archived `passed` 与重放 fixed 侧绿/红对账（`passed` 为归档字段，非本工具口径）：")
    add("")
    pkeys = sorted({k for arm in report["arms"] for k in (arm["cross_check"]["passed_vs_replay_fixed_green"] or {})})
    add("| 对账标签 | " + " | ".join(f"`{arm['arm']}`" for arm in report["arms"]) + " |")
    add("|---|" + "---|" * len(report["arms"]))
    for key in pkeys:
        add(
            f"| `{key}` | "
            + " | ".join(
                str((arm["cross_check"]["passed_vs_replay_fixed_green"] or {}).get(key, 0)) for arm in report["arms"]
            )
            + " |"
        )
    add("")
    for arm in report["arms"]:
        cc = arm["cross_check"]
        if cc["detection_disagreements"]:
            add(f"**`{arm['arm']}` detection 对账差异（{len(cc['detection_disagreements'])} 条）**：")
            add("")
            add("| task_id | 归档 | 重放 | 重放(strict) | 归因 |")
            add("|---|---|---|---|---|")
            for item in cc["detection_disagreements"]:
                add(
                    f"| `{item['task_id']}` | {_fmt(item['artifact_detection_rate'])} | "
                    f"{_fmt(item['replay_detection'])} | {_fmt(item['replay_detection_strict'])} | "
                    f"{item['reason']} |"
                )
            add("")
        if cc["verdict_disagreements"]:
            add(f"**`{arm['arm']}` verdict 对账差异（{len(cc['verdict_disagreements'])} 条）**：")
            add("")
            for item in cc["verdict_disagreements"]:
                add(f"- `{item['task_id']}`: {item['reason']}")
            add("")
    add("## 6. 结构跳过任务（不静默跳过）")
    add("")
    for arm in report["arms"]:
        skips = arm.get("structural_skips") or []
        add(f"**`{arm['arm']}`（{len(skips)} 个）**：")
        add("")
        if not skips:
            add("- 无")
        for item in skips:
            add(f"- `{item['task_id']}` [{item['analysis_set']}] `{item['reason']}`: {item['detail'][:240]}")
        add("")
    add("## 7. 逐任务明细")
    add("")
    for arm in report["arms"]:
        add(f"### `{arm['arm']}`")
        add("")
        add(
            "| task_id | 状态 | signal | collected | classifiable | eff | mis | bp | bf | timeout | skipped | other | "
            "归档det | 重放det | 归档verdict | verdict对账 |"
        )
        add("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for task in arm["tasks"]:
            counts = task.get("counts") or {}
            unc = task.get("unclassifiable") or {}
            add(
                f"| `{task['task_id']}` | {task['status']}"
                + (f" ({task['skip_reason']})" if task["status"] != "ok" else "")
                + f" | {_fmt(task.get('defect_signal'))}"
                + f" | {task.get('n_collected', 0)} | {task.get('n_classifiable', 0)}"
                f" | {counts.get('effective', 0)} | {counts.get('misguided', 0)}"
                f" | {counts.get('both_pass', 0)} | {counts.get('both_fail', 0)}"
                f" | {unc.get('timeout', 0)} | {unc.get('skipped', 0)}"
                f" | {sum(v for k, v in unc.items() if k not in {'timeout', 'skipped'})}"
                f" | {_fmt(task.get('artifact_detection_rate'))} | {_fmt(task.get('replay_detection'))}"
                f" | {task.get('artifact_verdict')} | {task.get('verdict_agreement')} |"
            )
        add("")
    add("## 8. 确定性声明")
    add("")
    determinism = run_meta.get("determinism") or {}
    add(f"- 报告 body 不含时间戳/墙钟（这些只进 run_meta）；body digest = `{run_meta.get('body_digest')}`。")
    if determinism:
        add(
            f"- 重复重放次数 `repeat={determinism.get('repeat')}`，各次 body digest："
            + "、".join(f"`{d}`" for d in determinism.get("body_digests") or [])
            + f"；**deterministic={determinism.get('deterministic')}**。"
        )
        if not determinism.get("deterministic"):
            add("- 差异路径（前 20 条，如实披露、不做静默平均）：")
            for path in (determinism.get("difference_paths") or [])[:20]:
                add(f"  - `{path}`")
    add("")
    add("## 9. 已知限制")
    add("")
    for item in report.get("limitations") or []:
        add(f"- {item}")
    add("")
    return "\n".join(lines) + "\n"


# ─── CLI 入口 ──────────────────────────────────────────────────────────────
def _build_arg_parser() -> argparse.ArgumentParser:
    """CLI 参数定义。"""
    parser = argparse.ArgumentParser(
        prog="misguided_metrics",
        description=(
            "ISSTA'26 口径 misguided/effective 逐测试三分度量：读批次 JSON 工件，"
            "对 buggy/fixed 两侧各跑一次生成测试（零 LLM），输出四分类报告。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--artifact",
        action="append",
        required=True,
        metavar="PATH",
        help="批次 benchmark JSON 工件（可重复；每份可含一个或多个臂）",
    )
    parser.add_argument(
        "--arm",
        action="append",
        default=[],
        metavar="NAME",
        help="只分析指定臂（可重复；缺省分析工件内全部臂）",
    )
    parser.add_argument("--out", required=True, metavar="DIR", help="输出目录")
    parser.add_argument(
        "--quixbugs-root",
        default=None,
        metavar="DIR",
        help="缺陷版源码根目录覆盖（含 python_programs/；缺省按缓存/data/env 顺序解析）",
    )
    parser.add_argument("--jobs", type=int, default=min(8, os.cpu_count() or 1), help="并行任务数（默认 min(8, CPU)）")
    parser.add_argument(
        "--per-test-timeout",
        type=float,
        default=10.0,
        metavar="SEC",
        help="pytest-timeout 单测超时秒数（0=不用插件，仅整文件墙钟；默认 10）",
    )
    parser.add_argument(
        "--collect-timeout", type=float, default=60.0, metavar="SEC", help="收集阶段墙钟上限（默认 60）"
    )
    parser.add_argument(
        "--file-timeout", type=float, default=120.0, metavar="SEC", help="整文件执行墙钟上限（默认 120）"
    )
    parser.add_argument("--limit", type=int, default=0, help="每个臂只分析前 N 个任务（0=全部；测试/冒烟用）")
    parser.add_argument("--repeat", type=int, default=1, help="整批重复次数（≥2 用于确定性验证；默认 1）")
    parser.add_argument("--skip-markdown", action="store_true", help="只写 JSON，不写 Markdown 报告")
    parser.add_argument("--quiet", action="store_true", help="不打印逐任务进度")
    return parser


def _resolve_selection(artifacts: list[Path], arms_requested: list[str]) -> list[dict[str, Any]]:
    """解析（工件, 臂）选择；校验重复工件/未知臂，返回按输入顺序的条目。"""
    entries: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for path in artifacts:
        resolved = str(path.resolve())
        if resolved in seen_paths:
            raise ArtifactError(f"工件重复传入: {path}")
        seen_paths.add(resolved)
        artifact = load_artifact(path)
        artifact["__path__"] = str(path)
        available = list_artifact_arms(artifact)
        selected = arms_requested or available
        unknown = sorted(set(selected) - set(available))
        if unknown:
            raise ArtifactError(f"工件 {path} 内不存在臂 {unknown}（可用: {available}）")
        entry = {
            "path": path,
            "artifact_label": _display_path(path),
            "sha256": sha256_file(path),
            "arms": selected,
            "data": artifact,
        }
        entries.append(entry)
    if not entries:
        raise ArtifactError("未提供任何工件")
    return entries


def _run_replay(
    selection: list[dict[str, Any]],
    *,
    roots: list[Path],
    config: dict[str, Any],
    jobs: int,
    limit: int,
    progress: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """执行完整重放，返回 (报告 body, 本次运行的易变元信息)。"""
    started = time.time()
    arms: list[dict[str, Any]] = []
    for entry in selection:
        for arm in entry["arms"]:
            rows = select_rows(entry["data"], arm)
            arms.append(
                build_arm_result(
                    artifact_path=entry["path"],
                    artifact_sha256=entry["sha256"],
                    artifact_label=entry["artifact_label"],
                    arm=arm,
                    rows=rows,
                    roots=roots,
                    pytest_timeout_s=float(config["per_test_timeout_s"]),
                    collect_timeout_s=float(config["collect_timeout_s"]),
                    file_timeout_s=float(config["file_timeout_s"]),
                    jobs=jobs,
                    limit=limit,
                    progress=progress,
                )
            )
    artifact_entries = [
        {
            "path": entry["artifact_label"],
            "sha256": entry["sha256"],
            "arms": [{"arm": arm, "n_rows": len(select_rows(entry["data"], arm))} for arm in entry["arms"]],
        }
        for entry in selection
    ]
    body = build_report(
        artifact_entries=artifact_entries,
        arms=arms,
        config=config,
        command=_command_line(),
    )
    meta = {
        "generated_at": _now_iso(),
        "tool_wall_s": round(time.time() - started, 3),
        "body_digest": body_digest(body),
    }
    return body, meta


def _command_line() -> list[str]:
    """当前进程的可复算命令行（统一写成 ``python -m experiments.misguided_metrics ...``）。"""
    return ["python", "-m", "experiments.misguided_metrics", *sys.argv[1:]]


def _determinism_meta(repeats: list[tuple[dict[str, Any], dict[str, Any]]]) -> dict[str, Any]:
    """多次重放的确定性元信息（body digest 比较 + 差异路径如实披露）。"""
    if len(repeats) <= 1:
        return {
            "repeat": len(repeats),
            "body_digests": [meta["body_digest"] for _, meta in repeats],
            "deterministic": True,
            "difference_paths": [],
            "note": "未做重复重放（--repeat 1）；确定性口径由单测锁定",
        }
    base_body = strip_volatile(repeats[0][0])
    digests = [meta["body_digest"] for _, meta in repeats]
    diffs: list[str] = []
    for body, _meta in repeats[1:]:
        diffs.extend(_diff_paths(base_body, strip_volatile(body)))
    deterministic = len(set(digests)) == 1
    return {
        "repeat": len(repeats),
        "body_digests": digests,
        "deterministic": deterministic,
        "difference_paths": diffs[:20],
        "note": "differences 仅出现在易变字段之外视为非确定性；生成测试自身随机源会导致分类漂移",
    }


def main(argv: list[str] | None = None) -> int:
    """CLI 主入口：解析 → 重放（可重复）→ 落盘 JSON/Markdown。"""
    args = _build_arg_parser().parse_args(argv)
    out_dir = Path(args.out)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        selection = _resolve_selection([Path(p) for p in args.artifact], list(args.arm or []))
    except MisguidedMetricsError as e:
        print(f"[misguided] 错误: {e}", file=sys.stderr)
        return 2
    roots = resolve_quixbugs_roots(args.quixbugs_root)
    pytest_timeout_ok = pytest_timeout_available()
    per_test_timeout = float(args.per_test_timeout)
    if per_test_timeout > 0 and not pytest_timeout_ok:
        print(
            "[misguided] 警告: pytest-timeout 不可用——回退整文件墙钟口径（超时测试整体单列 timeout）",
            file=sys.stderr,
        )
        per_test_timeout = 0.0
    config = {
        "per_test_timeout_s": per_test_timeout,
        "pytest_timeout_plugin_available": pytest_timeout_ok,
        "collect_timeout_s": float(args.collect_timeout),
        "file_timeout_s": float(args.file_timeout),
        "jobs": int(args.jobs),
        "limit": int(args.limit),
        "test_filename": TEST_FILENAME,
        "layout": "dual(flat+python_programs package)",
        "quixbugs_roots": [str(p) for p in roots],
        "pytest_version": _pytest_version(),
    }
    repeats: list[tuple[dict[str, Any], dict[str, Any]]] = []
    n_repeat = max(1, int(args.repeat))
    for index in range(n_repeat):
        if n_repeat > 1:
            print(f"[misguided] 确定性重放 {index + 1}/{n_repeat}", file=sys.stderr)
        body, meta = _run_replay(
            selection,
            roots=roots,
            config=config,
            jobs=int(args.jobs),
            limit=int(args.limit),
            progress=not args.quiet,
        )
        repeats.append((body, meta))
    body, meta = repeats[0]
    determinism = _determinism_meta(repeats)
    run_meta = {
        **meta,
        "argv": list(sys.argv),
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "determinism": determinism,
    }
    payload = {"schema_version": SCHEMA_VERSION, "report": body, "run_meta": run_meta}
    json_path = out_dir / "MISGUIDED_REPORT.json"
    atomic_write_json(str(json_path), payload)
    print(f"[misguided] JSON 报告: {json_path}", flush=True)
    if not args.skip_markdown:
        md_path = out_dir / "MISGUIDED_REPORT.md"
        atomic_write_text(str(md_path), render_markdown(body, run_meta))
        print(f"[misguided] Markdown 报告: {md_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
