# SpecExpr DSL 诊断批次（2026-10-14，save-state 冒烟）

> 用途：EMSE 报告 §6.9 的**验证证据基**——用 save-state 捕获 Planner 实际
> 产出的 `*_expr` 形式化子句，离线对账旧/新度量门的可编译率差异。
> 零 LLM 复算（子句捕获花 ~$0.06 LLM；对账纯本地）。

## 内容

- `raw/<task_id>/*.json`：12 任务（seed45 前 12）的环节级状态工件，
  含 `test_plan.logic_analysis` 的 NL 与 `*_expr` 子句全文；
- `benchmark_synthetic_*.json`：批次汇总（新门下管线实测 compile rate）；
- `traces/`：节点级轨迹；
- `emse_dsl_diag2_20261014_run.log`：跑批日志。

## 对账方法（§6.9 验证）

对 30 条 `*_expr` 子句逐条复判：

| 门 | 可编译 | unknown_name | 任务级可编译 |
|---|---|---|---|
| 旧门（fn 原样 + 无类型名放行） | 11/30（36.7%） | 16 | 9/12 |
| 新门（unknown/空 → sole 函数回退 + 内建类型名） | 14/30（46.7%） | 13 | 9/12 |

- 签名参数用再生的 `SyntheticDataset(seed=45, task_count=87)` 的
  instance_code 离线提取（state 工件不存 target_code，数据集确定性可再生）；
- 旧门复刻：`known = params or _default_known_names()`；
  `known_with_calls = known | _ALLOWED_CALL_NAMES`；
- 新门 = 当前代码 `clause_reject_reason`（含 `_BUILTIN_TYPE_NAMES` 与
  `sole_top_level_function_name` 回退）。

## 附带发现（写入 EMSE 报告 §6.8/§6.9）

1. Planner function_name 分布：10/12 有效、2/12 为字面量 `"unknown"`
   （M10 降级形态）——`extract_signature_params(code, "unknown")` 返回
   None，旧逻辑静默回退默认集；
2. unknown_name 标识符 Top：isinstance×14（调用位，本已放行）、result×12、
   full_name×7、int×7、str×6、len×6——**值位置的内建类型名与参数名/
   result 别名是主要误拒源**；
3. 诊断必须评 `*_expr` 字段（LLM 形式化子句）而非 NL 字段——后者是
   `compile_readiness` 的正确靶（初版诊断评错字段，已修正）。
