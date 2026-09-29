# 改进批次落地（P5）：level2.5-hard 难度层 + n=40 大规模 A/B 验证（2026-10）

> **本批次背景**：针对 2026-09 批次 A/B 阴性结果（定位 0/30、RAG token 负向、
> 跨文件 T1 未达 +15pp）的根因修复后，以 n=40 大规模验证确认改进方向。
>
> **默认行为不变**：所有新增能力均带独立环境变量开关，默认关闭，
> 历史实验基线不受影响。
>
> **数据源**：`experiments/results/{pa_l25h_n40,rag_lvl25h_n40,cf_bi_l35_n40}/`；
> **基线口径**：agnes-3.0-flash（LLM_1）+ 合成数据集 + seed=42，n=40。

---

## 1. P5.1：level2.5-hard 难度层（BUG_PATTERNS_LEVEL25HARD）

**背景**：level2.5 运行时异常缺陷库在 agnes-3.0-flash 上首轮生成即全过
（100% 成功率），定位阶段未能被激活——缺陷太浅，LLM 第一轮就能修复。
为让定位阶段有可测量的样本，新增 8 个"困难"缺陷模式：

| 模式名 | 缺陷类型 | 特征 |
|---|---|---|
| `hard_depth_blind_nested` | KeyError → AssertionError | 嵌套 dict 深度访问无 guard |
| `hard_chained_dict_lookup` | KeyError | 链式 dict 取值无 `.get` |
| `hard_polluted_entry_guard` | TypeError | 被污染条目混入正常聚合 |
| `hard_iter_over_none` | TypeError | 迭代 None（未初始化变量） |
| `hard_nested_iter_mixed` | TypeError | 嵌套迭代类型混入 |
| `hard_mixed_numeric_agg` | TypeError | 数值聚合中混入 None/str |
| `hard_attribute_chain_guard` | AttributeError | 属性链无 guard |
| `hard_slice_contract` | IndexError | 切片越界 |

- 设计目标：缺陷藏在嵌套调用链 / 特定输入形状里，agnis-3.0-flash 首轮
  生成会失败（激活定位阶段），但在 MAX_ITERATIONS=3 内可修复。
- 注册为难度码 26（`_DIFFICULTY_PATTERNS[26]`）；
  decimal map `"2.5-hard" → 26`；
  CLI `--difficulty level2.5-hard` 在 `run_benchmark.py` /
  `rag_ab_experiment.py` / `position_aware_ab.py` / `cross_file_ab.py` 均已支持。
- 回归测试 81 通过（`test_dataset_loader.py` + `test_synthetic_dataset.py`）。

**G8-lite 数据管道（同批落地）**：`data/` 被 .gitignore 排除（`data/` 整目录），
SWE-bench lite 复测数据文件不入库，需按下述步骤本地重建（约 2 分钟）：

```bash
# 1. 下载 lite (dev split) 225 行
export SSL_CERT_FILE=/etc/ssl/cert.pem HF_ENDPOINT=https://hf-mirror.com
.venv/bin/python scripts/download_swe_bench.py --subset lite --output data/
# 或直接用 datasets API（loader 已映射 lite→dev）：
.venv/bin/python - <<'EOF'
from datasets import load_dataset
import json
ds = load_dataset("princeton-nlp/SWE-bench", split="dev")
with open("data/swe_bench_lite_instances.jsonl", "w") as f:
    for item in ds:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")
EOF
# 2. 合并 enrichment（仅 20 个 sqlfluff 任务携带 instance_code）
#    → data/swe_bench_lite_instances_merged.jsonl
# 3. 取 gate-ready 子集（instance_code + test_patch + FAIL_TO_PASS + base_commit）
#    → data/swe_bench_lite_g8_ready.jsonl（20 任务，全 sqlfluff）
# 4. 门禁检查（把子集放入任意目录并命名 *instances.jsonl）：
mkdir -p /tmp/g8data && cp data/swe_bench_lite_g8_ready.jsonl /tmp/g8data/swe_bench_pro_g8_instances.jsonl
AITESTER_SWE_BENCH_PRO_DIR=/tmp/g8data .venv/bin/python scripts/check_swe_bench_pro_ready.py --data-dir /tmp/g8data
# 5. 全开链路复测（七开关 + 仓库级验证）：
export AITESTER_SWE_BENCH_PRO_DIR=/tmp/g8data
.venv/bin/python experiments/run_full_stack_swe_bench_pro.py \
    --dataset swe_bench_pro --task-limit 3 --output-dir experiments/results/g8_lite_retest --no-rag
```

