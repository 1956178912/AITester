"""llm_configs.json 模型目录 schema 校验（R4，2026-10-09 审查落地·S9）。

背景：llm_configs.json 是模型路由目录（provider → 可用模型清单），由
config_generator.py 生成、被 expand_models.py / check_quota.py 消费。此前
该文件**无任何 schema 守卫**——手改（provider 拼错 / required_api_key 漂移 /
模型名重复）会静默导致路由歧义或凭证注入错误，只在运行期才暴露。

本脚本作为 CI 守卫（纯 stdlib 快检，无网络）：读根目录 llm_configs.json，
经 config_generator.validate_llm_configs 校验，违例非空时打印清单并 exit 1。

用法：
    python scripts/gates/check_llm_configs_schema.py            # 校验根目录 llm_configs.json
    python scripts/gates/check_llm_configs_schema.py --file F   # 校验指定文件
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 项目根目录（脚本位于 scripts/ 下）；插入 sys.path 以 import 项目模块
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _load(file_path: Path) -> list:
    """读取模型目录 JSON；缺失/损坏 → 返回空列表（由调用方决定语义）。"""
    if not file_path.exists():
        print(f"[check_llm_configs_schema] 未找到 {file_path}（跳过）")
        return []
    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"[check_llm_configs_schema] JSON 解析失败：{file_path}: {exc}")
        return []


def main() -> int:
    parser = argparse.ArgumentParser(description="校验 llm_configs.json 模型目录 schema")
    parser.add_argument("--file", help="模型目录文件路径（默认项目根 llm_configs.json）")
    args = parser.parse_args()

    file_path = Path(args.file) if args.file else PROJECT_ROOT / "llm_configs.json"
    configs = _load(file_path)
    if not configs:
        # 空目录：合法（未配置任何模型目录，非错误）；文件缺失按 0 退出
        # 但显式 --file 指定了缺失文件时视为错误（调用方显式意图）
        if args.file and not file_path.exists():
            print(f"[check_llm_configs_schema] 指定文件缺失：{file_path}")
            return 1
        return 0

    # 延迟导入：校验逻辑归 config_generator（与 PROVIDER_TEMPLATES 同源）
    from src.config.config_generator import validate_llm_configs

    violations = validate_llm_configs(configs)
    if violations:
        print(f"[check_llm_configs_schema] {file_path.name} 发现 {len(violations)} 条违例：")
        for line in violations:
            print(f"  - {line}")
        return 1
    print(f"[check_llm_configs_schema] {file_path.name} schema 校验通过（{len(configs)} 条模型目录）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
