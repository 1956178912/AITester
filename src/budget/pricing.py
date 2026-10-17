"""LLM 调用美元费用估算（D1 修复，N-5）：把 token 用量按价目表换算为 USD。

背景（N-4 真实 LLM 探针实测 D1，P0）
------------------------------------
`COST_BUDGET_USD` 生产路径**从未记账**：`src/agents/llm_client.py::_record_response_usage`
只把 token 增量传给 `check_budget(consumed_delta_tokens=...)`，`consumed_delta_usd`
恒 0 → `BudgetSnapshot.consumed_usd` 恒 0 → USD 上限永不触发（"纸面开关"）。
本模块提供**单一计价事实源**：按 `experiments/price_table.json`（模型级
input/output 每百万 token 美元价）计算本次调用 USD；价目缺失时回退到
既有 `COST_USD_PER_1K` 配置（每千 token 混合价，历史旋钮）；两者皆无则返回
None（**不编造价格**，由调用方显式记录"未计价"事件，不静默当 0）。

诚实条款（与 `experiments/price_table.json` 的 `_comment` 同口径）
-----------------------------------------------------------------
- 价目表模型未登记 / 价格字段 null / 币种非 USD → 视为"无美元价目"；
- 文件缺失 / JSON 解析失败 / 结构不符 → 空表（降级为回退/未计价，不阻断主流程）；
- 金额为**估算**（at standard price），不是供应商账单；审计面须带来源标记
  （`estimate_usd` 返回的 source 字符串）。

设计约束（ADR-0003 默认关 + ADR-0004 零默认依赖）
-------------------------------------------------
- 纯标准库（json/os/pathlib/threading），无新依赖；
- 价目表**懒加载 + 进程内缓存**（每进程一次 IO）；`reset_price_table_cache()`
  供测试/长进程刷新；
- 仅在预算开关启用时由 `_record_response_usage` 调用 → `COST_BUDGET_ENABLE=false`
  时零行为差异（连价目表 IO 都不发生）。
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: 仓库根（src/budget/pricing.py → parents[2]）。
_REPO_ROOT = Path(__file__).resolve().parents[2]
#: 价目表默认路径（与 `experiments/statistical_analysis.py` / `emse_stats_report.py`
#: 的价目事实源同一文件；本模块只读、不改口径）。
_PRICE_TABLE_PATH = _REPO_ROOT / "experiments" / "price_table.json"

_price_table_cache: dict[str, dict[str, Any]] | None = None
_cache_lock = threading.Lock()


def reset_price_table_cache() -> None:
    """清空价目表进程内缓存（测试隔离 / 长进程刷新用）。"""
    global _price_table_cache
    with _cache_lock:
        _price_table_cache = None


def load_price_table() -> dict[str, dict[str, Any]]:
    """加载价目表（模型名 → 条目 dict），进程内缓存；失败返回空表。

    Returns:
        `{"<model>": {"input_per_mtok": float|None, "output_per_mtok": ...,
        "currency": "USD|CNY|...", "source": str, "as_of": str}, ...}`。
        文件缺失 / 解析失败 / 结构不符 → `{}`（调用方降级为回退价/未计价）。
    """
    global _price_table_cache
    with _cache_lock:
        if _price_table_cache is not None:
            return _price_table_cache
        models: dict[str, dict[str, Any]] = {}
        try:
            data = json.loads(_PRICE_TABLE_PATH.read_text(encoding="utf-8"))
            raw_models = data.get("models") if isinstance(data, dict) else None
            if isinstance(raw_models, dict):
                models = {str(k): v for k, v in raw_models.items() if isinstance(v, dict)}
            else:
                logger.warning("价目表 %s 结构不符（缺 models dict）：USD 记账降级为回退/未计价", _PRICE_TABLE_PATH)
        except FileNotFoundError:
            logger.warning("价目表缺失（%s）：USD 记账降级为 COST_USD_PER_1K 回退/未计价", _PRICE_TABLE_PATH)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("价目表加载失败（%s: %s）：USD 记账降级为回退/未计价", _PRICE_TABLE_PATH, e)
        _price_table_cache = models
        return models


def _as_non_negative_float(value: Any) -> float | None:
    """把价目字段规整为非负 float；非法（非数值/bool/负数）→ None。"""
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
        return None
    return float(value)


def _usd_prices(entry: Any) -> tuple[float, float] | None:
    """从价目表条目取美元 in/out 每百万 token 价（非 USD / 缺价 / 负数 → None）。

    Args:
        entry: 价目表模型条目（任意类型，容错）。

    Returns:
        ``(input_per_mtok, output_per_mtok)``；不可用时 None。
    """
    if not isinstance(entry, dict):
        return None
    if str(entry.get("currency", "USD")).upper() != "USD":
        # 诚实条款：币种不是 USD 时不换算（无汇率事实源），回退/未计价。
        return None
    price_in = _as_non_negative_float(entry.get("input_per_mtok"))
    price_out = _as_non_negative_float(entry.get("output_per_mtok"))
    if price_in is None or price_out is None:
        return None
    return price_in, price_out


def _fallback_usd_per_1k() -> float:
    """`COST_USD_PER_1K` 回退单价（每千 token 混合价）；未配置/坏值 → 0.0。

    坏值不在此 fail-closed：`check_budget` 已对 `COST_USD_PER_1K` 坏值做
    fail-closed 阻断（G 轮口径）；本函数只负责取"可用回退价"，坏值按未配置处理
    以避免重复计数/重复告警。
    """
    raw = os.getenv("COST_USD_PER_1K", "").strip()
    if not raw:
        return 0.0
    try:
        value = float(raw)
    except ValueError:
        return 0.0
    return value if value > 0 else 0.0


def estimate_usd(
    model_name: str,
    input_tokens: int,
    output_tokens: int,
) -> tuple[float | None, str]:
    """估算一次 LLM 调用的美元费用（价目表优先，COST_USD_PER_1K 回退）。

    计价优先级：
        1. `experiments/price_table.json` 中该模型**USD 完整价目** →
           ``in × input_per_mtok/1e6 + out × output_per_mtok/1e6``；
        2. 价目不可用且 `COST_USD_PER_1K > 0` → ``总tokens/1000 × COST_USD_PER_1K``；
        3. 两者皆无 → ``(None, "unpriced")``（**不编造价格**，调用方记账"未计价"）。

    Args:
        model_name: 实际服务模型名（如 deepseek-flash；空串可接受）。
        input_tokens: 输入 token 数（负数按 0）。
        output_tokens: 输出 token 数（负数按 0）。

    Returns:
        ``(usd, source)``：usd 为 None 表示无美元价目；source ∈
        ``price_table:<model>`` / ``cost_usd_per_1k`` / ``zero_tokens`` / ``unpriced``。
    """
    try:
        tokens_in = max(0, int(input_tokens or 0))
        tokens_out = max(0, int(output_tokens or 0))
    except (TypeError, ValueError):
        return None, "invalid_usage"
    if tokens_in + tokens_out <= 0:
        return 0.0, "zero_tokens"
    model = str(model_name or "").strip()
    prices = _usd_prices(load_price_table().get(model)) if model else None
    if prices is not None:
        price_in, price_out = prices
        usd = tokens_in * price_in / 1_000_000 + tokens_out * price_out / 1_000_000
        return usd, f"price_table:{model}"
    per_1k = _fallback_usd_per_1k()
    if per_1k > 0:
        return (tokens_in + tokens_out) / 1000.0 * per_1k, "cost_usd_per_1k"
    return None, "unpriced"


__all__ = [
    "estimate_usd",
    "load_price_table",
    "reset_price_table_cache",
]
