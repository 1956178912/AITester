"""
示例被测代码：包含多个典型 bug 的实用函数库，用于演示 AITester 的修复能力。
每个函数都设计了一个真实场景下的常见缺陷。

Bug 清单：
    1. binary_search:   right 初始值应为 len(arr)-1，当前为 len(arr) 导致越界
    2. sanitize_input:  使用了 Python 不支持的 null 关键字，应为 None
    （其余函数暂无 bug，作为对照组）
"""

import re


def binary_search(arr: list, target: int) -> int:
    """
    在有序数组中二分查找目标值，返回索引；未找到返回 -1。

    算法原理：
        维护 [left, right] 闭区间，每次取中点与目标比较，
        缩小搜索范围直到找到目标或区间为空。

    Args:
        arr: 已排序的列表（升序）。
        target: 要查找的目标值。

    Returns:
        目标值的索引，未找到时返回 -1。
    """
    left, right = 0, len(arr) - 1
    while left <= right:
        mid = (left + right) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            left = mid + 1
        else:
            right = mid - 1  # 修复：原代码 right = mid 导致区间不收缩，可能无限循环
    return -1


def merge_sorted_lists(list1: list, list2: list) -> list:
    """
    合并两个已排序列表为一个有序列表。

    使用双指针法，每次取两个列表当前较小元素追加到结果中。
    时间复杂度 O(m+n)，空间复杂度 O(m+n)。

    Args:
        list1: 第一个已排序列表（升序）。
        list2: 第二个已排序列表（升序）。

    Returns:
        合并后的有序列表。
    """
    result = []
    i, j = 0, 0
    # 双指针归并：各取较小元素依次追加
    while i < len(list1) and j < len(list2):
        if list1[i] <= list2[j]:
            result.append(list1[i])
            i += 1
        else:
            result.append(list2[j])
            j += 1
    # 追加剩余元素（最多只有一个列表有剩余）
    result.extend(list1[i:])
    result.extend(list2[j:])
    return result


def find_majority_element(nums: list) -> int:
    """
    找出数组中出现次数超过 n/2 的多数元素（保证存在）。

    使用 Boyer-Moore 投票算法，时间复杂度 O(n)，空间复杂度 O(1)。
    核心思想：不同元素互相抵消，最终剩下的即为多数元素。

    Args:
        nums: 输入整数列表。

    Returns:
        出现次数超过 n/2 的多数元素。
    """
    candidate = nums[0]
    count = 1
    for num in nums[1:]:
        if num == candidate:
            count += 1
        else:
            count -= 1
            if count == 0:
                candidate = num
                count = 1
    return candidate


def sanitize_input(text: str) -> str:
    """
    去除字符串首尾空白字符，并将连续多个空白字符压缩为单个空格。

    Args:
        text: 待清理的字符串。

    Returns:
        清理后的字符串。
    """
    if text is None:
        return ""
    result = text.strip()
    # 将连续空白字符压缩为单个空格
    result = re.sub(r"\s+", " ", result)
    return result


def lcs_length(s1: str, s2: str) -> int:
    """
    计算两个字符串的最长公共子序列（LCS）长度。

    使用动态规划，空间优化为一维数组。dp[j] 表示当前行与 s2[:j] 的 LCS 长度。
    状态转移：若 s1[i-1] == s2[j-1]，则 dp[j] = prev + 1，
    否则 dp[j] = max(dp[j], dp[j-1])。

    时间复杂度 O(m*n)，空间复杂度 O(min(m,n))。

    Args:
        s1: 第一个字符串。
        s2: 第二个字符串。

    Returns:
        最长公共子序列的长度。
    """
    # 优化：确保 s2 是较短的字符串，以减少 DP 表宽度
    if len(s1) < len(s2):
        s1, s2 = s2, s1

    m, n = len(s1), len(s2)
    if m == 0 or n == 0:
        return 0

    # 一维 DP 数组，初始化为 0
    dp = [0] * (n + 1)

    for i in range(1, m + 1):
        prev = 0  # 记录 dp[i-1][j-1]
        for j in range(1, n + 1):
            temp = dp[j]  # 保存当前值，供下一轮作为 prev
            if s1[i - 1] == s2[j - 1]:
                dp[j] = prev + 1
            else:
                dp[j] = max(dp[j], dp[j - 1])
            prev = temp

    return dp[n]
