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
import time
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

# P2-2（2026-10 批次）：错误类别 → 优先维度 映射表。
# 背景：此前 3 维度固定（边界/类型/死代码），不随 error_category 变化——
# 对 type_error 任务仍派"边界处理"专家（维度错位，候选命中率低）。
# 现按 ErrorCategory 映射到维度子集：命中类别把关联维度排前、其余维度补位
# （保持 expert_count 不变，只重排序不增删，零新 LLM 成本、零行为默认变化）。
# EXPERT_POOL_CATEGORY_CONDITIONED=true（默认 false，历史口径 3 维固定）时
# generate_parallel 接受 error_category 参数并重排维度。
# 映射口径（保守，缺类别/未知类别 → 原序 3 维，等价历史行为）：
_ERROR_CATEGORY_TO_PRIORITY_DIMENSION: dict[str, str] = {
    "type_error": "type_safety",
    "index_error": "boundary_handling",
    "assertion": "dead_code_and_logic",
    "logic_error": "dead_code_and_logic",
    "runtime": "boundary_handling",
    "import_error": "type_safety",  # 导入失败多为 API/类型误用
    "syntax": "dead_code_and_logic",
    "unknown": "dead_code_and_logic",
}


def _category_conditioned() -> bool:
    """P2-2 维度条件化开关（EXPERT_POOL_CATEGORY_CONDITIONED=true 时启用，默认关）。"""
    return os.getenv("EXPERT_POOL_CATEGORY_CONDITIONED", "false").lower() in ("true", "1", "on")


def _dimensions_for_category(error_category: str | None, count: int) -> list[str]:
    """P2-2：按 error_category 重排维度（命中类别关联维度排前，其余补位）。

    开关 OFF（默认）或 error_category 为空/未知 → 返回原序 _EXPERT_DIMENSIONS
    前 count 个（与历史固定 3 维口径一致，零行为变化）。
    开关 ON 且类别命中映射表 → 命中维度排前 + 其余维度按原序补位到 count。
    """
    base = list(_EXPERT_DIMENSIONS)
    if not _category_conditioned() or not error_category:
        return _take_n(base, count)
    top = _ERROR_CATEGORY_TO_PRIORITY_DIMENSION.get(error_category)
    if top is None or top not in base:
        return _take_n(base, count)  # 未知类别 → 保守回退原序
    ordered = [top] + [d for d in base if d != top]
    return _take_n(ordered, count)


def _take_n(dimensions: list[str], n: int) -> list[str]:
    """取前 n 个维度（不足时循环复用，与原 generate_parallel 补位口径一致）。"""
    if n <= 0 or not dimensions:
        return []
    out = list(dimensions[:n])
    if len(out) < n:
        cycles = (n - len(out)) // len(dimensions) + 1
        out += list(dimensions) * cycles
    return out[:n]


# ─── LLM 温度 / 候选置信度常量（2026 可读性审查 P3：抽取历史内联魔法数字）──
# 此前 0.3/0.2 温度与 0.5/0.6 置信度散落内联在 generate_parallel._run_expert
# 与 debate_round 的 LLM 调用点，无命名、无环境变量口径（对比同文件其他参数
# 均经 expert_pool_enabled / _debate_top_k 等函数读环境变量）。收拢为命名常量，
# 便于实验复用与一致性审阅（值保持历史口径不变）。
_EXPERT_TEMPERATURE: float = 0.3  # 单专家候选温度（比默认 0.7 低，收紧维度聚焦）
_DEBATE_TEMPERATURE: float = 0.2  # 辩论修订温度（修订候选需低温收敛，避免发散）
_EXPERT_BASE_CONFIDENCE: float = 0.5  # 单专家候选基线置信度（专家无内置评估，保守值）
_DEBATE_REVISED_CONFIDENCE: float = 0.6  # 辩论修订候选置信度（保守略高于单候选基线）


def expert_pool_enabled() -> bool:
    """专家池开关（EXPERT_POOL_ENABLE=true 时启用，默认 false）。"""
    return os.getenv("EXPERT_POOL_ENABLE", "false").lower() == "true"


