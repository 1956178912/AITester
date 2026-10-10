"""仓库密钥卫生回归测试（R5 审查 2026-10-09，P0 SEC-01）。

回归背景（三条实证，均来自本次审查实测）：
    1. 工作树内曾存在 ``src/.env.local``（2680 B，含 ``LLM_10_API_KEY=sk-...``
       真实形态凭证），位于 **包目录 src/ 内**。该文件被 ``.gitignore:29``
       的 ``.env.local`` 模式覆盖（无分隔符模式匹配任意层级），故未入库、
       无历史泄露；但包目录内的凭证文件会带来两类真实风险：
         a) Docker 构建上下文：``.dockerignore`` 的 ``.env.*`` 同样是无分隔符
            模式，Docker patternmatcher 只匹配构建上下文根层级，嵌套副本
            不在排除范围内 → ``COPY . .`` 可将其打进镜像层；
         b) 打包分发：``src/`` 是 wheel 的内容来源目录，任何放宽 package-data
            或改用 ``COPY src`` 的改动都可能把凭证带进产物。
    2. 全部加载器实际只读取 **仓库根** 的 ``.env.local``：
       ``config.py::load_env_local()`` 用 ``dirname(abspath(__file__))``
       （config.py 在根 → 根路径），``src/config/config_manager.py`` 用
       ``Path(__file__).resolve().parents[2]``（src/config/ 的上两级 → 根）。
       即 ``src/.env.local`` 是**未被任何代码引用的遗留副本**，迁移零行为影响。
    3. 已执行的修复：文件迁至 ``.private/.env.local``，``.dockerignore`` 补
       ``**/.env`` / ``**/.env.*`` / ``**/config.local.example``，``.gitignore``
       补 ``.private/``。本测试锁定这三条不再退化。

设计口径（与 ADR-0003「默认关、新开关独立」同精神）：
    - 纯文件系统断言，零 LLM、零网络、零外部依赖；
    - 失败即阻断：这是安全门禁，不做 warn-only 降级。
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 包目录 / 分发内容来源目录：这些目录内**不得**出现任何本地凭证文件
_PROTECTED_DIRS = ("src", "examples", "experiments", "scripts")

# 凭证文件名形态（glob 口径，覆盖 .env / .env.local / .env.local.bak_g8 等）
_SECRET_GLOBS = (".env", ".env.*")

# .dockerignore 必须具备的任意深度排除模式（防根级模式漏掉嵌套副本）
_REQUIRED_DOCKERIGNORE_PATTERNS = ("**/.env", "**/.env.*")


def test_no_secret_files_inside_package_dirs():
    """受保护目录内不得残留任何 .env* 凭证文件（含任意后缀备份）。"""
    offenders: list[str] = []
    for d in _PROTECTED_DIRS:
        base = PROJECT_ROOT / d
        if not base.is_dir():
            continue
        for pattern in _SECRET_GLOBS:
            # 只拦截文件；.env.example 一类模板是允许的（且本项目根级才是模板）
            offenders.extend(str(p.relative_to(PROJECT_ROOT)) for p in base.rglob(pattern) if p.is_file())
    assert not offenders, (
        "以下受保护目录内发现凭证文件，须移出包目录并加入 .gitignore/.dockerignore: "
        f"{sorted(offenders)}（参考 2026-10-09 修订版审查 §9 SEC-01，见 CHANGELOG.md）"
    )


def test_dockerignore_covers_nested_env_files():
    """.dockerignore 必须显式覆盖任意深度的 .env*，不能只依赖根级模式。"""
    path = PROJECT_ROOT / ".dockerignore"
    assert path.is_file(), "缺少 .dockerignore，Docker 构建上下文将包含全部工作树文件"
    text = path.read_text(encoding="utf-8")
    lines = {ln.strip() for ln in text.splitlines()}
    missing = [p for p in _REQUIRED_DOCKERIGNORE_PATTERNS if p not in lines]
    assert not missing, (
        f".dockerignore 缺少任意深度排除模式 {missing}——"
        "无分隔符模式（如 .env.*）在 Docker patternmatcher 中只匹配构建上下文根层级，"
        "src/.env.local 一类嵌套副本会随 `COPY . .` 进入镜像层"
    )


def test_private_dir_is_gitignored():
    """.private/ 私有目录必须同时被 .gitignore 与 .dockerignore 覆盖。"""
    gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    dockerignore = (PROJECT_ROOT / ".dockerignore").read_text(encoding="utf-8")
    gi_lines = {ln.strip() for ln in gitignore.splitlines()}
    di_lines = {ln.strip() for ln in dockerignore.splitlines()}
    assert ".private/" in gi_lines or ".private" in gi_lines, (
        ".gitignore 未覆盖 .private/——该目录用于存放敏感工件，未忽略时 `git add -A` 存在误提交风险"
    )
    assert ".private" in di_lines, ".dockerignore 未覆盖 .private（镜像构建会带入私有工件）"
