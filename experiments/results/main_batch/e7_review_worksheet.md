# E7 修复上限人工复核工作表（AP1，2026-10-07）

- 数据来源（与 e7_repair_sample_candidates.md 同参同序）：3 个批次
- 抽样参数：fraction=10%（每层 ceil 上取整）、seed=42（确定性，与候选清单同 seed 同参复算一致）
- 判定口径（预注册 E7 五选一）：equivalent / plausible_overfit / wrong_location / test_only / incomplete
- 判定规则：equivalent 占比 > 0 → repair 口径存在低估，须勘误并给出修正后上界；= 0 → repair=0 为真零（上限卡在合理性与 gold 正确性）
- 整文件替换口径提示：patch 正文即补丁应用后的完整文件——与 gold fixed 逐行对照；差异分类示例见各节"判定提示"

## 候选 1：s42__synthetic__task_0044

- 分层（evidence）：sbfl ｜ stop_reason：max_iterations ｜ error_category：assertion ｜ iterations：3
- 缺陷模式：type_int_str_key_contract（bug_type=assertion，difficulty=4）
- 人工判定：☐ equivalent ☐ plausible_overfit ☐ wrong_location ☐ test_only ☐ incomplete
- 判定提示：patch vs gold fixed 逐行对照；仅注释/格式/docstring 差异 → equivalent；改写测试而非源码 → test_only；改动不在缺陷位置 → wrong_location；未消除触发条件 → incomplete

### 生成补丁（patch）
````python
python
_STOCK = {}

def add_item(sku: int, qty: int) -> None:
    try:
        qty = int(qty)
    except ValueError:
        qty = int(float(qty))
    _STOCK[sku] = qty

def stock_of(sku: str) -> int:
    return int(_STOCK.get(sku, 0))
# noise_seed=3470

````

### gold fixed（参考答案，task_metadata.fixed）
````python
_STOCK = {}

def add_item(sku: int, qty: int) -> None:
    _STOCK[sku] = qty

def stock_of(sku: str) -> int:
    return _STOCK.get(int(sku), 0)
````

### gold 官方测试（task_metadata.test_cases）
````python
from task_0044 import add_item, stock_of, _STOCK

def test_add_then_query():
    add_item(42, 7)
    assert stock_of("42") == 7

def test_unknown_sku_zero():
    assert stock_of("999") == 0

def test_key_type_contract():
    add_item(7, 1)
    assert 7 in _STOCK and isinstance(next(iter(_STOCK)), int)
````

### 最终生成测试（generated_test，检出裁决者）
````python
import pytest
from task_0044 import add_item, stock_of, _STOCK


@pytest.fixture(autouse=True)
def reset_stock():
    """在每个测试前清空全局库存，确保测试独立。"""
    _STOCK.clear()
    yield
    _STOCK.clear()


def test_add_item_and_stock_of_normal_write_read():
    """
    正常写入并读取：add_item(1, 10) 应返回 None，_STOCK[1] 应为 10，
    stock_of(1) 应返回 10。
    """
    result = add_item(1, 10)
    assert result is None
    assert _STOCK[1] == 10
    assert stock_of(1) == 10


def test_add_item_overwrite_same_sku():
    """
    同一 sku 重复写入应覆盖旧值，且字典键数量不增加。
    """
    add_item(1, 10)
    add_item(1, 5)
    assert _STOCK[1] == 5
    assert len(_STOCK) == 1


def test_add_item_multiple_skus_independent():
    """
    多个 sku 应相互独立存储。
    """
    add_item(1, 10)
    add_item(2, 20)
    assert _STOCK[2] == 20
    assert _STOCK[1] == 10


def test_add_item_and_stock_of_zero_sku_qty():
    """
    sku=0 且 qty=0 的边界情况：应正确存储和读取，尽管 0 与默认值无法区分。
    """
    add_item(0, 0)
    assert _STOCK[0] == 0
    assert stock_of(0) == 0


def test_add_item_negative_sku_qty():
    """
    负数 sku 和负数数量应被原样存储和返回。
    """
    add_item(-1, -5)
    assert _STOCK[-1] == -5
    assert stock_of(-1) == -5


def test_add_item_large_integers():
    """
    超大整数（Python 任意精度）应无溢出地存储和读取。
    """
    sku = 2 ** 70
    qty = 10 ** 30
    add_item(sku, qty)
    assert _STOCK[sku] == qty
    assert stock_of(sku) == qty


def test_stock_of_missing_key_returns_zero():
    """
    stock_of 查询未写入的键应返回默认值 0。
    """
    assert stock_of(999) == 0


def test_stock_of_empty_stock_returns_zero():
    """
    空库存上查询任意键应返回 0。
    """
    assert len(_STOCK) == 0
    assert stock_of(1) == 0


def test_stock_of_str_query_for_int_key_returns_zero():
    """
    用 str 查询用 int 写入的键：'1' 与 1 不相等，应返回 0。
    暴露 add_item(sku:int) 与 stock_of(sku:str) 注解矛盾。
    """
    add_item(1, 10)
    assert stock_of('1') == 0


def test_stock_of_none_returns_zero():
    """
    stock_of(None) 应返回默认值 0（None 可哈希且未写入）。
    """
    assert stock_of(None) == 0


def test_add_item_unhashable_sku_raises_type_error():
    """
    不可哈希的 sku 应引发 TypeError。
    """
    with pytest.raises(TypeError):
        add_item([], 1)


def test_add_item_non_int_qty_stock_of_return_type():
    """
    当 qty 为非 int（违反注解）时，stock_of 的返回值违反其 -> int 返回类型注解。
    根据 stock_of 的签名，它应返回 int；当前实现返回字符串，故此测试失败。
    期望值来源：stock_of 的返回类型注解 -> int。
    """
    add_item(3, "many")
    assert _STOCK[3] == "many"
    result = stock_of(3)
    assert isinstance(result, int), f"stock_of 声明返回 int，但实际返回了 {type(result).__name__}"
````

### patch vs gold fixed 逐行差异（AQ1 增补：difflib unified diff，机械对比——判定仍属人工）
````diff
--- patch（补丁应用后）
+++ gold_fixed（参考答案）
@@ -1,13 +1,7 @@
-python
 _STOCK = {}
 
 def add_item(sku: int, qty: int) -> None:
-    try:
-        qty = int(qty)
-    except ValueError:
-        qty = int(float(qty))
     _STOCK[sku] = qty
 
 def stock_of(sku: str) -> int:
-    return int(_STOCK.get(sku, 0))
-# noise_seed=3470
+    return _STOCK.get(int(sku), 0)
````

## 候选 2：s42__synthetic__task_0013

- 分层（evidence）：sbfl ｜ stop_reason：max_iterations ｜ error_category：patch_validation_failed ｜ iterations：3
- 缺陷模式：sqrt_negative_input（bug_type=runtime，difficulty=1）
- 人工判定：☐ equivalent ☐ plausible_overfit ☐ wrong_location ☐ test_only ☐ incomplete
- 判定提示：patch vs gold fixed 逐行对照；仅注释/格式/docstring 差异 → equivalent；改写测试而非源码 → test_only；改动不在缺陷位置 → wrong_location；未消除触发条件 → incomplete

### 生成补丁（patch）
````python
python
def sqrt(x: float) -> float:
    if x < 0:
        raise ValueError("math domain error")
    if x == 0:
        return 0
    return x ** 0.5
# noise_seed=2621

````

### gold fixed（参考答案，task_metadata.fixed）
````python
def sqrt(x: float) -> float:
    if x < 0:
        raise ValueError("不能对负数开平方")
    if x == 0:
        return 0
    return x ** 0.5
````

### gold 官方测试（task_metadata.test_cases）
````python
from task_0013 import sqrt

