"""
数据集加载模块：支持 SWE-bench 和 Defects4J-Python 格式的标准数据集。

提供统一的数据集接口，将不同基准测试的数据加载为 AITester 可消费的 Task 对象。

结构说明（优化轮次拆分）：本模块保留数据模型（BenchmarkTask）、抽象基类
（BaseDatasetLoader）、SWE-bench 加载器（SWEBenchDataset，含模块级 `_datasets`
全局供测试 patch）与工厂函数；Defects4J-Python 与内置示例数据集已拆分至
dataset_defects4j.py / dataset_inmemory.py，并经 re-export 维持旧导入路径。

使用方式：
    from src.datasets.dataset_loader import SWEBenchDataset, Defects4JPYDataset, load_dataset
    dataset = SWEBenchDataset("full")
    for task in dataset.tasks:
        result = run_single_task(task)
"""

from __future__ import annotations

import json
import logging
import os
import re
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, ClassVar

from config import SWE_BENCH_ENRICHMENT

logger = logging.getLogger(__name__)

# 数据集下载依赖（HuggingFace datasets 库）。可选导入：
# 未安装时模块仍可加载，download_from_huggingface 会在调用时抛出 ImportError。
# 使用模块级引用（_datasets）以便测试通过 patch 替换，避免真实网络下载。
try:
    import datasets as _datasets
except ImportError:
    _datasets = None

# ─── 数据模型 ─────────────────────────────────────────────────────────────────


@dataclass
class BenchmarkTask:
    """
    基准测试任务标准模型。

    所有数据集加载器均输出此格式的任务，便于 AITester 统一消费。

    属性:
        task_id: 任务唯一标识（如 "django__django-12345"）。
        repo_name: 仓库名称（如 "django/django"）。
        problem_statement: 问题描述 / bug 报告文本。
        instance_code: 有缺陷的原始代码（将被 AITester 分析并修复）。
        test_code: 对应的测试代码（用于验证修复结果）。
        expected_pass_count: 期望通过的最小测试用例数。
        total_test_count: 总测试用例数。
        metadata: 附加元数据（如 GitHub issue 链接、commit hash 等）。
    """

    task_id: str
    repo_name: str
    problem_statement: str
    instance_code: str
    test_code: str
    expected_pass_count: int
    total_test_count: int
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def passed_count(self) -> int:
        """已通过的测试数（初始为 0，随修复过程更新）。"""
        return self.metadata.get("passed_count", 0)

    @property
    def pass_rate(self) -> float:
        """通过率（0.0 - 100.0）。"""
        if self.total_test_count == 0:
            return 0.0
        return (self.passed_count / self.total_test_count) * 100.0

    def mark_passed(self, count: int) -> None:
        """记录本轮修复后通过的测试数。"""
        self.metadata["passed_count"] = count
        logger.debug(
            "任务 %s: 通过 %d/%d 测试，通过率 %.1f%%",
            self.task_id,
            count,
            self.total_test_count,
            self.pass_rate,
        )


# ─── 抽象基类 ─────────────────────────────────────────────────────────────────


