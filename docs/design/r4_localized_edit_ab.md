# R4 A/B 预注册：定位锚定的局部编辑通道（LOCALIZED_EDIT_ENABLE）

- 日期：2026-10-08
- 状态：预注册（跑批前固化；判定规则与阈值在本文件落盘后不因结果而改）
- 关联：`src/tools/patch_localized.py`、ADR-0024（反事实 FL 上界）、ADR-0028（FL 约束观测门）、ADR-0018（编辑意图确定性落盘）

## 目的

验证"定位锚定的局部编辑约束"（`LOCALIZED_EDIT_ENABLE`）对修复质量的增量贡献。
ADR-0024 反事实指出 `P(correct | FL 命中)=15.8%` < `P(correct | FL 未命中)=64.7%`，
根因是补丁生成走整文件重写、不消费定位信号。本实验在"编辑意图通道
（`EDIT_INTENT_ENABLE`）"之上叠加定位锚定约束，隔离后者的净贡献。

## 臂

| 臂 | 环境变量 | 含义 |
|----|----------|------|
| A（对照） | `EDIT_INTENT_ENABLE=true` | 编辑意图通道，**无**定位约束（历史口径） |
| B（处理） | `EDIT_INTENT_ENABLE=true` + `LOCALIZED_EDIT_ENABLE=true` | 编辑意图 + 定位锚定约束（R4） |

两臂均为 `aitester` 完整管线；差异仅 `LOCALIZED_EDIT_ENABLE` 一个开关。
`AITESTER_PROFILE=logic` 已注入 `FAULT_LOCALIZER_ENABLE=true` +
`FL_SPECTRAL_ENABLE=true`，故定位信号在两臂均产出（A 臂仅"告知"、B 臂升级为"约束"）。

## 设计

- 数据集：synthetic，n=50，seed=42
- 模型：deepseek-flash（`.env.local` LLM_1）
- `AITESTER_PROFILE=logic`、`TEMPERATURE=0`（确定性采样）、`--max-pattern-repeat 2`
- 基线：`aitester` 单臂（两批各一臂，`--skip-stats` 后手工对比）
- LLM 缓存：两臂 Debugger prompt 不同（B 多局部化约束段），缓存 key 天然隔离；
  Planner / FaultLocalizer prompt 相同可命中缓存（保证定位一致 + 省 token）。

## 主终点

1. `repair_rate`（gold 独立裁决，修正口径——见 ADR-0021/0027）
2. `patch_correct` 行数

## 机制终点

1. `edit_localization.localized_ratio`（仅 B 臂非 None；衡量约束被 LLM 遵循程度）
2. `edit_localization.violations`（锚点越界诊断分布）
3. `fl_constraint_verdict`（hit / miss 占比——补丁实际修改位置与定位候选的求交）

## 判定规则

- H1（主）：B 臂 `repair_rate` ≥ A 臂，且 `patch_correct` 不下降；
- H2（机制）：B 臂 `localized_ratio` > 0（约束被遵循，非空转）；
- H3（机制）：B 臂 `fl_constraint_verdict=hit` 占比 ≥ A 臂。

结果如实记录，不因方向不理想而筛选或改判。若 H1 不成立（局部化约束未提升修复率），
记为阴性（与 ADR-0024"生成侧主导"结论一致：约束落点可能仍未触及整文件重写的根因）；
若 H2 不成立（`localized_ratio`≈0），说明 LLM 未遵循约束或锚点过严，需回查 prompt 契约。

## 就绪命令

```bash
# A 臂（对照）
AITESTER_PROFILE=logic EDIT_INTENT_ENABLE=true \
  .venv/bin/python experiments/run_main_batch.py \
  --task-count 50 --seed 42 --baselines aitester --max-pattern-repeat 2 --skip-stats

# B 臂（处理）
AITESTER_PROFILE=logic EDIT_INTENT_ENABLE=true LOCALIZED_EDIT_ENABLE=true \
  .venv/bin/python experiments/run_main_batch.py \
  --task-count 50 --seed 42 --baselines aitester --max-pattern-repeat 2 --skip-stats
```

