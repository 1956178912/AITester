# PREREG_CONTINUATION — T2/B1 执行修订与续跑规则（跑中落盘，正式分析前）

> **性质声明**：本文件在 6 格数据采集**全部完成之前**写入，属于**执行性修订（execution amendment）**，不是判据修订。`PREREG.md` §2–§7 的**研究问题、三格定义、seeds、数据、指标定义、判定规则（H-text / H-sampling / 联合 verdict）、失败/超时/停止规则**逐字不变，仍按预注册执行。本文件只登记：①已发生的运行观察；②为在墙钟预算内完成六格而做的**运行参数**修订；③修订后未完成格的续跑规则。
>
> 写入时点：2026-10-18 09:19（Asia/Shanghai），第 1 跑（C1_seed42）任务阶段已完成、辅助后处理仍在进行；**尚未产出任何可分析的主终点数据**（无批次 JSON、无 meta），因此本修订发生在任何判定数据可见之前。
>
> **09:21 更新（第一跑中止）**：C1_seed42 后处理持续 >10.5 min 仍未结束（`ps` 观测到 MDO 阶段持续子进程），继续等待将不可控。为避免把时间预算耗在非终点辅助测量上，**中止首跑进程组**（其日志已归档至 `_superseded_first_attempt/C1_seed42_pre_amendment.log`，未产生批次 JSON、无任何主终点数据被丢弃/查看），**改按 §2.1 修订后的统一 env 重跑全部六格**（不再保留 C1_seed42，六跑协议完全一致）。

## 1. 触发事实（来自实际运行日志，非估计）

- `_superseded_first_attempt/C1_seed42_pre_amendment.log`（首跑原文）：命令于 `2026-10-18T01:01:44Z` 启动；tqdm 任务进度在 **463.8 s（约 5:27）** 到达 100%（87/87），即 **LLM 生成/执行阶段约 7.7 分钟**完成。
- 任务阶段完成后，进程进入**辅助后处理**（`ENABLE_MUTATION_SCORING=true` 下内联 `mutation_score` + MDO 两个阶段，`experiments/run_benchmark.py::_run_baseline_postprocess_with_wall`）。到本修订写入时点，后处理已持续 **>9 分钟且未结束**（`ps` 观测到持续 fork 的 pytest 子进程；`sample` 显示主线程在 postprocess 循环中）。
- 仓库内已有同源记录：`experiments/mdo_posthoc.py` 模块文档直言"把 MDO 挂在 `ENABLE_MUTATION_SCORING` 下内联计算时，实测一次 **20 任务 × 2 臂**的跑批在批后阶段**再多花 >15 分钟且未收敛**（每个变异体要跑行为探针 + 测试，共 2 次子进程执行）"。
- 外推：6 跑（C1/C2/C3 × seed42/44）按"任务阶段 + 数分钟辅助后处理"计预计 2 小时以上，**会在 C3 之前触发 `PREREG.md` §6.4 的 85 min 全局硬停**，导致文本效应判定必需的 **C3（df 全协议）格缺失**，使预注册判据无法判定。

## 2. 修订决策（只改运行参数，不改判据）

1. **六格（首跑中止后整体重跑，含一切续跑）共享 env 增加 `ENABLE_MUTATION_SCORING=false`**（显式 env 覆盖 `AITESTER_PROFILE=logic` 的档位预设 `setdefault`，见 `config.py::_apply_profile_presets`）。
   - 该开关**只控制批后辅助测量**：`mutation_score`、`mdo_*` 字段（`_run_baseline_postprocess_with_wall` 内 mutation + MDO 两个 stage）。它**不参与** 生成 / 再生成 / 提示段落 / detection 计算 / 预算 / 停止规则，因此本实验的主终点 `detection_rate`（及并列 `llm_suite_detection_rate`）的测量口径与三格干预完全不变。
   - 选择关闭而非"调小 MDO 池/超时"的理由：两者都不是本实验的终点；调参仍保留 >若干分钟的不确定开销与新的参数面，而关闭可把单跑墙钟压回可预算区间，并避免"边跑边调参"污染时间可比性。MDO/mutation 若后续需要，可按项目既有做法用 `experiments/mdo_posthoc.py` **离线**补算（输入 `generated_test` 已在批次工件中），不需重跑 LLM。
