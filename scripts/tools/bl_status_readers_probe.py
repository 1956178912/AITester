#!/usr/bin/env python3
"""BL 轮测量探针（只读、零 LLM、零网络、零写入）。

测量"发布侧带 status、判定侧仍按空值判定"这一缺陷族的真实可达性，产出三类读数：

A. **键名读者普查**（AST 扫 `src/`，按键名逐处归类）+ **A2 局部变量再判定普查**
   （`x = state.get(key)` 后 `if x:` 不再含键名，须顺变量数；变量多次绑定或来源
   含 0/多个键时弃读，宁可少计不误计）：
   - `PUBLISH` —— 该键在此处被写出（字典字面量键、`x["k"] = …` 赋值目标、`state.py` 声明）；
   - `JUDGMENT_READ(…)` —— 该键的读出现在 `if`/`while`/`assert` 条件、比较/布尔/取反/三元运算、
     函数实参或关键字实参位（即值直接进入判定）；
   - `PASS_THROUGH` —— 读到之后只是赋值给局部变量 / 原样转发 / 作为表达式语句丢弃；
   每处都打印 `文件:行号` 供人工复核，分类规则即上面的定义，不含推断；末行**对账**要求
   每键的计数等于印出的读点行数。两条腿的计数口径不同且各自写明：
   - A（键名）一个读点 = `(文件, 行号, 键, 构造)` 去重后计数——`f(k=state.get("k"))`
     这一行里"关键字名"与"取键字面量"是同一个读的两层写法，按 AST 节点数会虚增；
   - A2（变量）按**使用处**计数——同一行两次使用（`isinstance(x, list) and len(x) > 0`）
     就是两处判定，不去重。
B. **折叠复现**：把真实消费函数分别喂 `status=ok` 与 `status=error/disabled` 下的同一空列表，
   比对判定读数（相同即证明今天"没比成"与"比完干净"不可区分）；B3 同时打印返回值面与
   sink 的 status 面（返回面四行相同、status 面可区分即口径成立）；B4 用调用点实参面
   核对消费方到底有没有把 status / outcome_sink 一起取走，以及 state 是否声明了该通道；
   B5 数 telemetry 侧新增的 status 判定读者（归档口径全缺席 ⇒ 不命中，保证历史读数零影响）。
C. **归档取值分布**：`experiments/results/**/*.json` 里这些键的出现次数与空值占比，
   假值/非平凡值的具体形态（`None` 与 `[]` 在消费侧不同判据），
   以及归档里是否存在任何 status 键（决定"历史读数零影响"能否成立）。
D. **形参级判定读者**：status 一旦被换成语义名再比较（`_contract_disclosure`
   里的 `== CHECK_OK`、`dangerous_api_added(..., outcome_sink)`），A 与 A2 都结构性
   数不到；本腿按形参名（`*_status` / `outcome_sink` / `sink`）数判定构造，并区分
   "真比较（condition/operator）"与"交给另一个函数（call-arg/kwarg）"，
   另列 `status_for_check(...)` 原语的调用点。
D2. **词汇级**比较普查：判定构造里出现 `CHECK_*` 词汇的站点——名字追不到的
   别名读者（`_guard_status = status_for_check(...)` 后 `!= CHECK_OK`）只能靠这条数。

用法：`.venv/bin/python scripts/tools/bl_status_readers_probe.py`
"""

from __future__ import annotations

import ast
import inspect
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.graph.risk_approval import assess_task_risk  # noqa: E402
from src.observability.agent_telemetry import (  # noqa: E402
    _UNMEASURABLE_STATUS_KEYS,
    _pattern_check_unmeasurable,
    _pattern_contract_break_rewrite,
)
from src.tools.patch_applier import dangerous_api_added  # noqa: E402
from src.utils.check_status import CHECK_DISABLED, CHECK_ERROR, CHECK_OK, status_for_check  # noqa: E402

STATUS_KEYS = (
    "static_check_status",
    "static_check_outcomes",
    "safety_check_status",
    "safety_check_outcomes",
    "oracle_check_status",
    "oracle_check_outcomes",
    "contract_status",
    "contract_outcomes",
    "contract_reason",
    "check_status",
    "check_outcomes",
)
EVIDENCE_KEYS = (
    "oracle_findings",
    "injection_findings",
    "contract_missing_symbols",
    "missing_symbols",
    "mypy_findings_count",
    "findings",
)
ALL_KEYS = tuple(dict.fromkeys(STATUS_KEYS + EVIDENCE_KEYS))
keys_holder = set(ALL_KEYS)

