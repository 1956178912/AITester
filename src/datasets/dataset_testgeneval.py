"""TGE（2026-10-28 用户授权配额批落地）：
TestGenEval-Lite 基准加载器（Meta AI facebookresearch/testgeneval，ICLR 2025）。

背景（ADR-0036 判据 B1 配额实验之一；骨架文档 T-2）：
    TestGenEval（Zhang et al., 2024→ICLR 2025）由 SWE-bench 转化而来，
    1,210 个真实 repo 的 code/test 文件对（11 个大型维护良好的 Python 仓库）；
    **TestGenEvalLite 子集 = 160 对**（django 66 / sympy 42 / scikit-learn 20 /
    pytest 12 / matplotlib 7 / astropy 3 / xarray 3 / seaborn 2 / sphinx 2 /
    pylint 2 / flask 1）。官方评测协议依赖 per-repo Docker testbed
    （base_commit 精确对齐 + coverage/mutation 依赖）；本环境无 Docker，
    本加载器按本仓 tmp-tree 协议接入，**与官方数字不可直接比**（口径披露：
    库版本不对齐 + 无 repo 完整环境；官方 GPT-4o 对照 35.2% line 仅供
    量级参照，引用时必须带口径标签）。

数据获取（一手来源，本模块不内置抓取）：
    HuggingFace datasets `kjain14/testgenevallite`（官方 README 指认），
    data/test-00000-of-00001.parquet（160 对主口径）+
    data/dev-00000-of-00001.parquet（15 对）。下载命令（curl，企业代理
    环境不适用 huggingface_hub 的 httpx 代理路径）：
        curl -sL -o test.parquet \\
          "https://huggingface.co/datasets/kjain14/testgenevallite/resolve/main/data/test-00000-of-00001.parquet"
    落盘 ~/.cache/aitester/testgeneval/（或 AITESTER_TESTGENEVAL_DATA 指向）。

任务口径（对齐官方 full-file generation 任务形态）：
    - task_id = "tge__<instance_id>"（instance_id 如 django__django-17087，
      前缀 tge__ 与 ult__ 同风格，中性可导入标识符）；
    - instance_code = code_src（被测 code 文件全文，均值 ~782 LOC）；
    - test_code = test_src（官方人工测试文件全文 = gold 材料）；
    - expected_pass_count = 0、total_test_count = test_src 中 ``def test_``
      函数静态计数（执行判定以 pytest 实跑为准，与 dfsmoke 口径一致）；
    - metadata["gold_tests"] = [test_src]（M1 判分材料，与 ULT 同纪律）；
    - metadata["official_metrics"] = pass@1 / coverage / mutation score
      （官方口径登记，本仓 tmp-tree 协议只产出其中可执行子集的
      pass/coverage 读数）；
    - metadata["preds_context"] = 官方任务切分（first/last/last_minus_one/
      none/preamble，供 test-completion 形态复用）；
    - metadata["tmp_tree_protocol"] = True（口径标签：本仓协议，非官方
      Docker 协议——引用官方对照数字时必须同时披露此标签）。

评测执行提示：code/test 物化到 tmp 树需宿主库可 import（django/sympy 等，
版本与 base_commit 不对齐）；import 失败的实例按"诚实不可测"口径单列
（material_missing 同款纪律），不进 detection 分母。
"""

from __future__ import annotations

import ast
import logging
import os
from typing import Any, ClassVar

from src.datasets.dataset_loader import BaseDatasetLoader, BenchmarkTask
from src.utils.check_status import AST_UNREADABLE_ERRORS

logger = logging.getLogger(__name__)

_SPLIT_FILES: dict[str, str] = {
    # subset 名 → parquet 文件名（官方 HF repo 的 data/ 目录布局）
    "lite": "test.parquet",
    "test": "test.parquet",
    "dev": "dev.parquet",
    "all": "test.parquet",  # "all" = Lite 主口径（160 对）；dev 另名显式请求
}


