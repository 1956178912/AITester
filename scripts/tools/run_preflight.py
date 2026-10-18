#!/usr/bin/env python3
"""批次跑批前置闸（EMSE 批次 2026-10-15）：配额预算 + 模型指纹 + 工作树状态。

## 为什么需要它（来自本轮审计的实证）

1. **SWE-bench Lite 的失败根因是"没有批次级配额闸"，不是模型能力**——
   `experiments/results/emse_swebench_disclosure.md` 记录：20 次尝试中 10 次超时、
   7 次完成者全部因 API 429 限流失败，`capability_conclusion =
   none_valid_infrastructure_failure`，且**该数据集的 pass_rate 不得引用**。
   该披露文档自己写明："复跑前置：客户端已具备 429 退避，**但下载器/跑批入口
   无配额预算控制——重跑前需先补配额闸**"。本工具就是那道闸的前置检查。
2. **头条批次的模型指纹缺失**——主批次 provenance 10/10 `git_dirty=true`、
   0/10 有 `model_fingerprint`，而模型是浮动别名 `deepseek-flash`；
   `scripts/gates/check_model_fingerprint.py` 只扫近 2 天，历史批次被豁免。
   跑新批次前必须先确认"这次跑出来会带 `pinned=true` 指纹"，否则复跑一次仍不可复现。

## 与既有机制的关系（不重复造）

- **任务级**硬上限已存在：`COST_BUDGET_ENABLE` / `COST_BUDGET_TOKENS` /
  `COST_BUDGET_USD`（`src/budget/cost_budget.py`）——超限抛
  `BudgetExceededError`，任务标记 `BUDGET_EXCEEDED`。
- 本工具补的是**批次级**：任务数 × 重试 × 并行度 的请求量估算与"是否配了
  批次级上限"的判定。二者叠加使用（任务级防单任务失控，批次级防整批烧穿配额）。

## 用法

    python scripts/tools/run_preflight.py                      # 只读体检（零网络）
    python scripts/tools/run_preflight.py --expect-tasks 261   # 按计划任务数估算请求量
    python scripts/tools/run_preflight.py --check-quota        # 追加一次最小 LLM 探测（消耗 1 次调用）
    python scripts/tools/run_preflight.py --strict             # 任一项不达标 → 退出码非 0

退出码：0 = 通过（或非 strict 模式下的告警）；1 = strict 模式下存在阻断项；
2 = 用法/环境错误（如 --check-quota 但无可用 key）。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# 批次级配额口径的**权威实现**在 `src/budget/batch_quota.py`（同时是 evn 变量
# 登记表的扫描面）；本工具只做编排与打印，不再自带一份解析逻辑（去重）。
from src.budget.batch_quota import (  # noqa: E402
    assess_batch_budget,
)


def git_state() -> dict[str, Any]:
    """工作树状态（干净树是"可复现批次"的必要条件之一）。"""
    out: dict[str, Any] = {"sha": None, "dirty": None, "dirty_reason": None}
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=_REPO_ROOT, capture_output=True, text=True, timeout=10)
        if sha.returncode == 0:
            out["sha"] = sha.stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"], cwd=_REPO_ROOT, capture_output=True, text=True, timeout=10
        )
        if status.returncode == 0:
            lines = [ln for ln in status.stdout.splitlines() if ln.strip()]
            out["dirty"] = bool(lines)
            out["dirty_reason"] = f"{len(lines)} 个未提交变更" if lines else None
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover - 环境异常
        out["dirty_reason"] = f"git 调用失败：{type(exc).__name__}"
    return out


_NESTED_ORPHAN_SCRIPT = _REPO_ROOT / "scripts" / "tools" / "detect_orphan_procs.py"


def proc_hygiene(timeout: float = 15.0) -> dict[str, Any]:
    """孤儿嵌套测试进程巡检（K 轮 2026-10-17，委托 detect_orphan_procs.py）。

    为什么前置闸要看它：实测两个被 init 收养的变异体 pytest 进程各占 ~97% CPU
    空转 7 小时（见 detect_orphan_procs.py docstring）。跑批前若宿主机已有这种
    泄漏，并行度 4 的批次会被 CPU 饥饿拖出大量超时——超时任务在 M1 口径里
    是 **None/不可判定**而不是"能力失败"，等于用测量伪影污染整批结论。

    口径：只读巡检（不自动 kill——前置闸不应有副作用）；返回结构化字典，
    `available=false` 时明确表示"读不到进程表"而非"零泄漏"。

    Args:
        timeout: 子进程超时秒数。

    Returns:
        detect_orphan_procs.py `--json` 的报告；不可用时含 `available=False`。
    """
    try:
        proc = subprocess.run(
            [sys.executable, str(_NESTED_ORPHAN_SCRIPT), "--json"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover - 环境异常
        return {"available": False, "reason": f"调用失败：{type(exc).__name__}", "leaked": [], "leaked_count": 0}
    if proc.returncode not in (0, 1):  # 0=无泄漏 1=有泄漏，其余为脚本自身异常
        return {
            "available": False,
            "reason": f"退出码 {proc.returncode}：{(proc.stderr or '').strip()[:120]}",
            "leaked": [],
            "leaked_count": 0,
        }
    try:
        payload = json.loads((proc.stdout or "").strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        return {"available": False, "reason": "输出不可解析", "leaked": [], "leaked_count": 0}
    return payload if isinstance(payload, dict) else {"available": False, "reason": "输出结构异常"}


def recent_fingerprints(limit: int = 5) -> list[dict[str, Any]]:
    """近期批次的模型指纹状态（新批次必须 pinned=true 才能锁住可复现性）。"""
    rows: list[dict[str, Any]] = []
    for path in sorted(
        (_REPO_ROOT / "experiments" / "results").glob("**/benchmark_*.json"),
        key=lambda p: p.stat().st_mtime if p.exists() else 0,
        reverse=True,
    )[:limit]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        prov = data.get("provenance") or {}
        fp = prov.get("model_fingerprint") or {}
        rows.append(
            {
                "file": str(path.relative_to(_REPO_ROOT)),
                "model_name": prov.get("model_name"),
                "pinned": fp.get("pinned"),
                "returned_model": fp.get("returned_model"),
                "git_dirty": prov.get("git_dirty"),
            }
        )
    return rows


def batch_budget_report(expect_tasks: int, parallelism: int) -> dict[str, Any]:
    """批次级请求量估算 + 上限配置检查（口径来自 `src/budget/batch_quota.py`）。"""
    assessment = assess_batch_budget(expect_tasks)
    return {
        "expect_tasks": expect_tasks,
        "parallelism": parallelism,
        "estimated_calls_upper_bound": assessment.estimated_calls_upper_bound,
        "task_level": {
            "enabled": assessment.task_level_enabled,
            "tokens": assessment.task_level_tokens,
            "usd": assessment.task_level_usd,
        },
        "batch_cap_calls": assessment.batch_cap_calls,
        "batch_cap_usd": assessment.batch_cap_usd,
        "preflight_required": assessment.preflight_required,
        "blocking": list(assessment.blocking),
    }


def quota_probe() -> dict[str, Any]:
    """最小 LLM 连通性/配额探测（**消耗 1 次调用**，仅在 --check-quota 时执行）。

    T 轮 2026-10-18 修复（本函数此前引用了**不存在的符号**）：
    旧实现 `from src.agents.llm_client import LLMClient` → `llm_client` 模块
    根本没有 `LLMClient` 类（只有模块级 `_get_llm_config()` 配置三元组与
    `_get_or_create_chat_client()` 聊天客户端工厂）→ `--check-quota` 恒
    ImportError、探测结果恒 `skipped=True`，strict 模式下"配额闸自身坏了"
    会阻断一切批次前置闸（B2 主批次实证）。

    修复口径（最小、真实可用、与生产 LLM 调用路径一致）：
    1. `import config` 触发 .env / .env.local 加载（本工具不自带凭据文件解析）；
    2. `_get_llm_config()` 取 (api_key, base_url, model_name)；
    3. `_get_or_create_chat_client(model, 0.0, api_key, base_url)` 复用进程内
       客户端缓存（与 BaseAgent 同一入口），`.invoke(...)` 发一次最小请求；
    4. 三态语义保持不变：
       - 无凭证 / 配置不完整 → `{"ok": False, "skipped": True, "reason": ...}`
         （strict 下阻断：跑批缺凭据必须显式可见）；
       - 网络/配额/鉴权异常 → `{"ok": False, "skipped": False, "reason": ...}`；
       - 探测成功 → `{"ok": True/False, "skipped": False, "response_prefix": ...}`
         （ok 取决于响应文本是否含 "ok" 令牌，短请求非 OK 回复也算异常口径）。

    Returns:
        探测结果字典（含 ok / skipped / reason 或 response_prefix）。

    Note:
        本函数只发 1 次低温短请求；不写缓存、不改任何 state。
    """
    # 先触发 config 导入：config.py 在 import 期执行 load_dotenv() +
    # load_env_local()，把 .env.local 的 LLM_1_* 注入 os.environ。此前探测在
    # config 加载前读 os.environ，开发者直接跑（未手工 export）时恒判"无凭证"。
    try:
        import config  # noqa: F401  # 副作用导入：加载 .env / .env.local 到 os.environ
    except Exception as exc:  # pragma: no cover - 依赖/环境异常
        return {"ok": False, "skipped": True, "reason": f"导入 config 失败：{type(exc).__name__}"}
    if not any(os.getenv(k, "").strip() for k in ("LLM_1_API_KEY", "DEEPSEEK_API_KEY")):
        return {"ok": False, "skipped": True, "reason": "未检测到 LLM_1_API_KEY / DEEPSEEK_API_KEY"}
    try:
        from src.agents.llm_client import (  # 延迟导入：零网络体检路径不加载
            _get_llm_config,
            _get_or_create_chat_client,
        )
    except Exception as exc:  # pragma: no cover - 依赖异常
        return {"ok": False, "skipped": True, "reason": f"导入 LLM 调用入口失败：{type(exc).__name__}"}
    try:  # pragma: no cover - 需要真实凭据
        api_key, base_url, model_name = _get_llm_config()
        if not (api_key and base_url and model_name):
            return {"ok": False, "skipped": True, "reason": "LLM 配置不完整（api_key/base_url/model_name 含空值）"}
        client = _get_or_create_chat_client(model_name, 0.0, api_key, base_url)
        resp = client.invoke("Reply with the single token: OK")
        content = getattr(resp, "content", None)
        text = content if isinstance(content, str) else str(resp)
        return {
            "ok": "ok" in text.lower(),
            "skipped": False,
            "response_prefix": text[:40],
            "model": model_name,
        }
    except Exception as exc:  # pragma: no cover - 网络/配额异常
        return {"ok": False, "skipped": False, "reason": f"{type(exc).__name__}: {exc}"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="批次跑批前置闸（配额/指纹/工作树）")
    parser.add_argument("--expect-tasks", type=int, default=261, help="计划任务数（默认主批次 261）")
    parser.add_argument("--parallelism", type=int, default=int(os.getenv("BENCHMARK_PARALLELISM", "4") or 4))
    parser.add_argument("--check-quota", action="store_true", help="追加一次最小 LLM 探测（消耗 1 次调用）")
    parser.add_argument("--strict", action="store_true", help="存在阻断项时退出码非 0")
    args = parser.parse_args(argv)

    git = git_state()
    budget = batch_budget_report(args.expect_tasks, args.parallelism)
    prints = recent_fingerprints()
    pinned_recent = [r for r in prints if r.get("pinned") is True]

    print("=" * 72)
    print("批次跑批前置闸（EMSE 批次 2026-10-15）")
    print("=" * 72)
    print(
        f"工作树：sha={git['sha']}  dirty={git['dirty']}"
        + (f"（{git['dirty_reason']}）" if git["dirty_reason"] else "")
    )
    print(
        f"计划任务数={budget['expect_tasks']}  并行度={budget['parallelism']}  "
        f"估算请求量上界={budget['estimated_calls_upper_bound']}"
    )
    print(
        f"任务级预算：enabled={budget['task_level']['enabled']} "
        f"tokens={budget['task_level']['tokens']} usd={budget['task_level']['usd']}"
    )
    print(f"批次级上限：AITESTER_BATCH_MAX_CALLS={budget['batch_cap_calls']}")
    print(f"近期批次指纹（近 {len(prints)} 个）：pinned=true 的有 {len(pinned_recent)} 个")
    for row in prints:
        print(f"  - {row['file']}｜alias={row['model_name']}｜pinned={row['pinned']}｜dirty={row['git_dirty']}")

    blocking = list(budget["blocking"])
    if git["dirty"]:
        blocking.append("工作树不干净：新批次 provenance 将记 git_dirty=true（复现性主张打折）")
    if prints and not pinned_recent:
        blocking.append("近期批次均无 pinned=true 模型指纹：新批次须确认带指纹后再跑")

    hygiene = proc_hygiene()
    if hygiene.get("available"):
        print(
            f"孤儿进程巡检：扫描 {hygiene.get('scanned', 0)} 个进程，"
            f"泄漏的嵌套测试子进程 {hygiene.get('leaked_count', 0)} 个"
        )
        for row in hygiene.get("leaked") or []:
            print(f"  - pid={row.get('pid')} 存活={row.get('etime')} 命中={row.get('matched_marker')}")
        if hygiene.get("leaked_count"):
            blocking.append(
                "宿主存在泄漏的嵌套测试子进程：会与批次争抢 CPU 导致超时（None 任务=不可判定，"
                "会污染批次结论）；先跑 `python scripts/tools/detect_orphan_procs.py --kill` 清理"
            )
    else:
        print(f"孤儿进程巡检：跳过（{hygiene.get('reason', 'ps 不可用')}）")

    if args.check_quota:
        probe = quota_probe()
        print(f"配额探测：{probe}")
        if not probe.get("ok"):
            blocking.append(f"配额/连通性探测未通过：{probe.get('reason') or probe}")
    else:
        print("配额探测：未执行（加 --check-quota 可消耗 1 次调用探测）")

    if blocking:
        print("\n阻断/告警项：")
        for item in blocking:
            print(f"  ✗ {item}")
    else:
        print("\n✓ 前置闸全部通过")
    print("=" * 72)
    if blocking and args.strict:
        print("strict 模式：存在阻断项，退出码 1")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
