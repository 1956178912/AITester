# 外部文献读数登记（EXTERNAL READINGS REGISTER）

> 生成：2026-10-25（CN 轮）；用途 = 论文在 Related Work / Discussion 中引用的**外部**
> 数字，逐条登记出处与原文读数，供 `scripts/tools/audit_paper_numbers.py` 的
> 「数字存在性」判据核对。

## 0. 这份登记册验证什么、不验证什么

- **验证**：论文里写的这个数字，与登记册里抄录的原文读数一致；登记册里同时给出
  出处（DOI/arXiv 号）与检索日期，人可以逐条回查。
- **不验证**：这些数字**不是本仓库复算出来的**。内部数字的 SRC 指向
  `experiments/results/` 或 `BASELINE.yaml`，可零 LLM 复算；外部数字只能登记，
  不能复算。审计器对两者的判据形式相同，**证据强度不同**，正文与附录不得把
  二者混为一谈。
- 登记纪律：只登记**能从原文（摘要/正文）直接抄到**的读数；版本间读数不一致时，
  登记**会议/期刊定稿**并注明版本差异，不取「看起来更好」的那个。
- 检索日期：2026-10-25。

## 1. 编排 vs 单提示（RQ2 的外部对照）

| 键 | 读数 | 原文表述 | 出处 |
|---|---|---|---|
| `konstantinou2026icst` | +17.72 / +19.80 / +20.92 | "a plain LLM approach outperforms all of them on line coverage (+17.72%), branch coverage (+19.80%), and mutation score (+20.92%) at comparable query cost" | ICST 2026（DOI 10.1109/ICST65540.2026.00012，见 `refs.bib`） |
| `arna2026icstw` | 3–4× | "they yield an ESR comparable to single-agent frameworks ... at the expense of a threefold to fourfold increase in token expenditure" | ICSTW 2026, pp. 29–36（DOI 10.1109/ICSTW72326.2026.00018） |
| `radaideh2026bdai` | 69.90 / 45.63 | "one-shot GPT-4o reaches a 69.90% mutation score versus CANDOR's 45.63%" | BDAI 2026（DOI 10.1109/BDAI70753.2026.11655121，Crossref 2026-10-25 核验） |
| `radaideh2026bdai` | 88.35 / 35.92 | "one-shot Gemini 2.5 Flash reaches 88.35% versus CANDOR's 35.92%" | 同上 |
| `radaideh2026bdai` | 45 s / 50 h | "in about 45 seconds, while CANDOR with Gemini took roughly 50 hours" | 同上 |

**版本差异（必须留存）**：`arna2026icstw` 的 ESR 读数在不同版本里不一致——
POLITO 机构库与 IEEE CSDL 摘要写 "96.88% versus 96.89%"，ResearchR 会议页写
"97.31% versus 97.25%"，覆盖率峰值亦有 99.54% / 99.75% 两版。正文因此**只取
跨版本稳定的定性结论**（执行成功率无可测差异、token 三到四倍），不引用这两组
小数。这是「同一结论、不同快照」的典型，登记在此以免日后被当成新数据。

## 2. 评测任务族与检出上限（RQ1 的外部对照）

| 键 | 读数 | 原文表述 | 出处 |
|---|---|---|---|
| `sun2026swemutation` | 10.20 / 36.15 | "even DeepSeek-V3.1 achieves only 10.20% verification and 36.15% detection rates" | Findings of ACL 2026, pp. 39651–39674（DOI 10.18653/v1/2026.findings-acl.1976） |
| `sun2026swemutation` | 71.04 / 39.81 | "reducing average detection rates from 71.04% to 39.81% compared to conventional methods" | 同上 |
| `sun2026swemutation` | 2,636 / 800 | "2,636 mutated variants derived from 800 original instances" | 同上 |
| `hamidi2026criteria` | ~99% | "traditional test criteria fail to trigger and detect almost all faults examined (approximately miss approximately 99% of them)" | arXiv:2609.09315 |
| `hamidi2026criteria` | 6,000+ | "We collect 6,000+ faulty program instances" | 同上 |
| `liu2026testexplora` | 16.06 | "state-of-the-art models achieve a maximum Fail-to-Pass (F2P) rate of only 16.06%" | ICML 2026, PMLR v306 |
| `liu2026testexplora` | 2,389 / 482 | "2,389 tasks across 482 repositories" | 同上 |

## 3. 规格锚点与「先测试后编码」（RQ4 的外部对照）

| 键 | 读数 | 原文表述 | 出处 |
|---|---|---|---|
| `tufano2026specops` | 9.8 / 53.4 / 63.2 | "a 9.8 percentage points (p = 0.0352) improvement in bug detection rate" over a 53.4% baseline, reaching 63.2% | SpecOps '26（DOI 10.1145/3842652.3843195；arXiv:2608.17177） |
| `tufano2026specops` | 2.5 | "a 2.5 percentage point (p = 0.0034) improvement in branch coverage" | 同上 |
| `tufano2026specops` | 0.0352 / 0.0034 | McNemar p-values quoted above | 同上 |
| `tufano2026specops` | 90 | "a dataset of 90 historical production bugs from Google's Issue Tracking System" | 同上 |
| `konstantinou2026coding` | 25 / 14 | "a fault detection rate of 25% for a test-driven workflow versus approximately 14% when tests follow code generation" | arXiv:2607.05139 |
| `konstantinou2026coding` | 13.2 | "Providing both sources reduces fault detection by 13.2% on average relative to the description alone" | 同上 |
| `konstantinou2026coding` | 15.1 | "providing only the implementation reduces it by 15.1%" | 同上 |

## 4. 论文中已存在、此前未登记的外部读数（本轮补登记）

| 键 | 读数 | 原文表述 | 出处 |
|---|---|---|---|
| `zhao2026misguidance` | 0.46 / 3.84 | "raises misguided tests from 0.46% to 3.84% of generated tests" | ISSTA 2026（见 `refs.bib`） |
| `zhao2026misguidance` | 8.51 / 2.98 | "reducing effective tests from 8.51% to 2.98%" | 同上 |
| `zhao2026coverage` | 13 | "Across thirteen model setups on Defects4J" | 同上（`refs.bib` 记为 ISSTA 2026 复现研究） |

## 5. 未采用的候选（登记为「查过但不用」，防止重复检索）

| 候选 | 为什么不引入正文 |
|---|---|
| SWT-Bench 榜单 2026 读数（Lite 89.1% / Verified 84.0%） | 榜单是滚动更新的运行产物，不是同行评审定稿；引用即过期。正文只把 SWT-Bench 作为**任务族**引用，不引榜首数字。 |
| 「多智能体没有更好」的博客/论坛实测（如 20 任务三组对比） | 非同行评审、无工件，不能作为证据。 |
| ICLR 2026 CAO workshop 的 prompt-drift 结果 | 与本稿 RQ2 的机制不同（协议漂移 vs 编排预算），且为 workshop poster；不扩范围。 |
