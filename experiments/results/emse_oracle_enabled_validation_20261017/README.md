# O-2 oracle-enabled 二臂验证批（真 LLM，验证性测量，2026-10-17）

> 运行 20261017T175944Z；切点 worktree `/Users/wangchenyu/Workspace/AITester-o2-oracle-70b5436`，HEAD=`70b5436a9b8786b18b5bd80a83ce8a4741b2bfce`；
> 本报告数字全部由脚本从两臂批次 JSON 直出（不手写）；协议见 §1。

## 1. 协议（固定，验证性非 confirmatory）

- 臂 A（control）：`--baselines plain_llm_df_spec`，oracle 关闭；臂 B（oracle）：同一 baseline + `SPEC_ORACLE_EXEC_ENABLE=true`；均不设 `DETECTION_SPEC_MODE`。
- `--dataset quixbugs --task-limit 20 --seed 42`；`AITESTER_PROFILE=logic TEMPERATURE=0.0 LLM_THINKING_MODE=disabled BENCHMARK_PARALLELISM=4`。
- `AITESTER_BATCH_MAX_CALLS=100 COST_BUDGET_ENABLE=true COST_BUDGET_USD=1 AITESTER_LLM_CACHE=0`；两臂独立 `AITESTER_CACHE_NAMESPACE`。
- 零 LLM 材料可行性探测：arm_can_inject_oracle=`True`；no_anchor_verdict=`not_attempted`；spec_anchor_injected=`True`。
- SPEC_ANCHOR_TABLE sha256=`3e90b2ad5ed365ad5ee989c73c92b84956a83c0fa8cb51368d288ae3ea53bf22`（仅 arm_baseline=plain_llm_df_spec 时涉及）。
- 调度：两臂**并发**执行（各 P4、独立 namespace/log/trace；主指标在任务阶段采集，次指标含并发 CPU 噪声）。

> **sequential pairing 披露**：本轮为 **control-only 补跑**（attempt#2 的 control 臂在 MDO 后处理阶段撞 2400s 看门狗失败），
> oracle 臂批次**复用** attempt#2 已完成工件（`/Users/wangchenyu/Workspace/AITester/experiments/results/emse_oracle_enabled_validation_20261017/_attempt2_partial_control_timeout_20261018/benchmark_quixbugs_20261018_015516.json`），未重跑。两臂同切点/同协议/独立 namespace，
> 但 control 补跑与 oracle 运行**不是同一并发时刻**（sequential pairing，非 same-batch concurrent），解释时须注意。

**验证性协议修正（Lead 批准 2026-10-17，方案 a）**：任务书默认 baseline `plain_llm_df` 修正为 `plain_llm_df_spec`。
原因：N-3 oracle 材料优先级 = `spec_ir` → `test_plan.logic_analysis` → `spec_anchor.logic_analysis / human_spec`；
`plain_llm_df` 无 planner（无 `test_plan`）且不加载锚表（无 `spec_anchor`）→ 材料为空 → `SPEC_ORACLE_EXEC_ENABLE=true`
只会记 `not_attempted`，无法验证 oracle 注入；`plain_llm_df_spec` 携带 `spec_anchor.logic_analysis`（随库 `SPEC_ANCHOR_TABLE`）
为可编译锚材料 → 才能真实验证 oracle-enabled 通道。**该修正属验证性协议修正，不改变任何判定规则/判分口径。**

> **profile preset 陷阱（O-2 实测，AITESTER_PROFILE=logic）**：档位预设会用 `setdefault` 注入
> `SPEC_ORACLE_EXEC_ENABLE=true`（`config.py` logic 预设）——关闭 oracle 的 control 臂必须**显式**
> `SPEC_ORACLE_EXEC_ENABLE=false`，仅 unset 会被预设重新打开（O-2 首跑即因此 invalid，见附录 / `_invalid_control_attempt_20261018/`）。

## 2. 两臂结果

| 项 | A（control） | B（oracle） |
|---|---|---|
| baseline / namespace | `plain_llm_df_spec` / `emse_oracle_enabled_validation_20261017_control` | `plain_llm_df_spec` / `emse_oracle_enabled_validation_20261017_oracle` |
| 批次工件 sha256 | `56b948f5a8fb04ce…` | `a81b902cfdd6543a…` |
| 行数 | 20 | 20 |
| 墙钟(s) | **2297.4**（watchdog 实测；control 补跑） | **2311.4**（attempt#2 watchdog 实测；批次复用） |
| tokens（in/out/total） | 24258/36341/60599 | 24330/36452/60782 |
| LLM calls / cache hits | 27/0 | 27/0 |
| 成本（标准价上界） | $0.0509 | $0.0510 |
| LLM-suite detection | 71.43% | 78.57% |

## 3. oracle 注入与独立判读分布

