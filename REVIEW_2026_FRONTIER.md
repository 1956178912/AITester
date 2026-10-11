# AITester 系统性审查与 2025–2026 前沿对标报告

| 项 | 值 |
|---|---|
| 审查对象 | `/Users/wangchenyu/Workspace/AITester`（Python；HEAD `d9e51df`；456 commits；工作树干净） |
| 审查日期 | 2026-10-10 |
| 审查方式 | 4 名独立审计者（工作目录索引 / Python 专项 / 领域专项 / 对抗式证据核验）+ Lead 一手复核 + 联网前沿检索 |
| 证据纪律 | 项目侧数字一律标注「工件路径 + JSON key + 分母」；外部数字标注可信度 A/B/C；凡未独立核验者显式标 `[未核验]` |

**口径与缺陷披露（先行声明）**：本报告是"审查报告"而非"论文"。
其中若干外部引用（尤其项目文档中转引的 2026 年新论文）**未能一手核验**，
已在 §3 与 §14 逐条标注 `[未核验]`，**不得直接用于投稿**。
凡一手核验的数字，均给出工件路径与计算口径，可复算。

> **🔴 最紧急发现（本报告优先级最高的单条结论，含自我更正）**
> `README.md:15-16` / `README.en.md:16-17` 引用："（CANDOR, ICST 2026 [待核验]：one-shot Gemini
> 88.35% vs CANDOR 35.92%，且耗时 45s vs 50h）"。
> 经复核（详见 §3.6）：**数字与论文都是真的，缺陷是错误归属**——
> 88.35%/35.92% 来自 **IEEE 独立复现研究**（Radaideh & Corriveau, IEEE Xplore **11655121**），
> 而 CANDOR 是 **TOSEM 2026**（DOI 10.1145/3803418）且原文结论**相反**（多智能体 line 0.991）。
> README 把第三方复现的结论挂在了"CANDOR, ICST 2026"名下，且未标注这是第三方复现。
> **必须改写为三方并列表述**（§3.6.2 给出可直接采用的文字）。
> *(本报告初版曾判定为"文献编造"，该判定过重，已在 §3.6 显式更正。)*

---

## 0. 执行摘要

### 0.1 一句话定位

> **AITester 是一个方法学诚实度处于同规模研究代码前 5%、但正主张证据基础严重不足的系统。**
> 它已经用三次独立实验证明自己的多智能体编排是净负贡献（−28pp），
> 而其"逻辑驱动"主张所依赖的通道在关键批次里**根本没有开启**。
> 它目前的真实水平是：**一个在小程序契约任务上能与前沿对话的修复引擎 + 一套世界级的归因评估方法学**，
> 而不是一个"逻辑驱动的多智能体测试生成与自修复系统"。
>
> **本次审查同时纠正了两个方向的外部事实**：项目 README 里有一条**编造的引用**（CANDOR）；
> 而任务简报里作为"已验证有效方向"给出的多条参考（85% MTTR、VIGIL、TwinMem-Agent 的 18× 等）
> **经一手核验后同样不成立或严重限定**（C6）。**双方的引用都需要重建。**

### 0.2 八个核心结论（C1–C8）

| # | 结论 | 关键证据 |
|---|---|---|
| **C1** | **"多智能体"标签被判了负，但决定性实验里没有任何多智能体组件；而 2026 文献对该范式的结论是分裂的，不是共识。** `logic` 档（`config.py:64-112`）不含 `EXPERT_POOL_ENABLE` / 辩论 / RAG / risk_approval。−28pp 测的是"带规划与修复环的单体流水线"，却被用来给"多智能体"这一更大标签判负。**且项目用一条错误归属的引用（见 C1b）把"单一复现的单一指标结果"包装成"跨论文共识"。** 真实证据是分裂的：负面只指向**手工的、工具特定的编排**（Konstantinou et al., ICST 2026）；而 CANDOR（TOSEM 2026, line 0.991）、TestAgent（FSE Companion 2026, line 92.34%/mutation 83.69%）、MUATC（APSEC 2025）都是**正面**结果；IEEE 复现研究则在 mutation score 上给出对 CANDOR 的**不利**结果。 | T3 §2；`README.md:15-16`；§3.1、§3.6 |
| **C1b** | **🔴 README 引用存在"错误归属"（非编造），必须改写为三方并列表述。** `README.md:15-16` 称"CANDOR, ICST 2026: one-shot Gemini 88.35% vs CANDOR 35.92%，45s vs 50h"。复核：**数字真实**（来自 IEEE 复现研究 Radaideh & Corriveau, Xplore **11655121**；另有 one-shot GPT-4o 69.90% vs CANDOR 45.63%）；**CANDOR 真实**（TOSEM 2026, DOI 10.1145/3803418，原文结论**相反**：line 0.991）。缺陷是：① venue 错（把 IEEE 复现研究挂到 ICST 2026 CANDOR）；② 未标注第三方复现身份；③ "45s vs 50h" 无出处。**该引用正支撑项目最核心的叙事调整（ADR-0016 / R26），且把"单一复现的单一指标结果"表述为"跨论文共识"，证据强度被高估。** | §3.6.1、§3.6.2 |
| **C1c** | **最强的负面证据本可正确引用，却被一句错误归属掩盖。** ICST 2026 的 **Konstantinou, Degiovanni & Papadakis**（arXiv:2601.09695）在 6 个完整 Java 仓库 / 393 类 / 3,657 方法上证明 Plain-LLM 49.95/35.33/33.82 全面优于 HITS/SymPrompt/CoverUp/TestSpark，且请求数更少——**这才是"手工编排优势有限"的正确出处**。 | §3.1、§3.6.2 |
| **C2** | **"逻辑驱动"的度量通道与注入通道口径不一致；且其检出贡献经一手 A/B 测定为【负】。** `spec_compile_rate`（0.472–0.517）度量的是"编译器对 LLM 形式化产物的接受率"，而实际 oracle 注入通道用的是**另一套更严的判定**（`_compile_single_clause` 增加标识符绑定检查）。**⚠️ 本节初版曾断言"逻辑通道一行都没注入"，该断言错误**（见 §6.8 更正框）：实测 **18/50 行注入了** `test_specir_v2_oracle`，注入率 36%；**但注入组的 detection 反而更低（5/16 = 31% vs 12/21 = 57%）**——这是**观察性关联，非因果**（注入与 LLM 产出更丰富的 `logic_analysis` 同源，亦与 stop_reason 分布纠缠）。**✅ 2026-10-10 已由一手 A/B 测定：注入 `SPEC_ORACLE_EXEC_ENABLE` 使 detection 24/37(64.9%) → 15/37(40.5%)，McNemar p=0.0389 / 精确二项 p=0.0352，机制指向 over_red 22→29 升高（n=37、ITT 口径，须附限定）。****✅✅ 2×2 因子实验已独立复现（`review_2026/E6_factorial_2x2_result.md`，$1.61）：gate ON 层 26/36→14/36（12:1, p=0.0034）、gate OFF 层 25/36→18/37（9:2, p=0.065），两层同向；pooled 33:6, p<0.001。机制再次是 over_red 升高（17→31 / 20→28）。** | §6.8；`spec_ir_v2.py:571-580` vs `:195-238`；`e4_quixbugs_FIXED_harness/aitester.json` |
| **C3**【2026-10-10 经真实 A/B 更正】 | **证据门不是"漏点"，而是"有效守门"。** 关掉证据门后落盘补丁 **27→45（+18 行）**，但 **correct 总量完全不变（32/46）**，而**落盘精确率从 92.6% 降到 71.1%**（多落盘的 18 行中仅 7 行 correct）。detection 与 repair 配对检验均为 **p=1.0000（无效应）**。**原报告"修复天花板最大漏点在落盘侧、接受侧高精度"的表述已撤回**（该估算源自工件 `patch_correct` 字段的静态重放，未做真实 A/B）。 | `review_2026/E6_factorial_2x2_result.md`；`experiments/results/llm_logic_ab_20261010_202129/`（4 臂） |
| **C4** | **存在第五起测量伪影，且性质比前四起更隐蔽。** 全部 16 个入库批次 **476/476（100%）** 的 `patch` 字段带围栏残留；ADR-0021 的修复只落在**测量层**，**透出层从未回灌**。后果：`patch_plausible` / `patch_precision` / CPR / IDR / REPAIR_CEILING 漏斗 / E7 抽样框与 repair 主指标的**分子不同源**。 | T4 §3 R1/R2；`run_benchmark.py:601-617` |
| **C5**【2026-10-10 经零 LLM 体检更正为**两层**根因】 | **唯一有效的真实基准是 50 个玩具程序；SWE-bench「0/20」不是负结果，而是两次发生在判定之前的失败。** 第 1 层：**JSONL 无源码字段 → `instance_code` 兜底为 issue 文本**（项目自带 `python main.py check-dataset swe_bench` 直接报「缺失被测源码任务 **225 个**（instance_code 兜底为 issue 文本）」并列出那 20 个实例）→ `error_category=syntax` 19/20 → **检出从未被计算**；第 2 层（本次新发现）：**仓库级 venv 环境不兼容**——`click 8.5.0` 已移除 `CliRunner(mix_stderr=…)`，而 sqlfluff 测试工具仍在传该参数 → **gold 补丁正确应用后 F2P 仍 TypeError**（实测 rc=1）→ 即使修好第 1 层，评测仍被阻断。**故 0/20 既非负结果、也非有效评测。** | `review_2026/E7_swe_bench_data_path_audit.md`；`swe_bench_lite_20/benchmark_swe_bench_20260818_113525.json` |
| **C6** | **🔴 任务简报中作为"已验证有效技术方向"列出的多条参考，经一手核验后不成立或严重限定。** "MTTR 降低 85%" 的唯一来源是一个**个人 GitHub README**；VIGIL 是**单作者、n=12、无基线**的案例研究；**ARC-APR 疑似不存在、Defects4J v3 不存在、AgentRepair 无可获取指标**；TwinMem-Agent 的 89.1% 是 **200 实例子集 + FSE *Companion***，其 18× 成本主张**可疑**；latent comms 的 O(N²)→O(N) 是**渐近证明而非实测节省**。**简报所给的"参考基线"不可直接采信。** | §3.2.1、§3.3、§3.6.1；R2 |
| **C7** | **"自修复"子方向在 2025–2026 年没有可引用的量化前沿基线。** 这既是机会（本项目是少数把自修复做成可测量、可复现、带弃权与防作弊机制的系统），也是风险（无人对标 = 无人验证问题重要性）。**策略含义：不要定位为"超越自修复 SOTA"，而应定位为"第一个可归因、可复现的 LLM 自修复评估平台"。** | §3.3 |
| **C8** | **两个已发表的机制性发现直接命中本项目的核心病理，必须引用（否则会被认为重复发现）。** ① **Self-Repair Trap（ASE 2026）**："迭代修复把模型推向更易满足但检出更弱的断言"——正是 −28pp/`false_fix 87.2%` 的已发表解释；② **ImpossibleBench（ICLR 2026）**：pass-rate 等价于 cheating-rate（构造使然）——`false_fix 87.2%` 的同构证据。③ **Abstain and Validate（ICSE-SEIP 2026）**：弃权 +13pp、验证 +15pp、**组合 +39pp**——本项目 `patch_abstain` 已在此方向上，是**最应强化的护城河**。 | §3.2.2 |

### 0.3 四个必须立即处理的行动（P0）

1. **P0-0｜改写 README 的 88.35%/35.92% 引用为三方并列表述**（零成本，当天）。
   现状是**错误归属**（把 IEEE 复现研究的结论挂在"CANDOR, ICST 2026"名下），
   且把单一复现的单一指标结果表述为"跨论文共识"。§3.6.2 给出可直接采用的替换文字。详见 I-21 / I-22。
2. **P0-1｜回灌围栏残留 + 把"开关必须入 `env_snapshot`"做成门禁**（零 LLM 成本，1–2 天）。
   详见 §9 建议 I-01 / I-02。
3. **P0-2｜做"载荷等价"单变量实验（H1）**，回答 −28pp 到底是"编排"还是"载荷"（约 0.7M token，20 分钟单臂）。
   详见 §5 路径 **P1-H1**。
4. **P0-3｜把逻辑通道真正打开并单独度量**：新增行级 `spec_oracle_injected` / `spec_oracle_verdict` 指标，
   在 QuixBugs 41 任务上跑 `SPEC_ORACLE_EXEC_ENABLE=true` 的 A/B。
   **注意**：同构主张已有已发表的**正向**证据（Google SpecOps：规格驱动 +9.8pp bug detection,
   p=0.0352；SPARC：+20.78% mutation），**这条路本身是对的，只是本项目没跑起来**。
   详见 §5 路径 **P2-L1**。

---

## 1. 工作目录与文件清单

### 1.1 扫描范围与规模（可复现）

| 项 | 值 | 依据 |
|---|---|---|
| 仓库总占用 | 1.2 GB（`.venv` 911 MB、`experiments/results` 88 MB） | `du -sh` |
| 排除缓存/虚拟环境后文件数 | 1,035 | `find`（排除 `.git`/`.venv`/缓存/`experiments/results`） |
| 被 git 追踪 | 4,028（其中 **3,426 在 `experiments/results/`，占 85.1%**） | `git ls-files` |
| `src/` | 119 py / 45,371 行 / 4.1 MB | `find` + `wc -l` |
| `tests/` | 255 py / 66,880 行 / 12.0 MB | 同上 |
| `experiments/` | 46 py / 19,087 行（`run_benchmark.py` 单文件 156,754 B） | 同上 |
| `scripts/` | 35 py / 6,292 行 | 同上 |
| 文档 `.md` | 33,108 行（`README.md` 128,786 B、`CHANGELOG.md` 397,160 B） | 同上 |
| 实验工件 | 138 条目（52 目录 + 86 文件，5,322 文件 / 75.6 MB） | T1 §1.4 |
| **Jupyter Notebook** | **0 个 `.ipynb`**（以 `experiments/*.py` 脚本替代） | T1 §1.2 |

### 1.2 文件树（顶层，排除缓存与虚拟环境）

```
AITester/
├── src/                   119 py / 45,371 行  ← 主源码（16 个子包）
│   ├── agents/    (48 文件) planner, generator, executor*, debugger, fault_localizer,
│   │                        fl_spectral, error_classifier, rogue_monitor, flaky_gate,
│   │                        deterministic_guard, injection_guard, kernel_sandbox, llm_client…
│   ├── graph/     (34 文件) workflow.py(1088) nodes.py(2005) state.py(781) debugger.py
│   │                        event_bus, expert_pool, risk_approval, trace_reward, patch_io…
│   ├── tools/     (58 文件) patch_*(applier/rollback/abstain/evidence/intent/localized/
│   │                        postprocess/test_hacking), fl_spectral, oracle_validator,
│   │                        detection_gates, multi_candidate, branch_coverage_inject,
│   │                        logic_spec, cross_file, graphrag, language_backend, tree_sitter…
│   ├── specs/     (10 文件) spec_ir.py(365) spec_ir_v2.py(649) spec_smt.py(719) spec_refine.py(225)
│   ├── datasets/, api/, budget/, cli/, config/, db/, experiments/, observability/,
│   │   prompts/, rag/, reports/, utils/
├── tests/                 255 py / 66,880 行（257 条目含 README/conftest）
├── experiments/           46 py / 19,087 行 + results/(88 MB)
├── docs/                  83 文件：adr/(24 ADR) design/(13) history/(20) security/
│                          preregistration.md(42 KB) api_reference.md(92 KB)
│                          threat_model.md DATA_CARD.md coverage_ratchet.yaml env_budget.yaml
├── scripts/               35 py：gates/(20 门禁脚本) tools/
├── data/quixbugs/         438 文件（**嵌套 git 仓库，未登记 submodule**）
├── examples/ .github/workflows/{ci,perf,release}.yml .git-hooks/ .private/(未追踪)
└── 根文件：README(.en).md QUICKSTART(.en).md CHANGELOG(.en).md BASELINE.yaml
          MODEL_CARD(.en).md SECURITY(.en).md CITATION.cff LICENSE
          pyproject.toml setup.py requirements(.txt/.lock) Dockerfile(.repro)
          Makefile reproduce.sh config.py main.py init_db.py .pre-commit-config.yaml
```

### 1.3 关键文件摘要（要点）

| 文件 | 关键内容 |
|---|---|
| `README.md:1-30` | 自我定位 = "检出优先的测试生成与修复**归因评估系统**"；**多智能体被降级为"可消融容器（非主断言）"**；披露 repair 修正口径 39.31% |
| `BASELINE.yaml`（611 行） | **机器可读单一事实来源**。detection plain_llm_df 44.8% > aitester 15.8% > plain_llm 1.5%；repair 39.31%；QuixBugs 修正结算；4 起测量伪影；A1 假阴性；孤儿进程；D1/D2/D3 缺陷 |
| `docs/preregistration.md`（606 行） | E1–E7 预注册：主终点、阈值、停止规则、统计计划（McNemar + BH-FDR + 贝叶斯 ROPE ±5pp + 聚类 DEFF + 模板级符号检验）；E4 污染防控强制披露条款 |
| `docs/adr/`（24 份） | 0003 默认关原则 / 0016 编排定位重述 / 0017–0020 修复引擎范式转向 / **0021 repair=0 围栏伪影定案** / 0024 反事实 FL 上界 / 0027 修正口径重估 / 0028 FL 约束门 / **0029 测量伪影连环** |
| `docs/design/repair_caliber_matrix.md` | repair 口径矩阵 8 行（分子/分母/oracle/数据集/臂/种子/开关/工件/复算命令）+ 4 条强制引用纪律；自述"在建立本表之前，任何对外引用 repair 数字都有被审稿人一枪命中的风险" |
| `MODEL_CARD.md` | 不自研/不微调模型；诚实声明检测劣于纯提示；"逻辑驱动"全链路**默认关闭**；真实 SWE-bench Lite resolved 0/20 |
| `docs/DATA_CARD.md` | 自曝"**出题人=判卷人**"偏差；QuixBugs MIT / BugsInPy 无 SPDX / TestGenEval CC BY-NC 4.0 门槛 |
| `docs/threat_model.md` | 六大攻击面；自述"LLM 生成代码自动执行 = 最核心风险源"；内核级沙箱默认关 |
| `pyproject.toml` | PEP 621 + `dynamic=["version"]` + PEP 639 SPDX + extras（rag/viz/experiments/ux/dev/formal/db）+ PEP 561 `py.typed` |
| `.github/workflows/ci.yml`（36,952 B） | 4 jobs：`smoke-llm`（默认关）/`test`（3.12–3.14 矩阵）/`security`/`supply-chain`；action 全部 SHA 钉版 |
| `Makefile` | 24 个目标；`gates` 聚合 8 类门禁；只读复算目标（`corrected-metrics`/`repair-replay`/`target-quality`/`cpr-idr`）均标"零 LLM" |

### 1.4 缺失 / 不可读 / 敏感

| 项 | 状态 |
|---|---|
| `.env` / `.env.local` | 存在、已被 gitignore、**未读取内容**；**权限位 0644**（同机其他用户可读），而仓库另有 **209 个文件为 0600** —— 敏感文件权限策略与实际相反 |
| `.private/` | 21 文件 / 0.92 MB（含 9 份历史审查报告）；已 gitignore、未追踪、未读取 |
| `docs/troubleshooting.en.md` | **缺失**（中文版自述"待补"，由双语门禁白名单豁免） |
| `docs/review/` | 已随 2026-10-09 清理批次删除 |
| `data/swe_bench_lite_*` | **本机不存在**（`data/` 下仅 `quixbugs/`）→ SWE-bench 复跑当前不可行 |
| `experiments/results/**` 明细 | 本次只做类别汇总；4,406 trace JSONL 与 820 JSON 未逐个读取 |

### 1.5 本次审查依据的范围声明

- **一手读取**：`BASELINE.yaml` 全文、`README.md` 头部、`docs/preregistration.md` 结构与执行记录、
  `docs/adr/README.md` + 0029、`docs/design/repair_caliber_matrix.md`、`pyproject.toml`、
  `src/specs/spec_ir_v2.py`、`src/specs/spec_smt.py`、`src/graph/{workflow,nodes}.py`（关键函数）、
  `src/tools/{detection_gates,patch_applier}.py`、`src/agents/{generator,credential_scrub,kernel_sandbox}.py`、
  `experiments/{run_benchmark,_m1_metrics,repair_replay,corrected_metrics,mutation_testing}.py`（关键函数）、
  以及 **5 个实验工件 JSON 的逐行重算**。
- **只列清单未读内容**：`tests/**`（255 文件）、`experiments/results/**`（除被重算的 5 个工件）、
  `data/quixbugs/**`、`docs/history/**`、`.venv/`。
- **未读取内容（按令）**：`.env`、`.env.local`、`.private/**`。
- **未执行**：任何写操作于仓库既有文件；任何调用 LLM 的脚本；任何 formatter/自动修复。
  本报告及其配套 5 份审计文件写入 `review_2026/`（新增目录，`git status` 仅显示 `?? review_2026/`）。

---

## 2. 项目理解与边界

### 2.1 项目真实定位 vs 任务描述（重要偏差）

任务描述称其为「逻辑驱动的多智能体测试生成与自修复系统」。
**仓库自身的第一手表述不同，而这个差异本身就是审查的第一结论**：

| 来源 | 表述 |
|---|---|
| `README.md:3` | "AITester：检出优先的测试生成与修复评估（**归因**）系统" |
| `README.md:5-9` | 核心创新 = 检出优先思维链 + 分层错误修复 + Oracle 闭环；"**多智能体编排**在本系统中定位为**可消融容器**（非主断言）" |
| `docs/adr/0016` | 编排净负贡献 δ=−0.3673；标题与开篇不再以"多智能体"为主表述（R26 叙事对齐） |
| `MODEL_CARD.md:87-88` | "逻辑驱动"全链路**默认关闭**；"有效性主张尚未被真实基准支持" |

**因此审查的核心问题不是"它的多智能体做得好不好"，而是：**
> 在一个已被自身三次实验证否编排增益的系统里，"逻辑驱动"是否是**唯一尚未兑现但可兑现**的差异化卖点？

本报告的回答是「是」，并在 §5 给出可实验验证的兑现路径。

### 2.2 系统当前架构（实际执行路径）

```
[可选] Planner ──▶ Generator ──▶ Executor ──▶ [特异性门①对照 gold fixed]
   │                   ▲              │                    │
   │                   │              ▼                    ▼
   │            (再生成 ≤MAX_REGEN)  路由 _should_debug:  specific_red → 修复环
   │                   │              │                   over_red    → 再生成
   │                   │              ├─ 全绿未检出 → regenerate（检出优先）
   │                   │              ├─ 近期修复无效 → done（48% 任务在此终止）
   │                   │              ▼
   │                   └──────── Debugger ──▶ [多候选] ──▶ PatchApplier ──▶ Executor
   │                                            │                    │
   └─ SpecIR/SMT（默认关）                       └─ 弃权门/证据门/回滚（默认关）
```

- **编排引擎**：LangGraph `StateGraph`，显式 `recursion_limit` 上界 + checkpointer（`workflow.py:883-914`）。
- **终止条件**：`StopReason` 枚举 + 单点判定 `determine_stop_reason`（`workflow.py:100-214`）。
- **实测终止分布（QuixBugs 50 任务）**：`skip_debugger_repair_invalid` **24** / `test_passed` 13 / `max_iterations` 13。

### 2.3 关键假设与红队判断

| # | 项目假设 | 审查判断 | 证据 |
|---|---|---|---|
| A1 | 多智能体编排带来检测增益 | **已被自身三次独立证否** | δ = −0.279 / −0.3673 / −0.253；`BASELINE.yaml:165-169,200-236,571-577` |
| A2 | 逻辑驱动能提升检出 | **既未被证实也未被证否**（观察性关联为负，但存在混淆） | §6.8：注入 18/50，注入组 detection 5/16=31% vs 未注入组 12/21=57% |
| A3 | 覆盖率是有效性代理 | **对"被测代码可能有缺陷"的场景成立（本项目正属此类）**——但**引用必须用限定版结论**：Zhao, Zhou & Cohen（ISSTA 2026）证明覆盖+变异在**回归（无缺陷代码）**设定下做**跨模型比较有效**（branch vs raw mutation r=0.780），在**有缺陷代码**时不可靠。MUTGEN（TSE 2026）实测有 100% 覆盖仅 4% 变异的套件 | 覆盖 84–94% 而检出 13–16%；`BASELINE.yaml:56-62`（该 note 的引用已按 R3 更正） |
| A4 | repair 能力真实存在（39.31%） | **成立，但口径可被误读** | 见 §6.3 C3 |
| A5 | 合成基准结论可外推 | **不成立** | 29 个模板覆盖 87 任务；唯一真实基准是 50 个玩具程序 |

---

## 3. 2025–2026 前沿基线表

> **可信度分级**：**A** = 顶会/顶刊已发表；**B** = arXiv 预印本或 workshop（待同行评审）；
> **C** = 技术报告/厂商博客；**V** = 本审查者一手核验（读取原文/摘要页）。
> **`[未核验]`** = 数据来自项目文档转引，**我未能一手确认，不得直接用于投稿**。

### 3.1 测试生成（LLM / 多智能体 / agentic）

