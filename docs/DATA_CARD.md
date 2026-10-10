> **语言 / Language**：[English](DATA_CARD.en.md) | 简体中文（本文）

# 数据卡（DATA CARD）

最后更新：2026-10-08（R20：§4 新增 QuixBugs 定位降格声明——近饱和
（引 2025–2026 横向坐标）+ 记忆污染风险，限定为 L1 管道验证；§1 状态列
更新为"单臂复跑（非 E4 正式执行）"。此前 2026-10-07：AN1：§4 新增
TestGenEval L2 候补评估登记——
CC BY-NC 4.0 经 LICENSE 原文核实，与 BugsInPy 同列非清洁许可门槛；
此前 AH1：§4 许可节权威核实——QuixBugs MIT 已确认
〔L1 前置解除〕、BugsInPy 无 SPDX 许可证〔L2 决策门槛新登记〕；
此前 AA2：§2 重复采样偏差登记缓解机制 `max_pattern_repeat`；
此前 Z6 新增：数据治理缺口补齐——此前数据说明并入
MODEL_CARD §3，无独立数据卡；审查 R15 落地）

## 1. 数据集总览

| 数据集 | 加载名 | 状态 | 用途 |
|--------|--------|------|------|
| 合成缺陷模板库 | `synthetic` | ✅ 主批次在用（n=50 任务） | 主实验 / 消融 |
| QuixBugs（Python 子集） | `quixbugs` | 单臂 aitester 复跑（R4 副产品，**非 E4 正式执行**）；L1 管道验证用 | 真实缺陷阶梯 L1 |
| BugsInPy | `bugsinpy` | 加载器就绪，**零实跑** | 真实缺陷阶梯 L2 |
| SWE-bench Lite | `swe_bench` | 历史 0/20 冒烟 | 仓库级（靶点错位，见下） |

## 2. 合成模板库（当前主批次基准）

- **来源**：全部由项目作者手写（8 个 pattern 池按 name 去重共 50 个唯一
  缺陷 pattern，`BASELINE.yaml synthetic_templates` 为单一事实来源，
  `scripts/tools/verify_synthetic_templates.py` 三重不变量自验证）；
- **构造**：每 pattern 含 buggy `template` / `fixed` / gold `test_cases`
  三件套；实例化仅追加噪声注释（`# noise_seed=<0-9999>`）并做 task_id
  中性化（`task_0000..`，P1-4 泄漏修复——此前文件名内嵌 pattern 名等于
  答案），gold 测试 import 同步重写（`_neutralize_gold_imports`）；
- **主批次构成**：n=50、seed=42、3 基线；难度 L1-L5 分布
  {15,10,10,8,7}；8 个跨文件任务；bug_type：assertion 30 / runtime 20；
  pattern 存在重复采样（如 `import_chain_type_contract` 出现 10 次）——
  AA2（2026-10-06）已提供缓解机制：`SyntheticDataset(max_pattern_repeat=...)` /
  `run_benchmark --max-pattern-repeat`（opt-in，默认口径与 seed=42 复现性
  不变）；后续重跑主实验建议启用该参数；
- **gold 材料 schema**：`metadata["test_cases"]`（gold 测试）、
  `metadata["fixed"]`（单文件 gold 补丁）、`fixed_module_code`（跨文件）、
  `pass_to_pass`（P2P 回归集）。gold 材料只进结果行 `task_metadata`，
  **不进任何 LLM prompt**。

## 3. 已知偏差与限制（诚实声明）

1. **出题人 = 判卷人**：gold 测试 / fixed 补丁 / 任务模板同由项目作者
   手写，detection / repair 的"真值"与系统面对的题目强耦合——内部效度
   受限，正向证据不可外推（`docs/design/real_benchmark_upgrade.md` 的
   阶梯计划即为此而设）；
2. **分布偏差**：函数级 Python 单语言、模板缺陷类型集中于 assertion /
   runtime 两类，不代表真实仓库缺陷分布；
3. **泄漏通道现状**：`problem_statement`（= pattern description，字面上
   是缺陷答案）当前仅被注入扫描消费、不进任何 prompt——该"无 prompt
   消费点"不变量**已由静态守卫测试锁定**（AF-D，2026-10-06：
   tests/test_af_batch.py；新增 prompt 侧消费必须显式更新本卡与该测试）；
4. **统计功效**：n=50 在 detection 2% 基线下对 10pp 差异的检验功效不足
   （`scripts/tools/power_analysis.py` 可复算）。

## 4. 真实缺陷阶梯（L1/L2）

