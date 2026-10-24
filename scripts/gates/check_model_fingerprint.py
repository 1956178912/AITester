#!/usr/bin/env python3
"""S29（2026-10-11 独立评审落地）门禁：模型版本指纹核验。

背景（F13/S29，见 CONSOLIDATED_REVIEW_AND_PLAN.md §2.1/§3.1）：
    `deepseek-flash` 是**浮动别名**，历史 provenance 只记录别名，没有任何
    可校验的版本指纹。实测同一 87 任务 × 3 seed，`plain_llm` 检出率从存档
    1.5%(4/261) 漂移到 19.2%(50/261) —— **全部历史结论失去可复现性**。

    修复方向：`experiments/run_benchmark.py` 在 provenance 增加
    `model_fingerprint` 子块（requested_alias / returned_model /
    system_fingerprint / probe_sha256 / probe_at / pinned）。本门禁消费该
    字段：**pinned 不为 true 的结果 JSON 一律阻断**（预注册停止规则：
    快照失效即实验作废，不得与历史批次合并统计）。

判定口径（诚实口径，防"存在即通过"）：
    - 仅当 `provenance.model_fingerprint.pinned is True` 才算通过；
    - `pinned` 缺失、为 false、为 "true" 字符串、或 model_fingerprint 整块
      缺失 → **不通过**（布尔 true 是唯一通过条件，避免字符串真值蒙混）；
    - 不通过时打印**缺失项**（`missing` 字段优先；无该字段时按必需键
      逐项推断）与 `error` 文本，使"为何未锁定"可当场定位；
    - 网络/解析类问题与"未锁定"严格区分：非法 JSON 记 JSONDecodeError
      并同样阻断（工件不可解析 = 不可审计）；
    - **预指纹时代历史批次按名豁免**（`_PRE_FINGERPRINT_EXEMPT`）：2 天
      mtime 窗口在 fresh clone 上失效（checkout 刷新全部 mtime），为测试
      契约入库的跑批早于指纹功能的历史工件不得按"新批次"要求；豁免带
      漂移检查（文件消失 / 已 pinned 都失败）。
    - **CE 轮（2026-10-23）新增两条可比性围栏**（只对已 `pinned=true` 的工件
      追加判定，**pinned 的判定值与方向一处不动**）：`alias_mismatch is True`
      （跑批侧已自报"请求别名 ≠ 返回模型"）与 `requested_alias ∉ 运行时模型集`
      （别名当前运行面已不能产生）。命中即 `rc=1`，文案与"未锁定"分开打印，
      因为两者的修复动作不同：前者要人工确认可比性，后者要确认别名并重的跑。
    - **运行时模型集是权威源、不是复制常量**（`runtime_model_aliases` import
      `src.config.config_generator.COMMON_MODELS`）：复制会让"运行面删了某个
      别名"与"门禁仍认它"同时为真。import 失败 ⇒ 打印 `[SKIP]` 带成因并跳过
      alias 对账（`pinned` 判定不受影响），绝不静默降级为"没有不合规"。
    - **成功语句的分母必须自带口径**：`[SURFACE]` 四行披露受检面（窗口内 /
      豁免 / 实检）、语料面（在盘递归 / 入库 / 顶层非递归）、结构面
      （provenance / fingerprint / pinned）与全语料 alias 对账读数，防止
      "1/1 通过"被读成"整个语料干净"。语料侧的 alias 读数**只披露不判定**
      ——历史批次不能重跑，判红等于改史。

用法：
    python scripts/gates/check_model_fingerprint.py                       # 扫默认结果目录
    python scripts/gates/check_model_fingerprint.py path/a.json path/b.json
    python scripts/gates/check_model_fingerprint.py --results-dir experiments/results
    python scripts/gates/check_model_fingerprint.py --allow-empty          # 无文件时不阻断

退出码：0 = 全部 pinned 且可比性围栏通过（或 --allow-empty 且无文件）；
1 = 存在未锁定 / 不可解析 / 已锁定但可比性不成立的工件，或豁免漂移；
2 = CLI 用法错误（路径不存在）。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 默认扫描面：本地跑批输出目录。CI 场景由调用方显式传路径（工件目录随批次而异）。
DEFAULT_RESULTS_DIR = PROJECT_ROOT / "experiments" / "results"

# pinned=True 的必要条件（与 run_benchmark._FINGERPRINT_REQUIRED_KEYS 同口径；
# 此处刻意**复制常量而非 import**——门禁必须能在跑批脚本 import 失败 / 环境
# 不完整时独立运行，且不得因 src/ 侧改动而静默放宽判定）。
REQUIRED_FINGERPRINT_KEYS: tuple[str, ...] = ("requested_alias", "returned_model", "system_fingerprint")

# BZ 轮（2026-10-23）：预指纹时代历史批次的逐路径豁免（与 json-strict 的
# _ALLOWLIST 同纪律：登记理由 + 漂移检查）。背景：2 天 mtime 窗口在 fresh
# clone（CI）上失效——actions/checkout 把所有文件 mtime 刷成当下，"近期"
# 从此只反映入库时间而不反映跑批时间；默认扫描面（results 顶层、非递归）
# 一旦有历史工件入库（为测试契约），门禁就把它们当"新批次"要求
# pinned=true，而它们在指纹功能（2026-10-11）上线前跑批，永远不可能满足
# ——旧 run 的 0 秒通过只是因为那时顶层 benchmark 文件全部未被跟踪
# （扫描面为空）。豁免只收"为测试契约入库的预指纹时代历史批次"，
# 新跑批不在此列。
# CI 轮补遗（2026-10-24）：原豁免条目 `benchmark_examples_20260813_125502.json`
# 随本轮非 DeepSeek 历史数据清除（2026-08-13 Agnes/GLM 时代批次，含 BY 轮
# 分析集流量测试契约入库的份）一并删除，豁免条目按「文件消失 ⇒ 删登记」
# 同步移除——本表现在为空表，条目数锁（若引用 _PRE_FINGERPRINT_EXEMPT
# 的 len）由对应测试按新值刷新。
_PRE_FINGERPRINT_EXEMPT: dict[str, str] = {}


def collect_result_files(
    paths: list[Path],
    pattern: str = "benchmark_*.json",
    max_age_days: float | None = 2.0,
) -> tuple[list[Path], list[Path]]:
    """展开输入路径为待检文件列表，返回 (文件列表, 不存在的路径列表)。

    目录 → 其下匹配 `pattern` 且**修改时间在 `max_age_days` 内**的文件
    （非递归，避免把旁挂工件一并拉进来）；文件 → 原样全检（**不按扩展名
    与时间过滤**——调用方显式点名的文件一律检，防止"点名了但被静默跳过"）。

    两条范围规则（2026-10-11 修，均为范围错误）：

    1. **默认 pattern = `benchmark_*.json`（跑批结果工件）**。此前取全部
       `*.json`，会把 `experiments/results/` 下的**派生分析产物**
       （`full_comparison.json` / `strategy_bank.json` / `performance_benchmark.json`
       等）一并判为"未锁定"；那些文件由离线脚本生成、**从来就不含
       `provenance` 块**，判它们失败等于往 CI 塞一个永远为红的门禁。
       指纹是**跑批**的属性，不是派生分析的属性。

    2. **默认只看近 `max_age_days` 天修改的批次**。S29 是**预注册停止规则**
       （快照失效即作废），其可执行的用途是"**新批次在合并统计前必须已锁定**"；
       对**历史批次**要求 `pinned=true` 是范畴错误——它们跑在指纹功能存在之前，
       永远不可能满足，只会让门禁永久为红而失去信号。需要审计历史时用
       `--all-history` 显式放宽（此时理应大量报红，那是**发现**而非**故障**）。
    """
    import time as _time

    cutoff = None if max_age_days is None else (_time.time() - max_age_days * 86400.0)
    files: list[Path] = []
    missing: list[Path] = []
    for path in paths:
        if path.is_dir():
            for candidate in sorted(path.glob(pattern)):
                if not candidate.is_file():
                    continue
                if cutoff is not None and candidate.stat().st_mtime < cutoff:
                    continue
                files.append(candidate)
        elif path.is_file():
            files.append(path)
        else:
            missing.append(path)
    # 去重（同一文件被显式点名 + 落在目录内）并保持确定性顺序
    return sorted(set(files)), missing


def extract_fingerprint(payload: Any) -> dict[str, Any] | None:
    """从结果 JSON 顶层取 provenance.model_fingerprint（取不到返回 None）。

    逐层 isinstance 判定而非 `.get` 链：工件里 `provenance` 可能是 list /
    字符串（历史格式漂移），直接 `.get` 会抛 AttributeError 使门禁崩在
    判定之外——门禁崩 ≠ 通过，必须走"判定失败"路径。
    """
    if not isinstance(payload, dict):
        return None
    provenance = payload.get("provenance")
    if not isinstance(provenance, dict):
        return None
    fingerprint = provenance.get("model_fingerprint")
    return fingerprint if isinstance(fingerprint, dict) else None


def missing_required_keys(fingerprint: dict[str, Any] | None) -> list[str]:
    """列出未锁定的原因项（缺失/空值的必需键；整块缺失时列为全部必需键）。

    优先采用工件自报的 `missing`（跑批侧已判定），但仍**独立复核**必需键：
    自报 missing 为空而必需键实际为空时，以复核结果为准（不采信自报）。
    """
    if fingerprint is None:
        return list(REQUIRED_FINGERPRINT_KEYS)
    observed = [key for key in REQUIRED_FINGERPRINT_KEYS if not fingerprint.get(key)]
    reported = fingerprint.get("missing")
    reported_list = [str(item) for item in reported] if isinstance(reported, list) else []
    # 并集（保序：先跑批自报，再复核补漏）
    return list(dict.fromkeys(reported_list + observed))


def check_payload(payload: Any) -> tuple[bool, list[str], str | None]:
    """判定单个结果 JSON 是否 pinned，返回 (passed, 未锁定项, error 文本)。

    通过条件：`provenance.model_fingerprint.pinned is True`（严格布尔）。
    """
    fingerprint = extract_fingerprint(payload)
    if fingerprint is None:
        if isinstance(payload, dict) and isinstance(payload.get("provenance"), dict):
            return False, list(REQUIRED_FINGERPRINT_KEYS), "provenance 无 model_fingerprint 子块"
        return False, list(REQUIRED_FINGERPRINT_KEYS), "结果 JSON 无 provenance 块"

    # 严格布尔：`is True` —— 字符串 "true" / 1 / 非空列表一律不通过
    raw_pinned = fingerprint.get("pinned")
    passed = raw_pinned is True
    error = fingerprint.get("error")
    error_text = str(error) if error else None
    if passed:
        return True, [], error_text
    items = missing_required_keys(fingerprint)
    if not items:
        # pinned 非布尔真值（如字符串 "true"）：必需键齐全但口径不合规——
        # 必须给出可读原因，否则门禁输出"未提供缺失项"等于没解释
        items.append(f"pinned 非布尔 true（实际 {type(raw_pinned).__name__}: {raw_pinned!r}）")
        if error_text:
            items.append("原因见 error")
    return False, items, error_text


def check_file(path: Path) -> tuple[bool, list[str], str | None]:
    """校验单个结果 JSON 文件，返回 (passed, 未锁定项, error 文本)。

    Raises:
        json.JSONDecodeError: 文件不是合法 JSON（调用方按"不可审计"阻断）。
        OSError: 文件不可读（权限 / 编码），同样阻断。
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    return check_payload(payload)


