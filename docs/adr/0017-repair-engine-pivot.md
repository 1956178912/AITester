# ADR-0017: 修复引擎范式转向——从"检出优先评估方法学"转向"局部化 → 合成 → 验证"修复引擎路线

- 日期：2026-10-07（批次 I，用户 scope 级拍板）
- 状态：已采纳（Accepted）
- 关联：ADR-0016（编排定位重述）、ADR-0015（检出优先协议）、ADR-0003（默认关口径）、`src/agents/fault_localizer.py`、`src/agents/fl_spectral.py`、`experiments/results/main_batch/statistical_report_e2_iter.md`

## 背景（Context）

预注册序列的最终实证结果指向同一结论——**修复是当前管线的第一短板，而局部化是其上游瓶颈**：

1. **repair 全线 0**：R-P0-2 生死实验三臂 repair=0.0%；AK1 上限归因（修复循环 154/261 → patch 产出 94.2% → plausible 46.8% → correct 0）证明瓶颈在补丁质量而非产出。
2. **E2 正式定案（"恰好一次"迭代用尽）**：H2a 过红 88→31（降幅 64.8%）、H2b 抹红 28→2（降幅 92.9%）——门协议大幅削减两类失效通道但未归零；H2c aitester vs plain_llm_df δ=−0.3673 [−0.4552, −0.2785]（bayes_neg）——"编排容器在检出口径下结构性劣后"最终确立（承接 ADR-0016）。
3. **局部化首度可测即见短板**：FL@1 首测 19/53=35.8%（E2 迭代批，gold diff 对齐修复后口径）——近 2/3 的真实缺陷行不在谱系 Top-1。
4. **前沿 APR 共识范式**为"局部化 → 合成 → 验证"且局部化是公认瓶颈（引用核验 2026-10-07 第二轮/第十六轮：RGFL〔**Reasoning**-Guided，arXiv 2601.18044——全称勘误：非 Retrieval-Guided〕file-level Hit@1 71.4%→85%，接 Agentless 端到端 +12.8%；多 Hunk 行为研究 arXiv 2511.11012：修复准确率 Claude Code 92.82% vs Qwen Code 26.98%、随 hunk 数与分散度递减；定位主导性 500 实例 61 配置研究〔GPT-5-mini，file-level 为主因素〕。**勘误**：此前引用的"Hunk-SWE"与"PSR（四模式 LoRA）"两名经第十六轮三轮检索未能定位原文，暂以上述已核验锚点替代；Kronumos 2 Kairos 系单作者未评审预印本，慎引——其 93.5% token 削减数字摘要层未确认）。

用户在 AI 给出"先完成论文轨道"建议后**否决该建议并拍板立即转向**（三阶段：局部化重建 → 模式专业化 + 确定性验证 → 成本效率）。ISSTA 2027 论文窗口放弃，可发表贡献转为 v2 基础设施；预注册序列 E4/E6 冻结（验证后可按新目标重定义）；E7 与论文成稿暂停。

## 决策（Decision）

1. **项目主线转向修复引擎**："局部化 → 合成 → 验证"三段范式；repair 从"诚实测量的结论"转为"要优化的目标"。M1 诚实指标的**裁判员角色不变**（检出优先协议、门协议、FL@k、patch_precision 口径全部继承——它们正是修复引擎需要的测量层）。
2. **局部化升格为可独立量化的第一阶段**（批次 I 落地，`src/agents/fault_localizer.py`）：
   - **双通道融合**：谱系通道（Ochiai Top-k，零 LLM，复用 `fl_spectral` 测量层）提供行级可疑度佐证；推理通道（RGFL 式 LLM 结构化定位 `{function_name, line_start, line_end, confidence, reasoning}`）**只定位不修复**；
   - **接线**：`_debugger_node` 内联调用，定位结果写 `state["llm_localization"]`，经 `build_localization_prompt_section()` 与谱系段落并列注入 Debugger prompt；
   - **独立指标**：`localization_hit_function`（LLM 定位函数 ∈ gold 变更函数集合，`gold_changed_functions()` 以 buggy↔gold-fixed diff 行 → AST 所属函数提取 gold 口径）与既有 `fl_at_k`（行级）并列输出；
   - **降级口径**：开关关 / LLM 失败 / JSON 解析失败 / 必填字段缺失 → None（不产出假定位；实验层按"不可测"处理，键集合同构保持历史批次兼容）；
   - **开关**：`FAULT_LOCALIZER_ENABLE` 默认 **true**（修复引擎主路径；显式 false = 纯谱系消融对照）——本决策是 ADR-0003"默认关"原则的**显式例外**：范式转向后局部化即主路径本身，且消融对照组（纯谱系）经同一开关保留。