_PARSE_ERRORS = (SyntaxError, ValueError)


def _is_reader_call(call: ast.Call) -> bool:
    """`x.get("k")` / `x["k"]` 形态的读，本身不是判定构造。"""
    return isinstance(call.func, ast.Attribute) and call.func.attr in ("get", "pop")


def _contains(node: ast.AST, target: ast.AST) -> bool:
    return any(n is target for n in ast.walk(node))


def classify(node: ast.AST, parents: dict[int, ast.AST]) -> str:
    """按键出现的最近构造归类，规则见模块 docstring A。"""
    par = parents.get(id(node))
    if isinstance(node, ast.keyword):
        return "JUDGMENT_READ(call-kwarg)"
    if isinstance(par, ast.Dict) and any(k is node for k in par.keys):
        return "PUBLISH(dict-key)"
    if isinstance(par, ast.Subscript) and par.slice is node and isinstance(par.ctx, (ast.Store, ast.Del)):
        return "PUBLISH(subscript-write)"
    cur: ast.AST | None = node
    for _ in range(16):
        cur = parents.get(id(cur)) if cur is not None else None
        if cur is None:
            break
        if isinstance(cur, ast.keyword):
            return "JUDGMENT_READ(call-kwarg)"
        if isinstance(cur, (ast.If, ast.While, ast.Assert)) and _contains(cur.test, node):
            return "JUDGMENT_READ(condition)"
        if isinstance(cur, (ast.Compare, ast.BoolOp, ast.UnaryOp, ast.IfExp)):
            return "JUDGMENT_READ(operator)"
        if isinstance(cur, ast.Call) and not _is_reader_call(cur):
            return "JUDGMENT_READ(call-arg)"
        if isinstance(cur, (ast.Assign, ast.AnnAssign, ast.Return)):
            return "PASS_THROUGH"
        if isinstance(cur, ast.Expr):
            return "DISCARD(expr-stmt)"
    return "OTHER"


def _parents(tree: ast.AST) -> dict[int, ast.AST]:
    out: dict[int, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            out[id(child)] = parent
    return out


def census_src() -> tuple[dict[str, Counter[str]], dict[str, list[str]]]:
    """读点普查：**一个读点 = (文件, 行号, 键, 构造)**，先去重再计数。

    去重三处都必须进键：`_build_risk_summary(contract_status=state.get("contract_status"))`
    这一行里，关键字名与字典取键字面量是同一个"读"的两层写法，按 AST 节点数会虚增；
    而 (文件, 行号) 单独去重又会让同行的第二个键被第一个吞掉（BL 开工时正是这样少计了
    ``contract_missing_symbols`` 与 ``contract_status`` 各自的读点）。
    去重后再计数，"计数 == 印出的读点行"因此由构造成立（末行对账只作复核）。
    """
    kinds: dict[str, Counter[str]] = {k: Counter() for k in ALL_KEYS}
    sites: dict[str, list[str]] = defaultdict(list)
    seen: set[tuple[str, int, str, str]] = set()
    for path in sorted((ROOT / "src").rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except _PARSE_ERRORS:
            continue
        parents = _parents(tree)
        rel = str(path.relative_to(ROOT))
        for node in ast.walk(tree):
            key: str | None = None
            if isinstance(node, ast.keyword):
                key = node.arg
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                par = parents.get(id(node))
                is_dict_key = isinstance(par, ast.Dict) and any(k is node for k in par.keys)
                is_subscript = isinstance(par, ast.Subscript) and par.slice is node
                is_get_arg = isinstance(par, ast.Call) and _is_reader_call(par) and node in par.args
                if is_dict_key or is_subscript or is_get_arg:
                    key = node.value
            if key not in kinds:
                continue
            kind = classify(node, parents)
            if rel == "src/graph/state.py" and kind.startswith(("JUDGMENT", "PASS_THROUGH", "OTHER")):
                # 通道声明与默认值构造面：不是判定读点，单列 DECLARE（口径写进手册）
                kind = "DECLARE(state 通道声明/默认值)"
            site = (rel, getattr(node, "lineno", 0), key, kind)
            if site in seen:
                continue
            seen.add(site)
            kinds[key][kind] += 1
            sites[key].append(f"{rel}:{site[1]} {kind}")
    return kinds, sites


def _read_keys(expr: ast.AST) -> set[str]:
    """子树里的**键读取**（`d["k"]` Load / `.get("k")` 位置实参）。

    跳过 `keyword` 子树：`f(contract_missing_symbols=state.get(...))` 是把值**喂进**
    另一个函数，赋给左边的不是该键的值而是该函数的返回值——键名普查与变量普查都
    要按这条界线走，否则消费面会被虚增。
    """
    out: set[str] = set()

    def visit(node: ast.AST) -> None:
        if isinstance(node, ast.keyword):
            return
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.ctx, ast.Load)
            and node.slice.value in keys_holder
        ):
            out.add(str(node.slice.value))
        if isinstance(node, ast.Call) and _is_reader_call(node):
            for arg in node.args:
                if isinstance(arg, ast.Constant) and arg.value in keys_holder:
                    out.add(str(arg.value))
        for child in ast.iter_child_nodes(node):
            visit(child)

    visit(expr)
    return out


