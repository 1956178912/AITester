#!/usr/bin/env python3
"""DF（2026-10-26）：依赖漏洞**豁免过期**守卫——修复版一旦发布，`--ignore-vuln` 必须失效。

起因（本轮实测的事实）：本仓对 chromadb 1.5.9 的 5 条漏洞（PYSEC-2026-311 重复两条 +
3813 / 3814 / 3815）的处置方式，是让 `pip-audit` 带 `--ignore-vuln` 跑。这个写法有三个
让它「适合被一道锁钉住」的性质：

1. **豁免没有到期日**。`--ignore-vuln` 按 ID 匹配，与「当前是否有修复版本」无关；
   上游明天发布修复版，CI 明天照常绿。`docs/dependency_exemptions.md` 的「复审触发
   条件」是一句人话，没有任何可执行判据去检查它——这正是本轮要补的洞。
2. **豁免会把新事实一起吞掉**。CI 现有两步的真实职责是「新 advisory ⇒ 红」，但它们
   只看**未被忽略**的 ID；一旦某个 ID 进了忽略清单，它之后的 `fix_versions` 变化、
   甚至同一 ID 的语义修订，都不会再出现在阻断面上。
3. **豁免理由会随代码漂移**。登记表写的理由是「仅嵌入式 PersistentClient /
   EphemeralClient、无 HTTP 服务面、无 trust_remote_code」。这句话是安全结论的**前提**，
   但此前没有任何判据在读它：谁在 `src/` 里加一行 `chromadb.HttpClient` 或
   `trust_remote_code=True`，理由就自动变成假话，而豁免照旧生效。

判定面（两条独立通道）：

  1. **真实审计**（网络可用时）：跑 `pip-audit -r requirements.lock --format json`，
     **不带 `--ignore-vuln`**。退出码为 1 是「发现漏洞」的正常表现，不是失败——
     判据在 JSON 上，不在退出码上。
       - 审计命中但登记表没有的 ID ⇒ 红（新 advisory 未登记）；
       - 登记表有、审计命中且 `fix_versions` 非空 ⇒ 红（**豁免已过期**，升级后移除）；
       - 登记表的「锁定版本」与 `requirements.lock` 不一致 ⇒ 红（依赖变了，理由必须复审）；
       - 登记了但本次审计未命中的 ID ⇒ warning（advisory 撤回 / 已修复，去关闭登记）。
     pip-audit 缺席或网络不可用 ⇒ `[SKIP]` 披露（默认 rc=0；`--require-audit` 判红，
     「无法验证」不等于「通过」）。
  2. **可达性前提静态扫描**（不依赖网络，始终执行）：扫描 `src/**/*.py` 中**提到
     chromadb 的文件**，出现 `trust_remote_code` / `HttpClient` /
     `SimpleRBACAuthorizationProvider` / `chromadb.app` 任一 ⇒ 红。这四个 token 正是
     五条通告的触发面；命中即表示「仅嵌入式」的豁免前提已被推翻，必须重新评估而不是
     继续沿用旧理由。

口径诚实化：

  - 本门**不替代** CI 既有的两步 pip-audit（它们仍在装工具链的同一作业里、对
    requirements.txt 与 requirements.lock 分别阻断）；本门补的是**过期与理由**这一面。
  - 本门对网络失败只做披露、不静默通过；CI 以 `--require-audit` 运行。
  - `requirements.lock` / 登记表 / `src/` 三者任一家缺席 ⇒ 红（仓库级前提缺失，
    不是环境问题）。

用法：
    python scripts/gates/check_dependency_audit.py                  # 默认档（离线披露 [SKIP]）
    python scripts/gates/check_dependency_audit.py --require-audit  # 审计不可用即红（CI）
    python scripts/gates/check_dependency_audit.py --list           # 打印命中明细

退出码：0 = 通过（含 [SKIP] 披露）；1 = 存在未登记 / 过期 / 版本漂移 / 前提被推翻。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

LOCK = PROJECT_ROOT / "requirements.lock"
REGISTRY = PROJECT_ROOT / "docs" / "dependency_exemptions.md"
SRC = PROJECT_ROOT / "src"

_SECTION_TITLE = "## 当前豁免"
_LOCK_RE = re.compile(r"^(?P<name>[A-Za-z0-9_.-]+)==(?P<version>[^\s;]+)")
_VULN_TOKEN_RE = re.compile(r"(?P<full>[A-Z]{2,}-\d{4}-\d+)|/\s*(?P<bare>\d{3,5})\b")

#: 五条 chromadb 通告的触发面。命中即表示登记表的「仅嵌入式」前提不再成立。
_REACHABILITY_TOKENS: tuple[tuple[str, str], ...] = (
    ("trust_remote_code", "代码注入通告（CVE-2026-45829 / CVE-2026-45833）的前置条件"),
    ("HttpClient", "Chroma HTTP 客户端 ⇒ 连接远端服务器，偏离「仅嵌入式」前提"),
    ("SimpleRBACAuthorizationProvider", "多租户 RBAC 面（CVE-2026-45830 / CVE-2026-45831）"),
    ("chromadb.app", "Chroma 服务器应用面"),
)


@dataclass(frozen=True)
class Exemption:
    """登记表「当前豁免」节的一行。"""

    package: str
    version: str
    ids: tuple[str, ...]


@dataclass(frozen=True)
class AuditResult:
    """真实审计的结构化结果。

    status:
      - ``ok``          拿到可解析的 pip-audit JSON（退出码 1 只是「有漏洞」）
      - ``unavailable`` pip-audit 不在环境 / JSON 不可解析（网络失败也落这里）
    """

    status: str
    dependencies: list[dict] | None = None
    reason: str = ""


@dataclass
class Verdict:
    reds: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _section(text: str, title: str) -> str:
    """取 `## title` 到下一个 `## ` 之间的正文（标题缺席 ⇒ 空串）。"""
    lines: list[str] = []
    inside = False
    for raw in text.splitlines():
        if raw.strip().startswith("## "):
            if inside:
                break
            inside = raw.strip().startswith(title)
            continue
        if inside:
            lines.append(raw)
    return "\n".join(lines)


def _vuln_ids(cell: str) -> tuple[str, ...]:
    """从登记单元格取漏洞 ID。

    兼容 ``PYSEC-2026-3813 / 3814 / 3815`` 的合写：裸序号继承**最近一个完整 ID**
    的前缀（``PYSEC-2026``）。完整 ID 自身由前半支命中，不重复补全。
    """
    ids: list[str] = []
    prefix: str | None = None
    for match in _VULN_TOKEN_RE.finditer(cell):
        full = match.group("full")
        if full:
            prefix = full.rsplit("-", 1)[0]
            ids.append(full)
        elif prefix and match.group("bare"):
            ids.append(f"{prefix}-{match.group('bare')}")
    return tuple(dict.fromkeys(ids))


def _registry_exemptions(text: str) -> list[Exemption]:
    """解析登记表「当前豁免」节的表格行（表头 / 分隔行自动跳过）。"""
    entries: list[Exemption] = []
    for raw in _section(text, _SECTION_TITLE).splitlines():
        line = raw.strip()
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 3:
            continue
        package, version, id_cell = cells[0], cells[1], cells[2]
        if not package or package == "依赖" or set(version) <= set("-: "):
            continue
        ids = _vuln_ids(id_cell)
        if not ids:
            continue
        entries.append(Exemption(package=package, version=version, ids=ids))
    return entries


def _lock_versions(text: str) -> dict[str, str]:
    """`requirements.lock` 的 name → version（小写名，忽略注释行）。"""
    versions: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        match = _LOCK_RE.match(line)
        if match:
            versions[match.group("name").lower()] = match.group("version")
    return versions


def _run_audit(lock: Path | None = None, *, python: str | None = None, timeout: int = 300) -> AuditResult:
    """真跑 pip-audit（**不带** `--ignore-vuln`），把 JSON 与失败都变成结构化结果。"""
    lock_path = LOCK if lock is None else Path(lock)
    interpreter = python or sys.executable
    try:
        proc = subprocess.run(
            [
                interpreter,
                "-m",
                "pip_audit",
                "-r",
                str(lock_path),
                "--format",
                "json",
                "--progress-spinner",
                "off",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return AuditResult("unavailable", reason=f"pip-audit 超时（{timeout}s）")
    except OSError as exc:
        return AuditResult("unavailable", reason=f"pip-audit 启动失败：{exc}")

    try:
        payload = json.loads(proc.stdout or "")
    except json.JSONDecodeError:
        stderr_tail = (proc.stderr or "").strip().splitlines()[-1:] or ["（无 stderr）"]
        reason = f"pip-audit 未产出 JSON（rc={proc.returncode}）：{stderr_tail[0]}"
        if "No module named" in (proc.stderr or ""):
            reason = "pip-audit 不在当前解释器"
        return AuditResult("unavailable", reason=reason)

    dependencies = payload.get("dependencies")
    if not isinstance(dependencies, list):
        return AuditResult("unavailable", reason="pip-audit JSON 缺少 dependencies 列表")
    return AuditResult("ok", dependencies=dependencies)


def _collect_findings(dependencies: list[dict]) -> dict[str, tuple[str, str, set[str]]]:
    """漏洞 ID → (包名, 版本, 修复版本集合)。

    同一条 advisory 可能被 pip-audit 报告两次（本轮实测 PYSEC-2026-311 重复），
    按 ID 合并而不是按条目计数。
    """
    findings: dict[str, tuple[str, str, set[str]]] = {}
    for dep in dependencies:
        name = str(dep.get("name", ""))
        version = str(dep.get("version", ""))
        for vuln in dep.get("vulns") or []:
            vuln_id = str(vuln.get("id", ""))
            if not vuln_id:
                continue
            fixes = {str(fix) for fix in (vuln.get("fix_versions") or [])}
            if vuln_id in findings:
                findings[vuln_id][2].update(fixes)
            else:
                findings[vuln_id] = (name, version, fixes)
    return findings


def _judge(
    exemptions: list[Exemption],
    lock_versions: dict[str, str],
    dependencies: list[dict],
) -> Verdict:
    """把「登记表 × 锁定版本 × 审计结果」对成红/黄。"""
    verdict = Verdict()
    registered: dict[str, Exemption] = {}
    for entry in exemptions:
        for vuln_id in entry.ids:
            registered[vuln_id] = entry
        locked = lock_versions.get(entry.package.lower())
        if locked is None:
            verdict.reds.append(f"登记表的依赖 {entry.package} 不在 requirements.lock")
        elif locked != entry.version:
            verdict.reds.append(
                f"登记表锁定版本与 requirements.lock 不一致：{entry.package} {entry.version} → {locked}"
                "（依赖变了，豁免理由必须复审）"
            )

    findings = _collect_findings(dependencies)
    for vuln_id in sorted(set(findings) - set(registered)):
        name, version, _ = findings[vuln_id]
        verdict.reds.append(f"新漏洞未登记：{vuln_id}（{name} {version}）")
    for vuln_id in sorted(set(findings) & set(registered)):
        name, version, fixes = findings[vuln_id]
        entry = registered[vuln_id]
        if entry.package.lower() != name.lower():
            verdict.reds.append(f"漏洞 ID 的依赖与登记不一致：{vuln_id} 登记为 {entry.package}，审计命中 {name}")
        if fixes:
            verdict.reds.append(
                f"豁免已过期：{vuln_id}（{name} {version}）已有修复版本 {', '.join(sorted(fixes))}"
                " ⇒ 升级依赖并移除 ci.yml 的 --ignore-vuln 与登记表条目"
            )
    for vuln_id in sorted(set(registered) - set(findings)):
        verdict.warnings.append(
            f"登记豁免 {vuln_id} 本次审计未命中（advisory 已撤回或已修复）——复审后移入「已复审关闭」"
        )

    return verdict


def _reachability_hits(src_root: Path | None = None) -> list[tuple[str, str, str]]:
    """扫描提到 chromadb 的 src 文件，返回 (相对路径, token, 说明)。"""
    root = SRC if src_root is None else Path(src_root)
    hits: list[tuple[str, str, str]] = []
    if not root.is_dir():
        return hits
    for path in sorted(root.rglob("*.py")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "chromadb" not in text.lower():
            continue
        for token, why in _REACHABILITY_TOKENS:
            if token in text:
                hits.append((str(path.relative_to(root)), token, why))
    return hits


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="依赖漏洞豁免过期守卫")
    parser.add_argument(
        "--require-audit",
        action="store_true",
        help="真实审计不可用时判红（CI 用；默认档按 [SKIP] 披露并放行）",
    )
    parser.add_argument("--list", action="store_true", help="打印审计与登记明细")
    args = parser.parse_args(argv)

    registry_text = _read(REGISTRY)
    lock_text = _read(LOCK)
    if registry_text is None:
        print(f"[dependency-audit] ❌ 登记表缺席或不可读：{REGISTRY}")
        return 1
    if lock_text is None:
        print(f"[dependency-audit] ❌ 锁定文件缺席或不可读：{LOCK}")
        return 1
    if not SRC.is_dir():
        print(f"[dependency-audit] ❌ 源码目录缺席：{SRC}")
        return 1

    exemptions = _registry_exemptions(registry_text)
    lock_versions = _lock_versions(lock_text)
    registered_count = len({vuln_id for entry in exemptions for vuln_id in entry.ids})
    names = "、".join(f"{entry.package} {entry.version}" for entry in exemptions) or "（无）"
    print(f"[dependency-audit] 登记豁免：{names}，{registered_count} 个唯一 ID")

    reachability = _reachability_hits()
    if reachability:
        print("[dependency-audit] ❌ 豁免前提「仅嵌入式 / 无服务器面 / 无 trust_remote_code」已被推翻：")
        for relative, token, why in reachability:
            print(f"    src/{relative}: {token} —— {why}")
        print("[dependency-audit] 请重新评估五条 chromadb 通告的可达性，不要沿用旧理由。")

    audit = _run_audit()
    verdict = Verdict()
    if audit.status == "ok":
        dependencies = audit.dependencies or []
        total = len(dependencies)
        findings = _collect_findings(dependencies)
        print(f"[dependency-audit] 真实审计：OK（{total} 个依赖，{len(findings)} 个唯一漏洞 ID，未使用 --ignore-vuln）")
        verdict = _judge(exemptions, lock_versions, dependencies)
    else:
        print(f"[dependency-audit] 真实审计无法完成：{audit.reason}")

    for warning in verdict.warnings:
        print(f"[dependency-audit] [WARN] {warning}")

    if args.list:
        for vuln_id, entry in sorted({v: e for e in exemptions for v in e.ids}.items()):
            print(f"    {vuln_id}: {entry.package} {entry.version}")

    reds = verdict.reds + [f"可达性前提被推翻：src/{rel} 出现 {token}" for rel, token, _ in reachability]
    if reds:
        print("[dependency-audit] ❌ 判定失败：")
        for red in reds:
            print(f"    - {red}")
        return 1

    if audit.status != "ok":
        if args.require_audit:
            print("[dependency-audit] ❌ --require-audit：无法完成真实审计 ⇒ 不判绿（无法验证 ≠ 通过）")
            return 1
        print(
            "[dependency-audit] [SKIP] 未做真实漏洞审计（pip-audit / 网络不可用）——登记表与可达性扫描已执行，默认档放行"
        )
        return 0

    print("[dependency-audit] ✅ 审计命中全部已登记、无修复版本、版本未漂移、可达性前提成立")
    return 0


if __name__ == "__main__":
    sys.exit(main())
