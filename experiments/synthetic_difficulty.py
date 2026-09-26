"""
4.3 合成数据集多层难度任务生成器（Level 1-4 难度分层构造）。

背景：
    当前合成数据集（占 benchmark 88%）存在天花板效应——变异得分全部 1.0，
    多候选仅 +2%，跨文件 +0%。根因是所有合成任务都是"单函数简单缺陷"
    （Level 1），LLM 一次即可修复，无法暴露跨文件 / 多函数交互 / 边界异常
    路径的短板。

    本模块提供多层难度任务构造器（纯代码生成，无 LLM 依赖，可复算）：
    - Level 1：单函数简单缺陷（现状基线）；
    - Level 2：多函数交互缺陷（需修改 2-3 个函数，缺陷藏在调用链中）；
    - Level 3：跨文件依赖缺陷（需修改 2+ 文件，import 链 / 接口契约约束）；
    - Level 4：边界条件与异常路径的隐蔽缺陷（正常路径全绿，仅边界/异常
      分支触发）。

    每个 Level 生成器返回一个 SyntheticTask（target_code + 注入的缺陷 +
    expected_fix_hint + 可复算的 defect_type 标签），供合成数据集构造与
    难度分层实验（stratify_by_dimension 的"难度等级"维度）消费。

设计约束（与 mutation_testing / difficulty_stratification 同口径）：
    - 纯标准库 + 字符串模板，零 LLM / 零外部硬依赖，可复算；
    - 缺陷注入是"保守变异"（仅改返回值 / 运算符 / 边界条件 / 异常分支），
      保证 expected 行为明确可判定；
    - Level 3 的跨文件任务生成"两个模块源码 + 依赖边"，与 cross_file 工具
      的 CrossFileDependency schema 对齐；
    - 生成的任务 target_code 可被 ast.parse（语法合法，保证 executor 可运行）。
"""

from __future__ import annotations

import ast
import random
from dataclasses import dataclass, field
from typing import Any

# ─── 合成任务定义 ──────────────────────────────────────────────────────────


@dataclass
class SyntheticTask:
    """单个合成难度任务。

    Attributes:
        task_id: 任务标识（含 level 标签，如 "syn_L2_multifunc_001"）。
        level: 难度等级（1-4）。
        target_code: 被测模块源码（含注入的缺陷）。
        defect_description: 缺陷描述（供复现测试 / 诊断消费）。
        expected_fix_hint: 期望修复方向提示（供实验分析，不注入 LLM prompt）。
        target_function: 主要被测函数名（Level 2-4 可能有多个，取入口）。
        module_name: 模块名（不含 .py）。
        extra_modules: 跨文件任务的额外模块 {module_name: code}（Level 3）。
        cross_file_deps: 跨文件依赖边（Level 3，与 cross_file schema 对齐）。
    """

    task_id: str
    level: int
    target_code: str
    defect_description: str
    expected_fix_hint: str
    target_function: str
    module_name: str = "target_module"
    extra_modules: dict[str, str] = field(default_factory=dict)
    cross_file_deps: list[dict[str, Any]] = field(default_factory=list)

    def to_state_fields(self) -> dict[str, Any]:
        """转工作流初始状态字段（与 create_initial_state 对齐）。"""
        return {
            "target_code": self.target_code,
            "target_function": self.target_function,
            "module_name": self.module_name,
            "task_uuid": self.task_id,
        }


# ─── Level 1：单函数简单缺陷（现状基线）────────────────────────────────────


