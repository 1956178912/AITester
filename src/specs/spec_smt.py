"""SpecSMT：规约前件的 SMT 见证生成层（G4，2026-10-05 优化批次·T2）。

背景（2026-10-05 系统审查 G4）：
    SpecIR v2 的确定性 oracle 依赖 boundaries 输入材料（无材料时回退
    字面量 0 绑定——已知可能违反前件）。规约前件本身是约束系统：
    ``x > 0 and x < 100`` 的可行输入空间可直接交给 SMT 求解器取模型，
    天然产出"满足前件"的合法输入（见证），且经 optimize 可取到
    边界极值（x=0+1 / x=99 一类）——比 LLM 举例与字面量兜底更系统，
    是"逻辑驱动"链路上第一条纯求解器通道（零 LLM 成本）。

能力边界（诚实口径，防过度宣称）：
    1. 只处理可被 spec_ir_v2.is_expression_clause + 白名单接受的子句，
       且翻译层只支持保守算子集（布尔 / 比较 / +-*/% / 常量 / 名称）；
       调用（len() 等）、幂、下标、属性 → 整体保守跳过（返回 []）；
    2. 后件引用结果变量 r，实现未知 → **不做**"实现是否满足后件"的判定
       （那需要被测函数实际语义，无实现判了也是空话）；但**做**"后件
       自身一致性"判定（把 r 视为自由变量，UNSAT = 后件自相矛盾，
       无论实现如何都无解）——该判定零实现语义依赖，见
       check_postcondition_consistency（R4 补反例环节）。本层前件侧做：
       - 前件 SAT 见证（合法输入样本）；
       - 前件数值目标 optimize（边界极值输入）；
       - 前件 UNSAT 检测（规约空洞化 finding，check_precondition_vacuity）；
    3. z3 未安装 / 超时 / unknown → 一律保守返回 [] / skipped
       （与 chromadb / hypothesis 的可选依赖降级惯例同口径）。

开关（模块自有，与 spec_ir_v2 的 _ENV_DSL 模式一致，默认关）：
    SPEC_SMT_ENABLE=false（默认）时 compile_spec_oracle 输出与历史
    逐字节一致；true 且 z3 可用时，oracle 产物追加
    ``test_specir_v2_smt_witness_*`` 参数化见证测试（前件断言 + 调用 +
    后件断言，与主 oracle 并列）。
"""

from __future__ import annotations

import ast
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_ENV_SMT = "SPEC_SMT_ENABLE"
# 求解器超时（毫秒）：SMT 求解在个别病态约束下可能不终止，必须可中断
_ENV_TIMEOUT_MS = "SPEC_SMT_TIMEOUT_MS"
# 单规约最多产出的见证数（sat 模型 + min/max 边界共享该上限）
_ENV_MAX_WITNESSES = "SPEC_SMT_MAX_WITNESSES"
# optimize 时对无界数值变量的显式包围盒（防 min/max 目标无界求解不终止）
_OPT_BOUND = 10**6

# 见证 Python 语义复核时注入的纯函数环境（与 spec_ir_v2._ALLOWED_CALL_NAMES
# 同一集合；子句经白名单后理论不含调用，此处双保险防 0 除 / 内建缺失）
_EVAL_SAFE_FUNCS: dict[str, Any] = {
    name: __builtins__[name] if isinstance(__builtins__, dict) else getattr(__builtins__, name)
    for name in ("len", "abs", "min", "max", "round", "float", "int", "str", "sorted", "any", "all")
}


def spec_smt_enabled() -> bool:
    """SMT 见证层开关（SPEC_SMT_ENABLE=true 时启用，默认 false）。"""
    return os.getenv(_ENV_SMT, "false").strip().lower() in ("true", "1", "on")


def smt_available() -> bool:
    """z3-solver 是否已安装（可选依赖 [formal] extra，缺失时本层整体降级）。"""
    try:
        import z3  # noqa: F401  （仅探测可导入性，不触发求解器初始化）

        return True
    except ImportError:
        return False


