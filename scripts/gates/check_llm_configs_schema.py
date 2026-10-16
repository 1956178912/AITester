"""llm_configs.json 模型目录 schema 校验（R4，2026-10-09 审查落地·S9）。

背景：llm_configs.json 是模型路由目录（provider → 可用模型清单），由
config_generator.py 生成、被 expand_models.py / check_quota.py 消费。此前
该文件**无任何 schema 守卫**——手改（provider 拼错 / required_api_key 漂移 /
模型名重复）会静默导致路由歧义或凭证注入错误，只在运行期才暴露。

本脚本作为 CI 守卫（纯 stdlib 快检，无网络）：读根目录 llm_configs.json，
经 config_generator.validate_llm_configs 校验，违例非空时打印清单并 exit 1。
G 轮（2026-10-16）：文件存在但**读不懂**（JSON 损坏 / 顶层非数组）同样
exit 1——此前返回空列表被当成"合法空目录"，损坏的模型目录能过门禁（假绿）。

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


def _load(file_path: Path) -> tuple[list | None, str]:
    """读取模型目录 JSON，把"读不出"的三种原因分开上报（G 轮 fail-closed）。

    Returns:
        ``(目录列表 | None, 状态)``，状态取值：

        - ``"missing"``：文件不存在——"未配置任何模型目录"，语义由调用方裁决；
        - ``"corrupt"``：JSON 解析失败（或不可读）——**不是**空目录，调用方
          必须 exit 1。此前这里返回 ``[]``，与"合法空目录"同形，损坏文件被判
          绿（门禁假绿）；
        - ``"wrong_type"``：顶层不是 JSON 数组（如手改成对象）——同上 fail-closed；
        - ``"ok"``：解析成功（可能为空数组）。
    """
    if not file_path.exists():
        return None, "missing"
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[check_llm_configs_schema] 文件存在但无法解析：{file_path}: {exc}")
        return None, "corrupt"
    if not isinstance(data, list):
        print(f"[check_llm_configs_schema] 顶层不是 JSON 数组（实际 {type(data).__name__}）：{file_path}")
        return None, "wrong_type"
    return data, "ok"


def main() -> int:
    parser = argparse.ArgumentParser(description="校验 llm_configs.json 模型目录 schema")
    parser.add_argument("--file", help="模型目录文件路径（默认项目根 llm_configs.json）")
    args = parser.parse_args()

    file_path = Path(args.file) if args.file else PROJECT_ROOT / "llm_configs.json"
    configs, status = _load(file_path)
    if status == "missing":
        # 缺失：默认路径下视为"未配置模型目录"（合法，exit 0）；显式 --file
        # 指定了缺失文件时视为错误（调用方显式意图）。
        if args.file:
            print(f"[check_llm_configs_schema] 指定文件缺失：{file_path}")
            return 1
        print(f"[check_llm_configs_schema] 未找到 {file_path}（未配置模型目录，跳过）")
        return 0
    if status != "ok":
        # G 轮 fail-closed：文件存在却读不懂 ≠ 空目录，一律判红。
        return 1
    if not configs:
        print(f"[check_llm_configs_schema] {file_path.name} 是空目录（合法：未配置任何模型）")
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