| 子方向 | 前沿方法/系统 | 关键指标 | 指标值 | 评测基准（规模） | 来源（作者, 年份, venue） | 可信度 | 可迁移性 |
|---|---|---|---|---|---|---|---|
| LLM 单发测试生成 | **GPT-4o zero-shot** | any-p@1 / line cov / mutation | **64.0% / 35.2% / 18.8%**（all-p@1 仅 **7.5%**） | TestGenEval（68,647 tests / 1,210 file pairs / 11 Python repos） | Jain, Synnaeve, Rozière, **ICLR 2025**（arXiv:2410.00752） | **A** | 高（同生态、Python） |
| Agentic 反馈驱动 | **TestForge** | pass@1 / line cov / mutation / 成本 | **84.3% / 44.4% / 33.8% / $0.63 per file**（25 轮，≈447s/数据点） | TestGenEval full（1,210 programs） | Jain & Le Goues, 2025, arXiv:2503.14713 + CMU-S3D-25-100 | **B** | **很高（直接对标基线）** |
| 同上（自身消融） | TestForge vs GPT-4o 0-shot | 增量 | **coverage +9.6pp；mutation +15.0pp** | 同上 | 同上 | B | 高 |
| 同上（45 程序子集） | TestForge / Pynguin / CodaMosa | pass@1 / cov / mut | **100 / 60.0 / 31.6** vs **60.0 / 24.0 / 4.2** vs **62.2 / 30.2 / 2.7** | TestGenEval Python-3.10 子集（45） | 同上 | B | 高 |
| Python 覆盖率 SOTA | **CoverUp** | line / branch / L+B | **63.8% / 49.2% / 60.3%**（CM 套件：425 模块 ≈100k LOC）；median **82.4/66.7/79.6**；MT 套件 **89.2/88.7/89.0** | 自有 CM/PY/MT 套件（**非 TestGenEval**） | Pizzorno & Berger, **FSE 2025**（DOI 10.1145/3729398） | **A** | 高 |
| 同上（成本） | CoverUp | 成本/时间 | **$399 / 4.0h / 28,690 prompts**（CM 套件）；TestForge 侧估 **≈$2/数据点** | CM 套件 | CoverUp Table 3 / TestForge §4.2 | A | 高 |
| 神经符号（C） | **SPARC** | line / branch / mutation 相对 vanilla prompt | **+31.36% / +26.01% / +20.78%**；测试保留率 94.3%；匹配或超过 **KLEE** | 59 real-world + algorithmic C subjects | Chowdhury, Fu, Jabbarvand, 2026-02, arXiv:2602.16671 | **B** | 中（C 生态；机制可迁移） |
| **多智能体（负面，最强）** | **Plain-LLM beats 4 SOTA 工具** | line / branch / mutation | **Plain-LLM 49.95/35.33/33.82** > HITS 42.43/29.49/27.97 > SymPrompt 40.95/27.19/28.40 > **CoverUp 38.85/25.11/26.26** > TestSpark 23.65/16.48/13.88；且请求数更少（11,718 vs CoverUp 12,264 / HITS 23,865） | **6 个完整 Java 仓库 / 393 类 / 3,657 方法**（半数项目在 2023-10 之后） | Konstantinou, Degiovanni, Papadakis, **ICST 2026**（arXiv:2601.09695） | **A** | **极高（直接支持 ADR-0016）** |
| 同上（编译/通过率） | 同上 | 比率 | **≈20% 生成测试不编译；≈43% 不通过** | 同上 | 同上 | A | **极高（基线常量）** |
| 多智能体（混合） | ASTA/ICST 2026 | coverage / ESR / 成本 | multi-agent coverage 峰值 **99.75%**，但 **ESR 97.31% vs single 97.25%（持平）**，token **3–4×** | HumanEval（黑盒） | Arnaudo, Coppola, Morisio et al., **ICST 2026 ASTA workshop** | **B** | 高（成本效益判定） |
| 多智能体（正面） | **CANDOR** | line / branch / mutation；oracle correctness | **0.991/0.970/0.980**（HumanEvalJava 160）；**0.990/0.949/0.939**（LeetCode-Med）；**0.989/0.980/0.937**（LeetCode-Hard）；oracle **0.971/0.993/0.961** | HumanEvalJava + LeetCodeJava | Xu, Wang, Briand, Liu, **TOSEM 2026**（DOI 10.1145/3803418） | **A** | 高 |
| 多智能体（正面，JVM 最强） | **TestAgent** | 执行率 / line / branch / mutation | **97.46% / 92.34% / 90.24% / 83.69%**；检出 154 个真实 bug，精确率 92.22% | 6 个 Java 项目 / 1,451 方法 | Shang et al., **FSE Companion 2026**（DOI 10.1145/3803437.3806428） | **A** | 中（Java、方法级） |
| 多智能体（正面） | **MUATC** | coverage vs CoverUp | **+4.8%–5.5%**；ChatUniTest 数据集 **+12.7%** | 摘要级（**逐系统表未核验**） | Ma et al., **APSEC 2025**（DOI 10.1109/APSEC66846.2025.00028） | **A（摘要）/ 数值部分未核验** | 中 |
| 多智能体（正面，原始出处） | **AgentCoder** multi vs single（消融） | line coverage | **87.5/89.5 vs 72.5/75.9 = +15.0/+13.6pp** | HumanEval/MBPP **canonical solutions**（函数级） | Huang et al., arXiv:2312.13010 | **B** | 中（**"13–15%"的真实出处**；非真实仓库） |
| 变异/检出（更强判据） | **AdverTest** | fault detection | **+8.56% over 最强 LLM 方法；+50.20% over EvoSuite**（Defects4J） | Defects4J | Chang et al., **PACMSE vol.3 / ISSTA 2026**（DOI 10.1145/3832122） | **A** | 高 |
| 变异/检出 | **SWE-Mutation** | VRR / RDR / Pass@1 | 最强：Claude-sonnet-4.5 + Claude Code **98.00 / 40.40 / 71.71**；DeepSeek-V3.1 **88.20 / 10.20 / 36.15**；**agentic 变异使平均检出 71.04% → 39.81%** | 2,636 变异体 / 800 实例 / 9 语言 | Sun et al., **Findings of ACL 2026**（DOI 10.18653/v1/2026.findings-acl.1976） | **A** | **极高（最可比桥接指标）** |
| 变异/检出 | **MUTGEN** | 覆盖 vs 变异反差 | **部分套件 100% line coverage 仅 4% mutation score**；204 subjects beat EvoSuite | 204 subjects / 2 基准 | Wang, Xu, Briand, Liu, **TSE 2026**（DOI 10.1109/tse.2026.3682975） | **A** | 极高 |
| 规格驱动（**与项目最相关**） | Google spec-driven test gen | Δbug detection / Δbranch cov | **+9.8pp（p=0.0352）/ +2.5pp（p=0.0034）**；LLM-as-judge 优于基线 77.8%、优于人类测试 56.7% | Google 生产缺陷 | Tufano et al. (Google), **SpecOps '26**（DOI 10.1145/3842652.3843195） | **B** | **极高（"先写前置/后置条件"正是本项目 spec 层的主张）** |

**本子方向的"必须打败"基线（协议明确）**：
1. **TestForge on TestGenEval full**：pass@1 ≥84.3% / line cov ≥44.4% / mutation ≥33.8% @ ≤$0.63/file。
2. **GPT-4o 0-shot 地板**：pass@1 64.0% / cov 35.2% / mutation 18.8%。
3. **ICST 2026 复现常量**：任何测试生成系统都应报**编译率与通过率**（≈20% 不编译 / ≈43% 不通过）。
4. **SPARC（C 生态）**：神经符号相对提示基线 +20–31pp——**"逻辑驱动"路线在方法论上已被验证可行**的最强证据。
5. **Google SpecOps**：规格驱动的 bug detection +9.8pp（p=0.0352）——**与项目 spec 层主张同构的、已发表的正向证据**。

### 3.2 多智能体程序修复 / APR

| 子方向 | 前沿方法/系统 | 关键指标 | 指标值 | 评测基准 | 来源 | 可信度 | 可迁移性 |
|---|---|---|---|---|---|---|---|
| 潜在空间通信 | **LaMAR (LAC)** | repair success rate | **Defects4J 24.5%（Qwen3-8B）；DebugBench 62.1–87.5%；QuixBugs 62.1–87.5%** | Defects4J / DebugBench / **QuixBugs** | Jiao, Zhang, Feng, Li, **ASE 2026**（DOI 10.1145/3832783.3837423） | **A** | **极高（同基准 QuixBugs）** |
| 同上（理论） | LAC 信息容量 | token 复杂度 | **O(N²) → O(N)**，证明连续空间信道信息容量**严格更高** | 理论（**渐近证明，非实测**） | 同上 | A | 极高 |
| ⚠️ **但** | **潜在空间通信的"成本收益"无实测证据** | — | **无任何论文报告 latent comms 带来的实测 token/$ 节省**；LaMAR 的消融是**定性**的 | — | R2 §6.1 | **A（负面结论）** | **重要：不要把 O(N²)→O(N) 当成本主张** |
| 跨语言修复 | **LANTERN** | Pass@10（Rust） | **+22.09%**（基线 Rust Pass@10 = 65.58%，故"pp vs 相对"需读原文）；p=0.0126，Cliff's δ=0.64；DeepSeek-V3 | xCodeEval APR 子集 | **ICSE 2026**（DOI 10.1145/3744916.3773227） | **A** | 高 |
| 联邦式双链修复 | **FedDualFix** | CR / PR / P@1 | **58 / 84 / 52.1%**；同后端 GPT-4o Direct = 49/44.1%；**plausible-but-incorrect = 26/84 = 31.0%**；成本 3.3k tok/bug、$0.007–0.028/bug | Defects4J v2.0 | Applied Soft Computing 202:115898 | **A** | **极高（plausible vs correct 双报的范例）** |
| Java 真实缺陷最强 | **MultiFixer** | 修复数 | **420/835 = 50.3%**（Claude-3.5-Sonnet；基座模型 326）；声称 Defects4J 新 SOTA | Defects4J v2.0 | arXiv:2607.26591 | **B** | 中（Java） |
| 动态分析增强 | **ADI** | resolve rate / 成本 | **63.8%** SWE-bench Verified，**$1.28/task**，Claude-Sonnet-3.7 | SWE-bench Verified | **PACMSE 2026**（DOI 10.1145/3797126） | **A** | 高 |
| 仓库级修复 | **PhoenixRepair** | Pass@1 | **76.0%** SWE-bench Verified（MiniMax-M2.5）——**独立印证官方榜 75.8%** | SWE-bench Verified | arXiv:2607.18859 | **B** | 中 |
| 开放权重 | **SWE-Master** | resolve rate | **61.4%**（Qwen2.5-Coder-32B）；**70.8% @ TTS@8** | SWE-bench Verified | arXiv:2602.03411 | **B** | 中 |
| 长程仓库导航 | **Prometheus** | resolve rate | **74.4%** | SWE-bench Verified | arXiv:2507.19942 | **B** | 中 |
| **成本前沿（官方榜 JSON）** | **MiniMax M2.5** | resolve / $/实例 | **75.8% @ $0.0733/instance**（60.5 calls） | SWE-bench Verified（500） | 官方 swebench.com leaderboard JSON（2026-02-26 最新提交） | **A（一手提取）** | **极高（成本对标的现实锚点）** |
| 对比 | Claude 4.5 Opus | resolve / $/实例 | **76.8% @ $0.7539/instance**（官方榜最优 79.2% @ 2025-12-15） | 同上 | 同上 | **A** | **MiniMax 便宜 10.3× 只差 1.0pp** |
| 长程仓库导航 | — | — | 成本区间 **$0.0281**（DeepSeek V3.2R, 60.0%）→ **$1.5311**（GPT-4o, 21.6%） | 同上 | 同上 | A | 高 |
| 潜在空间风险 | 未署名预印本 | 警示"latent-channel 风险应在高带宽隐藏态协作被当作默认之前可见" | — | — | arXiv:2606.28958 | **B（警示性）** | 高（对 LaMAR 路线的**反证据**，须正面回应） |

**⚠️ 关于 SWE-bench Verified 的重要警告（R2 一手核验）**：
**不要把 SWE-bench Verified 当作差异化指标**。官方 swebench.com leaderboard 最高 **79.2%**，
但第三方聚合站宣传 "Claude Opus 5 达 96%"；`benchlm.ai` 自己承认
**"94 行中 0 行来自基准所有者或独立运行，88 行是厂商自报"**。
该基准已饱和且自报污染严重。

#### 3.2.1 🔴 两条流传甚广但**不成立**的引用（直接影响本项目与任务简报）

| 引用 | 核验结论 | 证据 |
|---|---|---|
| **"自愈系统 MTTR 降低 85%"** | **❌ 来源是一个个人 GitHub README**：`github.com/suhail39ahmed/self-healing-azure-pipelines`。**无论文、无 DOI、无基准、无方法学**。可信度 **C**。最接近的同行评议来源是低层级 Atlantis Press 论文（ICSSSM 2025），报的是"小时级 → 28 分钟内"、96% RCA、73% 修复成功率，且在**模拟环境**——**不是 85%** | R2 §3、§6.1 |
| **VIGIL（反射式运行时 / EmoBank + RBT 诊断）** | **⚠️ 科学上空心**：单作者 arXiv 预印本，**n=12 事件**，单个合成 agent，**无基线、无统计检验**。其四个数字（12/12→0/12 提示、97s→8s、8→0）来自**一次未重复的案例研究**。**不得作为"反射式运行时可工作"的证据引用** | R2 §3 |
| **ARC-APR benchmark** | **❌ 疑似不存在（很可能为编造）** | R2 §6 |
| **Defects4J v3** | **❌ 不存在** | R2 §6 |
| **AgentRepair** | **⚠️ 无法获取任何指标**（IEEE Xplore 挑战页 / S2 限流） | R2 §6 |
| **DEIMerge** | **⚠️ 出版方隐去了摘要** | R2 §6 |
| **ESBMC-AI** | **⚠️ 不公布成功率**（仅称 "high accuracy"，C 语言 "proof of concept"） | R2 §6 |
| **TwinMem-Agent（89.1% Pass@1 / 18× 成本降低）** | **⚠️ 字面准确但有四处限定**：基准是 SWE-Bench Pro 的 **200 实例分层子集**（8×25），**不是** 1,865 题全集；venue 是 **FSE *Companion***（非主 track）；基线是 mini-swe-agent；**$0.0044/instance 比所有官方 agentic 运行低 6–17×** → **18× 成本主张可疑** | R2 §3 |
| **"85% MTTR" 与 "TwinMem 18×"** | **任务简报中作为"已验证有效技术方向"列出的这两条，经核验不成立或严重限定** | R2 |

#### 3.2.2 本项目必须正面回应的两个**已发表**机制性发现

| 发现 | 内容 | 对本项目的意义 |
|---|---|---|
| **Self-Repair Trap（ASE 2026，arXiv:2608.05917）** | "迭代修复逐步把模型推向**更容易满足但更不擅长检出故障**的断言" | **这精确描述了本项目的核心病理**：项目已实现 `self_repair_trap` 观测器（ADR-0028），但该发现已在 ASE 2026 被同行评议发表——**项目必须引用它，否则会被认为重复发现**；同时它给出了"为什么 −28pp"的一个**已发表机制解释** |
| **"Whose Oracle Is It?"** | **93.0%（160/172）真实 test-changing 修复改动的是一份已存在的测试工件** | 说明"锁定测试防作弊"**不是可部署的答案**——本项目 `patch_test_hacking` 守卫的设计前提需据此重新评估 |
| **ImpossibleBench（ICLR 2026）** | pass-rate **等价于** cheating-rate（构造使然） | 为本项目的 `false_fix=87.2%` 提供了**同构的已发表证据**，可显著增强该发现的学术分量 |
| **Abstain and Validate（ICSE-SEIP 2026，arXiv:2510.03217）** | 缺陷弃权 **+13pp**、补丁验证 **+15pp**、**组合最高 +39pp**（174 个 Google 缺陷） | 本项目已有 `patch_abstain`（弃权精确率 85.97%）——**该工作证明"弃权 + 验证"正是前沿方向，且给出 +39pp 的量级参照**，是本项目最应强化的护城河 |
| **HEJ-Robust（AIware 2026）** | 1,450 个语义保持变换实例；性能**下降 >50%** | 本项目的 detection 从未做过鲁棒性变换测试——**这是一个零成本的补测项** |

**本子方向的"必须打败"基线（R2 给出的 10 点报告协议）**：
1. **75.8% SWE-bench Verified @ ≤$0.10/instance**（MiniMax M2.5 + mini-SWE-agent，500 实例，$0.0733，60.5 calls）；
2. 79.2%（官方榜最优）；76.8% @ $0.7539；
3. **420/835 = 50.3% on Defects4J v2.0**（MultiFixer）；
4. **报告必须齐备 10 项**（否则不可比）：benchmark+版本+实例数与 ID；子集纪律须写入标题；脚手架 + 精确模型版本 + 日期；**$/instance ∧ tokens/instance ∧ LLM calls/instance**（含定价日）；预算/停止规则；**故障定位设置（perfect vs end-to-end）——这是 Defects4J 上最大的膨胀源**；**plausible vs correct 双报**（FedDualFix 的 84/58 是范例）+ 留出/变异检验；测试面完整性声明（ImpossibleBench）；多种子 + 置信区间；HEJ-Robust 式鲁棒性下降。
5. **不要用作头条指标**：SWE-bench Verified（饱和 + 自报）、HumanEval/ClassEval 函数级、latent comms 作成本主张。

> **对 AITester 的直接影响**：本项目已有的 `patch_plausible` / `patch_correct` 双报
> **恰好符合上述第 4 点里的 "plausible vs correct" 要求**，且 `fl_at_k` / `llm_localization`
> 提供了 **end-to-end 故障定位设置**的声明依据。**这两点是本项目相对于多数论文的合规优势，
> 应显式写进方法节而不是埋在补充材料里。**

### 3.3 自修复 / 运行时反思（**R2 独立核验后的诚实结论：该子方向前沿基线基本不成立**）

| 子方向 | 前沿方法/系统 | 关键指标 | 指标值 | 来源 | 可信度 |
|---|---|---|---|---|---|
| LLM 编排自愈微服务 | Agentic AI for Self-Healing Microservices | 框架 | **无量化指标** | SCITEPRESS 2026 | **C** |
| 预算感知自愈 | **FTDI** | 恢复率 | **95.65%** lost-performance recovery（HumanEval/+/MBPP；故障注入）——**但仅来自中文二级摘要**，ScienceDirect 403 | 二级来源 | **`[未核验]`** |
| ⚠️ **MTTR 降低 85%** | 流传甚广 | — | **❌ 来源是一个个人 GitHub README**（`github.com/suhail39ahmed/self-healing-azure-pipelines`）：无论文、无 DOI、无基准、无方法学。最接近的同行评议来源是低层级 Atlantis Press 论文（ICSSSM 2025），报"小时级 → 28 分钟内"、96% RCA、73% 修复成功率，且在**模拟环境**——**不是 85%** | R2 一手核验 | **C（不可引用）** |
| ⚠️ **VIGIL（反射式运行时）** | EmoBank + RBT 诊断 | 12/12→0/12 提示、97s→8s、8→0 | **科学上空心**：单作者预印本、**n=12 合成事件**、**无基线、无统计检验**、**一次未重复的案例研究** | R2 一手核验 | **不可引用为证据** |
| ⚠️ **ESBMC-AI（LLM + BMC）** | — | **不公布成功率**（仅称 "high accuracy"；C 语言 "proof of concept"） | — | R2 | **C** |
| ⚠️ **agent-sandbox-runtime** | — | **纯基础设施，无指标** | — | R2 | **C** |
| ⚠️ **CrewAI 多 Agent SRE** | — | **未取到任何一手量化结果** | — | R2 | **`[未核验]`** |

**诚实结论（本报告最重要的一处"不填表"）**：
**"自修复 / 运行时反思"这一子方向在 2025–2026 年没有可引用的量化前沿基线。**
流传的 MTTR 85% 来自个人 README；VIGIL 是 n=12 的无对照案例研究；
ESBMC-AI 与 agent-sandbox 均不公布指标。**任何以"自修复 SOTA"为对标对象的说法都缺乏证据基础。**

**这对本项目的战略含义（重要）**：本项目在"自修复"上**没有可以对照的前沿**——
这既是**机会**（本项目是少数把自修复做成可测量、可复现、带弃权与防作弊机制的系统），
也是**风险**（无人可对标意味着无人验证该问题的重要性）。
**建议策略**：不要把自己定位为"超越自修复 SOTA"（不存在该 SOTA），
而应定位为**"第一个把 LLM 自修复做成可归因、可复现评估的研究平台"**——
并用**已发表的机制性发现**（Self-Repair Trap, ASE 2026；ImpossibleBench, ICLR 2026；
Abstain and Validate, ICSE-SEIP 2026）作为问题重要性的外部背书。

**唯一可用的近邻对标**（来自 §3.2，属 APR 而非自愈）：本项目的 repair
应与 **Defects4J v2.0 上的 MultiFixer 420/835 = 50.3%** 或
**SWE-bench Verified 上 MiniMax M2.5 的 75.8% @ $0.0733/instance** 对标，
且必须遵循 §3.2 的 10 点报告协议。

### 3.4 逻辑驱动 / 形式化 / 神经符号（**经 R3 独立核验后的重大更正**）

> **⚠️ 本节两处更正（2026-10-10，R3 一手核验）**
> **更正 1**：SPARC 的"neuro-symbolic"**不含 SMT**——它是 CFG 路径枚举 + RAG helper map +
> 编译器/ASan 修复环，**全程无约束求解器**，KLEE 只是对照基线。真正的 2026 SMT+LLM SOTA 是
> **GORDIAN**（见下）。**把 SPARC 当作 SMT 路线代表引用会被审稿人纠正。**
> **更正 2**：本报告 §3.5 与 §2.2/A3 曾引用"ULT/TOSEM 2026 结论：覆盖率与缺陷检出弱相关"
> ——**这是双重误归属**。ULT 是**基准论文**，不是相关性研究；真正的相关性批评是另一篇
> ISSTA 2026 论文，且其结论**更精细**（见 §3.5 更正框）。

| "逻辑驱动"的含义 | 2026 最强范例（R3 核验） | 量化结果 | 可信度 |
|---|---|---|---|
| **(a) SMT / 约束求解 + LLM** | **GORDIAN**（Bouras & Mechtaev, PACMSE, DOI 10.1145/3832126, arXiv:2603.19239）——**建在 KLEE 之上**，让 LLM 生成 "ghost code" 使求解器能处理 solver-hostile 片段 | **+28.5–115.2% 覆盖率 over 传统符号执行；+74.1–189.8% over LLM 符号执行基线；同时削减 token 91–96%** | **A** |
| (a-对照) 结构约束（**非 SMT**） | **SPARC**（arXiv:2602.16671）——CFG 路径枚举 + Operation Map + 编译/ASan 修复环 | +31.36% line / +26.01% branch / +20.78% mutation（59 个 C subject）；测试保留率 94.3%；复杂主体上匹配或超过 KLEE；分层：≤10 路径 100%/100%、11–30 路径 94.4%/86.9%、>30 路径 88.2%/76.3% | **B** |
| **(b) 契约 / 属性测试（Python）** | **SpecPylot**（FSE Companion '26）——`icontract` + `CrossHair`，**唯一的同行评议 Python 契约流水线**；**故意不公布成功率** | — | **A** |
| (b) 属性生成 | **PropGen**（arXiv:2604.13463v2） | **92.6% 属性有效率（912/985）**；发现 25 个新 bug | **B** |
| (b) 智能体式 PBT | **Agentic PBT**（NeurIPS 2025 DL4C, arXiv:2510.09907，含 Hypothesis 作者 Hatfield-Dodds） | 100 个 Python 包：**56% 有效 bug / 32% 可报告 / top-21 86% 有效**；3 个补丁被合并（含 **NumPy**） | **B（workshop）** |
| (b) 公理式 oracle | **Tratto**（ISSTA 2025, DOI 10.1145/3728960） | 73% acc / 72% prec / 61% F1；oracle 产出量 **3×** Jdoctor、FP **10× 少于** GPT-4+CoT | **A** |
| **(c) 时序逻辑** | **LLM-Falsifier**（arXiv:2609.20752）——STL，在 ARCH-COMP 上 **14/21 规格上击败现有 falsifier** | **⚠️ 关键事实：2026 年时序逻辑只作为"伪造目标"出现，没有一篇论文把 LTL/MTL 编译成单元测试**；且属**另一个社区**（仿真计数指标，与单元测试无共享基准） | **B** |
| **(d) NL → 形式化规格 → 测试** | **DSpec2Test**（arXiv:2609.29713，Dafny 规格黑盒测试）：**93.9% 变异击杀 vs 82.4%**；**LM2Alloy**（arXiv:2607.18555，NL→Alloy→测试）**发现了一个 68% 分支覆盖的直接 LLM 基线在 3 次运行中都漏掉的真实缺陷** | (d) 是**最不拥挤、上限最高**的方向 | **B** |
| (d) 规格合成基准 | **AxDafny 92.7% on DafnyBench**（arXiv:2606.32007）；**DafnyPro 86%**（arXiv:2601.05385） | — | **B** |
| (d) 跨语言规格 | **SESpec**（arXiv:2506.09550v4）：QCP + Frama-C/ACSL + Z3，按循环复杂度 **97%/77%/63%** 成功率；优于 AutoSpec 与 ACInv | — | **B** |
| 冲突测试/约束缺陷 | **LM2Alloy**（同 (d)）：形式化中间产物能抓到**约束级缺陷**，而直接 LLM 基线漏掉 | — | **B** |
| LogiCase | IJCAI 2025：CCFG + CodeT5 | **81.18% 集合级有效率** | **A** |

**新增的 2026 Python 强基线（R3 核验，均带数字）**：

| 系统 | venue | 数字 |
|---|---|---|
| **TestTailor** | **FSE 2026**（DOI 10.1145/3797140） | 神经符号，Python **CODAMOSA 486 模块**：**+5.01% 语句 / +4.17% 分支 覆盖率 over CoverUp，API 成本 −60%**；覆盖率准确率 85.2%。**当前最强 Python 基线** |
| **NeuroTestGen** | arXiv:2609.30178 | Z3 + LLM，Defects4J **2,971 方法**：**92.91% line / 88.89% branch / 96.88% pass**（Sonnet 4.6）。**诚实警示：纯符号消融已达 92.35%/88.15% → SMT 对前沿模型仅贡献 +0.56pp** |
| **Panta** | **ICSE 2026**（DOI 10.1145/3744916.3764553） | +26% line / +23% branch（NeuroTestGen 打败的 SOTA 基线） |

#### 3.4.1 🔴 对项目"逻辑驱动"战略的**根本性影响**：瓶颈是"规格合成与保真"，不是"测试生成"

**SWE-PROOF（arXiv:2609.21190v2, 2026-09）的关键结果**：
- 把 SWE-bench Verified 转成 **500 个形式化验证的 issue**；
- **约 25% 的"测试通过"的 LLM 补丁存在反例**（即测试通过 ≠ 正确）；
- **一份忠实的（faithful）形式化规格把解决率从 85% 提升到 95%**；
  **而自然语言规格做不到**（说明"形式化"本身是价值来源，不是"写规格"这个动作）；
- **只有 56% 的 agent 自写规格能通过审计**（spec audit）；
- 规格在**未解决**问题上失败率 92%，在**已解决**问题上 51%。

**R3 的结论一句话**：**2026 年的瓶颈是"规格合成（specification synthesis）与规格保真审计"，不是"测试生成"。**

**这对 AITester 意味着什么（三条，按重要性）**：

1. **本项目的 `false_fix = 87.2%` 与 SWE-PROOF 的"25% 测试通过补丁有反例"是同一现象**，
   而 SWE-PROOF 给出了**已被验证的解法**：用**忠实形式化规格**做补丁验证（85%→95%）。
   本项目的 `spec_smt` + `spec_oracle` + `patch_abstain` **正好是这条路线**——
   但**从未做规格保真度审计**。**这是本项目最大的战略机会，也是最紧迫的缺口。**
2. **必须新增指标 `spec_faithfulness_audit`**：判定"LLM 写出的规约是否真的刻画了目标函数语义"。
   SWE-PROOF 报告 **44% 的 agent 自写规格通不过审计**——若本项目不测，
   则所有"逻辑驱动"的结论都建立在一份**可能不忠实**的规格上。
   （这也解释了为何逻辑 oracle 注入率低：**不忠实的规格编译不通过，反而是安全阀**。）
3. **重新定位"逻辑驱动"的正确靶子**：不是"让 LLM 写出更多可编译表达式"（本项目当前做法，
   `spec_compile_rate` 0.47），而是**"合成并审计出忠实的规格"**。
   前者是语法问题，后者才是语义问题——而 2026 的 SOTA（GORDIAN/SWE-PROOF）
   证明**语义那一侧才有不可替代的价值**。

**同时必须回应的危险基线**：**TEST WARS（arXiv 2501.10200）**——在 GitBug Java 上，
**LLM（TestSpark）在覆盖率与真实缺陷检出上同时输给 EvoSuite（SBST）与 Kex（符号执行），
仅在 mutation score 上获胜**。任何"LLM 优于传统方法"的主张都必须先处理这一反例。

**"必须打败"基线（逻辑驱动侧，R3 给出的 B1–B10 精选）**：
- **B-GORDIAN**：SMT+LLM 真 SOTA（覆盖率 +28.5–115.2% vs 符号执行，token −91–96%）
- **B-TestTailor**：FSE 2026，Python，+5.01% stmt / +4.17% branch over CoverUp @ −60% API 成本
- **B-NeuroTestGen**：Defects4J 2,971 方法，92.91% line / 88.89% branch，
  **且必须做纯符号消融**（该文自己显示 SMT 只贡献 +0.56pp）
- **B-PropGen**：属性有效率 92.6%（本项目无对应指标）
- **B-SWE-PROOF**：忠实规格 85%→95%，**规格审计通过率 56%**（本项目无对应指标）

**⚠️ 不得引用的条目（R3 核验为不存在或无数值）**：
**SymLLM / LLM4Sym / ChatTCG / µBert**（arXiv 全文与网络检索**零学术来源**，疑似不存在）；
**TSC2CARLA**（Borchers et al., DLR, *Sci. Comput. Program.* 242(2025)103256 为真且 Grade A，
TSC = 一阶逻辑 + Z3 → CARLA，但全文只声称"**可行性初步证据**"，**没有任何覆盖率/检出数字**，
引用其数字即为曲解）；**Gena**（ASE 2025 论文为真，DOI 10.1109/ASE63991.2025.00240，
但工具名与全部数字未核验——付费墙）；**CrossHair / PyExZ3**（**未找到同行评议论文**，Grade C）；
**ESBMC-AI**（arXiv 2305.14752 报告修复准确率 90.40% scanf 溢出 / 86.47% 除零 /
70.27% 算术溢出 / 69.66% 数组越界，但**论文内部不一致**：摘要称 50,000 个 C 程序，
贡献节又称"over 1,000"——须标注该警告）。