3. **已有资产按新范式重排而非重写**：17 类错误分类器、strategy_bank、AST 守卫、跨文件分析、双门协议等保留，按"局部化 → 合成 → 验证"位置重新接线。
4. **防污染纪律保留**：SWE-bench Lite 仅内部验证用，对外修复主张须 Live/SWE-rebench 口径（承接既有基准意识）。

## 后果（Consequences）

**正面**：

- 局部化质量首次可独立归因（函数级命中 vs 行级 FL@k、谱系 vs 推理通道四档消融），优化预算可投向实测瓶颈；
- Debugger prompt 首次获得"谱系佐证 + 推理定位"双先验，合成冒烟三态全过（有失败用例/无失败用例/开关关），全量 4453/0 零回归；
- E2 定案解锁的测量资产（双门、FL@k gold diff 口径、matched cap 提取）直接服务修复引擎迭代。

**负面/风险**：

- 推理定位每修复轮新增 1 次 LLM 调用（定位段 prompt 含带行号源码 + 测试 + 输出截断 2000 字符 + 谱系 Top-5）；
- LLM 定位错误可能误导 Debugger（与谱系佐证冲突时 prompt 约定"以推理为准"，错误率待消融测量）；
- `FAULT_LOCALIZER_ENABLE` 默认开打破"新能力默认关"惯例（ADR-0003），历史批次结果与默认口径的可比性依赖消融开关维持。

## 验证

- 批次 I 冒烟：真实三态（定位产出 / 无失败用例跳过 / 开关关回退）全过；`localization_hit_function` 与 `llm_localization` 结果行键集合同构（成功/失败分支）；
- 全量 4453 passed / 0 failed（+16 定位测试）；
- 后续：四模式 Debugger 拆分 + 确定性后处理 + 多 Hunk 任务（第二阶段）；定位四档消融（双通道/仅谱系/仅推理/无定位）出数后回填本 ADR 修订记录。

## 已知局限与演进方向

- `localization_hit_file`（跨文件任务）口径已定义但单文件场景恒命中，暂不透出；行级沿用 FL@k；
- gold 口径 `gold_changed_functions()` 按最内层函数归属，跨文件场景需调用方按模块分别调用（当前单文件管线未触达）；
- E2 迭代批实证的 df 臂失控回环（regenerate 计数上限缺失）与 fl 触发链缺口，须在 E4/E6 重定义前修复。

## 修订记录

1. 2026-10-07 首次落地（修复引擎批次 I，提交 0355f51）：`src/agents/fault_localizer.py` + `_debugger_node` 双通道接线 + `state["llm_localization"]` + 结果行 `llm_localization`/`localization_hit_function` + `FAULT_LOCALIZER_ENABLE`（默认 true）+ 16 项测试。
2. 2026-10-07 修复引擎批次 II（第十六轮审查驱动）：①定位升级 **Top-3 候选排序**（RGFL 两阶段式）——prompt 要求 1~3 个候选按可能性降序，每候选新增 `expected_logic`（推理引导：先写"该处应有的正确行为"再对比实际代码）；解析器向后兼容旧单对象 schema，顶层字段 = 首位候选；②新增**元素级排序指标** `localization_hit_function_at_3` / `localization_mrr`（`localization_rank_metrics` 纯函数，与 Hit@1 并列透出；旧 schema 退化单候选）；③新增 **CPR/IDR 离线口径**（`experiments/cpr_idr_report.py`，零 LLM）——首测 **IDR = 27.78%（40/144）**：72% 的 plausible-but-wrong 补丁零负信号通过，验证通道缺口定量化，为第二阶段"验证越过 plausible + 弃权机制"提供实测依据；CPR 因 correct=0 诚实未定义；④引用面勘误（见背景 4）；⑤全量 4478/0（+25）。
3. 2026-10-07 **动机勘误（ADR-0021，批次 VII）**：背景 1"repair 全线 0"系测量层伪影——patch 字段围栏残留（`python\n` 前缀）使 M1 独立裁决在未清理文本上 100% 失败；修正口径存量重放 repair_rate = **38.7%**（266 可重放行 correct=103；E2 双种子 44–48%）。**范式转向不撤销**（FL 短板 / H2c 劣后 / 前沿共识动机独立成立），但第二阶段优先级重排：repair 目标从"破零"修正为"38.7% → 提升"，反事实 FL 上界与弃权阻断档价值上升、四子智能体重构紧迫性下降（重构前先按修正口径重估漏斗）。