## 执行记录（2026-10-08 跑批后追加，不改判定规则）

| 臂 | 批次工件 | repair_rate | patch_correct | patch_plausible | edit_localization | fl_constraint |
|----|----------|-------------|---------------|-----------------|-------------------|---------------|
| A（对照） | `benchmark_synthetic_20261008_133303.json` | 8/50 (16.0%) | 8/50 | 5/50 (10.0%) | 0 行（全 None，预期） | hit=18, not_evaluable=32 |
| B（处理） | `benchmark_synthetic_20261008_134156.json` | 8/50 (16.0%) | 8/50 | 4/50 (8.0%) | 17/18 约束行，localized_ratio=1.00，0 越界 | hit=18, not_evaluable=32 |

**逐任务 repair 完全一致**：A 成功 8 个、B 成功 8 个，交集 8、差异 0——没有任何任务因
加定位约束而改变修复结果。

**判定**：
- H1（主，repair 提升）：**不成立**——两臂 repair 逐任务完全相同。
- H2（机制，约束被遵循）：**表面成立但空洞**——localized_ratio=1.00、0 越界，但这是
  因为**函数级约束在单函数 synthetic 任务上恒成立**（FaultLocalizer 定位到"被测函数"
  = 覆盖整个被测代码，锚点必然落在候选内）。
- H3（机制，FL hit 上升）：**无差异**——两臂 fl_constraint 均 {hit:18, not_evaluable:32}。

**根因洞察（比数字更重要）**：函数级定位约束在单函数数据集上**无区分度**——候选函数
就是被测函数本身，约束"锚点落在候选函数内"退化为"锚点落在被测代码内"，等价于
edit_intent 通道本身，未新增约束力。这与 ADR-0028 预判（"整文件重写下约束门近乎恒 hit"）
同向，且更进一层：**即便走局部编辑通道，函数级约束仍空洞**。要获得真正约束力，须把
约束粒度从"函数级"升级为"行级"——用 FaultLocalizer 的 `line_start/line_end`（缺陷语句行）
而非函数定义行范围判定锚点落点（风险：行级定位 FL@1=35.8% 精度有限，须 A/B 复核）；
或在 QuixBugs（多函数真实文件）上验证函数级约束（那里函数级才有区分度）。

本结果为**诚实阴性记录**，不因方向不理想而筛选或改判。

## 行级约束升级 + QuixBugs 并行复跑（2026-10-08 追加）

首测发现"函数级约束空洞"后，把约束升级为**行级**（`validate_edit_localization` 主判定改用
FaultLocalizer 的 `line_start/line_end` ± 窗口 `LOCALIZED_EDIT_WINDOW`（默认 3），候选缺 line
信息回退函数级），并在 synthetic + QuixBugs 上并行复跑：

| 数据集 | 臂 | edit_localization | localized_ratio | repair_rate | FL@1 |
|--------|----|-------------------|-----------------|-------------|------|
| synthetic（n=50） | B2（行级） | 17 行 mode=line | 恒 1.00（0 越界） | 8/50 (16.0%) | 10/18 (55.6%) |
| QuixBugs（n=50） | A（对照） | 0 行（预期） | — | 0/50 (0.0%) | 11/37 (29.7%) |
| QuixBugs（n=50） | B（行级） | 37 行 mode=line | 36/37=1.00（1 越界） | 0/50 (0.0%) | 11/37 (29.7%) |

**结论（阴性，方向性）**：

1. **行级约束机制生效但区分度仍极低**：synthetic 上函数太小（±3 窗口覆盖整个函数）；
   QuixBugs 上仅 1/37 越界——根因是 FaultLocalizer 缺陷行定位不准（FL@1=29.7%），
   "缺陷行 ±3 窗口"仍覆盖锚点。行级约束的前提（精确缺陷行定位）尚不成立。