def _smt_timeout_ms() -> int:
    """求解器超时毫秒数（SPEC_SMT_TIMEOUT_MS，默认 2000，下限 100 上限 30000）。"""
    try:
        return max(100, min(30000, int(os.getenv(_ENV_TIMEOUT_MS, "2000"))))
    except ValueError:
        return 2000


def _max_witnesses() -> int:
    """单规约见证数上限（SPEC_SMT_MAX_WITNESSES，默认 3，下限 1 上限 10）。"""
    try:
        return max(1, min(10, int(os.getenv(_ENV_MAX_WITNESSES, "3"))))
    except ValueError:
        return 3


class _Untranslatable(Exception):
    """子句含保守算子集之外的构造（调用 / 幂 / 下标 / …）——整体跳过。"""


# ─── 0. 受限 AST 求值器（S8，2026-10-08 R3：彻底消除裸 eval）────────────────
# 背景：见证的 Python 语义复核原先用 eval(clause, {"__builtins__": {}}, env)
# 求值白名单子句。白名单（spec_ir_v2._whitelist_check）已拦截危险调用/属性
# 逃逸，翻译层（_translate）进一步把 usable 限制到 常量/名称/布尔/一元/比较/
# 二元 子集，理论上 eval 面无注入；但"仍有 eval 存在"这一事实本身是审计噪音
# （bandit S307 noqa），且未来白名单/翻译层放宽时该面可能被重新打开。
# 此处以受限 AST 求值器替代裸 eval：只递归支持白名单节点类型，任何其他节点
# /异常一律抛 _Untranslatable（保守丢弃见证，与"宁可无见证，不产坏约束"同口径）。

# 二元运算符 → Python 语义（与 _translate 支持的算子集对齐，Pow/FloorDiv 为
# 防御性补齐：翻译层当前不产 Pow/FloorDiv，但求值器独立存在，宁多不缺口）
_BINOP_FUNCS: dict[type[ast.operator], Any] = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.Mod: lambda a, b: a % b,
    ast.Pow: lambda a, b: a**b,
    ast.FloorDiv: lambda a, b: a // b,
}

# 比较运算符 → Python 语义（In/NotIn/Is/IsNot 不支持 → 保守拒绝）
_CMPOP_FUNCS: dict[type[ast.cmpop], Any] = {
    ast.Eq: lambda a, b: a == b,
    ast.NotEq: lambda a, b: a != b,
    ast.Lt: lambda a, b: a < b,
    ast.LtE: lambda a, b: a <= b,
    ast.Gt: lambda a, b: a > b,
    ast.GtE: lambda a, b: a >= b,
}


