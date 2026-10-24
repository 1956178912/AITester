# M-4 prompt 增广核验（LLM 缓存证据，脚本抽取）

> 目的：证明 augment 臂的 Generator prompt **同时包含目标缺陷代码块与人类规格锚段落**
> （M-1 处理有效性的一等证据）。数据来源 = `~/.cache/aitester/llm/*.json` 中批次时间窗内
> 的 generator 调用缓存。

> **判据澄清（重要）**：QuixBugs 的人类规格文本就是缺陷源码文件尾部的模块级 docstring，
> 因此「规格文本出现」**不能**单独证明增广注入（df 对照臂代码块内也含该文本）。
> 本证据以 **M-1 augment framing 段**为决定性判据：代码标记 < framing 标记 < 规格锚末次出现，
> 且 `spec_marker_occurrences` 记录该文本出现次数（源码内嵌 vs 增广段重复注入）。

## 计数

- 时间窗：`2026-10-24T15:30:02Z` → `2026-10-24T16:38:56Z`
- generator 缓存条目数（时间窗内）：**110**
- augment framing 命中（= augment 臂）：**43**
- 含代码块但无 framing 段（= df 对照臂，负向对照）：**44**
- framing 标记：`【规格增广模式（Spec-Augment）：规格锚与目标代码并列】`
- 证据状态：**ok**；负向对照在场：**True**

## 样例（1–2 例）

### 例 1：`knapsack`

- 缓存文件：`0495c2b4370cfeda.json`（sha256 `51883c6f4199936c…`）
- 缓存时间：`2026-10-24T15:32:31Z`
- prompt 长度：2301；代码标记 offset=29；augment framing offset=1097；规格锚出现次数=2；末次出现=1415；增广段小节标题在场=True

```text
ck(100, [(60, 10), (50, 8), (20, 4), (20, 4), (8, 3), (3, 2)])
    19
"""

```

【规格增广模式（Spec-Augment）：规格锚与目标代码并列】
上方已完整给出目标代码；以下并列追加同一函数的人类独立规格锚（独立于缺陷实现书写）。
请结合两者：当实现与规格不一致时，按规格构造期望值（这是检出缺陷的关键）。
不得仅凭当前实现的实际行为推断期望值——那会把缺陷固化成预期（oracle-from-implementation），系统性抹掉检出。

函数签名：def knapsack(capacity, items)
被测模块名：knapsack（import 必须 `from knapsack import ...`）

【独立于实现的规格锚（人类 docstring）】
Knapsack
knapsack

You have a knapsack that can hold a maximum weight. You are given a selection of items, each with a weight and a value. You may
choose to take or leave each item, but you must choose items whose total weight does not exceed the capacity of your knapsack.

Input:
    capacity: Max weight the knapsack can hold, an int
    items: The items to choose from, a list of (weight, value) pairs

Output:
    The maximum total value of any combination of items that the knapsack can hold

Example:
    >>> knapsack(100, [(60, 10), (50, 8), (20, 4), (20, 4), (8, 3), (3, 2)])
    19

【生成纪律（增广模式）】
1. 人类规格 / docstring 明确覆盖的行为，必须按规格断言——不得以当前实现的实际行为作为期望值；
2. 规格与实现不一致处即为嫌疑缺陷：按规格推导正确结果并断言（这是检出缺陷的关键）；
3. 输入构造必须满足前置条件（不满足前件的输入应走 pytest.raises 路径或排除）；
4. 可以阅读上方目标代码理解调用方式，但不得访问规约与签名之外的属性 / 符号。

被测模
```

### 例 2：`shortest_paths`

- 缓存文件：`0a6d6e6ef7a22367.json`（sha256 `65e17512600628f1…`）
- 缓存时间：`2026-10-24T15:39:49Z`
- prompt 长度：2836；代码标记 offset=29；augment framing offset=1320；规格锚出现次数=2；末次出现=1718；增广段小节标题在场=True

```text
'F'): -1
    })
    {'A': 0, 'C': 3, 'B': 1, 'E': 5, 'D': 10, 'F': 4}
"""

```

【规格增广模式（Spec-Augment）：规格锚与目标代码并列】
上方已完整给出目标代码；以下并列追加同一函数的人类独立规格锚（独立于缺陷实现书写）。
请结合两者：当实现与规格不一致时，按规格构造期望值（这是检出缺陷的关键）。
不得仅凭当前实现的实际行为推断期望值——那会把缺陷固化成预期（oracle-from-implementation），系统性抹掉检出。

函数签名：def shortest_paths(source, weight_by_edge)
被测模块名：shortest_paths（import 必须 `from shortest_paths import ...`）

【独立于实现的规格锚（人类 docstring）】
Minimum-Weight Paths
bellman-ford

Bellman-Ford algorithm implementation

Given a directed graph that may contain negative edges (as long as there are no negative-weight cycles), efficiently calculates the minimum path weights from a source node to every other node in the graph.

Input:
    source: A node id
    weight_by_edge: A dict containing edge weights keyed by an ordered pair of node ids

Precondition:
    The input graph contains no negative-weight cycles

Output:
   A dict mapping each node id to the minimum weight of a path from the source node to that node

Example:
    >>> shortest_paths('A', {
        ('A', 'B'): 3,
        ('A', 'C'): 3,
        ('A', 'F'): 5,
        ('C', 'B'): -2,
        ('C', 'D'): 7,
        ('C', 'E'): 4,
        ('D', 'E'): -5,
```

