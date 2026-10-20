# AC 轮（2026-10-20）：McNemar p 的 `1−cdf` 浮点下溢修复 + E7 工具链干跑 + AB-17 接线核查

最后更新：2026-10-20
范围：Z→AB 收口批（提交 `e934fc55` / `31445192`）后的独立复算审计。零 LLM 调用、$0 配额。
性质：**fix-the-fixes**——对第四轮评审（Z 轮）20 项修复与 AB-1~17 轮的新代码做自查，
以"独立复算"为主方法（前几轮该方法抓到过真实漂移）。

## 0. 一句话结论

Z 轮修复批整体质量高（BH / 配对 / MDO / rlimit / venv marker / swebench 接口等逐项审计通过），
但独立复算抓到一处**统计层数值缺陷（AC-1）**：`mcnemar_test` 的 `1.0 - chi2.cdf(x, df=1)`
在卡方尾部浮点下溢为精确 0.0，使 Z 轮勘误表引用的精确值（p=5.890715e-26 / q=1.767215e-25）
**无法从生产代码路径复算**。已修复（`chi2.sf`）+ 6 例回归锁（变异验证）+ 日期化勘误；
E7 工具链干跑与 AB-17 七读点接线核查均通过，无新缺陷。

## 1. 审计方法与覆盖

| 审计面 | 方法 | 结果 |
|---|---|---|
| F01 BH q 重写 | 2 万次模糊对拍 vs 独立暴力参考实现（含并列/0/1/nan/多 alpha） | 0 不一致 |
| F02 配对分子/分母 | 读码 + 与 `_pair_by_task` 同源性核对 | 同源正确 |
| F04 rlimit 0=禁用 | diff 审查（逐项 `> 0` 守卫） | 正确 |
| F07 init_db try/finally | diff 审查 | 正确 |
| F09 zai temperature | diff 审查 | 正确 |
| F10 共享 venv marker | 读码（锁序 env→venv、锁内复检、fail-closed） | 正确 |
| F11 官方 swebench 接口 | 读码（命名参数/预测 schema/递归解析/降级） | 正确 |
| F12/F13 MDO 断言判别与探针校验 | 读码（conftest 注入/schema 校验/分母排除） | 正确 |
| F14 负 rc 守卫 | diff 审查 + 全仓 `1−cdf` 模式普查 | 正确；**普查顺带抓到 AC-1** |
| nodes.py 三节点拆分 | 入口层覆盖核查（20+ 既有文件经生产节点） | 无接线盲区 |
| AB-17 价目表七读点 | 消费方 import 普查 | 七处全部接线共享助手 |
| E7 工具链 | 干跑（validate ×3 路径 + 越界 fail-closed + 未填拒合并 + κ/bootstrap） | 全通过 |
| 主批关键数字 | 独立复算脚本（只读原始 JSON + scipy，不 import 项目统计代码） | **抓到 AC-1**；F02/F20 复算值逐位吻合 |

## 2. AC-1：缺陷、根因与修复

### 2.1 现象

`experiments/statistical_analysis.mcnemar_test` 旧实现：

```python
p_value = float(1.0 - stats.chi2.cdf(chi2, df=1))
```

float64 相对 1 的机器精度约 2.2e-16 ⇒ `1.0 - cdf` 在 p ≲ 6e-17（χ² ≳ 71）时
恒等于 1.0 → **p 静默变为精确 0.0**。主批 plain_llm_df vs plain_llm（χ²=111.00885）
实测旧路径 p=0.0、BH q=0.0；精确值 p=5.890715e-26 / q=1.767215e-25
（`erfc(√(χ²/2))`、`chi2.sf`、独立复算脚本三方逐位一致）。

### 2.2 为什么此前没被抓到

Z 轮回归锁 `tests/test_review_20261019_stats.py` 确实锁定了精确值
（`_EXPECTED_P = (5.890715e-26, ...)`），但其 `_mcnemar_from_flags` 是**测试内的
erfc 助手**——生产 `mcnemar_test` 从未在主批数据上被执行。锁锁住了助手的正确性，
没锁住生产路径会返回什么（"逻辑有测试、接线无测试"同型盲区，见
`docs/MEASUREMENT_INTEGRITY.md` §21）。

### 2.3 修复与回归锁

- 修复：`p_value = float(stats.chi2.sf(chi2, df=1))`（生存函数，尾部数值稳定；
  docstring 同步记录下溢阈值与实测值）。
- 回归锁 `tests/test_ac_round_mcnemar_tail.py`（6 例）：
  1. 生产路径主批三比较 p/q 真值（`abs=0.0` 纯相对比较，闭合复算链）；
  2. 生产 χ² 与 pooled 报告主表逐位一致（111.01 / 48.79 / 27.23）；
  3. 合成大 χ²（b/c=1000/0，χ²≈998）p > 0 且 < 1e-100；
  4. 下溢阈值边界（χ²≈54 与 ≈998 两档）与 erfc 精确式一致；
  5. 中等 χ²（27.225）sf 与旧 1−cdf 在 1e-12 相对误差内一致（既有可复算值不变）；
  6. 既有边界语义（全一致 → (0.0, 1.0)；n<2 → (nan, nan)）保持。
