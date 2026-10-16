"""路径 C：求解器/属性搜索定向触发输入（Solver-Directed Trigger Search, SDTS）。

**为什么需要它**（2026-10-11 完整实测的结论）

QuixBugs 50 任务 × 2 臂的实测（583 个变异体）给出：

| 指标 | 值 | 95% CI |
|---|---|---|
| MTR（触发率） | **0.679** | [0.640, 0.716] |
| MDR（判别率） | **0.654** | [0.614, 0.691] |
| oracle 缺口 | **0.038** | [0.023, 0.062] |

**触发缺口 32.1% 是 oracle 缺口（3.8%）的约 8.5 倍**——即在真实基准上，
"测试没把变异体的行为偏差跑出来"远比"跑出来了但断言没抓到"严重。

同时，对抗演示暴露了**测试生成侧的输入选择弱点**：LLM 为 QuixBugs `bitcount`
写 `assert bitcount(-1) == 0` 导致无限循环；为 `get_factors` 断言了错误期望值。
**根因是 LLM 在"选什么输入"上不可靠**。

**本模块的做法（严格分工，对齐 ConcoLixir arXiv:2606.26545 的定位）**

- **输入侧由自动搜索负责**（本模块）：不依赖 LLM 猜输入；
- **断言侧仍交给 LLM**：本模块只产出**行为差分见证**（输入 + 缺陷版输出 + 正确版输出），
  把它作为"必须断言的期望值"交给 LLM 写断言。

**三层策略**（按可用信息量递进，全部零 LLM）

1. **名称启发式**：QuixBugs 全部 41 个程序**零类型注解**（实测 `grep -l "def .*->"` = 0），
   因此按参数名推断类型（`arr`/`items`/`s`/`x`/`n`/`k`...）；
2. **属性搜索（hypothesis）**：在推断出的策略空间内搜索，含边界值偏好；
3. **行为差分验证（唯一判据）**：候选输入 `i` 仅在
   `behavior(buggy, i) ≠ behavior(gold, i)` 时才算**触发见证**。
   等价/无差异的候选一律丢弃——**不猜、不假设**。
   ⚠️ **行为必须归一化后比较**：generator/iterator 的 `repr` 含内存地址，
   直接比较会产生大量**假见证**（实测 `flatten` 两版都返回 generator →
   57/57 假阳性）。见 `_norm`。

**安全阀**（实测必需，见 `bitcount` 教训）：
- 每次调用 1s 软超时（`signal.setitimer`）→ 记录 `"timeout"`；
- 单任务总预算（默认 120 次候选）→ 防止在慢函数上耗光预算；
- 探针与执行均在隔离子进程/tmp 目录，不触碰宿主文件。

用法：
    from experiments.solver_directed_trigger import search_trigger_witnesses

    w = search_trigger_witnesses(buggy_code=..., gold_code=..., fn_name="bitcount")
    print(w.as_prompt_section())   # 交给 LLM 写断言的"期望值清单"
"""

from __future__ import annotations

import ast
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# 名称启发式：参数名 → 类型族
_SEQ_NAMES = {"arr", "items", "nums", "values", "lst", "list", "seq", "weight_by_edge"}
_STR_NAMES = {"s", "t", "source", "target", "parens", "text", "pattern"}
_INT_NAMES = {"n", "k", "x", "capacity", "height", "start", "end", "goal", "value"}
_DICT_NAMES = {"weight_by_edge", "mapping", "table"}
_NODE_NAMES = {"node", "startnode", "goalnode", "root", "head"}


def infer_param_family(name: str, default_code: str = "") -> str:
    """按参数名（必要时辅以函数体线索）推断类型族。

    Returns: "seq" | "seq_seq" | "str" | "int" | "dict" | "node" | "unknown"
    """
    low = name.lower()
    if low in _SEQ_NAMES:
        # knapsack 的 items 是 [(weight, value), ...] → 二元组序列
        if low == "items":
            return "seq_seq"
        if low == "weight_by_edge":
            return "dict"
        return "seq"
    if low in _STR_NAMES:
        return "str"
    if low in _DICT_NAMES:
        return "dict"
    if low in _NODE_NAMES:
        return "node"
    if low in _INT_NAMES:
        return "int"
    # 体线索：函数体里出现下标/长度运算 → 序列
    if default_code and f"{name}[" in default_code:
        return "seq"
    return "unknown"


@dataclass
class TriggerWitness:
    """一条**机械验证过的**触发见证：输入 + 两版实现的行为差异。"""

    args: list[Any]
    buggy_behavior: str
    gold_behavior: str
    note: str = ""

    def render(self) -> str:
        return (
            f"输入 {json.dumps(self.args, ensure_ascii=False)} → "
            f"缺陷版 {self.buggy_behavior[:90]} ｜ 正确版 {self.gold_behavior[:90]}"
        )


