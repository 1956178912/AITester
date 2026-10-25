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
| A3 | 复现包闭环：零 LLM 复算链 L0/L1 每条命令 ok 或显式 [SKIP] 带实测理由；REPLICATION.md 每项数字/路径指向在盘工件 | **待核**（L0 已 [SKIP] 化；REPLICATION.md 对 v0.8.0 语料撤回后的路径/数字未全面复查） |
| A4 | 论文数字审计：`paper-audit --strict` 通过（200 条声明可追溯 100%、无效引用 0） | **待核**（v0.5 数据换代重写后头注列为未竟项） |
| A5 | 三必披露缺口在论文**正文**显式披露：① fixed 臂 53/261 行无 token 记录的成本下界口径；② 合成数据发生器的漂移；③ scale87 SpecExpr 未测 | **待核**（v0.3 头注有 ① 的记载，正文形态待验；②③ 待验） |
| A6 | 双语文档同步 + 文档链接 strict 零失败；登记册/INDEX/MEASUREMENT_INTEGRITY 与实测一致 | **绿**（CJ 轮刷新） |
| A7 | 已知限制完整披露：README「已知失败/已知限制」行、MODEL_CARD §限制、论文 Threats 段与仓库实况一致 | **待核** |

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
