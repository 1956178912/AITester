# T4 对外声明对抗式证据核验（task-4）

> 角色：独立审查团队"怀疑论者"。规则：项目声称的每个关键数字，都在**入库工件**
> （`experiments/results/**/*.json`）里亲手算一遍，或明确写出"无法核验及原因"。
> 产物只写本文件；仓库源文件零改动（`git status` 仅新增 `review_2026/`）。
>
> 核验环境：HEAD `d9e51df`（2026-10-10 16:28 文档清理批）；Python 3.14.6（`.venv`）。
> 零 LLM 成本：全部为只读统计 + 本地 pytest 重放（不触网、无 API key）。

## 0. 结论速览

| # | 声明 | 结论 | 关键偏差 |
|---|------|------|----------|
| 1 | detection 117/261 · 38/240 · 4/261 | **支持**（逐位） | 三臂分母不同源；δ 是贝叶斯后验均值非原始差 |
| 2 | repair 57/145=39.31% · 58/106=54.72% | **支持**（逐位，独立重放） | E1/E2「四批次」实为 2 种子×2 次重跑（同 cache namespace） |
| 3 | QuixBugs 17/37 · 37/40 · 31/37 · p=0.0005 | **部分支持** | repair 同源重放为 **37/41=90.2%**，非 37/40=92.5% |
| 4 | spec_compile 0.472–0.517；expr 0.72–0.74；注入 2–3/87、20/50 | **部分支持** | 前两者分属不同批次；注入数**无入库证据** |
| 5 | coverage 84.0–93.6 vs 86.0–97.2；mutation 0.818–0.976 vs 0.986–0.997 | **支持**（区间逐位） | BASELINE 注记「10 批次 n=87」与工件不符（实为 8 批含 n=50） |
| 6 | $/task 0.0259/0.0034/0.0045；QuixBugs 16038 vs 1905（8.4×） | **部分支持** | token 只在 41 行子集成立；全 50 行比值 6.6×；df 成本受 D2 低估 |
| 7 | 四起测量伪影的零 LLM 复现证据 | **部分支持** | ①274/274 ✓ ②✓ ③仅总量✓ ④「9/9 双 rc=2」「0/7→6/7」**无入库证据** |
| 8 | tests 5015 / mypy 119 文件 0 错 / ruff 0.16.3 | **部分支持** | ruff ✓；mypy 0 错但 **120** 文件；pytest 实测**收集 5178** |
| 9 | false_fix 87.2% · plausible 46.8% · CPR 84.3% · 弃权 86.0% · IDR 27.78% | **部分支持** | CPR 现值为 84.5%；**IDR 27.78% 已被 34.33%/34.85% 取代** |
| 10 | A1「实际等价」· E6 δ=−25.3pp 校正后显著 · RT1 +19.5pp 归因提示协议 | **部分支持** | A1 结论已作废（开关未生效）；E6 ✓；RT1 开关**不在 env_snapshot** |

计数：**支持 3 / 部分支持 7 / 不支持 0 / 完全无法核验 4 个具体数字**
（注入 2–3/87、20/50；9/9 双 rc=2；F2P 0/7→6/7）。

---

## 1. 逐条核验

### 声明 1｜detection 三种子合并

- **声明原文**：`detection：plain_llm_df 44.8%（117/261）> aitester 15.8%（38/240，21 行 M10
  第 0 轮死亡 None 不进分母）> plain_llm 1.5%（4/261）`
- **出处**：`BASELINE.yaml:159`（批次指针）、`:164-169`；`README.md:42`；
  `experiments/results/main_batch/statistical_report_3seed_pooled.md:33-37`
- **核验方式**：读三批次 `results.<arm>.details[].detection_rate`，None / 0.0 / 1.0 三态分开计数
  （代码见附录 A.1）
- **结论：支持（逐位吻合）**

| 臂 | hit | miss | None | 分母 | 率 |
|----|-----|------|------|------|----|
| aitester | 38 | 202 | 21 | 240 | 15.83% |
| plain_llm | 4 | 257 | 0 | 261 | 1.53% |
| plain_llm_df | 117 | 144 | 0 | 261 | 44.83% |

- **已核实的口径细节**：
  - 21 行 None **确为 M10 第 0 轮死亡**：21/21 行 `diagnosis` 含
    `"执行异常: M10 LOGIC_SPEC_STRICT_ENABLE=true：logic_analysis 缺失，拒绝静默兜底"`、
    `iterations=0`、`error_category="error"`。（`stop_reason` 与 `detection_first_status`
    在这些行是 `null`——M10 归因要靠 `diagnosis` 字段核验，不能靠 `stop_reason`。）
  - **None ≠ 0** 的正确性：None 行 `patch=null`、`generated_test=null`，确实是"没跑起来"
    而非"没检出"；把它们按 0 计入会得到 38/261=14.6%。
- **口径歧义 / 未披露风险**：
  1. **三臂分母不同源**：44.8% 与 1.5% 的分母是 261，15.8% 的分母是 240。
  2. **δ 不是原始配对差**：报告表中 δ = Dirichlet(1,1,1,1) 后验均值
     `(n10−n01)/(n+4)`，不是 `(n10−n01)/n`。我手工复算的 2×2（aitester vs df，240 行：
    n10(df-only)=80、n01(aitester-only)=12）给出原始差 **−28.3pp**，而后验均值
    为 12−80)/244 = **−27.9pp**——报告写 −0.279，BASELINE/README 口语化为「−28pp」。
    两个口径都对，但**必须说明 δ 的定义**，否则"配对差 −0.279"会被误读为原始差。
  3. df 在 240 行配对子集上是 **106/240=44.2%**，与头条 44.8% 不同源。
  4. `git_dirty=true`（三批次 provenance 实测，`--allow-dirty`）：代码态不可由 sha 单独复现。

### 声明 2｜repair 修正口径

- **声明原文**：`修正口径 repair 重估 R-P0-2=39.31%（57/145）、E1/E2=54.72%（58/106）`
- **出处**：`BASELINE.yaml:152-158`、`:170-175`；`README.md:23-24`；
  `docs/design/repair_caliber_matrix.md:18-19`（⑤⑥）；
  `experiments/results/main_batch/corrected_report_v2.md` §1
