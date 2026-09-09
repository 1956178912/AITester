"""
API 管理模块：智能多模型轮换、健康检查与自动故障转移。

公开接口：
    from src.api import APIManger, RotationStrategy

详见 api_manager.py。
"""

from src.api.api_manager import APIManger, RotationStrategy, print_status_table  # noqa: F401
