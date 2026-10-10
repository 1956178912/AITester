# AITester 可复现实验环境
# 构建: docker build -t aitester:latest .
# 运行: docker run --rm -v $(pwd):/workspace aitester:latest python main.py run examples/calculator.py
# 注: LLM 密钥随挂载的 .env.local 生效，无需 -e 传递

FROM python:3.12-slim

# 安装系统依赖（pytest-cov 需要 gcc）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /workspace

# 先复制依赖文件以利用 Docker 层缓存。
# 版本锁定说明（2026-09-28 补充）：requirements.txt 内所有顶层依赖均以 == 锁定
# 到本地验证过的版本（与 requirements.lock 同步，由 scripts/gates/check_lock_sync.py 在
# CI 守卫一致性）。镜像构建期依赖预安装使用同一锁定版本，保证 Docker 隔离执行
# （4.3）与本地开发环境依赖完全一致，避免"镜像内旧版依赖 / 本地新版依赖"导致
# 难以排查的执行差异。升级依赖流程：先改 requirements.txt + 在 .venv 重新
# `pip freeze > requirements.lock`，跑全量测试后重建镜像。
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目代码
COPY . .

# 默认命令：运行 benchmark
CMD ["python", "experiments/run_benchmark.py"]
