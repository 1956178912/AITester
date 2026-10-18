"""MDO：政策无关的变异判别力度量（Mutant-Discrimination Oracle metrics）。

**为什么需要本模块**（外部评审 §3.4 / 优化方案 v2 §2.3）

项目原有的 `detection_rate` 与修复策略**数学耦合**：系统用补丁把测试"改绿"后，
最终测试在缺陷原码上不再变红，该行 detection 归零（实测 `red_then_green` 93 行中
34 行因此丢失检出证据）。因此"测试生成质量"无法与"修复策略"分离度量。

本模块把判别力做成**政策无关**（policy-agnostic）的量：变异体池由确定性 AST 算子
生成、测试集在执行前冻结、判定只看**行为差异**与**断言结果**，全程不涉及任何补丁或
修复动作。

**与既有 `mutation_score` 的三点区别**（这是本模块存在的理由）

1. **不以退出码为判据**：`mutation_score` 用 `rc == 1` 判"杀死"。一个让程序
   **崩溃/抛异常**的变异体，任何写了断言的测试都会红 → 被算作"杀死"，但那是**崩溃**
   而非**断言判别力**。本模块把 `behavior`（返回值 + 异常类型 + 全局状态摘要）作为
   差异判据，并把"崩溃但无断言失败"单列为 `CRASH`，不并入 `MDR`。
2. **区分触发与判别**：`MTR`（触发：行为发生了偏差）与 `MDR`（判别：断言标记了该偏差）
   分开报告。一手依据：arXiv:2609.09315 实测"触发率 32–39% 而检出率仅 1–2%，
   原因是 test oracle 失败"——两者必须分开度量，否则无法归因。
3. **不假设池已足够**：报告**实际**池规模与"是否达判别力下限"，池过小即标
   `status="provisional_pool"`（见下方 T6 节：出口同时把 `mtr`/`mdr` 置 `None`），
   避免在饱和指标上做结论（实测存量工件 89.4% 的行
   `mutation_score == 1.0`、58.6% 的任务变异体 ≤5 个）。

**T6（2026-10-11 独立评审落地）：池未达下限时的序列化边界拦截**

实测缺陷：`compute_mdo` 在 `pool_floor_ok=False`（实测池仅 2，下限 29）时
仍输出 `mtr=1.0` / `mdr=1.0`，下游（结果行 / 报告）把这读成"判别力满分"。
修正分两层，**爆炸半径最小**：

- **属性层不变**：`MDOResult.mutant_trigger_rate` / `mutant_discrimination_rate`
  照旧写入计算值——弱/强断言判别、崩溃不计入 MDR 等**计算正确性**仍由既有
  测试直接覆盖；
- **序列化出口拦截**（`MDOResult.as_dict`）：`pool_floor_ok=False` 且可测时，
  规范键 `mtr` / `mdr` / `crash_rate` 一律输出 `None`（下游无法误读为数字），
  并新增 `mdo_provisional=True` 与 `mdo_raw={mtr, mdr, crash_rate}` 做诚实披露
  （原始值仍可审计，但不占会被按数字读取的规范键）；`status` 同时给出第三态
  `"provisional_pool"`（原只有 `"measured"` / `"not_measurable"`）。

**池规模下限的定量依据**：若某类变异体被测试杀死的概率为 `p`，要在置信度
`1-α` 下至少捕获 1 个，需 `n ≥ ln(α) / ln(1-p)`。取 `α=0.05`：
`p=10% → n≥29`，`p=5% → n≥59`。低于 29 即视为**指标饱和风险**。

**开关**：本模块为纯函数 + 子进程执行，无 LLM 调用、无默认行为变化；由调用方
显式使用（不接入主链路，先作为测量层）。
"""

# ruff: noqa: T201  （本模块 __main__ 为人工复算入口，输出用户可见结果）

from __future__ import annotations

import logging
import math
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# 池规模下限（依据见模块 docstring：n >= ln(0.05)/ln(1-p)）
POOL_FLOOR_FOR_10PCT = 29
POOL_FLOOR_FOR_5PCT = 59

