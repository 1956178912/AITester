"""
lock 同步校验脚本：检查 requirements.txt 与 requirements.lock 是否一致。

校验规则：
1. requirements.txt 中的每个依赖项必须出现在 requirements.lock 中（按 PEP 503
   规范化名称匹配：小写，- 与 _ 等价）。
2. requirements.txt 中使用 == 锁定的版本必须与 lock 中的版本完全一致
   （防止"lock 更新了但 requirements 忘了改"或反向脱节）。
3. requirements.txt 中存在 >= 等未锁定版本时给出警告（提示锁定）。

用途：
- 本地：python scripts/check_lock_sync.py
- CI：作为独立步骤运行，失败即阻断合并（.github/workflows/ci.yml）

退出码：0 = 全部一致；1 = 存在错误（规则 1/2）；警告（规则 3）不影响退出码。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# 项目根目录 = 本脚本所在目录的上一级
PROJECT_ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS_FILE = PROJECT_ROOT / "requirements.txt"
LOCK_FILE = PROJECT_ROOT / "requirements.lock"


def normalize_name(name: str) -> str:
    """按 PEP 503 规范化包名：小写，- 与 _ 等价，连续 .-_ 合并为 -。"""
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_requirements(path: Path) -> dict[str, str | None]:
    """解析 requirements.txt，返回 {规范化包名: 版本约束或 None}。

    仅处理 `name==version` / `name>=version` 形式；跳过注释行、空行与
    不满足此格式的行（如 -e / -r 等 pip 指令）。
    """
    result: dict[str, str | None] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        # 去除行内注释（pip 允许 # 后跟注释）
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        match = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*([<>=!~].*)?$", line)
        if not match:
            continue
        name, constraint = match.group(1), (match.group(2) or "").strip()
        result[normalize_name(name)] = constraint or None
    return result


def parse_lock(path: Path) -> dict[str, str]:
    """解析 requirements.lock，返回 {规范化包名: 锁定版本}。"""
    result: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        match = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([A-Za-z0-9.!+_-]+)$", line)
        if match:
            result[normalize_name(match.group(1))] = match.group(2)
    return result


def main() -> int:
    """执行校验，打印报告，返回进程退出码（0 成功 / 1 失败）。"""
    for required in (REQUIREMENTS_FILE, LOCK_FILE):
        if not required.exists():
            print(f"✗ 缺少文件：{required.name}（请先生成：在 .venv 中 pip freeze > requirements.lock）")
            return 1

    requirements = parse_requirements(REQUIREMENTS_FILE)
    lock = parse_lock(LOCK_FILE)

    errors: list[str] = []
    warnings: list[str] = []

    # 规则 1 + 2：requirements 中的每项必须存在于 lock，且 == 锁定版本必须一致
    for name, constraint in sorted(requirements.items()):
        if name not in lock:
            errors.append(f"{name}: requirements.txt 中存在但 lock 中缺失")
            continue
        if constraint:
            match = re.match(r"^==\s*([A-Za-z0-9.!+_-]+)$", constraint)
            if match and lock[name] != match.group(1):
                errors.append(f"{name}: requirements 锁定 {match.group(1)}，lock 中为 {lock[name]}（版本脱节）")
            elif not match:
                # 规则 3：非 == 锁定形式（如 >=1.0.0），仅警告
                warnings.append(f"{name}: 使用 {constraint}（建议改为 == 锁定，版本将随上游漂移）")

    # 汇总
    print(f"lock 同步校验：requirements.txt（{len(requirements)} 项） vs requirements.lock（{len(lock)} 项）")
    for w in warnings:
        print(f"  ⚠ {w}")
    for e in errors:
        print(f"  ✗ {e}")

    if errors:
        print(f"结果：失败（{len(errors)} 个错误）。请同步两个文件后重试。")
        return 1
    print("结果：通过。requirements.txt 与 requirements.lock 保持一致。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
