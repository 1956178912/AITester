#!/usr/bin/env python3
"""A-11 编译率 / 执行率度量（零 LLM 重放，M 轮 T7-B）。

动机（独立评审 §10 A-11 / G12，2026-10-17）
==========================================
项目指标 schema 此前只有 detection / repair / false_fix 等**结果侧**指标，
没有把"生成的测试代码本身是否可编译、可执行"单列出来——独立评审主张实测
规格里 TestAgent 报编译率 99.11% / 执行率 97.46%，而本项目未报对应量。
本工具对**存量批次工件**做零 LLM 重放，按行度量：

    compile_rate = ast.parse 成功的生成测试行占比
    exec_rate    = pytest --collect-only 可收集且无 import/collection error
                   的行占比（nested_pytest_env + run_with_timeout；超时单列）

口径纪律
--------
1. **compile_rate**：``ast.parse(generated_test)`` 成功即编译成功。空
   ``generated_test`` 不是"编译失败"而是"无产物"，单列 ``empty_generated_test``
   并**排除在两率分母之外**（无物可编译/执行）；其余行进 compile 分母。
   同时报"编译成功但无 test_* 定义"数（n_no_test_defs，可编译≠可收集）。
2. **exec_rate**：对可编译行物化执行树后跑一次 ``pytest --collect-only``。
   可收集且无 import/collection error 即执行成功；超时（收集阶段墙钟）单列
   ``collect_timeout``，**不进 exec_rate 分母**（另给 ``exec_rate_excl_timeout``
   双口径）。不可执行原因逐类计数：``compile_syntax_error`` / ``import_error`` /
   ``syntax_error`` / ``collect_error`` / ``no_tests_collected`` /
   ``collect_timeout`` / ``material_incomplete`` / ``empty_generated_test``。
3. **材料不可重建 ≠ 测试不可执行**：跨文件 synthetic 任务的伴生模块代码
   不在归档 metadata 中（且合成发生器历史缓存漂移，不可靠重建）、
   ``task_metadata.fixed`` 为空 → 记 ``material_incomplete`` **排除**在
   exec 分母之外并披露覆盖缺口（不把"我们没材料"算成"测试坏了"）。
   单文件 synthetic 行用归档 gold fixed 代码物化目标模块（归档无缺陷版
   源码，如实标注 ``material_source=fixed_gold``）；QuixBugs 行优先用
   缺陷版源码（生产执行口径），缺缓存时回退归档 fixed。
4. **确定性**：报告 body 不含时间戳/墙钟；``--repeat ≥2`` 时比较 body
   digest（收集重放无随机源）。超时/失败如实单列，不做静默平均。
5. **与 TestAgent 99.11%/97.46% 的可比性**：不同数据集（QuixBugs /
   synthetic vs 其基准）、不同语言/判分脚本、不同"执行"定义（collect-only
   可收集 vs 全量运行）——**仅作方向参考，不横向断言优劣**。

覆盖（默认输入，全部为存量只读工件）
------------------------------------
- L 轮三臂：``experiments/results/emse_docstring_anchor_20261017/``
  （plain_llm_df / plain_llm_df_doc / plain_llm_df_doc_union）；
- df_spec 两臂：``experiments/results/emse_df_spec_20261016/``；
- main_batch 三臂 × 3 个种子：``experiments/results/main_batch/``
  （aitester / plain_llm / plain_llm_df，seed 42/43/44）。
字段不齐的行（如 main_batch 跨文件 synthetic 无目标源码）如实记
``material_incomplete`` 并披露，不 crash、不静默跳过。

输出
----
``--out`` 目录下写 ``COMPILE_EXEC_REPORT.json`` / ``.md``：输入 sha256、
复算命令、批次×臂×n×compile_rate×exec_rate 表、不可执行原因分布、分母披露、
确定性声明、限制。

用法示例::

    nice -n 15 .venv/bin/python -m experiments.compile_exec_metrics \\
        --out experiments/results/emse_compile_exec_20261017 --jobs 4 --repeat 2
"""

from __future__ import annotations

import argparse
import ast
import concurrent.futures
import os
import re
import shutil
import sys
import tempfile
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from experiments import misguided_metrics as mm  # noqa: E402
from experiments.misguided_metrics import (  # noqa: E402
    TEST_FILENAME,
    _classify_collection_failure,
    _display_path,
    _normalize_node_list,
    _now_iso,
    _pytest_version,
    _task_program,
    _truncate,
    body_digest,
    list_artifact_arms,
    load_artifact,
    resolve_buggy_source,
    resolve_quixbugs_roots,
    select_rows,
    sha256_file,
)
from src.utils.process_utils import nested_pytest_env, run_with_timeout  # noqa: E402

SCHEMA_VERSION = "compile_exec_metric/1"
TOOL_NAME = "experiments.compile_exec_metrics"
TOOL_VERSION = "1.0.0"

# 不可执行原因（单列、不进 exec 分母的原因有明确注释）
UNEXECUTABLE_REASONS: tuple[str, ...] = (
    "empty_generated_test",  # 无产物（不进 compile/exec 分母，单列）
    "material_incomplete",  # 材料不可重建（不进 exec 分母，单列）
    "compile_syntax_error",  # ast.parse 失败（进 exec 分母，计失败）
    "import_error",  # 收集期 import 失败（含相对 import）
    "syntax_error",  # 执行期语法错误（compile 侧已拦截，兜底）
    "collect_error",  # 其它收集期错误
    "no_tests_collected",  # 可编译但无 test_* 或全部跳过
    "collect_timeout",  # 收集阶段墙钟超时（不进 exec_rate 分母，单列）
)
_PY_IDENT_RE = mm._PY_IDENT_RE
DEFAULT_OUT = _REPO_ROOT / "experiments/results/emse_compile_exec_20261017"

# 报告 digest/重复运行比较时剔除的易变键（时间戳/墙钟；不含任何计数）
_VOLATILE_KEYS: frozenset[str] = frozenset(
    {"generated_at", "started_at", "finished_at", "wall_s", "total_wall_s", "duration_s", "elapsed_s", "timing"}
)


# ─── 批次注册（默认覆盖 L 轮三臂 + df_spec 两臂 + main_batch 三臂×3 seed） ─
@dataclass(frozen=True)
class BatchSpec:
    """一个批次工件（label 唯一；round 用于跨 seed 合并展示）。"""

    label: str
    path: Path
    round: str