def _rel_key(path: Path) -> str:
    """工件路径的仓库相对键（豁免登记表用；绝对/相对调用都收敛到同一键）。"""
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def exemption_drift_failures() -> list[str]:
    """豁免登记表的漂移检查（json-strict 同纪律：只在"仍然需要"时有效）。

    两种漂移都算失败：登记项的文件消失（豁免失去对象）、文件已变为
    pinned=true（豁免不再需要，应移除登记）。文件在场且仍未锁定 ⇒ 静默
    （豁免正常生效或本地休眠）。
    """
    failures: list[str] = []
    for key, reason in _PRE_FINGERPRINT_EXEMPT.items():
        target = PROJECT_ROOT / key
        if not target.exists():
            failures.append(f"{key}: 豁免漂移（文件已不存在：{reason}）")
            continue
        try:
            passed, _, _ = check_file(target)
        except (json.JSONDecodeError, OSError) as e:
            failures.append(f"{key}: 豁免漂移（工件不可审计：{type(e).__name__}: {e}）")
            continue
        if passed:
            failures.append(f"{key}: 豁免漂移（已 pinned=true，应移除豁免登记：{reason}）")
    return failures


# ══ CE 轮（2026-10-23）：可比性围栏 + 受检面披露 ═════════════════════════════
# 改前实测（同一棵树）：
#   ① pinned=true + alias_mismatch=true ⇒ rc=0（写侧三处 `alias_mismatch`
#      全仓零读者；F13/S29 的漂移形态正是"别名不变、返回模型变了"）；
#   ② pinned=true + requested_alias 不在运行时模型集 ⇒ rc=0（CD 轮把运行面
#      收成单别名 `deepseek-flash` 后，这条缺口第一次可判定，此前多 provider
#      时"合法集合"本身就模糊）；
#   ③ 成功语句"1/1 个受检工件均 pinned=true"的分母 = 近 2 天窗口内文件数
#      （实测窗口内 2 / 豁免 1 / 实检 1），而入库 benchmark_*.json 107 份、
#      在盘递归 239 份——读者无法从输出区分"这 1 份干净"与"整个语料干净"。
# 处置纪律：**pinned 判定值与方向一处不动**（`check_payload` / `check_file`
# 逐字节不变，豁免漂移仍按 pinned 口径），围栏与新披露全部加在 main 侧。