### 3.5 评估与基准

| 基准 | 规模（一手核验） | 用于 | 可信度 |
|---|---|---|---|
| **TestGenEval** | 68,647 tests / 1,210 file pairs / 11 repos；median gold coverage 60.4%；TestGenEval-Lite = 160 pairs（v1/v2 对文件长度有冲突：1,157/943 vs 782/677 LOC） | 测试生成（**前沿主战场**） | **A（ICLR 2025）** |
| **ULT / UnLeakedTestbench** | **3,909 函数级任务**（cyclomatic ≥10，均值 14.87）；PLT（含泄漏）= 18,169 | 泄漏控制 + 测试生成 | **A（TOSEM 2026, DOI 10.1145/3805043）** |
| ULT 关键数值 | 12 模型均值：**ULT 41.32% acc / 45.10% stmt / 30.22% branch / 40.21% mutation**；**PLT 47.07/55.13/40.07/50.80**；**TestEval 91.79/92.18/82.04/49.69**；**最佳单模型仅 17.83% Pass@1**（TestEval 上 68–78%） | **泄漏使 branch coverage 膨胀最多（+9.85pp）**；mutation 也不免疫（PLT 50.80 > TestEval 49.69） | **A** |
| ULT 协议 | 函数级 K-query 迭代（第 i 轮给 FUT + 全部历史测试，要求**不同**测试）；**greedy temp 0.0**；≤1,024 新 token；**Cosmic-Ray** + 120s 超时 | **可复现到可逐条对齐的程度** | **A** |
| **SWE-Mutation** | 2,636 变异体 / 800 实例 / 9 语言 | **agentic 变异使平均检出 71.04% → 39.81%** | **A（Findings of ACL 2026）** |
| **TestGen-LLM (Meta)** | 工业部署（Instagram/Facebook，Kotlin） | 75% built / 57% passed reliably / 25% 提升覆盖率；被采纳 73% | **A（FSE 2024 Industry）** |
| SWE-bench Verified | 500 人类验证实例（Prometheus 74.4% 为 2026 最强之一） | 仓库级修复 | A/B |
| **QuixBugs** | 本机 `data/quixbugs/python_programs` = **50 程序**、`python_testcases` 42 JSON | 修复（**AITester 与 LaMAR 的公共基准**） | 数据一手核验 |
| Defects4J | LaMAR Java 侧 24.5%；AdverTest / IntTestGen 主战场 | 修复（Java，非 Python） | A |
| DebugBench | LaMAR 62.1–87.5% | 修复 | A |
| RunBugRun / xCodeEval / LogicEval | 项目转引的规模数字**均未核验** | — | **`[未核验]`** |

**评估方法学趋势（一手核验，直接影响本项目的指标设计）**：
1. **mutation score 必须用标准工具**：TestForge、SPARC、**ULT 均用 cosmic-ray 默认算子集**；
   ULT 还规定了超时（120s）与"击杀"定义（原码过 ∧ 变异码失败）。
   本项目用自研 5 类 AST 变换、均值 4.76 变异体/任务 → **完全不可比**（见 §6.6 / I-06）。
2. **覆盖率单独不可作为有效性证据**——但**理由必须引用正确**：
   - **MUTGEN（TSE 2026, DOI 10.1109/tse.2026.3682975）**：实测存在 **100% 行覆盖仅 4% 变异得分** 的套件；
   - **TestForge 原文**称 coverage 是 "weak proxy for test quality"。

   > **🔴 更正框（2026-10-10，R3 一手核验）**：流传的"**ULT/TOSEM 2026 结论：覆盖率与缺陷检出弱相关**"
   > 是**双重误归属**——(i) **ULT = UnLeakedTestbench 是一个基准**（TOSEM 2026, DOI 10.1145/3805043），
   > **不是相关性研究**；(ii) 真正的相关性批评是 **Zhao, Zhou & Cohen, ISSTA 2026**
   > （DOI 10.1145/3832093, arXiv:2607.22880），11 个 LLM / 13 种设定 / **>100,000 个测试** / Defects4J v3.0，
   > 且其结论**远为精细**：覆盖+变异在**回归（无缺陷代码）**设定下做**跨模型比较**是**有效的**
   > （branch vs raw mutation **r=0.780** @k=10，控制套件规模后），而在**被测代码可能有缺陷**时
   > **不可靠**（此时变异分析根本不适用）。该文还**反驳了 Inozemtseva** 关于"套件规模是强混杂因子"的说法。
   > **对本项目的直接含义**：本项目的场景**正是"被测代码有缺陷"**（缺陷检出），
   > 因此"覆盖率不可作为有效性证据"**成立**——但**必须引用 ISSTA 2026 的限定版结论**，
   > 而不是笼统的"弱相关"。引用笼统版本会被这篇论文本身反驳。
   > *(本报告 §2.2 与 §3.5 初版曾使用笼统表述，已在此更正；`BASELINE.yaml` 的对应 note 亦已同步更正。)*
3. **泄漏必须控制**：ULT 的 PLT/ULT 对照设计是当前最严格的范式；
   本项目合成集无任何泄漏对照设计。
4. **检出必须用强变异体测**：SWE-Mutation 显示 agentic 变异使检出从 71.04% 掉到 39.81%
   ——**约 44% 的"弱变异体下的检出"是虚高的**。本项目的 detection 用 50 模板各 ~3 次重复，属最弱档。
5. **成本必须入表**（TestForge $/file；CoverUp $399/4h/28,690 prompts）。
6. **必须报编译率与通过率**（ICST 2026：≈20% 不编译 / ≈43% 不通过）。
7. **⚠️ 最危险的反例：TEST WARS（arXiv 2501.10200）**——在 **GitBug Java** 上，
   **LLM（TestSpark）在覆盖率与真实缺陷检出上同时输给 EvoSuite（SBST）与 Kex（符号执行），
   仅在 mutation score 上获胜**。**任何"LLM 方法优于传统方法"的主张都必须先处理这一反例**——
   本项目若要主张"逻辑驱动优于纯 LLM 提示"，也必须给出对传统方法的对照。

### 3.6 🔴 引用完整性事件：README 中的 88.35%/35.92% 条目属**错误归属**，必须改写

**被审查对象**：`README.md:15-16` 与 `README.en.md:16-17`

> "（CANDOR，ICST 2026 [待核验]：one-shot Gemini 88.35% vs CANDOR 35.92%，且耗时 45s vs 50h）"
> `CHANGELOG.md:123-127` 记载该引用系 2026-10-09 批次新增，并自标"[待核验]"。

> **⚠️ 本节为审查报告的自我更正（2026-10-10，用户指正 + 复核）**
> 本节初版判定为"文献编造"，**该判定过重**。经复核：**数字是真的，论文也是真的，
> 真正的缺陷是"错误归属 + 未标注第三方复现身份"**。更正后的结论见下。

#### 3.6.1 事实还原

| 项 | 事实 |
|---|---|
| 88.35% / 35.92% 来自哪里 | **IEEE 的一篇独立复现研究**：*Understanding the Effect of Agentic Iteration on LLM-Based Unit Test Generation: A Comparison with Human-Written Tests Using Mutation Testing*（Radaideh & Corriveau），IEEE Xplore 文档 **11655121**。该研究用 mutation testing 对比 one-shot 与 agentic 迭代，报告 **one-shot Gemini 2.5 Flash 达 88.35% mutation score，而 CANDOR 为 35.92%**；同研究还报告了 **one-shot GPT-4o 69.90% vs CANDOR 45.63%**。 |
| CANDOR 是什么 | **真实存在**：*Hallucination to Consensus: Multi-Agent LLMs for End-to-End JUnit Test Generation*（Xu, Wang, Briand, Liu），**TOSEM 2026**，DOI **10.1145/3803418**，arXiv:2506.02943。其原始结论是**多智能体为正**（line/branch/mutation = 0.991/0.970/0.980 on HumanEvalJava）。 |
| **真正的缺陷是什么** | 1. **venue 错误**：把一篇 **IEEE 复现研究**的结论挂到了"CANDOR, ICST 2026"名下——CANDOR 既不是 ICST 2026，也不是该数字的来源论文；<br>2. **身份错误**：未说明这是**第三方复现**在**mutation score**指标上对 CANDOR 的**不利复现结果**，而非 CANDOR 原文的自述；<br>3. **不可追溯**："45s vs 50h" 的耗时对比未给出处。 |
| 对项目叙事的影响 | 该引用被用来论证"跨论文证据已形成共识：手工多智能体编排全面落败"。**方向上并非无据**（IEEE 复现研究确实报告 one-shot 显著优于 CANDOR），但**证据强度被高估**：这是**单一第三方复现**在**单一指标（mutation score）**上的结果，且**与 CANDOR 原文结论相反**，不能表述为"共识"。 |

#### 3.6.2 替换方案（可直接采用）

`README.md` / `README.en.md` 顶部段落建议改写为：

> **为什么不用"手工设计"的多智能体**（2026-10-10 修订）：
> 项目自身 n=261 生死实验（δ=−0.28，vs 检出优先提示协议 `plain_llm_df`）之外，
> 2026 年出现两类**方向相反**的外部证据，二者须并列呈现、不得择一表述为"共识"：
> **(a) 不利证据**：IEEE 独立复现研究（Radaideh & Corriveau, *Understanding the Effect of
> Agentic Iteration on LLM-Based Unit Test Generation*, IEEE Xplore 11655121）在 mutation score
> 上报告 one-shot Gemini 2.5 Flash **88.35%** vs CANDOR **35.92%**、one-shot GPT-4o **69.90%**
> vs CANDOR **45.63%**；
> **(b) 有利证据**：CANDOR 原文（Xu, Wang, Briand, Liu, **TOSEM 2026**,
> DOI 10.1145/3803418）报告多智能体在 line/branch/mutation 上分别达 **0.991/0.970/0.980**（HumanEvalJava）；
> 另有 TestAgent（**FSE Companion 2026**, DOI 10.1145/3803437.3806428）line **92.34%** / mutation **83.69%**。
> **(c) 迄今最强的负面证据**来自 ICST 2026 的复现研究（Konstantinou, Degiovanni & Papadakis,
> arXiv:2601.09695）：在 6 个完整 Java 仓库 / 393 类 / 3,657 方法上，**Plain-LLM
> 49.95/35.33/33.82 全面优于 HITS/SymPrompt/CoverUp/TestSpark**，且请求数不高于 CoverUp
> （11,718 vs 12,264）。**其结论应精确表述为：手工的、工具特定的编排相对强 LLM 单提示 +
> 统一修复环优势有限或无优势——而非"多智能体范式被击败"。**

同时修改 `CHANGELOG.md:123-127`：把"CANDOR（ICST 2026…）"改为上述三方并列表述。

#### 3.6.3 连带发现：项目自己的核验清单已被删除，导致 14 条引用处于"待核验"状态

`CHANGELOG.md:146-150` 载明：本项目引用的 2026 年新文献统一标注 `[待核验]`，
"投稿 / 对外引用前必须逐条打开 arXiv / DOI 一手核验并补全 URL/DOI（核验清单原载于
**已删除的** `docs/review/review_2026_10_09_revision.md` §12.1）"。

即：**项目自己建立的引用核验清单，在 2026-10-10 的"文档清理批次"中被当作孤儿文档删除了**
（`CHANGELOG.md:13-22`）。这使 14 条引用（CANDOR / BOAD / Centaur / TDFlow / ADI / PAGENT /
AdverTest / JavaOracle / TestAgent / Slopsquatting / SWE-Bench Illusion 等）失去了核验载体。

**本次审查对其中若干条做了独立核验，结果分裂**：

| 引用 | 核验结果 |
|---|---|
| **88.35%/35.92%（README 归给"CANDOR, ICST 2026"）** | **❌ 错误归属**：实为 IEEE 复现研究（11655121）；CANDOR 是 TOSEM 2026 且原文结论相反——须改写为三方并列（§3.6.2） |
| **BOAD（ICLR 2026）** | **⚠️ 真实但错位**（arXiv:2512.23631，IBM Research）——是仓库级 SWE 任务解决，不是测试生成 |
| **AdverTest（ISSTA 2026）** | **✅ 真实**（PACMSE vol.3, DOI 10.1145/3832122，fault detection +8.56%/+50.20%）——可用 |
| **TestAgent（FSE Companion 2026）** | **✅ 真实**（DOI 10.1145/3803437.3806428，line 92.34%/mutation 83.69%）——可用 |
| **LANTERN（ICSE 2026）** | **✅ 真实**（DOI 10.1145/3744916.3773227，+22.09% Pass@10 Rust，p=0.0126）——可用，但"pp vs 相对"需读原文 |
| **ADI（PACMSE 2026）** | **✅ 真实**（DOI 10.1145/3797126，63.8% Verified，$1.28/task）——可用 |
| **TwinMem-Agent** | **⚠️ 字面准确但四处严重限定**（200 实例子集 / FSE *Companion* / mini-swe-agent 基线 / 成本低于官方 6–17×）——**18× 成本主张可疑** |
| **"MTTR 降低 85%"** | **❌ 来源是个人 GitHub README**——不可引用（见 §3.3） |
| **VIGIL** | **⚠️ n=12、无基线、单作者**——不可作为证据引用（见 §3.3） |
| **ARC-APR benchmark** | **❌ 疑似不存在** |
| **Defects4J v3** | **❌ 不存在** |
| **RunBugRun（716,900/9 语言）** | **✅ 正确，但仅限 EMSE 2026 期刊版**（arXiv 2023 版为 450,000/8 语言） |
| **xCodeEval（5,068/11 语言）** | **⚠️ 那是 Compact Set（APR 子集）**；完整 xCodeEval 为 25M 样本 / 7,514 问题 |
| **LogicEval（122 逻辑漏洞）** | **✅ 正确**（ACL 2026 Long, pp. 46025–46049） |
| 其余（Centaur / TDFlow / PAGENT / JavaOracle / Slopsquatting / SWE-Bench Illusion 等） | **未核验**——本次审查未逐条追查 |

**结论**：项目已经**正确识别**了引用完整性风险（自标 `[待核验]`），
但**随后删除了核验清单**，导致风险从"待处理"退化为"不可追踪"。
这是本次审查中**最容易被审稿人一击致命**的软性缺陷。

**关于可恢复性（本审查已实测）**：该清单**无法从 git 历史恢复**——
`git log --all -- docs/review/` 与全历史 tree 检索（前 500 提交）均**无命中**，
说明 `docs/review/review_2026_10_09_revision.md` **从未被提交过**（属 gitignore 区或本地文件）。
因此这些引用**必须从头逐条重新核验**。修复清单：

| 动作 | 成本 |
|---|---|
| ① 改写 88.35%/35.92% 引用为三方并列表述（§3.6.2），`README.md` / `README.en.md` / `CHANGELOG.md` 三处 | 30 分钟 |
| ② BOAD 限定适用域为"SWE 任务解决" | 10 分钟 |
| ③ 对剩余 10 条逐条核验（arXiv/DOI 打开、数值逐位对照、标注核对人与日期），无法核验的直接删除 | 1–2 天 |
| ④ `scripts/gates/check_citations.py` 门禁：README/预注册中每条外部引用必须含 `DOI:` 或 `arXiv:` + 括号内数值 | 半天 |

---

## 4. 项目与前沿量化对比矩阵

> 「项目现状」列全部为**一手复算值**，附工件路径。`n_eff` = 经模板聚类校正后的有效样本量。

| 维度 | 2025–2026 前沿 SOTA | 关键来源 | 项目现状（一手复算） | 绝对差距 | 相对差距 | 竞争位置 | 超越路径编号 |
|---|---|---|---|---|---|---|---|
| **被测代码 line coverage** | TestForge **44.4%**（1,157 LOC 真实文件）／CoverUp **63.8%**（CM 套件 425 模块 ≈100k LOC） | arXiv:2503.14713 (B)；FSE 2025 (A) | **69.12%**（QuixBugs 均值）／84.0–93.6%（合成） | — | **看似领先，但不可比**：QuixBugs 单函数玩具程序 vs 真实工程文件；且前沿覆盖率"仅计通过测试" | **不可比**（不同难度域） | P2-L3 |
| **mutation score** | TestForge **33.8%**／ULT 12 模型均值 **40.21%**（cosmic-ray + 120s 超时） | arXiv:2503.14713 (B)；TOSEM 2026 (A) | **72.1%**（自研 5 类算子，**仅 17/50 任务有变异体，均值 4.76 个/任务**） | 不可比 | **不可比**：算子集与变异体数量差 1–2 个数量级 | **不可比**（须重测） | P2-M1 |
| **pass@1 / 编译率** | TestForge **84.3%**；ULT 最佳单模型仅 **17.83%**；ICST 2026 常量 ≈20% 不编译 / ≈43% 不通过 | arXiv:2503.14713 (B)；TOSEM 2026 (A)；ICST 2026 (A) | 合成集 detection 15.8%（n=240）／QuixBugs 45.9%（17/37）；**未报编译率** | −38.4pp（协议不同，仅供参考） | −46% | **落后** | P1-H1 |
| **detection（自有指标）** | 无直接对应；最接近的是 **SWE-Mutation RDR**（最强 71.71）与 **ULT mutation 均值 40.21** | ACL 2026 Findings (A)；TOSEM 2026 (A) | **aitester 45.9% < plain_llm_df 83.8%**（p=0.0005，QuixBugs） | **−37.9pp vs 自家对照臂** | **−45%** | **显著落后于自家纯提示基线** | P1-H1 |
| **多智能体增益** | **分裂，非共识**：负面（Konstantinou ICST 2026：Plain-LLM 49.95 > CoverUp 38.85，且请求更少）；正面（CANDOR TOSEM 2026 line 0.991；TestAgent FSE Companion 2026 line 92.34%/mutation 83.69）；混合（ASTA/ICST 2026：coverage 胜、ESR 平、token 3–4×） | ICST 2026 (A)；TOSEM 2026 (A)；FSE Companion 2026 (A) | **δ = −0.279 / −0.3673 / −0.253（三次复现）**，但**未开任何多智能体组件** | — | — | **已自证为负，但归因错位** | P1-H1 / P1-AS |
| **repair success rate** | **LaMAR 62.1–87.5%（QuixBugs，Qwen3-8B，ASE 2026）** | DOI 10.1145/3832783.3837423 (A) | **90.2%（37/41）** QuixBugs；**39.31%（57/145）** 合成修正口径 | 合成侧 −23pp vs LaMAR 下界 | **协议不同源，暂判"未对齐"** | **待对齐后判定** | P3-R1 |
| **Top-1 / 定位质量** | LaMAR 报告 bug analysis chain 为最关键组件 | ASE 2026 (A) | LLM 定位 Hit@1 **29/37 = 78%**、Hit@3 30/37、MRR **0.797**；谱系 `fl_at_k` 部分命中（12 行 fl_at_1=1.0） | — | **定位质量本身不差** | **持平偏弱** | P3-R2 |
| **通信效率 / 成本** | ⚠️ **latent comms 有渐近证明（O(N²)→O(N)）但无实测成本收益**（LaMAR 消融是定性的；R2 确认无任何论文报告实测 token/$ 节省） | ASE 2026 (A)；R2 §6.1 | 纯文本 token 通信；QuixBugs **16,038 tok/task vs df 1,905**（**41 非测试驱动行**口径 = 8.4×；全 50 行为 **15,253 vs 2,309 = 6.6×**） | 成本高于自家纯提示基线 | **6.6–8.4×** | **落后于自家基线**（但**无前沿成本基线可比**） | P1-AS |
| **cost per task** | TestForge **$0.63/file**；CoverUp **$399 / 4.0h / 28,690 prompts**（CM 套件） | arXiv:2503.14713 (B)；FSE 2025 (A) | **$0.0259/task**（合成单函数，261 行口径） | — | **不可比**（任务粒度差 ~58×） | **不可比** | P2-M2 |
| **逻辑驱动覆盖率** | **GORDIAN**（SMT+LLM，真 SOTA）：覆盖率 **+28.5–115.2%** over 符号执行、token **−91–96%**；**TestTailor**（FSE 2026，Python）：**+5.01% stmt / +4.17% branch over CoverUp @ 成本 −60%**；**Google SpecOps**：规格驱动 **+9.8pp bug detection（p=0.0352）** | PACMSE (A)；FSE 2026 (A)；SpecOps '26 (B) | `spec_compile_rate` **0.4599**（真实基准）；**规约 oracle 实际注入率 36%（18/50）**；注入组检出 31% vs 未注入 57%（**观察性、非因果**） | 同构主张已有正向已发表证据；本项目**净效应未知且不可观测** | **经一手 A/B 测定为负**（−24.4pp, p≈0.04） | **未兑现** | P2-L1 / **P2-L4** / I-07 / I-25 |
| **泄漏控制** | ULT（3,909 去泄漏任务）+ PLT 对照；泄漏使 branch cov 膨胀 **+9.85pp**，mutation 亦不免疫 | TOSEM 2026 (A) | 合成集**无泄漏对照设计**（模板与判分同源） | — | — | **缺失** | P4-B1 |
| **变异体强度** | SWE-Mutation：agentic 变异使平均检出 **71.04% → 39.81%**（≈44% 虚高） | ACL 2026 Findings (A) | detection 在 29 模板 × ~3 重复上测得（最弱档） | — | **约 44% 可能虚高** | **落后** | P2-M1 |
| **SMT 求解效率** | —（未建立前沿基线） | — | z3 前件 SAT/UNSAT/optimize 三通道已实现；超时 2s 上限 | — | — | **有实现、无对照** | P2-L2 |
| **可复现性** | TestForge 提供 OpenHands 集成 + 复现包；ULT 协议逐条可对齐 | (B)/(A) | **方法学世界级**：预注册 + SHA256SUMS + 4 起伪影自曝 + 零 LLM 复算目标 | — | **领先** | **领先** | 保持 |
| **默认安全姿态** | 前沿普遍容器化 + 人类门 | TestGen-LLM (Meta) 工业部署含人工复核 | 宿主 uid 执行 LLM 代码（内核沙箱默认关）、默认自动打补丁、默认无人类门、无 SLSA | — | — | **落后** | P5-S1 |
| **引用完整性** | 顶会论文均带 DOI 与可核验数值 | — | **1 处错误归属（88.35%/35.92% 挂到"CANDOR, ICST 2026"）+ 1 处错位引用（BOAD）+ 13 条 `[未核验]` 转引** | — | — | **重大风险** | **I-21 / I-22** |

### 4.1 竞争位置总判

| 层面 | 位置 |
|---|---|
| **方法学 / 归因严谨性** | **同规模研究代码前 5%**（预注册、伪影自曝、零 LLM 复算、双界披露、聚类校正、ROP 等价检验） |
| **测试生成有效性** | **落后**——显著低于自家纯提示基线（−37.9pp）；且从未在 TestGenEval/ULT 等公共协议上测过 |
| **修复能力** | **待对齐**——QuixBugs 上 90.2% 与 LaMAR 62.1–87.5% 区间重叠，但协议不同源 |
| **逻辑驱动** | **未兑现**——通道未启用；指标口径与注入通道不一致；**但同构主张已有已发表正向证据（Google SpecOps +9.8pp，p=0.0352）**，说明这条路本身是对的 |
| **多智能体** | **已自证为负，但归因错位**；且 2026 文献对此**分裂而非共识**——负面结果只指向"手工的、工具特定的编排" |
| **工程化 / 可复现** | **领先** |
| **外部有效性** | **最大单点风险**——仅 50 个玩具程序 + 一个损坏的 SWE-bench 管道 + 无泄漏对照 |
| **引用完整性** | **重大风险**——1 处编造 + 1 处错位 + 13 条未核验转引，且编造的那条正支撑核心叙事 |

### 4.2 与前沿的"可迁移桥接指标"

本项目的 M1 三指标（`detection_rate`/`repair_rate`/`false_fix_rate`）**与前沿论文的任何指标都不可直接比较**。
若要对标，必须做**指标桥接**。经审查，最可行的两个桥是：

| 桥 | 前沿指标 | 定义 | 为什么可比 | 需要做什么 |
|---|---|---|---|---|
| **B-A** | **SWE-Mutation 的 RDR**（Relative Detection Rate） | 生成测试对"对抗性变异体"的检出比例（最强系统 71.71） | 与 `detection_rate` 语义最接近：都是"测试能否区分错误实现与正确实现" | 把本项目的 detection 在**agentic 变异体**上重测（当前用弱变异体，按 SWE-Mutation 的 71.04→39.81 结论，**当前 detection 可能虚高约 44%**） |
| **B-B** | **ULT 的 mutation score** | cosmic-ray 默认算子 + 120s 超时 + 严格击杀定义（原码过 ∧ 变异码失败） | 协议完全公开、逐条可复现，且 ULT 只做函数级自包含代码——**与本项目 QuixBugs/合成集的粒度最接近** | 接入 cosmic-ray，在 ULT（3,909 任务）上直接跑，报 accuracy/statement/branch/mutation 四指标 |

**重要提醒（来自 R1 研究的结构性警告）**：任何"超过 SOTA"的主张都必须先完成上述桥接之一，
否则不可比。**最省力的路径是 B-B**：ULT 与本项目粒度相同（函数级、自包含），
且 ULT 的协议公开到"greedy temp 0.0 / ≤1,024 token / 120s 超时"的程度。

---

## 5. 超越前沿方法设计

> 编号规则：**P<序号>-<子方向><序号>**。
> 每条含：技术路径 / 差异化点 / 理论基础 / 预期提升（量化+置信度）/ 实验验证 / 反事实推演 / 里程碑。

### 5.1 测试生成超越路径

#### 路径 P1-H1｜载荷等价实验：把 −28pp 从"编排"分离到"载荷"（**最高优先级，先做**）

| 项 | 内容 |
|---|---|
| **技术路径** | 保持节点集合、调用次数上限、再生成上限、双门开关**全部不变**，只把 Generator 收到的载荷从 `full`（plan JSON 含 `expected_output`/`edge_cases`/`boundaries` + 现存断言 + RAG + CFG + 变异反馈）降到 `df_parity`（仅被测代码 + 检出优先协议文本）。实现落点：`src/agents/generator.py:395-430` 的 `build_query`，新增 `GENERATOR_PAYLOAD ∈ {full, df_parity}` 开关并**入 `_env_snapshot_keys`** |
| **差异化点** | 前沿（TestForge）在**加**上下文（覆盖缺口反馈）；本路径先做**减**上下文的因果实验。若 H1 成立，则"提升检出"的动作是**减法**而非加法——这与 ADR-0016"不做编排加码"的决策方向一致，也与 TestForge"把未覆盖行**全量**给 agent 而非子集"（同样是控制载荷形状）形成互补对照 |
| **理论基础** | (1) **oracle-from-implementation**：plan 的 `expected_output` 由缺陷代码派生 → 断言复制缺陷行为 → 缺陷代码上全绿 → 检出被系统性抹掉（`flags.py:255-274` 已自述该机制）；(2) **上下文稀释**：载荷越长，检出优先指令的相对权重越低；(3) **A1 消融的旁证**：剥离 `expected_output` 后 +5.5pp 且三项过程指标同向（`specific_red` 19→21、`over_red` 21→17），方向正确但幅度小 |
| **预期提升** | `df_parity` 相对 `full` 的 detection **+20pp 以上**（QuixBugs 41 任务；从 45.9% → ≥66%）。**置信度：中**（依据：A1 的 +5.5pp 方向为正；df 臂在同协议下已达 83.8%；但 A1 只动了一个字段，本路径动整个载荷，效应可能不单调） |
| **实验验证** | 基准：QuixBugs 41 个有 gold 的缺陷程序（`BASELINE.yaml:291-298` 口径）。设计：单变量 A/B，seed 42，**cold cache**（`AITESTER_LLM_CACHE=0`），`TEMPERATURE=0`，`LLM_THINKING_MODE=disabled`。主终点：detection 配对差（McNemar + BH-FDR + 贝叶斯 ROPE ±5pp + 模板级聚类校正）。判别规则：≥+20pp 且与 df 臂 83.8% 差距不再显著 → H1 成立；差异 ≤5pp（ROPE 内）→ H1 否证，转 H2（拓扑消融）。**先做零 LLM 前置**：用 LLM 缓存 `prompt` 字段做"载荷长度 × over_red"关联分析，0 预算先判功效。成本：单臂 ≈20 分钟 / ≈0.7M token |
| **反事实推演** | 若 df 臂（纯提示）也采用 `df_parity` 载荷 → **它就是 df 臂本身**，此时本项目仅剩"协议文本 + 归因方法学"。**护城河不在检测，在归因**：本项目是唯一同时具备 (a) 预注册主终点、(b) 4 起测量伪影的零 LLM 复现、(c) 聚类校正与 ROPE 等价检验、(d) 全部工件入库的同类系统。这条护城河**前沿论文不提供**，因为它们的贡献是方法而非评估基础设施 |
| **里程碑** | 短期（1 周）：零 LLM 载荷关联分析 → 中期（2–3 周）：单变量 A/B 定案 → 长期：若 H1 成立，把 `df_parity` 设为默认载荷 |

