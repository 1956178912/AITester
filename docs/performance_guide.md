> **语言 / Language**：[English](performance_guide.en.md) | 简体中文（本文）

# AITester 性能调优指南

> 本文档介绍 AITester 的性能优化机制、配置方法和常见问题排查。
> 最后更新：2026-09-25（0.10 深度审查轮：LLM 缓存负缓存 TTL 正确性回归 + 路径白名单根归一口径修正 + 追踪层冗余摘要消除 + 统计接口免重扫；7.3 节 LRU 描述同步 0.9 批次 `llm_cache.py` 删除后的内嵌快路径口径）

---

## 一、RAG 检索器单例化

### 1.1 背景

ChromaDB 客户端初始化涉及：
- 加载嵌入模型（bge-small-zh-v1.5，约 100MB）
- 打开向量数据库索引文件
- 建立 HNSW 索引内存映射

单次初始化耗时约 **1-3 秒**。若每个节点都创建新实例，一轮修复可能浪费 **2-6 秒**。

### 1.2 实现方案

系统在 `src/graph/rag.py` 中实现了**懒加载单例模式**（`workflow.py` 经 `from src.graph.rag import get_rag_retriever` re-export 保持旧导入路径）：

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

系统采用**指数退避 + API 自动切换**策略（0.6 轮次 P0-1 起统一走
`_retry_with_exponential_backoff`）：

```python
# llm_client.py 中的统一重试逻辑（OpenAI 兼容路径与 zai SDK 路径共用）
for attempt in range(max_retries + 1):
    try:
        response = llm.invoke(messages, timeout=LLM_TIMEOUT)
        return response
    except Exception:
        wait_time = base_wait * (2**attempt)  # 指数退避：1s→1/2/4s（zai 路径 5s→5/10/20s）
        time.sleep(wait_time)
        continue
# 重试耗尽 → 自动切换到同 API 下一模型 / 备用 API
```

**特点**：
- 退避等待按 `base_wait * 2^attempt` 增长：OpenAI 兼容路径 `base_wait=1s`
  （1s/2s/4s），zai SDK 路径 `base_wait=5s`（5s/10s/20s，限流更严格取更长基准）
- 所有重试失败：自动切换到同 API 下一模型 / 备用 API（故障转移）
- 注意：`LLM_RETRY_WAIT` 现仅用于 `run_benchmark` 的任务间限流等待，**不再驱动重试退避**
  （退避基准由 `base_wait` 参数控制）

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

# 清除 RAG 向量库并重新初始化（RAG 检索库持久化在 rag_data/，可用 RAG_PERSIST_PATH 覆盖；
# chromadb 自身不落 .chroma_cache 目录，旧版命令已废弃）
rm -rf rag_data/
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

**APIManager 熔断器与成本感知配置项（4.1/4.2/3.4，经 `get_status()` 监控）**：

| 配置项（`APIManagerConfig`） | 默认值 | 监控字段（`get_status().nodes[*]`） | 说明 |
|------|--------|------|------|
| `circuit_cooldown_seconds` | 60.0 | `circuit_open_remaining_s` | 4.1 熔断冷却时长：连续失败达 `max_consecutive_failures` 后节点进入冷却期，路由层跳过 |
| `enable_half_open_probe` | True | `circuit_state`（closed/open/half_open） | 4.2 半开探测：冷却到期后节点先进入 half-open 窗口仅承载一次探测，成功闭合 / 失败重开 `min(cooldown/2, cap)` 半程冷却 |
| `half_open_probe_penalty_cap_seconds` | 30.0 | （惩罚时长上限，无独立监控字段） | 4.2 半开探测失败惩罚上限，防死 provider 冷却期无限缩短 |
| `cost_alert_threshold` | 2.0 | （故障转移落昂贵节点时记 WARNING） | 3.4 成本告警：转移到 `cost_weight >= 阈值` 的昂贵 provider 时告警 |

| 指标 | 含义 | 解读 |
|------|------|------|
| `repair_convergence_metrics.first_attempt_success_rate` | 首次尝试（iterations==0）且通过的任务占比 | 高 = 任务对当前模型/策略友好；低 = 需多轮修复， Debugger 压力更大 |
| `repair_convergence_metrics.success_iteration_stats.avg/median` | 成功任务平均/中位迭代次数 | 收敛速度刻画；中位比均值更稳健（抗长尾） |
| `quality_proxy_metrics.coverage_proxy` / `runtime_proxy` | 成功/失败任务的覆盖率与耗时代理 | 用于观察"修复后是否引入性能回归"的保守信号 |
| `quality_proxy_metrics.assertion_proxy` | 若 `details[].generated_test` 存在，统计每任务 `assert` 行数 | 代理断言强度，检测"断言弱化"趋势；旧 JSON 自动 N/A |

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

## 七、LLM 客户端复用（连接池共享）

### 7.1 背景

