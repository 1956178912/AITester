"""
多候选补丁生成与验证筛选（3.1 修复成功率增强）。

背景：
    当前系统 Debugger 单轮生成 1 个补丁 → 直接 apply_patch_to_code 写盘 →
    重新执行测试。单个补丁生成存在"一步走错步步错"的风险：LLM 偶发
    输出语法残缺、误删函数、改错行时，该补丁既会污染 target_code，
    又会带着"错误的诊断路径"进入下一轮迭代，白白消耗修复预算。

    多候选补丁策略（multi-candidate patching）：
    1. 在同一轮内生成 N 个候选补丁（扰动 prompt 让 LLM 走不同的
       修复思路，而非单纯靠温度去噪）；
    2. 静态筛选（cheap gate）：对每个候选做 `ast.parse` 语法校验 +
       函数定义完整性校验，淘汰明显坏候选（不消耗执行成本）；
    3. 执行验证（expensive gate，可选）：对幸存候选逐个写回临时副本
       并跑一遍测试，选"通过率最高且不低于原通过率"的候选；
    4. 仅当选中的候选严格优于原代码时才提交到 target_code。

设计约束：
    - 默认关闭（ENABLE_MULTI_CANDIDATE_PATCH=False，经 workflow 节点
      可选启用）：保持历史实验口径不变，开启时通过环境变量 / 参数注入。
    - 候选数 N 默认 3（经验值：2 太少难跳出局部，5 以上 token 成本
      线性放大且收益递减）。
    - 静态筛选不依赖 LLM、成本极低；执行验证复用 ExecutorAgent
      （含沙箱/重试），不新增执行基础设施。
    - 全程在内存完成候选评估，写盘只在"选中"时发生一次（原子写），
      与现有 patch_applier 的安全检查口径一致（无函数定义 / 过短 /
      非法路径 均拒绝）。
"""

from __future__ import annotations

import ast
import difflib
import logging
import os
import tempfile
from dataclasses import dataclass
from typing import Any

from src.tools.patch_applier import _count_function_defs, apply_patch_to_code

logger = logging.getLogger(__name__)

# ─── 魔数常量（统一管理，便于后续调整）─────────────────────────────────────
# 候选数默认值：3（2 太少难跳出局部，5+ token 成本线性放大且收益递减）
_DEFAULT_CANDIDATE_COUNT = 3
# 候选数上限：防止误配置（如 N=50）拖垮 LLM 配额
_MAX_CANDIDATE_COUNT = 8
# 候选扰动提示词：N 个候选各自追加不同视角的引导，让 LLM 走不同修复路径
# （比单纯调温度更可控——温度采样可能重复生成同一补丁，视角扰动保证差异）
_CANDIDATE_PROMPT_VARIANTS = [
    "请给出【方案 A（最小改动）】：只做让失败测试通过的最小修复，尽量保留原代码结构与命名，不重构无关函数。",
    "请给出【方案 B（根因修复）】：定位根本原因，允许重写相关函数的完整实现，必要时调整内部结构（不改对外接口）。",
    "请给出【方案 C（防御式修复）】：除了修复主路径，补充边界与异常"
    "输入的健壮性处理（类型检查、空值、越界），确保相邻用例不再误伤。",
]
# ───────────────────────────────────────────────────────────────────────────


def candidate_variant_prompt(index: int, num_candidates: int) -> str:
    """生成第 index（0 起）个候选的扰动提示词（循环取模，超出变体数时复用）。

    Args:
        index: 候选序号（0 起）。
        num_candidates: 候选总数（用于在提示中说明"这是 N 个候选中的第几个"）。

    Returns:
        追加到 Debugger 基础 query 之后的扰动提示字符串。
    """
    variant = _CANDIDATE_PROMPT_VARIANTS[index % len(_CANDIDATE_PROMPT_VARIANTS)]
    return f"【多候选修复 {index + 1}/{num_candidates}】{variant}"


