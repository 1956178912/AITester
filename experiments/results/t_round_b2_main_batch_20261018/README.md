# T1（B2）：主批次锁指纹复现批（3 seed × 3 臂，synthetic n=87/seed）

> **性质：复现性测量（decision-grade），非能力主张。** 预注册见 `PREREG.md`（跑前冻结）、
> 成本估算修正见 `PREREG_AMENDMENT_cost_estimate.md`（判据未改）。

## 0. 预注册判定

| 项 | 结果 |
|---|---|
| **verdict** | **`not_reproduced`** — R1 或 R2 反向/不成立 |
| §1.1 硬门槛（干净树/指纹/行数/exit） | `PASS` |
| R1 合并排序 df>aitester>plain | `False` |
| R2 aitester vs df 配对差 | δ=-0.2529 （-25.29pp）；b/c=4/70；McNemar p=0.0；CI95=[-0.3103, -0.1954] |
| R3 逐 seed 排序 | `False`（seed []） |

## 0.5 与原批的机制对照（描述性；不用于改判）

### 0.5.1 stop_reason 分布（三 seed 合并，逐臂）

| 臂 | 新批 stop_reason | 原批 stop_reason |
|---|---|---|
| `aitester` | {'test_passed': 207, 'test_defect_regeneration_cap': 33, 'max_iterations': 21} | {'test_passed': 143, 'skip_debugger_repair_invalid': 77, 'None': 21, 'max_iterations': 20} |
| `plain_llm` | {'test_passed': 213, 'unknown': 48} | {'test_passed': 229, 'unknown': 32} |
| `plain_llm_df` | {'test_passed': 129, 'unknown': 132} | {'unknown': 254, 'test_passed': 7} |

### 0.5.2 logic 档预设漂移（候选机制来源，非因果证明）

logic 档自 R-P0-2 切点新增 **5** 个行为开关（R-P0-2 切点未启用）：`DETECTION_SPECIFICITY_GATE_ENABLE`、`FL_SPECTRAL_ENABLE`、`LOGIC_SPEC_STRICT_FALLBACK_ENABLE`、`MUTATION_ADVISOR_ENABLE`、`RED_REGRESSION_GATE_ENABLE`。本批按当前 documented protocol（logic 档）运行，因此**新批不是 R-P0-2 的逐字节等价重跑**；R1 未复现与这些漂移的相关性只能作为**候选机制**，因果归属需下一轮的逐开关消融（另预注册）。

### 0.5.3 解释边界（写死口径，防事后改写）

- **正面（R2）**：新批 `aitester` vs `plain_llm_df` 的配对差为 δ=-0.2529（-25.29pp；b/c=4/70；McNemar p=0.0；bootstrap CI=[-0.3103, -0.1954]）——头条结论的核心负面证据（编排 vs df 提示协议的检出差距，方向为负）在新协议下**仍然成立且显著**。
- **未复现（R1/R3）**：预设的完整排序 `plain_llm_df > aitester > plain_llm` 未成立（R1=False；R3=False）。注意：R-P0-2 中 `aitester > plain_llm` 这一**次级排序**本身不是核心结论；其未复现意味着"aitester 检出高于裸提示"在当前协议下不成立（新批部分 seed 甚至更低）。
- **不得**把本批差异归因于模型能力变化（同切点同模型指纹）；也**不得**声称"编排更差"是因果结论——协议漂移是混杂因素。可辩护表述："R-P0-2 头条批次的检出数字对 logic 档协议版本敏感；核心负面（vs df）稳健，次级排序（vs 裸提示）不稳健"。

## 1. 合并口径（3 seed 池化，n=261/臂）

| 臂 | 检出/可测 | detection | repair | false_fix | tokens | 成本(USD, 估算) |
|---|---|---|---|---|---|---|
| `aitester`（新批） | 8/261 | 0.0307 | 22/261 | 200/261 | 2629059 | 1.447277 |
| `aitester`（R-P0-2 旧批） | 38/240 | 0.1583 | — | — | — | — |
| `plain_llm`（新批） | 31/261 | 0.1188 | 0/261 | 213/261 | 310018 | 0.260967 |
| `plain_llm`（R-P0-2 旧批） | 4/261 | 0.0153 | — | — | — | — |
| `plain_llm_df`（新批） | 74/261 | 0.2835 | 0/261 | 129/261 | 643952 | 0.541408 |
| `plain_llm_df`（R-P0-2 旧批） | 117/261 | 0.4483 | — | — | — | — |

