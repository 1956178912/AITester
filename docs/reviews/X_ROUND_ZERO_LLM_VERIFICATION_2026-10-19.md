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

## 3. 记录未修：T 轮 README 重写隐患（移交 X 轮评审）

`analyze_t1_b2_main_batch.py --write` 会**从零重生成** README.md；归档版第 105–136 行
的"0.6 T 轮发现（可辩护表述，写死防事后改写）"是**手工追加**节，脚本不重生成——
任何重跑 `--write` 都会静默丢失该节（本轮复算即在目录副本上实证：diff 显示 32 行缺失）。
归档工件本身未受影响（本轮复算只在 /tmp 副本上进行）。建议修法：生成-保留标记
（`<!-- MANUAL:BEGIN/END -->`）或把该节移入手写文件。列入 X 轮评审候选。

## 4. 验证

- 新测试：`pytest tests/test_emse_recompute_entrypoints.py -q` → **9 passed**（broker 禁用环境；沙箱内 tmp_path 被 broker 阻断属已知环境限制）
- ruff check + format：全部变更文件通过
- 清单门禁：三个受影响工件目录 `checksum_results.py --verify` 通过（3/2/3 项一致）
- 论文编译：typst 19 页；附录 A/B 逐页 SVG→Chrome 截图目检通过
- 全量测试：见提交记录（本变更新增 9 例）
