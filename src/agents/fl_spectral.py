"""
O2（2026-09-29 审查 P1）：Ochiai 谱系故障定位（Top-k 可算化）。

背景：
    历史定位链路是"把失败用例 / traceback 行号塞进 prompt 让 LLM 猜"
    （O1 位置感知修复 / M6 定位），无量化排序依据——LLM 对"哪几行最
    可疑"的输出不可复核、不可消融。本模块引入经典谱系定位法
    （Ochiai / Tarantula 式）：用"同一批测试里哪些行被失败测试踩到
    而未被通过测试踩到"的命中差异，对候选行做可计算、可排序的
    可疑度打分（FL@k 指标由此可报告）。

Ochiai 公式（经典谱系定位，0 ∈ [0,1]）：
    susp(x) = (Ndf(x) / sqrt(Nd(x))) / (Ndf(x) + Npf(x))
    其中：
    - Ndf(x)：失败测试集合 F 中执行过行 x 的测试数；
    - Npf(x)：通过测试集合 P 中执行过行 x 的测试数；
    - Nd(x)：Ndf(x) + Npf(x)（总命中测试数）。
    直觉：被失败测试大量命中、被通过测试很少命中的行可疑度趋近 1；
    被两类测试同等命中的行趋近 0.5 以下（弱嫌疑）。

数据来源（零 LLM 成本，纯数据 + subprocess 测量）：
    复用 coverage 模块对 (target_file, generated_test) 做 branch=True
    独立测量（subprocess 同解释器，独立临时数据文件，不污染宿主
    .coverage），但本模块仅消费"行级 executed_lines"（分支维度
    已由 O3 branch_coverage_inject 覆盖，避免双份测量）。
    - 失败测试集合 F：当前轮 failed_cases（state["failed_cases"]）；
    - 通过测试集合 P：当前轮全部通过用例（test_passed=True 时全量，
      否则为空集——空 P 时 Ochiai 退化为"仅失败测试命中"排序，
      保守口径不变）。

设计口径（保守、零 LLM 成本、默认关）：
    - FL_SPECTRAL_ENABLE=false（默认）时，调用方不调本模块，历史
      口径零变化；
    - 开启时，_debugger_node 经 fl_spectral_enabled() 决定是否对
      (target_file, target_code, generated_test, failed_cases) 做
      一次 Ochiai 测量，Top-k 可疑行（默认 k=5）写入
      state["fl_spectral_focus"]；
    - _debugger_node 把 fl_spectral_focus 的 top-k 行作为"定位先验"
      注入修复 prompt（替代/补充 O1 位置感知修复的静态定位）；
    - 测量失败 / coverage 不可用 / 空测试 → fl_spectral_focus=None
      （保守降级，不阻断主流程）；
    - Docker 链路（EXECUTOR_USE_DOCKER=true）暂不支持（O16 单独
      处理容器内 JSON 报告回传），本模块本地 / venv 口径。

消费方式（纯观测层）：
    - Debugger prompt 注入：fl_spectral_focus 非空时，把"Top-k 可疑行
      （行号 + Ochiai 分数）"渲染为定位先验段落（_debugger_node 经
      build_fl_spectral_prompt_section 消费）；
    - 实验分析：experiments/ 读取 state["fl_spectral_focus"] 统计
      FL@k（真实缺陷行是否落在 Top-k）与定位消融对比。
"""

from __future__ import annotations

import json
import logging
import math
import os
import shutil
import subprocess
import sys
import tempfile
from typing import Any

logger = logging.getLogger(__name__)

_ENV = "FL_SPECTRAL_ENABLE"
_ENV_K = "FL_SPECTRAL_TOP_K"
_MEASURE_TIMEOUT = 60
_DEFAULT_TOP_K = 5


def fl_spectral_enabled() -> bool:
    """O2 开关（FL_SPECTRAL_ENABLE=true 时启用）。

    R8（2026-09-30 独立审查 N7，P1）起**默认开启**：谱系定位是零 LLM
    成本的纯数据测量（subprocess + coverage 行级 Ochiai），且是 R33
    证据门 "sbfl" 证据等级的数据源——默认关时证据门只剩 gold 一条
    强证据通道，keyword/none 写盘全被拒（修复成功率退化）。
    开启后测量失败 / coverage 不可用 / 空测试时仍保守降级（fl_spectral
    focus=None，prompt 段落为空串），不影响主流程。
    设 FL_SPECTRAL_ENABLE=false 可显式退回历史"关闭"口径
    （消融实验对照组使用）。
    """
    return os.getenv(_ENV, "true").lower() in ("true", "1", "on")


