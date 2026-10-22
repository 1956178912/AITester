# M1（2026-09-29 审查 P0）：假修复/检出三指标 —— 评估一等口径（B6/2026-10-16：
# 呈现层不得以 passed 单独作数，须与三指标并列；本模块只增不改 passed 字段）
# 产出（不改变 passed），供评估层把"测试是否漏检缺陷"与"修复是否真正
# 成功"拆开度量。判分材料来自合成数据集模板自带的 `test_cases`（gold 测试）
# 与 `fixed`（gold 补丁），无需额外 LLM 调用。
#
# 设计原则（保守、零默认行为变化）：
#   1. 三指标对 SWE-bench 任务（metadata["source"] == "swe_bench"）与无
#      gold 材料的任务一律以 None 占位（键集合同构，向后兼容）；
#   2. 指标值 0.0 表示"可测量且为 0"，None 表示"材料缺失/不适用"——
#      下游统计（success_rate 等）不得把 None 计为 0；
#   3. 本模块是**纯函数 + 子进程执行**，不引入 LLM 调用；子进程失败时
#      保守记 None 而非 0（不误报）。
#
# F2P（fail-to-pass）修正（2026-09-30 独立审查 N1，P0）：
#   此前 detection_rate 仅取"生成测试在 buggy 代码上 rc != 0"单边口径，
#   导致"恒失败测试"（assert False / 恒不存在的 import / 语法错误文件）
#   同样记 1.0 —— 完全无信息量的测试获得满分（SWT-Bench 口径要求
#   fail-to-pass 双段：buggy 上红 **且** fixed 上绿，外加收集/语法
#   错误不算检出）。现改为三段判定：
#     F2P = rc_buggy != 0
#           AND rc_fixed == 0
#           AND 无收集/语法错误（"errors during collection" / SyntaxError
#               出现在 buggy 或 fixed 侧任一输出即拒）
#   测试执行错误率（test_error_rate）：生成测试在 buggy 侧以"非 0 但属于
#   收集/语法错误"退出 → 1.0（恒失败测试的直接防线）。

from __future__ import annotations

import logging
import os
import re
import shutil
import sys
import tempfile
from typing import Any

from src.utils.pytest_output import pytest_summary_counts as _pytest_summary_counts
from src.utils.pytest_output import suite_has_effective_pass

logger = logging.getLogger(__name__)

# 收集错误 / 语法错误的保守信号（pytest 输出子串，大小写不敏感匹配）。
# 仅取高置信标记，避免把普通断言失败文本误判为"测试执行错误"。
#
# 说明（2026-09-30 独立审查 N1 实测）：
# - pytest 的 import 失败（ModuleNotFoundError）不输出
#   "errors during collection" 字面串（其摘要为 "ERROR collecting
#   ..." + "1 error in ..."，且 rc=2 与断言失败 rc=1 区分）；
# - 语法错误输出 "SyntaxError"（"invalid syntax" 的 E 行）；
# - 因此判据取"rc>=2（收集/编译阶段中断，0 个测试被执行）
#   OR 任一显式标记命中"，双通道互补。
_COLLECTION_ERROR_MARKERS: tuple[str, ...] = (
    "errors during collection",
    "no tests were run",
    "syntaxerror",
    "error in 0.",
)

# ─── per-test 超时（A-06，2026-10-17 独立评审）─────────────────────────────
# 背景：QuixBugs 41 缺陷程序口径有 4 个任务（bitcount / sqrt / wrap /
# find_first_in_sorted）的**缺陷实现本身不终止**（如 bitcount 的
# `n ^= n - 1` 对任何 n 不终止）——生成测试在 buggy 侧整套餐被 120s
# 墙钟超时击杀 → `_run_pytest_in_tmp` 返回 None → detection=None 被
# 剔除（fail-closed 口径正确，但损失了 4 个可判定样本：这些任务在
# fixed 侧快速通过，本应判检出）。
#
# 修复口径：**per-test 超时**（pytest-timeout 的 --timeout=N，signal
# 方法可中断纯 Python 死循环）——单条挂死测试被单独判失败（红），
# 其余测试照常完赛，整套餐得出退出码而非 None。墙钟超时（120s）
# 保留为外层兜底。
#
# 纪律（与项目"零默认行为变化"一致）：
#   - 开关 M1_PER_TEST_TIMEOUT（秒；0/缺省 = 历史口径，零行为变化）；
#   - pytest-timeout 不可用（未安装/探测失败）时静默回退历史口径并
#     记 warning（不因缺插件改变判分语义）；
#   - 判分语义变化只发生在"原本整套餐超时记 None"的任务上
#     （None → 可判定），历史已判定任务逐位不变——单变量重放验证
#     见 tests/test_m1_per_test_timeout.py。
_PER_TEST_TIMEOUT_ENV = "M1_PER_TEST_TIMEOUT"
_PER_TEST_TIMEOUT_DEFAULT = 0
_pytest_timeout_available: bool | None = None

# N-3（2026-10-17）：确定性 oracle 与 LLM 测试的**独立判读**口径。
# 测试名单一事实源在 src/graph/nodes.py::_SPEC_ORACLE_TEST_NAMES；本模块用
# 同值常量（避免把 langgraph 依赖拖进判分轻路径），由
# tests/test_oracle_independent_judging.py 锁定两处相等。
_ORACLE_SUITE_TEST_NAMES: tuple[str, ...] = ("test_specir_v2_oracle", "test_specir_v2_smt_witness")
# pytest -k 表达式（一条即可同时覆盖主 oracle 与 SMT 见证）：
#   LLM-suite = 排除 oracle 测试名；或acle-suite = 只选 oracle 测试名。
_LLM_SUITE_KEYWORD_FILTER = "not test_specir_v2_oracle and not test_specir_v2_smt_witness"
_ORACLE_SUITE_KEYWORD_FILTER = "test_specir_v2_oracle or test_specir_v2_smt_witness"
# oracle-suite 独立判定取值域（写入结果行 oracle_suite_verdict）：
#   correct     oracle 在缺陷版失败 ∧ 修复版通过（真检出）
#   fp          oracle 在修复版失败（对正确实现假阳；含两侧皆失败的恒红型）
#   silent      两侧都通过（对该缺陷无信号）
#   misguided   缺陷版通过 ∧ 修复版失败（把缺陷行为断言成期望）
#   unavailable 未注入 / 材料缺失 / 超时 / 收集错误（fail-closed，不臆测）
ORACLE_SUITE_VERDICTS: tuple[str, ...] = ("correct", "fp", "silent", "misguided", "unavailable")
# pytest-timeout 的失败摘要标记（单条挂死测试 → 不可判，不并入 oracle 判定）
_ORACLE_SUITE_TIMEOUT_MARKERS: tuple[str, ...] = ("failed: timeout (>", "timeout (>")
# O-1（2026-10-18）：pytest 摘要行计数解析（区分"skip/unavailable"与 pass/fail）。
# 背景：oracle 仪器加固后，崩溃被 harness 转成 pytest.skip → 该测试的 rc=0；
# 若只看退出码会把"仪器不可用"误判为"pass"（进而把 oracle 判成 silent/fp）。
# 摘要行形如 "1 skipped in 0.12s" / "2 passed, 1 skipped in 0.3s"。
_ORACLE_SKIP_SENTINEL = "oracle-unavailable:"


def per_test_timeout_seconds() -> int:
    """读取 M1_PER_TEST_TIMEOUT（秒）。非正/缺省/非法值 → 0（历史口径）。"""
    raw = os.environ.get(_PER_TEST_TIMEOUT_ENV, "")
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return _PER_TEST_TIMEOUT_DEFAULT
    return value if value > 0 else _PER_TEST_TIMEOUT_DEFAULT