- **核验方式**：**独立重放**（`experiments.repair_replay.replay_batch`，本地 pytest，零 LLM），
  逐批次重放并用 `normalize_patch_text` 清理补丁后跑 gold 测试（附录 A.2）
- **结论：支持（分子分母逐位吻合）**

| 批次 | patch 非空（分母） | 我重放 correct | 率 |
|------|-----|------|----|
| RP02 seed42 `..._140906` | 54 | 20 | 37.04% |
| RP02 seed43 `..._151907` | 46 | 20 | 43.48% |
| RP02 seed44 `..._164357` | 45 | 17 | 37.78% |
| **R-P0-2 合计** | **145** | **57** | **39.31%** ✓ |
| E1 seed42 `..._161053` | 27 | 14 | 51.85% |
| E1 seed44 `..._170147` | 26 | 15 | 57.69% |
| E2 seed42 `..._181638` | 27 | 15 | 55.56% |
| E2 seed44 `..._185941` | 26 | 14 | 53.85% |
| **E1/E2 合计** | **106** | **58** | **54.72%** ✓ |

  分母也可由工件独立复现：三批次 `patch` 非空行数 54+46+45=145，四批次 27+26+27+26=106。
  与 `corrected_report_v2.md` 首部「correct=115」一致（115=57+58+早期 0/15）。
- **口径歧义 / 未披露风险**：
  1. **E1/E2「四批次」不是四个独立观测**：`161053` 与 `181638` 同为
     `seed=42`+`cache namespace=seed42`，`170147` 与 `185941` 同为 seed44；
     两次跑批只是 git SHA 从 `d3c3cc4` 换到 `1a5a5a7`（同一 cache namespace 复用缓存）。
     去重到「每种子一批」后为 **29/53 = 54.7%**（率几乎不变，**n 腰斩**）。
     报"n=106"会把相关观测当独立样本。
  2. **修正值不落工件**：入库 JSON 的 `repair_rate` 仍是 `0.0`（三批次实测 0/261 全零）。
     39.31% 只在"零 LLM 重放"这一口径下存在。对外必须写"存量重放"，**不能**写成
     "入库工件 repair=39.31%"，否则审稿人打开 JSON 会看到 0.0。
  3. 重放依赖 `AITESTER_QUIXBUGS_DATA` / 本地 gold 材料；材料缺失行 fail-closed 记 None。

### 声明 3｜QuixBugs 修正结算

- **声明原文**：`aitester detection 17/37=45.9%、repair 37/40=92.5%、plain_llm_df
  detection 31/37=83.8%（配对 McNemar p=0.0005）`
- **出处**：`BASELINE.yaml:356-364`、`:374-388`；`docs/preregistration.md:455-471`
- **核验方式**：读 `experiments/results/e6_a1_batches/e4_quixbugs_FIXED_harness/{aitester,plain_llm_df}.json`；
  手工构造配对 2×2 并算 McNemar；另用 `repair_replay.replay_row` 逐行重放对照（附录 A.3）
- **结论：部分支持**

| 项 | 工件实际值 | 声明 | 判定 |
|----|-----------|------|------|
| aitester detection | 17 hit / 37 可测（None=13） | 17/37=45.9% | ✓ |
| aitester repair（工件 `repair_rate`） | 非空 40、命中 37 → 92.5% | 37/40=92.5% | ✓（工件口径） |
| aitester repair（**同源重放**） | **37/41 = 90.24%** | — | ⚠ 与 92.5% 不同源 |
| plain_llm_df detection | 31/37=83.8% | ✓ | ✓ |
| 配对 McNemar | n10=0 / n01=14 / both=17 / neither=6、χ²=12.071、**p=0.00051** | 不一致对 14、p=0.0005 | ✓ |

- **13 行 None 的构成已核实**：9 个 QuixBugs 测试驱动脚本（`*_test`，无 gold）
  + 4 个"缺陷实现不终止"（`bitcount/find_first_in_sorted/sqrt/wrap`，判分层超时 → None）。
  prereg「9 个测试驱动」与 BASELINE「4 个 None 因果」相加恰为 13 ✓。
- **必须修正的口径**：工件里 `repair_rate` 非空行是 **40**，但同一批工件的重放路径可裁决
  **41** 行——多出的是 `quixbugs__node`（`repair_rate=None`，但有 `patch`(685B) 与
  `test_cases`(427B)，重放判 `wrong_patch`）。逐行对照显示：
  `37 行 artifact repair=1.0 ↔ 重放 correct`（**零不一致**）、`9 行 skipped_no_material`、
  `3 行 artifact 0.0 ↔ wrong_patch`、`1 行 artifact None ↔ wrong_patch`。
  因此 **同族口径（ADR-0029:28-30、口径矩阵 ④）用的是 37/41=90.2%**，92.5% 依赖把
  该行排除在分母外。对外应统一引用 **37/41=90.2%**，或显式写"37/40（fail-closed 排除
  1 行不可裁决 patch）"。

### 声明 4｜规约通道指标与 oracle 注入

- **声明原文**：`spec_compile_rate 0.472–0.517；spec_expr_coverage 0.72–0.74；
  规约 oracle 注入：合成 2–3/87、QuixBugs 20/50`
- **出处**：`BASELINE.yaml:488-501`（a2_logic_chain_reach）、`:68-72`（target_quality）
- **核验方式**：逐批次聚合 `details[].spec_compile_rate` / `details[].spec_expr_coverage`
  （None 剔除后求均值）；注入数在全部工件与日志中全文检索
  `spec_oracle_injected` / `"oracle 已注入"` / `R1c`
- **结论：前两项支持（但分属不同批次）／注入数无法核验**

| 指标 | 声明区间 | 我复算（批次:n:均值） | 判定 |
|------|---------|---------------------|------|
| spec_compile_rate | 0.472–0.517 | 0.472(e6_phase1:87)、0.478(e4_quixbugs:50)、0.514(e6_phase2:87)、0.517(d1:87) | ✓ |
| spec_expr_coverage | 0.72–0.74 | 0.741(161053:45)、0.723(170147:51) —— **10-07 E1/E2 批** | ✓（批次归属见下） |
| oracle 注入（合成） | 2–3/87 | **无任何入库痕迹** | ✗ 无法核验 |
| oracle 注入（QuixBugs） | 20/50 | **无任何入库痕迹** | ✗ 无法核验 |