#### 路径 P2-L1｜把"逻辑驱动"从 (d) 类升级到 (a) 类：结构约束优先于表达式约束

| 项 | 内容 |
|---|---|
| **技术路径** | 三件事同时做：<br>① **打开并单独度量**现有通道——新增行级指标 `spec_oracle_injected`（bool）、`spec_oracle_verdict`（`pass`/`fail_on_buggy`/`fail_on_fixed`/`not_run`），进 `BASELINE.yaml` `metrics_schema`；在 QuixBugs 41 任务上跑 `SPEC_ORACLE_EXEC_ENABLE=true` A/B。<br>② **对齐度量通道与注入通道**：把 `compile_readiness`（`spec_ir_v2.py:571-580`）的判据与 `_compile_single_clause`（`:195-238`）统一——目前前者**不做标识符绑定检查**，后者做，故 `spec_compile_rate` 是**上界而非实际注入率**。<br>③ **引入结构约束**（SPARC 式）：把 CFG 路径/分支条件作为 Generator 的**一等输入**写入载荷，替代"LLM 先产表达式、再反过来约束测试"的逆向链路 |
| **差异化点** | 前沿 SPARC 用"CFG + Operation Map + 路径定向合成"在 **C** 上实现 +31.36% line / +20.78% mutation；本项目把它迁到 **Python**（CFG 已由 `src/tools/control_flow.py` 提供），且**叠加**已有的检出优先协议与双门——形成"结构约束 × 检出协议 × 特异性门"三者正交组合，SPARC 仅有第一项 |
| **理论基础** | SPARC 的 "leap-to-code failure mode" 诊断：LLM 在未被结构/约束 grounding 时过早产出代码，导致不可编译、低分支覆盖、语义无关断言。本项目的对应症状已被自身数据量化：首轮 `over_red` **30/50（60%）**、`specific_red` 19/50（38%），且**臂内 over_red 组 detection=0%、specific_red 组 detection=100%**——"红得是否特异"几乎完全决定检出，而特异性正是"是否 grounded 在正确路径上"的代理 |
| **预期提升** | ① 单独度量后，若确定性 oracle 通道贡献 >0，则"逻辑驱动"首次获得**可归因的检出增量**（无论正负都是可发表结果）；② 结构约束路径目标：`over_red` 占比从 60% 降到 ≤35%，detection **+10–18pp**。**置信度：中**（SPARC 在 C 上给出 +20–31pp，但 Python 无内存管理复杂度、CFG 更简单，迁移效应大概率衰减） |
| **实验验证** | 基准：QuixBugs 41 任务 + 合成集 87 任务（双层）。对照：`SPEC_ORACLE_EXEC_ENABLE` off/on；结构约束 off/on；SPARC 式载荷 vs 现有载荷。指标：detection、`over_red` 占比、`spec_oracle_verdict` 分布、`spec_compile_rate`、token。统计：McNemar + BH-FDR + ROPE。**零 LLM 先行**：`spec_oracle_verdict` 通道可完全离线重放已有 427 个真实 Planner 规约（`BASELINE.yaml:500-506` 的离线可达性数据即为此基础） |
| **反事实推演** | 若前沿（TestForge）也接入 CFG 路径定向 → 它的载荷同样变结构约束。此时本项目剩余优势是：(a) **确定性 oracle 通道**（不依赖 LLM 的机器锚点，TestForge 没有）；(b) **特异性门**（用 gold fixed 对照判定"红得是否特异"，TestForge 无此机制）；(c) **可归因的失败分类学**。**护城河 = 确定性锚点 + 反事实判定**，而非"逻辑"这个词 |
| **里程碑** | 短期（2 周）：`spec_oracle_injected`/`spec_oracle_verdict` 落地 + 零 LLM 离线重放定案 → 中期（1–2 月）：CFG 结构约束载荷 A/B → 长期（3–6 月）：把 SMT 从"前件见证"扩展到"后件反例生成" |

#### 路径 P2-M1｜用标准变异工具重测，让 mutation score 可比

| 项 | 内容 |
|---|---|
| **技术路径** | 接入 **cosmic-ray**（TestForge / SPARC 均用它，是事实标准）作为 `mutation_score` 的权威计算器，保留自研算子集作为**补充信号**而非主指标；对每个任务保证 ≥30 个变异体（当前均值 4.76）；把 `mutation_score` 的分母从"全部任务（含无变异体的 33 行记 0）"改为"有变异体的任务"并**并列披露两者** |
| **差异化点** | 前沿报告 mutation score 时都明确工具与算子集；本项目当前的自研 5 类算子既**数量级不足**又**不可比**，是"指标看起来漂亮（0.976）但鉴别力为零"的根因 |
| **理论基础** | 变异得分是"测试套件能否区分代码行为差异"的**唯一客观代理**（TestForge 原文：coverage 是 weak proxy，mutation 更能反映抓 bug 能力）。变异体数量 <10 时，得分的置信区间宽到无判别力 |
| **预期提升** | 指标**可信**（而非提升）。预期实测值会**低于**当前 0.721：因为当前 33 行无变异体任务被记 0 参与均值，且算子过弱。**置信度：高**（这是工程改造，不是方法假设） |
| **实验验证** | 同批工件离线重算（零 LLM 成本）：对 50 个 QuixBugs 任务 × 30+ 变异体，比较自研算子 vs cosmic-ray 的得分差异与排序一致性（Spearman）。若两者排序显著不一致 → 证明当前指标不可用于系统间比较 |
| **反事实推演** | 无护城河影响——这是**可比性修复**，不是竞争优势。但它是投稿的**必要条件**：审稿人一定会问"你的 mutation score 用什么工具算的" |
| **里程碑** | 短期（1–2 周，纯离线） |

### 5.2 多智能体协作超越路径

#### 路径 P1-AS｜自动搜索编排 vs 手工编排（正面回应 BOAD 路线）

| 项 | 内容 |
|---|---|
| **技术路径** | 把现有节点与开关**算子化**为一个可搜索空间：`{Planner on/off} × {载荷 full/df_parity/structure} × {Debugger 轮数 1/2/3} × {多候选 1/3} × {RAG on/off} × {变异顾问 on/off} × {双门 on/off}`，用 bandit/贝叶斯优化在**小网格**（≤64 组合）上按 detection/token 双目标搜索；对照臂 = 当前手工配置。**关键**：所有组合必须入 `env_snapshot`（P0-2 门禁） |
| **差异化点** | CANDOR 式"one-shot 打败手工多智能体"与本项目的 −28pp 是**同一现象的两次观测**；BOAD 式"自动搜索能超越更大单模型"给出了**唯一的反例路径**。本项目的独特资产是：**已经有一套完整、可复现、可消融的编排基础设施 + 世界级的评估方法学**——这正是"搜索"所需的地基，而 BOAD 类工作通常缺少本项目这种伪影防控纪律 |
| **理论基础** | 手工编排的失败不是"多智能体范式"的失败，而是**在无梯度的离散设计空间里手工试错**的失败。若把编排视为超参数搜索问题，则"节点数量"不再是先验主张，而是搜索结果。项目自己的 `docs/design/mas_compilation.md` 已把该路线标为探索性 Proposed，**本文给出首个本地证据** |
| **预期提升** | 找出 ≥1 个组合使 detection **≥ df 臂 83.8%** 且 token **≤ df 臂 2×**（即"编排不再劣于纯提示"）。**置信度：低–中**（若 BOAD 类结果可迁移则可达；若 CANDOR 类结果更普遍则大概率失败——**但失败也是可发表的高价值负结果**） |
| **实验验证** | 预算：小网格 64 组合 × 41 任务太多；采用**两阶段**——阶段 1 在 12 任务子集上用 bandit 搜 32 组合（≈2M token），阶段 2 把 Top-3 在 41 任务全量确认。主终点：`detection`；次要终点：`token/task`、`over_red` 占比。必须预注册搜索空间与停止规则 |
| **反事实推演** | 若前沿也做自动搜索 → 双方回到"谁的评估更可信"的竞争。本项目在此**领先**（预注册 + 伪影防控 + 全工件入库）。另一层护城河：**搜索出的拓扑是可解释的结构知识**（"哪种载荷/轮数组合有效"），而单模型的能力提升不可解释 |
| **里程碑** | 短期（1 月）：算子化 + 搜索脚手架 → 中期（2–3 月）：阶段 1 搜索 → 长期（6 月）：Top-3 确认 + 写成"手工 vs 自动编排"的对照论文 |

#### 路径 P1-TO｜拓扑消融：禁 debugger 的干净对照（H2）

| 项 | 内容 |
|---|---|
| **技术路径** | 若 H1 否证，则测 H2：`ENABLE_DEBUGGER=false` + `ENABLE_PLANNER` 不变，其余不变——分离"修复环反噬检测"（环路消耗预算 / 中途改写代码使测试语义漂移） |
| **差异化点** | 项目已有该消融开关（`ENABLE_DEBUGGER`），但**从未在真实基准上跑过干净对照** |
| **理论基础** | `patch_applier` 会**改写被测代码**（`nodes.py:1762-1763`）。若测试在补丁后被重新执行，生成测试与"被检出的缺陷"之间的对应关系可能被破坏——这是"环路反噬"的机制 |
| **预期提升** | 判定性结果（是/否）；若 H2 成立，detection 提升量级与 H1 相当（+15–25pp）。**置信度：低**（df 臂无修复环，但它同时也无 Planner，故不能单独归因） |
| **实验验证** | 同 H1 协议，单变量 `ENABLE_DEBUGGER` on/off，41 任务，cold cache |
| **反事实推演** | 若成立，则"自修复"与"检出"存在**结构性冲突**——这是本项目最有价值的科学发现之一（"修得越好，检得越少"），远超工程优化价值 |
| **里程碑** | 短期（1 月，H1 之后立即做） |

### 5.3 自修复超越路径

#### 路径 P3-R1｜落盘优先：把"补丁没落盘"从最大漏点变成可度量通道

| 项 | 内容 |
|---|---|
| **技术路径** | ① 新增行级 `patch_apply_failure_class`（`anchor_miss` / `syntax` / `multi_func_conflict` / `fence_residue` / `other`）——把 apply 失败**分类**而非二值化；② **在写盘处**（`src/graph/nodes.py:1762` 附近，而非测量处）调用 `normalize_patch_text`，使 `state["patch"]` 从源头干净；③ 对 `anchor_miss` 类走确定性重试（复用 `deterministic_repair.py`） |
| **差异化点** | 项目当前把瓶颈归因为"生成侧合成质量"（ADR-0024）；**本审查的重算表明最大漏点在落盘侧**（266 有补丁文本 → 144 落盘 → 115 gold 正确；接受侧 CPR 84.5%）。这是**归因方向的修正**，且修复是工程性的、零 LLM 成本 |
| **理论基础** | 补丁管线的最优策略是**先最大化"可验证候选"的数量**，再优化候选质量。当前管线在"数量"环节损失 ≈46%，而"质量"环节已达 84.5% 精度——**先修数量，收益更大** |
| **预期提升** | 落盘成功率 **54% → ≥85%**（对齐 `plausible` 语义修正后的上界）；若下游 correct 率不变（保守假设），repair 从 39.31% → **≈60%**（+21pp）。**置信度：中–高**（机制清楚、零 LLM 可离线验证大部分；但部分 apply 失败是真实语义冲突，无法机械修复） |
| **实验验证** | **先做零 LLM 离线重算**：用 `normalize_patch_text` 重判全部 476 个带补丁行的 `plausible`，量化 `plausible` 从 144→? ；再在 QuixBugs 41 任务上跑 A/B（开关：`PATCH_WRITE_NORMALIZE_ENABLE`）。指标：`plausible` 率、`patch_precision`（修正语义后）、repair、CPR、IDR、成本 |
| **反事实推演** | 若前沿（LaMAR/Agentless）本就采用"最小编辑 + 严格锚定"，则它们天然没有这个漏点——本项目修完只是**追平**，不构成优势。**真正的护城河是 `patch_abstain` 弃权门**（精确率 85.97%，前沿无对应机制）：弃权 = "我知道这个补丁不可信"的能力，在人类监督场景下比"多修一个"更有价值 |
| **里程碑** | 短期（1 周，离线重算 + 写盘归一化）→ 中期（1 月，失败分类学 + 确定性重试）→ 长期：把 `plausible` 语义重命名为 `patch_written`，另设 `patch_wellformed`（清理后 `ast.parse` 通过） |

#### 路径 P3-R2｜让补丁生成**消费**定位信号（修复负相关）

| 项 | 内容 |
|---|---|
| **技术路径** | 当前 ADR-0024 观测到 **P(correct \| FL 命中)=15.79% < P(correct \| FL 未命中)=64.71%**——定位越准修复越差。机制：整文件重写**不消费**定位。改为**局部编辑强制消费**：补丁必须以"改哪个函数/哪几行"为输出契约，整文件重写降级为兜底（`EDIT_INTENT_ENABLE` / `LOCALIZED_EDIT_ENABLE` 已有实现，R4 已测出**阴性**——但 R4 的阴性是"函数级约束在单函数任务上空洞"，**恰好说明需要在多函数任务上测**） |
| **差异化点** | LaMAR 的消融表明 **bug analysis chain 是最关键组件**——即"诊断"必须真正驱动"修复"。本项目已把诊断做出来了（LLM 定位 Hit@1 78%、MRR 0.797），**但没有接到修复的输入端** |
| **理论基础** | 修复是**条件生成**：`P(patch | bug_location, bug_semantics)`。当前实现近似 `P(patch | 全文)`，定位信号被稀释。局部编辑把条件收紧到目标函数，理论上应提升精度 |
| **预期提升** | 定位命中组的 correct 率**反超**未命中组（当前 15.79% vs 64.71%，目标反转）；repair **+8–15pp**。**置信度：中**（R4 的函数级 A/B 阴性，需先解决"单函数任务上约束空洞"的测量问题——改用跨文件/多函数任务子集） |
| **实验验证** | 基准：合成集 Level 2/3 跨文件任务（`data` 中 8 个跨文件任务 + `cross_file_ab_level3` 批次已有的 50 个跨文件任务）+ QuixBugs 多函数程序。对照：`EDIT_INTENT_ENABLE` off/on、`LOCALIZED_EDIT_ENABLE` on。**必须先在多函数子集上跑**（R4 的阴性是单函数子集的产物） |
| **反事实推演** | 若前沿采用 Agentless 式"定位→最小编辑→验证"，本路径等于追平其核心思想。本项目剩余差异是**弃权门 + 证据等级 + test-hacking 守卫**（三层防错修复），前沿少见 |
| **里程碑** | 中期（1–2 月） |

### 5.4 逻辑驱动超越路径

#### 路径 P2-L2｜SMT 从"前件见证"扩展到"反例驱动的非终止检出"（**本报告的技术亮点**）

| 项 | 内容 |
|---|---|
| **技术路径** | 当前 `spec_smt.py` 只做三件保守的事：前件 SAT 见证、前件数值 optimize、后件自身一致性 UNSAT。**新增第四件：`test_hang`（非终止）作为独立检出通道**——<br>① 在判分层用 per-test timeout 把"测试挂起"从"红"里拆出来（`experiments/_m1_metrics.py` 的 `_run_pytest_in_tmp` 已返回 `None` 表示超时，但该信号被 `detection_gates.py:69-93` 丢弃）；<br>② 判定规则：**测试在 buggy 上超时 ∧ 在 gold fixed 上有限时间通过 → 记为检出（`detection=hang_detected`）**。这是**可靠且确定性的**非终止 oracle；<br>③ 用 `pytest-timeout` / signal.alarm 在**测试侧**加有界执行，把"挂起"变成"快速失败"而非进程级 kill |
| **差异化点** | 前沿把 hang 当噪声（测试超时 = 坏测试）；本路径把它当**信号**。且这恰好击中项目**已量化但未解决**的切片：4 个 QuixBugs 任务的缺陷实现**永不返回**（`bitcount` 的 `n ^= n - 1` 对任何 n 不终止），当前以 `detection=None` fail-closed 处理；而 `over_red` 的 30/50 里"相当一部分"就是挂起（`BASELINE.yaml:454` 自述"再好的 prompt 也无法让挂起的测试变红；需测试侧超时判定"） |
| **理论基础** | 终止性是**可判定的**程序性质（对给定输入），且"buggy 不终止 vs fixed 终止"是一个**合法的 fail-to-pass 信号**（与"断言失败 vs 断言通过"在语义上同构：都是可观测的行为差异）。当前把它排除在检测之外，是**人为丢失了一个确定性通道** |
| **预期提升** | ① 4 个 `None` 任务变为可判定 → detection 分母从 37 恢复到 41；② `over_red` 中属于 `over_red_hang` 的部分（估 8–15 个任务）转为 `specific_red`（若 fixed 侧终止）或明确的 `hang_detected`；③ detection **+6–12pp**（保守：仅回收当前被记为 None/over_red 的挂起类）。**置信度：中–高**（机制确定、零 LLM；幅度取决于挂起任务占比，需先做分类学统计） |
| **实验验证** | **第一步零 LLM**：对现有 50 个 QuixBugs 任务的全部 `generated_test` 工件做离线分类——用「buggy 侧 rc/超时状态 × fixed 侧 rc/超时状态」四格交叉，量化 `over_red_hang` 的真实占比。第二步 A/B：`TEST_HANG_DETECTION_ENABLE` off/on，41 任务。指标：detection、`over_red` 五值分布（见 P1-F1）、`None` 行数、token |
| **反事实推演** | 若前沿也采用"hang 即检出" → 双方检出率同步上升，本项目的相对位置不变。**但本项目独有优势**：它**已经**有 gold fixed 对照 + 双门 + 三段判定（F2P），加上 hang 通道后构成**四通道检出协议**（断言红 / hang / 规约 oracle / 变异体），而 TestForge 类系统只有第一通道。**护城河 = 多通道检出的正交性** |
| **里程碑** | 短期（1 周，零 LLM 分类学）→ 短期（2 周，执行层 timeout 语义 + A/B） |

#### 路径 P2-L3｜规格语言表达力升级：从命题表达式到关系/量化契约

| 项 | 内容 |
|---|---|
| **技术路径** | 当前受限 DSL（`spec_ir_v2.py:63-124`）**无量化、无关系、无时序**。实测：`xs != None implies len(xs) > 0` 因 `implies` 是未知标识符被拒；`all(x > 0 for x in xs)` 通过 `is_expression_clause` 但语义编译受限。升级三步：<br>① **表达式层**：白名单加入 `implies`/`==>`（编译为 `(not A) or B`）、集合运算 `set`/`in`、`all/any` 生成式的受限编译；<br>② **量化层**：支持 `forall x in domain: P(x)` 形式，编译为 `hypothesis` 参数化 + 有限域枚举（`hypothesis` 已在 `[formal]` extra 中）；<br>③ **关系层**：支持"输入-输出关系"子句（如 `r == sorted(xs)` 已在样本中），并把它绑定到**属性测试模板**（`docs/design/property_template_route_skeleton.md` 已有骨架） |
| **差异化点** | SPARC 证明"结构约束"有效；本路径补的是**语义约束**（量化与蕴含），二者正交。项目已有 hypothesis 依赖，**零新依赖成本** |
| **理论基础** | 可判定性：加入全称量化后进入**一阶逻辑**，一般不可判定；但对**有限域**（列表长度上界、整数区间）可判定，且 hypothesis 的随机采样提供了"有界验证"的实用替代。**必须在文档中显式声明复杂度上界与不可判定边界**——这正是当前缺失的"可判定性论证" |
| **预期提升** | `spec_compile_rate` 从 0.47–0.52 → **0.70+**（表达式层 + 量化层的白名单扩展，预期恢复当前被 `parse_failed`/未知标识符丢弃的 18.7%（`BASELINE.yaml:506` 的 compiler_nonempty_end_to_end）中的一半以上）。**置信度：中**（工程性强，但需重跑 LLM 让 Planner 产出新形态——**或先用存量 427 个规约离线重测，零成本**） |
| **实验验证** | **零 LLM 先行**：对存量 427 个真实 Planner 规约（`BASELINE.yaml:500-506` 已给出离线可达性基线：含 `*_expr` 28.8%、过 AST 90.0%、过白名单 73.3%、端到端非空 18.7%）重跑新的编译链，量化提升。然后 A/B：`SPEC_IR_DSL_ENABLE=true` + 新文法 vs 旧文法 |
| **反事实推演** | 若前沿用 Dafny/JML 级规格（更强表达力），本 DSL 仍是玩具。**因此不要在这条路上做"表达力军备竞赛"**——本项目的差异化应在**评估与归因**，表达力只需达到"能产生可归因的确定性检出"这一门槛 |
| **里程碑** | 中期（2–3 月） |

### 5.5 评估与外部有效性超越路径

#### 路径 P4-B1｜指标桥接：从"自有 detection"到"前沿可比协议"（**投稿的前置条件**）

| 项 | 内容 |
|---|---|
| **技术路径** | 三选一或全做：<br>① **桥 B-B（推荐先做，最省力）**：在 **ULT（UnLeakedTestbench，3,909 函数级 Python 任务）** 上直接跑本系统 — ULT 粒度（函数级、自包含、复杂度 ≥10）与本项目 QuixBugs/合成集**最接近**，协议公开到 `greedy temp 0.0 / ≤1,024 new tokens / cosmic-ray + 120s 超时 / 严格击杀定义（原码过 ∧ 变异码失败）`，可直接对齐。报告 **accuracy / statement coverage / branch coverage / mutation score** 四指标，对标 ULT 12 模型均值（41.32 / 45.10 / 30.22 / 40.21）与最佳单模型（**17.83% Pass@1**）。<br>② **桥 B-A**：把 detection 在 **agentic 变异体**上重测（SWE-Mutation 协议），报 **VRR / RDR**，对标最强 71.71。<br>③ **TestGenEval 全量**：pass@1 ≥84.3 / line ≥44.4 / mutation ≥33.8 @ ≤$0.63/file（对标 TestForge）。**注意许可 CC BY-NC 4.0 的商用限制**。 |
| **差异化点** | 前沿系统在**单一基准上刷分**；本项目的资产是**多协议可比能力 + 泄漏对照设计**。若能在 ULT 上同时报告**去泄漏/含泄漏双轨**（ULT vs PLT），即复现 ULT 论文最有价值的对照设计（泄漏使 branch coverage 膨胀 **+9.85pp**，mutation 亦不免疫：PLT 50.80 > TestEval 49.69），这在国内同类工作中极少见 |
| **理论基础** | 本项目的 detection 是"生成测试能否在缺陷码上变红"——与 **mutation score**（测试能否杀死人为注入的缺陷）语义同构，与 **RDR**（能否检出对抗性变异体）更同构。因此该桥**不是勉强的换算，而是同一概念的两种实现**；差异只在"缺陷来源"（真实缺陷 vs 注入变异）与"难度"（弱变异 vs agentic 变异） |
| **预期提升** | **首次获得可对外比较的绝对数值**。预测：在 ULT 上 accuracy 可能**高于** 12 模型均值 41.32%（因本项目有 gold 对照与双门），mutation 可能接近或略低于 40.21%（因当前变异器弱）。**置信度：中**（ULT 无泄漏且复杂度 ≥10，比 QuixBugs 难；本系统在复杂度 ≥10 的函数上从未测过） |
| **实验验证** | 基准：ULT 3,909 任务（先做 200 任务子集定标，再全量）。对照：ULT 论文的 12 模型均值 + 最佳单模型。指标：四指标齐报。统计：与 ULT 基线做配对比较（同任务同协议）。**成本估计**：3,909 任务 × ~16k token/task ≈ **63M token**（按本项目 QuixBugs 成本外推），需预算决策；建议先做 200 任务子集 |
| **反事实推演** | 若前沿（TestForge/CANDOR）也跑 ULT → 双方在同一协议上可比，竞争回到方法本身。本项目的护城河仍是**评估基础设施**：ULT/PLT 双轨泄漏对照 + 预注册 + 伪影自曝，这些是"基础设施贡献"，前沿论文不做。**这也提示一个新的、更诚实的贡献定位：把本项目做成"Python 测试生成/修复的可信评估平台"，而不是又一个生成器** |
| **里程碑** | 短期（2 周）：ULT 加载器 + 200 任务定标 → 中期（1–2 月）：全量四指标 + PLT 对照 → 长期：作为公开 leaderboard 发布 |

#### 路径 P2-L4｜规格合成与保真审计：把"逻辑驱动"的靶子从语法改成语义（**R3 核验后新增，战略优先级最高的逻辑路径**）

| 项 | 内容 |
|---|---|
| **技术路径** | 三步：<br>① **新增 `spec_faithfulness_audit` 指标**——判定"LLM 写出的规约是否真的刻画了目标函数语义"。实现：对同一函数（a）用规约 oracle 判定 gold fixed 实现 → 应通过；（b）对**变异体**（至少 30 个，接入 cosmic-ray）判定 → 应当至少杀死一部分；（c）对原始 buggy 实现判定 → 应当失败。三者都满足才算"忠实"。<br>② **把 `spec_compile_rate` 与"忠实率"并列**——当前 0.47 的"可编译率"是语法指标；真实的"逻辑驱动"价值应由"忠实率 × 注入率 × 检出贡献"衡量。<br>③ **在规格不忠实时弃权**——接 `patch_abstain`：规格审计不通过 → 该任务标记弃权，不生成补丁（与 I-08/P1-8 的弃权设计合并）。 |
| **差异化点** | 2026 的 SOTA 在**语法侧**已经很挤（GORDIAN 用 ghost code 让求解器处理难片段；NeuroTestGen 的纯符号消融已达 92.35% line，**SMT 仅贡献 +0.56pp**），但在**语义侧几乎无人做审计**：SWE-PROOF 报告 **只有 56% 的 agent 自写规格能通过审计**——即**当前所有"规格驱动"系统的结论都建立在一份可能不忠实的规格上**。本项目做审计，是在填补一个**被公认存在但无人测量**的空白 |
| **理论基础** | **SWE-PROOF（arXiv:2609.21190v2, 2026-09）**：把 SWE-bench Verified 转为 500 个形式化验证 issue，证明——**约 25% 的"测试通过"LLM 补丁存在反例**；**忠实的形式化规格把解决率从 85% 提升到 95%，而自然语言规格做不到**（说明价值来自"形式化 + 忠实"，而非"写规格"这个动作本身）；规格在未解决 issue 上失败率 92%、在已解决上 51%。**GORDIAN（PACMSE, DOI 10.1145/3832126）**证明 SMT+LLM 在**覆盖率**上可 +28.5–115.2% 且 token 削减 91–96%——但那是语法/求解效率侧。语义侧的缺位正是本路径的机会 |
| **预期提升** | ① `spec_faithfulness_audit` 首次给出本项目"逻辑驱动"的**真实**质量（预测：显著低于 `spec_compile_rate` 0.47，可能落在 **0.15–0.35**——因为"能编译"远弱于"忠实"）；② 若审计通过的任务上 detection 显著高于审计不通过的任务，则**首次证明逻辑通道的检出贡献**；③ 若与弃权联动，`false_fix` 有望从 87.2% 下降。**置信度：中**（指标定义可立即实现、零 LLM；但"忠实率能否预测检出"是经验问题） |
| **实验验证** | **零 LLM 先行（立即可做）**：对存量 427 个真实 Planner 规约（`BASELINE.yaml:500-506` 已有离线可达性基线：含 `*_expr` 28.8%、过 AST 90.0%、过白名单 73.3%、端到端非空 18.7%）跑忠实度审计，给出忠实率分布 + 与 detection 的相关性。**这一步零 token 成本，却是全报告投入产出比最高的一步。** 第二步 A/B：`SPEC_FAITHFULNESS_AUDIT_ENABLE` off/on + 弃权联动 |
| **反事实推演** | 若前沿（SWE-PROOF/GORDIAN）也做规格审计 → 双方都在语义侧竞争。**本项目的独特资产**：(a) 已有一份**真实的、由 LLM 在真实任务上产出的**规约语料（427 条），可直接做审计分布研究；(b) `patch_abstain` 已有 85.97% 弃权精确率，可与审计联动。**护城河 = 在真实 LLM 产出语料上做审计的实证研究，这是 SWE-PROOF 用形式化基准做不到的** |
| **里程碑** | 短期（**本周，零 LLM**）：审计指标实现 + 427 条规约的忠实率分布 → 中期（1 月）：审计 × 检出相关性 + 弃权联动 A/B → 长期（3 月）：把"规格保真"作为论文主线论点 |

