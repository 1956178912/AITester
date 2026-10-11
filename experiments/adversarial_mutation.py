"""对抗式变异搜索（Adversarial Mutant Search, AMS）。

**定位**：这是优化方案 v2 §3.2 / P0-1 的**变异生成侧**实现——把项目现有的
**单向**变异反馈（存活变异体 → prompt）升级为**对抗式**：变异生成方持续针对
测试套件的**盲区**生产新变异体，测试方迭代精化以杀死它们。

**外部依据（均为一手核验）**

| 来源 | 一手事实 |
|---|---|
| AdverTest, ISSTA 2026（DOI 10.1145/3832122） | 测试/变异**双 agent 对抗循环**，Defects4J 上 FDR 相对最强 LLM 基线 **+8.56%**；Python（SWE-Rebench）**11/12** 检出 |
| arXiv:2607.23002（2026-07，预注册） | **机械 oracle** 下的 Critic 循环"杀死 105 个 one-shot 漏掉的变异体且未丢一个"；跨谱系 Critic 问题返回**预声明零结果** |
| arXiv:2605.22175（SWE-Mutation, ACL 2026 Findings） | agentic 变异**增强真实性**，平均检出率从 71.04% 降至 39.81%——即**算子式变异体给出虚高检出** |
| arXiv:2609.09315 | 触发与判别必须分开度量（本模块复用 MDO 的三分口径） |

**与本项目现有机制的关系**

- `experiments/mutation_testing.ExtendedMutationGenerator`：**一次性**生成全池；
- `src/graph/mutation_advisor.build_mutation_prompt_section`：把**存活**清单渲染进 prompt（单向）；
- **本模块**：在轮次之间**定向**生成——每一轮的候选变异体只在"当前测试套件无法判别"
  的方向上生产，且**仅接受真实存活的候选**（等价/被杀的候选不入池，避免虚高）。

**设计要点（可独立验证）**

1. **盲区定义客观**：候选变异体 `m` 是盲区 ⟺ `MDR({T}, {m}) == 0`，即"行为发生偏差
   但测试无断言失败"。等价变异体（行为无偏差）**不入池**——这直接规避了
   SWE-Mutation 指出的"变异真实性问题"。
2. **不引入 LLM 依赖**：本模块是纯确定的 AST 层搜索，可用 `MutationGenerator`
   的子类注入任意变异算子（含未来 LLM 变异体，只要满足 `Mutant` 协议）。
3. **零 LLM、无默认行为变化**：独立模块，不接入主链路；调用方显式使用。

用法：
    from experiments.adversarial_mutation import AdversarialMutantSearch

    ams = AdversarialMutantSearch(target_code=gold_code, module_name="bitcount")
    rounds = ams.run(test_code=suite, max_rounds=3)
    print(ams.report())
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class MutantLike(Protocol):
    """变异体协议（与 `experiments.mutation_testing.Mutant` 结构兼容）。"""

    code: str
    mutant_type: str
    description: str
    line_no: int


@dataclass
class SearchRound:
    """单轮对抗结果（全部可复算）。"""

    round_index: int
    candidates_proposed: int = 0
    survivors_accepted: int = 0
    equivalent_rejected: int = 0
    killed_by_suite: int = 0
    mtr: float | None = None
    mdr: float | None = None
    crash_rate: float | None = None
    pool_size: int = 0
    survivor_descriptions: list[str] = field(default_factory=list)


@dataclass
class AdversarialSearchResult:
    """整轮对抗的汇总。"""

    rounds: list[SearchRound] = field(default_factory=list)
    available: bool = False
    not_available_reason: str = ""

    @property
    def initial_mdr(self) -> float | None:
        """首轮 MDR（对抗前基线）。"""
        for r in self.rounds:
            if r.mdr is not None:
                return r.mdr
        return None

    @property
    def final_mdr(self) -> float | None:
        """末轮 MDR（对抗后）。"""
        for r in reversed(self.rounds):
            if r.mdr is not None:
                return r.mdr
        return None

    @property
    def mdr_delta(self) -> float | None:
        a, b = self.initial_mdr, self.final_mdr
        if a is None or b is None:
            return None
        return round(b - a, 4)

    @property
    def total_survivors_accepted(self) -> int:
        return sum(r.survivors_accepted for r in self.rounds)

    def as_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "not_available_reason": self.not_available_reason,
            "n_rounds": len(self.rounds),
            "initial_mdr": self.initial_mdr,
            "final_mdr": self.final_mdr,
            "mdr_delta": self.mdr_delta,
            "total_survivors_accepted": self.total_survivors_accepted,
            "rounds": [
                {
                    "round": r.round_index,
                    "candidates_proposed": r.candidates_proposed,
                    "survivors_accepted": r.survivors_accepted,
                    "equivalent_rejected": r.equivalent_rejected,
                    "killed_by_suite": r.killed_by_suite,
                    "mtr": r.mtr,
                    "mdr": r.mdr,
                    "crash_rate": r.crash_rate,
                    "pool_size": r.pool_size,
                    "survivors": r.survivor_descriptions,
                }
                for r in self.rounds
            ],
        }


class AdversarialMutantSearch:
    """对抗式变异搜索：定向生产"真实存活"的变异体，供测试方迭代杀死。

    Args:
        target_code: **基准实现**（应为 gold 修复后代码——MDO 的政策无关口径
            要求测试在基准上全绿）。
        module_name: 模块名（测试与变异体落盘名一致）。
        generator: 变异生成器（默认 `ExtendedMutationGenerator`；可注入
            任意满足 `MutantLike` 协议的生产者，例如未来的 LLM 变异体）。
        timeout_seconds: 单步子进程超时。
        max_pool: 每轮入池上限（存活变异体可能很多，需截断控制预算）。
    """

    def __init__(
        self,
        *,
        target_code: str,
        module_name: str,
        generator: Any = None,
        timeout_seconds: int = 30,
        max_pool: int = 60,
    ) -> None:
        if generator is None:
            from experiments.mutation_testing import ExtendedMutationGenerator

            generator = ExtendedMutationGenerator(max_per_task=max_pool * 4)
        self._code = target_code
        self._module = module_name
        self._gen = generator
        self._timeout = timeout_seconds
        self._max_pool = max_pool
        # 已接受为"真实盲区"的变异体（跨轮累积，避免重复生产）
        self._accepted: list[Any] = []
        self._accepted_codes: set[str] = set()

    # ---------- 公开 API ----------

    def propose_and_filter(self, test_code: str) -> tuple[list[Any], dict[str, int]]:
        """生产候选变异体并**按客观盲区定义过滤**。

        过滤规则（这是与"一次性全池"的本质区别）：
        - **等价变异体拒绝**：行为与基准无偏差（`divergent=False`）→ 丢弃；
        - **已被判别的拒绝**：测试以断言失败结束（`assertion_failed=True`）→ 丢弃；
        - **崩溃独立**：测试崩溃（rc>=2/5）→ 记为 `crashed`，**不入池**（不是判别力）；
        - **接受**：`divergent=True ∧ assertion_failed=False ∧ crashed=False`。

        Returns:
            (接受的变异体列表, 计数统计)
        """
        from src.measurement.mdo import compute_mdo

        candidates = list(self._gen.generate(self._code))
        # 去掉跨轮已接受过的（避免重复计入池）
        candidates = [m for m in candidates if str(getattr(m, "code", "")) not in self._accepted_codes]
        if not candidates:
            return [], {"proposed": 0, "accepted": 0, "equivalent": 0, "killed": 0, "crashed": 0}

        res = compute_mdo(
            base_code=self._code,
            test_code=test_code,
            module_name=self._module,
            mutants=candidates,
            timeout_seconds=self._timeout,
        )
        stats = {"proposed": len(candidates), "accepted": 0, "equivalent": 0, "killed": 0, "crashed": 0}
        accepted: list[Any] = []
        if not res.available:
            # 不可测（测试未全绿等）→ 不臆造盲区
            logger.info("AMS：MDO 不可测（%s），本轮不生产盲区", res.not_available_reason)
            return [], stats
        by_desc = {o.description: o for o in res.outcomes}
        for m in candidates:
            desc = str(getattr(m, "description", ""))
            o = by_desc.get(desc)
            if o is None:
                continue
            if o.crashed:
                stats["crashed"] += 1
            elif not o.divergent:
                stats["equivalent"] += 1
            elif o.assertion_failed:
                stats["killed"] += 1
            else:
                accepted.append(m)
        if len(accepted) > self._max_pool:
            accepted = accepted[: self._max_pool]
        stats["accepted"] = len(accepted)
        for m in accepted:
            code = str(getattr(m, "code", ""))
            self._accepted_codes.add(code)
        self._accepted.extend(accepted)
        return accepted, stats

    def run(self, *, test_code: str, max_rounds: int = 3) -> AdversarialSearchResult:
        """执行 `max_rounds` 轮对抗（测试代码不变；变异方逐轮逼近盲区）。

        **重要**：本方法**不修改测试**——它只测量"变异方能否持续发现新盲区"。
        测试方的精化由调用方（LLM 或人工）在轮次之间完成，然后再次调用 `run`。
        这样把"变异方能力"与"测试方能力"**解耦度量**（Adversarial Test-Hardening
        的机械 oracle 口径，arXiv:2607.23002）。
        """
        from src.measurement.mdo import compute_mdo

        out = AdversarialSearchResult()
        if not self._code.strip() or not (test_code or "").strip():
            out.not_available_reason = "no_code_or_test"
            return out
        out.available = True
        for i in range(max_rounds):
            accepted, stats = self.propose_and_filter(test_code)
            if i == 0 and not self._accepted:
                # 首轮无任何可接受候选 → 无法对抗
                out.not_available_reason = "no_surviving_mutant_found"
            # 用**已累积的全部盲区变异体**度量当前测试的判别力
            pool = self._accepted or accepted
            mtr = mdr = crash = None
            if pool:
                res = compute_mdo(
                    base_code=self._code,
                    test_code=test_code,
                    module_name=self._module,
                    mutants=pool,
                    timeout_seconds=self._timeout,
                )
                if res.available:
                    mtr, mdr, crash = res.mutant_trigger_rate, res.mutant_discrimination_rate, res.crash_rate
            out.rounds.append(
                SearchRound(
                    round_index=i,
                    candidates_proposed=stats["proposed"],
                    survivors_accepted=stats["accepted"],
                    equivalent_rejected=stats["equivalent"],
                    killed_by_suite=stats["killed"],
                    mtr=mtr,
                    mdr=mdr,
                    crash_rate=crash,
                    pool_size=len(pool),
                    survivor_descriptions=[
                        f"[{getattr(m, 'mutant_type', '?')}] {getattr(m, 'description', '')}" for m in accepted[:15]
                    ],
                )
            )
            if not accepted:
                break  # 已无新盲区可发现 → 收敛
        return out

    def build_targeting_section(self) -> str:
        """把累积盲区渲染为**测试方的定向 prompt 段落**（对抗循环的"告知"环节）。

        与 `build_mutation_prompt_section`（单向：只给存活清单）的区别：
        本段落附带**可判别的判据说明**（"该变异改变了什么行为、你的断言为何没抓到"），
        并要求测试方**只补断言、不改被测代码**——对齐 MDO 的政策无关口径。
        """
        if not self._accepted:
            return ""
        lines = [
            f"【对抗式盲区清单（AMS，共 {len(self._accepted)} 个**真实存活**变异体）】",
            "下列变异体均已机械验证：① 它们**确实改变了被调用函数的行为**（非等价变异体）；",
            "② 你当前测试套件**没有**以断言失败捕获它们；③ 它们不是崩溃（是断言盲区）。",
            "请**只补充断言**（不得修改被测代码），使测试能判别下列行为偏差：",
        ]
        for i, m in enumerate(self._accepted[:15], start=1):
            lines.append(
                f"{i}. line {getattr(m, 'line_no', 0)}｜{getattr(m, 'mutant_type', '?')}｜"
                f"{getattr(m, 'description', '')}"
            )
        lines.append(
            "对策提示：优先检查边界值（严格/非严格比较）、返回类型与长度、"
            "短路条件的真假两侧、以及异常路径是否被断言覆盖。"
        )
        return "\n".join(lines)
