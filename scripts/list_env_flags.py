"""环境变量开关清单工具：静态扫描 config.py 与 src/ 的 os.getenv 调用点。

背景（config.py R15 注释自述）：全仓环境变量开关散落各模块，导航成本高。
AITESTER_PROFILE 预设缓解了组合复杂度，但"某个开关叫什么 / 默认值是什么 /
定义在哪个文件 / 是否进了 profile 预设"仍无法一键查询。本脚本纯静态扫描
（ast + 正则，零 LLM、零网络、零行为副作用），产出按开关名去重排序的清单。

用法：
    .venv/bin/python scripts/list_env_flags.py                     # 全部开关（去重）
    .venv/bin/python scripts/list_env_flags.py --missing-profile   # 仅未进 profile 的
    .venv/bin/python scripts/list_env_flags.py --all               # 含重复出现位置
    .venv/bin/python scripts/list_env_flags.py --json              # JSON 输出

解析口径（保守，不臆测）：
    - 只匹配 os.getenv(NAME[, DEFAULT]) 与 os.environ.get(NAME[, DEFAULT])；
    - NAME 为字符串字面量直接取用；为标识符时回查同文件内 `NAME = "..."` 常量定义
      （如 _ENV_DSL = "SPEC_IR_DSL_ENABLE"），查不到则标注 `<const:NAME>`；
    - DEFAULT 仅取字符串字面量（None 记为未提供）；`.lower()` 等调用后缀不影响解析；
    - profile 归属经 ast.literal_eval 解析 config.py 的 _PROFILE_PRESETS 得到
      （纯数据，不执行 config.py）。
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

# 匹配 os.getenv(...) / os.environ.get(...)，name 可为字符串字面量或标识符，
# default 仅接受字符串字面量（含空串）；调用外的 .lower() 等后缀天然不进入捕获组。
_GETENV_RE = re.compile(
    r"os\.(?:getenv|environ\.get)\(\s*"
    r"(?P<name>\"[^\"]+\"|'[^']+'|[A-Za-z_]\w*)"
    r"(?:\s*,\s*(?P<default>\"[^\"]*\"|'[^']*'))?\s*\)"
)
# 同文件内字符串常量赋值（单行口径，覆盖 _ENV_* = "..." 形态）
_STR_CONST_RE = re.compile(r"^(?P<name>[A-Za-z_]\w*)\s*=\s*[\"'](?P<val>[^\"']*)[\"']")

ROOT = Path(__file__).resolve().parent.parent
SCAN_TARGETS: tuple[Path, ...] = (
    ROOT / "config.py",
    ROOT / "src",
)


def _scan_targets() -> list[Path]:
    """收集待扫描的 .py 文件（config.py + src/**/*.py，排除 __pycache__）。"""
    files: list[Path] = []
    for target in SCAN_TARGETS:
        if target.is_file():
            files.append(target)
        elif target.is_dir():
            files.extend(p for p in sorted(target.rglob("*.py")) if "__pycache__" not in p.parts)
    return files


def _load_profile_presets(config_path: Path) -> dict[str, list[str]]:
    """从 config.py 静态解析 _PROFILE_PRESETS → {flag: [profiles]} 反向映射。

    经 ast.parse + ast.literal_eval（不执行 config.py），失败时返回空映射
    （保守：不因预设解析失败阻断清单输出）。
    """
    try:
        tree = ast.parse(config_path.read_text(encoding="utf-8"))
    except (SyntaxError, OSError, ValueError):
        return {}
    for node in ast.walk(tree):
        # _PROFILE_PRESETS 为带类型注解赋值（AnnAssign），非普通 Assign——
        # 二者都处理，避免漏配导致 profile 归属全空
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign):
            targets, value = [node.target], node.value
        else:
            continue
        if not any(isinstance(t, ast.Name) and t.id == "_PROFILE_PRESETS" for t in targets):
            continue
        try:
            presets = ast.literal_eval(value)
        except (ValueError, TypeError):
            return {}
        if not isinstance(presets, dict):
            return {}
        flag_to_profiles: dict[str, list[str]] = {}
        for profile, flags in presets.items():
            if isinstance(flags, dict):
                for flag in flags:
                    flag_to_profiles.setdefault(str(flag), []).append(str(profile))
        return flag_to_profiles
    return {}


def _string_constants(text: str) -> dict[str, str]:
    """提取文件内单行字符串常量赋值（供 getenv 标识符参数回查）。"""
    constants: dict[str, str] = {}
    for line in text.splitlines():
        m = _STR_CONST_RE.match(line.strip())
        if m:
            constants[m.group("name")] = m.group("val")
    return constants


def _unquote(value: str | None) -> str | None:
    """去掉字符串字面量的引号；非字符串 / None 原样返回。"""
    if value is None:
        return None
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def collect_flags() -> list[dict[str, str]]:
    """扫描全部目标文件，返回开关记录列表（含重复出现位置）。"""
    profiles = _load_profile_presets(ROOT / "config.py")
    records: list[dict[str, str]] = []
    for path in _scan_targets():
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        constants = _string_constants(text)
        rel = str(path.relative_to(ROOT))
        for lineno, line in enumerate(text.splitlines(), start=1):
            for m in _GETENV_RE.finditer(line):
                raw_name = m.group("name")
                if raw_name is None:
                    continue
                if raw_name[0] in ("'", '"'):
                    name = _unquote(raw_name)
                else:
                    # 标识符参数：回查同文件常量定义；查不到 = 函数参数动态读取
                    # （如 _get_env_int(name)），非具体开关定义，跳过不纳入清单
                    name = constants.get(raw_name)
                    if name is None:
                        continue
                default = _unquote(m.group("default"))
                flag_profiles = profiles.get(name, [])
                records.append(
                    {
                        "name": name or "",
                        "default": default if default is not None else "",
                        "has_default": "yes" if default is not None else "no",
                        "file": rel,
                        "line": str(lineno),
                        "profiles": ",".join(sorted(flag_profiles)),
                    }
                )
    return records


def _dedupe(records: list[dict[str, str]]) -> list[dict[str, str]]:
    """按开关名去重（保留首次出现位置，其余位置并入 locations 计数）。"""
    seen: dict[str, dict[str, str]] = {}
    for rec in records:
        name = rec["name"]
        if name not in seen:
            seen[name] = dict(rec)
            seen[name]["locations"] = "1"
        else:
            seen[name]["locations"] = str(int(seen[name]["locations"]) + 1)
    return list(seen.values())


def _render(records: list[dict[str, str]]) -> str:
    """渲染为对齐文本表（终端友好）。"""
    if not records:
        return "（未发现任何 os.getenv 调用点）"
    header = ("开关名", "默认值", "有默认", "profiles", "位置数", "文件:行")
    rows = [
        (
            r["name"],
            r["default"] or "-",
            r["has_default"],
            r["profiles"] or "-",
            r.get("locations", "1"),
            f"{r['file']}:{r['line']}",
        )
        for r in records
    ]
    widths = [max(len(header[i]), *(len(row[i]) for row in rows)) for i in range(len(header))]
    line_fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    lines = [line_fmt.format(*header), "-" * (sum(widths) + 2 * (len(widths) - 1))]
    lines.extend(line_fmt.format(*row) for row in rows)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="环境变量开关清单（静态扫描 os.getenv）")
    parser.add_argument("--all", action="store_true", help="显示全部出现位置（含重复）")
    parser.add_argument("--missing-profile", action="store_true", help="仅显示未进任何 AITESTER_PROFILE 预设的开关")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = parser.parse_args(argv)

    records = collect_flags()
    if args.missing_profile:
        records = [r for r in records if not r["profiles"]]
    view = records if args.all else _dedupe(records)

    if args.json:
        print(json.dumps(view, ensure_ascii=False, indent=2))
    else:
        print(_render(view))
        print(
            f"\n共 {len(view)} 个开关（{'含重复位置' if args.all else '按名去重'}；扫描 {len(_scan_targets())} 个 .py 文件）"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
