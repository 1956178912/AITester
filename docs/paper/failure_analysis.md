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

---

## 5. 补充分析：Synthetic 数据集失败案例（2026-08-13 ~ 2026-08-14）

### 5.1 实验概况

**数据来源**: `experiments/results/synthetic_*/` 目录下的实验结果  
**总失败案例数**: 16 个  
**覆盖基线**: aitester, plain_llm  
**实验配置**: ENABLE_PLANNER=true, ENABLE_DEBUGGER=true, ENABLE_RAG=false

### 5.2 失败率统计

#### 按错误类型分布
| 错误类型 | 数量 | 占比 | 说明 |
|---------|------|------|------|
| syntax | 14 | 87.5% | 模块导入失败、语法错误 |
| error | 2 | 12.5% | LLM响应解析失败、执行异常 |
| unknown | 0 | 0.0% | 未分类错误 |

#### 按Bug类型分布
| Bug类型 | 数量 | 占比 | 说明 |
|---------|------|------|------|
| runtime | 11 | 68.8% | 运行时错误（实际为导入问题） |
| assertion | 5 | 31.2% | 断言失败、测试逻辑错误 |

#### 按诊断模式分布
| 诊断模式 | 数量 | 占比 | 典型案例 |
|---------|------|------|---------|
| 模块导入失败 | 13 | 81.2% | ModuleNotFoundError |
| LLM响应解析失败 | 1 | 6.2% | No JSON found in response |
| 参数化测试错误 | 1 | 6.2% | parametrize参数不匹配 |
| 其他 | 1 | 6.2% | 测试逻辑错误 |

### 5.3 失败模式分类

#### 类别 1: LLM 能力边界

**1.1 复杂逻辑推理失败**
- **表现**: 测试用例设计逻辑错误
- **案例**: `synthetic__palindrome_case_sensitive_0012`
- **原因**: LLM 在生成参数化测试时，参数名数量与测试值数量不匹配
- **诊断**: `parametrize 装饰器声明了2个参数名 ['s', 'expected']，但提供的测试数据每个用例包含3个值`
- **根本原因**: LLM 缺乏对测试框架语法的精确理解，容易在复杂场景下出现格式错误

**1.2 多步修复失败**
- **表现**: 经过多次迭代仍无法修复
- **案例**: 所有 syntax 错误类型的任务（14个）
- **原因**: Debugger 无法识别模块导入问题，认为代码无bug
- **诊断**: "被测代码本身语法正确，但缺少模块文件结构"
- **根本原因**: 错误分类器将导入错误归类为 syntax，但 Debugger 的修复策略针对代码逻辑错误，无法处理环境问题

**1.3 边界情况处理错误**
- **表现**: 测试用例无法覆盖边界情况
- **案例**: 部分 assertion 类型失败
- **原因**: LLM 生成的测试用例缺乏边界值设计
- **根本原因**: Generator 的 Prompt 中未明确要求覆盖边界情况

#### 类别 2: 代码依赖问题

**2.1 模块导入路径错误** ⭐ **最高频**
- **表现**: ModuleNotFoundError
- **案例数**: 13 个 (81.2%)
- **典型案例**:
  - `synthetic__divide_by_zero_missing_0000`: 测试尝试 `from calculator import divide`，但代码未保存为 calculator.py
  - `synthetic__off_by_one_right_0001`: 测试尝试 `from binary_search import binary_search`，但代码未保存为 binary_search.py
- **根本原因**:
  1. Generator 生成的测试代码使用绝对导入（`from module import func`）
  2. 被测代码仅作为函数定义提供，未包装为模块
  3. Executor 执行测试时，临时目录不在 Python 模块搜索路径中
- **影响范围**: 所有使用合成数据集的实验

**2.2 依赖库缺失**
- **表现**: ImportError（未安装的库）
- **案例数**: 0 个
- **说明**: 当前实验未遇到此问题

