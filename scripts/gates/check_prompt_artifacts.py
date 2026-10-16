#!/usr/bin/env python3
"""Instruction artifact 哈希锁门禁（EMSE / PROMPT-SE 复现纪律，零 LLM）。

## 为什么需要它

Instruction artifact 的复现底座必须是"**源码逐字抽取 + 哈希锁定**"：
prompt 改了而清单没刷新，就会重演本项目最熟悉的失败形态——**文档与工件静默分裂**。
本门禁把"prompt 变更"变成一次**显式动作**（与 `docs/env_budget.yaml` 的开关登记同款）。

## 判据

1. **逐 artifact 对账**：`experiments.prompt_artifacts.collect_artifacts()` 的实时
   `(id, sha256, chars)` 必须与清单工件（`experiments/results/prompt_artifacts_*/PROMPT_ARTIFACTS.json`）
   完全一致；
2. **集合对账**：清单不得含"已从登记表删除"的 artifact（防幽灵条目）；
3. **可执行性对账**：登记表里每个 artifact 的源位置必须仍可解析（本门禁即证明——
   抽取失败会直接抛异常而非静默跳过）。

## 缺清单时的行为

清单派生物不入 git（`experiments/results/**` 被忽略），故新鲜克隆下清单不存在：
- 默认（非 strict）：打印 `SKIP` 并以 **0** 退出——但**仍执行一次实时抽取**，
  使"登记表与源码是否可解析"在每次 CI 都被验证；
- `--strict`：清单缺失即失败（用于本地/发布自检，避免"没刷新也算绿"）。
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_MANIFEST_GLOB = "experiments/results/prompt_artifacts_*/PROMPT_ARTIFACTS.json"


def _rel(path: Path) -> str:
    """显示名：仓库内用相对路径，仓库外（如测试 tmp 目录）退化为绝对路径。

    与 artifact-doc-consistency 门禁同款守则：**显示名不得成为崩溃面**。
    """
    try:
        return str(path.relative_to(_REPO_ROOT))
    except ValueError:
        return str(path)


def _latest_manifest() -> Path | None:
    matches = sorted(glob.glob(str(_REPO_ROOT / _MANIFEST_GLOB)))
    return Path(matches[-1]) if matches else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Instruction artifact 哈希锁门禁（零 LLM）")
    parser.add_argument("--strict", action="store_true", help="清单缺失即失败（默认跳过）")
    parser.add_argument("--manifest", type=Path, default=None, help="显式指定清单工件")
    args = parser.parse_args(argv)

    from experiments.prompt_artifacts import collect_artifacts

    live = collect_artifacts()
    live_map = {row["id"]: row for row in live}
    print(f"  实时抽取：{len(live)} 个 artifact / {sum(r['chars'] for r in live)} 字符")

    manifest_path = args.manifest or _latest_manifest()
    if manifest_path is None or not manifest_path.is_file():
        message = f"未找到清单工件（{_MANIFEST_GLOB}）——请先运行 `python -m experiments.prompt_artifacts`"
        if args.strict:
            print(f"✗ [strict] {message}")
            return 1
        print(f"  [SKIP] {message}（非 strict 模式；实时抽取已验证登记表可解析）")
        return 0

    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"✗ 清单不可读：{manifest_path}（{type(exc).__name__}: {exc}）")
        return 1

    recorded = {row["id"]: row for row in payload.get("artifacts", [])}
    failures: list[str] = []
    for artifact_id, live_row in live_map.items():
        old = recorded.get(artifact_id)
        if old is None:
            failures.append(f"{artifact_id}：清单缺失该 artifact（新增后未刷新清单）")
            continue
        if old.get("sha256") != live_row["sha256"]:
            failures.append(
                f"{artifact_id}：sha256 不一致（清单 {str(old.get('sha256'))[:12]} vs "
                f"源码 {live_row['sha256'][:12]}，{old.get('chars')} → {live_row['chars']} 字符）"
            )
    failures.extend(f"{ghost}：幽灵条目（登记表已无此 artifact）" for ghost in sorted(set(recorded) - set(live_map)))

    if failures:
        print(f"✗ instruction artifact 哈希锁失败（{len(failures)} 项）：")
        for item in failures:
            print(f"    ✗ {item}")
        print("  处置：确认 prompt 变更后运行 `python -m experiments.prompt_artifacts` 刷新清单并随提交")
        return 1

    print(
        f"✓ instruction artifact 哈希锁通过：{len(live_map)} 个 artifact 与清单逐位一致（清单：{_rel(manifest_path)}）"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