def _pytest_timeout_plugin_available() -> bool:
    """pytest-timeout 是否可被 M1 解释器加载（进程内探测，缓存一次）。

    判据：`import pytest_timeout` 成功即插件在（pytest 经 entry point
    自动加载，无需 -p 显式指定）。探测异常（解释器故障等）→ False
    （保守回退历史口径）。
    """
    global _pytest_timeout_available
    if _pytest_timeout_available is None:
        try:
            import pytest_timeout  # noqa: F401

            _pytest_timeout_available = True
        except Exception:
            _pytest_timeout_available = False
    return _pytest_timeout_available


def _looks_like_test_execution_error(returncode: int, output: str) -> bool:
    """判定一次 pytest 运行是否属于"测试执行错误"（根本没跑起来/异常终止）。

    三通道判据（任一命中即为执行错误）：
    1. **负退出码 = 进程被信号终止**（F14，2026-10-19 第三方审查 P1）：
       POSIX 下 subprocess 以 `-N` 表示"被信号 N 杀死"（如 -15=SIGTERM、
       -9=SIGKILL）。此时 pytest 没有给出正常结果，既不能当断言失败、更
       不能当"测试检出"——按执行错误 / 异常终止单列（detection 侧因此
       记 0.0 而非误判阳性，test_error_rate 记 1.0，门/预算侧判不可用）。
       历史缺陷：只排除 `rc>=2`，`buggy_rc=-15 ∧ fixed_rc=0` 会穿过所有
       守卫落到 `return 1.0`，把"异常进程终止"计成有效检出（报告 §M4）。
    2. rc >= 2：pytest 约定 rc=1 = 有测试失败（断言级）、rc=0 = 全过；
       rc>=2 表示收集/编译阶段中断（import 失败、语法错误、配置错误
       等），此时没有任何断言被执行，不构成有效 F2P 信号（N1 防线）；
       rc==5（no tests collected）是 pytest 的独立约定，同样归此；
    3. 输出含显式执行错误标记（"errors during collection" /
       "no tests were run" / "SyntaxError" / "error in 0.<s>" 的收集
       阶段中断摘要，如 "1 error in 0.05s"）——兜底 rc 不可得或
       非标准执行器的场景。

    消费方一致性（同口径）：`_compute_detection_rate`（检出不得为阳性）、
    `_compute_test_error_rate`（计入执行错误率 1.0）、`_suite_run_verdict`
    （oracle 判 unavailable）、`src/tools/detection_gates`（门判
    unavailable 而非 over_red）、`experiments/mutation_detection.py`、
    `experiments/misguided_metrics.py` 均委托本函数——负 rc 在所有入口
    都被视为异常终止。
    """
    if returncode < 0:
        # F14：信号终止（-SIGTERM / -SIGKILL / ...）→ 异常退出，不是断言失败，
        # 也不得进入正常检出路径。负 rc 是 POSIX subprocess 的固定语义
        # （Windows 无信号退出，不会出现负值）。
        return True
    if returncode >= 2:
        # R16（2026-10-08 第三起测量伪影配套）：rc>=2 覆盖 pytest 的 rc==2
        # （收集/编译中断）与 rc==5（no tests collected，收集到 0 个用例）。
        # 两者同属"没跑起来"而非"跑通了/断言失败"，一律判为执行错误——
        # 供 detection / test_error_rate / repair 三处消费（repair 侧对
        # rc==5 记 None 而非 0，见 _compute_repair_rate），遵循
        # "不误报→不漏报"（宁可标不可测，不产假信号）。
        return True
    if not output:
        return False
    low = output.lower()
    return any(marker in low for marker in _COLLECTION_ERROR_MARKERS)


def has_oracle_suite(generated_test: Any) -> bool:
    """生成测试文本是否含确定性 oracle 注入测试名（marker 子串判定）。

    用途：独立判读的**零差异开关**——无 marker（SPEC_ORACLE_EXEC_ENABLE=false
    的历史口径）时所有执行路径与修复前逐位一致（不过滤、不新增子进程）。
    """
    text = str(generated_test or "")
    return any(marker in text for marker in _ORACLE_SUITE_TEST_NAMES)


def llm_suite_keyword_filter(generated_test: Any) -> str | None:
    """LLM-suite 的 pytest -k 过滤表达式；无 oracle 测试时返回 None（历史口径）。

    Returns:
        ``_LLM_SUITE_KEYWORD_FILTER``（排除 oracle 测试）或 None（不过滤）。
    """
    return _LLM_SUITE_KEYWORD_FILTER if has_oracle_suite(generated_test) else None


def suite_filters(generated_test: Any) -> tuple[str | None, str | None]:
    """返回 (LLM-suite filter, oracle-suite filter)；无 oracle 测试时均为 None。"""
    if not has_oracle_suite(generated_test):
        return None, None
    return _LLM_SUITE_KEYWORD_FILTER, _ORACLE_SUITE_KEYWORD_FILTER


# F03（BA 轮建立、BD 轮上移）：计数解析与「有效通过」谓词的唯一实现在
# ``src/utils/pytest_output.py``。保留私有别名是因为本模块内约 20 个消费点
# 与既有回归锁按 ``_suite_has_effective_pass`` 这个名字引用（同一对象）。
pytest_summary_counts = _pytest_summary_counts
_suite_has_effective_pass = suite_has_effective_pass


def _suite_run_verdict(run: tuple[int, str, str] | None) -> str:
    """一次 pytest 子进程结果 → ``pass`` / ``fail`` / ``unavailable``（fail-closed）。

    - 超时 / IO 异常（``run is None``）→ unavailable（不误判为 fail）；
    - 收集/语法/无测试等执行错误（``_looks_like_test_execution_error``）→ unavailable；
    - pytest-timeout 单测超时标记 → unavailable（超时单列，不并入四分类）；
    - **O-1 仪器加固**：``pytest.skip("oracle-unavailable: ...")``（崩溃安全
      harness 产物）在 pytest 里记 skipped、**退出码仍为 0**；只看 rc 会把它
      误判成 pass（→ silent/fp）。故解析摘要行：``skipped>0 且 failed==0``
      → unavailable（"仪器不可用"不是判定信号，也不能算通过）；无任何
      passed/failed/skipped（被 deselect）→ unavailable。
    - 其余 rc==0 → pass；rc==1（含断言失败）→ fail。
    """
    if run is None:
        return "unavailable"
    rc, out, err = run
    combined = f"{out}\n{err}"
    if _looks_like_test_execution_error(rc, combined):
        return "unavailable"
    low = combined.lower()
    if any(marker in low for marker in _ORACLE_SUITE_TIMEOUT_MARKERS):
        return "unavailable"
    counts = pytest_summary_counts(combined)
    skipped = int(counts.get("skipped", 0))
    failed = int(counts.get("failed", 0))
    passed = int(counts.get("passed", 0))
    if rc == 0:
        if skipped > 0 and failed == 0:
            # 全 skip 或部分 skip 但无失败：无有效判定信号
            return "unavailable"
        if passed == 0 and skipped == 0:
            return "unavailable"
        return "pass"
    return "fail"


def _python_interpreter() -> str:
    """M2（2026-09-30 独立审查 N4，P1）：子进程解释器口径。

    此前硬编码 "python3"：本机 `which python3` 指向系统 Python（如
    /Library/Frameworks/Python.framework/Versions/3.14/bin/python3），
    与项目 venv 解释器不同 —— 一旦该解释器无 pytest，所有 M1 任务
    静默退化为 "collection error → detection=1.0 / repair=0.0" 的
    无效口径。现改用 `sys.executable`（本进程解释器，实验脚本与
    _m1_metrics 同进程加载，即 venv 解释器），并在模块加载期做
    前置断言：解释器无 pytest 时直接 raise（fail-fast，不再静默
    退化）。

    环境变量 AITESTER_M1_PYTHON 可显式覆盖（供特殊执行环境使用）。
    """
    override = os.getenv("AITESTER_M1_PYTHON", "").strip()
    interpreter = override or sys.executable
    # 前置断言：解释器必须能 import pytest，否则 M1 指标会整体失效。
    # P0-4（2026-10-11 外部评审 §10）：探测同样走 run_with_timeout，避免
    # 解释器挂死时遗留孤儿进程（与判分路径同一修法）。
    from src.utils.process_utils import run_with_timeout

    probe = run_with_timeout(
        [interpreter, "-c", "import pytest"],
        timeout=30,
        text=True,
        logger_name="m1_interpreter_probe",
    )
    if getattr(probe, "timed_out", False):
        raise RuntimeError(f"M1 指标解释器 {interpreter} 探测超时（30s），拒绝产出无效指标（超时非'无 pytest'）")
    if probe.returncode != 0:
        raise RuntimeError(
            f"M1 指标解释器 {interpreter} 无法 import pytest，拒绝产出无效指标：{(probe.stderr or '').strip()[:200]}"
        )
    return interpreter


