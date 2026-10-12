#!/usr/bin/env bash
# spec_replace A/B 扩样实跑（87 gold 任务，2026-10-12）
#
# 预注册：docs/design/spec_replace_ab_scale87_prereg.md
#
# 设计：
#   - 三臂：A=aitester(off) / B=aitester(replace) / C=plain_llm_df
#   - 数据集 1：quixbugs（41 gold，F2P 可配对主判据）
#   - 数据集 2：ult lite 46 任务（seed=42 随机抽 46，官方测试材料齐备，
#     描述性观测——ULT 无 buggy 版本，detection 恒 0.0 基线）
#   - 两次 run_benchmark 调用：quixbugs 全量（50 任务，41 带 gold）+
#     ult（subset=lite，task_limit 随机抽 46）
#
# 口径（与首跑 SPEC_REPLACE_AB_REPORT_2026-10-12.md 一致）：
#   - 单种子 42，parallel=4，deterministic 未开启（TEMP 默认）
#   - DETECTION_SPEC_MODE 进程级（off / replace）
#   - --save-state 全环节落盘
#   - AITESTER_ULT_DATA 指向本地官方仓库 datasets 目录
#
# 成本：≈$5.6–$9.0（上界，price_table.json deepseek-flash 峰时价）
# 耗时：≈60–90 分钟（三臂 × 96 任务，parallel=4）
set -euo pipefail

cd "$(dirname "$0")/.."
PY=.venv/bin/python
ROOT="$(pwd)"

# ── 环境 ──────────────────────────────────────────────────────────────────────
export AITESTER_ULT_DATA="$HOME/.cache/aitester/ult_repo/datasets"
# 缓存命名空间隔离（多臂共享同 seed 42，跨臂隔离由 DETECTION_SPEC_MODE 区分）
export AITESTER_LLM_CACHE=1
export AITESTER_CACHE_NAMESPACE="scale87_seed42"

OUT_ROOT=/tmp/spec_ab_scale87
mkdir -p "$OUT_ROOT"

# ── 数据集 1：QuixBugs（全量 50 任务，41 带 gold，F2P 主判据）────────────
echo "=== [1/2] QuixBugs 三臂（off + replace + df 同批次）==="
# off 臂：aitester + plain_llm_df 同批次（DETECTION_SPEC_MODE=off）
DETECTION_SPEC_MODE=off \
  "$PY" experiments/run_benchmark.py \
    --dataset quixbugs \
    --baselines aitester,plain_llm_df \
    --output-dir "$OUT_ROOT/quixbugs_off" \
    --parallel 4 \
    --save-state \
    --no-rag \
    2>&1 | tee "$OUT_ROOT/quixbugs_off.log" | tail -5

# replace 臂：aitester（DETECTION_SPEC_MODE=replace）
DETECTION_SPEC_MODE=replace \
  "$PY" experiments/run_benchmark.py \
    --dataset quixbugs \
    --baselines aitester \
    --output-dir "$OUT_ROOT/quixbugs_replace" \
    --parallel 4 \
    --save-state \
    --no-rag \
    2>&1 | tee "$OUT_ROOT/quixbugs_replace.log" | tail -5

# ── 数据集 2：ULT_Lite 46 任务（seed=42 随机抽 46，描述性观测）────────
echo "=== [2/2] ULT_Lite 46 任务三臂 ==="
# 抽 46 任务口径：固定 seed=42，用 random.sample 从 ULT_Lite 200 任务里抽 46。
# run_benchmark --task-limit 是 slice 截断（非随机），不能直接用于随机抽样。
# 用子进程先抽样出 46 个 task_id，再写一个临时 JSONL manifest 指向它们，
# 用 AITESTER_ULT_DATA 指向该 manifest。

