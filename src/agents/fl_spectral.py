"""
O2（2026-09-29 审查 P1）：Ochiai 谱系故障定位（Top-k 可算化）。
C3（2026-10-05 系统审查 P0）：修复"聚合测量 + 空 passed 集合"导致的退化。

背景：
    历史定位链路是"把失败用例 / traceback 行号塞进 prompt 让 LLM 猜"
    （O1 位置感知修复 / M6 定位），无量化排序依据——LLM 对"哪几行最
    可疑"的输出不可复核、不可消融。本模块引入经典谱系定位法
    （Ochiai / Tarantula 式）：用"同一批测试里哪些行被失败测试踩到
    而未被通过测试踩到"的命中差异，对候选行做可计算、可排序的
    可疑度打分（FL@k 指标由此可报告）。

C3 修复前（退化，2026-10-05 审查实证）：
    1. 测量层只跑一次聚合 executed_lines（无逐用例数据），
       passed_set 恒为空集 → 所有候选行 n_df=1、n_pf=0、分数恒 1.0，
       "Top-k 可疑行"退化为"文件最靠前的被执行行"；
    2. 公式层 (Ndf/sqrt(Nd))/Nd 非经典 Ochiai（随失败命中数递减，
       方向相反）。
    该退化连带使 R33 证据门的 "sbfl" 等级近乎恒放行（Top-k 必然
    "命中"靠前的补丁行）。本批次双修复：
    - 测量层：coverage dynamic_context="test_function" 逐用例上下文
      + pytest --junitxml 逐用例通过/失败裁决，一次子进程同时产出
      {测试名 → 行集合} 与 {测试名 → outcome}；
    - 公式层：经典 Ochiai susp(x) = Ndf(x) / sqrt(|F| × (Ndf(x)+Npf(x)))。

Ochiai 公式（经典谱系定位，susp ∈ [0,1]）：
    susp(x) = Ndf(x) / sqrt( |F| × (Ndf(x) + Npf(x)) )
    其中：
    - Ndf(x)：失败测试集合 F 中执行过行 x 的测试数；
    - Npf(x)：通过测试集合 P 中执行过行 x 的测试数；
    - |F|：失败测试总数。
    直觉：被失败测试大量命中、被通过测试很少命中的行可疑度趋近 1；
    被两类测试同等命中的行趋近 1/sqrt(|F|+…) 以下（弱嫌疑）；
    未被任何测试执行的行无证据（0 分，不进候选）。

数据来源（零 LLM 成本，纯数据 + subprocess 测量）：
    复用 coverage 模块对 (target_file, generated_test) 做行级独立测量
    （subprocess 同解释器，独立临时数据文件，不污染宿主 .coverage），
    dynamic_context="test_function" 使行命中按测试函数切分为上下文；
    --junitxml 提供逐用例 outcome。逐用例数据缺失时（旧版 coverage /
    上下文特性失效）保守返回 None——不产出"恒分数"假证据。

设计口径（保守、零 LLM 成本）：
    - FL_SPECTRAL_ENABLE（R8 起默认 true）由调用方 _debugger_node 决定
      是否测量；测量失败 / coverage 不可用 / 空测试 / 无法逐用例裁决
      失败集合 → fl_spectral_focus=None（保守降级，不阻断主流程）；
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
# C3：一次子进程同时产出 (a) 逐测试函数的 executed_lines 上下文
# （coverage dynamic_context="test_function"）与 (b) 逐用例 outcome
# （pytest --junitxml 解析）。两者按"测试函数名"对齐（junit name 与
# coverage 上下文标签都归一到去参数化的函数名）。
_MEASURE_SCRIPT = (
    "import json, sys, os\n"
    "from coverage import Coverage\n"
    "target = json.loads(sys.argv[1])\n"
    "test_path = sys.argv[2]\n"
    "data_file = sys.argv[3]\n"
    "out_json = sys.argv[4]\n"
    "result_file = sys.argv[5]\n"
    "junit_path = sys.argv[6]\n"
    "cov = Coverage(branch=False, data_file=data_file, config_file=False, "
    "source=[os.path.dirname(target)])\n"
    "# dynamic_context 不是构造参数（coverage 7.x TypeError），经 set_option 设置\n"
    "cov.set_option('run:dynamic_context', 'test_function')\n"
    "cov.erase()\n"
    "cov.start()\n"
    "import pytest\n"
    "pytest.main([test_path, '-q', '--tb=no', '-p', 'no:cacheprovider', '--junitxml=' + junit_path])\n"
    "cov.stop()\n"
    "cov.json_report(outfile=out_json, show_contexts=True)\n"
    "import xml.etree.ElementTree as ET\n"
    "outcome_sets = {}\n"
    "try:\n"
    "    root = ET.parse(junit_path).getroot()\n"
    "    for tc in root.iter('testcase'):\n"
    "        name = (tc.get('name') or '').split('[')[0].split('.')[-1]\n"
    "        if not name:\n"
    "            continue\n"
    "        status = 'passed'\n"
    "        for child in tc:\n"
    "            if child.tag in ('failure', 'error'):\n"
    "                status = 'failed'\n"
    "                break\n"
    "            if child.tag == 'skipped':\n"
    "                status = 'skipped'\n"
    "                break\n"
    "        outcome_sets.setdefault(name, set()).add(status)\n"
    "except Exception:\n"
    "    outcome_sets = {}\n"
    "# 同名用例多次出现（参数化归一后）取最严结果：failed > skipped > passed\n"
    "outcomes = {}\n"
    "for name, statuses in outcome_sets.items():\n"
    "    if 'failed' in statuses:\n"
    "        outcomes[name] = 'failed'\n"
    "    elif 'skipped' in statuses:\n"
    "        outcomes[name] = 'skipped'\n"
    "    else:\n"
    "        outcomes[name] = 'passed'\n"
    "with open(out_json, encoding='utf-8') as f:\n"
    "    data = json.load(f)\n"
    "target_base = os.path.basename(target)\n"
    "per_test = {}\n"
    "for fname, fdata in data.get('files', {}).items():\n"
    "    if target_base not in fname:\n"
    "        continue\n"
    "    contexts = fdata.get('contexts') or {}\n"
    "    for key, val in contexts.items():\n"
    "        if isinstance(val, dict):\n"
    "            # 旧格式：{ctx: {'executed_lines': [...]}}\n"
    "            for ctx, cdata in val.items():\n"
    "                base = str(ctx).split('[')[0].split('.')[-1].split('::')[-1]\n"
    "                if base:\n"
    "                    per_test.setdefault(base, set()).update(int(ln) for ln in cdata.get('executed_lines', []))\n"
    "        else:\n"
    "            # 新格式（coverage 7.x 实测）：{'<行号>': [ctx, ...]}\n"
    "            try:\n"
    "                ln = int(key)\n"
    "            except (TypeError, ValueError):\n"
    "                continue\n"
    "            for ctx in val or []:\n"
    "                base = str(ctx).split('[')[0].split('.')[-1].split('::')[-1]\n"
    "                if base:\n"
    "                    per_test.setdefault(base, set()).add(ln)\n"
    "result = {'outcomes': outcomes, 'per_test_lines': {k: sorted(v) for k, v in per_test.items()}}\n"
    "with open(result_file, 'w', encoding='utf-8') as f:\n"
    "    json.dump(result, f)\n"
)


def _measure_per_test_lines(
    target_file: str,
    test_code: str,
    cwd: str | None = None,
) -> dict[str, Any] | None:
    """逐测试函数测量在 target_file 上的执行行 + 逐用例 outcome。

    Returns:
        {"outcomes": {测试名: "passed"|"failed"|"skipped"},
         "per_test_lines": {测试名: [行号…]}}
        测试为空 / target_file 不存在 / coverage 不可用 / 子进程失败 /
        junit 或上下文数据缺失（逐用例裁决不可能）时返回 None。
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
    junit_path = os.path.join(tmp_dir, "junit.xml")
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
                junit_path,
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
        outcomes = parsed.get("outcomes") or {}
        per_test = parsed.get("per_test_lines") or {}
        # C3：逐用例数据缺失（旧 coverage 无 contexts / junit 解析失败）
        # → 无法区分 Ndf/Npf，保守降级 None（不产出恒分数假证据）
        if not outcomes or not per_test:
            logger.warning(
                "O2 FL_spectral 逐用例数据缺失（outcomes=%d per_test=%d），保守降级 None",
                len(outcomes),
                len(per_test),
            )
            return None
        logger.info(
            "O2 FL_spectral 逐用例测量：tests=%d（failed=%d passed=%d skipped=%d）",
            len(outcomes),
            sum(1 for v in outcomes.values() if v == "failed"),
            sum(1 for v in outcomes.values() if v == "passed"),
            sum(1 for v in outcomes.values() if v == "skipped"),
        )
        return {"outcomes": outcomes, "per_test_lines": per_test}
    except subprocess.TimeoutExpired:
        logger.warning("O2 FL_spectral 测量超时（>%ds），降级 None", _measure_timeout())
        return None
    except Exception as e:
        logger.debug("O2 FL_spectral 测量异常（保守降级 None）: %s", e)
        return None
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _ochiai_score(n_df: int, n_pf: int, total_failed: int | None = None) -> float:
    """经典 Ochiai 谱系定位公式（susp ∈ [0,1]）。

    C3（2026-10-05）：修正为经典公式 susp = Ndf / sqrt(|F| × (Ndf+Npf))。
    旧公式 (Ndf/sqrt(Nd))/Nd 随失败命中数**递减**（方向相反），已废弃。

    Args:
        n_df: 失败测试集合 F 中执行过该行的测试数。
        n_pf: 通过测试集合 P 中执行过该行的测试数。
        total_failed: 失败测试总数 |F|（None = 聚合口径，退化为
            max(1, n_df)——单"伪失败测试"二值命中时的保守口径）。

    Returns:
        Ochiai 可疑度分数。总命中数（n_df + n_pf）为 0 或 |F| 为 0 时
        返回 0.0（该行无定位证据 / 无失败测试，保守口径）。
    """
    if n_df + n_pf == 0:
        return 0.0
    # |F| 不应小于该行失败命中数（真实数据恒满足 n_df ≤ |F|；
    # 防御式钳制保证调用方传参不一致时分数仍在 [0,1]）
    total_failed = max(total_failed or 0, n_df, 1)
    return n_df / math.sqrt(total_failed * (n_df + n_pf))