- **口径陷阱**：`0.472–0.517`（10-09 批）与 `0.72–0.74`（10-07 批）**不是同一批数据**。
  在 0.472–0.517 的那几个批次里，expr coverage 实际是 **0.612–0.792**；而 0.72–0.74 对应的
  批次 spec_compile_rate 只有 **0.205–0.219**。把两个区间并列成一句，会被读成
  "compile 0.47–0.52 且 expr 0.72–0.74"的同一口径。
- **注入数为何无法核验**：结果行 schema 没有 `spec_oracle_injected` 键（`BASELINE.yaml:110-112`
  描述其为 `SPEC_ORACLE_EXEC_ENABLE` 观测），该状态只写在 `state`（`src/graph/nodes.py:865`），
  未透出。全仓 `experiments/results/` 检索注入日志 **0 命中**。
  20/50 的唯一出处是 `.private/review/AITester_前沿对比与超越路径审查报告.md:1487`（**非入库
  工件**）。旁证 `oracle_type` 在该批 50/50 = `generated_test` 与该主张不矛盾，但**不能互证**
  （`oracle_type` 只区分 `enhanced_generated_test`/`generated_test`）。

### 声明 5｜target quality（被测代码覆盖率 / 变异得分）

- **声明原文**：`line coverage aitester 84.0–93.6% vs plain_llm 86.0–97.2%；
  mutation_score aitester 0.818–0.976 vs df 0.986–0.997`
- **出处**：`BASELINE.yaml:56-67`；`experiments/results/main_batch/target_quality_report.md:8-34`
- **核验方式**：按批次对 `details[].coverage` / `details[].mutation_score` 求均值，取批次均值
  的 min–max（附录 A.4）
- **结论：支持（区间逐位吻合），但 BASELINE 的口径注记与工件不符**

| 指标 | 声明 | 复算 | 判定 |
|------|------|------|------|
| coverage aitester | 84.0–93.6 | 84.0(`_151907`) … 93.6(`_121523`) | ✓ |
| coverage plain_llm | 86.0–97.2 | 86.0(`_121523`) … 97.2(`_151907`) | ✓ |
| mutation aitester | 0.818–0.976 | 0.818(`_170147`) … 0.976(`_140906`)，n=77–81 | ✓ |
| mutation df | 0.986–0.997 | 0.986 … 0.997 | ✓ |
| mutation plain_llm | （未声明） | 0.951–0.992 | — |

- **注记纠错**：`BASELINE.yaml:59` 写「10 批次区间（n=87/批，2026-10-06/07）」。
  实测：该区间只有在**排除两个 n=5 冒烟批**（`_112528`/`_112801`，plain_llm=70.4 会突破下界）
  且**包含 10-01 的 n=50 批**（提供 93.6/86.0 两个端点）后才成立；实际是 **8 批
  = 1×n=50 + 7×n=87**，且其中 4 批两两同值。写成"10 批次 n=87/批"会让审稿人复算失败。
- 另注：`coverage` 行级存在 0.0（失败行），区间是**批次均值**区间而非行级区间，
  且 `mutation_score` 的 n 只有 77–81（<87，部分行为 None）。

### 声明 6｜成本

- **声明原文**：`$/task aitester 0.0259 / plain_llm 0.0034 / plain_llm_df 0.0045`；
  `QuixBugs token/task aitester 16038 vs df 1905（成本高 8.4×）`
- **出处**：`BASELINE.yaml:179-180`（价目表口径）、`:361-363`、`:381-385`
- **核验方式**：`experiments/price_table.json`（deepseek-flash input \$0.3/Mtok、output \$1.2/Mtok）
  × 三批次 `token_usage.{input,output}_tokens` 手工计价；QuixBugs 侧按 50/41/37 三种分母重算；
  并按 `total_tokens==0` 的行普查 D2 污染面（附录 A.5）
- **结论：$/task 支持（逐位）／QuixBugs token 只在 41 行分母上成立**

| 臂 | input | output | total | tok/task | cost | **$/task** |
|----|-------|--------|-------|----------|------|-----------|
| aitester | 1,581,326 | 5,234,651 | 6,815,977 | 26,115 | \$6.7560 | **0.0259** ✓ |
| plain_llm | 142,783 | 694,881 | 837,664 | 3,209 | \$0.8767 | **0.0034** ✓ |
| plain_llm_df | 152,103 | 950,127 | 1,102,230 | 4,223 | \$1.1858 | **0.0045** ✓ |

| QuixBugs 分母 | aitester | df | 比值 |
|--------------|----------|-----|------|
| 41 缺陷程序（=声明口径） | **16,038** | **1,905** | **8.42×** ✓ |
| 50 全任务 | 15,253 | 2,309 | 6.61× |
| 37 可测 detection 行 | 16,866 | 1,939 | 8.70× |

- **必须附带的限定**：同一张 BASELINE 表里 detection 的分母是 **37**、token 的分母是 **41**、
  batch 是 50 —— "8.4×"是 41 行子集口径。原文「成本高 8.4×」若不写分母，复算者用 50 行会得 6.6×。
- **D2（缓存命中不计 token，`BASELINE.yaml:210-211`）的量化影响面**：
  规则 = `token_usage.total_tokens==0` 的行（`src/agents/base_agent.py:437` 缓存命中提前
  return 绕过 `record_usage`）。实测零 token 行数：

  | 批次（cache flag / namespace） | 零 token 行 |
  |------|------|
  | E6 control（cache=1, seed42） | aitester **50/87**、plain_llm **87/87**、df **87/87** |
  | A1-strip（cache=1, seed42） | aitester **16/87** |
  | E1/E2 `_161053`、`_170147` | plain_llm 87/87、df 87/87 |
  | E1/E2 `_181638`、`_185941` | aitester 60–61/87、plain_llm 87/87、df 87/87 |
  | R-P0-2 `_140906`/`_151907`/`_164357` | df **8/13/14**；aitester 与 plain_llm **0** |
  | 10-01 `_112528`/`_112801` | plain_llm 5/5 |

  **方向 = 系统性低估**；对声明 6 的具体影响：`0.0045`（df）是**下界**（35/261 行缺记账，
  按非零行均值回补约 \$0.0050/task，aitester/df 比值会从 5.76× 下降）；`0.0259`（aitester）
  与 `0.0034`（plain_llm）在 R-P0-2 上不受影响。**因此"aitester 贵 5.8×"是被高估的**。
  E6 批的三臂 token 记账基本不可用（BASELINE 已自认「不得作预算配对基准」，✓ 与实测一致）。

