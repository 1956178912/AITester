#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# AITester 实验复现脚本
#
# 用法：
#   bash reproduce.sh                    # 快速模式（3 个任务，内置示例数据集）
#   bash reproduce.sh --full             # 完整模式（全部任务）
#   bash reproduce.sh --dataset swe_bench  # 使用 SWE-bench 数据集
#   bash reproduce.sh --dataset synthetic --full  # 合成数据集主批口径（87 任务，
#                                        # max-pattern-repeat=2，seed=42，三臂）
#   bash reproduce.sh --quick --verbose  # 快速模式 + 详细日志
#
# A02（2026-10-18 第三方审查，P1）：数据集口径 fail-closed——只支持
# examples / swe_bench / synthetic；未知 --dataset 立即报错退出（历史行为是
# 静默回退 examples，这与 REPLICATION.md 推荐 `--dataset synthetic --full`
# 的"主批复现"承诺矛盾：实际跑的是 3 任务示例集）。
#
# P1（2026-10 Docker 化实验复现）：任意批次可用 Docker 一条命令复现，
# 结果 JSON 自带 environment provenance 块（git sha / python 版本 /
# 容器标记），由 Dockerfile.repro 构建的镜像执行：
#   docker build --build-arg GIT_SHA=$(git rev-parse HEAD) \
#         -f Dockerfile.repro -t aitester-repro:$(git rev-parse --short HEAD) .
#   docker run --rm -v $(pwd)/experiments/results:/workspace/experiments/results \
#         -v $(pwd)/.env.local:/workspace/.env.local:ro \
#         aitester-repro:<sha> bash reproduce.sh --dataset synthetic --full
#   （容器内 .git 被 .dockerignore 排除；run_benchmark 读取 .repro_provenance
#    的 GIT_SHA 作为 provenance 来源——见 A03 修复）
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
DATASET="examples"  # examples | swe_bench | synthetic：数据集选择（未知值 fail-closed）
TASK_LIMIT=3        # 由 MODE 决定（quick=3，full=不限）；默认 quick 即 3，与文档一致
TASK_COUNT=""       # synthetic 任务数透传（run_benchmark --task-count）；空=按 MODE 默认
MAX_PATTERN_REPEAT=""  # synthetic 同池模板重复上限（run_benchmark --max-pattern-repeat）
SEED="42"           # 数据采样/合成种子（run_benchmark --seed；主批默认 42）
BASELINES="aitester,plain_llm,single_agent"  # 基线方法列表
BASELINES_USER_SET="false"  # 是否由用户显式 --baselines 指定
VERBOSE=""          # 是否输出详细日志
# 2.3 RAG：W7（2026-10-05 审查落地·阴性证据驱动）默认关闭——RAG A/B 对照实验
#（experiments/results/rag_ab_*，docs/experiment_ab_results_2026-09-28.md）实测
# token +40.7% 负向、成功率无显著增益；此前"合成/内置数据集默认 --enable-rag"
# 的口径不再成立。需要 RAG 对照时显式 --enable-rag；--no-rag 保留为兼容参数（空操作）。
ENABLE_RAG=""
# 3.1 多候选补丁：W7（2026-10-05 审查落地·阴性证据驱动）默认关闭——A/B 实测
# 成功率 -2pp 且 token +256%（experiments/results/multi_candidate*）。需要时显式
# --multi-candidate；--no-multi-candidate 保留为兼容参数（空操作）。
MULTI_CANDIDATE="false"
# 3.5 跨文件修复：默认关闭（保持历史单文件口径），--cross-file 显式启用
CROSS_FILE=""       # 默认空 = 关闭；--cross-file 时设为 true

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --quick)     MODE="quick"; TASK_LIMIT=3; shift ;;
        --full)      MODE="full";  TASK_LIMIT="";  shift ;;
        --dataset)   DATASET="$2"; shift 2 ;;
        --task-count) TASK_COUNT="$2"; shift 2 ;;
        --max-pattern-repeat) MAX_PATTERN_REPEAT="$2"; shift 2 ;;
        --seed)      SEED="$2"; shift 2 ;;
        --baselines) BASELINES="$2"; BASELINES_USER_SET="true"; shift 2 ;;
        --enable-rag) ENABLE_RAG="--enable-rag"; shift ;;
        --no-rag)    ENABLE_RAG=""; shift ;;
        --multi-candidate) MULTI_CANDIDATE="true"; shift ;;
        --no-multi-candidate) MULTI_CANDIDATE="false"; shift ;;
        --cross-file) CROSS_FILE="true"; shift ;;
        --no-cross-file) CROSS_FILE="false"; shift ;;
        --verbose|-v) VERBOSE="-v"; shift ;;
        *) error "未知参数: $1" ;;
    esac