# 生成 46 任务抽样 manifest（seed=42，可复现）
# 注意 1：test_list 必须写官方**原始断言片段**（裸 assert 行），让
# dataset_ult 的 M1 归一化层（has_bare_asserts → 包装为 pytest 函数）
# 真正执行并产出可判分的 test_code / metadata.test_cases / fixed。
# 若直接写已包装的 metadata.test_cases（from ... import ...），加载器
# 会走"完整函数直接拼接"路径，绕过本批次新加的 M1 归一化逻辑。
# 注意 2：官方 ULT_Lite 记录**不含** cyclomatic_complexity 字段，加载器
# 写出的 metadata 该键为显式 None；run_benchmark 复杂度路由
# int(task.metadata.get("cyclomatic_complexity", 1)) 在"键存在但 None"时
# 取到 None → int(None) TypeError，46 任务全崩（首轮实测）。故 manifest
# 行必须显式补该键（缺省 1），并加自检防回归。
"$PY" - <<'PYEOF'
import json, os, random, sys
sys.path.insert(0, ".")
os.environ["AITESTER_ULT_DATA"] = os.path.expanduser("~/.cache/aitester/ult_repo/datasets")
from src.datasets.dataset_ult import ULTDataset

ds = ULTDataset(subset="lite")
tasks = ds.tasks
random.seed(42)
sample = random.sample(tasks, 46)
out_dir = "/tmp/spec_ab_scale87/ult_lite46"
os.makedirs(out_dir, exist_ok=True)
manifest = os.path.join(out_dir, "ult_lite46_manifest.jsonl")
with open(manifest, "w", encoding="utf-8") as f:
    for t in sample:
        # 写原始官方记录（func_name/code/prompt/task_id/test_list=裸断言）
        # test_list 用 gold_tests_raw（官方原始断言片段，M1 归一化的输入）
        # cyclomatic_complexity 显式写出（缺省 1）——run_benchmark 复杂度
        # 路由 int(metadata.get(...,1)) 在键缺失时取 1，键存在但 None 时崩
        cc = t.metadata.get("cyclomatic_complexity")
        row = {
            "func_name": t.metadata.get("function_name", ""),
            "code": t.instance_code,
            "prompt": t.problem_statement,
            "task_id": t.task_id,
            "test_list": (t.metadata.get("gold_tests_raw") or "").splitlines(),
            "cyclomatic_complexity": cc if cc is not None else 1,
        }
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
print(f"WROTE: {manifest} ({len(sample)} tasks)")
# 自检 1：test_list 是裸断言（触发 M1 包装路径）
first = json.loads(open(manifest).readline())
assert first["test_list"] and first["test_list"][0].strip().startswith("assert"), \
    f"test_list 非裸断言（M1 包装路径未触发）: {first['test_list'][:1]!r}"
print("self-check OK: test_list 为裸断言片段（M1 归一化路径已触发）")
# 自检 2：cyclomatic_complexity 全行非 None（复杂度路由 int() 不崩）
for line in open(manifest):
    row2 = json.loads(line)
    assert row2.get("cyclomatic_complexity") is not None, \
        f"manifest 行 cyclomatic_complexity=None 会触发 run_benchmark int(None) 崩溃: {row2['task_id']}"
print("self-check OK: cyclomatic_complexity 全行非 None（复杂度路由 int() 安全）")
PYEOF

ULT46_DIR=/tmp/spec_ab_scale87/ult_lite46

# off 臂（AITESTER_ULT_DATA 指向 46 任务抽样 manifest）
DETECTION_SPEC_MODE=off \
  AITESTER_ULT_DATA="$ULT46_DIR/ult_lite46_manifest.jsonl" \
  "$PY" experiments/run_benchmark.py \
    --dataset ult \
    --baselines aitester,plain_llm_df \
    --output-dir "$OUT_ROOT/ult_lite46_off" \
    --parallel 4 \
    --save-state \
    --no-rag \
    2>&1 | tee "$OUT_ROOT/ult_lite46_off.log" | tail -5

# replace 臂
DETECTION_SPEC_MODE=replace \
  AITESTER_ULT_DATA="$ULT46_DIR/ult_lite46_manifest.jsonl" \
  "$PY" experiments/run_benchmark.py \
    --dataset ult \
    --baselines aitester \
    --output-dir "$OUT_ROOT/ult_lite46_replace" \
    --parallel 4 \
    --save-state \
    --no-rag \
    2>&1 | tee "$OUT_ROOT/ult_lite46_replace.log" | tail -5

echo "=== 实跑完成，工件在 $OUT_ROOT ==="
echo "下一步：跑配对检验 + 产出报告 SPEC_REPLACE_AB_SCALE87_REPORT_2026-10-12.md"
