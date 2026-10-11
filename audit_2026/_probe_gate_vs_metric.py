"""T-B 临时分析脚本（只读复现，无 LLM）：
验证 detection_gates.specificity_verdict（运行时门）与
experiments._m1_metrics._compute_detection_rate（离线指标）在同一份
"收集错误"输入上的判定分歧。
不修改项目任何文件；只在临时目录写 pytest 材料。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from experiments._m1_metrics import _run_pytest_in_tmp  # noqa: E402
from src.tools.detection_gates import specificity_verdict  # noqa: E402

TARGET = "def f(x):\n    return x + 1\n"

# 形态 1：测试 import 一个不存在的伴生模块（跨文件任务的典型形态；
# 运行时门调用不传 task_metadata）
CROSS_FILE_TEST = "from module_a import helper\n\ndef test_t():\n    from module_b import f\n    assert f(1) == 2\n"

# 形态 2：测试自身语法错误（也是"没跑起来"）
BROKEN_TEST = "def test_t(:\n    assert True\n"

for label, test_code in (("cross_file_import", CROSS_FILE_TEST), ("syntax_error", BROKEN_TEST)):
    print(f"--- {label} ---")
    # a) 离线指标原语（M1 口径，无 metadata -> 单文件布局）
    res = _run_pytest_in_tmp(test_code, TARGET, "module_b", timeout=60, task_metadata=None)
    print("  _run_pytest_in_tmp rc =", None if res is None else res[0])
    from experiments._m1_metrics import _looks_like_test_execution_error

    if res is not None:
        print("  _looks_like_test_execution_error =", _looks_like_test_execution_error(res[0], res[1] + res[2]))
    # b) 运行时门判定（gate 不排除执行错误）
    verdict = specificity_verdict(test_code, TARGET, "module_b")
    print("  specificity_verdict =", verdict)
    print("  => detection_rate 语义下该行 = 0.0（或 None），门语义下 =", verdict)
