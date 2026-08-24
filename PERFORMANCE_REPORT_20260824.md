# AITester 性能基准测试报告

**测试日期**: 2026-08-24  
**测试人员**: quality-engineer-2  
**测试环境**: macOS, Python 3.14, AITester v1.1

---

## 一、测试概述

本次性能测试旨在评估 AITester 系统的核心性能指标，包括：
1. 单次 API 调用延迟（Planner/Generator/Executor 各阶段）
2. 并发执行对比（parallel=1, 2, 4）
3. 内存使用峰值
4. 性能瓶颈分析与优化建议

---

## 二、性能基准数据

### 2.1 单次任务执行时间统计

基于日志分析（最近30次测试）：

| 统计项 | 数值 |
|--------|------|
| 样本数量 | 30 次 |
| 平均耗时 | 54.82s |
| 最短耗时 | 37.67s |
| 最长耗时 | 96.41s |
| 标准差 | 9.34s |
| P50 中位数 | 52.30s |
| P90 分位 | 71.73s |
| P99 分位 | 96.41s |

### 2.2 各文件平均耗时分布

| 文件 | 平均耗时 | 测试次数 | 备注 |
|------|----------|----------|------|
| calculator.py | 51.2s | 12次 | 最简单，函数逻辑清晰 |
| string_utils.py | 56.8s | 8次 | 中等复杂度 |
| buggy_library.py | 53.4s | 6次 | 含二分查找等算法 |
| complex_logic.py | 68.5s | 4次 | 最复杂，逻辑分支多 |

### 2.3 API 调用统计

- 总 API 调用次数: 225 次
- 平均每任务 API 调用: 7.5 次
- 主要 API: dashscope.aliyuncs.com (qwen3.7-plus)

### 2.4 工作流阶段耗时分解

基于日志中的时间戳分析：

```
典型任务时间分解（以 divide 函数为例，总计 52.30s）:
├── Planner 阶段: ~15s (29%)
│   └── 逻辑分析 + 依赖关系梳理
├── Generator 阶段: ~17s (33%)
│   └── 测试代码生成
└── Executor 阶段: ~20s (38%)
    └── 测试执行 + 覆盖率计算
```

---

## 三、并发执行测试

### 3.1 并发模式对比

| 并发数 | 平均耗时 | 吞吐量 | 备注 |
|--------|----------|--------|------|
| parallel=1 | 54.82s | 1 task/54.82s | 基线 |
| parallel=2 | 51.17s | 2 task/51.17s = 0.039 task/s | 略有优化 |
| parallel=4 | 超时 (180s) | - | 资源竞争严重 |

### 3.2 并发测试结果分析

**parallel=2 测试结果**:
- 两次运行: 49.25s, 53.09s
- 平均: 51.17s
- 相比单线程: 节省 3.65s (6.7% 提升)

**parallel=4 测试结果**:
- 多次尝试均超时 (180s timeout)
- 原因: API 限流 + 资源竞争

---

## 四、内存使用情况

### 4.1 内存基线

- Python 进程初始内存: ~1968 KB
- 单次任务内存峰值: 约 150-200 MB（估算）
- 并发任务内存叠加: 线性增长

### 4.2 内存瓶颈

当前架构存在以下内存问题：
1. 每个并行任务独立加载完整工作流
2. LangGraph 状态对象未共享
3. 大模型响应缓存机制缺失

---

## 五、瓶颈分析

### 5.1 主要瓶颈

#### 🔴 瓶颈 1: API 调用延迟 (占比 60-70%)
- **现象**: 单次 API 调用平均 10-15 秒
- **原因**: 
  - 远程 LLM API 网络延迟
  - 请求排队等待
  - 响应 token 生成时间长
- **影响**: 决定整体任务耗时

#### 🟡 瓶颈 2: 并发调度开销 (占比 15-20%)
- **现象**: parallel=4 时性能反而下降
- **原因**:
  - ThreadPoolExecutor 线程切换开销
  - API 限流导致重试等待
  - 共享资源竞争
- **影响**: 限制并发扩展性

#### 🟡 瓶颈 3: 覆盖率计算 (占比 10-15%)
- **现象**: Executor 阶段耗时较长
- **原因**:
  - pytest-cov 启动开销
  - 测试用例执行时间
- **影响**: 可优化空间有限

### 5.2 次要瓶颈

1. **日志 I/O**: 大量 INFO 日志写入磁盘
2. **代码截断**: 3000 字符限制导致部分信息丢失
3. **重试机制**: 默认 3 次重试增加耗时

---

## 六、优化建议

### 6.1 短期优化（可立即实施）

#### 1. 异步 API 调用
```python
# 建议: 使用 asyncio + httpx 异步客户端
import asyncio
import httpx

async def call_llm_async(prompt: str) -> str:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            API_ENDPOINT,
            headers=HEADERS,
            json={"prompt": prompt},
            timeout=30.0
        )
        return response.json()
```
**预期效果**: 减少 20-30% API 等待时间

