# ADR-0036: 1.0.0 发布判据——「前沿领先」在测量廉洁纪律内的操作化定义

- **状态**：已接受
- **日期**：2026-10-25
- **决策**：1.0.0 = **判据 A（测量面前沿）与判据 C（发布机械）全部关闭且干净树全链复跑绿**；
  判据 B（研究面前沿）中需外部授权/人工决策的项目**不阻塞 1.0.0**，以本 ADR + 论文占位 +
  README 已知限制诚实披露，并编入 1.x 计划。「前沿领先」不通过夸大主张实现——本项目核心结论
  多为阴性（编排净 −28pp、spec-first 三检全负），领先性体现在**测量装置本身**（32 道门禁 /
  单一事实源 / 变异锚定锁 / 零 LLM 复算链）与**声明的可追溯性**（论文 200 条数字声明 100% 可追溯）。

## 1. 背景

v0.8.0（2026-10-25）完成测量廉洁重置 + DeepSeek 单端点语料重建 + PROMPT-SE 投稿版重写
（180 轮逐轮评审-修复）。用户提出下一目标：**迭代到 1.0.0 稳定版，且达到前沿领先水平**。
仓库此前无 1.0.0 定义、无路线图文档；待办清单中四类项目（E7 人工裁决 / 论文投稿 /
LLM 配额实验 / D3 全量 Mut@k）均含外部依赖。本 ADR 把「稳定 + 前沿领先」拆成可判定、
可分批关闭的三组判据。

## 2. 判据 A：测量面前沿（全部可自主关闭，零 LLM）

| # | 判据 | 当前状态（2026-10-25 CJ 轮收口） |
|---|---|---|
| A1 | 门禁链 20 步干净树 rc=0（lint/format/mypy/全量测试/双语文档/env-budget/baseline/state-contract/env-snapshot/model-fingerprint/tool-versions/json-contract-sites/json-strict/artifact-doc-consistency/zero-assert/ast-guards/status-persistence/registration-consistency/invocation-caliber/flag-effect） | **绿**（CJ 轮实测） |
| A2 | 全量测试零失败（正常口径 collected 与 BASELINE 登记逐位一致） | **绿**（12,490 passed / 268 skipped / 0 failed，collected 12758） |
| A3 | 复现包闭环：零 LLM 复算链 L0/L1 每条命令 ok 或显式 [SKIP] 带实测理由；REPLICATION.md 每项数字/路径指向在盘工件 | **已关闭（CM 轮）**：L0 实测 3 ok / 3 显式 [SKIP] / rc=0；完整性校验改四态后 **8 目录 / 401 文件通过 / 0 失败 / 5 目录缺席披露**（改前「0 通过 / 0 失败 / 6 跳过」仍读作绿）；REPLICATION.md 补路径三类口径 |
| A4 | 论文数字审计：`paper-audit --strict` 通过（200 条声明可追溯 100%、无效引用 0） | **已关闭（CM 轮）**：210 条声明 / 综合可追溯率 100.0% / SRC 无效 0 / strict 块失败 0。**并发现一处真实断裂**：附录 E 成本表的 SRC 指向不含该数字的工件（路径存在、数字不在，审计仍报 100%）——已改 historical + 表 W-1 落点，工具新增块级数字存在性判据（A/B：错指针 rc=1） |
| A5 | 三必披露缺口在论文**正文**显式披露：① fixed 臂 53/261 行无 token 记录的成本下界口径；② 合成数据发生器的漂移；③ scale87 SpecExpr 未测 | **已关闭（CM 轮，含勘误）**：① 实为两件事——fixed 材料缺口 53/261（过红上限 69/88）与 df 臂 token 记账下界 35/261（附录 E caption）；② 模板库 30→50 + 6 模板 gold 修复 ⇒ 归档 mutation 值只能以归档件复算；③ scale87 的 `DETECTION_SPEC_MODE=replace` ≠ 完整 SpecExpr 路线。②③ 落 Threats / Instrument provenance |
| A6 | 双语文档同步 + 文档链接 strict 零失败；登记册/INDEX/MEASUREMENT_INTEGRITY 与实测一致 | **绿**（CM 轮刷新） |
| A7 | 已知限制完整披露：README「已知失败/已知限制」行、MODEL_CARD §限制、论文 Threats 段与仓库实况一致 | **已关闭（CM 轮）**：README 双语新增「已知限制（1.0.0）」7 条；MODEL_CARD §4 加世代横幅（261 行池标 historical）；论文 Threats 补三处 |

## 3. 判据 B：研究面前沿（需用户授权或人工决策，不阻塞 1.0.0）

| # | 项目 | 阻塞原因 |
|---|---|---|
| B1 | LLM 配额实验：B1 2×2 / ULT accuracy / TestGenEval-Lite / B2 指纹 / SWE-bench Lite | 消耗付费配额，需用户授权 |
| B2 | D3 全量 Mut@k（cosmic-ray 全量，6 周量级） | 计算时长，需用户授权排期 |
| B3 | E7 人工裁决（三路径备料 n=8/41/72） | 人工决策 |
| B4 | 论文投稿（EMSE）+ Zenodo DOI / 双盲 TODO(submit) 占位替换 | 外部投稿流程 |

**纪律**：B 组每项在 ADR-0036、论文对应占位、README 1.x 计划三处同文登记；1.0.0 的「前沿」
主张只覆盖 A 组已关闭面，不借用 B 组未执行实验的任何暗示。

## 4. 判据 C：发布机械（可自主关闭）