def generate_level1_task(rng: random.Random | None = None) -> SyntheticTask:
    """Level 1：单函数简单缺陷（边界值 / 运算符错误）。

    注入缺陷：把正确的 `>=` 边界写成 `>`（或把 `+` 写成 `-`），
    正常路径部分正确，仅特定输入触发。
    """
    rng = rng or random.Random()
    # 正确实现：分段计费（边界 >= 阈值）
    threshold = rng.choice([10, 100, 1000])
    discount = rng.choice([0.1, 0.05, 0.2])
    buggy_code = (
        f"def price_item(amount, threshold={threshold}, discount={discount}):\n"
        f"    # 缺陷：应为 amount > threshold 时打折，误写为 amount >= threshold\n"
        f"    if amount >= threshold:\n"
        f"        return amount * (1 - discount)\n"
        f"    return amount\n"
    )
    return SyntheticTask(
        task_id=f"syn_L1_single_{rng.randint(1000, 9999)}",
        level=1,
        target_code=buggy_code,
        defect_description=(f"price_item 在 amount 恰好等于 {threshold} 时错误地打了折（应为严格大于阈值才打折）。"),
        expected_fix_hint=f"把 if amount >= {threshold} 改为 if amount > {threshold}",
        target_function="price_item",
        module_name="pricing",
    )


# ─── Level 2：多函数交互缺陷（需修改 2-3 个函数）──────────────────────────


def generate_level2_task(rng: random.Random | None = None) -> SyntheticTask:
    """Level 2：多函数交互缺陷（缺陷藏在调用链中，需修改 2 个函数）。

    注入缺陷：
    - parse_record 把字段顺序解析错（把 amount 解析成 fee）；
    - compute_fee 依赖 parse_record 返回的 dict，但 parse_record 返回的 key
      名与 compute_fee 期望的 key 名不一致（一个用 "amt" 一个用 "amount"），
      导致 compute_fee 永远拿到默认值 0。
    修复需同时改 parse_record 的 key 名 + compute_fee 的读取 key。
    """
    rng = rng or random.Random()
    buggy_code = (
        "def parse_record(raw):\n"
        "    # 缺陷：raw = [timestamp, amount, fee]，但 dict key 用 'amt'（应为 'amount'）\n"
        "    return {'ts': raw[0], 'amt': raw[1], 'fee': raw[2]}\n\n"
        "def compute_fee(record, rate=0.1):\n"
        "    # 缺陷：期望 record['amount']，但 parse_record 提供的是 'amt'，拿到默认 0\n"
        "    amount = record.get('amount', 0)\n"
        "    return amount * rate\n"
    )
    return SyntheticTask(
        task_id=f"syn_L2_multifunc_{rng.randint(1000, 9999)}",
        level=2,
        target_code=buggy_code,
        defect_description=(
            "compute_fee 永远返回 0：它读 record['amount']，但 parse_record "
            "产出的是 record['amt']，key 名不一致导致 .get 拿到默认 0。"
            "需同时修 parse_record 的 key 名 与 compute_fee 的读取 key。"
        ),
        expected_fix_hint="把 parse_record 的 'amt' 改为 'amount'（或 compute_fee 读 'amt'）",
        target_function="compute_fee",
        module_name="records",
    )


# ─── Level 3：跨文件依赖缺陷（需修改 2+ 文件）─────────────────────────────


def generate_level3_task(rng: random.Random | None = None) -> SyntheticTask:
    """Level 3：跨文件依赖缺陷（需修改 2 个文件 + 保持接口契约）。

    注入缺陷：
    - 模块 `utils` 的 validate_id 正确校验 id 长度 [1, 12]；
    - 模块 `entry` 调用 utils.validate_id，但 entry 自己又内联了一份
      错误的本地 _validate_id（长度误写为 [1, 10]），且 entry 的实际
      业务函数 process 用的是本地 _validate_id 而非 utils.validate_id，
      导致 11-12 位的合法 id 被错误拒绝。
    修复需改 entry 的 process 改用 utils.validate_id（跨文件调用契约），
    并保证 entry 的公共接口 process 名不变（命名契约）。
    """
    rng = rng or random.Random()
    utils_code = (
        "def validate_id(value):\n"
        "    '''校验 id 长度 [1, 12]。'''\n"
        "    if not isinstance(value, str):\n"
        "        raise TypeError('id must be str')\n"
        "    if not (1 <= len(value) <= 12):\n"
        "        raise ValueError('id length must be 1..12')\n"
        "    return True\n"
    )
    entry_code = (
        "from utils import validate_id  # 导入了但实际未用\n"
        "\n"
        "def _validate_id(value):\n"
        "    # 缺陷：本地实现误写为 [1, 10]\n"
        "    if not isinstance(value, str) or not (1 <= len(value) <= 10):\n"
        "        raise ValueError('bad id')\n"
        "    return True\n"
        "\n"
        "def process(user_id, payload):\n"
        "    _validate_id(user_id)\n"
        "    return {'ok': True, 'id': user_id, 'size': len(payload)}\n"
    )
    deps = [
        {
            "source_module": "entry",
            "target_module": "utils",
            "symbol": "validate_id",
            "call_line": 1,
            "context": "from utils import validate_id（导入但 process 实际用了本地 _validate_id）",
        }
    ]
    return SyntheticTask(
        task_id=f"syn_L3_crossfile_{rng.randint(1000, 9999)}",
        level=3,
        target_code=entry_code,
        defect_description=(
            "entry.process 用本地 _validate_id（长度 [1,10]）而非 utils.validate_id"
            "（[1,12]），导致 11-12 位合法 id 被拒。需把 process 改用 utils.validate_id。"
        ),
        expected_fix_hint="entry.process 调用 utils.validate_id 而非本地 _validate_id",
        target_function="process",
        module_name="entry",
        extra_modules={"utils": utils_code},
        cross_file_deps=deps,
    )


