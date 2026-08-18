# API 管理器扩展指南

## 📋 当前状态

- **已配置模型**: 9 个
- **支持规模**: 100+ 模型
- **健康检查**: 批量执行，自动故障转移

---

## 🚀 快速开始

### 1. 查看当前配置

```bash
# 列出所有模型
python expand_models.py list

# 或运行配置报告
PYTHONPATH=. .venv/bin/python src/config_manager.py
```

### 2. 添加单个模型

```bash
python expand_models.py add \
  --name qwen-plus \
  --url https://dashscope.aliyuncs.com/compatible-mode/v1 \
  --key sk-your-aliyun-key-here
```

### 3. 批量添加（推荐）

#### 方式 A: 使用 JSON 模板

1. 编辑 `models_template.json`，填入您的 API Keys
2. 运行批量添加：

```bash
python expand_models.py batch --json models_template.json
```

#### 方式 B: 使用 CSV 模板

1. 编辑 `models_template.csv`，填入您的 API Keys
2. 运行批量添加：

```bash
python expand_models.py batch --csv models_template.csv
```

### 4. 交互式添加

```bash
python expand_models.py interactive
```

---

## 📊 支持的平台

| 平台 | Base URL | API Key 变量 |
|------|----------|--------------|
| 阿里云百炼 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `ALIYUN_API_KEY` |
| Agnes AI 国内站 | `https://api.agnes-ai.cn/v1` | `AGNES_API_KEY` |
| BigModel 智谱 | `https://open.bigmodel.cn/api/paas/v4/` | `BIGMODEL_API_KEY` |
| DeepSeek 官方 | `https://api.deepseek.com/v1` | `DEEPSEEK_API_KEY` |

---

## 🔧 配置示例

### 阿里云百炼（通义千问系列）

```json
{
  "model_name": "qwen-max",
  "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
  "api_key": "sk-ws-YOUR_ALIYUN_KEY",
  "provider": "阿里云百炼"
}
```

**可用模型**:
- `qwen-max` - 最强性能
- `qwen-plus` - 平衡性能与成本
- `qwen-turbo` - 最快响应
- `qwen-long` - 长上下文（100K+）
- `deepseek-v3` - DeepSeek V3
- `deepseek-v4-pro` - DeepSeek V4 Pro
- `deepseek-v4-flash` - DeepSeek V4 Flash
- `kimi-k2.7-code` - Kimi 代码专用

### BigModel 智谱（GLM 系列）

```json
{
  "model_name": "glm-4-flash",
  "base_url": "https://open.bigmodel.cn/api/paas/v4/",
  "api_key": "your-bigmodel-key",
  "provider": "BigModel 智谱"
}
```

**可用模型**:
- `glm-4` - GLM-4 基础版
- `glm-4-plus` - GLM-4 Plus
- `glm-4-air` - GLM-4 Air（快速）
- `glm-4-flash` - GLM-4 Flash（最快）
- `glm-4.7` - GLM-4.7
- `glm-4.7-flash` - GLM-4.7 Flash

### Agnes AI

```json
{
  "model_name": "agnes-2.5-flash",
  "base_url": "https://api.agnes-ai.cn/v1",
  "api_key": "sk-JOrnkHNaQAGW08mwA8ZcNc8tRC55yHWX1A2pLpIjE5nnk6jN",
  "provider": "Agnes AI"
}
```

### DeepSeek 官方

```json
{
  "model_name": "deepseek-chat",
  "base_url": "https://api.deepseek.com/v1",
  "api_key": "sk-your-deepseek-key",
  "provider": "DeepSeek"
}
```

**可用模型**:
- `deepseek-chat` - 通用对话
- `deepseek-coder` - 代码专用

---

## 📈 扩展到 100+ 模型

### 步骤 1: 准备模型列表

创建一个包含所有模型的 JSON 文件：

```json
{
  "models": [
    {
      "model_name": "model-1",
      "base_url": "https://api1.example.com/v1",
      "api_key": "key-1",
      "provider": "Provider 1"
    },
    {
      "model_name": "model-2",
      "base_url": "https://api2.example.com/v1",
      "api_key": "key-2",
      "provider": "Provider 2"
    },
    // ... 添加更多模型
  ]
}
```

### 步骤 2: 批量导入

```bash
python expand_models.py batch --json your_models.json
```

### 步骤 3: 验证配置

