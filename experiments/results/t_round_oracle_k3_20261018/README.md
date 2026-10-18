# T3 K=3 多数一致 + canonical input 约束：交集保留率 96%，但 correct 8→5（损失 3）→ 高风险默认关

> **一句话结论**：canonical input 约束把三个采样的示例集合重叠率大幅提高（union 57 / 交集 55，只丢弃 2 条；S-3 K=2 为 67→43/丢弃 24），P-1 的 **2 例 hallucination 均未进入本轮 oracle**；但代价是 **correct 8→5（损失 3 ≥2）**：canonical 边界示例不再区分 3 个任务的 buggy/fixed（correct→silent），且 `knapsack` 出现**新的一致幻觉**（3/3 采样一致给出错误期望 `(1,[[1,1]])→0`）继续 misguided。按 PREREG 冻结规则判定**「高风险，默认关」**；生产保持默认关。

## 1. 协议（`PREREG.md` 跑前冻结，sha256 见 `PREFLIGHT.json`）

| 项 | 设置 |
|---|---|
| 任务集 | P-1 的 20 个任务（按 `task_id` 排序；材料构造与 P-1 重放生成路径逐字节一致） |
| 采样 | **K=3** × 20 任务 = **60 次** spec-only 小调用；每样本 ≤3 条；`temperature=0.0`、`LLM_MAX_OUTPUT_TOKENS=512`、**关闭 LLM 缓存**、cache namespace `:sample<i>` 仅审计 |
| canonical 约束 | prompt 追加冻结段落：固定边界值模板（数值 0/1/-1、字符串 ""/"abc"/"()"、列表 []/[0]/[1]/[1,2]、二维 [[1,1]]/[[2,3]]、每参数按位取最小合法组合） |
| 失败回退 | 仅当某任务 3/3 样本 `status != ok` 时用旧 prompt 重采样一次；本批回退任务 **0** 个 |
| 处理 | 归一化 JSON 键（与 S-3 相同；tuple/list 等价、int/float 不合并），**≥2/3** 出现才保留，≤3 条/任务 |
| 基线 | P-1.1 表示归一 `ORACLE_EXAMPLES_REPORT_norm.json`（correct 8 / fp 0 / silent 3 / misguided 2 / unavailable 7；分母 13） |
| 重放 | `oracle_examples_replay --reuse-examples`（**零 LLM**）；臂 1 = R-2 默认开（主判定），臂 2 = `SPEC_EXAMPLES_SELF_VALIDATE=false`（敏感性）；显式开 Q-1 双门 |

## 2. 采样成本与一致性统计（`K3_STATS.json` 逐任务可核）

- LLM 调用 **60 次**；input/output tokens = **56,385 / 3,051**；估算成本 **$0.020577**（`experiments/price_table.json` deepseek-flash 峰时价，预算 ≤$0.05 的 41.2%）；采样墙钟 **45.301s**。
- 20/20 任务 canonical 采样 status=ok（每样本 1–3 条）；**union 57 → 交集 55**（丢弃 2 条），最终示例合计 **55** 条。
- 与 S-3（K=2 自由采样）对比：S-3 union 67 → 交集 43（丢弃 24，1 个任务交集为空）；本轮 canonical 后 20/20 任务均有非空交集——**重叠率显著提升**。

## 3. 两个 P-1 hallucination：均未进入本轮 oracle（但注意新的一致幻觉）

| 任务 | P-1 幻觉示例 | 3 个新样本中出现 | 在最终示例集 | 结果 |
|---|---|---|---|---|
| `quixbugs__is_valid_parenthesization` | `{"input": ["((("], "expected": true}` | [False, False, False]（0/3） | 否 | 被排除 |
| `quixbugs__knapsack` | `{"input": [5, [[5, 10]]], "expected": 0}` | [False, False, False]（0/3） | 否 | 被排除 |

> 机制区分：两条 P-1 幻觉示例在 3 个 canonical 样本中**均未再现**（不是被 ≥2/3 过滤掉的），而是重采样/模板约束下消失。多数一致过滤本身只丢弃 2 条示例（`depth_first_search` 1 条、`kheapsort` 1 条）。

