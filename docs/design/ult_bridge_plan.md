# ULT / UnLeakedTestbench 指标桥接方案（P2-10 / 任务 task-8）

> **性质**：设计文档，**不含实现代码**。定义可对齐性结论、数据与许可、工程接入、分层执行、报告协议与风险。
>
> **锚点时间**：2026-10-10T17:00+08:00（Asia/Shanghai），`HEAD=d9e51df` + 工作树未提交改动。
> 行号为**快照**；稳定锚点是符号名与键名。写入范围仅本文件（+ 同任务另两份产物）。

---

## 0. 一页结论

1. **本项目的 `detection_rate` 与 ULT 的 accuracy / mutation score 不同构、不可换算**；
   唯一正当做法是**在 ULT 协议上重跑本项目**，并用"逐指标对应表"（§3）显式登记映射与差异。
2. **ULT 数据许可未澄清**：上游 The Stack v2 为 `license: other` + gated 且附四条使用条款；
   ULT 本体在 HF 的副本**未声明任何 license**；官方仓库在本环境不可达（NOT VERIFIED）。
   → **禁止把 ULT 数据打包进本仓**；以"用户本地拉取 + 显式接受条款 + 逐文件许可元数据"方式接入（§4.1）。
3. 执行路径：**200 任务定标 → 门禁 → 全量 3,909 + PLT 双轨**；成本**先测后推**（§5）。
4. 预期：本项目在 ULT 上**显著低于 41.32%**（复杂度鸿沟，QuixBugs 是玩具程序），
   方案把它写成**预期而非意外**，并给出应对（§7 R1）。

---

## 1. ULT 事实基线（外部数据，已核验范围已标注）

**来源**：Huang, Zhang, Harman, Zhang, Du, Ng. *Benchmarking LLMs for Unit Test Generation from Real-World Functions.*
**ACM TOSEM**，Article 3805043，DOI `10.1145/3805043`（2026-02-25 接受，2026-03-28 Online AM；2026-10-16 经 ACM DL 一手页面 `https://dl.acm.org/doi/10.1145/3805043` 核验归属与作者名单）；预印本 arXiv:2508.00408（2025-08-01，CC BY 4.0）。
核验途径：`https://discovery.ucl.ac.uk/id/eprint/10223971/`（作者接受稿落地页 + 摘要）、`https://arxiv.org/abs/2508.00408`（摘要）与 ACM DL（归属/日期）。三处摘要数字**逐位一致**。

| 项 | 值 | 可信度 |
|---|---|---|
| 任务规模 | **3,909** 个函数级去泄漏 Python 任务；cyclomatic ≥10，**均值 14.87** | A（venue）/ B（数字来自摘要） |
| 配对基准 | **PLT（PreLeakedTestbench）**：带泄漏测试的配对集 | 同上 |
| 协议 | **K-query 迭代**（第 i 轮给 FUT + 全部历史测试，要求产出**不同**的测试）；**greedy, temperature 0.0**；每轮 **≤1,024 新 token** | 同上 |
| 变异评测 | **cosmic-ray** 全变异体 + **120s 超时**；击杀定义 = **原码通过 ∧ 变异码失败** | 同上 |
| 12 模型均值（ULT） | accuracy **41.32%** / stmt **45.10%** / branch **30.22%** / mutation **40.21%** | 同上 |
| 12 模型均值（PLT，含泄漏） | **47.07% / 55.13% / 40.07% / 50.80%** | 同上 |
| TestEval（对照基准） | **91.79% / 92.18% / 82.04% / 49.69%** | 同上 |
| 最佳单模型 | **Pass@1 仅 17.83%** | 同上 |
| 泄漏效应 | **branch 膨胀最大（+9.85pp）**；mutation 亦不免疫（PLT 50.80 > TestEval 49.69） | 同上 |
| 相关性 | ULT 上"代码能力 vs 测试生成 Pass@1"相关系数 **0.79 (p=0.002)**；TestEval 0.56 (p=0.059)、PLT 0.52 (p=0.080) | 同上 |

