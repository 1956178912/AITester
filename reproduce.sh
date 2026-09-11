#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# AITester 实验复现脚本
#
# 用法：
#   bash reproduce.sh                    # 快速模式（3 个任务，内置示例数据集）
#   bash reproduce.sh --full             # 完整模式（全部任务）
#   bash reproduce.sh --dataset swe_bench  # 使用 SWE-bench 数据集
#   bash reproduce.sh --quick --verbose  # 快速模式 + 详细日志
#
# 所有命令在项目根目录（本脚本所在目录）下执行
# ═══════════════════════════════════════════════════════════════════════════════

# 严格模式：命令失败时立即退出；未定义变量时报错；管道失败时也报错
set -euo pipefail

# 获取脚本所在目录的绝对路径，并切换到该目录
# 确保无论从哪里调用脚本，工作目录始终是项目根目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ─── 颜色输出配置 ───────────────────────────────────────────────────────────────
# 用 ANSI 转义码定义彩色输出，提升终端可读性
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'  # 无色（重置）

# 封装日志函数：INFO=绿色，WARN=黄色，ERROR=红色+退出
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ─── 参数解析 ───────────────────────────────────────────────────────────────────
# 默认参数值
MODE="quick"        # quick | full：控制任务数量
DATASET="examples"  # examples | swe_bench | synthetic：数据集选择
TASK_LIMIT=3        # 由 MODE 决定（quick=3，full=不限）；默认 quick 即 3，与文档一致
BASELINES="aitester,plain_llm,single_agent"  # 基线方法列表
VERBOSE=""          # 是否输出详细日志
ENABLE_RAG=""       # 2.3 RAG 纳入主实验：默认对合成/内置数据集显式开启 RAG

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --quick)     MODE="quick"; TASK_LIMIT=3; shift ;;
        --full)      MODE="full";  TASK_LIMIT="";  shift ;;
        --dataset)   DATASET="$2"; shift 2 ;;
        --baselines) BASELINES="$2"; shift 2 ;;
        --no-rag)    ENABLE_RAG="--no-rag"; shift ;;
        --verbose|-v) VERBOSE="-v"; shift ;;
        *) error "未知参数: $1" ;;
    esac
done

# 2.3 RAG 纳入主实验（消融公平性）：合成/内置数据集默认显式开启 RAG，
# 使"完整系统 vs Plain LLM"的对比包含检索增强效果；rag_data/ 持久化目录
# 跨实验复用（config.RAG_PERSIST_PATH 默认项目下 rag_data/）。
# 用户可用 --no-rag 回退到 config.ENABLE_RAG（默认 false）口径。
if [[ "$DATASET" == "synthetic" || "$DATASET" == "examples" ]]; then
    if [[ -z "$ENABLE_RAG" ]]; then
        ENABLE_RAG="--enable-rag"
        info "数据集 '$DATASET' 默认开启 RAG（检索增强 + rag_data/ 持久化，2.3）"
    fi
else
    ENABLE_RAG=""
fi

info "模式: $MODE  |  数据集: $DATASET  |  基线: $BASELINES"
[[ -n "$TASK_LIMIT" ]] && info "任务限制: $TASK_LIMIT"
[[ -n "$ENABLE_RAG" ]] && info "RAG: 显式开启（--enable-rag）"

# ─── 步骤 1/6：检查运行环境 ─────────────────────────────────────────────────────
info "Step 1/6: 检查环境..."

# 检查 Python 3.12+ 是否安装（锁定依赖 scipy==1.18.0 要求 >=3.12）
if ! command -v python3 &>/dev/null; then
    error "未找到 python3，请安装 Python 3.12+"
fi

PYTHON_BIN="$(command -v python3)"
info "Python: $PYTHON_BIN ($("$PYTHON_BIN" --version 2>&1))"

# 检查/创建虚拟环境（.venv）
if [[ ! -d ".venv" ]]; then
    warn ".venv 不存在，正在创建 Python 虚拟环境..."
    python3 -m venv .venv
fi

# 激活虚拟环境（使后续 pip/python 命令使用虚拟环境中的解释器）
source .venv/bin/activate
info "虚拟环境: $(which python)"

# 检查 .env 基础配置（非敏感项；敏感 LLM Key 在 .env.local，见下方检查）
if [[ ! -f ".env" ]]; then
    if [[ -f ".env.example" ]]; then
        warn ".env 不存在，已从 .env.example 复制"
        cp .env.example .env
    fi
fi

# 检查 .env.local LLM 敏感配置（模板为 config.local.example；
# 旧变量 OPENAI_API_KEY 已不再被系统读取，现使用 LLM_N_* 编号格式）
if [[ ! -f ".env.local" ]]; then
    if [[ -f "config.local.example" ]]; then
        warn ".env.local 不存在，已从 config.local.example 复制（请填入 LLM_1_API_KEY 后再运行）"
        cp config.local.example .env.local
    else
        warn "未找到 .env.local 与 config.local.example，请在项目根目录创建 .env.local 并配置 LLM_1_API_KEY"
    fi
