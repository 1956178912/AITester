#!/usr/bin/env python3
"""BK 轮变异验证：ast.parse 守卫捕获面 / 形态归因 / 侧信道披露 / 发布键 / 棘轮 12 个锚点 + 1 个中性对照。

纪律（与 BA→BH 轮同）：
- 干净副本先全绿且 collected 数一致；
- 每个变异：读取原字节 → 写入变异 → compile() → 收集数核对 → 跑受影响面 →
  记录红数 → sha256 校验后按原字节还原（绝不用 git checkout / git stash）；
- 变异串一律带 ``# bk-mutation`` 标记，跑完后对 src/ scripts/ 做残留扫描；
- 变异必须转红；中性对照（仅改注释措辞）必须 0 红。

锚点选择口径：每个锚点对应一类"收口被拆掉后必须立刻变红"的能力——
捕获面（M1）、形态归因（M2）、空聚合默认（M3）、四个模块的腿（M4-M9）、
两个发布键（M10-M11）、棘轮的两条判定（M12-M13）。
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

BK_TESTS = ["tests/test_bk_ast_guard_capture.py"]
VOCAB = "src/utils/check_status.py"
MC = "src/tools/multi_candidate.py"

# (锚点名, 文件, 原串, 变异串, 额外受影响测试)
MUTANTS: list[tuple[str, str, str, str, list[str]]] = [
    (
        # 捕获面本体：缩回单腿 ⇒ ValueError 族重新抛穿（7 个锁 + 棘轮同时红）。
        "M1-capture-surface-narrowed-to-syntax-only",
        VOCAB,
        "AST_UNREADABLE_ERRORS: tuple[type[BaseException], ...] = (SyntaxError, ValueError)",
        "AST_UNREADABLE_ERRORS: tuple[type[BaseException], ...] = (SyntaxError,)  # bk-mutation: 捕获面缩回单腿",
        ["tests/test_multi_candidate.py"],
    ),
    (
        # 形态归因折叠：编码问题记成语法问题 ⇒ "读不懂"的成因被抹平。
        "M2-shape-undecodable-folded-into-syntax",
        VOCAB,
        "    except UnicodeEncodeError:\n        return UNPARSEABLE_UNDECODABLE",
        "    except UnicodeEncodeError:\n        return UNPARSEABLE_SYNTAX  # bk-mutation: 编码问题记成语法",
        [],
    ),
    (
        # 空聚合默认：一层都没记录 ⇒ 自称 ok（BK 的 fail-closed 默认被拆）。
        "M3-worst-status-empty-default-looks-clean",
        VOCAB,
        '    values = [status or "" for status in statuses]\n    if not values:\n        return default',
        '    values = [status or "" for status in statuses]\n    if not values:\n        return CHECK_OK  # bk-mutation: 空读数自称干净',
        [],
    ),
    (
        "M4-deterministic-target-unreadable-claims-ok",
        "src/tools/deterministic_repair.py",
        '            "target_readability",\n            CHECK_ERROR,\n            f"unparseable_target:{unparseable_shape(target_code)}",',
        '            "target_readability",\n            CHECK_OK,  # bk-mutation: 读不懂自称干净\n            f"unparseable_target:{unparseable_shape(target_code)}",',
        ["tests/test_batch_iv.py"],
    ),
    (
        "M5-cross-file-entry-unreadable-claims-ok",
        "src/tools/cross_file.py",
        '            "entry_readability",\n            CHECK_ERROR,\n            f"unparseable_entry:{unparseable_shape(entry_code)}",',
        '            "entry_readability",\n            CHECK_OK,  # bk-mutation: 入口读不懂自称干净\n            f"unparseable_entry:{unparseable_shape(entry_code)}",',
        ["tests/test_cross_file.py"],
    ),
    (
        # 投票归一化腿拆回单腿 ⇒ 棘轮必须点名（新单腿站点=违规）。
        "M6-expert-pool-normalization-single-leg-restored",
        "src/graph/expert_pool.py",
        "        return normalized or ast.dump(tree, annotate_fields=True)\n    except AST_UNREADABLE_ERRORS:",
        "        return normalized or ast.dump(tree, annotate_fields=True)\n    except SyntaxError:  # bk-mutation: 单腿守卫回归",
        ["tests/test_expert_pool.py"],
    ),
    (
        "M7-patch-intent-original-unreadable-claims-ok",
        "src/tools/patch_intent.py",
        '            "original_readability",\n            CHECK_ERROR,\n            f"unparseable_original:{unparseable_shape(code)}",',
        '            "original_readability",\n            CHECK_OK,  # bk-mutation: 原文读不懂自称干净\n            f"unparseable_original:{unparseable_shape(code)}",',
        ["tests/test_batch_iii.py"],
    ),
    (
        # 静态门 ValueError 腿换成拦不住的异常 ⇒ 孤立代理位重新抛穿节点。
        "M8-static-gate-value-error-leg-never-fires",
        MC,
        "    except ValueError as e:\n        # BK 轮：孤立代理位这类",
        "    except UnicodeDecodeError as e:  # bk-mutation: 实际拦不住孤立代理位\n        # BK 轮：孤立代理位这类",
        ["tests/test_multi_candidate.py", "tests/test_process_and_candidate_matrix.py"],
    ),
    (
        "M9-synthesis-result-unreadable-claims-ok",
        MC,
        'record_check_outcome(outcome_sink, "synthesis_result_readability", CHECK_ERROR, f"unparseable_result:{detail}")',
        'record_check_outcome(outcome_sink, "synthesis_result_readability", CHECK_OK, f"unparseable_result:{detail}")  # bk-mutation',
        ["tests/test_multi_candidate_synthesis.py"],
    ),
    (
        # 发布键聚合改成常量 ⇒ meta 读数不再来自真实腿。
        "M10-expert-pool-published-status-hardcoded-ok",
        "src/graph/debugger.py",
        '                    "check_status": worst_check_status(str(_leg.get("status", "")) for _leg in _ep_legs),',
        '                    "check_status": "ok",  # bk-mutation: 聚合改常量',
        ["tests/test_debugger_node_branches.py"],
    ),
    (
        # 发布键只留聚合不留腿 ⇒ 读数侧无法逐腿核对。
        "M11-expert-pool-published-legs-emptied",
        "src/graph/debugger.py",
        '                    "check_outcomes": list(_ep_legs),',
        '                    "check_outcomes": [],  # bk-mutation: 腿不发布',
        ["tests/test_debugger_node_branches.py"],
    ),
    (
        # 棘轮判定 1：任何 handler 都算覆盖 ⇒ 单腿守卫静默通过。
        "M12-ratchet-covers-predicate-always-true",
        "scripts/gates/check_ast_parse_guards.py",
        "def _covers_value_error(names: list[str]) -> bool:\n    return any(name in _CATCH_ALL or _catches_whole_value_error_family(name) for name in names)",
        "def _covers_value_error(names: list[str]) -> bool:\n    return True  # bk-mutation: 棘轮空转",
        [],
    ),
    (
        # 棘轮判定 2：豁免额度失效 ⇒ 超额站点不再点名。
        "M13-ratchet-exempt-quota-unenforced",
        "scripts/gates/check_ast_parse_guards.py",
        "            if key in EXEMPT and exempt_hits.count(key) < quota:",
        "            if key in EXEMPT:  # bk-mutation: 额度不参与判定",
        [],
    ),
    (
        # 中性对照：只改注释措辞，判定与文案都不变 ⇒ 必须 0 红。
        "N0-neutral-comment-wording-only",
        VOCAB,
        "#: 静态预检的可解析性原因字面量（BH 的 testless 层与 BI 的两个守卫共用）",
        "#: 静态预检的可解析性原因字面量（BH 的 testless 层与 BI 的守卫共用）",
        [],
    ),
]

_COLLECTED_RE = re.compile(r"(\d+) tests collected")


def collect_count(paths: list[str]) -> int:
    cmd = [str(PY), "-m", "pytest", *BK_TESTS, *paths, "--collect-only", "-q"]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=300)
    match = _COLLECTED_RE.search(proc.stdout + proc.stderr)
    if proc.returncode != 0 or not match:
        raise RuntimeError(f"collect failed rc={proc.returncode}: {(proc.stdout + proc.stderr)[-500:]}")
    return int(match.group(1))


def run_tests(paths: list[str]) -> tuple[int, int, str]:
    cmd = [
        str(PY),
        "-m",
        "pytest",
        *BK_TESTS,
        *paths,
        "-q",
        "--basetemp=/tmp/pt_bk_mut",
        "-p",
        "no:cacheprovider",
    ]
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=900,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    output = proc.stdout + proc.stderr
    red = len(re.findall(r"^FAILED ", output, flags=re.MULTILINE))
    tail = "\n".join(output.splitlines()[-3:])
    return proc.returncode, red, tail


def residue_scan() -> list[str]:
    hits: list[str] = []
    for rel in ("src", "scripts/gates"):
        for path in (ROOT / rel).rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            if "# bk-mutation" in path.read_text(encoding="utf-8", errors="replace"):
                hits.append(path.relative_to(ROOT).as_posix())
    return hits


def main() -> int:
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
        neutral = name.startswith("N0")
        verdict = "FAILED" if rc != 0 else "SURVIVED"
        if neutral:
            verdict = "NEUTRAL-GREEN" if rc == 0 else "NEUTRAL-UNEXPECTED-RED"
        elif rc == 0:
            verdict = "SURVIVED"
        print(f"[{name}] rc={rc} red={red} collected={mutated_collected} {verdict}\n{tail}")
        results.append((name, verdict, red))

    residue = residue_scan()
    print(f"\n[residue] '# bk-mutation' 残留文件={residue or '无'}")

    print("\n=== SUMMARY ===")
    for name, verdict, red in results:
        print(f"{verdict:22s} red={red:<3d} {name}")
    bad = [name for name, verdict, _ in results if verdict not in ("FAILED", "NEUTRAL-GREEN")]
    print(f"\nKILLED={sum(1 for _, v, _ in results if v == 'FAILED')}  未击杀/异常={len(bad)}  残留={len(residue)}")
    for name in bad:
        print(f"  需要复核：{name}")
    return 0 if not bad and not residue else 1


if __name__ == "__main__":
    sys.exit(main())
