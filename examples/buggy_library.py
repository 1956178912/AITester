"""
示例被测代码：包含多个典型 bug 的实用函数库，用于演示 AITester 的修复能力。
每个函数都设计了一个真实场景下的常见缺陷。
"""


def binary_search(arr: list, target: int) -> int:
    """
    在有序数组中二分查找目标值，返回索引；未找到返回 -1。
    BUG: 初始 right 边界应为 len(arr) - 1，但当前设为 len(arr)，导致越界风险。
    """
    left, right = 0, len(arr)  # BUG: right 应为 len(arr) - 1
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
    BUG: 最后一个元素遗漏——当其中一个列表遍历完后，未追加另一个列表剩余元素。
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
    # BUG: 缺少追加剩余元素的逻辑
    return result


def find_majority_element(nums: list) -> int:
    """
    找出数组中出现次数超过 n/2 的多数元素（保证存在）。
    BUG: 使用了错误的投票算法实现，计数逻辑有误。
    """
    candidate = nums[0]
    count = 1
    for num in nums[1:]:
        if num == candidate:
            count += 1
        else:
            count -= 1
        # BUG: 当 count 降为 0 时，未及时更新 candidate
    return candidate


def sanitize_input(text: str) -> str:
    """
    去除字符串首尾空白字符，并将连续多个空白字符压缩为单个空格。
    BUG: 未处理 None 输入，会抛出 AttributeError。
    """
    # BUG: 没有对 None 或非标量输入做校验
    result = text.strip()
    import re
    result = re.sub(r'\s+', ' ', result)
    return result


def lcs_length(s1: str, s2: str) -> int:
    """
    计算两个字符串的最长公共子序列（LCS）长度。
    BUG: 动态规划表的递推关系有误，当字符不匹配时应取上方或左方的最大值。
    """
    m, n = len(s1), len(s2)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if s1[i - 1] == s2[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                # BUG: 应取 max(dp[i-1][j], dp[i][j-1])，当前写成了 dp[i-1][j-1]
                dp[i][j] = dp[i - 1][j - 1]
    return dp[m][n]
