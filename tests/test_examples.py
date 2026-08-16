# -*- coding: utf-8 -*-
"""
示例代码端到端功能测试

本模块对 examples/ 目录下的三个示例文件进行完整测试：
- calculator.py: 基础数学运算
- string_utils.py: 字符串处理工具
- buggy_library.py: 包含已知 bug 的实用函数库

所有测试使用中文注释，不依赖 LLM API，纯单元测试。
"""

import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from examples.calculator import add, subtract, multiply, divide, factorial
from examples.string_utils import (
    reverse_string,
    is_palindrome,
    count_vowels,
    capitalize_words,
    caesar_cipher,
    longest_common_prefix
)
from examples.buggy_library import (
    binary_search,
    merge_sorted_lists,
    find_majority_element,
    sanitize_input,
    lcs_length
)


# ============================================================================
# calculator.py 测试
# ============================================================================

class TestCalculator:
    """计算器模块测试类"""
    
    # ------------------------------------------------------------------
    # add 函数测试
    # ------------------------------------------------------------------
    
    def test_add_normal(self):
        """正常加法：2 + 3 = 5"""
        assert add(2, 3) == 5
    
    def test_add_negative(self):
        """负数加法：(-1) + (-2) = -3"""
        assert add(-1, -2) == -3
    
    def test_add_zero(self):
        """加零：5 + 0 = 5"""
        assert add(5, 0) == 5
    
    def test_add_float(self):
        """浮点数加法：1.5 + 2.3 = 3.8"""
        assert add(1.5, 2.3) == pytest.approx(3.8)
    
    def test_add_mixed_sign(self):
        """正负数混合加法：10 + (-5) = 5"""
        assert add(10, -5) == 5
    
    # ------------------------------------------------------------------
    # subtract 函数测试
    # ------------------------------------------------------------------
    
    def test_subtract_normal(self):
        """正常减法：10 - 3 = 7"""
        assert subtract(10, 3) == 7
    
    def test_subtract_negative_result(self):
        """结果为负：5 - 10 = -5"""
        assert subtract(5, 10) == -5
    
    def test_subtract_zero(self):
        """减零：7 - 0 = 7"""
        assert subtract(7, 0) == 7
    
    # ------------------------------------------------------------------
    # multiply 函数测试
    # ------------------------------------------------------------------
    
    def test_multiply_normal(self):
        """正常乘法：6 * 7 = 42"""
        assert multiply(6, 7) == 42
    
    def test_multiply_by_zero(self):
        """乘零：5 * 0 = 0"""
        assert multiply(5, 0) == 0
    
    def test_multiply_negative(self):
        """负数乘法：(-3) * 4 = -12"""
        assert multiply(-3, 4) == -12
    
    def test_multiply_both_negative(self):
        """双负数乘法：(-2) * (-5) = 10"""
        assert multiply(-2, -5) == 10
    
    # ------------------------------------------------------------------
    # divide 函数测试
    # ------------------------------------------------------------------
    
    def test_divide_normal(self):
        """正常除法：10 / 2 = 5.0"""
        assert divide(10, 2) == 5.0
    
    def test_divide_float_result(self):
        """结果为浮点数：7 / 2 = 3.5"""
        assert divide(7, 2) == 3.5
    
    def test_divide_by_zero(self):
        """除零应抛出 ValueError"""
        with pytest.raises(ValueError, match="除数不能为零"):
            divide(10, 0)
    
    def test_divide_negative(self):
        """负数除法：(-10) / 2 = -5.0"""
        assert divide(-10, 2) == -5.0
    
    # ------------------------------------------------------------------
    # factorial 函数测试
    # ------------------------------------------------------------------
    
    def test_factorial_zero(self):
        """0 的阶乘：0! = 1"""
        assert factorial(0) == 1
    
    def test_factorial_positive(self):
        """正数阶乘：5! = 120"""
        assert factorial(5) == 120
    
    def test_factorial_one(self):
        """1 的阶乘：1! = 1"""
        assert factorial(1) == 1
    
    def test_factorial_negative(self):
        """负数阶乘应抛出 ValueError"""
        with pytest.raises(ValueError, match="阶乘不支持负数输入"):
            factorial(-1)
    
    def test_factorial_large(self):
        """较大数阶乘：10! = 3628800"""
        assert factorial(10) == 3628800


# ============================================================================
# string_utils.py 测试
# ============================================================================