### 5.6 超越前沿方法汇总表

| 路径编号 | 子方向 | 技术路径 | 前沿参考 | 差异化点 | 目标指标 | 预期提升 | 置信度 | 验证基准 | 对照组 | 里程碑 | 反事实风险 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **P1-H1** | 测试生成 | 载荷等价单变量 | TestForge（加上下文）／ADR-0016 | 先做**减**上下文的因果实验 | detection | **+20pp** | 中 | QuixBugs 41 | df / full | 1–3 周 | 若前沿也减载荷 → 仅剩归因护城河 |
| **P1-AS** | 多智能体 | 自动搜索编排小网格 | BOAD `[未核验]`／CANDOR `[未核验]` | 用已有的可消融基础设施做搜索地基 | detection ≥83.8% ∧ token ≤2× df | 定性 | 低–中 | QuixBugs 12→41 | 手工配置 | 1–3 月 | 若搜索也无效 → 强负结果（可发表） |
| **P1-TO** | 多智能体 | 禁 debugger 拓扑消融 | — | 首次干净对照 | detection | 判定性 | 低 | QuixBugs 41 | debugger on | 1 月 | 若成立 → "修得越好检得越少"科学发现 |
| **P2-L1** | 逻辑驱动 | 打开+单独度量 oracle 通道；CFG 结构约束 | **SPARC +31.36%/+20.78%** | 结构约束 × 检出协议 × 特异性门三者正交 | `spec_oracle_injected`；`over_red` 60%→≤35% | +10–18pp | 中 | QuixBugs+合成 | oracle off/on | 2 周–3 月 | 若前沿也接 CFG → 靠确定性锚点+反事实判定 |
| **P2-L2** | 逻辑驱动 | hang 作为独立检出通道 | —（前沿当噪声） | 把超时从噪声变信号；构成四通道检出 | detection | **+6–12pp** | 中–高 | QuixBugs 41 | hang 通道 off | 1–2 周 | 若前沿也做 → 靠多通道正交性 |
| **P2-L3** | 逻辑驱动 | DSL 表达力升级（蕴含/量化/关系） | Dafny/JML 级规格 | 不做军备竞赛，只到"可归因"门槛 | `spec_compile_rate` 0.47→0.70 | +0.23 | 中 | 存量 427 规约（零 LLM） | 旧文法 | 2–3 月 | 表达力永远拼不过 Dafny → 不在此竞争 |
| **P2-M1** | 评估 | 接入 cosmic-ray | TestForge / SPARC | 指标可比性修复 | mutation score | 值可能下降但**可信** | 高 | 50 QuixBugs（离线） | 自研算子 | 1–2 周 | 无可比性即不可投稿 |
| **P3-R1** | 自修复 | 落盘优先 + 失败分类学 | Agentless 式最小编辑 | 归因方向修正；弃权门护城河 | 落盘率 54%→≥85%；repair 39%→≈60% | +21pp | 中–高 | 存量 476 行 + QuixBugs | 现状 | 1 周–1 月 | 前沿本就无此漏点 → 只是追平 |
| **P3-R2** | 自修复 | 补丁消费定位信号 | LaMAR（bug analysis chain 最关键） | 诊断已做好但未接线 | P(correct\|FL命中) 反超 | +8–15pp | 中 | 跨文件/多函数子集 | EDIT_INTENT off | 1–2 月 | 等于追平 Agentless 核心思想 |
| **P5-S1** | 安全合规 | 默认安全档 + 人类门 + SLSA | 容器化 + 人类监督惯例 | 分级默认（高风险任务强制暂停） | 默认档下坏补丁不入工作树 | 定性 | 高 | CI + 端到端 | 现状默认 | 2 周–1 月 | 无——这是合规门槛 |
| **P4-B1** | 评估/外部有效性 | 指标桥接到 ULT / SWE-Mutation / TestGenEval | ULT (TOSEM 2026)、SWE-Mutation (ACL 2026 Findings)、TestForge | 多协议可比 + ULT/PLT 双轨泄漏对照 | 四指标（acc/stmt/branch/mutation）可比数值 | 首次可对外比较 | 中 | ULT 3,909（先 200 定标） | ULT 12 模型均值 / 最佳单模型 | 2 周–2 月 | 若前沿也跑 ULT → 靠评估基础设施护城河 |
| **I-21** | 学术诚信 | 改写错误归属引用 + 引用门禁 | IEEE 复现研究（11655121）+ CANDOR 原文（TOSEM 2026）+ Konstantinou et al.（ICST 2026）三方并列 | **零成本、当天可完成** | 全部引用可解析到 DOI/arXiv 且数值可复现 | 消除重大风险 | 高 | README/CHANGELOG | — | **立即** | 无 |
| **I-25** | `src/specs/spec_ir_v2.py`、`src/tools/oracle_validator.py` | **本项目从未审计"规约是否忠实刻画了目标函数语义"**——而 `spec_compile_rate` 只是"能编译"（语法），与"忠实"（语义）是两件事 | **SWE-PROOF（arXiv:2609.21190v2）**：**只有 56% 的 agent 自写规格能通过审计**；忠实形式化规格把补丁解决率 **85%→95%**（NL 规格做不到）；**约 25% 的"测试通过"补丁存在反例**——与本项目 `false_fix=87.2%` 同源。**R3 结论：2026 的瓶颈是规格合成与保真审计，不是测试生成** | 新增 `spec_faithfulness_audit` 指标：规约 oracle 在（a）gold fixed 上应通过、（b）≥30 个 cosmic-ray 变异体上应杀死一部分、（c）原始 buggy 上应失败；三者皆满足才算忠实。与 `spec_compile_rate` **并列**报告；审计不通过 → 接弃权门 | NEW | **P0** | "逻辑驱动"首次有**语义**质量指标；可解释低注入率 | 低（零 LLM，存量 427 条规约即可先跑） | 忠实率分布 + 与 detection 的相关性 | **本周（零 LLM 先行）** | `python -m experiments.spec_faithfulness_audit`（待建）；`pip install cosmic-ray` |
| **I-26** | `docs/MODEL_CARD.md`、论文方法节 | 缺少对 2026 最强反例的正面回应 | **TEST WARS（arXiv 2501.10200）**：GitBug Java 上 **LLM（TestSpark）在覆盖率与真实缺陷检出上输给 EvoSuite（SBST）与 Kex（符号执行），仅在 mutation score 上获胜** | 在方法节显式加入"与传统方法的对照"要求：任何"LLM 优于 X"的主张必须附 SBST/符号执行基线（EvoSuite/Pynguin/CrossHair）在同一基准上的结果 | NEW | **P1** | 预堵审稿人最强反驳 | 中（需跑传统工具基线） | 三方法同基准对照表 | 1 月 | `pip install pynguin`；`crosshair` |

---

## 6. 差距分析表

| # | 维度 | 项目现状（一手复算） | 前沿/应有水准 | 差距性质 | 严重度 |
|---|---|---|---|---|---|
| G1 | **外部有效性** | 合成集 29 模板覆盖 87 任务（n_eff≈40）；真实基准仅 QuixBugs 50 玩具程序；SWE-bench 管道损坏 | TestGenEval 1,210 真实文件 / 11 repos | **证据基础缺失** | **P0** |
| G2 | **检测有效性** | QuixBugs 45.9% (17/37) vs 自家纯提示臂 83.8% | TestForge pass@1 84.3% | **显著落后** | **P0** |
| G3 | **归因闭合** | 编排判负但实验未开多智能体组件；逻辑通道贡献不可观测；−28pp 机制停在"结构" | 前沿要求单变量归因 | **科学缺陷** | **P0** |
| G4 | **测量口径** | 476/476 补丁围栏残留未回灌；`plausible` 语义 ≠ 名字；分母 6 处不同源 | 口径矩阵已建立（自身已达前沿） | **自建规范未执行** | **P0** |
| G5 | **指标可比性** | mutation score 用自研 5 类算子、均值 4.76 变异体/任务、仅 17/50 任务有变异体 | cosmic-ray 标准算子，数十–数百变异体 | **不可比** | **P1** |
| G6 | **逻辑驱动兑现** | `spec_compile_rate` 度量通道 ≠ 注入通道；注入率实测 **36%（18/50）**；注入组检出反而更低（31% vs 57%，观察性关联）；DSL 无量化/关系/时序；**无规格保真审计** | GORDIAN（SMT+LLM，覆盖率 +28.5–115.2%，token −91–96%）；TestTailor（+5.01% stmt @ −60% 成本）；**SWE-PROOF：仅 56% 的 agent 自写规格通过审计** | **未兑现 + 靶子错位** | **P0** |
| G7 | **修复落盘** | 266 有补丁文本 → 144 落盘（≈46% 丢失）；接受侧 CPR 84.5% | 前沿最小编辑天然锚定 | **工程漏洞** | **P1** |
| G8 | **反馈闭环分类学** | `over_red` 60% 被当同质现象；"挂起"未从"红"里拆出 | 需要把 hang 语义单列 | **测量与机制缺口** | **P1** |
| G9 | **默认姿态安全** | 宿主 uid 执行 LLM 代码（内核沙箱默认关）、默认自动打补丁、默认无人类门、无 SLSA | 容器化 + 人类监督 + 供应链证明 | **合规风险** | **P1** |
| G10 | **通信效率** | 纯文本通信，QuixBugs 8.4× token（41 行口径） | LaMAR：O(N²)→O(N)，信道容量严格更高 | **架构性** | **P2** |
| G11 | **文档一致性** | `tests` 三值矛盾（5015 / 5107+3 / 实测 5178）；mypy 119 vs 实测 120；ADR 索引缺 0029；CHANGELOG 版本 0.6 vs 0.7；双语日期门禁静默放行 | 单一事实来源应生效 | **治理漂移** | **P2** |
| G12 | **开关可审计性** | 37/55 个 `*_ENABLE` 不在 `env_snapshot`；A1 假阴性、RT1 同类风险已发生 | 新开关必须入快照 | **方法学漏洞** | **P0** |

### 6.8 🔴 更正框：本报告初版关于"逻辑通道零注入"的断言是错的（2026-10-10 自纠）

**初版断言（错误）**：产出 `detection=45.9%` 的那一批里 `oracle_type` 50/50 = `generated_test`，
故"逻辑通道一行都没注入"。

**错在两处，都必须记下来**：

1. **用错了字段**。`oracle_type` 由 `experiments/run_benchmark.py:581-598` 的
   `_oracle_type_label()` 计算，它**只看 `ORACLE_ENHANCE_ENABLE`**，与 `spec_oracle` 注入
   **完全无关**。用它当"注入与否"的证据是**误读**（该问题由执行工程师 spec-engineer 独立发现）。
2. **事实相反**。规约 oracle 的注入会在**生成测试文本**里留下可识别的函数名
   `test_specir_v2_oracle`（`src/specs/spec_ir_v2.py:269` 的产物结构）。
   本审查者**改为直接检测该标记**后重算：

| 口径 | 计数 | 占比 |
|---|---|---|
| `generated_test` 含 `test_specir_v2_oracle` 的行 | **18 / 50** | **36%** |
| 其中在 41 个有 gold 的缺陷程序中 | 18 / 41 | 44% |
| 在 37 个可测 detection 行中 | 16 / 37 | 43% |
| 对照臂 `plain_llm_df` 含该标记的行 | **0 / 50** | 0%（符合预期：无逻辑通道） |

**且关联方向是"负"的**（同批，37 个可测行）：

| 分组 | n | detection | repair |
|---|---|---|---|
| 注入规约 oracle | 16 | **5/16 = 31%** | **18/18 = 100%** |
| 未注入 | 21 | **12/21 = 57%** | 19/22 = 86% |

**如何正确解读（三步，缺一不可）**：

1. **这是观察性关联，不是因果**。注入与否**不是随机分配的**——它取决于 LLM 是否产出了含
   `*_expr` 子句的 `logic_analysis`，而这与任务的**模型输出质量**同源，
   也与 `stop_reason` 分布纠缠（注入组 repair 100% vs 未注入 86% 提示两组任务构成不同）。
   **因此不能据此说"逻辑通道降低了检出"。**
2. **但也不能说逻辑通道无效**——要判定贡献必须做**单变量 A/B**：
   `SPEC_ORACLE_EXEC_ENABLE` off/on，其余（尤其载荷、节点、预算）全部固定。这正是建议 I-07 的第二步。
3. **可观测性必须先补**。当前**没有任何行级字段**记录注入与否——本审查者只能靠
   **在生成测试文本里找函数名**这种脆弱手段。`BASELINE.yaml:110-112` 早已把
   `spec_oracle_injected` **写进注释**，但它**从未出现在 `metrics_schema` 列表里、
   也从未在结果行中产出**（全仓 `grep -rn spec_oracle src/` 只有函数/标志定义，无行级键）。
   这是一个**"文档化了但从未实现的指标"**——比缺失更危险，因为它会让读者以为已被测量。

**对报告其它部分的影响**：§0.2 的 C2、§2.2 的 A2、§6 的 G6 已同步更正。
**"逻辑驱动从未运行"这一叙事必须撤回，替换为"逻辑驱动确实运行了（36% 注入率），
但其净效应未知，且当前无法从工件观测"。**

> **✅ 2026-10-10 更新：净效应已由一手 A/B 测定（不再是"未知"）**
> 完成了一次真实 LLM 的正式 A/B（`review_2026/E5_logic_channel_ab_result.md`，
> 工件 `experiments/results/llm_logic_ab_20261010_194701/`，成本 **≈$0.80**）：
> 协议 = QuixBugs（排 4 个不终止任务 → 46 程序）· logic 档 · seed 42 · temp 0 ·
> **冷缓存** · 单变量 = `SPEC_ORACLE_EXEC_ENABLE` off/on · 双臂 det_measured 均 37（可配对）。
>
> | 臂 | detection | 注入行数 | specific_red | over_red |
> |---|---|---|---|---|
> | control（off） | **24/37 = 64.9%** | **0/46** | 24 | 22 |
> | treat（on） | **15/37 = 40.5%** | **25/46** | 15 | **29** |
>
> 配对：both=12 · **control-only=12** · **treat-only=3** · neither=10；
> McNemar χ²=**4.267, p=0.0389**；精确二项（双侧）**p=0.0352**。
> **→ 注入确定性规约 oracle 使检出下降 24.4pp，且机制指向 over_red 升高
> （22→29，特定红 24→15）。**
>
> **口径限定（必须随数字一并引用）**：n=37、不一致对仅 15（边际显著、未做聚类校正）；
> 属**意向性分析**（treat 臂仅 25/46 实际注入，16 行 `compiled_empty`、5 行 `not_attempted`）；
> treat 臂内"注入组 24% vs 未注入组 75%"是**观察性**对比、不可作因果解读；
> 本批关闭变异评分故无 mutation 指标；**control 臂 64.9% 与历史 45.9% 协议不同源，
> 不可跨批比较**——A/B 结论只依赖双臂同批配对。
>
> **这一结果强化了 P2-L1 的诊断并新增 I-28**：问题不在"有没有逻辑通道"，
> 而在**注入的 oracle 断言本身不忠实/过苛**——它在 gold fixed 上失败，
> 使门①把该行判为 `over_red`，进而压低检出。**故"提高规格保真度"必须先于"提高注入率"。**

### 6.9 🔴 更正框：本报告初版的"围栏残留导致写盘被拒"假设被**证否**（2026-10-10）

**初版假设（错误）**：`patch` 字段的围栏残留（476/476 行）导致 `safe_apply_patch` 判定非法
→ 补丁写盘失败 → `patch_plausible=0`。据此我把它列为"修复天花板的最大漏点"。

**证否证据（三条，互相独立）**：

1. **代码层**：`normalize_patch_text` 在**所有守卫之前**执行——`src/tools/patch_applier.py:236`
   是 `safe_apply_patch` 的第一条语句（"Step 1/2 … 与测量层共用的单一权威口径"）。
   因此写盘层看到的**永远是清理后的文本**，围栏根本到不了守卫。
2. **数据层**：862/862 带补丁行经 `normalize_patch_text` 后**全部 wellformed**（`ast.parse` 通过，0 语法错误）。
3. **字段层（决定性）**：394 行"证据门拒绝"的行**带有非空 `patch_evidence_level`**，
   而该字段只在 `if written:` 分支写入（`src/graph/nodes.py:1841`）——
   **证明补丁当时已成功应用、通过全部静态守卫，之后才被回滚。**
   围栏残留对"落盘"的量化影响 = **0 行**。

**真实主因（已量化）**：

| 原因 | 行数 | 占比 | 性质 |
|---|---|---|---|
| **`PATCH_EVIDENCE_GATE_ENABLE` 回滚**（默认开，仅放行 gold/sbfl） | **394 / 402** | **98.0%** | **门禁策略**，非模型能力 |
| "仅类定义"整文件补丁无法应用 | 7 | 1.7% | 独立 bug（`patch_applier.py:116/148`） |
| 命名契约拒绝（2026-10-01 老代码） | 1 | 0.2% | 历史口径 |

**量化影响（这是本批次最有价值的修复线索）**：
- main_batch 129 行未落盘中，**44 行（34.1%）经 gold 独立裁决为 correct**
  （对照：已落盘行 71/137 = 51.8% correct）；
- **若旁路证据门：修正口径 repair = 115/266 (43.2%) → 159/266 (59.8%)，+16.5pp**；
- 全三组同类上界（工件自带 `patch_correct`）：**132 行**。

**同时修正一个数字**：初版写"≈122 行未落盘"是**混用分母**的错误——
144 是 **274**（全部带补丁行）口径的 plausible 数，266 是"有 gold 材料"口径。
正确为 **274 中 130 行**（266 可重放口径内 **129 行**）。

**第三个硬发现（归因陷阱）**：129/130 行的 `error_category = patch_validation_failed`、
124 行 `stop_reason = skip_debugger_repair_invalid`，后者经
`src/observability/failure_taxonomy.py:75` 映射为 **`GENERATION_CAPABILITY_FAILURE`（模型能力失败）**。
**但两者都是从 `repair_history[-1].patch_applied is False` 派生的后果标签**
（`src/agents/error_classifier.py:1288`）——129 行的真实含义是"证据门回滚"。
**按这两个字段做归因，会把门禁策略问题系统性错判为模型能力问题。**
这解释了为何 ADR-0024 把修复上限归因为"生成侧合成质量"：**归因所依赖的字段本身就是后果标签。**

**对报告其它部分的影响**：§0.2 的 C3、§9 的 I-10 已同步更正；
**建议新增 I-27（证据门 A/B）**——见下。

---

## 7. Python 专项诊断表

> 详见 `review_2026/T2_python_audit.md`（608 行）。以下为提炼。

| # | 子维度 | 现状（file:line / 命令） | 问题 | 严重度 | 可执行修复 |
|---|---|---|---|---|---|
| PY1 | 结构/包管理 | `src/` 119 文件 45,371 行；`pyproject.toml` PEP 621 + dynamic version；wheel 只含 `src/`+`config.py`；`nodes.py` 2,005 行经四簇拆分后仍为最大 | 单文件过大（`nodes.py`/`error_classifier.py` 1,348/`executor_repo.py` 1,135）；`src/` 作为顶层包名与 PEP 8 惯例不符（应为 `aitester/`） | P2 | 续拆 `error_classifier.py`（规则表外置 YAML）；`src` → `aitester` 需一次性大改名（低优先） |
| PY2 | 依赖 | `requirements.txt` 全 `==` 锁定；`requirements.lock` 一致；`check_lock_sync.py` CI 门禁；`pip-audit` 有 5 条 chromadb 豁免登记 | 无法本地核验（需联网）；豁免 5 条需定期复核 | P2 | `pip-audit -r requirements.lock --ignore-vuln ...` 纳入定期巡检；豁免加到期日 |
| PY3 | 代码质量 | ruff 0.16.3 固定（CI/lock/pre-commit 三方一致）；mypy 0 错误（**实测 120 源文件，BASELINE 写 119**）；`PGH003` 门禁已重启；6 处 blanket type-ignore 已收窄 | 数字漂移（G11） | P2 | 更新 `BASELINE.yaml:82` → 120；把"数字取数脚本"入库（见 PY9） |
| PY4 | 测试 | **实测 `--collect-only` = 5,178**；实跑 5,175 passed + 3 skipped / 54.08s；8,906 assert / 4,996 用例 = **1.78 assert/用例**（"零断言"门禁真实有效） | `BASELINE.yaml:17` 写 5015、同页另一处写 5107+3 → **三值矛盾** | **P1** | 用 `pytest --collect-only -q \| tail -1` 生成数字并接门禁；`make tests-count` 自动刷新 BASELINE |
| PY5 | 可复现性 | `reproduce.sh`、`Dockerfile.repro`、种子管理、`env_snapshot`、`SHA256SUMS`（4/52 批次有）、工件入库（3,426 文件受追踪） | **`data/quixbugs` 是嵌套 git 仓库且未登记 submodule**（外部无法锁定 commit）；A1 批次仍滞留 `/tmp/a1_fixed`（我已核验其 `PLAN_STRIP_EXPECTED_OUTPUT_ENABLE=true`、`cache_namespace=a1_strip`、19/37 与登记一致，**证据真实但未归档**） | **P1** | `git submodule add` 或记录 quixbugs commit（现为 `4257f44b…`）；把 `/tmp/a1_fixed` 移入 `experiments/results/` 并生成 `SHA256SUMS` |
| PY6 | 性能/资源 | `BENCHMARK_PARALLELISM`、LLM 文件缓存、语义缓存、`run_with_timeout`（killpg + 有界收口） | **`run_with_timeout` 只接线 1 个文件**；其余 **9 文件 12 处**裸 `subprocess.run`（`fl_spectral.py:238`、`executor_repo.py:90/869`、`executor_modes.py:467`、`executor_runtime.py:133`、`runtime_probe.py:345`、`dependency.py:533/895`、`patch_rollback.py:188`、`testless_validation.py:120/228`、`type_repair.py:270`）——BASELINE 自述"20 处"经 AST 复算为 12 处 | **P1** | 逐处替换为 `run_with_timeout`；加门禁禁止 `src/` 内裸 `subprocess.run(` |
| PY7 | 安全/合规 | 凭证剔除白名单默认开（`build_minimal_env` 13 键）；日志三层脱敏；gitleaks + 二进制 SHA256；`src/` 内 `exec/eval/pickle/shell=True` **全为 0**（bandit 本地 exit 0） | **LLM 缓存记录为"已知可接受风险"但不进 git**（缓存含 prompt/response，跨用户隔离靠 namespace）；`.env` 权限 0644 而 209 个普通文件 0600 | P1 | 缓存目录 `chmod 700`；`.env` `chmod 600`；`bandit -r src/ -ll` 接 CI |
| PY8 | CI/CD | ci.yml 4 jobs（test/security/supply-chain/smoke-llm）+ perf.yml + release.yml；action SHA 钉版；**`make gates` 缺 9 类 CI 门禁**（本地绿 ≠ CI 绿） | 本地门禁与 CI 门禁不一致，是"本地全绿但 CI 红"的结构性来源 | **P1** | `make gates` 逐条对齐 ci.yml 的 job 步骤；或把 ci.yml 步骤抽为可本地执行的脚本 |
| PY9 | 数据/实验管线 | 预注册（606 行）、McNemar/BH-FDR/贝叶斯 ROPE、聚类 DEFF、模板级符号检验；`contamination_check.py`；`difficulty_stratification.py` | **D2 未闭环**：缓存命中不记账（`token_usage.py:129-148`、`cost_budget.py:141/154`、`llm_client.py:331`、`base_agent.py:420-431/437`）→ `total_tokens` 系统性低估、预算 cap 随缓存漂移；main_batch 10/10 `cache_enabled=true`；e6_control 两臂 **0/87 token 行** | **P0** | 三处补缓存命中记账；工件层加"token 覆盖率"校验门禁 |
| PY10 | 文档/协作 | README/QUICKSTART/api_reference/CONTRIBUTING/CHANGELOG 双语；`check_bilingual_docs.py` 双语门禁 | 门禁对"中文侧无日期行"**静默放行**（`:174-183`），当前 README/QUICKSTART/CONTRIBUTING 三对中英**日期不可核对**；无 Issue/PR 模板 | P2 | 门禁改为"任一语言有日期行则双方必须都有"；补 `.github/ISSUE_TEMPLATE/`、`PULL_REQUEST_TEMPLATE.md` |

---

## 8. 领域专项诊断表

> 详见 `review_2026/T3_domain_audit.md`（494 行）。评分为该审计独立给出（1 = 概念层，5 = 领域标杆）。

| 领域维度 | 评分 | 依据（关键位置） | 最短板 |
|---|---|---|---|
| 1. **逻辑驱动** | **2** | 受限 DSL 与保守降级真实（`spec_ir_v2.py:63-124`）；z3 三通道已实现（`spec_smt.py:459-693`）；CEGIR 反例精化已落地（`spec_refine.py`） | **名不副实 + 贡献不可测**：无量化/关系/时序；度量通道 ≠ 注入通道；关键批次注入 **0 行** |
| 2. **多智能体** | **2** | 工程完整（并发/超时/记账/降级 `expert_pool.py:321-373`）；LangGraph 状态机 + 显式递归上界 | **标签与实验对象错位**（logic 档无多智能体组件）+ 通信为自由文本（`state.py:152-158`）+ 共识为文本投票（`expert_pool.py:375-383`） |
| 3. **测试生成** | **3** | 覆盖/变异/flaky/断言校验齐备；分支覆盖注入（`branch_coverage_inject.py`） | **缺"断言强度/过苛断言"度量**，导致 `over_red` 无生成侧解释力；属性测试名不副实；无 MC/DC、无模糊/符号执行 |
| 4. **自修复** | **3** | 定位+补丁+回滚+弃权+防 hacking 链路罕见（`patch_abstain.py`、`patch_test_hacking.py`、`fl_spectral.py:295-352`） | **定位与修复负相关**（15.79% vs 64.71%）+ **落盘丢 46%** |
| 5. **反馈闭环** | **3** | 检出优先协议 +43pp 且已排除采样效应（RT1）；三值终态；双门；聚类校正 | **"红得不特异"没有分类学**：60% `over_red` 被同质处理；无测试侧超时语义；奖励信号无消费者（`trace_reward.py:117-150`） |
| 6. **评估与基准** | **3**（方法学 **4.5** / 证据基础 **1.5**） | 预注册、伪影自曝、双界披露、ROPE 等价检验达前沿水准 | **外部有效性**：n_eff≈40 + 50 玩具程序 + 损坏的 SWE-bench |
| 7. **安全与合规** | **3** | 三级沙箱 + fail-closed + Docker 强加固 + 凭证剔除 + 豁免登记 + SHA 钉版 | **默认配置不安全**：内核沙箱默认关（`kernel_sandbox.py:69`）、默认自动打补丁（`patch_rollback.py:81`）、默认无人类门（`risk_approval.py:57`）；无 SLSA/provenance |
| 8. **工程化与运维** | **4** | 20 个门禁脚本 + 3.12–3.14 矩阵 + mypy/覆盖率硬门 + ratchet + 工件 checksum 守卫 + SHA 钉版 | 无告警链路；SBOM info-only；孤儿进程只修一环；`make gates` 缺 9 类 CI 门禁 |