def _safe_eval(node: ast.AST, env: dict[str, Any]) -> Any:
    """受限 AST 求值器（白名单节点子集，零 eval/exec）。

    支持：Constant / Name / BoolOp(And,Or) / UnaryOp(Not,USub,UAdd) /
    Compare(Eq,NotEq,Lt,LtE,Gt,GtE) / BinOp(Add,Sub,Mult,Div,Mod,Pow,
    FloorDiv) / Call（仅 _EVAL_SAFE_FUNCS 白名单内名称、无关键字实参）。
    其余节点（Attribute / Subscript / Lambda / 推导式 / f-string / …）一律
    抛 _Untranslatable → 见证保守丢弃。Name 仅在 env（见证 inputs）内解析，
    不注入 __builtins__，无 import/exec/属性/下标逃逸面。
    """
    if isinstance(node, ast.Expr):
        # 防御性：eval 模式 body 理论上不包 Expr，但若上游传入 exec 形态
        # 子树则剥壳继续（与 _infer_sorts/_translate 的 Expr 分支同口径）
        return _safe_eval(node.value, env)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id not in env:
            raise _Untranslatable
        return env[node.id]
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            result: Any = True
            for value in node.values:
                result = _safe_eval(value, env)
                if not result:
                    return result
            return result
        if isinstance(node.op, ast.Or):
            for value in node.values:
                result = _safe_eval(value, env)
                if result:
                    return result
            return result
        raise _Untranslatable
    if isinstance(node, ast.UnaryOp):
        operand = _safe_eval(node.operand, env)
        if isinstance(node.op, ast.Not):
            return not operand
        if isinstance(node.op, ast.USub):
            return -operand
        if isinstance(node.op, ast.UAdd):
            return +operand
        raise _Untranslatable
    if isinstance(node, ast.Compare):
        left = _safe_eval(node.left, env)
        for op, comp in zip(node.ops, node.comparators, strict=True):
            right = _safe_eval(comp, env)
            fn = _CMPOP_FUNCS.get(type(op))
            if fn is None:
                raise _Untranslatable
            if not fn(left, right):
                return False
            left = right
        return True
    if isinstance(node, ast.BinOp):
        left = _safe_eval(node.left, env)
        right = _safe_eval(node.right, env)
        fn = _BINOP_FUNCS.get(type(node.op))
        if fn is None:
            raise _Untranslatable
        return fn(left, right)
    if isinstance(node, ast.Call):
        name = node.func.id if isinstance(node.func, ast.Name) else None
        if name is None or name not in _EVAL_SAFE_FUNCS:
            raise _Untranslatable
        if node.keywords:
            raise _Untranslatable
        args = [_safe_eval(a, env) for a in node.args]
        return _EVAL_SAFE_FUNCS[name](*args)
    raise _Untranslatable


def _safe_eval_clause(clause: str, env: dict[str, Any]) -> Any:
    """解析并受限求值单个子句（失败抛 _Untranslatable）。"""
    tree = ast.parse(clause, mode="eval")
    return _safe_eval(tree.body, env)


# ─── 1. 排序推断（名称 → z3 Int/Real/Bool，冲突即不可翻译）───────────────────