> **未核实**：论文正文表格（逐模型明细、K 的具体取值、超时口径细节、ULT 精选流程的每阶段通过数）
> 未逐行核验——UCL 的 PDF 在本环境不可解析（`application/pdf` 不支持）。落地页与 arXiv 摘要已交叉一致，
> 但**任何正文级明细在引用前必须补核**。

---

## 2. 目标

在**不改动本项目既有指标口径**的前提下，建立一个可复算的 ULT 桥接层，使 AITester 能：
(a) 在 ULT 协议上产出四指标（accuracy / stmt / branch / mutation）；
(b) 与 ULT 12 模型基线做**配对比较**（不是均值对均值）；
(c) 用 ULT/PLT 双轨量化**泄漏效应对本项目的污染程度**。

---

## 3. 可对齐性分析（核心；结论：不可换算）

### 3.1 逐指标对应表

| ULT 指标 | 本项目最接近的量 | 同构？ | 差异与所需映射 |
|---|---|---|---|
| **accuracy**（生成测试在 FUT 上有效/通过） | `detection_rate` 的**第二段**（gold 修复代码上 `rc == 0`，`experiments/_m1_metrics.py:473-539`） | **否** | `detection_rate` 要求**两段同时成立**：buggy 侧 `rc != 0`（检出缺陷）∧ fixed 侧 `rc == 0` ∧ 两侧无收集错误。ULT **没有 buggy 版本**（被测函数就是正确实现）→ 缺"buggy 侧红"这一段。需要新谓词 `green_on_fut`（等价于 detection_rate 的第二段 + 收集错误防线）。**2026-10-12 M1 归一化批次**：`dataset_ult.py` 已把官方裸断言片段（`test_list`）包装为 `from <mod> import <fn>` + `test_<i>` pytest 函数并写回 `metadata.test_cases` / `metadata.fixed`（=被测函数全文，无缺陷基线），M1 三段判定对 ULT 任务由 None 变为可判分（恒 0.0"未检出"基线，对应本节的 `green_on_fut` 辅助口径）。mutation score 仍为主指标（见 `metadata.mutation_primary_metric`）。 |
| **statement coverage** | `results[arm].avg_coverage`（`experiments/run_benchmark.py:2642,2676`；执行器 `parse_coverage` 解析，`src/agents/executor.py:259`） | **待确认** | 本项目的 coverage 是执行器解析出的单一覆盖率数值；**分支覆盖未单列**。ULT 报 stmt 与 branch 两个量 → 必须新增 branch 通道并对齐"被测单元"边界（ULT 是函数级 FUT） |
| **branch coverage** | 无直接通道 | **否** | 需新增 `coverage --branch` 类采集，并核对与 ULT 的 branch 定义（函数级、去泄漏任务）一致 |
| **mutation score** | `experiments/mutation_detection.py` 的 `mutation_detection_rate`：**对 gold 修复代码**做变异，要求"原码全绿 ∧ 变异体变红 ∧ 非收集错误" | **结构同构，实现不同** | 击杀定义与 ULT 一致（原码过 ∧ 变异码失败）。**但变异体来源不同**：本项目用自研 `MutationGenerator` + 采样 `n_mutants`（seed 可复现）；ULT 用 **cosmic-ray 全变异体 + 120s 超时** → **数值不可直接比**，必须换 cosmic-ray 后端 |
| （本项目 `mutation_testing.compute_mutation_score`） | 对**缺陷代码**变异（生成器视角故障覆盖） | **否** | 与 ULT 的 mutation score **不是**同一件事，禁止混用（两者区别见 `experiments/mutation_detection.py:1-20` 模块 docstring） |
| **Pass@1**（最佳单模型 17.83%） | 本项目 `passed` / `success_rate` | **否** | ULT 的 Pass@1 是"测试生成任务"的成功定义；本项目 `passed` 是"被测代码通过自生成测试"。分子分母均不同 |

### 3.2 结论（必须写进任何对外材料）

1. **不可换算**：不存在一个系数能把本项目的 `detection_rate` 变成 ULT accuracy，反之亦然。
   `detection_rate` 是**故障检出**指标（需要缺陷存在），ULT accuracy 是**测试有效性**指标（无缺陷）。
