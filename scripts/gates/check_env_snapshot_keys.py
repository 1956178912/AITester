#!/usr/bin/env python
"""E-B / P0-2：环境开关 provenance 门禁（`_env_snapshot_keys` 完备性检查）。

背景（2026-10-10 E2 审查，已一手核验）：
    `experiments/run_benchmark.py` 的 `_env_snapshot_keys` 决定批次工件
    `provenance.env_snapshot` 收录哪些环境开关——它是"从工件证明干预是否
    生效"的**唯一**通道。已知三起事故均源于该清单不完备：

    1. `PLAN_STRIP_EXPECTED_OUTPUT_ENABLE`（A1 首跑）：开关未入快照 → 消融臂
       实际未生效却被当成"零效应"（假阴性）；
    2. `OVER_RED_SECTION_ENABLE`（D3）：首跑受控臂无 provenance 证据 → 只能
       重跑（工件标记 NOTVERIFIABLE）；
    3. `DETECTION_FIRST_SECTION_ENABLE`（RT1）：检出优先协议开关未登记，
       批间口径不可从工件审计。

    三起的共同机制：**代码新增了开关，快照清单没有同步**。本门禁把该动作
    从"人肉纪律"变为"CI 阻断"：源码里出现而快照缺失的开关 → exit 非 0。

扫描口径（AST，非正则）：
    - 扫描根默认 `src/`（`--scan-root` 可重复，例如附加 `config.py`）；
    - 收集以下调用形态的**字符串字面量**参数名：
        `os.getenv("X")` / `os.environ.get("X")` / `os.environ["X"]` /
        `os.environ.setdefault("X", ...)` / `_flag("X")` 及同类开关 helper；
      `from os import getenv` 后的裸 `getenv("X")` 亦识别；
    - 模块级 `_ENV* = "X"` 常量间接引用（`os.getenv(_ENV_FOO)`）会解析回
      字面量（与 `scripts/gates/check_env_budget.py` 同口径）；
    - 动态拼接（`os.getenv(f"{p}_ENABLE")` / 变量名）静态不可见——已知漏网面，
      本门禁是"名字集合的一致性检查"，不是开关完备性证明。

选择口径：
    - 默认只检查 `<NAME>_ENABLE` 形态的开关（`--select` 正则可改，
      `--all-keys` 等价于检查全部字面量环境变量名）；
    - 白名单文件（`--allow`，默认 `review_2026/E2_env_snapshot_allowlist.txt`，
      不存在即视为空）中的键不参与阻断，用于登记"有意不入快照"的键。

用法：
    python scripts/gates/check_env_snapshot_keys.py            # 人读报告
    python scripts/gates/check_env_snapshot_keys.py --json     # 机读（纯 JSON）
    python scripts/gates/check_env_snapshot_keys.py --all-keys  # 全量键（含非 _ENABLE）
    python scripts/gates/check_env_snapshot_keys.py --scan-root config.py

退出码：0 = 无缺失；1 = 存在缺失键（快照清单需同步）；2 = 解析错误。
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_FILE = PROJECT_ROOT / "experiments" / "run_benchmark.py"
SNAPSHOT_VAR = "_env_snapshot_keys"
DEFAULT_ALLOWLIST = PROJECT_ROOT / "review_2026" / "E2_env_snapshot_allowlist.txt"
DEFAULT_SCAN_ROOTS = ("src",)
# H1（2026-10-30）：除 `_ENABLE` 布尔开关外，还有**枚举型**载荷/档位开关
# （GENERATOR_PAYLOAD / ORACLE_CONTEXT_TIER）——它们同样改变臂间干预，
# 同样必须入 provenance 快照。
# 注意**不要**写成裸 `_TIER$`：`src/tools/patch_applier.py` 的 `CONTEXT_TIER`
# 是补丁重试降级链的**运行期内部变量**（由程序自己逐级改写），不是批次级
# 自变量；入快照只会记录"最后一个降级层"的瞬时值，是噪声而非审计证据。
DEFAULT_SELECT = r"(_ENABLE|_PAYLOAD|^ORACLE_CONTEXT_TIER)$"

# 开关 helper 名（项目约定：`_flag("X")` 等薄封装直接读 env）。任务书点名
# `_flag`；其余为同族命名，一并覆盖——新增 helper 时在此登记即可。
FLAG_HELPERS = frozenset(
    {
        "_flag",
        "_flags",
        "_env_flag",
        "env_flag",
        # 2026-10-17 J-2：opt-out 型守卫开关单一事实源。不收则该式调用点对本
        # 门禁完全不可见——同 check_env_budget.py 的 C/F 轮"新引用方式绕过治理"盲区族。
        "env_flag_opt_out",
        "_env_bool",
        "env_bool",
        "_bool_env",
        "bool_env",
        "_flag_enabled",
        "flag_enabled",
        "_is_flag_enabled",
        "is_flag_enabled",
        "_getenv_flag",
    }
)

# 模块级字符串常量值形态（形如环境变量名）——用于解析 `os.getenv(_CONST)`：
# 仅当该常量被用作 env 读取调用的名字实参时才解析（不解析则漏检
# `_GOLD_INJECTION_ENV = "FL_GOLD_INJECTION_ENABLE"` 这类非 _ENV 前缀常量）。
_ENV_NAME_VALUE_RE = re.compile(r"^[A-Z][A-Z0-9_]+$")
# 说明：早前口径只认 `_ENV*` 前缀常量（check_env_budget.py 的登记口径），
# 实测漏检 11 个 `*_ENABLE` 开关（如 DETECTION_SPECIFICITY_GATE_ENABLE /
# PATCH_EVIDENCE_GATE_ENABLE / FAULT_LOCALIZER_ENABLE），故放宽为"值形如
# 环境变量名的模块级字符串常量"，解析仍限定在 env 读取调用实参位置。


@dataclass(frozen=True)
class EnvSite:
    """一处字面量环境变量名的定义点。"""

    name: str
    path: str
    lineno: int
    kind: str
    default: str | None = None
    via_constant: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "file": self.path,
            "line": self.lineno,
            "kind": self.kind,
            "literal_default": self.default,
            "via_constant": self.via_constant,
        }


@dataclass
class SnapshotKeys:
    """`_env_snapshot_keys` 的静态提取结果。"""

    keys: list[str] = field(default_factory=list)
    mode: str = "missing"
    lineno: int | None = None
    note: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "file": _rel(SNAPSHOT_FILE),
            "variable": SNAPSHOT_VAR,
            "line": self.lineno,
            "mode": self.mode,
            "count": len(self.keys),
            "keys": self.keys,
            "note": self.note,
        }


def _rel(path: Path | str) -> str:
    """项目根相对路径（根外路径原样返回）。"""
    p = Path(path)
    try:
        return str(p.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(p)


def _str_const(node: ast.AST | None) -> str | None:
    """字符串字面量节点 → 值（非字面量 → None）。"""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _iter_source_files(scan_roots: list[str]) -> list[Path]:
    """展开扫描根为确定性排序的 .py 文件列表（文件 / 目录 / glob 均支持）。"""
    out: list[Path] = []
    for raw in scan_roots:
        p = Path(raw)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        if p.is_dir():
            out.extend(sorted(q for q in p.rglob("*.py") if q.is_file()))
        elif p.is_file():
            out.append(p)
        else:
            out.extend(sorted(q for q in PROJECT_ROOT.glob(raw) if q.is_file()))
    # 去重保序
    seen: set[Path] = set()
    uniq: list[Path] = []
    for q in out:
        rq = q.resolve()
        if rq not in seen:
            seen.add(rq)
            uniq.append(q)
    return uniq


def _module_env_constants(tree: ast.Module) -> dict[str, str]:
    """收集模块级字符串常量（值形如环境变量名）供间接引用解析。

    覆盖两种项目惯例：
    - `_ENV_FOO = "FOO_ENABLE"`（check_env_budget.py 登记口径）；
    - `_GOLD_INJECTION_ENV = "FL_GOLD_INJECTION_ENABLE"`（无 `_ENV` 前缀）。
    仅在该常量被用作 env 读取调用的第一实参时才生效，故不引入误报。
    """
    consts: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets: list[ast.expr] = list(node.targets)
            value = _str_const(node.value)
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
            value = _str_const(node.value)
        else:
            continue
        if value is None or not _ENV_NAME_VALUE_RE.match(value):
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                consts[target.id] = value
    return consts


def _os_aliases(tree: ast.Module) -> tuple[set[str], set[str]]:
    """识别 `from os import getenv` / `from os import environ` 的别名。"""
    getenv_aliases: set[str] = set()
    environ_aliases: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.module != "os":
            continue
        for alias in node.names:
            local = alias.asname or alias.name
            if alias.name == "getenv":
                getenv_aliases.add(local)
            elif alias.name == "environ":
                environ_aliases.add(local)
    return getenv_aliases, environ_aliases


def _resolve_arg(
    node: ast.AST | None,
    consts: dict[str, str],
) -> tuple[str, bool] | None:
    """调用实参 → (环境变量名, 是否经模块级常量间接引用)。"""
    direct = _str_const(node)
    if direct is not None:
        return direct, False
    if isinstance(node, ast.Name):
        resolved = consts.get(node.id)
        if resolved is not None:
            return resolved, True
    return None


def _classify_call(
    node: ast.Call,
    getenv_aliases: set[str],
    environ_aliases: set[str],
) -> str | None:
    """调用节点 → 形态标签（非环境变量读取 → None）。"""
    func = node.func
    if isinstance(func, ast.Attribute):
        base = func.value
        # os.getenv / os.environ.get / os.environ.setdefault
        if isinstance(base, ast.Name) and base.id == "os":
            if func.attr == "getenv":
                return "os.getenv"
            if func.attr in ("get", "setdefault"):
                # os.environ.get 在 AST 上是 Attribute(Attribute(os, environ), get)
                return f"os.environ.{func.attr}"
        if isinstance(base, ast.Attribute) and base.attr == "environ":
            inner = base.value
            if isinstance(inner, ast.Name) and inner.id == "os" and func.attr in ("get", "setdefault"):
                return f"os.environ.{func.attr}"
        if isinstance(base, ast.Name) and base.id in environ_aliases and func.attr in ("get", "setdefault"):
            return f"environ.{func.attr}"
        if func.attr == "getenv":
            return "os.getenv"
    elif isinstance(func, ast.Name):
        if func.id in getenv_aliases:
            return "getenv (from os import)"
        if func.id in FLAG_HELPERS:
            return f"{func.id}()"
    return None


def collect_env_sites(scan_roots: list[str]) -> dict[str, list[EnvSite]]:
    """AST 扫描扫描根，返回 环境变量名 → 定义点列表（含重复点，排序确定）。"""
    found: dict[str, list[EnvSite]] = {}
    for path in _iter_source_files(scan_roots):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError, OSError) as exc:  # pragma: no cover - 工程防御
            raise SystemExit(f"[env-snapshot] 解析失败 {path}: {exc}") from exc
        consts = _module_env_constants(tree)
        getenv_aliases, environ_aliases = _os_aliases(tree)
        rel = _rel(path)
        for node in ast.walk(tree):
            # os.environ["X"]（Subscript）
            if isinstance(node, ast.Subscript):
                value = node.value
                is_environ = (
                    isinstance(value, ast.Attribute)
                    and value.attr == "environ"
                    and isinstance(value.value, ast.Name)
                    and value.value.id == "os"
                ) or (isinstance(value, ast.Name) and value.id in environ_aliases)
                if is_environ:
                    resolved = _resolve_arg(node.slice, consts)
                    if resolved:
                        name, via_const = resolved
                        found.setdefault(name, []).append(
                            EnvSite(name, rel, node.lineno, "os.environ[]", None, via_const)
                        )
                continue
            if not isinstance(node, ast.Call):
                continue
            kind = _classify_call(node, getenv_aliases, environ_aliases)
            if kind is None or not node.args:
                continue
            resolved = _resolve_arg(node.args[0], consts)
            if not resolved:
                continue
            name, via_const = resolved
            default = _str_const(node.args[1]) if len(node.args) > 1 else None
            found.setdefault(name, []).append(EnvSite(name, rel, node.lineno, kind, default, via_const))
    for sites in found.values():
        sites.sort(key=lambda s: (s.path, s.lineno))
    return found


def _find_snapshot_assignment(tree: ast.Module, var: str) -> tuple[ast.AST | None, int | None]:
    """定位 `_env_snapshot_keys` 的赋值/声明节点。"""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == var:
                    return node.value, node.lineno
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == var
            and node.value is not None
        ):
            return node.value, node.lineno
    return None, None


def collect_snapshot_keys(snapshot_file: Path = SNAPSHOT_FILE, var: str = SNAPSHOT_VAR) -> SnapshotKeys:
    """静态提取 `_env_snapshot_keys` 的键集合。

    模式（写入输出的 `mode` 字段，供审计判断可信度）：
    - `literal_eval`：赋值为纯字面量列表/元组/字符串拼接 → 精确求值；
    - `literal-scan`：赋值含非常量元素（函数调用 / 变量）→ 退化为
      "赋值节点内字符串字面量扫描 + 全文件对该名字的 `.extend()/.append()`
      字面量收集"，并置 `note` 说明（可能多收/漏收）；
    - `missing`：文件中不存在该名字 → 空集（门禁将报全部缺失）。
    """
    path = Path(snapshot_file)
    if not path.exists():
        return SnapshotKeys(mode="missing", note=f"快照文件不存在：{_rel(path)}")
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    value, lineno = _find_snapshot_assignment(tree, var)
    if value is None:
        return SnapshotKeys(mode="missing", lineno=None, note=f"未找到 {var} 赋值")

    try:
        evaluated = ast.literal_eval(value)
    except (ValueError, SyntaxError, TypeError):
        evaluated = None
    if isinstance(evaluated, (list, tuple)) and all(isinstance(k, str) for k in evaluated):
        return SnapshotKeys(keys=list(evaluated), mode="literal_eval", lineno=lineno)

    # 退化路径：字面量扫描（赋值节点 + 对同一名字的 extend/append/+= 调用）
    literals: list[str] = []
    for node in ast.walk(value):
        text = _str_const(node)
        if text is not None:
            literals.append(text)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            base = node.func.value
            if isinstance(base, ast.Name) and base.id == var and node.func.attr in ("extend", "append"):
                for arg in node.args:
                    if node.func.attr == "append":
                        text = _str_const(arg)
                        if text is not None:
                            literals.append(text)
                    else:
                        for sub in ast.walk(arg):
                            text = _str_const(sub)
                            if text is not None:
                                literals.append(text)
    seen: set[str] = set()
    keys = [k for k in literals if not (k in seen or seen.add(k))]
    return SnapshotKeys(
        keys=keys,
        mode="literal-scan",
        lineno=lineno,
        note=f"{var} 赋值含非常量元素，退化为字面量扫描（可能多收/漏收）",
    )


def load_allowlist(path: Path | None) -> set[str]:
    """读白名单（缺省文件不存在 → 空集；`#` 起注释，逐行一个键）。"""
    if path is None or not Path(path).exists():
        return set()
    out: set[str] = set()
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            out.add(line)
    return out


def build_report(
    scan_roots: list[str],
    select: str,
    allowlist_path: Path | None,
    snapshot_file: Path = SNAPSHOT_FILE,
) -> dict[str, object]:
    """组装门禁报告（纯数据，便于 --json / Markdown 双消费）。"""
    sites = collect_env_sites(scan_roots)
    snapshot = collect_snapshot_keys(snapshot_file)
    allowed = load_allowlist(allowlist_path)
    pattern = re.compile(select)

    universe = sorted(name for name in sites if pattern.search(name))
    snapshot_set = set(snapshot.keys)
    missing = [name for name in universe if name not in snapshot_set and name not in allowed]
    suppressed = [name for name in universe if name not in snapshot_set and name in allowed]
    covered = [name for name in universe if name in snapshot_set]
    extra = sorted(snapshot_set - set(universe))

    missing_detail = []
    for name in missing:
        definitions = [s.as_dict() for s in sites[name]]
        files = sorted({str(s.path) for s in sites[name]})
        defaults = sorted({s.default for s in sites[name] if s.default is not None})
        missing_detail.append(
            {
                "key": name,
                "files": files,
                "definitions": definitions,
                "literal_defaults": defaults,
                "via_constant_only": all(s.via_constant for s in sites[name]),
            }
        )

    via_const_names = sorted(name for name in universe if any(s.via_constant for s in sites[name]))
    const_only_names = sorted(name for name in universe if all(s.via_constant for s in sites[name]))
    direct_site_names = sorted(set(universe) - set(const_only_names))
    missing_const_only = [d["key"] for d in missing_detail if d["via_constant_only"]]

    return {
        "gate": "check_env_snapshot_keys",
        "select": select,
        "scan_roots": [_rel(PROJECT_ROOT / r) if not Path(r).is_absolute() else r for r in scan_roots],
        "scanned_files": len(_iter_source_files(scan_roots)),
        "snapshot": snapshot.as_dict(),
        "allowlist": {
            "file": _rel(allowlist_path) if allowlist_path else None,
            "exists": bool(allowlist_path and Path(allowlist_path).exists()),
            "keys": sorted(allowed),
        },
        "counts": {
            "universe": len(universe),
            "universe_direct_site": len(direct_site_names),
            "universe_via_constant": len(via_const_names),
            "universe_constant_only": len(const_only_names),
            "snapshot_total": len(snapshot.keys),
            "covered": len(covered),
            "missing": len(missing),
            "missing_direct_site": len(missing) - len(missing_const_only),
            "missing_constant_only": len(missing_const_only),
            "missing_allowlisted": len(suppressed),
            "snapshot_extra": len(extra),
        },
        "missing": missing_detail,
        "missing_keys": missing,
        "suppressed": suppressed,
        "snapshot_extra": extra,
        "all_env_names": sorted(sites),
    }


def _emoji_free_status(report: dict[str, object]) -> str:
    """人读状态行（缺失清单按文件分组）。"""
    counts = report["counts"]
    assert isinstance(counts, dict)
    lines = [
        "[env-snapshot] 扫描 {} 个文件；开关全集 {} 个（select={}）".format(
            report["scanned_files"],
            counts["universe"],
            report["select"],
        ),
        "[env-snapshot] 快照 {} 个键（提取模式 {}，{}:{}）".format(
            counts["snapshot_total"],
            report["snapshot"]["mode"],  # type: ignore[index]
            report["snapshot"]["file"],  # type: ignore[index]
            report["snapshot"]["line"],  # type: ignore[index]
        ),
        "[env-snapshot] 已覆盖 {}；缺失 {}；白名单豁免 {}".format(
            counts["covered"],
            counts["missing"],
            counts["missing_allowlisted"],
        ),
    ]
    note = report["snapshot"]["note"]  # type: ignore[index]
    if note:
        lines.append(f"[env-snapshot] 提取说明：{note}")
    missing = report["missing"]
    assert isinstance(missing, list)
    if missing:
        by_file: dict[str, list[str]] = {}
        for item in missing:
            for f in item["files"]:
                by_file.setdefault(f, []).append(item["key"])
        lines.append("[env-snapshot] 缺失键（按定义文件分组）：")
        lines.extend(f"  {f}: {', '.join(sorted(by_file[f]))}" for f in sorted(by_file))
    extra = report["snapshot_extra"]
    assert isinstance(extra, list)
    if extra:
        lines.append(f"[env-snapshot] 提示：快照内 {len(extra)} 个键未在扫描面出现（信息项，不阻断）")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="环境开关 provenance 门禁：源码开关 ⊄ 快照清单 → exit 1",
    )
    parser.add_argument(
        "--scan-root",
        action="append",
        default=None,
        help=f"扫描根（文件/目录/glob，可重复；默认 {' '.join(DEFAULT_SCAN_ROOTS)}）",
    )
    parser.add_argument(
        "--select",
        default=DEFAULT_SELECT,
        help=f"参与检查的键名正则（默认 '{DEFAULT_SELECT}'）",
    )
    parser.add_argument(
        "--all-keys",
        action="store_true",
        help="等价于 --select '.*'（检查全部字面量环境变量名，含非 _ENABLE）",
    )
    parser.add_argument(
        "--allow",
        default=str(DEFAULT_ALLOWLIST),
        help=f"白名单文件（每行一个键，# 注释；默认 {_rel(DEFAULT_ALLOWLIST)}）",
    )
    parser.add_argument(
        "--snapshot-file",
        default=str(SNAPSHOT_FILE),
        help=f"含 {SNAPSHOT_VAR} 的文件（默认 {_rel(SNAPSHOT_FILE)}）",
    )
    parser.add_argument("--json", action="store_true", help="输出纯 JSON（供 CI / 报告消费）")
    args = parser.parse_args(argv)

    select = ".*" if args.all_keys else args.select
    report = build_report(
        scan_roots=list(args.scan_root) if args.scan_root else list(DEFAULT_SCAN_ROOTS),
        select=select,
        allowlist_path=Path(args.allow) if args.allow else None,
        snapshot_file=Path(args.snapshot_file),
    )

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(_emoji_free_status(report))
        missing = report["missing"]
        assert isinstance(missing, list)
        if missing:
            print("[env-snapshot] 阻断：缺失键须加入 _env_snapshot_keys（或登记白名单）", file=sys.stderr)
            for item in missing:
                print(f"  - {item['key']} @ {', '.join(item['files'])}", file=sys.stderr)

    return 1 if report["missing"] else 0


if __name__ == "__main__":
    sys.exit(main())
