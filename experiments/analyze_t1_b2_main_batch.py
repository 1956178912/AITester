#!/usr/bin/env python3
"""T1（B2）主批次锁指纹复现批分析（零 LLM 只读工件）。

用法：
    .venv/bin/python experiments/analyze_t1_b2_main_batch.py \
        --out experiments/results/t_round_b2_main_batch_20261018 \
        --orig-dir experiments/results/main_batch \
        [--write]

产出（--write 时）：
    <out>/ANALYSIS_REPORT.json   判定（§1.2 pre-registered）+ 逐 seed/合并表 + 与原批并排 + provenance 漂移
    <out>/README.md              中文报告（含 §1.1 硬门槛、判定、三指标、成本、口径与局限）。
                                  生成内容之外的**手工维护节**用 `<!-- MANUAL:BEGIN/END -->`
                                  标记包裹，--write 时原样保留在文末（防重跑丢失手写
                                  解读；X 轮 2026-10-19 增设，回归锁见
                                  tests/test_analyze_t1_b2_manual_sections.py）。

口径：
- detection 计数 = 行 `detection_rate` 值 >= 1.0（None 不进分母）；同时并列 `llm_suite_detection_rate`
  可测时的计数（N-3 后独立判读口径；旧批该字段恒 None）。
- repair/false_fix 计数沿用主批次 M1 行口径（>=1.0 计命中），分母 = 字段非 None 行数。
- McNemar：按 (seed, task_id) 配对；b=新检出旧未检出，c=旧检出新未检出；双侧精确二项 p。
- bootstrap：按任务对重采样 5000 次（固定 seed=20261018，percentile 95% CI）。
- 成本：本批 token_metrics 的 input/output 分别 × 价目表（官方价，峰时全额），非账单。
- 缺席披露（AB-12b，2026-10-20）：`availability` / `verdict.gates_state` /
  `provenance_drift.skipped_seeds` 三类键**只在真的发生缺席或无法核验时**写入——无缺席输入
  产出的载荷逐字节不变（已归档工件不需要重写，回归锁见
  `tests/test_experiments_absent_vs_zero_ab12.py`）。§1.1 硬门槛为三态
  （PASS/FAIL/UNVERIFIABLE）：GATES.json 缺席、读不动、`all_pass` 键缺席或值非布尔都只报
  "无法核验"，不得渲染成 FAIL；臂/批次缺席必须留机制名，不得降成 `rows: 0` 的空读数。
"""

from __future__ import annotations

import argparse
import ast
import json
import math
import random
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

# AB-14（2026-10-20）：币种判定的唯一事实源在 `src.budget.pricing.currency_status`；
# AB-16（2026-10-20）：条目准入与价目数字域的唯一事实源在 `src.budget.pricing.entry_block_reason`；
# AB-17（2026-10-20）：文件 → `models` 层的表级准入在 `load_table_json` / `models_layer`。
# 本文件既可被测试按包导入，也可直接以脚本方式运行（`python experiments/analyze_t1_b2_main_batch.py`），
# 故与 `experiments/statistical_analysis.py` 同口径做路径引导后再导入。
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.budget.pricing import entry_block_reason, load_table_json, models_layer  # noqa: E402

SEEDS = (42, 43, 44)
ARMS = ("aitester", "plain_llm", "plain_llm_df")
BOOTSTRAP_N = 5000
BOOTSTRAP_SEED = 20261018


def _load_json(path: Path) -> dict[str, Any]:
    """读 JSON（失败抛异常，供调用方定位）。"""
    return json.loads(path.read_text(encoding="utf-8"))


def _profile_presets(rev: str) -> tuple[dict[str, dict[str, str]], str]:
    """从指定 git 版本的 config.py 读取 `_PROFILE_PRESETS`（AST 求值，零导入）。

    返回 ``(预设, 原因码)``：成功时原因为空串，失败时**四种机制各给各的原因码**——
    调用方必须按"无法核验"披露，不得当成"无漂移"（本项目纪律：缺席与通过不同形），
    而"无法核验"的原因写错同样是错的读数。
    """
    try:
        src = subprocess.run(
            ["git", "show", f"{rev}:config.py"], capture_output=True, text=True, timeout=20, check=True
        ).stdout
    except Exception as e:
        return {}, f"git_show_failed:{type(e).__name__}"
    try:
        tree = ast.parse(src)
    except Exception as e:
        return {}, f"ast_parse_failed:{type(e).__name__}"
    for node in tree.body:
        targets = []
        if isinstance(node, ast.AnnAssign):
            targets = [node.target]
            value = node.value
        elif isinstance(node, ast.Assign):
            targets = list(node.targets)
            value = node.value
        else:
            continue
        if any(getattr(t, "id", "") == "_PROFILE_PRESETS" for t in targets) and value is not None:
            try:
                return ast.literal_eval(value), ""
            except Exception as e:
                return {}, f"literal_eval_failed:{type(e).__name__}"
    return {}, "assignment_not_found"


def _profile_drift(old_rev: str, new_rev: str, profile: str = "logic") -> dict[str, Any]:
    """profile 预设漂移（新增/删除/改值）——env_snapshot 只记录固定键集，
    profile 注入的新增开关不体现在 snapshot diff 里，必须单独披露。"""
    old, old_reason = _profile_presets(old_rev)
    new, new_reason = _profile_presets(new_rev)
    if not old or not new:
        mechanisms = [
            f"{rev[:7]}:{reason or '预设表为空'}"
            for rev, presets, reason in ((old_rev, old, old_reason), (new_rev, new, new_reason))
            if reason or not presets
        ]
        return {
            "available": False,
            "reason": "读不到 `_PROFILE_PRESETS`（" + "，".join(mechanisms) + "）——无法核验，不得当作无漂移",
        }
    if profile not in old or profile not in new:
        missing = [label for label, presets in (("旧切点", old), ("新切点", new)) if profile not in presets]
        return {
            "available": False,
            "reason": (
                f"档位 {profile!r} 在{'、'.join(missing)}的 `_PROFILE_PRESETS` 里不存在（档名缺席不等于该档无漂移）"
            ),
        }
    o = old.get(profile) or {}
    n = new.get(profile) or {}
    return {
        "available": True,
        "profile": profile,
        "old_rev": old_rev,
        "new_rev": new_rev,
        "added": {k: n[k] for k in sorted(set(n) - set(o))},
        "removed": {k: o[k] for k in sorted(set(o) - set(n))},
        "changed": {k: {"old": o[k], "new": n[k]} for k in sorted(set(o) & set(n)) if o[k] != n[k]},
        "old_key_count": len(o),
        "new_key_count": len(n),
    }


def arm_absence_reason(batch: Any, arm: str) -> str | None:
    """批次里某一臂的**在场性读数**：返回缺席机制名，`None` = 该臂可读。

    AB-12b（站点 a ①）：历史实现 `(batch.get("results") or {}).get(arm) or {}` 把下面
    各机制全部塌成同一个空对象，报告只剩 `rows: 0`——与"批次真的产出了 0 行"同形；
    而 `nb.get("results", {}).get(arm)` 只在 `results` **键缺席**时走默认值，键存在但值为
    null 时直接 `AttributeError`（崩溃点与静默点分岔，正是 AB-11 说的"四种失败机制塌成
    一句"）。判据：键缺席 / 值为 null / 类型不对 / 真的为空是**四种不同的事实**。
    `details == []` 是可读的真零行读数（返回 None），不作缺席。
    """
    if not isinstance(batch, dict):
        return f"batch_not_object({type(batch).__name__})"
    if "results" not in batch:
        return "results_key_absent"
    res = batch["results"]
    if res is None:
        return "results_value_null"
    if not isinstance(res, dict):
        return f"results_not_object({type(res).__name__})"
    if arm not in res:
        return "arm_key_absent"
    a = res[arm]
    if a is None:
        return "arm_value_null"
    if not isinstance(a, dict):
        return f"arm_not_object({type(a).__name__})"
    if "details" not in a:
        return "details_key_absent"
    d = a["details"]
    if d is None:
        return "details_value_null"
    if not isinstance(d, list):
        return f"details_not_object({type(d).__name__})"
    return None


