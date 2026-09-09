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

# 先复制依赖文件以利用 Docker 层缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目代码
COPY . .

# 默认命令：运行 benchmark
CMD ["python", "experiments/run_benchmark.py"]