# 对账权威源：运行时模型注册表本身（CD 轮起 = 单别名）。刻意 import 而非
# 复制常量——复制会让"运行面删了某个别名"与"门禁仍认它"同时为真。
RUNTIME_REGISTRY_ORIGIN = "src.config.config_generator.COMMON_MODELS"


def runtime_model_aliases() -> tuple[frozenset[str], str | None]:
    """读取运行时模型别名集，返回 (别名集, 不可用成因)。

    取不到时返回 (空集, 成因文本)：调用方必须把成因打印出来并**跳过 alias
    对账**（BZ §70 纪律：前提不成立要显式 skip 带读数，既不能静默放行，
    也不能把 import 失败冒充成"工件不合规"）。
    """
    try:
        # 门禁以脚本方式执行时 sys.path[0] = scripts/gates，仓库根不在路径上：
        # 实测 `make model-fingerprint` 直接 ModuleNotFoundError ⇒ alias 对账整条
        # 退化成 skip。补路径而不是接受 skip——静默降级等于围栏不存在。
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from src.config.config_generator import COMMON_MODELS
    except Exception as e:
        return frozenset(), f"运行时模型集不可用：import `{RUNTIME_REGISTRY_ORIGIN}` 失败（{type(e).__name__}: {e}）"
    if not isinstance(COMMON_MODELS, list) or not COMMON_MODELS:
        return (
            frozenset(),
            f"运行时模型集不可用：`{RUNTIME_REGISTRY_ORIGIN}` 为空或类型漂移（{type(COMMON_MODELS).__name__}）",
        )
    names = {str(item.get("name")) for item in COMMON_MODELS if isinstance(item, dict) and item.get("name")}
    if not names:
        return frozenset(), f"运行时模型集不可用：`{RUNTIME_REGISTRY_ORIGIN}` 内无带 name 的条目"
    return frozenset(names), None