# pytest 退出码语义（与 experiments/_m1_metrics.py 同口径，避免两套判据）
_RC_ASSERTION_FAILURE = 1
_RC_ALL_PASSED = 0
_RC_COLLECTION_ERROR = 2
_RC_NO_TESTS = 5

_COLLECTION_ERROR_MARKERS = (
    "errors during collection",
    "no tests were run",
    "syntaxerror",
    "error in 0.",
)


@dataclass
class MutantOutcome:
    """单个变异体的观测结果（全部为客观字段，可复算）。"""

    mutant_type: str
    description: str
    line_no: int = 0
    # 行为是否与基准实现不同（返回值 / 异常类型 / 全局状态摘要）
    divergent: bool = False
    # 测试在该变异体上是否以**断言失败**结束（rc==1）——真正的判别信号
    assertion_failed: bool = False
    # 测试在该变异体上崩溃/收集错误（rc>=2 或 5）——不得计入判别
    crashed: bool = False
    # 套件在该变异体上能否成功运行（rc in {0,1}）
    ran: bool = False
    # **行为探针不可终止**（变异体自身挂死）→ 无判别信息，须出 MDR 分母。
    # 2026-10-11 修正：此前"探针超时"被折叠为 divergent=False，导致
    # ① 非终止变异体被误算为"等价"；② 修复后又会被算成"测试未判别"。
    # 双向污染 MDR。实测触发场景：QuixBugs `bitcount` 在 Python 负数上
    # 永不终止（`n &= n-1`），其 `cond_negate` 变异体即挂死。
    non_terminating: bool = False
    baseline_behavior: str = ""
    mutant_behavior: str = ""


@dataclass
class MDOResult:
    """MDO 指标集合（政策无关）。

    `status` 三态（T6，2026-10-11 独立评审落地）：
    - `"not_measurable"`：不可测（`available=False`，附 `not_available_reason`）；
    - `"measured"`：可测且池规模达下限（`pool_floor_ok=True`），指标可出结论；
    - `"provisional_pool"`：可测但池规模未达下限——指标处于**饱和风险区**，
      不得出结论；`as_dict()` 在出口把 `mtr`/`mdr`/`crash_rate` 置 `None`
      （原始值移入 `mdo_raw` 供审计）。
    """

    available: bool = False
    not_available_reason: str = ""
    pool_size: int = 0
    pool_floor_ok: bool = False
    mutant_trigger_rate: float | None = None  # MTR：触发率
    mutant_discrimination_rate: float | None = None  # MDR：判别率
    crash_rate: float | None = None  # CRASH：崩溃-非判别率
    status: str = "not_measurable"
    outcomes: list[MutantOutcome] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """序列化为结果行字段（T6：池未达下限时在出口拦截，不误导下游）。

        历史口径（`pool_floor_ok=True` 或不可测）逐键不变；仅当
        `available and not pool_floor_ok` 时改写规范键：
        `mtr` / `mdr` / `crash_rate` → `None`，并新增 `mdo_provisional=True`
        与 `mdo_raw`（原始 MTR/MDR/CRASH 数值，仅供审计，**不占**规范键）。
        """
        payload: dict[str, Any] = {
            "mdo_available": self.available,
            "mdo_not_available_reason": self.not_available_reason,
            "mdo_pool_size": self.pool_size,
            "mdo_pool_floor_ok": self.pool_floor_ok,
            "mtr": self.mutant_trigger_rate,
            "mdr": self.mutant_discrimination_rate,
            "crash_rate": self.crash_rate,
            "mdo_status": self.status,
            "mdo_non_terminating": sum(1 for o in self.outcomes if o.non_terminating),
            "mdo_evaluable": sum(1 for o in self.outcomes if not o.non_terminating),
        }
        if self.available and not self.pool_floor_ok:
            # 池不足 → 规范键一律 None（数字出口关闭），原始值移入审计字段
            payload["mtr"] = None
            payload["mdr"] = None
            payload["crash_rate"] = None
            payload["mdo_provisional"] = True
            payload["mdo_raw"] = {
                "mtr": self.mutant_trigger_rate,
                "mdr": self.mutant_discrimination_rate,
                "crash_rate": self.crash_rate,
            }
        return payload