2. **第一跑（C1_seed42，修订前）中止并整体重跑**（09:21 更新）：
   - 中止发生时该跑**尚未写出批次 JSON / meta**，主终点数据为零；其运行日志归档至 `_superseded_first_attempt/C1_seed42_pre_amendment.log`（含任务阶段 463.8 s 与后处理 >10.5 min 未完成的证据），**不作为任何分析输入**。
   - 六格全部按修订后统一 env（`ENABLE_MUTATION_SCORING=false`）重跑 → 六跑 env 完全一致，`PREREG.md` §3"格间唯一差异 = `DETECTION_FIRST_SECTION_ENABLE`"的表述在修订后协议内成立。
   - 披露：`README.md` §8 与 `GATES.json` 记录"首跑因批后辅助测量墙钟超预期被中止、整体重跑"这一运行事实；**任何 mutation_score/MDO 数值不得用于本批结论**（本协议已关闭其计算）。
3. **续跑触发规则**：若 `PREREG.md` §6.4 的全局硬停（wall>5100 s 或累计费用>$1.8）在六格齐备前触发，则**立即在同一隔离 worktree（切点 `a93c1f6`）、同一 env（含上述修订）、同一 seeds/task 集/预算/`AITESTER_CACHE_NAMESPACE` 规则下续跑缺失格**（runner `--resume`：跳过已完成的格，不重跑；单 run watchdog 仍 1800 s）。六格齐备后再分析。
4. 其余不改：§4 指标定义、§5 判定规则、§6 失败处理、$2.0 总预算上限、seeds 42/44、`--task-count 87 --max-pattern-repeat 2`、`DETECTION_FIRST_SECTION_ENABLE` 三格定义、`AITESTER_CACHE_NAMESPACE=t_b1_<cell>_<seed>`、trace 目录约定。

## 3. 修订后预算与墙钟重估

- 单跑任务阶段（观测 463.8 s 为 C1 首跑；C2/C3 预计 1.4–1.8×）→ C1 ≈ 8 min、C2 ≈ 12–13 min、C3 ≈ 13–14 min。
- 辅助 postprocess 关闭后不再有 10+ min 级后处理；**六格整体重跑**（09:21 起）预计 **≈ 60–70 min** 完成；含首次尝试已耗 ≈ 20 min，累计墙钟预计 **≈ 85–90 min**；若续跑，按 §2.3 规则执行。
- 费用：C1_seed42 的任务阶段 token 已计入；后处理零 LLM 零费用。预计 6 跑总计 ≈ $0.9–1.1，低于 $2.0 上限与 $1.8 硬停阈值。
- 本修订**不改变**任何统计判据；若最终判定因数据缺失而不成立，按 `PREREG.md` §6.3 如实报 `insufficient_data`。
- 首次尝试（09:01:44–09:21，C1_seed42 修订前）已耗墙钟与 token 如实计入总账：其任务阶段 token 消耗约见 `_superseded_first_attempt/C1_seed42_pre_amendment.log`（该跑还额外烧掉一次辅助后处理但不产生工件）；总费用预计仍 ≤ $1.2。

## 4. 披露义务（写入最终 README）

- 本批存在一次**跑中执行修订**：`ENABLE_MUTATION_SCORING` 在 C1_seed42 为 true、其余跑为 false；修订动机（墙钟）、影响面（仅辅助测量字段）与不建议引用 mutation/MDO 字段的告诫，必须写入 `README.md` 的"运行参数与局限"节。
- 不得把"同 env"表述为 6 跑完全一致；应表述为"三格干预协议同 env，辅助测量开关按本修订逐跑记录"。