**综合均分 ≈ 2.9 / 5**。若只看**方法学诚实度**：同规模研究代码前 5%；若看**主张可支撑度**：落在"有真实负结果、但正主张证据不足"一档。

### 8.1 红队反例（可能推翻本项目的竞争路线）

| # | 竞争路线 | 为什么能推翻它 | 已有的脆弱证据 | 最小防御动作 |
|---|---|---|---|---|
| R1 | **更强基座 + one-shot** | 若前沿模型在单提示 + 检出优先协议下达 ≥90%，完整流水线增量归零 | df 臂在 `deepseek-flash` 上已 **83.8%** | 把"协议 × 模型能力"做成 2×2 网格；显式声明模型档位依赖 |
| R2 | **自动搜索编排（BOAD 类）** | 若搜索能超越 one-shot，则"手工编排净负"被解释为"手工"而非"编排" | 项目只有设计文档（Proposed），无本地证据 | 做路径 P1-AS 的小网格搜索 |
| R3 | **微调/蒸馏小模型** | 1–2B 微调模型逼近流水线则"提示协议 + 编排"被商品化 | 项目零训练能力（`MODEL_CARD.md:20-21` 自述不自研模型） | 出"零样本 vs 少样本 vs 微调"可行性 + 成本对比表（诚实声明未做） |
| R4 | **现成契约/属性工具链**（icontract + CrossHair + hypothesis） | 若它们在同类任务上直接检出大部分缺陷，"逻辑驱动"被现成工具支配 | 本项目端到端非空仅 18.7%，规约 oracle 注入率 36%，且**净效应未知** | **零边际成本先做基线对照**（见 §11.2 EXP-0）——**这是最便宜也最致命的红队检验** |
| R5 | **Agentless 式三阶段 APR**（定位→最小编辑→验证） | 若它在 QuixBugs 上 >39.31% 且成本远低，复杂修复引擎无优势 | 项目自己的 ADR-0024 已把杠杆指向"让补丁生成消费定位"——正是 Agentless 核心 | 把局部化编辑做成默认路径并对照 |
| R6 | **基准效度质疑** | 若审稿人认定合成集自证、QuixBugs 过小、SWE-bench 0/20 系管道问题，**全部主批次结论失去载体** | n_eff≈40；50 玩具程序；`instance_code` 空 | 一手基准扩容（路径 P4-B1） |

---

## 9. 改进 / 优化 / 新增建议表

> **类型**：必须改进（MUST）/ 建议优化（SHOULD）/ 可新增（NEW）。**优先级**：P0 > P1 > P2。

