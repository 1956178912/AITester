#!/usr/bin/env python3
"""SWE-bench Pro（python 子集）零 LLM 红→绿翻转判定器。

协议（与 SWE-bench Lite 阶段 2 同构，判定侧零 LLM——gold patch 由数据集自带）：
    worktree(base_commit) → git apply test_patch → 跑 selected_test_files
    （FAIL_TO_PASS 预期全红）→ git apply gold patch → 重跑（预期全绿）
    → 双满足 = PASS。

口径纪律：
- 判定面 = FAIL_TO_PASS 逐测试名（Pro 格式 `path::Class::method`，与 pytest
  `-rA` 摘要行的全路径 node id 精确匹配——比 Lite 的 sympy/django 特判简单）；
- **无观测 ≠ 0 也不 = 失败**：env/依赖失败单列 install_failed，不折进
  fix_not_green；双口径（全量/有判定）必须并列披露；
- 并发写防护（2026-10-30 教训）：--out 同名进程互覆丢数据 ⇒ 写 `--out.lock`
  pid 文件，第二个进程启动即拒绝（fail-closed），完成后清理；
- 嵌套 pytest 净环境：`nested_pytest_env`（宿主 pytest 配置/凭证不入子进程），
  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1（插件 autoload 收尾挂死同族根因）；
- repo 无官方环境规格（Pro 官方走 Docker）⇒ venv 复刻 best-effort：per-repo
  venv + `pip install -e .` 尝试，失败不阻断（逐记录披露），ImportError 类
  归 install_failed / collection_failed 单列。

用法：
    .venv/bin/python3 scripts/tools/swe_pro_judge.py \
        --dataset ~/.cache/aitester/swe_bench_pro/swe_bench_pro_instances.jsonl \
        --repos-dir ~/.cache/aitester/swe_bench_pro/repos \
        --out experiments/results/swe_pro_judge_20261030/PRO_JUDGE.json \
        [--resume] [--parallel 4] [--limit N] [--only-lang python]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from src.utils.atomic_io import atomic_write_json  # noqa: E402
from src.utils.process_utils import nested_pytest_env  # noqa: E402

_APPLY_RE = re.compile(r"error:|does not apply|patch does not apply", re.IGNORECASE)


def sh(
    args: list[str],
    cwd: str | None = None,
    timeout: int = 120,
    input_text: str | None = None,
    env_overrides: dict[str, str] | None = None,
) -> tuple[int, str]:
    """小型 git/命令执行（合并 stdout+stderr，超时返回 rc=124）。"""
    env = nested_pytest_env(**(env_overrides or {}))
    try:
        r = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            input=input_text,
            env=env,
        )
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "timeout"
    except Exception as exc:  # pragma: no cover - 防御
        return 1, f"{type(exc).__name__}: {exc}"


def ensure_repo_venv(repo_dir: Path, venv_dir: Path) -> tuple[str | None, str]:
    """per-repo venv：uv 建 + `pip install -e .` best-effort。

    返回 (错误, )：None = 可用（含 install 失败但 venv 本体可用的降级）。
    install 失败只记 note——部分任务不装也能跑（PYTHONPATH 直用）。
    """
    if (venv_dir / "bin" / "python").is_file():
        return None
    venv_dir.parent.mkdir(parents=True, exist_ok=True)
    rc, out = sh(["uv", "venv", "--python", sys.executable, str(venv_dir)], timeout=300)
    if rc != 0:
        return f"uv venv 失败: {out[-200:]}"
    venv_py = str(venv_dir / "bin" / "python")
    # pytest 是判定必需品：uv pip 装（企业代理下 venv 内置 pip 的 urllib 路径
    # 不可用——仓内既有结论；uv 走自己的传输栈可通），装失败/不可导入 = 判红
    # （诚实口径：没有 pytest 一切免谈，不降级跑空转）。
    sh(
        ["uv", "pip", "install", "--quiet", "--python", venv_py, "pytest", "pyyaml", "jinja2"],
        timeout=600,
    )
    irc, iout = sh([venv_py, "-c", "import pytest"], timeout=60)
    if irc != 0:
        return f"pytest 不可导入（uv pip 安装失败）: {iout[-150:]}"
    # repo 本体可编辑安装（best-effort：老依赖在 arm64 上可能编译失败，披露不阻断）
    setup_candidates = [q for q in ("setup.py", "pyproject.toml") if (repo_dir / q).is_file()]
    if setup_candidates:
        sh(
            ["uv", "pip", "install", "--quiet", "--python", venv_py, "-e", str(repo_dir), "--no-build-isolation"],
            timeout=900,
        )
    return None


def run_pytest_ftps(
    venv_py: str, worktree: Path, test_files: list[str], ftps: list[str], timeout: int
) -> tuple[dict[str, bool] | None, str]:
    """跑 selected test files，返回 {ftp: 是否 PASSED}（None = 无法解析输出）。

    env 必须覆盖 PYTHONPATH=worktree（Pro 无官方环境规格 ⇒ 不依赖 install -e，
    直接从 worktree import 被测包；nested_pytest_env 白名单保留的是**宿主**
    PYTHONPATH，须显式覆盖才指向 worktree——漏传曾致 No module named ansible）。
    包根按 repo 布局拼接：ansible 的包在 ``lib/`` 子目录（repo 全 history 布局
    恒定），openlibrary / qutebrowser 为顶层包。
    """
    pkg_roots = [str(worktree)]
    if (worktree / "lib" / "ansible").is_dir():
        pkg_roots.append(str(worktree / "lib"))
    _rc, out = sh(
        [venv_py, "-m", "pytest", *test_files, "-rA", "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=str(worktree),
        timeout=timeout,
        env_overrides={"PYTHONPATH": ":".join(pkg_roots), "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"},
    )
    passed: set[str] = set()
    for line in out.splitlines():
        s = line.strip()
        m = re.match(r"^(PASSED|FAILED|ERROR|SKIPPED)\s+(.+)$", s)
        if m and m.group(1) == "PASSED":
            passed.add(m.group(2).strip())
    # 甄别"测试真的跑了"与"执行失败"（假红防护）：pytest 有结果时输出必含
    # short test summary / passed|failed 统计 / no tests ran 三者之一；缺失 =
    # 收集或启动失败（如 No module named pytest）→ None，由调用方单列，
    # 不得把执行失败折进 baseline_red / fix_green 的判定。
    ran = ("short test summary info" in out) or ("no tests ran" in out) or re.search(r"\d+ passed", out)
    if not ran:
        return None, out[-300:]
    return {ftp: (ftp in passed) for ftp in ftps}, out[-400:]


def judge_instance(args: tuple[str, str, str, str]) -> dict:
    """单实例红绿翻转（顶层函数——ProcessPool 需要）。"""
    instance_id, dataset_path, repos_dir, venvs_dir = args
    rows = [json.loads(ln) for ln in Path(dataset_path).read_text(encoding="utf-8").splitlines() if ln.strip()]
    inst = next(x for x in rows if x["instance_id"] == instance_id)
    repo_slug: str = inst["repo"]
    repo_name = repo_slug.split("/")[-1]
    repo_dir = Path(repos_dir) / repo_name
    rec: dict = {"instance_id": instance_id, "repo": repo_slug, "version": str(inst.get("version", ""))}
    if not repo_dir.is_dir():
        rec["verdict"] = "repo_missing"
        return rec
    ftps: list[str] = (
        json.loads(inst["fail_to_pass"]) if isinstance(inst["fail_to_pass"], str) else list(inst["fail_to_pass"])
    )
    test_files: list[str] = (
        json.loads(inst["selected_test_files_to_run"])
        if isinstance(inst["selected_test_files_to_run"], str)
        else list(inst["selected_test_files_to_run"])
    )
    if not ftps:
        rec["verdict"] = "no_ftps"
        return rec
    venv_dir = Path(venvs_dir) / repo_name
    err = ensure_repo_venv(repo_dir, venv_dir)
    if err:
        rec["verdict"] = "env_build_failed"
        rec["error"] = err
        return rec
    venv_py = str(venv_dir / "bin" / "python")
    base: str = inst["base_commit"]
    mat = Path(tempfile.mkdtemp(prefix=f"swepro_{repo_name}_"))
    try:
        rc, out = sh(["git", "worktree", "add", "--detach", str(mat), base], cwd=str(repo_dir), timeout=300)
        if rc != 0:
            # commit 不可达（浅克隆/历史截断）——如实披露
            rec["verdict"] = "checkout_failed"
            rec["error"] = out[-200:]
            return rec
        # test_patch 进基线（Pro 的 before_repo_set_cmd 同序）
        rc, out = sh(
            ["git", "apply", "--whitespace=nowarn", "-"], cwd=str(mat), timeout=120, input_text=inst["test_patch"]
        )
        if rc != 0:
            rec["verdict"] = "test_patch_apply_failed"
            rec["error"] = out[-200:]
            return rec
        # 1) 基线：FTPS 预期全红
        base_map, base_tail = run_pytest_ftps(venv_py, mat, test_files, ftps, timeout=1800)
        if base_map is None:
            rec["verdict"] = "collection_failed"
            rec["error"] = f"baseline no-parseable: {base_tail}"
            return rec
        baseline_red = not any(base_map.values())
        rec["baseline_red"] = baseline_red
        if not baseline_red:
            rec["verdict"] = "baseline_not_red"
            rec["tail"] = base_tail
            return rec
        # 2) gold patch → 预期全绿
        rc, out = sh(["git", "apply", "--whitespace=nowarn", "-"], cwd=str(mat), timeout=120, input_text=inst["patch"])
        if rc != 0:
            rec["verdict"] = "patch_apply_failed"
            rec["error"] = out[-200:]
            return rec
        fix_map, fix_tail = run_pytest_ftps(venv_py, mat, test_files, ftps, timeout=1800)
        if fix_map is None:
            rec["verdict"] = "collection_failed"
            rec["error"] = f"fix no-parseable: {fix_tail}"
            return rec
        green_ok = all(fix_map.values())
        rec["fix_green"] = green_ok
        rec["verdict"] = "PASS" if green_ok else "fix_not_green"
        rec["tail"] = fix_tail
        return rec
    finally:
        sh(["git", "worktree", "remove", str(mat), "--force"], cwd=str(repo_dir), timeout=60)


def acquire_lock(out_path: Path) -> None:
    """输出文件并发锁（2026-10-30 同 out 互覆丢数据教训）：pid 文件 fail-closed。"""
    lock = out_path.with_suffix(out_path.suffix + ".lock")
    if lock.exists():
        try:
            pid = int(lock.read_text(encoding="utf-8").strip() or "0")
            os.kill(pid, 0)
            print(f"[lock] {lock} 已被 pid={pid} 持有 ⇒ 拒绝启动（并发写同 out 会互覆丢数据）", flush=True)
            raise SystemExit(3)
        except (ProcessLookupError, ValueError, PermissionError):
            pass  # 陈旧锁（进程已死）→ 接管
    lock.write_text(str(os.getpid()), encoding="utf-8")


def release_lock(out_path: Path) -> None:
    lock = out_path.with_suffix(out_path.suffix + ".lock")
    try:
        if lock.exists() and lock.read_text(encoding="utf-8").strip() == str(os.getpid()):
            lock.unlink()
    except OSError:
        pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--repos-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--parallel", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only-lang", default="python")
    ap.add_argument("--timeout", type=int, default=1800, help="单次 pytest 上限秒")
    ap.add_argument(
        "--venvs-dir",
        default="",
        help="per-repo venv 缓存目录（默认 ~/.cache/aitester/swe_bench_pro/venvs；不进工件目录）",
    )
    args = ap.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    acquire_lock(out_path)
    try:
        rows = [json.loads(ln) for ln in Path(args.dataset).read_text(encoding="utf-8").splitlines() if ln.strip()]
        if args.only_lang:
            rows = [x for x in rows if x.get("repo_language") == args.only_lang]
        if args.limit:
            rows = rows[: args.limit]
        records: list[dict] = []
        if args.resume and out_path.is_file():
            prev = json.loads(out_path.read_text(encoding="utf-8"))
            records = list(prev.get("records") or [])
            done = {r["instance_id"] for r in records}
            rows = [x for x in rows if x["instance_id"] not in done]
            print(f"resume：已完成 {len(done)}，续判 {len(rows)}", flush=True)
        print(f"实例 {len(rows)} | parallel={args.parallel}", flush=True)
        t0 = time.time()
        # 阶段 1：串行预建 per-repo venv（并行建同一 venv 会竞态互拆——Lite 同款教训）
        venvs_dir = args.venvs_dir or str(Path.home() / ".cache" / "aitester" / "swe_bench_pro" / "venvs")
        need_repos = sorted({x["repo"].split("/")[-1] for x in rows})
        for k, name in enumerate(need_repos, 1):
            err = ensure_repo_venv(Path(args.repos_dir) / name, Path(venvs_dir) / name)
            print(f"  [venv {k}/{len(need_repos)}] {name}: {'OK' if err is None else err[:120]}", flush=True)
        jobs = [(x["instance_id"], args.dataset, args.repos_dir, venvs_dir) for x in rows]
        with ProcessPoolExecutor(max_workers=args.parallel) as pool:
            futs = {pool.submit(judge_instance, j): j[0] for j in jobs}
            for i, fut in enumerate(as_completed(futs), 1):
                try:
                    rec = fut.result()
                except Exception as exc:  # 单实例异常登记不中断
                    rec = {"instance_id": futs[fut], "verdict": "runner_error", "error": str(exc)[:200]}
                records.append(rec)
                if i % 5 == 0 or rec.get("verdict") == "PASS":
                    print(
                        f"[{i}/{len(rows)}] {rec['instance_id']}: {rec['verdict']} ({time.time() - t0:.0f}s)",
                        flush=True,
                    )
                atomic_write_json(
                    out_path,
                    {"schema": "aitester_swe_pro_judge/1", "n": len(records), "records": records},
                )
        dist = Counter(r["verdict"] for r in records)
        print("verdict 分布:", dict(dist))
        n_total = len(records)
        n_pass = dist.get("PASS", 0)
        unjudged = sum(
            v
            for k, v in dist.items()
            if k
            in ("install_failed", "env_build_failed", "checkout_failed", "collection_failed", "no_ftps", "repo_missing")
        )
        print(f"全量口径 = {n_pass}/{n_total}")
        if n_total - unjudged:
            print(f"有判定口径 = {n_pass}/{n_total - unjudged}")
        return 0
    finally:
        release_lock(out_path)


if __name__ == "__main__":
    raise SystemExit(main())
