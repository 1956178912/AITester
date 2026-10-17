#!/usr/bin/env python3
"""A-05 确定性规约 oracle 质量度量（零 LLM 重放，M 轮 T7-A）。

动机（独立评审 §10 A-05 / G6 / D-4，2026-10-17）
================================================
逻辑驱动通道会把 ``src/specs/spec_ir_v2.compile_spec_oracle`` 编译出的
**确定性规约 oracle** 追加到 LLM 生成测试尾部并列执行
（生产注入口 ``src/graph/nodes.py::_append_spec_oracle_to_test_with_verdict``，
注入测试名固定 ``test_specir_v2_oracle`` / ``test_specir_v2_smt_witness``）。
项目此前只报"注入率"（``spec_oracle_injected`` / ``spec_oracle_verdict``），
**oracle 本身的正确率从未度量**——若 oracle 在正确实现上也失败（假阳），
它会把"逻辑驱动"的确定性通道变成检出损伤源；若 oracle 在缺陷版上通过，
它对该缺陷无信号。本工具把该缺口落地为可复算的零 LLM 重放。

输入（只读）与反事实口径
------------------------
1. ``experiments/results/emse_df_spec_20261016/`` 两臂批次 JSON
   （``plain_llm_df_spec`` 处理 / ``plain_llm_df`` 对照；``generated_test``
   已归档，LLM-only）。SHA256SUMS 锁定的工件只读消费，不修改。
2. ``experiments/results/emse_spec_anchor_20261016/SPEC_ANCHOR_TABLE.json``
   （Planner ``logic_analysis`` 锚材料，按 ``sha256(target_code.strip())``
   内容寻址）。**加载时强制用同目录 SHA256SUMS 校验**（不一致 fail-closed）。
3. QuixBugs 缺陷版源码（``~/.cache/aitester/quixbugs/python_programs`` 优先，
   ``data/quixbugs`` / ``AITESTER_QUIXBUGS_DATA`` 回退）。

归档批次跑在 ``--baselines plain_llm_df*``（Planner 关闭）上，故
``test_plan`` 缺席 → 生产注入口在该批次里一律 ``not_attempted``（归档
``spec_oracle_verdict=not_attempted`` 50/50）。本工具做**反事实重放**：

    state 从锚表重建（``test_plan={function_name, logic_analysis}``、
    ``target_function``=归档 suggested_function、``module_name``=task_id
    末段、``target_code``=缺陷版源码），**原样调用生产注入函数**把 oracle
    追加到归档 ``generated_test``；state 不注入现场 ``spec_ir`` /
    ``boundary_triplets``——即"只拿到锚表材料时，生产注入口会产出什么质量的
    oracle"这一受控问题。该口径由任务书显式指定，见 §限制。

逐测试分类（在 misguided_metrics 物化/子进程口径上复用）
--------------------------------------------------------
对每个任务把 buggy / fixed 两版源码与（LLM-only / oracle-augmented）测试
分别物化到临时目录，``pytest --junitxml`` 取逐测试结果，仅对**oracle 测试
节点**做四分类（互斥，覆盖全部可分类 oracle 测试）：

    oracle_correct   = oracle 测试 buggy 失败 ∧ fixed 通过（真检出）
    oracle_misguided = oracle 测试 buggy 通过 ∧ fixed 失败（把缺陷行为固化为期望）
    oracle_silent    = 两侧都通过（对该缺陷零信号）
    oracle_fp        = 其余可分类情形（fixed 失败 = 对正确实现的假阳；
                       含 buggy 失败 ∧ fixed 失败的恒红型 oracle）

超时 / 收集失败 / import 失败 / skipped / setup error / 单侧缺失一律
**单列不可分类原因**，绝不并入四分类分母。

同时报告（任务级，M1 detection 口径）
------------------------------------
- **注入统计**：锚命中率 / 尝试注入率 / 注入成功率（编译产物非空率）/
  每任务 oracle 测试数；
- **注入任务检出贡献**：``LLM-only 重放 detection`` vs
  ``oracle-augmented 重放 detection``（同任务配对）的 0→1（added）/
  1→0（lost）/ 保留 / 均无 转移表；lost 逐条归因到 oracle 假阳；
- **交叉校验（0 mismatch 要求）**：
  1. LLM-only 重放 detection vs 归档 ``detection_rate``（mismatch = 两侧
     均可判但结论不同）；差异逐条给归因（环境/超时口径/跨批次随机性）；
  2. 归档 ``spec_oracle_verdict`` / ``spec_oracle_injected`` 的**语义复现**：
     用"归档状态"（无 test_plan）重建 state 调生产注入口，重放 verdict 必须
     与归档逐行一致；不一致即 mismatch 并列归因。归档字段自洽性
     （injected 三态 ↔ verdict 取值域）也一并校验。
  ``cross_check.all_ok`` 是报告字段；``--fail-on-mismatch`` 时 mismatch>0
  以退出码 3 结束（fail-closed，供 gate 用）。

输出
----
``--out`` 目录下写 ``ORACLE_QUALITY_REPORT.json`` / ``.md`` / ``README.md``：
输入 sha256、复算命令、分母披露、逐任务明细、确定性声明、限制。

用法示例::

    .venv/bin/python -m experiments.oracle_quality_replay \\
        --out experiments/results/emse_oracle_quality_20261017 --jobs 8 --repeat 2

纪律与限制（报告同步披露）
--------------------------
- **描述性度量**：oracle 质量反映"确定性规约通道"本身，**不是** LLM 生成
  能力指标；与 Tratto/TOGLL 等外部工作数字不同口径，不横向引用为对比。
  独立评审 A-05 只把它定位为"逻辑驱动通道有效性可量化"。
- 反事实注入口径（锚表材料直接解析、无现场 ``spec_ir``/``boundary_triplets``）
  可能低估完整 logic 链路的注入质量；不声称等同生产全链路。
- 生成测试与 oracle 同文件、同 session 执行（生产口径），全局状态污染与
  收集顺序照旧；只按版本隔离临时目录。
- 官方金测试 ``test_cases`` 不参与本分类；仅用于任务级 detection 交叉校验口径。
- 9 个 QuixBugs ``*_test`` 驱动任务（相对 import、无金测试）与辅助模块
  ``node`` 在平铺执行口径下结构性不可 replay → 结构跳过单列。
"""

from __future__ import annotations

import argparse
import ast
import concurrent.futures
import json
import os
import re
import shutil
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
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
    _TIMEOUT_FAILURE_RE,
    _count_ast_test_defs,
    _detection_agreement,
    _detection_disagreement_reason,
    _display_path,
    _junit_node_key,
    _now_iso,
    _pytest_version,
    _side_failure_reason,
    _summary,
    _task_program,
    _truncate,
    body_digest,
    collect_siblings,
    dataset_fixed_source,
    list_artifact_arms,
    load_artifact,
    materialize_version,
    pytest_timeout_available,
    replay_detection,
    resolve_buggy_source,
    resolve_quixbugs_roots,
    run_side,
    select_rows,
    sha256_file,
    sha256_text,
    strip_volatile,
    validate_buggy_source,
)
from src.graph.state import AITesterState  # noqa: E402

SCHEMA_VERSION = "oracle_quality_metric/1"
TOOL_NAME = "experiments.oracle_quality_replay"
TOOL_VERSION = "1.0.0"

# 生产注入测试名（与 src/graph/nodes.py::_SPEC_ORACLE_TEST_NAMES 同值；
# tests 用 production_oracle_test_names() 锁定两者相等——生产改名即红）。
ORACLE_TEST_MARKERS: tuple[str, ...] = ("test_specir_v2_oracle", "test_specir_v2_smt_witness")

# 四分类（互斥覆盖全部可分类 oracle 测试）
ORACLE_CLASSES: tuple[str, ...] = ("correct", "fp", "silent", "misguided")
ORACLE_CLASS_DEFINITIONS: dict[str, str] = {
    "correct": "oracle 测试 buggy 失败 ∧ fixed 通过（真检出：区分缺陷版与修复版）",
    "fp": "oracle 在正确实现（fixed）上失败 = 假阳；含 buggy 失败 ∧ fixed 失败的恒红型 oracle",
    "silent": "两侧都通过（对该缺陷零信号，oracle 断言未触达缺陷行为）",
    "misguided": "oracle 测试 buggy 通过 ∧ fixed 失败（把缺陷行为断言成期望行为）",
}
# misguided_metrics 四分类 → 本工具四分类（复用其分类器后再映射）
MM_TO_ORACLE_CLASS: dict[str, str] = {
    "effective": "correct",
    "both_fail": "fp",
    "both_pass": "silent",
    "misguided": "misguided",
}

# 任务级结构跳过原因（不静默跳过；与 misguided 同族 + 本工具特有）
STRUCTURAL_REASONS: tuple[str, ...] = (
    "artifact_row_malformed",
    "empty_generated_test",
    "invalid_program_name",
    "generated_test_syntax_error",
    "missing_buggy_source",
    "buggy_source_unparseable",
    "buggy_source_validation_failed",
    "anchor_miss",
    "anchor_malformed",
    "missing_fixed_material",
    "fixed_material_unparseable",
    "already_contains_oracle",
    "not_injected",
    "llm_only_not_replayable",
    "augmented_side_unavailable",
    "no_oracle_tests_collected",
    "no_classifiable_oracle_tests",
    "file_timeout",
    "import_error",
    "syntax_error",
    "collect_error",
    "no_tests_collected",
    "materialize_failed",
    "unknown",
)

# 归档 spec_oracle_verdict 取值域（生产三态 + 执行后升级两态）
ARCHIVED_VERDICTS: tuple[str, ...] = (
    "not_attempted",
    "compiled_empty",
    "injected",
    "injected_and_passed",
    "injected_and_failed",
)
_ARCHIVED_INJECTED_VERDICTS = frozenset({"injected", "injected_and_passed", "injected_and_failed"})

# 默认输入（df_spec 批：处理臂 / 对照臂；两臂同批同日、可复算）
_DEFAULT_DF_SPEC = _REPO_ROOT / "experiments/results/emse_df_spec_20261016/benchmark_quixbugs_20261016_232138.json"
_DEFAULT_DF = _REPO_ROOT / "experiments/results/emse_df_spec_20261016/benchmark_quixbugs_20261017_003023.json"
DEFAULT_ARTIFACTS: tuple[Path, ...] = (_DEFAULT_DF_SPEC, _DEFAULT_DF)
DEFAULT_ANCHOR_TABLE = _REPO_ROOT / "experiments/results/emse_spec_anchor_20261016/SPEC_ANCHOR_TABLE.json"
DEFAULT_OUT = _REPO_ROOT / "experiments/results/emse_oracle_quality_20261017"

# N-3（2026-10-17，A-05 后续修复）：独立判读模式。
# 语义：把生产独立判读链（nodes 注入 + _m1_metrics 的 LLM-suite/oracle-suite
# 分开执行）**原样**套到归档 df_spec 两臂上，验证：
#   ① 接线修复（仅 spec_anchor 材料的 state 也能注入）；
#   ② LLM-suite detection 与 M-2 已测值一致（40 口径 df_spec 50.00% / df 77.50%）；
#   ③ oracle 独立四分类与 M-2 逐任务分类的一致性。
M2_REPORT_DEFAULT = _REPO_ROOT / "experiments/results/emse_oracle_quality_20261017/ORACLE_QUALITY_REPORT.json"
INDEPENDENT_OUT_DEFAULT = _REPO_ROOT / "experiments/results/emse_oracle_independent_judging_20261017"
INDEPENDENT_SCHEMA_VERSION = "oracle_independent_judging/1"
# 与 _m1_metrics 同一 M1 判分 caliber：M-2 重放用 --per-test-timeout 1；
# 独立判读复用生产 _m1_metrics 路径时通过 M1_PER_TEST_TIMEOUT 显式对齐，
# 否则挂死任务族（bitcount/find_first_in_sorted/sqrt/wrap）会退化为
# 整套餐超时 None，无法与 M-2 的 40 口径分母对账。
INDEPENDENT_M1_PER_TEST_TIMEOUT_S = 1

_PY_IDENT_RE = mm._PY_IDENT_RE


# ─── 异常 ────────────────────────────────────────────────────────────────
class OracleQualityError(Exception):
    """本工具的可预期错误（CLI 捕获后以非零码退出，不打印 traceback）。"""


class AnchorTableError(OracleQualityError):
    """锚表缺失 / sha256 校验失败 / 结构不合法（fail-closed）。"""


# ─── 锚表加载与 sha256 校验 ────────────────────────────────────────────────
def _display_path_or_str(path: Path) -> str:
    """展示用路径（仓库内相对路径；否则绝对路径）。"""
    return _display_path(path)


def find_sha256sums_entry(sums_path: Path, basename: str) -> str:
    """从 ``SHA256SUMS`` 取指定文件名的 sha256（fail-closed）。

    Args:
        sums_path: SHA256SUMS 文件路径。
        basename: 被校验文件名（如 ``SPEC_ANCHOR_TABLE.json``）。

    Returns:
        64 位十六进制摘要。

    Raises:
        AnchorTableError: 文件缺失 / 无匹配行 / 匹配行格式不合法。
    """
    if not sums_path.is_file():
        raise AnchorTableError(f"SHA256SUMS 不存在（无法校验锚表）: {sums_path}")
    matches: list[str] = []
    try:
        lines = sums_path.read_text(encoding="utf-8").splitlines()
    except OSError as e:
        raise AnchorTableError(f"SHA256SUMS 不可读: {sums_path}: {e}") from e
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        digest, name = parts[0].strip(), parts[1].strip().lstrip("*")
        if name == basename or name.endswith("/" + basename):
            matches.append(digest.lower())
    if not matches:
        raise AnchorTableError(f"SHA256SUMS 中无 {basename} 条目: {sums_path}")
    if len(set(matches)) > 1:
        raise AnchorTableError(f"SHA256SUMS 中 {basename} 有多条不同摘要: {sums_path}")
    digest = matches[0]
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise AnchorTableError(f"SHA256SUMS 中 {basename} 摘要格式不合法: {digest!r}")
    return digest


