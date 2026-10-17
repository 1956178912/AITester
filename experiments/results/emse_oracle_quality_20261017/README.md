# A-05 oracle 质量度量工件（emse_oracle_quality_20261017）

> **性质**：M 轮 T7-A（独立评审 §10 A-05 / G6 / D-4）零 LLM 重放的**描述性**
> 机制度量工件。oracle 质量反映确定性规约通道，**不是 LLM 生成能力指标**；
> 非预注册确认性证据，不做显著性推断。

## 1. 输入 sha256（只读消费）

| 输入 | sha256 |
|---|---|
| `experiments/results/emse_df_spec_20261016/benchmark_quixbugs_20261016_232138.json` | `813c437fc53a84c1517cce234b12184e5047bf483fb982cb9382d1c61307245a` |
| `experiments/results/emse_df_spec_20261016/benchmark_quixbugs_20261017_003023.json` | `536da803dbb290dab9dff26ae14302a8ce8d452e058b1d2c4c1705852900d0ec` |
| `experiments/results/emse_spec_anchor_20261016/SPEC_ANCHOR_TABLE.json` | `3e90b2ad5ed365ad5ee989c73c92b84956a83c0fa8cb51368d288ae3ea53bf22`（SHA256SUMS 校验：`experiments/results/emse_spec_anchor_20261016/SHA256SUMS`） |

> 以上输入工件哈希同时以 `../` 相对路径引用行记入同目录 `SHA256SUMS`（`scripts/gates/checksum_results.py --verify` 一并校验；文件内路径条目仅覆盖本目录工件）。

## 2. 复算命令

```bash
python -m experiments.oracle_quality_replay --out experiments/results/emse_oracle_quality_20261017 --jobs 4 --per-test-timeout 1 --file-timeout 240 --repeat 1
```

## 3. 覆盖与分母

- `plain_llm_df_spec`（treatment）：任务行 50，锚命中 50，注入成功 38，可测 oracle 任务 38，可分类 oracle 测试（分母）38，不可分类 0
- `plain_llm_df`（control）：任务行 50，锚命中 50，注入成功 38，可测 oracle 任务 38，可分类 oracle 测试（分母）38，不可分类 0

> 四分类占比分母 = 可分类 oracle 测试数（buggy/fixed 两侧均有 pass/fail）；
> timeout/collect/import/syntax/skipped/test_error/missing_side 单列、不进分母。

## 4. 核心数字（40 缺陷程序口径）

| 指标 | `plain_llm_df_spec` | `plain_llm_df` |
|---|---|---|
| `correct` 计数/占比 | 0 / 0.00% | 0 / 0.00% |
| `fp` 计数/占比 | 29 / 76.32% | 29 / 76.32% |
| `silent` 计数/占比 | 9 / 23.68% | 9 / 23.68% |
| `misguided` 计数/占比 | 0 / 0.00% | 0 / 0.00% |
| detection `archived` | 54.29% | 77.78% |
| detection `llm_only_replay` | 50.00% | 77.50% |
| detection `oracle_augmented_replay` | 10.53% | 18.42% |
| Δ augmented − llm_only（配对 pp） | -36.8421 | -57.8947 |

## 5. 交叉校验（0 mismatch 要求）

- `plain_llm_df_spec`：detection 对账 {'artifact_none': 6, 'both_none': 9, 'match': 35}（mismatch=0）；归档 oracle verdict 复现 {'match': 50}（mismatch=0）；归档字段自洽性违规 0；**all_ok=True**
- `plain_llm_df`：detection 对账 {'artifact_none': 5, 'both_none': 9, 'match': 36}（mismatch=0）；归档 oracle verdict 复现 {'match': 50}（mismatch=0）；归档字段自洽性违规 0；**all_ok=True**

## 6. 确定性 / 墙钟

- body digest：`ce10e33bc54b56c00c26cd5fd5f7f741649a52554e579d0f154f4a46fd372376`
- repeat=1；deterministic=True；各次 digest=['ce10e33bc54b56c00c26cd5fd5f7f741649a52554e579d0f154f4a46fd372376']
- 本次重放墙钟：390.333 s（只进 run_meta，不进 body digest）
- **确定性口径**：A-05 repeat=1（单测锁 body 结构；窗口结束后可选补 repeat=2）；A-11 repeat=2 逐位一致。

## 7. 已知限制

- 反事实注入口径：锚表材料直接重建 test_plan（无 Planner 现场 spec_ir / boundary_triplets），不声称等同完整 logic 链路生产注入质量
- 归档批次（plain_llm_df*，Planner 关闭）生产注入口未实际尝试注入；本报告质量数字来自零 LLM 重放
- oracle 与 LLM 测试同文件、同 pytest session 执行（生产口径），全局状态污染与收集顺序照旧
- 官方金测试 test_cases 不参与本分类，仅用于任务级 detection 交叉校验口径说明
- 9 个 QuixBugs *_test 驱动任务（相对 import、无金测试）与辅助模块 node 在平铺执行口径下结构性不可 replay → 结构跳过单列；41 口径兼容行（node，buggy==fixed）无缺陷信号，主分析集为 40 口径
- per-test timeout 把挂死 oracle 测试记为不可分类 timeout（不并入四分类），与 M1 判分口径有意不同
- oracle 假阳/误导若因编译器提供的 0 字面量绑定导致（如 TypeError），属确定性通道自身缺陷，由 failure_stats.fixed_side_exception_types 逐类披露，不在本工具内修复
- 描述性对比，不提供显著性推断；两臂差异仅作机制侧方向参考