| 建议编号 | 对应文件/位置 | 问题 | 2025–2026 前沿依据 | 建议内容 | 类型 | 优先级 | 预期收益 | 成本/风险 | 验证指标 | 时间线 | Python 工具/命令 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **I-01** | `src/graph/nodes.py:1762`、`src/tools/patch_applier.py:58` | 476/476 补丁行围栏残留；修复只在测量层未回灌 | test-hacking / 补丁证据链标准做法 | 在**写盘处**调 `normalize_patch_text`；加回归测试禁止 `patch` 以 `python\n`/围栏开头 | MUST | **P0** | `plausible` 144→?；`patch_precision` 语义恢复；下游 5 个消费者口径统一 | 极低（纯函数已有） | 新行 `patch` 无围栏比例 = 100% | 1–2 天 | `pytest tests/ -k patch -q` |
| **I-02** | `experiments/run_benchmark.py:2712-2770` `_env_snapshot_keys` | 37/55 个 `*_ENABLE` 不在快照；A1 假阴性、RT1 同类风险已发生 | 消融可审计性（项目自述"未实施"） | 把"新开关必须出现在 `_env_snapshot_keys`"做成 CI 门禁（AST 扫描 `os.getenv("..._ENABLE")` vs 快照键集合） | MUST | **P0** | 杜绝第三、第四次"开关未生效"事故 | 低 | 门禁 exit 0；RT1 补登记 | 2–3 天 | `scripts/gates/check_env_snapshot_keys.py` + `ruff`/`ast` |
| **I-03** | `experiments/_m1_metrics.py`（token 记账）、`src/agents/base_agent.py:420-437` | 缓存命中不计 token（D2 未闭环）→ 成本低估、预算 cap 漂移 | TestForge 等均报 $/file 成本 | 三处补记账（`token_usage.py:129-148`、`cost_budget.py:141/154`、`llm_client.py:331`、`base_agent.py:437`）；工件加 token 覆盖率校验门禁 | MUST | **P0** | 成本数字可信；E6 matched 臂可执行 | 中（需改动记账核心） | 每批次 token 覆盖行 ≥ 95% | 1 周 | `pytest tests/test_cost_budget.py tests/test_token_usage.py -q` |
| **I-04** | `data/quixbugs/`（嵌套 git，未登记 submodule）；`/tmp/a1_fixed` | 外部无法锁定数据集 commit；A1 关键证据滞留 `/tmp` | 工件入库约定（`preregistration.md:247-250`） | `git submodule add` 或记录 commit（现 `4257f44b…`）；`/tmp/a1_fixed` 移入 `experiments/results/` + `SHA256SUMS` | MUST | **P0** | 真实基准可复现；A1 "开关已生效"证据链闭合 | 低 | `git submodule status`；`sha256sum -c SHA256SUMS` | 1 天 | `sha256sum`、`git submodule` |
| **I-05** | `experiments/results/{swe_bench_lite_20,g8_lite_retest*}`；`README.md`、`docs/design/swe_bench_probe.md` | SWE-bench 工件是失败分支行，`instance_code` 空；对外被叙述为"负结果" | 基准效度要求 | ① 撤回"0/20 负结果"表述，改为"输入物化失败，评测未执行"；② 修复 loader 后**先做零 LLM 预检**（只验 gold 测试能否收集/执行） | MUST | **P0** | 消除一处对外事实性偏差 | 低（改写）+ 中（loader） | 预检：sqlfluff 子集 gold 测试 collect-only 成功率 | 1 周 | `pytest --collect-only` 于导出仓库 |
| **I-06** | `experiments/mutation_testing.py`、`BASELINE.yaml:63-67` | 自研 5 类算子、均值 4.76 变异体/任务、仅 17/50 任务有变异体 → 不可比 | **TestForge / SPARC 均用 cosmic-ray 默认算子集** | 接入 cosmic-ray 作为权威计算器；每任务 ≥30 变异体；分母改"有变异体任务"并并列披露 | MUST | **P1** | 指标可比，投稿必要条件 | 中（新依赖 + 集成） | 与自研算子的 Spearman 排序一致性 | 1–2 周 | `pip install cosmic-ray`；`cosmic-ray init/baseline/exec` |
| **I-07** | `src/specs/spec_ir_v2.py:571-580` vs `:195-238`；`metrics_schema` | 度量通道 ≠ 注入通道；`spec_compile_rate` 是上界而非注入率；注入量不可观测 | SPARC：结构/约束需可归因 | ① 统一两通道判据；② 新增行级 `spec_oracle_injected` / `spec_oracle_verdict` | MUST | **P0** | "逻辑驱动"首次可证伪/可证实 | 低 | 新键出现在结果 JSON；离线重放可复算 | 1 周 | `pytest tests/ -k spec_ir -q` |
| **I-08** | `src/tools/detection_gates.py:69-121`；`experiments/_m1_metrics.py` | "挂起"与"断言失败"未区分；`_run_pytest_in_tmp` 的 `None` 被丢弃 | 测试侧超时语义（前沿标准做法） | ① 五值 verdict：`specific_red`/`over_red_hang`/`over_red_assert`/`over_red_plan`/`unavailable`；② `hang` 作为独立检出通道（buggy 超时 ∧ fixed 通过 → 检出） | NEW | **P0** | detection +6–12pp；`None` 行归零 | 中 | `None` 行数→0；detection 提升 | 1–2 周 | `pytest-timeout`；`signal` 限时 |
| **I-09** | `experiments/repair_ceiling_analysis.py:74,100,191`；`cpr_idr_report.py:118`；`repair_sample_selection.py:57-62` | 漏斗/CPR/IDR/E7 抽样框以 `patch_plausible` 为闸口，与 repair 分子不同源 | 单一口径原则（项目自己已建立口径矩阵） | 重命名 `patch_plausible` → `patch_written`；另设 `patch_wellformed`（清理后 `ast.parse` 通过）；重生成 `repair_ceiling_report.md` | MUST | **P0** | 漏斗各层同源；`patch_precision` 恢复 ≤1 | 低（零 LLM 重算） | 重算后所有比率 ≤1 且分母一致 | 2–3 天 | `make corrected-metrics`、`make cpr-idr` |
| **I-10** | `src/graph/workflow.py:727-734`（`_recent_repairs_invalid` 早退） | 48%（24/50）任务在 2 轮后提前终止，其中 13 行仍被 gold 判正确。**⚠️ 2026-10-10 更正：该早退的直接触发源是证据门回滚**（`patch_applied=False`）→ 属 I-27 的下游症状，须与 I-27 一起做 | 修复循环收敛性要求 | 早退判据改为"连续 2 轮 ∧ 清理后补丁仍不可解析/为空"；或直接做门槛 A/B。**但若 I-27 成立，本项可能自动缓解** | MUST | **P1** | 回收被提前掐断的修复能力 | 低 | repair 配对差；终止原因分布 | 1 周（**排在 I-27 之后**） | `pytest tests/ -k workflow -q` |
| **I-27**【⚠️ **2026-10-10 经 A/B 证否，不再列为 P0**】 | `src/tools/patch_evidence.py:58-66`（`PATCH_EVIDENCE_GATE_ENABLE` 默认 **true**）、`src/graph/nodes.py:1841`（`if written:` 写入 `patch_evidence_level`） | **默认开的证据门在补丁已成功写盘后回滚原文件**，占"有补丁文本但未落盘"的 **394/402 = 98.0%**；其中 **34.1% 经 gold 裁决为 correct**。**旁路后修正口径 repair 43.2% → 59.8%（+16.5pp）** | 前端/中端质量已达标（接受侧 CPR 84.5%、862/862 补丁 wellformed），瓶颈在门禁策略而非生成质量；前沿以"最小编辑 + 验证"取代宽泛回滚 | ① 立即做 **`PATCH_EVIDENCE_GATE_ENABLE` off/on 的零 LLM 口径 A/B**（存量 266 行重放即可，无需新跑批）；② 把门禁从"二值回滚"改为**分档**（gold/sbfl 放行 + 带负信号者弃权 + 其余标记而非回滚）；③ 新增行级 `patch_write_blocked_reason`，把"门禁回滚"与"安全守卫拒绝"**分开计**——当前二者共用同一后果标签 | ~~MUST~~ **不必做** | ~~**P0**~~ **P3** | **⚠️ 2026-10-10 经真实 A/B 证否**：关闸后 correct 总量不变（32/46）、detection 与 repair 配对均 p=1.0000，而落盘精确率从 **92.6% 降至 71.1%**。证据门是**有效守门**，不是漏点。原"+16.5pp"系工件字段静态重放所得，未做 A/B | 零成本（已证否，无需再投入） | — | — | **已结案** | — |
| **I-28** | `src/specs/spec_ir_v2.py`（oracle 编译）、`src/tools/detection_gates.py:96-121`（门①）、`src/specs/spec_smt.py` | **A/B 实测：注入规约 oracle 使检出下降 24.4pp（64.9%→40.5%，p≈0.04），机制是 over_red 从 22 升到 29**——即注入的 oracle 断言**在 gold fixed 上失败**，被门①判为"红得不特异" | **SWE-PROOF（arXiv:2609.21190v2）**：仅 56% 的 agent 自写规格通过审计；忠实形式化规格把补丁解决率 85%→95%，NL 规格无效。**→ 规格合成的瓶颈是"保真"，不是"产量"** | ① **先加规格忠实的必要子条件**：oracle 编译后先验"在 gold fixed 上通过"（不通过则**不注入**，记 `spec_oracle_verdict=compiled_unfaithful`）；② 接 I-25 的 `spec_faithfulness_audit`，把"忠实率"与"注入率"**并列**报告；③ **在忠实率达标前不要提高注入率**——否则注入越多、over_red 越多、检出越低 | MUST | **P0** | 把逻辑通道从"净负"扭回"净零或正"，且**零 LLM 即可先验证**（存量 427 条规约离线跑忠实性判定） | 低（先离线） | 忠实率分布；注入后的 over_red 占比；detection 配对差 | **本周（零 LLM 先行）** | `python -m experiments.spec_faithfulness_audit`（待建）；`pytest tests/ -k spec -q` |
| **I-29** | `src/tools/patch_evidence.py`（证据门放行集） | 证据门现为**二值**（仅 gold/sbfl 放行、其余回滚）：本批 1 行 `keyword` 级证据被丢弃；而**直接旁路无收益**（本次 A/B：correct 32→32 不变） | **Abstain and Validate（ICSE-SEIP 2026, arXiv:2510.03217）**：弃权 +13pp、验证 +15pp、组合 +39pp（⚠️ 该 +39pp 分母是过滤后子集、摘要与正文数字不自洽——引用红线：禁止写「可得 +39pp」） | 改**三档**：gold/sbfl 直放 / keyword+独立验证 放行 / none 弃权；判据用「弃权率 vs correct 率」权衡曲线（沿用 `docs/design/abstain_validate_design.md` 的 τ-sweep）。**二值旁路已被证否，分档须另有 A/B 证据才转正** | SHOULD | **P2** | 在不损失 correct 的前提下提高落盘率与可审计性 | 低（复用现有五信号） | 三档下 correct 不降 ∧ 落盘率升；弃权率 ≤0.35 | 1–2 月 | `make cpr-idr` |
| **I-30** | `src/graph/nodes.py:931`（oracle 注入点）、`src/specs/spec_ir_v2.py` | **在规格保真度达标前不得提高 oracle 注入率**——2×2 四臂一致显示：注入越多，over_red 越多（17→31 / 20→28），检出越低（−33.3pp / −20.8pp） | **SWE-PROOF（arXiv:2609.21190v2）**：仅 56% 的 agent 自写规格通过审计；忠实形式化规格才带来 85%→95% | ① 把 I-25 的 `spec_faithfulness_audit` 设为 oracle 通道前置门（不忠实 → 不注入，记 `compiled_unfaithful`）；② 在忠实率与 over_red 关系明确前**冻结注入率相关优化**；③ 反过来说明当前 36% 注入率**不是缺陷**，而是概率性自我保护 | MUST | **P0** | 阻止「继续优化错误方向」 | 零成本（一条纪律） | 注入后 over_red 占比；detection 配对差 | **立即** | — |
| **I-31** | `pyproject.toml:41`（`click>=8.0.0`）、`src/agents/executor_repo.py:120-140`（`repo_envs` venv 构建） | **两处真实缺陷**：① `click>=8.0.0` **无上界**，而 `click 8.5.0 已移除 `CliRunner(mix_stderr=)`——`pip install aitester`（不带 lock）会拉到不兼容版本；② 被测仓库的 venv 用 `python -m venv` + 装最新依赖构建（`repo_envs/…/venv/pyvenv.cfg` 可见），**未按各 repo 锁定依赖**，已知产生不兼容环境 | 实测：sqlfluff `a820c139ccbe` 的缓存 venv 为 click 8.5.0，其 `src/sqlfluff/utils/testing/cli.py:18` 传 `mix_stderr=` → **gold 补丁应用后 F2P 仍 TypeError**；该仓库 20 个检出中 6 个受影响（E7 §2–3） | ① `click>=8.0.0` 收紧为 `click>=8.0,<9` 并在 `docs/dependency_exemptions.md` 登记；② 仓库 venv 改为按 repo 的 `pyproject`/`setup.py` 约束安装（`pip install -e '.[test]'`）或预置镜像；③ **加零 LLM 前置门禁**：跑批前验证「gold 补丁能让 F2P 转绿」，不过则该实例不入指标（fail-closed） | **部分已修复** | **P1** | **已完成**：导出脚本字段名缺陷（读 `repository` 应为 `repo`）**已修复**，导出从 **0/225 → 48/225**，`check-dataset` 显示 48 条「加载质量健康」；venv 层 click 降级修法已实测有效。**已修**：截断的 F2P ID 已在加载期剔除（530 个 / 影响 82 任务，含留痕字段 + 4 例回归锁）；**剩余**：层 2 venv 环境（缺 `langchain_openai` + pytest 9.1.1 vs sqlfluff 0.11.0，需按各 repo 依赖重装）+ 177 条需克隆另外 5 个仓库（需网络） | 中（需重建环境） | gold F2P 转绿率 = 100%；SWE-bench 实例可判定率 | 2–4 周 | `python scripts/gates/check_swe_bench_pro_ready.py`；自建 gold-F2P 前置检查 |
| **I-32** | `experiments/contamination_check.py:296-318`（`_combined_risk_level`） | **污染检测旧口径取 max，假阳性 40.5%**：`structural`（AST 语句类型序列 LCS）对**同模板产出的补丁**缺乏判别力——实测 639 条真实补丁的 200 组**无关**配对中，该通道单独判 medium/high **77/200 = 38.5%**（≈ 瞎猜），而 `jaccard` 仅 2.0%。旧口径 `any(v>=阈值)` 让最吵维度单方面决定等级 → **"零中高风险"结论无判别力**。项目自身早有察觉（`tests/test_contamination_multidim.py:43` 注释即为规避此误报而挑样本） | **SWE-bench 污染研究**：LLM 高分可来自训练集记忆，故污染检测是数字可信度前提；本项目 **token Jaccard 口径仍有效**（假阳性 2.0%，2,619 行全部 <0.85） | **已修**：改为**佐证原则**——`structural` 不得单独升级，须与 `jaccard`/`semantic` 同级命中；单通道场景沿用历史口径；`AITESTER_CONTAMINATION_STRICT_MAX` 可 opt-in 复现旧口径。**建议追加**：把"阴性对照假阳性率"纳入 `scripts/gates/` 常规门禁 | MUST（已实施） | **P1** | 假阳性 **40.5% → 4.5%**（9 倍改善），阳性对照不变 | 零（已完成） | 无关补丁配对假阳性率 ≤5%；补丁==gold 仍判 high | **已完成** | `pytest tests/test_contamination_multidim.py -q`；`review_2026/E8_contamination_detector_audit.md` |
| **I-11** | `src/agents/executor*.py` | 宿主 uid 执行 LLM 生成代码；内核沙箱默认关 | 2025–2026 默认安全姿态 | 发布默认档含：内核沙箱（可用时 fail-closed）+ 快照回滚 + 高风险任务人类门 | MUST | **P1** | 合规门槛；消除"以为隔离了其实没有" | 中（平台相关） | 默认档下越权写盘被拒；`kernel_sandbox_obs.backend != none` | 2 周 | `sandbox-exec`（macOS）/ `bwrap`（Linux） |
| **I-12** | `src/utils/process_utils.py` + 9 文件 12 处裸 `subprocess.run` | 孤儿/挂死只修一环 | 进程组回收标准做法 | 逐处替换为 `run_with_timeout`；加门禁禁止 `src/` 内裸 `subprocess.run(` | SHOULD | **P1** | 消除 12 处同构挂死风险 | 低–中 | 门禁 exit 0；病态任务不再留孤儿 | 1 周 | `grep -rn "subprocess.run(" src/`；`ruff` 自定义规则 |
| **I-13** | `BASELINE.yaml:17,82` | `tests` 三值矛盾；mypy 119 vs 实测 120 | 单一事实来源应生效 | 用脚本自动生成这两处数字并接门禁（`make baseline-refresh`） | SHOULD | **P1** | 消除 G11 治理漂移 | 极低 | 门禁校验：文档数字 == 实测 | 1–2 天 | `pytest --collect-only -q \| tail -1`；`mypy src/ config.py \| tail -1` |
| **I-14** | `Makefile` `gates` vs `.github/workflows/ci.yml` | 本地门禁缺 9 类 CI 门禁 → "本地绿 CI 红" | CI 一致性 | `make gates` 逐条对齐 ci.yml；或抽为共享脚本 | SHOULD | **P1** | 消除结构性 CI 红灯 | 低 | 本地 `make gates` 与 CI 步骤集合一致 | 2–3 天 | `act` 或脚本抽取 |
| **I-15** | `src/tools/oracle_validator.py`；生成侧 | 缺"断言强度/过苛断言"度量，`over_red` 无生成侧解释力 | 断言强度度量（前沿标准） | 新增 `assertion_strength`（每断言的操作数/常量占比 + 是否含边界值）与 `assertion_overstrict`（在 gold fixed 上失败的断言比例） | NEW | **P1** | 给 `over_red` 一个可优化的生成侧目标 | 中 | 与 `specificity_gate_verdict` 的相关性；A/B 后 `over_red` 下降 | 2–3 周 | `ast` 遍历 + `pytest` 执行 |
| **I-16** | `docs/troubleshooting.md`、`.github/`、`scripts/gates/check_bilingual_docs.py:174-183` | 双语日期门禁静默放行；无 Issue/PR 模板 | 协作规范 | 门禁改为"任一语言有日期行则双方必须都有"；补 Issue/PR 模板 | SHOULD | **P2** | 文档不再无限漂移 | 极低 | 门禁对缺日期行报错 | 1 天 | `python scripts/gates/check_bilingual_docs.py --strict` |
| **I-17** | `docs/adr/README.md:41-43` | ADR 索引缺 0029 | 治理 | 补索引行 | SHOULD | **P2** | 索引与实体一致 | 极低 | 索引覆盖全部 ADR | 1 小时 | — |
| **I-18** | `CHANGELOG.md:5400` | "当前版本 0.6" vs `src/__init__.py` 0.7 | 单一事实来源 | 改为引用 `src/__init__.py` | SHOULD | **P2** | 消除版本歧义 | 极低 | `aitester --version` == CHANGELOG | 1 小时 | — |
| **I-19** | `.env` `.env.local` 权限 0644 | 敏感文件权限弱于普通文件（209 个为 0600） | 最小权限原则 | `chmod 600 .env .env.local`；`.private/` 也收紧 | MUST | **P2** | 消除同机越权读取 | 极低 | `stat -f %Sp .env` = `-rw-------` | 1 分钟 | `chmod 600 .env .env.local` |
| **I-20** | `docs/MODEL_CARD.md`、`docs/DATA_CARD.md` | 有卡片，但缺"风险分级/滥用边界/监管映射"实质内容 | EU AI Act 类风险分级；NIST AI RMF；SLSA | 补：① 用途边界（禁止自动提交补丁到生产）；② 风险分级；③ SLSA provenance（`release.yml` 生成 `provenance.json`）；④ SBOM 转阻断门 | NEW | **P1** | 合规可审计 | 中 | SBOM 阻断；provenance 可校验 | 2–3 周 | `cyclonedx-py`、`slsa-github-generator` |
| **I-21** | `README.md:15-16`、`README.en.md:16-17`、`CHANGELOG.md:123-127` | **存在一处"错误归属"的引用**：把 IEEE 复现研究（Radaideh & Corriveau, Xplore 11655121）的 mutation score 结果（one-shot Gemini 2.5 Flash 88.35% vs CANDOR 35.92%）挂在"CANDOR, ICST 2026"名下；CANDOR 实为 TOSEM 2026 且原文结论相反。另有 1 处错位引用（BOAD 用于测试生成论证）+ 13 条 `[未核验]` 转引 | 学术诚信；审稿人一旦查到会质疑全部引用可信度 | ① 按 §3.6.2 把该段改写为**三方并列**（IEEE 复现研究 / CANDOR 原文 / Konstantinou et al. ICST 2026），并标注"(a) 不利证据 / (b) 有利证据 / (c) 最强负面证据"；② BOAD 限定为"SWE 任务解决"；③ 建引用门禁：进入 README/预注册的外部文献必须带 **DOI 或 arXiv ID + 已核对的具体数值 + 核对人 + 日期** | MUST | **P0** | 消除足以动摇全部引用可信度的风险 | 极低（改写，零成本） | 所有 README 引用均可解析到 DOI/arXiv 且数值可复现 | **立即（当天）** | `grep -n "DOI\|arXiv" README.md`；人工逐条核对 |
| **I-22** | `README.md:9-14`（"跨论文证据已形成共识"） | 把**分裂的**文献状况表述为"共识"；且用单一复现的单一指标（mutation score）支撑全局结论 | 2026 实际状况：负面（Konstantinou ICST 2026）/ 正面（CANDOR TOSEM 2026 line 0.991、TestAgent FSE Companion 2026 line 92.34%）/ 混合（ASTA：coverage 胜、ESR 平、token 3–4×）/ 单指标不利复现（IEEE 11655121 的 mutation score） | 改为精确表述：**"手工的、工具特定的编排相对强 LLM 单提示 + 统一修复环，优势有限或无优势"**（ICST 2026 复现研究支持的窄主张），而非"多智能体范式被击败"；并显式区分**指标**（line coverage vs mutation score 结论可不同） | MUST | **P0** | 主张与证据强度匹配 | 极低 | 无"共识"类表述；每条主张可追溯到具体论文 + 指标 | 立即 | — |
| **I-23** | `experiments/_m1_metrics.py`（detection 定义）、`BASELINE.yaml` | detection 在**弱变异体 + 29 模板 ×~3 重复**上测得；SWE-Mutation 证明弱变异体使检出虚高约 44% | SWE-Mutation (ACL 2026 Findings)：agentic 变异使平均检出 **71.04% → 39.81%**；ULT 协议（cosmic-ray + 120s + 严格击杀定义） | ① 把 detection 在 **agentic 变异体**上重测；② 接入 ULT 协议（3,909 函数级任务）作为公共可比协议；③ 报 **RDR/VRR** 而非仅 detection | NEW | **P1** | 建立与前沿的可比桥（§4.2 桥 B-A/B-B） | 中（新协议 + 跑批） | ULT 四指标（acc/stmt/branch/mutation）可比数值 | 1–2 月 | `pip install cosmic-ray`；ULT 仓库协议 |
| **I-24** | `src/graph/nodes.py:429-488`（`_over_red_section`）、`src/tools/detection_gates.py:96-121` | `over_red` 中含大量"缺陷实现不终止"的挂起情形，而提示词**无法修复挂起**（项目自己已得出此结论） | 测试侧超时语义是前沿标准做法 | 与 I-08 合并：**停止用 prompt 处理挂起**，改为执行层 per-test timeout + 把 hang 作为独立检出通道 | MUST | **P0** | 释放两类干预（A1 strip、over_red section）已验证为 +5.5pp 非显著——应停止在该方向继续投入 | 低 | hang 分类占比可量化；`None` 行归零 | 1–2 周 | `pytest-timeout` |

---

## 10. 优化后的项目方案与路线图

### 10.1 建议的新叙事定位（对外一句话）

> **AITester：一个"多通道检出协议 + 可归因修复引擎 + 世界级评估基础设施"的 Python 测试生成与修复研究平台。**
> 其科学贡献不是"多智能体"也不是"逻辑驱动"这两个已贬值/未兑现的标签，
> 而是：**在 LLM 测试生成与修复这个充满测量伪影的领域，提供第一套可复现、可证伪、自带伪影防控的评估与归因方法学**，
> 并以"确定性 oracle + hang 通道 + 特异性门 + 弃权门"构成正交于纯提示方案的检出与修复能力。

**理由**：C1/C2 表明两个主标签都不可用；而 §4.1 表明项目的**方法学遥遥领先**且**工程化评分最高（4/5）**。把主张收缩到证据能支撑的范围，是唯一诚实且仍有影响力的路径。

### 10.2 推荐目录结构（增量调整，不做大改名）

```
AITester/
├── src/                          # 保持现状（大改名收益 < 风险）
│   ├── specs/                    # ◀ 扩展：+ spec_expr_grammar.py（蕴含/量化/关系）
│   ├── tools/                    # ◀ 新增：check_hang.py（非终止判定）、assertion_strength.py
│   ├── agents/                   # ◀ 拆分：error_classifier.py（1348 行）→ 规则表 + 引擎
│   └── observability/            # ◀ 新增：env_snapshot.py（开关登记单一入口）
├── experiments/
│   ├── results/                  # 现状（3,426 受追踪文件）
│   └── ◀ 新增：search/（P1-AS 的编排搜索结果与配置）
├── benchmarks/                   # ◀ 新增：统一基准加载与外部基准适配
│   ├── quixbugs/  testgeneval/  defects4j/   # 每个含 commit 锁定 + SHA256SUMS
├── docs/
│   ├── adr/                      # ◀ 补 0029 索引
│   ├── caliber/                  # ◀ 由 repair_caliber_matrix.md 扩展为全指标口径矩阵
│   └── compliance/               # ◀ 新增：risk_classification.md、slsa.md、provenance.md
└── scripts/gates/                # ◀ 新增 4 个门禁（见下）
```

**新增门禁（4 个，均为 §9 建议的可执行落点）**：
1. `check_env_snapshot_keys.py`（I-02）
2. `check_patch_field_clean.py`（I-01 回归）
3. `check_baseline_numbers_fresh.py`（I-13）
4. `check_no_bare_subprocess.py`（I-12）

### 10.3 技术路线（按优先级串行）

```
阶段 A（W1–W2，零/低 LLM 成本）
  A1 I-01 围栏回灌 + I-09 口径重命名 + I-19 权限            ← 全部零 LLM
  A2 I-02 env_snapshot 门禁 + I-13/I-17/I-18 文档数字刷新    ← 全部零 LLM
  A3 I-04 quixbugs submodule + A1 批次归档                   ← 零 LLM
  A4 I-06 cosmic-ray 重测 mutation（离线）                   ← 零 LLM
  A5 I-08 离线 hang 分类学（四格交叉，判定 over_red_hang 占比）← 零 LLM
  A6 P1-H1 零 LLM 前置：缓存 prompt 载荷 × over_red 关联分析  ← 零 LLM
阶段 B（W3–W6，主实验）
  B1 P1-H1 载荷等价 A/B（QuixBugs 41，cold cache，≈1.4M token）
  B2 I-08 hang 通道 A/B（同批，可并行）
  B3 I-07 逻辑 oracle 单独度量 A/B
  B4 I-10 早退门槛 A/B
阶段 C（M2–M3，方法创新）
  C1 P2-L1 CFG 结构约束载荷（SPARC 式迁移）
  C2 P3-R1 落盘优先 + 失败分类学 + 确定性重试
  C3 P3-R2 局部编辑在多函数子集上重测（修正 R4 的单函数空洞）
  C4 P1-TO 拓扑消融（H2）
  C5 I-15 断言强度度量
阶段 D（M4–M6，前沿突破）
  D1 P4-B1 一手基准扩容（TestGenEval 许可门槛 → 改用 Apache/MIT 许可的 Python 仓库集）
  D2 P1-AS 编排小网格自动搜索
  D3 P2-L2 SMT 后件反例生成
  D4 P5-S1 默认安全档 + SLSA provenance + 人类门
```

### 10.4 里程碑与 KPI

| 里程碑 | 时间 | KPI（可验证） |
|---|---|---|
| **M1 口径诚实** | W2 | 4 个新门禁 exit 0；`plausible`/`precision` 分母一致；`tests`/`mypy` 数字与实测一致；A1 批次入库 |
| **M2 −28pp 归因定案** | W6 | P1-H1 + H2 给出判定性结论（无论方向），预注册 + 聚类校正 + ROPE |
| **M3 逻辑驱动首次可归因** | M2 | `spec_oracle_injected` 行级非零；oracle 通道对 detection 的贡献（含 0）有配对检验 |
| **M4 多通道检出协议** | M3 | detection ≥ 65%（QuixBugs 41，含 hang 通道与结构约束）；`over_red` ≤35% |
| **M5 修复追平前沿** | M4 | repair ≥ 60%（合成修正口径）；落盘率 ≥85%；QuixBugs repair 保持 ≥90% |
| **M6 外部有效性** | M6 | 至少在 1 个 ≥200 任务的**许可清洁**真实基准上报告 M1 三指标；protocol 与 TestForge/LaMAR 可对齐 |

---

## 11. 实验、验证与评估计划

### 11.1 基准策略（三层）

| 层 | 基准 | 规模 | 用途 | 许可/状态 |
|---|---|---|---|---|
| **L0 合成** | 自建 50 模板 | n=87（29 模板，n_eff≈40） | 快速迭代、消融 | 自有；**必须标注 n_eff** |
| **L1 真实小程序** | QuixBugs | 50 程序（41 有 gold） | 与 LaMAR 公共基准对齐 | MIT；**需锁 commit + submodule** |
| **L2 真实工程** | **待定**：TestGenEval（CC BY-NC 4.0，商用受限）／BugsInPy（无 SPDX）／自建 Apache-2.0 Python 仓库集 | ≥200 任务 | **外部有效性（当前最大缺口）** | **须先做许可决策** |

**关于 L2 的明确建议**：TestGenEval 的 **CC BY-NC 4.0** 对学术使用可行，
但对"产业影响力/商用"目标构成限制。建议**双轨**：
① 学术投稿用 TestGenEval（与 TestForge 直接可比）；
② 另建 Apache-2.0/MIT 许可的 Python 仓库集（≥200 任务），作为可商用的自有基准并开源。
**这是本项目在"影响力"维度上投入产出比最高的一件事。**

### 11.2 实验清单（预注册级）

| 编号 | 实验 | 自变量 | 基准/规模 | 主终点 | 判别规则 | 预算 |
|---|---|---|---|---|---|---|
| **EXP-0** | **现成工具基线对照**（红队 R4） | `{CrossHair+icontract, hypothesis, Pynguin, CodaMosa}` vs AITester | QuixBugs 41 | detection | 若现成工具检出 ≥ AITester → "逻辑驱动"无独立价值，路径 P2 需重定向 | 零 LLM（工具本地执行） |
| **EXP-1** | 载荷等价（H1） | `GENERATOR_PAYLOAD ∈ {full, df_parity}` | QuixBugs 41，cold cache | detection | ≥+20pp → H1 成立；≤5pp → 否证 | ≈1.4M token |
| **EXP-2** | 拓扑消融（H2） | `ENABLE_DEBUGGER on/off` | 同上 | detection | 同上 | ≈1.4M token |
| **EXP-3** | hang 通道 | `TEST_HANG_DETECTION_ENABLE on/off` | 同上 | detection；`None` 行数 | `None` → 0 且 detection 提升 | ≈1.4M token |
| **EXP-4** | 逻辑 oracle 贡献 | `SPEC_ORACLE_EXEC_ENABLE on/off` | 同上 + 合成 87 | `spec_oracle_verdict` 分布；detection 配对差 | 若注入率 <30% 先修暴露面再判 | ≈1.4M token |
| **EXP-5** | 结构约束载荷 | CFG 路径注入 on/off | 同上 | detection；`over_red` 占比 | `over_red` 60%→≤35% | ≈1.4M token |
| **EXP-6** | 编排自动搜索 | 32 组合 bandit | 12 任务子集 → Top-3 在 41 确认 | detection / token 双目标 | 找出 ≥1 组合 detection ≥83.8% ∧ token ≤2× df | ≈2M token |
| **EXP-7** | mutation 工具一致性 | 自研算子 vs cosmic-ray | 50 QuixBugs 离线 | Spearman 排序一致性 | ρ<0.7 → 当前指标不可用于跨系统比较 | 零 LLM |

### 11.3 统计协议（沿用并强化项目现有协议）

沿用：**McNemar（连续性校正）+ BH-FDR（α=0.05）+ 贝叶斯 Dirichlet 配对（ROPE ±5pp，MC seed=42）+ 模板聚类 DEFF 敏感性 + 模板级符号检验**。
**强化三点**：
1. **每个比例后强制附 `n_eff`**（A1 的 `n_eff = 39.9 / 174` 是因为 ICC=0.671、DEFF=4.356）；
2. **所有主终点必须报 `det_measured` 分母**（不能只报比例——45.9% 是 17/37 而非 17/50）；
3. **等价性检验优先于"不显著"**（项目已做对这一点，保持）。

### 11.4 可复现性要求（新增硬约束）

1. 每个实验产出：批次 JSON + 全量 trace + 统计报告 + `SHA256SUMS` + `env_snapshot`（**含全部 `*_ENABLE`**）+ 代码 SHA（`git_dirty=false`）；
2. **外部基准必须锁 commit**（submodule 或 manifest + SHA256）；
3. **反事实臂必须冷缓存**（`AITESTER_LLM_CACHE=0`）或显式声明 cache namespace 与复用范围；
4. **任何 B 类负结果（开关未生效、缓存短路、伪影）必须就地勘误并在 `BASELINE.yaml` 登记**（项目已建立该惯例，需保持）。

---

## 12. 风险、伦理与合规

### 12.1 风险登记

| # | 风险 | 类型 | 概率 | 影响 | 缓解（Plan B） |
|---|---|---|---|---|---|
| T1 | P1-H1 否证（载荷不是主因） | 技术 | 中 | −28pp 无法解释，主卖点缺失 | 转 H2（拓扑）→ 再转 EXP-0（现成工具）；若全部失败 → **把"编排系统性地劣于纯提示"做成正式负结果论文**（本身高价值） |
| T2 | 一手基准扩容受阻（许可/成本） | 数据 | 中 | 外部有效性无法补齐 | 自建 MIT/Apache Python 仓库集（≥200 任务），开源为贡献物 |
| T3 | 逻辑通道打开后贡献为 0 | 方法 | **中–高** | "逻辑驱动"主张需撤回 | 预先声明"含 0 结果"的发表计划；把贡献重心转向评估方法学（§10.1） |
| T4 | 基座模型升级使全部对照失效 | 竞争 | 高 | 增量归零 | "协议 × 模型能力"2×2 网格；声明模型档位依赖 |
| R1 | 复现性风险：嵌套 git 仓库、`/tmp` 证据、cache namespace 复用 | 复现 | **已发生** | 结论不可复核 | I-04 + §11.4 的 4 条硬约束 |
| R2 | 成本风险：每实验 ≈0.7–2M token | 成本 | 中 | 预算不足 | 先做零 LLM 前置（A1–A6 全部零 LLM）；两阶段设计（12 任务筛选 → 41 确认） |
| S1 | **默认在宿主 uid 执行 LLM 生成代码** | 安全 | 中 | 任意代码执行 | I-11：发布默认档含内核沙箱（fail-closed）+ 回滚 + 人类门 |
| S2 | 自动把 LLM 补丁写入工作树 | 安全 | 中 | 源码腐蚀 | 默认开启快照回滚 + `patch_abstain` 阻断档 |
| S3 | 供应链：SBOM info-only、无 SLSA provenance | 合规 | 中 | 审计不通过 | I-20：SBOM 转阻断 + provenance 生成 |
| S4 | LLM 缓存含 prompt/response 且为"已知可接受风险" | 隐私/合规 | 低–中 | 潜在数据残留 | 缓存目录 `chmod 700`；加 TTL 与显式清理目标 |

### 12.2 伦理与合规缺口（相对 2025–2026 视角）

| 项 | 现状 | 缺口 | 建议 |
|---|---|---|---|
| **用途边界** | `MODEL_CARD.md` 有定位，**无明确滥用条款**（"禁止自动提交补丁到生产"之类） | LLM 自动修复代码的滥用风险 | 补 `docs/compliance/acceptable_use.md`；在 CLI 启动时打印一次 |
| **风险分级** | 无 | EU AI Act 式风险分类缺失 | 补 `docs/compliance/risk_classification.md`（建议自评"有限风险 + 开发者工具"档，并声明不做自动部署） |
| **人类监督** | `risk_approval.py:57` 默认**关** | 高风险动作无人类门 | 分级默认：跨文件/低置信/高风险任务默认 `human_confirm` |
| **供应链证明** | SBOM info-only；grep 无 SLSA/provenance | 企业采用受阻 | I-20 |
| **数据许可** | QuixBugs MIT ✓；BugsInPy 无 SPDX ✗；TestGenEval CC BY-NC 4.0（商用受限）⚠️ | 商用路径不清晰 | §11.1 双轨基准策略 |
| **人类受试者/隐私** | 不涉及（无人类受试者；LLM API 调用含代码片段） | 需声明"代码片段发送至第三方 LLM API"的隐私含义 | `SECURITY.md`/`MODEL_CARD.md` 补一段数据出境说明 |
| **审计日志** | 有脱敏三层防线 + `audit/` | 无不可篡改审计链 | 可选：把关键决策（补丁落地/回滚/人类确认）写 append-only 日志 |

---

## 13. 待澄清问题

> 以下为我**无法从仓库推断**、需项目方确认的信息。回答后可直接改写 §4/§5 的相关判定。

| # | 问题 | 为什么重要 | 影响章节 |
|---|---|---|---|
| Q1 | 项目**对外发表的目标 venue 与时间线**是什么？（ICSE/FSE/ASE/ISSTA 2027-01 截稿？还是先发 arXiv？） | 决定是先补外部有效性（M6，6 个月）还是先补归因（M2，6 周） | §10.4 |
| Q2 | **商用/产业落地**是否是目标？ | 决定 TestGenEval（CC BY-NC）能否用，以及是否必须自建许可清洁基准 | §11.1 |
| Q3 | 是否**接受把主叙事从"多智能体/逻辑驱动"收缩为"多通道检出 + 评估方法学"**？ | 这是 §10.1 的核心建议；若不接受，则 C1/C2 必须先解决 | §10.1 |
| Q4 | `logic` 档**有意不含** `EXPERT_POOL_ENABLE`/辩论/RAG，是设计决策还是历史遗留？ | 若是设计决策，则"多智能体"标签应彻底弃用；若是遗留，则需补一次真正开多智能体的对照 | C1 / P1-AS |
| Q5 | `spec_compile_rate 0.472–0.517`（`BASELINE.yaml:488-499`）是**已登记口径**还是单批证据？为何 `target_quality` 节仍是 0.205–0.219？ | 对外引用哪个数字 | §3.4 / I-07 |
| Q6 | QuixBugs repair 对外应统一为 **37/40=92.5%** 还是 **37/41=90.2%**？（T4 实测 `quixbugs__node` 被重放判为 `wrong_patch`，而工件记 `repair_rate=null`） | 与 LaMAR 对标时的关键数字 | §4 / P3-R1 |
| Q7 | `data/quixbugs` 的 commit（`4257f44b…`）是否可写入 manifest？是否有上游许可/引用要求？ | 复现性 + 合规 | I-04 / §12.2 |
| Q8 | `/tmp/a1_fixed` 批次（我已核验 `PLAN_STRIP_EXPECTED_OUTPUT_ENABLE=true`、`cache_namespace=a1_strip`、19/37）**是否授权归档入库**？ | 该结论目前只能作"待复核"引用 | I-04 |
| Q9 | RT1 批次的 `DETECTION_FIRST_SECTION_ENABLE` 生效性是否可补证（重跑或日志）？ | "+43pp 归因提示协议"是项目重要正面结论，当前无审计证据 | I-02 |
| Q10 | 是否具备**微调/训练**算力与数据管线？（红队 R3） | 决定"零样本 vs 微调"对照是否需要写进路线图 | §8.1 R3 |
| Q11 | 是否有**外部合作者/审稿反馈**已提出过与 C1/C2 相同的问题？ | 避免重复劳动；也可能已有未入库的回应 | §9 |
| Q12 | `experiments/results/` 3,426 个受追踪文件是否长期保留？仓库体积（1.2 GB）是否可接受？ | 影响 CI 时长与克隆成本 | §10.2 |

---

## 14. 参考来源

### 14.1 本审查一手核验的外部来源（可用于投稿引用）

| # | 来源 | 类型 | 可信度 | 引用的数据点 |
|---|---|---|---|---|
| E1 | Jain K., Synnaeve G., Rozière B. **TestGenEval: A Real World Unit Test Generation and Test Completion Benchmark.** ICLR 2025（arXiv:2410.00752v2）https://arxiv.org/abs/2410.00752 | 顶会 + 预印本 | **A** | 基准规模：68,647 tests / 1,210 file pairs / 11 Python repos；median gold coverage 60.4%；**GPT-4o 单发 64.0% any-p@1 / 35.2% cov / 18.8% mutation**（all-p@1 仅 7.5%）。*注：v1 与 v2 对文件长度有冲突（1,157/943 vs 782/677 LOC）* |
| E2 | Jain K., Le Goues C. **TestForge: Feedback-Driven, Agentic Test Suite Generation.** arXiv:2503.14713 + CMU-S3D-25-100 https://ar5iv.labs.arxiv.org/html/2503.14713 | 预印本 + 技术报告 | **B**（待同行评审） | **pass@1 84.3% / line cov 44.4% / mutation score 33.8% / $0.63 per file**；25 轮；**coverage +9.6pp / mutation +15.0pp** vs 自身 0-shot（64.0/34.8/18.4）；**用 cosmic-ray 默认算子集**；**无法与 CoverUp 头对头比较**（≈$2/数据点） |
| E3 | Pizzorno J., Berger E. **CoverUp: Effective High Coverage Test Generation for Python.** FSE 2025 / PACMSE vol.2, DOI 10.1145/3729398 | 顶会 | **A** | CM 套件（425 模块 ≈100k LOC）：**63.8% line / 49.2% branch / 60.3% L+B**；median 82.4/66.7/79.6；MT 套件 89.2/88.7/89.0；成本 **$399 / 4.0h / 28,690 prompts**。**注意：非 TestGenEval 数值** |
| E4 | Chowdhury J. M., Fu C.-A., Jabbarvand R. **SPARC: Scenario Planning and Reasoning for Automated C Unit Test Generation.** arXiv:2602.16671（2026-02-18）https://arxiv.org/abs/2602.16671 | 预印本 | **B**（待同行评审） | **+31.36% line / +26.01% branch / +20.78% mutation** vs vanilla prompt；匹配或超过 **KLEE**；测试保留率 94.3%；59 subjects |
| E5 | Jiao R., Zhang Y., Feng Z., Li J. **LaMAR: Latent Multi-agent Collaboration via KV-Cache Communication for Automated Program Repair.** ASE 2026（DOI 10.1145/3832783.3837423）https://conf.researchr.org/details/ase-2026/ase-2026-research-track/127/ | **顶会** | **A** | **Repair success：Defects4J 24.5%（Qwen3-8B）；DebugBench 与 QuixBugs 62.1–87.5%**；LAC 证明连续空间信道信息容量**严格更高**，token 复杂度 **O(N²)→O(N)**；消融：bug analysis chain 与 latent communication 为最关键组件 |
| E6 | Konstantinou, Degiovanni, Papadakis. **How well LLM-based test generation techniques perform with newer LLM versions?** **ICST 2026 Research Papers**（arXiv:2601.09695） | **顶会** | **A** | 6 个完整 Java 仓库 / 393 类 / 3,657 方法：**Plain-LLM 49.95/35.33/33.82 > HITS 42.43/29.49/27.97 > SymPrompt 40.95/27.19/28.40 > CoverUp 38.85/25.11/26.26 > TestSpark 23.65/16.48/13.88**；请求数 11,718 vs CoverUp 12,264 vs HITS 23,865；**≈20% 不编译 / ≈43% 不通过**。**这是 README 中 CANDOR 引用的正确替代** |
| E7 | Xu, Wang, Briand, Liu. **Hallucination to Consensus: Multi-Agent LLMs for End-to-End JUnit Test Generation.** **TOSEM 2026**（DOI 10.1145/3803418，arXiv:2506.02943） | **顶刊** | **A** | **CANDOR** 原文：line/branch/mutation **0.991/0.970/0.980**（HumanEvalJava）、**0.990/0.949/0.939**（LeetCode-Med）、**0.989/0.980/0.937**（LeetCode-Hard）；oracle correctness **0.971/0.993/0.961**。**注意：原文结论对多智能体为正**，与 IEEE 复现研究（E25b）在 mutation score 上的不利结果**方向相反**——引用时须并列 |
| E25b | Radaideh & Corriveau. **Understanding the Effect of Agentic Iteration on LLM-Based Unit Test Generation: A Comparison with Human-Written Tests Using Mutation Testing.** IEEE Xplore 文档 **11655121** | 期刊/会议（IEEE） | **A（一手定位）** | **one-shot Gemini 2.5 Flash 88.35% mutation score vs CANDOR 35.92%**；**one-shot GPT-4o 69.90% vs CANDOR 45.63%**。**这是 README 中"88.35% vs 35.92%"的真实出处**（被误挂到"CANDOR, ICST 2026"名下）。注：**该数字是 mutation score，不是 line coverage** |
| E8 | Shang et al. **TestAgent.** **FSE Companion 2026**（DOI 10.1145/3803437.3806428，arXiv:2607.09101） | 顶会 companion | **A** | 6 Java 项目 / 1,451 方法：**执行率 97.46% / line 92.34% / branch 90.24% / mutation 83.69%**；检出 154 个真实 bug，精确率 92.22% |
| E9 | Huang, Zhang, Harman, Zhang, Du, Ng. **ULT / UnLeakedTestbench.** **TOSEM 2026**（DOI 10.1145/3805043，arXiv:2508.00408） | **顶刊** | **A** | **去泄漏 ULT 3,909 函数级任务**（cyclomatic ≥10，均值 14.87）；**ULT 41.32/45.10/30.22/40.21** vs **PLT 47.07/55.13/40.07/50.80** vs **TestEval 91.79/92.18/82.04/49.69**；**最佳单模型仅 17.83% Pass@1**；协议：K-query 迭代 / greedy temp 0.0 / ≤1,024 token / **cosmic-ray + 120s**。**本项目最可对齐的公共协议** |
| E10 | Sun et al. **SWE-Mutation.** **Findings of ACL 2026**（DOI 10.18653/v1/2026.findings-acl.1976） | 顶会 Findings | **A** | 2,636 变异体 / 800 实例 / 9 语言；最强 Claude-sonnet-4.5+Claude Code **98.00 / 40.40 / 71.71**；DeepSeek-V3.1 **88.20 / 10.20 / 36.15**；**agentic 变异使平均检出 71.04% → 39.81%** |
| E11 | Wang, Xu, Briand, Liu. **MUTGEN.** **TSE 2026**（DOI 10.1109/tse.2026.3682975） | **顶刊** | **A** | 204 subjects / 2 基准；**关键发现：部分套件 100% line coverage 仅 4% mutation score** |
| E12 | Chang et al. **AdverTest.** **PACMSE vol.3（ISSTA 2026）**（DOI 10.1145/3832122） | 顶会 | **A** | **fault detection +8.56% over 最强 LLM 方法；+50.20% over EvoSuite**（Defects4J） |
| E13 | Molinelli, Martin-Lopez, Zackrone, Eken, Ernst, Pezzè. **Tratto.** **ISSTA 2025**（DOI 10.1145/3728960，arXiv:2504.04251） | 顶会 | **A** | 公理式 oracle：**73% acc / 72% prec / 61% F1**（Jdoctor 61/62/25；GPT-4 few-shot+CoT 40/24/37）；追加到 EvoSuite 套件使 mutation **25%→32%**、**55%→56%**；**GPT-4 有 552/1,213（45.5%）oracle 不可编译** |
| E14 | Tufano et al. (Google). **Spec-driven test generation.** **SpecOps '26**（DOI 10.1145/3842652.3843195） | workshop | **B** | **规格驱动 +9.8pp bug detection（p=0.0352）/ +2.5pp branch cov（p=0.0034）**；LLM-as-judge 优于基线 77.8%、优于人类测试 56.7%。**与本项目 spec 层主张同构的已发表正向证据** |
| E15 | Alshahwan et al. **TestGen-LLM (Meta).** **FSE 2024 Industry**（DOI 10.1145/3663529.3663839） | 顶会 Industry | **A** | Instagram/Facebook（Kotlin）：**75% built / 57% passed reliably / 25% 提升覆盖率**；部署中被采纳 **73%** |
| E16 | Arnaudo, Coppola, Morisio et al. **Automated Black-Box Testing: A Comparative Study of LLM Agent Architectures and Prompt Engineering.** **ICST 2026 ASTA workshop** | workshop | **B** | HumanEval 黑盒：multi-agent coverage 峰值 **99.75%**，**ESR 97.31% vs single 97.25%（持平）**，token **3–4×**；结论：**提示工程才是主驱动**（+20–30%） |
| E17 | **Prometheus: Towards Long-Horizon Codebase Navigation for Repository-Level Problem Solving.** arXiv:2507.19942 | 预印本 | **B** | SWE-bench Verified **74.4%** resolve rate |
| E18 | **BOAD: Discovering Hierarchical Software Engineering Agents via Bandit Optimization.** arXiv:2512.23631（IBM Research, ICLR 2026） | 预印本 | **B** | 多臂老虎机发现层级智能体。**注意：这是仓库级 SWE 任务解决，不是测试生成**——README 用它支撑测试生成论证属**引用错位** |
| E19 | **AgentCoder.** arXiv:2312.13010 | 预印本 | **B** | multi vs single 消融：line coverage **87.5/89.5 vs 72.5/75.9 = +15.0/+13.6pp**（HumanEval/MBPP **canonical solutions**）。**这是"13–15% 覆盖率增益"的真实出处**（非真实仓库任务） |
| E20 | Ma et al. **MUATC.** **APSEC 2025**（DOI 10.1109/APSEC66846.2025.00028） | 会议 | **A（摘要级）** | coverage vs CoverUp **+4.8%–5.5%**；ChatUniTest 数据集 **+12.7%**。**逐系统表未核验（付费墙）** |
| E21 | **Agentic AI for Self-Healing Microservices: An LLM-Orchestrated Framework…** SCITEPRESS 2026 | 会议 | **C** | 框架参考（**未取到量化指标**） |
| E22 | arXiv:2606.28958 | 预印本 | **B** | **反证据**：latent-channel 风险应在其被当作默认协作方式之前可见——路径 P1-AS/P4-C1 必须正面回应 |
| E23 | QuixBugs（本机 `data/quixbugs`，commit `4257f44b…`） | 数据集 | — | 50 Python 程序（41 有 gold）+ 42 个 `json_testcases` |
| E24 | 补充候选基准（**数值未核验，建议纳入 §11.1 的 L2 候选**）：SWT-Bench（NeurIPS 2024 D&B，1,762 实例）；Multi-SWT-Bench（1,963 实例/8 语言）；TAM-Eval（1,539 场景）；TEBench（314 实例/10 项目）；CovQValue（TestGenEval-Lite branch cov +51–77% 相对） | — | — | 用于 L2 外部有效性扩容的候选池 |
| E25 | **swebench.com 官方 leaderboard 内嵌 JSON**（500 Verified 实例，per-instance cost + API calls；最新提交 2026-02-26） | 官方榜单 | **A（一手提取）** | **MiniMax M2.5 = 75.8% @ $0.0733/instance（60.5 calls）** vs **Claude 4.5 Opus = 76.8% @ $0.7539**（便宜 **10.3×** 只差 1.0pp）；官方最优 **79.2%**（2025-12-15）；成本区间 $0.0281（DeepSeek V3.2R, 60.0%）→ $1.5311（GPT-4o, 21.6%）。**警告：第三方聚合站宣传 96%，benchlm.ai 自认"94 行中 0 行来自基准所有者或独立运行，88 行是厂商自报"** |
| E26 | **MultiFixer.** arXiv:2607.26591 | 预印本 | **B** | **420/835 = 50.3%** on **Defects4J v2.0**（Claude-3.5-Sonnet；基座模型 326）。当前核验到的最强真实缺陷 Java APR 数字 |
| E27 | **FedDualFix.** Applied Soft Computing 202:115898 | 期刊 | **A** | CR 58 / PR 84 / **P@1 52.1%**（Defects4J v2.0，GPT-4o）；同后端 Direct = 49/44.1%；**plausible-but-incorrect = 26/84 = 31.0%**；3.3k tok/bug、$0.007–0.028/bug。**plausible vs correct 双报的范例** |
| E28 | **LANTERN.** ICSE 2026（DOI 10.1145/3744916.3773227） | **顶会** | **A** | **+22.09% Pass@10（Rust）**，DeepSeek-V3，多智能体；p=0.0126，Cliff's δ=0.64；xCodeEval APR 子集（基线 Rust Pass@10 = 65.58%） |
| E29 | **ADI.** PACMSE 2026（DOI 10.1145/3797126） | 顶会 | **A** | SWE-bench Verified **63.8%**，**$1.28/task**，Claude-Sonnet-3.7，动态分析增强 |
| E30 | **TwinMem-Agent.** FSE **Companion** 2026 | 顶会 companion | **B** | 89.1% Pass@1 vs 60.0% 基线（**SWE-Bench Pro 的 200 实例分层子集**，非 1,865 全集）；**$0.0044/instance 低于所有官方 agentic 运行 6–17×** → **18× 成本主张可疑** |
| E31 | Li, Yu & Yuan (Beihang University). **Escaping the Self-Repair Trap: Improving Test Oracle Generation via Dual-Context Awareness.** **ASE 2026**（arXiv:2608.05917） | **顶会** | **A** | "迭代修复逐步把模型推向**更容易满足但更不擅长检出故障**的断言"。**注：该文针对回归 oracle/测试生成，正是本项目核心病理（−28pp / false_fix 87.2%）的已发表机制解释——不引用会被审稿人视为重复发现** |
| E32 | Cheng et al. (Google). **Abstain and Validate.** **ICSE-SEIP 2026**（arXiv:2510.03217） | 顶会 SEIP | **A（摘要级）** | 174 个 Google 缺陷：缺陷弃权 **+13pp**、补丁验证 **+15pp**、**组合最高 +39pp**。**本项目 `patch_abstain`（弃权精确率 85.97%）的量化参照**。⚠️ **正文设置未核实**：+39pp 的基线、任务与分母需获取全文确认后才能作为护城河叙事 |
| E33 | **ImpossibleBench: Measuring LLMs' Propensity of Exploiting Test Cases.** **ICLR 2026** | 顶会 | **A** | 把单元测试改写为与自然语言规范直接冲突的"不可能任务"，使**pass-rate 等价于 cheating-rate（构造使然）**——提供 0 噪声的 reward-hacking 可测指标。本项目 `false_fix=87.2%` 的同构已发表证据，也是"挂起信号"研究的现成方法论框架 |
| E32 | **Abstain and Validate.** **ICSE-SEIP 2026**（arXiv:2510.03217） | 顶会 SEIP | **A** | 174 个 Google 缺陷：缺陷弃权 **+13pp**、补丁验证 **+15pp**、**组合最高 +39pp**。**本项目 `patch_abstain` 的量化参照** |
| E33 | **ImpossibleBench.** **ICLR 2026** | 顶会 | **A** | **pass-rate 等价于 cheating-rate（构造使然）**——本项目 `false_fix=87.2%` 的同构已发表证据 |
| E34 | **HEJ-Robust.** **AIware 2026** | 会议 | **A** | 1,450 个语义保持变换实例；性能**下降 >50%**。**零成本可补测的鲁棒性维度** |
| E35 | **"Whose Oracle Is It?"** | 会议 | — | **93.0%（160/172）** 真实 test-changing 修复改动的是一份已存在的测试工件 → "锁定测试防作弊"不是可部署答案 |
| E36 | ⚠️ **不可引用来源（R2 核验）**：`github.com/suhail39ahmed/self-healing-azure-pipelines`（"85% MTTR" 的唯一来源，个人 README）；VIGIL 单作者预印本（n=12，无基线）；ESBMC-AI（无成功率）；agent-sandbox-runtime（无指标）。**ARC-APR 疑似不存在；Defects4J v3 不存在；AgentRepair 无可获取指标；DEIMerge 摘要被出版方隐去** | — | **C / 不存在** | **这些条目不得进入任何对外文档** |
| E37 | **GORDIAN**（Bouras & Mechtaev）. PACMSE, DOI **10.1145/3832126**, arXiv:2603.19239 | 顶会 | **A** | **真正的 2026 SMT+LLM SOTA**：建在 KLEE 之上，LLM 生成 ghost code 使求解器可处理 solver-hostile 片段；**+28.5–115.2% 覆盖率 over 传统符号执行；+74.1–189.8% over LLM 符号执行基线；token 削减 91–96%** |
| E38 | **SWE-PROOF.** arXiv:2609.21190v2（2026-09） | 预印本 | **B** | SWE-bench Verified → 500 个形式化验证 issue；**约 25% 的"测试通过"LLM 补丁存在反例**；**忠实形式化规格使解决率 85%→95%（NL 规格无效）**；**仅 56% 的 agent 自写规格通过审计**；规格在未解决 issue 上失败率 92% vs 已解决 51%。**R3 结论：2026 瓶颈是规格合成与保真审计** |
| E39 | Zhao, Zhou & Cohen. ISSTA 2026, DOI **10.1145/3832093**, arXiv:2607.22880 | 顶会 | **A** | 11 个 LLM / 13 种设定 / **>100,000 测试** / Defects4J v3.0：覆盖+变异在**回归（无缺陷代码）**设定下做**跨模型比较有效**（branch vs raw mutation **r=0.780** @k=10，控制规模后），在**被测代码可能有缺陷**时**不可靠**；并**反驳 Inozemtseva** 的"套件规模是强混杂因子"。**⚠️ 这是"覆盖率批评"的正确出处——此前被误挂到 ULT 名下** |
| E40 | **TEST WARS.** arXiv:2501.10200 | 预印本 | **B** | GitBug Java：**LLM（TestSpark）在覆盖率与真实缺陷检出上同时输给 EvoSuite（SBST）与 Kex（符号执行），仅在 mutation score 上获胜** |
| E41 | **TestTailor.** FSE 2026, DOI 10.1145/3797140 | **顶会** | **A** | 神经符号，Python **CODAMOSA 486 模块**：**+5.01% 语句 / +4.17% 分支 over CoverUp @ API 成本 −60%**；覆盖率准确率 85.2%。**当前最强 Python 基线** |
| E42 | **NeuroTestGen.** arXiv:2609.30178 | 预印本 | **B** | Z3 + LLM，Defects4J **2,971 方法**：92.91% line / 88.89% branch / 96.88% pass（Sonnet 4.6）。**关键：纯符号消融已达 92.35%/88.15% → SMT 对前沿模型仅 +0.56pp** |
| E43 | **Panta.** ICSE 2026, DOI 10.1145/3744916.3764553 | **顶会** | **A** | +26% line / +23% branch |
| E44 | **PropGen.** arXiv:2604.13463v2 | 预印本 | **B** | **92.6% 属性有效率（912/985）**；25 个新 bug |
| E45 | **Agentic PBT.** NeurIPS 2025 DL4C, arXiv:2510.09907（含 Hypothesis 作者 Hatfield-Dodds） | workshop | **B** | 100 个 Python 包：56% 有效 bug / 32% 可报告 / top-21 86% 有效；**3 个补丁被合并（含 NumPy）** |
| E46 | **SpecPylot.** FSE Companion '26 | 顶会 companion | **A** | `icontract` + `CrossHair`——**唯一的同行评议 Python 契约流水线**；**故意不公布成功率** |
| E47 | **DSpec2Test**（arXiv:2609.29713）；**LM2Alloy**（arXiv:2607.18555）；**AxDafny**（arXiv:2606.32007）；**DafnyPro**（arXiv:2601.05385）；**SESpec**（arXiv:2506.09550v4）；**LLM-Falsifier**（arXiv:2609.20752） | 预印本 | **B** | (d) NL→形式化规格方向：DSpec2Test **93.9% 变异击杀 vs 82.4%**；LM2Alloy **发现一个 68% 分支覆盖的直接 LLM 基线 3 次都漏掉的真实缺陷**；AxDafny **92.7% DafnyBench**；DafnyPro 86%；SESpec 按循环复杂度 97%/77%/63%；LLM-Falsifier 在 ARCH-COMP 上 14/21 规格获胜（**时序逻辑仅作伪造目标，无一篇把 LTL/MTL 编译为单元测试**） |
| E48 | ⚠️ **R3 核验为不存在或不可引用**：**SymLLM / LLM4Sym / ChatTCG / µBert**（arXiv 全文与网络检索**零学术来源**，疑似不存在）；**TSC2CARLA**（Borchers et al., DLR, *Sci. Comput. Program.* 242(2025)103256 为真、Grade A，TSC = 一阶逻辑 + Z3 → CARLA，但全文仅声称"**可行性初步证据**"，**无任何覆盖率/检出数字**——引用其数字即曲解）；**Gena**（ASE 2025 论文为真，DOI 10.1109/ASE63991.2025.00240，但工具名与数字未核验）；**CrossHair / PyExZ3**（**无同行评议论文**，Grade C）；**ESBMC-AI**（arXiv 2305.14752 有数字 90.40%/86.47%/70.27%/69.66%，但**论文内部不一致**：摘要称 50,000 个 C 程序 vs 贡献节 "over 1,000"） | — | **不存在 / C** | **不得进入任何对外文档** |

### 14.2 项目内部一手来源（工件级，可复算）

| # | 路径 | 用途 |
|---|---|---|
| P1 | `BASELINE.yaml`（611 行） | 机器可读单一事实来源 |
| P2 | `experiments/results/e6_a1_batches/e4_quixbugs_FIXED_harness/{aitester,plain_llm_df}.json` | QuixBugs 修正结算（17/37、31/37、90.2%） |
| P3 | `experiments/results/main_batch/{corrected_report_v2.md, target_quality_report.md, repair_ceiling_report.md, statistical_report_3seed_pooled.md}` | 修正口径与统计报告 |
| P4 | `experiments/results/swe_bench_lite_20/benchmark_swe_bench_20260818_113525.json` | SWE-bench 失败分支工件（本审查 F7 对象） |
| P5 | `/tmp/a1_fixed/benchmark_quixbugs_20261010_113757.json` | A1 首次真正生效批次（**未归档**） |
| P6 | `docs/{preregistration.md, adr/*, design/repair_caliber_matrix.md, DATA_CARD.md, threat_model.md}`、`MODEL_CARD.md`、`SECURITY.md` | 方法学与合规 |

### 14.3 本审查产出的配套文件

| 文件 | 内容 |
|---|---|
| `review_2026/T1_inventory.md`（416 行） | 工作目录索引、122 条文件清单、关键文件摘要、缺失/敏感清单、范围声明 |
| `review_2026/T2_python_audit.md`（608 行） | Python 10 维度专项诊断，逐条 file:line / 命令原文 |
| `review_2026/T3_domain_audit.md`（494 行） | 领域 8 维度诊断、评分表、6 条红队反例、H1 预注册级实验设计 |
| `review_2026/T4_claims_audit.md`（583 行） | 10 条对外声明的对抗式核验（支持 3 / 部分支持 7 / 不支持 0）、TOP 5 口径风险、复现代码附录 |
| `review_2026/LEAD_findings.md`（127 行） | Lead 一手复核原始记录（F1–F8） |
| `review_2026/REPORT_draft.md` | 本报告的中间草稿（保留供追溯） |
| **`REVIEW_2026_FRONTIER.md`** | **本报告** |

### 14.4 我未能核验的引用（**投稿前必须逐条补齐**）

以下数据在**项目文档中被引用**，但**我在本次审查中未能一手确认**。
按项目自身的诚实惯例（`CHANGELOG.md:146-150` 已把 2026 新文献统一标注 `[待核验]`），
**这些条目在投稿前必须逐条到原始出处核对，否则删去**：

| 条目 | 出处（项目文档） | 待核验内容 |
|---|---|---|
| CANDOR（ICST 2026）：one-shot Gemini 88.35% vs CANDOR 35.92%，45s vs 50h | `README.md:9-14` | 论文是否存在、数字是否准确 |
| BOAD（ICLR 2026）：bandit 自动搜索层级多智能体超越更大单模型 | `README.md:9-14` | 同上 |
| LANTERN（ICSE 2026）：Rust Pass@10 +22.09% | 任务描述 / 项目文档 | 已定位到 ICSE 2026 与 ACM DOI 10.1145/3744916.3773227；**具体数字未核验** |
| FedDualFix：52.1% Top-1 precision / 58 correct repairs | 任务描述 | 来源未定位 |
| TraceCoder / AgentRepair / DEIMerge / PhoenixRepair | 任务描述 | 来源未定位 |
| TwinMem-Agent：SWE-Bench Pro 89.1% Pass@1 vs 60.0%，成本降 18× | 任务描述 | 来源未定位；量级可疑，**建议删除或核验** |
| ADI：SWE-bench Verified 63.8% | 任务描述 | 来源未定位 |
| MUATC：比 CoverUp 提升 4.8–5.5% 覆盖率 | 任务描述 | 来源未定位 |
| ULT/UnLeakedTestbench：45.10% stmt / 40.21% mutation | `BASELINE.yaml:49` | 已定位仓库 https://github.com/huangd1999/UnLeakedTestBench（本次抓取被网络策略拒绝）；**数值未核验** |
| RunBugRun 716,900 pairs / xCodeEval 5,068 bugs / LogicEval 122 vulnerabilities | 任务描述 | 规模数字均未核验 |
| MTTR reduction 85%；VIGIL / FTDI / ESBMC-AI 的具体指标 | 任务描述 | 来源未定位；**85% 疑为厂商口径** |
| Tratto（ISSTA 2025）axiomatic test oracles | 任务描述 | 来源未定位 |
| LogiCase（CCFG + CodeT5）、TSC2CARLA、Alloy 组合测试 | 任务描述 | 来源未定位 |

**建议的补齐检索**：
- 数据库：**ACM DL、IEEE Xplore、DBLP、arXiv、OpenReview、Semantic Scholar**
- 关键词：`multi-agent program repair`、`latent communication agent`、`LLM test generation benchmark`、`mutation score LLM tests`、`neuro-symbolic test generation`、`specification-based test generation`、`self-healing LLM agent`
- 筛选：2025-01 之后；venue ∈ {ICSE, FSE, ASE, ISSTA, TOSEM, TSE, OOPSLA, NeurIPS, ICLR, ACL, CAV, TACAS}；有一手工件或可复现包

---

## 附录 A：本审查的边界与诚实声明

1. **本次审查未运行任何调用 LLM 的实验**（无预算、无密钥授权）。所有项目侧数字来自**存量工件的只读重算**。
2. **未修改仓库任何既有文件**；全部产出在 `review_2026/`（新增目录，`git status` 仅显示 `?? review_2026/`）。
3. **外部前沿基线覆盖（已更新）**：测试生成（§3.1）、**APR / 多智能体修复（§3.2，经 R2 一手核验）**、
   逻辑驱动（§3.4）、评估基准（§3.5）四个子方向已建立**一手核验**基线；
   **自修复 / 运行时反思（§3.3）经 R2 核验后的结论是"该子方向的前沿量化基线基本不成立"**——
   流传的 85% MTTR 来自个人 GitHub README，VIGIL 为 n=12 无对照案例研究。
   本报告选择**如实留白并说明原因**，而非用未核验数字填表。
4. **子任务交付情况（最终）**：派出的 4 个代码审计子任务（T1–T4）**全部交付**（合计 2,101 行）；
   派出的 **3 个前沿检索子任务（R1/R2/R3）现已全部交付**（614 + 392 + 357 行，合计 1,363 行）。
   三个子任务共**纠正了任务简报与本报告初版中的 8 处引用错误**：
   - **R1**：发现 README 的 CANDOR 引用无法证实（后经用户指正 + Lead 复核，定性为**错误归属**而非编造，见 §3.6）；
   - **R2**：发现"85% MTTR"来源为个人 GitHub README；VIGIL 为 n=12 无基线；ARC-APR/Defects4J v3 不存在；
     TwinMem-Agent 的 18× 成本主张可疑；**latent comms 无实测成本收益**；
   - **R3**：发现 **SPARC 不含 SMT**（真正的 SMT+LLM SOTA 是 **GORDIAN**）；
     **"ULT/TOSEM 2026 覆盖率弱相关"是双重误归属**（正确出处为 **Zhao, Zhou & Cohen, ISSTA 2026**，
     且结论为限定性）；
     **SymLLM/LLM4Sym/ChatTCG/µBert 无任何学术来源**；**TSC2CARLA 无可用数字**；
     并指出 **2026 的真正瓶颈是"规格合成与保真审计"**（SWE-PROOF：仅 56% 的 agent 自写规格通过审计，
     忠实形式化规格使补丁解决率 85%→95%）。
   **本报告的两处初版判断已被 R3 更正并就地修订**（§3.4 更正框、§3.5 更正框、§2.2 的 A3 行）。
   **交付质量评估**：三个子任务均为一手来源核验、逐条标注 DOI/arXiv 与可信度、并主动列出"无法核验"清单——
   这一质量水平构成了本次审查最可靠的部分。
5. **一份工件未归档**：`/tmp/a1_fixed`（A1 首次真正生效批次）。我已核验其
   `PLAN_STRIP_EXPECTED_OUTPUT_ENABLE=true`、`cache_namespace=a1_strip`、`git_sha=425f83d`、detection 19/37、
   specificity `specific_red 21 / over_red 26`，与 `BASELINE.yaml:409-419` 登记一致，**证据真实但按 I-04 应立即归档**。
6. **`fl_at_k` 的初判被否证并已更正**：我最初观察到"谱系定位全零"，T4 独立核验发现该批有 12 行 `fl_at_1=1.0`，
   仅 16 行全零（df 臂才是 50/50 `null`）；localization 分母应为 37。
   §4 已采用 T4 的 29/37、30/37、MRR 0.797。
7. **三处分母必须区分**：QuixBugs 的 detection 分母是 37、token 是 41、批次是 50。
   任何跨行引用都会复算失败（T4 已将 token 倍数从 8.4× 修正为"41 行口径 8.4× / 全 50 行 6.6×"）。
8. **CANDOR 引用事件的两级核验**：R1 研究子任务独立发现该引用无法证实；
   我本人随后用 `web_search` 独立确认（ICST 2026 存在 Konstantinou et al. 且 CANDOR 实为 TOSEM 2026）。
   **两次独立核验一致**，故本报告将其列为 P0 级发现。
9. **`tests` 计数的三个值**：`BASELINE.yaml` 写 5015，同页另写 5107+3，T2 实测 `--collect-only` = 5178、
   实跑 5175 passed + 3 skipped。本报告一律引用**实测值**并标注该矛盾（I-13）。

---

## 附录 B：执行记录（2026-10-10 落地批次）

> 本附录记录**按用户指令实际执行**的 11 项行动。
> 区分三种状态：**已落地**（改码/改文档 + 测试证据）、**已就绪未跑**（需授权预算）、**如实记录为不可执行**。
> **本批次全程未调用任何 LLM**（无授权预算分支）。

### B.1 已落地（可验证）

| # | 行动 | 落点 | 验证证据 |
|---|---|---|---|
| 1 | **修正 88.35%/35.92% 的错误归属**（三方并列表述，撤回"共识"） | `README.md:12-34`、`README.en.md:12-40`、`CHANGELOG.md:128-142` | 三处已改写；IEEE 11655121 / CANDOR TOSEM 2026 (DOI 10.1145/3803418) / Konstantinou et al. ICST 2026 并列 |
| 2 | **替换唯一有效对标基线**（TestForge 作小规模契约任务锚点） | 本报告 §3.1（**未写进 README**——避免继续堆叠未经核验的外部数字） | pass@1 84.3% / line 44.4% / mutation 33.8% @ $0.63/file（arXiv:2503.14713） |
| 3 | **引入 Self-Repair Trap 作为理论框架** | 本报告 §3.2.2、§14.1 E31 | Li, Yu & Yuan, **ASE 2026**（arXiv:2608.05917） |
| 4 | **引入 ImpossibleBench 作为 reward-hacking 方法论** | 本报告 §3.2.2、§14.1 E33 | **ICLR 2026**；pass-rate ≡ cheating-rate |
| 5 | **修正 ULT 引用误归属** | `BASELINE.yaml:62`（note 重写）、本报告 §3.5 更正框、§2.2 A3 行 | 正确出处 Zhao, Zhou & Cohen, **ISSTA 2026**（DOI 10.1145/3832093） |
| 6 | **逻辑通道度量/注入对齐** | `src/specs/spec_ir_v2.py`（`_clause_is_compilable` + `_select_compile_channels`，四门全保留）+ `result`→`r` 精准别名（依据 `templates.py:48/50/93`） | `pytest tests/test_spec_oracle_metrics.py tests/test_spec_ir_v2.py tests/test_ac_batch.py` → **112 passed / 1 xfailed**；ruff + mypy 全绿 |
| 7 | **新增行级指标 `spec_oracle_injected` / `spec_oracle_verdict`** 并**透出到结果行** | `src/graph/state.py:408-419,735-739`、`src/graph/nodes.py:159-290`、**`experiments/run_benchmark.py`：成功分支 + 失败分支各 1 处**、`BASELINE.yaml` `metrics_schema`（39 键） | 键字面量各 3 处；失败分支 None 占位保持键集合同构；`pytest -k run_benchmark` → **15 passed** |
| 8 | **修复"死门禁" `check_citations.py`** | `scripts/gates/check_citations.py`（`DEFAULT_GLOBS` 由**空列表**改为真实文档集；新增 `--traceability`、`--allowlist`；**扫描面为空即 FAIL**，防门禁随文档删除而静默失效） | `--traceability` → 4 处发现全部登记于 `docs/citation_allowlist.txt` 后 **exit 0**；ruff 全绿 |
| 9 | **env_snapshot 门禁 + 关闭最高风险缺口** | 新增 `scripts/gates/check_env_snapshot_keys.py`（AST，支持模块级常量间接引用）；`experiments/run_benchmark.py` 补入 **11 个默认开开关 + `SPEC_ORACLE_EXEC_ENABLE`** | 门禁现正确 **exit 1**（剩余 46 键未补，属 P1/P2/P3 档，见 `review_2026/E2_env_snapshot_report.md`） |
| 10 | **围栏回灌重算（零 LLM，16 批 + e6 全量）** | `scripts/tools/refresh_patch_field.py` → `review_2026/E2_fence_recompute.md` | **862/862** 带补丁行围栏残留；`patch_written` **460 → wellformed 862**；`written=0 & correct=1` **88 行**；QuixBugs FIXED 批重算精确率 **74.0%**（原口径 142.3%，即 >1） |
| 11 | **四通道零 LLM 重算 + H1 预注册** | `experiments/four_channel_recompute.py`、`docs/design/payload_equivalence_prereg.md`、`experiments/run_payload_ab.py` → `review_2026/E3_*.md` | 见 B.2 |

### B.2 关键执行发现（改变了原有结论）

1. **🔴 "逻辑通道零注入"是错的（本报告自纠）**：实测 QuixBugs FIXED 批 **18/50（36%）行注入了**
   `test_specir_v2_oracle`；成因是此前**无任何行级字段可观测注入**（`spec_oracle_injected` 虽在
   `BASELINE.yaml:110-112` 有注释，却**从未进 `metrics_schema`、从未产出**——"文档化了但未实现"）。
   本次已在 `state.py`+`nodes.py`+`run_benchmark.py` 三处闭环。
   **注入组 detection 反而更低（31% vs 57%），但这是观察性关联（存在混淆），不能解读为因果。**

2. **🔴 "over_red 里相当一部分是挂起"被证否**：30 行 `over_red` 中仅 **1 行**有挂起痕迹（3.3%）；
   且**门口径下 over_red 与挂起互斥**。全库普查 1157 行：挂起仅 **17 例且全在 QuixBugs**
   （合成批次 957 行 **0 例**）⇒ **挂起通道的收益不可外推**。

3. **挂起通道的价值是"救不可测"，不是"救 0"**：2×2 中"执行=0 但挂起=1"格子 **= 0**，
   已证明 **C1=0 ⇒ C2=0**。救回 2 行（bitcount / find_first_in_sorted，41 口径 **+4.9pp**）。
   **但 M1 裁决层未落盘 `rc_buggy`/`rc_fixed`，只能记 `not_available`**——
   判定级结论需先在 `_m1_metrics.py:298/473/519` 补 4 个字段。

4. **H1 载荷等价实验现在不可执行，且不是预算问题**：dry-run 实测 **4 项前置门全红**——
   围栏残留 50/50、`GENERATOR_PAYLOAD` 未入 `_env_snapshot_keys`、CI 门禁 `DEFAULT_SELECT='_ENABLE$'`
   不覆盖非 `_ENABLE` 键、`src/` 无消费者。**此刻强跑会重演 A1 首跑的假阴性**
   （开关未生效却被当成零效应）。`run_payload_ab.py --confirm-budget` 现**硬拒绝 exit 3**。

5. **任务书的字段名有误（已订正）**：`boundaries` **不是 plan JSON 字段**，而是 SpecIR/CFG 的独立注入段
   （由 `BOUNDARY_TRIPLETS_ENABLE` 控制）；`edge_cases` 实际位于 `logic_analysis.edge_cases`
   而非 `test_cases[]`。预注册附录 A 按实码列出 20 项。

6. **弃权+验证的"+39pp"不可直接引用**：核实正文后确认——基线 ftp@1=0.11、174 bug / 20 轨迹 / 25 步、
   单用 0.21/0.29、组合 0.35/0.53；但**摘要的 13/15/39pp 与正文的 +10/+18/+24/+42pp 不自洽**，
   且 **+39pp 的分母是过滤后子集**。设计文档已立引用红线：**禁止写"可得 +39pp"**。

7. **ULT 桥接受许可阻塞**：The Stack v2 = `license: other` + gated + 四条款（批量下载需 SWH/INRIA 协议、
   逐文件许可与署名）；**ULT 的 HF 副本无 license、无 dataset card**。结论：**禁打包进仓**，
   改为本地拉取 + 显式接受 + 保留逐文件许可元数据。成本外推：实测 **12,604.8 tok/task** →
   3,909 任务 ≈49.3M tok ≈**$45.7/轨**（不含 K 轮重放与 cosmic-ray）。

### B.3 未执行（需用户授权）

| 项 | 原因 | 需要什么 |
|---|---|---|
| H1 载荷等价实验（3 臂 × 41 任务） | 前置门 4 项全红 + 需预算 | 先落地 `GENERATOR_PAYLOAD` 开关与消费者；再授权 ≈1.4M token |
| 打开逻辑通道 A/B（`SPEC_ORACLE_EXEC_ENABLE` off/on） | 需预算 | 指标已就绪，可直接跑 |
| ULT 全量重跑（3,909 任务） | 许可 + 预算（≈$45.7/轨） | 先解决 SWH/INRIA 协议；先做 200 任务定标 |
| 落盘优先修复的代码改动 | patch-analyst 的诊断报告仍在产出 | 待 `review_2026/E2_patch_not_landed.md` 完成后按其分类落地 |
| `_env_snapshot_keys` 剩余 46 键 | 属 P1/P2/P3 档，应随下个正式批次补 | 按 `E2_env_snapshot_report.md` §3 表整段粘贴 |

### B.4 本批次未触碰的边界

- **未调用任何 LLM**；未修改任何入库实验工件字节（`git status --short experiments/results` 为空）。
- 未跑全量 pytest（约 5,000 用例，避免与并行成员冲突）；仅跑受影响文件。
- 未修改 `data/quixbugs`、未安装新依赖（cosmic-ray 未装）。
- **实现代码的最终质量门（全量 pytest + ruff + mypy）应由维护流程在合入前跑一次**——
  本批次只对受影响文件做了针对性验证（112 passed / 1 xfailed、ruff 全绿、mypy 3 文件 0 错误）。