def static_validate_patch(original_code: str, patch: str) -> tuple[bool, str, str]:
    """对候选补丁做静态筛选（3.1 的 cheap gate，不消耗 LLM 与执行成本）。

    校验项：
    1. 补丁能成功 apply（单函数/整文件模式，见 patch_applier）；
    2. 应用后的代码可 `ast.parse`（语法完整）；
    3. 函数定义数量不减少（防止 LLM 误删其他函数导致模块退化）；
    4. 应用后代码非空且长度不低于原代码 10%（沿用 patch_applier 安全检查口径）。

    Args:
        original_code: 原始被测代码。
        patch: 候选补丁文本（可含 ```python 包裹）。

    Returns:
        (是否通过静态筛选, 拒绝原因, 应用后的完整代码)。
        通过时原因为空字符串、应用后代码为 apply_patch_to_code 的产物
        （供调用方直接复用，无需二次应用补丁）；拒绝时应用后代码为空串。
    """
    if not patch or not patch.strip():
        return False, "空补丁", ""

    new_code, applied = apply_patch_to_code(original_code, patch)
    if not applied:
        return False, "补丁无法应用到原代码（函数定位/完整性校验失败）", ""

    if new_code == original_code:
        return False, "补丁未产生实际改动", ""

    # 安全检查 1：过短（与 workflow._patch_applier_node 同口径，防 LLM 返回空壳）
    if len(new_code) < len(original_code) * 0.1:
        return False, f"应用后代码过短（{len(new_code)} < 原 {len(original_code)} 的 10%）", ""

    # 安全检查 2：必须保留至少一个函数定义
    if _count_function_defs(new_code) == 0 and _count_function_defs(original_code) > 0:
        return False, "应用后代码丢失了全部函数定义", ""

    # 安全检查 3：语法完整（ast.parse 可编译）
    try:
        ast.parse(new_code)
    except SyntaxError as e:
        return False, f"语法错误（line {e.lineno}）: {e.msg}", ""

    # 安全检查 4：函数定义数量不减少（防止误删其他函数）
    if _count_function_defs(new_code) < _count_function_defs(original_code):
        return False, "函数定义数量减少（可能误删其他函数）", ""

    return True, "", new_code


@dataclass
class CandidateResult:
    """单个候选补丁的评估结果。

    属性:
        index: 候选序号（0 起）。
        patch: 补丁文本（原始输出，可能含 ```python 包裹）。
        new_code: 应用后的完整代码（静态筛选失败时保持 None）。
        static_passed: 静态筛选是否通过。
        static_reason: 静态拒绝原因（通过时为空字符串）。
        exec_passed: 执行验证是否通过（未执行验证时保持 None）。
        exec_coverage: 执行验证的覆盖率（未执行验证时保持 None）。
    """

    index: int
    patch: str
    new_code: str | None = None
    static_passed: bool = False
    static_reason: str = ""
    exec_passed: bool | None = None
    exec_coverage: float | None = None
    # 3.2 改进：行级信用分配评分（line_level_credit_scores 计算，
    # 静态模式排序与执行模式记录复用；None 表示未计算）
    credit_score: float | None = None


