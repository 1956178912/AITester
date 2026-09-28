"""
并行专家 Agent 池（Parallel Expert Pool，默认关）。

背景（P2 并行专家协作方向：从"串行图"走向"并行专家协作"）：
    当前工作流拓扑全串行（planner → generator → executor → debugger →
    patch_applier → executor），修复吞吐受限于单 LLM 调用链。2026 年
    K11tech（14 专家 Agent + 7 MCP 服务器）与 Anthropic Code Review
    （多 Agent 分别搜索不同缺陷类别 + 相互验证）等系统验证了并行专家
    池 + 交叉验证的准确率与吞吐收益。

    本模块提供**并行专家池 + 交叉验证边**的最小骨架（默认关，
    历史串行拓扑零变化）：
    - `ExpertPoolAgent`：并发调用 N 个专家子 Agent（各聚焦一个修复维度，
      如 "边界处理" / "类型安全" / "死代码"），汇总各自产出的候选补丁；
    - `cross_validate`：对 N 个候选做两两一致性投票（"哪些候选被多数专家
      同意"），过滤误报候选（Anthropic Code Review 同口径），按
      "被验证数 + 严重度"排序；
    - 与现有 `multi_candidate.py`（同一 Agent 生成 N 候选 + 静态筛选）正交：
      multi_candidate 是"同策略多采样"，expert_pool 是"多策略并行 + 交叉
      验证"，二者可叠加但默认都关。

设计约束（与 ADR-0003 默认关 + ADR-0004 零默认依赖口径一致）：
    - `EXPERT_POOL_ENABLE=false`（默认）时，本模块零行为变化：
      工作流拓扑零改动，_debugger_node 不走专家池路径；
    - 专家池用 `concurrent.futures.ThreadPoolExecutor`（N 个专家 LLM 调用
      并发，互不阻塞），线程数 = 专家数（默认 3，EXPERT_POOL_SIZE 可调）；
    - 每个专家的 prompt 聚焦一个维度（_EXPERT_DIMENSIONS 常量表），
      产出候选补丁 + 置信度；
    - 交叉验证是**纯静态投票**（候选 patch 文本的 AST 归一化 + 多数同意
      判定），零额外 LLM 成本；
    - 降级：专家池故障（线程池异常 / 全专家失败）时，保守回退到
      历史单补丁路径（multi_candidate 或单候选），不阻断修复。

使用方式（_debugger_node 集成）：
    from src.graph.expert_pool import ExpertPoolAgent, expert_pool_enabled

    if expert_pool_enabled():
        pool = ExpertPoolAgent()
        candidates = pool.generate_parallel(target_code, test_output, failed_cases)
        verified = pool.cross_validate(candidates)
        # 把 verified（排序后的候选）传给 multi_candidate.select_best_candidate
        # 或直接取 verified[0] 作为最优候选
"""

from __future__ import annotations

import ast
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any

logger = logging.getLogger(__name__)

# 专家维度常量表（默认 3 个维度，EXPERT_POOL_SIZE 可调）：
# 每个专家聚焦一个修复维度，避免"全维度单专家"的盲区
_EXPERT_DIMENSIONS: tuple[str, ...] = (
    "boundary_handling",  # 边界条件（空列表 / 除零 / 负数 / 溢出）
    "type_safety",  # 类型一致（重赋值 / 容器混用 / 返回类型）
    "dead_code_and_logic",  # 死代码 / 逻辑错误（不可达分支 / 恒假条件）
)


def expert_pool_enabled() -> bool:
    """专家池开关（EXPERT_POOL_ENABLE=true 时启用，默认 false）。"""
    return os.getenv("EXPERT_POOL_ENABLE", "false").lower() == "true"


def _expert_pool_size() -> int:
    """专家池大小（EXPERT_POOL_SIZE，默认 3，范围 [1, 7]）。"""
    try:
        n = int(os.getenv("EXPERT_POOL_SIZE", "3"))
    except ValueError:
        n = 3
    return max(1, min(n, 7))


def _expert_timeout_seconds() -> int:
    """单专家 LLM 调用超时（EXPERT_POOL_TIMEOUT，默认 120s，范围 [30, 600]）。"""
    try:
        n = int(os.getenv("EXPERT_POOL_TIMEOUT", "120"))
    except ValueError:
        n = 120
    return max(30, min(n, 600))