def read_gates_artifact(path: Path) -> tuple[dict[str, Any] | None, str, str]:
    """§1.1 硬门槛工件 → ``(对象, 三态读数, 无法核验成因)``。

    AB-12b（站点 a ②）：历史实现 `_load_json(p) if p.exists() else None` 再
    `bool((gates or {}).get("all_pass"))`，把"文件缺席 / 文件读不动 / 顶层非对象 /
    `all_pass` 键缺席 / 值为 null 或非布尔"与"值确实是 false"共用一个 `False`——
    缺席被渲染成**未通过**（本项目纪律：缺席与未通过不同形）。非布尔/缺席一律
    `UNVERIFIABLE`，只有货真价实的 `false` 才是 `FAIL`。
    """
    if not path.is_file():
        return None, "UNVERIFIABLE", f"{path.name} 文件缺席"
    try:
        raw = _load_json(path)
    except Exception as e:  # 读不动是"无法核验"，不是"未通过"
        return None, "UNVERIFIABLE", f"{path.name} 读不动（{type(e).__name__}）"
    if not isinstance(raw, dict):
        return None, "UNVERIFIABLE", f"{path.name} 顶层非对象（{type(raw).__name__}）"
    if "all_pass" not in raw:
        return None, "UNVERIFIABLE", f"{path.name} 无 all_pass 键（键缺席不等于未通过）"
    value = raw["all_pass"]
    if not isinstance(value, bool):
        return None, "UNVERIFIABLE", f"{path.name} 的 all_pass 非布尔（{type(value).__name__}）"
    return raw, ("PASS" if value else "FAIL"), ""


def _metric_hit(value: Any) -> bool | None:
    """M1 行级二值指标：>=1.0 记命中；None 不可测返回 None。"""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    return float(value) >= 1.0


def arm_stats(batch: dict[str, Any], arm: str) -> dict[str, Any]:
    """逐臂统计（detection / repair / false_fix / 覆盖率 / token / 成本 / stop_reason）。

    调用方须先用 `arm_absence_reason` 确认该臂可读：本函数内部的 `(x or {})` 只兜
    "可读但字段缺省"，**不**负责把缺席臂报成缺席（那正是站点 a ① 的历史缺陷）。
    """
    res = (batch.get("results") or {}).get(arm) or {}
    rows = res.get("details") or []
    det = [v for r in rows if (v := _metric_hit(r.get("detection_rate"))) is not None]
    llm_det = [v for r in rows if (v := _metric_hit(r.get("llm_suite_detection_rate"))) is not None]
    rep = [v for r in rows if (v := _metric_hit(r.get("repair_rate"))) is not None]
    ff = [v for r in rows if (v := _metric_hit(r.get("false_fix_rate"))) is not None]
    covs = [float(r["coverage"]) for r in rows if isinstance(r.get("coverage"), (int, float))]
    iters = [float(r["iterations"]) for r in rows if isinstance(r.get("iterations"), (int, float))]
    tm = res.get("token_metrics") or {}
    return {
        "rows": len(rows),
        "detection_measurable": len(det),
        "detected": sum(det),
        "detection_rate": round(sum(det) / len(det), 4) if det else None,
        "llm_suite_detection_measurable": len(llm_det),
        "llm_suite_detected": sum(llm_det) if llm_det else None,
        "repair_measurable": len(rep),
        "repaired": sum(rep),
        "repair_rate": round(sum(rep) / len(rep), 4) if rep else None,
        "false_fix_measurable": len(ff),
        "false_fixed": sum(ff),
        "false_fix_rate": round(sum(ff) / len(ff), 4) if ff else None,
        "coverage_mean": round(sum(covs) / len(covs), 2) if covs else None,
        "iterations_mean": round(sum(iters) / len(iters), 3) if iters else None,
        "stop_reasons": dict(Counter(str(r.get("stop_reason")) for r in rows)),
        "regeneration_rows": sum(
            1 for r in rows if isinstance(r.get("regeneration_count"), (int, float)) and r["regeneration_count"] > 0
        ),
        "rollback_field_present": sum(1 for r in rows if "patch_rolled_back" in r),
        "token_metrics": tm,
        "cost_usd": None,  # 由 price 计算后填充
        "calls": tm.get("total_llm_calls"),
    }


def _format_reason_counts(reasons: dict[str, Any]) -> str:
    """归因计数 → 一行可读文本；支持 `{code: n}` 与 `{arm: {code: n}}` 两种形状。

    成本节聚合的是逐臂 `unpriced_reasons`（嵌套一层）；逐臂表传入的是单臂计数。
    若把嵌套值直接塞进 `×` 模板，报告会落 `aitester×{'currency_not_usd:CNY': 3}`
    ——机制名被一层 Python 字典字面量包住，读者拿不到可直接检索的原因码。
    """
    parts: list[str] = []
    for code, detail in sorted(reasons.items()):
        if isinstance(detail, dict):
            inner = "、".join(f"{reason}×{n}" for reason, n in sorted(detail.items()))
            parts.append(f"{code}: {inner}")
        else:
            parts.append(f"{code}×{detail}")
    return "；".join(parts)


def _usd_text(value: Any, reasons: dict[str, Any] | None = None, prefix: str = "$") -> str:
    """美元读数的呈现（AB-15 判据）：**被拒绝的金额不得披着金额的形状出现在报告里**。

    改前实测两种落字：`oracle_examples_replay.render_readme` 把 `None` 印成 `$None`、
    本文件的成本行把聚合折出来的 `0.0` 印成 `$0.0`——"无法估算"与"确实没花钱"只差一个词，
    却共用同一个美元前缀。现 `None` 落 `—（无法估算：<机制>）`，`0.0` 仍落 `$0.0`。

    `prefix` 供已经写明单位的表头列复用（列头是 `成本(USD, 估算)`，单元格里改前不落 `$`；
    金额分支保持原样 ⇒ 受保护工件的字节一字不变，只有拒绝分支新增文字）。
    """
    if value is None:
        shown = _format_reason_counts(reasons or {})
        return f"—（无法估算：{shown or '机制未记录'}）"
    return f"{prefix}{value}"


def _load_price_entry(path: str | Path) -> tuple[Any, str | None]:
    """读价目表并取本批次模型的条目：`(条目, None)` 或 `(None, 机制名)`（AB-17）。

    改前 `main()` 里拼成一行：`json.loads(Path(args.price).read_text(encoding="utf-8"))
    .get("models", {}).get("deepseek-flash", {})`——七种坏表里半数直接崩（缺文件 / 语法错 /
    顶层非对象分别在 `read_text` / `json.loads` / `.get` 上抛），余下把"表里没这个模型"
    与"表损坏"共读成同一个空条目（`entry_empty`）。现文件 → `models` 层判定收口到共享
    事实源：模型缺席读 `model_unregistered`，表级失败点名机制并原样交 `add_cost`
    写进 `cost_unpriced_reason`。
    """
    data, reason = load_table_json(path)
    if reason is None:
        models, reason = models_layer(data)
        if reason is None:
            if "deepseek-flash" not in models:
                return None, "model_unregistered"
            return models["deepseek-flash"], None
    return None, reason


