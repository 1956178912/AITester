"""W4b（2026-10-10 独立审查落地；2026-10-12 官方仓库一手核验勘误）：
ULT（UnLeakedTestbench）基准加载器。

背景（独立审查 2026-10-10，前沿数据一手核验）：
    ULT（Huang, Zhang, Harman et al.，TOSEM 2026，DOI 10.1145/3805043；
    github.com/huangd1999/UnLeakedTestBench，MIT 许可）是当前最适合
    "检出优先"主张的 Python 测试生成基准：3,909 个真实 Python 函数、
    圈复杂度 ≥10（均值 14.87）、多阶段防污染策划。12 个 SOTA LLM 在
    ULT 上平均 Pass@1 仅 41.32%、变异分数 40.21%，远低于 TestEval 的
    91.79% / 49.69%——**没有任何已发表系统在 ULT 上报告 detection-first
    协议的结果，是本项目独有的空白机会**（独立审查路径 P3）。

评测协议（官方 README + 官方 Ray 脚本核验）：
    1. K-query 迭代：Round 1 只给 FUT（function under test）生成 1 个
       测试，Round i 给 FUT + 之前所有测试生成 1 个新测试（temp 0.0，
       greedy，max 1024 新 token）——与本项目 detection-first 协议的
       "先红后绿"无冲突，但需在适配层显式说明；
    2. mutation 用 Cosmic-Ray（官方脚本 Ray/generate_mutation_details.py），
       mutant killed 判据 = 套件在变异代码上失败且在原代码上通过；
       评测主指标为 **mutation score（Mut@k）**。

⚠️ 官方数据一手核验勘误（2026-10-12，git clone 官方仓库实测，
datasets/ 目录三个文件逐项核验）：
    - 官方仓库 README 的"Data Preservation Notice"称"不发布
      ground-truth tests"，但 `datasets/ULT.jsonl`（全量 3,909 函数）
      的每条记录实际**携带 `tests` 字段**（list[str]，每函数 5 条官方
      测试函数）——README 声明与数据文件实况不一致；
    - `datasets/ULT_Lite.jsonl`（200 任务子集）携带 `test_list` 字段
      （list[str]，每条为断言片段而非完整 test 函数）；
    - `datasets/PLT.jsonl`（18,310 函数，Pass@k 对照集）携带
      `test_input` 字段（输入样本，非测试函数）。
    本加载器据此**记录官方测试材料**（test_code / total_test_count /
    metadata["gold_tests"]）：材料存在时 M1 detection 可测（官方测试
    作为 gold 材料），同时保留 ULT 官方评测口径——mutation score
    （Mut@k）仍为主指标、detection 为辅助指标（与独立审查
    "coverage 降级为辅助指标、mutation 为主指标"的结论一致）。
    无官方测试材料（字段缺失/空）时仍按"诚实不可测"口径置
    metadata["no_gold_tests"]=True、test_code=""。

数据格式（相对 self.data_dir，默认 ~/.cache/aitester/ult/）：
    文件解析顺序（三选一，首个命中即用）：
    1. data_dir 直接指向 `.jsonl` 文件（官方 ULT.jsonl / ULT_Lite.jsonl
       均为 JSON 数组格式，本加载器直接兼容，无需转换）；
    2. data_dir 目录下 `ult_manifest.jsonl`（本项目转换脚本
       scripts/tools/convert_ult_manifest.py 产物，逐行 JSONL）；
    3. data_dir 目录下 `manifest.jsonl`。
    每任务字段（官方名 → 兼容名）：
    {
      "func_name": "toTextType",        # 或 "function_name"（必需，可导入标识符）
      "code": "def toTextType...",      # 或 "source_code"（必需，函数全文，FUT）
      "prompt": "Render a type...",     # 可选（官方任务描述）
      "tests": ["def test_...", ...],   # 或 "test_list" / "test_cases"（可选，官方测试材料）
      "cyclomatic_complexity": 11       # 可选（难度分层用）
    }

获取方式：ULT 官方仓库（github.com/huangd1999/UnLeakedTestBench）的
 datasets/ 目录直接提供上述 JSONL 文件（注意：文件名为 .jsonl 但内容
 为 JSON 数组，非逐行 JSONL——本加载器两种格式均支持），经
 AITESTER_ULT_DATA 指向数据目录（设到 datasets/ 目录即可，如
 AITESTER_ULT_DATA=~/.cache/aitester/ult_repo/datasets，
 并可用 subset="lite" 指定 ULT_Lite.jsonl）。本模块不内置抓取脚本
 （与 QuixBugs/BugsInPy 同口径，避免网络依赖与许可争议）。

任务口径：
    - task_id = ult__<function_name>（末段=模块名，中性可导入标识符）；
    - instance_code = source_code（被测函数全文）；
    - test_code = 官方测试材料（tests/test_list 非空时），否则 ""；
    - total_test_count = 官方测试条数（无材料时 0）；
    - metadata["no_gold_tests"] = True 当且仅当无官方测试材料；
      metadata["gold_tests"] = 官方测试材料（list[str]，供 M1 判分）；
    - metadata["suggested_function"] = function_name。
    - metadata["mutation_primary_metric"] = True（ULT 官方评测口径：
      mutation score（Mut@k）为主指标，detection/coverage 为辅助指标——
      与独立审查"coverage 降级为辅助指标、mutation 为主指标"的结论一致）。
"""