def _top_k() -> int:
    """Top-k 行数（FL_SPECTRAL_TOP_K，默认 5）。"""
    try:
        return int(os.getenv(_ENV_K, str(_DEFAULT_TOP_K)))
    except ValueError:
        return _DEFAULT_TOP_K


def _measure_timeout() -> int:
    """行级测量子进程超时（FL_SPECTRAL_TIMEOUT，默认 60s）。"""
    try:
        return int(os.getenv("FL_SPECTRAL_TIMEOUT", str(_MEASURE_TIMEOUT)))
    except ValueError:
        return _MEASURE_TIMEOUT


# 子进程测量脚本（字符串内联，避免宿主文件写权限依赖）：
# 与 O3 branch_coverage_inject 同构，但仅消费行级 executed_lines，
# 不测量分支维度（避免与 O3 双份测量开销）。
_MEASURE_SCRIPT = (
    "import json, sys, os\n"
    "from coverage import Coverage\n"
    "target = json.loads(sys.argv[1])\n"
    "test_path = sys.argv[2]\n"
    "data_file = sys.argv[3]\n"
    "out_json = sys.argv[4]\n"
    "cov = Coverage(branch=False, data_file=data_file, config_file=False, source=[os.path.dirname(target)])\n"
    "cov.erase()\n"
    "cov.start()\n"
    "import pytest\n"
    "pytest.main([test_path, '-q', '--tb=no', '-p', 'no:cacheprovider'])\n"
    "cov.stop()\n"
    "cov.json_report(outfile=out_json)\n"
    "with open(out_json, encoding='utf-8') as f:\n"
    "    data = json.load(f)\n"
    "target_base = os.path.basename(target)\n"
    "lines = set()\n"
    "for fname, fdata in data.get('files', {}).items():\n"
    "    if target_base not in fname:\n"
    "        continue\n"
    "    for ln in fdata.get('executed_lines', []):\n"
    "        lines.add(int(ln))\n"
    "with open(sys.argv[5], 'w', encoding='utf-8') as f:\n"
    "    json.dump({'executed_lines': sorted(lines)}, f)\n"
)


def _measure_executed_lines(
    target_file: str,
    test_code: str,
    cwd: str | None = None,
) -> list[int] | None:
    """测量当前测试在 target_file 上执行过的行集合（零 LLM 成本）。

    Returns:
        去重后的行号列表（升序）；测试为空 / target_file 不存在 /
        coverage 不可用 / 测量失败时返回 None（保守降级）。
    """
    if not test_code or not test_code.strip():
        return None
    if not target_file or not os.path.exists(target_file):
        return None
    try:
        import coverage  # noqa: F401
    except ImportError:
        logger.debug("O2 FL_spectral 降级：coverage 模块不可用")
        return None

    exec_dir = cwd or os.path.dirname(os.path.abspath(target_file))
    tmp_dir = tempfile.mkdtemp(prefix="aitester_fl_spectral_")
    test_path = os.path.join(tmp_dir, "test_generated.py")
    data_file = os.path.join(tmp_dir, ".coverage_data")
    out_json = os.path.join(tmp_dir, "coverage.json")
    result_file = os.path.join(tmp_dir, "result.json")
    try:
        with open(test_path, "w", encoding="utf-8") as f:
            f.write(test_code)
        # O35（2026-09-30 全面审查 P1）：改用 credential_scrub.scrub_os_environ
        # ——本子进程执行的是 **LLM 生成的测试代码**，此前 `dict(os.environ)`
        # 把 LLM_*_API_KEY / AWS_* / MYSQL_PASSWORD / DATABASE_URL 等凭证
        # 原样注入，生成代码 print 出来的环境内容会经 stdout 流回 state/日志。
        # 与 executor_runtime / runtime_probe / testless_validation 同口径
        # （白名单默认拒绝；CREDENTIAL_SCRUB_WHITELIST_ENABLE=false 时回退黑名单）。
        from src.utils.credential_scrub import scrub_os_environ

        env = scrub_os_environ()
        pp = os.pathsep.join([exec_dir, tmp_dir])
        if env.get("PYTHONPATH"):
            pp = os.pathsep.join([pp, env["PYTHONPATH"]])
        env["PYTHONPATH"] = pp
        proc = subprocess.run(
            [
                sys.executable,
                "-c",
                _MEASURE_SCRIPT,
                json.dumps(target_file),
                test_path,
                data_file,
                out_json,
                result_file,
            ],
            capture_output=True,
            text=True,
            timeout=_measure_timeout(),
            cwd=exec_dir,
            env=env,
            check=False,  # 显式声明按 returncode 判断（本仓统一口径，PLW1510）
        )
        if proc.returncode != 0 or not os.path.exists(result_file):
            logger.debug(
                "O2 FL_spectral 测量子进程失败（rc=%d）: %s",
                proc.returncode,
                (proc.stderr or "")[:300],
            )
            return None
        with open(result_file, encoding="utf-8") as f:
            parsed = json.load(f)
        lines = parsed.get("executed_lines", [])
        logger.info(
            "O2 FL_spectral 测量：执行行数=%d（target_file=%s）",
            len(lines),
            target_file,
        )
        return lines
    except subprocess.TimeoutExpired:
        logger.warning("O2 FL_spectral 测量超时（>%ds），降级 None", _measure_timeout())
        return None
    except Exception as e:
        logger.debug("O2 FL_spectral 测量异常（保守降级 None）: %s", e)
        return None
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _ochiai_score(n_df: int, n_pf: int) -> float:
    """经典 Ochiai 谱系定位公式（0 ∈ [0,1]）。

    Args:
        n_df: 失败测试集合 F 中执行过该行的测试数。
        n_pf: 通过测试集合 P 中执行过该行的测试数。

    Returns:
        Ochiai 可疑度分数。总命中数（n_df + n_pf）为 0 时返回 0.0
        （该行未被任何测试执行，无定位证据，保守口径）。
    """
    total = n_df + n_pf
    if total == 0:
        return 0.0
    return (n_df / math.sqrt(total)) / total