```bash
python expand_models.py list
```

### 步骤 4: 健康检查

```bash
# 运行示例脚本进行健康检查
PYTHONPATH=. .venv/bin/python examples/api_manager_example.py
```

---

## 🎯 API 管理器使用

### 基础调用

```python
from src.api_manager import get_manager

manager = get_manager()

# 智能调用（自动选择最优节点）
response = manager.call(
    messages=[{"role": "user", "content": "你好"}],
    max_tokens=100
)

print(response.choices[0].message.content)
```

### 指定模型

```python
# 指定使用特定模型
response = manager.call(
    messages=[...],
    model="qwen-max"
)
```

### 查看状态

```python
# 打印状态表格
from src.api_manager import print_status_table
print_status_table(manager)

# 获取状态摘要
status = manager.get_status()
print(f"总模型: {status['total_nodes']}")
print(f"健康: {status['healthy_nodes']}")
```

### 切换策略

```python
from src.api_manager import RotationStrategy

manager.config.rotation_strategy = RotationStrategy.FASTEST_FIRST
```

---

## 🔍 故障排查

### 问题 1: 部分模型不可用

**原因**: API Key 无效或配额耗尽

**解决**:
```bash
# 查看哪些模型不健康
PYTHONPATH=. .venv/bin/python examples/api_manager_example.py

# 移除不可用模型
python expand_models.py remove model-name
```

### 问题 2: 限流频繁

**解决**:
```python
# 增加重试次数
from src.api_manager import APIManagerConfig, APIManger

config = APIManagerConfig(
    retry_count=5,  # 增加到 5 次重试
    fallback_on_failure=True
)
manager = APIManger(config=config)
```

### 问题 3: 响应慢

**解决**:
```python
# 使用最快优先策略
manager.config.rotation_strategy = RotationStrategy.FASTEST_FIRST

# 或查看 Top 5 最快的节点
top_nodes = manager.get_top_nodes(n=5, sort_by="response_time")
for node in top_nodes:
    print(f"{node['model']}: {node['avg_response_time_ms']:.0f}ms")
```

---

## 📝 最佳实践

### 1. 混合多个提供商

不要依赖单一提供商，混合使用：
- 阿里云百炼（主力）
- BigModel 智谱（备用）
- Agnes AI（快速响应）
- DeepSeek（代码专用）

### 2. 定期健康检查

```python
# 每天运行一次健康检查
manager.health_check_batch(batch_size=20)
```

### 3. 监控关键指标

```python
status = manager.get_status()
print(f"健康率: {status['healthy_nodes']/status['total_nodes']:.1%}")
```

### 4. 分级使用

- **重要任务**: 使用成功率最高的模型
- **快速任务**: 使用响应最快的模型
- **代码任务**: 使用代码专用模型（deepseek-coder, kimi-k2.7-code）
- **长文本**: 使用 qwen-long

---

## 🎓 高级用法

### 动态添加模型

```python
from config import LLMConfig
from src.api_manager import get_manager

manager = get_manager()

# 添加新模型
new_config = LLMConfig(
    api_key="new-key",
    base_url="https://new.api.com/v1",
    model_name="new-model"
)
manager.add_node(new_config)
```

### 自定义轮换策略

```python
from src.api_manager import RotationStrategy

# 轮询策略 - 均匀分布
manager.config.rotation_strategy = RotationStrategy.ROUND_ROBIN

# 加权随机 - 根据性能选择
manager.config.rotation_strategy = RotationStrategy.WEIGHTED_RANDOM

# 健康感知 - 综合评分最高
manager.config.rotation_strategy = RotationStrategy.HEALTH_BASED

# 最快优先 - 响应最快（适合大规模节点池）
manager.config.rotation_strategy = RotationStrategy.FASTEST_FIRST
```

---

## 📦 交付清单

- [x] `src/api_manager.py` - 核心模块
- [x] `src/config_manager.py` - 配置管理
- [x] `src/config_generator.py` - 配置生成器
- [x] `expand_models.py` - 扩展脚本
- [x] `models_template.json` - JSON 模板
- [x] `models_template.csv` - CSV 模板
- [x] `examples/api_manager_example.py` - 使用示例
- [x] 本文档

---

**提示**: 您可以先使用模板文件，填入实际的 API Keys，然后运行批量导入命令即可快速扩展到 100+ 模型！
