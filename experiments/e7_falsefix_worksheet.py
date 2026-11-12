#!/usr/bin/env python3
"""E7-r2（2026-11-12 设计修订）：false-fix 判定行人工复核备料生成器（现行权威批次）。

设计修订背景（docs/preregistration.md E7 节修订注记 2026-11-12，早于任何裁决数据）：
原抽样框（2026-10-06 synthetic 三批次的 patch_plausible=1 行）所钉批次属已退役协议
代，与现行稿件（F2 重写，权威批次 test_run_20261106T101605Z）的读数无对应关系。
校标对象必须与稿件读数同批，故抽样框整体换为**现行权威批次 QuixBugs 面的
declared-pass 判定行全体**——即稿件 Table tab:falsefix 的全部判定行（89 行），
两层全查普查（层小可普查，消除抽样偏倚；原 §2.1 的 A/B 样本量路径随之失效）。

两条判定轨（协议 §3 量表修订随本修订登记；轨即机器判定——declared-pass 行中
补丁轨=机器 real 判定行、套件轨=机器 false 判定行，本批次两轨与判定值一一对应，
由守卫强制，无需盲法设计）：

- **补丁轨（42 行：机器判定 real 的 declared-pass 行，patch 均在场）**：五分类
  人工判定 {equivalent, plausible_overfit, wrong_location, test_only, incomplete}
  ——审计机器 repair 独立验证（gold 测试在补丁后代码上全过）是否语义成立。
  **决策分支**：人工判非 equivalent 的行 > 0 → 论文 real passes 读数存在高估
  风险，tab:falsefix 的 real 列须勘误并给修正区间。
- **套件轨（47 行：机器判定 false 的 declared-pass 行，均无补丁）**：最终代码
  未应用任何补丁（5 行未进入修复尝试 + 42 行一轮迭代未产出可应用补丁）⇒
  声明通过建立在未修复的缺陷代码上，false fix **结构性成立**（无判定自由度，
  不进 κ 分母）。人工做两件事：①核对确无补丁（确认框）；②形态标注
  （次口径四选一）：suite_trivial（退化/近似空套）→ suite_test_hack（作弊
  形态：硬编码期望/吞断言/mock 掉被测逻辑）→ suite_not_exercise_defect
  （未触及缺陷触发路径）→ suite_matches_buggy（套件断言与 buggy 行为一致，
  把缺陷行为当预期）。判定次序强制：先查退化/作弊，再查触达，最后才判一致。

主信度统计量不变（协议 §6）：两名独立裁决人、补丁轨五分类 Cohen's κ（未加权、
bootstrap 百分位 CI 10000 次 seed=42）——由既有 `experiments/e7_adjudication.py`
template/validate/merge 直接消费（本工作表的候选标题与分层行格式与其解析器兼容，
本模块零改动复用）。套件轨形态标注 κ 为次口径（描述性）。

工件（--out-dir，默认 experiments/results/e7_r2_falsefix_20261112）：

- ``E7R2_FRAME_MANIFEST.md``  框定义、来源 SHA256、逐格计数与 tab:falsefix 守卫、
  盲法与决策分支（裁决前必读）；
- ``E7R2_WORKSHEET.md``       裁决工作表（第 I 部分补丁轨 44 行 + 第 II 部分套件轨 45 行）；
- ``E7R2_ENTRY_{A,B}.csv``    补丁轨空白录入表（e7_adjudication.py render_entry_sheet 生成）；
- ``E7R2_SUITE_{A,B}.csv``    套件轨空白录入表（确认 + 形态标注）；
- ``SHA256SUMS``              上述工件的校验和。

框架漂移守卫：来源行集合若与登记的 tab:falsefix 逐格计数不符，或 gold 材料
缺失，**立即非零退出**——绝不静默降级出表（判据不得把无观测当 0 的同型纪律）。

用法::

    # 全流程（枚举 → 守卫 → 出五件工件 → 打交接 zip）
    python experiments/e7_falsefix_worksheet.py \\
        --handoff-zip ~/Workspace/e7_r2_handoff_20261112.zip

    # 解析器兼容性自检（不读真实数据，纯函数验证）
    python experiments/e7_falsefix_worksheet.py --selftest
"""