# ─── Level 4：边界条件与异常路径的隐蔽缺陷（正常全绿，仅边界/异常触发）────


def generate_level4_task(rng: random.Random | None = None) -> SyntheticTask:
    """Level 4：隐蔽缺陷（正常路径全绿，仅异常 / 边界分支触发）。

    注入缺陷：
    - safe_div 正常路径正确，但除零分支 `if b == 0: return 0` 在 b 为
      float 0.0 或 -0.0 时，因 `b == 0` 为 True 也返回 0（看似对），
      但调用方期望除零时返回 None（调用方用 `result is None` 判定除零）；
    - 隐藏缺陷：b 为 0 时返回 0 而非 None，调用方 `if x is None` 永远
      不触发 → 除零未被识别。正常输入（b≠0）全绿，仅 b=0 的异常路径
      暴露缺陷。
    """
    rng = rng or random.Random()
    buggy_code = (
        "def safe_div(a, b):\n"
        "    '''返回 a / b；除零时返回 None。'''\n"
        "    if b == 0:\n"
        "        # 缺陷：除零应返回 None，误返回 0（调用方用 is None 判定除零）\n"
        "        return 0\n"
        "    return a / b\n"
    )
    return SyntheticTask(
        task_id=f"syn_L4_boundary_{rng.randint(1000, 9999)}",
        level=4,
        target_code=buggy_code,
        defect_description=(
            "safe_div 除零时返回 0 而非 None，调用方 `if result is None` 永远"
            "不触发，除零未被识别。正常输入（b≠0）全绿，仅 b=0 异常路径暴露缺陷。"
        ),
        expected_fix_hint="除零分支改为 return None",
        target_function="safe_div",
        module_name="arithmetic",
    )


# ─── 统一生成入口 ─────────────────────────────────────────────────────────


_LEVEL_GENERATORS = {
    1: generate_level1_task,
    2: generate_level2_task,
    3: generate_level3_task,
    4: generate_level4_task,
}


def generate_synthetic_task(level: int, rng: random.Random | None = None) -> SyntheticTask:
    """按难度等级生成一个合成任务（1-4）。

    Args:
        level: 难度等级（1-4，见模块 docstring 各 Level 说明）。
        rng: 随机数发生器（可注入保证可复算；None 时用系统随机）。

    Returns:
        SyntheticTask 实例。level 越界抛 ValueError。

    生成后做 ast.parse 自检（保证 target_code 语法合法，executor 可运行）。
    """
    if level not in _LEVEL_GENERATORS:
        raise ValueError(f"未知难度等级: {level}（支持 1-4）")
    task = _LEVEL_GENERATORS[level](rng=rng)
    # 语法自检：保证生成的被测代码可被 ast.parse（缺陷是语义级，非语法级）
    try:
        ast.parse(task.target_code)
    except (SyntaxError, ValueError) as e:
        raise ValueError(f"Level {level} 生成的 target_code 语法不合法: {e}") from e
    # Level 3 额外模块也做语法自检
    for mod_name, mod_code in (task.extra_modules or {}).items():
        try:
            ast.parse(mod_code)
        except (SyntaxError, ValueError) as e:
            raise ValueError(f"Level 3 额外模块 {mod_name} 语法不合法: {e}") from e
    return task


