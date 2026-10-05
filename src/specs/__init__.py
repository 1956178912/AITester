"""SpecIR（R7，2026-09-30 独立审查 P0）：可执行规约中间表示。

背景：
    AITester 的"逻辑驱动"测试生成依赖 LLM 输出的 `logic_analysis`
    （5 个自然语言字段：输入域 / 输出域 / 前置条件 / 后置条件 /
    边界情况）。自然语言规约**无语法、无类型、无语义、不可执行**——
    评审及格线 #1（"指标可信"）要求把"逻辑驱动"从"可静默退化为空
    规约"升级为"可证伪、可消融"：规约必须能被机器解析、校验、并
    编译为可执行的测试预言（oracle）。

本模块（纯 Python 路线，2–3 人日，无需先上 z3）：
    1. **SpecIR 定义**：JSON Schema 描述的受限规约 IR（`spec_ir.py`）；
    2. **解析**：把 Planner 的 `logic_analysis`（自然语言字段 + 结构化
       边界三元组）解析为 SpecIR（保守降级：解析失败 → None，不阻断）；
    3. **校验**：SpecIR 的 schema 强校验（`validate_spec_ir`，必填字段
       + 类型 + 非空），失败返回 findings（纯观测）；
    4. **编译到 Hypothesis 策略**：SpecIR 的 `boundary` / `invariant`
       字段编译为 Hypothesis 属性测试代码字符串（oracle 转换，
       `compile_to_hypothesis`），hypothesis 缺失时降级为"生成 pytest
       参数化断言"（纯 stdlib 路径，零依赖）。

设计口径（保守、默认关、零 LLM 成本）：
    - SPEC_IR_ENABLE=false（默认）时，调用方不调本模块，历史口径零变化；
    - 开启后，Planner 输出 logic_analysis → 解析为 SpecIR → 校验 findings
      渲染为"规约缺陷清单"段落注入下一轮 Generator prompt；
    - 编译 Hypothesis 策略 / pytest 参数化断言为确定性 oracle（替代
      LLM 自由断言），提升"断言太弱导致假通过"的检出率；
    - 所有失败路径保守降级（None / 空串），不阻断生成主流程。
"""

from __future__ import annotations

__all__ = [
    "compile_to_hypothesis",
    "extract_signature_params",
    "parse_logic_analysis",
    "spec_ir_enabled",
    "validate_spec_ir",
]

from src.specs.spec_ir import (
    compile_to_hypothesis,
    extract_signature_params,
    parse_logic_analysis,
    spec_ir_enabled,
    validate_spec_ir,
)
from src.specs.spec_ir_v2 import (
    compile_readiness,
    compile_spec_oracle,
    is_expression_clause,
    spec_ir_dsl_enabled,
    spec_provenance,
)

__all__ += [
    "compile_readiness",
    "compile_spec_oracle",
    "is_expression_clause",
    "spec_ir_dsl_enabled",
    "spec_provenance",
]