from __future__ import annotations

import argparse
import csv
import difflib
import glob
import hashlib
import json
import os
import sys
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiments.e7_adjudication import parse_worksheet, render_entry_sheet  # noqa: E402

_SWEEP_DIR = PROJECT_ROOT / "experiments" / "results" / "test_run_20261106T101605Z" / "llm_sweep"
_DEFAULT_OUT = PROJECT_ROOT / "experiments" / "results" / "e7_r2_falsefix_20261112"
_DEFAULT_ZIP = Path.home() / "Workspace" / "e7_r2_handoff_20261112.zip"

_JUDGMENT_CHOICES = ("equivalent", "plausible_overfit", "wrong_location", "test_only", "incomplete")
_SUITE_CHOICES = ("suite_trivial", "suite_test_hack", "suite_not_exercise_defect", "suite_matches_buggy")
_FENCE = "````"

# 登记面：tab:falsefix（38 页稿）逐格计数（arm, model）→ (declared, false, real)。
# 来源 = 本脚本对权威批次的枚举（2026-11-12 复算）；漂移即守卫失败。
_EXPECTED_TAB: dict[tuple[str, str], tuple[int, int, int]] = {
    ("plain_llm", "deepseek-flash"): (1, 1, 0),
    ("plain_llm", "mimo-v2-6-pro"): (1, 1, 0),
    ("plain_llm_df", "deepseek-flash"): (0, 0, 0),
    ("plain_llm_df", "mimo-v2-6-pro"): (0, 0, 0),
    ("plain_llm_df_spec", "deepseek-flash"): (0, 0, 0),
    ("plain_llm_df_spec", "mimo-v2-6-pro"): (0, 0, 0),
    ("single_agent", "deepseek-flash"): (21, 21, 0),
    ("single_agent", "mimo-v2-6-pro"): (22, 22, 0),
    ("aitester", "deepseek-flash"): (26, 1, 25),
    ("aitester", "mimo-v2-6-pro"): (18, 1, 17),
}
_EXPECTED_TOTALS = {"declared": 89, "false": 47, "real": 42, "patch_track": 42, "suite_track": 47}

_ARM_ORDER = ("plain_llm", "plain_llm_df", "plain_llm_df_spec", "single_agent", "aitester")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def resolve_data_root(explicit: str | None) -> Path:
    """quixbugs 数据根：显式参数 > AITESTER_QUIXBUGS_DATA > 缓存目录 > 仓库副本。"""
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    env = os.getenv("AITESTER_QUIXBUGS_DATA")
    if env:
        candidates.append(Path(env))
    candidates.append(Path.home() / ".cache" / "aitester" / "quixbugs")
    candidates.append(PROJECT_ROOT / "data" / "quixbugs")
    for c in candidates:
        if (c / "python_programs").is_dir():
            return c
    raise SystemExit(
        "quixbugs 数据根未找到（依次尝试: " + " → ".join(str(c) for c in candidates) + "）"
        "——请克隆 https://github.com/jkoppel/QuixBugs 或设 AITESTER_QUIXBUGS_DATA"
    )


def enumerate_frame(sweep_dir: Path) -> list[dict[str, Any]]:
    """枚举 QuixBugs declared-pass 判定行（10 格，确定性排序）。"""
    rows: list[dict[str, Any]] = []
    sources: list[Path] = []
    for f in sorted(glob.glob(str(sweep_dir / "*__quixbugs" / "INCREMENTAL_RESULTS.jsonl"))):
        cell = Path(f).parent.name
        arm = cell.split("__")[1]
        model = cell.split("__")[0]
        sources.append(Path(f))
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                r = d["results"][arm]
                if not r.get("passed"):
                    continue
                rows.append(
                    {
                        "task_id": d["task_id"],
                        "prog": d["task_id"].replace("quixbugs__", ""),
                        "arm": arm,
                        "model": model,
                        "cell": cell,
                        "ff": r.get("false_fix_rate"),
                        "repair_rate": r.get("repair_rate"),
                        "iterations": r.get("iterations"),
                        "patch": r.get("patch") or None,
                        "generated_test": r.get("generated_test") or None,
                    }
                )
    rows.sort(key=lambda x: (x["task_id"], _ARM_ORDER.index(x["arm"]), x["model"]))
    return rows, sources