def _is_literal_default(expr: ast.AST) -> bool:
    """纯字面量（`None` / `[]` / `{}` / 常量元组）——通道的哨兵初值，不构成新来源。"""
    if isinstance(expr, ast.Constant):
        return True
    if isinstance(expr, (ast.List, ast.Tuple, ast.Set)):
        return all(_is_literal_default(e) for e in expr.elts)
    if isinstance(expr, ast.Dict):
        return all(_is_literal_default(v) for v in expr.values if v is not None)
    return False


def _binding_of(value: ast.AST) -> tuple[str, str | None]:
    """赋值右侧与键的关系：`("bind", key)` / `("literal", None)` / `("unknown", None)`。"""
    if _is_literal_default(value):
        return "literal", None
    keys = _read_keys(value)
    if len(keys) == 1:
        return "bind", next(iter(keys))
    return "unknown", None


def _scope_of(node: ast.AST, parents: dict[int, ast.AST]) -> str:
    """所在作用域标识（函数名或模块级），用作变量绑定的作用域键。"""
    cur: ast.AST | None = node
    while cur is not None:
        if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return f"fn:{cur.name}"
        cur = parents.get(id(cur))
    return "module"


def census_variables() -> tuple[dict[str, Counter[str]], dict[str, list[str]]]:
    """A2：先取键、再对局部变量判定的读点（键名普查数不到 `if oracle_findings:`）。

    绑定规则（非流敏感，按作用域聚合）：某名字的全部"取值来源"指向同一个键 ⇒ 绑定；
    来源含 0 个或多个键（`f(state["k1"], state["k2"])` 的返回值、把键喂进 kwarg 的
    调用结果）⇒ 弃读；字面量初值（`= None` / `= []`）算哨兵，不改变绑定。
    """
    var_kinds: dict[str, Counter[str]] = {k: Counter() for k in ALL_KEYS}
    var_sites: dict[str, list[str]] = defaultdict(list)
    for path in sorted((ROOT / "src").rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except _PARSE_ERRORS:
            continue
        parents = _parents(tree)
        rel = str(path.relative_to(ROOT))
        # (作用域, 变量名) → 该名字的全部纯取值来源键名；非取值赋值计入 ambiguous。
        sources: dict[tuple[str, str], set[str]] = defaultdict(set)
        ambiguous: set[tuple[str, str]] = set()
        for node in ast.walk(tree):
            target: ast.AST | None = None
            value: ast.AST | None = None
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target, value = node.targets[0], node.value
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                target, value = node.target, node.value
            if value is None or not isinstance(target, ast.Name):
                continue
            slot = (_scope_of(node, parents), target.id)
            relation, key = _binding_of(value)
            if relation == "bind":
                sources[slot].add(str(key))
            elif relation == "unknown":
                ambiguous.add(slot)
        bindings = {slot: next(iter(ks)) for slot, ks in sources.items() if len(ks) == 1}
        for slot in ambiguous:
            bindings.pop(slot, None)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Name) or not isinstance(node.ctx, ast.Load):
                continue
            key = bindings.get((_scope_of(node, parents), node.id))
            if key is None:
                continue
            kind = classify(node, parents)
            var_kinds[key][kind] += 1
            var_sites[key].append(f"{rel}:{getattr(node, 'lineno', 0)} {kind} (var {node.id})")
    return var_kinds, var_sites