## 2. 逐 seed 检出（新批 vs 旧批）

| seed | 臂 | 新批检出/可测 | 新批率 | 旧批检出/可测 | 旧批率 | 新 vs 旧 配对 δ | 不一致 b/c | McNemar p |
|---|---|---|---|---|---|---|---|---|
| 42 | `aitester` | 4/87 | 0.046 | 12/81 | 0.1481 | — | — | — |
| 42 | `plain_llm` | 9/87 | 0.1034 | 1/87 | 0.0115 | — | — | — |
| 42 | `plain_llm_df` | 24/87 | 0.2759 | 38/87 | 0.4368 | — | — | — |
| 43 | `aitester` | 0/87 | 0.0 | 15/79 | 0.1899 | — | — | — |
| 43 | `plain_llm` | 12/87 | 0.1379 | 1/87 | 0.0115 | — | — | — |
| 43 | `plain_llm_df` | 27/87 | 0.3103 | 36/87 | 0.4138 | — | — | — |
| 44 | `aitester` | 4/87 | 0.046 | 11/80 | 0.1375 | — | — | — |
| 44 | `plain_llm` | 10/87 | 0.1149 | 2/87 | 0.023 | — | — | — |
| 44 | `plain_llm_df` | 23/87 | 0.2644 | 43/87 | 0.4943 | — | — | — |

> 说明：第 2 节表内「新 vs 旧」配对列按臂汇总（三 seed 合并），逐 seed 明细见 ANALYSIS_REPORT.json。

## 3. 新批 vs 旧批配对一致性（按 seed+task 配对，三 seed 合并）

| 臂 | 配对数 | b(新检出旧未) | c(旧检出新未) | δ | McNemar p | CI95 |
|---|---|---|---|---|---|---|
| `aitester` | 240 | 4 | 34 | -0.125 | 6e-07 | [-0.175, -0.0792] |
| `plain_llm` | 261 | 30 | 3 | 0.1034 | 1.4e-06 | [0.0651, 0.1456] |
| `plain_llm_df` | 261 | 26 | 69 | -0.1648 | 1.183e-05 | [-0.2337, -0.0958] |

## 4. 成本与 provenance

- tokens=3583029；实测估算成本=**$2.249652**；跑前估算=$4.518（口径已修正为 $8.8，见 amendment）；预算参考=$6.0
- 新批 git_dirty=False / git_sha=a93c1f60ee31b9582e0146f73e3038e6ce0f01a1 / fingerprint.pinned=True；旧批 git_dirty=True / fingerprint 在场=False
- 逐 seed env_snapshot / harness 漂移明细见 ANALYSIS_REPORT.json `provenance_drift`。

### 4.1 logic 档预设漂移（R-P0-2 切点 b533cff → 本批切点 a93c1f6）

logic 档开关数 13 → 18；新增 **5**、删除 0、改值 0。

| 新增开关 | 生效值 |
|---|---|
| `DETECTION_SPECIFICITY_GATE_ENABLE` | `true` |
| `FL_SPECTRAL_ENABLE` | `true` |
| `LOGIC_SPEC_STRICT_FALLBACK_ENABLE` | `true` |
| `MUTATION_ADVISOR_ENABLE` | `true` |
| `RED_REGRESSION_GATE_ENABLE` | `true` |

> 这些开关改变的是 aitester 臂的**再生成路由/变异反馈/定位测量**，是本批与 R-P0-2 的协议级差异；本批判据因此限定为『当前切点 documented protocol 下方向性复现』，不作逐字节等价陈述。

## 5. 局限

