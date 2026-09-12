# AITester 快速开始指南

## 1. 克隆仓库

```bash
git clone https://github.com/1956178912/AITester.git
cd AITester
```

## 2. 安装依赖

```bash
# 创建虚拟环境（Python 3.12+；锁定依赖 scipy 要求 ≥3.12）
python3 -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

## 3. 配置环境变量

> 两步都要做：步骤一配置非敏感项，步骤二配置 LLM 密钥（可跳过步骤一使用默认值，但密钥必须配）。

### 步骤一：非敏感配置（.env）

```bash
# 复制非敏感配置模板
cp .env.example .env

# 按需调整（如 TEMPERATURE）
vim .env
```

### 步骤二：LLM 密钥（.env.local，必须）

```bash
# 复制敏感配置模板
cp config.local.example .env.local

# 编辑 .env.local 文件，填入 LLM_N_API_KEY 等
vim .env.local
```

## 4. 验证配置已加载

```bash
# 仅校验配置加载（无网络调用）：成功打印加载的 LLM 配置数即可
python3 -c "from config import LLM_CONFIGS; print(f'已加载 {len(LLM_CONFIGS)} 个 LLM 配置')"

# 如需真实探测各模型 API 连通性与额度（每个仅 1 token），用第 6 步的脚本：
# python scripts/check_quota.py
```

## 5. 运行测试

```bash
# 列出示例文件
python3 main.py list-examples

# 测试单个文件
python3 main.py run examples/calculator.py --func add

# 并发测试多个文件
python3 main.py run examples/calculator.py examples/string_utils.py --parallel=2
```

## 6. 可选：模型额度探测与省 token 缓存

LLM 调用默认开启文件缓存（`src/cache/`，命中相同 prompt 不再消耗 token）。在「免费额度用完即停」的供应商下可延长可用时长。

```bash
# 探测各已配置模型哪些还活着、哪些 403 额度用尽（每个仅 1-token，不打印 key）
python scripts/check_quota.py

# 关闭缓存 / 清缓存
export AITESTER_LLM_CACHE=0
rm -rf src/cache
```

## 7. 可选：高级开关（默认全部关闭，不影响常规使用）

以下开关均默认关闭，按需启用（详见 `.env.example` 注释）：

```bash
# 结构化 JSONL 追踪（4.1）：每任务落 <task_uuid>.trace.jsonl，
# 记录各智能体节点决策/token/耗时，供实验分析回放。未设置时全 no-op。
export AITESTER_TRACE_DIR=./trace_out

# 多候选补丁（3.1）：Debugger 一轮生成 N 个候选补丁，静态+执行验证选最优。
export ENABLE_MULTI_CANDIDATE_PATCH=true
export MULTI_CANDIDATE_COUNT=3
export MULTI_CANDIDATE_EXEC_VALIDATE=true   # 逐候选跑测试筛选（成本更高）

# 成本感知路由（3.4）：COST_AWARE 策略避免故障转移全量切到昂贵 provider。
# 各 provider 相对成本倍数在 .env.local 以 LLM_N_COST_WEIGHT 配置。
# 成本告警阈值可配（3.2）：转移到 cost_weight >= 阈值（默认 2.0）的昂贵节点时记 WARNING，
# 阈值过低导致误报多时上调（如 3.0/5.0），成本敏感度高时下调，无需改代码：
from src.api.api_manager import APIManager, APIManagerConfig
manager = APIManager(config=APIManagerConfig(cost_alert_threshold=3.0))

# 熔断冷却期 + 半开探测（4.1 + 4.2）：APIManager 节点连续失败达
# max_consecutive_failures 阈值后自动进入冷却期（circuit_cooldown_seconds，默认 60s），
# 冷却期内即使健康检查翻回 is_healthy=True 路由层也继续跳过该节点。
# 4.2：冷却到期后节点进入"半开"窗口，仅承载一次探测请求；探测成功闭合
# 熔断器恢复全量路由，失败重开半程冷却（min(cooldown/2, cap=30s)）。
# 半开探测默认开启（enable_half_open_probe=True）；对比实验可退回 4.1 直接放行：
from src.api.api_manager import APIManager, APIManagerConfig
manager = APIManager(config=APIManagerConfig(
    circuit_cooldown_seconds=120.0,
    # 可选：关闭半开探测退回 4.1 行为（默认 True）
    enable_half_open_probe=False,
    # 可选：半开探测失败惩罚时长上限（默认 30.0s）
    # half_open_probe_penalty_cap_seconds=60.0,
))

# RAG（检索增强）：合成/内置数据集实验可显式开启
python experiments/run_benchmark.py --dataset synthetic --enable-rag

# 3.5 跨文件修复（默认关）：启用后 workflow 在 executor → debugger 之间插入
# cross_file_analyzer 节点，分析被测代码的跨文件 import 依赖关系，
# 多文件补丁按拓扑序应用（被调用方先改，调用方后改），失败整体回滚。
# 单文件项目自动降级（依赖边为空时走单文件路径）。
export CROSS_FILE_ENABLE=true
export CROSS_FILE_MAX_MODULES=5

# 3.4 断言增强（默认关）：Generator 在生成前先 AST 提取被测代码中已有
# assert 语句，作为"锚点断言"注入 prompt，避免断言弱化 / 恒真断言 / 魔数异味。
export ASSERTION_AUGMENT_ENABLE=true

# 结果分析（4.3 + 1.1/1.2/1.3 指标增强）：跑完 benchmark 后生成 Markdown 汇总，
# 含成功率 / token 效率 / 迭代分布 / 失败原因分布 / RAG 质量 /
# 修复收敛效率（首次尝试成功率、成功与失败任务的迭代及耗时统计）/
# 修复收敛曲线（按迭代轮次 0/1/2/3+ 累计通过率与耗时）/
# 测试异味检测（Assertion Roulette / Magic Number / 断言弱化 / 平凡测试）/
# 多维质量代理（覆盖率、耗时、可选 generated_test 的断言行数、失败类别 Top N）。
# 旧 JSON 缺 token_metrics / rag_metrics / generated_test 键时自动兜底或降级，不崩。
python experiments/analyze_results.py --results-dir experiments/results

# 失败根因分类 + 案例知识库（5.3）：按 LLM 能力 / 依赖 / 框架三大根因归因，
# 结构化案例落盘 failure_knowledge_base.json（含 task_id / root_cause / 复现步骤 / 建议修复）。
python experiments/analyze_failures.py --results-dir experiments/results
python experiments/analyze_failures.py -r experiments/results -k experiments/results/failure_knowledge_base.json

# 4.4 依赖缓存监控：venv 缓存命中率统计 + 清理
from src.tools.dependency import get_venv_cache_stats, clear_venv_cache
print(get_venv_cache_stats())          # {"hits": N, "creates": M, "hit_rate": ...}
clear_venv_cache(max_age_days=30)      # 清理 30 天前的 venv 缓存
```

## 配置文件说明

| 文件 | 说明 | Git 状态 |
|------|------|---------|
| `.env.example` | 非敏感配置模板 | ✅ 已提交 |
| `config.local.example` | 敏感配置模板（API Key） | ✅ 已提交 |
| `.env` | 实际配置（需自行创建） | ❌ 已排除 |
| `.env.local` | 实际敏感配置（需自行创建） | ❌ 已排除 |

## 注意事项

1. **不要提交 `.env` 和 `.env.local` 到 Git**
2. 从 `.env.example` 和 `config.local.example` 创建你的配置文件
3. 确保 API Key 安全存储，不要分享给他人
