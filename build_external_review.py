"""把主报告与 5 份审计报告合并为单一外部评审文件（幂等、可重跑）。

用法：.venv/bin/python build_external_review.py
产出：EXTERNAL_REVIEW_2026-10-11.md
"""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent
MAIN = ROOT / "FINAL_REVIEW_2026-10-11.md"
OUT = ROOT / "EXTERNAL_REVIEW_2026-10-11.md"

# (源文件, 附录字母, 附录标题)
APPENDICES: list[tuple[str, str, str]] = [
    (
        "audit_2026/T_A_claims_traceability.md",
        "A",
        "项目声明溯源审计（零 LLM 复算，90 条逐条复核）",
    ),
    (
        "audit_2026/T_B_code_domain_audit.md",
        "B",
        "Python 与领域机制独立代码审查",
    ),
    (
        "audit_2026/T_C_frontier_primary_sources.md",
        "C",
        "2025–2026 前沿基线一手来源重建（含失败端点与检索方法）",
    ),
    (
        "audit_2026/T_D_citation_verification.md",
        "D",
        "引用与前沿数字真实性核验（42 DOI + 72 arXiv ID）",
    ),
    (
        "audit_2026/T_E_adversarial_verification.md",
        "E",
        "对抗式验证记录（对主报告的独立复算与纠错）",
    ),
    (
        "audit_2026/lead_replay_seed_a.md",
        "F",
        "Lead 独立重放验证（repair 修正口径）",
    ),
]