### 声明 7｜四起测量伪影的零 LLM 复现证据

- **出处**：`BASELINE.yaml:343-354`（第四起）、`:367-373`（measurement_artifact_4）、
  `docs/adr/0021-repair-zero-measurement-artifact.md:14-16`、
  `docs/adr/0029-measurement-artifact-cross-file-and-packaged-import.md:20-38`
- **结论：部分支持**

| 起 | 伪影 | 零 LLM 复现证据 | 判定 |
|----|------|----------------|------|
| ① | patch 围栏残留 | ADR-0021「10 主批次 274/274」——我独立计数 = 4+4+15+54+46+45+27+26+27+26 = **274/274** ✓；扩到 16 个入库批次 = **476/476 (100%)** | **支持（且更强）** |
| ② | QuixBugs 包结构 import | 配 `AITESTER_QUIXBUGS_DATA` 后重放同批工件得 37/41 ✓；不配则全部 fail-closed None | **支持** |
| ③ | 跨文件 `module_a/b/c` 未物化 | matrix §2 的 25 行「0→11」需关闭 R27 分支才能单独复现（未做）；但**总量可复现**：v2 总 correct=115/266，与 ADR-0021 的 v1「103/266」差 **+12** = matrix 声称的 11+1 ✓ | **部分支持** |
| ④ | M1 判分树 import 布局 | **无入库证据** | **无法核验** |

- **第四起细节（重点）**：「9/9 缺陷程序在 buggy 与 fixed 两侧均 rc=2」与「F2P 0/7→6/7」在
  仓库里只能找到三处痕迹，**都不是可复算证据**：
  1. `tests/test_m1_packaged_tests.py:108-118` 的 **docstring** 复述该结论（测试本身只锁
     `TestDualLayout` 5 例的布局机制，不测 12 任务 rc 计数）；
  2. `experiments/results/e6_a1_batches/e4_quixbugs_FIXED_harness/diagnostic_12task_prerepair.json`
     —— 12 行，只有 `detection_rate=0.0`，**没有 `rc_buggy`/`rc_fixed` 列**；
  3. 修复前后 detection 对照（`e4_quixbugs_aitester` 0/41 → FIXED 17/37）。
- **强旁证（可核验）**：修复前批 `e4_quixbugs_aitester` 里 **red_seen 40/41 而 detection 0/41**
  ——与"判分树构造性恒 0（红测试存在却三段判定第 2 段永不通过）"的机制完全一致。
  结论：机制**可信且有间接证据**，但"9/9 双 rc=2"这一具体计数**不可对外引用为已复现数字**。

### 声明 8｜测试与静态检查

- **声明原文**：`BASELINE.yaml tests.total_passed=5015 / mypy 119 源文件 0 错误 / ruff 0.16.3`
- **出处**：`BASELINE.yaml:16-20`、`:78-82`
- **核验方式**：`.venv/bin/python -m pytest tests/ --collect-only -q -p no:cacheprovider`；
  `.venv/bin/python -m mypy src/ config.py --cache-dir=/tmp/t4/mypy_cache`；
  `.venv/bin/ruff --version`。**未跑全量**（任务限制 + 另一位同学在跑）
- **结论：部分支持**

| 项 | 声明 | 实测 | 判定 |
|----|------|------|------|
| ruff | 0.16.3 | `ruff 0.16.3`（venv），`requirements.lock:109` = 0.16.3 | ✓ |
| mypy | 119 文件 0 错误 | `Success: no issues found in **120** source files` | 0 错误 ✓ / 文件数 ✗ |
| pytest | 5015 passed | `**5178 tests collected** in 1.87s`（collect-only，未执行） | ✗ |

- **解释与风险**：5015 是 **2026-10-09 特定工作树**的数字；当前 HEAD 是 2026-10-10 的文档清理批，
  `tests/` 下 **57 个 `.py` 文件 mtime 晚于 10-09**。因此 BASELINE 的 5015 / 119 是**过期快照**，
  不能作为当前树对外数字。建议改为「基线条目附带日期+sha」或刷新。
- **BASELINE 内部自相矛盾**：同一天登记了三个不同的测试数——`:17` `total_passed: 5015`、
  `:522` `full_suite: "5107 passed / 3 skipped / 0 failed"`、以及实测 collected 5178。
  对外引用任一个都必须注明日期与口径（passed vs collected）。

### 声明 9｜false_fix / plausible / CPR / 弃权 / IDR

- **声明原文**：`false_fix 87.2%、patch_plausible 46.8%、CPR 84.3%、弃权精确率 86.0%、IDR 27.78%`
- **出处**：`BASELINE.yaml:170-178`；`corrected_report_v2.md` §2–3；
  `repair_ceiling_report.md:19`；`docs/adr/0027-corrected-caliber-re-estimation.md:26-31`
- **核验方式**：读 `corrected_report_v2.md` 汇总值 + 从三批次 JSON 直接数
  `patch_plausible==1` / `detection_first_status` 桶（附录 A.6）
- **结论：部分支持**

| 指标 | 声明 | 工件实际值 | 判定 |
|------|------|-----------|------|
| false_fix | 87.2% | `0.8716`（380/436，v1 ADR-0027 与 v2 一致） | ✓ |
| patch_plausible | 46.8% | **72/154 = 46.75%**（我直接数得 72；154 = red_not_repaired 97 + red_then_green 57） | ✓ |
| CPR | 84.3% | **`0.8451`（60/71，v2 现值）**；84.29%（59/70）是 v1 | ⚠ 数值需限定版本 |
| 弃权精确率 | 86.0% | `0.8597` | ✓ |
| IDR | 27.78% | **`0.3485`（v2）/ 34.33%（ADR-0027 修正）** | ✗ 已被取代 |

- **口径歧义**：
  1. **false_fix 87.2% 的分母不是 R-P0-2**：`380/436` 是 `main_batch` **全部 10 批、669 行**
     的 passed 可测行（跨 10-01/10-06/10-07 三个代际）。BASELINE 把它写在 R-P0-2 段落里，
     容易被读成生死实验口径。
  2. **plausible 46.8% 的分母是 154**（"进入修复循环的行"），不是 261 也不是 145；
     且其语义是 **patch 写盘成功**（`repair_history[-1].patch_applied`），**不是"补丁合理"**——
     见 §4.2。
  3. **IDR 27.78% 是伪影前值**（批次 II，40/144）。修正后为 34.33%（ADR-0027）/
     **34.85%**（`corrected_report_v2.md` §3 `0.3485`）。README「最近改动」仍在引 27.78%，
     属于历史条目，但**不得作为当前口径对外**。