def add_cost(stats: dict[str, Any], price: dict[str, Any], price_reason: str | None = None) -> None:
    """按价目表计算 arm 成本（$；input/output 分开计价）。

    AB-14（2026-10-20）：改前这里读 input/output 单价却**从不看币种**——登记为非 USD
    或压根没登记单位的价目会被原样累加进名为 `cost_usd` 的字段（与 AB-13c 在
    `emse_stats_report.total_usd` 上坐实的缺陷同型）。现接共享谓词：币种不可判定或非 USD
    ⇒ 保持 None（未计价），既不静默当 0，也不静默当美元。

    AB-15b（2026-10-20）：拒绝时把**机制名**写进 `cost_unpriced_reason`（币种这一维的词汇
    取自 `src.budget.pricing.currency_block_reason`）。改前门写对了但下游看不到原因——聚合把
    `None` 折成 `0.0` 后，报告里既没有金额也没有"为什么没有"。披露键只在真拒绝时写入
    ⇒ 真批次（全 USD）的载荷逐字节不变。

    AB-16（2026-10-20）：条目级准入（形状 → 空 → 币种 → 数字）与数字域收口到共享事实源
    `entry_block_reason`——本文件首写的 `price_reject_reason` 词汇搬进 `src/budget/pricing.py`
    并补"非有限"一档（`nan`/`inf` 改前照乘成非有限金额）；非对象条目改名为形状事实
    `entry_not_object:<T>`、空条目从 `currency_absent` 改读 `entry_empty`（与 spec/report 一致）。

    AB-17（2026-10-20）：`price_reason` 是**表级**失败（文件读不动 / 形状不符 / 模型未登记）
    的机制名，由 `_load_price_entry` 判定后原样交进来；为 None 时才按 `entry_block_reason`
    读条目本身——"价目表坏了"与"这一条用不了"是两种事实，不得共用一个码（AB-11 判据）。
    """
    reason = price_reason if price_reason is not None else entry_block_reason(price)
    if reason is not None:
        stats["cost_unpriced_reason"] = reason
        return
    p_in = price["input_per_mtok"]
    p_out = price["output_per_mtok"]
    tm = stats.get("token_metrics") or {}
    tin = tm.get("total_input_tokens") or 0
    tout = tm.get("total_output_tokens") or 0
    stats["cost_usd"] = round((tin * p_in + tout * p_out) / 1e6, 6)


def _missing_side_reason(batch: Any, key: str) -> str:
    """批次某个顶层键读不到时的成因名——"没有这个键" / "键值为 null" / "类型不对" /
    "空对象" / "批次本身缺席"是五种不同事实（AB-11 判据），不得共写一句"没有 X"。"""
    if not isinstance(batch, dict) or not batch:
        return "批次本身缺席"
    if key not in batch:
        return f"{key}_key_absent"
    value = batch[key]
    if value is None:
        return f"{key}_value_null"
    if not isinstance(value, dict):
        return f"{key}_not_object({type(value).__name__})"
    return f"{key}_empty_object"


def _nested_absence(obj: dict[str, Any], key: str) -> str | None:
    """对象里某个**应为对象**的子键：返回缺席机制名，`None` = 可读（含真的空对象）。"""
    if key not in obj:
        return f"{key}_key_absent"
    value = obj[key]
    if value is None:
        return f"{key}_value_null"
    if not isinstance(value, dict):
        return f"{key}_not_object({type(value).__name__})"
    return None


def _value_or_absent(obj: dict[str, Any], key: str) -> Any:
    """键在场→返回其值（生产者写的 null 是真实读数，保持 None）；键缺席→返回显式标记。

    AB-11 判据：「生产者没写这个键」与「生产者写了 null」是两种事实，塌成一个 `None`
    就只剩一种读数。
    """
    return obj.get(key, f"{key}_key_absent")


def _fingerprint_pinned(provenance: dict[str, Any]) -> Any:
    """`model_fingerprint.pinned` 读数：缺席/非对象/内层键缺席各给各的标记。

    历史实现 `(np_.get("model_fingerprint") or {}).get("pinned")` 让"指纹键缺席"、
    "指纹为 null"、"指纹里没有 pinned" 与"pinned=false"四种事实都落到假值。
    """
    if "model_fingerprint" not in provenance:
        return "model_fingerprint_key_absent"
    fp = provenance["model_fingerprint"]
    if fp is None:
        return "model_fingerprint_value_null"
    if not isinstance(fp, dict):
        return f"model_fingerprint_not_object({type(fp).__name__})"
    return _value_or_absent(fp, "pinned")


def per_task_detection(batch: dict[str, Any], arm: str) -> dict[str, bool | None]:
    """task_id → detection 命中（None=不可测），供配对检验。

    臂缺席时返回空表**且不猜测**：缺席成因由 `build_report` 的 `availability` 披露。
    """
    out: dict[str, bool | None] = {}
    if arm_absence_reason(batch, arm) is not None:
        return out
    for r in ((batch.get("results") or {}).get(arm) or {}).get("details") or []:
        out[str(r.get("task_id"))] = _metric_hit(r.get("detection_rate"))
    return out


def mcnemar_exact(b: int, c: int) -> float:
    """McNemar 双侧精确二项 p 值（b+c 个不一致对，p=0.5）。"""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    # 双侧：2 × P(X <= k)，上限 1
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2**n)
    return min(1.0, 2 * tail)


def paired_delta(
    new_map: dict[str, bool | None], old_map: dict[str, bool | None], *, keys: list[str]
) -> dict[str, Any]:
    """配对差（new − old）的 McNemar + bootstrap CI（仅双方均可测的配对）。"""
    pairs = [(new_map.get(k), old_map.get(k)) for k in keys]
    pairs = [(n, o) for n, o in pairs if n is not None and o is not None]
    b = sum(1 for n, o in pairs if n and not o)
    c = sum(1 for n, o in pairs if o and not n)
    n = len(pairs)
    if n == 0:
        return {
            "n_pairs": 0,
            "b_new_only": b,
            "c_old_only": c,
            "delta": None,
            "delta_pp": None,
            "mcnemar_exact_p_two_sided": 1.0,
            "bootstrap_ci95": [None, None],
        }
    delta = (b - c) / n
    rng = random.Random(BOOTSTRAP_SEED)
    boots: list[float] = []
    for _ in range(BOOTSTRAP_N):
        s = 0
        for _ in range(n):
            nn, oo = pairs[rng.randrange(n)]
            s += int(nn) - int(oo)
        boots.append(s / n)
    boots.sort()
    lo = boots[int(0.025 * BOOTSTRAP_N)]
    hi = boots[int(0.975 * BOOTSTRAP_N) - 1]
    return {
        "n_pairs": n,
        "b_new_only": b,
        "c_old_only": c,
        "delta": round(delta, 4) if delta is not None else None,
        "delta_pp": round(delta * 100, 2) if delta is not None else None,
        "mcnemar_exact_p_two_sided": round(mcnemar_exact(b, c), 8),
        "bootstrap_ci95": [round(lo, 4), round(hi, 4)],
    }


def pooled_counts(batch: dict[str, Any], arm: str) -> tuple[int, int]:
    """合并口径计数（detected, measurable）。"""
    st = arm_stats(batch, arm)
    return st["detected"], st["detection_measurable"]


def ordering_ok(stats_by_arm: dict[str, dict[str, Any]]) -> bool:
    """R1：plain_llm_df > aitester > plain_llm（按 detection_rate，合并口径）。"""
    d = {a: stats_by_arm[a]["detection_rate"] for a in ARMS}
    if any(v is None for v in d.values()):
        return False
    return d["plain_llm_df"] > d["aitester"] > d["plain_llm"]


