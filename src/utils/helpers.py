"""
通用工具模块：提供跨模块的公共工具函数。

本模块集中管理被多个子模块重复使用的工具函数，遵循 DRY 原则：
- extract_code_block(): 从 LLM 输出中提取代码块（支持多种格式）
- extract_json_object(): 从文本中提取 JSON 对象（含括号平衡法）

使用示例：
    from src.utils.helpers import extract_code_block, extract_json_object
"""

from __future__ import annotations

import ast
import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# 预编译正则表达式（避免重复编译开销）
# 匹配 ```python ... ``` 代码块（带语言标记）
_CODE_BLOCK_PYTHON_PATTERN = re.compile(r"```python\s*\n(.*?)\n\s*```", re.DOTALL)
# 匹配 ``` ... ``` 通用代码块
_CODE_BLOCK_PATTERN = re.compile(r"```(?:python)?\s*\n(.*?)\n\s*```", re.DOTALL)
# 匹配最内层无嵌套的 {...} JSON 对象
_JSON_LEAF_PATTERN = re.compile(r"\{[^{}]*\}")
# 预编译 JSON 清理正则（extract_json_object 热路径：LLM 响应可能很长，
# 每次调用重复编译 re.sub 模式浪费；re 内部缓存有限，显式编译最稳妥）。
#
# K 轮（2026-10-17 属性模糊测试反例）修复：此前两个模式**无条件删除全文
# 任意位置的三连反引号**（`_JSON_BACKTICK_STRIP_PATTERN = r"```"`），会把
# 合法 JSON **字符串内容里**的反引号一并删掉——`{"cmd": "```bash"}` 被静默
# 改写为 `{"cmd": "bash"}`、`{"```": null}` 变成 `{"": null}`：解析成功但
# 内容错误，比解析失败更危险（下游拿到的补丁/命令被篡改且无任何告警）。
# 反例来源：`tests/test_helpers_json_property.py` 的围栏直通性质（hypothesis
# 生成 `{'```': None}` 后该性质失败）。
# 修复口径：① 围栏只在**行首**剥离（markdown 围栏的语法位置），不触碰字符串
# 内容；② 解析主路径新增"原始文本先行"快路径（`_try_parse_raw_json`）——
# 合法 JSON 在未清洗文本上直接解析，内容零改写；清洗后的文本只作为修复档
# 的兜底输入。行首剥离仍是无损的：围栏本身不是 JSON 令牌，剥离只是让
# 修复档的括号平衡切片不被围栏噪声干扰。
_JSON_FENCE_STRIP_PATTERN = re.compile(r"(?m)^[ \t]*```[ \t]*(?:json)?[ \t]*\r?\n?")
# 行首裸围栏（无语言标记）：语义上区分"裸围栏行"，与上一模式叠加为幂等清洗
# （上一模式已覆盖该形态；保留独立常量以免破坏历史调用语义与测试引用）。
_JSON_BACKTICK_STRIP_PATTERN = re.compile(r"(?m)^[ \t]*```[ \t]*\r?\n?")
# OMS（M10 可观测性，2026-10-14 EMSE 批次四）：叶子回退静默片段检测。
# 背景：extract_json_object 的叶子降级档（正则取最内层无嵌套 {...}）在
# "括号平衡法失败 + 顶层对象残缺"时会**静默返回一个错误片段**（如
# {'items': ...}）——下游（Planner M10 路径）把"缺关键字段"归因为
# "LLM 未输出 logic_analysis"，实为提取器缺陷（LLM 输出了完整正确 JSON，
# 只是解析链回退到了错的片段）。本模块以函数级哨兵
# `_LEAF_FALLBACK_ACTIVE`（线程无关：Python GIL 下 extract_json_object
# 为同步调用，无并发）记录"本次调用是否发生了叶子回退且返回的是
# 最内层片段"，供调用方（planner/debugger）读取后显式告警，消除误诊。
# 纪律：哨兵必须在 extract_json_object 返回前复位（finally 语义），
# 调用方在**同一调用栈、同线程**内立即读取；跨线程/缓存回放路径
# 不得依赖哨兵（历史缓存响应不经 extract_json_object，哨兵恒 False）。
_LEAF_FALLBACK_ACTIVE: bool = False
# "python:" 前缀剥离（extract_code_block 热路径：LLM 每次输出的代码提取都会走，
# 显式预编译避免每次调用重复编译）
_PYTHON_PREFIX_STRIP_PATTERN = re.compile(r"^python(?!\w)\s*:?\s*\n?", re.IGNORECASE)