def _infer_sorts(clauses: list[str], param_names: frozenset[str]) -> dict[str, str] | None:
    """从子句的用字上下文推断每个输入名的 SMT 排序（两遍口径）。

    第一遍标记布尔用字：bare 名称出现在布尔上下文（BoolOp/Not 操作数）、
    或作为与布尔常量比较的左侧名称 → Bool（先标记后默认，避免
    ``flag == True`` 被"非布尔上下文默认 Int"抢先误标导致 Bool×Int 冲突）。
    第二遍数值默认：Int 起步，浮点上下文（与 float 常量比较 / 除法操作数）
    升 Real。合并冲突（Bool × 数值）→ None（整体保守跳过）。
    出现 param_names 之外的自由名（如前件里误写 r）→ None。
    """
    bool_names: set[str] = set()

    def _mark_bool(node: ast.AST, bool_ctx: bool) -> None:
        if isinstance(node, ast.Name):
            if bool_ctx and node.id in param_names:
                bool_names.add(node.id)
        elif isinstance(node, ast.BoolOp):
            for operand in node.values:
                _mark_bool(operand, True)
        elif isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.Not):
                _mark_bool(node.operand, True)
            elif isinstance(node.op, ast.USub):
                _mark_bool(node.operand, False)
        elif isinstance(node, ast.Compare):
            _mark_bool(node.left, False)
            for idx, comp in enumerate(node.comparators):
                _mark_bool(comp, False)
                left_operand = node.left if idx == 0 else node.comparators[idx - 1]
                if (
                    isinstance(comp, ast.Constant)
                    and isinstance(comp.value, bool)
                    and isinstance(left_operand, ast.Name)
                    and left_operand.id in param_names
                ):
                    bool_names.add(left_operand.id)
        elif isinstance(node, ast.BinOp):
            _mark_bool(node.left, False)
            _mark_bool(node.right, False)
        elif isinstance(node, ast.Expr):
            _mark_bool(node.value, bool_ctx)

    sorts: dict[str, str] = {}

    def _meet(name: str, want: str) -> bool:
        have = sorts.get(name)
        if have is None:
            sorts[name] = want
            return True
        if have == want:
            return True
        if {have, want} == {"Int", "Real"}:
            sorts[name] = "Real"
            return True
        return False  # Bool × 数值冲突 → 整体不可翻译

    def _walk(node: ast.AST) -> bool:
        if isinstance(node, ast.Name):
            if node.id not in param_names:
                return False
            return _meet(node.id, "Bool" if node.id in bool_names else "Int")
        if isinstance(node, ast.Constant):
            return True
        if isinstance(node, ast.BoolOp):
            return all(_walk(o) for o in node.values)
        if isinstance(node, ast.UnaryOp):
            return _walk(node.operand)
        if isinstance(node, ast.Compare):
            if not _walk(node.left):
                return False
            ok = all(_walk(c) for c in node.comparators)
            # 与浮点常量比较 → 左侧名称升 Real（z3 Int/Real 混排需显式收敛）
            lefts = [node.left, *list(node.comparators[:-1])]
            for left_operand, right_operand in zip(lefts, node.comparators, strict=True):
                if (
                    isinstance(right_operand, ast.Constant)
                    and isinstance(right_operand.value, float)
                    and isinstance(left_operand, ast.Name)
                    and left_operand.id in param_names
                    and not _meet(left_operand.id, "Real")
                ):
                    return False
            return ok
        if isinstance(node, ast.BinOp):
            left_ok = _walk(node.left)
            right_ok = _walk(node.right)
            if not left_ok or not right_ok:
                return False
            if isinstance(node.op, ast.Div):
                for side in (node.left, node.right):
                    if isinstance(side, ast.Name) and side.id in param_names and not _meet(side.id, "Real"):
                        return False
            return True
        if isinstance(node, ast.Expr):
            return _walk(node.value)
        raise _Untranslatable

    try:
        for clause in clauses:
            tree = ast.parse(clause, mode="eval")
            _mark_bool(tree.body, True)
        for clause in clauses:
            tree = ast.parse(clause, mode="eval")
            if not _walk(tree.body):
                return None
    except _Untranslatable:
        return None
    except (SyntaxError, ValueError):
        return None
    return sorts


# ─── 2. AST → z3 表达式翻译（保守算子集）─────────────────────────────────────


def _translate(node: ast.AST, sorts: dict[str, str], z3: Any) -> Any:
    """把白名单 AST 节点翻译为 z3 表达式；越界构造抛 _Untranslatable。"""
    if isinstance(node, ast.Constant):
        v = node.value
        if isinstance(v, bool):
            return z3.BoolVal(v)
        if isinstance(v, int):
            return z3.IntVal(v)
        if isinstance(v, float):
            return z3.RealVal(str(v))
        raise _Untranslatable
    if isinstance(node, ast.Name):
        sort = sorts.get(node.id)
        if sort == "Int":
            return z3.Int(node.id)
        if sort == "Real":
            return z3.Real(node.id)
        if sort == "Bool":
            return z3.Bool(node.id)
        raise _Untranslatable
    if isinstance(node, ast.BoolOp):
        vals = [_translate(o, sorts, z3) for o in node.values]
        return z3.And(*vals) if isinstance(node.op, ast.And) else z3.Or(*vals)
    if isinstance(node, ast.UnaryOp):
        inner = _translate(node.operand, sorts, z3)
        if isinstance(node.op, ast.Not):
            return z3.Not(inner)
        if isinstance(node.op, ast.USub):
            return -inner
        raise _Untranslatable
    if isinstance(node, ast.Compare):
        left = _translate(node.left, sorts, z3)
        parts: list[Any] = []
        for op, comp in zip(node.ops, node.comparators, strict=True):
            right = _translate(comp, sorts, z3)
            if isinstance(op, ast.Eq):
                parts.append(left == right)
            elif isinstance(op, ast.NotEq):
                parts.append(left != right)
            elif isinstance(op, ast.Lt):
                parts.append(left < right)
            elif isinstance(op, ast.LtE):
                parts.append(left <= right)
            elif isinstance(op, ast.Gt):
                parts.append(left > right)
            elif isinstance(op, ast.GtE):
                parts.append(left >= right)
            else:
                raise _Untranslatable
            left = right
        return z3.And(*parts) if len(parts) > 1 else parts[0]
    if isinstance(node, ast.BinOp):
        left = _translate(node.left, sorts, z3)
        right = _translate(node.right, sorts, z3)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right
        if isinstance(node.op, ast.Mod):
            return left % right
        raise _Untranslatable
    raise _Untranslatable


