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

**2026-10-19 第三方审查修复（F12 / F13，均 P1）**

- **F12：断言失败 ≠ rc==1（指标构念错误）**。历史实现把 `elif rc == 1` 一律
  标 `assertion_failed=True`——"测试无断言 + 变异体抛 ValueError"（pytest
  rc=1）也会得到 MDR（报告 §G 最小反例）。现 `_run_tests_on_code` 在 tmp
  目录落一个零依赖 `conftest.py`（`pytest_exception_interact` 钩子，未引入
  新插件依赖），把 call 阶段失败异常的**类型**写入 JSON；`compute_mdo`
  仅当"该次运行的全部 call 阶段失败均为断言型（`AssertionError` / `pytest.fail`
  的 `Failed`，含 DID NOT RAISE）"才记 `assertion_failed`；纯运行异常
  （ValueError / TypeError / ...）记 `crashed`（异常类别，MDR 不增）。
  JSON 记录缺失时回退解析 pytest `-rf` 失败摘要 / traceback 异常类型，
  且遵循保守原则：**不能证明"只有断言失败"就不计判别**（宁可不记 MDR，
  不把运行异常误记为断言判别）。
- **F13：探针不可测不得折叠为 0**。历史行为探针硬依赖
  `signal.SIGALRM` / `setitimer` / `ITIMER_REAL`；Windows 上这些 API 不存在，
  探针捕获后打印 `{"probe_error": ...}` 正常退出，父进程把该诊断当"行为
  摘要"比较 → base / mutant 摘要相同 → `divergent=False` → 池达 29 时仍
  `measured` 且 MTR/MDR=0（伪零值）。现两层修复：(a) 探针源码自带能力
  守卫，无 POSIX 定时器时打印 `{"probe_unsupported": ...}` 并退出；
  (b) `_run_probe` 校验探针 schema（必须含 `calls: list`），拒绝
  `probe_error` / `import_error` / `probe_unsupported` / 非 JSON → 返回
  None（日志区分原因）。`compute_mdo`：base 探针无效 → `not_measurable`
  （reason=`probe_unavailable`）；单个变异体探针无效 → `probe_invalid`
  排除出分母；全部无效 → 不可测，不得输出 `measured` 零值。

