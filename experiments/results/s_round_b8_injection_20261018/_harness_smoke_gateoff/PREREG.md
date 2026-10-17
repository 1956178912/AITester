# S-2 harness 冒烟 2：gate-off 可达性验证（非主判定；2026-10-18）

目的：验证 `PATCH_EVIDENCE_GATE_ENABLE=false`（两臂同设）解除 repair_invalid
抢占后，停滞判据是否可达且 ON 臂相对 OFF 臂真正省迭代。
- on / off 各 2 任务（seed 42、fast、inject-rounds 3、两臂并发）。
- 预期（机制）：on 臂 iter=2 触发 coverage_stall；off 臂继续到 iter=3（真实执行轮）。
- 不计入主判定/预算，结果在主 README 披露。
