#!/usr/bin/env python3
"""
AITester 完整对比实验脚本（v2）

本脚本运行标准化的对比实验，确保所有基线使用相同的配置和环境。

实验设计：
1. 合成数据集：100任务，固定随机种子，3个基线对比
2. 消融实验：分别禁用Planner、Debugger、RAG
3. 所有实验使用相同配置：ENABLE_PLANNER=true, ENABLE_DEBUGGER=true

使用方式：
    python scripts/run_standardized_experiments.py
"""

import os
import subprocess
import sys
from pathlib import Path
from datetime import datetime

# 实验配置
PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_BASE = PROJECT_ROOT / "experiments" / "results" / "standardized_20260819"

# 确保输出目录存在
OUTPUT_BASE.mkdir(parents=True, exist_ok=True)

# 定义实验矩阵
EXPERIMENTS = [
    {
        "name": "full_comparison_100tasks",
        "description": "完整对比实验：AITester vs Plain LLM vs Single Agent",
        "dataset": "synthetic",
        "task_count": 100,
        "baselines": "aitester,plain_llm,single_agent",
        "env_vars": {
            "ENABLE_PLANNER": "true",
            "ENABLE_DEBUGGER": "true",
            "ENABLE_RAG": "false",
        },
        "seed": 42,
    },
    {
        "name": "ablation_no_planner",
        "description": "消融实验：禁用Planner",
        "dataset": "synthetic",
        "task_count": 50,
        "baselines": "aitester",
        "env_vars": {
            "ENABLE_PLANNER": "false",
            "ENABLE_DEBUGGER": "true",
            "ENABLE_RAG": "false",
        },
        "seed": 42,
    },
    {
        "name": "ablation_no_debugger",
        "description": "消融实验：禁用Debugger",
        "dataset": "synthetic",
        "task_count": 50,
        "baselines": "aitester",
        "env_vars": {
            "ENABLE_PLANNER": "true",
            "ENABLE_DEBUGGER": "false",
            "ENABLE_RAG": "false",
        },
        "seed": 42,
    },
    {
        "name": "ablation_with_rag",
        "description": "消融实验：启用RAG",
        "dataset": "synthetic",
        "task_count": 50,
        "baselines": "aitester",
        "env_vars": {
            "ENABLE_PLANNER": "true",
            "ENABLE_DEBUGGER": "true",
            "ENABLE_RAG": "true",
        },
        "seed": 42,
    },
]


def run_experiment(exp_config: dict) -> dict:
    """运行单个实验并返回结果。"""
    print(f"\n{'='*80}")
    print(f"🚀 启动实验: {exp_config['name']}")
    print(f"📝 描述: {exp_config['description']}")
    print(f"{'='*80}\n")

    # 设置环境变量
    env = os.environ.copy()
    for key, value in exp_config["env_vars"].items():
        env[key] = value
        print(f"🔧 设置环境变量: {key}={value}")

    # 构建命令
    output_dir = OUTPUT_BASE / exp_config["name"]
    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "experiments" / "run_benchmark.py"),
        "--dataset", exp_config["dataset"],
        "--task-count", str(exp_config["task_count"]),
        "--baselines", exp_config["baselines"],
        "--output-dir", str(output_dir),
        "--seed", str(exp_config["seed"]),
    ]

    print(f"\n📊 执行命令:")
    print(f"   {' '.join(cmd)}\n")

    # 执行实验
    try:
        result = subprocess.run(
            cmd,
            env=env,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=3600,  # 1小时超时
        )

        # 记录输出
        log_file = output_dir / f"{exp_config['name']}.log"
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(f"=== 实验配置 ===\n")
            for k, v in exp_config["env_vars"].items():
                f.write(f"{k}={v}\n")
            f.write(f"\n=== 标准输出 ===\n")
            f.write(result.stdout)
            f.write(f"\n=== 标准错误 ===\n")
            f.write(result.stderr)

        print(f"✅ 实验完成: {exp_config['name']}")
        print(f"📄 日志已保存: {log_file}")

        return {
            "name": exp_config["name"],
            "status": "success" if result.returncode == 0 else "failed",
            "return_code": result.returncode,
            "log_file": str(log_file),
            "output_dir": str(output_dir),
        }

    except subprocess.TimeoutExpired:
        print(f"❌ 实验超时: {exp_config['name']}")
        return {
            "name": exp_config["name"],
            "status": "timeout",
            "error": "实验执行超过1小时",
        }
    except Exception as e:
        print(f"❌ 实验失败: {exp_config['name']} - {e}")
        return {
            "name": exp_config["name"],
            "status": "error",
            "error": str(e),
        }


def main():
    """主函数：运行所有实验并生成汇总报告。"""
    print("\n" + "="*80)
    print("🎯 AITester 标准化对比实验套件")
    print(f"📅 执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📂 输出目录: {OUTPUT_BASE}")
    print("="*80)

    results = []
    for exp_config in EXPERIMENTS:
        result = run_experiment(exp_config)
        results.append(result)

    # 生成汇总报告
    summary_file = OUTPUT_BASE / "EXPERIMENT_SUMMARY.md"
    with open(summary_file, "w", encoding="utf-8") as f:
        f.write("# AITester 标准化实验汇总报告\n\n")
        f.write(f"**执行时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("## 实验概览\n\n")
        f.write("| 实验名称 | 描述 | 状态 |\n")
        f.write("|---------|------|------|\n")
        for r in results:
            status_icon = "✅" if r["status"] == "success" else "❌"
            f.write(f"| {r['name']} | {r['description']} | {status_icon} {r['status']} |\n")

        f.write("\n## 详细结果\n\n")
        for r in results:
            f.write(f"### {r['name']}\n\n")
            f.write(f"- **状态**: {r['status']}\n")
            if "log_file" in r:
                f.write(f"- **日志**: [{r['log_file']}]({r['log_file']})\n")
            if "output_dir" in r:
                f.write(f"- **结果目录**: {r['output_dir']}\n")
            if "error" in r:
                f.write(f"- **错误**: {r['error']}\n")
            f.write("\n")

    print(f"\n{'='*80}")
    print("📊 实验套件完成!")
    print(f"📄 汇总报告: {summary_file}")
    print("="*80)

    # 检查是否有失败
    failed = [r for r in results if r["status"] != "success"]
    if failed:
        print(f"\n⚠️  {len(failed)} 个实验失败:")
        for r in failed:
            print(f"   - {r['name']}: {r.get('error', '未知错误')}")
        sys.exit(1)
    else:
        print("\n✅ 所有实验成功完成!")
        sys.exit(0)


if __name__ == "__main__":
    main()