2. **只能同协议重跑**：把本项目当作一个"被测系统"放进 ULT 的 K-query 协议，
   用 ULT 的判分口径产出四指标，再与 12 模型基线比。
3. **口径纪律**：任何把 `detection_rate` 与 ULT accuracy 并列陈述的写法，
   等同 `docs/design/repair_caliber_matrix.md:50-57` 所禁止的"跨口径混用"；
   新增的 ULT 数字必须在 `repair_caliber_matrix.md:11` 的口径矩阵**新增行**。

---

## 4. 工程方案

### 4.1 数据接入与**许可核实结果**（逐条，含来源与未核实项）

| 层 | 事实 | 来源（本次实测） | 含义 |
|---|---|---|---|
| 上游 The Stack v2 | HF 数据集元数据：`license: other`、**`gated: auto`**；card 含 **Terms of Use 四条**：①批量下载需与 SoftwareHeritage/INRIA 达成协议；②用于模型训练须遵守 SWH 的 LLM 训练原则；③须遵守原始文件许可（含署名义务）；④须随官方删除请求更新版本 | `https://hf-mirror.com/api/datasets/bigcode/the-stack-v2`（HF 官方域名 `huggingface.co` 在本环境被解析为非公网 IP，不可达；镜像 API 返回同一 card 数据） | ULT 由 The Stack v2 派生 → **再分发受上游与逐文件许可双重约束** |
| ULT 数据集本体 | HF `DONG19/Unleakedtestbench`：`private:false`、`gated:false`、**`tags` 仅 `["region:us"]` → 未声明 license**；仓库仅 4 个文件（`.gitattributes`、`datasets/ULTv3.jsonl`、`datasets/PLTv3.jsonl`、`pool.tar.zst`）→ **无 README / 无 dataset card**；创建 2026-05-29，约 304 MB | `https://hf-mirror.com/api/datasets/DONG19/Unleakedtestbench`（镜像 API） | **无明示许可 = 不得默认再分发**（HF 副本口径）；**但 2026-10-12 批次实测官方仓库为 MIT 许可，数据改经官方仓库 git clone 获取（MIT 覆盖），HF 无许可副本口径不再适用** |
| 官方仓库 | `github.com/huangd1999/UnLeakedTestBench` —— **NOT VERIFIED**（2026-10-10 锚定时）：本环境 `github.com` 与 `raw.githubusercontent.com` 均解析为非公网 IP（`web_fetch` 拒绝），`cdn.jsdelivr.net` 跳转到 `raw.githubusercontent.com` 亦不可达。尝试过的路径：github.com 仓库页、raw README、jsdelivr 镜像。**⚠️ 2026-10-12 批次更新：官方仓库已在本环境成功 `git clone`（数据已落盘 `~/.cache/aitester/ult_repo/`），"官方仓库不可达"前提不再成立；官方仓库 `LICENSE` 为 **MIT**（本批实测核实）——"许可未知"结论更正为"已核实 MIT"。数据文件格式勘误：官方 `datasets/ULT.jsonl`（3909 任务）/ `ULT_Lite.jsonl`（200 任务子集）/ `PLT.jsonl`（18310 任务）文件名虽为 `.jsonl`，**实际为 JSON 数组（非逐行 JSONL）**；官方 `tests` 字段全量非空（每任务 5 条官方测试函数），"官方不发布 gold tests" 为误读。详见 `PHASE1_PRECHECK_2026-10-12.md` §2.2 与 `dataset_ult.py` 勘误 docstring。** | — | 仓库声明的许可**未知**；需人工在可联网环境确认 |
| 论文可复现声明 | UCL 落地页："We also make ULT and evaluation results publicly available"；arXiv 摘要同 | UCL Discovery 落地页 | 公共可得，但**公共可得 ≠ 可再分发** |

**合规结论与动作（强制）**：
1. **不得**把 ULT/PLT 数据或其派生文件提交进本仓（`data/`、`experiments/` 均不例外）；
2. 接入方式：**用户本地拉取脚本**（`scripts/fetch_ult.py`，设计建议）+ 首次运行时的**显式条款接受**
   （展示 §4.1 四条 + ULT 许可"未声明"状态，要求用户确认）；