优化前，每次 LLM 调用都新建一个客户端实例（`ChatOpenAI` / `ZhipuAiClient`），意味着反复创建底层 HTTP 连接池。高迭代次数（`MAX_ITERATIONS=3` × 多任务）时，建连开销累积明显。

### 7.2 实现方案

`src/agents/base_agent.py` 提供两个按配置键复用的客户端缓存：

| 路径 | 缓存键 | 上限 | 驱逐策略 |
|------|--------|------|----------|
| OpenAI 兼容（`ChatOpenAI`） | `(model_name, temperature, api_key, base_url)` | 16 | FIFO |
| zai SDK（`ZhipuAiClient`） | `(api_key, base_url)` | 16 | FIFO |

入口函数：`_get_or_create_chat_client()` 与 `_get_or_create_zai_client()`。同一配置下的多次调用共享同一客户端（及其连接池），不同配置互不影响。

### 7.3 注意事项

- 缓存上限 16：常规使用（少数几个模型配置）远不会触及；大量不同 API Key 轮换时按 FIFO 逐个驱逐，行为可预期。
- 客户端复用不影响 LLM 文件缓存与进程内 LRU 快路径（0.9 轮次删除了独立的 `src/graph/llm_cache.py` 模块，LLM 文件缓存的进程内 LRU 快路径现内嵌于 `base_agent._call_llm_with_cache`，二者作用于响应层，与客户端生命周期正交）。

---

## 八、附录：配置速查表

```bash
# ==================== 基础配置 ====================
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

*文档版本：v1.1（新增 LLM 客户端复用章节）*  
*维护者：aitester-maintenance-team*

---

## 九、性能剖析基准（2026-09-12 实测）

> 依据 `scripts/performance_profile.py` 的 cProfile / tracemalloc 实测数据归纳。

### 9.1 运行时逻辑高效，无 CPU 热点

- **ErrorClassifier 分类**：2500 次调用仅 0.025s（单次约 10μs），正则已预编译（`re.Pattern.search` 而非每次 `re.compile`），无"重复编译"开销
- **CodeAnalyzer AST 分析**：50 次循环 0.132s，`ast.walk` / `iter_child_nodes` 属 AST 遍历正常开销，无优化空间
- **BaseAgent JSON/代码提取**：解析逻辑近乎零开销，耗时全部来自模块首次 import

### 9.2 主要开销是第三方库 import（固有成本）

| 库 | 耗时 | 触发链 |
|----|------|--------|
| chromadb | ~0.6s | import workflow → retriever → chromadb |
| pandas + datasets | ~0.53s | import dataset_loader → datasets → pandas |
| openai + pydantic | ~0.9s | import base_agent/llm_client → langchain_openai → openai |

这些库均为项目核心依赖（RAG / 数据集 / LLM 调用），import 成本属固有开销，无法通过代码重构消除。

**可优化点评估**：延迟导入 chromadb / datasets 仅对"未启用 RAG / 不加载数据集"的场景省 0.5-0.6s 启动，但需改动 workflow 多个节点函数的可用性检查，收益有限、风险偏高，当前不实施。

### 9.3 内存

tracemalloc 实测三个被测模块的内存增量均 < 0.01 MB，无异常，无需专项优化。

### 9.4 结论

项目当前**无低垂果实式的性能优化点**，性能方向以保持现状为主；启动耗时瓶颈在第三方库 import 固有成本，运行时无 CPU 热点与内存泄漏。

---

## 十、Docker 隔离执行与依赖缓存（4.3 + 4.4）

### 10.1 背景

venv 沙箱（`EXECUTOR_USE_VENV=true`）按依赖组合在 `~/.cache/aitester/venvs/` 创建隔离 venv。首次运行需 `pip install` 缺失依赖（网络 + 安装耗时），后续同依赖组合任务命中磁盘缓存（仅 venv 创建，不重装依赖）。但 venv 创建仍有固定开销（`python -m venv` 初始化 + pip 元数据解析），且不同任务依赖组合差异大时缓存命中率低。

Docker 隔离执行（`EXECUTOR_USE_DOCKER=true`）将依赖预安装缓存在镜像构建期（Docker 层缓存复用），运行时通过 `docker run --rm -v <sandbox>:/workspace` 挂载卷传入被测代码，每任务零安装开销。

### 10.2 执行模式选择

| 模式 | 适用场景 | 首次开销 | 稳态开销 | 依赖隔离 | 凭证隔离 |
|------|---------|---------|---------|---------|---------|
| 本地（默认） | 快速验证、单任务 | 无 | 低 | ❌ | ❌（子进程已剔除 LLM API 凭证） |
| venv 沙箱 | 含第三方依赖的实验 | 高（pip install） | 中（venv 创建） | ✅ | ✅ |
| Docker | 发表级批量实验 | 高（镜像构建一次） | 低（卷挂载） | ✅ | ✅（容器级隔离） |

**选择依据**：单任务 / 快速迭代用本地；SWE-bench 等含第三方依赖用 venv；大规模并行（`BENCHMARK_PARALLELISM > 1`）且依赖稳定用 Docker。

### 10.3 Docker 配置

```bash
# 构建镜像（首次；依赖预安装在构建期完成，层缓存复用）
docker build -t aitester:latest .

