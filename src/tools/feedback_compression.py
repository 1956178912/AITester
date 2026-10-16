"""
P2 一期（2026-10 批次）：观测级行粒度压缩（Observation Compression）。

背景（A/B 阴性结果驱动的 token 成本优化）：
    完整编排臂（aitester）每任务 token 26.1k，而检出优先协议臂
    （plain_llm_df）仅 4.2k——6.2× 开销是编排净负（−28pp detection）的
    直接体现。优化目标：token/任务 ≤10k（−60%）且 detection 掉幅 ≤2pp。

    一期方案（低成本、先行）：Debugger→Generator 的反馈不传完整 trace，
    只传「失败测试涉及的源代码行 + 错误类型 + 存活变异体摘要」。
    参考：arXiv:2605.15315 行级压缩在 SWE-bench Verified 上省 23–30%
    token。二期高成本方向（LaMAR KV-Cache 级通信，O(N²)→O(N)）另行立项，
    本模块不涉及。

设计口径（保守、零 LLM 成本、默认关，ADR-0003 + ADR-0004）：
    - FEEDBACK_COMPRESSION_ENABLE=false（默认）时，调用方不调本模块，
      历史口径零变化；
    - 开启时，_generator_node 在再生成轮经 build_compressed_feedback 从
      state 既有观测（runtime_probe_snapshot / fl_spectral_focus /
      test_output / failed_cases / mutation_feedback / error_category）
      提取压缩反馈，经 build_feedback_compression_section 渲染为
      Generator prompt 注入段落（有界，替代朴素全量 trace 注入）；
    - 候选行定位复用既有能力（不重复造轮子），按信任优先级：
      1. runtime_probe 快照最内层帧（frames[0] = 异常抛出点；与
         debugger._locate_repair_focus_from_probe 同口径）；
      2. fl_spectral Ochiai Top-k（FL_SPECTRAL_ENABLE 默认开，
         _debugger_node 已测量入 state，纯读取零成本）；
      3. traceback 行号（复用 ErrorClassifier.extract_error_context
         公开 API；完整帧与 pytest --tb=short 两种格式均已覆盖）；
    - 跨文件保护：traceback 帧文件名 basename 与 target_module 不符时
      丢弃该候选（复刻 debugger._locate_repair_focus 的守卫口径，
      防定位到测试侧帧误导修复）；
    - 体积上界：行数 / 每行字符 / 变异体条数与单条字符 / 失败测试条数 /
      段落总字符均有上限（环境变量可调，非法值钳制），防 prompt 爆炸；
    - 降级路径：无失败用例 / 无快照 / 无变异反馈 → 保守回退（无实质
      内容返回 None，不注入）；任何异常静默返回 None，绝不阻断工作流。

纯 stdlib（os / logging），零新依赖；中文注释与 docstring（项目约定）。
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

from src.utils.env_utils import env_flag

if TYPE_CHECKING:
    from src.graph.state import AITesterState

logger = logging.getLogger(__name__)

_ENV = "FEEDBACK_COMPRESSION_ENABLE"

# ─── 体积参数默认值与钳制区间 ────────────────────────────────────────────
# 钳制理由：体积参数是 prompt 爆炸的防线——上限调过高压不住 token，下限
# 调过低会把「压缩」退化成「只传一个行号」的信息损失；非法值（非数字 /
# 空串）一律回退默认值（与项目既有 _xxx_max 助手同口径）。
_DEFAULT_MAX_LINES = 8
_MAX_LINES_RANGE = (1, 50)
_DEFAULT_LINE_CHARS = 200
_LINE_CHARS_RANGE = (20, 2000)
_DEFAULT_MAX_MUTANTS = 5
_MAX_MUTANTS_RANGE = (0, 20)
_DEFAULT_MUTANT_CHARS = 120
_MUTANT_CHARS_RANGE = (20, 1000)
_DEFAULT_MAX_TESTS = 3
_MAX_TESTS_RANGE = (0, 10)
_DEFAULT_MAX_CHARS = 4000
_MAX_CHARS_RANGE = (500, 20000)


def feedback_compression_enabled() -> bool:
    """P2 一期开关（FEEDBACK_COMPRESSION_ENABLE=true 时启用，默认 false）。

    默认关 = 历史口径零变化（ADR-0003：新功能默认关）。调用期读取 env
    （非 import 期），测试可 monkeypatch.setenv 切换，保留消融能力。
    """
    return env_flag(_ENV)


def _clamp_env_int(name: str, default: int, lo: int, hi: int) -> int:
    """读取环境变量整数并钳制到 [lo, hi]（非法值 → 默认值）。"""
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return max(lo, min(value, hi))


def _max_lines() -> int:
    """涉及源代码行数上限（FEEDBACK_COMPRESSION_MAX_LINES，默认 8）。"""
    return _clamp_env_int("FEEDBACK_COMPRESSION_MAX_LINES", _DEFAULT_MAX_LINES, *_MAX_LINES_RANGE)


def _line_chars() -> int:
    """单行源码截断字符数（FEEDBACK_COMPRESSION_LINE_CHARS，默认 200）。"""
    return _clamp_env_int("FEEDBACK_COMPRESSION_LINE_CHARS", _DEFAULT_LINE_CHARS, *_LINE_CHARS_RANGE)


def _max_mutants() -> int:
    """存活变异体摘要条数上限（FEEDBACK_COMPRESSION_MAX_MUTANTS，默认 5）。"""
    return _clamp_env_int("FEEDBACK_COMPRESSION_MAX_MUTANTS", _DEFAULT_MAX_MUTANTS, *_MAX_MUTANTS_RANGE)


def _mutant_chars() -> int:
    """单条变异体描述截断字符数（FEEDBACK_COMPRESSION_MUTANT_CHARS，默认 120）。"""
    return _clamp_env_int("FEEDBACK_COMPRESSION_MUTANT_CHARS", _DEFAULT_MUTANT_CHARS, *_MUTANT_CHARS_RANGE)


def _max_tests() -> int:
    """失败测试名条数上限（FEEDBACK_COMPRESSION_MAX_TESTS，默认 3）。"""
    return _clamp_env_int("FEEDBACK_COMPRESSION_MAX_TESTS", _DEFAULT_MAX_TESTS, *_MAX_TESTS_RANGE)


def _max_section_chars() -> int:
    """段落总字符上限（FEEDBACK_COMPRESSION_MAX_CHARS，默认 4000）。"""
    return _clamp_env_int("FEEDBACK_COMPRESSION_MAX_CHARS", _DEFAULT_MAX_CHARS, *_MAX_CHARS_RANGE)


def _probe_throw_line(state: AITesterState) -> int | None:
    """运行时探针快照的最内层帧行号（frames[0] = 异常抛出点，无则 None）。

    帧序口径与 debugger._locate_repair_focus_from_probe 一致：frames
    按「最内层抛出点 → 外层」排列，frames[0] 即抛出点帧
    （runtime_probe.capture_failure_snapshot 产物结构）。
    """
    snapshot = state.get("runtime_probe_snapshot") or {}
    if not isinstance(snapshot, dict):
        return None
    frames = snapshot.get("frames") or []
    if not isinstance(frames, list) or not frames:
        return None
    first = frames[0]
    if not isinstance(first, dict):
        return None
    line = first.get("line")
    return line if isinstance(line, int) and line > 0 else None


def _fl_candidate_lines(state: AITesterState) -> list[int]:
    """FL_spectral Ochiai Top-k 候选行（分数降序即 top_k 既有顺序，无则空列表）。

    零成本：纯读 state（FL_SPECTRAL_ENABLE 默认开，_debugger_node 已把
    测量结果写入 state["fl_spectral_focus"]）。
    """
    focus = state.get("fl_spectral_focus") or {}
    if not isinstance(focus, dict):
        return []
    top_k = focus.get("top_k") or []
    if not isinstance(top_k, list):
        return []
    lines: list[int] = []
    for item in top_k:
        if isinstance(item, dict):
            line = item.get("line")
            if isinstance(line, int) and line > 0:
                lines.append(line)
    return lines


def _traceback_candidate_line(state: AITesterState) -> int | None:
    """traceback 兜底候选行（复用 ErrorClassifier.extract_error_context，无则 None）。

    跨文件保护（复刻 debugger._locate_repair_focus 守卫口径）：traceback
    帧文件名 basename 与 target_module 不符时丢弃该候选——纯测试侧断言
    失败 / 第三方库帧不应定位到被测文件，宁缺勿误。
    """
    test_output = str(state.get("test_output") or "")
    failed_cases = state.get("failed_cases") or []
    if not test_output and not failed_cases:
        return None
    try:
        from src.agents.error_classifier import ErrorClassifier

        safe_cases = [case for case in failed_cases if isinstance(case, dict)]
        context = ErrorClassifier().extract_error_context(test_output, safe_cases)
    except Exception as e:  # 定位能力异常不阻断压缩主流程（保守降级）
        logger.debug("P2 压缩反馈 traceback 定位异常（降级跳过该路）: %s", e)
        return None
    line = getattr(context, "line", None)
    if not isinstance(line, int) or line <= 0:
        return None
    module_name = state.get("module_name")
    filename = getattr(context, "filename", None)
    if module_name and filename:
        file_base = str(filename).rsplit("/", 1)[-1]
        if file_base not in (module_name, f"{module_name}.py") and not file_base.startswith(module_name):
            logger.debug(
                "P2 压缩反馈跨文件保护：traceback 帧 %s 与 target_module=%s 不符，丢弃", file_base, module_name
            )
            return None
    return line


def _build_compressed_feedback_inner(state: AITesterState) -> dict[str, Any] | None:
    """build_compressed_feedback 的主体实现（异常由外层统一兜底）。"""
    # 候选行收集：按信任优先级（probe > fl_spectral > traceback）先到先得去重
    candidates: list[tuple[int, str]] = []
    seen: set[int] = set()

    def _add(line: int | None, origin: str) -> None:
        if isinstance(line, int) and line > 0 and line not in seen:
            seen.add(line)
            candidates.append((line, origin))

    # 1. probe（最高信任：运行时真实抛出点；RUNTIME_PROBE_ENABLE 默认关，开了才有）
    _add(_probe_throw_line(state), "probe")
    # 2. FL_spectral Ochiai Top-k（默认开的零成本测量，分数降序）
    for line in _fl_candidate_lines(state):
        _add(line, "fl_spectral")
    # 3. traceback 兜底（零开关依赖，任何开关组合下都有定位能力）
    _add(_traceback_candidate_line(state), "traceback")

    # 源码回填（target_code.splitlines 按行号取原文；越界 / 空码守卫：
    # 仅保留行号记录，source 为空串，不崩）
    code_lines = (state.get("target_code") or "").splitlines()
    target_lines: list[dict[str, Any]] = []
    for lineno, origin in candidates:
        source = code_lines[lineno - 1][: _line_chars()] if 1 <= lineno <= len(code_lines) else ""
        target_lines.append({"lineno": lineno, "source": source, "origin": origin})
    # 按行号升序展示 + 行数上限截断
    target_lines.sort(key=lambda item: item["lineno"])
    target_lines = target_lines[: _max_lines()]

    # 失败测试名（≤ _max_tests 条；空名跳过）
    failed_tests: list[str] = []
    for case in state.get("failed_cases") or []:
        if isinstance(case, dict):
            name = str(case.get("name") or "").strip()
            if name:
                failed_tests.append(name)
        if len(failed_tests) >= _max_tests():
            break

    # 存活变异体摘要（≤ _max_mutants 条 × ≤ _mutant_chars 字符）+ 变异得分透传
    survived: list[str] = []
    score: float | None = None
    mutation_feedback = state.get("mutation_feedback") or {}
    if isinstance(mutation_feedback, dict):
        raw_survived = mutation_feedback.get("survived_mutants") or []
        if isinstance(raw_survived, list):
            survived = [str(desc)[: _mutant_chars()] for desc in raw_survived[: _max_mutants()]]
        raw_score = mutation_feedback.get("mutation_score")
        if isinstance(raw_score, (int, float)) and not isinstance(raw_score, bool):
            score = float(raw_score)

    # 保守条件：无实质内容（无失败测试 / 无涉及行 / 无变异摘要）→ 不注入
    if not failed_tests and not target_lines and not survived:
        return None

    return {
        "schema_version": 1,
        # error_category 由 _debugger_node 本轮写入（regenerate 路由前必经
        # debugger 的路径）；缺省 "unknown"（over_red 等不过 debugger 的路径）
        "error_category": str(state.get("error_category") or "unknown"),
        "failed_tests": failed_tests,
        "target_lines": target_lines,
        "survived_mutants": survived,
        "mutation_score": score,
        # 渲染后由 build_feedback_compression_section 回填（观测字段）
        "section_chars": 0,
    }


def build_compressed_feedback(state: AITesterState) -> dict[str, Any] | None:
    """从 state 既有观测提取行粒度压缩反馈（零 LLM 成本，纯文本处理）。

    产物 schema：
        {"schema_version": 1,
         "error_category": str,                  # state["error_category"]（缺省 "unknown"）
         "failed_tests": [str, ...],             # state["failed_cases"][i]["name"]，≤ _max_tests()
         "target_lines": [{"lineno": int, "source": str, "origin": str}],  # ≤ _max_lines()，行号升序
         "survived_mutants": [str, ...],         # state["mutation_feedback"]["survived_mutants"]，≤ _max_mutants()
         "mutation_score": float | None,         # state["mutation_feedback"]["mutation_score"]
         "section_chars": int}                   # 渲染后回填（观测）
    其中 target_lines[].origin ∈ {"probe", "fl_spectral", "traceback"}
    （候选行定位来源，见模块 docstring 的优先级口径）。

    Args:
        state: 当前工作流状态（读 runtime_probe_snapshot / fl_spectral_focus /
            test_output / failed_cases / mutation_feedback / error_category /
            target_code / module_name，全部为既有键，不引入新观测源）。

    Returns:
        压缩反馈字典；无实质内容（§降级路径）或任何异常时返回 None
        （调用方不注入，prompt 与历史逐字节一致）。
    """
    try:
        return _build_compressed_feedback_inner(state)
    except Exception as e:  # 观测层兜底：任何异常静默降级，绝不阻断工作流
        logger.debug("P2 压缩反馈构建异常（保守降级 None）: %s", e)
        return None


def build_feedback_compression_section(compressed: dict[str, Any] | None) -> str:
    """把压缩反馈渲染为 Generator prompt 注入段落（None / 空 → 空串）。

    保守口径：compressed 为 None / 空 dict 时返回空串（调用方不追加，
    prompt 与历史逐字节一致）。渲染成功后把段落字符数回填到
    compressed["section_chars"]（观测字段，供实验层证明体积上界——
    该上界即「行级压缩 vs 朴素全量 trace 注入」的可测量差值）。

    Args:
        compressed: build_compressed_feedback 产物。

    Returns:
        注入段落文本（总字符 ≤ _max_section_chars()），或空串。
    """
    if not compressed:
        return ""
    error_category = str(compressed.get("error_category") or "unknown")
    failed_tests = compressed.get("failed_tests") or []
    target_lines = compressed.get("target_lines") or []
    survived = compressed.get("survived_mutants") or []
    score = compressed.get("mutation_score")

    lines: list[str] = ["【压缩反馈（观测级行粒度压缩）】", f"错误类型：{error_category}"]
    if failed_tests:
        lines.append("失败测试：" + ", ".join(failed_tests))
    if target_lines:
        lines.append("涉及源代码行（按行号，标注定位来源）：")
        lines.extend(
            f"- 第 {item.get('lineno', '?')} 行（{item.get('origin', '?')}）: {item.get('source', '')}"
            for item in target_lines
        )
    if survived:
        lines.append(f"存活变异体摘要（上一轮变异测试未捕获，共 {len(survived)} 条）：")
        lines.extend(f"- {desc}" for desc in survived)
    if score is not None:
        lines.append(f"当前变异得分 {score}")
    lines.append(
        "请针对上述失败位置与未捕获故障模式补强断言；期望值必须来自问题语义（数学定律/规约），不得照抄实现当前行为。"
    )

    section = "\n".join(lines)
    # 防御性硬截断：正常情况下各分项上限已保证不超限；极端 env 配置下
    # 以省略号标记截断（宁缺勿滥，保指令尾部可读）
    max_chars = _max_section_chars()
    if len(section) > max_chars:
        section = section[: max_chars - 1] + "…"
    # 回填观测字段（渲染后实际字符数，实验层量「压缩 vs 全量」差值用）
    compressed["section_chars"] = len(section)
    return section


__all__ = [
    "build_compressed_feedback",
    "build_feedback_compression_section",
    "feedback_compression_enabled",
]