def report_census() -> None:
    print("=" * 72)
    print("A. src/ 键名读者普查（判定读点=值直接进入条件/运算/实参）")
    print("=" * 72)
    kinds, sites = census_src()
    mismatched = []
    for key in ALL_KEYS:
        ctr = kinds[key]
        pub = sum(v for k, v in ctr.items() if k.startswith("PUBLISH"))
        judg = sum(v for k, v in ctr.items() if k.startswith("JUDGMENT"))
        pas = sum(v for k, v in ctr.items() if k.startswith("PASS_THROUGH"))
        dec = sum(v for k, v in ctr.items() if k.startswith("DECLARE"))
        tag = "status 通道" if key in STATUS_KEYS else "证据/计数"
        print(
            f"\n[{key}]（{tag}）  发布={pub}  判定读点={judg}  转发={pas}  声明={dec}  "
            f"其它={sum(v for k, v in ctr.items() if k in ('OTHER', 'DISCARD(expr-stmt)'))}"
        )
        for line in sorted(sites[key]):
            print("   ", line)
        if sum(ctr.values()) != len(sites[key]):
            mismatched.append((key, sum(ctr.values()), len(sites[key])))
    print(
        f"\n   对账（每键：计数 == 印出的读点行）成立 = {not mismatched}"
        f"{'  失配=' + str(mismatched) if mismatched else ''}"
    )
    print("\n" + "=" * 72)
    print("A2. 局部变量再判定普查（`x = state.get(key)` 后 `if x:` 不再含键名，须顺变量数）")
    print("=" * 72)
    var_kinds, var_sites = census_variables()
    for key in ALL_KEYS:
        ctr = var_kinds[key]
        judg = sum(v for k, v in ctr.items() if k.startswith("JUDGMENT"))
        other = sum(v for k, v in ctr.items() if not k.startswith("JUDGMENT"))
        if not judg and not other:
            continue
        print(f"\n[{key}]  变量判定读点={judg}  变量其它用法={other}")
        for line in sorted(var_sites[key]):
            print("   ", line)


def _call_sites(rel: str, fname: str) -> list[tuple[int, list[str]]]:
    """某文件里对 `fname(...)` 的调用点：行号 + 关键字实参名（源码级，不看推断）。"""
    path = ROOT / rel
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except _PARSE_ERRORS as exc:
        return [(0, [f"PARSE_{type(exc).__name__}"])]
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
        if name != fname:
            continue
        out.append((node.lineno, sorted(k.arg or "<pos>" for k in node.keywords)))
    return out


def _state_declared(rel: str, key: str) -> bool:
    """state 通道声明文件里是否出现该键名（源码级子串判定）。"""
    return key in (ROOT / rel).read_text(encoding="utf-8")


def report_callsites() -> None:
    print("\n" + "=" * 72)
    print("B4. 真实调用点的实参面（消费侧有没有把 status 一起取走）")
    print("=" * 72)
    for rel, fname, need in (
        ("src/graph/debugger.py", "_build_risk_summary", "contract_status"),
        ("src/graph/risk_approval.py", "assess_task_risk", "contract_status"),
        ("src/tools/patch_applier.py", "dangerous_api_added", "outcome_sink"),
        ("src/tools/patch_applier.py", "check_naming_contract", "outcome_sink"),
    ):
        sites = _call_sites(rel, fname)
        print(f"\n   {rel} :: {fname}(...)  调用点={len(sites)}  需带实参={need}")
        for lineno, kwargs in sites:
            print(f"      :{lineno}  关键字实参={kwargs}  含 {need} = {need in kwargs}")
    print("\n   state 通道声明面（src/graph/state.py 是否声明该键）")
    for key in ("contract_status", "contract_reason", "contract_outcomes", "static_check_status", "check_status"):
        print(f"      {key:22s} 已声明 = {_state_declared('src/graph/state.py', key)}")


