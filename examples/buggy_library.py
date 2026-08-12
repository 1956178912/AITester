"""
示例被测代码：包含多个典型 bug 的实用函数库，用于演示 AITester 的修复能力。
每个函数都设计了一个真实场景下的常见缺陷。
"""

import re


def binary_search(arr: list, target: int) -> int:
    """
    在有序数组中二分查找目标值，返回索引；未找到返回 -1。
    BUG: right 初始值应为 len(arr) - 1，当前设为 len(arr) 导致越界风险。
    """
    # BUG: right 应为 len(arr) - 1，否则 mid 可能等于 len(arr) 越界
    left, right = 0, len(arr)
    while left <= right:
        mid = (left + right) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            left = mid + 1
        else:
            right = mid - 1
    return -1


def merge_sorted_lists(list1: list, list2: list) -> list:
    """
    合并两个已排序列表为一个有序列表。
    BUG: 当其中一个列表遍历完后，未追加另一个列表剩余元素，导致尾部遗漏。
    """
    result = []
    i, j = 0, 0
    while i < len(list1) and j < len(list2):
        if list1[i] <= list2[j]:
            result.append(list1[i])
            i += 1
        else:
            result.append(list2[j])
            j += 1
    # BUG: 缺少追加剩余元素的代码，导致 list1 或 list2 尾部数据丢失
    return result


def find_majority_element(nums: list) -> int:
    """
    找出数组中出现次数超过 n/2 的多数元素（保证存在）。
    BUG: Boyer-Moore 投票算法实现有误——count 降为 0 后才更新 candidate，
         应在相等时先减再判断是否归零，顺序颠倒导致结果错误。
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
    BUG: 未处理 None 输入，传入 None 时会抛出 AttributeError。
    """
    # BUG: text 为 None 时，.strip() 会抛出 AttributeError
    result = text.strip()
    result = re.sub(r'\s+', ' ', result)
    return result


def lcs_length(s1: str, s2: str) -> int:
    """
    计算两个字符串的最长公共子序列（LCS）长度。
    BUG: 动态规划递推关系有误——字符不匹配时取 dp[i-1][j-1]（对角线）而非 max(dp[i-1][j], dp[i][j-1])，
         导致 LCS 长度计算偏低。
    """
    m, n = len(s1), len(s2)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if s1[i - 1] == s2[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                # BUG: 应取 max(dp[i-1][j], dp[i][j-1])，当前取的是 dp[i-1][j-1]
                dp[i][j] = dp[i - 1][j - 1]
    return dp[m][n]
