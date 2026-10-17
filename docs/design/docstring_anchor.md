# docstring 独立规格锚设计说明（P1 / A-02）

> 立项日期：2026-10-17（L 轮）
> 状态：**已实装**（锚表构建器 + 两臂 + 分析脚本 + 预注册；正式跑批待 LLM 配额）
> 依据：独立评审报告 §6 P1（独立锚规格生成）+ §10 A-02（规格锚=缺陷代码再描述的
> 机制缺陷修复路径）。
> 关联：[spec_first.py](../../src/tools/spec_first.py)（提取/渲染）、
> [build_docstring_anchor_table.py](../../experiments/build_docstring_anchor_table.py)（零 LLM 锚表物化）、
> [emse_docstring_anchor_analysis.py](../../experiments/emse_docstring_anchor_analysis.py)（判定）、
> [run_benchmark.py](../../experiments/run_benchmark.py)（两臂注册）。
> 本文件为中文单语；`docs/design/` 不在双语门禁扫描面。

## 1. 背景：为什么需要"独立"锚

df_spec 臂（A-10）把 Generator prompt 的目标代码块替换为 Planner 计划子集
（signature + `logic_analysis`），预期切断 oracle-from-implementation。实测
**显著为负**：df_spec 54.3%（19/35）vs df 77.8%（28/36），δ=−25.7pp，双向
精确 p=0.0117（`experiments/results/emse_df_spec_20261016/`）。

机制假设（独立评审 §6 P1）：Planner 的 `logic_analysis` 是对**缺陷代码**的
再描述，约一半概率把缺陷行为固化成预期——这不是"独立规格"，而是
misguidance 的另一种载体（ISSTA'26 Zhao et al.；SpecOps'26 Tufano et al.）。

**修复路径（三级回退）**：

1. **(a) 人类 docstring**（独立于缺陷实现的人类规格源）；
2. **(b) 人类 docstring + Planner SpecExpr 子句并集**（保留形式化增益，
   但不让 Planner 再描述**替换**人类规格）；
3. **(c) 仅在 (a)(b) 均缺失时**沿用 Planner 再描述（现 df_spec 口径）。

本轮实装 (a)/(b) 两臂；QuixBugs 上 (c) 只作为 union 臂的 node.py 单例特例。

## 2. 数据事实：QuixBugs 的"尾部规格块"

QuixBugs 41 个缺陷程序**没有函数 docstring**，但 **40/41** 个程序文件尾部有
一个**顶层字符串字面量**——人类书写的规格块（`Input:` / `Output:` /
`Precondition:` / `Examples:`），例如 `bitcount.py` 末尾的 Bitcount 块。
只有 `node.py`（纯类定义）缺失。

`spec_first._docstring_of` 只取**函数 docstring**，取不到该块；因此新增
`module_spec_text(source_code)` 专门提取模块级人类规格。

## 3. 提取口径（`src/tools/spec_first.py::module_spec_text`）

纯 stdlib AST、零 LLM、确定性、无异常泄漏（解析失败返回 `""`）：

1. 只认**模块级** `Expr(Constant str)` 语句（函数/类内部的不算）；
2. 忽略 strip 后为空的字面量；
3. 存在"非首句"字面量（不是模块 docstring 的顶层字符串）时，取**最靠后**的
   一个（QuixBugs 尾部规格块语义；多处时取尾部）；
4. 否则回退**首句模块 docstring**；
5. 语法错误 / 空输入 / 无字面量 → `""`（调用方自行决定回退）。

验证口径（实测）：QuixBugs `python_programs/*.py`（排除 `_test.py`）41 个
程序中 **40 个**可提取人类规格（唯一缺失 `node`）。

## 4. 锚表（`experiments/build_docstring_anchor_table.py`）

零 LLM 从 QuixBugs 数据目录物化（默认 `data/quixbugs`，
`AITESTER_QUIXBUGS_DATA` 可覆盖）；**内容寻址**：`key = sha256(source.strip())`
（同源码同锚，免受 task_id/种子/路径漂移影响）。每条：

```json
{
  "function_name": "bitcount",
  "human_spec": "Bitcount\nbitcount\n\nInput: ...\nOutput: ...",
  "source_head": "def bitcount(n):",
  "source_len": 214,
  "human_spec_len": 182
}
```

- `function_name`：复用 `sole_top_level_function_name`（无歧义唯一顶层函数）；
  多函数模块（如 `shortest_path_length.py`）回退首个顶层函数（与数据加载器
  `suggested_function` 同口径）；无顶层函数（`node.py`）→ `""`。
- 覆盖统计写入表头 `meta`：`programs` / `human_spec_present` /
  `human_spec_missing_programs` / `function_name_present` 等（41/40 口径可
  从表头直接复算）。
- **确定性**：无时间戳；程序按文件名排序；两次运行输出**逐字节一致**。
- 缺数据目录 / 程序数不符 / union 的 Planner 表缺失 → **fail-fast 非零退出**
  并给清晰提示（不静默产出残缺锚表——"锚缺失静默回退"是 A1 假阴性类缺陷）。

两种模式：