class TestStringUtils:
    """字符串工具模块测试类"""
    
    # ------------------------------------------------------------------
    # reverse_string 函数测试
    # ------------------------------------------------------------------
    
    def test_reverse_string_simple(self):
        """简单字符串反转：hello -> olleh"""
        assert reverse_string("hello") == "olleh"
    
    def test_reverse_string_empty(self):
        """空字符串反转"""
        assert reverse_string("") == ""
    
    def test_reverse_string_single_char(self):
        """单字符字符串反转"""
        assert reverse_string("a") == "a"
    
    def test_reverse_string_palindrome(self):
        """回文字符串反转后不变：aba -> aba"""
        assert reverse_string("aba") == "aba"
    
    def test_reverse_string_with_spaces(self):
        """含空格字符串反转：hello world -> dlrow olleh"""
        assert reverse_string("hello world") == "dlrow olleh"
    
    # ------------------------------------------------------------------
    # is_palindrome 函数测试
    # ------------------------------------------------------------------
    
    def test_is_palindrome_simple(self):
        """简单回文：aba 应为 True"""
        assert is_palindrome("aba") is True
    
    def test_is_palindrome_mixed_case(self):
        """大小写回文：Racecar 应为 True（忽略大小写）"""
        assert is_palindrome("Racecar") is True
    
    def test_is_palindrome_with_punctuation(self):
        """含标点和空格的回文："A man, a plan, a canal: Panama" 应为 True"""
        assert is_palindrome("A man, a plan, a canal: Panama") is True
    
    def test_is_palindrome_not_palindrome(self):
        """非回文字符串：hello 应为 False"""
        assert is_palindrome("hello") is False
    
    def test_is_palindrome_empty(self):
        """空字符串是回文"""
        assert is_palindrome("") is True
    
    def test_is_palindrome_single_char(self):
        """单字符是回文"""
        assert is_palindrome("a") is True
    
    def test_is_palindrome_with_numbers(self):
        """含数字的回文：12321 应为 True"""
        assert is_palindrome("12321") is True
    
    # ------------------------------------------------------------------
    # count_vowels 函数测试
    # ------------------------------------------------------------------
    
    def test_count_vowels_basic(self):
        """基础元音统计：hello 有 2 个元音"""
        assert count_vowels("hello") == 2
    
    def test_count_vowels_all_vowels(self):
        """全元音字符串：aeiou 有 5 个元音"""
        assert count_vowels("aeiou") == 5
    
    def test_count_vowels_no_vowels(self):
        """无元音字符串：rhythm 有 0 个元音"""
        assert count_vowels("rhythm") == 0
    
    def test_count_vowels_case_insensitive(self):
        """不区分大小写：AEIOU 应返回 5"""
        assert count_vowels("AEIOU") == 5
    
    def test_count_vowels_mixed_case(self):
        """混合大小写：aEiOu 应返回 5"""
        assert count_vowels("aEiOu") == 5
    
    def test_count_vowels_empty(self):
        """空字符串"""
        assert count_vowels("") == 0
    
    def test_count_vowels_with_numbers(self):
        """含数字：abc123 有 1 个元音"""
        assert count_vowels("abc123") == 1
    
    # ------------------------------------------------------------------
    # capitalize_words 函数测试
    # ------------------------------------------------------------------
    
    def test_capitalize_words_basic(self):
        """基础首字母大写：hello world -> Hello World"""
        assert capitalize_words("hello world") == "Hello World"
    
    def test_capitalize_words_single_word(self):
        """单单词：python -> Python"""
        assert capitalize_words("python") == "Python"
    
    def test_capitalize_words_already_capitalized(self):
        """已大写字符串保持不变"""
        assert capitalize_words("Hello World") == "Hello World"
    
    def test_capitalize_words_empty(self):
        """空字符串"""
        assert capitalize_words("") == ""
    
    def test_capitalize_words_with_numbers(self):
        """含数字的字符串：hello123 -> Hello123"""
        assert capitalize_words("hello123") == "Hello123"
    
    # ------------------------------------------------------------------
    # caesar_cipher 函数测试
    # ------------------------------------------------------------------
    
    def test_caesar_cipher_encrypt(self):
        """Caesar 加密：Hello 偏移 3 -> Khoor"""
        assert caesar_cipher("Hello", 3) == "Khoor"
    
    def test_caesar_cipher_decrypt(self):
        """Caesar 解密：Khoor 偏移 -3 -> Hello"""
        assert caesar_cipher("Khoor", -3) == "Hello"
    
    def test_caesar_cipher_preserve_non_alpha(self):
        """保留非字母字符：Hello, World! 偏移 3"""
        assert caesar_cipher("Hello, World!", 3) == "Khoor, Zruog!"
    
    def test_caesar_cipher_wrap_around(self):
        """循环移位：xyz 偏移 3 -> abc"""
        assert caesar_cipher("xyz", 3) == "abc"
    
    def test_caesar_cipher_encrypt_decrypt_roundtrip(self):
        """加密解密往返：encrypt 后 decrypt 应得到原文"""
        original = "Test Message 123"
        encrypted = caesar_cipher(original, 7)
        decrypted = caesar_cipher(encrypted, -7)
        assert decrypted == original
    
    def test_caesar_cipher_shift_26(self):
        """偏移 26（完整循环）应返回原文"""
        assert caesar_cipher("Hello", 26) == "Hello"
    
    def test_caesar_cipher_empty(self):
        """空字符串"""
        assert caesar_cipher("", 5) == ""
    
    # ------------------------------------------------------------------
    # longest_common_prefix 函数测试
    # ------------------------------------------------------------------
    
    def test_longest_common_prefix_basic(self):
        """基础公共前缀：[flower,flow,flight] -> fl"""
        assert longest_common_prefix(["flower", "flow", "flight"]) == "fl"
    
    def test_longest_common_prefix_none(self):
        """无公共前缀：[dog,racecar,car] -> 空串"""
        assert longest_common_prefix(["dog", "racecar", "car"]) == ""
    
    def test_longest_common_prefix_single(self):
        """单元素列表：[abc] -> abc"""
        assert longest_common_prefix(["abc"]) == "abc"
    
    def test_longest_common_prefix_all_same(self):
        """所有元素相同"""
        assert longest_common_prefix(["abc", "abc", "abc"]) == "abc"
    
    def test_longest_common_prefix_empty_list(self):
        """空列表"""
        assert longest_common_prefix([]) == ""
    
    def test_longest_common_prefix_empty_string(self):
        """含空字符串"""
        assert longest_common_prefix(["", "abc"]) == ""
    
    def test_longest_common_prefix_partial(self):
        """部分公共前缀"""
        assert longest_common_prefix(["interspecies", "interstellar", "interstate"]) == "inters"