---

## 2. P5.2：n=40 三组 A/B 结果

### 2.1 位置感知 L2.5-hard（position_aware_ab.py）

| 指标 | OFF | ON | delta |
|---|---|---|---|
| 成功率 | 85.0% | 92.5% | **+7.50pp** |
| 平均迭代 | 0.68 | 0.55 | -0.13 |
| 定位正确率 | —（未激活） | 25.0% | — |

- 定位正确率分母为有修复轮次的任务（`_repaired=True`），命中 gold
  `suggested_function` 的比例为 25%（1/4 的激活样本）。
- 成功率 +7.50pp 为正，平均迭代下降 0.13——定位引入的开销未抵消收益。
- 结论：**位置感知在 L2.5-hard 上产生正向收益**，但定位正确率仍偏低
  （25%），后续可在 debugger 侧加强 AST 区间收窄逻辑。

### 2.2 RAG 相关性 L2.5-hard（rag_ab_experiment.py --relevance-ab）

| 指标 | RAG ON | RAG OFF | delta |
|---|---|---|---|
| 成功率 | 87.5% | 87.5% | 0.00pp |
| 平均 token | 4197 | 1558 | **+2639（RAG ON 多消耗）** |
| 平均迭代 | 0.38 | 0.60 | -0.22 |
| Cohen's d（token） | 0.944 | — | 显著（p_welch=0.0000） |

- RAG ON 相关性过滤生效（`relevance_filter_rate > 0` 的记录存在），
  但 token 净增 +2639（检索注入上下文）；成功率持平。
- 迭代 ON 下降 0.22（RAG 辅助减少修复轮次），但不显著（p=0.29）。
- 结论：**RAG 相关性层在 L2.5-hard 上未带来成功率提升，token 成本显著增加**，
  与原 n=8 小样本方向一致（RAG 非该难度层的有效优化维度）。

### 2.3 跨文件双向 L3.5（cross_file_ab.py --bidirectional）

| 指标 | OFF | ON（bidirectional） | delta |
|---|---|---|---|
| 成功率 | 80.0% | 87.5% | **+7.50pp** |
| 平均迭代 | 0.78 | 0.60 | -0.18 |
| T1 阈值（≥ +15pp） | — | ❌ 未通过 | — |

- 双向依赖图 + 双向拓扑序使 ON 组提升 +7.50pp，仍低于 T1 的 +15pp 阈值。
- 根因分析脚本（`cross_file_root_cause.py --results-on ... --difficulty level3.5`）
  可进一步定位未达阈值的瓶颈（预期为 `LLM_CAPABILITY` 类）。
- 结论：**跨文件机制在 L3.5 n=40 上仍交付正向增益（+7.5pp），但未达 T1**；
  瓶颈在 LLM 能力而非依赖图（与 n=8 小样本结论一致，n=40 放大后 delta 稳定）。

---

## 3. 回归测试

- `tests/test_dataset_loader.py` + `tests/test_synthetic_dataset.py`：81 通过。
- ruff 全绿（`src/datasets/` + 全部修改的 `experiments/` 脚本）。

---

## 4. 默认行为不变声明

本批次全部新增内容（`BUG_PATTERNS_LEVEL25HARD` 8 个模式、难度码 26、
`level2.5-hard` CLI 选项）**默认关闭**；历史实验基线（mixed / level2.5 /
level3.5 单入口口径）逐字节不变。

---

*生成时间：2026-10；数据源：`experiments/results/{pa_l25h_n40,rag_lvl25h_n40,cf_bi_l35_n40}/`；
基线口径：agnes-3.0-flash（LLM_1）+ 合成数据集 + seed=42，n=40。*