def report_fold() -> None:
    print("\n" + "=" * 72)
    print("B. 折叠复现（真实消费函数）")
    print("=" * 72)
    params = list(inspect.signature(assess_task_risk).parameters)
    print(f"\nB1 assess_task_risk 形参 = {params}")
    print(f"   形参中含 status/outcome 者 = {[p for p in params if ('status' in p or 'outcome' in p)]}")
    accepts_status = "contract_status" in params
    print(f"   消费函数已能接收 contract_status = {accepts_status}")
    cases = (
        ("契约比完且一个不缺（status=ok）", [], CHECK_OK),
        ("契约根本没比（status=disabled，列表同样空）", [], CHECK_DISABLED),
        ("契约想比但没比成（status=error，列表同样空）", [], CHECK_ERROR),
        ("历史口径：键缺席", None, None),
        ("契约确实缺符号（status=ok）", ["Rule_L101"], CHECK_OK),
    )
    judgments: list[tuple] = []
    buckets: dict[str, str] = {}
    for label, missing, status in cases:
        kwargs: dict[str, Any] = {
            "confidence": 0.9,
            "changed_lines": 5,
            "changed_files": 1,
            "contract_missing_symbols": missing,
        }
        if accepts_status and status is not None:
            kwargs["contract_status"] = status
        d = assess_task_risk(**kwargs).to_dict()
        judgment = (d["factors"].get("impact"), d["risk_level"], d["approval_action"], d["risk_score"])
        judgments.append(judgment)
        label_key = label.split("（")[0]
        buckets[label_key] = (
            "unmeasurable" if any(str(r).startswith("contract_unmeasurable(") for r in d["reasons"]) else "clean"
        )
        print(f"   {label:34s} -> 判定={judgment}")
        print(f"   {'':34s}    披露={d['reasons']}")
    print(f"   判定四位（impact/level/action/score）逐位相同 = {len({tuple(j) for j in judgments[:4]}) == 1}")
    print(f"   第五行判定与前四行不同 = {judgments[4] != judgments[0]}")
    print(f"   披露桶（缺席/ok ⇒ clean，disabled/error ⇒ unmeasurable）= {buckets}")
    print(
        "   口径：BL 收口后 B1 不再断言『四行整字典相同』（披露进了 reasons），"
        "而是断言判定四位相同 + 披露可区分——前者=判定不变，后者=沉默被消掉。"
    )

    print("\nB2 _pattern_contract_break_rewrite（telemetry 故障模式命中）")
    recs = (
        ("记录里没有该键", {}),
        ("空列表（status 缺席）", {"contract_missing_symbols": []}),
        ("空列表 + status=ok", {"contract_missing_symbols": [], "contract_status": "ok"}),
        ("空列表 + status=disabled", {"contract_missing_symbols": [], "contract_status": "disabled"}),
        ("空列表 + status=error", {"contract_missing_symbols": [], "contract_status": "error"}),
        ("非空列表 + status=error", {"contract_missing_symbols": ["Rule_L101"], "contract_status": "error"}),
    )
    hits = [(label, _pattern_contract_break_rewrite(rec)) for label, rec in recs]
    for label, v in hits:
        print(f"   {label:26s} -> {v}")
    print(f"   前五行全 False = {not any(v for _, v in hits[:5])}（status 三值不影响命中）")

    print("\nB3 dangerous_api_added（S2 危险 API 守卫，补丁应用前置）")
    clean = "def f():\n    return 1\n"
    sig = list(inspect.signature(dangerous_api_added).parameters)
    print(f"   形参 = {sig}  含 outcome_sink = {'outcome_sink' in sig}")
    print("   返回面（历史口径，四行读数即『空列表不可区分』）与 sink 面（BL 收口后可区分）：")
    for label, new_code in (
        ("可读且干净", clean),
        ("读不懂（真语法错误）", "def (:\n"),
        ("读不懂（围栏整块含危险调用）", "```python\nimport os\nos.system('id')\n```"),
        ("读不懂（NUL 字节）", "x = 1\x00"),
    ):
        sink: list[dict[str, Any]] = []
        added = dangerous_api_added(clean, new_code, outcome_sink=sink)
        print(
            f"   {label:22s} -> 返回 {added}  status={status_for_check(sink, 'dangerous_api')!r}"
            f"  reason={sink[0].get('reason') or '-'}"
        )

    print("\nB5 _pattern_check_unmeasurable（BL 轮新增的 status 判定侧读者）")
    legs = (
        ("归档口径：5 个 status 键全缺席", {}),
        ("全部 ok", dict.fromkeys(_UNMEASURABLE_STATUS_KEYS, "ok")),
        ("全部 disabled（按设计未检查）", dict.fromkeys(_UNMEASURABLE_STATUS_KEYS, "disabled")),
        ("contract_status=error", {"contract_status": "error"}),
        ("oracle_check_status=unavailable", {"oracle_check_status": "unavailable"}),
        ("check_status=ERROR（大小写折叠）", {"check_status": "ERROR"}),
        ("contract_status=None（本轮没记录）", {"contract_status": None}),
    )
    hits5 = [(label, _pattern_check_unmeasurable(rec)) for label, rec in legs]
    for label, v in hits5:
        print(f"   {label:32s} -> {v}")
    print(f"   归档口径（键全缺席）不命中 = {not hits5[0][1]}（历史读数零影响的判据）")
    print(f"   ok / disabled / None 三行不命中 = {not any(v for _, v in hits5[1:3] + hits5[6:])}")
    print(f"   error / unavailable / 大小写折叠 三行命中 = {all(v for _, v in hits5[3:6])}")


