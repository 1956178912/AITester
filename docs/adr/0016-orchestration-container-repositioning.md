# ADR-0016: 编排定位重述——从"多智能体增益主张"转向"可消融编排容器 + 检出优先轻量管线"

- 日期：2026-10-06（第十轮审查 T-P0-3）
- 状态：已采纳（Accepted）
- 关联：`experiments/results/main_batch/statistical_report_3seed_pooled.md`、ADR-0015（检出优先协议）、ADR-0003（默认关口径）、`src/tools/detection_gates.py`

## 背景（Context）

R-P0-2 生死实验（预注册，n=87 × 3 臂 {aitester, plain_llm, plain_llm_df} ×
3 种子 {42,43,44}，强模型 deepseek-flash，temp=0.0，`AITESTER_PROFILE=logic`，
干净树 b533cff，3.8h / 8.76M tokens）给出决定性证据：

| 对比 | detection 配对差（gold 独立裁决，BH-FDR 后显著） | token/任务 |
|------|------|------|
| plain_llm_df vs plain_llm | **+43pp**（δ=+0.426 [0.367, 0.487]） | 4.2k vs 3.2k |
| aitester vs plain_llm | +14pp（δ=+0.139 [0.092, 0.190]，三种子逐一显著） | 26.1k vs 3.2k（8.1×） |
| **aitester vs plain_llm_df** | **−28pp**（δ=−0.279 [−0.348, −0.209]） | 26.1k vs 4.2k（6.2×） |

机制归因（合并报告"已知口径缺口"节）：−28pp 的两条主通道为 88 行**过红测试**
（buggy 红 fixed 也红，非缺陷特异，空耗修复循环）与 28 行**修复循环抹红**
（再生成测试使最终测试在 buggy 原码上变绿，检出证据被销毁）。repair 全线
0.000。聚类稳健敏感性分析（AC4：模板级 DEFF 校正 + 符号检验）确认三组
结论方向与显著性全部保持。

另有同批实证：logic 档下 spec_compile_rate 恒 0.0（AB1 验证批 12/12）——
根因是 prompt–DSL 编译器契约断裂（AC1 修复：`SPEC_EXPR_CONTRACT_SECTION`
表达式通道），规约链在修复前对检出零贡献。

## 决策（Decision）

1. **编排降级为"可消融容器"**：多智能体编排（专家池/辩论/多候选/RAG 等，
   默认关的组件群）不再作为增益主张，定位为**消融研究对象与能力容器**。
   任何编排组件转正前必须在与 plain_llm_df 等预算对照下复现正向
   detection 增量（历史 A/B 全阴性 + 本实验 −28pp 净负，证据标准从严）。
   后续优化方向为**轻量管线**（检出优先协议 + 定向反馈门），不做编排加码。
2. **主张 A 收缩为"检出优先提示协议 +43pp"**（提示工程贡献），论文按
   三点式框架 B/C 轴（归因方法学 + 阴性/归因结果）+ A 收缩版落笔。
3. **双门协议扩展**（ADR-0015 修订记录第 6 条，本 ADR 的工程侧落地）：
   特异性门（过红 → regenerate 而非修复循环）与红回归门（抹红 → 恢复
   红证人交回修复循环），均为默认关开关、logic 档注入，属检出优先协议
   的协议层增强而非编排组件。
4. **测试文件锁定原则**：修复循环内**不得**以"换测试"方式达成绿灯——
   红证人快照（`red_witness_test_code`）与红回归门是该原则的机制保证；
   已落地补丁场景交 M1 gold 独立裁决（门内不重复执行）。
5. **graph→experiments 延迟导入冻结存量**：`detection_gates` 的门执行
   委托 `experiments/_m1_metrics._run_pytest_in_tmp`（与 M1 裁决同一原语，
   沿 mutation_advisor / nodes 既有先例）。该反向依赖为已知架构债，
   收敛方案（src 层统一执行原语）待后续批次，**新增**反向导入须先在本
   ADR 追加修订记录。