def expert_pool_debate_enabled() -> bool:
    """G6 多 Agent 辩论修复开关（EXPERT_POOL_DEBATE_ENABLE=true 时启用，默认 false）。

    在 expert_pool_enabled() 的基础上叠加辩论收敛轮次（cross_validate 之后
    的"互辩修订"），进一步收敛候选补丁。默认关时本方法恒 False，
    历史 cross_validate 口径零变化。
    """
    if not expert_pool_enabled():
        return False
    return os.getenv("EXPERT_POOL_DEBATE_ENABLE", "false").lower() == "true"


def _debate_top_k() -> int:
    """辩论收敛的 top-K（EXPERT_POOL_DEBATE_TOP_K，默认 2，范围 [2, 4]）。"""
    try:
        n = int(os.getenv("EXPERT_POOL_DEBATE_TOP_K", "2"))
    except ValueError:
        n = 2
    return max(2, min(n, 4))


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
        error_category: str | None = None,
    ) -> list[dict[str, Any]]:
        """并发调用 N 个专家子 Agent，汇总候选补丁。

        每个专家聚焦一个维度（_EXPERT_DIMENSIONS 前 expert_count 个），
        产出候选补丁 + 置信度。线程池并发（互不阻塞），异常专家
        保守降级（产出空候选，不影响其他专家）。

        P2-2（2026-10 批次）：error_category 参数（默认 None 保持历史口径）
        —— EXPERT_POOL_CATEGORY_CONDITIONED=true 且 error_category 非空时，
        按 _ERROR_CATEGORY_TO_PRIORITY_DIMENSION 把关联维度排前（命中维度
        优先），其余维度按原序补位（expert_count 不变，只重排序不增删）。
        开关 OFF 或 error_category=None 时，本参数零作用（维度表固定原序）。

        Args:
            target_code: 被测代码全文。
            test_output: pytest 失败输出。
            failed_cases: 失败用例列表。
            rag_references: RAG 参考案例（可选，注入各专家 prompt）。
            focus_function: 焦点函数名（可选）。
            error_category: 错误类别字符串（ErrorCategory.value，如
                "type_error" / "index_error"，可选；None 时维度表固定原序）。

        Returns:
            候选列表，每项含 {"dimension": str, "patch": str, "new_code":
            str | None, "confidence": float, "expert_failed": bool}
            （expert_failed=True 时 patch 为空串、new_code 为 None）。
            new_code（2026-09-30 审查补充）：补丁应用后的完整代码——
            _debugger_node 多解合成按 CandidateResult 契约消费（new_code
            参与 AST 区域 diff）；apply 失败时为 None，调用侧兜底。
        """
        if not target_code:
            return []
        # P2-2：维度选择（默认固定原序；EXPERT_POOL_CATEGORY_CONDITIONED=true
        # 且 error_category 命中映射表时按类别重排，命中维度排前）
        dimensions = _dimensions_for_category(error_category, self.expert_count)

        # 并发调用各专家（ThreadPoolExecutor，线程数 = 专家数）
        candidates: list[dict[str, Any]] = [None] * self.expert_count  # type: ignore[list-item]
        timeout_s = _expert_timeout_seconds()

        # C8（2026-10-05 系统审查 P0）：任务级记账实例跨线程传播。
        # token_usage / cost_budget 均为线程局部——工作线程不绑定时，专家池
        # 的 LLM 调用记到孤儿线程上（任务统计失真 + 预算上限被绕过）。
        # 提交前捕获本任务（提交线程）的两个累计器实例，_run_expert 在
        # 工作线程内 attach 到同实例，记账/预算作用域跟随任务。
        from src.budget.cost_budget import attach_budget, current_budget
        from src.budget.token_usage import attach_usage, get_usage

        _task_usage = get_usage()
        _task_budget = current_budget()

        def _run_expert(idx: int, dimension: str) -> None:
            # C8：工作线程记账绑定（同实例可变共享，字段读改写由各模块锁保护）
            attach_usage(_task_usage)
            attach_budget(_task_budget)
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
                    temperature=_EXPERT_TEMPERATURE,  # 专家维度聚焦：比默认温度低（收紧发散）
                )
                _patch_expert = result.get("patch") or ""
                from src.tools.patch_applier import apply_patch_to_code as _apply_patch_expert

                _exp_code, _exp_applied = _apply_patch_expert(target_code, _patch_expert)
                candidates[idx] = {
                    "dimension": dimension,
                    # 合成口径（2026-09-30 审查修复）：_debugger_node 多解合成
                    # 按 CandidateResult 契约消费候选——patch=补丁文本、
                    # new_code=应用后的完整代码。补丁应用失败时 new_code=None
                    # （调用侧经 static_validate_patch 兜底判定，不劣化）。
                    "new_code": _exp_code if _exp_applied else None,
                    "patch": _patch_expert,
                    "confidence": _EXPERT_BASE_CONFIDENCE,  # 专家无内置置信度评估，保守基线
                    "expert_failed": False,
                }
            except Exception as e:
                logger.warning("专家 %d（维度=%s）产出候选失败（保守降级为空候选）: %s", idx, dimension, e)
                candidates[idx] = {
                    "dimension": dimension,
                    "patch": "",
                    # 与成功路径同口径携带 new_code 键（失败 = None，调用侧
                    # static_validate_patch 兜底判定）
                    "new_code": None,
                    "confidence": 0.0,
                    "expert_failed": True,
                }

        # 2026-10-01 全面审查 P1 修复：此前用 cf.wait(futures, timeout) +
        # except cf.TimeoutError 做超时保护——但 concurrent.futures.wait 从不
        # 抛 TimeoutError（它返回 (done, not_done) 集合），该 except 是死代码；
        # 且 `with ThreadPoolExecutor` 块退出时 shutdown(wait=True) 仍会阻塞等
        # 所有 future（含挂死的那个），"填充未完成槽位"循环永不触发。净效果：
        # 单专家 LLM 挂死 = 整池 + 整轮 debugger + 整图卡死，EXPERT_POOL_TIMEOUT
        # 完全失效（与文档"带超时等待避免单专家拖住整池"直接矛盾）。
        # 现改为：不用 with 块（避免 shutdown(wait=True) 阻塞），逐个
        # fut.result(timeout=remaining) 等待（Future.result 才会抛
        # concurrent.futures.TimeoutError——注意是 future 级异常而非
        # cf.TimeoutError 类型），超时的 future 保守降级为空候选（专家线程
        # 后台继续跑但不再阻塞主流程；线程是守护线程，进程退出时自然终止）。
        # 挂死专家的 _run_expert 异常分支仍会写 candidates[idx]（线程内写，
        # 主流程已跳过——保守口径：主流程不再等它，已写到的值也不读）。
        pool = ThreadPoolExecutor(max_workers=self.expert_count, thread_name_prefix="expert_pool")
        futures = [pool.submit(_run_expert, i, dim) for i, dim in enumerate(dimensions)]
        import concurrent.futures as cf

        start = time.monotonic()
        timed_out = False
        for i, fut in enumerate(futures):
            remaining = timeout_s - (time.monotonic() - start)
            if remaining <= 0:
                timed_out = True
                break
            try:
                fut.result(timeout=remaining)
            except cf.TimeoutError:
                timed_out = True
                logger.warning(
                    "专家池等待超时（%.1fs），专家 %d 起未完成专家保守降级为空候选",
                    timeout_s,
                    i,
                )
                break
            except Exception as e:
                # _run_expert 内部已捕获全部异常，这里仅防御性兜底
                logger.warning("专家 %d 线程异常（保守降级为空候选）: %s", i, e)
        if timed_out:
            # 未完成的槽位保守降级（含已 break 时剩余 futures 全部）
            for j in range(len(futures)):
                if candidates[j] is None:
                    candidates[j] = {
                        "dimension": dimensions[j],
                        "patch": "",
                        "new_code": None,  # 与成功路径同口径（失败 = None）
                        "confidence": 0.0,
                        "expert_failed": True,
                    }
        # 不阻塞 shutdown（wait=False）：挂死专家的线程后台自然终止，
        # 主流程立即返回（避免 with 块退出时的 shutdown(wait=True) 卡死）。
        pool.shutdown(wait=False)
        return [c for c in candidates if c is not None]

    def cross_validate(self, candidates: list[dict[str, Any]], min_agreement: int = 2) -> list[dict[str, Any]]:
        """交叉验证：对候选做两两一致性投票（AST 归一化 + 多数同意）。

        投票口径（保守、零 LLM 成本）：
        - 把每个候选的 patch 文本 AST 归一化（_normalize_patch_for_voting）；
        - 两两比对归一化文本，完全一致 / 子串包含关系视为"同意"；
        - 候选的"被验证数" = 同意它的其他候选数（含自身）；
        - 按 (被验证数, 置信度) 降序排序，过滤被验证数 < min_agreement 的候选
          （"误报"过滤，Anthropic Code Review 同口径）。

        O5（2026-09-29 审查 P1）：置信度由可验证信号派生——此前所有候选
        confidence 恒为 _EXPERT_BASE_CONFIDENCE（0.5），投票仅按
        verified_count 排序、confidence 并列无区分度。现按可验证信号
        重新计算：
        - 基线 = _EXPERT_BASE_CONFIDENCE（历史口径）；
        - + 0.1 × min(verified_count - 1, 3)（被更多专家验证 → 更高置信度，
          封顶 3 防饱和）；
        - + 0.05（patch 长度 ≥ 200 字符 → 实质性修复，非空壳）；
        - - 0.1（patch 含"TODO"/"FIXME"/"HACK" → 未完成标记，保守降权）；
        - 结果 clip 到 [0.0, 1.0]。
        历史基线（verified_count=0、无 TODO、patch 短）= 0.5，不变。
        默认关时（EXPERT_POOL_ENABLE=false）本方法不被调用，历史口径不变。

        Args:
            candidates: generate_parallel 产出的候选列表。
            min_agreement: 最小同意数（默认 2 = 至少 1 个其他专家同意，
                1 = 不投票仅按置信度排序）。

        Returns:
            排序后的候选列表（每项追加 "verified_count" / "agreed_dimensions"
            / "confidence"（O5 可验证信号派生）字段）。
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
            # O5（2026-09-29 审查 P1）：可验证信号派生置信度
            _o5_conf = _EXPERT_BASE_CONFIDENCE
            _o5_conf += 0.1 * min(c["verified_count"] - 1, 3)
            _o5_patch_text = c.get("patch", "")
            if len(_o5_patch_text) >= 200:
                _o5_conf += 0.05
            if any(marker in _o5_patch_text for marker in ("TODO", "FIXME", "HACK")):
                _o5_conf -= 0.1
            c["confidence"] = round(max(0.0, min(1.0, _o5_conf)), 4)
        # 过滤 + 排序（被验证数 + 置信度 降序）
        filtered = [c for c in valid if c.get("verified_count", 0) >= min_agreement]
        filtered.sort(key=lambda c: (c.get("verified_count", 0), c.get("confidence", 0.0)), reverse=True)
        return filtered

    def debate_round(
        self,
        verified: list[dict[str, Any]],
        target_code: str,
        test_output: str,
        failed_cases: list[dict[str, str]],
        focus_function: str | None = None,
    ) -> list[dict[str, Any]]:
        """G6 多 Agent 辩论收敛轮次（EXPERT_POOL_DEBATE_ENABLE=true 时调用，默认关）。

        在 cross_validate 的投票结果之上，对 top-K 候选做"互辩修订"：
        把 top-K 候选的维度标签 + 补丁文本拼成一个"辩论上下文"，
        让 LLM 在已知"哪些候选被哪些专家同意"的前提下，产出一个
        综合修订版候选（吸收 top-K 的共性修复点，规避各自的弱点）。
        修订候选非空时直接插入排序结果首位（修订候选优先级最高），
        不再要求与 top-K 重新投票（修订版是"综合版"，投票口径不适用）。

        设计口径（保守、零额外 LLM 成本约束的例外）：
            - 本方法是**可选增强**（EXPERT_POOL_DEBATE_ENABLE=true 时
              才走辩论路径，默认关时历史 cross_validate 口径零变化）；
            - 辩论只取 top-K（默认 2）候选，K 个候选互相可见
              对方的维度标签与补丁摘要，避免无界讨论；
            - 修订候选 LLM 失败 / 空补丁时保守降级：返回原 verified
              列表不变（不引入劣化）；
            - 修订候选标注 "debate_revise": True，供下游报告 / 实验
              分析区分"投票胜出"与"辩论修订"两种来源。

        Args:
            verified: cross_validate 排序后的候选列表（每项含 dimension /
                patch / confidence / verified_count / agreed_dimensions）。
            target_code: 被测代码全文。
            test_output: pytest 失败输出。
            failed_cases: 失败用例列表。
            focus_function: 焦点函数名（可选）。

        Returns:
            修订后的候选列表（修订候选插入首位 + 原 verified 候选），
            每项含 "debate_revise" 布尔标记（True = 辩论修订候选，
            False = 原投票候选）。
        """
        from src.agents.debugger import DebuggerAgent

        if not verified:
            return []
        top_k = _debate_top_k()
        top_candidates = verified[:top_k]
        if len(top_candidates) < 2:
            # top-K 不足 2 个时无法互辩（单候选无"弱点反馈"对象），
            # 保守降级：原样返回（不触发 LLM 修订调用，避免无意义成本）
            return [{**c, "debate_revise": False} for c in verified]

        # 构建辩论上下文：top-K 候选的维度标签 + 补丁摘要（截断防 prompt 爆炸）
        debate_hints: list[str] = []
        for c in top_candidates:
            patch_text = str(c.get("patch") or "")
            if len(patch_text) > 800:
                patch_text = patch_text[:800] + "…[truncated]"
            debate_hints.append(
                f"【候选 {c.get('dimension')}】（被 {c.get('verified_count')} 个专家同意）\n{patch_text}"
            )
        debate_context = (
            "\n\n【多 Agent 辩论收敛】以下是交叉验证后的 top "
            f"{len(top_candidates)} 候选（每个候选由不同专家维度产出）。"
            "请综合分析这些候选的共性修复点与各自弱点，产出一个**综合修订版**补丁："
            "吸收各候选的正确修复逻辑，规避其错误假设与冗余改动，"
            "仅输出修订后的完整补丁代码（markdown 代码块包裹）。"
        )
        enriched_code = f"{target_code}\n\n{debate_context}\n\n" + "\n\n".join(debate_hints)

        try:
            agent = DebuggerAgent()
            result = agent.debug(
                target_code=enriched_code,
                test_output=test_output,
                failed_cases=failed_cases,
                focus_function=focus_function,
                temperature=_DEBATE_TEMPERATURE,  # 辩论修订：低温收紧（综合版不应发散）
            )
            revise_patch = (result.get("patch") or "").strip()
        except Exception as e:
            logger.warning("辩论修订 LLM 调用失败（保守降级为原 verified 列表）: %s", e)
            return [{**c, "debate_revise": False} for c in verified]

        if not revise_patch:
            return [{**c, "debate_revise": False} for c in verified]

        revise_candidate = {
            "dimension": "debate_revise",
            "patch": revise_patch,
            "confidence": _DEBATE_REVISED_CONFIDENCE,  # 修订候选置信度保守略高于单候选基线
            "expert_failed": False,
            "verified_count": max(c.get("verified_count", 0) for c in top_candidates),
            "agreed_dimensions": [c.get("dimension") for c in top_candidates],
            "debate_revise": True,
        }
        # 修订候选插入首位（优先级最高），原 verified 候选标注 debate_revise=False
        return [revise_candidate] + [{**c, "debate_revise": False} for c in verified]


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
    "expert_pool_debate_enabled",
    "expert_pool_enabled",
]
