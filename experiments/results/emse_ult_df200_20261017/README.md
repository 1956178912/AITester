# ULT 检出优先（detection-first）accuracy 阶段 1（2026-10-17，n=200）

> **性质**：阶段 1（定标全量）实跑——**可对外引用的 accuracy 数**（n=200 配
> Wilson 95% CI），取代阶段 0 冒烟的描述性 n=20 值。预注册
> `docs/study/ULT_DF200_PREREG_2026-10-17.md`（判定口径跑批前锁定）。

## 主结果

| 指标 | 值 |
|---|---|
| arm | `plain_llm_df`（检出优先单提示，`AITESTER_PROFILE=logic`，temp=0） |
| 数据集 | ULT_Lite 全量 200（`--task-limit 200 --seed 42`） |
| **accuracy（green_on_fut）** | **21.0%（42/200）** |
| Wilson 95% CI | **[15.9%, 27.2%]** |
| pass / fail / nonterminate / material_missing | 42 / 158 / 0 / 0 |
| provenance | git_dirty=false（c55fb5a1）；cache_hit 14.74%（前 20 任务与冒烟 namespace 互异，重生成） |
| token | 理论 ~995K（≈$0.5–1，deepseek-flash） |

## 对照（量级，非同批/同协议，标注口径）

| 组 | accuracy | Wilson 95% CI | n |
|---|---|---|---|
| **检出优先 plain_llm_df（本件）** | **21.0%** | **[15.9%, 27.2%]** | 200 |
| 规格优先 replace | 19.6% | [10.7%, 33.2%] | 46 |
| 规格优先 specir | 20.0% | [8.9%, 39.1%] | 25 |
| QuixBugs 玩具程序 | 60.0% | [46.2%, 72.4%] | 50 |
| 官方 12 模型 accuracy 均值（K=20 greedy，全量 3909） | 41.32% | — | 3909 |

## 结论（描述性）

1. **复杂度鸿沟确认**：检出优先协议在 ULT 真实函数（cyclomatic ≥10）上的
   测试有效性 21.0%，显著低于玩具程序 60.0%（CI 不相交），与设计文档 R1
   预注册预期一致。
2. **检出优先 ≈ 规格优先（不可区分）**：21.0% [15.9%, 27.2%] 与规格优先
   19.6% [10.7%, 33.2%] / 20.0% [8.9%, 39.1%] 的 CI 高度重叠——
   **阶段 0 冒烟观察到的「检出优先 10% < 规格优先 20%」在 n=200 下未复现**
   （n=20 小样本方向信号，已由本件取代；预注册 §4 已披露 temp=0 跨跑批
   非确定性）。两种协议在真实函数上同为 ~20% 量级。
3. **低于官方 12 模型均值**：21.0% < 41.32%（量级对照，非同集/同协议——
   本项目单次提示 + ULT_Lite 200，官方 K=20 greedy + 全量 3909），不作
   绝对对标宣传。

## 文件

- `benchmark_ult_20261017_110803.json`：跑批工件（200 任务 details + provenance）
- `ACCURACY_REPORT.json`：accuracy 判定（`experiments/emse_ult_dfsmoke_accuracy.py`）
- `traces/`：逐任务轨迹

## 复现

```bash
AITESTER_PROFILE=logic AITESTER_CACHE_NAMESPACE=emse_ult_df200_20261017 \
TEMPERATURE=0.0 LLM_THINKING_MODE=disabled BENCHMARK_PARALLELISM=4 \
python experiments/run_benchmark.py --dataset ult --task-limit 200 --seed 42 \
  --baselines plain_llm_df --no-mutation \
  --output-dir experiments/results/emse_ult_df200_20261017
python experiments/emse_ult_dfsmoke_accuracy.py \
  --benchmark <benchmark_ult_*.json> --arm plain_llm_df \
  --out experiments/results/emse_ult_df200_20261017/ACCURACY_REPORT.json
```
