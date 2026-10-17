# M-4 prompt 增广核验（LLM 缓存证据，脚本抽取）

> 目的：证明 augment 臂的 Generator prompt **同时包含目标缺陷代码块与人类规格锚段落**
> （M-1 处理有效性的一等证据）。数据来源 = `~/.cache/aitester/llm/*.json` 中批次时间窗内
> 的 generator 调用缓存。

> **判据澄清（重要）**：QuixBugs 的人类规格文本就是缺陷源码文件尾部的模块级 docstring，
> 因此「规格文本出现」**不能**单独证明增广注入（df 对照臂代码块内也含该文本）。
> 本证据以 **M-1 augment framing 段**为决定性判据：代码标记 < framing 标记 < 规格锚末次出现，
> 且 `spec_marker_occurrences` 记录该文本出现次数（源码内嵌 vs 增广段重复注入）。

## 计数

- 时间窗：`2026-10-17T13:10:22Z` → `2026-10-17T14:20:00Z`
- generator 缓存条目数（时间窗内）：**108**
- augment framing 命中（= augment 臂）：**43**
- 含代码块但无 framing 段（= df 对照臂，负向对照）：**42**
- framing 标记：`【规格增广模式（Spec-Augment）：规格锚与目标代码并列】`
- 证据状态：**ok**；负向对照在场：**True**

## 样例（1–2 例）

### 例 1：`minimum_spanning_tree`

- 缓存文件：`099e0d7fcfc6436d.json`（sha256 `09f41270ad0e8c27…`）
- 缓存时间：`2026-10-17T13:16:51Z`
- prompt 长度：2223；代码标记 offset=29；augment framing offset=1027；规格锚出现次数=2；末次出现=1588；增广段小节标题在场=True

```text
): 10,
    ...     (1, 4): 10
    ... })
    {(1, 2), (3, 4), (1, 4)}
"""

```

【规格增广模式（Spec-Augment）：规格锚与目标代码并列】
上方已完整给出目标代码；以下并列追加同一函数的人类独立规格锚（独立于缺陷实现书写）。
请结合两者：当实现与规格不一致时，按规格构造期望值（这是检出缺陷的关键）。
不得仅凭当前实现的实际行为推断期望值——那会把缺陷固化成预期（oracle-from-implementation），系统性抹掉检出。

函数签名：def minimum_spanning_tree(weight_by_edge)
被测模块名：minimum_spanning_tree（import 必须 `from minimum_spanning_tree import ...`）

【独立于实现的规格锚（人类 docstring）】
Minimum Spanning Tree


Kruskal's algorithm implementation.

Input:
    weight_by_edge: A dict of the form {(u, v): weight} for every undirected graph edge {u, v}

Precondition:
    The input graph is connected

Output:
    A set of edges that connects all the vertices of the input graph and has the least possible total weight.

Example:
    >>> minimum_spanning_tree({
    ...     (1, 2): 10,
    ...     (2, 3): 15,
    ...     (3, 4): 10,
    ...     (1, 4): 10
    ... })
    {(1, 2), (3, 4), (1, 4)}

【生成纪律（增广模式）】
1. 人类规格 / docstring 明确覆盖的行为，必须按规格断言——不得以当前实现的实际行为作为期望值；
2. 规格与实现不一致处即为嫌疑缺陷：按规格推导正确结果并断言（这是检出缺陷的关键）；
3. 输入构造必须满足前置条件（不满足前件的输入应走 pytest.raises 路径或排除）；
4. 可以阅读上方目标代码理解调用方式，但不得访问规约与签名之外的属性 / 符号。

被测模块名：minimum_spanning_tree

请根据以上计划生成完整的 pytest 测
```

### 例 2：`subsequences`

- 缓存文件：`2862c16a50ed6835.json`（sha256 `bdbae64c7ef009c6…`）
- 缓存时间：`2026-10-17T13:22:02Z`
- prompt 长度：1385；代码标记 offset=28；augment framing offset=511；规格锚出现次数=2；末次出现=899；增广段小节标题在场=True

```text
ces(a=1, b=5, k=3)
    [[1, 2, 3], [1, 2, 4], [1, 3, 4], [2, 3, 4]]
"""



```

【规格增广模式（Spec-Augment）：规格锚与目标代码并列】
上方已完整给出目标代码；以下并列追加同一函数的人类独立规格锚（独立于缺陷实现书写）。
请结合两者：当实现与规格不一致时，按规格构造期望值（这是检出缺陷的关键）。
不得仅凭当前实现的实际行为推断期望值——那会把缺陷固化成预期（oracle-from-implementation），系统性抹掉检出。

函数签名：def subsequences(a, b, k)
被测模块名：subsequences（import 必须 `from subsequences import ...`）

【独立于实现的规格锚（人类 docstring）】
Subsequences


Input:
    a: An int
    b: An int
    k: A positive int

Output:
    A list of all length-k ascending sequences of ints in range(a, b)

Example:
    >>> subsequences(a=1, b=5, k=3)
    [[1, 2, 3], [1, 2, 4], [1, 3, 4], [2, 3, 4]]

【生成纪律（增广模式）】
1. 人类规格 / docstring 明确覆盖的行为，必须按规格断言——不得以当前实现的实际行为作为期望值；
2. 规格与实现不一致处即为嫌疑缺陷：按规格推导正确结果并断言（这是检出缺陷的关键）；
3. 输入构造必须满足前置条件（不满足前件的输入应走 pytest.raises 路径或排除）；
4. 可以阅读上方目标代码理解调用方式，但不得访问规约与签名之外的属性 / 符号。

被测模块名：subsequences

请根据以上计划生成完整的 pytest 测试代码。

【重要约束】import 语句必须使用以下模块名：`subsequences`，即 `from subsequences import ...`
```

