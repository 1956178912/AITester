"""测试 complex_logic 模块"""
import pytest


class TestValidateEmail:
    """测试邮箱验证"""

    def test_valid_email(self):
        """有效邮箱"""
        from examples.complex_logic import validate_email
        assert validate_email("test@example.com") is True
        assert validate_email("user.name+tag@domain.co.uk") is True

    def test_invalid_email(self):
        """无效邮箱"""
        from examples.complex_logic import validate_email
        assert validate_email("invalid") is False
        assert validate_email("@missing.com") is False
        assert validate_email("no@domain") is False

    def test_empty_email(self):
        """空邮箱"""
        from examples.complex_logic import validate_email
        assert validate_email("") is False


class TestFindMaxSubarraySum:
    """测试最大子数组和"""

    def test_basic_case(self):
        """基本案例 - 实际结果是 9 (3+4-1+2+1)"""
        from examples.complex_logic import find_max_subarray_sum
        assert find_max_subarray_sum([1, -2, 3, 4, -1, 2, 1, -5, 4]) == 9

    def test_all_negative(self):
        """全负数"""
        from examples.complex_logic import find_max_subarray_sum
        assert find_max_subarray_sum([-1, -2, -3]) == -1

    def test_single_element(self):
        """单元素"""
        from examples.complex_logic import find_max_subarray_sum
        assert find_max_subarray_sum([5]) == 5

    def test_empty_list_raises(self):
        """空列表抛出异常"""
        from examples.complex_logic import find_max_subarray_sum
        with pytest.raises(ValueError):
            find_max_subarray_sum([])

    def test_all_positive(self):
        """全正数"""
        from examples.complex_logic import find_max_subarray_sum
        assert find_max_subarray_sum([1, 2, 3, 4, 5]) == 15


class TestMergeIntervals:
    """测试区间合并"""

    def test_basic_merge(self):
        """基本合并"""
        from examples.complex_logic import merge_intervals
        result = merge_intervals([(1, 3), (2, 6), (8, 10)])
        assert result == [(1, 6), (8, 10)]

    def test_no_overlap(self):
        """无重叠"""
        from examples.complex_logic import merge_intervals
        result = merge_intervals([(1, 2), (3, 4), (5, 6)])
        assert result == [(1, 2), (3, 4), (5, 6)]

    def test_all_overlapping(self):
        """全部重叠 - 实际结果是 (1, 6)"""
        from examples.complex_logic import merge_intervals
        result = merge_intervals([(1, 4), (2, 5), (3, 6)])
        assert result == [(1, 6)]

    def test_empty_input(self):
        """空输入"""
        from examples.complex_logic import merge_intervals
        assert merge_intervals([]) == []