elif grep -qE "^\s*#\s*LLM_1_API_KEY" .env.local || grep -qE "^\s*LLM_1_API_KEY\s*=(\s*|<)" .env.local; then
    warn "LLM_1_API_KEY 未设置或仍为占位值，请在 .env.local 中填入真实 API Key"
fi

# ─── 步骤 2/6：安装 Python 依赖 ──────────────────────────────────────────────────
info "Step 2/6: 安装/升级依赖..."
# 安装 requirements.txt 中的核心依赖（-q 静默模式）
pip install -q -r requirements.txt
# 额外安装实验统计可视化依赖（scipy/matplotlib/pandas）
pip install -q scipy matplotlib pandas

# ─── 步骤 3/6：运行单元测试 ──────────────────────────────────────────────────────
info "Step 3/6: 运行单元测试..."
# 先确保日志目录存在（tee 重定向在管道前求值，目录缺失会直接失败）
mkdir -p experiments/results
# 运行所有 tests/ 下的 pytest 用例，输出到 log 文件便于排查
# pipefail + set -e 下管道失败会直接终止脚本，用 || 捕获退出码改为告警继续
TEST_EXIT=0
python -m pytest tests/ -v --tb=short 2>&1 | tee experiments/results/test_output.log || TEST_EXIT=$?
if [[ $TEST_EXIT -ne 0 ]]; then
    warn "部分单元测试失败，但继续执行（可能依赖 LLM API 可用性）"
fi

# ─── 步骤 4/6：准备数据集 ────────────────────────────────────────────────────────
if [[ "$DATASET" == "swe_bench" ]]; then
    info "Step 4/6: 下载 SWE-bench 数据集..."
    if [[ "$MODE" == "quick" ]]; then
        SUBSET="mini"       # 50 个任务，快速验证
        SUBSET_DESC="mini (50 tasks)"
    else
        SUBSET="lite"       # 500 个任务，标准实验
        SUBSET_DESC="lite (500 tasks)"
    fi
    # 从 HuggingFace 自动下载数据集到 ~/.cache/aitester/swe_bench/
    python -c "
from src.datasets.dataset_loader import SWEBenchDataset
path = SWEBenchDataset.download_from_huggingface(subset='$SUBSET')
print(f'已下载到: {path}')
"
elif [[ "$DATASET" == "examples" ]]; then
    info "Step 4/6: 使用内置示例数据集（无需下载，包含 3 个预定义 bug 任务）"
else
    warn "未知数据集 '$DATASET'，回退到 examples"
    DATASET="examples"
fi

# ─── 步骤 5/6：运行基准测试 ───────────────────────────────────────────────────────
info "Step 5/6: 运行基准测试..."
mkdir -p experiments/results

# 构建任务数量限制参数
TASK_LIMIT_ARG=""
[[ -n "$TASK_LIMIT" ]] && TASK_LIMIT_ARG="--task-limit $TASK_LIMIT"

# 运行多基线对比实验（自动保存 JSON 结果到 experiments/results/）
# 2.3 RAG：$ENABLE_RAG 在合成/内置数据集默认设为 --enable-rag（见参数解析段）
python experiments/run_benchmark.py \
    --dataset "$DATASET" \
    --baselines "$BASELINES" \
    $TASK_LIMIT_ARG \
    $ENABLE_RAG \
    --output-dir experiments/results \
    $VERBOSE

BENCH_EXIT=$?
if [[ $BENCH_EXIT -ne 0 ]]; then
    error "基准测试失败，请检查 experiments/results/test_output.log"
fi

# ─── 步骤 6/6：生成可视化图表 ────────────────────────────────────────────────────
info "Step 6/6: 生成结果可视化..."
# 生成柱状图、统计检验图、CSV 表格和 Markdown 汇总报告
python experiments/visualize_results.py

# ─── 完成 ────────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  ✅ 实验复现完成！${NC}"
echo -e "${GREEN}══════════════════════════════════════════════════${NC}"
echo ""
echo "结果文件位置:"
echo "  📊 实验结果(JSON):  experiments/results/benchmark_*.json"
echo "  📈 对比柱状图:      experiments/results/charts/baseline_comparison.png"
echo "  📉 统计检验图:      experiments/results/charts/statistical_significance.png"
echo "  📋 详细表格(CSV):   experiments/results/charts/results_table.csv"
echo "  📝 汇总报告(MD):    experiments/results/charts/summary_stats.md"
echo ""
echo "下一步建议:"
echo "  1. 打开 summary_stats.md 查看统计检验结果（p 值、Cohen's d）"
echo "  2. 如需运行更多任务，使用 --full 参数"
echo "  3. 如需完整 SWE-bench 实验，使用 --dataset swe_bench --full"
echo ""