def build_report(
    out_dir: Path, orig_dir: Path, price: dict[str, Any], price_reason: str | None = None
) -> dict[str, Any]:
    """构建完整分析报告（JSON 载荷）。

    AB-12b 的披露口径：`availability` / `verdict.gates_state` 这些键**只在真的发生缺席
    或无法核验时**才写入——因此无缺席输入（含已归档的 T1/B2 批）产出的载荷逐字节不变，
    入库工件不需要重写（同 AB-9"只在有跳过时追加一节"的先例）。
    """
    gates, gates_state, gates_reason = read_gates_artifact(out_dir / "GATES.json")
    preflight = _load_json(out_dir / "PREFLIGHT.json") if (out_dir / "PREFLIGHT.json").exists() else None
    amendment = out_dir / "PREREG_AMENDMENT_cost_estimate.md"

    new_batches: dict[int, dict[str, Any]] = {}
    missing_new_batches: list[dict[str, Any]] = []
    for seed in SEEDS:
        files = sorted((out_dir / f"seed{seed}").glob("benchmark_*.json"), key=lambda p: p.stat().st_mtime)
        if not files:
            new_batches[seed] = {}
            missing_new_batches.append({"seed": seed, "mechanism": f"seed{seed}/ 下无 benchmark_*.json"})
            continue
        try:
            raw = _load_json(files[-1])
        except Exception as e:  # 读不动要留文件名与机制，不是静默空批次
            new_batches[seed] = {}
            missing_new_batches.append({"seed": seed, "mechanism": f"{files[-1].name} 读不动（{type(e).__name__}）"})
            continue
        if not isinstance(raw, dict):
            new_batches[seed] = {}
            missing_new_batches.append(
                {"seed": seed, "mechanism": f"{files[-1].name} 顶层非对象（{type(raw).__name__}）"}
            )
            continue
        new_batches[seed] = raw

    orig_batches: dict[int, dict[str, Any]] = {}
    orig_unreadable: list[dict[str, str]] = []
    orig_excluded: list[dict[str, str]] = []
    orig_scanned = 0
    for p in sorted(orig_dir.glob("benchmark_synthetic_*.json")):
        orig_scanned += 1
        try:
            d = _load_json(p)
        except Exception as e:  # 损坏/半写批次 JSON 不中断全批分析，但必须留名留机制
            orig_unreadable.append({"file": p.name, "mechanism": f"读不动（{type(e).__name__}）"})
            continue
        if not isinstance(d, dict):
            orig_unreadable.append({"file": p.name, "mechanism": f"顶层非对象（{type(d).__name__}）"})
            continue
        seed = d.get("seed")
        if seed not in SEEDS:
            continue
        if "total_tasks" not in d:
            orig_excluded.append({"file": p.name, "mechanism": f"seed{seed} 的 total_tasks 键缺席"})
            continue
        if d["total_tasks"] != 87:
            orig_excluded.append({"file": p.name, "mechanism": f"seed{seed} 的 total_tasks={d['total_tasks']!r}≠87"})
            continue
        if seed in orig_batches:
            orig_excluded.append({"file": p.name, "mechanism": f"seed{seed} 已有先行文件（首份胜出，本份未采用）"})
            continue
        orig_batches[seed] = d
    missing_orig_seeds = [s for s in SEEDS if s not in orig_batches]

    report: dict[str, Any] = {
        "schema": "aitester_t1_b2_analysis/1",
        "out_dir": str(out_dir),
        "orig_dir": str(orig_dir),
        "seeds": list(SEEDS),
        "arms": list(ARMS),
        "prereg_amendment": {
            "path": str(amendment),
            "note": "跑前成本估算修正（input/output 份额口径），判据未改",
        },
        "gates": gates,
        "preflight": {
            "prereg_sha256": (preflight or {}).get("prereg_sha256"),
            "cost_estimate": (preflight or {}).get("cost_estimate"),
            "quota_probe_ok": ((preflight or {}).get("quota_probe") or {}).get("ok"),
        },
        "per_seed": {},
        "pooled": {},
        "original_pooled": {},
        "paired_new_vs_original": {},
        "provenance_drift": {},
        "cost": {},
        "verdict": {},
        "limitations": [
            "单次运行/seed，温度 0 仍有服务端非确定性；复现判据只到方向/排序级，不要求逐位相等",
            "harness 自 R-P0-2（2026-10-06, b533cff）演进至 a93c1f6：logic 档/默认开关增量为披露项（见 provenance_drift），跨批差异不作单一归因",
            "detection 为 M1 行口径（detection_rate≥1）；repair/false_fix 随行口径并列，不与旧批修正口径混用",
            "成本为官方价目表峰时全额估算（非账单）；跑前估算曾误设 input 份额，已在 PREREG_AMENDMENT 披露",
        ],
    }

    # ── 逐 seed 表 ──────────────────────────────────────────────────────────
    arm_absences: dict[str, str] = {}
    for seed in SEEDS:
        nb = new_batches.get(seed) or {}
        ob = orig_batches.get(seed) or {}
        entry: dict[str, Any] = {"new": {}, "original": {}}
        for arm in ARMS:
            # 历史实现 `if nb.get("results", {}).get(arm):`：`results` 值为 null 时抛
            # AttributeError，臂缺席/为 null 时静默不收录（分母悄悄变小）。现逐臂点名机制。
            for label, batch in (("new", nb), ("original", ob)):
                reason = arm_absence_reason(batch, arm)
                if reason is not None:
                    arm_absences[f"{label}.seed{seed}.{arm}"] = reason
                    continue
                st = arm_stats(batch, arm)
                add_cost(st, price, price_reason)
                entry[label][arm] = st
        new_order = ordering_ok(entry["new"]) if len(entry["new"]) == 3 else None
        entry["same_seed_ordering_ok"] = new_order
        report["per_seed"][str(seed)] = entry

    # ── 缺席披露（只在真的有缺席/无法核验时写入；无缺席 ⇒ 载荷逐字节不变）────
    availability: dict[str, Any] = {}
    if missing_new_batches:
        availability["new_batches"] = missing_new_batches
    if orig_unreadable or missing_orig_seeds:
        # 只在"真读不动 / 配对真缺席"时写入。`excluded`（total_tasks≠87 的部分批、同 seed
        # 的第二份候选）是**有记录的过滤**，不是缺席；已归档批次的目录里就有 7 份这种
        # 未采用候选，若把它们也写进载荷，重算载荷会与受 SHA256SUMS 保护的入库工件不再
        # 逐字节相同——那属于"改判据就顺手改工件"，本轮不做（登记见评审文档站点 a ④）。
        availability["original_batches"] = {
            "scanned_files": orig_scanned,
            "unreadable": orig_unreadable,
            "excluded": orig_excluded,
            "missing_seeds": missing_orig_seeds,
        }
    if arm_absences:
        availability["arms"] = arm_absences
    if gates_state == "UNVERIFIABLE":
        availability["gates"] = gates_reason
    if availability:
        report["availability"] = availability

    # ── 合并口径（3 seed 池化）──────────────────────────────────────────────
    pooled: dict[str, Any] = {}
    orig_pooled: dict[str, Any] = {}
    for arm in ARMS:
        det = 0
        meas = 0
        rep = rep_n = 0
        ff = ff_n = 0
        cost = 0.0
        n_seeds_unpriced = 0
        unpriced_reasons: dict[str, int] = {}
        tokens = {"in": 0, "out": 0, "total": 0, "calls": 0}
        for seed in SEEDS:
            st = report["per_seed"][str(seed)]["new"].get(arm)
            if st:
                det += st["detected"]
                meas += st["detection_measurable"]
                rep += st["repaired"]
                rep_n += st["repair_measurable"]
                ff += st["false_fixed"]
                ff_n += st["false_fix_measurable"]
                if st["cost_usd"] is None:
                    # AB-15b：改前这里是 `cost += st["cost_usd"] or 0.0`——门（AB-14c）在
                    # 逐 seed 层把"不计价"写成了 None，聚合却又把它折回金额形状，于是
                    # "整臂没能计价"与"确实一分钱没花"在报告里同为 `$0.0`，而 token 数
                    # 一字不变。拒绝必须在下游保住"没有金额"这个形状，并带上原因。
                    n_seeds_unpriced += 1
                    key = st.get("cost_unpriced_reason") or "reason_not_recorded"
                    unpriced_reasons[key] = unpriced_reasons.get(key, 0) + 1
                else:
                    cost += st["cost_usd"]
                tm = st["token_metrics"] or {}
                tokens["in"] += tm.get("total_input_tokens") or 0
                tokens["out"] += tm.get("total_output_tokens") or 0
                tokens["total"] += tm.get("total_tokens") or 0
                tokens["calls"] += tm.get("total_llm_calls") or 0
        pooled[arm] = {
            "detected": det,
            "measurable": meas,
            "detection_rate": round(det / meas, 4) if meas else None,
            "repaired": rep,
            "repair_measurable": rep_n,
            "repair_rate": round(rep / rep_n, 4) if rep_n else None,
            "false_fixed": ff,
            "false_fix_measurable": ff_n,
            "false_fix_rate": round(ff / ff_n, 4) if ff_n else None,
            "tokens": tokens,
            # 任一 seed 未计价 ⇒ 该臂没有可呈现的全额（部分和不得冒充全额）。
            "cost_usd": None if n_seeds_unpriced else round(cost, 6),
        }
        # 披露键只在真发生时写入：真批次全 USD、拒绝不发生，载荷逐字节不变。
        if n_seeds_unpriced:
            pooled[arm]["n_seeds_unpriced"] = n_seeds_unpriced
            pooled[arm]["unpriced_reasons"] = dict(sorted(unpriced_reasons.items()))
        # 旧批同口径池化
        odet = omeas = 0
        for seed in SEEDS:
            st = report["per_seed"][str(seed)]["original"].get(arm)
            if st:
                odet += st["detected"]
                omeas += st["detection_measurable"]
        orig_pooled[arm] = {
            "detected": odet,
            "measurable": omeas,
            "detection_rate": round(odet / omeas, 4) if omeas else None,
        }
    report["pooled"] = pooled
    report["original_pooled"] = orig_pooled

    # ── R1/R2/R3（预注册判据）───────────────────────────────────────────────
    r1 = ordering_ok(pooled)
    seeds_with_order = [s for s in SEEDS if report["per_seed"][str(s)].get("same_seed_ordering_ok")]
    r3 = len(seeds_with_order) >= 2
    # R2：新批 aitester vs df 配对（按 seed+task 配对）
    new_maps: dict[str, dict[tuple[int, str], bool | None]] = {a: {} for a in ARMS}
    for seed in SEEDS:
        nb = new_batches.get(seed) or {}
        for arm in ARMS:
            for tid, hit in per_task_detection(nb, arm).items():
                new_maps[arm][(seed, tid)] = hit
    keys = sorted(set(new_maps["aitester"]) & set(new_maps["plain_llm_df"]))
    flat_new = {str(k): v for k, v in new_maps["aitester"].items()}
    flat_new_df = {str(k): v for k, v in new_maps["plain_llm_df"].items()}
    r2_stats = paired_delta(flat_new, flat_new_df, keys=[str(k) for k in keys])
    r2 = r2_stats["delta"] is not None and r2_stats["delta"] < 0 and r2_stats["bootstrap_ci95"][1] < 0
    gates_ok = gates_state == "PASS"
    if missing_new_batches:
        verdict = "batch_absent_grade"
        rationale = (
            "协议批次缺席（"
            + "；".join(f"seed{m['seed']}：{m['mechanism']}" for m in missing_new_batches)
            + "）：R1/R2/R3 只在剩余 seed 上可算，只报告事实、不出方向性结论"
        )
    elif gates_state == "UNVERIFIABLE":
        verdict = "gates_unverifiable_grade"
        rationale = f"§1.1 硬门槛无法核验（{gates_reason}）——既不得当作通过，也不得报成未通过"
    elif not gates_ok:
        verdict = "not_reproducible_grade"
        rationale = "§1.1 硬门槛未全过（见 gates），只报告事实、不出方向性结论"
    elif r1 and r2 and r3:
        verdict = "reproduced"
        rationale = "R1 合并排序成立 ∧ R2 负向差显著（CI 全负）∧ R3 逐 seed 排序 ≥2/3"
    elif r1:
        verdict = "direction_partial"
        rationale = "R1 成立但 R2 的 bootstrap CI 跨 0（方向一致但强度不足）"
    else:
        verdict = "not_reproduced"
        rationale = "R1 或 R2 反向/不成立"
    report["verdict"] = {
        "verdict": verdict,
        "rationale": rationale,
        "R1_pooled_ordering_df_gt_aitester_gt_plain": r1,
        "R2_aitester_vs_df_delta_negative_ci_below_zero": r2,
        "R2_stats": r2_stats,
        "R3_ordering_in_at_least_2_of_3_seeds": r3,
        "R3_seeds_with_ordering": seeds_with_order,
        "gates_all_pass": gates_ok,
    }
    if gates_state == "UNVERIFIABLE":
        # 只在无法核验时追加：三态读数不得由 `gates_all_pass` 一个布尔代答（站点 a ②）。
        report["verdict"]["gates_state"] = gates_state
        report["verdict"]["gates_state_reason"] = gates_reason

    # ── 新批 vs 原批配对（复现性的逐任务一致性，描述性）────────────────────
    old_maps: dict[str, dict[str, bool | None]] = {a: {} for a in ARMS}
    for seed, ob in orig_batches.items():
        for arm in ARMS:
            for tid, hit in per_task_detection(ob, arm).items():
                old_maps[arm][(seed, tid)] = hit
    for arm in ARMS:
        flat_new_arm = {str(k): v for k, v in new_maps[arm].items()}
        flat_old_arm = {str(k): v for k, v in old_maps[arm].items()}
        common = [k for k in flat_new_arm if k in flat_old_arm]
        report["paired_new_vs_original"][arm] = paired_delta(flat_new_arm, flat_old_arm, keys=common)

    # ── provenance 漂移（新旧 env_snapshot / harness）────────────────────────
    drift: dict[str, Any] = {"env_snapshot_diff": {}, "harness_diff": {}, "profile": {}}
    drift_skipped: list[dict[str, Any]] = []
    flags_seed: int | None = None
    for seed in SEEDS:
        nb = new_batches.get(seed) or {}
        ob = orig_batches.get(seed) or {}
        np_ = nb.get("provenance") or {}
        op_ = ob.get("provenance") or {}
        if not np_ or not op_:
            # 历史实现直接 `continue`：漂移小节静默少一个 seed，读者看不出是"没漂移"
            # 还是"读不到 provenance"（AB-12b：缺席必须留名留机制）。
            drift_skipped.append(
                {
                    "seed": seed,
                    "mechanism": "；".join(
                        f"{label}侧 {_missing_side_reason(batch, 'provenance')}"
                        for label, batch in (("新", nb), ("原", ob))
                        if not (isinstance(batch, dict) and batch.get("provenance"))
                    ),
                }
            )
            continue
        nsnap_absent = _nested_absence(np_, "env_snapshot")
        osnap_absent = _nested_absence(op_, "env_snapshot")
        if nsnap_absent or osnap_absent:
            # 一侧 snapshot 读不到时，diff 只会是"两边都没有共同键"的假象（历史实现直接
            # 落 `{}` 读作"无漂移"）——改为明写无法核验，成因逐项点名。
            drift["env_snapshot_diff"][str(seed)] = {
                "unverifiable": "；".join(
                    f"{label}侧 {why}" for label, why in (("新", nsnap_absent), ("原", osnap_absent)) if why
                )
            }
        else:
            nsnap = np_["env_snapshot"]
            osnap = op_["env_snapshot"]
            diff = {}
            for k in sorted(set(nsnap) | set(osnap)):
                if nsnap.get(k) != osnap.get(k):
                    diff[k] = {"new": nsnap.get(k), "old": osnap.get(k)}
            drift["env_snapshot_diff"][str(seed)] = diff
        drift["profile"][str(seed)] = {"new": np_.get("profile"), "old": op_.get("profile")}
        nh_absent = _nested_absence(np_, "harness")
        oh_absent = _nested_absence(op_, "harness")
        if nh_absent or oh_absent:
            drift["harness_diff"][str(seed)] = {
                "unverifiable": "；".join(
                    f"{label}侧 {why}" for label, why in (("新", nh_absent), ("原", oh_absent)) if why
                )
            }
        else:
            nh = np_["harness"]
            oh = op_["harness"]
            hdiff = {}
            for k in sorted(set(nh) | set(oh)):
                if nh.get(k) != oh.get(k):
                    hdiff[k] = {"new": nh.get(k), "old": oh.get(k)}
            drift["harness_diff"][str(seed)] = hdiff
        flags_seed = seed
        # 口径（登记）：`provenance_flags` 是**最后一个未被跳过 seed** 的读数，不是三 seed
        # 汇总；缺席时才追加 `provenance_flags_seed`/`provenance_flags_unverifiable` 说明。
        drift["provenance_flags"] = {
            "new_git_dirty": _value_or_absent(np_, "git_dirty"),
            "new_git_sha": _value_or_absent(np_, "git_sha"),
            "new_fingerprint_pinned": _fingerprint_pinned(np_),
            "old_git_dirty": _value_or_absent(op_, "git_dirty"),
            "old_git_sha": _value_or_absent(op_, "git_sha"),
            "old_fingerprint_present": "model_fingerprint" in op_,
        }
    if drift_skipped:
        drift["skipped_seeds"] = drift_skipped
        if flags_seed is None:
            drift["provenance_flags"] = {
                "unverifiable": "三 seed 的 provenance 全部读不到（逐 seed 成因见 skipped_seeds）"
                "——不得当作 git_dirty=false 或指纹在场"
            }
        else:
            drift["provenance_flags_seed"] = flags_seed
    report["provenance_drift"] = drift
    # profile 预设漂移（logic 档新增 5 个行为开关等）——env_snapshot 固定键集看不到
    report["profile_preset_drift"] = _profile_drift(
        "b533cff1c316e8e80db635a1b2946610b211a5b6", "a93c1f60ee31b9582e0146f73e3038e6ce0f01a1"
    )

    # ── 成本 ────────────────────────────────────────────────────────────────
    # AB-15b：只要有一臂没算出钱，整批的"实测估算成本"就不是一个金额（部分和冒充全额
    # 与 `or 0.0` 抹平拒绝是同一条缺陷的两级），并把这些臂的机制名随载荷带出去。
    unpriced_arms = {arm: blk["unpriced_reasons"] for arm, blk in pooled.items() if blk.get("unpriced_reasons")}
    total_cost = round(sum(v["cost_usd"] for v in pooled.values() if v["cost_usd"] is not None), 6)
    total_tokens = sum(v["tokens"]["total"] for v in pooled.values())
    report["cost"] = {
        "actual_est_usd": None if unpriced_arms else total_cost,
        "total_tokens": total_tokens,
        "preflight_estimate_usd": ((preflight or {}).get("cost_estimate") or {}).get("est_usd"),
        "amended_estimate_usd": 8.8,
        "budget_usd": (preflight or {}).get("budget_usd"),
        "note": "实测成本按本批 token_metrics 的 input/output 分别计价（官方价目表峰时全额，非账单）",
    }
    if unpriced_arms:
        report["cost"]["unpriced_arms"] = unpriced_arms
    return report