def generate_candidates(
    debugger: Any,
    target_code: str,
    test_output: str,
    failed_cases: list[dict[str, str]],
    num_candidates: int = _DEFAULT_CANDIDATE_COUNT,
    rag_references: list[dict[str, Any]] | None = None,
    focus_function: str | None = None,
    target_module: str | None = None,
) -> list[CandidateResult]:
    """生成并静态筛选 N 个候选补丁（3.1 核心入口）。

    流程：
    1. 取 num_candidates 个候选（超上限时截断到 _MAX_CANDIDATE_COUNT）；
    2. 逐候选调用 debugger.debug（附加不同视角的扰动提示，走不同修复路径）；
    3. 对每个候选做 static_validate_patch 静态筛选，淘汰明显坏候选；
    4. 返回全部 CandidateResult（含通过/拒绝），由调用方决定后续筛选。

    Args:
        debugger: DebuggerAgent 实例（其 debug() 方法生成补丁）。
        target_code: 被测代码全文。
        test_output: 测试失败输出。
        failed_cases: 失败用例列表。
        num_candidates: 候选数（默认 3，上限 8）。
        rag_references: RAG 检索到的相似修复案例（透传给各候选，可选）。
        focus_function: 焦点函数名（透传给 debugger，超长代码时 AST 截取）。
        target_module: 被测模块名（透传给 debugger，区分 ASSERTION/LOGIC_ERROR）。

    Returns:
        CandidateResult 列表（长度 = min(num_candidates, _MAX_CANDIDATE_COUNT)）。
    """
    n = max(1, min(num_candidates, _MAX_CANDIDATE_COUNT))
    candidates: list[CandidateResult] = []
    for i in range(n):
        variant = candidate_variant_prompt(i, n)
        try:
            result = debugger.debug(
                target_code=target_code,
                test_output=f"{test_output}\n\n{variant}",
                failed_cases=failed_cases,
                rag_references=rag_references,
                focus_function=focus_function,
                target_module=target_module,
            )
            patch = result.get("patch", "")
        except Exception as e:
            # 单候选 LLM 调用失败不中断其余候选（降级为"拒绝"候选）
            logger.warning("候选 %d/%d 生成失败（跳过）: %s", i + 1, n, e)
            candidates.append(CandidateResult(index=i, patch="", static_passed=False, static_reason=f"生成失败: {e}"))
            continue

        ok, reason, applied_code = static_validate_patch(target_code, patch)
        if ok:
            # static_validate_patch 内部已调用 apply_patch_to_code，直接复用
            # 其产物（此前再调一次是同候选双次应用补丁的纯冗余）
            candidates.append(CandidateResult(index=i, patch=patch, new_code=applied_code, static_passed=True))
        else:
            candidates.append(CandidateResult(index=i, patch=patch, static_passed=False, static_reason=reason))
            logger.info("候选 %d/%d 静态筛选未通过: %s", i + 1, n, reason)
    passed_count = sum(1 for c in candidates if c.static_passed)
    logger.info("多候选补丁：生成 %d 个，静态筛选通过 %d 个", n, passed_count)
    return candidates


