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
from src.utils.env_utils import env_flag

logger = logging.getLogger(__name__)

# S2（2026-10-11 独立评审落地，F4/K6）：`instance_code` **兜底口径开关**。
#
# 事实：官方 SWE-bench JSONL 不含被测源码字段，历史口径把 `problem_statement`
# （issue 文本）静默兜底为 `instance_code`。后果实测为 **389/389 行工件同时缺
# `instance_code` 与 `detection_rate`**，20/20 任务 `llm_patch_apply_failed`
# ——补丁从未成功应用，而跑批**照常出数**（"静默兜底 ⇒ 静默失效"）。
#
# 两档口径：
#   false（默认，保持历史口径）：兜底为 issue 文本，任务照跑（下游据
#       validate_task / tasks_missing_source 识别"仅验证流程"任务）；
#   true（fail-fast）：该行**判定为无效并从批次剔除**，剔除数 + 任务 ID
#       写入 `SWEBenchDataset.strict_skipped_task_ids`，由 run_benchmark 落
#       provenance（strict_skipped_count）——宁缺毋滥：宁可少跑，不可把
#       "补丁必然应用失败"的任务混进检出率分母。
#
# 命名与环境变量约定：`_ENV` 前缀常量（check_env_budget.py 的静态提取规则
# 之一，登记于 docs/env_budget.yaml）。
_ENV_STRICT_INSTANCE_CODE = "AITESTER_DATASET_STRICT_INSTANCE_CODE"


