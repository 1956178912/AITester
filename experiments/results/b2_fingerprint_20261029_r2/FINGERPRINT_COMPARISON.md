# B2 指纹对比判定（2026-11-01，零 LLM 收口）

> 判据（预注册 `PREREG.md` §判定 冻结口径）：新批 system_fingerprint 与 T 轮批
> `t_round_b2_main_batch_20261018` 记录对比——一致 ⇒ 快照漂移假说否定；不一致 ⇒ 实锤。
> 本文是该判据的执行记录与判定落盘。

## 指纹时间线（同一探针输入 probe_sha256=fc3d9159…efda3）

| 时间点（probe_at） | 来源工件 | system_fingerprint |
|---|---|---|
| 2026-10-18（T 轮 B2 三 seed） | `t_round_b2_main_batch_20261018/` | **不可得**（工件 2026-10-24 撤回，BASELINE.yaml@da100d59 只登记 "pinned=true / system_fingerprint 齐全" 未记值；云会话检索零命中） |
| 2026-10-24T10:08:48Z | `experiments/results/e2e_probe_llm_latest.json`（observability-model-fingerprint 探针） | **e72d3c7f663d3e1383b00b3884cb4501** |
| 2026-10-28T11:41:03Z | `e8_2x2_20261028/current-off/seed42/benchmark_synthetic_20261028_194104.json` | **bc19ba97cbe016479903222bb1578db6** |
| 2026-10-28T15:21:13Z | `e8_2x2_20261028/current-on/seed42/benchmark_synthetic_20261028_232114.json` | bc19ba97…（同上） |
| 2026-10-29T06:12:52Z | `b2_fingerprint_20261029/seed42/…141253.json` | bc19ba97…（同上） |
| 2026-10-29（B2 r2 seed43/44） | `b2_fingerprint_20261029_r2/seed43/…170735.json`、`seed44/…181956.json` | bc19ba97…（同上） |

## 判定

1. **快照漂移实锤（新增事实，非假说）**：10-24 → 10-28 窗口内，同一探针输入的
   system_fingerprint 由 `e72d3c7f…` 变为 `bc19ba97…`。别名 `deepseek-flash`
   的服务端快照在该窗口内发生变化——"同别名快照漂移"（S29 风险）由风险条目
   升级为已观测事实。
2. **T 轮对比半边：inconclusive（结构性不可得）**。T 轮指纹具体值随工件撤回
   一并不可得（撤回登记 `docs/study/WITHDRAWN_ARTIFACTS_2026-10-24.md` 行
   "t_round_b2_main_batch_20261018：未复刻（论文标 historical）"）。按诚实条款
   记"不可判定"，不读作"一致"也不读作"不一致"。
3. **新批内部一致**：B2 三 seed（含 r1 seed42 与 r2 seed43/44）全部
   bc19ba97… / pinned=true——E8（10-28）与 B2（10-29）全程单快照，**新批
   之间互比有效**；与 T 轮 / R-P0-2 旧批的既有口径隔离纪律维持。
4. **漂移归因分解（PREREG 第二问）**：双因素均已观测——
   - 快照漂移：本判定项 1（10-24→10-28 实锤；E8 legacy-on 复现失败 10-28
     发生在变化窗口之后的 bc19ba97 快照上，时间吻合）；
   - 任务集漂移：E8-legacy-on 与 R-P0-2 原批内容三元组哈希命中率 3/15
     （checkpoint 2026-10-29 中午节，已登记）。
   - 推理模式漂移（补充证据，非本判据）：T 轮 token 证据 output 占比
     78.6%→36.4%（BASELINE.yaml@da100d59 drift_findings）。
   T 轮 `not_reproduced` 与 E8 legacy 复现失败的归因 = 快照漂移 × 任务集漂移
   × 推理模式混合；**"仅归因模型侧、harness 侧排除"的强表述不成立**（任务集
   漂移是 harness 侧已观测因素），按登记册 §E8 核心发现的修正表述为准。

## 对稿件引用的约束

- 新批读数（E8 三格、B2 三 seed、ULT 全量、TGE、C8/TGE 扩样判定）引用时
  标注 `system_fingerprint=bc19ba97…（2026-10-28 起单快照）`。
- 与 R-P0-2 / T 轮旧批并列时必须带批名与协议版本（既有纪律，不变）。
- T 轮对比缺口如实披露："T 轮指纹值随工件撤回不可得，T 轮↔新批快照同一性
  不可判定；10-24→10-28 窗口已实锤一次快照变化。"

## 复算命令

```bash
python3 - <<'EOF'
import json
for p, label in [
    ("experiments/results/e2e_probe_llm_latest.json", "10-24 probe"),
    ("experiments/results/e8_2x2_20261028/current-off/seed42/benchmark_synthetic_20261028_194104.json", "10-28 E8"),
    ("experiments/results/b2_fingerprint_20261029_r2/seed44/benchmark_synthetic_20261029_181956.json", "10-29 B2"),
]:
    d = json.load(open(p))
    fp = d.get("probes", [{}]) if "probes" in d else [d.get("provenance", {}).get("model_fingerprint", {})]
    if isinstance(fp, list):
        fp = [x.get("fingerprint", x) for x in fp if x.get("name") == "observability-model-fingerprint"] or fp
    print(label, json.dumps(fp, ensure_ascii=False)[:200])
EOF
```
