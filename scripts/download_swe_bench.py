"""SWE-bench 数据集下载与预处理脚本。

使用方式：
    python scripts/download_swe_bench.py --subset lite --output ~/.cache/aitester/swe_bench/
"""

import json
import logging
import sys
from pathlib import Path

import click

logger = logging.getLogger(__name__)


def download_swe_bench(subset: str = "lite", output_dir: str | None = None) -> Path:
    if output_dir is None:
        output_dir = Path.home() / ".cache" / "aitester" / "swe_bench"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    # 文件名带子集标识，与 SWEBenchDataset._resolve_jsonl_paths 的读盘约定一致：
    # 指定 subset 时 loader 找 swe_bench_<subset>_instances.jsonl，写死通用名会导致
    # lite 等子集流程找不到文件（未指定 subset 时 loader 会合并所有 swe_bench_* 文件）
    output_file = output_dir / f"swe_bench_{subset}_instances.jsonl"
    if output_file.exists():
        logger.info("数据集已存在: %s", output_file)
        return output_file
    logger.info("正在从 HuggingFace 下载 SWE-bench-%s 数据集...", subset)
    try:
        from datasets import load_dataset

        ds = load_dataset("princeton-nlp/SWE-bench", name=f"swe_bench_{subset}", split="test")
        with open(output_file, "w", encoding="utf-8") as f:
            for item in ds:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        logger.info("下载完成，共 %d 条记录", len(ds))
    except ImportError:
        logger.error("请先安装 datasets 库: pip install datasets")
        sys.exit(1)
    except Exception as e:
        logger.error("下载失败: %s", e)
        sys.exit(1)
    return output_file


@click.command()
@click.option("--subset", "-s", default="lite", help="数据集子集: lite/mini/full")
@click.option("--output", "-o", default=None, help="输出目录")
def cli(subset: str, output: str | None):
    path = download_swe_bench(subset=subset, output_dir=output)
    print(f"数据集已保存至: {path}")


if __name__ == "__main__":
    cli()
