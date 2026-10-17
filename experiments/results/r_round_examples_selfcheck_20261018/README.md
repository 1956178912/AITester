# R-2 示例自校验过滤器：90 条 examples 离线评估 + 零 LLM 重放

> **一句话结论**：过滤器按预注册规则实现且**安全**（0 误杀、0 拦截），但在本批
> 90 条示例上 **0 条被丢弃、2 个 hallucination 均未命中**——因为这两个任务的
> 可机检后置子句过弱（`isinstance(result, bool)` / `isinstance(result, int)`、
> `result >= 0`），LLM 的幻觉期望值（`'(((' → True`、`knapsack(5,[[5,10]]) → 0`）
> 与这些子句**不构成矛盾**；严格 AST 白名单下 Call/属性/下标又不可求值。
> 因此按 PREREG 判定：**「未达有效过滤（无效拦截），非高风险」**——correct 无
> 损失（8→8），misguided 未下降（2→2）。这是"规约表达力上界"的诚实负结果，
> 不是过滤器实现缺陷。

## 1. 协议（PREREG 已冻结：`PREREG.md`）

| 项 | 设置 |
|---|---|
| 输入 | P-1 raw `ORACLE_EXAMPLES_REPORT.json` 的 20 任务 / **90 条** LLM spec-only examples（不重新生成） |
| 基线 | P-1.1 表示归一 `ORACLE_EXAMPLES_REPORT_norm.json`：correct 8 / fp 0 / silent 3 / misguided 2 / unavailable 7（分母 13） |
| 过滤器 | `src/specs/spec_ir_v2.py::self_validate_examples`（默认开启；`SPEC_EXAMPLES_SELF_VALIDATE=false/0/off` 关闭） |
| 丢弃条件 | 仅当 `postconditions_expr` 在受限 AST 求值下为 **False**（原因 `postcondition_false`）；不可求值/异常/超长 → **保留**（保守放行） |
| 重放 | `oracle_examples_replay.py --reuse-examples <P-1 raw>` → `ORACLE_EXAMPLES_REPORT_selfcheck.json`（零 LLM；`SPEC_ORACLE_EXEC_ENABLE=true SPEC_ORACLE_EXAMPLES_ENABLE=true` 以启用生产注入链路；`SPEC_EXAMPLES_SELF_VALIDATE` 未设=默认开） |
| 判定（跑前冻结） | misguided 2→≤1 且 correct 损失 ≤1 → 有效过滤；correct 损失 ≥2 → 高风险默认关；其余 → 未达有效过滤（无效） |

## 2. 过滤器算法与安全边界

对每条示例构造环境变量：`signature_params[i] ← input[i]`（单参 args-list 展开规则
与编译器一致；多参按位映射）、`r` 与 `result` ← `expected`；对 spec 的
`postconditions_expr` 逐条做**受限安全求值**：

- 允许 AST：比较（`== != < <= > >= in not in is is not`）、布尔（`and/or/not`）、
  算术（`+ - * / // %`、一元 `±`）、常量、`Name`（仅示例环境变量）、`list`/`tuple`；
- **拒绝**：`Call`（含 `len`/`isinstance`/`__import__`）、属性访问、下标、lambda、
  推导式、dict/set、f-string、walrus；
- 表达式 ≤500 字符、AST 节点 ≤200（DoS 上限）；语法错误/名称缺失/除零等异常
  → `unevaluable` → **保留**；
- 前件 `preconditions_expr` 仅做域检查审计：可求值且 False 只计数
  `n_precondition_false_kept`，**不丢弃**（保守，不误杀边界示例）。

无 examples 路径：编译器不引入任何额外代码/行为（单测锁定与无示例产物逐字节一致）。

## 3. 90 条 examples 过滤统计（`FILTER_STATS.json` 逐条可核）

| 指标 | 计数 |
|---|---|
| n_input | **90** |
| n_kept | **90** |
| **n_dropped** | **0**（reasons={}） |
| n_fully_validated（全部后置子句可求值） | 9 |
| n_partially_validated（部分可求值，无 False） | 16 |
| n_no_post_clause（无 `postconditions_expr`） | 10 |
| n_unevaluable（全部不可机检） | 55 |
| n_precondition_false_kept（前件 False 但保留） | 1 |
| 有丢弃的任务数 | **0 / 20** |

> 覆盖率说明：55/90 示例"全部后置子句不可求值"——真实锚后置子句大量使用
> `len/isinstance/all/...` 与下标/推导式，而严格 AST 白名单（按任务书要求
> 仅比较/布尔/算术/常量/Name/List/Tuple）拒绝 Call/下标/推导式。可求值部分
> （9 全 + 16 部分）无一条与示例期望矛盾。

## 4. 两个 hallucination 任务：**未命中**（诚实负结果）

| 任务 | 真实锚 `postconditions_expr` | 幻觉示例 | 是否拦截 | 原因 |
|---|---|---|---|---|
| `quixbugs__is_valid_parenthesization` | `isinstance(result, bool)` | `'(((' → True` | **否** | 后置子句只约束类型；Call 不可求值 → 无矛盾可判 |
| `quixbugs__knapsack` | `isinstance(result, int)`、`result >= 0` | `capacity=5, [[5,10]] → 0` | **否** | `result>=0` 对 0 为真；语义（最大价值）未编码进可机检表达式 |