def compute_ochiai_scores_from_contexts(
    failed_contexts: dict[str, set[int]] | dict[str, list[int]],
    passed_contexts: dict[str, set[int]] | dict[str, list[int]],
    all_candidate_lines: list[int] | None = None,
) -> dict[int, float]:
    """逐测试上下文口径的 Ochiai 打分（C3 修复后的主口径）。

    Args:
        failed_contexts: {失败测试名: 该测试执行过的行集合}。
        passed_contexts: {通过测试名: 该测试执行过的行集合}。
        all_candidate_lines: 候选行全集（None = 失败 ∪ 通过命中行并集；
            未被执行的行无证据，不进候选）。

    Returns:
        行号 → 经典 Ochiai 分数（susp = Ndf/sqrt(|F|×(Ndf+Npf))）。
    """
    failed_map = {k: set(v) for k, v in (failed_contexts or {}).items() if v}
    passed_map = {k: set(v) for k, v in (passed_contexts or {}).items() if v}
    if not failed_map:
        return {}
    total_failed = len(failed_map)
    if all_candidate_lines is not None:
        candidate_set = set(all_candidate_lines)
    else:
        candidate_set = set().union(*failed_map.values()) if failed_map else set()
        for lines in passed_map.values():
            candidate_set |= lines
    if not candidate_set:
        return {}
    scores: dict[int, float] = {}
    for line in candidate_set:
        n_df = sum(1 for lines in failed_map.values() if line in lines)
        n_pf = sum(1 for lines in passed_map.values() if line in lines)
        scores[line] = round(_ochiai_score(n_df, n_pf, total_failed), 6)
    return scores