def load_anchor_table(
    path: Path,
    *,
    sums_path: Path | None = None,
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    """加载规格锚表并强制校验 sha256（fail-closed）。

    校验顺序：显式 ``expected_sha256`` 优先；否则从同目录 ``SHA256SUMS``
    查条目。二者都没有 → 报错（**不允许无校验加载**——锚表是反事实
    state 重建的唯一材料源）。

    Args:
        path: SPEC_ANCHOR_TABLE.json 路径。
        sums_path: SHA256SUMS 路径（缺省 = 同目录 SHA256SUMS）。
        expected_sha256: 显式期望摘要（CLI 覆盖 / 预注册锁定）。

    Returns:
        {"path", "sha256", "expected_sha256", "expected_sha256_source",
         "sums_path", "meta", "anchors"}。

    Raises:
        AnchorTableError: 缺失 / JSON 非法 / 无 ``anchors`` dict / sha256 不符。
    """
    if not path.is_file():
        raise AnchorTableError(f"锚表不存在: {path}")
    actual = sha256_file(path)
    source = "cli"
    expected = (expected_sha256 or "").strip().lower() or None
    sums = sums_path or (path.parent / "SHA256SUMS")
    if expected is None:
        expected = find_sha256sums_entry(sums, path.name)
        source = _display_path_or_str(sums)
    if actual != expected:
        raise AnchorTableError(f"锚表 sha256 校验失败: {path}（期望 {expected}，实际 {actual}）")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise AnchorTableError(f"锚表无法解析为 JSON: {path}: {e}") from e
    if not isinstance(data, dict) or not isinstance(data.get("anchors"), dict):
        raise AnchorTableError(f"锚表结构不合法（缺 anchors dict）: {path}")
    anchors = {str(k): v for k, v in data["anchors"].items() if isinstance(v, dict)}
    if not anchors:
        raise AnchorTableError(f"锚表 anchors 为空: {path}")
    return {
        "path": _display_path_or_str(path),
        "sha256": actual,
        "expected_sha256": expected,
        "expected_sha256_source": source,
        "sums_path": _display_path_or_str(sums) if sums.is_file() else None,
        "meta": data.get("meta") if isinstance(data.get("meta"), dict) else {},
        "anchors": anchors,
    }


def lookup_anchor(anchors: dict[str, dict[str, Any]], target_code: str) -> tuple[str, dict[str, Any] | None]:
    """按 ``sha256(target_code.strip())`` 查锚材料（与生产臂查找口径逐字一致）。

    Returns:
        (内容摘要, 锚条目或 None)。
    """
    digest = sha256_text(str(target_code).strip())
    entry = anchors.get(digest)
    return digest, entry if isinstance(entry, dict) else None


# ─── state 重建（生产注入口的输入契约） ───────────────────────────────────
def module_name_for_task(task_id: str) -> str:
    """task_id → 生产 module_name 口径（task_id 末段，``-``→``_``，截 50 字符）。"""
    raw = str(task_id).split("__")[-1]
    return raw.replace("-", "_")[:50]


def reconstruct_state(
    task_id: str,
    task_metadata: dict[str, Any],
    anchor_entry: dict[str, Any] | None,
    target_code: str,
    *,
    archived_state: bool = False,
) -> AITesterState:
    """从锚表材料重建生产注入函数的 state（反事实 / 归档语义两态）。

    任务书口径（反事实，``archived_state=False``）：只带
    ``test_plan={function_name, logic_analysis}``、``target_function``、
    ``module_name``、``target_code``；不写 ``spec_ir``（生产注入函数在
    ``spec_ir`` 缺席时现场解析 ``test_plan.logic_analysis``——与 R7 关闭
    时的降级路径同口径）。

    ``archived_state=True``：模拟归档批次真实 state（``test_plan`` 缺席，
    Planner 关闭）——用于交叉校验归档 ``spec_oracle_verdict`` 的可复现性。

    Args:
        task_id: 任务 id（末段即 module_name）。
        task_metadata: 归档行 task_metadata（取 suggested_function）。
        anchor_entry: 锚表条目（``function_name`` + ``logic_analysis``）。
        target_code: 缺陷版源码（生产 state.target_code）。
        archived_state: 是否按归档批次 state 重建（无 test_plan）。

    Returns:
        AITesterState（生产注入函数只读其中四个键）。
    """
    state: AITesterState = {
        "target_code": str(target_code),
        "module_name": module_name_for_task(task_id),
    }
    suggested = task_metadata.get("suggested_function")
    if isinstance(suggested, str) and suggested.strip():
        state["target_function"] = suggested.strip()
    if not archived_state and isinstance(anchor_entry, dict):
        state["test_plan"] = {
            "function_name": anchor_entry.get("function_name"),
            "logic_analysis": anchor_entry.get("logic_analysis"),
        }
    return state


def reconstruct_state_anchor_only(
    task_id: str,
    task_metadata: dict[str, Any],
    anchor_entry: dict[str, Any] | None,
    target_code: str,
) -> AITesterState:
    """N-3：只带 ``spec_anchor`` 的 state（复刻生产 df_spec/doc/union/augment 类臂）。

    生产这些臂 Planner 关闭（``baseline`` 不跑 planner）→ state 里**没有**
    ``test_plan``，只有 ``run_benchmark`` 预载的 ``state["spec_anchor"]``。
    N-3 修复前注入口只认 ``spec_ir`` / ``test_plan`` → 这些臂永远
    ``not_attempted``（接线缺口）；修复后 spec_anchor.logic_analysis 成为
    第三材料源。本函数用于独立判读重放，同时充当接线修复的生产态验证。

    Args:
        task_id: 任务 id（末段 = module_name）。
        task_metadata: 归档行 task_metadata（取 suggested_function）。
        anchor_entry: 锚表条目（logic_analysis / human_spec / function_name）。
        target_code: 缺陷版源码。

    Returns:
        AITesterState（不含 test_plan / spec_ir；只带 spec_anchor）。
    """
    state: AITesterState = {
        "target_code": str(target_code),
        "module_name": module_name_for_task(task_id),
    }
    suggested = task_metadata.get("suggested_function")
    if isinstance(suggested, str) and suggested.strip():
        state["target_function"] = suggested.strip()
    if isinstance(anchor_entry, dict):
        state["spec_anchor"] = dict(anchor_entry)
    return state


def production_oracle_test_names() -> tuple[str, ...]:
    """生产侧 oracle 测试名常量（惰性 import：避免本工具 import 期拉起重依赖）。"""
    from src.graph.nodes import _SPEC_ORACLE_TEST_NAMES

    return tuple(_SPEC_ORACLE_TEST_NAMES)


def production_inject_oracle(generated_test: str, state: AITesterState) -> tuple[str, bool, str]:
    """**原样调用**生产注入函数（A-05 fidelity：重放与生产同一函数）。

    Args:
        generated_test: LLM 生成测试全文。
        state: ``reconstruct_state`` 产物。

    Returns:
        (追加后的测试代码, 是否注入, verdict)。
    """
    from src.graph.nodes import _append_spec_oracle_to_test_with_verdict

    return _append_spec_oracle_to_test_with_verdict(generated_test, state)


def is_oracle_node(node: str, markers: tuple[str, ...] = ORACLE_TEST_MARKERS) -> bool:
    """node id 是否为 oracle 注入测试（生产用子串匹配，本工具同口径）。"""
    return any(marker in str(node) for marker in markers)


# ─── 归档 verdict 交叉校验 ────────────────────────────────────────────────
def normalize_archived_verdict(value: Any) -> str:
    """归档 ``spec_oracle_verdict`` 归一（None/空 → not_attempted，历史兜底口径）。"""
    if value is None:
        return "not_attempted"
    text = str(value).strip()
    if not text or text.lower() in {"none", "null"}:
        return "not_attempted"
    return text


def archive_field_consistency(verdict: Any, injected: Any) -> tuple[bool, str]:
    """归档行 ``spec_oracle_verdict`` 与 ``spec_oracle_injected`` 自洽性检查。

    Returns:
        (是否自洽, 说明)。不自洽 = 工件字段内部矛盾（非本工具重放差异）。
    """
    norm = normalize_archived_verdict(verdict)
    if norm in _ARCHIVED_INJECTED_VERDICTS:
        if injected is True:
            return True, ""
        return False, f"归档 verdict={norm} 但 spec_oracle_injected={injected!r}（应为 True）"
    if norm in {"not_attempted", "compiled_empty"}:
        if injected in (None, False):
            return True, ""
        return False, f"归档 verdict={norm} 但 spec_oracle_injected={injected!r}（应为 None/False）"
    return False, f"归档 verdict 不在生产取值域: {norm!r}"


# ─── 逐测试 oracle 四分类 ──────────────────────────────────────────────────
def classify_oracle_outcomes(
    nodes: list[str],
    buggy_outcomes: dict[str, str],
    fixed_outcomes: dict[str, str],
    *,
    buggy_missing_reason: str = "unknown",
    fixed_missing_reason: str = "unknown",
) -> tuple[list[dict[str, Any]], dict[str, int], dict[str, int]]:
    """对 oracle 测试节点做四分类（复用 misguided_metrics 分类器 + 类别映射）。

    复用保证：可分类判定（两侧均有 pass/fail）、不可分类原因优先级
    （timeout/skipped/test_error/missing_side/unknown）与 T2 工具逐字一致；
    仅把四类映射为本工具口径（effective→correct、both_fail→fp）。

    Returns:
        (rows, counts, unclassifiable_counts)；rows 内 ``cls`` 为 oracle 类别
        （None 时 ``reason`` 给不可分类原因）。
    """
    mm_rows, mm_counts, unclassifiable = mm.classify_outcomes(
        nodes,
        buggy_outcomes,
        fixed_outcomes,
        buggy_missing_reason=buggy_missing_reason,
        fixed_missing_reason=fixed_missing_reason,
    )
    counts: dict[str, int] = dict.fromkeys(ORACLE_CLASSES, 0)
    rows: list[dict[str, Any]] = []
    for row in mm_rows:
        cls = MM_TO_ORACLE_CLASS.get(str(row.get("cls")))
        if cls is not None:
            counts[cls] += 1
        rows.append(
            {
                "node": row.get("node"),
                "buggy": row.get("buggy"),
                "fixed": row.get("fixed"),
                "cls": cls,
                "reason": row.get("reason"),
                "mm_cls": row.get("cls"),
                # O-1：fp 细分与 skip 归因（由 analyze_task 在解析 junit 后填充；
                # 分类本身仍复用 T2 分类器，旧四分类键不变）
                "fp_kind": None,
                "buggy_skip_reason": None,
                "fixed_skip_reason": None,
            }
        )
    # 防御：映射不丢计数（mm_counts 总和 = 映射后 counts 总和）
    if sum(mm_counts.values()) != sum(counts.values()):  # pragma: no cover - 结构不变式
        raise OracleQualityError("oracle 类别映射丢计数（MM_TO_ORACLE_CLASS 与 CLASSES 不同步）")
    return rows, counts, unclassifiable


# ─── 失败类型归因（论文级诊断：假阳是断言失败还是 oracle 自身崩溃） ──────
_EXCEPTION_RE = re.compile(r"\b([A-Z][A-Za-z0-9_]*(?:Error|Exception|Warning))\b")
# O-1（2026-10-18）：仪器不可用 skip 原因归一（崩溃 harness / no-valid-input）。
# 报告只保留稳定前缀（"oracle-unavailable: <ExcType|no-valid-input>"），异常
# 消息正文不进入聚合键（保证重复重放 digest 稳定）。
_ORACLE_SKIP_SENTINEL = "oracle-unavailable:"
FP_FLAG_ASSERTION = "fp_assertion_fail"
FP_INSTRUMENT_ERROR = "instrument_error"
FP_UNATTRIBUTED = "fp_unattributed"


def _normalize_oracle_skip_reason(message: str) -> str:
    """把 skip 消息归一为稳定原因键（``oracle-unavailable: <reason>``）。"""
    text = str(message or "").replace("\n", " ").strip()
    if _ORACLE_SKIP_SENTINEL not in text:
        return "skipped_other"
    tail = text.split(_ORACLE_SKIP_SENTINEL, 1)[1].strip().lstrip(":").strip()
    # 形如 "TypeError: ..." / "no-valid-input"：只保留第一段（异常类型或原因码）
    first = tail.split(":", 1)[0].strip()
    return f"{_ORACLE_SKIP_SENTINEL} {first or 'unknown'}"


def classify_fp_kind(fixed_note: dict[str, Any] | None) -> str:
    """O-1：把 oracle fp 拆成"断言失败型"与"仪器失效型"（旧四分类兼容）。

    - fixed 侧 junit 记录为 ``failure`` 且失败类型是 assertion → ``fp_assertion_fail``
      （oracle 断言在正确实现上失败 = 语义判断错误，保留为 fp）；
    - fixed 侧 junit 记录为 ``error`` / 失败类型是 exception/timeout → ``instrument_error``
      （崩溃等仪器失效；加固后新产物应转为 skipped/unavailable）；
    - 无诊断记录（junit 缺失/未解析）→ ``fp_unattributed``（保守，不臆测归因）。
    """
    note = fixed_note or {}
    if not note:
        return FP_UNATTRIBUTED
    if note.get("tag") == "error":
        return FP_INSTRUMENT_ERROR
    kind = str(note.get("kind") or "")
    if kind == "assertion":
        return FP_FLAG_ASSERTION
    if kind in {"exception", "timeout", "other"}:
        return FP_INSTRUMENT_ERROR
    return FP_UNATTRIBUTED


def failure_kind(message: str) -> str:
    """pytest 失败消息 → 粗粒度失败类型（诊断列，不参与四分类）。

    Returns:
        ``timeout`` / ``assertion`` / ``exception`` / ``other``。
    """
    text = str(message or "")
    if _TIMEOUT_FAILURE_RE.search(text):
        return "timeout"
    stripped = text.strip()
    if "AssertionError" in text or stripped.startswith("assert ") or "\nassert " in text:
        return "assertion"
    if _EXCEPTION_RE.search(text):
        return "exception"
    return "other"


def exception_name(message: str) -> str | None:
    """从失败消息提取异常类型名（TypeError / NameError…；无 → None）。"""
    match = _EXCEPTION_RE.search(str(message or ""))
    return match.group(1) if match else None


def parse_junit_failure_notes(path: Path) -> dict[str, dict[str, Any]]:
    """解析 junitxml 的失败详情（node → {tag, kind, exception, message}）。

    仅用于**诊断列**（假阳归因），不参与分类判定；解析失败返回空 dict
    （保守——分类本身由 misguided_metrics.parse_junit_xml 主口径承担）。
    """
    notes: dict[str, dict[str, Any]] = {}
    if not path.is_file():
        return notes
    try:
        tree = ET.parse(str(path))
    except (ET.ParseError, OSError):
        return notes
    for case in tree.getroot().iter("testcase"):
        node = _junit_node_key(case.get("classname") or "", case.get("name") or "")
        if node is None:
            continue
        for child in case:
            if child.tag not in {"failure", "error", "skipped"}:
                continue
            message = f"{child.get('message') or ''}\n{child.text or ''}"
            if child.tag == "skipped":
                # O-1 仪器加固：崩溃安全 harness 的 pytest.skip 详情（诊断列）
                notes[node] = {
                    "tag": "skipped",
                    "kind": "skipped",
                    "exception": None,
                    "message": _truncate(message, 300),
                    "skip_reason": _normalize_oracle_skip_reason(message),
                }
            else:
                notes[node] = {
                    "tag": child.tag,
                    "kind": failure_kind(message),
                    "exception": exception_name(message),
                    "message": _truncate(message, 300),
                    "skip_reason": None,
                }
            break
    return notes


# ─── 任务级检出转移 ────────────────────────────────────────────────────────
def injection_transition(llm_only_detection: float | None, augmented_detection: float | None) -> str:
    """LLM-only → oracle-augmented 的任务级检出转移类别。"""
    if llm_only_detection is None or augmented_detection is None:
        return "undecidable"
    llm = round(float(llm_only_detection))
    aug = round(float(augmented_detection))
    if llm == 0 and aug == 1:
        return "added"
    if llm == 1 and aug == 0:
        return "lost"
    if llm == 1 and aug == 1:
        return "preserved"
    return "none"


def _as_float_or_none(value: Any) -> float | None:
    """工件 detection_rate 安全归一（"None"/缺失/NaN → None）。"""
    return mm._as_float_or_none(value)


def _as_bool_or_none(value: Any) -> bool | None:
    """工件 passed 等字段安全归一。"""
    return mm._as_bool_or_none(value)


# ─── 单任务分析 ────────────────────────────────────────────────────────────
def _skip(record: dict[str, Any], reason: str, detail: str) -> dict[str, Any]:
    """把任务记录标为结构跳过（不静默：原因码 + 详情）。"""
    record["status"] = "structural_skip"
    record["skip_reason"] = reason
    record["skip_detail"] = _truncate(detail, 600)
    return record


def _oracle_failure_stats(
    rows: list[dict[str, Any]],
    buggy_notes: dict[str, dict[str, Any]],
    fixed_notes: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """oracle 测试失败类型分布（buggy 侧 / fixed 侧，按诊断目的分开）。"""
    buggy_kinds: Counter[str] = Counter()
    fixed_kinds: Counter[str] = Counter()
    fixed_exceptions: Counter[str] = Counter()
    skip_reasons: Counter[str] = Counter()
    for row in rows:
        node = str(row.get("node"))
        if row.get("buggy") == "skip" and node in buggy_notes:
            skip_reasons[str(buggy_notes[node].get("skip_reason") or "skipped_other")] += 1
        if row.get("fixed") == "skip" and node in fixed_notes:
            skip_reasons[str(fixed_notes[node].get("skip_reason") or "skipped_other")] += 1
        if row.get("buggy") == "fail" and node in buggy_notes:
            buggy_kinds[str(buggy_notes[node].get("kind") or "other")] += 1
        if row.get("fixed") == "fail" and node in fixed_notes:
            note = fixed_notes[node]
            fixed_kinds[str(note.get("kind") or "other")] += 1
            if note.get("exception"):
                fixed_exceptions[str(note["exception"])] += 1
    return {
        "buggy_side_failure_kinds": dict(sorted(buggy_kinds.items())),
        "fixed_side_failure_kinds": dict(sorted(fixed_kinds.items())),
        "fixed_side_exception_types": dict(sorted(fixed_exceptions.items())),
        # O-1：仪器不可用 skip 原因分布（oracle-unavailable: <ExcType|no-valid-input>）
        "skip_reason_counts": dict(sorted(skip_reasons.items())),
    }


def analyze_task(
    row: dict[str, Any],
    *,
    anchors: dict[str, dict[str, Any]],
    roots: list[Path],
    pytest_timeout_s: float,
    collect_timeout_s: float,
    file_timeout_s: float,
    siblings_cache: dict[str, dict[str, str]],
    independent_judging: bool = False,
) -> dict[str, Any]:
    """分析一个归档任务行：state 重建 → 生产注入 → LLM-only 重放 → 增强重放分类。

    任何材料/执行不可用都记 ``structural_skip`` + 原因码（不静默跳过）；
    注入统计为纯函数结果，即使后续 replay 不可用也保留（可审计）。

    ``independent_judging=True``（N-3）：state 只带 ``spec_anchor``（复刻生产
    df_spec 类臂形态，同时验证接线修复），并用生产 ``_m1_metrics`` 的 LLM-suite /
    oracle-suite 分离判读替代本工具的混判复算；结果写入 ``independent`` 字段。
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
        "status": "ok",
        "skip_reason": None,
        "skip_detail": "",
        "artifact_detection_rate": _as_float_or_none(row.get("detection_rate")),
        "artifact_spec_oracle_verdict": normalize_archived_verdict(row.get("spec_oracle_verdict")),
        "artifact_spec_oracle_injected": _as_bool_or_none(row.get("spec_oracle_injected")),
        "anchor": {"key_sha256": None, "function_name": None, "hit": False},
        "target": {
            "module_name": None,
            "target_function": None,
            "buggy_source_path": None,
            "buggy_source_sha256": None,
            "fixed_source_sha256": None,
            "generated_test_sha256": sha256_text(generated_test) if generated_test else None,
            "n_ast_test_defs": 0,
        },
        "injection": {
            "verdict": None,
            "injected": None,
            "attempted": None,
            "oracle_code_len": 0,
            "oracle_code_sha256": None,
            "merged_sha256": None,
            "n_oracle_test_defs": 0,
        },
        "archived_check": {
            "replay_verdict": None,
            "replay_injected": None,
            "verdict_agreement": "not_applicable",
            "field_consistency": None,
            "field_consistency_detail": "",
        },
        "llm_only": {
            "status": None,
            "skip_reason": None,
            "n_classifiable": 0,
            "counts": dict.fromkeys(mm.CLASSES, 0),
            "replay_detection": None,
            "replay_detection_strict": None,
            "detection_agreement": "not_applicable",
            "detection_disagreement_reason": "",
        },
        "oracle": {
            "status": "not_run",
            "skip_reason": None,
            "skip_detail": "",
            "n_collected_total": 0,
            "n_oracle_nodes": 0,
            "n_classifiable": 0,
            "counts": dict.fromkeys(ORACLE_CLASSES, 0),
            "unclassifiable": {},
            "failure_stats": {},
            "tests": [],
        },
        "detection": {
            "archived": None,
            "llm_only_replay": None,
            "augmented_replay": None,
            "transition": "undecidable",
        },
        # N-3 独立判读（--independent-judging；非该模式时保持默认"未判读"）
        "independent": {
            "status": "not_run",
            "skip_reason": None,
            "skip_detail": "",
            "llm_suite_detection": None,
            "oracle_suite_verdict": "unavailable",
            "state_mode": None,
            "judge_wall_s": 0.0,
        },
        "timing": {"total_wall_s": 0.0, "llm_only_wall_s": 0.0, "augmented_wall_s": 0.0},
    }
    t_total = time.time()

    # ① 基本材料校验（与 misguided_metrics 同口径）
    if not task_id or not task_metadata:
        return _finish_fast(_skip(record, "artifact_row_malformed", "归档行缺 task_id 或 task_metadata"), t_total)
    if not generated_test.strip():
        return _finish_fast(_skip(record, "empty_generated_test", "归档 generated_test 为空"), t_total)
    if not _PY_IDENT_RE.match(program or ""):
        return _finish_fast(
            _skip(record, "invalid_program_name", f"程序名不是合法 Python 标识符: {program!r}"), t_total
        )
    n_ast = _count_ast_test_defs(generated_test)
    record["target"]["n_ast_test_defs"] = n_ast
    if n_ast < 0:
        return _finish_fast(_skip(record, "generated_test_syntax_error", "generated_test 无法通过 ast.parse"), t_total)
    if is_oracle_node(generated_test):
        # 归档测试已含注入 oracle（本批次为 0）→ 二次注入会破坏"oracle 测试"的
        # 可分离性（同名函数覆盖），保守跳过并单列（不静默去重）。
        return _finish_fast(
            _skip(record, "already_contains_oracle", "归档 generated_test 已含 oracle 测试名，拒绝二次注入"),
            t_total,
        )

    fixed_code = str(task_metadata.get("fixed") or "")
    if not fixed_code.strip():
        return _finish_fast(_skip(record, "missing_fixed_material", "task_metadata.fixed 为空"), t_total)
    try:
        ast.parse(fixed_code)
    except SyntaxError as e:
        return _finish_fast(_skip(record, "fixed_material_unparseable", f"task_metadata.fixed 语法错误: {e}"), t_total)
    record["target"]["fixed_source_sha256"] = sha256_text(fixed_code)

    # ② 缺陷版源码解析与校验（生产 state.target_code 的重建材料）
    try:
        buggy_code, buggy_path = resolve_buggy_source(program, roots)
        dataset_fixed = dataset_fixed_source(program, roots)
        validate_buggy_source(buggy_code, program, task_metadata, dataset_fixed)
    except mm.MaterialError as e:
        return _finish_fast(_skip(record, e.reason, e.detail), t_total)
    record["target"]["buggy_source_path"] = _display_path(buggy_path)
    record["target"]["buggy_source_sha256"] = sha256_text(buggy_code)
    record["defect_signal"] = buggy_code.strip() != fixed_code.strip()

    # ③ 锚表查找（内容寻址；生产臂同口径）——未命中即结构跳过（覆盖率是一等数）
    digest, anchor_entry = lookup_anchor(anchors, buggy_code)
    record["anchor"]["key_sha256"] = digest
    record["anchor"]["hit"] = anchor_entry is not None
    if anchor_entry is None:
        return _finish_fast(
            _skip(record, "anchor_miss", f"缺陷版源码内容哈希不在锚表: {digest[:16]}…（锚覆盖率不足）"),
            t_total,
        )
    function_name = anchor_entry.get("function_name")
    logic_analysis = anchor_entry.get("logic_analysis")
    if not isinstance(function_name, str) or not function_name.strip() or not isinstance(logic_analysis, dict):
        return _finish_fast(
            _skip(record, "anchor_malformed", "锚表条目缺 function_name 或 logic_analysis dict"),
            t_total,
        )
    record["anchor"]["function_name"] = function_name.strip()
    if independent_judging:
        # N-3 独立判读：忠实复刻生产 df_spec/doc/union/augment 臂的 state 形态
        # ——只有 spec_anchor、**没有** test_plan（修复前的接线缺口正是此形态
        # 永远 not_attempted）。本模式因此同时验证生产接线修复。
        state = reconstruct_state_anchor_only(task_id, task_metadata, anchor_entry, buggy_code)
        record["independent"]["state_mode"] = "anchor_only"
    else:
        state = reconstruct_state(task_id, task_metadata, anchor_entry, buggy_code)
        record["independent"]["state_mode"] = "test_plan"
    record["target"]["module_name"] = state.get("module_name")
    record["target"]["target_function"] = state.get("target_function")

    # ④ 生产注入函数原样调用（反事实 state）
    merged_test, injected, verdict = production_inject_oracle(generated_test, state)
    record["injection"]["verdict"] = verdict
    record["injection"]["injected"] = bool(injected)
    record["injection"]["attempted"] = verdict != "not_attempted"
    if injected:
        appended = merged_test[len(generated_test) :]
        record["injection"]["oracle_code_len"] = len(appended)
        record["injection"]["oracle_code_sha256"] = sha256_text(appended)
        record["injection"]["merged_sha256"] = sha256_text(merged_test)
        record["injection"]["n_oracle_test_defs"] = _count_oracle_defs(merged_test)

    # ⑤ 归档语义复现（state 无 test_plan → 生产函数应返回 not_attempted）
    archived_state = reconstruct_state(task_id, task_metadata, anchor_entry, buggy_code, archived_state=True)
    _a_merged, a_injected, a_verdict = production_inject_oracle(generated_test, archived_state)
    record["archived_check"]["replay_verdict"] = a_verdict
    record["archived_check"]["replay_injected"] = bool(a_injected)
    archived_ok, archived_detail = archive_field_consistency(
        record["artifact_spec_oracle_verdict"], record["artifact_spec_oracle_injected"]
    )
    record["archived_check"]["field_consistency"] = archived_ok
    record["archived_check"]["field_consistency_detail"] = archived_detail
    if a_verdict == record["artifact_spec_oracle_verdict"]:
        record["archived_check"]["verdict_agreement"] = "match"
    else:
        record["archived_check"]["verdict_agreement"] = "mismatch"

    # N-3 独立判读模式：不走 M-2 的 LLM-only/增强混判路径，改为直接调用
    # **生产判读链**（_m1_metrics：LLM-suite detection + oracle-suite 独立判定）。
    if independent_judging:
        record["detection"]["archived"] = record["artifact_detection_rate"]
        record["independent"] = judge_task_independent(
            task_id=task_id,
            task_metadata=task_metadata,
            buggy_code=buggy_code,
            fixed_code=fixed_code,
            generated_test=generated_test,
            merged_test=merged_test,
            injected=bool(injected),
            injection_verdict=verdict,
        )
        return _finish_fast(record, t_total)

    # ⑥ LLM-only 重放（复用 T2 工具的完整分析：detection 交叉校验 + 材料校验）
    t_llm = time.time()
    if program not in siblings_cache:
        siblings_cache[program] = collect_siblings(buggy_path)
    siblings = siblings_cache[program]
    base = mm.analyze_task(
        row,
        roots=roots,
        pytest_timeout_s=pytest_timeout_s,
        collect_timeout_s=collect_timeout_s,
        file_timeout_s=file_timeout_s,
        siblings_cache=siblings_cache,
    )
    record["timing"]["llm_only_wall_s"] = round(time.time() - t_llm, 3)
    record["llm_only"] = {
        "status": base.get("status"),
        "skip_reason": base.get("skip_reason"),
        "n_classifiable": int(base.get("n_classifiable") or 0),
        "counts": dict(base.get("counts") or dict.fromkeys(mm.CLASSES, 0)),
        "replay_detection": base.get("replay_detection"),
        "replay_detection_strict": base.get("replay_detection_strict"),
        "detection_agreement": _detection_agreement(record["artifact_detection_rate"], base.get("replay_detection")),
        "detection_disagreement_reason": _detection_disagreement_reason(
            record["artifact_detection_rate"],
            base.get("replay_detection"),
            base.get("replay_detection_strict"),
            base.get("buggy_side") or {},
            base.get("fixed_side") or {},
        ),
    }
    record["detection"]["archived"] = record["artifact_detection_rate"]
    record["detection"]["llm_only_replay"] = base.get("replay_detection")

    # ⑦ oracle-augmented 重放（仅注入成功且 LLM-only 侧可 replay 时）
    if not injected:
        record["oracle"]["status"] = "not_run"
        record["oracle"]["skip_reason"] = "not_injected"
        record["oracle"]["skip_detail"] = f"注入 verdict={verdict}（无 oracle 测试可分类）"
        return _finish_fast(record, t_total)
    llm_only_side_ok = _llm_only_side_replayable(base)
    if not llm_only_side_ok:
        record["oracle"]["status"] = "not_run"
        record["oracle"]["skip_reason"] = "llm_only_not_replayable"
        record["oracle"]["skip_detail"] = f"LLM-only 侧不可 replay（{base.get('skip_reason') or '未知'}）"
        return _finish_fast(record, t_total)

    t_aug = time.time()
    tmpdir = Path(tempfile.mkdtemp(prefix=f"oracle_{program}_"))
    try:
        buggy_dir = tmpdir / "buggy"
        fixed_dir = tmpdir / "fixed"
        try:
            materialize_version(buggy_dir, program, buggy_code, merged_test, siblings)
            materialize_version(fixed_dir, program, fixed_code, merged_test, siblings)
        except OSError as e:
            return _finish_fast(_skip(record, "materialize_failed", f"增强重放物化失败: {e}"), t_total)
        aug_buggy = run_side(
            version_dir=buggy_dir,
            pytest_timeout_s=pytest_timeout_s,
            collect_timeout_s=collect_timeout_s,
            file_timeout_s=file_timeout_s,
        )
        aug_fixed = run_side(
            version_dir=fixed_dir,
            pytest_timeout_s=pytest_timeout_s,
            collect_timeout_s=collect_timeout_s,
            file_timeout_s=file_timeout_s,
        )
        buggy_notes = parse_junit_failure_notes(buggy_dir / "junit.xml")
        fixed_notes = parse_junit_failure_notes(fixed_dir / "junit.xml")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    record["timing"]["augmented_wall_s"] = round(time.time() - t_aug, 3)

    side_failure = _side_failure_reason(aug_buggy, aug_fixed)
    if side_failure is not None:
        record["oracle"]["status"] = "not_run"
        record["oracle"]["skip_reason"] = "augmented_side_unavailable"
        record["oracle"]["skip_detail"] = f"{side_failure[0]}: {side_failure[1]}"
        return _finish_fast(record, t_total)
    nodes = sorted(
        {
            *[str(n) for n in (aug_buggy.get("collected") or [])],
            *[str(n) for n in (aug_fixed.get("collected") or [])],
            *[str(n) for n in (aug_buggy.get("outcomes") or {})],
            *[str(n) for n in (aug_fixed.get("outcomes") or {})],
        }
    )
    oracle_nodes = [n for n in nodes if is_oracle_node(n)]
    record["oracle"]["n_collected_total"] = len(nodes)
    record["oracle"]["n_oracle_nodes"] = len(oracle_nodes)
    if not oracle_nodes:
        record["oracle"]["status"] = "not_run"
        record["oracle"]["skip_reason"] = "no_oracle_tests_collected"
        record["oracle"]["skip_detail"] = "增强重放未收集到 oracle 测试节点（注入产物收集失败？）"
        return _finish_fast(record, t_total)
    rows, counts, unclassifiable = classify_oracle_outcomes(
        oracle_nodes,
        aug_buggy.get("outcomes") or {},
        aug_fixed.get("outcomes") or {},
        buggy_missing_reason=aug_buggy.get("missing_reason") or "missing_side",
        fixed_missing_reason=aug_fixed.get("missing_reason") or "missing_side",
    )
    for row_out in rows:
        node = str(row_out["node"])
        buggy_note = buggy_notes.get(node) or {}
        fixed_note = fixed_notes.get(node) or {}
        row_out["buggy_failure_kind"] = buggy_note.get("kind")
        row_out["fixed_failure_kind"] = fixed_note.get("kind")
        # O-1：fp 细分（断言型 vs 仪器失效型）与 skip 原因（稳定键，不含消息正文）
        row_out["fp_kind"] = classify_fp_kind(fixed_note) if row_out.get("cls") == "fp" else None
        row_out["buggy_skip_reason"] = buggy_note.get("skip_reason") if buggy_note.get("tag") == "skipped" else None
        row_out["fixed_skip_reason"] = fixed_note.get("skip_reason") if fixed_note.get("tag") == "skipped" else None
    record["oracle"].update(
        {
            "status": "ok",
            "n_classifiable": sum(counts.values()),
            "counts": counts,
            "unclassifiable": {k: v for k, v in unclassifiable.items() if v},
            "failure_stats": _oracle_failure_stats(rows, buggy_notes, fixed_notes),
            "tests": rows,
        }
    )
    if record["oracle"]["n_classifiable"] == 0:
        record["oracle"]["status"] = "not_run"
        record["oracle"]["skip_reason"] = "no_classifiable_oracle_tests"
        record["oracle"]["skip_detail"] = f"oracle 节点全部不可分类（{record['oracle']['unclassifiable']}）"
    aug_detection = replay_detection(aug_buggy, aug_fixed)
    record["detection"]["augmented_replay"] = aug_detection
    record["detection"]["transition"] = injection_transition(base.get("replay_detection"), aug_detection)
    return _finish_fast(record, t_total)


def _finish_fast(record: dict[str, Any], t_total: float) -> dict[str, Any]:
    """写 public 计时并返回记录（避免顶层 ``_finish`` 闭包在 early-return 处重复）。"""
    record["timing"]["total_wall_s"] = round(time.time() - t_total, 3)
    return record


def _count_oracle_defs(code: str) -> int:
    """统计代码中 oracle 测试函数定义数（生产名子串匹配，语法错误 → 0）。"""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return 0
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and is_oracle_node(node.name)
    )


def _llm_only_side_replayable(base: dict[str, Any]) -> bool:
    """LLM-only 重放两侧是否足以作为增强重放的对照（收集成功、未整文件超时）。"""
    for side in (base.get("buggy_side") or {}, base.get("fixed_side") or {}):
        if not isinstance(side, dict):
            return False
        if not side.get("collect_ok"):
            return False
        if side.get("exec_timed_out"):
            return False
    return bool(base.get("buggy_side")) and bool(base.get("fixed_side"))


# ─── N-3 独立判读（生产 _m1_metrics 链原样套用） ────────────────────────────
@dataclass(frozen=True)
class _ArchivedTask:
    """把归档行包装成 ``_m1_metrics`` 判分函数可消费的最小任务对象。

    只提供判分路径实际读取的属性（``task_id`` / ``instance_code`` /
    ``metadata``）：metadata 必须保留归档原始字段（``source`` /
    ``test_cases`` / ``fixed`` / ``is_cross_file`` 等），由 _m1_metrics 的
    ``_extract_gold_material`` / ``_gold_fixed_code`` / 物化分派消费。
    """

    task_id: str
    instance_code: str
    metadata: dict[str, Any]
    repo_name: str = "quixbugs"


def m1_llm_suite_detection(task: Any, final_state: dict[str, Any] | None) -> float | None:
    """生产 M1 判分：LLM-suite detection（N-3 语义，排除 oracle 测试）。

    惰性 import 生产函数（单测可 monkeypatch 本包装器以避开真实子进程）。
    """
    from experiments._m1_metrics import _compute_llm_suite_detection_rate

    return _compute_llm_suite_detection_rate(task, final_state)


def m1_oracle_suite_verdict(task: Any, final_state: dict[str, Any] | None) -> str:
    """生产 M1 判分：oracle-suite 独立判定（correct/fp/silent/misguided/unavailable）。"""
    from experiments._m1_metrics import _compute_oracle_suite_verdict

    return _compute_oracle_suite_verdict(task, final_state)


def judge_task_independent(
    *,
    task_id: str,
    task_metadata: dict[str, Any],
    buggy_code: str,
    fixed_code: str,
    generated_test: str,
    merged_test: str,
    injected: bool,
    injection_verdict: str,
) -> dict[str, Any]:
    """N-3：对单任务跑生产独立判读链（LLM-suite detection + oracle-suite 判定）。

    Args:
        task_id / task_metadata / buggy_code: 归档任务与缺陷版源码（构造判分对象）。
        fixed_code: 归档 gold fixed（_m1_metrics 从 metadata 自行读取；参数保留
            以便调用方语义完整/未来扩展）。
        generated_test / merged_test: LLM-only 与注入后测试全文（仅用于审计字段）。
        injected / injection_verdict: 生产注入结果（未注入 → 不判 read）。

    Returns:
        independent 记录 dict（status/skip_reason/llm_suite_detection/
        oracle_suite_verdict/state_mode/judge_wall_s + 审计字段）。
    """
    record: dict[str, Any] = {
        "status": "not_run",
        "skip_reason": None,
        "skip_detail": "",
        "llm_suite_detection": None,
        "oracle_suite_verdict": "unavailable",
        "state_mode": "anchor_only",
        "judge_wall_s": 0.0,
        "injection_verdict": injection_verdict,
        "merged_has_oracle_markers": is_oracle_node(merged_test),
        "merged_test_sha256": sha256_text(merged_test),
        "generated_test_sha256": sha256_text(generated_test),
    }
    task = _ArchivedTask(task_id=task_id, instance_code=str(buggy_code), metadata=dict(task_metadata))
    final_state: dict[str, Any] = {"generated_test": str(merged_test)}
    t0 = time.time()
    try:
        # LLM-suite detection 与注入与否**无关**：未注入（compiled_empty /
        # not_attempted_* / human_spec_only）任务的 LLM 测试仍有检出语义，
        # 必须照常计算，否则 40 口径分母会因"未注入"被动缩小、与 M-2 基线
        # 不可比。oracle-suite 判定仅在真正注入时执行（未注入 = unavailable）。
        detection = m1_llm_suite_detection(task, final_state)
        oracle_verdict = m1_oracle_suite_verdict(task, final_state) if injected else "unavailable"
    except Exception as e:  # pragma: no cover - 生产函数内部已 fail-closed；此处兜底不崩报告
        record.update(status="error", skip_reason="independent_judge_error", skip_detail=str(e))
        record["judge_wall_s"] = round(time.time() - t0, 3)
        return record
    record.update(
        status="ok",
        llm_suite_detection=detection,
        oracle_suite_verdict=oracle_verdict,
    )
    if not injected:
        record["skip_reason"] = "not_injected"
        record["skip_detail"] = f"注入 verdict={injection_verdict}（oracle 判定 unavailable；LLM-suite 照常判读）"
    record["judge_wall_s"] = round(time.time() - t0, 3)
    return record


# ─── M-2 报告加载与逐任务对账 ─────────────────────────────────────────────
def load_m2_report(path: Path) -> dict[str, Any]:
    """加载 M-2 oracle 质量报告（独立判读对账的权威基线；缺失 fail-closed）。

    Returns:
        {"path", "sha256", "report", "arm_index"}；arm_index 见
        ``index_m2_report``。

    Raises:
        OracleQualityError: 文件缺失 / JSON 非法 / 结构不合法。
    """
    if not path.is_file():
        raise OracleQualityError(f"M-2 基线报告不存在（--independent-judging 需要）: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise OracleQualityError(f"M-2 基线报告无法解析: {path}: {e}") from e
    report = payload.get("report") if isinstance(payload, dict) else None
    if not isinstance(report, dict) or not report.get("arms"):
        raise OracleQualityError(f"M-2 基线报告结构不合法（缺 report.arms）: {path}")
    return {
        "path": _display_path(path),
        "sha256": sha256_file(path),
        "body_digest": (payload.get("run_meta") or {}).get("body_digest"),
        "report": report,
        "arm_index": index_m2_report(report),
    }


def index_m2_report(m2_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """把 M-2 报告索引成 {arm: {task_id: 对账字段}}。

    对账字段：
        - ``llm_only_replay_detection``：M-2 LLM-only 重放任务级 detection；
        - ``oracle_class``：M-2 四分类（每任务 1 条 oracle 测试 → 类别即任务级）；
        - ``injection_verdict``：M-2 反事实注入 verdict；
        - ``oracle_status``/``status``：M-2 可测性上下文。
    另把臂级 40 口径基线放进 ``"aggregate"`` 键（用于 pooled 率对账）。
    """
    index: dict[str, dict[str, Any]] = {}
    for arm in m2_report.get("arms") or []:
        tasks: dict[str, dict[str, Any]] = {}
        for task in arm.get("tasks") or []:
            counts = (task.get("oracle") or {}).get("counts") or {}
            oracle_class = next((cls for cls in ORACLE_CLASSES if int(counts.get(cls) or 0) > 0), None)
            tasks[str(task.get("task_id"))] = {
                "llm_only_replay_detection": (task.get("llm_only") or {}).get("replay_detection"),
                "oracle_class": oracle_class,
                "oracle_status": (task.get("oracle") or {}).get("status"),
                "injection_verdict": (task.get("injection") or {}).get("verdict"),
                "status": task.get("status"),
            }
        subsets = arm.get("subsets") or {}
        defect = subsets.get("defect_programs") or {}
        index[str(arm.get("arm"))] = {
            "tasks": tasks,
            "aggregate": {
                "llm_only_replay_40": (defect.get("detection") or {}).get("llm_only_replay") or {},
                "oracle_counts_40": (defect.get("oracle") or {}).get("counts") or {},
                "injection_40": (defect.get("injection") or {}),
            },
        }
    return index


def _oracle_class_agreement_tag(m2_class: Any, new_verdict: Any) -> str:
    """M-2 oracle 类别 vs N-3 独立 oracle verdict 的对账标签。"""
    m2_norm = str(m2_class) if m2_class else None
    new_norm = None if new_verdict in (None, "unavailable") else str(new_verdict)
    if m2_norm is None and new_norm is None:
        return "both_unavailable"
    if m2_norm is None:
        return "new_measured_m2_unavailable"
    if new_norm is None:
        return "m2_measured_new_unavailable"
    return "match" if m2_norm == new_norm else "mismatch"


def build_independent_cross_check(
    tasks: list[dict[str, Any]],
    m2_arm: dict[str, Any] | None,
) -> dict[str, Any]:
    """N-3 独立判读 vs M-2 基线的逐任务对账（detection 0 mismatch 要求）。

    Returns:
        - detection 对账计数（match / both_none / mismatch / m2_task_missing）；
        - 逐条 mismatch 归因（不静默）；
        - oracle 类别对账计数与差异清单（描述性，不要求 0 mismatch）；
        - injection 对账（anchor-only 接线后的注入 verdict vs M-2 反事实注入）；
        - ``all_ok`` = detection mismatch 0 且无缺失任务。
    """
    detection_counts: Counter[str] = Counter()
    detection_mismatches: list[dict[str, Any]] = []
    class_counts: Counter[str] = Counter()
    class_mismatches: list[dict[str, Any]] = []
    injection_counts: Counter[str] = Counter()
    m2_tasks: dict[str, Any] = (m2_arm or {}).get("tasks") or {}
    for task in tasks:
        task_id = str(task.get("task_id"))
        independent = task.get("independent") or {}
        m2 = m2_tasks.get(task_id)
        if not isinstance(m2, dict):
            detection_counts["m2_task_missing"] += 1
            detection_mismatches.append({"task_id": task_id, "reason": "M-2 基线报告缺该任务（无法对账）"})
            continue
        new_detection = independent.get("llm_suite_detection") if independent.get("status") == "ok" else None
        m2_detection = m2.get("llm_only_replay_detection")
        tag = _detection_agreement(m2_detection, new_detection)
        detection_counts[tag] += 1
        if tag == "mismatch":
            detection_mismatches.append(
                {
                    "task_id": task_id,
                    "m2_llm_only_replay_detection": m2_detection,
                    "n3_llm_suite_detection": new_detection,
                    "agreement": tag,
                    "reason": (
                        "独立 LLM-suite 与 M-2 LLM-only 重放在同一任务上结论不同——需人工归因（物化/超时/执行环境差异）"
                    ),
                }
            )
        class_tag = _oracle_class_agreement_tag(m2.get("oracle_class"), independent.get("oracle_suite_verdict"))
        class_counts[class_tag] += 1
        if class_tag in {"mismatch", "m2_measured_new_unavailable", "new_measured_m2_unavailable"}:
            class_mismatches.append(
                {
                    "task_id": task_id,
                    "m2_oracle_class": m2.get("oracle_class"),
                    "n3_oracle_suite_verdict": independent.get("oracle_suite_verdict"),
                    "agreement": class_tag,
                }
            )
        task_injection = (task.get("injection") or {}).get("verdict")
        m2_injection = m2.get("injection_verdict")
        if task_injection == m2_injection:
            injection_counts["same_verdict"] += 1
        elif bool((task.get("injection") or {}).get("injected")) == bool(
            str(m2_injection) in {"injected", "injected_and_passed", "injected_and_failed"}
        ):
            injection_counts["same_injected_flag_refined_verdict"] += 1
        else:
            injection_counts["injected_flag_mismatch"] += 1
    detection_mismatch_n = detection_counts.get("mismatch", 0)
    all_ok = detection_mismatch_n == 0 and detection_counts.get("m2_task_missing", 0) == 0
    return {
        "requirement": "LLM-suite detection 与 M-2 基线逐任务 0 mismatch（差异逐条归因）",
        "detection_vs_m2": {
            "agreement_counts": dict(sorted(detection_counts.items())),
            "n_mismatch": detection_mismatch_n,
            "mismatches": detection_mismatches,
        },
        "oracle_class_vs_m2": {
            "agreement_counts": dict(sorted(class_counts.items())),
            "n_mismatch": class_counts.get("mismatch", 0),
            "mismatches": class_mismatches,
            "note": (
                "M-2 类别来自『LLM+oracle 同文件混判重放』的逐测试分类；N-3 为生产独立判读"
                "（oracle 单独 -k 运行）。类别差异属预期可比对项（描述性），不作 0 mismatch 要求"
            ),
        },
        "injection_vs_m2": {
            "agreement_counts": dict(sorted(injection_counts.items())),
            "note": (
                "N-3 用 anchor-only state（复刻生产 df_spec 臂）注入；M-2 反事实用 test_plan state。"
                "same_injected_flag_refined_verdict = 注入与否一致、但 N-3 细分了未尝试原因"
                "（如 node：not_attempted → not_attempted_anchor_unparseable）"
            ),
        },
        "all_ok": all_ok,
    }


def aggregate_independent(
    tasks: list[dict[str, Any]],
    m2_arm: dict[str, Any] | None,
    *,
    limited: bool = False,
) -> dict[str, Any]:
    """N-3 独立判读臂级聚合（分子/分母按子集重算，不做比率平均）。

    Args:
        tasks: 任务记录（含 independent 段）。
        m2_arm: M-2 基线臂索引（tasks/aggregate）。
        limited: 本次是否 --limit 截断（截断运行不能要求与 M-2 全量 40 口径
            计数一致；只保留逐任务 0 mismatch 要求，并在报告披露）。

    Returns:
        {"subsets": {subset: {...llm_suite/oracle_suite 计数与率...}},
         "cross_check_vs_m2": {...}, "m2_baseline_40caliber": {...},
         "m2_rates_match": bool, "measurement_limited": bool, "all_ok": bool}
    """
    subsets_out: dict[str, Any] = {}
    for subset in _SUBSETS:
        subset_tasks = _subset_tasks(tasks, subset)
        judged = [t for t in subset_tasks if (t.get("independent") or {}).get("status") == "ok"]
        det_values: list[float] = []
        for judged_task in judged:
            value = (judged_task.get("independent") or {}).get("llm_suite_detection")
            if value is not None:
                det_values.append(float(value))
        n_detected = sum(1 for value in det_values if round(value) == 1)
        verdicts: Counter[str] = Counter(
            str((t.get("independent") or {}).get("oracle_suite_verdict") or "unavailable") for t in judged
        )
        subsets_out[subset] = {
            "n_tasks": len(subset_tasks),
            "n_tasks_judged": len(judged),
            "n_tasks_structural_skip": sum(1 for t in subset_tasks if t.get("status") != "ok"),
            "n_tasks_not_injected": sum(
                1 for t in subset_tasks if (t.get("independent") or {}).get("skip_reason") == "not_injected"
            ),
            "llm_suite_detection": {
                "n_detected": n_detected,
                "n_denominator": len(det_values),
                "rate": round(n_detected / len(det_values), 6) if det_values else None,
            },
            "oracle_suite_counts": {
                verdict: int(verdicts.get(verdict, 0))
                for verdict in ("correct", "fp", "silent", "misguided", "unavailable")
            },
        }
    cross_check = build_independent_cross_check(tasks, m2_arm)
    aggregate = (m2_arm or {}).get("aggregate") or {}
    m2_baseline_40 = aggregate.get("llm_only_replay_40") or {}
    n3_40 = subsets_out.get("defect_programs", {}).get("llm_suite_detection") or {}
    rates_match = m2_baseline_40.get("n_detected") == n3_40.get("n_detected") and m2_baseline_40.get(
        "n_denominator"
    ) == n3_40.get("n_denominator")
    return {
        "subsets": subsets_out,
        "cross_check_vs_m2": cross_check,
        "m2_baseline_40caliber": m2_baseline_40,
        "m2_rates_match": bool(rates_match),
        "measurement_limited": bool(limited),
        "all_ok": bool(cross_check["all_ok"] and (rates_match or limited)),
        "note": (
            "--limit 截断运行：40 口径计数不要求与 M-2 全量一致（只验证逐任务 0 mismatch）"
            if limited
            else "全量运行：40 口径计数必须与 M-2 基线完全一致"
        ),
    }


# ─── 聚合 ──────────────────────────────────────────────────────────────────
def _subset_tasks(tasks: list[dict[str, Any]], subset: str) -> list[dict[str, Any]]:
    """取任务子集（all_tasks / defect_programs / defect_programs_41 / injected_measurable）。"""
    if subset == "all_tasks":
        return tasks
    if subset == "defect_programs":
        return [t for t in tasks if t.get("analysis_set") == "defect_program" and t.get("defect_signal") is True]
    if subset == "defect_programs_41_convention":
        return [t for t in tasks if t.get("analysis_set") == "defect_program"]
    if subset == "injected_measurable":
        return [t for t in tasks if (t.get("oracle") or {}).get("status") == "ok"]
    raise OracleQualityError(f"未知任务子集: {subset}")


def aggregate_injection(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    """注入统计（锚命中 / 尝试 / 注入成功 / 编译非空率 / 每任务 oracle 测试数）。"""
    n_anchor_hit = sum(1 for t in tasks if (t.get("anchor") or {}).get("hit"))
    verdicts: Counter[str] = Counter()
    n_attempted = 0
    n_injected = 0
    n_compiled_empty = 0
    oracle_test_counts: list[float] = []
    for task in tasks:
        injection = task.get("injection") or {}
        verdict = str(injection.get("verdict") or "not_run")
        if injection.get("verdict") is None:
            verdicts["not_run"] += 1
            continue
        verdicts[verdict] += 1
        if injection.get("attempted"):
            n_attempted += 1
        if injection.get("injected"):
            n_injected += 1
            oracle = task.get("oracle") or {}
            independent = task.get("independent") or {}
            if oracle.get("status") == "ok":
                oracle_test_counts.append(float(oracle.get("n_oracle_nodes") or 0))
            elif independent.get("status") == "ok":
                # N-3 独立判读模式：生产 _m1 判分链每任务 1 条 oracle-suite 判定
                oracle_test_counts.append(float(1))
        elif verdict == "compiled_empty":
            n_compiled_empty += 1
    n_rows = len(tasks)
    return {
        "n_task_rows": n_rows,
        "n_anchor_hit": n_anchor_hit,
        "anchor_hit_rate": round(n_anchor_hit / n_rows, 6) if n_rows else None,
        "n_attempted": n_attempted,
        "n_injected": n_injected,
        "n_compiled_empty": n_compiled_empty,
        "verdict_counts": dict(sorted(verdicts.items())),
        "injection_rate_of_rows": round(n_injected / n_rows, 6) if n_rows else None,
        "injection_rate_of_attempted": round(n_injected / n_attempted, 6) if n_attempted else None,
        "compiled_nonempty_rate_of_attempted": round(n_injected / n_attempted, 6) if n_attempted else None,
        "n_tasks_with_measurable_oracle": len(oracle_test_counts),
        "oracle_tests_per_measurable_task": _summary(oracle_test_counts),
    }


def aggregate_oracle(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    """oracle 四分类聚合（分母 = 可分类 oracle 测试数；不可分类单列）。"""
    counts: dict[str, int] = dict.fromkeys(ORACLE_CLASSES, 0)
    unclassifiable: Counter[str] = Counter()
    buggy_kinds: Counter[str] = Counter()
    fixed_kinds: Counter[str] = Counter()
    fixed_exceptions: Counter[str] = Counter()
    skip_reasons: Counter[str] = Counter()
    fp_breakdown: Counter[str] = Counter({FP_FLAG_ASSERTION: 0, FP_INSTRUMENT_ERROR: 0, FP_UNATTRIBUTED: 0})
    per_task_tests: list[float] = []
    task_counts: Counter[str] = Counter()
    n_measured_tasks = 0
    for task in tasks:
        oracle = task.get("oracle") or {}
        # O-1：做过 oracle 收集（n_oracle_nodes>0）但全部不可分类的任务
        # （status=not_run + skip_reason=no_classifiable_oracle_tests）也必须
        # 计入不可分类统计——否则加固后 skipped 会"凭空消失"（分母缩小的
        # 原因不可见，正是 M-2 类测量伪影的复发形态）。
        if oracle.get("status") != "ok" and not int(oracle.get("n_oracle_nodes") or 0):
            continue
        n_measured_tasks += 1
        per_task_tests.append(float(oracle.get("n_oracle_nodes") or 0))
        for cls in ORACLE_CLASSES:
            n = int((oracle.get("counts") or {}).get(cls) or 0)
            counts[cls] += n
            if n:
                task_counts[cls] += 1
        for reason, value in (oracle.get("unclassifiable") or {}).items():
            if value:
                unclassifiable[str(reason)] += int(value)
        stats = oracle.get("failure_stats") or {}
        for kind, value in (stats.get("buggy_side_failure_kinds") or {}).items():
            if value:
                buggy_kinds[str(kind)] += int(value)
        for kind, value in (stats.get("fixed_side_failure_kinds") or {}).items():
            if value:
                fixed_kinds[str(kind)] += int(value)
        for exc, value in (stats.get("fixed_side_exception_types") or {}).items():
            if value:
                fixed_exceptions[str(exc)] += int(value)
        # O-1：逐测试 fp 细分（断言型 / 仪器失效型 / 无归因）与 skip 侧归因。
        # skip 原因优先从 per-test 行取（唯一来源）；仅当旧/外部报告没有
        # per-test 行时才回退 failure_stats，避免同一 skip 被双计。
        test_rows = oracle.get("tests") or []
        if not test_rows:
            for reason, value in (stats.get("skip_reason_counts") or {}).items():
                if value:
                    skip_reasons[str(reason)] += int(value)
        for test_row in test_rows:
            if test_row.get("cls") == "fp":
                fp_breakdown[str(test_row.get("fp_kind") or FP_UNATTRIBUTED)] += 1
            # skip 原因按**测试**计一次（fixed 侧优先、回退 buggy 侧）——
            # 两侧同为 skip（崩溃 harness 常见形态）时不得双计。
            reason = test_row.get("fixed_skip_reason") or test_row.get("buggy_skip_reason")
            if reason:
                skip_reasons[str(reason)] += 1
    n_classifiable = sum(counts.values())
    n_skipped = int(unclassifiable.get("skipped", 0))
    return {
        "n_tasks_measured": n_measured_tasks,
        "n_oracle_tests_classifiable": n_classifiable,
        "n_oracle_tests_unclassifiable": sum(unclassifiable.values()),
        "counts": counts,
        # 旧四分类兼容映射：fp = fp_assertion_fail + instrument_error + fp_unattributed
        "counts_legacy_mapping": {
            "fp": counts["fp"],
            "fp_breakdown": dict(sorted(fp_breakdown.items())),
            "note": (
                "旧键 counts.fp 保留（= fp_assertion_fail + instrument_error + fp_unattributed）；"
                "instrument_error 为 fixed 侧异常/收集失败等非断言失败（O-1 从 fp 拆出，"
                "加固后新产物应转为 skipped/unavailable）；fp_assertion_fail 为断言型假阳"
            ),
        },
        "rates": {cls: (round(counts[cls] / n_classifiable, 6) if n_classifiable else None) for cls in ORACLE_CLASSES},
        "unclassifiable_counts": dict(sorted(unclassifiable.items())),
        "n_tasks_with_class": {cls: int(task_counts.get(cls, 0)) for cls in ORACLE_CLASSES},
        "per_task_oracle_tests": _summary(per_task_tests),
        "skipped_count": n_skipped,
        "skip_reason_counts": dict(sorted(skip_reasons.items())),
        "failure_stats": {
            "buggy_side_failure_kinds": dict(sorted(buggy_kinds.items())),
            "fixed_side_failure_kinds": dict(sorted(fixed_kinds.items())),
            "fixed_side_exception_types": dict(sorted(fixed_exceptions.items())),
            "skip_reason_counts": dict(sorted(skip_reasons.items())),
        },
    }


def detection_stats(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    """任务级 detection 三口径（归档 / LLM-only 重放 / oracle-augmented 重放）。

    分母纪律：每个比率的 n_denominator 只含该口径下**可判定**（非 None）的任务；
    oracle-augmented 只在"注入成功且增强重放可判"的任务上有值。
    """
    transitions: Counter[str] = Counter()
    added: list[dict[str, Any]] = []
    lost: list[dict[str, Any]] = []
    n_injected_tasks = 0
    for task in tasks:
        if (task.get("injection") or {}).get("injected"):
            n_injected_tasks += 1
        transition = task.get("detection", {}).get("transition") or "undecidable"
        transitions[str(transition)] += 1
        if transition == "added":
            added.append(
                {
                    "task_id": task.get("task_id"),
                    "oracle_counts": (task.get("oracle") or {}).get("counts"),
                    "oracle_nodes": (task.get("oracle") or {}).get("n_classifiable"),
                }
            )
        elif transition == "lost":
            fixed_kinds = ((task.get("oracle") or {}).get("failure_stats") or {}).get("fixed_side_failure_kinds") or {}
            lost.append(
                {
                    "task_id": task.get("task_id"),
                    "oracle_counts": (task.get("oracle") or {}).get("counts"),
                    "fixed_side_failure_kinds": fixed_kinds,
                }
            )

    def _rate(key: str) -> dict[str, Any]:
        values = [t["detection"][key] for t in tasks if (t.get("detection") or {}).get(key) is not None]
        detected = sum(1 for v in values if round(float(v)) == 1)
        return {
            "n_detected": detected,
            "n_denominator": len(values),
            "rate": round(detected / len(values), 6) if values else None,
        }

    paired = [
        t
        for t in tasks
        if (t.get("detection") or {}).get("llm_only_replay") is not None
        and (t.get("detection") or {}).get("augmented_replay") is not None
    ]
    paired_archived = [
        t
        for t in tasks
        if (t.get("detection") or {}).get("archived") is not None
        and (t.get("detection") or {}).get("llm_only_replay") is not None
    ]

    def _paired_delta(key_a: str, key_b: str, pair_list: list[dict[str, Any]]) -> dict[str, Any]:
        if not pair_list:
            return {"n_paired": 0, "delta_pp_b_minus_a": None}
        diffs = [round(float(t["detection"][key_b])) - round(float(t["detection"][key_a])) for t in pair_list]
        n_changed = sum(1 for d in diffs if d != 0)
        return {
            "n_paired": len(pair_list),
            "n_changed": n_changed,
            "delta_pp_b_minus_a": round(100.0 * sum(diffs) / len(diffs), 4),
        }

    return {
        "n_tasks_injected": n_injected_tasks,
        "archived": _rate("archived"),
        "llm_only_replay": _rate("llm_only_replay"),
        "oracle_augmented_replay": _rate("augmented_replay"),
        "paired_llm_only_vs_archived": _paired_delta("archived", "llm_only_replay", paired_archived),
        "paired_augmented_vs_llm_only": _paired_delta("llm_only_replay", "augmented_replay", paired),
        "transition_counts": dict(sorted(transitions.items())),
        "added_tasks": added,
        "lost_tasks": lost,
    }


def build_cross_check(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    """与归档 ``detection_rate`` / ``spec_oracle_verdict`` 的交叉校验（0 mismatch 要求）。"""
    detection_counts: Counter[str] = Counter()
    detection_mismatches: list[dict[str, Any]] = []
    verdict_counts: Counter[str] = Counter()
    verdict_mismatches: list[dict[str, Any]] = []
    consistency_violations: list[dict[str, Any]] = []
    for task in tasks:
        tag = str((task.get("llm_only") or {}).get("detection_agreement") or "not_applicable")
        detection_counts[tag] += 1
        if tag in {"mismatch", "artifact_none", "replay_none"}:
            item = {
                "task_id": task.get("task_id"),
                "artifact_detection_rate": task.get("artifact_detection_rate"),
                "replay_detection": (task.get("llm_only") or {}).get("replay_detection"),
                "replay_detection_strict": (task.get("llm_only") or {}).get("replay_detection_strict"),
                "agreement": tag,
                "reason": (task.get("llm_only") or {}).get("detection_disagreement_reason") or "",
                "llm_only_status": (task.get("llm_only") or {}).get("status"),
                "skip_reason": task.get("skip_reason"),
            }
            detection_mismatches.append(item)
        v_tag = str((task.get("archived_check") or {}).get("verdict_agreement") or "not_applicable")
        verdict_counts[v_tag] += 1
        if v_tag == "mismatch":
            verdict_mismatches.append(
                {
                    "task_id": task.get("task_id"),
                    "archived_verdict": task.get("artifact_spec_oracle_verdict"),
                    "replay_verdict": (task.get("archived_check") or {}).get("replay_verdict"),
                    "replay_injected": (task.get("archived_check") or {}).get("replay_injected"),
                    "reason": (
                        "归档批次 Planner 关闭（test_plan 缺席）但归档 verdict 非 not_attempted"
                        if is_oracle_node(task.get("task_id") or "")
                        else "归档 state 语义与生产注入口重放不一致（需人工核对）"
                    ),
                }
            )
        if (task.get("archived_check") or {}).get("field_consistency") is False:
            consistency_violations.append(
                {
                    "task_id": task.get("task_id"),
                    "detail": (task.get("archived_check") or {}).get("field_consistency_detail"),
                }
            )
    detection_mismatch_n = detection_counts.get("mismatch", 0)
    verdict_mismatch_n = verdict_counts.get("mismatch", 0)
    all_ok = detection_mismatch_n == 0 and verdict_mismatch_n == 0 and not consistency_violations
    return {
        "requirement": "0 mismatch（detection：两侧均可判但结论不同；verdict：归档 vs 归档语义重放）",
        "all_ok": all_ok,
        "detection_vs_archive": {
            "agreement_counts": dict(sorted(detection_counts.items())),
            "n_mismatch": detection_mismatch_n,
            "mismatch_or_attributed_nonmatch": detection_mismatches,
        },
        "oracle_verdict_vs_archive": {
            "agreement_counts": dict(sorted(verdict_counts.items())),
            "n_mismatch": verdict_mismatch_n,
            "mismatches": verdict_mismatches,
            "note": (
                "归档批次（plain_llm_df*，Planner 关闭）生产注入口未尝试注入；"
                "本项用『归档 state 语义』（无 test_plan）重放生产函数，验证归档 verdict 可复现。"
                "反事实注入 quality 统计见 injection 字段（不是归档字段复现）"
            ),
        },
        "archive_field_consistency_violations": consistency_violations,
    }


_SUBSETS: tuple[str, ...] = ("all_tasks", "defect_programs", "defect_programs_41_convention", "injected_measurable")


def build_arm_subset_stats(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    """各子集统计（all / 40 缺陷程序 / 41 口径 / 可测注入任务）。"""
    out: dict[str, Any] = {}
    for subset in _SUBSETS:
        subset_tasks = _subset_tasks(tasks, subset)
        ok_tasks = [t for t in subset_tasks if t.get("status") == "ok"]
        skips: Counter[str] = Counter(
            str(t.get("skip_reason")) for t in subset_tasks if t.get("status") == "structural_skip"
        )
        out[subset] = {
            "n_tasks": len(subset_tasks),
            "n_tasks_ok": sum(1 for t in subset_tasks if t.get("status") == "ok"),
            "n_tasks_structural_skip": sum(1 for t in subset_tasks if t.get("status") == "structural_skip"),
            "structural_skip_reasons": dict(sorted(skips.items())),
            "n_tasks_with_llm_only_classifiable": sum(
                1 for t in ok_tasks if (t.get("llm_only") or {}).get("n_classifiable")
            ),
            "injection": aggregate_injection(subset_tasks),
            "oracle": aggregate_oracle(subset_tasks),
            "detection": detection_stats(subset_tasks),
        }
    return out


# ─── 臂级结果与报告 ────────────────────────────────────────────────────────
def build_arm_result(
    *,
    artifact_path: Path,
    artifact_sha256: str,
    artifact_label: str,
    arm: str,
    rows: list[dict[str, Any]],
    anchors: dict[str, dict[str, Any]],
    roots: list[Path],
    pytest_timeout_s: float,
    collect_timeout_s: float,
    file_timeout_s: float,
    jobs: int,
    limit: int,
    progress: bool = True,
    independent_judging: bool = False,
    m2_arm: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """跑一个（工件, 臂）的全部任务并返回臂级结果（并行、确定性排序）。

    ``independent_judging=True``（N-3）：每任务改用生产 _m1_metrics 独立判读链，
    并额外产出 ``independent_judging`` 段（含与 M-2 基线逐任务对账）。
    """
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
            anchors=anchors,
            roots=roots,
            pytest_timeout_s=pytest_timeout_s,
            collect_timeout_s=collect_timeout_s,
            file_timeout_s=file_timeout_s,
            siblings_cache=siblings_cache,
            independent_judging=independent_judging,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        futures = {pool.submit(_one, row): row for row in work_rows}
        for future in concurrent.futures.as_completed(futures):
            task = future.result()
            tasks.append(task)
            done += 1
            if progress:
                counts = (task.get("oracle") or {}).get("counts") or {}
                print(
                    f"[oracle] {artifact_label}/{arm} {done}/{total} {task.get('task_id')}: "
                    f"{task.get('status')} inj={(task.get('injection') or {}).get('verdict')} "
                    f"correct={counts.get('correct', 0)} fp={counts.get('fp', 0)} "
                    f"silent={counts.get('silent', 0)} mis={counts.get('misguided', 0)}"
                    + (f" skip={task.get('skip_reason')}" if task.get("status") != "ok" else ""),
                    flush=True,
                )
    tasks.sort(key=lambda t: str(t.get("task_id") or ""))
    skip_reasons: Counter[str] = Counter(str(t.get("skip_reason")) for t in tasks if t.get("status") != "ok")
    arm_result: dict[str, Any] = {
        "artifact": artifact_label,
        "artifact_sha256": artifact_sha256,
        "arm": arm,
        "role": _arm_role(arm),
        "n_rows": len(rows),
        "n_tasks": len(tasks),
        "structural_skip_reasons": dict(sorted(skip_reasons.items())),
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
        "subsets": build_arm_subset_stats(tasks),
        "cross_check": build_cross_check(tasks),
        "tasks": tasks,
        "timing": {"wall_s": round(time.time() - started, 3)},
    }
    if independent_judging:
        arm_result["independent_judging"] = aggregate_independent(tasks, m2_arm, limited=limit > 0)
    return arm_result


def _arm_role(arm: str) -> str:
    """臂角色：处理臂 / 对照臂 / 其它（报告标注用）。"""
    if arm == "plain_llm_df_spec":
        return "treatment"
    if arm == "plain_llm_df":
        return "control"
    return "other"


def _rate_pair(arm_a: dict[str, Any], arm_b: dict[str, Any], path: tuple[str, ...]) -> dict[str, Any]:
    """两臂某标量对比（访问路径如 (subset, 'oracle', 'rates', 'correct')）。"""

    def _get(arm: dict[str, Any]) -> Any:
        cur: Any = arm
        for key in path:
            if not isinstance(cur, dict) or key not in cur:
                return None
            cur = cur[key]
        return cur

    value_a = _get(arm_a)
    value_b = _get(arm_b)
    delta = None
    if value_a is not None and value_b is not None:
        delta = round((float(value_b) - float(value_a)) * 100.0, 4)
    return {"arm_a": value_a, "arm_b": value_b, "delta_pp_b_minus_a": delta}


def build_comparison(arms: list[dict[str, Any]]) -> dict[str, Any] | None:
    """臂间描述性对比（N≥2 臂的无序臂对；不做显著性推断）。"""
    if len(arms) < 2:
        return None
    pairs: list[dict[str, Any]] = []
    for i in range(len(arms)):
        for j in range(i + 1, len(arms)):
            arm_a, arm_b = arms[i], arms[j]
            per_class: dict[str, Any] = {}
            for cls in ORACLE_CLASSES:
                per_class[f"{cls}_share"] = _rate_pair(
                    arm_a, arm_b, ("subsets", "defect_programs", "oracle", "rates", cls)
                )
            injection: dict[str, Any] = {
                key: _rate_pair(arm_a, arm_b, ("subsets", "defect_programs", "injection", key))
                for key in ("injection_rate_of_rows", "compiled_nonempty_rate_of_attempted")
            }
            detection: dict[str, Any] = {}
            for key in ("archived", "llm_only_replay", "oracle_augmented_replay"):
                detection[key] = _rate_pair(arm_a, arm_b, ("subsets", "defect_programs", "detection", key, "rate"))
            pairs.append(
                {
                    "arm_a": {"label": arm_a["arm"], "role": arm_a["role"], "artifact": arm_a["artifact"]},
                    "arm_b": {"label": arm_b["arm"], "role": arm_b["role"], "artifact": arm_b["artifact"]},
                    "oracle_class_shares_defect_programs": per_class,
                    "injection_defect_programs": injection,
                    "detection_rates_defect_programs": detection,
                }
            )
    return {
        "kind": "descriptive_pairwise",
        "arms": [
            {"label": arm["arm"], "role": arm["role"], "artifact": arm["artifact"], "sha256": arm["artifact_sha256"]}
            for arm in arms
        ],
        "pairs": pairs,
        "interpretation_disclaimer": (
            "描述性对比：delta_pp = 臂 B − 臂 A（百分点），不构成预注册确认性证据、"
            "无显著性/效应量推断；数值须结合分母披露与交叉校验表解读。"
            "oracle 质量反映确定性通道，不是 LLM 生成能力指标。"
        ),
    }


def load_oracle_quality_report(path: Path) -> dict[str, Any]:
    """加载任意 A-05 oracle 质量报告（O-1 before/after 对照的 before 侧）。

    Returns:
        {"path","sha256","body_digest","report"}。

    Raises:
        OracleQualityError: 缺失 / JSON 非法 / 结构不合法（fail-closed）。
    """
    if not path.is_file():
        raise OracleQualityError(f"对照基线报告不存在（--compare-report）: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise OracleQualityError(f"对照基线报告无法解析: {path}: {e}") from e
    report = payload.get("report") if isinstance(payload, dict) else None
    if not isinstance(report, dict) or not isinstance(report.get("arms"), list):
        raise OracleQualityError(f"对照基线报告结构不合法（缺 report.arms）: {path}")
    return {
        "path": _display_path(path),
        "sha256": sha256_file(path),
        "body_digest": (payload.get("run_meta") or {}).get("body_digest"),
        "report": report,
    }


def _baseline_oracle_breakdown(oracle: dict[str, Any]) -> dict[str, Any]:
    """从报告聚合的 oracle 段推导 before 侧 fp 细分（O-1 对照用）。

    M-2 工件没有 per-test fp_kind 字段；可由 failure_stats 推导：
    - ``fixed_side_failure_kinds.assertion`` = 断言型 fp；
    - ``fixed_side_exception_types`` 求和 = 仪器失效型 fp；
    - 差额 = 无归因（保守）。
    """
    counts = oracle.get("counts") or {}
    failure_stats = oracle.get("failure_stats") or {}
    fixed_kinds = failure_stats.get("fixed_side_failure_kinds") or {}
    fixed_exceptions = failure_stats.get("fixed_side_exception_types") or {}
    assertion = int(fixed_kinds.get("assertion", 0) or 0)
    instrument = sum(int(v or 0) for v in fixed_exceptions.values())
    fp_total = int(counts.get("fp", 0) or 0)
    unattributed = max(0, fp_total - assertion - instrument)
    return {
        "fp_assertion_fail": assertion,
        "instrument_error": instrument,
        "fp_unattributed": unattributed,
        "fp_total": fp_total,
        "fixed_side_exception_types": dict(sorted(fixed_exceptions.items())),
        "fixed_side_failure_kinds": dict(sorted(fixed_kinds.items())),
    }


def build_instrument_hardening_comparison(
    arms: list[dict[str, Any]],
    baseline: dict[str, Any],
) -> dict[str, Any]:
    """O-1 仪器加固 before/after 对照（同一 replay 工具口径；before = 基线工件）。

    诚实口径：这是**仪器治疗**对照，不是检出能力提升证据。加固后崩溃应从
    fp 变为 skipped/unavailable（不再被当假阳），断言型 fp 保留；correct 的
    语义质量不受影响（预期仍为 0）。
    """
    baseline_arms = {
        str(arm.get("arm")): arm for arm in (baseline.get("report") or {}).get("arms") or [] if isinstance(arm, dict)
    }
    rows: list[dict[str, Any]] = []
    for arm in arms:
        name = str(arm.get("arm"))
        current_oracle = ((arm.get("subsets") or {}).get("all_tasks") or {}).get("oracle") or {}
        baseline_arm = baseline_arms.get(name)
        if baseline_arm is None:
            rows.append({"arm": name, "before": None, "after": None, "delta": None, "note": "基线工件缺该臂"})
            continue
        before_oracle = ((baseline_arm.get("subsets") or {}).get("all_tasks") or {}).get("oracle") or {}
        before_counts = dict(before_oracle.get("counts") or {})
        after_counts = dict(current_oracle.get("counts") or {})
        before_breakdown = _baseline_oracle_breakdown(before_oracle)
        after_breakdown = dict(((current_oracle.get("counts_legacy_mapping") or {}).get("fp_breakdown")) or {})
        before_unclassifiable = dict(before_oracle.get("unclassifiable_counts") or {})
        after_unclassifiable = dict(current_oracle.get("unclassifiable_counts") or {})
        delta = {
            cls: int(after_counts.get(cls, 0) or 0) - int(before_counts.get(cls, 0) or 0) for cls in ORACLE_CLASSES
        }
        delta["classifiable"] = int(current_oracle.get("n_oracle_tests_classifiable") or 0) - int(
            before_oracle.get("n_oracle_tests_classifiable") or 0
        )
        delta["skipped"] = int(after_unclassifiable.get("skipped", 0) or 0) - int(
            before_unclassifiable.get("skipped", 0) or 0
        )
        rows.append(
            {
                "arm": name,
                "before": {
                    "n_oracle_tests_classifiable": int(before_oracle.get("n_oracle_tests_classifiable") or 0),
                    "counts": before_counts,
                    "fp_breakdown": before_breakdown,
                    "unclassifiable_counts": before_unclassifiable,
                    "failure_stats": before_oracle.get("failure_stats") or {},
                },
                "after": {
                    "n_oracle_tests_classifiable": int(current_oracle.get("n_oracle_tests_classifiable") or 0),
                    "counts": after_counts,
                    "fp_breakdown": after_breakdown,
                    "skipped_count": int(after_unclassifiable.get("skipped", 0) or 0),
                    "skip_reason_counts": current_oracle.get("skip_reason_counts") or {},
                    "unclassifiable_counts": after_unclassifiable,
                    "failure_stats": current_oracle.get("failure_stats") or {},
                },
                "delta": delta,
            }
        )
    return {
        "kind": "instrument_hardening_before_after",
        "baseline": {
            "path": baseline.get("path"),
            "sha256": baseline.get("sha256"),
            "body_digest": baseline.get("body_digest"),
        },
        "caliber": (
            "同一 experiments/oracle_quality_replay.py 混合重放口径（LLM-only 重放 + oracle-augmented 混判）；"
            "before 取基线工件聚合、after 为本次加固后重放聚合；分母 = 可分类 oracle 测试数"
            "（加固后 skipped/不可分类单列、不进分母）"
        ),
        "arms": rows,
        "expected_mapping": (
            "before 的 fp = fp_assertion_fail（断言型，保留）+ instrument_error（崩溃型；"
            "加固后应转为 skipped/unavailable，由 unclassifiable_counts.skipped 与 "
            "skip_reason_counts 观测）"
        ),
        "honesty_note": (
            "**仪器治疗 ≠ 检出能力提升**：加固只改变「崩溃如何被记账」（fp → skipped/unavailable），"
            "不改变 oracle 断言语义；correct 的语义质量预期不变（仍为 0，需质量治理另立项）。"
            "加固后可分类分母变小，引用占比必须同时给出 skipped 数与分母。"
        ),
    }


def _m1_oracle_suite_verdict_domain() -> tuple[str, ...]:
    """oracle-suite verdict 取值域（单一事实源 = experiments/_m1_metrics.py）。"""
    from experiments._m1_metrics import ORACLE_SUITE_VERDICTS

    return tuple(ORACLE_SUITE_VERDICTS)


def build_report(
    *,
    artifact_entries: list[dict[str, Any]],
    anchor_info: dict[str, Any],
    arms: list[dict[str, Any]],
    config: dict[str, Any],
    command: list[str],
    independent_judging: bool = False,
    m2_info: dict[str, Any] | None = None,
    instrument_comparison: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """组装确定性报告 body（不含时间戳/墙钟；这些只进 run_meta）。

    ``independent_judging=True``（N-3）：body 顶层加 ``mode`` 与
    ``independent_judging`` 段（M-2 基线输入 sha256、逐臂对账口径说明）。
    """
    body: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION if not independent_judging else INDEPENDENT_SCHEMA_VERSION,
        "mode": "independent_judging" if independent_judging else "mixed_replay",
        "tool": {"name": TOOL_NAME, "version": TOOL_VERSION},
        "metric_definition": {
            "name": "A-05 确定性规约 oracle 质量度量（零 LLM 重放）",
            "injection_path": (
                "生产函数 src.graph.nodes._append_spec_oracle_to_test_with_verdict 原样调用；"
                "state 由锚表重建（test_plan={function_name, logic_analysis}、target_function、"
                "module_name=task_id 末段、target_code=缺陷版源码；不写现场 spec_ir/boundary_triplets）"
            ),
            "oracle_test_markers": list(ORACLE_TEST_MARKERS),
            "classes": dict(ORACLE_CLASS_DEFINITIONS),
            "unclassifiable_reasons": list(mm.UNCLASSIFIABLE_REASONS),
            "denominator": (
                "四分类占比分母 = 可分类 oracle 测试数（buggy/fixed 两侧均有 pass/fail 结果）；"
                "timeout/collect_error/import_error/syntax_error/skipped/test_error/missing_side/unknown "
                "单列、不进分母；任务级结构跳过单独计数，不混入可判定集合"
            ),
            "detection_definition": (
                "任务级二值：buggy 侧 pytest 非零退出 ∧ fixed 侧为 0 ∧ 两侧无执行错误"
                "（与 experiments/_m1_metrics.py 的 M1 detection 口径同源，沿用 T2 工具实现）；"
                "oracle 检出贡献 = oracle-augmented 重放 detection − LLM-only 重放 detection（同任务配对）"
            ),
            "archive_cross_check": (
                "0 mismatch：① LLM-only 重放 detection vs 归档 detection_rate 两侧均可判时必须一致；"
                "② 归档 spec_oracle_verdict 用『归档 state 语义』重放生产注入口必须一致；"
                "差异逐条归因，不静默"
            ),
            "evidence_status": (
                "描述性机制度量（A-05/G6 缺口补齐）；非预注册确认性证据，无显著性推断；"
                "oracle 质量反映确定性规约通道，不是 LLM 生成能力指标"
            ),
            "external_reference_note": (
                "独立评审 A-05 引用 Tratto 73% / TOGLL 63%（ISSTA'25/arXiv'24）作为缺口参照；"
                "本工具与其数据集/口径/语言不同，不横向引用为对比数字"
            ),
        },
        "config": config,
        "command": command,
        "inputs": artifact_entries,
        "anchor_table": anchor_info,
        "arms": arms,
        "comparison": build_comparison(arms),
        "instrument_hardening_comparison": instrument_comparison,
        "independent_judging": (
            {
                "m2_baseline": m2_info,
                "caliber": (
                    "生产独立判读链：_m1_metrics LLM-suite detection（-k 排除 "
                    "test_specir_v2_oracle / test_specir_v2_smt_witness）+ oracle-suite "
                    "verdict（-k 只选 oracle 测试名）；state 只带 spec_anchor（复刻生产 "
                    "df_spec 类臂，同时验证 N-3 接线修复）；M1_PER_TEST_TIMEOUT 与 M-2 重放"
                    "对齐为 1s"
                ),
                "requirement": (
                    "LLM-suite detection 逐任务与 M-2 基线 0 mismatch，且 40 口径 pooled "
                    "计数与 M-2 完全一致（df_spec 20/40=50.00%、df 31/40=77.50%）"
                ),
                "oracle_suite_verdict_domain": list(_m1_oracle_suite_verdict_domain()),
            }
            if independent_judging
            else None
        ),
        "limitations": [
            "反事实注入口径：锚表材料直接重建 test_plan（无 Planner 现场 spec_ir / boundary_triplets），"
            "不声称等同完整 logic 链路生产注入质量",
            "归档批次（plain_llm_df*，Planner 关闭）生产注入口未实际尝试注入；本报告质量数字来自零 LLM 重放",
            "oracle 与 LLM 测试同文件、同 pytest session 执行（生产口径），全局状态污染与收集顺序照旧",
            "官方金测试 test_cases 不参与本分类，仅用于任务级 detection 交叉校验口径说明",
            "9 个 QuixBugs *_test 驱动任务（相对 import、无金测试）与辅助模块 node 在平铺执行口径下"
            "结构性不可 replay → 结构跳过单列；41 口径兼容行（node，buggy==fixed）无缺陷信号，主分析集为 40 口径",
            "per-test timeout 把挂死 oracle 测试记为不可分类 timeout（不并入四分类），与 M1 判分口径有意不同",
            "oracle 假阳/误导若因编译器提供的 0 字面量绑定导致（如 TypeError），属确定性通道自身缺陷，"
            "由 failure_stats.fixed_side_exception_types 逐类披露，不在本工具内修复",
            "描述性对比，不提供显著性推断；两臂差异仅作机制侧方向参考",
            *(
                [
                    "独立判读模式的 M1 判分使用生产 _m1_metrics（M1_PER_TEST_TIMEOUT=1s 对齐 M-2 重放）；"
                    "与 M-2 基线差异逐条归因，未静默平均",
                    "oracle-suite verdict 每任务单值（correct/fp/silent/misguided/unavailable），"
                    "与 M-2 逐测试四分类的类别差异属预期可比对项（描述性）",
                ]
                if independent_judging
                else []
            ),
        ],
    }
    return body


# ─── Markdown / README 渲染 ────────────────────────────────────────────────
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


def _render_comparison_rows(comparison: dict[str, Any]) -> list[tuple[str, str, str]]:
    """把 before/after 对照渲染为 (指标, before, after) 行（Markdown 共用）。"""
    rows: list[tuple[str, str, str]] = []
    for arm_row in comparison.get("arms") or []:
        before = arm_row.get("before") or {}
        after = arm_row.get("after") or {}
        before_counts = before.get("counts") or {}
        after_counts = after.get("counts") or {}
        before_break = before.get("fp_breakdown") or {}
        after_break = after.get("fp_breakdown") or {}
        before_skip = int((before.get("unclassifiable_counts") or {}).get("skipped", 0) or 0)
        after_skip = int(after.get("skipped_count", 0) or 0)
        rows.append(
            (
                f"`{arm_row.get('arm')}` 可分类 oracle 测试数",
                str(before.get("n_oracle_tests_classifiable")),
                str(after.get("n_oracle_tests_classifiable")),
            )
        )
        rows.extend(
            (
                f"`{arm_row.get('arm')}` `{cls}`",
                str(int(before_counts.get(cls, 0) or 0)),
                str(int(after_counts.get(cls, 0) or 0)),
            )
            for cls in ORACLE_CLASSES
        )
        rows.append(
            (
                f"`{arm_row.get('arm')}` `fp_assertion_fail`（断言型假阳，保留）",
                str(int(before_break.get("fp_assertion_fail", 0) or 0)),
                str(int(after_break.get("fp_assertion_fail", 0) or 0)),
            )
        )
        rows.append(
            (
                f"`{arm_row.get('arm')}` `instrument_error`（崩溃型假阳，拆出）",
                str(int(before_break.get("instrument_error", 0) or 0)),
                str(int(after_break.get("instrument_error", 0) or 0)),
            )
        )
        rows.append(
            (
                f"`{arm_row.get('arm')}` `skipped`（仪器不可用单列，不进分母）",
                str(before_skip),
                str(after_skip),
            )
        )
    return rows


def render_markdown(report: dict[str, Any], run_meta: dict[str, Any]) -> str:
    """渲染 Markdown 报告（确定性；时间戳/墙钟只从 run_meta 读）。"""
    lines: list[str] = []
    add = lines.append
    add("# A-05 确定性规约 oracle 质量度量报告（零 LLM 重放）")
    add("")
    add("> **性质**：描述性机制度量（A-05/G6 缺口补齐），**非**预注册确认性证据；")
    add("> oracle 质量反映确定性规约通道，**不是 LLM 生成能力指标**；不做显著性推断。")
    add(f"> **生成时间**：{run_meta.get('generated_at')}　**body digest**：`{run_meta.get('body_digest')}`")
    add(f"> **工具**：{report['tool']['name']} v{report['tool']['version']}　**schema**：`{report['schema_version']}`")
    add("")
    add("复算命令：")
    add("")
    add("```bash")
    add(" ".join(str(x) for x in report.get("command") or []))
    add("```")
    add("")
    add("## 1. 输入与锚表")
    add("")
    add("| 工件 | sha256 | 臂 | 行数 |")
    add("|---|---|---|---|")
    for entry in report.get("inputs") or []:
        for arm in entry.get("arms") or []:
            add(f"| `{entry['path']}` | `{entry['sha256']}` | `{arm['arm']}` | {arm['n_rows']} |")
    anchor = report.get("anchor_table") or {}
    add("")
    add(
        f"锚表：`{anchor.get('path')}`　sha256=`{anchor.get('sha256')}`"
        f"　校验来源=`{anchor.get('expected_sha256_source')}`"
    )
    meta = anchor.get("meta") or {}
    add(
        f"锚表规模：{anchor.get('n_anchors')} 条锚；构建器 `{meta.get('generated_by', '—')}`；"
        f"缓存扫描 {meta.get('scanned_files', '—')} / Planner 条目 {meta.get('planner_entries', '—')}"
    )
    add("")
    add("## 2. 口径定义")
    add("")
    add("| oracle 类别 | 定义 |")
    add("|---|---|")
    for cls, definition in (report["metric_definition"]["classes"] or {}).items():
        add(f"| `{cls}` | {definition} |")
    add("")
    add("> 分母纪律：" + report["metric_definition"]["denominator"])
    add("")
    add("> 注入路径：" + report["metric_definition"]["injection_path"])
    add("")
    add("> 交叉校验：" + report["metric_definition"]["archive_cross_check"])
    add("")
    add("## 3. 注入统计")
    add("")
    add("| 指标 | " + " | ".join(f"`{arm['arm']}`" for arm in report["arms"]) + " |")
    add("|---|" + "---|" * len(report["arms"]))
    injection_rows = [
        ("任务行数", lambda a: a["subsets"]["all_tasks"]["injection"]["n_task_rows"]),
        ("锚命中数", lambda a: a["subsets"]["all_tasks"]["injection"]["n_anchor_hit"]),
        ("尝试注入任务数", lambda a: a["subsets"]["all_tasks"]["injection"]["n_attempted"]),
        ("注入成功任务数", lambda a: a["subsets"]["all_tasks"]["injection"]["n_injected"]),
        ("编译产物为空任务数", lambda a: a["subsets"]["all_tasks"]["injection"]["n_compiled_empty"]),
        (
            "注入率（占任务行）",
            lambda a: _fmt_rate(a["subsets"]["all_tasks"]["injection"]["injection_rate_of_rows"]),
        ),
        (
            "编译产物非空率（占尝试）",
            lambda a: _fmt_rate(a["subsets"]["all_tasks"]["injection"]["compiled_nonempty_rate_of_attempted"]),
        ),
        ("可测 oracle 任务数", lambda a: a["subsets"]["all_tasks"]["injection"]["n_tasks_with_measurable_oracle"]),
    ]
    for label, getter in injection_rows:
        add(f"| {label} | " + " | ".join(str(getter(arm)) for arm in report["arms"]) + " |")
    add("")
    add("各臂注入 verdict 分布：")
    add("")
    for arm in report["arms"]:
        counts = arm["subsets"]["all_tasks"]["injection"]["verdict_counts"]
        text = "、".join(f"`{k}`={v}" for k, v in counts.items())
        add(f"- `{arm['arm']}`：{text or '无'}")
    add("")
    add("## 4. oracle 四分类（分母 = 可分类 oracle 测试数）")
    add("")
    md_subsets = (
        ("defect_programs", "40 缺陷程序主分析集（非 *_test 且 buggy≠fixed）"),
        ("all_tasks", "全量任务行"),
        ("injected_measurable", "可测注入任务"),
    )
    for subset_index, (subset, label) in enumerate(md_subsets, start=1):
        add(f"### 4.{subset_index} {label}")
        add("")
        add("| 指标 | " + " | ".join(f"`{arm['arm']}`" for arm in report["arms"]) + " |")
        add("|---|" + "---|" * len(report["arms"]))
        add(
            "| 可测任务数 | "
            + " | ".join(str(arm["subsets"][subset]["oracle"]["n_tasks_measured"]) for arm in report["arms"])
            + " |"
        )
        add(
            "| 可分类 oracle 测试数（分母） | "
            + " | ".join(str(arm["subsets"][subset]["oracle"]["n_oracle_tests_classifiable"]) for arm in report["arms"])
            + " |"
        )
        for cls in ORACLE_CLASSES:
            add(
                f"| `{cls}` 计数 / 占比 | "
                + " | ".join(
                    f"{arm['subsets'][subset]['oracle']['counts'][cls]} / "
                    f"{_fmt_rate(arm['subsets'][subset]['oracle']['rates'][cls])}"
                    for arm in report["arms"]
                )
                + " |"
            )
        add(
            "| 含 `correct` 的任务数 | "
            + " | ".join(
                str(arm["subsets"][subset]["oracle"]["n_tasks_with_class"]["correct"]) for arm in report["arms"]
            )
            + " |"
        )
        add(
            "| 含 `fp` 的任务数 | "
            + " | ".join(str(arm["subsets"][subset]["oracle"]["n_tasks_with_class"]["fp"]) for arm in report["arms"])
            + " |"
        )
        add(
            "| 每任务 oracle 测试数（mean/median） | "
            + " | ".join(
                " / ".join(
                    _fmt(x)
                    for x in (
                        arm["subsets"][subset]["oracle"]["per_task_oracle_tests"]["mean"],
                        arm["subsets"][subset]["oracle"]["per_task_oracle_tests"]["median"],
                    )
                )
                for arm in report["arms"]
            )
            + " |"
        )
        add("")
    add("### 4.4 不可分类原因与失败类型（诊断）")
    add("")
    add("| 项 | " + " | ".join(f"`{arm['arm']}`" for arm in report["arms"]) + " |")
    add("|---|" + "---|" * len(report["arms"]))
    reasons = sorted(
        {
            r
            for arm in report["arms"]
            for r in (arm["subsets"]["defect_programs"]["oracle"]["unclassifiable_counts"] or {})
        }
    )
    for reason in reasons:
        add(
            f"| 不可分类 `{reason}` | "
            + " | ".join(
                str(arm["subsets"]["defect_programs"]["oracle"]["unclassifiable_counts"].get(reason, 0))
                for arm in report["arms"]
            )
            + " |"
        )
    for kind in ("assertion", "exception", "timeout", "other"):
        add(
            f"| fixed 侧失败类型 `{kind}` | "
            + " | ".join(
                str(
                    (
                        arm["subsets"]["defect_programs"]["oracle"]["failure_stats"]["fixed_side_failure_kinds"] or {}
                    ).get(kind, 0)
                )
                for arm in report["arms"]
            )
            + " |"
        )
    add("")
    exceptions = sorted(
        {
            exc
            for arm in report["arms"]
            for exc in (
                arm["subsets"]["defect_programs"]["oracle"]["failure_stats"]["fixed_side_exception_types"] or {}
            )
        }
    )
    if exceptions:
        add("fixed 侧失败异常类型分布（假阳根因诊断）：")
        add("")
        add("| 异常类型 | " + " | ".join(f"`{arm['arm']}`" for arm in report["arms"]) + " |")
        add("|---|" + "---|" * len(report["arms"]))
        for exc in exceptions:
            add(
                f"| `{exc}` | "
                + " | ".join(
                    str(
                        (
                            arm["subsets"]["defect_programs"]["oracle"]["failure_stats"]["fixed_side_exception_types"]
                            or {}
                        ).get(exc, 0)
                    )
                    for arm in report["arms"]
                )
                + " |"
            )
        add("")
    add("## 5. 注入任务检出贡献（任务级，M1 detection 口径）")
    add("")
    add("| 指标（40 缺陷程序口径） | " + " | ".join(f"`{arm['arm']}`" for arm in report["arms"]) + " |")
    add("|---|" + "---|" * len(report["arms"]))
    for key, label in (
        ("archived", "归档 detection（LLM-only）"),
        ("llm_only_replay", "LLM-only 重放 detection"),
        ("oracle_augmented_replay", "oracle-augmented 重放 detection"),
    ):
        add(
            f"| {label} | "
            + " | ".join(
                f"{arm['subsets']['defect_programs']['detection'][key]['n_detected']}"
                f" / {arm['subsets']['defect_programs']['detection'][key]['n_denominator']}"
                f" = {_fmt_rate(arm['subsets']['defect_programs']['detection'][key]['rate'])}"
                for arm in report["arms"]
            )
            + " |"
        )
    add(
        "| Δ augmented − llm_only（配对，pp） | "
        + " | ".join(
            _fmt(arm["subsets"]["defect_programs"]["detection"]["paired_augmented_vs_llm_only"]["delta_pp_b_minus_a"])
            for arm in report["arms"]
        )
        + " |"
    )
    add(
        "| 配对 LLM-only 重放 vs 归档（n_paired / n_changed） | "
        + " | ".join(
            f"{arm['subsets']['defect_programs']['detection']['paired_llm_only_vs_archived']['n_paired']}"
            f" / {arm['subsets']['defect_programs']['detection']['paired_llm_only_vs_archived']['n_changed']}"
            for arm in report["arms"]
        )
        + " |"
    )
    add("")
    add("转移表（任务级 0/1，LLM-only → oracle-augmented）：")
    add("")
    add("| 转移 | " + " | ".join(f"`{arm['arm']}`" for arm in report["arms"]) + " |")
    add("|---|" + "---|" * len(report["arms"]))
    transitions = sorted(
        {
            k
            for arm in report["arms"]
            for k in (arm["subsets"]["defect_programs"]["detection"]["transition_counts"] or {})
        }
    )
    for transition in transitions:
        add(
            f"| `{transition}` | "
            + " | ".join(
                str(arm["subsets"]["defect_programs"]["detection"]["transition_counts"].get(transition, 0))
                for arm in report["arms"]
            )
            + " |"
        )
    add("")
    for arm in report["arms"]:
        det = arm["subsets"]["defect_programs"]["detection"]
        if det["added_tasks"]:
            add(f"`{arm['arm']}` 新增检出任务（oracle 使其由 0→1，共 {len(det['added_tasks'])}）：")
            add("")
            for item in det["added_tasks"]:
                counts = item.get("oracle_counts") or {}
                add(f"- `{item['task_id']}`：oracle correct={counts.get('correct', 0)} fp={counts.get('fp', 0)}")
            add("")
        if det["lost_tasks"]:
            add(f"`{arm['arm']}` 检出损失任务（oracle 假阳使 fixed 转红，共 {len(det['lost_tasks'])}）：")
            add("")
            for item in det["lost_tasks"]:
                counts = item.get("oracle_counts") or {}
                add(
                    f"- `{item['task_id']}`：oracle fp={counts.get('fp', 0)} misguided={counts.get('misguided', 0)}"
                    f" fixed 侧失败类型={item.get('fixed_side_failure_kinds') or {}}"
                )
            add("")
    add("## 6. 交叉校验（0 mismatch 要求）")
    add("")
    add("| 对账项 | " + " | ".join(f"`{arm['arm']}`" for arm in report["arms"]) + " |")
    add("|---|" + "---|" * len(report["arms"]))
    det_keys = sorted(
        {k for arm in report["arms"] for k in (arm["cross_check"]["detection_vs_archive"]["agreement_counts"] or {})}
    )
    for key in det_keys:
        add(
            f"| detection 对账 `{key}` | "
            + " | ".join(
                str(arm["cross_check"]["detection_vs_archive"]["agreement_counts"].get(key, 0))
                for arm in report["arms"]
            )
            + " |"
        )
    v_keys = sorted(
        {
            k
            for arm in report["arms"]
            for k in (arm["cross_check"]["oracle_verdict_vs_archive"]["agreement_counts"] or {})
        }
    )
    for key in v_keys:
        add(
            f"| oracle verdict 对账 `{key}` | "
            + " | ".join(
                str(arm["cross_check"]["oracle_verdict_vs_archive"]["agreement_counts"].get(key, 0))
                for arm in report["arms"]
            )
            + " |"
        )
    add(
        "| 归档字段自洽性违规 | "
        + " | ".join(str(len(arm["cross_check"]["archive_field_consistency_violations"])) for arm in report["arms"])
        + " |"
    )
    add(
        "| **all_ok（0 mismatch）** | "
        + " | ".join(f"**{arm['cross_check']['all_ok']}**" for arm in report["arms"])
        + " |"
    )
    add("")
    for arm in report["arms"]:
        cc = arm["cross_check"]
        diff_items = cc["detection_vs_archive"]["mismatch_or_attributed_nonmatch"]
        if diff_items:
            add(f"**`{arm['arm']}` detection 对账差异/非匹配（{len(diff_items)} 条，逐条归因）**：")
            add("")
            add("| task_id | 归档 | 重放 | 重放(strict) | 标签 | 归因 |")
            add("|---|---|---|---|---|---|")
            for item in diff_items:
                add(
                    f"| `{item['task_id']}` | {_fmt(item['artifact_detection_rate'])} | "
                    f"{_fmt(item['replay_detection'])} | {_fmt(item['replay_detection_strict'])} | "
                    f"{item['agreement']} | {item['reason']} |"
                )
            add("")
        if cc["oracle_verdict_vs_archive"]["mismatches"]:
            add(
                f"**`{arm['arm']}` oracle verdict 对账差异（{len(cc['oracle_verdict_vs_archive']['mismatches'])} 条）**："
            )
            add("")
            for item in cc["oracle_verdict_vs_archive"]["mismatches"]:
                add(f"- `{item['task_id']}`：{item['reason']}")
            add("")
        if cc["archive_field_consistency_violations"]:
            add(f"**`{arm['arm']}` 归档字段自洽性违规（{len(cc['archive_field_consistency_violations'])} 条）**：")
            add("")
            for item in cc["archive_field_consistency_violations"]:
                add(f"- `{item['task_id']}`：{item['detail']}")
            add("")
    comparison = report.get("comparison")
    if comparison:
        add("## 7. 臂间描述性对比（oracle 质量与检出贡献）")
        add("")
        for pair in comparison.get("pairs") or []:
            label_a = pair["arm_a"]["label"]
            label_b = pair["arm_b"]["label"]
            add(f"**{label_a} → {label_b}**（`delta_pp` = B − A，百分点；40 缺陷程序口径）：")
            add("")
            add(f"| 指标 | `{label_a}` | `{label_b}` | delta_pp |")
            add("|---|---|---|---|")
            for cls in ORACLE_CLASSES:
                entry = pair["oracle_class_shares_defect_programs"].get(f"{cls}_share") or {}
                add(
                    f"| `{cls}_share` | {_fmt_rate(entry.get('arm_a'))} | {_fmt_rate(entry.get('arm_b'))} | "
                    f"{_fmt(entry.get('delta_pp_b_minus_a'))} |"
                )
            for key in ("injection_rate_of_rows", "compiled_nonempty_rate_of_attempted"):
                entry = pair["injection_defect_programs"].get(key) or {}
                add(
                    f"| `{key}` | {_fmt_rate(entry.get('arm_a'))} | {_fmt_rate(entry.get('arm_b'))} | "
                    f"{_fmt(entry.get('delta_pp_b_minus_a'))} |"
                )
            for key in ("archived", "llm_only_replay", "oracle_augmented_replay"):
                entry = pair["detection_rates_defect_programs"].get(key) or {}
                add(
                    f"| `{key}_rate` | {_fmt_rate(entry.get('arm_a'))} | {_fmt_rate(entry.get('arm_b'))} | "
                    f"{_fmt(entry.get('delta_pp_b_minus_a'))} |"
                )
            add("")
        add("> " + comparison["interpretation_disclaimer"])
        add("")
    add("## 8. 结构跳过 / oracle 未测量任务（不静默跳过）")
    add("")
    for arm in report["arms"]:
        skips = arm.get("structural_skips") or []
        add(f"**`{arm['arm']}`（{len(skips)} 个）**：")
        add("")
        if not skips:
            add("- 无")
        for item in skips:
            add(f"- `{item['task_id']}` [{item['analysis_set']}] `{item['reason']}`: {str(item['detail'])[:240]}")
        add("")
    add("### 8.1 oracle 未测量原因（注入未成功 / 增强重放不可分类）")
    add("")
    for arm in report["arms"]:
        unmeasured: dict[str, int] = {}
        n_measurable = 0
        for task in arm.get("tasks") or []:
            oracle = task.get("oracle") or {}
            if oracle.get("status") == "ok":
                n_measurable += 1
                continue
            reason = str(oracle.get("skip_reason") or "unknown")
            unmeasured[reason] = unmeasured.get(reason, 0) + 1
        add(f"**`{arm['arm']}`（可测 {n_measurable} / 未测量 {sum(unmeasured.values())}）**：")
        add("")
        if not unmeasured:
            add("- 无")
        for reason, count in sorted(unmeasured.items()):
            add(f"- `{reason}`：{count}")
        add("")
    add("> 未测量任务不进四分类分母；上述原因与注入 verdict 分布（§3）一并披露。")
    add("")
    add("## 9. 逐任务明细")
    add("")
    for arm in report["arms"]:
        add(f"### `{arm['arm']}`")
        add("")
        add(
            "| task_id | 状态 | 注入 | oracle测试 | correct | fp | silent | mis | 不可分类 | "
            "归档det | LLM重放det | 增强重放det | 转移 | 归档verdict对账 |"
        )
        add("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for task in arm["tasks"]:
            oracle = task.get("oracle") or {}
            counts = oracle.get("counts") or {}
            unc = sum((oracle.get("unclassifiable") or {}).values())
            det = task.get("detection") or {}
            add(
                f"| `{task['task_id']}` | {task['status']}"
                + (f" ({task['skip_reason']})" if task["status"] != "ok" else "")
                + f" | {(task.get('injection') or {}).get('verdict')}"
                f" | {oracle.get('n_oracle_nodes', 0)} | {counts.get('correct', 0)} | {counts.get('fp', 0)}"
                f" | {counts.get('silent', 0)} | {counts.get('misguided', 0)} | {unc}"
                f" | {_fmt(det.get('archived'))} | {_fmt(det.get('llm_only_replay'))}"
                f" | {_fmt(det.get('augmented_replay'))} | {det.get('transition')}"
                f" | {(task.get('archived_check') or {}).get('verdict_agreement')} |"
            )
        add("")
    comparison_hardening = report.get("instrument_hardening_comparison")
    if comparison_hardening:
        add("## 10. O-1 仪器加固前后对照（before/after）")
        add("")
        baseline = comparison_hardening.get("baseline") or {}
        add(
            f"> 对照基线：`{baseline.get('path')}`（sha256 `{baseline.get('sha256')}`）。"
            "**这是仪器治疗对照，不是检出能力提升证据**——加固后崩溃由 fp 转为 "
            "skipped/unavailable，断言语义不变。"
        )
        add("")
        add("| 指标 | before | after |")
        add("|---|---|---|")
        for label, before, after in _render_comparison_rows(comparison_hardening):
            add(f"| {label} | {before} | {after} |")
        add("")
        skip_reasons = sorted(
            {
                reason
                for arm_row in comparison_hardening.get("arms") or []
                for reason in ((arm_row.get("after") or {}).get("skip_reason_counts") or {})
            }
        )
        if skip_reasons:
            add("after 侧仪器不可用 skip 原因分布：")
            add("")
            add(
                "| skip 原因 | "
                + " | ".join(f"`{a.get('arm')}`" for a in comparison_hardening.get("arms") or [])
                + " |"
            )
            add("|---|" + "---|" * len(comparison_hardening.get("arms") or []))
            for reason in skip_reasons:
                add(
                    f"| `{reason}` | "
                    + " | ".join(
                        str(((arm_row.get("after") or {}).get("skip_reason_counts") or {}).get(reason, 0))
                        for arm_row in comparison_hardening.get("arms") or []
                    )
                    + " |"
                )
            add("")
        add("> " + str(comparison_hardening.get("expected_mapping") or ""))
        add("")
        add("> " + str(comparison_hardening.get("honesty_note") or ""))
        add("")
    add("## 10. 确定性声明")
    add("")
    determinism = run_meta.get("determinism") or {}
    add(f"- 报告 body 不含时间戳/墙钟；body digest = `{run_meta.get('body_digest')}`。")
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
    add("## 11. 已知限制")
    add("")
    for item in report.get("limitations") or []:
        add(f"- {item}")
    add("")
    return "\n".join(lines) + "\n"


def render_readme(report: dict[str, Any], run_meta: dict[str, Any]) -> str:
    """渲染工件 README（输入 sha256 / 命令 / 分母 / 限制 / 墙钟）。"""
    lines: list[str] = []
    add = lines.append
    add("# A-05 oracle 质量度量工件（emse_oracle_quality_20261017）")
    add("")
    add("> **性质**：M 轮 T7-A（独立评审 §10 A-05 / G6 / D-4）零 LLM 重放的**描述性**")
    add("> 机制度量工件。oracle 质量反映确定性规约通道，**不是 LLM 生成能力指标**；")
    add("> 非预注册确认性证据，不做显著性推断。")
    add("")
    add("## 1. 输入 sha256（只读消费）")
    add("")
    add("| 输入 | sha256 |")
    add("|---|---|")
    for entry in report.get("inputs") or []:
        add(f"| `{entry['path']}` | `{entry['sha256']}` |")
    anchor = report.get("anchor_table") or {}
    add(
        f"| `{anchor.get('path')}` | `{anchor.get('sha256')}`（SHA256SUMS 校验：`{anchor.get('expected_sha256_source')}`） |"
    )
    add("")
    add(
        "> 以上输入工件哈希同时以 `../` 相对路径引用行记入同目录 `SHA256SUMS`"
        "（`scripts/gates/checksum_results.py --verify` 一并校验；文件内路径条目仅覆盖本目录工件）。"
    )
    add("")
    add("## 2. 复算命令")
    add("")
    add("```bash")
    add(" ".join(str(x) for x in report.get("command") or []))
    add("```")
    add("")
    add("## 3. 覆盖与分母")
    add("")
    for arm in report.get("arms") or []:
        injection = arm["subsets"]["all_tasks"]["injection"]
        oracle = arm["subsets"]["all_tasks"]["oracle"]
        add(
            f"- `{arm['arm']}`（{arm['role']}）：任务行 {injection['n_task_rows']}，锚命中 {injection['n_anchor_hit']}，"
            f"注入成功 {injection['n_injected']}，可测 oracle 任务 {injection['n_tasks_with_measurable_oracle']}，"
            f"可分类 oracle 测试（分母）{oracle['n_oracle_tests_classifiable']}，"
            f"不可分类 {oracle['n_oracle_tests_unclassifiable']}"
        )
    add("")
    add("> 四分类占比分母 = 可分类 oracle 测试数（buggy/fixed 两侧均有 pass/fail）；")
    add("> timeout/collect/import/syntax/skipped/test_error/missing_side 单列、不进分母。")
    add("")
    add("## 4. 核心数字（40 缺陷程序口径）")
    add("")
    add("| 指标 | " + " | ".join(f"`{arm['arm']}`" for arm in report.get("arms") or []) + " |")
    add("|---|" + "---|" * len(report.get("arms") or []))
    for cls in ORACLE_CLASSES:
        add(
            f"| `{cls}` 计数/占比 | "
            + " | ".join(
                f"{arm['subsets']['defect_programs']['oracle']['counts'][cls]} / "
                f"{_fmt_rate(arm['subsets']['defect_programs']['oracle']['rates'][cls])}"
                for arm in report.get("arms") or []
            )
            + " |"
        )
    for key in ("archived", "llm_only_replay", "oracle_augmented_replay"):
        add(
            f"| detection `{key}` | "
            + " | ".join(
                _fmt_rate(arm["subsets"]["defect_programs"]["detection"][key]["rate"])
                for arm in report.get("arms") or []
            )
            + " |"
        )
    add(
        "| Δ augmented − llm_only（配对 pp） | "
        + " | ".join(
            _fmt(arm["subsets"]["defect_programs"]["detection"]["paired_augmented_vs_llm_only"]["delta_pp_b_minus_a"])
            for arm in report.get("arms") or []
        )
        + " |"
    )
    add("")
    add("## 5. 交叉校验（0 mismatch 要求）")
    add("")
    for arm in report.get("arms") or []:
        cc = arm["cross_check"]
        det_counts = cc["detection_vs_archive"]["agreement_counts"]
        add(
            f"- `{arm['arm']}`：detection 对账 {det_counts}（mismatch="
            f"{cc['detection_vs_archive']['n_mismatch']}）；归档 oracle verdict 复现 "
            f"{cc['oracle_verdict_vs_archive']['agreement_counts']}（mismatch="
            f"{cc['oracle_verdict_vs_archive']['n_mismatch']}）；归档字段自洽性违规 "
            f"{len(cc['archive_field_consistency_violations'])}；**all_ok={cc['all_ok']}**"
        )
    add("")
    add("## 6. 确定性 / 墙钟")
    add("")
    determinism = run_meta.get("determinism") or {}
    add(f"- body digest：`{run_meta.get('body_digest')}`")
    add(
        f"- repeat={determinism.get('repeat')}；deterministic={determinism.get('deterministic')}；"
        f"各次 digest={determinism.get('body_digests')}"
    )
    add(f"- 本次重放墙钟：{run_meta.get('tool_wall_s')} s（只进 run_meta，不进 body digest）")
    add("- **确定性口径**：A-05 repeat=1（单测锁 body 结构；窗口结束后可选补 repeat=2）；A-11 repeat=2 逐位一致。")
    add("")
    comparison_hardening = report.get("instrument_hardening_comparison")
    if comparison_hardening:
        add("## 7. O-1 仪器加固前后对照（before/after）")
        add("")
        baseline = comparison_hardening.get("baseline") or {}
        add(
            f"> 对照基线：`{baseline.get('path')}`（sha256 `{baseline.get('sha256')}`）。"
            "**仪器治疗 ≠ 检出能力提升**：加固只改变崩溃的记账方式（fp → skipped/unavailable），"
            "oracle 断言语义与 correct 语义质量不变。"
        )
        add("")
        add("| 指标 | before | after |")
        add("|---|---|---|")
        for label, before, after in _render_comparison_rows(comparison_hardening):
            add(f"| {label} | {before} | {after} |")
        add("")
        add("> " + str(comparison_hardening.get("expected_mapping") or ""))
        add("")
        add("## 8. 已知限制（与 §7 前合并引用）")
        add("")
    add("")
    for item in report.get("limitations") or []:
        add(f"- {item}")
    add("")
    return "\n".join(lines) + "\n"


# ─── 独立判读报告渲染与校验 ────────────────────────────────────────────────
def independent_checks_all_ok(arms: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    """独立判读模式的校验汇总（检测 0 mismatch + 40 口径率与 M-2 一致）。

    Returns:
        (ok, failures)：ok=False 时 failures 给出逐臂原因（--fail-on-mismatch 用）。
    """
    failures: list[str] = []
    for arm in arms:
        independent = arm.get("independent_judging") or {}
        if not independent:
            failures.append(f"{arm.get('arm')}: 缺 independent_judging 段")
            continue
        if not independent.get("all_ok"):
            cross = independent.get("cross_check_vs_m2") or {}
            failures.append(
                f"{arm.get('arm')}: detection mismatch="
                f"{(cross.get('detection_vs_m2') or {}).get('n_mismatch')}、"
                f"40 口径计数与 M-2 一致={independent.get('m2_rates_match')}"
            )
    return (not failures, failures)


def _fmt6_rate(stats: Any) -> str:
    """detection 统计 dict → ``n/n = %%`` 字符串（分母 0 → "—"）。"""
    if not isinstance(stats, dict):
        return "—"
    denominator = stats.get("n_denominator")
    if not denominator:
        return "—"
    return f"{stats.get('n_detected', 0)}/{denominator} = {float(stats.get('rate') or 0.0) * 100:.2f}%"


def render_independent_readme(report: dict[str, Any], run_meta: dict[str, Any]) -> str:
    """渲染独立判读工件 README（输入 sha256/命令/口径/核心数字/限制）。"""
    lines: list[str] = []
    add = lines.append
    add("# A-05 后续修复：独立判读零 LLM 重放验证（N-3）")
    add("")
    add("> **性质**：N-3 任务的**零 LLM 验证工件**（验证性，不作能力证据/预注册证据）。")
    add("> 验证两处生产修复：① `nodes._append_spec_oracle_to_test_with_verdict` 的")
    add("> `spec_anchor` 接线（修复 df_spec/doc/union/augment 类臂永远 not_attempted 的缺口）；")
    add("> ② `_m1_metrics` 的 LLM-suite / oracle-suite **独立判读**（oracle 失败不再改写 LLM 检出）。")
    add("> 对账权威基线 = M-2 `emse_oracle_quality_20261017`（df_spec 50.00% / df 77.50%，40 口径）。")
    add("")
    add("## 1. 输入 sha256（只读消费）")
    add("")
    add("| 输入 | sha256 |")
    add("|---|---|")
    for entry in report.get("inputs") or []:
        add(f"| `{entry['path']}` | `{entry['sha256']}` |")
    anchor = report.get("anchor_table") or {}
    add(f"| `{anchor.get('path')}` | `{anchor.get('sha256')}` |")
    m2 = (report.get("independent_judging") or {}).get("m2_baseline") or {}
    add(f"| `{m2.get('path')}`（M-2 基线报告） | `{m2.get('sha256')}` |")
    add("")
    add("## 2. 复算命令")
    add("")
    add("```bash")
    add(" ".join(str(x) for x in report.get("command") or []))
    add("```")
    add("")
    add("## 3. 口径")
    add("")
    add("- **state 形态**：只带 `spec_anchor`（复刻生产 df_spec/doc/union/augment 臂，无 `test_plan`）")
    add("  —— 注入成功本身即 N-3 接线修复的生产态证据。")
    add("- **LLM-suite detection**：`_m1_metrics._compute_llm_suite_detection_rate`")
    add("  （pytest `-k` 排除 `test_specir_v2_oracle` / `test_specir_v2_smt_witness`）。")
    add("- **oracle-suite verdict**：`_m1_metrics._compute_oracle_suite_verdict`")
    add("  （`-k` 只选 oracle 测试名，独立运行 buggy/fixed 两侧；取值域见报告 metric 段）。")
    add(f"- **M1 判分口径**：`M1_PER_TEST_TIMEOUT={run_meta.get('m1_per_test_timeout_s')}`s（与 M-2 重放对齐）。")
    add("")
    add("## 4. 核心数字")
    add("")
    add("| 指标 | " + " | ".join(f"`{arm['arm']}`" for arm in report.get("arms") or []) + " |")
    add("|---|" + "---|" * len(report.get("arms") or []))
    add(
        "| 锚命中 / 注入成功（anchor-only state） | "
        + " | ".join(
            f"{(arm['subsets']['all_tasks']['injection']['n_anchor_hit'])}"
            f" / {arm['subsets']['all_tasks']['injection']['n_injected']}"
            for arm in report.get("arms") or []
        )
        + " |"
    )
    add(
        "| LLM-suite detection（40 口径） | "
        + " | ".join(
            _fmt6_rate(
                (arm.get("independent_judging") or {})
                .get("subsets", {})
                .get("defect_programs", {})
                .get("llm_suite_detection")
            )
            for arm in report.get("arms") or []
        )
        + " |"
    )
    add(
        "| M-2 40 口径基线（对账） | "
        + " | ".join(
            _fmt6_rate((arm.get("independent_judging") or {}).get("m2_baseline_40caliber"))
            for arm in report.get("arms") or []
        )
        + " |"
    )
    add(
        "| 与 M-2 计数一致 | "
        + " | ".join(
            str((arm.get("independent_judging") or {}).get("m2_rates_match")) for arm in report.get("arms") or []
        )
        + " |"
    )
    add(
        "| detection 对账 mismatch 数 | "
        + " | ".join(
            str(
                ((arm.get("independent_judging") or {}).get("cross_check_vs_m2") or {})
                .get("detection_vs_m2", {})
                .get("n_mismatch")
            )
            for arm in report.get("arms") or []
        )
        + " |"
    )
    add("")
    if any((arm.get("independent_judging") or {}).get("measurement_limited") for arm in report.get("arms") or []):
        add(
            "> **注意**：本次为 `--limit` 截断运行——40 口径计数**不**与 M-2 全量对账"
            "（只验证逐任务 0 mismatch；全量运行才要求计数一致）。"
        )
        add("")
    add("oracle-suite 四分类（独立判读；40 口径）：")
    add("")
    verdicts = ("correct", "fp", "silent", "misguided", "unavailable")
    add("| 类别 | " + " | ".join(f"`{arm['arm']}`" for arm in report.get("arms") or []) + " |")
    add("|---|" + "---|" * len(report.get("arms") or []))
    for verdict in verdicts:
        add(
            f"| `{verdict}` | "
            + " | ".join(
                str(
                    ((arm.get("independent_judging") or {}).get("subsets", {}).get("defect_programs", {}))
                    .get("oracle_suite_counts", {})
                    .get(verdict, 0)
                )
                for arm in report.get("arms") or []
            )
            + " |"
        )
    add("")
    add("oracle 类别 vs M-2 逐测试分类对账（描述性）：")
    add("")
    for arm in report.get("arms") or []:
        cross = (arm.get("independent_judging") or {}).get("cross_check_vs_m2") or {}
        add(f"- `{arm['arm']}`：{cross.get('oracle_class_vs_m2', {}).get('agreement_counts')}")
    add("")
    add("注入 verdict 对账（anchor-only 接线 vs M-2 反事实）：")
    add("")
    for arm in report.get("arms") or []:
        cross = (arm.get("independent_judging") or {}).get("cross_check_vs_m2") or {}
        add(f"- `{arm['arm']}`：{cross.get('injection_vs_m2', {}).get('agreement_counts')}")
    add("")
    add("## 5. 确定性 / 墙钟")
    add("")
    determinism = run_meta.get("determinism") or {}
    add(f"- body digest：`{run_meta.get('body_digest')}`（不含时间戳/墙钟）")
    add(
        f"- repeat={determinism.get('repeat')}；deterministic={determinism.get('deterministic')}；"
        f"各次 digest={determinism.get('body_digests')}"
    )
    add(f"- 本次重放墙钟：{run_meta.get('tool_wall_s')} s（只进 run_meta）")
    add("")
    add("## 6. 已知限制")
    add("")
    for item in report.get("limitations") or []:
        add(f"- {item}")
    add("")
    return "\n".join(lines) + "\n"


# ─── CLI 入口 ──────────────────────────────────────────────────────────────
def _build_arg_parser() -> argparse.ArgumentParser:
    """CLI 参数定义。"""
    parser = argparse.ArgumentParser(
        prog="oracle_quality_replay",
        description=(
            "A-05 确定性规约 oracle 质量度量：读 df_spec 批工件 + 规格锚表，"
            "原样调用生产注入函数重建 oracle，零 LLM 重放四分类与检出贡献。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--artifact",
        action="append",
        default=[],
        metavar="PATH",
        help="批次 benchmark JSON（可重复；缺省 = df_spec 两臂工件）",
    )
    parser.add_argument(
        "--arm",
        action="append",
        default=[],
        metavar="NAME",
        help="只分析指定臂（可重复；缺省分析各工件内全部臂）",
    )
    parser.add_argument("--anchor-table", default=str(DEFAULT_ANCHOR_TABLE), metavar="PATH", help="规格锚表路径")
    parser.add_argument(
        "--anchor-sha256",
        default=None,
        metavar="HEX",
        help="锚表期望 sha256（缺省从同目录 SHA256SUMS 校验；不允许无校验加载）",
    )
    parser.add_argument(
        "--sha256sums",
        default=None,
        metavar="PATH",
        help="SHA256SUMS 路径覆盖（缺省 = 锚表同目录 SHA256SUMS）",
    )
    parser.add_argument(
        "--out",
        default=None,
        metavar="DIR",
        help=f"输出目录（缺省：混合重放 {_display_path(DEFAULT_OUT)}；独立判读 {_display_path(INDEPENDENT_OUT_DEFAULT)}）",
    )
    parser.add_argument(
        "--independent-judging",
        action="store_true",
        help=(
            "N-3 独立判读模式：state 只带 spec_anchor（复刻生产 df_spec 臂），"
            "调用生产 _m1_metrics 的 LLM-suite/oracle-suite 分离判读，并与 M-2 基线逐任务对账"
        ),
    )
    parser.add_argument(
        "--m2-report",
        default=str(M2_REPORT_DEFAULT),
        metavar="PATH",
        help="M-2 基线报告（独立判读对账权威基线；缺省 = emse_oracle_quality_20261017/ORACLE_QUALITY_REPORT.json）",
    )
    parser.add_argument(
        "--compare-report",
        default=None,
        metavar="PATH",
        help=(
            "O-1 仪器加固 before/after 对照基线（任一 A-05 oracle 质量报告；给定时报告增加 "
            "instrument_hardening_comparison 段与 README 对照表）"
        ),
    )
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
        default=None,
        metavar="SEC",
        help=(
            "pytest-timeout 单测超时秒数（0=不用插件，仅整文件墙钟）；"
            "缺省：混合重放 10.0 / 独立判读 1.0（与 M-2 重放口径对齐）"
        ),
    )
    parser.add_argument(
        "--collect-timeout", type=float, default=60.0, metavar="SEC", help="收集阶段墙钟上限（默认 60）"
    )
    parser.add_argument(
        "--file-timeout", type=float, default=120.0, metavar="SEC", help="整文件执行墙钟上限（默认 120）"
    )
    parser.add_argument("--limit", type=int, default=0, help="每个臂只分析前 N 个任务（0=全部；测试/冒烟用）")
    parser.add_argument("--repeat", type=int, default=1, help="整批重复次数（≥2 用于确定性验证；默认 1）")
    parser.add_argument("--skip-markdown", action="store_true", help="只写 JSON，不写 Markdown/README")
    parser.add_argument("--fail-on-mismatch", action="store_true", help="交叉校验 mismatch>0 时退出码 3（gate 用）")
    parser.add_argument("--quiet", action="store_true", help="不打印逐任务进度")
    return parser


def _resolve_selection(artifacts: list[Path], arms_requested: list[str]) -> list[dict[str, Any]]:
    """解析（工件, 臂）选择；校验重复工件与未知臂，返回按输入顺序的条目。"""
    entries: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for path in artifacts:
        resolved = str(path.resolve())
        if resolved in seen_paths:
            raise mm.ArtifactError(f"工件重复传入: {path}")
        seen_paths.add(resolved)
        artifact = load_artifact(path)
        artifact["__path__"] = str(path)
        available = list_artifact_arms(artifact)
        selected = arms_requested or available
        unknown = sorted(set(selected) - set(available))
        if unknown:
            raise mm.ArtifactError(f"工件 {path} 内不存在臂 {unknown}（可用: {available}）")
        entries.append(
            {
                "path": path,
                "artifact_label": _display_path(path),
                "sha256": sha256_file(path),
                "arms": selected,
                "data": artifact,
            }
        )
    if not entries:
        raise mm.ArtifactError("未提供任何工件")
    return entries


def _run_replay(
    selection: list[dict[str, Any]],
    *,
    anchor_table: dict[str, Any],
    roots: list[Path],
    config: dict[str, Any],
    jobs: int,
    limit: int,
    progress: bool,
    independent_judging: bool = False,
    m2_baseline: dict[str, Any] | None = None,
    compare_baseline: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """执行完整重放，返回 (报告 body, 本次运行的易变元信息)。

    ``independent_judging``（N-3）：每臂额外产出独立判读段（与 M-2 基线对账）。
    """
    started = time.time()
    anchors = anchor_table["anchors"]
    arms: list[dict[str, Any]] = []
    arms.extend(
        build_arm_result(
            artifact_path=entry["path"],
            artifact_sha256=entry["sha256"],
            artifact_label=entry["artifact_label"],
            arm=arm,
            rows=select_rows(entry["data"], arm),
            anchors=anchors,
            roots=roots,
            pytest_timeout_s=float(config["per_test_timeout_s"]),
            collect_timeout_s=float(config["collect_timeout_s"]),
            file_timeout_s=float(config["file_timeout_s"]),
            jobs=jobs,
            limit=limit,
            progress=progress,
            independent_judging=independent_judging,
            m2_arm=((m2_baseline or {}).get("arm_index") or {}).get(arm),
        )
        for entry in selection
        for arm in entry["arms"]
    )
    artifact_entries = [
        {
            "path": entry["artifact_label"],
            "sha256": entry["sha256"],
            "arms": [{"arm": arm, "n_rows": len(select_rows(entry["data"], arm))} for arm in entry["arms"]],
        }
        for entry in selection
    ]
    anchor_info = {
        "path": anchor_table["path"],
        "sha256": anchor_table["sha256"],
        "expected_sha256": anchor_table["expected_sha256"],
        "expected_sha256_source": anchor_table["expected_sha256_source"],
        "sums_path": anchor_table["sums_path"],
        "n_anchors": len(anchor_table["anchors"]),
        "meta": anchor_table["meta"],
    }
    m2_info = (
        {
            "path": (m2_baseline or {}).get("path"),
            "sha256": (m2_baseline or {}).get("sha256"),
            "body_digest": (m2_baseline or {}).get("body_digest"),
        }
        if independent_judging
        else None
    )
    instrument_comparison: dict[str, Any] | None = None
    if compare_baseline is not None:
        instrument_comparison = build_instrument_hardening_comparison(arms, compare_baseline)
    body = build_report(
        artifact_entries=artifact_entries,
        anchor_info=anchor_info,
        arms=arms,
        config=config,
        command=_command_line(),
        independent_judging=independent_judging,
        m2_info=m2_info,
        instrument_comparison=instrument_comparison,
    )
    meta = {
        "generated_at": _now_iso(),
        "tool_wall_s": round(time.time() - started, 3),
        "body_digest": body_digest(body),
    }
    return body, meta


def _command_line() -> list[str]:
    """当前进程的可复算命令行（统一写成 ``python -m experiments.oracle_quality_replay ...``）。"""
    return ["python", "-m", "experiments.oracle_quality_replay", *sys.argv[1:]]


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
        diffs.extend(mm._diff_paths(base_body, strip_volatile(body)))
    deterministic = len(set(digests)) == 1
    return {
        "repeat": len(repeats),
        "body_digests": digests,
        "deterministic": deterministic,
        "difference_paths": diffs[:20],
        "note": "differences 仅出现在易变字段之外视为非确定性；oracle 编译/分类本身零随机源",
    }


def _check_cross_check(arms: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    """交叉校验失败明细（--fail-on-mismatch / 报告层共用）。"""
    failures: list[str] = []
    for arm in arms:
        cc = arm["cross_check"]
        if not cc["all_ok"]:
            failures.append(
                f"{arm['arm']}: detection mismatch={cc['detection_vs_archive']['n_mismatch']}、"
                f"verdict mismatch={cc['oracle_verdict_vs_archive']['n_mismatch']}、"
                f"字段自洽违规={len(cc['archive_field_consistency_violations'])}"
            )
    return (not failures, failures)


def main(argv: list[str] | None = None) -> int:
    """CLI 主入口：解析 → 锚表校验（+ 独立判读的 M-2 基线）→ 重放 → 落盘工件。"""
    args = _build_arg_parser().parse_args(argv)
    independent = bool(args.independent_judging)
    out_dir = Path(args.out) if args.out else (INDEPENDENT_OUT_DEFAULT if independent else DEFAULT_OUT)
    m2_baseline: dict[str, Any] | None = None
    try:
        anchor_path = Path(args.anchor_table).expanduser()
        anchor_table = load_anchor_table(
            anchor_path,
            sums_path=Path(args.sha256sums).expanduser() if args.sha256sums else None,
            expected_sha256=args.anchor_sha256,
        )
        artifact_paths = [Path(p).expanduser() for p in args.artifact] or list(DEFAULT_ARTIFACTS)
        selection = _resolve_selection(artifact_paths, list(args.arm or []))
        if independent:
            m2_baseline = load_m2_report(Path(args.m2_report).expanduser())
        if getattr(args, "compare_report", None):
            # O-1：before/after 对照基线 fail-closed 前置加载（不消耗重放时间）
            compare_baseline = load_oracle_quality_report(Path(args.compare_report).expanduser())
        else:
            compare_baseline = None
    except (OracleQualityError, mm.ArtifactError) as e:
        print(f"[oracle] 错误: {e}", file=sys.stderr)
        return 2
    out_dir.mkdir(parents=True, exist_ok=True)
    roots = resolve_quixbugs_roots(args.quixbugs_root)
    pytest_timeout_ok = pytest_timeout_available()
    # 单测超时口径：混合重放历史默认 10s；独立判读缺省 1s（对齐 M-2 重放）。
    default_per_test_timeout = 1.0 if independent else 10.0
    per_test_timeout = float(default_per_test_timeout if args.per_test_timeout is None else args.per_test_timeout)
    if per_test_timeout > 0 and not pytest_timeout_ok:
        print(
            "[oracle] 警告: pytest-timeout 不可用——回退整文件墙钟口径（超时测试整体单列 timeout）",
            file=sys.stderr,
        )
        per_test_timeout = 0.0
    # 独立判读：生产 _m1_metrics 走 M1_PER_TEST_TIMEOUT 环境变量；显式对齐到
    # 同一秒数（默认 1s），跑批结束后恢复宿主值（不污染进程外环境）。
    previous_m1_timeout = os.environ.get("M1_PER_TEST_TIMEOUT")
    m1_per_test_timeout_s: int | None = None
    if independent:
        m1_per_test_timeout_s = int(per_test_timeout) if per_test_timeout > 0 else 0
        os.environ["M1_PER_TEST_TIMEOUT"] = str(m1_per_test_timeout_s)
    try:
        config = {
            "mode": "independent_judging" if independent else "mixed_replay",
            "per_test_timeout_s": per_test_timeout,
            "m1_per_test_timeout_s": m1_per_test_timeout_s,
            "pytest_timeout_plugin_available": pytest_timeout_ok,
            "collect_timeout_s": float(args.collect_timeout),
            "file_timeout_s": float(args.file_timeout),
            "jobs": int(args.jobs),
            "limit": int(args.limit),
            "test_filename": TEST_FILENAME,
            "layout": "dual(flat+python_programs package)",
            "quixbugs_roots": [str(p) for p in roots],
            "pytest_version": _pytest_version(),
            "oracle_test_markers": list(ORACLE_TEST_MARKERS),
            "injection_function": "src.graph.nodes._append_spec_oracle_to_test_with_verdict",
            "state_reconstruction": (
                "只带 spec_anchor（复刻生产 df_spec/doc/union/augment 臂；无 test_plan/spec_ir）"
                if independent
                else (
                    "test_plan={function_name, logic_analysis} + target_function(归档 suggested_function) + "
                    "module_name(task_id 末段) + target_code(缺陷版源码)；不写 spec_ir/boundary_triplets"
                )
            ),
            "m2_baseline": ({"path": m2_baseline["path"], "sha256": m2_baseline["sha256"]} if m2_baseline else None),
            "instrument_compare_report": (
                _display_path(Path(args.compare_report).expanduser()) if getattr(args, "compare_report", None) else None
            ),
        }
        repeats: list[tuple[dict[str, Any], dict[str, Any]]] = []
        n_repeat = max(1, int(args.repeat))
        for index in range(n_repeat):
            if n_repeat > 1:
                print(f"[oracle] 确定性重放 {index + 1}/{n_repeat}", file=sys.stderr)
            body, meta = _run_replay(
                selection,
                anchor_table=anchor_table,
                roots=roots,
                config=config,
                jobs=int(args.jobs),
                limit=int(args.limit),
                progress=not args.quiet,
                independent_judging=independent,
                m2_baseline=m2_baseline,
                compare_baseline=compare_baseline,
            )
            repeats.append((body, meta))
    finally:
        if independent:
            if previous_m1_timeout is None:
                os.environ.pop("M1_PER_TEST_TIMEOUT", None)
            else:
                os.environ["M1_PER_TEST_TIMEOUT"] = previous_m1_timeout
    body, meta = repeats[0]
    determinism = _determinism_meta(repeats)
    archive_ok, archive_failures = _check_cross_check(body["arms"])
    if independent:
        independent_ok, independent_failures = independent_checks_all_ok(body["arms"])
        ok = bool(archive_ok and independent_ok)
        failures = [*archive_failures, *independent_failures]
    else:
        ok, failures = archive_ok, archive_failures
    run_meta = {
        **meta,
        "argv": list(sys.argv),
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "determinism": determinism,
        "cross_check_ok": ok,
        "cross_check_failures": failures,
        "m1_per_test_timeout_s": m1_per_test_timeout_s,
    }
    schema = INDEPENDENT_SCHEMA_VERSION if independent else SCHEMA_VERSION
    payload = {"schema_version": schema, "report": body, "run_meta": run_meta}
    json_path = out_dir / ("ORACLE_INDEPENDENT_JUDGING_REPORT.json" if independent else "ORACLE_QUALITY_REPORT.json")
    from src.utils.atomic_io import atomic_write_json, atomic_write_text

    atomic_write_json(str(json_path), payload)
    print(f"[oracle] JSON 报告: {json_path}", flush=True)
    if not args.skip_markdown:
        if independent:
            readme_path = out_dir / "README.md"
            atomic_write_text(str(readme_path), render_independent_readme(body, run_meta))
            print(f"[oracle] README: {readme_path}", flush=True)
        else:
            md_path = out_dir / "ORACLE_QUALITY_REPORT.md"
            atomic_write_text(str(md_path), render_markdown(body, run_meta))
            readme_path = out_dir / "README.md"
            atomic_write_text(str(readme_path), render_readme(body, run_meta))
            print(f"[oracle] Markdown/README: {md_path} / {readme_path}", flush=True)
    if not ok:
        print("[oracle] 交叉校验未通过（0 mismatch 要求）: " + "；".join(failures), file=sys.stderr)
        if args.fail_on_mismatch:
            return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