from __future__ import annotations

import ast
import json
import logging
import os
import re
from typing import Any, ClassVar

from src.datasets.dataset_loader import BaseDatasetLoader, BenchmarkTask

logger = logging.getLogger(__name__)

# 官方字段名 → 加载器内部字段名（兼容映射；官方仓库 2026-10-12 一手核验）
_FIELD_ALIASES: dict[str, str] = {
    "func_name": "function_name",
    "code": "source_code",
    "test_list": "test_cases",
    "tests": "test_cases",
}


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


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    """官方/兼容字段名归一化（func_name→function_name、code→source_code、
    tests/test_list→test_cases）；tests 字段两种形态（list / 字符串化 JSON）
    统一为 list[str]。"""
    normalized: dict[str, Any] = {}
    for key, raw_value in row.items():
        target = _FIELD_ALIASES.get(key, key)
        value: Any = raw_value
        if target == "test_cases" and isinstance(value, str):
            # 字符串化 JSON 数组（官方 ULT.jsonl 部分记录的 tests 形态）
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                value = [value] if value.strip() else []
        normalized[target] = value
    return normalized


def _iter_records(manifest: str):
    """逐条产出任务记录：兼容逐行 JSONL（旧 manifest / 转换脚本产物）与
    JSON 数组（官方 ULT.jsonl / ULT_Lite.jsonl——文件名为 .jsonl 但内容
    为顶层数组，官方仓库 2026-10-12 一手核验）。"""
    with open(manifest, encoding="utf-8") as f:
        head = f.readline()
    stripped = head.lstrip()
    if stripped.startswith("["):
        # JSON 数组（官方文件格式）
        with open(manifest, encoding="utf-8") as f:
            try:
                records = json.load(f)
            except json.JSONDecodeError as e:
                logger.warning("ULT manifest JSON 数组解析失败: %s", e)
                return
            if isinstance(records, list):
                for row in records:
                    if isinstance(row, dict):
                        yield row
        return
    # 逐行 JSONL
    with open(manifest, encoding="utf-8") as f:
        for line_no, raw in enumerate(f, 1):
            line = raw.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as e:
                logger.warning("ULT manifest 第 %d 行解析失败（跳过）: %s", line_no, e)
                continue


