#!/usr/bin/env python3
"""全量测试监测运行器（一次跑完 0LLM + 多 LLM，两档口径 + 进度 + 卡死监测）。

## 两档（用户口径：冒烟全通，全量才许开跑）

| 档 | 跑什么 | 目的 |
|---|---|---|
| `smoke` | 所有面各跑一项：pytest 每个测试文件 1 个 nodeid（先 `-qq` 收集再抽样）、LLM 每个「模型 × 臂 × 数据集面」1 个任务、门禁快检 | 查装配有没有坏——收集/导入/夹具/端点/落盘，这些坏了全量就是白花钱 |
| `full` | 最大量：`make test-cov`（全量+覆盖率）→ `make gates`（全链门禁）→ LLM 跑满每个数据集面（不给 `--llm-tasks` 即不加 `-n`） | 出判定读数 |
| `both`（默认） | 先 smoke 后 full | 一次命令跑完；**冒烟未全通则 full 一个阶段都不建** |

前置不是提示而是判据：full 档只认 `SMOKE_GATE.json` 里**同配置指纹**且通过的冒烟证据
（指纹含矩阵形状与协议取值、`HEAD` 与 `git status --porcelain` 摘要——改了任何文件，
旧证据即失效；`--jobs`/`--out` 这类不影响覆盖面的取值不进指纹）。确要跳过：
`--allow-stale-smoke`。

## 进度与卡死

每个阶段：固定节拍主循环（`--tick`）+ 后台读线程，按 `--heartbeat` 打印
`进度% (done/total) | 用时 | 静默秒 | load/core | mem | 最近输出`。总数取自
`collected N items` / `workers [N items]` / run_benchmark 的 `待运行任务数: N`；
LLM 段的完成数取 `INCREMENTAL_RESULTS.jsonl` 行数（输出行会被日志噪声支配）。

卡死检测必须主动：旧实现 `for line in proc.stdout` 阻塞读、把墙钟判断写在循环体内，
子进程一声不出时循环根本不转，"卡死"恰好是唯一不会被发现的失效模式。现在静默超过
`--stall-after`（默认 600s）或墙钟超过阶段上限，就终止**整个进程组**（SIGTERM→SIGKILL，
只杀直接子进程会留下 xdist worker 与容器，本仓的 983 个孤儿判定进程就是这么攒的），
按一次失败计入 `--retries` 重跑；LLM 段重跑走增量落盘，不二次付费。

## 最高规格默认值（用户口径：所有默认测试取最高规格）

| 项 | 默认 | 说明 |
|---|---|---|
| 单测超时 | 3600 s | `pyproject.toml` 同步；`--timeout-method=thread` 防子进程卡死 |
| 并行度 | `物理核 × 75%` | **资源占用上限 75%**（用户口径），留 25% 给系统与交互；内存 < 2 GB/worker 时再降档 |
| LLM 并发 | ≤ 4 | 网络受限而非 CPU 受限，超了只会触发 429 重试（重试是付费的） |
| LLM 重试 | 6 次 | `LLM_MAX_RETRIES`；退避 1+2+4+8+16+32 s |
| LLM 传输超时 | 600 s | `LLM_HTTP_TIMEOUT`；深度思考默认开启后 180 s 不够 |
| 覆盖率 | 行 + 分支 | 走 `make test-cov`（CI 同口径，`coverage.xml` 供登记册对账） |
| 失败重跑 | 3 轮 | 每轮只跑上一轮失败用例（`--lf`） |
| 临时根 | 每次运行独占 `<报告目录>/tmp` | 见 `stage_base_env`：临时根堆积会拖慢内层 pytest |

## 用法

```bash
python scripts/run_all_tests.py                          # both：先冒烟，通了再全量
python scripts/run_all_tests.py --spec smoke --no-llm     # 只验装配，零花费
python scripts/run_all_tests.py --estimate-llm              # 先看两档投影，不跑不花钱
python scripts/run_all_tests.py --no-llm                  # 跳过真 LLM 阶段（零成本）
python scripts/run_all_tests.py --stall-after 300         # 更激进的卡死阈值
```

`--estimate-llm` 在任何执行与建目录之前短路，分别打印 smoke 与 full 两档的费用投影；
full 档跑满每面时若上界超过 `--budget-cny`（默认 ¥300）就拒跑并给出可行的最大规模。

报告落 `experiments/results/test_run_<时间戳>/REPORT.json`（含每档的进度读数、
卡死/超时标记与冒烟证据）；该目录默认被 gitignore。

退出码：0 = 全部通过；1 = 有阶段失败 / 无阶段可跑 / 冒烟前置未满足；130 = 用户中断。
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import platform
import queue
import re
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable
_MAKE = os.environ.get("MAKE", "make")
PYTEST_TIMEOUT_SECONDS = 3600

# ─── 两档口径（用户口径：冒烟全通才允许全量开跑）───────────────────────────────
SPEC_SMOKE = "smoke"
SPEC_FULL = "full"
SPEC_BOTH = "both"
SPEC_CHOICES = (SPEC_SMOKE, SPEC_FULL, SPEC_BOTH)
#: 冒烟档每格任务数——1 就够：它只回答"这条管路通不通"，不产出任何判定读数。
SMOKE_TASKS_PER_CELL = 1
#: 冒烟通过证据文件名（落在运行目录，全量档开跑前逐项校验其指纹）。
SMOKE_GATE_FILE = "SMOKE_GATE.json"

# ─── LLM 段降本口径 ──────────────────────────────────────────────────────────
# 费用实测排序（用户口径 + 本仓登记证据）：① 输出 token ② 未命中输入 ③ 命中输入。
# 证据：src/agents/llm_client.py 记 R-P0-2 批 aitester 臂输出 5.23M token 而工件仅
# ~1–2k（思维链按输出计费）；价目表 deepseek-flash 输出 ¥8/M 对未命中输入 ¥2/M，
# 命中价 ¥0.04/M 低两个数量级。故降本先压输出量，再提命中率。
DEFAULT_LLM_ARMS = "aitester,plain_llm,plain_llm_df,plain_llm_df_spec,single_agent"
DEFAULT_LLM_DATASETS = "all"  # 满量档默认＝所有基准面；面清单现取加载器注册表
DEFAULT_BUDGET_CNY = 300.0
#: 每任务 token 上限按**真实需要**定，不按预算反推（反推等于允许每任务把整份
#: 预算烧光）。它只是斩断失控螺旋的闸，不是计价依据：
#: - 思考开启档：依据 `src/agents/llm_client.py` 的实测记录——单任务输出最高 84k
#:   token、整批 5.23M，而落盘工件仅 ~1–2k token，故取 120k 作余量；
#: - 思考关闭档（**当前默认**）：2026-11-04 实测同一 prompt 的单条 Generator 调用
#:   输出只有 709（deepseek-flash）/ 342（mimo-v2.6-pro）token，按每任务最坏 4.3 次
#:   调用（`src/budget/batch_quota.py` 的 `PER_TASK_CALLS_WORST`，实测 4.24）外推
#:   ≈ 3.0k token，取 20k ≈ 6.6 倍余量。
#:   沿用 120k 会把保护性上界抬高 6 倍，让满量档在没有依据的情况下被预算挡下。
NEED_BASED_TOKEN_CAP = 120_000
NEED_BASED_TOKEN_CAP_THINKING_OFF = 20_000
#: 实测单条调用形状（thinking off，QuixBugs `bitcount`，`TEMPERATURE=0.0`，两家取
#: 各自较大的读数）：(prompt_tokens, completion_tokens)，供投影给出"实测参考值"。
MEASURED_OFF_CALL_TOKENS = (489, 709)
#: 每任务最坏调用数（aitester 臂实测 4.24 ⇒ 取 4.3 作保守外推基数）。
MEASURED_CALLS_PER_TASK = 4.3


def thinking_default_on() -> bool:
    """当前思考口径是否开启——与 `llm_client._openai_extra_body` 用同一 env 判据。

    不 import `llm_client`（那会拉起 langchain 依赖面），但默认值必须与生产端
    一致，否则投影算的是另一档的钱。
    """
    return (os.getenv("LLM_THINKING_MODE", "disabled") or "").strip().lower() == "enabled"


def default_task_token_cap() -> int:
    """按思考档取默认每任务上限（关思考后的真实需要量小一个数量级）。"""
    return NEED_BASED_TOKEN_CAP if thinking_default_on() else NEED_BASED_TOKEN_CAP_THINKING_OFF


#: LLM 并发上限：网络受限而非 CPU 受限，超过它只会触发 429 重试（重试是付费的）。
LLM_PARALLELISM_CAP = 4
#: 峰时口径下两家的输出单价（¥/百万 token）；空闲时段官方为半价，故同一参数
#: 挪到空闲窗执行是**测量等价、账单减半**（不改任何协议变量，读数仍按峰时登记
#: 为上界）。见 experiments/price_table.json 的 `_comment`。
OFF_PEAK_WINDOWS = ((0, 9), (14, 17))  # 本地时区小时区间 [start, end)


def load_price_and_models() -> tuple[list[str], dict[str, float], str | None]:
    """已配置模型清单 + 各模型输出单价（登记币种）+ 币种。

    取不到价目（未登记/币种不可判定）时该模型不进单价表，调用方按"无法证明
    上限"处理——宁可不跑，也不要在没有价格事实源时假装预算安全。
    """
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    import config
    from src.budget import pricing

    models = [c.model_name for c in config.LLM_CONFIGS]
    table = pricing.load_price_table()
    out_prices: dict[str, float] = {}
    currency: str | None = None
    for model in models:
        entry = table.get(model)
        if entry is None or pricing.entry_block_reason(entry, allow_non_usd=True) is not None:
            continue
        price_out = entry.get("output_per_mtok")
        if isinstance(price_out, (int, float)) and price_out > 0:
            out_prices[model] = float(price_out)
            currency = str(entry.get("currency") or "").strip().upper() or currency
    return models, out_prices, currency


def in_off_peak(now_hours: int, windows: tuple[tuple[int, int], ...] = OFF_PEAK_WINDOWS) -> bool:
    """是否落在官方半价窗口内（纯小时判定，零依赖）。"""
    return any(start <= now_hours < end for start, end in windows)


def plan_llm_budget(
    tasks_total: int,
    budget_cny: float,
    out_prices: dict[str, float],
    currency: str | None,
    token_cap: int | None,
) -> dict:
    """投影 LLM 段费用上界，并检查它是否落在需要之内。

    上界口径（保守）：把每任务的全部 token 都按**输出单价**计（价目表里的最高
    档），故 `上界 = 任务数 × 每任务上限 × max(输出单价) / 1e6`。

    目标是"用最少的钱做完"，所以：
    - 上限默认取 `NEED_BASED_TOKEN_CAP`（按实测需要），**不是** `预算 / 任务数`
      反推——反推会让每个任务都获准烧掉自己那份预算，总账正好等于预算；
    - 超预算时的正确动作是**减小规模**（任务数/臂数/数据集面）或缩短无效螺旋，
      而不是放大上限把预算吃满；
    - 不用 `LLM_MAX_OUTPUT_TOKENS` 压输出：`base_agent` 把 `finish_reason=length`
      判为可恢复失败并重试（`LLM_MAX_RETRIES` 现为 6），截断一次反而付费多次。
    """
    note: dict = {
        "tasks_total": tasks_total,
        "budget": budget_cny,
        "currency": currency or "未知",
        "per_task_token_cap": token_cap or default_task_token_cap(),
        "worst_price_per_mtok": None,
        "upper_bound": None,
        "provable": False,
        "fits_budget": False,
        "advice": "",
        "reason": "",
    }
    if tasks_total <= 0:
        note["reason"] = "任务数为 0，LLM 段无事可做"
        return note
    if not out_prices:
        note["reason"] = "价目表无可用输出单价（未登记/币种不可判定）→ 无法投影费用上界"
        return note
    worst = max(out_prices.values())
    cap = token_cap or default_task_token_cap()
    note["worst_price_per_mtok"] = worst
    note["per_task_token_cap"] = cap
    if cap <= 0:
        note["reason"] = f"每任务 token 上限非法（{cap}），LLM 段拒绝开跑"
        return note
    bound = tasks_total * cap * worst / 1_000_000
    note["upper_bound"] = round(bound, 2)
    # 实测参考：保护性上界把每任务都按上限计价（最坏档），thinking-off 档另有实测
    # 基数，故再给一个可对照的期望值。只计**输出侧**——输入侧按同批实测约 2.1k
    # token/任务，在同一量级，但不混进这个数里以免假装精确。
    if not thinking_default_on():
        ref_out_per_task = MEASURED_OFF_CALL_TOKENS[1] * MEASURED_CALLS_PER_TASK
        note["measured_reference"] = round(tasks_total * ref_out_per_task * worst / 1_000_000, 2)
        note["measured_basis"] = f"{MEASURED_OFF_CALL_TOKENS[1]} 输出 token/调用 × {MEASURED_CALLS_PER_TASK} 调用/任务"
    else:
        note["measured_reference"] = None
    note["provable"] = True
    note["fits_budget"] = bound <= budget_cny
    if note["fits_budget"]:
        # 预算有余量 → 说明规模已经很小，直接给"再省"的建议而不是加量
        cheapest = min(out_prices, key=lambda m: out_prices[m])
        note["advice"] = (
            f"规模已在预算内；进一步降本按顺序：① 移到空闲窗（官方半价，测量等价）；"
            f"② 贯通段只跑必需臂（plain 臂 1 次调用/任务，aitester 臂实测 4.3 次）；"
            f"③ 保持身份键缓存开启（重跑零增量成本）；④ 探索性批次可用输出单价更低的 {cheapest}"
        )
        note["reason"] = (
            f"上界 {bound:.2f} {note['currency']} ≤ 预算 {budget_cny:.2f}（上界按最坏档计价，实际远低于此）"
        )
    else:
        # 超预算：给可达规模，不放大上限
        max_tasks = int(budget_cny * 1_000_000 / (cap * worst))
        note["advice"] = (
            f"按当前规模上界 {bound:.2f} {note['currency']} 超预算 {budget_cny:.2f}："
            f"把任务总数降到 ≤{max_tasks}（减数据集面或减 --llm-tasks），或分批跑并先跑判定面"
        )
        note["reason"] = f"上界 {bound:.2f} {note['currency']} > 预算 {budget_cny:.2f} → 缩小规模，不放大上限"
    return note


# ─── 本机规格探测 ────────────────────────────────────────────────────────────


def detect_cpu_count() -> int:
    """物理核数（macOS/Linux 通用；拿不到时退回逻辑核，再退回 4）。"""
    try:
        physical = int(
            subprocess.run(
                ["sysctl", "-n", "hw.physicalcpu"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            ).stdout.strip()
        )
        if physical > 0:
            return physical
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return os.cpu_count() or 4


def detect_memory_gb() -> float:
    """物理内存 GB（macOS 用 sysctl，Linux 读 /proc/meminfo）。"""
    try:
        out = subprocess.run(
            ["sysctl", "-n", "hw.memsize"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        ).stdout.strip()
        if out:
            return int(out) / (1024**3)
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) / (1024**2)
    except (OSError, ValueError):
        pass
    return 0.0


#: CPU 占用上限比例（用户口径：最高占本机 75%，不占满）。
CPU_CAP_RATIO = 0.75


def plan_jobs(cpu: int, mem_gb: float, requested: int | None, cap_ratio: float = CPU_CAP_RATIO) -> tuple[int, str]:
    """定并行度：核数 × 75% 是硬上限，内存是第二约束（每 worker 至少 2 GB）。

    注意"最高规格"指的是**测试覆盖面**（跑最全的用例集、含 slow 与 LLM），
    不是资源占满——用户明确要求 CPU/GPU 占用不超过本机 75%。

    Returns:
        ``(jobs, reason)``：reason 记录降档原因，写进报告便于复核。
    """
    if requested is not None:
        return max(1, requested), "用户显式指定（不受 75% 上限约束）"
    cap = max(1, int(cpu * cap_ratio))
    by_cpu = cap
    if mem_gb <= 0:
        return by_cpu, f"按核数 × {cap_ratio:.0%}（内存未知）"
    by_mem = max(1, int(mem_gb // 2))
    if by_mem < by_cpu:
        return by_mem, f"内存约束降档（{mem_gb:.1f} GB / 每 worker 2 GB）"
    return by_cpu, f"按物理核数 × {cap_ratio:.0%}（{cpu} 核 → {cap}）"


# ─── 运行与监测 ──────────────────────────────────────────────────────────────


@dataclass
class StageResult:
    """单个阶段的运行结果（供汇总与报告序列化）。"""

    name: str
    command: list[str]
    exit_code: int = -1
    duration_s: float = 0.0
    attempts: int = 0
    timed_out: bool = False
    stalled: bool = False
    progress: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


# ─── 进度解析 ────────────────────────────────────────────────────────────────

_TOTAL_RES = (
    re.compile(r"collected (\d+) items?"),  # pytest 单进程
    re.compile(r"workers \[(\d+) items?\]"),  # pytest-xdist
    re.compile(r"待运行任务数: (\d+)"),  # experiments/run_benchmark.py
)
_RESULT_RES = re.compile(r"\b(?:PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)\b")
_PERCENT_RES = re.compile(r"\[\s*(\d+)%\]")


@dataclass
class ProgressState:
    """一个阶段的进度读数（读数只用于展示，不参与判定）。"""

    total: int = 0
    done: int = 0
    percent: float | None = None
    last_line: str = ""
    output_lines: int = 0
    silent_s: float = 0.0

    def render(self) -> str:
        if self.total:
            share = self.done / self.total
            return f"{share:6.1%} ({self.done}/{self.total})"
        if self.percent is not None:
            return f"{self.percent:6.1f}%"
        return f"{self.output_lines} 行输出"


def _count_incremental_lines(path: Path | None) -> int:
    if path is None or not path.is_file():
        return 0
    with open(path, encoding="utf-8", errors="replace") as fh:
        return sum(1 for line in fh if line.strip())


def _update_progress(state: ProgressState, line: str, incremental_path: Path | None) -> None:
    """从输出行推进度读数；LLM 段以 `INCREMENTAL_RESULTS.jsonl` 行数为完成数。"""
    state.output_lines += 1
    state.last_line = line.strip()[:120]
    for pattern in _TOTAL_RES:
        m = pattern.search(line)
        if m:
            state.total = int(m.group(1))
            break
    m = _PERCENT_RES.search(line)
    if m:
        state.percent = float(m.group(1))
    if incremental_path is not None:
        state.done = _count_incremental_lines(incremental_path)
    elif _RESULT_RES.search(line):
        state.done += 1


def _terminate_group(proc: subprocess.Popen[str], grace_s: float = 10.0) -> None:
    """终止**整个进程组**——只杀直接子进程会留下 pytest-xdist worker 与容器。"""
    try:
        pgid = os.getpgid(proc.pid)
    except (ProcessLookupError, AttributeError, OSError):
        pgid = -1
    for sig, kwargs in ((signal.SIGTERM, {"timeout": grace_s}), (signal.SIGKILL, {"timeout": grace_s})):
        if pgid > 0:
            with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
                os.killpg(pgid, sig)
        else:
            (proc.terminate if sig is signal.SIGTERM else proc.kill)()
        try:
            proc.wait(**kwargs)
            return
        except subprocess.TimeoutExpired:
            continue


def _sample_resources() -> tuple[float, float]:
    """采样系统负载与可用内存（轻量、无第三方依赖）。

    Returns:
        ``(load_per_core, mem_used_gb)``；取不到时返回 ``(-1.0, -1.0)``。
    """
    try:
        load1 = os.getloadavg()[0]
        cpu = detect_cpu_count() or 1
        load_per_core = load1 / cpu
    except (OSError, AttributeError):
        load_per_core = -1.0
    try:
        mem_total = detect_memory_gb()
        # 用 vm_stat 估算已用内存（macOS）；Linux 走 /proc/meminfo 的 available
        if platform.system() == "Darwin":
            out = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=10, check=False).stdout
            pagesize = 4096
            free = 0
            for line in out.splitlines():
                if "page size of" in line:
                    pagesize = int(line.split("page size of")[1].split("bytes")[0].strip())
                if line.startswith("Pages free:") or line.startswith("Pages inactive:"):
                    free += int(line.split(":")[1].strip().rstrip(".")) * pagesize
            mem_used = max(0.0, mem_total - free / (1024**3))
        else:
            avail = mem_total
            with open("/proc/meminfo", encoding="utf-8") as fh:
                for line in fh:
                    if line.startswith("MemAvailable:"):
                        avail = int(line.split()[1]) / (1024**2)
                        break
            mem_used = max(0.0, mem_total - avail)
    except (OSError, ValueError, subprocess.SubprocessError, IndexError):
        mem_used = -1.0
    return load_per_core, mem_used


def run_stage(
    name: str,
    command: list[str],
    env: dict[str, str],
    cwd: Path,
    log_dir: Path,
    retries: int,
    heartbeat_s: float = 30.0,
    stage_timeout_s: float = 0.0,
    stall_after_s: float = 600.0,
    tick_s: float = 5.0,
    incremental_path: Path | None = None,
    on_progress: object | None = None,
) -> StageResult:
    """执行一个阶段：进度显示、卡死检测与失败重跑。

    卡死检测必须是**主动**的。旧实现用 `for line in proc.stdout` 阻塞读，并把墙钟
    判断写在循环体内——子进程一声不出时循环根本不转，于是"卡死"恰好成了唯一不会
    被发现的失效模式。现改为读线程 + 固定节拍主循环：静默超过 `stall_after_s` 或
    墙钟超过 `stage_timeout_s` 都终止**整个进程组**（只杀直接子进程会留下
    pytest-xdist worker 与容器），记一次失败并按 `retries` 重跑。

    Args:
        name: 阶段名（写日志与报告）。
        command: 命令列表。
        env: 环境变量快照。
        cwd: 工作目录。
        log_dir: 日志目录。
        retries: 失败重跑轮数上限。
        heartbeat_s: 进度打印间隔（秒）。
        stage_timeout_s: 整阶段墙钟上限（0 表示不限）。
        stall_after_s: 无任何输出的最长秒数（超过判卡死）。
        tick_s: 主循环节拍（秒）。
        incremental_path: LLM 段的 `INCREMENTAL_RESULTS.jsonl` 路径（完成数来源）。
        on_progress: 每节拍回调 `(state, elapsed)`，供 `ProgressWriter` 写外部进度面。

    Returns:
        `StageResult`（含 `progress` 读数、`stalled` / `timed_out` 标记）。
    """
    result = StageResult(name=name, command=list(command))
    started = time.time()
    attempt = 0
    while True:
        attempt += 1
        result.attempts = attempt
        log_path = log_dir / f"{name}.attempt{attempt}.log"
        print(f"\n▶ [{name}] 第 {attempt}/{retries + 1} 次尝试")
        print(f"  命令: {' '.join(shlex.quote(part) for part in command)}")
        print(f"  日志: {log_path}")
        print(
            f"  监测: 静默 {stall_after_s:.0f}s 判卡死 | 墙钟 {stage_timeout_s:.0f}s 判超时 | 心跳 {heartbeat_s:.0f}s"
        )
        t0 = time.time()
        state = ProgressState()
        stalled = False
        timed_out = False
        q: queue.Queue[str | None] = queue.Queue()
        with open(log_path, "w", encoding="utf-8") as log:
            proc = subprocess.Popen(
                command,
                cwd=str(cwd),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                start_new_session=True,
            )

            def _pump(stream=proc.stdout, sink=q) -> None:
                assert stream is not None
                for line in stream:
                    sink.put(line)
                sink.put(None)

            reader = threading.Thread(target=_pump, name=f"pump-{name}", daemon=True)
            reader.start()
            last_output = time.time()
            last_beat = 0.0
            try:
                while True:
                    try:
                        item = q.get(timeout=tick_s)
                    except queue.Empty:
                        item = ""
                    now = time.time()
                    if item is None:
                        break
                    if item:
                        log.write(item)
                        log.flush()
                        _update_progress(state, item, incremental_path)
                        last_output = now
                    state.silent_s = now - last_output
                    if stage_timeout_s and now - t0 > stage_timeout_s:
                        timed_out = True
                        result.notes.append(f"阶段墙钟超限 {stage_timeout_s:.0f}s，已终止进程组")
                        _terminate_group(proc)
                        break
                    if stall_after_s and state.silent_s > stall_after_s:
                        stalled = True
                        result.notes.append(f"静默 {state.silent_s:.0f}s > {stall_after_s:.0f}s 判卡死，已终止进程组")
                        _terminate_group(proc)
                        break
                    if on_progress is not None:
                        on_progress(state, now - t0)
                    if now - last_beat >= heartbeat_s:
                        load, mem = _sample_resources()
                        elapsed = now - t0
                        print(
                            f"  ⟳ {name:<26} {state.render()} | {elapsed:5.0f}s | 静默 {state.silent_s:4.0f}s | "
                            f"load/core {load:.2f} | mem {mem:.1f} GB | {state.last_line[:70]}"
                        )
                        last_beat = now
            except KeyboardInterrupt:
                _terminate_group(proc)
                print(f"  ⏹ 用户中断，已终止 [{name}] 的进程组")
                raise
            finally:
                exit_code = proc.wait()
                reader.join(timeout=tick_s * 2)
        elapsed = time.time() - t0
        result.exit_code = exit_code
        result.duration_s += elapsed
        result.timed_out = timed_out or result.timed_out
        result.stalled = stalled or result.stalled
        result.progress = {
            "total": state.total,
            "done": state.done,
            "percent": state.percent,
            "output_lines": state.output_lines,
            "last_line": state.last_line,
        }
        print(f"  结果: exit={exit_code} 用时 {elapsed:.0f}s 进度 {state.render()}")
        if exit_code == 0 or attempt > retries:
            break
        # 只重跑失败用例（pytest 支持 --lf；其他命令整条重跑）
        if "--lf" not in command and any("pytest" in part for part in command):
            result.notes.append(f"第 {attempt + 1} 次改为 --lf 只跑失败用例")
            command = [*command, "--lf"]
        else:
            result.notes.append(f"第 {attempt + 1} 次整条重跑")
        print(f"  ↻ 失败，准备第 {attempt + 1} 次尝试（剩余 {retries - attempt} 轮）")
    result.duration_s = time.time() - started
    return result


def _git_porcelain() -> str:
    """工作树状态（`git status --porcelain`）——冒烟证据必须绑在它上面。

    只看 `HEAD` 不够：本地改了代码而没提交时 commit 不变，旧冒烟结论会被误当成
    "同版本已通"。工作树清单对任何文件增删改都敏感，正是这里要的敏感度。
    """
    try:
        return subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def config_fingerprint(args: argparse.Namespace, models: list[str]) -> str:
    """冒烟证据的适用边界：只有这些取值相同，冒烟结论才能支撑全量开跑。

    不哈希整个 `args`——`--out`/`--jobs` 这类不改变"哪些面被覆盖"的取值不进指纹，
    否则换个输出目录就得重跑冒烟。进指纹的是矩阵形状、协议取值，以及版本与工作树
    状态（改了任何文件，旧的冒烟结论即失效）。
    """
    keys = (
        "llm_arms",
        "llm_datasets",
        "llm_profile",
        "llm_seed",
        "llm_token_cap",
        "budget_cny",
        "no_llm",
        "skip_gates",
        "skip_dataset_gate",
        "pytest_smoke_batch",
    )
    payload = {key: getattr(args, key, None) for key in keys}
    payload["models"] = sorted(models)
    payload["token_cap_default"] = NEED_BASED_TOKEN_CAP
    payload["revision"] = _git_revision()
    payload["worktree"] = hashlib.sha256(_git_porcelain().encode("utf-8")).hexdigest()[:12]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def write_smoke_evidence(out_dir: Path, fingerprint: str, results: list[StageResult]) -> dict:
    """冒烟跑完即落证据：全量档只认这份文件，不认"我记得刚才通了"。"""
    evidence = {
        "spec": SPEC_SMOKE,
        "at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "revision": _git_revision(),
        "fingerprint": fingerprint,
        "ok": all(r.ok for r in results) and bool(results),
        "stages": [
            {
                "name": r.name,
                "exit_code": r.exit_code,
                "attempts": r.attempts,
                "stalled": r.stalled,
                "timed_out": r.timed_out,
            }
            for r in results
        ],
    }
    (out_dir / SMOKE_GATE_FILE).write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8"
    )
    return evidence


def find_smoke_evidence(out_dir: Path, fingerprint: str) -> dict | None:
    """取最近一次**同指纹**且通过的冒烟证据；指纹不符等于没跑过。

    查两个根：默认结果根（`experiments/results/`）与本次 `--out` 的父目录——用户把
    运行目录指到别处时，之前的冒烟证据仍应被认出来（前提是同一配置指纹与工作树）。
    """
    candidates: list[tuple[str, dict]] = []
    seen: set[Path] = set()
    roots = [PROJECT_ROOT / "experiments" / "results", out_dir.parent]
    paths: list[Path] = []
    for root in roots:
        if root in seen or not root.is_dir():
            continue
        seen.add(root)
        paths.extend(root.glob(f"test_run_*/{SMOKE_GATE_FILE}"))
        paths.append(root / out_dir.name / SMOKE_GATE_FILE)
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("spec") == SPEC_SMOKE and data.get("ok") and data.get("fingerprint") == fingerprint:
            candidates.append((str(data.get("at", "")), data))
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


# ─── 阶段编排 ────────────────────────────────────────────────────────────────


def stage_base_env(out_dir: Path) -> dict[str, str]:
    """所有阶段共用的子进程环境（每次运行独占一个空临时根）。

    临时根不是可有可无的整洁问题：执行器把测试文件写在临时根**下**，内层 pytest
    于是把临时根挂到 ``sys.path``，其条目数直接进入每次内层运行的耗时。作者机实测
    （GL，2026-11-04）TMPDIR 根堆积 196 万条目时，一个单行用例的内层运行从 0.6s
    变成 257s —— 超过 ``EXECUTION_TIMEOUT`` 就被判超时，判定因此取决于机器历史而非
    测试结果。临时根由本运行器创建、运行结束时删除。
    """
    base_env = dict(os.environ)
    # 工作记忆口径：沙箱 broker 会让全量 pytest 随机 SIGTERM，运行器里显式摘掉。
    base_env.pop("CODEBUDDY_SANDBOX_BROKER_IPC_ADDRESS", None)
    base_env.pop("CODEBUDDY_SANDBOX_HOST_FILE_OPERATION_COMMAND", None)
    base_env.setdefault("LLM_MAX_RETRIES", "6")
    base_env.setdefault("LLM_HTTP_TIMEOUT", "600")
    base_env.setdefault("PYTHONUNBUFFERED", "1")
    tmp_root = out_dir / "tmp"
    tmp_root.mkdir(parents=True, exist_ok=True)
    # macOS/Linux 读 TMPDIR，Windows 读 TEMP/TMP——三者同指一处，子进程无论走哪个
    # 变量都落在本运行的临时根。
    for key in ("TMPDIR", "TEMP", "TMP"):
        base_env[key] = str(tmp_root)
    return base_env


def build_full_stages(args: argparse.Namespace, jobs: int, out_dir: Path, tasks_per_cell: int | None) -> list[dict]:
    """全量档（最大规格）：`make test-cov` 全量+覆盖率 → `make gates` 全链 → LLM 跑满每面。

    两段 0 LLM 面都会跑一遍全量套件（`make gates` 的 test 步骤即全量 pytest），
    这是刻意的：前者产出 `coverage.xml` 供登记册对账，后者是仓库自己的门禁口径。
    一次运行的代价是套件两遍，换的是"一次命令覆盖两种权威口径"。
    """
    base_env = stage_base_env(out_dir)
    stages: list[dict] = []

    if not args.skip_gates:
        stages.append(
            {
                # 覆盖率档：链内同口径 + coverage.xml 落仓库根供登记册对账消费
                "name": "test_cov_0llm",
                "command": [_MAKE, "test-cov"],
                "env": base_env,
                "timeout": 0,
                "retries": args.retries,
            }
        )
        stages.append(
            {
                # 门禁全链：docs/env-budget/baseline/json/zero-assert/... 全部
                "name": "gates_chain",
                "command": [_MAKE, "gates"],
                "env": base_env,
                "timeout": 0,
                "retries": args.retries,
            }
        )

    if not args.no_llm:
        # 先跑零成本/近零成本的冒烟：它验证端点与响应契约，失败就没必要花钱。
        llm_env = {**base_env, "AITESTER_SMOKE_LLM": "true"}
        stages.append(
            {
                "name": "llm_smoke",
                "command": [PYTHON, "-m", "experiments.run_smoke_llm"],
                "env": llm_env,
                "timeout": 1800,
                "retries": 1,
            }
        )
        stages.extend(_build_llm_sweep_stages(args, jobs, out_dir, base_env, tasks_per_cell))
    return stages


# ─── 冒烟档：所有面各跑一项 ──────────────────────────────────────────────────

_NODE_ID_RES = re.compile(r"^(tests/[^\s]+\.py::\S+)$")


def _first_node_id_per_file(log_path: Path) -> list[str]:
    """从 `--collect-only -q` 日志里取每个测试文件的首个 nodeid。

    "每个只跑一个"落在 pytest 面上就是"每个文件一项"：它检的是收集/导入/夹具/
    落盘这些装配环节，正是全量档最容易先坏的地方。
    """
    if not log_path.is_file():
        return []
    first: dict[str, str] = {}
    for raw in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        m = _NODE_ID_RES.match(line)
        if not m:
            continue
        node_id = m.group(1)
        file_part = node_id.split("::", 1)[0]
        first.setdefault(file_part, node_id)
    return [first[key] for key in sorted(first)]


def collect_smoke_batches(args: argparse.Namespace, out_dir: Path) -> list[list[str]]:
    """跑一次 `--collect-only` 并切成「每个测试文件 1 项」的批次（收集面归收集面）。

    与阶段装配分开：装配函数保持无副作用，便于单测直接喂批次。收集失败/为空
    返回空清单，由调用方判红——不在这里造假绿。
    """
    base_env = stage_base_env(out_dir)
    # `-qq` 不是"更安静的 -q"而是不同的输出形状：本仓 `pyproject.toml` 的 addopts 带
    # `-v`，单 `-q` 抵消后 pytest 9 打的是 `<Function …>` 收集树，取不到 nodeid 行；
    # `-qq`（verbosity −1）才逐行输出 `tests/x.py::Test::test_y`。
    collect_stage = run_stage(
        name="pytest_collect_only",
        command=[PYTHON, "-m", "pytest", "tests/", "--collect-only", "-qq", "-p", "no:cacheprovider"],
        env={**base_env, "AITESTER_SMOKE_LLM": "false"},
        cwd=PROJECT_ROOT,
        log_dir=out_dir,
        retries=0,
        stage_timeout_s=1800,
        stall_after_s=args.stall_after,
        tick_s=args.tick,
    )
    if collect_stage.exit_code != 0:
        print(f"  ❌ 收集失败 rc={collect_stage.exit_code}（冒烟档无法确定面清单）")
        return []
    node_ids = _first_node_id_per_file(out_dir / "pytest_collect_only.attempt1.log")
    if not node_ids:
        print("  ❌ 收集结果为空：冒烟档无从判定（tests/ 面取不到 nodeid）")
        return []
    print(f"  ℹ 冒烟抽样：{len(node_ids)} 个测试文件各取 1 项")
    return [node_ids[i : i + args.pytest_smoke_batch] for i in range(0, len(node_ids), args.pytest_smoke_batch)]


def read_gate_targets() -> list[str]:
    """从 Makefile 的 `gates:` 先决条件行取门禁目标清单（唯一事实源＝写入端）。

    冒烟档要覆盖"所有需要跑的面"，因此不能写死一份清单——门禁链加/减一道时，
    冒烟档必须跟着变，否则新门禁只在全量档第一次被发现。`test` 不在冒烟档里
    单独跑（它的"面"是各测试文件，由抽样阶段逐项覆盖，跑满全量违背每面 1 项的口径）。
    """
    makefile = PROJECT_ROOT / "Makefile"
    if not makefile.is_file():
        return []
    for line in makefile.read_text(encoding="utf-8").splitlines():
        if line.startswith("gates:"):
            head = line.split("##", 1)[0]
            return [token for token in head.split(":", 1)[1].split() if token and token != "test"]
    return []


#: 无人值守期间的三个外部观察面：活锁、进度、终态标记。
LOCK_FILE = "RUNNING.lock"
PROGRESS_FILE = "PROGRESS.json"
DONE_FILE = "DONE.json"


class ProgressWriter:
    """把运行进度持续写进 `PROGRESS.json`（原子替换），供无人看守时外部读取。

    每阶段写：阶段序号 / 该阶段 done/total / 用时 / ETA / 最近输出行 / 卡死次数；
    全局写：完成阶段占比（未知进度的阶段按 0 计，不用假数据抬高总进度）。
    """

    def __init__(self, path: Path, stages_total: int) -> None:
        self.path = path
        self.stages_total = max(1, stages_total)
        self.stage_index = 0
        self.stage_name = ""
        self.started_s = time.time()
        self.stalls = 0
        self.state = ProgressState()
        self.stage_elapsed = 0.0
        self.finished: dict[str, Any] | None = None

    def begin_stage(self, index: int, name: str) -> None:
        self.stage_index = index
        self.stage_name = name
        self.state = ProgressState()
        self.stage_elapsed = 0.0
        self.dump()

    def tick(self, state: ProgressState, elapsed: float) -> None:
        self.state = state
        self.stage_elapsed = elapsed
        self.dump()

    def overall_percent(self) -> float:
        frac = 0.0
        if self.state.total > 0:
            frac = min(1.0, self.state.done / self.state.total)
        return (self.stage_index - 1 + frac) / self.stages_total * 100.0

    def eta_s(self) -> float | None:
        if self.state.total and self.state.done and self.stage_elapsed > 0:
            per_done = self.stage_elapsed / self.state.done
            return round(per_done * max(0, self.state.total - self.state.done), 1)
        return None

    def dump(self) -> None:
        payload = {
            "updated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "stage_index": self.stage_index,
            "stages_total": self.stages_total,
            "stage": self.stage_name,
            "stage_done": self.state.done,
            "stage_total": self.state.total,
            "stage_elapsed_s": round(self.stage_elapsed, 1),
            "stage_eta_s": self.eta_s(),
            "overall_percent": round(self.overall_percent(), 2),
            "run_elapsed_s": round(time.time() - self.started_s, 1),
            "stalls": self.stalls,
            "last_line": self.state.last_line[:160],
            "finished": self.finished,
        }
        tmp = self.path.with_suffix(".json.tmp")
        try:
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            pass  # 进度面板不得成为运行失败的原因；写不进去就只丢显示

    def finish(self, rc: int, ok_stages: int, failed_stages: int) -> None:
        self.finished = {
            "rc": rc,
            "ok_stages": ok_stages,
            "failed_stages": failed_stages,
            "at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        self.dump()


class RunLockError(RuntimeError):
    """已有活着的运行器在跑（重入锁）。"""


def acquire_run_lock(out_dir: Path, fingerprint: str, force: bool) -> Path:
    """写 `RUNNING.lock`（pid + 心跳时间）；同目录已有活锁时拒绝并发运行。

    2026-11-02 的队列失控事故（launchd `KeepAlive` 反复重拉 ⇒ 983 个孤儿判定
    进程、load 747）就是缺这一层；无人值守更要它，因为没人看见重复启动。
    """
    path = out_dir / LOCK_FILE
    if path.is_file() and not force:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            pid = int(payload.get("pid", -1))
        except (OSError, ValueError, TypeError):
            pid = -1
        alive = False
        if pid > 0:
            try:
                os.kill(pid, 0)
                alive = True
            except ProcessLookupError:
                alive = False
            except PermissionError:
                alive = True  # 存在但属别人——同样不得并发
        if alive:
            raise RunLockError(f"{path} 记录的 pid={pid} 仍活着；确要并发用 --force-restart")
    path.write_text(
        json.dumps(
            {"pid": os.getpid(), "started_at": datetime.now(UTC).isoformat(), "fingerprint": fingerprint},
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        ),
        encoding="utf-8",
    )
    return path


def build_smoke_stages(
    args: argparse.Namespace, jobs: int, out_dir: Path, smoke_batches: list[list[str]]
) -> list[dict]:
    """冒烟档：每个面只跑一项，用来确认"跑得起来"，不产出任何判定读数。"""
    base_env = stage_base_env(out_dir)
    stages: list[dict] = []

    if not args.skip_gates:
        stages.append(
            {
                "name": "gates_fast",
                # 不带 `-q`：addopts 的 `-v` 才产出逐用例行，进度计数才有来源
                "command": [
                    PYTHON,
                    "-m",
                    "pytest",
                    "tests/test_llm_configs_schema.py",
                    "tests/test_repo_hygiene_cx.py",
                    "--no-header",
                ],
                "env": base_env,
                "timeout": 1800,
                "retries": 0,
            }
        )
        # 所有门禁面都要在冒烟档走一遍：链上每道非 test 门禁各跑一次。
        # 清单从 Makefile 的 `gates:` 先决条件现取，门禁链加/减一道时这里跟着变，
        # 不留"新门禁只在全量档第一次被发现"的洞。某道门禁在冒烟档红，全量档同样会红
        # ⇒ 阻塞是对的，不是误伤。
        stages += [
            {
                "name": f"smoke_gate_{target}"[:60],
                "command": [_MAKE, target],
                "env": base_env,
                "timeout": 1800,
                "retries": 0,
            }
            for target in read_gate_targets()
        ]

    # 1) pytest 面：每个测试文件 1 项（检的是收集/导入/夹具/落盘这些装配环节）
    if not smoke_batches:
        # 抽样为空 = 收集失败或 tests/ 面不可见，绝不能读作"冒烟通过"
        stages.append(
            {
                "name": "pytest_smoke_no_samples",
                "command": [PYTHON, "-c", "raise SystemExit('冒烟档取不到任何抽样项：收集为空/失败，判红而非放行')"],
                "env": base_env,
                "timeout": 60,
                "retries": 0,
            }
        )
    for index, batch in enumerate(smoke_batches, start=1):
        stages.append(
            {
                "name": f"pytest_smoke_{index}",
                "command": [
                    PYTHON,
                    "-m",
                    "pytest",
                    *batch,
                    "-n",
                    str(jobs),
                    f"--timeout={PYTEST_TIMEOUT_SECONDS}",
                    "--timeout-method=thread",
                    "--strict-markers",
                    "--no-header",
                    "--tb=short",
                ],
                "env": {**base_env, "AITESTER_SMOKE_LLM": "false"},
                "timeout": 1800,
                "retries": args.retries,
            }
        )

    if not args.no_llm:
        # 2) LLM 面：端点契约冒烟 + 每个「模型 × 臂 × 面」1 个任务（真调用，最小额度）
        stages.append(
            {
                "name": "llm_smoke",
                "command": [PYTHON, "-m", "experiments.run_smoke_llm"],
                "env": {**base_env, "AITESTER_SMOKE_LLM": "true"},
                "timeout": 1800,
                "retries": 1,
            }
        )
        stages.extend(_build_llm_sweep_stages(args, jobs, out_dir, base_env, SMOKE_TASKS_PER_CELL))
    return stages


def _completed_task_ids(stage_dir: Path) -> list[str]:
    """从上一轮的 INCREMENTAL_RESULTS.jsonl 读已完成任务 id（续跑不再付费）。"""
    path = stage_dir / "INCREMENTAL_RESULTS.jsonl"
    if not path.is_file():
        return []
    done: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue  # 半行（崩溃时截断）跳过，不猜测内容
        task_id = row.get("task_id") or row.get("instance_id")
        if task_id and str(task_id) not in done:
            done.append(str(task_id))
    return done


def llm_scale_plan(args: argparse.Namespace, tasks_per_cell: int | None) -> dict:
    """规模与预算的**唯一算式**：投影与实跑阶段共用它，避免两处各算一遍再漂移。

    `tasks_per_cell=None` ⇒ 每个数据集面跑满（上限现取加载器）；给数字 ⇒ 每面固定
    任务数（smoke 档用 1）。面名先经注册表核验——`load_dataset` 对未登记名称静默降级
    为内置示例面（3 条假任务），拼错的面名会让"跑满"变成假的。不可读的面逐个剔除并
    披露（数据未下载不等于配置错误），全部不可读才整段拒跑。
    """
    models, out_prices, currency = load_price_and_models()
    arms = [a.strip() for a in args.llm_arms.split(",") if a.strip()]
    requested = resolve_dataset_faces(args.llm_datasets)
    # 冒烟档给了 tasks_per_cell 就不需要真实上限；满量档必须逐面实测任务数，
    # 否则"跑满"没有依据，投影也没有依据。
    counts: dict[str, int | None] = {ds: (tasks_per_cell or dataset_task_count(ds)) for ds in requested}
    unavailable = sorted(ds for ds, count in counts.items() if not count)
    datasets = [ds for ds in requested if ds not in unavailable]
    if unavailable:
        print(f"  ⚠ 本轮剔除不可读的数据面（数据未下载/为空）：{unavailable}；其余面仍跑满")
    # 注册表里有别名与"同加载器不同数据目录"的兄弟名；数据目录未配置时它们解析到
    # 同一批任务。按数据身份（任务数 + 首末 task_id）去重，否则同一批数据被铺两遍：
    # 双倍付费，且读数看着像两个独立面。同组内保留最短名（`quixbugs` 而非 `quix_bugs`，
    # 与本仓跑批脚本的用法一致），其余别名逐个点名剔除。
    by_sig: dict[tuple[int, str, str], list[str]] = {}
    for ds in datasets:
        sig = dataset_signature(ds)
        if sig is not None:
            by_sig.setdefault(sig, []).append(ds)
    faces: dict[str, int | None] = {}
    for sig, names in by_sig.items():
        names = sorted(names, key=lambda n: (len(n), n))
        keeper = names[0]
        for dup in names[1:]:
            print(f"  ⚠ 面 {dup} 与 {keeper} 指向同一批数据（{sig[0]} 条，{sig[1]} … {sig[2]}）——已剔除，不重复付费")
        faces[keeper] = counts[keeper]
    datasets = list(faces)
    scale = "{} 模型 × {} 臂 × {} 个面（{}）".format(
        len(models), len(arms), len(datasets), " + ".join(f"{ds}×{c}" for ds, c in faces.items()) or "无可用面"
    )
    tasks_total = len(models) * len(arms) * (sum(faces.values()) if faces else 0)
    plan = plan_llm_budget(tasks_total, args.budget_cny, out_prices, currency, args.llm_token_cap)
    plan["scale"] = scale
    if not datasets:
        plan = {
            **plan,
            "provable": False,
            "fits_budget": False,
            "reason": f"请求的面全部不可读（{requested}）——没有数据面可跑，拒跑而非跑空",
        }
    return {"models": models, "arms": arms, "datasets": datasets, "face_counts": faces, "plan": plan}


def print_llm_projection(args: argparse.Namespace, tasks_per_cell: int | None) -> int:
    """打印 LLM 段费用投影（零执行、零花费），返回 0=在需要与预算内 / 1=不该开跑。

    独立于阶段编排：`--estimate-llm` 必须在建阶段之前短路，否则它会连着把
    0LLM 全量套件跑一遍——那已经不是"只投影"了。
    """
    scale = llm_scale_plan(args, tasks_per_cell)
    if not scale["models"]:
        print("LLM 段投影：未配置任何 LLM 端点，无花费")
        return 0
    _print_plan(scale["plan"], scale["plan"]["scale"])
    return 0 if scale["plan"]["provable"] and scale["plan"]["fits_budget"] else 1


def _print_plan(plan: dict, scale: str) -> None:
    """投影打印（统一格式，供 --estimate-llm 与实跑前复用）。"""
    print("-" * 78)
    print("LLM 段费用投影（口径：全部 token 按价目表最贵的输出单价计，故为保守上界）")
    print(f"  规模            : {scale} = {plan['tasks_total']} 任务")
    print(f"  每任务 token 上限: {plan['per_task_token_cap']}（按实测需要定，超限走 budget_exceeded 停止）")
    print(f"  最坏输出单价    : {plan['worst_price_per_mtok']} / 百万 {plan['currency']}")
    print(
        f"  费用上界        : {plan['upper_bound']} {plan['currency']}（预算上限 {plan['budget']}；按每任务上限的最坏档计价）"
    )
    if plan.get("measured_reference") is not None:
        print(
            f"  实测参考（仅输出侧）: {plan['measured_reference']} {plan['currency']}"
            f"（基数 {plan['measured_basis']}，2026-11-04 单条调用实测；输入侧同量级另计）"
        )
    print(f"  判定            : {plan['reason']}")
    if plan.get("advice"):
        print(f"  降本顺序        : {plan['advice']}")


def _off_peak_wait_stage(args: argparse.Namespace, base_env: dict[str, str]) -> dict | None:
    """空闲窗等待段（官方半价窗口；同参数移窗执行 = 测量等价、账单减半）。"""
    if not args.off_peak:
        return None
    now_h = time.localtime().tm_hour
    if in_off_peak(now_h):
        print(f"  ℹ 当前 {now_h} 时已在空闲窗 {OFF_PEAK_WINDOWS}，无需等待")
        return None
    # 下一个窗口起点
    nxt = min(((s if s > now_h else s + 24) - now_h, s) for s, _ in OFF_PEAK_WINDOWS)[0]
    if nxt > args.off_peak_max_wait_hours:
        print(f"  ⚠ 距下一空闲窗 {nxt}h 超过 --off-peak-max-wait-hours={args.off_peak_max_wait_hours}，不等待")
        return None
    print(f"  ⏳ 距下一空闲窗约 {nxt}h，等待后再跑 LLM 段（账单按官方空闲半价）")
    sleep_s = nxt * 3600
    return {
        "name": "wait_off_peak",
        "command": [PYTHON, "-c", f"import time; time.sleep({sleep_s})"],
        "env": base_env,
        "timeout": sleep_s + 600,
        "retries": 0,
    }


#: 玩具面（内置示例/合成数据）不算基准面：它们恒为 3 条，把"跑满"变成假读数。
TOY_DATASET_FACES = ("examples", "in_memory", "synth", "synthetic")


def registered_dataset_faces() -> list[str]:
    """加载器注册表里的基准面清单（唯一事实源＝`src/datasets/dataset_loader.py`）。

    `load_dataset` 对**未登记名称**降级为内置示例数据集（其 docstring 明写的宽容
    契约），所以面名拼错不会报错，只会安静地跑出 3 条假任务——满量档必须在调用前
    逐名核验注册表，否则"跑满"是假的。
    """
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from src.datasets.dataset_loader import get_available_datasets

    return [name for name in get_available_datasets() if name not in TOY_DATASET_FACES]


def resolve_dataset_faces(requested: str) -> list[str]:
    """把 `--llm-datasets` 解析成经过注册表核验的面清单（`all` = 全部基准面）。"""
    registered = registered_dataset_faces()
    tokens = [t.strip() for t in (requested or "").split(",") if t.strip()]
    if not tokens or tokens == ["all"]:
        return registered
    unknown = [t for t in tokens if t not in registered]
    if unknown:
        raise ValueError(
            f"数据集面 {unknown} 不在加载器注册表内——`load_dataset` 会静默降级为内置示例面（3 条假任务）。"
            f"可用面：{registered}"
        )
    # 去重且保持用户给的顺序（单一变量的要求：同一面不得被铺两遍、付两次钱）
    seen: set[str] = set()
    ordered = []
    for token in tokens:
        if token not in seen:
            seen.add(token)
            ordered.append(token)
    return ordered


def dataset_task_count(name: str) -> int | None:
    """数据集面的任务上限（`-n` 不给时 run_benchmark 跑全部，投影需要这个数）。

    取不到或为 0（数据未下载）都返回 None——投影宁可判"该面无数据可读"并披露，
    也不要按 0 个任务假装跑满，或在价格事实源缺失时假装预算安全。
    """
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    sig = dataset_signature(name)
    return sig[0] if sig else None


def dataset_signature(name: str) -> tuple[int, str, str] | None:
    """(任务数, 首个 task_id, 末个 task_id)；数据缺失或加载失败返回 None。

    带上首末 id 是为了识别"两个面其实指向同一批数据"——同一批数据被铺两遍就是双倍
    付费，光看任务数相同看不出这件事。
    """
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    try:
        from src.datasets.dataset_loader import load_dataset

        tasks = list(load_dataset(name))
        if not tasks:
            return None
        return len(tasks), str(getattr(tasks[0], "task_id", "") or ""), str(getattr(tasks[-1], "task_id", "") or "")
    except Exception as exc:  # 数据集面加载失败面广（缺失/损坏/依赖），一律按"不可读"处理
        print(f"  ⚠ 数据集面 {name} 不可读：{type(exc).__name__}: {str(exc)[:80]}")
        return None


def _build_llm_sweep_stages(
    args: argparse.Namespace,
    jobs: int,
    out_dir: Path,
    base_env: dict[str, str],
    tasks_per_cell: int | None,
) -> list[dict]:
    """按「模型 × 基线臂 × 数据集面」铺阶段；`tasks_per_cell=None` ⇒ 每面跑满。

    小规模贯通：每个「模型 × 基线臂 × 数据集面」一小批，费用上界可投影。

    单一变量（用户第 12 条）：模型只能有一个变化维度——每个阶段用
    `AITESTER_LLM_MODEL_FILTER` 钉住单一模型（run_benchmark 按 task_index 轮询
    端点，不钉住时"模型"会随"任务"一起变），协议其余变量逐阶段同值。

    降本三档（用户排序：输出 > 未命中输入 > 命中输入）：
    ① 每任务 token 上限按实测需要定，超限走 `budget_exceeded` 停止通道——不用
       `LLM_MAX_OUTPUT_TOKENS`（截断会被判可恢复失败并重试，反而更贵）；
    ② 免费闸先筛掉永不产生数据的任务，并把重跑/重试引到身份键缓存上命中；
    ③ 可选移到官方空闲半价窗（参数不变 ⇒ 测量等价）。
    """
    scale = llm_scale_plan(args, tasks_per_cell)
    models, arms, datasets, face_counts, plan = (
        scale["models"],
        scale["arms"],
        scale["datasets"],
        scale["face_counts"],
        scale["plan"],
    )
    if not models:
        print("  ⚠ 未配置任何 LLM 端点，跳过 LLM 贯通段")
        return []
    tasks_total = plan["tasks_total"]
    args._llm_budget_plan = plan  # 供 main() 打印与报告落盘

    stages: list[dict] = []
    # 付费前的免费闸：数据集加载质量（零 LLM，零成本）。加载不出的面
    # 不可能产生判定，先花 0 元确认，再决定是否花钱。
    if not args.skip_dataset_gate:
        stages += [
            {
                "name": f"dataset_gate_{ds}"[:60],
                "command": [PYTHON, str(PROJECT_ROOT / "main.py"), "check-dataset", ds],
                "env": {**base_env, "AITESTER_SMOKE_LLM": "false"},
                "timeout": 900,
                "retries": 0,
            }
            for ds in datasets
        ]

    if not plan["provable"] or not plan["fits_budget"]:
        print(f"  ❌ LLM 段不开跑：{plan['reason']}")
        if plan.get("advice"):
            print(f"     → {plan['advice']}")
        stages.append(
            {
                "name": "llm_sweep_refused",
                "command": [PYTHON, "-c", f"raise SystemExit('LLM sweep not within need/budget: {plan['reason']}')"],
                "env": base_env,
                "timeout": 60,
                "retries": 0,
            }
        )
        return stages

    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from src.budget.batch_quota import estimate_calls

    wait = _off_peak_wait_stage(args, base_env)
    if wait:
        stages.append(wait)

    llm_jobs = max(1, min(jobs, LLM_PARALLELISM_CAP))
    worst = plan["worst_price_per_mtok"] or 0.0
    # 单任务金额闸按**需要**定（上限 × 最坏输出单价），不是预算 ÷ 任务数
    per_task_money = round(plan["per_task_token_cap"] * worst / 1_000_000, 6)
    batch_max_calls = estimate_calls(tasks_total)
    for model in models:
        for arm in arms:
            for ds in datasets:
                slug = f"{model}__{arm}__{ds}".replace(".", "-")
                ns = f"allrun_{slug}"[:80]
                stage_dir = out_dir / "llm_sweep" / slug
                env = {
                    **base_env,
                    # ① 钉住模型：同批只可能有一个模型，跨模型差异才可归因
                    "AITESTER_LLM_MODEL_FILTER": model,
                    # ② 需要口径的硬闸（金额按价目表基准币种解释）
                    "COST_BUDGET_ENABLE": "true",
                    "COST_BUDGET_TOKENS": str(plan["per_task_token_cap"]),
                    "COST_BUDGET_USD": str(per_task_money),
                    "AITESTER_BATCH_MAX_CALLS": str(batch_max_calls),
                    "AITESTER_BATCH_MAX_USD": str(plan["upper_bound"]),
                    # ③ 身份键缓存复用（重跑/重试零增量成本），namespace 阶段隔离
                    "AITESTER_LLM_CACHE": "1",
                    "AITESTER_CACHE_NAMESPACE": ns,
                    # 逐阶段同值的协议变量（单一变量的"同值"部分）
                    "AITESTER_PROFILE": args.llm_profile,
                    "TEMPERATURE": "0.0",
                    "AITESTER_SMOKE_LLM": "false",
                }
                if args.resume_dir:
                    done = _completed_task_ids(Path(args.resume_dir) / "llm_sweep" / slug)
                    if done:
                        env["AITESTER_SKIP_TASK_IDS"] = ",".join(done)
                        print(f"  ↻ {slug}: 续跑跳过 {len(done)} 个已完成任务（不二次付费）")
                command = [
                    PYTHON,
                    str(PROJECT_ROOT / "experiments" / "run_benchmark.py"),
                    "-d",
                    ds,
                    "-b",
                    arm,
                    "-p",
                    str(llm_jobs),
                    "--seed",
                    str(args.llm_seed),
                    "-o",
                    str(stage_dir),
                ]
                # full 档不给 `-n` ⇒ run_benchmark 跑满该面（--task-limit 默认 None）
                if face_counts[ds]:
                    command += ["-n", str(face_counts[ds])]
                stages.append(
                    {
                        "name": f"llm_{slug}"[:60],
                        "command": command,
                        "env": env,
                        "timeout": args.llm_stage_timeout,
                        "retries": args.llm_retries,
                        "incremental": str(stage_dir / "INCREMENTAL_RESULTS.jsonl"),
                    }
                )
    return stages


def _git_revision() -> str:
    try:
        return (
            subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=str(PROJECT_ROOT),
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            ).stdout.strip()
            or "unknown"
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="全量测试监测运行器（0LLM + LLM）")
    parser.add_argument(
        "--spec",
        choices=SPEC_CHOICES,
        default=SPEC_BOTH,
        help="档位：smoke=所有面各跑 1 项（查装配是否通）；full=最大量（pytest 全量+门禁全链+LLM 跑满每面）；"
        "both=先 smoke 后 full，冒烟未全通则全量一个阶段都不开跑（默认）",
    )
    parser.add_argument("--jobs", type=int, default=None, help="并行度（默认按本机核数/内存自动定）")
    parser.add_argument("--retries", type=int, default=3, help="失败重跑轮数（默认 3）")
    parser.add_argument("--no-llm", action="store_true", help="跳过真 LLM 阶段")
    parser.add_argument("--skip-gates", action="store_true", help="跳过门禁档（full 档跳过即不跑 test-cov/gates）")
    parser.add_argument("--out", default=None, help="报告目录（默认 experiments/results/test_run_<ts>）")
    parser.add_argument("--selftest", action="store_true", help="只验运行器自身")
    # ─── 进度与卡死监测 ─────────────────────────────────────────────────────────
    parser.add_argument("--stall-after", type=float, default=600.0, help="无输出多少秒判卡死（终止整个进程组并重跑）")
    parser.add_argument("--tick", type=float, default=5.0, help="主循环节拍秒（静默与墙钟判断的分辨率）")
    parser.add_argument("--heartbeat", type=float, default=30.0, help="进度打印间隔秒")
    parser.add_argument("--allow-stale-smoke", action="store_true", help="跳过「冒烟必须先通过」前置（显式承担风险）")
    parser.add_argument(
        "--max-wall-hours", type=float, default=12.0, help="整轮墙钟上限小时（0=不限；到点不再开新阶段）"
    )
    parser.add_argument("--max-stalls", type=int, default=6, help="累计卡死次数上限（超过即停止开新阶段）")
    parser.add_argument("--force-restart", action="store_true", help="忽略 RUNNING.lock 活锁强行开跑（并发风险自负）")
    parser.add_argument(
        "--pytest-smoke-batch", type=int, default=400, help="冒烟档每批 nodeid 数（受 argv 长度约束，非按文件切）"
    )
    # ── LLM 贯通段（降本口径：每任务上限按实测需要取，不由预算反推，也不做事后拦截）──
    parser.add_argument(
        "--llm-tasks",
        type=int,
        default=None,
        help="full 档每面任务数（不给=跑满数据集面；smoke 档固定 1，不受本项影响）",
    )
    parser.add_argument("--llm-arms", default=DEFAULT_LLM_ARMS, help="基线臂（逗号分隔）")
    parser.add_argument(
        "--llm-datasets",
        default=DEFAULT_LLM_DATASETS,
        help="数据集面（逗号分隔；all 或留空＝加载器注册表里的全部基准面，名称拼错直接拒跑而非降级）",
    )
    parser.add_argument("--llm-profile", default="logic", help="协议档位（跨阶段同值，默认 logic 论文口径）")
    parser.add_argument("--llm-seed", type=int, default=42, help="随机种子（跨阶段同值）")
    parser.add_argument("--llm-retries", type=int, default=1, help="LLM 阶段失败重跑轮数（重跑走缓存，不二次付费）")
    parser.add_argument("--llm-stage-timeout", type=int, default=5400, help="单阶段墙钟上限秒")
    parser.add_argument(
        "--budget-cny", type=float, default=DEFAULT_BUDGET_CNY, help="本轮 LLM 段费用上界（登记币种，默认 ¥300）"
    )
    parser.add_argument(
        "--llm-token-cap",
        type=int,
        default=None,
        help=f"每任务 token 上限（默认按需要取 {NEED_BASED_TOKEN_CAP}，不按预算反推）",
    )
    parser.add_argument("--estimate-llm", action="store_true", help="只打印 LLM 段费用投影，不跑也不花钱")
    parser.add_argument("--skip-dataset-gate", action="store_true", help="跳过付费前的零成本数据集闸")
    parser.add_argument("--resume-dir", default=None, help="上一轮报告目录：已完成的任务跳过，不二次付费")
    parser.add_argument("--off-peak", action="store_true", help="等到官方空闲半价窗再跑 LLM 段（测量等价，账单约减半）")
    parser.add_argument("--off-peak-max-wait-hours", type=int, default=10, help="空闲窗最长等待小时数（超时不等待）")
    return parser


def _execute_stages(
    stages: list[dict],
    out_dir: Path,
    args: argparse.Namespace,
    writer: ProgressWriter | None = None,
    index_offset: int = 0,
    deadline: float | None = None,
    stall_budget: int | None = None,
) -> tuple[list[StageResult], int]:
    """顺序执行阶段清单：进度显示、卡死检测，外加运行级封顶。

    无人值守的四道闸：单阶段静默（`--stall-after`）→ 单阶段墙钟（阶段 timeout）→
    整轮墙钟（`--max-wall-hours`）与累计卡死次数（`--max-stalls`）。后两者触发时
    **不再开新阶段**，并落一条命名失败的阶段记录——静默少跑不得读成跑通。

    Returns:
        `(results, stalls_used)`。
    """
    results: list[StageResult] = []
    stalls = 0
    for offset, spec in enumerate(stages):
        index = index_offset + offset + 1
        if deadline is not None and time.time() > deadline:
            print(f"  ⛔ 整轮墙钟上限已到，剩余 {len(stages) - offset} 个阶段不再开跑")
            results.append(
                StageResult(
                    name="aborted_wall_clock",
                    command=[],
                    exit_code=1,
                    notes=[f"总时限到点未跑：{spec['name']} 等 {len(stages) - offset} 个阶段"],
                )
            )
            break
        if stall_budget is not None and stalls > stall_budget:
            print(f"  ⛔ 累计卡死 {stalls} 次超过 --max-stalls={stall_budget}，停止开新阶段")
            results.append(
                StageResult(
                    name="aborted_stall_budget",
                    command=[],
                    exit_code=1,
                    notes=[f"卡死预算耗尽后未跑：{spec['name']} 等 {len(stages) - offset} 个阶段"],
                )
            )
            break
        incremental = Path(spec["incremental"]) if spec.get("incremental") else None
        on_progress = None
        if writer is not None:
            writer.begin_stage(index, spec["name"])
            on_progress = writer.tick
        result = run_stage(
            name=spec["name"],
            command=spec["command"],
            env=spec["env"],
            cwd=PROJECT_ROOT,
            log_dir=out_dir,
            retries=spec["retries"],
            stage_timeout_s=spec["timeout"],
            stall_after_s=args.stall_after,
            tick_s=args.tick,
            incremental_path=incremental,
            on_progress=on_progress,
        )
        results.append(result)
        if result.stalled:
            stalls += 1
        if writer is not None:
            writer.stalls = stalls
            writer.dump()
    return results, stalls


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    cpu = detect_cpu_count()
    mem_gb = detect_memory_gb()
    jobs, jobs_reason = plan_jobs(cpu, mem_gb, args.jobs)

    if args.selftest:
        print(f"CPU 物理核: {cpu}")
        print(f"内存: {mem_gb:.1f} GB")
        print(f"并行度: {jobs}（{jobs_reason}）")
        print(f"pytest 单测超时: {PYTEST_TIMEOUT_SECONDS}s")
        print(f"档位: {args.spec}（smoke 每格 {SMOKE_TASKS_PER_CELL} 任务；full 不给 --llm-tasks 即跑满每面）")
        print(f"卡死监测: 静默 {args.stall_after}s 击杀进程组，节拍 {args.tick}s")
        assert jobs >= 1 and PYTEST_TIMEOUT_SECONDS >= 600
        assert args.tick > 0 and args.stall_after >= args.tick, "节拍必须小于静默阈值，否则卡死检测不触发"
        assert args.max_stalls >= 0 and args.max_wall_hours >= 0, "封顶参数不得为负"
        targets = read_gate_targets()
        assert targets and "test" not in targets, f"门禁面清单异常：{targets[:3]}"
        assert args.spec in SPEC_CHOICES, f"未知档位 {args.spec}"
        assert SMOKE_TASKS_PER_CELL == 1 and _PERCENT_RES.search("[ 27%]") and _TOTAL_RES[2].search("待运行任务数: 50")
        print("selftest 通过")
        return 0

    # 面名先核验再谈别的：`load_dataset` 会把未登记名称降级成 3 条内置示例，
    # 让"跑满所有面"静默变成"跑了 3 条假任务"。
    try:
        resolve_dataset_faces(args.llm_datasets)
    except ValueError as exc:
        print(f"❌ 数据集面校验失败：{exc}")
        return 1

    # 投影必须先于任何执行与建目录：`--estimate-llm` 的语义是"只看不花钱"。
    if args.estimate_llm:
        print(f"【冒烟档 {SPEC_SMOKE}】每格 {SMOKE_TASKS_PER_CELL} 任务")
        smoke_rc = print_llm_projection(args, SMOKE_TASKS_PER_CELL)
        print(f"\n【全量档 {SPEC_FULL}】不给 --llm-tasks 即跑满每个数据集面")
        full_rc = print_llm_projection(args, args.llm_tasks or None)
        return 0 if smoke_rc == 0 and full_rc == 0 else 1

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out) if args.out else PROJECT_ROOT / "experiments" / "results" / f"test_run_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    fingerprint = config_fingerprint(args, load_price_and_models()[0])

    print("=" * 78)
    print(f"全量测试运行器  {stamp}  档位={args.spec}")
    print(f"本机: {platform.platform()} | {cpu} 核 | {mem_gb:.1f} GB")
    print(f"并行度: {jobs}（{jobs_reason}）| 单测超时 {PYTEST_TIMEOUT_SECONDS}s | 重跑 {args.retries} 轮")
    print(
        f"卡死监测: 静默 {args.stall_after}s ⇒ 终止进程组并重跑 | 心跳 {args.heartbeat}s | "
        f"累计卡死上限 {args.max_stalls} 次 | 整轮墙钟 {args.max_wall_hours or '不限'}h"
    )
    print(f"LLM 阶段: {'跳过' if args.no_llm else '包含'} | 配置指纹 {fingerprint}（冒烟证据按它判定适用性）")
    print(f"报告目录: {out_dir}（进度实时写 {PROGRESS_FILE}，活锁 {LOCK_FILE}，终态 {DONE_FILE}）")
    print("=" * 78)

    results: list[StageResult] = []
    plans: dict[str, dict] = {}
    smoke_evidence: dict | None = None
    rc = 1
    stalls = 0
    t_start = time.time()
    deadline = t_start + args.max_wall_hours * 3600 if args.max_wall_hours else None

    try:
        lock_path = acquire_run_lock(out_dir, fingerprint, args.force_restart)
    except RunLockError as exc:
        print(f"❌ 拒绝并发运行：{exc}")
        return 1

    try:
        smoke_stages: list[dict] = []
        full_stages: list[dict] = []
        if args.spec in (SPEC_SMOKE, SPEC_BOTH):
            smoke_stages = build_smoke_stages(args, jobs, out_dir, collect_smoke_batches(args, out_dir))
        run_full = args.spec in (SPEC_FULL, SPEC_BOTH)
        if run_full:
            if args.spec == SPEC_FULL and not args.allow_stale_smoke:
                found = find_smoke_evidence(out_dir, fingerprint)
                if not found:
                    print(
                        "❌ 全量档未开跑：没有与本配置同指纹、且通过的冒烟证据。\n"
                        f"   先跑：{' '.join([shlex.quote(sys.executable), str(Path(__file__)), f'--spec {SPEC_SMOKE}'])}\n"
                        f"   （证据文件 {SMOKE_GATE_FILE} 需匹配指纹 {fingerprint}；确要跳过用 --allow-stale-smoke）"
                    )
                    return 1
                print(f"✅ 冒烟前置满足：{found['at']} 指纹 {found['fingerprint']}")
            full_stages = build_full_stages(args, jobs, out_dir, args.llm_tasks or None)

        writer = ProgressWriter(out_dir / PROGRESS_FILE, len(smoke_stages) + len(full_stages))
        stalls = 0
        if smoke_stages:
            smoke_results, used = _execute_stages(smoke_stages, out_dir, args, writer, 0, deadline, args.max_stalls)
            stalls += used
            results += smoke_results
            plans[SPEC_SMOKE] = getattr(args, "_llm_budget_plan", {}) or {}
            smoke_evidence = write_smoke_evidence(out_dir, fingerprint, smoke_results)
            print(f"\n冒烟结论: {'全通' if smoke_evidence['ok'] else '未全通'}（阶段 {len(smoke_results)} 个）")

        if run_full and full_stages and (smoke_evidence is None or smoke_evidence["ok"]):
            full_results, used = _execute_stages(
                full_stages, out_dir, args, writer, len(smoke_stages), deadline, args.max_stalls - stalls
            )
            stalls += used
            results += full_results
            plans[SPEC_FULL] = getattr(args, "_llm_budget_plan", {}) or {}
        elif run_full and not full_stages:
            print("❌ 全量档阶段清单为空（门禁档与 LLM 档同时关闭）：没有可验证的内容，判不通过而非静默通过")
            results.append(StageResult(name="full_no_stages", command=[], exit_code=1, notes=["无阶段可跑"]))
        elif run_full and smoke_evidence is not None and not smoke_evidence["ok"]:
            print("❌ 冒烟未全通 ⇒ 全量档一个阶段都不启动（花钱的面保持零调用）")

        rc = 0 if results and all(r.ok for r in results) else 1
        writer.finish(rc, sum(1 for r in results if r.ok), sum(1 for r in results if not r.ok))
    finally:
        total = time.time() - t_start
        # 临时根按运行独占（目录含时间戳），异常中断也不会污染下一次运行；跑完即回收，
        # 否则"每次运行留下判定临时目录"会累积成下一轮的速度与判定问题（GL 现场）。
        shutil.rmtree(out_dir / "tmp", ignore_errors=True)
        lock_path.unlink(missing_ok=True)
    report = {
        "generated_at": stamp,
        "revision": _git_revision(),
        "spec": args.spec,
        "fingerprint": fingerprint,
        "host": {
            "platform": platform.platform(),
            "cpu_physical": cpu,
            "memory_gb": round(mem_gb, 1),
            "jobs": jobs,
            "jobs_reason": jobs_reason,
        },
        "config": {
            "pytest_timeout_s": PYTEST_TIMEOUT_SECONDS,
            "retries": args.retries,
            "stall_after_s": args.stall_after,
            "tick_s": args.tick,
            "heartbeat_s": args.heartbeat,
            "llm_included": not args.no_llm,
            "llm_budget_plans": plans,
            "max_wall_hours": args.max_wall_hours,
            "max_stalls": args.max_stalls,
        },
        "rc": rc,
        "stalls": stalls,
        "smoke_gate": smoke_evidence,
        "total_duration_s": round(total, 1),
        "stages": [
            {
                "name": r.name,
                "exit_code": r.exit_code,
                "ok": r.ok,
                "duration_s": round(r.duration_s, 1),
                "attempts": r.attempts,
                "timed_out": r.timed_out,
                "stalled": r.stalled,
                "progress": r.progress,
                "notes": r.notes,
                "command": r.command,
            }
            for r in results
        ],
    }
    (out_dir / "REPORT.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8"
    )

    print("\n" + "=" * 78)
    print("汇总")
    for r in results:
        mark = "✅" if r.ok else "❌"
        extra = " [卡死]" if r.stalled else (" [超时]" if r.timed_out else "")
        print(f"  {mark} {r.name:<26} exit={r.exit_code:<4} {r.duration_s:>7.0f}s  尝试 {r.attempts} 次{extra}")
    print(f"  总计 {total / 60:.1f} 分钟 | 累计卡死 {stalls} 次 | 报告: {out_dir / 'REPORT.json'}")
    print("=" * 78)
    # 终态标记：无人值守时外部只看 DONE.json 在不在、rc 是多少（活锁此时已释放）
    (out_dir / DONE_FILE).write_text(
        json.dumps(
            {
                "rc": rc,
                "at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "stages_total": len(results),
                "stages_ok": sum(1 for r in results if r.ok),
                "stalls": stalls,
                "duration_s": round(total, 1),
            },
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        ),
        encoding="utf-8",
    )
    return rc


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n用户中断", file=sys.stderr)
        sys.exit(130)