- **QuixBugs**：本地目录解析（`python_programs/` 缺陷版 +
  `correct_python_programs/` 修复版 + `python_testcases/` 官方测试），
  目录缺失时空数据集 + warning 优雅降级；数据目录经
  `AITESTER_QUIXBUGS_DATA` 注入（不随仓库分发，需自行获取上游数据）；
- **BugsInPy**：manifest JSONL 口径（project / bug_id / buggy_code /
  fixed_code / test_code），task_id 末段为 ≤30 字符中性模块名（防泄缺陷
  语义）；`AITESTER_BUGSINPY_DATA` 注入；
- **TestGenEval（L2 候补评估登记，AN1，2026-10-07；未加载零实跑）**：
  `facebookresearch/testgeneval`（Jain et al., ICLR 2025，
  arXiv:2410.00752）——真实仓库上下文的单元测试生成/补全基准
  （1,210 文件对 / 68,647 测试 / 11 个活跃 Python 仓库，由 SWE-bench
  改造），与本项目"测试生成"主命题同域，比 BugsInPy 的"缺陷修复"口径
  更贴题；**许可：CC BY-NC 4.0**（GitHub API license 字段
  `spdx_id=NOASSERTION`，LICENSE 原文核实 2026-10-07 =
  Attribution-NonCommercial 4.0 International）——学术非商业研究评估
  可用（署名），商业用途与衍生工件再分发受限；与 BugsInPy 同列
  "非清洁许可"门槛（下方三选一口径同样适用），L2 立项时并列决策；
- **许可**（AH1，2026-10-06 经 GitHub API 权威核实并登记）：
  - **QuixBugs：MIT License（已核实，L1/E4 前置条件解除）**——
    `api.github.com/repos/jkoppel/QuixBugs` license 字段
    `spdx_id=MIT`（核实日期 2026-10-06）；**数据已获取**（AJ 批，
    2026-10-06）：本地 `data/quixbugs`（gitignore 区不入库），
    commit `4257f44b0ff1181dedaedee6a447e133219fcebf`；零 LLM 加载器
    冒烟实测 50 程序加载、41 个 gold 三件套齐全（9 个无官方测试的
    任务按 M1 口径 detection=None 不进分母）；
  - **QuixBugs 定位降格（R20，2026-10-08 R2）——近饱和 + 记忆污染风险，
    定位为 L1 管道验证而非外部效度主张**：
    - **近饱和**：2025–2026 横向坐标显示前沿模型已接近满分——
      GPT-o1 40/40、GPT-4o 38/40、ThinkRepair / ContrastRepair 40/40
      （40 为 QuixBugs Python 子集全量）、claude-code 适配器 resolve
      ≈80.75%（**聚合来源，个别数字待原文复核**）；本项目可测口径
      90.2%/87.8%（37/41、36/41）位于"饱和前沿之下、非 SOTA"区间；
    - **记忆污染风险**：QuixBugs 为公开小基准（40 程序），存在训练集
      记忆污染嫌疑（与本项目对 SWE-bench Verified 弃用的卫生叙事同向）；
    - **用途限定**：仅作"管道可用性验证"（验证真实基准链路可跑通、
      gold 材料/包结构/证据门行为可观测）；**外部效度主张迁移**至
      BugsInPy（许可待决，见下）或 TestGenEval（CC BY-NC 门槛）。
    - 引用纪律：引用其数字须注明"M1 可测口径 + 近饱和 + 不作外效主张"
      （见 `docs/design/repair_caliber_matrix.md`）。
  - **BugsInPy：无 SPDX 可识别许可证（新发现合规门槛，L2 实跑前须
    用户决策）**——`api.github.com/repos/google/bugsinpy` license 字段
    为 null（2026-10-06 核实），即上游未随仓库声明许可、默认版权保留；
    缓解措施：数据仅本地研究性使用（gitignore 区，不随仓库分发），
    但**不构成完整合规**。L2 立项前三选一：①联系上游取得书面许可；
    ②改用带许可证的真实缺陷基准（如 SWE-bench 系 MIT / Multi-SWE-bench）；
    ③风险接受并在本卡与全局决策日志双登记。QuixBugs L1（E4）不受此
    影响，可先行。

## 5. 维护约定

- 本卡随数据集变更同步更新（双语配对由 CI
  `scripts/gates/check_bilingual_docs.py --strict` 守卫）；
- pattern 总数 / 主批次构成数字以 `BASELINE.yaml` 为单一事实来源，
  本卡只描述口径不承载"当前数字"；
- 新增数据源必须在本卡登记：来源、构造方式、gold 材料位置、泄漏
  控制措施、许可核实结论。