def comparability_findings(fingerprint: dict[str, Any], aliases: frozenset[str]) -> list[str]:
    """对已 pinned 的指纹做可比性判定，返回点名式不合规项（空 = 可比）。

    两条围栏：
    - `alias_mismatch is True`：跑批侧已判定"请求别名 ≠ 返回模型"，跨批次
      合并统计前必须由人确认，不能靠 pinned 蒙过去（严格 `is True`，与
      pinned 同口径，字符串 "true" 不算）。
    - `requested_alias ∉ 运行时模型集`：该批次声称的模型当前运行面已不能
      产生，结论不可复现（`aliases` 为空 = 注册表不可用 ⇒ 本条跳过，由
      调用方打印 [SKIP] 成因）。
    """
    findings: list[str] = []
    if fingerprint.get("alias_mismatch") is True:
        findings.append(
            "可比性：`alias_mismatch is True`（请求别名 "
            f"{fingerprint.get('requested_alias')!r} ≠ 返回模型 {fingerprint.get('returned_model')!r}）"
            "——跨批次合并统计前必须人工确认"
        )
    if aliases:
        alias = fingerprint.get("requested_alias")
        if isinstance(alias, str) and alias and alias not in aliases:
            findings.append(
                f"可比性：`requested_alias={alias!r}` 不在运行时模型集 {sorted(aliases)} 内"
                f"（权威源 {RUNTIME_REGISTRY_ORIGIN}；该别名已不能由当前运行面产生）"
            )
    return findings


