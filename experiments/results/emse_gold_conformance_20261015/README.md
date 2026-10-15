# 基准 gold 材料自洽性审计工件（2026-10-15 批次九）

> **性质**：EMSE 投稿的**测量有效性证据工件**（零 LLM 可复算）。
> **触发**：批次九对「gold 材料自身在其 gold 目标代码上通过」这一
> detection / repair / false_fix 度量族**隐含前提**做端到端审计（批次八已在
> ULT 侧发现官方 gold 参照问题，本批次推广到 synthetic + QuixBugs，并把
> ULT 归因做成独立脚本）。
> **脚本**：`experiments/emse_gold_conformance_audit.py`（零 LLM，只读数据集
> 材料 + 临时目录内 pytest；不改动基准）。

## 1. 口径

- **判据**：`metadata.test_cases`（gold 套件）在 `metadata.fixed`（gold 目标
  代码）上 30s 内 `rc == 0`；否则该任务的 gold 裁决前提不成立。
- **材料化**：复用 M1 判分链路 `experiments/_m1_metrics.py::_run_pytest_in_tmp`
  （与 `_compute_detection_rate` 同一执行口径：跨文件透传 `task_metadata`、
  QuixBugs 包结构镜像、辅助材料 fail-closed）。
- **集合**：synthetic n=87 × 3 种子（R-P0-2 主批次口径，`max_pattern_repeat=2`）
  + QuixBugs 50 程序。

## 2. 核心发现：synthetic 模板残留 import（O2 缺陷）

**症状**：主批次 synthetic 261 任务中 **25 个（9.6%）** 的 gold 套件在 gold
目标代码上**必然失败**（`ModuleNotFoundError`）⇒ 这些任务在 `detection_rate`
口径下**结构性不可检出**（与被测系统能力无关）。

**根因链**：
1. 模板 `import45_shadow_builtin`（`src/datasets/synthetic_dataset.py`
   `BUG_PATTERNS_LEVEL45`）的 gold 测试在**函数体内**写
   `import import45_shadow_builtin as m`（`test_no_builtin_shadow`）；
2. P1-4 的模块名中性化 `_neutralize_gold_imports()` 只有两条**行级**正则：
   `from X import ...` 与独占一行的 `import X`（`\s*$` 要求行尾）；
3. 函数体内形态是 `import X as m` —— 模块 token 后**不是行尾** ⇒ 两条正则
   均不匹配 ⇒ 模块名**未被重写**为中性名 `task_XXXX`；
4. 判分树中不存在名为 `import45_shadow_builtin` 的模块 ⇒ gold 套件恒
   `ModuleNotFoundError` ⇒ `_compute_detection_rate` 的「fixed 侧 rc==0」
   一段永不成立 ⇒ 该任务恒判 `0.0`（未检出）。

**为何既有测试漏检**：`tests/test_2026_10_05_v_batch.py::TestV5NeutralTaskIds`
原断言为 `f"from {mod} import" in gold or f"import {mod}" in gold` —— 函数体内
形态**满足**第二条子串（`import task_0007 as m` 存在）⇒ 断言通过。

## 3. 前后对照（冻结证据）

| 工件 | 状态 | synthetic gold 自洽 | 说明 |
|---|---|---|---|
| `../emse_gold_conformance_pre_fix_20261015/GOLD_CONFORMANCE.json` | **修复前（冻结）** | **236 pass / 25 fail** | 25 失败任务全部命中断面 import 判别式 |
| `GOLD_CONFORMANCE_PREFIX_FROZEN.json` | 修复前（探针口径副本） | 236 / 25 | 逐任务记录（含 seed 键） |
| `GOLD_CONFORMANCE.json` | **修复后** | **261 pass / 0 fail** | 第三条正则覆盖 `import X as Y` / `import X  # 注释` |
| `GOLD_CONFORMANCE_POSTFIX_COPY.json` | 迁移过程副本（非权威） | 261 / 0 | 历史拷贝，保留供审计 |

修复后单任务校验（canary 任务 `synthetic__task_0007`）：gold 套件在 gold fixed
上 `3 passed`；在 buggy 代码上 `2 failed, 1 passed` —— gold 裁决恢复为**有判别力**
的 fail-to-pass 形态。

## 4. 对已发表数值的影响（`IMPACT_RECOMPUTE.json`）

受影响 25 任务的 detection 分布（归档主批次三臂）：

| 臂 | 1.0（检出） | 0.0 | None |
|---|---|---|---|
| aitester | **0** | 23 | 2 |
| plain_llm | 0 | 25 | 0 |
| plain_llm_df | **19** | 6 | 0 |

**解释**：`plain_llm_df`（检出优先提示协议）的生成测试**不 import 该残留模块**，
故 gold 套件里的坏用例不影响其裁决 —— 它在这些任务上真实检出 19 例；
`aitester` 的生成测试依赖 `from task_XXXX import ...`，gold 坏用例使其 fixed 侧
恒红 ⇒ 全部记 0。**该缺陷方向性偏向压低 aitester。**

排除这 25 任务后的重算（McNemar 精确检验，零 LLM）：