1. `src/__init__.py` `__version__` → `1.0.0`；`pyproject.toml`（attr 引用，随动）。
2. `CITATION.cff`：`version: 1.0.0` + `date-released`。
3. README 双语「当前版本」块、MODEL_CARD 双语、QUICKSTART 双语的版本/最后更新行。
4. CHANGELOG 双语：新增 `## [1.0.0]` 节，归并全部 `[Unreleased]` 轮次段（CA–CJ 及
   关闭 A 组差距的新轮次），写版本主题。
5. BASELINE.yaml `last_verified` 与登记册 §1 随发布轮刷新；版本相关锁（如有）同轮推进。

## 5. 执行顺序

1. 差距清单（对照 A3/A4/A5/A7 逐项实测，登记册 §5 记条目）。
2. 逐轮关闭（CK 起，沿用既定轮次方法论：沉默分叉 → 单一事实源 → 读侧统计 → 测试锁 →
   变异锚点 → 干净树门禁复跑 → 双语文档收口）。
3. A 组全绿 ⇒ 执行 C 组发布机械 ⇒ 干净树全链复跑 ⇒ 推送 ⇒ 打 tag `v1.0.0`。
4. B 组作为 1.x 计划列于 ADR-0036 §3 与 README，不阻塞。

## 6. 非目标

- 不在 1.0.0 引入新功能（新功能走 ADR 单独评审）；1.0.0 是**测量与发布纪律的收敛版**。
- 不改任何已发表的阴性/阳性结论的方向；只做可追溯性、披露完整性、登记一致性收口。

## 7. CM 轮实测记录与判据订正（2026-10-25）

### 7.1 A4：可追溯率 100% 曾是「路径存在」冒充「数字在工件里」

附录 E 的成本表（26,114.9 tokens/task、$0.025885、35-of-261）来自**已撤回**的
261 行池（`emse_stats_extensions_20261021`，commit `d5bda23e`），而 SRC 指向
在盘的 `emse_stats_extensions_20261025/`——该工件只有 n=20/36/41 的单批臂，
**不含这些数**。审计器此前只判路径存在，故 `--strict` 全程绿。

- 处置：论文改 historical + 落点本仓 `WITHDRAWN_ARTIFACTS_2026-10-24.md` 表 W-1
  （冻结原值）；该表加 `// SRC-CHECK: strict`。
- 工具：新增块级数字存在性判据。**边界**：p 值 / CI / z 常数是派生量，不字面存盘，
  只作披露；`strict` 是作者显式声明「这块是存盘读数」的契约，不是自动语义分类器。
  当前 210 条声明中，12 段派生量块与 7 段无可判定工件块按披露计。

### 7.2 A5 ①：登记本身把两件事写成了一件（已勘误）

本 ADR 原 A5 ① 写「fixed 臂 53/261 行无 token 记录」，实测是两个不同事实：

| 事实 | 读数 | 出处 |
|---|---|---|
| fixed 材料缺口（`task_metadata.fixed` 缺失） | 53/261 行（20.3%），过红机制分析上限 69/88 | `CHANGELOG.md` 2026-10-13 条；`docs/VALIDITY.md` §4 |
| df 臂 token 记账下界（`token_usage` 全 0 但 `generated_test` 非空） | 35/261 行 | `WITHDRAWN_ARTIFACTS_2026-10-24.md` 表 W-1 |

两者均属撤回世代；论文已分别在 Threats / Internal validity 与附录 E caption 披露。
**教训**：登记面的「一行」也会把两个事实折叠成一个，与代码侧收口的折叠同族。

### 7.3 A3：完整性校验曾在 0 份受检文件时也是绿的

6 条清单里 5 条目录已撤回、唯一在盘目录没有清单，报告输出
「0 通过 / 0 失败 / 6 跳过」——「没清单」被读成「跳过」。四态化后
（`ok` / `FAILED` / 无清单=FAILED / `absent` 披露）实测 8 目录 / 401 文件通过。
**边界**：受检面排除 `traces/`；清单随工件在本机生成，工件分发（Zenodo）
仍为 1.x 待办——1.0.0 声称的是「在本机工件上可校验」，不是「已随包分发」。

### 7.4 A5 ②③ 的落点

② 在 Threats / Instrument provenance 披露模板库漂移（30→50、6 模板 gold 修复、
seed=42 重建哈希不符）；③ 在同段披露 scale87 的 `replace` 臂不执行 SpecExpr
通道。两处均以 `BASELINE.yaml#synthetic_templates`、`CHANGELOG.md` 与
`docs/design/spec_replace_ab_scale87_prereg.md` §2.2 为证据。

### 7.5 外部定位核验（只取一手来源）

1.0.0 的「前沿」主张按 §2 只覆盖 A 组（测量装置），不以外部榜单加冕。做过的
外部核验与**拒绝引入**的读数：

- **已核**：EMSE「Replications and Negative Results」专刊为官方 CFP
  （`emsejournal.github.io/special_issues/2024_SI_RENE.html`，截稿 2025-06-20），
  论文的投稿定位以此为据；
- **未引入**：检索到的 SWE-bench Lite 聚合榜单/博客读数互相矛盾，同一页面出现
  无法核实的模型命名与版本，**一个数字都没有进本仓库或论文**；本项目对
  SWE-bench Lite 的结论仍只有「20 次尝试全为基础设施故障，无能力结论」；
- **纪律**：外部数字只在能追到一手页面（官方 CFP / 论文 DOI / 官方榜单）时引用；
  聚合站排名不作为「前沿」证据。
