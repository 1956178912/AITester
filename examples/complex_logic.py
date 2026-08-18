"""
复杂逻辑示例：包含多种 bug 模式的复杂函数

本文件提供具有复杂逻辑的示例代码，用于测试 AITester 处理更复杂场景的能力。
"""


def find_max_subarray_sum(nums: list[int]) -> int:
    """
    查找数组中最大子数组和（Kadane 算法）。

    Args:
        nums: 整数列表

    Returns:
        最大子数组和

    Raises:
        ValueError: 当输入列表为空时
    """
    if not nums:
        raise ValueError("输入列表不能为空")

    max_sum = nums[0]
    current_sum = nums[0]

    for num in nums[1:]:
        current_sum = max(num, current_sum + num)
        max_sum = max(max_sum, current_sum)

    return max_sum


def validate_email(email: str) -> bool:
    """
    简单的邮箱格式验证。

    Args:
        email: 待验证的邮箱地址

    Returns:
        True 表示格式有效，False 表示无效
    """
    import re

    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))


def merge_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """
    合并重叠区间。

    Args:
        intervals: 区间列表，每个区间为 (start, end) 元组

    Returns:
        合并后的不重叠区间列表

    Examples:
        >>> merge_intervals([(1, 3), (2, 6), (8, 10)])
        [(1, 6), (8, 10)]
        >>> merge_intervals([(1, 4), (4, 5)])
        [(1, 5)]
    """
    if not intervals:
        return []

    # 按起始时间排序
    sorted_intervals = sorted(intervals, key=lambda x: x[0])
    merged = [sorted_intervals[0]]

    for current in sorted_intervals[1:]:
        last = merged[-1]
        if current[0] <= last[1]:
            # 重叠，合并区间
            merged[-1] = (last[0], max(last[1], current[1]))
        else:
            merged.append(current)

    return merged


def lcs_dp(s1: str, s2: str) -> int:
    """
    使用动态规划计算最长公共子序列长度。

    Args:
        s1: 第一个字符串
        s2: 第二个字符串

    Returns:
        最长公共子序列长度
    """
    m, n = len(s1), len(s2)
    dp = [[0] * (n + 1) for _ in range(m + 1)]

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if s1[i - 1] == s2[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])

    return dp[m][n]


def contains_duplicate(nums: list[int], k: int) -> bool:
    """
    判断数组中是否存在两个不同索引 i 和 j，
    满足 nums[i] == nums[j] 且 |i - j| <= k。

    Args:
        nums: 整数列表
        k: 最大索引差值

    Returns:
        True 表示存在重复，False 表示不存在
    """
    window = set()

    for i, num in enumerate(nums):
        if i > k:
            window.remove(nums[i - k - 1])
        if num in window:
            return True
        window.add(num)

    return False


def rotate_matrix(matrix: list[list[int]]) -> list[list[int]]:
    """
    顺时针旋转 90 度矩阵。

    Args:
        matrix: N x N 二维列表

    Returns:
        旋转后的矩阵
    """
    n = len(matrix)
    # 转置
    transposed = [[matrix[j][i] for j in range(n)] for i in range(n)]
    # 每行反转
    return [row[::-1] for row in transposed]


def is_valid_sudoku(board: list[list[str]]) -> bool:
    """
    验证 9x9 数独棋盘是否有效。

    Args:
        board: 9x9 棋盘，'.' 表示空位

    Returns:
        True 表示有效，False 表示无效
    """
    rows = [set() for _ in range(9)]
    cols = [set() for _ in range(9)]
    boxes = [set() for _ in range(9)]

    for i in range(9):
        for j in range(9):
            cell = board[i][j]
            if cell == ".":
                continue

            box_idx = (i // 3) * 3 + j // 3

            if cell in rows[i]:
                return False
            if cell in cols[j]:
                return False
            if cell in boxes[box_idx]:
                return False

            rows[i].add(cell)
            cols[j].add(cell)
            boxes[box_idx].add(cell)

    return True


if __name__ == "__main__":
    # 快速测试
    print("最大子数组和:", find_max_subarray_sum([-2, 1, -3, 4, -1, 2, 1, -5, 4]))
    print("邮箱验证:", validate_email("test@example.com"))
    print("合并区间:", merge_intervals([(1, 3), (2, 6), (8, 10)]))
    print("LCS长度:", lcs_dp("ABCBDAB", "BDCABA"))
    print("包含重复:", contains_duplicate([1, 2, 3, 1], 3))
    print("矩阵旋转:", rotate_matrix([[1, 2, 3], [4, 5, 6], [7, 8, 9]]))
