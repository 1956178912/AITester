"""汇总全部探针 item_meta.json → ITEM_RESULTS.json/.md（不手写数字）。"""

from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

out = Path(sys.argv[1])
root = Path(sys.argv[2])
run_stamp = sys.argv[3]
start_epoch = int(sys.argv[4])
end_epoch = int(sys.argv[5])

preflight = {}
try:
    preflight = json.loads((out / "PREFLIGHT.json").read_text(encoding="utf-8"))
except (OSError, ValueError):
    pass

items = []
for meta_path in sorted(out.glob("*/item_meta.json")):
    try:
        items.append(json.loads(meta_path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        items.append({"item": meta_path.parent.name, "status": "meta_unreadable"})

# rc 文件（runner 写入）
for item in items:
    rc_path = out / item["item"] / ".rc"
    item["exit_code"] = int(rc_path.read_text().strip()) if rc_path.is_file() else None

total_cost = 0.0
cost_known = True
for item in items:
    c = item.get("cost_usd_standard_price")
    if c is None:
        cost_known = False
    else:
        total_cost += float(c)

result = {
    "schema": "n4_e2e_llm_probes/1",
    "run_stamp": run_stamp,
    "wall_seconds_total": end_epoch - start_epoch,
    "wall_minutes_total": round((end_epoch - start_epoch) / 60, 2),
    "preflight": preflight,
    "items": items,
    "total_cost_usd_standard_price": round(total_cost, 6) if cost_known else None,
    "cost_note": "标准价目表上界（非错峰/缓存价）；未登记价格时 None",
}
(out / "ITEM_RESULTS.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

lines = []
add = lines.append
add("# N-4 真实 LLM 重型功能探针：逐项观测汇总（脚本直出）")
add("")
add(f"> 运行 {run_stamp}；总墙钟 {result['wall_minutes_total']}min；总成本（标准价上界）≈ ${result['total_cost_usd_standard_price']}")
add("> 数字均来自各 item 的批次 JSON / 日志 / trace，不手写；结论与缺陷清单见 README.md。")
add("")
add("| item | exit | 墙钟(s) | tokens | 成本($) | 行数 | stop_reason | trace 节点命中 |")
add("|---|---|---|---|---|---|---|---|")
for item in items:
    tm = item.get("tokens") or {}
    rows = item.get("rows") or []
    stops = sorted({str(r.get("stop_reason")) for r in rows if r.get("stop_reason") is not None})
    nodes = sorted((item.get("trace") or {}).get("node_event_counts", {}).keys())
    add(
        f"| `{item.get('item')}` | {item.get('exit_code')} | {item.get('wall_seconds')} | "
        f"{tm.get('total_tokens', 0)} | {item.get('cost_usd_standard_price')} | {len(rows)} | "
        f"{', '.join(stops) if stops else '—'} | {', '.join(nodes) if nodes else '—'} |"
    )
add("")
add("## 逐项关键观测（字段恒 None / 路径进入证据）")
add("")
for item in items:
    add(f"### `{item.get('item')}`")
    add("")
    if item.get("status") == "blocked":
        add(f"- **blocked**：{item.get('reason')}")
        add("")
        continue
    add(f"- exit={item.get('exit_code')}，墙钟 {item.get('wall_seconds')}s，batches={len(item.get('batch_files') or [])}，rows={len(item.get('rows') or [])}")
    if item.get("cost_usd_standard_price") is not None:
        add(f"- tokens={item.get('tokens')}，成本≈${item.get('cost_usd_standard_price')}")
    fn = item.get("field_none_counts") or {}
    if fn:
        add("- 字段 None/空计数：" + "，".join(f"`{k}`={v}" for k, v in fn.items()))
    trace = item.get("trace") or {}
    add(f"- trace：{trace.get('files')} 文件；节点事件计数={trace.get('node_event_counts')}")
    venv = item.get("venv_cache_touched_in_window") or []
    if venv:
        add(f"- venv 缓存时间窗命中：{len(venv)} 个（{', '.join(v['name'] for v in venv[:5])}…）")
    hits = item.get("log_keyword_hits") or {}
    if hits:
        add("- 日志关键词命中：" + "，".join(f"`{k}`×{v.get('count')}" for k, v in list(hits.items())[:12]))
    for row in (item.get("rows") or [])[:5]:
        add(f"  - row `{row.get('task_id')}`：passed={row.get('passed')} iterations={row.get('iterations')} "
            f"stop_reason={row.get('stop_reason')} diagnosis={'✓' if row.get('diagnosis_present') else '✗'} "
            f"patch={'✓' if row.get('patch_present') else '✗'} repair_history_len={row.get('repair_history_len')} "
            f"spec_compile_rate={row.get('spec_compile_rate')} spec_oracle_injected={row.get('spec_oracle_injected')} "
            f"spec_oracle_verdict={row.get('spec_oracle_verdict')} rag_stats={'✓' if row.get('rag_stats') else '✗'} "
            f"cross_file_deps={row.get('cross_file_deps')} difficulty={row.get('task_metadata_difficulty')} "
            f"token_budget_capped={row.get('token_budget_capped')}")
    if item.get("log_warnings_errors"):
        add("- 日志告警/错误样本：")
        for ln in item["log_warnings_errors"][:5]:
            add(f"  - `{ln}`")
    add("")

(out / "ITEM_RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"ITEM_RESULTS：{out / 'ITEM_RESULTS.json'} / .md（items={len(items)}，总成本≈${result['total_cost_usd_standard_price']}）")