## 后果（Consequences）

**正面**：

- 项目叙事与证据对齐：不再为无证据的"多智能体增益"背书，−28pp 本身
  成为可发表的核心发现（与 mini-SWE-agent / Agentless 的简洁管线证据
  相互印证）；
- 后续批次的优化预算集中于协议层（双门、契约、特异性裁决），ROI 有
  实验依据（+43pp 协议效应 vs −28pp 编排效应）；
- 双门把 F2P 三段判定从"事后评估"前移到"环路内路由"，−28pp 的两条
  机制通道可被直接消除（待复跑验证）。

**负面/风险**：

- "多智能体系统"标签弱化，相关章节/ README 叙述需同步（编排定位为
  容器，标题与主张措辞调整）；
- 双门引入环路内对照执行（门①），单任务 +1 次 pytest 子进程（~秒级，
  仅首轮红触发）；
- 若双门复跑后 aitester 仍劣于 plain_llm_df，则结论升级为"编排容器在
  检出口径下结构性劣后"，主张 A 彻底收缩为协议本身——两种结果均可发表。

## 验证

- 双门修复后复跑（预注册同口径）：过红/抹红通道行数 → 0；
  aitester vs plain_llm_df 差距收敛至不显著或反超（E2，见第十轮审查报告）；
- 契约修复后冒烟（E1）：spec_compile_rate ≥ 0.3（预注册阈值：< 0.2 放弃
  逻辑驱动主张）。

## 修订记录

1. 2026-10-06 首次落地（AC 批次）：本 ADR + ADR-0015 修订记录第 6 条 +
   `src/tools/detection_gates.py` + 双门路由/观测接线 + 21 项锁定测试
   （`tests/test_ac_batch.py`）。
2. 2026-10-06 AF 批次（决策 5 收敛尝试与阻塞登记，第十一轮审查 N12）：
   "src 层统一执行原语"收敛方案本轮尝试落地（新建 `src/tools/execution.py`
   承载 `_run_pytest_in_tmp`），三次写稿均被 Mimosa PreToolUse 静态扫描
   以"命令注入"高危拦截——扫描器对新建 src 文件做数据流污点分析
   （`os.getenv` / `sys.executable` 流入命令列表即判污，函数间接、
   `is_file` 校验、`shell=False` 均不解除），而"经校验的动态解释器 +
   参数列表子进程"正是执行原语的业务本质（`sys.executable` 固定口径是
   M2 修复的成果；硬编码字面量解释器会重新引入 M2 之前的静默失效 bug）。
   按"不绕过安全工具"原则终止尝试：原语维持 experiments/_m1_metrics
   现状（存量豁免），detection_gates 委托模式不变，graph→experiments
   反向导入维持 6 处冻结存量计数。解除路径：①Mimosa 门禁侧对
   sys.executable 校验模式加白名单后重试；②用户调整
   MIMOSA_GIT_GATE_MODE 后人工复核放行。
3. 2026-10-06 AK 批次（修复上限归因证据 + 双界稳健性 + provenance 勘误）：
   repair=0 漏斗实测（`experiments/repair_ceiling_analysis.py` →
   `experiments/results/main_batch/repair_ceiling_report.md`）：修复循环
   154/261 行中 patch 产出 94.2%、plausible 46.8%、correct 0，
   patch_evidence_level=none 占 48.1%、stop_reason=
   skip_debugger_repair_invalid 占 50.0%——"编排反噬"机制证据补充：修复
   循环大量产出补丁但被验证/证据门拒绝，且 gold 裁决无一正确（E7 分层
   抽样框）。21 行 detection=None 双界下 −28pp 结论稳健（最好情形仍
   −22.2pp，p=1.7e-08）；pooled 报告 provenance 勘误（git_dirty=true）
   与报告引用工件入库 CI 强制（check_artifacts_tracked.py）同批落地。
   src/ 零改动，默认行为不变。