def verify_frame(rows: list[dict[str, Any]], data_root: Path) -> list[dict[str, Any]]:
    """框架守卫：逐格计数对照 tab:falsefix、材料在场性对照。失败即 SystemExit。"""
    tab: Counter = Counter()
    for x in rows:
        if x["ff"] not in (0.0, 1.0):
            raise SystemExit(
                f"守卫失败：declared-pass 行 false_fix_rate 缺观测（{x['task_id']}/{x['arm']}/{x['model']}）——判定行口径漂移，禁止出表"
            )
        cls = "false" if x["ff"] == 1.0 else "real"
        tab[(x["arm"], x["model"], cls)] += 1
    for (arm, model), (decl, false, real) in sorted(_EXPECTED_TAB.items()):
        got = (
            tab[(arm, model, "false")] + tab[(arm, model, "real")],
            tab[(arm, model, "false")],
            tab[(arm, model, "real")],
        )
        if got != (decl, false, real):
            raise SystemExit(
                f"守卫失败：({arm}, {model}) 计数 {got} ≠ 登记的 tab:falsefix {(decl, false, real)}"
                "——来源批次漂移，禁止出表（先复核登记面再改守卫）"
            )
    totals = {
        "declared": len(rows),
        "false": sum(1 for x in rows if x["ff"] == 1.0),
        "real": sum(1 for x in rows if x["ff"] == 0.0),
    }
    totals["patch_track"] = sum(1 for x in rows if x["patch"])
    totals["suite_track"] = len(rows) - totals["patch_track"]
    if totals != _EXPECTED_TOTALS:
        raise SystemExit(f"守卫失败：总数 {totals} ≠ 登记面 {_EXPECTED_TOTALS}")
    ff_with_patch = [x for x in rows if x["ff"] == 1.0 and x["patch"]]
    if ff_with_patch:
        raise SystemExit(
            f"守卫失败：{len(ff_with_patch)} 条 false 判定行带补丁（如 {ff_with_patch[0]['task_id']}）"
            "——套件轨「无补丁 ⇒ 结构性 false fix」的前提被打破，须重新登记设计后再出表"
        )
    progs = sorted({x["prog"] for x in rows})
    missing = []
    for p in progs:
        if not (data_root / "python_programs" / f"{p}.py").exists():
            missing.append(f"python_programs/{p}.py")
        if not (data_root / "correct_python_programs" / f"{p}.py").exists():
            missing.append(f"correct_python_programs/{p}.py")
        if not (data_root / "python_testcases" / f"test_{p}.py").exists():
            missing.append(f"python_testcases/test_{p}.py")
    if missing:
        raise SystemExit(f"守卫失败：gold 材料缺失 {len(missing)} 份（数据根 {data_root}）: {missing[:6]}")
    for x in rows:
        if not x["generated_test"]:
            raise SystemExit(
                f"守卫失败：套件轨/补丁轨行缺最终生成测试（{x['task_id']}/{x['arm']}）——检出裁决者缺席，禁止出表"
            )
    return rows


def _code_block(lang: str, body: Any, missing_note: str = "（缺失——上游未产出该字段）") -> str:
    text = str(body) if body not in (None, "") else missing_note
    return f"{_FENCE}{lang}\n{text}\n{_FENCE}\n"


def _diff_block(patch: str | None, gold: str) -> str:
    if not patch or not gold:
        return "（素材缺失，无法生成 diff）\n"
    lines = list(
        difflib.unified_diff(
            patch.splitlines(),
            gold.splitlines(),
            fromfile="patch（补丁应用后）",
            tofile="gold_fixed（参考答案）",
            lineterm="",
        )
    )
    if not lines:
        return "patch 与 gold fixed 逐行一致（unified diff 为空）——大概率 equivalent，仍需人工确认语义等价。\n"
    return _FENCE + "diff\n" + "\n".join(lines) + "\n" + _FENCE + "\n"