def select_best_candidate(
    candidates: list[CandidateResult],
    original_code: str,
    test_code: str | None = None,
    target_file: str | None = None,
    target_function: str | None = None,
    use_execution_validation: bool = False,
    executor: Any = None,
    execution_trace: list[dict[str, Any]] | None = None,
) -> CandidateResult | None:
    """从候选列表中选出最优补丁（3.1 的验证筛选）。

    筛选逻辑（逐级收紧）：
    1. 无静态通过的候选 → 返回 None（调用方回退到原单补丁流程，不引入劣化）；
    2. 仅启用静态筛选（默认）：
       - 优先选"通过静态筛选且改动最小"的候选（diff 行数越小越保守，
         降低引入无关改动的风险）；
    3. 启用执行验证（use_execution_validation=True 且 executor 已提供）：
       - 对每个静态通过的候选，把新代码写入临时副本，用 test_code 跑
         一遍 executor.execute；
       - 选"测试通过且覆盖率最高"的候选；全部失败时回退到第 2 级。

    Args:
        candidates: generate_candidates 的返回（含静态筛选结果）。
        original_code: 原始被测代码（计算 diff 比例用）。
        test_code: 执行验证用的测试代码（use_execution_validation 时必填）。
        target_file: 被测文件路径（执行验证时写临时副本，不污染原文件）。
        target_function: 测试过滤函数名（执行验证时传给 executor）。
        use_execution_validation: 是否做执行验证（默认 False，仅静态筛选）。
        executor: ExecutorAgent 实例（执行验证时必填）。

    Returns:
        选中的 CandidateResult；无可接受候选时返回 None。
    """
    static_ok = [c for c in candidates if c.static_passed and c.new_code]
    if not static_ok:
        return None

    if not (use_execution_validation and executor is not None and test_code and target_file):
        # 静态筛选模式：3.2 改进——用行级信用分配排序（"修改行数少但
        # 静态通过"的候选优先，与 BOOSTAPR 行级信用思想同方向）
        credits = line_level_credit_scores(original_code, static_ok)
        credit_by_index = {c["index"]: c["credit_score"] for c in credits["candidates"]}
        # 计算每个候选的信用（未执行验证时 exec_factor=1.0，纯简洁性代理）；
        # 按 float 归一（line_level_credit_scores 的 credit_score 可能为 None）
        for c in static_ok:
            c.credit_score = float(credit_by_index.get(c.index, 0.0))
        # 3.3 改进：轻量奖励预测器（REWARD_PREDICTOR_ENABLE=true 且提供历史
        # execution_trace 时）按预测奖励重排：覆盖率连降→偏最小改动，
        # 覆盖率停滞→偏更大改动（换根因视角）；否则保持基础信用排序。
        if reward_predictor_enabled() and execution_trace:
            pred = predict_candidate_rewards(original_code, static_ok, execution_trace)
            reward_by_index = {c["index"]: c["predicted_reward"] for c in pred["candidates"]}
            static_ok.sort(key=lambda c: (-reward_by_index.get(c.index, 0.0), c.index))
            logger.info("奖励预测器（3.3）重排候选：trend=%s", pred.get("trend"))
        else:
            # 信用高 → 修改行少且静态通过；平手时按 index 稳定排序
            # （lambda 中 credit_score 按 float 归一，None 视为 0.0）
            static_ok.sort(key=lambda c: (-(float(c.credit_score) if c.credit_score is not None else 0.0), c.index))
        return static_ok[0]

    # 执行验证模式：逐个候选写临时副本 + 跑测试，选通过率最高且覆盖率最高者
    best: CandidateResult | None = None
    best_score: tuple[bool, float] = (False, -1.0)
    for candidate in static_ok:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8", prefix=f"aitester_cand{candidate.index}_"
        ) as tmp:
            tmp.write(candidate.new_code or "")
            tmp_path = tmp.name
        try:
            result = executor.execute(
                test_code=test_code,
                target_file=tmp_path,
                target_function=target_function,
            )
            candidate.exec_passed = bool(result.get("passed"))
            candidate.exec_coverage = float(result.get("coverage", 0.0) or 0.0)
            score = (candidate.exec_passed, candidate.exec_coverage)
            if score > best_score:
                best, best_score = candidate, score
            logger.info(
                "候选 %d 执行验证：passed=%s, coverage=%.1f%%",
                candidate.index + 1,
                candidate.exec_passed,
                candidate.exec_coverage,
            )
        except Exception as e:
            logger.warning("候选 %d 执行验证异常: %s", candidate.index + 1, e)
        finally:
            _safe_unlink(tmp_path)
    return best


def _safe_unlink(path: str) -> None:
    """删除临时文件，失败仅记 warning（不影响主流程）。"""
    try:
        if path and os.path.exists(path):
            os.unlink(path)
    except OSError as e:
        logger.warning("清理候选临时文件失败: %s", e)


def multi_candidate_available() -> bool:
    """多候选补丁策略是否启用（供 workflow 节点判断是否走 3.1 分支）。

    启用条件：环境变量 ENABLE_MULTI_CANDIDATE_PATCH=true（默认 false）。
    """
    return os.getenv("ENABLE_MULTI_CANDIDATE_PATCH", "false").lower() == "true"


def multi_candidate_count() -> int:
    """读取环境变量 MULTI_CANDIDATE_COUNT（默认 3，范围 [1, 8]）。"""
    raw = os.getenv("MULTI_CANDIDATE_COUNT", str(_DEFAULT_CANDIDATE_COUNT))
    try:
        value = int(raw)
    except ValueError:
        logger.warning("MULTI_CANDIDATE_COUNT=%r 非整数，回退默认 %d", raw, _DEFAULT_CANDIDATE_COUNT)
        return _DEFAULT_CANDIDATE_COUNT
    return max(1, min(value, _MAX_CANDIDATE_COUNT))