def extract_code_block(text: str, language: str | None = None) -> str:
    """
    从 LLM 输出中提取代码块。

    支持四种格式（按优先级）：
    1. ```<language> ... ```（按调用方期望语言精确匹配的代码块）
    2. ```python ... ```（带语言标记的 markdown 代码块）
    3. ``` ... ```（通用 markdown 代码块）
    4. python: ... 前缀格式（某些模型输出不带反引号）
    5. 纯文本（无标记时直接返回）

    Args:
        text: LLM 返回的包含代码的原始文本。
        language: 期望的代码语言（如 "python"），None 表示不限制。
            O35（2026-09-30 全面审查 P3）：此前该参数**完全未被读取**（docstring
            承诺"期望的代码语言"但函数体从不引用），language="javascript" 的
            调用方会拿到第一个 ```python 块。现按 language 优先精确匹配
            对应标记的块；未命中时回退到原优先级链（对现有 python 调用方
            行为不变：language="python" 时第 1 步与原第 1 步等价）。

    Returns:
        提取出的代码字符串（已去除 markdown 包裹和首尾空白）。
    """
    # 0. 按调用方期望语言精确匹配（language 给定且非 python 时的新增前置档；
    #    language="python" 命中即等价于下方原第 1 步，不改变既有行为）
    if language:
        lang_pat = re.compile(rf"```{re.escape(language)}\s*\n(.*?)\n\s*```", re.DOTALL | re.IGNORECASE)
        match = lang_pat.search(text)
        if match:
            return match.group(1).strip()

    # 尝试带语言标记的格式：```python ... ```（优先匹配）
    match = _CODE_BLOCK_PYTHON_PATTERN.search(text)
    if match:
        return match.group(1).strip()

    # 尝试通用 markdown 格式：``` ... ```
    match = _CODE_BLOCK_PATTERN.search(text)
    if match:
        return match.group(1).strip()

    # 尝试 "python" 前缀格式（某些模型输出不带反引号，如 "python:\n..."）。
    # 关键：仅当 "python" 是独立"标签"（后接 冒号/换行/空白/行尾，而非标识符续
    # 字符）时才剥离，否则会误吞以 python 开头的合法代码行（如 python_path = 3
    # 会被剥成 _path = 3）——用 (?!\w) 负向后瞻排除"python 是更长标识符一部分"。
    # （0.7 债务项 0.1：仅剥离首个前缀；LLM 输出中多重 python: 包裹为
    # 既有限制，本次不做扩展以保持行为口径不变）
    stripped = text.strip()
    if stripped.lower().startswith("python"):
        stripped = _PYTHON_PREFIX_STRIP_PATTERN.sub("", stripped)
        return stripped.strip()

    # 返回原始文本（strip 空白）
    return text.strip()


def _repair_json_text(json_str: str) -> str:
    """D1 修复层（2026-10-09 审查报告 §11.1b D1）：JSON 语法级保守修复。

    背景（实测证据）：对 4,041 个 LLM 缓存响应做结构裁决，**188/621（30%）**
    的 Planner 形态响应无法 ``json.loads``，错误分布为：
    - 94 例 ``Expecting ',' delimiter`` —— LLM 在 JSON 值里写 **Python 表达式**
      （如 ``"input_args":{"key":"a"*10000}``、``inf``）；
    - 57 例 ``Extra data`` —— **多个 JSON 对象背靠背拼接**；
    - 35 例 ``Expecting value`` —— **未加引号的 Python 字面量**
      （``"expected_output":None``、未经转义的裸标识符）。
    该失败经 `nodes.py:269` 的 ``except json.JSONDecodeError`` 走到
    ``_get_default_test_plan``（test_cases=[]），使 Generator 在约 30% 任务上
    **拿不到任何测试计划**——这是 never-red 通道（worker 报告 86/240）的
    主因候选（D1）。

    修复策略（**保守、只做语法级、绝不改语义**）：
    1. 移除尾随逗号（``,]`` / ``,}``）；
    2. 未加引号的 Python 字面量 → JSON 字面量（``: None`` → ``: null`` 等，
       仅在**值位置**，且用负向后瞻避免命中字符串内部）；
    3. 若整体解析失败但含**多个顶层对象**（{...}{...}），用括号平衡法
       取**第一个完整对象**（LLM 常把多个任务的计划连写）。

    不做的事（刻意）：不尝试把 ``"a"*10000`` 这类**表达式**求值为字面量——
    那需要 eval，既有注入面又可能把 LLM 的表达式意图猜错；此类样本保持
    原样交给既有降级链（诚实失败优于静默错误修复）。

    Args:
        json_str: 已做 markdown 剥离/括号平衡提取后的候选 JSON 文本。

    Returns:
        修复后的文本（可能仍不可解析，由调用方继续降级）。
    """
    s = json_str
    # 1) 尾随逗号
    s = re.sub(r",(\s*[\]}])", r"\1", s)
    # 2) 值位置的未加引号 Python 字面量（负向后瞻排除字符串内部：
    #    仅当前置字符是 : [ , 或空白时才替换）
    for py_lit, json_lit in (
        ("None", "null"),
        ("True", "true"),
        ("False", "false"),
        ("Infinity", "1e999"),
        ("NaN", "null"),
    ):
        s = re.sub(rf"(?<=[:\s,\[]){py_lit}(?=\s*[,}}\]])", json_lit, s)
    return s