class BaseDatasetLoader(ABC):
    """
    数据集加载器抽象基类。

    所有具体数据集实现均应继承此类，实现 _load_raw_data() 方法。

    属性:
        data_dir: 数据集根目录（默认为 ~/.cache/aitester/<dataset_name>/）。
        subset: 数据子集名称（如 "full", "lite", "mini"），None 表示全部。
    """

    DATASET_NAME: str = "base"
    DEFAULT_CACHE_DIR: str = os.path.join(os.path.expanduser("~"), ".cache", "aitester")

    def __init__(self, subset: str | None = None, data_dir: str | None = None) -> None:
        """
        初始化数据集加载器。

        Args:
            subset: 数据子集名称。None 表示加载全部数据。
            data_dir: 显式覆盖数据集根目录（2.1：SWE-rebench 等
                外部基准经 load_dataset(kwargs) 注入；None 时用默认缓存目录）。
        """
        self.subset = subset
        self.data_dir = data_dir or os.path.join(self.DEFAULT_CACHE_DIR, self.DATASET_NAME)
        self._tasks: list[BenchmarkTask] = []
        self._loaded = False
        # task_id 索引（2026-09-26 全面审查：get_task_by_id 由 O(n) 线性扫描
        # 降为 O(1) 查表——SWE-bench full 2294 任务 × benchmark 循环逐查
        # 原为 O(n²)）。懒建：_ensure_loaded 加载完成后构建一次；任务列表
        # 运行时新增（InMemoryDataset.add_task）时由调用方自行重建（见下）。
        self._task_index: dict[str, BenchmarkTask] = {}
        self._index_size = 0  # 索引对应的 _tasks 长度（惰性失效判断，O(1)）

    def _ensure_loaded(self) -> None:
        """确保数据已加载（惰性加载模式）。"""
        if not self._loaded:
            self._load_raw_data()
            self._loaded = True
            # 加载完成后重建 task_id 索引（全量一次，O(n)）
            self._rebuild_task_index()

    def _rebuild_task_index(self) -> None:
        """全量重建 task_id 索引（_load_raw_data 完成后 / 索引失效时调用）。"""
        self._task_index = {t.task_id: t for t in self._tasks}
        self._index_size = len(self._tasks)

    def _rebuild_task_index_if_stale(self) -> None:
        """按需重建索引：_tasks 长度与索引记录不一致（外部直接
        _load_raw_data + _loaded=True 绕过、或 add_task 追加）时重建
        （O(n) 一次，后续 O(1)；正常 _ensure_loaded 路径长度一致，O(1) 短路）。"""
        if len(self._tasks) != self._index_size:
            self._rebuild_task_index()

    def add_task(self, task: BenchmarkTask) -> None:
        """向数据集追加任务（InMemoryDataset / 外部动态扩展）。

        2026-09-26 全面审查：原 InMemoryDataset.add_task 直接 append
        （无索引维护），现统一在基类实现——追加后 _tasks 长度变化，
        下次 get_task_by_id 时经 _rebuild_task_index_if_stale 惰性重建索引。
        """
        self._tasks.append(task)

    @property
    def tasks(self) -> list[BenchmarkTask]:
        """返回所有任务列表（惰性加载）。"""
        self._ensure_loaded()
        return self._tasks

    @property
    def task_ids(self) -> list[str]:
        """返回所有任务 ID 列表。"""
        return [t.task_id for t in self.tasks]

    @property
    def size(self) -> int:
        """数据集规模（任务总数）。"""
        return len(self.tasks)

    @abstractmethod
    def _load_raw_data(self) -> None:
        """
        加载原始数据并填充 self._tasks。

        子类必须实现此方法。加载失败时应抛出 RuntimeError 而非静默忽略。
        """
        raise NotImplementedError

    def __len__(self) -> int:
        return self.size

    def __iter__(self) -> Iterator[BenchmarkTask]:
        self._ensure_loaded()
        return iter(self._tasks)

    def get_task_by_id(self, task_id: str) -> BenchmarkTask | None:
        """
        按 task_id 查找任务（O(1) 查表，2026-09-26 全面审查：原 O(n) 线性扫描
        在 SWE-bench full 2294 任务 × benchmark 循环逐查场景下为 O(n²)）。

        Args:
            task_id: 任务唯一标识。

        Returns:
            匹配的任务对象，未找到时返回 None。
        """
        self._ensure_loaded()
        self._rebuild_task_index_if_stale()
        return self._task_index.get(task_id)

    def filter_by_repo(self, repo_pattern: str) -> list[BenchmarkTask]:
        """
        按仓库名称正则过滤任务。

        Args:
            repo_pattern: 正则表达式模式（如 "django" 匹配所有 django 相关任务）。

        Returns:
            匹配的任务列表。
        """
        self._ensure_loaded()
        pattern = re.compile(repo_pattern, re.IGNORECASE)
        return [t for t in self._tasks if pattern.search(t.repo_name)]


# ─── SWE-bench 数据集加载器 ───────────────────────────────────────────────────