### 声明 10｜统计结论

- **出处**：`BASELINE.yaml:214-223`（统计）、`:224-237`（stats）、`:524-540`（RT1）；
  `docs/preregistration.md:350`（A1 聚类）
- **核验方式**：读 E6/A1 两批 JSON 手工构造配对 2×2；用项目自带
  `experiments/statistical_analysis.py`（`--cluster-by-template`）与
  `template_cluster_sensitivity` 原语复算（附录 A.7）
- **结论：数值部分全部可复现；但 A1 的因果结论已作废、RT1 的开关生效不可核验**

| 子声明 | 复现结果 | 判定 |
|--------|---------|------|
| A1 8/87 vs 8/87、discordant 1:1、χ²=0.500、精确二项 p=1.0000 | ✓ 逐位 | 数值 ✓ |
| A1 ROPE：δ=0.0000、CI[−0.0451,+0.0445]、P(\|δ\|≤ROPE)=0.9691 | （未独立重算贝叶斯，依赖 `bayesian_paired.py`；CI 与"2 个不一致对"量级自洽） | 未独立复现 |
| A1 聚类 k=29、ICC=0.671、DEFF=4.356、n_eff=39.9/174、符号 1:1 p=1.0 | ✓ 用 `template_cluster_sensitivity` 逐位复现 | ✓ |
| **E6** aitester 8/87、df 30/87、plain_llm 0/87、2×2 = 2:24、χ²=**16.962** | ✓ 逐位 | ✓ |
| E6 聚类 χ²_adj=**6.6006**、符号检验 1:12 p=**0.0034**、k=29 | ✓ 逐位 | ✓ |
| E6 「ICC=0.671/DEFF=4.356」 | ✗ 那是 **A1** 的数；E6 的是 **ICC=0.364/DEFF=2.820**，符号检验 p=0.0034 仍显著 | ⚠ 归属混淆 |
| aitester vs plain_llm +8.8pp 校正后不显著（符号 p=0.0625） | ✓ 复现 p=0.0625 | ✓ |
| RT1：df 27/87 vs RT1 10/87、配对 17:0、χ²=15.059、p=0.0001；RT1 vs plain_llm 1 个不一致对 p=1.0 | ✓ 逐位 | 数值 ✓ |

- **A1 结论已作废**：`a1_strip_seed42` 与 `e6_control_seed42` 的 `env_snapshot` **都没有**
  `PLAN_STRIP_EXPECTED_OUTPUT_ENABLE` 键（37 键快照）；两批 detection 逐点相同（8/87 vs 8/87）。
  BASELINE 自己在 `:389-402` 承认为「假阴性：消融未生效」，但 `:216-219` 的 `a1_verdict`
  仍写「实际等价（95% CI 完全落在 ROPE ±5pp 内）」。**两者不能同时对外**——「实际等价」
  只能改写为「干预未生效，无可判定」。
- **RT1 的开关生效不可核验（与 A1 同类风险）**：`DETECTION_FIRST_SECTION_ENABLE`
  **不在** `_env_snapshot_keys`（`experiments/run_benchmark.py:2712` 起 38 项键表），
  `rt1.log` 无任何强化段/开关行，工件行 schema 也无该键；其**默认值是 `true`**
  （`src/graph/nodes.py:490-495`）。更关键：**RT1 批与 E6-p1 批的 38 个 env 键逐字节相同**
  （唯一差异是 `AITESTER_LLM_CACHE`/`AITESTER_CACHE_NAMESPACE`，属另外两批），
  两批却给出 10/87 vs 27/87。→ 差异只能归因于**一个未登记的开关**（推断），
  不能从工件直接验证。这与 D3 是同一缺陷类，但 BASELINE 只为 A1/`OVER_RED_SECTION_ENABLE`
  登记了该项，**未为 RT1 登记**。

---

## 2. 声明 → 可对外引用性总表

