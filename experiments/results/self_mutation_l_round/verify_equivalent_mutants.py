"""L 轮等价归因证据：11 个实践等价变异体的公开 API 差分探测（确定性种子）。

口径：只调用公开 API（extract_json_object / extract_json_array /
was_leaf_fallback_used），比较「原始 vs 变异体」的 (返回值, 哨兵) / 异常类型。
输出每个变异体的差分计数与语料规模；0 差异 + 机制论证 = 「强证据实践等价」。
"""
from __future__ import annotations

import json
import logging
import random
import sys
import types

sys.path.insert(0, '.')
logging.disable(logging.CRITICAL)
import src.utils.helpers as orig
from experiments.mutation_testing import ExtendedMutationGenerator
from scripts.tools.self_mutation import _mutant_id

EQUIVALENT = [
    'helpers:1567052b264f',  # _first 修复环 continue→break（环不可达：可修复片段必被主链先返回）
    'helpers:499e052e17f3',  # _first_balanced_object 字符串闭合取反（同环，不可观测）
    'helpers:4b692477a69f',  # _safe_eval Mult 首分支 and→or（正则文法下恒真，elif/else 不可达）
    'helpers:5e361b2a0469',  # _try_parse_raw_json start 守卫取反（快路径与主链同片段，纯性能）
    'helpers:708a96fb4c79',  # _try_parse_raw_json opener 分派取反（同上）
    'helpers:90f214353202',  # _quote_python_expressions 非 str 守卫删除（匹配文法恒返回 str）
    'helpers:969a4fdc693d',  # _first_balanced_object 开引号判定改写（同环，不可观测）
    'helpers:9d7b56bee4bd',  # _safe_eval Mult 次分支 and→or（正则文法下不可达）
    'helpers:b7e3f4dfe70b',  # normalize 非数值守卫 or→and（val 恒为数值非 bool，守卫空转）
    'helpers:b96d0e079983',  # 删除 _first 修复环（环不可达，死代码删除）
    'helpers:fdaf4935266c',  # 合法 JSON 数字早退守卫取反（重序列化文本等价，解析值相同）
]
REL = 'src/utils/helpers.py'
src = open(REL, encoding='utf-8').read()
gen = ExtendedMutationGenerator(max_per_task=10_000)
by_id = {_mutant_id('helpers', m): m for m in gen.generate(src)}
mods: dict[str, types.ModuleType] = {}
for mid in EQUIVALENT:
    mod = types.ModuleType('mut')
    exec(compile(by_id[mid].code, 'mut.py', 'exec'), mod.__dict__)
    mods[mid] = mod

# 确定性语料：结构化模板 + 固定种子随机结构串（不含随机值断言，仅差分探测）
TEMPLATES = [
    '{"a": 1}', '{"a": None}', '{"a": (0,1): 5}', '{"a": "x"*2}', '{"a": 10**3}',
    '{"": 1, (0,1): 5}', '{"desc": "note ,(0,1): pair", (0,1): 5}', '{"a": 1, , , , }',
    '{"outer": {"good": 5} junk} {"bad1": } {"bad2": }', 'prefix {} suffix', '```json\n{"a": 1}\n```',
    '[1, 2]', '["a"*2]', '[2**32]', '{"n": 10**4095}', '{"n": 10**4096}',
    '{"a": "x" + "y"}', '{"a": "\\\\"}', '{"a": "\\"", "b": }', '{"cmd": "```bash"}',
]
rng = random.Random(20261017)
ALPHA = ['{', '}', '"', '\\', ': ', ', ', '[', ']', '1', 'a', ' ', 'None', '{"a": 1}', '(0,1): ']
corpus = list(TEMPLATES)
corpus += [''.join(rng.choice(ALPHA) for _ in range(rng.choice([6, 8, 10, 12, 16]))) for _ in range(20000)]
corpus += [p + t + s for t in TEMPLATES for p in ('', 'x ', '```json\n') for s in ('', '\n```', ' tail')]


def observe(mod: types.ModuleType, fn: str, text: str) -> tuple:
    try:
        value = getattr(mod, fn)(text)
        out = ('ok', type(value).__name__, repr(value))
    except json.JSONDecodeError:
        out = ('json_error',)
    except Exception as e:  # noqa: BLE001
        out = ('exc', type(e).__name__)
    if fn == 'extract_json_object':
        out = out + ('leaf', mod.was_leaf_fallback_used())
    return out


print(f'语料规模: {len(corpus)} 输入 × 2 公开 API × {len(EQUIVALENT)} 变异体')
for mid in EQUIVALENT:
    diffs = 0
    sample = None
    for text in corpus:
        for fn in ('extract_json_object', 'extract_json_array'):
            if observe(orig, fn, text) != observe(mods[mid], fn, text):
                diffs += 1
                sample = sample or (fn, text[:80])
    print(f'{mid}: 公开 API 差分 = {diffs}' + (f'（示例 {sample}）' if sample else '（零差异）'))
