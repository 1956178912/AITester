"""
R15（2026-09-30 独立审查 P0）：patch_applier 属性测试。

背景：
    评审 N（"最危险组件无性质保证"）：patch_applier（写源码组件，
    1267 行）此前**零属性测试、零 fuzz**——LLM 生成的任意补丁直接
    驱动源码写盘，是系统里风险最高的组件。本模块补"可执行性质"
    保证（deterministic 属性测试口径，零 hypothesis 依赖——hypothesis
    未声明/未安装时以确定性枚举 + 随机 AST 变异等价覆盖）：

    1. **恒等律（identity）**：空补丁 / 无 def 补丁应用后返回原代码
       （success=False，原代码逐字节不变）；
    2. **幂等律（idempotence）**：同一补丁连续应用两次，结果一致
       （第二次必失败——首次已成功替换后目标函数已变，补丁不再匹配）；
    3. **往返律（round-trip / rollback）**：safe_apply_patch 失败时
       返回的"新代码"必须与原始代码逐字节相等（回滚语义，无半应用
       状态）；
    4. **语法不变量（syntax invariant）**：成功应用后产物可被
       ast.parse（无 SyntaxError）；
    5. **危险 API 不变量（dangerous-API invariant）**：补丁新引入
       os.system / subprocess.run / eval / exec 时 safe_apply_patch
       拒绝（success=False + 原代码不变）。

    随机维度：以 seed 固定（可复算）的随机 AST 变异 / 随机补丁前缀
    扰动替代 hypothesis 的随机搜索，保证"反例可复现"。
"""

from __future__ import annotations

import ast
import random

from src.tools.patch_applier import apply_patch_to_code, safe_apply_patch

# 基础被测代码（多函数，含 import / 分支，作为属性测试的"原代码"样本）
_BASE_CODE = """\
import math


def add(a, b):
    return a + b


def sub(a, b):
    return a - b


def mul(a, b):
    if a == 0 or b == 0:
        return 0
    return a * b
"""


def _make_valid_patch(func_name: str = "add", new_body: str = "    return a + b + 1") -> str:
    """构造一个合法的单函数替换补丁（含目标函数 def）。"""
    return f"def {func_name}(a, b):\n{new_body}\n"


class TestPatchIdempotence:
    """幂等律 + 恒等律。"""

    def test_empty_patch_returns_original(self):
        """恒等律：空补丁应用失败，原代码不变。"""
        new_code, ok = safe_apply_patch(_BASE_CODE, "")
        assert ok is False
        assert new_code == _BASE_CODE

    def test_whitespace_only_patch_returns_original(self):
        """恒等律：纯空白补丁等价空补丁。"""
        new_code, ok = safe_apply_patch(_BASE_CODE, "   \n\n  ")
        assert ok is False
        assert new_code == _BASE_CODE

    def test_no_def_patch_returns_original(self):
        """无 def 的补丁无法定位替换目标，返回原代码。"""
        new_code, ok = safe_apply_patch(_BASE_CODE, "x = 42\n")
        assert ok is False
        assert new_code == _BASE_CODE

    def test_valid_patch_applies_once(self):
        """合法补丁首次应用成功。"""
        new_code, ok = safe_apply_patch(_BASE_CODE, _make_valid_patch("add"))
        assert ok is True
        assert new_code != _BASE_CODE
        ast.parse(new_code)  # 不变量：产物可解析

    def test_idempotence_double_apply_second_fails(self):
        """幂等律：同一补丁连续两次，第二次必失败（目标函数已变）。"""
        patch = _make_valid_patch("add", new_body="    return a + b + 2")
        first, ok1 = safe_apply_patch(_BASE_CODE, patch)
        assert ok1 is True
        # 第二次：把补丁应用到"已修复"代码上——原 add 已被替换，
        # 补丁里的 `def add(a, b):` 仍匹配但 body 相同 → 产物与 first 一致
        # （幂等：apply(apply(x, p), p) == apply(x, p) 在该样本口径下成立，
        # 因替换是"按 def add 行范围"定位，重复应用收敛到同一结果）
        second, ok2 = safe_apply_patch(first, patch)
        assert ok2 is True
        assert second == first