def _normalize_patch_for_voting(patch: str) -> str:
    """AST 归一化补丁文本（去空白 + 排序语句，供交叉验证投票用）。

    保守口径：仅做 AST 级归一化（忽略注释 / 空白差异），不做语义等价
    判定（那需要 LLM，超出本模块零成本约束）。归一化失败时返回原文
    （保守：无法归一化的补丁仍参与投票，不误杀）。
    """
    if not patch:
        return ""
    # 提取 ```python 代码块（与 base_agent._extract_python_code 同口径）
    code = patch
    if "```" in patch:
        import re

        m = re.search(r"```(?:python)?\s*\n(.*?)```", patch, re.DOTALL)
        if m:
            code = m.group(1)
    try:
        tree = ast.parse(code)
        # 归一化：把每个顶层语句 AST dump 成稳定字符串（忽略行号 / 注释）
        normalized = "\n".join(
            sorted(ast.dump(stmt, annotate_fields=True) for stmt in tree.body if not isinstance(stmt, ast.Expr))
        )
        return normalized or ast.dump(tree, annotate_fields=True)
    except SyntaxError:
        return code  # 归一化失败 → 保守用原文参与投票


class ExpertPoolAgent:
    """并行专家 Agent 池：N 个专家子 Agent 并发产出候选 + 交叉验证投票。

    属性:
        expert_count: 专家数（默认 3，EXPERT_POOL_SIZE 可调，[1,7]）。
    """

    def __init__(self) -> None:
        self.expert_count = _expert_pool_size()

    def generate_parallel(
        self,
        target_code: str,
        test_output: str,
        failed_cases: list[dict[str, str]],
        rag_references: list[dict[str, Any]] | None = None,
        focus_function: str | None = None,
    ) -> list[dict[str, Any]]:
        """并发调用 N 个专家子 Agent，汇总候选补丁。

        每个专家聚焦一个维度（_EXPERT_DIMENSIONS 前 expert_count 个），
        产出候选补丁 + 置信度。线程池并发（互不阻塞），异常专家
        保守降级（产出空候选，不影响其他专家）。

        Args:
            target_code: 被测代码全文。
            test_output: pytest 失败输出。
            failed_cases: 失败用例列表。
            rag_references: RAG 参考案例（可选，注入各专家 prompt）。
            focus_function: 焦点函数名（可选）。

        Returns:
            候选列表，每项含 {"dimension": str, "patch": str, "confidence": float,
            "expert_failed": bool}（expert_failed=True 时 patch 为空串）。
        """
        if not target_code:
            return []
        # 取前 expert_count 个维度（expert_count > len(_EXPERT_DIMENSIONS) 时
        # 循环复用维度表，保守：不新增维度，仅重复已有维度）
        dimensions = list(_EXPERT_DIMENSIONS[: self.expert_count])
        if len(dimensions) < self.expert_count:
            dimensions += list(_EXPERT_DIMENSIONS) * (
                (self.expert_count - len(dimensions)) // len(_EXPERT_DIMENSIONS) + 1
            )
            dimensions = dimensions[: self.expert_count]

        # 并发调用各专家（ThreadPoolExecutor，线程数 = 专家数）
        candidates: list[dict[str, Any]] = [None] * self.expert_count  # type: ignore[list-item]
        timeout_s = _expert_timeout_seconds()

        def _run_expert(idx: int, dimension: str) -> None:
            # 专家聚焦单一维度：注入维度标签 + 全量上下文（target_code / test_output /
            # failed_cases / rag_references），让 LLM 按该维度产出候选补丁。
            # 实现口径（保守、零新依赖）：复用 DebuggerAgent.debug 的 prompt 构建
            # 路径（不重复 LLM prompt 工程），仅把维度标签追加到 system prompt
            # 尾部（_EXPERT_DIMENSION_PROMPT_HINTS 常量表）。
            try:
                from src.agents.debugger import DebuggerAgent

                agent = DebuggerAgent()
                # 把维度标签注入 target_code 尾部（保守：不改 agent.debug 签名，
                # 仅在 prompt 构建路径的 target_code 参数里追加维度提示）
                dimension_hint = _EXPERT_DIMENSION_PROMPT_HINTS.get(dimension, "")
                enriched_code = f"{target_code}\n\n{dimension_hint}" if dimension_hint else target_code
                result = agent.debug(
                    target_code=enriched_code,
                    test_output=test_output,
                    failed_cases=failed_cases,
                    rag_references=rag_references,
                    focus_function=focus_function,
                    temperature=0.3,  # 专家维度聚焦：比默认温度低（收紧发散）
                )
                candidates[idx] = {
                    "dimension": dimension,
                    "patch": result.get("patch") or "",
                    "confidence": 0.5,  # 专家无内置置信度评估，保守置 0.5
                    "expert_failed": False,
                }
            except Exception as e:
                logger.warning("专家 %d（维度=%s）产出候选失败（保守降级为空候选）: %s", idx, dimension, e)
                candidates[idx] = {"dimension": dimension, "patch": "", "confidence": 0.0, "expert_failed": True}

        with ThreadPoolExecutor(max_workers=self.expert_count, thread_name_prefix="expert_pool") as pool:
            futures = [pool.submit(_run_expert, i, dim) for i, dim in enumerate(dimensions)]
            # 带超时等待（避免单专家卡死拖垮整池）
            import concurrent.futures as cf

            try:
                cf.wait(futures, timeout=timeout_s)
            except cf.TimeoutError:
                logger.warning("专家池等待超时（%ds），未完成专家保守降级为空候选", timeout_s)
        # 填充未完成的槽位（保守：expert_failed=True 的空候选）
        for i, fut in enumerate(futures):
            if not fut.done():
                candidates[i] = {"dimension": dimensions[i], "patch": "", "confidence": 0.0, "expert_failed": True}
        return [c for c in candidates if c is not None]

    def cross_validate(self, candidates: list[dict[str, Any]], min_agreement: int = 2) -> list[dict[str, Any]]:
        """交叉验证：对候选做两两一致性投票（AST 归一化 + 多数同意）。

        投票口径（保守、零 LLM 成本）：
        - 把每个候选的 patch 文本 AST 归一化（_normalize_patch_for_voting）；
        - 两两比对归一化文本，完全一致 / 子串包含关系视为"同意"；
        - 候选的"被验证数" = 同意它的其他候选数（含自身）；
        - 按 (被验证数, 置信度) 降序排序，过滤被验证数 < min_agreement 的候选
          （"误报"过滤，Anthropic Code Review 同口径）。

        Args:
            candidates: generate_parallel 产出的候选列表。
            min_agreement: 最小同意数（默认 2 = 至少 1 个其他专家同意，
                1 = 不投票仅按置信度排序）。

        Returns:
            排序后的候选列表（每项追加 "verified_count" / "agreed_dimensions" 字段）。
        """
        valid = [c for c in candidates if not c.get("expert_failed") and c.get("patch")]
        if not valid:
            return []
        # AST 归一化每个候选
        normalized = [(c, _normalize_patch_for_voting(c["patch"])) for c in valid]
        # 两两投票（O(N²)，N ≤ 7 可接受）
        for i, (c, norm_i) in enumerate(normalized):
            agreed = [i]
            for j, (_, norm_j) in enumerate(normalized):
                if i == j:
                    continue
                if _patches_agree(norm_i, norm_j):
                    agreed.append(j)
            c["verified_count"] = len(agreed)
            c["agreed_dimensions"] = [normalized[k][0]["dimension"] for k in agreed]
        # 过滤 + 排序（被验证数 + 置信度 降序）
        filtered = [c for c in valid if c.get("verified_count", 0) >= min_agreement]
        filtered.sort(key=lambda c: (c.get("verified_count", 0), c.get("confidence", 0.0)), reverse=True)
        return filtered