# ============================================================================
# buggy_library.py 测试
# ============================================================================

class TestBuggyLibrary:
    """含 bug 的库测试类（测试应反映当前状态）"""
    
    # ------------------------------------------------------------------
    # binary_search 函数测试
    # ------------------------------------------------------------------
    
    def test_binary_search_found(self):
        """二分查找找到元素：[1,2,3,4,5] 查找 3 -> 索引 2"""
        assert binary_search([1, 2, 3, 4, 5], 3) == 2
    
    def test_binary_search_found_first(self):
        """查找第一个元素"""
        assert binary_search([1, 2, 3, 4, 5], 1) == 0
    
    def test_binary_search_found_last(self):
        """查找最后一个元素（注意：bug 可能导致此测试失败）"""
        # 由于 right 初始值为 len(arr) 而非 len(arr)-1，
        # 当查找末尾元素时可能触发 IndexError
        # 此处测试正常情况下的查找
        result = binary_search([1, 2, 3, 4, 5], 5)
        assert result == 4
    
    def test_binary_search_not_found(self):
        """二分查找未找到元素：返回 -1"""
        # bug 已修复：right 初始值已改为 len(arr) - 1
        assert binary_search([1, 2, 3, 4, 5], 6) == -1
    
    def test_binary_search_not_found_at_start(self):
        """查找不存在的第一个元素"""
        assert binary_search([1, 2, 3, 4, 5], 0) == -1
    
    def test_binary_search_single_element_found(self):
        """单元素列表找到目标"""
        assert binary_search([5], 5) == 0
    
    def test_binary_search_single_element_not_found(self):
        """单元素列表未找到目标"""
        assert binary_search([5], 3) == -1
    
    def test_binary_search_empty_list(self):
        """空列表应返回 -1"""
        # bug 已修复：空列表正确返回 -1
        assert binary_search([], 5) == -1
    
    def test_binary_search_target_at_end(self):
        """target 超出数组范围时正确返回 -1"""
        # bug 已修复：超出边界的 target 正确返回 -1
        assert binary_search([1, 2, 3], 10) == -1
    
    # ------------------------------------------------------------------
    # merge_sorted_lists 函数测试
    # ------------------------------------------------------------------
    
    def test_merge_sorted_lists_basic(self):
        """合并两个有序列表：[1,3,5] + [2,4,6] -> [1,2,3,4,5,6]"""
        assert merge_sorted_lists([1, 3, 5], [2, 4, 6]) == [1, 2, 3, 4, 5, 6]
    
    def test_merge_sorted_lists_empty_first(self):
        """第一个列表为空"""
        assert merge_sorted_lists([], [1, 2, 3]) == [1, 2, 3]
    
    def test_merge_sorted_lists_empty_second(self):
        """第二个列表为空"""
        assert merge_sorted_lists([1, 2, 3], []) == [1, 2, 3]
    
    def test_merge_sorted_lists_both_empty(self):
        """两个列表都为空"""
        assert merge_sorted_lists([], []) == []
    
    def test_merge_sorted_lists_overlapping(self):
        """有重叠元素的列表"""
        assert merge_sorted_lists([1, 2, 3], [2, 3, 4]) == [1, 2, 2, 3, 3, 4]
    
    def test_merge_sorted_lists_single_element(self):
        """单元素列表"""
        assert merge_sorted_lists([1], [2]) == [1, 2]
    
    # ------------------------------------------------------------------
    # find_majority_element 函数测试
    # ------------------------------------------------------------------
    
    def test_find_majority_element_basic(self):
        """基础多数元素：[2,2,1,1,1,2,2] -> 2"""
        assert find_majority_element([2, 2, 1, 1, 1, 2, 2]) == 2
    
    def test_find_majority_element_all_same(self):
        """所有元素相同"""
        assert find_majority_element([5, 5, 5, 5]) == 5
    
    def test_find_majority_element_three_elements(self):
        """三元素情况：[1, 2, 1] -> 1"""
        assert find_majority_element([1, 2, 1]) == 1
    
    def test_find_majority_element_large(self):
        """较大列表：多数元素在末尾"""
        nums = [3, 3, 4, 2, 3, 3, 3]
        assert find_majority_element(nums) == 3
    
    # ------------------------------------------------------------------
    # sanitize_input 函数测试
    # ------------------------------------------------------------------
    
    def test_sanitize_input_basic(self):
        """基础清理：'  hello  world  ' -> 'hello world'"""
        assert sanitize_input("  hello  world  ") == "hello world"
    
    def test_sanitize_input_no_extra_spaces(self):
        """无多余空格的字符串"""
        assert sanitize_input("hello") == "hello"
    
    def test_sanitize_input_empty(self):
        """空字符串"""
        assert sanitize_input("") == ""
    
    def test_sanitize_input_only_spaces(self):
        """仅含空格的字符串"""
        assert sanitize_input("   ") == ""
    
    def test_sanitize_input_none_value(self):
        """None 值应返回空字符串（注意：代码中使用了 None，应正常工作）"""
        # 由于代码已修复（使用 None 而非 null），此测试应通过
        assert sanitize_input(None) == ""
    
    def test_sanitize_input_with_numbers(self):
        """含数字的字符串"""
        assert sanitize_input("  abc 123  def  ") == "abc 123 def"
    
    # ------------------------------------------------------------------
    # lcs_length 函数测试
    # ------------------------------------------------------------------
    
    def test_lcs_length_basic(self):
        """基础 LCS：'ABCBDAB' 和 'BDCABA' -> 4"""
        assert lcs_length("ABCBDAB", "BDCABA") == 4
    
    def test_lcs_length_no_common(self):
        """无公共子序列"""
        assert lcs_length("ABC", "DEF") == 0
    
    def test_lcs_length_identical(self):
        """相同字符串"""
        assert lcs_length("ABC", "ABC") == 3
    
    def test_lcs_length_empty_first(self):
        """第一个字符串为空"""
        assert lcs_length("", "ABC") == 0
    
    def test_lcs_length_empty_second(self):
        """第二个字符串为空"""
        assert lcs_length("ABC", "") == 0
    
    def test_lcs_length_both_empty(self):
        """两个字符串都为空"""
        assert lcs_length("", "") == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