| # | 声明数字 | 可对外引用性 | 附加口径（必须同时写出） | 风险 |
|---|---------|-------------|------------------------|------|
| 1 | df 44.8% / aitester 15.8% / plain_llm 1.5% | **能** | 3 种子合并；分母 261/240/261 各写；δ 定义=Dirichlet 后验均值；git_dirty=true | 三臂分母不同源；−28pp 需附双界敏感性 |
| 2 | repair 39.31%（57/145）、54.72%（58/106） | **需限定** | "零 LLM 存量重放"（工件 repair_rate 仍 0.0）；v2 含 R27；E1/E2 标注 n 非独立 | 不写"重放"即与 JSON 不符；E1/E2 n 腰斩 |
| 3 | QuixBugs 17/37、31/37、p=0.0005 | **能** | 41 缺陷程序口径；13 None=9 测试驱动+4 不终止 | — |
| 3' | QuixBugs repair 92.5%（37/40） | **需限定** | 或改用同族 37/41=90.2% | 与 ADR-0029/口径矩阵 ④ 的 90.2% 不同源 |
| 4 | spec_compile 0.472–0.517 | **需限定** | 10-09 批（S6 后）；n=50/87 | 与 expr 0.72–0.74 **非同一批** |
| 4' | spec_expr 0.72–0.74 | **需限定** | 10-07 E1/E2 批，n=45/51 | 与上一行并列会被误读 |
| 4'' | oracle 注入 2–3/87、20/50 | **不能** | — | 无入库工件/日志，schema 无该键 |
| 5 | coverage 84.0–93.6 vs 86.0–97.2；mutation 0.818–0.976 vs 0.986–0.997 | **能** | 批次均值区间；排除 n=5 冒烟批；含 n=50 批；mutation n=77–81 | BASELINE 注记"10 批 n=87"错误 |
| 6 | \$/task 0.0259 / 0.0034 / 0.0045 | **能**（df 需注明下界） | 价目表 2026-10-06 峰时全额；分母 261；D2 使 df 低估 | "aitester 贵 5.8×"被高估 |
| 6' | QuixBugs 16038 vs 1905（8.4×） | **需限定** | 41 缺陷程序行口径（全 50 行 = 6.6×） | 分母未披露会复算失败 |
| 7 | 围栏残留 274/274（476/476） | **能** | 限定"透出层 patch 字段"；测量层已修但工件未回灌 | 下游消费者直接读 patch 会 100% 失败 |
| 7' | 9/9 双 rc=2、F2P 0/7→6/7 | **不能** | — | 仅 docstring + 无 rc 列的诊断批 |
| 8 | ruff 0.16.3 | **能** | venv 与 lock 一致 | — |
| 8' | mypy 119 文件 0 错误 | **需限定** | 0 错误 ✓，但当前树 **120** 文件 | 数字过期 |
| 8'' | tests 5015 | **不能**（作当前数字） | 须标日期+sha；当前 collect-only=5178；同文件另有 5107+3 | BASELINE 内部三值不一致 |
| 9 | false_fix 87.2% | **需限定** | 10 批 669 行、passed 可测 436（非 R-P0-2） | 被读成 R-P0-2 口径 |
| 9' | plausible 46.8% | **需限定** | 分母 154（进入修复循环）；语义=写盘成功 | 语义易被读成"补丁合理"；与 repair 分子不同源 |
| 9'' | CPR 84.3% | **需限定** | 现值 v2=84.5%（60/71）；84.3% 为 v1 | 版本漂移 |
| 9''' | 弃权精确率 86.0% | **能** | v2 0.8597 | — |
| 9'''' | IDR 27.78% | **不能** | 现值为 34.33%（v1 修正）/34.85%（v2） | 伪影前值 |
| 10 | A1「实际等价」 | **不能** | 只能写"开关未生效，无可判定" | 与 BASELINE 自身勘误矛盾 |
| 10' | E6 δ=−25.3pp 校正后显著 | **能** | 后验均值 −0.2418；χ²_adj=6.60（E6 的 ICC=0.364/DEFF=2.820） | ICC 归属混淆（0.671 是 A1 的） |
| 10'' | RT1 +19.5pp 归因提示协议 | **需限定** | 开关未入快照；跨批配对（RT1 批 vs E6-p1 批）；RT1 臂在工件里名为 `plain_llm_df` | 与 A1 同类的"开关未生效"风险 |

---

## 3. TOP 5 口径风险

**R1（最高）｜"已修"只修了测量层，透出层 100% 未回灌。**
16 个入库批次里 **476/476（100%）** 带补丁行的 `patch` 字段以 `python\n` / ` ``` ` 围栏残留
开头（10 个主批次恰为 ADR-0021 声称的 274/274）。ADR-0021 的修复落在
`_m1_metrics.normalize_patch_text`，工件的 `patch` 从未回填。后果：
`patch_plausible`/`patch_precision`/CPR/IDR/`repair_ceiling_report` 漏斗/E7 抽样框
（`repair_sample_selection.py:57-62`）与修正 repair 的**分子不同源**。任何按下游口径
重算 plausibility 的人会得到"100% 补丁非法"。**对外必须声明：`patch` 字段是原始未清理值。**

**R2｜`patch_plausible` 语义 ≠ 名字，且系统性低估 correct。**
`_patch_plausible`（`run_benchmark.py:601-617`）= 有补丁文本 ∧ `repair_history[-1].patch_applied`。
在 `skip_debugger_repair_invalid` 早退路径上（`_recent_repairs_invalid` 要求最近 2 次
`patch_applied=False`，`workflow.py`），末条记录为 False → plausible=0，
而该补丁经 normalize 后**可以**通过 gold 裁决。实测：
- QuixBugs FIXED：**13 行** `plausible=0 且 correct=1`（全部 `stop_reason=skip_debugger_repair_invalid`、
  `iterations=2`）；该批 `plausible=26 < correct=37` → `patch_precision` 分母（26）
  小于分子（37），**指标自相矛盾**。
- RP02 合成：`plausible=72`（46.8%）而重放 correct=57，且 145/145 带补丁行都可重放。
- ADR-0027 已承认同类现象 33 行（"33 个 correct 行 plausible=0"）但**未展开**。
量化影响（见 §4.2）：判 plausible 的口径一改，QuixBugs 从 26→41、precision 从
"37/26（>1）"→37/41=90.2%；RP02 从 72/154=46.8% → 145/154=94.2%，
于是 plausible 层**退化为"有补丁"**、precision ≡ repair_rate，"上限漏斗"失去独立信息。

**R3｜分母不同源/不同批，且多处未披露。**
(a) detection 240 vs 261；(b) QuixBugs token 41 vs detection 37 vs batch 50；
(c) false_fix/CPR/弃权是 10 批 669 行而非 R-P0-2；(d) plausible 分母 154；
(e) spec_compile 0.47–0.52 与 expr 0.72–0.74 分属 10-09 与 10-07 两代；
(f) coverage 区间跨 8 批（含 n=50 与 n=87）却标注"10 批次 n=87/批"。
任何跨行引用都会踩到。

**R4｜观测独立性被高估：缓存复用 + 同种子重跑 + 同模板聚类。**
(a) E1/E2「四批次 106 行」= 2 种子 × 2 次重跑，同种子两批复用**同一 cache namespace**
（`seed42`/`seed44`）而 git SHA 已变（`d3c3cc4`→`1a5a5a7`）→ 独立 n 只有 53；
(b) E6/A1 用 namespace `seed42` 承接 10-06 的 R-P0-2 缓存，E6 两臂 87/87 行零 token 记账；
(c) 同模板跨种子相关：主批次 AC4 校正 DEFF=3.42–5.53，E6 的 aitester-vs-df DEFF=2.82、
A1 的 DEFF=4.356 → 逐对 McNemar 的 n 应打折到 n_eff（A1 仅 39.9/174）。
(d) 三批次 `git_dirty=true`，代码态不可由 sha 复现。

**R5｜开关生效性证据缺失（同类缺陷第三次出现，且未全部登记）。**
`DETECTION_FIRST_SECTION_ENABLE`（RT1 的定义开关，默认 **true**）不在
`_env_snapshot_keys`；RT1 批与 E6-p1 批 env 快照**逐字节相同**，两批结果却差 17pp。
`PLAN_STRIP_EXPECTED_OUTPUT_ENABLE`（A1）同样缺失 → A1 已定案为"假阴性"。
`OVER_RED_SECTION_ENABLE` 已被登记为 D3。**RT1 至今未登记**，却已被写进
BASELINE/prereg 作为"红队假说证否"的证据。建议：把「新开关必须出现在
`_env_snapshot_keys`」做成门禁（BASELINE 自己已建议但"未实施"），并对 RT1 补登记。

---

## 4. Lead 三项交叉核验的独立结论

### 4.1 项 1｜`repair_history` 在 skip 早退路径上导致 `_patch_plausible` 低估 — **支持（机制推断 + 效应实测）**

- **机制（代码）**：`workflow.py::_recent_repairs_invalid` → 最近 2 条
  `repair_history` 的 `patch_applied` 均为 False 时返回 `StopReason.REPAIR_INVALID`
  → 路由 `done`，**不再进入 Debugger/PatchApplier**；`run_benchmark.py:601-617::_patch_plausible`
  取 `repair_history[-1]["patch_applied"]` → 记 0。
  `repair_history` 未透出到结果行（行 schema 无该键），故**机制无法逐行直接读证**，
  只能由 (stop_reason, iterations, plausible, correct) 交叉表 + 代码路径推断。
- **效应（实测，可复现）**：QuixBugs FIXED 的交叉表逐格复现 Lead 的数字——
  `(test_passed,1,1,26?)`…完整表：

  | stop_reason | plausible | correct | n |
  |---|---|---|---|
  | test_passed | 1 | 1 | 13 |
  | **skip_debugger_repair_invalid** | **0** | **1** | **13** |
  | skip_debugger_repair_invalid | 0 | 0 | 11 |
  | max_iterations | 1 | 1 | 11 |
  | max_iterations | 1 | 0 | 2 |

  13 行"矛盾行"全部 `iterations=2`，与"连续 2 次 patch_applied=False 触发早退"一致。
- 同一现象在合成批亦有：ADR-0027 自认 33 个 correct 行 plausible=0。

### 4.2 项 2｜围栏残留比例与量化影响 — **支持（并给出量化）**

- **残留比例**：
  - QuixBugs FIXED aitester：**50/50 = 100%** 带补丁行以字面 `python\n` 开头
    （0 行以 ` ``` ` 开头）；13 个"矛盾行"**13/13** 全部以 `python\n` 开头 ✓（与 Lead 抽样一致）。
  - 10 个 synthetic 主批次：**274/274 = 100%**（= ADR-0021 声明，逐位吻合）。
  - 扩到 16 个入库批次（含 r4_batches/quixbugs 批）：**476/476 = 100%**。
  - 对照：`generated_test` 字段干净（ADR-0021 称 974/974），说明**仅 patch 通道受染**。