def pool_floor(p: float = 0.10, alpha: float = 0.05) -> int:
    """给定单变异体被杀概率 `p` 与显著性 `alpha`，返回所需最小池规模。

    `n ≥ ln(alpha) / ln(1-p)`（向上取整）。`p<=0` 或 `p>=1` 时返回哨兵值。
    """
    if not 0 < p < 1:
        raise ValueError(f"p 必须在 (0,1) 内，实际 {p}")
    if not 0 < alpha < 1:
        raise ValueError(f"alpha 必须在 (0,1) 内，实际 {alpha}")
    return math.ceil(math.log(alpha) / math.log(1 - p))


def _behavior_probe_source(module_name: str) -> str:
    """生成"行为探针"源码：导入被测模块并打印行为摘要。

    行为摘要 = 返回值 + 异常类型 + 全局状态摘要，以 JSON 单行输出供父进程比较；
    不依赖测试断言（这是"触发"的客观判据）。

    **安全输入集（2026-10-11 修正，重要）**
    --------------------------------------
    初版用 `([], [0], [1], [2], [3], [1,2], [0,0], [-1], [5], [10])` 逐个试参，
    实测在 `bitcount(n)` 上以 `n=10**9`（即上面的 `[10]` 的位数）级别输入挂死：
    `while n: n &= n-1` 循环 10 亿次 → 探针 60s 超时 → `_run_probe` 返回 None
    → 所有变异体被判"行为无偏差（等价）" → **对抗搜索完全失效**（实测
    `bitcount`/`bucketsort` 上 equiv=4/4、5/5，盲区恒为 0）。

    修正为三条硬约束：
    1. **只按签名元数调用**：用 `inspect.signature` 取参数个数，不再盲试；
    2. **输入一律小**：整数仅取 `-2..5`（含 0/1/2 等边界），序列仅取长度 ≤3；
    3. **逐调用软超时**：`signal.setitimer` 限每调用 1s（POSIX），超时即记
       `"timeout"`——**不终止**变异体（`signal.alarm` 语义；不引入外部依赖），
       且超时本身是行为差异的合法信号（不终止 vs 终止）。
    """
    return f'''
import json, sys, hashlib, inspect, signal

INT_INPUTS = (-2, -1, 0, 1, 2, 3, 5)
SEQ_INPUTS = ([], [0], [1, 2], [3, 1, 2], "", "a", "ab", "abc", {{}}, {{"a": 1}})


class _CallTimeout(Exception):
    pass


def _alarm(signum, frame):
    raise _CallTimeout()


def _state_digest(mod):
    items = []
    for name, val in sorted(vars(mod).items()):
        if name.startswith("__"):
            continue
        if isinstance(val, (int, float, str, bool)) or val is None:
            items.append([name, repr(val)[:80]])
        elif isinstance(val, (list, dict, set, tuple)):
            try:
                items.append([name, hashlib.md5(repr(val).encode()).hexdigest()[:16], len(val)])
            except Exception:
                items.append([name, "unhashable"])
    return items


def _candidates(nparams):
    """按参数个数生成小输入组合（不再盲试大值）。"""
    if nparams == 0:
        return [()]
    if nparams == 1:
        return [(v,) for v in INT_INPUTS] + [(v,) for v in SEQ_INPUTS]
    if nparams == 2:
        out = []
        for a in INT_INPUTS[:5]:
            for b in INT_INPUTS[:5]:
                out.append((a, b))
        out += [([], 0), ([1, 2], 1), ([1, 2], 2), ("ab", 1), (0, 1)]
        return out
    if nparams == 3:
        return [(0, 1, 2), (1, 2, 0), ([], 0, 1), ([1, 2], 0, 1), (0, 0, 0), (1, 1, 1)]
    return []


def _call(mod):
    results = []
    for name, fn in sorted(vars(mod).items()):
        if name.startswith("_") or not callable(fn) or inspect.isclass(fn):
            continue
        try:
            sig = inspect.signature(fn)
        except (TypeError, ValueError):
            continue
        nparams = len([p for p in sig.parameters.values()
                       if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
                       and p.default is p.empty])
        for args in _candidates(nparams):
            signal.signal(signal.SIGALRM, _alarm)
            signal.setitimer(signal.ITIMER_REAL, 1.0)
            try:
                out = fn(*args)
                results.append([name, list(map(repr, args))[:3], "ok", repr(out)[:120]])
            except _CallTimeout:
                results.append([name, list(map(repr, args))[:3], "timeout", None])
            except TypeError:
                continue
            except Exception as exc:
                results.append([name, list(map(repr, args))[:3], "exc", type(exc).__name__])
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
    return results


try:
    import {module_name} as _m
except Exception as exc:
    print(json.dumps({{"import_error": type(exc).__name__}}))
    sys.exit(0)

try:
    payload = {{"calls": _call(_m), "state": _state_digest(_m)}}
    print(json.dumps(payload, sort_keys=True))
except Exception as exc:
    print(json.dumps({{"probe_error": type(exc).__name__}}))
'''