_DOCSTRING_DIR = _REPO_ROOT / "experiments/results/emse_docstring_anchor_20261017"
_DF_SPEC_DIR = _REPO_ROOT / "experiments/results/emse_df_spec_20261016"
_MAIN_BATCH_DIR = _REPO_ROOT / "experiments/results/main_batch"


def default_batches() -> list[BatchSpec]:
    """默认批次清单（与任务书覆盖要求逐项对应；全部只读）。"""
    return [
        BatchSpec(
            "emse_docstring_anchor_df",
            _DOCSTRING_DIR / "benchmark_quixbugs_20261017_194444.json",
            "emse_docstring_anchor_20261017",
        ),
        BatchSpec(
            "emse_docstring_anchor_doc",
            _DOCSTRING_DIR / "benchmark_quixbugs_20261017_193626.json",
            "emse_docstring_anchor_20261017",
        ),
        BatchSpec(
            "emse_docstring_anchor_union",
            _DOCSTRING_DIR / "benchmark_quixbugs_20261017_201928.json",
            "emse_docstring_anchor_20261017",
        ),
        BatchSpec(
            "emse_df_spec_treatment",
            _DF_SPEC_DIR / "benchmark_quixbugs_20261016_232138.json",
            "emse_df_spec_20261016",
        ),
        BatchSpec(
            "emse_df_spec_control",
            _DF_SPEC_DIR / "benchmark_quixbugs_20261017_003023.json",
            "emse_df_spec_20261016",
        ),
        BatchSpec("main_batch_seed42", _MAIN_BATCH_DIR / "benchmark_synthetic_20261006_140906.json", "main_batch"),
        BatchSpec("main_batch_seed43", _MAIN_BATCH_DIR / "benchmark_synthetic_20261006_151907.json", "main_batch"),
        BatchSpec("main_batch_seed44", _MAIN_BATCH_DIR / "benchmark_synthetic_20261006_164357.json", "main_batch"),
    ]


# ─── 异常 ────────────────────────────────────────────────────────────────
class CompileExecError(Exception):
    """本工具的可预期错误（CLI 捕获后以非零码退出，不打印 traceback）。"""


# ─── 编译度量（纯函数） ───────────────────────────────────────────────────
def compile_generated_test(generated_test: Any) -> dict[str, Any]:
    """对一份生成测试做 ast 编译判定（compile_rate 的行级口径）。

    Args:
        generated_test: 归档的生成测试全文（可能为 None/空）。

    Returns:
        {"status": "ok"|"syntax_error"|"empty", "ok": bool, "empty": bool,
         "n_test_defs": int|None, "error": str|None}
    """
    text = str(generated_test or "")
    if not text.strip():
        return {"status": "empty", "ok": False, "empty": True, "n_test_defs": 0, "error": None}
    try:
        tree = ast.parse(text)
    except SyntaxError as e:
        location = f"line {e.lineno}" if e.lineno else "unknown line"
        return {
            "status": "syntax_error",
            "ok": False,
            "empty": False,
            "n_test_defs": None,
            "error": f"{e.msg} ({location})",
        }
    n_defs = sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
    )
    return {"status": "ok", "ok": True, "empty": False, "n_test_defs": n_defs, "error": None}


# ─── 执行（收集）度量 ──────────────────────────────────────────────────────
def classify_collect_result(
    rc: int | None,
    output: str,
    *,
    timed_out: bool,
    n_nodes: int,
) -> dict[str, Any]:
    """``pytest --collect-only`` 结果 → 执行率行级判定（纯函数，便于单测）。

    Args:
        rc: pytest 退出码（超时 → None）。
        output: stdout + stderr 合并文本（失败归因用）。
        timed_out: 是否收集阶段墙钟超时。
        n_nodes: 解析出的 node id 数。

    Returns:
        {"ok": bool|None, "reason": str|None, "detail": str}；
        超时/失败如实单列，不臆测成功。
    """
    if timed_out:
        return {"ok": None, "reason": "collect_timeout", "detail": "收集阶段墙钟超时（结果不可判，单列）"}
    if rc == 0 and n_nodes > 0:
        return {"ok": True, "reason": None, "detail": ""}
    if rc == 5 or (rc == 0 and n_nodes == 0):
        return {"ok": False, "reason": "no_tests_collected", "detail": "pytest 收集到 0 条测试（rc=5 或无 node）"}
    reason, detail = _classify_collection_failure(rc, output, False)
    if reason == "file_timeout":  # _classify 的该分支在本函数入口已由 timed_out 处理
        reason = "collect_timeout"
    return {"ok": False, "reason": reason, "detail": detail}


_DURATION_RE = re.compile(r"\bin \d+(?:\.\d+)?s\b")
_TMP_PREFIX_RE = re.compile(r"/var/folders/[^\s:]+|/tmp/[A-Za-z0-9_\-]+")


def sanitize_collect_detail(detail: str, version_dir: Path | None = None) -> str:
    """把收集失败详情中的**易变片段**替换为占位符（保证报告 body 确定性）。

    实测不确定源：pytest 摘要行含实际耗时（``no tests collected, 1 error in
    0.23s``）与临时目录路径（``/var/folders/...``），两次重放必然不同。
    这些是时间/环境噪声、不属于度量结论，故在进入报告 body 前统一规范化；
    ``--repeat`` 的确定性比较因此不会再被噪声干扰（不掩盖真实分类差异）。

    Args:
        detail: 原始失败详情（pytest 输出尾部）。
        version_dir: 本次执行的临时目录（替换为 ``<TMPDIR>``）。

    Returns:
        规范化后的详情文本。
    """
    text = str(detail or "")
    if version_dir is not None:
        text = text.replace(str(version_dir), "<TMPDIR>")
    text = _DURATION_RE.sub("in <DURATION>s", text)
    return _TMP_PREFIX_RE.sub("<TMPDIR>", text)