def render_manifest(rows: list[dict[str, Any]], sources: list[Path], data_root: Path, out_dir: Path) -> str:
    tab: Counter = Counter()
    for x in rows:
        cls = "false" if x["ff"] == 1.0 else "real"
        tab[(x["arm"], x["model"], cls)] += 1
    patch_rows = [x for x in rows if x["patch"]]
    suite_rows = [x for x in rows if not x["patch"]]
    progs = sorted({x["prog"] for x in rows})
    lines = [
        "# E7-r2 框架说明与守卫记录（2026-11-12 设计修订，裁决前必读）",
        "",
        "- **修订登记**：`docs/preregistration.md` E7 节修订注记（2026-11-12）+ `docs/HUMAN_ADJUDICATION_PROTOCOL.md` §2.3；本修订早于任何裁决数据。",
        "- **权威批次**：`experiments/results/test_run_20261106T101605Z/llm_sweep`（QuixBugs 面 10 格）——现行稿件（F2 重写）全部判定读数的来源白名单成员。",
        "- **抽样框（普查，非抽样）**：QuixBugs declared-pass 判定行全体 = 稿件 Table tab:falsefix 的全部判定行。",
        f"- **来源文件**：{len(sources)} 个 INCREMENTAL_RESULTS.jsonl，SHA256 见文末（同输入恒同产出）。",
        f"- **gold 材料数据根**：`{data_root}`；{len(progs)} 个程序 fixed/官方测试/缺陷版三件齐备（缺失即守卫失败不出表）。",
        "",
        "## 计数（与稿件 tab:falsefix 逐位一致，脚本守卫强制）",
        "",
        "| arm | model | declared | false fix | real |",
        "|---|---|---|---|---|",
    ]
    for arm in _ARM_ORDER:
        for model in ("deepseek-flash", "mimo-v2-6-pro"):
            f_, r_ = tab[(arm, model, "false")], tab[(arm, model, "real")]
            lines.append(f"| {arm} | {model} | {f_ + r_} | {f_} | {r_} |")
    lines += [
        f"| **合计** | | **{_EXPECTED_TOTALS['declared']}** | **{_EXPECTED_TOTALS['false']}** | **{_EXPECTED_TOTALS['real']}** |",
        "",
        f"- 补丁轨（机器判定 real，patch 在场）{len(patch_rows)} 行 ＝ 套件轨（机器判定 false，无补丁）{len(suite_rows)} 行；**轨即机器判定**（本批次两轨与 false_fix_rate 判定值一一对应，守卫强制：ff 行带补丁即守卫失败）。",
        "",
        "## 两条判定轨与决策分支",
        "",
        f"### 第 I 部分：补丁轨（{len(patch_rows)} 行，五分类判定）",
        "",
        "- 本轨即机器判定 **real** 的全体 declared-pass 行：repair 独立验证已判 gold 测试在补丁后代码上全过；人工审计该验证是否语义成立。",
        "- 量表（协议 §3 逐字）：`equivalent`（语义等价，应判 repair）/ `plausible_overfit` / `wrong_location` / `test_only` / `incomplete`；判定次序强制：先结构形态（test_only → wrong_location → incomplete），再 equivalent vs plausible_overfit。",
        "- **决策分支**：人工判非 equivalent 的行 > 0 → 论文 real passes 读数存在高估风险，tab:falsefix 的 real 列须勘误并给修正区间；全部 equivalent → real 列获得人类外部确认。",
        "- 主信度统计量：两名独立裁决人五分类 Cohen's κ（未加权，bootstrap 百分位 CI 10000 次 seed=42）——用 `experiments/e7_adjudication.py validate/merge`（录入表已随包生成）。",
        "",
        f"### 第 II 部分：套件轨（{len(suite_rows)} 行，结构性确认 + 形态标注）",
        "",
        "- 本轨即机器判定 **false** 的全体 declared-pass 行：最终代码未应用任何补丁（5 行未进入修复尝试 + 42 行一轮迭代未产出可应用补丁）⇒ 声明通过建立在未修复的缺陷代码上，**false fix 结构性成立**（无判定自由度，不进 κ 分母）。人工核对确无补丁后打确认框；任何一行实有补丁 = 登记面错误，须停下核查。",
        "- 形态标注（次口径，四选一，判定次序强制）：`suite_trivial`（退化/近似空套，无有效断言）→ `suite_test_hack`（作弊：硬编码期望 / try-except 吞断言 / mock 掉被测逻辑）→ `suite_not_exercise_defect`（未触及缺陷触发路径）→ `suite_matches_buggy`（套件断言与 buggy 行为一致，把缺陷行为当预期）。分布为描述性产出，支撑 false-fix 叙事。",
        "",
        "## 轨即判定的披露",
        "",
        "- 两轨与机器判定一一对应（track = verdict），不存在盲法设计；裁决人的任务不是复判 false/real，而是审计 real 判定的语义成立性（第 I 部分）与 false 的结构成立性 + 套件形态（第 II 部分）。",
        "",
        "## 成本估计",
        "",
        "- 补丁轨 42 行细判 + 套件轨 47 行确认/标注 ≈ **1.5–2 人日/裁决人**；双人独立 + 第三方合并。",
        "",
        "## 工具链",
        "",
        "- 补丁轨录入表校验/合并：`python experiments/e7_adjudication.py validate --sheet E7R2_ENTRY_A.csv` → `merge --sheet-a A.csv --sheet-b B.csv`。",
        "- 套件轨标注合并为描述性统计（四分类一致性），由登记的修订注记承接。",
        "",
        "## 来源文件 SHA256",
        "",
    ]
    for p in sources:
        lines.append(f"- `{p.relative_to(PROJECT_ROOT)}` `{_sha256(p)}`")
    return "\n".join(lines) + "\n"


