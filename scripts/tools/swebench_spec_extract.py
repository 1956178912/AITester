#!/usr/bin/env python3
"""swebench_spec_extract.py — 从官方 swebench 包提取权威安装 spec（零 LLM）。

对 SWE-bench Lite 300 逐 instance 调 ``make_test_spec``（官方 2.1.8 知识库），
提取每个 repo×version 线的安装 spec（conda python 版本 + pip 依赖 + 安装命令），
聚合落盘供 ``swebench_task_judge.py`` 的 DEP_LOCKS 使用——以官方 spec 替代
逐线手工考古。

用法：
    python experiments/scripts/tools/swebench_spec_extract.py \
        --dataset ~/.cache/aitester/swe_bench/swe_bench_lite_full_fields.jsonl \
        --out experiments/results/swebench_repo_checkout_20261029/SPEC_EXTRACT.json
"""

from __future__ import annotations

import argparse
import json
import sys
import types
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _stub_modal() -> None:
    """stub modal（swebench.harness 顶层强引 modal；spec 提取是纯函数不需要它）。"""

    class _Any:
        def __getattr__(self, name: str) -> Any:
            return _Any()

        def __call__(self, *args: Any, **kwargs: Any) -> Any:
            return _Any()

    for sub in ("container_process", "io_streams"):
        sys.modules[f"modal.{sub}"] = types.ModuleType(f"modal.{sub}")
    sys.modules["modal"] = _Any()


def _patch_requests_local_git() -> None:
    """monkeypatch ``requests.get``：raw.githubusercontent.com URL → 本地 clone 的 ``git show``。

    make_test_spec 在生成 env 脚本时要取 base/environment_setup commit 处的
    requirements.txt 等文件——企业代理拦截 GitHub raw（152/300 失败根因），
    而本机 REPO_CHECKOUT 已 clone 全部 12 repo 且 317 commit 全可达，直接本地读。
    """
    import subprocess

    import requests
    from swebench.harness.constants import SWE_BENCH_URL_RAW

    raw_prefix = SWE_BENCH_URL_RAW
    repos_root = Path.home() / ".cache/aitester/swe_bench/repos"

    class _Resp:
        def __init__(self, text: str, status: int):
            self.text = text
            self.status_code = status

    _orig_get = requests.get

    def _local_get(url: str, *args: Any, **kwargs: Any):
        if not str(url).startswith(raw_prefix):
            return _orig_get(url, *args, **kwargs)
        # URL 结构 = <raw>/<org>/<name>/<commit>/<path...>——repo 固定两段，
        # 不能用 maxsplit=2（会把 commit 段吞进 path）
        parts = str(url)[len(raw_prefix) :].split("/")
        if len(parts) < 4:
            return _Resp("", 404)
        repo_full = "/".join(parts[:2])
        commit, path = parts[2], "/".join(parts[3:])
        local = repos_root / repo_full.split("/")[-1]
        proc = subprocess.run(
            ["git", "-C", str(local), "show", f"{commit}:{path}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode == 0:
            return _Resp(proc.stdout, 200)
        return _Resp(proc.stderr[:200], 404)

    requests.get = _local_get  # type: ignore[assignment]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True, help="swe_bench_lite_full_fields.jsonl")
    ap.add_argument("--out", required=True, help="SPEC_EXTRACT.json 输出路径")
    args = ap.parse_args()

    _stub_modal()
    _patch_requests_local_git()
    from swebench.harness.test_spec import make_test_spec

    instances = [
        json.loads(line) for line in Path(args.dataset).read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    print(f"实例: {len(instances)}")

    # repo×version 线聚合（同线安装 spec 相同——官方按线复用环境）
    lines: dict[tuple[str, str], dict[str, Any]] = {}
    errors: list[dict[str, str]] = []
    for inst in instances:
        try:
            spec = make_test_spec(inst)
        except Exception as exc:
            errors.append({"instance_id": inst.get("instance_id", "?"), "error": str(exc)[:200]})
            continue
        # 官方 specs 原始字典（python/pip_packages/pre_install/install/test_cmd）
        # ——judge 的权威安装配方（venv 复刻 conda 的输入）
        import swebench.harness.constants as _C

        specs_raw = _C.MAP_REPO_VERSION_TO_SPECS.get(inst["repo"], {}).get(str(inst.get("version")), {})
        key = (inst["repo"], str(inst.get("version")))
        if key not in lines:
            lines[key] = {
                "repo": inst["repo"],
                "version": str(inst.get("version")),
                "env_setup_commit_sample": inst.get("environment_setup_commit", ""),
                # 2.1.8 TestSpec：setup_env_script = 完整可执行环境安装脚本
                # （conda python 版本 + 全部精确锁定依赖）；eval_script = 判定脚本。
                "setup_env_script": getattr(spec, "setup_env_script", "") or "",
                "eval_script": getattr(spec, "eval_script", "") or "",
                "specs": {
                    "python": specs_raw.get("python"),
                    "pip_packages": specs_raw.get("pip_packages", []),
                    "pre_install": specs_raw.get("pre_install", []),
                    "install": specs_raw.get("install", ""),
                    "test_cmd": specs_raw.get("test_cmd", ""),
                },
                "instance_count": 0,
            }
        lines[key]["instance_count"] += 1

    out = {
        "schema": "aitester_swebench_spec_extract/1",
        "source_package": "swebench==2.1.8 make_test_spec（官方安装知识）",
        "n_instances": len(instances),
        "n_lines": len(lines),
        "n_errors": len(errors),
        "errors": errors[:20],
        "lines": [
            {"repo": k[0], "version": k[1], **v}
            for k, v in sorted(lines.items(), key=lambda kv: (-kv[1]["instance_count"], kv[0]))
        ],
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(f"线数: {len(lines)} | 错误: {len(errors)} → {out_path}")
    for line in out["lines"][:6]:
        print(
            f"  {line['repo']}@{line['version']}: {line['instance_count']} 实例 | env 脚本 {len(line['setup_env_script'])} 字符"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
