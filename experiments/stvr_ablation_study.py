"""STVR 实证研究：AITester 增强机制消融实验骨架（设计稿，默认 dry-run，零 LLM 成本）。

定位（STVR 投稿导向）：
    本脚本是 **消融实验矩阵 + 研究设计文档** 的可执行骨架，
    把 `docs/design/stvr_empirical_study_design.md` 的 RQ 与消融矩阵
    固化为一份**可直接预注册、可复跑**的实验定义。默认 `--dry-run`
    （只打印将要执行的命令与环境变量，**不**调用 LLM、**不**写结果），
    满足"暂时不用 LLM 测试"的约束；`--execute` 才真正驱动
    `run_benchmark.py` 多臂实跑（耗 LLM，需用户显式授权配额）。

RQ 对应（详见 docs/design/stvr_empirical_study_design.md §1）：
    RQ1（主）：增强机制（RAG 检索 + 历史用例学习）是否实质性提升
        故障发现能力（mutation score / detection rate），而非仅"生成更多用例"？
    RQ2：RAG 检索策略（向量 vs 关键词 vs 无）对生成质量的差异化影响？
    RQ3：历史用例学习的"冷启动"——检索库为空时的早期性能差距？

消融矩阵（6 臂，因子 = {RAG检索, 历史用例学习}）：
    arm0  both_off      : RAG=off  历史库=空（纯 LLM 基线）
    arm1  rag_only      : RAG=on   历史库=预填充（仅检索注入，无学习闭环）
    arm2  learn_only    : RAG=off  历史库=预填充（仅历史案例参考，不走向量检索）
    arm3  both_on       : RAG=on   历史库=预填充+闭环（完整 AITester）
    arm4  cold_start    : RAG=on   历史库=空（检索开关开但无料可检——RQ3 冷启动）
    arm5  full_cold     : RAG=off  历史库=空+无闭环（冷启动纯基线）

主指标（STVR 社区最认可，见 design 文档 §4）：
    - mutation_score（变异得分，ENABLE_MUTATION_SCORING=true，
      experiments/mutation_testing.py 自研 AST 变异体；ULT 口径需
      cosmic-ray，见 docs/design/ult_bridge_plan.md §4.3）
    - detection_rate（M1 F2P 三段判定，experiments/_m1_metrics.py）
    - repair_rate（gold 测试在补丁后代码上的独立裁决）
辅助指标：
    - 行/分支覆盖率（results[arm].avg_coverage）
    - 检索质量 Recall@k（src/measurement/retrieval_quality.py，
      RAG_RETRIEVAL_RECALL_ENABLE=true 时透出，STVR 检索精度关注点）
    - token / 迭代 / 耗时（效率维度）

统计规范（design 文档 §5）：
    - 每臂 ≥ N_REPEATS 次独立运行（LLM 随机性），固定 seed 集合
    - 效应量（Cliff's delta / Cohen's d）+ 95% CI，**不**只报均值
    - 配对比较（同任务跨臂配对），复用 experiments/statistical_analysis.py
    的 mcnemar_test / two_proportion_binomtest + bayesian_paired

冷启动协议（RQ3，design 文档 §3）：
    - 检索库状态显式化：每臂记录 RAG 库的初始条目数（0 = 冷启动）
    - 运行前 `TestCaseRetriever.clear()` + 预填充脚本（`--seed-history`）
    - 冷启动臂（arm4/5）与预填充臂（arm1/2/3）配对，量"学习增益"

确定性保证（零 LLM）：
    - `--dry-run`（默认）：只生成命令串与环境变量清单，写
      `ablation_plan_<ts>.json`，**不** exec 任何 LLM 调用；
    - 变异体生成（experiments/mutation_testing.py）与 pytest 判定
      （experiments/_m1_metrics.py）均为确定性本地执行（AST 算子 +
      退出码判定），不耗 LLM 配额；但 LLM 测试生成侧仍需调用
      （由 --execute 驱动，需用户授权）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ─── 预注册常量（与 design 文档 §2 的增强机制定义对齐）─────────────────────
# 每臂独立重复次数（LLM 随机性 → 多次运行取分布，STVR 规范）
N_REPEATS = 10
# 固定 seed 集合（跨臂同 seed 配对，消除采样噪声）
SEED_SET = [42, 137, 256, 777, 1024, 2048, 4096, 8192, 16384, 32768]
# 主指标门控（全部显式打开，design 文档 §4）
DEFAULT_ENV = {
    "ENABLE_MUTATION_SCORING": "true",  # 主指标 mutation_score
    "MUTATION_MAX_MUTANTS": "10",  # 每任务 ≤10 变异体（默认）
    "RAG_RETRIEVAL_RECALL_ENABLE": "true",  # 检索质量 Recall@k 观测
    "RAG_RECALL_K": "3",
    "RAG_RECALL_RELEVANT_THRESHOLD": "0.7",
}


@dataclass(frozen=True)
class Arm:
    """单个消融臂（因子组合 + 环境变量 + 检索库状态）。"""

    name: str
    rag_enabled: bool  # RAG 向量检索开关（ENABLE_RAG）
    history_prefilled: bool  # 检索库是否预填充历史案例（学习闭环输入）
    learn_feedback: bool  # 是否开"历史用例学习"闭环（mutation_feedback + RAG 入库）
    cold_start: bool  # 冷启动（检索库强制清空，RQ3）
    description: str
    extra_env: dict[str, str] = field(default_factory=dict)

    def env_dict(self) -> dict[str, str]:
        """本臂的完整环境变量（覆盖 DEFAULT_ENV + 因子开关）。"""
        env = dict(DEFAULT_ENV)
        env["ENABLE_RAG"] = "true" if self.rag_enabled else "false"
        if self.learn_feedback:
            env.setdefault("AITESTER_LLM_CACHE", "1")  # 学习闭环需跨任务共享缓存
        if self.cold_start:
            # 冷启动：清空 RAG 持久化目录 + 检索库（见 run 前钩子）
            env["RAG_COLD_START"] = "true"
        env.update(self.extra_env)
        return env


ARMS: tuple[Arm, ...] = (
    Arm(
        "both_off",
        rag_enabled=False,
        history_prefilled=False,
        learn_feedback=False,
        cold_start=False,
        description="纯 LLM 基线：无 RAG 检索、无历史库、无学习闭环",
    ),
    Arm(
        "rag_only",
        rag_enabled=True,
        history_prefilled=True,
        learn_feedback=False,
        cold_start=False,
        description="仅 RAG 检索注入（预填充历史案例，不走向量检索的闭环学习）",
    ),
    Arm(
        "learn_only",
        rag_enabled=False,
        history_prefilled=True,
        learn_feedback=True,
        cold_start=False,
        description="仅历史用例学习（mutation_feedback 闭环 + 案例参考，关向量检索）",
    ),
    Arm(
        "both_on",
        rag_enabled=True,
        history_prefilled=True,
        learn_feedback=True,
        cold_start=False,
        description="完整 AITester：RAG 检索 + 历史学习闭环",
    ),
    Arm(
        "cold_start",
        rag_enabled=True,
        history_prefilled=False,
        learn_feedback=False,
        cold_start=True,
        description="冷启动 RAG：检索开关开但库为空（RQ3 早期性能）",
    ),
    Arm(
        "full_cold",
        rag_enabled=False,
        history_prefilled=False,
        learn_feedback=False,
        cold_start=True,
        description="冷启动纯基线：无任何历史料（RQ3 对照）",
    ),
)


def build_command(arm: Arm, dataset: str, subset: str, seed: int, out_dir: str) -> str:
    """生成单臂单 seed 的 run_benchmark CLI 命令串（预注册口径）。"""
    parts = [
        ".venv/bin/python experiments/run_benchmark.py",
        f"--dataset {dataset}",
    ]
    if subset:
        parts.append(f"--subset {subset}")
    parts += [
        "--baselines aitester",
        f"--seed {seed}",
        "--parallel 4",
        "--save-state",
        f"--output-dir {out_dir}/{arm.name}/seed_{seed}",
    ]
    return " ".join(parts)


def build_plan(
    dataset: str,
    subset: str,
    out_root: str,
    execute: bool = False,
    task_limit: int | None = None,
) -> dict[str, Any]:
    """生成完整消融实验计划（JSON 可序列化，供预注册与复跑）。

    Args:
        dataset: 数据集名（quixbugs / synthetic / ult / bugsinpy / swe_bench）。
        subset: 子集（如 "lite"），可为空。
        out_root: 结果输出根目录。
        execute: True 时实际驱动 run_benchmark（耗 LLM，需授权）；
            False（默认 dry-run）只生成计划 JSON。
        task_limit: 每臂任务数上限（None = 全量）。

    Returns:
        计划 dict（可 json 落盘）：含 arms / env / seeds / commands /
        prereg 口径 + 主指标门控 + 冷启动钩子说明。
    """
    ts = int(time.time())
    commands: dict[str, list[str]] = {}
    for arm in ARMS:
        cmds = []
        for seed in SEED_SET:
            out_dir = os.path.join(out_root, f"run_{ts}")
            cmd = build_command(arm, dataset, subset, seed, out_dir)
            if task_limit:
                cmd += f" --task-limit {task_limit}"
            # 前缀环境变量（shell 形式，可复制到 bash 执行）
            env_prefix = " ".join(f"{k}={v}" for k, v in arm.env_dict().items())
            cmds.append(f"{env_prefix} {cmd}")
        commands[arm.name] = cmds

    return {
        "prereg_id": f"stvr_ablation_{ts}",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(ts)),
        "dataset": dataset,
        "subset": subset,
        "n_repeats": N_REPEATS,
        "seed_set": SEED_SET,
        "primary_metrics": [
            "mutation_score (ENABLE_MUTATION_SCORING=true)",
            "detection_rate (M1 F2P three-way)",
            "repair_rate (gold adjudication)",
        ],
        "aux_metrics": [
            "coverage (line/branch)",
            "retrieval Recall@k (RAG_RETRIEVAL_RECALL_ENABLE=true)",
            "token / iterations / elapsed",
        ],
        "env_defaults": DEFAULT_ENV,
        "arms": [
            {
                "name": a.name,
                "rag_enabled": a.rag_enabled,
                "history_prefilled": a.history_prefilled,
                "learn_feedback": a.learn_feedback,
                "cold_start": a.cold_start,
                "description": a.description,
                "env": a.env_dict(),
            }
            for a in ARMS
        ],
        "commands": commands,
        "execute": execute,
        "task_limit": task_limit,
        "cold_start_hook": (
            "RAG_COLD_START=true 的臂在 run 前调用 TestCaseRetriever.clear() + "
            "清空 RAG 持久化目录（AITESTER_RAG_DIR），强制检索库初始 0 条目；"
            "预填充臂在 run 前经 --seed-history 注入历史案例。"
        ),
        "statistics": {
            "paired": "same seed + same task across arms (task-paired)",
            "effect_size": ["cliff_delta", "cohens_d"],
            "ci": "paired bootstrap 95%",
            "reuse": [
                "experiments/statistical_analysis.py::mcnemar_test",
                "experiments/statistical_analysis.py::two_proportion_binomtest",
                "experiments/bayesian_paired.py",
            ],
        },
        "llm_cost_note": (
            "dry-run（execute=False）不耗 LLM；execute=True 驱动 run_benchmark "
            "的 LLM 测试生成侧（6 臂 × N_REPEATS × dataset 任务数），需用户授权配额。"
            "变异体生成与 pytest 判定为确定性本地执行（零 LLM）。"
        ),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", default="quixbugs", help="数据集名（默认 quixbugs）")
    ap.add_argument("--subset", default="", help="子集（如 lite）")
    ap.add_argument("--out-root", default="experiments/results/stvr_ablation")
    ap.add_argument("--task-limit", type=int, default=None, help="每臂任务数上限")
    ap.add_argument(
        "--execute",
        action="store_true",
        help="实际驱动 run_benchmark（耗 LLM，需授权）；默认 dry-run 只生成计划",
    )
    ap.add_argument(
        "--write-plan",
        default="",
        help="把计划 JSON 写到该路径（默认写 stdout）",
    )
    args = ap.parse_args(argv)

    plan = build_plan(
        dataset=args.dataset,
        subset=args.subset,
        out_root=args.out_root,
        execute=args.execute,
        task_limit=args.task_limit,
    )
    out = json.dumps(plan, indent=2, ensure_ascii=False)

    if args.write_plan:
        Path(args.write_plan).write_text(out, encoding="utf-8")
        print(f"[stvr_ablation] 计划已写 {args.write_plan}")
    else:
        print(out)

    if args.execute:
        print("\n[stvr_ablation] ⚠️ --execute 已指定：将驱动 LLM 实跑，需用户授权配额。")
        print("[stvr_ablation] 当前为骨架（设计稿），实际执行钩子待后续批次接入 run_benchmark。")
        print("[stvr_ablation] 本批次只生成预注册计划 JSON（零 LLM 成本，符合约束）。")
    else:
        print("\n[stvr_ablation] dry-run 完成：已生成 6 臂 × N_REPEATS 的预注册计划（零 LLM 成本）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