- 单次运行/seed，温度 0 仍有服务端非确定性；复现判据只到方向/排序级，不要求逐位相等
- harness 自 R-P0-2（2026-10-06, b533cff）演进至 a93c1f6：logic 档/默认开关增量为披露项（见 provenance_drift），跨批差异不作单一归因
- detection 为 M1 行口径（detection_rate≥1）；repair/false_fix 随行口径并列，不与旧批修正口径混用
- 成本为官方价目表峰时全额估算（非账单）；跑前估算曾误设 input 份额，已在 PREREG_AMENDMENT 披露

## 6. 复算入口

```bash
.venv/bin/python experiments/analyze_t1_b2_main_batch.py \
    --out experiments/results/t_round_b2_main_batch_20261018 \
    --orig-dir experiments/results/main_batch --write
```

<!-- MANUAL:BEGIN -->（手工维护节：生成器 --write 时原样保留在文末；块内引用数字更新须人工与 ANALYSIS_REPORT.json 核对。）

## 0.6 T 轮发现（可辩护表述，写死防事后改写）

1. **核心负面稳健、次级排序不稳健**：新批 `aitester` vs `plain_llm_df` 配对差 **δ=−25.29pp**
   （b/c=4/70，McNemar p≈0，bootstrap CI [−31.0,−19.5]pp）——"编排 vs df 提示协议在检出上
   净负"这一点在新协议下**仍成立且显著**；但 R-P0-2 的次级排序
   （`aitester 15.8% > plain_llm 1.5%`）**未复现**（新批 pooled：aitester **3.07%**、
   plain_llm **11.88%**、df **28.35%**）。按预注册冻结规则判 `not_reproduced`
   （R1 排序失败，尽管 R2 成立）——不做事后改判，R2 作为并列证据如实报告。
2. **漂移波及全部臂，不能只归因于 logic 档新增开关**：`plain_llm` 是单次提示臂，
   logic 档的 5 个新增行为开关（specificity/red-regression gates、FL-spectral、
   mutation-advisor、strict-fallback）理论上不改变它的生成路径，却从旧批 **1.53%**
   变为新批 **11.88%**；df 44.83%→28.35%；aitester 15.83%→3.07%。⇒ 跨批差异中存在
   **全局性因素**（模型服务端行为/推理模式/测量路径），不能全部归因于协议开关。
3. **已定位的确定性漂移：推理（thinking）模式**。R-P0-2 切点（`b533cff`）的
   `llm_client` **尚不存在 `LLM_THINKING_MODE` 开关**（该开关在更晚的 `6e46463` 才加入，
   `git merge-base --is-ancestor` 实测非祖先），即旧批按模型**默认推理模式**运行；
   本批显式设 `LLM_THINKING_MODE=disabled`（现代默认）。token 证据：旧批 output 占比
   **78.6%**（2,276k in / 6,880k out，总 8.76M）；新批 output 占比 **36.4%**
   （2,278k in / 1,305k out，总 3.58M）——总 token 少 2.4×，且旧批高 output 份额与
   reasoning token 计入 completion 的形态一致。**即：旧批与新批不是同一推理模式下的重跑**，
   这是比"5 个 profile 开关"更早、更全局的混杂因素。
4. **成本估算差异获得解释**：修正后上界估算 $8.8 基于旧批 token 结构；本批实测
   **$2.249652**（3.58M tokens），差异主因即推理模式（思考输出 token 大幅减少）。
   跑前估算仍是**上界**口径而非预测，AMENDMENT 的方法学结论不变（份额必须实算）。
5. **可执行建议（下一轮立项，不在本批改判）**：
   - **推理模式 2×2**：{thinking on/off} × {R-P0-2 legacy profile / current profile}，
     在干净切点、固定 seed/task 集、指纹 pinned 下跑，隔离"推理预算"与"协议开关"两个因素；
   - 旧批数字一律标注"无推理模式记录、无 model_fingerprint、git_dirty=true"，**不得**
     与新批（`not_reproduced`）混池；本批可作为**当前协议的新基线**供后续批内比较；
   - `plain_llm` 跨批波动属 Q5 已知问题（历史 1.5%→19.2%），本批 11.88% 再次佐证
     "跨批不可比、同批对照才可辩护"。

<!-- MANUAL:END -->