def run_collect_replay(
    version_dir: Path,
    *,
    pythonpath: list[str],
    timeout_s: float,
    python_exe: str | None = None,
) -> dict[str, Any]:
    """在已物化的执行树里跑一次 ``pytest --collect-only``（零执行、零网络）。

    Returns:
        {"ok", "reason", "detail", "rc", "timed_out", "n_collected",
         "parser", "output_head", "timing": {"wall_s"}}。
    """
    python_exe = python_exe or sys.executable
    env = nested_pytest_env(
        PYTHONPATH=os.pathsep.join([str(p) for p in pythonpath]),
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONHASHSEED="0",
        PYTHONUNBUFFERED="1",
        COLUMNS="200",
    )
    common = ["-p", "no:cacheprovider", "-p", "no:randomly", "--no-header", "--color=no"]
    cmd = [python_exe, "-m", "pytest", TEST_FILENAME, "--collect-only", "-q", *common]
    t0 = time.time()
    res = run_with_timeout(
        cmd,
        timeout=timeout_s,
        cwd=str(version_dir),
        text=True,
        logger_name="compile_exec_collect",
        env=env,
    )
    wall = round(time.time() - t0, 3)
    stdout = res.stdout or ""
    stderr = res.stderr or ""
    output = stdout + "\n" + stderr
    timed_out = bool(getattr(res, "timed_out", False))
    rc = None if timed_out else res.returncode
    nodes = _normalize_node_list(stdout)
    verdict = classify_collect_result(rc, output, timed_out=timed_out, n_nodes=len(nodes))
    return {
        **verdict,
        "detail": sanitize_collect_detail(str(verdict.get("detail") or ""), version_dir),
        "rc": rc,
        "timed_out": timed_out,
        "n_collected": len(nodes),
        "parser": "collect_only_q",
        "output_head": sanitize_collect_detail(_truncate(output, 400), version_dir),
        "timing": {"wall_s": wall},
    }


# ─── 执行树物化（材料可重建性判定 + 落盘） ────────────────────────────────
def find_quixbugs_support_root(roots: list[Path]) -> Path | None:
    """在候选根目录中找带辅助材料（python_testcases/node.py）的 QuixBugs 根。"""
    for root in roots:
        if (root / "python_testcases" / "node.py").is_file():
            return root
    return None


def classify_material(
    row: dict[str, Any],
    *,
    roots: list[Path],
) -> dict[str, Any]:
    """判定一行执行材料是否可重建（纯函数，不落盘）。

    Returns:
        {"ok": bool, "reason": str|None, "layout": "quixbugs"|"flat"|None,
         "module_name": str|None, "target_code": str|None,
         "material_source": "buggy"|"fixed_gold"|None,
         "support_root": str|None, "detail": str}
    """
    raw_meta = row.get("task_metadata")
    task_metadata: dict[str, Any] = raw_meta if isinstance(raw_meta, dict) else {}
    task_id = str(row.get("task_id") or "")
    program = _task_program(task_id, task_metadata)
    module_name = task_id.split("__")[-1].replace("-", "_")[:50] if task_id else ""
    detail = ""
    source = str(task_metadata.get("source") or "").strip().lower()
    is_cross_file = bool(task_metadata.get("is_cross_file"))
    fixed_code = str(task_metadata.get("fixed") or "")
    target_code: str | None = None
    material_source: str | None = None
    layout: str | None = None
    if source == "quixbugs":
        layout = "quixbugs"
        try:
            buggy_code, _buggy_path = resolve_buggy_source(program, roots)
        except mm.MaterialError as e:
            detail = f"缺陷版源码缺失（{e.detail[:200]}）；回退归档 fixed"
            buggy_code = ""
        if buggy_code.strip():
            target_code = buggy_code
            material_source = "buggy"
        elif fixed_code.strip():
            target_code = fixed_code
            material_source = "fixed_gold"
        if target_code is None:
            return {
                "ok": False,
                "reason": "material_incomplete",
                "layout": None,
                "module_name": module_name or None,
                "target_code": None,
                "material_source": None,
                "support_root": None,
                "detail": detail or "缺陷版源码与归档 fixed 均缺失",
            }
        support_root = find_quixbugs_support_root(roots)
        if not module_name or not _PY_IDENT_RE.match(module_name):
            return {
                "ok": False,
                "reason": "material_incomplete",
                "layout": None,
                "module_name": module_name or None,
                "target_code": target_code,
                "material_source": material_source,
                "support_root": None,
                "detail": f"模块名不是合法 Python 标识符: {module_name!r}",
            }
        return {
            "ok": True,
            "reason": None,
            "layout": layout,
            "module_name": module_name,
            "target_code": target_code,
            "material_source": material_source,
            "support_root": str(support_root) if support_root else None,
            "detail": detail,
        }
    if is_cross_file:
        # 归档 metadata 不含伴生模块代码（module_a/b/c_code）且 fixed 为空；
        # 合成发生器历史缓存漂移（2026-10-17 实测 pattern/noise 不匹配），
        # 不可靠重建 → 记材料不完整，排除 exec 分母（不误判为测试不可执行）。
        return {
            "ok": False,
            "reason": "material_incomplete",
            "layout": None,
            "module_name": module_name or None,
            "target_code": None,
            "material_source": None,
            "support_root": None,
            "detail": "跨文件 synthetic 任务缺伴生模块材料（归档无 module_*_code 且 fixed 为空）",
        }
    if not fixed_code.strip():
        return {
            "ok": False,
            "reason": "material_incomplete",
            "layout": None,
            "module_name": module_name or None,
            "target_code": None,
            "material_source": None,
            "support_root": None,
            "detail": "归档 task_metadata.fixed 为空（无目标模块材料）",
        }
    if not module_name or not _PY_IDENT_RE.match(module_name):
        return {
            "ok": False,
            "reason": "material_incomplete",
            "layout": None,
            "module_name": module_name or None,
            "target_code": fixed_code,
            "material_source": "fixed_gold",
            "support_root": None,
            "detail": f"模块名不是合法 Python 标识符: {module_name!r}",
        }
    return {
        "ok": True,
        "reason": None,
        "layout": "flat",
        "module_name": module_name,
        "target_code": fixed_code,
        "material_source": "fixed_gold",
        "support_root": None,
        "detail": "归档无缺陷版源码，目标模块用 gold fixed 代码物化（仅影响 import 解析，不参与判定）",
    }


