#!/usr/bin/env python3
"""EVIDENCE-ARTIFACT CONSISTENCY GATE（EMSE 批次 2026-10-15，报告→工件对账）。

## 为什么需要这道门禁

本轮 EMSE 审计发现的最严重"可避免失分"不是统计方法，而是**同一事实在文档与
落盘工件之间分裂**：

- 文档表写 `n=261/臂、Pearson +0.0995`，而同一命令生成的落地工件写
  `配对 n 556/609/571、Pearson +0.1805`（差异静默存在，直到审计才发现）；
- 文档表里 `plain_llm_df` 的结论标签写"近饱和"，工件写"**无鉴别力（饱和）**"
  ——同一事实两种结论。

这类缺陷的共同结构是：**文档手工复制了本应由脚本再生成的数字**。

## 本门禁做什么

对指定的"数字族"做**逐单元格对账**（工件 = 权威，文档 = 派生）：

1. 从**工件**（`experiments/results/main_batch/mutation_detection_correlation.md`）
   解析每臂的 {批次文件数, 配对 n, detection 可测 n, detection 率, mean(MS|det=1),
   mean(MS|det=0), Δ均值, Pearson, Spearman, 饱和判定}；
2. 从**文档**（`docs/study/OPTIMIZATION_2026-10-15.md` §2 表）解析同名列；
3. 数值按容差比较（默认 5e-4，覆盖四舍五入），结论标签要求**字符串包含**一致；
4. 任一侧缺失该臂 → 报告为"未对账"（fail），因为静默缺失正是本轮缺陷的形态。

## 设计纪律（沿用本项目既有门禁教训）

- **保留完整行**解析：早期 `check_json_contract_sites.py` 曾因截断 200 字符
  误报 `MODEL_CARD.en.md:3`——本门禁不做行截断，且对全角字符做归一化；
- **不臆造缺失值**：缺列即失败，不按 0 或空串兜底；
- 零 LLM、零网络、纯 stdlib，秒级；不写任何文件。
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT = _REPO_ROOT / "experiments" / "results" / "main_batch" / "mutation_detection_correlation.md"
DEFAULT_DOCS = (_REPO_ROOT / "docs" / "emse" / "OPTIMIZATION_2026-10-15.md",)
ARMS = ("aitester", "plain_llm", "plain_llm_df")

# 列名 → 归一化键（中英/空格/加粗差异由 _norm 吸收）
_COLUMNS: dict[str, str] = {
    "批次文件数": "n_batches",
    "配对n": "n_pairs",
    "detection可测n": "n_det_measurable",
    "detection率": "detection_rate_pct",
    "mean(ms|det=1)": "mean_det1",
    "mean(ms|det=0)": "mean_det0",
    "Δ均值": "mean_delta",
    # `.lower()` 会把 `Δ`（U+0394）折叠为 `δ`（U+03B4），故两形态都登记，
    # 避免"大小写折叠"成为新的静默丢列通道。
    "δ均值": "mean_delta",
    "pearson": "pearson",
    "spearman": "spearman",
    "饱和判定": "saturation",
}
# 数值列（按容差比较）；其余按归一化字符串包含比较
_NUMERIC = {
    "n_batches",
    "n_pairs",
    "n_det_measurable",
    "detection_rate_pct",
    "mean_det1",
    "mean_det0",
    "mean_delta",
    "pearson",
    "spearman",
}


def _norm(text: str) -> str:
    """归一化：去空白/全角转半角/去 markdown 强调符/小写。"""
    out: list[str] = []
    for ch in text:
        code = ord(ch)
        if code == 0x3000:  # 全角空格
            continue
        if 0xFF01 <= code <= 0xFF5E:  # 全角 ASCII
            ch = chr(code - 0xFEE0)
        out.append(ch)
    s = "".join(out)
    for token in ("**", "`", "*", "_", "\\", " "):
        s = s.replace(token, "")
    return s.strip().lower()


def _split_row(line: str) -> list[str]:
    """拆分 Markdown 表格行（保留完整单元格内容，不截断）。

    `\\|`（转义竖线，如 `mean(MS\\|det=1)` 列头）必须**先占位再切分**，否则会
    把一列切成两列、导致整行错位——本项目已有过"截断/转义导致门禁误判"的教训。
    """
    if not line.strip().startswith("|"):
        return []
    placeholder = "\x00PIPE\x00"
    body = line.strip().replace("\\|", placeholder)
    cells = body.strip("|").split("|")
    return [c.replace(placeholder, "|").strip() for c in cells]


def _parse_markdown_table(text: str, arm_column: str = "臂") -> dict[str, dict[str, str]]:
    """解析表格：返回 {臂名: {归一化列名: 单元格原文}}。"""
    header: list[str] | None = None
    rows: dict[str, dict[str, str]] = {}
    for raw in text.splitlines():
        cells = _split_row(raw)
        if not cells:
            header = None
            continue
        norm = [_norm(c) for c in cells]
        if arm_column in norm[0]:
            header = norm
            continue
        if header is None or len(cells) != len(header):
            continue
        arm_raw = cells[0]
        # 归一化会去掉 `_`（markdown 强调符），臂名比较必须用同一归一化口径，
        # 否则 `plain_llm` 会被误判为"未识别臂"而静默丢行（本门禁第一版的缺陷）。
        arm = _norm(arm_raw).strip("`")
        # 最长匹配优先：`plain_llm_df` 归一化后包含 `plainllm`，须先匹配更具体的臂。
        matched = sorted((a for a in ARMS if _norm(a) in arm), key=len, reverse=True)
        if not matched:
            continue
        record: dict[str, str] = {}
        for key_norm, value in zip(header, cells, strict=True):
            canonical = _COLUMNS.get(key_norm)
            if canonical:
                record[canonical] = value.strip()
        rows[matched[0]] = record
    return rows


def _to_float(cell: str) -> float | None:
    cleaned = _norm(cell).replace("%", "").replace(",", "")
    if not cleaned or cleaned in {"-", "—", "n/a", "na"}:
        return None
    match = re.search(r"[-+]?\d*\.?\d+", cleaned)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


@dataclass
class Mismatch:
    source: str
    arm: str
    column: str
    artifact: str
    doc: str
    reason: str


def compare_tables(
    artifact: dict[str, dict[str, str]],
    doc: dict[str, dict[str, str]],
    *,
    tolerance: float = 5e-4,
) -> list[Mismatch]:
    problems: list[Mismatch] = []
    for arm in ARMS:
        art_row = artifact.get(arm)
        doc_row = doc.get(arm)
        if art_row is None or doc_row is None:
            problems.append(
                Mismatch(
                    "—",
                    arm,
                    "row",
                    "present" if art_row else "missing",
                    "present" if doc_row else "missing",
                    "表格缺该臂（不得静默跳过）",
                )
            )
            continue
        for canonical in (
            "n_batches",
            "n_pairs",
            "n_det_measurable",
            "detection_rate_pct",
            "mean_det1",
            "mean_det0",
            "mean_delta",
            "pearson",
            "spearman",
            "saturation",
        ):
            art_cell = art_row.get(canonical)
            doc_cell = doc_row.get(canonical)
            if art_cell is None or doc_cell is None:
                problems.append(Mismatch("—", arm, canonical, art_cell or "missing", doc_cell or "missing", "缺列"))
                continue
            if canonical in _NUMERIC:
                av, dv = _to_float(art_cell), _to_float(doc_cell)
                if av is None or dv is None:
                    problems.append(Mismatch("—", arm, canonical, art_cell, doc_cell, "无法解析为数值"))
                elif abs(av - dv) > tolerance:
                    problems.append(
                        Mismatch("—", arm, canonical, art_cell, doc_cell, f"数值不一致（容差 {tolerance}）")
                    )
            else:
                a_norm, d_norm = _norm(art_cell), _norm(doc_cell)
                if a_norm != d_norm and a_norm not in d_norm and d_norm not in a_norm:
                    problems.append(Mismatch("—", arm, canonical, art_cell, doc_cell, "结论标签不一致"))
    return problems


def _regenerate_artifact_text() -> str | None:
    """从**源批次工件**再生成对账用表格文本（不写任何文件）。

    CI/新鲜克隆场景：派生报告 `experiments/results/**` 不入库（`.gitignore:158`），
    只有源批次 JSON 入库。若源批次在场，则"工件"由生成函数**现场再生成**——
    这比把派生物入库更强：它同时锁定"文档数字 = 生成器输出"与"生成器可运行"。
    源批次缺席时返回 None（调用方回退到盘上派生物，并对生成器不做断言）。
    """
    batch_dir = _REPO_ROOT / "experiments" / "results" / "main_batch"
    if not batch_dir.is_dir():
        return None
    # 必须传**绝对路径**：生成器 `_load_arm_rows` 对非目录项按相对 CWD 解析，
    # 传文件名在从其他目录调用 CI 步骤时会静默读不到行（本门禁第二版缺陷）。
    files = sorted(str(p) for p in batch_dir.glob("benchmark_synthetic_*.json"))
    if not files:
        return None
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    try:
        from experiments.emse_optimization import mutation_correlation_report
    except Exception as exc:  # pragma: no cover - 依赖/环境异常时退回盘上工件
        print(f"  [WARN] 无法导入生成器（{type(exc).__name__}: {exc}）——改用盘上派生物")
        return None
    return mutation_correlation_report(files)


def _recompute_pass_matched_facts() -> dict[str, int] | None:
    """现场复算 T-10 通过率混淆分析的关键计数（源批次在场时）。

    动机（2026-10-15 扩展）：T-10 的匹配子集存在**两种口径**——
    严格（pattern×seed）与宽松（仅 pattern）。首版报告写 62 行/55 可测（宽松），
    而严格口径是 29 行/25 可测。文档若只引一个数字，读者无法判断是哪种口径；
    若引旧值，则与工件漂移。本函数把两种口径的关键计数**现算**出来，
    供 `--check-t10-docs` 对账用；源批次缺席时返回 None（不臆造）。
    """
    batch_dir = _REPO_ROOT / "experiments" / "results" / "main_batch"
    if not batch_dir.is_dir():
        return None
    if not sorted(batch_dir.glob("benchmark_synthetic_20261006_1*.json")):
        return None
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    try:
        from experiments.pass_matched_sensitivity import (
            ARM_PROMPT_ONLY,
            ARM_TREATMENT,
            load_batches,
            pass_matched_subset,
            success_declaration_table,
        )
    except Exception as exc:  # pragma: no cover - 依赖异常时不阻断主流程
        print(f"  [WARN] 无法导入 T-10 复算器（{type(exc).__name__}: {exc}）")
        return None
    rows = load_batches(batch_dir, seeds=(42, 43, 44))
    rows.pop("__batches__", None)
    matched = pass_matched_subset(rows, arm_treatment=ARM_TREATMENT, arm_reference=ARM_PROMPT_ONLY)
    sd = {r["arm"]: r for r in success_declaration_table(rows, [ARM_TREATMENT, "plain_llm", ARM_PROMPT_ONLY])}
    # 防"静默零"：批次文件在场但解析出 0 行（空文件 / 结构不符）时**不得**把它当成
    # "匹配子集为 0" 去对账文档——那会把解析失败伪装成合法事实（本项目已多次
    # 因"结构性 0"吃过亏：ADR-0021/0029/0033 三起伪影皆此形态）。
    if not rows.get(ARM_TREATMENT) or matched["matched_loose"]["rows"] == 0 or matched["matched_strict"]["rows"] == 0:
        print(
            f"  [WARN] T-10 复算得到空行集（aitester={len(rows.get(ARM_TREATMENT) or [])}、"
            f"strict={matched['matched_strict']['rows']}、loose={matched['matched_loose']['rows']}）——"
            "判定为源批次不可用，跳过对账（不臆造 0）"
        )
        return None
    return {
        "strict_rows": matched["matched_strict"]["rows"],
        "strict_measurable": matched["matched_strict"]["detection_measurable"],
        "loose_rows": matched["matched_loose"]["rows"],
        "loose_measurable": matched["matched_loose"]["detection_measurable"],
        "unmatched_rows": matched["unmatched"]["rows"],
        "unmatched_detections": matched["unmatched"]["detection_true"],
        "df_passed": sd[ARM_PROMPT_ONLY]["passed_true"],
    }


# T-10 文档对账锚点：文档必须同时出现"严格口径行数"与该口径的可测数。
# 只要求这两个数字在场（不校验句子结构），避免把门禁绑死在特定措辞上。
_T10_ANCHOR_DOCS = (
    _REPO_ROOT / "docs" / "VALIDITY.md",
    _REPO_ROOT / "docs" / "EVALUATION_SCOPE.md",
)


def _rel(path: Path) -> str:
    """路径显示名：仓库内用相对路径，仓库外（如测试 tmp_path）退化为绝对路径。

    门禁会被测试以 tmp 文档调用，`Path.relative_to` 在仓库外会抛 ValueError——
    显示名不得成为新的崩溃面。
    """
    try:
        return str(path.relative_to(_REPO_ROOT))
    except ValueError:
        return str(path)


# 状态登记册按设计必须随基线同步刷新，故其覆盖率声明直接与 coverage.xml 对账。
_STATUS_REGISTER = _REPO_ROOT / "docs" / "PROJECT_STATUS_REGISTER.md"
_COVERAGE_XML = _REPO_ROOT / "coverage.xml"

# 对账锚点：登记册 §1 表格的覆盖率声明行。锚定表头文字而非"全文任意位置出现过
# 该数字"——旧口径下正文任何角落（含历史勘误、别的指标）凑巧出现 92.93 就算对账通过。
_REGISTER_DECL: dict[str, re.Pattern[str]] = {
    "行": re.compile(r"总行覆盖\s*\|\s*\*\*(\d{1,3}(?:\.\d{1,2})?)\s*%\*\*"),
    "分支": re.compile(r"总分支覆盖\s*\|\s*\*\*(\d{1,3}(?:\.\d{1,2})?)\s*%\*\*"),
}
# 对账容差（百分点）。**实测**依据（2026-10-16，同一份源码连跑多次全量）：
#   - 分支：5460/6236=87.56% 与 5459/6236=87.54% —— 单分支抖动 0.016pp；
#   - 行：`graph/nodes.py` 两次分别 0.7776 与 0.7862（约 6 行），对**总行覆盖**
#     的贡献约 6/16926 = 0.035pp。
# 即：本仓库的覆盖率测量本身带 ≈0.05pp 量级的非确定性，逐位相等**不可满足**，
# 真跑起来只会把"常年假绿"换成"随机真红"（flaky 门禁的结局是被忽略或加
# continue-on-error）。故先取观测抖动上界的约 2 倍 = ±0.10pp（2026-10-16）。
#
# 2026-10-18 U 轮（首次真实 CI 实测）跨平台校准：同一 Python 3.14、同一份源码，
# ubuntu CI 实测行 96.53%（17501/18131）/ 分支 92.66%（6273/6770），macOS 本地
# 实测行 96.55%（17506/18131）/ 分支 92.79%（6282/6770）——**分支差 0.13pp
# （9 条平台专属分支：Seatbelt/bwrap 等）** > 原 0.10pp，导致"文档声明 ubuntu 则本地红、
# 声明 macOS 则 CI 红"的双向假红。故校准为 ±0.20pp（= 观测跨平台差 0.13pp 的
# ≈1.5 倍，仍远小于任何实质性错报——声称 95% 实测 92.7% 依然立刻转红）。
# 容差不等于放松：防回退由 coverage_ratchet.py 的只升水位独立把守；登记册 §1
# 声明口径 = **CI ubuntu 3.14**（权威执行环境），本地 macOS 差异按已披露口径处置。
_REGISTER_TOLERANCE_PP = 0.20


def check_status_register(*, require_coverage: bool = False) -> tuple[list[str], bool]:
    """状态登记册 §1 的覆盖率声明必须与 `coverage.xml` 实测相符（防文档自我美化）。

    返回 ``(问题清单, 是否真正对过账)``。第二个返回位是 G6（2026-10-16）加的：
    此前本函数在 coverage.xml 缺席时返回空清单，调用方一律打印 `[OK]`——而 CI 里
    本步骤排在生成 coverage.xml 的测试步骤之前约 90 行，产物**必然不存在**，
    于是"登记册数字过期即 CI 红"的声明（本册开头自述）长期是一句空话：这道对账
    从未在 CI 真正运行过。现在缺席与通过可区分，且 `--require-coverage` 下缺席
    即计为问题（CI 覆盖率集群用法）。

    同日修正对账口径：从"实测值的两位小数字符串出现在全文任意位置"改成
    "锚定 §1 声明行 + `_REGISTER_TOLERANCE_PP` 容差"。旧口径同时犯两个错——
    漏判（全文凑巧出现即通过）与不可满足（分支覆盖逐次抖动 ±1 分支），
    后者会让 CI 随机转红；声明行缺失一律计为问题（缺席 ≠ 通过）。
    """
    if not _STATUS_REGISTER.is_file():
        # 登记册入库、与 coverage 产物无关，缺席属仓库级问题 → 一律计为问题
        return ([f"{_rel(_STATUS_REGISTER)}：文件缺失，覆盖率声明无从对账"], False)
    if not _COVERAGE_XML.is_file():
        if require_coverage:
            return (
                [
                    f"{_rel(_COVERAGE_XML)} 缺席：--require-coverage 下覆盖率对账不得跳过"
                    "（本步骤必须排在生成 coverage.xml 的测试步骤之后）"
                ],
                False,
            )
        return ([], False)
    import xml.etree.ElementTree as _ET

    try:
        tree = _ET.parse(_COVERAGE_XML).getroot()
        measured = {
            "行": float(tree.get("line-rate")) * 100,
            "分支": float(tree.get("branch-rate")) * 100,
        }
    except Exception as exc:  # pragma: no cover - 工件损坏/属性缺失时给出明确告警
        return ([f"coverage.xml 解析失败（{type(exc).__name__}）——状态登记册无法对账"], False)
    text = _STATUS_REGISTER.read_text(encoding="utf-8")
    problems: list[str] = []
    for label, pattern in _REGISTER_DECL.items():
        match = pattern.search(text)
        if not match:
            problems.append(
                f"{_rel(_STATUS_REGISTER)}：§1 未找到总{label}覆盖声明行"
                f"（期望 `| 总{label}覆盖 | **NN.NN%** |`）——无从对账，按不通过处置"
            )
            continue
        declared = float(match.group(1))
        delta = declared - measured[label]
        if abs(delta) > _REGISTER_TOLERANCE_PP:
            problems.append(
                f"{_rel(_STATUS_REGISTER)}：§1 声明总{label}覆盖 {declared:.2f}%，"
                f"实测 {measured[label]:.2f}%（偏差 {delta:+.2f}pp，容差 ±{_REGISTER_TOLERANCE_PP:.2f}pp）"
                "——按 coverage.xml 刷新 §1"
            )
    return problems, True


def check_t10_docs(facts: dict[str, int]) -> list[str]:
    """检查 T-10 文档是否声明了**严格口径**的匹配子集规模（返回问题清单）。"""
    problems: list[str] = []
    strict_rows, strict_meas = facts["strict_rows"], facts["strict_measurable"]
    for doc in _T10_ANCHOR_DOCS:
        if not doc.is_file():
            problems.append(f"{_rel(doc)}：文件缺失")
            continue
        text = doc.read_text(encoding="utf-8")
        has_rows = re.search(rf"(?<!\d){strict_rows}\s*行", text) or re.search(rf"(?<!\d){strict_rows}\s*rows", text)
        has_meas = re.search(rf"(?<!\d){strict_meas}\s*(?:可测|measurable)", text)
        if not has_rows:
            problems.append(
                f"{_rel(doc)}：未声明严格口径匹配子集行数（应为 {strict_rows} 行）"
                "——宽松口径（62 行）不得单独出现，否则读者无法判断口径"
            )
        if not has_meas:
            problems.append(f"{_rel(doc)}：未声明严格口径可测行数（应为 {strict_meas} 可测）")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="报告→工件 数值对账门禁（零 LLM）")
    parser.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT)
    parser.add_argument(
        "--doc",
        type=Path,
        action="append",
        default=None,
        help="待对账文档（可重复；默认 docs/study/OPTIMIZATION_2026-10-15.md）",
    )
    parser.add_argument("--tolerance", type=float, default=5e-4)
    parser.add_argument(
        "--no-regenerate",
        action="store_true",
        help="不现场再生成，直接用盘上派生物（调试用；CI 应保持默认的「再生成优先」）",
    )
    parser.add_argument(
        "--skip-t10",
        action="store_true",
        help="跳过 T-10（通过率混淆）文档对账（调试用）",
    )
    parser.add_argument(
        "--require-coverage",
        action="store_true",
        help="coverage.xml 缺席即失败（CI 覆盖率集群用法；默认缺席只报 SKIP，不计通过）",
    )
    args = parser.parse_args(argv)

    docs = tuple(args.doc) if args.doc else DEFAULT_DOCS
    artifact_text: str | None = None
    if not args.no_regenerate:
        artifact_text = _regenerate_artifact_text()
    if artifact_text is not None:
        source = f"现场再生成（源：{_REPO_ROOT / 'experiments' / 'results' / 'main_batch'}）"
    elif args.artifact.is_file():
        artifact_text = args.artifact.read_text(encoding="utf-8")
        source = f"盘上派生物（{args.artifact}）"
    else:
        print(f"✗ 无可用工件：既无源批次（无法再生成），盘上派生物也不存在（{args.artifact}）")
        return 1
    artifact = _parse_markdown_table(artifact_text)
    if not artifact:
        print(f"✗ 工件表格解析为空（来源：{source}）")
        return 1
    print(f"  工件来源：{source}；对账臂：{sorted(artifact)}")

    failures: list[Mismatch] = []
    checked = 0
    for doc_path in docs:
        if not Path(doc_path).is_file():
            print(f"✗ 文档缺失：{doc_path}")
            failures.append(Mismatch(str(doc_path), "—", "file", "—", "—", "文档不存在"))
            continue
        doc_table = _parse_markdown_table(Path(doc_path).read_text(encoding="utf-8"))
        if not doc_table:
            print(f"✗ 文档内未找到可对账表格（臂/批次文件数 列头）：{doc_path}")
            failures.append(Mismatch(str(doc_path), "—", "table", "—", "—", "未找到表格"))
            continue
        problems = compare_tables(artifact, doc_table, tolerance=args.tolerance)
        checked += len(ARMS) * len(_COLUMNS)
        for p in problems:
            p.source = str(doc_path)
            failures.append(p)
        print(
            f"  [{'OK' if not problems else 'FAIL'}] {doc_path}"
            f" —— 对账臂 {sorted(doc_table)}，不一致 {len(problems)} 项"
        )

    for f in failures:
        print(f"    ✗ {f.source}｜臂={f.arm}｜列={f.column}：工件={f.artifact!r} vs 文档={f.doc!r}（{f.reason}）")

    # ─── T-10（通过率混淆）声明对账：严格口径必须显式声明 ───────────────────
    if not args.skip_t10:
        t10_facts = _recompute_pass_matched_facts()
        if t10_facts is None:
            print("  [SKIP] T-10 对账：源批次缺席（无法现算，不臆造）")
        else:
            t10_problems = check_t10_docs(t10_facts)
            print(
                f"  [{'OK' if not t10_problems else 'FAIL'}] T-10 声明对账"
                f"（严格口径 {t10_facts['strict_rows']} 行 / {t10_facts['strict_measurable']} 可测；"
                f"宽松 {t10_facts['loose_rows']} / {t10_facts['loose_measurable']}）"
            )
            for item in t10_problems:
                print(f"    ✗ {item}")
                failures.append(Mismatch(str(_T10_ANCHOR_DOCS[0]), "—", "t10_strict_caliber", "—", "—", item))

    # ─── 状态登记册：覆盖率声明必须与 coverage.xml 实测相符（±容差） ────────
    register_problems, register_checked = check_status_register(require_coverage=args.require_coverage)
    if register_problems:
        print(f"  [FAIL] 状态登记册覆盖率对账（{len(register_problems)} 项）")
        for item in register_problems:
            print(f"    ✗ {item}")
            failures.append(Mismatch(str(_STATUS_REGISTER), "—", "status_register_coverage", "—", "—", item))
    elif register_checked:
        print(
            f"  [OK] 状态登记册覆盖率对账（§1 行/分支声明与 coverage.xml 实测相符，容差 ±{_REGISTER_TOLERANCE_PP:.2f}pp）"
        )
    else:
        # G6：缺席 ≠ 通过。此前这里固定打印 "[OK] …（无 coverage.xml 时跳过）"，
        # 把"根本没对过账"读作"对账通过"。
        print("  [SKIP] 状态登记册覆盖率对账：coverage.xml 缺席，本次未对账（不得读作通过）")

    if failures:
        print(f"\n✗ 报告→工件对账失败：{len(failures)} 项不一致（文档数字必须来自工件再生成，不得手工复制）")
        return 1
    print(
        f"\n✓ 报告→工件对账通过（{len(docs)} 份文档 × {len(ARMS)} 臂 × {len(_COLUMNS)} 列，"
        f"容差 {args.tolerance}；工件权威 = {args.artifact.name}）"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
