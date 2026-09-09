"""测试 string_utils 模块"""


class TestReverseString:
    """测试字符串反转"""

    def test_basic_reverse(self):
        """基本反转"""
        from examples.string_utils import reverse_string

        assert reverse_string("hello") == "olleh"

    def test_empty_string(self):
        """空字符串"""
        from examples.string_utils import reverse_string

        assert reverse_string("") == ""

    def test_palindrome(self):
        """回文"""
        from examples.string_utils import reverse_string

        assert reverse_string("aba") == "aba"


class TestCountVowels:
    """测试元音计数"""

    def test_basic_count(self):
        """基本计数"""
        from examples.string_utils import count_vowels

        assert count_vowels("hello") == 2
        assert count_vowels("aeiou") == 5

    def test_no_vowels(self):
        """无元音"""
        from examples.string_utils import count_vowels

        assert count_vowels("rhythm") == 0

    def test_mixed_case(self):
        """混合大小写"""
        from examples.string_utils import count_vowels

        assert count_vowels("AEIOU") == 5


class TestCaesarCipher:
    """测试凯撒密码"""

    def test_basic_shift(self):
        """基本移位"""
        from examples.string_utils import caesar_cipher

        assert caesar_cipher("abc", 1) == "bcd"
        assert caesar_cipher("xyz", 3) == "abc"

    def test_negative_shift(self):
        """负移位"""
        from examples.string_utils import caesar_cipher

        assert caesar_cipher("bcd", -1) == "abc"

    def test_wrap_around(self):
        """环绕"""
        from examples.string_utils import caesar_cipher

        assert caesar_cipher("z", 1) == "a"
        assert caesar_cipher("a", -1) == "z"

    def test_preserve_case(self):
        """保持大小写"""
        from examples.string_utils import caesar_cipher

        assert caesar_cipher("AbC", 1) == "BcD"