def _model_value(z3: Any, expr: Any) -> int | float | bool:
    """把 z3 模型值转换为 Python 标量（Int→int，Real→int/float，Bool→bool）。"""
    ev = expr
    if z3.is_int_value(ev):
        return ev.as_long()
    if z3.is_rational_value(ev):
        num = ev.numerator_as_long()
        den = ev.denominator_as_long()
        return num if den == 1 else num / den
    if z3.is_true(ev):
        return True
    if z3.is_false(ev):
        return False
    raise _Untranslatable


def _collect_pre_constraints(
    spec: dict[str, Any] | None,
    signature_params: list[str] | None,
    z3: Any,
) -> tuple[list[Any], dict[str, str], list[str]] | None:
    """前件子句 → z3 约束列表 + 排序表；任一保守条件不满足 → None。"""
    if not spec or signature_params is None or not signature_params:
        return None
    # 复用 v2 的可编译判定（含白名单），保证两层数据源同口径
    from src.specs.spec_ir_v2 import _whitelist_check, is_expression_clause

    pre = [c for c in (spec.get("preconditions") or []) if isinstance(c, str) and c.strip()]
    usable: list[str] = []
    for clause in pre:
        if not is_expression_clause(clause) or _whitelist_check(clause):
            continue
        usable.append(clause.strip())
    if not usable:
        return None
    params = frozenset(signature_params)
    sorts = _infer_sorts(usable, params)
    if sorts is None or not sorts:
        return None
    constraints: list[Any] = []
    usable_bool: list[str] = []
    try:
        for clause in usable:
            tree = ast.parse(clause, mode="eval")
            translated = _translate(tree.body, sorts, z3)
            # S11 配套（2026-10-08）：is_expression_clause 放宽后，算术子句
            # （如 "x + 1"）也会通过——_translate 对 BinOp 返回算术表达式
            # （非 Bool sort），solver.add 会抛 Z3Exception。前件 SAT 见证
            # 只关心 Bool 前件（比较/布尔/裸名），非 Bool 子句跳过
            # （保守：不产坏约束，与"宁可无见证"口径一致）；同步过滤
            # usable，使 clauses 字段与约束对齐（防 Python 复核对算术
            # 子句求值产生假见证）。
            if not z3.is_bool(translated):
                continue
            constraints.append(translated)
            usable_bool.append(clause)
    except _Untranslatable:
        return None
    except Exception:
        # z3 翻译期类型异常（如 Bool×Int 混排比较抛 Z3Exception）→ 整体
        # 保守跳过（不产出半翻译约束；与"宁可无见证，不产坏约束"口径一致）
        logger.debug("SpecSMT 子句翻译失败（保守跳过该规约）", exc_info=True)
        return None
    if not constraints:
        # 全部子句均为非 Bool（如纯算术表达式）→ 无有效前件约束
        return None
    return constraints, sorts, usable_bool