- **量化影响（若用 normalize 后的补丁判 plausible）**：

  | 批 | 记录 plausible | normalize 后 plausible | 记录的 correct/plausible | 修正后 |
  |----|---------------|----------------------|------------------------|--------|
  | QuixBugs FIXED | 26/50 | **41/50**（40 有 gold + 1 行 node 可补判；9 测试驱动仍无 gold） | 37/26 = **1.42（>1，矛盾）** | **37/41 = 90.2%** |
  | RP02 合成 | 72/154 = 46.8% | **145/154 = 94.2%**（145 带补丁行全部可重放） | 0（伪影口径） | 57/145 = 39.3%（= repair 率） |
  | E1/E2 | 14+11+14+11 = **50/106 = 47.2%** | **106/106 = 100%**（106 带补丁行全部可重放） | — | 58/106 = 54.7% |

  → 结论：**plausible 层在 normalize 口径下退化为"有补丁文本"，precision 恒等于 repair 率**，
  `repair_ceiling_report.md` 的"145 → 72（46.8%）→ correct"漏斗中间层**不是独立的合理性过滤**，
  引用该漏斗时必须说明 72 的语义是"写盘成功"。
- **下游受影响清单**（分母与 repair 分子不同源）：
  `repair_ceiling_analysis.py`（以 `patch_plausible=1` 为闸口）、
  `patch_precision`（本批只有 26 行非空而 correct=37）、
  `cpr_idr_report.py:118`（跳过 `patch_plausible!=1`）、
  `repair_sample_selection.py:57-62`（E7 抽样框）、
  `corrected_metrics.py`（CPR 分母 = plausible∩correct，ADR-0027 已承认与总 correct 不同）。

### 4.3 项 3｜`fl_at_k` 与 `oracle_type` — **`fl_at_k` 全零的观察被否证**

- **`fl_at_k` 并非全零**（`e4_quixbugs_FIXED_harness/aitester.json`，n=50）：

  | fl_at_k 取值 | 行数 |
  |---|---|
  | `null` | 13 |
  | `{fl_at_1:0.0, fl_at_3:0.0, fl_at_5:0.0}` | 16 |
  | `{1.0,1.0,1.0}` | **12** |
  | `{0.0,1.0,1.0}` | 5 |
  | `{0.0,0.0,1.0}` | 4 |

  修复前批（`e4_quixbugs_aitester`）同样有 12 行 `fl_at_1=1.0`。
  → **Lead 的"全为 0"在本仓工件中不成立**；怀疑是看了 `plain_llm_df` 臂
  （该臂 50/50 全为 `null`，不是 `0.0`——`null` 与 `0.0` 混同正是本项目反复踩的坑）。
- **localization 分母应为 37 而非 50**：`localization_hit_function` 非空 37 行、命中 **29**；
  `localization_hit_function_at_3` 命中 **30/37 = 81.1%**；`localization_mrr` 均值 **0.7973** ✓
  （与 Lead 的 0.797 一致）。写"29/50"会把 13 行 fail-closed None 计入分母。
- **`oracle_type` = `generated_test` 50/50 ✓**（四个 QuixBugs 工件全部如此，df 臂亦然）。
  但它**不能**用于核验"规约 oracle 注入 20/50"：注入量由 `state["spec_oracle_injected"]`
  （`src/graph/nodes.py:865`）记录，未透出到结果行；该批日志 0 条 `oracle 已注入`。
  **`a2_logic_chain_reach.injection_quixbugs = "20/50"` 与结果行/日志完全无对齐口径可言
  ——建议标注为"仅审查报告口径、无入库证据"，或补做零 LLM 离线可达性复算后入工件。**