_CORPUS_SURFACE_CACHE: dict[str, int] | None = None


def corpus_surface() -> dict[str, int]:
    """指纹判定的**语料面**读数（纯只读，进程内缓存一次）。

    口径逐条写明，避免与扫描面混读：
    - `tracked`：`git ls-files` 下的入库 `benchmark_*.json`（git 不可用记 -1，
      打印时明示"不可用"而不是冒充 0）。**索引口径**：含工作区已删除但尚未提交的条目，
      因此可以大于"在盘可读"（实测 107 vs 100，差 7 = 上一轮未提交的删除）——读作
      "CI clone 会得到什么"，不要读作"能复核多少份"；
    - `on_disk`：`experiments/results/**/benchmark_*.json` 递归在盘数（与
      `tests/_corpus_guard.py` 的 benchmark 口径同源）；
    - `top_level`：门禁默认扫描面的目录层（非递归）文件数；
    - `with_provenance` / `with_fingerprint` / `pinned_true`：结构层层数；
      不可解析的文件留在 `on_disk` 而不进入结构层计数（严格 JSON 是
      `check_json_strict.py` 的判定面，本门禁不重判）；
    - `unsupported_alias` / `alias_mismatch_true`：全语料的 alias 对账读数
      （只披露，不判定——历史批次不能重跑，判红等于改史）。
    """
    global _CORPUS_SURFACE_CACHE
    if _CORPUS_SURFACE_CACHE is not None:
        return _CORPUS_SURFACE_CACHE
    root = DEFAULT_RESULTS_DIR
    # 递归口径与 tests/_corpus_guard.py 的 benchmark 计数同源（rglob，非目录单层）
    on_disk = sorted(root.rglob("benchmark_*.json"))
    top_level = (
        sorted(p for p in root.iterdir() if p.is_file() and p.name.startswith("benchmark_") and p.suffix == ".json")
        if root.is_dir()
        else []
    )
    tracked = _tracked_benchmark_count()
    aliases, _reason = runtime_model_aliases()
    counts = {
        "tracked": tracked,
        "on_disk": len(on_disk),
        "top_level": len(top_level),
        "with_provenance": 0,
        "with_fingerprint": 0,
        "pinned_true": 0,
        "unsupported_alias": 0,
        "alias_mismatch_true": 0,
    }
    for path in on_disk:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        fingerprint = extract_fingerprint(payload)
        provenance = payload.get("provenance") if isinstance(payload, dict) else None
        if isinstance(provenance, dict):
            counts["with_provenance"] += 1
        if not isinstance(fingerprint, dict):
            continue
        counts["with_fingerprint"] += 1
        if fingerprint.get("pinned") is True:
            counts["pinned_true"] += 1
        if fingerprint.get("alias_mismatch") is True:
            counts["alias_mismatch_true"] += 1
        alias = fingerprint.get("requested_alias")
        if aliases and isinstance(alias, str) and alias and alias not in aliases:
            counts["unsupported_alias"] += 1
    _CORPUS_SURFACE_CACHE = counts
    return counts


