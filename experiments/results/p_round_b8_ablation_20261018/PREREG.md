# PREREG（重跑声明）：B8 覆盖率停滞消融——DeepSeek 数据重建批

- 日期：2026-10-24（CI 轮补跑）
- 性质：**非历史预注册复现**——原 p_round_b8_ablation 批次工件随 2026-10-24
  「历史数据全清 + DeepSeek 重跑」用户指令删除；本 PREREG 是重跑批的新声明。
- 协议（与原批一致）：两臂并发；A=--enable-stagnation（COVERAGE_STALL_DETECT_ENABLE=true），
  B=--no-stagnation；任务数 10、parallelism 4、预算上限 $0.3。
- 判定（沿用原判据）：on 臂 stall 触发率应显著高于 off 臂（原批 10/10 vs 0/10，
  iterations 均值 off>on）；本批为 DeepSeek 单模型重建数据，**不与原批数字混合引用**。
- provenance：工作树携带 CA–CI 轮未提交改动（git_dirty=true 如实记录）；
  切点 HEAD=00e8c24d685bfff55e92b8a2a5b82e786ffc5103。
