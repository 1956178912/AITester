# X 轮零 LLM 复算核对与论文复现性闭环（2026-10-19）

> **性质**：论文定稿核对 + 工件包复现性审计。全部工作**零 LLM 调用**（$0）。
> **触发**：用户指示的本轮迭代三方向之一（论文定稿推进）的前置核对。
> **结论**：论文全部关键数字在当前 HEAD 代码下复算吻合；核对过程中发现并修复
> **四个复现性缺口**（两个复算入口缺失、一个语料在作者机、一个附录引用不存在的
> 入口），另记录一个 README 重写隐患（未修，列入 X 轮评审）。

## 1. 零 LLM 复算核对（Phase 1）

对论文引用的核心数字，用当前 HEAD（`55bb711` + 本轮暂存改动）逐一复算：

| # | 复算项 | 命令入口 | 公布值 | 复算结果 |
|---|---|---|---|---|
| 1 | 主批三种子统计（概览） | `statistical_analysis.py --pool-seeds` | aitester 261/143/54.8%/240/15.8% | **逐位一致** |
| 2 | 主批 detection McNemar | 同上 | 240 对、40 不一致、χ²=27.2250；92、χ²=48.7935 | **一致** |
| 3 | 主批贝叶斯后验 | 同上 | δ=+0.139 [+0.092,+0.190]；−0.279 [−0.348,−0.209] | **一致**（0.1393/−0.2787） |
| 4 | 主批配对 t 检验 | 同上 | t=−8.7759/d=−0.5432；t=15.4555/d=0.9567 | **一致** |
| 5 | 簇稳健（S13/A06） | `--cluster-robust --cluster-task-count 87 --cluster-seed 42 --cluster-max-pattern-repeat 2` | 31 簇、符号检验 p=0.0018/0.0169（5:17:9） | **一致**（5:17 双侧精确 p=0.01690054） |
| 6 | df_spec 主对比（P1 主实验） | `emse_df_spec_analysis` | δ=−25.71pp、p=0.0117、BF10=16.40、1:10 | **JSON 逐位一致** |
| 7 | T 轮 B2 锁指纹复现批 | `analyze_t1_b2_main_batch.py --write` | not_reproduced、δ=−25.29pp、b/c=4/70 | **ANALYSIS_REPORT 逐位一致**（除 out_dir 路径） |
| 8 | df_doc 锚替换（RQ4） | `emse_docstring_anchor_analysis` | 60.0% vs 86.1%、δ=−25.71pp、p=0.0352、3:12 | **JSON 逐位一致** |
| 9 | df_doc 增广（RQ4） | `emse_docstring_augment_analysis` | 82.9% vs 80.6%、δ=+2.86pp、p=1.0 | **一致**（除输入路径，源于原批在不同工作树跑出） |
| 10 | ULT accuracy（RQ4 竞争缺口） | `emse_ult_dfsmoke_accuracy`（200 任务×子进程重放，10m18s） | 0.21（42/200）、fail=158 | **头条与 200 条语义字段全同**（仅 wall_s 与 pytest 计时后缀不同） |
| 11 | T 轮 B1 协议文本（RQ2） | 归档 ANALYSIS_REPORT | replicated_strong、+16.09/+19.54pp | 归档值与论文引用一致 |
| 12 | 门禁计数口径 | `ls scripts/gates/*.py` + ci.yml | 26 脚本 / 24 唯一引用 / 27 调用点 | **三项全中** |

**输入指纹核对**：5 个关键批次 JSON 的 sha256 与各报告 `inputs` 记录逐项匹配。

**结论**：论文数字体系在当前代码下**未发现复算偏差**；W 轮 A07 配对修复对历史批次
数字零影响（与修复说明一致：历史批无跨批重复 task_id）。

## 2. 发现的复现性缺口与修复（Phase 2）

论文 Reproducibility 一节声称"每个数字都可从工件包零 LLM 复算"
（*recomputable claims*）。逐项审计附录 A 引用的复算入口后，发现四个缺口：

| # | 缺口 | 影响数字 | 修复 |
|---|---|---|---|
| G1 | `emse_dsl_extend_recheck.py`（+ 依赖的 `emse_dsl_diag3.py`）被 gitignore，且语料派生自作者机 `~/.cache/aitester/llm` | 子句可编译率 0.8847→0.9127 | 脚本入库；语料按归档报告 mtime 切点（2026-10-15 12:45:38，719 planner 条目→607 去重子句，精确重建）固化为 `CORPUS_607.json`；脚本新增 `--dump-corpus`/`--from-corpus`/`--out`。**重放逐位复现归档 RECHECK_REPORT.json** |
| G2 | `emse_ult_dfsmoke_accuracy.py` 被 gitignore（语料=库内 benchmark JSON，脚本自闭环） | ULT accuracy 42/200=21.0% | 脚本入库（§1 第 10 项即为其入库后复算） |
| G3 | `emse_quixbugs_mutk_full.py` / `emse_ult_mutk_full.py` / `emse_test_sanity_audit.py` 被 gitignore（批次八纪律"无测试引用"） | **Table 5 mutation 分数**（0.9543/0.7444/0.6749、0.928/0.64/0.4395） | 三脚本入库（论文表格直接依赖，纪律前提失效） |
| G4 | 附录 A 缺 5 处量化引用映射（可编译率、ULT 估计、oracle 质量/SMT 见证、设计敏感性、过红审计） | 论文诚信（附录自称 SRC 注释的排版形式） | 附录 A 补 5 行 + 表题更新；全部入口经 `git ls-files` 实证在库 |

