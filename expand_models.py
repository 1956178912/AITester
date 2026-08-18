#!/usr/bin/env python3
"""
模型配置扩展脚本
用法：
    # 方式 1: 从 JSON 文件批量添加
    python expand_models.py --from-json models.json
    # 方式 2: 从 CSV 文件批量添加
    python expand_models.py --from-csv models.csv
    # 方式 3: 交互式添加
    python expand_models.py --interactive
    # 方式 4: 查看当前配置
    python expand_models.py --list
    # 方式 5: 查看帮助
    python expand_models.py --help
"""
import argparse
import csv
import json
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))
from src.config_manager import (
    add_llm_config,
    count_llm_configs,
    get_all_llm_configs,
    get_model_names,
    print_config_report,
)


def load_models_from_json(json_file: str) -> list[dict]:
    """从 JSON 文件加载模型配置"""
    with open(json_file, encoding='utf-8') as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    elif isinstance(data, dict) and "models" in data:
        return data["models"]
    else:
        raise ValueError("JSON 文件格式不正确，应为模型列表或包含 'models' 键的字典")
def load_models_from_csv(csv_file: str) -> list[dict]:
    """从 CSV 文件加载模型配置"""
    models = []
    with open(csv_file, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            models.append({
                "model_name": row.get("model_name", ""),
                "base_url": row.get("base_url", ""),
                "api_key": row.get("api_key", ""),
            })
    return models
def interactive_add():
    """交互式添加模型"""
    print("\n=== 交互式添加模型 ===\n")
    while True:
        print(f"当前已配置 {count_llm_configs()} 个模型\n")
        model_name = input("模型名称 (输入 'quit' 退出): ").strip()
        if model_name.lower() == 'quit':
            break
        if not model_name:
            print("错误：模型名称不能为空")
            continue
        base_url = input("API Base URL: ").strip()
        if not base_url:
            print("错误：Base URL 不能为空")
            continue
        api_key = input("API Key: ").strip()
        if not api_key:
            print("错误：API Key 不能为空")
            continue
        # 检查是否已存在
        existing_models = get_model_names()
        if model_name in existing_models:
            print(f"警告：模型 '{model_name}' 已存在，将跳过")
            continue
        # 添加配置
        success = add_llm_config(
            api_key=api_key,
            base_url=base_url,
            model_name=model_name
        )
        if success:
            print(f"✓ 成功添加模型: {model_name}")
        else:
            print(f"✗ 添加模型失败: {model_name}")
        print()
def cmd_list(args):
    """列出所有模型"""
    print_config_report()
    # 显示详细信息
    configs = get_all_llm_configs()
    print(f"\n详细配置 ({len(configs)} 个模型):\n")
    print(f"{'编号':<6} {'模型名称':<25} {'提供商':<20} {'状态':<10}")
    print("-" * 65)
    for idx, config in enumerate(configs, start=1):
        # 根据 URL 判断提供商
        if "dashscope" in config.base_url or "aliyuncs" in config.base_url:
            provider = "阿里云百炼"
        elif "agnes-ai" in config.base_url:
            provider = "Agnes AI"
        elif "bigmodel" in config.base_url:
            provider = "BigModel"
        elif "deepseek" in config.base_url:
            provider = "DeepSeek"
        else:
            provider = "未知"
        print(f"{idx:<6} {config.model_name:<25} {provider:<20} ✓ 有效")
def cmd_add(args):
    """添加单个模型"""
    success = add_llm_config(
        api_key=args.api_key,
        base_url=args.base_url,
        model_name=args.model_name
    )
    if success:
        print(f"✓ 成功添加模型: {args.model_name}")
        print(f"  当前总模型数: {count_llm_configs()}")
    else:
        print(f"✗ 添加模型失败: {args.model_name}")
        sys.exit(1)
def cmd_batch(args):
    """批量添加模型"""
    if args.json:
        models = load_models_from_json(args.json)
        source = f"JSON 文件: {args.json}"
    elif args.csv:
        models = load_models_from_csv(args.csv)
        source = f"CSV 文件: {args.csv}"
    else:
        print("错误：请指定 --json 或 --csv 文件")
        sys.exit(1)
    print(f"\n从 {source} 加载了 {len(models)} 个模型配置")
    print("开始批量添加...\n")
    success_count = 0
    fail_count = 0
    for i, model in enumerate(models, start=1):
        model_name = model.get("model_name", "")
        base_url = model.get("base_url", "")
        api_key = model.get("api_key", "")
        if not all([model_name, base_url, api_key]):
            print(f"[{i}/{len(models)}] ✗ 跳过不完整配置: {model}")
            fail_count += 1
            continue
        # 检查是否已存在
        existing_models = get_model_names()
        if model_name in existing_models:
            print(f"[{i}/{len(models)}] ⊘ 跳过已存在: {model_name}")
            continue
        success = add_llm_config(
            api_key=api_key,
            base_url=base_url,
            model_name=model_name
        )
        if success:
            print(f"[{i}/{len(models)}] ✓ 添加成功: {model_name}")
            success_count += 1
        else:
            print(f"[{i}/{len(models)}] ✗ 添加失败: {model_name}")
            fail_count += 1
    print("\n批量添加完成:")
    print(f"  成功: {success_count}")
    print(f"  失败: {fail_count}")
    print(f"  总计: {count_llm_configs()} 个模型")
def cmd_remove(args):
    """移除模型"""
    from src.config_manager import remove_llm_config
    success = remove_llm_config(args.model_name)
    if success:
        print(f"✓ 成功移除模型: {args.model_name}")
        print(f"  当前总模型数: {count_llm_configs()}")
    else:
        print(f"✗ 移除模型失败: {args.model_name}")
        sys.exit(1)
def main():
    parser = argparse.ArgumentParser(
        description="LLM 模型配置管理工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 列出所有模型
  python expand_models.py --list
  # 添加单个模型
  python expand_models.py --add --name qwen-max --url https://api.example.com/v1 --key sk-xxx
  # 批量添加（JSON）
  python expand_models.py --batch --json models.json
  # 批量添加（CSV）
  python expand_models.py --batch --csv models.csv
  # 交互式添加
  python expand_models.py --interactive
  # 移除模型
  python expand_models.py --remove qwen-max
        """
    )
    # 子命令
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    # list 命令
    subparsers.add_parser("list", help="列出所有模型")
    # add 命令
    add_parser = subparsers.add_parser("add", help="添加单个模型")
    add_parser.add_argument("--name", required=True, help="模型名称")
    add_parser.add_argument("--url", required=True, help="API Base URL")
    add_parser.add_argument("--key", required=True, help="API Key")
    # batch 命令
    batch_parser = subparsers.add_parser("batch", help="批量添加模型")
    batch_parser.add_argument("--json", help="JSON 配置文件路径")
    batch_parser.add_argument("--csv", help="CSV 配置文件路径")
    # remove 命令
    remove_parser = subparsers.add_parser("remove", help="移除模型")
    remove_parser.add_argument("model_name", help="要移除的模型名称")
    # interactive 命令
    subparsers.add_parser("interactive", help="交互式添加模型")
    args = parser.parse_args()
    if args.command == "list":
        cmd_list(args)
    elif args.command == "add":
        cmd_add(args)
    elif args.command == "batch":
        cmd_batch(args)
    elif args.command == "remove":
        cmd_remove(args)
    elif args.command == "interactive":
        interactive_add()
    else:
        parser.print_help()
if __name__ == "__main__":
    main()