def _count_test_functions(test_src: str) -> int:
    """静态计数 test 文件中的 ``def test_*`` 函数数（ast 口径，语法失败按 0）。

    只捕 ``SyntaxError`` 会让 ``ValueError`` 族（含 3.14 对孤立代理位抛的
    ``UnicodeEncodeError``）从守卫里抛穿到调用方，故按仓内统一口径
    ``AST_UNREADABLE_ERRORS`` 判定（与 ``parses_as_module`` 同源）。
    """
    try:
        tree = ast.parse(test_src)
    except AST_UNREADABLE_ERRORS:
        return 0
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test")
    )


class TestGenEvalDataset(BaseDatasetLoader):
    """TestGenEvalLite 加载器（HuggingFace parquet → BenchmarkTask）。

    subset：``lite``/``test``（默认主口径，160 对）、``dev``（15 对）、
    ``all``（同 lite）。数据文件缺失时优雅降级为空数据集 + warning
    （与 bugsinpy/ult 同口径），并在 ``subset_fallback_reason`` 留痕。
    """

    DATASET_NAME = "testgeneval"
    SUPPORTS_SUBSET: ClassVar[bool] = True
    SUPPORTED_SUBSETS = frozenset(_SPLIT_FILES)

    def _split_file(self) -> str | None:
        requested = (self.subset or "lite").lower()
        filename = _SPLIT_FILES.get(requested)
        if filename is None:
            self.subset_fallback_reason = f"未知子集 {self.subset!r}（支持: {', '.join(sorted(_SPLIT_FILES))}）"
            filename = _SPLIT_FILES["lite"]
        candidate = os.path.join(self.data_dir, filename)
        if not os.path.exists(candidate):
            self.subset_fallback_reason = (
                f"数据文件缺失 {candidate}（按模块 docstring 的 curl 命令下载 HuggingFace kjain14/testgenevallite）"
            )
            return None
        if self.subset and self.subset not in _SPLIT_FILES:
            pass  # 已在上面记录 fallback 原因
        return candidate

    def _load_raw_data(self) -> None:
        self._tasks.clear()
        path = self._split_file()
        if path is None:
            logger.warning("TestGenEvalLite 数据未找到：%s", self.subset_fallback_reason)
            return

        import pyarrow.parquet as pq  # type: ignore[import-untyped]

        table = pq.read_table(path).to_pylist()
        loaded = skipped = 0
        for row in table:
            if not isinstance(row, dict):
                skipped += 1
                continue
            instance_id = str(row.get("instance_id") or "").strip()
            code_src = str(row.get("code_src") or "")
            test_src = str(row.get("test_src") or "")
            if not instance_id or not code_src.strip():
                skipped += 1
                continue

            preds_ctx = row.get("preds_context") or {}
            metadata: dict[str, Any] = {
                "instance_id": instance_id,
                "base_commit": str(row.get("base_commit") or ""),
                "version": str(row.get("version") or ""),
                "code_file": str(row.get("code_file") or ""),
                "test_file": str(row.get("test_file") or ""),
                "local_imports": list(row.get("local_imports") or []),
                "baseline_covs": row.get("baseline_covs") or {},
                "preds_context": preds_ctx if isinstance(preds_ctx, dict) else {},
                "gold_tests": [test_src] if test_src.strip() else [],
                "official_metrics": "pass@1 / coverage / mutation score（官方 Docker 协议）",
                "tmp_tree_protocol": True,
                "suggested_function": "",  # 文件级任务（非单函数）
            }
            self._tasks.append(
                BenchmarkTask(
                    task_id=f"tge__{instance_id}",
                    repo_name=str(row.get("repo") or ""),
                    problem_statement=(
                        f"为 {row.get('code_file')} 生成完整 pytest 测试文件（full-file generation，官方任务形态）。"
                    ),
                    instance_code=code_src,
                    test_code=test_src,
                    expected_pass_count=0,
                    total_test_count=_count_test_functions(test_src),
                    metadata=metadata,
                )
            )
            loaded += 1
        logger.info(
            "TestGenEvalLite 加载完成：loaded=%d skipped=%d（subset=%s，口径=%s）",
            loaded,
            skipped,
            self.subset or "lite",
            "tmp-tree（非官方 Docker，数字不可与官方直接比）",
        )
