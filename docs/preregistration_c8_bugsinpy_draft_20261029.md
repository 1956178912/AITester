# C8 外部效度预注册草案：BugsInPy 真实项目小样（2026-10-29，草稿待冻结）

> ADR-0036 判据 C8（EVALUATION_SCOPE 第 3 行）："真实项目小样或 Java 最小臂"，
> 声明限定"Python 合成基准"。本草案选 **BugsInPy 真实 Python 缺陷基准子集**
> 作为 C8 外部效度小样。**状态：FROZEN（2026-10-29 21:30 用户确认冻结执行）**。

## 动机

全部现有读数（E8/B2/E6/ULT 定标）产生于**合成任务集**（模板生成）与 **ULT
（官方基准但函数级 + gold 齐备）**。C8 要求证明结论可迁移到**真实仓库的
真实缺陷**。BugsInPy（Wong et al., ICST 2020）是 Python 生态最接近 SWE-bench
形态的真实缺陷基准（17 项目 / ~500 bug / 带 gold patch 与测试）。

## 选型（冻结前可调）

- **项目子集**：`pallets/flask` + `psf/requests`（2 个项目——轻依赖、判定
  协议已在 SWE-bench 阶段 2 验证 flask 端到端可走通；BugsInPy 的 flask/requests
  版本线与 SWE-bench 实例高度重叠，DEP_LOCKS 表可直接复用/小幅扩展）。
- **任务量**：每项目抽 10 个 bug（`ceil(10%)` 分层口径同 E7）——共 20 任务。
- **臂**：aitester + plain_llm_df（2 臂）× 20 任务 × 1 seed 42。
- **判定口径**：FAIL_TO_PASS 红绿翻转（复用 `scripts/tools/swebench_task_judge.py`
  协议，BugsInPy 的 gold test 替代 test_patch）。

## 与 SWE-bench 阶段 2 的工程复用

| 复用件 | 说明 |
|---|---|
| repo clone/checkout | BugsInPy 自带 repo 快照（GitHub fork），clone 流程同 |
| venv + 依赖锁定 | DEP_LOCKS 表扩展（flask/requests 的 BugsInPy 版本线） |
| 红绿翻转判定 | swebench_task_judge.py 协议直接复用 |
| 结构化记录 | JUDGE_*.json 同 schema |

## 成本预估

2 臂 × 20 任务 × 实测 tokens/task（编排 ~10k / df ~2.4k）≈ 250k tokens ≈ **$0.25**。

## 判据（冻结前定稿）

- 主读数：两臂检出率（红→绿翻转成功 = 检出）+ δ（aitester − df）。
- **C8 声明模板**（执行后回填）：在 {n} 个真实缺陷上，检出优先协议 X%、
  编排 Y%（δ=Z pp；CI；快照指纹标签必带）。

## 风险与披露预登记

1. BugsInPy 的 repo 快照年久（2019-2020 线）——依赖考古难度高于 SWE-bench
   实例（Python 3.6/3.7 时代），**Python 版本矩阵可能需要 3.8/3.9**（uv 可装）。
2. BugsInPy gold test 的 pytest 兼容性未验证——首任务端到端验证是执行前置。
3. 20 任务小样**不构成**统计外推主张——声明限定"方向性外部效度证据"。

## 偏离表（2026-10-31 补登；此前违反"偏离须登记"条款，追记）

| # | 冻结选型 | 实际执行 | 影响 | 处置 |
|---|---|---|---|---|
| D1 | 项目子集 = pallets/flask + psf/requests | PySnooper（3 bugs）+ sanic（5 bugs） | flask/requests **不在 BugsInPy 17 项目集**（冻结选型调研失实，结构性不可得） | 已执行部分降级为"判定器验证小样"（红绿翻转协议可用性），不得作为 C8 主读数引用 |
| D2 | 每项目 10 bug（20 任务） | PySnooper 3 + sanic 5（共 8） | 候选轻依赖项目无一满 10 bug | 同上 |
| D3 | 2 臂 LLM 批（aitester + plain_llm_df） | 零 LLM 判定（gold 红绿翻转） | **C8 主读数（2 臂检出率 + δ）未产出** | 主批待修订选型后另批执行 |

**修订选型候选（待用户确认后重新冻结）**：以实际存在的项目重选——
tqdm（9）+ thefuck（32）/ scrapy（40）子集分层抽样，或 tornado（16）+
black（23）；规模口径（每项目 bug 数上限、总任务量）随选型重冻。
manifest 导出工具链（bugsinpy-checkout → BugsInPyDataset manifest）在
主批前须先用 1 个 bug 冒烟验证（PySnooper/sanic 判定走的是
swebench_task_judge 独立通路，不等于 manifest 通路可用）。

## v1 修订选型（2026-10-31 16:50 冻结执行；文档落盘滞后于主批启动，如实记录）

| 项 | 冻结值 |
|---|---|
| 项目子集 | **PySnooper（3 bugs）+ sanic（5 bugs）= 8 bugs**——判定器已验证红绿翻转可用的分母（10-30 判定轮），repos 已克隆、micromamba py3.8.20 环境在位 |
| 臂 | aitester + plain_llm_df（原冻结不变） |
| 任务形态 | BugsInPyDataset manifest（buggy_code/fixed_code/test_code，单文件上下文 + gold_patch 扩展字段）；`AITESTER_BUGSINPY_DATA` 指向 |
| 生成判定 | **检出 = 生成测试在 buggy 上「红」（pytest failed≥1）∧ 在 fixed 上「绿」（退出码 0）**；收集失败 = invalid_test 不计检出；环境失败 = env_error 不进分母 |
| 偏离 | 规模 8 vs 20（D2 延续：候选项目 bug 不足）；manifest 单文件上下文截断（多文件 bug 的次要文件不进 LLM 上下文，gold_patch 完整用于判定） |
| 工具链 | `export_bugsinpy_manifest.py`（新，manifest 导出 8/8）+ `judge_c8_generated_tests.py`（新，复用 bugsinpy_judge 环境管理） |
| 成本实测 | 主批 2 臂 8 任务 158k tokens ≈ **$0.16**（冒烟 + 主批，冻结估算 $0.25 内） |
| 冒烟 | 1 任务通路验证通过（加载→生成→执行反馈环，10,958 tok） |

## v3 扩样修订（2026-10-31 21:05 冻结执行，数据产生前落盘）

| 项 | 冻结值 |
|---|---|
| 扩样选型 | **tqdm（9 bugs 全跑）+ tornado（16 bugs 字典序前 11）= 20 任务**——向原冻结规模 20 靠拢；tornado 抽样规则 = bugs 目录字典序（确定性可复现） |
| 环境事实 | tqdm 全部 py3.6.9、tornado 全部 py3.7.0——判定统一用 py3.8.20 判定 venv（3.6/3.7 代码向后兼容至 3.8；依赖 requirements best-effort 装失败逐包披露）；repos 已 clone、25/25 commit 可达 |
| 判据 | v2 同款：检出 = 生成测试 buggy 上红（failed≥1）∧ fixed 上绿（exit 0）；invalid_test / env_error 不进检出分母并披露 |
| 成本预估 | 2 臂 × 20 任务 × ~8k tok ≈ 320k tok ≈ **$0.35** |
| 与 v2 关系 | v2 读数（PySnooper+sanic 8）保留为「判定器已验证分母」层；v3 扩样为「规模对齐冻结口径」层——两层并列披露、分母不混池 |
