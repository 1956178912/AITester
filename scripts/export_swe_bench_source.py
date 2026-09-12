"""2.1 SWE-bench 源码补充文件自动导出脚本。

背景：
    官方 SWE-bench JSONL 不含被测源码字段（instance_code），加载器只能
    兜底为 issue 文本，此类任务在基准中仅验证流程、不产生有效修复对比。
    此前需手动准备 SWE_BENCH_ENRICHMENT 补充文件（JSONL，按 instance_id
    关联），本脚本把"git checkout 目标文件内容"的批量操作自动化。

导出逻辑：
    1. 读取已下载的 SWE-bench JSONL（~/.cache/aitester/swe_bench/）；
    2. 按 repository 分组，在本地克隆目录（--repos-dir）中定位各仓库；
    3. 对每个 instance 用 `git show <base_commit>:<target_file>` 导出被测
       源码（target_file 从官方 patch 的 "+++ b/<path>" 行提取，多文件补丁
       取首个非测试文件）；
    4. 输出 SWE_BENCH_ENRICHMENT 格式的 JSONL（instance_id + instance_code），
       加载器经环境变量 SWE_BENCH_ENRICHMENT 消费。

使用方式：
    # 批量导出 lite 子集全部任务的源码（需先在 --repos-dir 下克隆各仓库）
    python scripts/export_swe_bench_source.py --subset lite \
        --repos-dir ~/swe_repos --output enrichment_lite.jsonl

    # 仅导出指定 instance（配合 check-dataset 输出的缺失源码列表）
    python scripts/export_swe_bench_source.py --subset lite \
        --instance-ids django__django-11525 --repos-dir ~/swe_repos

    # dry-run：只打印将导出的 (instance_id, target_file, base_commit)，不执行 git
    python scripts/export_swe_bench_source.py --subset lite --dry-run
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import click

# 项目根入路径（与 download_swe_bench.py 同口径）
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger(__name__)

# 默认缓存目录（与 SWEBenchDataset.DEFAULT_CACHE_DIR 一致）
_DEFAULT_SWE_CACHE_DIR = Path.home() / ".cache" / "aitester" / "swe_bench"

# 目标文件提取：patch 中 "+++ b/<path>"（或裸路径）行；测试文件标记
_RE_NEW_FILE_PATH = re.compile(r"^\+\+\+ (?:b/)?(\S+)")
# 视为"测试文件"的路径特征（源码导出取首个非测试文件）
_TEST_FILE_MARKERS = ("test_", "_test.py", "tests/", "testing/", "conftest.py")


@dataclass
class InstanceSource:
    """单个 instance 的源码导出结果。"""

    instance_id: str
    repository: str
    base_commit: str
    target_file: str
    source_code: str | None = None  # None 表示导出失败

    @property
    def ok(self) -> bool:
        return self.source_code is not None


def read_jsonl_instances(jsonl_path: str | Path) -> list[dict]:
    """读取 SWE-bench JSONL 文件为 dict 列表（容错坏行）。"""
    items: list[dict] = []
    with open(jsonl_path, encoding="utf-8") as f:
        for _line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                logger.warning("JSON 解析失败（%s 第 %d 行），跳过: %s...", _line_num, jsonl_path, line[:60])
    return items


def extract_target_file_from_patch(patch_text: str) -> str | None:
    """从官方修复 patch 提取首个非测试目标文件路径。

    解析 "+++ b/<path>" 行；跳过测试文件（path 含测试标记）与 /dev/null；
    多文件补丁返回首个非测试文件（被测源码通常在此）。

    Args:
        patch_text: git diff 格式补丁文本。

    Returns:
        首个非测试目标文件路径；无 patch 或全部为测试文件时返回 None。
    """
    if not patch_text:
        return None
    for line in patch_text.splitlines():
        m = _RE_NEW_FILE_PATH.match(line.strip())
        if not m:
            continue
        path = m.group(1)
        if path == "/dev/null":
            continue
        if any(marker in path for marker in _TEST_FILE_MARKERS):
            continue
        return path
    return None


def resolve_repo_dir(repository: str, repos_dir: str | Path) -> Path | None:
    """在 --repos-dir 下定位仓库克隆目录（支持 org/name 与任意子目录匹配）。"""
    repos_root = Path(repos_dir).expanduser()
    if not repos_root.exists():
        return None
    # 优先精确 org/name；回退为按 basename 匹配（如 django/django → django）
    exact = repos_root / repository
    if exact.exists():
        return exact
    candidate = repos_root / repository.split("/")[-1]
    if candidate.exists():
        return candidate
    return None


def git_show_file(repo_dir: Path, base_commit: str, file_path: str, timeout: int = 30) -> str | None:
    """用 `git show <commit>:<path>` 只读导出文件内容（不污染工作树）。

    Args:
        repo_dir: 仓库克隆目录。
        base_commit: 被测版本 commit（SWE-bench instance 的 base_commit 字段）。
        file_path: 仓库内相对路径。
        timeout: 子进程超时秒数。

    Returns:
        文件内容；git 失败（路径不存在/commit 未 fetch）时返回 None。
    """
    cmd = ["git", "-C", str(repo_dir), "show", f"{base_commit}:{file_path}"]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.warning("git show 异常（%s @ %s:%s）: %s", base_commit, repo_dir.name, file_path, e)
        return None
    if proc.returncode != 0:
        logger.warning(
            "git show 失败（%s @ %s:%s）: %s",
            base_commit,
            repo_dir.name,
            file_path,
            (proc.stderr or "").strip()[:200],
        )
        return None
    return proc.stdout


def export_instance_sources(
    instances: list[dict],
    repos_dir: str | Path,
    instance_ids: list[str] | None = None,
    dry_run: bool = False,
    timeout: int = 30,
) -> list[InstanceSource]:
    """批量导出 instance 的被测源码。

    Args:
        instances: JSONL 解析后的 dict 列表。
        repos_dir: 本地仓库克隆根目录。
        instance_ids: 仅导出指定 instance（None = 全部）。
        dry_run: 只计算目标文件与路径，不执行 git show。
        timeout: 单条 git show 超时秒数。

    Returns:
        InstanceSource 列表（失败项 source_code=None）。
    """
    results: list[InstanceSource] = []
    repo_dirs: dict[str, Path | None] = {}

    for data in instances:
        instance_id = data.get("instance_id", "")
        if instance_ids is not None and instance_id not in instance_ids:
            continue
        repository = data.get("repository", "")
        base_commit = data.get("base_commit", "")
        target_file = extract_target_file_from_patch(data.get("patch", ""))
        if not target_file:
            logger.info("instance %s: patch 无可导出目标文件，跳过", instance_id)
            continue

        # 仓库定位缓存（同 repo 多条 instance 复用）
        if repository not in repo_dirs:
            repo_dirs[repository] = resolve_repo_dir(repository, repos_dir)

        source = InstanceSource(
            instance_id=instance_id,
            repository=repository,
            base_commit=base_commit,
            target_file=target_file,
        )

        if dry_run:
            source.source_code = "(dry-run)" if repo_dirs[repository] else None
            results.append(source)
            continue

        repo_dir = repo_dirs[repository]
        if repo_dir is None:
            source.source_code = None
            results.append(source)
            continue

        source.source_code = git_show_file(repo_dir, base_commit, target_file, timeout=timeout)
        results.append(source)

    return results


def write_enrichment_jsonl(results: list[InstanceSource], output_path: str | Path) -> int:
    """把导出结果写为 SWE_BENCH_ENRICHMENT 格式 JSONL（仅成功项）。

    Args:
        results: export_instance_sources 的输出。
        output_path: 输出 JSONL 路径。

    Returns:
        写入的成功条数。
    """
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with open(out, "w", encoding="utf-8") as f:
        for r in results:
            if not r.ok:
                continue
            f.write(
                json.dumps({"instance_id": r.instance_id, "instance_code": r.source_code}, ensure_ascii=False) + "\n"
            )
            written += 1
    return written


def load_jsonl_for_subset(subset: str, data_dir: str | Path) -> list[dict]:
    """按子集名定位已下载 JSONL（与下载脚本的写盘约定一致）。"""
    root = Path(data_dir).expanduser()
    path = root / f"swe_bench_{subset}_instances.jsonl"
    if not path.exists():
        path = root / "swe_bench_instances.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"SWE-bench JSONL 未找到: {path}（请先运行 scripts/download_swe_bench.py）")
    return read_jsonl_instances(path)


@click.command()
@click.option("--subset", "-s", default="lite", help="数据集子集: lite/mini/full")
@click.option("--data-dir", default=None, help=f"SWE-bench JSONL 目录（默认 {_DEFAULT_SWE_CACHE_DIR}）")
@click.option("--repos-dir", "-r", default=None, help="本地仓库克隆根目录（含各 org/name）")
@click.option("--instance-ids", "-i", default=None, help="仅导出指定 instance（逗号分隔或 @文件）")
@click.option("--output", "-o", default=None, help="输出 enrichment JSONL 路径")
@click.option("--dry-run", is_flag=True, help="只打印导出计划，不执行 git show")
def cli(
    subset: str,
    data_dir: str | None,
    repos_dir: str | None,
    instance_ids: str | None,
    output: str | None,
    dry_run: bool,
) -> None:
    """导出 SWE-bench 被测源码为 enrichment JSONL（2.1 源码补充流程自动化）。"""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    jsonl_path = load_jsonl_for_subset(subset, data_dir or _DEFAULT_SWE_CACHE_DIR)
    instances = read_jsonl_instances(jsonl_path)
    logger.info("读取 %d 条 instance（%s）", len(instances), jsonl_path)

    # instance_ids 支持逗号分隔或 @文件
    id_list: list[str] | None = None
    if instance_ids:
        if instance_ids.startswith("@"):
            with open(instance_ids[1:], encoding="utf-8") as f:
                id_list = [item.strip() for item in f if item.strip()]
        else:
            id_list = [s.strip() for s in instance_ids.split(",") if s.strip()]

    if not dry_run and not repos_dir:
        click.echo("错误: 非 dry-run 模式必须指定 --repos-dir（本地仓库克隆目录）", err=True)
        sys.exit(1)

    results = export_instance_sources(
        instances,
        repos_dir=repos_dir or ".",
        instance_ids=id_list,
        dry_run=dry_run,
    )

    if dry_run:
        ok = [r for r in results if r.ok]
        logger.info("dry-run: %d 条可导出, %d 条缺仓库/无目标文件", len(ok), len(results) - len(ok))
        for r in results[:50]:
            status = "OK" if r.ok else "MISSING"
            print(f"[{status}] {r.instance_id}  {r.repository} @ {r.base_commit[:12]}  {r.target_file}")
        return

    # 默认输出路径：与 data_dir 同级的 enrichment_<subset>.jsonl
    out_path = output or str(Path(jsonl_path).parent / f"swe_bench_{subset}_enrichment.jsonl")
    written = write_enrichment_jsonl(results, out_path)
    failed = len(results) - written
    logger.info("导出完成: 成功 %d, 失败 %d → %s", written, failed, out_path)
    click.echo(f"\n导出 {written} 条源码至 {out_path}")
    if failed:
        click.echo(f"失败 {failed} 条（仓库未克隆或目标文件缺失），详见上方 warning")
    click.echo("\n使用方式: export SWE_BENCH_ENRICHMENT=<此文件路径> 后运行 benchmark")


if __name__ == "__main__":
    cli()
