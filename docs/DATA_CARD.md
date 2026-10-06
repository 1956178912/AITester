> **语言 / Language**：[English](DATA_CARD.en.md) | 简体中文（本文）

# 数据卡（DATA CARD）

最后更新：2026-10-06（AA2：§2 重复采样偏差登记缓解机制 `max_pattern_repeat`；
此前 Z6 新增：数据治理缺口补齐——此前数据说明并入
MODEL_CARD §3，无独立数据卡；审查 R15 落地）

## 1. 数据集总览

| 数据集 | 加载名 | 状态 | 用途 |
|--------|--------|------|------|
| 合成缺陷模板库 | `synthetic` | ✅ 主批次在用（n=50 任务） | 主实验 / 消融 |
| QuixBugs（Python 子集） | `quixbugs` | 加载器就绪，**零实跑** | 真实缺陷阶梯 L1 |
| BugsInPy | `bugsinpy` | 加载器就绪，**零实跑** | 真实缺陷阶梯 L2 |
| SWE-bench Lite | `swe_bench` | 历史 0/20 冒烟 | 仓库级（靶点错位，见下） |

## 2. 合成模板库（当前主批次基准）

- **来源**：全部由项目作者手写（8 个 pattern 池按 name 去重共 50 个唯一
  缺陷 pattern，`BASELINE.yaml synthetic_templates` 为单一事实来源，
  `scripts/verify_synthetic_templates.py` 三重不变量自验证）；
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
   消费点"不变量**尚无测试锁定**（登记为待办）；
4. **统计功效**：n=50 在 detection 2% 基线下对 10pp 差异的检验功效不足
   （`scripts/power_analysis.py` 可复算）。

## 4. 真实缺陷阶梯（L1/L2）

- **QuixBugs**：本地目录解析（`python_programs/` 缺陷版 +
  `correct_python_programs/` 修复版 + `python_testcases/` 官方测试），
  目录缺失时空数据集 + warning 优雅降级；数据目录经
  `AITESTER_QUIXBUGS_DATA` 注入（不随仓库分发，需自行获取上游数据）；
- **BugsInPy**：manifest JSONL 口径（project / bug_id / buggy_code /
  fixed_code / test_code），task_id 末段为 ≤30 字符中性模块名（防泄缺陷
  语义）；`AITESTER_BUGSINPY_DATA` 注入；
- **许可**：上游 QuixBugs / BugsInPy 数据**接入实跑前**须核实各自仓库
  许可并在本卡登记核实结论与获取 commit（当前标注：待核实）。

## 5. 维护约定

- 本卡随数据集变更同步更新（双语配对由 CI
  `scripts/check_bilingual_docs.py --strict` 守卫）；
- pattern 总数 / 主批次构成数字以 `BASELINE.yaml` 为单一事实来源，
  本卡只描述口径不承载"当前数字"；
- 新增数据源必须在本卡登记：来源、构造方式、gold 材料位置、泄漏
  控制措施、许可核实结论。
