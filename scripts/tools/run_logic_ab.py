#!/usr/bin/env python
"""逻辑通道 A/B 单进程执行器（2026-10-10 独立审查 · 第二次修订）。

为什么不用 shell 脚本：
    首版 shell 编排器在两次启动之间**未做互斥**——第一次启动的实例在被
    kill 后并未真正退出，与第二次启动的实例**并发跑了同一实验**，
    导致 control/treat 两臂的 trace 文件互相污染（单变量隔离被破坏，
    结果不可用，已整体丢弃）。教训：跑批编排器本身必须**单实例自锁**，
    不能依赖操作者记得先杀干净。

本执行器的硬约束（防止上述事故重演）：
    1. **PID 锁文件**：启动即独占创建 `.run.lock`（O_EXCL），已有活动实例即拒绝；
    2. **单进程内顺序执行**双臂**：无 shell 后台、无并行脚本实例；
    3. **每臂独立输出目录**（含 run_id）：工件绝不混淆；
    4. **每臂硬墙钟上限**：超时即 killpg 整树（防变异层挂死无限占用）；
    5. **收尾自检**：核对数据集落点、开关快照、两臂 det_measured 分母一致。

用法：
    python scripts/tools/run_logic_ab.py --mode smoke   # 3 任务 × 2 臂
    python scripts/tools/run_logic_ab.py --mode full    # 50 任务 × 2 臂
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = str(ROOT / ".venv" / "bin" / "python")
LOCK = ROOT / "experiments" / "results" / ".logic_ab.lock"


def _live_benchmark_pids() -> list[int]:
    """扫描仍存活的 `experiments/run_benchmark.py` 进程（含**孤儿**）。

    为什么需要它（2026-10-10 事故的直接教训）：
        首版只用 PID 锁文件做互斥。但 kill 掉编排器时，其以
        `start_new_session=True` 启动的 run_benchmark **子进程会脱离进程组
        存活下来**（实测：kill 编排器后 run_benchmark 仍继续跑了数分钟），
        而锁文件随编排器一起消失 → **新实例被放行** → 同一实验出现两个
        并发写入者（两臂 trace 互相污染，整个结果作废）。
        故互斥必须**同时**检查"是否已有跑批进程活着"，而不只是查锁文件。
    """
    try:
        out = subprocess.run(
            ["pgrep", "-f", "experiments/run_benchmark.py"],
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    pids = []
    for tok in out.split():
        try:
            pids.append(int(tok))
        except ValueError:
            continue
    return pids


def _acquire_lock() -> None:
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    # 第一道：孤儿跑批进程检查（锁文件会随编排器消失，这道不会）
    stale = [p for p in _live_benchmark_pids() if p != os.getpid()]
    if stale:
        print(
            f"[FAIL] 检测到仍存活的跑批进程 {stale}（可能是上次编排器被 kill 后"
            f"脱离进程组的孤儿）——拒绝并发启动。\n"
            f"       请先清理：kill -9 {' '.join(map(str, stale))}",
            file=sys.stderr,
        )
        sys.exit(3)
    # 第二道：PID 锁文件
    if LOCK.exists():
        try:
            old = int(LOCK.read_text().strip())
            os.kill(old, 0)  # 存活探测（信号 0 不投递）
        except (ValueError, ProcessLookupError, PermissionError):
            print(f"[WARN] 发现陈旧锁文件 {LOCK}，已清除")
            LOCK.unlink(missing_ok=True)
        else:
            print(
                f"[FAIL] 已有活动实例（PID {old}）持有 {LOCK}——拒绝并发启动。\n"
                f"       若确认其已死，删除该文件后重试：rm {LOCK}",
                file=sys.stderr,
            )
            sys.exit(3)
    fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
    print(f"[OK] 已获取独占锁 {LOCK}（PID {os.getpid()}）")


def _build_filtered_dataset(exclude: set[str], workdir: Path) -> Path | None:
    """构造一份**排除指定任务**的 QuixBugs 副本，返回其路径（无排除则返回 None）。

    为什么需要它（2026-10-10 实跑教训）：
        QuixBugs 有 4 个任务的**缺陷实现永不终止**（`bitcount` 的 `n ^= n - 1`、
        `find_first_in_sorted` / `sqrt` / `wrap`，见 BASELINE.yaml 的
        detection_none_cause 登记）。执行器跑 LLM 生成测试时被这类任务拖死：
        3 任务冒烟在 `bitcount` 上卡死 10+ 分钟（主进程 %CPU 0.0、持有 3 个 PIPE、
        无存活子进程），导致批次 JSON 从不写出。
        根因是执行器链路仍用裸 `subprocess.run(timeout=)`——超时只 kill 直接子进程，
        被测代码的子进程继续持有管道写端 → `communicate()` 永久阻塞。
        **注意：这 4 个任务本来就无法给出 detection**（M1 三段判定第 1 段
        "buggy 上变红"无从判定，fail-closed 记 None），故排除它们**不损失主终点信息**。

    实现：只复制符号链接/文件树中除被排除任务外的 .py 与 json_testcases，
    指向**临时目录**（不动仓库内 data/quixbugs，也不改任何代码）。
    """
    src = Path(os.environ.get("AITESTER_QUIXBUGS_DATA", str(ROOT / "data" / "quixbugs")))
    if not (src / "python_programs").is_dir():
        return None
    dst = workdir / "quixbugs_filtered"
    if dst.exists():
        return dst
    for sub in ("python_programs", "correct_python_programs", "python_testcases", "json_testcases"):
        s = src / sub
        if not s.is_dir():
            continue
        d = dst / sub
        d.mkdir(parents=True, exist_ok=True)
        for f in s.iterdir():
            if not f.is_file():
                continue
            stem = f.stem
            # 按任务名排除（test 驱动的任务名形如 <name>_test，同样按前缀排除）
            if stem in exclude or stem.replace("_test", "") in exclude:
                continue
            (d / f.name).symlink_to(f)  # 软链避免复制大目录
    return dst


def _run_arm(
    arm: str,
    outdir: Path,
    limit: int,
    envs: dict[str, str],
    timeout: float,
    mutation: bool,
    data_dir: str | None,
) -> int:
    outdir.mkdir(parents=True, exist_ok=True)
    log = outdir / "run.log"
    env = {
        **os.environ,
        "AITESTER_PROFILE": "logic",
        "TEMPERATURE": "0",
        "LLM_THINKING_MODE": "disabled",
        "AITESTER_LLM_CACHE": "0",  # 冷缓存：臂间零复用
        "BENCHMARK_PARALLELISM": "4",
        "MAX_ITERATIONS": "3",
        # 2026-10-10 第二次修订：逻辑档（_PROFILE_PRESETS["logic"]）会打开
        # ENABLE_MUTATION_SCORING=true，而变异层是**实测挂死源**——control 臂
        # 50/50 任务完成后卡在批后阶段 35 分钟（%CPU 0.3、无变异子进程存活），
        # 批次 JSON 始终未写出。虽然变异子进程的 killpg 缺陷已修
        # （mutation_testing.py 改建在 run_with_timeout 之上），但本 A/B 的
        # **主终点是 detection_rate**，变异得分是次要指标；为了让跑批可靠收尾，
        # 此轮显式关闭变异评分（config.py:437 读 os.getenv，显式值优先于档位预设）。
        # 代价：本批无 mutation_score，不作为本次结论依据——已在报告中披露。
        "ENABLE_MUTATION_SCORING": "true" if mutation else "false",
        # 2026-10-10 实跑修复：开启 pytest 插件级超时。被测缺陷实现若死循环
        # （实测 `to_base` / `bitcount` 等），外层 `subprocess.run(timeout=30)`
        # 到点只 kill 直接子进程，pytest 孙进程继续持有管道写端 →
        # `communicate()` 永久阻塞 → 整臂挂死、批次 JSON 从不写出。
        # 插件级超时（20s < 外层 30s）让 pytest **正常退出并返回非零 rc**，
        # 从而避开管道死锁；命令层改动，subprocess 返回契约不变。
        "PYTEST_TIMEOUT_ENABLE": "true",
        "PYTEST_TIMEOUT_SECONDS": "20",
        "AITESTER_QUIXBUGS_DATA": data_dir or os.environ.get("AITESTER_QUIXBUGS_DATA", str(ROOT / "data" / "quixbugs")),
    }
    env.update(envs)
    cmd = [
        PY,
        "experiments/run_benchmark.py",
        "--dataset",
        "quixbugs",
        "--task-limit",
        str(limit),
        "--baselines",
        "aitester",
        "--output-dir",
        str(outdir),
        "--parallel",
        "4",
        "--seed",
        "42",
        "--verbose",
    ]
    print(f"\n──────── 臂 {arm}: {envs} ────────")
    print(f"  输出: {outdir}")
    t0 = time.monotonic()
    with open(log, "wb") as logf:
        proc = subprocess.Popen(
            cmd, stdout=logf, stderr=subprocess.STDOUT, cwd=str(ROOT), env=env, start_new_session=True
        )
        try:
            rc = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            print(f"  [WARN] 触及上限 {timeout:.0f}s → killpg 整树", file=sys.stderr)
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                time.sleep(5)
                if proc.poll() is None:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
            rc = 124
    print(f"  exit={rc} 耗时={time.monotonic() - t0:.1f}s · 日志 {log}")
    return rc


def _verify_multi(outbase: Path, switches: list[str], configs: dict[str, dict[str, str]]) -> bool:
    """多臂核验（支持 2×2 因子）：工件齐备 + 每个开关入快照且与臂设定相符 + 分母可比。"""
    ok = True
    summary: dict[str, dict] = {}
    for arm, want_env in configs.items():
        hits = sorted(glob.glob(str(outbase / arm / "benchmark_quixbugs_*.json")))
        if not hits:
            got = sorted(Path(x).name for x in glob.glob(str(outbase / arm / "benchmark_*.json")))
            print(f"[FAIL] {arm}: 无 benchmark_quixbugs_*.json（实得 {got}）——数据集回退？")
            ok = False
            continue
        d = json.loads(Path(hits[-1]).read_text())
        rows = d["results"]["aitester"]["details"]
        env = d.get("provenance", {}).get("env_snapshot") or {}
        det = [r.get("detection_rate") for r in rows if r.get("detection_rate") is not None]
        rep = [r.get("repair_rate") for r in rows if r.get("repair_rate") is not None]
        summary[arm] = {
            "n": len(rows),
            "det": f"{sum(1 for x in det if x)}/{len(det)}",
            "rep": f"{sum(1 for x in rep if x)}/{len(rep)}",
            "written": sum(1 for r in rows if r.get("patch_plausible") == 1),
            "injected": sum(1 for r in rows if r.get("spec_oracle_injected") is True),
            "over_red": sum(1 for r in rows if r.get("specificity_gate_verdict") == "over_red"),
            "switch": {k: env.get(k) for k in switches},
        }
        # 干预生效性：每个开关都必须入快照且等于该臂设定值（A1 假阴性防复发）
        for k, v in want_env.items():
            if str(env.get(k)).lower() != str(v).lower():
                print(f"[FAIL] {arm}: 快照 {k}={env.get(k)!r} ≠ 臂设定 {v!r}——干预生效性不可证明")
                ok = False
        if d.get("dataset") != "quixbugs":
            print(f"[FAIL] {arm}: dataset={d.get('dataset')!r}")
            ok = False
    print("\n=== 多臂核验 ===")
    for arm, st in summary.items():
        print(f"  [{arm}] env={configs[arm]} → {st}")
    dets = {st["det"] for st in summary.values()}
    if len(dets) > 1 and len({st["det"].split("/")[1] for st in summary.values()}) > 1:
        print("[WARN] 各臂 det_measured 分母不一致 → 配对检验须按共同任务集重算")
    return ok


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="逻辑通道 A/B（单进程、自锁、顺序双臂）")
    ap.add_argument("--mode", choices=("smoke", "full"), default="smoke")
    ap.add_argument("--arm-timeout", type=float, default=2700.0, help="每臂墙钟上限（秒）")
    ap.add_argument(
        "--arms",
        default="",
        help="要跑的臂（逗号分隔；默认空=跑 --config/默认的全部臂）。用于断点续跑：--arms treat",
    )
    ap.add_argument("--mutation", action="store_true", help="开启变异评分（默认关：它是实测挂死源且非本 A/B 主终点）")
    ap.add_argument(
        "--switch",
        default="SPEC_ORACLE_EXEC_ENABLE",
        help="单变量开关名（默认 SPEC_ORACLE_EXEC_ENABLE = 逻辑通道 A/B）",
    )
    ap.add_argument("--control-value", default="false", help="control 臂的开关取值")
    ap.add_argument("--treat-value", default="true", help="treat 臂的开关取值")
    ap.add_argument(
        "--config",
        default="",
        help='臂配置 JSON 文件：{"臂名": {"开关": "值"}}；用于 2×2 因子等多元设计',
    )
    ap.add_argument(
        "--exclude-tasks",
        default="bitcount,find_first_in_sorted,sqrt,wrap",
        help=(
            "排除的 QuixBugs 任务（逗号分隔）。默认排除 4 个**缺陷实现永不终止**的任务"
            "（BASELINE.yaml detection_none_cause 登记）——它们本就无法产出 detection，"
            "且会把执行器拖死。传空串表示不排除。"
        ),
    )
    args = ap.parse_args(argv)

    limit = 3 if args.mode == "smoke" else 50
    run_id = time.strftime("%Y%m%d_%H%M%S")
    outbase = ROOT / "experiments" / "results" / f"llm_logic_ab_{run_id}"

    _acquire_lock()
    try:
        qx = Path(os.environ.get("AITESTER_QUIXBUGS_DATA", str(ROOT / "data" / "quixbugs")))
        if not (qx / "python_programs").is_dir():
            print(f"[FAIL] QuixBugs 数据缺失: {qx}", file=sys.stderr)
            return 3
        print(f"[OK] QuixBugs 数据: {qx}（{len(list((qx / 'python_programs').glob('*.py')))} 个 .py）")
        print(f"[OK] 运行目录: {outbase} · mode={args.mode} · limit={limit} · 冷缓存")

        # 顺序执行，绝不并发
        want = {a.strip() for a in args.arms.split(",") if a.strip()}
        excludes = {t.strip() for t in (args.exclude_tasks or "").split(",") if t.strip()}
        data_dir: str | None = None
        if excludes:
            filtered = _build_filtered_dataset(excludes, outbase)
            if filtered is not None:
                data_dir = str(filtered)
                n_kept = len(list((filtered / "python_programs").glob("*.py")))
                print(
                    f"[OK] 过滤数据集就绪：排除 {sorted(excludes)} → 保留 {n_kept} 个程序"
                    f"（源 {ROOT / 'data' / 'quixbugs'} 未被修改；副本 {filtered}）"
                )
            else:
                print("[WARN] 无法构造过滤数据集，将使用原始数据（可能因不终止任务挂死）")
        # 臂配置：--config JSON 优先（支持 2×2 因子），否则用 --switch/--control-value/--treat-value
        if args.config:
            configs = json.loads(Path(args.config).read_text(encoding="utf-8"))
            # 值统一转字符串（env 只接受 str）
            configs = {k: {kk: str(vv) for kk, vv in v.items()} for k, v in configs.items()}
            switches = sorted({k for v in configs.values() for k in v})
        else:
            configs = {args.switch: {"control": args.control_value, "treat": args.treat_value}}
            configs = {"control": {args.switch: args.control_value}, "treat": {args.switch: args.treat_value}}
            switches = [args.switch]
        order = [a for a in ("control", "treat", "c1", "c2", "c3", "c4") if a in configs]
        order += [a for a in configs if a not in order]

        rcs: dict[str, int] = {}
        for arm in order:
            if want and arm not in want:
                print(f"[SKIP] 臂 {arm}（--arms 未包含）")
                continue
            rcs[arm] = _run_arm(arm, outbase / arm, limit, configs[arm], args.arm_timeout, args.mutation, data_dir)
        if any(rc != 0 for rc in rcs.values()):
            print(f"\n[WARN] 臂退出码 {rcs}")
        ok = _verify_multi(outbase, switches, configs)
        print(f"\n工件目录: {outbase}")
        return 0 if ok else 1
    finally:
        LOCK.unlink(missing_ok=True)
        print(f"[OK] 已释放锁 {LOCK}")


if __name__ == "__main__":
    sys.exit(main())