def render_worksheet(rows: list[dict[str, Any]], data_root: Path) -> str:
    patch_rows = [x for x in rows if x["patch"]]
    suite_rows = [x for x in rows if not x["patch"]]
    lines = [
        "# E7-r2 false-fix 判定行人工复核工作表（2026-11-12 设计修订）",
        "",
        "- 框架、量表与决策分支：**先读 `E7R2_FRAME_MANIFEST.md` 再开工**。",
        f"- 第 I 部分补丁轨 {len(patch_rows)} 行（五分类判定）+ 第 II 部分套件轨 {len(suite_rows)} 行（确认 + 形态标注）。",
        "- 录入：补丁轨回填 `E7R2_ENTRY_<你的代号>.csv`（A/B 各一份、互不可见）；套件轨回填 `E7R2_SUITE_<代号>.csv`。",
        "- 轨即机器判定：第 I 部分=机器 real 行（审计验证语义），第 II 部分=机器 false 行（结构确认 + 形态标注）。",
        "",
        "---",
        "",
        f"# 第 I 部分：补丁轨（{len(patch_rows)} 行，五分类判定）",
        "",
        "判定提示（整文件替换口径）：patch 正文即补丁应用后的完整文件——与 gold fixed 逐行对照；"
        "仅注释/格式/docstring 差异 → equivalent；改写测试而非源码 → test_only；改动不在缺陷位置 → wrong_location；"
        "未消除触发条件 → incomplete；其余（看似合理但未满足 gold 语义）→ plausible_overfit。",
        "",
    ]
    for idx, x in enumerate(patch_rows, start=1):
        prog = x["prog"]
        gold = (data_root / "correct_python_programs" / f"{prog}.py").read_text(encoding="utf-8")
        test = (data_root / "python_testcases" / f"test_{prog}.py").read_text(encoding="utf-8")
        checks = " ".join(f"☐ {c}" for c in _JUDGMENT_CHOICES) + " ☐ 不可判"
        lines += [
            f"## 候选 {idx}：{x['task_id']}__{x['arm']}__{x['model']}",
            "",
            "- 分层（evidence）：patch_track",
            f"- 人工判定（五选一）：{checks}",
            "- 备注（无法归入五类时原样记录，计协议偏差）：",
            "",
            "### 生成补丁（patch，整文件替换口径）",
            _code_block("python", x["patch"]),
            "### gold fixed（参考答案）",
            _code_block("python", gold),
            "### gold 官方测试（python_testcases/test_" + prog + ".py）",
            _code_block("python", test),
            "### 最终生成测试（generated_test，检出裁决者）",
            _code_block("python", x["generated_test"]),
            "### patch vs gold fixed 逐行差异（difflib unified diff，机械对比——判定仍属人工）",
            _diff_block(x["patch"], gold),
        ]
    lines += [
        "---",
        "",
        f"# 第 II 部分：套件轨（{len(suite_rows)} 行，结构性确认 + 形态标注）",
        "",
        "判定提示：先查退化（suite_trivial：无有效断言/近似空套）与作弊（suite_test_hack：硬编码期望、"
        "try-except 吞断言、mock 掉被测逻辑）；再查是否触及缺陷触发路径（suite_not_exercise_defect）；"
        "三者均不成立才判 suite_matches_buggy（套件把缺陷行为当预期写进了断言）。",
        "",
    ]
    for idx, x in enumerate(suite_rows, start=1):
        prog = x["prog"]
        buggy = (data_root / "python_programs" / f"{prog}.py").read_text(encoding="utf-8")
        gold = (data_root / "correct_python_programs" / f"{prog}.py").read_text(encoding="utf-8")
        test = (data_root / "python_testcases" / f"test_{prog}.py").read_text(encoding="utf-8")
        checks = " ".join(f"☐ {c}" for c in _SUITE_CHOICES)
        lines += [
            f"## 套件 {idx}：{x['task_id']}__{x['arm']}__{x['model']}",
            "",
            "- 结构事实：该行最终代码未应用任何补丁（5 行未进入修复尝试 + 42 行一轮迭代未产出可应用补丁，行内 patch 字段为空）⇒ 声明通过建立在未修复的缺陷代码上，false fix 结构性成立。",
            "- 确认：☐ 我已核对该行确无补丁（若实有补丁 = 登记面错误，立即停下并记录）",
            f"- 形态标注（四选一，次口径）：{checks}",
            "- 备注：",
            "",
            "### buggy 源码（python_programs）",
            _code_block("python", buggy),
            "### gold fixed（参考答案）",
            _code_block("python", gold),
            "### gold 官方测试",
            _code_block("python", test),
            "### 最终生成测试（generated_test）",
            _code_block("python", x["generated_test"]),
        ]
    lines += [
        "---",
        "",
        "复核完成后：双人独立录入表交第三方 `e7_adjudication.py merge` 合并（κ + bootstrap CI + 混淆矩阵 + 分歧行清单）；"
        "套件轨标注合并后按修订注记登记描述性分布；再按 manifest 决策分支更新 `docs/preregistration.md` 执行记录表 E7 行。",
        "",
    ]
    return "\n".join(lines)


