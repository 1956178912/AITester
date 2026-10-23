# EMSE 统计补口报告：主对比 MDE/功效 + 比例型端点 bootstrap 95% CI

（2026-10-15 批次；零 LLM / 零网络 / 只读归档工件；全部数字由 `experiments/emse_stats_report.py` 现算）

## 0. 口径（caliber）

- **派生证据声明**：本报告由 `experiments/emse_stats_report.py` 从下述**已归档批次 JSON**派生（零 LLM / 零网络 / 只读工件），全部数字现算；它**不替代**预注册主报告，引用时须标注为派生证据（canonical 口径以 `statistical_report_3seed_pooled.md` 为准）。
- 生成时间：2026-10-17 10:16:48（本地时间）；复算命令：`python -m experiments.emse_stats_report`
- 批次目录：`/Users/wangchenyu/Workspace/AITester/experiments/results/main_batch`；批次文件（3）：
  - `benchmark_synthetic_20261006_140906.json`（seed=42，行前缀 `s42__`，sha256=`6e31c07dd76ce7c3…`，每臂行数 aitester:87、plain_llm:87、plain_llm_df:87）
  - `benchmark_synthetic_20261006_151907.json`（seed=43，行前缀 `s43__`，sha256=`bb5fcfc8afebeb5a…`，每臂行数 aitester:87、plain_llm:87、plain_llm_df:87）
  - `benchmark_synthetic_20261006_164357.json`（seed=44，行前缀 `s44__`，sha256=`be6a42e5597a449b…`，每臂行数 aitester:87、plain_llm:87、plain_llm_df:87）
- 臂（3）：`aitester` / `plain_llm` / `plain_llm_df`
- **种子处理**：跨种子池化——行 `task_id` 加 `s<seed>__` 前缀（seed 取批次 `provenance.seed`，回退顶层 `seed`，再回退文件名），与 `statistical_analysis.py --pool-seeds` 同口径；3 种子 × 87 任务 → 261 配对单元/臂（同种子重复跑仍按最新批次优先去重）。
- **缺失值口径**：M1 诚实口径——端点字段为 `None` 的行**剔除**（不计 0、不进分母）；配对要求两侧该字段均可测（`emse_optimization.paired_contrast` 同口径）。
- **统计口径来源**：MDE σ_d² 闭式 = `scripts/tools/power_analysis.py` 的 n_required 公式反演（α=0.05 双侧，power=0.8）；MDE ψ/4 = `experiments/emse_optimization.mde_paired_pp`；比例型端点 95% CI = `experiments/statistical_analysis.bootstrap_paired_diff_ci`（配对差值均值，百分位法，10000 次重采样，seed=42，order-statistic 分位）。
- **未含聚类校正**：模板聚类稳健性（26 个唯一程序体 / 31 模板簇）见 canonical 报告 AC4 节，本报告的 n 与 CI 均为逐任务独立口径（名义偏乐观）。

## 1. 三主要对比的 MDE / 功效（主端点 detection_rate）

配对结构（McNemar 2×2 的不一致单元；n10 = 前臂检出=1 且后臂=0，n01 = 反向，n11 = 均检出）：

| 对比（前臂 − 后臂） | n_common | n10 | n01 | n11 | n00 | ψ（不一致率） | 观测 δ(pp) |
|---|---|---|---|---|---|---|---|
| `aitester` vs `plain_llm` | 240 | 37 | 3 | 1 | 199 | 0.1667 | 14.1667 |
| `aitester` vs `plain_llm_df` | 240 | 12 | 80 | 26 | 122 | 0.3833 | -28.3333 |
| `plain_llm_df` vs `plain_llm` | 261 | 113 | 0 | 4 | 144 | 0.4330 | 43.2950 |

MDE（α=0.05 双侧 / power=0.8，单位 pp）与观测效应比值——**观测/MDE < 1 表示该对比在当前 n 下本就检不出**：

| 对比 | MDE_σ(pp)（闭式，主口径） | MDE_σ(pp)（二分） | MDE_ψ(pp)（ψ/4 口径） | 观测/MDE_σ | 观测/MDE_ψ | 功效@观测δ（σ_d²） | 功效@观测δ（ψ） | 达 80% 功效所需 n（σ_d²） |
|---|---|---|---|---|---|---|---|---|
| `aitester` vs `plain_llm` | 6.9241 | 4.8120 | 3.6914 | 2.0460 | 3.8377 | 0.9999 | 1.0000 | 58 |
| `aitester` vs `plain_llm_df` | 9.9554 | 7.4293 | 5.5983 | 2.8460 | 5.0611 | 1.0000 | 1.0000 | 30 |
| `plain_llm_df` vs `plain_llm` | 8.5924 | 2.9194 | 5.7052 | 5.0388 | 7.5887 | 1.0000 | 1.0000 | 11 |