def compute_ochiai_scores(
    failed_test_lines: list[int],
    passed_test_lines: list[int],
    all_candidate_lines: list[int] | None = None,
) -> dict[int, float]:
    """聚合行集合口径的 Ochiai 打分（兼容层：二值命中 + 单伪失败测试）。

    语义：failed_test_lines / passed_test_lines 是"失败 / 通过测试命中行
    的并集"，无逐用例计数 → Ndf/Npf 只能取 0/1，|F|=1。逐用例真实
    计数请用 compute_ochiai_scores_from_contexts（C3 主口径）。

    Returns:
        行号 → Ochiai 分数 的映射（分数在 [0,1] 区间）。
    """
    if not failed_test_lines:
        return {}
    failed_set = set(failed_test_lines)
    passed_set = set(passed_test_lines)
    candidate_set = set(all_candidate_lines) if all_candidate_lines is not None else (failed_set | passed_set)
    if not candidate_set:
        return {}
    scores: dict[int, float] = {}
    for line in candidate_set:
        n_df = 1 if line in failed_set else 0
        n_pf = 1 if line in passed_set else 0
        scores[line] = round(_ochiai_score(n_df, n_pf, 1), 6)
    return scores


def rank_top_k(scores: dict[int, float], k: int | None = None) -> list[dict[str, Any]]:
    """按 Ochiai 分数降序取 Top-k 可疑行（纯数据排序，零 LLM 成本）。

    分数并列时按行号升序（稳定、可复算）；k 为 None 时取全部行。

    Args:
        scores: compute_ochiai_scores(_from_contexts) 的输出（行号 → 分数）。
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
        f"【O2 谱系定位先验（FL_spectral，Top-{len(top_k)} 可疑行，Ochiai = 失败命中数 / sqrt(失败测试总数 × 总命中数)）】"
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

    实现（C3 修复后）：
    1. 一次子进程测量：coverage dynamic_context="test_function" 逐用例
       行命中 + pytest --junitxml 逐用例 outcome；
    2. 按 outcome 切分失败/通过上下文；无法逐用例裁决失败集合
       （数据缺失 / junit 全通过）时保守返回 None（不产出假证据）；
    3. 对 target_code 的 AST 可执行行与（失败 ∪ 通过）命中行求交作为
       候选全集，经典 Ochiai 打分取 Top-k（默认 5）返回。

    Args:
        target_file: 被测代码文件路径。
        target_code: 被测代码全文（用于 AST 提取可执行行号集合，
            候选全集口径；None / 空串时退化为全命中行）。
        test_code: 当前轮生成的测试代码全文。
        failed_cases: 当前轮失败用例列表（state["failed_cases"]）；
            None / 空列表时（测试全通过或无失败用例）本函数返回
            None（无定位需求，历史口径零变化）。逐用例失败集合以
            junit outcome 为准（failed_cases 仅作触发条件）。
        module_name: 被测模块名（不含 .py，仅记录用）。
        cwd: 执行目录（默认被测文件所在目录）。

    Returns:
        {"top_k": [{"line": int, "score": float}, ...],
         "total_candidates": int,
         "failed_lines": int,
         "failed_tests": int,
         "passed_tests": int,
         "target_module": str}
        或 None（无失败用例 / 测量失败 / 逐用例数据缺失时保守降级）。
    """
    if not failed_cases:
        return None
    if not test_code or not test_code.strip():
        return None
    if not target_file or not os.path.exists(target_file):
        return None

    # 1. 逐用例测量（Ndf/Npf 数据源）
    measurement = _measure_per_test_lines(target_file, test_code, cwd=cwd)
    if measurement is None:
        return None
    outcomes: dict[str, str] = measurement["outcomes"]
    per_test: dict[str, list[int]] = measurement["per_test_lines"]

    failed_contexts: dict[str, set[int]] = {}
    passed_contexts: dict[str, set[int]] = {}
    for name, lines in per_test.items():
        status = outcomes.get(name, "passed")
        if status == "failed":
            failed_contexts[name] = set(lines)
        elif status == "passed":
            passed_contexts[name] = set(lines)
        # skipped：无定位证据，两侧均不计入
    if not failed_contexts:
        logger.warning("O2 FL_spectral：junit 裁决无失败用例（与 failed_cases 输入不一致，可能 flaky），保守降级 None")
        return None

    failed_set: set[int] = set()
    for _lines in failed_contexts.values():
        failed_set |= _lines
    executed_union: set[int] = set(failed_set)
    for _lines in passed_contexts.values():
        executed_union |= _lines

    # 2. 候选行全集：target_code 的 AST 可执行行 ∩ 命中行并集
    # （无 target_code 时退化为全命中行）
    candidate_lines: list[int] | None = None
    if target_code and target_code.strip():
        try:
            import ast

            tree = ast.parse(target_code)
            ast_lines: set[int] = set()
            for node in ast.walk(tree):
                if isinstance(node, (ast.stmt, ast.expr)) and hasattr(node, "lineno"):
                    ast_lines.add(int(node.lineno))
            candidate_lines = sorted(ast_lines & executed_union)
        except (SyntaxError, ValueError):
            candidate_lines = sorted(executed_union)
    else:
        candidate_lines = sorted(executed_union)

    if not candidate_lines:
        return None

    # 3. 经典 Ochiai 打分 + Top-k 排序
    scores = compute_ochiai_scores_from_contexts(
        failed_contexts=failed_contexts,
        passed_contexts=passed_contexts,
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
        "failed_tests": len(failed_contexts),
        "passed_tests": len(passed_contexts),
        "target_module": module_name or os.path.basename(target_file),
    }
    logger.info(
        "O2 FL_spectral 定位：候选行=%d 失败测试=%d 通过测试=%d Top-%d 首行=%s（score=%.4f）",
        len(candidate_lines),
        len(failed_contexts),
        len(passed_contexts),
        k,
        top_k[0].get("line"),
        top_k[0].get("score", 0.0),
    )
    return result


__all__ = [
    "build_fl_spectral_prompt_section",
    "compute_ochiai_scores",
    "compute_ochiai_scores_from_contexts",
    "fl_spectral_enabled",
    "measure_fl_spectral_focus",
    "rank_top_k",
]
