"""AS 批次（2026-10-07 第十五轮审查续四）锁定测试。

覆盖两项自主执行项：
- AS1 发行构建链路现代化与验证：PEP 639 license（SPDX 表达式 +
  license-files + [build-system] setuptools>=77）落地并经真实构建链
  验证（wheel METADATA 产出 Metadata-Version 2.4 / License-Expression:
  MIT；全新 venv 安装 + CLI 冒烟通过——本文件锁静态声明面，运行链
  验证由 `make build-check` 承担）；
- AS2 `make build-check` 目标在位（发行链路的本地可复现冒烟入口，
  发布批次 AL9 决定是否接 CI）。

背景：十五轮审查从未真正走过发行构建链路——本批基线取证证明
O9/O35/X4 打包链端到端无 latent bug（wheel 构建/依赖解析/入口/导入
全绿），AS1b 在该基线上完成最后一个 survey 打包缺口。
"""

from __future__ import annotations

import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

PYPROJECT = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
MAKEFILE = (PROJECT_ROOT / "Makefile").read_text(encoding="utf-8")


class TestPEP639License:
    """AS1：license 元数据现代化（survey 打包缺口的最后一项）。"""

    def test_license_is_spdx_expression(self) -> None:
        """[project].license 为 SPDX 字符串（PEP 639），旧式 {file=…} 表
        不得残留；license-files 通配列表在位。"""
        license_field = PYPROJECT["project"]["license"]
        assert license_field == "MIT", f"license 应为 SPDX 字符串，实际 {license_field!r}"
        license_files = PYPROJECT["project"]["license-files"]
        assert license_files == ["LICENSE"]
        assert not isinstance(license_field, dict)

    def test_build_system_requires_modern_setuptools(self) -> None:
        """[build-system] requires 含 setuptools>=77.0（PEP 639 实现下限）。"""
        requires = PYPROJECT["build-system"]["requires"]
        assert any(req.startswith("setuptools>=77") for req in requires), requires

    def test_setup_py_shim_license_files_aligned(self) -> None:
        """setup.py shim 的 license_files 键名与 PEP 639 一致（回退路径）。"""
        setup_py = (PROJECT_ROOT / "setup.py").read_text(encoding="utf-8")
        assert 'license_files=["LICENSE"]' in setup_py


class TestBuildCheckTarget:
    """AS2：发行链路冒烟的本地可复现入口。"""

    def test_makefile_has_build_check(self) -> None:
        """build-check 目标在 Makefile 且声明了四个关键步骤。"""
        assert "build-check:" in MAKEFILE
        assert "python -m build --wheel" in MAKEFILE.replace("$(PY) -m", "python -m")
        assert "aitester_build_check" in MAKEFILE
        assert "--version" in MAKEFILE
        assert "build-check OK" in MAKEFILE