@dataclass
class TriggerSearchResult:
    """触发搜索汇总（全部可复算）。"""

    witnesses: list[TriggerWitness] = field(default_factory=list)
    candidates_tried: int = 0
    timeouts: int = 0
    errors: int = 0
    available: bool = False
    not_available_reason: str = ""

    @property
    def hit_rate(self) -> float | None:
        if not self.candidates_tried:
            return None
        return round(len(self.witnesses) / self.candidates_tried, 4)

    def as_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "not_available_reason": self.not_available_reason,
            "candidates_tried": self.candidates_tried,
            "witnesses": len(self.witnesses),
            "hit_rate": self.hit_rate,
            "timeouts": self.timeouts,
            "errors": self.errors,
        }

    def as_prompt_section(self, limit: int = 12) -> str:
        """渲染为交给 LLM 的"必须断言的期望值"段落（路径 C 的交付物）。"""
        if not self.witnesses:
            return ""
        lines = [
            f"【机械发现的触发输入（共 {len(self.witnesses)} 条，已逐条验证两版实现行为不同）】",
            "下列输入在缺陷版与正确版上**行为不同**。请为每条写**断言正确版行为**的测试：",
        ]
        lines.extend(f"- {w.render()}" for w in self.witnesses[:limit])
        lines.append(
            "注意：断言必须写**正确版的行为**（上表右侧），"
            "且不得修改被测实现；若某输入在正确版上会抛异常或超时，请用 pytest.raises/超时保护。"
        )
        return "\n".join(lines)


def _probe_source(module_name: str, fn_name: str, args_repr: str) -> str:
    """生成单次调用探针源码（安全阀：1s 软超时 + 结果 JSON）。"""
    return f'''
import json, signal, sys

class _TO(Exception):
    pass

def _h(s, f):
    raise _TO()

def _norm(v):
    """行为归一化（关键：防止"表示差异"被误判为"行为差异"）。

    实测教训：`flatten` 的两版实现都返回 **generator**，其 `repr` 含内存地址
    （`<generator object flatten at 0x...>`）→ 两次调用的 repr 必然不同 →
    产生 **57/57 的假见证**。若不归一化，路径 C 会把"同一个对象换个地址"
    当成触发依据，交给 LLM 写成必然失败的断言。

    归一化规则：
    - generator / iterator → 物化为 list（再递归归一化）；
    - dict → 按键排序；set → 排序；tuple/list → 递归；
    - 其他有 `__next__` 无 `__len__` 的对象 → 尝试物化；
    - 兜底：`type` + 稳定 repr（去掉 `0x...` 地址）。
    """
    import collections.abc as _abc

    if isinstance(v, (str, bytes, int, float, bool)) or v is None:
        return v
    if isinstance(v, dict):
        return {{str(k): _norm(x) for k, x in sorted(v.items(), key=lambda kv: str(kv[0]))}}
    if isinstance(v, (set, frozenset)):
        return sorted((_norm(x) for x in v), key=lambda x: repr(x))
    if isinstance(v, (list, tuple)):
        return [_norm(x) for x in v]
    if isinstance(v, _abc.Iterator) or (
        hasattr(v, "__next__") and not hasattr(v, "__len__")
    ):
        try:
            return [_norm(x) for x in list(v)[:200]]
        except Exception as _e:
            return f"<iterator-error:{{type(_e).__name__}}>"
    try:
        import re as _re
        return _re.sub(r"0x[0-9a-fA-F]+", "0xADDR", repr(v))[:200]
    except Exception:
        return f"<{{type(v).__name__}}>"


signal.signal(signal.SIGALRM, _h)
signal.setitimer(signal.ITIMER_REAL, 1.0)
try:
    import {module_name} as _m
    _fn = getattr(_m, "{fn_name}")
    _args = {args_repr}
    try:
        _out = _fn(*_args)
        _r = {{"kind": "ok", "value": repr(_norm(_out))[:200]}}
    except _TO:
        _r = {{"kind": "timeout"}}
    except Exception as _e:
        _r = {{"kind": "exc", "value": type(_e).__name__}}
finally:
    signal.setitimer(signal.ITIMER_REAL, 0)
print(json.dumps(_r))
'''