| 模式 | 输出 | 内容 | P1 档 |
|---|---|---|---|
| 默认（doc） | `DOCSTRING_ANCHOR_TABLE.json` | 人类规格（node.py 空串条目） | (a) |
| `--union` | `DOCSTRING_ANCHOR_TABLE_UNION.json` | 人类规格 + 命中条目的 Planner `logic_analysis` | (b) |

默认落点 `experiments/results/emse_docstring_anchor_20261017/`；union 默认读
既有 Planner 锚表 `experiments/results/emse_spec_anchor_20261016/SPEC_ANCHOR_TABLE.json`
（`--planner-table` 可覆盖）。QuixBugs 实测：doc 40/41 有 human_spec；union
**41/41** 命中 Planner 子句（Planner 锚表对 QuixBugs 50 任务全覆盖）。

## 5. 渲染契约（`build_spec_replace_section`）

材料 dict **显式携带 `human_spec` 键**时：

- 键在场即进入材料判定（**空串也算材料**）——docstring 锚臂对"无人类规格"
  的任务（`node.py`）仍走替换口径，不会回落注入缺陷代码；
- 键值非空时渲染段落（位于函数签名之后、`【文档化契约（docstring）】`之前）：

```
【独立于实现的规格锚（人类 docstring）】
<human spec 原文>
```

- **未携带该键的材料（既有 df_spec/Planner 锚与全部历史臂）渲染结果逐字节
  不变**——`tests/test_docstring_anchor.py` 以金标记测试锁定（期望字符串固化
  字面量，防历史可复现性回归）。

## 6. 实验臂（`experiments/run_benchmark.py`）

| 臂 | 锚表（默认） | 材料 | P1 档 |
|---|---|---|---|
| `plain_llm_df_doc` | `DOCSTRING_ANCHOR_TABLE.json` | 人类规格 | (a) |
| `plain_llm_df_doc_union` | `DOCSTRING_ANCHOR_TABLE_UNION.json` | 人类规格 + Planner 子句 | (b) |

- 与 df_spec 臂同构：查表（`sha256(target_code.strip())`）→ 写
  `state["spec_anchor"]` → 线程覆盖 `DETECTION_SPEC_MODE=replace` → invoke →
  `finally` 复原；`--parallel` 下不串扰邻线程（线程局部覆盖，非 env）。
- `env DOC_ANCHOR_TABLE` 可覆盖两臂的锚表路径（测试/复跑用；已入批次
  provenance 的 `env_snapshot`）；正式跑批**不得设**——默认路径即预注册表。
- 表缺失/损坏/结构不符 → **逐任务回落 df 口径**（不写 `spec_anchor` →
  节点渲染空串 → `spec_replace_applied=attempted_fallback`），不 crash；
  命中率可从批次工件审计。
- **不得改变既有臂行为**：两臂为新增注册项；df_spec 与 df 路径/默认值未动。

## 7. 判定与分析

预注册件：`docs/study/DOCSTRING_ANCHOR_PREREG_2026-10-17.md`（本地件；
sha256 记录于跑批前 commit message）。分析脚本
[emse_docstring_anchor_analysis.py](../../experiments/emse_docstring_anchor_analysis.py)
锁定判定常量（`SUCCESS_LINE=0.65` / `FAIL_LINE=0.55` / `CONFIRM_P=0.05` /
`TREND_P=0.10`），三臂输入（`--df` 对照、`--doc` 处理 A、`--union` 次级可选），
输出 JSON（verdict/conditions/contrast/detection/audit）与 Markdown 摘要；
缺臂/行数或行集合异常/可判定配对为 0 → fail-closed 明确报错。

机制指标（misguided/effective 逐测试三分）由 T2 工具
`experiments/misguided_metrics.py` 独立产出（口径见
`docs/design/misguided_effective_metric.md`）；分析脚本只在报告中登记其
工件路径/sha256，**不以 over_red proxy 冒充机制结论**。

## 8. 已知限制

1. **union 不是纯独立锚**：Planner `logic_analysis` 仍是对 buggy 代码的再
   描述，union 若为负不能直接归因于人类锚；
2. **单数据集 / 单模型**：结论仅 QuixBugs + deepseek-flash；跨批波动与 MDE
   （n≈35、80% power ≈16.6pp）在预注册披露；
3. **node.py 无锚**：doc 臂该任务无锚文本（仍在 replace 口径，审计面以
   `attempted_replaced` 出现）；锚覆盖 40/41 是一等报告数；
4. **人类规格覆盖 ≠ 被违反条件覆盖**（SpecOps'26 的增益条件化结论）：
   人类规格块并不保证覆盖每条缺陷的触发条件——这是本路线的主要外部效度
   风险，需以 detection/misguided 实测判定，不得从"锚独立"直接推断"锚有效"。

## 9. 验证入口（零 LLM）

```bash
pytest tests/test_docstring_anchor.py tests/test_emse_docstring_anchor_analysis.py -q
python experiments/build_docstring_anchor_table.py            # doc 表（确定性）
python experiments/build_docstring_anchor_table.py --union    # union 表
```