def _write_csv(path: Path, columns: tuple[str, ...], recs: list[dict[str, str]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(columns), lineterminator="\n")
        w.writeheader()
        w.writerows(recs)


def selftest() -> int:
    """解析器兼容性与出表函数的纯函数验证（不读真实数据）。"""
    # 解析器兼容性验证：候选标题/分层行格式必须与 e7_adjudication.parse_worksheet 对齐，
    # 套件轨标题不得混入候选集合。
    text = (
        "# t\n## 候选 1：quixbugs__gcd__aitester__deepseek-flash\n- 分层（evidence）：patch_track\nbody\n"
        "## 候选 2：quixbugs__gcd__single_agent__mimo-v2-6-pro\n- 分层（evidence）：patch_track\nbody\n"
        "## 套件 1：quixbugs__gcd__aitester__deepseek-flash\n- 结构事实：无补丁\n"
    )
    cands = parse_worksheet(text)
    assert [c["candidate_no"] for c in cands] == [1, 2], cands
    assert cands[0]["stratum"] == "patch_track", cands
    entry = render_entry_sheet(cands, "A")
    assert entry.splitlines()[0] == "candidate_no,task_id,stratum,judgment,reason,finished_at_utc,rater"
    assert len(entry.strip().splitlines()) == 3
    print("selftest OK: parse_worksheet/render_entry_sheet 兼容（2 候选 + 套件节不混入）")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="E7-r2 false-fix 判定行人工复核备料生成器（现行权威批次）")
    ap.add_argument("--sweep-dir", default=str(_SWEEP_DIR), help="权威批次 llm_sweep 目录")
    ap.add_argument("--data-root", default=None, help="quixbugs 数据根（默认 env > 缓存 > 仓库副本）")
    ap.add_argument("--out-dir", default=str(_DEFAULT_OUT), help="输出目录")
    ap.add_argument("--handoff-zip", default=None, help="交接 zip 输出路径（默认不打包）")
    ap.add_argument("--selftest", action="store_true", help="解析器兼容性自检（不读真实数据）")
    ns = ap.parse_args(argv)
    if ns.selftest:
        return selftest()

    sweep_dir = Path(ns.sweep_dir)
    data_root = resolve_data_root(ns.data_root)
    out_dir = Path(ns.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows, sources = enumerate_frame(sweep_dir)
    if not sources:
        raise SystemExit(f"守卫失败：{sweep_dir} 下未找到 *__quixbugs/INCREMENTAL_RESULTS.jsonl")
    verify_frame(rows, data_root)

    manifest = render_manifest(rows, sources, data_root, out_dir)
    worksheet = render_worksheet(rows, data_root)

    files: list[tuple[str, str]] = [("E7R2_FRAME_MANIFEST.md", manifest), ("E7R2_WORKSHEET.md", worksheet)]

    # 补丁轨录入表：复用 e7_adjudication 的解析器与模板生成（零改动复用）
    cands = parse_worksheet(worksheet)
    assert len(cands) == _EXPECTED_TOTALS["patch_track"], (
        f"解析器候选数 {len(cands)} ≠ {_EXPECTED_TOTALS['patch_track']}"
    )
    files.extend((f"E7R2_ENTRY_{rater}.csv", render_entry_sheet(cands, rater)) for rater in ("A", "B"))

    # 套件轨录入表
    suite_cols = ("candidate_no", "task_id", "confirmed", "annotation", "reason", "finished_at_utc", "rater")
    suite_rows = [x for x in rows if not x["patch"]]
    for rater in ("A", "B"):
        recs = [
            {
                "candidate_no": str(i),
                "task_id": f"{x['task_id']}__{x['arm']}__{x['model']}",
                "confirmed": "",
                "annotation": "",
                "reason": "",
                "finished_at_utc": "",
                "rater": rater,
            }
            for i, x in enumerate(suite_rows, start=1)
        ]
        buf_key = f"E7R2_SUITE_{rater}.csv"
        import io as _io

        buf = _io.StringIO()
        w = csv.DictWriter(buf, fieldnames=list(suite_cols), lineterminator="\n")
        w.writeheader()
        w.writerows(recs)
        files.append((buf_key, buf.getvalue()))

    for name, text in files:
        (out_dir / name).write_text(text, encoding="utf-8")

    sums = "".join(f"{_sha256_text(text)}  {name}\n" for name, text in sorted(files))
    (out_dir / "SHA256SUMS").write_text(sums, encoding="utf-8")

    print(
        f"frame: declared={_EXPECTED_TOTALS['declared']} false={_EXPECTED_TOTALS['false']} real={_EXPECTED_TOTALS['real']} "
        f"(patch_track={_EXPECTED_TOTALS['patch_track']} suite_track={_EXPECTED_TOTALS['suite_track']})"
    )
    print(f"out: {out_dir} （6 工件 + SHA256SUMS）")

    if ns.handoff_zip:
        zip_path = Path(ns.handoff_zip).expanduser()
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        proto = PROJECT_ROOT / "docs" / "HUMAN_ADJUDICATION_PROTOCOL.md"
        pregen = PROJECT_ROOT / "docs" / "preregistration.md"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            for name, _ in files:
                z.write(out_dir / name, arcname=f"e7_r2/{name}")
            z.write(out_dir / "SHA256SUMS", arcname="e7_r2/SHA256SUMS")
            z.write(proto, arcname="docs/HUMAN_ADJUDICATION_PROTOCOL.md")
            z.write(pregen, arcname="docs/preregistration.md")
        print(f"handoff zip: {zip_path} ({zip_path.stat().st_size:,} B)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