3. **保留逐文件许可元数据**：The Stack v2 的 schema 提供 `detected_licenses` / `license_type`（permissive vs non-permissive）
   → 落盘时保留，用于署名与"仅 permissive 子集"过滤；
4. 报告必须标注数据口径：**全量集**还是**permissive 子集**；子集口径与 12 模型基线**不可直接比**（另立口径行）；
5. 建议向 ULT 作者索取书面使用/引用条款，并把回复归档到 `docs/`（本任务不做，列为后续动作）。

### 4.2 复用本项目判分原语

| 复用对象 | 位置 | 用途 | 需要的改动 |
|---|---|---|---|
| `_compute_detection_rate` 的三段判定（含 `_looks_like_test_execution_error` 坏测试防线） | `experiments/_m1_metrics.py:473-539` | ULT **accuracy** 的判定器 | 去掉 buggy 段，得到 `green_on_fut`；保留收集错误/语法错误防线 |
| `_run_pytest_in_tmp` | `experiments/_m1_metrics.py:298` | 统一测试执行、超时、收集错误判据 | 超时与 ULT 口径对齐（120s 用于变异体；pytest 侧超时单列并记录） |
| `_prepare_packaged_test_tree` / `_prepare_cross_file_test_tree` | `experiments/_m1_metrics.py:125` / `:236` | 在隔离 tmp 树中物化 FUT + 测试（包结构/import 伪影经验） | 复用于宇宙射线会话准备 |
| `mutation_detection_rate` 的击杀口径 | `experiments/mutation_detection.py` | ULT **mutation score** 的判定器 | **把变异体来源换成 cosmic-ray**；保留"原码过 ∧ 变异失败 ∧ 非收集错误" |
| 配对统计通道 | `experiments/bayesian_paired.py`、`experiments/run_statistical_test.py` | 与 12 模型基线的配对比较 | 输入改为"按任务配对"的四指标 |
| 零 LLM 回放/口径通道 | `experiments/corrected_metrics.py`、`docs/design/repair_caliber_matrix.md` | 结果复算与口径登记 | 新增 ULT 口径行 |

**新模块（设计，不实现）**：`experiments/ult_adapter.py`（任务加载 + FUT 物化 + 逐文件许可元数据）、
`experiments/ult_protocol.py`（K-query 迭代：历史测试注入 + "必须不同"去重 + ≤1,024 新 token 约束 + greedy）、
`experiments/ult_metrics.py`（四指标 + `n_eff` + 超时率 + 失败分类）。

### 4.3 cosmic-ray 接入

- 现状：**已安装 8.7.0**（2026-10-13 D3 第一阶段，`experiments/ult_adapter.py`
  已实装 `init → exec → dump` 工作流并冒烟通过）；需**钉版本进 `requirements.lock`**
  （见 D3 报告 `（工件已清除）` §5）；