**2.3 环境问题**
- **表现**: 临时目录路径配置问题
- **案例数**: 13 个（与模块导入问题重叠）
- **根本原因**: 
  - 测试脚本运行在 `/var/folders/.../T/` 临时目录
  - 被测代码文件未置于同一目录
  - sys.path 未包含被测代码路径

#### 类别 3: 框架设计缺陷

**3.1 错误分类器遗漏**
- **表现**: 将环境问题误判为代码错误
- **案例**: 所有 syntax 类型失败
- **诊断**: "被测代码本身语法正确，但缺少模块文件结构"
- **根本原因**: 
  - 错误分类器无法区分"代码逻辑错误"和"测试环境配置错误"
  - 缺乏对 ModuleNotFoundError 的专门处理逻辑
- **影响**: Debugger 尝试修复不存在的代码bug，浪费迭代次数

**3.2 补丁应用失败**
- **表现**: Debugger 生成的补丁无效
- **案例数**: 14 个（所有 syntax 类型）
- **原因**: Debugger 针对代码逻辑生成补丁，但问题是模块结构
- **根本原因**: 工作流设计假设错误都是代码bug，忽略了测试环境问题

**3.3 工作流路由错误**
- **表现**: 进入无效修复循环
- **案例**: 所有 syntax 类型任务（平均迭代 3 次）
- **原因**: 
  - Executor 检测到测试失败
  - 路由到 Debugger
  - Debugger 无法识别导入问题，生成无效补丁
  - 循环 3 次后放弃
- **根本原因**: 缺少对导入错误的提前检测和专门处理

### 5.4 典型失败案例详情

#### 案例 1: 模块导入失败（最高频）

**任务描述**:
- 任务ID: `synthetic__divide_by_zero_missing_0000`
- Bug类型: runtime（实际为导入问题）
- 模式: divide_by_zero_missing
- 基线: aitester

**失败过程**:
1. Generator 生成测试代码：`from calculator import divide`
2. Executor 执行测试，抛出 `ModuleNotFoundError: No module named 'calculator'`
3. Debugger 诊断："被测代码本身 divide 函数逻辑正确，但缺少模块级声明"
4. 迭代 3 次后放弃，成功率 0%

**根本原因分析**:
- Generator 生成的测试代码假设被测代码是独立模块文件
- 但合成数据集的 instance_code 仅包含函数定义，未包装为模块
- Executor 在临时目录执行测试，sys.path 不包含被测代码路径
- Debugger 无法识别这是环境问题而非代码问题

**改进建议**:
1. Executor 阶段自动检测导入错误，创建临时模块文件
2. Generator Prompt 明确要求测试代码使用相对导入或正确路径
3. 增强 SyntheticDataset 的模板一致性检查

#### 案例 2: LLM响应解析失败

**任务描述**:
- 任务ID: `synthetic__palindrome_case_sensitive_0002`
- Bug类型: assertion
- 模式: palindrome_case_sensitive
- 基线: plain_llm

**失败过程**:
1. Generator 调用 LLM 生成测试代码
2. LLM 返回空响应（可能因限流或超时）
3. 解析失败："No JSON found in response: line 1 column 1 (char 0)"
4. 直接标记为失败，未进入 Executor

**根本原因分析**:
- API 限流导致 LLM 调用失败
- 重试机制不足（仅重试 3 次）
- 缺少降级策略（如使用备用模型）

**改进建议**:
1. 增加 LLM 调用重试次数（5-10次）
2. 实现多模型fallback机制
3. 添加请求速率限制和退避策略

#### 案例 3: 参数化测试定义错误

**任务描述**:
- 任务ID: `synthetic__palindrome_case_sensitive_0012`
- Bug类型: assertion
- 模式: palindrome_case_sensitive
- 基线: aitester

**失败过程**:
1. Generator 生成参数化测试代码
2. 测试收集阶段失败：`parametrize 装饰器声明了2个参数名 ['s', 'expected']，但提供的测试数据每个用例包含3个值`
3. 错误被分类为 unknown
4. Debugger 无法修复（测试代码本身有逻辑错误）

**根本原因分析**:
- LLM 在生成复杂参数化测试时出现格式错误
- 参数名数量与测试值数量不匹配
- 缺乏对测试代码的静态检查

