"""验收 oracle 类型标签的单一事实源（BT 轮，2026-10-22）。

背景：`oracle_type` / `test_visible_to_system` 是 R52 引入的 APR 严谨性检查点，
但写入端把可见性硬编码为 `True`、类型恒为 `generated_test`——SWE-bench 的
仓库级验收（gold FAIL_TO_PASS/PASS_TO_PASS）被标成"生成测试验收且系统可见"，
与事实相反（gold 测试不进入任何 agent prompt）。标签收敛到本模块，供写入端
（`run_benchmark._oracle_descriptor`）与报告读端（`statistical_analysis`）共用。
"""

from __future__ import annotations

#: 本地验收：LLM 自生成测试的通过性（测试对系统可见）。
ORACLE_TYPE_GENERATED = "generated_test"

#: 本地验收：规约增强后的生成测试（仍对系统可见）。
ORACLE_TYPE_ENHANCED = "enhanced_generated_test"

#: 仓库级验收：gold FAIL_TO_PASS / PASS_TO_PASS 实测（gold 测试对系统不可见）。
ORACLE_TYPE_REPO_GOLD = "gold_fail_to_pass"

#: 词表（报告端"词表外取值"单列点名用；新增取值必须同时进这里）。
ORACLE_TYPES: tuple[str, ...] = (
    ORACLE_TYPE_GENERATED,
    ORACLE_TYPE_ENHANCED,
    ORACLE_TYPE_REPO_GOLD,
)