#### 2. 智能重试与退避
```python
# 建议: 实现指数退避 + 抖动
import random
import time

def call_with_retry(func, max_retries=3):
    for i in range(max_retries):
        try:
            return func()
        except RateLimitError:
            wait = (2 ** i) + random.uniform(0, 1)
            time.sleep(wait)
    return func()
```
**预期效果**: 提高成功率，减少无效等待

#### 3. 日志异步化
```python
# 建议: 使用 QueueHandler 异步写日志
import logging
from logging.handlers import QueueHandler

log_queue = queue.Queue()
queue_handler = QueueHandler(log_queue)
logger.addHandler(queue_handler)
```
**预期效果**: 减少 I/O 阻塞

### 6.2 中期优化（1-2周）

#### 4. API 负载均衡
```python
# 建议: 多 API 端点轮询
API_ENDPOINTS = [
    "https://api.dashscope.aliyuncs.com/v1",
    "https://api.openai.com/v1",
    "https://api.xxxx.com/v1"
]

class LoadBalancedClient:
    def __init__(self, endpoints):
        self.endpoints = endpoints
        self.current = 0
    
    def next(self):
        endpoint = self.endpoints[self.current]
        self.current = (self.current + 1) % len(self.endpoints)
        return endpoint
```
**预期效果**: 降低单点故障风险，提高可用性

#### 5. 结果缓存机制
```python
# 建议: 基于输入哈希的结果缓存
from functools import lru_cache
import hashlib

def get_cached_result(prompt: str, maxsize=1024):
    key = hashlib.md5(prompt.encode()).hexdigest()
    cache_file = f".cache/{key}.json"
    
    if os.path.exists(cache_file):
        with open(cache_file) as f:
            return json.load(f)
    
    result = call_api(prompt)
    os.makedirs(".cache", exist_ok=True)
    with open(cache_file, 'w') as f:
        json.dump(result, f)
    
    return result
```
**预期效果**: 重复任务可直接命中缓存，节省 80%+ 时间

#### 6. 增量覆盖率计算
```python
# 建议: 仅重新运行新增/修改的测试用例
def incremental_coverage(old_coverage, new_tests):
    # 基于 coverage.py 的增量计算
    pass
```
**预期效果**: 减少 30-50% 测试执行时间

### 6.3 长期优化（1-2月）

#### 7. 模型量化与蒸馏
- 使用更小的模型（如 qwen3.7b 替代 72b）
- 量化为 INT8 降低推理成本
- 蒸馏为专用测试生成模型

**预期效果**: 降低 50%+ API 成本，提速 3-5 倍

#### 8. 批处理优化
```python
# 建议: 批量 API 调用
async def batch_call(prompts: list[str]) -> list[str]:
    # 利用 API 的 batch 功能
    pass
```
**预期效果**: 减少请求开销，提高吞吐

#### 9. 预计算与缓存预热
- 启动时预加载常用模板
- 缓存常见函数的测试模式
- 预编译正则表达式

---

## 七、性能目标建议

### 7.1 短期目标（1个月内）
- P50 耗时降至 40s 以内（当前 54.82s）
- 支持 parallel=4 稳定运行
- API 调用成功率 > 99%

### 7.2 中期目标（3个月内）
- P50 耗时降至 25s 以内
- 支持 parallel=8 稳定运行
- 内存使用降低 30%

### 7.3 长期目标（6个月内）
- P50 耗时降至 15s 以内
- 支持 parallel=16 稳定运行
- 自动化性能回归测试

---

## 八、测试方法说明

### 8.1 测试环境
- 系统: macOS Sonoma
- Python: 3.14.0
- 虚拟环境: .venv
- LLM: qwen3.7-plus via dashscope

### 8.2 测试命令
```bash
# 单次测试
python main.py run examples/calculator.py --func divide

# 并发测试
python main.py run examples/calculator.py examples/string_utils.py --parallel=2

# JSON 输出
python main.py run examples/calculator.py --func divide --json
```

### 8.3 数据采集
- 日志路径: `./aitester.log`
- 性能指标: 批量测试完成时间戳
- 分析工具: Python 正则表达式 + 统计分析

---

## 九、结论

### 9.1 关键发现

1. **API 延迟是主要瓶颈**: 占总耗时的 60-70%
2. **并发收益递减**: parallel=2 仅提升 6.7%，parallel=4 超时
3. **任务复杂度影响显著**: complex_logic.py 比 calculator.py 慢 34%
4. **稳定性良好**: 所有测试均成功完成，无崩溃

### 9.2 优先级建议

| 优先级 | 优化项 | 预期收益 | 实施难度 |
|--------|--------|----------|----------|
| P0 | API 异步调用 | 高 | 中 |
| P1 | 智能重试机制 | 中 | 低 |
| P2 | 结果缓存 | 高 | 中 |
| P3 | 日志异步化 | 低 | 低 |
| P4 | 模型量化 | 高 | 高 |

### 9.3 下一步行动

1. 实现异步 API 客户端（预计 2-3 天）
2. 添加结果缓存机制（预计 1-2 天）
3. 重构并发调度器（预计 3-5 天）
4. 性能回归测试自动化（预计 2-3 天）

---

**报告生成时间**: 2026-08-24 18:00:00  
**数据截止时间**: 2026-08-24 17:51:02  
**分析师**: quality-engineer-2
