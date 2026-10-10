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
# 每次调用重复编译 re.sub 模式浪费；re 内部缓存有限，显式编译最稳妥）
_JSON_FENCE_STRIP_PATTERN = re.compile(r"```(?:json)?\s*\n?")
_JSON_BACKTICK_STRIP_PATTERN = re.compile(r"```")
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
      数字/容器由 JSON 自身语法覆盖，不做过度替换）；
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


def extract_json_object(text: str) -> dict[str, Any]:
    """
    从文本中提取 JSON 对象。

    处理流程：
    1. 移除 markdown 代码块标记（```json 或 ```）
    2. 使用括号平衡法找到完整的 JSON 对象
    3. 若失败，用正则提取候选 JSON 作为降级方案

    Args:
        text: 包含 JSON 对象的文本。

    Returns:
        解析后的字典对象。

    Raises:
        json.JSONDecodeError: 无法找到有效 JSON 时抛出。
    """
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
    if last_match is not None:
        try:
            return json.loads(last_match.group())
        except json.JSONDecodeError:
            pass
    if prev_match is not None:
        try:
            return json.loads(prev_match.group())
        except json.JSONDecodeError:
            pass
    # 双候选均不可解析：反向全量扫描（旧 reversed(list(finditer)) 语义）——
    # 跳过最后两个叶子（上两档已试过），从倒数第三个起逐个尝试，
    # 首个可解析者即返回（覆盖"可解析叶子排在更早位置"的损坏响应场景）；
    # 叶子总数 ≤ 2 时零迭代，直接落到下方 raise
    tail_matches = list(_JSON_LEAF_PATTERN.finditer(cleaned))
    if len(tail_matches) > 2:
        for m in reversed(tail_matches[:-2]):
            try:
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
    depth = 0
    in_string = False
    escape = False

    if start < 0 or start >= len(text):
        return None

    i = start
    while i < len(text):
        ch = text[i]

        # 处理转义
        if escape:
            escape = False
            i += 1
            continue

        # 遇到反斜杠，标记下一个字符为转义字符
        if ch == "\\":
            escape = True
            i += 1
            continue

        # 遇到双引号，切换字符串状态
        if ch == '"':
            in_string = not in_string
            i += 1
            continue

        # 在字符串内部时跳过
        if in_string:
            i += 1
            continue

        # 处理花括号深度变化
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]

        i += 1

    # JSON 对象未闭合（全文无匹配右括号）：返回 None，由调用方走正则降级方案。
    # 此前返回 text[start:]（未闭合的残余文本），json.loads 必失败还要再付
    # 一遍 O(n) 解析——直接 None 省掉该次无谓解析
    return None