**开关**：本模块为纯函数 + 子进程执行，无 LLM 调用、无默认行为变化；由调用方
显式使用（不接入主链路，先作为测量层）。
"""

# ruff: noqa: T201  （本模块 __main__ 为人工复算入口，输出用户可见结果）

from __future__ import annotations

import json
import logging
import math
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Any, NamedTuple

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

# ─── F12/F13（2026-10-19 第三方审查 P1）常量 ────────────────────────────────
# 逐测试结果 JSON 文件名（由 tmp 目录内的 conftest.py 在 pytest_sessionfinish
# 写出，父进程读取；固定文件名避免额外环境变量进入不可信子进程）。
_TEST_OUTCOME_REPORT = "_mdo_test_outcomes.json"
# 失败摘要行前缀（pytest -rf）："FAILED test_t.py::test_f - TypeError: ..."
_FAILED_SUMMARY_PREFIX = "FAILED "
# 无结构化记录时的断言型失败回退标记（-rf 摘要 / traceback 异常类型）
_ASSERTION_OUTPUT_MARKERS = (
    "AssertionError",
    "Failed: ",
    "DID NOT RAISE",
)
# 探针诊断键：出现即代表"探针本身无效"，绝不能被当作行为摘要比较（F13）
_PROBE_REJECT_MARKERS = ("probe_error", "import_error", "probe_unsupported")


@dataclass(frozen=True)
class ProbeOutcome:
    """一次行为探针的判定结果（F13，2026-10-19 第三方审查 P1）。

    ``behavior`` 为**校验通过后**的规范化行为摘要（可直接跨进程比较）；
    为 None 时 ``invalid_reason`` 说明拒绝原因（probe_timeout / probe_error /
    import_error / probe_unsupported / invalid_json / missing_calls / ...）。
    ``timed_out`` 单独保留：探针超时在 MDO 语义里是"变异体自身不可终止"，
    与"探针基础设施无效"不同（前者历史上排除出分母，后者新增口径同样排除）。
    """

    behavior: str | None = None
    invalid_reason: str = ""
    timed_out: bool = False


class TestRunResult(NamedTuple):
    """一次 pytest 执行的退出码 + 输出 + 失败类型分类（F12）。

    作为 tuple 子类保留历史 ``(rc, output)`` 的下标访问（``result[0]`` /
    ``result[1]``，既有调用点零改动）；同时用命名属性承载 tmp 目录内
    conftest.py 落盘的逐测试失败类型计数：

    - ``assertion_failures``：call 阶段失败且异常为 ``AssertionError`` /
      ``Failed``（pytest.fail / DID NOT RAISE）的测试数；
    - ``runtime_errors``：call 阶段失败但异常为其他类型（ValueError 等）的测试数；
    - ``report_available``：是否读到结构化 JSON（False 时分类回退输出解析）。
    """

    rc: int
    output: str
    assertion_failures: int = 0
    runtime_errors: int = 0
    report_available: bool = False


@dataclass
class MutantOutcome:
    """单个变异体的观测结果（全部为客观字段，可复算）。"""

    mutant_type: str
    description: str
    line_no: int = 0
    # 行为是否与基准实现不同（返回值 / 异常类型 / 全局状态摘要）。
    # 探针无效（probe_invalid / non_terminating）时无从比较，保持 False。
    divergent: bool = False
    # 测试在该变异体上是否以**断言失败**结束——真正的判别信号。
    # F12（2026-10-19 第三方审查 P1）修正：不再等价于 rc==1，而要求该次
    # 运行的全部 call 阶段失败均为断言型（AssertionError / pytest 的 Failed）。
    assertion_failed: bool = False
    # 测试在该变异体上崩溃 / 异常类别，不得计入判别：
    # - rc>=2 / 5 / 负 rc：收集/编译中断、无测试、被信号终止；
    # - F12：rc==1 但失败为**纯运行异常**（ValueError / TypeError / ...）。
    crashed: bool = False
    # 套件在该变异体上能否成功运行（rc in {0,1}；F12 后含运行异常 rc==1）
    ran: bool = False
    # **行为探针不可终止**（变异体自身挂死）→ 无判别信息，须出 MDR 分母。
    # 2026-10-11 修正：此前"探针超时"被折叠为 divergent=False，导致
    # ① 非终止变异体被误算为"等价"；② 修复后又会被算成"测试未判别"。
    # 双向污染 MDR。实测触发场景：QuixBugs `bitcount` 在 Python 负数上
    # 永不终止（`n &= n-1`），其 `cond_negate` 变异体即挂死。
    non_terminating: bool = False
    # F13（2026-10-19 第三方审查 P1）：行为探针**无效**（probe_error /
    # import_error / probe_unsupported / 非 JSON / schema 不符）→ 行为不可比，
    # 排除出 MTR/MDR 分母。与 non_terminating 区分：后者是"探针正常但变异体
    # 挂死"，本字段是"探针本身没产出有效行为摘要"（如 Windows 无 SIGALRM）。
    probe_invalid: bool = False
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
            # F13：探针无效（如 Windows 无 SIGALRM）单列披露——这些变异体
            # 不进入 MTR/MDR 分母，也不得被当作"行为相同"。
            "mdo_probe_invalid": sum(1 for o in self.outcomes if o.probe_invalid),
            "mdo_evaluable": sum(1 for o in self.outcomes if not o.non_terminating and not o.probe_invalid),
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

    **平台能力守卫（F13，2026-10-19 第三方审查 P1，重要）**
    ----------------------------------------------------
    逐调用软超时依赖 POSIX 的 `SIGALRM` / `setitimer` / `ITIMER_REAL`，
    Windows 三者均不存在。历史探针在 Windows 上捕获异常后打印
    `{"probe_error": ...}` **正常退出**，父进程把该诊断当行为摘要比较
    → base / mutant 摘要相同 → 伪零值。现在探针**先**做能力探测：缺任一
    API 即打印 `{"probe_unsupported": ...}` 并退出，父进程显式拒绝该输出
    （不进入行为比较），并落不可测状态。
    """
    return f'''
import json, sys, hashlib, inspect

try:
    import signal
except Exception:
    print(json.dumps({{"probe_unsupported": "no_signal_module"}}))
    sys.exit(0)

# F13：Windows 无 SIGALRM / setitimer / ITIMER_REAL——不做能力探测就进入
# 逐调用超时逻辑只会得到 probe_error 诊断（历史"相同诊断 = 相同行为"的
# 伪零值来源）。
if not (
    hasattr(signal, "SIGALRM")
    and hasattr(signal, "setitimer")
    and hasattr(signal, "ITIMER_REAL")
):
    print(json.dumps({{"probe_unsupported": "no_posix_alarm"}}))
    sys.exit(0)

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


def _normalize_probe_output(raw: str | None) -> tuple[str | None, str]:
    """校验探针 stdout 并返回 ``(规范化行为摘要, 拒绝原因)``（F13）。

    父进程**不得**把探针诊断当行为摘要比较：Windows 上历史探针会打印
    ``{"probe_error": ...}`` 并正常退出，base / mutant 都得到同一段诊断文本
    → 被判"行为相同" → 池达下限时输出 measured 且 MTR/MDR=0 的伪零值。

    接受条件（全部满足）：
    1. 合法 JSON object（非 JSON / 空输出 → 拒绝）；
    2. 不含 ``probe_error`` / ``import_error`` / ``probe_unsupported`` 诊断键；
    3. 含 ``calls: list``（行为探针 schema；缺失说明输出不是探针产物）。

    返回的规范化摘要用 ``sort_keys`` 重排后重新序列化——同一行为必产出
    逐字节相同摘要，跨子进程比较稳定；对已是规范化 JSON 的输入幂等。

    Args:
        raw: 探针子进程 stdout（可为 None = 进程未产出）。

    Returns:
        (behavior, "") 有效；否则 (None, 拒绝原因)。
    """
    if raw is None:
        return None, "probe_not_run"
    text = str(raw).strip()
    if not text:
        return None, "empty_output"
    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        return None, "invalid_json"
    if not isinstance(payload, dict):
        return None, "non_object_payload"
    for marker in _PROBE_REJECT_MARKERS:
        if marker in payload:
            return None, marker
    calls = payload.get("calls")
    if not isinstance(calls, list):
        return None, "missing_calls"
    try:
        # `not_serializable` 实测不可达：payload 出自上方 json.loads，其值域天然可
        # 再序列化。保留作纵深防御——不要为凑覆盖伪造非 JSON 入参（ROUND4 审计）。
        normalized = json.dumps({"calls": calls, "state": payload.get("state")}, sort_keys=True)
    except (TypeError, ValueError):
        return None, "not_serializable"
    return normalized, ""


def _run_probe(
    code: str,
    module_name: str,
    timeout_seconds: int,
    *,
    outcome_sink: list[ProbeOutcome] | None = None,
) -> str | None:
    """在隔离 tmp 目录执行行为探针，返回**校验通过**的行为摘要（F13）。

    历史契约"失败返回 None"保留；F13（2026-10-19 第三方审查 P1）起 None
    还覆盖"stdout 是探针诊断（probe_error / import_error / probe_unsupported）/
    非 JSON / schema 不符"——父进程拒绝把诊断当行为摘要（历史 Windows 上
    base/mutant 都得到相同 probe_error → 伪零值）。

    Args:
        code: 被测模块源码（基准或变异体）。
        module_name: 模块名（探针 import 用）。
        timeout_seconds: 探针子进程墙钟超时。
        outcome_sink: 可选；传入 list 时把**详细判定**（ProbeOutcome：超时 /
            无效原因）追加进去，供 `compute_mdo` 区分 `non_terminating`
            与 `probe_invalid`。默认 None 时行为与历史完全一致。

    Returns:
        规范化行为摘要（合法 JSON 字符串）；无效/超时/进程异常 → None。
    """
    outcome = ProbeOutcome(invalid_reason="probe_not_run")
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
        # 本函数必然返回；超时 → returncode=-9 + timed_out → 走失败分支。
        res = run_with_timeout(
            [sys.executable, probe_path],
            timeout=timeout_seconds,
            cwd=tmpdir,
            env=env,
        )
        if res.timed_out:
            # 探针不可终止：变异体自身挂死（历史 non_terminating 语义）。
            logger.debug("MDO 行为探针超时（%ss）", timeout_seconds)
            outcome = ProbeOutcome(invalid_reason="probe_timeout", timed_out=True)
        elif res.returncode != 0:
            logger.debug("MDO 行为探针进程异常退出 rc=%s", res.returncode)
            outcome = ProbeOutcome(invalid_reason=f"probe_rc_{res.returncode}")
        else:
            behavior, reason = _normalize_probe_output(res.stdout)
            if behavior is None:
                # 父进程侧显式拒绝诊断输出：区分 probe_error / import_error /
                # probe_unsupported / invalid_json（日志可审计），绝不比较它们。
                logger.debug("MDO 行为探针输出无效（reason=%s，raw=%.200s）", reason, res.stdout)
                outcome = ProbeOutcome(invalid_reason=reason)
            else:
                outcome = ProbeOutcome(behavior=behavior)
    except Exception:
        logger.debug("MDO 探针执行失败", exc_info=True)
        outcome = ProbeOutcome(invalid_reason="probe_exception")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    if outcome_sink is not None:
        outcome_sink.append(outcome)
    return outcome.behavior


def _run_probe_detailed(code: str, module_name: str, timeout_seconds: int) -> ProbeOutcome:
    """``_run_probe`` 的详细判定包装（F13）：区分探针超时与探针无效。

    compute_mdo 需要区分"探针超时（变异体挂死 → non_terminating）"与"探针
    输出无效（probe_invalid → 排除分母）"，而 ``_run_probe`` 的公开契约
    只返回行为摘要/None；本函数通过 outcome_sink 拿详细状态。

    若 ``_run_probe`` 被替换/包裹（例如报告 §M6 反例直接把原始 probe_error
    文本传回），sink 不会被填充——此时对返回值再做一次 schema 校验，
    保证诊断输出绝不会被当行为摘要。
    """
    sink: list[ProbeOutcome] = []
    raw = _run_probe(code, module_name, timeout_seconds, outcome_sink=sink)
    if sink:
        return sink[0]
    behavior, reason = _normalize_probe_output(raw)
    if behavior is None:
        return ProbeOutcome(invalid_reason=reason)
    return ProbeOutcome(behavior=behavior)


def _test_outcome_conftest_source() -> str:
    """生成 tmp 目录内 conftest.py 源码：把逐测试失败异常**类型**落 JSON（F12）。

    设计要点（零新依赖，只用 pytest 稳定钩子）：
    - ``pytest_exception_interact(node, call, report)`` 在测试抛异常时被调用，
      ``call.excinfo`` 直接给出异常对象——不需要解析 traceback 文本；
    - 只记录 ``when == "call"`` 的阶段（setup/teardown 异常不属于"断言判别"，
      仅以 rc 体现为运行异常/执行错误）；
    - 断言型失败 = ``AssertionError``（assert 语句）或 ``Failed``
      （``pytest.fail(...)`` / ``pytest.raises`` 的 DID NOT RAISE）；
    - ``pytest_sessionfinish`` 写固定文件名（不用环境变量传路径——不可信
      子进程环境是最小白名单，自定义键不会保留）；写失败静默忽略，
      父进程以"无结构化记录"回退输出解析。
    """
    return f'''
