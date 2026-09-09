"""
配置生成与管理模块。

公开接口（通过子模块直接导入）：
    from src.config.config_generator import generate_env_template, generate_config_json
    from src.config.config_manager import get_all_llm_configs, count_llm_configs

注意：config_manager 使用 sys.path 技巧导入项目根目录的 config.py，
为避免循环导入，不在此处批量导出。
"""

from src.config.config_generator import (  # noqa: F401
    generate_config_json,
    generate_env_template,
    print_model_catalog,
)