- 变异验证：回退 `1−cdf` → 3 例转红（用例 1/3/4）；还原后 6 例全绿。

### 2.4 测试自身的陷阱（方法学产出）

第一版生产真值用 `pytest.approx(expected, rel=1e-5)`，变异验证时**不转红**——
`pytest.approx` 默认 `abs=1e-12`，让"下溢的 0.0"冒充 1e-25 量级真值通过。
修正为 `abs=0.0` 后变异即红。判据入库 `MEASUREMENT_INTEGRITY.md` §21：
**小量级断言必须纯相对比较**。

### 2.5 影响面（实测）

- χ²≤48.79 的两行 detection 比较与全部 repair 比较不受影响
  （1−cdf 与 sf 在 p≥1e-14 区间相对误差 <1e-12）；
- canonical `statistical_report.md` 的 passed 表 χ²=123.1419 行同款下溢
  （p 0.0000 → 精确 ≈1.4e-28），因渲染格式 `{:.4f}`，报告显示与结论不变；
- 显著性结论（主批三项均 ***）不变；拒绝集合不变；
- `experiments/results/main_batch/statistical_report_3seed_pooled.md` 追加
  2026-10-20 日期化勘误节（缺陷/修复/影响面），`SHA256SUMS` 同步刷新
  （2040 项校验通过，仅该文件一行变化）；
- p 值量级的**显示精度**（`{:.4f}` 把 1e-28 印成 0.0000）登记为后续轮次候选，
  不影响任何判定。

## 3. E7 工具链干跑（零 LLM）

| 检查 | 命令/输入 | 结果 |
|---|---|---|
| 三路径空白表校验 | `validate --sheet e7_entry_raterA_n{8,41,72}.csv --worksheet ... --allow-incomplete` | 8/41/72 行全部就绪 |
| 越界量表 fail-closed | 合成 `valid`/`invalid`（非七档词）填表后 `merge` | 拒绝并逐行点名 |
| 未填拒合并 | 部分填表后 `merge` | 拒绝（"第 N 行 judgment 未填"） |
| κ/bootstrap 全链 | 合成双人完整填表 `merge --output-dir /tmp/e7_dry` | κ=0.641、CI [0.167, 1.0]、混淆矩阵、分歧行 2 行正常产出 |

干跑数据全部在 `/tmp`，未触碰任何入库工件。

## 4. AB-17 七读点接线核查

七个价目表读点全部经 `src/budget/pricing.py` 共享助手接线：
`pricing`（缓存包装）、`spec_examples_generator`、`emse_stats_report`、
`emse_stats_extensions`、`statistical_analysis`、`analyze_t1_b2_main_batch`、
`run_b8_injection`——无"声明未消费"缺口（AB-17 收口声明的七处与 import 普查一致）。

## 5. 基线

- collected **10294** = passed **10289** + skipped 5 + failed 0（正常环境登记口径；
  本机沙箱宿主两跑实测：不带 `--cov-branch` 10275 passed / 19 skipped / 0 failed（814.76s）、
  带 `--cov-branch` 10273 passed / 19 skipped / 2 failed（951.60s）——2 例失败均为
  `test_artifact_doc_consistency_gate.py` 端到端锁，根因是跑批中途读到上一轮非分支口径的
  coverage.xml（分支读作 0.00%），属跑批交叠的状态假象；盘上 coverage.xml 更新为分支口径后
  该门单独复跑通过，收口确认跑（不带 --cov）全绿）；
- `experiments/` 不在 `--cov=src` 口径内；AC 轮 `coverage.xml`（分支口径）实测
  18440/18963 行 = 97.2420%（两位小数 97.24）、6652/7090 弧 = 93.8223%（两位小数 93.82），
  与 AB-17 登记的 18439/6653 各差 1，落在 AB-11 已登记的 `process_utils.py` 竞态分支
  ±2 抖动域（同值/差值均不作佐证，佐证是改动面清单）；
- ruff 882 → 883 文件零错；mypy 134 源文件 0 错；全部门禁绿
  （双语文档、链接 600 条、基线数字、工件对账、零断言、env-budget、
  状态契约、env-snapshot、JSON 契约站点、工具版本、工件入库 185/185、
  覆盖率棘轮行 97.24 ≥ 96.40 / 分支 93.82 ≥ 92.50 均不写回）。

## 6. 登记不修 / 后续候选

1. p 值显示精度（`{:.4f}` 把 1e-28 印成 0.0000）——不影响判定，留待后续轮次；
2. `emse_testlevel_detection.py` 的 `p_normal_approx` 同用 `1 - _normal_cdf(z)`，
   但该字段 `round(..., 4)` 显示且主口径是精确 DP 枚举 ⇒ 同模式、非缺陷，登记不修；
3. E7 三路径人工裁决仍待用户选定路径（n=8/41/72 备料与工具链均已就绪）。
