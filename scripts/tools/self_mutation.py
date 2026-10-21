#!/usr/bin/env python3
"""自身测试套件的变异测试驱动器（WP-A：把"测试强度"从覆盖率代理变成实测分数）。

## 为什么需要它（问题定义）

本仓已有覆盖率门禁（行/分支/严格核心），但覆盖率只回答"代码被执行过吗"，
不回答"测试能发现缺陷吗"——`experiments/mutation_testing.py` 的既有变异层服务
**LLM 生成的测试**（被测对象是任务代码，测试代码由模型产出），从未度量**项目
自身测试套件**对自身源码的检出能力。本工具补的正是这个元层面缺口：

- 输入：`src/` 下指定源码文件 + 该项目自己的测试文件；
- 输出：逐模块 killed/survived/invalid/timeout 计数与 mutation score 点估计；
- 用途：暴露"覆盖到了但没有断言强度"的代码面（存活变异体即具体证据）。

## 设计口径（每个选择都在回答"为什么这样做"）

1. **复用而不是重写变异算子**：直接复用
   `experiments.mutation_testing.ExtendedMutationGenerator`（18 类算子、AST 单点
   改动、按变异后代码去重、语法有效性校验）。理由：(a) 该算子集已有 476 处
   mutant 规模的真实产出记录，口径与项目论文实验一致，结果可与其他批次对齐；
   (b) 自研算子会产生第二套"变异语义"，两处口径漂移正是本仓反复治理的问题；
   (c) 18 类含边界替换/比较翻转/布尔取反/语句删除/返回替换，覆盖任务要求。
   本工具只替换"目标"（项目自身源码）与"执行面"（项目自己的测试），
   生成语义零改动。

2. **绝不原地变异**：每个 worker 在 `tempfile` 下持有**独立仓库副本**
   （`src/` 全树 + `config.py` + `pyproject.toml` + `tests/conftest.py` + 目标
   测试文件）。变异体只写进副本，运行前写入、运行后立刻用内存中的原始字节
   还原；工作树字节级不受影响（`tests/test_self_mutation_tool.py` 锁定该契约）。
   为什么不"原地改再还原"：任何崩溃/超时都会把变异体留在工作树里，且并发
   worker 会互相看到对方变异——副本隔离让"测量污染"在结构上不可能发生。

3. **子进程隔离与超时**：子进程 pytest 用
   `src.utils.process_utils.nested_pytest_env`（剔除宿主 PYTEST_PLUGINS /
   PYTEST_ADDOPTS，杜绝宿主配置静默改变 rc）构造环境，且用
   `run_with_timeout`（`start_new_session` + `killpg` 整树终止 + 文件后端）
   而不是 `subprocess.run(timeout=)`——变异体可能让测试陷入死循环，裸 timeout
   只杀直接子进程，pytest 孙进程持有管道写端会让父进程永久阻塞（该根因在
   `experiments/mutation_testing._run_mutant_tests` 有实跑复现记录）。

4. **rc 分类按 pytest 官方退出码，invalid 单列不进分母**：
   - rc == 1（TESTS_FAILED，测试跑起来且有失败）→ **killed**；
   - rc == 0（全部通过）→ **survived**；
   - rc == 2/3/4/5（中断/收集错误/内部错误/用法错误/没收集到测试）或超时
     → **invalid**（超时单独计 timeout）。理由：套件根本没成功运行时，
     "被杀死"与"存活"都无法判定；把它算成存活会低估分数，算成杀死会虚增
     分数，两种都会让指标失去鉴别力。故 invalid 单独披露，不参与
     mutation score = killed / (killed + survived)。
   注意这与 `experiments/mutation_testing._run_mutant_tests` 的**保守口径**
   （rc≠1 一律记存活）刻意不同：那里是给 LLM 测试打分的流水线，宁可低估；
   这里是度量项目自身测试强度，必须显式区分"测试弱"与"测试没跑起来"。

5. **green baseline 前置校验**：正式执行前在副本上跑一遍**未变异**的测试命令。
   测试套件本身红着时，任何变异体的 rc=1 都可能是既有失败而非"被杀死"——
   分数会全部虚增。baseline 不绿时默认中止（退出码 2），只有显式
   `--allow-red-baseline` 才继续并在报告中标记 `measurement_valid=false`。

6. **确定性与可复算**：变异体按源码位置（行号、类型、描述）排序后
   **等距抽样**，同一份源码 + 同一 `--max-mutants` 得到同一变异体集合（ID 取
   变异体代码 sha256 前缀，跨 run 稳定，便于 before/after 对比与击杀归因）；
   子进程固定 `PYTHONHASHSEED=0`、`PYTHONDONTWRITEBYTECODE=1`（避免 __pycache__
   让"写变异体 → 还原"之间出现陈旧字节码）；报告记录 Python/主机/worker/
   样本量/测试命令/git sha，数字可复算。

## 用法

    # 默认 3 个核心模块，2 worker，每文件最多 120 个变异体（等距抽样）
    python scripts/tools/self_mutation.py

    # 指定文件 + CI 口径（分数低于 0.75 退出码 1）
    python scripts/tools/self_mutation.py --files src/utils/env_utils.py,src/utils/atomic_io.py \\
        --workers 2 --fail-under 0.75

    # 只看变异体清单（不执行，零子进程）
    python scripts/tools/self_mutation.py --dry-run --json-out /tmp/inventory.json

    # 用自定义测试命令（模板必须含 {test_files}；{python} 为当前解释器）
    python scripts/tools/self_mutation.py --test-command "{python} -m pytest {test_files} -q -x"

    # 冻结某模块的测试集合（before/after 可比性；击杀测试即在此追加新文件）
    python scripts/tools/self_mutation.py --test-map src/utils/helpers.py=tests/test_helpers_json_property.py,tests/test_self_mutation_targets.py

## 退出码

- 0：正常完成（`--fail-under` 未设或已达标）；
- 1：`--fail-under` 未达标（mutation score 低于阈值）；
- 2：用法/环境错误（文件不存在、baseline 非绿且未放行、测试发现失败等）。

零 LLM / 零网络：只做本地 AST 分析与子进程 pytest；输出
`experiments/results/self_mutation_20261017/` 下的 JSON + Markdown 报告。
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import platform
import shlex
import shutil
import socket
import sys
import tempfile
import threading
import time
from collections import Counter
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# 复用既有变异算子与子进程工具（理由见模块 docstring 口径 1/3）
from experiments.mutation_testing import (  # noqa: E402
    ExtendedMutationGenerator,
    Mutant,
)
from src.utils.process_utils import nested_pytest_env, run_with_timeout  # noqa: E402

# ─── 常量 ────────────────────────────────────────────────────────────────────

#: 默认观测面：3 个核心叶子工具模块（依赖轻、测试独立、是全会话的高频路径）
DEFAULT_MODULES: tuple[str, ...] = (
    "src/utils/env_utils.py",
    "src/utils/helpers.py",
    "src/utils/atomic_io.py",
)

#: 报告默认落点（数据而非代码，ruff 口径下 experiments/results 已被排除）
DEFAULT_REPORT_DIR = _REPO_ROOT / "experiments" / "results" / "self_mutation_20261017"
DEFAULT_JSON_OUT = DEFAULT_REPORT_DIR / "self_mutation_report.json"
DEFAULT_MD_OUT = DEFAULT_REPORT_DIR / "self_mutation_report.md"

_SCHEMA_VERSION = "1.0"

#: 结果分类（timeout 是 invalid 的子类，但报告单独计数以暴露"卡死风险"）
OUTCOME_KILLED = "killed"
OUTCOME_SURVIVED = "survived"
OUTCOME_INVALID = "invalid"
OUTCOME_TIMEOUT = "timeout"
OUTCOME_NOT_RUN = "not_run"

#: pytest 非 0/1 退出码的语义（pytest.ExitCode 官方定义），用于 invalid 归因
_PYTEST_EXIT_REASONS: dict[int, str] = {
    2: "interrupted_or_collection_error(rc=2)",
    3: "internal_error(rc=3)",
    4: "usage_error(rc=4)",
    5: "no_tests_collected(rc=5)",
}

#: 默认测试命令模板：-x 让单个变异体的失败尽早短路（only need 1 counterexample），
#: `-o addopts=` 清空副本 pyproject 的宿主口径 addopts（-v/--timeout 会拖慢且
#: 引入对 pytest-timeout 插件的隐式依赖），`-p no:cacheprovider` 避免写 .pytest_cache。
DEFAULT_TEST_COMMAND = "{python} -m pytest {test_files} -q --tb=no -x -p no:cacheprovider -o addopts="

#: 生成器内部上限（不截断：抽样由 --max-mutants 在生成后统一做，保证 ID/口径稳定）
_GENERATOR_MAX_PER_TASK = 1_000_000

#: 报告里保留的失败输出尾部长度（invalid/timeout 归因用；killed/survived 不保留）
_OUTPUT_TAIL_CHARS = 700


class SelfMutationError(RuntimeError):
    """本工具的可预期用法/环境错误（main 捕获后转退出码 2，而非抛栈）。"""


# ─── 数据模型 ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class MutantOutcome:
    """单个变异体的执行结果（报告的最小记录单元）。"""

    mutant_id: str
    module: str
    mutant_type: str
    line_no: int
    description: str
    code_sha256: str
    outcome: str
    returncode: int | None = None
    duration_s: float = 0.0
    reason: str = ""
    output_tail: str = ""

    def to_dict(self) -> dict[str, Any]:
        """转 JSON 友好的 dict（报告 schema 的 stable 字段顺序）。"""
        return {
            "mutant_id": self.mutant_id,
            "module": self.module,
            "mutant_type": self.mutant_type,
            "line_no": self.line_no,
            "description": self.description,
            "code_sha256": self.code_sha256,
            "outcome": self.outcome,
            "returncode": self.returncode,
            "duration_s": round(self.duration_s, 3),
            "reason": self.reason,
            "output_tail": self.output_tail,
        }


@dataclass(frozen=True)
class ModulePlan:
    """单个目标模块的变异计划（生成 → 剔除生成器无效 → 抽样 → 测试集合）。"""

    module: str
    source_sha256: str
    total_generated: int
    test_files: tuple[str, ...]
    mutants: tuple[Mutant, ...]
    #: 生成器产出的"语义恒等"变异体数（未真正改变代码，剔除）
    filtered_identity: int = 0
    #: 生成器产出的"语法非法"变异体数（不可执行，剔除）
    filtered_syntax_error: int = 0

    @property
    def sampled(self) -> int:
        """本模块实际执行的变异体数（抽样后）。"""
        return len(self.mutants)

    @property
    def executable_pool(self) -> int:
        """剔除生成器无效变异体后的可执行池大小（抽样率的分母）。"""
        return self.total_generated - self.filtered_identity - self.filtered_syntax_error


# ─── 基础工具 ────────────────────────────────────────────────────────────────


def sha256_text(text: str) -> str:
    """源码/测试文件内容指纹（报告记录实测快照，便于复算与漂移审计）。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    """文件字节指纹（读失败时返回空串，不阻断报告生成）。"""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def _tail(text: str) -> str:
    """截取输出尾部（归因需要最后几行，完整 stdout 会让报告膨胀数十倍）。"""
    cleaned = text.strip()
    if len(cleaned) <= _OUTPUT_TAIL_CHARS:
        return cleaned
    return "…" + cleaned[-_OUTPUT_TAIL_CHARS:]