def _shape(value: Any) -> str:
    """非平凡取值的紧凑形态（列表只数长度，字符串只记长度，避免把归档正文打进读数）。"""
    if isinstance(value, (list, dict, str)):
        return f"{type(value).__name__}(len={len(value)})"
    return f"{type(value).__name__}={value!r}"


def _walk_json(node: Any, holder: set[str], counts: Counter[str]) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            if k in holder:
                counts[k] += 1
                if isinstance(v, (list, dict, str)) and len(v) == 0:
                    counts[f"{k}::empty"] += 1
                    counts[f"{k}::shape::empty-{type(v).__name__}"] += 1
                elif v is None or v is False or v == 0:
                    counts[f"{k}::falsy"] += 1
                    counts[f"{k}::shape:falsy-{type(v).__name__}={v!r}"] += 1
                else:
                    counts[f"{k}::nontrivial"] += 1
                    counts[f"{k}::shape:nontrivial-{_shape(v)}"] += 1
        for v in node.values():
            _walk_json(v, holder, counts)
    elif isinstance(node, list):
        for v in node:
            _walk_json(v, holder, counts)


def report_corpus() -> None:
    print("\n" + "=" * 72)
    print("C. 归档取值分布（experiments/results/**/*.json）")
    print("=" * 72)
    holder = set(ALL_KEYS)
    counts: Counter[str] = Counter()
    files = sorted((ROOT / "experiments" / "results").rglob("*.json"))
    parsed = 0
    errors: Counter[str] = Counter()
    for p in files:
        try:
            data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        except _PARSE_ERRORS as exc:
            errors[type(exc).__name__] += 1
            continue
        parsed += 1
        _walk_json(data, holder, counts)
    print(f"   扫描文件={len(files)}  可解析={parsed}  解析失败={dict(errors)}")
    for key in ALL_KEYS:
        print(
            f"   [{key}] 出现={counts[key]}  空={counts[f'{key}::empty']}  "
            f"假值={counts[f'{key}::falsy']}  非平凡={counts[f'{key}::nontrivial']}"
        )
        for shape in sorted(k for k in counts if k.startswith(f"{key}::shape:")):
            print(f"      {shape.split('::shape:', 1)[1]:34s} {counts[shape]}")