def _run_probe(code: str, module_name: str, timeout_seconds: int) -> str | None:
    """在隔离 tmp 目录执行行为探针，返回其 stdout（失败返回 None）。"""
    tmpdir = tempfile.mkdtemp(prefix="aitester_mdo_")
    try:
        with open(os.path.join(tmpdir, f"{module_name}.py"), "w", encoding="utf-8") as f:
            f.write(code)
        probe_path = os.path.join(tmpdir, "_mdo_probe.py")
        with open(probe_path, "w", encoding="utf-8") as f:
            f.write(_behavior_probe_source(module_name))
        # A08（2026-10-18 第三方评审 P0，凭证边界）：行为探针执行的是**被测
        # 代码**（不可信）；历史实现显式 `{**os.environ, ...}` 把宿主凭证
        # （LLM_*_API_KEY / OPENAI_API_KEY / AWS_* 等）原样注入探针子进程
        # ——MDO 是评分旁路，必须与主 Executor 同口径。改用统一的最小环境
        # 构造器（最小白名单 + 探针必需 overrides）。
        from src.utils.process_utils import run_with_timeout, untrusted_exec_env

        env = untrusted_exec_env(
            PYTHONDONTWRITEBYTECODE="1",
            PYTHONPATH=tmpdir,
        )
        # 2026-10-11 全面优化批次：run_with_timeout 接线（孤儿风险消除）——
        # 行为探针执行被测代码派生的子进程（探针体内 _call），孙进程持管道
        # 写端时裸 subprocess.run(timeout=) 的 communicate 可能永久阻塞
        # （2026-10-09 批后挂死事故同构风险面）。文件后端 + 进程组 kill 保证
        # 本函数必然返回；超时 → returncode=-9 + timed_out → 走失败分支
        # （与历史 TimeoutExpired → None 同口径）。
        res = run_with_timeout(
            [sys.executable, probe_path],
            timeout=timeout_seconds,
            cwd=tmpdir,
            env=env,
        )
        if res.timed_out or res.returncode != 0:
            return None
        return (res.stdout or "").strip()
    except Exception:
        logger.debug("MDO 探针执行失败", exc_info=True)
        return None
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _run_tests_on_code(
    test_code: str,
    code: str,
    module_name: str,
    timeout_seconds: int,
) -> tuple[int, str] | None:
    """在 code 上跑测试套件，返回 (rc, output)；不可判定返回 None。"""
    tmpdir = tempfile.mkdtemp(prefix="aitester_mdo_t_")
    try:
        with open(os.path.join(tmpdir, f"{module_name}.py"), "w", encoding="utf-8") as f:
            f.write(code)
        test_path = os.path.join(tmpdir, f"test_{module_name}.py")
        with open(test_path, "w", encoding="utf-8") as f:
            f.write(test_code)
        # 2026-10-11 全面优化批次：run_with_timeout 接线——此处执行的是**LLM
        # 生成的测试套件**（pytest 可派生子进程：插件 / multiprocessing /
        # 测试内 subprocess），孙进程持管道写端时裸 subprocess.run 超时后
        # communicate 可能永久阻塞（与 M1 判分层 2026-10-11 P0-4 同构）。
        # 超时 → returncode=-9 + timed_out=True → 返回 None（fail-closed，
        # 与历史 TimeoutExpired → None 同口径）。
        # A08（2026-10-18 第三方评审 P0）：本子进程执行 LLM 生成的测试套件 +
        # 被测代码，环境必须与 M1 判分同口径最小化（凭证不进不可信子进程）。
        from src.utils.process_utils import run_with_timeout, untrusted_exec_env

        res = run_with_timeout(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "--no-header",
                "-p",
                "no:cacheprovider",
                test_path,
            ],
            timeout=timeout_seconds,
            cwd=tmpdir,
            # H 轮（2026-10-16）：剔除宿主 PYTEST_PLUGINS/PYTEST_ADDOPTS——
            # PYTHONPATH 已覆盖成 tmpdir，宿主插件在嵌套运行里不可导入会让
            # pytest 在收集前就 rc=1 退出，被读成"测试红"（与 _m1_metrics
            # 同构缺陷，实测复现见 nested_pytest_env 文档串）。
            # A08 起改走统一最小环境构造器：宿主凭证同样不进本子进程。
            env=untrusted_exec_env(
                PYTHONDONTWRITEBYTECODE="1",
                PYTHONPATH=tmpdir,
            ),
        )
        if res.timed_out:
            return None
        return res.returncode, f"{res.stdout or ''}\n{res.stderr or ''}"
    except Exception:
        return None
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _is_execution_error(rc: int, output: str) -> bool:
    """是否为"根本没跑起来"（收集/语法错误，rc>=2 或 5）。与 M1 同判据。"""
    if rc in (_RC_COLLECTION_ERROR, _RC_NO_TESTS) or rc >= 2:
        return True
    low = (output or "").lower()
    return any(marker in low for marker in _COLLECTION_ERROR_MARKERS)


