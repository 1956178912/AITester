# S-3 多采样自一致性过滤器（K=2）评估：2 例幻觉被排除，但 correct 损失 5 → 高风险

> **一句话结论**：K=2 独立 spec-only 采样求交**确实把 2 个 hallucination 期望
> 排除出了 oracle**（`is_valid_parenthesization` 幻觉两采样均未再现；
> `knapsack` 幻觉只在 1 个采样出现 → 不在交集），使 `misguided 2→0`；但代价是
> **`correct 8→3`（损失 5，≥2）**——按 PREREG 冻结规则判定为
> **「高风险，默认关」**。根因：两次自由采样产生的示例集合重叠有限（union 67 /
> 交集 43，20 任务中 1 个交集为空），精确 JSON 键求交把大量有判别力的示例也
> 一起丢弃。**不用于生产**；下一步应改"K=3 + ≥2 一致"、给采样加 canonical
> input 约束、或把交集仅作为高置信子集而非唯一集合。

## 1. 协议（`PREREG.md` 跑前冻结）

| 项 | 设置 |
|---|---|
| 输入 | 同 P-1 的 20 任务/锚材料（`emse_spec_anchor_20261016` + `emse_df_spec_20261016`）；**重新做 K=2 spec-only 采样** |
| 采样 | `generate_examples_multisample(k=2)`：每任务 2 次小调用（max_tokens 512、≤3 条/样本）、cache namespace 区分 `:sample0/:sample1`、**关闭 LLM 缓存**（`AITESTER_LLM_CACHE=0`） |
| 处理 | 归一化键（`json.dumps({input,expected}, sort_keys, ensure_ascii=False, separators)`）求交：出现于 **2/2** 采样才保留，≤3 条；丢弃样本内唯一示例 |
| 基线 | P-1.1 norm：correct 8 / fp 0 / silent 3 / misguided 2 / unavailable 7（分母 13） |
| 重放 | `--reuse-examples <交集版报告>`（零 LLM；`SPEC_ORACLE_EXEC_ENABLE=true SPEC_ORACLE_EXAMPLES_ENABLE=true SPEC_EXAMPLES_SELF_VALIDATE=false`，关闭 R-2 确定性过滤器以隔离多采样效应） |
| 判定（冻结） | ≥1 hallucination 不在交集 **且** correct 损失 ≤1 → 有效过滤；correct 损失 ≥2 → **高风险，默认关**；否则未达有效过滤 |

## 2. 生成成本与采样统计（`MULTISAMPLE_STATS.json` 逐任务可核）

- LLM 调用 **40 次**（20 任务 ×2）；input/output tokens = **27,670 / 2,176**；
  估算成本 **$0.010912**（deepseek-flash 价目表，预算 ≤$0.05 的 22%）；墙钟 **31.3s**。
- 每任务两采样均成功（status ok；无 empty/error）；每样本 1-3 条（上限 3）。
- union **67** 条 → 交集 **43** 条；**丢弃 24 条**（样本内唯一示例）。
- **19/20 任务有非空交集**；`quixbugs__bucketsort` 两采样示例完全不相交
  （交集 0，丢弃 6）——该任务在原 P-1 中正是 correct 检出之一。

## 3. 两个 hallucination：均被排除出 oracle

| 任务 | P-1 幻觉示例 | 出现在新采样 | 在交集中 | 结果 |
|---|---|---|---|---|
| `quixbugs__is_valid_parenthesization` | `'(((' → True` | **sample0=False, sample1=False** | 否 | 被排除（重采样未再现该幻觉；交集自然不含） |
| `quixbugs__knapsack` | `capacity=5, [[5,10]] → 0` | sample0=False, **sample1=True** | 否 | 被**交集剔除**（仅 1/2 采样出现） |

两例都不再进入编译后的 oracle → `misguided 2→0`。

## 4. 重放前后对照（B 臂；两源臂相同；A 臂不变 correct 0 / silent 5 / unavailable 13）

| 指标（oracle 测试级；分母=可分类） | P-1.1 norm | K=2 交集版 | Δ |
|---|---|---|---|
| 可分类分母 | 13 | **11** | −2 |
| `correct` | **8** | **3** | **−5** |
| `fp` | 0 | 0 | 0 |
| `silent` | 3 | **8** | +5 |
| `misguided` | **2** | **0** | **−2** |
| `unavailable`（单列） | 7 | 9 | +2 |

