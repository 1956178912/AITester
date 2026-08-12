"""
示例被测代码：字符串工具函数，包含若干常见逻辑缺陷。
用于测试 AITester 对字符串处理函数的修复能力。
"""


def reverse_string(s: str) -> str:
    """返回反转后的字符串。"""
    return s[::-1]


def is_palindrome(s: str) -> bool:
    """
    判断字符串是否为回文（忽略大小写和非字母数字字符）。
    BUG: 未过滤非字母数字字符，导致 "A man, a plan, a canal: Panama" 判断错误。
    """
    # BUG: 没有去除非字母数字字符和统一大小写
    return s == s[::-1]


def count_vowels(s: str) -> int:
    """统计字符串中元音字母（a,e,i,o,u）的数量（不区分大小写）。"""
    return sum(1 for c in s.lower() if c in 'aeiou')


def capitalize_words(s: str) -> str:
    """将字符串中每个单词的首字母大写。"""
    return s.title()


def caesar_cipher(text: str, shift: int) -> str:
    """
    实现 Caesar 密码加密/解密（仅处理英文字母，保留大小写）。
    BUG: 移位计算未处理边界 wrap-around，导致大写/小写字母超出 ASCII 范围。
    """
    result = []
    for ch in text:
        if ch.isalpha():
            # BUG: 没有正确 wrap-around，'z' + 1 会变成 '{'
            result.append(chr(ord(ch) + shift))
        else:
            result.append(ch)
    return ''.join(result)


def longest_common_prefix(strs: list) -> str:
    """
    找出字符串列表的最长公共前缀。
    BUG: 当输入为空列表时未处理，会抛出 IndexError。
    """
    # BUG: 没有处理空列表的情况
    strs.sort()
    s1, s2 = strs[0], strs[-1]
    for i in range(min(len(s1), len(s2))):
        if s1[i] != s2[i]:
            return s1[:i]
    return s1