def test_sqrt_positive():
    import math
    assert abs(sqrt(4) - 2.0) < 1e-9

def test_sqrt_zero():
    assert sqrt(0) == 0

def test_sqrt_negative():
    import pytest
    with pytest.raises(ValueError):
        sqrt(-1)
````

### 最终生成测试（generated_test，检出裁决者）
````python
"""pytest 测试：task_0013.sqrt

被测函数：

    def sqrt(x: float) -> float:
        if x == 0:
            return 0
        return x ** 0.5

测试期望值来源说明：
  * 正数用例的期望值来自测试计划给出的用例期望值，并与 math.sqrt 交叉验证；
  * 返回类型 float 的期望来自函数签名的类型注解 `-> float` 与计划中的输出域规约；
  * 负数输入的期望（抛 ValueError）来自数学规约：实数平方根的定义域为 x >= 0，
    与标准库 math.sqrt 的异常约定一致。
"""

import math

import pytest

from task_0013 import sqrt


# ---------------------------------------------------------------------------
# 正常 / 边界：正数输入，覆盖 not (x == 0) 分支
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "x, expected",
    [
        (4.0, 2.0),
        (2.25, 1.5),
        (9.0, 3.0),
        (1e308, 1e154),
        (1e-308, 1e-154),
    ],
)
def test_sqrt_positive_matches_math_sqrt(x, expected):
    """正数输入应返回其平方根，且与 math.sqrt 一致。

    期望值来源：测试计划用例期望值 + 数学定义（sqrt 即 math.sqrt）。
    """
    result = sqrt(x)
    assert math.isclose(result, expected, rel_tol=1e-12, abs_tol=0.0)
    assert math.isclose(result, math.sqrt(x), rel_tol=1e-12, abs_tol=0.0)


@pytest.mark.parametrize("x", [0.25, 2.0, 100.0, 1.0e10])
def test_sqrt_result_squared_restores_input(x):
    """平方根的定义性质：返回值非负，且其平方（近似）等于输入。

    期望值来源：数学定义 r = sqrt(x)  <=>  r >= 0 且 r * r == x。
    """
    r = sqrt(x)
    assert r >= 0
    assert math.isclose(r * r, x, rel_tol=1e-12)


# ---------------------------------------------------------------------------
# 边界：x == 0 分支（0、0.0、-0.0 三者 == 0 均为真）
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("x", [0, 0.0, -0.0])
def test_sqrt_zero_branch_returns_zero_value(x):
    """x == 0 时直接返回 0，-0.0 因 == 0 为真同样走该分支。

    期望值来源：测试计划边界用例（x = 0 / -0.0）。
    """
    assert sqrt(x) == 0


@pytest.mark.parametrize("x", [0, 0.0, -0.0, 4.0, 2.25])
def test_sqrt_return_type_is_float(x):
    """返回值必须是 float，符合签名 `-> float` 与输出域规约。

    期望值来源：函数类型注解 `-> float` 与计划中的输出域描述（float 类型）。
    当前实现对 x == 0 返回 int 0，违反该类型契约，本用例用于检出该缺陷。
    """
    assert isinstance(sqrt(x), float)


# ---------------------------------------------------------------------------
# 异常路径：负数输入
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("x", [-1.0, -0.5, -2.25, -1e308])
def test_sqrt_negative_input_raises_value_error(x):
    """实数域上平方根对负数无定义，应抛出 ValueError。

    期望值来源：数学规约（定义域 x >= 0）与 math.sqrt 的异常约定；
    计划中该用例标注为 error 类且期望值未知，此处以标准库行为作为规约。
    """
    with pytest.raises(ValueError):
        sqrt(x)


def test_sqrt_negative_input_reference_math_sqrt_raises():
    """对照组：math.sqrt 对负数抛 ValueError，佐证上述规约的合理性。

    期望值来源：标准库 math.sqrt 的定义域约定。
    """
    with pytest.raises(ValueError):
        math.sqrt(-1.0)
````

### patch vs gold fixed 逐行差异（AQ1 增补：difflib unified diff，机械对比——判定仍属人工）
````diff
--- patch（补丁应用后）
+++ gold_fixed（参考答案）
@@ -1,8 +1,6 @@
-python
 def sqrt(x: float) -> float:
     if x < 0:
-        raise ValueError("math domain error")
+        raise ValueError("不能对负数开平方")
     if x == 0:
         return 0
     return x ** 0.5
-# noise_seed=2621
````

## 候选 3：s43__synthetic__task_0028

- 分层（evidence）：sbfl ｜ stop_reason：test_passed ｜ error_category：test_regenerated_pass_unverified ｜ iterations：2
- 缺陷模式：boundary_and_exception（bug_type=runtime，difficulty=4）
- 人工判定：☐ equivalent ☐ plausible_overfit ☐ wrong_location ☐ test_only ☐ incomplete
- 判定提示：patch vs gold fixed 逐行对照；仅注释/格式/docstring 差异 → equivalent；改写测试而非源码 → test_only；改动不在缺陷位置 → wrong_location；未消除触发条件 → incomplete

### 生成补丁（patch）
````python
python
import datetime
import re

# 仅接受严格零填充的 YYYY-MM-DD（ASCII 数字），避免 strptime 的宽松匹配把
# "2024-1-1" 之类的非规范写法当成合法日期。
_STRICT_DATE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def parse_date(s: str) -> datetime.datetime:
    try:
        # 拒绝非字符串、非严格零填充格式以及含多余字符的输入
        if not isinstance(s, str) or _STRICT_DATE_PATTERN.fullmatch(s) is None:
            raise ValueError("not a strict YYYY-MM-DD date: %r" % (s,))
        return datetime.datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        # 契约：非法输入不抛 ValueError，统一回落为 datetime.min
        return datetime.datetime.min


def days_until(target: str) -> int:
    dt = parse_date(target)
    delta = dt - datetime.datetime.now()
    return delta.days


def is_expired(target: str) -> bool:
    return days_until(target) < 0
# noise_seed=9485

````

### gold fixed（参考答案，task_metadata.fixed）
````python
import datetime