def generate_spec_witnesses(
    spec: dict[str, Any] | None,
    signature_params: list[str] | None,
    max_witnesses: int | None = None,
) -> list[dict[str, Any]]:
    """从规约前件生成 SMT 见证输入（sat 模型 + 数值边界极值）。

    Returns:
        [{"inputs": {参数名: Python 标量}, "kind": "sat"|"boundary_min"|"boundary_max",
          "objective": 名称|None, "clauses": [前件子句]}]；
        任一保守条件不满足（无前件 / 不可翻译 / z3 缺失 / 超时 / unsat）→ []。
    """
    if not smt_available():
        return []
    import z3

    bundle = _collect_pre_constraints(spec, signature_params, z3)
    if bundle is None:
        return []
    constraints, sorts, usable = bundle
    cap = max_witnesses if max_witnesses is not None else _max_witnesses()
    timeout = _smt_timeout_ms()
    seen_keys: set[str] = set()
    witnesses: list[dict[str, Any]] = []
    # 名称 → z3 变量（sat 与 optimize 两条路径共用的模型提取锚点）
    sorts_expr: dict[str, Any] = {}
    for name, sort in sorts.items():
        sorts_expr[name] = z3.Int(name) if sort == "Int" else (z3.Real(name) if sort == "Real" else z3.Bool(name))

    def _extract(model: Any, kind: str, objective: str | None) -> dict[str, Any] | None:
        inputs: dict[str, int | float | bool] = {}
        try:
            for name in sorts:
                inputs[name] = _model_value(z3, model.eval(sorts_expr[name], model_completion=True))
        except _Untranslatable:
            return None
        # Python 语义复核：z3 见证必须在 **Python** 下满足全部前件子句
        # （z3 的 Bool/Int 隐式收敛、除法语义与 Python 存在分歧；复核失败
        # 的见证会让编译产物在执行期 TypeError/断言失败 → 假检出，直接丢弃）。
        # 子句已过 spec_ir_v2 白名单（无调用/属性逃逸）+ 翻译层（无 Call/
        # 下标/属性），此处以受限 AST 求值器求值（零 eval/exec，见
        # _safe_eval_clause）。求值顺序：ast.literal_eval 快速路径（纯字面量
        # 子句如 True / 1 / "x" 不经求值器）→ 非字面量落 _safe_eval_clause
        # （S8 彻底消除裸 eval；R9 历史的"受限 eval + debug 告警"口径升级）。
        safe_env: dict[str, Any] = dict(inputs)
        try:
            for clause in usable:
                try:
                    value = ast.literal_eval(clause)
                except (ValueError, SyntaxError):
                    # 非字面量（比较 / 运算）：受限 AST 求值器兜底（白名单
                    # 节点子集，越界抛 _Untranslatable → 见证保守丢弃）
                    value = _safe_eval_clause(clause, safe_env)
                if not value:
                    return None
        except _Untranslatable:
            return None
        except Exception:
            return None
        key = repr(sorted(inputs.items()))
        if key in seen_keys:
            return None
        seen_keys.add(key)
        return {"inputs": inputs, "kind": kind, "objective": objective, "clauses": usable}

    # ① SAT 见证：直接取可行模型
    solver = z3.Solver()
    solver.set("timeout", timeout)
    solver.add(constraints)
    if solver.check() == z3.sat:
        witness = _extract(solver.model(), "sat", None)
        if witness is not None:
            witnesses.append(witness)

    # ② 边界极值：首个数值变量做 min/max（显式包围盒防无界目标）
    numeric = [n for n, s in sorts.items() if s in ("Int", "Real")]
    if numeric:
        objective = numeric[0]
        var = sorts_expr[objective]
        for kind, meth in (("boundary_min", "minimize"), ("boundary_max", "maximize")):
            if len(witnesses) >= cap:
                break
            try:
                opt = z3.Optimize()
                opt.set("timeout", timeout)
                opt.add(constraints)
                opt.add(var >= -_OPT_BOUND, var <= _OPT_BOUND)
                getattr(opt, meth)(var)
                if opt.check() == z3.sat:
                    witness = _extract(opt.model(), kind, objective)
                    if witness is not None:
                        witnesses.append(witness)
            except Exception:
                # Optimize 参数/求解器版本兼容性问题 → 保守跳过该边界见证
                # （sat 见证不受影响；不因求解器附属能力失败而中断 oracle 编译）
                logger.debug("SpecSMT optimize %s 失败（保守跳过）", kind, exc_info=True)

    return witnesses[:cap]


