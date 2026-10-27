#!/usr/bin/env python3
"""FD 轮变异验证：未验证路径补锁与审计登记分类的六处回归锚点。

纪律（与 FB/FC 轮同）：
- 干净树先全绿且 collected 数一致；
- 每个变异：读取原字节 → 写入变异 → compile() → 收集数核对 → 跑受影响面 →
  记录红数 → sha256 校验后按原字节还原（绝不用 git checkout / git stash）；
- 变异必须转红；中性对照（仅改 docstring 措辞）必须 0 红。

锚点方向：每一处都是「把 FD 轮补上的验证退回沉默」——守卫不拦、清理不留、
登记不分类、探针不拒。
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = ROOT / ".venv" / "bin" / "python3"

CLI_APP = "src/cli/app.py"
MYSQL = "src/db/mysql_client.py"
TRACE = "src/observability/trace.py"
TRACE_VIZ = "src/utils/trace_viz.py"
AUDIT = "scripts/tools/audit_fix_coverage.py"

FD_TESTS = [
    "tests/test_unverified_paths_fd.py",
    "tests/test_audit_fix_coverage_registry_fd.py",
    "tests/test_audit_fix_coverage_base.py",
]

# (锚点名, 文件, 原串, 变异串, 额外受影响测试)
MUTANTS: list[tuple[str, str, str, str, list[str]]] = [
    (
        "F1-cli-guard-stops-rejecting",
        CLI_APP,
        '    if final_state is None:\n        raise AssertionError("graph.invoke 未返回状态（非预期）")',
        '    if False:  # mutation: 守卫不再拦 invoke 返回 None\n        raise AssertionError("graph.invoke 未返回状态（非预期）")',
        [],
    ),
    (
        "F2-mysql-guard-stops-rejecting",
        MYSQL,
        '        if self._pool is None:\n            raise AssertionError("MySQLClient 连接池未初始化")',
        '        if False:  # mutation: 守卫不再拦未初始化连接池\n            raise AssertionError("MySQLClient 连接池未初始化")',
        [],
    ),
    (
        "F3-trace-partial-file-not-cleaned",
        TRACE,
        "    except OSError as e:\n        if path is not None:\n            with contextlib.suppress(OSError):\n                os.unlink(path)",
        "    except OSError as e:\n        if False:  # mutation: 半成品文件不再清理\n            with contextlib.suppress(OSError):\n                os.unlink(path)",
        [],
    ),
    (
        "F4-trace-exhaustion-raises-wrong-type",
        TRACE,
        '    raise OSError(f"{target_dir} 下同名诊断快照已连续占用 {_DUMP_NAME_ATTEMPTS} 次")',
        '    raise RuntimeError(f"{target_dir} 下同名诊断快照已连续占用 {_DUMP_NAME_ATTEMPTS} 次")',
        [],
    ),
    (
        "F5-trace-viz-accepts-bool-as-int",
        TRACE_VIZ,
        "    if isinstance(total, int) and not isinstance(total, bool):\n        return total",
        "    if isinstance(total, int):  # mutation: bool 被当成整数读入\n        return total",
        [],
    ),
    (
        "F6-audit-registry-stops-classifying",
        AUDIT,
        "        verified = [ln for ln in uncovered if (rel, ln) in effective_entries]",
        "        verified = []  # mutation: 登记在册的行不再被单列",
        [],
    ),
    (
        "F8-crash-task-dump-success-path-lost",
        CLI_APP,
        '        if dump_path is not None:\n            result["trace_dump_path"] = dump_path',
        '        if False:  # mutation: 崩溃任务导出成功时不再写 trace_dump_path\n            result["trace_dump_path"] = dump_path',
        [],
    ),
    (
        "F9-glob-magic-dir-not-rejected",
        CLI_APP,
        '                    error_msg(f"目标不是普通文件（目录或特殊文件）：{pattern}")\n                    raise SystemExit(2)',
        '                    error_msg(f"目标不是普通文件（目录或特殊文件）：{pattern}")\n                    raise SystemExit(0)',
        [],
    ),
    (
        "F10-doctor-usage-text-lies",
        CLI_APP,
        '            conclusion_text = "用法错误（参数未通过校验；功能矩阵未执行，环境检查见上）"',
        '            conclusion_text = "用法错误（未执行任何检查）"  # mutation: 谎称环境检查未执行',
        [],
    ),
    (
        "F11-doctor-strict-reason-dropped",
        CLI_APP,
        '        reason = "；--strict 下 warn/skip 视为不通过"',
        '        reason = ""  # mutation: --strict 的理由不再披露',
        [],
    ),
    (
        # 中性对照：仅改 docstring 措辞，不动任何判据 —— 必须 0 红。
        "F7-control-wording",
        TRACE,
        "    落点纪律：``O_EXCL`` 创建 + 同名追加序号，绝不覆盖已有快照；写盘中途\n    失败会删除本次留下的半成品文件。",
        "    落点纪律：``O_EXCL`` 创建 + 同名追加序号，绝不覆盖已有快照；写盘中途\n    失败会删掉本次留下的半成品文件。",
        [],
    ),
]

_COLLECTED_RE = re.compile(r"(\d+) tests collected")
_BROKER_VARS = ("CODEBUDDY_SANDBOX_BROKER_IPC_ADDRESS", "CODEBUDDY_SANDBOX_HOST_FILE_OPERATION_COMMAND")


def _clean_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in _BROKER_VARS}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def collect_count(paths: list[str]) -> int:
    cmd = [str(PY), "-m", "pytest", *FD_TESTS, *paths, "--collect-only", "-q"]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=300, env=_clean_env())
    match = _COLLECTED_RE.search(proc.stdout + proc.stderr)
    if proc.returncode != 0 or not match:
        raise RuntimeError(f"collect failed rc={proc.returncode}: {(proc.stdout + proc.stderr)[-500:]}")
    return int(match.group(1))


def run_tests(paths: list[str]) -> tuple[int, int, str]:
    cmd = [
        str(PY),
        "-m",
        "pytest",
        *FD_TESTS,
        *paths,
        "-q",
        "--basetemp=/tmp/pt_fd_mut",
        "-p",
        "no:cacheprovider",
    ]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=900, env=_clean_env())
    output = proc.stdout + proc.stderr
    red = len(re.findall(r"^FAILED ", output, flags=re.MULTILINE))
    tail = "\n".join(output.splitlines()[-3:])
    return proc.returncode, red, tail


def precheck() -> bool:
    ok = True
    for name, relpath, old, _new, _ in MUTANTS:
        text = (ROOT / relpath).read_text(encoding="utf-8")
        counts = text.count(old)
        if counts != 1:
            print(f"[{name}] PRECHECK anchor count={counts} in {relpath}")
            ok = False
    print(f"[precheck] 锚点唯一性 {'全部通过' if ok else '有失败'}（{len(MUTANTS)} 个）")
    return ok


def main() -> int:
    if not precheck():
        return 1
    rc, red, tail = run_tests([])
    print(f"[baseline] rc={rc} red={red} collected={collect_count([])}\n{tail}")
    if rc != 0:
        print("BASELINE NOT GREEN — abort")
        return 1

    selected = MUTANTS
    if len(sys.argv) > 1:
        wanted = set(sys.argv[1:])
        selected = [m for m in MUTANTS if any(m[0].startswith(w) for w in wanted)]
        print(f"[filter] running {len(selected)} of {len(MUTANTS)}")

    results = []
    for name, relpath, old, new, extra in selected:
        path = ROOT / relpath
        original = path.read_bytes()
        sha_before = hashlib.sha256(original).hexdigest()
        text = original.decode("utf-8")
        if text.count(old) != 1:
            print(f"[{name}] ANCHOR NOT UNIQUE ({text.count(old)}) — skip")
            results.append((name, "ANCHOR-ERROR", -1))
            continue
        mutated = text.replace(old, new, 1)
        try:
            compile(mutated, str(path), "exec")
        except SyntaxError as exc:
            print(f"[{name}] MUTATION SYNTAX ERROR: {exc}")
            results.append((name, "SYNTAX-ERROR", -1))
            continue
        expected_collected = collect_count(extra)
        path.write_text(mutated, encoding="utf-8")
        try:
            rc, red, tail = run_tests(extra)
            mutated_collected = collect_count(extra)
        finally:
            path.write_bytes(original)
            restored = path.read_bytes()
            assert hashlib.sha256(restored).hexdigest() == sha_before, f"{name}: restore mismatch"
        if mutated_collected != expected_collected:
            print(f"[{name}] COLLECTED DRIFT {expected_collected} -> {mutated_collected}")
            results.append((name, "COLLECTED-DRIFT", red))
            continue
        verdict = "FAILED" if rc != 0 else "SURVIVED"
        print(f"[{name}] rc={rc} red={red} collected={mutated_collected} {verdict}\n{tail}")
        results.append((name, verdict, red))

    print("\n=== SUMMARY ===")
    for name, verdict, red in results:
        print(f"{verdict:14s} red={red:<3d} {name}")
    survivors = [n for n, v, _ in results if v != "FAILED" and n != "F7-control-wording"]
    wrong_control = [n for n, v, _ in results if n == "F7-control-wording" and v != "SURVIVED"]
    print(f"\n未杀活的变异 = {survivors}；对照误杀 = {wrong_control}")
    return 0 if not survivors and not wrong_control else 2


if __name__ == "__main__":
    sys.exit(main())