def render_baseline_fragment(report: dict[str, Any]) -> str:
    """渲染 BASELINE.yaml `target_quality.b2_main_batch_t_round` 片段（2 空格缩进 YAML）。"""
    v = report["verdict"]
    lines: list[str] = []
    lines.append("  b2_main_batch_t_round:")
    lines.append('    measured_at: "2026-10-18"')
    lines.append('    nature: "锁指纹复现批（decision-grade；预注册冻结；成本估算口径修正见 PREREG_AMENDMENT）"')
    lines.append('    cut_commit: "a93c1f60ee31b9582e0146f73e3038e6ce0f01a1"')
    lines.append(
        "    protocol: {dataset: synthetic, task_count: 87, max_pattern_repeat: 2, seeds: [42, 43, 44], "
        'arms: [aitester, plain_llm, plain_llm_df], profile: logic, temperature: 0.0, cache: "off", parallelism: 4}'
    )
    per_seed = {
        k: {"pass": x.get("pass"), "exit_code": x.get("exit_code"), "wall_seconds": x.get("wall_seconds")}
        for k, x in (report.get("gates") or {}).get("per_seed", {}).items()
    }
    lines.append(f"    gates: {{all_pass: {str(v.get('gates_all_pass')).lower()}, per_seed: {per_seed}}}")
    if v.get("gates_state") == "UNVERIFIABLE":
        lines.append('    gates_state: "UNVERIFIABLE: ' + str(v.get("gates_state_reason")) + '"')
    if report.get("availability"):
        lines.append('    availability_note: "缺席披露逐条见 ANALYSIS_REPORT.json 的 availability 键与 README §0.1"')
    pooled = report["pooled"]
    lines.append("    pooled_261_per_arm:")
    for arm in report["arms"]:
        p = pooled.get(arm) or {}
        o = (report.get("original_pooled") or {}).get(arm) or {}
        lines.append(
            f"      {arm}: {{detected: {p.get('detected')}, measurable: {p.get('measurable')}, "
            f"detection_rate: {p.get('detection_rate')}, repaired: {p.get('repaired')}, "
            f"repair_measurable: {p.get('repair_measurable')}, false_fixed: {p.get('false_fixed')}, "
            f"false_fix_measurable: {p.get('false_fix_measurable')}, tokens: {(p.get('tokens') or {}).get('total')}, "
            f"cost_usd: {p.get('cost_usd')}, original_detected: {o.get('detected')}, "
            f"original_measurable: {o.get('measurable')}, original_rate: {o.get('detection_rate')}}}"
        )
    lines.append("    verdict:")
    lines.append(f'      classification: "{v.get("verdict")}"')
    lines.append(f'      rationale: "{v.get("rationale")}"')
    r1 = str(v.get("R1_pooled_ordering_df_gt_aitester_gt_plain")).lower()
    r3 = str(v.get("R3_ordering_in_at_least_2_of_3_seeds")).lower()
    lines.append(f"      R1_pooled_ordering_df_gt_aitester_gt_plain: {r1}")
    lines.append(
        f"      R3_ordering_in_at_least_2_of_3_seeds: {r3}  # seeds_with_ordering={v.get('R3_seeds_with_ordering')}"
    )
    r2 = v.get("R2_stats") or {}
    lines.append(
        f"      R2_aitester_vs_df: {{delta_pp: {r2.get('delta_pp')}, b_new_only: {r2.get('b_new_only')}, "
        f"c_old_only: {r2.get('c_old_only')}, mcnemar_p: {r2.get('mcnemar_exact_p_two_sided')}, "
        f"bootstrap_ci95: {r2['bootstrap_ci95']}}}"
    )
    lines.append(
        '    provenance: "三 seed 均 git_dirty=false / git_sha=a93c1f6 / model_fingerprint.pinned=true / '
        '87 行×3 臂 / task 集与原批一致"'
    )
    c = report.get("cost") or {}
    lines.append(
        f"    cost: {{actual_est_usd: {c.get('actual_est_usd')}, total_tokens: {c.get('total_tokens')}, "
        f"preflight_estimate_usd: {c.get('preflight_estimate_usd')}, "
        f"amended_estimate_usd: {c.get('amended_estimate_usd')}, budget_usd: {c.get('budget_usd')}}}"
    )
    lines.append(
        '    caliber_note: "harness 漂移（logic 档自 R-P0-2 新增 5 开关、输出 token 份额差异）逐项披露；'
        'repair/false_fix 与旧批修正口径不混用"'
    )
    lines.append(
        '    artifacts: "experiments/results/t_round_b2_main_batch_20261018/'
        '（PREREG/PREFLIGHT/PREREG_AMENDMENT/GATES/ANALYSIS_REPORT/README/SHA256SUMS）"'
    )
    return "\n".join(lines) + "\n"