| 字段分布 | A（control） | B（oracle） |
|---|---|---|
| `spec_oracle_injected` | `{"None": 20}` | `{"False": 4, "True": 16}` |
| `spec_oracle_verdict` | `{"not_attempted": 20}` | `{"compiled_empty": 4, "injected": 16}` |
| `oracle_suite_verdict` | `{"unavailable": 20}` | `{"unavailable": 15, "silent": 5}` |

- **实测解读**：
  - **control（oracle 显式关闭）**：`spec_oracle_injected` 全 None、`spec_oracle_verdict` 全 `not_attempted`、`oracle_suite_verdict` 全 `unavailable`
    → **关闭 oracle 时无任何注入**（符合预期，也证明开关真正生效、环境无串味）。
  - **oracle**：`injected=16/20`、`compiled_empty=4/20`（3 个 `*_test` 驱动任务 + `flatten`，材料不可编译→不注入，非故障）；
    `oracle_suite_verdict = unavailable 15 / silent 5`，**correct=0 / fp=0 / misguided=0**。与 M-2 加固前 fp 76.3% 对照，
    **O-1 的崩溃安全目标在本批再次得到方向性支持（无 fp）**；但本 20 任务子集 oracle 断言无区分信号，不作 oracle 质量结论。

## 4. LLM-suite 一致性（oracle 不改变 LLM 检出）

- 两臂共同任务：20；逐任务 `detection_rate`/`llm_suite_detection_rate` 不一致：**1**；
- only_in_control=[]；only_in_oracle=[]。
- **解读**：20 个共同任务中 19/20 的 LLM-suite 判定完全一致；唯一不一致 `kheapsort`（control 0.0 / oracle 1.0）发生在
  **sequential pairing** 下，无法归因于 oracle（N-3 起 `detection_rate` 语义=LLM-suite，oracle 测试被排除在执行/判分之外；
  且 attempt#1 同配置重复跑曾出现 2/20 逐任务不一致——temp=0 仍有 run-to-run 非确定性）。
  **结论（验证性）**：本批未发现"oracle 注入改变 LLM-suite 检出"的证据；差异幅度在重跑噪声量级内。

| task | control | oracle |
|---|---|---|
| `quixbugs__kheapsort` | 0.0 | 1.0 |

## 5. provenance / env_snapshot / 完整性

| 项 | A（control） | B（oracle） |
|---|---|---|
| git_sha / dirty | `70b5436a9b8786b18b5bd80a83ce8a4741b2bfce` / False | `70b5436a9b8786b18b5bd80a83ce8a4741b2bfce` / False |
| fingerprint pinned / returned | True / deepseek-flash | True / deepseek-flash |
| env_snapshot.SPEC_ORACLE_EXEC_ENABLE | `false` | `true` |
| env_snapshot.DETECTION_SPEC_MODE | `None` | `None` |
| 行字段完整率 | `{"spec_oracle_injected": "20/20", "spec_oracle_verdict": "20/20", "oracle_suite_verdict": "20/20", "llm_suite_detection_rate": "20/20", "detection_rate": "20/20"}` | `{"spec_oracle_injected": "20/20", "spec_oracle_verdict": "20/20", "oracle_suite_verdict": "20/20", "llm_suite_detection_rate": "20/20", "detection_rate": "20/20"}` |

核验 issues：无。

## 6. 成本 / 墙钟 / 异常与局限

### 6.1 最终有效 A/B 两臂（本批主结果）
| 项 | control | oracle |
|---|---|---|
| 执行 | attempt#3 control 补跑（oracle off） | attempt#2 oracle 臂（复用批次，未重跑） |
| 墙钟(s) | 2297.4 | 2311.4 |
| tokens / LLM calls | 60,599 / 27 | 60,782 / 27 |
| 成本（标准价上界） | **$0.050887** | **$0.051041** |
| 合计 | **$0.101928** | |

### 6.2 O-2 全轮成本（含两次不完整尝试，供预算审计）
| 尝试 | 状态 | 成本 |
|---|---|---|
| attempt#1（两臂 oracle-on，对照无效） | 已归档 | $0.094722（完整记账） |
| attempt#2（control 撞 2400s 看门狗失败） | 已归档 partial | oracle $0.051041（有效）；control 无批次工件、LLM 消耗不可精确记账（保守估 ≈$0.04） |
| attempt#3（control 补跑） | 本报告 | $0.050887 |
| **O-2 累计** | | **≈$0.1967 实测 + ≈$0.04 未记账 ≈ $0.23–0.24**（Lead 豁免上限 $0.25 ✓） |

- 墙钟累计：attempt#1 2329s + attempt#2 2402s + attempt#3 2297s ≈ **117min**（Lead 豁免 ≤140min ✓）。
- 验证性测量（非 confirmatory），小样本 20 任务不作显著性/效能结论。

### 6.3 后处理墙钟 run-to-run 波动证据（重要局限）
- **control 臂三次墙钟**：attempt#1 **2102.4s**（成功）→ attempt#2 **>2400s 被看门狗终止**（终止时处于 **MDO 后处理**阶段，
  日志残留 `aitester_mdo_*/test_find_first_in_sorted.py` 子进程）→ attempt#3（本批）**2297.4s**（成功）。
