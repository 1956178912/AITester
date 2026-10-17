# SpecExpr 修门后可编译率校准表（2026-10-14）

> post-fix gate（2026-10-14 §6.9：sole 函数名回退 + 内建类型名值位置放行）；fresh LLM sample（跨跑批非确定性，与旧门值不可直接比）

| 数据集 | n | 行级均值（BASELINE 口径） | 恒 0 占比 | expr 子句数 | 拒绝原因 Top |
|---|---|---|---|---|---|
| synthetic | 25 | 0.5913（n=25） | 0.28 | 65 | [('unknown_name', 11), ('unsupported_operator', 3), ('unsupported_syntax', 1)] |

旧门参照（BASELINE，2026-10-14 修门前）：QuixBugs 0.6321（n=50）/ ULT 0.5626（n=25）/ synthetic 0.3102（n=174）。
