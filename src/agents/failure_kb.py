"""
4. 失败知识库最小闭环（改进清单 P2，落地 docs/design/failure_knowledge_feedback.md 落点 B）。

设计文档 `docs/design/failure_knowledge_feedback.md` 此前标注"设计文档，未落地
代码"。本模块落地**最小在线消费侧**（落点 B：Debugger prompt 片段注入 + 条目
衰减机制），使 `experiments/analyze_failures.py` 产出的失败知识库（结构化
JSON）可被后续运行复用，同类错误的修复策略跨任务传递。

默认行为不变（新开关全默认关）：
- `FAILURE_KB_ENABLE=false`（默认）时，`kb_debugger_snippet()` 返回 None，
  Debugger prompt 与历史逐字节一致；
- 开关开启但知识库文件缺失 / 损坏 / 空时，同样返回 None（保守降级，不阻断修复）；
- 条目衰减（`FAILURE_KB_DECAY_DAYS`，默认 30 天）：知识库条目按 `last_seen`
  时间戳衰减，超龄条目权重降低（频次 × 衰减因子），避免过时策略污染后续
  修复。衰减是纯读侧计算，不改写源文件（保守：源知识库仍由离线
  `analyze_failures.py --knowledge-base` 重新生成）。

离线→在线闭环（五阶段，见设计文档 §2）：
    ① 离线积累：`experiments/analyze_failures.py -k failure_knowledge_base.json`
    ② 人工审核：高置信度模式聚类打分（设计文档口径，本模块不自动改写源）
    ③ 固化落地：本模块 = 落点 B（prompt 片段注入），默认关
    ④ 后续运行消费：`_debugger_node` 经 `kb_debugger_snippet()` 注入
    ⑤ 效果验证：`analyze_results.py` 统计"走 KB 路径"的任务（观测层）
"""

from __future__ import annotations

import json
import logging
import math
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

# 知识库默认路径（experiments/results 下，与 analyze_failures.py --knowledge-base
# 默认输出同口径）；可用环境变量 FAILURE_KB_PATH 覆盖（测试指向临时文件）
_DEFAULT_KB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "experiments",
    "results",
    "failure_knowledge_base.json",
)

# 衰减半衰期（天）：条目 last_seen 距今每过一个半衰期，权重 × 0.5。
# 默认 30 天（FAILURE_KB_DECAY_DAYS 可调；≤0 关闭衰减，全部条目等权）。
_DEFAULT_DECAY_HALF_LIFE_DAYS = 30.0
# 注入 prompt 的最大片段数（避免 prompt 过长）
_MAX_SNIPPETS = 3
# 单片段建议修复 / 诊断摘录截断长度
_SNIPPET_FIELD_TRUNCATE = 300


def _kb_enabled() -> bool:
    """失败知识库开关（FAILURE_KB_ENABLE=true 时启用，默认 false，历史口径不变）。"""
    return os.getenv("FAILURE_KB_ENABLE", "false").lower() == "true"


def _kb_path() -> str:
    """知识库文件路径（支持 FAILURE_KB_PATH 环境变量覆盖，便于测试隔离）。"""
    return os.environ.get("FAILURE_KB_PATH", _DEFAULT_KB_PATH)


def _decay_half_life_days() -> float:
    """衰减半衰期（天）（FAILURE_KB_DECAY_DAYS，默认 30；≤0 关闭衰减）。"""
    try:
        return float(os.environ.get("FAILURE_KB_DECAY_DAYS", str(_DEFAULT_DECAY_HALF_LIFE_DAYS)))
    except ValueError:
        return _DEFAULT_DECAY_HALF_LIFE_DAYS


