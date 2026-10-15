# ULT 全变异体 Mut@k（2026-10-15 批次八，零 LLM）

> **口径**：cosmic-ray 8.7.0，**全变异体（不截断，哨兵值 10⁹）**，
> `timeout=120s`（timeout 计 killed，ULT 官方）+ **健全性前置门**（测试须在
> 目标代码 `task_metadata.fixed`（ULT FUT）上 30s 内终止且通过；未过门任务
> 保守跳过并全额披露）。配置哈希
> `1e1230a7e298d1e2d7856ca437332e27702cfa1612dfc80ab71f9ca105b6ea22`。
>
> **取代关系**：本工件取代 `emse_ult_mutk_20261014/`（截断面口径；批次八
> 勘误：截断面 = uuid4 随机序单次抽样；归档"击杀"含大量恒红/挂死套件的
> 平凡信号，系统性偏高）。

## 结果（健全子集）

| 组 | n（健全/全部） | 全变异体 Mut@k |
|---|---|---|
| 生成测试·完整规格优先（specir 探针 25） | 5/25 | **0.4395（847/1927）** |
| 生成测试·纯 NL 规格优先（lite46 replace） | 9/46 | **0.6749（1590/2356）** |
| gold 官方测试（上界参照，探针 25） | **0/25** | —（25/25 `test_fails_on_fixed` 全跳过，pooled=None） |

**逐任务（replace）**：idx_for_diag_se_from_tr 0.850（181/213）/ initiate_board
0.824（70/85）/ convolution_size 0.946（318/336）/ circle_line_intersection
0.858（470/548）/ formatTime 0.878（79/90）/ BinaryFromFraction 0.479（152/317）
/ number_of_trees_bin_nt_partial 0.230（106/460）/ get_text_point_at_line
0.653（171/262）/ max_rewards 0.956（43/45）。

**逐任务（specir）**：x0x1_after_extraction 0.730（84/115）/ deg2HMS 0.469
（152/324）/ needleman_wunsch0 0.929（486/523）/ next_holiday **0.087
（80/920）** / max_rewards 1.0（45/45）。next_holiday 是**截断 10 样本极端
不代表性**的案例（截断健全 0.40 → 全量 0.087）。

## 对照与勘误（批次八）

| 口径 | specir | replace | gold |
|---|---|---|---|
| 全变异体·健全子集（本件） | **0.4395** | **0.6749** | —（n=0） |
| 截断面·健全子集（对照） | 0.64 | 0.7444 | 1.0（伪影） |
| 截断面·全部（历史，单次随机抽样） | 0.928 | 0.9543 | 1.0（伪影） |

- **gold 参照作废**：官方 `test_list` 在两个子集 **71/71** 任务上无法在
  `fixed` 通过（已排除包装/物化因素；`fixed` 与上游 `ULT_Lite.jsonl` 的
  `code` 逐字节一致）⇒「fixed = ULT 正确实现」假设不成立，归档 gold
  上界 1.0 系恒红套件的平凡击杀伪影；"距 gold 4–8pp"叙事作废。
- 官方协议对照（Ray/main.py 一手核对）：官方 `correct_tasks` 过滤
  = 套件在未变异代码上 green（本件健全性门的操作化来源）；官方 12 模型
  基线 Mut@k 均值 40.21%（量级对照，非严格同集比较）。
- 完整披露：`experiments/results/emse_test_sanity_20261015/`（121 gen
  + 71 gold 任务分类）。

## 未过门任务

gen 口径：lite46 37/46、probe25 20/25（收集错误 / 断言失败 / 非终止 /
函数名不一致四类，明细见审计工件与 README）。

## 复现

```bash
python experiments/emse_ult_mutk_full.py --groups replace --out experiments/results/emse_ult_mutk_full_20261015/MUTK_ULT_FULL_REPLACE.json
python experiments/emse_ult_mutk_full.py --groups specir,gold --out experiments/results/emse_ult_mutk_full_20261015/MUTK_ULT_FULL_SPECIR_GOLD.json
```

## 关联

- 脚本：`experiments/emse_ult_mutk_full.py`（gitignored，无测试引用）；
- 审计：`experiments/results/emse_test_sanity_20261015/`；
- 叙事：`docs/design/emse_layered_narrative.md` §3（批次八修正版）。
