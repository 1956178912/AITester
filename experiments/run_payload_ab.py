"""H1 载荷等价实验 —— 三臂驱动脚本骨架（**不真跑 LLM**）。

配套预注册：[docs/design/payload_equivalence_prereg.md](../docs/design/payload_equivalence_prereg.md)

设计约束（来自 task-7）
----------------------
1. **本脚本不修改** ``experiments/run_benchmark.py``，只经 ``subprocess`` 调用既有 runner；
2. 负责构造三臂的 env 组合、落盘到**独立目录**、生成 ``env_snapshot`` 校验与 ``SHA256SUMS``；
3. ``--dry-run`` 打印将要执行的命令与环境变量，**不执行**——打印出的 env 是**将被注入的完整集合**；
4. **默认不执行任何 LLM 调用**：不加 ``--confirm-budget`` 时脚本只做 dry-run 级别的检查后退出。

臂设计（预注册 §2.1 / 附录 B）
------------------------------
| 臂 | GENERATOR_PAYLOAD | 编排 | 基线 | 角色 |
|---|---|---|---|---|
| ``p_df_parity__o_logic`` | ``df_parity`` | logic 档多智能体 | ``aitester`` | H1 主检验臂（①） |
| ``p_df_parity__o_mono``  | ``df_parity`` | 单体流水线 | ``plain_llm_df`` | 同载荷编排对照（②） |
| ``p_full__o_logic``      | ``full``      | logic 档多智能体 | ``aitester`` | H1 对照臂（③） |

REF（外部参照 ``df_stored``）**不重跑**，直接引用存量工件（预注册 §3.4）。

runner 选择
-----------
默认 ``--runner main_batch`` → ``experiments/run_main_batch.py``。**理由**：
E4 的 −28pp 基准即经此入口产生（批次日志首行 "R4 主批次：dataset=quixbugs task_count=50 seed=42"），
它额外提供 ``--allow-dirty`` / ``--dirty-reason``（写入 ``provenance.dirty_reason``）与 R14 统计协议——
单变量比较要求三臂代码态可审计。``run_main_batch.py`` 本身是 ``run_benchmark.run_benchmark()``
的薄壳包装（其模块 docstring 自述），故"H1 经 run_benchmark 执行"依然成立。
``--runner benchmark`` 可直接调 ``experiments/run_benchmark.py``；``--dry-run`` 会**同时**打印该等价命令。

用法
----
    # 1) 先看将要执行什么（不执行）
    .venv/bin/python experiments/run_payload_ab.py --dry-run

    # 2) 真跑（需显式确认预算；本任务未授权，勿运行）
    .venv/bin/python experiments/run_payload_ab.py --confirm-budget \\
        --out-dir experiments/results/e3_h1_payload

    # 3) 只校验已落盘工件的 env_snapshot 一致性
    .venv/bin/python experiments/run_payload_ab.py --verify-only \\
        --out-dir experiments/results/e3_h1_payload
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNNER = "main_batch"
DEFAULT_OUT_DIR = "experiments/results/e3_h1_payload"
DEFAULT_SEED = 42
DEFAULT_TASK_COUNT = 50

#: H1 外部参照（**不重跑**）：E4 FIXED harness 的 df 臂存量工件（预注册 §3.4）。
REF_ARM = {
    "name": "df_stored",
    "path": "experiments/results/e6_a1_batches/e4_quixbugs_FIXED_harness/plain_llm_df.json",
    "sha256": "d23402fb03602e3b547a51824cda76e6e8b333936a636649dd8734072e6db3ac",
    "expected_detection_gold": 31,
    "gold_denominator": 41,
}

#: 预注册附录 B 的臂定义（顺序 = 执行顺序）。
ARMS: tuple[dict[str, Any], ...] = (
    {
        "name": "p_df_parity__o_logic",
        "payload": "df_parity",
        "baselines": "aitester",
        "role": "H1 主检验臂（①）",
    },
    {
        "name": "p_df_parity__o_mono",
        "payload": "df_parity",
        "baselines": "plain_llm_df",
        "role": "同载荷编排对照（②）",
    },
    {
        "name": "p_full__o_logic",
        "payload": "full",
        "baselines": "aitester",
        "role": "H1 对照臂（③）",
    },
)

#: 三臂共用的常量控制（预注册 §2.3）。**任何两台臂之间除 GENERATOR_PAYLOAD 外不得有差异。**
COMMON_ENV: dict[str, str] = {
    "AITESTER_PROFILE": "logic",
    "TEMPERATURE": "0.0",
    "LLM_THINKING_MODE": "disabled",
    "AITESTER_LLM_CACHE": "0",  # cold cache（硬性，预注册 §2.3）
    "AITESTER_CACHE_NAMESPACE": "e3_h1_seed42",
    "MAX_ITERATIONS": "3",
    "EXECUTION_TIMEOUT": "30",
    "DETECTION_SPECIFICITY_GATE_ENABLE": "true",
    "RED_REGRESSION_GATE_ENABLE": "true",
    "DETECTION_FIRST_ENABLE": "true",
    "BENCHMARK_PARALLELISM": "4",
    "ENABLE_RAG": "false",
}

#: 允许在三臂之间**不同**的 env 键（白名单，只有自变量）。
ALLOWED_ARM_DIFF_KEYS = frozenset({"GENERATOR_PAYLOAD"})

#: G0-b：必须登记进 `_env_snapshot_keys` 才能从工件证明干预生效。
REQUIRED_SNAPSHOT_KEYS = ("GENERATOR_PAYLOAD", "ORACLE_CONTEXT_TIER")

_RUNNER_SCRIPTS = {
    "main_batch": "experiments/run_main_batch.py",
    "benchmark": "experiments/run_benchmark.py",
}


@dataclass
class Blocker:
    """阻断项：不满足则 H1 不得启动（预注册 §0 / 附录 C）。"""

    gate: str
    detail: str
    ok: bool = False

    def __str__(self) -> str:
        mark = "✅" if self.ok else "⛔"
        return f"{mark} [{self.gate}] {self.detail}"


@dataclass
class ArmResult:
    name: str
    out_dir: Path
    snapshot_ok: bool
    problems: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# 前置门检查（只读：解析 AST / 文本，不执行任何实验）
# --------------------------------------------------------------------------- #
def _snapshot_keys(benchmark_py: Path) -> list[str] | None:
    """用 AST 取 ``_env_snapshot_keys`` 的字面量列表（只读，不做文本正则猜测）。"""
    if not benchmark_py.is_file():
        return None
    tree = ast.parse(benchmark_py.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if "_env_snapshot_keys" not in targets:
            continue
        if isinstance(node.value, ast.List):
            return [e.value for e in node.value.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
    return None


def _grep_consumers(needle: str, roots: tuple[str, ...] = ("src",)) -> list[str]:
    """``src/`` 下出现该环境变量名的文件（判断干预是否已落地）。"""
    hits: list[str] = []
    for root in roots:
        base = PROJECT_ROOT / root
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            try:
                if needle in path.read_text(encoding="utf-8"):
                    hits.append(str(path.relative_to(PROJECT_ROOT)))
            except OSError:  # pragma: no cover - 不可读文件跳过
                continue
    return sorted(hits)


def check_preconditions() -> list[Blocker]:
    """预注册 §0 / 附录 C 的前置门（全部只读）。"""
    blockers: list[Blocker] = []
    benchmark_py = PROJECT_ROOT / "experiments" / "run_benchmark.py"
    keys = _snapshot_keys(benchmark_py)

    # G0-b：干预开关必须入 provenance 快照。
    if keys is None:
        blockers.append(Blocker("G0-b", "无法从 run_benchmark.py 解析 _env_snapshot_keys（AST 未命中）"))
    else:
        missing = [k for k in REQUIRED_SNAPSHOT_KEYS if k not in keys]
        blockers.append(
            Blocker(
                "G0-b",
                (
                    f"`_env_snapshot_keys` 缺 {missing}（当前共 {len(keys)} 键）——"
                    "缺口未补则干预**不可从工件证明**（A1/D3/RT1 同类事故）"
                    if missing
                    else f"必需快照键齐备（当前共 {len(keys)} 键）"
                ),
                ok=not missing,
            )
        )

    # G0-c：环境开关 CI 门禁的 --select 口径——`_ENABLE$` 不覆盖非 _ENABLE 形态的载荷开关。
    gate_py = PROJECT_ROOT / "scripts" / "gates" / "check_env_snapshot_keys.py"
    if gate_py.is_file():
        text = gate_py.read_text(encoding="utf-8")
        m = re.search(r"^DEFAULT_SELECT\s*=\s*r?[\"'](.+?)[\"']", text, re.M)
        pattern = m.group(1) if m else None
        allow_py = PROJECT_ROOT / "review_2026" / "E2_env_snapshot_allowlist.txt"
        allowed = allow_py.read_text(encoding="utf-8").split() if allow_py.is_file() else []
        uncovered: list[str] = []
        for key in REQUIRED_SNAPSHOT_KEYS:
            selected = bool(pattern) and re.search(pattern, key) is not None
            if not selected and key not in allowed:
                uncovered.append(key)
        blockers.append(
            Blocker(
                "G0-c",
                (
                    f"check_env_snapshot_keys.py 的 DEFAULT_SELECT={pattern!r} 不匹配 {uncovered} "
                    f"且不在白名单 ⇒ CI 门禁不覆盖载荷开关（须加白名单或扩正则）"
                    if uncovered
                    else f"CI 门禁覆盖载荷开关（DEFAULT_SELECT={pattern!r}，白名单 {len(allowed)} 键）"
                ),
                ok=not uncovered,
            )
        )
    else:
        blockers.append(Blocker("G0-c", "scripts/gates/check_env_snapshot_keys.py 不存在，无法核验"))

    # P-1：干预本身必须先落地（src 中必须有消费者）。
    consumers = _grep_consumers("GENERATOR_PAYLOAD")
    blockers.append(
        Blocker(
            "P-1",
            (
                "src/ 下**无** GENERATOR_PAYLOAD 消费者 ⇒ 载荷干预未落地，"
                "现在跑三臂等于跑同一个 full 载荷（A1 首跑同类假阴性）"
                if not consumers
                else f"GENERATOR_PAYLOAD 消费者：{consumers}"
            ),
            ok=bool(consumers),
        )
    )

    # G0-a：围栏残留（P0-2）——检查最近一次批次工件是否仍有 `python\n` 残留。
    probe = PROJECT_ROOT / "experiments/results/e6_a1_batches/e4_quixbugs_FIXED_harness/aitester.json"
    if probe.is_file():
        try:
            details = json.loads(probe.read_text(encoding="utf-8"))["results"]
            details = details[next(iter(details))]["details"]
            n = sum(1 for r in details if (r.get("patch") or "").lstrip().startswith("python"))
            blockers.append(
                Blocker(
                    "G0-a",
                    (
                        f"参考批次 {n}/{len(details)} 行 patch 仍以 'python\\n' 开头（围栏残留未回灌）"
                        if n
                        else "参考批次无围栏残留"
                    ),
                    ok=(n == 0),
                )
            )
        except (OSError, KeyError, StopIteration, json.JSONDecodeError) as exc:
            blockers.append(Blocker("G0-a", f"无法读取参考批次工件：{exc}"))
    return blockers


# --------------------------------------------------------------------------- #
# 命令构造
# --------------------------------------------------------------------------- #
def build_env(arm: dict[str, Any]) -> dict[str, str]:
    """该臂的**完整**目标 env（含继承的 os.environ，便于审阅）。"""
    env = dict(os.environ)
    env.update(COMMON_ENV)
    env["GENERATOR_PAYLOAD"] = str(arm["payload"])
    return env


def build_argv(arm: dict[str, Any], runner: str, out_dir: Path, seed: int, task_count: int) -> list[str]:
    """构造该臂的 runner argv。"""
    script = _RUNNER_SCRIPTS[runner]
    argv = [
        sys.executable,
        script,
        "--dataset",
        "quixbugs",
        "--task-count",
        str(task_count),
        "--seed",
        str(seed),
        "--baselines",
        str(arm["baselines"]),
        "--output-dir",
        str(out_dir),
    ]
    if runner == "main_batch":
        argv += [
            "--skip-stats",
            "--allow-dirty",
            "--dirty-reason",
            f"E3 H1 payload-equivalence arm={arm['name']}",
        ]
    return argv


def build_benchmark_equivalent(arm: dict[str, Any], out_dir: Path, seed: int, task_count: int) -> list[str]:
    """``--runner benchmark`` 的等价命令（供 dry-run 并列展示）。"""
    return build_argv(arm, "benchmark", out_dir, seed, task_count)


def _render_env(env: dict[str, str], keys: list[str]) -> list[str]:
    return [f"    {k}={env.get(k, '')!r}" for k in keys]


# --------------------------------------------------------------------------- #
# 执行与校验
# --------------------------------------------------------------------------- #
def run_arm(arm: dict[str, Any], runner: str, out_dir: Path, seed: int, task_count: int) -> int:
    env = build_env(arm)
    argv = build_argv(arm, runner, out_dir, seed, task_count)
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[run] {arm['name']} → {out_dir}")
    proc = subprocess.run(argv, cwd=str(PROJECT_ROOT), env=env, check=False)
    return proc.returncode


def _find_batch_json(arm_dir: Path) -> Path | None:
    cands = sorted(p for p in arm_dir.glob("*.json") if not p.name.endswith(("summary.json", "SHA256SUMS")))
    return cands[-1] if cands else None


def verify_env_snapshot(out_dir: Path, arms: list[dict[str, Any]]) -> list[ArmResult]:
    """逐臂核对 ``provenance.env_snapshot``，并做**跨臂逐键 diff**。

    预注册 §6.2 三条断言：
    1. ``GENERATOR_PAYLOAD`` == 该臂声明值（缺失/串值均判失败）；
    2. 跨臂**键集合**一致（防某臂漏登记开关）；
    3. 跨臂**逐键取值**一致（``ALLOWED_ARM_DIFF_KEYS`` 白名单除外）。
    """
    results: list[ArmResult] = []
    snapshots: dict[str, dict[str, Any]] = {}
    declared: dict[str, str] = {}

    for arm in arms:
        name = str(arm["name"])
        declared[name] = str(arm["payload"])
        arm_dir = out_dir / name
        problems: list[str] = []
        batch = _find_batch_json(arm_dir)
        if batch is None:
            results.append(ArmResult(name, arm_dir, snapshot_ok=False, problems=["未找到批次 JSON"]))
            continue
        try:
            data = json.loads(batch.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            results.append(ArmResult(name, arm_dir, snapshot_ok=False, problems=[f"批次 JSON 不可解析：{exc}"]))
            continue
        snap = (data.get("provenance") or {}).get("env_snapshot") or {}
        if not snap:
            problems.append("provenance.env_snapshot 缺失（无法证明干预生效）")
        else:
            got = snap.get("GENERATOR_PAYLOAD")
            if got != declared[name]:
                problems.append(f"GENERATOR_PAYLOAD={got!r} ≠ 声明值 {declared[name]!r}（干预未生效或未登记）")
        snapshots[name] = snap
        results.append(ArmResult(name, arm_dir, snapshot_ok=not problems, problems=problems))

    # 跨臂 diff（键集合 + 逐键取值）
    if len(snapshots) >= 2:
        names = sorted(snapshots)
        all_keys: set[str] = set()
        for n in names:
            all_keys |= set(snapshots[n])
        for key in sorted(all_keys - ALLOWED_ARM_DIFF_KEYS):
            present = {n: (key in snapshots[n]) for n in names}
            if len(set(present.values())) > 1:
                msg = f"跨臂键集合不一致：{key} 出现于 {[n for n in names if present[n]]}"
            else:
                vals = {n: snapshots[n].get(key) for n in names}
                if len(set(map(repr, vals.values()))) == 1:
                    continue
                msg = f"跨臂 env 不一致：{key} = {vals}"
            for r in results:
                r.problems.append(msg)
                r.snapshot_ok = False
    return results


def write_sha256sums(root: Path) -> Path:
    """递归生成 SHA256SUMS（预注册 §6.1）。"""
    lines: list[str] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file() and p.name != "SHA256SUMS"):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.relative_to(root)}")
    out = root / "SHA256SUMS"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


# --------------------------------------------------------------------------- #
# dry-run 渲染
# --------------------------------------------------------------------------- #
def render_dry_run(
    arms: list[dict[str, Any]],
    runner: str,
    out_dir: Path,
    seed: int,
    task_count: int,
    blockers: list[Blocker],
) -> str:
    lines: list[str] = []
    lines.append("=" * 78)
    lines.append("H1 载荷等价实验 —— DRY RUN（不会执行任何命令，不会调用任何 LLM）")
    lines.append("=" * 78)
    lines.append(f"runner      : {runner} → {_RUNNER_SCRIPTS[runner]}")
    lines.append(f"out-dir     : {out_dir}")
    lines.append(f"dataset     : quixbugs  task-count={task_count}  seed={seed}")
    lines.append(f"三臂        : {[a['name'] for a in arms]}")
    lines.append(f"外部参照REF : {REF_ARM['name']} = {REF_ARM['path']}（存量，不重跑）")
    lines.append("")

    lines.append("-" * 78)
    lines.append("前置门（预注册 §0 / 附录 C）")
    lines.append("-" * 78)
    lines.extend(str(b) for b in blockers)
    blocked = [b for b in blockers if not b.ok]
    if blocked:
        lines.append("")
        lines.append(f"⛔ {len(blocked)} 项前置门未通过 —— 真跑前必须补齐（见预注册 §2.5 P-1 / §0 G0）。")
    lines.append("")

    env_keys = ["GENERATOR_PAYLOAD", *COMMON_ENV.keys()]
    for arm in arms:
        arm_out = out_dir / arm["name"]
        lines.append("-" * 78)
        lines.append(f"臂 {arm['name']}   （{arm['role']}）")
        lines.append("-" * 78)
        lines.append("  注入的环境变量（COMMON_ENV + 自变量）：")
        lines.extend(_render_env(build_env(arm), env_keys))
        lines.append("")
        lines.append("  命令：")
        lines.append("    " + " ".join(build_argv(arm, runner, arm_out, seed, task_count)))
        if runner != "benchmark":
            lines.append("  等价的直接 runner 命令（--runner benchmark）：")
            lines.append("    " + " ".join(build_benchmark_equivalent(arm, arm_out, seed, task_count)))
        lines.append("")

    lines.append("-" * 78)
    lines.append("单变量纪律自检（预注册 §2.3）")
    lines.append("-" * 78)
    base = arms[0]
    for arm in arms[1:]:
        diff = {k for k in COMMON_ENV if COMMON_ENV[k] != COMMON_ENV.get(k)}
        diff |= {"GENERATOR_PAYLOAD"} if arm["payload"] != base["payload"] else set()
        extra = diff - ALLOWED_ARM_DIFF_KEYS
        lines.append(
            f"  {base['name']} vs {arm['name']}: 允许差异={sorted(diff & ALLOWED_ARM_DIFF_KEYS)} "
            f"违规差异={sorted(extra) if extra else '无'}"
        )
    lines.append("")
    lines.append("-" * 78)
    lines.append("落盘与校验计划")
    lines.append("-" * 78)
    lines.append(f"  1) 每臂输出 → {out_dir}/<arm>/")
    lines.append("  2) 逐臂核 provenance.env_snapshot['GENERATOR_PAYLOAD'] == 该臂声明值")
    lines.append("  3) 跨臂逐键 diff（除 GENERATOR_PAYLOAD 外必须完全相同）")
    lines.append(f"  4) 生成 {out_dir}/SHA256SUMS（递归覆盖全部工件）")
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 入口
# --------------------------------------------------------------------------- #
def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="H1 载荷等价实验三臂驱动骨架（默认 dry-run）")
    ap.add_argument("--dry-run", action="store_true", help="只打印将执行的命令与 env（默认行为）")
    ap.add_argument("--confirm-budget", action="store_true", help="显式确认已获 LLM 预算授权（否则拒绝执行）")
    ap.add_argument("--verify-only", action="store_true", help="只校验已落盘工件的 env_snapshot 一致性")
    ap.add_argument("--runner", choices=sorted(_RUNNER_SCRIPTS), default=DEFAULT_RUNNER, help="runner 入口")
    ap.add_argument("--out-dir", default=DEFAULT_OUT_DIR, help=f"独立落盘目录（默认 {DEFAULT_OUT_DIR}）")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED, help="随机种子（默认 42）")
    ap.add_argument("--task-count", type=int, default=DEFAULT_TASK_COUNT, help="任务数（默认 50，终点 41）")
    ap.add_argument("--arms", nargs="+", default=None, help="只跑指定臂（默认预注册三臂全部）")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = PROJECT_ROOT / out_dir
    arms = [a for a in ARMS if args.arms is None or a["name"] in args.arms]
    if not arms:
        print(f"[h1] --arms 未匹配任何预注册臂；可选：{[a['name'] for a in ARMS]}", file=sys.stderr)
        return 2

    blockers = check_preconditions()

    if args.verify_only:
        results = verify_env_snapshot(out_dir, arms)
        bad = 0
        for r in results:
            status = "✅" if r.snapshot_ok else "⛔"
            print(f"{status} {r.name}: {r.out_dir}")
            for p in r.problems:
                print(f"     - {p}")
            bad += 0 if r.snapshot_ok else 1
        return 1 if bad else 0

    # 默认即 dry-run（--dry-run 显式给出时亦同）。
    if args.dry_run or not args.confirm_budget:
        print(render_dry_run(arms, args.runner, out_dir, args.seed, args.task_count, blockers))
        if not args.confirm_budget:
            print("提示：未传 --confirm-budget ⇒ 只做 dry-run，未执行任何实验（安全默认）。")
        return 0

    # ---- 以下路径才会真正 subprocess 调 runner（会消耗 LLM 预算）----
    blocked = [b for b in blockers if not b.ok]
    if blocked:
        print("⛔ 前置门未通过，拒绝执行：", file=sys.stderr)
        for b in blocked:
            print(f"   {b}", file=sys.stderr)
        return 3

    failed: list[str] = []
    for arm in arms:
        rc = run_arm(arm, args.runner, out_dir / arm["name"], args.seed, args.task_count)
        if rc != 0:
            failed.append(f"{arm['name']}(rc={rc})")
            print(f"⛔ 臂 {arm['name']} 以 rc={rc} 结束，按预注册 §5.2 停止规则中止后续臂", file=sys.stderr)
            break

    sums = write_sha256sums(out_dir)
    print(f"[h1] SHA256SUMS → {sums}")

    results = verify_env_snapshot(out_dir, arms)
    for r in results:
        print(("✅" if r.snapshot_ok else "⛔") + f" env_snapshot {r.name}")
        for p in r.problems:
            print(f"     - {p}")
    if failed or any(not r.snapshot_ok for r in results):
        return 1
    print("[h1] 三臂完成，env_snapshot 校验通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
