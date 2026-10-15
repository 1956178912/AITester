# 修复前冻结证据：synthetic gold 材料自洽性（2026-10-15 批次九）

> **性质**：O2 测量缺陷的**修复前冻结证据**（零 LLM）。
> **生成方式**：在**修复前代码**上重跑
> `experiments/emse_gold_conformance_audit.py`（`--skip-quixbugs`，
> `git stash` 暂存修复后重放，随后恢复）。逐任务记录见
> `GOLD_CONFORMANCE.json`。
> **权威叙述与影响量化**：见 `../emse_gold_conformance_20261015/README.md`。

## 结果（修复前）

| 集合 | n | pass | fail |
|---|---|---|---|
| synthetic seed 42 | 87 | 80 | 7 |
| synthetic seed 43 | 87 | 77 | 10 |
| synthetic seed 44 | 87 | 79 | 8 |
| **合计** | **261** | **236** | **25** |

- 25 个失败任务**全部**命中「模板残留 import」判别式
  （`stale_import_tasks`），失败签名为 `assertion_failure`
  （`test_no_builtin_shadow` 内 `import import45_shadow_builtin as m`
  ⇒ `ModuleNotFoundError`）；
- 失败分布与种子一致（7 / 10 / 8），即模板在三种子主批次中的出现
  次数（`import45_shadow_builtin` 属 Level 4.5 池，3 种子合计 25 次）。

## 复现（需修复前代码）

```bash
git stash push -- src/datasets/synthetic_dataset.py
AITESTER_QUIXBUGS_DATA=~/.cache/aitester/quixbugs \
  .venv/bin/python experiments/emse_gold_conformance_audit.py \
  --out experiments/results/emse_gold_conformance_pre_fix_20261015 --skip-quixbugs
git stash pop
```

（本目录即该命令的输出快照；SHA256SUMS.txt 锁定字节。）
