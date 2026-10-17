# 事故记录：零 LLM 阻断自测误启动真实 LLM 批（2026-10-18）

> **性质：流程事故记录（非 Q-2 研究数据）**。本目录工件**禁止**作为任何研究证据引用；仅用于审计与根因复盘。

## 时间线与事实

| 时间（UTC+8） | 事件 |
|---|---|
| 04:08 | 首次 dry-run 带 `--require-clean-root` → 主树 dirty（其他队友 P-1/Q-1 在途）被正确阻断（exit 2）。 |
| 04:10 | 二次 dry-run（不带 clean 门）→ 通过；当时 `feature_present=false`（Q-1 接线尚未见于 `run_benchmark.py`），仅 warning。 |
| 04:10:12 | **我的错误**：为验证"真实模式在 feature 缺失时应阻断"，在 `/tmp/q2_block_test` 用真实模式重跑（未带 clean 门）。此时 Q-1 队友的并发编辑已把 `SPEC_ORACLE_EXAMPLES_ENABLE`/行字段写入 `experiments/run_benchmark.py` → `feature_present=true` → 预检通过 → **两臂真实 LLM 被启动**。 |
| 04:14 | 发现命令长时间未返回；立即 `job_kill` + 按 pid 文件 SIGTERM 两个进程组，终止两臂。**无批次 JSON 产出**；无残留进程/孤儿（巡检 0）。 |
| 04:15 | 复制证据到本目录（两臂 logs/traces/PREFLIGHT）。 |

## 根因（三层，全部记入加固）

1. **直接触发**：验证"应阻断"用的却是**真实执行模式**（而非"只跑预检"模式），且未加 `--require-clean-root`——主树 dirty 时本应被拒。
2. **并发竞态**：主树同时被 Q-1 队友编辑，`experiments/run_benchmark.py` 在我的两次检查之间从"无接线"变为"有接线"，使预检从"应阻断"翻转为"通过"（TOCTOU：check 与 launch 之间的时间窗）。
3. **守卫缺口**：runner 缺少 (a) 真实模式强制 clean-root；(b) 预注册"未冻结（DRAFT/占位符）"阻断；(c) `--preflight-only` 安全自测模式；(d) preflight→launch 之间的文件 sha256 复核。

## 损害评估（诚实）

- **LLM 花费不可精确记账**（无批次 JSON）；按两臂已发生的调用节点估算：control ~68 次、examples ~67 次；按历史 aitester/logic QuixBugs 批次均值 ~2.6k tokens/call → 合计 ≈35 万 tokens；
  按 deepseek-flash 价目（in 0.72/out 0.28 分摊）≈ **$0.15–0.20**（粗估，非精确）。这笔花费属 Q-2 预算外损耗，将由 Lead 决定是否影响 Q-2 预算/是否继续。
- **无研究数据产生**：无批次 JSON、无 meta、无 SHA；logs/traces 仅存本目录供审计，**不得引用**。
- **对 Q-2 设计/切点无影响**：错误批次跑在主树（dirty、未冻结切点），与 Q-1 切点后正式批无关；两臂已被杀、无孤儿。
- **对仓库无写入影响**：arms 的 staging/trace 均在 `/tmp`；主树 dirty 行数变化来自其他队友在途编辑，非本事故。

## 加固（已在 runner 中落实，见 `experiments/run_q_examples_ab.sh`）

1. 真实模式**强制要求 ROOT dirty=0**（不依赖调用者记得加 `--require-clean-root`；dirty 即 exit 2）。
2. 新增 `--preflight-only`：只跑零 LLM 预检并落盘 `PREFLIGHT.json`，**绝不 launch**；零 LLM 阻断自测必须用它。
3. 真实模式要求 `PREREG.md` **已冻结**（不得含 `DRAFT`/`<Q-1 … sha>` 占位符），且其 sha256 记入 PREFLIGHT。
4. preflight→launch **TOCTOU 守卫**：记录 `run_benchmark.py`/`planner.py` 的 sha256，launch 前复核；变化即中止并要求重跑预检。
5. 未来零 LLM 阻断测试在**独立临时仓库副本**（含/不含 feature 标记各一份）里跑，不再对活的主树用真实模式。

## 证据清单

- `PREFLIGHT.json`：误启动时的预检（`feature_present=true`、`blocking=[]`）。
- `log_control.log` / `log_examples.log`：两臂 ~4min 日志（无最终摘要）。
- `traces_control/`（15 task trace）/ `traces_examples/`（18 task trace）。
