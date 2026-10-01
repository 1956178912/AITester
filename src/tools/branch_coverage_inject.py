"""
O3（2026-09-29 审查 P1）：分支覆盖率注入层。

背景：
    历史执行链路仅产出标量行覆盖率（--cov-report=term 文本解析），
    "未覆盖分支" 对 Generator 不可见——迭代生成时无法针对性补充
    分支用例（边界值 / 异常路径 / 短路分支），覆盖率曲线长期
    停滞在 80% 上下。本模块把"未覆盖分支清单"变成可操作信号。

设计口径（保守、零 LLM 成本、默认关）：
    - BRANCH_COVERAGE_INJECT_ENABLE=false（默认）时，调用方不调本模块，
      历史口径零变化；
    - 开启时，_executor_node 在本地 / venv 沙箱执行完成后，用
      coverage 模块（subprocess 同解释器，独立临时数据文件，不污染
      宿主 .coverage）对 (target_file, generated_test) 做
      branch=True 的独立测量，解析 coverage.json 的 missing_branches，
      写入 state["branch_coverage"]；
    - 测量失败 / coverage 不可用 → branch_coverage=None（保守降级，
      不阻断主流程）；
    - Docker 链路（EXECUTOR_USE_DOCKER=true）暂不支持（O16 单独处理
      容器内 JSON 报告回传），本模块本地 / venv 口径。

消费方式（纯观测层）：
    - Generator prompt 注入：branch_coverage 非空时，把"未覆盖分支
      清单（行号→缺失分支端点）"渲染为提示段落（_generator_node
      经 build_branch_coverage_prompt_section 消费）；
    - 实验分析：experiments/ 读取 state["branch_coverage"] 统计
      "未覆盖分支数随迭代收敛曲线"。
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from typing import Any

logger = logging.getLogger(__name__)

_ENV = "BRANCH_COVERAGE_INJECT_ENABLE"
_MEASURE_TIMEOUT = 60  # branch 测量子进程超时（秒，默认 60）


def branch_coverage_inject_enabled() -> bool:
    """O3 开关（BRANCH_COVERAGE_INJECT_ENABLE，默认 false 历史口径）。"""
    return os.getenv(_ENV, "false").lower() in ("true", "1", "on")


def _measure_timeout() -> int:
    """branch 测量子进程超时（BRANCH_COVERAGE_INJECT_TIMEOUT，默认 60s）。"""
    try:
        return int(os.getenv("BRANCH_COVERAGE_INJECT_TIMEOUT", "60"))
    except ValueError:
        return _MEASURE_TIMEOUT


# 子进程测量脚本（字符串内联，避免宿主文件写权限依赖）：
# coverage 7.x JSON 报告口径——executed_branches / missing_branches 均为
# [[start, end], ...] 配对列表，summary.percent_branches_covered 为分支覆盖率。
_MEASURE_SCRIPT = (
    "import json, sys, os\n"
    "from coverage import Coverage\n"
    "target = json.loads(sys.argv[1])\n"
    "test_path = sys.argv[2]\n"
    "data_file = sys.argv[3]\n"
    "out_json = sys.argv[4]\n"
    "cov = Coverage(branch=True, data_file=data_file, config_file=False, source=[os.path.dirname(target)])\n"
    "cov.erase()\n"
    "cov.start()\n"
    "import pytest\n"
    "pytest.main([test_path, '-q', '--tb=no', '-p', 'no:cacheprovider'])\n"
    "cov.stop()\n"
    "cov.json_report(outfile=out_json)\n"
    "with open(out_json, encoding='utf-8') as f:\n"
    "    data = json.load(f)\n"
    "target_base = os.path.basename(target)\n"
    "tot_b = 0; tot_missing = 0; missing = []; pct = None\n"
    "for fname, fdata in data.get('files', {}).items():\n"
    "    if target_base not in fname:\n"
    "        continue\n"
    "    s = fdata.get('summary', {}) or {}\n"
    "    if s.get('num_branches'):\n"
    "        tot_b += s['num_branches']\n"
    "        tot_missing += s.get('missing_branches', 0) or 0\n"
    "        if pct is None:\n"
    "            pct = s.get('percent_branches_covered')\n"
    "    for pair in (fdata.get('missing_branches') or []):\n"
    "        if isinstance(pair, (list, tuple)) and len(pair) == 2:\n"
    "            missing.append({'line': int(pair[0]), 'to': int(pair[1])})\n"
    "result = {\n"
    "    'branch_coverage': round(pct, 2) if pct is not None else (round((tot_b - tot_missing) / tot_b * 100, 2) if tot_b else 0.0),\n"
    "    'total_branches': tot_b,\n"
    "    'covered_branches': tot_b - tot_missing,\n"
    "    'missing_branches': missing[:200],\n"
    "}\n"
    "with open(sys.argv[5], 'w', encoding='utf-8') as f:\n"
    "    json.dump(result, f)\n"
)


def measure_branch_coverage(
    target_file: str,
    test_code: str,
    module_name: str = "",
    cwd: str | None = None,
) -> dict[str, Any] | None:
    """对 (target_file, test_code) 做 branch 覆盖率测量（零 LLM 成本）。

    实现：临时目录写测试文件，subprocess 同解释器跑
    coverage(branch=True) + pytest，解析 coverage.json 的
    missing_branches。COVERAGE_FILE / 数据文件均指向临时目录，
    不污染宿主 .coverage。

    Args:
        target_file: 被测代码文件路径。
        test_code: 生成的测试代码全文。
        module_name: 被测模块名（不含 .py，仅记录用）。
        cwd: 执行目录（默认被测文件所在目录，保证 import 可解析）。

    Returns:
        {"branch_coverage": float, "missing_branches": [...],
         "total_branches": int, "covered_branches": int,
         "target_module": str}
        或 None（coverage 不可用 / 测量失败 / 空测试时保守降级）。
    """
    if not test_code or not test_code.strip():
        return None
    if not os.path.exists(target_file):
        return None
    try:
        import coverage  # noqa: F401
    except ImportError:
        logger.debug("O3 branch 测量降级：coverage 模块不可用")
        return None

    exec_dir = cwd or os.path.dirname(os.path.abspath(target_file))
    tmp_dir = tempfile.mkdtemp(prefix="aitester_branch_cov_")
    test_path = os.path.join(tmp_dir, "test_generated.py")
    data_file = os.path.join(tmp_dir, ".coverage_data")
    out_json = os.path.join(tmp_dir, "coverage.json")
    result_file = os.path.join(tmp_dir, "result.json")
    try:
        with open(test_path, "w", encoding="utf-8") as f:
            f.write(test_code)
        # O35（2026-09-30 全面审查 P1）：改用 credential_scrub.scrub_os_environ
        # ——本子进程执行 LLM 生成的测试代码，此前 `dict(os.environ)` 把
        # LLM_*_API_KEY / AWS_* / MYSQL_PASSWORD 等凭证原样注入子进程
        # （与 fl_spectral 同一漏洞面）。与 executor_runtime /
        # testless_validation 同口径：白名单默认拒绝。
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
                "O3 branch 测量子进程失败（rc=%d）: %s",
                proc.returncode,
                (proc.stderr or "")[:300],
            )
            return None
        with open(result_file, encoding="utf-8") as f:
            parsed = json.load(f)
        parsed["target_module"] = module_name or os.path.basename(target_file)
        logger.info(
            "O3 branch 测量：总分支=%d 已覆盖=%d 覆盖率=%.1f%% 未覆盖分支=%d",
            parsed.get("total_branches", 0),
            parsed.get("covered_branches", 0),
            parsed.get("branch_coverage", 0.0),
            len(parsed.get("missing_branches", [])),
        )
        return parsed
    except subprocess.TimeoutExpired:
        logger.warning("O3 branch 测量超时（>%ds），降级 None", _measure_timeout())
        return None
    except Exception as e:
        logger.debug("O3 branch 测量异常（保守降级 None）: %s", e)
        return None
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def build_branch_coverage_prompt_section(branch_coverage: dict[str, Any] | None) -> str:
    """把未覆盖分支清单渲染为 Generator prompt 注入段落（空时返回空串）。

    保守口径：branch_coverage 为 None / missing_branches 为空 / 开关关时
    调用方不调本函数，prompt 与历史逐字节一致。
    """
    if not branch_coverage or not branch_coverage.get("missing_branches"):
        return ""
    missing = branch_coverage.get("missing_branches", [])
    lines = [
        f"【未覆盖分支清单（O3，共 {len(missing)} 条，分支覆盖率 {branch_coverage.get('branch_coverage', 0.0)}%）】"
    ]
    # 按行号排序展示前 20 条（prompt token 预算保护）
    sorted_missing = sorted(missing, key=lambda m: m.get("line", 0))[:20]
    for m in sorted_missing:
        if m.get("to") is not None:
            lines.append(f"- 第 {m['line']} 行 → 第 {m['to']} 行 分支未覆盖")
        else:
            lines.append(f"- 第 {m.get('line', '?')} 行 部分分支未覆盖")
    lines.append("请优先为上述未覆盖分支补充针对性用例（边界值 / 异常路径 / 短路条件），提升分支覆盖率。")
    return "\n".join(lines)


__all__ = [
    "branch_coverage_inject_enabled",
    "build_branch_coverage_prompt_section",
    "measure_branch_coverage",
]
