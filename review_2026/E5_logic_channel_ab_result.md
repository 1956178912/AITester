# E5 · 逻辑通道 A/B 正式结果（SPEC_ORACLE_EXEC_ENABLE off/on）

> 2026-10-10 独立审查落地批次 · **首次成功端到端跑通的真实 LLM A/B**
> 工件目录：`llm_logic_ab_20261010_194701`
> 协议：QuixBugs（排除 4 个不终止任务 → 46 程序）· AITESTER_PROFILE=logic ·
> seed 42 · TEMPERATURE=0 · LLM_THINKING_MODE=disabled · **冷缓存**（AITESTER_LLM_CACHE=0）·
> 并行 4 · 双臂单变量（唯一自变量 = SPEC_ORACLE_EXEC_ENABLE）· 变异评分关（挂死源，非本 A/B 主终点）

## 0. 结论

| 项 | control（开关 off） | treat（开关 on） |
|---|---|---|
| detection（M1 三段判定 F2P） | **24/37 = 64.9%** | **15/37 = 40.5%** |
| 规约 oracle 注入行数 | **0 / 46** | **25 / 46** |
| detection 分母 | 37 | 37（**一致，可配对**） |

**配对检验（37 对共同任务）**：
- 2×2：both=12 · **control-only=12** · **treat-only=3** · neither=10
- McNemar（连续性校正）：不一致对 15、χ²=**4.267**、**p=0.0389**
- 精确二项（双侧）：12:3 → **p=0.0352**
- 方向：**注入确定性规约 oracle 使检出率下降 24.4pp**

**机制证据（与本批 specificity 门分布一致）**：

| 臂 | specific_red | over_red |
|---|---|---|
| control | **24** | 22 |
| treat | **15** | **29** |

即 **注入 oracle 使 over_red 增加 7 行（22→29）、specific_red 减少 9 行（24→15）**，
而本报告已多次观测到"检出几乎完全由 specific_red 决定"。故**最可能的机制是
"注入提高了过红率"**（oracle 断言在 gold fixed 上失败 → 门①判 over_red →
路由再生成 → 终态检出下降）。

## 1. 干预生效性（A1 事故的防复发检查）

- 双臂 `provenance.env_snapshot.SPEC_ORACLE_EXEC_ENABLE` 分别为 `false` / `true` ✅
- treat 臂 `spec_oracle_verdict` 分布：injected 20 · compiled_empty 16 · **not_attempted 5** · injected_and_passed 5
- control 臂：**全部 not_attempted**（0 注入）✅
- `PYTEST_TIMEOUT_ENABLE=true` 入快照 ✅（本次挂死修复的配套开关）

**→ 干预确实生效，且可从工件证明**（这正是此前缺 `spec_oracle_injected` 行级字段导致无法验证的那一环）。

## 2. 成本（实测，非估算）

| 臂 | 总 token | input | output | 成本 |
|---|---|---|---|---|
| control | 695,751 | 502,979 | 192,772 | $0.382 |
| treat | 774,434 | 564,646 | 209,788 | $0.421 |
| **合计** | 1,470,185 | — | — | **≈$0.80** |

价目：deepseek-flash $0.3/Mtok(in) + $1.2/Mtok(out)（experiments/price_table.json，峰时全额=上界）。

## 3. 必须附带的口径限定（不得省略）

1. **n=37、不一致对仅 15**——功效有限；p=0.0389 是**边际显著**，
   未做聚类校正（QuixBugs 任务间无模板簇，但共享"to_base 类"缺陷族）；
2. **treat 臂内并非全部注入**（25/46）——`compiled_empty` 16 行、`not_attempted` 5 行，
   故这是**意向性分析（ITT）**口径，不是"纯注入效应"；
3. treat 臂内**注入组 detection 6/25 = 24% vs 未注入组 9/12 = 75%**，
   方向与 ITT 一致，但**这是观察性对比（注入与否非随机），不可作因果解读**；
4. **本批关闭变异评分** → 无 mutation_score，不作为本次结论依据；
5. control 臂 64.9% 与历史同基准 45.9%（BASELINE.yaml:381-386）**不同**——
   两者协议差异未逐项对齐（本次排除了 4 个不终止任务、开了 pytest 超时、
   未开变异评分），故 **control 臂的绝对值不可与历史数字直接比较**；
   A/B 结论只依赖**双臂同批配对**，不依赖跨批可比性。
6. **排除 4 个不终止任务是必要取舍**：它们本就 `detection=None`
   （M1 第 1 段"buggy 上变红"无从判定，fail-closed），排除不损失主终点信息；
   但会把"挂起型缺陷"整类移出评估面——**这正是 I-08/hang 通道要解决的问题**。

## 4. 对报告结论的影响

- **§6.8 更正框**（"逻辑驱动净效应未知"）→ 现在**有了一手 A/B 证据：
  净效应为负（−24.4pp, p≈0.04），机制指向 over_red 升高**；
- 这**强化**了路径 **P2-L1** 的诊断：问题不在"有没有逻辑通道"，而在
  **注入的 oracle 断言本身过苛/不忠实**（对应 I-25 规格保真审计）——
  oracle 在 gold fixed 上失败 = 门①判 over_red = 该行被判"红得不特异"。
- **新增建议 I-28**：把"oracle 断言在 gold fixed 上是否通过"作为
  **规格忠实的必要子条件**（SWE-PROOF 的 spec-audit 思路落地），
  先于"提高注入率"——否则注入越多、over_red 越多、检出越低。
