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
- 价目表模型未登记 / 价格字段 null / 币种不可判定 / 币种登记为非 USD → 视为"无美元价目"；
  AB-14（2026-10-20）把这句的判定收成本模块的 `currency_status`：币种**键缺席**、值为
  `null`、值为空白、值不是字符串是四种不同事实，一律"不可判定"，**不得默认成任何单位**
  （改前本模块给 `currency` 键设了美元缺省值，把"没写"读成"美元"）；
- 文件缺失 / JSON 解析失败 / 结构不符 → 空表（降级为回退/未计价，不阻断主流程）；
  AB-17（2026-10-20）把"文件 → `models` 层"的准入判定收口到本模块的
  `table_read_reason` / `load_table_json` / `models_layer` / `load_table_models`：
  机制码在一处写一遍，七个读点（本模块、spec/report/ext 三个站点、
  `statistical_analysis`、两个 CLI）共用同一个名字；
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
import math
import os
import threading
from collections.abc import Mapping
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
    """加载价目表（模型名 → 条目 dict），进程内缓存；失败返回空表并点名机制（AB-17）。

    Returns:
        `{"<model>": {"input_per_mtok": float|None, "output_per_mtok": ...,
        "currency": "USD|CNY|...", "source": str, "as_of": str}, ...}`——**原样**交出：
        AB-17 起非对象条目不再被静默过滤（改前 `isinstance(v, dict)` 让坏条目无声消失，
        读起来与"没登记"同形；现交下游按 `entry_block_reason` 点名）。
        文件缺失 / 解析失败 / 结构不符 → `{}`（降级为回退价/未计价）+ 一条带机制码的
        `logger.warning`；机制码取自 `load_table_models`，与其余六个读点同源。
    """
    global _price_table_cache
    with _cache_lock:
        if _price_table_cache is not None:
            return _price_table_cache
        models, reason = load_table_models(_PRICE_TABLE_PATH)
        if reason is not None:
            logger.warning("价目表不可用（%s：%s）：USD 记账降级为回退/未计价", _PRICE_TABLE_PATH, reason)
        _price_table_cache = models
        return models


# ─── AB-14（2026-10-20）：币种判定的唯一事实源 ────────────────────────────────
#
# 改前同一个"这笔钱是不是美元"的判断在仓内被写了四遍且四遍互不相同：
# 本模块用 `currency` 键的缺省值兜底（键缺席即当成美元）、`statistical_analysis.cost_analysis`
# 对取到的币种再加一次美元兜底（缺席/null/空白三种事实一律印成 USD，且大小写敏感）、
# `spec_examples_generator.estimate_cost_usd` 与 `emse_stats_report.cost_effectiveness_block`
# 用空串兜底后大写比对（缺席一律剔除，但不 strip 也不认 ` USD `），第五处
# `analyze_t1_b2_main_batch.add_cost` 干脆不看币种直接把登记值累加成 `cost_usd`。分叉的后果
# 不是"风格不一致"：同一个条目在一处计价、在另一处被剔除，而两处都账面正常。
# 判定只在这里写一遍，五处全部接过来。
#
# AB-15d（2026-10-20）再往下收一层：判定收口后，**归因**又被抄了三遍——同一笔拒绝在
# `emse_stats_report` 里叫 `currency_absent`、在 `statistical_analysis` 里叫
# `currency_blocked`、在 `oracle_examples_replay` 里连名字都没有（只剩一个 `$None`）。
# "为什么没算出钱"的词汇表同样只在这里写一遍（`currency_block_reason`），站点只做计数与格式化。


def currency_status(entry: Any) -> str:
    """价目表条目的币种字段状态（**只读事实，不做兜底**）。

    Returns:
        七类互不相同的读数之一：

        - `entry_not_object:<T>`：条目本身不是对象（`<T>` 为类型名）；
        - `absent`：`currency` 键缺席——"没登记单位"，不是"登记了美元"；
        - `null`：键在、值为 `null`；
        - `blank`：键在、值是空串或纯空白；
        - `usd`：strip + 大写归一后等于 `USD`；
        - `other:<NORM>`：登记了别的单位（`<NORM>` 为归一化后的字面值）；
        - `not_string:<T>`：值不是字符串（`int`/`bool`/`list`/`dict`…）。
    """
    if not isinstance(entry, dict):
        return f"entry_not_object:{type(entry).__name__}"
    if "currency" not in entry:
        return "absent"
    value = entry["currency"]
    if value is None:
        return "null"
    if not isinstance(value, str):
        return f"not_string:{type(value).__name__}"
    normalized = value.strip().upper()
    if not normalized:
        return "blank"
    return "usd" if normalized == "USD" else f"other:{normalized}"


