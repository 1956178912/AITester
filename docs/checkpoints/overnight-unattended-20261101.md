# 过夜无人值守总控（2026-11-01 深夜）

## 背景与授权

用户指令：截图六项"没跑"清单过夜全部跑掉；超时跳过；无人重启；最终交付终端命令。
事实核查后分诊（机器可跑 vs 本质人工活）：

| 项 | 分诊 | 处置 |
|---|---|---|
| B3 完整读数（docker 298 份重判） | **可跑** | judge_b3_docker.py 第 154 行已改全直连（daocloud+清华源，零代理依赖），"固定端口代理"缺口已在代码层关闭；6 分片 manifest（minimal_gen/b3_s1..6.jsonl）+ instances（~/.cache/aitester/swe_bench/b3_enrich_shard*.jsonl）就位 |
| TGE 重判 | **可跑** | judge_tge_accuracy.py --manifest 就位（tge_aitester/tge_plain_llm_df.jsonl）；--py 仅作 venv 基座（/tmp 独立 venv），不污染主仓 |
| G8 full178 on 臂（正在跑） | **可续命** | 现有看护 LIMIT=150min（22:17 起，约 00:47 到限）；总控 wait_gone 接管后重拉，上限 3 次 |
| H1 三臂 + REF 臂（正在跑） | **可续命** | 同上；REF 臂 run_h1_ref_20261101.sh 幂等（RUN_SUMMARY.log REFUSE） |
| E7 人工裁决 / B5 段落目检 / 投稿动作 | 人工活 | 机器无法代办，明确不入无人值守清单 |
| G8 Docker per-instance（30 任务） | 无入口 | 无现成脚本；无人值守时段不现写不可验证代码，跳过 |
| N05/H1 原口径 | 已收口 | e8-2x2 checkpoint：δ=+27.78pp 判定已收，无需重跑 |

## 交付物

- 总控脚本：`experiments/overnight_20261101.sh`（bash 3.2 兼容；无 declare -A）
- 启动命令（用户终端前台 + 防睡眠）：`caffeinate -is bash experiments/overnight_20261101.sh`
- 产物目录：`experiments/results/overnight_20261101/`（OVERNIGHT_LOG.txt / OVERNIGHT_REPORT.md / 各 track 日志与判定 JSON）

## 脚本机制

- Phase 1（LLM 批）：G8 on 接管（wait_gone 等 `run_benchmark.py.*full178/on` 消失）∥ H1 接管（等 `run_payload_ab.py.*confirm-budget` 消失，实测当前有 **两个实例** 37010/55742 并发——现有看护重启击杀打偏所致，wait_gone 等两者全退）→ 缺臂重拉 → REF 幂等补跑
- Phase 2（判定批，CPU 释放后串行）：B3 docker 6 分片（3+3 两批，bash -c 内 wait，各批 deadline 130min）∥ TGE 2 臂（deadline 90min）
- guarded_run：deadline 击杀 + **zombie 检测**（ps stat= Z；否则快速失败命令会空等满 deadline）
- 收尾 OVERNIGHT_REPORT.md：各 track rc + 产物路径 + 未覆盖项披露

## 风险登记（设计内，非故障）

1. G8 批次预算闸 $10 fail-closed（预注册）：178 任务可能中途截断；重启即重置计数，重试上限 3 次/臂封顶 LLM 费用
2. run_benchmark.py 已有增量断点续跑（并发会话 23:09 提交 84899665，晚于本计划初稿）：重拉只补未完成任务，不再整批重来
3. H1 双实例并发写同臂目录（接管前既成事实）：臂产物可信度需明早以 run_payload_ab 自带 env_snapshot + SHA256SUMS 校验；总控重拉发生在两者全退之后
4. B3/TGE 超时被杀后残留判定进程靠脚本内 per-command timeout 自行收尾，残留 docker 容器无害
5. 判定批安排在 LLM 批之后：避免 Rosetta x86 pytest 与 G8/H1 执行超时（30s/任务）抢 CPU 污染正式读数

## 明早动作

1. 读 `experiments/results/overnight_20261101/OVERNIGHT_REPORT.md`
2. H1 臂产物 provenance 校验（双实例污染排查）
3. B3/TGE 若有产出 → 聚合进 JUDGE_REPORT（判定器并发互覆教训：同 out 文件禁止并发 --resume）
4. E7/B5/投稿仍待人工

## 2026-11-02 晨间核验（07:48-08:00）

**报告 rc 全部误导，逐项核验后真实状态**：
- G8 on：✅ 178/178 完成（INCREMENTAL 178 行；attempt1 23:33-00:25 增量跑完，attempt2/3 = 20s 汇总重放）
- H1 三臂：✅ 3/3 完成（env_snapshot x3 通过 + SHA256SUMS）；REF：✅ 完成（03:40 汇总落盘）
- B3：❌ 真失败（instances 误用 enrich 版缺 repo/base_commit → KeyError；正解 b3_shard*，与 manifest 300 全对齐实证）
- TGE：❌ 真失败（缺 --arm）
- G8 off：177/178，看护 attempt28 正常推进中（fp 在变）

**误判根因**：完成标志 RUN_SUMMARY.log 是增量模式前旧约定；84899665 后为 benchmark_*.json + INCREMENTAL_RESULTS.jsonl。总控脚本已完成标志+两处调用修正留档。bash 3.2 全角标点坑二次出现（line 242 G8_ATTEMPTS? unbound），`$var`+全角一律 `${var}` 已成铁律。

**白班补跑**：`experiments/daypatch_b3_tge_20261102.sh`——等 off 收尾（上限 90min）→ B3 6 分片（b3_shard* 合并 instances）3+3 → TGE 双臂（补 --arm）→ 产出 DAYPATCH_*.json。判定不烧 LLM。

## 2026-11-02 09:06 收官终态

- **G8 full178 两臂收官**：on 178/178（00:25 汇总落盘）+ off 177/178 + 1 skip（09:05 汇总落盘）。必卡任务 `instance_qutebrowser__qutebrowser-3e21c8214a99...` 经 `AITESTER_SKIP_TASK_IDS` 显式跳过（attempt29–33 五轮同点 stall、看护进度提取失效 ⇒ 交叉 skip 机制未触发，手动兜底），偏离表 D2 已登记。
- **在跑**：daypatch 判定批（TGE 双臂正常；B3 旧版判定器报废批——markers 嵌套引号断裂，s2 50/50 env_error 实证）；relay（新版）等 daypatch 结束 → B3 v2 六分片重判 → G8 门禁 178 全量。
- **文档面**：CHANGELOG 双语门面换新批次（旧 128 行原文归档 docs/history/CHANGELOG_2026-11-02_batches(.en).md）、prereg 偏离表 D2、本 checkpoint 三节。
- **待 relay 产出**：V2_B3_DOCKER_s1..6.json（B3 精确读数）、G8_GATE_DOCKER_{ansible,qutebrowser,openlibrary}.json（真实 effective 分母）。聚合与两臂对比分析在产出后进行。
