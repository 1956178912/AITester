# 多 seed 与原始 trace 实施方案（2026-11-27）

> **状态**：协议与命令已固化；**未执行任何新跑批**，因此不产生新结果、不改动稿件中的
> 任何数字或结论。执行需要 API 配额；执行完成后必须新建批次目录、重算 data pack，
> 并随下一次 Zenodo 版本发布。
>
> 当前稿件对这两项的处理是如实披露：单次执行、不估计 seed 级方差；归档不含原始
> trace 或模型转录。本文件只把“若作者决定补做，应当怎么做、如何验收”写成可执行步骤。

## 一、多 seed

### 1.1 现状（实测）

- 主批 `REPORT.json` 与全部 34 份 `benchmark_swebench_*.json` 的 `seed` 均为 **42**。
- `src/api/api_manager.py` 当前**没有把 seed 传入 LLM 请求**（2026-11-26 实测）；
  seed 只进入配置指纹与缓存命名空间。
- 因此当前实现下的“多 seed”实际是**同配置重复采样**，不是采样随机性扰动；
  在 temperature 0 下，差异主要来自 provider 侧非确定性。

### 1.2 两种可选方案

**方案 A：重复采样（不改代码，立即可跑）**

- 固定 `seed=42`，独立重复 3 次；每次使用独立缓存命名空间与独立输出目录。
- 目录命名：`experiments/results/test_run_<UTC时间戳>_rep1`、`_rep2`、`_rep3`。
- 用途：估计 run-to-run 方差；与现有单次结果对照，不替代主批。

**方案 B：真正的 seed 扰动（需改代码）**

- 先在 `src/api/api_manager.py` 增加 seed 透传（仅对支持的 provider 生效，
  不支持的 provider 保持现值并在 provenance 记录 `seed_forwarded=false`）。
- 再跑 `seed=42/43/44` 三组；每组独立缓存命名空间。
- 用途：区分“采样随机性”与“provider 漂移”；需要 provider 明确支持 seed。

### 1.3 命令模板

```bash
# 方案 A：重复采样（示例：QuixBugs 50 任务，单臂）
.venv/bin/python experiments/run_main_batch.py \
  --dataset quixbugs --task-count 50 --seed 42 --skip-stats \
  --baselines plain_llm

# 方案 B：seed 扰动（示例）
.venv/bin/python experiments/run_benchmark.py \
  --dataset quixbugs --task-limit 50 --seed 43 --baselines plain_llm
```

实际跑全网格时，按主批的 2 端点 × 5 臂 × 5 基准逐臂调用；每个批次必须在
`REPORT.json.provenance` 中记录 `seed`、缓存命名空间与模型指纹。

### 1.4 验收判据（执行后才适用）

1. 每个新批次的 `provenance.seed` 与目录名可区分，且 `git_dirty=false`。
2. 新批次进入 `RESULTS_DATA_PACK` 的 SOURCE_ROOTS 后，50 格齐全、`tasks_total`
   与主批逐格一致（筛选规则不变）。
3. 产出逐格差异表（pass / false-fix / tokens），并明确方差是否小于已报告的
   跨臂差异；若方差与跨臂差异同量级，稿件必须保留“排序未分辨”的表述。
4. 稿件只在新结果齐备后增加多 seed 表述；不得用旧的单 seed 数据冒充重复实验。

## 二、原始 trace

### 2.1 现状（实测）

- 批次结果行只保存 `task_id` 与聚合后的 `results`，**不含**模型请求/响应原文。
- `tmp_trace/` 共 240 个文件，内容是本地失败调试痕迹（`crash_task` 的节点事件），
  **不是**主批模型转录，不能作为论文的原始 trace 发布。
- `experiments/run_benchmark.py` 提供 `--save-state`，会把环节级状态
  （测试计划、生成代码、诊断、补丁）写入 `output_dir/raw/`；主批
  `provenance.save_state=false`，因此归档不含这些文件。
- 当前 R23 归档明确不含 raw execution traces / model transcripts；这一披露与
  `EXTERNAL_VERIFICATION`、`SUBMISSION.md` 一致。

### 2.2 采集方案

```bash
.venv/bin/python experiments/run_benchmark.py \
  --dataset quixbugs --task-limit 50 --seed 42 --baselines plain_llm \
  --save-state
```

- 每个 cell 使用独立输出目录；采集后用 JSONL/JSON 压缩，保留
  `task_id`、`node`、prompt、response、tool calls、时间戳与模型指纹。
- 采集批次必须与已报告配置一致（temperature 0、同一 fingerprint），否则只能作为
  新的补充实验，不能与主批混算。

### 2.3 脱敏与发布

发布前必须执行以下检查，任一失败即不得打包：

1. 删除 `Authorization`、`Cookie`、API key、provider 请求头、内网地址与家目录绝对路径。
2. 对手机号、邮箱、身份证等个人信息做正则扫描；命中即脱敏或删除整行。
3. 确认 trace 中无第三方 benchmark 的受限文本；只保留自有 prompt 与模型输出。
4. 记录文件级 SHA-256 与总大小；与代码、派生数据一起发布为**新的 Zenodo 版本**
   （当前 R23 不变）。
5. 同步更新 Data availability、Appendix A 与 `UPLOAD_GUIDE`；若 trace 体积过大，
   发布抽样清单与获取方式，不声称“完整 trace 已归档”。

### 2.4 验收判据（执行后才适用）

- 脱敏扫描 0 命中；抽样人工复核至少 20 条，确认无密钥/个人信息。
- 新版本归档的解包树可独立校验 SHA-256。
- 稿件只在新归档发布后改写“not in the deposit”相关句子；不得提前声称已归档。

## 三、当前边界

| 项 | 状态 |
|---|---|
| 225→217 筛选证据 | **已闭合**：8 个实例与两条原因写入正文 Appendix B，CLI `swebench-filter` 可复核 |
| 独立 CLI | **已实现**：`scripts/tools/paper_recompute.py`（`aggregate --check` / `swebench-filter` / `verify`） |
| 多 seed | **协议就绪，未执行**：需 API 配额；方案 A 可不改代码，方案 B 需 seed 透传 |
| 原始 trace | **协议就绪，未执行**：需 `--save-state` 重跑与新 Zenodo 版本 |
