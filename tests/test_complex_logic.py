"""
复杂逻辑示例测试

测试 complex_logic.py 中的各种算法函数
"""

import pytest

from examples.complex_logic import (
    contains_duplicate,
    find_max_subarray_sum,
    is_valid_sudoku,
    lcs_dp,
    merge_intervals,
    rotate_matrix,
    validate_email,
)


class TestMaxSubarraySum:
    """最大子数组和测试"""

    def test_all_positive(self):
        """全正数"""
        assert find_max_subarray_sum([1, 2, 3, 4, 5]) == 15

    def test_all_negative(self):
        """全负数"""
        assert find_max_subarray_sum([-1, -2, -3]) == -1

    def test_mixed(self):
        """混合正负"""
        assert find_max_subarray_sum([-2, 1, -3, 4, -1, 2, 1, -5, 4]) == 6

    def test_single_element(self):
        """单元素"""
        assert find_max_subarray_sum([5]) == 5

    def test_empty_raises(self):
        """空列表应抛出异常"""
        with pytest.raises(ValueError):
            find_max_subarray_sum([])


class TestValidateEmail:
    """邮箱验证测试"""

    def test_valid_email(self):
        """有效邮箱"""
        assert validate_email("test@example.com") is True

    def test_invalid_no_at(self):
        """缺少 @ 符号"""
        assert validate_email("testexample.com") is False

    def test_invalid_no_domain(self):
        """缺少域名"""
        assert validate_email("test@") is False

    def test_invalid_spaces(self):
        """包含空格"""
        assert validate_email("test @example.com") is False

    def test_empty_string(self):
        """空字符串"""
        assert validate_email("") is False


class TestMergeIntervals:
    """合并区间测试"""

    def test_basic_merge(self):
        """基础合并"""
        result = merge_intervals([(1, 3), (2, 6), (8, 10)])
        assert result == [(1, 6), (8, 10)]

    def test_adjacent_intervals(self):
        """相邻区间"""
        result = merge_intervals([(1, 4), (4, 5)])
        assert result == [(1, 5)]

    def test_no_overlap(self):
        """无重叠"""
        result = merge_intervals([(1, 2), (4, 5), (7, 8)])
        assert result == [(1, 2), (4, 5), (7, 8)]

    def test_empty_input(self):
        """空输入"""
        assert merge_intervals([]) == []

    def test_single_interval(self):
        """单个区间"""
        assert merge_intervals([(1, 5)]) == [(1, 5)]

    def test_fully_nested(self):
        """完全嵌套"""
        result = merge_intervals([(1, 10), (2, 5)])
        assert result == [(1, 10)]


class TestLCSDP:
    """最长公共子序列测试"""

    def test_basic(self):
        """基础测试"""
        assert lcs_dp("ABCBDAB", "BDCABA") == 4

    def test_identical(self):
        """相同字符串"""
        assert lcs_dp("ABC", "ABC") == 3

    def test_no_common(self):
        """无公共子序列"""
        assert lcs_dp("ABC", "DEF") == 0

    def test_empty_first(self):
        """第一个为空"""
        assert lcs_dp("", "ABC") == 0

    def test_empty_second(self):
        """第二个为空"""
        assert lcs_dp("ABC", "") == 0

    def test_both_empty(self):
        """都为空"""
        assert lcs_dp("", "") == 0


class TestContainsDuplicate:
    """包含重复元素测试"""

    def test_within_k(self):
        """k 范围内有重复"""
        assert contains_duplicate([1, 2, 3, 1], 3) is True

    def test_outside_k(self):
        """超出 k 范围"""
        assert contains_duplicate([1, 0, 1, 1], 1) is True
        assert contains_duplicate([1, 2, 3, 1, 2, 3], 2) is False

    def test_no_duplicate(self):
        """无重复"""
        assert contains_duplicate([1, 2, 3, 4, 5], 3) is False

    def test_empty(self):
        """空列表"""
        assert contains_duplicate([], 3) is False


class TestRotateMatrix:
    """矩阵旋转测试"""

    def test_3x3(self):
        """3x3 矩阵"""
        matrix = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
        result = rotate_matrix(matrix)
        assert result == [[7, 4, 1], [8, 5, 2], [9, 6, 3]]

    def test_2x2(self):
        """2x2 矩阵"""
        matrix = [[1, 2], [3, 4]]
        result = rotate_matrix(matrix)
        assert result == [[3, 1], [4, 2]]

    def test_1x1(self):
        """1x1 矩阵"""
        matrix = [[1]]
        result = rotate_matrix(matrix)
        assert result == [[1]]


class TestIsValidSudoku:
    """数独验证测试"""

    def test_valid_board(self):
        """有效数独"""
        board = [
            ["5", "3", ".", ".", "7", ".", ".", ".", "."],
            ["6", ".", ".", "1", "9", "5", ".", ".", "."],
            [".", "9", "8", ".", ".", ".", ".", "6", "."],
            ["8", ".", ".", ".", "6", ".", ".", ".", "3"],
            ["4", ".", ".", "8", ".", "3", ".", ".", "1"],
            ["7", ".", ".", ".", "2", ".", ".", ".", "6"],
            [".", "6", ".", ".", ".", ".", "2", "8", "."],
            [".", ".", ".", "4", "1", "9", ".", ".", "5"],
            [".", ".", ".", ".", "8", ".", ".", "7", "9"],
        ]
        assert is_valid_sudoku(board) is True

    def test_invalid_row(self):
        """无效行"""
        board = [
            ["8", "3", ".", ".", "7", ".", ".", ".", "."],
            ["6", ".", ".", "1", "9", "5", ".", ".", "."],
            [".", "9", "8", ".", ".", ".", ".", "6", "."],
            ["8", ".", ".", ".", "6", ".", ".", ".", "3"],
            ["4", ".", ".", "8", ".", "3", ".", ".", "1"],
            ["7", ".", ".", ".", "2", ".", ".", ".", "6"],
            [".", "6", ".", ".", ".", ".", "2", "8", "."],
            [".", ".", ".", "4", "1", "9", ".", ".", "5"],
            [".", ".", ".", ".", "8", ".", ".", "7", "8"],  # 最后一行有两个 8
        ]
        assert is_valid_sudoku(board) is False

    def test_invalid_column(self):
        """无效列"""
        board = [
            ["8", "3", ".", ".", "7", ".", ".", ".", "."],
            ["6", ".", ".", "1", "9", "5", ".", ".", "."],
            [".", "9", "8", ".", ".", ".", ".", "6", "."],
            ["8", ".", ".", ".", "6", ".", ".", ".", "3"],
            ["4", ".", ".", "8", ".", "3", ".", ".", "1"],
            ["7", ".", ".", ".", "2", ".", ".", ".", "6"],
            [".", "6", ".", ".", ".", ".", "2", "8", "."],
            [".", ".", ".", "4", "1", "9", ".", ".", "5"],
            [".", ".", ".", ".", "8", ".", ".", "7", "9"],
        ]
        # 第一列有两个 8
        board[0][0] = "8"
        board[3][0] = "8"
        assert is_valid_sudoku(board) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
