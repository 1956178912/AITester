# E8 单格预注册（自 docs/preregistration.md §E8 提取，2026-10-28 授权执行）

状态：FROZEN（判据与设计自 2026-10-18 E8 amendment 冻结，本文件只做格级
落盘与执行披露，不改任何判定规则；用户已于 2026-10-28 授权 LLM 配额）。

## 设计（冻结，摘自预注册原文）

- 2×2 = {`LLM_THINKING_MODE` on/off} × {R-P0-2 切点 `b533cff1c316e8e80db635a1b2946610b211a5b6`
  legacy profile, T 轮切点 `a93c1f60ee31b9582e0146f73e3038e6ce0f01a1` current profile}；
- 臂 = {aitester, plain_llm, plain_llm_df}；synthetic n=87 × 1 seed（42）起步，
  显著不明确时扩 seed {44}；`TEMPERATURE=0`、冷缓存（`AITESTER_LLM_CACHE=0`）、
  干净 worktree、`model_fingerprint.pinned=true`、逐 seed 硬门槛
  （干净树/指纹/87 行/exit=0/task 集一致）；
- legacy profile 格的取得方式：`git worktree add` 至 `b533cff1` 后执行
  （该切点无 `LLM_THINKING_MODE` 开关，其"默认推理模式"即 on 格口径），
  provenance 记 `git_sha`；current profile 格用 `a93c1f60` 同口径。

## 执行披露（2026-10-28，数据产出前落盘）

1. **legacy-off 格结构性不可得**：`git grep LLM_THINKING_MODE b533cff1 -- '*.py'`
   零命中——legacy 切点代码不读取该环境变量，请求体不带 thinking 参数，
   DeepSeek API 默认思考开启，即 legacy 列只有 on 格口径。本批只执行
   **legacy-on / current-on / current-off 三格**；legacy-off 缺格对 H1
   （"四格中 δ 均为负"）判定的影响在统计报告如实披露，不得以三格冒充四格。
2. **legacy 切点 CLI 差异**：`run_main_batch.py`@b533cff1 无
   `--max-pattern-repeat` / `--staging-dir` 参数，legacy 格命令不含两者；
   任务数均显式 `--task-count 87`，与预注册 n=87 一致。
3. **格预算上界**（价目表峰时上界，in_share=0.76 同 S-1/R-1 口径）：
   off 格 REF_TOKENS=3,200,000 → ≈$1.65；on 格 REF_TOKENS=7,000,000 →
   ≈$3.61；三格合计 ≈$8.9（预注册预估 $6–9 内）。dry-run/首格实测后按
   预注册条款修正（修正只改预算、不改判定，本披露即数据产出前的修订落盘）。

## 主终点与判定（冻结，摘自预注册原文）

- 主终点：格内 `aitester` vs `plain_llm_df` 的 detection 配对差 δ
  （McNemar 精确 + bootstrap CI + 贝叶斯 ROPE ±5pp；BH-FDR 校正族 = 四格主对比）。
- H1（推理模式不变式）：四格中 `aitester − df` 均为负且 95% CI 全负
  → 核心阴性稳健于推理模式与协议开关；
- H2（模式依赖）：任一格 δ 转正且 CI 不含 0 → 核心阴性仅在特定推理模式下成立；
- H3（漂移归因）：plain_llm 臂四格方差 > 两个处理臂的格间方差
  → 次级排序漂移主要来自基线臂全局漂移而非协议开关；
- 混合结果 → 按主导格如实报告，禁止挑选性引格。

## 停止规则（冻结）

一次性 2×2（三格可跑 + legacy-off 缺格披露），无迭代条款；任格硬门槛
失败该格作废并披露（不得以其余格补位声称"全格通过"）。
预算授权门槛：用户 2026-10-28 已授权。
