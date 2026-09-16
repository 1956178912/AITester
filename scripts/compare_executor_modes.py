"""
4.3 Docker 模式与本地 venv 模式执行时间对比（实验环境选择依据）。

对同一组任务分别用 EXECUTOR_USE_DOCKER=true 与 EXECUTOR_USE_VENV=true
跑一遍，记录两种模式的墙钟耗时与依赖安装/复用情况，输出 Markdown 对比表。

使用方式（docker 模式需本机已构建镜像）：
    python scripts/compare_executor_modes.py --tasks examples/calculator.py examples/string_utils.py

输出：
    stdout Markdown 表 + 可选 --output 文件（默认 experiments/results/
    executor_mode_comparison.md）。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


def _measure_one_mode(mode_env: dict[str, str], task_files: list[str], timeout: int) -> dict:
    """以指定环境变量跑一遍任务，返回 {mode, 耗时, 任务通过数, 明细}。

    模式开关通过环境变量传入 run 命令（config 在 import 期固化，
    故每次测量起独立子进程，避免同进程内切换开关无效）。
    """
    merged_env = {**os.environ, **mode_env}
    cmd = [sys.executable, "main.py", "run", *task_files, "--json", f"--timeout={timeout}"]
    start = time.time()
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=600,
        cwd=PROJECT_ROOT,
        env=merged_env,
    )
    elapsed = time.time() - start
    try:
        results = json.loads(proc.stdout) if proc.stdout.strip().startswith(("[", "{")) else []
        if isinstance(results, dict):
            results = [results]
        passed = sum(1 for r in results if r.get("passed"))
    except json.JSONDecodeError:
        results, passed = [], 0
    return {
        "mode": mode_env.get("EXECUTOR_USE_DOCKER", mode_env.get("EXECUTOR_USE_VENV", "local")),
        "elapsed_seconds": round(elapsed, 2),
        "tasks_passed": passed,
        "tasks_total": len(task_files),
        "exit_code": proc.returncode,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="4.3 Docker vs venv 执行时间对比")
    parser.add_argument("--tasks", nargs="+", required=True, help="被测文件列表")
    parser.add_argument("--timeout", type=int, default=60, help="单任务执行超时（秒）")
    parser.add_argument("--output", default=None, help="Markdown 输出路径（默认打印 stdout）")
    args = parser.parse_args()

    docker_result = _measure_one_mode({"EXECUTOR_USE_DOCKER": "true"}, args.tasks, args.timeout)
    venv_result = _measure_one_mode(
        {"EXECUTOR_USE_VENV": "true", "EXECUTOR_AUTO_INSTALL_DEPS": "true"}, args.tasks, args.timeout
    )

    speedup = ""
    if docker_result["elapsed_seconds"] > 0 and venv_result["elapsed_seconds"] > 0:
        speedup = f"{venv_result['elapsed_seconds'] / docker_result['elapsed_seconds']:.2f}x"

    lines = [
        "# 4.3 执行模式时间对比（Docker vs venv）",
        "",
        f"- 任务: {', '.join(args.tasks)}",
        "",
        "| 模式 | 墙钟耗时(s) | 通过/总数 | 退出码 | 相对加速比 |",
        "|------|------------|----------|--------|-----------|",
        f"| Docker（{docker_result.get('mode')}） | {docker_result['elapsed_seconds']} "
        f"| {docker_result['tasks_passed']}/{docker_result['tasks_total']} "
        f"| {docker_result['exit_code']} | 基准 |",
        f"| venv（{venv_result.get('mode')}） | {venv_result['elapsed_seconds']} "
        f"| {venv_result['tasks_passed']}/{venv_result['tasks_total']} "
        f"| {venv_result['exit_code']} | {speedup or 'N/A'} |",
        "",
        "> 解读：Docker 模式镜像构建一次后，每任务零安装开销，适合依赖固定的"
        "大规模批量实验；venv 模式按依赖组合缓存复用，依赖差异大时命中率下降。",
        "首次运行（缓存冷启动）venv 模式因创建 venv + pip install 显著慢于 Docker 复用镜像。",
    ]
    markdown = "\n".join(lines)
    print(markdown)
    if args.output:
        os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(markdown + "\n")
        print(f"\n对比表已写入: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