def parse_date(s: str) -> datetime.datetime:
    if not s or not s.strip():
        raise ValueError("日期字符串不能为空")
    try:
        return datetime.datetime.strptime(s.strip(), "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"无法解析日期: {s!r}（期望格式 YYYY-MM-DD）") from None

def days_until(target: str) -> int:
    if target is None:
        raise ValueError("target 不能为 None")
    dt = parse_date(target)
    delta = dt - datetime.datetime.now()
    return delta.days

def is_expired(target: str) -> bool:
    if target is None or not target.strip():
        raise ValueError("target 不能为 None 或空字符串")
    return days_until(target) < 0
````

### gold 官方测试（task_metadata.test_cases）
````python
from task_0028 import parse_date, days_until, is_expired
import datetime
import pytest

def test_parse_date_normal():
    result = parse_date("2024-01-15")
    assert result.year == 2024

def test_parse_date_empty():
    with pytest.raises(ValueError):
        parse_date("")

def test_parse_date_invalid():
    with pytest.raises(ValueError):
        parse_date("not-a-date")

def test_days_until_future():
    far_future = (datetime.datetime.now() + datetime.timedelta(days=365)).strftime("%Y-%m-%d")
    assert days_until(far_future) > 300

def test_is_expired_past():
    assert is_expired("2000-01-01") is True

````

### 最终生成测试（generated_test，检出裁决者）
````python
import datetime

import pytest

from task_0028 import parse_date


class TestParseDateNormal:
    """正常解析路径测试。"""

    def test_parse_date_normal_date(self):
        """验证合法格式日期能正确解析为对应 datetime 对象。

        期望值来源：测试计划 expected_output = datetime.datetime(2024, 1, 1, 0, 0)。
        """
        result = parse_date("2024-01-01")
        assert result == datetime.datetime(2024, 1, 1, 0, 0)
        assert isinstance(result, datetime.datetime)

    def test_parse_date_returns_datetime_instance(self):
        """验证返回值类型为 datetime.datetime。

        期望值来源：docstring/类型注解 -> datetime.datetime。
        """
        result = parse_date("2024-06-15")
        assert isinstance(result, datetime.datetime)

    def test_parse_date_time_component_is_midnight(self):
        """验证解析出的时间部分为 00:00:00。

        期望值来源：逻辑分析 output_domain -> 合法日期返回时间 00:00:00。
        """
        result = parse_date("2024-06-15")
        assert result.hour == 0
        assert result.minute == 0
        assert result.second == 0
        assert result.microsecond == 0


class TestParseDateBoundary:
    """边界值测试。"""

    def test_parse_date_leap_year_feb_29(self):
        """验证闰年 2024-02-29 能合法解析。

        期望值来源：测试计划 expected_output = datetime.datetime(2024, 2, 29, 0, 0)。
        """
        result = parse_date("2024-02-29")
        assert result == datetime.datetime(2024, 2, 29, 0, 0)

    def test_parse_date_min_date(self):
        """验证最小可表示日期 0001-01-01。

        期望值来源：测试计划 expected_output = datetime.datetime.min。
        """
        result = parse_date("0001-01-01")
        assert result == datetime.datetime.min

    def test_parse_date_max_date(self):
        """验证最大可表示日期 9999-12-31。

        期望值来源：测试计划 expected_output = datetime.datetime(9999, 12, 31, 0, 0)。
        """
        result = parse_date("9999-12-31")
        assert result == datetime.datetime(9999, 12, 31, 0, 0)

    def test_parse_date_month_boundaries(self):
        """验证各月份首末日的合法解析。

        期望值来源：calendar 月份天数常识，1/31、4/30、12/31 均为合法。
        """
        assert parse_date("2024-01-31") == datetime.datetime(2024, 1, 31)
        assert parse_date("2024-04-30") == datetime.datetime(2024, 4, 30)
        assert parse_date("2024-12-31") == datetime.datetime(2024, 12, 31)


class TestParseDateErrors:
    """非法输入测试：均应返回 datetime.datetime.min，且不得抛出异常。"""

    @pytest.mark.parametrize(
        "s",
        [
            "2023-02-29",          # 非闰年 2 月 29 日
            "2024-13-01",          # 非法月份
            "2024-04-31",          # 非法日期
            "2024/01/01",          # 错误分隔符
            "",                    # 空字符串
            "2024-01-01 12:00:00", # 多余时间部分
            "0000-01-01",          # 年份为零
        ],
    )
    def test_parse_date_invalid_returns_min(self, s):
        """验证非法日期字符串返回 datetime.datetime.min 且不抛出 ValueError。

        期望值来源：测试计划各 error 用例 expected_output = datetime.datetime.min；
        非法输入清单同样来自测试计划 edge_cases / test_cases。
        """
        result = parse_date(s)
        assert result == datetime.datetime.min

    def test_parse_date_non_leap_year_feb_29_returns_min(self):
        """验证非闰年 2023-02-29 触发 ValueError 后返回 datetime.min。

        期望值来源：测试计划 expected_output = datetime.datetime.min。
        """
        assert parse_date("2023-02-29") == datetime.datetime.min

    def test_parse_date_invalid_month_returns_min(self):
        """验证月份 13 非法，返回 datetime.min。

        期望值来源：测试计划 expected_output = datetime.datetime.min。
        """
        assert parse_date("2024-13-01") == datetime.datetime.min

    def test_parse_date_invalid_day_returns_min(self):
        """验证 2024-04-31 日期非法，返回 datetime.min。

        期望值来源：测试计划 expected_output = datetime.datetime.min。
        """
        assert parse_date("2024-04-31") == datetime.datetime.min

    def test_parse_date_wrong_separator_returns_min(self):
        """验证分隔符为 '/' 时格式不匹配，返回 datetime.min。

        期望值来源：测试计划 expected_output = datetime.datetime.min。
        """
        assert parse_date("2024/01/01") == datetime.datetime.min

    def test_parse_date_empty_string_returns_min(self):
        """验证空字符串返回 datetime.min。

        期望值来源：测试计划 expected_output = datetime.datetime.min。
        """
        assert parse_date("") == datetime.datetime.min

    def test_parse_date_extra_time_part_returns_min(self):
        """验证带时间部分的字符串格式不匹配，返回 datetime.min。

        期望值来源：测试计划 expected_output = datetime.datetime.min。
        """
        assert parse_date("2024-01-01 12:00:00") == datetime.datetime.min

    def test_parse_date_year_zero_returns_min(self):
        """验证年份 0000 非法，返回 datetime.min。

        期望值来源：测试计划 expected_output = datetime.datetime.min。
        """
        assert parse_date("0000-01-01") == datetime.datetime.min


class TestParseDateExceptionContract:
    """异常传播契约测试：ValueError 必须被内部捕获，不向外传播。"""

    @pytest.mark.parametrize(
        "s",
        [
            "not-a-date",
            "2024-1-1",
            "20240101",
            "2024-01-32",
            "abc",
            " 2024-01-01",
        ],
    )
    def test_parse_date_does_not_raise_value_error(self, s):
        """验证任意非法字符串下 parse_date 均不抛出 ValueError，而是返回 datetime.min。

        期望值来源：logic_analysis postconditions -> ValueError 被捕获，不向外传播；
        非法字符串返回 datetime.datetime.min（来自 docstring/description）。
        """
        try:
            result = parse_date(s)
        except ValueError:
            pytest.fail(f"parse_date({s!r}) 不应抛出 ValueError")
        assert result == datetime.datetime.min

    def test_parse_date_never_returns_none_on_error(self):
        """验证错误输入返回的并非 None，而是 datetime.datetime.min。

        期望值来源：description -> 解析失败时返回 datetime.datetime.min。
        """
        result = parse_date("2024-02-30")
        assert result is not None
        assert result == datetime.datetime.min
````

### patch vs gold fixed 逐行差异（AQ1 增补：difflib unified diff，机械对比——判定仍属人工）
````diff
--- patch（补丁应用后）
+++ gold_fixed（参考答案）
@@ -1,29 +1,21 @@
-python
 import datetime
-import re
-
-# 仅接受严格零填充的 YYYY-MM-DD（ASCII 数字），避免 strptime 的宽松匹配把
-# "2024-1-1" 之类的非规范写法当成合法日期。
-_STRICT_DATE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
-
 
 def parse_date(s: str) -> datetime.datetime:
+    if not s or not s.strip():
+        raise ValueError("日期字符串不能为空")
     try:
-        # 拒绝非字符串、非严格零填充格式以及含多余字符的输入
-        if not isinstance(s, str) or _STRICT_DATE_PATTERN.fullmatch(s) is None:
-            raise ValueError("not a strict YYYY-MM-DD date: %r" % (s,))
-        return datetime.datetime.strptime(s, "%Y-%m-%d")
+        return datetime.datetime.strptime(s.strip(), "%Y-%m-%d")
     except ValueError:
-        # 契约：非法输入不抛 ValueError，统一回落为 datetime.min
-        return datetime.datetime.min
-
+        raise ValueError(f"无法解析日期: {s!r}（期望格式 YYYY-MM-DD）") from None
 
 def days_until(target: str) -> int:
+    if target is None:
+        raise ValueError("target 不能为 None")
     dt = parse_date(target)
     delta = dt - datetime.datetime.now()
     return delta.days
 
-
 def is_expired(target: str) -> bool:
+    if target is None or not target.strip():
+        raise ValueError("target 不能为 None 或空字符串")
     return days_until(target) < 0
-# noise_seed=9485
````

## 候选 4：s43__synthetic__task_0022

- 分层（evidence）：sbfl ｜ stop_reason：test_passed ｜ error_category：test_regenerated_pass_unverified ｜ iterations：1
- 缺陷模式：factorial_negative_input（bug_type=runtime，difficulty=1）
- 人工判定：☐ equivalent ☐ plausible_overfit ☐ wrong_location ☐ test_only ☐ incomplete
- 判定提示：patch vs gold fixed 逐行对照；仅注释/格式/docstring 差异 → equivalent；改写测试而非源码 → test_only；改动不在缺陷位置 → wrong_location；未消除触发条件 → incomplete

### 生成补丁（patch）
````python
python
def factorial(n: int) -> int:
    if n < 0:
        raise ValueError("factorial() not defined for negative values")
    if n == 0:
        return 1
    return n * factorial(n - 1)
# noise_seed=3547

````

### gold fixed（参考答案，task_metadata.fixed）
````python
def factorial(n: int) -> int:
    if n < 0:
        raise ValueError("阶乘不支持负数")
    if n == 0:
        return 1
    return n * factorial(n - 1)
````

### gold 官方测试（task_metadata.test_cases）
````python
from task_0022 import factorial

def test_factorial_zero():
    assert factorial(0) == 1

def test_factorial_positive():
    assert factorial(5) == 120

def test_factorial_negative():
    import pytest
    with pytest.raises(ValueError):
        factorial(-1)
````

### 最终生成测试（generated_test，检出裁决者）
````python
"""针对被测模块 task_0022 中 factorial 函数的 pytest 测试。

被测实现（当前版本）::

    def factorial(n: int) -> int:
        if n == 0:
            return 1
        return n * factorial(n - 1)

期望值来源（不抄袭被测实现的当前行为）：
1. 问题语义 / 数学定律：0! = 1，且 n >= 1 时 n! = n * (n-1)!。
2. 交叉参考：标准库 math.factorial 是同一数学函数的权威参考实现。
3. 定义域约定：类型注解为 ``n: int``，而阶乘只对非负整数有定义；
   对定义域外的负整数，标准库 math.factorial 明确抛出 ValueError。
   因此"负整数必须被确定性地以 ValueError 拒绝，而不是进入无基例的
   无限递归（最终 RecursionError 耗尽调用栈）"属于规约的一部分。

关于"大 n / 递归深度边界"：n 接近 Python 默认递归上限（约 1000）时，
返回值与 RecursionError 的边界依赖运行环境的递归限制，
无法从 docstring / 类型注解 / 调用方约定确定具体期望值，
故本文件只断言远低于该上限（n <= 200）的精确数学结果，
不臆造 n=1000 的期望值。
"""

import math

import pytest

from task_0022 import factorial


# ---------------------------------------------------------------------------
# 正常路径：基例、递归、后置条件
# ---------------------------------------------------------------------------

def test_factorial_zero_returns_one():
    """n = 0 命中基例分支，必须返回 1。

    期望值来源：问题语义（0! = 1）。
    """
    assert factorial(0) == 1
    assert factorial(0) == math.factorial(0)


@pytest.mark.parametrize("n", [1, 2, 3, 4, 5, 6, 7, 10])
def test_factorial_small_non_negative_matches_math_factorial(n):
    """小规模非负整数：返回值必须等于数学定义值 n!。

    期望值来源：数学定义，并用标准库 math.factorial 交叉验证。
    """
    assert factorial(n) == math.factorial(n)


@pytest.mark.parametrize("n", [1, 3, 7, 12])
def test_factorial_satisfies_recurrence_relation(n):
    """后置条件：n >= 1 时 factorial(n) == n * factorial(n - 1)。

    期望值来源：问题描述中的递归定义（无固定字面量，纯关系断言）。
    """
    assert factorial(n) == n * factorial(n - 1)


@pytest.mark.parametrize("n", [20, 50, 100, 200])
def test_factorial_moderate_n_matches_math_factorial(n):
    """中等规模输入（远低于默认递归深度上限）必须给出精确的数学结果。

    期望值来源：数学定义 / 标准库 math.factorial。
    """
    assert factorial(n) == math.factorial(n)


def test_factorial_returns_int_type():
    """返回类型注解为 int，正常调用应返回 int 且值正确。"""
    result = factorial(6)
    assert isinstance(result, int)
    assert result == 720


# ---------------------------------------------------------------------------
# 异常 / 定义域外路径：负整数
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("n", [-1, -2, -5, -100])
def test_factorial_negative_n_raises_value_error(n):
    """负整数不在定义域内，必须抛出 ValueError 做域错误拒绝。

    期望值来源：问题语义——负整数阶乘在数学上未定义；
    标准库 math.factorial 对负整数抛 ValueError（同一数学函数的权威约定）。

    当前实现没有任何定义域守卫，n < 0 时 n == 0 恒为假、缺少终止基例，
    会陷入无限递归并最终抛出 RecursionError —— 本用例即为检出该缺陷的红灯用例。
    """
    with pytest.raises(ValueError):
        factorial(n)


def test_factorial_negative_one_error_is_domain_error_not_stack_exhaustion():
    """-1 的失败方式必须是"域错误"，而不是"栈耗尽"。

    期望值来源：规约——定义域外输入应被确定性拒绝（ValueError），
    而不是靠无限递归耗尽调用栈（RecursionError）来失败。
    """
    result = None
    try:
        result = factorial(-1)
    except ValueError:
        return
    except RecursionError as exc:  # pragma: no cover - 当前缺陷实现会走到这里
        pytest.fail(
            "负整数输入触发了无基例无限递归（RecursionError），"
            f"缺少定义域校验: {exc!r}"
        )
    pytest.fail(f"负整数输入不应有返回值，实际返回 {result!r}")
````

### patch vs gold fixed 逐行差异（AQ1 增补：difflib unified diff，机械对比——判定仍属人工）
````diff
--- patch（补丁应用后）
+++ gold_fixed（参考答案）
@@ -1,8 +1,6 @@
-python
 def factorial(n: int) -> int:
     if n < 0:
-        raise ValueError("factorial() not defined for negative values")
+        raise ValueError("阶乘不支持负数")
     if n == 0:
         return 1
     return n * factorial(n - 1)
-# noise_seed=3547
````

## 候选 5：s43__synthetic__task_0005

- 分层（evidence）：sbfl ｜ stop_reason：test_passed ｜ error_category：test_regenerated_pass_unverified ｜ iterations：1
- 缺陷模式：sqrt_negative_input（bug_type=runtime，difficulty=1）
- 人工判定：☐ equivalent ☐ plausible_overfit ☐ wrong_location ☐ test_only ☐ incomplete
- 判定提示：patch vs gold fixed 逐行对照；仅注释/格式/docstring 差异 → equivalent；改写测试而非源码 → test_only；改动不在缺陷位置 → wrong_location；未消除触发条件 → incomplete

### 生成补丁（patch）
````python
python
def sqrt(x: float) -> float:
    if x < 0:
        raise ValueError("math domain error: sqrt() requires a non-negative number")
    if x == 0:
        return 0
    return x ** 0.5
# noise_seed=279

````

### gold fixed（参考答案，task_metadata.fixed）
````python
def sqrt(x: float) -> float:
    if x < 0:
        raise ValueError("不能对负数开平方")
    if x == 0:
        return 0
    return x ** 0.5
````

### gold 官方测试（task_metadata.test_cases）
````python
from task_0005 import sqrt

def test_sqrt_positive():
    import math
    assert abs(sqrt(4) - 2.0) < 1e-9

def test_sqrt_zero():
    assert sqrt(0) == 0

def test_sqrt_negative():
    import pytest
    with pytest.raises(ValueError):
        sqrt(-1)
````

### 最终生成测试（generated_test，检出裁决者）
````python
"""Pytest test suite for ``task_0005.sqrt``.

期望值来源说明：
- 常规用例的期望值来自数学定义（实数平方根），并与标准库 ``math.sqrt`` 对照；
- 负数用例的期望值来自"实数平方根定义域为 x >= 0"这一规约，
  结合被测函数 ``-> float`` 的返回类型注解（负数在实数域无解，
  不得返回 complex），因此期望抛出 ValueError（与 ``math.sqrt`` 语义一致）；
- 无法由规约唯一确定的边界（如极端浮点舍入）使用相对容差断言
  或仅断言"记录实际行为且与 docstring 一致"。
"""

import math

import pytest

from task_0005 import sqrt


# ---------------------------------------------------------------------------
# 常规分支：x != 0
# ---------------------------------------------------------------------------

def test_sqrt_positive_perfect_square_returns_exact_root():
    """docstring: x != 0 时返回 x ** 0.5；9.0 的平方根应为 3.0（数学定义）。"""
    result = sqrt(9.0)
    assert result == pytest.approx(3.0, rel=0, abs=1e-12)
    assert isinstance(result, float)


@pytest.mark.parametrize(
    "x",
    [2.0, 3.0, 10.0, 0.25, 12345.678, 1e-8, 1e8],
)
def test_sqrt_positive_values_match_math_sqrt(x):
    """docstring: x != 0 时返回 x ** 0.5；正数平方根须与 math.sqrt 一致（数学定义）。"""
    assert sqrt(x) == pytest.approx(math.sqrt(x), rel=1e-12, abs=0.0)


def test_sqrt_returns_float_for_positive_int_input():
    """docstring: 返回类型注解为 float；x = 4（int）时结果 2.0 且为 float。"""
    result = sqrt(4)
    assert result == pytest.approx(2.0, rel=0, abs=1e-12)
    assert isinstance(result, float)


# ---------------------------------------------------------------------------
# 边界分支：x == 0
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("x", [0, 0.0, -0.0])
def test_sqrt_zero_like_input_returns_zero(x):
    """docstring: x == 0 时返回 0；整数零、浮点零、负零的 == 0 均为 True。"""
    result = sqrt(x)
    assert result == 0
    assert not isinstance(result, complex)


def test_sqrt_int_zero_returns_plain_zero():
    """docstring: x == 0 时返回 0；显式校验等于数值 0 且非布尔/复数。"""
    result = sqrt(0)
    assert result == 0
    assert result is not False
    assert not isinstance(result, complex)


# ---------------------------------------------------------------------------
# 误差/异常路径：定义域外的负数
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("x", [-1.0, -4.0, -0.25, -1e-300, -1e300])
def test_sqrt_negative_input_raises_value_error(x):
    """实数平方根定义域为 x >= 0。

    被测函数注解为 ``-> float``，负数在实数域无平方根，因此按规约应像
    ``math.sqrt`` 一样抛出 ValueError，而不是返回 complex（复数违反返回注解）。
    期望值来源：实数平方根定义域 + 返回类型注解（非实现当前行为）。
    """
    with pytest.raises(ValueError):
        sqrt(x)


def test_sqrt_negative_input_result_is_not_complex():
    """规约要求返回 float：负数入参不得静默返回 complex（先红后绿检出错路径）。"""
    try:
        result = sqrt(-9.0)
    except ValueError:
        return  # 与规约一致：抛出 ValueError 亦可接受
    assert not isinstance(result, complex), (
        "sqrt 的返回类型注解为 float，负数入参返回了复数，违反规约"
    )


# ---------------------------------------------------------------------------
# 极端边界
# ---------------------------------------------------------------------------

def test_sqrt_large_positive_value_no_overflow_error():
    """docstring: x != 0 时返回 x ** 0.5；1e308 的平方根约为 1e154（期望值来源：数学定义）。"""
    result = sqrt(1e308)
    assert math.isfinite(result)
    assert result == pytest.approx(1e154, rel=1e-12)


def test_sqrt_very_small_positive_value():
    """docstring: x != 0 时返回 x ** 0.5；1e-300 的平方根（记录实际值并与数学值对照）。"""
    result = sqrt(1e-300)
    assert result == pytest.approx(math.sqrt(1e-300), rel=1e-12, abs=0.0)


def test_sqrt_positive_infinity_is_infinite():
    """docstring: x != 0 分支；+inf ** 0.5 == +inf（期望值来源：数学定义）。"""
    result = sqrt(float("inf"))
    assert math.isinf(result)
    assert result > 0


def test_sqrt_nan_propagates():
    """docstring: x != 0 分支；nan ** 0.5 为 nan（期望值来源：浮点语义，nan != 0）。"""
    result = sqrt(float("nan"))
    assert math.isnan(result)


def test_sqrt_result_squared_recovers_input():
    """数学定律：对 x > 0，(sqrt(x)) ** 2 == x（自洽性校验，不依赖具体实现细节）。"""
    for x in (0.5, 1.0, 7.0, 1024.0):
        assert sqrt(x) ** 2 == pytest.approx(x, rel=1e-12)


# ---------------------------------------------------------------------------
# 违反类型注解的输入
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("x", ["4", None, [4.0], {4.0: 1}])
def test_sqrt_non_float_input_raises_type_error(x):
    """类型注解要求 float；非数值输入在 x != 0 分支执行 ** 0.5 时应抛 TypeError。"""
    with pytest.raises(TypeError):
        sqrt(x)


def test_sqrt_string_input_does_not_silently_succeed():
    """类型规约：字符串入参不允许被静默接受（防止内部做了隐式转换掩盖类型错误）。"""
    with pytest.raises(TypeError):
        sqrt("9")
````

### patch vs gold fixed 逐行差异（AQ1 增补：difflib unified diff，机械对比——判定仍属人工）
````diff
--- patch（补丁应用后）
+++ gold_fixed（参考答案）
@@ -1,8 +1,6 @@
-python
 def sqrt(x: float) -> float:
     if x < 0:
-        raise ValueError("math domain error: sqrt() requires a non-negative number")
+        raise ValueError("不能对负数开平方")
     if x == 0:
         return 0
     return x ** 0.5
-# noise_seed=279
````

## 候选 6：s42__synthetic__task_0055

- 分层（evidence）：sbfl ｜ stop_reason：test_passed ｜ error_category：test_regenerated_pass_unverified ｜ iterations：1
- 缺陷模式：clamp_range_error（bug_type=assertion，difficulty=1）
- 人工判定：☐ equivalent ☐ plausible_overfit ☐ wrong_location ☐ test_only ☐ incomplete
- 判定提示：patch vs gold fixed 逐行对照；仅注释/格式/docstring 差异 → equivalent；改写测试而非源码 → test_only；改动不在缺陷位置 → wrong_location；未消除触发条件 → incomplete

### 生成补丁（patch）
````python
python
def clamp(value: float, min_val: float, max_val: float) -> float:
    # Inverted bounds (min_val > max_val): result is independent of value,
    # conventionally return max_val.
    if min_val > max_val:
        return max_val
    if value < min_val:
        return min_val
    if value > max_val:
        return max_val
    return value
# noise_seed=1104

````

### gold fixed（参考答案，task_metadata.fixed）
````python
def clamp(value: float, min_val: float, max_val: float) -> float:
    if min_val > max_val:
        raise ValueError("min_val 不能大于 max_val")
    if value < min_val:
        return min_val
    if value > max_val:
        return max_val
    return value
````

### gold 官方测试（task_metadata.test_cases）
````python
from task_0055 import clamp

def test_clamp_normal():
    assert clamp(5, 0, 10) == 5

def test_clamp_below():
    assert clamp(-1, 0, 10) == 0

def test_clamp_above():
    assert clamp(15, 0, 10) == 10

def test_clamp_invalid_range():
    import pytest
    with pytest.raises(ValueError):
        clamp(5, 10, 0)
````

### 最终生成测试（generated_test，检出裁决者）
````python
"""task_0055.clamp 的 pytest 测试。

规约（问题语义，独立于被测实现的当前行为）：

    clamp(x, lo, hi) := min(max(x, lo), hi)        # GLSL `clamp` / numpy.clip 的规范定义

由该定义可直接推出：
  1) x < lo           -> lo
  2) x > hi           -> hi
  3) lo <= x <= hi    -> x（原样返回，含两端点）
  4) lo <= hi 时结果必落在闭区间 [lo, hi] 内，且满足幂等与单调
  5) lo > hi（区间倒置的无效输入）时仍有确定结果：
     max(x, lo) >= lo > hi，故 min(max(x, lo), hi) 恒等于 hi = max_val，与 x 无关

第 5 条是"复核实现分支顺序"的关键：若实现先判下界并在 x < lo 时直接返回 lo，
在区间倒置时会返回 min_val，违反规范定义。因此下面的
test_clamp_with_inverted_bounds_* 在未修复实现上必然失败。
"""

import random

import pytest

from task_0055 import clamp


# ---------------------------------------------------------------------------
# 有效区间（lo <= hi）：普通、边界与极端输入
# ---------------------------------------------------------------------------

VALID_RANGE_CASES = [
    # (value, min_val, max_val, expected)
    (5.0, 0.0, 10.0, 5.0),        # 区间内
    (0.0, 0.0, 10.0, 0.0),        # 等于下界
    (10.0, 0.0, 10.0, 10.0),      # 等于上界
    (3.0, 3.0, 3.0, 3.0),         # 退化区间，值等于唯一点
    (0.0, 0.0, 0.0, 0.0),         # 全零
    (-5.0, 0.0, 10.0, 0.0),       # 低于下界
    (15.0, 0.0, 10.0, 10.0),      # 高于上界
    (-3.0, -10.0, -1.0, -3.0),    # 负数区间内
    (-10.0, -10.0, -1.0, -10.0),  # 负数下界端点
    (-1.0, -10.0, -1.0, -1.0),    # 负数上界端点
    (-20.0, -10.0, -1.0, -10.0),  # 低于负下界
    (1e308, 0.0, 10.0, 10.0),     # 极大有限浮点数
    (-1e308, 0.0, 10.0, 0.0),     # 极小有限浮点数
    (2.5, 2.5, 7.5, 2.5),         # 非整数端点，等于下界
    (5.0, 2.5, 7.5, 5.0),         # 非整数端点，区间内
    (7.5, 2.5, 7.5, 7.5),         # 非整数端点，等于上界
]


@pytest.mark.parametrize("value, min_val, max_val, expected", VALID_RANGE_CASES)
def test_clamp_with_valid_range(value, min_val, max_val, expected):
    """lo <= hi 时按夹取规约返回：越下界取下界、越上界取上界、否则原值。

    期望值来源：clamp(x, lo, hi) = min(max(x, lo), hi)，
    它等价于三分支规约（x<lo -> lo；x>hi -> hi；否则 -> x）。
    """
    assert clamp(value, min_val, max_val) == expected


def test_clamp_result_stays_inside_valid_range():
    """属性检验：lo <= hi 时结果必须落在闭区间 [lo, hi] 内，并等于规范定义值。

    期望值来源：夹取的数学定义（结果被投影到区间上）。
    """
    rng = random.Random(1104)
    for _ in range(300):
        lo = rng.uniform(-1000.0, 1000.0)
        hi = lo + rng.uniform(0.0, 1000.0)   # 保证 lo <= hi
        x = rng.uniform(-3000.0, 3000.0)

        result = clamp(x, lo, hi)

        assert lo <= result <= hi
        assert result == min(max(x, lo), hi)   # 规范定义


def test_clamp_is_idempotent_and_monotonic_for_valid_range():
    """属性检验：有效区间下 clamp 幂等，且对 value 单调不减。

    期望值来源：夹取是到区间上的投影 —— 投影幂等；且 x1 <= x2 => clamp(x1) <= clamp(x2)。
    """
    rng = random.Random(20240517)
    for _ in range(200):
        lo = rng.uniform(-100.0, 100.0)
        hi = lo + rng.uniform(0.0, 100.0)
        xs = sorted(rng.uniform(-200.0, 200.0) for _ in range(5))

        ys = [clamp(x, lo, hi) for x in xs]

        assert ys == sorted(ys), (xs, ys)          # 单调不减
        for y in ys:
            assert clamp(y, lo, hi) == y           # 幂等


# ---------------------------------------------------------------------------
# 区间倒置（min_val > max_val）：无效输入的确定化规约
# ---------------------------------------------------------------------------

INVERTED_RANGE_CASES = [
    # (value, min_val, max_val, expected)
    (5.0, 10.0, 0.0, 0.0),     # 值同时满足 x<lo 与 x>hi，必须取上界
    (0.0, 10.0, 0.0, 0.0),     # 值等于上界
    (15.0, 10.0, 0.0, 0.0),    # 值大于上界
    (100.0, 10.0, 0.0, 0.0),   # 远大于上界
    (2.0, 1.0, -1.0, -1.0),    # 另一组倒置边界
    (-1.0, 1.0, -1.0, -1.0),   # 值等于上界
]


@pytest.mark.parametrize("value, min_val, max_val, expected", INVERTED_RANGE_CASES)
def test_clamp_with_inverted_bounds_returns_max_val(value, min_val, max_val, expected):
    """min_val > max_val 时，规范定义仍给出确定结果：恒为 max_val。

    期望值来源：clamp(x, lo, hi) := min(max(x, lo), hi)（GLSL clamp 与 numpy.clip 的定义）。
    lo > hi 时 max(x, lo) >= lo > hi，因此 min(max(x, lo), hi) == hi == max_val，与 x 无关。
    注意：若实现把下界分支放在最前（x < lo 直接 return lo），当 x 同时落在
    x < lo 与 x > hi 时就会返回 min_val，违反上述规约——这些用例即为该缺陷的检出点。
    """
    assert clamp(value, min_val, max_val) == max_val


def test_clamp_inverted_bounds_result_is_independent_of_value():
    """倒置边界下，返回值必须由边界决定而与 value 无关（差值应为 0）。

    期望值来源：同 min(max(x, lo), hi) 定义 —— lo > hi 时结果恒等于 hi。
    """
    lo, hi = 10.0, 0.0
    samples = [5.0, 0.0, 15.0, 100.0, 1e308]
    results = [clamp(x, lo, hi) for x in samples]

    assert all(r == results[0] for r in results), results
    assert results[0] == hi


# ---------------------------------------------------------------------------
# 类型前置条件被破坏时的异常路径
# ---------------------------------------------------------------------------

def test_clamp_raises_type_error_for_non_numeric_value():
    """非数值 value 破坏类型前置条件，与 float 边界比较时抛出 TypeError。

    期望值来源：Python 比较语义 —— str 与 float 之间 '<' 不受支持，抛 TypeError；
    函数未捕获异常，应向上传播。
    """
    with pytest.raises(TypeError):
        clamp("abc", 0.0, 10.0)


def test_clamp_raises_type_error_for_none_value():
    """value 为 None 时同样破坏类型前置条件，应抛出 TypeError。

    期望值来源：Python 比较语义（NoneType 与 float 不可比较）。
    """
    with pytest.raises(TypeError):
        clamp(None, 0.0, 10.0)
````

### patch vs gold fixed 逐行差异（AQ1 增补：difflib unified diff，机械对比——判定仍属人工）
````diff
--- patch（补丁应用后）
+++ gold_fixed（参考答案）
@@ -1,12 +1,8 @@
-python
 def clamp(value: float, min_val: float, max_val: float) -> float:
-    # Inverted bounds (min_val > max_val): result is independent of value,
-    # conventionally return max_val.
     if min_val > max_val:
-        return max_val
+        raise ValueError("min_val 不能大于 max_val")
     if value < min_val:
         return min_val
     if value > max_val:
         return max_val
     return value
-# noise_seed=1104
````

## 候选 7：s42__synthetic__task_0043

- 分层（evidence）：sbfl ｜ stop_reason：test_passed ｜ error_category：test_regenerated_pass_unverified ｜ iterations：1
- 缺陷模式：clamp_boundary_inverted（bug_type=assertion，difficulty=1）
- 人工判定：☐ equivalent ☐ plausible_overfit ☐ wrong_location ☐ test_only ☐ incomplete
- 判定提示：patch vs gold fixed 逐行对照；仅注释/格式/docstring 差异 → equivalent；改写测试而非源码 → test_only；改动不在缺陷位置 → wrong_location；未消除触发条件 → incomplete

### 生成补丁（patch）
````python
python
def clamp(value: int, low: int, high: int) -> int:
    # 类型校验：clamp 只接受 int 参数（非 int 边界/取值一律抛 TypeError）
    if not isinstance(value, int) or not isinstance(low, int) or not isinstance(high, int):
        raise TypeError(
            "clamp() arguments must be int, got "
            f"value={type(value).__name__}, "
            f"low={type(low).__name__}, "
            f"high={type(high).__name__}"
        )
    # 标准 clamp 语义：等价于 max(low, min(value, high))
    if value < low:
        return low
    if value > high:
        return high
    return value
# noise_seed=9938

````

### gold fixed（参考答案，task_metadata.fixed）
````python
def clamp(value: int, low: int, high: int) -> int:
    if value > high:
        return high
    if value < low:
        return low
    return value
````

### gold 官方测试（task_metadata.test_cases）
````python
from task_0043 import clamp

def test_clamp_within():
    assert clamp(5, 0, 10) == 5

def test_clamp_above_high():
    assert clamp(99, 0, 10) == 10

def test_clamp_below_low():
    assert clamp(-7, 0, 10) == 0

def test_clamp_boundary_equals():
    assert clamp(0, 0, 10) == 0
    assert clamp(10, 0, 10) == 10
````

### 最终生成测试（generated_test，检出裁决者）
````python
"""Tests for ``clamp`` (module: task_0043).

Expected values are derived from the standard mathematical definition of a
clamp operator::

    clamp(value, low, high) == min(max(value, low), high)

i.e. the result is never below ``low``, never above ``high``, and an
already-in-range ``value`` is returned unchanged.  These expectations come
from the public semantics of the name/signature, not from the current
implementation body.
"""

import pytest

from task_0043 import clamp


# ---------------------------------------------------------------------------
# Core semantics: in-range values must be returned unchanged
# ---------------------------------------------------------------------------

def test_clamp_returns_value_when_inside_range():
    """An in-range value must be returned unchanged (identity on the interval).

    This is the defining property of clamp; the current implementation
    returns ``high`` here, so this test is expected to fail until fixed.
    """
    assert clamp(5, 0, 10) == 5


def test_clamp_returns_value_when_equal_to_low():
    """value == low is inside the range, so clamp must return ``low``."""
    assert clamp(0, 0, 10) == 0


def test_clamp_returns_value_when_equal_to_high():
    """value == high is inside the range, so clamp must return ``high``."""
    assert clamp(10, 0, 10) == 10


# ---------------------------------------------------------------------------
# Core semantics: saturation behaviour
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "value, low, high, expected",
    [
        # below the lower bound -> saturate at low
        (-5, 0, 10, 0),
        (-1, 0, 10, 0),
        (-100, -10, 10, -10),
        # above the upper bound -> saturate at high
        (15, 0, 10, 10),
        (11, 0, 10, 10),
        (100, -10, 10, 10),
        # inside the interval -> unchanged
        (5, 0, 10, 5),
        (0, 0, 10, 0),
        (10, 0, 10, 10),
        (-5, -10, 10, -5),
        # negative-only interval
        (-3, -10, -1, -3),
        (-11, -10, -1, -10),
        (-2, -10, -1, -2),
        # degenerate interval (low == high)
        (0, 0, 0, 0),
        (5, 0, 0, 0),
        (-5, 0, 0, 0),
        (7, 7, 7, 7),
        # large integers (Python ints have no fixed width)
        (10 ** 30, 0, 10 ** 30 + 1, 10 ** 30),
        (10 ** 30 + 2, 0, 10 ** 30, 10 ** 30),
        (-(10 ** 30), -(10 ** 30) + 1, 0, -(10 ** 30) + 1),
    ],
)
def test_clamp_saturation_and_identity(value, low, high, expected):
    """clamp(value, low, high) == min(max(value, low), high)."""
    assert clamp(value, low, high) == expected


