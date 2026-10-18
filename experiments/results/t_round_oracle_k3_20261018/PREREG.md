# T3 预注册（跑批前冻结）：K=3 多数一致 + canonical input 约束评估

- 冻结时间：2026-10-18（实现与定向单测完成、**任何真实采样调用开始前**冻结）
- 性质：**探索性机制验证**（非 confirmatory）；承接 S-3 登记下一步
  「K=3 + ≥2 一致（多数一致）+ canonical input 约束」
- 本文件 sha256 在 `PREFLIGHT.json.prereg_sha256` 登记；跑后不得改判据/口径
- 生产开关 `SPEC_ORACLE_EXAMPLES_ENABLE` 保持**默认关**；本实验不改生产默认行为

## 1. 输入（只读；sha256 见 `PREFLIGHT.json.input_sha256`）

| 输入 | 用途 |
|---|---|
| `experiments/results/emse_spec_anchor_20261016/SPEC_ANCHOR_TABLE.json` | 20 任务的锚材料（`logic_analysis` + `human_spec`）；与 P-1/S-3 同源 |
| `experiments/results/emse_df_spec_20261016/benchmark_quixbugs_20261016_232138.json` | df_spec 归档源臂 1（任务集/`generated_test`/`fixed`） |
| `experiments/results/emse_df_spec_20261016/benchmark_quixbugs_20261017_003023.json` | df_spec 归档源臂 2 |
| `experiments/results/p_round_oracle_examples_20261018/ORACLE_EXAMPLES_REPORT.json` | P-1 raw 报告：**2 例 hallucination 定义** + P-1 examples 明细 |
| `experiments/results/p_round_oracle_examples_20261018/ORACLE_EXAMPLES_REPORT_norm.json` | P-1.1 表示归一**基线**（correct 8 / fp 0 / silent 3 / misguided 2 / unavailable 7；可分类分母 13） |
| `experiments/results/s_round_examples_multisample_20261018/MULTISAMPLE_STATS.json` | S-3（K=2）对照工件（只作参照，不作基线） |
| `experiments/spec_examples_generator.py` | 采样实现（本轮扩展 majority/canonical；默认行为不变） |
| `experiments/oracle_examples_replay.py` | 零 LLM 重放工具（`--reuse-examples`；**不修改**） |
| `docs/design/oracle_quality_metric.md` §12–15 | P-1/P-1.1/R-2/S-3 口径与已登记下一步 |

任务集：与 P-1/S-3 相同的 **20 个缺陷程序任务**（按 `task_id` 排序、`--limit 20`
语义）。材料构造与 P-1 重放生成路径**逐字节一致**（锚 `logic_analysis` +
`human_spec`；`signature_params=extract_signature_params(buggy_code, function_name)`）。
**链路校准（零 LLM，预注册前完成）**：用同一 helper 重建的 prompt 与 S-3 工件
`samples[0].prompt_sha256` **20/20 完全相同**，证明任务集/材料/参数构造一致。

## 2. 采样协议（冻结）

- **K=3**：每任务 3 次独立 spec-only 调用（共 **60 次**；无缓存，`AITESTER_LLM_CACHE=0`；
  cache namespace `t_round_k3_20261018:sample<i>` 仅作审计，不命中）；
- 每样本 **≤3 条**示例（`max_examples=3`）、`temperature=0.0`、
  `LLM_MAX_OUTPUT_TOKENS=512`、模型 `deepseek-flash`（项目价目表）；
- **canonical input 约束**：在既有 P-1 prompt 的「规格材料」之后追加下述冻结段落
  （仅本轮启用；实现为 `build_spec_examples_prompt(..., canonical_inputs=True)`）：

  ```
  标准输入模板（canonical 约束，强制）：
  - 为提高跨采样一致性，input 的每个参数必须优先取自下列固定边界值集合，不得自创大数/长序列：
    * 整数/浮点参数：0、1、-1（需要正数时用 2 或 3）；
    * 字符串参数：""（空串），其次用 "abc" 或 "()" 这类 3 字符以内的最小片段；
    * 列表/元组参数：[]、[0]、[1]、[-1]、[1, 2]；
    * 二维列表参数（物品/区间/边等）：[]、[[1, 1]]、[[2, 3]]；
  - 多参数函数：每个参数按位从上述集合取值，组成最小合法组合（例：容量用 1 或 2、物品表用 [[1, 1]]）；
  - 若规格列出了边界情况，优先为每个边界输出示例；
  - 只有当上述模板值全部落在规格定义域之外时，才可使用其它小值，且必须同时满足"小且可快速执行"要求。
  ```