done

# ─── A02（2026-10-18 第三方审查，P1）：数据集口径 fail-closed + synthetic 分支 ──
# 历史行为：未知 --dataset 静默回退 examples。REPLICATION.md 推荐
# `reproduce.sh --dataset synthetic --full` 作为主批复现入口，但脚本无 synthetic
# 分支 → 实际跑 3 任务示例集，"主批复现"承诺落空。现口径：
#   1. 只接受 examples / swe_bench / synthetic（synth 归一为 synthetic）；
#   2. 其余 --dataset 立即报错退出（fail-closed，不替换数据集）；
#   3. synthetic：quick 默认 3 任务；full 默认复现主批入口参数
#      `--task-count 87 --max-pattern-repeat 2 --seed 42` + 主批三臂
#      （aitester/plain_llm/plain_llm_df，用户显式 --baselines 可覆盖）。
#      与主批"3 seed（42/43/44）"完整协议的区别：本脚本单次运行单 seed；
#      三种子协议入口是 experiments/run_main_batch.py / run_t1_b2_main_batch.sh，
#      不同 seed 批次不可直接合并统计（见 REPLICATION.md §6 已知偏差）。
case "$DATASET" in
    examples|swe_bench) ;;
    synthetic|synth) DATASET="synthetic" ;;
    *)
        error "未知数据集: ${DATASET}（支持: examples | swe_bench | synthetic；其他真实数据集请直接用 experiments/run_benchmark.py --dataset <name>）"
        ;;
esac

if [[ "$DATASET" == "synthetic" ]]; then
    if [[ -z "$TASK_COUNT" ]]; then
        if [[ "$MODE" == "full" ]]; then
            TASK_COUNT=87
        else
            TASK_COUNT=3
        fi
    fi
    if [[ "$MODE" == "full" && -z "$MAX_PATTERN_REPEAT" ]]; then
        MAX_PATTERN_REPEAT=2
    fi
    if [[ "$MODE" == "full" && "$BASELINES_USER_SET" != "true" ]]; then
        # 主批次臂集（benchmark_synthetic_20261006_140906.json: baselines 三臂）
        BASELINES="aitester,plain_llm,plain_llm_df"
    fi
    # synthetic 规模由 --task-count 控制；清空 --task-limit 避免二次截断
    # （quick 模式默认 --task-limit 3 会覆盖用户显式 --task-count 的意图）。
    TASK_LIMIT=""
    info "synthetic 参数: --task-count $TASK_COUNT --seed $SEED${MAX_PATTERN_REPEAT:+ --max-pattern-repeat $MAX_PATTERN_REPEAT}"
fi

# 2.3 RAG（W7 口径，2026-10-05）：默认关闭（阴性证据：token +40.7% 无成功率
# 增益，见 rag_ab A/B 对照）；显式 --enable-rag 时开启（rag_data/ 持久化目录
# 跨实验复用，config.RAG_PERSIST_PATH 默认项目下 rag_data/）。
if [[ -n "$ENABLE_RAG" ]]; then
    info "RAG: 显式开启（--enable-rag，rag_data/ 持久化）"
else
    ENABLE_RAG=""
    info "RAG: 默认关闭（W7 阴性证据口径；--enable-rag 显式开启）"
fi

info "模式: $MODE  |  数据集: $DATASET  |  基线: $BASELINES"
[[ -n "$TASK_LIMIT" ]] && info "任务限制: $TASK_LIMIT"
[[ -n "$ENABLE_RAG" ]] && info "RAG: 显式开启（--enable-rag）"

# 3.1 多候选补丁（W7 口径，2026-10-05）：默认关闭（阴性证据：成功率 -2pp、
# token +256%）；显式 --multi-candidate 开启（多候选 + 静态筛选），
# 与单补丁口径的 A/B 对照经该开关一键切换。
export ENABLE_MULTI_CANDIDATE_PATCH="${MULTI_CANDIDATE:-false}"
export MULTI_CANDIDATE_COUNT="${MULTI_CANDIDATE_COUNT:-3}"
info "多候选补丁(3.1): ENABLE_MULTI_CANDIDATE_PATCH=$ENABLE_MULTI_CANDIDATE_PATCH MULTI_CANDIDATE_COUNT=$MULTI_CANDIDATE_COUNT"

# 3.5 跨文件修复（协调器-提议者架构）：默认关闭保持历史单文件口径，
# 用户可用 --cross-file 显式启用（CROSS_FILE_ENABLE=true）。
# 真实数据集（SWE-bench / Defects4J）约 40% 任务需多文件修改，
# 启用后 cross_file_analyzer 节点分析跨文件依赖，patch_applier 走多文件补丁路径。
export CROSS_FILE_ENABLE="${CROSS_FILE:-false}"
info "跨文件修复(3.5): CROSS_FILE_ENABLE=$CROSS_FILE_ENABLE"