def _strict_instance_code_enabled() -> bool:
    """读取 instance_code fail-fast 开关（AITESTER_DATASET_STRICT_INSTANCE_CODE）。

    默认 false（历史口径）；"true"/"1"/"yes"/"on" 视为启用。取值非法时
    按默认 false 处理（与项目其余 `_ENV` 布尔开关同口径：不因环境变量
    笔误让跑批崩溃）。
    """
    return env_flag(_ENV_STRICT_INSTANCE_CODE, extra_true=("yes",))


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
        """返回所有任务 ID 列表（惰性加载，O(n) 单次遍历）。

        2026-09-26 全面优化：此前每次调用都触发 `self.tasks`（含
        `_ensure_loaded` + 列表拷贝），benchmark 热循环中反复调用为
        O(n) 冗余。改为直接访问 `self._tasks`（加载状态由
        `_ensure_loaded` 在 `__iter__`/`tasks` 首次调用时已保证）。
        """
        self._ensure_loaded()
        return [t.task_id for t in self._tasks]

    @property
    def size(self) -> int:
        """数据集规模（任务总数）。"""
        self._ensure_loaded()
        return len(self._tasks)

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

    # 2.1 外部数据目录注入（类级 env var 钩子）：key = load_dataset() 的
    # 注册名，value = 外部数据目录环境变量名。swe_rebench / swe_bench_pro 等
    # 注册名经 load_dataset() 按 dataset name 注入各自的环境变量。此前文档声称
    # "数据文件经 AITESTER_SWE_BENCH_PRO_DIR 指向 Pro 数据集目录"但加载器从不读
    # 该环境变量——设置后数据仍从默认缓存目录找文件（G8 全开链路复测数据注入
    # 通道断点，2026-10 修复）。
    _EXTRA_DATA_DIR_ENV: ClassVar[dict[str, str]] = {
        "swe_rebench": "SWE_BENCH_DATA_DIR",
        "swebench_rebench": "SWE_BENCH_DATA_DIR",
        "swe_bench_pro": "AITESTER_SWE_BENCH_PRO_DIR",
        "swebench_pro": "AITESTER_SWE_BENCH_PRO_DIR",
    }

    # 可选子集及其对应的任务数量（用于快速预览）
    SUBSET_MAP: ClassVar[dict[str, int]] = {
        "lite": 500,  # Lite 子集：500 个任务，适合快速验证
        "mini": 50,  # Mini 子集：50 个任务，适合开发调试
        "full": 2294,  # 完整数据集：2294 个任务
    }

    def __init__(self, subset: str | None = None, data_dir: str | None = None, **kwargs: Any) -> None:
        """
        初始化 SWE-bench 风格数据集加载器。

        Args:
            subset: 数据子集名称。None 表示加载全部数据。
            data_dir: 显式覆盖数据集根目录（优先级最高）；None 时依次回退：
                1. 注册名对应的环境变量（_EXTRA_DATA_DIR_ENV，经 load_dataset()
                   按注册名解析；直接用类构造时按注册名逐个探测环境变量）；
                2. 默认缓存目录（DEFAULT_CACHE_DIR/swe_bench/，历史口径）。
            **kwargs: 兼容 load_dataset 工厂透传的额外参数（data_dir_env_value）。
        """
        # 注册名：load_dataset() 传入 data_dir_env_value（str 注册名）；
        # 直接类构造时为 None——逐个探测环境变量（命中即用，零副作用）。
        # 2026-10-01 全面审查 P2 修复：此前直接类构造路径用
        # dict.values() 按"插入顺序"探测——SWE_BENCH_DATA_DIR（swe_rebench）
        # 排在 AITESTER_SWE_BENCH_PRO_DIR 之前，若用户同时设了两个变量
        # 且目标数据集是 swe_bench_pro，会误用 SWE_BENCH_DATA_DIR 指向
        # rebench 目录。现改为显式优先级序（Pro 先于 rebench——Pro 是
        # 更具体的指向，rebench 是泛化兜底），与注册名路径的"精确匹配"
        # 语义对齐。
        registered_name: str | None = kwargs.get("data_dir_env_value") or None
        env_dir: str | None = None
        if registered_name:
            env_dir = os.getenv(self._EXTRA_DATA_DIR_ENV.get(registered_name, "")) or None
        else:
            # 显式优先级序：Pro 数据集变量先于 rebench 泛化变量
            _PROBE_ORDER: tuple[str, ...] = ("AITESTER_SWE_BENCH_PRO_DIR", "SWE_BENCH_DATA_DIR")
            for _env_key in _PROBE_ORDER:
                env_dir = os.getenv(_env_key)
                if env_dir:
                    break
        super().__init__(subset=subset, data_dir=data_dir or env_dir)
        # S2（2026-10-11 独立评审落地）：strict 模式剔除面（instance_id 列表，
        # 加载顺序）——_load_raw_data 每次重载时重置。run_benchmark 读本属性
        # 把剔除数写入 provenance（"有多少任务被剔除"必须可审计，不能只在
        # 日志里一闪而过）。
        self.strict_skipped_task_ids: list[str] = []

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
        self._ensure_loaded()
        report: dict[str, list[str]] = {}
        for task in self._tasks:
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
        供 check-dataset 质量报告输出与 scripts/tools/export_swe_bench_source.py
        的 --instance-ids 批量导出筛选使用。

        Returns:
            instance_id 列表（空列表 = 全部任务源码完整）。
        """
        self._ensure_loaded()
        missing: list[str] = [
            task.task_id
            for task in self._tasks
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
            for raw_line in f:
                line = raw_line.strip()
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
        # S2：strict 剔除面同步重置（重载后旧剔除记录不得残留）
        self.strict_skipped_task_ids.clear()
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
                for line_num, raw_line in enumerate(f, start=1):
                    line = raw_line.strip()
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
        if self.strict_skipped_task_ids:
            # S2：strict 口径下**未打印剔除数等于静默**——历史缺陷正是
            # "389/389 行缺 instance_code 而结果里看不出来"。这里显式点名。
            logger.warning(
                "S2 strict instance_code 模式：%d 个任务因 instance_code 兜底为 issue 文本被剔除"
                "（%s=%s，宁可少跑不可混入无效分母）",
                len(self.strict_skipped_task_ids),
                _ENV_STRICT_INSTANCE_CODE,
                os.getenv(_ENV_STRICT_INSTANCE_CODE),
            )

    @staticmethod
    def _drop_malformed_test_ids(nodes: list[str]) -> tuple[list[str], list[str]]:
        """剔除被截断的测试节点 ID，返回 (保留的, 被剔除的)。

        判据：含 `[`（参数化）但**未以 `]` 收尾** → 判定为截断。
        保守：仅按此形态判定，不做任何"补全"猜测；正常非参数化 ID
        （无 `[`）一律保留。
        """
        kept: list[str] = []
        dropped: list[str] = []
        for node in nodes:
            if "[" in node and not node.rstrip().endswith("]"):
                dropped.append(node)
            else:
                kept.append(node)
        return kept, dropped

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
        # 仓库名：官方 JSONL 的 repo 字段（org/name）优先；兼容旧数据
        # repository 字段（同为 org/name）；均缺失时按 instance_id 的
        # "org__repo" 命名约定推导；都推不出才兜底 "unknown"。
        # 2026-10（G8-lite 复测暴露）：旧口径只读 repository，官方 JSONL
        # 的 repo 字段从未被读取 → repo_name 恒 "unknown" → repo_url 为空 →
        # REPO_LEVEL_EXECUTION 仓库级路由永不命中（"数据集就绪但路由断点"
        # 的第二层缺口）。
        repo_name = (
            data.get("repo") or data.get("repository") or (task_id.split("__")[0] if "__" in task_id else "unknown")
        )
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
        #
        # S2（2026-10-11 独立评审落地）：**兜底改为可配置 fail-fast**。
        # 默认（AITESTER_DATASET_STRICT_INSTANCE_CODE 未设/false）保持历史口径
        # ——兜底 + 照跑；置 true 时该行判定为**无效任务并从批次剔除**
        # （返回 None），instance_id 记入 strict_skipped_task_ids 供
        # run_benchmark 落 provenance。
        #
        # 为何是"剔除"而非"raise"：run_benchmark 对加载失败是**直接崩批**，
        # 而缺源码在真实工件里是**大比例**现象（实测 389/389）——raise 会让
        # strict 模式在当前数据上完全不可用，反而逼人回退到静默兜底。
        # 剔除 + 计数 + 告警使"跑批继续"与"缺口可见"同时成立。
        _instance_code_raw = data.get("instance_code") or data.get("base_code")
        if _instance_code_raw:
            # 保持历史语义：显式源码字段**原样使用**（不做 str() 强转，
            # 避免改变非 str 字段的行为）
            instance_code = _instance_code_raw
        else:
            if _strict_instance_code_enabled():
                # 剔除口径：按 instance_id 记录（task_id 已在上方解析）
                self.strict_skipped_task_ids.append(task_id)
                logger.warning("S2 strict 模式剔除任务（instance_code 兜底为 issue 文本）: %s", task_id)
                return None
            instance_code = problem_statement
        # 从官方修复补丁提取目标函数（P0：target_function 定位）
        suggested_function = self._extract_suggested_function(data.get("patch", ""))

        total_tests = data.get("n_tests_before", 0) or data.get("n_tests_after", 0)
        expected_pass = data.get("pass_num_before", 0) or 0
        total_pass = data.get("pass_num_after", 0) or total_tests

        # total_test_count 兜底口径（SWE-bench 官方 JSONL 无 n_tests_before /
        # pass_num_after 字段，上述读取恒为 0）：FAIL_TO_PASS 是"修复前失败
        # 但修复后必须通过"的测试节点列表，PASS_TO_PASS 是"修复前后均通过"
        # 的测试节点列表。SWE-bench 官方通过判定 = F2P 全绿 + P2P 不回归，
        # 故任务测试用例总数 = len(FAIL_TO_PASS) + len(PASS_TO_PASS)。
        # 2026-09-27 round10 P2：旧口径仅取 len(FAIL_TO_PASS)（分母漏计
        # P2P），使通过率先被低估、修复率被高估。官方字段存在（自定义
        # JSONL）时仍以官方值为准，口径不变。
        fail_to_pass_list = self._parse_swe_test_list(data.get("FAIL_TO_PASS", ""))
        pass_to_pass_list = self._parse_swe_test_list(data.get("PASS_TO_PASS", ""))
        # 2026-10-10 独立审查（E7 §5.4）：**剔除被截断的测试节点 ID**。
        #
        # 事实：上游 `princeton-nlp/SWE-bench` 的 FAIL_TO_PASS/PASS_TO_PASS
        # 中存在被截断的参数化节点 ID（实测 530/24,122 = 2.20%，跨 4 个仓库：
        # sqlfluff 279 / pydicom 173 / marshmallow 41 / astroid 37），例如
        # `...jinja_test.py::test__templater_jinja_slice_file[{%`（缺 `-if ...-%}]`）。
        # 成因在上游数据集（本项目下载脚本仅做 json.dumps 直通），**不可在此修复**。
        #
        # 危害（实测）：pytest 对无法匹配的节点 ID 报
        # `ERROR: not found: <id>` 并以 **rc=4** 中止**整个调用** ——
        # 即**一个坏 ID 毒化该任务的全部测试**（合法 ID 也不会被执行）。
        # 好消息：M1 判分层的 `_looks_like_test_execution_error` 以 `rc>=2`
        # 为执行错误（experiments/_m1_metrics.py:66-84），故该任务记为
        # detection=0.0 而非假检出——**fail-closed 防线成立，无假信号**。
        #
        # 本处只做"标记 + 剔除坏 ID"，使：(a) 合法 ID 仍可被判分；
        # (b) 下游能据 `*_malformed_ids` 获知该任务的 F2P 面不完整。
        # 绝不"猜"补全被截断的 ID（宁缺毋滥）。
        fail_to_pass_list, f2p_malformed = self._drop_malformed_test_ids(fail_to_pass_list)
        pass_to_pass_list, p2p_malformed = self._drop_malformed_test_ids(pass_to_pass_list)
        if total_tests <= 0 and (fail_to_pass_list or pass_to_pass_list):
            total_tests = len(fail_to_pass_list) + len(pass_to_pass_list)
            total_pass = total_pass if total_pass > 0 else len(fail_to_pass_list) + len(pass_to_pass_list)

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
                # 2026-10-10（E7 §5.4）：改用**已剔除截断 ID** 的列表
                # （此前在此处重新解析原始值 → 上面的净化白做）。截断的上游
                # 节点 ID 会让 pytest 以 rc=4 中止整个调用（一个坏 ID 毒化
                # 全任务，合法 ID 也不执行），故这里必须是净化后的列表。
                "fail_to_pass": fail_to_pass_list,
                "pass_to_pass": pass_to_pass_list,
                # 被剔除的截断 ID（观测面）：非空即表示该任务的 F2P/P2P 面
                # **不完整**，下游应据此知晓覆盖率折损，而非静默按完整处理。
                "fail_to_pass_malformed_ids": f2p_malformed,
                "pass_to_pass_malformed_ids": p2p_malformed,
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
            f.writelines(json.dumps(item, ensure_ascii=False) + "\n" for item in dataset)

        logger.info("SWE-bench [%s] 下载完成，已保存至: %s", subset, output_path)
        return output_path


# 拆分出的子类经 re-export 保持旧导入路径（from src.datasets.dataset_loader
# import Defects4JPYDataset / InMemoryDataset）。放在 SWEBenchDataset 类定义之后：
# dataset_defects4j / dataset_inmemory 需在本模块类定义完成后反向导入
# BaseDatasetLoader / BenchmarkTask，顶层导入会触发循环导入。
# ruff E402/I001：刻意置于模块中部（非顶层），忽略排序告警。
from src.datasets.dataset_defects4j import Defects4JPYDataset  # noqa: E402, I001
from src.datasets.dataset_realbugs import BugsInPyDataset, QuixBugsDataset  # noqa: E402
from src.datasets.dataset_ult import ULTDataset  # noqa: E402
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
        - "swe_bench_pro" 或 "swebench_pro": SWE-bench Pro 抗污染基准
          （强 copyleft 设计 + 高区分度任务，字段与 SWE-bench 同构，
          数据文件经 AITESTER_SWE_BENCH_PRO_DIR 环境变量指向）
        - "defects4j_python" 或 "d4j_py": Defects4J-Python 数据集
        - "quixbugs" / "quix_bugs": QuixBugs 真实缺陷基准（W4 阶梯 L1）
        - "bugsinpy" / "bugs_in_py": BugsInPy 真实缺陷基准（W4 阶梯 L2，
          manifest JSONL 口径，见 dataset_realbugs.BugsInPyDataset）
        - "ult" / "unleaked_testbench": ULT 基准（W4b，TOSEM 2026；
          官方 JSON 数组 .jsonl 直接兼容；mutation score（Mut@k）为主
          评测指标，见 dataset_ult.ULTDataset）
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
        # 2.1 SWE-bench Pro 抗污染基准（强 copyleft 设计，GPT-5 Pass@1 仅
        # ~23.3%）：同样共用 SWEBenchDataset 加载器（字段同构），数据文件经
        # AITESTER_SWE_BENCH_PRO_DIR 环境变量指向 Pro 数据集目录；未配置时
        # 加载失败由调用方兜底（与 swe_rebench 注册口径一致）。
        "swe_bench_pro": SWEBenchDataset,
        "swebench_pro": SWEBenchDataset,
        "defects4j_python": Defects4JPYDataset,
        "d4j_py": Defects4JPYDataset,
        # W4（2026-10-05 审查落地）：真实缺陷基准阶梯 L1/L2（real_benchmark_upgrade
        # 设计稿实现）——本地目录解析，目录缺失时空数据集 + warning 优雅降级
        # （与 d4j_py 同口径）；gold 材料对齐合成集（metadata.test_cases/fixed）
        # 使 M1 诚实指标开箱可用。
        "quixbugs": QuixBugsDataset,
        "quix_bugs": QuixBugsDataset,
        "bugsinpy": BugsInPyDataset,
        "bugs_in_py": BugsInPyDataset,
        # W4b（2026-10-10 独立审查落地；2026-10-12 官方仓库一手核验勘误）：
        # ULT 基准（TOSEM 2026，防污染）。官方 JSON 数组 .jsonl 直接兼容；
        # 官方测试材料（tests/test_list）记录为 gold 材料；mutation
        # score（Mut@k）为主评测指标；目录缺失时优雅降级（与 bugsinpy 同口径）。
        "ult": ULTDataset,
        "unleaked_testbench": ULTDataset,
        "in_memory": InMemoryDataset,
        # "synthetic": SyntheticDataset,  # 使用懒加载避免循环导入
        # "synth": SyntheticDataset,  # 使用懒加载避免循环导入
    }

    # 懒加载 synthetic 以避免循环导入
    if name_lower in ("synthetic", "synth"):
        from src.datasets.synthetic_dataset import SyntheticDataset

        return SyntheticDataset(subset=subset, **kwargs)

    loader_class = dataset_map.get(name_lower, InMemoryDataset)
    if loader_class is SWEBenchDataset:
        instance = loader_class(subset=subset, data_dir_env_value=name_lower, **kwargs)
    else:
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
            "swe_bench_pro",
            "swebench_pro",
            "defects4j_python",
            "d4j_py",
            "quixbugs",
            "quix_bugs",
            "bugsinpy",
            "bugs_in_py",
            "ult",
            "unleaked_testbench",
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
