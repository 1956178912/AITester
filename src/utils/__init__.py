"""
通用工具模块包。

包含跨子包共享的基础工具：
    - helpers: 代码块/JSON 对象提取等文本处理工具
    - exceptions: 统一异常层次结构与重试/上下文装饰器
    - logging_utils: 日志敏感信息脱敏（SensitiveFilter）

注意：本文件是包标记文件（package marker），必须存在——
setuptools 的 find_packages() 只收集含 __init__.py 的目录，
缺失时 src.utils 不会被打入 pip 安装包，安装后导入会 ImportError。
"""