def _first_balanced_object(text: str) -> str | None:
    """取文本中**第一个**括号平衡的 ``{...}`` 片段（应对多对象拼接）。"""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _quote_tuple_keys_once(s: str) -> tuple[str, bool]:
    """把 JSON 对象**键位置**的 Python 元组字面量加引号。

    D1 残余主因之一（实测）：LLM 用元组作字典键，如
    ``{"length_by_edge":{(0,1):5,(1,0):5}}`` —— Python 合法、JSON 非法
    （解析器报 ``Expecting property name enclosed in double quotes``）。
    转换为 ``"（0,1)":5``（键变异为字符串）保留测试输入的**意图**（一组
    带标签的边），且不改变值的类型。

    仅在 ``{``/``,`` 之后（键位置）匹配，**不触碰值位置**——故形如
    ``{"desc":"(0,1) 是边"}`` 的字符串不会被误改。
    含字符串字面量的元组（``("a",1):2``）刻意不处理（需完整词法分析，
    风险高于收益）。

    **字符串感知（关键正确性）**：必须跳过 JSON 字符串**内部**的 ``{``/``,``
    ——实测反例：``"n=1：单节点，返回 {"(0,0)": 0}"``（把 JSON 片段写进描述
    文本），若不跳过就会被误改并把**本来可解析**的响应改坏。故先按字符串
    边界切分，仅在字符串**之外**做替换。

    Returns:
        (新文本, 是否发生替换) —— 布尔值供"是否需要再试"的判断使用。
    """
    pat = re.compile(r"([{,]\s*)\((\s*-?\d+(?:\s*,\s*-?\d+)+)\)(\s*:)")

    def _repl(m: re.Match[str]) -> str:
        inner = m.group(2)
        return m.group(1) + json.dumps(f"({inner})", ensure_ascii=False) + m.group(3)

    # 字符串感知切分：只对"字符串之外"的片段做替换
    segs: list[str] = []
    buf: list[str] = []
    in_str = False
    esc = False
    for ch in s:
        if in_str:
            buf.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
                segs.append("".join(buf))
                buf = []
            continue
        if ch == '"':
            if buf:
                segs.append("".join(buf))
                buf = []
            in_str = True
            buf.append(ch)
        else:
            buf.append(ch)
    if buf:
        segs.append("".join(buf))

    changed = False
    for i, seg in enumerate(segs):
        if seg.startswith('"'):
            continue  # 字符串段：跳过
        new_seg, n = pat.subn(_repl, seg)
        if n:
            segs[i] = new_seg
            changed = True
    return "".join(segs), changed


# 数值 Python 表达式（2026-10-14，LLM_JSON_MODE 上线捕获）：LLM 在 JSON 值
# 位置写 Python 数值表达式 `10**18` / `2**32` / `10_000_000`（下划线分隔符
# 为合法 Python 字面量、非法 JSON）——实测 Planner `input_args` 中
# `{"items":[10**18]}` 致 json.loads 失败，且既有修复链（字符串表达式 /
# 元组键）不含数值路径 → 叶子回退静默返回错误片段（{'items': ...}）→ 被
# 误诊为「LLM 未输出 logic_analysis」（M10）。本函数把值位置的纯数值表达式
# 换算为等值 JSON 数字字面量；仅 `**` / 下划线 / 前导 `+` 场景替换，
# 已是合法 JSON 数字的零改动。
_NUMERIC_EXPR_TOKEN_RE = re.compile(
    r"(?<=[:,\[])(?P<ws>\s*)"
    r"(?P<expr>-?\d[\d_]*(?:\s*\*\*\s*\d[\d_]*)?(?:\s*[+\-*]\s*\d[\d_]*(?:\s*\*\*\s*\d[\d_]*)?)*)"
    r"(?=\s*[,}\]])"
)
# 指数上限：防 `10**10**9` 式内存放大（本函数出现前 JSON 必已解析失败，
# 属罕见路径；预算给足常见工程常量 2**63、10**18 量级）
_MAX_NUMERIC_EXPONENT = 4096
# 结果十进制位数上限（4096 位 ≈ 13KB 字符串，远远超出正常边界输入）
_MAX_NUMERIC_DIGITS = 4096


def _position_in_string(s: str, pos: int) -> bool:
    """pos 是否处于 JSON 字符串字面量内（转义感知的引号奇偶扫描）。

    仅用于数值表达式修复的字符串内防护（该路径只在 json 已解析失败的
    罕见输入上执行，O(n) 成本可接受），避免把字符串内容误当值位置替换。
    """
    in_str = False
    esc = False
    for i in range(min(pos, len(s))):
        ch = s[i]
        if esc:
            esc = False
            continue
        if ch == "\\":
            esc = True
        elif ch == '"':
            in_str = not in_str
    return in_str