**但**：`knapsack` 出现**新的一致幻觉**——3/3 canonical 样本一致给出 `(1,[[1,1]])→0`（正确应为 1；buggy 因 `weight < j` 严格比较恰好返回 0，fixed 返回 1），该任务最终仍为 **misguided**。这是本轮最重要的负面证据：**多数一致 + canonical 模板可以一致地错，自一致性不是正确性证明。**

## 4. 重放前后对照（两臂；两张源臂工件逐位相同）

| 指标（oracle 测试级；分母=可分类） | P-1.1 norm 基线 | 臂 1：K=3/≥2 交集（R-2 默认开，主判定） | 臂 2：同左 − R-2（敏感性） |
|---|---|---|---|
| 可分类分母 | 13 | 12 | 12 |
| `correct` | 8 | 5 | 5 |
| `fp` | 0 | 0 | 0 |
| `silent` | 3 | 6 | 6 |
| `misguided` | 2 | 1 | 1 |
| `unavailable`（单列） | 7 | 8 | 8 |
| 正确率（correct/可分类） | 0.615385 | 0.416667 | 0.416667 |
| 错误率（(fp+misguided)/可分类） | 0.1538 | 0.0833 | 0.0833 |

- 两臂逐任务类别是否完全一致：**True**（R-2 自校验丢弃示例数：0；两任务锚后置子句表达力仍不足，与 R-2 结论一致）。

## 5. 逐任务变化表（20 任务，各 1 个 oracle 测试）

| 任务 | 基线（P-1.1 norm） | K=3/≥2 + canonical | 变化 | 示例数 |
|---|---|---|---|---|
| `quixbugs__bitcount` | unavailable | unavailable | — | 3 |
| `quixbugs__breadth_first_search` | unavailable | unavailable | — | 1 |
| `quixbugs__bucketsort` | correct | correct | — | 3 |
| `quixbugs__depth_first_search` | unavailable | unavailable | — | 2 |
| `quixbugs__detect_cycle` | unavailable | unavailable | — | 1 |
| `quixbugs__find_first_in_sorted` | unavailable | unavailable | — | 3 |
| `quixbugs__find_in_sorted` | silent | silent | — | 3 |
| `quixbugs__flatten` | unavailable | unavailable | — | 3 |
| `quixbugs__gcd` | unavailable | unavailable | — | 3 |
| `quixbugs__get_factors` | correct | correct | — | 3 |
| `quixbugs__hanoi` | correct | correct | — | 3 |
| `quixbugs__is_valid_parenthesization` | misguided | silent | **变化** | 3 |
| `quixbugs__kheapsort` | correct | correct | — | 3 |
| `quixbugs__knapsack` | misguided | misguided | — | 3 |
| `quixbugs__kth` | silent | unavailable | **变化** | 3 |
| `quixbugs__lcs_length` | correct | correct | — | 3 |
| `quixbugs__levenshtein` | correct | silent | **变化** | 3 |
| `quixbugs__lis` | correct | silent | **变化** | 3 |
| `quixbugs__longest_common_subsequence` | silent | silent | — | 3 |
| `quixbugs__max_sublist_sum` | correct | silent | **变化** | 3 |

- 保持 correct：`quixbugs__bucketsort`, `quixbugs__get_factors`, `quixbugs__hanoi`, `quixbugs__kheapsort`, `quixbugs__lcs_length`（5 个）。
- correct 丢失：`quixbugs__levenshtein`, `quixbugs__lis`, `quixbugs__max_sublist_sum`（3 个）。
- misguided 消失：`quixbugs__is_valid_parenthesization`；仍 misguided：`quixbugs__knapsack`。
- 新增 unavailable：`quixbugs__kth`（buggy 崩溃 → O-1 harness skip，单列不进分母）。

**归因（人工核对源码；仅本批工件）**

