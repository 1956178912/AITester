"""
数据集加载模块：支持 SWE-bench 和 Defects4J-Python 格式的标准数据集。

公开接口：
    from src.datasets import SWEBenchDataset, Defects4JPYDataset, load_dataset
    from src.datasets import SyntheticDataset  # 合成数据集生成器
"""

from src.datasets.dataset_loader import Defects4JPYDataset, SWEBenchDataset, load_dataset  # noqa: F401
from src.datasets.synthetic_dataset import SyntheticDataset  # noqa: F401