def materialize_exec_tree(material: dict[str, Any], version_dir: Path, generated_test: str) -> list[str]:
    """按 material 判定落盘执行树（目标模块 + 生成测试文件），返回 PYTHONPATH。

    - ``quixbugs`` 布局：平铺 ``{module}.py`` + ``python_programs/{module}.py``
      双布局（生产平铺 import 与官方包结构 import 均可解析），并复制
      QuixBugs 辅助模块（node.py / load_testdata.py / json_testcases）。
    - ``flat`` 布局：仅平铺 ``{module}.py``（synthetic 单文件口径）。

    Raises:
        OSError: 物化失败（调用方归因为 ``materialize_failed``）。
    """
    version_dir.mkdir(parents=True, exist_ok=True)
    module_name = str(material["module_name"])
    target_code = str(material["target_code"])
    version_dir.joinpath(f"{module_name}.py").write_text(target_code, encoding="utf-8")
    version_dir.joinpath(TEST_FILENAME).write_text(str(generated_test), encoding="utf-8")
    pythonpath = [str(version_dir)]
    if material["layout"] == "quixbugs":
        package_dir = version_dir / "python_programs"
        package_dir.mkdir(exist_ok=True)
        (package_dir / "__init__.py").write_text("", encoding="utf-8")
        (package_dir / f"{module_name}.py").write_text(target_code, encoding="utf-8")
        (version_dir / "conftest.py").write_text(
            "import pytest\n\npytest.use_correct = False\npytest.run_slow = False\n",
            encoding="utf-8",
        )
        support_root = Path(str(material.get("support_root") or "")) if material.get("support_root") else None
        testcases_dir = version_dir / "python_testcases"
        testcases_dir.mkdir(exist_ok=True)
        if support_root is not None and support_root.is_dir():
            for aux in ("node.py", "load_testdata.py"):
                src = support_root / "python_testcases" / aux
                if src.is_file():
                    shutil.copy(str(src), str(testcases_dir / aux))
                    shutil.copy(str(src), str(version_dir / aux))
            src_json = support_root / "json_testcases"
            if src_json.is_dir():
                shutil.copytree(str(src_json), str(version_dir / "json_testcases"))
        pythonpath.append(str(testcases_dir))
    return pythonpath


# ─── 单行分析 ──────────────────────────────────────────────────────────────
def analyze_row(
    row: dict[str, Any],
    *,
    batch_label: str,
    round_name: str,
    arm: str,
    roots: list[Path],
    collect_timeout_s: float,
) -> dict[str, Any]:
    """分析一行：编译 → 材料判定 → 收集重放（不执行测试）。"""
    task_id = str(row.get("task_id") or "")
    raw_meta = row.get("task_metadata")
    task_metadata: dict[str, Any] = raw_meta if isinstance(raw_meta, dict) else {}
    record: dict[str, Any] = {
        "task_id": task_id or "(缺失 task_id)",
        "program": _task_program(task_id, task_metadata) or None,
        "batch": batch_label,
        "round": round_name,
        "arm": arm,
        "status": "ok",
        "skip_reason": None,
        "compile": {"status": None, "ok": None, "empty": None, "n_test_defs": None, "error": None},
        "material": {
            "ok": None,
            "reason": None,
            "layout": None,
            "module_name": None,
            "material_source": None,
            "detail": "",
        },
        "exec": {
            "attempted": False,
            "ok": None,
            "reason": None,
            "detail": "",
            "rc": None,
            "timed_out": False,
            "n_collected": 0,
        },
        "timing": {"wall_s": 0.0},
    }
    t_total = time.time()
    if not task_id or not task_metadata:
        record["status"] = "malformed"
        record["skip_reason"] = "artifact_row_malformed"
        record["timing"]["wall_s"] = round(time.time() - t_total, 3)
        return record
    compile_info = compile_generated_test(row.get("generated_test"))
    record["compile"] = compile_info
    if compile_info["empty"]:
        record["status"] = "empty_generated_test"
        record["material"] = {**record["material"], "ok": False, "reason": "empty_generated_test"}
        record["timing"]["wall_s"] = round(time.time() - t_total, 3)
        return record
    material = classify_material(row, roots=roots)
    record["material"] = {
        "ok": material["ok"],
        "reason": material["reason"],
        "layout": material["layout"],
        "module_name": material["module_name"],
        "material_source": material["material_source"],
        "detail": material["detail"],
    }
    if not material["ok"]:
        record["status"] = "material_incomplete"
        record["skip_reason"] = material["reason"]
        record["timing"]["wall_s"] = round(time.time() - t_total, 3)
        return record
    if not compile_info["ok"]:
        record["status"] = "compile_syntax_error"
        record["exec"].update(
            {"attempted": False, "ok": False, "reason": "compile_syntax_error", "detail": compile_info["error"] or ""}
        )
        record["timing"]["wall_s"] = round(time.time() - t_total, 3)
        return record
    tmpdir = Path(tempfile.mkdtemp(prefix=f"compile_exec_{material['module_name']}_"))
    try:
        try:
            pythonpath = materialize_exec_tree(material, tmpdir, str(row.get("generated_test") or ""))
        except OSError as e:
            record["status"] = "materialize_failed"
            record["skip_reason"] = "materialize_failed"
            record["material"]["ok"] = False
            record["material"]["detail"] = f"物化执行树失败: {e}"
            record["timing"]["wall_s"] = round(time.time() - t_total, 3)
            return record
        collect = run_collect_replay(tmpdir, pythonpath=pythonpath, timeout_s=collect_timeout_s)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    record["exec"] = {
        "attempted": True,
        "ok": collect["ok"],
        "reason": collect["reason"],
        "detail": collect["detail"],
        "rc": collect["rc"],
        "timed_out": collect["timed_out"],
        "n_collected": collect["n_collected"],
    }
    record["timing"]["wall_s"] = round(time.time() - t_total, 3)
    return record


# ─── 聚合 ──────────────────────────────────────────────────────────────────
def _empty_aggregate() -> dict[str, Any]:
    """空聚合骨架（键集合同构；便于测试与合并）。"""
    return {
        "n_rows": 0,
        "n_malformed": 0,
        "n_empty_generated_test": 0,
        "n_compile_denominator": 0,
        "n_compile_ok": 0,
        "n_no_test_defs": 0,
        "n_material_incomplete": 0,
        "n_exec_attempted": 0,
        "n_exec_ok": 0,
        "n_collect_timeout": 0,
        "n_exec_denominator_excl_timeout": 0,
        "compile_rate": None,
        "exec_rate": None,
        "exec_rate_excl_timeout": None,
        "n_driver_task_rows": 0,
        "compile_rate_excl_driver_tasks": None,
        "exec_rate_excl_driver_tasks": None,
        "n_compile_ok_excl_driver_tasks": 0,
        "n_compile_denominator_excl_driver_tasks": 0,
        "n_exec_ok_excl_driver_tasks": 0,
        "n_exec_attempted_excl_driver_tasks": 0,
        "reason_counts": {},
        "material_source_counts": {},
    }