**口径说明（三个 MDE 列不可混用）**：

1. `MDE_σ` 闭式（主口径）= `(z_{1−α/2}+z_power)·√(σ_d²/n)`，σ_d² = p_a + p_b − δ² − 2·p11 取**观测不一致结构**（源：`scripts/tools/power_analysis.py` 的 n_required 公式，闭式反演）。
2. `MDE_σ` 二分 = `power_analysis.detectable_delta_paired`：该函数在候选 δ 上**重算** σ_d²（p_a = p_b + δ，p11 固定），当不一致结构退化（如 n01=0 且 p11≈p_b，σ_d²→0）时会把 MDE 压到远小于闭式值——属「结构随 δ 漂移」的乐观口径，仅作交叉核对，**不用于主结论**。
3. `MDE_ψ` = `emse_optimization.mde_paired_pp`（10-13 定案公式，只用不一致率 ψ、不区分 n10/n01 的分布，未乘 (1−ψ) 项），与 σ_d² 口径不可互推，只作定案口径对照。

功效与所需 n 的 σ_d² 口径分别复用 `power_analysis.power_paired` 与 `power_analysis.required_n_paired`（后者在闭式 n 上自增直到达标功效）。

## 2. 比例型端点：各臂点估计（None 剔除，不计 0）

| 臂 | 端点 | 可测分子/分母 | 点估计(%) |
|---|---|---|---|
| `aitester` | detection_rate（边际） | 38/240 | 15.8333 |
| `aitester` | repair_rate（边际） | 0/240 | 0.0000 |
| `aitester` | false_fix_rate（边际） | 143/240 | 59.5833 |
| `aitester` | false_fix_rate（条件：passed=True） | 143/143 | 100.0000 |
| `plain_llm` | detection_rate（边际） | 4/261 | 1.5326 |
| `plain_llm` | repair_rate（边际） | 0/261 | 0.0000 |
| `plain_llm` | false_fix_rate（边际） | 229/261 | 87.7395 |
| `plain_llm` | false_fix_rate（条件：passed=True） | 229/229 | 100.0000 |
| `plain_llm_df` | detection_rate（边际） | 117/261 | 44.8276 |
| `plain_llm_df` | repair_rate（边际） | 0/261 | 0.0000 |
| `plain_llm_df` | false_fix_rate（边际） | 7/261 | 2.6820 |
| `plain_llm_df` | false_fix_rate（条件：passed=True） | 7/7 | 100.0000 |

## 3. 比例型端点：配对差 95% CI（bootstrap，10000 次重采样，seed=42）

配对差 = 前臂 − 后臂（pp）；条件口径 = 两侧皆 `passed=True` 的行子集（配对不变）。

| 对比（前臂 − 后臂） | 端点 | n_pairs | 配对差(pp) | 95% CI(pp) | 排除 0？ |
|---|---|---|---|---|---|
| `aitester` vs `plain_llm` | detection_rate（边际） | 240 | 14.1667 | [9.5833, 19.1667] | 是 |
| `aitester` vs `plain_llm` | repair_rate（边际） | 240 | 0.0000 | [0.0000, 0.0000] | 否 |
| `aitester` vs `plain_llm` | false_fix_rate（边际） | 240 | -27.9167 | [-35.4167, -20.4167] | 是 |
| `aitester` vs `plain_llm` | false_fix_rate（条件：passed=True） | 124 | 0.0000 | [0.0000, 0.0000] | 否 |
| `aitester` vs `plain_llm_df` | detection_rate（边际） | 240 | -28.3333 | [-35.4167, -21.2500] | 是 |
| `aitester` vs `plain_llm_df` | repair_rate（边际） | 240 | 0.0000 | [0.0000, 0.0000] | 否 |
| `aitester` vs `plain_llm_df` | false_fix_rate（边际） | 240 | 57.0833 | [50.4167, 63.7500] | 是 |
| `aitester` vs `plain_llm_df` | false_fix_rate（条件：passed=True） | 1 | — | — | — |
| `plain_llm_df` vs `plain_llm` | detection_rate（边际） | 261 | 43.2950 | [37.1648, 49.4253] | 是 |
| `plain_llm_df` vs `plain_llm` | repair_rate（边际） | 261 | 0.0000 | [0.0000, 0.0000] | 否 |
| `plain_llm_df` vs `plain_llm` | false_fix_rate（边际） | 261 | -85.0575 | [-89.2720, -80.4598] | 是 |
| `plain_llm_df` vs `plain_llm` | false_fix_rate（条件：passed=True） | 7 | 0.0000 | [0.0000, 0.0000] | 否 |

