# ADR-0034: 编排自动搜索（16 臂 bandit）冻结登记——工程骨架就绪、未经实跑验证

- **日期**：2026-10-16（冻结登记；模块落地于 2026-10-12 P1-A 批次）
- **状态**：已采纳（冻结；实跑解锁条件在案）
- **关联模块**：`src/graph/orchestration_search.py`、`experiments/run_orchestration_search.py`、
  `config.py`（`ORCHESTRATION_SEARCH_*` 开关组）、`tests/test_orchestration_search_matrix.py`、
  `experiments/run_benchmark.py`（`_env_snapshot_keys` 已登记 `ORCHESTRATION_SEARCH_ENABLE`，
  2026-10-12 第五次快照缺口预防）
- **关联 ADR**：ADR-0016（多智能体编排降级为"可消融容器"）、ADR-0003（实验开关默认关）

## 背景

独立评审（`INDEPENDENT_REVIEW_2026-10-16.md`）在"无法验证声明"清单登记：
**`orchestration_search.py` 16 臂 bandit 的实跑状态（源码在场，无结果工件）**——
即"源码在场 ⇒ 能力暗示"的审计歧义（评审建议 A-11：实跑或 ADR 记录冻结理由，
防"死代码宣称能力"）。

现状核验（2026-10-16）：

1. **实现完整**：P1-A 骨架含 16 臂精选空间（全因子上界 3072 臂 × 约 1% 精选）、
   UCB1 选择、hindsight credit（**只进归因报告、绝不进臂选择**，reward hacking
   防线已有测试以源码检查锁定）、eval/token 双预算硬顶、确定性 cell 分配
   （每 (arm, cell) 至多评估一次）、默认关零行为（`SearchDisabledError`）；
2. **测试矩阵在场**：`tests/test_orchestration_search_matrix.py` 等锁定默认关
   零行为与纯 stdlib 纪律；
3. **从未执行任何搜索批次**：无批次工件、无奖励曲线、无 champion 记录——
   一切"自动搜索可增益"的表述均**无本项目实证**。

外部方向依据（保留理由）：BOAD（ICLR 2026）证明**自动发现**的层级多智能体
可优于手工设计（SWE-bench Verified 53.2% vs 47.4%）——与本项目"手工编排
净负（ADR-0016）"互补，方向值得保留但尚未验证。

## 决策

1. **冻结口径**：模块状态 = **"已测试的工程骨架 + 待跑实验"**。冻结期间：
   - 不新增功能（防死代码宣称持续积累）；
   - 任何文档 / 论文 / README / BASELINE **不得出现**"bandit 自动搜索提升 X"
     类表述；允许的最强表述是"已实现并测试、待预注册实跑的搜索机制"；
   - 模块与测试**保留**（不删除；BOAD 方向依据见上）。
2. **实跑解锁条件**（全部满足方可排批）：
   a. **预注册先落盘**：臂函数评估预算 / token 硬顶 / 主终点（M1 detection，
      gold 独立裁决）/ 停止规则 / 多重比较校正方案——结果产出前归档
     （与 M4 扩样同一 Registered-Report 机制）；
   b. **等预算纪律**（E6 教训）：champion 必须与 `plain_llm_df`（当期最强
     轻量臂）在**匹配预算**下对照；预算混杂的"提升"不成立；
   c. 前置闸全绿：`run_preflight`（配额 / 指纹 / 干净树）+ `batch_quota`
     硬上限（`AITESTER_BATCH_MAX_CALLS`）；
   d. 奖励口径跑批前后一致 = M1 `detection_rate`（不得事后更换终点）；
   e. 16 臂多重比较须带校正（BH-FDR 或预注册的层级检验）。
3. **优先级记录**：当前 LLM 预算排序（`docs/PROJECT_STATUS_REGISTER.md` §2）中，
   B1 2×2 消融 / T-1 ULT accuracy / P1（df_spec 规格锚臂）实跑均优先于本项；
   本项维持冻结。
4. **决断期限**：若至下一投稿周期仍未实跑，二选一（按 ADR-0016 §5 精神）：
   删除模块，或降格为 `experimental/` 标注 + 论文明确"未执行"。

## 后果

- **正面**：关闭 A-11 审计歧义；冻结不阻断未来 BOAD 式方向；不删除已有
  工程投资（实现 + 测试矩阵的沉没成本保留为期权）。
- **负面**：16 臂空间随框架演进可能过时（可接受——纯 stdlib、接口小而稳，
  解锁跑批时可先做最小可行配置）。
- **演进方向**：解锁时优先最小可行配置（4–6 臂子集 × 单 cell × 3 seeds）
  压低首跑成本；hindsight credit 维持"只进归因不进选择"纪律。

## 已知局限

- 本 ADR 不改变 `docs/algorithm_design.md` 的算法映射表（编排自动搜索未入
  该表——冻结期间亦不新增映射行）。
- 16 臂空间与 UCB1 的参数（c 值等）未经真实奖励分布标定，解锁前不得作为
  "超参数已调优"引用。

## 勘误（2026-10-27，FB / FC 轮）：冻结期间的两处**判据缺陷**修复（不是新增功能）

§1 的冻结口径是「不新增功能（防死代码宣称持续积累）」。本勘误登记两处**只让判据更严、不增加任何能力声明**的
缺陷修复，并说明为何不违反冻结：

1. **`assert_no_credit_coupling` 的守卫会被 `python -O` 整条删除**（FB 轮）。
   该守卫原以 `assert banned not in source` 实现；CPython 在 `optimize=1/2` 下会删除整条断言
   （连同消息常量），于是「禁止 hindsight credit 进入 UCB 臂选择」这条**防 reward hacking 的判据**
   在优化模式下**静默消失**。改为显式 `if` + `raise AssertionError`（公开函数名与异常类型不变）。
   这是**恢复已声明的约束**，不是新增能力。
2. **champion 守卫把「假修复率无观测」读作 0**（FC 轮）。
   `select_champion` 的第 3 条约束原为 `mean_false_fix <= 0.5`，而 `mean_false_fix` 在零样本时取
   `_mean([]) = 0.0`——「一条假修复率观测都没有」的臂**空洞通过**该守卫并被选为 champion
   （「没测」被读成「测得 0」）。现要求 `n_false_fix >= 1` 才判读，报告新增 `n_false_fix` 披露观测数。
   同属**收紧已声明的约束**（原意是「防刷 passed 配置」，而改前它在该处从未真正判读）。

**纪律不变**：本组件仍为「已测试的工程骨架 + 待跑实验」，仍**无任何实跑工件**；
§1 的冻结口径（不新增功能、不出现"bandit 自动搜索提升 X"类表述、文档不得暗示能力）与 §2 的实跑解锁条件
**一字未改**；§4 的「决断期限」照旧。两处修复均不产生任何新的能力声明，
反而把两处「看起来在守、其实没守」的判据变成真守。

**新增的永久约束**：FC 轮为 `src/` 的运行期判据立了**类锁**
（`tests/test_optimized_mode_guard_fc.py`）：普查 `src/**` 的全部 `assert`（按内容锚点登记）、
以 `compile(..., optimize=2)` 的字节码探针证明守卫不会被优化器删除。
⇒ 今后该组件内**任何**以 `assert` 承载的运行期判据都会在 CI 转红。