# ---------------------------------------------------------------------------
# Property-based style checks (loops, no external deps)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("low, high", [(0, 10), (-10, 0), (-5, 5), (3, 3), (-7, -7)])
def test_clamp_result_always_within_bounds(low, high):
    """For every input the result must lie in the closed interval [low, high]."""
    for value in range(low - 3, high + 4):
        result = clamp(value, low, high)
        assert low <= result <= high, (
            f"clamp({value}, {low}, {high}) = {result} is outside [{low}, {high}]"
        )


def test_clamp_is_monotonic_non_decreasing():
    """clamp is a non-decreasing function of ``value``."""
    low, high = 0, 10
    previous = clamp(-5, low, high)
    for value in range(-4, 16):
        current = clamp(value, low, high)
        assert current >= previous, (
            f"clamp is not monotonic: clamp({value - 1}) = {previous} > "
            f"clamp({value}) = {current}"
        )
        previous = current


def test_clamp_is_idempotent():
    """Applying clamp twice with the same bounds changes nothing."""
    low, high = 0, 10
    for value in (-100, -3, 0, 5, 10, 13, 100):
        once = clamp(value, low, high)
        twice = clamp(once, low, high)
        assert twice == once, (
            f"clamp is not idempotent for value={value}: "
            f"clamp({once}) = {twice}"
        )


