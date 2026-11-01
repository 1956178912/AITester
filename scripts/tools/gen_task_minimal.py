#!/usr/bin/env python3
"""gen_task_minimal.py — 任务粒度极简生成器 v2（对抗环境杀进程的最终架构）。

每任务 = 一次独立短进程。df 臂口径复刻 _build_df_parity_query；
thinking 显式关闭（AD1 复刻——V4 默认开思考会吃光 max_tokens 致 content 空）。
checkpoint 逐任务落盘，进程死亡只损当前任务。

用法：
    python gen_task_minimal.py --manifest <jsonl> --out <jsonl> --task-index <i> --kind <df|swebench|tge>
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import sys
import time
from pathlib import Path

for var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ.pop(var, None)

import httpx  # noqa: E402

SYSTEM_PROMPT = (
    "你是测试生成专家。为给定的被测代码生成一个完整的 pytest 测试文件。"
    "只输出 Python 代码本身，不要任何解释或 markdown 标记。"
    "测试必须可以直接保存为 test 文件并用 pytest 运行。"
)


def build_df_parity_query(target_code: str, module_name: str) -> str:
    """复刻 src/agents/generator.py _build_df_parity_query（df 臂口径冻结）。"""
    query = f"目标代码：\n```\n{target_code}\n```"
    if module_name:
        query += (
            f"\n\n被测模块名：{module_name}"
            f"\n\n【重要约束】import 语句必须使用以下模块名：`{module_name}`，"
            f"即 `from {module_name} import ...`"
        )
    return query


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--task-index", type=int, required=True)
    ap.add_argument("--kind", required=True, choices=["df", "swebench", "tge"])
    args = ap.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(args.manifest, encoding="utf-8") as mf:
        rows = [json.loads(ln) for ln in mf if ln.strip()]
    row = rows[args.task_index]

    # checkpoint
    done_ids = set()
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            with contextlib.suppress(Exception):
                done_ids.add(json.loads(line).get("task_id", ""))
    task_id = row.get("task_id") or row.get("instance_id", f"idx_{args.task_index}")
    if task_id in done_ids:
        print(f"SKIP {task_id} (done)")
        return 0

    # 载荷构造
    if args.kind == "df":
        code = row.get("buggy_code", "")
        fp = str(row.get("file_path", "") or "")
        module_name = (fp[:-3] if fp.endswith(".py") else fp).replace("/", ".")[:50]
        query = build_df_parity_query(code, module_name)
    elif args.kind == "swebench":
        code = row.get("instance_code", "")
        fp = str(row.get("file_path", "") or "")
        mod = (fp[:-3] if fp.endswith(".py") else fp).replace("/", ".")[:50]
        query = build_df_parity_query(code, mod) + (
            f"\n\n【任务】该代码来自 SWE-bench 任务 {row.get('instance_id', '')}，"
            "包含一个真实缺陷。请生成能暴露该缺陷、且缺陷修复后能通过的测试。"
        )
    else:
        code = row.get("code_src", "")
        query = (
            "目标代码：\n```\n" + code + "\n```\n\n"
            "为上述正常代码生成完整的 pytest 测试文件（accuracy 口径：测试在代码上运行通过即可）。"
            "只输出 Python 代码本身。"
        )

    # LLM 配置（.env.local 在仓库根）
    env = {}
    env_file = Path("/Users/wangchenyu/Workspace/AITester/.env.local")
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    key = env.get("LLM_1_API_KEY")
    url = env.get("LLM_1_BASE_URL", "https://api.deepseek.com/v1")
    model = env.get("LLM_1_MODEL_NAME", "deepseek-flash")

    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ],
        "max_tokens": 8192,
        "temperature": 0.0,
        # AD1 复刻：V4 thinking 默认开启会吃光 max_tokens 致 content 空
        "thinking": {"type": "disabled"},
    }

    t0 = time.time()
    last_err = ""
    for attempt in range(1, 4):
        try:
            r = httpx.post(
                url.rstrip("/") + "/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json=body,
                verify=False,  # noqa: S501 — 网关 MITM 证书不可信，显式豁免
                timeout=300.0,
            )
            r.raise_for_status()
            d = r.json()
            ch = d["choices"][0]
            finish = ch.get("finish_reason")
            content = ch["message"]["content"] or ""
            usage = d.get("usage", {})
            print(
                f"DIAG {task_id}: attempt={attempt} finish={finish} "
                f"completion_tokens={usage.get('completion_tokens')} content_len={len(content)}",
                file=sys.stderr,
            )
            m = re.search(r"```(?:python)?\s*\n(.*?)```", content, re.S)
            gen = (m.group(1) if m else content).strip()
            if not gen:
                last_err = f"finish={finish} empty content (completion={usage.get('completion_tokens')})"
                time.sleep(2**attempt)
                continue
            rec = {
                "task_id": task_id,
                "kind": args.kind,
                "generated_test": gen,
                "token_usage": {"total_tokens": usage.get("total_tokens", 0)},
                "wall_s": round(time.time() - t0, 1),
                "attempt": attempt,
            }
            with out_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False, allow_nan=False) + "\n")
            print(f"OK {task_id} ({rec['wall_s']}s, {len(gen)} chars)")
            return 0
        except Exception as e:
            last_err = f"{type(e).__name__}: {str(e)[:100]}"
            print(f"attempt {attempt} FAIL {task_id}: {last_err}", file=sys.stderr)
            time.sleep(2**attempt)
    print(f"DEAD {task_id}: {last_err}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