def currency_label(status: str) -> str | None:
    """状态 → 可呈现的单位标签；币种不可判定 → None。

    `usd` → `USD`；`other:<NORM>` → `<NORM>`（归一化后的登记值，供带币种列的表呈现）；
    `absent` / `null` / `blank` / `not_string:<T>` / `entry_not_object:<T>` → None——
    "没登记单位"不得被渲染成任何单位名，尤其不得渲染成 `USD`。
    """
    if status == "usd":
        return "USD"
    if status.startswith("other:"):
        return status.partition(":")[2]
    return None


def is_usd_entry(entry: Any) -> bool:
    """条目是否**明确登记**为美元币种（币种不可判定与其他单位同样不计价）。"""
    return currency_status(entry) == "usd"


#: `currency_status` 里"根本没登记单位"的三种事实（AB-15d）。
CURRENCY_UNDETERMINED_STATUSES: frozenset[str] = frozenset({"absent", "null", "blank"})


def currency_block_reason(status: str) -> str | None:
    """币种这一维的**机制名**——"这笔钱为什么不能进美元列"（AB-15d）。

    `currency_status` 回答"是不是美元"，本函数把同一个读数翻译成可写进报告的原因码；
    词汇表只在这里写一遍，站点只负责计数与格式化。改前三处各抄一套（
    `emse_stats_report` 的 if/elif 链、`statistical_analysis` 的分桶名、
    `oracle_examples_replay` 干脆没有归因），于是同一笔拒绝在两份报告里点名不同。

    Returns:
        `usd` → None（无阻断）；其余按 `currency_status` 的读数落互不相同的码：

        - `absent` / `null` / `blank` → `currency_absent`（没登记单位）；
        - `other:<NORM>` → `currency_not_usd:<NORM>`；
        - `not_string:<T>` → `currency_not_usd:not_string:<T>`；
        - 其余（含 `entry_not_object:<T>`）→ `currency_unreachable:<T>`——
          "条目不是对象 ⇒ 币种这一维根本读不到"与"币种值不是字符串"是两种事实
          （AB-11 判据），不共用一个码。
    """
    if status == "usd":
        return None
    if status in CURRENCY_UNDETERMINED_STATUSES:
        return "currency_absent"
    kind, separated, detail = status.partition(":")
    if kind == "other":
        return f"currency_not_usd:{detail}"
    if kind == "not_string":
        return f"currency_not_usd:not_string:{detail}"
    return f"currency_unreachable:{detail if separated else kind}"


# ─── AB-16（2026-10-20）：价目数字与条目的准入域，一处写一遍 ──────────────────
#
# AB-14 收了"是不是美元"、AB-15 收了"拒绝的呈现与归因"，但"什么算一个价格数字"仍在
# 仓内写了五套：本模块的 `_as_non_negative_float`（约等于但 `inf < 0` 为假 ⇒ 收下）、
# spec/report 的 `float()` 直收（`True` 当 1、`"1.0"` 收下、`-1.0` 编出负数金额、
# `[1.0]` 抛 TypeError）、ext 的 bool 特判 + 直乘（str/list 抛 TypeError、负价照乘）、
# `analyze_t1_b2_main_batch._price_reject_reason`（最完整但不管 `nan`/`inf`）、
# `statistical_analysis._model_is_priced`（`inf >= 0` 为真 ⇒ 收下）。同一张条目在一处
# 计价、在第二处被拒、在第三处崩溃，而三处账面各自正常。什么能变成金额，只在这里写一遍。


def price_block_reason(price_in: Any, price_out: Any) -> str | None:
    """价目数字这一维的机制名（"这个价格为什么不能进金额"）；两个价都可用 → None。

    AB-15b 在 `analyze_t1_b2_main_batch` 里首写，AB-16 收口到本模块。一个输入只得到
    一条机制，优先级：缺席 > 类型 > 负数 > 非有限——与 AB-15b 既有读数逐码保持
    （`-inf` 仍是一条 `price_negative`：它确实小于零；`nan` 与 `+inf` 是新收的"非有限"档）。

    Returns:
        - 任一为 None（含键缺席）→ `price_null`；
        - 类型不是真数（`bool` 单列一档，它是 `int` 的子类；str/list/dict…按类型名排序
          聚合）→ `price_not_a_number:<T>`（如 `price_not_a_number:bool/str`）；
        - 任一为负（含 `-inf`）→ `price_negative`；
        - 任一为 `nan` / `+inf` → `price_not_finite:nan` / `price_not_finite:inf`；
        - 可用 → None。
    """
    if price_in is None or price_out is None:
        return "price_null"
    bad = sorted(
        {type(p).__name__ for p in (price_in, price_out) if isinstance(p, bool) or not isinstance(p, (int, float))}
    )
    if bad:
        return f"price_not_a_number:{'/'.join(bad)}"
    if price_in < 0 or price_out < 0:
        return "price_negative"
    weird = sorted({("nan" if math.isnan(p) else "inf") for p in (price_in, price_out) if not math.isfinite(p)})
    if weird:
        return f"price_not_finite:{'/'.join(weird)}"
    return None


