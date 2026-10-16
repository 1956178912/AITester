#!/usr/bin/env python3
"""Instruction artifact 清单生成器（EMSE / PROMPT-SE 复现底座，零 LLM）。

## 为什么需要它

PROMPT-SE 2026 的硬要求是"**instruction artifacts 作为一等研究对象**，并以
足以支持复现的细节报告"。本项目的 instruction artifact **全部活在源码里**
（`src/prompts/templates.py` 的四个全文系统提示 + `src/graph/nodes.py` 的两个
内联强化段落 + `src/agents/planner.py` 的动态文法段），没有独立的 prompt 文件。

因此复现底座必须是**从源码逐字抽取 + 哈希锁定**，而不是"另写一份 prompt 文档"
（那会立刻与代码漂移，正是本项目已多次吃亏的形态）。

## 本生成器做什么

1. **逐字抽取**：对每个 artifact 记录 `sha256`（内容哈希）、字符数、以及
   **注入开关**（env 名 + 默认值 + 关闭时的行为口径）；
2. **两个输出**：人类可读清单（Markdown）+ 机器可校验清单（JSON）；
3. **不写任何源码、不改任何 prompt**：本工具只读；文本权威仍是代码本身。

## 用法

    python -m experiments.prompt_artifacts --out experiments/results/prompt_artifacts_2026-10-15
    # 幂等：同源码两次运行逐字节一致（可用 SHA256SUMS 校验）

## 与门禁的关系

`scripts/gates/check_prompt_artifacts.py` 会用本生成器的**哈希表**校验清单工件
是否与当前源码一致——源码改了 prompt 而清单未刷新，门禁即红。这使"prompt 变更"
成为一次**显式动作**（与 `docs/env_budget.yaml` 的开关登记同款纪律）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from src.utils.atomic_io import atomic_write_text

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

DEFAULT_OUT_DIR = _REPO_ROOT / "experiments" / "results" / "prompt_artifacts_2026-10-15"

# ─── artifact 登记表（新增 instruction artifact 时必须在此登记）──────────────
# 字段：id / 名称 / 源位置（文件 + 抽取方式）/ 注入开关 / 关闭时行为 / 规格说明
_ARTIFACT_SPECS: tuple[dict[str, Any], ...] = (
    {
        "id": "planner_system_prompt",
        "kind": "full_system_prompt",
        "module": "src.prompts.templates",
        "attr": "PLANNER_SYSTEM_PROMPT",
        "injection": {"mode": "always", "env": None, "default": None},
        "on_disabled": "不适用（始终注入）",
        "role": "Planner 节点系统提示（生成 test_plan / logic_analysis / spec 子句）",
    },
    {
        "id": "generator_system_prompt",
        "kind": "full_system_prompt",
        "module": "src.prompts.templates",
        "attr": "GENERATOR_SYSTEM_PROMPT",
        "injection": {"mode": "always", "env": None, "default": None},
        "on_disabled": "不适用（始终注入）",
        "role": "Generator 节点系统提示（生成 pytest 测试代码）",
    },
    {
        "id": "oracle_enhancer_system_prompt",
        "kind": "full_system_prompt",
        "module": "src.prompts.templates",
        "attr": "ORACLE_ENHANCER_SYSTEM_PROMPT",
        "injection": {"mode": "always", "env": None, "default": None},
        "on_disabled": "不适用（始终注入）",
        "role": "Oracle 增强节点系统提示（断言增强）",
    },
    {
        "id": "debugger_system_prompt",
        "kind": "full_system_prompt",
        "module": "src.prompts.templates",
        "attr": "DEBUGGER_SYSTEM_PROMPT",
        "injection": {"mode": "always", "env": None, "default": None},
        "on_disabled": "不适用（始终注入）",
        "role": "Debugger 节点系统提示（生成源码补丁）",
    },
    {
        "id": "spec_expr_contract_section",
        "kind": "fragment_appended_to_user_query",
        "module": "src.prompts.templates",
        "attr": "SPEC_EXPR_CONTRACT_SECTION",
        "injection": {"mode": "default_off", "env": "SPEC_IR_DSL_ENABLE", "default": "false"},
        "on_disabled": "不追加（prompt 零变化，ADR-0003）",
        "role": "SpecExpr 表达式通道契约段（追加到 Planner 的用户查询）",
    },
    {
        "id": "detection_first_section",
        "kind": "inline_runtime_fragment",
        "module": "src.graph.nodes",
        "callable": "_detection_first_section",
        "source_lines": "src/graph/nodes.py:543-550（return 字面量）",
        "injection": {
            "mode": "default_on_gated_by_path",
            "env": "DETECTION_FIRST_SECTION_ENABLE",
            "default": "true",
            "also_requires": "再生成路径命中（_detection_first_regenerate_entry）",
        },
        "on_disabled": "保留再生成路由与计数，仅**不注入本段**（RT1 消融口径：分离协议文本效应与多一次采样效应）",
        "role": "检出优先（先红后绿）强化段——本项目的核心 instruction artifact",
    },
    {
        "id": "over_red_section",
        "kind": "inline_runtime_fragment",
        "module": "src.graph.nodes",
        "callable": "_over_red_section",
        "source_lines": "src/graph/nodes.py:650-667（return 字面量）",
        "injection": {
            "mode": "default_off_gated_by_path",
            "env": "OVER_RED_SECTION_ENABLE",
            "default": "false",
            "also_requires": "过红再生成路径命中（_specificity_over_red_regenerate_entry）",
        },
        "on_disabled": "不注入（默认关，历史口径零变化）",
        "role": "过红修复（重写为特异测试）强化段——v4 冒号放行的配对护栏",
    },
)


def _today() -> str:
    """生成日期（UTC，ISO 8601 日期部分）——与其它派生物工件的日期口径一致。"""
    import datetime

    return datetime.datetime.now(datetime.UTC).date().isoformat()


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_attr(module: str, attr: str) -> str:
    """按登记表从源码模块读取常量文本（逐字，不做任何改写）。"""
    import importlib

    mod = importlib.import_module(module)
    value = getattr(mod, attr)
    assert isinstance(value, str), f"{module}.{attr} 不是字符串（得到 {type(value).__name__}）"
    return value


def _load_inline_literal(module: str, callable_name: str) -> str:
    """从函数体**字面量**抽取内联段落文本（用 AST，避免执行依赖状态的路径）。

    这两段文本只在特定 state 下返回非 None，直接调用需要构造 state；改用 AST
    读取 `return (...)` 的字符串字面量，等价且**不依赖运行期状态**。
    多段字符串拼接（隐式连接）由 `ast.Constant` 合并后即为最终文本。
    """
    import ast
    import importlib

    mod = importlib.import_module(module)
    src_file = Path(mod.__file__ or "")
    tree = ast.parse(src_file.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == callable_name:
            for sub in ast.walk(node):
                if isinstance(sub, ast.Return) and isinstance(sub.value, ast.Constant):
                    value = sub.value.value
                    if isinstance(value, str):
                        return value
    raise AssertionError(f"未在 {module}.{callable_name} 中找到字符串字面量返回")


def collect_artifacts() -> list[dict[str, Any]]:
    """按登记表抽取全部 instruction artifact（含哈希与注入口径）。"""
    rows: list[dict[str, Any]] = []
    for spec in _ARTIFACT_SPECS:
        if "attr" in spec:
            text = _load_attr(spec["module"], spec["attr"])
            location = f"{spec['module'].replace('.', '/')}.py::{spec['attr']}"
        else:
            text = _load_inline_literal(spec["module"], spec["callable"])
            location = spec.get("source_lines", spec["module"])
        rows.append(
            {
                "id": spec["id"],
                "kind": spec["kind"],
                "role": spec["role"],
                "location": location,
                "injection": spec["injection"],
                "on_disabled": spec["on_disabled"],
                "sha256": _sha256(text),
                "chars": len(text),
                "lines": text.count("\n") + 1,
                "text": text,
            }
        )
    return rows


def build_markdown(rows: list[dict[str, Any]], *, json_name: str) -> str:
    total_chars = sum(r["chars"] for r in rows)
    lines: list[str] = [
        "# Instruction Artifact 清单（逐字抽取 + 哈希锁，PROMPT-SE 复现底座）",
        "",
        "- 生成：`python -m experiments.prompt_artifacts`（零 LLM；只读源码，不改写任何 prompt）",
        f"- artifact 数：**{len(rows)}**；合计 **{total_chars}** 字符",
        f"- 机器可校验清单：`{json_name}`（同目录 JSON，含全文与 sha256）",
        "",
        "> **口径**：本清单的文本是**从源码逐字抽取**的产物；权威仍是代码本身。",
        "> 源码改动而未刷新本清单 → `scripts/gates/check_prompt_artifacts.py` 报红，",
        "> 使 prompt 变更成为一次**显式动作**（与 `docs/env_budget.yaml` 开关登记同款纪律）。",
        "",
        "## 1. artifact 总表",
        "",
        "| # | id | 类型 | 注入开关（默认） | 关闭时行为 | sha256（前 12 位） | 字符 | 行 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for idx, row in enumerate(rows, 1):
        inj = row["injection"]
        if inj.get("env"):
            switch = f"`{inj['env']}`（默认 {inj['default']}）"
            if inj.get("also_requires"):
                switch += f" + {inj['also_requires']}"
        else:
            switch = "始终注入"
        lines.append(
            f"| {idx} | `{row['id']}` | {row['kind']} | {switch} | {row['on_disabled']} | "
            f"`{row['sha256'][:12]}` | {row['chars']} | {row['lines']} |"
        )
    lines += [
        "",
        "## 2. 逐 artifact 全文（逐字）",
        "",
    ]
    for idx, row in enumerate(rows, 1):
        lines += [
            f"### 2.{idx} `{row['id']}`",
            "",
            f"- 角色：{row['role']}",
            f"- 源位置：`{row['location']}`",
            f"- sha256：`{row['sha256']}`",
            f"- 规模：{row['chars']} 字符 / {row['lines']} 行",
            "",
            "```text",
            row["text"].rstrip("\n"),
            "```",
            "",
        ]
    lines += [
        "## 3. 复现者须知（诚实边界）",
        "",
        "1. 本清单覆盖**登记表的 artifact 全集**；新增 instruction artifact 必须先在",
        "   `experiments/prompt_artifacts.py::_ARTIFACT_SPECS` 登记，否则不会被抽取。",
        "2. `planner.py` 的动态文法段（`SPEC_EXPR_GRAMMAR_SECTION`，由 `spec_ir_v2` 常量拼装）",
        "   **未纳入本清单**——它是运行期拼装产物，需在执行期抓取（属后续工作，见状态登记册 §4）。",
        "3. 注入的**上下文**（被测代码、诊断、覆盖率、边界三元组等）不在本清单内；",
        "   它们由各构建器在运行期产生，逐次结果记录在批次工件 provenance 与 trace 中。",
        "4. 全文以 UTF-8 逐字给出，未做任何标点/空格规范化——哈希即按此文本计算。",
    ]
    return "\n".join(lines) + "\n"


def _call_sites() -> dict[str, list[str]]:
    """按 AST 统计 `json_mode=True` 的显式实参调用点（与 JSON 契约门禁同口径）。

    不硬编码数字：调用点增减会同时反映到本卡，并由
    `scripts/gates/check_json_contract_sites.py` 独立报红——两处不可能同时漂移而不被发现。
    """
    import ast

    sites: dict[str, list[str]] = {}
    for path in sorted((_REPO_ROOT / "src").rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and any(
                kw.arg == "json_mode" and isinstance(kw.value, ast.Constant) and kw.value.value is True
                for kw in node.keywords
            ):
                sites.setdefault(str(path.relative_to(_REPO_ROOT)), []).append(node.lineno)
    # 行号按数值排序（字符串排序会把 1078 排在 622 前面），并转成字符串供渲染
    return {path: [str(n) for n in sorted(nums)] for path, nums in sites.items()}


def build_prompt_card(rows: list[dict[str, Any]], *, generated_at: str) -> str:
    """Prompt Card（投稿用派生件）：全文 + 哈希 + 注入口径 + 调用点 + 复现步骤。

    **自动生成，不手工编辑**：本卡每个字符都来自源码；手工改动会在下次生成时被覆盖，
    且 `check_prompt_artifacts.py` 会对哈希对账报红。
    """
    core = next((r for r in rows if r["id"] == "detection_first_section"), None)
    sites = _call_sites()
    site_count = sum(len(v) for v in sites.values())
    lines: list[str] = [
        "# Prompt Card — AITester instruction artifacts 全文与注入口径",
        "",
        f"> 自动生成（{generated_at}；生成器：`experiments/prompt_artifacts.py`）。"
        "**请勿手工编辑**：本卡每个字符均逐字取自源码，手工改动会在下次生成时被覆盖，"
        "并由 `scripts/gates/check_prompt_artifacts.py` 的哈希对账报红。",
        "",
        "## 0. 用途与边界",
        "",
        "本卡是 EMSE / PROMPT-SE 类投稿所需的 instruction artifact 复现材料，覆盖：",
        "",
        f"- **{len(rows)} 个 instruction artifact** 的全文（逐字）、sha256、注入口径（env + 默认值 + 关闭时行为）；",
        f"- **{site_count} 个 JSON 契约调用点**（`json_mode=True` 显式实参，与 "
        "`check_json_contract_sites.py` 同口径）；",
        "- 复现步骤与已知边界（见 §4）。",
        "",
        "**边界（诚实声明）**：",
        "1. 本卡**不含**运行期拼装的上下文（被测代码、诊断、覆盖率、边界三元组等）——",
        "   它们由各构建器在运行期产生，逐次记录在批次工件 provenance 与 trace 中；",
        "2. `planner.py` 的动态文法段（`SPEC_EXPR_GRAMMAR_SECTION`，由 `spec_ir_v2` 常量拼装）",
        "   未纳入（运行期产物，需执行期抓取）；",
        "3. 文本权威是源码本身；本卡是派生物。",
        "",
        "## 1. detection-first 协议段（核心 artifact，全文）",
        "",
    ]
    if core is not None:
        lines += [
            f"- id：`{core['id']}`；sha256：`{core['sha256']}`；{core['chars']} 字符",
            f"- 源位置：`{core['location']}`",
            f"- 注入口径：`{core['injection'].get('env')}`（默认 {core['injection'].get('default')}）"
            f"，且需 {core['injection'].get('also_requires', '—')}",
            f"- 关闭时行为：{core['on_disabled']}",
            "",
            "```text",
            core["text"].rstrip(),
            "```",
            "",
        ]
    lines += [
        "## 2. 其余 artifact 全文",
        "",
    ]
    for row in rows:
        if row["id"] == "detection_first_section":
            continue
        inj = row["injection"]
        switch = f"`{inj['env']}`（默认 {inj['default']}）" if inj.get("env") else "始终注入"
        lines += [
            f"### 2.{row['id']}",
            "",
            f"- 角色：{row['role']}；注入：{switch}；关闭时：{row['on_disabled']}",
            f"- 源位置：`{row['location']}`；sha256：`{row['sha256']}`；{row['chars']} 字符",
            "",
            "```text",
            row["text"].rstrip(),
            "```",
            "",
        ]
    lines += [
        "## 3. JSON 契约调用点（口径 A）",
        "",
        "| 文件 | 行号 |",
        "|---|---|",
    ]
    for path, linenos in sorted(sites.items()):
        lines.append(f"| `{path}` | {', '.join(linenos)} |")
    lines += [
        "",
        f"合计 **{site_count}** 处；权威计数由 `scripts/gates/check_json_contract_sites.py`"
        "（AST 计数 + 5 份文档声明一致性）独立把守。",
        "",
        "## 4. 复现步骤",
        "",
        "```bash",
        "# 1) 抽取（零 LLM、只读源码；幂等）",
        "python -m experiments.prompt_artifacts",
        "# 2) 哈希锁自检（清单与源码逐位一致；strict 要求清单存在）",
        "python scripts/gates/check_prompt_artifacts.py --strict",
        "# 3) JSON 契约调用点计数一致性",
        "python scripts/gates/check_json_contract_sites.py",
        "```",
        "",
        "## 5. 待确认项（投稿前须由作者确认）",
        "",
        "- [ ] 确认 §1 与 §2 的全文与**当前实际运行的 prompt** 逐字一致"
        "（尤其 detection-first 段与 over-red 段为内联代码字面量）；",
        "- [ ] 确认注入口径描述与实际运行档位一致（默认值见各条 `injection`）；",
        "- [ ] 确认后可将本卡（或其等价内容）作为论文附录 / 复现包 `PROMPT_CARD.md` 发布，"
        "并把哈希升级为**冻结值**（改动即红，而非仅要求刷新清单）。",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Instruction artifact 清单生成（零 LLM）")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args(argv)

    rows = collect_artifacts()
    payload = {
        "generated_by": "experiments/prompt_artifacts.py",
        "count": len(rows),
        "total_chars": sum(r["chars"] for r in rows),
        "artifacts": rows,
    }
    args.out.mkdir(parents=True, exist_ok=True)
    json_path = args.out / "PROMPT_ARTIFACTS.json"
    md_path = args.out / "PROMPT_ARTIFACTS.md"
    card_path = args.out / "PROMPT_CARD.md"
    atomic_write_text(json_path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n", mode=0o644)
    md_path.write_text(build_markdown(rows, json_name=json_path.name), encoding="utf-8")
    card_path.write_text(build_prompt_card(rows, generated_at=_today()), encoding="utf-8")
    # SHA256SUMS：与仓库其它工件目录同口径（可 checksum_results 校验）
    sums = args.out / "SHA256SUMS"
    sums.write_text(
        "\n".join(f"{_sha256(p.read_text(encoding='utf-8'))}  {p.name}" for p in (json_path, md_path, card_path))
        + "\n",
        encoding="utf-8",
    )

    print(f"[prompt-artifacts] 目录：{args.out}")
    for row in rows:
        print(f"  {row['id']:<34} {row['chars']:>5} chars  sha256={row['sha256'][:12]}")
    print(f"[prompt-artifacts] 合计 {payload['count']} 个 artifact / {payload['total_chars']} 字符")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
