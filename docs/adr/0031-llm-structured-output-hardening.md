# ADR-0031: LLM 结构化输出加固（JSON Output + 数值表达式解析修复 + finish_reason 守卫）

- **日期**：2026-10-14
- **状态**：已采纳（JSON 模式默认 on，含 `LLM_JSON_MODE=off` 历史口径逃生门）
- **关联模块**：`src/agents/llm_client.py`、`src/agents/base_agent.py`、`src/agents/planner.py`、`src/agents/debugger.py`、`src/utils/helpers.py`、`experiments/run_benchmark.py`、`docs/env_budget.yaml`

## 背景

2026-10-14 EMSE 批次日志审计（按 DeepSeek 官方文档逐条归因）：日志中
"执行失败/重试/超时"字样绝大多数**非故障**——「第 N 次执行失败，尝试重试」
是执行器对 pytest 变红的重试（**检测信号本身**，检测到缺陷的正常路径，
75 任务日志中 161 次）；「执行超时（>30s）」是测试侧挂起保护（挂起测试 ×
30s 上限）；API 侧零 429/连接错误。**真正的 LLM 侧缺陷是结构化输出解析
失败**：`M10：LLM 未输出 logic_analysis`（6/75 任务）、Debugger
`llm_json_parse_failed` 严格重试路径多次触发。

根因分析（真实响应取证）：

1. **JSON 语法非法**：LLM 在 JSON 值位置写 Python 数值表达式
   （`10**18`、`10**18+1`、`10_000`）——JSON 非法；既有修复链
   （字符串表达式/元组键）不含数值路径 → 解析失败 → **叶子回退静默返回
   错误片段**（`{'items': ...}`）→ 被误诊为"LLM 未输出 logic_analysis"
   （实为提取器缺陷——LLM 输出了完整正确的 JSON）；
2. **结构化契约无运行时约束**：Planner/Debugger 的调用契约均为 JSON 对象，
   但请求未使用 DeepSeek 官方 JSON Output（`response_format=
   {"type":"json_object"}`，官方保证响应为合法 JSON 字符串）；
3. **截断/资源中断静默**：响应 `finish_reason ∈ {length,
   insufficient_system_resource}` 时残缺内容仍被交给下游解析。

## 决策

三项加固，均按 DeepSeek 官方文档配置：

1. **JSON Output（`LLM_JSON_MODE`，默认 on）**：7 处 JSON 契约调用点显式传
   `json_mode=True`（Planner 测试计划；Debugger 补丁/严格重试/批评者重查/
   击穿用例/缺陷分类；FaultLocalizer 定位），请求绑定
   `response_format={"type":"json_object"}`。
   官方前置条件已逐一核查（提示须含 "JSON" 字样与格式示例——全部满足）；
   官方已知"偶发空响应"由既有空响应重试承接。**默认 on** 沿 AD1
   `LLM_THINKING_MODE` 的"行为默认值"先例（成本/可靠性保护优先）；
   `off` 时请求体与历史逐字节一致（旧批次复现/回归对照）。配置入
   `env_budget.yaml` 与 `_env_snapshot_keys`（双登记），provenance 可审计。
   代码生成类调用（Generator 测试、重采样补丁）**不**受影响——避免把
   代码输出强制成 JSON；zai 兼容路径不支持该参数，保守忽略。
2. **数值表达式 JSON 修复**（`_normalize_python_numeric_expressions`）：
   值位置的纯数值 Python 表达式换算为等值 JSON 数字字面量。**受限求值
   无 eval**（仅 常量/一元正负/`+ - *`/`**`），指数 ≤4096 有界、结果位数
   ≤4096 有界、字符串内位置防护（引号奇偶扫描）、已是合法 JSON 数字零
   改动。接入 `_repair_json_bounded` 修复链（所有提取路径共享）。
3. **finish_reason 守卫**：`length`（max_tokens 截断）/
   `insufficient_system_resource`（推理资源中断）→ 按可恢复失败重试
   （指数退避 + 跨模型故障转移），不把残缺内容交给下游解析。

## 后果

- **验证**：修复前 3 任务冒烟 1 次 M10（task_0000 回退默认计划）→ 修复后
  **M10=0，3/3 任务产出完整计划**；缓存真实样本回归 9/9（覆盖
  `10**18`、`10**18+1`、双对象背靠背两类失败形态）；新增 36 例测试
  （JSON 模式 21 + 数值修复 15）锁定行为；受影响套件全绿（197 例）。
- **口径影响**：JSON 模式改变结构化调用的采样约束（默认 on）——复现
  2026-10-14 之前批次须显式 `LLM_JSON_MODE=off`；数值修复为**纯解析层**
  改进，对历史请求零影响（历史原始响应在新代码下解析更完整，已入库
  工件不受影响）。
- **M10 / logic_degraded 率下降**：此前约 7-8% 任务（6/75）触发 M10 降级，
  其中大部分实为解析缺陷而非 LLM 缺字段——"逻辑驱动"路径的实际覆盖率
  比历史记录更高（对 EMSE 报告的 logic_degraded 统计有正向影响）。
- 新增 21 例 `test_llm_json_mode.py` + 15 例 `test_json_repair_layer.py`
  数值修复用例锁定行为（含字符串内防护、指数界、非数值构造拒绝）。

## 已知局限与演进方向

- **已知局限**：① JSON Output 偶发空响应（官方已知问题）依赖既有重试，
  极端情况下仍可能跨模型故障转移；② 数值修复只覆盖"纯数值表达式"——
  含变量/函数调用的表达式（如 `len(x)**2`）仍保守失败（交既有降级链）；
  ③ max_tokens 未显式调高（非思考默认 8K 对当前输出量足够），截断仅由
  finish_reason 守卫暴露并重试，未做预防性上调；
- **演进方向**：① 若观测到成规模截断（finish_reason=length 日志），
  对 JSON 调用点显式设 max_tokens（官方建议）；② 叶子回退"静默返回错误
  片段"的分辨率问题（本次误诊的来源）可加"片段缺关键字段时显式告警"
  的可观测性改进；③ 枚举/字符串格式化表达式（f-string）修复按需扩展。
