# 失败案例分析报告

> 生成时间: 2026-08-14 14:49
> 总任务数: 187，成功: 56，失败: 131
> 整体失败率: 70.1%

## 1. 各基线失败统计

### aitester
- 总任务: 132，成功: 49，失败: 83
- 成功率: 37.1%

### plain_llm
- 总任务: 29，成功: 4，失败: 25
- 成功率: 13.8%

### single_agent
- 总任务: 26，成功: 3，失败: 23
- 成功率: 11.5%

## 2. 错误类型分布

### aitester
- error: 39 个任务 (47%)
- syntax: 25 个任务 (30%)
- runtime: 12 个任务 (14%)
- unknown: 5 个任务 (6%)
- assertion: 2 个任务 (2%)

### plain_llm
- syntax: 20 个任务 (80%)
- error: 4 个任务 (16%)
- unknown: 1 个任务 (4%)

### single_agent
- unknown: 22 个任务 (96%)
- error: 1 个任务 (4%)

## 3. 典型失败案例

### 案例 1: [aitester] error
- **任务**: `examples__is_palindrome`
- **错误**: error
- **诊断**: 执行异常: No JSON found in response: line 1 column 1 (char 0)

### 案例 2: [aitester] error
- **任务**: `examples__binary_search`
- **错误**: error
- **诊断**: 执行异常: No JSON found in response: line 1 column 1 (char 0)

### 案例 3: [aitester] syntax
- **任务**: `examples__binary_search`
- **错误**: syntax
- **诊断**: 测试文件尝试执行 `from binary_search import binary_search`，但当前代码未保存为 `binary_search.py` 模块文件或文件名不匹配，导致 Python 解释器无法找到该模块。错误类型为导入错误，归入 syntax/结构问题。

### 案例 4: [aitester] syntax
- **任务**: `examples__calculator_divide`
- **错误**: syntax
- **诊断**: 测试文件尝试从模块 'basic_operations' 导入函数，但被测代码未封装在名为 basic_operations.py 的文件中，导致 ModuleNotFoundError。

### 案例 5: [aitester] runtime
- **任务**: `examples__calculator_divide`
- **错误**: runtime
- **诊断**: 所有20个测试用例均报 NameError: name 'add' is not defined（及同类错误），根本原因是被测模块 calculator.py 中的函数没有被正确导入到测试作用域。虽然 target_code 本身函数定义完整，但测试运行时无法解析 add/subtract/multiply/divide/factorial 名称，说明被测文件未被模块系统正确加载或函数定义存在作用域问题。

### 案例 6: [aitester] runtime
- **任务**: `examples__calculator_divide`
- **错误**: runtime
- **诊断**: 两个测试失败：1) test_divide_very_small_divisor：divide(1.0, 1e-300) 返回约 1e+300 而非 inf，测试期望除极小正数时抛出 OverflowError；2) test_factorial_negative：测试期望传入负数时不抛异常，但当前代码在第19行直接 raise ValueError。

### 案例 7: [aitester] unknown
- **任务**: `examples__binary_search`
- **错误**: unknown
- **诊断**: 测试文件中的 @pytest.mark.parametrize 装饰器定义了3个参数名 ['arr', 'target', 'expected']，但每个测试用例提供了4个值 ('normal-middle', [1, 2, 3, 4, 5], 3, 2)。参数名数量与测试值数量不匹配，导致 pytest 收集阶段报错。被测代码 binary_search 本身逻辑正确，问题出在测试用例定义。

### 案例 8: [aitester] unknown
- **任务**: `examples__is_palindrome`
- **错误**: unknown
- **诊断**: JSON 解析失败: LLM 调用失败: Error code: 429 - {'error': {'code': '', 'message': 'You’ve reached the API rate limit for free users. Upgrade to a Token Plan to unlock higher limits and continue using the API without interruption. (request id: 20260814035436692164183q5nNYxzx)', 'type': 'AgnesAI_error'}}

### 案例 9: [aitester] assertion
- **任务**: `examples__calculator_divide`
- **错误**: assertion
- **诊断**: 测试用例 test_add_infinity 期望 add(float('inf'), float('inf')) 返回一个无穷大值（通过 math.isinf 检查），但当前 add 函数在检测到结果为无穷大时会抛出 OverflowError，导致测试断言失败。这是代码实现与测试预期不符：测试预期加法对无穷大是合法的，而代码却将其视为溢出异常。

### 案例 10: [aitester] assertion
- **任务**: `examples__calculator_divide`
- **错误**: assertion
- **诊断**: 断言失败源于测试用例本身的逻辑错误，而非被测代码 bug。具体有三处：1) 测试公式写反：用参数b=3.1作为期望值，但断言中却写 `(a - expected + b)` 即 `2.5 - 5.6 + 3.1 = 0.0`，而实际 `subtract(2.5, 3.1) = -0.6`，导致浮点不等式失败；2) 数据错位：`[5.0, 5.0, 0.0]` 预期 `add(5.0, 5.0) == 0.0`（应为10.0），`[-2.0, 3.0, -6.0]` 预期 `add(-2.0, 3.0) == -6.0`（应为1.0），明显是测试数据构造错误或参数顺序理解有误。被测代码所有函数实...

## 4. 基础设施问题汇总

共发现 45 个基础设施类失败（模块导入/文件名不匹配）。

**主要原因**：
1. 测试代码使用 `from module_name import func` 语法，但被测代码文件名与模块名不一致
2. 合成数据集模板中 instance_code 未保存为独立 .py 文件
3. Generator 生成的测试代码未感知目标文件的实际路径

**改进建议**：
- 在 Executor 阶段自动检测文件结构，动态创建或重命名模块文件
- 在 Generator Prompt 中明确要求测试代码使用相对导入
- 增强 SyntheticDataset 的模板一致性检查