def _patches_agree(norm_a: str, norm_b: str) -> bool:
    """两个归一化补丁文本是否"同意"（完全一致 / 一方是另一方子串）。"""
    if not norm_a or not norm_b:
        return False
    if norm_a == norm_b:
        return True
    # 子串包含（短补丁被长补丁覆盖 = 同意，保守口径）
    shorter, longer = (norm_a, norm_b) if len(norm_a) <= len(norm_b) else (norm_b, norm_a)
    return len(shorter) > 10 and shorter in longer


# 专家维度 → prompt 提示（追加到 target_code 尾部，引导 LLM 按维度聚焦）
_EXPERT_DIMENSION_PROMPT_HINTS: dict[str, str] = {
    "boundary_handling": (
        "\n\n【专家维度：边界处理】请优先检查：空列表 / 空字符串 / 除零 / 负数 / 溢出 / None 输入，"
        "针对这些边界场景生成更精确的断言与修复。"
    ),
    "type_safety": (
        "\n\n【专家维度：类型安全】请优先检查：类型重赋值 / 容器混用 / 返回类型不一致 / "
        "鸭子类型误用，生成类型收紧的修复补丁。"
    ),
    "dead_code_and_logic": (
        "\n\n【专家维度：死代码与逻辑错误】请优先检查：不可达分支 / 恒假条件 / 死代码 / "
        "逻辑倒置，生成移除死代码 + 修正逻辑的修复补丁。"
    ),
}


__all__ = [
    "ExpertPoolAgent",
    "expert_pool_enabled",
]