def compute_ochiai_scores(
    failed_test_lines: list[int],
    passed_test_lines: list[int],
    all_candidate_lines: list[int] | None = None,
) -> dict[int, float]:
    """对候选行集合计算 Ochiai 可疑度分数（纯数据，零 LLM 成本）。

    数据来源：
    - failed_test_lines：失败测试执行过的行集合（当前轮 failed_cases
      对应的 executed_lines）；
    - passed_test_lines：通过测试执行过的行集合（test_passed=True 时
      全量用例的 executed_lines；空集时 Ochiai 退化为仅失败测试命中
      排序，保守口径不变）；
    - all_candidate_lines：候选行全集（默认取失败 ∪ 通过行集合，避免
      对"从未被执行"的行打分——无证据行 Ochiai=0，排序无意义）。

    Returns:
        行号 → Ochiai 分数 的映射（分数在 [0,1] 区间）。
    """
    if not failed_test_lines:
        return {}
    failed_set = set(failed_test_lines)
    passed_set = set(passed_test_lines)
    candidate_set = set(all_candidate_lines) if all_candidate_lines else (failed_set | passed_set)
    if not candidate_set:
        return {}
    scores: dict[int, float] = {}
    for line in candidate_set:
        n_df = 1 if line in failed_set else 0
        n_pf = 1 if line in passed_set else 0
        scores[line] = round(_ochiai_score(n_df, n_pf), 6)
    return scores


def rank_top_k(scores: dict[int, float], k: int | None = None) -> list[dict[str, Any]]:
    """按 Ochiai 分数降序取 Top-k 可疑行（纯数据排序，零 LLM 成本）。

    分数并列时按行号升序（稳定、可复算）；k 为 None 时取全部行。

    Args:
        scores: compute_ochiai_scores 的输出（行号 → Ochiai 分数）。
        k: Top-k 行数（None = 全部）。

    Returns:
        [{"line": int, "score": float}, ...]（分数降序，行号升序 tie-break）。
    """
    effective_k = len(scores) if k is None else max(0, int(k))
    if effective_k == 0:
        return []
    # 按分数降序、行号升序（稳定排序，可复算）
    sorted_items = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    return [{"line": int(line), "score": float(score)} for line, score in sorted_items[:effective_k]]


def build_fl_spectral_prompt_section(fl_spectral_focus: dict[str, Any] | None) -> str:
    """把 Top-k 可疑行清单渲染为 Debugger prompt 注入段落（空时返回空串）。

    保守口径：fl_spectral_focus 为 None / top_k 为空 / 开关关时调用方
    不调本函数，prompt 与历史逐字节一致。
    """
    if not fl_spectral_focus or not fl_spectral_focus.get("top_k"):
        return ""
    top_k = fl_spectral_focus.get("top_k", [])
    lines = [
        f"【O2 谱系定位先验（FL_spectral，Top-{len(top_k)} 可疑行，Ochiai 分数 = 失败命中 / sqrt(总命中) / 总命中）】"
    ]
    lines.extend(f"- 第 {item.get('line', '?')} 行（score={item.get('score', 0.0):.4f}）" for item in top_k)
    lines.append("请优先在以上可疑行附近定位缺陷根因（而非全文件随机猜测），结合失败用例与 traceback 上下文验证。")
    return "\n".join(lines)


