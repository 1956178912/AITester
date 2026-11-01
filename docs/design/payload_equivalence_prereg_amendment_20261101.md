# H1 载荷等价重跑——预注册修订（2026-11-01，用户授权）

> 状态：FROZEN（跑前落盘）。原预注册：`payload_equivalence_prereg.md`（判据不变部分继续有效）。
> 授权：用户 2026-11-01"这三可以执行"+"授权重跑（约 $5-8）"。

## 修订动机

首轮 H1（`experiments/results/e3_h1_payload/`，36 配对任务）配对差 δ=+27.78pp
显著，但操纵检查判 **不可判定**：assay sensitivity 未建立——外部参照
`df_stored` 存量工件已清除（仅存记录值 31/41 = 75.6%），与新批 arm 检出率
差 13.29pp，assay 无法区分"载荷等价"与"参照基线漂移"。

## 修订内容（冻结）

1. **REF 臂重建**：在当前快照（system_fingerprint=bc19ba97…）重跑 REF 臂——
   `plain_llm_df` 单臂、quixbugs 50 任务、seed 42、温度 0、冷缓存，与三臂
   同任务集同协议。原"REF 引用存量工件（§3.4）"条款废止（工件已清除）。
2. **assay sensitivity 判据（冻结）**：REF 臂与臂②（`p_df_parity__o_mono`，
   同为 df 载荷、无编排路径）的配对检出率差 **|δ_ref| ≤ 10pp** ⇒ assay
   敏感度建立，H1 主检验可判；否则维持"不可判定"（如实披露，不计 0）。
3. **主检验判据不变**：臂① vs 臂③ 配对差（载荷等价检验），McNemar + bootstrap
   CI + ROPE ±5pp，None 行剔除不计 0（§3.1 原文）。
4. **快照披露**：全部四批同快照（bc19ba97…），与首轮（跨快照）读数不混池、
   不并列；首轮结果保留为历史。
5. **预算**：50 任务 × 4 臂，任务级 cap 不变（200k tok / $1.0），批次闸 $3
   （fail-closed）。实测外推 ≈ $1.2。

## 执行入口

- REF 臂：`experiments/run_h1_ref_20261101.sh`（本修订配套，幂等、干净树强制）
- 三臂：`experiments/run_payload_ab.py --confirm-budget --out-dir experiments/results/e3_h1_payload_r2`
- 分析：四批落盘后按本修订判据出 `H1_STATISTICAL_REPORT_R2.md`

## 偏离表

| # | 原文 | 实际 | 影响 |
|---|---|---|---|
| A1 | §3.4 REF 引用存量工件 | REF 工件已清除，改为当前快照重跑 | REF 读数含义从"历史外部参照"变为"同快照参照"，assay 判据随之冻结为 ≤10pp |
| A2 | 首轮三臂结果 | 保留为历史，重跑四批不混池 | 跨批对比仅限定性方向描述 |
