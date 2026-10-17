# D1 QuixBugs 提示协议 A/B 批次（2026-10-13，EMSE 优化决策项 D1 执行）

> 目的（主报告 §6 决策项 D1）：补跑 bare `plain_llm` 臂，与 `plain_llm_df`
> 臂在 QuixBugs 真实代码上做配对对照，验证合成集上"+43pp 检出优先协议
> 增益"是否可外推到真实代码。两臂同批跑批（同缓存命名空间、同模型
> 快照、同判分环境），配对口径。

## 跑批协议

| 项 | 值 |
|---|---|
| 命令 | `AITESTER_PROFILE=logic TEMPERATURE=0.0 LLM_THINKING_MODE=disabled BENCHMARK_PARALLELISM=4 AITESTER_CACHE_NAMESPACE=emse_d1_qb_seed42 .venv/bin/python experiments/run_main_batch.py --dataset quixbugs --task-count 50 --seed 42 --baselines plain_llm,plain_llm_df --skip-stats --allow-dirty --dirty-reason "EMSE D1 QuixBugs bare plain_llm vs plain_llm_df A/B (50 tasks seed42, 2026-10-13)"` |
| 工件 | `benchmark_quixbugs_20261013_155145.json` |
| git_dirty | True（豁免原因已入 provenance.dirty_reason） |
| 模型 | deepseek-flash，temp=0.0，thinking disabled |
| 模型指纹 | pinned，`aeb56401ca74e127821c4f9126dcb669`——与 spec_replace 扩样（10-12）、D2 冒烟（10-13）**一致**，跨批次对照具备同一模型快照前提 |
| 墙钟 | 2h36m（沙箱机器满载导致子进程大面积 30s 超时重试，见 §4） |

## 1. 结果（配对 McNemar + 贝叶斯，n=36 共同可测）

| 对比 | 仅前 | 仅后 | 双中 | 双未 | δ | p（精确） | BF10 | MDE(80%) | 判读 |
|---|---|---|---|---|---|---|---|---|---|
| plain_llm vs plain_llm_df | 0 | 1 | 24 | 11 | **−2.78pp** | 1.0000 | 1.00 | 3.89pp | 数据不充分；功效内可排除 ≥3.9pp 的协议增益 |

- 臂级边际率：plain_llm **66.67%**（24/36）、plain_llm_df **69.44%**（25/36）；
- 跨批次对照（本批 df vs scale87 df，10-12 无 profile 口径）：69.44% vs
  75.0%，δ=−5.56pp，p=0.7266，BF10=0.35——同向不显著（机器负载
  混淆跨批次比较，仅作稳健性参考，主判据为批内配对）。

**结论：合成集 +43pp 的协议增益在 QuixBugs 真实代码上不可复现**
（δ=−2.8pp，p=1.0，BF10=1.0；80% 功效下可检测下限 3.9pp）。
论文中"检出优先提示协议 +43pp"的主张应加**数据集限定语**。

## 2. 机制解释（为什么真实代码上协议无功）

1. **两臂首轮 prompt 相同**：检出优先强化段落（"先红后绿"）只在
   **再生成调用**时注入（`nodes.py:_detection_first_section` →
   `_detection_first_regenerate_entry`，要求首轮 `test_passed=True`）；
   首轮调用两臂逐字节同 prompt（代码级核实）；
2. **协议只通过再生成介入**：首轮全绿（假成功，DETECTION_FIRST 路由）
   或首轮过红（特异性门，logic 档注入）才触发再生成。df 臂 15/50
   触发再生成，plain_llm 臂 2/50；
3. **QuixBugs 上首轮即红占 49/50**（玩具缺陷程序，任何合格测试都能
   让缺陷代码变红）——协议的应用场景（挽救全绿假成功）几乎不出现；
   唯一走"全绿→带段落再生成"路径的任务
   （`quixbugs__is_valid_parenthesization`）被协议救回
   （det 0→1），即唯一的不一致对；
4. 合成集正相反：plain_llm 首轮 87.7% 全绿假成功，协议有巨大发挥
   空间——**协议价值与"首轮免假成功率"成正比，是数据集属性而非
   普适增益**。

## 3. 缓存重放披露（ reproducibility 必读）

- plain_llm 臂：50/50 行全新调用（95,628 tokens，token 记账齐全）；
- plain_llm_df 臂：**48/50 行零调用（缓存命中）**——首轮 prompt 与
  同进程 plain_llm 臂相同（§2.1），命中其刚写入的同命名空间缓存
  文件；48/50 行 generated_test 与 plain_llm 臂**逐字节相同**；
- 2 行有真实调用（`is_valid_parenthesization` 1549 tok +
  `shunting_yard` 3397 tok）：再生成段落 prompt 无缓存文件 → 全新
  调用；
- **无偏性论证**：temp=0 + 同一模型快照（指纹 aeb56401 跨批次
  一致）⇒ df 首轮若全新调用也会返回逐字节相同响应；缓存重放是
  **确定性等价**而非抽样替代。但严格独立性口径下应披露为
  "df 臂 = 同进程确定性重放（48/50）+ 全新再生成（2/50）"；
- 本批启动警告（AITESTER_LLM_CACHE 未禁用）适用于此；正式论文
  实验如需全新抽样，应设 `AITESTER_LLM_CACHE=0` 重跑两臂。

## 4. 日志"执行失败"刷屏诊断（用户质询，2026-10-13）

- `第 N 次执行失败，尝试重试...`（`src/agents/executor_runtime.py:168`）
  = **pytest 在缺陷代码上退出码非零（测试变红）**，即检测信号本身，
  **不是 LLM/API 失败**；固定重试 1 次（max_attempts=2）后记录红色。
  QuixBugs 首轮即红占 49/50，故该警告刷屏。历史批次（d1.log 等）
  同型；
- 日志中真正的基础设施事件为 30s/60s 子进程超时
  （executor / mutation_testing / m1_metrics / O3 branch）——跑批期间
  沙箱机器满载（同期前台命令被 OOM kill），pytest 子进程大面积超时，
  是 2h36m 墙钟的主因；超时按保守口径降级（None/不计入），
  两臂同环境判分，配对结论不受影响；
- **模型侧健康证据**：日志零 API 错误签名（无 429/连接/鉴权错误）；
  100/100 行 `error_category` 为空；模型指纹 pinned 且跨批次一致；
  token 记账正常（plain_llm 95,628 / df 4,946 真实调用）。

## 5. 成本登记

- 真实 token 消耗：plain_llm 95,628 + plain_llm_df 4,946 ≈ **100.6k**
  （≈$0.06，deepseek-flash 峰时价上界）；
- 缓存避免的 token（df 臂重放）≈ 48×3.5k ≈ 170k（≈$0.10，未实际
  计费）；
- 加 D2 冒烟（5 任务合成集）合计实际支出 <$0.15，远低于预估 $0.5。

## 校验

```bash
cd experiments/results/emse_d1_quixbugs_ab_20261013 && shasum -a 256 -c SHA256SUMS
```

复算（零 LLM）：

```bash
.venv/bin/python experiments/emse_optimization.py \
  --ab-pair experiments/results/emse_d1_quixbugs_ab_20261013/benchmark_quixbugs_20261013_155145.json \
            experiments/results/emse_d1_quixbugs_ab_20261013/benchmark_quixbugs_20261013_155145.json \
            plain_llm plain_llm_df detection_rate
```