2. **QuixBugs repair=0 的真正根因不在局部化约束**：`patch_evidence_level` 分布
   sbfl=20 / none=29——29 个补丁被证据门（`PATCH_EVIDENCE_GATE_ENABLE` 默认 true）以
   "无确定性证据"拒绝写盘；而 20 个放行补丁 `patch_plausible=1` 但 gold `correct=0`
   （**plausible ≠ correct 过拟合**）。对照 synthetic：5 plausible → 8 correct。

3. **优化优先级重排**（R4"局部化约束"方向被证伪为当前非瓶颈）：
   ① 补丁正确性 / 过拟合（QuixBugs 20 plausible 但 0 correct——ADR-0024"生成侧主导"、
   PRepair"over-editing"的同构证据）；② 证据门在真实基准上的行为（29/50 被拒，需
   重新审视 sbfl 证据在 QuixBugs 上的可得性）；③ FaultLocalizer 行级定位精度（29.7%）。

## 【勘误】测量层修复：QuixBugs repair=0 是伪影（2026-10-08 归因后定案）

上述第 ②③ 条结论经归因后**部分作废**——"QuixBugs repair=0"是**测量层 bug**：

**归因链**：B 臂 20 个 plausible 补丁 → 9 个「弃权门未标记但 correct=0」盲区 → 用 QuixBugs
官方测试**直接检验 patch**（写回 `python_programs/xxx.py` 跑官方测试）→ **9/9 全 PASS**
（均为真实正确修复）→ 复现 `_compute_repair_rate` 捕获真实报错：
`ModuleNotFoundError: No module named 'node'`（pytest rc=2，收集阶段中断）。

**根因**：`experiments/_m1_metrics.py::_run_pytest_in_tmp` 的历史"单文件口径"只在 tmp 目录
写 `{module}.py` + `test_{module}.py`；而 QuixBugs 官方测试依赖辅助模块（`from node import Node`、
`from load_testdata import ...`）、包结构（`from python_programs.xxx import xxx`）与
`pytest.use_correct`（conftest）→ 上述 import 在 tmp 环境全部失败 → repair 被系统性判 0
（与 ADR-0021 同类测量伪影，且影响面更大）。synthetic 因 gold 测试是单文件口径而不受影响。

**修复**：新增 `_quixbugs_support_root()` + `_prepare_packaged_test_tree()`（镜像包目录树：
`python_programs/` 包 + `correct_python_programs/` 占位 + `conftest.py` + 从 `AITESTER_QUIXBUGS_DATA`
复制 `node.py`/`load_testdata.py`/`json_testcases/` + 测试 prelude 注入 `pytest.use_correct`）；
`_run_pytest_in_tmp` 检测 `python_programs` 走包分支，synthetic 单文件走历史分支（零行为变化）。

**修复后重算（同存量工件）**：

| 臂 | 原判 repair | 修复后 repair |
|----|-------------|---------------|
| QuixBugs A（对照） | 0/50 (0.0%) | **37/50 (74.0%)** |
| QuixBugs B（行级约束） | 0/50 (0.0%) | **36/50 (72.0%)** |

**连锁更正**：
1. 本文档上文"② 证据门 29/50 被拒 / ③ 定位精度"对 repair=0 的归因**不成立**——0 是测量伪影；
2. A/B（LOCALIZED 行级）真实差异 = 74% vs 72%（1 行，无显著差异）→ R4 局部化约束在
   QuixBugs 上**同样无增益**（但正确率水平 72–74% 远高于此前认知）；
3. **真实基准修复率首次测得 72–74%**（synthetic 16%、历史 BASELINE 修正口径 35.9%）——
   与"真实基准更难"的直觉相反，提示 synthetic 模板缺陷可能更刁钻，或 synthetic 侧仍有
   测量问题待查（后续批次跟进）。

**测试**：`tests/test_m1_packaged_tests.py`（7 项，锁定包结构分支与端到端链路）；
引用 `_m1_metrics` 的 6 个测试文件 84 passed 零回归。



