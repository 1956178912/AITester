# ADR-0029: 测量伪影连环——包结构 import + 跨文件任务未物化（R16/R27/R28 修复与治理）

- **日期**：2026-10-08
- **状态**：已采纳（测量层修复 + fail-closed + M-suite + 口径矩阵纪律）
- **关联模块**：`experiments/_m1_metrics.py`、`experiments/repair_replay.py`、
  `experiments/corrected_metrics.py`、`src/tools/detection_gates.py`、
  `src/datasets/synthetic_dataset.py`、`docs/design/repair_caliber_matrix.md`
- **关联 ADR**：ADR-0021（围栏残留伪影，第一起）、ADR-0027（修正口径重估）

## 背景

R2 系统性评审（`REVIEW_2026-10-08_R2.md`）独立发现并量化了**第二、第三起测量伪影**。
至此测量层已三度成为"假结论"来源，共同形态均为"**意图口径 ≠ 执行口径**"分叉：

| 起 | 伪影 | 状态 | 影响 |
|----|------|------|------|
| ① | patch 字段围栏残留（```` ```python ```` 前缀未清理） | 已修（ADR-0021） | repair 全线 0 |
| ② | `_run_pytest_in_tmp` 单文件口径 vs QuixBugs 包结构 import | 已修（本次） | QuixBugs repair 系统性 0 |
| ③ | 跨文件任务 `module_a/b/c` 未物化 | 已修（本次，新发现） | 六批次跨文件行 repair 系统性 0 |

### 第二起（包结构 import）

QuixBugs 官方测试依赖辅助模块（`from node import Node`）、包结构
（`from python_programs.<module> import <name>`）与 `pytest.use_correct`；历史判分
只在 tmp 写 `{module}.py` + `test_{module}.py` → 上述 import 全部 ModuleNotFoundError
→ pytest 收集错误（rc=2）→ **9 个通过官方测试的正确补丁被误判 repair=0**。修复前
QuixBugs A/B 两臂 repair 均 0/50；修复后 A=37/50（可测 37/41）、B=36/50（36/41）。

### 第三起（跨文件任务未物化）

合成跨文件任务（Level 3 / 3.5）的 gold test_cases 直接 `import module_a/module_b/
module_c`（与 pattern 名无关，模块名中性化不重写）。历史单文件判分口径只物化
`{task_id末段}.py`，伴生模块缺失 → 收集错误 rc=2 → **六批次（R4-A、E2×2、R-P0-2×3）
跨文件行 repair 系统性 0、false_fix 被抬升（R4-A 6/8 行 =1.0）、detection 偏低**；
连带污染"修正口径"数字（ADR-0027 的 35.9%/48.1% 仍含系统性零行）。

## 决策

1. **跨文件任务判分物化**（`_prepare_cross_file_test_tree`）：
   - 判分时按 metadata 物化完整伴生模块树——模块名取
     `module_a_name/module_b_name/module_c_name`（缺省兜底），**被测目标模块**
     （`target_module` 指向者）内容 = 传入 `target_code`（buggy/patched/fixed 三态
     统一规则），其余伴生模块取 `module_*_code` 缺陷原版（与
     `run_benchmark._write_cross_file_modules` 同口径）；
   - 顶层模块直接落 `{name}.py`（gold 测试为顶层 import，无需包 `__init__.py`）；
     PYTHONPATH 覆盖 tmpdir。
2. **分派显式化**（`_run_pytest_in_tmp(..., task_metadata=...)`）：
   - 四个判分入口（`_compute_detection_rate/_compute_repair_rate/
     _compute_regression_rate/_compute_test_error_rate`）把任务上下文透传执行器；
   - 执行器优先消费显式信号：`is_cross_file=True` → 跨文件物化；
     `source=="quixbugs"`（显式）→ 包结构物化；**子串 `"python_programs" in
     test_code` 仅在 metadata 缺省时作 QuixBugs 兼容回退**（`detection_gates.py:85`
     委托调用不传 metadata → 行为逐位不变）。
   - 消除"含字面 `python_programs` 的非包测试被误分派"的隐患。
3. **fail-closed（R16）**：材料缺失不再静默记 0——
   - 需要 QuixBugs 辅助模块（node/load_testdata）而 `AITESTER_QUIXBUGS_DATA` 缺失
     或辅助文件缺失 → **记 None + logger.warning**（语义变更：不误报→不漏报，
     "没跑起来"与"没修好"不再混淆）；
   - pytest `rc==5`（no tests collected）并入执行错误判定；`_compute_repair_rate`
     对 rc==5 记 None。
   - **rc==2 与 rc==5 口径区分**：rc==5（no tests collected）在 repair 侧记
     **None**（fail-closed，"没跑起来"不落 0）；rc==2（收集/编译中断，含包结构
     与伴生模块缺失）在 repair 侧**保留 0.0**（补丁使目标模块不可导入 = 修复
     失败，属有意口径）；detection / test_error_rate 侧 rc>=2 一律按执行错误处理
     （0.0 / 1.0）。两条诊断路径分开记录：rc==2 先核对 dispatch 与模块树；
     rc==5 先核对用例收集规则。
4. **空补丁语义对齐（R28）**：`_compute_repair_rate` 对空补丁早退 `return 0.0`
   （对齐 docstring；消除"缺陷原码恰好过 gold → 误判 1.0"的边界假阳性）。
5. **M-suite**：新增 `tests/test_m1_cross_file_metric.py`、
   `tests/test_m1_dispatch_heuristic.py`、`tests/test_m1_packaged_missing_support.py`，
   锁定跨文件物化、显式分派、fail-closed 三条路径（含先红后绿过程注释）。
6. **口径矩阵纪律**：新增 `docs/design/repair_caliber_matrix.md`——所有对外引用的
   repair 数字必须注明口径（分子/分母/oracle/数据集/臂/种子/开关/工件/可复算命令）；
   禁止 all-task 与 M1 可测口径混用；禁止引用未修正的跨文件零行数字。
7. **受影响数字处置**：以 R27 修复后重放为准（`corrected_report_v2.md`、
   `replay_r4_ab_arm_a_v2.md`）——R-P0-2 35.86%→**39.31%**、E1/E2 48.11%→**54.72%**、
   R4-A 可重放 44.4%→**55.6%**；QuixBugs 37/41 & 36/41 **逐位不变**。历史受影响
   数字在对外材料中一律标注为"修正前下界"或直接替换为 v2。

## 已知局限

- **畸形 metadata 退化（已知边界，待立项）**：跨文件物化依赖 `module_a/b/c_name`、
  `module_*_code` 与 `target_module` 齐备且自洽；当 metadata 畸形（缺模块名、
  字段冲突、或 `is_cross_file` 标记与模块树不一致）时，物化可能产出不完整模块树
  → 收集错误 rc==2 → repair 侧记 **0.0**（detection 0.0）——**该行会被记为
  "修复失败"而非"不可测"**（本边界尚未实现物化前置 fail-closed 校验；列入待立项）。
  当前数据集生成器不产出该形态（8/8 探针全过）；新增/改写任务 metadata 时须保证
  字段自洽（与 `run_benchmark._write_cross_file_modules` 同源校验），并在结果
  复盘时区分"材料畸形"与"修复失败"。

## 后果

- **正面**：合成集跨文件行 repair 由系统性 0 恢复可测；修正口径数字自洽；测量层
  假结论风险归零（M-suite 失效注入）；QuixBugs 数字经独立重放逐位确认（37/41/36/41）。
- **代价**：`_run_pytest_in_tmp` 签名新增 `task_metadata`（keyword-only 语义，向后兼容）；
  跨文件判分增加 tmp 目录写盘开销；fail-closed 使个别批次的可测分母缩小（诚实降级，
  非缺陷）。
- **政策**：新增基准/多模块任务一律走显式 dispatch 契约（metadata 来源标记），
  不得依赖测试文本子串；测量层任何"收集 0 测试 / 材料缺失"场景一律 fail-closed
  （None + warning），不得静默记 0。

## 关联

- 口径矩阵：`docs/design/repair_caliber_matrix.md`；
- 预注册执行记录：`docs/preregistration.md`（R4 / QuixBugs 单臂运行登记 + E4 待执行）；
- 工件：`experiments/results/r4_batches/`（SHA256SUMS + README）与
  `experiments/results/main_batch/corrected_report_v2.md`；
- 上游先例：ADR-0021（第一起）、ADR-0027（修正重估）、ADR-0016（编排净负）。
