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

# RAG（检索增强）：合成/内置数据集实验可显式开启
python experiments/run_benchmark.py --dataset synthetic --enable-rag
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