import json
import os

import pytest

_REPORT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), {_TEST_OUTCOME_REPORT!r})
_RECORDS = []


def pytest_exception_interact(node, call, report):
    """记录 call 阶段失败异常的类名与断言型判定（F12 核心证据）。"""
    try:
        excinfo = getattr(call, "excinfo", None)
        if excinfo is None:
            return
        exc = excinfo.value
        _RECORDS.append(
            {{
                "nodeid": getattr(report, "nodeid", ""),
                "when": getattr(call, "when", ""),
                "outcome": getattr(report, "outcome", ""),
                "exception_type": type(exc).__name__,
                "is_assertion": isinstance(exc, AssertionError) or type(exc).__name__ == "Failed",
            }}
        )
    except Exception:
        pass


def pytest_sessionfinish(session, exitstatus):
    try:
        with open(_REPORT_PATH, "w", encoding="utf-8") as f:
            json.dump(_RECORDS, f)
    except Exception:
        pass
'''


def _load_test_outcome_report(path: str) -> list[dict[str, Any]] | None:
    """读取 conftest 落盘的逐测试结果 JSON；文件缺失/损坏 → None（回退解析）。"""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, list):
        return None
    return [item for item in data if isinstance(item, dict)]


def _is_assertion_failure_text(message: str) -> bool:
    """失败摘要/异常类型文本是否为断言型失败（F12 回退判据）。"""
    text = (message or "").strip()
    return text.startswith(("assert ", "AssertionError", "Failed:")) or "DID NOT RAISE" in text


def _failed_summary_messages(output: str) -> list[str]:
    """从 pytest ``-rf`` 失败摘要行提取每条失败的原因文本。

    形如 ``FAILED test_t.py::test_f - TypeError: can only concatenate ...``；
    无法解析出原因的行返回空串（调用方按"非断言"保守处理）。
    """
    messages: list[str] = []
    for line in (output or "").splitlines():
        stripped = line.strip()
        if not stripped.startswith(_FAILED_SUMMARY_PREFIX):
            continue
        body = stripped[len(_FAILED_SUMMARY_PREFIX) :]
        detail = body.split(" - ", 1)[1].strip() if " - " in body else ""
        messages.append(detail)
    return messages


def _classify_rc1_failure(run: Any) -> str:
    """判定 rc==1 的失败性质：``"assertion"`` / ``"runtime"`` / ``"unknown"``（F12）。

    优先级：
    1. **结构化证据**（conftest JSON，report_available=True）：仅当存在
       断言型失败且**没有**运行异常失败时返回 ``"assertion"``；混合失败
       或纯运行异常返回 ``"runtime"``（保守：不能证明"只有断言失败"就不
       计判别，宁可不记 MDR，不把运行异常误记为断言判别）。
    2. **回退输出解析**（无 JSON：conftest 加载失败 / 测试进程异常退出 /
       既有 mock 调用点）：解析 ``-rf`` 失败摘要；全部原因均为断言型才返回
       ``"assertion"``；无摘要行时扫 traceback 断言标记（``AssertionError`` /
       ``Failed: `` / ``DID NOT RAISE``）。

    Args:
        run: ``TestRunResult`` 或历史 ``(rc, output)`` 二元组（兼容 mock）。

    Returns:
        "assertion" 才允许记 ``assertion_failed``；"runtime"/"unknown" 记
        ``crashed``（异常类别，MDR 不增）。
    """
    assertion = getattr(run, "assertion_failures", None)
    runtime = getattr(run, "runtime_errors", None)
    if bool(getattr(run, "report_available", False)) and isinstance(assertion, int) and isinstance(runtime, int):
        if assertion > 0 and runtime == 0:
            return "assertion"
        return "runtime" if (assertion + runtime) > 0 else "unknown"
    output = str(run[1]) if isinstance(run, (tuple, list)) and len(run) > 1 else ""
    messages = _failed_summary_messages(output)
    if messages:
        return "assertion" if all(_is_assertion_failure_text(m) for m in messages) else "runtime"
    if any(marker in output for marker in _ASSERTION_OUTPUT_MARKERS):
        return "assertion"
    return "unknown"


def _run_tests_on_code(
    test_code: str,
    code: str,
    module_name: str,
    timeout_seconds: int,
) -> TestRunResult | None:
    """在 code 上跑测试套件，返回退出码 + 输出 + 失败类型分类；不可判定返回 None。

    F12（2026-10-19 第三方审查 P1）：tmp 目录额外落一个零依赖 ``conftest.py``，
    用 pytest 钩子记录 call 阶段失败异常类型（断言型 vs 运行异常）——
    历史实现只拿 ``(rc, output)`` 且把 rc==1 一律当断言失败，无断言测试
    遇到 ValueError 也会产生 MDR（报告最小反例）。

    返回 ``TestRunResult``（tuple 子类，``result[0]``/``result[1]`` 与历史
    ``(rc, output)`` 兼容）；超时 / IO 异常 → None（fail-closed）。
    """
    tmpdir = tempfile.mkdtemp(prefix="aitester_mdo_t_")
    try:
        with open(os.path.join(tmpdir, f"{module_name}.py"), "w", encoding="utf-8") as f:
            f.write(code)
        test_path = os.path.join(tmpdir, f"test_{module_name}.py")
        with open(test_path, "w", encoding="utf-8") as f:
            f.write(test_code)
        # F12：失败类型记录 conftest（无第三方依赖；--tb=short/-rf 同时给
        # 无结构化记录场景提供可解析的失败摘要）。
        with open(os.path.join(tmpdir, "conftest.py"), "w", encoding="utf-8") as f:
            f.write(_test_outcome_conftest_source())
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
                # F12：失败摘要（-rf）与短 traceback（--tb=short）供
                # "conftest JSON 缺失"时的保守回退解析。
                "--tb=short",
                "-rf",
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
        report = _load_test_outcome_report(os.path.join(tmpdir, _TEST_OUTCOME_REPORT))
        assertion_failures = 0
        runtime_errors = 0
        if report is not None:
            for record in report:
                if record.get("when") != "call" or record.get("outcome") != "failed":
                    continue
                if record.get("is_assertion"):
                    assertion_failures += 1
                else:
                    runtime_errors += 1
        return TestRunResult(
            rc=res.returncode,
            output=f"{res.stdout or ''}\n{res.stderr or ''}",
            assertion_failures=assertion_failures,
            runtime_errors=runtime_errors,
            report_available=report is not None,
        )
    except Exception:
        return None
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _is_execution_error(rc: int, output: str) -> bool:
    """是否为"根本没跑起来"（收集/语法错误、无测试、异常终止）。

    与 M1（``experiments._m1_metrics._looks_like_test_execution_error``）同判据：
    - 负 rc = 进程被信号终止（POSIX；F14 同口径）→ 异常终止，不得当断言失败；
    - rc>=2 / 5 = 收集/编译中断、无测试收集；
    - 输出含收集错误标记（兜底非标准执行器）。
    """
    if rc < 0:
        return True
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

    F12（2026-10-19 第三方审查 P1）：rc==1 不再无差别记断言判别——只有该次
    运行的失败**全部**为断言型（AssertionError / pytest.fail）才记
    `assertion_failed`；纯运行异常（ValueError 等）记 `crashed`，MDR 不增。
    F13：base 行为探针无效 → `not_measurable(reason="probe_unavailable")`；
    单个变异体探针无效 → 排除出 MTR/MDR 分母；全部无效 → 不可测。
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
    # 下标访问：兼容历史 (rc, output) 二元组 mock 与 TestRunResult（tuple 子类）
    base_rc = baseline_run[0]
    base_out = baseline_run[1]
    if _is_execution_error(base_rc, base_out):
        return MDOResult(not_available_reason="baseline_execution_error", status="not_measurable")
    if base_rc != _RC_ALL_PASSED:
        return MDOResult(
            not_available_reason=f"test_not_green_on_base(rc={base_rc})",
            status="not_measurable",
        )

    # F13（2026-10-19 第三方审查 P1）：base 行为探针必须**有效**。历史实现把
    # 探针诊断（Windows 上 {"probe_error": ...}）当行为摘要，base / mutant
    # 得到相同诊断 → divergent=False → 池达下限时 measured 且 MTR/MDR=0。
    # 现 base 探针无效即整体不可测，不输出 measured 零值。
    base_probe = _run_probe_detailed(base_code, module_name, timeout_seconds)
    if base_probe.behavior is None:
        logger.warning(
            "MDO base 行为探针无效（reason=%s）→ 不可测（不输出伪零值 MTR/MDR）",
            base_probe.invalid_reason,
        )
        return MDOResult(not_available_reason="probe_unavailable", status="not_measurable")
    base_behavior = base_probe.behavior

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

        mut_probe = _run_probe_detailed(mutant_code, module_name, timeout_seconds)
        mut_behavior = mut_probe.behavior
        outcome.baseline_behavior = base_behavior[:200]
        outcome.mutant_behavior = (mut_behavior or "")[:200]
        if mut_behavior is None:
            # F13：变异体探针无效 → 行为不可比，排除出 MTR/MDR 分母；
            # 超时（探针被 kill = 变异体自身挂死）沿用历史 non_terminating 语义。
            outcome.probe_invalid = True
            outcome.non_terminating = bool(mut_probe.timed_out)
        else:
            outcome.divergent = base_behavior != mut_behavior

        run = _run_tests_on_code(test_code, mutant_code, module_name, timeout_seconds)
        if run is None:
            # 执行不可判定 → 保守：不计判别、不计崩溃，ran=False
            outcomes.append(outcome)
            continue
        rc = run[0]
        out = run[1]
        if rc == _RC_ALL_PASSED:
            outcome.ran = True
        elif _is_execution_error(rc, out):
            # 收集/语法错误、无测试、信号终止 → CRASH，不计判别
            outcome.crashed = True
        elif rc == _RC_ASSERTION_FAILURE:
            outcome.ran = True
            # F12：rc==1 不等于断言失败——只有"全部 call 阶段失败均为断言型"
            # 才记判别；纯运行异常（ValueError 等）记 crashed（异常类别，
            # MDR 不增）。混合失败保守归运行异常。
            if _classify_rc1_failure(run) == "assertion":
                outcome.assertion_failed = True
            else:
                outcome.crashed = True
        else:
            # AA-5 核实（ROUND4 审计）：此 else **恒不触发**——rc<0 与 rc>=2 已被上面
            # ``_is_execution_error`` 收下（含 rc==3 internal / rc==4 usage / rc==5 无测试），
            # rc==0 与 rc==1 各有分支，值域无剩余。旧注释把它写成"其他非 0 退出"的处理
            # 分支是误导。保留作执行器替身返回异常 rc 时的纵深防御。
            outcome.crashed = True
        outcomes.append(outcome)

    n = len(outcomes)
    if n == 0:
        # 恒不触发：上方已对空变异体池提前返回，且循环每轮必 append 一次。
        # 保留作除零护栏（MTR/MDR 分母）。
        return MDOResult(not_available_reason="no_outcome", status="not_measurable")
    # MTR/MDR 的分母统一为 **可评估** 变异体：
    # - 排除 non_terminating（探针正常但变异体自身挂死，历史口径）；
    # - 排除 probe_invalid（F13：探针没产出有效行为摘要，行为不可比）。
    # 依据：非终止/探针无效意味着"该变异体没有有效行为证据"——它既不能
    # 给测试记功（不是测试触发的），也不能记过（测试无从判别）。计入分母
    # 会双向污染（实测：QuixBugs `cond_negate` 在负数输入上永不终止，会让
    # 强断言测试的 MDR 反低于弱断言测试）。
    denom = [o for o in outcomes if not o.non_terminating and not o.probe_invalid]
    probe_invalid_count = sum(1 for o in outcomes if o.probe_invalid)
    if not denom and probe_invalid_count > 0:
        # F13：全部变异体探针无效（如 Windows 无 SIGALRM 场景）→ 不可测，
        # 不得返回 measured 且 MTR/MDR=0 的伪零值。
        logger.warning("MDO 全部变异体行为探针无效（%d/%d）→ 不可测", probe_invalid_count, n)
        return MDOResult(
            not_available_reason="probe_unavailable",
            status="not_measurable",
            pool_size=n,
            outcomes=outcomes,
        )
    mtr = sum(1 for o in denom if o.divergent) / len(denom) if denom else None
    mdr = sum(1 for o in denom if o.divergent and o.assertion_failed) / len(denom) if denom else None
    # CRASH 率分母保持全池 n：测试执行的崩溃证据独立于"行为探针是否有效"
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
