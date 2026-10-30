#!/usr/bin/env python3
"""swebench_full_judge.py — SWE-bench Lite 300 全量物化判定（零 LLM）。

官方红→绿翻转协议（per-instance 完整物化）：
    worktree checkout base_commit → pre_install sed 补丁 → `pip install -e .`
    构建（C 扩展包必需）→ 应用 test_patch → 官方 test_cmd 跑 FAIL_TO_PASS
    （预期红）→ 应用 gold patch → 重跑（预期绿）→ 双满足 = verdict PASS。

环境配方来源 = swebench==2.1.8 官方 specs（swebench_spec_extract.py 提取）：
python 版本 + pip_packages 行级缓存 venv；install/pre_install 实例级执行；
test_cmd 为各 repo 原生 runner（django 用 runtests.py，pytest 族用 pytest）。

口径披露：
    - 只判 FAIL_TO_PASS 红绿翻转（PASS_TO_PASS 回归面不跑）；
    - Python 3.6 线在 macOS arm64 无官方解释器（结构性不可得）；
    - conda environment.yml 族（matplotlib）不在本 runner 覆盖内。

用法：
    python scripts/tools/swebench_full_judge.py \
        --spec experiments/results/swebench_repo_checkout_20261029/SPEC_EXTRACT.json \
        --dataset ~/.cache/aitester/swe_bench/swe_bench_lite_full_fields.jsonl \
        --out experiments/results/swebench_repo_checkout_20261029/FULL_JUDGE.json \
        [--limit N] [--instances id1,id2] [--parallel 4]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import types
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
REPOS_ROOT = Path.home() / ".cache/aitester/swe_bench/repos"
ENV_ROOT = Path("/tmp/swebench_envs")
MAT_ROOT = Path("/tmp/swebench_mat")
UV = shutil.which("uv") or "/Users/wangchenyu/.local/bin/uv"


def _stub_modal() -> None:
    """stub modal（swebench.harness 顶层强引；worker 只用纯函数不需要它）。

    idempotent：已 stub 则跳过（ProcessPool worker 各自执行一次）。"""
    if "modal" in sys.modules and getattr(sys.modules["modal"], "_is_stub", False):
        return

    class _Any:
        _is_stub = True

        def __getattr__(self, name: str) -> Any:
            return _Any()

        def __call__(self, *args: Any, **kwargs: Any) -> Any:
            return _Any()

    for sub in ("container_process", "io_streams"):
        sys.modules.setdefault(f"modal.{sub}", types.ModuleType(f"modal.{sub}"))
    sys.modules.setdefault("modal", _Any())


def sh(cmd: list[str] | str, cwd: str | None = None, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)


def uv_env() -> dict[str, str]:
    """uv 子进程环境：企业代理 TLS 须显式指系统 CA（SSL_CERT_FILE 缺失时
    uv 的 rustls 报 UnknownIssuer——实测 pip 引导静默失败的根因）。"""
    env = dict(os.environ)
    env.setdefault("SSL_CERT_FILE", "/etc/ssl/cert.pem")
    return env


def ensure_line_venv(spec: dict[str, Any]) -> tuple[str | None, str, str]:
    """按官方 specs 建 repo×version 级 venv（python 版本 + 锁定 pip 包）。缓存复用。"""
    repo, version = spec["repo"], spec["version"]
    env_dir = ENV_ROOT / f"{repo.split('/')[-1]}_{version.replace('.', '_')}"
    venv_py = env_dir / "bin" / "python"
    if venv_py.is_file():
        return str(venv_py), "", ""
    if env_dir.exists():
        shutil.rmtree(env_dir, ignore_errors=True)
    env_dir.parent.mkdir(parents=True, exist_ok=True)
    python_version = (spec.get("specs") or {}).get("python") or ""
    if not python_version:
        return None, "specs.python 缺失", ""
    # 平台可得性（2026-10-30 实测）：uv 的 rustls 不吃 SSL_CERT_FILE 且
    # python-build-standalone 无 3.6/3.7 的 macOS arm64（3.8 也无——结构
    # 性不可得线直接豁免，避免 600s 下载挂起）；3.8 走 micromamba（conda-
    # forge 有 osx-arm64 3.8.20）。
    fallback_note = ""
    if python_version.startswith(("3.6", "3.7")):
        # 披露式 fallback：官方 pin 的 3.6/3.7 在 arm64 无解释器，但多数老线
        # 上游支持 3.8——降级运行并逐记录披露（django 2.x/3.0 实测可跑）
        python_version = "3.8"
        fallback_note = (
            f"python_fallback: 官方 pin 3.6/3.7 → 3.8（arm64 无 {python_version and '3.6/3.7'} 解释器，上游支持内）"
        )
    if python_version.startswith("3.8"):
        # micromamba 建 per-line env（conda-forge 有 osx-arm64 3.8.20）
        if not Path("/tmp/micromamba").is_file():
            return None, "structural: micromamba 未就绪", fallback_note
        if not venv_py.is_file():
            env_dir.parent.mkdir(parents=True, exist_ok=True)
            r = subprocess.run(
                ["/tmp/micromamba", "create", "-y", "-p", str(env_dir), "python=3.8", "-c", "conda-forge"],
                capture_output=True,
                text=True,
                timeout=900,
                env=uv_env(),
            )
            if r.returncode != 0:
                return None, f"micromamba 失败: {(r.stderr or r.stdout)[-200:]}", fallback_note
        # micromamba env 自带 pip/setuptools——跳过 uv venv 创建，直落 pkgs 安装
        pkgs = (spec.get("specs") or {}).get("pip_packages") or []
        if pkgs:
            r = subprocess.run(
                [UV, "pip", "install", "--python", str(venv_py), *pkgs],
                capture_output=True,
                text=True,
                timeout=1800,
                env=uv_env(),
            )
            if r.returncode != 0:
                return None, f"uv pip 失败: {(r.stderr or r.stdout)[-300:]}", fallback_note
        return str(venv_py), "", fallback_note
    try:
        r = subprocess.run(
            [UV, "venv", "--seed", "--python", python_version, str(env_dir)],
            capture_output=True,
            text=True,
            timeout=600,
            env=uv_env(),
        )
        uv_ok = r.returncode == 0
        uv_err = f"uv venv 失败: {(r.stderr or r.stdout)[-200:]}"
    except subprocess.TimeoutExpired:
        uv_ok = False
        uv_err = f"uv venv 超时（python={python_version}）"
    if not uv_ok:
        # 通用 fallback：uv 的 python-build-standalone 缺老版本（3.10 也被
        # 新版 release 丢弃）→ micromamba（conda-forge 全版本 osx-arm64）
        if not Path("/tmp/micromamba").is_file():
            return None, uv_err, ""
        shutil.rmtree(env_dir, ignore_errors=True)
        env_dir.parent.mkdir(parents=True, exist_ok=True)
        rm = subprocess.run(
            ["/tmp/micromamba", "create", "-y", "-p", str(env_dir), f"python={python_version}", "-c", "conda-forge"],
            capture_output=True,
            text=True,
            timeout=900,
            env=uv_env(),
        )
        if rm.returncode != 0:
            return None, f"{uv_err} | micromamba 也失败: {(rm.stderr or rm.stdout)[-200:]}", fallback_note
    if r.returncode != 0:
        return None, f"uv venv 失败: {(r.stderr or r.stdout)[-200:]}", ""
    pkgs = (spec.get("specs") or {}).get("pip_packages") or []
    # --seed 装 pip；老 venv 缺 pip 时按需引导（官方 install 命令用 `python -m pip`）
    if sh([str(venv_py), "-m", "pip", "--version"], timeout=60).returncode != 0:
        rb = subprocess.run(
            [UV, "pip", "install", "--python", str(venv_py), "pip"],
            capture_output=True,
            text=True,
            timeout=300,
            env=uv_env(),
        )
        if rb.returncode != 0:
            return None, f"pip 引导失败: {(rb.stderr or rb.stdout)[-200:]}", ""
    # 构建链先装（--no-build-isolation 的输入）：setuptools<69 保老包 setup.py 兼容；
    # 行内 pin 的 setuptools 在 pkgs 步覆盖为官方锁版
    rb = subprocess.run(
        [UV, "pip", "install", "--python", str(venv_py), "setuptools<69", "wheel", "cython"],
        capture_output=True,
        text=True,
        timeout=600,
        env=uv_env(),
    )
    if rb.returncode != 0:
        return None, f"构建链安装失败: {(rb.stderr or rb.stdout)[-200:]}", fallback_note
    if pkgs:
        r = subprocess.run(
            [UV, "pip", "install", "--python", str(venv_py), *pkgs],
            capture_output=True,
            text=True,
            timeout=1800,
            env=uv_env(),
        )
        if r.returncode != 0:
            return None, f"uv pip 失败: {(r.stderr or r.stdout)[-300:]}", fallback_note
    return str(venv_py), "", fallback_note


def _grade_ftps(ftps: list[str], output: str) -> tuple[bool, str]:
    """官方评分语义：逐测试判定 FAIL_TO_PASS 是否全过（rc 代理会被模块内
    无关测试拖累——django 11001 实测 121 测试中 2 失败即整模块判红）。

    pytest -rA 摘要行：`PASSED node::id` / `FAILED node::id`；
    django runtests --verbosity 2：`test_x (module.Class) ... ok`。
    """
    passed_pytest = set()
    passed_sympy: set[str] = set()
    passed_django = []  # (name, module)——FTPS 的 module 可能无类名，须前缀匹配
    for line in output.splitlines():
        s = line.strip()
        m = re.match(r"^(PASSED|FAILED|ERROR)\s+(.+)$", s)
        if m:
            if m.group(1) == "PASSED":
                passed_pytest.add(m.group(2).strip())
            continue
        m2 = re.match(r"^(\w+) \(([\w.]+)\)\s*\.\.\.\s*(ok|FAIL|ERROR)", s)
        if m2 and m2.group(3) == "ok":
            passed_django.append((m2.group(1), m2.group(2)))
            continue
        # sympy bin/test --verbose：`test_Name ok` 逐测试一行（FTPS 是裸测试名）
        # 行尾常带填充与文件级标记（"... ok    [FAIL]"）——只锚定状态词
        m4 = re.match(r"^(test\w*) (ok|F|E|s)(?:\s|\[|$)", s)
        if m4 and m4.group(2) == "ok":
            passed_sympy.add(m4.group(1))
    if not passed_pytest and not passed_django and not passed_sympy:
        return False, "no-parseable-test-results: " + output[-300:]

    def _ftp_passed(t: str) -> bool:
        if t in passed_pytest or t in passed_sympy:
            return True
        # sympy 裸测试名（test_Derivative）
        if re.match(r"^test\w*$", t):
            return t in passed_sympy
        m3 = re.match(r"^(\w+) \(([\w.]+)\)$", t)
        if m3:
            name, module = m3.groups()
            return any(
                (n == name and mod.startswith(module + ".")) or (n == name and mod == module)
                for n, mod in passed_django
            )
        return False

    missing = [t for t in ftps if not _ftp_passed(t)]
    return (not missing), f"FTPS 未过 {len(missing)}/{len(ftps)}: {missing[:3]}"


def run_ftps(venv_py: str, mat: Path, spec: dict[str, Any], test_patch: str, ftps: list[str]) -> tuple[bool, str]:
    """官方协议：test_patch 的**测试模块**（get_test_directives，django 系
    自动转 module 路径）接在原生 test_cmd 后；verdict 按 FTPS 逐测试评分。"""
    test_cmd = (spec.get("specs") or {}).get("test_cmd") or "pytest -rA"
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    # 注意：此处**不禁**插件 autoload——判定 venv 只装官方 pin 的插件
    # （astropy setup.cfg 的 --doctest-rst 依赖 pytest-doctestplus，禁了直接
    # unrecognized arguments；Mut@k 的挂死系 AITester 主仓 venv 特有插件集）
    # 裸 `pytest`/`python` 须解析到线 venv（否则吃到别的环境的 site-packages
    # ——hypothesis 缺失假红实测）——与 install 步同款激活语义
    env["PATH"] = f"{Path(venv_py).parent}:{env.get('PATH', '')}"
    from swebench.harness.utils import get_test_directives

    directives = get_test_directives({"repo": spec["repo"], "test_patch": test_patch})
    # test_cmd 可带 shell 环境前缀（sympy: PYTHONWARNINGS='...' bin/test ...）
    # ——list 形式 subprocess 不能执行"VAR=val"令牌，解析进 env（去引号）
    parts = test_cmd.split()
    while parts and re.match(r"^[A-Z_][A-Z0-9_]*=", parts[0]):
        _k, _, _v = parts[0].partition("=")
        env[_k] = _v.strip("'\"")
        parts = parts[1:]
    cmd = [*parts, *directives]
    try:
        proc = subprocess.run(cmd, cwd=str(mat), capture_output=True, text=True, timeout=1200, env=env)
        output = (proc.stdout or "") + (proc.stderr or "")
        return _grade_ftps(ftps, output)
    except subprocess.TimeoutExpired:
        return False, ">1200s timeout"


def judge_instance(inst: dict[str, Any], line_index: dict[tuple[str, str], dict[str, Any]]) -> dict[str, Any]:
    """单实例完整物化 + 红绿翻转判定。"""
    _stub_modal()
    repo, version = inst["repo"], str(inst.get("version"))
    iid = inst["instance_id"]
    rec: dict[str, Any] = {"instance_id": iid, "repo": repo, "version": version}
    spec = line_index.get((repo, version))
    if spec is None:
        rec["verdict"], rec["stage"], rec["error"] = "structural_limitation", "env_spec", "线 spec 缺失"
        return rec
    venv_py, err, fallback_note = ensure_line_venv(spec)
    if venv_py is None:
        rec["verdict"], rec["stage"], rec["error"] = "env_build_failed", "venv", err
        return rec
    if fallback_note:
        rec["python_fallback"] = fallback_note

    local_repo = REPOS_ROOT / repo.split("/")[-1]
    mat = MAT_ROOT / iid
    if mat.exists():
        shutil.rmtree(mat, ignore_errors=True)
    # 清残留注册（被杀进程留下的 registered-but-deleted worktree 会让 add 拒绝）
    sh(["git", "-C", str(local_repo), "worktree", "prune"], timeout=60)
    r = sh(["git", "-C", str(local_repo), "worktree", "add", str(mat), inst["base_commit"]], timeout=120)
    if r.returncode != 0:
        rec["verdict"], rec["stage"], rec["error"] = "checkout_failed", "worktree", (r.stderr or "")[-200:]
        return rec
    try:
        # pre_install（sed 补丁等，官方口径）
        for pre in (spec.get("specs") or {}).get("pre_install") or []:
            sh(["bash", "-c", pre], cwd=str(mat), timeout=60)
        # install（`pip install -e .` 构建 C 扩展——cwd=worktree）。
        # --no-build-isolation：build isolation 每次联网拉 setuptools/ninja
        # （代理下慢且进程易被杀）——构建依赖由行级 venv 预装替代。
        install_cmd = (spec.get("specs") or {}).get("install") or ""
        if install_cmd:
            env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
            env["SSL_CERT_FILE"] = os.environ.get("SSL_CERT_FILE", "/etc/ssl/cert.pem")
            # spec 的 install 用裸 `python`（假设 conda activate）——把 venv bin
            # 置顶 PATH 复刻激活语义（否则解析到宿主 python 3.13——实测）
            env["PATH"] = f"{Path(venv_py).parent}:{env.get('PATH', '')}"
            # 新版 Xcode clang 把旧 Cython/C API 的函数指针不兼容从警告升级为
            # 错误（astropy wcslib 实测）——降回警告属编译器妥协，不影响判定语义
            env["CFLAGS"] = (
                "-Wno-error=incompatible-function-pointer-types -Wno-error=implicit-function-declaration "
                + env.get("CFLAGS", "")
            )
            env["LDFLAGS"] = env.get("LDFLAGS", "")
            # 解析 pyproject [build-system].requires → 预装进 venv
            # （no-build-isolation 下全部构建依赖必须在位——astropy 的
            # extension_helpers/setuptools_scm/oldest-supported-numpy 实测缺口）
            pyproject = mat / "pyproject.toml"
            if pyproject.is_file():
                try:
                    import tomllib

                    build_req = (
                        tomllib.loads(pyproject.read_text(encoding="utf-8")).get("build-system", {}).get("requires", [])
                    )
                    if build_req:
                        rb = subprocess.run(
                            [UV, "pip", "install", "--python", str(venv_py), *build_req],
                            capture_output=True,
                            text=True,
                            timeout=900,
                            env={**env, "SSL_CERT_FILE": os.environ.get("SSL_CERT_FILE", "/etc/ssl/cert.pem")},
                        )
                        if rb.returncode != 0:
                            rec["verdict"], rec["stage"], rec["error"] = (
                                "install_failed",
                                "build_deps",
                                (rb.stderr or rb.stdout)[-250:],
                            )
                            return rec
                except Exception as exc:  # tomllib 解析失败不阻断（老 setup.py 仓库）
                    rec["build_deps_note"] = str(exc)[:100]
            install_cmd = install_cmd.replace("pip install", "pip install --no-build-isolation")
            r = subprocess.run(
                ["bash", "-c", install_cmd], cwd=str(mat), capture_output=True, text=True, timeout=1800, env=env
            )
            if r.returncode != 0:
                rec["verdict"], rec["stage"], rec["error"] = "install_failed", "install", (r.stderr or "")[-250:]
                return rec
        # test_patch（测试先于修复；stdin 直传防挂起）
        r = subprocess.run(
            ["git", "apply", "-"], input=inst["test_patch"], cwd=str(mat), capture_output=True, text=True, timeout=60
        )
        if r.returncode != 0:
            rec["verdict"], rec["stage"], rec["error"] = "test_patch_failed", "test_patch", (r.stderr or "")[-200:]
            return rec
        ftps = json.loads(inst["FAIL_TO_PASS"]) if isinstance(inst["FAIL_TO_PASS"], str) else inst["FAIL_TO_PASS"]
        # 基线（buggy）：预期红（FTPS 未全过）
        red_ok, red_tail = run_ftps(venv_py, mat, spec, inst["test_patch"], ftps)
        rec["baseline_red"] = not red_ok
        if red_ok:
            rec["verdict"], rec["stage"], rec["tail"] = "baseline_not_red", "baseline", red_tail
            return rec
        # gold patch：预期绿
        r = subprocess.run(
            ["git", "apply", "-"], input=inst["patch"], cwd=str(mat), capture_output=True, text=True, timeout=60
        )
        if r.returncode != 0:
            rec["verdict"], rec["stage"], rec["error"] = "gold_patch_failed", "gold_patch", (r.stderr or "")[-200:]
            return rec
        green_ok, green_tail = run_ftps(venv_py, mat, spec, inst["test_patch"], ftps)
        rec["fix_green"] = green_ok
        rec["verdict"] = "PASS" if green_ok else "fix_not_green"
        rec["tail"] = green_tail
        return rec
    finally:
        sh(["git", "-C", str(local_repo), "worktree", "remove", str(mat), "--force"], timeout=60)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--instances", default="")
    ap.add_argument("--parallel", type=int, default=4)
    ap.add_argument("--resume", action="store_true", help="续跑：跳过 out 文件中已判定的实例")
    args = ap.parse_args()

    spec_data = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    line_index = {(line["repo"], line["version"]): line for line in spec_data["lines"]}
    instances = [
        json.loads(line) for line in Path(args.dataset).read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    if args.instances:
        wanted = {x.strip() for x in args.instances.split(",") if x.strip()}
        instances = [x for x in instances if x["instance_id"] in wanted]
    if args.limit:
        instances = instances[: args.limit]
    records: list[dict[str, Any]] = []
    if args.resume and Path(args.out).is_file():
        prev = json.loads(Path(args.out).read_text(encoding="utf-8"))
        records = list(prev.get("records") or [])
        done_ids = {r["instance_id"] for r in records}
        instances = [x for x in instances if x["instance_id"] not in done_ids]
        print(f"resume：已完成 {len(done_ids)}，续判 {len(instances)}", flush=True)
    print(f"实例 {len(instances)} | spec 线 {len(line_index)}", flush=True)
    t0 = time.time()

    # 阶段 1：串行预建全部线 venv（并行建同一 venv 会竞态互拆——实测教训）
    need_lines = {(i["repo"], str(i.get("version"))) for i in instances}
    env_fail = {}
    for k, (repo, version) in enumerate(sorted(need_lines), 1):
        spec = line_index.get((repo, version))
        if spec is None:
            continue
        try:
            _, err, _fb = ensure_line_venv(spec)
        except Exception as exc:  # 预建异常不拖垮全量——登记后继续
            err = f"{type(exc).__name__}: {exc}"[:200]
        if err:
            env_fail[(repo, version)] = err
        if k % 8 == 0:
            print(f"  [venv {k}/{len(need_lines)}] ({time.time() - t0:.0f}s)", flush=True)
    print(f"venv 预建完成：失败 {len(env_fail)} 线 {[(k[0], k[1]) for k in list(env_fail)[:5]]}", flush=True)

    t0 = time.time()
    with ProcessPoolExecutor(max_workers=args.parallel) as pool:
        futs = {pool.submit(judge_instance, inst, line_index): inst for inst in instances}
        for i, fut in enumerate(as_completed(futs), 1):
            try:
                rec = fut.result()
            except Exception as exc:  # 单实例异常登记不中断
                rec = {"instance_id": futs[fut]["instance_id"], "verdict": "runner_error", "error": str(exc)[:200]}
            records.append(rec)
            if i % 10 == 0 or rec.get("verdict") == "PASS":
                print(
                    f"[{i}/{len(instances)}] {rec['instance_id']}: {rec['verdict']} ({time.time() - t0:.0f}s)",
                    flush=True,
                )
            Path(args.out).write_text(
                json.dumps(
                    {"schema": "aitester_swebench_full_judge/1", "n": len(records), "records": records},
                    ensure_ascii=False,
                    indent=1,
                    allow_nan=False,
                ),
                encoding="utf-8",
            )
    dist = Counter(r["verdict"] for r in records)
    print("verdict 分布:", dict(dist))
    print(f"基础设施覆盖率 = {dist.get('PASS', 0)}/{len(records)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