class ULTDataset(BaseDatasetLoader):
    """ULT（UnLeakedTestbench）基准加载器。

    与 QuixBugs/BugsInPy 加载器同模式（manifest 本地解析），目录缺失时
    返回空数据集 + warning（优雅降级，不阻断 CI / 精简环境）。

    官方测试材料（2026-10-12 勘误）：官方 `datasets/ULT.jsonl` 每条记录
    实际携带 `tests` 字段（list[str]，每函数 5 条官方测试），`ULT_Lite.jsonl`
    携带 `test_list`（list[str] 断言片段）——README 的"不发布 gold tests"
    声明与数据文件实况不一致。本加载器记录官方测试材料
    （test_code / total_test_count / metadata["gold_tests"]），material
    缺失时才按"诚实不可测"口径置 no_gold_tests=True。评测主指标仍为
    ULT 官方口径的 mutation score（Mut@k）。

    subset 口径（2026-10-12 接线）：subset="lite" 且 data_dir 为目录时
    优先加载 `ULT_Lite.jsonl`（官方 200 任务子集）；data_dir 直接指向
    文件时忽略 subset（显式文件优先）。
    """

    DATASET_NAME = "ult"
    SUPPORTS_SUBSET = True
    _MANIFEST_NAMES: ClassVar[tuple[str, ...]] = ("ult_manifest.jsonl", "manifest.jsonl")
    _SUBSET_FILENAMES: ClassVar[dict[str, str]] = {
        "lite": "ULT_Lite.jsonl",
        "full": "ULT.jsonl",
    }
    SUPPORTED_SUBSETS: ClassVar[frozenset[str] | None] = frozenset(_SUBSET_FILENAMES)
    _MAX_NAME_LEN: ClassVar[int] = 40  # task_id 末段长度预算（可导入标识符）

    def __init__(self, subset: str | None = None, data_dir: str | None = None) -> None:
        # data_dir 显式参数 > AITESTER_ULT_DATA 环境变量 > 默认缓存目录
        super().__init__(subset=subset, data_dir=data_dir or os.getenv("AITESTER_ULT_DATA") or None)

    def _manifest_path(self) -> str | None:
        # 显式文件路径优先（data_dir 直接指向 .jsonl）
        if self.data_dir.endswith(".jsonl") and os.path.exists(self.data_dir):
            if self.subset:
                self.subset_fallback_reason = f"数据源为显式文件 {self.data_dir}，--subset 不生效"
            return self.data_dir
        # subset 指定的官方子集文件（lite → ULT_Lite.jsonl）
        if self.subset:
            if self.subset not in self._SUBSET_FILENAMES:
                self.subset_fallback_reason = (
                    f"未知子集 {self.subset!r}（支持: {', '.join(sorted(self._SUBSET_FILENAMES))}）"
                )
            elif os.path.isdir(self.data_dir):
                candidate = os.path.join(self.data_dir, self._SUBSET_FILENAMES[self.subset])
                if os.path.exists(candidate):
                    return candidate
                # 不能静默换成通用 manifest：调用方会以为校验/跑批的是请求的子集
                self.subset_fallback_reason = f"未找到子集文件 {os.path.basename(candidate)}，已回退到通用 manifest"
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
                "ULT manifest 未找到: %s（期待 %s 之一，或直接指向 .jsonl 文件；"
                "设 AITESTER_ULT_DATA 指向数据目录，官方仓库 datasets/ 目录可直接使用）",
                self.data_dir,
                " / ".join(self._MANIFEST_NAMES),
            )
            return

        loaded = skipped = 0
        for raw_row in _iter_records(manifest):
            if not isinstance(raw_row, dict):
                skipped += 1
                continue
            row = _normalize_row(raw_row)

            source_code = str(row.get("source_code") or "")
            if not source_code.strip():
                skipped += 1
                continue

            func_name = str(row.get("function_name") or "").strip()
            # 函数名中性化：非标识符时回退到 AST 首个顶层函数，再不行才用任务序号
            if not func_name.isidentifier():
                func_name = _first_function_name(source_code) or f"func{loaded + skipped + 1}"
            func_name = re.sub(r"\W", "_", func_name)[: self._MAX_NAME_LEN].strip("_") or f"func{loaded + skipped + 1}"

            # 圈复杂度（可选，难度分层用）；坏值保守置 None
            complexity = row.get("cyclomatic_complexity")
            if not isinstance(complexity, int) or complexity < 0:
                complexity = None

            # 官方测试材料（2026-10-12 勘误）：tests / test_cases（test_list
            # 归一化）非空时记录为 gold 材料——M1 detection 可测（官方测试作
            # gold），同时评测主指标保持 ULT 官方口径 mutation score（Mut@k）。
            gold_tests = row.get("test_cases")
            if isinstance(gold_tests, str):
                gold_tests = [gold_tests] if gold_tests.strip() else []
            if not isinstance(gold_tests, list):
                gold_tests = []
            gold_tests = [str(t) for t in gold_tests if str(t).strip()]

            # 官方任务描述（prompt 字段，可选；缺省时回退旧 manifest 的
            # problem_statement 字段）
            prompt = str(row.get("prompt") or row.get("problem_statement") or "").strip()
            # M1 判分材料归一化（2026-10-12 批次）：ULT 官方测试材料两种形态：
            #   a) 完整 pytest 函数（tests 字段元素以 `def ` 开头）——直接使用；
            #   b) 裸断言片段（test_list 字段，元素形如 `assert fn(...) == ...`）
            #      ——缺 pytest 函数包装，_m1_metrics._run_pytest_in_tmp 无法收集。
            # 包装策略：裸断言行包装为 `import <module>` + `test_<i>` 函数；完整
            # 函数直接拼接（与 _m1_metrics 单文件口径一致）。模块名 = task_id
            # 末段（与 _extract_gold_material 派生规则同构）。写回
            # metadata["test_cases"] / metadata["fixed"]（fixed = 被测函数全文，
            # 即"无缺陷"基线）——M1 detection 三段判定可测。
            alt_test_code = "\n".join(gold_tests) if gold_tests else ""
            module_name_alt = func_name.replace("-", "_")[:50]
            if alt_test_code.strip():
                # 包装策略：含行首裸断言（`assert ` 在行首，无缩进）→ 包装为
                # pytest 函数；否则（全部是完整 def/class 块）→ 直接拼接。
                # 行首识别不 lstrip——避免把 def 块内缩进的 assert 误识别。
                has_bare_asserts = alt_test_code.lstrip().startswith("assert ") or any(
                    line.startswith("assert ") for line in alt_test_code.splitlines()
                )
                if has_bare_asserts:
                    # 裸断言片段 → 包装为 pytest 函数。
                    # import 用 `from <mod> import <fn>`：module 名（task_id
                    # 末段）与函数名可能不一致（如 task_id 末段是中性化模块名，
                    # 函数名是原始标识符）。`from <mod> import <fn>` 把函数名
                    # 绑定到断言中调用的标识符（如 `assert fnA(1) == 2` 中的
                    # `fnA`），使 M1 判分可直接收集运行。
                    fn_name = func_name  # 与 assert_lines 中调用的标识符一致
                    non_assert_lines = [
                        line
                        for line in alt_test_code.splitlines()
                        if line.strip() and not line.strip().startswith("assert")
                    ]
                    assert_lines = [line for line in alt_test_code.splitlines() if line.strip().startswith("assert")]
                    wrapped_lines: list[str] = [f"from {module_name_alt} import {fn_name}"]
                    wrapped_lines.extend(non_assert_lines)
                    wrapped_lines.extend(
                        f"def test_{i}():\n    {line.strip()}\n" for i, line in enumerate(assert_lines, start=1)
                    )
                    wrapped_test = "\n".join(wrapped_lines) + "\n"
                else:
                    # 完整 pytest 函数 → 直接拼接
                    wrapped_test = alt_test_code
            else:
                wrapped_test = ""
            self._tasks.append(
                BenchmarkTask(
                    task_id=f"ult__{func_name}",
                    repo_name="ult",
                    problem_statement=(
                        f"ULT function {func_name}（圈复杂度 {complexity if complexity is not None else '未知'}）"
                        + (f"；任务：{prompt}" if prompt else "")
                    ),
                    instance_code=source_code,
                    # 官方测试材料（2026-10-12 勘误）：ULT.jsonl tests 字段
                    # 实为 list[str] 官方测试函数——非空时作为 gold 材料记录，
                    # M1 detection 可测；空时按"诚实不可测"口径置空。
                    # 2026-10-12 M1 归一化：test_code = 包装后的 pytest 函数
                    # 形式（_m1_metrics 可直接消费）；原始断言片段保留在
                    # metadata["gold_tests_raw"]（审计用途）。
                    test_code=wrapped_test,
                    expected_pass_count=len(gold_tests),
                    total_test_count=len(gold_tests),
                    metadata={
                        "source": "ult",
                        "function_name": func_name,
                        "signature": str(row.get("signature") or ""),
                        "cyclomatic_complexity": complexity,
                        # 下游评测口径：mutation score（Mut@k）为主指标、
                        # detection 为辅助指标（ULT 官方评测协议）
                        "mutation_primary_metric": True,
                        # 2026-10-12 勘误：no_gold_tests 仅在官方测试材料
                        # 缺失/为空时为 True（此前 W4b 恒置 True 基于
                        # "官方不发布 gold tests" 的误读，见模块 docstring）
                        "no_gold_tests": not gold_tests,
                        "gold_tests": gold_tests,
                        "gold_tests_raw": alt_test_code,
                        # M1 判分归一化材料（_extract_gold_material 消费）：
                        # test_cases = 包装后的 pytest 函数（_m1_metrics 直接
                        # 可判分）；fixed = 被测函数全文（ULT 无缺陷版本，
                        # 即"无缺陷"基线，三段判定 fixed 侧 = 原码）。
                        "test_cases": wrapped_test,
                        "fixed": source_code,
                        "suggested_function": func_name,
                        "is_cross_file": False,
                    },
                )
            )
            loaded += 1
        logger.info(
            "ULT 加载完成：%d 个任务（跳过 %d 条无效记录；带官方测试材料 %d 个；评测主指标 mutation score（Mut@k））",
            loaded,
            skipped,
            sum(1 for t in self._tasks if t.metadata.get("gold_tests")),
        )


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    ds = ULTDataset()
    logger.info("ULT: %d tasks", ds.size)