| 对比 | 口径 | n | 不一致比 | δ | χ² | p |
|---|---|---|---|---|---|---|
| aitester vs plain_llm_df | 全量（已发表） | 240 | 12:80 | **−28.33pp** | 48.79 | 1.7e−13 |
| aitester vs plain_llm_df | **排除 25** | 217 | 12:63 | **−23.50pp** | 33.33 | 1.7e−09 |
| plain_llm_df vs plain_llm | 全量（已发表） | 261 | 113:0 | **+43.30pp** | 111.01 | 1.9e−34 |
| plain_llm_df vs plain_llm | **排除 25** | 236 | 94:0 | **+39.83pp** | 92.01 | 1.0e−28 |
| aitester vs plain_llm | 全量（已发表） | 240 | 37:3 | **+14.17pp** | 27.23 | 1.9e−08 |
| aitester vs plain_llm | **排除 25** | 217 | 37:3 | **+15.67pp** | 27.23 | 1.9e−08 |

**结论**：三项主结论（协议 +43pp / 编排净负 / 编排优于裸 LLM）**方向与显著性全部
不变**；但「编排净负」效应量在排除受损任务后由 −28.33pp 收窄至 −23.50pp
（受损任务贡献了 4.83pp 的表观劣势）。对外报告应改用保守口径或并列两值。

**为何不能只改代码了事**：归档批次工件是**冻结**的（任务材料逐字节参与复算），
修正生成器只影响未来批次；25 个任务的真实检出需**重跑测量**（本批次未授权
LLM 重跑，故不主张「修好后 aitester 会检出多少」）。

## 5. 判别式回归测试

`tests/test_2026_10_05_v_batch.py::TestV5NeutralTaskIds::test_no_pattern_name_survives_in_gold_imports`
按**行首 import token 全量扫描**（3 种子 × 87 任务），任何非中性 / 非合法辅助件的
模块名即失败。

判别力实证：临时停用第三条正则（模拟修复前代码）时，**新测试失败而原有两条测试
仍通过** —— 新测试确实覆盖了原测试的漏检面。

## 6. QuixBugs gold 材料可用性上限（第二项发现）

50 程序中：

| 类别 | 数量 | gold 自洽判定 |
|---|---|---|
| 无官方测试材料（9 个 `<prog>_test` 驱动程序的配套 program） | 9 | `material_missing` |
| 官方测试经 `load_testdata.load_json_testcases` 读 `json_testcases/<prog>.json` | 31 | **fail（`collection_error:missing_fixture_file`）** |
| 仅 import `node` 辅助件 | 6 | pass |
| 自足（含 `node` 任务本身） | 4 | 3 pass / 1 `no tests collected` |

**含义**：QuixBugs 侧 detection 的**可测上限 = 35 任务**（= M4 四臂实测 N=35，
逐位吻合）。上限成因是上游 `json_testcases/` 只覆盖部分程序（判分树按上游克隆
镜像，缺 json ⇒ 官方测试收集失败 ⇒ 记 None，不误报 0）。**这是材料约束，不是
缺陷**；但它解释了 M4 的功效天花板，并为「QuixBugs 本地 50 程序」的样本量声明
提供精确口径（对外应写「detection 可测 35/50」）。

## 7. 第三项基准（ULT）：独立归因诊断

ULT gold 的 71/71 失败归因见同族工件
`../emse_ult_gold_diagnosis_20261015/`（脚本 `experiments/emse_ult_gold_diagnosis.py`）：
**70/71 在官方契约下同样失败**（上游断言内容不一致 36 + 混合 28 + 非自足 3 +
接口不匹配 3），**1/71（`ult__fix_labels`）纯属项目物化缺陷**（缺官方
`code_import` 前置块 ⇒ `re` 未定义；官方契约下 5/5 通过）。⇒ 原「gold 参照作废
（上游不一致 71/71）」的 blanket 表述**过度概括**，应按上述拆分改写。

## 8. 复现

```bash
# 修复前（冻结证据已归档；此命令可在旧代码上重放）
AITESTER_QUIXBUGS_DATA=~/.cache/aitester/quixbugs \
  .venv/bin/python experiments/emse_gold_conformance_audit.py \
  --out experiments/results/emse_gold_conformance_pre_fix_20261015

# 修复后（当前树）
AITESTER_QUIXBUGS_DATA=~/.cache/aitester/quixbugs \
  .venv/bin/python experiments/emse_gold_conformance_audit.py

# 判别式回归
.venv/bin/python -m pytest tests/test_2026_10_05_v_batch.py -q
```

## 9. 披露纪律（写入 EMSE 稿件 limitations）

1. 主批次 synthetic 的 25/261 任务曾受 gold 材料缺陷影响；**排除后重算值**与
   已发表值并列给出（§4 表）；
2. QuixBugs detection 可测上限 35/50，原因为上游 `json_testcases` 覆盖缺口；
3. ULT gold 归因按 §7 拆分（禁止再用「71/71 上游不一致」的 blanket 表述）；
4. 本修复属**测量层修复**（恢复度量前提），不改变任何归档工件；受影响任务的
   真实检出需重跑测量，本轮未主张；
5. 与批次八「gold 参照须先验证 gold 在目标代码上通过」的建议同源 —— 本批次把
   该建议**自动化**为跨基准审计脚本，可复算。