def _quixbugs_support_root() -> str | None:
    """QuixBugs 数据根目录（AITESTER_QUIXBUGS_DATA），未配置/不存在 → None。

    真实基准（QuixBugs）的 gold 测试依赖辅助模块（node / load_testdata）
    与 json 测试数据，需从克隆目录复制进 tmp 环境；未配置时保守返回
    None（包结构测试将在缺辅助模块时自然失败，与历史口径同，不误报）。
    """
    root = os.getenv("AITESTER_QUIXBUGS_DATA", "").strip()
    return root if root and os.path.isdir(root) else None


def _prepare_packaged_test_tree(tmpdir: str, target_code: str, test_code: str, module_name: str) -> tuple[str, str]:
    """为"包结构测试"（QuixBugs 口径）构建 tmp 目录树，返回 (test_path, PYTHONPATH)。

    QuixBugs 官方测试的 import 形态（实测 2026-10-08）：
        from node import Node                          # 辅助模块
        from load_testdata import load_json_testcases  # 辅助模块（读 ../json_testcases/*.json）
        from python_programs.<module> import <name>    # 被测模块（包结构）

    历史口径（单文件 synthetic）只在 tmpdir 写 {module}.py + test_{module}.py，
    上述 import 全部 ModuleNotFoundError → pytest 收集错误（rc=2）→
    repair/detection 被系统性判 0（2026-10-08 QuixBugs A/B 实测：9 个
    **通过官方测试的正确补丁**被误判 patch_correct=0，根因即此——测量层
    bug，与 ADR-0021 同类）。本函数按真实基准的包结构镜像 tmp 目录：

        tmpdir/
          conftest.py                          # pytest.use_correct=False（测试 if 分支需要）
          python_programs/__init__.py
          python_programs/{module}.py          # 补丁后代码
          correct_python_programs/__init__.py  # 测试 if 分支占位（默认不执行）
          python_testcases/                    # 辅助模块 + 本次 gold 测试（从克隆目录复制辅助件）
          json_testcases/                      # load_testdata 的相对路径依赖

    PYTHONPATH = [tmpdir, tmpdir/python_testcases]。辅助模块缺失时尽力而为
    （至少建包结构 + conftest），不阻断其余场景。
    """
    from pathlib import Path

    root = Path(tmpdir)
    pkg = root / "python_programs"
    pkg.mkdir(exist_ok=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / f"{module_name}.py").write_text(target_code, encoding="utf-8")
    # 2026-10-10（审查报告 §11.1b 结果二十一：第四起测量伪影）：**双布局**——
    # 同时把被测模块放到 tmpdir 根，使 `from {module} import f`（扁平平铺）
    # 与 `from python_programs.{module} import f`（QuixBugs 包结构）**都能解析**。
    #
    # 背景（实测证据）：`state["module_name"]` 取 task_id 末段（如 `bitcount`），
    # 生产执行环境把被测模块**平铺**写成 `{module}.py`（`executor_runtime` 沙箱），
    # 故 Generator 按提示写出的测试是**扁平 import**（`from bitcount import bitcount`）
    # ——这在它被生成时的环境里是**正确**的。但本判分树此前**只**提供包结构
    # `python_programs/{module}.py`，扁平 import 一律 `ModuleNotFoundError`
    # → pytest rc=2（收集中断）→ `_looks_like_test_execution_error` 判"没跑起来"
    # → **detection 恒为 0（构造性），与测试质量无关**。
    #
    # 零 LLM 复现（12 任务子集、9 个缺陷程序）：**9/9 在 buggy 与 fixed 两侧
    # 均 rc=2**，全部"执行错误(收集失败)"；即 E4 的 0/41 检出有相当部分来自
    # 该测量伪影，而非"红得不特异"。
    #
    # **判分口径不放松**：仅让两种**合法**的模块解析方式都能 import；
    # 三段判定（buggy 红 ∧ fixed 绿 ∧ 两边无执行错误）**逐字不变**，
    # 一个无效/恒失败的测试在新旧布局下同样得 0。
    (root / f"{module_name}.py").write_text(target_code, encoding="utf-8")
    correct_pkg = root / "correct_python_programs"
    correct_pkg.mkdir(exist_ok=True)
    (correct_pkg / "__init__.py").write_text("", encoding="utf-8")
    (root / "conftest.py").write_text(
        "import pytest\n\npytest.use_correct = False\npytest.run_slow = False\n", encoding="utf-8"
    )
    testcases_dir = root / "python_testcases"
    testcases_dir.mkdir(exist_ok=True)
    support_root = _quixbugs_support_root()
    if support_root:
        src_testcases = Path(support_root) / "python_testcases"
        for aux in ("node.py", "load_testdata.py"):
            src = src_testcases / aux
            if src.is_file():
                shutil.copy(str(src), str(testcases_dir / aux))
        src_json = Path(support_root) / "json_testcases"
        if src_json.is_dir():
            shutil.copytree(str(src_json), str(root / "json_testcases"))
    test_path = testcases_dir / f"test_{module_name}.py"
    # 前置注入 pytest.use_correct / run_slow（QuixBugs 测试的 `if pytest.use_correct:`
    # 条件依赖）——直接写进测试模块头部比依赖 conftest 的目录收集更可靠
    # （tmp 目录无 pytest 配置文件时，conftest 的自动收集不覆盖该路径，
    # 实测 AttributeError；注入 prelude 后与 conftest.py 双保险）。
    prelude = "import pytest\n\npytest.use_correct = False\npytest.run_slow = False\n\n"
    test_path.write_text(prelude + test_code, encoding="utf-8")
    return str(test_path), os.pathsep.join([tmpdir, str(testcases_dir)])


# QuixBugs 官方测试对辅助模块（node / load_testdata）的 import——正则限定
# 行首 from/import，避免把正文中的同名词符串误判为依赖。
_QUIXBUGS_SUPPORT_IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+(?:node|load_testdata)\b", re.MULTILINE)


def _needs_quixbugs_support(test_code: str) -> bool:
    """测试代码是否依赖 QuixBugs 辅助模块（node / load_testdata）。"""
    return bool(_QUIXBUGS_SUPPORT_IMPORT_RE.search(test_code or ""))


def _packaged_support_ready() -> tuple[bool, str]:
    """QuixBugs 包结构判分所需辅助材料是否就绪（R16 fail-closed 前置检查）。

    返回 (就绪, 原因)：就绪时原因为空；否则原因给出缺失项（供 logger.warning）。
    仅当测试确实 import 辅助模块时才需调用（自足包结构测试无需辅助材料）。

    R16（2026-10-08 第三起测量伪影配套）：历史上辅助材料缺失时"尽力而为"
    会把"没跑起来"（收集错误 rc=2）静默记成 repair=0 / detection=0——与
    "真的没修好/没检出"不可区分（假结论来源）。现改 fail-closed：材料缺失
    时调用方记 None + logger.warning（不误报→不漏报）。
    """
    root = _quixbugs_support_root()
    if root is None:
        return False, "AITESTER_QUIXBUGS_DATA 未配置或其目录不存在"
    src_testcases = os.path.join(root, "python_testcases")
    missing = [aux for aux in ("node.py", "load_testdata.py") if not os.path.isfile(os.path.join(src_testcases, aux))]
    if missing:
        return False, f"QuixBugs 辅助模块缺失 {missing}（预期位于 {src_testcases}）"
    return True, ""