反例（证明过滤器在**规约表达力足够**时有效，单测覆盖）：若把 knapsack 语义写成
`result == 10`，同一幻觉示例（expected 0）会被丢弃（`postcondition_false`）。

## 5. 重放前后对照（B 臂，oracle 测试级；分母=可分类；A 臂不变：correct 0 / silent 5 / unavailable 13）

| 指标 | P-1.1 norm（过滤前） | R-2 过滤后 | Δ |
|---|---|---|---|
| 可分类分母 | 13 | **13** | 0 |
| `correct` | 8 | **8** | 0 |
| `fp` | 0 | **0** | 0 |
| `silent` | 3 | **3** | 0 |
| `misguided` | **2** | **2** | **0** |
| `unavailable`（单列） | 7 | **7** | 0 |
| 任务级 A→B 转移 | — | 同 P-1.1（silent→correct 2、unavailable→correct 6、unavailable→misguided 2、unavailable→silent 3、silent→unavailable 3、unavailable→unavailable 4） | 无变化 |

结论：过滤后 B 臂与 P-1.1 norm **逐位相同**（两源臂相同）；过滤器**零误杀**，
但也**未解决**目标 hallucination。

## 6. 判定（按 PREREG 冻结规则）

- misguided 2 → 2（未 ≤1）→ 不满足「有效过滤」；
- correct 8 → 8（损失 0，未 ≥2）→ 不满足「高风险默认关」；
- **判定 = 未达有效过滤（无效拦截），非高风险**。

**解释与建议**：
1. 过滤器是**安全网**（零误杀、DoS 有界、异常保守放行），保留默认开启无观测
   代价；但**不能**宣称它能修复示例幻觉——它只能剔除"与可机检后置子句直接
   矛盾"的示例。
2. 根因是**规约表达力**而非示例生成：两个 hallucination 的锚后置子句未编码
   语义。下一步（按收益排序）：① 规约强化（把关键语义写成 `*_expr` 可机检
   表达式，例如括号平衡/最大价值）；② 示例级独立验证/多次采样自一致性
   （LLM 生成后二次核验，零/低成本）；③ 放宽求值白名单（允许纯内建调用
   `isinstance/len/all/...` 与推导式）——可把可求值率从 25/90 提升，但对
   本批 2 例仍无效，且引入语义求值风险，需谨慎。
3. 生产接线（Q-1）：过滤器已默认开启且与示例编译同一路径，不需要额外开关
   编排；若 R 轮判定"无效"被接受，Q-2 类 A/B 不应假设该过滤器带来质量提升。

## 7. 限制

- n=20 任务 / 90 示例、单次零 LLM 重放；结论仅限本批，不外推。
- 后置子句取自 Planner 锚 `logic_analysis`（与生产同源），但本评估不重新
  生成示例/规约；样本对"LLM 幻觉多样性"覆盖有限。
- 严格 AST 白名单使 55/90 示例后置子句不可求值（Call/下标/推导式）——这是
  任务书安全边界的直接结果，也限制了过滤器召回；已在 §2 完整披露。
- 前件 False 仅审计不丢弃（保守），可能放过"输入违反前件"的示例；本批 1 例。
- 过滤器不校验 `expected` 的类型域/边界一致性（任务书标记可选，未实现）。

## 8. 复算命令与工件

```bash
# 过滤统计（零 LLM；读 P-1 raw 报告 + 锚表）
.venv/bin/python - <<'PY'  # 见 FILTER_STATS.json 生成逻辑（仓库内脚本模板）
...
PY

# 过滤后重放（零 LLM；必须显式开 Q-1 生产双门，否则 B 臂示例会被 nodes 剥离）
SPEC_ORACLE_EXEC_ENABLE=true SPEC_ORACLE_EXAMPLES_ENABLE=true \
nice -n 15 .venv/bin/python -m experiments.oracle_examples_replay \
    --out experiments/results/r_round_examples_selfcheck_20261018 \
    --reuse-examples experiments/results/p_round_oracle_examples_20261018/ORACLE_EXAMPLES_REPORT.json \
    --report-name ORACLE_EXAMPLES_REPORT_selfcheck --skip-markdown \
    --limit 20 --jobs 4 --per-test-timeout 1 --file-timeout 180
# 墙钟 259.8s；llm_calls=0
```

| 工件 | 说明 |
|---|---|
| `PREREG.md` | 跑前冻结的判定规则与预期 |
| `ORACLE_EXAMPLES_REPORT_selfcheck.json` | 过滤后重放报告（body digest `df222a58…`；含逐任务 `examples_self_validation` 审计） |
| `FILTER_STATS.json` | 90 条示例逐条决策（input/expected/post 求值/decision）+ 2 hallucination 详情 + 判定 |
| `README.md` | 本文件 |
| `SHA256SUMS` | 目录内文件 + 外部输入引用 sha256（`checksum_results.py --verify` 通过） |
