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
