"""tests for scripts/tools/export_swe_bench_source.py（2.1 源码导出自动化）。

覆盖：
- extract_target_file_from_patch：patch 目标文件提取（首个非测试文件 / 全测试文件 / 无 patch）
- resolve_repo_dir：仓库定位（精确 org/name / basename 回退 / 缺失）
- export_instance_sources：dry-run 与 instance_ids 过滤
- write_enrichment_jsonl：仅成功项落盘、格式与 SWE_BENCH_ENRICHMENT 一致
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import importlib.util

# scripts 非包（无 __init__.py），按文件路径加载模块
_SCRIPT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts",
    "tools",
    "export_swe_bench_source.py",
)
_spec = importlib.util.spec_from_file_location("export_swe_bench_source", _SCRIPT_PATH)
mod = importlib.util.module_from_spec(_spec)
sys.modules["export_swe_bench_source"] = mod
_spec.loader.exec_module(mod)


class TestExtractTargetFile:
    """patch 目标文件提取。"""

    def test_first_non_test_file(self):
        patch = (
            "diff --git a/tests/test_a.py b/tests/test_a.py\n"
            "+++ b/tests/test_a.py\n"
            "-assert x\n+assert y\n"
            "diff --git a/mymod/impl.py b/mymod/impl.py\n"
            "+++ b/mymod/impl.py\n"
            "-return 1\n+return 2\n"
        )
        assert mod.extract_target_file_from_patch(patch) == "mymod/impl.py"

    def test_no_b_prefix(self):
        patch = "+++ mymod/impl.py\n"
        assert mod.extract_target_file_from_patch(patch) == "mymod/impl.py"

    def test_all_test_files_returns_none(self):
        patch = "+++ b/tests/test_a.py\n"
        assert mod.extract_target_file_from_patch(patch) is None

    def test_dev_null_skipped(self):
        patch = "+++ /dev/null\n"
        assert mod.extract_target_file_from_patch(patch) is None

    def test_empty_patch(self):
        assert mod.extract_target_file_from_patch("") is None
        assert mod.extract_target_file_from_patch(None) is None


class TestResolveRepoDir:
    """仓库定位（tmp_path 模拟克隆目录）。"""

    def test_exact_org_name(self, tmp_path):
        (tmp_path / "django" / "django").mkdir(parents=True)
        resolved = mod.resolve_repo_dir("django/django", tmp_path)
        assert resolved == tmp_path / "django" / "django"

    def test_basename_fallback(self, tmp_path):
        (tmp_path / "django").mkdir()
        resolved = mod.resolve_repo_dir("django/django", tmp_path)
        assert resolved == tmp_path / "django"

    def test_missing_returns_none(self, tmp_path):
        assert mod.resolve_repo_dir("foo/bar", tmp_path) is None


class TestWriteEnrichment:
    """enrichment JSONL 落盘。"""

    def test_only_success_rows(self, tmp_path):
        results = [
            mod.InstanceSource("a__1", "r/r", "c1", "a.py", source_code="def f(): pass"),
            mod.InstanceSource("a__2", "r/r", "c2", "b.py", source_code=None),
        ]
        out = tmp_path / "enrich.jsonl"
        written = mod.write_enrichment_jsonl(results, out)
        assert written == 1
        lines = out.read_text(encoding="utf-8").strip().splitlines()
        row = json.loads(lines[0])
        assert row["instance_id"] == "a__1"
        assert row["instance_code"] == "def f(): pass"

    def test_roundtrip_loader_enrichment_format(self, tmp_path):
        """写出的 JSONL 行可被 SWEBenchDataset._load_enrichment 消费（格式回归护栏）。"""
        results = [mod.InstanceSource("x__1", "r/r", "c", "x.py", source_code="def g(): pass")]
        out = tmp_path / "enrich.jsonl"
        mod.write_enrichment_jsonl(results, out)
        from src.datasets.dataset_loader import SWEBenchDataset

        enriched = SWEBenchDataset._load_enrichment(str(out))
        assert "x__1" in enriched
        assert enriched["x__1"]["instance_code"] == "def g(): pass"


class TestExportInstanceSources:
    """批量导出（dry-run + instance_ids 过滤）。"""

    def _instances(self):
        return [
            {
                "instance_id": "r__1",
                "repository": "org/r",
                "base_commit": "abc123",
                "patch": "+++ b/r/mod.py\n",
            },
            {
                "instance_id": "r__2",
                "repository": "org/r",
                "base_commit": "def456",
                "patch": "+++ b/r/other.py\n",
            },
        ]

    def test_dry_run_marks_missing_repo(self, tmp_path):
        # 仓库目录不存在 → dry-run 下 source_code=None（MISSING）
        results = mod.export_instance_sources(self._instances(), tmp_path, dry_run=True)
        assert len(results) == 2
        assert all(not r.ok for r in results)
        assert results[0].target_file == "r/mod.py"

    def test_instance_ids_filter(self, tmp_path):
        results = mod.export_instance_sources(self._instances(), tmp_path, instance_ids=["r__2"], dry_run=True)
        assert [r.instance_id for r in results] == ["r__2"]

    def test_repo_present_dry_run_ok(self, tmp_path):
        (tmp_path / "org" / "r").mkdir(parents=True)
        results = mod.export_instance_sources(self._instances(), tmp_path, dry_run=True)
        assert all(r.ok for r in results)
        assert results[0].source_code == "(dry-run)"


class TestResolveRepoDirRequiresGitDir:
    """2026-10-30 实跑缺陷：同名文件/同名非仓库子目录被当成克隆根。

    NodeBB 仓库根有一个可执行脚本 `NodeBB`、openlibrary 仓库根有一个同名包
    目录——旧实现用 `exists()` 判定，把二者当克隆根，git 随后在非仓库路径
    上执行（38 + 1 条实例被误判为"仓库未克隆"）。
    """

    def _make_repo(self, path):
        (path / ".git").mkdir(parents=True)
        (path / "impl.py").write_text("x = 1\n", encoding="utf-8")

    def test_same_named_file_does_not_shadow_repo(self, tmp_path):
        repo = tmp_path / "NodeBB"
        self._make_repo(repo)
        (repo / "NodeBB").write_text("#!/usr/bin/env node\n", encoding="utf-8")
        resolved = mod.resolve_repo_dir("NodeBB/NodeBB", tmp_path)
        assert resolved == repo
        assert (resolved / ".git").is_dir()

    def test_exact_plain_dir_falls_back_to_basename_repo(self, tmp_path):
        repo = tmp_path / "openlibrary"
        self._make_repo(repo)
        (repo / "openlibrary").mkdir()
        resolved = mod.resolve_repo_dir("internetarchive/openlibrary", tmp_path)
        assert resolved == repo

    def test_missing_repo_returns_none(self, tmp_path):
        assert mod.resolve_repo_dir("no/such", tmp_path) is None


class TestExtractTargetFiles:
    """多路径回退的候选顺序：去重、跳过测试文件与 /dev/null。"""

    def test_ordered_dedup_and_test_filter(self):
        patch = (
            "+++ b/changelogs/fragments/1.yml\n"
            "+++ b/lib/ansible/mod.py\n"
            "+++ b/lib/ansible/mod.py\n"
            "+++ b/tests/test_mod.py\n"
            "+++ /dev/null\n"
        )
        assert mod.extract_target_files_from_patch(patch) == [
            "changelogs/fragments/1.yml",
            "lib/ansible/mod.py",
        ]

    def test_empty(self):
        assert mod.extract_target_files_from_patch("") == []
        assert mod.extract_target_files_from_patch(None) == []


class TestExportMultiPathFallback:
    """首文件在 base_commit 不存在时，按补丁内顺序回退到真实存在的源码。"""

    def _init_repo(self, repo: Path) -> str:
        import subprocess

        repo.mkdir(parents=True)
        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.com",
        }
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True, env=env)
        (repo / "impl.py").write_text("def f():\n    return 1\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo, check=True, env=env)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=repo, check=True, env=env)
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True, env=env
        )
        return head.stdout.strip()

    def test_falls_back_to_existing_file(self, tmp_path):
        repo = tmp_path / "repos" / "org" / "r"
        commit = self._init_repo(repo)
        instances = [
            {
                "instance_id": "r__1",
                "repo": "org/r",
                "base_commit": commit,
                # 首文件是补丁新建的 changelog（base 上不存在），第二文件才存在
                "patch": ("+++ b/changelog/1.yml\n+new: yes\n+++ b/impl.py\n-return 1\n+return 2\n"),
            }
        ]
        results = mod.export_instance_sources(instances, tmp_path / "repos")
        assert len(results) == 1
        assert results[0].ok, "应通过多路径回退导出成功"
        assert results[0].target_file == "impl.py"
        assert "return 1" in results[0].source_code