**入库清单**（6 脚本 + 1 语料 + 1 测试 + 相关 README/清单）：
- `experiments/emse_dsl_diag3.py`、`experiments/emse_dsl_extend_recheck.py`（新增语料重放路径）
- `experiments/emse_ult_dfsmoke_accuracy.py`
- `experiments/emse_quixbugs_mutk_full.py`、`experiments/emse_ult_mutk_full.py`、`experiments/emse_test_sanity_audit.py`
- `experiments/results/emse_dsl_extend_recheck_20261015/CORPUS_607.json`（+ README 复现节重写 + SHA256SUMS 重生）
- `tests/test_emse_recompute_entrypoints.py`（9 例：语料重放逐位复现 + 确定性 + 结构锁 + 旧门常量恢复 + ULT/Mut@k/健全性三入口分类契约）
- `.gitignore`：移除 6 条 ignore 条目并更新两处纪律注释（X 轮说明）
- Mut@k 两目录 README 去掉"gitignored"表述 + SHA256SUMS 重生

**口径说明**：`smt_witness_batch.py` 经验证**已在库**（`962c77e`，此前 bash grep 编码
问题误报）；论文 Data Availability 仅剩 Zenodo DOI 待归档后回填（T-4，需用户操作）。

## 3. X 轮（二）系统评审：同类缺口普查与修复（2026-10-19 续）

在第一阶段修复后，对"引用-入库"一致性做了全形态普查（不限于 .py）：

| 检查 | 范围 | 结果 |
|---|---|---|
| 文档引用的 experiments 脚本 | 70 个被引脚本（docs/ + README + REPLICATION + CONTRIBUTING） | 3 个不在库，均为**非 live 引用**（api_reference 版本史的历史快照 1 + ult_bridge_plan 明确标注"设计，不实现" 2）——live 引用全部闭合 |
| 工件 README 的复现命令引用 | 全部 `experiments/results/**/README.md` | **0 个**不在库 |
| 被跟踪文件引用的全部路径 | 106 条（data/docs/experiments 全形态） | 绝大多数为既有约定（测试夹具 / 历史快照 / 本地工件 / 本地预注册件）；发现 **2 个真实输入缺口**（G5，见下） |
| README 重写隐患（手工节丢失） | 10 个写 README 的脚本 × 各自归档工件 | T 轮实例已修；其余 9 个无手工节，无同类风险 |
| 新入库 6 脚本危险模式 | 硬编码绝对路径 / eval·exec / shell=True / sk- 样式 / os.system / 字符串命令 | **全部 CLEAN** |

**输入缺口修复（G5）**：两个零 LLM 脚本的**默认输入批次**不在工件包内（脚本在库、
输入不在——复算链仍断）：
- `emse_quixbugs_mutk_full.py`（论文 Table 5 QuixBugs mutation）的 `_INPUT_JSON`
  → 入库 `emse_spec_ir_quixbugs_20261013/`（52 文件，985,875 字节，含 traces）；
- `emse_ult_gold_diagnosis.py`（Table 5 题注"gold fails on fixed 71/71"）的
  `_LITE46_JSON` → 入库 `spec_ab_scale87_20261012/ult_lite46_replace/`（94 文件，
  2,178,508 字节，含 raw + traces）。
均按 r4_batches 先例整目录入库（批次 JSON + 逐任务轨迹 + provenance README +
SHA256SUMS；`.gitattributes` 已设 `-text` 保证字节一致）。

**T 轮 README 重写隐患修复（第一阶段记录项的闭环）**：
`analyze_t1_b2_main_batch.py` 增设 `<!-- MANUAL:BEGIN/END -->` 标记块的
生成-保留机制（`_preserve_manual_sections`：成对闭合块在 `--write` 时原样
保留到生成内容末尾；未闭合标记不保留；多块按原序保留）；归档 README 的
"0.6 T 轮发现"节已包标记。**端到端实证**：/tmp 副本重跑 `--write` 后手工节
完整存活（此前必丢 32 行）。回归锁
`tests/test_analyze_t1_b2_manual_sections.py`（5 例，hermetic——用归档报告
直接渲染，不重跑批次分析）。

## 4. 验证

**第一阶段**：
- 新测试 `tests/test_emse_recompute_entrypoints.py` → **9 passed**（broker 禁用环境；沙箱内 tmp_path 被 broker 阻断属已知环境限制）
- 清单门禁：三个受影响工件目录 `checksum_results.py --verify` 通过（3/2/3 项一致）
- 论文编译：typst 19 页；附录 A/B 逐页 SVG→Chrome 截图目检通过

**第二阶段**：
- 新测试 `tests/test_analyze_t1_b2_manual_sections.py` → **5 passed**（0.08s，hermetic）
- 端到端实证：/tmp 副本重跑 `analyze_t1_b2_main_batch.py --write`，手工节存活（修复前丢失）
- 输入批次清单：`emse_spec_ir_quixbugs_20261013` 52 项、`ult_lite46_replace` 94 项、`t_round_b2` 804 项全部 verify 通过
- 新入库 6 脚本危险模式扫描全部 CLEAN
- 全量测试（两阶段合计 +14 例）：正常环境口径 **9153 passed / 5 skipped / 0 failed**（collected 9158）；本机沙箱 9138 passed / 19 skipped / 1 failed（唯一失败 = 基线守卫，刷新 BASELINE 后转绿）
- 门禁：ruff（828 文件）+ mypy（134 源文件 0 错）+ 双语文档 strict + 链接 strict + 基线/基线数字 + 状态契约 + env 预算/快照 + 模型指纹 + JSON 契约 + 零断言（390 文件）+ 引用 + 审计脱敏 + 凭证剔除 + 锁同步 + 工件对账 + prompt 哈希锁（7 artifact）+ 分支覆盖 + 棘轮（92.70% ≥ 92.50%）+ 工件入库（179/179）+ main_batch 清单 2029 项——全部通过