def _safe_eval_numeric_expr(node: ast.AST) -> Any:
    """受限数值求值：仅 常量 / 一元正负号 / 四则（``+ - *``）/ 幂运算。

    不使用 eval / ast.literal_eval 的全量语义——拒绝 Call/Attribute/Name/
    Subscript 等一切可执行构造，无任意代码执行面。指数先做界检查
    （``abs(exp) <= _MAX_NUMERIC_EXPONENT``），防超巨整数计算；结果位数
    由调用方 ``_MAX_NUMERIC_DIGITS`` 兜底。
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        val = _safe_eval_numeric_expr(node.operand)
        return -val if isinstance(node.op, ast.USub) else val
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Pow)):
        left = _safe_eval_numeric_expr(node.left)
        right = _safe_eval_numeric_expr(node.right)
        if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
            raise TypeError("non-numeric operand")
        if isinstance(node.op, ast.Pow):
            if not isinstance(left, int) or not isinstance(right, int):
                raise TypeError("unsupported pow operands (int-only)")
            if abs(right) > _MAX_NUMERIC_EXPONENT:
                raise ValueError("exponent too large")
            return left**right
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        return left * right
    raise TypeError(f"unsupported node {type(node).__name__}")


def _normalize_python_numeric_expressions(s: str) -> str:
    """把 JSON 值位置的纯数值 Python 表达式替换为等值 JSON 数字。

    覆盖形态：``{"items":[10**18]}`` → ``{"items":[1000000000000000000]}``、
    ``{"n":2**32}`` → ``4294967296``、``{"m":10_000_000}`` → ``10000000``。
    保守口径：字符串内位置不替换（_position_in_string 防护）；求值结果
    超界/非数值/异常 → 原样保留（交既有降级链）。已是合法 JSON 数字的
    内联数字零改动。
    """

    def _repl(m: re.Match[str]) -> str:
        raw = m.group("expr")
        # 已是合法 JSON 数字（含负数/科学计数/小数）→ 零改动
        try:
            jv = json.loads(raw)
            if isinstance(jv, (int, float)) and not isinstance(jv, bool):
                return m.group(0)
        except (json.JSONDecodeError, ValueError):
            pass
        if _position_in_string(s, m.start("expr")):
            return m.group(0)
        try:
            tree = ast.parse(raw, mode="eval")
            val = _safe_eval_numeric_expr(tree.body)
        except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):
            return m.group(0)
        if not isinstance(val, (int, float)) or isinstance(val, bool):
            return m.group(0)
        if len(str(val)) > _MAX_NUMERIC_DIGITS:
            return m.group(0)
        return m.group(0)[: m.start("expr") - m.start(0)] + json.dumps(val)

    return _NUMERIC_EXPR_TOKEN_RE.sub(_repl, s)


def _repair_json_bounded(s: str, rounds: int = 4) -> str:
    """有界迭代修复：反复施加各类保守修复，直到可解析或用尽轮次。

    单轮修复常不足以解决**复合**损坏（如"元组键 + 尾随逗号 + 未加引号
    字面量"同时出现）；逐轮施加并在每轮后试解析，命中即停。
    轮次上限防病态输入下的无限循环。
    """
    cur = s
    for _ in range(max(1, rounds)):
        try:
            json.loads(cur)
            return cur
        except json.JSONDecodeError:
            pass
        nxt, changed = _quote_tuple_keys_once(cur)
        nxt = _repair_json_text(nxt)
        nxt = _quote_python_expressions(nxt)
        # 2026-10-14：数值 Python 表达式（10**18 / 10_000 等，JSON 非法）
        nxt = _normalize_python_numeric_expressions(nxt)
        if not changed and nxt == cur:
            return cur
        cur = nxt
    return cur


def _quote_python_expressions(s: str, max_len: int = 4096) -> str:
    """把 JSON 值位置上的**纯字面量 Python 表达式**替换为等值 JSON 字面量。

    D1 残余主因（实测 93/188 失败样本）：LLM 在 ``input_args`` 里写
    ``{"key":"a"*10000}``、``{"length_by_edge":{(0,1):5}}`` 这类 **Python
    表达式/元组键** —— 语法上不是 JSON。

    安全口径（**不使用 eval**）：只对匹配到的候选片段调用
    ``ast.literal_eval``（仅接受字面量：常量/字符串/数字/容器/一元负号，
    拒绝 Call/Attribute/Name 等一切可执行构造），并限制：
    - 候选必须是**单行**且长度 ≤ ``max_len``（防 ReDoS/超长解析）；
    - 求值结果必须是 ``str``（值位置的字面量只需处理字符串场景；
      数字内联字面量由 JSON 自身语法覆盖、**数值表达式**（``10**18``）
      由 ``_normalize_python_numeric_expressions`` 单独处理，本函数不做
      过度替换）；
    - 求值异常/类型不符/超限 → 原样保留（保守失败，交既有降级链）。

    覆盖形态：``"a"*10000``（字符串重复）、``"x"+y`` 中的纯字面量连接。
    元组作**键**（``(0,1):5``）不在本函数处理范围——键位置需改写结构，
    风险高于收益，保持既有降级（诚实失败）。
    """
    if '"' not in s:
        return s

    def _safe_eval(node: ast.AST, budget: int) -> Any:
        """受限求值：只支持 常量 / 字符串重复``"a"*n`` / 字面量连接``+``。

        ``ast.literal_eval`` 覆盖不了 ``"x"*3``（那是 ``BinOp`` 而非字面量），
        故自写最小求值器：**只允许** ``Constant``、``BinOp(Mult)``（一侧为
        字符串、另一侧为小整数）、``BinOp(Add)``。其余节点一律抛错拒绝——
        不触达 Call/Attribute/Name/Subscript，故无任意代码执行面。
        ``budget`` 为字符串长度上限（防 ``"a"*10**9`` 式内存放大）。
        """
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.BinOp):
            left = _safe_eval(node.left, budget)
            right = _safe_eval(node.right, budget)
            if isinstance(node.op, ast.Add) and isinstance(left, str) and isinstance(right, str):
                out = left + right
            elif isinstance(node.op, ast.Mult):
                if isinstance(left, str) and isinstance(right, int) and not isinstance(right, bool):
                    out = left * right
                elif isinstance(right, str) and isinstance(left, int) and not isinstance(left, bool):
                    out = right * left
                else:
                    raise TypeError("unsupported mult operands")
            else:
                raise TypeError("unsupported operator")
            if len(out) > budget:
                # 超预算不丢弃整条计划，而是**截断**：LLM 常写
                # ``"a"*10000`` 之类的超长边界输入，测试语义上"一个长字符串"
                # 已足够触发边界路径；截断保留该用例其余字段（远优于整任务
                # 回退空计划）。截断是**保守失真**，不改类型/类别语义。
                out = out[:budget]
            return out
        raise TypeError(f"unsupported node {type(node).__name__}")

    def _repl(m: re.Match[str]) -> str:
        raw = m.group(1)
        if len(raw) > max_len or "\n" in raw:
            return m.group(0)
        try:
            tree = ast.parse(raw, mode="eval")
            val = _safe_eval(tree.body, max_len)
        except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):
            return m.group(0)
        if not isinstance(val, str):
            return m.group(0)
        # 保留冒号前的原始前缀（含 ": " 与缩进），只替换表达式本体
        prefix = m.group(0)[: m.start(1) - m.start(0)]
        return prefix + json.dumps(val, ensure_ascii=False)

    # 值位置：冒号后、由引号开头的表达式，直到遇到 , } ] 为止
    return re.sub(r':\s*("(?:[^"\\]|\\.)*"(?:\s*\*\s*\d+|\s*\+\s*"(?:[^"\\]|\\.)*")+)', _repl, s)


def _find_balanced_delimited(text: str, start: int, open_ch: str, close_ch: str) -> str | None:
    """括号平衡法提取从 ``start``（应为 ``open_ch``）开始的第一个完整定界片段。

    2026-10-16 C 轮去重：``_find_balanced_bracket`` 与 ``_find_balanced_json``
    曾是同构双份实现（仅括号类型不同），合并为参数化单一实现；两个公共
    包装函数行为逐字节不变（各有锁定测试）。

    算法：遇 ``open_ch`` 深度 +1、遇 ``close_ch`` 深度 -1，归零时返回
    ``text[start:i+1]``；字符串字面量内（含转义）的括号不计入深度。

    Args:
        text: 待搜索文本。
        start: 起始位置（应为 ``open_ch`` 的下标）。
        open_ch: 开定界符（``[`` 或 ``{``）。
        close_ch: 闭定界符（``]`` 或 ``}``）。

    Returns:
        完整片段字符串；未闭合时返回 None。
    """
    depth = 0
    in_string = False
    escape = False

    if start < 0 or start >= len(text):
        return None

    i = start
    while i < len(text):
        ch = text[i]

        if escape:
            escape = False
            i += 1
            continue

        if ch == "\\":
            escape = True
            i += 1
            continue

        if ch == '"':
            in_string = not in_string
            i += 1
            continue

        if in_string:
            i += 1
            continue

        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]

        i += 1

    return None


def _find_balanced_bracket(text: str, start: int) -> str | None:
    """括号平衡法提取从 ``start``（应为 ``[``）开始的第一个完整 JSON **数组**。

    委托 :func:`_find_balanced_delimited`（方括号口径）；字符串字面量内的
    ``[`` / ``]`` 不计入深度。

    Args:
        text: 待搜索文本。
        start: 起始位置（应为 ``[`` 的下标）。

    Returns:
        完整的 JSON 数组字符串；未闭合时返回 None。
    """
    return _find_balanced_delimited(text, start, "[", "]")


def _try_parse_raw_json(text: str, opener: str, expected_type: type) -> Any | None:
    """在**未经围栏清洗**的原始文本上尝试首个括号平衡片段（K 轮快路径）。

    为什么需要这条快路径：围栏清洗只应服务于"异常形态的修复档"，不应改写
    合法 JSON 的字符串内容（见 ``_JSON_FENCE_STRIP_PATTERN`` 上方 K 轮修复
    说明）。快路径在原始文本上做与主链**同构**的首片段提取（首个 opener
    起、括号平衡、``json.loads``），成功即返回——对合法 LLM 输出（含
    markdown 围栏、前后自然语言）内容零改写；失败才落到既有"清洗 + 修复"
    链，历史行为逐字节不变。

    与主链的选择口径一致性：清洗只删除行首围栏、不改变花括号/方括号的
    相对结构与首个 opener 的位置，因此快路径与主链选中的是**同一个片段**，
    区别仅在于快路径保留字符串字面量内的反引号（这正是本函数要保住的语义）。

    Args:
        text: 原始响应文本（未清洗）。
        opener: ``"{"``（对象）或 ``"["``（数组）。
        expected_type: 期望的顶层类型（``dict`` / ``list``），不匹配时返回
            None 交回主链（主链对顶层类型不做强制，保持既有宽松口径）。

    Returns:
        解析成功且顶层类型匹配时返回对象；否则 None。
    """
    start = text.find(opener)
    if start == -1:
        return None
    fragment = _find_balanced_json(text, start) if opener == "{" else _find_balanced_bracket(text, start)
    if fragment is None:
        return None
    try:
        value = json.loads(fragment.strip())
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, expected_type) else None


# 匹配最内层无嵌套的 [...] JSON 数组（降级方案用）
_JSON_ARRAY_LEAF_PATTERN = re.compile(r"\[[^\[\]]*\]")


def extract_json_array(text: str) -> list[Any]:
    """从文本中提取 JSON **数组**（对称于 :func:`extract_json_object`）。

    T2（2026-10-11 独立评审落地）：修复"顶层 JSON 数组永远解析失败"缺陷。

    背景（真实 LLM 调用实测）：``extract_json_object`` 只查找第一个 ``{``，
    从不接受顶层数组——对合法数组输入 ``'["a","b"]'`` 直接抛
    ``JSONDecodeError: No JSON found in response``。而以下调用点**以数组为
    契约**，故从设计上永远不可能生效（静默降级为空结果）：

    - ``debugger.py`` 的 ``_generate_adversarial_intents``（对抗性推理 3.1）
      提示词要求"请输出 JSON 数组（字符串列表）"；
    - ``oracle_enhancer.py`` 的 ``enhance``（原子化测试预言）提示词要求
      "输出 JSON 数组，每项含 {case_name, oracle, ...}"。

    处理流程与对象版逐档对齐：
    1. 原始文本直解析（K 轮快路径：合法数组的字符串内容零改写）；
    2. 剥离**行首** markdown 围栏后，找到第一个 ``[``，括号平衡法提取完整数组；
    3. 失败时对片段做语法级修复再试（尾随逗号等）；
    4. 仍失败则用正则取最内层无嵌套数组；
    5. 全部失败抛 ``json.JSONDecodeError``（与对象版同口径，调用方按
       既有 ``except Exception`` 保守降级路径处理，行为不变）。

    Args:
        text: 包含 JSON 数组的文本。

    Returns:
        解析后的列表对象。

    Raises:
        json.JSONDecodeError: 无法找到有效 JSON 数组时抛出。
    """
    if not text:
        raise json.JSONDecodeError("No JSON array found in response", text or "", 0)

    # K 轮快路径：原始文本直解析（合法数组的字符串内容零改写；
    # 失败才落到既有清洗 + 修复链，历史行为不变）
    _fast = _try_parse_raw_json(text, "[", list)
    if _fast is not None:
        return _fast

    cleaned = _JSON_FENCE_STRIP_PATTERN.sub("", text)
    cleaned = _JSON_BACKTICK_STRIP_PATTERN.sub("", cleaned)

    start = cleaned.find("[")
    if start == -1:
        raise json.JSONDecodeError("No JSON array found in response", text, 0)

    # 档 1：括号平衡 + 语法级修复
    json_str = _find_balanced_bracket(cleaned, start)
    if json_str is not None:
        _base = json_str.strip()
        for _cand in (
            _base,
            _repair_json_text(_base),
            _quote_python_expressions(_base),
            _quote_python_expressions(_repair_json_text(_base)),
            _repair_json_bounded(_base),
        ):
            try:
                _arr = json.loads(_cand)
            except json.JSONDecodeError:
                continue
            if isinstance(_arr, list):
                return _arr

    # 档 2：正则取最内层（最后出现）的无嵌套数组
    last_match: re.Match[str] | None = None
    for m in _JSON_ARRAY_LEAF_PATTERN.finditer(cleaned):
        last_match = m
    if last_match is not None:
        try:
            _arr = json.loads(last_match.group())
            if isinstance(_arr, list):
                return _arr
        except json.JSONDecodeError:
            pass

    raise json.JSONDecodeError("Could not find complete JSON array", text, start)


def was_leaf_fallback_used() -> bool:
    """OMS（M10 可观测性）：最近一次 extract_json_object 是否走了叶子回退档。

    背景（ADR-0031 遗留，EMSE 批次四 M1）：extract_json_object 的叶子降级
    档在括号平衡法失败时**静默返回最内层片段**（如 {'items': ...}），下游
    Planner M10 路径把"缺 logic_analysis"误诊为"LLM 未输出"（实为提取器
    缺陷，LLM 输出了完整正确 JSON）。本函数返回**最近一次**调用是否命中
    叶子档且返回了片段（调用方须在同一调用栈立即读取——见模块级哨兵
    纪律注释）。纯观测：不影响任何解析行为，历史口径零变化。
    """
    return _LEAF_FALLBACK_ACTIVE


def extract_json_object(text: str) -> dict[str, Any]:
    """
    从文本中提取 JSON 对象。

    处理流程：
    1. 原始文本直解析（K 轮快路径：合法对象的字符串内容零改写——反引号等
       字面量不被围栏清洗误删）
    2. 失败时剥离**行首** markdown 围栏（```json 或 ```），再用括号平衡法
       找到完整的 JSON 对象
    3. 若仍失败，用正则提取候选 JSON 作为降级方案
       （OMS：叶子档命中时记录 warning + 置模块级哨兵 _LEAF_FALLBACK_ACTIVE，
       调用方经 was_leaf_fallback_used() 读取后把 M10 归因改写为
       "提取器叶子回退"——ADR-0031 §已知局限②，纯观测零行为变化）

    Args:
        text: 包含 JSON 对象的文本。

    Returns:
        解析后的字典对象。

    Raises:
        json.JSONDecodeError: 无法找到有效 JSON 时抛出。
    """
    global _LEAF_FALLBACK_ACTIVE
    _LEAF_FALLBACK_ACTIVE = False
    # K 轮快路径：原始文本直解析（合法对象的字符串内容零改写——反引号等
    # 字面量不被围栏清洗误删；见模块头部 K 轮修复说明）。
    # 快路径成功不属于任何降级档，哨兵保持 False。
    _fast = _try_parse_raw_json(text, "{", dict)
    if _fast is not None:
        return _fast
    # 移除 markdown 代码块标记（使用预编译正则，避免每次调用重复编译）
    cleaned = _JSON_FENCE_STRIP_PATTERN.sub("", text)
    cleaned = _JSON_BACKTICK_STRIP_PATTERN.sub("", cleaned)

    # 找到第一个 '{' 位置
    start = cleaned.find("{")
    if start == -1:
        raise json.JSONDecodeError("No JSON found in response", text, 0)

    # 使用括号平衡法提取完整 JSON
    json_str = _find_balanced_json(cleaned, start)
    if json_str is not None:
        try:
            return json.loads(json_str.strip())
        except json.JSONDecodeError:
            # D1 修复档 1：括号平衡片段先做语法级修复再试（尾随逗号 /
            # 未加引号 Python 字面量）——实测该类占失败样本约 129/188。
            _base = json_str.strip()
            for _cand in (
                _repair_json_text(_base),
                _quote_python_expressions(_base),
                _quote_python_expressions(_repair_json_text(_base)),
                _repair_json_bounded(_base),
            ):
                if _cand == _base:
                    continue
                try:
                    _obj = json.loads(_cand)
                    if isinstance(_obj, dict):
                        return _obj
                except json.JSONDecodeError:
                    continue
            # 降级到正则方案

    # D1 修复档 2：多对象背靠背拼接（实测 57/188）——取**第一个**平衡对象
    # 并做语法修复。放在叶子方案之前：叶子方案会取到"最后一个"对象，
    # 对"多个任务的计划连写"场景语义不符（应取首个，与 Planner 单任务契约一致）。
    _first = _first_balanced_object(cleaned)
    if _first is not None:
        for cand in (
            _first,
            _repair_json_text(_first),
            _quote_python_expressions(_first),
            _quote_python_expressions(_repair_json_text(_first)),
            _repair_json_bounded(_first),
        ):
            try:
                _obj = json.loads(cand)
                if isinstance(_obj, dict) and _obj:
                    return _obj
            except json.JSONDecodeError:
                continue

    # 降级方案：用正则匹配最内层无嵌套的 {...}
    # 2026-09-26 优化：O(1) 记忆扫描"最后出现的叶子 JSON"（避免
    # list(finditer) 物化全部匹配的 O(n) 内存分配）——语义等价：原
    # reversed(list(...)) 逐个尝试叶子，最内层（最后出现）的嵌套对象
    # 是 LLM 真实输出，首个可解析者即为提取目标。扫描时记录候选，
    # 仅最后候选解析失败时回退前一个（覆盖"外层 wrapper 失败 → 内层
    # 成功"的常见两层嵌套场景，罕见三层嵌套仍由括号平衡法兜底）。
    # 2026-09-26 审查修正（P1 语义回归）：O(1) 双候选只试"最后两个"叶子，
    # 当"可解析叶子"排在更早位置时（损坏响应中夹带 ≥3 个片段、仅第 1 个
    # 合法）会被静默跳过直接 raise——而括号平衡法恰在此场景失败（最外层
    # 残缺 → 返回 None），叶子降级方案是该路径唯一兜底，回归即主链 LLM 解析
    # 失败误判。现补"双候选均失败 → 反向全量扫描"的罕见降级尾路径
    # （只在平衡法失败 + 最后两个叶子都不可解析时执行，频率极低，
    # O(n) 可接受；正常路径仍为 O(1) 双候选快路径，行为不变）。
    last_match: re.Match[str] | None = None
    prev_match: re.Match[str] | None = None
    for m in _JSON_LEAF_PATTERN.finditer(cleaned):
        prev_match = last_match
        last_match = m
    # OMS（M10 可观测性，EMSE 批次四）：叶子回退档命中时置哨兵 + 显式告警。
    # 此前该路径**静默**返回最内层片段（如 {'items': ...}）——下游 Planner
    # M10 把"缺 logic_analysis"归因为 LLM 未输出，实为提取器回退到错误片段
    # （ADR-0031 §已知局限②）。现命中时记录 warning + 置模块级哨兵，
    # 调用方经 was_leaf_fallback_used() 读取后可把 M10 归因改写为
    # "提取器叶子回退"（消除 10-14 批次 ~7-8% 解析层误诊的度量盲区）。
    # 纯观测：解析行为与返回值零变化（哨兵不复位到本调用结束，由下一次
    # 调用覆盖；raise 路径不触发，哨兵保持 False）。
    if last_match is not None:
        try:
            _LEAF_FALLBACK_ACTIVE = True
            logger.warning(
                "JSON 提取叶子回退：括号平衡法与首对象修复均失败，"
                "返回最内层片段（len=%d, 前缀=%r）——下游缺字段归因须复核",
                len(last_match.group()),
                last_match.group()[:60],
            )
            return json.loads(last_match.group())
        except json.JSONDecodeError:
            _LEAF_FALLBACK_ACTIVE = False
    if prev_match is not None:
        try:
            _LEAF_FALLBACK_ACTIVE = True
            logger.warning(
                "JSON 提取叶子回退（次新候选）：返回倒数第二内层片段（len=%d）",
                len(prev_match.group()),
            )
            return json.loads(prev_match.group())
        except json.JSONDecodeError:
            _LEAF_FALLBACK_ACTIVE = False
    # 双候选均不可解析：反向全量扫描（旧 reversed(list(finditer)) 语义）——
    # 跳过最后两个叶子（上两档已试过），从倒数第三个起逐个尝试，
    # 首个可解析者即返回（覆盖"可解析叶子排在更早位置"的损坏响应场景）；
    # 叶子总数 ≤ 2 时零迭代，直接落到下方 raise
    tail_matches = list(_JSON_LEAF_PATTERN.finditer(cleaned))
    if len(tail_matches) > 2:
        for m in reversed(tail_matches[:-2]):
            try:
                _LEAF_FALLBACK_ACTIVE = True
                logger.warning("JSON 提取叶子回退（尾扫）：返回更早位置的片段")
                return json.loads(m.group())
            except json.JSONDecodeError:
                continue

    # 所有方案均失败
    raise json.JSONDecodeError("Could not find complete JSON", text, start)


def _find_balanced_json(text: str, start: int) -> str | None:
    """
    使用括号平衡法找到从 start 位置开始的第一个完整 JSON 对象。

    算法原理：
    - 遇到 '{' 深度+1，遇到 '}' 深度-1
    - 当深度归零时，说明找到了匹配的右花括号
    - 字符串字面量内的 '{' 和 '}' 不计入深度

    Args:
        text: 待搜索的文本。
        start: 起始搜索位置（应为 '{' 的位置）。

    Returns:
        完整的 JSON 字符串，未找到时返回 None。
    """
    # 2026-10-16 C 轮去重：委托参数化实现（花括号口径），行为不变。
    # JSON 对象未闭合（全文无匹配右括号）时返回 None，由调用方走正则降级方案——
    # 此前返回 text[start:]（未闭合的残余文本），json.loads 必失败还要再付
    # 一遍 O(n) 解析；直接 None 省掉该次无谓解析
    return _find_balanced_delimited(text, start, "{", "}")
