# 快速开始

> 最后更新：2026-10-27 · English: [QUICKSTART.en.md](QUICKSTART.en.md)

## 1. 安装

需要 Python 3.12+（`scipy` 的下限决定）。

```bash
python3 -m venv .venv
source .venv/bin/activate
make install
cp .env.example .env                   # 非敏感配置（可选）
cp config.local.example .env.local     # LLM 配置模板
```

也可以一键引导：`bash scripts/tools/bootstrap_dev.sh`（创建 venv、装依赖、复制两个
env 模板并校验配置加载；完成后编辑 `.env.local` 填入真实值）。

## 2. 配置 LLM

`.env.local` 只填值，变量名固定：

| 变量 | 用途 |
|---|---|
| `LLM_1_API_KEY` | API Key |
| `LLM_1_BASE_URL` | OpenAI 兼容端点 |
| `LLM_1_MODEL_NAME` | 模型名 |

`1` 可替换为其它编号以配置多个端点；内置 provider 仅 DeepSeek 官方端点。
`.env.local` 已被 git 忽略，不要把真实密钥写进任何被跟踪的文件。

## 3. 第一个任务

```bash
make test                    # 先验证环境与依赖
python3 main.py list-examples
python3 main.py run examples/calculator.py --func add
```

`main.py run` 会调用 LLM，消耗配额。纯离线自检用：

```bash
bash scripts/tools/smoke_test.sh --no-llm --skip-lint
```

## 4. 沙箱与安全

- 执行隔离：`EXECUTOR_USE_VENV` **默认开启**（R10 起），LLM 生成的代码在 venv 沙箱中执行。
- Docker / 内核级沙箱为显式启用；平台不支持时 **fail-closed** 拒绝执行。
- 三条执行链路统一剔除 LLM 凭证，日志三层脱敏。
- 设 `EXECUTOR_USE_VENV=false` 只在本地调试时使用。

## 5. 遇到问题

按症状查 [docs/troubleshooting.md](docs/troubleshooting.md)：
安装与环境 → 运行与沙箱 → 测试与门禁。提交前跑 `make gates`（单链）。
