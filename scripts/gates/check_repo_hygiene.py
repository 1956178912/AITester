#!/usr/bin/env python3
"""CX（2026-10-26）：仓库卫生守卫——**构建/测试临时产物不得被 git 跟踪**。

起因（本轮实测）：CW 轮的一次 pytest 运行把 `--basetemp` 落在仓库内的
`.tmp_pytest/`，而 `.gitignore` 只登记了 `.pytest_tmp/` 与 `.pytest_tmp*/`
**没有**登记 `.tmp_pytest/` ⇒ 12 个 pytest 临时文件（含 `.lock` 与
`pytest-current` 符号链接）被**提交进仓库**，随 v1.0.0 一同发布。

为什么值得单独设门：这类文件
  - 每次跑测试都在变 ⇒ 永久制造无意义的 diff；
  - `.lock` 与 `pytest-current` 是**符号链接**⇒ 在不同机器/容器上解引用目标不同
    ⇒ 跨平台检出会炸；
  - 它们是**别人的产物**（pytest 的），进版本库等于把工具的内部布局固化成本项目的
    公开契约。

判定面：被 git 跟踪的路径里，不得出现「缓存/临时」形态。规则按**路径分量**判定
（不是后缀）——`.log` 在 `experiments/results/` 下是**故意的证据工件**，不在禁列。

新增判定面（2026-10-26，用户口径「上传 GitHub 的只能是项目相关代码和必要的
说明性文档」）：**敏感/私有路径也不得被跟踪**。`.gitignore` 只约束未跟踪面——
一旦 `git add`（尤其 `-f`）就随提交上传，推送后内容进远端历史、无从撤回。故本
门禁增第二判据面，读同一个 `git ls-files`：顶层 `paper/`、`.private/`、`data/`、
`rag_data/`、`.qoder/`、`.workbuddy/`、`tmp_apr_baseline/`；文件 `.env`、
`.env.local`、`.env.local.bak*`、`.gitignore-sensitive`；以及学术/评审/投稿类
文档模式（见 `_PRIVATE_PATH_GLOBS` / `_PRIVATE_BASENAME_GLOBS`）。两级锚定都有
负例钉住：顶层锚定避免误伤 `docs/paper/`、`src/data/`；`docs/study/*_PREREG_*.md`
锚定避免误伤 `experiments/results/**/PREREG.md`（公开证据工件）。

口径：
  - 只看 `git ls-files`（已跟踪面），不看工作树（未跟踪文件由 .gitignore 管）；
  - 不设豁免表：缓存/临时文件进版本库没有正当理由；确有需要时应当**改名**成
    语义化的工件（如 `run_artifacts_<ts>/`）后再入库；
  - git 不可用 ⇒ 判红（无法验证 ≠ 通过）。

用法：
    python scripts/gates/check_repo_hygiene.py          # 审计，违规 exit 1
    python scripts/gates/check_repo_hygiene.py --list   # 打印命中的规则与路径

CI 接线：ci.yml test 作业（仅 3.14 档，纯 git 调用，与 Python 版本无关）。
"""

from __future__ import annotations

import argparse
import fnmatch
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

#: `git ls-files` 的正常耗时是毫秒级；60s 仍不返回即视为仓库被锁或 git 挂起。
_GIT_TIMEOUT_S = 60.0

#: (规则名, 命中说明, 判定函数)。判定函数收到「路径分量列表」。
#: 全部按**分量**判定：只有当某个分量整体等于（或匹配）该模式时才命中，
#: 避免 `foo/tmp_trace_notes.md` 这类正常文件名被误伤。
Rule = tuple[str, str, object]

#: 分量精确匹配（该分量整体等于此值即命中）。
_EXACT_COMPONENTS: tuple[tuple[str, str], ...] = (
    ("__pycache__", "Python 字节码缓存目录"),
    (".pytest_cache", "pytest 缓存目录"),
    (".tmp_pytest", "pytest --basetemp 落点（本轮实测被误提交 12 个文件）"),
    (".pytest_tmp", "pytest 专用 TMPDIR 沙箱"),
    (".tmp_run", "临时运行目录"),
    ("tmp_trace", "失败追踪残留（Makefile 有 clean-traces 目标）"),
    (".DS_Store", "macOS 目录元数据"),
    (".venv", "本地虚拟环境"),
    ("node_modules", "Node 依赖目录"),
)