def _prepare_cross_file_test_tree(
    tmpdir: str, target_code: str, test_code: str, task_metadata: dict[str, Any]
) -> tuple[str, str]:
    """为"跨文件任务"（synthetic Level 3 / 3.5）构建 tmp 目录树并返回 (test_path, PYTHONPATH)。

    背景（2026-10-08 R2 第三起测量伪影）：
        跨文件任务的 gold test_cases 直接 import 伴生模块
        （``from module_a import run_pipeline`` / ``from module_b import process``），
        与 pattern 名无关，故 P1-4 的模块名中性化不重写它们。历史"单文件
        判分口径"只在 tmp 写 ``{task_id末段}.py`` + ``test_{task_id末段}.py``，
        ``module_a/b/c`` 全部 ModuleNotFoundError → pytest 收集错误 rc=2 →
        跨文件行的 repair 被系统性判 0、false_fix 被抬升、detection 偏低
        （六批次实证：R4-A 8/50 跨文件行 repair 全 0、false_fix 6/8）。

    物化规则（与被测系统真实工作区 ``run_benchmark._write_cross_file_modules``
    同口径，仅补"被测目标模块 = 传入 target_code"这一判分必需项）：
        - 模块名取 metadata 的 module_a_name / module_b_name / module_c_name
          （缺省按 module_a / module_b / module_c 兜底，与物化链路一致）；
        - **被测目标模块**（metadata["target_module"] 指向者，如 module_b /
          module_c）的内容 = 传入的 target_code —— buggy / patched / fixed
          三态统一走此参数（detection 侧传 original_code / gold fixed，
          repair 侧传应用补丁后的代码）；
        - 其余伴生模块取 metadata 的缺陷原版代码（module_*_code）；
        - 顶层模块直接落 ``{name}.py``（gold 测试为 ``from module_x import``
          顶层 import，无需包 ``__init__.py``，与真实工作区同结构）；
        - PYTHONPATH 覆盖 tmpdir，保证 import 解析到物化模块。

    模块缺失 / 目标模块名不在伴生列表中时尽力而为（至少落 target_code），
    不阻断——与 _write_cross_file_modules 的保守降级一致。
    """
    from pathlib import Path

    root = Path(tmpdir)
    target_module = str(task_metadata.get("target_module") or "module_b")
    specs = (
        ("module_a_name", "module_a_code"),
        ("module_b_name", "module_b_code"),
        ("module_c_name", "module_c_code"),
    )
    written: set[str] = set()
    for name_key, code_key in specs:
        name = str(task_metadata.get(name_key) or code_key.replace("_code", ""))
        if not name:
            continue
        if name == target_module:
            # 目标模块内容 = 传入 target_code（buggy/patched/fixed 三态统一）
            (root / f"{name}.py").write_text(target_code, encoding="utf-8")
            written.add(name)
            continue
        body = str(task_metadata.get(code_key) or "")
        if not body.strip():
            continue  # 伴生模块缺失（如 L3 无 module_c）：跳过，同 _write_cross_file_modules
        (root / f"{name}.py").write_text(body, encoding="utf-8")
        written.add(name)
    if target_module not in written:
        # metadata 缺伴生名（异常输入）时至少保证目标模块可被 import
        (root / f"{target_module}.py").write_text(target_code, encoding="utf-8")
    test_path = root / f"test_{target_module}.py"
    test_path.write_text(test_code, encoding="utf-8")
    return str(test_path), tmpdir


