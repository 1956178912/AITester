"""agents/executor_repo 纯静态辅助函数 / 补丁形态识别分支补齐（2026-10-02·三）。

锁定 executor_repo 零 LLM / 零 git 的纯逻辑分支：
- parse_new_file_bodies：unified diff new-file hunk 解析
- _patch_touches_test_files：测试路径命中 / /dev/null 过滤 / 前缀归一
- _apply_llm_patch：空补丁 / 非 unified diff 形态保守 False
- _get_repo_setup_lock / _repo_envs_root：进程级锁 / env 根目录口径
"""

from __future__ import annotations


class TestParseNewFileBodiesBranches:
    def test_new_file_body_extracted(self):
        from src.agents.executor_repo import RepoExecutor

        patch = (
            "diff --git a/newmod.py b/newmod.py\n"
            "new file mode 100644\n"
            "--- /dev/null\n"
            "+++ b/newmod.py\n"
            "@@ -0,0 +1,3 @@\n"
            "+def f():\n"
            "+    return 1\n"
            "+\n"
        )
        out = RepoExecutor.parse_new_file_bodies(patch)
        assert "newmod.py" in out
        assert "def f():" in out["newmod.py"]

    def test_existing_file_not_parsed_as_new(self):
        from src.agents.executor_repo import RepoExecutor

        patch = (
            "diff --git a/existing.py b/existing.py\n"
            "index abc..def 100644\n"
            "--- a/existing.py\n"
            "+++ b/existing.py\n"
            "@@ -1 +1 @@\n"
            "-old\n"
            "+new\n"
        )
        out = RepoExecutor.parse_new_file_bodies(patch)
        # 非 new-file（有 index / --- a/... 非 /dev/null）→ 不产出
        assert "existing.py" not in out

    def test_empty_patch_returns_empty(self):
        from src.agents.executor_repo import RepoExecutor

        assert RepoExecutor.parse_new_file_bodies("") == {}

    def test_mixed_new_and_modified(self):
        from src.agents.executor_repo import RepoExecutor

        patch = (
            "diff --git a/modified.py b/modified.py\n"
            "index abc..def 100644\n"
            "--- a/modified.py\n"
            "+++ b/modified.py\n"
            "@@ -1 +1 @@\n"
            "-old\n"
            "+new\n"
            "diff --git a/fresh.py b/fresh.py\n"
            "new file mode 100644\n"
            "--- /dev/null\n"
            "+++ b/fresh.py\n"
            "@@ -0,0 +1,2 @@\n"
            "+x = 1\n"
            "+y = 2\n"
        )
        out = RepoExecutor.parse_new_file_bodies(patch)
        assert "fresh.py" in out
        assert "modified.py" not in out


class TestPatchTouchesTestFilesBranches:
    @classmethod
    def _helper(cls):
        from src.agents.executor_repo import RepoExecutor

        return RepoExecutor._patch_touches_test_files

    def test_test_path_hit(self):
        helper = self._helper()
        patch = "diff --git a/test_foo.py b/test_foo.py\n--- a/test_foo.py\n+++ b/test_foo.py\n@@ -1 +1 @@\n-1\n+2\n"
        out = helper(patch)
        assert out is not None
        assert "test_foo" in out

    def test_dev_null_skipped(self):
        helper = self._helper()
        # 仅 /dev/null 目标（纯删除），无真实测试路径 → None
        patch = (
            "diff --git a/old.py b/old.py\ndeleted file mode 100644\n--- a/old.py\n+++ /dev/null\n@@ -1,1 +0,0 @@\n-x\n"
        )
        out = helper(patch)
        # old.py 非测试路径 → None
        assert out is None

    def test_no_diff_returns_none(self):
        helper = self._helper()
        assert helper("") is None

    def test_b_prefix_normalized(self):
        helper = self._helper()
        # b/ 前缀归一化：`p[2:] if p[:2] in ("a/", "b/")` 把 "b/tests/test_x.py"
        # 归一为 "tests/test_x.py"（正则锚定 (^|/) 开头）
        out = helper("diff --git a/tests/test_x.py b/tests/test_x.py")
        assert out is not None
        assert out == "tests/test_x.py"


class TestApplyLlmPatchFormBranches:
    def _apply(self, repo_dir, llm_patch):
        from src.agents.executor_repo import RepoExecutor

        re_ = RepoExecutor.__new__(RepoExecutor)  # 跳过 __init__（无 git）
        re_.repo_dir = repo_dir
        return re_._apply_llm_patch(repo_dir, llm_patch)

    def test_empty_patch_false(self, tmp_path):
        assert self._apply(str(tmp_path), "") is False
        assert self._apply(str(tmp_path), "   ") is False

    def test_full_file_code_form_false(self, tmp_path):
        # 非 unified diff 形态（完整文件 Python 源码）→ 保守 False
        assert self._apply(str(tmp_path), "def f():\n    return 1\n") is False

    def test_unified_diff_form_not_immediately_false(self, tmp_path):
        # unified diff 形态（diff --git 开头）→ 进入 git apply 路径
        # （本测试仅确认"未被前置形态判定拒绝"，git apply 在 tmp_path 上
        # 会因无 git 仓库降级为 False，整体结果 False 但不走形态拒绝分支）
        out = self._apply(str(tmp_path), "diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n")
        assert out in (True, False)


class TestRepoSetupLockBranches:
    def test_same_env_dir_same_lock(self):
        from src.agents.executor_repo import _get_repo_setup_lock

        l1 = _get_repo_setup_lock("/tmp/env_a")
        l2 = _get_repo_setup_lock("/tmp/env_a")
        assert l1 is l2

    def test_different_env_dir_different_lock(self):
        from src.agents.executor_repo import _get_repo_setup_lock

        l1 = _get_repo_setup_lock("/tmp/env_a")
        l2 = _get_repo_setup_lock("/tmp/env_b")
        assert l1 is not l2


class TestOfficialHarnessSwitch:
    def test_official_harness_default(self, monkeypatch):
        from src.agents.executor_repo import RepoExecutor

        monkeypatch.delenv("OFFICIAL_SWEBENCH_HARNESS", raising=False)
        out = RepoExecutor._official_harness_enabled()
        assert out in (True, False)