#: 分量前缀匹配（该分量以此开头即命中）。
_PREFIX_COMPONENTS: tuple[tuple[str, str], ...] = (
    (".pytest_tmp", "pytest 专用 TMPDIR 沙箱（带后缀变体）"),
    (".coverage", "coverage 数据文件"),
)

#: 分量后缀匹配（**某个分量**以此结尾即命中）——如 `pkg.egg-info/` 这类目录分量。
_COMPONENT_SUFFIXES: tuple[tuple[str, str], ...] = ((".egg-info", "打包元数据目录"),)

#: 文件名后缀匹配（整条路径的最后一个分量以该后缀结尾即命中）。
_SUFFIX_COMPONENTS: tuple[tuple[str, str], ...] = (
    (".pyc", "Python 字节码"),
    (".pyo", "Python 优化字节码"),
)

#: 顶层目录禁跟踪（仅路径**第一段**整体等于该值才命中）。
#: 要么是敏感内容（论文源 / 私有审查 / 数据集 / 密钥），要么是工具生成物（可重建）。
_PRIVATE_TOP_LEVEL_DIRS: tuple[tuple[str, str], ...] = (
    ("paper", "论文 LaTeX 源与构建产物（双盲投稿纪律：不入公开仓）"),
    (".private", "私有隔离目录（论文/实验/审查的本地副本）"),
    ("data", "本地数据集（不入库，复现走下载入口）"),
    ("rag_data", "RAG 持久化检索库（本地生成，可再生）"),
    (".qoder", "Qoder 生成的 RepoWiki 知识（工具产物，可重建）"),
    (".workbuddy", "第三方工具工作记忆目录（运行时产物）"),
    ("tmp_apr_baseline", "APR 基线爬取缓存（一次性脚本产物）"),
)

#: 文件名禁跟踪（任意层级，末段整体相等）。
_PRIVATE_FILENAMES: tuple[tuple[str, str], ...] = (
    (".env", "真实环境变量文件（含 API Key）"),
    (".env.local", "本机 LLM 配置（含真实 API Key）"),
    (".gitignore-sensitive", "敏感文件清单（本地策略件）"),
)

#: 文件名前缀禁跟踪——`.env.local.bak_g8` 这类版本化备份曾含 22 条真实密钥。
_PRIVATE_FILE_PREFIXES: tuple[tuple[str, str], ...] = ((".env.local.bak", "密钥备份文件（历史泄漏面）"),)

#: 路径模式禁跟踪（相对仓库根的 glob）——学术/评审/投稿类文档。
_PRIVATE_PATH_GLOBS: tuple[tuple[str, str], ...] = (
    ("docs/study/OPTIMIZATION_APPENDIX_*.md", "投稿优化附录"),
    ("docs/study/*_PREREG_*.md", "预注册文档（论文数字未公开前的口径）"),
    ("docs/study/BATCH8_MUTK_VALIDITY_*.md", "批八变异体效度文档"),
    ("docs/study/GOLD_CONFORMANCE_*.md", "金标一致性预注册"),
    ("docs/study/PAPER_CONSISTENCY_AUDIT_*.md", "论文-源码一致性审计（含论文正文数字）"),
    ("docs/design/stvr_empirical_study_design.md", "研究设计文档"),
    ("docs/design/false_fix_caliber_matrix.md", "误修口径矩阵"),
    ("SPEC_REPLACE_AB_SCALE87_REPORT_*.md", "扩样实验报告"),
)

#: 文件名模式禁跟踪（任意层级）——`.gitignore` 里该模式本就未锚定。
_PRIVATE_BASENAME_GLOBS: tuple[tuple[str, str], ...] = (("INDEPENDENT_REVIEW_*.md", "独立审查报告"),)


def _private_hit_reason(parts: tuple[str, ...]) -> tuple[str, str] | None:
    """返回 (规则名, 命中说明)；敏感/私有路径命中，否则 None。"""
    if not parts:
        return None
    top = parts[0]
    if len(parts) > 1:
        for name, why in _PRIVATE_TOP_LEVEL_DIRS:
            if top == name:
                return (name + "/", why)
    last = parts[-1]
    for name, why in _PRIVATE_FILENAMES:
        if last == name:
            return (name, why)
    for prefix, why in _PRIVATE_FILE_PREFIXES:
        if last.startswith(prefix):
            return (prefix + "*", why)
    path = "/".join(parts)
    for pattern, why in _PRIVATE_PATH_GLOBS:
        if fnmatch.fnmatchcase(path, pattern):
            return (pattern, why)
    for pattern, why in _PRIVATE_BASENAME_GLOBS:
        if fnmatch.fnmatchcase(last, pattern):
            return (pattern, why)
    return None