def report_status_params() -> None:
    """D. **形参级**判定读者普查（A/A2 的键名/变量口径结构性数不到的一类）。

    为什么需要这条腿：收口后的读者把 status 换成语义名再比较
    （`_contract_disclosure(contract_status)` 里的 `== CHECK_OK`、
    `dangerous_api_added(..., outcome_sink)`），键名字面量早已不在判定构造里，
    A 数到的是"管道"（`state.get("contract_status")` 喂进实参位），A2 因为
    `_binding_of` 对多键来源弃读也数不到。本腿按**函数形参名**数判定构造，
    形参名口径：`*_status` 结尾，或 `outcome_sink` / `sink`。
    同时列出 `status_for_check(...)` 的调用点——它是本轮新增的"按腿取 status"读者原语。
    """
    print("\n" + "=" * 72)
    print("D. 形参级判定读者（键名/变量普查数不到的语义名比较）")
    print("=" * 72)
    rows = []
    primitive_sites: list[str] = []
    total_judg = 0
    total_cmp = 0
    for path in sorted((ROOT / "src").rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except _PARSE_ERRORS:
            continue
        parents = _parents(tree)
        rel = str(path.relative_to(ROOT))
        for fn in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            names = [a.arg for a in [*fn.args.posonlyargs, *fn.args.args, *fn.args.kwonlyargs]]
            for pname in names:
                if not (pname.endswith("_status") or pname in ("outcome_sink", "sink")):
                    continue
                kinds_here: Counter[str] = Counter()
                for node in ast.walk(fn):
                    if not (isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id == pname):
                        continue
                    kinds_here[classify(node, parents)] += 1
                judg = sum(v for k, v in kinds_here.items() if k.startswith("JUDGMENT"))
                cmp_ = sum(v for k, v in kinds_here.items() if k.endswith("(condition)") or k.endswith("(operator)"))
                if judg:
                    kinds_txt = {k: v for k, v in sorted(kinds_here.items())}
                    rows.append(f"{rel}:{fn.lineno} {fn.name}({pname})  判定读点={judg}  其中比较={cmp_}  {kinds_txt}")
                    total_judg += judg
                    total_cmp += cmp_
        primitive_sites.extend(
            f"{rel}:{node.lineno}"
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "status_for_check"
        )
    print("   形参名口径：*_status 结尾 或 outcome_sink / sink；仅列判定读点>0 的函数")
    print(
        "   『其中比较』= condition/operator（真去比 status 取值）；"
        "其余是 call-arg/call-kwarg，即把值交给另一个函数——按 A 腿同一口径计入判定，但语义是转发"
    )
    for row in sorted(rows):
        print(f"   {row}")
    print(f"   读者函数数（判定读点>0）= {len(rows)}  判定读点合计={total_judg}  其中比较={total_cmp}")
    print(f"\n   status_for_check(...) 调用点（本轮新增的按腿取 status 原语）= {len(primitive_sites)}")
    for site in sorted(primitive_sites):
        print(f"      {site}")
    report_status_vocabulary_compares()


def report_status_vocabulary_compares() -> None:
    """D2. **词汇级**比较普查：谁真的把 status 与 `CHECK_*` 词汇比了一次。

    为什么还要这条腿：D 按形参名数，A2 按"绑到键名的变量"数，两者都追不到
    把 status 取成局部别名后再比较的读者（`_guard_status = status_for_check(...)`
    后 `!= CHECK_OK`——别名既不含键名也不是形参）。词汇级不认名字，只认
    "判定构造里出现了 `CHECK_OK/DISABLED/UNAVAILABLE/ERROR`"，因此是本族缺陷
    "有没有人真的读 status" 的最直接读数。
    """
    print("\n" + "=" * 72)
    print("D2. 判定构造里出现 CHECK_* 词汇的站点（与名字无关）")
    print("=" * 72)
    vocab = {"CHECK_OK", "CHECK_DISABLED", "CHECK_UNAVAILABLE", "CHECK_ERROR"}
    sites: list[str] = []
    for path in sorted((ROOT / "src").rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except _PARSE_ERRORS:
            continue
        parents = _parents(tree)
        rel = str(path.relative_to(ROOT))
        sites.extend(
            f"{rel}:{node.lineno} {classify(node, parents)} ({node.id})"
            for node in ast.walk(tree)
            if isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Load)
            and node.id in vocab
            and classify(node, parents).startswith("JUDGMENT")
        )
    vocab_sites = Counter(s.split(" ")[2].strip("()") for s in sites)
    forms = Counter(s.split(" ")[1] for s in sites)
    print(
        f"   词汇比较站点 = {len(sites)}  按构造={dict(forms)}  "
        f"（call-arg 绝大多数是**发布侧**：把 CHECK_* 交给 record_check_outcome；"
        f"只有 operator/condition 是真的读）"
    )
    print(f"   按词汇={dict(vocab_sites)}")
    for site in sorted(sites):
        print(f"      {site}")


def main() -> int:
    report_census()
    report_fold()
    report_callsites()
    report_status_params()
    report_corpus()
    return 0


if __name__ == "__main__":
    sys.exit(main())
