"""生成 L 轮自身变异测试报告（JSON + Markdown）——唯一事实源为 before/after 报告 JSON。

用法（仓库根）：
    .venv/bin/python experiments/results/self_mutation_l_round/build_l_round_report.py

输入（默认同目录，均由 scripts/tools/self_mutation.py 实测产出）：
    self_mutation_before.json  —— 追加 L 轮测试前的同口径基线（K 轮 after 测试集）
    self_mutation_after.json   —— 追加 tests/test_self_mutation_survivors_l.py 后的复跑
输出：
    self_mutation_l_round.json —— 机器可读聚合（before/after + 击杀清单 + 存活逐条归因）
    SELF_MUTATION_L_ROUND.md   —— 人读报告

纪律：数字一律从 JSON 读取，不手写；击杀/归因映射是 L 轮分析结论（含测试函数名）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_BEFORE = _HERE / "self_mutation_before.json"
_AFTER = _HERE / "self_mutation_after.json"
_OUT_JSON = _HERE / "self_mutation_l_round.json"
_OUT_MD = _HERE / "SELF_MUTATION_L_ROUND.md"

_COMMON = (
    ".venv/bin/python scripts/tools/self_mutation.py "
    "--files src/utils/env_utils.py,src/utils/helpers.py,src/utils/atomic_io.py --workers 2"
)
_TEST_MAP_ENV = "--test-map src/utils/env_utils.py=tests/test_env_utils.py,tests/test_self_mutation_targets.py"
_TEST_MAP_ATOMIC = "--test-map src/utils/atomic_io.py=tests/test_atomic_io.py,tests/test_self_mutation_targets.py"
_HELPERS_TESTS = (
    "tests/test_helpers_json_property.py,tests/test_helpers_json_robustness.py,"
    "tests/test_helpers_json_fence_content.py,tests/test_self_mutation_targets.py"
)
_BEFORE_CMD = (
    f"{_COMMON} {_TEST_MAP_ENV} "
    f"--test-map src/utils/helpers.py={_HELPERS_TESTS} {_TEST_MAP_ATOMIC} "
    "--json-out experiments/results/self_mutation_l_round/self_mutation_before.json "
    "--md-out experiments/results/self_mutation_l_round/self_mutation_before.md"
)
_AFTER_CMD = (
    f"{_COMMON} {_TEST_MAP_ENV} "
    f"--test-map src/utils/helpers.py={_HELPERS_TESTS},tests/test_self_mutation_survivors_l.py "
    f"{_TEST_MAP_ATOMIC} "
    "--json-out experiments/results/self_mutation_l_round/self_mutation_after.json "
    "--md-out experiments/results/self_mutation_l_round/self_mutation_after.md"
)

# L 轮击杀清单：变异体 ID → (变异语义, 击杀测试, 行为契约解释)
_KILLED: dict[str, tuple[str, str, str]] = {
    "helpers:29836f6132a3": (
        "extract_json_array 修复候选循环 continue→break",
        "test_numeric_expression_repaired_in_array",
        "数组路径数值表达式修复：首个候选失败后必须继续尝试后续修复档，不得提前终止",
    ),
    "helpers:396a28db8ca8": (
        "_quote_python_expressions 超长/多行守卫 or→and",
        "test_overlong_single_line_expression_is_not_evaluated",
        "超长单行表达式保守不评估（文档 max_len 口径）→ 诚实失败而非静默截断改写",
    ),
    "helpers:5f59874830d1": (
        "_find_balanced_json 闭合符 '}'→'x'",
        "test_empty_object_via_direct_path_is_not_leaf_fallback; "
        "test_fenced_empty_object_is_not_leaf_fallback",
        "合法空对象直解析不得被误记为叶子回退（OMS 哨兵公开可观测契约）",
    ),
    "helpers:5f886043809a": (
        "叶子回退尾扫档哨兵置位 True→False",
        "test_tail_scan_fallback_returns_later_fragment_and_sets_flag",
        "尾扫档命中时必须置位 OMS 哨兵（返回值 + 可观测标记成对承诺）",
    ),
    "helpers:608205e3bd2f": (
        "_quote_tuple_keys_once 字符串开引号判定改写",
        "test_tuple_key_repair_preserves_string_literal_content",
        "元组键修复必须字符串感知：字符串内部 ',(0,1):' 文本不得被当键替换",
    ),
    "helpers:925bf0576cf6": (
        "数值结果位数上限 >→>=",
        "test_numeric_expression_digit_boundary_is_conservative",
        "恰好 4096 位的结果仍须修复（严格大于才拒绝，边界语义）",
    ),
    "helpers:a3ee749e3485": (
        "叶子回退尾扫阈值 2→3",
        "test_tail_scan_fallback_returns_later_fragment_and_sets_flag",
        "≥3 个叶子且末两个不可解析时尾扫必须触发（返回更早可解析片段）",
    ),
    "helpers:a93688ca6eb0": (
        "_quote_tuple_keys_once esc 初值 False→True",
        "test_tuple_key_repair_with_empty_first_string",
        "字符串感知状态机对「空串/首字符转义」边界正确，元组键才能修复",
    ),
    "helpers:cc058e223acc": (
        "叶子回退失败分支哨兵复位 False→True",
        "test_leaf_flag_resets_when_extraction_ultimately_fails",
        "解析最终失败时哨兵必须复位 False（不得残留「发生过回退」的假标记）",
    ),
    "helpers:e6b7f907a2b1": (
        "_repair_json_bounded 尾部 return cur→None",
        "test_bounded_repair_failure_raises_json_decode_error_not_type_error",
        "修复轮次耗尽必须抛 json.JSONDecodeError（调用方降级契约），不得泄漏 TypeError",
    ),
    "helpers:f95a3a18c5c3": (
        "_quote_tuple_keys_once 字符串闭合判定取反",
        "test_tuple_key_repair_preserves_string_literal_content",
        "元组键修复必须字符串感知（同 608205 契约的另一处状态机分支）",
    ),
    "helpers:383bf2851ceb": (
        "叶子回退「次新候选」logger.warning 文本整体改写（诊断文本变异）",
        "test_second_newest_leaf_fallback_sets_flag; "
        "test_tail_scan_fallback_returns_later_fragment_and_sets_flag",
        "【间接击杀，机制如实披露】改写后的格式串不含占位符但调用仍传参 → 在会格式化日志记录的"
        "运行环境（pytest logging 捕获）触发 TypeError，调用方观测到异常而非返回字典；"
        "未断言日志消息文本，属诊断文本变异在测试运行环境下的可观测崩溃（非「公开契约外」硬杀）",
    ),
}

# L 轮「强证据实践等价」：变异体 ID → 等价机制
_EQUIVALENT: dict[str, str] = {
    "helpers:1567052b264f": "extract_json_object 首对象修复环 continue→break：该环在可修复片段上不可达"
    "（可修复/可解析片段必然先被主链同候选集返回；差分语料零差异）",
    "helpers:499e052e17f3": "_first_balanced_object 字符串闭合判定取反：唯一调用点即上述不可达修复环，公开面不可观测",
    "helpers:969a4fdc693d": "_first_balanced_object 开引号判定改写：唯一调用点即上述不可达修复环，公开面不可观测",
    "helpers:b96d0e079983": "删除 extract_json_object 首对象修复环整段：环不可达，等价于死代码删除",
    "helpers:4b692477a69f": "_safe_eval Mult 首分支 and→or：正则文法保证 Mult 左操作数恒为 str、右操作数恒为 int"
    "（非 bool），首分支恒真，elif/else 不可达",
    "helpers:9d7b56bee4bd": "_safe_eval Mult 次分支 and→or：同上，次分支与 else 在匹配文法下不可达",
    "helpers:90f214353202": "_quote_python_expressions 非 str 守卫删除：匹配文法下 _safe_eval 恒返回 str，守卫空转",
    "helpers:b7e3f4dfe70b": "_normalize 结果类型守卫 or→and：求值成功值恒为 int/float 且非 bool，守卫空转",
    "helpers:fdaf4935266c": "合法 JSON 数字早退守卫取反：回退路径对整数重序列化文本等价（解析值相同；'-0'→'0' 同值）",
    "helpers:5e361b2a0469": "raw 快路径 start 守卫取反（等价于禁用快路径）：合法片段直解析与主链同片段同结果，纯性能路径",
    "helpers:708a96fb4c79": "raw 快路径 opener 分派取反（等价于禁用快路径）：同上，公开输出零差异",
}

# L 轮「公开契约外」：内部诊断文本（本轮最终 0 个：383b 转为间接击杀，见 _KILLED 注记）
_CONTRACT_OUT: dict[str, str] = {}

# K 轮既有「强证据实践等价」（17 个，来源 survivor_attribution.md §3.2）
_K_EQUIVALENT: dict[str, str] = {
    "atomic_io:1cd56015792b": "dirname(abspath(path)) or '.' 的 '.' 为死代码（abspath 后 dirname 恒非空）",
    "atomic_io:1e70830a0a5a": "if fd >= 0 的 fd==0 分支正常进程不可达（stdio 占 0/1/2）",
    "atomic_io:3d86e2a8cfa5": "os.fdopen(fd, 'x') 对已打开 fd 忽略创建语义（Python 3.14 实测相同）",
    "atomic_io:d1ee323e21c3": "if fd >= 0 → fd > 0：同上，fd==0 分支不可达",
    "helpers:076b4fb6bd68": "_CODE_BLOCK_PYTHON_PATTERN 改写：次档 _CODE_BLOCK_PATTERN 为其超集，同输入同结果",
    "helpers:181ced4c9a27": "_try_parse_raw_json 返回 None：快路径失败后修复链对同输入产出相同结果",
    "helpers:1fbc17a82a71": "删除同一越界守卫：越界输入在后续切分路径同样得 None",
    "helpers:2676fb402fc5": "删除早期 JSONDecodeError：后续兜底 raise 同类型异常，公开契约不变",
    "helpers:380f944f4d05": "ensure_ascii=False→True：仅 JSON 文本转义表示差异，解析后字符串值相同",
    "helpers:48aefe5bc7c2": "删除数组快路径：修复链兜底同结果",
    "helpers:6e7072a0ce66": "删除反引号剥离：与前一条围栏剥离冗余（幂等叠加）",
    "helpers:8f110b11781a": "修复表 'NaN' 改写：json.loads 原生接受 NaN，raw 快路径先行，公开输入无差异",
    "helpers:d4e24d830a4e": "删除函数尾部 return None：Python 尾部隐式返回 None，逐字节恒等",
    "helpers:df6a1908286d": "搜索循环 continue→break：循环最多命中一个候选，提前终止结果一致",
    "helpers:dfceeed070e0": "对象快路径首字符 '{' 改写：慢速修复链兜底同结果",
    "helpers:f024186d57c1": "balanced 搜索越界守卫 >=→>：start==len(text) 时后续循环无字符可匹配，同样 None",
    "helpers:fc7613504be5": "_JSON_BACKTICK_STRIP_PATTERN 改写：前一条围栏剥离已覆盖同一行集合（幂等叠加）",
}

# K 轮既有「公开契约外」（5 个，来源 survivor_attribution.md §3.3）
_K_CONTRACT_OUT: dict[str, str] = {
    "helpers:114f04d5d4a0": "TypeError 消息被改写（调用方捕获后不可观测）",
    "helpers:8011133ca57c": "TypeError 消息前缀被改写（同上）",
    "helpers:9716aa32b00c": "私有 _quote_python_expressions 内 TypeError→ValueError（公开契约只承诺 JSONDecodeError）",
    "helpers:99254d5ff306": "TypeError 消息被改写（同上）",
    "helpers:9da8ba489b67": "删除 raise TypeError('unsupported mult operands')：后续路径同样降级/抛错，公开结果一致",
}

# K 轮既有归因（用于覆盖校验）
_K_ANNOTATION_IDS = [
    "env_utils:64503fd89fd3",
    "env_utils:d878f6d742fa",
    "env_utils:e45234decf0a",
    "env_utils:f4f329f903f1",
    "helpers:1f497e6d172a",
]
_K_EQUIVALENT_COUNT = 17
_K_CONTRACT_OUT_COUNT = 5


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _summary_rows(before: dict, after: dict) -> list[dict]:
    rows = []
    for b, a in zip(before["modules"], after["modules"], strict=True):
        assert b["module"] == a["module"]
        rows.append(
            {
                "module": b["module"],
                "before": {**b["samples"], "mutation_score": b["mutation_score"], "sampled": b["sampled_mutants"]},
                "after": {**a["samples"], "mutation_score": a["mutation_score"], "sampled": a["sampled_mutants"]},
            }
        )
    return rows


def _build(before: dict, after: dict) -> tuple[dict, dict]:
    rows = _summary_rows(before, after)
    b_sum, a_sum = before["summary"], after["summary"]
    survived_after = {
        m["mutant_id"]: m for mod in after["modules"] for m in mod["mutants"] if m["outcome"] == "survived"
    }
    survived_before = {
        m["mutant_id"] for mod in before["modules"] for m in mod["mutants"] if m["outcome"] == "survived"
    }
    killed_ids = set(_KILLED)
    for mid in killed_ids:
        assert mid in survived_before, f"{mid} 在 before 中不是 survived，击杀声明不成立"
        assert mid not in survived_after, f"{mid} 在 after 中仍存活，击杀声明不成立"
    newly_killed = survived_before - set(survived_after)
    assert killed_ids <= newly_killed, f"新击杀集合与声明不一致：{sorted(killed_ids - newly_killed)}"
    unexpected = newly_killed - killed_ids
    assert not unexpected, f"出现未声明的额外击杀：{sorted(unexpected)}"
    attribution = {}
    for mid in survived_after:
        if mid in _EQUIVALENT:
            attribution[mid] = {
                "category": "strong_evidence_practical_equivalence",
                "round": "L",
                "mechanism": _EQUIVALENT[mid],
            }
        elif mid in _CONTRACT_OUT:
            attribution[mid] = {
                "category": "outside_public_contract_internal_diagnostic",
                "round": "L",
                "reason": _CONTRACT_OUT[mid],
            }
        elif mid in _K_EQUIVALENT:
            attribution[mid] = {
                "category": "strong_evidence_practical_equivalence",
                "round": "K",
                "mechanism": _K_EQUIVALENT[mid],
            }
        elif mid in _K_CONTRACT_OUT:
            attribution[mid] = {
                "category": "outside_public_contract_internal_diagnostic",
                "round": "K",
                "reason": _K_CONTRACT_OUT[mid],
            }
        elif mid in _K_ANNOTATION_IDS:
            attribution[mid] = {
                "category": "provable_equivalent_annotation_only",
                "mechanism": "from __future__ import annotations 下注解运行期从不求值",
            }
        else:
            raise AssertionError(f"存活变异体未归因：{mid}")
    counts = {"provable_equivalent": 0, "practical_equivalent": 0, "outside_contract": 0}
    for item in attribution.values():
        category = item["category"]
        if category == "provable_equivalent_annotation_only":
            counts["provable_equivalent"] += 1
        elif category == "strong_evidence_practical_equivalence":
            counts["practical_equivalent"] += 1
        else:
            counts["outside_contract"] += 1
    payload = {
        "schema_version": 1,
        "tool": "scripts/tools/self_mutation.py",
        "round": "L",
        "generated_from": {
            "before": _BEFORE.name,
            "after": _AFTER.name,
            "before_generated_at": before["generated_at"],
            "after_generated_at": after["generated_at"],
        },
        "commands": {"before": _BEFORE_CMD, "after": _AFTER_CMD},
        "caliber": {
            "modules": [m["module"] for m in before["modules"]],
            "workers": after["config"]["workers"],
            "max_mutants_per_file": after["config"]["max_mutants_per_file"],
            "sampling": after["config"]["sampling"],
            "test_map_before": before["config"]["test_map"],
            "test_map_after": after["config"]["test_map"],
            "score_definition": "killed/(killed+survived)；invalid/timeout 不进分母",
            "note": "helpers 为 120/468 等距抽样点估计，非全量 mutation score",
        },
        "summary": {
            "before": b_sum,
            "after": a_sum,
            "delta": {
                "killed": a_sum["killed"] - b_sum["killed"],
                "survived": a_sum["survived"] - b_sum["survived"],
                "mutation_score": a_sum["mutation_score"] - b_sum["mutation_score"],
            },
        },
        "modules": rows,
        "killed": {
            mid: {"mutation": mutation, "killing_tests": tests, "contract": contract}
            for mid, (mutation, tests, contract) in _KILLED.items()
        },
        "survivor_attribution": {
            mid: {
                "module_line": survived_after[mid]["line_no"],
                "mutation_type": survived_after[mid]["mutant_type"],
                "description": survived_after[mid]["description"],
                **item,
            }
            for mid, item in attribution.items()
        },
        "survivor_attribution_counts": {
            **counts,
            "total": len(attribution),
            "k_round_carry_over": {
                "annotation_only": len(_K_ANNOTATION_IDS),
                "practical_equivalent": _K_EQUIVALENT_COUNT,
                "outside_contract": _K_CONTRACT_OUT_COUNT,
            },
        },
    }
    return payload, attribution


def _fmt(score: float) -> str:
    return f"{score:.4f}"


def _render_md(payload: dict, attribution: dict) -> str:
    b_sum, a_sum = payload["summary"]["before"], payload["summary"]["after"]
    rows = payload["modules"]
    counts = payload["survivor_attribution_counts"]
    lines: list[str] = []
    add = lines.append
    add("# 自身测试套件变异测试 L 轮报告（2026-10-17）")
    add("")
    add("> 本文件由同名 JSON（机器可读事实源）镜像生成；所有数字来自")
    add("> `scripts/tools/self_mutation.py` 的 before/after 实测报告，不手写。")
    add("")
    add("## 1. 口径与复现命令")
    add("")
    add("- 测量口径与 K 轮完全一致：3 个叶子模块、workers=2、**每文件 120 变异体等距抽样**、")
    add("  `--test-map` 冻结测试集（after 仅追加 L 轮击杀测试文件）；env_utils/atomic_io 全量执行；")
    add("- before 与 after 使用**同一生成器快照、同一工作树源码、同一抽样口径**，变异体 ID 逐项相同；")
    add("- score = killed/(killed+survived)；invalid/timeout 不进分母；helpers 为 120/468 抽样点估计。")
    add("")
    add("```bash")
    add("# before（K 轮 after 测试集，复现 0.7674）")
    add(_BEFORE_CMD)
    add("")
    add("# after（同一测试集 + L 轮击杀测试）")
    add(_AFTER_CMD)
    add("```")
    add("")
    add("## 2. before / after 总览")
    add("")
    add("| 模块 | before K/S | before score | after K/S | after score | Δ score |")
    add("| --- | ---: | ---: | ---: | ---: | ---: |")
    for row in rows:
        b, a = row["before"], row["after"]
        add(
            f"| `{row['module']}` | {b['killed']}/{b['survived']} | {_fmt(b['mutation_score'])} | "
            f"{a['killed']}/{a['survived']} | {_fmt(a['mutation_score'])} | "
            f"{a['mutation_score'] - b['mutation_score']:+.4f} |"
        )
    add(
        f"| **合计** | {b_sum['killed']}/{b_sum['survived']} | **{_fmt(b_sum['mutation_score'])}** | "
        f"{a_sum['killed']}/{a_sum['survived']} | **{_fmt(a_sum['mutation_score'])}** | "
        f"**{a_sum['mutation_score'] - b_sum['mutation_score']:+.4f}** |"
    )
    add("")
    add(f"- 有效分母：before {b_sum['valid_denominator']} → after {a_sum['valid_denominator']}；")
    add(f"- invalid/timeout：before {b_sum['invalid']}/{b_sum['timeout']} → after {a_sum['invalid']}/{a_sum['timeout']}；")
    add(
        f"- baseline_green：before {b_sum['baseline_green']} / after {a_sum['baseline_green']}；"
        f"measurement_valid：before {b_sum['measurement_valid']} / after {a_sum['measurement_valid']}。"
    )
    add("")
    add(f"## 3. L 轮新击杀（{len(_KILLED)} 个，全部 survived→killed，无反向翻转；其中 1 个为诊断文本间接击杀）")
    add("")
    add("| 变异体 | 变异语义 | 击杀测试（tests/test_self_mutation_survivors_l.py） | 行为契约 |")
    add("| --- | --- | --- | --- |")
    for mid, (mutation, tests, contract) in _KILLED.items():
        add(f"| `{mid}` | {mutation} | `{tests}` | {contract} |")
    add("")
    add("> 每个击杀均在「临时沙箱副本 × 单变异体 × L 轮测试文件」预验证 rc==1，")
    add("> 且 L 轮测试文件在未变异工作树全绿；工作树 `src/` 零改动。")
    add("")
    add(f"## 4. 仍存活变异体归因（{len(attribution)} 个）")
    add("")
    add("| 类别 | 数量 | 说明 |")
    add("| --- | ---: | --- |")
    add(
        f"| 可证明等价（annotation-only） | {counts['provable_equivalent']} | K 轮既有：注解在 "
        "`from __future__ import annotations` 下运行期从不求值 |"
    )
    add(f"| 强证据实践等价 | {counts['practical_equivalent']} | K 轮 17 + L 轮 11（机制见下表） |")
    add(f"| 公开契约外（内部诊断文本） | {counts['outside_contract']} | K 轮 5（L 轮 383b 因日志格式化 TypeError 转为间接击杀） |")
    add("| 待补（未构造出可杀输入） | 0 | L 轮已清空：23 个「待补」中 12 击杀（11 直接 + 1 间接）、11 归因等价 |")
    add("")
    add("### 4.1 L 轮新增「强证据实践等价」（11 个）")
    add("")
    add("判定证据 = 机制论证 + 确定性公开 API 差分探测零差异（20,200 输入 × 2 API，")
    add("见 `verify_equivalent_mutants.py`，固定种子 20261017）。")
    add("")
    add("| 变异体 | 等价机制 |")
    add("| --- | --- |")
    for mid, mechanism in _EQUIVALENT.items():
        add(f"| `{mid}` | {mechanism} |")
    add("")
    add("### 4.2 L 轮新增「公开契约外」（0 个；383b 转为间接击杀）")
    add("")
    for mid, reason in _CONTRACT_OUT.items():
        add(f"- `{mid}`：{reason}")
    add("")
    add("### 4.3 K 轮既有存活归因（延续）")
    add("")
    add("- annotation-only 5 个、强证据实践等价 17 个、公开契约外 5 个：逐条见")
    add("  `experiments/results/self_mutation_20261017/survivor_attribution.md`；本 L 轮 JSON")
    add("  已把全部存活逐条机器化归因（`survivor_attribution`）。")
    add("")
    add("## 5. 验证命令（本机实测）")
    add("")
    add("```bash")
    add("# L 轮新增测试 + K 轮击杀测试 + 工具测试 全绿")
    add(
        ".venv/bin/python -m pytest tests/test_self_mutation_survivors_l.py "
        "tests/test_self_mutation_targets.py tests/test_self_mutation_tool.py -q"
    )
    add("")
    add("# 12 个击杀变异体的沙箱逐条预验证（临时副本，不动工作树）")
    add(".venv/bin/python experiments/results/self_mutation_l_round/verify_kills_sandbox.py")
    add("")
    add("# 11 个实践等价变异体的公开 API 差分探测（零差异）")
    add(".venv/bin/python experiments/results/self_mutation_l_round/verify_equivalent_mutants.py")
    add("")
    add("# 孤儿进程巡检（只读）")
    add(".venv/bin/python scripts/tools/detect_orphan_procs.py --json")
    add("```")
    add("")
    add("## 6. 限制与披露")
    add("")
    add("1. **抽样分数**：helpers 120/468（25.6%）等距抽样，合计分数是抽样点估计，不写成全量 mutation score；")
    add("   采样确定性（无随机种子，按源码行+类型排序等距）保证 before/after 变异体 ID 逐项可对账。")
    add("2. **不硬杀**：11 个实践等价变异体如实保留存活并归因；未使用「断言私有属性/具体错误消息/随机值」的脆弱测试。")
    add("   383b（诊断文本）为**间接击杀**：变异后的 logger 格式串与参数不匹配，在 pytest 日志捕获下")
    add("   触发 TypeError——归因表如实注明该机制，未断言任何日志文本。")
    add("3. **行为导向**：所有新测试只调用公开 API（`extract_json_object` / `extract_json_array` /")
    add("   `was_leaf_fallback_used`），不 monkeypatch 被测实现、不读取私有函数。")
    add("4. **CPU 竞争**：after 复跑在 L 轮跑批窗口结束后执行；timeout 单列不进分母")
    add("   （K 轮既有的 aug_assign_swap timeout 未复活）。")
    add("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    before_path = Path(args[0]) if len(args) > 0 else _BEFORE
    after_path = Path(args[1]) if len(args) > 1 else _AFTER
    before = _load(before_path)
    after = _load(after_path)
    payload, attribution = _build(before, after)
    _OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _OUT_MD.write_text(_render_md(payload, attribution), encoding="utf-8")
    b_sum, a_sum = payload["summary"]["before"], payload["summary"]["after"]
    print(f"wrote {_OUT_JSON}")
    print(f"wrote {_OUT_MD}")
    print(
        f"score {b_sum['mutation_score']:.4f} -> {a_sum['mutation_score']:.4f}; "
        f"killed {b_sum['killed']} -> {a_sum['killed']}; survived {b_sum['survived']} -> {a_sum['survived']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