def _hit_reason(parts: tuple[str, ...]) -> tuple[str, str] | None:
    """返回 (规则名, 命中说明)；未命中则 None。"""
    for name, why in _EXACT_COMPONENTS:
        if name in parts:
            return (name, why)
    for name, why in _PREFIX_COMPONENTS:
        if any(part.startswith(name) for part in parts):
            return (name, why)
    for name, why in _COMPONENT_SUFFIXES:
        if any(part.endswith(name) for part in parts):
            return (name, why)
    last = parts[-1] if parts else ""
    for name, why in _SUFFIX_COMPONENTS:
        if last.endswith(name):
            return (name, why)
    # 顶层 `venv/`（未带点的写法）也禁——避免与 `.venv` 规则重复登记。
    if parts and parts[0] == "venv":
        return ("venv", "本地虚拟环境（无点写法）")
    return None


def tracked_files(repo: Path) -> list[str]:
    """列出被 git 跟踪的文件（相对仓库根）。git 不可用或超时抛 RuntimeError。"""
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "ls-files", "-z"],
            capture_output=True,
            check=False,
            timeout=_GIT_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"`git ls-files` 超时（>{_GIT_TIMEOUT_S:g}s）——仓库可能被锁或 git 挂起") from exc
    except FileNotFoundError as exc:  # pragma: no cover - 环境无 git
        raise RuntimeError("git 不可用——无法核验跟踪面") from exc
    if proc.returncode != 0:
        raise RuntimeError(f"`git ls-files` 退出码 {proc.returncode}：{proc.stderr.decode('utf-8', 'replace').strip()}")
    out = proc.stdout.decode("utf-8", "replace")
    return [p for p in out.split("\0") if p]


def find_offenders(repo: Path) -> list[tuple[str, str, str]]:
    """返回 [(相对路径, 规则名, 说明)]。"""
    offenders: list[tuple[str, str, str]] = []
    for path in tracked_files(repo):
        parts = tuple(path.split("/"))
        hit = _hit_reason(parts)
        if hit is not None:
            offenders.append((path, hit[0], hit[1]))
    return offenders


def find_private_offenders(repo: Path) -> list[tuple[str, str, str]]:
    """返回被跟踪的敏感/私有路径 [(相对路径, 规则名, 说明)]。"""
    offenders: list[tuple[str, str, str]] = []
    for path in tracked_files(repo):
        hit = _private_hit_reason(tuple(path.split("/")))
        if hit is not None:
            offenders.append((path, hit[0], hit[1]))
    return offenders


def rule_inventory() -> list[tuple[str, str, str]]:
    """列出全部规则：[(类别, 规则名, 说明)]。`--list` 打印它。"""
    rows: list[tuple[str, str, str]] = []
    for name, why in _EXACT_COMPONENTS:
        rows.append(("分量精确匹配", name, why))
    for name, why in _PREFIX_COMPONENTS:
        rows.append(("分量前缀匹配", name, why))
    for name, why in _COMPONENT_SUFFIXES:
        rows.append(("分量后缀匹配", name, why))
    for name, why in _SUFFIX_COMPONENTS:
        rows.append(("末段后缀匹配", name, why))
    rows.append(("顶层目录精确匹配", "venv", "本地虚拟环境（无点写法）"))
    for name, why in _PRIVATE_TOP_LEVEL_DIRS:
        rows.append(("敏感/私有：顶层目录", name + "/", why))
    for name, why in _PRIVATE_FILENAMES:
        rows.append(("敏感/私有：文件名", name, why))
    for prefix, why in _PRIVATE_FILE_PREFIXES:
        rows.append(("敏感/私有：文件名前缀", prefix + "*", why))
    for pattern, why in _PRIVATE_PATH_GLOBS:
        rows.append(("敏感/私有：路径模式", pattern, why))
    for pattern, why in _PRIVATE_BASENAME_GLOBS:
        rows.append(("敏感/私有：文件名模式", pattern, why))
    return rows


#: `scripts/README.md` 里 gates 清单的小节标题形如 `## gates/（27 个）`。
_GATES_SECTION_RE = re.compile(r"^##\s+gates/（(\d+)\s*个）", re.M)
#: 清单里每一行形如 `| `check_xxx.py` | 说明 |`。
_GATES_ROW_RE = re.compile(r"^\|\s*`([^`]+)`\s*\|", re.M)


