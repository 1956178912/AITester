# QuixBugs 全变异体 Mut@k（2026-10-15 批次八，零 LLM）

> **口径**：cosmic-ray 8.7.0，**全变异体（不截断，哨兵值 10⁹）**，
> `timeout=120s`（timeout 计 killed，ULT 官方）+ **健全性前置门**（生成测试须在
> QuixBugs fixed 上 30s 内终止且通过；未过门任务保守跳过并全额披露）。
> 配置哈希 `1e1230a7e298d1e2d7856ca437332e27702cfa1612dfc80ab71f9ca105b6ea22`。
>
> **取代关系**：本工件取代 `emse_quixbugs_mutk_20261014/`（截断面口径；
> 批次八勘误：截断面 = uuid4 随机序单次抽样，非确定性；且含恒红/挂死
> 套件的平凡击杀，系统性偏高）。

## 结果

| 口径 | 值 | 说明 |
|---|---|---|
| **全变异体·健全子集** | **0.9396（1182/1258）** | n=29/50 可测（30 过健全门，其中 `node` 无变异点） |
| 截断面·健全子集（对照） | 248/266 = 0.9323 | 随机 10 抽样 |
| 截断面·全部（历史值，标注"单次随机抽样"） | 443/461 = 0.9610 | 含 20 任务不健全套件的平凡击杀 |

**观察**：截断 10 抽样在 QuixBugs 上略偏保守（0.9323 vs 全量 0.9396，−0.7pp），
与 ULT 侧 next_holiday 的极端高估（0.40 vs 0.087）方向相反——小额随机样本的
偏差方向不可预知，进一步支持"全变异体"为定案口径。

## 未过门任务（20/50，详见 `emse_test_sanity_20261015/SANITY_AUDIT.json`）

- 收集错误 9（`*_test` 变体相对导入：`from .node import Node` 单模块物化必然失败）；
- 断言失败 8（恒红类，与 T-08 过红研究同源）；
- 非终止 3（bitcount / sqrt / wrap）；
- 另 `node` 任务过门但无有效变异点（skip 原因 = "无有效变异体结果"）。

## 复现

```bash
# 零 LLM：只读归档批次工件 + 本地 cosmic-ray 变异与 pytest 判定
python experiments/emse_quixbugs_mutk_full.py
# 健全性审计（前置门依据 + 披露证据）
python experiments/emse_test_sanity_audit.py
```

## 关联

- 脚本：`experiments/emse_quixbugs_mutk_full.py`（gitignored，无测试引用）；
- 审计：`experiments/results/emse_test_sanity_20261015/`；
- 叙事：`docs/design/emse_layered_narrative.md` §3（批次八修正版）。
