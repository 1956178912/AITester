# E7 候选客观证据预筛（零 LLM，**非判定**）

> **本文件不是判定结果**，只把机械可算的事实提前列好，供人工裁决时对照。
> 预注册的五选一口径不变；`equivalent` 仍须人工确认语义。
> 输出顺序与 `e7_review_worksheet_n72.md` 完全一致，便于交叉核对。

- 候选总数：72
- AST 结构等价（去 docstring/注释后逐节点相同）：**15**（20.8%）
- 差异仅注释/空行：**14**（19.4%）

> gold 取值口径：单文件任务取 `task_metadata.fixed`，跨文件任务（`is_cross_file=True`）取 `task_metadata.fixed_module_code`——后者的 `fixed` 字段为空，只读 `fixed` 会把取错字段误报成素材缺失。

## 如何读这三列

| 列 | 含义 | 使用建议 |
|---|---|---|
| AST 结构等价 | 两份代码去掉 docstring/注释后，AST 逐节点相同 | 语法层结构相同，**不是**语义判定——仍需确认运行时行为（导入、全局状态、装饰器） |
| 差异行数 | unified diff 的增删行数 | 0 = 逐行相同；越大越需要逐行看 |
| 差异仅注释/空行 | 所有差异是否都是 `#` 注释或空行 | 是 → 语义极可能相同，但仍须人工确认 |
| 素材缺失 | patch / gold 哪一侧为空 | 非「—」→ 该行**无可比对素材**，差异两列同时记「—」，不得读成「有差异」 |

## 逐条证据