def load(path: pathlib.Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def normalize_appendix(lines: list[str], letter: str) -> list[str]:
    """把审计报告的标题层级下移一级，并把 ##N / ###N 重编号为 ##X.N / ###X.N。"""
    out: list[str] = []
    in_fence = False
    for line in lines:
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            out.append(line)
            continue
        if not in_fence:
            m = re.match(r"^## (\d+)\.\s*(.*)$", line)
            if m:
                out.append(f"### {letter}.{m.group(1)} {m.group(2)}".rstrip())
                continue
            m = re.match(r"^### (\d+)\.(\d+)\s*(.*)$", line)
            if m:
                out.append(f"#### {letter}.{m.group(1)}.{m.group(2)} {m.group(3)}".rstrip())
                continue
            m = re.match(r"^#### (\d+)\.(\d+)\.(\d+)\s*(.*)$", line)
            if m:
                out.append(f"##### {letter}.{m.group(1)}.{m.group(2)}.{m.group(3)} {m.group(4)}".rstrip())
                continue
            # 表 X ｜ ... 形式的分节
            m = re.match(r"^## (表 \d+.*)$", line)
            if m:
                out.append(f"### {letter}·{m.group(1)}")
                continue
            m = re.match(r"^## (附.*)$", line)
            if m:
                out.append(f"### {letter}·{m.group(1)}")
                continue
            # 兜底：审计文件内部若残留一级标题，降为二级并加附录前缀，避免与
            # 合并文件的 "# 附录" 层级冲突
            if line.startswith("# ") and not line.startswith("## "):
                out.append(f"### {letter}·{line[2:].strip()}")
                continue
        out.append(line)
    # 丢弃源文件的一级标题（由合并器统一生成）
    while out and not out[0].strip():
        out.pop(0)
    if out and out[0].startswith("# "):
        out.pop(0)
        while out and not out[0].strip():
            out.pop(0)
    return out


def main() -> None:
    main_lines = load(MAIN)

    parts: list[str] = []

    # ---------- 外部评审导读 ----------
    parts.append(
        """# AITester 独立评审报告（外部评审版·单文件自包含）

> **文件性质**：单一自包含交付件。正文 = 独立评审报告；附录 A–F = 支撑该报告的**全部原始审计工件**，
> 每个数字均可回溯到附录中的具体表格、命令与工件路径。
> **评审对象**：`/Users/wangchenyu/Workspace/AITester`（Python，工作树 HEAD `d9e51df` + 33 个未提交修改文件）
> **评审日期**：2026-10-11 · **报告版本**：v1.1（外部评审版，含对抗式验证勘误）
> **总规模**：约 2.9 千行 / 26 万字符；含 1,252 行表格（约 60 张表）；附录 A–F 为完整审计工件。

---

## 给外部评审者的导读

### 这份报告的立场

本报告是一次**独立评审**：项目内既有的 6 份评审材料（9,654 行）与全部自评数字**均被当作"待验证声明"**，
不作为事实来源。项目侧每一个数字都由本次评审**直接解析原始工件**（`experiments/results/**/*.json`、
`*.trace.jsonl`）重新计算得到；前沿每一个数字都回溯到**一手来源**（arXiv 原文、Crossref 机读元数据、
SWE-bench 官方榜单仓库的逐条结果文件）。

### 证据分级（全文统一）

| 等级 | 定义 | 可用于 |
|---|---|---|
| **A** | 一手可逐条复算：原始工件逐位复算一致，或 arXiv/DOI 原文数值逐字命中且元数据经机读核验 | 独立支撑关键结论 |
| **B** | 一手存在但条件不完整（预印本、摘要级、付费墙、口径需限定） | 需交叉验证后方可支撑 |
| **C** | 二手（综述转述、博客、项目内引用） | 仅作参考，**不得单独支撑结论** |
| **D** | 不可验证 / 检索无命中 / 疑似不存在 | **不得支撑任何结论** |
| **E** | 推测（本报告仅用于 §6 的预期提升，且已逐条标注） | 必须标注为推测 |

### 三条阅读规则（避免误读本报告）

1. **分母纪律**：项目侧 detection/repair 一律区分三套分母 ——
   `all-task`（全部任务）/ `measurable`（有 gold 材料可测）/ `replayable`（可重放）。
   全文凡出现单值处，必在该段或表中注明分母。
2. **"不可比"不是"差"**：§5 对比矩阵中标注"否（无可比条件）"的维度，表示**项目与前沿的度量对象不同**
   （例如项目的 `spec_compile_rate` 度量"规约子句能否编译"，前限度量"生成的测试能否运行"），
   **不代表项目在该维度落后 400 倍**。
3. **负结果优先**：本项目最重要的发现是**推翻性的**。若你只想读结论，请读 §0，
   再读 §3.4（机制归因被推翻）、§3.7（真实基准结论不成立）、§11（既有评审逐条复核）。

### 如何独立验证（三步，零 LLM）

```bash
cd /Users/wangchenyu/Workspace/AITester

# 第 1 步：复算核心三臂指标（附录 A/E 的数字来源）
.venv/bin/python - <<'PY'
import json, glob
for f in sorted(glob.glob("experiments/results/main_batch/benchmark_synthetic_2026100[67]_*.json")):
    for arm, v in json.load(open(f))["results"].items():
        d = v["details"]
        print(f, arm,
              "det=",  sum(1 for x in d if x.get("detection_rate") == 1.0),
              "meas=", sum(1 for x in d if x.get("detection_rate") is not None),
              "rep1=", sum(1 for x in d if x.get("repair_rate") == 1.0))
PY

# 第 2 步：独立重放修复验证（约 200 秒；附录 F 的来源）
.venv/bin/python -m experiments.repair_replay \\
  experiments/results/main_batch/benchmark_synthetic_20261006_140906.json --arm aitester

# 第 3 步：抽查引用真实性（附录 D 的方法）
curl -s https://api.crossref.org/works/10.1145/3803418 | head -c 400
curl -s "https://export.arxiv.org/api/query?id_list=2609.09315" | head -c 400
```

### 已自曝的局限（请一并评估）

1. 本次评审**未调用任何 LLM API**，因此无法重跑实验，只能对**入库工件**做重算与重放；
2. 覆盖率声明（89% / 83%）因仓库 `.coverage` 退化而**无法验证**，已标 E 级；
3. 对抗式验证（附录 E）由 **Lead 自查**完成，**不构成完全第三方复核**——这正是本文件交付外部评审的原因；
4. **本报告经过两轮更正，痕迹均保留**：
   - 第一轮（自查）：§3.4.2 反事实分解口径算错（写成"88%"），已就地更正并留注记；
   - 第二轮（独立对抗式验证，附录 E）：查出 **S1 伪重复对齐方式错误**（143/261 → **252/261**）、**S2 门交叉表"例外"表述错误**（**真实分歧实为 0**）、**S3 oracle 普查 scope 错误**（1,803 → 全库 **2,015**）等 **10 项**，逐条更正见 **§17.1 勘误表**。
   - 若你发现本报告与附录数字不一致，**以原始工件复算为准**，并把差异反馈给我们——这正是本文件交付外部评审的目的。

### 目录与交叉引用映射

**正文（独立评审报告）**

| 节 | 内容 | 关键结论 |
|---|---|---|
| §0 | 执行摘要 | 独立评审声明、10 项关键发现（K1–K10）、数据可信度总览、**竞争位置判定** |
| §1 | 工作目录与文件清单 | 7,502 文件 / 103.5 MB；源码 122 文件 40,204 行；含自评数据的文件清单 |
| §2 | 项目理解与边界 | **项目实际身份 ≠ 任务书标签**（逻辑驱动/自修复未经证实）；7 条关键假设的红队判定 |
| §3 | 项目数据独立审计 | **14 条声明复核表**（P1–P16）；检出机制分解；修复口径；真实基准缺陷；伪重复；无法验证清单 |
| §4 | 2025–2026 前沿基线（一手重建） | 11 条测试生成基线 + 官方榜单逐条复算 + 自愈方向"基线未建立"判定 |
| §5 | 项目与前沿量化对比矩阵 | 14 维度 × 可否对比判定（**多数维度因口径不同不可比**） |
| §6 | 超越前沿方法设计 | 4 条路径（A 政策无关指标 / B 修复单调性 / C 求解器定向反例 / D 外部有效性），含**成功与失败判定标准** |
| §7 | 差距分析表 | 10 项能力差距 + 4 项问题定义差距 |
| §8 | Python 专项诊断表 | 12 项（含进程泄漏、类型门禁深度） |
| §9 | 领域专项诊断表 | 9 项 + **7 条红队反例** |
| §10 | 改进/优化/新增建议表 | P0 六条、P1 九条、P2 五条（均附 file:line、验证指标、时间线、命令） |
| §11 | 既有评审结论独立复核表 | 17 条（**支持 8 / 推翻 5 / 部分 4**） |
| §12 | 优化后的项目方案与路线图 | 定位重述、目录结构、T0–T3 路线图与 KPI |
| §13–§14 | 实验/验证计划、风险与合规 | 预注册要求、五步审计协议、12 项风险登记 |
| §15 | 待澄清问题 | 10 项（**不以假设填充**） |
| §16 | 参考来源 | 25 条一手来源 + 共识/争议/假设/推测分类 |
| §17–§18 | 可审计工件与复现指引、最终结论 | — |

**附录（原始审计工件）**

| 附录 | 内容 | 与正文的对应 |
|---|---|---|
| **A** | 项目声明溯源审计（90 条逐条复核，A43/B11/C12/D7/E17） | → §3 的完整证据链 |
| **B** | Python 与领域机制独立代码审查（13 条声称 vs 实现） | → §8、§9 的 file:line |
| **C** | 2025–2026 前沿基线一手重建（5 张分表 + 12 项交叉验证 + 失败端点） | → §4 的完整证据链 |
| **D** | 引用真实性核验（42 DOI + 72 arXiv ID + 15 项元数据错配 + 逐条更正文本） | → §11 C-12/C-13、§16 |
| **E** | 对抗式验证记录（584 行：对本报告 15 项核心数字的复算，**查出 3 项数据/口径/scope 错误 + 7 项表述问题**，全部已更正） | → §17.1 勘误表、全文可信度自检 |
| **F** | Lead 独立重放验证（repair 修正口径 54 行 → 20 correct） | → §3.5.1 |

---

### 本项目在 2025–2026 前沿格局中的位置（一句话）

> 项目在**能力维度**上不处于前沿（合成集检出低于其自身最强单提示基线；真实基准仅 50 个玩具程序），
> 且当前**不存在任何可验证的"超越前沿"证据**；但其**测量与实验方法学基础设施**（fail-closed 三态语义、
> provenance、工件校验、测量伪影自我披露）在同规模科研代码中属于稀缺资产——
> **这既是本次评审给出"不超越"判定的依据，也是 §6 四条路径唯一可能成立的基础。**

---
"""
    )

    # ---------- 正文 ----------
    # 主报告自带的 "# 标题" 降为二级，避免与合并文件的文件级标题同级
    if main_lines and main_lines[0].startswith("# "):
        main_lines[0] = "## 第一部分｜" + main_lines[0][2:].strip()
    parts.append("\n".join(main_lines).strip())
    parts.append("\n---\n\n# 第二部分｜附录（原始审计工件）\n")

    # ---------- 附录 ----------
    for rel, letter, title in APPENDICES:
        src = ROOT / rel
        if not src.exists():
            raise SystemExit(f"缺失源文件：{src}")
        body = normalize_appendix(load(src), letter)
        parts.append(
            f"\n---\n\n## 附录 {letter}｜{title}\n\n"
            f"> 源文件：`{rel}`（本附录为该文件的完整内容，仅调整标题层级与编号）\n"
        )
        parts.append("\n".join(body))
        parts.append("\n")

    # ---------- 文件清单 ----------
    parts.append(
        """
---

## 附：交付文件清单与规模

| 文件 | 角色 | 行数 |
|---|---|---|
| `EXTERNAL_REVIEW_2026-10-11.md` | **本文件**（外部评审版，自包含） | 2,894 |
| `FINAL_REVIEW_2026-10-11.md` | 主报告（不含附录） | 1,071 |
| `audit_2026/T_A_claims_traceability.md` | 附录 A 源 | 424 |
| `audit_2026/T_B_code_domain_audit.md` | 附录 B 源 | 366 |
| `audit_2026/T_C_frontier_primary_sources.md` | 附录 C 源 | 311 |
| `audit_2026/T_D_citation_verification.md` | 附录 D 源 | 482 |
| `audit_2026/T_E_adversarial_verification.md` | 附录 E 源 | 68 |
| `audit_2026/lead_replay_seed_a.md` | 附录 F 源 | 14 |
| `audit_2026/a*.py`（19 个） | 审计临时脚本（被附录 A 引用，供复算） | — |

**重建本文件**：`.venv/bin/python build_external_review.py`（幂等，可重跑）。

**工作树完整性声明**：本次评审**未修改项目任何源码、配置、测试或既有文档**；
新增内容仅为本报告、附录源文件与 `build_external_review.py`。
工作树中 33 个已修改文件与全部未跟踪项**均早于本次会话**（最新 mtime 2026-10-10 23:32）。
"""
    )

    OUT.write_text("\n".join(parts) + "\n", encoding="utf-8")
    n = OUT.read_text(encoding="utf-8").count("\n") + 1
    print(f"wrote {OUT.name}: {n} lines, {OUT.stat().st_size:,} bytes")  # noqa: T201


if __name__ == "__main__":
    main()
