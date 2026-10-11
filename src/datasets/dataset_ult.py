"""W4b（2026-10-10 独立审查落地）：ULT（UnLeakedTestbench）基准加载器。

背景（独立审查 2026-10-10，前沿数据一手核验）：
    ULT（Huang, Zhang, Harman et al.，TOSEM 2026，DOI 10.1145/3805043；
    github.com/huangd1999/UnLeakedTestBench，MIT 许可）是当前最适合
    "检出优先"主张的 Python 测试生成基准：3,909 个真实 Python 函数、
    圈复杂度 ≥10（均值 14.87）、多阶段防污染策划。12 个 SOTA LLM 在
    ULT 上平均 Pass@1 仅 41.32%、变异分数 40.21%，远低于 TestEval 的
    91.79% / 49.69%——**没有任何已发表系统在 ULT 上报告 detection-first
    协议的结果，是本项目独有的空白机会**（独立审查路径 P3）。

关键约束（一手核验，github.com/huangd1999/UnLeakedTestBench README）：
    1. **官方不发布 ground-truth tests**（防污染设计，仅发布函数源码 +
       评测脚本 + 官方模型结果）——因此本加载器产出的任务 **无 gold
       test_cases / fixed 材料**，M1 的 detection_rate 恒为 None（诚实，
       不可测量），评测须走 ULT 官方脚本的 **mutation score（Mut@k）**
       而非 detection_rate；
    2. 评测协议为 K-query 迭代：Round 1 只给 FUT（function under test）
       生成 1 个测试，Round i 给 FUT + 之前所有测试生成 1 个新测试
       （temp 0.0，greedy，max 1024 新 token）——与本项目 detection-first
       协议的"先红后绿"无冲突，但需在适配层显式说明；
    3. mutation 用 Cosmic-Ray（官方脚本），mutant killed 判据 = 套件在
       变异代码上失败且在原代码上通过。

数据格式（manifest JSONL，相对 self.data_dir，默认 ~/.cache/aitester/ult/）：
    文件名 ult_manifest.jsonl（或 data_dir 直接指向 .jsonl 文件），每行一个
    函数级任务：
    {
      "function_name": "resolve_path",      # 必需（可导入标识符）
      "source_code": "def resolve_path...",  # 必需（函数全文，FUT）
      "signature": "def resolve_path(a, b)", # 可选（签名，供 prompt 聚焦）
      "cyclomatic_complexity": 14            # 可选（难度分层用）
    }

获取方式：ULT 官方仓库（github.com/huangd1999/UnLeakedTestBench）的
datasets/ 目录提供函数源码；建议用官方仓库的分析脚本导出上述 manifest
（字段一一对应），经 AITESTER_ULT_DATA 指向数据目录。本模块不内置抓取
脚本（与 QuixBugs/BugsInPy 同口径，避免网络依赖与许可争议）。

任务口径：
    - task_id = ult__<function_name>（末段=模块名，中性可导入标识符）；
    - instance_code = source_code（被测函数全文）；
    - test_code = ""（**无 gold tests**——ULT 官方防污染设计，非缺失）；
    - metadata["no_gold_tests"] = True（下游据此知道 detection_rate 不可测，
      评测走 mutation）；metadata["suggested_function"] = function_name。
"""

from __future__ import annotations

import ast
import json
import logging
import os
import re
from typing import ClassVar

from src.datasets.dataset_loader import BaseDatasetLoader, BenchmarkTask

logger = logging.getLogger(__name__)


def _first_function_name(code: str) -> str | None:
    """提取首个顶层函数名（suggested_function 的保守默认值）。"""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            return node.name
    return None