| # | task_id | AST 结构等价 | 差异行数 | 差异仅注释/空行 | 素材缺失 |
|---|---|---|---|---|---|
| 1 | s42__synthetic__task_0044 | 有差异 | 7 | 否 | — |
| 2 | s42__synthetic__task_0013 | 有差异 | 3 | 否 | — |
| 3 | s43__synthetic__task_0028 | 有差异 | 23 | 否 | — |
| 4 | s43__synthetic__task_0022 | 有差异 | 3 | 否 | — |
| 5 | s43__synthetic__task_0005 | 有差异 | 3 | 否 | — |
| 6 | s42__synthetic__task_0055 | 有差异 | 5 | 否 | — |
| 7 | s42__synthetic__task_0043 | 有差异 | 14 | 否 | — |
| 8 | s42__synthetic__task_0036 | 有差异 | 12 | 否 | — |
| 9 | s44__synthetic__task_0008 | **结构等价** | 1 | 是 | — |
| 10 | s42__synthetic__task_0012 | 有差异 | 9 | 否 | — |
| 11 | s42__synthetic__task_0006 | 有差异 | 3 | 否 | — |
| 12 | s42__synthetic__task_0018 | 有差异 | 5 | 否 | — |
| 13 | s44__synthetic__task_0050 | 有差异 | 10 | 否 | — |
| 14 | s44__synthetic__task_0082 | **结构等价** | 1 | 是 | — |
| 15 | s43__synthetic__task_0023 | 有差异 | 5 | 否 | — |
| 16 | s43__synthetic__task_0052 | 有差异 | 10 | 否 | — |
| 17 | s44__synthetic__task_0039 | 有差异 | 12 | 否 | — |
| 18 | s44__synthetic__task_0067 | 有差异 | 5 | 否 | — |
| 19 | s42__synthetic__task_0037 | 有差异 | 17 | 否 | — |
| 20 | s43__synthetic__task_0070 | 有差异 | 10 | 否 | — |
| 21 | s43__synthetic__task_0059 | **结构等价** | 1 | 是 | — |
| 22 | s43__synthetic__task_0067 | **结构等价** | 1 | 是 | — |
| 23 | s43__synthetic__task_0027 | 有差异 | 13 | 否 | — |
| 24 | s42__synthetic__task_0084 | **结构等价** | 1 | 是 | — |
| 25 | s44__synthetic__task_0031 | 有差异 | 9 | 否 | — |
| 26 | s44__synthetic__task_0058 | 有差异 | 6 | 否 | — |
| 27 | s43__synthetic__task_0043 | **结构等价** | 7 | 否 | — |
| 28 | s44__synthetic__task_0053 | 有差异 | 3 | 否 | — |
| 29 | s42__synthetic__task_0005 | 有差异 | 20 | 否 | — |
| 30 | s42__synthetic__task_0035 | 有差异 | 5 | 否 | — |
| 31 | s43__synthetic__task_0002 | 有差异 | 4 | 否 | — |
| 32 | s42__synthetic__task_0068 | 有差异 | 20 | 否 | — |
| 33 | s43__synthetic__task_0080 | 有差异 | 5 | 否 | — |
| 34 | s42__synthetic__task_0033 | **结构等价** | 1 | 是 | — |
| 35 | s44__synthetic__task_0034 | 有差异 | 11 | 否 | — |
| 36 | s43__synthetic__task_0058 | 有差异 | 9 | 否 | — |
| 37 | s42__synthetic__task_0020 | 有差异 | 9 | 否 | — |
| 38 | s44__synthetic__task_0036 | 有差异 | 8 | 否 | — |
| 39 | s42__synthetic__task_0078 | 有差异 | 6 | 否 | — |
| 40 | s44__synthetic__task_0047 | 有差异 | 11 | 否 | — |
| 41 | s42__synthetic__task_0069 | **结构等价** | 1 | 是 | — |
| 42 | s43__synthetic__task_0082 | **结构等价** | 2 | 是 | — |
| 43 | s44__synthetic__task_0048 | 有差异 | 10 | 否 | — |
| 44 | s42__synthetic__task_0058 | 有差异 | 21 | 否 | — |
| 45 | s42__synthetic__task_0028 | **结构等价** | 2 | 是 | — |
| 46 | s42__synthetic__task_0081 | **结构等价** | 2 | 是 | — |
| 47 | s44__synthetic__task_0013 | 有差异 | 5 | 否 | — |
| 48 | s42__synthetic__task_0075 | 有差异 | 4 | 否 | — |
| 49 | s43__synthetic__task_0075 | 有差异 | 3 | 否 | — |
| 50 | s43__synthetic__task_0054 | 有差异 | 5 | 否 | — |
| 51 | s44__synthetic__task_0077 | 有差异 | 3 | 否 | — |
| 52 | s44__synthetic__task_0006 | 有差异 | 36 | 否 | — |
| 53 | s44__synthetic__task_0044 | 有差异 | 13 | 否 | — |
| 54 | s44__synthetic__task_0059 | 有差异 | 22 | 否 | — |
| 55 | s44__synthetic__task_0019 | 有差异 | 15 | 否 | — |
| 56 | s43__synthetic__task_0010 | **结构等价** | 3 | 是 | — |
| 57 | s44__synthetic__task_0026 | **结构等价** | 1 | 是 | — |
| 58 | s42__synthetic__task_0053 | 有差异 | 11 | 否 | — |
| 59 | s43__synthetic__task_0077 | 有差异 | 13 | 否 | — |
| 60 | s43__synthetic__task_0063 | 有差异 | 6 | 否 | — |
| 61 | s43__synthetic__task_0060 | 有差异 | 4 | 否 | — |
| 62 | s43__synthetic__task_0035 | **结构等价** | 1 | 是 | — |
| 63 | s42__synthetic__task_0014 | 有差异 | 5 | 否 | — |
| 64 | s44__synthetic__task_0004 | 有差异 | 9 | 否 | — |
| 65 | s43__synthetic__task_0026 | **结构等价** | 1 | 是 | — |
| 66 | s42__synthetic__task_0048 | 有差异 | 10 | 否 | — |
| 67 | s42__synthetic__task_0062 | 有差异 | 4 | 否 | — |
| 68 | s42__synthetic__task_0024 | 有差异 | 17 | 否 | — |
| 69 | s43__synthetic__task_0073 | 有差异 | 18 | 否 | — |
| 70 | s43__synthetic__task_0018 | 有差异 | 5 | 否 | — |
| 71 | s42__synthetic__task_0057 | 有差异 | 6 | 否 | — |
| 72 | s43__synthetic__task_0078 | 有差异 | 21 | 否 | — |

## 复核完成后

把每行判定回填 `e7_repair_sample_candidates_n72.md` 的「人工判定」列，按预注册
判定规则更新 `docs/preregistration.md` 执行记录表 E7 行，并追记全局决策日志。

**若确认的出现 equivalent ≥ 1**：E7 判定规则要求勘误 repair 口径并给出修正后
上界（原「repair=0 为真零」表述不再成立）。