def check_precondition_vacuity(
    spec: dict[str, Any] | None,
    signature_params: list[str] | None,
) -> dict[str, Any]:
    """前件可满足性检测（UNSAT = 规约空洞：任何输入都不合法）。

    Returns:
        {"status": "sat"|"unsat"|"unknown"|"skipped", "clauses": 前件子句数}；
        z3 缺失 / 无可翻译前件 → skipped（保守，不产出伪结论）。
    """
    if not smt_available():
        return {"status": "skipped", "clauses": 0}
    import z3

    bundle = _collect_pre_constraints(spec, signature_params, z3)
    if bundle is None:
        return {"status": "skipped", "clauses": 0}
    constraints, _sorts, usable = bundle
    solver = z3.Solver()
    solver.set("timeout", _smt_timeout_ms())
    solver.add(constraints)
    result = solver.check()
    status = "sat" if result == z3.sat else ("unsat" if result == z3.unsat else "unknown")
    if status == "unsat":
        logger.warning("SpecSMT：规约前件 UNSAT（空洞规约），clauses=%s", usable)
    return {"status": status, "clauses": len(usable)}


# ─── 4. 后件一致性检测（R4 补反例环节，2026-10-09）────────────────────────
# 背景（2026-10-09 系统评审 R4·S1）：SpecSMT 此前只做**前件** SAT/UNSAT 判定，
# 后件（postconditions / invariants）因"引用结果变量 r、实现未知"被明确
# 排除在求解之外（本模块 docstring 第 15-16 行）。但"后件**自身**可满足性"
# （把 r 视为自由变量）并不依赖实现语义——它判定的是"后件约束系统是否
# 自洽"：若后件同时要求 ``r > 0`` 与 ``r < 0``，则**无论被测实现如何**都
# 不存在能满足全部后件的返回值，即规约自相矛盾（LLM 形式化时的幻觉/语义
# 漂移）。这正是"反例驱动精化"（Balestra ICST2026 / SpecPylot）的**求解器
# 起点**：先由 SMT 判定矛盾，再由上层把矛盾子句回灌 LLM 修正契约。
#
# 能力边界（诚实口径，与既有前件层对齐）：
#   1. 只处理可被 spec_ir_v2 白名单接受的后件子句，翻译层复用同一保守
#      算子集；调用/幂/下标/属性 → 整体保守跳过；
#   2. 只判定"后件自身一致性"（r 自由），**不**判定"实现是否满足后件"
#      （那需要被测函数的实际语义，本层无实现 → 不做，防过度宣称）；
#   3. z3 未安装 / 超时 / unknown → 保守 skipped（同前件口径）。


