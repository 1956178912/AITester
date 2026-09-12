"""
失败案例深度分析模块。

从实验结果 JSON 中提取失败任务，按错误类型聚类分析，
生成失败案例报告，供技术评审与改进方向讨论使用。

使用方式：
    python experiments/analyze_failures.py --results-dir experiments/results --output experiments/results/failure_analysis.md

5.3 扩展（失败根因分类 + 案例知识库）：
- root_cause_classification(details)：把每个失败任务归因为三类之一
  （llm_capability / dependency / framework），基于 error_category + diagnosis
  文本匹配，输出根因分布与代表案例；
- failure_knowledge_base(details)：把典型失败案例结构化为
  experiments/results/failure_knowledge_base.json，含 task_id / root_cause /
  error_category / 可复现步骤 / 建议修复，供后续优化参考；
- analyze_failures CLI 新增 --knowledge-base 选项（默认输出到 results 目录）。
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import click

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ─── 5.3 失败根因分类 ────────────────────────────────────────────────────────
# 三大根因类别与启发式关键词（保守口径：仅用于分析层归因，不影响修复流程）
_ROOT_CAUSE_RULES: list[tuple[str, list[str]]] = [
    (
        "llm_capability",
        [
            "llm_format_error",
            "index_error",
            "json",
            "解析失败",
            "输出格式",
            "non-json",
            "empty response",
        ],
    ),
    (
        "dependency",
        [
            "import_error",
            "module_not_found",
            "pip",
            "venv",
            "依赖",
            "install",
        ],
    ),
    (
        "framework",
        [
            "patch_validation_failed",
            "rag_retrieval_empty",
            "timeout",
            "sandbox",
            "docker",
            "executor",
        ],
    ),
]
_DEFAULT_ROOT_CAUSE = "llm_capability"  # 未命中任何规则时归 LLM 能力边界


def root_cause_classification(details: list[dict[str, Any]]) -> dict[str, Any]:
    """5.3 失败根因分类：按 error_category + diagnosis 文本匹配三大根因。

    Args:
        details: benchmark 结果 JSON 的 details[] 列表。

    Returns:
        {"root_causes": {category: count},
         "distribution": {category: ratio},
         "representative_cases": {category: [task_id...]},
         "total_failed": int}

    说明：
    - 仅统计失败任务（passed=False）；
    - 每个失败任务归到第一个命中的规则（保守口径，避免多重计数）；
    - 未命中任何规则时归 llm_capability（最泛兜底）。
    """
    failed = [r for r in details if not r.get("passed")]
    root_causes: dict[str, int] = {"llm_capability": 0, "dependency": 0, "framework": 0}
    representative_cases: dict[str, list[str]] = {"llm_capability": [], "dependency": [], "framework": []}

    for row in failed:
        cat = str(row.get("error_category") or "").lower()
        diag = str(row.get("diagnosis") or "").lower()
        assigned = _DEFAULT_ROOT_CAUSE
        for cause, keywords in _ROOT_CAUSE_RULES:
            if cat in keywords or any(kw in diag for kw in keywords):
                assigned = cause
                break
        root_causes[assigned] += 1
        task_id = str(row.get("task_id", "unknown"))
        if len(representative_cases[assigned]) < 3:  # 每类最多 3 个代表案例
            representative_cases[assigned].append(task_id)

    total_failed = len(failed)
    distribution = {cause: (count / total_failed if total_failed else 0.0) for cause, count in root_causes.items()}
    return {
        "root_causes": root_causes,
        "distribution": distribution,
        "representative_cases": representative_cases,
        "total_failed": total_failed,
    }


def failure_knowledge_base(details: list[dict[str, Any]], top_n: int = 10) -> list[dict[str, Any]]:
    """5.3 失败案例知识库：把典型失败案例结构化为可复用记录。

    每条记录含：
    - task_id / baseline / error_category / diagnosis / root_cause
    - reproducible_steps（可复现步骤，含数据集名 + 任务标识）
    - suggested_fix（基于根因类别的建议修复方向）

    Args:
        details: benchmark 结果 JSON 的 details[] 列表。
        top_n: 最多收录的案例数（默认 10，按失败类别多样性选取）。

    Returns:
        结构化案例列表（可直接 JSON 落盘为 experiments/results/failure_knowledge_base.json）。

    说明：
    - 仅收录失败任务（passed=False）；
    - 按 error_category 多样性优先选取（每类取前 1-2 个，避免重复）；
    - reproducible_steps 为字符串，含数据集与任务标识，便于后续复现。
    """
    failed = [r for r in details if not r.get("passed")]
    if not failed:
        return []

    # 按 error_category 分组，每类取前 2 个案例（多样性）
    by_cat: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in failed:
        cat = str(row.get("error_category") or "unknown")
        by_cat[cat].append(row)

    cases: list[dict[str, Any]] = []
    for cat, rows in sorted(by_cat.items()):
        for row in rows[:2]:
            if len(cases) >= top_n:
                break
            task_id = str(row.get("task_id", "unknown"))
            diagnosis = str(row.get("diagnosis") or "")[:300]
            suggested = _suggest_fix_for_root_cause(row, cat)
            cases.append(
                {
                    "task_id": task_id,
                    "error_category": cat,
                    "root_cause": _assign_root_cause(row, cat),
                    "diagnosis_excerpt": diagnosis,
                    "reproducible_steps": (
                        f"运行 experiments/run_benchmark.py --dataset "
                        f"{row.get('dataset', 'synthetic')} "
                        f"--task-limit 1 复现任务 {task_id}；"
                        f"失败类别 {cat}；根因 {suggested['root_cause']}"
                    ),
                    "suggested_fix": suggested,
                }
            )
    return cases


def _assign_root_cause(row: dict[str, Any], cat: str) -> str:
    """按 error_category + diagnosis 关键词匹配三大根因之一。"""
    diag = str(row.get("diagnosis") or "").lower()
    for cause, keywords in _ROOT_CAUSE_RULES:
        if cat in keywords or any(kw in diag for kw in keywords):
            return cause
    return _DEFAULT_ROOT_CAUSE


def _suggest_fix_for_root_cause(row: dict[str, Any], cat: str) -> dict[str, str]:
    """基于根因类别给出建议修复方向（保守口径，供人工参考）。"""
    cause = _assign_root_cause(row, cat)
    suggestions = {
        "llm_capability": {
            "root_cause": "llm_capability",
            "suggestion": (
                "LLM 输出格式或边界推理能力不足。建议：1) 增大 LLM 温度 / 多次采样取众数；"
                "2) 在 Debugger 提示词中追加格式约束（JSON schema）；"
                "3) 对 INDEX_ERROR / LLM_FORMAT_ERROR 类失败启用 3.1 多候选补丁"
            ),
        },
        "dependency": {
            "root_cause": "dependency",
            "suggestion": (
                "第三方依赖缺失或版本冲突。建议：1) 在 Executor 沙箱内自动 pip install 缺失包；"
                "2) 用 4.4 依赖缓存监控命中率，识别频繁重建的依赖组合；"
                "3) 在 dataset_loader 中预标注每个任务的依赖清单"
            ),
        },
        "framework": {
            "root_cause": "framework",
            "suggestion": (
                "框架自身缺陷（沙箱 / 补丁校验 / RAG 检索为空 / 超时）。建议：1) 检查 RAG 检索"
                "（rag_retrieval_empty 任务）；2) 降低 MAX_ITERATIONS 或调高 EXECUTION_TIMEOUT；"
                "3) 对 PATCH_VALIDATION_FAILED 任务启用 3.1 多候选补丁 + 静态筛选"
            ),
        },
    }
    return suggestions.get(cause, suggestions["llm_capability"])


def load_all_results(results_dir: str) -> list[dict[str, Any]]:
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


def classify_failures(tasks: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """将失败任务按基线和错误类型分组。"""
    failed = [t for t in tasks if not t.get("passed", True)]
    by_bl_err = defaultdict(lambda: defaultdict(list))
    for t in failed:
        bl = t.get("baseline", "unknown")
        err = t.get("error_category") or t.get("error") or "unknown"
        by_bl_err[bl][err].append(t)
    return dict(by_bl_err)


def generate_report(tasks: list[dict[str, Any]], output_path: str) -> None:
    """生成失败案例分析报告。"""
    failed = [t for t in tasks if not t.get("passed", True)]
    passed = [t for t in tasks if t.get("passed", False)]

    lines = []
    lines.append("# 失败案例分析报告")
    lines.append("")
    lines.append(f"> 生成时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"> 总任务数: {len(tasks)}，成功: {len(passed)}，失败: {len(failed)}")
    lines.append(f"> 整体失败率: {len(failed) / len(tasks) * 100:.1f}%" if tasks else "")
    lines.append("")

    # 按基线统计
    lines.append("## 1. 各基线失败统计")
    lines.append("")
    by_bl = defaultdict(list)
    for t in tasks:
        by_bl[t.get("baseline", "?")].append(t)
    for bl, bl_tasks in sorted(by_bl.items()):
        # passed 为 True 表示成功（此前上方两行结果被丢弃的无操作推导已删）
        bl_passed_correct = [t for t in bl_tasks if t.get("passed") is True]
        bl_failed_correct = [t for t in bl_tasks if t.get("passed") is not True]
        lines.append(f"### {bl}")
        lines.append(f"- 总任务: {len(bl_tasks)}，成功: {len(bl_passed_correct)}，失败: {len(bl_failed_correct)}")
        lines.append(f"- 成功率: {len(bl_passed_correct) / len(bl_tasks) * 100:.1f}%" if bl_tasks else "")
        lines.append("")

    # 错误类型分布
    lines.append("## 2. 错误类型分布")
    lines.append("")
    by_bl_err = classify_failures(tasks)
    for bl, err_map in sorted(by_bl_err.items()):
        lines.append(f"### {bl}")
        total_failed = sum(len(v) for v in err_map.values())
        for err, err_tasks in sorted(err_map.items(), key=lambda x: -len(x[1])):
            lines.append(f"- {err}: {len(err_tasks)} 个任务 ({len(err_tasks) / total_failed * 100:.0f}%)")
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
    infra_issues = [
        t
        for t in failed
        if t.get("error_category") == "syntax"
        or t.get("error") == "syntax"
        or "ModuleNotFoundError" in str(t.get("diagnosis", ""))
        or "ImportError" in str(t.get("diagnosis", ""))
    ]
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

    # 5.3 失败根因分类（LLM 能力 / 依赖 / 框架）
    root_cause = root_cause_classification(failed)
    lines.append("## 5. 失败根因分类（5.3）")
    lines.append("")
    lines.append(f"> 共 {root_cause['total_failed']} 个失败任务，按三大根因归类：")
    lines.append("")
    lines.append("| 根因 | 任务数 | 占比 | 代表案例 |")
    lines.append("|------|--------|------|---------|")
    for cause in ("llm_capability", "dependency", "framework"):
        count = root_cause["root_causes"].get(cause, 0)
        ratio = root_cause["distribution"].get(cause, 0.0)
        reps = ", ".join(root_cause["representative_cases"].get(cause, [])[:3]) or "—"
        lines.append(f"| {cause} | {count} | {ratio:.1%} | {reps} |")
    lines.append("")

    # 5.3 失败案例知识库（结构化存储）
    kb = failure_knowledge_base(failed, top_n=10)
    lines.append("## 6. 失败案例知识库（5.3，结构化）")
    lines.append("")
    if kb:
        for i, case in enumerate(kb, start=1):
            lines.append(f"### 案例 {i}: `{case['task_id']}` [{case['root_cause']} / {case['error_category']}]")
            lines.append(f"- **诊断摘录**: {case['diagnosis_excerpt']}")
            lines.append(f"- **复现步骤**: {case['reproducible_steps']}")
            lines.append(f"- **建议修复**: {case['suggested_fix']['suggestion']}")
            lines.append("")
        lines.append(
            "> 知识库落盘：`experiments/results/failure_knowledge_base.json`"
            "（由 CLI `--knowledge-base` 选项输出；默认不自动写入，需显式开启）。"
        )
    else:
        lines.append("> 无失败任务，知识库为空。")
    lines.append("")

    # 写入文件
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"报告已保存: {output_file}")


@click.command()
@click.option("--results-dir", "-r", default="experiments/results", help="实验结果目录")
@click.option("--output", "-o", default="experiments/results/failure_analysis.md", help="输出报告路径")
@click.option(
    "--knowledge-base",
    "-k",
    default=None,
    help="失败案例知识库 JSON 输出路径（默认 <results-dir>/failure_knowledge_base.json）",
)
def cli(results_dir: str, output: str, knowledge_base: str | None):
    tasks = load_all_results(results_dir)
    if not tasks:
        print("未找到任何实验结果，请检查 --results-dir 路径")
        return
    generate_report(tasks, output)

    # 5.3 知识库落盘（默认输出到 <results-dir>/failure_knowledge_base.json）
    kb_path = knowledge_base or str(Path(results_dir) / "failure_knowledge_base.json")
    kb_cases = failure_knowledge_base(tasks, top_n=10)
    out = Path(kb_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(kb_cases, f, ensure_ascii=False, indent=2)
    print(f"知识库已保存: {out}（{len(kb_cases)} 条案例）")


if __name__ == "__main__":
    cli()