def test_clamp_matches_reference_formula_on_grid():
    """Exhaustive cross-check against min(max(value, low), high) on a small grid."""
    for low in range(-3, 4):
        for high in range(low, 4):
            for value in range(-5, 6):
                expected = min(max(value, low), high)
                assert clamp(value, low, high) == expected, (
                    f"clamp({value}, {low}, {high}) != min(max(value, low), high)"
                )


# ---------------------------------------------------------------------------
# Error / contract-violation paths
# ---------------------------------------------------------------------------

def test_clamp_raises_type_error_for_non_int_value():
    """Non-int ``value`` violates the type contract; comparison must raise TypeError."""
    with pytest.raises(TypeError):
        clamp("5", 0, 10)


def test_clamp_raises_type_error_for_non_int_bound():
    """Non-int bounds violate the type contract; comparison must raise TypeError."""
    with pytest.raises(TypeError):
        clamp(5, None, 10)


def test_clamp_raises_type_error_for_mixed_incomparable_types():
    """Incomparable mixed types must surface as TypeError, not silently pass."""
    with pytest.raises(TypeError):
        clamp(5, 0, "10")
````

### patch vs gold fixed 逐行差异（AQ1 增补：difflib unified diff，机械对比——判定仍属人工）
````diff
--- patch（补丁应用后）
+++ gold_fixed（参考答案）
@@ -1,17 +1,6 @@
-python
 def clamp(value: int, low: int, high: int) -> int:
-    # 类型校验：clamp 只接受 int 参数（非 int 边界/取值一律抛 TypeError）
-    if not isinstance(value, int) or not isinstance(low, int) or not isinstance(high, int):
-        raise TypeError(
-            "clamp() arguments must be int, got "
-            f"value={type(value).__name__}, "
-            f"low={type(low).__name__}, "
-            f"high={type(high).__name__}"
-        )
-    # 标准 clamp 语义：等价于 max(low, min(value, high))
+    if value > high:
+        return high
     if value < low:
         return low
-    if value > high:
-        return high
     return value
-# noise_seed=9938
````

## 候选 8：s42__synthetic__task_0036

- 分层（evidence）：sbfl ｜ stop_reason：test_passed ｜ error_category：test_regenerated_pass_unverified ｜ iterations：3
- 缺陷模式：factorial_negative_input（bug_type=runtime，difficulty=1）
- 人工判定：☐ equivalent ☐ plausible_overfit ☐ wrong_location ☐ test_only ☐ incomplete
- 判定提示：patch vs gold fixed 逐行对照；仅注释/格式/docstring 差异 → equivalent；改写测试而非源码 → test_only；改动不在缺陷位置 → wrong_location；未消除触发条件 → incomplete

### 生成补丁（patch）
````python
python
def factorial(n: int) -> int:
    # 迭代实现：避免大 n 时递归深度超过解释器递归上限
    if n < 0:
        # 与原递归实现保持一致的行为：负数输入会无限递归并抛出 RecursionError
        raise RecursionError("maximum recursion depth exceeded (negative input)")
    result = 1
    for i in range(2, n + 1):
        result *= i
    return result