# 4.4 熔断器指数退避 + Prometheus 指标导出：默认启用（纯旁路，不影响路由行为）
export API_CIRCUIT_BACKOFF="${API_CIRCUIT_BACKOFF:-true}"
export API_PROMETHEUS_EXPORT="${API_PROMETHEUS_EXPORT:-false}"
info "熔断器(4.4): 指数退避=$API_CIRCUIT_BACKOFF Prometheus导出=$API_PROMETHEUS_EXPORT"

# ─── 步骤 1/6：检查运行环境 ─────────────────────────────────────────────────────
info "Step 1/6: 检查环境..."

# 批次跑批前置闸（EMSE 批次 2026-10-15，可选）：配额预算 + 模型指纹 + 工作树状态。
# 动机：SWE-bench Lite 20 次尝试因**批次级无配额闸**产生 10 次超时 + 7 次 429 失败，
# 能力结论被判为 none_valid_infrastructure_failure（披露见
# experiments/results/emse_swebench_disclosure.md）。默认**不启用**（保持历史行为，
# ADR-0003 默认不变原则）；设 AITESTER_RUN_PREFLIGHT=true 时未过闸即中止，且
# AITESTER_BATCH_MAX_CALLS 未配置即视为阻断（"未配置 ≠ 无限"）。
if [[ "${AITESTER_RUN_PREFLIGHT:-false}" == "true" ]]; then
    info "前置闸(EMSE): AITESTER_RUN_PREFLIGHT=true → 执行 scripts/tools/run_preflight.py --strict"
    # A02：预期任务数口径——显式 --task-limit > synthetic --task-count > 历史默认 261
    EXPECTED_TASKS="${TASK_LIMIT:-${TASK_COUNT:-261}}"
    if ! python3 scripts/tools/run_preflight.py --expect-tasks "$EXPECTED_TASKS" --strict; then
        error "批次前置闸未通过（配额/指纹/工作树）：修好后再跑，或显式设 AITESTER_RUN_PREFLIGHT=false 跳过（不推荐）"
    fi
else
    info "前置闸(EMSE): 未启用（设 AITESTER_RUN_PREFLIGHT=true 启用；建议重跑真实基准前启用）"
fi

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
mkdir -p experiments/results  # tee 重定向在管道前求值，目录缺失会直接失败
# U2（2026-10-05）：测试失败默认硬失败——"复现全绿"不得建立在未察觉失败上；宽容口径用 REPRODUCE_ALLOW_TEST_FAILURES=1 显式逃生（仅告警继续）。
# F05（2026-10-19 第三方审查，P2）：镜像按 .dockerignore 不含 experiments/results
# 历史工件，tests/ 多组用例以该目录归档 JSON 为夹具——空目录启动必须显式
# REPRODUCE_SKIP_TESTS=1 跳过测试门（此时复现结论不含测试验证）。
if [[ "${REPRODUCE_SKIP_TESTS:-0}" == "1" ]]; then
    warn "REPRODUCE_SKIP_TESTS=1：跳过 Step 3 测试门——本次复现缺少测试门，复现结论不含测试验证"
else
    TEST_EXIT=0
    python -m pytest tests/ -v --tb=short 2>&1 | tee experiments/results/test_output.log || TEST_EXIT=$?
    if [[ $TEST_EXIT -ne 0 && "${REPRODUCE_ALLOW_TEST_FAILURES:-0}" != "1" ]]; then
        error "单元测试失败（exit=${TEST_EXIT}）。复现实验前必须先让全量测试通过；如确需带失败继续，设 REPRODUCE_ALLOW_TEST_FAILURES=1"
    elif [[ $TEST_EXIT -ne 0 ]]; then
        warn "部分单元测试失败（REPRODUCE_ALLOW_TEST_FAILURES=1，继续执行——复现结论将不可信）"
    fi
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
elif [[ "$DATASET" == "synthetic" ]]; then
    info "Step 4/6: 使用内置合成数据集（本地生成 --task-count ${TASK_COUNT}，无需下载）"
else
    # 参数解析段已 fail-closed；此处双保险（任何路径都不得静默替换数据集）
    error "未知数据集 '$DATASET'（支持: examples | swe_bench | synthetic）"
fi

# ─── 步骤 5/6：运行基准测试 ───────────────────────────────────────────────────────
info "Step 5/6: 运行基准测试..."
mkdir -p experiments/results

