# Q-2 首次真实执行 quick-fail（零 LLM；runner 路径 bug）

- 时间：2026-10-18T04:18:49Z 附近（两臂 exit=2，总墙钟 ~15s）。
- 现象：runner 在 `cd <worktree>` 的子 shell 里仍使用**相对** `--out`（`experiments/results/...`），
  导致调用 `<worktree>/experiments/results/q_round_examples_ab_20261018/_helpers/limited_run.py`（不存在）→ python exit 2。
- **零 LLM 调用、零成本、无批次工件**；两个 arm 日志各 ~1.2KB，均为 "can't open file" 类错误。
- 修复：runner 启动前把 `ROOT/OUT` 规范化为**绝对路径**，并增加 import-source 预检（`experiments.__file__` 必须在 ROOT 下）。
- 本目录保留原始证据（logs/failed meta/sidecars/RUN_SUMMARY）；正式批在其后重跑。