def entry_block_reason(entry: Any, *, allow_non_usd: bool = False) -> str | None:
    """条目级准入判定（AB-16）：形状 → 空条目 → 币种 → 价格数字，一处写一遍；可用 → None。

    改前"一张条目能不能进美元金额"在四个消费点各写一套，同一张条目读出四种结论：
    `{}` 在 spec/report 是 `entry_empty`、在 ext 是"未计价"（折成 `0.0` 部分和）、
    在 analyze 是 `currency_absent`；非对象条目在 spec/ext/analyze 是
    `currency_unreachable:<T>`、在 report 是 `entry_not_object:<T>`。判定顺序与既有
    站点逐条保持（形状 → 空 → 币种 → 数字），站点只负责计数与格式化。

    Args:
        allow_non_usd: AG（2026-10-20）——按价目表登记币种**原样计价**的站点
            （`statistical_analysis.cost_analysis` 的成本表带币种列）置 True：
            `other:<NORM>` 可用（不是"进美元金额"，而是"进它自己单位的金额"）。
            币种**不可判定**（absent/null/blank/not_string）仍阻断——没有单位就
            无法说这笔钱是什么。默认 False = 只收明确 USD 的条目。

    Returns:
        - 条目不是对象 → `entry_not_object:<T>`；
        - 空条目 → `entry_empty`（"什么都没有"比"没写单位"更准确）；
        - 币种不可判定 / 非 USD（`allow_non_usd` 时非 USD 放行）→
          `currency_block_reason(currency_status(...))` 的码；
        - 价格数字不可用 → `price_block_reason(...)` 的码；
        - 可用 → None。
    """
    if not isinstance(entry, dict):
        return f"entry_not_object:{type(entry).__name__}"
    if not entry:
        return "entry_empty"
    status = currency_status(entry)
    reason = currency_block_reason(status)
    if reason is not None and not (allow_non_usd and status.startswith("other:")):
        return reason
    return price_block_reason(entry.get("input_per_mtok"), entry.get("output_per_mtok"))


def model_entry_reason(models: Mapping[str, Any], model: str, *, allow_non_usd: bool = False) -> str | None:
    """模型在**表内**的准入读数：键缺席 → `model_unregistered`，其余交 `entry_block_reason`。

    "模型没登记"是表级事实，条目谓词看不见；AG（2026-10-20）前这个缺席分支在
    `run_b8_injection` 与 `cost_analysis` 各写一次。名字只在这里写一遍，两个站点
    得到同一个读数（`model_unregistered` 只留给**真的键缺席**，值 null 仍是
    `entry_not_object:NoneType`——AB-17 判据）。
    """
    if model not in models:
        return "model_unregistered"
    return entry_block_reason(models[model], allow_non_usd=allow_non_usd)


# ─── AB-17（2026-10-20）：表级读侧准入，一处写一遍 ────────────────────────────
#
# AB-14 收了"是不是美元"、AB-15 收了"拒绝的呈现与归因"、AB-16 收了"什么算一张合格条目"，
# 但"这个文件读出来算不算一张表"仍写在七处、读出七种记法：同一份坏表在 src 只留一个错
# 文案（"缺 models dict"，连"键在但值为 null"也并写）、在 `emse_stats_extensions` 直接崩
# （FileNotFoundError / JSONDecodeError / KeyError / TypeError / AttributeError）、在
# `emse_stats_report` 是六套中文短语、在 `spec_examples_generator` 文件级只进日志、
# 在 `statistical_analysis` 文件路径全程无痕而参数路径点名、两个 CLI
# （`analyze_t1_b2_main_batch` / `run_b8_injection`）半数崩、余下把损坏表读成别的。
# 文件 → `models` 层的准入判定只在这里写一遍；七处只负责把机制名放进各自的披露通道。