- 口径一致性：变异体集合必须与 ULT 论文一致（cosmic-ray 版本 + 算子配置）→ **报告里记录 cosmic-ray 版本与配置哈希**，否则 mutation score 不可比；
- 每个变异体 **120s 超时**（ULT 口径）；超时按**击杀（killed/detected）**计——与 ULT 官方 Cosmic-Ray 口径一致（见下）；
  - ✅ **2026-10-13 已裁定（超时语义）**：cosmic-ray 8.7.0 的 `run_tests`
    把 timeout 判为 **KILLED**（`TestOutcome.KILLED, "timeout"`）。一手核验：
    ① ULT 官方仓库（huangd1999/UnLeakedTestBench）定义
    `Mut@k = Σ Killed_Mutants / N`，明确用 **Cosmic-Ray**；② Cosmic-Ray 的
    `is_killed` 把 timeout 计入 killed；③ mutation-testing-elements 标准口径
    `detected = killed + timeout`（timeout 算检出——"若此变异体注入，CI 构建会
    因测试永不完成而发现它"）。故 **cosmic-ray 的 timeout=killed 符合 ULT 官方
    口径**；本条原"超时按存活计"系本项目保守口径，与 ULT 官方相反，已修正。
    D3 适配器沿用 `is_killed`（timeout 计入 killed）无需改动；但 `mutation_detection.py`
    （自研 AST 变异体的保守口径）保持"超时按存活计"，两者分述、不得混比。
  - ✅ **2026-10-13 已裁定（算子集 / 版本 / incompetent）**：
    ① **算子集 = 全变异体**——ULT 官方仓库 README 的 mutation 评测仅
    `pip install cosmic-ray pytest pytest-cov`、**未指定 operators 过滤**
    （Cosmic-Ray 默认全变异体）。故适配器"不设 operators 键 = 全变异体"与
    ULT 一致；`ult_adapter.py` 的 `ULT_MUTANT_OPERATORS`（9 类描述）是
    **描述性分类，非实际算子集**，`cosmic_ray_config_hash` 应改为哈希
    "全变异体事实 + cosmic-ray 版本"（而非 9 类常量）——待 W1 工程落实；
    ② **版本**——ULT 官方未钉 cosmic-ray 版本（默认安装），本项目为可复现
    钉 `8.7.0`，报告须披露"ULT 官方未钉版本、本项目钉 8.7.0 与默认一致"；
    ③ **incompetent 计击杀**——沿用 Cosmic-Ray 官方 `is_killed`
    （`test_outcome != survived`），与 ULT（用 Cosmic-Ray 默认）一致。
- 工程风险：cosmic-ray 需要可导入模块 + 会话初始化；本项目历史上有两类 import 伪影（跨文件未物化、包结构）
  → 复用 §4.2 的 tmp 树物化经验，先跑 smoke（阶段 0）。
- 基线漂移：本项目自研 `MutationGenerator` 的分数**保留**，作为"内部可比"的旧口径；cosmic-ray 分数是**新口径**，两者不得混述。
- ✅ **2026-10-14 Mut@k 子集实测完成**（`experiments/emse_ult_mutk.py` +
  `tests/test_emse_ult_mutk.py`，零 LLM；工件
  `（工件已清除）`）：对既有工件的生成测试
  批量跑 cosmic-ray 口径 Mut@k——
  | 组 | 任务 | killed/total | pooled |
  |---|---|---|---|
  | 生成测试·完整规格优先（specir 探针） | 25 | 232/250 | **0.928** |
  | 生成测试·纯 NL 规格优先（ult_lite46 replace） | 46 | 439/460 | 0.9543 |
  | gold 官方测试（上界参照，探针 25） | 25 | 250/250 | 1.0 |
  口径：cosmic-ray 8.7.0（配置哈希 `1e1230a7e298d1e2d7856ca437332e27
  702cfa1612dfc80ab71f9ca105b6ea22` 随工件透出），target=`fixed` 正确
  实现，max_mutants=10（**确定性截断面，非全变异体**，引用须带此标签），
  timeout=120s（timeout 计 killed，2026-10-13 裁定）。**「变异强但缺陷盲」
  洞察**：同批 specir 生成测试 detection=0/24（不在缺陷码上变红）却杀死
  92.8% 变异体——测试强度（变异维度）与缺陷检出（F2P 维度）是可分离的
  两种质量。局限：① max_mutants=10 截断面；② 臂级任务集不同（25 vs 46，
  重叠 7）——配对子集仅描述性；③ 全量 Mut@k（全变异体 × 3,909 任务）仍属
  T-07 6 周原范围，本批次为子集实测。
- ⚠️ **2026-10-15 批次八勘误（取代上表口径）**：① 上表"max_mutants=10
  确定性截断面"实为 **uuid4 随机序子集**（非确定性；`_trim_work_items`
  docstring 已更正）；② 上表数字含大量"在正确代码上 fail/nonterminate"
  套件的**平凡击杀**，系统性偏高；③ gold 1.0 已确认为**伪影**（官方
  test_list 在 **71/71** 任务上无法在 `fixed` 通过——上游不一致，已排除
  包装/物化因素；官方物化风格复测同败）。**新定案（全变异体 + 健全性
  前置门 = 官方 correct_tasks 操作化）**：specir **0.4395**（847/1927，
  n=5/25）；replace **0.6749**（1590/2356，n=9/46）；gold **n=0**（全跳过）。
  工件：`（工件已清除）` + 审计
  `emse_test_sanity_20261015/`。完整口径链与对外措辞纪律见
  `docs/design/layered_narrative.md` §3（批次八修正）。

