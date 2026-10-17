# O-2 oracle-enabled 二臂验证批（真 LLM，验证性测量，2026-10-17）

> 运行 20261017T163420Z；切点 worktree `/Users/wangchenyu/Workspace/AITester-o2-oracle-70b5436`，HEAD=`70b5436a9b8786b18b5bd80a83ce8a4741b2bfce`；
> 本报告数字全部由脚本从两臂批次 JSON 直出（不手写）；协议见 §1。

> ## ⚠️ 本轮**对照臂有效性缺陷**（如实披露，Lead 决策中）
> - 实测两臂 `provenance.env_snapshot.SPEC_ORACLE_EXEC_ENABLE` **均为 `'true'`**：`AITESTER_PROFILE=logic`
>   的档位预设（`config.py:61/80`，`setdefault` 注入）**默认开启** `SPEC_ORACLE_EXEC_ENABLE=true`，
>   因此 control 臂仅"unset"该环境变量并不能关闭 oracle——**两臂实际都是 oracle-enabled**，不构成有效 A/B 对照。
> - 零 LLM 最小复现：`env -u SPEC_ORACLE_EXEC_ENABLE AITESTER_PROFILE=logic python -c "import os,config;print(os.getenv('SPEC_ORACLE_EXEC_ENABLE'))"` → `'true'`。
> - 本轮因此只构成**"oracle-enabled 真实链路 ×2 同配置重复"**：可验证注入/verdict 字段与 O-1 崩溃安全（本轮
>   `oracle_suite_verdict` = unavailable 15 / silent 5，**无 fp** = O-1 目标达成迹象），但**不能**给出 oracle 对 LLM-suite
>   检出的影响（A/B 对照无效）。两臂同配置下的差异（§4 的 2/20 任务）+ 检测率差 1 任务，可作"temp=0 重跑噪声"的
>   小样本数据点（约 5–7pp 量级，与 Q5 跨批波动同向）。
> - 修复状态：跑批脚本已修复（control 臂改为**显式** `SPEC_ORACLE_EXEC_ENABLE=false`，并修正 bash 3.2 不兼容的
>   `${var^^}` 收尾 bug）——是否在**同一切点**补跑 control-only（20 任务，约 35min/< $0.06，会使总墙钟超 60min 目标）
>   由 Lead 裁决；详见交接消息。

## 1. 协议（固定，验证性非 confirmatory）

- 臂 A（control）：`--baselines plain_llm_df_spec`，oracle 关闭；臂 B（oracle）：同一 baseline + `SPEC_ORACLE_EXEC_ENABLE=true`；均不设 `DETECTION_SPEC_MODE`。
- `--dataset quixbugs --task-limit 20 --seed 42`；`AITESTER_PROFILE=logic TEMPERATURE=0.0 LLM_THINKING_MODE=disabled BENCHMARK_PARALLELISM=4`。
- `AITESTER_BATCH_MAX_CALLS=100 COST_BUDGET_ENABLE=true COST_BUDGET_USD=1 AITESTER_LLM_CACHE=0`；两臂独立 `AITESTER_CACHE_NAMESPACE`。
- 零 LLM 材料可行性探测：arm_can_inject_oracle=`True`；no_anchor_verdict=`not_attempted`；spec_anchor_injected=`True`。
- SPEC_ANCHOR_TABLE sha256=`3e90b2ad5ed365ad5ee989c73c92b84956a83c0fa8cb51368d288ae3ea53bf22`（仅 arm_baseline=plain_llm_df_spec 时涉及）。
- 调度：两臂**并发**执行（各 P4、独立 namespace/log/trace；主指标在任务阶段采集，次指标含并发 CPU 噪声）。

**验证性协议修正（Lead 批准 2026-10-17，方案 a）**：任务书默认 baseline `plain_llm_df` 修正为 `plain_llm_df_spec`。
原因：N-3 oracle 材料优先级 = `spec_ir` → `test_plan.logic_analysis` → `spec_anchor.logic_analysis / human_spec`；
`plain_llm_df` 无 planner（无 `test_plan`）且不加载锚表（无 `spec_anchor`）→ 材料为空 → `SPEC_ORACLE_EXEC_ENABLE=true`
只会记 `not_attempted`，无法验证 oracle 注入；`plain_llm_df_spec` 携带 `spec_anchor.logic_analysis`（随库 `SPEC_ANCHOR_TABLE`）
为可编译锚材料 → 才能真实验证 oracle-enabled 通道。**该修正属验证性协议修正，不改变任何判定规则/判分口径。**

## 2. 两臂结果

| 项 | A（control） | B（oracle） |
|---|---|---|
| baseline / namespace | `plain_llm_df_spec` / `emse_oracle_enabled_validation_20261017_control` | `plain_llm_df_spec` / `emse_oracle_enabled_validation_20261017_oracle` |
| 批次工件 sha256 | `e7c10524d1f29769…` | `57533e651c999da3…` |
| 行数 | 20 | 20 |
| 墙钟(s) | **2102.4s**（watchdog 实测，日志 `[watchdog] rc=0 wall=…`） | **2319.8s**（watchdog 实测） |
| tokens（in/out/total） | 21452/30954/52406 | 24482/36498/60980 |
| LLM calls / cache hits | 24/0 | 27/0 |
| 成本（标准价上界） | $0.0436 | $0.0511 |
| LLM-suite detection | 80.00% | 78.57% |

