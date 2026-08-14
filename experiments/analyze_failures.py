"""
失败案例深度分析模块。

从实验结果 JSON 中提取失败任务，按错误类型聚类分析，
生成失败案例报告，供论文讨论章节使用。

使用方式：
    python experiments/analyze_failures.py --results-dir experiments/results --output docs/paper/failure_analysis.md
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List

import click

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def load_all_results(results_dir: str) -> List[Dict[str, Any]]:
    """加载所有实验结果文件，展平为任务级列表。"""
    all_tasks = []
    results_path = Path(results_dir)
    for f in sorted(results_path.glob("benchmark_*.json")):
        try:
            with open(f, encoding="utf-8") as fp:
                data = json.load(fp)
            if isinstance(data, dict) and "results" in data:
                for baseline, bl_data in data["results"].items():
                    if "details" in bl_data:
                        for d in bl_data["details"]:
                            d["baseline"] = baseline
                            d["experiment_file"] = f.name
                            all_tasks.append(d)
        except Exception as e:
            print(f"警告: 跳过文件 {f.name}: {e}")
    return all_tasks


def classify_failures(tasks: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """将失败任务按基线和错误类型分组。"""
    failed = [t for t in tasks if not t.get("passed", True)]
    by_bl_err = defaultdict(lambda: defaultdict(list))
    for t in failed:
        bl = t.get("baseline", "unknown")
        err = t.get("error_category") or t.get("error") or "unknown"
        by_bl_err[bl][err].append(t)
    return dict(by_bl_err)


def generate_report(tasks: List[Dict[str, Any]], output_path: str) -> None:
    """生成失败案例分析报告。"""
    failed = [t for t in tasks if not t.get("passed", True)]
    passed = [t for t in tasks if t.get("passed", False)]

    lines = []
    lines.append("# 失败案例分析报告")
    lines.append("")
    lines.append(f"> 生成时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"> 总任务数: {len(tasks)}，成功: {len(passed)}，失败: {len(failed)}")
    lines.append(f"> 整体失败率: {len(failed)/len(tasks)*100:.1f}%" if tasks else "")
    lines.append("")

    # 按基线统计
    lines.append("## 1. 各基线失败统计")
    lines.append("")
    by_bl = defaultdict(list)
    for t in tasks:
        by_bl[t.get("baseline", "?")].append(t)
    for bl, bl_tasks in sorted(by_bl.items()):
        bl_failed = [t for t in bl_tasks if not t.get("passed", True)]
        bl_passed = [t for t in bl_tasks if t.get("passed", False) is False]
        # 修正：passed 为 True 表示成功
        bl_passed_correct = [t for t in bl_tasks if t.get("passed") is True]
        bl_failed_correct = [t for t in bl_tasks if t.get("passed") is not True]
        lines.append(f"### {bl}")
        lines.append(f"- 总任务: {len(bl_tasks)}，成功: {len(bl_passed_correct)}，失败: {len(bl_failed_correct)}")
        lines.append(f"- 成功率: {len(bl_passed_correct)/len(bl_tasks)*100:.1f}%" if bl_tasks else "")
        lines.append("")

    # 错误类型分布
    lines.append("## 2. 错误类型分布")
    lines.append("")
    by_bl_err = classify_failures(tasks)
    for bl, err_map in sorted(by_bl_err.items()):
        lines.append(f"### {bl}")
        total_failed = sum(len(v) for v in err_map.values())
        for err, err_tasks in sorted(err_map.items(), key=lambda x: -len(x[1])):
            lines.append(f"- {err}: {len(err_tasks)} 个任务 ({len(err_tasks)/total_failed*100:.0f}%)")
        lines.append("")

    # 失败案例详情
    lines.append("## 3. 典型失败案例")
    lines.append("")
    sample_count = 0
    for bl, err_map in sorted(by_bl_err.items()):
        for err, err_tasks in sorted(err_map.items(), key=lambda x: -len(x[1])):
            if sample_count >= 10:
                break
            for t in err_tasks[:2]:  # 每类取前2个案例
                sample_count += 1
                lines.append(f"### 案例 {sample_count}: [{bl}] {err}")
                lines.append(f"- **任务**: `{t.get('task_id', 'N/A')}`")
                lines.append(f"- **错误**: {err}")
                diag = t.get("diagnosis", "无诊断信息")
                if diag:
                    lines.append(f"- **诊断**: {diag[:300]}{'...' if len(diag) > 300 else ''}")
                lines.append("")

    # 基础设施问题汇总
    lines.append("## 4. 基础设施问题汇总")
    lines.append("")
    infra_issues = [t for t in failed
                    if t.get("error_category") == "syntax"
                    or t.get("error") == "syntax"
                    or "ModuleNotFoundError" in str(t.get("diagnosis", ""))
                    or "ImportError" in str(t.get("diagnosis", ""))]
    lines.append(f"共发现 {len(infra_issues)} 个基础设施类失败（模块导入/文件名不匹配）。")
    lines.append("")
    lines.append("**主要原因**：")
    lines.append("1. 测试代码使用 `from module_name import func` 语法，但被测代码文件名与模块名不一致")
    lines.append("2. 合成数据集模板中 instance_code 未保存为独立 .py 文件")
    lines.append("3. Generator 生成的测试代码未感知目标文件的实际路径")
    lines.append("")
    lines.append("**改进建议**：")
    lines.append("- 在 Executor 阶段自动检测文件结构，动态创建或重命名模块文件")
    lines.append("- 在 Generator Prompt 中明确要求测试代码使用相对导入")
    lines.append("- 增强 SyntheticDataset 的模板一致性检查")
    lines.append("")

    # 写入文件
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"报告已保存: {output_file}")


@click.command()
@click.option("--results-dir", "-r", default="experiments/results", help="实验结果目录")
@click.option("--output", "-o", default="docs/paper/failure_analysis.md", help="输出报告路径")
def cli(results_dir: str, output: str):
    tasks = load_all_results(results_dir)
    if not tasks:
        print("未找到任何实验结果，请检查 --results-dir 路径")
        return
    generate_report(tasks, output)


if __name__ == "__main__":
    cli()