# 启用 Docker 隔离执行
EXECUTOR_USE_DOCKER=true python main.py run examples/calculator.py

# 指定自定义镜像（如预装特定依赖的版本）
EXECUTOR_USE_DOCKER=true EXECUTOR_DOCKER_IMAGE=aitester:with-pandas \
    python main.py run examples/calculator.py
```

**诊断行为**：docker CLI 不可用（未安装 / daemon 未运行）时任务提前返回 `docker_unavailable` 诊断（`error_info.type`），**不静默降级本地执行**——避免实验口径混淆（Docker 与本地的环境差异会影响失败归因）。

**执行时间对比**：
```bash
# 同一任务分别跑 Docker / venv 两种模式，输出 Markdown 对比表
python scripts/compare_executor_modes.py \
    --tasks examples/calculator.py examples/string_utils.py
```

### 10.4 依赖缓存监控（4.4）

venv 缓存的命中率统计与清理已纳入分析层：

```bash
# 查看现有缓存与命中率（--list-only 只读）
python main.py clean-venv-cache --list-only

# 按时间清理（30 天前的 venv）
python main.py clean-venv-cache --max-age-days 30

# 按大小清理（超过 512MB 的 venv）
python main.py clean-venv-cache --max-size-mb 512

# 编程获取命中率（analyze_results.py 自动渲染"依赖缓存命中统计（4.4）"章节）
python -c "from src.tools.dependency import get_venv_cache_stats; print(get_venv_cache_stats())"
# → {"hits": N, "creates": M, "hit_rate": R}
```

**缓存目录覆盖**：默认 `~/.cache/aitester/venvs/`；容器 / CI 隔离场景经 `AITESTER_VENV_CACHE_DIR` 指向挂载卷（如 `/workspace/.venv_cache`），避免缓存随容器销毁丢失。

**命中率解读**：`hit_rate = hits / (hits + creates)`。新实验（首次跑某依赖组合）命中率低属正常；重跑同组合时命中率应趋近 1.0。若长期低命中率，检查 `AITESTER_VENV_CACHE_DIR` 是否指向持久化卷。

### 10.4b 多版本 venv 缓存（4.4）

不同 Python 版本的依赖包二进制不兼容（如 `numpy` / `pandas` 的 C 扩展）。`venv_cache_dir` 默认将 `sys.version_info` 前两位纳入缓存 key，不同版本的 venv 隔离存放（`py3.10` / `py3.12` 前缀），避免交叉复用导致 `ImportError` / 段错误：

```python
from src.tools.dependency import venv_cache_dir

# 默认：取当前解释器版本（如 3.14 → py3.14 前缀）
d = venv_cache_dir(["pandas"])
# → ~/.cache/aitester/venvs/py3.14_<digest>_pandas

# 显式指定 Python 版本（容器 / 多版本共存场景）
d_310 = venv_cache_dir(["pandas"], python_version="3.10")
d_312 = venv_cache_dir(["pandas"], python_version="3.12")
# 三者互不相同，venv 隔离存放
```

**行为说明**：
- 相同依赖组合 + 相同 Python 版本 → 复用同一 venv（命中缓存）
- 不同 Python 版本 → 不同目录，零交叉
- `create_venv` 创建 venv 时若目录已存在且 `python_version` 匹配，直接复用（不重建）

### 10.5 子进程环境凭证剔除（4.1 安全加固，2026-09-24 动态模式化）

ExecutorAgent 在本地 / venv / Docker 三种模式下，子进程环境均剔除 LLM API 凭证。这堵住"生成代码继承宿主环境凭证"的泄露面——被测代码 / 生成的测试代码无法通过 `os.environ` 访问 LLM 密钥。

三条链路统一走 `src/utils/credential_scrub.py` 的 `scrub_os_environ()`（单一实现，避免名单漂移）：
- **动态模式**：`LLM_\d+_API_KEY` / `LLM_\d+_BASE_URL`（N 为 1-32，对齐 `config.py` 的 LLM provider 扫描口径）——覆盖 `LLM_1_API_KEY` 等全部编号，此前 venv/Docker 链路原样继承宿主 `os.environ`、本地链路只剔 7 个固定变量（覆盖不了 `LLM_N_*` 系列），现统一动态剔除；
- **通用 SDK 凭证固定名单**：`OPENAI_API_KEY` / `OPENAI_BASE_URL` / `ANTHROPIC_API_KEY` / `API_KEY` / `LLM_API_KEY` / `LLM_CONFIG_API_KEY`（保留历史口径）。