def check_gate_registry(repo: Path) -> list[str]:
    """判定面 B：`scripts/README.md` 的门禁清单必须**完整且与盘面一致**。

    起因（本轮实测）：`scripts/README.md` 的「## gates/（27 个）」与它自己的表格
    内部自洽（27 行），但**盘上已有 34 个门禁**——CF / CG / CH / BN / BK / CU 几轮
    新增的 7 道门从未登记进这张表。读者按文档找门禁，会漏掉其中 7 道；而**门禁
    数量本身**是文档里的一个手写数字，没有任何机制能发现它过期。

    三条判据：
      1. 盘上每个 `scripts/gates/*.py` 都必须出现在清单表格里；
      2. 小节标题里的个数必须等于盘上的实际个数；
      3. 表格行数必须等于标题里的个数（表与标题不能各说各话）。

    返回问题描述列表；空列表 = 通过。
    """
    problems: list[str] = []
    gates_dir = repo / "scripts" / "gates"
    actual = sorted(p.name for p in gates_dir.glob("*.py"))
    readme = repo / "scripts" / "README.md"
    if not readme.exists():
        return ["scripts/README.md 不在场——门禁清单无法对账"]
    text = readme.read_text(encoding="utf-8")

    header = _GATES_SECTION_RE.search(text)
    if not header:
        return ["scripts/README.md 里找不到「## gates/（N 个）」小节标题——门禁清单无法对账"]
    declared = int(header.group(1))

    # 只取 gates/ 小节**内部**的表格行：小节从标题行开始，到下一个 `## ` 为止。
    # （早先版本用全文正则，把 tools/ 等小节的表格行也算进来 ⇒ 行数虚高 35。）
    section_end = re.search(r"^##\s", text[header.end() :], re.M)
    section_text = text[header.end() : header.end() + section_end.start()] if section_end else text[header.end() :]
    rows = _GATES_ROW_RE.findall(section_text)
    registered = {name for name in rows if name.endswith(".py") and (gates_dir / name).exists()}

    missing = [name for name in actual if name not in registered]
    if missing:
        problems.append(f"scripts/README.md 的门禁清单漏登 {len(missing)} 道（盘上已存在）：{missing}")
    if declared != len(actual):
        problems.append(f"scripts/README.md 标题写「gates/（{declared} 个）」，盘上实有 {len(actual)} 个")
    if len(rows) != declared:
        problems.append(f"scripts/README.md 的门禁表有 {len(rows)} 行，标题写 {declared} 个——表与标题不一致")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="仓库卫生守卫：临时/缓存产物与敏感/私有路径不得被 git 跟踪")
    parser.add_argument(
        "--list",
        action="store_true",
        help="打印规则清单（不改变判定与退出码）",
    )
    args = parser.parse_args(argv)

    if args.list:
        print("[repo-hygiene] 规则清单（临时/缓存 + 敏感/私有）：")
        for kind, name, why in rule_inventory():
            print(f"  - [{kind}] {name}：{why}")

    failures: list[str] = []

    try:
        offenders = find_offenders(PROJECT_ROOT)
        private_offenders = find_private_offenders(PROJECT_ROOT)
    except RuntimeError as exc:
        print(f"[repo-hygiene] ❌ {exc}")
        return 1

    if offenders:
        print(f"[repo-hygiene] ❌ 被 git 跟踪的临时/缓存产物 {len(offenders)} 个：")
        for path, rule, why in offenders:
            print(f"  - {path}  （规则「{rule}」：{why}）")
        print("[repo-hygiene] 处置：`git rm --cached <路径>` 移出索引 + 把该目录名登记进 .gitignore。")
        failures.append(f"跟踪面内含 {len(offenders)} 个临时/缓存产物")

    if private_offenders:
        print(f"[repo-hygiene] ❌ 被 git 跟踪的敏感/私有路径 {len(private_offenders)} 个：")
        for path, rule, why in private_offenders:
            print(f"  - {path}  （规则「{rule}」：{why}）")
        print(
            "[repo-hygiene] 处置：`git rm --cached <路径>` 移出索引；若已推送，内容已进远端历史，须按泄漏处置流程重写历史。"
        )
        failures.append(f"跟踪面内含 {len(private_offenders)} 个敏感/私有路径")

    registry_problems = check_gate_registry(PROJECT_ROOT)
    for problem in registry_problems:
        print(f"[repo-hygiene] ❌ {problem}")
    failures.extend(registry_problems)

    if failures:
        return 1

    print("[repo-hygiene] ✅ 跟踪面内无临时/缓存产物或敏感/私有路径；门禁清单与盘面一致。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
