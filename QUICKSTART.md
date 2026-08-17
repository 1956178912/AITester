# AITester 快速开始指南

## 1. 克隆仓库

```bash
git clone https://github.com/your-username/AITester.git
cd AITester
```

## 2. 安装依赖

```bash
# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

## 3. 配置环境变量

### 方式一：使用 .env.example（推荐）

```bash
# 复制非敏感配置模板
cp .env.example .env

# 编辑 .env 文件，填入你的配置
vim .env
```

### 方式二：使用 config.local.example（敏感配置）

```bash
# 复制敏感配置模板
cp config.local.example .env.local

# 编辑 .env.local 文件，填入 API Key
vim .env.local
```

## 4. 验证配置

```bash
# 测试 API 连接
python3 -c "from config import LLM_CONFIGS; print(f'已加载 {len(LLM_CONFIGS)} 个 LLM 配置')"
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