def _aggregate_counts_without_driver(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """复用 aggregate_rows 计算"排除驱动任务"子集的分母/比率（内部工具）。

    为避免递归（aggregate_rows 内会再调用本函数），该子集不受驱动任务
    影响（rows 已排除），其 ``n_driver_task_rows`` 恒 0。
    """
    # 直接复制主聚合逻辑的最小子集（compile/exec 两率），保持分母纪律一致。
    n_compile_denom = 0
    n_compile_ok = 0
    n_material_incomplete = 0
    n_exec_attempted = 0
    n_exec_ok = 0
    for row in rows:
        if row.get("status") == "malformed":
            continue
        compile_info = row.get("compile") or {}
        if compile_info.get("empty"):
            continue
        n_compile_denom += 1
        if compile_info.get("ok"):
            n_compile_ok += 1
        if not (row.get("material") or {}).get("ok"):
            n_material_incomplete += 1
            continue
        if not compile_info.get("ok"):
            continue
        n_exec_attempted += 1
        if (row.get("exec") or {}).get("ok") is True:
            n_exec_ok += 1
    return {
        "n_compile_denominator": n_compile_denom,
        "n_compile_ok": n_compile_ok,
        "n_material_incomplete": n_material_incomplete,
        "n_exec_attempted": n_exec_attempted,
        "n_exec_ok": n_exec_ok,
        "compile_rate": round(n_compile_ok / n_compile_denom, 6) if n_compile_denom else None,
        "exec_rate": round(n_exec_ok / n_exec_attempted, 6) if n_exec_attempted else None,
    }


def aggregate_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """行级聚合 → compile_rate / exec_rate（分母纪律显式披露）。"""
    agg = _empty_aggregate()
    reasons: Counter[str] = Counter()
    material_sources: Counter[str] = Counter()
    for row in rows:
        agg["n_rows"] += 1
        if row.get("status") == "malformed":
            agg["n_malformed"] += 1
            continue
        compile_info = row.get("compile") or {}
        material = row.get("material") or {}
        collect = row.get("exec") or {}
        if compile_info.get("empty"):
            agg["n_empty_generated_test"] += 1
            reasons["empty_generated_test"] += 1
            continue
        agg["n_compile_denominator"] += 1
        if compile_info.get("ok"):
            agg["n_compile_ok"] += 1
            if compile_info.get("n_test_defs") == 0:
                agg["n_no_test_defs"] += 1
        if material.get("material_source"):
            material_sources[str(material["material_source"])] += 1
        if not material.get("ok"):
            agg["n_material_incomplete"] += 1
            reasons["material_incomplete"] += 1
            continue
        if not compile_info.get("ok"):
            reasons["compile_syntax_error"] += 1
            continue
        agg["n_exec_attempted"] += 1
        if collect.get("ok") is True:
            agg["n_exec_ok"] += 1
            continue
        reason = str(collect.get("reason") or "collect_error")
        if reason == "no_tests_collected" and compile_info.get("n_test_defs") == 0:
            reasons["no_tests_collected"] += 1
        else:
            reasons[reason] += 1
        if collect.get("timed_out"):
            agg["n_collect_timeout"] += 1
        elif reason not in {"no_collected", "file_timeout"}:
            pass
    agg["n_exec_denominator_excl_timeout"] = agg["n_exec_attempted"] - agg["n_collect_timeout"]
    if agg["n_compile_denominator"]:
        agg["compile_rate"] = round(agg["n_compile_ok"] / agg["n_compile_denominator"], 6)
    if agg["n_exec_attempted"]:
        agg["exec_rate"] = round(agg["n_exec_ok"] / agg["n_exec_attempted"], 6)
    if agg["n_exec_denominator_excl_timeout"]:
        agg["exec_rate_excl_timeout"] = round(agg["n_exec_ok"] / agg["n_exec_denominator_excl_timeout"], 6)
    # 敏感性口径（quixbugs 特有）：9 个 *_test 驱动任务在平铺执行口径下因
    # 相对 import 结构性不可收集（与归档 detection=None 同源）。主口径把它们
    # 作为真实不可执行计入；这里另给"排除驱动任务"的敏感性比率（对
    # synthetic 批次无 *_test 任务，两口径相同）。
    driver_rows = [row for row in rows if str(row.get("task_id") or "").endswith("_test")]
    non_driver = [row for row in rows if not str(row.get("task_id") or "").endswith("_test")]
    driver_agg = _aggregate_counts_without_driver(non_driver)
    agg["n_driver_task_rows"] = len(driver_rows)
    agg["compile_rate_excl_driver_tasks"] = driver_agg["compile_rate"]
    agg["exec_rate_excl_driver_tasks"] = driver_agg["exec_rate"]
    agg["n_compile_ok_excl_driver_tasks"] = driver_agg["n_compile_ok"]
    agg["n_compile_denominator_excl_driver_tasks"] = driver_agg["n_compile_denominator"]
    agg["n_exec_ok_excl_driver_tasks"] = driver_agg["n_exec_ok"]
    agg["n_exec_attempted_excl_driver_tasks"] = driver_agg["n_exec_attempted"]
    agg["reason_counts"] = dict(sorted(reasons.items()))
    agg["material_source_counts"] = dict(sorted(material_sources.items()))
    return agg


# ─── 报告 ──────────────────────────────────────────────────────────────────
def default_metric_definition() -> dict[str, Any]:
    """口径定义（报告与文档共用同一文本源）。"""
    return {
        "name": "A-11 编译率 / 执行率（零 LLM 重放）",
        "compile_rate": (
            "ast.parse(generated_test) 成功的行占比；分母 = 全部行 − 空 generated_test（空产物单列，不算编译失败）"
        ),
        "exec_rate": (
            "物化执行树后 `pytest --collect-only` 可收集（rc==0 且 node>0）的行占比；"
            "分母 = 编译成功行 − 材料不可重建行（material_incomplete 单列，不算测试失败）；"
            "收集阶段超时（collect_timeout）单列、不进 exec_rate 分母（另给 excl_timeout 口径）"
        ),
        "this_protocol": "pytest --collect-only（仅收集，不执行测试用例：执行错误与失败不属本指标）",
        "unexecutable_reasons": list(UNEXECUTABLE_REASONS),
        "denominator_discipline": (
            "每个比率均报分母；空产物 / 材料不完整 / 收集超时三类**不混入** exec_rate 分母，"
            "在 reason_counts 与 n_* 字段单列；跨 seed 合并按计数重新计算比率（不做比率平均）"
        ),
        "testagent_comparability": (
            "独立评审引 TestAgent 编译率 99.11% / 执行率 97.46%；本项目与其数据集"
            "（QuixBugs/synthetic vs 其基准）、语言/工具链、执行定义（collect-only vs 全量运行）"
            "均不同——**仅作方向参考，不横向断言优劣**"
        ),
        "evidence_status": "描述性工程度量（指标 schema 缺口补齐）；非预注册确认性证据",
    }


def build_report(
    *,
    inputs: list[dict[str, Any]],
    batch_results: list[dict[str, Any]],
    pooled: list[dict[str, Any]],
    config: dict[str, Any],
    command: list[str],
) -> dict[str, Any]:
    """组装确定性报告 body（时间戳/墙钟只进 run_meta）。"""
    return {
        "schema_version": SCHEMA_VERSION,
        "tool": {"name": TOOL_NAME, "version": TOOL_VERSION},
        "metric_definition": default_metric_definition(),
        "config": config,
        "command": command,
        "inputs": inputs,
        "batches": batch_results,
        "pooled_by_round_arm": pooled,
        "limitations": [
            "exec_rate 仅衡量 pytest 可收集/可 import，不衡量测试执行通过率或检出能力（后者见 M1/机制指标）",
            "main_batch 跨文件 synthetic 行缺伴生模块与目标源码材料（归档 metadata 无 module_*_code、fixed 为空；"
            "合成发生器历史缓存漂移不可靠重建）→ material_incomplete 单列、排除 exec 分母，覆盖缺口如实披露",
            "单文件 synthetic 行归档无缺陷版源码，目标模块用 gold fixed 代码物化（仅影响 import 解析，不参与判定）",
            "QuixBugs 9 个 *_test 驱动任务在平铺执行口径下因相对 import 结构性不可收集（与归档 detection=None 同源），"
            "作为真实不可执行计入 exec_rate；排除后的敏感性口径见报告 §3.1（四臂均 100%）",
            "收集重放失败/超时按原因单列，不并入成功；分类定义不因失败而调整",
            "不同批次/臂的生成测试可能依赖宿主 pytest 插件行为；已用 nested_pytest_env 剔除宿主 PYTEST_PLUGINS/PYTEST_ADDOPTS",
            "与 TestAgent 数字仅方向参考（数据集/语言/执行定义不同），不做横向断言",
        ],
    }


# ─── Markdown 渲染 ─────────────────────────────────────────────────────────
def _fmt_rate(value: Any) -> str:
    """比率 → 百分比字符串（None → "—"）。"""
    if value is None:
        return "—"
    return f"{float(value) * 100:.2f}%"


def _fmt_rate_pair(ok: Any, denom: Any) -> str:
    """计数/分母 + 百分比（分母 0/None → "—"）。"""
    if not denom:
        return "—"
    return f"{_fmt_rate(float(ok) / float(denom))}（{ok}/{denom}）"


def render_markdown(report: dict[str, Any], run_meta: dict[str, Any]) -> str:
    """渲染 Markdown 报告（确定性；时间戳/墙钟只从 run_meta 读）。"""
    lines: list[str] = []
    add = lines.append
    add("# A-11 编译率 / 执行率报告（零 LLM 重放）")
    add("")
    add("> **性质**：描述性工程度量（指标 schema 缺口补齐），**非**预注册确认性证据。")
    add("> `exec_rate` 只衡量 pytest 可收集/可 import，不衡量测试执行通过率或检出能力。")
    add(f"> **生成时间**：{run_meta.get('generated_at')}　**body digest**：`{run_meta.get('body_digest')}`")
    add(f"> **工具**：{report['tool']['name']} v{report['tool']['version']}　**schema**：`{report['schema_version']}`")
    add("")
    add("复算命令：")
    add("")
    add("```bash")
    add(" ".join(str(x) for x in report.get("command") or []))
    add("```")
    add("")
    add("## 1. 输入工件（只读）")
    add("")
    add("| 批次 | 轮次 | 工件 | sha256 | 臂 |")
    add("|---|---|---|---|---|")
    for entry in report.get("inputs") or []:
        add(
            f"| `{entry['batch']}` | `{entry['round']}` | `{entry['path']}` | `{entry['sha256']}` | "
            + "、".join(f"`{a}`" for a in entry.get("arms") or [])
            + " |"
        )
    add("")
    add("## 2. 口径定义")
    add("")
    definition = report["metric_definition"]
    add(f"- **compile_rate**：{definition['compile_rate']}")
    add(f"- **exec_rate**：{definition['exec_rate']}")
    add(f"- **执行协议**：{definition['this_protocol']}")
    add(f"- **分母纪律**：{definition['denominator_discipline']}")
    add(f"- **外部可比性**：{definition['testagent_comparability']}")
    add("")
    add("## 3. 主表（批次 × 臂）")
    add("")
    add("| 批次 | 轮次 | 臂 | n | compile 分母 | compile_rate | exec 分母 | exec_rate | exec_rate(excl. timeout) |")
    add("|---|---|---|---|---|---|---|---|---|")
    for batch in report.get("batches") or []:
        for arm in batch.get("arms") or []:
            agg = arm["aggregate"]
            add(
                f"| `{batch['label']}` | `{batch['round']}` | `{arm['arm']}` | {agg['n_rows']} | "
                f"{agg['n_compile_denominator']} | {_fmt_rate_pair(agg['n_compile_ok'], agg['n_compile_denominator'])} | "
                f"{agg['n_exec_attempted']} | {_fmt_rate_pair(agg['n_exec_ok'], agg['n_exec_attempted'])} | "
                f"{_fmt_rate(agg['exec_rate_excl_timeout'])}（{agg['n_exec_ok']}/{agg['n_exec_denominator_excl_timeout']}） |"
            )
    add("")
    add("说明：compile 分母 = 全部行 − 空 generated_test；exec 分母 = 编译成功行 − 材料不可重建行。")
    add("")
    add("### 3.1 敏感性：排除 QuixBugs *_test 驱动任务（结构性不可收集）")
    add("")
    add(
        "QuixBugs 的 9 个 `*_test` 驱动任务在平铺执行口径下因相对 import 结构性不可收集"
        "（与归档 detection=None 同源），主口径计入 exec_rate；下表给出排除后的敏感性"
        "（synthetic 批次无 `*_test` 任务，两口径相同）："
    )
    add("")
    add("| 批次 | 臂 | 驱动任务行数 | compile_rate(excl.) | exec_rate(excl.) |")
    add("|---|---|---|---|---|")
    for batch in report.get("batches") or []:
        for arm in batch.get("arms") or []:
            agg = arm["aggregate"]
            add(
                f"| `{batch['label']}` | `{arm['arm']}` | {agg.get('n_driver_task_rows', 0)} | "
                f"{_fmt_rate_pair(agg.get('n_compile_ok_excl_driver_tasks', 0), agg.get('n_compile_denominator_excl_driver_tasks', 0))} | "
                f"{_fmt_rate_pair(agg.get('n_exec_ok_excl_driver_tasks', 0), agg.get('n_exec_attempted_excl_driver_tasks', 0))} |"
            )
    add("")
    add("## 4. 不可执行原因分布")
    add("")
    reasons = sorted(
        {
            r
            for batch in report.get("batches") or []
            for arm in batch.get("arms") or []
            for r in (arm["aggregate"]["reason_counts"] or {})
        }
    )
    add("| 批次 | 臂 | " + " | ".join(f"`{reason}`" for reason in reasons) + " |")
    add("|---|---|" + "---|" * len(reasons))
    for batch in report.get("batches") or []:
        for arm in batch.get("arms") or []:
            counts = arm["aggregate"].get("reason_counts") or {}
            add(
                f"| `{batch['label']}` | `{arm['arm']}` | "
                + " | ".join(str(counts.get(reason, 0)) for reason in reasons)
                + " |"
            )
    add("")
    add("## 5. 合并表（轮次 × 臂；跨 seed 按计数重算，不做比率平均）")
    add("")
    add("| 轮次 | 臂 | 批次数 | n | compile_rate | exec_rate | exec_rate(excl. timeout) |")
    add("|---|---|---|---|---|---|---|")
    for row in report.get("pooled_by_round_arm") or []:
        agg = row["aggregate"]
        add(
            f"| `{row['round']}` | `{row['arm']}` | {row['n_batches']} | {agg['n_rows']} | "
            f"{_fmt_rate_pair(agg['n_compile_ok'], agg['n_compile_denominator'])} | "
            f"{_fmt_rate_pair(agg['n_exec_ok'], agg['n_exec_attempted'])} | "
            f"{_fmt_rate(agg['exec_rate_excl_timeout'])} |"
        )
    add("")
    add("## 6. 确定性 / 墙钟")
    add("")
    determinism = run_meta.get("determinism") or {}
    add(f"- body digest：`{run_meta.get('body_digest')}`（不含时间戳/墙钟）")
    add(
        f"- repeat={determinism.get('repeat')}；deterministic={determinism.get('deterministic')}；"
        f"各次 digest={determinism.get('body_digests')}"
    )
    if not determinism.get("deterministic"):
        for path in (determinism.get("difference_paths") or [])[:20]:
            add(f"  - 差异路径：`{path}`")
    add(f"- 本次重放墙钟：{run_meta.get('tool_wall_s')} s（只进 run_meta）")
    add("")
    add("## 7. 已知限制")
    add("")
    for item in report.get("limitations") or []:
        add(f"- {item}")
    add("")
    return "\n".join(lines) + "\n"


# ─── CLI 入口 ──────────────────────────────────────────────────────────────
def _build_arg_parser() -> argparse.ArgumentParser:
    """CLI 参数定义。"""
    parser = argparse.ArgumentParser(
        prog="compile_exec_metrics",
        description=(
            "A-11 编译率/执行率：对存量批次工件的 generated_test 做零 LLM 重放"
            "（ast.parse + pytest --collect-only），输出批次×臂表与原因分布。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--batch",
        action="append",
        default=[],
        metavar="LABEL=PATH[,ROUND]",
        help="批次工件覆盖（可重复；缺省 = L 轮三臂 + df_spec 两臂 + main_batch 三臂×3 seed）",
    )
    parser.add_argument("--arm", action="append", default=[], metavar="NAME", help="只分析指定臂（可重复）")
    parser.add_argument("--out", default=str(DEFAULT_OUT), metavar="DIR", help="输出目录")
    parser.add_argument(
        "--quixbugs-root",
        default=None,
        metavar="DIR",
        help="缺陷版源码根目录覆盖（含 python_programs/；缺省按缓存/data/env 顺序解析）",
    )
    parser.add_argument("--jobs", type=int, default=min(4, os.cpu_count() or 1), help="并行任务数（默认 min(4, CPU)）")
    parser.add_argument(
        "--collect-timeout", type=float, default=60.0, metavar="SEC", help="收集阶段墙钟上限（默认 60）"
    )
    parser.add_argument("--limit", type=int, default=0, help="每批次每臂只分析前 N 行（0=全部；测试/冒烟用）")
    parser.add_argument("--repeat", type=int, default=1, help="整批重复次数（≥2 用于确定性验证；默认 1）")
    parser.add_argument("--only-round", default=None, metavar="NAME", help="只跑指定 round 的批次")
    parser.add_argument("--skip-markdown", action="store_true", help="只写 JSON，不写 Markdown")
    parser.add_argument("--quiet", action="store_true", help="不打印逐批次进度")
    return parser


def _parse_batch_arg(raw: str) -> BatchSpec:
    """解析 ``LABEL=PATH[,ROUND]`` 形式的 --batch 参数。"""
    if "=" not in raw:
        raise CompileExecError(f"--batch 需要 LABEL=PATH[,ROUND] 形式: {raw!r}")
    label, rest = raw.split("=", 1)
    parts = rest.rsplit(",", 1)
    path = Path(parts[0]).expanduser()
    round_name = parts[1] if len(parts) == 2 else label
    if not label.strip() or not str(path).strip():
        raise CompileExecError(f"--batch 参数为空: {raw!r}")
    return BatchSpec(label.strip(), path, round_name.strip() or label.strip())


def _resolve_batches(args: argparse.Namespace) -> list[BatchSpec]:
    """解析批次清单（默认注册或 CLI 覆盖）+ round 过滤。"""
    specs = [_parse_batch_arg(raw) for raw in args.batch] if args.batch else default_batches()
    if args.only_round:
        specs = [spec for spec in specs if spec.round == args.only_round]
    seen: set[str] = set()
    for spec in specs:
        if spec.label in seen:
            raise CompileExecError(f"批次 label 重复: {spec.label}")
        seen.add(spec.label)
        if not spec.path.is_file():
            raise CompileExecError(f"批次工件不存在: {spec.path}")
    if not specs:
        raise CompileExecError("没有可分析的批次（--batch / --only-round 过滤后为空）")
    return specs


def _run_one_batch(
    spec: BatchSpec,
    *,
    arms_requested: list[str],
    roots: list[Path],
    collect_timeout_s: float,
    jobs: int,
    limit: int,
    progress: bool,
) -> dict[str, Any]:
    """跑一个批次工件的全部（选定）臂。"""
    artifact = load_artifact(spec.path)
    available = list_artifact_arms(artifact)
    selected = arms_requested or available
    unknown = sorted(set(selected) - set(available))
    if unknown:
        raise CompileExecError(f"批次 {spec.label} 内不存在臂 {unknown}（可用: {available}）")
    arm_results: list[dict[str, Any]] = []
    for arm in selected:
        rows = select_rows(artifact, arm)
        work_rows = sorted(rows, key=lambda r: str(r.get("task_id") or ""))
        if limit > 0:
            work_rows = work_rows[:limit]
        results: list[dict[str, Any]] = []
        started = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
            futures = [
                pool.submit(
                    analyze_row,
                    row,
                    batch_label=spec.label,
                    round_name=spec.round,
                    arm=arm,
                    roots=roots,
                    collect_timeout_s=collect_timeout_s,
                )
                for row in work_rows
            ]
            results = [future.result() for future in concurrent.futures.as_completed(futures)]
        results.sort(key=lambda r: str(r.get("task_id") or ""))
        aggregate = aggregate_rows(results)
        arm_results.append(
            {
                "arm": arm,
                "n_rows_artifact": len(rows),
                "n_rows_analyzed": len(results),
                "aggregate": aggregate,
                "rows": results,
                "timing": {"wall_s": round(time.time() - started, 3)},
            }
        )
        if progress:
            print(
                f"[compile-exec] {spec.label}/{arm} n={aggregate['n_rows']} "
                f"compile={_fmt_rate_pair(aggregate['n_compile_ok'], aggregate['n_compile_denominator'])} "
                f"exec={_fmt_rate_pair(aggregate['n_exec_ok'], aggregate['n_exec_attempted'])} "
                f"wall={arm_results[-1]['timing']['wall_s']}s",
                flush=True,
            )
    return {
        "label": spec.label,
        "round": spec.round,
        "artifact": _display_path(spec.path),
        "sha256": sha256_file(spec.path),
        "arms": arm_results,
        "timing": {"wall_s": round(sum(a["timing"]["wall_s"] for a in arm_results), 3)},
    }


def _build_pooled(batch_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """合并表：按 (round, arm) 汇总行级记录后重算比率（不做比率平均）。"""
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for batch in batch_results:
        for arm in batch["arms"]:
            key = (str(batch["round"]), str(arm["arm"]))
            buckets.setdefault(key, []).extend(arm["rows"])
    pooled: list[dict[str, Any]] = []
    for (round_name, arm), rows in sorted(buckets.items()):
        pooled.append(
            {
                "round": round_name,
                "arm": arm,
                "n_batches": sum(
                    1
                    for batch in batch_results
                    if batch["round"] == round_name and any(a["arm"] == arm for a in batch["arms"])
                ),
                "aggregate": aggregate_rows(rows),
            }
        )
    return pooled


def _command_line() -> list[str]:
    """当前进程的可复算命令行（统一写成 ``python -m experiments.compile_exec_metrics ...``）。"""
    return ["python", "-m", "experiments.compile_exec_metrics", *sys.argv[1:]]


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
    base_body = mm.strip_volatile(repeats[0][0])
    digests = [meta["body_digest"] for _, meta in repeats]
    diffs: list[str] = []
    for body, _meta in repeats[1:]:
        diffs.extend(mm._diff_paths(base_body, mm.strip_volatile(body)))
    return {
        "repeat": len(repeats),
        "body_digests": digests,
        "deterministic": len(set(digests)) == 1,
        "difference_paths": diffs[:20],
        "note": "收集重放无随机源；digest 差异会如实列出，不做静默平均",
    }


def _run_replay(
    specs: list[BatchSpec],
    *,
    arms_requested: list[str],
    roots: list[Path],
    config: dict[str, Any],
    jobs: int,
    limit: int,
    progress: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """执行完整重放，返回 (报告 body, 易变元信息)。"""
    started = time.time()
    batch_results = [
        _run_one_batch(
            spec,
            arms_requested=arms_requested,
            roots=roots,
            collect_timeout_s=float(config["collect_timeout_s"]),
            jobs=jobs,
            limit=limit,
            progress=progress,
        )
        for spec in specs
    ]
    inputs = [
        {
            "path": batch["artifact"],
            "sha256": batch["sha256"],
            "batch": batch["label"],
            "round": batch["round"],
            "arms": [arm["arm"] for arm in batch["arms"]],
        }
        for batch in batch_results
    ]
    body = build_report(
        inputs=inputs,
        batch_results=batch_results,
        pooled=_build_pooled(batch_results),
        config=config,
        command=_command_line(),
    )
    meta = {
        "generated_at": _now_iso(),
        "tool_wall_s": round(time.time() - started, 3),
        "body_digest": body_digest(body),
    }
    return body, meta


def main(argv: list[str] | None = None) -> int:
    """CLI 主入口：解析 → 重放（可重复）→ 落盘 JSON/Markdown。"""
    args = _build_arg_parser().parse_args(argv)
    out_dir = Path(args.out)
    try:
        specs = _resolve_batches(args)
    except CompileExecError as e:
        print(f"[compile-exec] 错误: {e}", file=sys.stderr)
        return 2
    out_dir.mkdir(parents=True, exist_ok=True)
    roots = resolve_quixbugs_roots(args.quixbugs_root)
    config = {
        "collect_timeout_s": float(args.collect_timeout),
        "jobs": int(args.jobs),
        "limit": int(args.limit),
        "test_filename": TEST_FILENAME,
        "protocol": "pytest --collect-only -q（仅收集，不执行测试）",
        "pythonpath_layout": "quixbugs: flat+python_programs package + support(node/load_testdata/json_testcases)；flat: 单文件",
        "quixbugs_roots": [str(p) for p in roots],
        "pytest_version": _pytest_version(),
        "batches": [{"label": spec.label, "round": spec.round, "path": _display_path(spec.path)} for spec in specs],
    }
    repeats: list[tuple[dict[str, Any], dict[str, Any]]] = []
    n_repeat = max(1, int(args.repeat))
    for index in range(n_repeat):
        if n_repeat > 1:
            print(f"[compile-exec] 确定性重放 {index + 1}/{n_repeat}", file=sys.stderr)
        body, meta = _run_replay(
            specs,
            arms_requested=list(args.arm or []),
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
    from src.utils.atomic_io import atomic_write_json, atomic_write_text

    json_path = out_dir / "COMPILE_EXEC_REPORT.json"
    atomic_write_json(str(json_path), payload)
    print(f"[compile-exec] JSON 报告: {json_path}", flush=True)
    if not args.skip_markdown:
        md_path = out_dir / "COMPILE_EXEC_REPORT.md"
        atomic_write_text(str(md_path), render_markdown(body, run_meta))
        print(f"[compile-exec] Markdown 报告: {md_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