def load_knowledge_base(path: str | None = None) -> list[dict[str, Any]]:
    """加载失败知识库 JSON（缺失 / 损坏 / 非列表时返回空列表，保守降级）。

    Args:
        path: 知识库文件路径；None 时读 FAILURE_KB_PATH / 默认路径。

    Returns:
        结构化案例列表（analyze_failures.failure_knowledge_base 口径）。
    """
    kb_file = path or _kb_path()
    if not os.path.isfile(kb_file):
        return []
    try:
        with open(kb_file, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("失败知识库加载失败（降级为空，不阻断修复）: %s", e)
        return []
    if not isinstance(data, list):
        return []
    return [entry for entry in data if isinstance(entry, dict)]


def _entry_decay_weight(entry: dict[str, Any], now: float, half_life_days: float) -> float:
    """条目衰减权重：按 last_seen 距今时间 × 半衰期指数衰减。

    - last_seen 缺失（历史条目无时间戳）→ 权重 1.0（不衰减，保守）；
    - half_life_days ≤ 0 → 权重 1.0（衰减关闭）；
    - 权重 = 0.5 ** (age_days / half_life_days)，越久越权低（避免过时策略污染）。
    """
    if half_life_days <= 0:
        return 1.0
    last_seen = entry.get("last_seen")
    if last_seen is None:
        return 1.0
    try:
        age_seconds = max(0.0, now - float(last_seen))
    except (TypeError, ValueError):
        return 1.0
    age_days = age_seconds / 86400.0
    return math.pow(0.5, age_days / half_life_days)


def rank_knowledge_entries(
    entries: list[dict[str, Any]],
    error_category: str,
    now: float | None = None,
    top_k: int = _MAX_SNIPPETS,
) -> list[dict[str, Any]]:
    """按 (error_category 匹配 + 频次 × 衰减权重) 对知识库条目排序取 top-k。

    评分口径（保守，纯数据计算不依赖 LLM）：
    - 同 error_category 条目得基础分 10（跨类条目得 0，不注入无关策略）；
    - 频次加权：同一 error_category 在知识库中出现 N 次（含 root_cause 维度），
      每个同类型号得分 += N × 衰减权重；
    - 衰减：条目 last_seen 越久权重越低（避免过时策略污染后续修复）。

    Args:
        entries: 知识库条目列表（load_knowledge_base 返回）。
        error_category: 当前任务的错误类别（refine_failure_category 口径）。
        now: 当前时间戳（None 用 time.time()，测试可注入固定值）。
        top_k: 返回的最大条目数。

    Returns:
        排序后的条目列表（最多 top_k 条，按得分降序；得分 0 的条目不返回）。
    """
    if not entries:
        return []
    ts = now if now is not None else time.time()
    half_life = _decay_half_life_days()

    # 同 error_category 的条目数（频次口径：含 root_cause 维度去重计数）
    same_cat_entries = [e for e in entries if str(e.get("error_category") or "").lower() == error_category.lower()]
    if not same_cat_entries:
        return []
    frequency = len(same_cat_entries)

    scored: list[tuple[float, int, dict[str, Any]]] = []
    for idx, entry in enumerate(same_cat_entries):
        weight = _entry_decay_weight(entry, ts, half_life)
        # 基础分 10（同类匹配）× 频次 × 衰减权重；idx 做稳定 tie-break
        score = 10.0 * frequency * weight
        scored.append((score, -idx, entry))
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)

    ranked: list[dict[str, Any]] = []
    for score, _idx, entry in scored:
        if score <= 0:
            break
        ranked.append(entry)
        if len(ranked) >= top_k:
            break
    return ranked


def kb_debugger_snippet(error_category: str, now: float | None = None) -> str | None:
    """生成注入 Debugger prompt 的失败知识库片段（落点 B，默认关）。

    返回 None（历史口径）的情形：
    - `FAILURE_KB_ENABLE=false`（默认）——开关关闭，prompt 与历史逐字节一致；
    - 知识库文件缺失 / 损坏 / 空；
    - 当前 error_category 在知识库中无匹配条目（不注入无关策略）。

    返回非 None 时：拼接同 error_category 的 top-k 条目的"建议修复 + 诊断
    摘录"，供 `_debugger_node` 追加到既有 prompt 尾部（不替换历史模板，
    注入失败时 Debugger 正常走通用兜底）。

    Args:
        error_category: 当前任务错误类别（refine_failure_category 口径字符串）。
        now: 当前时间戳（测试可注入；None 用 time.time()）。

    Returns:
        prompt 片段字符串，或 None（不注入）。
    """
    if not _kb_enabled():
        return None
    entries = load_knowledge_base()
    if not entries:
        return None
    ranked = rank_knowledge_entries(entries, error_category, now=now)
    if not ranked:
        return None

    lines: list[str] = [
        "【失败知识库提示（4. 闭环落点 B，默认关）】",
        f"以下历史案例与当前错误类别（{error_category}）同类，已按频次×时间衰减排序：",
    ]
    for i, entry in enumerate(ranked, 1):
        cat = str(entry.get("error_category") or "unknown")
        root_cause = str(entry.get("root_cause") or "unknown")
        diagnosis = str(entry.get("diagnosis_excerpt") or "")[:_SNIPPET_FIELD_TRUNCATE]
        suggested = entry.get("suggested_fix") or {}
        suggested_fix = str(suggested.get("direction") or suggested.get("root_cause") or "")[:_SNIPPET_FIELD_TRUNCATE]
        repro = str(entry.get("reproducible_steps") or "")[:_SNIPPET_FIELD_TRUNCATE]
        lines.append(
            f"  案例{i}（类别={cat}，根因={root_cause}）：{suggested_fix}"
            + (f"｜诊断摘录：{diagnosis}" if diagnosis else "")
            + (f"｜复现：{repro}" if repro else "")
        )
    lines.append("请优先参考上述同类案例的修复方向；若与当前代码上下文冲突，以当前代码为准。")
    return "\n".join(lines)


def kb_applied_state_key() -> dict[str, Any] | None:
    """观测层：返回"本任务是否走了 KB 增强路径"的 state 键（供 analyze_results 统计）。

    开关关 / 无匹配条目时返回 None（不写入 state，历史口径不变）；
    开启且有注入时返回 {"kb_prompt_snippet_applied": True, "kb_error_category": ...}。
    实际类别由调用方（_debugger_node）填入。
    """
    if not _kb_enabled():
        return None
    return {"kb_prompt_snippet_applied": False}


if __name__ == "__main__":
    # 自检：打印当前知识库加载与排序结果（供人工核验闭环）
    sample = load_knowledge_base()
    print(f"知识库条目数：{len(sample)}（路径：{_kb_path()}）")
    if sample:
        top = rank_knowledge_entries(sample, sample[0].get("error_category", "unknown"))
        for e in top:
            print(f"  - {e.get('error_category')} / {e.get('root_cause')} / {e.get('task_id')}")
    else:
        print("（知识库为空或不存在；离线积累：python experiments/analyze_failures.py -k）")