- `quixbugs__knapsack`：P-1 的幻觉示例 `(5,[[5,10]])→0` 未再现（3/3 样本均无）；但 canonical 模板「容量 1 + 物品 [[1,1]]」被 3/3 采样一致给出**新幻觉期望** `(1,[[1,1]])→0`（buggy 因 `weight < j` 严格比较恰好返回 0，fixed 返回 1）→ 任务仍 misguided。说明：多数一致 + canonical 可产生**一致地错**，自一致性≠正确性。
- `quixbugs__is_valid_parenthesization`：P-1 的幻觉示例 `'((('→True` 未再现（3/3 样本均无）；canonical 新示例（`""→True`、`"()"→True`、`")("→False`）全部与规格一致，但 buggy/fixed 均通过 → 由 misguided 变 silent（幻觉已消除，但无检出）。
- `quixbugs__kth`：canonical 新增 `([1,2],1)` 触发 buggy 的递归越界（IndexError→O-1 harness skip），该 oracle 测试由 silent 变 unavailable（单列、不进分母）。
- `quixbugs__levenshtein`：canonical 边界示例（`""`/`"abc"` 空串组合）buggy/fixed 均通过 → 不再区分 → correct→silent。
- `quixbugs__lis`：canonical 边界示例（`[]`/`[1]`/`[1,2]`）buggy/fixed 均通过 → 不再区分 → correct→silent。
- `quixbugs__max_sublist_sum`：canonical 边界示例（`[]`/`[-1]`/`[1,2]`）buggy/fixed 均通过 → 不再区分 → correct→silent。

## 6. 判定（按 `PREREG.md` 冻结规则）

1. **hallucination 排除**：P-1 的 2 条幻觉示例均不在本轮示例集 → **2/2**（满足 ≥1 子句）；
2. **correct 损失**：8 → 5，**损失 3 ≥2** → 触发规则 2；
3. **判定 = 「高风险，默认关」**（`high_risk_default_off`）——correct 8→5（损失 3 ≥2）→ 触发预注册规则 2。

**敏感性**：臂 2（关闭 R-2 过滤器）与臂 1 逐任务结果**完全一致**，判定不变；R-2 不是本轮损失来源（其丢弃示例数为 0）。

## 7. 结论与下一步（按收益）

1. **canonical 约束达到预期的一半**：跨采样重叠率 96%（union→交集），K=3/≥2 不再是召回瓶颈（S-3 中 K=2 精确求交 loss=5 的机制是「交集稀疏」；本轮 loss=3 的机制是「边界示例不区分」）。
2. **但固定边界模板有系统副作用**：① 边界输入对部分任务不具判别力（levenshtein/lis/max_sublist_sum correct→silent）；② 模板组合可能诱导模型给出**一致但错误**的期望（knapsack 新幻觉）。旧幻觉消失不等于幻觉问题解决。
3. **下一步（供 Lead 裁决）**：① 示例级独立核验（LLM 二次核验 expected 与规格一致性）——针对「一致地错」，与一致性正交；② canonical 模板只约束**输入取值集合**而不要求「最小组合」，或按任务结构生成模板（容器/字符串型任务给非平凡样例）；③ 叠加 R-2 表达力强化（关键语义写成 `*_expr`）；④ 多采样一致仅作为**高置信子集**而非唯一集合（与 P-1 原示例取并集）。生产继续保持 `SPEC_ORACLE_EXAMPLES_ENABLE` 默认关。

## 8. 限制

