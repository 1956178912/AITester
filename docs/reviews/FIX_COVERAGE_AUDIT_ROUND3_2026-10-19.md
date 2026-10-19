# 修复覆盖率缺口审计·第三轮（2026-10-19，零 LLM）

> **性质**：Y2 轮遗留项的收口（死代码清理 + provenance 降级路径），并把审计视野
> 从"修复新增行"扩展到**全仓未覆盖行地图**——为后续批次提供排序依据。
> **花费**：真实 LLM **$0**。
> **结论**：清理 2 个死函数（−8 行）；补齐 A03 provenance 三条降级路径（3 例，
> 逐项变异验证）；首次产出全仓 637 行未覆盖行的分类地图。

## 1. 死代码清理

上一轮审计发现的两个无调用点函数已删除（`experiments/statistical_analysis.py`）：

| 函数 | 原位置 | 删除理由 |
|---|---|---|
| `_strip_seed_prefix` | 2290-2292 | 全仓（含 395 个测试文件）零调用点；A06 重构后由 `_split_seed_prefix` 取代 |
| `_rebuilt_task_fingerprints` | 2327-2333 | 同上；由 `_rebuilt_task_table` 取代 |

**验证**：`ast.parse` 语法通过、ruff 通过、统计相关 105 例全绿。
**收益**：消除"看似被使用实则死掉"的误导，并让覆盖分母减少 8 行（此前它们恒为
未覆盖，会虚高缺口数）。

## 2. A03 provenance 的三条降级路径（`run_benchmark.py`）

这三条路径共同保证"溯源不可得时如实记录、不中断整批跑测"。此前零执行。

| 路径 | 位置 | 行为 |
|---|---|---|
| marker 读取失败 | 3818-3820 | 记录 `error` 字段并返回，不抛异常 |
| marker 行格式不符 | 3824 | 跳过（无 `=` / key 非 `GIT_SHA`），继续解析 |
| git 调用异常 | 3862-3863 | `git_available=False`，回落 marker 作为来源 |

**为什么重要**：若退化为抛异常，一次权限异常或 git 缺失就能让整批实验在启动
阶段崩溃——而这正是复现容器（无 git）的**常态**。

**变异证据**（逐项单独注入，每次仅目标用例变红、其余 2 例全绿）：

| 变异 | 变红用例 |
|---|---|
| 读取失败不再捕获 | `test_marker_read_error_is_recorded_not_raised` |
| 格式不符不再跳过 | `test_marker_ignores_malformed_lines` |
| git 异常不再捕获 | `test_git_exception_degrades_to_marker` |

## 3. 全仓未覆盖行地图（首次）

`coverage.xml` 全量口径：**637 行未覆盖 / 83 个文件**（对应 96.57% 行覆盖，
17913/18550）。相比 Y 轮未覆盖的 652 行减少 15 行——其中 9 行是 Y2 轮补 `trace.py`
A20 三处守卫的连带覆盖，6 行来自本轮 provenance 测试。

### 3.1 Top 15

| 文件 | 未覆盖 | 总行 | 占比 |
|---|---|---|---|
| `src/graph/orchestration_search.py` | 74 | 471 | 15.7% |
| `src/specs/spec_ir_v2.py` | 36 | 787 | 4.6% |
| `src/specs/spec_smt.py` | 28 | 464 | 6.0% |
| `src/utils/helpers.py` | 26 | 361 | 7.2% |
| `src/tools/cross_file.py` | 21 | 299 | 7.0% |
| `src/agents/fl_spectral.py` | 20 | 184 | 10.9% |
| `src/datasets/dataset_loader.py` | 19 | 309 | 6.1% |
| `src/agents/executor_runtime.py` | 17 | 222 | 7.7% |
| `src/graph/expert_pool.py` | 17 | 187 | 9.1% |
| `src/tools/patch_applier.py` | 17 | 466 | 3.6% |
| `src/agents/runtime_probe.py` | 15 | 111 | 13.5% |
| `src/datasets/dataset_ult.py` | 15 | 123 | 12.2% |
| `src/measurement/mdo.py` | 15 | 147 | 10.2% |
| `src/agents/executor.py` | 13 | 127 | 10.2% |
| `src/datasets/dataset_realbugs.py` | 13 | 115 | 11.3% |

> `src/observability/trace.py` 已从榜上退出：Y2 轮补齐 A20 三级降级链后其未覆盖
> 行由 16 降至 7。

### 3.2 分类与处置建议

| 类别 | 代表 | 判断 | 建议 |
|---|---|---|---|
| **冻结/未启用功能** | `orchestration_search.py`（74 行，占未覆盖 11.3%） | 16 臂 bandit **未实跑**，ADR-0034 已冻结并列出解锁五条件 | 不补——补测等于为冻结功能维护测试，反而掩盖"未验证"状态 |
| **容错/防御分支** | `helpers.py`（JSON 数组的正则回退档）、`spec_ir_v2.py`（SMT 见证的保守回落）、`trace.py`（A20 其余守卫） | 各 docstring 明确定义"任一不满足即保守回落" | 选择性补：优先补**有明确契约文档**的回落路径（如 `_precondition_witness_binding` 的 4 条保守边界） |
| **多数据集适配层** | `dataset_loader` / `dataset_ult` / `dataset_realbugs`（合计 47 行） | 本地只有部分数据集，其余分支不可达 | 用 fixture 伪造数据集元数据可达——中等成本 |
| **平台/探测分支** | `executor_runtime` / `runtime_probe` | 跨平台探测失败路径 | 低优先（macOS 上不可达属正常） |

### 3.3 抽样核查记录

抽查三个高占比文件的未覆盖行，确认性质：

- `spec_ir_v2.py:963-980`：`_precondition_witness_binding` 的异常兜底与见证解析
  边界（主路径已覆盖）——属"保守边界"，有 docstring 契约；
- `helpers.py:658-668`：JSON 数组提取的**档 2**（正则取最内层）——测试只覆盖了
  档 1（括号匹配），档 2 在畸形 LLM 输出时才启用；
- `spec_ir_v2.py:929-931`：空行处理的 `continue`——纯防御。

## 4. 结论

1. 死代码清理与 provenance 补口完成，本轮**没有**发现新的 P1 级契约缺口；
   剩余 637 行以容错/防御/平台分支为主，边际价值低于前两轮。
2. **不建议**以"降低未覆盖行数"为目标继续补测：`orchestration_search` 的 74 行
   本就不该覆盖（冻结功能），强行补测会产生"测试存在但语义未验证"的假安全感。
3. 下轮若要继续，优先序建议：
   ① `helpers.py` 档 2 正则回退（LLM 输出容错是真实需求）；
   ② `spec_ir_v2` 的 SMT 见证 4 条保守边界（有明确契约）；
   ③ 数据集适配层（需先确认本地数据集可用性）。

## 附录：复跑

```bash
make test-cov
python scripts/tools/audit_fix_coverage.py                    # 修复新增行口径
python scripts/tools/audit_fix_coverage.py \
    --base <更早的基线> --pathspec experiments/               # experiments 口径
```