---

## 5. 分层执行计划与成本

### 5.1 阶段

| 阶段 | 规模 | 目的 | 门禁 |
|---|---|---|---|
| **0 冒烟** | 10–20 任务 | cosmic-ray 在本项目 Python 环境下可跑通；FUT 物化无 import 伪影 | 全流程零异常 |
| **1 定标** | **200 任务**（按 cyclomatic 分位**分层抽样**，固定 seed，抽样脚本预注册） | 四指标 + `n_eff` + 超时率 + **实测 tokens/task** + K 的实际效应 + 失败模式分布 | `n_eff ≥ 180` ∧ 超时率 ≤ 预注册阈值 → 才可进阶段 2 |
| **2 全量** | **ULT 3,909** + **PLT 双轨** | 对外数字 | 预注册的停机规则 |

### 5.2 成本估算（**外推依据已注明**）

**实测依据（本项目主批次，零 LLM 回放）**：
`experiments/results/main_batch/*.json`（10 批，**669 任务**，`aitester` 臂）
→ 聚合 `results["aitester"]["token_metrics"]`：input **2,549,193** / output **5,883,417** / total **8,432,610**
→ **12,604.8 tokens/task**（输出占比 **69.77%**）；`avg_iterations` 均值 0.82；`avg_elapsed_seconds` 均值 47.0 s。
同一聚合下该批次 LLM 成本 ≈ **$7.82**（价目见 `experiments/price_table.json`：deepseek-flash 峰时 `$0.30/M` in、`$1.20/M` out，`as_of 2026-10-06`）。

**外推（单轨、单遍、同 per-task 成本；用于预算申请，不是承诺）**：

| 项 | 估算 | 说明 |
|---|---|---|
| Token 量 | **49.3 M tokens**/轨（3,909 × 12,604.8） | 线性外推，**假设** ULT 任务与本仓 synthetic 任务同量级 |
| $ | **≈ $45.7** /轨 | 按上述实测输入输出配比换算 |
| 该估算**不包含** | ① K-query 的**历史重放放大因子**；② 更高复杂度（cyclomatic 均值 14.87）带来的更长代码与更多轮次；③ PLT 第二轨（×2）；④ cosmic-ray 全变异体的 CPU 时间 | ①–③ 由阶段 1 **实测**后替换；④ 从未在本项目跑过，**不计入** |

**纪律**：**先测后推**——阶段 1 必须产出实测 `tokens/task` 与 `K` 的实际值，全量预算据此重算；
**禁止**用本表的线性外推对外承诺成本。

### 5.3 ULT/PLT 双轨泄漏对照的实施方式

- **配对设计**：同一任务、同一模型、同一 greedy 配置（temp 0.0）、同一 K、同一超时；
  **唯一变量** = 测试可见性（ULT：无泄漏 / PLT：泄漏测试可见）；
- **分析**：配对差 Δ（PLT − ULT）逐任务计算 → 报 **paired bootstrap 95% CI** 与效应量；
  指标级分解，重点验证"branch 膨胀最大（+9.85pp）"与"mutation 不免疫"是否在本项目复现；
- **报告纪律**：PLT 数字**不得**与 ULT 数字混用（口径矩阵另立行）。

---

## 6. 报告协议

1. **四指标齐报**：accuracy / statement coverage / branch coverage / mutation score，缺一不可（ULT 基线即四指标）；
2. **每个指标必须带 `n_eff`**：分母 = 有效任务数；超时/不可测任务**不进分母**（与 `_m1_metrics` 的 `None` 保守口径一致），
   同时**单列超时率与不可测原因分布**（防止"分母缩小抬高分数"的伪影）；