**改进建议**:
1. Executor 阶段增加测试代码静态检查
2. Generator Prompt 强调参数化测试的格式要求
3. 实现测试代码自动生成后的语法验证

### 5.5 改进建议汇总

#### 立即改进（P0）
1. **Executor 模块导入修复**
   - 检测 ModuleNotFoundError
   - 自动创建临时模块文件
   - 动态调整 sys.path

2. **错误分类器增强**
   - 识别环境问题 vs 代码问题
   - 对导入错误使用专门处理逻辑
   - 避免进入无效修复循环

3. **LLM 调用可靠性**
   - 增加重试次数到 5-10 次
   - 实现多模型 fallback
   - 添加速率限制和指数退避

#### 中期改进（P1）
1. **Generator Prompt 优化**
   - 明确要求测试代码使用相对导入
   - 强调参数化测试格式规范
   - 添加测试代码静态检查示例

2. **SyntheticDataset 模板增强**
   - 确保 instance_code 包含完整模块结构
   - 添加 `__init__.py` 文件
   - 提供模块导入示例

3. **工作流路由优化**
   - 在 Executor 阶段增加导入错误检测
   - 对导入错误跳过 Debugger，直接报告
   - 减少无效迭代

#### 长期改进（P2）
1. **测试代码验证框架**
   - 实现 AST 解析和语法检查
   - 验证参数化测试格式
   - 检查导入路径正确性

2. **环境隔离机制**
   - 使用 Docker 容器执行测试
   - 自动配置 Python 环境
   - 隔离依赖冲突

3. **智能错误分类**
   - 基于历史数据训练分类器
   - 自动识别问题类型
   - 动态调整修复策略

### 5.6 与现有分析的对比

**原有分析（2026-08-14）**:
- 总任务数: 187
- 整体失败率: 70.1%
- 主要问题: 基础设施类失败（45个）

**补充分析（2026-08-13 ~ 2026-08-14）**:
- 新增失败案例: 16个
- 模块导入失败占比: 81.2%
- 主要发现: 环境问题被误判为代码问题，导致无效修复循环

**关键洞察**:
1. 合成数据集的实验失败率显著高于示例数据集（5% vs 37%）
2. 模块导入问题是合成数据集的主要失败原因（81.2%）
3. 错误分类器无法区分环境问题和代码问题，导致Debugger无效工作
4. 需要在工作流层面增加环境检测和自动修复机制

---

## 6. 综合讨论

### 6.1 失败模式的系统性分析

通过整合所有实验结果（examples + synthetic 数据集），我们发现失败模式具有明显的层次结构：

**第一层：基础设施问题（占比最高）**
- 模块导入失败
- 环境配置错误
- 依赖缺失

**第二层：LLM能力边界**
- 复杂逻辑推理失败
- 格式输出不稳定
- 边界情况遗漏

**第三层：框架设计缺陷**
- 错误分类不准确
- 修复策略不匹配
- 工作流路由不合理

### 6.2 改进优先级

基于失败频率和影响程度，建议改进优先级：

1. **P0（立即实施）**: 模块导入自动修复
   - 预计可减少 80% 的合成数据集失败
   - 实现成本低，效果显著

2. **P1（近期实施）**: 错误分类器增强
   - 减少无效修复循环
   - 提升系统鲁棒性

3. **P2（长期规划）**: LLM调用可靠性提升
   - 增加重试和fallback机制
   - 提升整体成功率

### 6.3 未来研究方向

1. **自动化环境配置**
   - 检测并修复导入路径问题
   - 自动创建模块文件结构

2. **智能错误分类**
   - 基于历史数据训练分类器
   - 自动区分环境问题和代码问题

3. **测试代码质量保障**
   - 静态分析验证测试格式
   - 自动修复参数化测试错误

---

**报告更新时间**: 2026-08-16  
**分析范围**: 扩展至 synthetic 数据集失败案例  
**新增发现**: 模块导入问题是合成数据集的主要失败原因（81.2%）
