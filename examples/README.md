# 示例库（examples/）

本目录包含两类内容：

## 1. 被测代码模块（基础示例）

| 文件 | 说明 |
|------|------|
| `calculator.py` | 简易计算器（含典型 bug：算术、除零、二分查找等），`main.py run examples/calculator.py --func add` |
| `buggy_library.py` | 多函数缺陷库（字符串、算法等），演示批量修复 |
| `string_utils.py` | 字符串处理缺陷模块 |
| `complex_logic.py` | 复杂控制流缺陷模块 |
| `api_manager_example.py` | `APIManager` 集成示例（复杂度路由 / 成本告警 / 熔断） |

运行基础示例：

```bash
python main.py list-examples
python main.py run examples/calculator.py --func add
python main.py run examples/calculator.py examples/string_utils.py --parallel=2
```

## 2. 能力演示子目录（高级能力最小示例）

每个目录含可独立运行的 `run.py` + `README.md`（预期输出 + 涉及的环境变量开关），
无需额外配置即可离线运行（实跑高级能力需真实 LLM key / chromadb）：

| 子目录 | 能力 | 环境变量开关 |
|--------|------|-------------|
| [`semantic_cache_demo/`](semantic_cache_demo/README.md) | 5.1 语义级 LLM 缓存 | `SEMANTIC_CACHE_ENABLE`（默认 false） |
| [`cost_budget_demo/`](cost_budget_demo/README.md) | 5.4 任务级成本预算硬上限 | `COST_BUDGET_ENABLE`（默认 false） |
| [`rag_ab_demo/`](rag_ab_demo/README.md) | 3.1 RAG 检索增强 A/B | `ENABLE_RAG`（默认 false） |

运行能力演示：

```bash
python examples/semantic_cache_demo/run.py
python examples/cost_budget_demo/run.py
python examples/rag_ab_demo/run.py
```

> 各演示脚本的"预期输出说明"与"真实工作流中的效果验证命令"见对应目录
> 的 `README.md`；高级能力（RAG 实跑 / 跨文件修复 / 对抗性推理）的完整
> 用法见 [docs/usage_examples.md](../docs/usage_examples.md) 与
> [QUICKSTART.md](../QUICKSTART.md) "可选：高级开关" 节。