---

## 附录 A：复现命令与代码片段

所有脚本写 `/tmp/t4/`，仓库零写入。运行目录 = `/Users/wangchenyu/Workspace/AITester`。

### A.1 声明 1（三态计数 + 配对）
```python
BATCHES = {42:"experiments/results/main_batch/benchmark_synthetic_20261006_140906.json",
           43:".../benchmark_synthetic_20261006_151907.json",
           44:".../benchmark_synthetic_20261006_164357.json"}
for seed,p in BATCHES.items():
    d=json.load(open(p))
    for arm,a in d['results'].items():
        for row in a['details']:
            dr=row.get('detection_rate')          # None / 0.0 / 1.0 三态
```
21 行 None 的 M10 归因：`row['diagnosis']` 含 `"M10 LOGIC_SPEC_STRICT_ENABLE=true"` 且 `iterations==0`。
配对 2×2（aitester vs df，240 行）= n10 80 / n01 12 / both 26 / neither 122；
`chi2=(|80-12|-1)**2/92 = 48.793`；贝叶斯 δ `=(12-80)/(240+4) = -0.2787`。

### A.2 声明 2（独立重放）
```bash
.venv/bin/python -c "
from pathlib import Path; from experiments.repair_replay import replay_batch
for f in ['benchmark_synthetic_20261006_140906.json','..._151907.json','..._164357.json',
          'benchmark_synthetic_20261007_161053.json','..._170147.json','..._181638.json','..._185941.json']:
    print(replay_batch(Path('experiments/results/main_batch')/f,'aitester',timeout=30))"
# → correct 20/46/17/14/15/15/14  ⇒ 57/145 与 58/106
```

### A.3 声明 3（QuixBugs 逐行对照）
```bash
AITESTER_QUIXBUGS_DATA=$PWD/data/quixbugs .venv/bin/python -c "
import json; from experiments.repair_replay import replay_row
det=json.load(open('experiments/results/e6_a1_batches/e4_quixbugs_FIXED_harness/aitester.json'))['results']['aitester']['details']
for r in det: print(r['task_id'], r.get('repair_rate'), replay_row(r,timeout=45)['status'])"
# → 37×(1.0,correct), 9×(None,skipped_no_material), 3×(0.0,wrong_patch), 1×(None,wrong_patch)=quixbugs__node
```

### A.4 声明 5（批次均值区间）
```python
v=[r['coverage'] for r in det if r.get('coverage') is not None]; mean=sum(v)/len(v)
# aitester: 89.6/91.6/93.6/88.2/84.0/84.8/86.4/90.6/86.4/90.6 → [84.0, 93.6]
```

### A.5 声明 6（成本 + D2 污染面）
```python
cost=(sum_in*0.3+sum_out*1.2)/1e6; per_task=cost/261        # → 0.0259 / 0.0034 / 0.0045
zero = sum(1 for r in det if not (r.get('token_usage') or {}).get('total_tokens'))
# df 在 RP02 三批 = 8/13/14；E6 control 三臂 = 50/87/87、87/87、87/87
# QuixBugs: 41 非测试驱动行均值 = 16038 / 1905（全 50 行 = 15253 / 2309）
```

### A.6 声明 9（漏斗直数）
```python
c=collections.Counter(r.get('detection_first_status') for r in rows)   # 97/86/57/21
plausible=sum(1 for r in rows if r.get('patch_plausible')==1)          # 72
assert 97+57==154 and plausible/154==0.4675
```

### A.7 声明 10（聚类 + RT1）
```bash
.venv/bin/python experiments/statistical_analysis.py --results-dir experiments/results/main_batch \
  --cluster-by-template --batches benchmark_synthetic_20261006_140906.json,... \
  --sensitivity-output /tmp/t4/cluster.md          # k=31 / ICC=0.153-0.299 / χ²_adj 33.06/6.44/9.08
.venv/bin/python experiments/statistical_analysis.py --results-dir experiments/results/e6_a1_batches/e6_control_seed42 \
  --cluster-by-template --batches benchmark_synthetic_20261009_181758.json --sensitivity-output /tmp/t4/cluster_e6.md
# → k=29，aitester vs df χ²_adj=6.6006、符号 1:12 p=0.00341797 ✓
```
A1 的 ICC/DEFF 需用 `template_cluster_sensitivity(rows_a1, rows_ctrl, ...)` 手工拼（两批不同目录），
复现 k=29 / ICC=0.671 / DEFF=4.356 / n_eff=39.9 / 符号 1:1 p=1.0。

### A.8 声明 8（测试与静态检查）
```bash
.venv/bin/python -m pytest tests/ --collect-only -q -p no:cacheprovider --basetemp=/tmp/t4pytest_collect
# → 5178 tests collected in 1.87s
.venv/bin/python -m mypy src/ config.py --cache-dir=/tmp/t4/mypy_cache
# → Success: no issues found in 120 source files
.venv/bin/ruff --version           # ruff 0.16.3
```

## 附录 B：本次审查的边界（未做/不能做）

1. **未跑全量 pytest**（任务限制 + 并发纪律），只做 `--collect-only`；因此
   "5015 passed" 无法用本次审查判定真伪，只能判定**当前树的收集数是 5178**。
2. **未重算贝叶斯 CI/P(ROPE)**：`bayesian_paired.py` 的后验 CI（A1 的
   [−0.0451,+0.0445]、E6 的 [−0.3447,−0.1432]）未独立重算，仅核对了 2×2 计数
   与"不一致对数量↔CI 宽度"的自洽性。RT1 的 δ=+0.1868 同理。
3. **无法复现伪影 ④ 的 9/9 与 0/7→6/7**：需要"修复前判分树"行为，
   而当前源码只保留修复后实现；不修改 `src/` 的前提下无法重放（未做 git 历史版
   本抽取，成本收益不划算）。
4. **未核验 20/50 注入数**：无 artifact 字段、无日志、无脚本。
5. `experiments/corrected_metrics.py` 的全量重放（669 行 × pytest）**未整体执行**；
   我按批次粒度独立重放了其中 251+50 行（RP02+E1/E2+QuixBugs），
   与报告分子逐位一致，故认定报告可信，但 `false_fix/CPR/弃权` 三个跨代际汇总值
   我**只核对了报告自述的数字与分桶算术**（380/436、60/71、0.8597），未逐行重算。
