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
# 所有命令在 /Users/wangchenyu/workspace/AITester 目录下执行
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
DATASET="examples"  # examples | swe_bench：数据集选择
TASK_LIMIT=""       # 由 MODE 决定（quick=3，full=不限）
BASELINES="aitester,plain_llm,single_agent"  # 基线方法列表
VERBOSE=""          # 是否输出详细日志

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --quick)     MODE="quick"; TASK_LIMIT=3; shift ;;
        --full)      MODE="full";  TASK_LIMIT="";  shift ;;
        --dataset)   DATASET="$2"; shift 2 ;;
        --baselines) BASELINES="$2"; shift 2 ;;
        --verbose|-v) VERBOSE="-v"; shift ;;
        *) error "未知参数: $1" ;;
    esac
done

info "模式: $MODE  |  数据集: $DATASET  |  基线: $BASELINES"
[[ -n "$TASK_LIMIT" ]] && info "任务限制: $TASK_LIMIT"

# ─── 步骤 1/6：检查运行环境 ─────────────────────────────────────────────────────
info "Step 1/6: 检查环境..."

# 检查 Python 3.10+ 是否安装
if ! command -v python3 &>/dev/null; then
    error "未找到 python3，请安装 Python 3.10+"
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

# 检查 .env 配置文件
if [[ ! -f ".env" ]]; then
    if [[ -f ".env.example" ]]; then
        warn ".env 不存在，从 .env.example 复制（请手动填入 API Key 后再运行）"
        cp .env.example .env
    else
        error "未找到 .env.example，无法继续"
    fi
fi

# 校验必需环境变量 OPENAI_API_KEY 是否已设置
for var in OPENAI_API_KEY; do
    val="${!var:-}"
    if [[ -z "$val" || "$val" == "<YOUR_API_KEY_HERE>" || "$val" == "<OPENAI_API_KEY>" ]]; then
        warn "环境变量 $var 未设置，请在 .env 中填入真实值"
    fi
done

# ─── 步骤 2/6：安装 Python 依赖 ──────────────────────────────────────────────────
info "Step 2/6: 安装/升级依赖..."
# 安装 requirements.txt 中的核心依赖（-q 静默模式）
pip install -q -r requirements.txt
# 额外安装实验统计可视化依赖（scipy/matplotlib/pandas）
pip install -q scipy matplotlib pandas

# ─── 步骤 3/6：运行单元测试 ──────────────────────────────────────────────────────
info "Step 3/6: 运行单元测试..."
# 运行所有 tests/ 下的 pytest 用例，输出到 log 文件便于排查
python -m pytest tests/ -v --tb=short 2>&1 | tee experiments/results/test_output.log
TEST_EXIT=$?
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
from src.dataset_loader import SWEBenchDataset
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
python experiments/run_benchmark.py \
    --dataset "$DATASET" \
    --baselines "$BASELINES" \
    $TASK_LIMIT_ARG \
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