def table_read_reason(exc: BaseException) -> str:
    """文件级读取失败 → 机制名（AB-17）。

    "文件不存在" / "内容不是 JSON" / "文件读不动"是三种不同事实（AB-11 判据），不得共享
    一句"价目表不可用"。`UnicodeDecodeError` 与 `JSONDecodeError` 同属 `ValueError`：两者
    都是"这份内容不是那张表"，不是"文件读不动"。

    Returns:
        - `FileNotFoundError` → `price_table_file_missing`；
        - `ValueError`（含 `JSONDecodeError` / `UnicodeDecodeError`）→
          `price_table_json_invalid:<T>`；
        - 其余（含 `PermissionError` 等）→ `price_table_file_unreadable:<T>`。
    """
    if isinstance(exc, FileNotFoundError):
        return "price_table_file_missing"
    if isinstance(exc, ValueError):
        return f"price_table_json_invalid:{type(exc).__name__}"
    return f"price_table_file_unreadable:{type(exc).__name__}"


def load_table_json(path: str | Path) -> tuple[Any | None, str | None]:
    """读取并解析价目表文件：`(解析结果, None)` 或 `(None, 机制名)`（AB-17）。

    返回 `(None, None)` 是合法读数——文件内容就是 `null`（`json.loads` 的六种非对象顶层
    之一）；`reason` 非 None 才表示**没读到内容**。两种 `None` 的区分由 reason 承担，
    调用方不得用 `data is None` 判断读取失败（AB-12e 的同型判据）。

    改前七处各写 try/except 且各拦不同异常集（report 拦三类、spec 只拦
    `OSError`/`JSONDecodeError`、两个 CLI 干脆不拦）——同一份坏文件在不同站点得到
    崩溃/静默两种结局。
    """
    try:
        return json.loads(Path(path).read_text(encoding="utf-8")), None
    except (OSError, ValueError) as exc:
        return None, table_read_reason(exc)


def models_layer(data: Any) -> tuple[dict[str, Any], str | None]:
    """从解析结果取 `models` 层（**原样，不过滤**）：`(models, None)` 或 `(空表, 机制名)`（AB-17）。

    七处读点原本各写一套形状判定，同一份坏表读出六种结论；这里只写一遍：

    - 顶层非对象（含文件内容是 `null`）→ `price_table_not_object:<T>`；
    - 顶层对象、缺 `models` 键：**空对象没有形状可说** ⇒ 静默"真的没登记"
      （`({}, None)`，沿用 `statistical_analysis` AB-14 已注册的口径）；
      非空对象 ⇒ `models_key_absent`（"键缺席"与"值为 `null`"是两种事实——AB-11 判据）；
    - `models` 键在、值为非对象（**真假一律**）→ `models_not_object:<T>`；
    - 可用 → 原样交出：非对象条目**不再被静默丢弃**（改前 `src` 与
      `statistical_analysis` 各有一处 `isinstance(v, dict)` 过滤，坏条目无声消失，
      读起来与"没登记"同形；现交下游按 `entry_block_reason` 点名）。
    """
    if not isinstance(data, dict):
        return {}, f"price_table_not_object:{type(data).__name__}"
    if "models" not in data:
        if data:
            return {}, "models_key_absent"
        return {}, None
    models = data["models"]
    if not isinstance(models, dict):
        return {}, f"models_not_object:{type(models).__name__}"
    return models, None


def load_table_models(path: str | Path) -> tuple[dict[str, Any], str | None]:
    """读文件 → `models` 层一步到位：`(models, None)` 或 `(空表, 机制名)`（AB-17）。"""
    data, reason = load_table_json(path)
    if reason is not None:
        return {}, reason
    return models_layer(data)


def _usd_prices(entry: Any) -> tuple[float, float] | None:
    """从价目表条目取美元 in/out 每百万 token 价（币种不可判定 / 非 USD / 缺价 / 坏数字 → None）。

    AB-16：数字域收口到共享谓词——改前 `inf` 满足 `inf < 0` 为假被收下，记账出 `inf` 美元。

    Args:
        entry: 价目表模型条目（任意类型，容错）。

    Returns:
        ``(input_per_mtok, output_per_mtok)``；不可用时 None。
    """
    if not is_usd_entry(entry):
        # 诚实条款：币种不可判定或登记为非 USD 时不换算（无汇率事实源），回退/未计价。
        return None
    if price_block_reason(entry.get("input_per_mtok"), entry.get("output_per_mtok")) is not None:
        return None
    return float(entry["input_per_mtok"]), float(entry["output_per_mtok"])


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
    "CURRENCY_UNDETERMINED_STATUSES",
    "currency_block_reason",
    "currency_label",
    "currency_status",
    "entry_block_reason",
    "estimate_usd",
    "is_usd_entry",
    "load_price_table",
    "load_table_json",
    "load_table_models",
    "model_entry_reason",
    "models_layer",
    "price_block_reason",
    "reset_price_table_cache",
    "table_read_reason",
]