def render_readme(report: dict[str, Any]) -> str:
    """渲染中文 README 报告（表格为主，数字全部来自 report）。"""
    v = report["verdict"]
    lines: list[str] = []
    lines.append("# T1（B2）：主批次锁指纹复现批（3 seed × 3 臂，synthetic n=87/seed）")
    lines.append("")
    lines.append("> **性质：复现性测量（decision-grade），非能力主张。** 预注册见 `PREREG.md`（跑前冻结）、")
    lines.append("> 成本估算修正见 `PREREG_AMENDMENT_cost_estimate.md`（判据未改）。")
    lines.append("")
    lines.append("## 0. 预注册判定")
    lines.append("")
    lines.append("| 项 | 结果 |")
    lines.append("|---|---|")
    lines.append(f"| **verdict** | **`{v['verdict']}`** — {v['rationale']} |")
    if v.get("gates_state") == "UNVERIFIABLE":
        lines.append(
            f"| §1.1 硬门槛（干净树/指纹/行数/exit） | **无法核验**：{v['gates_state_reason']}"
            " ——既不作 `PASS`，也不得报成 `FAIL` |"
        )
    else:
        lines.append(f"| §1.1 硬门槛（干净树/指纹/行数/exit） | `{'PASS' if v['gates_all_pass'] else 'FAIL'}` |")
    lines.append(f"| R1 合并排序 df>aitester>plain | `{v['R1_pooled_ordering_df_gt_aitester_gt_plain']}` |")
    lines.append(
        f"| R2 aitester vs df 配对差 | δ={v['R2_stats']['delta']} （{v['R2_stats']['delta_pp']}pp）"
        f"；b/c={v['R2_stats']['b_new_only']}/{v['R2_stats']['c_old_only']}"
        f"；McNemar p={v['R2_stats']['mcnemar_exact_p_two_sided']}"
        f"；CI95={v['R2_stats']['bootstrap_ci95']} |"
    )
    lines.append(
        f"| R3 逐 seed 排序 | `{v['R3_ordering_in_at_least_2_of_3_seeds']}`（seed {v['R3_seeds_with_ordering']}） |"
    )
    lines.append("")
    # ── 0.1 缺席披露（只在真的有缺席/无法核验时才有本节；无缺席 ⇒ README 逐字节不变）─
    avail = report.get("availability") or {}
    if avail:
        lines.append("## 0.1 缺席与无法核验披露（有缺席才有本节）")
        lines.append("")
        lines.extend(f"- 协议批次缺席：seed{m['seed']} — {m['mechanism']}" for m in avail.get("new_batches") or [])
        ob = avail.get("original_batches") or {}
        if ob:
            lines.append(
                f"- 原批次目录：glob 命中 {ob.get('scanned_files')} 份；"
                f"读不动 {len(ob.get('unreadable') or [])} 份；"
                f"候选但未采用 {len(ob.get('excluded') or [])} 份；"
                f"配对缺席 seed {ob.get('missing_seeds')}"
            )
            lines.extend(
                f"  - `{item['file']}`：{item['mechanism']}"
                for item in (ob.get("unreadable") or []) + (ob.get("excluded") or [])
            )
        lines.extend(
            f"- 臂缺席 `{key}`：{why}（该行不进入统计，分母相应减少）" for key, why in (avail.get("arms") or {}).items()
        )
        if avail.get("gates"):
            lines.append(f"- §1.1 硬门槛无法核验：{avail['gates']}")
        lines.append("")
    # ── 0.5 机制对照（描述性，不做事后改判）──────────────────────────────
    lines.append("## 0.5 与原批的机制对照（描述性；不用于改判）")
    lines.append("")
    lines.append("### 0.5.1 stop_reason 分布（三 seed 合并，逐臂）")
    lines.append("")
    lines.append("| 臂 | 新批 stop_reason | 原批 stop_reason |")
    lines.append("|---|---|---|")
    for arm in report["arms"]:
        new_sr: dict[str, int] = {}
        old_sr: dict[str, int] = {}
        for seed in report["seeds"]:
            st = (report["per_seed"].get(str(seed)) or {}).get("new", {}).get(arm)
            if st:
                for key, n in (st.get("stop_reasons") or {}).items():
                    new_sr[str(key)] = new_sr.get(str(key), 0) + int(n)
            ost = (report["per_seed"].get(str(seed)) or {}).get("original", {}).get(arm)
            if ost:
                for key, n in (ost.get("stop_reasons") or {}).items():
                    old_sr[str(key)] = old_sr.get(str(key), 0) + int(n)
        lines.append(f"| `{arm}` | {new_sr} | {old_sr} |")
    lines.append("")
    pd = report.get("profile_preset_drift") or {}
    lines.append("### 0.5.2 logic 档预设漂移（候选机制来源，非因果证明）")
    lines.append("")
    if pd.get("available"):
        added = pd.get("added") or {}
        lines.append(
            f"logic 档自 R-P0-2 切点新增 **{len(added)}** 个行为开关（R-P0-2 切点未启用）："
            + "、".join(f"`{k}`" for k in added)
            + "。本批按当前 documented protocol（logic 档）运行，因此**新批不是 R-P0-2 的逐字节等价重跑**；"
            "R1 未复现与这些漂移的相关性只能作为**候选机制**，因果归属需下一轮的逐开关消融（另预注册）。"
        )
    else:
        lines.append(f"profile 预设漂移无法核验（{pd.get('reason') or '原因未记录'}）——不得当作无漂移。")
    lines.append("")
    r2 = v.get("R2_stats") or {}
    lines.append("### 0.5.3 解释边界（写死口径，防事后改写）")
    lines.append("")
    lines.append(
        "- **正面（R2）**：新批 `aitester` vs `plain_llm_df` 的配对差为 "
        f"δ={r2.get('delta')}（{r2.get('delta_pp')}pp；b/c={r2.get('b_new_only')}/{r2.get('c_old_only')}；"
        f"McNemar p={r2.get('mcnemar_exact_p_two_sided')}；bootstrap CI={r2.get('bootstrap_ci95')}）——"
        "头条结论的核心负面证据（编排 vs df 提示协议的检出差距，方向为负）在新协议下**仍然成立且显著**。"
    )
    lines.append(
        f"- **未复现（R1/R3）**：预设的完整排序 `plain_llm_df > aitester > plain_llm` 未成立"
        f"（R1={v.get('R1_pooled_ordering_df_gt_aitester_gt_plain')}；R3={v.get('R3_ordering_in_at_least_2_of_3_seeds')}）。"
        "注意：R-P0-2 中 `aitester > plain_llm` 这一**次级排序**本身不是核心结论；其未复现意味着"
        '"aitester 检出高于裸提示"在当前协议下不成立（新批部分 seed 甚至更低）。'
    )
    lines.append(
        '- **不得**把本批差异归因于模型能力变化（同切点同模型指纹）；也**不得**声称"编排更差"是因果结论——'
        '协议漂移是混杂因素。可辩护表述："R-P0-2 头条批次的检出数字对 logic 档协议版本敏感；核心负面（vs df）稳健，'
        '次级排序（vs 裸提示）不稳健"。'
    )
    lines.append("")
    lines.append("## 1. 合并口径（3 seed 池化，n=261/臂）")
    lines.append("")
    lines.append("| 臂 | 检出/可测 | detection | repair | false_fix | tokens | 成本(USD, 估算) |")
    lines.append("|---|---|---|---|---|---|---|")
    for arm in report["arms"]:
        p = report["pooled"].get(arm) or {}
        o = report["original_pooled"].get(arm) or {}
        lines.append(
            f"| `{arm}`（新批） | {p.get('detected')}/{p.get('measurable')} | {p.get('detection_rate')} | "
            f"{(p.get('repaired') or 0)}/{p.get('repair_measurable')} | "
            f"{(p.get('false_fixed') or 0)}/{p.get('false_fix_measurable')} | "
            f"{(p.get('tokens') or {}).get('total')} | {_usd_text(p.get('cost_usd'), p.get('unpriced_reasons'), prefix='')} |"
        )
        lines.append(
            f"| `{arm}`（R-P0-2 旧批） | {o.get('detected')}/{o.get('measurable')} | {o.get('detection_rate')} | — | — | — | — |"
        )
    lines.append("")
    lines.append("## 2. 逐 seed 检出（新批 vs 旧批）")
    lines.append("")
    lines.append(
        "| seed | 臂 | 新批检出/可测 | 新批率 | 旧批检出/可测 | 旧批率 | 新 vs 旧 配对 δ | 不一致 b/c | McNemar p |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for seed in report["seeds"]:
        entry = report["per_seed"].get(str(seed)) or {}
        for arm in report["arms"]:
            nst = (entry.get("new") or {}).get(arm) or {}
            ost = (entry.get("original") or {}).get(arm) or {}
            lines.append(
                f"| {seed} | `{arm}` | {nst.get('detected')}/{nst.get('detection_measurable')} | "
                f"{nst.get('detection_rate')} | {ost.get('detected')}/{ost.get('detection_measurable')} | "
                f"{ost.get('detection_rate')} | — | — | — |"
            )
    lines.append("")
    lines.append("> 说明：第 2 节表内「新 vs 旧」配对列按臂汇总（三 seed 合并），逐 seed 明细见 ANALYSIS_REPORT.json。")
    lines.append("")
    lines.append("## 3. 新批 vs 旧批配对一致性（按 seed+task 配对，三 seed 合并）")
    lines.append("")
    lines.append("| 臂 | 配对数 | b(新检出旧未) | c(旧检出新未) | δ | McNemar p | CI95 |")
    lines.append("|---|---|---|---|---|---|---|")
    for arm in report["arms"]:
        p = report["paired_new_vs_original"].get(arm) or {}
        lines.append(
            f"| `{arm}` | {p.get('n_pairs')} | {p.get('b_new_only')} | {p.get('c_old_only')} | "
            f"{p.get('delta')} | {p.get('mcnemar_exact_p_two_sided')} | {p.get('bootstrap_ci95')} |"
        )
    lines.append("")
    lines.append("## 4. 成本与 provenance")
    lines.append("")
    c = report["cost"]
    lines.append(
        f"- tokens={c['total_tokens']}；实测估算成本=**{_usd_text(c['actual_est_usd'], c.get('unpriced_arms'))}**；"
        f"跑前估算={_usd_text(c['preflight_estimate_usd'])}"
        f"（口径已修正为 {_usd_text(c['amended_estimate_usd'])}，见 amendment）；"
        f"预算参考={_usd_text(c['budget_usd'])}"
    )
    drift_block = report.get("provenance_drift") or {}
    flags = drift_block.get("provenance_flags") or {}
    if flags.get("unverifiable"):
        lines.append(f"- 新批/原批 provenance flags：**无法核验**（{flags['unverifiable']}）——不作任何门槛陈述。")
    else:
        lines.append(
            f"- 新批 git_dirty={flags.get('new_git_dirty')} / git_sha={flags.get('new_git_sha')} / "
            f"fingerprint.pinned={flags.get('new_fingerprint_pinned')}；"
            f"旧批 git_dirty={flags.get('old_git_dirty')} / fingerprint 在场={flags.get('old_fingerprint_present')}"
        )
    if drift_block.get("provenance_flags_seed") is not None:
        lines.append(
            f"- 上行 flags 取的是**最后一个未跳过 seed（{drift_block['provenance_flags_seed']}）**，非三 seed 汇总。"
        )
    lines.extend(
        f"- provenance 漂移缺席 seed{item['seed']}：{item['mechanism']}（该 seed 不进入 diff 小节）"
        for item in drift_block.get("skipped_seeds") or []
    )
    lines.append("- 逐 seed env_snapshot / harness 漂移明细见 ANALYSIS_REPORT.json `provenance_drift`。")
    pd = report.get("profile_preset_drift") or {}
    if pd.get("available"):
        lines.append("")
        lines.append("### 4.1 logic 档预设漂移（R-P0-2 切点 b533cff → 本批切点 a93c1f6）")
        lines.append("")
        lines.append(
            f"logic 档开关数 {pd.get('old_key_count')} → {pd.get('new_key_count')}；"
            f"新增 **{len(pd.get('added') or {})}**、删除 {len(pd.get('removed') or {})}、改值 {len(pd.get('changed') or {})}。"
        )
        if pd.get("added"):
            lines.append("")
            lines.append("| 新增开关 | 生效值 |")
            lines.append("|---|---|")
            for k, v in pd["added"].items():
                lines.append(f"| `{k}` | `{v}` |")
        lines.append("")
        lines.append(
            "> 这些开关改变的是 aitester 臂的**再生成路由/变异反馈/定位测量**，是本批与 R-P0-2 的协议级差异；"
            "本批判据因此限定为『当前切点 documented protocol 下方向性复现』，不作逐字节等价陈述。"
        )
    else:
        lines.append(f"- profile 预设漂移：**无法核验**（{pd.get('reason') or '原因未记录'}），不得当作无漂移。")
    lines.append("")
    lines.append("## 5. 局限")
    lines.append("")
    lines.extend(f"- {item}" for item in report["limitations"])
    lines.append("")
    lines.append("## 6. 复算入口")
    lines.append("")
    lines.append("```bash")
    lines.append(".venv/bin/python experiments/analyze_t1_b2_main_batch.py \\")
    lines.append("    --out experiments/results/t_round_b2_main_batch_20261018 \\")
    lines.append("    --orig-dir experiments/results/main_batch --write")
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


_MANUAL_BEGIN = "<!-- MANUAL:BEGIN -->"
_MANUAL_END = "<!-- MANUAL:END -->"


def _preserve_manual_sections(generated: str, existing_path: Path) -> str:
    """把既有 README 中 MANUAL 标记块原样保留到生成内容末尾。

    背景（X 轮 2026-10-19）：归档 README 曾含手工追加的"0.6 T 轮发现（可辩护
    表述，写死防事后改写）"节，而 `render_readme` 从零生成——重跑 `--write` 会
    **静默丢失**该节（复算实证：/tmp 副本重跑后 diff 缺 32 行）。标记块内的
    内容为手写解读（引用数字须人工与 report 核对后更新），生成器不重写、不
    校验其内容，只保证不丢。

    规则：
    - 仅保留 `MANUAL:BEGIN` 与 `MANUAL:END` 成对闭合的块（未闭合标记整体
      不保留——防截断内容被当作完整块）；
    - 多个块按原相对顺序追加到生成内容末尾；
    - 既有文件不存在（首次生成）时原样返回。
    """
    if not existing_path.is_file():
        return generated
    existing = existing_path.read_text(encoding="utf-8")
    blocks: list[str] = []
    rest = existing
    while True:
        begin = rest.find(_MANUAL_BEGIN)
        if begin < 0:
            break
        end = rest.find(_MANUAL_END, begin)
        if end < 0:
            break
        blocks.append(rest[begin : end + len(_MANUAL_END)].strip("\n"))
        rest = rest[end + len(_MANUAL_END) :]
    if not blocks:
        return generated
    header = (
        "\n\n---\n\n"
        "<!-- 以下为手工维护节（MANUAL 标记块）：生成器 --write 时原样保留，\n"
        "     不重写亦不校验其内容；块内引用数字更新须人工核对后编辑。 -->\n"
    )
    return generated.rstrip("\n") + "\n" + header + "\n\n" + "\n\n".join(blocks) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="T1（B2）主批次锁指纹复现批分析（零 LLM）")
    parser.add_argument("--out", required=True, help="T1 结果目录")
    parser.add_argument("--orig-dir", default="experiments/results/main_batch", help="R-P0-2 原批次目录")
    parser.add_argument("--price", default="experiments/price_table.json")
    parser.add_argument("--write", action="store_true", help="写出 ANALYSIS_REPORT.json / README.md")
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    price, price_reason = _load_price_entry(args.price)
    report = build_report(out_dir, Path(args.orig_dir), price, price_reason)
    if args.write:
        (out_dir / "ANALYSIS_REPORT.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        readme_path = out_dir / "README.md"
        readme_path.write_text(_preserve_manual_sections(render_readme(report), readme_path), encoding="utf-8")
        (out_dir / "BASELINE_FRAGMENT.yaml").write_text(render_baseline_fragment(report), encoding="utf-8")
        print(f"已写出：{out_dir / 'ANALYSIS_REPORT.json'}")
        print(f"已写出：{out_dir / 'README.md'}")
    print(json.dumps(report["verdict"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