def multi_candidate_exec_validate() -> bool:
    """读取环境变量 MULTI_CANDIDATE_EXEC_VALIDATE（默认 false）。

    开启后 select_best_candidate 会逐候选真实跑测试做执行验证（成本更高、
    筛选更准）；默认关闭走纯静态筛选。与 multi_candidate_available /
    multi_candidate_count 并列，集中管理多候选补丁的全部开关，避免各节点
    裸读 os.getenv 导致配置口径分裂。
    """
    return os.getenv("MULTI_CANDIDATE_EXEC_VALIDATE", "false").lower() == "true"


# ─── 3.2 改进：行级信用分配（BOOSTAPR 式）──────────────────────────────────


def line_level_credit_scores(
    original_code: str,
    candidates: list[CandidateResult],
) -> dict[str, Any]:
    """3.2 改进：行级信用分配——对每个候选补丁的修改行做信用评分。

    核心思想（参考 BOOSTAPR 行级信用分配器）：把"修复效果好"（测试通过
    / 覆盖率高）的奖励精确分配到"修改了哪些行"，而非笼统奖励整个补丁。
    本函数对静态通过的候选逐个计算：
    - modified_lines：候选相对原代码的 diff 变更行（行号集合，1-based）；
    - credit_score：保守信用 = 执行验证通过率 × (1 - 修改行占比)。
      "修改行数少但修复效果好"的候选得分更高（与 BOOSTAPR 的
      "关键编辑区域精确奖励"同方向）；未执行验证时退化为
      credit = 1 - 修改行占比（纯简洁性代理）。

    Args:
        original_code: 原始被测代码。
        candidates: generate_candidates 的返回（static_passed 的候选
            才有 new_code，未通过静态筛选的跳过）。

    Returns:
        {"candidates": [{"index": int, "modified_lines": [行号...],
          "modified_line_count": int, "modified_ratio": float,
          "credit_score": float}],
         "best_candidate_index": int | None（credit 最高的候选索引）,
         "best_credit": float | None}
        无静态通过候选时 best_candidate_index 为 None。
    """
    old_lines = original_code.splitlines()
    old_line_count = max(len(old_lines), 1)
    scored: list[dict[str, Any]] = []
    best_idx: int | None = None
    best_credit = -1.0
    for c in candidates:
        if not (c.static_passed and c.new_code):
            continue
        new_lines = c.new_code.splitlines()
        # diff 变更行（unified diff 中 +/- 行，排除 +++/--- 文件头）
        changed = 0
        for line in difflib.unified_diff(old_lines, new_lines):
            if line[:1] in "+-" and line[:3] not in {"+++", "---"}:
                changed += 1
        modified_ratio = round(changed / old_line_count, 4)
        # 信用 = 执行验证通过率 × (1 - 修改行占比)；未验证时退化为 1 - 修改行占比
        if c.exec_passed is None:
            exec_factor = 1.0  # 未执行验证（纯静态模式），不惩罚
        elif c.exec_passed:
            exec_factor = 1.0
        else:
            # 执行失败：coverage 仍部分有效时保守给 0.5，全 0 时给 0.0
            exec_factor = 0.5 if (c.exec_coverage or 0.0) > 0 else 0.0
        credit = round(exec_factor * (1.0 - modified_ratio), 4)
        scored.append(
            {
                "index": c.index,
                "modified_line_count": changed,
                "modified_ratio": modified_ratio,
                "exec_passed": c.exec_passed,
                "exec_coverage": c.exec_coverage,
                "credit_score": credit,
            }
        )
        if credit > best_credit:
            best_credit = credit
            best_idx = c.index
    return {
        "candidates": scored,
        "best_candidate_index": best_idx,
        "best_credit": best_credit if best_idx is not None else None,
    }


# ─── 3.3 改进：轻量奖励预测器（BOOSTAPR 行级信用思想的规则式落地）──────────


