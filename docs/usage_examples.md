# AITester 使用示例

> 本文档提供详细的使用示例，帮助开发者快速上手 AITester。
> 最后更新：2026-09-14

---

## 目录

1. [基础使用](#基础使用)
2. [批量基准测试](#批量基准测试)
3. [配置调整](#配置调整)
4. [高级功能](#高级功能)
5. [常见问题](#常见问题)

---

## 基础使用

### 示例 1：测试单个函数

```bash
# 测试 calculator.py 的 divide 函数
python main.py run examples/calculator.py --func divide
```

**输出示例：**
```
[Planner] 开始分析函数: divide
[Generator] 生成测试代码...
[Executor] 执行测试...
[Debugger] 未发现需要修复的错误
结果: PASS, 覆盖率: 100%
```

---

### 示例 2：测试包含 bug 的函数

```bash
# 测试 buggy_library.py 的 binary_search 函数（含 bug）
python main.py run examples/buggy_library.py --func binary_search
```

**输出示例：**
```
[Planner] 开始分析函数: binary_search
[Generator] 生成测试代码...
[Executor] 执行测试...
[Debugger] 检测到 assertion 错误，开始修复...
[Debugger] 修复补丁已应用，重新执行测试...
结果: PASS, 覆盖率: 100%, 迭代次数: 1
```

---

### 示例 3：测试全部函数

```bash
# 不指定 --func，测试文件中所有函数
python main.py run examples/calculator.py
```

---

## 批量基准测试

### 示例 4：运行内置数据集

```bash
# 运行 examples 数据集，对比三种基线
python experiments/run_benchmark.py \
    --dataset examples \
    --baselines aitester,plain_llm,single_agent
```

---

### 示例 5：限制任务数量（快速验证）

```bash
# 仅运行 2 个任务
python experiments/run_benchmark.py \
    --dataset examples \
    --task-limit 2
```

---

### 示例 6：运行合成数据集

```bash
# 生成并运行 50 个合成任务
python experiments/run_benchmark.py \
    --dataset synthetic \
    --task-count 50 \
    --baselines aitester
```

---

### 示例 7：并行执行（加速）

```bash
# 使用 4 个线程并行执行
BENCHMARK_PARALLELISM=4 python experiments/run_benchmark.py \
    --dataset synthetic \
    --task-count 100
```

或使用命令行参数：
```bash
python experiments/run_benchmark.py \
    --dataset synthetic \
    --task-count 100 \
    --parallel 4
```

---

## 配置调整

### 示例 8：调整超时时间

```bash
# 设置 pytest 执行超时为 60 秒
python main.py run examples/calculator.py --timeout 60
```

或配置环境变量：
```bash
EXECUTION_TIMEOUT=60 python main.py run examples/calculator.py
```

---

### 示例 9：调整最大迭代次数

```bash
# 最多修复 5 轮
python main.py run examples/buggy_library.py --func binary_search --max-iterations 5
```

---

### 示例 10：启用 RAG 增强

编辑 `.env` 文件：
```bash
ENABLE_RAG=true
```

然后运行：
```bash
python main.py run examples/calculator.py --func divide
```

---

### 示例 11：消融实验

```bash
# 仅启用 Planner（禁用 Debugger）
ENABLE_PLANNER=true ENABLE_DEBUGGER=false python experiments/run_benchmark.py \
    --dataset examples
```

---

## 高级功能

### 示例 12：JSON 输出（程序化处理）

```bash
# 结果以 JSON 格式输出（stdout 直接打印，无需开关）
python experiments/run_benchmark.py \
    --dataset examples
```

**输出示例：**
```json
{
  "dataset": "examples",
  "total_tasks": 3,
  "results": [
    {
      "task_id": "calculator.py::divide",
      "status": "pass",
      "coverage": 100.0,
      "iterations": 0
    }
  ]
}
```

---

### 示例 13：结果可视化

```bash
# 生成可视化图表
python experiments/visualize_results.py

# 指定结果目录
python experiments/visualize_results.py \
    --results-dir experiments/results/synthetic_full
```

输出文件：
- `experiments/results/charts/baseline_comparison.png`
- `experiments/results/charts/statistical_significance.png`
- `experiments/results/charts/summary_stats.md`

---

### 示例 13.5：结果结构化分析（4.3 + 1.1/1.2/1.3 指标）

```bash
# 分析最新一次 benchmark 结果
python experiments/analyze_results.py --results-dir experiments/results

# 分析指定 benchmark JSON
python experiments/analyze_results.py \
    --input experiments/results/benchmark_synthetic_<timestamp>.json
```

输出：
- 终端打印 Markdown 汇总（成功率 / Token 效率 / 迭代次数分布 / 失败原因分布 / RAG 质量 / 修复收敛效率 / 多维质量代理 / 测试异味检测 / 修复收敛曲线）
- `<输入文件同目录>/analysis_summary.md`

**新增指标说明（1.1 多维评估 + 1.2 修复收敛效率 + 1.3 修复收敛曲线 + 1.2 测试异味检测）**：

| 指标组 | 字段 | 说明 |
|--------|------|------|
| 修复收敛效率 | `repair_convergence_metrics.first_attempt_success_rate` | 首次尝试（iterations==0）且通过的任务占比 |
| 修复收敛效率 | `repair_convergence_metrics.success_iteration_stats` | 成功任务迭代次数的 min/avg/median/max |
| 修复收敛效率 | `repair_convergence_metrics.success_elapsed_seconds` | 成功任务耗时的 min/avg/median/max |
| 多维质量代理 | `quality_proxy_metrics.coverage_proxy` | 成功/失败任务的覆盖率均值与中位数 |
| 多维质量代理 | `quality_proxy_metrics.runtime_proxy` | 成功/失败任务耗时的均值与中位数 |
| 多维质量代理 | `quality_proxy_metrics.assertion_proxy` | 若 `details[].generated_test` 存在，统计每任务 `assert` 行数（代理断言强度） |
| 多维质量代理 | `quality_proxy_metrics.failure_top_categories` | 失败任务 Top N 错误类别（辅助归因） |
| 测试异味检测（1.2） | `test_smell_detection` | AST 扫 `details[].generated_test`，检测 4 类 LLM 生成异味：Assertion Roulette（无有效断言）/ Magic Number（≥3 个未命名整数）/ 断言弱化（断言行数较上轮减少）/ 平凡测试（函数体仅 pass / 恒真断言）；旧 JSON 无 `generated_test` 时 `available=False` 跳过章节 |
| 修复收敛曲线（1.3） | `repair_convergence_curve` | 按迭代轮次 0/1/2/3+ 统计"到达任务数 / 累计通过 / 累计通过率 / 累计平均耗时"，观察随迭代增加通过率如何变化 |

> 注：该章节为保守代理指标（基于现有结果字段可复算），不等同于 AST 圈复杂度、内存占用等精确结构/性能指标；`assertion_proxy` / 测试异味检测 / 修复收敛曲线仅在结果 JSON 的 `details[].generated_test` 提供时可用，旧 JSON 自动降级为 `N/A` 或跳过章节。

---

### 示例 13.6：失败根因分析 + 案例知识库（5.3）

```bash
# 失败案例聚类报告 + 根因三大类（LLM 能力 / 依赖 / 框架）+ 结构化知识库落盘
python experiments/analyze_failures.py \
    --results-dir experiments/results \
    --knowledge-base experiments/results/failure_knowledge_base.json
```

输出：
- 失败案例按基线 / 错误类型聚类的 Markdown 报告（`--output` 默认 `experiments/results/failure_analysis.md`）
- 失败根因三大类（`llm_capability` / `dependency` / `framework`，`root_cause_classification()` 保守启发式归类，每类最多 3 个代表案例）
- 结构化案例知识库 `failure_knowledge_base.json`（按 `error_category` 多样性优先选取，含 `task_id` / `root_cause` / `reproducible_steps` / `suggested_fix`）

---

### 示例 14：查看示例列表

```bash
python main.py list-examples
```

**输出：**
```
可用示例文件：
  - examples/calculator.py (divide, factorial)
  - examples/buggy_library.py (binary_search, merge_sorted)
  - examples/string_utils.py (is_palindrome, caesar_cipher)
```

---

## Python API 使用

### 示例 15：编程方式调用

```python
from src.agents.planner import PlannerAgent
from src.agents.generator import GeneratorAgent
from src.agents.executor import ExecutorAgent
from src.agents.debugger import DebuggerAgent
from src.tools.patch_applier import apply_patch_to_code

# 目标代码
target_code = """
def divide(a: float, b: float) -> float:
    '''返回两数之商。'''
    if b == 0:
        raise ValueError("除数不能为零")
    return a / b
"""

# Step 1: 规划
planner = PlannerAgent()
plan = planner.plan(target_code, "divide")

# Step 2: 生成测试
generator = GeneratorAgent()
test_code = generator.generate(plan, target_code, "calculator")

# Step 3: 执行测试
executor = ExecutorAgent()
result = executor.execute(test_code)

print(f"测试结果: {result['status']}")
print(f"覆盖率: {result['coverage']}%")
```

---

### 示例 16：使用工作流图

```python
from src.graph.workflow import build_workflow
from src.graph.state import AITesterState

# 构建工作流（planner/debugger 默认 None，读取 config.ENABLE_PLANNER / ENABLE_DEBUGGER）
graph = build_workflow()

# 运行工作流：invoke 接收初始状态字典，返回最终状态
state: AITesterState = {
    "target_code": "def add(a, b): return a - b",  # 故意写错
    "target_function": "add",
    "module_name": "calculator",
    "max_iterations": 3,
}
result = graph.invoke(state)

print(f"测试是否通过: {result['test_passed']}")
print(f"修复后代码:\n{result['target_code']}")
```

---

## 常见问题

### Q: 如何添加新的被测文件？

将 Python 文件放入 `examples/` 目录，确保包含函数定义和已知 bug（可选）。

```python
# examples/my_module.py
def my_function(x: int) -> int:
    """返回 x 的平方。"""
    return x * x  # 正常实现
```

然后运行：
```bash
python main.py run examples/my_module.py --func my_function
```

---

### Q: 如何处理 ModuleNotFoundError？

**原因**：import 语句中的模块名与实际文件不匹配。

**解决**：
1. 检查 `module_name` 参数是否与文件名一致
2. 确认被测文件在 Python 路径中
3. 使用相对导入：`from src.my_module import my_function`

---

### Q: 如何调整 LLM 模型？

编辑 `.env.local`（LLM 敏感配置所在），修改 `LLM_N_*` 组：
```bash
LLM_1_MODEL_NAME=gpt-4o
LLM_1_BASE_URL=https://api.openai.com/v1
# 或
LLM_1_MODEL_NAME=agnes-3.0-flash
LLM_1_BASE_URL=https://api.agnes-ai.cn/v1
```

---

### Q: 如何查看详细日志？

添加 `-v` 参数：
```bash
python main.py run examples/calculator.py -v
```

或设置日志级别：
```bash
LOG_LEVEL=DEBUG python main.py run examples/calculator.py
```

---

## 更多资源

- [API 参考文档](api_reference.md)
- [性能调优指南](performance_guide.md)
- [算法设计文档](algorithm_design.md)
- [贡献指南](../CONTRIBUTING.md)