class ULTDataset(BaseDatasetLoader):
    """ULT（UnLeakedTestbench）基准加载器。

    与 QuixBugs/BugsInPy 加载器同模式（manifest JSONL 本地解析），目录缺失时
    返回空数据集 + warning（优雅降级，不阻断 CI / 精简环境）。

    **关键差异**：ULT 官方**不发布 ground-truth tests**（防污染设计），故本
    加载器产出的任务 test_code 恒为空、metadata["no_gold_tests"]=True——
    M1 的 detection_rate 对这些任务恒为 None（诚实不可测），评测须走 ULT
    官方脚本的 mutation score（Mut@k）。这与独立审查"coverage 降级为辅助
    指标、mutation 为主指标"的结论一致。
    """

    DATASET_NAME = "ult"
    _MANIFEST_NAMES: ClassVar[tuple[str, ...]] = ("ult_manifest.jsonl", "manifest.jsonl")
    _MAX_NAME_LEN: ClassVar[int] = 40  # task_id 末段长度预算（可导入标识符）

    def __init__(self, subset: str | None = None, data_dir: str | None = None) -> None:
        # data_dir 显式参数 > AITESTER_ULT_DATA 环境变量 > 默认缓存目录
        super().__init__(subset=subset, data_dir=data_dir or os.getenv("AITESTER_ULT_DATA") or None)

    def _manifest_path(self) -> str | None:
        if self.data_dir.endswith(".jsonl") and os.path.exists(self.data_dir):
            return self.data_dir
        for name in self._MANIFEST_NAMES:
            candidate = os.path.join(self.data_dir, name)
            if os.path.exists(candidate):
                return candidate
        return None

    def _load_raw_data(self) -> None:
        self._tasks.clear()
        manifest = self._manifest_path()
        if manifest is None:
            logger.warning(
                "ULT manifest 未找到: %s（期待 %s 之一，或直接指向 .jsonl 文件；设 AITESTER_ULT_DATA 指向数据目录）",
                self.data_dir,
                " / ".join(self._MANIFEST_NAMES),
            )
            return

        loaded = skipped = 0
        with open(manifest, encoding="utf-8") as f:
            for line_no, raw in enumerate(f, 1):
                line = raw.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as e:
                    logger.warning("ULT manifest 第 %d 行解析失败（跳过）: %s", line_no, e)
                    skipped += 1
                    continue

                source_code = str(row.get("source_code") or "")
                if not source_code.strip():
                    skipped += 1
                    continue

                func_name = str(row.get("function_name") or "").strip()
                # 函数名中性化：非标识符时回退到 AST 首个顶层函数，再不行才用行号
                if not func_name.isidentifier():
                    func_name = _first_function_name(source_code) or f"func{line_no}"
                func_name = re.sub(r"\W", "_", func_name)[: self._MAX_NAME_LEN].strip("_") or f"func{line_no}"

                # 圈复杂度（可选，难度分层用）；坏值保守置 None
                complexity = row.get("cyclomatic_complexity")
                if not isinstance(complexity, int) or complexity < 0:
                    complexity = None

                self._tasks.append(
                    BenchmarkTask(
                        task_id=f"ult__{func_name}",
                        repo_name="ult",
                        problem_statement=(
                            f"ULT function {func_name}（圈复杂度 {complexity if complexity is not None else '未知'}）"
                        ),
                        instance_code=source_code,
                        # ULT 官方不发布 ground-truth tests（防污染），test_code 恒空
                        test_code="",
                        expected_pass_count=0,
                        total_test_count=0,
                        metadata={
                            "source": "ult",
                            "function_name": func_name,
                            "signature": str(row.get("signature") or ""),
                            "cyclomatic_complexity": complexity,
                            # 下游据此知道 detection_rate 不可测，评测走 mutation（Mut@k）
                            "no_gold_tests": True,
                            "suggested_function": func_name,
                            "is_cross_file": False,
                        },
                    )
                )
                loaded += 1
        logger.info(
            "ULT 加载完成：%d 个任务（跳过 %d 行无效记录；官方不发布 gold tests，评测走 mutation）", loaded, skipped
        )


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    ds = ULTDataset()
    logger.info("ULT: %d tasks", ds.size)