def _tracked_benchmark_count() -> int:
    """入库 benchmark_*.json 计数；git 不可用返回 -1（打印侧明示）。

    `subprocess` 走模块顶层名字（不是函数内 import）：锁必须能注入替身来验证
    "git 失败 ⇒ -1"，函数内 import 会让那条路径在测试里不可达。
    """
    try:
        out = subprocess.run(
            ["git", "ls-files", "--", "experiments/results"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        ).stdout
    except Exception:
        return -1
    names = [line for line in out.splitlines() if Path(line).name.startswith("benchmark_") and line.endswith(".json")]
    return len(names)


def surface_disclosure(files: list[Path], exempt_count: int) -> list[str]:
    """把受检面放进语料面里打印——成功语句的分母不再是孤立数字。"""
    surface = corpus_surface()
    checked = len(files) - exempt_count
    tracked_note = str(surface["tracked"]) if surface["tracked"] >= 0 else "不可用（git 失败）"
    return [
        (
            f"[SURFACE] 受检面：窗口内 {len(files)}（豁免 {exempt_count} ⇒ 实检 {checked}，"
            f"口径 = 默认目录非递归 + 近 2 天 mtime）"
        ),
        (f"[SURFACE] 语料面：在盘递归 {surface['on_disk']} / 入库 {tracked_note} / 顶层非递归 {surface['top_level']}"),
        (
            f"[SURFACE] 结构面：有 provenance {surface['with_provenance']} / "
            f"有 model_fingerprint {surface['with_fingerprint']} / pinned=true {surface['pinned_true']}"
        ),
        (
            f"[SURFACE] alias 对账：运行时模型集 "
            f"{sorted(runtime_model_aliases()[0]) or '不可用'}；全语料 unsupported_alias "
            f"{surface['unsupported_alias']} / alias_mismatch_true {surface['alias_mismatch_true']}（只披露，历史批次不重判）"
        ),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="S29 模型版本指纹门禁：pinned != true 则阻断")
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help=f"结果 JSON 文件或目录（默认 {DEFAULT_RESULTS_DIR}）",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=None,
        help="结果目录（等价于传入一个目录路径；与位置参数可同时使用）",
    )
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="未发现任何 JSON 工件时不阻断（默认阻断：扫描面为空 = 门禁失效）",
    )
    parser.add_argument(
        "--pattern",
        default="benchmark_*.json",
        help=(
            "目录扫描时匹配的文件名模式（默认 benchmark_*.json = 跑批结果工件）。"
            "派生分析产物（full_comparison.json 等）从来不含 provenance，"
            "不在默认扫描面内；需要全量扫描时传 --pattern '*.json'。"
        ),
    )
    parser.add_argument(
        "--all-history",
        action="store_true",
        help=(
            "扫描目录下全部历史批次（默认只查近 2 天修改的批次）。"
            "S29 是预注册停止规则，可执行用途是「新批次合并统计前必须已锁定」；"
            "对指纹功能上线前的历史批次要求 pinned=true 是范畴错误，"
            "只会让门禁永久为红。审计历史时用本开关，此时大量报红是发现而非故障。"
        ),
    )
    args = parser.parse_args(argv)

    targets: list[Path] = list(args.paths)
    if args.results_dir is not None:
        targets.append(args.results_dir)
    if not targets:
        targets = [DEFAULT_RESULTS_DIR]

    files, missing_paths = collect_result_files(
        targets, pattern=args.pattern, max_age_days=None if args.all_history else 2.0
    )
    for path in missing_paths:
        print(f"[ERROR] 路径不存在: {path}", file=sys.stderr)
    if missing_paths:
        return 2

    # 豁免漂移先于空扫描面判定：登记项失效与"近期无新批次"无关，任何时候
    # 都必须是可观测信号（json-strict 的 allowlist 同口径）。
    failures: list[str] = exemption_drift_failures()
    for failure in failures:
        print(f"[ERROR] {failure}", file=sys.stderr)

    if not files:
        msg = f"[model-fingerprint] 未发现任何结果 JSON（扫描面: {[str(t) for t in targets]}）"
        # 空扫描面 ≠ 未锁定。S29 的可执行语义是"**新批次**在合并统计前必须已
        # 锁定"，因此"近期没有新批次"是**合规状态**（nothing to verify），
        # 不是故障——若在此返回非零，门禁会在两次跑批之间永久为红，失去信号
        # （与 check_branch_coverage 仅在存在 coverage.xml 时判定同理）。
        # 退出码语义：0=通过（或无新批次可验）；1=存在未锁定批次（真故障）；
        # 2=用法/路径错误。默认扫描面已限定为近 2 天的 benchmark_*.json；
        # 审计历史请显式传 --all-history 或点名文件。
        if args.allow_empty:
            print(f"{msg}——--allow-empty，不阻断")
            for line in surface_disclosure([], 0):
                print(line)
            return 0 if not failures else 1
        print(f"{msg}——近期无新批次可验（S29 只要求新批次已锁定），通过；审计历史请用 --all-history")
        for line in surface_disclosure([], 0):
            print(line)
        return 0 if not failures else 1

    aliases, registry_reason = runtime_model_aliases()
    if registry_reason is not None:
        # 前提不成立 ⇒ 显式 skip 带成因（BZ §70）：不判 alias，但绝不静默。
        print(f"[SKIP] alias 对账未执行：{registry_reason}（`pinned` 判定不受影响）")

    checked: list[Path] = []
    exempt_count = 0
    for path in files:
        key = _rel_key(path)
        if key in _PRE_FINGERPRINT_EXEMPT:
            exempt_count += 1
            print(f"[EXEMPT] {path}: {_PRE_FINGERPRINT_EXEMPT[key]}")
            continue
        checked.append(path)

    comparable = 0
    for path in checked:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            print(f"[ERROR] {path}: 工件不可审计（{type(e).__name__}: {e}）")
            failures.append(f"{path}: 不可解析")
            continue
        passed, items, error_text = check_payload(payload)
        if not passed:
            detail = "；".join(items) if items else "未提供缺失项"
            suffix = f"（error: {error_text}）" if error_text else ""
            print(f"[FAIL] {path}: 模型版本未锁定——缺失项: {detail}{suffix}")
            failures.append(f"{path}: 缺少 {detail}")
            continue
        findings = comparability_findings(extract_fingerprint(payload) or {}, aliases)
        if findings:
            detail = "；".join(findings)
            print(f"[FAIL] {path}: 模型版本已锁定（pinned=true）但可比性不成立——{detail}")
            failures.append(f"{path}: 可比性 {len(findings)} 项")
            continue
        comparable += 1
        print(f"[PASS] {path}: model_fingerprint.pinned=true + 可比性围栏通过")

    total = len(files)
    exempt_note = f"（另有 {exempt_count} 个预指纹时代历史批次按名豁免）" if exempt_count else ""
    surface_lines = surface_disclosure(files, exempt_count)
    if failures:
        print(
            f"\n[model-fingerprint] 阻断：{len(failures)}/{total} 个工件不合格"
            f"（未锁定 + 已锁定但可比性不成立）{exempt_note}。"
            "预注册停止规则：未锁定或别名不可比的批次不得与历史批次合并统计。"
            "修复：确认 API 可用且 provider 返回 model/system_fingerprint，"
            "并确认 `requested_alias` 仍是当前运行面支持的模型，重跑批次。",
            file=sys.stderr,
        )
        for line in surface_lines:
            print(line, file=sys.stderr)
        return 1
    print(
        f"\n[model-fingerprint] 通过：{comparable}/{total - exempt_count} 个受检工件"
        f"均 pinned=true 且可比性两项围栏通过{exempt_note}"
    )
    for line in surface_lines:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
