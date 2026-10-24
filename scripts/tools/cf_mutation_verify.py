#!/usr/bin/env python3
"""CF 轮变异验证：登记面读侧对账门禁的判定锚点 38 个 + 1 个中性对照。

纪律（与 BH→CE 轮同）：
- 先全绿且收集数一致，再逐锚点变异；
- 每个变异：读原字节 → 写变异 → `compile()` → 收集数核对 → 跑受影响面 →
  记录红数与首批红名 → sha256 校验后按原字节还原（绝不用 git checkout / git stash）；
- 变异必须转红；中性对照（只在 docstring 加星号）必须 0 红。

锚点方向：每一处都是「把本轮补上的登记面读者退回静默」——§1 声明不比对、未登记键与无主键
不点名、行/小节缺席不报、BASELINE 判定键不读、收集恒等不判、工具不可用当 0、口径混用
（唯一数=调用点、目标数=命令数、非递归、漏 config.py）、清单方向不判、豁免无理由/陈旧、
编号断裂不报、拥有者锚点与接线不查、受检面披露丢失、披露读错仓库、摘要取错行、
括号语法放松、历史小节当 §1、重复行后者赢。

受影响面 = `tests/test_registration_readers_cf.py`。默认 deselect 登记完成前必然转红的
两例真实树锁（`test_gate_passes_on_real_tree` / `test_real_authorities_equal_baseline`），
登记完成后用 `CF_MUT_FULL=1` 整面重跑。
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = ROOT / ".venv" / "bin" / "python"

GATE = "scripts/gates/check_registration_consistency.py"
LOCK = "tests/test_registration_readers_cf.py"

PRE_REG_REDS = ["test_gate_passes_on_real_tree", "test_real_authorities_equal_baseline"]
FULL = os.environ.get("CF_MUT_FULL") == "1"
BASE_ARGS = [LOCK] if FULL else [LOCK, "-k", " and ".join(f"not {name}" for name in PRE_REG_REDS)]

COLLECTED_RE = re.compile(r"(\d+)(?:/\d+)? tests collected")
FAILED_RE = re.compile(r"^FAILED (\S+)", re.MULTILINE)

CONTROL = "N01-control-docstring"

# (锚点名, 文件, 原串, 变异串)
MUTANTS: list[tuple[str, str, str, str]] = [
    (
        "M01-declared-drift-not-judged",
        GATE,
        "        if got != authority:",
        "        if False:  # mutation: 声明与权威值不等也不报",
    ),
    (
        "M02-unregistered-key-not-named",
        GATE,
        '                f"{_rel(register_path)} §1「{label}」行：未登记当前口径键 {key}（权威值 {authority:.0f}）"',
        '                f"{_rel(register_path)} §1「{label}」行：（权威值 {authority:.0f}）"  # mutation: 键名不点名',
    ),
    (
        "M03-unowned-bracket-key-ignored",
        GATE,
        "    if unowned:",
        "    if False:  # mutation: 括号里的无主键不报",
    ),
    (
        "M04-heading-absent-counted-pass",
        GATE,
        '        return ([f"{_rel(register_path)}：未找到 §1「现状快照」小节标题——登记面无从解析"], [], [], {})',
        "        return [], [], [], {}  # mutation: 小节标题缺席当作通过",
    ),
    (
        "M05-row-absent-silent",
        GATE,
        '            problems.append(f"{_rel(register_path)} §1：未找到「{label}」行——缺席 ≠ 通过")\n            continue',
        "            continue  # mutation: 行缺席静默跳过",
    ),
    (
        "M06-skip-becomes-red",
        GATE,
        '            skips.append(f"[SKIP] 「{label}」项 {key}：权威值未取到，本项不判（成因见上）")',
        '            problems.append(f"[SKIP] 「{label}」项 {key}：权威值未取到，本项不判（成因见上）")'
        "  # mutation: 前提缺失记成红",
    ),
    (
        "M07-baseline-self-key-absent-silent",
        GATE,
        '                    "被指认为登记的权威源却没有这一键，等于没人读"',
        '                    ""  # mutation: 权威源缺键不报',
    ),
    (
        "M08-baseline-self-key-drift-ignored",
        GATE,
        "            if float(raw) != authority:",
        "            if False:  # mutation: BASELINE 与复算不等也不报",
    ),
    (
        "M09-baseline-authority-key-absent-silent",
        GATE,
        "                problems.append(f\"{spec['row']} 项 {key}：BASELINE.yaml {missing}——无权威值可对\")",
        "                continue  # mutation: BASELINE 缺权威键不报",
    ),
    (
        "M10-collected-identity-not-judged",
        GATE,
        "            if derived != collected:",
        "            if False:  # mutation: 收集口径与分项不等也不报",
    ),
    (
        "M11-ruff-unavailable-counted-zero",
        GATE,
        '        notes.append(f"[SKIP] 已格式化面复算未执行：{reason}")',
        '        auth["已格式化"] = 0.0  # mutation: 工具取不到当 0',
    ),
    (
        "M12-warn-only-ignored-as-blocking",
        GATE,
        '        1 for _, body in gate_steps if "continue-on-error: true" in body or re.search(r"--warn-only\\b", body)',
        '        1 for _, body in gate_steps if "continue-on-error: true" in body  # mutation: 只认 continue-on-error',
    ),
    (
        "M13-ci-unique-equals-callsites",
        GATE,
        '        "ci唯一门禁": len(set(refs)),',
        '        "ci唯一门禁": len(refs),  # mutation: 调用点数当唯一数',
    ),
    (
        "M14-make-commands-equals-targets",
        GATE,
        "    commands = sum(len(make_target_body(make_text, dep).splitlines()) for dep in deps)",
        "    commands = len(deps)  # mutation: 目标数当命令数",
    ),
    (
        "M15-mypy-targets-non-recursive",
        GATE,
        '    count = len(list(src.rglob("*.py")))',
        '    count = len(list(src.glob("*.py")))  # mutation: 只数顶层',
    ),
    (
        "M16-mypy-targets-drop-config",
        GATE,
        '    if (root / "config.py").is_file():\n        count += 1',
        "    if False:  # mutation: config.py 不进面\n        count += 1",
    ),
    (
        "M17-orphan-booklet-ignored",
        GATE,
        "        if orphans:",
        "        if False:  # mutation: 在盘未登记分册不报",
    ),
    (
        "M18-allowlist-reason-not-required",
        GATE,
        "        if not reason:",
        "        if False:  # mutation: 豁免不需要理由",
    ),
    (
        "M19-stale-allowlist-not-caught",
        GATE,
        "        if not (reviews_dir / booklet).is_file():",
        "        if False:  # mutation: 陈旧豁免不查",
    ),
    (
        "M20-allowlist-clears-both-sides",
        GATE,
        '        suffix = "" if side == "zh" else ".en"',
        '        suffix = ""  # mutation: 一侧豁免两侧通吃',
    ),
    (
        "M21-numbering-gap-ignored",
        GATE,
        "        if gaps:",
        "        if False:  # mutation: 编号断裂不报",
    ),
    (
        "M22-index-parse-failure-silent",
        GATE,
        "        if parse_problem is not None:\n            problems.append(parse_problem)\n            continue",
        "        if False:  # mutation: 清单面无从解析也不报\n            pass",
    ),
    (
        "M23-owner-anchor-missing-silent",
        GATE,
        "        if missing:",
        "        if False:  # mutation: 拥有者锚点缺失不报",
    ),
    (
        "M24-owner-chain-check-dropped",
        GATE,
        "        if owner in CHAIN_OWNED:",
        "        if False:  # mutation: 拥有者是否被跑不查",
    ),
    (
        "M25-self-wiring-always-wired",
        GATE,
        "    if invoked_by_chain(stem, make_text, ci_text):\n        return []",
        "    if True:  # mutation: 本门永远算已接线\n        return []",
    ),
    (
        "M26-red-path-drops-disclosure",
        GATE,
        "        for line in surface:\n            print(line, file=sys.stderr)",
        "        pass  # mutation: 报红路径不披露受检面",
    ),
    (
        "M27-disclosure-reads-real-repo",
        GATE,
        "        f\" / §2.2 编号 zh {len(reviewer_path_numbers(_index_label('zh', root))[0])} 条目、\"",
        "        f\" / §2.2 编号 zh {len(reviewer_path_numbers(_index_label('zh'))[0])} 条目、\"  # mutation: 漏传 root",
    ),
    (
        "M28-bare-number-disclosure-zeroed",
        GATE,
        "    bare = sum(bare_number_count(rows[label]) for label in per_row if label in rows)",
        "    bare = 0  # mutation: 裸数字披露恒 0",
    ),
    (
        "M29-gates-index-git-failure-empty",
        GATE,
        '    if res.returncode != 0:\n        return None, f"git ls-files 退出码 {res.returncode}"\n'
        '    return sorted(Path(line).stem for line in res.stdout.split() if line.endswith(".py")), None',
        "    if res.returncode != 0:  # mutation: git 失败当空索引\n        return [], None\n"
        '    return sorted(Path(line).stem for line in res.stdout.split() if line.endswith(".py")), None',
    ),
    (
        "M30-reviews-index-git-failure-empty",
        GATE,
        '    if res.returncode != 0:\n        return None, f"git ls-files 退出码 {res.returncode}"\n'
        '    return [Path(line).name for line in res.stdout.split() if line.endswith(".md")], None',
        "    if res.returncode != 0:  # mutation: git 失败当空清单\n        return [], None\n"
        '    return [Path(line).name for line in res.stdout.split() if line.endswith(".md")], None',
    ),
    (
        "M31-gates-index-git-absent-empty",
        GATE,
        '    res = _run(["git", "ls-files", "scripts/gates"], root)\n    if res is None:\n'
        '        return None, "git 可执行文件不可用（子进程未能启动）"',
        '    res = _run(["git", "ls-files", "scripts/gates"], root)\n    if res is None:  # mutation: git 缺席当空索引\n'
        "        return [], None",
    ),
    (
        "M32-reviews-index-git-absent-empty",
        GATE,
        '    res = _run(["git", "ls-files", "docs/reviews"], root)\n    if res is None:\n'
        '        return None, "git 可执行文件不可用（子进程未能启动）"',
        '    res = _run(["git", "ls-files", "docs/reviews"], root)\n    if res is None:  # mutation: git 缺席当空清单\n'
        "        return [], None",
    ),
    (
        "M33-summary-takes-first-line",
        GATE,
        '    lines = [line.strip() for line in out.splitlines() if line.strip()]\n    return lines[-1] if lines else ""',
        "    lines = [line.strip() for line in out.splitlines() if line.strip()]  # mutation: 取首行而非末行\n"
        '    return lines[0] if lines else ""',
    ),
    (
        "M34-any-bracket-counted-current",
        GATE,
        r'_BRACKET_RE = re.compile(r"〔当前口径[^：:]*[：:](?P<body>[^〕]*)〕")',
        r'_BRACKET_RE = re.compile(r"〔[^：:]*[：:](?P<body>[^〕]*)〕")  # mutation: 任何〔〕都算当前口径',
    ),
    (
        "M35-pair-accepts-equals-sign",
        GATE,
        r'_PAIR_RE = re.compile(r"([^\s/；;、]+)\s+([0-9]+(?:\.[0-9]+)?)")',
        r'_PAIR_RE = re.compile(r"([^\s/；;、]+?)[=\s]+([0-9]+(?:\.[0-9]+)?)")  # mutation: 键=数 也认',
    ),
    (
        "M36-section-one-not-cut",
        GATE,
        '    nxt = re.search(r"^##\\s+\\d\\.", tail, re.M)\n    return tail[: nxt.start()] if nxt else tail',
        "    return tail  # mutation: §1 不在下一个 H2 收口",
    ),
    (
        "M37-section-one-reads-whole-register",
        GATE,
        '    start = re.search(r"^##\\s+1\\.", register_text, re.M)\n    if start is None:\n'
        "        return None\n    tail = register_text[start.end() :]",
        '    if not re.search(r"^##\\s+1\\.", register_text, re.M):  # mutation: 整册都当 §1\n        return None\n'
        "    tail = register_text",
    ),
    (
        "M38-register-rows-last-wins",
        GATE,
        "        rows.setdefault(label, body)",
        "        rows[label] = body  # mutation: 后出现的同名行覆盖",
    ),
    (
        CONTROL,
        GATE,
        "退出码：`0` = 全部对账通过；`1` = 存在漂移 / 未登记分册 / 无主数字 / 拥有者失效 /",
        "退出码：**`0` = 全部对账通过；`1` = 存在漂移 / 未登记分册 / 无主数字 / 拥有者失效 /",
    ),
]


def _clean_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def collect_count() -> int:
    cmd = [str(PY), "-m", "pytest", *BASE_ARGS, "--collect-only", "-q"]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=300, env=_clean_env())
    match = COLLECTED_RE.search(proc.stdout + proc.stderr)
    if proc.returncode != 0 or not match:
        raise RuntimeError(f"collect failed rc={proc.returncode}: {(proc.stdout + proc.stderr)[-500:]}")
    return int(match.group(1))


def run_tests() -> tuple[int, int, str, list[str]]:
    cmd = [str(PY), "-m", "pytest", *BASE_ARGS, "-q", "--basetemp=/tmp/pt_cf_mut", "-p", "no:cacheprovider"]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=900, env=_clean_env())
    output = proc.stdout + proc.stderr
    failed = FAILED_RE.findall(output)
    tail = "\n".join(output.splitlines()[-3:])
    return proc.returncode, len(failed), tail, failed


def precheck() -> bool:
    ok = True
    seen: set[str] = set()
    for name, relpath, old, _new in MUTANTS:
        if name in seen:
            print(f"[{name}] DUPLICATE ANCHOR NAME")
            ok = False
        seen.add(name)
        counts = (ROOT / relpath).read_text(encoding="utf-8").count(old)
        if counts != 1:
            print(f"[{name}] PRECHECK anchor count={counts} in {relpath}")
            ok = False
    print(f"[precheck] 锚点唯一性 {'全部通过' if ok else '有失败'}（{len(MUTANTS)} 个，含对照）")
    return ok


def main() -> int:
    print(f"[caliber] 受影响面 = {'整面（CF_MUT_FULL=1）' if FULL else f'{LOCK} 去掉 2 例登记前真实树锁'}")
    if not precheck():
        return 1
    baseline_collected = collect_count()
    rc, red, tail, _ = run_tests()
    print(f"[baseline] rc={rc} red={red} selected={baseline_collected}\n{tail}")
    if rc != 0 or red != 0:
        print("BASELINE NOT GREEN — abort")
        return 1

    selected = MUTANTS
    if len(sys.argv) > 1:
        wanted = set(sys.argv[1:])
        selected = [m for m in MUTANTS if any(m[0].startswith(w) for w in wanted)]
        print(f"[filter] running {len(selected)} of {len(MUTANTS)}")

    results = []
    for name, relpath, old, new in selected:
        path = ROOT / relpath
        original = path.read_bytes()
        sha_before = hashlib.sha256(original).hexdigest()
        text = original.decode("utf-8")
        if text.count(old) != 1:
            print(f"[{name}] ANCHOR NOT UNIQUE ({text.count(old)}) — skip")
            results.append((name, "ANCHOR-ERROR", -1, []))
            continue
        mutated = text.replace(old, new, 1)
        try:
            compile(mutated, str(path), "exec")
        except SyntaxError as exc:
            print(f"[{name}] MUTATION SYNTAX ERROR: {exc}")
            results.append((name, "SYNTAX-ERROR", -1, []))
            continue
        path.write_text(mutated, encoding="utf-8")
        try:
            rc, red, tail, failed = run_tests()
            mutated_collected = collect_count()
        finally:
            path.write_bytes(original)
            restored = path.read_bytes()
            assert hashlib.sha256(restored).hexdigest() == sha_before, f"{name}: restore mismatch"
        if mutated_collected != baseline_collected:
            print(f"[{name}] COLLECTED DRIFT {baseline_collected} -> {mutated_collected}")
            results.append((name, "COLLECTED-DRIFT", red, failed))
            continue
        verdict = "FAILED" if rc != 0 else "SURVIVED"
        killers = [f.rsplit("::", 1)[-1] for f in failed[:3]]
        print(f"[{name}] rc={rc} red={red} selected={mutated_collected} {verdict} 红名={killers}")
        results.append((name, verdict, red, failed))

    print("\n=== SUMMARY ===")
    for name, verdict, red, _failed in results:
        print(f"{verdict:14s} red={red:<3d} {name}")
    survivors = [n for n, v, _r, _f in results if v != "FAILED" and n != CONTROL]
    wrong_control = [n for n, v, _r, _f in results if n == CONTROL and v != "SURVIVED"]
    print(f"\n未杀活的变异 = {survivors}；对照误杀 = {wrong_control}")
    return 0 if not survivors and not wrong_control else 2


if __name__ == "__main__":
    sys.exit(main())