- **失败回退（预注册，仅此一种触发）**：某任务的 canonical 采样视为失败
  **当且仅当 3/3 个样本 `status != "ok"`**（全为 `empty`（JSON/严格 schema 失败）
  或 `error` 或两者混合）。仅对失败任务用**旧 prompt**（`canonical_inputs=False`）
  重新 K=3 采样一次；该任务的最终候选示例取回退采样的多数一致结果；审计
  `fallback_tasks`（任务/原因/时间/回退前后状态）。其余任何情况（示例质量差、
  correct 损失大）**不得**触发回退或重采样。回退调用计入预算与墙钟。

## 3. 处理（多数一致口径，冻结）

- 归一化键：`json.dumps({"input":..., "expected":...}, sort_keys=True,
  ensure_ascii=False, separators=(",", ":"))`（与 S-3 相同；tuple/list 经 JSON
  等价，**int 与 float 不合并**）；
- 保留条件：示例出现于 **≥2/3** 个样本（`majority=2`，实现层 `intersect_examples`
  的 `threshold`）；样本内重复只计该样本一次；
- 每任务输出 **≤3 条**（超过时按首次出现顺序截断：先 sample0 顺序，再后续样本新增）；
- 某任务 0 条一致 → 该任务无示例（B 臂回退 A，与 P-1 失败透传一致）；
- 审计逐任务保留：3 个样本原始示例、各样本条数、union、intersection、
  dropped（含 `present_in_samples`）、tokens/usage、prompt/response sha256。

## 4. 零 LLM 重放（两条臂，冻结）

多条一致示例写入 `K3_REUSE_REPORT.json`（结构同 S-3 的 reuse 报告），用
`oracle_examples_replay --reuse-examples` 重放（**零 LLM 调用**；分类口径复用
O-1：oracle 测试级 correct/fp/silent/misguided，unavailable 单列不进分母）：

```bash
# 臂 1（主判定，生产默认口径）：R-2 示例自校验默认开启
SPEC_ORACLE_EXEC_ENABLE=true SPEC_ORACLE_EXAMPLES_ENABLE=true \
  nice -n 15 .venv/bin/python -m experiments.oracle_examples_replay \
  --out experiments/results/t_round_oracle_k3_20261018 \
  --reuse-examples experiments/results/t_round_oracle_k3_20261018/K3_REUSE_REPORT.json \
  --report-name ORACLE_EXAMPLES_REPORT_k3_default --skip-markdown \
  --limit 20 --jobs 4 --per-test-timeout 1 --file-timeout 180

# 臂 2（敏感性分析，隔离多采样效应）：关闭 R-2 确定性过滤器
# 其余参数同上 + SPEC_EXAMPLES_SELF_VALIDATE=false
# --report-name ORACLE_EXAMPLES_REPORT_k3_r2off
```

- **主判定臂 = 臂 1（R-2 默认开，生产口径）**；臂 2 为敏感性分析。若两臂
  判定不同，以臂 1 为准并**同时披露**两臂数字；
- 基线 = P-1.1 表示归一 `ORACLE_EXAMPLES_REPORT_norm.json`（不重跑基线）；
- 两源臂（df_spec 归档 2 个 artifact）结果预期逐位相同；逐任务转移表以
  `task_id` 为键合并（相同则注明）。

## 5. 判定规则（冻结，跑后不得改）

1. **有效（多采样一致 + canonical）**：P-1 的 2 个 hallucination 期望中
   **≥1 个不在多数一致示例集（不会进入 oracle）** **且** `correct` 相对基线
   8 的损失 **≤1**（即 ≥7）→ 记为「**有效**」；