3. **与 12 模型基线做配对比较**：以任务为单位配对（同 3,909 任务），
   报 paired bootstrap 95% CI 与效应量（复用 `experiments/bayesian_paired.py` / `run_statistical_test.py`）；
   **禁止**只报均值差或跨任务均值比；
4. **单模型明细**：同时报"12 模型均值（41.32/45.10/30.22/40.21）"与"最佳单模型（Pass@1 17.83%）"两个参照点，
   避免只挑一个更好看的比较对象；
5. **泄漏对照单列一节**（ULT vs PLT），并标注为本项目**自采**的独立性检验；
6. **预注册**：抽样方案、K、超时、cosmic-ray 版本与配置、`n_eff` 门槛、停机规则、失败分类口径；
7. **落盘与登记**：结果入 `experiments/results/ult_*/`；口径行入 `docs/design/repair_caliber_matrix.md`（引用纪律 `:50-57`）。

---

## 7. 风险

| # | 风险 | 预期 | 应对 |
|---|---|---|---|
| **R1** | **复杂度鸿沟**：本项目的验证场景是 QuixBugs 单函数玩具程序与 synthetic 模板；ULT 是 cyclomatic ≥10（均值 14.87）的**真实函数**，本项目**从未测过**该复杂度 | **本项目在 ULT 协议上显著低于 41.32%**；甚至可能低于"12 模型"的下限 | ①把该预期**预注册**为假设，避免事后找补；②阶段 1 先建**内部锚点**（同协议下本仓 synthetic Level 3.5 的分数）作为相对参照；③若定标 <20%，先做**能力缺口分析**（失败分类：语法/导入/断言弱/超时/幻觉 API）再决定是否跑全量；④报告用**相对基线**表述，不做绝对对标宣传 |
| **R2** | 泄漏混淆（PLT 显著更高） | 记忆效应污染结论 | 双轨配对设计是唯一控制手段（§5.3）；结论只在**配对差**上给 |
| **R3** | cosmic-ray 环境/口径风险（Python 3.12、动态导入、超时） | 变异体枚举失败或分数不可比 | 阶段 0 冒烟 + 版本/配置哈希入报告 + 超时按存活计（保守） |
| **R4** | 数据许可风险（§4.1 未澄清） | 法务/署名问题 | 不打包、用户本地拉取、显式条款、保留逐文件许可元数据、报告标注口径 |
| **R5** | K-query 协议实现偏差 | 与论文数字不可比 | 与论文**定性模式**对拍（如 branch 膨胀排序、mutation 相对表现），不追求逐位相同（模型不同）；协议参数写入报告 |
| **R6** | 分母膨胀/幸存者偏差 | 分数虚高 | 四指标齐报 + `n_eff` + 超时率 + 失败分类（§6.2） |
| **R7** | 成本失控（K 轮 + 全变异体） | 预算超支 | 阶段 1 实测后重算；设每任务 token 上限与熔断 |

---

## 8. 边界（本方案**不做**的事）

1. 不写实现代码；不改 `experiments/` / `src/` / `BASELINE.yaml` / README（本任务写入范围仅三份文档）；
2. 不改本项目既有指标口径（`detection_rate` / `repair_rate` / `false_fix_rate` / `passed` 全部保持）；
3. 不提供跨口径换算系数（§3 结论：不存在）；
4. 不把 ULT 数字写入 README/MODEL_CARD/BASELINE（无写入权限，且需先完成 §4.1 许可澄清与 §6 报告协议）。

---

## 9. 验收 checklist

- [ ] `repair_caliber_matrix.md` 新增 ULT 口径行（四指标 + n_eff + 数据子集口径）；
- [ ] 阶段 0 冒烟通过（cosmic-ray 可跑、FUT 物化无 import 伪影）；
- [ ] 阶段 1 产出实测 tokens/task 与 K，替换 §5.2 的线性外推；
- [ ] 双轨配对比较的 CI 与效应量落盘；
- [ ] 许可动作 1–5（§4.1）完成，含向作者的条款询问归档；
- [ ] 报告含 R1 预注册的"预期显著低于 41.32%"陈述，且无绝对对标宣传。