## 3. oracle 注入与独立判读分布

| 字段分布 | A（control） | B（oracle） |
|---|---|---|
| `spec_oracle_injected` | `{"False": 4, "True": 16}` | `{"False": 4, "True": 16}` |
| `spec_oracle_verdict` | `{"compiled_empty": 4, "injected": 16}` | `{"compiled_empty": 4, "injected": 16}` |
| `oracle_suite_verdict` | `{"unavailable": 15, "silent": 5}` | `{"unavailable": 15, "silent": 5}` |

- **实测解读（注意：两臂配置相同，见顶部 banner）**：
  - 注入面：`injected=16/20`、`compiled_empty=4/20`（4 行无可用/不可编译锚材料——QuixBugs `_test` 驱动任务等），两臂分布一致（同配置）；
  - 独立判读：`oracle_suite_verdict` = **unavailable 15 / silent 5**，**correct=0 / fp=0 / misguided=0**——
    O-1 加固后崩溃全部落入 unavailable（**不再误记为 fp**，与 O-1 目标一致）；但本 20 任务子集上 oracle 断言无区分信号
    （可能原因：被绑定输入仍触发前件外崩溃/超时 → unavailable；或断言在 buggy/fixed 两侧皆过 → silent）。
  - 因对照无效，以上只描述 oracle-enabled 链路行为，**不作"oracle 不损伤检出"结论**。

## 4. LLM-suite 一致性（oracle 不改变 LLM 检出）

- 两臂共同任务：20；逐任务 `detection_rate`/`llm_suite_detection_rate` 不一致：**2**；
- only_in_control=[]；only_in_oracle=[]。
- **解读**：两臂实际同配置（见顶部 banner），故这 2 处不一致 + 检测率 1 任务差 **不是处理效应**，而是 temp=0 下
  LLM/执行的非确定性重跑噪声（小样本描述性数据点，非本批目的）。

| task | control | oracle |
|---|---|---|
| `quixbugs__gcd` | 1.0 | 0.0 |
| `quixbugs__knapsack` | 0.0 | None |

## 5. provenance / env_snapshot / 完整性

| 项 | A（control） | B（oracle） |
|---|---|---|
| git_sha / dirty | `70b5436a9b8786b18b5bd80a83ce8a4741b2bfce` / False | `70b5436a9b8786b18b5bd80a83ce8a4741b2bfce` / False |
| fingerprint pinned / returned | True / deepseek-flash | True / deepseek-flash |
| env_snapshot.SPEC_ORACLE_EXEC_ENABLE | `true` | `true` |
| env_snapshot.DETECTION_SPEC_MODE | `None` | `None` |
| 行字段完整率 | `{"spec_oracle_injected": "20/20", "spec_oracle_verdict": "20/20", "oracle_suite_verdict": "20/20", "llm_suite_detection_rate": "20/20", "detection_rate": "20/20"}` | `{"spec_oracle_injected": "20/20", "spec_oracle_verdict": "20/20", "oracle_suite_verdict": "20/20", "llm_suite_detection_rate": "20/20", "detection_rate": "20/20"}` |

**核验 issues（阻断）**：
- control: control 臂 env_snapshot.SPEC_ORACLE_EXEC_ENABLE='true'，期望未设

## 6. 成本 / 墙钟 / 异常与局限

- 两臂成本合计（标准价上界）≈ $0.0947；预算 ≤$0.2。
- 两臂并发 P4；墙钟以各臂日志 START/END 为准；验证性测量（非 confirmatory），小样本 20 任务不作显著性结论。
- 局限：单模型/单数据集/单 seed；并发噪声影响次指标；oracle-suite 分类为机制侧描述性信号，不替代 LLM-suite detection 主判定。
- **执行备注（透明披露）**：两臂 LLM 执行均 exit=0、批次 JSON 完整（control 2102.4s / oracle 2319.8s，watchdog 实测）；
  跑批脚本在**收尾收集阶段**触发 bash 3.2 不兼容缺陷（`${var^^}` bad substitution），导致 oracle 臂收集/README/SHA
  未由脚本自动完成。本报告的 oracle meta/comparison/README/SHA 由**已完成的两臂批次 JSON 零 LLM 补算**恢复
  （未重跑任何 LLM 臂、未改任何测量数字）；该脚本 bug 已定位并修复（同时修复 control 显式关 oracle）。

## 7. 复现

```bash
bash experiments/run_oracle_validation_batch.sh \
  --root <clean-worktree> --require-clean-root --arm-baseline plain_llm_df_spec
# 判定/核验（零 LLM 复算）：读 arm_*.meta.json + ARM_COMPARISON.json
```

## 8. 文件

| 文件 | 说明 |
|---|---|
| `log_control.log` / `log_oracle.log` | 两臂完整日志（命令/env/开始结束/git 状态） |
| `benchmark_quixbugs_*.json` | 两臂批次工件 |
| `arm_control.meta.json` / `arm_oracle.meta.json` | 每臂结构化元数据（token/成本/字段/逐任务） |
| `ARM_COMPARISON.json` | 一致性/注入分布/核验 issues |
| `PREFLIGHT.json` | 切点/门禁/材料可行性探测 |
| `traces_control/` / `traces_oracle/` | 逐任务 trace |
| `SHA256SUMS` | checksum_results.py --write 生成 |

