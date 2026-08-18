# AITester 性能调优指南

> 本文档介绍 AITester 的性能优化机制、配置方法和常见问题排查。
> 最后更新：2026-08-16

---

## 一、RAG 检索器单例化

### 1.1 背景

ChromaDB 客户端初始化涉及：
- 加载嵌入模型（bge-small-zh-v1.5，约 100MB）
- 打开向量数据库索引文件
- 建立 HNSW 索引内存映射

单次初始化耗时约 **1-3 秒**。若每个节点都创建新实例，一轮修复可能浪费 **2-6 秒**。

### 1.2 实现方案

系统在 `src/graph/workflow.py` 中实现了**懒加载单例模式**：

```python
# 模块级缓存
_rag_retriever = None


def get_rag_retriever():
    """获取 RAG 检索器单例实例。"""
    global _rag_retriever
    if _rag_retriever is None and RAG_MODULE_AVAILABLE:
        try:
            _rag_retriever = TestCaseRetriever()
            logger.info("RAG 检索器单例已初始化")
        except Exception as e:
            logger.warning("RAG 检索器初始化失败: %s", e)
            _rag_retriever = None
    return _rag_retriever
```

**关键特性**：
- 首次调用时初始化，后续调用直接返回缓存实例
- 异常时标记为不可用，避免重复尝试
- 通过 `ENABLE_RAG` 开关控制是否启用

### 1.3 使用方式

在 `.env` 文件中配置：

```bash
ENABLE_RAG=true          # 启用 RAG 检索增强
```

> **注意**：启用 RAG 需要安装 `chromadb` 依赖，且首次运行会下载嵌入模型。

---

## 二、LLM 超时配置

### 2.1 背景

LLM API 调用可能因网络问题或模型负载过高而长时间无响应，导致任务卡死。

### 2.2 配置项

| 配置项 | 说明 | 默认值 | 推荐范围 |
|--------|------|--------|----------|
| `LLM_TIMEOUT` | 单次 LLM 调用超时（秒） | 60 | 30-300 |
| `LLM_RETRY_WAIT` | LLM 重试等待时间（秒） | 30 | 10-60 |
| `EXECUTION_TIMEOUT` | pytest 执行超时（秒） | 30 | 10-300 |
| `MAX_ITERATIONS` | 最大修复迭代次数 | 3 | 1-10 |

### 2.3 配置方法

在 `.env` 文件中设置：

```bash
# LLM 调用超时（防止 API 无响应）
LLM_TIMEOUT=60

# LLM 重试等待时间（指数退避基准）
LLM_RETRY_WAIT=30

# pytest 执行超时
EXECUTION_TIMEOUT=30

# 最大修复迭代次数
MAX_ITERATIONS=3
```

### 2.4 重试策略

系统采用**指数退避 + API 自动切换**策略：

```python
# base_agent.py 中的重试逻辑
for attempt in range(max_retries):
    try:
        response = llm.invoke(messages, timeout=LLM_TIMEOUT)
        return response
    except APIReachLimitError:
        wait_time = 2**attempt * LLM_RETRY_WAIT
        time.sleep(wait_time)
        continue
    except Exception:
        # 切换备用 API
        continue
```

**特点**：
- 限流错误：等待时间按 `2^attempt * base_wait` 增长
- 状态错误：指数退避重试
- 所有 API 失败：自动切换到下一个配置

---

## 三、并发执行（BENCHMARK_PARALLELISM）

### 3.1 背景

批量基准测试时，N 个任务串行执行总耗时 = N × 单任务耗时。通过多线程并行可显著缩短总时间。

### 3.2 配置方法

```bash
# 使用 4 个线程并行执行
BENCHMARK_PARALLELISM=4 python experiments/run_benchmark.py \
    --dataset synthetic \
    --task-count 50 \
    --baselines aitester,plain_llm,single_agent

# 串行执行（默认）
BENCHMARK_PARALLELISM=0 python experiments/run_benchmark.py ...
```

### 3.3 多线程配置隔离

系统通过 `threading.local()` 实现线程级 LLM 配置隔离：

```python
# base_agent.py
_thread_local = threading.local()


def set_thread_llm_config(api_key, base_url, model_name):
    """设置当前线程的 LLM 配置。"""
    _thread_local.api_key = api_key
    _thread_local.base_url = base_url
    _thread_local.model_name = model_name
```

**并发执行时的 API Key 配置**：

```bash
# 配置多个 API Key，系统自动轮询
LLM_1_API_KEY=sk-key-1
LLM_1_BASE_URL=https://api.provider1.com
LLM_1_MODEL_NAME=model-1

LLM_2_API_KEY=sk-key-2
LLM_2_BASE_URL=https://api.provider2.com
LLM_2_MODEL_NAME=model-2
```

### 3.4 性能对比

| 任务数 | 串行耗时（估计） | 4 线程并行耗时（估计） | 加速比 |
|--------|-----------------|----------------------|--------|
| 10 | ~500s | ~130s | 3.8x |
| 50 | ~2500s | ~650s | 3.8x |
| 100 | ~5000s | ~1300s | 3.8x |

> 实际加速比取决于 CPU 核心数、内存带宽和 API 限流情况。

---

## 四、常见问题排查

### 4.1 RAG 初始化失败

**症状**：日志中出现 `RAG 检索器初始化失败`

**可能原因**：
1. `chromadb` 未安装
2. 嵌入模型下载失败
3. 向量数据库目录权限问题