class SWEBenchDataset(BaseDatasetLoader):
    """
    SWE-bench 风格数据集加载器。

    SWE-bench（Software Engineering Bench）是业界标准的大模型代码修复基准，
    包含来自真实开源仓库的 bug-fix 配对数据。

    数据格式说明：
        每个任务对应一个 JSON 文件，包含以下字段：
        - instance_id: 任务唯一标识（如 "django__django-12345"）
        - repository: 仓库路径（如 "django/django"）
        - problem_statement: GitHub issue 描述
        - test_before_patches: 原始测试代码
        - patch: 官方修复补丁（用于验证）

    注意：由于 SWE-bench 需要大量手动下载和数据准备，
    本加载器默认从本地缓存目录加载 JSON 文件。
    若缓存目录不存在，会尝试从 HuggingFace 自动下载（需网络连接）。

    使用方式：
        dataset = SWEBenchDataset(subset="full")
        for task in dataset.tasks:
            logger.info("%s: %s", task.task_id, task.problem_statement[:50])
    """

    DATASET_NAME = "swe_bench"

    # 可选子集及其对应的任务数量（用于快速预览）
    SUBSET_MAP: ClassVar[dict[str, int]] = {
        "lite": 500,  # Lite 子集：500 个任务，适合快速验证
        "mini": 50,  # Mini 子集：50 个任务，适合开发调试
        "full": 2294,  # 完整数据集：2294 个任务
    }

    def _resolve_jsonl_paths(self) -> list[str]:
        """解析本加载器实例应读取的 JSONL 文件路径列表。

        规则（与 download_from_huggingface 的写盘约定一致）：
        - 指定 subset：读取 swe_bench_<subset>_instances.jsonl（子集专属文件）
        - 未指定 subset：合并 data_dir 下所有 swe_bench_*_instances.jsonl，
          并兼容旧版通用文件 swe_bench_instances.jsonl

        Returns:
            按确定性顺序（sorted）排列的 JSONL 文件路径列表（可能为空）。
        """
        if self.subset:
            path = os.path.join(self.data_dir, f"swe_bench_{self.subset}_instances.jsonl")
            return [path]

        if not os.path.isdir(self.data_dir):
            # 目录不存在时仍返回旧版通用路径，供调用方打印明确的缺失提示
            return [os.path.join(self.data_dir, "swe_bench_instances.jsonl")]
        paths = [
            os.path.join(self.data_dir, name)
            for name in sorted(os.listdir(self.data_dir))
            if name.startswith("swe_bench_") and name.endswith("_instances.jsonl")
        ]
        # 兼容旧版通用文件名（无子集标识）
        legacy = os.path.join(self.data_dir, "swe_bench_instances.jsonl")
        if os.path.exists(legacy) and legacy not in paths:
            paths.append(legacy)
        return paths

    @staticmethod
    def _extract_suggested_function(patch_text: str) -> str | None:
        """从 SWE-bench 官方修复补丁（patch）提取目标函数名。

        解析 git diff 的 hunk 头（@@ -a,b +c,d @@ <上下文行>），
        上下文行若为函数定义（def/async def），提取函数名。
        用于 benchmark 的 target_function 定位（P0：target_function 准确性）。

        Args:
            patch_text: 官方修复补丁文本（git diff 格式），可为空。

        Returns:
            首个可识别的目标函数名；无法识别时返回 None。
        """
        if not patch_text:
            return None
        for line in patch_text.splitlines():
            if not line.startswith("@@"):
                continue
            # hunk 头格式：@@ -a,b +c,d @@ <上下文>（上下文可能为空）
            # 按 "@@" 切分后第 3 段（parts[2]）即上下文文本
            parts = line.split("@@")
            if len(parts) < 3:
                continue
            context_line = parts[2].strip()
            m = re.match(r"(?:async\s+)?def\s+(\w+)", context_line)
            if m:
                return m.group(1)
        return None

    @staticmethod
    def validate_task(task: BenchmarkTask) -> list[str]:
        """校验单个任务的加载质量（P0：数据集加载正确性排查工具）。

        检查项：
        1. instance_code 是否非兜底值（官方 SWE-bench JSONL 不含源码字段，
           兜底为 issue 文本的任务在基准中只能验证流程、不能产生有效修复对比）；
        2. instance_code 是否为合法 Python（可 compile）；
        3. test_code 是否非空且包含测试用例（def test_ / assert）；
        4. total_test_count 是否 > 0（用例数未知的任务无法计算通过率）。

        Args:
            task: 待校验的 SWE-bench 任务。

        Returns:
            问题描述列表（空列表 = 加载质量健康）。
        """
        issues: list[str] = []
        if not task.instance_code or task.instance_code == task.problem_statement:
            issues.append("instance_code 兜底为 issue 文本（JSONL 无源码字段），无法产生有效修复对比")
        else:
            try:
                compile(task.instance_code, f"{task.task_id}_instance", "exec")
            except SyntaxError as e:
                issues.append(f"instance_code 不是合法 Python 源码: {e.msg} (line {e.lineno})")
        if not task.test_code.strip():
            issues.append("test_code 为空")
        elif "def test_" not in task.test_code and "assert" not in task.test_code:
            issues.append("test_code 未包含测试用例（无 def test_ / assert）")
        if task.total_test_count <= 0:
            issues.append("total_test_count 为 0，无法计算通过率")
        return issues

    def quality_report(self) -> dict[str, list[str]]:
        """生成已加载任务的加载质量报告（task_id → 问题列表，仅列有问题项）。

        用法示例（P0 排查方法：手动检查 2-3 个任务的加载结果）：
            ds = SWEBenchDataset("lite")
            report = ds.quality_report()
            for task_id, issues in list(report.items())[:3]:
                print(task_id, issues)

        Returns:
            {task_id: [问题描述, ...]}；全部健康时为空 dict。
        """
        report: dict[str, list[str]] = {}
        for task in self.tasks:
            issues = self.validate_task(task)
            if issues:
                report[task.task_id] = issues
        if report:
            logger.info("SWE-bench 质量报告：%d/%d 个任务存在问题", len(report), len(self._tasks))
        return report

    def tasks_missing_source(self) -> list[str]:
        """2.1 源码补充流程：识别缺失被测源码的任务 instance_id 列表。

        官方 SWE-bench JSONL 不含被测源码字段，未配 SWE_BENCH_ENRICHMENT
        补充文件时 instance_code 兜底为 issue 文本（validate_task 标记为
        "兜底为 issue 文本"）。本方法返回这些任务的 instance_id（加载顺序），
        供 check-dataset 质量报告输出与 scripts/export_swe_bench_source.py
        的 --instance-ids 批量导出筛选使用。

        Returns:
            instance_id 列表（空列表 = 全部任务源码完整）。
        """
        missing: list[str] = [
            task.task_id
            for task in self.tasks
            if not task.instance_code or task.instance_code == task.problem_statement
        ]
        return missing

    @staticmethod
    def _load_enrichment(enrichment_path: str) -> dict[str, dict[str, Any]]:
        """加载源码补充文件（P0：官方 SWE-bench JSONL 缺被测源码的补全通道）。

        补充文件格式（JSONL，按 instance_id 关联）：
            {"instance_id": "repo__repo-123", "instance_code": "def f(): ...",
             "test_code": "def test_f(): ..."}
        每行至少需含 instance_id；缺失的源码字段会被跳过（仅补全有值的字段）。
        文件不存在或为空时返回空映射（不影响主加载流程）。

        Args:
            enrichment_path: 补充文件路径（环境变量 SWE_BENCH_ENRICHMENT 指定）。

        Returns:
            {instance_id: 补充字段字典}。
        """
        if not enrichment_path or not os.path.exists(enrichment_path):
            return {}
        enriched: dict[str, dict[str, Any]] = {}
        with open(enrichment_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning("补充文件 JSON 解析失败，跳过该行: %s...", line[:80])
                    continue
                row_id = row.get("instance_id")
                if not row_id:
                    continue
                enriched[row_id] = {k: v for k, v in row.items() if v not in (None, "")}
        if enriched:
            logger.info("已加载源码补充文件：%d 条记录（%s）", len(enriched), enrichment_path)
        return enriched

    def _load_raw_data(self) -> None:
        """
        从本地缓存加载 SWE-bench 数据。

        优先从 data_dir 读取 JSONL 文件（子集专属文件或全部子集，见 _resolve_jsonl_paths）；
        若文件不存在，打印提示并返回空列表（允许 gracefully degrade）。
        若设置环境变量 SWE_BENCH_ENRICHMENT，会按 instance_id 合并源码补充文件。
        """
        # 清空任务列表，避免重复加载时数据累积
        self._tasks.clear()
        # 跨文件去重集合：加载多子集 JSONL 时按 instance_id 去重（加载开始时重置，避免重复加载残留）
        self._seen_task_ids: set[str] = set()

        jsonl_paths = self._resolve_jsonl_paths()

        if not jsonl_paths or not any(os.path.exists(p) for p in jsonl_paths):
            logger.warning(
                "SWE-bench 数据未找到: %s\n"
                "请先下载数据集（参考 README.md 中的复现步骤），"
                "或从 HuggingFace 下载后放入 %s/",
                jsonl_paths,
                self.data_dir,
            )
            return

        # 源码补充文件（P0）：官方 SWE-bench JSONL 不含被测源码，
        # 通过 SWE_BENCH_ENRICHMENT 指定的 JSONL 按 instance_id 补 instance_code/test_code
        enrichment = self._load_enrichment(SWE_BENCH_ENRICHMENT)

        loaded = 0
        for jsonl_path in jsonl_paths:
            if not os.path.exists(jsonl_path):
                continue
            with open(jsonl_path, encoding="utf-8") as f:
                for line_num, line in enumerate(f, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError as e:
                        logger.warning("JSON 解析失败（%s 第 %d 行）: %s", jsonl_path, line_num, e)
                        continue

                    task = self._build_task_from_swe_row(data, enrichment, fallback_task_id=f"swe_{line_num}")
                    if task is None:
                        # 重复 instance_id（mini 是 lite 的子集，多文件合并时去重）
                        continue
                    self._tasks.append(task)
                    loaded += 1

        logger.info("SWE-bench 加载完成：%d 个任务", loaded)

    @staticmethod
    def _parse_swe_test_list(value: Any) -> list[str]:
        """解析 SWE-bench 官方 JSONL 的测试节点列表字段。

        官方格式：JSON 编码的字符串（'["test_a.py::t1", "test_b.py::t2"]'）；
        兼容已是 list 的自定义 JSONL。解析失败/类型不符 → 空 list（路由
        条件永不命中，历史口径零变化）。

        Args:
            value: FAIL_TO_PASS / PASS_TO_PASS 字段原始值。

        Returns:
            测试节点字符串列表（可能为空）。
        """
        if isinstance(value, list):
            return [str(item) for item in value if item]
        if isinstance(value, str) and value.strip():
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return [str(item) for item in parsed if item]
            except (json.JSONDecodeError, TypeError):
                logger.warning("测试节点列表解析失败（按空处理）: %s...", value[:80])
        return []

    def _build_task_from_swe_row(
        self, data: dict[str, Any], enrichment: dict[str, dict[str, Any]], fallback_task_id: str
    ) -> BenchmarkTask | None:
        """
        从单条 SWE-bench JSONL 行构建 BenchmarkTask。

        Args:
            data: 解析后的 JSON 行（已按 instance_id 合并源码补充字段）。
            enrichment: 源码补充文件按 instance_id 索引的映射（_load_enrichment 产出）。
            fallback_task_id: 缺少 instance_id 时的兜底任务 ID（带行号便于定位）。

        Returns:
            构建完成的 BenchmarkTask；instance_id 已存在（重复行）时返回 None。
        """
        # 构建 BenchmarkTask
        task_id = data.get("instance_id", fallback_task_id)
        # 合并加载多个子集文件时按 instance_id 去重（mini 是 lite 的子集）
        if task_id in self._seen_task_ids:
            return None
        self._seen_task_ids.add(task_id)
        repo_name = data.get("repository", "unknown")
        problem_statement = data.get(
            "problem_statement",
            f"Fix bug in {repo_name} ({task_id})",
        )
        # 源码补充文件按 instance_id 合并（官方 JSONL 缺源码时的补全通道）
        enriched = enrichment.get(task_id, {})
        data = {**data, **enriched}

        # test_code 字段优先级（兼容自定义与官方字段命名）：
        # 显式测试代码字段 > 官方 test_patch（测试补丁）> test_before_patches
        test_code = data.get("test_code") or data.get("test_patch") or data.get("test_before_patches", "")
        # instance_code 字段优先级：显式源码字段（自定义 JSONL 或
        # 补充文件可提供 instance_code/base_code）> problem_statement 兜底。
        # 官方 SWE-bench JSONL 不含源码字段，只能兜底为 issue 文本，
        # 此类任务在基准中仅验证流程、不产生有效修复对比。
        instance_code = data.get("instance_code") or data.get("base_code") or problem_statement
        # 从官方修复补丁提取目标函数（P0：target_function 定位）
        suggested_function = self._extract_suggested_function(data.get("patch", ""))

        total_tests = data.get("n_tests_before", 0) or data.get("n_tests_after", 0)
        expected_pass = data.get("pass_num_before", 0) or 0
        total_pass = data.get("pass_num_after", 0) or total_tests

        return BenchmarkTask(
            task_id=task_id,
            repo_name=repo_name,
            problem_statement=problem_statement,
            instance_code=instance_code,
            test_code=test_code,
            expected_pass_count=expected_pass,
            total_test_count=total_pass if total_pass > 0 else total_tests,
            metadata={
                "repository": repo_name,
                "instance_id": task_id,
                "original_pass_num": expected_pass,
                "final_pass_num": total_pass,
                "source": "swe_bench",
                # 从官方 patch 的 hunk 头提取的目标函数（可能为 None），
                # benchmark 入口用它初始化 target_function 做 AST 聚焦截取
                "suggested_function": suggested_function,
                # 2.1 数据污染检测：保留官方黄金补丁文本（供
                # experiments/contamination_check 计算重叠度，不直接暴露给 LLM）
                "golden_patch": data.get("patch", ""),
                # P0 仓库级验证（REPO_LEVEL_EXECUTION=true 时经 run_benchmark
                # 路由到 RepoExecutor）：gold 验证口径所需元数据。
                # repo_url 由 repo 路径（org/name）构造 GitHub URL；
                # fail_to_pass / pass_to_pass 为官方 JSONL 的测试节点列表
                # （"test_x.py::test_y"）；base_commit 为官方基础 commit。
                # 字段缺失（旧数据）时为空，路由条件永不命中，口径零变化。
                "repo_url": f"https://github.com/{repo_name}.git" if repo_name != "unknown" else "",
                "base_commit": data.get("base_commit", ""),
                # 官方 JSONL 的 FAIL_TO_PASS / PASS_TO_PASS 是 JSON 编码的
                # 字符串列表（'["a::b", "c::d"]'），解析为 list；解析失败
                # （非 list）时兜底空 list（路由条件永不命中，口径零变化）。
                "fail_to_pass": self._parse_swe_test_list(data.get("FAIL_TO_PASS", "")),
                "pass_to_pass": self._parse_swe_test_list(data.get("PASS_TO_PASS", "")),
                "test_patch": data.get("test_patch", "") or "",
            },
        )

    @classmethod
    def download_from_huggingface(
        cls,
        cache_dir: str | None = None,
        subset: str = "lite",
    ) -> str:
        """
        从 HuggingFace 下载指定子集的 SWE-bench 数据到本地缓存。

        Args:
            cache_dir: 缓存目录，默认为 ~/.cache/aitester/swe_bench/
                （与加载器的 data_dir 一致；此前误写 ~/.cache/aitester/ 导致下载后加载器找不到）。
            subset: 子集名称（"lite"/"mini"/"full"），默认 "lite"。

        Returns:
            下载完成后的本地路径。

        Raises:
            ImportError: datasets 库未安装时抛出。
            RuntimeError: 网络下载失败时抛出。
        """
        if _datasets is None:
            raise ImportError("请下载 HuggingFace datasets 库: pip install datasets")

        # 与 SWEBenchDataset.data_dir（DEFAULT_CACHE_DIR/swe_bench/）对齐
        target_dir = cache_dir or os.path.join(cls.DEFAULT_CACHE_DIR, cls.DATASET_NAME)
        os.makedirs(target_dir, exist_ok=True)

        split_map = {"mini": "lite", "lite": "dev", "full": "full"}
        split = split_map.get(subset, "dev")

        logger.info("正在从 HuggingFace 下载 SWE-bench [%s] 子集 ...", subset)
        try:
            dataset = _datasets.load_dataset("princeton-nlp/SWE-bench", split=split, streaming=False)
        except Exception as e:
            raise RuntimeError(f"SWE-bench 下载失败: {e}") from e

        # 文件名带子集标识，避免不同子集互相覆盖（加载器按子集读取）
        output_path = os.path.join(target_dir, f"swe_bench_{subset}_instances.jsonl")
        with open(output_path, "w", encoding="utf-8") as f:
            for item in dataset:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

        logger.info("SWE-bench [%s] 下载完成，已保存至: %s", subset, output_path)
        return output_path


# 拆分出的子类经 re-export 保持旧导入路径（from src.datasets.dataset_loader
# import Defects4JPYDataset / InMemoryDataset）。放在 SWEBenchDataset 类定义之后：
# dataset_defects4j / dataset_inmemory 需在本模块类定义完成后反向导入
# BaseDatasetLoader / BenchmarkTask，顶层导入会触发循环导入。
# ruff E402/I001：刻意置于模块中部（非顶层），忽略排序告警。
from src.datasets.dataset_defects4j import Defects4JPYDataset  # noqa: E402, I001
from src.datasets.dataset_inmemory import InMemoryDataset  # noqa: E402


# ─── 便捷工厂函数 ─────────────────────────────────────────────────────────────


def load_dataset(
    name: str,
    subset: str | None = None,
    **kwargs: Any,
) -> BaseDatasetLoader:
    """
    根据数据集名称创建对应的加载器实例（工厂函数）。

    支持的名称：
        - "swe_bench" 或 "swebench": SWE-bench 数据集
        - "swe_rebench" 或 "swebench_rebench": SWE-rebench 抗污染基准
          （2.1 数据污染风险应对：字段与 SWE-bench 同构，仅数据文件不同）
        - "defects4j_python" 或 "d4j_py": Defects4J-Python 数据集
        - "in_memory": 内置示例数据集
        - 其他名称返回 InMemoryDataset（允许 graceful degradation）

    Args:
        name: 数据集名称。
        subset: 数据子集名称（可选）。
        **kwargs: 其他传递给构造函数的关键字参数。

    Returns:
        对应的数据集加载器实例。
    """
    name_lower = name.lower().replace("-", "_").replace(" ", "_")

    dataset_map: dict[str, type] = {
        "examples": InMemoryDataset,
        "swe_bench": SWEBenchDataset,
        "swebench": SWEBenchDataset,
        # 2.1 SWE-rebench 抗污染基准：与 SWE-bench 共用 SWEBenchDataset 加载器
        # （字段同构），数据文件经 SWE_BENCH_DATA_DIR / AITESTER_SWE_REBENCH_DIR
        # 环境变量指向 rebench 数据集目录；未配置时加载失败由调用方兜底。
        "swe_rebench": SWEBenchDataset,
        "swebench_rebench": SWEBenchDataset,
        "defects4j_python": Defects4JPYDataset,
        "d4j_py": Defects4JPYDataset,
        "in_memory": InMemoryDataset,
        # "synthetic": SyntheticDataset,  # 使用懒加载避免循环导入
        # "synth": SyntheticDataset,  # 使用懒加载避免循环导入
    }

    # 懒加载 synthetic 以避免循环导入
    if name_lower in ("synthetic", "synth"):
        from src.datasets.synthetic_dataset import SyntheticDataset

        return SyntheticDataset(subset=subset, **kwargs)

    loader_class = dataset_map.get(name_lower, InMemoryDataset)
    instance = loader_class(subset=subset, **kwargs)
    # InMemoryDataset（含 "examples" 别名）需要预填充示例任务
    if isinstance(instance, InMemoryDataset):
        instance.add_sample_tasks()
    return instance


def get_available_datasets() -> list[str]:
    """
    返回当前支持的所有数据集名称列表。

    与 load_dataset 的 dataset_map 保持同步（含别名）：
    未列出的名称调用 load_dataset 时会降级为 InMemoryDataset。

    Returns:
        数据集名称列表（排序后，跨进程/哈希随机化下顺序稳定）。
    """
    return sorted(
        {
            "swe_bench",
            "swebench",
            "swe_rebench",
            "swebench_rebench",
            "defects4j_python",
            "d4j_py",
            "in_memory",
            "examples",
            "synthetic",
            "synth",
        }
    )


if __name__ == "__main__":
    # 快速验证：加载内置示例数据集
    ds = InMemoryDataset.create_with_samples()
    logger.info("内置示例数据集规模: %d 个任务", ds.size)
    for task in ds.tasks:
        logger.info("  - %s: %s", task.task_id, task.problem_statement)