- 同 cut、同协议、同 20 任务，墙钟波动 ≥14%（2102→>2402s），**尾部超过当时固定的 2400s 看门狗**；方差主要来自任务阶段后的串行后处理
  （mutation_testing / m1_metrics / O3 / MDO 的 30–120s 超时链；QuixBugs 非终止家族放大波动）。
- **下一轮建议**：(a) 批次 runner 的 per-arm watchdog 不要用固定 2400s，改为 `task_phase_预估 + 后处理预算 + margin`（20 任务 logic/df_spec 建议 ≥3600s；
  本报告已用 3600s 成功）；(b) 把 mutation_testing / m1_metrics / MDO / O3 的逐任务超时与总预算做成可配置 env（如 `POSTPROCESS_BUDGET_SECONDS`、
  `MDO_TIMEOUT_SECONDS` 等）并在日志里输出**逐阶段墙钟分解**，便于下轮预注册披露与看门狗自适应；(c) 失败臂保留的孤儿 pytest（本批 1 例，
  已记录并清理）再次提示需要"后处理收尾巡检"兜底。
- 其他局限：单模型/单数据集/单 seed；两臂为 sequential pairing（非同一并发时刻）；oracle-suite 为机制侧描述性信号，不替代 LLM-suite detection 主判定。

## 7. 复现

```bash
# 常规两臂（并发）
bash experiments/run_oracle_validation_batch.sh \
  --root <clean-worktree> --require-clean-root --arm-baseline plain_llm_df_spec
# 本报告实际执行（control-only 补跑 + 复用 attempt#2 oracle 批次）：
bash experiments/run_oracle_validation_batch.sh \
  --root /Users/wangchenyu/Workspace/AITester-o2-oracle-70b5436 --require-clean-root \
  --arm-baseline plain_llm_df_spec --watchdog-seconds 3600 --only-control \
  --reuse-oracle-batch <attempt#2 oracle batch.json>
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
| `PROC_HYGIENE*.md` / `proc_hygiene.log` | 跑批期/收尾孤儿 pytest 巡检与清理记录 |
| `_invalid_control_attempt_20261018/` | attempt#1 归档（两臂 oracle-on，**对照无效**；含其 README/JSON/SHA；原样保留） |
| `_attempt2_partial_control_timeout_20261018/` | attempt#2 归档（control 撞 2400s 看门狗；含 oracle 有效批次+两臂日志/PREFLIGHT/孤儿记录；原样保留） |
| `SHA256SUMS` | 顶层 checksum_results.py --write 生成（134 项，递归包含三个归档目录） |

## 9. 执行历史（三次运行，全部保留）
| # | 结果 | 关键事实 | 归档 |
|---|---|---|---|
| attempt#1 | **invalid**（对照无效） | A/B 均 oracle-on：`AITESTER_PROFILE=logic` 预设 setdefault 注入 `SPEC_ORACLE_EXEC_ENABLE=true`，仅 unset 无法关闭 | `_invalid_control_attempt_20261018/`（58 文件） |
| attempt#2 | **partial**（control 失败） | 配置已修正（PREFLIGHT effective_env_probe: control=false/oracle=true distinct）；oracle rc=0 有效；control 后处理超 2400s 被看门狗终止（无批次 JSON） | `_attempt2_partial_control_timeout_20261018/`（55 文件） |
| attempt#3 | **valid**（本报告主表） | control-only 补跑（watchdog 3600s）rc=0/2297.4s；oracle 复用 attempt#2 批次；核验 issues 无 | 本目录顶层 |

## 10. 结论（验证性，不改变任何判定规则）
1. **oracle-enabled 真实链路可用**：B 臂 20 任务中注入 16/20（4 例为材料不可编译），字段 `spec_oracle_injected`/`spec_oracle_verdict`/`oracle_suite_verdict`/`llm_suite_detection_rate` 逐行 20/20 在场。
2. **O-1 崩溃安全方向性验证通过**：oracle-suite 结果 = unavailable 15 / silent 5 / **fp 0**（M-2 加固前 fp 76.3%）；本子集无 correct/misguided，属"无区分信号"，不作 oracle 质量结论。
3. **独立判读不损伤检出（验证性支持）**：LLM-suite detection control 71.43%(10/14) vs oracle 78.57%(11/14)；20 个共同任务 19/20 判定一致，唯一差异（kheapsort）在 sequential pairing + temp=0 重跑噪声量级内，**未发现 oracle 改变 LLM-suite 检出的证据**。
4. **开关有效性/审计**：控制臂显式 `false` 时零注入、oracle 臂显式 `true` 时按预期注入；两臂 env_snapshot 分别 `false`/`true`；provenance `git_dirty=false`、切点 `70b5436`、跑前/跑后 worktree 0 dirty。
5. **已知限制**：sequential pairing、单模型/单数据集/单 seed、20 任务小样本、后处理墙钟波动（已给出下一轮可配置化建议）。