逐任务（correct → 其它）：`bucketsort` correct→unavailable（交集空）；
`kheapsort`/`levenshtein`/`lis`/`max_sublist_sum` correct→silent（交集里的示例
不再区分 buggy/fixed）；`get_factors`/`hanoi`/`lcs_length` 保持 correct；
`is_valid_parenthesization`/`knapsack` misguided→silent；`find_in_sorted`
silent→unavailable。

## 5. 判定（按 PREREG 冻结规则）

- hallucination 排除：**2/2**（≥1 ✅）；
- correct：8→3，损失 **5 ≥2** → 触发 **「高风险，默认关」**；
- 因此**不满足**「有效过滤」（后者要求 correct 损失 ≤1）。

**结论**：多采样精确求交在 K=2 的**召回代价过高**——它确实清除了 2 例幻觉
misguided，但也把 5 个真检出（correct）降级为 silent/unavailable。根因是
两次自由采样示例集合重叠有限（union 67 → 交集 43，2 个任务交集 ≤1），
有判别力的示例常只出现一次。生产**不建议启用**；保持 default off。

## 6. 下一步（按收益）

1. **K=3 + ≥2 一致**（而非 K=2 的 2/2）：提高保留率、仍可剔除只出现 1 次的
   幻觉；成本 60 次小调用仍 ≤$0.02。
2. **canonical input 约束**：prompt 要求使用固定边界值集合/标准输入模板（如
   空、单元素、小随机），提高跨采样重叠，使"一致即高质量"更可信。
3. **交集只作高置信子集**：B 臂 = 交集（高置信）∪ R-2 过滤器通过的 union
   其余示例；或按"至少出现在 floor(k/2)+1 个采样"的多数一致（K=3 时 ≥2）。
4. **示例级 LLM 二次核验**（生成后单独提示核验 expected 与规格一致性）——
   与一致性正交，可组合。
5. 与 R-2 确定性过滤器串联：R-2 零误杀但零命中；多采样有命中但高成本——
   两者结合前需先在 K=3/约束输入下复评。

## 7. 限制

- n=20 任务、单次 K=2、单次零 LLM 重放；LLM 服务端非严格确定（temp=0 也不
  保证重放一致），两采样相关性未知；结论仅限本批，不外推。
- 交集版示例来自**重新采样**（非 P-1 原 90 条），与 P-1.1 norm 的差异同时包含
  "示例集合不同"与"交集过滤"两个因素；本评估按预注册规则合并看待。
- 关闭了 R-2 确定性过滤器（隔离多采样效应）；与 R-2 串联的效果未评估。
- 归一化键为严格 JSON（int 1 与 float 1.0 不合并；tuple/list 经 JSON 等价），
  可能低估一致率。
- 非 confirmatory；不用于生产。

## 8. 复算与工件

```bash
# ① 真实 K=2 采样（40 次小调用；预算 ≤$0.05；关闭缓存；本批 $0.010912）
AITESTER_LLM_CACHE=0 .venv/bin/python - <<'PY'
# 见 MULTISAMPLE_STATS.json 生成逻辑：读 P-1 raw 报告 + 锚表，逐任务调用
# spec_examples_generator.generate_examples_multisample(k=2, max_examples=3,
# cache_namespace="s_round_multisample_20261018")
PY
# ② 交集版零 LLM 重放（必须显式开 Q-1 双门 + 关 R-2 过滤器以隔离效应）
SPEC_ORACLE_EXEC_ENABLE=true SPEC_ORACLE_EXAMPLES_ENABLE=true SPEC_EXAMPLES_SELF_VALIDATE=false \
nice -n 15 .venv/bin/python -m experiments.oracle_examples_replay \
    --out experiments/results/s_round_examples_multisample_20261018 \
    --reuse-examples experiments/results/s_round_examples_multisample_20261018/MULTISAMPLE_REUSE_REPORT.json \
    --report-name ORACLE_EXAMPLES_REPORT_multisample --skip-markdown \
    --limit 20 --jobs 4 --per-test-timeout 1 --file-timeout 180
# 墙钟 262.6s；llm_calls=0
```

| 工件 | 说明 |
|---|---|
| `PREREG.md` | 跑前冻结的判定规则 |
| `MULTISAMPLE_STATS.json` | 40 次采样逐任务 stats（样本/交集/丢弃审计、2 hallucination 明细、成本、重放对照、判定） |
| `MULTISAMPLE_REUSE_REPORT.json` | 交集版 examples 的 reuse 报告（供零 LLM 重放） |
| `ORACLE_EXAMPLES_REPORT_multisample.json` | 交集版重放报告（body digest `f50ca1cf…`） |
| `README.md` | 本文件 |
| `SHA256SUMS` | 目录内文件 + 外部输入引用 sha256（`checksum_results.py --verify` 通过） |
