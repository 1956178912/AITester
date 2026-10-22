"""检查腿可测量性分析（BQ 轮，2026-10-22；从 analyze_results.py 拆出，承 0.7 债务项 1.6 的主题分包惯例）。

BG→BN 七轮把"读不懂 ⇒ 判优"逐个收成四值 status 并在发布侧/判定侧接上双读，
BN 轮把四个 status 通道写进结果行两分支与 raw 白名单。但**报告面
（analyze_results / run_main_batch / statistical_analysis）没有一个行读者**：
`build_analysis` 的三十个指标助手无一读这四个键，归档与新批次里
"这条腿跑过且干净（ok）"与"崩了（error）/ 按设计没跑（disabled）/
材料缺失（unavailable）/ 没记录（null / absent）"在所有报告面同形——
BG→BN 的披露链在实验侧断在最后一步（BM 轮给 contract_status 接的是
生产侧透传 final_state→结果行，不是报告面行读者）。

本模块只补**读侧披露**：分档计数 + 恒等式，判定值与判定方向一处不动
（四个键不进入任何判定，既不被翻成通过也不被翻成拒绝）。
"""

from __future__ import annotations

from typing import Any

#: BN/BL 轮写进结果行的四个 status 通道（顺序与 run_benchmark 结果行一致）
CHECK_LEG_CHANNELS: tuple[str, ...] = (
    "contract_status",
    "static_check_status",
    "safety_check_status",
    "oracle_check_status",
)

#: 通道的中文名（报告渲染用；口径注释在 src/utils/check_status.py）
CHECK_LEG_LABELS: dict[str, str] = {
    "contract_status": "命名契约腿",
    "static_check_status": "静态检查腿",
    "safety_check_status": "安全预检腿",
    "oracle_check_status": "oracle 腿",
}

#: 四值词汇（src/utils/check_status.py 单一事实源）；ok 才是"检查完成且零疑点"
CHECK_LEG_VOCAB: tuple[str, ...] = ("ok", "disabled", "unavailable", "error")

#: 没测成的两档（按设计没跑 disabled 单列，不算"没测成"）
CHECK_LEG_UNMEASURABLE: tuple[str, ...] = ("error", "unavailable")

#: 分档键序（计数字典的键序即报告列序）
CHECK_LEG_GRADES: tuple[str, ...] = (*CHECK_LEG_VOCAB, "null", "absent", "other")


def _channel_counts(details: list[dict[str, Any]], channel: str) -> dict[str, Any]:
    """单通道七档计数：ok / disabled / unavailable / error / null / absent / other。

    分档口径（BP 式"缺席 ≠ 零"判据，四值词汇外加三档非词汇形状）：
        - ``absent``：行里没有这个键——批次早于 BN 轮（2026-10-22）落盘；
        - ``null``：键在场、值为 None——该任务这条腿没记录（失败分支占位，
          或成功分支里 leg 未跑/未产出）；
        - ``other``：词表外真值——自成一档并带 ``other_values`` 明细，
          不进 ok 也不进任何否定档（防"OK"/"1"被静默算成干净）。
    """
    counts: dict[str, Any] = {grade: 0 for grade in CHECK_LEG_GRADES}
    other_values: list[Any] = []
    for row in details:
        if channel not in row:
            counts["absent"] += 1
            continue
        value = row.get(channel)
        if value is None:
            counts["null"] += 1
        elif value in CHECK_LEG_VOCAB:
            counts[value] += 1
        else:
            counts["other"] += 1
            if value not in other_values:
                other_values.append(value)
    counts["other_values"] = other_values
    return counts


def _check_leg_measurability(details: list[dict[str, Any]]) -> dict[str, Any]:
    """报告面读侧：四个 status 通道的逐行分档计数（BQ 轮，纯披露）。

    Args:
        details: run_benchmark 结果行的 details 列表（归档旧批次四键全缺席；
            BN 起成功分支写真实取值、失败分支写 None 占位）。

    Returns:
        {"available": bool,               # 至少一行记录了至少一个通道
         "reason": None | "no_rows" | "no_channel_recorded",
         "n_rows": int,
         "recorded_rows": int,            # 至少一键在场的行数（含值为 None 的行）
         "rows_any_unmeasurable": int,    # 任一路 error/unavailable 的行数
         "channels": {channel: {ok, disabled, unavailable, error, null,
                                absent, other, other_values}}}

    恒等式（锁里逐条钉）：
        - 每通道 ``ok+disabled+unavailable+error+null+absent+other == n_rows``；
        - ``recorded_rows == n_rows - 四键全缺席的行数``；
        - ``rows_any_unmeasurable <= recorded_rows``。

    判定纪律：``status != ok`` **不**表示"发现问题"，也**不**表示"没问题"——
    本函数不产出任何通过/拒绝判定，只让"没测成 / 没记录"在报告面可见。
    """
    n_rows = len(details)
    channels = {channel: _channel_counts(details, channel) for channel in CHECK_LEG_CHANNELS}
    recorded_rows = sum(1 for row in details if any(channel in row for channel in CHECK_LEG_CHANNELS))
    rows_any_unmeasurable = sum(
        1 for row in details if any(row.get(channel) in CHECK_LEG_UNMEASURABLE for channel in CHECK_LEG_CHANNELS)
    )
    result: dict[str, Any] = {
        "available": recorded_rows > 0,
        "n_rows": n_rows,
        "recorded_rows": recorded_rows,
        "rows_any_unmeasurable": rows_any_unmeasurable,
        "channels": channels,
    }
    if not details:
        # 改前的对应形态：没有任何一行 ⇒ available=False。两档 reason 可分
        # （BP 轮同款判据："没有行"与"有行但全没记录"是两件事）。
        result["reason"] = "no_rows"
    elif recorded_rows == 0:
        result["reason"] = "no_channel_recorded"
    else:
        result["reason"] = None
    return result