2. **高风险，默认关**：多数一致版 `correct` 相对 8 下降 **≥2**（≤6）→ 记为
   「**高风险，默认关**」；
3. 其余 → 记为「**未达有效过滤**」。判定顺序固定：**先查规则 2**（损失 ≥2 即
   「高风险默认关」，即使有 hallucination 被排除），再查规则 1，两者都不满足
   （典型：0 个 hallucination 被排除且损失 ≤1）即规则 3。

- **hallucination 命中定义（与 S-3 相同，冻结）**：P-1 的 2 条错误期望示例——
  `is_valid_parenthesization`: `input=["((("]`, `expected=True`；
  `knapsack`: `input=[5, [[5,10]]]`, `expected=0`——是否**不在**本轮多数一致
  示例集。同时报告其在 3 个新样本中的出现次数，区分「被多数一致剔除」与
  「重采样未再现」。
- 判定基准为 `correct` 计数（oracle 测试级，20 任务各 1 个 oracle 测试）；
  次要指标（fp/silent/misguided/unavailable、可分类分母、逐任务转移）仅报告，
  不参与判定切换。
- **不得**因结果不理想而改阈值、改口径、增加重采样或换判定臂。

## 6. 预算、墙钟与中止条件（冻结）

- 预算：**≤ $0.05**（价目：`experiments/price_table.json` deepseek-flash
  峰时注册价；预期主采样 ~$0.016，含最坏回退 ~$0.033）；token/成本按项目
  `get_usage` 实测记账，不编造；
- 墙钟：采样阶段 **≤15 min**（S-3 的 40 次调用实测 31.3s；预期本轮 ≤3 min）；
  两次重放为**零 LLM 本地 pytest**（S-3 单次口径实测 262.6s），各自记录实测墙钟；
- **中止条件**（任一触发即停止后续采样，如实报告未完成）：实测成本已超
  $0.05；采样阶段墙钟已超 15 min；`deepseek-flash` 连续 3 个任务全部 3 样本
  `error`（疑似服务/配置故障）。中止后不重跑、不换模型。

## 7. 预声明预期与风险

- **预期**：canonical input 约束应提高跨采样重叠（边界输入更可能被多个采样
  同时选中），K=3/≥2 比 K=2/2-精确求交保留更多示例 → `correct` 损失应
  小于 S-3 的 5；但 canonical 模板值是**模型不可见实现**下的猜测，可能生成
  规格错误期望（引入新 misguided），也可能仍不足以剔除 2 例 hallucination。
- S-3 已知：K=2 精确求交 union 67→交集 43（丢弃 24），correct 8→3。本轮
  期望交集/保留率更高；若 correct 仍损失 ≥2 → 按规则「高风险，默认关」，
  如实报告，不粉饰。
- **服务端非严格确定**（temperature=0 也不保证逐字节重放）：多采样前提成立但
  样本相关性未知；结论仅限本批工件，不外推。

## 8. 次要指标（只报告，不参与判定）

每任务 3 样本条数/状态、union/intersection/dropped 审计、回退任务清单、
LLM 调用/tokens/成本/墙钟、两臂重放全表（correct/fp/silent/misguided/
unavailable、可分类分母、逐任务转移）、R-2 过滤器审计（n_input/n_kept/
n_dropped/原因）、prompt/response sha256、输入/产物 sha256。

## 9. 限制

- n=20 任务、单轮 K=3、单次零 LLM 重放 ×2 臂；探索性，非 confirmatory；
- 示例来自**重新采样**（非 P-1 原 90 条），与基线的差异同时包含「示例集合
  不同」「canonical 约束」「多数一致过滤」三个因素，本评估按预注册规则合并
  看待，不做单因素归因；
- canonical 模板为人工设计的通用边界集合，不保证覆盖各函数真实定义域；
- R-2 过滤器在 S-3/P-1 已证 0 拦截，臂 2 预期与臂 1 相同（若不同则披露）；
- 不改生产代码默认值、不改基线工件、不 git commit；本批不用于生产决策之外的
  能力主张。