def _collect_post_constraints(
    spec: dict[str, Any] | None,
    signature_params: list[str] | None,
    z3: Any,
) -> tuple[list[Any], dict[str, str], list[str]] | None:
    """后件子句（post + invariant）→ z3 约束列表 + 排序表；r 纳入自由变量。

    与前件层 `_collect_pre_constraints` 的唯一差异：变量域 = signature_params
    ∪ {"r"}（结果变量 r 作为自由变量参与排序推断与翻译）。任一保守条件
    不满足（无后件 / 不可翻译 / 白名单违例）→ None。
    """
    if not spec or signature_params is None or not signature_params:
        return None
    from src.specs.spec_ir_v2 import _whitelist_check, is_expression_clause

    post = [c for c in (spec.get("postconditions") or []) if isinstance(c, str) and c.strip()]
    inv = [c for c in (spec.get("invariants") or []) if isinstance(c, str) and c.strip()]
    usable: list[str] = []
    for clause in post + inv:
        if not is_expression_clause(clause) or _whitelist_check(clause):
            continue
        usable.append(clause.strip())
    if not usable:
        return None
    # r 作为结果变量纳入自由变量域（后件子句引用 r 是合法语义，非笔误）
    params = frozenset(signature_params) | {"r"}
    sorts = _infer_sorts(usable, params)
    if sorts is None or not sorts:
        return None
    constraints: list[Any] = []
    usable_bool: list[str] = []
    try:
        for clause in usable:
            tree = ast.parse(clause, mode="eval")
            translated = _translate(tree.body, sorts, z3)
            if not z3.is_bool(translated):
                continue  # 非 Bool 后件子句跳过（与前件层同口径）
            constraints.append(translated)
            usable_bool.append(clause)
    except _Untranslatable:
        return None
    except Exception:
        logger.debug("SpecSMT 后件子句翻译失败（保守跳过该规约）", exc_info=True)
        return None
    if not constraints:
        return None
    return constraints, sorts, usable_bool


def check_postcondition_consistency(
    spec: dict[str, Any] | None,
    signature_params: list[str] | None,
) -> dict[str, Any]:
    """后件自洽性检测（UNSAT = 后件约束系统自相矛盾）。

    语义：把后件（postconditions + invariants）的可编译子句视为关于
    ``{signature_params} ∪ {r}`` 的约束系统；``r`` 为自由结果变量。判定：
    - sat：存在某个 (inputs, r) 组合满足全部后件 → 规约自洽；
    - unsat：任何 (inputs, r) 都无法同时满足全部后件 → 规约自相矛盾
      （无论被测实现如何都无解），属"逻辑驱动"能发现的真实规约缺陷，
      上层可据此把矛盾子句回灌 LLM 精化契约；
    - unknown / skipped：求解器超时 / z3 缺失 / 无后件 / 不可翻译。

    Returns:
        {"status": "sat"|"unsat"|"unknown"|"skipped", "clauses": 后件子句数,
         "variables": [变量名列表]}；z3 缺失 / 无可翻译后件 → skipped。
    """
    if not smt_available():
        return {"status": "skipped", "clauses": 0, "variables": []}
    import z3

    bundle = _collect_post_constraints(spec, signature_params, z3)
    if bundle is None:
        return {"status": "skipped", "clauses": 0, "variables": []}
    constraints, sorts, usable = bundle
    solver = z3.Solver()
    solver.set("timeout", _smt_timeout_ms())
    solver.add(constraints)
    result = solver.check()
    status = "sat" if result == z3.sat else ("unsat" if result == z3.unsat else "unknown")
    if status == "unsat":
        logger.warning(
            "SpecSMT：规约后件 UNSAT（自相矛盾，无论实现如何都无解），clauses=%s",
            usable,
        )
    return {"status": status, "clauses": len(usable), "variables": sorted(sorts)}


def check_spec_consistency(
    spec: dict[str, Any] | None,
    signature_params: list[str] | None,
) -> dict[str, Any]:
    """规约一致性联合检测（前件空洞 + 后件矛盾两 finding 汇总）。

    这是"逻辑驱动"补反例环节的统一入口：一次调用产出前件可满足性与
    后件自洽性两个独立判定，供上层（报告层 / 精化循环）聚合消费。
    Returns:
        {"precondition": {...}, "postcondition": {...}}——两个子结果分别
        遵循 check_precondition_vacuity / check_postcondition_consistency
        的返回契约。
    """
    return {
        "precondition": check_precondition_vacuity(spec, signature_params),
        "postcondition": check_postcondition_consistency(spec, signature_params),
    }


__all__ = [
    "check_postcondition_consistency",
    "check_precondition_vacuity",
    "check_spec_consistency",
    "generate_spec_witnesses",
    "smt_available",
    "spec_smt_enabled",
]
