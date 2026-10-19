# SpecExpr DSL v4 扩展前后对账（emse_dsl_extend_recheck，2026-10-15，零 LLM）

> 用途：EMSE 批次六的**受控估计**证据——同一语料、同一去重口径下，v4 扩展
> 门 vs v4 前门的逐子句对比。零 LLM。

## 口径

- 语料与 `emse_dsl_diag3_20261015/` 逐字同源（719 计划 → 607 去重子句）；
- **旧门精确复刻**（非标记猜测）：临时摘除 spec_ir_v2 三个模块级常量
  （字符类去冒号 / 调用白名单去 sum·set·bool·hasattr / 属性白名单去
  values·keys·items·get·isupper·islower·bit_length）后调用**同一**
  `clause_reject_reason`——判定逻辑零复刻，只换常量；
- 新门 = 当前源码（v4：冒号入字符类 + lambda/海象护栏 + 白名单扩容）。

## 核心结果

| 指标 | v4 前 | v4 后 | Δ |
|---|---|---|---|
| 子句级可编译率（总体） | 0.8847 | **0.9127** | **+2.80pp** |
| quixbugs（n=256） | 0.8906 | 0.9258 | +3.52pp |
| other/合成（n=238） | 0.8782 | 0.9118 | +3.36pp |
| ult（n=113） | 0.885 | 0.885 | 0（其拒绝全是模块链，合法） |
| 任务级均值（91 任务，论文引用口径） | 0.8809 | 0.9110 | +3.01pp（14 改善 / 77 不变 / 0 回退） |

迁移矩阵（prior→new，607 条）：

| 迁移 | 计数 | 说明 |
|---|---|---|
| 可编译→可编译 | 537 | 不受影响 |
| unknown_name→unknown_name | 40 | 内部变量引用，正确拒绝（非 DSL 缺口） |
| unsupported_syntax→可编译 | 5 | 切片×4 + 字符串内冒号×1 |
| unsupported_operator→可编译 | 12 | 白名单扩容收复（sum/set/bool/hasattr/values/isupper/bit_length…） |
| unsupported_operator→unknown_name | 3 | 新白名单方法作用于未绑定名（如 config.get），仍拒但归因更准 |
| unsupported_operator→unsupported_operator | 10 | 残余合法拒绝（successor×5 / 模块链 / 自递归） |

**收复 17 条 / 回退 0 条**（回退恒 0 符合预期：v4 只放行不收紧；lambda/
海象在旧门下即被字符门拒绝，护栏零成本——语料中两类子句 0 实例）。

## 判读纪律

- 子句级对账=**受控估计**（同子句两门对比），非端到端任务级增益
  （需 LLM 重跑，本批次不做）；
- v4 只改度量/编译门；注入侧经 P0-3 单一事实源（`_clause_is_compilable`）
  自动跟随同一判定——`compile_spec_oracle` 产物同步扩展
  （测试锁定 `assert r == text[::-1]` 注入行）；
- 语料只含"LLM 已形式化子句"，衡量编译器接受率，不衡量形式化意愿。

## 残余（下一轮候选）

1. 被测函数自递归（fibonacci×4/gcd×1/factorial×1）：需"目标函数名入绑定
   上下文"的语义扩展（单独设计：递归不终止、自指真值性）；
2. 域名属性（successor×5/outgoing_nodes）：任意属性链=注入面，建议不改，
   走 Planner 提示侧收敛；
3. unknown_name 40 条：Planner 提示遵从度问题（自检③已点名内部变量），
   非文法缺口。

## 复算

**主路径（fresh clone / 工件包；X 轮 2026-10-19 补齐）**——语料已归档为
`CORPUS_607.json`（719 planner 条目 → 607 去重子句，切点 = 本报告 mtime
2026-10-15 12:45:38 本地时；派生数据，无隐私字段），重放不读 `~/.cache`：

```bash
python3 experiments/emse_dsl_extend_recheck.py \
    --from-corpus experiments/results/emse_dsl_extend_recheck_20261015/CORPUS_607.json
```

实测逐位复现本报告（rates / transitions / recovered / by_dataset / task_level
全部一致）；回归锁 `tests/test_emse_recompute_entrypoints.py`。

**作者机路径（缓存随时间增长，导出的是当前语料、非归档语料）**：

```bash
python3 experiments/emse_dsl_extend_recheck.py                          # 默认：读 ~/.cache 打分
python3 experiments/emse_dsl_extend_recheck.py --dump-corpus <out.json> # 导出去重子句语料
```
