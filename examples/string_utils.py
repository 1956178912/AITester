"""
字符串工具函数，包含若干常见逻辑缺陷。
用于测试 AITester 对字符串处理函数的修复能力。

当前版本为"已修复版"，所有函数行为正确。
测试用例通过此文件验证，若 Debugger 将其回退到 buggy 版本则测试失败。

函数清单：
    reverse_string:          字符串反转
    is_palindrome:           回文判断（忽略大小写和非字母数字字符）
    count_vowels:            统计元音字母数量
    capitalize_words:        单词首字母大写
    caesar_cipher:           Caesar 密码加密/解密
    longest_common_prefix:   最长公共前缀
"""


def reverse_string(s: str) -> str:
    """返回反转后的字符串。

    使用 Python 切片语法 s[::-1] 实现，时间复杂度 O(n)。

    Args:
        s: 待反转的字符串。

    Returns:
        反转后的字符串。
    """
    return s[::-1]


def is_palindrome(s: str) -> bool:
    """
    判断字符串是否为回文（忽略大小写和非字母数字字符）。

    算法步骤：
        1. 过滤掉非字母数字字符（如空格、标点）
        2. 统一转为小写
        3. 比较字符串与其反转是否相等

    Args:
        s: 待检测的字符串。

    Returns:
        是回文返回 True，否则返回 False。

    Examples:
        >>> is_palindrome("Racecar")
        True
        >>> is_palindrome("A man, a plan, a canal: Panama")
        True
    """
    # 过滤非字母数字字符并统一转为小写，确保"Racecar"和"racecar"视为相同
    cleaned = "".join(c.lower() for c in s if c.isalnum())
    return cleaned == cleaned[::-1]


def count_vowels(s: str) -> int:
    """统计字符串中元音字母（a,e,i,o,u）的数量（不区分大小写）。

    使用生成器表达式配合 sum()，时间复杂度 O(n)。

    Args:
        s: 待统计的字符串。

    Returns:
        元音字母的数量。
    """
    return sum(1 for c in s.lower() if c in "aeiou")


def capitalize_words(s: str) -> str:
    """将字符串中每个单词的首字母大写。

    使用 str.title() 方法，遇非字母字符（如空格、连字符）会自动分割单词。

    Args:
        s: 待处理的字符串。

    Returns:
        首字母大写后的字符串。
    """
    return s.title()


def caesar_cipher(text: str, shift: int) -> str:
    """
    实现 Caesar 密码加密/解密（仅处理英文字母，保留大小写和非字母字符）。

    算法原理：
        - 对每个英文字母，计算其在字母表中的位置（0-25）
        - 加上偏移量后对 26 取模，实现循环移位
        - 非字母字符（空格、标点、数字）原样保留

    Args:
        text: 待加密/解密的文本。
        shift: 偏移量（正数加密，负数解密，如 shift=-3 等价于加密量 23）。

    Returns:
        加密/解密后的文本。

    Examples:
        >>> caesar_cipher("Hello", 3)
        'Khoor'
        >>> caesar_cipher("Khoor", -3)
        'Hello'
    """
    result = []
    for ch in text:
        if ch.isalpha():
            # 根据大小写选择基准字母（'A'=65 或 'a'=97）
            base = ord("A") if ch.isupper() else ord("a")
            # 循环移位：(当前位置 + 偏移量) % 26
            result.append(chr((ord(ch) - base + shift) % 26 + base))
        else:
            # 非字母字符原样保留
            result.append(ch)
    return "".join(result)


def longest_common_prefix(strs: list) -> str:
    """
    找出字符串列表的最长公共前缀。

    算法：先对字符串列表排序，然后比较首尾两个字符串的公共前缀。
    排序后首尾字符串的差异最大，其公共前缀即为所有字符串的公共前缀。
    时间复杂度：O(N * M * log N)，N 为字符串数量，M 为平均字符串长度。

    Args:
        strs: 字符串列表。

    Returns:
        最长公共前缀字符串；空列表返回空串。

    Examples:
        >>> longest_common_prefix(["flower","flow","flight"])
        'fl'
        >>> longest_common_prefix(["dog","racecar","car"])
        ''
    """
    if not strs:
        return ""
    # 排序后首尾差异最大，只需比较首尾即可
    strs.sort()
    s1, s2 = strs[0], strs[-1]
    for i in range(min(len(s1), len(s2))):
        if s1[i] != s2[i]:
            return s1[:i]
    return s1
