#!/usr/bin/env python3
"""BK 轮判定不变性对账（手册 §4 的读数由本脚本产出，零 LLM、零写入、零网络）。

要回答的问题：本轮把 5 个模块的 13 个 AST 守卫站点从"只捕 SyntaxError"收敛到
共享口径 ``AST_UNREADABLE_ERRORS``，并给 ``attempt_deterministic_repair`` /
``analyze_cross_file_deps`` / ``apply_edit_intents`` / ``cross_validate`` /
``static_validate_patch`` / ``synthesize_candidates`` 加了可选 ``outcome_sink``。
**判定值（返回值）必须逐字节不变**，只有"读不懂"这一事实新增了一条侧信道披露。

做法：用 ``git show HEAD:<path>`` 把本轮改动前的五个模块取到临时目录，装成一个
独立包 ``headpkg``（其对 ``src.*`` 的导入仍解析到工作树——本轮没动那些依赖），
再对同一批输入分别调用新旧函数，比对 ``repr``。

分类口径：
- ``identical``：新旧返回值逐字相同 ⇒ 判定不变；
- ``escape_fixed``：旧版抛非 ``SyntaxError``（``ValueError`` 族）、新版返回 ⇒
  这正是本轮修掉的抛穿腿，不算判定变化；
- ``UNEXPECTED``：其余任何差异 ⇒ 本轮的"只补披露、不改判定"承诺被破坏，脚本
  以 rc=1 失败。

输入面 = 归档语料全部代码类字符串（``experiments/results/**/*.json`` 的
``patch`` / ``generated_test`` / ``test_patch`` / ``code`` / ``target_code``），
外加一组人工形态栅格（空 / 语法错 / 闭合围栏 / 截断围栏 / git diff / 空字节 /
孤立代理位，以及三条"读不懂但锚点或线索命中"的业务形态：代理位注释、代理位
NameError 目标、可应用的围栏代理位）——形态栅格专门覆盖归档里 0 实例的那几类，
``apply_edit_intents`` 的锚点也按这三条选（``return 1``），否则它走不到 AST 门、
抛穿腿证明不了。
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
RESULTS = REPO / "experiments" / "results"
HEAD_FILES = (
    "src/tools/deterministic_repair.py",
    "src/tools/cross_file.py",
    "src/tools/patch_intent.py",
    "src/tools/multi_candidate.py",
    "src/graph/expert_pool.py",
    "src/utils/env_utils.py",
)
CODE_KEYS = ("patch", "generated_test", "test_patch", "code", "target_code")


def _materialize_head(root: Path) -> None:
    """把 HEAD 版四个模块落到 `root/headpkg/…`（不触碰工作树）。"""
    for rel in HEAD_FILES:
        text = subprocess.run(
            ["git", "-C", str(REPO), "show", f"HEAD:{rel}"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        dest = root / "headpkg" / Path(rel).relative_to("src")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
    for pkg in ("", "utils", "tools", "graph"):
        (root / "headpkg" / pkg / "__init__.py").touch()


def _shapes() -> dict[str, str]:
    """人工形态栅格：覆盖归档 0 实例的两类（孤立代理位 / git diff）与 BJ 已见的三类。"""
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as fh:
        fh.write(b"x = '\xff\xfe'\nprint(x)\n")
        tmp = Path(fh.name)
    lone = tmp.read_text(encoding="utf-8", errors="surrogateescape")
    tmp.unlink(missing_ok=True)
    return {
        "empty": "",
        "syntax_error": "def f(:\n",
        "fenced_closed": "```python\ndef f():\n    return 1\n```",
        "fenced_unclosed": "```python\ndef f():\n    return 1",
        "git_diff": "--- a/m.py\n+++ b/m.py\n@@ -1,2 +1,2 @@\n-x = 1\n+x = 2\n",
        "nul_byte": "x = 1\x00\n",
        "lone_surrogate": lone,
        "valid_module": "import json\n\n\ndef f(v):\n    return json.dumps(v)\n",
        # 三条"读不懂但仍在业务流程里"的形态：入口面（attempt_deterministic_repair /
        # apply_edit_intents / static_validate_patch）在纯代理位文本上走不到 AST 门，
        # 只有锚点命中 / NameError 线索 / 可应用的围栏补丁才能证明抛穿腿真的在。
        "surrogate_anchor": "def f():\n    return 1  # \ud800\n",
        "surrogate_nameerror": "def f():\n    return os.path  # \ud800\n",
        "fenced_surrogate": "```python\ndef f():\n    return 1  # \ud800\n```",
    }


def _corpus_inputs() -> list[str]:
    out: list[str] = []
    for path in sorted(RESULTS.rglob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError, RecursionError, UnicodeDecodeError):
            continue
        stack: list[Any] = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                for key, value in node.items():
                    if key in CODE_KEYS and isinstance(value, str):
                        out.append(value)
                    stack.append(value)
            elif isinstance(node, list):
                stack.extend(node)
    return out


def _call_pair(label: str, code: str, live_fn, head_fn) -> str:
    """返回 identical / both_raised / escape_fixed / UNEXPECTED:<详情>。"""

    def run(fn):
        try:
            return "OK", repr(fn(code))
        except BaseException as exc:
            return type(exc).__name__, ""

    h_kind, h_repr = run(head_fn)
    l_kind, l_repr = run(live_fn)
    if h_kind == l_kind == "OK":
        return "identical" if h_repr == l_repr else f"UNEXPECTED[{label}] repr 不同 {h_repr[:60]!r} != {l_repr[:60]!r}"
    if h_kind not in {"OK", "SyntaxError"} and l_kind == "OK":
        return "escape_fixed"
    if h_kind == l_kind and h_repr == l_repr:
        # 两侧抛同一种非 SyntaxError 异常：判据上等价，但对账质量上它是盲区——
        # 若整批都是 both_raised，说明调用面本身写错了（实测踩坑：把双参函数按
        # 单参调用，两侧同样 TypeError，会被记成 identical 的假绿）。
        return f"both_raised:{h_kind}"
    return f"UNEXPECTED[{label}] 异常面不同 head={h_kind} live={l_kind}"


def main() -> int:
    sys.path.insert(0, str(REPO))
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _materialize_head(root)
        sys.path.insert(0, str(root))
        import headpkg.graph.expert_pool as head_ep
        import headpkg.tools.cross_file as head_cf
        import headpkg.tools.deterministic_repair as head_dr
        import headpkg.tools.multi_candidate as head_mc
        import headpkg.tools.patch_intent as head_pi

        from src.graph import expert_pool as live_ep
        from src.tools import cross_file as live_cf
        from src.tools import deterministic_repair as live_dr
        from src.tools import multi_candidate as live_mc
        from src.tools import patch_intent as live_pi

        original = "def f():\n    return 1\n"

        targets = (
            (
                "attempt_deterministic_repair",
                lambda c: live_dr.attempt_deterministic_repair(
                    target_code=c,
                    test_output="NameError: name 'os' is not defined\ncannot import name 'flatten'",
                ),
                lambda c: head_dr.attempt_deterministic_repair(
                    target_code=c,
                    test_output="NameError: name 'os' is not defined\ncannot import name 'flatten'",
                ),
            ),
            ("_top_level_names", live_dr._top_level_names, head_dr._top_level_names),
            (
                "_insert_import",
                lambda c: live_dr._insert_import(c, "json"),
                lambda c: head_dr._insert_import(c, "json"),
            ),
            (
                "analyze_cross_file_deps",
                lambda c: live_cf.analyze_cross_file_deps("m", {"m": c}),
                lambda c: head_cf.analyze_cross_file_deps("m", {"m": c}),
            ),
            (
                "_collect_reverse_deps",
                lambda c: live_cf.analyze_cross_file_deps("m", {"m": "import o\no.f()\n", "o": c}, bidirectional=True),
                lambda c: head_cf.analyze_cross_file_deps("m", {"m": "import o\no.f()\n", "o": c}, bidirectional=True),
            ),
            ("_normalize_patch_for_voting", live_ep._normalize_patch_for_voting, head_ep._normalize_patch_for_voting),
            (
                "cross_validate",
                lambda c: live_ep.ExpertPoolAgent.cross_validate(
                    object.__new__(live_ep.ExpertPoolAgent),
                    [{"patch": c, "dimension": "boundary_handling", "confidence": 0.5}],
                    min_agreement=1,
                ),
                lambda c: head_ep.ExpertPoolAgent.cross_validate(
                    object.__new__(head_ep.ExpertPoolAgent),
                    [{"patch": c, "dimension": "boundary_handling", "confidence": 0.5}],
                    min_agreement=1,
                ),
            ),
            (
                "apply_edit_intents",
                lambda c: live_pi.apply_edit_intents(c, [{"old_str": "return 1", "new_str": "return 2"}]),
                lambda c: head_pi.apply_edit_intents(c, [{"old_str": "return 1", "new_str": "return 2"}]),
            ),
            (
                "static_validate_patch",
                lambda c: live_mc.static_validate_patch(original, c),
                lambda c: head_mc.static_validate_patch(original, c),
            ),
            (
                "_extract_modified_regions",
                lambda c: live_mc._extract_modified_regions(original, c),
                lambda c: head_mc._extract_modified_regions(original, c),
            ),
            (
                "synthesize_candidates",
                lambda c: live_mc.synthesize_candidates(
                    original, [live_mc.CandidateResult(index=0, patch="p", new_code=c, static_passed=True)]
                ),
                lambda c: head_mc.synthesize_candidates(
                    original, [head_mc.CandidateResult(index=0, patch="p", new_code=c, static_passed=True)]
                ),
            ),
        )

        inputs = [("shape", name, code) for name, code in _shapes().items()]
        inputs += [("corpus", f"#{i}", code) for i, code in enumerate(_corpus_inputs(), start=1)]

        tally: dict[str, int] = {"identical": 0, "escape_fixed": 0, "both_raised": 0}
        escapes: Counter[str] = Counter()
        raised_kinds: Counter[str] = Counter()
        unexpected: list[str] = []
        for origin, name, code in inputs:
            for label, live_fn, head_fn in targets:
                verdict = _call_pair(f"{label}@{origin}:{name}", code, live_fn, head_fn)
                if verdict.startswith("UNEXPECTED"):
                    unexpected.append(verdict)
                else:
                    bucket = verdict.split(":")[0]
                    tally[bucket] += 1
                    if bucket == "escape_fixed":
                        escapes[f"{label} <- {origin}:{name}"] += 1
                    if bucket == "both_raised":
                        raised_kinds[f"{label}:{verdict.split(':', 1)[1]}"] += 1

        print(f"输入数={len(inputs)}（形态栅格 {len(_shapes())} + 归档 {len(inputs) - len(_shapes())}）")
        print(f"对账项={len(inputs) * len(targets)}（{len(targets)} 个判定面）")
        for key in sorted(tally):
            print(f"  {key} = {tally[key]}")
        print("两侧同异常（对账盲区，逐类点名；不影响 rc，但整批同类=调用面写错）：")
        for item, count in raised_kinds.most_common():
            print(f"  {item} = {count}")
        print("抛穿腿点名（旧版抛非 SyntaxError、新版返回）：")
        for item, count in escapes.most_common():
            print(f"  {item} = {count}")
        print(f"UNEXPECTED = {len(unexpected)}")
        for item in unexpected[:10]:
            print(f"  {item}")
        return 1 if unexpected else 0


if __name__ == "__main__":
    raise SystemExit(main())