- n=20 任务、单轮 K=3、单次零 LLM 重放 ×2 臂；探索性、非 confirmatory，结论仅限本批工件，不外推。
- 示例来自重新采样（非 P-1 原 90 条），与基线差异同时包含「示例集合不同」「canonical 约束」「≥2/3 多数一致过滤」三个因素；本评估按预注册规则合并看待，不做单因素归因。
- P-1 两条幻觉示例在 3 个 canonical 样本中均未再现（不是被多数一致过滤掉的）；「hallucination 排除 2/2」只表示它们未进入本轮 oracle，不代表示例幻觉问题被解决（knapsack 出现新的一致幻觉）。
- canonical 模板是人工设计的通用边界集合，不保证覆盖各函数真实定义域；本轮观测到「边界示例不区分 buggy/fixed」与「模板组合诱导一致错误期望」两类副作用。
- R-2 自校验在臂 1 中丢弃示例 0 条（两任务锚后置子句表达力不足，与 R-2 结论一致）；臂 2 关 R-2 后逐任务结果与臂 1 相同，判定不变。
- 与 B2 主批次并发运行（重放 nice -n 15）；墙钟为实测，可能受 CPU 争用轻微影响。
- 未改生产默认（SPEC_ORACLE_EXAMPLES_ENABLE 默认关）；未 git commit；基线工件只读。
- helper 脚本的执行版本/当前版本 sha256 见 ANALYSIS_REPORT.helper_provenance（采样 helper 在跑后仅做过 ruff format，无行为变化）。
- helper 版本：采样实际执行版本 `_helpers/run_k3_sampling.py` sha256=`da2eb72fe49f37f118549325f374e86a35ec241f015797b110f659a9c2e106c9`（PREFLIGHT 记录）；当前文件 sha256=`b996a19c36be49e3606589c8a7001fb79761a67b4fe7e541924137ac6ccd093b`（执行后仅 `ruff format`，无行为变化）。

## 9. 复算与工件

```bash
# ① 采样（60 次真实小调用；cache off；本批 $0.020577 / 45.301s）
AITESTER_LLM_CACHE=0 .venv/bin/python experiments/results/t_round_oracle_k3_20261018/_helpers/run_k3_sampling.py
# ② 零 LLM 重放（臂 1 = R-2 默认开；臂 2 加 SPEC_EXAMPLES_SELF_VALIDATE=false）
SPEC_ORACLE_EXEC_ENABLE=true SPEC_ORACLE_EXAMPLES_ENABLE=true \
  nice -n 15 .venv/bin/python -m experiments.oracle_examples_replay \
  --out experiments/results/t_round_oracle_k3_20261018 \
  --reuse-examples experiments/results/t_round_oracle_k3_20261018/K3_REUSE_REPORT.json \
  --report-name ORACLE_EXAMPLES_REPORT_k3_default --skip-markdown \
  --limit 20 --jobs 4 --per-test-timeout 1 --file-timeout 180
# ③ 分析/README/摘要；④ 校验和
.venv/bin/python experiments/results/t_round_oracle_k3_20261018/_helpers/analyze_k3.py
.venv/bin/python scripts/gates/checksum_results.py --write --results-dir experiments/results/t_round_oracle_k3_20261018
```

- 默认 prompt（`canonical=False`）与 S-3 工件 `samples[0].prompt_sha256` 逐任务相同：**20/20** → 生成器默认路径零变化；canonical=True 仅为追加冻结段落（`PREFLIGHT_PROMPTS.json`）。

| 工件 | 说明 |
|---|---|
| `PREREG.md` | 跑前冻结的协议/判定/预算（sha256 见 PREFLIGHT） |
| `PREFLIGHT.json` | 预检：prereg sha256 / 实现 sha256 / 输入 sha256 / 定向测试 / 预算估计 |
| `PREFLIGHT_PROMPTS.json` | 两变体 prompt 逐任务 sha256 + 与 S-3 的 20/20 校准 |
| `SAMPLING_REPORT.json` | 采样阶段紧凑报告（token/成本/墙钟/union/intersection/dropped 审计；派生自 K3_STATS） |
| `K3_STATS.json` | 60 次采样逐任务统计（样本/交集/丢弃/回退/usage/成本/幻觉明细） |
| `K3_REUSE_REPORT.json` | 多数一致示例的 reuse 报告（供零 LLM 重放） |
| `ORACLE_EXAMPLES_REPORT_k3_default.json` | 重放臂 1（R-2 默认开；主判定） |
| `ORACLE_EXAMPLES_REPORT_k3_r2off.json` | 重放臂 2（R-2 关；敏感性） |
| `ANALYSIS_REPORT.json` | 预注册判据逐项判定 + 逐任务变化 + 两臂全表 + 归因 |
| `RUN_SUMMARY.log` | 命令/墙钟/关键计数摘要 |
| `SAMPLING_CONSOLE.log / REPLAY_*_console.log` | 采样与重放的控制台原始记录 |
| `SHA256SUMS` | 目录内文件 + 外部输入引用 sha256（checksum_results.py --verify 通过） |