def compute_mdo(
    *,
    base_code: str,
    test_code: str,
    module_name: str,
    mutants: list[Any],
    timeout_seconds: int = 30,
    pool_floor_p: float = 0.10,
) -> MDOResult:
    """计算政策无关的 MTR / MDR / CRASH。

    Args:
        base_code: 基准（可能含缺陷）实现源码。
        test_code: 待度量的生成测试套件（执行前已冻结）。
        module_name: 模块名（测试与变异体均以此名落盘）。
        mutants: 变异体列表（需有 `.code` / `.mutant_type` / `.description` / `.line_no`）。
        timeout_seconds: 单步超时。
        pool_floor_p: 池规模下限所用的单变异体被杀概率（默认 10% → 下限 29）。

    Returns:
        `MDOResult`。**不可测时 available=False 且给出原因**（不臆造 0）。
        池规模未达下限（`pool_floor_ok=False`）时 `status="provisional_pool"`，
        且 `as_dict()` 的 `mtr`/`mdr`/`crash_rate` 输出 `None`（T6 出口拦截）
        ——属性层仍保留计算值供审计与既有计算正确性测试使用。
    """
    if not (test_code or "").strip():
        return MDOResult(not_available_reason="no_test_code", status="not_measurable")
    if not (base_code or "").strip():
        return MDOResult(not_available_reason="no_base_code", status="not_measurable")
    if not mutants:
        return MDOResult(not_available_reason="empty_mutant_pool", status="not_measurable")

    # 前置：测试套件必须在基准实现上**全绿**，否则 MDR 语义不成立
    baseline_run = _run_tests_on_code(test_code, base_code, module_name, timeout_seconds)
    if baseline_run is None:
        return MDOResult(not_available_reason="baseline_timeout", status="not_measurable")
    base_rc, base_out = baseline_run
    if _is_execution_error(base_rc, base_out):
        return MDOResult(not_available_reason="baseline_execution_error", status="not_measurable")
    if base_rc != _RC_ALL_PASSED:
        return MDOResult(
            not_available_reason=f"test_not_green_on_base(rc={base_rc})",
            status="not_measurable",
        )

    base_behavior = _run_probe(base_code, module_name, timeout_seconds)

    outcomes: list[MutantOutcome] = []
    for m in mutants:
        mutant_code = str(getattr(m, "code", "") or "")
        outcome = MutantOutcome(
            mutant_type=str(getattr(m, "mutant_type", "unknown")),
            description=str(getattr(m, "description", ""))[:200],
            line_no=int(getattr(m, "line_no", 0) or 0),
        )
        if not mutant_code.strip():
            outcomes.append(outcome)
            continue

        mut_behavior = _run_probe(mutant_code, module_name, timeout_seconds)
        outcome.baseline_behavior = (base_behavior or "")[:200]
        outcome.mutant_behavior = (mut_behavior or "")[:200]
        # 探针不可终止 = 变异体自身挂死 → 无判别信息，排除出 MDR 分母
        outcome.non_terminating = mut_behavior is None and base_behavior is not None
        outcome.divergent = bool(
            base_behavior is not None and mut_behavior is not None and base_behavior != mut_behavior
        )

        run = _run_tests_on_code(test_code, mutant_code, module_name, timeout_seconds)
        if run is None:
            # 执行不可判定 → 保守：不计判别、不计崩溃，ran=False
            outcomes.append(outcome)
            continue
        rc, out = run
        if _is_execution_error(rc, out):
            outcome.crashed = True
        elif rc == _RC_ASSERTION_FAILURE:
            outcome.ran = True
            outcome.assertion_failed = True
        elif rc == _RC_ALL_PASSED:
            outcome.ran = True
        outcomes.append(outcome)

    n = len(outcomes)
    if n == 0:
        return MDOResult(not_available_reason="no_outcome", status="not_measurable")
    # MTR/MDR 的分母统一为 **可评估** 变异体（探针成功终止者）。
    # 依据：探针不可终止意味着"该变异体自身挂死"——它既不能给测试记功
    # （不是测试触发的），也不能记过（测试无从判别）。计入分母会双向污染
    # （实测：QuixBugs `cond_negate` 变异体在负数输入上永不终止，会让
    # 强断言测试的 MDR 反低于弱断言测试）。
    # MDR：分母 = **可评估**变异体（排除探针不可终止者）。否则"挂死"会被
    # 算成"测试未判别"，把变异体的缺陷记到测试头上。
    denom = [o for o in outcomes if not o.non_terminating]
    mtr = sum(1 for o in denom if o.divergent) / len(denom) if denom else None
    mdr = sum(1 for o in outcomes if o.divergent and o.assertion_failed) / len(denom) if denom else None
    crash = sum(1 for o in outcomes if o.crashed) / n
    floor = pool_floor(pool_floor_p)
    pool_ok = n >= floor
    return MDOResult(
        available=True,
        pool_size=n,
        pool_floor_ok=pool_ok,
        mutant_trigger_rate=(round(mtr, 4) if mtr is not None else None),
        # mdr 在 denom 为空（全部变异体非终止）时为 None —— round(None) 会抛错
        mutant_discrimination_rate=(round(mdr, 4) if mdr is not None else None),
        crash_rate=round(crash, 4),
        # T6（2026-10-11 独立评审落地）：池未达下限 → 第三态 "provisional_pool"
        # （饱和风险区，不得出结论）；与 as_dict 的序列化边界拦截配套。
        status="measured" if pool_ok else "provisional_pool",
        outcomes=outcomes,
    )


if __name__ == "__main__":  # pragma: no cover - 供人工复算
    import argparse
    import json
    import pathlib

    ap = argparse.ArgumentParser(description="MDO 复算（零 LLM）")
    ap.add_argument("--base", required=True, help="基准实现 .py")
    ap.add_argument("--test", required=True, help="测试套件 .py")
    ap.add_argument("--module", required=True, help="模块名")
    ap.add_argument("--max-mutants", type=int, default=100)
    args = ap.parse_args()

    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
    from experiments.mutation_testing import MutationGenerator

    base = pathlib.Path(args.base).read_text(encoding="utf-8")
    tests = pathlib.Path(args.test).read_text(encoding="utf-8")
    pool = MutationGenerator().generate(base)[: args.max_mutants]
    res = compute_mdo(
        base_code=base,
        test_code=tests,
        module_name=args.module,
        mutants=pool,
        timeout_seconds=60,
    )
    print(json.dumps(res.as_dict(), ensure_ascii=False, indent=2))
    print(f"池下限（p=10%）= {POOL_FLOOR_FOR_10PCT}；实际池 = {res.pool_size}；达下限 = {res.pool_floor_ok}")
