# Q-3 smoke：批后处理墙钟可观测（构造数据）

> 目录日期：2026-10-18。**非真实批次工件**：本目录仅演示
> `experiments/postprocess_wall.py::build_postprocess_wall` 的稳定 JSON 形状与
> 告警输出，输入为**手工构造**的逐任务耗时（见下），不代表任何实验数字。

## 生成方式（确定性，零网络/零 LLM）

逐任务耗时（秒，构造值）：

| stage | durations | timed_out_tasks |
|---|---|---|
| mutation | 0.42, 0.51, 0.38, 0.47, 12.0 | 1 |
| m1 | 0.03, 0.05, 0.04, 0.02 | 0 |
| mdo | 1.2, 0.9, 740.0 | 0 |
| other | （无任务） | 0 |

调用：

```python
from experiments.postprocess_wall import build_postprocess_wall, postprocess_warn_s

wall = build_postprocess_wall(
    {
        "mutation": [0.42, 0.51, 0.38, 0.47, 12.0],
        "m1": [0.03, 0.05, 0.04, 0.02],
        "mdo": [1.2, 0.9, 740.0],
        "other": [],
    },
    timed_out={"mutation": 1, "m1": 0, "mdo": 0, "other": 0},
    warn_s=postprocess_warn_s(),  # env AITESTER_POSTPROCESS_WARN_S，默认 600
)
```

`smoke_postprocess_wall.json` 中：

- `postprocess_wall`：稳定形状（每阶段 `wall_s/n_tasks/mean_s/p50_s/p95_s/max_s/timed_out_tasks`）；
- `derived_warnings`：阈值告警示例（mdo 阶段 742.1s > 600s；真实 hook 会由调用方
  `logger.warning` 逐条输出，不写入批次 JSON）；
- `warn_s`：生效阈值（默认 600；env 覆盖仅影响告警判定，不影响统计字段）。

## 完整性

`SHA256SUMS` 由 `scripts/gates/checksum_results.py --write` 生成，可
`--verify` 校验。本目录在 `experiments/results/**`（gitignored）下，如需随
commit 归档需 Lead `git add -f`。