`—` = 不可计算（n_pairs<2：helper 返回 nan），**不是 0**；`[0.0000, 0.0000]` 则是真实的零宽区间（逐任务差值全为 0，如原口径 repair）。

口径备注：CI 由 `bootstrap_paired_diff_ci` 计算——该 helper 的签名只接受 `passed` 字段（无 field 参数），故本工具把端点字段**投影**到 `passed` 键上再调用（浅拷贝适配，配对与重采样逻辑完全复用，未重实现 bootstrap）；`None` 行在配对阶段即退出分母。
条件 false_fix 的两臂点估计按各臂自身 passed 行计算（§2），而 §3 的配对差限制在**两侧皆 passed** 的子集（保持配对结构），故 §3 的点估计与 §2 两臂点估计之差不必然相等。
CI 为百分位法（order-statistic）区间，非基本 bootstrap；`n_pairs<2` 时 helper 返回 nan，本报告记 `—`（不臆造区间）。

## 4. 成本分布：每任务 tokens（中位数 + IQR，不只报均值）

| 臂 | 行数 | 有正向记账行 | 中位数 tokens | Q1 | Q3 | IQR | 均值 | 记账健全性 |
|---|---|---|---|---|---|---|---|---|
| `aitester` | 261 | 261 | 23193.0 | 16898.0 | 32060.0 | 15162.0 | 26114.8 | 可计算（0 行无记账） |
| `plain_llm` | 261 | 261 | 2495.0 | 1920.0 | 3708.0 | 1788.0 | 3209.4 | 可计算（0 行无记账） |
| `plain_llm_df` | 261 | 226 | 3779.0 | 2814.2 | 5717.5 | 2903.2 | 4877.1 | 可计算（35 行无记账） |

分位口径：`statistics.quantiles(..., n=4, method='inclusive')`（线性插值）；只统计 `token_usage.total_tokens > 0` 的行（与 S11 记账健全性判定同口径）；记账断裂的臂一律输出 NOT_COMPUTABLE，不给成本数字。

## 5. 修正口径（repair / false_fix，ADR-0021/0027）

**本报告默认输出原口径（raw）数字**：修正口径需按 ADR-0021 对带补丁行做 `normalize_patch_text` + gold `test_cases` 重放（`experiments/corrected_metrics.correct_row`，本地 pytest 子进程、零 LLM），属重型路径——请运行 `make corrected-metrics`，或本工具 `--corrected-repair` 开关（同一函数、只读工件）后再引用修正值。

已知影响面：R-P0-2 的「repair 全线 0」系 patch 字段围栏残留导致的测量伪影（ADR-0021），原口径 `repair_rate` 因此系统性压零；本报告 §2/§3 的 repair 行须与该勘误同读。

## 6. 不可计算项与局限（显式登记，不用代理值替代）

- `aitester` vs `plain_llm_df` · false_fix_rate（条件：passed=True）：n_pairs=1 < 2，CI 不可计算。
- **repair_rate 端点的功效分析无对象（现算）**：三对比配对结构 `aitester vs plain_llm` n10/n01=0/0；`aitester vs plain_llm_df` n10/n01=0/0；`plain_llm_df vs plain_llm` n10/n01=0/0——不一致对全为 0（ψ=0），正态近似退化，故本报告不为 repair 端点报 MDE/功效（`emse_optimization.mde_paired_pp` 在 ψ=0 时按设计返回 None；不以 0 冒充 MDE），对应 §3 的配对差亦为真实的零宽区间 [0, 0]。
- 修正口径 repair/false_fix：默认未现算（重型重放路径），见 §5 说明。
- 本报告为**逐任务独立口径**：27 模板 → 26 个唯一程序体（S13），跨种子同模板任务相关，n 与 CI 名义偏乐观；聚类稳健结论以 canonical 报告 AC4 节为准。
- MDE 为**正态近似**（无精确检验对应物），且假定不一致结构在备择下不变；观测 δ 远大于 MDE 时该近似不影响定性结论，接近 MDE 量级时须谨慎。

---

*报告生成：`experiments/emse_stats_report.py`（EMSE 统计补口批次 2026-10-15；派生证据，不得替代预注册主报告）*
