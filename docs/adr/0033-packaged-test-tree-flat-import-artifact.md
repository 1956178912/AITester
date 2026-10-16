# ADR-0033: 测量伪影第四起——判分树包结构 vs 平铺 import（detection 构造性恒 0）

- **日期**：2026-10-10（伪影定性 + 修复）；**2026-10-15 补登记为 ADR**（EMSE 批次：
  此前仅记录于 `docs/preregistration.md` §"第四起测量伪影修正与 E4 重结算"，
  未进入 ADR 决策账本，导致"伪影治理"叙事在 ADR 索引中缺一环）
- **状态**：已采纳（修复已落地并锁回归）
- **关联模块**：`experiments/_m1_metrics.py`（`_prepare_packaged_test_tree`）、
  `src/datasets/synthetic_dataset.py`（物化布局）、`experiments/run_benchmark.py`
  （生产执行沙箱的模块平铺写盘）
- **关联 ADR**：ADR-0021（第一起：patch 字段围栏残留）、ADR-0029（第二/三起：
  包结构 import 与跨文件任务未物化）、ADR-0027（修正口径重估）

## 背景

同族缺陷第四次出现：**意图口径 ≠ 执行口径**，且本次的后果比前三次更严重——
它使**主指标 `detection_rate` 在整批任务上构造性恒为 0**（不是偏低，是结构性不可测）。

机制（两个布局不一致）：

1. **判分树布局**：M1 判分树由 `_prepare_packaged_test_tree` 构造，只提供
   QuixBugs 式包结构 `python_programs/{module}.py`；
2. **生产执行沙箱布局**：被测模块名取 `task_id` 末段，生成侧沙箱把模块
   **平铺**写成 `{module}.py`。因此 Generator 写出的**扁平 import**
   （如 `from bitcount import bitcount`）在它自己的生成环境里是**正确**的；
3. **分叉点**：同一份生成测试被送进判分树执行时，扁平 import 一律
   `ModuleNotFoundError` → pytest `rc=2`（收集中断）→ 三段判定第 3 条
   （"两侧输出均无收集错误"）不成立 → `detection_rate = 0.0`。

**零 LLM 验证（决定性证据）**：12 任务子集 9 个缺陷程序，修复前 **9/9 在
buggy 与 fixed 两侧均 rc=2**；同一批工件仅改判分树布局 → F2P 检出
**0/7 → 6/7**。

**E4 重结算（单变量：同协议、同 cache namespace 复用原响应）**：

| 臂 | detection（41 缺陷程序口径） | token/task |
|---|---|---|
| `aitester` | **17/37 = 45.9%**（修正前 0/41 = 0.0%） | 16,038 |
| `plain_llm_df` | **31/37 = 83.8%** | **1,905** |

配对 McNemar（修正前 vs 修正后，aitester）：不一致对 17、χ²=15.059、
**p=1.042e-04**；2×2：n10=17、n01=0（单向翻转，无反向证据）。
配对 McNemar（两臂）：不一致对 14、χ²=12.071、**p=0.0005**。

## 决策

1. **双布局物化**：判分树 tmpdir 根同时写一份 `{module}.py`，与包结构
   `python_programs/{module}.py` 并存——使扁平与包两种 import 均在判分树内可解析；
2. **三段判定逐字未改、口径未放松**：恒失败测试在新布局下同样得
   `detection=0.0`（已加回归测试锁定），修复只消除"收集错误"这一
   非缺陷因素；
3. **修复不得只改判分树而不同步生产侧**：物化布局的权威定义收敛到
   `src/datasets/synthetic_dataset.py`，判分树与执行沙箱从同一布局
   约定派生（同 ADR-0021 `normalize_patch_text()` 的"单一权威"纪律）；
4. **本起伪影进入口径矩阵**：任何跨批次 detection 数字的引用必须标注
   是否含本修复（修复前批次 detection 为下界，不得与修复后批次混池）。

## 后果

**正面**：

- 主指标从"构造性恒 0"恢复为可测，且**修正后结论方向未变**——
  aitester 45.9% 仍显著低于 plain_llm_df 83.8%（p=0.0005），
  即"编排净负贡献"不依赖本伪影；
- 第四次印证同一治理模式：**凡"分叉的判分/执行路径"必产伪影**，
  该模式已成为本项目的显式检查项（见 `docs/design/repair_caliber_matrix.md`
  与 ADR-0029 的 fail-closed 纪律）。

**代价与残余风险**：

- 双布局物化使判分树内同名模块出现两份（包结构与扁平），
  **不同 import 风格可能解析到不同文件**——当前两者内容同源，
  该风险未在任何批次上触发，但属结构性隐患（登记为已知局限）；
- 本 ADR 为**补登记**：修复与验证发生于 2026-10-10，
  ADR 落盘于 2026-10-15，时间序证据以 `docs/preregistration.md`
  该节与批次工件为准。

## 已知局限与演进方向

1. 双布局一致性守卫（判分树内 `{module}.py` 与 `python_programs/{module}.py`
   内容等价断言）——当前靠同源物化约定，未加显式断言；
2. 判分树布局与生产沙箱布局的**单一布局源**重构（现为两处约定同步），
   与 ADR-0016 §5 的 graph→experiments 反向依赖收敛同批处理；
3. 修复前历史批次的 detection 值须在下游文档一律标注"修复前下界"
   （本 ADR 为标签权威之一）。