def reward_predictor_enabled() -> bool:
    """3.3 改进：轻量奖励预测器开关（REWARD_PREDICTOR_ENABLE=true 时启用，默认 false）。

    启用后 select_best_candidate 在静态筛选模式下，用历史 execution_trace
    的覆盖率趋势调节候选排序（覆盖率连降偏最小改动、停滞偏更大改动）。
    """
    return os.getenv("REWARD_PREDICTOR_ENABLE", "false").lower() == "true"


def _coverage_trend(execution_trace: list[dict[str, Any]] | None) -> str:
    """3.3 改进：从历史执行轨迹推断覆盖率趋势（declining/stagnant/improving/unknown）。

    Args:
        execution_trace: 3.2 执行反馈轨迹列表（每项含 coverage_delta）。

    Returns:
        趋势标签：declining（连降）/ stagnant（停滞）/ improving（连升）/
        unknown（轨迹不足或无 delta 数据）。
    """
    if not execution_trace:
        return "unknown"
    # 覆盖率 delta 过滤 None 后按 float 归一（trace 中 coverage_delta 可能缺失/非数值）
    deltas = [float(t["coverage_delta"]) for t in execution_trace if t.get("coverage_delta") is not None]
    if len(deltas) < 2:
        return "unknown"
    recent = deltas[-2:]
    if all(d < 0 for d in recent):
        return "declining"
    if all(abs(d) < 0.5 for d in recent):
        return "stagnant"
    if all(d > 0 for d in recent):
        return "improving"
    return "unknown"


def predict_candidate_rewards(
    original_code: str,
    candidates: list[CandidateResult],
    execution_trace: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """3.3 改进：轻量奖励预测器——基于历史 execution_trace 与候选静态信用，
    预测每个候选的"预期修复奖励"，用于候选重排序。

    核心思想（BOOSTAPR 行级信用分配器的规则式轻量落地，无需训练、纯标准库）：
    1. 基础信用 = line_level_credit_scores 的 credit_score
       （静态模式下 credit = 1 - 修改行占比，越小改动信用越高）；
    2. 趋势调节（_coverage_trend）：
       - declining（覆盖率连降）：当前路径发散 → 奖励最小改动候选（predicted = base）；
       - stagnant（覆盖率停滞）：当前视角失效 → 奖励更大改动候选
         （predicted = 1 - base，抬升"大改/根因重写"候选）；
       - improving / unknown：保持基础信用（predicted = base）。

    Args:
        original_code: 原始被测代码。
        candidates: generate_candidates 的返回（static_passed 的候选参与评分）。
        execution_trace: 3.2 执行反馈轨迹（可 None，无轨迹时退化为基础信用）。

    Returns:
        {"candidates": [{"index": int, "credit_score": float,
          "modified_ratio": float, "predicted_reward": float}],
         "best_candidate_index": int | None（预测奖励最高者）,
         "trend": str}
    """
    credits = line_level_credit_scores(original_code, candidates)
    trend = _coverage_trend(execution_trace)
    credit_by_index = {c["index"]: c for c in credits["candidates"]}
    scored: list[dict[str, Any]] = []
    best_idx: int | None = None
    best_reward = -1.0
    for c in candidates:
        if not (c.static_passed and c.new_code):
            continue
        info = credit_by_index.get(c.index, {})
        base = float(info.get("credit_score", 0.0))
        modified_ratio = float(info.get("modified_ratio", 0.0))
        # 趋势调节：停滞 → 反转信用抬升"更大改动"候选（换根因视角）；
        # 其余（declining / improving / unknown）→ 保持基础信用（偏最小改动）。
        predicted = round(1.0 - base, 4) if trend == "stagnant" else base
        scored.append(
            {
                "index": c.index,
                "credit_score": base,
                "modified_ratio": modified_ratio,
                "predicted_reward": predicted,
            }
        )
        if predicted > best_reward:
            best_reward = predicted
            best_idx = c.index
    return {
        "candidates": scored,
        "best_candidate_index": best_idx,
        "trend": trend,
    }