def measure_fl_spectral_focus(
    target_file: str,
    target_code: str,
    test_code: str,
    failed_cases: list[dict[str, Any]] | None = None,
    module_name: str = "",
    cwd: str | None = None,
) -> dict[str, Any] | None:
    """对 (target_file, test_code, failed_cases) 做 Ochiai Top-k 故障定位
    （零 LLM 成本，纯数据 + subprocess 测量）。

    实现：
    1. 用 coverage 模块（subprocess 同解释器，独立临时数据文件）对
       (target_file, test_code) 做行级测量，得到 executed_lines；
    2. 若 failed_cases 非空（当前轮有失败用例），把 executed_lines
       视为"失败测试命中行集合"（本模块不做逐用例细粒度行采集，
       以整体测试文件的 executed_lines 作为 Ndf 来源——保守口径，
       避免多轮测量开销）；
    3. 通过测试命中行集合（Npf）：当前轮 test_passed=True 时全量
       用例的 executed_lines（本模块无独立测量，保守取空集——
       空 P 时 Ochiai 退化为"仅失败测试命中"排序，与历史
       "失败用例 + traceback 定位"同方向，不引入劣化）；
    4. 对 target_code 的 AST 可执行行（行号集合）与失败命中行求交，
       计算 Ochiai 分数，取 Top-k（默认 5）返回。

    Args:
        target_file: 被测代码文件路径。
        target_code: 被测代码全文（用于 AST 提取可执行行号集合，
            候选全集口径；None / 空串时退化为全 executed_lines）。
        test_code: 当前轮生成的测试代码全文。
        failed_cases: 当前轮失败用例列表（state["failed_cases"]）；
            None / 空列表时（测试全通过或无失败用例）本函数返回
            None（无定位需求，历史口径零变化）。
        module_name: 被测模块名（不含 .py，仅记录用）。
        cwd: 执行目录（默认被测文件所在目录）。

    Returns:
        {"top_k": [{"line": int, "score": float}, ...],
         "total_candidates": int,
         "failed_lines": int,
         "target_module": str}
        或 None（无失败用例 / 测量失败 / coverage 不可用时保守降级）。
    """
    if not failed_cases:
        return None
    if not test_code or not test_code.strip():
        return None
    if not target_file or not os.path.exists(target_file):
        return None

    # 1. 测量失败测试在 target_file 上执行过的行（Ndf 来源）
    failed_lines = _measure_executed_lines(target_file, test_code, cwd=cwd)
    if not failed_lines:
        return None
    failed_set = set(failed_lines)

    # 2. 通过测试命中行集合（Npf）：当前轮全用例通过时取 executed_lines
    # （保守取空集——本模块不做逐用例细粒度行采集，避免多轮测量开销；
    # 空 P 时 Ochiai 退化为仅失败测试命中排序，与历史口径同方向）
    passed_set: set[int] = set()

    # 3. 候选行全集：target_code 的 AST 可执行行 ∩ 失败命中行
    # （无 target_code 时退化为全 failed_set）
    candidate_lines: list[int] | None = None
    if target_code and target_code.strip():
        try:
            import ast

            tree = ast.parse(target_code)
            ast_lines: set[int] = set()
            for node in ast.walk(tree):
                if isinstance(node, (ast.stmt, ast.expr)) and hasattr(node, "lineno"):
                    ast_lines.add(int(node.lineno))
            candidate_lines = sorted(ast_lines & failed_set)
        except (SyntaxError, ValueError):
            candidate_lines = sorted(failed_set)
    else:
        candidate_lines = sorted(failed_set)

    if not candidate_lines:
        return None

    # 4. Ochiai 打分 + Top-k 排序
    scores = compute_ochiai_scores(
        failed_test_lines=failed_lines,
        passed_test_lines=sorted(passed_set),
        all_candidate_lines=candidate_lines,
    )
    k = _top_k()
    top_k = rank_top_k(scores, k=k)
    if not top_k:
        return None

    result: dict[str, Any] = {
        "top_k": top_k,
        "total_candidates": len(candidate_lines),
        "failed_lines": len(failed_set),
        "target_module": module_name or os.path.basename(target_file),
    }
    logger.info(
        "O2 FL_spectral 定位：候选行=%d 失败命中行=%d Top-%d 首行=%s（score=%.4f）",
        len(candidate_lines),
        len(failed_set),
        k,
        top_k[0].get("line"),
        top_k[0].get("score", 0.0),
    )
    return result


__all__ = [
    "build_fl_spectral_prompt_section",
    "compute_ochiai_scores",
    "fl_spectral_enabled",
    "measure_fl_spectral_focus",
    "rank_top_k",
]
