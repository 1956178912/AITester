# 真实基准升级设计（BugsInPy / QuixBugs / SWE-bench Lite 三级递进）

批次：U13（2026-10-05 系统性审查落地）·状态：**L1/L2 加载器已落地（W4，2026-10-05：`src/datasets/dataset_realbugs.py` 的 `QuixBugsDataset` / `BugsInPyDataset`，经 `load_dataset("quixbugs"|"bugsinpy")` 注册）**；L2 manifest 导出与 L3 复测仍未实现——本文档其余部分仍为设计稿
前置约束（全局决策日志 2026-10-05 条目）：R3 基准升级属大改动，需先出设计文档再动代码——本文档即该设计。

## 1. 动机与现状

当前系统在真实基准上的实证为零：SWE-bench Lite n=20 冒烟 resolved 0/20（限流 + 缺 `instance_code`/`sqlfluff` 依赖，工件 `results/swebench_20_summary.json` 等 5 份一致）；主批次全部证据来自合成数据集（历史批 n=50：detection 2.0% / repair 0.0% / false_fix 89.8%；当前口径 R-P0-2 三种子 n=261/臂：detection 15.8% / repair 0.0%）。合成集无法回答"系统对真实历史缺陷是否有效"。

系统能力定位是**函数级**修复（合成集同为函数级），而 SWE-bench Lite 是仓库级基准——靶点错位。2026-10 检索口径（AL14 更新）：**SWE-bench Verified 已于 2026-02-23 被 OpenAI 官方弃用**（定性"饱和且高度污染"，内部审计发现 59.4% 最难未解任务的测试本身有缺陷）；替代榜 SWE-bench Pro / SWE-bench Live / SWE-rebench 三者排名互相冲突（2026-04 分析）——**L3 选型原则（预注册）：防污染滚动基准二选一（SWE-bench Live〔arXiv 2505.23419，滚动新增真实 issue〕 vs SWE-rebench〔Nebius 持续重建〕），执行前在 ADR 固化选型与理由，禁止单源口径；引用任何具体 SOTA 分数须先联网核验**；函数级/单文件级基准更贴合本系统能力（不变）。

## 2. 三级递进设计

| 级 | 基准 | 粒度 | 为什么 | 首批规模 | 前置工程 |
| --- | --- | --- | --- | --- | --- |
| L1 | **QuixBugs**（arXiv 2017，2023 起被 LLM-APR 广泛复用） | 单函数 | 每题 ≤30 行、含 gold 补丁与多语言对齐版本、无环境构建；与现有合成链路同构度最高 | 40 题全量 | 仅需 dataset_loader 新增后端（读 JSON 题面 + 注入缺陷版函数） |
| L2 | **BugsInPy**（2020，持续维护） | 单文件/模块 | 真实 GitHub 项目历史缺陷、含 gold 补丁与 F2P/P2P 测试清单、Python 生态；per-repo 容器化后工程量可控 | 3 个项目 × 10 缺陷 = 30 | per-repo venv/Docker 构建 + 测试裁剪（沿用 executor_repo 的 per-env 锁与超时收敛） |
| L3 | **SWE-bench Lite**（ICLR 2024） | 仓库级 | 外部效度终点；官方评价口径（F2P/P2P/patch apply） | 20（修复 0/20 的阻塞项后复测） | ① download_swe_bench 补 lite 子集；② export_swe_bench_source 生成 SWE_BENCH_ENRICHMENT（git clone 各仓库）；③ per-repo 依赖安装脚本（0/20 根因：sqlfluff 等缺依赖 + API 限流重试） |

**判定口径（对齐 M1 严谨性检查点）**：
- 主指标：resolved（gold F2P 全过 ∧ P2P 不回归 ∧ 补丁非仅改测试）；辅助：detection / repair / false_fix / FL@k / patch_plausible / $/task。
- 严谨性红线：`test_visible_to_system`（系统不得看见 gold 测试）、`source_patched_unverified` 观测、`fail-to-pass` 三段判定全部沿用 `experiments/_m1_metrics` 既有实现，不另造口径。

## 3. 工程改动清单（按依赖序）

1. **dataset_loader 后端**：新增 `QuixBugsDataset` / `BugsInPyDataset`（实现 `BaseDatasetLoader` 接口，`load_dataset` 工厂注册；未知数据集名静默降级 InMemoryDataset 的行为需同步改为显式报错，防拼写错误被掩盖——审查 U10 同口径）。
2. **per-repo 环境构建**（L2/L3）：复用 `executor_repo.RepoExecutor` 的 per-env 锁 / 超时 rc=124 收敛 / 路径越界防护；新增 `scripts/build_bugsinpy_env.py`（一次性预构建 + 磁盘缓存，键 = repo@commit）。
3. **限流治理**（L3 复测前置）：run_benchmark 已有 API 健康轮换；补"429 指数退避 + 单任务失败可断点续跑"（结果 JSONL 追加式落盘，重启跳过已完成 task_id）。
4. **统计协议**：沿用 R14（McNemar + BH-FDR）与固定 seed；每基准先跑 n≤50 探路批，全绿工时 <1 天再扩量。

## 4. 风险与回退

| 风险 | 缓解 |
| --- | --- |
| BugsInPy 环境构建不可复现（老依赖装不上） | 限定 2023 年后维护活跃的 3 个项目起步；Dockerfile.repro 扩展 per-repo 层 |
| L3 依旧 0 resolved | 归因拆解（定位失败/补丁失败/环境失败三桶，用 U11 failure_taxonomy 标注），把"L3 阻塞项清单"而非 resolved 数字作为该级交付 |
| API 预算 | L1 零 LLM 成本链路（确定性 oracle）先行；LLM 批次按 $/task 预算闸（COST_BUDGET_USD）封顶 |

## 5. 验收标准

- L1：QuixBugs 全量 40 题跑通，detection>0 且 resolved>0（首证系统在真实缺陷上的非零检出）。
- L2：BugsInPy 30 题跑通，产出与合成集同 schema 的 M1 指标行（false_fix 可跨基准对比）。
- L3：0/20 的两类根因（缺依赖、限流）被消除，复测产出新的 statistical_report；若仍为 0，交付 U11 桶分布与根因清单。

## 6. 参考

- QuixBugs: Lin et al., arXiv:1708.00154（程序修复多语言基准）。
- BugsInPy: Widyasari et al., ASE 2020（真实 PyPI 项目缺陷库，F2P/P2P 清单）。
- SWE-bench: Jimenez et al., ICLR 2024；Verified 为 OpenAI 2024 人工筛选子集（引用前经 `scripts/check_citations.py --online` 核验）。