def _run_pytest_in_tmp(
    test_code: str,
    target_code: str,
    module_name: str,
    timeout: int = 120,
    task_metadata: dict[str, Any] | None = None,
    per_test_timeout: int | None = None,
    keyword_filter: str | None = None,
) -> tuple[int, str, str] | None:
    """在临时目录里写 target + test 文件并跑 pytest。

    返回 (pytest 退出码, stdout, stderr)；
    - 0 = 全过；非 0 = 存在失败/错误；
    - 超时 / IO 异常 / 材料缺失（fail-closed）→ 返回 None（无法判定，
      调用方保守记 None）。

    分派（R27/R16，2026-10-08）：**优先消费显式信号**——
        - task_metadata["is_cross_file"] 为真 → 跨文件物化分支
          （_prepare_cross_file_test_tree）；
        - 否则回退历史子串启发式 ``"python_programs" in test_code``
          （QuixBugs 包结构兼容回退，见 _prepare_packaged_test_tree）；
        - 其余走历史单文件口径（synthetic 单文件）。
    task_metadata 为 None 时行为与历史逐位一致（detection_gates.py:85 的
    委托调用不传该参数 → 零回归）。

    A-06（2026-10-17）：per_test_timeout 为 None 时读环境变量
    M1_PER_TEST_TIMEOUT（0/缺省 = 历史口径）；为正且 pytest-timeout
    可用时，pytest 追加 ``--timeout=N``（signal 方法）——单条挂死
    测试被单独判失败而非拖垮整套餐（缺陷实现不终止类任务由 None
    转为可判定）。墙钟 timeout 参数保持外层兜底语义不变。

    N-3（2026-10-17，A-05 独立判读）：``keyword_filter`` 非空时追加
    ``-k <表达式>`` 选择子集（LLM-suite / oracle-suite 分开执行）。
    **缺省 None 时不追加任何参数**——命令与修复前逐位一致（SPEC_ORACLE_EXEC_ENABLE
    =false 的历史口径零差异；由 tests 锁定）。
    """
    if per_test_timeout is None:
        per_test_timeout = per_test_timeout_seconds()
    use_per_test = per_test_timeout > 0 and _pytest_timeout_plugin_available()
    if per_test_timeout > 0 and not use_per_test:
        logger.warning(
            "M1_PER_TEST_TIMEOUT=%d 已设置但 pytest-timeout 不可用——回退历史口径（整套餐墙钟超时）",
            per_test_timeout,
        )
    tmpdir = tempfile.mkdtemp(prefix=f"aitester_m1_{module_name}_")
    try:
        md = task_metadata or {}
        # 显式分派（R16/R27）：metadata 在场时信号优先；仅当 metadata 缺省
        # （detection_gates 委托调用）才回退历史子串启发式。
        #   - is_cross_file=True → 跨文件物化；
        #   - source=="quixbugs"（显式）或（缺省时）测试含 "python_programs"
        #     子串 → 包结构物化。含字面 "python_programs" 的 synthetic 单文件
        #     测试在 metadata 在场时**不再**被误分派到包分支。
        packaged = md.get("source") == "quixbugs" or (not md and "python_programs" in test_code)
        if md.get("is_cross_file"):
            # 跨文件任务（显式信号优先）：物化 module_a/b/c 伴生模块树
            test_path, pythonpath = _prepare_cross_file_test_tree(tmpdir, target_code, test_code, md)
        elif packaged:
            # 包结构测试（QuixBugs 等真实基准口径，2026-10-08 修复）：
            # 镜像包目录树，不让 gold 测试的 import 在 tmp 环境里失败。
            # R16 fail-closed：依赖辅助模块（node/load_testdata）而材料缺失
            # 时记 None（不静默判 0）。
            if _needs_quixbugs_support(test_code):
                ready, reason = _packaged_support_ready()
                if not ready:
                    logger.warning(
                        "M1 包结构判分需 QuixBugs 辅助材料但不可用（%s）——保守记 None（fail-closed，不误判为 0）",
                        reason,
                    )
                    return None
            test_path, pythonpath = _prepare_packaged_test_tree(tmpdir, target_code, test_code, module_name)
        else:
            # 历史口径（synthetic 单文件：{module}.py + test_{module}.py）
            target_path = os.path.join(tmpdir, f"{module_name}.py")
            test_path = os.path.join(tmpdir, f"test_{module_name}.py")
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(target_code)
            with open(test_path, "w", encoding="utf-8") as f:
                f.write(test_code)
            pythonpath = tmpdir
        # P0-4（2026-10-11 外部评审 §10）：改用 run_with_timeout。
        # 此前用裸 subprocess.run(timeout=)：超时只杀**直接子进程**，pytest
        # 派生的子进程成为孤儿（实测遗留 3 个进程运行 16.5 小时、100% CPU）。
        # run_with_timeout 以 start_new_session 建新进程组 + killpg 整树终止，
        # 且以临时文件（非管道）承接输出，结构上不会因孙进程持管道写端而阻塞。
        #
        # M-3（2026-10-17，孤儿 pytest 根因修复）：额外启用 orphan_guard——
        # start_new_session 让本 pytest 自成会话（killpg 整树终止所需）的代价是
        # **调用方进程被外部 SIGKILL 时本 pytest 会变 ppid=1 孤儿**（L 轮实测
        # PID 57034：bitcount 挂死 + 父进程异常消亡；仅超时路径的 killpg 覆盖不到）。
        # orphan_guard 起一个父死亡看门狗（与 pytest 同进程组）：调用方消亡后
        # 0.1s 级检测并 killpg 回收本 pytest 进程组；超时路径仍由 killpg 整组回收。
        # 嵌套 pytest 命令自身不建新会话，故看门狗对新会话逃逸形态的边界不在此处触发。
        # A08（2026-10-18 第三方评审 P0，凭证边界）：本子进程执行的是 LLM
        # 生成测试 + 被测代码（不可信），此前只剔除宿主 pytest 配置，宿主
        # LLM_*_API_KEY / OPENAI_API_KEY / AWS_* 等凭证随环境整体继承。改用
        # 统一构造器 untrusted_exec_env（最小白名单 + 显式 overrides）——
        # M1 判分是主基准必经路径，凭证不得进入被评判子进程。
        try:
            from src.utils.process_utils import run_with_timeout, untrusted_exec_env

            res = run_with_timeout(
                [
                    _python_interpreter(),
                    "-m",
                    "pytest",
                    "-q",
                    "--no-header",
                    "-p",
                    "no:cacheprovider",
                    # A-06：per-test 超时（仅当开关为正且插件可用；signal
                    # 方法可中断纯 Python 死循环——缺陷实现不终止类任务的
                    # 单条挂死测试据此被单独判失败，整套餐得以完赛）。
                    *(["--timeout", str(per_test_timeout)] if use_per_test else []),
                    # N-3：独立判读的 -k 子集过滤（None = 历史逐位一致的命令）
                    *(["-k", keyword_filter] if keyword_filter else []),
                    test_path,
                ],
                timeout=timeout,
                cwd=tmpdir,
                text=True,
                logger_name="m1_metrics",
                orphan_guard=True,
                # H 轮（2026-10-16）：剔除宿主 PYTEST_PLUGINS/PYTEST_ADDOPTS——
                # 否则宿主插件在 PYTHONPATH=tmpdir 的嵌套运行里不可导入 → rc=1
                # 被读成"测试红" → detection_gates 误判 over_red（实测复现，
                # 详见 nested_pytest_env 文档串）。A08 起改走最小环境构造器：
                # 宿主凭证同样不进入本子进程（覆盖 pytest 配置 + 凭证）。
                env=untrusted_exec_env(
                    PYTHONDONTWRITEBYTECODE="1",
                    PYTHONPATH=pythonpath,
                ),
            )
            if getattr(res, "timed_out", False):
                # 超时 = 不可测（与历史口径一致：返回 None 不计为 0，不误报）
                return None
            return res.returncode, res.stdout or "", res.stderr or ""
        except Exception:
            return None
    except Exception:
        return None
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _target_code_after_patch(original_code: str, patch: str) -> str:
    """把系统生成的补丁（unified diff 或完整文件代码）应用到原始代码。

    - 完整文件代码形态（非 unified diff）→ 直接用 patch 文本作为新代码；
    - unified diff 形态 → 用 patch_applier 的安全应用路径（safe_apply_patch）；
    - 应用失败 / 空补丁 → 返回原始代码（口径保守：不假设修复发生）。

    批次 VII（ADR-0021）：完整文件分支先经 normalize_patch_text 清理
    （markdown 围栏 / python 前缀剥离，与写盘链路同口径）。此前直接用
    原始文本——state["patch"] 约定可含围栏残留（E2 存量 274/274 实测
    以 "python\n" 开头），未清理文本首行不可解析，gold 测试 100%
    NameError 失败，repair_rate 被系统性压零（"repair 全线 0"测量伪影，
    清理后重放 51/106 通过）。本修复弥合"透出口径 ≠ 执行口径"分叉；
    干净补丁幂等（清理后不变），历史行为仅在受染输入上改变。
    """
    if not patch or not patch.strip():
        return original_code
    stripped = patch.lstrip()
    if not stripped.startswith(("diff --git", "@@", "---", "+++", "old ", "new ")):
        # 完整文件代码形态（批次 VII：写盘同口径清理，见 docstring）
        from src.tools.patch_applier import normalize_patch_text

        return normalize_patch_text(patch)
    try:
        from src.tools.patch_applier import safe_apply_patch

        new_code, ok = safe_apply_patch(original_code, patch)
        if ok:
            return new_code
    except Exception:
        pass
    return original_code


def _extract_gold_material(task: Any) -> tuple[str, str, str] | None:
    """从任务 metadata 提取 (module_name, gold_test_code, gold_fixed_code)。

    合成数据集（synthetic）：metadata 含 test_cases（gold 测试）与
    fixed（gold 补丁文本，可能是完整函数或 unified diff）；模块名来自
    task_id 最后一段。SWE-bench / 无 gold 材料 → 返回 None。
    """
    md = getattr(task, "metadata", None) or {}
    if md.get("source") == "swe_bench":
        return None
    test_cases = md.get("test_cases") or ""
    fixed = md.get("fixed") or ""
    if not test_cases.strip():
        return None
    # P1-4（2026-10-05 独立审查）：模块名 = task_id 末段。泄漏修复在**生成
    # 层**完成（synthetic_dataset 中性化 task_id 并同步重写 gold import），
    # 本侧派生规则保持不变即自动中性——单点派生，避免双名机制。
    raw_name = str(task.task_id).split("__")[-1]
    module_name = raw_name.replace("-", "_")[:50]
    return module_name, test_cases, fixed


def _gold_fixed_code(task: Any) -> str:
    """gold 修复后的代码全文（F2P 第二段判据）。

    材料来源（合成数据集）：
    - 单文件任务（is_cross_file=False）：metadata["fixed"] 是"修复后的
      函数代码"（完整文件形态或函数体），经 _target_code_after_patch
      应用到 instance_code（空补丁返回原始代码，保守口径）；
    - 跨文件任务（is_cross_file=True）：metadata["fixed_module_code"]
      是被调方修复后的完整模块源码，直接作为固定版代码（该任务
      instance_code = 缺陷方模块全文，"应用"语义无意义，全文替换
      即正确语义）；
    - SWE-bench / 无 gold 材料 → 返回 ""（调用方据此保守降级为 None）。

    注意：noise_seed 注释（实例侧"# noise_seed=<n>"）在固定版侧不存在，
    不影响 gold 测试在固定版上的判定（gold 测试 import 的是模块名，
    与注释无关）。
    """
    md = getattr(task, "metadata", None) or {}
    if md.get("source") == "swe_bench":
        return ""
    original_code = str(getattr(task, "instance_code", "") or "")
    if md.get("is_cross_file"):
        return str(md.get("fixed_module_code") or "")
    fixed = md.get("fixed") or ""
    if not fixed.strip():
        return ""
    return _target_code_after_patch(original_code, fixed)