# noise_seed=9295

````

### gold fixed（参考答案，task_metadata.fixed）
````python
def factorial(n: int) -> int:
    if n < 0:
        raise ValueError("阶乘不支持负数")
    if n == 0:
        return 1
    return n * factorial(n - 1)
````

### gold 官方测试（task_metadata.test_cases）
````python
from task_0036 import factorial

def test_factorial_zero():
    assert factorial(0) == 1

def test_factorial_positive():
    assert factorial(5) == 120

def test_factorial_negative():
    import pytest
    with pytest.raises(ValueError):
        factorial(-1)
````

### 最终生成测试（generated_test，检出裁决者）
````python
"""pytest test suite for task_0036.factorial.

约定（来自被测函数的 docstring 与类型注解）：
- 参数 n 为 int，语义上要求 n >= 0。
- n == 0 时返回 1；n > 0 时返回 n!（n * (n-1)!）。
- 数学定义（阶乘规约）是期望值的唯一来源，不参考实现内部写法。
"""

import math
import sys

import pytest

from task_0036 import factorial


# ---------------------------------------------------------------------------
# 基础分支 / 常规递归
# ---------------------------------------------------------------------------
def test_factorial_n0_returns_one():
    """基础分支：0! = 1（期望值来源：数学定义 0! = 1）。"""
    assert factorial(0) == 1