# 构建任务数量限制参数
TASK_LIMIT_ARG=""
[[ -n "$TASK_LIMIT" ]] && TASK_LIMIT_ARG="--task-limit $TASK_LIMIT"

# A02：synthetic 真实参数透传（与 run_benchmark 主批入口一致）
TASK_COUNT_ARG=""
[[ -n "$TASK_COUNT" ]] && TASK_COUNT_ARG="--task-count $TASK_COUNT"
MAX_PATTERN_REPEAT_ARG=""
[[ -n "$MAX_PATTERN_REPEAT" ]] && MAX_PATTERN_REPEAT_ARG="--max-pattern-repeat $MAX_PATTERN_REPEAT"
SEED_ARG="--seed $SEED"

# 3.2 结构化追踪：显式设置 AITESTER_TRACE_DIR 收集逐智能体快照/Token 明细/
# 墙钟耗时/决策路径（默认 no-op，此处主动启用以支撑论文案例分析）
export AITESTER_TRACE_DIR="${AITESTER_TRACE_DIR:-experiments/results/traces}"
info "结构化追踪(3.2): AITESTER_TRACE_DIR=$AITESTER_TRACE_DIR"

# 1.2 变异得分评估（可选）：默认关闭——每任务需跑 ≤ MUTATION_MAX_MUTANTS 个
# 变异体 × pytest 子进程（约 30-60s/任务），对全量实验是显著时间税。
# 需要变异得分指标时显式设置 ENABLE_MUTATION_SCORING=true 后再运行，
# run_benchmark 会把 mutation_score 写进 details[]，analyze_results 自动汇总。
# 本复现流程默认不启用，保持历史实验口径与耗时预算不变。
if [[ -n "${ENABLE_MUTATION_SCORING:-}" ]]; then
    export ENABLE_MUTATION_SCORING
    info "变异得分(1.2): ENABLE_MUTATION_SCORING=${ENABLE_MUTATION_SCORING}（耗时显著增加，确认已知晓）"
else
    info "变异得分(1.2): 默认关闭（启用请设 ENABLE_MUTATION_SCORING=true）"
fi

# 运行多基线对比实验（自动保存 JSON 结果到 experiments/results/）
# 2.3 RAG：$ENABLE_RAG 显式传参（默认关，见 W7 阴性证据口径）
# 3.2 结构化追踪：显式设置 AITESTER_TRACE_DIR 收集逐智能体快照/Token 明细/
# 墙钟耗时/决策路径（默认 no-op，此处主动启用以支撑论文案例分析）
# A02：$TASK_COUNT_ARG / $MAX_PATTERN_REPEAT_ARG 为 synthetic 主批参数透传；
# $SEED_ARG 固定透传（主批 seed=42，多 seed 协议见 REPLICATION.md §5/§6）。
python experiments/run_benchmark.py \
    --dataset "$DATASET" \
    --baselines "$BASELINES" \
    $TASK_LIMIT_ARG \
    $TASK_COUNT_ARG \
    $MAX_PATTERN_REPEAT_ARG \
    $SEED_ARG \
    $ENABLE_RAG \
    --output-dir experiments/results \
    $VERBOSE

BENCH_EXIT=$?
if [[ $BENCH_EXIT -ne 0 ]]; then
    error "基准测试失败，请检查 experiments/results/test_output.log"
fi

# ─── 步骤 6/6：生成可视化图表 ────────────────────────────────────────────────────
info "Step 6/6: 生成结果可视化..."
# F06（2026-10-19 审查）：显式传 --dataset，只可视化本次数据集产物（不按文件名倒序猜）；随后生成柱状图/统计检验图/CSV/Markdown 汇总报告
python experiments/visualize_results.py --dataset "$DATASET"

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
echo "  3. 主批合成数据集复现（87 任务 / max-pattern-repeat 2 / seed 42 / 三臂）："
echo "     bash reproduce.sh --dataset synthetic --full"
echo "  4. 如需完整 SWE-bench 实验，使用 --dataset swe_bench --full"
echo ""

# F05（2026-10-19 第三方审查，P2）实现说明：
# REPRODUCE_SKIP_TESTS=1 显式跳过 Step3 全量测试门——镜像内 experiments/results
# 历史工件被 .dockerignore 排除，空目录挂载时测试缺夹具；跳过时脚本打印醒目
# WARN 并在本节声明"复现结论不含测试验证"。默认未设置仍跑测试且保持 fail-closed。
# 挂载该目录时它是**历史输入（测试夹具）与输出（本次结果）双重角色**：
# 需挂载含归档结果的完整目录，或空目录 + 本逃生开关（详见 Dockerfile.repro 末尾）。