def _is_flaky_unverified(final_state: dict[str, Any] | None) -> bool:
    """A16（2026-10-18 第三方评审）：该任务是否已观测到执行不稳定（fail→pass）。

    背景：``nodes._executor_node`` 在重试层保留每次尝试记录后，若观察到同一
    (target_code, generated_test) 先失败后通过（fail→pass），写
    ``state["flaky_unverified"]=True``（与历史 flaky 门禁同字段语义）。
    此时该任务的执行结果本身不确定，**全部 M1 指标按"不可测"（None）处理**，
    不得用一次可能翻转的运行结果污染 detection / repair / false-fix 分母
    （这正是 flaky_gate / state.py 文档承诺的"M1 不可测"口径；A16 修复前
    该承诺只有标记、没有下游消费实现）。

    缺失 / None / False → 视为非 flaky（历史批次零行为变化）。
    """
    return bool((final_state or {}).get("flaky_unverified"))


def _compute_detection_rate(task: Any, final_state: dict[str, Any] | None) -> float | None:
    """M1 检出率（**fail-to-pass 三段判定**，SWT-Bench 口径）。

    定义（2026-09-30 独立审查 N1 修正）：
        1. 生成测试在 original_code（缺陷代码）上运行 → rc_buggy != 0；
        2. 生成测试在 gold 修复代码（fixed）上运行 → rc_fixed == 0；
        3. 两侧输出均无"收集错误 / 语法错误"信号
           （"errors during collection" / "no tests were run" /
             "SyntaxError"）；
        三者同时成立 → detection_rate = 1.0（真实 fail-to-pass 检出）；
        任一不成立 → 0.0。

        F03（2026-10-21 第三方审查 P1）：第二段的 rc==0 必须伴随**至少
        1 个真实 passed**（全 skip / xfail / xpass / deselect 的套件没有
        断言通过）——否则记 None（不可测），不得计为检出。

        特别地，"恒失败测试"（assert False / 恒不存在的 import /
        语法错误文件）在 fixed 上同样非 0 或有收集错误 → 判定 0.0，
        消除 N1 的"坏测试刷满指标"通道。

    无 generated_test / 无 gold 材料 / 执行超时 → None（不可测量，
    不误报）。
    历史 88% 的"假成功"（29/44 iteration-0 无修复动作）在此口径下
    会被如实标为 0.0。

    gold 修复代码缺失时（有 test_cases 但无 fixed 材料）无法完成
    F2P 第二段，保守记 None（不误报，与"无 gold 材料"同口径）。

    N-3（2026-10-17）：本函数判定对象 = **LLM-suite**（排除
    test_specir_v2_oracle / test_specir_v2_smt_witness 的独立运行）。
    生成测试无 oracle 注入测试名时行为与历史逐位一致。oracle 单独判定见
    ``_compute_oracle_suite_verdict``；结果行另有显式
    ``llm_suite_detection_rate`` / ``oracle_suite_verdict`` 两键。
    """
    if final_state is None:
        return None
    if _is_flaky_unverified(final_state):
        # A16：执行不稳定（fail→pass）→ 该任务检出结果不可测（None），
        # 与 flaky_gate/state.py 的"M1 按不可测处理"承诺一致。
        return None
    mat = _extract_gold_material(task)
    if mat is None:
        return None
    module_name, _test_cases, _fixed = mat
    generated_test = final_state.get("generated_test") or ""
    if not generated_test.strip():
        return None
    original_code = str(getattr(task, "instance_code", "") or "")
    if not original_code.strip():
        return None

    # F2P 第二段材料：gold 修复代码。缺失时保守 None（不误报，与
    # "无 gold 材料"同口径 —— 无 fixed 材料的任务无法完成 F2P 判定）。
    fixed_code = _gold_fixed_code(task)
    if not fixed_code.strip():
        return None

    # R27：把任务上下文（跨文件物化信号）透传执行器——显式分派，不再依赖
    # 测试文本子串启发式。
    task_md = getattr(task, "metadata", None) or {}
    # N-3（2026-10-17）：detection_rate 语义 = **LLM-suite**。生成测试含确定性
    # oracle（SPEC_ORACLE_EXEC_ENABLE=true）时，本判定只跑排除 oracle 测试名
    # 的子集——oracle 在 fixed 侧的失败不得改写 LLM 检出结论（A-05 实测混判
    # 抹掉 14/22 个既有检出）。无 oracle 测试（默认关）时 filter=None，
    # 命令与修复前逐位一致（零差异由 tests 锁定）。
    llm_filter = llm_suite_keyword_filter(generated_test)
    rc_buggy = _run_pytest_in_tmp(
        generated_test, original_code, module_name, task_metadata=task_md, keyword_filter=llm_filter
    )
    if rc_buggy is None:
        return None
    buggy_rc, buggy_out, buggy_err = rc_buggy
    rc_fixed = _run_pytest_in_tmp(
        generated_test, fixed_code, module_name, task_metadata=task_md, keyword_filter=llm_filter
    )
    if rc_fixed is None:
        return None
    fixed_rc, fixed_out, fixed_err = rc_fixed

    # 三段判定（N1 修正）
    if buggy_rc == 0:
        return 0.0  # buggy 侧没红 = 缺陷未被检出（盲区通过）
    if _looks_like_test_execution_error(buggy_rc, buggy_out + "\n" + buggy_err):
        return 0.0  # buggy 侧红是"没跑起来"（收集/语法错误），不是检出
    if fixed_rc != 0:
        # fixed 侧仍红：测试恒失败 / 无效（N1 核心防线）；
        # 若 fixed 侧红且属执行错误，同样 0.0（下一分支兜底）
        return 0.0
    if _looks_like_test_execution_error(fixed_rc, fixed_out + "\n" + fixed_err):
        return 0.0  # fixed 侧红且是收集/语法错误 = 测试本身坏
    if not _suite_has_effective_pass(fixed_out + "\n" + fixed_err):
        # F03：fixed 侧 rc==0 但全 skip/xfail/deselect——没有断言通过，
        # F2P 第二段不成立也不可能成立，记不可测（None），不误报检出。
        return None
    return 1.0


def _compute_test_error_rate(task: Any, final_state: dict[str, Any] | None) -> float | None:
    """M1 测试执行错误率（N1 防线，2026-09-30 独立审查）：

    定义：生成测试在 buggy 代码上以"非 0 且属于收集/语法错误"退出
    （"errors during collection" / "no tests were run" / "SyntaxError"）
    → 1.0；否则 → 0.0。
    无 generated_test / 无 gold 材料 / 执行超时 → None。

    用途：把"恒失败 / 坏测试"从 detection_rate 的"分母侧"单独报出，
    供统计层直接观测 N1 通道的占比（历史批次 148 个 JSON 无一携带
    本字段，故默认键值 None 保持键集合同构）。
    """
    if final_state is None:
        return None
    if _is_flaky_unverified(final_state):
        # A16：执行不稳定 → 测试执行错误率同样不可测（None）。
        return None
    mat = _extract_gold_material(task)
    if mat is None:
        return None
    module_name, _test_cases, _fixed = mat
    generated_test = final_state.get("generated_test") or ""
    if not generated_test.strip():
        return None
    original_code = str(getattr(task, "instance_code", "") or "")
    if not original_code.strip():
        return None
    # R27：透传任务上下文（跨文件物化信号）供显式分派
    task_md = getattr(task, "metadata", None) or {}
    # N-3：测试执行错误率同样只看 LLM-suite（oracle 自身的收集/崩溃属
    # oracle_suite_verdict 的 unavailable 语义，不污染 LLM 测试健康度）。
    rc = _run_pytest_in_tmp(
        generated_test,
        original_code,
        module_name,
        task_metadata=task_md,
        keyword_filter=llm_suite_keyword_filter(generated_test),
    )
    if rc is None:
        return None
    rc_val, out, err = rc
    if rc_val != 0 and _looks_like_test_execution_error(rc_val, out + "\n" + err):
        return 1.0
    return 0.0