def generate_synthetic_suite(
    counts: dict[int, int] | None = None,
    seed: int = 42,
) -> list[SyntheticTask]:
    """生成多层难度合成任务套件（供合成数据集构造 / 难度分层实验消费）。

    Args:
        counts: 各 Level 数量 {1: n1, 2: n2, 3: n3, 4: n4}。
            缺省时 {1: 3, 2: 3, 3: 2, 4: 2}（保守默认，保证各层都有样本）。
        seed: 随机种子（可复算口径，默认 42）。

    Returns:
        SyntheticTask 列表（按 level 升序，同 level 内按生成序）。
    """
    counts = counts or {1: 3, 2: 3, 3: 2, 4: 2}
    rng = random.Random(seed)
    tasks: list[SyntheticTask] = []
    # PERF401：extend + 生成器替代逐次 append（语义与循环完全等价）
    for level in sorted(counts.keys()):
        tasks.extend(generate_synthetic_task(level, rng=rng) for _ in range(int(counts[level] or 0)))
    return tasks


def summarize_suite(tasks: list[SyntheticTask]) -> dict[str, Any]:
    """汇总合成任务套件（供实验报告 / 难度分层消费）。

    Returns:
        {"total": int, "by_level": {level: count},
         "with_cross_file": int, "with_multi_func": int}
    """
    by_level: dict[int, int] = {}
    for t in tasks:
        by_level[t.level] = by_level.get(t.level, 0) + 1
    return {
        "total": len(tasks),
        "by_level": {str(k): v for k, v in sorted(by_level.items())},
        "with_cross_file": sum(1 for t in tasks if t.level == 3),
        "with_multi_func": sum(1 for t in tasks if t.level == 2),
    }


# ─── CLI：生成多层难度合成任务并输出为 benchmark 可消费的 JSONL ─────────────


def _render_cli() -> None:
    """CLI 入口：生成多层难度合成任务并打印 / 写入 JSONL。

    用法：
        python -m experiments.synthetic_difficulty \
            --counts '{"1":3,"2":3,"3":2,"4":2}' --seed 42 \
            --output experiments/results/synthetic_suite.jsonl
    """
    import argparse
    import json

    parser = argparse.ArgumentParser(description="4.3 多层难度合成任务生成器")
    parser.add_argument(
        "--counts",
        default='{"1":3,"2":3,"3":2,"4":2}',
        help='各 Level 数量（JSON 字符串，如 \'{"1":3,"2":3,"3":2,"4":2}\'）',
    )
    parser.add_argument("--seed", type=int, default=42, help="随机种子（默认 42，可复算）")
    parser.add_argument("--output", default=None, help="JSONL 输出路径（缺省打印到 stdout）")
    args = parser.parse_args()

    counts = {int(k): int(v) for k, v in json.loads(args.counts).items()}
    tasks = generate_synthetic_suite(counts=counts, seed=args.seed)
    summary = summarize_suite(tasks)

    rows = []
    for t in tasks:
        row = {
            "task_id": t.task_id,
            "difficulty_level": t.level,
            "module_name": t.module_name,
            "target_function": t.target_function,
            "instance_code": t.target_code,
            "defect_description": t.defect_description,
            "expected_fix_hint": t.expected_fix_hint,
            "extra_modules": t.extra_modules,
            "cross_file_deps": t.cross_file_deps,
        }
        rows.append(row)

    if args.output:
        out_path = args.output
        import os

        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"已生成 {summary['total']} 个合成任务（{summary['by_level']}）→ {out_path}")
    else:
        for row in rows:
            print(json.dumps(row, ensure_ascii=False))
    print(f"套件汇总: {json.dumps(summary, ensure_ascii=False)}")


if __name__ == "__main__":
    _render_cli()
