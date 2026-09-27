#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# 3.3 端到端冒烟测试脚本（一键验证最小可用流程）。
#
# 验证项（按依赖顺序，任一失败立即终止）：
#   S1 配置加载：LLM_CONFIGS 非空（.env.local 密钥已配）
#   S2 导入完整性：核心模块（src.graph / src.agents / src.tools）可导入
#   S3 静态检查：ruff 全量 0 违规（可选，--skip-lint 跳过）
#   S4 快速单测：核心模块子集（约 <30s，--full 跑全量）
#   S5 最小生成流程：PlannerAgent + GeneratorAgent 真实 LLM 调用
#      （--no-llm 跳过，纯离线验证 S1-S4）
#
# 用法：
#   bash scripts/smoke_test.sh            # S1-S5（含一次 LLM 调用，最小 token）
#   bash scripts/smoke_test.sh --no-llm   # 纯离线（CI 无密钥场景）
#   bash scripts/smoke_test.sh --full     # S4 跑全量测试（~31s）
#   bash scripts/smoke_test.sh --skip-lint
#
# 退出码：0 = 全过；1 = 失败（定位到具体步骤）；2 = 环境错误（缺依赖等）
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

PY="${PYTHON:-python3}"
# 优先用项目 .venv（存在时）
if [[ -x ".venv/bin/python" ]]; then
  PY=".venv/bin/python"
fi

RUN_LLM=1
RUN_LINT=1
TEST_SCOPE="quick"
for arg in "$@"; do
  case "$arg" in
    --no-llm) RUN_LLM=0 ;;
    --skip-lint) RUN_LINT=0 ;;
    --full) TEST_SCOPE="full" ;;
    -h|--help) grep '^#' "$0" | head -25; exit 0 ;;
    *) echo "未知参数: $arg（支持 --no-llm / --skip-lint / --full）"; exit 2 ;;
  esac
done

step() { echo; echo "── [S$1] $2"; }
ok() { echo "   ✓ $1"; }
fail() { echo "   ✗ $1" >&2; exit 1; }

# ── S1 配置加载 ───────────────────────────────────────────────────────────────
step 1 "配置加载（config.LLM_CONFIGS）"
$PY - <<'EOF' || fail "LLM_CONFIGS 为空：请按 QUICKSTART 第 3 步配置 .env.local"
from config import LLM_CONFIGS
assert LLM_CONFIGS, "LLM_CONFIGS 为空"
print(f"   loaded {len(LLM_CONFIGS)} LLM configs")
EOF
ok "LLM 配置已加载"

# ── S2 导入完整性 ─────────────────────────────────────────────────────────────
step 2 "核心模块导入"
$PY - <<'EOF' || fail "核心模块导入失败：先跑 pip install -r requirements.txt"
import src.graph.workflow
import src.agents.base_agent
import src.tools.patch_applier
import src.tools.patch_postprocess
import src.graph.cost_budget
import src.agents.semantic_cache
import src.agents.error_classifier
print("   core imports ok")
EOF
ok "核心模块导入成功"

# ── S3 静态检查（可选）───────────────────────────────────────────────────────
if [[ "$RUN_LINT" == 1 ]]; then
  step 3 "ruff 静态检查"
  if $PY -m ruff check src/ config.py main.py >/dev/null 2>&1; then
    ok "ruff 0 违规"
  else
    $PY -m ruff check src/ config.py main.py
    fail "ruff 违规（详见上方输出；修复后重跑）"
  fi
else
  echo; echo "── [S3] ruff 静态检查（--skip-lint 跳过）"
fi

# ── S4 快速单测 ──────────────────────────────────────────────────────────────
step 4 "单元测试（$TEST_SCOPE 范围）"
if [[ "$TEST_SCOPE" == "full" ]]; then
  $PY -m pytest tests/ -q --no-header -p no:cacheprovider \
    || fail "全量测试失败"
else
  # 快速层：核心模块 + 本轮新增（后处理层/预算/语义缓存/分类映射）
  $PY -m pytest \
    tests/test_base_agent.py \
    tests/test_error_classifier.py \
    tests/test_patch_applier.py \
    tests/test_patch_postprocess.py \
    tests/test_cost_budget.py \
    tests/test_semantic_cache.py \
    tests/test_state.py \
    tests/test_debugger.py \
    -q --no-header -p no:cacheprovider \
    || fail "快速层测试失败"
fi
ok "测试通过"

# ── S5 最小生成流程（真实 LLM 调用，--no-llm 跳过）─────────────────────────
if [[ "$RUN_LLM" == 1 ]]; then
  step 5 "最小生成流程（Planner + Generator，1 次 LLM 调用级）"
  # 隔离 LLM 缓存避免污染 src/cache；最小任务：calculator.add（无 bug 基准）
  AITESTER_LLM_CACHE_DIR="$(mktemp -d)" $PY - <<'EOF' || fail "最小生成流程失败（LLM 连通性 / 密钥 / 网络）"
import os, tempfile
from src.agents.planner import PlannerAgent
from src.agents.generator import GeneratorAgent

code = open(os.path.join("examples", "calculator.py")).read()
plan = PlannerAgent().plan(code, "add")
assert isinstance(plan, dict) and "function_name" in plan and "logic_analysis" in plan, \
    "Planner 输出结构不完整"
test_code = GeneratorAgent().generate(plan, code, module_name="calculator", focus_function="add")
assert "def test" in test_code, "Generator 未产出 pytest 测试函数"
assert "add" in test_code, "测试未引用目标函数 add"
print(f"   planner cases: {len(plan.get('test_cases', []))}; generator chars: {len(test_code)}")
EOF
  ok "最小生成流程通过"
else
  echo; echo "── [S5] 最小生成流程（--no-llm 跳过）"
fi

echo
echo "════════ 冒烟测试全部通过 ════════"