def test_factorial_n1_returns_one():
    """最小正数输入：1! = 1（期望值来源：数学定义 1! = 1）。"""
    assert factorial(1) == 1


@pytest.mark.parametrize(
    "n, expected",
    [
        (2, 2),
        (3, 6),
        (4, 24),
        (5, 120),
        (6, 720),
        (7, 5040),
        (10, 3628800),
        (12, 479001600),
        (20, 2432902008176640000),
    ],
)
def test_factorial_known_values(n, expected):
    """常规取值：n! 的标准数值（期望值来源：阶乘数学定义）。"""
    assert factorial(n) == expected


@pytest.mark.parametrize("n", list(range(0, 51)))
def test_factorial_matches_math_factorial_small_range(n):
    """一致性：对 0..50 的每个 n，结果必须等于 math.factorial(n)。

    期望值来源：阶乘的数学定义（math.factorial 为标准库参考实现）。
    """
    assert factorial(n) == math.factorial(n)


@pytest.mark.parametrize("n", [1, 2, 5, 9, 13, 30])
def test_factorial_satisfies_recursive_identity(n):
    """递归恒等式：n! == n * (n-1)!（期望值来源：阶乘递推定义）。"""
    assert factorial(n) == n * factorial(n - 1)


@pytest.mark.parametrize("n", [0, 1, 5, 10])
def test_factorial_result_is_exact_int(n):
    """返回值必须是精确整数而非浮点近似（期望值来源：类型注解 -> int）。"""
    result = factorial(n)
    assert isinstance(result, int)
    assert not isinstance(result, bool) or n <= 1


# ---------------------------------------------------------------------------
# 异常 / 域外输入
# ---------------------------------------------------------------------------
def test_factorial_negative_input_never_terminates_normally():
    """负整数不在定义域内，实现无负向保护，必然耗尽递归深度。

    期望值来源：代码路径分析（n < 0 时永远无法命中 n == 0 分支），
    与测试计划中 n = -1 的预期一致。
    """
    with pytest.raises(RecursionError):
        factorial(-1)


def test_factorial_negative_five_never_terminates_normally():
    """更小的负数同样无法收敛，应以 RecursionError 终止而非返回错误数值。"""
    with pytest.raises(RecursionError):
        factorial(-5)


# ---------------------------------------------------------------------------
# 深层递归 / 资源边界（契约性断言）
# ---------------------------------------------------------------------------
def test_factorial_deep_recursion_within_interpreter_limit():
    """递归深度边界内的深调用必须给出正确阶乘值。

    期望值来源：阶乘数学定义；n = 998 距 CPython 默认递归上限（1000）
    尚有余量，因此没有理由失败。
    """
    assert factorial(998) == math.factorial(998)


def test_factorial_n1000_matches_math_factorial():
    """契约性断言：非负整数 n 的阶乘必须可计算，n = 1000 亦不例外。

    期望值来源：函数签名承诺计算非负整数 n 的阶乘，且 Python int 无固定
    位宽、不存在溢出；1000! 是数学上完全确定的整数
    （math.factorial(1000)）。递归深度只是实现细节，不能成为契约边界。
    当前递归实现在此深度会耗尽解释器栈并抛出 RecursionError，
    本用例即用于检出该实现层面的缺陷；不允许放宽断言以换取通过。
    """
    assert factorial(1000) == math.factorial(1000)


@pytest.mark.parametrize("n", [1001, 1500])
def test_factorial_very_large_n_matches_math_factorial(n):
    """更大输入的阶乘同样必须精确可算。

    期望值来源：阶乘数学定义 + Python int 无界性。
    注意：不得通过抬高 sys.setrecursionlimit 来规避实现缺陷，
    因此本用例显式确认当前解释器上限未被测试代码篡改。
    """
    assert sys.getrecursionlimit() <= 1000 or True  # 仅记录，不做条件化断言
    assert factorial(n) == math.factorial(n)
````

### patch vs gold fixed 逐行差异（AQ1 增补：difflib unified diff，机械对比——判定仍属人工）
````diff
--- patch（补丁应用后）
+++ gold_fixed（参考答案）
@@ -1,11 +1,6 @@
-python
 def factorial(n: int) -> int:
-    # 迭代实现：避免大 n 时递归深度超过解释器递归上限
     if n < 0:
-        # 与原递归实现保持一致的行为：负数输入会无限递归并抛出 RecursionError
-        raise RecursionError("maximum recursion depth exceeded (negative input)")
-    result = 1
-    for i in range(2, n + 1):
-        result *= i
-    return result
-# noise_seed=9295
+        raise ValueError("阶乘不支持负数")
+    if n == 0:
+        return 1
+    return n * factorial(n - 1)
````

复核完成后：把每行判定回填 e7_repair_sample_candidates.md 的"人工判定"列，按预注册判定规则更新 docs/preregistration.md 执行记录表 E7 行，并追记全局决策日志。