def _repo_relative(path_str: str, repo_root: Path = _REPO_ROOT) -> str:
    """把用户传入的路径规范化为仓库根相对路径（报告/沙箱内一律用它）。

    为什么不容许仓外路径：沙箱副本只包含仓库内文件，仓外路径无法映射；
    同时避免把 /tmp 等临时路径写进可复算报告。
    """
    raw = Path(path_str).expanduser()
    candidate = raw if raw.is_absolute() else (repo_root / raw)
    try:
        relative = candidate.resolve().relative_to(repo_root.resolve())
    except ValueError as e:
        raise SelfMutationError(f"路径不在仓库内，无法映射到沙箱副本: {path_str}") from e
    if not candidate.is_file():
        raise SelfMutationError(f"文件不存在: {path_str}")
    return relative.as_posix()


# ─── 变异生成与抽样 ──────────────────────────────────────────────────────────


def sample_mutants(mutants: Sequence[Mutant], cap: int) -> list[Mutant]:
    """按源码位置等距抽样（cap<=0 或不足上限时全量返回）。

    为什么等距而不是按类型轮转：项目既有 `MutationGenerator` 的轮转取样会
    把大类型（如 stmt_delete）压到与稀有类型同等少量，导致"类型覆盖看起来
    均匀、实际分数方差更大"；等距抽样保持变异体的源码空间分布与类型比例的
    近似无偏，且**完全确定性**（无随机种子，便于 before/after 复算）。
    排序键取 (行号, 类型, 描述)：同一源码 + 同一 cap 必然得到同一子集。
    """
    if cap <= 0 or len(mutants) <= cap:
        return list(mutants)
    ordered = sorted(mutants, key=lambda m: (m.line_no, m.mutant_type, m.description))
    if cap == 1:
        return [ordered[len(ordered) // 2]]
    step = (len(ordered) - 1) / (cap - 1)
    indices = sorted({round(i * step) for i in range(cap)})
    return [ordered[i] for i in indices]


def filter_generator_invalid_mutants(source: str, mutants: Sequence[Mutant]) -> tuple[list[Mutant], dict[str, int]]:
    """剔除"生成器无效"变异体，返回 (可执行变异体, {identity: n, syntax_error: n})。

    为什么必须剔除（2026-10-17 实测发现，两处均为**生成器缺陷**导致的假变异体）：

    1. **语义恒等（identity）**：``_generate_numeric_offset`` 会为 Compare 中的
       **非数值常量**（``None`` / ``"x"`` / ``True``）登记"const None → +1"变异体，
       但其 ``_offset_numeric`` 内部只处理 int/float，实际未改任何节点——
       ``ast.unparse`` 重排版后的代码与源码**AST 逐节点相同**（实测 env_utils /
       helpers / atomic_io 各 1 个）。这种变异体跑测试必然存活，若计入分母就是把
       生成器缺陷记成"本项目测试弱"，系统性压低分数。
    2. **语法非法（syntax_error）**：``_gen_subscript_negate`` 在 helpers.py:468
       附近产出的 5 个变异体 unparse 结果语法非法（``[-:...]``），根本不可执行；
       标准变异测试口径应在抽样前剔除（否则只是浪费样本额度并污染 invalid 计数）。

    过滤在**抽样前**完成，因此抽样率按可执行池（``executable_pool``）披露；
    被剔除数量逐模块记录在报告 ``generator_filtered`` 字段，不静默丢弃。
    """
    source_dump = ast.dump(ast.parse(source))
    kept: list[Mutant] = []
    identity = 0
    syntax_error = 0
    for mutant in mutants:
        try:
            tree = ast.parse(mutant.code)
        except SyntaxError:
            syntax_error += 1
            continue
        if ast.dump(tree) == source_dump:
            identity += 1
            continue
        kept.append(mutant)
    return kept, {"identity": identity, "syntax_error": syntax_error}


def _mutant_id(stem: str, mutant: Mutant) -> str:
    """稳定变异体 ID：模块 stem + 变异代码 sha256 前缀。

    不用"生成顺序下标"作 ID：`--max-mutants` 改变时下标会漂移，而代码哈希
    在源码不变时跨 run 恒定——before/after 报告、存活变异体击杀清单、
    归因表都能按同一 ID 对账。
    """
    digest = hashlib.sha256(mutant.code.encode("utf-8")).hexdigest()[:12]
    return f"{stem}:{digest}"


def _build_module_plan(
    module: str,
    *,
    max_mutants: int,
    generator: ExtendedMutationGenerator,
    repo_root: Path = _REPO_ROOT,
) -> tuple[ModulePlan, dict[str, str]]:
    """生成模块的变异计划（返回 plan 与其原始源码字节，供沙箱还原用）。"""
    path = repo_root / module
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as e:
        raise SelfMutationError(f"读取目标源码失败: {module} ({e})") from e
    all_mutants = generator.generate(source)
    executable, filtered = filter_generator_invalid_mutants(source, all_mutants)
    sampled = sample_mutants(executable, max_mutants)
    plan = ModulePlan(
        module=module,
        source_sha256=sha256_text(source),
        total_generated=len(all_mutants),
        test_files=(),  # 测试集合在解析 --test-map / 测试发现后填入
        mutants=tuple(sampled),
        filtered_identity=filtered["identity"],
        filtered_syntax_error=filtered["syntax_error"],
    )
    return plan, {module: source}


def _attach_test_files(plan: ModulePlan, test_files: Sequence[str]) -> ModulePlan:
    """把解析好的测试集合绑定到计划上（保持 frozen dataclass 的不可变性）。"""
    return ModulePlan(
        module=plan.module,
        source_sha256=plan.source_sha256,
        total_generated=plan.total_generated,
        test_files=tuple(test_files),
        mutants=plan.mutants,
        filtered_identity=plan.filtered_identity,
        filtered_syntax_error=plan.filtered_syntax_error,
    )


# ─── 测试集合解析 ────────────────────────────────────────────────────────────


def discover_test_files(module_rel: str, repo_root: Path = _REPO_ROOT) -> list[str]:
    """按项目命名惯例发现模块的专属测试（精确优先，其次前缀族）。

    规则：
    1. `tests/test_<module_stem>.py` 存在 → 只用它（精确约定最强）；
    2. 否则取 `tests/test_<module_stem>_*.py` 全族（如 helpers 的
       test_helpers_json_property / test_helpers_json_robustness）；
    3. 都没有 → 空列表（调用方报错并要求 --test-map，而不是瞎猜全会话套件：
       让"测试选择"显式可审计，避免把几十个文件拖进每个变异体）。
    """
    stem = Path(module_rel).stem
    tests_dir = repo_root / "tests"
    exact = tests_dir / f"test_{stem}.py"
    if exact.is_file():
        return [exact.relative_to(repo_root).as_posix()]
    family = sorted(tests_dir.glob(f"test_{stem}_*.py"))
    return [p.relative_to(repo_root).as_posix() for p in family if p.is_file()]


def parse_test_map(
    entries: Sequence[str], known_modules: Sequence[str], repo_root: Path = _REPO_ROOT
) -> dict[str, tuple[str, ...]]:
    """解析 `--test-map MODULE=test1.py,test2.py`（可重复）。

    存在意义：before/after 对比必须冻结同一测试集合，否则"分数提升"可能只是
    多挂了一个测试文件；击杀存活变异体时又必须把新测试文件追加进集合。
    显式映射让两次运行的测试集合都可审计。
    """
    known = set(known_modules)
    result: dict[str, tuple[str, ...]] = {}
    for entry in entries:
        module_raw, sep, tests_raw = entry.partition("=")
        if not sep:
            raise SelfMutationError(f"--test-map 格式应为 MODULE=test1,test2，收到: {entry}")
        module = _repo_relative(module_raw.strip(), repo_root)
        if module not in known:
            raise SelfMutationError(f"--test-map 指定的模块不在 --files 列表中: {module}")
        test_files = tuple(_repo_relative(t.strip(), repo_root) for t in tests_raw.split(",") if t.strip())
        if not test_files:
            raise SelfMutationError(f"--test-map 未指定任何测试文件: {entry}")
        result[module] = test_files
    return result


# ─── 命令构造与结果分类 ──────────────────────────────────────────────────────


def build_test_command(template: str, python: str, test_files: Sequence[str]) -> list[str]:
    """把命令模板渲染成 argv（`{python}` / `{test_files}` 两个占位符）。

    实现细节：先 `shlex.split` 再按 token 展开，而不是先 format 再 split——
    解释器/仓库路径可能含空格，先 split 才能把 `{python}` 当成一个原子参数；
    `{test_files}` 展开为多个 argv 元素，天然规避 shell 注入面（本工具不经过
    shell）。
    """
    if "{test_files}" not in template:
        raise SelfMutationError("--test-command 必须包含 {test_files} 占位符")
    argv: list[str] = []
    for token in shlex.split(template):
        if token == "{python}":
            argv.append(python)
        elif token == "{test_files}":
            argv.extend(test_files)
        else:
            try:
                argv.append(token.format(python=python, test_files=" ".join(test_files)))
            except KeyError as e:
                raise SelfMutationError(f"--test-command 含未知占位符: {e}") from e
    if not argv:
        raise SelfMutationError("--test-command 渲染结果为空")
    return argv


def classify_result(returncode: int | None, timed_out: bool) -> tuple[str, str]:
    """按 pytest 官方退出码与超时标记分类，返回 (outcome, reason)。

    口径（与模块 docstring 第 4 条一致）：rc==1 kill、rc==0 survive、
    其余与超时一律 invalid（不进 mutation score 分母）；超时单独成类以便
    归因"测试是否会被变异体拖死"。
    """
    if timed_out:
        return OUTCOME_TIMEOUT, "超时：已 killpg 整树终止（单独记 invalid，不进分母）"
    if returncode is None:
        return OUTCOME_INVALID, "no_returncode"
    if returncode == 0:
        return OUTCOME_SURVIVED, ""
    if returncode == 1:
        return OUTCOME_KILLED, ""
    reason = _PYTEST_EXIT_REASONS.get(returncode, f"unexpected_exit(rc={returncode})")
    if returncode < 0:
        reason = f"terminated_by_signal(rc={returncode})"
    return OUTCOME_INVALID, reason


# ─── 临时沙箱（绝不触碰工作树） ──────────────────────────────────────────────

#: 复制副本时需要剔除的非源码产物（.pyc/缓存复制过去只会制造陈旧字节码风险）
_SANDBOX_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", ".mypy_cache")

#: 宿主 pytest 会话残留键：本工具若在 pytest 用例内被调用，这些键会泄漏进
#: 嵌套 pytest，让被测行为依赖"是谁启动了它"（CI 用 xdist -n4，worker 身份
#: 变量同样不应跨层传播）
_HOST_SESSION_ENV_KEYS: tuple[str, ...] = (
    "PYTEST_CURRENT_TEST",
    "PYTEST_XDIST_WORKER",
    "PYTEST_XDIST_WORKER_COUNT",
)


class Sandbox:
    """一个 worker 独占的仓库临时副本（变异只发生在副本内）。"""

    def __init__(
        self,
        root: Path,
        module_bytes: dict[str, bytes],
        *,
        label: str = "worker",
    ) -> None:
        self.root = root
        self.label = label
        self._module_bytes = dict(module_bytes)
        # 子环境：nested_pytest_env 先剔除宿主 PYTEST_PLUGINS/PYTEST_ADDOPTS，
        # 再显式固定影响确定性的键（hash 种子/字节码/LLM 缓存）。
        env = {
            key: value
            for key, value in nested_pytest_env().items()
            if key not in _HOST_SESSION_ENV_KEYS and not key.startswith("COV_CORE_")
        }
        env.update(
            {
                "PYTHONPATH": str(root),
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONHASHSEED": "0",
                "AITESTER_LLM_CACHE": "0",
            }
        )
        self.env: dict[str, str] = env

    @classmethod
    def create(
        cls,
        root: Path,
        repo_root: Path,
        *,
        module_paths: Sequence[str],
        test_files: Sequence[str],
        label: str = "worker",
    ) -> Sandbox:
        """建立完整副本：src/ 全树 + config.py + pyproject.toml + conftest + 目标测试。"""
        root.mkdir(parents=True, exist_ok=True)
        shutil.copytree(repo_root / "src", root / "src", ignore=_SANDBOX_IGNORE)
        shutil.copy2(repo_root / "config.py", root / "config.py")
        # pyproject.toml 决定 pytest rootdir/ini；复制但不改写——命令模板已用
        # `-o addopts=` 清空宿主口径，副本保持"与工作树同字节"便于审计。
        shutil.copy2(repo_root / "pyproject.toml", root / "pyproject.toml")
        tests_dir = root / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)
        conftest = repo_root / "tests" / "conftest.py"
        if conftest.is_file():
            shutil.copy2(conftest, tests_dir / "conftest.py")
        # tests/ 是包（有 __init__.py），副本必须一并复制，否则 pytest 以
        # tests.test_x 导入时会因缺包初始化而收集失败（rc=2 全 invalid）。
        tests_init = repo_root / "tests" / "__init__.py"
        if tests_init.is_file():
            shutil.copy2(tests_init, tests_dir / "__init__.py")
        for test_rel in test_files:
            destination = root / test_rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(repo_root / test_rel, destination)
        module_bytes = {module: (repo_root / module).read_bytes() for module in module_paths}
        return cls(root, module_bytes, label=label)

    def apply_mutant(self, module_rel: str, code: str) -> None:
        """把变异体写入副本中的目标模块文件（仅副本）。"""
        target = self.root / module_rel
        target.write_text(code, encoding="utf-8")

    def restore_module(self, module_rel: str) -> None:
        """用内存中的原始字节还原模块（每个变异体运行后必须调用）。"""
        target = self.root / module_rel
        target.write_bytes(self._module_bytes[module_rel])

    def run_tests(self, test_files: Sequence[str], command_template: str, timeout: float) -> Any:
        """在副本内运行一次 slim pytest，返回 run_with_timeout 的 CompletedProcess。"""
        command = build_test_command(command_template, sys.executable, test_files)
        return run_with_timeout(
            command,
            timeout=timeout,
            cwd=str(self.root),
            env=self.env,
            logger_name=f"self_mutation_{self.label}",
        )

    def close(self) -> None:
        """删除副本目录（失败不阻断：临时目录残留比测量失败影响小）。"""
        shutil.rmtree(self.root, ignore_errors=True)


class SandboxPool:
    """按线程惰性分配 Sandbox（每个并发 worker 独占一份副本，互不干扰）。"""

    def __init__(
        self,
        base_dir: Path,
        repo_root: Path,
        *,
        module_paths: Sequence[str],
        test_files: Sequence[str],
    ) -> None:
        self._base_dir = base_dir
        self._repo_root = repo_root
        self._module_paths = tuple(module_paths)
        self._test_files = tuple(test_files)
        self._local = threading.local()
        self._lock = threading.Lock()
        self._created: list[Sandbox] = []
        # 序号必须在锁内分配并自增：两个 worker 线程可能同时首次调用 get()，
        # 若用 len(_created) 推导序号会拿到同一个 index、争抢同一副本目录
        # （实测 FileExistsError: worker-0/src 已存在——首次冒烟即命中）。
        self._worker_seq = 0

    def get(self) -> Sandbox:
        """取当前线程的沙箱（首次调用时创建并登记，退出时统一清理）。"""
        sandbox: Sandbox | None = getattr(self._local, "sandbox", None)
        if sandbox is not None:
            return sandbox
        with self._lock:
            index = self._worker_seq
            self._worker_seq += 1
        root = self._base_dir / f"{self.label_prefix}-{index}"
        sandbox = Sandbox.create(
            root,
            self._repo_root,
            module_paths=self._module_paths,
            test_files=self._test_files,
            label=root.name,
        )
        with self._lock:
            self._created.append(sandbox)
        self._local.sandbox = sandbox
        return sandbox

    #: 副本目录前缀（与 worker 序号拼成可读标签，便于 --keep-sandbox 排查）
    label_prefix = "worker"

    def close_all(self) -> None:
        """关闭所有已创建的沙箱。"""
        with self._lock:
            sandboxes = list(self._created)
            self._created.clear()
        for sandbox in sandboxes:
            sandbox.close()


# ─── 单变异体执行 ────────────────────────────────────────────────────────────


def _run_single_mutant(
    sandbox: Sandbox,
    module_rel: str,
    mutant: Mutant,
    *,
    test_files: Sequence[str],
    command_template: str,
    timeout: float,
) -> MutantOutcome:
    """在沙箱中执行"写变异体 → 跑 slim 测试 → 还原"的完整闭环。"""
    stem = Path(module_rel).stem
    mutant_id = _mutant_id(stem, mutant)
    code_sha = hashlib.sha256(mutant.code.encode("utf-8")).hexdigest()[:16]
    sandbox.apply_mutant(module_rel, mutant.code)
    started = time.perf_counter()
    try:
        proc = sandbox.run_tests(test_files, command_template, timeout)
    finally:
        # 无论子进程异常/超时/被中断，都必须还原，否则后续变异体会被污染
        sandbox.restore_module(module_rel)
    duration = time.perf_counter() - started
    timed_out = bool(getattr(proc, "timed_out", False))
    returncode = getattr(proc, "returncode", None)
    outcome, reason = classify_result(returncode, timed_out)
    output_tail = ""
    if outcome in (OUTCOME_INVALID, OUTCOME_TIMEOUT):
        output_tail = _tail(f"{getattr(proc, 'stdout', '')}\n{getattr(proc, 'stderr', '')}")
    return MutantOutcome(
        mutant_id=mutant_id,
        module=module_rel,
        mutant_type=mutant.mutant_type,
        line_no=mutant.line_no,
        description=mutant.description,
        code_sha256=code_sha,
        outcome=outcome,
        returncode=returncode,
        duration_s=duration,
        reason=reason,
        output_tail=output_tail,
    )


def _execute_mutants(
    tasks: Sequence[tuple[str, Mutant]],
    *,
    test_files_by_module: dict[str, tuple[str, ...]],
    sandbox_pool: SandboxPool,
    command_template: str,
    timeout: float,
    workers: int,
    verbose: bool,
    quiet: bool,
) -> list[MutantOutcome]:
    """并行执行全部变异体（线程池；子进程工作释放 GIL，线程足够）。"""
    if not tasks:
        return []
    total = len(tasks)
    step = max(1, total // 10)
    counter = {"done": 0}
    lock = threading.Lock()

    def work(task: tuple[str, Mutant]) -> MutantOutcome:
        module_rel, mutant = task
        sandbox = sandbox_pool.get()
        record = _run_single_mutant(
            sandbox,
            module_rel,
            mutant,
            test_files=test_files_by_module[module_rel],
            command_template=command_template,
            timeout=timeout,
        )
        with lock:
            counter["done"] += 1
            done = counter["done"]
        if verbose:
            print(
                f"[{done}/{total}] {record.outcome:<8} {record.mutant_id} "
                f"{module_rel}:{record.line_no} {record.mutant_type} ({record.duration_s:.2f}s)"
                + (f" reason={record.reason}" if record.reason else ""),
                flush=True,
            )
        elif not quiet and (done % step == 0 or done == total):
            print(f"[self-mutation] 进度 {done}/{total}", flush=True)
        return record

    with ThreadPoolExecutor(max_workers=workers) as executor:
        return list(executor.map(work, tasks))


# ─── green baseline 前置校验 ─────────────────────────────────────────────────


def _run_preflight(
    plans: Sequence[ModulePlan],
    *,
    sandbox_base: Path,
    repo_root: Path,
    command_template: str,
    timeout: float,
    allow_red_baseline: bool,
    quiet: bool,
) -> dict[str, dict[str, Any]]:
    """在副本上跑未变异测试，确认套件本身是绿的（测量有效性前提）。

    返回 {module: {green, returncode, duration_s, reason, output_tail}}。
    baseline 不绿且未显式放行 → 抛 SelfMutationError（退出码 2），
    避免把"既有失败"全部计成"杀死变异体"的虚高分数。
    """
    reports: dict[str, dict[str, Any]] = {}
    all_tests = sorted({test for plan in plans for test in plan.test_files})
    all_modules = [plan.module for plan in plans]
    sandbox = Sandbox.create(
        sandbox_base / "preflight",
        repo_root,
        module_paths=all_modules,
        test_files=all_tests,
        label="preflight",
    )
    try:
        for plan in plans:
            started = time.perf_counter()
            proc = sandbox.run_tests(plan.test_files, command_template, timeout)
            duration = time.perf_counter() - started
            timed_out = bool(getattr(proc, "timed_out", False))
            returncode = getattr(proc, "returncode", None)
            green = returncode == 0 and not timed_out
            report = {
                "green": green,
                "returncode": returncode,
                "duration_s": round(duration, 3),
                "timed_out": timed_out,
                "reason": "" if green else "baseline_not_green",
                "output_tail": "" if green else _tail(f"{getattr(proc, 'stdout', '')}\n{getattr(proc, 'stderr', '')}"),
            }
            reports[plan.module] = report
            status = "GREEN" if green else "RED"
            if not quiet:
                print(f"[self-mutation] baseline {status}: {plan.module} ({duration:.2f}s)", flush=True)
            if not green and not allow_red_baseline:
                raise SelfMutationError(
                    "未变异副本上的测试未通过（baseline 非绿），本次测量无效。"
                    f" 模块={plan.module} rc={returncode} timed_out={timed_out}。"
                    f" 输出尾部:\n{report['output_tail']}\n"
                    " 处理方式：先修绿该测试集合；确需在红基线上继续请显式传 --allow-red-baseline"
                    "（报告会标记 measurement_valid=false）。"
                )
    finally:
        sandbox.close()
    return reports


# ─── 汇总与报告 ──────────────────────────────────────────────────────────────


def _summarize_records(records: Sequence[MutantOutcome]) -> dict[str, Any]:
    """统计 killed/survived/invalid/timeout 与 mutation score 点估计。

    mutation score = killed / (killed + survived)；invalid/timeout 单列且
    不进分母（见模块 docstring 口径 4）。
    """
    counts: Counter[str] = Counter(record.outcome for record in records)
    killed = counts[OUTCOME_KILLED]
    survived = counts[OUTCOME_SURVIVED]
    invalid = counts[OUTCOME_INVALID]
    timeout = counts[OUTCOME_TIMEOUT]
    not_run = counts[OUTCOME_NOT_RUN]
    denominator = killed + survived
    score = (killed / denominator) if denominator else None
    return {
        "total": len(records),
        "killed": killed,
        "survived": survived,
        "invalid": invalid,
        "timeout": timeout,
        "not_run": not_run,
        "valid_denominator": denominator,
        "mutation_score": score,
    }


def _summarize_by_type(records: Sequence[MutantOutcome]) -> dict[str, dict[str, Any]]:
    """按变异算子类型汇总（暴露"哪类算子总能被杀死/总是存活"的结构信息）。"""
    grouped: dict[str, list[MutantOutcome]] = {}
    for record in records:
        grouped.setdefault(record.mutant_type, []).append(record)
    return {mutant_type: _summarize_records(group) for mutant_type, group in sorted(grouped.items())}


def summarize_module(
    plan: ModulePlan,
    records: Sequence[MutantOutcome],
    baseline: dict[str, Any] | None,
) -> dict[str, Any]:
    """单个模块的报告条目（测试集合快照 + 基线 + 计数 + 逐变异体记录）。"""
    summary = _summarize_records(records)
    return {
        "module": plan.module,
        "source_sha256": plan.source_sha256,
        "test_files": list(plan.test_files),
        "test_files_sha256": {test: _sha256_file(_REPO_ROOT / test) for test in plan.test_files},
        "baseline": baseline or {},
        "total_generated_mutants": plan.total_generated,
        "generator_filtered": {
            "identity": plan.filtered_identity,
            "syntax_error": plan.filtered_syntax_error,
        },
        "executable_pool": plan.executable_pool,
        "sampled_mutants": plan.sampled,
        "samples": {
            "killed": summary["killed"],
            "survived": summary["survived"],
            "invalid": summary["invalid"],
            "timeout": summary["timeout"],
            "not_run": summary["not_run"],
        },
        "mutation_score": summary["mutation_score"],
        "by_type": _summarize_by_type(records),
        "mutants": [record.to_dict() for record in records],
    }


def build_report(
    *,
    module_reports: Sequence[dict[str, Any]],
    plans: Sequence[ModulePlan],
    config: dict[str, Any],
    environment: dict[str, Any],
    git: dict[str, Any],
    mode: str,
    duration_s: float,
    generated_at: str,
) -> dict[str, Any]:
    """组装完整报告（JSON schema 的唯一构造点，单测直接锁 schema）。

    汇总层与逐模块层都用同一 `_summarize_records` 口径，保证
    "总分数"可手工由逐模块 killed/survived 复算出来（不引入第二套算法）。
    """
    all_records: list[MutantOutcome] = []
    for module_report in module_reports:
        all_records.extend(
            MutantOutcome(
                mutant_id=mutant["mutant_id"],
                module=mutant["module"],
                mutant_type=mutant["mutant_type"],
                line_no=mutant["line_no"],
                description=mutant["description"],
                code_sha256=mutant["code_sha256"],
                outcome=mutant["outcome"],
                returncode=mutant["returncode"],
                duration_s=mutant["duration_s"],
                reason=mutant["reason"],
            )
            for mutant in module_report["mutants"]
        )
    totals = _summarize_records(all_records)
    baseline_green = all(report.get("baseline", {}).get("green", False) for report in module_reports)
    return {
        "schema_version": _SCHEMA_VERSION,
        "tool": "scripts/tools/self_mutation.py",
        "mode": mode,
        "generated_at": generated_at,
        "duration_seconds": round(duration_s, 3),
        "environment": environment,
        "git": git,
        "config": config,
        "summary": {
            "modules": len(module_reports),
            "total_generated_mutants": sum(plan.total_generated for plan in plans),
            "generator_filtered_identity": sum(plan.filtered_identity for plan in plans),
            "generator_filtered_syntax_error": sum(plan.filtered_syntax_error for plan in plans),
            "executable_pool": sum(plan.executable_pool for plan in plans),
            "sampled_mutants": totals["total"],
            "killed": totals["killed"],
            "survived": totals["survived"],
            "invalid": totals["invalid"],
            "timeout": totals["timeout"],
            "not_run": totals["not_run"],
            "valid_denominator": totals["valid_denominator"],
            "mutation_score": totals["mutation_score"],
            "baseline_green": baseline_green,
            "measurement_valid": baseline_green or bool(config.get("allow_red_baseline")),
        },
        "modules": list(module_reports),
    }


# ─── 报告渲染 ────────────────────────────────────────────────────────────────


def _fmt_score(score: float | None) -> str:
    """分数展示口径：点估计保留 4 位小数，无效样本显示 n/a（不填 0 误导）。"""
    return "n/a" if score is None else f"{score:.4f}"


def render_markdown(report: dict[str, Any]) -> str:
    """把报告 dict 渲染为中文 Markdown（人读版；JSON 是机器可读事实源）。"""
    config = report["config"]
    environment = report["environment"]
    git = report["git"]
    summary = report["summary"]
    lines: list[str] = []
    lines.append("# 自身测试套件变异测试报告（self-mutation）")
    lines.append("")
    lines.append("> 机器可读事实源为同名 JSON；本文件是其可读镜像。所有数字由")
    lines.append("> `scripts/tools/self_mutation.py` 实测产出，复现命令见文末。")
    lines.append("")
    lines.append("## 测量口径")
    lines.append("")
    lines.append("- mutation score = killed / (killed + survived)；invalid/timeout **不进分母**。")
    lines.append("- rc 分类：rc==1 killed、rc==0 survived、rc==2/3/4/5 或超时 invalid。")
    lines.append("- 变异在 tempfile 临时副本中进行，工作树零改动；子进程 pytest 经")
    lines.append("  `nested_pytest_env` 隔离宿主配置、经 `run_with_timeout` 整树超时终止。")
    lines.append("- 基线（未变异副本）执行结果单列于各模块 `baseline`，红基线默认阻断。")
    lines.append(
        "- 抽样前先剔除**生成器无效**变异体：语义恒等（identity，与源码 AST 逐节点相同）与"
        "语法非法（syntax_error）——前者计入分母会把生成器缺陷误判成测试弱，后者不可执行。"
        "剔除数量逐模块披露于 `generator_filtered`；抽样率按可执行池披露。"
    )
    lines.append("")
    lines.append("## 运行环境")
    lines.append("")
    lines.append(
        f"- 生成时间：{report['generated_at']}；总耗时：{report['duration_seconds']}s；模式：`{report['mode']}`"
    )
    lines.append(
        f"- 主机：{environment.get('hostname')} / {environment.get('platform')} / CPU {environment.get('cpu_count')} 核"
    )
    lines.append(
        f"- Python：{environment.get('python_version')}（{environment.get('python_executable')}）；pytest：{environment.get('pytest_version')}"
    )
    lines.append(f"- git：sha=`{git.get('sha')}`，dirty={git.get('dirty')}（{git.get('dirty_files')} 个未提交变更）")
    lines.append(
        f"- worker：{config.get('workers')}；每变异体超时：{config.get('timeout_per_mutant_seconds')}s；"
        f"每文件变异体上限：{config.get('max_mutants_per_file')}（0=全量）"
    )
    lines.append(f"- 测试命令模板：`{config.get('test_command_template')}`；样本量口径：{config.get('sampling')}")
    lines.append("")
    lines.append("## 总览")
    lines.append("")
    lines.append(
        "| 模块 | 生成 | 过滤(恒等/语法) | 可执行池 | 抽样执行 | killed | survived | invalid | timeout "
        "| mutation score |"
    )
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for module_report in report["modules"]:
        samples = module_report["samples"]
        filtered = module_report["generator_filtered"]
        lines.append(
            f"| `{module_report['module']}` | {module_report['total_generated_mutants']} | "
            f"{filtered['identity']}/{filtered['syntax_error']} | {module_report['executable_pool']} | "
            f"{module_report['sampled_mutants']} | {samples['killed']} | {samples['survived']} | "
            f"{samples['invalid']} | {samples['timeout']} | {_fmt_score(module_report['mutation_score'])} |"
        )
    lines.append(
        f"| **合计** | {summary['total_generated_mutants']} | "
        f"{summary['generator_filtered_identity']}/{summary['generator_filtered_syntax_error']} | "
        f"{summary['executable_pool']} | {summary['sampled_mutants']} | "
        f"{summary['killed']} | {summary['survived']} | {summary['invalid']} | "
        f"{summary['timeout']} | **{_fmt_score(summary['mutation_score'])}** |"
    )
    lines.append("")
    lines.append(
        f"- 测量有效性：baseline_green={summary['baseline_green']}，"
        f"measurement_valid={summary['measurement_valid']}；有效分母（killed+survived）={summary['valid_denominator']}"
    )
    lines.append("")
    lines.append("## 分模块明细")
    lines.append("")
    for module_report in report["modules"]:
        lines.append(f"### `{module_report['module']}`")
        lines.append("")
        lines.append(
            f"- 源码 sha256：`{module_report['source_sha256'][:16]}…`（{len(module_report['source_sha256'])} 位）"
        )
        lines.append(f"- 测试集合：{', '.join(f'`{test}`' for test in module_report['test_files'])}")
        baseline = module_report["baseline"]
        lines.append(
            f"- 基线（未变异）：green={baseline.get('green')}，rc={baseline.get('returncode')}，"
            f"{baseline.get('duration_s')}s"
        )
        filtered = module_report["generator_filtered"]
        lines.append(
            f"- 生成 {module_report['total_generated_mutants']}，其中生成器无效被剔除 "
            f"{filtered['identity']} 个恒等 + {filtered['syntax_error']} 个语法非法；"
            f"可执行池 {module_report['executable_pool']}，抽样执行 {module_report['sampled_mutants']}，"
            f"mutation score = **{_fmt_score(module_report['mutation_score'])}**"
        )
        lines.append("")
        lines.append("| 变异类型 | killed | survived | invalid | timeout | score |")
        lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")
        for mutant_type, type_summary in module_report["by_type"].items():
            lines.append(
                f"| {mutant_type} | {type_summary['killed']} | {type_summary['survived']} | "
                f"{type_summary['invalid']} | {type_summary['timeout']} | {_fmt_score(type_summary['mutation_score'])} |"
            )
        lines.append("")
        survivors = [m for m in module_report["mutants"] if m["outcome"] == "survived"]
        if survivors:
            lines.append(f"**存活变异体（{len(survivors)} 个，待击杀/归因）**：")
            lines.append("")
            lines.append("| mutant_id | 行号 | 类型 | 描述 |")
            lines.append("| --- | ---: | --- | --- |")
            lines.extend(
                f"| `{survivor['mutant_id']}` | {survivor['line_no']} | {survivor['mutant_type']} | "
                f"{survivor['description']} |"
                for survivor in survivors
            )
            lines.append("")
        invalid_records = [m for m in module_report["mutants"] if m["outcome"] in ("invalid", "timeout")]
        if invalid_records:
            lines.append(f"**invalid / timeout（{len(invalid_records)} 个，不进分母）**：")
            lines.append("")
            lines.append("| mutant_id | 行号 | 结果 | 原因 |")
            lines.append("| --- | ---: | --- | --- |")
            lines.extend(
                f"| `{record['mutant_id']}` | {record['line_no']} | {record['outcome']} | {record['reason']} |"
                for record in invalid_records
            )
            lines.append("")
    lines.append("## 复现命令")
    lines.append("")
    lines.append("```bash")
    lines.append(config.get("command", ""))
    lines.append("```")
    lines.append("")
    lines.append(
        "报告落点与测试文件/源码的 sha256 已记录在 JSON 中；同一工作树下重跑应得到相同的"
        "变异体集合与（在确定性测试前提下）相同的计数。"
    )
    lines.append("")
    return "\n".join(lines)


def write_reports(report: dict[str, Any], json_out: Path, md_out: Path) -> None:
    """落盘 JSON + Markdown 报告（父目录自动创建）。"""
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    md_out.parent.mkdir(parents=True, exist_ok=True)
    md_out.write_text(render_markdown(report), encoding="utf-8")


# ─── 环境快照 ────────────────────────────────────────────────────────────────


def environment_snapshot() -> dict[str, Any]:
    """记录主机/Python/pytest 版本（报告的"可复算前提"字段）。"""
    pytest_version: str | None
    try:
        from importlib.metadata import version

        pytest_version = version("pytest")
    except Exception:  # pragma: no cover - 仅环境异常路径
        pytest_version = None
    return {
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "python_executable": sys.executable,
        "pytest_version": pytest_version,
    }


def git_state(repo_root: Path = _REPO_ROOT) -> dict[str, Any]:
    """记录 git sha 与工作树脏文件数（不阻断：脏树是本地开发的常态）。"""
    state: dict[str, Any] = {"sha": None, "dirty": None, "dirty_files": None}
    try:
        head = run_with_timeout(["git", "rev-parse", "HEAD"], timeout=10, cwd=str(repo_root))
        if head.returncode == 0:
            state["sha"] = head.stdout.strip()
        status = run_with_timeout(["git", "status", "--porcelain"], timeout=10, cwd=str(repo_root))
        if status.returncode == 0:
            lines = [line for line in status.stdout.splitlines() if line.strip()]
            state["dirty"] = bool(lines)
            state["dirty_files"] = len(lines)
    except OSError as e:  # pragma: no cover - git 缺失环境
        state["sha"] = None
        state["error"] = str(e)
    return state


# ─── CLI ─────────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    """构造 CLI（所有参数的中文 help 即口径文档；互斥组见 verbose/fail_under）。"""
    parser = argparse.ArgumentParser(
        prog="self_mutation",
        description="项目自身测试套件的变异测试驱动器（零 LLM / 零网络；变异只发生在临时副本）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--files",
        default=",".join(DEFAULT_MODULES),
        help="逗号分隔的目标源码文件（仓库根相对路径）",
    )
    parser.add_argument(
        "--max-mutants",
        type=int,
        default=120,
        help="每个文件最多执行的变异体数（按源码位置等距抽样；0=全量）",
    )
    parser.add_argument("--workers", type=int, default=2, help="并行 worker 数（每个 worker 一份独立副本）")
    parser.add_argument(
        "--timeout-per-mutant",
        type=float,
        default=60.0,
        help="单个变异体测试的超时秒数（超时 killpg 整树终止并记 timeout/invalid）",
    )
    parser.add_argument("--test-command", default=DEFAULT_TEST_COMMAND, help="测试命令模板（必须含 {test_files}）")
    parser.add_argument(
        "--test-map",
        action="append",
        default=[],
        metavar="MODULE=tests/a.py,tests/b.py",
        help="冻结指定模块的测试集合（可重复；用于 before/after 可比性与击杀测试追加）",
    )
    parser.add_argument("--json-out", default=str(DEFAULT_JSON_OUT), help="JSON 报告输出路径")
    parser.add_argument("--md-out", default=str(DEFAULT_MD_OUT), help="Markdown 报告输出路径")
    parser.add_argument(
        "--allow-red-baseline",
        action="store_true",
        help="baseline 非绿时仍继续（报告标记 measurement_valid=false，分数不可作结论）",
    )
    parser.add_argument("--keep-sandbox", action="store_true", help="保留 tempfile 沙箱目录（调试用）")
    verbosity = parser.add_mutually_exclusive_group()
    verbosity.add_argument("-v", "--verbose", action="store_true", help="逐变异体打印执行结果")
    verbosity.add_argument("-q", "--quiet", action="store_true", help="只打印最终汇总（错误仍输出 stderr）")
    execution = parser.add_mutually_exclusive_group()
    execution.add_argument("--dry-run", action="store_true", help="只生成变异体清单与报告，不执行子进程")
    execution.add_argument(
        "--fail-under",
        type=float,
        default=None,
        metavar="SCORE",
        help="mutation score 低于该阈值时退出码 1（CI 口径；与 --dry-run 互斥）",
    )
    return parser


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """解析并做跨参数校验（校验失败统一 argparse error → 退出码 2）。"""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.max_mutants < 0:
        parser.error("--max-mutants 必须 >= 0（0 表示全量）")
    if not 1 <= args.workers <= 8:
        parser.error("--workers 必须在 1..8（超过 8 对单机变异测试无收益且耗尽 CPU）")
    if args.timeout_per_mutant <= 0:
        parser.error("--timeout-per-mutant 必须 > 0")
    if args.fail_under is not None and not 0.0 <= args.fail_under <= 1.0:
        parser.error("--fail-under 必须在 [0, 1]")
    if args.fail_under is not None and args.dry_run:
        parser.error("--fail-under 与 --dry-run 互斥（dry-run 无实测分数）")
    if "{test_files}" not in args.test_command:
        parser.error("--test-command 必须包含 {test_files} 占位符")
    if not args.files.strip():
        parser.error("--files 不能为空")
    return args


def _resolve_output_path(path_str: str) -> Path:
    """输出路径解析：相对路径按**调用方 cwd** 解析（CLI 惯例），绝对路径原样。"""
    return Path(path_str).expanduser()


def _prepare_plans(args: argparse.Namespace) -> tuple[list[ModulePlan], dict[str, str]]:
    """把 CLI 输入变成可执行的模块计划（含测试集合发现与 --test-map 覆盖）。"""
    files = [_repo_relative(part.strip()) for part in args.files.split(",") if part.strip()]
    if not files:
        raise SelfMutationError("--files 解析后为空")
    test_map = parse_test_map(args.test_map, files)
    generator = ExtendedMutationGenerator(max_per_task=_GENERATOR_MAX_PER_TASK)
    plans: list[ModulePlan] = []
    source_map: dict[str, str] = {}
    for module in files:
        plan, source = _build_module_plan(module, max_mutants=args.max_mutants, generator=generator)
        source_map.update(source)
        test_files = test_map.get(module) or discover_test_files(module)
        if not test_files:
            raise SelfMutationError(
                f"未发现 {module} 的专属测试（tests/test_{Path(module).stem}.py 或 test_{Path(module).stem}_*.py），"
                "请用 --test-map 显式指定测试文件"
            )
        plans.append(_attach_test_files(plan, test_files))
    return plans, source_map


def _build_command_line(argv: Sequence[str]) -> str:
    """重建可复制的完整命令（报告"复现命令"字段，直接贴终端即可重跑）。"""
    parts = [shlex.quote(sys.executable), "scripts/tools/self_mutation.py"]
    parts.extend(shlex.quote(str(token)) for token in argv)
    return " ".join(parts)


def _dry_run_records(plans: Sequence[ModulePlan]) -> list[MutantOutcome]:
    """dry-run 模式：只登记变异体清单（outcome=not_run，零子进程）。"""
    records: list[MutantOutcome] = []
    for plan in plans:
        stem = Path(plan.module).stem
        records.extend(
            MutantOutcome(
                mutant_id=_mutant_id(stem, mutant),
                module=plan.module,
                mutant_type=mutant.mutant_type,
                line_no=mutant.line_no,
                description=mutant.description,
                code_sha256=hashlib.sha256(mutant.code.encode("utf-8")).hexdigest()[:16],
                outcome=OUTCOME_NOT_RUN,
            )
            for mutant in plan.mutants
        )
    return records


def _config_snapshot(
    args: argparse.Namespace, argv: Sequence[str], test_map: dict[str, tuple[str, ...]]
) -> dict[str, Any]:
    """报告 config 段：把本次运行的可变口径固定下来（复算/审计入口）。"""
    return {
        "files": [part.strip() for part in args.files.split(",") if part.strip()],
        "workers": args.workers,
        "timeout_per_mutant_seconds": args.timeout_per_mutant,
        "max_mutants_per_file": args.max_mutants,
        "sampling": "等距抽样（按源码行号+变异类型排序；0=全量）",
        "test_command_template": args.test_command,
        "test_map": {module: list(tests) for module, tests in test_map.items()},
        "generator": "experiments.mutation_testing.ExtendedMutationGenerator",
        "generator_max_per_task": _GENERATOR_MAX_PER_TASK,
        "allow_red_baseline": bool(args.allow_red_baseline),
        "command": _build_command_line(argv),
    }


def _print_summary(report: dict[str, Any]) -> None:
    """终端最终汇总（CI 日志里一眼看到分数与分母）。"""
    summary = report["summary"]
    print(flush=True)
    print("[self-mutation] 完成：", flush=True)
    for module_report in report["modules"]:
        samples = module_report["samples"]
        print(
            f"  - {module_report['module']}: killed={samples['killed']} survived={samples['survived']} "
            f"invalid={samples['invalid']} timeout={samples['timeout']} "
            f"score={_fmt_score(module_report['mutation_score'])} "
            f"({module_report['sampled_mutants']}/{module_report['total_generated_mutants']} 抽样)",
            flush=True,
        )
    print(
        f"  合计: killed={summary['killed']} survived={summary['survived']} invalid={summary['invalid']} "
        f"timeout={summary['timeout']} score={_fmt_score(summary['mutation_score'])}",
        flush=True,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """CLI 入口：准备计划 → baseline → 并行执行 → 报告落盘 → 阈值判定。"""
    raw_argv: list[str] = list(sys.argv[1:] if argv is None else argv)
    args = _parse_args(raw_argv)
    mode = "dry_run" if args.dry_run else "execute"
    started = time.perf_counter()
    generated_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    sandbox_base: Path | None = None
    try:
        plans, source_map = _prepare_plans(args)
        test_map = parse_test_map(args.test_map, [plan.module for plan in plans])
        all_tests = sorted({test for plan in plans for test in plan.test_files})
        environment = environment_snapshot()
        git = git_state()
        config = _config_snapshot(args, raw_argv, test_map)
        if not args.quiet:
            print(
                f"[self-mutation] 模块数={len(plans)} 生成变异体={sum(p.total_generated for p in plans)} "
                f"抽样执行={sum(p.sampled for p in plans)} workers={args.workers} mode={mode}",
                flush=True,
            )
        preflight: dict[str, dict[str, Any]] = {}
        if args.dry_run:
            records = _dry_run_records(plans)
            for plan in plans:
                preflight[plan.module] = {"green": None, "returncode": None, "duration_s": 0.0}
        else:
            sandbox_base = Path(tempfile.mkdtemp(prefix="aitester_self_mutation_"))
            preflight = _run_preflight(
                plans,
                sandbox_base=sandbox_base,
                repo_root=_REPO_ROOT,
                command_template=args.test_command,
                timeout=args.timeout_per_mutant,
                allow_red_baseline=args.allow_red_baseline,
                quiet=args.quiet,
            )
            sandbox_pool = SandboxPool(
                sandbox_base,
                _REPO_ROOT,
                module_paths=list(source_map),
                test_files=all_tests,
            )
            tasks: list[tuple[str, Mutant]] = [(plan.module, mutant) for plan in plans for mutant in plan.mutants]
            try:
                records = _execute_mutants(
                    tasks,
                    test_files_by_module={plan.module: plan.test_files for plan in plans},
                    sandbox_pool=sandbox_pool,
                    command_template=args.test_command,
                    timeout=args.timeout_per_mutant,
                    workers=args.workers,
                    verbose=args.verbose,
                    quiet=args.quiet,
                )
            finally:
                sandbox_pool.close_all()

        module_reports = []
        cursor = 0
        for plan in plans:
            module_records = records[cursor : cursor + plan.sampled]
            cursor += plan.sampled
            module_reports.append(summarize_module(plan, module_records, preflight.get(plan.module)))
        duration = time.perf_counter() - started
        report = build_report(
            module_reports=module_reports,
            plans=plans,
            config=config,
            environment=environment,
            git=git,
            mode=mode,
            duration_s=duration,
            generated_at=generated_at,
        )
        json_out = _resolve_output_path(args.json_out)
        md_out = _resolve_output_path(args.md_out)
        write_reports(report, json_out, md_out)
        if not args.quiet:
            _print_summary(report)
            print(f"[self-mutation] 报告：{json_out} / {md_out}", flush=True)
        if args.keep_sandbox and sandbox_base is not None:
            print(f"[self-mutation] 沙箱保留于：{sandbox_base}", flush=True)
        if args.fail_under is not None:
            score = report["summary"]["mutation_score"]
            if score is None:
                print("[self-mutation] --fail-under：无有效样本，判失败", file=sys.stderr)
                return 2
            if score < args.fail_under:
                print(
                    f"[self-mutation] --fail-under 未达标：score={score:.4f} < {args.fail_under:.4f}",
                    file=sys.stderr,
                )
                return 1
        return 0
    except SelfMutationError as e:
        print(f"[self-mutation] 错误：{e}", file=sys.stderr)
        return 2
    finally:
        if sandbox_base is not None and not args.keep_sandbox:
            shutil.rmtree(sandbox_base, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