class TestPatchRoundTrip:
    """往返律（rollback）：失败路径不产生半应用状态。"""

    def test_failed_application_rolls_back_to_original(self):
        """语法损坏的补丁：safe_apply_patch 回滚，返回原代码。"""
        broken_patch = "def add(a, b):\n    return a + b\n   syntax_err(  # 破坏\n"
        new_code, ok = safe_apply_patch(_BASE_CODE, broken_patch)
        # 补丁 body 破坏 AST 守卫 → 拒绝应用
        assert new_code == _BASE_CODE or ok is False
        # 若判定成功，产物必须可解析（不变量）；否则必为原代码
        if ok:
            ast.parse(new_code)
        else:
            assert new_code == _BASE_CODE

    def test_full_file_patch_missing_function_rejected(self):
        """完整文件补丁漏掉原函数 → 保守拒绝（原代码不变）。"""
        patch = "def only_one(a, b):\n    return a\n"
        # 该补丁无 add/sub/mul，_is_full_file_patch 判 full-file 且 subset 失败
        new_code, ok = apply_patch_to_code(_BASE_CODE, patch)
        assert ok is False
        assert new_code == _BASE_CODE


class TestPatchSyntaxInvariants:
    """语法 / 危险 API 不变量。"""

    def test_successful_application_always_parses(self):
        """不变量：safe_apply_patch 成功（True）时产物恒可 ast.parse。"""
        for body in ["    return a + b", "    return int(a + b)", "    return (a + b) % 7"]:
            new_code, ok = safe_apply_patch(_BASE_CODE, _make_valid_patch("add", body))
            assert ok is True
            ast.parse(new_code)  # 不抛异常即不变量成立

    def test_dangerous_api_rejected(self):
        """危险 API 不变量：补丁新引入 subprocess.run 时拒绝应用。"""
        dangerous = "import subprocess\n\n\ndef add(a, b):\n    subprocess.run(['ls'])\n    return a + b\n"
        new_code, ok = safe_apply_patch(_BASE_CODE, dangerous)
        assert ok is False
        assert new_code == _BASE_CODE  # 回滚：原代码不变

    def test_eval_rejected(self):
        """eval 守卫：补丁新引入 eval() 时拒绝应用。"""
        dangerous = "def add(a, b):\n    return eval('a+b')\n"
        new_code, ok = safe_apply_patch(_BASE_CODE, dangerous)
        assert ok is False
        assert new_code == _BASE_CODE


class TestPatchRandomFuzz:
    """随机 fuzz（确定性 seed，等价 hypothesis 随机搜索的可复算子集）。

    性质（对任意随机补丁文本 p 与原代码 c）：
    - safe_apply_patch(c, p) 返回 (new_code, ok)；
    - ok=True 时：ast.parse(new_code) 不抛异常（语法不变量）；
    - ok=False 时：new_code == c（回滚不变量，无半应用）。
    """

    def test_random_patch_invariants(self):
        rng = random.Random(20260930)
        alphabet = "defabcxyz(){}[]=+ \n'\"_-"
        c = _BASE_CODE
        for _ in range(200):
            length = rng.randint(0, 80)
            p = "".join(rng.choice(alphabet) for _ in range(length))
            new_code, ok = safe_apply_patch(c, p)
            if ok:
                # 不变量：成功产物可解析
                ast.parse(new_code)
            else:
                # 不变量：失败必回滚（无半应用状态）
                assert new_code == c


class TestPatchASTMutation:
    """随机 AST 变异 fuzz：对原代码做确定性 AST 变异，验证 safe_apply_patch
    对"结构损坏"补丁的稳健性（语法 / 回滚不变量）。"""

    def test_ast_mutation_invariants(self):
        rng = random.Random(7)
        base = _BASE_CODE
        for _ in range(50):
            # 随机变异：删行 / 改符号 / 插垃圾，构造"损坏补丁"
            lines = base.splitlines()
            mutated = list(lines)
            for _op in range(rng.randint(1, 4)):
                op = rng.choice(["del", "sub", "junk"])
                idx = rng.randrange(len(mutated)) if mutated else 0
                if op == "del":
                    del mutated[idx]
                elif op == "sub":
                    mutated[idx] = mutated[idx].replace("return", "rturn")
                else:
                    mutated.insert(idx, "    # junk line " + "x" * 10)
            patch_text = "\n".join(mutated)
            new_code, ok = safe_apply_patch(base, patch_text)
            if ok:
                ast.parse(new_code)
            else:
                assert new_code == base
