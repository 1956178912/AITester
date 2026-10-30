# G8 全开链路复测预注册（2026-10-30，数据产生前冻结）

> 授权：用户 2026-10-30「需要 LLM 的也可以跑」。
> 本文件在任何 G8 臂启动前落盘；判据冻结后取数，偏离须登记偏离表。
> 数据前置已闭合：SWE-bench Pro 数据落盘（default 642 + hard 51）+
> instance_code enrichment 172 条 ⇒ `check_swe_bench_pro_ready.py` 就绪 223/693
> （python 子集 237 中 ansible/openlibrary 大部分；js/go 超出本仓 Python
> 测试器范围，结构性不就绪——不是「未做」）。

## 设计（四开关全开 vs 历史默认关，同代码态）

- 臂 ON：`RUNTIME_PROBE_ENABLE / STRATEGY_BANK_ENABLE / EXPERT_POOL_ENABLE /
  CROSS_FILE_ENABLE` 全 true（runner 显式导出）；
- 臂 OFF：四开关全 false（同一次取数会话内先 OFF 后 ON，同代码态）；
- 数据：python 子集就绪任务；规模分层——冒烟 3 → 主批 30（--task-limit）；
  全量 223 待主批预算实读后决定（先测后推纪律）；
- 预算闸：任务级 COST_BUDGET_USD=1.0 / 批级 AITESTER_BATCH_MAX_USD=6.0。

## 主终点与判据

- 主终点：detection_rate（ON − OFF 配对差，bootstrap 95% CI）；
- H（方向验证）：ON ≥ OFF − 3pp（四开关不开倒车）；若 ON − OFF > +5pp
  ⇒ 支持「全开有真实收益」的后续默认值评审；ROPE ±3pp 内 ⇒ 记等价；
- 次要：token 成本 / LLM 调用数 / 崩溃率（runtime_probe 层不得引入
  harness_invalid）。

## 诚实条款

- 就绪 223/693 的构成必须披露（python-only 约束）；
- 判定基建侧：Pro 无 Docker，venv 复刻下 ansible 通路已被
  `swe_pro_judge_20261030` 实测（73/82 有判定）；openlibrary/qutebrowser
  的 collection_failed 实例**不进 G8 主批分母**（无观测 ≠ 0）；
- 单 seed 42、单模型 deepseek-flash 无 thinking；ON/OFF 同代码态
  （provenance git_sha 记录）。