def _probe(code: str, module_name: str, fn_name: str, args: list[Any], timeout: int) -> str | None:
    """在隔离环境调用一次，返回行为摘要字符串（如 `ok:5` / `exc:IndexError` / `timeout`）。"""
    tmp = tempfile.mkdtemp(prefix="aitester_sdts_")
    try:
        with open(os.path.join(tmp, f"{module_name}.py"), "w", encoding="utf-8") as f:
            f.write(code)
        args_repr = repr(args)
        probe = os.path.join(tmp, "_probe.py")
        with open(probe, "w", encoding="utf-8") as f:
            f.write(_probe_source(module_name, fn_name, args_repr))
        try:
            from src.utils.process_utils import run_with_timeout

            res = run_with_timeout(
                [sys.executable, probe],
                cwd=tmp,
                capture_output=True,
                text=True,
                timeout=timeout,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": tmp},
                check=False,
            )
        except subprocess.TimeoutExpired:
            return "timeout"
        if res.returncode != 0:
            return None
        payload = json.loads((res.stdout or "").strip() or "{}")
        kind = payload.get("kind")
        if kind == "ok":
            return f"ok:{payload.get('value')}"
        if kind == "exc":
            return f"exc:{payload.get('value')}"
        if kind == "timeout":
            return "timeout"
        return None
    except Exception:
        logger.debug("SDTS 探针失败", exc_info=True)
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _strategy_for(family: str) -> Any:
    """按类型族给出 hypothesis 搜索策略（边界值偏置）。"""
    from hypothesis import strategies as st

    if family == "int":
        return st.one_of(
            st.integers(min_value=-10, max_value=10),
            st.sampled_from([0, 1, 2, 3, 5, 10, 16, 100]),
        )
    if family == "seq":
        return st.one_of(
            st.lists(st.integers(min_value=-5, max_value=10), max_size=6),
            st.sampled_from([[], [0], [1], [1, 1], [2, 1], [3, 1, 2], [1, 2, 3, 4, 5]]),
        )
    if family == "seq_seq":
        pair = st.tuples(st.integers(min_value=0, max_value=5), st.integers(min_value=0, max_value=10))
        return st.one_of(st.lists(pair, max_size=4), st.sampled_from([[], [(1, 2)], [(1, 2), (2, 3)]]))
    if family == "str":
        return st.one_of(
            st.text(alphabet="()[]{}abc", max_size=6),
            st.sampled_from(["", "()", "((", "a", "ab", "abc", "()[]"]),
        )
    if family == "dict":
        return st.one_of(
            st.dictionaries(st.tuples(st.integers(0, 3), st.integers(0, 3)), st.integers(1, 5), max_size=3),
            st.just({}),
        )
    # unknown / node：只用安全小值，避免误构造复杂对象
    return st.one_of(st.integers(min_value=-3, max_value=3), st.just([]), st.just(""))


def search_trigger_witnesses(
    *,
    buggy_code: str,
    gold_code: str,
    fn_name: str,
    module_name: str = "target",
    max_candidates: int = 120,
    seed: int = 42,
    probe_timeout: int = 10,
) -> TriggerSearchResult:
    """搜索"缺陷版与正确版行为不同"的输入（触发见证）。

    Args:
        buggy_code: 缺陷实现源码（任务 `instance_code`）。
        gold_code: 正确实现源码（gold 修复版）。
        fn_name: 目标函数名。
        module_name: 落盘模块名（测试与被测同名）。
        max_candidates: 候选输入总预算（安全阀）。
        seed: 搜索种子（可复现）。
        probe_timeout: 单次探针子进程超时。

    Returns:
        `TriggerSearchResult`；`witnesses` 中每条都已机械验证行为不同。
    """
    out = TriggerSearchResult()
    if not buggy_code.strip() or not gold_code.strip():
        out.not_available_reason = "no_code"
        return out
    try:
        tree = ast.parse(buggy_code)
    except SyntaxError:
        out.not_available_reason = "buggy_syntax_error"
        return out
    fn_node = next((n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == fn_name), None)
    if fn_node is None:
        out.not_available_reason = f"fn_not_found:{fn_name}"
        return out
    params = [a.arg for a in fn_node.args.args if a.arg not in ("self", "cls")]
    defaults = len(fn_node.args.defaults)
    required = params[: len(params) - defaults] if defaults else params
    families = [infer_param_family(p, buggy_code) for p in required]
    logger.info("SDTS：%s 参数 %s → 类型族 %s", fn_name, required, families)

    from hypothesis import HealthCheck, given, settings
    from hypothesis import strategies as st

    out.available = True
    strategies = [_strategy_for(f) for f in families]
    if not strategies:
        out.not_available_reason = "no_required_params"
        return out
    composite = st.tuples(*strategies) if len(strategies) > 1 else strategies[0].map(lambda v: (v,))

    seen: set[str] = set()

    @settings(
        max_examples=max_candidates,
        deadline=None,
        suppress_health_check=list(HealthCheck),
        derandomize=True,
    )
    @given(composite)
    def _explore(case: Any) -> None:
        args = list(case) if isinstance(case, tuple) else [case]
        key = repr(args)
        if key in seen:
            return
        seen.add(key)
        out.candidates_tried += 1
        b = _probe(buggy_code, module_name, fn_name, args, probe_timeout)
        if b is None:
            out.errors += 1
            return
        if b == "timeout":
            out.timeouts += 1
            return
        g = _probe(gold_code, module_name, fn_name, args, probe_timeout)
        if g is None:
            out.errors += 1
            return
        if g == "timeout":
            out.timeouts += 1
            return
        if b != g:
            out.witnesses.append(
                TriggerWitness(args=args, buggy_behavior=b, gold_behavior=g, note=f"family={families}")
            )

    try:
        _explore()
    except Exception:
        logger.warning("SDTS：hypothesis 搜索异常（已收集 %d 条）", len(out.witnesses), exc_info=True)
    if not out.witnesses:
        out.not_available_reason = "no_divergent_input_found"
    return out