def _compute_repair_rate(task: Any, final_state: dict[str, Any] | None) -> float | None:
    """M1 修复率（gold 材料独立裁决，自动化 oracle）：gold 测试在"应用系统补丁后的代码"上是否全过。

    定义：
        系统生成补丁 → safe_apply_patch(original_code, patch) →
        new_code；再在 new_code 上跑 gold test_cases（模板自带）：
        rc == 0 且含至少 1 个真实 passed → repair_rate = 1.0（修复被独立验证）；
        rc == 0 但全 skip / xfail / deselect（F03）→ None（不可测，不误判修好）；
        rc != 0 → 0.0（补丁未通过 gold 材料独立裁决）；
        无补丁（iterations=0，patch 为空）→ 0.0（没有修复动作，与历史口径区分）；
        rc == 5（no tests collected，gold 材料未跑起来）→ None（R16
        fail-closed：不可测量，不误判为 0）。

    与 passed（"我生成的测试在（可能未修复的）代码上通过"）的区别：
        本指标只看 gold 测试在**最终代码**上的通过性，不依赖 LLM 自写
        测试，消除 oracle-from-implementation 假成功通道。

    R28（2026-10-08 R2）：空补丁早退 return 0.0 —— 对齐本 docstring 与
    _false_fix_rate 的推导口径。此前空补丁仍走"应用空补丁 = 原代码 → 跑
    gold"，若缺陷原码**恰好**能过 gold 测试（oracle 与缺陷不打架的边界行）
    会被误判 repair=1.0；早退消除该假阳性。
    """
    if final_state is None:
        return None
    if _is_flaky_unverified(final_state):
        # A16：执行不稳定（fail→pass）→ 修复率不可测（None），不得记 0/1。
        return None
    mat = _extract_gold_material(task)
    if mat is None:
        return None
    module_name, test_cases, _fixed = mat
    original_code = str(getattr(task, "instance_code", "") or "")
    if not original_code.strip():
        return None
    patch = final_state.get("patch") or ""
    if not patch.strip():
        return 0.0  # 无修复动作（iterations=0）——早退，不假设修复发生（R28）
    # P0-2b（2026-10-11，真实批次实测发现）：**补丁未写盘 ≠ 修复发生**。
    # R28 只堵住了"空补丁"这一条路径；非空补丁**全部被证据门拒绝**
    # （repair_history 全为 patch_applied=False）时，`_target_code_after_patch`
    # 返回的仍是**原始缺陷代码**，gold 测试在它上面通过 → 误判 repair=1.0。
    #
    # 实测证据（2026-10-11 真实 LLM 批次，QuixBugs n=50，缓存关闭）：
    # **8/50 行**（16%）出现 `patch_applied 全 False` + `repair_rate=1.0`
    # + `source_patched_unverified=True` + `stop_reason=skip_debugger_repair_invalid`
    # （get_factors / kheapsort / knapsack / rpn_eval / shunting_yard /
    #   bitcount / find_first_in_sorted / sqrt）。这些行**根本没有补丁落地**，
    # 其 1.0 完全来自"缺陷原码恰好过 gold 测试"——是该基准的已知属性
    # （历史 FIXED harness 批同现象：24/50 提前终止、其中 13 行仍判正确）。
    #
    # 口径：修复率评估的对象是**补丁**。若没有任何一轮补丁成功写盘，
    # 则"应用补丁后的代码"在语义上不存在 → 记 0.0（未修复），而非 1.0。
    # 该口径使 `correct ⊆ plausible` 不变量在结构上成立。
    history = final_state.get("repair_history") or []
    if history and not any(bool(h.get("patch_applied")) for h in history if isinstance(h, dict)):
        return 0.0  # 无任何一轮写盘成功 → 无补丁可评估
    new_code = _target_code_after_patch(original_code, patch)
    # R27：透传任务上下文（跨文件物化信号）供显式分派
    task_md = getattr(task, "metadata", None) or {}
    rc = _run_pytest_in_tmp(test_cases, new_code, module_name, task_metadata=task_md)
    if rc is None:
        return None
    rc_val, out, err = rc
    if rc_val == 0:
        # F03（2026-10-21 第三方审查 P1）：gold 套件全 skip/xfail 时 rc==0，
        # 但没有任何断言通过——不能当作"补丁通过独立裁决"。记 None
        # （不可测），与 rc==5 的 fail-closed 同口径。
        if not _suite_has_effective_pass(out + "\n" + err):
            return None
        return 1.0
    if rc_val == 5:
        # R16 fail-closed：gold 材料收集到 0 个用例 = "没跑起来"，非"没修好"
        return None
    return 0.0


def _compute_false_fix_rate(task: Any, final_state: dict[str, Any] | None) -> float | None:
    """M1 假修复率（任务级布尔）：passed=True 但 gold 材料独立裁决（自动化 oracle，无人工参与）失败。

    定义：
        passed（历史口径）= True 且 repair_rate = 0.0 → 1.0（假修复）；
        否则 → 0.0。无 gold 材料 / passed 缺失 → None。

    历史主实验（20260925_135638）中 29/44 的"成功"在此指标下会暴露为
    假修复（测试在带缺陷代码上直接通过，代码未改）。
    """
    if final_state is None:
        return None
    if _is_flaky_unverified(final_state):
        # A16：执行不稳定 → passed 本身不可信，假修复率不可测（None）。
        return None
    mat = _extract_gold_material(task)
    if mat is None:
        return None
    passed = bool(final_state.get("test_passed"))
    repair_rate = _compute_repair_rate(task, final_state)
    if repair_rate is None:
        return None
    if passed and repair_rate == 0.0:
        return 1.0
    return 0.0


def _compute_regression_rate(task: Any, final_state: dict[str, Any] | None) -> float | None:
    """M1 回归率（任务级布尔）：补丁应用后 gold P2P 基线测试出现回归。

    定义（R4 独立审查 P0，2026-09-30）：
        系统生成补丁后，gold P2P（pass_to_pass）测试在**应用补丁后的代码**
        上出现"原本全过 → 现失败"的回归 → regression_rate = 1.0；
        否则（无回归 / 无补丁）→ 0.0。
        无 gold 材料 / 无 P2P 材料 / 执行超时 → None（不可测量，不误报）。

    用途：repair_rate 只看"修复是否成功"（F2P 转绿），但修复可能**破坏
    原本正确的行为**（回归）——本指标把"修复引入回归"单独报出，
    供统计层观测"过度修复 / 误删逻辑"通道（与 false_fix_rate 互补：
    假修复是"没修复却通过"，回归是"修复了但破坏其他行为"）。

    材料来源（合成数据集）：metadata["pass_to_pass"] 为 P2P 测试代码列表；
    SWE-bench / 无 P2P 材料 → None。
    """
    if final_state is None:
        return None
    if _is_flaky_unverified(final_state):
        # A16：执行不稳定 → 回归率不可测（None）。
        return None
    mat = _extract_gold_material(task)
    if mat is None:
        return None
    md = getattr(task, "metadata", None) or {}
    p2p_tests = md.get("pass_to_pass") or []
    if not p2p_tests:
        return None  # 无 P2P 材料，不可测量
    module_name = mat[0]
    original_code = str(getattr(task, "instance_code", "") or "")
    if not original_code.strip():
        return None
    patch = final_state.get("patch") or ""
    new_code = _target_code_after_patch(original_code, patch)
    # P2P 测试代码拼接（列表 → 单个测试文件）
    p2p_code = "\n\n".join(str(t) for t in p2p_tests if str(t).strip())
    if not p2p_code.strip():
        return None
    # R27：透传任务上下文（跨文件物化信号）供显式分派
    rc_patched = _run_pytest_in_tmp(p2p_code, new_code, module_name, task_metadata=md)
    if rc_patched is None:
        return None  # 超时/异常，不可测量
    rc_base = _run_pytest_in_tmp(p2p_code, original_code, module_name, task_metadata=md)
    if rc_base is None:
        return None
    # 回归 = 基线（原始代码）P2P 全过 且 补丁后 P2P 出现失败
    if rc_base[0] == 0 and rc_patched[0] != 0:
        return 1.0
    return 0.0