**解决方案**：
```bash
# 检查 chromadb 是否安装
pip list | grep chromadb

# 重新安装（如需）
pip install chromadb

# 清除缓存并重新初始化
rm -rf .chroma_cache/
```

### 4.2 LLM 调用超时

**症状**：任务长时间无响应，最终抛出 `TimeoutError`

**可能原因**：
1. API 响应慢（模型负载高）
2. 网络不稳定
3. `LLM_TIMEOUT` 设置过小

**解决方案**：
```bash
# 增加超时时间
LLM_TIMEOUT=120

# 增加重试次数（通过 MAX_ITERATIONS 间接控制）
MAX_ITERATIONS=5
```

### 4.3 并发执行性能不升反降

**症状**：设置 `BENCHMARK_PARALLELISM > 1` 后总耗时反而增加

**可能原因**：
1. API 限流（多请求同时发送被拒绝）
2. CPU 内存竞争
3. API Key 配置不足

**解决方案**：
```bash
# 降低并发数
BENCHMARK_PARALLELISM=2

# 增加 API Key 数量，减少限流概率
# 在 .env.local 中配置更多 LLM_N_* 配置

# 添加重试间隔（指数退避已内置）
LLM_RETRY_WAIT=60
```

### 4.4 覆盖率始终低于阈值

**症状**：测试反复运行，始终无法达到 `COVERAGE_THRESHOLD`

**可能原因**：
1. `COVERAGE_THRESHOLD` 设置过高
2. LLM 生成测试质量不佳
3. 被测代码复杂度超出 LLM 能力

**解决方案**：
```bash
# 降低覆盖率阈值
COVERAGE_THRESHOLD=70.0

# 增加迭代次数
MAX_ITERATIONS=5

# 启用 RAG 增强（如有历史成功案例）
ENABLE_RAG=true
```

---

## 五、性能调优最佳实践

### 5.1 快速验证（小规模测试）

```bash
# 串行执行，限制任务数
python experiments/run_benchmark.py \
    --dataset examples \
    --task-limit 2 \
    --baselines aitester
```

### 5.2 中等规模测试（推荐配置）

```bash
# 4 线程并行，合成数据集
BENCHMARK_PARALLELISM=4 \
python experiments/run_benchmark.py \
    --dataset synthetic \
    --task-count 20 \
    --baselines aitester,plain_llm,single_agent
```

### 5.3 大规模测试（发表级实验）

```bash
# 8 线程并行，大样本
BENCHMARK_PARALLELISM=8 \
LLM_TIMEOUT=90 \
LLM_RETRY_WAIT=45 \
python experiments/run_benchmark.py \
    --dataset synthetic \
    --task-count 100 \
    --baselines aitester,plain_llm,single_agent
```

### 5.4 消融实验配置

```bash
# 仅启用 Planner
ENABLE_PLANNER=true ENABLE_DEBUGGER=false \
python experiments/run_benchmark.py --dataset examples

# 仅启用 Debugger
ENABLE_PLANNER=false ENABLE_DEBUGGER=true \
python experiments/run_benchmark.py --dataset examples

# 纯 LLM 基线（无 Planner、无 Debugger）
ENABLE_PLANNER=false ENABLE_DEBUGGER=false \
python experiments/run_benchmark.py --dataset examples
```

---

## 六、监控与诊断

### 6.1 启用调试日志

```bash
# 查看详细日志
PYTHONUNBUFFERED=1 python experiments/run_benchmark.py \
    --verbose \
    --log-level DEBUG
```

### 6.2 关键指标监控

| 指标 | 含义 | 正常范围 |
|------|------|----------|
| `avg_llm_latency` | 平均 LLM 响应时间 | < 30s |
| `llm_timeout_count` | LLM 超时次数 | < 5% |
| `retry_rate` | API 重试率 | < 20% |
| `coverage_improvement` | 覆盖率提升幅度 | > 10%/轮 |
| `max_iterations_reached` | 达到最大迭代的任务数 | < 30% |

### 6.3 性能分析脚本

```python
# 使用 cProfile 分析单任务耗时
python -m cProfile -s cumtime \
    -o profile.prof \
    main.py run examples/calculator.py --func divide

# 查看分析报告
snakeviz profile.prof
```

---

## 七、附录：配置速查表

```bash
# ==================== 基础配置 ====================
MODEL_NAME=agnes-2.5-flash
TEMPERATURE=0.2
COVERAGE_THRESHOLD=80.0

# ==================== 超时配置 ====================
LLM_TIMEOUT=60              # LLM 调用超时
LLM_RETRY_WAIT=30           # LLM 重试等待
EXECUTION_TIMEOUT=30        # pytest 执行超时
MAX_ITERATIONS=3            # 最大修复迭代

# ==================== 并发配置 ====================
BENCHMARK_PARALLELISM=4     # 并行线程数（0=串行）

# ==================== 消融开关 ====================
ENABLE_PLANNER=true         # 启用 Planner
ENABLE_DEBUGGER=true        # 启用 Debugger
ENABLE_RAG=false            # 启用 RAG

# ==================== LLM Provider 配置 ====================
# 支持多组 API Key，系统自动轮询
LLM_1_API_KEY=sk-key-1
LLM_1_BASE_URL=https://api.provider1.com
LLM_1_MODEL_NAME=model-1

LLM_2_API_KEY=sk-key-2
LLM_2_BASE_URL=https://api.provider2.com
LLM_2_MODEL_NAME=model-2
```

---

*文档版本：v1.0*  
*维护者：aitester-maintenance-team*