def _compute_llm_suite_detection_rate(task: Any, final_state: dict[str, Any] | None) -> float | None:
    """N-3：LLM-suite 检出率（语义 = ``detection_rate`` 的新口径名，显式字段）。

    与 ``_compute_detection_rate`` 完全同口径（同一实现）：生成测试含 oracle
    测试名时只跑排除 oracle 的子集；无 oracle 测试时与历史逐位一致。
    结果行同时写两个键（``detection_rate`` / ``llm_suite_detection_rate``），
    目标是让"detection_rate 的语义已收敛为 LLM-suite"在工件层显式可审计，
    并保留既有消费者零改动。
    """
    return _compute_detection_rate(task, final_state)


def _compute_oracle_suite_verdict(task: Any, final_state: dict[str, Any] | None) -> str:
    """N-3：确定性 oracle 的**独立判定**（与 LLM-suite 分开执行）。

    判定对象：生成测试里的 ``test_specir_v2_oracle`` / ``test_specir_v2_smt_witness``
    测试——用 ``-k`` 只选 oracle 测试名，在 buggy / fixed 两版代码上各跑一次。

    Returns（取值域见 ``ORACLE_SUITE_VERDICTS``）：
        - "unavailable"：未注入 oracle / 无 gold 材料 / 超时 / 收集错误 /
          单测超时（fail-closed，宁记不可判不臆测）；
        - "correct"：buggy 失败 ∧ fixed 通过（真检出）；
        - "fp"：fixed 失败（对正确实现假阳；含两侧皆失败）；
        - "silent"：两侧都通过（对该缺陷无信号）；
        - "misguided"：buggy 通过 ∧ fixed 失败（把缺陷行为断言成期望）。

    纪律：oracle 失败**不再改写** ``detection_rate``（LLM-suite 独立跑）；
    超时/收集错误单列（unavailable），不并入四分类。无 oracle 测试时
    不启动任何子进程（历史口径零成本/零行为变化）。

    O-1（2026-10-18 仪器加固）：oracle 产物自带崩溃安全 harness——fixed/buggy
    侧 TypeError 等**仪器失效**会 ``pytest.skip("oracle-unavailable: ...")``
    （rc=0 + skipped摘要），本函数经 ``_suite_run_verdict`` 把任一侧
    unavailable 记 overall "unavailable"（**不混入 fp/silent**）；只有真正的
    断言失败（rc=1）才进入 correct/fp/silent/misguided 判定。断言型失败仍保留
    （instrument 安全网不吞 AssertionError）。
    """
    if final_state is None:
        return "unavailable"
    if _is_flaky_unverified(final_state):
        # A16：执行不稳定 → oracle 独立判定同样不可测（fail-closed unavailable）。
        return "unavailable"
    mat = _extract_gold_material(task)
    if mat is None:
        return "unavailable"
    module_name, _test_cases, _fixed = mat
    generated_test = final_state.get("generated_test") or ""
    if not generated_test.strip() or not has_oracle_suite(generated_test):
        return "unavailable"
    original_code = str(getattr(task, "instance_code", "") or "")
    if not original_code.strip():
        return "unavailable"
    fixed_code = _gold_fixed_code(task)
    if not fixed_code.strip():
        return "unavailable"
    task_md = getattr(task, "metadata", None) or {}
    filter_expr = _ORACLE_SUITE_KEYWORD_FILTER
    buggy_verdict = _suite_run_verdict(
        _run_pytest_in_tmp(
            generated_test,
            original_code,
            module_name,
            task_metadata=task_md,
            keyword_filter=filter_expr,
        )
    )
    fixed_verdict = _suite_run_verdict(
        _run_pytest_in_tmp(
            generated_test,
            fixed_code,
            module_name,
            task_metadata=task_md,
            keyword_filter=filter_expr,
        )
    )
    if "unavailable" in (buggy_verdict, fixed_verdict):
        return "unavailable"
    if buggy_verdict == "fail" and fixed_verdict == "pass":
        return "correct"
    if buggy_verdict == "pass" and fixed_verdict == "fail":
        return "misguided"
    if buggy_verdict == "pass" and fixed_verdict == "pass":
        return "silent"
    return "fp"


def build_m1_task_metrics(task: Any, final_state: dict[str, Any] | None) -> dict[str, Any]:
    """M1 指标集（供 run_benchmark._build_task_result 消费）。

    返回 {"detection_rate": ..., "llm_suite_detection_rate": ...,
    "oracle_suite_verdict": ..., "repair_rate": ..., "false_fix_rate": ...,
    "test_error_rate": ..., "regression_rate": ...,
    "test_regenerated_pass_unverified": ...}。
    N-3（2026-10-17）起 detection_rate 语义收敛为 LLM-suite（与
    llm_suite_detection_rate 同值），oracle 独立判定见 oracle_suite_verdict。
    键集合同构（历史结果 JSON 结构向后兼容）：无 gold 材料时各指标均
    None；假通过标记仅 passed=True 且 regeneration_count > 0 时 True，
    否则 None。

    2026-09-30 独立审查 N1：新增 test_error_rate（测试执行错误率，
    坏测试直接防线）；detection_rate 改 F2P 三段判定。
    2026-09-30 独立审查 R4：新增 regression_rate（修复引入回归观测）。
    2026-10-18 第三方评审 A16（P1）：新增 flaky_unverified / flaky_detected
    透传键；观测到执行不稳定（fail→pass）时全部 M1 指标按不可测（None）
    处理——修复前 state.py / flaky_gate.py 只有该承诺，没有下游消费实现。
    """
    detection_rate: float | None = None
    repair_rate: float | None = None
    false_fix_rate: float | None = None
    test_error_rate: float | None = None
    regression_rate: float | None = None
    # N-3（2026-10-17）：独立判读的两键（无 oracle 注入时 detection 口径与
    # 历史逐位一致、oracle 判定为 unavailable 且零子进程成本）。
    llm_suite_detection_rate: float | None = None
    oracle_suite_verdict = "unavailable"
    # A16：flaky 标记原值透传（None = 历史批次/未启用；True = 观测到不稳定）。
    flaky_unverified: bool | None = None
    flaky_detected: bool | None = None
    if final_state is not None:
        flaky_unverified = final_state.get("flaky_unverified")
        flaky_detected = final_state.get("flaky_detected")
        detection_rate = _compute_detection_rate(task, final_state)
        llm_suite_detection_rate = detection_rate  # 同一实现/同一次判定
        oracle_suite_verdict = _compute_oracle_suite_verdict(task, final_state)
        repair_rate = _compute_repair_rate(task, final_state)
        false_fix_rate = _compute_false_fix_rate(task, final_state)
        test_error_rate = _compute_test_error_rate(task, final_state)
        regression_rate = _compute_regression_rate(task, final_state)
    test_regenerated_pass_unverified: bool | None = None
    if (
        final_state is not None
        and bool(final_state.get("test_passed"))
        and int(final_state.get("regeneration_count", 0)) > 0
        # A16：执行不稳定时"重生成后通过"同样不可信，不得记假通过标记。
        and not _is_flaky_unverified(final_state)
    ):
        test_regenerated_pass_unverified = True
    return {
        # detection_rate 语义（N-3 起）= LLM-suite（与 llm_suite_detection_rate 同值；
        # 保留既有键名供历史消费者零改动，新键用于显式审计口径）
        "detection_rate": detection_rate,
        "llm_suite_detection_rate": llm_suite_detection_rate,
        "oracle_suite_verdict": oracle_suite_verdict,
        "repair_rate": repair_rate,
        "false_fix_rate": false_fix_rate,
        "test_error_rate": test_error_rate,
        "regression_rate": regression_rate,
        "test_regenerated_pass_unverified": test_regenerated_pass_unverified,
        # A16：flaky 执行证据透传（键集合同构；历史批次为 None）
        "flaky_unverified": flaky_unverified,
        "flaky_detected": flaky_detected,
    }
